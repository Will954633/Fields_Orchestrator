#!/usr/bin/env python3
"""
Add display_postcode to all Gold_Coast suburb collections.
==========================================================

Problem: Australia Post postcode boundaries don't align with suburb boundaries.
The GNAF cadastral POSTCODE field is the correct mail delivery postcode but
Domain.com.au uses the primary suburb postcode for all listings.

Solution: Add a `display_postcode` field set to the primary postcode for the
suburb. Keep the original POSTCODE untouched.

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
    """Add display_postcode to all docs in a suburb collection using paginated updates."""
    coll = db[suburb]

    query = {"display_postcode": {"$ne": postcode}}

    if dry_run:
        # Just check if any docs need updating
        for attempt in range(5):
            try:
                sample = coll.find_one(query, {"_id": 1})
                needs = "yes" if sample else "no"
                break
            except OperationFailure as e:
                if e.code == 16500 and attempt < 4:
                    time.sleep(2 * (attempt + 1))
                else:
                    raise
        return {"suburb": suburb, "postcode": postcode, "needs_update": needs, "updated": 0}

    # Paginated update: fetch 500 IDs at a time, update one-by-one
    updated = 0
    errors = 0
    page = 0

    while True:
        page += 1
        batch_ids = []
        for attempt in range(5):
            try:
                batch_ids = [d["_id"] for d in coll.find(query, {"_id": 1}).limit(500)]
                break
            except OperationFailure as e:
                if e.code == 16500 and attempt < 4:
                    time.sleep(3 * (attempt + 1))
                else:
                    raise

        if not batch_ids:
            break

        for doc_id in batch_ids:
            for attempt in range(6):
                try:
                    coll.update_one({"_id": doc_id}, {"$set": {"display_postcode": postcode}})
                    updated += 1
                    break
                except (OperationFailure, WriteError) as e:
                    code = getattr(e, 'code', None)
                    if code == 16500 and attempt < 5:
                        time.sleep(1.5 * (attempt + 1))
                    else:
                        errors += 1
                        break

        print(f"    {suburb}: page {page}, {updated} updated ({errors} errors)")
        time.sleep(2)

    return {"suburb": suburb, "postcode": postcode, "needs_update": updated + errors, "updated": updated, "errors": errors}


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

    if args.suburb:
        if args.suburb not in SUBURB_POSTCODES:
            print(f"ERROR: Unknown suburb '{args.suburb}'")
            sys.exit(1)
        suburbs = {args.suburb: SUBURB_POSTCODES[args.suburb]}
    else:
        existing = set(db.list_collection_names())
        suburbs = {s: pc for s, pc in SUBURB_POSTCODES.items() if s in existing}

    mode = "DRY RUN" if args.dry_run else "LIVE"
    print(f"=== Add display_postcode ({mode}) ===")
    print(f"Suburbs: {len(suburbs)}\n")

    total_updated = 0
    total_errors = 0

    for suburb, postcode in sorted(suburbs.items()):
        time.sleep(1)
        print(f"  {suburb} → {postcode}")
        result = add_display_postcode(db, suburb, postcode, dry_run=args.dry_run)
        total_updated += result["updated"]
        total_errors += result.get("errors", 0)

        if args.dry_run:
            print(f"    needs update: {result['needs_update']}")
        else:
            print(f"    DONE: {result['updated']} updated, {result.get('errors', 0)} errors")

    print(f"\n=== COMPLETE ===")
    print(f"Total updated: {total_updated}")
    print(f"Total errors: {total_errors}")

    client.close()


if __name__ == "__main__":
    main()
