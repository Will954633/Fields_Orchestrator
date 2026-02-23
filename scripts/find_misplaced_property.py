#!/usr/bin/env python3
"""
Find Misplaced Property - Diagnostic Script
Created: 2026-02-17

Searches for the property mentioned in the bug report across all collections.
"""

import os
from pymongo import MongoClient

# MongoDB configuration
MONGODB_URI = os.getenv('MONGODB_URI', 'mongodb://127.0.0.1:27017/')
DATABASE_NAME = 'Gold_Coast_Currently_For_Sale'

def find_property():
    """Search for the property across all collections"""
    client = MongoClient(MONGODB_URI)
    db = client[DATABASE_NAME]

    print("=" * 80)
    print("SEARCHING FOR MISPLACED PROPERTY")
    print("=" * 80)

    # Get all collections
    collections = db.list_collection_names()
    print(f"\nFound {len(collections)} collections in {DATABASE_NAME}")

    # Search for properties in Robina across all collections
    search_terms = [
        "48 Peach Drive, Robina",
        "Peach Drive",
        "Robina",
    ]

    print("\n" + "=" * 80)
    print("SEARCH RESULTS")
    print("=" * 80)

    for coll_name in sorted(collections):
        coll = db[coll_name]

        # Search for addresses containing "Peach Drive" or "Robina"
        for term in ["Peach Drive", "48 Peach"]:
            docs = list(coll.find({"address": {"$regex": term, "$options": "i"}}).limit(10))

            if docs:
                print(f"\n📍 Collection: {coll_name}")
                print(f"   Found {len(docs)} properties matching '{term}':")
                for doc in docs:
                    print(f"   - ID: {doc.get('_id')}")
                    print(f"     Address: {doc.get('address')}")
                    print(f"     Suburb: {doc.get('suburb')}")
                    print(f"     Listing URL: {doc.get('listing_url', 'N/A')[:80]}")
                    print()

    # Also check varsity_lakes collection specifically
    print("\n" + "=" * 80)
    print("VARSITY_LAKES COLLECTION - ROBINA PROPERTIES")
    print("=" * 80)

    varsity_coll = db['varsity_lakes']
    robina_in_varsity = list(varsity_coll.find({"address": {"$regex": "Robina", "$options": "i"}}).limit(20))

    if robina_in_varsity:
        print(f"\n⚠️  Found {len(robina_in_varsity)} properties with 'Robina' in address:")
        for doc in robina_in_varsity:
            print(f"\n   - ID: {doc.get('_id')}")
            print(f"     Address: {doc.get('address')}")
            print(f"     Suburb: {doc.get('suburb')}")
            print(f"     First Seen: {doc.get('first_seen')}")
    else:
        print("\n✓ No properties with 'Robina' in address found in varsity_lakes collection")

    client.close()

if __name__ == '__main__':
    find_property()
