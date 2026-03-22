#!/usr/bin/env python3
""" 
Enhanced Production Property Valuation System with Missing Features Tracking

Last Updated: 29/01/2026, 3:24 PM (Wednesday) - Brisbane
- Added OpenStreetMap Nominatim geocoding fallback for properties not found in Gold_Coast
  - When Gold_Coast lookup fails, automatically geocodes using OSM Nominatim API
  - Rate limited to 1 request/second per OSM usage policy
  - Caches geocoded coordinates in properties_for_sale for future use
  - This ensures ALL properties can get coordinates for valuation

- 29/01/2026, 3:21 PM (Wednesday) - Brisbane
  - Fixed postcode mismatch issue causing 19 properties to fail coordinate lookup
  - properties_for_sale has postcode 4226 but Gold_Coast has different postcodes (4213, 4218, 4227)
  - Removed postcode from initial query, now matches on street address only
  - This fixes the "Missing LATITUDE/LONGITUDE" errors for most properties

Previous Updates (descending):
- 29/01/2026, 2:08 PM (Thursday) - Brisbane
  - Fixed invalid Python header text that caused SyntaxError in orchestrator runs
  - Added Gold_Coast address-based matching (per-suburb collections) to obtain LATITUDE/LONGITUDE
    even when properties_for_sale does not store coordinates
  - Added optional CLI flags to target a single property or limit batch size without changing code
- 27/01/2026, 1:56 PM (Monday) - Brisbane
  - Added shebang for orchestrator compatibility

Description:
This script values properties in property_data.properties_for_sale with:
1. Missing features tracking
2. Dual database insertion (properties_for_sale + Gold_Coast/<suburb> collections)
3. JSON report generation
4. Metadata with JSON file link

Usage:
    python batch_valuate_with_tracking.py
    python batch_valuate_with_tracking.py --limit 1
    python batch_valuate_with_tracking.py --for-sale-id 697a03122dd05817453a97d8

Author: Property Valuation Production System
Date: 20th November 2025
"""
import argparse
import re
import sys
import pymongo
from bson import ObjectId

try:
    sys.path.insert(0, '/home/fields/Fields_Orchestrator')
    from shared.monitor_client import MonitorClient
    _MONITOR_AVAILABLE = True
except ImportError:
    _MONITOR_AVAILABLE = False

import pandas as pd
import numpy as np
from datetime import datetime
from catboost import CatBoostRegressor
from pathlib import Path
import json
import logging
from typing import Dict, List, Optional
from collections import defaultdict

import time
import config
from cosmos_retry import cosmos_retry, cosmos_retry_call
from osm_enrichment import OSMEnricher
from gpt_enrichment_runner import GPTEnrichmentRunner
from feature_calculator_v2 import ComprehensiveFeatureCalculator
from feature_aligner import FeatureAligner


def _suburb_to_collection_name(suburb: str) -> str:
    """Convert suburb label to Gold_Coast collection name."""
    return (suburb or "").strip().lower().replace(" ", "_")


def _normalize_street_name(s: str) -> str:
    return re.sub(r"\s+", " ", (s or "").strip()).upper()


# Australian street type abbreviations → full words as stored in Gold_Coast cadastral DB
_STREET_TYPE_ABBREVS = {
    "ST": "STREET", "AVE": "AVENUE", "AV": "AVENUE",
    "RD": "ROAD", "DR": "DRIVE", "PL": "PLACE",
    "CT": "COURT", "CRT": "COURT", "CL": "CLOSE",
    "CR": "CRESCENT", "CRES": "CRESCENT",
    "TCE": "TERRACE", "TER": "TERRACE",
    "PDE": "PARADE", "HWY": "HIGHWAY",
    "BLVD": "BOULEVARD", "BVD": "BOULEVARD",
    "GR": "GROVE", "LN": "LANE", "LA": "LANE",
    "WY": "WAY", "CCT": "CIRCUIT", "CIR": "CIRCUIT",
}


def _parse_street_address(street_address: str) -> dict:
    """Parse a street address into components for Gold_Coast DB lookup.

    Handles:
    - '20A Tarrant Drive'
    - '2/10 Laceflower Court'          (unit/street number)
    - '2 10 Laceflower Court'          (unit street number)
    - 'Level 4, 403/144 Marine Parade' (leading Level N,)
    - '502/141 Musgrave Street "Rythm"' (trailing quoted building name)
    - '113 Cnr Hill St & Marine Parade' (corner address — uses first street)
    - 'St' / 'Ave' / 'Tce' etc.        (abbreviated street types)
    """
    s = (street_address or "").strip()
    if not s:
        return {}

    # Strip leading "Level N," prefix (e.g. "Level 4, 403/144 Marine Parade")
    s = re.sub(r"^Level\s+\d+[A-Za-z]?\s*,?\s*", "", s, flags=re.IGNORECASE).strip()

    # Strip trailing quoted building name (e.g. '"Rythm"' or "'The Heights'")
    s = re.sub(r'\s+"[^"]*"\s*$', "", s).strip()
    s = re.sub(r"\s+'[^']*'\s*$", "", s).strip()

    unit_number = None

    # Handle '2/10 ...'
    if "/" in s and re.match(r"^\s*\d+\s*/\s*\d+", s):
        unit_part, rest = [p.strip() for p in s.split("/", 1)]
        unit_number = unit_part
        s = rest

    # Handle '2 10 ...'
    m_unit = re.match(r"^\s*(\d+)\s+(\d+[A-Za-z]?)\s+(.+)$", s)
    if m_unit:
        unit_number = unit_number or m_unit.group(1)
        s = f"{m_unit.group(2)} {m_unit.group(3)}"

    # Split number + remainder
    m = re.match(r"^\s*(\d+(?:-\d+)?)([A-Za-z]?)\s+(.+)$", s)
    if not m:
        return {}

    street_no = m.group(1)
    street_no_suffix = m.group(2) or None
    remainder = m.group(3).strip()

    # Handle "Cnr" prefix (corner address): "Cnr Hill St & Marine Parade"
    # Use the first named street before " & " or " and "
    cnr_m = re.match(r"^Cnr\s+(.+)", remainder, re.IGNORECASE)
    if cnr_m:
        first_street = re.split(r"\s+[&/]\s+|\s+and\s+", cnr_m.group(1), maxsplit=1, flags=re.IGNORECASE)[0].strip()
        remainder = first_street

    parts = remainder.split()
    if len(parts) < 2:
        return {}

    street_type = parts[-1]
    street_name = " ".join(parts[:-1])

    normalized_type = _normalize_street_name(street_type)
    expanded_type = _STREET_TYPE_ABBREVS.get(normalized_type, normalized_type)

    return {
        "UNIT_NUMBER": unit_number,
        "STREET_NO_1": street_no,
        "STREET_NO_1_SUFFIX": street_no_suffix,
        "STREET_NAME": _normalize_street_name(street_name),
        "STREET_TYPE": expanded_type,
    }


def _build_gold_coast_query(for_sale_doc: dict, include_postcode: bool = False) -> dict:
    """Build a query for Gold_Coast/<suburb> collection using for-sale fields.

    NOTE: Unit numbers are intentionally excluded. The Gold_Coast cadastral DB
    stores strata complexes as a single record (UNIT_NUMBER: None) for the whole
    building, not individual units. Including the unit number causes all
    apartment/unit lookups to fail.

    NOTE: Postcode is NOT included by default because properties_for_sale often has
    incorrect postcodes (e.g., 4226 for Robina) while Gold_Coast has the correct ones
    (e.g., 4213, 4218, 4227). Matching on street address alone is more reliable.
    """
    street_address = for_sale_doc.get("street_address") or ""
    parsed = _parse_street_address(street_address)
    if not parsed:
        return {}

    q = {
        "STREET_NO_1": str(parsed.get("STREET_NO_1")),
        "STREET_NAME": parsed.get("STREET_NAME"),
        "STREET_TYPE": parsed.get("STREET_TYPE"),
    }

    # Suffix is optional in Gold_Coast for some addresses; include if we have it.
    if parsed.get("STREET_NO_1_SUFFIX"):
        q["STREET_NO_1_SUFFIX"] = str(parsed.get("STREET_NO_1_SUFFIX"))

    if include_postcode:
        postcode = str(for_sale_doc.get("postcode") or "").strip()
        if postcode:
            q["POSTCODE"] = postcode

    return q


def _apply_gold_coast_coords_to_for_sale(for_sale_doc: dict, gc_doc: dict) -> dict:
    """Return a merged doc (for feature calculation) with Gold_Coast coords copied in."""
    merged = dict(for_sale_doc)
    if gc_doc:
        merged["LATITUDE"] = gc_doc.get("LATITUDE")
        merged["LONGITUDE"] = gc_doc.get("LONGITUDE")
        merged["complete_address"] = merged.get("complete_address") or gc_doc.get("complete_address")
    return merged


def _geocode_with_nominatim(address: str, suburb: str = None, state: str = "QLD", country: str = "Australia") -> dict | None:
    """
    Geocode an address using OpenStreetMap Nominatim API.
    
    This is a FREE geocoding service with the following constraints:
    - Rate limit: 1 request per second (enforced by this function)
    - User-Agent required (identifies our application)
    - Results may be less accurate than Google for some Australian addresses
    
    Args:
        address: Street address (e.g., "22 Homebush Drive")
        suburb: Suburb name (e.g., "Robina")
        state: State code (default: "QLD")
        country: Country name (default: "Australia")
        
    Returns:
        Dict with LATITUDE and LONGITUDE, or None if geocoding failed
    """
    import requests
    import time
    
    # Clean address before geocoding
    import re as _re
    address = (address or "").strip()
    # Skip malformed addresses that are listing titles, not real street addresses
    # e.g. "Robina, QLD 4226 - 2 beds apartment for Sale, From $995,000 - 2019475450"
    _malformed_patterns = [
        r'beds?\s+apartment\s+for\s+sale',
        r'beds?\s+house\s+for\s+sale',
        r'for\s+sale.*\d{7,}',   # listing ID at end
        r'^\w[\w\s]+,\s*[A-Z]{2,3}\s+\d{4}\s+-\s+\d',  # "Suburb, QLD 4226 - N beds..."
    ]
    for _pat in _malformed_patterns:
        if _re.search(_pat, address, flags=_re.IGNORECASE):
            return None
    # Remove "ID:XXXXXXX/" prefix (off-plan/project ID prefix)
    address = _re.sub(r'^ID:\d+/', '', address)
    # Remove "Type X/" prefix (e.g., "Type B/46 Scottsdale Drive")
    address = _re.sub(r'^Type\s+\w+/', '', address, flags=_re.IGNORECASE)
    # For range street numbers like "22-34 Glenside Drive", use the first number only
    address = _re.sub(r'^(\d+)-\d+\s', r'\1 ', address)
    # For unit/street combos with range in street: "2301/22-34 X" -> "22 X"
    m = _re.match(r'^\d+/(\d+)-\d+\s(.+)', address)
    if m:
        address = f"{m.group(1)} {m.group(2)}"
    # For high unit numbers like "4212/61 Investigator Drive", strip unit prefix
    m2 = _re.match(r'^\d{3,}/(\d+\s.+)', address)
    if m2:
        address = m2.group(1)
    address = address.strip()

    if not address:
        return None

    # Build full address string
    address_parts = [address]
    if suburb:
        address_parts.append(suburb)
    address_parts.extend([state, country])
    full_address = ", ".join(address_parts)
    
    # Nominatim API endpoint
    url = "https://nominatim.openstreetmap.org/search"
    
    params = {
        "q": full_address,
        "format": "json",
        "limit": 1,
        "addressdetails": 1,
    }
    
    headers = {
        # Required by Nominatim usage policy
        "User-Agent": "FieldsPropertyValuation/1.0 (property-valuation-system)"
    }
    
    try:
        # Rate limiting: sleep 1 second between requests
        time.sleep(1.0)
        
        response = requests.get(url, params=params, headers=headers, timeout=10)
        response.raise_for_status()
        
        results = response.json()
        
        if results and len(results) > 0:
            result = results[0]
            lat = float(result.get("lat"))
            lon = float(result.get("lon"))
            
            logger.info(f"  ✓ Geocoded via Nominatim: {full_address} -> ({lat}, {lon})")
            
            return {
                "LATITUDE": lat,
                "LONGITUDE": lon,
                "geocode_source": "nominatim",
                "geocode_display_name": result.get("display_name"),
            }
        else:
            logger.warning(f"  ⚠️ Nominatim: No results for '{full_address}'")
            return None
            
    except requests.exceptions.RequestException as e:
        logger.error(f"  ✗ Nominatim geocoding failed: {e}")
        return None
    except (ValueError, KeyError) as e:
        logger.error(f"  ✗ Nominatim response parsing failed: {e}")
        return None


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Production valuation runner")
    parser.add_argument(
        "--limit",
        type=int,
        default=None,
        help="Limit number of for-sale properties to value (default: config.BATCH_SIZE)",
    )
    parser.add_argument(
        "--for-sale-id",
        dest="for_sale_id",
        type=str,
        default=None,
        help="Value a single property by ObjectId from properties_for_sale",
    )
    parser.add_argument(
        "--run-gpt",
        action="store_true",
        help="Enable GPT enrichment stage inside valuation (default: disabled)",
    )
    return parser.parse_args()


# Setup logging
logging.basicConfig(
    level=getattr(logging, config.LOG_LEVEL),
    format=config.LOG_FORMAT,
    datefmt=config.LOG_DATE_FORMAT
)
logger = logging.getLogger(__name__)


class MissingFeaturesTracker:
    """Tracks missing features across all properties during valuation"""
    
    def __init__(self):
        """Initialize tracking structures"""
        self.per_property_data = {}
        self.aggregate_stats = defaultdict(lambda: {'total_properties': 0, 'missing_count': 0})
        self.feature_categories = {
            'base': ['bedrooms', 'bathrooms', 'car_spaces', 'lot_size_sqm'],
            'gpt': [k for k in config.GPT_REQUIRED_FIELDS],
            'osm': [k for k in config.OSM_REQUIRED_FIELDS],
            'comparable': ['comparable_count_90d', 'comparable_median_price_90d', 'comparable_count_relaxed'],
            'suburb_stats': [f'suburb_{s}' for s in ['median_price_12m', 'median_price_6m', 'sales_volume_12m', 
                                                       'sales_volume_3m', 'market_velocity', 'price_growth_rate',
                                                       'avg_days_on_market', 'price_volatility', 'floor_area_median',
                                                       'lot_size_median', 'quality_score_avg', 'sold_ratio']],
            'distance': [f'distance_to_{loc}_km' for loc in ['cbd', 'robina_tc', 'burleigh_beach', 'surfers_beach']],
            'school': ['in_robina_state_high_catchment', 'in_somerset_college_catchment', 'premium_school_count_3km'],
            'location_lot': ['waterfront_lot_premium_estimate', 'suburb_lot_size_percentile', 'lot_size_value_segment'],
            'log_transforms': ['log_gpt_floor_area_sqm', 'log_lot_size_sqm', 'log_comparable_median_price', 'has_floor_plan']
        }
        
    def track_property(self, property_id: str, address: str, features: Dict, 
                      feature_summary: Dict):
        """Track missing features for a single property"""
        missing_features = []
        missing_by_category = defaultdict(int)
        
        # Identify missing features
        for feature_name, value in features.items():
            is_missing = value is None or (isinstance(value, str) and value.lower() in ['none', ''])
            
            if is_missing:
                missing_features.append(feature_name)
                
                # Categorize
                for category, feature_list in self.feature_categories.items():
                    if any(feature_name.startswith(f) or feature_name in feature_list 
                          for f in feature_list):
                        missing_by_category[category] += 1
                        break
            
            # Update aggregate stats
            self.aggregate_stats[feature_name]['total_properties'] += 1
            if is_missing:
                self.aggregate_stats[feature_name]['missing_count'] += 1
        
        # Store per-property data
        self.per_property_data[property_id] = {
            'address': address,
            'missing_features': missing_features,
            'missing_by_category': dict(missing_by_category),
            'total_features': feature_summary['total_features'],
            'missing_count': len(missing_features),
            'coverage_pct': feature_summary['coverage_pct']
        }
    
    def generate_report(self, json_file_path: str) -> Dict:
        """Generate comprehensive missing features report"""
        # Calculate most commonly missing features
        most_commonly_missing = []
        for feature_name, stats in self.aggregate_stats.items():
            if stats['total_properties'] > 0:
                missing_pct = (stats['missing_count'] / stats['total_properties']) * 100
                if missing_pct > 0:  # Only include if ever missing
                    most_commonly_missing.append({
                        'feature': feature_name,
                        'missing_count': stats['missing_count'],
                        'total_properties': stats['total_properties'],
                        'missing_pct': round(missing_pct, 1)
                    })
        
        # Sort by missing percentage
        most_commonly_missing.sort(key=lambda x: x['missing_pct'], reverse=True)
        
        # Calculate aggregate by category
        category_stats = {}
        for category, feature_list in self.feature_categories.items():
            total_features = len(feature_list)
            total_missing = 0
            total_possible = 0
            
            for prop_data in self.per_property_data.values():
                cat_missing = prop_data['missing_by_category'].get(category, 0)
                total_missing += cat_missing
                total_possible += total_features
            
            if total_possible > 0:
                avg_null_pct = (total_missing / total_possible) * 100
            else:
                avg_null_pct = 0
            
            category_stats[category] = {
                'total_features': total_features,
                'avg_null_pct': round(avg_null_pct, 1),
                'total_missing_instances': total_missing
            }
        
        # Build comprehensive report
        report = {
            'report_metadata': {
                'generated_date': datetime.now().isoformat(),
                'total_properties_valued': len(self.per_property_data),
                'json_file_path': json_file_path
            },
            'aggregate_summary': {
                'features_by_category': category_stats,
                'most_commonly_missing': most_commonly_missing[:50],  # Top 50
                'overall_stats': {
                    'total_features_tracked': len(self.aggregate_stats),
                    'avg_coverage_pct': round(np.mean([p['coverage_pct'] 
                                                       for p in self.per_property_data.values()]), 1)
                }
            },
            'per_property_details': self.per_property_data
        }
        
        return report
    
    def save_report(self, file_path: str) -> str:
        """Save report to JSON file"""
        report = self.generate_report(file_path)
        
        with open(file_path, 'w') as f:
            json.dump(report, f, indent=2, default=str)
        
        logger.info(f"Missing features report saved: {file_path}")
        return file_path


class EnhancedProductionValuationSystem:
    """Enhanced valuation system with missing features tracking and dual-database insertion"""
    
    def __init__(self):
        """Initialize the enhanced valuation system"""
        logger.info("="*80)
        logger.info("ENHANCED PRODUCTION PROPERTY VALUATION SYSTEM")
        logger.info("Features: Missing Tracking + Dual Database Insertion")
        logger.info("="*80)
        
        # Connect to MongoDB
        logger.info("Connecting to MongoDB...")
        self.mongo_client = pymongo.MongoClient(config.MONGODB_URI)
        
        # Production database
        self.production_db = self.mongo_client[config.PRODUCTION_DB]
        self.properties_collection = self.production_db[config.PRODUCTION_COLLECTION]
        
        # Gold Coast database (for dual insertion)
        self.gold_coast_db = self.mongo_client[config.GOLD_COAST_DB]
        
        # Load model
        logger.info("Loading Iteration 08 model...")
        model_path = config.MODEL_DIR / config.MODEL_FILE
        if not model_path.exists():
            raise FileNotFoundError(f"Model file not found: {model_path}")
        self.model = CatBoostRegressor()
        self.model.load_model(str(model_path))
        logger.info(f"✓ Model loaded: {config.MODEL_FILE}")
        
        # Initialize enrichers
        self.gpt_enrichment_runner = GPTEnrichmentRunner()
        self.osm_enricher = OSMEnricher()
        
        # Initialize comprehensive feature calculator
        logger.info("Initializing comprehensive feature calculator...")
        self.feature_calculator = ComprehensiveFeatureCalculator(self.mongo_client)
        logger.info("✓ Feature calculator initialized")
        
        # Initialize feature aligner (CRITICAL: ensures all 126 features are present)
        logger.info("Initializing feature aligner...")
        self.feature_aligner = FeatureAligner()
        logger.info("✓ Feature aligner initialized")
        
        # Initialize missing features tracker
        self.missing_features_tracker = MissingFeaturesTracker()
        logger.info("✓ Missing features tracker initialized")

        # Cache collection names to avoid repeated list_collection_names() calls (RU-expensive on Cosmos DB)
        logger.info("Caching collection names...")
        self._production_collection_names_cache = cosmos_retry_call(self.production_db.list_collection_names)
        self._gold_coast_collection_names_cache = cosmos_retry_call(self.gold_coast_db.list_collection_names)
        logger.info(f"✓ Cached {len(self._production_collection_names_cache)} production + {len(self._gold_coast_collection_names_cache)} Gold Coast collection names")
        
        # Statistics
        self.stats = {
            'start_time': None,
            'end_time': None,
            'properties_queried': 0,
            'properties_processed': 0,
            'properties_valued': 0,
            'properties_failed': 0,
            'dual_inserts_success': 0,
            'dual_inserts_failed': 0,
            'osm_enrichments': 0,
            'gpt_enrichments_needed': 0
        }
        
    def get_properties_needing_valuation(self, limit: int = None, for_sale_id: str | None = None):
        """Query MongoDB for properties that need valuation.

        NOTE: properties_for_sale does NOT currently store LATITUDE/LONGITUDE, so we do not filter on coords.
        We fetch candidates then look up coords in Gold_Coast/<suburb> collections.
        """
        logger.info("\nQuerying for properties needing valuation...")

        query: dict = {
            "listing_status": "for_sale",
            "$or": [
                {"iteration_08_valuation": {"$exists": False}},
                {"iteration_08_valuation.predicted_value": {"$exists": False}},
            ]
        }

        if for_sale_id:
            query = {"_id": ObjectId(for_sale_id)}

        batch_limit = limit or config.BATCH_SIZE

        # Only value target suburb collections (not all 96 suburb collections)
        suburb_collections = getattr(config, 'TARGET_SUBURB_COLLECTIONS', None)
        if not suburb_collections:
            # Fallback: collect from all suburb collections (using cache)
            suburb_collections = [
                c for c in self._production_collection_names_cache
                if c not in ('suburb_statistics', 'suburb_median_prices',
                             'suburb_median_prices_backup', 'change_detection_snapshots',
                             'address_search_index')
            ]
        logger.info(f"Querying {len(suburb_collections)} suburb collections: {suburb_collections}")
        properties = []
        for col_name in suburb_collections:
            cursor = cosmos_retry_call(self.production_db[col_name].find, query)
            for doc in cursor:
                doc['_collection'] = col_name
                properties.append(doc)
            if batch_limit and len(properties) >= int(batch_limit):
                properties = properties[:int(batch_limit)]
                break

        self.stats["properties_queried"] = len(properties)
        logger.info(f"Found {len(properties)} for-sale properties to value across {len(suburb_collections)} suburb collections")
        return properties

    def lookup_gold_coast_document_for_sale(self, for_sale_doc: dict) -> dict | None:
        """Find matching Gold_Coast document (contains coords) for a for-sale doc."""
        suburb = for_sale_doc.get("suburb")
        if not suburb:
            return None

        coll_name = _suburb_to_collection_name(suburb)
        if coll_name not in self._gold_coast_collection_names_cache:
            return None

        q = _build_gold_coast_query(for_sale_doc)
        if not q:
            return None

        doc = cosmos_retry_call(self.gold_coast_db[coll_name].find_one, q)
        return doc
    
    def lookup_gold_coast_documents(self, for_sale_properties: list) -> dict:
        """Match properties_for_sale to Gold_Coast documents (coords live there).

        We match using the per-doc suburb (collection name) + parsed street address components.
        If no match found in Gold_Coast, falls back to OpenStreetMap Nominatim geocoding.
        """
        logger.info("\n" + "="*80)
        logger.info("CRITICAL FIX: Lookup Gold_Coast Documents with Full Data")
        logger.info("="*80)
        
        gold_coast_docs: dict = {}
        matched_count = 0
        geocoded_count = 0
        not_found_count = 0

        for idx, prop in enumerate(for_sale_properties):
            prop_id = prop.get("_id")
            address = prop.get("address") or prop.get("complete_address") or "Unknown"
            street_address = prop.get("street_address") or address
            suburb = prop.get("suburb")

            # Throttle DB lookups to avoid Cosmos DB 429 rate limits (serverless 5000 RU/s ceiling)
            if idx > 0:
                time.sleep(0.6)

            gc_doc = self.lookup_gold_coast_document_for_sale(prop)
            if gc_doc:
                gc_doc["_for_sale_id"] = prop_id
                if not gc_doc.get("suburb"):
                    gc_doc["suburb"] = (gc_doc.get("LOCALITY") or prop.get("suburb") or "").lower()
                # Merge key for-sale fields into the Gold_Coast doc so downstream code has what it expects.
                # Prefer the for-sale values where present (e.g., listing_url, address).
                merged = dict(gc_doc)
                for k in ["address", "street_address", "suburb", "postcode", "listing_url", "property_images", "floor_plans", "image_analysis", "floor_plan_analysis", "property_valuation_data"]:
                    if prop.get(k) is not None:
                        merged[k] = prop.get(k)
                gold_coast_docs[prop_id] = merged
                matched_count += 1
            else:
                # FALLBACK: Use OpenStreetMap Nominatim geocoding
                logger.info(f"  ⚠️ Not in Gold_Coast: {street_address} - trying Nominatim geocoding...")
                
                geocode_result = _geocode_with_nominatim(street_address, suburb)
                
                if geocode_result:
                    # Create a merged doc with geocoded coordinates
                    merged = dict(prop)
                    merged["LATITUDE"] = geocode_result["LATITUDE"]
                    merged["LONGITUDE"] = geocode_result["LONGITUDE"]
                    merged["geocode_source"] = geocode_result.get("geocode_source", "nominatim")
                    merged["geocode_display_name"] = geocode_result.get("geocode_display_name")
                    merged["_for_sale_id"] = prop_id
                    
                    # Cache the geocoded coordinates back to the suburb collection
                    try:
                        prop_col = prop.get('_collection')
                        if prop_col:
                            cosmos_retry_call(
                                self.production_db[prop_col].update_one,
                                {"_id": prop_id},
                                {"$set": {
                                    "geocoded_coordinates": {
                                        "latitude": geocode_result["LATITUDE"],
                                        "longitude": geocode_result["LONGITUDE"],
                                        "source": "nominatim",
                                        "geocoded_at": datetime.now(),
                                        "display_name": geocode_result.get("geocode_display_name")
                                    }
                                }}
                            )
                    except Exception as e:
                        logger.warning(f"  ⚠️ Failed to cache geocoded coords: {e}")
                    
                    gold_coast_docs[prop_id] = merged
                    geocoded_count += 1
                else:
                    # No coordinates available at all
                    not_found_count += 1
                    gold_coast_docs[prop_id] = prop
        
        logger.info(f"\nLookup Results:")
        logger.info(f"  Matched to Gold_Coast: {matched_count}")
        logger.info(f"  Geocoded via Nominatim: {geocoded_count}")
        logger.info(f"  No coordinates found: {not_found_count}")
        logger.info(f"  Total: {len(gold_coast_docs)}")
        
        self.stats['gold_coast_matches'] = matched_count
        self.stats['nominatim_geocoded'] = geocoded_count
        self.stats['gold_coast_not_found'] = not_found_count
        
        return gold_coast_docs
    
    def enrich_property(self, property_doc: dict) -> bool:
        """Enrich property with OSM data if needed"""
        # Check and enrich OSM features
        osm_success = self.osm_enricher.enrich_property(
            property_doc, 
            self.properties_collection
        )
        
        if not osm_success:
            logger.warning(f"  OSM enrichment failed for {property_doc.get('_id')}")
            return False
        
        # Check GPT data exists (check both old and new field names)
        has_gpt_data = (
            property_doc.get('property_valuation_data', {}).get('structural') is not None or
            property_doc.get('gpt_valuation_data', {}).get('gpt_floor_area_sqm') is not None
        )
        
        if not has_gpt_data:
            self.stats['gpt_enrichments_needed'] += 1
            logger.warning(f"  Property needs GPT enrichment (will be enriched in batch)")
            # Don't fail here - GPT enrichment happens in batch before this
        
        return True
    
    def calculate_features_with_tracking(self, property_doc: dict) -> tuple:
        """Calculate features and track missing ones"""
        features = self.feature_calculator.calculate_all_features(property_doc)
        summary = self.feature_calculator.get_feature_summary(features)
        
        # Track missing features
        property_id = str(property_doc['_id'])
        address = property_doc.get('complete_address', 'Unknown')
        self.missing_features_tracker.track_property(property_id, address, features, summary)
        
        return features, summary
    
    def predict_value(self, features: dict) -> dict:
        """Run valuation model prediction with feature alignment"""
        try:
            # CRITICAL FIX: Align features to ensure all 126 features are present
            # This fills missing features with appropriate defaults
            aligned_features = self.feature_aligner.align_features(features)
            
            # Convert to DataFrame with proper categorical encoding
            feature_df = self.feature_aligner.features_to_dataframe(aligned_features)
            
            # Run prediction
            predicted_value = self.model.predict(feature_df)[0]
            
            result = {
                'predicted_value': float(predicted_value),
                'confidence': 'medium',
                'model_version': 'iteration_08_phase1',
                'valuation_date': datetime.now()
            }
            
            return result
            
        except Exception as e:
            logger.error(f"Prediction failed: {e}")
            import traceback
            traceback.print_exc()
            return None
    
    def store_valuation_dual_database(self, property_doc: dict, valuation: dict, 
                                      features_summary: dict, json_file_path: str) -> bool:
        """
        Store valuation in BOTH databases:
        1. properties_for_sale collection (using _for_sale_id)
        2. Gold_Coast/{suburb} collection (using document's own _id)
        """
        # Get IDs - property_doc is now a Gold_Coast document with _for_sale_id reference
        gold_coast_id = property_doc['_id']
        for_sale_id = property_doc.get('_for_sale_id', property_doc['_id'])  # Fallback to same ID
        suburb = property_doc.get('suburb', '').lower().replace(' ', '_')
        
        # Build enhanced valuation metadata with JSON link
        valuation_with_metadata = {
            **valuation,
            'missing_features_report': json_file_path,
            'feature_coverage': {
                'total_features': features_summary['total_features'],
                'populated_features': features_summary['non_null_features'],
                'coverage_pct': round(features_summary['coverage_pct'], 1)
            },
            'feature_breakdown': features_summary['feature_groups']
        }
        
        success_count = 0

        # Write valuation result back to the property's suburb collection
        col_name = suburb if suburb else None
        if col_name:
            try:
                cosmos_retry_call(
                    self.production_db[col_name].update_one,
                    {'_id': for_sale_id},
                    {
                        '$set': {
                            'iteration_08_valuation': valuation_with_metadata,
                            'last_valuation_date': datetime.now()
                        }
                    }
                )
                success_count += 1
                self.stats['dual_inserts_success'] += 1
                logger.debug(f"  ✓ Stored to {col_name}")
            except Exception as e:
                logger.error(f"  ✗ Failed to store in {col_name}: {e}")
                self.stats['dual_inserts_failed'] += 1
        else:
            logger.warning("  ⚠️  No suburb identified - cannot write valuation result")
            self.stats['dual_inserts_failed'] += 1

        return success_count >= 1
    
    def process_properties(self, properties: list, json_file_path: str):
        """Process and value all properties"""
        logger.info("\n" + "="*80)
        logger.info("PROCESSING PROPERTIES")
        logger.info("="*80)
        
        for idx, property_doc in enumerate(properties, 1):
            property_id = property_doc.get('_id')
            address = property_doc.get('complete_address', property_doc.get('address', 'Unknown'))
            
            logger.info(f"\n[{idx}/{len(properties)}] Processing: {address}")
            self.stats['properties_processed'] += 1

            # Ensure we have coords (needed by feature calculators)
            if property_doc.get('LATITUDE') is None or property_doc.get('LONGITUDE') is None:
                logger.warning("  ⚠️  Missing LATITUDE/LONGITUDE on merged doc; skipping valuation")
                self.stats['properties_failed'] += 1
                continue
            
            # Step 1: Enrich if needed
            if not self.enrich_property(property_doc):
                logger.error("  ✗ Enrichment incomplete - skipping valuation")
                self.stats['properties_failed'] += 1
                continue
            
            # Step 2: Calculate features with tracking
            try:
                features, summary = self.calculate_features_with_tracking(property_doc)
                logger.info(f"  ✓ Calculated {summary['total_features']} features ({summary['coverage_pct']:.1f}% coverage)")
            except Exception as e:
                logger.error(f"  ✗ Feature calculation failed: {e}")
                import traceback
                traceback.print_exc()
                self.stats['properties_failed'] += 1
                continue
            
            # Step 3: Run prediction
            valuation = self.predict_value(features)
            if not valuation:
                logger.error("  ✗ Prediction failed")
                self.stats['properties_failed'] += 1
                continue
            
            logger.info(f"  ✓ Predicted value: ${valuation['predicted_value']:,.0f}")
            
            # Step 4: Store in BOTH databases
            if self.store_valuation_dual_database(property_doc, valuation, summary, json_file_path):
                logger.info("  ✓ Valuation stored to both databases")
                self.stats['properties_valued'] += 1
            else:
                logger.error("  ✗ Failed to store valuation")
                self.stats['properties_failed'] += 1

            # Throttle between properties to stay under Cosmos DB 5000 RU/s ceiling
            if idx < len(properties):
                time.sleep(0.5)
    
    def print_summary(self):
        """Print execution summary"""
        logger.info("\n" + "="*80)
        logger.info("VALUATION SUMMARY")
        logger.info("="*80)
        
        duration = (self.stats['end_time'] - self.stats['start_time']).total_seconds()
        
        logger.info(f"\nExecution Time: {duration:.1f}s")
        
        logger.info(f"\nGold_Coast Document Matching (CRITICAL FIX):")
        logger.info(f"  Matched to Gold_Coast: {self.stats.get('gold_coast_matches', 0)}")
        logger.info(f"  Not found in Gold_Coast: {self.stats.get('gold_coast_not_found', 0)}")
        
        logger.info(f"\nGPT Enrichment:")
        logger.info(f"  Properties enriched: {self.stats.get('gpt_enrichments', 0)}")
        
        logger.info(f"\nProperties:")
        logger.info(f"  Queried: {self.stats['properties_queried']}")
        logger.info(f"  Processed: {self.stats['properties_processed']}")
        logger.info(f"  Successfully valued: {self.stats['properties_valued']}")
        logger.info(f"  Failed: {self.stats['properties_failed']}")
        
        logger.info(f"\nDual Database Insertions:")
        logger.info(f"  Successful: {self.stats['dual_inserts_success']}")
        logger.info(f"  Failed: {self.stats['dual_inserts_failed']}")
        
        logger.info("\n" + "="*80)
        
        # Save summary
        summary_file = config.RESULTS_DIR / f"valuation_summary_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json"
        with open(summary_file, 'w') as f:
            json.dump(self.stats, f, indent=2, default=str)
        logger.info(f"Summary saved: {summary_file}")
    
    def run(self):
        """Main execution flow"""
        self.stats['start_time'] = datetime.now()
        
        # Generate JSON file path
        timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
        json_file_path = str(config.RESULTS_DIR / f"missing_features_{timestamp}.json")
        
        try:
            # Parse CLI options
            args = _parse_args()

            # Get properties to value from properties_for_sale
            for_sale_properties = self.get_properties_needing_valuation(limit=args.limit, for_sale_id=args.for_sale_id)
            
            if len(for_sale_properties) == 0:
                logger.info("\n✓ No properties need valuation")
                return
            
            # Lookup matching Gold_Coast docs (coords live there)
            gold_coast_docs_map = self.lookup_gold_coast_documents(for_sale_properties)
            
            # Convert map to list of docs for enrichment
            gold_coast_properties = list(gold_coast_docs_map.values())
            
            # STEP 1: (Optional) GPT enrichment on Gold_Coast documents
            # Default is OFF for remediation runs; enable with --run-gpt.
            if args.run_gpt and config.RUN_GPT_ENRICHMENT_AUTOMATICALLY and self.gpt_enrichment_runner.gpt_available:
                logger.info("\n" + "="*80)
                logger.info("STEP 1: GPT ENRICHMENT (Using Gold_Coast Documents with Images)")
                logger.info("="*80)
                
                # Enrich Gold_Coast documents (they have scraped_data.images)
                gpt_stats = self.gpt_enrichment_runner.batch_enrich(
                    gold_coast_properties, 
                    self.gold_coast_db  # Store in Gold_Coast collections
                )
                self.stats['gpt_enrichments'] = gpt_stats.get('successful', 0)
                
                # Also copy GPT data to properties_for_sale
                if gpt_stats.get('successful', 0) > 0:
                    logger.info(f"\nCopying GPT data to properties_for_sale...")
                    for gc_doc in gold_coast_properties:
                        if gc_doc.get('gpt_valuation_data'):
                            for_sale_id = gc_doc.get('_for_sale_id')
                            if for_sale_id:
                                cosmos_retry_call(
                                    self.properties_collection.update_one,
                                    {'_id': for_sale_id},
                                    {'$set': {'gpt_valuation_data': gc_doc['gpt_valuation_data']}}
                                )
                    logger.info("✓ GPT data copied to properties_for_sale")
                
                # Reload Gold_Coast documents after GPT enrichment
                logger.info(f"\nReloading {len(for_sale_properties)} Gold_Coast documents with updated GPT data...")
                gold_coast_docs_map = self.lookup_gold_coast_documents(for_sale_properties)
                gold_coast_properties = list(gold_coast_docs_map.values())
            else:
                if not config.RUN_GPT_ENRICHMENT_AUTOMATICALLY:
                    logger.info("\n⚠️  Automatic GPT enrichment is disabled in config")
                    logger.info("   Set RUN_GPT_ENRICHMENT_AUTOMATICALLY = True to enable")
                elif not args.run_gpt:
                    logger.info("\nℹ️  GPT enrichment skipped (enable with --run-gpt)")
                else:
                    logger.info("\n⚠️  GPT client not available - skipping GPT enrichment")
                self.stats['gpt_enrichments'] = 0
            
            # STEP 2: Process all properties using Gold_Coast documents (with OSM enrichment and valuation)
            self.process_properties(gold_coast_properties, json_file_path)
            
            # Generate and save missing features report
            logger.info("\n" + "="*80)
            logger.info("GENERATING MISSING FEATURES REPORT")
            logger.info("="*80)
            self.missing_features_tracker.save_report(json_file_path)
            logger.info(f"✓ Report accessible at: {json_file_path}")
            
            # Print summary
            self.stats['end_time'] = datetime.now()
            self.print_summary()
            
            logger.info("\n✓ Valuation complete!")
            
        except Exception as e:
            logger.error(f"\n✗ Fatal error: {e}")
            import traceback
            traceback.print_exc()
            raise
        
        finally:
            if self.mongo_client:
                self.mongo_client.close()


def main():
    """Entry point"""
    monitor = MonitorClient(
        system="orchestrator", pipeline="orchestrator_daily",
        process_id="6", process_name="Batch Valuate Properties"
    ) if _MONITOR_AVAILABLE else None
    if monitor: monitor.start()

    print("\n" + "="*80)
    print("ENHANCED PROPERTY VALUATION SYSTEM")
    print("With Missing Features Tracking & Dual Database Insertion")
    print("="*80)
    print(f"\nModel: {config.MODEL_FILE}")
    print(f"Database 1: {config.PRODUCTION_DB}.{config.PRODUCTION_COLLECTION}")
    print(f"Database 2: {config.GOLD_COAST_DB}.[suburb_collections]")
    print(f"Batch size: {config.BATCH_SIZE}")
    print("\n" + "="*80 + "\n")

    # Run enhanced valuation system
    system = EnhancedProductionValuationSystem()
    try:
        system.run()
        if monitor:
            monitor.log_metric("properties_valued", system.stats.get("properties_valued", 0))
            monitor.log_metric("properties_failed", system.stats.get("properties_failed", 0))
            # Report failed only if zero properties were valued (complete batch failure).
            # Individual property failures (bad addresses, OSM 504s) are expected and
            # do not indicate a broken pipeline.
            monitor.finish(status="success" if system.stats.get("properties_valued", 0) > 0 else "failed")
    except Exception:
        if monitor: monitor.finish(status="failed")
        raise


if __name__ == "__main__":
    main()
