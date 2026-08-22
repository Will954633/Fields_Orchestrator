#!/usr/bin/env python3
"""
Backfill WebP renditions for photos of live listings.

Implements step 2/5 of `15_On_Market/03_Audit/IMAGE_DERIVATIVES_SPEC.md`. The blob
store holds one rendition per photo, so listing pages ship ~3,000px originals into an
800px slot — ~10 MB for a 14-photo gallery where 1.8 MB would do. This walks the
`for_sale` listings of the target suburbs and writes 480/960/1600 WebP beside each
original (see `shared/image_derivatives.py` for the naming and the never-upscale rule).

Idempotent: a photo whose renditions already exist is skipped without re-encoding.
Originals are never modified.

The one document write is `image_derivative_widths` on each listing — the widths present
on EVERY photo of that listing. The serializer cannot stat the blob disk, and a 404
inside `srcset` does not fall back to `src`, so it needs to be told which renditions are
safe to advertise. See `_listing_widths`.

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


def _blob_names_served(doc):
    """Blob names for every photo the public API can serve, deduped, order-stable.

    property.mjs builds the gallery (and its srcset) from `photo_tour_order` FIRST,
    then `property_images` — so a derivative must exist for a photo in EITHER array,
    not just `property_images`. When a listing's photos are re-uploaded to a new
    date-folder, `property_images` moves to it but `photo_tour_order` keeps pointing
    at the old folder; generating only for `property_images` left that old folder
    with no renditions, and the listing-level widths flag then made the browser
    request `.960.webp` files that 404 and get ORB-blocked — a blank gallery. See
    logs/fix-history/2026-08-22.md [GALLERY-SRCSET-STALE-FOLDER-404].
    """
    out, seen = [], set()
    for field in ('photo_tour_order', 'property_images'):
        for item in (doc.get(field) or []):
            url = item.get('url') if isinstance(item, dict) else item
            nm = blob_name_from_url(url)
            if nm and nm not in seen:
                seen.add(nm)
                out.append(nm)
    return out


def collect(db, suburbs, limit):
    """Live listings as (suburb, _id, [blob_name, ...]), capped at `limit` photos.

    Grouped by listing rather than flattened because the widths we advertise are a
    per-listing fact (see `_listing_widths`).
    """
    groups, n = [], 0
    for suburb in suburbs:
        for doc in db[suburb].find({'listing_status': 'for_sale'},
                                   {'property_images': 1, 'photo_tour_order': 1}):
            got = _blob_names_served(doc)
            if not got:
                continue
            if limit and n + len(got) > limit:
                got = got[:limit - n]
                if got:
                    groups.append((suburb, doc['_id'], got))
                return groups, n + len(got)
            groups.append((suburb, doc['_id'], got))
            n += len(got)
    return groups, n


def _one(name):
    """(status, count, widths) for a single photo. Runs on a worker thread.

    `corrupt` is kept apart from `skipped` on purpose. Folding an undecodable original
    into "nothing to do" is how a job reports success while achieving nothing — it hid
    three HTML-error-pages-saved-as-.jpg on the first Robina run.
    """
    before = deriv.existing_derivatives(CONTAINER, name)
    try:
        got = deriv.make_derivatives_from_disk(CONTAINER, name)
    except deriv.DecodeError as exc:
        print(f"    ! corrupt original: {exc}", flush=True)
        return ('corrupt', 0, set())
    if got is None:
        return ('missing', 0, set())
    new = set(got) - set(before)
    if new:
        return ('written', len(new), set(got))
    # Either the renditions already existed, or the source is narrower than every
    # target and correctly produced none. Both are genuinely "no work needed".
    return ('skipped', 0, set(got))


def _listing_widths(photo_widths):
    """The widths safe to advertise for a whole listing: the INTERSECTION.

    The serializer emits one `srcset` shape per listing but applies it to every photo,
    and a 404 inside `srcset` does not fall back to `src` — the image fails outright.
    So a width may only be advertised if EVERY photo has it. A listing containing one
    narrow (or corrupt) photo therefore advertises fewer widths, or none, and falls
    back to originals. Conservative on purpose: slow beats broken.
    """
    if not photo_widths:
        return []
    common = set(deriv.WIDTHS)
    for w in photo_widths:
        common &= w
    return sorted(common)


def run(suburbs, limit, dry_run, workers=4, beat=None):
    db = get_gold_coast_db()
    groups, seen = collect(db, suburbs, limit)
    listings = len(groups)
    written = skipped = missing = corrupt = tagged = 0

    if dry_run:
        for _suburb, _id, names in groups:
            for name in names:
                have = deriv.existing_derivatives(CONTAINER, name)
                todo = [w for w in deriv.WIDTHS if w not in have]
                print(f"  [DRY] {name} have={sorted(have)} todo={todo}", flush=True)
        return {'listings': listings, 'seen': seen, 'written': 0, 'skipped': 0,
                'missing': 0, 'corrupt': 0, 'tagged': 0}

    # Pillow releases the GIL across resize and encode, so threads genuinely
    # parallelise here. Kept modest: this shares a 4-vCPU box with the pipeline.
    done = 0
    with ThreadPoolExecutor(max_workers=workers) as pool:
        for suburb, _id, names in groups:
            per_photo = []
            for fut in as_completed(pool.submit(_one, n) for n in names):
                try:
                    status, n, widths = fut.result()
                except Exception as exc:
                    print(f"    ✗ worker failed: {exc}", flush=True)
                    missing += 1
                    continue
                if status == 'written':
                    written += n
                elif status == 'skipped':
                    skipped += 1
                elif status == 'corrupt':
                    corrupt += 1
                else:
                    missing += 1
                per_photo.append(widths)
                done += 1
                if done % 250 == 0:
                    print(f"  … {done}/{seen} photos, {written} written", flush=True)

            # Only widths present on EVERY photo of this listing may be advertised.
            # Written even when empty: an empty list is the instruction "serve the
            # originals", and is meaningfully different from the field being absent
            # (never processed). The serializer must treat both as originals-only.
            wid = _listing_widths(per_photo) if len(per_photo) == len(names) else []
            try:
                db[suburb].update_one({'_id': _id},
                                      {'$set': {'image_derivative_widths': wid}})
                tagged += 1
            except Exception as exc:
                print(f"    ✗ could not tag {suburb}/{_id}: {exc}", flush=True)

    if beat is not None:
        beat.metrics = {
            'listings': listings, 'photos_seen': seen, 'derivatives_written': written,
            'skipped_existing': skipped, 'originals_missing': missing,
            'originals_corrupt': corrupt, 'listings_tagged': tagged,
        }
        beat.detail = (f"{listings} listings ({tagged} tagged), {seen} photos, "
                       f"{written} written, {skipped} skipped, {missing} missing, "
                       f"{corrupt} corrupt")
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
                f"({missing} missing, {corrupt} corrupt) — encoding is failing, not idle")
        # A slow bleed of unreadable originals never trips the checks above, because
        # the healthy majority keeps `written`/`skipped` non-zero. Surface it instead
        # of letting it accumulate silently: these are photos broken on the live site.
        if corrupt and corrupt > 0.02 * seen:
            raise RuntimeError(
                f"{corrupt}/{seen} originals are undecodable (>2%) — the mirror is "
                f"storing error pages as .jpg, not just the odd bad file")
        # Derivatives nothing can find are derivatives that do not exist. If the disk
        # work succeeded but no listing carries the widths field, the website still
        # serves originals and this job has achieved nothing visible.
        if listings and tagged == 0:
            raise RuntimeError(
                f"processed {listings} listings but tagged 0 with "
                f"image_derivative_widths — the serializer cannot use any of this")

    return {'listings': listings, 'seen': seen, 'written': written,
            'skipped': skipped, 'missing': missing, 'corrupt': corrupt,
            'tagged': tagged}


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
          f"skipped={res['skipped']} missing={res['missing']} corrupt={res['corrupt']} "
          f"tagged={res['tagged']}",
          flush=True)


if __name__ == '__main__':
    main()
