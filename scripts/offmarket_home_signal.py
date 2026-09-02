#!/usr/bin/env python3
"""
offmarket_home_signal.py — permanent CRM record of the "google → /off-market/<addr>"
owner-lookup signal.

WHY: when someone googles their own address and clicks our /off-market/<slug>
result, that address is almost certainly their home (organic-pivot research:
~94% of organic visitors view a single address = owner lookup). The my-home
resolver reads this LIVE from `organic_journeys`, but that collection is rebuilt
nightly on a rolling 60-day window — so a visit older than 60 days silently ages
out of the answer. This job snapshots the signal onto the person's CRM contact
(`crm_contacts.offmarket_home`) so it persists permanently, per the requirement
that the CRM is the source of truth.

Writes a DEDICATED sub-doc (not `probable_address`) so it never ping-pongs with
minisite-visit.mjs, which owns the primary probable_address fields. The resolver
reads `offmarket_home` as a `medium_high` signal.

IMPORTANT: `crm_sync.py` REPLACES the whole contact doc hourly and only carries
forward an explicit allow-list — `offmarket_home` has been added to that list, so
this field survives. If you add more fields here, add them there too.

Runs nightly right after brain2/organic_journey_build.py. Self-registers on the
Systems Health → Process Registry board via job_run(cadence_hours=24).
"""
from __future__ import annotations

import json
import os
import re
import sys
import urllib.request
from collections import defaultdict
from datetime import datetime, timezone

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from ceo_agent_lib import get_client, load_env_file  # noqa: E402
from job_status import job_run  # noqa: E402

OFFMARKET_RE = re.compile(r"^/off-market/([a-z0-9][a-z0-9-]{2,80})/?$", re.I)

# PostHog capture endpoint + public ingest key (the same phc_ token root.tsx / lead-
# link-visit.mjs use — safe to embed; it can only WRITE events). Used to tag the PERSON
# for a device with their inferred home address, so device/person->address is queryable
# inside PostHog, not just Mongo. Best-effort: a PostHog failure never fails the CRM bind.
PH_CAPTURE_URL = "https://us.i.posthog.com/capture/"
PH_INGEST_KEY = (os.environ.get("POSTHOG_INGEST_KEY")
                 or "phc_RQ68rG9adv6NYtoZS4JzmJVzVyOWUfprV9ceHb0nLEs")


def tag_person_home(distinct_id: str, address: str, slug: str) -> bool:
    """Set home_address/home_address_slug/home_confidence on the PostHog PERSON for this
    device. Idempotent ($set). Returns True on a 2xx, False on any error (non-fatal)."""
    try:
        body = json.dumps({
            "api_key": PH_INGEST_KEY,
            "event": "$identify",
            "distinct_id": distinct_id,
            "properties": {
                "$set": {
                    "home_address": address,
                    "home_address_slug": slug,
                    "home_confidence": "medium_high",
                    "home_source": "offmarket_google_lookup",
                },
                "$set_once": {"home_first_inferred_at": datetime.now(timezone.utc).isoformat()},
            },
        }).encode()
        req = urllib.request.Request(
            PH_CAPTURE_URL, data=body, headers={"Content-Type": "application/json"})
        urllib.request.urlopen(req, timeout=10).read()
        return True
    except Exception as e:  # noqa: BLE001 — best-effort, never break the bind
        print(f"  posthog person-tag failed for {distinct_id[:12]} (non-fatal): {e}")
        return False


def offmarket_slug(path: str | None) -> str | None:
    m = OFFMARKET_RE.match((path or "").strip())
    return m.group(1).lower() if m else None


def pretty_address(slug: str) -> str:
    return " ".join(w[:1].upper() + w[1:] for w in (slug or "").split("-")).strip()


def main() -> None:
    load_env_file()
    with job_run("offmarket_home_signal", cadence_hours=24,
                 title="Off-Market Home Signal → CRM") as beat:
        client = get_client()
        db = client["system_monitor"]

        # 1) Pull every google-referred off-market session and extract its address slug.
        #    Per distinct_id, keep the most recent slug + all slugs seen.
        latest: dict[str, tuple[str, datetime]] = {}   # distinct_id -> (slug, t_last)
        all_slugs: dict[str, set] = defaultdict(set)    # distinct_id -> {slug}
        journeys_scanned = 0
        cur = db["organic_journeys"].find(
            {"is_offmarket": True, "referring_domain": {"$regex": "google", "$options": "i"}},
            {"distinct_id": 1, "entry_path": 1, "pages": 1, "t_last": 1},
        )
        for j in cur:
            did = j.get("distinct_id")
            if not did:
                continue
            slugs = set()
            for p in [j.get("entry_path"), *(j.get("pages") or [])]:
                s = offmarket_slug(p)
                if s:
                    slugs.add(s)
            if not slugs:
                continue
            journeys_scanned += 1
            all_slugs[did] |= slugs
            # t_last is an ISO string; lexical compare is chronological for ISO.
            t_last = j.get("t_last") or ""
            # primary = a slug from the most-recent session for this person
            primary = sorted(slugs)[0]
            if did not in latest or str(t_last) >= str(latest[did][1]):
                latest[did] = (primary, t_last)

        # 2) Resolve display addresses (canonical from property_reports if a report
        #    exists for the slug, else prettify the slug — same as the resolver).
        wanted = {s for ss in all_slugs.values() for s in ss}
        addr_map: dict[str, str] = {}
        if wanted:
            for r in db["property_reports"].find(
                {"slug": {"$in": list(wanted)}}, {"slug": 1, "address": 1}
            ):
                if r.get("address"):
                    addr_map[r["slug"]] = r["address"]

        # 3) Upsert each contact's dedicated offmarket_home sub-doc.
        now = datetime.now(timezone.utc)

        # crm_sync.py's hourly whole-doc REPLACE carries `offmarket_home`
        # forward with .get(), which stores an explicit null when the contact
        # has never had one. Mongo cannot create a dotted path inside a null
        # ("Cannot create field 'address' in element {offmarket_home: null}",
        # code 28), so every $set below would raise. crm_sync now carries it
        # forward as {} instead; this clears the nulls already on disk and
        # keeps the job robust if any other writer reintroduces one.
        db["crm_contacts"].update_many(
            {"offmarket_home": None}, {"$unset": {"offmarket_home": ""}}
        )

        contacts_updated = 0
        bound = 0
        tagged = 0
        for did, slug_set in all_slugs.items():
            primary_slug = latest.get(did, (sorted(slug_set)[0], ""))[0]
            primary_addr = addr_map.get(primary_slug) or pretty_address(primary_slug)
            db["crm_contacts"].update_one(
                {"posthog_ids": did},
                {
                    "$set": {
                        "offmarket_home.slug": primary_slug,
                        "offmarket_home.address": primary_addr,
                        "offmarket_home.source": "offmarket_google",
                        "offmarket_home.at": now,
                        "offmarket_home.referrer": "google",
                        # Bind the device for on-site behaviour logging: lead_web_activity.py
                        # harvests every contact with lead_web.posthog_distinct_id set, so
                        # this makes the organic owner's full journey (timeline, dwell, CTA,
                        # article read) appear on their crm-contact page — the same CRM the
                        # FB leads get. distinct_id goes into lead_web ONLY (never posthog_ids
                        # — crm_sync would fork on that). See [[parked_lead_token_identity_join]].
                        "lead_web.posthog_distinct_id": did,
                        "lead_web.source": "offmarket_organic",
                        "lead_web.landing": "offmarket",
                        "lead_web.bound_from": "offmarket_home_signal",
                        "lead_web.bound_at": now.isoformat(),
                        "updated_at": now,
                        "last_seen": now.date().isoformat(),
                    },
                    # $addToSet accumulates every off-market address this person
                    # has googled into — the array, not the query field, so no
                    # scalar/array upsert clash (see minisite-visit.mjs note).
                    "$addToSet": {
                        "tags": "offmarket_google_lookup",
                        "offmarket_home.slugs": {"$each": sorted(slug_set)},
                        "lead_web.distinct_ids": did,
                    },
                    "$setOnInsert": {
                        "posthog_ids": [did],
                        "primary_posthog_id": did,
                        "name": None, "email": None, "phone": None,
                        "company": None, "role": None,
                        "source": "offmarket_google",
                        "qualification_reason": f"Googled own address → {primary_addr}",
                        "first_seen": now.date().isoformat(),
                        "status": "prospect",
                        "lead_quality": None,
                        "owner": "will",
                        "engagement_score": 0,
                        "created_at": now,
                    },
                },
                upsert=True,
            )
            contacts_updated += 1
            bound += 1

            # Sticky home address for the crm-contact page — only where absent, so a
            # contact with a CONFIRMED address (home_confirmed / minisite) is never
            # clobbered by this weaker inferred one.
            db["crm_contacts"].update_one(
                {"posthog_ids": did,
                 "$or": [{"property_address": None}, {"property_address": {"$exists": False}}]},
                {"$set": {"property_address": primary_addr}},
            )

            # Tag the PostHog PERSON with the home address — but only when it changed,
            # so a nightly re-run doesn't re-POST all ~500 unchanged persons every time.
            existing = db["crm_contacts"].find_one(
                {"posthog_ids": did}, {"offmarket_home.ph_tagged_slug": 1})
            already = ((existing or {}).get("offmarket_home") or {}).get("ph_tagged_slug")
            if already != primary_slug and tag_person_home(did, primary_addr, primary_slug):
                db["crm_contacts"].update_one(
                    {"posthog_ids": did},
                    {"$set": {"offmarket_home.ph_tagged_slug": primary_slug}})
                tagged += 1

        beat.detail = (f"{contacts_updated} contacts flagged / {bound} bound for behaviour / "
                       f"{tagged} newly PostHog-tagged, from "
                       f"{journeys_scanned} google→off-market sessions")
        beat.metrics = {
            "contacts_updated": contacts_updated,
            "bound_for_behaviour": bound,
            "posthog_tagged": tagged,
            "journeys_scanned": journeys_scanned,
            "distinct_addresses": len(wanted),
        }
        # Rule 7b — google→off-market sessions exist but produced 0 contacts => the
        # organic_journeys read or the slug extraction is broken, not "no owners looked up".
        if journeys_scanned > 0 and contacts_updated == 0:
            raise RuntimeError(
                f"{journeys_scanned} google→off-market sessions scanned but 0 CRM contacts "
                f"written — the address→CRM bind is broken, not idle.")
        print(f"offmarket_home_signal: {beat.detail}")


if __name__ == "__main__":
    main()
