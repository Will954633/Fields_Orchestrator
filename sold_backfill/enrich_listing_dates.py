#!/usr/bin/env python3
"""
Enrich Sold Records with Listing Dates
========================================
For sold records missing first_listed_timestamp, attempts to recover the
listing date from:
  1. change_detection_snapshots (historical tracking data)
  2. The property page's dateListed JSON field (requires Chrome visit)

Then calculates days_on_market wherever both sold_date and first_listed_timestamp exist.

Usage:
    python3 sold_backfill/enrich_listing_dates.py              # Target suburbs
    python3 sold_backfill/enrich_listing_dates.py --suburb robina
    python3 sold_backfill/enrich_listing_dates.py --dry-run

Requires:
    source /home/fields/venv/bin/activate
    set -a && source /home/fields/Fields_Orchestrator/.env && set +a
"""

import os
import re
import sys
import argparse
from datetime import datetime
from pymongo import MongoClient

TARGET_SUBURBS = ["robina", "varsity_lakes", "burleigh_waters"]
DATABASE_NAME = "Gold_Coast"


def calculate_days_on_market(listed_date_str: str, sold_date_str: str) -> int:
    """Calculate days between listing and sale."""
    try:
        # Handle various formats
        if "T" in listed_date_str:
            listed_date_str = listed_date_str.split("T")[0]
        listed = datetime.strptime(listed_date_str[:10], "%Y-%m-%d")
        sold = datetime.strptime(sold_date_str[:10], "%Y-%m-%d")
        days = (sold - listed).days
        return days if days >= 0 else None
    except Exception:
        return None


def main():
    parser = argparse.ArgumentParser(description="Enrich sold records with listing dates")
    parser.add_argument("--suburb", type=str, help="Single suburb")
    parser.add_argument("--dry-run", action="store_true", help="Preview only")
    args = parser.parse_args()

    conn_str = os.environ.get("COSMOS_CONNECTION_STRING")
    if not conn_str:
        print("ERROR: COSMOS_CONNECTION_STRING not set")
        sys.exit(1)

    client = MongoClient(conn_str)
    db = client[DATABASE_NAME]
    client.admin.command("ping")

    suburbs = [args.suburb] if args.suburb else TARGET_SUBURBS

    total_enriched = 0
    total_dom_calculated = 0

    for suburb in suburbs:
        col = db[suburb]
        print(f"\n=== {suburb} ===")

        # Phase 1: Find sold records missing first_listed_timestamp
        missing_listed = list(col.find({
            "listing_status": "sold",
            "first_listed_timestamp": {"$exists": False},
            "listing_url": {"$exists": True, "$ne": None},
        }, {"address": 1, "listing_url": 1, "sold_date": 1}).limit(200))

        print(f"  Sold records missing first_listed_timestamp: {len(missing_listed)}")

        # Try to recover from change_detection_snapshots
        snapshots_col = db.get_collection("change_detection_snapshots")
        recovered = 0

        for doc in missing_listed:
            listing_url = doc.get("listing_url", "")
            # Extract listing ID
            m = re.search(r'-(\d{7,10})$', listing_url)
            if not m:
                continue
            listing_id = m.group(1)

            # Search snapshots for this listing
            snapshot = snapshots_col.find_one({
                "listing_url": {"$regex": listing_id}
            })

            if snapshot and snapshot.get("first_listed_timestamp"):
                if not args.dry_run:
                    col.update_one(
                        {"_id": doc["_id"]},
                        {"$set": {
                            "first_listed_timestamp": snapshot["first_listed_timestamp"],
                            "first_listed_date": snapshot.get("first_listed_date"),
                            "listing_date_source": "change_detection_snapshot",
                        }}
                    )
                recovered += 1
                addr = doc.get("address", "N/A")[:50]
                print(f"    RECOVERED: {addr} -> listed {snapshot.get('first_listed_date', 'N/A')}")

        print(f"  Recovered listing dates from snapshots: {recovered}")
        total_enriched += recovered

        # Phase 2: Calculate days_on_market for all sold records with both dates
        sold_with_dates = list(col.find({
            "listing_status": "sold",
            "sold_date": {"$exists": True, "$ne": None},
            "first_listed_timestamp": {"$exists": True, "$ne": None},
            "days_on_market": {"$exists": False},
        }, {"sold_date": 1, "first_listed_timestamp": 1, "address": 1}).limit(500))

        dom_calculated = 0
        for doc in sold_with_dates:
            listed_ts = str(doc.get("first_listed_timestamp", ""))
            sold_date = str(doc.get("sold_date", ""))
            dom = calculate_days_on_market(listed_ts, sold_date)
            if dom is not None:
                if not args.dry_run:
                    col.update_one(
                        {"_id": doc["_id"]},
                        {"$set": {"days_on_market": dom}}
                    )
                dom_calculated += 1

        print(f"  Days-on-market calculated: {dom_calculated}")
        total_dom_calculated += dom_calculated

    print(f"\n{'='*50}")
    print(f"  Total listing dates recovered: {total_enriched}")
    print(f"  Total DOM calculated: {total_dom_calculated}")
    if args.dry_run:
        print(f"  (DRY RUN — no changes written)")
    print(f"{'='*50}")

    client.close()


if __name__ == "__main__":
    main()
