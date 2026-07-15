#!/usr/bin/env python3
"""Recompute days_on_domain from first_listed_timestamp for all active listings.

The curl_cffi scraper froze days_on_domain on re-scrape (it was in skip_fields to
protect the original listing date), so ~85% of active listings had a stale value —
many stuck near 0 while actually listed for months. The scraper is fixed to
recompute it going forward; this backfills existing docs so the site is correct
immediately rather than waiting for each suburb's next scrape.

Usage:
  python3 scripts/backfill_days_on_domain.py            # dry-run (report only)
  python3 scripts/backfill_days_on_domain.py --apply    # write changes
"""
import sys
from datetime import datetime

sys.path.insert(0, '/home/fields/Fields_Orchestrator')
from src.mongo_client_factory import get_mongo_client, cosmos_retry

APPLY = '--apply' in sys.argv
NOW = datetime.now()


def parse_listed(ts):
    if not ts:
        return None
    try:
        listed = datetime.fromisoformat(str(ts).replace('Z', '+00:00').split('.')[0])
        if listed.tzinfo is not None:
            listed = listed.replace(tzinfo=None)
        return listed
    except Exception:
        return None


def main():
    client = get_mongo_client()
    db = client['Gold_Coast']
    collections = sorted(db.list_collection_names())

    total_active = 0
    have_ts = 0
    changed = 0
    examples = []

    for coll_name in collections:
        coll = db[coll_name]
        cursor = coll.find(
            {'listing_status': 'for_sale'},
            {'address': 1, 'first_listed_timestamp': 1, 'days_on_domain': 1},
        )
        for doc in cursor:
            total_active += 1
            listed = parse_listed(doc.get('first_listed_timestamp'))
            if listed is None:
                continue
            have_ts += 1
            correct = max((NOW - listed).days, 0)
            current = doc.get('days_on_domain')
            if current == correct:
                continue
            changed += 1
            if len(examples) < 20:
                examples.append((coll_name, (doc.get('address') or '')[:40], current, correct))
            if APPLY:
                cosmos_retry(
                    lambda cid=doc['_id'], val=correct: coll.update_one(
                        {'_id': cid}, {'$set': {'days_on_domain': val}}
                    )
                )

    print(f"Active for_sale listings scanned : {total_active}")
    print(f"  with first_listed_timestamp    : {have_ts}")
    print(f"  needing days_on_domain update  : {changed}")
    print(f"  without a listing timestamp    : {total_active - have_ts} (left unchanged)")
    print()
    print("Sample corrections (stored -> correct):")
    for c, a, cur, cor in examples:
        print(f"  {c:18} {a:42} {str(cur):>6} -> {cor:>4}")
    print()
    print("APPLIED." if APPLY else "DRY-RUN — re-run with --apply to write.")


if __name__ == '__main__':
    main()
