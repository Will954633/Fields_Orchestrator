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

Where db_label is "for_sale" or "sold".

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

from pymongo import MongoClient
from azure.storage.blob import BlobServiceClient, ContentSettings

# ── Configuration ─────────────────────────────────────────────────────────────

MONGODB_URI = os.getenv('MONGODB_URI', 'mongodb://127.0.0.1:27017/')
AZURE_STORAGE_CONNECTION_STRING = os.getenv('AZURE_STORAGE_CONNECTION_STRING', '')

DB_FOR_SALE = 'Gold_Coast_Currently_For_Sale'
DB_SOLD     = 'Gold_Coast_Recently_Sold'

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


def get_blob_url(account_name, blob_name):
    return f"https://{account_name}.{BLOB_DOMAIN}/{CONTAINER_NAME}/{blob_name}"


def upload_images_for_property(blob_service_client, doc, db_label, suburb, dry_run):
    property_id = str(doc.get('_id', 'unknown'))
    photo_urls  = doc.get('property_images', [])
    fp_urls     = doc.get('floor_plans', [])

    if not isinstance(photo_urls, list):
        photo_urls = []
    if not isinstance(fp_urls, list):
        fp_urls = []

    account_name = blob_service_client.account_name

    # Build list of (source_url, blob_name, category, index) tuples
    tasks = []
    for i, url in enumerate(photo_urls):
        if isinstance(url, str) and url:
            blob_name = f"{db_label}/{suburb}/{property_id}/photos/{i:02d}.jpg"
            tasks.append((url, blob_name, 'photo', i))
    for i, url in enumerate(fp_urls):
        if isinstance(url, str) and url:
            blob_name = f"{db_label}/{suburb}/{property_id}/floor_plans/{i:02d}.jpg"
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
        try:
            blob_client = blob_service_client.get_blob_client(
                container=CONTAINER_NAME, blob=blob_name
            )
            blob_client.upload_blob(
                data,
                overwrite=True,
                content_settings=ContentSettings(
                    content_type='image/jpeg',
                    cache_control='public, max-age=31536000',
                ),
            )
            return (category, idx, get_blob_url(account_name, blob_name))
        except Exception as e:
            print(f"    WARNING: Blob upload failed for {blob_name}: {e}", flush=True)
            return (category, idx, None)

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

    query = {
        "property_images": {"$exists": True, "$ne": []},
        "images_uploaded_to_blob": {"$ne": True},
    }
    docs = list(collection.find(query))

    total    = len(docs)
    uploaded = 0
    skipped  = 0
    failed   = 0

    for doc in docs:
        if is_already_uploaded(doc):
            skipped += 1
            continue

        property_id = str(doc.get('_id', 'unknown'))
        n_photos = len(doc.get('property_images', []))
        n_fps    = len(doc.get('floor_plans', []))
        print(f"  {collection_name}/{property_id}  ({n_photos} photos, {n_fps} floor plans)",
              flush=True)

        try:
            new_photos, new_fps = upload_images_for_property(
                blob_service_client, doc, db_label, collection_name, dry_run
            )

            if not dry_run:
                collection.update_one(
                    {"_id": doc["_id"]},
                    {"$set": {
                        "property_images":          new_photos,
                        "floor_plans":              new_fps,
                        "property_images_original": doc.get("property_images", []),
                        "floor_plans_original":     doc.get("floor_plans", []),
                        "images_uploaded_to_blob":  True,
                        "images_blob_uploaded_at":  datetime.now(timezone.utc).isoformat(),
                    }}
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
    parser.add_argument('--db',       type=str, choices=['for_sale', 'sold', 'both'],
                        default='both', help='Which database(s) to process (default: both)')
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
    print(f"Database scope: {args.db}")
    print(f"Log file:       {LOG_FILE}")
    print(f"{'=' * 70}\n")

    # Connect MongoDB
    try:
        mongo_client = MongoClient(
            MONGODB_URI, serverSelectionTimeoutMS=10000, tlsAllowInvalidCertificates=True
        )
        mongo_client.admin.command('ping')
        print("MongoDB connected.\n")
    except Exception as e:
        fail(f"ERROR: MongoDB connection failed: {e}")

    # Connect Azure Blob Storage
    try:
        blob_service_client = BlobServiceClient.from_connection_string(
            AZURE_STORAGE_CONNECTION_STRING
        )
        container_client = blob_service_client.get_container_client(CONTAINER_NAME)
        try:
            container_client.get_container_properties()
            print(f"Azure Blob container '{CONTAINER_NAME}' exists.\n")
        except Exception:
            print(f"Creating container '{CONTAINER_NAME}'...")
            blob_service_client.create_container(CONTAINER_NAME, public_access='blob')
            print(f"Container '{CONTAINER_NAME}' created.\n")
    except Exception as e:
        mongo_client.close()
        fail(f"ERROR: Azure Blob Storage connection failed: {e}")

    # Determine database scope
    db_scope = []
    if args.db in ('for_sale', 'both'):
        db_scope.append(('for_sale', DB_FOR_SALE))
    if args.db in ('sold', 'both'):
        db_scope.append(('sold', DB_SOLD))

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
