#!/usr/bin/env python3
"""
Check for active listings missing GPT photo analysis (step 105)
and queue re-runs via the trigger system.

Run: python3 scripts/check_missing_photo_analysis.py [--fix]
  Without --fix: report only
  With --fix: queue step 105 trigger for affected suburbs
"""
import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from datetime import datetime, timezone
from shared.db import get_gold_coast_db, get_client

TARGET_SUBURBS = ['robina', 'varsity_lakes', 'burleigh_waters', 'mudgeeraba', 'reedy_creek', 'worongary']
ANALYSIS_FIELD = 'ollama_image_analysis'  # Step 105 writes this field


def check_missing():
    db = get_gold_coast_db()
    results = []

    for suburb in TARGET_SUBURBS:
        col = db[suburb]
        total = col.count_documents({'listing_status': 'for_sale'})
        with_analysis = col.count_documents({
            'listing_status': 'for_sale',
            ANALYSIS_FIELD: {'$exists': True, '$ne': None}
        })
        missing = total - with_analysis
        pct = round(with_analysis / total * 100, 1) if total > 0 else 100

        # Get addresses of missing properties
        missing_docs = []
        if missing > 0:
            cursor = col.find(
                {'listing_status': 'for_sale', ANALYSIS_FIELD: {'$exists': False}},
                {'address': 1}
            ).limit(10)
            missing_docs = [d.get('address', '?') for d in cursor]

        results.append({
            'suburb': suburb,
            'total': total,
            'with_analysis': with_analysis,
            'missing': missing,
            'coverage_pct': pct,
            'sample_missing': missing_docs,
        })

    return results


def queue_rerun(suburbs_needing_fix):
    """Queue a step 105 trigger for affected suburbs."""
    client = get_client()
    sm = client['system_monitor']
    triggers = sm['triggers']

    trigger = {
        'type': 'process_rerun',
        'step_id': 105,
        'reason': f'Missing photo analysis on {sum(s["missing"] for s in suburbs_needing_fix)} properties across {len(suburbs_needing_fix)} suburbs',
        'suburbs': [s['suburb'] for s in suburbs_needing_fix],
        'status': 'pending',
        'created_at': datetime.now(timezone.utc),
        'created_by': 'check_missing_photo_analysis',
    }
    result = triggers.insert_one(trigger)
    print(f'\nQueued trigger: {result.inserted_id}')
    return result.inserted_id


def main():
    fix_mode = '--fix' in sys.argv
    results = check_missing()

    print('=' * 60)
    print('Photo Analysis Coverage Report (Step 105)')
    print('=' * 60)

    suburbs_needing_fix = []
    for r in results:
        status = '✅' if r['missing'] == 0 else '⚠️'
        print(f"\n{status} {r['suburb']}: {r['with_analysis']}/{r['total']} ({r['coverage_pct']}%)")
        if r['missing'] > 0:
            print(f"   Missing: {r['missing']} properties")
            for addr in r['sample_missing'][:5]:
                print(f"     - {addr}")
            if r['missing'] > 5:
                print(f"     ... and {r['missing'] - 5} more")
            suburbs_needing_fix.append(r)

    total_missing = sum(r['missing'] for r in results)
    total_active = sum(r['total'] for r in results)
    print(f'\n{"=" * 60}')
    print(f'Total: {total_active - total_missing}/{total_active} properties with photo analysis')
    print(f'Missing: {total_missing}')

    if total_missing > 0 and fix_mode:
        print('\n--fix mode: queuing step 105 rerun...')
        queue_rerun(suburbs_needing_fix)
    elif total_missing > 0:
        print('\nRun with --fix to queue a step 105 rerun for missing properties.')


if __name__ == '__main__':
    main()
