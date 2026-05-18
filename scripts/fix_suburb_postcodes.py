#!/usr/bin/env python3
"""Normalise cadastral POSTCODE to a suburb's canonical postcode for Domain URLs.

Background: cadastral baseline carries Australia Post delivery postcodes which
can split across adjacent suburb codes (golf estates, suburb edges). Domain's
property-profile URL pattern uses a single canonical postcode per locality, so
cadastral records with the wrong postcode generate 404 URLs and get flagged
scraped_v2_failed_at='parse'. This script normalises POSTCODE for a given
suburb, preserving the original in `POSTCODE_original_cadastral`.

Validated on Robina 2026-05-18 (CA-003) — 3,268 records normalised, 1,766
subsequently re-scraped successfully.

Suburb config table below maps each known target suburb to its canonical
postcode and the set of "wrong" postcodes seen in cadastral data.

Run:
    python3 scripts/fix_suburb_postcodes.py --suburb burleigh_waters --dry-run
    python3 scripts/fix_suburb_postcodes.py --suburb burleigh_waters
    python3 scripts/fix_suburb_postcodes.py --suburb burleigh_waters --revert
"""

from __future__ import annotations

import argparse
import datetime as dt
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT))

from shared.env import load_env  # type: ignore
from shared.db import get_client  # type: ignore

load_env()

# Suburb → (canonical postcode, wrong postcodes observed in cadastral data)
# Mongo `LOCALITY` is uppercase; collection is lowercase_with_underscores.
SUBURB_CONFIG: dict[str, dict] = {
    "robina": {
        "locality": "ROBINA",
        "canonical": "4226",
        "wrong": ["4213", "4218", "4220", "4227"],
    },
    "burleigh_waters": {
        "locality": "BURLEIGH WATERS",
        "canonical": "4220",
        # Observed in 2026-05-19 survey: 299 records on 4227 (Varsity edge)
        "wrong": ["4227"],
    },
    "varsity_lakes": {
        "locality": "VARSITY LAKES",
        "canonical": "4227",
        # Observed in 2026-05-19 survey: 543 on 4220 (Burleigh edge),
        # 48 on 2603 (likely owner residential), 20 on 4226 (Robina edge),
        # plus a long tail of NSW/VIC postcodes from data-entry errors.
        # Restrict to the geographic-edge codes only — NSW/VIC are noise.
        "wrong": ["4220", "4226", "4218"],
    },
}


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--suburb", required=True, choices=list(SUBURB_CONFIG.keys()),
                    help="Target suburb (collection name)")
    ap.add_argument("--dry-run", action="store_true", help="Preview without writing")
    ap.add_argument("--revert", action="store_true", help="Restore POSTCODE from sidecar")
    args = ap.parse_args()

    config = SUBURB_CONFIG[args.suburb]
    client = get_client()
    coll = client["Gold_Coast"][args.suburb]

    if args.revert:
        return revert(coll, config, args.dry_run)
    return apply(coll, config, args.suburb, args.dry_run)


def apply(coll, config: dict, suburb: str, dry_run: bool) -> int:
    locality = config["locality"]
    canonical = config["canonical"]
    wrong = config["wrong"]

    query = {
        "LOCALITY": locality,
        "POSTCODE": {"$in": wrong},
        "POSTCODE_original_cadastral": {"$exists": False},
    }
    candidates = coll.count_documents(query)
    print(f"Suburb: {suburb} (LOCALITY={locality}, canonical={canonical})")
    print(f"Eligible records: {candidates}")

    for pc in wrong:
        c = coll.count_documents({**query, "POSTCODE": pc})
        print(f"  POSTCODE={pc}: {c}")

    v2_failed = coll.count_documents({**query, "scraped_v2_failed_at": {"$exists": True, "$ne": None}})
    print(f"  Of which v2-failed (would re-queue): {v2_failed}")

    if dry_run:
        print("\nSample records (5):")
        for d in coll.find(query, {
            "_id": 1, "STREET_NO_1": 1, "STREET_NAME": 1, "STREET_TYPE": 1,
            "POSTCODE": 1, "scraped_v2_failed_reason": 1,
        }).limit(5):
            no = d.get("STREET_NO_1"); nm = d.get("STREET_NAME"); tp = d.get("STREET_TYPE")
            pc = d.get("POSTCODE"); fr = d.get("scraped_v2_failed_reason") or "-"
            print(f"  {d['_id']} | {no} {nm} {tp} {locality} QLD {pc} | v2_failed={fr}")
        print("\n(Dry run — no writes. Re-run without --dry-run to apply.)")
        return 0

    now = dt.datetime.utcnow()
    print(f"\nApplying update to {candidates} records...")
    result = coll.update_many(
        query,
        [
            {"$set": {
                "POSTCODE_original_cadastral": "$POSTCODE",
                "POSTCODE": canonical,
                "postcode_normalised_at": now,
                "postcode_normalised_reason": f"domain_url_compat_{suburb}",
            }},
            {"$unset": ["scraped_v2_failed_at", "scraped_v2_failed_reason"]},
        ],
    )
    print(f"  matched={result.matched_count}  modified={result.modified_count}")

    normalised = coll.count_documents({"LOCALITY": locality, "POSTCODE_original_cadastral": {"$exists": True}})
    still_wrong = coll.count_documents({"LOCALITY": locality, "POSTCODE": {"$in": wrong}})
    new_canon = coll.count_documents({"LOCALITY": locality, "POSTCODE": canonical})
    print("\nPost-state:")
    print(f"  Normalised (sidecar set):     {normalised}")
    print(f"  Still wrong postcode:         {still_wrong}")
    print(f"  POSTCODE={canonical} ({suburb} total): {new_canon}")
    return 0


def revert(coll, config: dict, dry_run: bool) -> int:
    locality = config["locality"]
    query = {
        "LOCALITY": locality,
        "POSTCODE_original_cadastral": {"$exists": True},
    }
    n = coll.count_documents(query)
    print(f"Records to revert: {n}")
    if dry_run:
        print("(Dry run — no writes.)")
        return 0
    result = coll.update_many(
        query,
        [
            {"$set": {"POSTCODE": "$POSTCODE_original_cadastral"}},
            {"$unset": ["POSTCODE_original_cadastral", "postcode_normalised_at", "postcode_normalised_reason"]},
        ],
    )
    print(f"  matched={result.matched_count}  modified={result.modified_count}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
