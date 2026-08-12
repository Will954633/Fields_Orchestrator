#!/usr/bin/env python3
"""
Backfill WebP renditions for photos of live listings.

Implements step 2/5 of `15_On_Market/03_Audit/IMAGE_DERIVATIVES_SPEC.md`. The blob
store holds one rendition per photo, so listing pages ship ~3,000px originals into an
800px slot — ~10 MB for a 14-photo gallery where 1.8 MB would do. This walks the
`for_sale` listings of the target suburbs and writes 480/960/1600 WebP beside each
original (see `shared/image_derivatives.py` for the naming and the never-upscale rule).

Idempotent: a photo whose renditions already exist is skipped without re-encoding.
Originals are never modified and no document is written — the derivative URL is
derivable from the original by string substitution, so there is nothing to store.

USAGE:
  python3 scripts/backfill_image_derivatives.py --dry-run
  python3 scripts/backfill_image_derivatives.py --suburbs robina --limit 50
  python3 scripts/backfill_image_derivatives.py            # all target suburbs
"""
import os
import sys
import argparse
from urllib.parse import urlparse
from concurrent.futures import ThreadPoolExecutor, as_completed

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__))))

from shared.env import load_env               # type: ignore
from shared.db import get_gold_coast_db       # type: ignore
from shared import blob_storage               # type: ignore
from shared import image_derivatives as deriv # type: ignore
from job_status import job_run                # type: ignore

CONTAINER = 'property-images'
TARGET_SUBURBS = ['robina', 'burleigh_waters', 'varsity_lakes']
LIVE_BLOB_HOST = 'blobs.fieldsestate.com.au'


def blob_name_from_url(url):
    """`https://blobs…/property-images/<name>` -> `<name>`; None if not our blob."""
    if not isinstance(url, str) or LIVE_BLOB_HOST not in url:
        return None
    path = urlparse(url).path.lstrip('/')
    prefix = CONTAINER + '/'
    return path[len(prefix):] if path.startswith(prefix) else None


def collect(db, suburbs, limit):
    """Blob names of every mirrored photo on live listings, capped at `limit`."""
    names, listings = [], 0
    for suburb in suburbs:
        for doc in db[suburb].find({'listing_status': 'for_sale'},
                                   {'property_images': 1}):
            got = [n for n in (blob_name_from_url(u)
                               for u in (doc.get('property_images') or [])) if n]
            if not got:
                continue
            listings += 1
            names.extend(got)
            if limit and len(names) >= limit:
                return names[:limit], listings
    return names, listings


def _one(name):
    """(status, count) for a single photo. Runs on a worker thread."""
    before = deriv.existing_derivatives(CONTAINER, name)
    got = deriv.make_derivatives_from_disk(CONTAINER, name)
    if got is None:
        return ('missing', 0)
    new = set(got) - set(before)
    if new:
        return ('written', len(new))
    # Either the renditions already existed, or the source is narrower than every
    # target and correctly produced none. Both are "no work needed".
    return ('skipped', 0)


def run(suburbs, limit, dry_run, workers=4, beat=None):
    db = get_gold_coast_db()
    names, listings = collect(db, suburbs, limit)
    seen = len(names)
    written = skipped = missing = 0

    if dry_run:
        for name in names:
            have = deriv.existing_derivatives(CONTAINER, name)
            todo = [w for w in deriv.WIDTHS if w not in have]
            print(f"  [DRY] {name} have={sorted(have)} todo={todo}", flush=True)
    else:
        # Pillow releases the GIL across resize and encode, so threads genuinely
        # parallelise here. Kept modest: this shares a 4-vCPU box with the pipeline.
        done = 0
        with ThreadPoolExecutor(max_workers=workers) as pool:
            for fut in as_completed(pool.submit(_one, n) for n in names):
                try:
                    status, n = fut.result()
                except Exception as exc:
                    print(f"    ✗ worker failed: {exc}", flush=True)
                    missing += 1
                    continue
                if status == 'written':
                    written += n
                elif status == 'skipped':
                    skipped += 1
                else:
                    missing += 1
                done += 1
                if done % 250 == 0:
                    print(f"  … {done}/{seen} photos, {written} written", flush=True)

    if beat is not None:
        beat.metrics = {
            'listings': listings, 'photos_seen': seen, 'derivatives_written': written,
            'skipped_existing': skipped, 'originals_missing': missing,
        }
        beat.detail = (f"{listings} listings, {seen} photos, {written} written, "
                       f"{skipped} skipped, {missing} missing")
        # Rule 7b: an empty queue is success; encoding every photo and writing nothing
        # is not. Only assert when there WAS work — seen==0 means no live listings had
        # mirrored photos, which is a different (and also suspicious) condition.
        if seen == 0:
            raise RuntimeError(
                "0 photos seen across target suburbs — expected live listings with "
                "mirrored blobs; upstream mirroring is broken, not empty")
        if written == 0 and skipped == 0:
            raise RuntimeError(
                f"saw {seen} photos and wrote 0 derivatives with 0 already present "
                f"({missing} originals missing) — encoding is failing, not idle")

    return {'listings': listings, 'seen': seen, 'written': written,
            'skipped': skipped, 'missing': missing}


def main():
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument('--suburbs', nargs='+', default=TARGET_SUBURBS)
    ap.add_argument('--limit', type=int, default=0, help='cap photos processed (testing)')
    ap.add_argument('--workers', type=int, default=4,
                    help='encode threads (default 4; shares a 4-vCPU box)')
    ap.add_argument('--dry-run', action='store_true')
    ap.add_argument('--no-heartbeat', action='store_true',
                    help='skip job_run (for scoped test runs)')
    args = ap.parse_args()

    load_env()

    print(f"Suburbs: {', '.join(args.suburbs)}"
          f"{f'  limit={args.limit}' if args.limit else ''}"
          f"{'  DRY RUN' if args.dry_run else ''}", flush=True)

    if args.dry_run or args.no_heartbeat:
        res = run(args.suburbs, args.limit, args.dry_run, workers=args.workers)
    else:
        with job_run('image_derivatives', cadence_hours=24,
                     title='Image derivatives') as beat:
            res = run(args.suburbs, args.limit, args.dry_run,
                      workers=args.workers, beat=beat)

    print(f"\nlistings={res['listings']} photos={res['seen']} written={res['written']} "
          f"skipped={res['skipped']} missing={res['missing']}", flush=True)


if __name__ == '__main__':
    main()
