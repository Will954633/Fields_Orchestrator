#!/usr/bin/env python3
"""
Waterfront backfill + editorial suppression (one-off + re-runnable).

WHY (2026-07-26): Waterfront is out of scope for Fields right now — see
shared/waterfront.py for the full rationale (needs a dedicated arm; valuation model
not ready for water-fronting cohorts; surfaced by 46 Mornington Terrace being valued
off dry comps). This script:

  1. Persists a canonical `is_waterfront: true` boolean (+ `waterfront_meta`) on every
     for-sale / sold / under-contract / withdrawn listing the canonical detector flags.
     That single flag drives: the website noindex + sitemap-drop gate, the valuation
     comp filter (keeps waterfront homes out of dry cohorts), and the valuation-hide.
  2. Suppresses any editorial on those homes: ai_analysis.status → 'suppressed_waterfront'
     (original status preserved in ai_analysis.pre_suppression_status). Reversible — when
     we build the waterfront arm, flip these back and delete the flag.

Dry-run by default. Pass --commit to write. Idempotent: re-running only touches docs
that still need a change.

    python3 scripts/waterfront_backfill_and_suppress.py            # dry-run
    python3 scripts/waterfront_backfill_and_suppress.py --commit
"""
import sys
import argparse
from datetime import datetime, timezone

sys.path.insert(0, '/home/fields/Fields_Orchestrator')
from shared.db import get_client
from shared.waterfront import detect_waterfront

try:
    from src.mongo_client_factory import cosmos_retry
except Exception:
    def cosmos_retry(fn, *a, **k):  # fallback: no retry wrapper available
        return fn(*a, **k)

SUPPRESS_REASON = 'waterfront_out_of_scope_2026-07-26'
DETECTOR_VERSION = 'waterfront.py@2026-07-26'
SKIP_COLLECTIONS = {
    'suburb_median_prices', 'suburb_statistics', 'change_detection_snapshots',
    'address_search_index', 'precomputed_market_charts',
}
# Listings that have (or could have) a live property page or act as a comp.
PAGE_STATUSES = {'for_sale', 'sold', 'under_contract', 'withdrawn'}
# Editorial states that must not remain publishable on a waterfront home.
SUPPRESSABLE = {'published', 'draft', 'needs_review', 'failed_factcheck'}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--commit', action='store_true', help='Apply writes (default: dry-run)')
    ap.add_argument('--include-sold', action='store_true',
                    help='Also flag+de-index sold waterfront pages that have NO editorial '
                         '(~400 GC-wide, currently indexed). Default OFF: those stay indexed, '
                         'matching "remove currently PUBLISHED waterfront homes". Sold pages that '
                         'DO carry editorial are always in scope regardless of this flag.')
    args = ap.parse_args()
    now = datetime.now(timezone.utc).isoformat()

    client = get_client()
    db = client['Gold_Coast']

    flagged, suppressed, borderline_rows = 0, 0, []
    already_flagged, already_suppressed = 0, 0

    for cn in db.list_collection_names():
        if cn.startswith('system.') or cn in SKIP_COLLECTIONS:
            continue
        coll = db[cn]
        # Only docs that are real listings (have a page) OR already carry editorial.
        query = {'$or': [
            {'listing_status': {'$in': list(PAGE_STATUSES)}},
            {'ai_analysis': {'$exists': True}},
        ]}
        for d in coll.find(query):
            res = detect_waterfront(d)
            if not res['is_waterfront']:
                continue

            ai0 = d.get('ai_analysis') or {}
            has_editorial = ai0.get('status') is not None
            # Sold pages without editorial already rank + sit in the sitemap. Flagging
            # them de-indexes them — a big SEO action beyond "remove published waterfront
            # homes" — so skip unless explicitly opted in. Sold pages WITH editorial are
            # part of the removal set and always processed.
            if d.get('listing_status') == 'sold' and not has_editorial and not args.include_sold:
                continue

            set_fields = {}
            # (1) Persist the flag + audit meta.
            if not d.get('is_waterfront'):
                set_fields['is_waterfront'] = True
                set_fields['waterfront_meta'] = {
                    'reason': res['reason'],
                    'borderline': res['borderline'],
                    'signals': res['signals'],
                    'detected_at': now,
                    'detector': DETECTOR_VERSION,
                    'policy': SUPPRESS_REASON,
                }
            else:
                already_flagged += 1

            # (2) Suppress editorial if present + publishable.
            ai = d.get('ai_analysis') or {}
            ai_status = ai.get('status')
            if ai_status in SUPPRESSABLE:
                set_fields['ai_analysis.status'] = 'suppressed_waterfront'
                set_fields['ai_analysis.pre_suppression_status'] = ai_status
                set_fields['ai_analysis.suppressed_at'] = now
                set_fields['ai_analysis.suppressed_reason'] = SUPPRESS_REASON
                suppressed += 1
            elif ai_status == 'suppressed_waterfront':
                already_suppressed += 1

            if 'is_waterfront' in set_fields:
                flagged += 1
            if res['borderline']:
                borderline_rows.append((cn, d.get('address'), ai_status))

            if set_fields:
                addr = d.get('address', '?')
                tag = []
                if 'is_waterfront' in set_fields:
                    tag.append(f"flag({res['reason']}{'/BORDERLINE' if res['borderline'] else ''})")
                if 'ai_analysis.status' in set_fields:
                    tag.append(f"suppress({ai_status}→suppressed_waterfront)")
                print(f"  [{cn}] {addr}  {' '.join(tag)}")
                if args.commit:
                    cosmos_retry(
                        lambda c=coll, i=d['_id'], sf=set_fields: c.update_one({'_id': i}, {'$set': sf})
                    )

    print("\n" + "=" * 60)
    print(f"{'APPLIED' if args.commit else 'DRY-RUN'} — mode={'commit' if args.commit else 'preview'}")
    print(f"  newly flagged is_waterfront : {flagged}")
    print(f"  editorial suppressed        : {suppressed}")
    print(f"  already flagged (unchanged) : {already_flagged}")
    print(f"  already suppressed          : {already_suppressed}")
    if borderline_rows:
        print(f"  ⚠ borderline (eyeball these — water boundary but 'adjacent'): {len(borderline_rows)}")
        for cn, addr, st in borderline_rows:
            print(f"      [{cn}] {addr}  (ai={st})")
    if not args.commit:
        print("\n  Re-run with --commit to apply.")


if __name__ == '__main__':
    main()
