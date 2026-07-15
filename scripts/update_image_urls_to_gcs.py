#!/usr/bin/env python3
"""
Update all property image URLs in MongoDB from Azure Blob to GCS.

Replaces:
  https://fieldspropertyimages.blob.core.windows.net/property-images/...
With:
  https://storage.googleapis.com/fields-property-images/...

Usage:
  python3 scripts/update_image_urls_to_gcs.py --dry-run    # Count URLs to update
  python3 scripts/update_image_urls_to_gcs.py              # Apply updates
"""

import os
import sys
import re
import argparse
import time

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from shared.env import load_env
from shared.db import get_client

load_env()

OLD_BASE = "https://fieldspropertyimages.blob.core.windows.net/property-images/"
NEW_BASE = "https://storage.googleapis.com/fields-property-images/"

# Fields in property documents that contain image URLs
IMAGE_FIELDS = [
    "property_images",
    "floor_plans",
    "scraped_property_images",
    "scraped_floor_plans",
    "property_images_original",
    "floor_plans_original",
]


def replace_urls_in_value(value):
    """Recursively replace Azure blob URLs with GCS URLs in any value."""
    if isinstance(value, str):
        if OLD_BASE in value:
            return value.replace(OLD_BASE, NEW_BASE), True
        return value, False

    if isinstance(value, list):
        changed = False
        new_list = []
        for item in value:
            new_item, item_changed = replace_urls_in_value(item)
            new_list.append(new_item)
            if item_changed:
                changed = True
        return new_list, changed

    if isinstance(value, dict):
        changed = False
        new_dict = {}
        for k, v in value.items():
            new_v, v_changed = replace_urls_in_value(v)
            new_dict[k] = new_v
            if v_changed:
                changed = True
        return new_dict, changed

    return value, False


def update_collection(db, coll_name, dry_run=False):
    """Update all image URLs in a collection."""
    coll = db[coll_name]

    # Find documents with Azure blob URLs
    query = {"$or": [{f: {"$regex": "blob\\.core\\.windows\\.net"}} for f in IMAGE_FIELDS
                      if coll.find_one({f: {"$exists": True}}, {"_id": 1})]}

    if not query.get("$or"):
        # Try a broader search
        count = coll.count_documents({"$where": "JSON.stringify(this).indexOf('blob.core.windows.net') > -1"})
        if count == 0:
            return 0
        # Fall through to full scan
        docs = coll.find()
    else:
        docs = coll.find(query)

    updated = 0
    for doc in docs:
        new_doc, changed = replace_urls_in_value(doc)
        if changed:
            if not dry_run:
                coll.replace_one({"_id": doc["_id"]}, new_doc)
            updated += 1

    return updated


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()

    client = get_client(fresh=True)

    print(f"{'DRY RUN — ' if args.dry_run else ''}Updating image URLs: Azure Blob → GCS")
    print(f"  Old: {OLD_BASE}")
    print(f"  New: {NEW_BASE}")
    print(f"{'='*60}")

    total_updated = 0

    for db_name in ["Gold_Coast", "Gold_Coast_Currently_For_Sale", "Gold_Coast_Recently_Sold",
                     "Target_Market_Sold_Last_12_Months", "property_data"]:
        db = client[db_name]
        db_updated = 0
        for coll_name in db.list_collection_names():
            count = update_collection(db, coll_name, args.dry_run)
            if count > 0:
                print(f"  {db_name}.{coll_name}: {count} docs updated")
                db_updated += count
        total_updated += db_updated

    print(f"\n{'='*60}")
    print(f"  Total: {total_updated} documents {'would be' if args.dry_run else ''} updated")
    print(f"{'='*60}")

    # Also update the website source code reference
    if not args.dry_run:
        print(f"\n  NOTE: Also update these files manually:")
        print(f"    - Feilds_Website/01_Website/src/root.tsx (preconnect hints)")
        print(f"    - Feilds_Website/01_Website/netlify/functions/monitor/db-validation.mjs")
        print(f"    - scripts/download_images_to_blob.py (future uploads)")

    client.close()


if __name__ == "__main__":
    main()
