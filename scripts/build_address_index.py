#!/usr/bin/env python3
"""
Build Address Search Index for "Analyse Your Home" feature.

Creates a single `address_search_index` collection in Gold_Coast DB with
lightweight address records from all suburb collections. This enables
fast autocomplete search (~100-200ms) instead of scanning 80+ collections.

Usage:
    python3 scripts/build_address_index.py
    python3 scripts/build_address_index.py --drop  # rebuild from scratch
"""
import os
import sys
import time
import argparse
from datetime import datetime
from pymongo import MongoClient
from pymongo.errors import OperationFailure, BulkWriteError

INDEX_COLLECTION = 'address_search_index'

TARGET_MARKET_SUBURBS = [
    'robina', 'mudgeeraba', 'varsity_lakes', 'carrara',
    'reedy_creek', 'burleigh_waters', 'merrimac', 'worongary',
]

SKIP_COLLECTIONS = {
    INDEX_COLLECTION, 'system.profile', 'suburb_median_prices',
    'suburb_statistics', 'change_detection_snapshots',
    'precomputed_indexed_prices', 'precomputed_motion_data',
    'precomputed_property_type_race',
}


def suburb_display_name(coll_name):
    return ' '.join(w.capitalize() for w in coll_name.split('_'))


def format_street_address(doc):
    parts = []
    if doc.get('STREET_NO_1'):
        parts.append(str(doc['STREET_NO_1']))
    if doc.get('STREET_NAME'):
        parts.append(doc['STREET_NAME'].title())
    if doc.get('STREET_TYPE'):
        parts.append(doc['STREET_TYPE'].title())
    return ' '.join(parts)


def cosmos_retry(fn, *args, max_retries=5, **kwargs):
    for attempt in range(max_retries):
        try:
            return fn(*args, **kwargs)
        except BulkWriteError:
            # Duplicate key errors are expected in resume mode — ignore
            return
        except OperationFailure as e:
            if '16500' in str(e) or '429' in str(e):
                wait = min(2 ** attempt * 2, 30)
                print(f"  429 rate limit, waiting {wait}s (attempt {attempt+1})...", flush=True)
                time.sleep(wait)
            else:
                raise
    raise Exception(f"Failed after {max_retries} retries")


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--drop', action='store_true', help='Drop and rebuild index')
    args = parser.parse_args()

    uri = os.environ.get('COSMOS_CONNECTION_STRING')
    if not uri:
        print("COSMOS_CONNECTION_STRING not set")
        sys.exit(1)

    client = MongoClient(uri, retryWrites=False, tls=True, tlsAllowInvalidCertificates=True)
    db = client['Gold_Coast']
    print(f"Build Address Index -- {datetime.now().strftime('%Y-%m-%d %H:%M')}", flush=True)

    idx_coll = db[INDEX_COLLECTION]

    if args.drop:
        print(f"Dropping {INDEX_COLLECTION}...", flush=True)
        db.drop_collection(INDEX_COLLECTION)
        time.sleep(2)

    # Check which suburbs already indexed
    already_indexed = set()
    try:
        pipeline = [{'$group': {'_id': '$suburb_key'}}]
        for doc in idx_coll.aggregate(pipeline):
            already_indexed.add(doc['_id'])
        if already_indexed:
            print(f"Already indexed: {len(already_indexed)} suburbs", flush=True)
    except Exception:
        pass

    # Get all suburb collections
    all_colls = db.list_collection_names()
    suburb_colls = [c for c in all_colls if c not in SKIP_COLLECTIONS and not c.startswith('system.')]

    # Target market first
    target = [c for c in suburb_colls if c in TARGET_MARKET_SUBURBS]
    others = sorted([c for c in suburb_colls if c not in TARGET_MARKET_SUBURBS])
    ordered = target + others

    print(f"Found {len(ordered)} suburb collections", flush=True)

    total_inserted = 0

    for suburb_name in ordered:
        if suburb_name in already_indexed:
            print(f"  Skip {suburb_display_name(suburb_name)} (already indexed)", flush=True)
            continue

        coll = db[suburb_name]
        is_target = suburb_name in TARGET_MARKET_SUBURBS

        projection = {
            '_id': 1, 'complete_address': 1,
            'STREET_NO_1': 1, 'STREET_NAME': 1, 'STREET_TYPE': 1,
            'LOCALITY': 1, 'POSTCODE': 1, 'PROPERTY_TYPE': 1,
            'images': 1, 'lot_size_sqm': 1,
            'scraped_data.bedrooms': 1, 'scraped_data.bathrooms': 1,
            'scraped_data.car_spaces': 1, 'scraped_data.features': 1,
            'bedrooms': 1, 'bathrooms': 1,
        }

        cursor = coll.find({}, projection).batch_size(100)
        batch = []
        count = 0
        BATCH_SIZE = 50

        for doc in cursor:
            addr = doc.get('complete_address')
            if not addr:
                continue

            scraped = doc.get('scraped_data', {})
            images = doc.get('images', [])
            if not isinstance(images, list):
                images = []

            bedrooms = doc.get('bedrooms') or scraped.get('bedrooms')
            bathrooms = doc.get('bathrooms') or scraped.get('bathrooms')
            car_spaces = scraped.get('car_spaces')

            index_doc = {
                'address': addr.upper(),
                'address_display': format_street_address(doc),
                'street_no': str(doc.get('STREET_NO_1', '')),
                'street_name': (doc.get('STREET_NAME') or '').upper(),
                'street_type': (doc.get('STREET_TYPE') or '').upper(),
                'source_id': doc['_id'],
                'suburb_key': suburb_name,
                'suburb': suburb_display_name(suburb_name),
                'postcode': doc.get('POSTCODE', ''),
                'property_type': doc.get('PROPERTY_TYPE', 'Residential'),
                'lot_size_sqm': doc.get('lot_size_sqm'),
                'has_images': len(images) > 0,
                'image_count': len(images),
                'bedrooms': bedrooms,
                'bathrooms': bathrooms,
                'car_spaces': car_spaces,
                'is_target_market': is_target,
            }

            batch.append(index_doc)
            count += 1

            if len(batch) >= BATCH_SIZE:
                cosmos_retry(idx_coll.insert_many, batch, ordered=False)
                total_inserted += len(batch)
                batch = []
                time.sleep(0.3)

        if batch:
            cosmos_retry(idx_coll.insert_many, batch, ordered=False)
            total_inserted += len(batch)

        print(f"  {suburb_display_name(suburb_name)}: {count} indexed", flush=True)
        time.sleep(1)

    # Create indexes
    print("\nCreating indexes...", flush=True)
    try:
        cosmos_retry(idx_coll.create_index,
            [('street_name', 1), ('street_no', 1), ('suburb_key', 1)],
            name='street_search_idx')
        print("  Created street_search_idx", flush=True)
    except Exception as e:
        print(f"  street_search_idx: {e}", flush=True)

    try:
        cosmos_retry(idx_coll.create_index, [('suburb_key', 1)], name='suburb_idx')
        print("  Created suburb_idx", flush=True)
    except Exception as e:
        print(f"  suburb_idx: {e}", flush=True)

    try:
        cosmos_retry(idx_coll.create_index, [('address', 1)], name='address_idx')
        print("  Created address_idx", flush=True)
    except Exception as e:
        print(f"  address_idx: {e}", flush=True)

    try:
        cosmos_retry(idx_coll.create_index,
            [('is_target_market', -1), ('suburb_key', 1)],
            name='target_market_idx')
        print("  Created target_market_idx", flush=True)
    except Exception as e:
        print(f"  target_market_idx: {e}", flush=True)

    final_count = idx_coll.estimated_document_count()
    print(f"\nDone! {total_inserted} new records inserted. Total: {final_count}", flush=True)
    client.close()


if __name__ == '__main__':
    main()
