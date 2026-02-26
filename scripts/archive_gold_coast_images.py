#!/usr/bin/env python3
"""
Archive Gold_Coast Database Images to Azure Blob Storage
Created: 2026-02-27

Walks every suburb collection in the Gold_Coast database, downloads all images
from scraped_data.images[].url and stores them in Azure Blob Storage.

Blob path structure:
  container: property-images
  gold_coast/{suburb}/{document_id}/{address_slug}/{index:02d}.jpg

Blob metadata (stored on each blob):
  document_id: MongoDB _id as string
  address: full complete_address value
  suburb: suburb collection name
  source_url: original Domain CDN URL

Skip logic:
  - Documents with images_uploaded_to_blob=True are skipped (idempotent)
  - Belt-and-braces: also skips if scraped_data.images[0].url already contains
    blob.core.windows.net (meaning a previous partial run updated URLs in place)

After upload, the document is updated:
  scraped_data.images[].url  -> replaced with blob URL
  images_uploaded_to_blob    -> True
  images_blob_uploaded_at    -> UTC ISO timestamp

Note: original Domain URLs are NOT preserved in this database — the document
traceability is via blob metadata (document_id, address) and the blob path itself
which encodes suburb/document_id/address_slug.

Log file: /home/fields/Fields_Orchestrator/logs/archive_gold_coast_images.log
  - Appended every run, never overwritten

USAGE:
  python3 scripts/archive_gold_coast_images.py
  python3 scripts/archive_gold_coast_images.py --suburbs robina,varsity_lakes
  python3 scripts/archive_gold_coast_images.py --dry-run --suburbs robina
  python3 scripts/archive_gold_coast_images.py --no-fail
"""

import os
import sys
import re
import time
import argparse
import requests
from datetime import datetime, timezone
from pathlib import Path
from concurrent.futures import ThreadPoolExecutor, as_completed

from pymongo import MongoClient
from azure.storage.blob import BlobServiceClient, ContentSettings

# ── Configuration ──────────────────────────────────────────────────────────────

MONGODB_URI = os.getenv('MONGODB_URI', '')
AZURE_STORAGE_CONNECTION_STRING = os.getenv('AZURE_STORAGE_CONNECTION_STRING', '')

DATABASE_NAME   = 'Gold_Coast'
CONTAINER_NAME  = 'property-images'
DB_LABEL        = 'gold_coast'
BLOB_DOMAIN     = 'blob.core.windows.net'

DOWNLOAD_THREADS = 6
REQUEST_TIMEOUT  = 15  # seconds per image
COSMOS_SLEEP     = 0.5  # seconds between document updates to avoid 429s

LOG_FILE = Path(__file__).parent.parent / 'logs' / 'archive_gold_coast_images.log'

# System/precomputed collections — not suburb data
SKIP_COLLECTIONS = {
    'precomputed_active_listings',
    'precomputed_indexed_prices',
    'precomputed_market_charts',
}


# ── Helpers ────────────────────────────────────────────────────────────────────

def write_log(lines):
    LOG_FILE.parent.mkdir(parents=True, exist_ok=True)
    with open(LOG_FILE, 'a') as f:
        for line in lines:
            f.write(line + '\n')


def slugify_address(address):
    """Convert address to a safe directory/blob name component."""
    if not address:
        return 'unknown'
    s = address.lower()
    s = re.sub(r'[^a-z0-9]+', '_', s)
    s = s.strip('_')
    return s[:80]  # cap length


def get_blob_url(account_name, blob_name):
    return f"https://{account_name}.{BLOB_DOMAIN}/{CONTAINER_NAME}/{blob_name}"


def is_already_uploaded(doc):
    """True if this document has already been processed."""
    if doc.get('images_uploaded_to_blob') is True:
        return True
    images = doc.get('scraped_data', {}).get('images', [])
    if images and isinstance(images[0], dict):
        url = images[0].get('url', '')
        if BLOB_DOMAIN in url:
            return True
    return False


def download_image(url):
    try:
        url = url.rstrip('\\')
        resp = requests.get(url, timeout=REQUEST_TIMEOUT)
        if resp.status_code == 200:
            return resp.content
        print(f"    WARNING: HTTP {resp.status_code} for {url[:80]}", flush=True)
        return None
    except Exception as e:
        print(f"    WARNING: Download failed for {url[:80]}: {e}", flush=True)
        return None


def upload_property_images(blob_service_client, doc, suburb, dry_run):
    """
    Download all images for a document and upload to blob storage.
    Returns list of updated image dicts (with blob URLs replacing Domain URLs).
    """
    doc_id   = str(doc['_id'])
    address  = doc.get('complete_address', '')
    addr_slug = slugify_address(address)
    images   = doc.get('scraped_data', {}).get('images', [])
    account_name = blob_service_client.account_name

    if not images:
        return []

    # Build upload tasks: (source_url, blob_name, list_index)
    tasks = []
    for i, img in enumerate(images):
        if not isinstance(img, dict):
            continue
        url = img.get('url', '')
        if not url or BLOB_DOMAIN in url:
            continue
        blob_name = f"{DB_LABEL}/{suburb}/{doc_id}/{addr_slug}/{i:02d}.jpg"
        tasks.append((url, blob_name, i))

    if not tasks:
        return images  # nothing to do

    if dry_run:
        for url, blob_name, i in tasks:
            blob_url = get_blob_url(account_name, blob_name)
            print(f"    [DRY-RUN] {url[:60]}... -> {blob_name}", flush=True)
        return images

    # Upload concurrently
    new_images = list(images)  # shallow copy

    def upload_one(task):
        url, blob_name, i = task
        data = download_image(url)
        if data is None:
            return (i, None)
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
                metadata={
                    'document_id': doc_id,
                    'address':     address[:256],
                    'suburb':      suburb,
                    'source_url':  url[:256],
                },
            )
            return (i, get_blob_url(account_name, blob_name))
        except Exception as e:
            print(f"    WARNING: Blob upload failed for {blob_name}: {e}", flush=True)
            return (i, None)

    with ThreadPoolExecutor(max_workers=DOWNLOAD_THREADS) as executor:
        futures = {executor.submit(upload_one, task): task for task in tasks}
        for future in as_completed(futures):
            try:
                i, blob_url = future.result()
                if blob_url and i < len(new_images):
                    new_images[i] = dict(new_images[i])
                    new_images[i]['url'] = blob_url
            except Exception as e:
                print(f"    WARNING: Thread error: {e}", flush=True)

    return new_images


def process_collection(mongo_client, blob_service_client, collection_name, dry_run):
    db = mongo_client[DATABASE_NAME]
    coll = db[collection_name]

    # Only fetch docs that have images and haven't been uploaded yet
    query = {
        'scraped_data.images': {'$exists': True},
        'images_uploaded_to_blob': {'$ne': True},
    }
    docs = list(coll.find(query, {
        '_id': 1,
        'complete_address': 1,
        'scraped_data.images': 1,
        'images_uploaded_to_blob': 1,
    }))

    total    = len(docs)
    uploaded = 0
    skipped  = 0
    failed   = 0

    for doc in docs:
        if is_already_uploaded(doc):
            skipped += 1
            continue

        doc_id  = str(doc['_id'])
        address = doc.get('complete_address', 'unknown')
        images  = doc.get('scraped_data', {}).get('images', [])
        n_imgs  = len(images)

        print(f"  {collection_name}/{doc_id}  {n_imgs} images  {address}", flush=True)

        try:
            new_images = upload_property_images(
                blob_service_client, doc, collection_name, dry_run
            )

            if not dry_run:
                # Re-fetch full doc for update (we only projected a subset)
                coll.update_one(
                    {'_id': doc['_id']},
                    {'$set': {
                        'scraped_data.images':     new_images,
                        'images_uploaded_to_blob': True,
                        'images_blob_uploaded_at': datetime.now(timezone.utc).isoformat(),
                    }}
                )
                time.sleep(COSMOS_SLEEP)

            uploaded += 1
            uploaded_count = sum(
                1 for img in new_images
                if isinstance(img, dict) and BLOB_DOMAIN in img.get('url', '')
            )
            print(f"    OK: {uploaded_count}/{n_imgs} images archived", flush=True)

        except Exception as e:
            failed += 1
            print(f"  ERROR: {doc_id} failed: {e}", flush=True)

    return {'total': total, 'uploaded': uploaded, 'skipped': skipped, 'failed': failed}


# ── Main ───────────────────────────────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser(
        description='Archive Gold_Coast database images to Azure Blob Storage',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  python3 scripts/archive_gold_coast_images.py
  python3 scripts/archive_gold_coast_images.py --suburbs robina,varsity_lakes
  python3 scripts/archive_gold_coast_images.py --dry-run --suburbs robina
  python3 scripts/archive_gold_coast_images.py --no-fail
        """
    )
    parser.add_argument('--suburbs', type=str,
                        help='Comma-separated collection names (e.g. robina,varsity_lakes)')
    parser.add_argument('--dry-run', action='store_true',
                        help='Log what would be uploaded without actually uploading')
    parser.add_argument('--no-fail', action='store_true',
                        help='Always exit 0 (for orchestrator integration)')
    args = parser.parse_args()

    def fail(msg):
        print(msg)
        sys.exit(0 if args.no_fail else 1)

    if not MONGODB_URI:
        fail("ERROR: MONGODB_URI environment variable is not set.")
    if not AZURE_STORAGE_CONNECTION_STRING:
        fail("ERROR: AZURE_STORAGE_CONNECTION_STRING environment variable is not set.")

    run_ts  = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
    dry_tag = " [DRY-RUN]" if args.dry_run else ""

    print(f"\n{'=' * 70}")
    print(f"ARCHIVE GOLD_COAST IMAGES TO BLOB STORAGE{dry_tag}")
    print(f"{'=' * 70}")
    print(f"Timestamp:  {run_ts}")
    print(f"Database:   {DATABASE_NAME}")
    print(f"Container:  {CONTAINER_NAME}")
    print(f"Blob prefix: {DB_LABEL}/{{suburb}}/{{doc_id}}/{{address_slug}}/")
    print(f"Log file:   {LOG_FILE}")
    print(f"{'=' * 70}\n")

    # Connect MongoDB
    try:
        mongo_client = MongoClient(
            MONGODB_URI, serverSelectionTimeoutMS=15000, tlsAllowInvalidCertificates=True
        )
        mongo_client.admin.command('ping')
        print("MongoDB connected.\n")
    except Exception as e:
        fail(f"ERROR: MongoDB connection failed: {e}")

    # Connect Azure Blob
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

    # Determine collections to process
    if args.suburbs:
        collections = [s.strip() for s in args.suburbs.split(',') if s.strip()]
    else:
        try:
            all_colls = mongo_client[DATABASE_NAME].list_collection_names()
            collections = sorted(c for c in all_colls if c not in SKIP_COLLECTIONS)
        except Exception as e:
            mongo_client.close()
            fail(f"ERROR: Could not list collections: {e}")

    print(f"Collections to process: {len(collections)}\n")

    overall   = {'total': 0, 'uploaded': 0, 'skipped': 0, 'failed': 0}
    log_lines = ['', '=' * 70, f"ARCHIVE GOLD_COAST RUN: {run_ts}{dry_tag}", '=' * 70]

    for coll_name in collections:
        print(f"\nCollection: {coll_name}")
        try:
            result = process_collection(
                mongo_client, blob_service_client, coll_name, args.dry_run
            )
            for k in overall:
                overall[k] += result[k]

            status = "OK  " if result['failed'] == 0 else "WARN"
            log_lines.append(
                f"[{status}] {run_ts}  {coll_name:35s}  "
                f"uploaded={result['uploaded']}  skipped={result['skipped']}  "
                f"failed={result['failed']}"
            )
            print(
                f"  Uploaded={result['uploaded']}  Skipped={result['skipped']}  "
                f"Failed={result['failed']}",
                flush=True
            )
        except Exception as e:
            print(f"  ERROR: Collection {coll_name} failed: {e}", flush=True)
            log_lines.append(
                f"[ERR ] {run_ts}  {coll_name:35s}  EXCEPTION: {e}"
            )

    # Summary
    print(f"\n{'=' * 70}")
    print(f"SUMMARY{dry_tag}")
    print(f"{'=' * 70}")
    print(f"Documents found:    {overall['total']}")
    print(f"Documents uploaded: {overall['uploaded']}")
    print(f"Documents skipped:  {overall['skipped']}")
    print(f"Documents failed:   {overall['failed']}")
    print(f"{'=' * 70}\n")
    print(f"Full log appended to: {LOG_FILE}")

    log_lines.append(
        f"TOTAL: uploaded={overall['uploaded']}  skipped={overall['skipped']}  "
        f"failed={overall['failed']}"
    )
    log_lines.append('=' * 70)
    write_log(log_lines)

    mongo_client.close()
    sys.exit(0)


if __name__ == '__main__':
    main()
