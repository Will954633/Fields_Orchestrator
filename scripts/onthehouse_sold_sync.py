#!/usr/bin/env python3
"""onthehouse_sold_sync.py — sold HOUSES from onthehouse.com.au, rolling 12 months.

Why this exists
---------------
Our sold capture has a known hole. Memory `data_source_undercapture_reset` records
Domain landing 40-50% below PropRadar, which made volume and months-of-supply
unreliable. Measured 2026-08-01 on the core three, houses, 12 months:

    Domain 508 | onthehouse 618 | matched 448 | UNION 678

Domain sees 75% of the union even in the suburbs it scrapes nightly. Where the two
overlap they agree almost perfectly — 539/554 matched sale prices identical to the
dollar, property type 769/769 — so the gap is genuine coverage, not a join artefact.
onthehouse also carries `saleSource: "VG"` (Valuer General) records, i.e. government
transfer data rather than agent-reported, which is why it reaches sales Domain never had.

Contract
--------
- Writes `system_monitor.onthehouse_sold`. NEVER writes Gold_Coast.
- OVERLAY, NOT TRUTH. The index is a hard rolling 12-month window (verified: paging to
  exhaustion still stops at 12 months). We hold Domain sold history back to 2023, so
  this must never be treated as the complete picture or used to prune anything older.
- `salePrice: 0` means WITHHELD, not $0. Filtered out, never stored as a price.
- Sold records are immutable history, so unlike listings nothing is ever expired —
  a record leaving the rolling window is not a deletion.
- Nightly runs shallow (SOLD_PAGES_NIGHTLY): new sales enter at page 1, so a few pages
  catch everything. `--deep` does the full 12-month backfill, and is what the weekly
  pass uses to heal anything a shallow run missed.

Usage:
  python3 scripts/onthehouse_sold_sync.py --deep --dry-run
  python3 scripts/onthehouse_sold_sync.py --deep      # first run / weekly
  python3 scripts/onthehouse_sold_sync.py             # nightly, shallow
"""
from __future__ import annotations

import argparse
import os
import sys
from datetime import datetime, timezone

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from shared.db import get_client
from job_status import job_run
from onthehouse import client as oth
from onthehouse.suburbs import CORE

COLL = "onthehouse_sold"
SOLD_PAGES_NIGHTLY = 4
SOLD_PAGES_DEEP = 45
BUDGET_NIGHTLY_S = 90
BUDGET_DEEP_S = 400


def is_house(rec: dict) -> bool:
    return rec.get("type") == "House"


def shape(rec: dict) -> dict | None:
    """Flatten one sold record. None if it carries no usable sale.

    A record with `salePrice` 0/absent is a withheld price, which is common (24% of
    sold houses) and legitimate — we keep the SALE (date, agency) but never invent a
    price for it. A record with no sale date at all is not a sale we can place in time.
    """
    a = rec.get("address") or {}
    sale = rec.get("lastSale") or {}
    guess = rec.get("guesstimate") or {}
    date = sale.get("eventDate")
    if not date:
        return None
    price = sale.get("salePrice") or 0
    agency = (sale.get("sellingAgency") or {})
    return {
        "match_key": rec["_key"],
        "suburb_key": rec["_suburb"],
        "found_via": rec["_via"],
        "address": a.get("formattedAddress"),
        "suburb": a.get("suburb"), "postcode": a.get("postCode"),
        "lat": ((a.get("location") or {}).get("lat")),
        "lon": ((a.get("location") or {}).get("lon")),
        "property_type": rec.get("type"),
        "beds": rec.get("beds"), "baths": rec.get("baths"),
        "car_spaces": rec.get("carSpaces"),
        "land_size": rec.get("landSize"), "floor_size": rec.get("floorSize"),
        "year_built": rec.get("yearBuilt"),
        "sold_date": date,
        "sale_price": int(price) if price and price > 0 else None,
        "price_withheld": not (price and price > 0),
        # VG = Valuer General (government transfer), OTH/RP = agent-reported. Worth
        # keeping: it is the reason this source reaches sales Domain never had.
        "sale_source": sale.get("saleSource"),
        "selling_agency": agency.get("name"),
        # Their AVM. Stored from day one deliberately: scoring it against sales that
        # already happened is contaminated (calculationDate post-dates most of them),
        # so a clean test needs values captured BEFORE the sale. Do not consume it for
        # anything user-facing until that forward test exists.
        "avm_price": guess.get("price"),
        "avm_low": guess.get("fromPrice"), "avm_high": guess.get("toPrice"),
        "avm_confidence": guess.get("confidence"),
        "avm_calculated": guess.get("calculationDate"),
        "cl_property_id": rec.get("clPropertyId"),
        "oth_property_id": rec.get("othPropertyId"),
    }


def sync(db, deep: bool = False, dry_run: bool = False) -> dict:
    now = datetime.now(timezone.utc)
    coll = db[COLL]
    pages = SOLD_PAGES_DEEP if deep else SOLD_PAGES_NIGHTLY
    budget = BUDGET_DEEP_S if deep else BUDGET_NIGHTLY_S
    stats = {"mode": "deep" if deep else "shallow", "suburbs_ok": 0, "suburbs_failed": 0,
             "seen": 0, "new": 0, "updated": 0, "withheld": 0, "pages": 0}

    rows: dict[str, dict] = {}
    for s in CORE:
        recs, meta = oth.crawl_suburb("sold", s["slug"], pages, budget, want=is_house)
        if recs is None:
            stats["suburbs_failed"] += 1
            print(f"{s['slug']}: FETCH FAILED")
            continue
        stats["suburbs_ok"] += 1
        stats["pages"] += meta.get("pages", 0)
        mine = [r for r in recs if r["_suburb"] == s["slug"]]
        print(f"{s['slug']}: {len(mine)} sold houses in-suburb (+{len(recs)-len(mine)} nearby) "
              f"over {meta.get('pages')} page(s), {meta.get('secs')}s")
        for r in recs:
            row = shape(r)
            if row:
                rows[r["_key"]] = row

    stats["seen"] = len(rows)
    stats["withheld"] = sum(1 for r in rows.values() if r["price_withheld"])
    if dry_run:
        return stats

    for key, row in rows.items():
        # Keyed by address + sale date: the same home can sell more than once inside a
        # rolling 12-month window, and collapsing those onto one _id would silently
        # overwrite the earlier sale.
        _id = f"{key}|{row['sold_date']}"
        res = coll.update_one(
            {"_id": _id},
            {"$set": {**row, "last_seen": now, "source": "onthehouse"},
             "$setOnInsert": {"first_seen": now}},
            upsert=True)
        if res.upserted_id is not None:
            stats["new"] += 1
        elif res.modified_count:
            stats["updated"] += 1
    return stats


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--deep", action="store_true",
                    help="full 12-month backfill (weekly); default is the shallow nightly pass")
    ap.add_argument("--dry-run", action="store_true")
    args = ap.parse_args()
    db = get_client()["system_monitor"]

    if args.dry_run:
        st = sync(db, deep=args.deep, dry_run=True)
        print(f"\ndry-run ({st['mode']}): {st['seen']} sold houses, {st['withheld']} price-withheld, "
              f"{st['pages']} pages, {st['suburbs_failed']} failure(s)")
        return

    # Deep and shallow report as the SAME job so the health board tracks one cadence.
    # A shallow run is the normal heartbeat; the weekly deep run just fills more.
    with job_run("onthehouse_sold_sync", cadence_hours=24,
                 title="onthehouse Sold Houses (12-month overlay)") as beat:
        try:
            st = sync(db, deep=args.deep)
        except oth.Blocked as e:
            beat.detail = f"BLOCKED by onthehouse — {e}"
            raise
        beat.detail = (f"{st['mode']}: {st['seen']} sold houses seen across "
                       f"{st['suburbs_ok']} suburb(s); {st['new']} new, {st['updated']} updated, "
                       f"{st['withheld']} price-withheld, {st['suburbs_failed']} fetch failure(s)")
        beat.metrics = st
        print("\n" + beat.detail)


if __name__ == "__main__":
    main()
