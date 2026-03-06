#!/usr/bin/env python3
"""
Backfill Domain Valuation Accuracy
====================================
1. Copies scraped_data.valuation → domain_valuation_at_listing for for_sale properties
   (only if domain_valuation_at_listing doesn't already exist)
2. Computes domain_valuation_accuracy for sold properties that have both
   a Domain valuation and a sale price.

Usage:
    python3 scripts/backfill_domain_valuation_accuracy.py [--dry-run]
"""

import os
import re
import sys
import time
import argparse
from datetime import datetime
from pymongo import MongoClient
from pymongo.errors import WriteError

MONGODB_URI = os.getenv('COSMOS_CONNECTION_STRING') or os.getenv('MONGODB_URI', 'mongodb://127.0.0.1:27017/')
DATABASE_NAME = 'Gold_Coast'
SKIP_COLLECTIONS = {'system.', 'suburb_median_prices', 'suburb_statistics', 'change_detection_snapshots'}


def retry_write(func, max_retries=5):
    """Retry a write operation with backoff on CosmosDB 429 errors."""
    for attempt in range(max_retries):
        try:
            return func()
        except WriteError as e:
            if e.code == 16500 and attempt < max_retries - 1:
                # Extract RetryAfterMs from error message
                m = re.search(r'RetryAfterMs=(\d+)', str(e))
                wait_ms = int(m.group(1)) if m else 500
                time.sleep(max(wait_ms / 1000.0, 0.5))
            else:
                raise


def get_collections(db):
    return [c for c in db.list_collection_names()
            if not any(c.startswith(s) if s.endswith('.') else c == s for s in SKIP_COLLECTIONS)]


def parse_price(price_str):
    """Extract numeric price from string like '$1,520,000'."""
    if not price_str:
        return None
    m = re.search(r'\$?([\d,]+)', str(price_str))
    if m:
        try:
            return int(m.group(1).replace(',', ''))
        except ValueError:
            return None
    return None


def backfill_listing_snapshots(db, dry_run=False):
    """Copy scraped_data.valuation → domain_valuation_at_listing for for_sale properties."""
    print("\n" + "=" * 70)
    print("PHASE 1: Snapshot domain_valuation_at_listing for active listings")
    print("=" * 70)

    total = 0
    updated = 0
    for coll_name in sorted(get_collections(db)):
        collection = db[coll_name]
        # Find for_sale properties that have scraped_data.valuation.mid but no domain_valuation_at_listing
        cursor = collection.find({
            "listing_status": "for_sale",
            "scraped_data.valuation.mid": {"$exists": True, "$ne": None},
            "domain_valuation_at_listing": {"$exists": False}
        }, {"scraped_data.valuation": 1})

        batch = list(cursor)
        total += len(batch)
        for doc in batch:
            val = doc.get("scraped_data", {}).get("valuation", {})
            if not val.get("mid"):
                continue
            if not dry_run:
                doc_id = doc["_id"]
                retry_write(lambda: collection.update_one(
                    {"_id": doc_id},
                    {"$set": {
                        "domain_valuation_at_listing": {
                            **val,
                            "captured_at": datetime.utcnow().isoformat(),
                            "source": "backfill_from_scraped_data"
                        }
                    }}
                ))
            updated += 1

        if batch:
            print(f"  {coll_name:30s}: {len(batch)} snapshots {'(dry-run)' if dry_run else 'written'}")

    print(f"\nTotal for_sale snapshotted: {updated}/{total}")
    return updated


def backfill_sold_accuracy(db, dry_run=False):
    """Compute domain_valuation_accuracy for sold properties."""
    print("\n" + "=" * 70)
    print("PHASE 2: Compute Domain valuation accuracy for sold properties")
    print("=" * 70)

    total_sold = 0
    computed = 0
    skipped_no_val = 0
    skipped_no_price = 0
    already_has = 0
    errors_list = []
    accuracy_data = []

    for coll_name in sorted(get_collections(db)):
        collection = db[coll_name]
        cursor = collection.find(
            {"listing_status": "sold"},
            {"sale_price": 1, "listing_price": 1, "scraped_data.valuation": 1,
             "domain_valuation_at_listing": 1, "domain_valuation_accuracy": 1,
             "address": 1}
        )

        coll_computed = 0
        for doc in cursor:
            total_sold += 1

            # Skip if already computed
            if doc.get("domain_valuation_accuracy"):
                already_has += 1
                continue

            # Get best available domain valuation
            domain_val = (doc.get("domain_valuation_at_listing")
                          or doc.get("scraped_data", {}).get("valuation"))
            if not domain_val or not domain_val.get("mid"):
                skipped_no_val += 1
                continue

            # Parse sale price
            sale_price_num = parse_price(doc.get("sale_price"))
            if not sale_price_num:
                skipped_no_price += 1
                continue

            mid = domain_val["mid"]
            low = domain_val.get("low")
            high = domain_val.get("high")

            try:
                error_dollars = sale_price_num - mid
                error_pct = round((error_dollars / mid) * 100, 2)
                within_range = bool(low and high and low <= sale_price_num <= high)
            except (ZeroDivisionError, TypeError):
                continue

            accuracy_record = {
                "domain_mid": mid,
                "domain_low": low,
                "domain_high": high,
                "sale_price": sale_price_num,
                "error_dollars": error_dollars,
                "error_pct": error_pct,
                "within_range": within_range,
                "computed_at": datetime.utcnow().isoformat(),
            }

            update_set = {"domain_valuation_accuracy": accuracy_record}
            # Also snapshot the valuation if not already done
            if not doc.get("domain_valuation_at_listing"):
                update_set["domain_valuation_at_listing"] = {
                    **domain_val,
                    "captured_at": datetime.utcnow().isoformat(),
                    "source": "backfill_from_scraped_data"
                }

            if not dry_run:
                doc_id = doc["_id"]
                retry_write(lambda: collection.update_one({"_id": doc_id}, {"$set": update_set}))

            accuracy_data.append(error_pct)
            computed += 1
            coll_computed += 1

        if coll_computed:
            print(f"  {coll_name:30s}: {coll_computed} accuracy records {'(dry-run)' if dry_run else 'written'}")

    print(f"\nTotal sold: {total_sold}")
    print(f"Already had accuracy: {already_has}")
    print(f"Computed this run: {computed}")
    print(f"Skipped (no valuation): {skipped_no_val}")
    print(f"Skipped (no sale price): {skipped_no_price}")

    if accuracy_data:
        import statistics
        abs_errors = [abs(e) for e in accuracy_data]
        print(f"\n--- Domain Valuation Accuracy Summary ---")
        print(f"Properties analysed: {len(accuracy_data)}")
        print(f"Mean absolute error: {statistics.mean(abs_errors):.1f}%")
        print(f"Median absolute error: {statistics.median(abs_errors):.1f}%")
        print(f"Mean error (bias): {statistics.mean(accuracy_data):+.1f}%")
        within = sum(1 for d in accuracy_data if abs(d) <= 10)
        print(f"Within ±10%: {within}/{len(accuracy_data)} ({within/len(accuracy_data)*100:.0f}%)")
        within_range_count = sum(1 for doc_pct in accuracy_data if doc_pct is not None)
        # Re-check within_range from the raw data
        print(f"Min error: {min(accuracy_data):.1f}%  Max error: {max(accuracy_data):.1f}%")

    return computed


def main():
    parser = argparse.ArgumentParser(description="Backfill Domain valuation accuracy data")
    parser.add_argument("--dry-run", action="store_true", help="Show what would be done without writing")
    args = parser.parse_args()

    client = MongoClient(MONGODB_URI)
    db = client[DATABASE_NAME]

    try:
        snapshots = backfill_listing_snapshots(db, dry_run=args.dry_run)
        computed = backfill_sold_accuracy(db, dry_run=args.dry_run)
        print(f"\n{'DRY RUN — no changes written' if args.dry_run else 'DONE'}")
        print(f"Listing snapshots: {snapshots}, Sold accuracy records: {computed}")
    finally:
        client.close()


if __name__ == "__main__":
    main()
