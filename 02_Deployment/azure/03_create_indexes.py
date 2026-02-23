#!/usr/bin/env python3
"""
Azure Cosmos DB Index Creation Script
Last Edit: 07/02/2026, 6:27 PM (Wednesday) - Brisbane Time

Creates indexes on Cosmos DB collections to optimize query performance.
Cosmos DB requires explicit indexes (unlike local MongoDB which auto-indexes).

IMPORTANT: Cosmos DB charges RU/s for index creation. The free tier handles this fine
for our collection sizes, but be aware of RU consumption during index creation.

Cosmos DB MongoDB API Limitations:
- No $graphLookup support
- Compound indexes limited to 8 fields
- Unique indexes must be created on empty collections
- Text indexes not supported (use Azure Cognitive Search instead)
- Wildcard indexes limited

Usage:
    cd /Users/projects/Documents/Fields_Orchestrator/02_Deployment && python3 azure/03_create_indexes.py
"""

import os
import sys
from pathlib import Path
from pymongo import MongoClient, ASCENDING, DESCENDING
from pymongo.errors import OperationFailure

# Load .env file
env_file = Path(__file__).parent.parent / ".env"
if env_file.exists():
    with open(env_file) as f:
        for line in f:
            line = line.strip()
            if line and not line.startswith("#") and "=" in line:
                key, _, value = line.partition("=")
                value = value.strip('"').strip("'")
                os.environ[key.strip()] = value


def get_connection_string():
    """Get Cosmos DB connection string from environment."""
    conn_str = os.environ.get("COSMOS_CONNECTION_STRING", "")
    if not conn_str:
        print("❌ COSMOS_CONNECTION_STRING not set in .env")
        print("   Run: bash azure/02_get_connection_string.sh")
        sys.exit(1)
    return conn_str


def create_index_safe(collection, keys, name=None, unique=False):
    """Create an index, handling Cosmos DB specific errors."""
    try:
        kwargs = {}
        if name:
            kwargs["name"] = name
        if unique:
            kwargs["unique"] = True
        
        collection.create_index(keys, **kwargs)
        key_str = ", ".join([f"{k[0]}:{k[1]}" for k in keys])
        print(f"   ✅ Created index: {name or key_str}")
        return True
    except OperationFailure as e:
        if "already exists" in str(e).lower() or "index already" in str(e).lower():
            print(f"   ℹ️  Index already exists: {name}")
            return True
        else:
            print(f"   ⚠️  Failed to create index {name}: {e}")
            return False
    except Exception as e:
        print(f"   ❌ Error creating index {name}: {e}")
        return False


def setup_property_data_indexes(client):
    """Create indexes for the property_data database."""
    print("\n📦 Database: property_data")
    db = client["property_data"]
    
    # Main properties collection (if it exists or will be created)
    collections_to_index = {
        "properties": [
            ([("address", ASCENDING)], "idx_address", False),
            ([("suburb", ASCENDING)], "idx_suburb", False),
            ([("status", ASCENDING)], "idx_status", False),
            ([("suburb", ASCENDING), ("status", ASCENDING)], "idx_suburb_status", False),
            ([("last_updated", DESCENDING)], "idx_last_updated", False),
            ([("listing_id", ASCENDING)], "idx_listing_id", False),
        ]
    }
    
    for coll_name, indexes in collections_to_index.items():
        print(f"\n   Collection: {coll_name}")
        coll = db[coll_name]
        for keys, name, unique in indexes:
            create_index_safe(coll, keys, name=name, unique=unique)


def setup_gold_coast_for_sale_indexes(client):
    """Create indexes for Gold_Coast_Currently_For_Sale database."""
    print("\n📦 Database: Gold_Coast_Currently_For_Sale")
    db = client["Gold_Coast_Currently_For_Sale"]
    
    # Each suburb is a collection - create common indexes
    # We'll create indexes on a template that applies to all suburb collections
    suburb_indexes = [
        ([("address", ASCENDING)], "idx_address", False),
        ([("price", ASCENDING)], "idx_price", False),
        ([("bedrooms", ASCENDING)], "idx_bedrooms", False),
        ([("property_type", ASCENDING)], "idx_property_type", False),
        ([("listing_id", ASCENDING)], "idx_listing_id", False),
        ([("last_updated", DESCENDING)], "idx_last_updated", False),
        ([("status", ASCENDING)], "idx_status", False),
    ]
    
    # Get existing collections
    existing_collections = db.list_collection_names()
    
    if existing_collections:
        for coll_name in existing_collections:
            if coll_name.startswith("system."):
                continue
            print(f"\n   Collection: {coll_name}")
            coll = db[coll_name]
            for keys, name, unique in suburb_indexes:
                create_index_safe(coll, keys, name=name, unique=unique)
    else:
        print("   ℹ️  No collections yet (will be created during first scrape)")
        print("   ℹ️  Indexes will need to be created after first data import")


def setup_gold_coast_master_indexes(client):
    """Create indexes for Gold_Coast (master) database."""
    print("\n📦 Database: Gold_Coast")
    db = client["Gold_Coast"]
    
    master_indexes = [
        ([("address", ASCENDING)], "idx_address", False),
        ([("suburb", ASCENDING)], "idx_suburb", False),
        ([("sold_date", DESCENDING)], "idx_sold_date", False),
        ([("price", ASCENDING)], "idx_price", False),
        ([("suburb", ASCENDING), ("sold_date", DESCENDING)], "idx_suburb_sold_date", False),
    ]
    
    existing_collections = db.list_collection_names()
    
    if existing_collections:
        for coll_name in existing_collections:
            if coll_name.startswith("system."):
                continue
            print(f"\n   Collection: {coll_name}")
            coll = db[coll_name]
            for keys, name, unique in master_indexes:
                create_index_safe(coll, keys, name=name, unique=unique)
    else:
        print("   ℹ️  No collections yet (will be created during migration/first run)")


def setup_gold_coast_sold_indexes(client):
    """Create indexes for Gold_Coast_Recently_Sold database."""
    print("\n📦 Database: Gold_Coast_Recently_Sold")
    db = client["Gold_Coast_Recently_Sold"]
    
    sold_indexes = [
        ([("address", ASCENDING)], "idx_address", False),
        ([("sold_date", DESCENDING)], "idx_sold_date", False),
        ([("sold_price", ASCENDING)], "idx_sold_price", False),
        ([("suburb", ASCENDING)], "idx_suburb", False),
        ([("status", ASCENDING)], "idx_status", False),
        ([("listing_id", ASCENDING)], "idx_listing_id", False),
    ]
    
    existing_collections = db.list_collection_names()
    
    if existing_collections:
        for coll_name in existing_collections:
            if coll_name.startswith("system."):
                continue
            print(f"\n   Collection: {coll_name}")
            coll = db[coll_name]
            for keys, name, unique in sold_indexes:
                create_index_safe(coll, keys, name=name, unique=unique)
    else:
        print("   ℹ️  No collections yet (will be created during migration/first run)")


def main():
    print("=" * 60)
    print("  Azure Cosmos DB - Index Creation")
    print("=" * 60)
    
    conn_str = get_connection_string()
    
    print(f"\n🔌 Connecting to Cosmos DB...")
    
    try:
        client = MongoClient(
            conn_str,
            serverSelectionTimeoutMS=30000,
            socketTimeoutMS=60000,
            connectTimeoutMS=30000,
            retryWrites=False,  # Cosmos DB requires retryWrites=false
        )
        
        # Test connection
        client.admin.command("ping")
        print("   ✅ Connected to Cosmos DB")
        
    except Exception as e:
        print(f"   ❌ Failed to connect: {e}")
        sys.exit(1)
    
    # Create indexes for each database
    setup_property_data_indexes(client)
    setup_gold_coast_for_sale_indexes(client)
    setup_gold_coast_master_indexes(client)
    setup_gold_coast_sold_indexes(client)
    
    print("\n" + "=" * 60)
    print("  ✅ Index creation complete!")
    print("=" * 60)
    
    client.close()


if __name__ == "__main__":
    main()
