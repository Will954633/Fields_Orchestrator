#!/usr/bin/env python3
"""
Migrate all data from Azure Cosmos DB to local MongoDB.

Reads every database and collection from Cosmos DB and writes
them into the local MongoDB instance (mongodb://localhost:27017).

Usage:
  python3 scripts/migrate_cosmos_to_local.py
  python3 scripts/migrate_cosmos_to_local.py --db Gold_Coast          # single database
  python3 scripts/migrate_cosmos_to_local.py --dry-run                # count only
"""

import os
import sys
import argparse
import time
from datetime import datetime

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from shared.env import load_env
load_env()

from pymongo import MongoClient
from pymongo.errors import BulkWriteError

COSMOS_URI = os.environ["COSMOS_CONNECTION_STRING"]
LOCAL_URI = "mongodb://localhost:27017"
BATCH_SIZE = 500  # docs per insert_many batch
SKIP_DBS = {"admin", "local", "config"}


def migrate_collection(cosmos_db, local_db, coll_name, dry_run=False):
    """Migrate a single collection from Cosmos to local MongoDB."""
    cosmos_coll = cosmos_db[coll_name]
    count = cosmos_coll.estimated_document_count()

    if count == 0:
        return 0

    if dry_run:
        print(f"    {coll_name}: {count:,} docs (dry run)")
        return count

    local_coll = local_db[coll_name]

    # Drop local collection if it exists (fresh migration)
    local_coll.drop()

    migrated = 0
    batch = []

    for doc in cosmos_coll.find():
        batch.append(doc)
        if len(batch) >= BATCH_SIZE:
            try:
                local_coll.insert_many(batch, ordered=False)
            except BulkWriteError as e:
                # Some docs may have duplicate _ids if re-running
                migrated += e.details.get("nInserted", 0)
                batch = []
                continue
            migrated += len(batch)
            if migrated % 5000 == 0:
                print(f"      ... {migrated:,}/{count:,} docs", flush=True)
            batch = []

    if batch:
        try:
            local_coll.insert_many(batch, ordered=False)
            migrated += len(batch)
        except BulkWriteError as e:
            migrated += e.details.get("nInserted", 0)

    print(f"    {coll_name}: {migrated:,}/{count:,} docs migrated")
    return migrated


def migrate_indexes(cosmos_db, local_db, coll_name):
    """Recreate indexes from Cosmos on local MongoDB."""
    cosmos_coll = cosmos_db[coll_name]
    local_coll = local_db[coll_name]

    for idx_name, idx_info in cosmos_coll.index_information().items():
        if idx_name == "_id_":
            continue  # _id index is automatic
        try:
            keys = idx_info["key"]
            kwargs = {}
            if idx_info.get("unique"):
                kwargs["unique"] = True
            if idx_info.get("sparse"):
                kwargs["sparse"] = True
            local_coll.create_index(keys, name=idx_name, **kwargs)
            print(f"      index: {idx_name} on {keys}")
        except Exception as e:
            print(f"      index {idx_name} FAILED: {e}")


def main():
    parser = argparse.ArgumentParser(description="Migrate Cosmos DB to local MongoDB")
    parser.add_argument("--db", help="Migrate only this database")
    parser.add_argument("--dry-run", action="store_true", help="Count docs only, don't migrate")
    args = parser.parse_args()

    print(f"Connecting to Cosmos DB...")
    cosmos_client = MongoClient(COSMOS_URI)

    print(f"Connecting to local MongoDB...")
    local_client = MongoClient(LOCAL_URI)

    # Verify local is reachable
    local_client.admin.command("ping")
    print(f"Local MongoDB: OK\n")

    db_names = [args.db] if args.db else [
        n for n in cosmos_client.list_database_names() if n not in SKIP_DBS
    ]

    total_docs = 0
    total_colls = 0
    start = time.time()

    for db_name in db_names:
        cosmos_db = cosmos_client[db_name]
        local_db = local_client[db_name]
        colls = cosmos_db.list_collection_names()

        print(f"\n{'='*60}")
        print(f"  Database: {db_name} ({len(colls)} collections)")
        print(f"{'='*60}")

        for coll_name in sorted(colls):
            docs = migrate_collection(cosmos_db, local_db, coll_name, args.dry_run)
            total_docs += docs
            if docs > 0:
                total_colls += 1
                if not args.dry_run:
                    migrate_indexes(cosmos_db, local_db, coll_name)

    elapsed = time.time() - start
    print(f"\n{'='*60}")
    print(f"  MIGRATION {'DRY RUN ' if args.dry_run else ''}COMPLETE")
    print(f"  {total_docs:,} documents across {total_colls} collections")
    print(f"  Time: {elapsed:.0f} seconds ({elapsed/60:.1f} minutes)")
    print(f"{'='*60}\n")

    cosmos_client.close()
    local_client.close()


if __name__ == "__main__":
    main()
