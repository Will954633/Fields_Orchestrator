#!/usr/bin/env python3
"""
ayh_home_signal.py — permanent CRM record of the "Analyse Your Home → typed own
address" owner signal.

WHY: when someone types their own street address into the Analyse Your Home form
(`analyse_home_address_submit`, which carries `properties.address`), that address is
almost certainly their home — a STRONGER signal than the google→/off-market lookup
that offmarket_home_signal.py captures, because it is explicitly typed rather than
inferred from a click. But nothing was binding it to the CRM:

  - the real-time endpoint analyse-lead-address.mjs only matches contacts by
    `{posthog_ids: <did>}`, so for an already-identified lead (whose device id lives
    in `lead_web.distinct_ids`, not `posthog_ids`) it misses the real contact and at
    best forks an orphan; and the /for-sale-v3 AYH flow does not call it at all.

So the address lived ONLY as a PostHog event and never reached the CRM. This job
reconciles those events onto the correct contact nightly, keyed by EVERY distinct-id
source we hold plus the person's identified email — the same lesson as
leadform_ph_match / lead-link-visit (never key identity off posthog_ids alone).

Discovered 2026-09-04: Rochelle Collins typed "43 Roundelay Drive, Varsity Lakes"
into AYH and read its off-market page, but the CRM never recorded it because her
device id was only in lead_web. See logs/fix-history/2026-09-04.md
[AYH-HOME-SIGNAL-NOT-CAPTURED].

WHAT IT WRITES
  crm_contacts.ayh_home = {address, slug, source:"ayh_address_submit",
                           confidence:"high", at, ph_tagged_slug}
  crm_contacts.property_address  (sticky — only when absent, never clobbers a
                                  confirmed/minisite address)
  PostHog person: home_address / home_address_slug / home_confidence="high" /
                  home_source="ayh_address_submit"  (only when the slug changed,
                  so a nightly re-run doesn't re-POST unchanged persons)

IMPORTANT: crm_sync.py REPLACES the whole contact doc hourly and carries forward
only an explicit allow-list — `ayh_home` has been added there. If you add more
fields here, add them there too.

Self-registers on Systems Health → Process Registry via job_run(cadence_hours=24).
Runs nightly in the 23:40 brain2 chain, right after offmarket_home_signal.py.
"""
from __future__ import annotations

import json
import os
import re
import sys
import urllib.request
from datetime import datetime, timezone

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from ceo_agent_lib import get_client, load_env_file  # noqa: E402
from job_status import job_run  # noqa: E402

SUBMIT_EVENT = "analyse_home_address_submit"   # carries properties.address
LOOKBACK_DAYS = 90

PH_QUERY_URL = "https://us.posthog.com/api/projects/{pid}/query/"
PH_CAPTURE_URL = "https://us.i.posthog.com/i/v0/e/"
PH_INGEST_KEY = (os.environ.get("POSTHOG_INGEST_KEY")
                 or "phc_RQ68rG9adv6NYtoZS4JzmJVzVyOWUfprV9ceHb0nLEs")

_STATE_PC_RE = re.compile(r"^(qld|queensland|nsw|vic|victoria|act|sa|wa|tas|nt)\b.*$", re.I)
_POSTCODE_RE = re.compile(r"^\d{4}$")


def _ph_query(sql: str):
    key = os.environ.get("POSTHOG_PERSONAL_API_KEY")
    pid = os.environ.get("POSTHOG_PROJECT_ID")
    if not key or not pid:
        raise RuntimeError("POSTHOG_PERSONAL_API_KEY / POSTHOG_PROJECT_ID not set")
    req = urllib.request.Request(
        PH_QUERY_URL.format(pid=pid),
        data=json.dumps({"query": {"kind": "HogQLQuery", "query": sql}}).encode(),
        headers={"Authorization": f"Bearer {key}", "Content-Type": "application/json"})
    d = json.loads(urllib.request.urlopen(req, timeout=90).read())
    if "results" not in d:
        raise RuntimeError(f"PostHog query returned no results: {str(d)[:300]}")
    return d["results"]


def slugify_address(addr: str) -> str:
    """"43 Roundelay Drive, Varsity Lakes, QLD 4227" -> "43-roundelay-drive-varsity-lakes"
    — matches the /off-market/<slug> form (street + suburb, state/postcode dropped)."""
    kept = []
    for part in (p.strip() for p in (addr or "").split(",")):
        if not part or _POSTCODE_RE.match(part) or _STATE_PC_RE.match(part):
            continue
        kept.append(part)
    s = re.sub(r"[^a-z0-9]+", "-", "-".join(kept).lower()).strip("-")
    return re.sub(r"-+", "-", s)


def tag_person_home(distinct_id: str, address: str, slug: str) -> bool:
    """Set home_address/home_confidence=high on the PostHog PERSON for this device.
    Best-effort: a PostHog failure never fails the CRM bind."""
    try:
        body = json.dumps({
            "api_key": PH_INGEST_KEY, "event": "$identify", "distinct_id": distinct_id,
            "properties": {
                "$set": {"home_address": address, "home_address_slug": slug,
                         "home_confidence": "high", "home_source": "ayh_address_submit"},
                "$set_once": {"home_first_inferred_at": datetime.now(timezone.utc).isoformat()},
            }}).encode()
        urllib.request.urlopen(urllib.request.Request(
            PH_CAPTURE_URL, data=body, headers={"Content-Type": "application/json"}),
            timeout=10).read()
        return True
    except Exception as e:  # noqa: BLE001 — best-effort
        print(f"  posthog person-tag failed for {distinct_id[:12]} (non-fatal): {e}")
        return False


def _find_contact(db, did: str, email: str):
    """Resolve the ONE real CRM contact for a device id. Key off every id source we
    hold — never posthog_ids alone (an identified lead's device lives in lead_web) —
    then fall back to the person's identified email. Returns the doc or None."""
    c = db["crm_contacts"].find_one({"$or": [
        {"lead_web.posthog_distinct_id": did},
        {"lead_web.distinct_ids": did},
        {"posthog_ids": did},
        {"primary_posthog_id": did},
    ]})
    if c:
        return c
    if email:
        return db["crm_contacts"].find_one({"email": {"$regex": f"^{re.escape(email)}$",
                                                       "$options": "i"}})
    return None


def main() -> None:
    load_env_file()
    with job_run("ayh_home_signal", cadence_hours=24,
                 title="Analyse-Your-Home Address → CRM") as beat:
        db = get_client()["system_monitor"]

        # Most recent typed address per device in the window, + person email hint.
        rows = _ph_query(f"""
            SELECT distinct_id,
                   argMax(properties.address, timestamp) AS address,
                   max(timestamp) AS last_ts,
                   argMax(person.properties.email, timestamp) AS email
            FROM events
            WHERE event = '{SUBMIT_EVENT}'
              AND properties.address != ''
              AND timestamp >= now() - INTERVAL {LOOKBACK_DAYS} DAY
            GROUP BY distinct_id
        """)

        now = datetime.now(timezone.utc)
        # crm_sync carries ayh_home forward as {}; clear any legacy null so a dotted
        # $set can't hit WriteError 28 (same guard offmarket_home_signal uses).
        db["crm_contacts"].update_many({"ayh_home": None}, {"$unset": {"ayh_home": ""}})

        events_scanned = len(rows)
        bound = tagged = created = 0
        unresolved = []
        for did, address, _last_ts, email in rows:
            address = (address or "").strip()
            if not did or not address:
                continue
            slug = slugify_address(address)
            contact = _find_contact(db, did, (email or "").strip())

            if contact is not None:
                q = {"_id": contact["_id"]}
            else:
                # Anonymous submitter we can't tie to a contact yet — upsert a
                # device-keyed contact so the owner signal is never lost (mirrors
                # offmarket_home_signal). A later email bind / crm merge reconciles it.
                q = {"posthog_ids": did}

            db["crm_contacts"].update_one(q, {
                "$set": {
                    "ayh_home.address": address,
                    "ayh_home.slug": slug,
                    "ayh_home.source": "ayh_address_submit",
                    "ayh_home.confidence": "high",
                    "ayh_home.at": now,
                    "updated_at": now,
                    "last_seen": now.date().isoformat(),
                },
                "$addToSet": {"tags": "ayh_home_address_entered",
                              "addresses_searched": address},
                "$setOnInsert": {
                    "posthog_ids": [did], "primary_posthog_id": did,
                    "name": None, "email": None, "phone": None,
                    "source": "ayh_address_submit",
                    "qualification_reason": f"Typed own address in Analyse Your Home → {address}",
                    "first_seen": now.date().isoformat(),
                    "status": "prospect", "owner": "will", "created_at": now,
                },
            }, upsert=(contact is None))
            if contact is None:
                created += 1
                if not email:
                    unresolved.append(did[:8])
            bound += 1

            # Sticky home address — only where absent, so a confirmed/minisite
            # address is never clobbered by this inferred one.
            db["crm_contacts"].update_one(
                {**q, "$or": [{"property_address": None},
                              {"property_address": {"$exists": False}}]},
                {"$set": {"property_address": address}})

            # Tag the PostHog person — only when the slug changed, so a nightly
            # re-run doesn't re-POST every unchanged person.
            cur = db["crm_contacts"].find_one(q, {"ayh_home.ph_tagged_slug": 1})
            already = ((cur or {}).get("ayh_home") or {}).get("ph_tagged_slug")
            if already != slug and tag_person_home(did, address, slug):
                db["crm_contacts"].update_one(q, {"$set": {"ayh_home.ph_tagged_slug": slug}})
                tagged += 1

        beat.detail = (f"{bound} contacts flagged ({created} new device-keyed, "
                       f"{tagged} newly PostHog-tagged) from {events_scanned} AYH "
                       f"address submits ({LOOKBACK_DAYS}d)")
        beat.metrics = {"events_scanned": events_scanned, "contacts_bound": bound,
                        "device_keyed_created": created, "posthog_tagged": tagged,
                        "unresolved_anon": len(unresolved)}
        # Rule 7b — submit events exist but produced 0 binds => the address→CRM
        # reconciliation is broken, not "nobody typed an address".
        if events_scanned > 0 and bound == 0:
            raise RuntimeError(
                f"{events_scanned} AYH address submits scanned but 0 CRM contacts "
                f"written — the address→CRM bind is broken, not idle.")
        print(f"ayh_home_signal: {beat.detail}")


if __name__ == "__main__":
    main()
