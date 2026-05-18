#!/usr/bin/env python3
"""Normalise Robina cadastral POSTCODE to 4226 (Domain's canonical postcode).

Background: Robina's cadastral baseline carries Australia Post delivery
postcodes which split across 4226/4227/4218/4213/4220 (suburb edges + golf
estates). Domain's property-profile URL pattern always uses `qld-4226` for
Robina, so cadastral records with non-4226 postcodes generate 404 URLs and
get flagged scraped_v2_failed_at='parse'. A test of 3 such records
(703 Glades Dr 4213, 2 Pearwood Ln 4227, 839 Legend Trail 4213) showed
Domain's profile pages exist when retried with 4226.

Fully reversible: original POSTCODE preserved in `POSTCODE_original_cadastral`.

Run:
    python3 scripts/fix_robina_postcodes.py --dry-run   # preview
    python3 scripts/fix_robina_postcodes.py             # apply
    python3 scripts/fix_robina_postcodes.py --revert    # restore originals
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

SUBURB = "robina"
TARGET_POSTCODE = "4226"
WRONG_POSTCODES = ["4213", "4218", "4220", "4227"]


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--dry-run", action="store_true", help="Preview without writing")
    ap.add_argument("--revert", action="store_true", help="Restore POSTCODE from sidecar")
    args = ap.parse_args()

    client = get_client()
    coll = client["Gold_Coast"][SUBURB]

    if args.revert:
        return revert(coll, args.dry_run)
    return apply(coll, args.dry_run)


def apply(coll, dry_run: bool) -> int:
    """Set POSTCODE=4226 wherever LOCALITY=ROBINA and POSTCODE in WRONG_POSTCODES.
    Preserves original. Idempotent (skips records already normalised)."""
    # Scope: cadastral records where LOCALITY=ROBINA and POSTCODE is wrong
    # AND we haven't already normalised this one.
    query = {
        "LOCALITY": "ROBINA",
        "POSTCODE": {"$in": WRONG_POSTCODES},
        "POSTCODE_original_cadastral": {"$exists": False},
    }
    candidates = coll.count_documents(query)
    print(f"Eligible records: {candidates}")

    # Per-postcode breakdown for sanity
    for pc in WRONG_POSTCODES:
        c = coll.count_documents({**query, "POSTCODE": pc})
        print(f"  POSTCODE={pc}: {c}")

    # How many of these are currently flagged v2-failed?
    v2_failed = coll.count_documents({**query, "scraped_v2_failed_at": {"$exists": True, "$ne": None}})
    print(f"  Of which v2-failed (would re-queue): {v2_failed}")

    if dry_run:
        # Show 5 sample records
        print("\nSample records (5):")
        for d in coll.find(query, {
            "_id": 1, "STREET_NO_1": 1, "STREET_NAME": 1, "STREET_TYPE": 1, "POSTCODE": 1,
            "scraped_v2_failed_reason": 1,
        }).limit(5):
            no = d.get("STREET_NO_1"); nm = d.get("STREET_NAME"); tp = d.get("STREET_TYPE")
            pc = d.get("POSTCODE"); fr = d.get("scraped_v2_failed_reason") or "-"
            print(f"  {d['_id']} | {no} {nm} {tp} ROBINA QLD {pc} | v2_failed={fr}")
        print("\n(Dry run — no writes. Re-run without --dry-run to apply.)")
        return 0

    # Apply: write in a single updateMany. Mongo handles this efficiently.
    # We also clear scraped_v2_failed_at + reason so the scraper sees a fresh slate.
    now = dt.datetime.utcnow()
    print(f"\nApplying update to {candidates} records...")
    # Stamp POSTCODE_original_cadastral per-doc (we can't use $set with $POSTCODE
    # in basic updateMany — use aggregation pipeline update).
    result = coll.update_many(
        query,
        [
            {"$set": {
                "POSTCODE_original_cadastral": "$POSTCODE",
                "POSTCODE": TARGET_POSTCODE,
                "postcode_normalised_at": now,
                "postcode_normalised_reason": "domain_url_compat_robina",
            }},
            {"$unset": ["scraped_v2_failed_at", "scraped_v2_failed_reason"]},
        ],
    )
    print(f"  matched={result.matched_count}  modified={result.modified_count}")

    # Post-check
    normalised = coll.count_documents({"LOCALITY": "ROBINA", "POSTCODE_original_cadastral": {"$exists": True}})
    still_wrong = coll.count_documents({"LOCALITY": "ROBINA", "POSTCODE": {"$in": WRONG_POSTCODES}})
    new_robina = coll.count_documents({"LOCALITY": "ROBINA", "POSTCODE": TARGET_POSTCODE})
    print(f"\nPost-state:")
    print(f"  Normalised (sidecar set):     {normalised}")
    print(f"  Still wrong postcode:         {still_wrong}")
    print(f"  POSTCODE=4226 (Robina total): {new_robina}")
    return 0


def revert(coll, dry_run: bool) -> int:
    """Restore POSTCODE from POSTCODE_original_cadastral sidecar."""
    query = {
        "LOCALITY": "ROBINA",
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
