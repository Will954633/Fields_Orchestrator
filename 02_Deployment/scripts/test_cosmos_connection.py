#!/usr/bin/env python3
"""
Azure Cosmos DB Connection Test Script
Last Edit: 07/02/2026, 6:28 PM (Wednesday) - Brisbane Time

Tests connectivity to Azure Cosmos DB (MongoDB API) and verifies
that all required databases are accessible.

Usage:
    cd /Users/projects/Documents/Fields_Orchestrator/02_Deployment && python3 scripts/test_cosmos_connection.py
"""

import os
import sys
import time
from pathlib import Path
from datetime import datetime

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

try:
    from pymongo import MongoClient
    from pymongo.errors import ConnectionFailure, ServerSelectionTimeoutError
except ImportError:
    print("❌ pymongo not installed. Run: pip3 install pymongo")
    sys.exit(1)


def get_connection_string():
    """Get Cosmos DB connection string from environment."""
    conn_str = os.environ.get("COSMOS_CONNECTION_STRING", "")
    if not conn_str:
        print("❌ COSMOS_CONNECTION_STRING not set in .env")
        print("   Run: cd /Users/projects/Documents/Fields_Orchestrator/02_Deployment && bash azure/02_get_connection_string.sh")
        sys.exit(1)
    return conn_str


def test_connection(conn_str):
    """Test basic connectivity to Cosmos DB."""
    print("🔌 Test 1: Basic Connection...")
    
    start = time.time()
    try:
        client = MongoClient(
            conn_str,
            serverSelectionTimeoutMS=30000,
            socketTimeoutMS=60000,
            connectTimeoutMS=30000,
            retryWrites=False,
        )
        
        # Ping the server
        client.admin.command("ping")
        elapsed = time.time() - start
        
        print(f"   ✅ Connected successfully ({elapsed:.2f}s)")
        return client
        
    except ServerSelectionTimeoutError as e:
        print(f"   ❌ Connection timeout: {e}")
        print("   Check: Is your IP allowed in Cosmos DB firewall?")
        print("   Azure Portal → Cosmos DB → Networking → Allow access from all networks")
        return None
    except ConnectionFailure as e:
        print(f"   ❌ Connection failed: {e}")
        return None
    except Exception as e:
        print(f"   ❌ Unexpected error: {e}")
        return None


def test_databases(client):
    """Test that all required databases exist."""
    print("\n📦 Test 2: Database Access...")
    
    required_dbs = [
        "property_data",
        "Gold_Coast_Currently_For_Sale",
        "Gold_Coast",
        "Gold_Coast_Recently_Sold",
    ]
    
    all_ok = True
    for db_name in required_dbs:
        try:
            db = client[db_name]
            # Try to list collections (this verifies database access)
            collections = db.list_collection_names()
            coll_count = len(collections)
            print(f"   ✅ {db_name} - accessible ({coll_count} collections)")
        except Exception as e:
            print(f"   ❌ {db_name} - error: {e}")
            all_ok = False
    
    return all_ok


def test_crud_operations(client):
    """Test basic CRUD operations."""
    print("\n📝 Test 3: CRUD Operations...")
    
    db = client["property_data"]
    test_collection = db["_connection_test"]
    
    # Create
    try:
        test_doc = {
            "test": True,
            "timestamp": datetime.now().isoformat(),
            "source": "connection_test_script",
            "message": "Fields Orchestrator Cosmos DB connection test"
        }
        result = test_collection.insert_one(test_doc)
        print(f"   ✅ INSERT - Document created (id: {result.inserted_id})")
    except Exception as e:
        print(f"   ❌ INSERT failed: {e}")
        return False
    
    # Read
    try:
        found = test_collection.find_one({"test": True})
        if found:
            print(f"   ✅ FIND - Document retrieved")
        else:
            print(f"   ❌ FIND - Document not found")
            return False
    except Exception as e:
        print(f"   ❌ FIND failed: {e}")
        return False
    
    # Update
    try:
        result = test_collection.update_one(
            {"test": True},
            {"$set": {"updated": True, "updated_at": datetime.now().isoformat()}}
        )
        if result.modified_count == 1:
            print(f"   ✅ UPDATE - Document updated")
        else:
            print(f"   ⚠️  UPDATE - No documents modified")
    except Exception as e:
        print(f"   ❌ UPDATE failed: {e}")
        return False
    
    # Delete
    try:
        result = test_collection.delete_one({"test": True})
        if result.deleted_count == 1:
            print(f"   ✅ DELETE - Document deleted")
        else:
            print(f"   ⚠️  DELETE - No documents deleted")
    except Exception as e:
        print(f"   ❌ DELETE failed: {e}")
        return False
    
    # Clean up test collection
    try:
        test_collection.drop()
        print(f"   ✅ CLEANUP - Test collection dropped")
    except Exception as e:
        print(f"   ⚠️  CLEANUP - Could not drop test collection: {e}")
    
    return True


def test_aggregation(client):
    """Test aggregation pipeline support."""
    print("\n📊 Test 4: Aggregation Pipeline...")
    
    db = client["property_data"]
    test_collection = db["_aggregation_test"]
    
    try:
        # Insert test data
        test_docs = [
            {"suburb": "Robina", "price": 1200000, "bedrooms": 4},
            {"suburb": "Robina", "price": 1500000, "bedrooms": 5},
            {"suburb": "Mudgeeraba", "price": 1100000, "bedrooms": 3},
            {"suburb": "Mudgeeraba", "price": 1300000, "bedrooms": 4},
        ]
        test_collection.insert_many(test_docs)
        
        # Run aggregation
        pipeline = [
            {"$group": {
                "_id": "$suburb",
                "avg_price": {"$avg": "$price"},
                "count": {"$sum": 1}
            }},
            {"$sort": {"avg_price": -1}}
        ]
        
        results = list(test_collection.aggregate(pipeline))
        
        if len(results) == 2:
            print(f"   ✅ Aggregation works - {len(results)} groups returned")
            for r in results:
                print(f"      {r['_id']}: avg ${r['avg_price']:,.0f} ({r['count']} properties)")
        else:
            print(f"   ⚠️  Unexpected result count: {len(results)}")
        
        # Clean up
        test_collection.drop()
        print(f"   ✅ CLEANUP - Test collection dropped")
        return True
        
    except Exception as e:
        print(f"   ❌ Aggregation failed: {e}")
        try:
            test_collection.drop()
        except:
            pass
        return False


def test_latency(client):
    """Test read/write latency."""
    print("\n⏱️  Test 5: Latency Check...")
    
    db = client["property_data"]
    test_collection = db["_latency_test"]
    
    # Write latency
    write_times = []
    for i in range(5):
        start = time.time()
        test_collection.insert_one({"test_num": i, "timestamp": datetime.now().isoformat()})
        write_times.append(time.time() - start)
    
    avg_write = sum(write_times) / len(write_times) * 1000
    print(f"   📝 Avg write latency: {avg_write:.0f}ms")
    
    # Read latency
    read_times = []
    for i in range(5):
        start = time.time()
        test_collection.find_one({"test_num": i})
        read_times.append(time.time() - start)
    
    avg_read = sum(read_times) / len(read_times) * 1000
    print(f"   📖 Avg read latency: {avg_read:.0f}ms")
    
    # Clean up
    test_collection.drop()
    
    if avg_write < 100 and avg_read < 50:
        print(f"   ✅ Latency is excellent")
    elif avg_write < 500 and avg_read < 200:
        print(f"   ✅ Latency is acceptable")
    else:
        print(f"   ⚠️  Latency is high - check network/region")
    
    return True


def main():
    print("=" * 60)
    print("  Azure Cosmos DB - Connection Test")
    print(f"  {datetime.now().strftime('%Y-%m-%d %H:%M:%S')} (Brisbane)")
    print("=" * 60)
    
    conn_str = get_connection_string()
    
    # Mask the connection string for display
    if "@" in conn_str:
        masked = conn_str.split("@")[1][:50] + "..."
    else:
        masked = conn_str[:50] + "..."
    print(f"\n🔗 Target: {masked}")
    
    # Run tests
    client = test_connection(conn_str)
    if not client:
        print("\n❌ FAILED - Cannot proceed without connection")
        sys.exit(1)
    
    db_ok = test_databases(client)
    crud_ok = test_crud_operations(client)
    agg_ok = test_aggregation(client)
    latency_ok = test_latency(client)
    
    client.close()
    
    # Summary
    print("\n" + "=" * 60)
    print("  TEST SUMMARY")
    print("=" * 60)
    
    tests = [
        ("Connection", True),
        ("Database Access", db_ok),
        ("CRUD Operations", crud_ok),
        ("Aggregation Pipeline", agg_ok),
        ("Latency", latency_ok),
    ]
    
    all_passed = True
    for name, passed in tests:
        status = "✅ PASS" if passed else "❌ FAIL"
        print(f"  {status} - {name}")
        if not passed:
            all_passed = False
    
    print("")
    if all_passed:
        print("  🎉 ALL TESTS PASSED - Cosmos DB is ready!")
        print("  You can now proceed with data migration.")
    else:
        print("  ⚠️  Some tests failed. Check the errors above.")
    
    print("=" * 60)
    
    sys.exit(0 if all_passed else 1)


if __name__ == "__main__":
    main()
