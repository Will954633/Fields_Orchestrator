#!/usr/bin/env python3
"""
Check if today's orchestrator run saved data correctly
"""
import os
from pymongo import MongoClient
from datetime import datetime, timedelta
import pytz

# Connection string from settings
COSMOS_URI = "mongodb://REDACTED:REDACTED@REDACTED.mongo.cosmos.azure.com:10255/"

# Target suburbs
TARGET_SUBURBS = [
    "Robina", "Mudgeeraba", "Varsity Lakes", "Reedy Creek",
    "Burleigh Waters", "Merrimac", "Worongary", "Carrara"
]

def main():
    print("=" * 60)
    print("  Fields Orchestrator - Today's Data Check")
    print(f"  {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print("=" * 60)
    print()

    # Connect to database
    client = MongoClient(COSMOS_URI, serverSelectionTimeoutMS=10000)

    # Get today's date in Brisbane timezone
    brisbane_tz = pytz.timezone('Australia/Brisbane')
    now = datetime.now(brisbane_tz)
    today_start = now.replace(hour=0, minute=0, second=0, microsecond=0)

    print(f"📅 Checking data for: {now.strftime('%Y-%m-%d')} (Brisbane time)")
    print()

    # Check Gold Coast Currently For Sale database
    db = client['Gold_Coast_Currently_For_Sale']

    print("🏠 Target Suburbs Data Status:")
    print("-" * 60)

    total_properties = 0
    total_updated_today = 0

    for suburb in TARGET_SUBURBS:
        try:
            collection = db[suburb]

            # Total properties in suburb
            total = collection.count_documents({})

            # Properties updated today
            updated_today = collection.count_documents({
                'last_updated': {'$gte': today_start.isoformat()}
            })

            # Get latest update timestamp
            latest = collection.find_one(
                {},
                sort=[('last_updated', -1)],
                projection={'last_updated': 1, 'address': 1}
            )

            latest_time = ""
            if latest and 'last_updated' in latest:
                try:
                    # Handle both string and datetime formats
                    if isinstance(latest['last_updated'], str):
                        latest_dt = datetime.fromisoformat(latest['last_updated'].replace('Z', '+00:00'))
                    else:
                        latest_dt = latest['last_updated']

                    if latest_dt.tzinfo is None:
                        latest_dt = brisbane_tz.localize(latest_dt)
                    else:
                        latest_dt = latest_dt.astimezone(brisbane_tz)

                    latest_time = latest_dt.strftime('%H:%M:%S')
                except Exception as e:
                    latest_time = str(latest['last_updated'])[:19]

            status_icon = "✅" if updated_today > 0 else "⚠️"
            print(f"  {status_icon} {suburb:20s} | Total: {total:3d} | Updated today: {updated_today:3d} | Latest: {latest_time}")

            total_properties += total
            total_updated_today += updated_today

        except Exception as e:
            print(f"  ❌ {suburb:20s} | Error: {str(e)}")

    print("-" * 60)
    print(f"  📊 TOTALS: {total_properties} properties | {total_updated_today} updated today")
    print()

    # Check sold properties
    sold_db = client['property_data']
    sold_coll = sold_db['Gold_Coast_Recently_Sold']

    try:
        total_sold = sold_coll.count_documents({})
        sold_today = sold_coll.count_documents({
            'date_sold': {'$gte': today_start.isoformat()}
        })

        print(f"🏡 Recently Sold Properties:")
        print(f"  Total: {total_sold} | Marked sold today: {sold_today}")
        print()
    except Exception as e:
        print(f"❌ Error checking sold properties: {str(e)}")
        print()

    # Overall assessment
    print("=" * 60)
    print("  ASSESSMENT")
    print("=" * 60)

    if total_updated_today > 0:
        print(f"  ✅ SUCCESS: {total_updated_today} properties were updated today")
        print(f"  ✅ Data pipeline is working correctly")
    else:
        print(f"  ⚠️  WARNING: No properties were updated today")
        print(f"  ⚠️  This may indicate an issue with the scraping process")

    print("=" * 60)

    client.close()

if __name__ == '__main__':
    main()
