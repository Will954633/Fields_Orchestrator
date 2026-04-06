#!/usr/bin/env python3
"""
Backfill days_on_market on sold records from two sources:

1. Domain timeline: scraped_data.property_timeline has days_on_market for some sales
2. Listing dates: first_listed_timestamp vs sold_date (for properties we scraped while listed)

Does NOT overwrite existing days_on_market values.

Usage:
  python3 scripts/backfill_days_on_market.py                  # dry run, all suburbs
  python3 scripts/backfill_days_on_market.py --apply           # write to DB
  python3 scripts/backfill_days_on_market.py --suburb robina   # single suburb
"""

import argparse
import os
import sys
import time
from datetime import datetime
from pymongo import MongoClient
from pymongo.errors import OperationFailure


def get_db():
    conn = os.environ.get("COSMOS_CONNECTION_STRING")
    if not conn:
        print("ERROR: COSMOS_CONNECTION_STRING not set")
        sys.exit(1)
    client = MongoClient(conn)
    return client["Gold_Coast"]


def backfill_suburb(db, suburb, apply=False):
    coll = db[suburb]
    sold = list(coll.find(
        {"listing_status": "sold", "days_on_market": {"$in": [None]}},
        {"sold_date": 1, "first_listed_timestamp": 1, "address": 1,
         "scraped_data.property_timeline": 1}
    ))
    # Also get records where field doesn't exist at all
    sold_no_field = list(coll.find(
        {"listing_status": "sold", "days_on_market": {"$exists": False}},
        {"sold_date": 1, "first_listed_timestamp": 1, "address": 1,
         "scraped_data.property_timeline": 1}
    ))
    # Merge (dedupe by _id)
    seen = {str(s["_id"]) for s in sold}
    for s in sold_no_field:
        if str(s["_id"]) not in seen:
            sold.append(s)
            seen.add(str(s["_id"]))

    from_timeline = 0
    from_listing = 0
    skipped = 0

    for record in sold:
        dom = None
        source = None
        sold_date = record.get("sold_date", "")
        if not sold_date:
            skipped += 1
            continue

        # Source 1: Domain timeline (fuzzy match — sold_date vs timeline date
        # can differ by weeks because Domain uses settlement date)
        timeline = record.get("scraped_data", {}).get("property_timeline", [])
        sale_events = [
            t for t in timeline
            if t.get("category") == "Sale" and t.get("is_sold")
            and t.get("days_on_market") is not None and t.get("date")
        ]
        if sale_events:
            try:
                sd = datetime.strptime(sold_date[:10], "%Y-%m-%d")
                best_match = None
                best_diff = 999
                for t in sale_events:
                    td = datetime.strptime(t["date"][:10], "%Y-%m-%d")
                    diff = abs((sd - td).days)
                    if diff <= 60 and diff < best_diff:
                        best_diff = diff
                        best_match = t
                if best_match:
                    dom = int(best_match["days_on_market"])
                    source = "domain_timeline"
            except (ValueError, TypeError):
                pass

        # Source 2: first_listed_timestamp (only if timeline didn't have it)
        if dom is None and record.get("first_listed_timestamp"):
            try:
                flt = record["first_listed_timestamp"]
                if isinstance(flt, str):
                    # Try parsing ISO format
                    flt_date = datetime.fromisoformat(flt.replace("Z", "+00:00")).date()
                elif isinstance(flt, datetime):
                    flt_date = flt.date()
                else:
                    flt_date = None

                if flt_date:
                    sd_date = datetime.strptime(sold_date[:10], "%Y-%m-%d").date()
                    computed = (sd_date - flt_date).days
                    if 0 <= computed <= 730:  # sanity: 0 to 2 years
                        dom = computed
                        source = "computed_from_listing_date"
            except (ValueError, TypeError):
                pass

        if dom is None:
            skipped += 1
            continue

        if source == "domain_timeline":
            from_timeline += 1
        else:
            from_listing += 1

        if apply:
            for attempt in range(5):
                try:
                    coll.update_one(
                        {"_id": record["_id"]},
                        {"$set": {
                            "days_on_market": dom,
                            "days_on_market_source": source
                        }}
                    )
                    break
                except OperationFailure as e:
                    if e.code == 16500:
                        wait = max(0.5, getattr(e, 'details', {}).get('RetryAfterMs', 500) / 1000)
                        time.sleep(wait * (1.5 ** attempt))
                    else:
                        raise

    return from_timeline, from_listing, skipped


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--apply", action="store_true", help="Write changes to DB")
    parser.add_argument("--suburb", help="Single suburb to process")
    args = parser.parse_args()

    db = get_db()

    if args.suburb:
        suburbs = [args.suburb]
    else:
        suburbs = ["robina", "burleigh_waters", "varsity_lakes",
                    "mudgeeraba", "reedy_creek", "worongary", "merrimac",
                    "mermaid_waters"]

    mode = "APPLYING" if args.apply else "DRY RUN"
    print(f"=== Backfill days_on_market ({mode}) ===\n")

    total_timeline = 0
    total_listing = 0
    total_skipped = 0

    for suburb in suburbs:
        t, l, s = backfill_suburb(db, suburb, apply=args.apply)
        total_timeline += t
        total_listing += l
        total_skipped += s
        print(f"{suburb:20s}: +{t} from timeline, +{l} from listing date, {s} no data")

    print(f"\n{'WROTE' if args.apply else 'Would write'}: "
          f"{total_timeline + total_listing} records "
          f"({total_timeline} timeline + {total_listing} listing date)")
    print(f"No data available: {total_skipped}")


if __name__ == "__main__":
    main()
