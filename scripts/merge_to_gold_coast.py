#!/usr/bin/env python3
"""
One-off migration: Merge Gold_Coast_Currently_For_Sale and Gold_Coast_Recently_Sold
into Gold_Coast database.

- Pre-loads Gold_Coast addresses into memory for fast matching (avoids 429 throttling)
- For each source document, matches by normalized address and merges fields
- Unmatched docs are inserted as new documents
- Does NOT modify or delete source databases.

Usage:
    source /home/fields/venv/bin/activate
    set -a && source /home/fields/Fields_Orchestrator/.env && set +a
    python3 scripts/merge_to_gold_coast.py --dry-run   # preview
    python3 scripts/merge_to_gold_coast.py              # execute
"""

import os
import re
import sys
import time
from datetime import datetime
from pymongo import MongoClient
from bson import ObjectId


def normalize_address(address: str) -> str:
    """Normalize address for matching (case, commas, unit numbers, spaces)."""
    if not address:
        return ""
    normalized = address.strip()
    # Strip "Sold X Address on DD Mon YYYY - NNNNN" prefix/suffix
    normalized = re.sub(r'^Sold\s+', '', normalized, flags=re.IGNORECASE)
    normalized = re.sub(r'\s+on\s+\d{1,2}\s+\w+\s+\d{4}\s*-?\s*\d*$', '', normalized)
    # Handle "Unit X Y Street" → "X/Y Street"
    unit_match = re.match(r'^Unit\s+(\d+)\s+(\d+)\s+(.+)$', normalized, re.IGNORECASE)
    if unit_match:
        normalized = f"{unit_match.group(1)}/{unit_match.group(2)} {unit_match.group(3)}"
    normalized = normalized.upper()
    normalized = normalized.replace(',', '')
    # Normalize unit numbers: "2 36 BONOGIN" -> "2/36 BONOGIN"
    match = re.match(r'^(\d+)\s+(\d+)\s+', normalized)
    if match:
        normalized = f"{match.group(1)}/{match.group(2)} {normalized[match.end():]}"
    normalized = re.sub(r'\s+', ' ', normalized).strip()
    return normalized


def normalize_no_postcode(addr: str) -> str:
    """Normalize address and strip trailing postcode for fuzzy matching."""
    return re.sub(r'\s+\d{4}$', '', normalize_address(addr))


def build_address_index(gc_collection):
    """Pre-load all addresses from a Gold_Coast collection into a lookup dict.
    Returns {normalized_address: ObjectId, ...} and {normalized_no_postcode: ObjectId, ...}
    """
    exact = {}
    fuzzy = {}
    # Only fetch _id and complete_address to minimize RU cost
    for doc in gc_collection.find({}, {'_id': 1, 'complete_address': 1}):
        addr = doc.get('complete_address', '')
        if addr:
            norm = normalize_address(addr)
            exact[norm] = doc['_id']
            fuzzy[normalize_no_postcode(addr)] = doc['_id']
    return exact, fuzzy


# Fields to skip when merging (Gold_Coast master fields we don't want to overwrite)
MASTER_ONLY_FIELDS = {
    '_id', 'ADDRESS_PID', 'ADDRESS_STANDARD', 'ADDRESS_STATUS', 'DATUM',
    'GEOCODE_TYPE', 'LGA_CODE', 'LOCALITY', 'LOCAL_AUTHORITY',
    'LOT', 'LOTPLAN_STATUS', 'PLAN', 'PROPERTY_NAME',
    'STREET_NAME', 'STREET_NO_1', 'STREET_NO_1_SUFFIX', 'STREET_NO_2',
    'STREET_NO_2_SUFFIX', 'STREET_SUFFIX', 'STREET_TYPE',
    'UNIT_NUMBER', 'UNIT_SUFFIX', 'UNIT_TYPE', 'complete_address',
    'cadastral_accuracy', 'cadastral_enriched_at',
    'is_strata_title', 'lot_size_calc_sqm', 'lot_size_sqm', 'lot_size_sqm_source',
    'parcel_state', 'property_tenure', 'property_tenure_desc',
    'postcode_distance_km', 'postcode_enriched_at',
    'target_market', 'target_market_labeled_at',
    'sales_history', 'last_sold_date', 'last_sale_price',
}


def cosmos_retry(fn, max_retries=3):
    """Retry wrapper for Cosmos DB 429 errors."""
    for attempt in range(max_retries + 1):
        try:
            return fn()
        except Exception as e:
            msg = str(e)
            is_429 = '16500' in msg or 'TooManyRequests' in msg or '429' in msg
            if not is_429 or attempt == max_retries:
                raise
            match = re.search(r'RetryAfterMs=(\d+)', msg)
            wait_ms = int(match.group(1)) + 100 if match else 1000
            time.sleep(wait_ms / 1000)


def main():
    dry_run = '--dry-run' in sys.argv

    conn_str = os.environ.get('COSMOS_CONNECTION_STRING')
    if not conn_str:
        print("ERROR: COSMOS_CONNECTION_STRING not set")
        sys.exit(1)

    client = MongoClient(conn_str)
    gc_db = client['Gold_Coast']
    fs_db = client['Gold_Coast_Currently_For_Sale']
    sold_db = client['Gold_Coast_Recently_Sold']

    skip_collections = {'suburb_median_prices', 'suburb_statistics', 'change_detection_snapshots'}

    print(f"{'[DRY RUN] ' if dry_run else ''}Merging data into Gold_Coast database")
    print(f"Started: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n")

    def process_source_db(source_db, db_label, listing_status):
        """Process all collections from a source database."""
        colls = [c for c in source_db.list_collection_names() if c not in skip_collections]
        merged = 0
        inserted = 0
        failed = 0

        for coll_name in sorted(colls):
            # Load source docs
            source_docs = list(source_db[coll_name].find({}))
            if not source_docs:
                continue

            gc_coll = gc_db[coll_name]
            print(f"\n  {coll_name}: {len(source_docs)} documents")

            # Pre-load Gold_Coast addresses for this suburb (single query)
            print(f"    Loading Gold_Coast.{coll_name} address index...", end=' ')
            exact_idx, fuzzy_idx = cosmos_retry(lambda: build_address_index(gc_coll))
            print(f"{len(exact_idx)} addresses loaded")

            for doc in source_docs:
                address = doc.get('address', 'UNKNOWN')
                norm = normalize_address(address)
                norm_fuzzy = normalize_no_postcode(address)

                # Try exact match, then fuzzy (no postcode)
                matched_id = exact_idx.get(norm) or fuzzy_idx.get(norm_fuzzy)

                # Build fields to set
                set_fields = {'listing_status': listing_status}
                for key, val in doc.items():
                    if key == '_id' or key in MASTER_ONLY_FIELDS:
                        continue
                    set_fields[key] = val

                try:
                    if matched_id:
                        if not dry_run:
                            cosmos_retry(lambda mid=matched_id, sf=set_fields: gc_coll.update_one(
                                {'_id': mid}, {'$set': sf}
                            ))
                            time.sleep(0.3)
                        merged += 1
                        print(f"    ✓ merged: {address}")
                    else:
                        set_fields['complete_address'] = norm
                        if not dry_run:
                            cosmos_retry(lambda sf=set_fields: gc_coll.insert_one(sf))
                            time.sleep(0.3)
                        inserted += 1
                        print(f"    + inserted (no match): {address}")
                except Exception as e:
                    failed += 1
                    print(f"    ✗ FAILED: {address} — {e}")

        print(f"\n  {db_label} totals: {merged} merged, {inserted} inserted, {failed} failed")
        return colls, merged, inserted, failed

    # --- Phase A: Merge Gold_Coast_Currently_For_Sale ---
    print("=" * 60)
    print("Phase A: Gold_Coast_Currently_For_Sale → Gold_Coast")
    print("=" * 60)
    fs_colls, fs_merged, fs_inserted, fs_failed = process_source_db(
        fs_db, "For-sale", "for_sale"
    )

    # --- Phase B: Merge Gold_Coast_Recently_Sold ---
    print("\n" + "=" * 60)
    print("Phase B: Gold_Coast_Recently_Sold → Gold_Coast")
    print("=" * 60)
    sold_colls, sold_merged, sold_inserted, sold_failed = process_source_db(
        sold_db, "Sold", "sold"
    )

    # --- Phase C: Create indexes ---
    if not dry_run:
        print("\n" + "=" * 60)
        print("Phase C: Creating listing_status indexes")
        print("=" * 60)
        indexed = set()
        for coll_name in fs_colls + sold_colls:
            if coll_name not in indexed:
                try:
                    cosmos_retry(lambda cn=coll_name: gc_db[cn].create_index('listing_status'))
                    print(f"  ✓ Index created: {coll_name}.listing_status")
                    indexed.add(coll_name)
                    time.sleep(0.5)
                except Exception as e:
                    print(f"  ✗ Index failed: {coll_name} — {e}")

    # --- Verification ---
    print("\n" + "=" * 60)
    print("Verification")
    print("=" * 60)
    all_colls = sorted(set(fs_colls + sold_colls))
    for coll_name in all_colls:
        try:
            fs_count = cosmos_retry(lambda: fs_db[coll_name].count_documents({})) if coll_name in fs_colls else 0
            time.sleep(0.3)
            sold_count = cosmos_retry(lambda: sold_db[coll_name].count_documents({})) if coll_name in sold_colls else 0
            time.sleep(0.3)
            gc_for_sale = cosmos_retry(lambda: gc_db[coll_name].count_documents({'listing_status': 'for_sale'}))
            time.sleep(0.3)
            gc_sold = cosmos_retry(lambda: gc_db[coll_name].count_documents({'listing_status': 'sold'}))
            time.sleep(0.3)
            ok = "✓" if (gc_for_sale >= fs_count and gc_sold >= sold_count) else "⚠"
            print(f"  {ok} {coll_name}: source({fs_count} fs, {sold_count} sold) → Gold_Coast({gc_for_sale} fs, {gc_sold} sold)")
        except Exception as e:
            print(f"  ⚠ {coll_name}: verification failed — {e}")

    print(f"\n{'[DRY RUN] ' if dry_run else ''}Migration complete.")
    print(f"  For-sale: {fs_merged} merged + {fs_inserted} inserted ({fs_failed} failed)")
    print(f"  Sold: {sold_merged} merged + {sold_inserted} inserted ({sold_failed} failed)")
    print(f"Finished: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    client.close()


if __name__ == '__main__':
    main()
