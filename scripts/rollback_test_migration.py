#!/usr/bin/env python3
"""
Rollback Test Migration
Restores from backup and removes incorrectly created collections
"""

import os
from pymongo import MongoClient

MONGODB_URI = os.getenv('MONGODB_URI', 'mongodb://127.0.0.1:27017/')
DATABASE_NAME = 'Gold_Coast_Currently_For_Sale'

client = MongoClient(MONGODB_URI)
db = client[DATABASE_NAME]

print("Rolling back test migration...")

# Collections that were incorrectly created
wrong_collections = ['waters', 'creek', 'lakes', 'robina', 'mudgeeraba']

# Restore from backup
backup_name = 'Gold_Coast_Recently_Sold_backup_20260217_120516'
if backup_name in db.list_collection_names():
    print(f"\n1. Restoring Gold_Coast_Recently_Sold from {backup_name}")

    # Drop current collection
    db['Gold_Coast_Recently_Sold'].drop()

    # Restore from backup
    backup_docs = list(db[backup_name].find({'_backup_metadata': {'$exists': False}}))
    if backup_docs:
        db['Gold_Coast_Recently_Sold'].insert_many(backup_docs)
        print(f"   ✓ Restored {len(backup_docs)} documents")
else:
    print(f"⚠️  Backup {backup_name} not found")

# Remove incorrectly created collections
print(f"\n2. Removing incorrectly created collections:")
for coll in wrong_collections:
    if coll in db.list_collection_names():
        count = db[coll].count_documents({})
        db[coll].drop()
        print(f"   ✓ Dropped '{coll}' collection ({count} docs)")

# Remove backup
if backup_name in db.list_collection_names():
    db[backup_name].drop()
    print(f"\n3. Removed backup: {backup_name}")

print("\n✅ Rollback complete!")

client.close()
