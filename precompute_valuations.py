#!/usr/bin/env python3
"""
Pre-compute Valuation Data for All For-Sale Properties
Last Updated: 16/02/2026, 8:07 AM (Sunday) — Brisbane Time

Description:
    This script pre-computes valuation data (NPUI/Home Value Score, comparables,
    value gap analysis, adjustments, verification, weighting, confidence intervals)
    for all properties in the properties_for_sale collection.
    This eliminates the need for the Netlify function to perform expensive
    on-demand computation, reducing response time from 5-10 seconds to < 1 second.

    Implements all 6 critical gaps from the valuation methodology:
      Gap 1: Independent valuation per comparable (regression line evaluation)
      Gap 2: Adjustment calculations (hybrid OLS regression + suburb fallback rates)
      Gap 3: Verification system (independent val accuracy, z-score outlier, data quality)
      Gap 4: Narrative generation (human-readable adjustment explanations)
      Gap 5: Weighting logic (5-factor: NPUI similarity, verification, data quality, recency, adj magnitude)
      Gap 6: Confidence intervals (weighted mean/std dev from verified adjusted values)

Edit History:
    - 16/02/2026 8:35 AM: Fixed null-safety issues causing 7 precompute errors
      - Added defensive `or {}` guards in gap processing loop for comp_bd['inputs']
      - Protected pt['features']['basic'].get() calls with fallback empty dicts
      - Properties affected: Mudgeeraba (31 Spoonbill Way, 6 Bagan Court, etc.)
    - 16/02/2026 8:07 AM: Implemented all 6 critical valuation gaps (v2)
      - Gap 1: Independent valuation using regression line slope/intercept
      - Gap 2: Hybrid adjustment rates (OLS regression on sold_last_6_months + suburb fallback)
      - Gap 3: Verification system (3 checks: accuracy, z-score, data quality)
      - Gap 4: Template-based narrative generation per comparable
      - Gap 5: 5-factor weighting with normalization
      - Gap 6: Weighted confidence intervals with CV-based confidence levels
      - Added numpy dependency for OLS regression
      - Added SUBURB_ADJUSTMENT_RATES constant from Section 6.1 methodology
      - compute_value_gap() now returns slope/intercept for Gap 1
      - valuation_data output now includes: adjustment_rates, confidence, regression_line
      - Each comparable/recent_sale now includes: independent_valuation, adjustment_result,
        verification, narrative, weight
    - 12/02/2026 1:19 PM: Initial creation
      - Ports NPUI calculation logic from JavaScript (valuation.mjs)
      - Computes valuation data for each property
      - Stores results in properties_for_sale.valuation_data field
      - Includes metadata: computed_at, data_source, computation_time_ms

Usage:
    python3 precompute_valuations.py

Environment Variables Required:
    COSMOS_CONNECTION_STRING - Azure Cosmos DB connection string

Output:
    - Updates properties_for_sale collection with valuation_data field
    - Each property gets a valuation_data object containing:
      {
        "computed_at": ISODate,
        "subject_property": {...},
        "comparables": [...],
        "recent_sales": [...],
        "chart_points": [...],
        "summary": {...},
        "valuation_breakdown": {...},
        "metadata": {...}
      }
"""

import os
import sys
import time
import math
from datetime import datetime
from dotenv import load_dotenv
from pymongo import MongoClient
from pymongo.errors import WriteError
from statistics import median
import re
import numpy as np
from math import radians, cos, sin, asin, sqrt


# ─── Haversine Distance ──────────────────────────────────────────────────────

def haversine_distance(lat1, lon1, lat2, lon2):
    """Great-circle distance between two points on earth in km."""
    lat1, lon1, lat2, lon2 = map(radians, [lat1, lon1, lat2, lon2])
    dlat = lat2 - lat1
    dlon = lon2 - lon1
    a = sin(dlat / 2) ** 2 + cos(lat1) * cos(lat2) * sin(dlon / 2) ** 2
    return 6371 * 2 * asin(sqrt(a))


# ─── Beach Proximity Premium ────────────────────────────────────────────────
# Beach coordinates — MUST match the BEACHES array in src/utils/beachDistance.ts
# (the frontend source of truth for the "Dist to Beach" stat pill). Using
# identical coordinates ensures the valuation adjustment and the displayed
# distance are always consistent.
GOLD_COAST_BEACHES = [
    ('Burleigh Heads Beach', -28.089, 153.455),
    ('Miami Beach',          -28.071, 153.446),
]

# Piecewise-linear premium curve from 2015-2025 Gold Coast sales analysis.
# Values are premium percentages relative to an 8km+ baseline (where beach
# distance has negligible effect on price). Interpolated linearly between
# breakpoints for smooth adjustments.
#   0 km → 30%   (full coastal premium)
#   2 km → 17.5% (significant premium)
#   4 km → 10%   (moderate premium)
#   6 km → 4.5%  (marginal premium)
#   8 km → 0%    (baseline — suburb fundamentals dominate)
_BEACH_PREMIUM_BREAKPOINTS = [
    (0.0, 0.30),
    (2.0, 0.175),
    (4.0, 0.10),
    (6.0, 0.045),
    (8.0, 0.00),
]

# Dampening factor: the raw premium percentages include effects correlated
# with other adjustment factors (water_views, land_value, neighbourhood
# quality). Apply 60% of the raw premium to avoid double-counting.
_BEACH_PREMIUM_DAMPING = 0.60


def resolve_beach_distance(doc, lat=None, lon=None):
    """
    Return distance in km to nearest beach using the same coordinates and
    Haversine method as the website's beachDistance.ts utility. This ensures
    the valuation adjustment matches the "Dist to Beach" figure shown in
    the property header.
    """
    if lat is not None and lon is not None:
        min_dist = float('inf')
        for _, blat, blon in GOLD_COAST_BEACHES:
            d = haversine_distance(lat, lon, blat, blon)
            if d < min_dist:
                min_dist = d
        return round(min_dist, 2)
    return None


def beach_premium_pct(distance_km):
    """
    Return the beach proximity premium as a fraction of property value.
    Uses piecewise-linear interpolation between breakpoints, then applies
    the dampening factor. Returns 0.0 for distances >= 8 km.
    """
    if distance_km is None:
        return 0.0
    if distance_km <= 0:
        return _BEACH_PREMIUM_BREAKPOINTS[0][1] * _BEACH_PREMIUM_DAMPING
    for i in range(len(_BEACH_PREMIUM_BREAKPOINTS) - 1):
        d0, p0 = _BEACH_PREMIUM_BREAKPOINTS[i]
        d1, p1 = _BEACH_PREMIUM_BREAKPOINTS[i + 1]
        if d0 <= distance_km <= d1:
            t = (distance_km - d0) / (d1 - d0)
            return (p0 + t * (p1 - p0)) * _BEACH_PREMIUM_DAMPING
    return 0.0


# ─── Renovation Quality Score ──────────────────────────────────────────────

def compute_renovation_quality_score(doc):
    """
    Composite 0-10 score capturing renovation QUALITY beyond ordinal level.
    Differentiates a basic cosmetic refresh from a premium full renovation.
    Returns float 0-10, or None if insufficient data.
    """
    pvd = doc.get('property_valuation_data', {})
    if not pvd:
        return None

    cond = pvd.get('condition_summary', {}) or {}
    kitchen = pvd.get('kitchen', {}) or {}
    reno = pvd.get('renovation', {}) or {}
    metadata = pvd.get('property_metadata', {}) or {}

    scores = []
    weights = []

    # Overall condition (25%)
    overall = cond.get('overall_score')
    if overall is not None and isinstance(overall, (int, float)):
        scores.append(float(overall))
        weights.append(0.25)

    # Interior score (20%)
    interior = cond.get('interior_score')
    if interior is not None and isinstance(interior, (int, float)):
        scores.append(float(interior))
        weights.append(0.20)

    # Kitchen composite (25%): quality_score + premium indicator bonuses
    kitchen_base = kitchen.get('quality_score')
    if kitchen_base is not None and isinstance(kitchen_base, (int, float)):
        k_score = float(kitchen_base)
        if kitchen.get('benchtop_material') == 'stone':
            k_score = min(10, k_score + 0.75)
        if kitchen.get('appliances_quality') == 'premium':
            k_score = min(10, k_score + 0.75)
        if kitchen.get('island_bench'):
            k_score = min(10, k_score + 0.5)
        if kitchen.get('butler_pantry'):
            k_score = min(10, k_score + 0.5)
        scores.append(k_score)
        weights.append(0.25)

    # Bathroom score (15%)
    bath = cond.get('bathroom_score')
    if bath is not None and isinstance(bath, (int, float)):
        scores.append(float(bath))
        weights.append(0.15)

    # Modern features score (10%)
    modern = reno.get('modern_features_score')
    if modern is not None and isinstance(modern, (int, float)):
        scores.append(float(modern))
        weights.append(0.10)

    # Prestige tier bonus (5%)
    tier = (metadata.get('prestige_tier') or '').lower()
    tier_scores = {'standard': 3, 'elevated': 5, 'prestige': 8, 'ultra_prestige': 10}
    if tier in tier_scores:
        scores.append(tier_scores[tier])
        weights.append(0.05)

    if not scores or sum(weights) < 0.3:
        return None

    total_weight = sum(weights)
    return round(sum(s * w for s, w in zip(scores, weights)) / total_weight, 1)


# ─── Suburb Median Calculator (for street + micro-location premiums) ──────

_STREET_PREMIUM_DAMPING = 0.50
_MICRO_LOCATION_DAMPING = 0.50
_LOCATION_PREMIUM_CAP = 0.15  # ±15% max


def _get_sold_date(doc):
    """Extract sold date from document as datetime."""
    from datetime import datetime as _dt
    for field in ('sold_date', 'sale_date'):
        val = doc.get(field)
        if val:
            if isinstance(val, _dt):
                return val
            if isinstance(val, str):
                try:
                    return _dt.fromisoformat(val[:10])
                except (ValueError, TypeError):
                    pass
            if isinstance(val, (int, float)) and val > 1_000_000_000:
                try:
                    return _dt.fromtimestamp(val / 1000 if val > 1e12 else val)
                except (ValueError, OSError):
                    pass
    return None


def _get_sale_price(doc):
    """Extract numeric sale price from a sold document."""
    for field in ('sale_price', 'sold_price', 'last_sold_price'):
        val = doc.get(field)
        if val:
            p = parse_price(val) if isinstance(val, str) else (val if isinstance(val, (int, float)) else None)
            if p and p > 50000:
                return p
    return None


def _build_suburb_median_cache(sold_by_suburb):
    """
    Pre-compute rolling 12-month suburb medians for each month with data.
    Returns dict: (suburb_key, year, month) -> median_price
    """
    from datetime import datetime as _dt, timedelta
    from statistics import median as _median

    cache = {}
    for suburb_key, docs in sold_by_suburb.items():
        # Collect all (date, price) pairs
        dated_prices = []
        for d in docs:
            sd = _get_sold_date(d)
            sp = _get_sale_price(d)
            if sd and sp:
                dated_prices.append((sd, sp))
        if not dated_prices:
            continue

        dated_prices.sort(key=lambda x: x[0])
        min_date = dated_prices[0][0]
        max_date = dated_prices[-1][0]

        # Iterate month by month
        current = _dt(min_date.year, min_date.month, 1)
        while current <= max_date:
            window_start = current - timedelta(days=365)
            prices = [p for (d, p) in dated_prices if window_start <= d <= current]
            if len(prices) >= 5:
                cache[(suburb_key, current.year, current.month)] = _median(prices)
            if current.month == 12:
                current = _dt(current.year + 1, 1, 1)
            else:
                current = _dt(current.year, current.month + 1, 1)
    return cache


def _extract_street_name(doc):
    """
    Extract street name from a property document.
    Uses STREET_NAME + STREET_TYPE fields (cadastral) or parses address string.
    Returns lowercase string like 'camberwell circuit' or None.
    """
    # Try cadastral fields first (most reliable)
    sn = doc.get('STREET_NAME')
    st = doc.get('STREET_TYPE')
    if sn and st:
        return f"{sn} {st}".lower().strip()

    # Fallback: parse from address string
    addr = doc.get('address') or doc.get('street_address') or ''
    if not addr:
        return None
    # "4 Camberwell Circuit, Robina, QLD 4226" -> "camberwell circuit"
    street_part = addr.split(',')[0].strip()
    # Remove leading unit/number: "12/8 Marine Parade" -> "marine parade"
    street_part = re.sub(r'^[\d/]+\s*', '', street_part).strip()
    return street_part.lower() if street_part else None


def _build_street_premium_cache(sold_by_suburb, median_cache, min_sales=3):
    """
    Pre-compute street premiums for all streets with sufficient data.
    Returns dict: (suburb_key, street_name) -> (premium_pct, n_sales)
    """
    cache = {}
    for suburb_key, docs in sold_by_suburb.items():
        # Group sales by street
        street_sales = {}
        for d in docs:
            sn = _extract_street_name(d)
            if not sn:
                continue
            sd = _get_sold_date(d)
            sp = _get_sale_price(d)
            if not sd or not sp:
                continue
            med = median_cache.get((suburb_key, sd.year, sd.month))
            if not med:
                continue
            pct = (sp - med) / med
            street_sales.setdefault(sn, []).append(pct)

        for street, pcts in street_sales.items():
            if len(pcts) >= min_sales:
                avg = sum(pcts) / len(pcts)
                # Apply dampening and cap
                dampened = avg * _STREET_PREMIUM_DAMPING
                capped = max(-_LOCATION_PREMIUM_CAP, min(_LOCATION_PREMIUM_CAP, dampened))
                cache[(suburb_key, street)] = (round(capped, 4), len(pcts))
    return cache


def compute_micro_location_premium(lat, lon, suburb_key, sold_docs, median_cache,
                                    radii=(0.5, 1.0, 1.5), min_sales=5):
    """
    Compute average % premium/discount for properties near the target coordinates.
    Uses adaptive radius: tries smallest first, expands until min_sales met.
    Returns (premium_pct, n_sales, radius_used) or (None, 0, None).
    """
    if lat is None or lon is None:
        return None, 0, None

    for radius_km in radii:
        premiums = []
        for d in sold_docs:
            d_lat = d.get('LATITUDE') or d.get('latitude')
            d_lon = d.get('LONGITUDE') or d.get('longitude')
            if not d_lat or not d_lon:
                continue
            try:
                dist = haversine_distance(lat, lon, float(d_lat), float(d_lon))
            except (ValueError, TypeError):
                continue
            if dist > radius_km:
                continue
            sd = _get_sold_date(d)
            sp = _get_sale_price(d)
            if not sd or not sp:
                continue
            med = median_cache.get((suburb_key, sd.year, sd.month))
            if not med:
                continue
            premiums.append((sp - med) / med)

        if len(premiums) >= min_sales:
            avg = sum(premiums) / len(premiums)
            dampened = avg * _MICRO_LOCATION_DAMPING
            capped = max(-_LOCATION_PREMIUM_CAP, min(_LOCATION_PREMIUM_CAP, dampened))
            return round(capped, 4), len(premiums), radius_km

    return None, 0, None


def _resolve_comp_micro_premium(pt, suburb_key, sold_by_suburb, median_cache, gc_coords):
    """Resolve micro-location premium for a comp point in the adjustment loop."""
    src = pt.get('_source_doc') or pt
    comp_lat, comp_lon = _resolve_coordinates(src, gc_coords, suburb_key)
    if comp_lat and comp_lon:
        prem, _, _ = compute_micro_location_premium(
            comp_lat, comp_lon, suburb_key,
            sold_by_suburb.get(suburb_key, []),
            median_cache or {})
        return prem
    return None


# ─── NPUI Feature Weights (matching JavaScript valuation.mjs) ─────────────

NPUI_WEIGHTS = {
    # Size & capacity (30%)
    'land_size_sqm': 0.30 * 0.45,  # 13.5%
    'floor_area_sqm': 0.30 * 0.45,  # 13.5%
    'bedrooms': 0.30 * 0.10 * 0.6,  # 1.8%
    'bathrooms': 0.30 * 0.10 * 0.4,  # 1.2%
    
    # Quality & condition (30%)
    'interior.overall_interior_condition_score': 0.30 * 0.25,
    'interior.kitchen_quality_score': 0.30 * 0.20,
    'interior.bathroom_quality_score': 0.30 * 0.20,
    'exterior.overall_exterior_condition_score': 0.30 * 0.20,
    'renovation.modern_features_score': 0.30 * 0.10,
    
    # Layout & liveability (25%)
    'layout.layout_efficiency_score': 0.25 * 0.40,
    'interior.natural_light_score': 0.25 * 0.30,
    'layout.number_of_living_areas': 0.25 * 0.20,
    
    # Features & lifestyle (15%)
    'outdoor.outdoor_entertainment_score': 0.15 * 0.30,
    'outdoor.landscaping_quality_score': 0.15 * 0.20,
    'outdoor.fence_condition_score': 0.15 * 0.15,
}

# Waterfront detection keywords
WATERFRONT_KEYWORDS = [
    'waterfront', 'water front', 'canal front', 'canal frontage',
    'lakefront', 'lake front', 'riverfront', 'river front',
    'beachfront', 'beach front', 'oceanfront', 'ocean front',
]

# ─── Suburb-specific adjustment rates (fallback from Section 6.1 methodology) ──
# Midpoint values from documented ranges in SECTION_6_1_QUANTIFYING_ADJUSTMENTS.md

# Methodology fallback rates — pool rates informed by OLS regression ($120k raw,
# discounted ~30% because binary pool coefficient absorbs correlated luxury features).
# Renovation level: ordinal 1-5 (original → new_build). Cladding: ordinal 1-4
# (weatherboard → stone). Water views: binary 0/1. Kitchen quality: 1-10 score.
# AC type: binary 0/1 (ducted premium).
SUBURB_ADJUSTMENT_RATES = {
    'Robina':          {'land_per_sqm': 500, 'floor_per_sqm': 2500, 'per_bedroom': 90000, 'per_bathroom': 65000, 'per_car_space': 40000, 'per_pool': 80000, 'per_storey': 50000, 'per_renovation_level': 60000, 'per_water_view': 150000, 'per_cladding_level': 25000, 'per_kitchen_point': 15000, 'per_ac_ducted': 25000, 'per_year_age': 3000, 'condition_pct_per_point': 0.05, 'per_renovation_quality_point': 20000},
    'Mudgeeraba':      {'land_per_sqm': 375, 'floor_per_sqm': 2200, 'per_bedroom': 85000, 'per_bathroom': 57000, 'per_car_space': 35000, 'per_pool': 70000, 'per_storey': 45000, 'per_renovation_level': 55000, 'per_water_view': 120000, 'per_cladding_level': 20000, 'per_kitchen_point': 12000, 'per_ac_ducted': 20000, 'per_year_age': 3000, 'condition_pct_per_point': 0.05, 'per_renovation_quality_point': 15000},
    'Varsity Lakes':   {'land_per_sqm': 550, 'floor_per_sqm': 2500, 'per_bedroom': 100000, 'per_bathroom': 65000, 'per_car_space': 40000, 'per_pool': 80000, 'per_storey': 50000, 'per_renovation_level': 60000, 'per_water_view': 180000, 'per_cladding_level': 25000, 'per_kitchen_point': 15000, 'per_ac_ducted': 25000, 'per_year_age': 3500, 'condition_pct_per_point': 0.05, 'per_renovation_quality_point': 20000},
    'Burleigh Waters': {'land_per_sqm': 1000, 'floor_per_sqm': 3000, 'per_bedroom': 125000, 'per_bathroom': 85000, 'per_car_space': 45000, 'per_pool': 90000, 'per_storey': 60000, 'per_renovation_level': 80000, 'per_water_view': 250000, 'per_cladding_level': 30000, 'per_kitchen_point': 20000, 'per_ac_ducted': 30000, 'per_year_age': 5000, 'condition_pct_per_point': 0.05, 'per_renovation_quality_point': 25000},
    'Merrimac':        {'land_per_sqm': 375, 'floor_per_sqm': 2000, 'per_bedroom': 75000, 'per_bathroom': 50000, 'per_car_space': 35000, 'per_pool': 65000, 'per_storey': 40000, 'per_renovation_level': 50000, 'per_water_view': 100000, 'per_cladding_level': 18000, 'per_kitchen_point': 10000, 'per_ac_ducted': 18000, 'per_year_age': 2500, 'condition_pct_per_point': 0.05, 'per_renovation_quality_point': 12000},
    'Reedy Creek':     {'land_per_sqm': 275, 'floor_per_sqm': 2500, 'per_bedroom': 110000, 'per_bathroom': 75000, 'per_car_space': 40000, 'per_pool': 80000, 'per_storey': 50000, 'per_renovation_level': 65000, 'per_water_view': 130000, 'per_cladding_level': 25000, 'per_kitchen_point': 15000, 'per_ac_ducted': 25000, 'per_year_age': 3000, 'condition_pct_per_point': 0.05, 'per_renovation_quality_point': 18000},
    'Worongary':       {'land_per_sqm': 225, 'floor_per_sqm': 2500, 'per_bedroom': 115000, 'per_bathroom': 80000, 'per_car_space': 40000, 'per_pool': 80000, 'per_storey': 50000, 'per_renovation_level': 65000, 'per_water_view': 130000, 'per_cladding_level': 25000, 'per_kitchen_point': 15000, 'per_ac_ducted': 25000, 'per_year_age': 3000, 'condition_pct_per_point': 0.05, 'per_renovation_quality_point': 18000},
    'Carrara':         {'land_per_sqm': 400, 'floor_per_sqm': 2200, 'per_bedroom': 80000, 'per_bathroom': 55000, 'per_car_space': 35000, 'per_pool': 65000, 'per_storey': 40000, 'per_renovation_level': 50000, 'per_water_view': 100000, 'per_cladding_level': 18000, 'per_kitchen_point': 10000, 'per_ac_ducted': 18000, 'per_year_age': 2500, 'condition_pct_per_point': 0.05, 'per_renovation_quality_point': 12000},
}
DEFAULT_ADJUSTMENT_RATES = {'land_per_sqm': 450, 'floor_per_sqm': 2500, 'per_bedroom': 85000, 'per_bathroom': 60000, 'per_car_space': 35000, 'per_pool': 75000, 'per_storey': 45000, 'per_renovation_level': 55000, 'per_water_view': 120000, 'per_cladding_level': 20000, 'per_kitchen_point': 12000, 'per_ac_ducted': 20000, 'per_year_age': 3000, 'condition_pct_per_point': 0.05, 'per_renovation_quality_point': 18000}

# ─── Ordinal encoding maps for categorical features ─────────────────────────
RENOVATION_LEVEL_MAP = {
    'original': 1,
    'partially_renovated': 2,
    'cosmetically_updated': 3,
    'fully_renovated': 4,
    'new_build': 5,
}

CLADDING_MATERIAL_MAP = {
    'weatherboard': 1,
    'brick': 2,
    'render': 3,
    'stone': 4,
}


# ─── GAP 2: Adjustment Factor Calculation (Hybrid: Regression + Fallback) ──────

def _load_sold_comparables(client):
    """
    Load sold property records from two databases and merge by suburb.

    Sources (in priority order):
      1. Gold_Coast_Recently_Sold — properties monitored through the scraper pipeline.
         Full enrichment (property_valuation_data, floor plans) but only ~16 records.
      2. Target_Market_Sold_Last_12_Months — 12 months of historical sold records from
         Domain scraping. ~1,600 records across 8 suburbs. Has sale_price, sale_date,
         bedrooms, bathrooms, land_size_sqm, property_type. No GPT analysis fields.

    Returns dict keyed by lowercase_underscore suburb name:
      { 'robina': [doc, ...], 'varsity_lakes': [...], ... }

    Both sources are normalised so precompute_property_valuation() can use them
    interchangeably. Duplicate addresses are deduped (recently_sold takes priority).
    """
    result = {}

    SUBURB_DISPLAY = {
        'robina': 'Robina', 'varsity_lakes': 'Varsity Lakes',
        'burleigh_waters': 'Burleigh Waters', 'burleigh_heads': 'Burleigh Heads',
        'mudgeeraba': 'Mudgeeraba', 'reedy_creek': 'Reedy Creek',
        'merrimac': 'Merrimac', 'worongary': 'Worongary', 'carrara': 'Carrara',
    }

    # ── Source 1: Gold_Coast sold properties (listing_status: "sold") ──
    try:
        gc_db = client['Gold_Coast']
        _SKIP_SOLD = {'suburb_median_prices', 'suburb_statistics', 'change_detection_snapshots',
                      'address_search_index', 'precomputed_market_charts'}
        for col_name in gc_db.list_collection_names():
            if col_name.startswith('system.') or col_name in _SKIP_SOLD:
                continue
            suburb_key = col_name.lower().replace(' ', '_')
            docs = list(gc_db[col_name].find({
                'listing_status': 'sold',
                'sale_price': {'$exists': True, '$ne': None}
            }))
            for doc in docs:
                if not doc.get('suburb_scraped'):
                    doc['suburb_scraped'] = (
                        doc.get('suburb') or doc.get('original_suburb') or
                        SUBURB_DISPLAY.get(suburb_key, '')
                    )
                doc['_sold_source'] = 'recently_sold'
            if docs:
                result.setdefault(suburb_key, []).extend(docs)
    except Exception as e:
        print(f"  ⚠️  Gold_Coast sold properties load error: {e}")

    # ── Source 2: Target_Market_Sold_Last_12_Months (historical depth) ───────
    try:
        tdb = client['Target_Market_Sold_Last_12_Months']
        for col_name in tdb.list_collection_names():
            suburb_key = col_name.lower().replace(' ', '_')
            docs = list(tdb[col_name].find({'sale_price': {'$exists': True, '$ne': None}}))
            display_suburb = SUBURB_DISPLAY.get(suburb_key, suburb_key.replace('_', ' ').title())
            existing_addrs = {
                d.get('address', '').lower().strip()
                for d in result.get(suburb_key, [])
            }
            for doc in docs:
                doc['suburb_scraped'] = display_suburb
                doc['_sold_source'] = 'target_market_12m'
            # Deduplicate: skip docs whose address already came from recently_sold
            new_docs = [
                d for d in docs
                if d.get('address', '').lower().strip() not in existing_addrs
            ]
            if new_docs:
                result.setdefault(suburb_key, []).extend(new_docs)
    except Exception as e:
        print(f"  ⚠️  Target_Market_Sold_Last_12_Months load error: {e}")

    return result


# ─── Coordinate & Timeline Preloaders ─────────────────────────────────────────

def _preload_gc_coordinates(client, suburbs):
    """
    Bulk-load LATITUDE/LONGITUDE from Gold_Coast.[suburb] for all target suburbs.
    Returns {suburb_key: {"street_no street_name": (lat, lng), ...}}.
    """
    from pymongo.errors import OperationFailure
    gc_db = client['Gold_Coast']
    result = {}
    total = 0

    for suburb_key in suburbs:
        coords = {}
        gc_col = gc_db[suburb_key]
        max_retries = 3
        for attempt in range(max_retries):
            try:
                cursor = gc_col.find(
                    {'LATITUDE': {'$exists': True}, 'LONGITUDE': {'$exists': True}},
                    {'STREET_NO_1': 1, 'STREET_NAME': 1, 'LATITUDE': 1, 'LONGITUDE': 1}
                )
                for doc in cursor:
                    lat = doc.get('LATITUDE')
                    lon = doc.get('LONGITUDE')
                    if lat and lon:
                        try:
                            lat_f, lon_f = float(lat), float(lon)
                            sno = str(doc.get('STREET_NO_1', '')).strip()
                            sname = (doc.get('STREET_NAME') or '').strip().lower()
                            if sno and sname:
                                coords[f"{sno} {sname}"] = (lat_f, lon_f)
                        except (ValueError, TypeError):
                            pass
                time.sleep(1.0)
                break
            except OperationFailure as e:
                if ('16500' in str(e) or '429' in str(e)) and attempt < max_retries - 1:
                    wait_time = 3.0 * (attempt + 1)
                    print(f"  ⚠️  Rate limited loading {suburb_key} coords, waiting {wait_time}s...")
                    time.sleep(wait_time)
                    coords = {}
                else:
                    print(f"  ⚠️  Error loading Gold_Coast.{suburb_key} coordinates: {e}")
                    break
            except Exception as e:
                print(f"  ⚠️  Error loading Gold_Coast.{suburb_key} coordinates: {e}")
                break

        result[suburb_key] = coords
        total += len(coords)

    print(f"✅ Pre-loaded {total} Gold_Coast coordinates across {len(suburbs)} suburbs")
    return result


def _preload_gc_timelines(client, suburbs):
    """
    Bulk-load property_timeline from Gold_Coast.[suburb] and extract earliest
    sale year as approximate build year.
    Returns {suburb_key: {"street_no street_name": year, ...}}.
    """
    from pymongo.errors import OperationFailure
    gc_db = client['Gold_Coast']
    result = {}
    total = 0

    for suburb_key in suburbs:
        timelines = {}
        gc_col = gc_db[suburb_key]
        max_retries = 3
        for attempt in range(max_retries):
            try:
                cursor = gc_col.find(
                    {'scraped_data.property_timeline': {'$exists': True, '$ne': []}},
                    {'STREET_NO_1': 1, 'STREET_NAME': 1, 'scraped_data.property_timeline': 1}
                )
                for doc in cursor:
                    timeline = (doc.get('scraped_data') or {}).get('property_timeline', [])
                    if not timeline:
                        continue
                    # Find earliest year from timeline entries
                    earliest_year = None
                    for entry in timeline:
                        date_str = entry.get('date', '') if isinstance(entry, dict) else ''
                        if date_str:
                            # Timeline dates are typically "DD Mon YYYY" or "Mon YYYY" or just "YYYY"
                            year_match = re.search(r'(\d{4})', str(date_str))
                            if year_match:
                                year = int(year_match.group(1))
                                if 1950 <= year <= 2026:
                                    if earliest_year is None or year < earliest_year:
                                        earliest_year = year
                    if earliest_year:
                        sno = str(doc.get('STREET_NO_1', '')).strip()
                        sname = (doc.get('STREET_NAME') or '').strip().lower()
                        if sno and sname:
                            timelines[f"{sno} {sname}"] = earliest_year
                time.sleep(1.0)
                break
            except OperationFailure as e:
                if ('16500' in str(e) or '429' in str(e)) and attempt < max_retries - 1:
                    wait_time = 3.0 * (attempt + 1)
                    print(f"  ⚠️  Rate limited loading {suburb_key} timelines, waiting {wait_time}s...")
                    time.sleep(wait_time)
                    timelines = {}
                else:
                    print(f"  ⚠️  Error loading Gold_Coast.{suburb_key} timelines: {e}")
                    break
            except Exception as e:
                print(f"  ⚠️  Error loading Gold_Coast.{suburb_key} timelines: {e}")
                break

        result[suburb_key] = timelines
        total += len(timelines)

    print(f"✅ Pre-loaded {total} Gold_Coast build year estimates across {len(suburbs)} suburbs")
    return result


def _parse_address_key(address):
    """
    Parse an address into (street_no, street_name_lower) for cross-referencing
    against Gold_Coast lookup dicts. Handles unit addresses, ranges, prefixes.
    Returns list of candidate keys to try, or empty list.
    """
    if not address:
        return []

    parts = address.split(',')
    if not parts:
        return []

    street_part = parts[0].strip()

    # Strip leading prefixes
    cleaned = street_part
    cleaned = re.sub(r'^(?:Type\s+\w+/)', '', cleaned, flags=re.IGNORECASE).strip()
    cleaned = re.sub(r'^(?:Unit\s+\d+\s+)', '', cleaned, flags=re.IGNORECASE).strip()
    cleaned = re.sub(r'^(?:Lot\s+)', '', cleaned, flags=re.IGNORECASE).strip()
    cleaned = re.sub(r'^(?:ID:\d+/)', '', cleaned, flags=re.IGNORECASE).strip()
    cleaned = re.sub(r'^\d+\s+[A-Za-z&]+\s*/\s*', '', cleaned).strip()
    cleaned = re.sub(r'^\d+\s*&\s*\d+\w*\s*/\s*', '', cleaned).strip()

    tokens = cleaned.split()
    if len(tokens) < 2:
        return []

    raw_no = tokens[0]
    street_name = ' '.join(tokens[1:]).lower()

    # Build candidate street numbers
    candidates = [raw_no]
    if '/' in raw_no:
        building_no = raw_no.split('/')[-1]
        candidates.append(building_no)
        if '-' in building_no:
            candidates.append(building_no.split('-')[0])
    if '-' in raw_no and '/' not in raw_no:
        candidates.append(raw_no.split('-')[0])
    stripped = re.sub(r'[a-zA-Z]+$', '', raw_no)
    if stripped and stripped != raw_no:
        candidates.append(stripped)

    # Deduplicate
    seen = set()
    unique = []
    for c in candidates:
        if c not in seen:
            seen.add(c)
            unique.append(c)

    return [(no, street_name) for no in unique]


def _lookup_in_gc(candidates, gc_lookup):
    """
    Try candidate (street_no, street_name) pairs against a Gold_Coast lookup dict.
    Returns the value or None.
    """
    for street_no, street_name in candidates:
        # Exact key match
        key = f"{street_no} {street_name}"
        if key in gc_lookup:
            return gc_lookup[key]
        # Partial match (Gold_Coast stores just first word of street name)
        first_word = street_name.split()[0] if street_name else ''
        if first_word:
            for k, v in gc_lookup.items():
                parts_k = k.split(' ', 1)
                if len(parts_k) == 2 and parts_k[0] == street_no and street_name.startswith(parts_k[1]):
                    return v
    return None


def _resolve_coordinates(doc, gc_coord_lookup, suburb_key):
    """
    Resolve coordinates for a property document.
    Priority: (1) geocoded_coordinates, (2) LATITUDE/LONGITUDE, (3) Gold_Coast cross-ref.
    Returns (lat, lon) or (None, None).
    """
    # Priority 1: geocoded_coordinates (For Sale collection)
    geo = doc.get('geocoded_coordinates') or {}
    if geo.get('latitude') and geo.get('longitude'):
        try:
            return (float(geo['latitude']), float(geo['longitude']))
        except (ValueError, TypeError):
            pass

    # Priority 2: Direct LATITUDE/LONGITUDE fields
    lat = doc.get('LATITUDE') or doc.get('latitude')
    lon = doc.get('LONGITUDE') or doc.get('longitude')
    if lat is not None and lon is not None:
        try:
            return (float(lat), float(lon))
        except (ValueError, TypeError):
            pass

    # Priority 3: Gold_Coast cross-reference by address
    suburb_coords = gc_coord_lookup.get(suburb_key, {})
    if suburb_coords:
        address = doc.get('address', '')
        candidates = _parse_address_key(address)
        result = _lookup_in_gc(candidates, suburb_coords)
        if result:
            return result

    return (None, None)


def _resolve_build_year(doc, gc_timeline_lookup, suburb_key):
    """
    Resolve approximate build year for a property document.
    Priority: (1) doc's own property_timeline, (2) Gold_Coast cross-ref.
    Returns int(year) or None.
    """
    # Priority 1: Doc's own timeline
    timeline = (doc.get('scraped_data') or {}).get('property_timeline', [])
    if timeline:
        earliest = None
        for entry in timeline:
            date_str = entry.get('date', '') if isinstance(entry, dict) else ''
            if date_str:
                year_match = re.search(r'(\d{4})', str(date_str))
                if year_match:
                    year = int(year_match.group(1))
                    if 1950 <= year <= 2026:
                        if earliest is None or year < earliest:
                            earliest = year
        if earliest:
            return earliest

    # Priority 2: Gold_Coast cross-reference
    suburb_timelines = gc_timeline_lookup.get(suburb_key, {})
    if suburb_timelines:
        address = doc.get('address', '')
        candidates = _parse_address_key(address)
        result = _lookup_in_gc(candidates, suburb_timelines)
        if result:
            return result

    return None


# ─── Time Adjustment for Stale Sales ─────────────────────────────────────────

_median_price_cache = {}  # (suburb, property_type) → list of {date, median}


def _load_median_prices(db, suburb, property_type):
    """Load quarterly median prices from suburb_median_prices collection.
    Results are cached per (suburb, property_type) for the script run."""
    key = (suburb.lower().replace(' ', '_'), property_type)
    if key in _median_price_cache:
        return _median_price_cache[key]
    doc = db['suburb_median_prices'].find_one({
        'suburb': key[0],
        'property_type': property_type,
    })
    series = doc.get('data', []) if doc else []
    _median_price_cache[key] = series
    return series


def _date_to_quarter_key(dt):
    """Convert a datetime to the 'YYYY-Qn' format used in suburb_median_prices."""
    q = (dt.month - 1) // 3 + 1
    return f"{dt.year}-Q{q}"


def _find_quarter_median(series, quarter_key):
    """Find the median price for a given quarter key in the series."""
    for entry in series:
        if entry.get('date') == quarter_key:
            return entry.get('median')
    return None


def time_adjust_sale_price(sale_price, sale_date_ms, suburb, property_type, db):
    """
    Adjust a sale price from the past to today's market using suburb median
    price growth.  Returns (adjusted_price, metadata_dict).

    If median data is unavailable for either quarter, returns the original
    price with a note in metadata explaining why.
    """
    if not sale_date_ms or not sale_price:
        return sale_price, None

    sale_dt = datetime.fromtimestamp(sale_date_ms / 1000)
    now_dt = datetime.utcnow()

    sale_quarter = _date_to_quarter_key(sale_dt)
    current_quarter = _date_to_quarter_key(now_dt)

    if sale_quarter == current_quarter:
        return sale_price, None  # Same quarter — no adjustment needed

    series = _load_median_prices(db, suburb, property_type)

    sale_median = _find_quarter_median(series, sale_quarter)
    current_median = _find_quarter_median(series, current_quarter)

    # If current quarter has no data yet, use the most recent available quarter
    if current_median is None and series:
        current_median = series[-1].get('median')
        current_quarter = series[-1].get('date', current_quarter)

    if not sale_median or not current_median or sale_median <= 0:
        return sale_price, {
            'applied': False,
            'reason': 'insufficient median data',
            'sale_quarter': sale_quarter,
            'current_quarter': current_quarter,
        }

    growth_factor = current_median / sale_median
    adjusted_price = round(sale_price * growth_factor)

    return adjusted_price, {
        'applied': True,
        'original_price': sale_price,
        'adjusted_price': adjusted_price,
        'growth_factor': round(growth_factor, 4),
        'sale_quarter': sale_quarter,
        'sale_quarter_median': sale_median,
        'current_quarter': current_quarter,
        'current_quarter_median': current_median,
    }


def calculate_adjustment_factors_regression(recent_sales, gc_timeline_lookup=None, suburb_key=None):
    """
    Tier 1: Derive $/unit adjustment rates from OLS regression on recent sales.
    Returns dict of rates or None if insufficient data (< 15 valid sales).
    Features: land, floor, beds, baths, cars, pool (0/1), stories,
              renovation_level (1-5), water_view (0/1), cladding_level (1-4),
              kitchen_score (1-10), ac_ducted (0/1), age (years since build).
    Uses numpy lstsq — no sklearn dependency needed.
    """
    current_year = datetime.utcnow().year
    valid = []
    for s in recent_sales:
        price = parse_price(s.get('sale_price') or s.get('sold_price') or s.get('last_sold_price'))
        land = resolve_land_size(s)
        floor = resolve_floor_area(s)
        beds = s.get('bedrooms')
        baths = s.get('bathrooms')
        cars = s.get('car_spaces') or s.get('carspaces') or 0
        # Pool and storey from GPT photo analysis
        pvd = s.get('property_valuation_data', {})
        pool = 1 if pvd.get('outdoor', {}).get('pool_present') else 0
        stories = pvd.get('property_overview', {}).get('number_of_stories') or 1
        stories = min(stories, 3)  # Cap at 3 for houses
        # New features from GPT photo analysis
        reno = pvd.get('renovation', {})
        reno_level = RENOVATION_LEVEL_MAP.get(reno.get('overall_renovation_level'), 3)  # default cosmetically_updated
        water_view = 1 if pvd.get('outdoor', {}).get('water_views') else 0
        cladding = CLADDING_MATERIAL_MAP.get(pvd.get('exterior', {}).get('cladding_material'), 2)  # default brick
        kitchen_score = pvd.get('kitchen', {}).get('quality_score') or 5
        ac_type = pvd.get('property_metadata', {}).get('air_conditioning', '')
        ac_ducted = 1 if ac_type == 'ducted' else 0
        # Property age from build year
        build_year = _resolve_build_year(s, gc_timeline_lookup or {}, suburb_key or '') if gc_timeline_lookup else None
        age = (current_year - build_year) if build_year else None
        if price and land and floor and beds is not None:
            valid.append({
                'price': price,
                'land': land,
                'floor': floor,
                'beds': beds,
                'baths': baths or 0,
                'cars': cars or 0,
                'pool': pool,
                'stories': stories,
                'reno_level': reno_level,
                'water_view': water_view,
                'cladding': cladding,
                'kitchen_score': kitchen_score,
                'ac_ducted': ac_ducted,
                'age': age,
            })

    if len(valid) < 15:
        return None

    # Use median age for records missing build year data
    ages_known = [v['age'] for v in valid if v['age'] is not None]
    median_age = sorted(ages_known)[len(ages_known) // 2] if ages_known else 15
    for v in valid:
        if v['age'] is None:
            v['age'] = median_age

    X = np.array([[v['land'], v['floor'], v['beds'], v['baths'], v['cars'],
                    v['pool'], v['stories'], v['reno_level'], v['water_view'],
                    v['cladding'], v['kitchen_score'], v['ac_ducted'],
                    v['age']] for v in valid])
    y = np.array([v['price'] for v in valid])
    X_with_intercept = np.column_stack([np.ones(len(X)), X])

    try:
        beta, residuals, rank, sv = np.linalg.lstsq(X_with_intercept, y, rcond=None)
        # Age coefficient can be negative (older = cheaper) — don't clamp to 0
        age_coeff = round(float(beta[13]))
        return {
            'land_per_sqm': max(0, round(float(beta[1]))),
            'floor_per_sqm': max(0, round(float(beta[2]))),
            'per_bedroom': max(0, round(float(beta[3]))),
            'per_bathroom': max(0, round(float(beta[4]))),
            'per_car_space': max(0, round(float(beta[5]))),
            'per_pool': max(0, round(float(beta[6]))),
            'per_storey': max(0, round(float(beta[7]))),
            'per_renovation_level': max(0, round(float(beta[8]))),
            'per_water_view': max(0, round(float(beta[9]))),
            'per_cladding_level': max(0, round(float(beta[10]))),
            'per_kitchen_point': max(0, round(float(beta[11]))),
            'per_ac_ducted': max(0, round(float(beta[12]))),
            'per_year_age': abs(age_coeff),  # Store as positive (cost per year older)
            'condition_pct_per_point': 0.05,  # Not derivable from regression, use default
            'source': 'regression',
            'sample_size': len(valid),
            'r_squared': None,
        }
    except Exception:
        return None


def _validate_regression_rates(regression_rates, fallback_rates):
    """
    Per-feature validation of regression coefficients against methodology fallbacks.
    Multicollinearity in OLS causes correlated features (beds/baths/cars) to get
    wildly wrong individual coefficients — one absorbs all effect while others go to 0.
    For each feature: if the regression rate is 0 or exceeds 2× the fallback, replace
    it with the fallback rate. This keeps regression benefits where it works (land,
    floor area) while protecting against multicollinearity on discrete features.
    Returns (validated_rates, n_overridden).
    """
    RATE_KEYS = ['land_per_sqm', 'floor_per_sqm', 'per_bedroom', 'per_bathroom', 'per_car_space', 'per_pool', 'per_storey', 'per_renovation_level', 'per_water_view', 'per_cladding_level', 'per_kitchen_point', 'per_ac_ducted', 'per_year_age']
    validated = dict(regression_rates)
    n_overridden = 0

    for key in RATE_KEYS:
        reg_val = regression_rates.get(key, 0)
        fallback_val = fallback_rates.get(key, 0)

        if fallback_val == 0:
            continue  # No fallback reference to validate against

        # Override if regression rate is 0 (feature effect lost to collinearity)
        # or if it exceeds 2× the methodology fallback (implausibly high)
        if reg_val == 0 or reg_val > 2.0 * fallback_val:
            validated[key] = fallback_val
            n_overridden += 1

    # Always inject condition_pct_per_point from fallback (percentage-based, not in OLS)
    if 'condition_pct_per_point' not in validated and 'condition_pct_per_point' in fallback_rates:
        validated['condition_pct_per_point'] = fallback_rates['condition_pct_per_point']

    if n_overridden > 0:
        validated['source'] = 'regression_validated'
        validated['n_rates_overridden'] = n_overridden

    return validated, n_overridden


def get_adjustment_rates(suburb, recent_sales_docs, gc_timeline_lookup=None, suburb_key=None):
    """
    Get adjustment rates: try regression first, validate per-feature, fall back
    to suburb-specific methodology rates.
    Returns (rates_dict, source_string).
    """
    fallback_rates = SUBURB_ADJUSTMENT_RATES.get(suburb, DEFAULT_ADJUSTMENT_RATES)

    # Tier 1: Try regression
    regression_rates = calculate_adjustment_factors_regression(
        recent_sales_docs, gc_timeline_lookup, suburb_key)
    if regression_rates:
        # Validate each coefficient — replace nonsensical ones with fallback
        validated, n_overridden = _validate_regression_rates(regression_rates, fallback_rates)
        if n_overridden > 0:
            print(f"      Regression rate validation: {n_overridden} rate(s) replaced with fallback")
        return validated, validated.get('source', 'regression')

    # Tier 2: Suburb-specific fallback
    return {**fallback_rates, 'source': 'methodology_fallback', 'sample_size': 0}, 'methodology_fallback'


def calculate_adjustments(subject_features, comp_features, comp_price, rates):
    """
    GAP 2: Calculate dollar adjustments from comparable to subject.
    Positive adjustment = subject is superior (comp price adjusted UP).
    Returns dict with per-feature adjustments and total.
    """
    adjustments = {}

    feature_map = [
        ('land_size', 'land_size_sqm', 'land_per_sqm'),
        ('floor_area', 'floor_area_sqm', 'floor_per_sqm'),
        ('bedrooms', 'bedrooms', 'per_bedroom'),
        ('bathrooms', 'bathrooms', 'per_bathroom'),
        ('car_spaces', 'car_spaces', 'per_car_space'),
    ]

    for label, feat_key, rate_key in feature_map:
        s_val = subject_features.get(feat_key)
        c_val = comp_features.get(feat_key)
        # Skip adjustment if either side has missing data for continuous features
        # (land_size, floor_area). Missing != zero — a missing value means we don't
        # know the feature, not that it's absent.
        if s_val is None or c_val is None or (s_val == 0 and feat_key in ('land_size_sqm', 'floor_area_sqm')) or (c_val == 0 and feat_key in ('land_size_sqm', 'floor_area_sqm')):
            adjustments[label] = {
                'subject_value': s_val or 0,
                'comp_value': c_val or 0,
                'diff': 0,
                'rate': rates.get(rate_key, 0),
                'dollars': 0,
                'skipped': True,
            }
            continue
        s_val = s_val or 0
        c_val = c_val or 0
        diff = s_val - c_val
        rate = rates.get(rate_key, 0)
        adj_dollars = round(diff * rate)
        adjustments[label] = {
            'subject_value': s_val,
            'comp_value': c_val,
            'diff': diff,
            'rate': rate,
            'dollars': adj_dollars,
        }

    # Pool adjustment (binary: has pool vs no pool)
    s_pool = 1 if subject_features.get('pool_present') else 0
    c_pool = 1 if comp_features.get('pool_present') else 0
    pool_diff = s_pool - c_pool
    pool_rate = rates.get('per_pool', 50000)
    pool_dollars = round(pool_diff * pool_rate)
    adjustments['pool'] = {
        'subject_value': s_pool,
        'comp_value': c_pool,
        'diff': pool_diff,
        'rate': pool_rate,
        'dollars': pool_dollars,
    }

    # Storey adjustment (structural premium beyond floor area)
    s_stories = subject_features.get('number_of_stories') or 1
    c_stories = comp_features.get('number_of_stories') or 1
    # Cap at 3 for houses — higher values are likely apartment buildings misclassified
    s_stories = min(s_stories, 3)
    c_stories = min(c_stories, 3)
    storey_diff = s_stories - c_stories
    storey_rate = rates.get('per_storey', 45000)
    storey_dollars = round(storey_diff * storey_rate)
    adjustments['stories'] = {
        'subject_value': s_stories,
        'comp_value': c_stories,
        'diff': storey_diff,
        'rate': storey_rate,
        'dollars': storey_dollars,
    }

    # Renovation level adjustment (ordinal: 1=original → 5=new_build)
    s_reno = subject_features.get('renovation_level', 3)
    c_reno = comp_features.get('renovation_level', 3)
    reno_diff = s_reno - c_reno
    reno_rate = rates.get('per_renovation_level', 55000)
    reno_dollars = round(reno_diff * reno_rate)
    adjustments['renovation'] = {
        'subject_value': s_reno,
        'comp_value': c_reno,
        'diff': reno_diff,
        'rate': reno_rate,
        'dollars': reno_dollars,
    }

    # Water views adjustment (binary: has water view vs no water view)
    s_water = 1 if subject_features.get('water_views') else 0
    c_water = 1 if comp_features.get('water_views') else 0
    water_diff = s_water - c_water
    water_rate = rates.get('per_water_view', 120000)
    water_dollars = round(water_diff * water_rate)
    adjustments['water_views'] = {
        'subject_value': s_water,
        'comp_value': c_water,
        'diff': water_diff,
        'rate': water_rate,
        'dollars': water_dollars,
    }

    # Cladding material adjustment (ordinal: 1=weatherboard → 4=stone)
    s_clad = subject_features.get('cladding_level', 2)
    c_clad = comp_features.get('cladding_level', 2)
    clad_diff = s_clad - c_clad
    clad_rate = rates.get('per_cladding_level', 20000)
    clad_dollars = round(clad_diff * clad_rate)
    adjustments['cladding'] = {
        'subject_value': s_clad,
        'comp_value': c_clad,
        'diff': clad_diff,
        'rate': clad_rate,
        'dollars': clad_dollars,
    }

    # Kitchen quality score adjustment (1-10 scale)
    s_kitchen = subject_features.get('kitchen_score') or 5
    c_kitchen = comp_features.get('kitchen_score') or 5
    kitchen_diff = s_kitchen - c_kitchen
    kitchen_rate = rates.get('per_kitchen_point', 12000)
    kitchen_dollars = round(kitchen_diff * kitchen_rate)
    adjustments['kitchen'] = {
        'subject_value': s_kitchen,
        'comp_value': c_kitchen,
        'diff': kitchen_diff,
        'rate': kitchen_rate,
        'dollars': kitchen_dollars,
    }

    # Air conditioning type adjustment (binary: ducted premium)
    s_ac = 1 if subject_features.get('ac_ducted') else 0
    c_ac = 1 if comp_features.get('ac_ducted') else 0
    ac_diff = s_ac - c_ac
    ac_rate = rates.get('per_ac_ducted', 20000)
    ac_dollars = round(ac_diff * ac_rate)
    adjustments['ac_type'] = {
        'subject_value': s_ac,
        'comp_value': c_ac,
        'diff': ac_diff,
        'rate': ac_rate,
        'dollars': ac_dollars,
    }

    # Condition adjustment (using interior condition score as proxy for age/condition)
    # Only adjust when both sides have real condition data (not defaults)
    s_cond = subject_features.get('condition_score')
    c_cond = comp_features.get('condition_score')
    if s_cond is not None and c_cond is not None and s_cond != 5 and c_cond != 5:
        cond_diff = s_cond - c_cond
        cond_dollars = round(cond_diff * rates.get('condition_pct_per_point', 0.05) * comp_price)
    else:
        s_cond = s_cond or 5
        c_cond = c_cond or 5
        cond_diff = 0
        cond_dollars = 0
    adjustments['condition'] = {
        'subject_value': s_cond,
        'comp_value': c_cond,
        'diff': round(cond_diff, 1),
        'rate': rates.get('condition_pct_per_point', 0.05),
        'dollars': cond_dollars,
    }

    # Property age adjustment (newer = higher value)
    # Only apply when both subject and comp have build year data
    s_build_year = subject_features.get('approximate_build_year')
    c_build_year = comp_features.get('approximate_build_year')
    if s_build_year and c_build_year:
        # Positive diff = subject is newer (adjusted UP)
        age_diff = s_build_year - c_build_year  # years newer
        age_rate = rates.get('per_year_age', 3000)
        age_dollars = round(age_diff * age_rate)
    else:
        age_diff = 0
        age_rate = rates.get('per_year_age', 3000)
        age_dollars = 0
    adjustments['property_age'] = {
        'subject_value': s_build_year or 0,
        'comp_value': c_build_year or 0,
        'diff': age_diff,
        'rate': age_rate,
        'dollars': age_dollars,
    }

    # Beach proximity adjustment (non-linear premium based on distance to
    # nearest beach). The premium curve is steepest in the 0-2km zone and
    # flattens beyond 4km. The adjustment is the difference in premium
    # percentages between subject and comparable, applied to comp price.
    s_beach = subject_features.get('beach_distance_km')
    c_beach = comp_features.get('beach_distance_km')
    if s_beach is not None and c_beach is not None:
        s_prem = beach_premium_pct(s_beach)
        c_prem = beach_premium_pct(c_beach)
        # Positive = subject is closer to beach (adjusted UP)
        beach_dollars = round((s_prem - c_prem) * comp_price)
    else:
        s_prem = 0.0
        c_prem = 0.0
        beach_dollars = 0
    adjustments['beach_proximity'] = {
        'subject_value': round(s_beach, 2) if s_beach is not None else None,
        'comp_value': round(c_beach, 2) if c_beach is not None else None,
        'diff': round(s_prem - c_prem, 4),
        'rate': 'pct_of_price',
        'dollars': beach_dollars,
        'skipped': s_beach is None or c_beach is None,
    }

    # Renovation quality adjustment (composite 0-10 score)
    s_rq = subject_features.get('renovation_quality_score')
    c_rq = comp_features.get('renovation_quality_score')
    rq_rate = rates.get('per_renovation_quality_point', 18000)
    if s_rq is not None and c_rq is not None:
        rq_diff = round(s_rq - c_rq, 1)
        rq_dollars = round(rq_diff * rq_rate)
    else:
        rq_diff = 0
        rq_dollars = 0
    adjustments['renovation_quality'] = {
        'subject_value': s_rq,
        'comp_value': c_rq,
        'diff': rq_diff,
        'rate': rq_rate,
        'dollars': rq_dollars,
        'skipped': s_rq is None or c_rq is None,
    }

    # Street premium adjustment (% of comp price)
    s_sp = subject_features.get('street_premium_pct')
    c_sp = comp_features.get('street_premium_pct')
    if s_sp is not None and c_sp is not None:
        sp_diff = round(s_sp - c_sp, 4)
        sp_dollars = round(sp_diff * comp_price)
    else:
        sp_diff = 0.0
        sp_dollars = 0
    adjustments['street_premium'] = {
        'subject_value': round(s_sp, 4) if s_sp is not None else None,
        'comp_value': round(c_sp, 4) if c_sp is not None else None,
        'diff': sp_diff,
        'rate': 'pct_of_price',
        'dollars': sp_dollars,
        'skipped': s_sp is None or c_sp is None,
    }

    # Micro-location premium adjustment (% of comp price)
    s_ml = subject_features.get('micro_location_premium_pct')
    c_ml = comp_features.get('micro_location_premium_pct')
    if s_ml is not None and c_ml is not None:
        ml_diff = round(s_ml - c_ml, 4)
        ml_dollars = round(ml_diff * comp_price)
    else:
        ml_diff = 0.0
        ml_dollars = 0
    adjustments['micro_location'] = {
        'subject_value': round(s_ml, 4) if s_ml is not None else None,
        'comp_value': round(c_ml, 4) if c_ml is not None else None,
        'diff': ml_diff,
        'rate': 'pct_of_price',
        'dollars': ml_dollars,
        'skipped': s_ml is None or c_ml is None,
    }

    total = sum(a['dollars'] for a in adjustments.values())

    # Cap total adjustment relative to comp price.
    # Professional valuers use 25-30%, but for premium properties ($2M+) with
    # wide feature variance (waterfront, acreage, luxury reno), a tighter cap
    # truncates legitimate differences and causes systematic undervaluation.
    # Scale the cap: 30% base, up to 40% for properties above $2M.
    if comp_price and comp_price >= 2_000_000:
        cap_pct = 0.40
    elif comp_price and comp_price >= 1_500_000:
        cap_pct = 0.35
    else:
        cap_pct = 0.30
    max_adj = abs(comp_price * cap_pct) if comp_price else 0
    if abs(total) > max_adj and max_adj > 0:
        scale = max_adj / abs(total)
        total = round(total * scale)
        for a in adjustments.values():
            a['dollars'] = round(a['dollars'] * scale)

    adjusted_price = comp_price + total

    return {
        'adjustments': adjustments,
        'total_adjustment': total,
        'total_adjustment_pct': round(total / comp_price, 3) if comp_price else 0,
        'adjusted_price': round(adjusted_price),
        'rates_source': rates.get('source', 'unknown'),
    }


# ─── GAP 1 & 3: Independent Valuation + Verification ──────────────────────────

def compute_independent_valuation(comp_npui, slope, intercept):
    """
    GAP 1: Compute independent valuation for a comparable using the cohort regression line.
    Returns expected price at the comparable's NPUI position.
    """
    if slope is None or intercept is None:
        return None
    expected = slope * comp_npui + intercept
    return round(expected) if expected > 0 else None


def verify_comparable(comp_price, adjusted_price, independent_val,
                      all_adjusted_prices, data_quality_pct):
    """
    GAP 3: Verification system — checks if a comparable is reliable.

    Uses the feature-adjusted price as the primary accuracy measure:
      - After adjusting a comp's sale price for feature differences with the
        subject, all adjusted prices *should* converge to a similar value.
      - A comp whose adjusted price is an outlier has unexplained variance
        (motivated seller, special conditions, errors, etc.)

    Checks:
      1. Adjusted price deviation — how far this comp's adjusted price is from
         the cohort median adjusted price.  ≤15% = verified, 15-25% = marginal.
      2. Z-score outlier detection on adjusted prices.
      3. Data quality threshold (feature coverage).

    Also stores the NPUI independent_val accuracy for display in the
    comparison table (informational, not used for status determination).
    """
    checks = []
    is_verified = True

    # Check 1: Adjusted price deviation from cohort median
    accuracy_pct = None
    if adjusted_price and all_adjusted_prices and len(all_adjusted_prices) >= 3:
        median_adj = sorted(all_adjusted_prices)[len(all_adjusted_prices) // 2]
        if median_adj > 0:
            accuracy_pct = (adjusted_price - median_adj) / median_adj
            if abs(accuracy_pct) > 0.15:
                is_verified = False
                checks.append(f"Adjusted price {accuracy_pct:+.0%} from cohort median")

    # Check 2: Z-score outlier detection on adjusted prices
    z_score = None
    if all_adjusted_prices and len(all_adjusted_prices) >= 3:
        mean_p = sum(all_adjusted_prices) / len(all_adjusted_prices)
        std_p = (sum((p - mean_p) ** 2 for p in all_adjusted_prices) / len(all_adjusted_prices)) ** 0.5
        if std_p > 0:
            z_score = (adjusted_price - mean_p) / std_p
            if abs(z_score) > 2.0:
                is_verified = False
                checks.append(f"Adjusted price outlier (z-score={z_score:.1f})")

    # Check 3: Data quality threshold
    if data_quality_pct < 0.4:
        is_verified = False
        checks.append(f"Low data quality ({data_quality_pct:.0%} coverage)")

    # Informational: NPUI regression accuracy (for comparison table display only)
    npui_accuracy_pct = None
    if independent_val and independent_val > 0:
        npui_accuracy_pct = (comp_price - independent_val) / independent_val

    # Determine status tier
    if is_verified:
        status = 'verified'
    elif accuracy_pct is not None and abs(accuracy_pct) < 0.25:
        status = 'marginal'
    else:
        status = 'flagged'

    return {
        'is_verified': is_verified,
        'status': status,
        'checks_passed': len(checks) == 0,
        'issues': checks if checks else ['All checks passed'],
        'accuracy_pct': round(accuracy_pct, 3) if accuracy_pct is not None else None,
        'npui_accuracy_pct': round(npui_accuracy_pct, 3) if npui_accuracy_pct is not None else None,
        'z_score': round(z_score, 2) if z_score is not None else None,
        'data_quality_pct': round(data_quality_pct, 2),
    }


# ─── GAP 4: Narrative Generation ──────────────────────────────────────────────

def generate_adjustment_narrative(comp_address, comp_price, adjustment_result):
    """
    GAP 4: Generate human-readable narrative explaining adjustments.
    Returns a string describing the adjustment from comparable to subject.
    """
    adj = adjustment_result.get('adjustments', {})
    parts = []

    labels = {
        'land_size': ('land', 'm\u00b2'),
        'floor_area': ('floor area', 'm\u00b2'),
        'bedrooms': ('bedroom', ''),
        'bathrooms': ('bathroom', ''),
        'car_spaces': ('car space', ''),
        'condition': ('condition point', ''),
    }

    for key, (label, unit) in labels.items():
        a = adj.get(key, {})
        diff = a.get('diff', 0)
        dollars = a.get('dollars', 0)
        if diff != 0 and dollars != 0:
            if diff > 0:
                direction = 'more' if key in ('bedrooms', 'bathrooms', 'car_spaces') else 'larger'
            else:
                direction = 'fewer' if key in ('bedrooms', 'bathrooms', 'car_spaces') else 'smaller'
            unit_str = f" {unit}" if unit else ''
            parts.append(f"{abs(diff)}{unit_str} {direction} {label} ({dollars:+,})")

    total = adjustment_result.get('total_adjustment', 0)
    adjusted = adjustment_result.get('adjusted_price', comp_price)

    narrative = f"Compared to {comp_address} (${comp_price:,.0f}): "
    if parts:
        narrative += '; '.join(parts) + '. '
    narrative += f"Net adjustment: ${total:+,.0f}. Adjusted value: ${adjusted:,.0f}."

    return narrative


# ─── GAP 5: Weighting Logic ───────────────────────────────────────────────────

def calculate_weight(comp):
    """
    GAP 5: Calculate quality weight for a comparable based on 6 factors.

    No NPUI dependency — uses feature-adjustment data instead:
      1. Adjustment magnitude (25%): smaller total adjustment = more similar property
      2. Adjusted price accuracy (20%): how close to cohort median
      3. Proximity (20%): geographic distance to subject property
      4. Recency (15%): more recent sales are more relevant
      5. Verification status (10%): binary verified/not
      6. Data quality (10%): feature coverage percentage

    Returns dict with raw_weight and factor breakdown.
    """
    comp_price = comp.get('price', 0)

    # Factor 1: Adjustment magnitude (less adjustment = more similar property)
    adj_total = abs(comp.get('adjustment_result', {}).get('total_adjustment', 0))
    adj_pct = adj_total / comp_price if comp_price else 0
    adj_quality = max(0, 1 - adj_pct / 0.30)

    # Factor 2: Adjusted price accuracy (how close to cohort median)
    acc_pct = comp.get('verification', {}).get('accuracy_pct')
    if acc_pct is not None:
        adj_accuracy = max(0, 1 - abs(acc_pct) / 0.20)
    else:
        adj_accuracy = 0.5  # Unknown accuracy — neutral

    # Factor 3: Proximity (linear decay: 1.0 at 0km, 0.0 at 5km+)
    dist_km = comp.get('distance_km')
    if dist_km is not None:
        proximity = max(0.0, 1.0 - dist_km / 5.0)
    else:
        proximity = 0.5  # Unknown distance — neutral

    # Factor 4: Recency (for sales only, 1.0 = today, 0.0 = 12+ months ago)
    recency = 1.0
    sale_date_ms = comp.get('sale_date')
    if sale_date_ms:
        now_ms = time.time() * 1000
        months_ago = (now_ms - sale_date_ms) / (30 * 24 * 3600 * 1000)
        recency = max(0, 1 - months_ago / 12)

    # Factor 5: Verification status (1.0 if verified, 0.3 if not)
    verified = 1.0 if comp.get('verification', {}).get('is_verified', False) else 0.3

    # Factor 6: Data quality
    data_q = comp.get('verification', {}).get('data_quality_pct', 0.5)

    raw = (adj_quality * 0.30 + adj_accuracy * 0.20 + proximity * 0.15 +
           recency * 0.15 + verified * 0.10 + data_q * 0.10)

    return {
        'raw_weight': round(raw, 3),
        'factors': {
            'adjustment_quality': round(adj_quality, 2),
            'adjusted_accuracy': round(adj_accuracy, 2),
            'proximity': round(proximity, 2),
            'recency': round(recency, 2),
            'verification': round(verified, 2),
            'data_quality': round(data_q, 2),
        },
    }


def normalize_weights(points):
    """Normalize raw weights across all points so they sum to 1.0."""
    total = sum(p.get('weight', {}).get('raw_weight', 0) for p in points)
    if total > 0:
        for p in points:
            w = p.get('weight', {})
            w['normalized'] = round(w.get('raw_weight', 0) / total, 3)


# ─── Quality Comp Selection ──────────────────────────────────────────────────

def select_quality_comps(all_enriched_points, min_comps=3, target_comps=8):
    """
    Select the highest-quality comparables for the valuation calculation.

    Strategy:
      1. Classify comps into tiers: verified, marginal, flagged
      2. Rank within each tier by a quality score based on adjustment quality,
         adjusted price accuracy, recency, and data quality (no NPUI)
      3. Use verified first; only include lower tiers when needed

    Thresholds:
      - verified >= 5 → use top target_comps verified only
      - verified >= min_comps → add marginal to reach target_comps
      - verified < min_comps → use all tiers (cap target_comps + 2)

    Marks each point with included_in_valuation = True/False.
    """
    def quality_score(pt):
        """Composite quality score for ranking within a tier."""
        factors = pt.get('weight', {}).get('factors', {})
        return (
            factors.get('adjustment_quality', 0) * 0.25 +
            factors.get('adjusted_accuracy', 0) * 0.20 +
            factors.get('proximity', 0) * 0.20 +
            factors.get('recency', 0) * 0.20 +
            factors.get('data_quality', 0) * 0.15
        )

    verified, marginal, flagged = [], [], []
    for pt in all_enriched_points:
        status = pt.get('verification', {}).get('status', 'flagged')
        if status == 'verified':
            verified.append(pt)
        elif status == 'marginal':
            marginal.append(pt)
        else:
            flagged.append(pt)

    verified.sort(key=quality_score, reverse=True)
    marginal.sort(key=quality_score, reverse=True)
    flagged.sort(key=quality_score, reverse=True)

    selected_ids = set()

    if len(verified) >= 5:
        for pt in verified[:target_comps]:
            selected_ids.add(pt['id'])
    elif len(verified) >= min_comps:
        for pt in verified:
            selected_ids.add(pt['id'])
        remaining = target_comps - len(verified)
        for pt in marginal[:remaining]:
            selected_ids.add(pt['id'])
    else:
        fallback_target = min(target_comps + 2, len(all_enriched_points))
        for pt in verified:
            selected_ids.add(pt['id'])
        remaining = fallback_target - len(verified)
        for pt in marginal[:remaining]:
            selected_ids.add(pt['id'])
        remaining = fallback_target - len(selected_ids)
        for pt in flagged[:remaining]:
            selected_ids.add(pt['id'])

    for pt in all_enriched_points:
        pt['included_in_valuation'] = pt['id'] in selected_ids

    return all_enriched_points


# ─── GAP 6: Confidence Intervals ──────────────────────────────────────────────

def calculate_confidence(points, n_total_override=None):
    """
    GAP 6: Calculate weighted mean valuation and confidence interval
    from quality-selected comparable values (included_in_valuation = true).
    This ensures the reconciled_valuation matches the sum shown in the breakdown.
    Returns dict with valuation, confidence level, and range.
    """
    # Use ALL comparables that have weights and adjusted prices
    weighted_comps = [p for p in points
                      if p.get('weight', {}).get('normalized')
                      and p.get('adjustment_result', {}).get('adjusted_price')]

    if len(weighted_comps) < 2:
        return {
            'reconciled_valuation': None,
            'confidence': 'insufficient_data',
            'range': None,
            'std_dev': None,
            'cv': None,
            'n_verified': 0,
            'n_total': n_total_override if n_total_override is not None else len(points),
        }

    values = [p['adjustment_result']['adjusted_price'] for p in weighted_comps]
    weights = [p.get('weight', {}).get('normalized', 1.0 / len(weighted_comps)) for p in weighted_comps]

    # Weighted mean
    w_mean = sum(v * w for v, w in zip(values, weights))

    # Weighted standard deviation
    w_var = sum(w * (v - w_mean) ** 2 for v, w in zip(values, weights))
    w_std = math.sqrt(w_var) if w_var > 0 else 0

    # Coefficient of variation
    cv = w_std / w_mean if w_mean > 0 else 0

    # Count how many are verified (for reporting purposes)
    n_verified = sum(1 for p in weighted_comps if p.get('verification', {}).get('is_verified', False))

    # Confidence level based on CV, sample size, and verification rate
    verification_rate = n_verified / len(weighted_comps) if len(weighted_comps) > 0 else 0
    if cv < 0.05 and len(weighted_comps) >= 5 and verification_rate >= 0.8:
        confidence = 'high'
    elif cv < 0.10 and len(weighted_comps) >= 3 and verification_rate >= 0.6:
        confidence = 'medium'
    elif cv < 0.15 and verification_rate >= 0.4:
        confidence = 'low'
    else:
        confidence = 'very_low'

    # 90% confidence interval using t-distribution for small samples
    # With only 3-8 comparables, z=1.645 severely underestimates uncertainty.
    # t-distribution accounts for small-sample variance inflation.
    n = len(weighted_comps)
    df = max(1, n - 1)

    # t-values for 90% two-sided CI (alpha=0.10, alpha/2=0.05 each tail)
    # Precomputed for common df values; falls back to z=1.645 for large n
    T_VALUES_90 = {1: 6.314, 2: 2.920, 3: 2.353, 4: 2.132, 5: 2.015,
                   6: 1.943, 7: 1.895, 8: 1.860, 9: 1.833, 10: 1.812,
                   15: 1.753, 20: 1.725, 30: 1.697}
    t_val = T_VALUES_90.get(df, 1.645)
    # Interpolate for unlisted df values
    if df not in T_VALUES_90 and df < 30:
        lower_df = max(k for k in T_VALUES_90 if k <= df)
        upper_df = min(k for k in T_VALUES_90 if k >= df)
        if lower_df != upper_df:
            frac = (df - lower_df) / (upper_df - lower_df)
            t_val = T_VALUES_90[lower_df] + frac * (T_VALUES_90[upper_df] - T_VALUES_90[lower_df])

    margin = t_val * w_std

    # Apply a minimum floor: the range should never be narrower than a
    # percentage of the valuation, since even "perfect" comparables have
    # irreducible uncertainty from unmeasured features.
    # Calibrated against 1,800+ sold property backtest (2025-2026 Gold Coast data).
    # These floors produce a range that captures the expected accuracy at each
    # confidence level — not a statistical CI, but a practical "estimated range".
    min_margin_pct = {'high': 0.12, 'medium': 0.15, 'low': 0.20, 'very_low': 0.28}
    floor = w_mean * min_margin_pct.get(confidence, 0.18)
    margin = max(margin, floor)

    return {
        'reconciled_valuation': round(w_mean),
        'confidence': confidence,
        'range': {
            'low': round(w_mean - margin),
            'high': round(w_mean + margin),
        },
        'std_dev': round(w_std),
        'cv': round(cv, 3),
        'n_verified': n_verified,
        'n_total': n_total_override if n_total_override is not None else len(points),
    }


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


def resolve_numeric(val):
    """
    Resolve a value that may be a plain number or {value: N} object.
    Returns the numeric value or None if invalid.
    """
    if isinstance(val, (int, float)) and val > 0:
        return float(val)
    if isinstance(val, dict) and 'value' in val:
        v = val['value']
        if isinstance(v, (int, float)) and v > 0:
            return float(v)
    return None


def resolve_floor_area(doc):
    """
    Resolve floor area from a property document, checking all known nested paths.
    Used by both the NPUI extraction and the regression rate calculator so they
    never diverge.

    Priority: top-level → pvd.layout → floor_plan_analysis → ollama → enriched_data
    """
    pvd = doc.get('property_valuation_data', {})
    old_layout = pvd.get('layout', {}) if isinstance(pvd.get('layout'), dict) else {}
    fpa = doc.get('floor_plan_analysis', {}) if isinstance(doc.get('floor_plan_analysis'), dict) else {}
    ofpa = doc.get('ollama_floor_plan_analysis', {})
    ofpa_data = {}
    if isinstance(ofpa, dict):
        ofpa_data = ofpa.get('floor_plan_data', {}) if isinstance(ofpa.get('floor_plan_data'), dict) else {}
    enriched_data = doc.get('enriched_data', {}) if isinstance(doc.get('enriched_data'), dict) else {}

    ofpa_floor = resolve_numeric(ofpa_data.get('internal_floor_area', {}).get('value')
                                 if isinstance(ofpa_data.get('internal_floor_area'), dict)
                                 else ofpa_data.get('internal_floor_area'))

    return (resolve_numeric(doc.get('floor_area_sqm')) or
            resolve_numeric(old_layout.get('floor_area_sqm')) or
            resolve_numeric(fpa.get('internal_floor_area')) or
            ofpa_floor or
            resolve_numeric(enriched_data.get('floor_area_sqm')))


def resolve_land_size(doc):
    """
    Resolve land size from a property document, checking all known nested paths.
    Used by both the NPUI extraction and the regression rate calculator so they
    never diverge.

    Priority: top-level → pvd.layout → enriched_data → floor_plan_analysis → ollama
    """
    pvd = doc.get('property_valuation_data', {})
    old_layout = pvd.get('layout', {}) if isinstance(pvd.get('layout'), dict) else {}
    fpa = doc.get('floor_plan_analysis', {}) if isinstance(doc.get('floor_plan_analysis'), dict) else {}
    ofpa = doc.get('ollama_floor_plan_analysis', {})
    ofpa_data = {}
    if isinstance(ofpa, dict):
        ofpa_data = ofpa.get('floor_plan_data', {}) if isinstance(ofpa.get('floor_plan_data'), dict) else {}
    enriched_data = doc.get('enriched_data', {}) if isinstance(doc.get('enriched_data'), dict) else {}

    ofpa_land = resolve_numeric(ofpa_data.get('total_land_area', {}).get('value')
                                if isinstance(ofpa_data.get('total_land_area'), dict)
                                else ofpa_data.get('total_land_area'))
    fpa_land = resolve_numeric(fpa.get('total_land_area', {}).get('value')
                               if isinstance(fpa.get('total_land_area'), dict)
                               else fpa.get('total_land_area'))

    # Prefer cadastral lot_size_sqm over scraped land_size_sqm — the scraper
    # regex sometimes grabs room dimensions instead of actual land size
    return (resolve_numeric(doc.get('lot_size_sqm')) or
            resolve_numeric(doc.get('land_size_sqm')) or
            resolve_numeric(old_layout.get('land_size_sqm')) or
            resolve_numeric(enriched_data.get('lot_size_sqm')) or
            fpa_land or ofpa_land)


def parse_price(price_str):
    """
    Parse price string to number.
    Handles formats like: "$1,500,000", "1.5m", "1500000", etc.
    """
    if isinstance(price_str, (int, float)):
        return float(price_str) if price_str > 0 else None
    
    if not isinstance(price_str, str):
        return None
    
    # Remove common non-numeric characters
    cleaned = re.sub(r'[$,\s]', '', price_str)
    
    # Handle "1.4m" or "1.4M" style
    m_match = re.match(r'^(\d+\.?\d*)m$', cleaned, re.IGNORECASE)
    if m_match:
        return float(m_match.group(1)) * 1_000_000
    
    try:
        num = float(cleaned)
        return num if num > 0 else None
    except ValueError:
        return None


def infer_prestige_tier(doc):
    """Infer prestige tier from existing PVD fields.

    Uses GPT's explicit classification when available (it has visual context from photos).
    Falls back to heuristic inference only when GPT didn't provide a prestige_tier.

    Returns 'standard', 'elevated', 'prestige', or 'ultra_prestige'.
    """
    _TIER_RANK = {'standard': 0, 'elevated': 1, 'prestige': 2, 'ultra_prestige': 3}
    _RANK_TIER = {v: k for k, v in _TIER_RANK.items()}

    pvd = doc.get('property_valuation_data', {})
    if not pvd:
        return 'standard'

    # GPT explicit classification — trust it when available (it saw the photos)
    explicit = (pvd.get('property_metadata', {}).get('prestige_tier') or '').lower()
    if explicit in _TIER_RANK:
        return explicit

    # No GPT classification — fall back to heuristic inference
    gpt_tier = 'standard'  # baseline for max-with-gpt helper (no GPT data)

    # Heuristic inference from existing PVD fields.
    #
    # There are multiple PVD schemas in the database:
    #   Schema A (for-sale, from enrich_for_sale_batch.py):
    #     structural.number_of_stories, renovation.renovation_level,
    #     exterior.cladding_material, overall.unique_features, overall.market_appeal_score,
    #     interior.kitchen_quality_score, interior.bathroom_quality_score
    #   Schema B (sold, from Ollama/GPT enrichment):
    #     property_overview.number_of_stories, renovation.overall_renovation_level,
    #     condition_summary.overall_score, exterior.cladding_material,
    #     property_metadata.unique_features, kitchen.benchtop_material
    #
    # We use fallback chains to read from whichever schema is present.

    def _get(keys_with_fallbacks):
        """Try multiple (section, key) pairs, return first non-None value."""
        for section, key in keys_with_fallbacks:
            val = pvd.get(section, {}).get(key)
            if val is not None:
                return val
        return None

    # --- Extract fields with schema-agnostic fallbacks ---
    overall = _get([
        ('condition_summary', 'overall_score'),
        ('overall', 'market_appeal_score'),  # schema A uses this as closest proxy
    ]) or 0

    reno_level = _get([
        ('renovation', 'overall_renovation_level'),  # schema B
        ('renovation', 'renovation_level'),           # schema A
    ]) or ''

    stories = _get([
        ('property_overview', 'number_of_stories'),   # schema B
        ('structural', 'number_of_stories'),           # schema A
    ]) or 1

    style = _get([
        ('property_overview', 'architectural_style'),  # schema B
        ('structural', 'architectural_style'),          # schema A
    ]) or ''

    cladding = _get([
        ('exterior', 'cladding_material'),             # both schemas
    ]) or ''

    unique = _get([
        ('property_metadata', 'unique_features'),      # schema B
        ('overall', 'unique_features'),                 # schema A
    ]) or []

    # Kitchen quality indicators
    kitchen_stone = _get([('kitchen', 'benchtop_material')]) == 'stone'
    kitchen_premium = _get([('kitchen', 'appliances_quality')]) == 'premium'
    # Schema A: use kitchen_quality_score >= 8 as proxy for premium kitchen
    if not kitchen_stone and not kitchen_premium:
        k_qual = _get([('interior', 'kitchen_quality_score')]) or 0
        if k_qual >= 8:
            kitchen_premium = True

    # Condition sub-scores (schema B has these in condition_summary)
    int_score = _get([
        ('condition_summary', 'interior_score'),
        ('interior', 'overall_interior_condition_score'),
    ]) or 0
    ext_score = _get([
        ('condition_summary', 'exterior_score'),
        ('exterior', 'overall_exterior_condition_score'),
    ]) or 0
    k_score = _get([
        ('condition_summary', 'kitchen_score'),
        ('interior', 'kitchen_quality_score'),
    ]) or 0
    b_score = _get([
        ('condition_summary', 'bathroom_score'),
        ('interior', 'bathroom_quality_score'),
    ]) or 0

    # --- Hard requirements for prestige (inference path — no GPT data) ---
    # Must have high overall condition (8+)
    if overall < 8:
        return 'elevated' if overall >= 7 else 'standard'

    # Must be significantly renovated or new build
    if reno_level not in ('new_build', 'fully_renovated', 'cosmetically_updated'):
        return 'elevated'

    # Must be a detached house with 4+ bedrooms — excludes townhouses/duplexes
    building_type = _get([
        ('property_overview', 'building_type'),
        ('structural', 'building_type'),
    ]) or ''
    if building_type in ('townhouse', 'unit', 'apartment'):
        return 'elevated'
    bedrooms = doc.get('bedrooms', 0) or 0
    if bedrooms < 4:
        return 'elevated'

    # Must be two-storey — single-storey homes are almost never prestige tier
    if stories < 2:
        return 'elevated'

    # --- Scoring for prestige vs elevated (2-storey + high condition + reno'd) ---
    score = 0

    if reno_level == 'new_build':
        score += 3
    elif reno_level == 'fully_renovated':
        score += 2
    elif reno_level == 'cosmetically_updated' and overall >= 9:
        score += 1

    if style in ('contemporary', 'hamptons'):
        score += 2

    if cladding == 'stone':
        score += 3
    elif cladding in ('weatherboard', 'composite'):
        score += 2
    elif cladding == 'render':
        score += 1

    if kitchen_stone and kitchen_premium:
        score += 1

    if all(s >= 8 for s in [int_score, ext_score, k_score, b_score] if s):
        score += 1

    prestige_keywords = ['stone', 'void', 'architect', 'bespoke', 'custom', 'herringbone',
                         'statement', 'feature wall', 'raked ceiling', 'high ceiling',
                         'designer', 'resort', 'luxury', 'marble']
    unique_text = ' '.join(str(f).lower() for f in unique)
    prestige_feature_count = sum(1 for kw in prestige_keywords if kw in unique_text)
    score += min(prestige_feature_count, 3)

    if score >= 8:
        return 'ultra_prestige'
    elif score >= 5:
        return 'prestige'
    else:
        return 'elevated'


def is_waterfront(doc):
    """Detect if property is waterfront — unified check across all data sources"""
    if doc.get('is_waterfront') or doc.get('waterfront_premium_eligible'):
        return True

    # Primary signal: GPT-4 Vision photo analysis (most reliable — it actually saw water)
    pvd = doc.get('property_valuation_data', {})
    if pvd.get('outdoor', {}).get('water_views'):
        return True

    # Fallback: keyword search in listing description
    text = f"{doc.get('description', '')} {doc.get('agents_description', '')}".lower()
    return any(kw in text for kw in WATERFRONT_KEYWORDS)


def extract_npui_inputs(doc):
    """
    Extract NPUI inputs from a property document.
    Returns dict with 'inputs' and 'null_fields'.

    Supports two schemas for property_valuation_data:
      - Old schema: pvd.interior / pvd.exterior / pvd.layout (keys match NPUI names directly)
      - New schema: pvd.condition_summary / pvd.kitchen / pvd.bathrooms[] / pvd.living_areas[]
        (keys differ from NPUI names; mapped explicitly below)
    Both schemas are tried so older and newer documents both work.
    """
    pvd = doc.get('property_valuation_data', {})

    # Old schema sub-dicts (may be empty if new schema is used)
    old_interior = pvd.get('interior', {}) if isinstance(pvd.get('interior'), dict) else {}
    exterior = pvd.get('exterior', {}) if isinstance(pvd.get('exterior'), dict) else {}
    old_layout = pvd.get('layout', {}) if isinstance(pvd.get('layout'), dict) else {}
    outdoor = pvd.get('outdoor', {}) if isinstance(pvd.get('outdoor'), dict) else {}
    renovation = pvd.get('renovation', {}) if isinstance(pvd.get('renovation'), dict) else {}

    # New schema sub-dicts
    condition_summary = pvd.get('condition_summary', {}) if isinstance(pvd.get('condition_summary'), dict) else {}
    kitchen = pvd.get('kitchen', {}) if isinstance(pvd.get('kitchen'), dict) else {}
    bathrooms_list = pvd.get('bathrooms', []) if isinstance(pvd.get('bathrooms'), list) else []
    living_areas = pvd.get('living_areas', []) if isinstance(pvd.get('living_areas'), list) else []

    fpa = doc.get('floor_plan_analysis', {}) if isinstance(doc.get('floor_plan_analysis'), dict) else {}
    ofpa_data = {}
    ofpa = doc.get('ollama_floor_plan_analysis', {})
    if isinstance(ofpa, dict):
        ofpa_data = ofpa.get('floor_plan_data', {}) if isinstance(ofpa.get('floor_plan_data'), dict) else {}
    enriched_data = doc.get('enriched_data', {}) if isinstance(doc.get('enriched_data'), dict) else {}

    inputs = {}
    null_fields = []

    # ── Size fields (shared helpers ensure regression + NPUI stay in sync) ───
    land_size = resolve_land_size(doc)
    floor_area = resolve_floor_area(doc)

    # Sanity check: if floor_area > 500 and no land_size, it's likely the lot size
    if floor_area and floor_area > 500 and not land_size:
        land_size = floor_area
        floor_area = None

    if land_size:
        inputs['land_size_sqm'] = land_size
    else:
        null_fields.append('land_size_sqm')

    if floor_area:
        inputs['floor_area_sqm'] = floor_area
    else:
        null_fields.append('floor_area_sqm')

    # Bedrooms and bathrooms
    if doc.get('bedrooms') is not None:
        inputs['bedrooms'] = doc['bedrooms']
    else:
        null_fields.append('bedrooms')

    if doc.get('bathrooms') is not None:
        inputs['bathrooms'] = doc['bathrooms']
    else:
        null_fields.append('bathrooms')

    # ── Quality scores (0-10 scale) ──────────────────────────────────────────
    # Each field tries the old schema first, then the new schema field mapping.

    # interior.overall_interior_condition_score
    interior_condition = (old_interior.get('overall_interior_condition_score') or
                          condition_summary.get('interior_score'))

    # interior.kitchen_quality_score
    kitchen_quality = (old_interior.get('kitchen_quality_score') or
                       kitchen.get('quality_score'))

    # interior.bathroom_quality_score — average across all bathrooms in new schema
    bathroom_quality = old_interior.get('bathroom_quality_score')
    if bathroom_quality is None and bathrooms_list:
        scores = [b.get('quality_score') for b in bathrooms_list
                  if isinstance(b, dict) and isinstance(b.get('quality_score'), (int, float))]
        if scores:
            bathroom_quality = sum(scores) / len(scores)
    # Fallback: infer from renovation data when bathroom wasn't visible in photos
    if bathroom_quality is None:
        if renovation.get('bathrooms_renovated'):
            # Renovated bathrooms — infer conservatively from overall/interior condition
            ref_score = (condition_summary.get('overall_score') or
                         condition_summary.get('interior_score'))
            if ref_score and isinstance(ref_score, (int, float)):
                bathroom_quality = max(ref_score - 1, 5)  # 1 point below overall, floor at 5

    # exterior.overall_exterior_condition_score
    exterior_condition = (exterior.get('overall_exterior_condition_score') or
                          exterior.get('condition_score') or
                          condition_summary.get('exterior_score'))

    # layout.number_of_living_areas — count from living_areas array in new schema
    num_living_areas = (old_layout.get('number_of_living_areas') or
                        (len(living_areas) if living_areas else None))

    # outdoor.landscaping_quality_score — new schema uses 'landscaping_score'
    landscaping = (outdoor.get('landscaping_quality_score') or
                   outdoor.get('landscaping_score'))

    # interior.natural_light_score — aggregate from per-room data in new schema
    natural_light_score = old_interior.get('natural_light_score')
    if natural_light_score is None:
        _nl_map = {'excellent': 9, 'good': 7, 'average': 5, 'poor': 3}
        _nl_scores = []
        for _room_key in ('bedrooms', 'living_areas'):
            _rooms = pvd.get(_room_key, []) if isinstance(pvd.get(_room_key), list) else []
            for _room in _rooms:
                if isinstance(_room, dict):
                    _nl = (_room.get('natural_light') or '').lower()
                    if _nl in _nl_map:
                        _nl_scores.append(_nl_map[_nl])
        _k_nl = (kitchen.get('natural_light') or '').lower()
        if _k_nl in _nl_map:
            _nl_scores.append(_nl_map[_k_nl])
        if _nl_scores:
            natural_light_score = round(sum(_nl_scores) / len(_nl_scores), 1)

    # layout.layout_efficiency_score — derive from floor plan + living area data
    layout_eff = old_layout.get('layout_efficiency_score')
    if layout_eff is None:
        _eff = 5  # baseline for any home with a floor plan
        _meta = pvd.get('property_metadata', {}) if isinstance(pvd.get('property_metadata'), dict) else {}
        # Open plan living bonus
        for _la in living_areas:
            if isinstance(_la, dict) and _la.get('open_plan_with_kitchen'):
                _eff += 2
                break
        # Multiple living areas
        if len(living_areas) >= 2:
            _eff += 1
        # Study or home office
        if _meta.get('has_study') or _meta.get('has_home_office'):
            _eff += 1
        # Multi-level (better separation of living/sleeping zones)
        _fpa = doc.get('floor_plan_analysis', {}) if isinstance(doc.get('floor_plan_analysis'), dict) else {}
        _levels = _fpa.get('levels', {}) if isinstance(_fpa.get('levels'), dict) else {}
        if (_levels.get('total_levels') or 1) >= 2:
            _eff += 1
        layout_eff = min(_eff, 10)

    # outdoor.fence_condition_score — derive from fence_type + exterior condition
    fence_score = outdoor.get('fence_condition_score')
    if fence_score is None:
        _fence_type = exterior.get('fence_type')
        if _fence_type and _fence_type != 'none':
            _ext_cond = (exterior.get('condition_score') or
                         condition_summary.get('exterior_score'))
            if _ext_cond and isinstance(_ext_cond, (int, float)):
                # Mixed fences slightly penalised vs uniform; pool fences neutral
                _discount = 1 if _fence_type == 'mixed' else 0
                fence_score = max(int(_ext_cond) - _discount, 3)

    quality_fields = {
        'interior.overall_interior_condition_score': interior_condition,
        'interior.kitchen_quality_score': kitchen_quality,
        'interior.bathroom_quality_score': bathroom_quality,
        'exterior.overall_exterior_condition_score': exterior_condition,
        'renovation.modern_features_score': renovation.get('modern_features_score'),
        'layout.layout_efficiency_score': layout_eff,
        'interior.natural_light_score': natural_light_score,
        'layout.number_of_living_areas': num_living_areas,
        'outdoor.outdoor_entertainment_score': outdoor.get('outdoor_entertainment_score'),
        'outdoor.landscaping_quality_score': landscaping,
        'outdoor.fence_condition_score': fence_score,
    }

    for key, val in quality_fields.items():
        if val is not None and isinstance(val, (int, float)):
            inputs[key] = val
        else:
            null_fields.append(key)

    # Car spaces
    car_spaces = doc.get('car_spaces') or doc.get('carspaces') or doc.get('parking')
    if car_spaces is not None:
        inputs['carspaces'] = car_spaces
    else:
        null_fields.append('carspaces')

    return {'inputs': inputs, 'null_fields': null_fields}


def compute_cohort_stats(all_inputs):
    """
    Compute min/max statistics for each feature across the cohort.
    Used for normalization.
    """
    stats = {}
    
    for inputs in all_inputs:
        for key, val in inputs.items():
            if not isinstance(val, (int, float)):
                continue
            if key not in stats:
                stats[key] = {'min': val, 'max': val, 'values': []}
            stats[key]['min'] = min(stats[key]['min'], val)
            stats[key]['max'] = max(stats[key]['max'], val)
            stats[key]['values'].append(val)
    
    return stats


def compute_raw_utility(inputs, cohort_stats):
    """
    Compute raw utility score for a single property.
    Returns a value between 0 and 1.
    """
    weighted_sum = 0
    total_weight = 0
    
    for feature, weight in NPUI_WEIGHTS.items():
        val = inputs.get(feature)
        if val is None:
            continue
        
        stats = cohort_stats.get(feature)
        if not stats or stats['max'] == stats['min']:
            continue
        
        # Normalize to 0-1 range
        if '.' in feature and 'number_of_living_areas' not in feature:
            # Quality scores are on 0-10 scale
            normalized = max(0, min(1, val / 10))
        else:
            normalized = max(0, min(1, (val - stats['min']) / (stats['max'] - stats['min'])))
        
        weighted_sum += normalized * weight
        total_weight += weight
    
    return weighted_sum / total_weight if total_weight > 0 else 0.5


def compute_npui_for_cohort(all_inputs, cohort_stats):
    """
    Compute NPUI (percentile ranks) for all properties in the cohort.
    Returns dict with 'raw_scores' and 'npui_values'.
    """
    # Step 1: Compute raw utility for each
    raw_scores = [compute_raw_utility(inputs, cohort_stats) for inputs in all_inputs]
    
    # Step 2: Convert to percentile ranks (0-1)
    sorted_scores = sorted(raw_scores)
    npui_values = []
    
    for score in raw_scores:
        rank = sum(1 for s in sorted_scores if s <= score)
        npui = max(0, min(1, (rank - 0.5) / len(sorted_scores)))
        npui_values.append(npui)
    
    return {'raw_scores': raw_scores, 'npui_values': npui_values}


def extract_images(doc, max_images=5):
    """Extract property images from document"""
    # Priority 1: photo_tour_order
    photo_tour = doc.get('photo_tour_order', [])
    if photo_tour:
        urls = []
        for item in photo_tour:
            if isinstance(item, dict):
                url = item.get('url')
            elif isinstance(item, str):
                url = item
            else:
                url = None
            if url:
                urls.append(url)
        if urls:
            return urls[:max_images]
    
    # Priority 2: property_images
    prop_images = doc.get('property_images', [])
    if prop_images:
        urls = []
        for img in prop_images:
            if isinstance(img, dict):
                url = img.get('url') or img.get('image_url')
            elif isinstance(img, str):
                url = img
            else:
                url = None
            if url:
                urls.append(url)
        if urls:
            return urls[:max_images]
    
    # Priority 3: image_analysis
    image_analysis = doc.get('image_analysis', [])
    if image_analysis:
        sorted_imgs = sorted(
            [img for img in image_analysis if img and img.get('url')],
            key=lambda x: x.get('image_index', 999)
        )
        return [img['url'] for img in sorted_imgs[:max_images]]
    
    return []


def basic_features(doc):
    """Extract basic features for tooltips"""
    pvd = doc.get('property_valuation_data', {})
    layout = pvd.get('layout', {})
    fpa = doc.get('floor_plan_analysis', {})
    enriched = doc.get('enriched_data', {})

    floor_area = (resolve_numeric(doc.get('floor_area_sqm')) or
                  resolve_numeric(layout.get('floor_area_sqm')) or
                  resolve_numeric(fpa.get('internal_floor_area')) or
                  resolve_numeric(enriched.get('floor_area_sqm')))

    fpa_land = resolve_numeric(fpa.get('total_land_area', {}).get('value')
                               if isinstance(fpa.get('total_land_area'), dict)
                               else fpa.get('total_land_area'))
    # Prefer cadastral lot_size_sqm over scraped land_size_sqm
    land_size = (resolve_numeric(doc.get('lot_size_sqm')) or
                 resolve_numeric(doc.get('land_size_sqm')) or
                 resolve_numeric(layout.get('land_size_sqm')) or
                 resolve_numeric(enriched.get('lot_size_sqm')) or
                 fpa_land)
    
    # Same sanity check
    if floor_area and floor_area > 500 and not land_size:
        land_size = floor_area
        floor_area = None
    
    # Pool and storey count from GPT photo analysis
    outdoor = pvd.get('outdoor', {})
    overview = pvd.get('property_overview', {})
    pool_present = outdoor.get('pool_present', False) if outdoor else False
    number_of_stories = overview.get('number_of_stories') if overview else None
    # Fallback storey count from floor plan analysis
    if not number_of_stories:
        fpa_levels = fpa.get('levels', {})
        if isinstance(fpa_levels, dict):
            number_of_stories = fpa_levels.get('total_levels')

    # Renovation status from GPT analysis
    reno = pvd.get('renovation', {})
    renovation_level_raw = reno.get('overall_renovation_level')
    renovation_level = RENOVATION_LEVEL_MAP.get(renovation_level_raw, 3)  # default: cosmetically_updated

    # Water views
    water_views = bool(outdoor.get('water_views', False)) if outdoor else False

    # Cladding material
    exterior = pvd.get('exterior', {})
    cladding_raw = exterior.get('cladding_material') if exterior else None
    cladding_level = CLADDING_MATERIAL_MAP.get(cladding_raw, 2)  # default: brick

    # Kitchen quality score
    kitchen = pvd.get('kitchen', {})
    kitchen_score = kitchen.get('quality_score') if kitchen else None

    # Air conditioning type
    metadata = pvd.get('property_metadata', {})
    ac_type = metadata.get('air_conditioning', '') if metadata else ''
    ac_ducted = ac_type == 'ducted'

    return {
        'bedrooms': doc.get('bedrooms'),
        'bathrooms': doc.get('bathrooms'),
        'car_spaces': doc.get('car_spaces') or doc.get('carspaces') or doc.get('parking'),
        'floor_area_sqm': floor_area,
        'land_size_sqm': land_size,
        'pool_present': bool(pool_present),
        'number_of_stories': number_of_stories,
        'renovation_level': renovation_level,
        'renovation_level_raw': renovation_level_raw,
        'water_views': water_views,
        'cladding_level': cladding_level,
        'cladding_raw': cladding_raw,
        'kitchen_score': kitchen_score,
        'ac_ducted': ac_ducted,
        'renovation_quality_score': compute_renovation_quality_score(doc),
    }


def check_coverage(inputs, null_fields):
    """Check data coverage quality"""
    core_fields = ['bedrooms', 'bathrooms', 'land_size_sqm', 'floor_area_sqm', 'carspaces']
    core_present = sum(1 for f in core_fields if f in inputs)
    core_coverage = core_present / len(core_fields)
    
    total_fields = len(inputs) + len(null_fields)
    overall_coverage = len(inputs) / total_fields if total_fields > 0 else 0
    
    has_land_and_floor = 'land_size_sqm' in inputs and 'floor_area_sqm' in inputs
    
    return {
        'core_coverage': core_coverage,
        'overall_coverage': overall_coverage,
        'has_land_and_floor': has_land_and_floor
    }


def compute_value_gap(subject_price, subject_npui, chart_points):
    """
    Compute value gap using linear regression.
    Returns dict with 'value_gap_pct', 'positioning', 'slope', and 'intercept'.
    Slope/intercept are exposed so Gap 1 can compute independent valuations.
    """
    if len(chart_points) < 5:
        return {'value_gap_pct': None, 'positioning': None, 'slope': None, 'intercept': None}
    
    xs = [p['npui'] for p in chart_points]
    ys = [p['price'] for p in chart_points]
    
    n = len(xs)
    sum_x = sum(xs)
    sum_y = sum(ys)
    sum_xx = sum(x * x for x in xs)
    sum_xy = sum(x * y for x, y in zip(xs, ys))
    
    denom = n * sum_xx - sum_x * sum_x
    if denom == 0:
        return {'value_gap_pct': None, 'positioning': None, 'slope': None, 'intercept': None}
    
    slope = (n * sum_xy - sum_x * sum_y) / denom
    intercept = (sum_y - slope * sum_x) / n
    
    expected_price = slope * subject_npui + intercept
    if expected_price <= 0:
        return {'value_gap_pct': None, 'positioning': None, 'slope': slope, 'intercept': intercept}
    
    gap = (expected_price - subject_price) / expected_price
    
    # Determine positioning
    if gap <= -0.08:
        positioning = 'underpriced'
    elif gap <= -0.03:
        positioning = 'good_value'
    elif gap < 0.03:
        positioning = 'fair'
    elif gap < 0.08:
        positioning = 'slightly_overpriced'
    else:
        positioning = 'overpriced'
    
    return {'value_gap_pct': gap, 'positioning': positioning, 'slope': slope, 'intercept': intercept}


def precompute_property_valuation(db, subject_doc, listings_coll, sold_by_suburb,
                                   gc_coord_lookup=None, gc_timeline_lookup=None,
                                   median_cache=None, street_premium_cache=None):
    """
    Pre-compute valuation data for a single property.
    Returns valuation_data dict or None if insufficient data.

    sold_by_suburb: dict keyed by lowercase_underscore suburb name containing
    merged sold records from Gold_Coast_Recently_Sold +
    Target_Market_Sold_Last_12_Months. Built once by _load_sold_comparables().
    gc_coord_lookup: {suburb_key: {"street_no street_name": (lat, lng), ...}}
    gc_timeline_lookup: {suburb_key: {"street_no street_name": year, ...}}
    """
    subject_id = str(subject_doc['_id'])
    suburb = subject_doc.get('suburb', '')
    prop_type = subject_doc.get('property_type', 'House')
    subject_is_waterfront = is_waterfront(subject_doc)

    # Find comparable listings from the same suburb collection
    col_name = subject_doc.get('_collection') or (suburb.lower().replace(' ', '_') if suburb else None)
    comps_query = {
        '_id': {'$ne': subject_doc['_id']},
        'property_type': prop_type,
    }
    if col_name:
        comparable_docs = list(db[col_name].find(comps_query).limit(30))
    else:
        comparable_docs = []

    # Find recent sold comparables from merged source (Gold_Coast_Recently_Sold +
    # Target_Market_Sold_Last_12_Months). Filter to matching property_type only;
    # the property_valuation_data requirement is dropped because Target_Market docs
    # don't have GPT enrichment but do have price, beds, land — enough for regression.
    # Hard cutoff: exclude sales older than 12 months entirely.
    suburb_key = col_name or (suburb.lower().replace(' ', '_') if suburb else '')

    # Resolve subject property coordinates and build year
    _gc_coords = gc_coord_lookup or {}
    _gc_timelines = gc_timeline_lookup or {}
    subject_lat, subject_lon = _resolve_coordinates(subject_doc, _gc_coords, suburb_key)
    subject_build_year = _resolve_build_year(subject_doc, _gc_timelines, suburb_key)
    subject_beach_km = resolve_beach_distance(subject_doc, subject_lat, subject_lon)

    all_suburb_sold = sold_by_suburb.get(suburb_key, [])
    twelve_months_ago_ms = (time.time() - 365 * 24 * 3600) * 1000

    def _parse_sale_date_ms(doc):
        """Parse sale_date from a sold record. Returns epoch ms or None."""
        raw = doc.get('sale_date') or doc.get('sold_date')
        if isinstance(raw, (int, float)):
            return float(raw)
        if isinstance(raw, str) and raw:
            try:
                return datetime.fromisoformat(raw[:10]).timestamp() * 1000
            except (ValueError, TypeError):
                return None
        return None

    def _is_within_12_months(doc):
        """Exclude sales older than 12 months. Keep sales with no parseable date."""
        ms = _parse_sale_date_ms(doc)
        if ms is not None and ms < twelve_months_ago_ms:
            return False
        return True

    recent_sales_docs = [
        s for s in all_suburb_sold
        if s.get('property_type', '') == prop_type
        and (parse_price(s.get('sale_price') or s.get('sold_price')) or 0) > 0
        and _is_within_12_months(s)
    ][:60]  # cap at 60; OLS regression needs >= 15, more improves accuracy

    # Parse subject listing price early — needed by in_cohort_sold() closure below
    subject_listing_price = parse_price(subject_doc.get('price'))

    # Detect if subject is a unit/apartment (X/Y address format) vs standalone house
    subject_addr = subject_doc.get('address', '')
    subject_is_unit = bool(re.match(r'^\d+/\d+', subject_addr.strip()))

    # Detect if subject is acreage (land > 5,000 sqm) — check multiple fields
    subject_land = resolve_land_size(subject_doc) or resolve_numeric(subject_doc.get('lot_size_sqm'))
    subject_is_acreage = subject_land is not None and subject_land > 5000

    # Detect prestige tier — uses explicit GPT flag if available, otherwise infers from PVD scores
    subject_prestige = infer_prestige_tier(subject_doc)
    subject_is_prestige = subject_prestige in ('prestige', 'ultra_prestige')

    # Filter by waterfront status, bedroom band, dwelling type, and prestige tier
    subject_beds = subject_doc.get('bedrooms')
    bed_band = [max(1, subject_beds - 1), subject_beds + 1] if subject_beds is not None else None

    def in_cohort(doc):
        # Waterfront filter
        if subject_is_waterfront and not is_waterfront(doc):
            return False
        if not subject_is_waterfront and is_waterfront(doc):
            return False

        # Prestige tier: soft filter — prestige homes prefer prestige comps but
        # don't hard-exclude non-prestige (cohort too small for hard split).
        # Instead, the weighting function penalises mismatched tiers.

        # Bedroom band
        if bed_band:
            beds = doc.get('bedrooms')
            if beds is None or beds < bed_band[0] or beds > bed_band[1]:
                return False

        # Dwelling type filter: don't mix unit-numbered addresses with standalone houses
        comp_addr = doc.get('address', '')
        comp_is_unit = bool(re.match(r'^\d+/\d+', comp_addr.strip()))
        if subject_is_unit != comp_is_unit:
            return False

        # Acreage filter: don't mix acreage (>5,000 sqm) with suburban lots
        comp_land = resolve_land_size(doc) or resolve_numeric(doc.get('lot_size_sqm'))
        comp_is_acreage = comp_land is not None and comp_land > 5000
        if subject_is_acreage != comp_is_acreage:
            return False

        return True

    def in_cohort_sold(doc):
        """Cohort filter for sold comparables — adds price proximity check."""
        if not in_cohort(doc):
            return False
        # Price proximity: comp sale price must be within ±40% of subject listing price.
        # Backtest shows this reduces MAE from 12.7% → 11.7% and P90 from 27.4% → 24.5%
        # by preventing structurally dissimilar comps from distorting adjustments.
        if subject_listing_price:
            comp_price = parse_price(doc.get('sale_price') or doc.get('sold_price')
                                     or doc.get('last_sold_price'))
            if comp_price:
                if comp_price < subject_listing_price * 0.60 or comp_price > subject_listing_price * 1.40:
                    return False
        return True

    filtered_comps = [c for c in comparable_docs if in_cohort(c)]
    filtered_sales = [s for s in recent_sales_docs if in_cohort_sold(s)]

    # Check for exclusion criteria — return "not available" with reason
    exclusion_reason = None
    # Exclude high-value properties ($2.5M+) — backtest shows MAE of 28-39%
    # above this threshold due to insufficient prestige comparables.
    # (subject_listing_price already parsed above for in_cohort_sold closure)
    subject_floor_area = resolve_floor_area(subject_doc)
    subject_has_pvd = bool(subject_doc.get('property_valuation_data'))
    if subject_listing_price and subject_listing_price >= 2500000:
        exclusion_reason = 'price_above_threshold'
    elif subject_is_acreage:
        exclusion_reason = 'acreage'
    elif subject_is_unit and prop_type == 'House':
        exclusion_reason = 'misclassified_dwelling'
    elif not subject_floor_area:
        # Floor area is the single biggest price driver — without it,
        # the model can't adjust for size differences between comps.
        exclusion_reason = 'missing_floor_area'
    elif not subject_land and not subject_is_unit:
        # Land size is critical for houses (units typically don't have lot size)
        exclusion_reason = 'missing_land_size'
    elif len(filtered_sales) < 3 and len(filtered_comps) < 2:
        exclusion_reason = 'insufficient_comparables'

    if exclusion_reason:
        return {
            'computed_at': datetime.utcnow(),
            'confidence': {
                'reconciled_valuation': None,
                'confidence': 'not_available',
                'range': None,
                'exclusion_reason': exclusion_reason,
                'n_verified': 0,
                'n_total': len(filtered_comps) + len(filtered_sales),
            },
            'summary': {
                'insufficient_data': True,
                'exclusion_reason': exclusion_reason,
                'n_comps': len(filtered_comps) + len(filtered_sales),
                'n_current_listings': len(filtered_comps),
                'n_recent_sales': len(filtered_sales),
            },
            'metadata': {
                'generated_at': int(datetime.utcnow().timestamp() * 1000),
                'parameters': {'address': subject_doc.get('address')},
                'gaps_version': 3,
            },
        }

    # Compute NPUI for all properties
    all_docs = [subject_doc] + filtered_comps + filtered_sales
    all_inputs_list = [extract_npui_inputs(d) for d in all_docs]
    all_inputs_only = [x['inputs'] for x in all_inputs_list]
    
    cohort_stats = compute_cohort_stats(all_inputs_only)
    npui_result = compute_npui_for_cohort(all_inputs_only, cohort_stats)
    
    # Build breakdown map
    breakdown_map = {}
    for idx, doc in enumerate(all_docs):
        doc_id = str(doc['_id'])
        breakdown_map[doc_id] = {
            'npui': npui_result['npui_values'][idx],
            'raw_utility': npui_result['raw_scores'][idx],
            'inputs': all_inputs_list[idx]['inputs'],
            'null_fields': all_inputs_list[idx]['null_fields'],
        }
    
    # Derive subject effective price
    subject_price = parse_price(subject_doc.get('price'))
    
    if not subject_price:
        # Try valuation
        iter_val = subject_doc.get('iteration_08_valuation', {})
        if isinstance(iter_val.get('predicted_value'), (int, float)):
            subject_price = iter_val['predicted_value']
    
    if not subject_price:
        # Estimate from recent sales median
        sale_prices = [parse_price(s.get('sale_price') or s.get('sold_price') or s.get('last_sold_price'))
                      for s in filtered_sales]
        sale_prices = [p for p in sale_prices if p]
        if sale_prices:
            sale_prices.sort()
            mid = len(sale_prices) // 2
            subject_price = sale_prices[mid] if len(sale_prices) % 2 == 1 else (sale_prices[mid-1] + sale_prices[mid]) / 2
    
    if not subject_price:
        return None  # Can't compute without price
    
    # Build chart points
    subject_npui = breakdown_map[subject_id]['npui']
    chart_points = []
    
    # Subject point
    chart_points.append({
        'type': 'subject',
        'series': 'current_listing',
        'price': subject_price,
        'npui': subject_npui,
        'label': subject_doc.get('address', 'Subject'),
        'id': subject_id,
    })
    
    # Comparable listings
    comparable_points = []
    for c in filtered_comps:
        cid = str(c['_id'])
        price = parse_price(c.get('price'))
        if not price:
            continue

        bd = breakdown_map[cid]
        cov = check_coverage(bd['inputs'], bd['null_fields'])
        if cov['core_coverage'] < 0.5 or cov['overall_coverage'] < 0.3 or not cov['has_land_and_floor']:
            continue

        npui = bd['npui']

        # Resolve distance and build year for this comparable
        c_lat, c_lon = _resolve_coordinates(c, _gc_coords, suburb_key)
        c_dist_km = None
        if subject_lat and subject_lon and c_lat and c_lon:
            c_dist_km = round(haversine_distance(subject_lat, subject_lon, c_lat, c_lon), 2)
        c_build_year = _resolve_build_year(c, _gc_timelines, suburb_key)

        comp_basic = basic_features(c)
        comp_basic['approximate_build_year'] = c_build_year
        comp_basic['beach_distance_km'] = resolve_beach_distance(c, c_lat, c_lon)

        comparable_points.append({
            'id': cid,
            'address': c.get('address', 'Comparable'),
            'price': price,
            'valuation_price': None,
            'utility_index': npui,
            'distance_km': c_dist_km,
            'series': 'current_listing',
            'features': {
                'basic': comp_basic,
                'npui_breakdown': bd,
            },
            'images': extract_images(c),
            '_source_doc': c,
        })
        
        chart_points.append({
            'type': 'comp',
            'series': 'current_listing',
            'price': price,
            'npui': npui,
            'label': c.get('address', 'Comparable'),
            'id': cid,
        })
    
    # Recent sales
    recent_points = []
    for s in filtered_sales:
        sid = str(s['_id'])
        price = parse_price(s.get('sale_price') or s.get('sold_price') or s.get('last_sold_price'))
        if not price:
            continue

        bd = breakdown_map[sid]
        cov = check_coverage(bd['inputs'], bd['null_fields'])
        if cov['core_coverage'] < 0.5 or cov['overall_coverage'] < 0.2 or not cov['has_land_and_floor']:
            continue

        npui = bd['npui']

        # Parse sale date
        sale_date_ms = None
        sale_date_raw = s.get('sale_date') or s.get('sold_date')
        if isinstance(sale_date_raw, (int, float)):
            sale_date_ms = int(sale_date_raw)
        elif isinstance(sale_date_raw, str) and sale_date_raw:
            try:
                sale_date_ms = int(datetime.fromisoformat(sale_date_raw[:10]).timestamp() * 1000)
            except:
                pass

        # Time-adjust sales older than 6 months using suburb median price growth
        time_adj_meta = None
        effective_price = price
        if sale_date_ms:
            months_ago = (time.time() * 1000 - sale_date_ms) / (30 * 24 * 3600 * 1000)
            if months_ago > 6:
                effective_price, time_adj_meta = time_adjust_sale_price(
                    price, sale_date_ms, suburb, prop_type, db)

        # Resolve distance and build year for this sale
        s_lat, s_lon = _resolve_coordinates(s, _gc_coords, suburb_key)
        s_dist_km = None
        if subject_lat and subject_lon and s_lat and s_lon:
            s_dist_km = round(haversine_distance(subject_lat, subject_lon, s_lat, s_lon), 2)
        s_build_year = _resolve_build_year(s, _gc_timelines, suburb_key)

        sale_basic = basic_features(s)
        sale_basic['approximate_build_year'] = s_build_year
        sale_basic['beach_distance_km'] = resolve_beach_distance(s, s_lat, s_lon)

        recent_points.append({
            'id': sid,
            'address': s.get('address') or s.get('street_address') or 'Recent sale',
            'price': effective_price,
            'original_sale_price': price if time_adj_meta and time_adj_meta.get('applied') else None,
            'time_adjustment': time_adj_meta,
            'valuation_price': None,
            'utility_index': npui,
            'distance_km': s_dist_km,
            'sale_date': sale_date_ms,
            'series': 'recent_sale',
            'features': {
                'basic': sale_basic,
                'npui_breakdown': bd,
            },
            'images': extract_images(s),
            '_source_doc': s,
        })

        chart_points.append({
            'type': 'recent_sale',
            'series': 'recent_sale',
            'price': effective_price,
            'npui': npui,
            'label': s.get('address') or s.get('street_address') or 'Recent sale',
            'id': sid,
            'sale_date': sale_date_ms,
        })
    
    # Compute value gap (now returns slope/intercept for Gap 1)
    value_gap_result = compute_value_gap(subject_price, subject_npui, chart_points)
    insufficient_data = len(chart_points) < 5
    reg_slope = value_gap_result.get('slope')
    reg_intercept = value_gap_result.get('intercept')

    # ─── GAP 2: Get adjustment rates (regression or fallback) ──────────────
    adj_rates, adj_source = get_adjustment_rates(suburb, recent_sales_docs, _gc_timelines, suburb_key)

    # Extract subject features for adjustment calculations
    subject_bd = breakdown_map[subject_id]
    subject_basic = basic_features(subject_doc)
    subject_features = {
        'land_size_sqm': subject_bd['inputs'].get('land_size_sqm') or subject_basic.get('land_size_sqm'),
        'floor_area_sqm': subject_bd['inputs'].get('floor_area_sqm') or subject_basic.get('floor_area_sqm'),
        'bedrooms': subject_doc.get('bedrooms', 0),
        'bathrooms': subject_doc.get('bathrooms', 0),
        'car_spaces': subject_doc.get('car_spaces') or subject_doc.get('carspaces') or 0,
        'condition_score': subject_bd['inputs'].get(
            'interior.overall_interior_condition_score', 5),
        'pool_present': subject_basic.get('pool_present', False),
        'number_of_stories': subject_basic.get('number_of_stories'),
        'renovation_level': subject_basic.get('renovation_level', 3),
        'water_views': subject_basic.get('water_views', False),
        'cladding_level': subject_basic.get('cladding_level', 2),
        'kitchen_score': subject_basic.get('kitchen_score'),
        'ac_ducted': subject_basic.get('ac_ducted', False),
        'approximate_build_year': subject_build_year,
        'beach_distance_km': subject_beach_km,
        'renovation_quality_score': subject_basic.get('renovation_quality_score'),
        'street_premium_pct': (street_premium_cache or {}).get(
            (suburb_key, _extract_street_name(subject_doc)), (None,))[0],
        'micro_location_premium_pct': compute_micro_location_premium(
            subject_lat, subject_lon, suburb_key,
            sold_by_suburb.get(suburb_key, []),
            median_cache or {})[0] if subject_lat and subject_lon else None,
    }

    # ─── Pass 1: Compute adjustments and narratives for all comps ──────────
    all_enriched_points = []

    for point_list in [comparable_points, recent_points]:
        for pt in point_list:
            comp_price = pt['price']
            comp_npui = pt['utility_index']
            comp_bd = pt.get('features', {}).get('npui_breakdown') or {}
            comp_bd_inputs = comp_bd.get('inputs') or {}
            comp_bd_null_fields = comp_bd.get('null_fields') or []
            comp_cov = check_coverage(comp_bd_inputs, comp_bd_null_fields)

            # Gap 1: Independent valuation (NPUI regression — kept for scatter plot display)
            indep_val = compute_independent_valuation(comp_npui, reg_slope, reg_intercept)
            pt['independent_valuation'] = indep_val

            # Gap 2: Feature-by-feature adjustments
            basic = pt.get('features', {}).get('basic') or {}
            comp_features = {
                'land_size_sqm': comp_bd_inputs.get('land_size_sqm') or basic.get('land_size_sqm'),
                'floor_area_sqm': comp_bd_inputs.get('floor_area_sqm') or basic.get('floor_area_sqm'),
                'bedrooms': basic.get('bedrooms') or 0,
                'bathrooms': basic.get('bathrooms') or 0,
                'car_spaces': basic.get('car_spaces') or 0,
                'condition_score': comp_bd_inputs.get(
                    'interior.overall_interior_condition_score', 5),
                'pool_present': basic.get('pool_present', False),
                'number_of_stories': basic.get('number_of_stories'),
                'renovation_level': basic.get('renovation_level', 3),
                'water_views': basic.get('water_views', False),
                'cladding_level': basic.get('cladding_level', 2),
                'kitchen_score': basic.get('kitchen_score'),
                'ac_ducted': basic.get('ac_ducted', False),
                'approximate_build_year': basic.get('approximate_build_year'),
                'beach_distance_km': basic.get('beach_distance_km'),
                'renovation_quality_score': basic.get('renovation_quality_score'),
                'street_premium_pct': (street_premium_cache or {}).get(
                    (suburb_key, _extract_street_name(pt.get('_source_doc') or pt)), (None,))[0],
                'micro_location_premium_pct': _resolve_comp_micro_premium(
                    pt, suburb_key, sold_by_suburb, median_cache, _gc_coords),
            }
            adj_result = calculate_adjustments(subject_features, comp_features, comp_price, adj_rates)
            pt['adjustment_result'] = adj_result

            # Gap 4: Narrative (can run before verification)
            pt['narrative'] = generate_adjustment_narrative(
                pt.get('address', 'Comparable'), comp_price, adj_result)

            # Store coverage for verification pass
            pt['_data_quality_pct'] = comp_cov['overall_coverage']

            all_enriched_points.append(pt)

    # ─── Pass 2: Verification (batch — needs all adjusted prices) ────────
    all_adjusted_prices = [
        pt['adjustment_result']['adjusted_price']
        for pt in all_enriched_points
        if pt.get('adjustment_result', {}).get('adjusted_price')
    ]

    for pt in all_enriched_points:
        adjusted_price = pt.get('adjustment_result', {}).get('adjusted_price')
        verification = verify_comparable(
            pt['price'], adjusted_price, pt.get('independent_valuation'),
            all_adjusted_prices, pt.get('_data_quality_pct', 0.5))
        pt['verification'] = verification

    # ─── Pass 3: Weights (needs verification results) ────────────────────
    for pt in all_enriched_points:
        pt['weight'] = calculate_weight(pt)

    # ─── Pass 3.5: Prestige tier weight adjustment ──────────────────────
    # Prestige properties are a fundamentally different market segment.
    # The NPUI adjustment pipeline systematically undervalues prestige homes because
    # the regression line and adjustment rates are fitted on the full cohort (~$1.5-2M avg).
    # Fix: for prestige subjects, use raw sale prices of prestige comps instead of
    # adjusted prices, and near-zero weight for non-prestige comps.
    for pt in all_enriched_points:
        comp_doc = pt.get('_source_doc', {})
        comp_tier = infer_prestige_tier(comp_doc) if comp_doc else 'standard'
        comp_is_p = comp_tier in ('prestige', 'ultra_prestige')
        if subject_is_prestige and comp_is_p:
            # Override adjusted_price with raw sale price — the adjustment pipeline
            # distorts prestige values because rates are derived from standard homes
            pt['adjustment_result']['adjusted_price'] = pt['price']
            pt['weight']['raw_weight'] *= 3.0
        elif subject_is_prestige and not comp_is_p:
            pt['weight']['raw_weight'] *= 0.05  # near-zero
        elif not subject_is_prestige and comp_is_p:
            pt['weight']['raw_weight'] *= 0.15

    # ─── Quality comp selection: keep only high-quality comps for valuation ──
    select_quality_comps(all_enriched_points, min_comps=3, target_comps=8)
    included_points = [p for p in all_enriched_points if p.get('included_in_valuation', False)]

    # Normalize weights across included points only (weights sum to 1.0)
    normalize_weights(included_points)

    # Set excluded points to zero normalized weight (for transparency in UI)
    for pt in all_enriched_points:
        if not pt.get('included_in_valuation', False):
            pt.setdefault('weight', {})['normalized'] = 0.0

    # ─── GAP 6: Confidence interval from quality-selected values ──────────
    confidence_result = calculate_confidence(
        included_points, n_total_override=len(all_enriched_points))

    # Build valuation breakdown
    sale_prices_for_estimate = [p['price'] for p in recent_points
                                if abs(p['utility_index'] - subject_npui) <= 0.15]
    sale_prices_for_estimate.sort()
    
    npui_median = None
    npui_average = None
    if sale_prices_for_estimate:
        mid = len(sale_prices_for_estimate) // 2
        npui_median = (sale_prices_for_estimate[mid] if len(sale_prices_for_estimate) % 2 == 1
                      else (sale_prices_for_estimate[mid-1] + sale_prices_for_estimate[mid]) / 2)
        npui_average = sum(sale_prices_for_estimate) / len(sale_prices_for_estimate)
    
    model_valuation = None
    iter_val = subject_doc.get('iteration_08_valuation', {})
    if isinstance(iter_val.get('predicted_value'), (int, float)):
        model_valuation = iter_val['predicted_value']
    
    blended_valuation = None
    if model_valuation and npui_median:
        blended_valuation = (model_valuation + npui_median) / 2
    elif npui_median:
        blended_valuation = npui_median
    elif model_valuation:
        blended_valuation = model_valuation
    
    comparable_sales = [
        {
            'address': s['address'],
            'sale_price': s['price'],
            'sale_date': datetime.fromtimestamp(s['sale_date'] / 1000).isoformat()[:10] if s['sale_date'] else None,
            'npui': s['utility_index'],
            'distance_km': s['distance_km'],
        }
        for s in recent_points
        if abs(s['utility_index'] - subject_npui) <= 0.15
    ][:8]
    
    has_listing_price = parse_price(subject_doc.get('price')) is not None
    
    valuation_breakdown = None
    if npui_median or model_valuation:
        valuation_breakdown = {
            'has_listing_price': has_listing_price,
            'model_valuation': model_valuation,
            'npui_median': npui_median,
            'npui_average': npui_average,
            'blended_valuation': blended_valuation,
            'comparable_sales': comparable_sales,
        }
    
    # Build final response
    subject_breakdown = breakdown_map[subject_id]
    
    # Strip internal _source_doc references before writing to MongoDB
    for pt in comparable_points + recent_points:
        pt.pop('_source_doc', None)

    # Post-computation exclusion: if reconciled valuation >= $2.5M, exclude.
    # This catches properties where listing price was unparseable ("Contact Agent")
    # but the model predicted a high value.
    rv = confidence_result.get('reconciled_valuation')
    if rv and rv >= 2_500_000:
        return {
            'computed_at': datetime.utcnow(),
            'confidence': {
                'reconciled_valuation': None,
                'confidence': 'not_available',
                'range': None,
                'exclusion_reason': 'valuation_above_threshold',
                'n_verified': 0,
                'n_total': len(comparable_points) + len(recent_points),
            },
            'summary': {
                'insufficient_data': True,
                'exclusion_reason': 'valuation_above_threshold',
                'n_comps': len(comparable_points) + len(recent_points),
                'n_current_listings': len(comparable_points),
                'n_recent_sales': len(recent_points),
            },
            'metadata': {
                'generated_at': int(datetime.utcnow().timestamp() * 1000),
                'parameters': {'address': subject_doc.get('address')},
                'gaps_version': 3,
            },
        }

    valuation_data = {
        'computed_at': datetime.utcnow(),
        'subject_property': {
            'id': subject_id,
            'address': subject_doc.get('address', 'Unknown'),
            'price': subject_price,
            'valuation_price': model_valuation,
            'utility_index': subject_npui,
            'distance_km': None,
            'series': 'current_listing',
            'features': {
                'basic': {
                    **basic_features(subject_doc),
                    'approximate_build_year': subject_build_year,
                    'beach_distance_km': subject_beach_km,
                    'renovation_quality_score': subject_features.get('renovation_quality_score'),
                    'street_premium_pct': subject_features.get('street_premium_pct'),
                    'micro_location_premium_pct': subject_features.get('micro_location_premium_pct'),
                },
                'npui_breakdown': subject_breakdown,
            },
            'images': extract_images(subject_doc),
        },
        'comparables': comparable_points,
        'recent_sales': recent_points,
        'chart_points': chart_points,
        'summary': {
            'value_gap_pct': value_gap_result['value_gap_pct'],
            'positioning': value_gap_result['positioning'],
            'n_comps': len(comparable_points) + len(recent_points),
            'n_current_listings': len(comparable_points),
            'n_recent_sales': len(recent_points),
            'n_included_in_valuation': len(included_points),
            'n_verified_included': sum(
                1 for p in included_points
                if p.get('verification', {}).get('status') == 'verified'
            ),
            'insufficient_data': insufficient_data,
        },
        'valuation_breakdown': valuation_breakdown,
        'adjustment_rates': {
            'rates': {k: v for k, v in adj_rates.items() if k not in ('source', 'sample_size', 'r_squared')},
            'source': adj_source,
            'sample_size': adj_rates.get('sample_size', 0),
        },
        'confidence': confidence_result,
        'regression_line': {
            'slope': reg_slope,
            'intercept': reg_intercept,
        },
        'metadata': {
            'generated_at': int(datetime.utcnow().timestamp() * 1000),
            'parameters': {'address': subject_doc.get('address')},
            'gaps_version': 3,
        },
    }
    
    return valuation_data


def main():
    """Main execution function"""
    # Load environment variables from .env file
    load_dotenv()
    
    print("=" * 80)
    print("Pre-computing Valuation Data for All For-Sale Properties")
    print("=" * 80)
    print()
    
    # Connect to database
    print("Connecting to Azure Cosmos DB...")
    client = get_db_connection()
    db = client['Gold_Coast']
    print("✅ Connected\n")

    # Load sold comparables from both databases, merged and deduped by suburb
    print("Loading sold comparables...")
    sold_by_suburb = _load_sold_comparables(client)
    total_sold = sum(len(v) for v in sold_by_suburb.values())
    print(f"✅ {total_sold} sold records across {len(sold_by_suburb)} suburbs")
    for sub, docs in sorted(sold_by_suburb.items()):
        src_counts = {}
        for d in docs:
            src = d.get('_sold_source', 'unknown')
            src_counts[src] = src_counts.get(src, 0) + 1
        print(f"   {sub}: {len(docs)} total — {src_counts}")
    print()

    # Get all for-sale properties from per-suburb collections
    # Prioritise target suburbs to avoid burning RU budget on non-target areas
    TARGET_SUBURBS = [
        'robina', 'burleigh_waters', 'varsity_lakes',
        'burleigh_heads', 'mudgeeraba', 'reedy_creek',
        'merrimac', 'worongary', 'carrara',
    ]

    # Pre-load Gold_Coast coordinates and timelines for distance + build year
    # Only load target suburbs + sold suburbs (not all 95) to conserve RUs
    all_suburb_keys = list(set(
        list(sold_by_suburb.keys()) +
        TARGET_SUBURBS
    ))
    print("Pre-loading Gold_Coast coordinates...")
    gc_coord_lookup = _preload_gc_coordinates(client, all_suburb_keys)
    print("Pre-loading Gold_Coast property timelines...")
    gc_timeline_lookup = _preload_gc_timelines(client, all_suburb_keys)
    print()
    print("Building suburb median cache...")
    median_cache = _build_suburb_median_cache(sold_by_suburb)
    print(f"✅ {len(median_cache)} month-suburb medians cached")
    print("Building street premium cache...")
    street_premium_cache = _build_street_premium_cache(sold_by_suburb, median_cache)
    print(f"✅ {len(street_premium_cache)} streets with premium data")
    print()
    print("Fetching for-sale properties from target suburbs only...")
    # Only query TARGET_SUBURBS — these are the suburbs shown on the website.
    # Querying all 91 suburbs finds ~2,229 properties and causes timeouts + 429s.
    # Target suburbs have ~116 active listings — completes in minutes, not hours.
    suburb_collections = list(TARGET_SUBURBS)
    all_properties = []
    for col_name in suburb_collections:
        # Retry-safe cursor iteration for Cosmos DB 429 rate limiting
        fetched = 0
        for attempt in range(8):
            try:
                cursor = db[col_name].find({'listing_status': 'for_sale'}).batch_size(50).skip(fetched)
                for doc in cursor:
                    doc['_collection'] = col_name
                    all_properties.append(doc)
                    fetched += 1
                break  # success
            except Exception as e:
                if '16500' in str(e) and attempt < 7:
                    import re as _re
                    _m = _re.search(r'RetryAfterMs=(\d+)', str(e))
                    wait = max(int(_m.group(1)) / 1000.0 if _m else 5, 2 * (attempt + 1))
                    print(f"    Cosmos 429 on {col_name} after {fetched} docs, waiting {wait:.1f}s (attempt {attempt+1}/8)")
                    time.sleep(wait)
                else:
                    raise
        time.sleep(0.5)  # brief pause between suburb collections to spread RU load
    listings_coll = None  # no longer a single flat collection
    print(f"✅ Found {len(all_properties)} for-sale properties across {len(suburb_collections)} suburb collections\n")
    
    print("Pre-computing valuation data:")
    print("-" * 80)
    
    success_count = 0
    skip_count = 0
    error_count = 0
    
    for i, subject_doc in enumerate(all_properties):
        property_id = str(subject_doc['_id'])
        address = subject_doc.get('address', 'Unknown')
        
        print(f"[{i+1}/{len(all_properties)}] Processing: {address}")
        
        try:
            start_time = time.time()

            # Compute valuation data
            valuation_data = precompute_property_valuation(
                db, subject_doc, listings_coll, sold_by_suburb,
                gc_coord_lookup, gc_timeline_lookup,
                median_cache, street_premium_cache)

            if valuation_data:
                # Store in database with retry on 429 (Cosmos DB rate limiting)
                computation_time_ms = int((time.time() - start_time) * 1000)
                valuation_data['metadata']['computation_time_ms'] = computation_time_ms

                col_name = subject_doc.get('_collection')
                for attempt in range(5):
                    try:
                        db[col_name].update_one(
                            {'_id': subject_doc['_id']},
                            {'$set': {'valuation_data': valuation_data}}
                        )
                        break
                    except Exception as write_err:
                        err_str = str(write_err)
                        if '16500' in err_str or 'TooManyRequests' in err_str:
                            # Extract RetryAfterMs if available
                            import re as _re_retry
                            retry_match = _re_retry.search(r'RetryAfterMs=(\d+)', err_str)
                            wait_ms = int(retry_match.group(1)) if retry_match else 1000 * (attempt + 1)
                            wait_s = max(wait_ms / 1000.0, 0.5) * (attempt + 1)
                            if attempt < 4:
                                time.sleep(wait_s)
                                continue
                        raise

                exclusion = valuation_data.get('summary', {}).get('exclusion_reason')
                if exclusion:
                    print(f"  ⚠️  Excluded ({exclusion}) — cleared existing valuation")
                    skip_count += 1
                else:
                    n_inc = valuation_data['summary'].get('n_included_in_valuation', '?')
                    n_tot = valuation_data['summary']['n_comps']
                    print(f"  ✅ Success ({computation_time_ms}ms, {n_inc}/{n_tot} comps included)")
                    success_count += 1
            else:
                print(f"  ⚠️  Skipped (insufficient data)")
                skip_count += 1

        except Exception as e:
            print(f"  ❌ Error: {str(e)}")
            error_count += 1

        # Rate limiting — 2.0s between properties to avoid Cosmos DB 429 errors
        # Each valuation_data write is ~50KB (heavy RU cost); needs spacing
        if i < len(all_properties) - 1:
            time.sleep(2.0)
    
    print()
    print("=" * 80)
    print("SUMMARY")
    print("=" * 80)
    print(f"✅ Successfully processed: {success_count}")
    print(f"⚠️  Skipped:               {skip_count}")
    print(f"❌ Errors:                {error_count}")
    print("=" * 80)
    
    client.close()


if __name__ == '__main__':
    main()
