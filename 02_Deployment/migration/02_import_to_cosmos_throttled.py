#!/usr/bin/env python3
"""
============================================================================
Throttled Import to Azure Cosmos DB (Free Tier Safe)
Last Edit: 07/02/2026, 6:52 PM (Wednesday) - Brisbane Time

This script imports data from local MongoDB to Azure Cosmos DB with
automatic rate-limit handling. Unlike mongorestore which bulk-inserts
too fast for the free tier (1000 RU/s), this script:

  - Inserts documents in small batches (5 at a time)
  - Automatically retries on Error 16500 (rate limit / 429)
  - Uses exponential backoff when throttled
  - Tracks progress and can resume from where it left off
  - Skips collections that are already fully imported

Prerequisites:
  - pymongo installed
  - Local MongoDB running
  - .env file with COSMOS_CONNECTION_STRING set

Usage:
  cd /Users/projects/Documents/Fields_Orchestrator/02_Deployment && python3 migration/02_import_to_cosmos_throttled.py

Options:
  --batch-size N     Documents per batch (default: 5)
  --db DATABASE      Import only this database
  --collection COLL  Import only this collection (requires --db)
  --resume           Skip collections already imported (default: True)
  --drop             Drop existing collections before import
============================================================================
"""

import os
import sys
import time
import json
import argparse
from datetime import datetime
from pathlib import Path

# Load .env
env_file = Path(__file__).parent.parent / '.env'
if env_file.exists():
    with open(env_file) as f:
        for line in f:
            line = line.strip()
            if line and not line.startswith('#') and '=' in line:
                key, _, value = line.partition('=')
                value = value.strip('"').strip("'")
                os.environ[key.strip()] = value

try:
    from pymongo import MongoClient
    from pymongo.errors import BulkWriteError, AutoReconnect, OperationFailure
except ImportError:
    print("❌ pymongo not installed. Run: pip install pymongo")
    sys.exit(1)


# Configuration
LOCAL_MONGO_URI = "mongodb://localhost:27017"
COSMOS_URI = os.environ.get('COSMOS_CONNECTION_STRING', '')

DATABASES = [
    "property_data",
    "Gold_Coast_Currently_For_Sale",
    "Gold_Coast",
    "Gold_Coast_Recently_Sold",
]

# Progress tracking file
PROGRESS_FILE = Path(__file__).parent / 'import_progress.json'


def load_progress():
    """Load import progress from file."""
    if PROGRESS_FILE.exists():
        with open(PROGRESS_FILE) as f:
            return json.load(f)
    return {}


def save_progress(progress):
    """Save import progress to file."""
    with open(PROGRESS_FILE, 'w') as f:
        json.dump(progress, f, indent=2)


def get_progress_key(db_name, coll_name):
    return f"{db_name}.{coll_name}"


def throttled_insert(cosmos_coll, documents, batch_size=5, max_retries=10):
    """
    Insert documents with automatic rate-limit retry.
    Returns (inserted_count, failed_count).
    """
    inserted = 0
    failed = 0
    
    # Process in small batches
    for i in range(0, len(documents), batch_size):
        batch = documents[i:i + batch_size]
        retries = 0
        
        while retries < max_retries:
            try:
                result = cosmos_coll.insert_many(batch, ordered=False)
                inserted += len(result.inserted_ids)
                break
            except BulkWriteError as bwe:
                # Some documents may have been inserted
                n_inserted = bwe.details.get('nInserted', 0)
                inserted += n_inserted
                
                # Check if it's a rate limit error (16500)
                write_errors = bwe.details.get('writeErrors', [])
                rate_limited = any(e.get('code') == 16500 for e in write_errors)
                
                if rate_limited:
                    # Get retry-after hint from error
                    retry_ms = 100  # default
                    for e in write_errors:
                        if 'RetryAfterMs' in str(e):
                            try:
                                import re
                                match = re.search(r'RetryAfterMs=(\d+)', str(e))
                                if match:
                                    retry_ms = max(retry_ms, int(match.group(1)))
                            except:
                                pass
                    
                    # Exponential backoff
                    wait_time = max(retry_ms / 1000.0, 0.5) * (2 ** retries)
                    wait_time = min(wait_time, 30)  # Cap at 30 seconds
                    
                    retries += 1
                    if retries < max_retries:
                        # Rebuild batch with only the failed documents
                        failed_indices = {e['index'] for e in write_errors if e.get('code') == 16500}
                        batch = [batch[idx] for idx in failed_indices if idx < len(batch)]
                        if not batch:
                            break
                        time.sleep(wait_time)
                        continue
                    else:
                        failed += len(batch)
                        break
                else:
                    # Non-rate-limit errors (e.g., duplicate keys) - skip them
                    dup_errors = [e for e in write_errors if e.get('code') != 16500]
                    failed += len(dup_errors)
                    break
                    
            except AutoReconnect:
                retries += 1
                time.sleep(2 * retries)
                continue
            except OperationFailure as e:
                if 'rate' in str(e).lower() or '16500' in str(e) or '429' in str(e):
                    retries += 1
                    time.sleep(2 * retries)
                    continue
                else:
                    failed += len(batch)
                    print(f"      ⚠️  Operation error: {e}")
                    break
    
    return inserted, failed


def import_collection(local_db, cosmos_db, coll_name, batch_size=5, drop=False):
    """Import a single collection with throttling."""
    local_coll = local_db[coll_name]
    cosmos_coll = cosmos_db[coll_name]
    
    # Count documents
    total_docs = local_coll.count_documents({})
    if total_docs == 0:
        return 0, 0, True
    
    # Check if already imported
    cosmos_count = cosmos_coll.count_documents({})
    if cosmos_count >= total_docs and not drop:
        return cosmos_count, 0, True  # Already done
    
    if drop and cosmos_count > 0:
        cosmos_coll.drop()
        cosmos_count = 0
    
    # Read all documents from local
    documents = list(local_coll.find({}))
    
    # If partially imported, skip already-imported docs by _id
    if cosmos_count > 0 and not drop:
        existing_ids = set()
        for doc in cosmos_coll.find({}, {'_id': 1}):
            existing_ids.add(doc['_id'])
        documents = [d for d in documents if d['_id'] not in existing_ids]
        if not documents:
            return cosmos_count, 0, True
    
    # Insert with throttling
    inserted, failed = throttled_insert(cosmos_coll, documents, batch_size)
    
    total_inserted = cosmos_count + inserted
    is_complete = (total_inserted >= total_docs)
    
    return total_inserted, failed, is_complete


def main():
    parser = argparse.ArgumentParser(description='Throttled import to Cosmos DB')
    parser.add_argument('--batch-size', type=int, default=5, help='Documents per batch (default: 5)')
    parser.add_argument('--db', type=str, help='Import only this database')
    parser.add_argument('--collection', type=str, help='Import only this collection')
    parser.add_argument('--drop', action='store_true', help='Drop existing collections before import')
    parser.add_argument('--no-resume', action='store_true', help='Disable resume (re-import everything)')
    args = parser.parse_args()
    
    if not COSMOS_URI:
        print("❌ COSMOS_CONNECTION_STRING not set in .env")
        sys.exit(1)
    
    # Connect to local MongoDB
    print("============================================================")
    print("  Throttled Import to Azure Cosmos DB")
    print(f"  {datetime.now().strftime('%Y-%m-%d %H:%M:%S')} (Brisbane)")
    print("============================================================")
    print()
    print(f"  Batch Size: {args.batch_size} documents")
    print(f"  Drop Mode:  {'Yes' if args.drop else 'No (resume/skip existing)'}")
    print(f"  Rate Limit: Auto-retry with exponential backoff")
    print()
    
    try:
        local_client = MongoClient(LOCAL_MONGO_URI, serverSelectionTimeoutMS=5000)
        local_client.admin.command('ping')
        print("🔗 Local MongoDB: Connected")
    except Exception as e:
        print(f"❌ Cannot connect to local MongoDB: {e}")
        sys.exit(1)
    
    try:
        cosmos_client = MongoClient(COSMOS_URI, serverSelectionTimeoutMS=10000)
        cosmos_client.admin.command('ping')
        print("🔗 Cosmos DB: Connected")
    except Exception as e:
        print(f"❌ Cannot connect to Cosmos DB: {e}")
        sys.exit(1)
    
    print()
    
    # Load progress
    progress = load_progress() if not args.no_resume else {}
    
    # Determine databases to import
    databases = [args.db] if args.db else DATABASES
    
    total_start = time.time()
    grand_inserted = 0
    grand_failed = 0
    grand_skipped = 0
    
    for db_name in databases:
        local_db = local_client[db_name]
        cosmos_db = cosmos_client[db_name]
        
        # Get collections
        if args.collection:
            collections = [args.collection]
        else:
            collections = sorted(local_db.list_collection_names())
        
        if not collections:
            print(f"⚠️  {db_name}: No collections found")
            continue
        
        # Count total docs in this database
        db_total = sum(local_db[c].count_documents({}) for c in collections)
        
        print(f"📦 {db_name} ({len(collections)} collections, {db_total:,} documents)")
        print(f"   {'─' * 50}")
        
        db_inserted = 0
        db_failed = 0
        db_skipped = 0
        
        for i, coll_name in enumerate(collections, 1):
            pkey = get_progress_key(db_name, coll_name)
            local_count = local_db[coll_name].count_documents({})
            
            # Check if already completed
            if pkey in progress and progress[pkey].get('complete') and not args.drop and not args.no_resume:
                db_skipped += local_count
                print(f"   ⏭️  [{i}/{len(collections)}] {coll_name} ({local_count} docs) - already imported")
                continue
            
            print(f"   📝 [{i}/{len(collections)}] {coll_name} ({local_count} docs)...", end='', flush=True)
            
            coll_start = time.time()
            inserted, failed, complete = import_collection(
                local_db, cosmos_db, coll_name, 
                batch_size=args.batch_size, 
                drop=args.drop
            )
            coll_elapsed = time.time() - coll_start
            
            db_inserted += inserted
            db_failed += failed
            
            # Save progress
            progress[pkey] = {
                'complete': complete,
                'inserted': inserted,
                'failed': failed,
                'local_count': local_count,
                'timestamp': datetime.now().isoformat()
            }
            save_progress(progress)
            
            if complete and failed == 0:
                print(f" ✅ {inserted} docs ({coll_elapsed:.1f}s)")
            elif complete:
                print(f" ⚠️  {inserted} ok, {failed} failed ({coll_elapsed:.1f}s)")
            else:
                print(f" ❌ {inserted}/{local_count} ({failed} failed, {coll_elapsed:.1f}s)")
        
        grand_inserted += db_inserted
        grand_failed += db_failed
        grand_skipped += db_skipped
        
        print(f"   {'─' * 50}")
        print(f"   ✅ {db_name}: {db_inserted:,} inserted, {db_failed:,} failed, {db_skipped:,} skipped")
        print()
    
    total_elapsed = time.time() - total_start
    total_minutes = int(total_elapsed / 60)
    total_seconds = int(total_elapsed % 60)
    
    print("============================================================")
    print("  IMPORT SUMMARY")
    print("============================================================")
    print(f"  Total Inserted: {grand_inserted:,}")
    print(f"  Total Failed:   {grand_failed:,}")
    print(f"  Total Skipped:  {grand_skipped:,} (already imported)")
    print(f"  Time:           {total_minutes}m {total_seconds}s")
    print()
    
    if grand_failed > 0:
        print("  ⚠️  Some documents failed. You can re-run this script")
        print("     to retry failed imports (it will resume automatically).")
        print()
        print("  Re-run command:")
        print("    cd /Users/projects/Documents/Fields_Orchestrator/02_Deployment && python3 migration/02_import_to_cosmos_throttled.py")
    else:
        print("  🎉 ALL IMPORTS SUCCESSFUL!")
        print()
        print("  Next Steps:")
        print("    1. Verify: cd /Users/projects/Documents/Fields_Orchestrator/02_Deployment && python3 migration/03_verify_migration.py")
        print("    2. Create indexes: cd /Users/projects/Documents/Fields_Orchestrator/02_Deployment && python3 azure/03_create_indexes.py")
    
    print("============================================================")
    
    # Cleanup
    local_client.close()
    cosmos_client.close()


if __name__ == '__main__':
    main()
