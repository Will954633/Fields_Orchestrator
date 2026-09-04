#!/usr/bin/env python3
"""
leadform_ph_match.py — join a Meta Instant-Form (leadform) lead to its anonymous
PostHog session by TIMESTAMP MATCH.

Why this exists
---------------
A native Meta leadform (`destination_type=ON_AD`) captures name/email/phone INSIDE
Facebook, so the person never lands an identified session on our site — they are
invisible in PostHog (see fix-history [LEAD-TOKEN-IDENTITY-JOIN], "only pure
Instant-Form leads with no click-through stay PostHog-invisible, which is
structural"). BUT many tap the leadform's "View website" completion button through
to `/for-sale-v3` seconds later. If — and only if — exactly ONE anonymous,
Facebook-referred landing occurs in a tight window after the form submission, that
landing is almost certainly the same person, and we can identify them.

The match is only as trustworthy as the base rate. `/for-sale-v3` gets ~1 landing
per several hours, so a single hit 18s after a submission is ~99.9% not a
coincidence. The guard that makes this safe is UNIQUENESS, not the gap: if two
people land in the window we ABSTAIN rather than guess. Every join is stamped
`match_method="timestamp_inferred"` so a probabilistic join is never mistaken for a
hard identity (contrast the token path, which is a certain identity).

Trigger
-------
Called from fb-lead-puller.py for each new non-test lead, right after the CRM
upsert (the "form-fill event" in our 3-min polling architecture). Because the
puller can occasionally see a lead BEFORE the person taps through, a first attempt
that finds no candidate is left `pending`; `sweep_pending()` re-attempts recent
unmatched leads on the next poll so a landing that arrives after the first attempt
is still caught.

Landmines respected (same as lead-link-visit.mjs / crm_sync.py)
---------------------------------------------------------------
- Join key goes to `crm_contacts.lead_web.posthog_distinct_id` ONLY — NEVER
  `posthog_ids`/`primary_posthog_id` (crm_sync re-keys `_id` off those and would
  fork the email-keyed lead, dropping lead_attribution + follow_up_at).
- `lead_web` is in crm_sync's carry-forward allow-list, so the hourly full-doc
  replace preserves the join.
"""

import os
import sys
import requests
from datetime import datetime, timezone, timedelta

PH_QUERY_URL = "https://us.posthog.com/api/projects/{pid}/query/"
PH_INGEST_URL = "https://us.i.posthog.com/i/v0/e/"
PH_INGEST_KEY = os.environ.get("POSTHOG_INGEST_KEY",
                               "phc_RQ68rG9adv6NYtoZS4JzmJVzVyOWUfprV9ceHb0nLEs")

# Window around the form-submission (created_time) to look for the landing.
# Person fills the FB form, THEN taps through, so the landing is AFTER submission;
# a little slack backwards absorbs clock skew between Meta and PostHog.
WINDOW_BEFORE_S = 90       # tolerate up to 90s of skew (landing "before" submit)
WINDOW_AFTER_S = 900       # 15 min forward — they may browse the ad first
# Only re-attempt leads this fresh in the pending sweep (older => the landing that
# was going to happen already has; stop querying forever).
PENDING_MAX_AGE_MIN = 30
# Landing pages that a leadform completion / ad click can plausibly hit.
LANDING_PATH_LIKE = "%/for-sale%"


def _pid():
    pid = os.environ.get("POSTHOG_PROJECT_ID")
    if not pid:
        raise RuntimeError("POSTHOG_PROJECT_ID not set")
    return pid


def _query(q):
    key = os.environ.get("POSTHOG_PERSONAL_API_KEY")
    if not key:
        raise RuntimeError("POSTHOG_PERSONAL_API_KEY not set")
    r = requests.post(PH_QUERY_URL.format(pid=_pid()),
                      headers={"Authorization": f"Bearer {key}"},
                      json={"query": {"kind": "HogQLQuery", "query": q}}, timeout=60)
    r.raise_for_status()
    d = r.json()
    if "results" not in d:
        raise RuntimeError(f"PostHog query returned no results: {str(d)[:300]}")
    return d["results"]


def _parse_created(created_time):
    """Meta created_time -> aware UTC datetime. Accepts ISO or +0000 offset forms."""
    if not created_time:
        return None
    s = str(created_time).strip()
    # Meta gives e.g. '2026-09-01T09:35:25+0000' or with ':' in the offset.
    try:
        return datetime.fromisoformat(s.replace("+0000", "+00:00"))
    except ValueError:
        try:
            return datetime.strptime(s, "%Y-%m-%dT%H:%M:%S%z")
        except ValueError:
            return None


def find_candidate(created_dt):
    """Return (distinct_id, first_ts, gap_seconds) for the UNIQUE anonymous,
    Facebook-referred landing in the window, or None if 0 or >=2 candidates.

    Uniqueness — not the raw gap — is what makes the match safe."""
    start = (created_dt - timedelta(seconds=WINDOW_BEFORE_S)).strftime("%Y-%m-%d %H:%M:%S")
    end = (created_dt + timedelta(seconds=WINDOW_AFTER_S)).strftime("%Y-%m-%d %H:%M:%S")
    q = f"""
        SELECT distinct_id, min(timestamp) AS first_ts
        FROM events
        WHERE event = '$pageview'
          AND properties.$pathname ILIKE '{LANDING_PATH_LIKE}'
          AND timestamp >= toDateTime('{start}') AND timestamp <= toDateTime('{end}')
          AND (properties.$referrer ILIKE '%facebook%'
               OR properties.$referrer ILIKE '%l.facebook%'
               OR properties.utm_source = 'fb')
          AND (person.properties.email IS NULL OR person.properties.email = '')
        GROUP BY distinct_id
        ORDER BY first_ts
    """
    rows = _query(q)
    if len(rows) != 1:
        return None  # 0 = pending (landing not in yet); >=2 = ambiguous, abstain
    distinct_id, first_ts = rows[0][0], rows[0][1]
    ts = first_ts if isinstance(first_ts, datetime) else datetime.fromisoformat(
        str(first_ts).replace("Z", "+00:00"))
    if ts.tzinfo is None:
        ts = ts.replace(tzinfo=timezone.utc)
    gap = int((ts - created_dt).total_seconds())
    return distinct_id, ts, gap


def _current_person_email(distinct_id):
    """Current (not person-on-events) email for a distinct_id, or '' if the person
    is still anonymous. The events table's `person.properties.email` is frozen at
    ingest time, so a session identified AFTER its pageview still reads as anonymous
    there — this queries live person state, the authority for 'already known?'."""
    rows = _query("SELECT properties.email FROM persons WHERE id IN "
                  f"(SELECT person_id FROM person_distinct_ids WHERE distinct_id='{distinct_id}')")
    return (rows[0][0] if rows and rows[0] and rows[0][0] else "") or ""


def _identify(distinct_id, email, name, phone):
    """Server-side $identify — mirrors identifyPerson() in lead-link-visit.mjs.
    Best-effort: a PostHog 5xx must not fail the match (the join key is stored
    on the CRM doc regardless)."""
    # Identity fields ($set: always win) — name/phone/email are the whole point of
    # the enrichment; they must overwrite whatever a thinner prior identify (e.g. a
    # Netlify landing that set only email) left behind, so the person is searchable
    # by name in PostHog.
    set_props = {"is_lead": True}
    if email:
        set_props["email"] = email
    if name:
        set_props["name"] = name
    if phone:
        set_props["phone"] = phone
    # Provenance fields ($set_once: first-writer-wins) — never clobber a richer or
    # higher-certainty source already on the person (a token match is a certain
    # identity; a specific lead_source like "five_property_friday" is more useful
    # than our generic "fb_lead_ad"). Downgrading those would be wrong.
    set_once = {"first_lead_link_at": datetime.now(timezone.utc).isoformat(),
                "lead_source": "fb_lead_ad",
                "lead_match_method": "timestamp_inferred"}
    try:
        r = requests.post(PH_INGEST_URL, headers={"Content-Type": "application/json"},
                          json={"api_key": PH_INGEST_KEY, "event": "$identify",
                                "distinct_id": distinct_id,
                                "properties": {"$set": set_props,
                                               "$set_once": set_once}},
                          timeout=20)
        return r.status_code == 200
    except Exception as e:
        print(f"    ph $identify failed: {e}", file=sys.stderr)
        return False


def _stamp_crm(db, email, phone, distinct_id, created_dt, land_ts, gap):
    """Stamp the durable join key on the email-keyed (else phone-keyed) contact.
    lead_web ONLY — never posthog_ids (fork landmine)."""
    lead_web = {
        "posthog_distinct_id": distinct_id,
        "distinct_ids": [distinct_id],
        "match_method": "timestamp_inferred",
        "match_gap_seconds": gap,
        "form_submit_at": created_dt.isoformat(),
        "site_landing_at": land_ts.isoformat(),
        "matched_at": datetime.now(timezone.utc).isoformat(),
    }
    q = {"email": email} if email else {"phone": phone}
    res = db["crm_contacts"].update_one(q, {"$set": {"lead_web": lead_web}})
    return res.modified_count


def match_lead(db, lead_doc, mark_state=True):
    """Attempt to timestamp-match one lead to its PostHog landing.
    Returns one of: 'matched', 'pending', 'ambiguous', 'skip'.
    Writes state onto the fb_leads doc (`posthog_match`) when mark_state."""
    fields = lead_doc.get("fields", {}) or {}
    email = fields.get("email")
    phone = fields.get("phone") or fields.get("phone_number")
    name = fields.get("full_name") or fields.get("name")
    created_dt = _parse_created(lead_doc.get("created_time"))
    if not created_dt or (not email and not phone):
        return "skip"

    # Idempotency: don't re-work a lead already matched on a prior poll.
    if (lead_doc.get("posthog_match") or {}).get("status") == "matched":
        return "matched"

    try:
        cand = find_candidate(created_dt)
    except Exception as e:
        print(f"    ph match query failed: {e}", file=sys.stderr)
        return "pending"

    lid = lead_doc.get("_id")
    now = datetime.now(timezone.utc).isoformat()
    if cand is None:
        # Distinguish "no candidate yet" (retry) from "several candidates" (abstain):
        # re-run just the count so state is honest.
        if mark_state and lid is not None:
            prev = (db["fb_leads"].find_one({"_id": lid}, {"posthog_match": 1}) or {})
            attempts = ((prev.get("posthog_match") or {}).get("attempts", 0)) + 1
            db["fb_leads"].update_one({"_id": lid}, {"$set": {"posthog_match": {
                "status": "pending", "attempts": attempts, "last_attempt": now}}})
        return "pending"

    distinct_id, land_ts, gap = cand
    # Authoritative current-state guard (person-on-events can't be trusted here):
    # never claim a session whose person is already identified as SOMEONE ELSE,
    # and treat "already this lead" as an idempotent no-op.
    try:
        cur = _current_person_email(distinct_id).strip().lower()
    except Exception as e:
        print(f"    ph current-person lookup failed: {e}", file=sys.stderr)
        return "pending"
    if cur and email and cur != email.strip().lower():
        print(f"    ph match ABSTAIN: candidate {distinct_id} already identified as "
              f"{cur}, not {email}", file=sys.stderr)
        if mark_state and lead_doc.get("_id") is not None:
            db["fb_leads"].update_one({"_id": lead_doc["_id"]}, {"$set": {"posthog_match": {
                "status": "ambiguous", "reason": "candidate_identified_other",
                "last_attempt": now}}})
        return "ambiguous"
    # `already_ours` (person already carries OUR email) only means "not a conflict"
    # — it does NOT mean nothing to do. A prior thin identify (e.g. a Netlify
    # landing that set email but no name/phone) leaves the person unsearchable by
    # name, so we ALWAYS enrich with name/phone here. _identify is idempotent
    # ($set overwrites, provenance is $set_once). Skipping it was the bug that left
    # matched leads showing only an email in PostHog.
    ok = _identify(distinct_id, email, name, phone)
    modified = _stamp_crm(db, email, phone, distinct_id, created_dt, land_ts, gap)
    if mark_state and lid is not None:
        db["fb_leads"].update_one({"_id": lid}, {"$set": {"posthog_match": {
            "status": "matched", "distinct_id": distinct_id, "gap_seconds": gap,
            "identified": ok, "crm_modified": modified, "matched_at": now}}})
    print(f"    ph timestamp-match: {email or phone} -> {distinct_id} (+{gap}s)")
    return "matched"


def sweep_pending(db):
    """Re-attempt recent leads still unmatched — catches a landing that arrived
    AFTER the first attempt (puller saw the lead before the click-through).
    Returns (matched, still_pending)."""
    cutoff = (datetime.now(timezone.utc) - timedelta(minutes=PENDING_MAX_AGE_MIN)).isoformat()
    q = {"posthog_match.status": "pending",
         "pulled_at": {"$gte": cutoff},
         "test_market": {"$ne": True}}
    matched = pending = 0
    for doc in db["fb_leads"].find(q):
        res = match_lead(db, doc)
        if res == "matched":
            matched += 1
        elif res == "pending":
            pending += 1
    return matched, pending
