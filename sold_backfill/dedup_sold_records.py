#!/usr/bin/env python3
"""
Deduplicate Sold Records in Gold_Coast
========================================
Finds sold records that share the same normalized address within a suburb
collection and merges them (keeping the record with the richest data).

Usage:
    python3 sold_backfill/dedup_sold_records.py              # Target suburbs
    python3 sold_backfill/dedup_sold_records.py --all-suburbs
    python3 sold_backfill/dedup_sold_records.py --dry-run     # Preview only

Requires:
    source /home/fields/venv/bin/activate
    set -a && source /home/fields/Fields_Orchestrator/.env && set +a
"""

import os
import re
import sys
import argparse
from datetime import datetime
from collections import defaultdict
from pymongo import MongoClient

TARGET_SUBURBS = ["robina", "varsity_lakes", "burleigh_waters"]
DATABASE_NAME = "Gold_Coast"


def normalize_address(address: str) -> str:
    """Normalize address for dedup matching."""
    if not address:
        return ""
    n = address.upper().replace(",", "").replace(".", "").strip()
    n = re.sub(r'\s+', ' ', n)
    # Remove state + postcode
    n = re.sub(r'\s+QLD\s+\d{4}\s*$', '', n)
    # Normalize unit separator
    n = re.sub(r'^(\d+)\s+(\d+)\s+', r'\1/\2 ', n)
    n = re.sub(r'\bUNIT\s+', '', n)
    # Normalize street types
    for full, abbr in [('STREET', 'ST'), ('ROAD', 'RD'), ('DRIVE', 'DR'),
                        ('AVENUE', 'AVE'), ('COURT', 'CT'), ('PARADE', 'PDE'),
                        ('CRESCENT', 'CRES'), ('CIRCUIT', 'CCT'), ('PLACE', 'PL'),
                        ('CLOSE', 'CL'), ('BOULEVARD', 'BVD'), ('LANE', 'LN'),
                        ('WAY', 'WAY'), ('TERRACE', 'TCE')]:
        n = re.sub(rf'\b{full}\b', abbr, n)
    return n


def doc_richness(doc: dict) -> int:
    """Score a document by how much useful data it has."""
    score = 0
    valuable_fields = [
        'sale_price', 'sold_date', 'sale_method', 'listing_url',
        'bedrooms', 'bathrooms', 'parking', 'land_size', 'property_type',
        'property_images', 'floor_plans', 'valuation_data', 'enriched_data',
        'property_valuation_data', 'floor_plan_analysis', 'agents_description',
        'selling_agent', 'selling_agency', 'first_listed_timestamp',
        'days_on_market', 'sales_history',
    ]
    for field in valuable_fields:
        val = doc.get(field)
        if val is not None and val != "" and val != []:
            score += 1
            # Extra weight for high-value fields
            if field in ('valuation_data', 'property_valuation_data', 'enriched_data',
                         'property_images', 'floor_plans', 'sales_history'):
                score += 2
    return score


def main():
    parser = argparse.ArgumentParser(description="Deduplicate sold records")
    parser.add_argument("--suburb", type=str, help="Single suburb")
    parser.add_argument("--all-suburbs", action="store_true", help="Check all collections")
    parser.add_argument("--dry-run", action="store_true", help="Preview only")
    args = parser.parse_args()

    conn_str = os.environ.get("COSMOS_CONNECTION_STRING")
    if not conn_str:
        print("ERROR: COSMOS_CONNECTION_STRING not set")
        sys.exit(1)

    client = MongoClient(conn_str)
    db = client[DATABASE_NAME]
    client.admin.command("ping")

    if args.suburb:
        suburbs = [args.suburb]
    elif args.all_suburbs:
        suburbs = [c for c in db.list_collection_names()
                    if not c.startswith("system.") and c not in (
                        "suburb_median_prices", "suburb_statistics", "change_detection_snapshots")]
    else:
        suburbs = TARGET_SUBURBS

    total_dupes = 0
    total_removed = 0

    for suburb in sorted(suburbs):
        col = db[suburb]
        sold_docs = list(col.find({"listing_status": "sold"}, {}))
        if not sold_docs:
            continue

        # Group by normalized address
        groups = defaultdict(list)
        for doc in sold_docs:
            addr = doc.get("address", "")
            norm = normalize_address(addr)
            if norm:
                groups[norm].append(doc)

        # Also group by listing_url (different addresses, same listing)
        url_groups = defaultdict(list)
        for doc in sold_docs:
            url = doc.get("listing_url", "")
            if url:
                # Extract listing ID
                m = re.search(r'-(\d{7,10})$', url)
                if m:
                    url_groups[m.group(1)].append(doc)

        # Merge address groups and URL groups
        all_dupe_sets = []
        seen_ids = set()

        for norm_addr, docs in groups.items():
            if len(docs) > 1:
                doc_ids = frozenset(str(d["_id"]) for d in docs)
                if doc_ids not in seen_ids:
                    seen_ids.add(doc_ids)
                    all_dupe_sets.append(docs)

        for lid, docs in url_groups.items():
            if len(docs) > 1:
                doc_ids = frozenset(str(d["_id"]) for d in docs)
                if doc_ids not in seen_ids:
                    seen_ids.add(doc_ids)
                    all_dupe_sets.append(docs)

        if all_dupe_sets:
            print(f"\n=== {suburb}: {len(all_dupe_sets)} duplicate groups ===")

        suburb_removed = 0
        for dupe_group in all_dupe_sets:
            # Score each doc
            scored = [(doc_richness(d), d) for d in dupe_group]
            scored.sort(key=lambda x: x[0], reverse=True)
            keeper = scored[0][1]
            to_remove = [d for _, d in scored[1:]]

            keeper_addr = keeper.get("address", "N/A")[:50]
            print(f"  DUPE: {keeper_addr} ({len(dupe_group)} copies)")
            print(f"    KEEP: _id={keeper['_id']} score={scored[0][0]}")
            for _, doc in scored[1:]:
                print(f"    DROP: _id={doc['_id']} score={doc_richness(doc)} addr={doc.get('address','')[:40]}")

            if not args.dry_run:
                # Merge useful fields from duplicates into keeper
                merged_fields = {}
                for _, dup in scored[1:]:
                    for field in ['sale_price', 'sold_date', 'sale_method', 'listing_url',
                                  'selling_agent', 'selling_agency', 'first_listed_timestamp',
                                  'days_on_market', 'bedrooms', 'bathrooms', 'parking',
                                  'property_type', 'land_size']:
                        if not keeper.get(field) and dup.get(field):
                            merged_fields[field] = dup[field]

                if merged_fields:
                    col.update_one({"_id": keeper["_id"]}, {"$set": merged_fields})
                    print(f"    MERGED fields: {list(merged_fields.keys())}")

                # Delete duplicates
                for doc in to_remove:
                    col.delete_one({"_id": doc["_id"]})
                    suburb_removed += 1

            total_dupes += len(dupe_group) - 1

        if suburb_removed:
            print(f"  Removed {suburb_removed} duplicate records from {suburb}")
        total_removed += suburb_removed

    print(f"\n{'='*50}")
    print(f"  Total duplicate groups: {total_dupes}")
    print(f"  Total records removed: {total_removed}")
    if args.dry_run:
        print(f"  (DRY RUN — no changes made)")
    print(f"{'='*50}")

    client.close()


if __name__ == "__main__":
    main()
