#!/usr/bin/env python3
"""
One-time remediation: populate `complete_address_norm` on all cadastral
property docs across the three suburb collections, then merge any
`cadastral_match=false` standalone docs created by an earlier backfill run
where a real cadastral match exists under normalization.

After running this, the suburb collections have a single canonical doc per
property and URLTracker / ingest_json_to_mongo.py can match on the
normalized field directly.

Safe to re-run.
"""

import re
import sys
from datetime import datetime, timezone
from pymongo import MongoClient, UpdateOne

UTC = timezone.utc
LOCAL_URI = "mongodb://localhost:27017/"
DB_NAME = "Gold_Coast"
SUBURBS = ["robina", "varsity_lakes", "burleigh_waters"]


STREET_ABBREV = {
    "AVE": "AVENUE", "AV": "AVENUE", "RD": "ROAD", "DR": "DRIVE", "DRV": "DRIVE",
    "CT": "COURT", "CRT": "COURT", "PL": "PLACE", "CRES": "CRESCENT", "CR": "CRESCENT",
    "CCT": "CIRCUIT", "CIR": "CIRCUIT", "CCKT": "CIRCUIT", "WY": "WAY",
    "BLVD": "BOULEVARD", "TCE": "TERRACE", "TER": "TERRACE", "HWY": "HIGHWAY",
    "PDE": "PARADE", "CL": "CLOSE", "LN": "LANE", "GR": "GROVE",
}


def normalise(addr: str) -> str:
    """Mirrors url_tracker._normalise_address — see that for full doc."""
    if not addr:
        return ""
    cleaned = re.sub(r"\s+", " ", addr.replace(",", " ").strip().upper())
    tokens = cleaned.split()
    expanded = [
        STREET_ABBREV.get(tok, tok) if 0 < i < len(tokens) - 3 else tok
        for i, tok in enumerate(tokens)
    ]
    return " ".join(expanded)


def main():
    client = MongoClient(LOCAL_URI)
    db = client[DB_NAME]

    for suburb in SUBURBS:
        coll = db[suburb]
        print(f"\n=== {suburb} ===")
        total = coll.count_documents({})
        print(f"  total docs: {total:,}")
        if total == 0:
            continue

        # Step 1 — (re)populate complete_address_norm on ALL docs. Always recompute
        # from complete_address so we overwrite any pre-fix norms that still carry
        # commas. Idempotent.
        print(f"  recomputing complete_address_norm on all docs...")
        batch = []
        cursor = coll.find(
            {},
            {"_id": 1, "complete_address": 1, "complete_address_norm": 1},
            no_cursor_timeout=True,
        )
        recomputed = 0
        for doc in cursor:
            addr = doc.get("complete_address") or ""
            norm = normalise(addr)
            if not norm:
                continue
            if doc.get("complete_address_norm") == norm:
                continue  # already correct
            batch.append(
                UpdateOne({"_id": doc["_id"]}, {"$set": {"complete_address_norm": norm}})
            )
            recomputed += 1
            if len(batch) >= 1000:
                coll.bulk_write(batch, ordered=False)
                batch.clear()
        if batch:
            coll.bulk_write(batch, ordered=False)
        cursor.close()
        print(f"  recomputed {recomputed:,} norm values")

        # Step 2 — for each cadastral_match=false standalone, see if it now
        # collides with a real cadastral doc under the normalized key.
        standalones = list(coll.find({"cadastral_match": False}))
        print(f"  cadastral_match=false standalones: {len(standalones)}")

        merged = 0
        kept_orphans = 0
        for stub in standalones:
            norm = stub.get("complete_address_norm") or normalise(stub.get("complete_address", ""))
            if not norm:
                continue
            # Find a real cadastral doc with same norm (excluding this stub itself)
            real = coll.find_one(
                {"complete_address_norm": norm, "_id": {"$ne": stub["_id"]}, "cadastral_match": {"$ne": False}}
            )
            if not real:
                kept_orphans += 1
                continue

            # Merge — copy listing-related fields from stub onto real, then delete stub.
            update = {k: v for k, v in stub.items() if k not in ("_id", "cadastral_match")}
            # Don't overwrite an existing complete_address with the stub's potentially
            # comma-formatted version — keep the cadastral form.
            update.pop("complete_address", None)
            update["last_updated"] = datetime.now(UTC)
            coll.update_one({"_id": real["_id"]}, {"$set": update})
            coll.delete_one({"_id": stub["_id"]})
            merged += 1

        print(f"  merged into cadastral: {merged}")
        print(f"  still orphaned (no cadastral): {kept_orphans}")

    print("\n=== Done ===")


if __name__ == "__main__":
    main()
