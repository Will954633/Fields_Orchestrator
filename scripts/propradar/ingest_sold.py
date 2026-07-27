"""
ingest_sold.py — pull PropRadar settlement-based sold records for core suburbs
into Gold_Coast.propradar_sold (the transaction source-of-truth feed our .py
generators will read). Idempotent upsert keyed by property_id + sold_date.

Usage:
    python3 scripts/propradar/ingest_sold.py --suburb robina --months 60 --dry-run
    python3 scripts/propradar/ingest_sold.py --all --months 60 --apply
"""
from __future__ import annotations

import argparse
import datetime
import os
import sys
from collections import Counter

sys.path.insert(0, "/home/fields/Fields_Orchestrator")
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from shared.db import get_gold_coast_db, cosmos_retry  # noqa: E402
import propradar_client as pr  # noqa: E402

SUBURBS = {
    "robina": "Robina",
    "burleigh_waters": "Burleigh Waters",
    "varsity_lakes": "Varsity Lakes",
}
COLLECTION = "propradar_sold"


def ingest(suburb_key: str, months: int, apply: bool):
    name = SUBURBS[suburb_key]
    records, calls, hdr = pr.fetch_all_sold("QLD", name, months=months)
    dates = sorted(r.get("sold_date", "") for r in records if r.get("sold_date"))
    by_year = Counter(d[:4] for d in dates)
    span = f"{dates[0]}..{dates[-1]}" if dates else "-"
    print(f"\n{name}: {len(records)} records in {calls} calls | span {span} "
          f"| by-year {dict(sorted(by_year.items()))} "
          f"| ratelimit_remaining={hdr.get('x-ratelimit-remaining')}")

    if not apply:
        print("  (dry-run — nothing written)")
        return records

    db = get_gold_coast_db()
    coll = db[COLLECTION]
    now = datetime.datetime.now(datetime.timezone.utc).isoformat()
    n = 0
    for r in records:
        pid, sold_date = r.get("property_id"), r.get("sold_date")
        if not pid or not sold_date:
            continue
        _id = f"{pid}_{sold_date}"
        doc = {
            "_id": _id,
            "property_id": pid,
            "address": r.get("address"),
            "suburb_key": suburb_key,
            "bedrooms": r.get("bedrooms"),
            "bathrooms": r.get("bathrooms"),
            "parking": r.get("parking"),
            "property_type": r.get("property_type"),
            "sold_price": r.get("sold_price"),
            "sold_date": sold_date,
            "source": "propradar",
            "ingested_at": now,
        }
        cosmos_retry(lambda d=doc: coll.replace_one({"_id": d["_id"]}, d, upsert=True),
                     f"propradar_sold.upsert:{_id}")
        n += 1
    print(f"  upserted {n} → Gold_Coast.{COLLECTION}")
    return records


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--suburb", choices=list(SUBURBS))
    ap.add_argument("--all", action="store_true")
    ap.add_argument("--months", type=int, default=60)
    ap.add_argument("--apply", action="store_true", help="write to DB (default dry-run)")
    ap.add_argument("--dry-run", action="store_true")
    args = ap.parse_args()

    targets = list(SUBURBS) if args.all else ([args.suburb] if args.suburb else [])
    if not targets:
        ap.error("pass --suburb <name> or --all")
    apply = args.apply and not args.dry_run
    for s in targets:
        ingest(s, args.months, apply)


if __name__ == "__main__":
    main()
