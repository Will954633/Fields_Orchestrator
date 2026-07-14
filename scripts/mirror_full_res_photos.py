#!/usr/bin/env python3
"""
Mirror full-resolution property photos to our own permanent blob store.

Companion to PHOTO-QUALITY-01 (2026-07-15). The website now serves full-res
photos by rewriting Domain's signed `rimh2.domainstatic.com.au` thumbnails
(~150px) to their `bucket-api.domain.com.au` originals at serve time. That fixes
graininess, but leaves those listings dependent on Domain's CDN. This script
downloads the SAME full-res photos and mirrors them to `blobs.fieldsestate.com.au`
(local backend, /data/blobs) so they're permanent and under our control — the
website already prefers our blob mirror over Domain URLs.

Scope by default: target-market (Robina, Burleigh Waters, Varsity Lakes)
`for_sale` listings that (a) have NO live blob mirror yet and (b) have a full-res
Domain source we can mirror. These are the listings the /for-sale-v3 feed and
property pages actually surface. The nightly pipeline (download_images_to_blob.py)
backfills new listings over time; this fills the current gap in one pass.

Source selection mirrors the website's `upgradePhotoQuality`: rewrite rimh2 ->
bucket-api, dedupe, order by the current listing's own sequence
(domain_hero_image_url + domain_image_urls). We never mirror a 150px thumbnail
when its full-res original is reachable.

Idempotent: skips any listing already on blobs.fieldsestate.com.au. On success it
sets property_images to the new blob URLs, preserves the source URLs in
property_images_original, sets images_uploaded_to_blob=True, and appends an
image_history entry — matching download_images_to_blob.py exactly.

USAGE:
  python3 scripts/mirror_full_res_photos.py --dry-run          # show plan, no writes
  python3 scripts/mirror_full_res_photos.py                    # mirror target market
  python3 scripts/mirror_full_res_photos.py --suburbs robina   # limit to one suburb
  python3 scripts/mirror_full_res_photos.py --limit 5          # cap listings (testing)
"""
import os
import re
import sys
import argparse
from datetime import datetime, timezone
from concurrent.futures import ThreadPoolExecutor, as_completed

import requests

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from shared.env import load_env          # type: ignore
from shared.db import get_gold_coast_db  # type: ignore
from shared import blob_storage          # type: ignore

CONTAINER = 'property-images'
DB_LABEL = 'for_sale'
TARGET_SUBURBS = ['robina', 'burleigh_waters', 'varsity_lakes']
LIVE_BLOB_HOST = 'blobs.fieldsestate.com.au'
REQUEST_TIMEOUT = 20
MAX_WORKERS = 6
UA = {'User-Agent': 'Mozilla/5.0'}


def to_full_res(url):
    """Rewrite a signed rimh2 thumbnail to its full-res bucket-api original.

    Mirrors shared-utils.mjs toFullResUrl. Legacy `hpg-unique-data` paths (whose
    final segment is a whole URL) can't be rewritten and are returned unchanged.
    """
    if not isinstance(url, str) or 'rimh2.domainstatic.com.au' not in url:
        return url
    if 'hpg-unique-data' in url:
        return url
    tail = url.rsplit('/', 1)[-1]
    if not tail or 'http' in tail:
        return url
    return 'https://bucket-api.domain.com.au/v1/bucket/image/' + tail


def select_full_res_photos(doc):
    """Ordered, deduped, full-res photo URL list for the current listing.

    Same strategy as upgradePhotoQuality's no-blob branch: rewrite thumbnails,
    dedupe, order by the listing's own sequence, then append remaining sources.
    Drops any URL we couldn't get off rimh2 (legacy thumbnails) so we never
    mirror a 150px image.
    """
    sources = []
    if doc.get('domain_hero_image_url'):
        sources.append(doc['domain_hero_image_url'])
    for field in ('domain_image_urls', 'scraped_property_images',
                  'property_images_original', 'photo_tour_order'):
        v = doc.get(field)
        if isinstance(v, list):
            for it in v:
                u = it if isinstance(it, str) else (it.get('url') if isinstance(it, dict) else None)
                if u:
                    sources.append(u)

    # rewrite + dedupe exact
    rw, seen = [], set()
    for u in sources:
        f = to_full_res(u)
        if f and f not in seen:
            seen.add(f)
            rw.append(f)

    # spine = current listing order
    spine = []
    if doc.get('domain_hero_image_url'):
        spine.append(to_full_res(doc['domain_hero_image_url']))
    for u in (doc.get('domain_image_urls') or []):
        if isinstance(u, str):
            spine.append(to_full_res(u))

    def is_full_res(u):
        return 'bucket-api.domain.com.au' in u or LIVE_BLOB_HOST in u

    rw_set = set(rw)
    out = []
    for u in spine:
        if u in rw_set and is_full_res(u) and u not in out:
            out.append(u)
    for u in rw:
        if is_full_res(u) and u not in out:
            out.append(u)
    return out


def already_mirrored(doc):
    pics = doc.get('property_images') or []
    return bool(pics) and isinstance(pics[0], str) and LIVE_BLOB_HOST in pics[0]


def download(url):
    try:
        r = requests.get(url.rstrip('\\'), timeout=REQUEST_TIMEOUT, headers=UA)
        return r.content if r.status_code == 200 else None
    except Exception as e:
        print(f"      WARN download {url[:60]}: {e}", flush=True)
        return None


def mirror_listing(coll, doc, suburb, date_prefix, dry_run):
    photos = select_full_res_photos(doc)
    if not photos:
        return ('no_source', 0)
    pid = str(doc['_id'])

    tasks = [
        (u, f"{DB_LABEL}/{suburb}/{pid}/photos/{date_prefix}/{i:02d}.jpg", i)
        for i, u in enumerate(photos)
    ]

    if dry_run:
        print(f"    [DRY-RUN] {doc.get('address', pid)[:40]}: would mirror {len(tasks)} full-res photos", flush=True)
        return ('dry', len(tasks))

    new_urls = [None] * len(tasks)

    def do(task):
        src, blob_name, idx = task
        data = download(src)
        if data is None:
            return (idx, None)
        return (idx, blob_storage.upload(CONTAINER, blob_name, data, content_type='image/jpeg'))

    with ThreadPoolExecutor(max_workers=MAX_WORKERS) as ex:
        for fut in as_completed([ex.submit(do, t) for t in tasks]):
            idx, blob_url = fut.result()
            if blob_url:
                new_urls[idx] = blob_url

    new_urls = [u for u in new_urls if u]
    if not new_urls:
        return ('failed', 0)

    now_iso = datetime.now(timezone.utc).isoformat()
    coll.update_one(
        {"_id": doc["_id"]},
        {
            "$set": {
                "property_images": new_urls,
                "property_images_original": photos,
                "images_uploaded_to_blob": True,
                "images_blob_uploaded_at": now_iso,
            },
            "$push": {
                "image_history": {
                    "captured_at": now_iso,
                    "source": "full_res_mirror",
                    "listing_url": doc.get("listing_url", ""),
                    "image_count": len(new_urls),
                    "blob_prefix": f"{DB_LABEL}/{suburb}/{pid}/photos/{date_prefix}/",
                    "urls": new_urls,
                }
            },
        },
    )
    print(f"    OK {doc.get('address', pid)[:40]}: mirrored {len(new_urls)} photos", flush=True)
    return ('uploaded', len(new_urls))


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument('--dry-run', action='store_true', help='Show plan without downloading or writing')
    ap.add_argument('--suburbs', type=str, help='Comma-separated subset of target suburbs (collection names)')
    ap.add_argument('--limit', type=int, default=0, help='Cap number of listings processed (0 = no cap)')
    args = ap.parse_args()

    load_env()
    if os.getenv('BLOB_BACKEND', 'local').lower() != 'local':
        print("Refusing to run: BLOB_BACKEND is not 'local' (Azure is decommissioned).")
        sys.exit(1)

    db = get_gold_coast_db()
    suburbs = [s.strip() for s in args.suburbs.split(',')] if args.suburbs else TARGET_SUBURBS
    date_prefix = datetime.now().strftime('%Y-%m-%d')

    tag = " [DRY-RUN]" if args.dry_run else ""
    print(f"\n{'='*66}\nMIRROR FULL-RES PHOTOS -> {LIVE_BLOB_HOST}{tag}\n{'='*66}")
    print(f"Suburbs: {suburbs} | backend: {os.getenv('BLOB_BACKEND','local')} | date: {date_prefix}\n")

    counts = {'uploaded': 0, 'dry': 0, 'skipped_mirrored': 0, 'no_source': 0, 'failed': 0}
    photos_total = 0
    processed = 0

    for suburb in suburbs:
        coll = db[suburb]
        docs = list(coll.find({"listing_status": "for_sale"}))
        print(f"[{suburb}] {len(docs)} for_sale listings")
        for doc in docs:
            if already_mirrored(doc):
                counts['skipped_mirrored'] += 1
                continue
            if args.limit and processed >= args.limit:
                break
            status, n = mirror_listing(coll, doc, suburb, date_prefix, args.dry_run)
            counts[status if status in counts else 'failed'] += 1
            photos_total += n
            processed += 1
        if args.limit and processed >= args.limit:
            break

    print(f"\n{'='*66}\nSUMMARY{tag}\n{'='*66}")
    print(f"Listings mirrored:        {counts['uploaded']}")
    if args.dry_run:
        print(f"Listings planned (dry):   {counts['dry']}")
    print(f"Already on blobs (skip):  {counts['skipped_mirrored']}")
    print(f"No full-res source:       {counts['no_source']}")
    print(f"Failed:                   {counts['failed']}")
    print(f"Photos {'planned' if args.dry_run else 'mirrored'}:          {photos_total}")
    print(f"{'='*66}\n")


if __name__ == '__main__':
    main()
