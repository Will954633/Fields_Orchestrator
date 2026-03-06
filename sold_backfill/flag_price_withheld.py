#!/usr/bin/env python3
"""
Flag Price-Withheld Sold Properties for Manual Review
======================================================
Queries the Gold_Coast database for sold properties with no sale_price
and writes them to system_monitor.price_withheld_review for Will to
manually investigate via agent contacts or auction results.

Usage:
    python3 sold_backfill/flag_price_withheld.py              # Flag all
    python3 sold_backfill/flag_price_withheld.py --suburb robina
    python3 sold_backfill/flag_price_withheld.py --list        # Just print, don't write

Requires:
    source /home/fields/venv/bin/activate
    set -a && source /home/fields/Fields_Orchestrator/.env && set +a
"""

import os
import sys
import re
import argparse
from datetime import datetime
from pymongo import MongoClient

TARGET_SUBURBS = ["robina", "varsity_lakes", "burleigh_waters"]
DATABASE_NAME = "Gold_Coast"
REVIEW_DB = "system_monitor"
REVIEW_COLLECTION = "price_withheld_review"


def main():
    parser = argparse.ArgumentParser(description="Flag price-withheld sold properties for review")
    parser.add_argument("--suburb", type=str, help="Single suburb collection name")
    parser.add_argument("--list", action="store_true", help="List only, don't write to review collection")
    parser.add_argument("--all-suburbs", action="store_true", help="Check all suburb collections")
    args = parser.parse_args()

    conn_str = os.environ.get("COSMOS_CONNECTION_STRING")
    if not conn_str:
        print("ERROR: COSMOS_CONNECTION_STRING not set")
        sys.exit(1)

    client = MongoClient(conn_str)
    db = client[DATABASE_NAME]
    review_col = client[REVIEW_DB][REVIEW_COLLECTION]
    client.admin.command("ping")

    if args.suburb:
        suburbs = [args.suburb.lower().replace(" ", "_")]
    elif args.all_suburbs:
        suburbs = [c for c in db.list_collection_names()
                    if not c.startswith("system.") and c not in (
                        "suburb_median_prices", "suburb_statistics", "change_detection_snapshots")]
    else:
        suburbs = TARGET_SUBURBS

    now = datetime.utcnow().isoformat()
    total_flagged = 0
    all_withheld = []

    for suburb in sorted(suburbs):
        col = db[suburb]
        # Find sold records with no sale_price or sale_price is None/"Price Withheld"
        query = {
            "listing_status": "sold",
            "$or": [
                {"sale_price": {"$exists": False}},
                {"sale_price": None},
                {"sale_price": ""},
                {"sale_price": {"$regex": "withheld", "$options": "i"}},
            ]
        }
        withheld = list(col.find(query, {
            "address": 1, "sold_date": 1, "listing_url": 1,
            "sale_method": 1, "selling_agent": 1, "selling_agency": 1,
            "bedrooms": 1, "bathrooms": 1, "property_type": 1,
            "sold_scrape_source": 1,
        }))

        if withheld:
            print(f"\n  {suburb}: {len(withheld)} price-withheld records")
            for doc in withheld:
                addr = doc.get("address", "N/A")[:55]
                sd = doc.get("sold_date", "N/A")
                method = doc.get("sale_method", "N/A")
                agent = doc.get("selling_agent") or doc.get("agent_name") or "unknown"
                print(f"    {addr:55s} | {sd:10s} | {method} | {agent}")

                all_withheld.append({
                    "suburb": suburb,
                    "address": doc.get("address"),
                    "sold_date": doc.get("sold_date"),
                    "listing_url": doc.get("listing_url"),
                    "sale_method": doc.get("sale_method"),
                    "agent": agent,
                    "bedrooms": doc.get("bedrooms"),
                    "bathrooms": doc.get("bathrooms"),
                    "property_type": doc.get("property_type"),
                    "doc_id": str(doc["_id"]),
                })
            total_flagged += len(withheld)

    print(f"\n  Total price-withheld: {total_flagged}")

    if not args.list and all_withheld:
        # Write to review collection
        review_doc = {
            "_id": f"price_withheld_{datetime.utcnow().strftime('%Y%m%d')}",
            "generated_at": now,
            "total_count": total_flagged,
            "suburbs_checked": suburbs,
            "properties": all_withheld,
            "review_status": "pending",  # Will sets to "reviewed" after checking
            "notes": "",
        }
        try:
            review_col.replace_one(
                {"_id": review_doc["_id"]},
                review_doc,
                upsert=True
            )
            print(f"  Written to {REVIEW_DB}.{REVIEW_COLLECTION} (id: {review_doc['_id']})")
            print(f"  Will can review at: https://fieldsestate.com.au/ops (Repair Queue panel)")
        except Exception as e:
            print(f"  ERROR writing review doc: {e}")

    client.close()


if __name__ == "__main__":
    main()
