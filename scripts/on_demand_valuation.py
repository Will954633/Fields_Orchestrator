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
    4. GPT Vision enrichment (if property has photos but no analysis)
    5. Run ComprehensiveFeatureCalculator (126 features)
    6. Run FeatureAligner (fill missing with defaults)
    7. Run CatBoost model prediction → iteration_08_valuation
    8. Run precompute_valuations logic → valuation_data (NPUI, comparables,
       confidence intervals, adjustment rates, verification)
    9. Store all fields on the property document
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
# Also load OpenAI key from enrichment script env
load_dotenv(Path(
    '/home/fields/Property_Data_Scraping/03_Gold_Coast/'
    'Gold_Coast_Wide_Currently_For_Sale_AND_Recently_Sold/'
    'Ollama_Property_Analysis/.env'
))

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

# ---------------------------------------------------------------------------
# GPT VISION ENRICHMENT (photo + floor plan analysis)
# ---------------------------------------------------------------------------

GPT_MODEL = "gpt-5-nano-2025-08-07"
GPT_MAX_TOKENS = 16000
GPT_MAX_PHOTOS = 20
GPT_IMAGE_TIMEOUT = 15
GPT_REQUEST_TIMEOUT = 180

# Lazy-loaded — only imported if we actually need GPT enrichment
_openai_client = None


def _get_openai_client():
    global _openai_client
    if _openai_client is None:
        from openai import OpenAI
        api_key = os.environ.get('OPENAI_API_KEY')
        if not api_key:
            raise RuntimeError('OPENAI_API_KEY not set — cannot run GPT enrichment')
        _openai_client = OpenAI(api_key=api_key)
    return _openai_client


def _image_key(url):
    import re
    match = re.search(r'(\d{10}_\d+_\d+_\d+_\d+)', url)
    return match.group(1) if match else url


def _clean_image_urls(raw_urls):
    best = {}
    for url in raw_urls:
        if not url or not isinstance(url, str):
            continue
        url = url.rstrip('\\').strip()
        key = _image_key(url)
        if key not in best:
            best[key] = url
        elif 'rimh2.domainstatic.com' in url:
            best[key] = url
    return list(best.values())[:GPT_MAX_PHOTOS]


def _url_to_base64(url):
    import base64
    from io import BytesIO
    import requests
    from PIL import Image
    try:
        resp = requests.get(url, timeout=GPT_IMAGE_TIMEOUT)
        resp.raise_for_status()
        img = Image.open(BytesIO(resp.content)).convert("RGB")
        buf = BytesIO()
        img.save(buf, format="JPEG", quality=85)
        encoded = base64.b64encode(buf.getvalue()).decode("utf-8")
        return f"data:image/jpeg;base64,{encoded}"
    except Exception:
        return None


def _build_image_content(urls):
    blocks = []
    for url in urls:
        data_uri = _url_to_base64(url)
        if data_uri:
            blocks.append({
                "type": "image_url",
                "image_url": {"url": data_uri, "detail": "high"}
            })
    return blocks


def _call_gpt(system_prompt, user_prompt, image_content):
    import json as _json
    client = _get_openai_client()
    messages = [
        {"role": "system", "content": system_prompt},
        {"role": "user", "content": [{"type": "text", "text": user_prompt}] + image_content}
    ]
    response = client.chat.completions.create(
        model=GPT_MODEL,
        messages=messages,
        max_completion_tokens=GPT_MAX_TOKENS,
        response_format={"type": "json_object"},
        timeout=GPT_REQUEST_TIMEOUT,
    )
    content = response.choices[0].message.content
    if not content or not content.strip():
        raise ValueError("Empty response from GPT")
    return _json.loads(content)


# Import prompts from the enrichment script directory
def _get_prompts():
    """Load photo and floor plan prompts from the enrichment script."""
    enrichment_dir = Path(
        '/home/fields/Property_Data_Scraping/03_Gold_Coast/'
        'Gold_Coast_Wide_Currently_For_Sale_AND_Recently_Sold/'
        'Ollama_Property_Analysis'
    )
    sys.path.insert(0, str(enrichment_dir))
    try:
        from enrich_for_sale_batch import PHOTO_ANALYSIS_PROMPT, FLOOR_PLAN_PROMPT
        return PHOTO_ANALYSIS_PROMPT, FLOOR_PLAN_PROMPT
    finally:
        sys.path.pop(0)


def run_gpt_enrichment(doc, collection):
    """Run GPT Vision photo + floor plan analysis on a single property.

    Returns dict with keys: property_valuation_data, floor_plan_analysis,
    processing_status, or None if no photos.
    """
    raw_images = doc.get('property_images', [])
    raw_floor_plans = doc.get('floor_plans', [])

    photo_urls = _clean_image_urls(raw_images)
    floor_plan_urls = [u.rstrip('\\').strip() for u in raw_floor_plans
                       if u and isinstance(u, str)]

    if not photo_urls:
        logger.info('  No photos available — skipping GPT enrichment')
        return None

    logger.info(f'  Running GPT Vision enrichment ({len(photo_urls)} photos, '
                f'{len(floor_plan_urls)} floor plans)...')

    PHOTO_PROMPT, FLOOR_PLAN_PROMPT = _get_prompts()

    # Call 1: Photo analysis
    start = time.time()
    image_content = _build_image_content(photo_urls)
    if not image_content:
        logger.warning('  Could not download any photos — skipping GPT enrichment')
        return None

    photo_result = _call_gpt(
        system_prompt="You are a professional property valuer with expertise in market comparison analysis.",
        user_prompt=PHOTO_PROMPT,
        image_content=image_content,
    )
    photo_elapsed = time.time() - start
    logger.info(f'  Photo analysis complete ({photo_elapsed:.1f}s)')

    # Call 2: Floor plan analysis (if available)
    floor_plan_result = None
    if floor_plan_urls:
        try:
            fp_start = time.time()
            fp_content = _build_image_content(floor_plan_urls)
            if fp_content:
                floor_plan_result = _call_gpt(
                    system_prompt="You are a professional floor plan analyst extracting detailed room dimensions and layout information.",
                    user_prompt=FLOOR_PLAN_PROMPT,
                    image_content=fp_content,
                )
                fp_elapsed = time.time() - fp_start
                logger.info(f'  Floor plan analysis complete ({fp_elapsed:.1f}s)')
        except Exception as e:
            logger.warning(f'  Floor plan analysis failed (non-fatal): {e}')

    # Build processing_status
    from datetime import timezone
    now = datetime.now(timezone.utc)
    processing_status = {
        "images_processed": True,
        "photos_analysed": len(photo_urls),
        "floor_plan_analysed": floor_plan_result is not None,
        "floor_plans_analysed": len(floor_plan_urls) if floor_plan_result else 0,
        "processed_at": now,
        "model_used": GPT_MODEL,
        "on_demand": True,
    }

    if floor_plan_result:
        internal = floor_plan_result.get("internal_floor_area") or {}
        external = floor_plan_result.get("external_floor_area") or {}
        total = floor_plan_result.get("total_floor_area") or {}
        processing_status["internal_floor_area_sqm"] = internal.get("value")
        processing_status["external_floor_area_sqm"] = external.get("value")
        processing_status["total_floor_area_sqm"] = total.get("value")

    # Write to DB immediately (so CatBoost can use the enriched data)
    update_set = {
        "property_valuation_data": photo_result,
        "processing_status": processing_status,
    }
    if floor_plan_result:
        update_set["floor_plan_analysis"] = floor_plan_result

    try:
        collection.update_one({"_id": doc["_id"]}, {"$set": update_set})
        logger.info('  GPT enrichment stored to DB')
    except Exception as e:
        logger.warning(f'  Failed to store GPT enrichment: {e}')

    # Also update the in-memory doc so downstream steps see enriched data
    doc['property_valuation_data'] = photo_result
    doc['processing_status'] = processing_status
    if floor_plan_result:
        doc['floor_plan_analysis'] = floor_plan_result

    return {
        'property_valuation_data': photo_result,
        'floor_plan_analysis': floor_plan_result,
        'processing_status': processing_status,
    }


# ---------------------------------------------------------------------------
# LIGHTWEIGHT GEOREFERENCE (embedded POI database for target suburbs)
# ---------------------------------------------------------------------------

import math

def _haversine_km(lat1, lon1, lat2, lon2):
    lat1, lon1, lat2, lon2 = map(math.radians, [lat1, lon1, lat2, lon2])
    dlat = lat2 - lat1
    dlon = lon2 - lon1
    a = math.sin(dlat/2)**2 + math.cos(lat1) * math.cos(lat2) * math.sin(dlon/2)**2
    return 6371 * 2 * math.asin(math.sqrt(a))

# Key Gold Coast POIs — curated for Robina / Burleigh Waters / Varsity Lakes corridor
_EMBEDDED_POIS = {
    'primary_schools': [
        ('Robina State School', -28.0770, 153.3850),
        ('Varsity College Primary', -28.0870, 153.4100),
        ('Burleigh Waters State School', -28.1016, 153.4268),
        ('Mudgeeraba State School', -28.0830, 153.3640),
        ('Merrimac State School', -28.0530, 153.3890),
        ('Worongary State School', -28.0700, 153.3580),
        ('Elanora State School', -28.1160, 153.4560),
        ('Caningeraba State School', -28.0940, 153.4360),
    ],
    'secondary_schools': [
        ('Robina State High School', -28.0690, 153.3800),
        ('Varsity College Secondary', -28.0870, 153.4100),
        ('Miami State High School', -28.0680, 153.4400),
        ('Merrimac State High School', -28.0510, 153.3840),
        ('Somerset College', -28.0750, 153.3450),
        ("King's Christian College", -28.0580, 153.3700),
    ],
    'supermarkets': [
        ('Woolworths Robina', -28.0770, 153.3930),
        ('Coles Robina Town Centre', -28.0700, 153.3850),
        ('Aldi Robina', -28.0760, 153.3960),
        ('Woolworths Varsity Lakes', -28.0900, 153.4110),
        ('Coles Varsity Lakes', -28.0910, 153.4100),
        ('Woolworths Burleigh Waters', -28.0930, 153.4280),
        ('Coles Stockland Burleigh Heads', -28.0920, 153.4430),
        ('Aldi Burleigh Heads', -28.0940, 153.4400),
        ('Woolworths Mudgeeraba', -28.0820, 153.3650),
    ],
    'shopping_malls': [
        ('Robina Town Centre', -28.0700, 153.3850),
        ('Stockland Burleigh Heads', -28.0920, 153.4430),
        ('Varsity Lakes Shopping Centre', -28.0900, 153.4110),
        ('Bond University Plaza', -28.0730, 153.4130),
    ],
    'hospitals': [
        ('Robina Hospital', -28.0730, 153.3920),
        ('Gold Coast University Hospital', -28.0030, 153.4100),
        ('John Flynn Private Hospital', -28.1280, 153.4750),
    ],
    'parks': [
        ('Robina Common', -28.0650, 153.3880),
        ('Central Park Robina', -28.0690, 153.3920),
        ('Lake Orr Park', -28.0870, 153.4060),
        ('Stockland Park', -28.0630, 153.3900),
        ('Burleigh Heads National Park', -28.0890, 153.4510),
        ('NightQuarter Helensvale', -27.9280, 153.3400),
    ],
    'public_transport': [
        ('Robina Station', -28.0710, 153.3840),
        ('Varsity Lakes Station', -28.0850, 153.4120),
        ('Mudgeeraba Station (future)', -28.0800, 153.3650),
        ('Merrimac Station (future)', -28.0530, 153.3890),
    ],
}

_BEACHES = [
    ('Burleigh Heads Beach', -28.1003, 153.4508),
    ('Broadbeach', -28.0264, 153.4294),
    ('Surfers Paradise Beach', -28.0023, 153.4295),
    ('Coolangatta Beach', -28.1682, 153.5376),
    ('Main Beach', -27.9605, 153.4278),
]

_AIRPORT = ('Gold Coast Airport', -28.164444, 153.504722)


def compute_georeference(lat, lon):
    """Compute georeference_data using embedded POI coordinates. No API calls."""
    distances = {}

    for category, pois in _EMBEDDED_POIS.items():
        items = []
        for name, plat, plon in pois:
            d = round(_haversine_km(lat, lon, plat, plon), 2)
            items.append({
                'name': name,
                'distance_meters': int(d * 1000),
                'distance_km': d,
                'coordinates': {'latitude': plat, 'longitude': plon},
            })
        items.sort(key=lambda x: x['distance_km'])
        distances[category] = items[:5]

    # Beaches
    beach_items = []
    for name, blat, blon in _BEACHES:
        d = round(_haversine_km(lat, lon, blat, blon), 2)
        beach_items.append({
            'name': name,
            'distance_meters': int(d * 1000),
            'distance_km': d,
            'coordinates': {'latitude': blat, 'longitude': blon},
        })
    beach_items.sort(key=lambda x: x['distance_km'])
    distances['beaches'] = beach_items[:3]

    # Airport
    aname, alat, alon = _AIRPORT
    ad = round(_haversine_km(lat, lon, alat, alon), 2)
    distances['airport'] = {
        'name': aname,
        'distance_meters': int(ad * 1000),
        'distance_km': ad,
        'coordinates': {'latitude': alat, 'longitude': alon},
    }

    # Summary stats
    def get_closest(cat):
        items = distances.get(cat, [])
        if isinstance(items, list) and items:
            return items[0]['distance_km']
        return None

    all_pois = []
    for cat, items in distances.items():
        if isinstance(items, list):
            all_pois.extend(items)

    summary_stats = {
        'closest_primary_school_km': get_closest('primary_schools'),
        'closest_secondary_school_km': get_closest('secondary_schools'),
        'closest_supermarket_km': get_closest('supermarkets'),
        'closest_beach_km': get_closest('beaches'),
        'closest_hospital_km': get_closest('hospitals'),
        'airport_distance_km': ad,
        'total_amenities_within_1km': len([p for p in all_pois if p['distance_km'] <= 1]),
        'total_amenities_within_2km': len([p for p in all_pois if p['distance_km'] <= 2]),
        'total_amenities_within_5km': len([p for p in all_pois if p['distance_km'] <= 5]),
    }

    return {
        'last_updated': datetime.now(),
        'coordinates': {'latitude': lat, 'longitude': lon},
        'distances': distances,
        'summary_stats': summary_stats,
        'calculation_method': 'embedded_poi_database',
    }


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


def _load_sold_comparables_scoped(client, target_suburbs):
    """Load sold comparables from only the specified suburbs (fast for on-demand)."""
    result = {}
    SUBURB_DISPLAY = {
        'robina': 'Robina', 'varsity_lakes': 'Varsity Lakes',
        'burleigh_waters': 'Burleigh Waters', 'burleigh_heads': 'Burleigh Heads',
        'mudgeeraba': 'Mudgeeraba', 'reedy_creek': 'Reedy Creek',
        'merrimac': 'Merrimac', 'worongary': 'Worongary', 'carrara': 'Carrara',
    }

    # Source 1: Gold_Coast sold properties
    gc_db = client['Gold_Coast']
    for suburb_key in target_suburbs:
        try:
            docs = list(gc_db[suburb_key].find({
                'listing_status': 'sold',
                'sale_price': {'$exists': True, '$ne': None}
            }))
            for doc in docs:
                if not doc.get('suburb_scraped'):
                    doc['suburb_scraped'] = SUBURB_DISPLAY.get(suburb_key, '')
                doc['_sold_source'] = 'recently_sold'
            if docs:
                result.setdefault(suburb_key, []).extend(docs)
        except Exception as e:
            logger.warning(f'  Error loading Gold_Coast.{suburb_key} sold: {e}')

    # Source 2: Target_Market_Sold_Last_12_Months
    try:
        tdb = client['Target_Market_Sold_Last_12_Months']
        available_cols = set(tdb.list_collection_names())
        for suburb_key in target_suburbs:
            # Try both formats
            col_name = None
            display_suburb = SUBURB_DISPLAY.get(suburb_key, suburb_key.replace('_', ' ').title())
            if suburb_key in available_cols:
                col_name = suburb_key
            elif display_suburb in available_cols:
                col_name = display_suburb
            if not col_name:
                continue
            docs = list(tdb[col_name].find({'sale_price': {'$exists': True, '$ne': None}}))
            existing_addrs = {
                d.get('address', '').lower().strip()
                for d in result.get(suburb_key, [])
            }
            new_docs = []
            for doc in docs:
                doc['suburb_scraped'] = display_suburb
                doc['_sold_source'] = 'target_market_12m'
                if doc.get('address', '').lower().strip() not in existing_addrs:
                    new_docs.append(doc)
            if new_docs:
                result.setdefault(suburb_key, []).extend(new_docs)
    except Exception as e:
        logger.warning(f'  Error loading Target_Market_Sold data: {e}')

    return result


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

    # Step 1b: Georeference enrichment (if missing)
    if not doc.get('georeference_data'):
        logger.info('  Computing georeference data (POI distances)...')
        geo_data = compute_georeference(lat, lon)
        try:
            db[suburb_key].update_one(
                {'_id': oid},
                {'$set': {'georeference_data': geo_data}}
            )
            doc['georeference_data'] = geo_data
            within_1km = geo_data['summary_stats']['total_amenities_within_1km']
            within_2km = geo_data['summary_stats']['total_amenities_within_2km']
            logger.info(f'  Georeference complete: {within_1km} amenities within 1km, {within_2km} within 2km')
        except Exception as e:
            logger.warning(f'  Failed to store georeference data: {e}')
    else:
        logger.info('  Georeference data already exists — skipping')

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

    # Step 3: GPT Vision enrichment (if property has photos but no analysis)
    gpt_result = None
    has_photos = bool(doc.get('property_images'))
    has_gpt = bool(doc.get('property_valuation_data'))
    if has_photos and not has_gpt:
        try:
            gpt_result = run_gpt_enrichment(doc, db[suburb_key])
            if gpt_result:
                # Re-read the doc from DB to get the enriched fields for CatBoost
                doc = db[suburb_key].find_one({'_id': oid})
                doc['LATITUDE'] = lat
                doc['LONGITUDE'] = lon
                logger.info('  Re-loaded property with GPT enrichment data')
        except Exception as e:
            logger.warning(f'  GPT enrichment failed (non-fatal): {e}')
    elif has_gpt:
        logger.info('  GPT enrichment already exists — skipping')
    else:
        logger.info('  No photos available — skipping GPT enrichment')

    # Step 4: CatBoost valuation — skip for on-demand (too slow, queries all 98 collections)
    # The website displays reconciled_valuation from precompute, not CatBoost
    catboost_result = None
    logger.info('  Skipping CatBoost (on-demand mode — precompute valuation is primary)')

    # Step 5: Precompute valuation data (NPUI, comparables, confidence intervals)
    # Only load sold records from nearby suburbs (not all 82 collections)
    NEARBY_SUBURBS = {
        'robina': ['robina', 'varsity_lakes', 'merrimac', 'mudgeeraba', 'worongary', 'carrara'],
        'varsity_lakes': ['varsity_lakes', 'robina', 'burleigh_waters', 'reedy_creek'],
        'burleigh_waters': ['burleigh_waters', 'burleigh_heads', 'varsity_lakes', 'merrimac'],
        'burleigh_heads': ['burleigh_heads', 'burleigh_waters', 'varsity_lakes'],
        'mudgeeraba': ['mudgeeraba', 'robina', 'worongary', 'reedy_creek'],
        'reedy_creek': ['reedy_creek', 'mudgeeraba', 'varsity_lakes', 'burleigh_waters'],
        'merrimac': ['merrimac', 'robina', 'carrara', 'burleigh_waters'],
        'worongary': ['worongary', 'mudgeeraba', 'robina'],
        'carrara': ['carrara', 'merrimac', 'robina'],
    }
    target_suburbs = NEARBY_SUBURBS.get(suburb_key, [suburb_key])
    logger.info(f'  Loading sold comparables for {len(target_suburbs)} nearby suburbs...')
    sold_by_suburb = _load_sold_comparables_scoped(client, target_suburbs)
    total_sold = sum(len(v) for v in sold_by_suburb.values())
    logger.info(f'  Loaded {total_sold} sold records')

    gc_coord_lookup = _preload_gc_coordinates(client, target_suburbs)
    gc_timeline_lookup = _preload_gc_timelines(client, target_suburbs)

    valuation_data = run_precompute_valuation(
        db, doc, suburb_key, sold_by_suburb,
        gc_coord_lookup, gc_timeline_lookup,
    )

    # Step 6: Store results
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
