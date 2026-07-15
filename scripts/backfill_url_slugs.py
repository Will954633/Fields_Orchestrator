#!/usr/bin/env python3
"""
Backfill url_slug on properties that are missing it.
Designed to run after each scrape cycle to catch new properties.
Fast — only queries for documents missing the field.

Usage:
  source /home/fields/venv/bin/activate
  set -a && source /home/fields/Fields_Orchestrator/.env && set +a
  python3 scripts/backfill_url_slugs.py
"""

import os
import re
import sys
import time
from pymongo.errors import WriteError, OperationFailure

REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, REPO_ROOT)

from shared.env import load_env  # type: ignore
from shared.db import get_client, get_db, TARGET_SUBURBS  # type: ignore

load_env()


def clean_address(address):
    sold_match = re.match(r"^Sold\s+(.+?)\s+on\s+\d{1,2}\s+\w+\s+\d{4}\s*-?\s*\d*$", address, re.IGNORECASE)
    if sold_match:
        address = sold_match.group(1)
    address = re.sub(r",?\s+(?:QLD|NSW|VIC|SA|WA|TAS|NT|ACT)\s+\d{4}$", "", address, flags=re.IGNORECASE)
    return address.strip()


def generate_slug(address, suburb):
    address = clean_address(address)
    suburb_lower = suburb.lower().replace("_", " ")
    addr_lower = address.lower()
    addr_lower_stripped = re.sub(r",?\s*" + re.escape(suburb_lower) + r"$", "", addr_lower).strip()
    if addr_lower_stripped != addr_lower:
        address = address[:len(addr_lower_stripped)]
    raw = f"{address} {suburb_lower}".lower()
    raw = raw.replace("/", "-")
    raw = re.sub(r"[^a-z0-9\s-]", "", raw)
    raw = re.sub(r"[\s-]+", "-", raw).strip("-")
    return raw


def main():
    client = get_client()
    db = get_db("Gold_Coast")
    total = 0

    for suburb in TARGET_SUBURBS:
        coll = db[suburb]
        # Only find docs with an address but no url_slug (missing or null)
        cursor = coll.find(
            {"address": {"$exists": True, "$ne": ""}, "$or": [{"url_slug": {"$exists": False}}, {"url_slug": None}]},
            {"address": 1, "full_address": 1, "suburb": 1}
        )
        for doc in cursor:
            address = doc.get("address") or doc.get("full_address") or ""
            doc_suburb = doc.get("suburb") or suburb.replace("_", " ").title()
            if not address:
                continue
            slug = generate_slug(address, doc_suburb)
            if not slug:
                continue
            # Check for duplicate slug (with Cosmos retry)
            existing = None
            for attempt in range(5):
                try:
                    existing = coll.find_one({"url_slug": slug, "_id": {"$ne": doc["_id"]}})
                    break
                except OperationFailure as e:
                    if e.code == 16500:
                        time.sleep(3 * (attempt + 1))
                    else:
                        raise
            if existing:
                slug = f"{slug}-{str(doc['_id'])[-4:]}"
            for attempt in range(5):
                try:
                    coll.update_one({"_id": doc["_id"]}, {"$set": {"url_slug": slug}})
                    break
                except (WriteError, OperationFailure) as e:
                    if getattr(e, 'code', None) == 16500:
                        time.sleep(3 * (attempt + 1))
                    else:
                        raise
            time.sleep(0.3)
            total += 1

    if total > 0:
        print(f"Backfilled {total} url_slugs")
    else:
        print("No new properties need slugs")


if __name__ == "__main__":
    main()
