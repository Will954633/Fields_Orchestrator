"""One-shot bulk URL rewrite in MongoDB:
   https://fieldspropertyimages.blob.core.windows.net/property-images/...
   → https://blobs.fieldsestate.com.au/property-images/...

Idempotent (safe to re-run). Walks each affected document, replaces every
string field containing the old host, and persists with replace_one.
Reports per-collection counts and a final summary.

Pass --dry-run to count + show transforms without writing.
"""

from __future__ import annotations

import argparse
import os
import sys
import time
from pathlib import Path
from typing import Any

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT))
from shared.env import load_env  # type: ignore
from pymongo import MongoClient, ReplaceOne

load_env()

OLD = "https://fieldspropertyimages.blob.core.windows.net"
NEW = "https://blobs.fieldsestate.com.au"

DBS = [
    "Gold_Coast",
    "property_data",
    "Target_Market_Sold_Last_12_Months",
    "system_monitor",
]

# Top-level paths/regex match the docs containing OLD anywhere.
MATCH_FIELDS = [
    "property_images",
    "floor_plans",
    "scraped_property_images",
    "scraped_floor_plans",
    "scraped_data.images",
    "scraped_data.images.url",
    "scraped_data.floor_plans",
    "satellite_analysis.satellite_image_url",
    "satellite_image_url",
    "primary_image",
    "thumbnail",
    "image_url",
]

OLD_RE = {"$regex": r"fieldspropertyimages\.blob\.core\.windows\.net"}


def transform(o: Any) -> tuple[Any, int]:
    """Recursively walk; return (new_value, num_replacements)."""
    if isinstance(o, str):
        if OLD in o:
            return (o.replace(OLD, NEW), 1)
        return (o, 0)
    if isinstance(o, dict):
        n = 0
        out = {}
        for k, v in o.items():
            nv, c = transform(v)
            out[k] = nv
            n += c
        return (out, n)
    if isinstance(o, list):
        n = 0
        out = []
        for v in o:
            nv, c = transform(v)
            out.append(nv)
            n += c
        return (out, n)
    return (o, 0)


def process_collection(coll, dry_run: bool, batch_size: int = 500) -> tuple[int, int, int]:
    """Returns (matched_docs, modified_docs, total_string_replacements)."""
    q = {"$or": [{f: OLD_RE} for f in MATCH_FIELDS]}
    matched = 0
    modified = 0
    replacements = 0
    batch: list[ReplaceOne] = []
    cursor = coll.find(q, no_cursor_timeout=True)
    try:
        for doc in cursor:
            matched += 1
            new_doc, n = transform(doc)
            if n == 0:
                continue
            replacements += n
            modified += 1
            if dry_run:
                continue
            batch.append(ReplaceOne({"_id": doc["_id"]}, new_doc))
            if len(batch) >= batch_size:
                coll.bulk_write(batch, ordered=False)
                batch = []
        if batch:
            coll.bulk_write(batch, ordered=False)
    finally:
        cursor.close()
    return matched, modified, replacements


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--db", help="Limit to one database")
    args = ap.parse_args()

    client = MongoClient(os.environ["MONGODB_URI"])
    overall_matched = 0
    overall_modified = 0
    overall_replacements = 0
    t_start = time.time()

    for db_name in DBS:
        if args.db and db_name != args.db:
            continue
        db = client[db_name]
        db_t0 = time.time()
        db_matched = db_modified = db_repl = 0
        affected = 0
        for coll_name in db.list_collection_names():
            coll = db[coll_name]
            try:
                m, mod, r = process_collection(coll, args.dry_run)
            except Exception as e:
                print(f"  ! {db_name}.{coll_name}: {e}", flush=True)
                continue
            if m:
                affected += 1
                db_matched += m; db_modified += mod; db_repl += r
                print(f"  {db_name}.{coll_name}: matched={m:,} modified={mod:,} replacements={r:,}", flush=True)
        if db_matched:
            print(f"=== {db_name}: matched={db_matched:,} modified={db_modified:,} replacements={db_repl:,} in {len(db.list_collection_names())} collections ({affected} affected) | {time.time()-db_t0:.1f}s ===", flush=True)
            overall_matched += db_matched
            overall_modified += db_modified
            overall_replacements += db_repl

    mode = "DRY-RUN" if args.dry_run else "APPLIED"
    print(f"\n{mode}  matched={overall_matched:,}  modified={overall_modified:,}  replacements={overall_replacements:,}  in {time.time()-t_start:.1f}s")
    return 0


if __name__ == "__main__":
    sys.exit(main())
