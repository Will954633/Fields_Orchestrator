#!/usr/bin/env python3
""" 
Pre-compute Active Listings Snapshot Series
Last Updated: 14/02/2026, 12:05 PM (Saturday) — Brisbane Time

Description:
    Captures a daily snapshot of the number of currently active for-sale listings
    per suburb (from Gold_Coast_Currently_For_Sale DB) and stores the counts as a
    time series in Gold_Coast.precomputed_active_listings.

    This enables credible MoM (month-over-month) deltas for the Phase 1 Data Insights
    Strip metric:
      - Active Listings (Current Stock)
      - MoM change

    Why we need this:
      - We can compute “current active listings” instantly via countDocuments(),
        but “vs last month” requires an actual historical series.

Output collection (Gold_Coast DB):
    precomputed_active_listings

Document model:
    {
      _id: "robina",
      suburb: "Robina",
      snapshots: [
        { date: ISODate("2026-02-14"), active_listings: 123 },
        ...
      ],
      last_updated: ISODate
    }

    Notes:
      - We keep up to MAX_SNAPSHOTS_DAYS history (default 400 days).
      - We de-duplicate by day (UTC date).

Environment Variables Required:
    COSMOS_CONNECTION_STRING - Azure Cosmos DB (MongoDB API) connection string

Usage:
    python3 precompute_active_listings.py

Edit History:
    - 14/02/2026 12:05 PM: Initial creation
"""

import os
import sys
from datetime import datetime, timedelta, timezone

from dotenv import load_dotenv
from pymongo import MongoClient, ASCENDING
from pymongo.errors import WriteError

# Load environment variables from .env file
load_dotenv()

try:
    sys.path.insert(0, '/home/fields/Fields_Orchestrator')
    from shared.monitor_client import MonitorClient
    _MONITOR_AVAILABLE = True
except ImportError:
    _MONITOR_AVAILABLE = False


TARGET_MARKET_SUBURBS = [
    'robina', 'mudgeeraba', 'varsity_lakes', 'carrara',
    'reedy_creek', 'burleigh_waters', 'merrimac', 'worongary'
]

MAX_SNAPSHOTS_DAYS = 400


def get_db_connection():
    connection_string = os.getenv('COSMOS_CONNECTION_STRING')
    if not connection_string:
        print('ERROR: COSMOS_CONNECTION_STRING environment variable not set')
        sys.exit(1)

    client = MongoClient(
        connection_string,
        retryWrites=False,
        serverSelectionTimeoutMS=30000,
        socketTimeoutMS=60000,
    )
    return client


def to_title_case(name: str) -> str:
    return ' '.join(word.capitalize() for word in name.replace('_', ' ').split())


def utc_day(dt: datetime) -> datetime:
    dt_utc = dt.astimezone(timezone.utc)
    return datetime(dt_utc.year, dt_utc.month, dt_utc.day, tzinfo=timezone.utc)


def count_active_listings(for_sale_db, suburb_collection: str) -> int:
    """Count active house listings in a suburb collection (excludes units, townhouses, sold, cadastral)."""
    try:
        return for_sale_db[suburb_collection].count_documents({
            'listing_status': 'for_sale',
            'property_type': {'$regex': '^house$', '$options': 'i'}
        })
    except Exception:
        return 0


def upsert_snapshot(gold_coast_db, suburb_collection: str, snapshot_date: datetime, active_listings: int):
    collection = gold_coast_db['precomputed_active_listings']

    # Ensure we only store one snapshot per day
    snapshot_doc = {
        'date': snapshot_date,
        'active_listings': int(active_listings),
    }

    # Pull any existing snapshot for the same day, then push the new one.
    # (Cosmos doesn't support all update operators perfectly; this is conservative.)
    collection.update_one(
        {'_id': suburb_collection},
        {
            '$setOnInsert': {
                '_id': suburb_collection,
                'suburb': to_title_case(suburb_collection),
            },
            '$set': {
                'last_updated': datetime.utcnow(),
            },
            '$pull': {
                'snapshots': {
                    'date': snapshot_date,
                }
            },
        },
        upsert=True,
    )

    collection.update_one(
        {'_id': suburb_collection},
        {
            '$push': {
                'snapshots': snapshot_doc,
            }
        }
    )

    # Trim history window
    cutoff = snapshot_date - timedelta(days=MAX_SNAPSHOTS_DAYS)
    collection.update_one(
        {'_id': suburb_collection},
        {
            '$pull': {
                'snapshots': {
                    'date': {'$lt': cutoff},
                }
            }
        }
    )


def main():
    monitor = MonitorClient(
        system="orchestrator", pipeline="orchestrator_daily",
        process_id="19", process_name="Precompute Active Listings"
    ) if _MONITOR_AVAILABLE else None
    if monitor: monitor.start()

    print('=' * 80)
    print('Pre-computing Active Listings snapshots')
    print('=' * 80)
    print('Connecting to Azure Cosmos DB...')

    client = get_db_connection()
    gold_coast_db = client['Gold_Coast']
    for_sale_db = client['Gold_Coast']

    print('✅ Connected')

    snapshot_date = utc_day(datetime.now(timezone.utc))
    print(f'Snapshot date (UTC): {snapshot_date.isoformat()}')
    print('Processing target market suburbs...')

    precomputed_collection = gold_coast_db['precomputed_active_listings']
    precomputed_collection.create_index([('_id', ASCENDING)])

    for suburb_collection in TARGET_MARKET_SUBURBS:
        count = count_active_listings(for_sale_db, suburb_collection)
        print(f'  {suburb_collection}: {count}')
        try:
            upsert_snapshot(gold_coast_db, suburb_collection, snapshot_date, count)
        except WriteError as e:
            print(f'  ⚠️  WriteError for {suburb_collection}: {str(e)}')
        except Exception as e:
            print(f'  ❌ Error for {suburb_collection}: {str(e)}')

    print('✅ Done')
    client.close()

    if monitor:
        monitor.log_metric("suburbs_snapshotted", len(TARGET_MARKET_SUBURBS))
        monitor.finish(status="success")


if __name__ == '__main__':
    main()
