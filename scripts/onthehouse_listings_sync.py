#!/usr/bin/env python3
"""onthehouse_listings_sync.py — current FOR-SALE houses from onthehouse.com.au.

Why this exists
---------------
Domain is not complete. Measured 2026-08-01 on the core three suburbs, houses only,
comparing like-for-like against Domain records refreshed within 14 days:

    Domain 176 | onthehouse 181 | matched 126  ->  72% overlap, onthehouse adds +31%

The 55 listings Domain misses are real and live — spot-checked against their listing
pages: inspections scheduled, modified within 48 hours. And 31 of them were sitting in
`offmarket_discovery` being treated as off-market, including one (41 Olympus Drive,
Robina — under contract with Harcourts) that had a finished appraisal report in
`under_review`. Marketing a home whose owner is already selling with another agent is
the single worst thing this business can do by accident.

So: Domain remains the system of record for enrichment (floor plans, images,
descriptions, withdrawn state, price history — none of which onthehouse has). This job
exists to answer ONE question more completely than Domain can: *is this address on the
market right now?*

Contract
--------
- Writes `system_monitor.onthehouse_listings`. NEVER writes Gold_Coast.
- A fetch failure is UNKNOWN, never "no listings". We only ever expire listings inside a
  suburb whose index we actually fetched, and reconciliation is deferred until all
  fetches are in (an index also returns neighbouring suburbs, so a Burleigh Waters
  listing first seen via the Robina page would otherwise be expired by the BW pass).
- ABSENCE IS NOT EVIDENCE: 28% of genuinely-live Domain listings are missing here, so
  "not in this collection" must never be read as "not for sale". Consumers should treat
  a hit as positive proof of listing and a miss as no information.
- 403/429 aborts the whole run and records an error heartbeat rather than degrading.

Usage:
  python3 scripts/onthehouse_listings_sync.py --dry-run
  python3 scripts/onthehouse_listings_sync.py
"""
from __future__ import annotations

import argparse
import os
import re
import sys
from datetime import datetime, timezone

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from shared.db import get_client
from job_status import job_run
from onthehouse import client as oth
from onthehouse.suburbs import CORE

COLL = "onthehouse_listings"
MAX_PAGES = 12
PAGE_BUDGET_S = 180


def is_house(rec: dict) -> bool:
    """Standalone houses only (Will, 2026-08-01).

    onthehouse's own taxonomy separates House from Townhouse / Apartment / Unit /
    DuplexSemi-detached / Semi-Detached / Villa / Land, and it agreed with Domain's
    property_type on 769/769 matched sold pairs and 236/236 matched sale pairs — so this
    one-word test is trustworthy, unusually for a cross-source type comparison.
    """
    return rec.get("type") == "House"


def shape(rec: dict) -> dict:
    a = rec.get("address") or {}
    lst = rec.get("listing") or {}
    agency = lst.get("agency") or {}
    return {
        "match_key": rec["_key"],
        "suburb_key": rec["_suburb"],
        "found_via": rec["_via"],
        "address": a.get("formattedAddress"),
        "unit": a.get("unitNumber"), "street_number": a.get("streetNumber"),
        "street": a.get("streetName"), "street_type": a.get("streetType"),
        "suburb": a.get("suburb"), "postcode": a.get("postCode"),
        "lat": ((a.get("location") or {}).get("lat")),
        "lon": ((a.get("location") or {}).get("lon")),
        "property_type": rec.get("type"),
        "beds": rec.get("beds"), "baths": rec.get("baths"),
        "car_spaces": rec.get("carSpaces"),
        "land_size": rec.get("landSize"), "floor_size": rec.get("floorSize"),
        # listedDate is 100% populated and is what makes days-on-market derivable here;
        # PropRadar gives current-campaign DOM only and has no list price at all.
        "listed_date": lst.get("listedDate"),
        "display_price": lst.get("displayPrice"),
        "under_offer": bool(rec.get("underOffer")),
        "agency": agency.get("name"),
        "agency_phone": agency.get("phoneNumber"),
        "inspection_count": len(lst.get("inspectionTimes") or []),
        "last_modified": lst.get("lastModifiedDateTime"),
        "listing_id": str(rec.get("id") or rec.get("clPropertyId") or ""),
        "oth_property_id": rec.get("othPropertyId"),
    }


def sync(db, dry_run: bool = False) -> dict:
    now = datetime.now(timezone.utc)
    coll = db[COLL]
    stats = {"suburbs_ok": 0, "suburbs_failed": 0, "active": 0,
             "new": 0, "ended": 0, "pages": 0}

    rows: dict[str, dict] = {}
    covered: set[str] = set()

    for s in CORE:
        recs, meta = oth.crawl_suburb("sale", s["slug"], MAX_PAGES, PAGE_BUDGET_S, want=is_house)
        if recs is None:
            stats["suburbs_failed"] += 1
            print(f"{s['slug']}: FETCH FAILED — nothing in this suburb will be expired")
            continue
        stats["suburbs_ok"] += 1
        stats["pages"] += meta.get("pages", 0)
        covered.add(s["slug"])
        mine = [r for r in recs if r["_suburb"] == s["slug"]]
        print(f"{s['slug']}: {len(mine)} houses in-suburb (+{len(recs)-len(mine)} nearby) "
              f"over {meta.get('pages')} page(s), {meta.get('secs')}s")
        for r in recs:
            rows[r["_key"]] = shape(r)
        if dry_run:
            for r in mine[:3]:
                d = shape(r)
                print(f"    {d['address']}  listed {d['listed_date']}  {d['display_price']}  {d['agency']}")

    stats["active"] = len(rows)
    if dry_run:
        return stats

    for key, row in rows.items():
        res = coll.update_one(
            {"_id": key},
            {"$set": {**row, "active": True, "last_seen": now, "source": "onthehouse"},
             "$setOnInsert": {"first_seen": now}},
            upsert=True)
        if res.upserted_id is not None:
            stats["new"] += 1

    # Expire only inside suburbs we actually fetched. Deferred to here so a listing seen
    # via a neighbouring suburb's index isn't expired by its own suburb's pass.
    if covered:
        stats["ended"] = coll.update_many(
            {"suburb_key": {"$in": sorted(covered)}, "active": True,
             "_id": {"$nin": list(rows)}},
            {"$set": {"active": False, "ended_at": now}}).modified_count
    return stats


def _street_number(address: str) -> str | None:
    """The street number WITH any letter suffix — '27a' for '27A Andromeda Pde',
    '44' for '4/44 Frascott Avenue'. None if unparseable."""
    a = re.sub(r"^\s*(unit|apt|apartment)\s+", "", (address or "").strip(), flags=re.I)
    m = re.match(r"^\s*(?:[\w]+\s*/\s*)?(\d+[a-z]?)\b", a, flags=re.I)
    return m.group(1).lower() if m else None


def is_listed(db, address: str, suburb: str | None = None) -> dict | None:
    """Active onthehouse sale listing for this address, if any.

    A hit is positive proof the home is on the market. A miss means NOTHING — see the
    module docstring. Callers must not infer "safe to market" from None.

    ⚠ The join key deliberately drops a letter suffix ('83a' -> '83', matching.py:81)
    so a unit written '1302a/3' still joins. That is right for a UNIT letter and wrong
    for a STREET-NUMBER letter: 27 and 27A Andromeda Parade are different houses on a
    subdivided block, and both key to `|27|andromeda|robina`. On 2026-08-17 that
    falsely reported 27 Andromeda Parade as listed (the real listing is 27A) and moved
    a live lead off the tracker — the one thing a function documented as "positive
    proof" must never do. 5 of 158 active listings currently carry such a suffix.

    So the key still finds the CANDIDATE, and the street number then has to agree
    exactly. Re-keying the collection would be the deeper fix but needs a full re-sync;
    this closes the false-positive path without one. Only ever narrows a match, so it
    cannot introduce a false negative beyond the miss the docstring already allows.
    """
    from onthehouse.matching import address_key
    k = address_key(address, suburb=suburb)
    if not k:
        return None
    hit = db[COLL].find_one({"_id": k, "active": True})
    if not hit:
        return None
    want, got = _street_number(address), _street_number(hit.get("address", ""))
    if want and got and want != got:
        return None
    return hit


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--dry-run", action="store_true")
    args = ap.parse_args()
    db = get_client()["system_monitor"]

    if args.dry_run:
        st = sync(db, dry_run=True)
        print(f"\ndry-run: {st['active']} active houses across {st['suburbs_ok']} suburb(s), "
              f"{st['pages']} pages, {st['suburbs_failed']} failure(s)")
        return

    with job_run("onthehouse_listings_sync", cadence_hours=24,
                 title="onthehouse For-Sale Houses (Domain gap-fill)") as beat:
        try:
            st = sync(db)
        except oth.Blocked as e:
            # Loud, not silent: being blocked is the one failure mode that would quietly
            # turn this whole source off.
            beat.detail = f"BLOCKED by onthehouse — {e}"
            raise
        beat.detail = (f"{st['active']} active houses across {st['suburbs_ok']} suburb(s); "
                       f"{st['new']} new, {st['ended']} ended, "
                       f"{st['suburbs_failed']} fetch failure(s)")
        beat.metrics = st
        print("\n" + beat.detail)


if __name__ == "__main__":
    main()
