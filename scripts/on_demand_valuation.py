#!/usr/bin/env python3
"""
On-Demand Property Valuation Script

Runs the full CatBoost ML valuation pipeline for a single property, triggered
by the Netlify analyse-property function via a MongoDB request queue.

Usage:
    python3 scripts/on_demand_valuation.py --suburb robina --property-id 690bd7da8b8f546592602972
    python3 scripts/on_demand_valuation.py --poll   # Poll for queued requests

Steps:
    1. Load property from Gold_Coast.[suburb]
    2. Resolve coordinates (cadastral DB → Nominatim fallback)
    3. Enrich with OSM features if missing
    4. Run ComprehensiveFeatureCalculator (126 features)
    5. Run FeatureAligner (fill missing with defaults)
    6. Run CatBoost model prediction → iteration_08_valuation
    7. Run precompute_valuations logic → valuation_data (NPUI, comparables,
       confidence intervals, adjustment rates, verification)
    8. Store both fields on the property document
"""

import argparse
import json
import os
import sys
import time
import logging
from datetime import datetime
from pathlib import Path
from bson import ObjectId

# Environment setup
from dotenv import load_dotenv
load_dotenv(Path(__file__).parent.parent / '.env')

# Add production valuation to sys.path
VALUATION_DIR = Path('/home/fields/Property_Valuation/04_Production_Valuation')
PRECOMPUTE_DIR = Path('/home/fields/Feilds_Website/07_Valuation_Comps')
sys.path.insert(0, str(VALUATION_DIR))
sys.path.insert(0, str(PRECOMPUTE_DIR))

import pymongo
from pymongo.errors import OperationFailure

# Production valuation imports
import config
from osm_enrichment import OSMEnricher
from feature_calculator_v2 import ComprehensiveFeatureCalculator
from feature_aligner import FeatureAligner
from catboost import CatBoostRegressor

# Precompute valuation imports
from precompute_valuations import (
    precompute_property_valuation,
    _load_sold_comparables,
    _preload_gc_coordinates,
    _preload_gc_timelines,
    get_db_connection,
)

logging.basicConfig(
    level=logging.INFO,
    format='[%(asctime)s] [%(levelname)s] %(message)s',
    datefmt='%Y-%m-%d %H:%M:%S'
)
logger = logging.getLogger(__name__)


def _geocode_with_nominatim(address, suburb=None):
    """Geocode an address using Nominatim. Returns {LATITUDE, LONGITUDE} or None."""
    import requests
    import re

    address = (address or '').strip()
    if not address:
        return None

    # Clean address
    address = re.sub(r'^ID:\d+/', '', address)
    address = re.sub(r'^Type\s+\w+/', '', address, flags=re.IGNORECASE)
    address = re.sub(r'^(\d+)-\d+\s', r'\1 ', address)
    m = re.match(r'^\d+/(\d+)-\d+\s(.+)', address)
    if m:
        address = f'{m.group(1)} {m.group(2)}'
    m2 = re.match(r'^\d{3,}/(\d+\s.+)', address)
    if m2:
        address = m2.group(1)

    address_parts = [address]
    if suburb:
        address_parts.append(suburb)
    address_parts.extend(['QLD', 'Australia'])
    full_address = ', '.join(address_parts)

    try:
        time.sleep(1.0)
        resp = requests.get(
            'https://nominatim.openstreetmap.org/search',
            params={'q': full_address, 'format': 'json', 'limit': 1, 'addressdetails': 1},
            headers={'User-Agent': 'FieldsPropertyValuation/1.0'},
            timeout=10,
        )
        resp.raise_for_status()
        results = resp.json()
        if results:
            return {
                'LATITUDE': float(results[0]['lat']),
                'LONGITUDE': float(results[0]['lon']),
            }
    except Exception as e:
        logger.warning(f'Nominatim geocoding failed: {e}')
    return None


def resolve_coordinates(doc, db, suburb_key):
    """Resolve LATITUDE/LONGITUDE from multiple sources."""
    # 1. geocoded_coordinates
    geo = doc.get('geocoded_coordinates') or {}
    if geo.get('latitude') and geo.get('longitude'):
        try:
            return float(geo['latitude']), float(geo['longitude'])
        except (ValueError, TypeError):
            pass

    # 2. Direct fields
    lat = doc.get('LATITUDE') or doc.get('latitude')
    lon = doc.get('LONGITUDE') or doc.get('longitude')
    if lat is not None and lon is not None:
        try:
            return float(lat), float(lon)
        except (ValueError, TypeError):
            pass

    # 3. Gold_Coast cadastral cross-reference
    import re
    street_addr = doc.get('street_address') or doc.get('address', '')
    if street_addr and suburb_key:
        # Parse street number and name for lookup
        cleaned = re.sub(r'^\d+/', '', street_addr).strip()
        m = re.match(r'^(\d+(?:-\d+)?)[A-Za-z]?\s+(.+)', cleaned)
        if m:
            street_no = m.group(1).split('-')[0]
            street_name = m.group(2).lower()
            try:
                gc_doc = db[suburb_key].find_one(
                    {'STREET_NO_1': street_no, 'LATITUDE': {'$exists': True}},
                    {'LATITUDE': 1, 'LONGITUDE': 1}
                )
                if gc_doc and gc_doc.get('LATITUDE'):
                    return float(gc_doc['LATITUDE']), float(gc_doc['LONGITUDE'])
            except Exception:
                pass

    # 4. Nominatim fallback
    suburb_display = suburb_key.replace('_', ' ').title() if suburb_key else None
    result = _geocode_with_nominatim(street_addr, suburb_display)
    if result:
        # Cache for future use
        try:
            db[suburb_key].update_one(
                {'_id': doc['_id']},
                {'$set': {
                    'geocoded_coordinates': {
                        'latitude': result['LATITUDE'],
                        'longitude': result['LONGITUDE'],
                        'source': 'nominatim',
                        'geocoded_at': datetime.now(),
                    }
                }}
            )
        except Exception:
            pass
        return result['LATITUDE'], result['LONGITUDE']

    return None, None


def run_catboost_valuation(doc, mongo_client):
    """Run CatBoost model prediction. Returns iteration_08_valuation dict or None."""
    logger.info('  Running CatBoost feature calculation...')

    # Initialize components
    feature_calculator = ComprehensiveFeatureCalculator(mongo_client)
    feature_aligner = FeatureAligner()

    model_path = config.MODEL_DIR / config.MODEL_FILE
    if not model_path.exists():
        logger.error(f'Model file not found: {model_path}')
        return None

    model = CatBoostRegressor()
    model.load_model(str(model_path))

    # Calculate all 126 features
    features = feature_calculator.calculate_all_features(doc)
    summary = feature_calculator.get_feature_summary(features)
    logger.info(f'  Calculated {summary["total_features"]} features ({summary["coverage_pct"]:.1f}% coverage)')

    # Align features to model expectations
    aligned = feature_aligner.align_features(features)
    feature_df = feature_aligner.features_to_dataframe(aligned)

    # Predict
    predicted_value = float(model.predict(feature_df)[0])
    logger.info(f'  CatBoost predicted value: ${predicted_value:,.0f}')

    return {
        'predicted_value': predicted_value,
        'confidence': 'medium',
        'model_version': 'iteration_08_phase1',
        'valuation_date': datetime.now(),
        'feature_coverage': {
            'total_features': summary['total_features'],
            'populated_features': summary['non_null_features'],
            'coverage_pct': round(summary['coverage_pct'], 1),
        },
    }


def run_precompute_valuation(db, doc, suburb_key, sold_by_suburb,
                              gc_coord_lookup, gc_timeline_lookup):
    """Run the full precompute valuation pipeline. Returns valuation_data dict or None."""
    logger.info('  Running precompute valuation (NPUI, comparables, confidence)...')

    doc['_collection'] = suburb_key
    start = time.time()

    valuation_data = precompute_property_valuation(
        db, doc, None, sold_by_suburb,
        gc_coord_lookup, gc_timeline_lookup,
    )

    elapsed_ms = int((time.time() - start) * 1000)
    if valuation_data:
        valuation_data.setdefault('metadata', {})['computation_time_ms'] = elapsed_ms
        confidence = valuation_data.get('confidence', {})
        reconciled = confidence.get('reconciled_valuation')
        conf_level = confidence.get('confidence', 'unknown')
        if reconciled:
            logger.info(f'  Reconciled valuation: ${reconciled:,.0f} (confidence: {conf_level})')
        else:
            logger.info(f'  Valuation data computed ({elapsed_ms}ms), confidence: {conf_level}')
    else:
        logger.warning('  Precompute returned None (insufficient data)')

    return valuation_data


def valuate_single_property(suburb_key, property_id_str):
    """Full valuation pipeline for a single property."""
    logger.info(f'Starting on-demand valuation: suburb={suburb_key}, id={property_id_str}')

    # Connect
    client = get_db_connection()
    db = client['Gold_Coast']

    # Load property
    try:
        oid = ObjectId(property_id_str)
    except Exception:
        logger.error(f'Invalid ObjectId: {property_id_str}')
        return False

    doc = db[suburb_key].find_one({'_id': oid})
    if not doc:
        logger.error(f'Property not found: Gold_Coast.{suburb_key} / {property_id_str}')
        return False

    address = doc.get('address') or doc.get('complete_address') or 'Unknown'
    logger.info(f'  Property: {address}')

    # Step 1: Resolve coordinates
    lat, lon = resolve_coordinates(doc, db, suburb_key)
    if lat is None or lon is None:
        logger.error('  Cannot resolve coordinates — valuation requires lat/lon')
        return False

    doc['LATITUDE'] = lat
    doc['LONGITUDE'] = lon
    logger.info(f'  Coordinates: ({lat:.6f}, {lon:.6f})')

    # Step 2: OSM enrichment
    osm_enricher = OSMEnricher()
    has_osm = all(doc.get(f) is not None for f in config.OSM_REQUIRED_FIELDS[:3])
    if not has_osm:
        logger.info('  Running OSM enrichment...')
        try:
            osm_enricher.enrich_property(doc, db[suburb_key])
            logger.info('  OSM enrichment complete')
        except Exception as e:
            logger.warning(f'  OSM enrichment failed (non-fatal): {e}')

    # Step 3: CatBoost valuation
    catboost_result = run_catboost_valuation(doc, client)

    # Step 4: Precompute valuation data (NPUI, comparables, confidence intervals)
    logger.info('  Loading sold comparables...')
    sold_by_suburb = _load_sold_comparables(client)
    total_sold = sum(len(v) for v in sold_by_suburb.values())
    logger.info(f'  Loaded {total_sold} sold records')

    # Pre-load coordinates and timelines for the target suburb + neighbouring suburbs
    target_suburbs = [suburb_key]
    # Add any suburbs that have sold data for comparable lookups
    for sk in sold_by_suburb:
        if sk not in target_suburbs:
            target_suburbs.append(sk)

    gc_coord_lookup = _preload_gc_coordinates(client, target_suburbs)
    gc_timeline_lookup = _preload_gc_timelines(client, target_suburbs)

    valuation_data = run_precompute_valuation(
        db, doc, suburb_key, sold_by_suburb,
        gc_coord_lookup, gc_timeline_lookup,
    )

    # Step 5: Store results
    update_fields = {
        'last_valuation_date': datetime.now(),
        'on_demand_valuation': True,
    }

    if catboost_result:
        update_fields['iteration_08_valuation'] = catboost_result

    if valuation_data:
        update_fields['valuation_data'] = valuation_data

    try:
        result = db[suburb_key].update_one(
            {'_id': oid},
            {'$set': update_fields}
        )
        if result.modified_count > 0:
            logger.info(f'  Stored valuation data on Gold_Coast.{suburb_key}/{property_id_str}')
        else:
            logger.warning('  update_one matched but did not modify (data may be identical)')
    except Exception as e:
        logger.error(f'  Failed to store valuation: {e}')
        return False

    logger.info('  On-demand valuation complete')
    client.close()
    return True


def poll_for_requests():
    """Poll MongoDB for queued valuation requests and process them."""
    logger.info('Polling for on-demand valuation requests...')

    client = get_db_connection()
    monitor_db = client['system_monitor']
    queue = monitor_db['valuation_requests']

    # Find pending requests, oldest first
    pending = list(queue.find({'status': 'pending'}).sort('requested_at', 1).limit(5))

    if not pending:
        logger.info('No pending valuation requests')
        client.close()
        return

    logger.info(f'Found {len(pending)} pending request(s)')

    for req in pending:
        req_id = req['_id']
        suburb_key = req.get('suburb')
        property_id = req.get('property_id')

        # Mark as processing
        queue.update_one(
            {'_id': req_id},
            {'$set': {'status': 'processing', 'started_at': datetime.utcnow()}}
        )
        client.close()

        try:
            success = valuate_single_property(suburb_key, property_id)

            # Re-connect to update status
            client = get_db_connection()
            monitor_db = client['system_monitor']
            queue = monitor_db['valuation_requests']

            if success:
                queue.update_one(
                    {'_id': req_id},
                    {'$set': {
                        'status': 'completed',
                        'completed_at': datetime.utcnow(),
                    }}
                )
                logger.info(f'  Request {req_id} completed successfully')
            else:
                queue.update_one(
                    {'_id': req_id},
                    {'$set': {
                        'status': 'failed',
                        'completed_at': datetime.utcnow(),
                        'error': 'Valuation pipeline returned False',
                    }}
                )
                logger.error(f'  Request {req_id} failed')
        except Exception as e:
            logger.error(f'  Request {req_id} exception: {e}')
            try:
                client = get_db_connection()
                client['system_monitor']['valuation_requests'].update_one(
                    {'_id': req_id},
                    {'$set': {
                        'status': 'failed',
                        'completed_at': datetime.utcnow(),
                        'error': str(e),
                    }}
                )
            except Exception:
                pass

    client.close()


def main():
    parser = argparse.ArgumentParser(description='On-demand property valuation')
    parser.add_argument('--suburb', type=str, help='Suburb collection name (e.g. robina)')
    parser.add_argument('--property-id', dest='property_id', type=str,
                        help='Property ObjectId')
    parser.add_argument('--poll', action='store_true',
                        help='Poll for queued requests')
    args = parser.parse_args()

    if args.poll:
        poll_for_requests()
    elif args.suburb and args.property_id:
        success = valuate_single_property(args.suburb, args.property_id)
        sys.exit(0 if success else 1)
    else:
        parser.print_help()
        sys.exit(1)


if __name__ == '__main__':
    main()
