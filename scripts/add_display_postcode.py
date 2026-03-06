#!/usr/bin/env python3
"""
Add display_postcode to all Gold_Coast suburb collections.
==========================================================

Problem: Australia Post postcode boundaries don't align with suburb boundaries.
Robina (suburb) spans postcodes 4226, 4227, 4218, 4213, 4220. The GNAF
cadastral POSTCODE field is the correct mail delivery postcode. Domain.com.au
uses the primary suburb postcode for all listings (e.g. 4226 for all of Robina).

Solution: Add a `display_postcode` field set to the primary/recognised postcode
for the suburb collection. Keep the original POSTCODE untouched.

Usage:
    python add_display_postcode.py                   # all suburbs
    python add_display_postcode.py --suburb robina    # single suburb
    python add_display_postcode.py --dry-run          # preview only
"""

import argparse
import os
import sys
import time
from pymongo import MongoClient
from pymongo.errors import OperationFailure, WriteError

# Primary display postcode for each suburb collection
# Source: Australia Post + Domain.com.au conventions
SUBURB_POSTCODES = {
    "advancetown": "4211",
    "alberton": "4207",
    "arundel": "4214",
    "ashmore": "4214",
    "austinville": "4213",
    "benowa": "4217",
    "biggera_waters": "4216",
    "bilinga": "4225",
    "bonogin": "4213",
    "broadbeach": "4218",
    "broadbeach_waters": "4218",
    "bundall": "4217",
    "burleigh_heads": "4220",
    "burleigh_waters": "4220",
    "carrara": "4211",
    "cedar_creek": "4207",
    "clear_island_waters": "4226",
    "coolangatta": "4225",
    "coombabah": "4216",
    "coomera": "4209",
    "currumbin": "4223",
    "currumbin_valley": "4223",
    "currumbin_waters": "4223",
    "elanora": "4221",
    "gaven": "4211",
    "gilston": "4211",
    "guanaba": "4210",
    "helensvale": "4212",
    "highland_park": "4211",
    "hollywell": "4216",
    "hope_island": "4212",
    "jacobs_well": "4208",
    "kingsholme": "4208",
    "labrador": "4215",
    "lower_beechmont": "4211",
    "luscombe": "4207",
    "main_beach": "4217",
    "maudsland": "4210",
    "mermaid_beach": "4218",
    "mermaid_waters": "4218",
    "merrimac": "4226",
    "miami": "4220",
    "molendinar": "4214",
    "mount_nathan": "4211",
    "mudgeeraba": "4213",
    "natural_bridge": "4211",
    "nerang": "4211",
    "neranwood": "4213",
    "norwell": "4208",
    "numinbah_valley": "4211",
    "ormeau": "4208",
    "ormeau_hills": "4208",
    "oxenford": "4210",
    "pacific_pines": "4211",
    "palm_beach": "4221",
    "paradise_point": "4216",
    "parkwood": "4214",
    "pimpama": "4209",
    "reedy_creek": "4227",
    "robina": "4226",
    "runaway_bay": "4216",
    "southport": "4215",
    "springbrook": "4213",
    "stapylton": "4207",
    "steiglitz": "4207",
    "surfers_paradise": "4217",
    "tallai": "4213",
    "tallebudgera": "4228",
    "tallebudgera_valley": "4228",
    "tugun": "4224",
    "upper_coomera": "4209",
    "varsity_lakes": "4227",
    "willow_vale": "4209",
    "wongawallan": "4210",
    "woongoolba": "4207",
    "worongary": "4213",
    "yatala": "4207",
}


def add_display_postcode(db, suburb: str, postcode: str, dry_run: bool = False) -> dict:
    """Add display_postcode to all docs in a suburb collection."""
    coll = db[suburb]

    # Count docs that need updating (don't already have correct display_postcode)
    needs_update_query = {
        "$or": [
            {"display_postcode": {"$exists": False}},
            {"display_postcode": {"$ne": postcode}},
        ]
    }

    # Count with retry
    count = 0
    for attempt in range(5):
        try:
            count = coll.count_documents(needs_update_query)
            break
        except OperationFailure as e:
            if e.code == 16500 and attempt < 4:
                time.sleep(2 * (attempt + 1))
            else:
                raise

    already_correct = 0
    for attempt in range(5):
        try:
            already_correct = coll.count_documents({"display_postcode": postcode})
            break
        except OperationFailure as e:
            if e.code == 16500 and attempt < 4:
                time.sleep(2 * (attempt + 1))
            else:
                raise

    if dry_run:
        return {
            "suburb": suburb,
            "postcode": postcode,
            "needs_update": count,
            "already_correct": already_correct,
            "updated": 0,
        }

    if count == 0:
        return {
            "suburb": suburb,
            "postcode": postcode,
            "needs_update": 0,
            "already_correct": already_correct,
            "updated": 0,
        }

    # Paginated update — fetch small batches of IDs, update one at a time
    # Cosmos serverless can't handle large finds or batch writes
    updated = 0
    errors = 0
    total_to_process = count
    page_size = 500

    while True:
        # Fetch a page of IDs that still need updating
        batch_ids = []
        for attempt in range(5):
            try:
                batch_ids = [d["_id"] for d in coll.find(needs_update_query, {"_id": 1}).limit(page_size)]
                break
            except (OperationFailure, WriteError) as e:
                code = getattr(e, 'code', None)
                if code == 16500 and attempt < 4:
                    time.sleep(3 * (attempt + 1))
                else:
                    raise

        if not batch_ids:
            break

        for doc_id in batch_ids:
            for attempt in range(6):
                try:
                    coll.update_one(
                        {"_id": doc_id},
                        {"$set": {"display_postcode": postcode}},
                    )
                    updated += 1
                    break
                except (OperationFailure, WriteError) as e:
                    code = getattr(e, 'code', None)
                    if code == 16500 and attempt < 5:
                        time.sleep(1.5 * (attempt + 1))
                    else:
                        errors += 1
                        break

        print(f"    {suburb}: {updated}/{total_to_process} updated ({errors} errors)")
        time.sleep(2)  # breathe between pages

    print(f"    {suburb}: {updated}/{total_to_process} DONE ({errors} errors)")

    return {
        "suburb": suburb,
        "postcode": postcode,
        "needs_update": total_to_process,
        "already_correct": already_correct,
        "updated": updated,
    }


def main():
    parser = argparse.ArgumentParser(description="Add display_postcode to Gold_Coast collections")
    parser.add_argument("--suburb", type=str, help="Process a single suburb only")
    parser.add_argument("--dry-run", action="store_true", help="Preview without writing")
    args = parser.parse_args()

    conn = os.environ.get("COSMOS_CONNECTION_STRING")
    if not conn:
        print("ERROR: COSMOS_CONNECTION_STRING not set")
        sys.exit(1)

    client = MongoClient(conn)
    db = client["Gold_Coast"]

    # Determine which suburbs to process
    if args.suburb:
        if args.suburb not in SUBURB_POSTCODES:
            print(f"ERROR: Unknown suburb '{args.suburb}'. Known: {', '.join(sorted(SUBURB_POSTCODES.keys()))}")
            sys.exit(1)
        suburbs = {args.suburb: SUBURB_POSTCODES[args.suburb]}
    else:
        # Only process collections that actually exist
        existing = set(db.list_collection_names())
        suburbs = {s: pc for s, pc in SUBURB_POSTCODES.items() if s in existing}

    mode = "DRY RUN" if args.dry_run else "LIVE"
    print(f"=== Add display_postcode ({mode}) ===")
    print(f"Suburbs to process: {len(suburbs)}\n")

    total_updated = 0
    total_needed = 0

    for suburb, postcode in sorted(suburbs.items()):
        time.sleep(1)  # rate limit between suburbs
        result = add_display_postcode(db, suburb, postcode, dry_run=args.dry_run)
        total_needed += result["needs_update"]
        total_updated += result["updated"]

        if args.dry_run:
            status = f"needs {result['needs_update']}, already done {result['already_correct']}"
        else:
            status = f"updated {result['updated']}"
        print(f"  {suburb} → {postcode}: {status}")

    print(f"\n=== COMPLETE ===")
    print(f"Total needed: {total_needed}")
    print(f"Total updated: {total_updated}")

    client.close()


if __name__ == "__main__":
    main()
