#!/usr/bin/env python3
"""
List all collections and their document counts
"""
from pymongo import MongoClient
from datetime import datetime

# Connection string
COSMOS_URI = "mongodb://REDACTED:REDACTED@REDACTED.mongo.cosmos.azure.com:10255/"

def main():
    print("=" * 80)
    print("  Azure Cosmos DB - Collections & Document Counts")
    print(f"  {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print("=" * 80)
    print()

    client = MongoClient(COSMOS_URI, serverSelectionTimeoutMS=10000)

    databases = [
        'property_data',
        'Gold_Coast_Currently_For_Sale',
        'Gold_Coast',
        'Gold_Coast_Recently_Sold'
    ]

    for db_name in databases:
        print(f"📦 Database: {db_name}")
        print("-" * 80)

        try:
            db = client[db_name]
            collections = db.list_collection_names()

            if not collections:
                print("  (empty - no collections)")
                print()
                continue

            # Get counts for each collection
            collection_data = []
            for coll_name in collections:
                try:
                    count = db[coll_name].count_documents({})

                    # Get a sample document to see last_updated
                    sample = db[coll_name].find_one(
                        {},
                        sort=[('last_updated', -1)],
                        projection={'last_updated': 1}
                    )

                    last_updated = ""
                    if sample and 'last_updated' in sample:
                        last_updated = str(sample['last_updated'])[:19]

                    collection_data.append((coll_name, count, last_updated))
                except Exception as e:
                    collection_data.append((coll_name, 0, f"Error: {str(e)}"))

            # Sort by count descending
            collection_data.sort(key=lambda x: x[1] if isinstance(x[1], int) else 0, reverse=True)

            # Print with counts
            for coll_name, count, last_updated in collection_data:
                if isinstance(count, int) and count > 0:
                    print(f"  ✅ {coll_name:40s} | {count:6d} docs | Last: {last_updated}")
                elif isinstance(count, int):
                    print(f"  ⚪ {coll_name:40s} | {count:6d} docs")
                else:
                    print(f"  ❌ {coll_name:40s} | {count}")

            print(f"\n  Total collections: {len(collections)}")
            print()

        except Exception as e:
            print(f"  ❌ Error accessing database: {str(e)}")
            print()

    client.close()

if __name__ == '__main__':
    main()
