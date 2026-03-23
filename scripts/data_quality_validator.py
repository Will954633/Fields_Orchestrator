#!/usr/bin/env python3
"""
Data Quality Validator — Fields Estate Pipeline
================================================

Scans property documents for data quality issues before valuations are published.
Records errors in system_monitor.data_quality_errors and optionally auto-corrects
known-bad patterns.

Checks performed:
  1. land_size_sqm vs lot_size_sqm divergence (scraper grabbed room dimension)
  2. Houses with implausibly small land size (<50 sqm)
  3. Missing critical fields for sold/for_sale properties
  4. Bedrooms/bathrooms sanity (e.g., 0 beds for a house)

Usage:
    python3 scripts/data_quality_validator.py                # scan + report
    python3 scripts/data_quality_validator.py --fix          # scan + auto-correct + report
    python3 scripts/data_quality_validator.py --suburbs robina,varsity_lakes
"""

import argparse
import os
import sys
import time
from datetime import datetime, timezone

from pymongo import MongoClient
from pymongo.errors import OperationFailure


def cosmos_retry(func, *args, retries=5, **kwargs):
    """Retry on Cosmos DB 429 (TooManyRequests)."""
    for attempt in range(retries):
        try:
            return func(*args, **kwargs)
        except OperationFailure as e:
            if '16500' in str(e) and attempt < retries - 1:
                wait = min(2 * (attempt + 1), 15)
                time.sleep(wait)
            else:
                raise


def safe_find(coll, query, proj, batch_size=10):
    """Find with Cosmos retry. Uses _id cursor to resume without costly skip()."""
    import re as _re
    from bson import ObjectId
    results = []
    last_id = None
    max_retries = 10
    for attempt in range(max_retries):
        try:
            # Resume from last seen _id to avoid expensive skip() on Cosmos
            q = dict(query)
            if last_id is not None:
                q['_id'] = {'$gt': last_id}
            cursor = coll.find(q, proj).sort('_id', 1).batch_size(batch_size)
            for doc in cursor:
                results.append(doc)
                last_id = doc['_id']
                # Brief pause every batch_size docs to spread RU load
                if len(results) % batch_size == 0:
                    time.sleep(0.3)
            return results
        except OperationFailure as e:
            if '16500' in str(e) and attempt < max_retries - 1:
                retry_ms = 5000
                m = _re.search(r'RetryAfterMs=(\d+)', str(e))
                if m:
                    retry_ms = int(m.group(1))
                wait = max(retry_ms / 1000.0, 3 * (attempt + 1))
                print(f"    Cosmos 429 after {len(results)} docs, waiting {wait:.1f}s (attempt {attempt+1}/{max_retries})")
                time.sleep(wait)
            else:
                raise
    return results


# ── Validation rules ──────────────────────────────────────────────────

MIN_LAND_SIZE_HOUSE = 50       # sqm — no house sits on 50 sqm
MIN_LAND_SIZE_TOWNHOUSE = 30   # sqm
DIVERGENCE_THRESHOLD = 0.30    # 30% difference between scraped and cadastral


def check_land_size_divergence(doc):
    """Check if scraped land_size_sqm diverges from cadastral lot_size_sqm."""
    land = doc.get('land_size_sqm')
    lot = doc.get('lot_size_sqm')

    if not land or not lot or lot <= 0:
        return None

    pct = abs(land - lot) / lot
    if pct > DIVERGENCE_THRESHOLD:
        return {
            'rule': 'land_lot_divergence',
            'severity': 'high' if pct > 0.8 else 'medium',
            'message': f'Scraped land_size_sqm ({land}) diverges {pct*100:.0f}% from cadastral lot_size_sqm ({lot:.0f}). Likely grabbed a room dimension.',
            'field': 'land_size_sqm',
            'bad_value': land,
            'correct_value': round(lot),
        }
    return None


def check_implausible_land_size(doc):
    """Check for houses/townhouses with impossibly small land."""
    land = doc.get('land_size_sqm')
    ptype = (doc.get('property_type') or '').lower()

    if not land or land <= 0:
        return None

    if ptype in ('house',) and land < MIN_LAND_SIZE_HOUSE:
        return {
            'rule': 'implausible_land_size',
            'severity': 'high',
            'message': f'{ptype.title()} has land_size_sqm={land}, which is implausibly small.',
            'field': 'land_size_sqm',
            'bad_value': land,
            'correct_value': round(doc['lot_size_sqm']) if doc.get('lot_size_sqm') else None,
        }
    if ptype in ('townhouse', 'villa', 'duplex') and land < MIN_LAND_SIZE_TOWNHOUSE:
        return {
            'rule': 'implausible_land_size',
            'severity': 'medium',
            'message': f'{ptype.title()} has land_size_sqm={land}, which is implausibly small.',
            'field': 'land_size_sqm',
            'bad_value': land,
            'correct_value': round(doc['lot_size_sqm']) if doc.get('lot_size_sqm') else None,
        }
    return None


def check_missing_critical_fields(doc):
    """Check that listed/sold properties have minimum required data."""
    status = doc.get('listing_status')
    if status not in ('for_sale', 'sold'):
        return None

    issues = []
    ptype = (doc.get('property_type') or '').lower()

    if ptype in ('house', 'townhouse', 'villa') and not doc.get('bedrooms'):
        issues.append('bedrooms')
    if ptype in ('house', 'townhouse', 'villa') and not doc.get('bathrooms'):
        issues.append('bathrooms')

    if issues:
        return {
            'rule': 'missing_critical_fields',
            'severity': 'low',
            'message': f'Missing fields for {status} {ptype}: {", ".join(issues)}',
            'field': ','.join(issues),
            'bad_value': None,
            'correct_value': None,
        }
    return None


ALL_CHECKS = [
    check_land_size_divergence,
    check_implausible_land_size,
    check_missing_critical_fields,
]


# ── Main logic ────────────────────────────────────────────────────────

def run_validator(db, monitor_db, suburbs, auto_fix=False):
    """Run all checks across specified suburbs. Return list of errors."""
    skip_collections = {
        'suburb_median_prices', 'suburb_statistics',
        'change_detection_snapshots', 'data_quality_errors',
    }

    if suburbs:
        collections = [s for s in suburbs if s not in skip_collections]
    else:
        all_colls = cosmos_retry(db.list_collection_names)
        collections = [c for c in sorted(all_colls) if c not in skip_collections]

    all_errors = []
    fixed_count = 0

    for coll_name in collections:
        print(f"  Scanning {coll_name}...")
        time.sleep(5)  # 5s cooldown between suburbs — Cosmos Serverless ~5000 RU/s burst

        coll = db[coll_name]
        proj = {
            'complete_address': 1, 'land_size_sqm': 1, 'lot_size_sqm': 1,
            'property_type': 1, 'listing_status': 1, 'bedrooms': 1,
            'bathrooms': 1, 'land_size_sqm_corrected': 1,
        }

        # Only check properties with listing_status or land_size data
        docs = safe_find(coll, {
            '$or': [
                {'listing_status': {'$in': ['for_sale', 'sold']}},
                {'land_size_sqm': {'$exists': True, '$gt': 0}},
            ]
        }, proj)

        for doc in docs:
            # Skip already-corrected records
            if doc.get('land_size_sqm_corrected'):
                continue

            for check_fn in ALL_CHECKS:
                issue = check_fn(doc)
                if issue:
                    error_doc = {
                        'property_id': str(doc['_id']),
                        'collection': coll_name,
                        'address': doc.get('complete_address', 'unknown'),
                        'listing_status': doc.get('listing_status'),
                        'property_type': doc.get('property_type'),
                        'detected_at': datetime.now(timezone.utc).isoformat(),
                        **issue,
                    }
                    all_errors.append(error_doc)

                    # Auto-fix land size issues if we have a correction value
                    if auto_fix and issue.get('correct_value') and issue['field'] == 'land_size_sqm':
                        for attempt in range(3):
                            try:
                                coll.update_one(
                                    {'_id': doc['_id']},
                                    {'$set': {
                                        'land_size_sqm': issue['correct_value'],
                                        'land_size_sqm_corrected': True,
                                        'land_size_sqm_original': issue['bad_value'],
                                        'land_size_sqm_correction_reason': issue['message'],
                                    }}
                                )
                                error_doc['auto_fixed'] = True
                                fixed_count += 1
                                break
                            except OperationFailure:
                                time.sleep(3 * (attempt + 1))

    # Write errors to system_monitor
    if all_errors:
        dq_coll = monitor_db['data_quality_errors']
        # Clear old errors for these collections before inserting fresh
        checked_colls = list(set(e['collection'] for e in all_errors))
        for attempt in range(3):
            try:
                # Insert as a batch report
                report = {
                    'report_date': datetime.now(timezone.utc).isoformat(),
                    'suburbs_checked': collections,
                    'total_errors': len(all_errors),
                    'auto_fixed': fixed_count,
                    'errors': all_errors,
                    'created_at': datetime.now(timezone.utc),
                }
                dq_coll.insert_one(report)
                break
            except OperationFailure:
                time.sleep(5 * (attempt + 1))

    return all_errors, fixed_count


def main():
    parser = argparse.ArgumentParser(description='Data Quality Validator')
    parser.add_argument('--fix', action='store_true', help='Auto-correct known-bad values')
    parser.add_argument('--suburbs', type=str, help='Comma-separated suburb list (default: target suburbs)')
    args = parser.parse_args()

    uri = os.environ.get('COSMOS_CONNECTION_STRING')
    if not uri:
        print("ERROR: COSMOS_CONNECTION_STRING not set", file=sys.stderr)
        sys.exit(1)

    client = MongoClient(uri)
    db = client['Gold_Coast']
    monitor_db = client['system_monitor']

    default_suburbs = [
        'robina', 'burleigh_waters', 'varsity_lakes',
        'burleigh_heads', 'mudgeeraba', 'reedy_creek',
        'merrimac', 'worongary', 'carrara',
    ]
    suburbs = args.suburbs.split(',') if args.suburbs else default_suburbs

    print(f"Data Quality Validator — scanning {len(suburbs)} suburbs (fix={'ON' if args.fix else 'OFF'})")
    errors, fixed = run_validator(db, monitor_db, suburbs, auto_fix=args.fix)

    print(f"\n{'='*60}")
    print(f"Results: {len(errors)} issues found, {fixed} auto-fixed")
    if errors:
        by_rule = {}
        for e in errors:
            by_rule.setdefault(e['rule'], []).append(e)
        for rule, errs in sorted(by_rule.items()):
            print(f"\n  [{rule}] — {len(errs)} issues")
            for e in errs[:5]:
                fixed_tag = ' [FIXED]' if e.get('auto_fixed') else ''
                print(f"    {e['address'][:50]} — {e['message'][:60]}{fixed_tag}")
            if len(errs) > 5:
                print(f"    ... and {len(errs) - 5} more")
    else:
        print("  All clean!")

    return 1 if errors and not all(e.get('auto_fixed') for e in errors) else 0


if __name__ == '__main__':
    sys.exit(main())
