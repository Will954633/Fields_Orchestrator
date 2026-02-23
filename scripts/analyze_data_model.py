#!/usr/bin/env python3
"""
Analyze Database Data Model
Helps understand which collections are legitimate and which contain errors
"""

import os
import re
from pymongo import MongoClient
from collections import defaultdict

MONGODB_URI = os.getenv('MONGODB_URI', 'mongodb://127.0.0.1:27017/')
DATABASE_NAME = 'Gold_Coast_Currently_For_Sale'

client = MongoClient(MONGODB_URI)
db = client[DATABASE_NAME]

print(f"=" * 80)
print(f"DATABASE DATA MODEL ANALYSIS")
print(f"=" * 80)
print(f"Database: {DATABASE_NAME}\n")

# Get all collections (exclude backups and system)
all_collections = db.list_collection_names()
active_collections = [c for c in all_collections
                      if not c.startswith('system.')
                      and '_backup_' not in c]

print(f"Total active collections: {len(active_collections)}\n")

# Analyze each collection
print(f"=" * 80)
print(f"COLLECTION ANALYSIS")
print(f"=" * 80)

collection_data = []

for coll_name in sorted(active_collections):
    coll = db[coll_name]

    # Get sample documents
    total_count = coll.count_documents({})
    sample_docs = list(coll.find({}).limit(5))

    # Extract suburbs from addresses
    suburbs_in_addresses = defaultdict(int)
    suburb_field_values = defaultdict(int)

    for doc in coll.find({}, {'address': 1, 'suburb': 1}).limit(100):
        address = doc.get('address', '')
        suburb_field = doc.get('suburb', '')

        # Extract suburb from address
        match = re.search(r',\s*([^,]+),\s*(QLD|NSW|VIC|SA|WA|TAS|NT|ACT)', address, re.IGNORECASE)
        if match:
            actual_suburb = match.group(1).strip()
            suburbs_in_addresses[actual_suburb] += 1

        if suburb_field:
            suburb_field_values[suburb_field] += 1

    # Determine collection type
    if len(suburbs_in_addresses) > 10:
        coll_type = "MIXED (catch-all collection)"
    elif len(suburbs_in_addresses) == 1:
        coll_type = "SINGLE SUBURB"
    else:
        coll_type = "FEW SUBURBS"

    collection_data.append({
        'name': coll_name,
        'count': total_count,
        'type': coll_type,
        'unique_suburbs_in_addresses': len(suburbs_in_addresses),
        'top_suburb_in_address': max(suburbs_in_addresses.items(), key=lambda x: x[1])[0] if suburbs_in_addresses else 'N/A',
        'top_suburb_field': max(suburb_field_values.items(), key=lambda x: x[1])[0] if suburb_field_values else 'N/A',
    })

# Print results
print(f"\n{'Collection Name':<40} {'Docs':<8} {'Type':<30} {'Top Suburb (Address)':<25} {'Top Suburb (Field)':<25}")
print("-" * 150)

for data in collection_data:
    print(f"{data['name']:<40} {data['count']:<8} {data['type']:<30} {data['top_suburb_in_address']:<25} {data['top_suburb_field']:<25}")

# Identify special collections
print(f"\n{'' * 80}")
print(f"SPECIAL COLLECTIONS (Mixed/Catch-All)")
print(f"=" * 80)

mixed_collections = [d for d in collection_data if d['type'] == "MIXED (catch-all collection)"]
for data in mixed_collections:
    print(f"\n{data['name']}:")
    print(f"  Documents: {data['count']:,}")
    print(f"  Unique suburbs in addresses: {data['unique_suburbs_in_addresses']}")
    print(f"  ⚠️  This appears to be a catch-all collection with properties from multiple suburbs")
    print(f"  ⚠️  May be intentional (different data model) - review before migrating")

# Check for duplicates between Gold_Coast_Recently_Sold and suburb collections
print(f"\n{'=' * 80}")
print(f"DUPLICATE ANALYSIS")
print(f"=" * 80)

if 'Gold_Coast_Recently_Sold' in [d['name'] for d in collection_data]:
    print(f"\nChecking for duplicates between Gold_Coast_Recently_Sold and suburb collections...")

    gcs_coll = db['Gold_Coast_Recently_Sold']
    gcs_urls = set(doc['listing_url'] for doc in gcs_coll.find({}, {'listing_url': 1}) if 'listing_url' in doc)

    duplicates_found = 0
    for data in collection_data:
        if data['name'] != 'Gold_Coast_Recently_Sold' and data['type'] == 'SINGLE SUBURB':
            coll = db[data['name']]
            coll_urls = set(doc['listing_url'] for doc in coll.find({}, {'listing_url': 1}) if 'listing_url' in doc)

            overlap = gcs_urls & coll_urls
            if overlap:
                print(f"  {data['name']}: {len(overlap)} duplicates with Gold_Coast_Recently_Sold")
                duplicates_found += len(overlap)

    print(f"\nTotal duplicate properties: {duplicates_found}")
    if duplicates_found > 0:
        print(f"⚠️  Gold_Coast_Recently_Sold appears to be a duplicate/catch-all collection")
        print(f"   Consider excluding it from migration")

print(f"\n{'=' * 80}")
print(f"RECOMMENDATIONS")
print(f"{'=' * 80}\n")

if mixed_collections:
    print(f"1. EXCLUDE these collections from migration (they're catch-all/aggregate collections):")
    for data in mixed_collections:
        print(f"   - {data['name']}")
    print()

print(f"2. MIGRATE suburb-specific collections only")
print(f"3. FIX malformed addresses before migration:")
print(f"   - 'Burleigh, Waters' → 'Burleigh Waters'")
print(f"   - 'Reedy, Creek' → 'Reedy Creek'")
print(f"   - 'Varsity, Lakes' → 'Varsity Lakes'")
print(f"\n{'=' * 80}\n")

client.close()
