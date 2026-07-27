#!/usr/bin/env python3
"""
Backfill url_slug on off-market addresses in the 3 core suburbs that don't
have one yet (~10K of 27K), so every off-market address the owner-lookup
funnel or a Google search resolves to a real page instead of a 404.

Deliberately NARROWER and SAFER than migrate_url_slugs.py:
  - Only the 3 core suburbs (robina, varsity_lakes, burleigh_waters), not all 9.
  - Only docs WHERE url_slug is missing — never touches/regenerates a slug that
    already exists, so already-live/paid/indexed pages never change out from
    under a customer or a Google-crawled URL.
  - Loads EXISTING slugs in each collection first, so new slugs can't collide
    with ones already live (migrate_url_slugs.py only dedupes within its own run).

Reuses generate_slug()/clean_address() from migrate_url_slugs.py so the output
matches the existing convention (and the frontend's slugify.ts) exactly.

Usage:
  source /home/fields/venv/bin/activate
  set -a && source /home/fields/Fields_Orchestrator/.env && set +a
  python3 scripts/backfill_offmarket_slugs.py [--dry-run]
"""

import os
import sys
import time

sys.path.insert(0, os.path.dirname(__file__))
from migrate_url_slugs import generate_slug  # noqa: E402

from pymongo import MongoClient
from pymongo.errors import WriteError

DRY_RUN = "--dry-run" in sys.argv
CORE_SUBURBS = ["robina", "varsity_lakes", "burleigh_waters"]


def main():
    uri = os.environ.get("COSMOS_CONNECTION_STRING")
    if not uri:
        print("ERROR: COSMOS_CONNECTION_STRING not set")
        sys.exit(1)

    client = MongoClient(uri, retryWrites=False)
    db = client["Gold_Coast"]

    grand_total_updated = 0

    for suburb in CORE_SUBURBS:
        coll = db[suburb]

        # Existing slugs — the dedup set new slugs must not collide with.
        existing_slugs = set(
            d["url_slug"] for d in coll.find(
                {"url_slug": {"$exists": True, "$ne": None}}, {"url_slug": 1}
            )
        )
        missing = list(coll.find(
            {"url_slug": {"$exists": False}},
            {"address": 1, "full_address": 1, "complete_address": 1, "suburb": 1, "LOCALITY": 1},
        ))

        print(f"\n{'='*60}")
        print(f"{suburb}: {len(missing)} missing url_slug ({len(existing_slugs)} already set)")
        print(f"{'='*60}")

        updated = skipped = 0
        for doc in missing:
            # Enriched docs use address/full_address; bare cadastral records
            # (the thinnest tier — geocode + lot only) use ALL-CAPS complete_address.
            address = doc.get("address") or doc.get("full_address") or doc.get("complete_address") or ""
            doc_suburb = doc.get("suburb") or doc.get("LOCALITY") or suburb.replace("_", " ").title()

            if not address:
                skipped += 1
                continue

            slug = generate_slug(address, doc_suburb)
            if not slug:
                skipped += 1
                continue

            # Dedup against EVERY existing slug in the collection, not just this run.
            if slug in existing_slugs:
                base = slug
                n = 2
                while f"{base}-{n}" in existing_slugs:
                    n += 1
                slug = f"{base}-{n}"
            existing_slugs.add(slug)

            if DRY_RUN:
                print(f"  [DRY RUN] {address} -> {slug}")
            else:
                for attempt in range(5):
                    try:
                        coll.update_one({"_id": doc["_id"]}, {"$set": {"url_slug": slug}})
                        break
                    except WriteError as e:
                        if e.code == 16500:
                            wait = 3 * (attempt + 1)
                            print(f"    rate limited, waiting {wait}s...")
                            time.sleep(wait)
                        else:
                            raise
                time.sleep(0.05)
            updated += 1

        print(f"  {suburb}: {'would update' if DRY_RUN else 'updated'} {updated}, skipped {skipped} (no address)")
        grand_total_updated += updated

    print(f"\n{'='*60}")
    print(f"TOTAL: {'would update' if DRY_RUN else 'updated'} {grand_total_updated} url_slugs across 3 core suburbs")
    print(f"{'='*60}")


if __name__ == "__main__":
    main()
