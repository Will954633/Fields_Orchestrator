#!/usr/bin/env python3
"""
Migrate all Azure Blob Storage containers to Google Cloud Storage.

STREAMING approach — migrates blobs as they're listed, never holds
more than BATCH_SIZE blob names in memory.

Usage:
  python3 scripts/migrate_azure_blobs_to_gcs.py                    # All containers
  python3 scripts/migrate_azure_blobs_to_gcs.py --container property-images
  python3 scripts/migrate_azure_blobs_to_gcs.py --dry-run
"""

import os
import sys
import argparse
import subprocess
import time
import tempfile
from concurrent.futures import ThreadPoolExecutor, as_completed

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from shared.env import load_env
load_env()

from azure.storage.blob import BlobServiceClient
from google.oauth2 import credentials as gcreds
from google.cloud import storage as gcs_storage

AZURE_CONN = os.environ["AZURE_STORAGE_CONNECTION_STRING"]

CONTAINER_MAP = {
    "property-images": "fields-property-images",
    "accounting": "fields-accounting-data",
    "knowledge-base": "fields-knowledge-base",
}

WORKERS = 8
BATCH_SIZE = 200  # process this many blobs at a time


def get_gcs_client():
    """Get GCS client using gcloud CLI auth."""
    result = subprocess.run(["gcloud", "auth", "print-access-token"], capture_output=True, text=True)
    token = result.stdout.strip()
    creds = gcreds.Credentials(token=token)
    return gcs_storage.Client(credentials=creds, project="fields-estate")


def migrate_blob(azure_cc, gcs_bucket, blob_name, blob_size):
    """Download one blob from Azure, upload to GCS."""
    tmp_path = None
    try:
        suffix = os.path.splitext(blob_name)[1] or ".bin"
        with tempfile.NamedTemporaryFile(delete=False, suffix=suffix, dir="/tmp") as tmp:
            tmp_path = tmp.name
            stream = azure_cc.download_blob(blob_name)
            stream.readinto(tmp)

        content_type = "application/octet-stream"
        lower = blob_name.lower()
        if lower.endswith((".jpg", ".jpeg")):
            content_type = "image/jpeg"
        elif lower.endswith(".png"):
            content_type = "image/png"
        elif lower.endswith(".webp"):
            content_type = "image/webp"
        elif lower.endswith(".pdf"):
            content_type = "application/pdf"
        elif lower.endswith(".json"):
            content_type = "application/json"
        elif lower.endswith((".txt", ".md")):
            content_type = "text/plain"

        gcs_blob = gcs_bucket.blob(blob_name)
        gcs_blob.upload_from_filename(tmp_path, content_type=content_type)

        return blob_size, None
    except Exception as e:
        return 0, f"{blob_name}: {e}"
    finally:
        if tmp_path and os.path.exists(tmp_path):
            os.unlink(tmp_path)


def get_existing_prefixes(gcs_client, gcs_bucket_name):
    """Get set of existing blob name prefixes (first 2 path segments) for fast skip checking."""
    # Instead of listing all GCS blobs (could also be millions),
    # we'll check existence per-blob during migration
    return set()


def migrate_container(azure_conn, container_name, gcs_bucket_name, dry_run=False):
    """Migrate blobs in streaming batches — never holds all names in memory."""
    azure_service = BlobServiceClient.from_connection_string(azure_conn)
    azure_cc = azure_service.get_container_client(container_name)

    gcs_client = get_gcs_client()
    gcs_bucket = gcs_client.bucket(gcs_bucket_name)

    print(f"\n  {container_name} → {gcs_bucket_name}", flush=True)
    print(f"  Streaming migration (batch size: {BATCH_SIZE})...", flush=True)

    if dry_run:
        count = 0
        size = 0
        for blob in azure_cc.list_blobs():
            count += 1
            size += blob.size
            if count % 100000 == 0:
                print(f"    ... {count:,} blobs counted, {size/1024/1024/1024:.1f} GB", flush=True)
        print(f"  Total: {count:,} blobs, {size/1024/1024/1024:.1f} GB (dry run)")
        return count, size, 0

    migrated = 0
    skipped = 0
    migrated_bytes = 0
    errors = []
    listed = 0
    start = time.time()

    batch = []
    executor = ThreadPoolExecutor(max_workers=WORKERS)

    for blob in azure_cc.list_blobs():
        listed += 1
        batch.append((blob.name, blob.size))

        if len(batch) >= BATCH_SIZE:
            # Process this batch
            futures = {}
            for blob_name, blob_size in batch:
                # Check if already exists in GCS
                gcs_blob = gcs_bucket.blob(blob_name)
                if gcs_blob.exists():
                    skipped += 1
                    continue
                f = executor.submit(migrate_blob, azure_cc, gcs_bucket, blob_name, blob_size)
                futures[f] = (blob_name, blob_size)

            for f in as_completed(futures):
                bytes_done, err = f.result()
                if err:
                    errors.append(err)
                else:
                    migrated += 1
                    migrated_bytes += futures[f][1]

            batch = []

            # Refresh GCS token every 50K blobs (tokens expire after 1 hour)
            if listed % 50000 == 0:
                try:
                    gcs_client = get_gcs_client()
                    gcs_bucket = gcs_client.bucket(gcs_bucket_name)
                except Exception:
                    pass

            if (migrated + skipped) % 500 == 0 and (migrated + skipped) > 0:
                elapsed = time.time() - start
                rate = migrated_bytes / 1024 / 1024 / elapsed if elapsed > 0 else 0
                print(f"    ... listed:{listed:,} migrated:{migrated:,} skipped:{skipped:,} "
                      f"({migrated_bytes/1024/1024/1024:.1f} GB) "
                      f"@ {rate:.1f} MB/s, errors:{len(errors)}", flush=True)

        if listed % 100000 == 0:
            elapsed = time.time() - start
            print(f"    ... {listed:,} blobs scanned, {migrated:,} migrated, "
                  f"{skipped:,} skipped", flush=True)

    # Process remaining batch
    if batch:
        futures = {}
        for blob_name, blob_size in batch:
            gcs_blob = gcs_bucket.blob(blob_name)
            if gcs_blob.exists():
                skipped += 1
                continue
            f = executor.submit(migrate_blob, azure_cc, gcs_bucket, blob_name, blob_size)
            futures[f] = (blob_name, blob_size)

        for f in as_completed(futures):
            bytes_done, err = f.result()
            if err:
                errors.append(err)
            else:
                migrated += 1
                migrated_bytes += futures[f][1]

    executor.shutdown(wait=True)

    elapsed = time.time() - start
    rate = migrated_bytes / 1024 / 1024 / elapsed if elapsed > 0 else 0
    print(f"  Done: listed:{listed:,} migrated:{migrated:,} skipped:{skipped:,} "
          f"errors:{len(errors)} ({migrated_bytes/1024/1024/1024:.1f} GB in {elapsed/3600:.1f}h @ {rate:.1f} MB/s)")
    if errors:
        print(f"  First 5 errors:")
        for e in errors[:5]:
            print(f"    {e}")

    return listed, migrated_bytes, len(errors)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--container", help="Migrate only this container")
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()

    containers = {args.container: CONTAINER_MAP[args.container]} if args.container else CONTAINER_MAP

    print(f"{'DRY RUN — ' if args.dry_run else ''}Migrating Azure Blob Storage → GCS (streaming)")
    print(f"{'='*60}")

    grand_total = 0
    grand_bytes = 0
    grand_errors = 0
    start = time.time()

    for container, bucket in containers.items():
        count, bytes_done, errs = migrate_container(AZURE_CONN, container, bucket, args.dry_run)
        grand_total += count
        grand_bytes += bytes_done
        grand_errors += errs

    elapsed = time.time() - start
    print(f"\n{'='*60}")
    print(f"  COMPLETE: {grand_total:,} blobs, {grand_bytes/1024/1024/1024:.1f} GB, {grand_errors} errors")
    print(f"  Total time: {elapsed/3600:.1f} hours")
    print(f"{'='*60}")


if __name__ == "__main__":
    main()
