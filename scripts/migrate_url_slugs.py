#!/usr/bin/env python3
"""
Backfill url_slug field on all properties in the Gold_Coast database.

Generates SEO-friendly slugs from address + suburb, e.g.:
  "49 Dixon Street" + "Robina" → "49-dixon-street-robina"
  "Unit 3/17 Palm Avenue" + "Burleigh Waters" → "unit-3-17-palm-avenue-burleigh-waters"

Creates an index on url_slug for each suburb collection.

Usage:
  source /home/fields/venv/bin/activate
  set -a && source /home/fields/Fields_Orchestrator/.env && set +a
  python3 scripts/migrate_url_slugs.py [--dry-run]
"""

import os
import re
import sys
import time
from pymongo import MongoClient
from pymongo.errors import WriteError

DRY_RUN = "--dry-run" in sys.argv

TARGET_SUBURBS = [
    "robina", "burleigh_waters", "varsity_lakes",
    "burleigh_heads", "mudgeeraba", "reedy_creek",
    "merrimac", "worongary", "carrara",
]


def clean_address(address: str) -> str:
    """Clean raw address: strip sold prefixes, state/postcode suffixes."""
    # Strip "Sold <address> on DD Mon YYYY - XXXXXXXXXX" wrapper
    sold_match = re.match(r"^Sold\s+(.+?)\s+on\s+\d{1,2}\s+\w+\s+\d{4}\s*-?\s*\d*$", address, re.IGNORECASE)
    if sold_match:
        address = sold_match.group(1)
    # Strip trailing ", QLD XXXX" or ", NSW XXXX" etc.
    address = re.sub(r",?\s+(?:QLD|NSW|VIC|SA|WA|TAS|NT|ACT)\s+\d{4}$", "", address, flags=re.IGNORECASE)
    return address.strip()


def generate_slug(address: str, suburb: str) -> str:
    """Generate a URL-safe slug from address + suburb.

    If the address already ends with the suburb name, don't duplicate it.
    Output: "49-dixon-street-robina" (not "49-dixon-street-robina-robina")
    """
    address = clean_address(address)

    # Strip trailing suburb name if address already contains it (e.g. "28 Federal Place, Robina")
    suburb_lower = suburb.lower().replace("_", " ")
    addr_lower = address.lower()
    # Remove trailing ", Suburb" or just "Suburb" at end
    addr_lower_stripped = re.sub(r",?\s*" + re.escape(suburb_lower) + r"$", "", addr_lower).strip()
    if addr_lower_stripped != addr_lower:
        address = address[:len(addr_lower_stripped)]

    raw = f"{address} {suburb_lower}".lower()
    # Replace / with - (for unit addresses like "3/17 Palm Ave")
    raw = raw.replace("/", "-")
    # Keep only alphanumeric, spaces, and hyphens
    raw = re.sub(r"[^a-z0-9\s-]", "", raw)
    # Collapse whitespace and hyphens into single hyphens
    raw = re.sub(r"[\s-]+", "-", raw).strip("-")
    return raw


def main():
    uri = os.environ.get("COSMOS_CONNECTION_STRING")
    if not uri:
        print("ERROR: COSMOS_CONNECTION_STRING not set")
        sys.exit(1)

    client = MongoClient(uri)
    db = client["Gold_Coast"]

    total_updated = 0
    total_skipped = 0
    duplicates = []

    for suburb in TARGET_SUBURBS:
        coll = db[suburb]
        count = coll.count_documents({})
        print(f"\n{'='*60}")
        print(f"Collection: {suburb} ({count} documents)")
        print(f"{'='*60}")

        # Track slugs within this collection for uniqueness
        slug_counts = {}
        updated = 0
        skipped = 0

        for doc in coll.find({}, {"address": 1, "full_address": 1, "suburb": 1}):
            address = doc.get("address") or doc.get("full_address") or ""
            doc_suburb = doc.get("suburb") or suburb.replace("_", " ").title()

            if not address:
                skipped += 1
                continue

            slug = generate_slug(address, doc_suburb)

            if not slug:
                skipped += 1
                continue

            # Handle duplicates by appending a suffix
            if slug in slug_counts:
                slug_counts[slug] += 1
                original_slug = slug
                slug = f"{slug}-{slug_counts[slug]}"
                duplicates.append(f"  {suburb}: {original_slug} → {slug}")
            else:
                slug_counts[slug] = 0

            if DRY_RUN:
                print(f"  [DRY RUN] {address} → {slug}")
            else:
                for attempt in range(5):
                    try:
                        coll.update_one(
                            {"_id": doc["_id"]},
                            {"$set": {"url_slug": slug}}
                        )
                        break
                    except WriteError as e:
                        if e.code == 16500:
                            wait = 3 * (attempt + 1)
                            print(f"    Rate limited, waiting {wait}s...")
                            time.sleep(wait)
                        else:
                            raise
                time.sleep(0.3)  # Throttle between writes

            updated += 1

        if not DRY_RUN:
            # Create index on url_slug
            for attempt in range(5):
                try:
                    coll.create_index("url_slug", unique=True, sparse=True)
                    print(f"  Created index on url_slug")
                    break
                except Exception as e:
                    if "16500" in str(e) or "429" in str(e):
                        time.sleep(5 * (attempt + 1))
                    else:
                        print(f"  Warning: index creation failed: {e}")
                        break

        total_updated += updated
        total_skipped += skipped
        print(f"  Updated: {updated}, Skipped: {skipped}")

    print(f"\n{'='*60}")
    print(f"TOTAL — Updated: {total_updated}, Skipped: {total_skipped}")
    if duplicates:
        print(f"\nDuplicate slugs resolved ({len(duplicates)}):")
        for d in duplicates:
            print(d)
    if DRY_RUN:
        print("\n⚠️  DRY RUN — no changes made. Remove --dry-run to apply.")


if __name__ == "__main__":
    main()
