#!/usr/bin/env python3
"""
Enrich Cadastral Properties
One-off script to enrich cadastral (non-listed) properties with:
  1. property_insights (rarity analysis from suburb statistics)
  2. enriched_data (lot_size, transactions, capital gain)

Only processes target market suburbs: robina, burleigh_waters, varsity_lakes.
Only processes properties with listing_status=None that have scraped_data.

Usage:
    python3 scripts/enrich_cadastral.py                  # all target suburbs
    python3 scripts/enrich_cadastral.py --suburb robina   # single suburb
    python3 scripts/enrich_cadastral.py --limit 100       # test run
    python3 scripts/enrich_cadastral.py --dry-run         # count only
"""

import argparse
import json
import os
import sys
import time
from datetime import datetime
from pymongo import MongoClient
from pymongo.errors import OperationFailure
from bson import ObjectId

TARGET_SUBURBS = ['robina', 'burleigh_waters', 'varsity_lakes']


def cosmos_retry(func, *args, max_retries=5, **kwargs):
    for attempt in range(max_retries):
        try:
            return func(*args, **kwargs)
        except OperationFailure as e:
            if e.code == 16500 and attempt < max_retries - 1:
                wait = max(getattr(e, 'details', {}).get('retryAfterMs', 2000) / 1000, 2)
                time.sleep(wait * (attempt + 1))
                continue
            raise


def extract_bedrooms(doc):
    """Extract bedroom count from various sources."""
    if doc.get('bedrooms'):
        return doc['bedrooms']
    sd = doc.get('scraped_data', {})
    features = sd.get('features', {})
    if features.get('bedrooms'):
        return features['bedrooms']
    return None


def extract_bathrooms(doc):
    if doc.get('bathrooms'):
        return doc['bathrooms']
    sd = doc.get('scraped_data', {})
    return sd.get('features', {}).get('bathrooms')


def extract_lot_size(doc):
    if doc.get('lot_size_sqm'):
        return doc['lot_size_sqm']
    if doc.get('lot_size_calc_sqm'):
        return doc['lot_size_calc_sqm']
    sd = doc.get('scraped_data', {})
    return sd.get('features', {}).get('land_size')


def extract_property_type(doc):
    if doc.get('classified_property_type'):
        return doc['classified_property_type']
    sd = doc.get('scraped_data', {})
    return sd.get('features', {}).get('property_type', 'House')


def extract_transactions(doc):
    """Extract sale transactions from scraped_data.property_timeline."""
    sd = doc.get('scraped_data', {})
    timeline = sd.get('property_timeline', [])
    txns = []
    for ev in timeline:
        if not isinstance(ev, dict):
            continue
        is_sale = ev.get('is_major_event') or ev.get('category') == 'Sale'
        if not is_sale or not ev.get('date') or ev.get('price') is None:
            continue
        try:
            price = float(ev['price'])
            if price <= 0:
                continue
            txns.append({
                'date': str(ev['date']),
                'price': price,
                'source': ev.get('agency_name') or ev.get('source') or 'Sale',
            })
        except (ValueError, TypeError):
            continue
    return txns


def compute_capital_gain(transactions, suburb_medians_coll, suburb):
    """Compute capital gain from transactions and suburb median prices."""
    if len(transactions) < 1:
        return None

    # Sort by date, get most recent sale
    sorted_txns = sorted(transactions, key=lambda t: t['date'], reverse=True)
    last_sale = sorted_txns[0]
    purchase_price = last_sale['price']
    purchase_date = last_sale['date']

    if not purchase_price or purchase_price <= 0:
        return None

    # Get suburb median for indexing
    try:
        suburb_display = suburb.replace('_', ' ').title()
        median_doc = cosmos_retry(
            suburb_medians_coll.find_one,
            {'suburb': suburb_display}
        )
    except Exception:
        median_doc = None

    if not median_doc:
        return None

    quarterly = median_doc.get('quarterly_medians', [])
    if not quarterly:
        return None

    # Find purchase quarter and latest quarter
    purchase_year = int(purchase_date[:4]) if len(purchase_date) >= 4 else None
    if not purchase_year:
        return None

    latest = quarterly[-1] if quarterly else None
    if not latest or not latest.get('median_price'):
        return None

    # Find nearest quarter to purchase
    purchase_quarter = None
    for q in quarterly:
        q_year = q.get('year')
        if q_year and q_year <= purchase_year and q.get('median_price'):
            purchase_quarter = q

    if not purchase_quarter or not purchase_quarter.get('median_price'):
        return None

    # Indexed value = purchase_price * (latest_median / purchase_median)
    index_ratio = latest['median_price'] / purchase_quarter['median_price']
    indexed_value = round(purchase_price * index_ratio)
    capital_gain_pct = round((index_ratio - 1) * 100, 1)

    years = max(1, (int(latest.get('year', 2026)) - purchase_year))
    annual_growth = round(capital_gain_pct / years, 1)

    return {
        'purchase_price': purchase_price,
        'purchase_date': purchase_date,
        'indexed_value': indexed_value,
        'capital_gain_pct': capital_gain_pct,
        'annual_growth_pct': annual_growth,
    }


def compute_bedroom_percentile(bedrooms, distribution):
    if not bedrooms or not distribution:
        return None
    cumulative = 0
    total = sum(distribution.values())
    if total == 0:
        return None
    for bed_count in sorted(distribution.keys(), key=lambda x: int(x)):
        cumulative += distribution[bed_count]
        if int(bed_count) >= bedrooms:
            return int(cumulative / total * 100)
    return 99


def build_rarity_insights(bedrooms, lot_size, suburb_stats, for_sale_count):
    """Build property_insights from suburb statistics."""
    insights = {}
    stats = suburb_stats.get('statistics', {})
    suburb_display = suburb_stats.get('suburb', '').replace('_', ' ').title()

    # Bedroom insights
    if bedrooms:
        bed_stats = stats.get('bedrooms', {})
        bed_dist = bed_stats.get('distribution', {})
        bed_median = bed_stats.get('median')
        percentile = compute_bedroom_percentile(bedrooms, bed_dist)

        rarity = []
        count_at = bed_dist.get(str(bedrooms), 0) if bed_dist else 0
        total = for_sale_count or sum(bed_dist.values()) if bed_dist else 0

        if count_at == 1 and total > 5:
            rarity.append({
                'type': 'ONLY_1',
                'feature': 'bedrooms',
                'label': f'Only {bedrooms}-bedroom home currently for sale in {suburb_display}',
                'urgencyLevel': 'high',
                'rank': 1,
            })
        elif count_at <= 3 and total > 10:
            rarity.append({
                'type': 'TOP_3',
                'feature': 'bedrooms',
                'label': f'One of only {count_at} {bedrooms}-bedroom homes for sale in {suburb_display}',
                'urgencyLevel': 'medium',
                'rank': count_at,
            })

        insights['bedrooms'] = {
            'value': bedrooms,
            'rarity_insights': rarity,
            'suburbComparison': {
                'median': bed_median,
                'percentile': percentile,
                'suburb': suburb_display,
            }
        }

    # Lot size insights
    if lot_size:
        lot_stats = stats.get('lot_size', {})
        lot_median = lot_stats.get('median')
        lot_p = lot_stats.get('percentiles', {})

        percentile = None
        if lot_p:
            pts = [(lot_p.get('p10', 0), 10), (lot_p.get('p25', 0), 25),
                   (lot_p.get('p50', 0), 50), (lot_p.get('p75', 0), 75),
                   (lot_p.get('p90', 0), 90)]
            for i in range(len(pts) - 1):
                lo_v, lo_pct = pts[i]
                hi_v, hi_pct = pts[i + 1]
                if lo_v and hi_v and lo_v <= lot_size <= hi_v:
                    frac = (lot_size - lo_v) / max(hi_v - lo_v, 1)
                    percentile = int(lo_pct + frac * (hi_pct - lo_pct))
                    break
            if percentile is None and lot_p.get('p90') and lot_size > lot_p['p90']:
                percentile = 95

        rarity = []
        if percentile and percentile >= 90:
            rarity.append({
                'type': 'RARE',
                'feature': 'lot_size',
                'label': f'Larger than {percentile}% of properties in {suburb_display}',
                'urgencyLevel': 'medium',
            })

        insights['lot_size'] = {
            'value': lot_size,
            'rarity_insights': rarity,
            'suburbComparison': {
                'median': lot_median,
                'percentile': percentile,
                'suburb': suburb_display,
            }
        }

    return insights if insights else None


def process_suburb(db, suburb, stats_coll, medians_coll, limit=None, dry_run=False):
    """Process all cadastral properties in a suburb."""
    coll = db[suburb]

    # Find cadastral properties with scraped data but no property_insights
    # Use $nin to match docs where listing_status is null/missing (cadastral)
    query = {
        'listing_status': {'$nin': ['for_sale', 'sold']},
        'scraped_data': {'$exists': True},
        'property_insights': {'$exists': False},
    }

    # Skip expensive count_documents on large collections — just estimate
    if dry_run:
        total = cosmos_retry(coll.count_documents, query)
        print(f"\n  {suburb}: {total} cadastral properties need insights", flush=True)
        return 0, 0

    print(f"\n  {suburb}: starting enrichment (skipping count for speed)...", flush=True)
    total = 0  # will count as we go

    # Get suburb stats for rarity comparison
    suburb_display = suburb.replace('_', ' ').title()
    suburb_stats = cosmos_retry(stats_coll.find_one, {'suburb': suburb_display, 'property_type': 'House'})
    if not suburb_stats:
        suburb_stats = cosmos_retry(stats_coll.find_one, {'suburb': suburb})

    # Count for-sale properties for rarity context
    for_sale_count = cosmos_retry(coll.count_documents, {'listing_status': 'for_sale'})
    time.sleep(1)

    processed = 0
    enriched = 0
    batch_size = 50

    cursor = coll.find(query).batch_size(batch_size)
    if limit:
        cursor = cursor.limit(limit)

    while True:
        try:
            doc = next(cursor)
        except StopIteration:
            break
        except Exception as cursor_err:
            # Handle 429 during cursor batch fetch
            if '429' in str(cursor_err) or '16500' in str(cursor_err):
                print(f"    Cursor 429 at {processed} docs, sleeping 10s...", flush=True)
                time.sleep(10)
                # Re-create cursor skipping already-processed docs
                cursor = coll.find(query).batch_size(batch_size).skip(processed)
                if limit:
                    remaining = limit - processed
                    if remaining <= 0:
                        break
                    cursor = cursor.limit(remaining)
                continue
            raise

        try:
            update = {}

            bedrooms = extract_bedrooms(doc)
            lot_size = extract_lot_size(doc)
            transactions = extract_transactions(doc)

            # Build property_insights
            if suburb_stats and (bedrooms or lot_size):
                insights = build_rarity_insights(bedrooms, lot_size, suburb_stats, for_sale_count)
                if insights:
                    update['property_insights'] = insights
                    update['property_insights_updated'] = datetime.utcnow().isoformat()

            # Build enriched_data
            enriched_data = {}
            if lot_size:
                enriched_data['lot_size_sqm'] = lot_size
            if transactions:
                enriched_data['transactions'] = transactions
                cap_gain = compute_capital_gain(transactions, medians_coll, suburb)
                if cap_gain:
                    enriched_data['capital_gain'] = cap_gain

            if enriched_data:
                update['enriched_data'] = enriched_data

            # Also set bedrooms/bathrooms at top level if missing
            if bedrooms and not doc.get('bedrooms'):
                update['bedrooms'] = bedrooms
            baths = extract_bathrooms(doc)
            if baths and not doc.get('bathrooms'):
                update['bathrooms'] = baths

            if update:
                cosmos_retry(coll.update_one, {'_id': doc['_id']}, {'$set': update})
                enriched += 1
            else:
                # Mark as processed even if no insights (to avoid re-processing)
                cosmos_retry(coll.update_one, {'_id': doc['_id']}, {
                    '$set': {'property_insights': {}, 'property_insights_updated': datetime.utcnow().isoformat()}
                })

            processed += 1
            if processed % 100 == 0:
                print(f"    {processed} processed, {enriched} enriched", flush=True)

            # Rate limit: ~2 ops per doc, need to stay under 400 RU/s
            time.sleep(0.3)

        except Exception as e:
            if '429' in str(e) or '16500' in str(e):
                time.sleep(5)
                continue
            print(f"    Error on {doc.get('complete_address', doc['_id'])}: {e}", flush=True)
            continue

    print(f"    Done: {processed} processed, {enriched} enriched", flush=True)
    return processed, enriched


def main():
    parser = argparse.ArgumentParser(description='Enrich cadastral properties')
    parser.add_argument('--suburb', help='Single suburb to process')
    parser.add_argument('--limit', type=int, help='Limit docs per suburb')
    parser.add_argument('--dry-run', action='store_true', help='Count only')
    args = parser.parse_args()

    uri = os.environ.get('COSMOS_CONNECTION_STRING')
    if not uri:
        print("ERROR: COSMOS_CONNECTION_STRING not set")
        sys.exit(1)

    client = MongoClient(uri, retryWrites=False, tls=True, tlsAllowInvalidCertificates=True)
    db = client['Gold_Coast']
    stats_coll = db['suburb_statistics']
    medians_coll = db['suburb_median_prices']

    suburbs = [args.suburb] if args.suburb else TARGET_SUBURBS

    print(f"Cadastral Enrichment — {datetime.now().strftime('%Y-%m-%d %H:%M')}", flush=True)
    print(f"Suburbs: {', '.join(suburbs)}", flush=True)
    if args.limit:
        print(f"Limit: {args.limit} per suburb", flush=True)
    if args.dry_run:
        print("DRY RUN — no writes", flush=True)

    total_processed = 0
    total_enriched = 0

    for suburb in suburbs:
        p, e = process_suburb(db, suburb, stats_coll, medians_coll, args.limit, args.dry_run)
        total_processed += p
        total_enriched += e
        time.sleep(3)

    print(f"\n{'='*60}", flush=True)
    print(f"Total: {total_processed} processed, {total_enriched} enriched", flush=True)
    client.close()


if __name__ == '__main__':
    main()
