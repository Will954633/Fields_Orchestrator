#!/usr/bin/env python3
"""
ensure_indexes.py — declare the indexes Gold_Coast needs, and create any missing.

Idempotent: `create_index` is a no-op when the index already exists, so this is
safe to run any time, and MUST be run after restoring the database from a
backup — indexes created by hand at the mongo shell do not survive a restore,
and their absence is silent. Nothing fails; queries just quietly go back to
scanning the whole collection.

Why these three exist (2026-08-15, see fix-history [MONGOD-SLOW-QUERY-LOG-FLOOD]):
`complex_cms`, `complex_subtype` and `complex_plan` are queried per property by
the appraisal/prewarm builders. Unindexed, each call was a COLLSCAN over the
whole suburb collection (12,096 docs for robina), taking a median 690ms. At
prewarm volume that produced ~18GB/day of "Slow query" lines in
/var/log/mongodb/mongod.log — which is on the root filesystem, so it was
actively eating the disk that had already hit 100% that morning.

⚠ This box's COSMOS_CONNECTION_STRING points at a LOCAL self-hosted mongod
(localhost:27017), not Azure Cosmos. Index builds here are cheap (~1.5s per
index over 12k docs) and do not burn RU.
"""

import os
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from shared.env import load_env  # noqa: E402

# collection -> fields needing a single-field index
REQUIRED = {
    "robina": ["complex_cms", "complex_subtype", "complex_plan"],
    "varsity_lakes": ["complex_cms", "complex_subtype", "complex_plan"],
    "burleigh_waters": ["complex_cms", "complex_subtype", "complex_plan"],
}


def main() -> int:
    load_env()
    from pymongo import MongoClient

    uri = os.environ.get("COSMOS_CONNECTION_STRING")
    if not uri:
        print("ERROR: COSMOS_CONNECTION_STRING not set", file=sys.stderr)
        return 2

    db = MongoClient(uri, serverSelectionTimeoutMS=10000)["Gold_Coast"]
    existing_names = set(db.list_collection_names())
    created = 0
    missing_collections = []

    for coll, fields in REQUIRED.items():
        if coll not in existing_names:
            missing_collections.append(coll)
            continue
        col = db[coll]
        have = {spec["key"][0][0] for spec in col.index_information().values()}
        for field in fields:
            if field in have:
                continue
            t0 = time.time()
            col.create_index(field, name=f"{field}_1")
            created += 1
            print(f"created {coll}.{field}_1 in {time.time() - t0:.2f}s")

    if missing_collections:
        # Don't silently "succeed" against a database that isn't the one we think
        # it is — an empty/renamed collection set means the URI is wrong.
        print(f"ERROR: expected collections absent: {missing_collections}", file=sys.stderr)
        return 1

    print(f"OK — {created} index(es) created, all declared indexes now present.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
