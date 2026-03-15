#!/usr/bin/env python3
"""
Valuation Backtest — Test the comparable-sales reconciled valuation method
against actual sale prices using leave-one-out cross-validation.

For each sold property:
  1. Treat it as the "subject" (pretend it hasn't sold yet)
  2. Use other sold properties as comparables
  3. Run the full NPUI + adjustment + weighting + reconciliation pipeline
  4. Compare reconciled_valuation to actual sale price

Also compares against Domain's valuation for benchmarking.

Usage:
  python3 scripts/valuation_backtest.py                    # All suburbs
  python3 scripts/valuation_backtest.py --suburb robina     # Single suburb
  python3 scripts/valuation_backtest.py --limit 50          # First 50 properties
  python3 scripts/valuation_backtest.py --verbose           # Show each property
"""

import argparse
import os
import sys
import re
import time
import math
from datetime import datetime
from collections import defaultdict

# Add the precompute script directory to path so we can import its functions
VALUATION_DIR = "/home/fields/Feilds_Website/07_Valuation_Comps"
sys.path.insert(0, VALUATION_DIR)

from pymongo import MongoClient
from dotenv import load_dotenv

# Import the actual valuation functions from precompute_valuations.py
from precompute_valuations import (
    extract_npui_inputs,
    compute_cohort_stats,
    compute_npui_for_cohort,
    compute_value_gap,
    check_coverage,
    basic_features,
    parse_price,
    is_waterfront,
    calculate_adjustments,
    compute_independent_valuation,
    verify_comparable,
    calculate_weight,
    select_quality_comps,
    normalize_weights,
    calculate_confidence,
    get_adjustment_rates,
    haversine_distance,
    extract_images,
)

# These may be private — import with fallback
try:
    from precompute_valuations import (
        _resolve_coordinates,
        _resolve_build_year,
        _load_sold_comparables,
        _preload_gc_coordinates,
        _preload_gc_timelines,
        _build_suburb_median_cache,
        _build_street_premium_cache,
        _extract_street_name,
        compute_micro_location_premium,
        compute_renovation_quality_score,
    )
except ImportError:
    _resolve_coordinates = None
    _resolve_build_year = None
    _load_sold_comparables = None

SUBURBS = [
    "robina", "burleigh_waters", "varsity_lakes", "burleigh_heads",
    "mudgeeraba", "reedy_creek", "merrimac", "worongary", "carrara"
]


def extract_sale_price(doc):
    """Extract numeric sale price from a sold document."""
    for field in ["sale_price", "sold_price", "last_sold_price"]:
        val = doc.get(field)
        if val:
            price = parse_price(val)
            if price and price > 50000:
                return price
    return None


def get_sold_date(doc):
    """Extract sold date from document."""
    for field in ["sold_date", "sale_date"]:
        val = doc.get(field)
        if val:
            if isinstance(val, datetime):
                return val
            if isinstance(val, str):
                try:
                    return datetime.fromisoformat(val[:10])
                except (ValueError, TypeError):
                    pass
    return None


def backtest_single_property(db, subject_doc, all_sold_in_suburb, sold_by_suburb,
                              gc_coord_lookup, gc_timeline_lookup,
                              median_cache=None, street_premium_cache=None,
                              no_new_factors=False):
    """
    Run the valuation pipeline on a single sold property, using other sold
    properties as comparables. Returns the reconciled_valuation or None.

    This mirrors precompute_property_valuation() but:
    - Excludes the subject from the comparable pool
    - Uses the sale_price field for actual price (not listing price)
    - Returns just the reconciled valuation for comparison
    """
    subject_id = str(subject_doc['_id'])
    suburb = subject_doc.get('suburb', '')
    prop_type = subject_doc.get('property_type', 'House')
    subject_is_waterfront = is_waterfront(subject_doc)
    suburb_key = subject_doc.get('_collection', suburb.lower().replace(' ', '_'))

    # Resolve subject coordinates and build year
    subject_lat, subject_lon = None, None
    subject_build_year = None
    if _resolve_coordinates:
        subject_lat, subject_lon = _resolve_coordinates(subject_doc, gc_coord_lookup or {}, suburb_key)
    if _resolve_build_year:
        subject_build_year = _resolve_build_year(subject_doc, gc_timeline_lookup or {}, suburb_key)

    # Temporal awareness: only use comparables that sold BEFORE the subject
    # This prevents lookahead bias — in production we wouldn't know future sales
    subject_sold_date = get_sold_date(subject_doc)

    def sold_before_subject(s):
        """Only include comparables that sold before the subject property."""
        if not subject_sold_date:
            return True  # Can't filter without a date
        comp_date = get_sold_date(s)
        if not comp_date:
            return True  # Keep if we can't determine date
        return comp_date < subject_sold_date

    # Build comparable sold pool — EXCLUDE the subject, only prior sales
    comparable_sold = [
        s for s in all_sold_in_suburb
        if str(s['_id']) != subject_id
        and s.get('property_type', '') == prop_type
        and (parse_price(s.get('sale_price') or s.get('sold_price')) or 0) > 0
        and sold_before_subject(s)
    ][:60]

    # Detect if subject is a unit/apartment (X/Y address format) vs standalone house
    import re as _re
    subject_addr = subject_doc.get('address', '')
    subject_is_unit = bool(_re.match(r'^\d+/\d+', subject_addr.strip()))

    # Detect if subject is acreage (land > 5,000 sqm)
    from precompute_valuations import resolve_land_size
    subject_land = resolve_land_size(subject_doc)
    subject_is_acreage = subject_land is not None and subject_land > 5000

    # Detect prestige tier
    from precompute_valuations import infer_prestige_tier
    subject_prestige = infer_prestige_tier(subject_doc)
    subject_is_prestige = subject_prestige in ('prestige', 'ultra_prestige')

    # Filter by waterfront status, bedroom band, dwelling type, and prestige tier
    subject_beds = subject_doc.get('bedrooms')
    bed_band = [max(1, subject_beds - 1), subject_beds + 1] if subject_beds is not None else None

    def in_cohort(doc):
        if subject_is_waterfront and not is_waterfront(doc):
            return False
        if not subject_is_waterfront and is_waterfront(doc):
            return False
        # Prestige tier: soft filter via weighting (not hard exclude)
        if bed_band:
            beds = doc.get('bedrooms')
            if beds is None or beds < bed_band[0] or beds > bed_band[1]:
                return False
        # Don't mix units with standalone houses
        comp_addr = doc.get('address', '')
        comp_is_unit = bool(_re.match(r'^\d+/\d+', comp_addr.strip()))
        if subject_is_unit != comp_is_unit:
            return False
        # Don't mix acreage with suburban lots
        comp_land = resolve_land_size(doc)
        comp_is_acreage = comp_land is not None and comp_land > 5000
        if subject_is_acreage != comp_is_acreage:
            return False
        return True

    filtered_sales = [s for s in comparable_sold if in_cohort(s)]

    if len(filtered_sales) < 3:
        return None  # Not enough comparables

    # For the backtest, we use the subject's sale price as the "listing price"
    # but we don't actually need it for the reconciled valuation calculation
    # The reconciled valuation is derived entirely from comparable adjustments

    # Compute NPUI for all properties
    all_docs = [subject_doc] + filtered_sales
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

    subject_npui = breakdown_map[subject_id]['npui']

    # Build recent sale points (these are the comparables)
    recent_points = []
    chart_points = []

    # Add subject to chart points (needed for regression)
    subject_price_actual = extract_sale_price(subject_doc)
    chart_points.append({
        'type': 'subject',
        'series': 'current_listing',
        'price': subject_price_actual,
        'npui': subject_npui,
        'label': subject_doc.get('address', 'Subject'),
        'id': subject_id,
    })

    for s in filtered_sales:
        sid = str(s['_id'])
        price = parse_price(s.get('sale_price') or s.get('sold_price'))
        if not price:
            continue

        bd = breakdown_map.get(sid)
        if not bd:
            continue
        cov = check_coverage(bd['inputs'], bd['null_fields'])
        if cov['core_coverage'] < 0.5 or cov['overall_coverage'] < 0.2 or not cov['has_land_and_floor']:
            continue

        npui = bd['npui']

        # Parse sale date
        sale_date_ms = None
        sale_date_raw = s.get('sale_date') or s.get('sold_date')
        if isinstance(sale_date_raw, str) and sale_date_raw:
            try:
                sale_date_ms = int(datetime.fromisoformat(sale_date_raw[:10]).timestamp() * 1000)
            except (ValueError, TypeError):
                pass

        # Resolve distance and build year
        s_lat, s_lon = None, None
        s_dist_km = None
        s_build_year = None
        if _resolve_coordinates:
            s_lat, s_lon = _resolve_coordinates(s, gc_coord_lookup or {}, suburb_key)
        if subject_lat and subject_lon and s_lat and s_lon:
            s_dist_km = round(haversine_distance(subject_lat, subject_lon, s_lat, s_lon), 2)
        if _resolve_build_year:
            s_build_year = _resolve_build_year(s, gc_timeline_lookup or {}, suburb_key)

        sale_basic = basic_features(s)
        sale_basic['approximate_build_year'] = s_build_year

        recent_points.append({
            'id': sid,
            'address': s.get('address', 'Recent sale'),
            'price': price,
            'valuation_price': None,
            'utility_index': npui,
            'distance_km': s_dist_km,
            'sale_date': sale_date_ms,
            'series': 'recent_sale',
            'features': {
                'basic': sale_basic,
                'npui_breakdown': bd,
            },
            'images': [],
            '_source_doc': s,
        })

        chart_points.append({
            'type': 'recent_sale',
            'series': 'recent_sale',
            'price': price,
            'npui': npui,
            'label': s.get('address', 'Recent sale'),
            'id': sid,
            'sale_date': sale_date_ms,
        })

    if len(recent_points) < 3:
        return None

    # Compute value gap (gives us regression slope/intercept for Gap 1)
    value_gap_result = compute_value_gap(subject_price_actual, subject_npui, chart_points)
    reg_slope = value_gap_result.get('slope')
    reg_intercept = value_gap_result.get('intercept')

    # Gap 2: Get adjustment rates (only from prior sales — temporal awareness)
    all_sold_for_rates = [
        s for s in all_sold_in_suburb
        if str(s['_id']) != subject_id
        and s.get('property_type', '') == prop_type
        and sold_before_subject(s)
    ]
    adj_rates, adj_source = get_adjustment_rates(suburb, all_sold_for_rates,
                                                  gc_timeline_lookup or {}, suburb_key)

    # Extract subject features
    subject_bd = breakdown_map[subject_id]
    subject_basic = basic_features(subject_doc)
    subject_features = {
        'land_size_sqm': subject_bd['inputs'].get('land_size_sqm') or subject_basic.get('land_size_sqm'),
        'floor_area_sqm': subject_bd['inputs'].get('floor_area_sqm') or subject_basic.get('floor_area_sqm'),
        'bedrooms': subject_doc.get('bedrooms', 0),
        'bathrooms': subject_doc.get('bathrooms', 0),
        'car_spaces': subject_doc.get('car_spaces') or subject_doc.get('carspaces') or 0,
        'condition_score': subject_bd['inputs'].get('interior.overall_interior_condition_score', 5),
        'pool_present': subject_basic.get('pool_present', False),
        'number_of_stories': subject_basic.get('number_of_stories'),
        'renovation_level': subject_basic.get('renovation_level', 3),
        'water_views': subject_basic.get('water_views', False),
        'cladding_level': subject_basic.get('cladding_level', 2),
        'kitchen_score': subject_basic.get('kitchen_score'),
        'ac_ducted': subject_basic.get('ac_ducted', False),
        'approximate_build_year': subject_build_year,
        'renovation_quality_score': None if no_new_factors else subject_basic.get('renovation_quality_score'),
        'street_premium_pct': None if no_new_factors else (
            (street_premium_cache or {}).get(
                (suburb_key, _extract_street_name(subject_doc)), (None,))[0]
            if _extract_street_name and street_premium_cache else None),
        'micro_location_premium_pct': None if no_new_factors else (
            compute_micro_location_premium(
                subject_lat, subject_lon, suburb_key,
                all_sold_in_suburb, median_cache or {})[0]
            if subject_lat and subject_lon and compute_micro_location_premium else None),
    }

    # Pass 1: Compute adjustments for all comparables
    all_enriched_points = []
    for pt in recent_points:
        comp_price = pt['price']
        comp_npui = pt['utility_index']
        comp_bd = pt.get('features', {}).get('npui_breakdown') or {}
        comp_bd_inputs = comp_bd.get('inputs') or {}
        comp_bd_null_fields = comp_bd.get('null_fields') or []
        comp_cov = check_coverage(comp_bd_inputs, comp_bd_null_fields)

        # Gap 1: Independent valuation
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
            'condition_score': comp_bd_inputs.get('interior.overall_interior_condition_score', 5),
            'pool_present': basic.get('pool_present', False),
            'number_of_stories': basic.get('number_of_stories'),
            'renovation_level': basic.get('renovation_level', 3),
            'water_views': basic.get('water_views', False),
            'cladding_level': basic.get('cladding_level', 2),
            'kitchen_score': basic.get('kitchen_score'),
            'ac_ducted': basic.get('ac_ducted', False),
            'approximate_build_year': basic.get('approximate_build_year'),
            'renovation_quality_score': None if no_new_factors else basic.get('renovation_quality_score'),
            'street_premium_pct': None if no_new_factors else (
                (street_premium_cache or {}).get(
                    (suburb_key, _extract_street_name(pt.get('_source_doc') or pt)), (None,))[0]
                if _extract_street_name and street_premium_cache else None),
            'micro_location_premium_pct': None if no_new_factors else (
                compute_micro_location_premium(
                    float(s_lat) if s_lat else None,
                    float(s_lon) if s_lon else None,
                    suburb_key, all_sold_in_suburb,
                    median_cache or {})[0]
                if s_lat and s_lon and compute_micro_location_premium else None),
        }
        adj_result = calculate_adjustments(subject_features, comp_features, comp_price, adj_rates)
        pt['adjustment_result'] = adj_result
        pt['_data_quality_pct'] = comp_cov['overall_coverage']
        all_enriched_points.append(pt)

    # Pass 2: Verification
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

    # Pass 3: Weights
    for pt in all_enriched_points:
        pt['weight'] = calculate_weight(pt)

    # Pass 3.5: Prestige tier weight adjustment
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

    # Quality comp selection
    select_quality_comps(all_enriched_points, min_comps=3, target_comps=8)
    included_points = [p for p in all_enriched_points if p.get('included_in_valuation', False)]

    if not included_points:
        return None

    # Normalize weights
    normalize_weights(included_points)

    # Set excluded to zero
    for pt in all_enriched_points:
        if not pt.get('included_in_valuation', False):
            pt.setdefault('weight', {})['normalized'] = 0.0

    # Gap 6: Confidence interval
    confidence_result = calculate_confidence(included_points, n_total_override=len(all_enriched_points))

    return {
        'reconciled_valuation': confidence_result.get('reconciled_valuation'),
        'confidence': confidence_result.get('confidence'),
        'range_low': confidence_result.get('range', {}).get('low') if confidence_result.get('range') else None,
        'range_high': confidence_result.get('range', {}).get('high') if confidence_result.get('range') else None,
        'n_included': len(included_points),
        'n_total_comps': len(all_enriched_points),
        'cv': confidence_result.get('cv'),
    }


def compute_metrics(results):
    """Compute accuracy metrics from a list of result dicts."""
    if not results:
        return {}

    errors = [r["error_pct"] for r in results]
    abs_errors = [abs(e) for e in errors]
    dollar_errors = [abs(r["predicted"] - r["actual"]) for r in results]

    abs_errors_sorted = sorted(abs_errors)
    dollar_errors_sorted = sorted(dollar_errors)
    n = len(abs_errors)

    return {
        "count": n,
        "mae_pct": sum(abs_errors) / n,
        "median_ae_pct": abs_errors_sorted[n // 2],
        "mean_error_pct": sum(errors) / n,
        "mae_dollars": sum(dollar_errors) / n,
        "median_ae_dollars": dollar_errors_sorted[n // 2],
        "within_5pct": sum(1 for e in abs_errors if e <= 5) / n * 100,
        "within_10pct": sum(1 for e in abs_errors if e <= 10) / n * 100,
        "within_15pct": sum(1 for e in abs_errors if e <= 15) / n * 100,
        "within_20pct": sum(1 for e in abs_errors if e <= 20) / n * 100,
        "worst_over": max(errors),
        "worst_under": min(errors),
        "p90_error": abs_errors_sorted[int(n * 0.9)] if n >= 10 else abs_errors_sorted[-1],
    }


def print_metrics(label, metrics, indent=2):
    pad = " " * indent
    if not metrics:
        print(f"{pad}No data")
        return
    print(f"{pad}{label} (n={metrics['count']})")
    print(f"{pad}  MAE:            {metrics['mae_pct']:.1f}%  (${metrics['mae_dollars']:,.0f})")
    print(f"{pad}  Median AE:      {metrics['median_ae_pct']:.1f}%  (${metrics['median_ae_dollars']:,.0f})")
    print(f"{pad}  Bias (mean):    {metrics['mean_error_pct']:+.1f}%  {'(overvalues)' if metrics['mean_error_pct'] > 0 else '(undervalues)'}")
    print(f"{pad}  Within  5%:     {metrics['within_5pct']:.0f}%")
    print(f"{pad}  Within 10%:     {metrics['within_10pct']:.0f}%")
    print(f"{pad}  Within 15%:     {metrics['within_15pct']:.0f}%")
    print(f"{pad}  Within 20%:     {metrics['within_20pct']:.0f}%")
    print(f"{pad}  Worst over:     +{metrics['worst_over']:.1f}%")
    print(f"{pad}  Worst under:    {metrics['worst_under']:.1f}%")
    if metrics["count"] >= 10:
        print(f"{pad}  90th pctl err:  {metrics['p90_error']:.1f}%")


def main():
    parser = argparse.ArgumentParser(description="Valuation Backtest (Comparable Sales Method)")
    parser.add_argument("--suburb", type=str, help="Filter to a single suburb")
    parser.add_argument("--limit", type=int, help="Limit number of properties to test")
    parser.add_argument("--verbose", action="store_true", help="Show each property result")
    parser.add_argument("--min-price", type=int, default=300000, help="Minimum sale price to include")
    parser.add_argument("--max-price", type=int, default=5000000, help="Maximum sale price to include")
    parser.add_argument("--no-new-factors", action="store_true",
                        help="Disable renovation quality, street premium, and micro-location factors for A/B comparison")
    parser.add_argument("--save-results", action="store_true",
                        help="Save backtest results to MongoDB (system_monitor.valuation_accuracy) for website display")
    args = parser.parse_args()

    load_dotenv("/home/fields/Fields_Orchestrator/.env")

    client = MongoClient(os.environ["COSMOS_CONNECTION_STRING"],
                         retryWrites=False, serverSelectionTimeoutMS=30000, socketTimeoutMS=60000)
    db = client["Gold_Coast"]

    print("=" * 70)
    print("VALUATION BACKTEST — Comparable Sales Reconciled Method")
    print("=" * 70)

    # Load sold comparables (same function the production system uses)
    print("\nLoading sold comparables...")
    if _load_sold_comparables:
        sold_by_suburb = _load_sold_comparables(client)
    else:
        # Fallback: load directly
        sold_by_suburb = {}
        for suburb in SUBURBS:
            docs = list(db[suburb].find({"listing_status": "sold"}))
            if docs:
                sold_by_suburb[suburb] = docs
    total_sold = sum(len(v) for v in sold_by_suburb.values())
    print(f"  {total_sold} sold records across {len(sold_by_suburb)} suburbs")

    # Pre-load coordinates and timelines
    print("Loading coordinates and timelines...")
    gc_coord_lookup = {}
    gc_timeline_lookup = {}
    if _preload_gc_coordinates:
        all_suburb_keys = list(sold_by_suburb.keys())
        gc_coord_lookup = _preload_gc_coordinates(client, all_suburb_keys)
        gc_timeline_lookup = _preload_gc_timelines(client, all_suburb_keys)
    print("  Done")

    # Build caches for new factors (street premium, micro-location)
    median_cache = {}
    street_premium_cache = {}
    if not args.no_new_factors and _build_suburb_median_cache:
        print("Building suburb median cache...")
        median_cache = _build_suburb_median_cache(sold_by_suburb)
        print(f"  {len(median_cache)} month-suburb medians cached")
        print("Building street premium cache...")
        street_premium_cache = _build_street_premium_cache(sold_by_suburb, median_cache)
        print(f"  {len(street_premium_cache)} streets with premium data")
    elif args.no_new_factors:
        print("New factors DISABLED (--no-new-factors)")

    # Build test set: sold properties with known sale prices
    suburbs_to_test = [args.suburb] if args.suburb else SUBURBS
    test_properties = []

    for suburb in suburbs_to_test:
        sold_docs = list(db[suburb].find({"listing_status": "sold"}))
        for doc in sold_docs:
            actual_price = extract_sale_price(doc)
            if not actual_price:
                continue
            if actual_price < args.min_price or actual_price > args.max_price:
                continue
            doc['_collection'] = suburb
            test_properties.append(doc)

    if args.limit:
        test_properties = test_properties[:args.limit]

    print(f"\nTesting {len(test_properties)} sold properties")
    print("-" * 70)

    # Run backtest
    fields_results = []
    domain_results = []
    per_suburb = defaultdict(lambda: {"fields": [], "domain": []})
    per_type = defaultdict(lambda: {"fields": [], "domain": []})
    per_price_band = defaultdict(lambda: {"fields": [], "domain": []})
    per_confidence = defaultdict(list)
    skipped = 0
    errors = 0

    for i, doc in enumerate(test_properties):
        actual_price = extract_sale_price(doc)
        addr = doc.get('address', doc.get('complete_address', 'Unknown'))
        suburb = doc.get('_collection', '')
        ptype = doc.get('property_type', 'Unknown')
        sold_date = get_sold_date(doc)

        # Price band
        if actual_price < 700000:
            band = "<$700K"
        elif actual_price < 1000000:
            band = "$700K-$1M"
        elif actual_price < 1500000:
            band = "$1M-$1.5M"
        elif actual_price < 2000000:
            band = "$1.5M-$2M"
        else:
            band = "$2M+"

        # Get the sold records for this suburb (from merged pool)
        all_sold_in_suburb = sold_by_suburb.get(suburb, [])

        try:
            result = backtest_single_property(
                db, doc, all_sold_in_suburb, sold_by_suburb,
                gc_coord_lookup, gc_timeline_lookup,
                median_cache, street_premium_cache,
                no_new_factors=args.no_new_factors
            )
        except Exception as e:
            if args.verbose:
                print(f"  [{i+1}] ERROR: {addr[:50]} — {e}")
            errors += 1
            continue

        if not result or not result['reconciled_valuation']:
            skipped += 1
            continue

        predicted = result['reconciled_valuation']
        error_pct = (predicted - actual_price) / actual_price * 100

        entry = {
            "address": addr,
            "suburb": suburb,
            "type": ptype,
            "actual": actual_price,
            "predicted": predicted,
            "error_pct": error_pct,
            "sold_date": sold_date,
            "band": band,
            "confidence": result['confidence'],
            "n_comps": result['n_included'],
            "range_low": result.get('range_low'),
            "range_high": result.get('range_high'),
        }

        fields_results.append(entry)
        per_suburb[suburb]["fields"].append(entry)
        per_type[ptype]["fields"].append(entry)
        per_price_band[band]["fields"].append(entry)
        per_confidence[result['confidence']].append(entry)

        # Domain valuation comparison
        dva = doc.get("domain_valuation_accuracy")
        if dva and dva.get("domain_mid") and actual_price:
            domain_mid = dva["domain_mid"]
            domain_err = (domain_mid - actual_price) / actual_price * 100
            d_entry = {
                "address": addr,
                "suburb": suburb,
                "type": ptype,
                "actual": actual_price,
                "predicted": domain_mid,
                "error_pct": domain_err,
                "band": band,
            }
            domain_results.append(d_entry)
            per_suburb[suburb]["domain"].append(d_entry)
            per_type[ptype]["domain"].append(d_entry)
            per_price_band[band]["domain"].append(d_entry)

        if args.verbose:
            in_range = ""
            if entry["range_low"] and entry["range_high"]:
                in_range = " IN-RANGE" if entry["range_low"] <= actual_price <= entry["range_high"] else " OUT-OF-RANGE"
            print(f"  [{i+1}] {addr[:45]:<45} Actual: ${actual_price:>10,}  Predicted: ${predicted:>10,}  Error: {error_pct:>+6.1f}%  [{result['confidence']}]{in_range}")

        # Progress indicator
        if not args.verbose and (i + 1) % 50 == 0:
            print(f"  Processed {i+1}/{len(test_properties)}...")

    # === RESULTS ===
    print(f"\n{'=' * 70}")
    print(f"RESULTS — {len(fields_results)} valued, {skipped} skipped (insufficient comps), {errors} errors")
    print(f"{'=' * 70}")

    print(f"\n{'─' * 70}")
    print("OVERALL ACCURACY — Fields Comparable Sales Method")
    print(f"{'─' * 70}")
    print_metrics("Fields Reconciled Valuation", compute_metrics(fields_results))

    if domain_results:
        print()
        print_metrics("Domain Valuation (benchmark)", compute_metrics(domain_results))

    # Range accuracy
    if fields_results:
        with_range = [r for r in fields_results if r.get("range_low") and r.get("range_high")]
        if with_range:
            in_range_count = sum(1 for r in with_range if r["range_low"] <= r["actual"] <= r["range_high"])
            print(f"\n  90% Confidence Range Accuracy:")
            print(f"    {in_range_count}/{len(with_range)} ({in_range_count/len(with_range)*100:.0f}%) actual prices fell within predicted range")

    # By confidence level
    print(f"\n{'─' * 70}")
    print("BY CONFIDENCE LEVEL")
    print(f"{'─' * 70}")
    for conf in ['high', 'medium', 'low', 'very_low']:
        if conf in per_confidence:
            m = compute_metrics(per_confidence[conf])
            print(f"  {conf:<15} MAE: {m['mae_pct']:>5.1f}%  Within 10%: {m['within_10pct']:>4.0f}%  (n={m['count']})")

    # By suburb
    print(f"\n{'─' * 70}")
    print("BY SUBURB")
    print(f"{'─' * 70}")
    for suburb in sorted(per_suburb.keys()):
        data = per_suburb[suburb]
        fm = compute_metrics(data["fields"])
        dm = compute_metrics(data["domain"])
        f_mae = f"{fm['mae_pct']:.1f}%" if fm else "N/A"
        d_mae = f"{dm['mae_pct']:.1f}%" if dm else "N/A"
        f_w10 = f"{fm['within_10pct']:.0f}%" if fm else "N/A"
        d_w10 = f"{dm['within_10pct']:.0f}%" if dm else "N/A"
        f_n = fm["count"] if fm else 0
        d_n = dm["count"] if dm else 0
        print(f"  {suburb:<20} Fields: MAE {f_mae:>6} w10%={f_w10:>4} (n={f_n:<3})  Domain: MAE {d_mae:>6} w10%={d_w10:>4} (n={d_n:<3})")

    # By property type
    print(f"\n{'─' * 70}")
    print("BY PROPERTY TYPE")
    print(f"{'─' * 70}")
    for ptype in sorted(per_type.keys()):
        data = per_type[ptype]
        fm = compute_metrics(data["fields"])
        dm = compute_metrics(data["domain"])
        f_mae = f"{fm['mae_pct']:.1f}%" if fm else "N/A"
        d_mae = f"{dm['mae_pct']:.1f}%" if dm else "N/A"
        f_n = fm["count"] if fm else 0
        d_n = dm["count"] if dm else 0
        print(f"  {ptype:<25} Fields: MAE {f_mae:>6} (n={f_n:<3})  Domain: MAE {d_mae:>6} (n={d_n:<3})")

    # By price band
    print(f"\n{'─' * 70}")
    print("BY PRICE BAND")
    print(f"{'─' * 70}")
    for band in ["<$700K", "$700K-$1M", "$1M-$1.5M", "$1.5M-$2M", "$2M+"]:
        if band not in per_price_band:
            continue
        data = per_price_band[band]
        fm = compute_metrics(data["fields"])
        dm = compute_metrics(data["domain"])
        f_mae = f"{fm['mae_pct']:.1f}%" if fm else "N/A"
        d_mae = f"{dm['mae_pct']:.1f}%" if dm else "N/A"
        f_n = fm["count"] if fm else 0
        d_n = dm["count"] if dm else 0
        print(f"  {band:<20} Fields: MAE {f_mae:>6} (n={f_n:<3})  Domain: MAE {d_mae:>6} (n={d_n:<3})")

    # Worst misses
    if fields_results:
        print(f"\n{'─' * 70}")
        print("WORST 10 MISSES")
        print(f"{'─' * 70}")
        worst = sorted(fields_results, key=lambda x: abs(x["error_pct"]), reverse=True)[:10]
        for r in worst:
            addr_short = r["address"][:50] if len(r["address"]) > 50 else r["address"]
            print(f"  {addr_short:<50} Actual: ${r['actual']:>10,}  Predicted: ${r['predicted']:>10,}  Error: {r['error_pct']:>+6.1f}%  [{r['confidence']}]")

    # Best predictions
    if fields_results and len(fields_results) >= 10:
        print(f"\n{'─' * 70}")
        print("BEST 10 PREDICTIONS")
        print(f"{'─' * 70}")
        best = sorted(fields_results, key=lambda x: abs(x["error_pct"]))[:10]
        for r in best:
            addr_short = r["address"][:50] if len(r["address"]) > 50 else r["address"]
            print(f"  {addr_short:<50} Actual: ${r['actual']:>10,}  Predicted: ${r['predicted']:>10,}  Error: {r['error_pct']:>+6.1f}%  [{r['confidence']}]")

    print(f"\n{'=' * 70}")
    print(f"Backtest complete.")
    print(f"{'=' * 70}")

    # === Save results to MongoDB if --save-results flag is set ===
    if args.save_results and fields_results:
        print("\nSaving results to MongoDB (system_monitor.valuation_accuracy)...")
        sm_db = client["system_monitor"]
        acc_coll = sm_db["valuation_accuracy"]

        overall_metrics = compute_metrics(fields_results)
        domain_metrics = compute_metrics(domain_results) if domain_results else {}

        # Build by-suburb metrics
        by_suburb = {}
        for sub, data in per_suburb.items():
            m = compute_metrics(data["fields"])
            if m:
                by_suburb[sub] = {
                    "count": m["count"], "mae_pct": round(m["mae_pct"], 1),
                    "median_ae_pct": round(m["median_ae_pct"], 1),
                    "within_10pct": round(m["within_10pct"]),
                    "within_15pct": round(m["within_15pct"]),
                }

        # Build by-price-band metrics
        by_band = {}
        for band_key in ["<$700K", "$700K-$1M", "$1M-$1.5M", "$1.5M-$2M", "$2M+"]:
            if band_key in per_price_band:
                m = compute_metrics(per_price_band[band_key]["fields"])
                if m:
                    by_band[band_key] = {
                        "count": m["count"], "mae_pct": round(m["mae_pct"], 1),
                        "within_10pct": round(m["within_10pct"]),
                    }

        # By confidence level
        by_confidence = {}
        for conf in ['high', 'medium', 'low', 'very_low']:
            if conf in per_confidence:
                m = compute_metrics(per_confidence[conf])
                if m:
                    by_confidence[conf] = {
                        "count": m["count"], "mae_pct": round(m["mae_pct"], 1),
                        "within_10pct": round(m["within_10pct"]),
                    }

        # Range accuracy
        with_range = [r for r in fields_results if r.get("range_low") and r.get("range_high")]
        in_range_count = sum(1 for r in with_range if r["range_low"] <= r["actual"] <= r["range_high"]) if with_range else 0
        range_accuracy = round(in_range_count / len(with_range) * 100) if with_range else None

        run_date = datetime.utcnow()

        # Document 1: Summary
        summary_doc = {
            "type": "summary",
            "run_date": run_date,
            "model_version": "comparable_sales_v3",
            "total_tested": len(fields_results),
            "total_skipped": skipped,
            "total_errors": errors,
            "metrics": {
                "mae_pct": round(overall_metrics["mae_pct"], 1),
                "median_ae_pct": round(overall_metrics["median_ae_pct"], 1),
                "mean_error_pct": round(overall_metrics["mean_error_pct"], 1),
                "mae_dollars": round(overall_metrics["mae_dollars"]),
                "within_5pct": round(overall_metrics["within_5pct"]),
                "within_10pct": round(overall_metrics["within_10pct"]),
                "within_15pct": round(overall_metrics["within_15pct"]),
                "within_20pct": round(overall_metrics["within_20pct"]),
                "p90_error": round(overall_metrics.get("p90_error", 0), 1),
                "range_accuracy_pct": range_accuracy,
            },
            "by_suburb": by_suburb,
            "by_price_band": by_band,
            "by_confidence": by_confidence,
            "domain_benchmark": {
                "mae_pct": round(domain_metrics.get("mae_pct", 0), 1),
                "within_10pct": round(domain_metrics.get("within_10pct", 0)),
                "count": domain_metrics.get("count", 0),
            } if domain_metrics else {},
            "model_updates": [
                {"date": "2026-03-15", "description": "Added renovation quality, street premium, and micro-location adjustment factors"},
                {"date": "2026-02-28", "description": "Removed NPUI from comp selection — switched to feature-level adjustments"},
                {"date": "2026-02-28", "description": "Added beach proximity adjustment factor"},
                {"date": "2026-02-23", "description": "Initial comparable sales valuation model with 12 adjustment factors"},
            ],
        }

        # Document 2: 20 most recent sold properties with predictions
        # Sort by sold_date descending, take 20
        dated_results = [r for r in fields_results if r.get("sold_date")]
        dated_results.sort(key=lambda x: x["sold_date"], reverse=True)
        recent_20 = dated_results[:20]

        properties_doc = {
            "type": "properties",
            "run_date": run_date,
            "properties": [
                {
                    "address": r["address"],
                    "suburb": r["suburb"],
                    "sale_price": round(r["actual"]),
                    "sale_date": r["sold_date"].isoformat()[:10] if r.get("sold_date") else None,
                    "predicted": round(r["predicted"]),
                    "error_pct": round(r["error_pct"], 1),
                    "confidence": r["confidence"],
                    "n_comps": r.get("n_comps"),
                    "bedrooms": None,  # not stored in result dict
                    "property_type": r.get("type", "House"),
                }
                for r in recent_20
            ],
        }

        # Upsert (replace previous run)
        acc_coll.replace_one({"type": "summary"}, summary_doc, upsert=True)
        acc_coll.replace_one({"type": "properties"}, properties_doc, upsert=True)
        print(f"  Saved summary ({len(fields_results)} tested) + {len(recent_20)} recent properties to MongoDB")


if __name__ == "__main__":
    main()
