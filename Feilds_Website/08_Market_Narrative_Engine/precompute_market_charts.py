#!/usr/bin/env python3
"""
Pre-compute Market Charts Data for Market Narrative Engine
Last Updated: 14/02/2026, 12:03 PM (Saturday) — Brisbane Time

Description:
    This script pre-computes data for 4 charts:
    1. Days on Market Trend - Shows how quickly properties sell
    2. Market Cycle Indicator - Circular dial showing market phase (0-100 score)
    3. Sales Volume Chart - Transaction volume per quarter
    4. Turnover Rate - Annual % of properties that changed hands
    
    Data is stored in Azure Cosmos DB precomputed_market_charts collection,
    eliminating the need for real-time calculations in Netlify Functions.

Edit History:
    - 14/02/2026 12:03 PM: Phase 1 metric support (Days on Market median)
      - Added median_days_on_market per quarter to days-on-market timeline
      - Added historical_median (keep historical_average)
      - Added latest_quarter_median and yoy_change_days (latest quarter vs same quarter last year)
      - Kept avg_days_on_market unchanged for backwards compatibility
    - 12/02/2026 10:15 AM: Initial creation
      - Implements Days on Market calculation with seasonal trends
      - Implements Market Cycle Score (price momentum, velocity, supply/demand)
      - Implements Sales Volume with YoY trends
      - Stores in precomputed_market_charts collection

Usage:
    python3 precompute_market_charts.py

Environment Variables Required:
    COSMOS_CONNECTION_STRING - Azure Cosmos DB connection string

Output:
    Data Sources (merged for complete picture):
        Gold_Coast.{suburb}                       - Historical property timelines (scraped_data.property_timeline)
        Target_Market_Sold_Last_12_Months.{suburb} - Recent 12 months sold data (flat sale_date/time_on_market_days)

    Output: Gold_Coast.precomputed_market_charts
        - {suburb}_days_on_market
        - {suburb}_market_cycle
        - {suburb}_sales_volume
        - {suburb}_turnover_rate
"""

import os
import sys
import time
from datetime import datetime, timedelta
from pymongo import MongoClient, ASCENDING
from pymongo.errors import WriteError
from statistics import median, mean
import math

# Target market suburbs (8 suburbs)
TARGET_MARKET_SUBURBS = [
    'robina', 'mudgeeraba', 'varsity_lakes', 'carrara',
    'reedy_creek', 'burleigh_waters', 'merrimac', 'worongary'
]


def get_db_connection():
    """Connect to Azure Cosmos DB"""
    connection_string = os.getenv('COSMOS_CONNECTION_STRING')
    if not connection_string:
        print("ERROR: COSMOS_CONNECTION_STRING environment variable not set")
        sys.exit(1)
    
    client = MongoClient(connection_string, 
                        retryWrites=False,
                        serverSelectionTimeoutMS=30000,
                        socketTimeoutMS=60000)
    return client


def to_title_case(name):
    """Convert suburb name to title case"""
    return ' '.join(word.capitalize() for word in name.replace('_', ' ').split())


def get_quarter_key(date_obj):
    """Get quarter key (e.g., '2024-Q1') from datetime"""
    quarter = (date_obj.month - 1) // 3 + 1
    return f"{date_obj.year}-Q{quarter}"


def _get_dom_sold_records_from_sold_db(sold_db, suburb_collection_name, start_date_str, end_date_str):
    """
    Fetch days-on-market records from Target_Market_Sold_Last_12_Months.
    Returns list of dicts with 'date' (datetime), 'days_on_market' (int), 'quarter' (str).
    """
    try:
        coll = sold_db[suburb_collection_name]
        pipeline = [
            {
                '$match': {
                    'property_type': 'House',
                    'sale_date': {'$gte': start_date_str, '$lte': end_date_str},
                    'time_on_market_days': {'$ne': None, '$gt': 0, '$lt': 365},
                },
            },
            {
                '$addFields': {
                    'timeline_date': {'$dateFromString': {'dateString': '$sale_date'}},
                },
            },
            {
                '$project': {
                    'date': '$timeline_date',
                    'days_on_market': '$time_on_market_days',
                    'quarter': {
                        '$concat': [
                            {'$toString': {'$year': '$timeline_date'}},
                            '-Q',
                            {'$toString': {'$ceil': {'$divide': [{'$month': '$timeline_date'}, 3]}}},
                        ],
                    },
                },
            },
        ]
        return list(coll.aggregate(pipeline))
    except Exception:
        return []



# ┌──────────────────────────────────────────────────────────────────────────────┐
# │ DATA SOURCE CONSISTENCY WARNING (March 2026 incident)                       │
# │                                                                             │
# │ Sales volume merges THREE sources per quarter and takes MAX:                 │
# │   1. property_timeline (Domain published, lags ~weeks) — houses only        │
# │   2. Target_Market_Sold_Last_12_Months (flat sold records) — houses only    │
# │   3. listing_status='sold' records (scraper-detected, real-time)            │
# │                                                                             │
# │ Source #3 queries the unified Gold_Coast DB which contains ~40K cadastral   │
# │ records. Many have sold_date + listing_status='sold' but NO scraped_data,   │
# │ and include all property types (townhouses, apartments, unknowns).          │
# │                                                                             │
# │ If source #3 is not filtered to match sources #1 and #2 (houses only),     │
# │ recent quarters will be inflated. In March 2026, Q1 showed 85 (all types)  │
# │ instead of 54 (houses only) — a phantom 57% "surge" that was actually      │
# │ just townhouses and cadastral records being counted.                        │
# │                                                                             │
# │ RULE: Any new data source added to the merge MUST filter by the same       │
# │ property_type as the existing sources. Test by comparing counts.            │
# └──────────────────────────────────────────────────────────────────────────────┘
def _get_listing_status_sold(gc_db, suburb_collection_name, start_date_str, end_date_str, property_type_filter="House"):
    """
    Fetch sold records from Gold_Coast.{suburb} using listing_status='sold'.
    This catches properties sold via the scraper's sold detection (step 103)
    that may NOT yet appear in property_timeline (Domain publishes timelines with a lag).

    When property_type_filter is set (default 'House'), only records whose resolved
    property_type matches are returned.  This keeps the listing_status source
    consistent with the property_timeline source (which filters 'House').

    Returns dicts with 'sold_date', 'days_on_market', 'price', 'property_type', 'quarter'.
    """
    def _resolve_ptype(doc):
        return (doc.get("scraped_data", {}).get("features", {}).get("property_type")
                or doc.get("property_type", "Unknown"))

    def _parse_docs(cursor):
        results = []
        for doc in cursor:
            sd = doc.get("sold_date", "")
            if not sd:
                continue
            try:
                if isinstance(sd, datetime):
                    dt = sd
                else:
                    dt = datetime.strptime(str(sd)[:10], "%Y-%m-%d")
                q = (dt.month - 1) // 3 + 1
                ptype = _resolve_ptype(doc)
                if property_type_filter and ptype != property_type_filter:
                    continue
                results.append({
                    "date": dt,
                    "days_on_market": doc.get("days_on_market"),
                    "price": doc.get("sold_price"),
                    "property_type": ptype,
                    "quarter": f"{dt.year}-Q{q}",
                    "year": dt.year,
                })
            except (ValueError, TypeError):
                continue
        return results

    try:
        coll = gc_db[suburb_collection_name]
        cursor = coll.find(
            {
                "listing_status": "sold",
                "sold_date": {"$gte": start_date_str, "$lte": end_date_str},
            },
            {
                "sold_date": 1, "days_on_market": 1, "sold_price": 1,
                "scraped_data.features.property_type": 1,
                "property_type": 1, "_id": 0,
            },
        ).batch_size(200)
        return _parse_docs(cursor)
    except Exception as e:
        # Retry once on Cosmos rate limit
        if "16500" in str(e) or "429" in str(e):
            print(f"      ⚠️  listing_status query rate-limited, retrying in 5s...")
            import time as _time
            _time.sleep(5)
            try:
                cursor = coll.find(
                    {"listing_status": "sold", "sold_date": {"$gte": start_date_str, "$lte": end_date_str}},
                    {"sold_date": 1, "days_on_market": 1, "sold_price": 1, "scraped_data.features.property_type": 1, "property_type": 1, "_id": 0},
                ).batch_size(200)
                return _parse_docs(cursor)
            except Exception as e2:
                print(f"      ⚠️  listing_status retry also failed: {e2}")
                return []
        print(f"      ⚠️  listing_status sold query failed: {e}")
        return []


def _merge_volume_sources(timeline_counts, status_counts):
    """
    Merge quarterly sales counts from property_timeline and listing_status sources.
    Takes MAX per quarter to avoid double-counting while using the best available source.
    - property_timeline: authoritative for historical data (published by Domain with lag)
    - listing_status: more current for recent quarters (detected in real-time by scraper)
    """
    all_quarters = set(list(timeline_counts.keys()) + list(status_counts.keys()))
    merged = {}
    for q in all_quarters:
        merged[q] = max(timeline_counts.get(q, 0), status_counts.get(q, 0))
    return merged


def calculate_days_on_market_data(gc_db, sold_db, suburb_collection_name):
    """
    Calculate Days on Market trend data for a suburb.
    Merges data from Gold_Coast (historical timeline) and Target_Market_Sold_Last_12_Months (recent 12 months).
    Returns dict with timeline, trends, and metadata.
    """
    print(f"    Calculating Days on Market for {suburb_collection_name}...")

    try:
        collection = gc_db[suburb_collection_name]

        # Query Gold_Coast for data older than 12 months (historical)
        end_date = datetime.now()
        cutoff_12m = end_date - timedelta(days=365)
        start_date = end_date - timedelta(days=365 * 3)  # 3 years total window
        start_date_str = start_date.strftime('%Y-%m-%d')
        end_date_str = end_date.strftime('%Y-%m-%d')
        cutoff_12m_str = cutoff_12m.strftime('%Y-%m-%d')

        pipeline = [
            {'$unwind': '$scraped_data.property_timeline'},
            {
                '$match': {
                    'scraped_data.property_timeline.is_sold': True,
                    'scraped_data.property_timeline.date': {
                        '$gte': start_date_str,
                        '$lt': cutoff_12m_str,   # only historical (>12 months ago)
                    },
                    'scraped_data.features.property_type': 'House',
                },
            },
            {
                '$addFields': {
                    'timeline_date': {'$dateFromString': {'dateString': '$scraped_data.property_timeline.date'}},
                    'days_on_market': '$scraped_data.property_timeline.days_on_market',
                },
            },
            {
                '$match': {
                    'days_on_market': {'$ne': None, '$gt': 0, '$lt': 365},  # Filter outliers
                },
            },
            {
                '$project': {
                    'date': '$timeline_date',
                    'days_on_market': 1,
                    'quarter': {
                        '$concat': [
                            {'$toString': {'$year': '$timeline_date'}},
                            '-Q',
                            {'$toString': {'$ceil': {'$divide': [{'$month': '$timeline_date'}, 3]}}},
                        ],
                    },
                },
            },
        ]

        historical_results = list(collection.aggregate(pipeline))

        # Query Target_Market_Sold_Last_12_Months for recent 12 months
        recent_results = _get_dom_sold_records_from_sold_db(sold_db, suburb_collection_name, cutoff_12m_str, end_date_str)

        # Also query listing_status='sold' records (catches sales not yet in property_timeline)
        status_sold = _get_listing_status_sold(gc_db, suburb_collection_name, cutoff_12m_str, end_date_str)
        status_dom_records = [
            {"date": r["date"], "days_on_market": r["days_on_market"], "quarter": r["quarter"]}
            for r in status_sold
            if r.get("days_on_market") and 0 < r["days_on_market"] < 365
        ]
        # Merge: add status records to recent pool (dedupe happens downstream via quarter grouping)
        recent_results.extend(status_dom_records)
        print(f"      Sources: {len(historical_results)} historical (timeline) + {len(recent_results)} recent (Sold_12M + listing_status)")

        # Fallback: if Target_Market has too few DOM records for the recent window,
        # also pull Gold_Coast data for the same period. Target_Market often has
        # time_on_market_days=None, leaving a multi-quarter gap in the DOM timeline.
        MIN_RECENT_DOM_RECORDS = 5
        if len(recent_results) < MIN_RECENT_DOM_RECORDS:
            print(f"      ⚠️  Only {len(recent_results)} recent DOM records from Sold_Last_12_Months (threshold: {MIN_RECENT_DOM_RECORDS})")
            print(f"      Falling through to Gold_Coast for recent DOM data...")
            gc_recent_pipeline = [
                {'$unwind': '$scraped_data.property_timeline'},
                {
                    '$match': {
                        'scraped_data.property_timeline.is_sold': True,
                        'scraped_data.property_timeline.date': {
                            '$gte': cutoff_12m_str,
                            '$lte': end_date_str,
                        },
                        'scraped_data.features.property_type': 'House',
                    },
                },
                {
                    '$addFields': {
                        'timeline_date': {'$dateFromString': {'dateString': '$scraped_data.property_timeline.date'}},
                        'days_on_market': '$scraped_data.property_timeline.days_on_market',
                    },
                },
                {
                    '$match': {
                        'days_on_market': {'$ne': None, '$gt': 0, '$lt': 365},
                    },
                },
                {
                    '$project': {
                        'date': '$timeline_date',
                        'days_on_market': 1,
                        'quarter': {
                            '$concat': [
                                {'$toString': {'$year': '$timeline_date'}},
                                '-Q',
                                {'$toString': {'$ceil': {'$divide': [{'$month': '$timeline_date'}, 3]}}},
                            ],
                        },
                    },
                },
            ]
            gc_recent_results = list(collection.aggregate(gc_recent_pipeline))
            # Merge: prefer Target_Market records, add Gold_Coast records for dates not already covered
            existing_dates = {r['date'] for r in recent_results}
            gc_added = 0
            for r in gc_recent_results:
                if r['date'] not in existing_dates:
                    recent_results.append(r)
                    existing_dates.add(r['date'])
                    gc_added += 1
            print(f"      Added {gc_added} DOM records from Gold_Coast fallback (total recent: {len(recent_results)})")

        results = historical_results + recent_results
        
        if not results:
            print(f"      ⚠️  No data found")
            return None
        
        # Group by quarter
        quarter_data = {}
        for doc in results:
            quarter = doc['quarter']
            if quarter not in quarter_data:
                quarter_data[quarter] = []
            quarter_data[quarter].append(doc['days_on_market'])
        
        # Determine the current (incomplete) quarter to exclude
        now = datetime.now()
        current_q = f"{now.year}-Q{(now.month - 1) // 3 + 1}"

        # Minimum DOM records per quarter — fewer than this is not representative
        MIN_DOM_PER_QUARTER = 3

        # Build timeline
        timeline = []
        all_days = []
        for quarter in sorted(quarter_data.keys()):
            # Skip the current incomplete quarter
            if quarter == current_q:
                print(f"      Skipping {quarter} (current quarter, incomplete)")
                continue

            days_list = quarter_data[quarter]

            # Skip quarters with too few DOM records
            if len(days_list) < MIN_DOM_PER_QUARTER:
                print(f"      Skipping {quarter} (only {len(days_list)} DOM records, min {MIN_DOM_PER_QUARTER})")
                continue

            avg_days = mean(days_list)
            median_days = median(days_list) if days_list else None
            quick_sales = sum(1 for d in days_list if d < 30) / len(days_list) * 100
            slow_sales = sum(1 for d in days_list if d > 90) / len(days_list) * 100

            timeline.append({
                'period': quarter,
                'avg_days_on_market': round(avg_days, 1),
                'median_days_on_market': round(median_days, 1) if median_days is not None else None,
                'transaction_count': len(days_list),
                'quick_sales_pct': round(quick_sales, 1),
                'slow_sales_pct': round(slow_sales, 1),
            })
            all_days.extend(days_list)
        
        # Calculate historical summary stats
        historical_average = round(mean(all_days), 1) if all_days else 0
        historical_median = round(median(all_days), 1) if all_days else 0

        # Latest quarter median + YoY change in days (latest quarter vs same quarter last year)
        latest_quarter_median = None
        yoy_change_days = None
        if timeline:
            latest = timeline[-1]
            latest_quarter_median = latest.get('median_days_on_market')
            latest_period = latest.get('period')  # e.g. 2025-Q4
            if latest_period and '-' in latest_period:
                year_str, quarter_part = latest_period.split('-')
                try:
                    prev_year_period = f"{int(year_str) - 1}-{quarter_part}"
                    year_ago = next((t for t in timeline if t.get('period') == prev_year_period), None)
                    if year_ago and latest_quarter_median is not None and year_ago.get('median_days_on_market') is not None:
                        yoy_change_days = round(latest_quarter_median - year_ago['median_days_on_market'], 1)
                except ValueError:
                    pass
        
        # Rate limit cooldown before second heavy aggregation
        time.sleep(4)

        # Calculate monthly seasonal trends (10 years, excluding 2020-2021)
        # Merge Gold_Coast historical + Target_Market_Sold_Last_12_Months recent data
        print("      Calculating 10-year monthly seasonal averages (excluding 2020-2021)...")

        # Query Gold_Coast for 10 years of historical DOM data (excluding last 12 months)
        seasonal_start = datetime.now() - timedelta(days=365 * 10)
        seasonal_start_str = seasonal_start.strftime('%Y-%m-%d')

        seasonal_pipeline = [
            {'$unwind': '$scraped_data.property_timeline'},
            {
                '$match': {
                    'scraped_data.property_timeline.is_sold': True,
                    'scraped_data.property_timeline.date': {
                        '$gte': seasonal_start_str,
                        '$lt': cutoff_12m_str,
                    },
                    'scraped_data.features.property_type': 'House',
                },
            },
            {
                '$addFields': {
                    'timeline_date': {'$dateFromString': {'dateString': '$scraped_data.property_timeline.date'}},
                    'days_on_market': '$scraped_data.property_timeline.days_on_market',
                },
            },
            {
                '$match': {
                    'days_on_market': {'$ne': None, '$gt': 0, '$lt': 365},
                },
            },
            {
                '$project': {
                    'date': '$timeline_date',
                    'days_on_market': 1,
                    'year': {'$year': '$timeline_date'},
                    'month': {'$month': '$timeline_date'},
                },
            },
        ]

        gc_seasonal_results = list(collection.aggregate(seasonal_pipeline))

        # Also get recent 12 months from sold_db for seasonal calculation
        recent_seasonal_raw = _get_dom_sold_records_from_sold_db(sold_db, suburb_collection_name, cutoff_12m_str, end_date_str)
        recent_seasonal_results = []
        for doc in recent_seasonal_raw:
            d = doc.get('date')
            if d:
                recent_seasonal_results.append({
                    'days_on_market': doc['days_on_market'],
                    'year': d.year,
                    'month': d.month,
                })

        # Group by month (1-12), excluding 2020 and 2021
        seasonal_data = {i: [] for i in range(1, 13)}
        for doc in gc_seasonal_results:
            year = doc['year']
            if year not in [2020, 2021]:
                month = doc['month']
                seasonal_data[month].append(doc['days_on_market'])
        for doc in recent_seasonal_results:
            year = doc['year']
            if year not in [2020, 2021]:
                month = doc['month']
                seasonal_data[month].append(doc['days_on_market'])

        # Calculate monthly averages
        month_names = ['Jan', 'Feb', 'Mar', 'Apr', 'May', 'Jun',
                       'Jul', 'Aug', 'Sep', 'Oct', 'Nov', 'Dec']
        seasonal_trend = []
        for month_num in range(1, 13):
            if seasonal_data[month_num]:
                seasonal_trend.append({
                    'month': month_num,
                    'month_name': month_names[month_num - 1],
                    'avg_days': round(mean(seasonal_data[month_num]), 1),
                })

        print(f"      ✅ Calculated {len(seasonal_trend)} monthly seasonal averages")
        
        result = {
            '_id': f"{suburb_collection_name}_days_on_market",
            'suburb': to_title_case(suburb_collection_name),
            'chart_type': 'days_on_market',
            'timeline': timeline,
            'historical_average': historical_average,
            'historical_median': historical_median,
            'latest_quarter_median': latest_quarter_median,
            'yoy_change_days': yoy_change_days,
            'seasonal_trend': seasonal_trend,
            'last_updated': datetime.utcnow(),
        }
        
        print(f"      ✅ {len(timeline)} quarters, avg={historical_average} days")
        return result
        
    except Exception as e:
        print(f"      ❌ Error: {str(e)}")
        return None


def calculate_market_cycle_score(gc_db, sold_db, suburb_collection_name):
    """
    Calculate Market Cycle Indicator score (0-100) for a suburb.
    Combines: price momentum, transaction velocity, days on market, supply/demand.
    """
    print(f"    Calculating Market Cycle Score for {suburb_collection_name}...")

    try:
        collection = gc_db[suburb_collection_name]
        
        # Get recent 6 months of data
        end_date = datetime.now()
        start_date_recent = end_date - timedelta(days=180)
        start_date_historical = end_date - timedelta(days=365 * 2)
        
        recent_str = start_date_recent.strftime('%Y-%m-%d')
        historical_str = start_date_historical.strftime('%Y-%m-%d')
        end_str = end_date.strftime('%Y-%m-%d')
        
        # 1. Price Momentum (recent 6 months vs previous 6 months)
        pipeline_prices = [
            {'$unwind': '$scraped_data.property_timeline'},
            {
                '$match': {
                    'scraped_data.property_timeline.is_sold': True,
                    'scraped_data.property_timeline.price': {'$ne': None, '$gt': 0},
                    'scraped_data.features.property_type': 'House',
                    'scraped_data.property_timeline.date': {
                        '$gte': historical_str,
                        '$lte': end_str,
                    },
                },
            },
            {
                '$addFields': {
                    'timeline_date': {'$dateFromString': {'dateString': '$scraped_data.property_timeline.date'}},
                    'price': '$scraped_data.property_timeline.price',
                },
            },
            {
                '$project': {
                    'date': '$timeline_date',
                    'price': 1,
                    'is_recent': {'$gte': ['$timeline_date', {'$dateFromString': {'dateString': recent_str}}]},
                },
            },
        ]
        
        price_results = list(collection.aggregate(pipeline_prices))
        
        if not price_results:
            print(f"      ⚠️  No price data found")
            return None
        
        recent_prices = [doc['price'] for doc in price_results if doc['is_recent']]
        historical_prices = [doc['price'] for doc in price_results if not doc['is_recent']]
        
        if not recent_prices or not historical_prices:
            print(f"      ⚠️  Insufficient price data")
            return None
        
        recent_median = median(recent_prices)
        historical_median = median(historical_prices)
        price_change_pct = ((recent_median / historical_median) - 1) * 100
        
        # Normalize to 0-1 (assume -10% to +10% is normal range)
        price_momentum = max(0, min(1, (price_change_pct + 10) / 20))
        
        # 2. Transaction Velocity (recent vs historical monthly rate)
        # Supplement recent count with listing_status sold data (timeline may lag)
        status_sold_recent = _get_listing_status_sold(gc_db, suburb_collection_name, recent_str, end_str)
        recent_count = max(len(recent_prices), len(status_sold_recent))
        historical_count = len(historical_prices)
        recent_monthly_rate = recent_count / 6  # 6 months
        historical_monthly_rate = historical_count / 18  # 18 months
        
        if historical_monthly_rate > 0:
            velocity_ratio = recent_monthly_rate / historical_monthly_rate
            transaction_velocity = max(0, min(1, velocity_ratio))
        else:
            transaction_velocity = 0.5
        
        # 3. Days on Market (lower is better for seller's market)
        pipeline_dom = [
            {'$unwind': '$scraped_data.property_timeline'},
            {
                '$match': {
                    'scraped_data.property_timeline.is_sold': True,
                    'scraped_data.property_timeline.date': {
                        '$gte': recent_str,
                        '$lte': end_str,
                    },
                    'scraped_data.features.property_type': 'House',
                },
            },
            {
                '$addFields': {
                    'days_on_market': '$scraped_data.property_timeline.days_on_market',
                },
            },
            {
                '$match': {
                    'days_on_market': {'$ne': None, '$gt': 0, '$lt': 365},
                },
            },
        ]
        
        dom_results = list(collection.aggregate(pipeline_dom))
        
        if dom_results:
            avg_dom = mean([doc['days_on_market'] for doc in dom_results])
            # Normalize: 30 days = 1.0 (excellent), 90 days = 0.5, 180 days = 0.0
            days_on_market_score = max(0, min(1, 1 - (avg_dom - 30) / 150))
        else:
            days_on_market_score = 0.5
        
        # 4. Supply/Demand (simplified - based on transaction velocity)
        supply_demand = transaction_velocity
        
        # Combine into overall score (0-100)
        # Weights: price momentum 30%, velocity 30%, DOM 25%, supply/demand 15%
        overall_score = (
            price_momentum * 0.30 +
            transaction_velocity * 0.30 +
            days_on_market_score * 0.25 +
            supply_demand * 0.15
        ) * 100
        
        # Determine market phase
        if overall_score >= 65:
            phase = "seller's market"
        elif overall_score >= 45:
            phase = "balanced"
        else:
            phase = "buyer's market"
        
        result = {
            '_id': f"{suburb_collection_name}_market_cycle",
            'suburb': to_title_case(suburb_collection_name),
            'chart_type': 'market_cycle',
            'score': round(overall_score, 1),
            'phase': phase,
            'metrics': {
                'price_momentum': round(price_momentum, 2),
                'transaction_velocity': round(transaction_velocity, 2),
                'days_on_market': round(days_on_market_score, 2),
                'supply_demand': round(supply_demand, 2),
            },
            'last_updated': datetime.utcnow(),
        }
        
        print(f"      ✅ Score={overall_score:.1f}, Phase={phase}")
        return result
        
    except Exception as e:
        print(f"      ❌ Error: {str(e)}")
        return None


def _get_volume_sold_records_from_sold_db(sold_db, suburb_collection_name, start_date_str, end_date_str):
    """
    Fetch quarterly sales counts from Target_Market_Sold_Last_12_Months.
    Returns list of dicts with 'period', 'year', 'quarter', 'sales_count'.
    """
    try:
        coll = sold_db[suburb_collection_name]
        pipeline = [
            {
                '$match': {
                    'property_type': 'House',
                    'sale_date': {'$gte': start_date_str, '$lte': end_date_str},
                },
            },
            {
                '$addFields': {
                    'timeline_date': {'$dateFromString': {'dateString': '$sale_date'}},
                },
            },
            {
                '$group': {
                    '_id': {
                        'year': {'$year': '$timeline_date'},
                        'quarter': {'$ceil': {'$divide': [{'$month': '$timeline_date'}, 3]}},
                    },
                    'sales_count': {'$sum': 1},
                },
            },
            {
                '$project': {
                    'period': {
                        '$concat': [
                            {'$toString': '$_id.year'},
                            '-Q',
                            {'$toString': '$_id.quarter'},
                        ],
                    },
                    'year': '$_id.year',
                    'quarter': '$_id.quarter',
                    'sales_count': 1,
                },
            },
        ]
        return list(coll.aggregate(pipeline))
    except Exception:
        return []


def calculate_sales_volume_data(gc_db, sold_db, suburb_collection_name):
    """
    Calculate Sales Volume chart data for a suburb.
    Merges data from Gold_Coast (historical timeline) and Target_Market_Sold_Last_12_Months (recent 12 months).
    Returns quarterly sales counts with YoY trends and seasonal averages.
    """
    print(f"    Calculating Sales Volume for {suburb_collection_name}...")

    try:
        collection = gc_db[suburb_collection_name]

        # Date bounds — query Gold_Coast for the FULL 3-year range (not just >12m cutoff).
        # Target_Market_Sold_Last_12_Months is supplementary; take max per quarter to avoid double-counting.
        end_date = datetime.now()
        start_date = end_date - timedelta(days=365 * 3)
        cutoff_12m = end_date - timedelta(days=365)
        start_date_str = start_date.strftime('%Y-%m-%d')
        end_date_str = end_date.strftime('%Y-%m-%d')
        cutoff_12m_str = cutoff_12m.strftime('%Y-%m-%d')

        # Query Gold_Coast for ALL sales in the 3-year window (full range, not just historical)
        pipeline = [
            {'$unwind': '$scraped_data.property_timeline'},
            {
                '$match': {
                    'scraped_data.property_timeline.is_sold': True,
                    'scraped_data.property_timeline.date': {
                        '$gte': start_date_str,
                        '$lte': end_date_str,
                    },
                    'scraped_data.features.property_type': 'House',
                },
            },
            {
                '$addFields': {
                    'timeline_date': {'$dateFromString': {'dateString': '$scraped_data.property_timeline.date'}},
                },
            },
            {
                '$group': {
                    '_id': {
                        'year': {'$year': '$timeline_date'},
                        'quarter': {'$ceil': {'$divide': [{'$month': '$timeline_date'}, 3]}},
                    },
                    'sales_count': {'$sum': 1},
                },
            },
            {
                '$project': {
                    'period': {
                        '$concat': [
                            {'$toString': '$_id.year'},
                            '-Q',
                            {'$toString': '$_id.quarter'},
                        ],
                    },
                    'year': '$_id.year',
                    'quarter': '$_id.quarter',
                    'sales_count': 1,
                },
            },
            {'$sort': {'year': 1, 'quarter': 1}},
        ]

        gc_results = list(collection.aggregate(pipeline))

        # Query Target_Market_Sold_Last_12_Months as supplementary source
        recent_results = _get_volume_sold_records_from_sold_db(sold_db, suburb_collection_name, cutoff_12m_str, end_date_str)

        # Query listing_status='sold' records (catches sales not yet in property_timeline)
        status_sold = _get_listing_status_sold(gc_db, suburb_collection_name, start_date_str, end_date_str)
        # Group listing_status sold by quarter
        status_quarter_counts = {}
        for r in status_sold:
            q = r.get("quarter", "")
            if q:
                status_quarter_counts[q] = status_quarter_counts.get(q, 0) + 1
        status_results = [
            {"period": q, "sales_count": c, "year": int(q[:4]), "quarter": int(q[-1])}
            for q, c in status_quarter_counts.items()
        ]

        print(f"      Sources: {len(gc_results)} quarters timeline + {len(recent_results)} quarters Target_Market + {len(status_results)} quarters listing_status")

        # Merge: per quarter, take the MAX of ALL THREE sources to avoid double-counting
        quarter_map_merged = {doc['period']: doc for doc in gc_results}
        for doc in recent_results + status_results:
            period = doc['period']
            if period in quarter_map_merged:
                quarter_map_merged[period] = {
                    **quarter_map_merged[period],
                    'sales_count': max(quarter_map_merged[period]['sales_count'], doc['sales_count']),
                }
            else:
                quarter_map_merged[period] = doc

        results = sorted(quarter_map_merged.values(), key=lambda d: (d['year'], d['quarter']))

        if not results:
            print(f"      ⚠️  No data found")
            return None

        # Build timeline with YoY calculations
        timeline = []
        quarter_map = {doc['period']: doc['sales_count'] for doc in results}

        for doc in results:
            period = doc['period']
            sales_count = doc['sales_count']

            # Calculate YoY change
            year = int(doc['year'])
            quarter = int(doc['quarter'])
            prev_year_period = f"{year - 1}-Q{quarter}"

            yoy_change = None
            if prev_year_period in quarter_map:
                prev_count = quarter_map[prev_year_period]
                if prev_count > 0:
                    yoy_change = round(((sales_count / prev_count) - 1) * 100, 1)

            timeline.append({
                'period': period,
                'sales_count': sales_count,
                'yoy_change': yoy_change,
            })

        # Calculate moving average (4-quarter)
        for i, item in enumerate(timeline):
            if i >= 3:
                recent_4 = [timeline[j]['sales_count'] for j in range(i - 3, i + 1)]
                item['moving_avg'] = round(mean(recent_4), 1)
            else:
                item['moving_avg'] = None

        # Rate limit cooldown before second heavy aggregation
        time.sleep(4)

        # ===== NEW: Calculate 10-year quarterly seasonal averages (excluding 2020-2021) =====
        print("      Calculating 10-year quarterly seasonal averages (excluding 2020-2021)...")

        # Query 10 years of data for seasonal calculation (full range from Gold_Coast)
        seasonal_start = datetime.now() - timedelta(days=365 * 10)
        seasonal_start_str = seasonal_start.strftime('%Y-%m-%d')

        seasonal_pipeline = [
            {'$unwind': '$scraped_data.property_timeline'},
            {
                '$match': {
                    'scraped_data.property_timeline.is_sold': True,
                    'scraped_data.property_timeline.date': {
                        '$gte': seasonal_start_str,
                        '$lte': end_date_str,
                    },
                    'scraped_data.features.property_type': 'House',
                },
            },
            {
                '$addFields': {
                    'timeline_date': {'$dateFromString': {'dateString': '$scraped_data.property_timeline.date'}},
                },
            },
            {
                '$group': {
                    '_id': {
                        'year': {'$year': '$timeline_date'},
                        'quarter': {'$ceil': {'$divide': [{'$month': '$timeline_date'}, 3]}},
                    },
                    'sales_count': {'$sum': 1},
                },
            },
            {
                '$project': {
                    'year': '$_id.year',
                    'quarter': '$_id.quarter',
                    'sales_count': 1,
                },
            },
        ]

        gc_seasonal_results = list(collection.aggregate(seasonal_pipeline))

        # Supplementary: Target_Market_Sold_Last_12_Months (take max per year-quarter)
        recent_seasonal = _get_volume_sold_records_from_sold_db(sold_db, suburb_collection_name, cutoff_12m_str, end_date_str)

        # Build year-quarter map from Gold_Coast, then merge Target_Market (max per quarter)
        yq_map = {}
        for doc in gc_seasonal_results:
            key = (doc['year'], doc['quarter'])
            yq_map[key] = doc['sales_count']
        for doc in recent_seasonal:
            year = doc.get('year')
            quarter = int(doc['quarter']) if doc.get('quarter') else None
            if year and quarter:
                key = (year, quarter)
                yq_map[key] = max(yq_map.get(key, 0), doc['sales_count'])

        # Group by quarter (Q1, Q2, Q3, Q4), excluding 2020, 2021, and current incomplete quarter
        current_year = datetime.now().year
        current_q = (datetime.now().month - 1) // 3 + 1
        seasonal_data = {1: [], 2: [], 3: [], 4: []}
        for (year, quarter), count in yq_map.items():
            if year in [2020, 2021]:
                continue
            if year == current_year and quarter == current_q:
                continue  # skip incomplete quarter from seasonal averages
            seasonal_data[quarter].append(count)

        # Calculate quarterly averages
        seasonal_trend = []
        for quarter_num in range(1, 5):
            if seasonal_data[quarter_num]:
                avg_sales = round(mean(seasonal_data[quarter_num]), 1)
                seasonal_trend.append({
                    'quarter': f'Q{quarter_num}',
                    'avg_sales_volume': avg_sales,
                    'sample_size': len(seasonal_data[quarter_num]),
                })

        print(f"      ✅ Calculated {len(seasonal_trend)} quarterly seasonal averages")

        # Calculate historical average across all quarters
        all_sales = [doc['sales_count'] for doc in results]
        historical_average = round(mean(all_sales), 1) if all_sales else 0

        # Calculate latest YoY change for the most recent COMPLETE quarter
        # (skip the current in-progress quarter)
        current_quarter_key = get_quarter_key(datetime.now())
        complete_timeline = [t for t in timeline if t['period'] != current_quarter_key]
        latest_yoy_change = complete_timeline[-1].get('yoy_change') if complete_timeline else 0

        result = {
            '_id': f"{suburb_collection_name}_sales_volume",
            'suburb': to_title_case(suburb_collection_name),
            'chart_type': 'sales_volume',
            'timeline': timeline,
            'seasonal_trend': seasonal_trend,
            'historical_average': historical_average,
            'yoy_change': latest_yoy_change if latest_yoy_change is not None else 0,
            'last_updated': datetime.utcnow(),
        }

        print(f"      ✅ {len(timeline)} quarters, avg={historical_average} sales/quarter")
        return result

    except Exception as e:
        print(f"      ❌ Error: {str(e)}")
        return None


def calculate_turnover_rate_data(gc_db, sold_db, suburb_collection_name):
    """
    Calculate annual Turnover Rate for a suburb.
    turnover_rate = (annual_house_sales / total_stock) * 100

    Uses dual-source merge matching the article pipeline methodology:
      - Gold_Coast.[suburb] (full timeline — no cutoff split for annual data)
      - Target_Market_Sold_Last_12_Months.[suburb] (recent flat docs, supplements Gold_Coast)

    total_stock = Gold_Coast.[suburb].count_documents({})  (all properties in historical DB)

    For each year, we take the max of (Gold_Coast count, Target_Market count) to avoid
    double-counting while ensuring the most complete figure.
    """
    print(f"    Calculating Turnover Rate for {suburb_collection_name}...")

    try:
        collection = gc_db[suburb_collection_name]

        # Total stock = all properties in Gold_Coast.[suburb]
        total_stock = collection.count_documents({})
        if total_stock == 0:
            print(f"      ⚠️  No properties in Gold_Coast.{suburb_collection_name}")
            return None

        print(f"      Total stock: {total_stock} properties")

        # Date bounds — 7 years of history (query full range, no cutoff split)
        end_date = datetime.now()
        start_date = end_date - timedelta(days=365 * 7)
        start_date_str = start_date.strftime('%Y-%m-%d')
        end_date_str = end_date.strftime('%Y-%m-%d')

        # ── Source 1: Gold_Coast full timeline (all sale events in window) ──
        pipeline = [
            {'$unwind': '$scraped_data.property_timeline'},
            {
                '$match': {
                    'scraped_data.property_timeline.date': {
                        '$gte': start_date_str,
                        '$lte': end_date_str,
                    },
                    'scraped_data.property_timeline.category': 'Sale',
                    'scraped_data.property_timeline.price': {'$gt': 50000},
                },
            },
            {
                '$addFields': {
                    'timeline_date': {'$dateFromString': {'dateString': '$scraped_data.property_timeline.date'}},
                },
            },
            {
                '$group': {
                    '_id': {'$year': '$timeline_date'},
                    'sales': {'$sum': 1},
                },
            },
            {
                '$project': {
                    'year': '$_id',
                    'sales': 1,
                },
            },
        ]

        gc_results = list(collection.aggregate(pipeline))

        # ── Source 2: Target_Market_Sold_Last_12_Months (all records) ──
        target_year_sales = {}
        try:
            sold_coll = sold_db[suburb_collection_name]
            sold_pipeline = [
                {
                    '$match': {
                        'property_type': 'House',
                        'sale_date': {'$gte': start_date_str, '$lte': end_date_str},
                    },
                },
                {
                    '$addFields': {
                        'parsed_date': {'$dateFromString': {'dateString': '$sale_date'}},
                    },
                },
                {
                    '$group': {
                        '_id': {'$year': '$parsed_date'},
                        'sales': {'$sum': 1},
                    },
                },
            ]
            for doc in sold_coll.aggregate(sold_pipeline):
                target_year_sales[doc['_id']] = doc['sales']
        except Exception:
            pass

        # ── Source 3: listing_status='sold' records (catches sales not yet in timeline) ──
        status_sold = _get_listing_status_sold(gc_db, suburb_collection_name, start_date_str, end_date_str)
        status_year_sales = {}
        for r in status_sold:
            y = r.get("year")
            if y:
                status_year_sales[y] = status_year_sales.get(y, 0) + 1

        print(f"      Sources: {len(gc_results)} years timeline + {len(target_year_sales)} years Target_Market + {len(status_year_sales)} years listing_status")

        # ── Merge: per year, take max of ALL THREE sources to avoid double-counting ──
        year_map = {}
        for doc in gc_results:
            year_map[doc['year']] = doc['sales']
        for year, count in target_year_sales.items():
            year_map[year] = max(year_map.get(year, 0), count)
        for year, count in status_year_sales.items():
            year_map[year] = max(year_map.get(year, 0), count)

        if not year_map:
            print(f"      ⚠️  No sales data found")
            return None

        # Exclude current year (incomplete — would show misleadingly low rate)
        current_year = end_date.year
        year_map.pop(current_year, None)

        # Build timeline sorted by year
        timeline = []
        for year in sorted(year_map.keys()):
            sales = year_map[year]
            rate = round(sales / total_stock * 100, 2)
            timeline.append({
                'year': year,
                'sales': sales,
                'turnover_rate': rate,
            })

        result = {
            '_id': f"{suburb_collection_name}_turnover_rate",
            'suburb': to_title_case(suburb_collection_name),
            'chart_type': 'turnover_rate',
            'total_stock': total_stock,
            'timeline': timeline,
            'last_updated': datetime.utcnow(),
        }

        latest = timeline[-1] if timeline else None
        if latest:
            print(f"      ✅ {len(timeline)} years, latest: {latest['year']} → {latest['turnover_rate']}%")
        return result

    except Exception as e:
        print(f"      ❌ Error: {str(e)}")
        return None


def precompute_suburb_charts(gc_db, sold_db, suburb_collection_name, charts=None):
    """
    Pre-compute chart types for a single suburb.
    Reads from Gold_Coast (historical) and Target_Market_Sold_Last_12_Months (recent).
    charts: set of chart types to compute (dom, cycle, volume, turnover).
    Returns list of result documents.
    """
    if charts is None:
        charts = {'dom', 'cycle', 'volume', 'turnover'}

    print(f"  Processing {suburb_collection_name}...")

    results = []

    # 1. Days on Market
    if 'dom' in charts:
        dom_data = calculate_days_on_market_data(gc_db, sold_db, suburb_collection_name)
        if dom_data:
            results.append(dom_data)

    # 2. Market Cycle Score
    if 'cycle' in charts:
        cycle_data = calculate_market_cycle_score(gc_db, sold_db, suburb_collection_name)
        if cycle_data:
            results.append(cycle_data)

    # 3. Sales Volume
    if 'volume' in charts:
        volume_data = calculate_sales_volume_data(gc_db, sold_db, suburb_collection_name)
        if volume_data:
            results.append(volume_data)

    # 4. Turnover Rate
    if 'turnover' in charts:
        turnover_data = calculate_turnover_rate_data(gc_db, sold_db, suburb_collection_name)
        if turnover_data:
            results.append(turnover_data)

    return results


def store_precomputed_data(db, data_list):
    """Store pre-computed data in database with retry logic"""
    if not data_list:
        return
    
    print("\nStoring pre-computed data in database...")
    print("-" * 80)
    
    precomputed_collection = db['precomputed_market_charts']
    
    # Create index on _id for fast lookups
    precomputed_collection.create_index([('_id', ASCENDING)])
    
    # Upsert all pre-computed data with retry logic
    for i, data in enumerate(data_list):
        max_retries = 3
        retry_count = 0
        
        while retry_count < max_retries:
            try:
                precomputed_collection.replace_one(
                    {'_id': data['_id']},
                    data,
                    upsert=True
                )
                break  # Success
                
            except WriteError as e:
                if 'TooManyRequests' in str(e) or e.code == 16500:
                    retry_count += 1
                    if retry_count < max_retries:
                        wait_time = 2 ** retry_count
                        print(f"  ⚠️  Rate limit hit for {data['_id']}, retrying in {wait_time}s...")
                        time.sleep(wait_time)
                    else:
                        print(f"  ❌ Failed to store {data['_id']} after {max_retries} retries")
                        raise
                else:
                    raise
        
        # Add delay between writes
        if i < len(data_list) - 1:
            time.sleep(0.2)
    
    print(f"✅ Stored {len(data_list)} pre-computed datasets")


def main(charts=None):
    """Main execution function. charts: set of chart types to compute (dom, cycle, volume, turnover)."""
    if charts is None:
        charts = {'dom', 'cycle', 'volume', 'turnover'}
    print("=" * 80)
    print("Pre-computing Market Charts Data")
    print("=" * 80)
    print()
    
    # Connect to database
    print("Connecting to Azure Cosmos DB...")
    client = get_db_connection()
    gc_db = client['Gold_Coast']                         # Historical property timelines + output destination
    sold_db = client['Target_Market_Sold_Last_12_Months'] # Recent 12 months sold data (flat structure)
    print("✅ Connected\n")
    print(f"  Source 1 (historical): Gold_Coast")
    print(f"  Source 2 (recent 12m): Target_Market_Sold_Last_12_Months")
    print(f"  Output:                Gold_Coast.precomputed_market_charts\n")

    # Use the 8 known target market suburbs
    suburb_collections = TARGET_MARKET_SUBURBS
    print(f"✅ Processing {len(suburb_collections)} target suburbs: {', '.join(suburb_collections)}\n")

    # Pre-compute charts for each suburb
    print("Pre-computing market charts for each suburb:")
    print("-" * 80)

    all_precomputed_data = []
    success_count = 0
    skip_count = 0

    print(f"  Chart types: {', '.join(sorted(charts))}\n")

    for i, suburb_name in enumerate(suburb_collections):
        results = precompute_suburb_charts(gc_db, sold_db, suburb_name, charts=charts)
        if results:
            all_precomputed_data.extend(results)
            success_count += len(results)
        else:
            skip_count += 1

        # Rate limiting
        if i < len(suburb_collections) - 1:
            time.sleep(0.5)

    print()

    # Store all pre-computed data into Gold_Coast.precomputed_market_charts (where API reads from)
    store_precomputed_data(gc_db, all_precomputed_data)
    print()
    
    # Summary
    print("=" * 80)
    print("SUMMARY")
    print("=" * 80)
    print(f"✅ Successfully processed: {success_count} charts")
    print(f"⚠️  Skipped (no data):     {skip_count} suburbs")
    print()
    print("Pre-computation complete! The Netlify function can now use this data.")
    print("Run this script nightly to keep data fresh.")
    print("=" * 80)
    
    client.close()


if __name__ == '__main__':
    import argparse
    parser = argparse.ArgumentParser(description='Pre-compute market chart data')
    parser.add_argument('--charts', nargs='+',
                        choices=['dom', 'cycle', 'volume', 'turnover', 'all'],
                        default=['all'],
                        help='Which chart types to compute (default: all)')
    args = parser.parse_args()
    chart_set = set(args.charts)
    if 'all' in chart_set:
        chart_set = {'dom', 'cycle', 'volume', 'turnover'}
    main(charts=chart_set)
