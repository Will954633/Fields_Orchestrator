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

import os
import re
import sys
from collections import defaultdict
from datetime import datetime, timezone

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from ceo_agent_lib import get_client, load_env_file  # noqa: E402
from job_status import job_run  # noqa: E402

OFFMARKET_RE = re.compile(r"^/off-market/([a-z0-9][a-z0-9-]{2,80})/?$", re.I)


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
        contacts_updated = 0
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
                        "updated_at": now,
                        "last_seen": now.date().isoformat(),
                    },
                    # $addToSet accumulates every off-market address this person
                    # has googled into — the array, not the query field, so no
                    # scalar/array upsert clash (see minisite-visit.mjs note).
                    "$addToSet": {
                        "tags": "offmarket_google_lookup",
                        "offmarket_home.slugs": {"$each": sorted(slug_set)},
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

        beat.detail = (f"{contacts_updated} contacts flagged from "
                       f"{journeys_scanned} google→off-market sessions")
        beat.metrics = {
            "contacts_updated": contacts_updated,
            "journeys_scanned": journeys_scanned,
            "distinct_addresses": len(wanted),
        }
        print(f"offmarket_home_signal: {beat.detail}")


if __name__ == "__main__":
    main()
