#!/usr/bin/env python3
"""
Download Property Images to Azure Blob Storage
Created: 2026-02-26

Downloads property_images and floor_plans from Domain CDN URLs and stores them
in Azure Blob Storage. Updates MongoDB documents to point at blob URLs instead.

Blob path structure:
  container: property-images
  {db_label}/{suburb}/{property_id}/photos/{index:02d}.jpg
  {db_label}/{suburb}/{property_id}/floor_plans/{index:02d}.jpg

Where db_label is "for_sale", "sold", or "target_sold".

Skip logic: properties with images_uploaded_to_blob=True are skipped (idempotent).
Belt-and-braces: also skips if property_images[0] already contains blob.core.windows.net.

Log file: /home/fields/Fields_Orchestrator/logs/download_images_to_blob.log
  - Appended every run, never overwritten

USAGE:
  python3 scripts/download_images_to_blob.py
  python3 scripts/download_images_to_blob.py --db for_sale
  python3 scripts/download_images_to_blob.py --suburbs "Robina:4226,Varsity Lakes:4227"
  python3 scripts/download_images_to_blob.py --dry-run --no-fail
"""

import os
import sys
import argparse
import time
import requests
from datetime import datetime, timezone
from pathlib import Path
from concurrent.futures import ThreadPoolExecutor, as_completed

REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, REPO_ROOT)

from shared.env import load_env  # type: ignore
from shared.db import get_client  # type: ignore
from shared import blob_storage  # type: ignore

load_env()

# ── Configuration ─────────────────────────────────────────────────────────────

AZURE_STORAGE_CONNECTION_STRING = os.getenv('AZURE_STORAGE_CONNECTION_STRING', '')

DB_FOR_SALE        = 'Gold_Coast'
DB_SOLD            = 'Gold_Coast'
DB_TARGET_SOLD     = 'Target_Market_Sold_Last_12_Months'

CONTAINER_NAME   = 'property-images'
BLOB_DOMAIN      = 'blob.core.windows.net'
DOWNLOAD_THREADS = 6
REQUEST_TIMEOUT  = 15  # seconds per image download

LOG_FILE = Path(__file__).parent.parent / "logs" / "download_images_to_blob.log"

# Collections that are metadata/system, not suburb property data
SKIP_COLLECTIONS = {'change_detection_snapshots', 'suburb_median_prices', 'suburb_statistics'}


# ── Helpers ───────────────────────────────────────────────────────────────────

def write_log(lines):
    LOG_FILE.parent.mkdir(parents=True, exist_ok=True)
    with open(LOG_FILE, 'a') as f:
        for line in lines:
            f.write(line + '\n')


def parse_suburbs_arg(arg):
    suburbs = []
    for part in arg.split(','):
        part = part.strip()
        if ':' in part:
            name, _ = part.split(':', 1)
            name = name.strip()
            collection = name.lower().replace(' ', '_').replace('-', '_')
            suburbs.append({'name': name, 'collection': collection})
        else:
            print(f"WARNING: Skipping malformed suburb '{part}' (expected Name:postcode)")
    return suburbs


def is_already_uploaded(doc):
    images = doc.get('property_images', [])
    if images and isinstance(images[0], str) and BLOB_DOMAIN in images[0]:
        return True
    return False


# Hosts that appear in Domain's image list but never serve an image — 3D tours and
# video embeds. Fetching one returns HTTP 200 and an HTML page, which used to be
# written straight to a .jpg (six of them found 2026-08-13). blob_storage.upload now
# refuses those bytes; this skips the pointless fetch as well. Matterport URLs also
# carry an `auth=Bearer …` token, so not requesting them keeps a credential off the
# wire. See 15_On_Market/HANDOFF_two_live_defects.md.
NON_IMAGE_URL_HOSTS = (
    'my.matterport.com',
    'matterport.com',
    'youtube.com',
    'youtu.be',
    'vimeo.com',
    'kuula.co',
)

# Path fragments that mark a tour/viewer page on a host we otherwise trust. A full
# sweep of all 364,148 URLs in `property_images_original` (2026-08-13) found exactly
# two non-CDN hosts: 10 `my.matterport.com` URLs and 8
# `www.domain.com.au/virtual-viewer/exterior?listingId=…`. Only Matterport actually
# trips the defect — the virtual-viewer fetch fails and is dropped — but it is one
# upstream change away from returning 200, so it is filtered too. Matching on path
# means we never blanket-block `www.domain.com.au`.
NON_IMAGE_URL_PATHS = (
    '/virtual-viewer',
    '/virtualtour',
    '/virtual-tour',
)


def is_non_image_url(url):
    if not isinstance(url, str):
        return True
    lowered = url.lower()
    if any(host in lowered for host in NON_IMAGE_URL_HOSTS):
        return True
    return any(frag in lowered for frag in NON_IMAGE_URL_PATHS)


def download_single_image(url):
    try:
        url = url.rstrip('\\')
        resp = requests.get(url, timeout=REQUEST_TIMEOUT)
        if resp.status_code == 200:
            return resp.content
        print(f"    WARNING: HTTP {resp.status_code} for {url}", flush=True)
        return None
    except Exception as e:
        print(f"    WARNING: Download failed for {url}: {e}", flush=True)
        return None


def get_blob_url(_account_name_unused, blob_name):
    return blob_storage.public_url(CONTAINER_NAME, blob_name)


def upload_images_for_property(blob_service_client, doc, db_label, suburb, dry_run,
                                date_prefix=None):
    property_id = str(doc.get('_id', 'unknown'))
    # Prefer scraped_property_images (fresh Domain URLs) over property_images (may be blob URLs)
    photo_urls  = doc.get('scraped_property_images') or doc.get('property_images') or doc.get('domain_image_urls', [])
    fp_urls     = doc.get('scraped_floor_plans') or doc.get('floor_plans', [])

    if not isinstance(photo_urls, list):
        photo_urls = []
    if not isinstance(fp_urls, list):
        fp_urls = []

    # Skip if source URLs are already blob URLs (nothing to download)
    if photo_urls and isinstance(photo_urls[0], str) and BLOB_DOMAIN in photo_urls[0]:
        return (photo_urls, fp_urls)

    account_name = None  # unused in local backend; kept for signature compat

    # Use dated subfolder for historical image tracking
    if date_prefix is None:
        date_prefix = datetime.now().strftime('%Y-%m-%d')

    # Build list of (source_url, blob_name, category, index) tuples
    tasks = []
    for i, url in enumerate(photo_urls):
        if isinstance(url, str) and url:
            if is_non_image_url(url):
                print(f"    SKIP non-image source (3D tour/video) at photo index {i}", flush=True)
                continue
            blob_name = f"{db_label}/{suburb}/{property_id}/photos/{date_prefix}/{i:02d}.jpg"
            tasks.append((url, blob_name, 'photo', i))
    for i, url in enumerate(fp_urls):
        if isinstance(url, str) and url:
            if is_non_image_url(url):
                print(f"    SKIP non-image source (3D tour/video) at floor plan index {i}", flush=True)
                continue
            blob_name = f"{db_label}/{suburb}/{property_id}/floor_plans/{date_prefix}/{i:02d}.jpg"
            tasks.append((url, blob_name, 'floor_plan', i))

    new_photo_urls = [None] * len(photo_urls)
    new_fp_urls    = [None] * len(fp_urls)

    if dry_run:
        for url, blob_name, category, idx in tasks:
            blob_url = get_blob_url(account_name, blob_name)
            print(f"    [DRY-RUN] {url[:60]}... -> {blob_name}", flush=True)
            if category == 'photo':
                new_photo_urls[idx] = blob_url
            else:
                new_fp_urls[idx] = blob_url
        return (
            [u for u in new_photo_urls if u],
            [u for u in new_fp_urls if u],
        )

    def upload_one(task):
        url, blob_name, category, idx = task
        data = download_single_image(url)
        if data is None:
            return (category, idx, None)
        blob_url = blob_storage.upload(
            CONTAINER_NAME, blob_name, data,
            content_type='image/jpeg',
            cache_control='public, max-age=31536000',
        )
        if blob_url is None:
            print(f"    WARNING: Blob upload failed for {blob_name}", flush=True)
        return (category, idx, blob_url)

    with ThreadPoolExecutor(max_workers=DOWNLOAD_THREADS) as executor:
        futures = {executor.submit(upload_one, task): task for task in tasks}
        for future in as_completed(futures):
            try:
                category, idx, blob_url = future.result()
                if blob_url:
                    if category == 'photo':
                        new_photo_urls[idx] = blob_url
                    else:
                        new_fp_urls[idx] = blob_url
            except Exception as e:
                print(f"    WARNING: Unexpected upload thread error: {e}", flush=True)

    return (
        [u for u in new_photo_urls if u],
        [u for u in new_fp_urls if u],
    )


def process_collection(mongo_client, blob_service_client, db_name, db_label,
                        collection_name, dry_run):
    db = mongo_client[db_name]
    collection = db[collection_name]

    # Find properties that need image download:
    # 1. images_uploaded_to_blob is not True (new or reset by scraper)
    # 2. Has image URLs to download (property_images or scraped_property_images)
    query = {
        "$or": [
            # Normal path: has source URLs and not yet uploaded to blob.
            {
                "images_uploaded_to_blob": {"$ne": True},
                "$or": [
                    {"property_images": {"$exists": True, "$ne": []}},
                    {"scraped_property_images": {"$exists": True, "$ne": []}},
                ],
            },
            # Gap fix (2026-07-30): the profile scraper captures the full gallery into
            # `domain_image_urls` but never uploads it — property_images stays absent/empty
            # even though images_uploaded_to_blob can be (wrongly) True. These photo-less
            # sold homes were falling back to a chart hero. Pull their galleries in too —
            # but ONLY for actual listings (sold/for_sale), NOT the whole cadastral base
            # (every parcel carries a domain_image_urls gallery; we don't need those).
            {
                "domain_image_urls": {"$exists": True, "$ne": []},
                "listing_status": {"$in": ["sold", "for_sale"]},
                "$or": [
                    {"property_images": {"$exists": False}},
                    {"property_images": {"$in": [None, []]}},
                ],
            },
        ],
    }
    docs = list(collection.find(query))

    total    = len(docs)
    uploaded = 0
    skipped  = 0
    failed   = 0

    date_prefix = datetime.now().strftime('%Y-%m-%d')

    for doc in docs:
        # Skip if property_images already contains blob URLs AND no scraped_ URLs waiting
        if is_already_uploaded(doc) and not doc.get('scraped_property_images'):
            skipped += 1
            continue

        property_id = str(doc.get('_id', 'unknown'))
        source_photos = doc.get('scraped_property_images') or doc.get('property_images') or doc.get('domain_image_urls', [])
        source_fps = doc.get('scraped_floor_plans') or doc.get('floor_plans', [])
        n_photos = len(source_photos) if isinstance(source_photos, list) else 0
        n_fps    = len(source_fps) if isinstance(source_fps, list) else 0
        print(f"  {collection_name}/{property_id}  ({n_photos} photos, {n_fps} floor plans)",
              flush=True)

        try:
            new_photos, new_fps = upload_images_for_property(
                blob_service_client, doc, db_label, collection_name, dry_run,
                date_prefix=date_prefix
            )

            if not dry_run:
                now_iso = datetime.now(timezone.utc).isoformat()

                # Build image_history entry for this upload
                history_entry = {
                    "captured_at": now_iso,
                    "source": "new_listing" if doc.get('listing_status') == 'for_sale' else "scrape",
                    "listing_url": doc.get("listing_url", ""),
                    "image_count": len(new_photos),
                    "floor_plan_count": len(new_fps),
                    "blob_prefix": f"{db_label}/{collection_name}/{property_id}/photos/{date_prefix}/",
                    "urls": new_photos,
                }

                # Preserve original source URLs
                original_photos = doc.get('scraped_property_images') or doc.get('property_images') or doc.get('domain_image_urls', [])
                original_fps = doc.get('scraped_floor_plans') or doc.get('floor_plans', [])

                collection.update_one(
                    {"_id": doc["_id"]},
                    {
                        "$set": {
                            "property_images":          new_photos,
                            "floor_plans":              new_fps,
                            "property_images_original": original_photos,
                            "floor_plans_original":     original_fps,
                            "images_uploaded_to_blob":  True,
                            "images_blob_uploaded_at":  now_iso,
                        },
                        "$push": {
                            "image_history": history_entry,
                        },
                    }
                )

            uploaded += 1
            print(f"    OK: {len(new_photos)} photos, {len(new_fps)} floor plans archived",
                  flush=True)

        except Exception as e:
            failed += 1
            print(f"  ERROR: Property {property_id} failed: {e}", flush=True)

    return {"total": total, "uploaded": uploaded, "skipped": skipped, "failed": failed}


# ── Main ──────────────────────────────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser(
        description='Download property images to Azure Blob Storage',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  python3 scripts/download_images_to_blob.py
  python3 scripts/download_images_to_blob.py --db for_sale
  python3 scripts/download_images_to_blob.py --suburbs "Robina:4226,Varsity Lakes:4227"
  python3 scripts/download_images_to_blob.py --dry-run --no-fail
        """
    )
    parser.add_argument('--no-fail',  action='store_true',
                        help='Always exit 0 (for orchestrator integration)')
    parser.add_argument('--suburbs',  type=str,
                        help='Comma-separated Name:postcode pairs to limit scope')
    parser.add_argument('--db',       type=str,
                        choices=['for_sale', 'sold', 'target_sold', 'all'],
                        default='all', help='Which database(s) to process (default: all)')
    parser.add_argument('--dry-run',  action='store_true',
                        help='Log what would be uploaded without actually uploading')
    args = parser.parse_args()

    def fail(msg):
        print(msg)
        sys.exit(0 if args.no_fail else 1)

    if not AZURE_STORAGE_CONNECTION_STRING:
        fail("ERROR: AZURE_STORAGE_CONNECTION_STRING environment variable is not set.")

    run_ts  = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
    dry_tag = " [DRY-RUN]" if args.dry_run else ""

    print(f"\n{'=' * 70}")
    print(f"DOWNLOAD IMAGES TO BLOB STORAGE{dry_tag}")
    print(f"{'=' * 70}")
    print(f"Timestamp:      {run_ts}")
    print(f"Database scope: {args.db} (for_sale, sold, target_sold, or all)")
    print(f"Log file:       {LOG_FILE}")
    print(f"{'=' * 70}\n")

    # Connect MongoDB
    try:
        mongo_client = get_client()
        mongo_client.admin.command('ping')
        print("MongoDB connected.\n")
    except Exception as e:
        fail(f"ERROR: MongoDB connection failed: {e}")

    blob_service_client = None  # legacy positional arg, no longer used
    print(f"Blob backend: {os.getenv('BLOB_BACKEND', 'local')} (container '{CONTAINER_NAME}')\n")

    # Determine database scope
    db_scope = []
    if args.db in ('for_sale', 'all'):
        db_scope.append(('for_sale', DB_FOR_SALE))
    if args.db in ('sold', 'all'):
        db_scope.append(('sold', DB_SOLD))
    if args.db in ('target_sold', 'all'):
        db_scope.append(('target_sold', DB_TARGET_SOLD))

    overall   = {"total": 0, "uploaded": 0, "skipped": 0, "failed": 0}
    log_lines = ["", "=" * 70, f"DOWNLOAD IMAGES RUN: {run_ts}{dry_tag}", "=" * 70]

    for db_label, db_name in db_scope:
        print(f"\nDatabase: {db_name}")

        if args.suburbs:
            collections = [s['collection'] for s in parse_suburbs_arg(args.suburbs)]
        else:
            try:
                collections = [
                    c for c in sorted(mongo_client[db_name].list_collection_names())
                    if c not in SKIP_COLLECTIONS
                ]
            except Exception as e:
                print(f"  ERROR: Could not list collections in {db_name}: {e}")
                continue

        for coll in collections:
            print(f"\n  Collection: {coll}")
            try:
                result = process_collection(
                    mongo_client, blob_service_client,
                    db_name, db_label, coll, args.dry_run
                )
                for k in overall:
                    overall[k] += result[k]

                status = "OK  " if result["failed"] == 0 else "WARN"
                log_lines.append(
                    f"[{status}] {run_ts}  {db_label}/{coll:30s}  "
                    f"uploaded={result['uploaded']}  skipped={result['skipped']}  "
                    f"failed={result['failed']}"
                )
                print(
                    f"    Uploaded={result['uploaded']}  Skipped={result['skipped']}  "
                    f"Failed={result['failed']}",
                    flush=True
                )
            except Exception as e:
                print(f"  ERROR: Collection {coll} failed: {e}", flush=True)
                log_lines.append(
                    f"[ERR ] {run_ts}  {db_label}/{coll:30s}  EXCEPTION: {e}"
                )

    # Summary
    print(f"\n{'=' * 70}")
    print(f"SUMMARY{dry_tag}")
    print(f"{'=' * 70}")
    print(f"Properties found:    {overall['total']}")
    print(f"Properties uploaded: {overall['uploaded']}")
    print(f"Properties skipped:  {overall['skipped']}")
    print(f"Properties failed:   {overall['failed']}")
    print(f"{'=' * 70}\n")
    print(f"Full log appended to: {LOG_FILE}")

    log_lines.append(
        f"TOTAL: uploaded={overall['uploaded']}  skipped={overall['skipped']}  "
        f"failed={overall['failed']}"
    )
    log_lines.append("=" * 70)
    write_log(log_lines)

    mongo_client.close()
    sys.exit(0)


if __name__ == '__main__':
    main()
