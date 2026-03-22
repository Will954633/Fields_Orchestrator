#!/usr/bin/env python3
"""
Calculate Property Insights Script
Last Updated: 30/01/2026, 4:56 PM (Thursday) - Brisbane Time

Description:
Computes rarity insights and unique features for each property by comparing against
suburb statistics. Generates "ONLY 1", "TOP 3", and "RARE" badges for the frontend.

Output Fields:
- property_insights: {bedrooms, floor_area, lot_size} with rarity_insights arrays and suburbComparison

Usage:
    python calculate_property_insights.py
"""

from __future__ import annotations

import os
import re
import sys
import time
from datetime import datetime
from pathlib import Path
from typing import Dict, Any, List

from pymongo import MongoClient

REPO_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO_ROOT))

from shared.monitor_client import MonitorClient  # type: ignore
from shared.ru_guard import cosmos_retry, EmptyWorkSetError, sleep_with_jitter  # type: ignore

TARGET_SUBURBS = ["robina", "varsity_lakes", "burleigh_waters"]


def get_ordinal_suffix(n):
    """Get ordinal suffix for a number (1st, 2nd, 3rd, etc.)"""
    if 10 <= n % 100 <= 20:
        suffix = 'th'
    else:
        suffix = {1: 'st', 2: 'nd', 3: 'rd'}.get(n % 10, 'th')
    return f"{n}{suffix}"


def compute_floor_area_percentile(floor_area, stats):
    """
    Interpolate percentile rank for a floor_area value using p10/p25/p50/p75/p90 breakpoints.
    Returns an integer 0-100.
    """
    if not floor_area or not stats:
        return None
    p = stats.get('percentiles', {})
    p10 = p.get('p10'); p25 = p.get('p25'); p50 = p.get('p50')
    p75 = p.get('p75'); p90 = p.get('p90')
    if None in (p10, p25, p50, p75, p90):
        return None

    breakpoints = [(0, p10, 10), (p10, p25, 25), (p25, p50, 50),
                   (p50, p75, 75), (p75, p90, 90), (p90, float('inf'), 100)]
    for lo_v, hi_v, hi_p in breakpoints:
        lo_p = hi_p - (25 if hi_p not in (10, 100) else (10 if hi_p == 10 else 10))
        # Map the breakpoints list properly
        pass

    # Simpler linear interpolation across the 5 known breakpoints
    pts = [(p10, 10), (p25, 25), (p50, 50), (p75, 75), (p90, 90)]
    if floor_area <= p10:
        return max(1, int(floor_area / p10 * 10))
    if floor_area >= p90:
        return min(99, int(90 + (floor_area - p90) / max(p90 * 0.2, 1) * 10))
    for i in range(len(pts) - 1):
        lo_v, lo_p = pts[i]
        hi_v, hi_p = pts[i + 1]
        if lo_v <= floor_area <= hi_v:
            frac = (floor_area - lo_v) / (hi_v - lo_v)
            return int(lo_p + frac * (hi_p - lo_p))
    return 50


def compute_bedroom_percentile(bedrooms, distribution):
    """
    Compute percentile rank for bedroom count using current for-sale distribution.
    Returns an integer 0-100 representing "what % of for-sale properties have <= this many beds".
    """
    if not bedrooms or not distribution:
        return None
    total = sum(distribution.values())
    if total == 0:
        return None
    count_lte = sum(v for k, v in distribution.items() if int(k) <= int(bedrooms))
    return min(99, max(1, int(count_lte / total * 100)))


def build_suburb_comparison(value, suburb_median, suburb_name, percentile, feature_label, total_sample):
    """
    Build a suburbComparison dict for insertion into property_insights.
    The narrative is used by MarketContext on the frontend.
    """
    if percentile is None or suburb_median is None:
        return None

    ordinal = get_ordinal_suffix(int(percentile))
    if percentile >= 75:
        narrative = f"Above {int(percentile)}% of {feature_label} for {suburb_name} properties currently for sale"
    elif percentile >= 50:
        narrative = f"Above median for {suburb_name} ({ordinal} percentile)"
    elif percentile >= 25:
        narrative = f"Below median for {suburb_name} ({ordinal} percentile)"
    else:
        narrative = f"Below {100 - int(percentile)}% of {feature_label} for {suburb_name} properties currently for sale"

    return {
        'percentile': percentile,
        'suburbMedian': suburb_median,
        'suburbName': suburb_name,
        'narrative': narrative,
        'sampleSize': total_sample,
    }


def get_room_area(property_doc, room_keywords, fallback_largest_bedroom=False):
    """
    Extract room area from floor_plan_analysis.rooms structure.

    Args:
        property_doc: The property document
        room_keywords: List of keywords to match in room_name (e.g., ['kitchen'], ['master', 'king main'])
        fallback_largest_bedroom: If True and no keyword match, return area of the largest bedroom

    Returns:
        float: Room area in sqm, or None if not found
    """
    floor_plan = property_doc.get('floor_plan_analysis', {})
    rooms = floor_plan.get('rooms', [])

    for room in rooms:
        room_name = room.get('room_name', '').lower()
        room_type = room.get('room_type', '').lower()

        # Check if any keyword matches
        for keyword in room_keywords:
            if keyword.lower() in room_name or keyword.lower() in room_type:
                dimensions = room.get('dimensions', {})
                area = dimensions.get('area')
                if area and area > 0:
                    return area

    # Fallback: return the largest bedroom by area
    if fallback_largest_bedroom:
        largest_area = None
        for room in rooms:
            room_name = room.get('room_name', '').lower()
            room_type = room.get('room_type', '').lower()
            if 'bed' in room_name or room_type == 'bedroom':
                dimensions = room.get('dimensions', {})
                area = dimensions.get('area')
                if area and area > 0:
                    if largest_area is None or area > largest_area:
                        largest_area = area
        return largest_area

    return None


def _rank_among(property_doc, for_sale_properties, value, extract_fn):
    """Count how many other properties have a value greater than this one."""
    count = 0
    for p in for_sale_properties:
        if p.get('_id') == property_doc.get('_id'):
            continue
        p_val = extract_fn(p)
        if p_val and p_val > value:
            count += 1
    return count + 1


def calculate_rarity_insights(property_doc, suburb_stats, for_sale_properties):
    """
    Calculate what's unique about this property compared to what's currently for sale.
    Uses both rank-based (top N) and percentile-based (90th+) thresholds.

    Args:
        property_doc: The property document
        suburb_stats: Suburb statistics document
        for_sale_properties: List of all properties for sale in this suburb

    Returns:
        list: Array of rarity insight objects
    """
    insights = []
    suburb_stats_data = suburb_stats.get('statistics', {})
    suburb_display = suburb_stats.get('suburb', '').replace('_', ' ').title()
    total_for_sale = len(for_sale_properties)

    # KITCHEN SIZE RARITY
    kitchen_area = get_room_area(property_doc, ['kitchen'])

    if kitchen_area and kitchen_area > 0:
        larger_kitchens = []
        for p in for_sale_properties:
            if p.get('_id') == property_doc.get('_id'):
                continue
            p_kitchen_area = get_room_area(p, ['kitchen'])
            if p_kitchen_area and p_kitchen_area >= kitchen_area:
                larger_kitchens.append(p)

        if len(larger_kitchens) == 0:
            insights.append({
                'type': 'only_one',
                'feature': 'kitchen',
                'label': f"Only property with kitchen over {kitchen_area:.1f}m²",
                'urgencyLevel': 'high'
            })
        elif len(larger_kitchens) <= 2:
            rank = len(larger_kitchens) + 1
            insights.append({
                'type': 'top_n',
                'feature': 'kitchen',
                'rank': rank,
                'label': f"{get_ordinal_suffix(rank)} largest kitchen currently for sale",
                'urgencyLevel': 'medium'
            })

    # LOT SIZE RANKING
    enriched_data = property_doc.get('enriched_data') or {}
    lot_size = enriched_data.get('lot_size_sqm')

    # Also check floor_plan_analysis.total_land_area.value if enriched_data doesn't have it
    if not lot_size:
        fp = property_doc.get('floor_plan_analysis') or {}
        tla = fp.get('total_land_area') or {}
        if isinstance(tla, dict) and tla.get('value') and tla['value'] > 0:
            lot_size = tla['value']

    try:
        lot_size = float(lot_size) if lot_size else None
    except (TypeError, ValueError):
        lot_size = None
    if lot_size and lot_size > 0:
        def extract_lot(p):
            ed = p.get('enriched_data') or {}
            ls = ed.get('lot_size_sqm')
            try:
                ls = float(ls) if ls else None
            except (TypeError, ValueError):
                ls = None
            if ls and ls > 0:
                return ls
            fp = p.get('floor_plan_analysis') or {}
            tla = fp.get('total_land_area') or {}
            if isinstance(tla, dict) and tla.get('value'):
                try:
                    v = float(tla['value'])
                    if v > 0:
                        return v
                except (TypeError, ValueError):
                    pass
            return None

        rank = _rank_among(property_doc, for_sale_properties, lot_size, extract_lot)

        if rank == 1:
            insights.append({
                'type': 'only_one',
                'feature': 'lot_size',
                'label': f"Largest lot currently for sale ({lot_size:.0f}m²)",
                'urgencyLevel': 'high'
            })
        elif rank <= 5:
            insights.append({
                'type': 'top_n',
                'feature': 'lot_size',
                'rank': rank,
                'label': f"{get_ordinal_suffix(rank)} largest lot currently for sale",
                'urgencyLevel': 'medium' if rank <= 3 else 'low'
            })

    # FLOOR AREA RANKING
    floor_area = enriched_data.get('floor_area_sqm')

    try:
        floor_area = float(floor_area) if floor_area else None
    except (TypeError, ValueError):
        floor_area = None
    if floor_area and floor_area > 0:
        def extract_fa(p):
            ed = p.get('enriched_data') or {}
            v = ed.get('floor_area_sqm')
            try:
                v = float(v) if v else None
            except (TypeError, ValueError):
                v = None
            return v if v and v > 0 else None

        rank = _rank_among(property_doc, for_sale_properties, floor_area, extract_fa)

        if rank == 1:
            insights.append({
                'type': 'only_one',
                'feature': 'floor_area',
                'label': f"Largest floor area currently for sale ({floor_area:.0f}m²)",
                'urgencyLevel': 'high'
            })
        elif rank <= 5:
            insights.append({
                'type': 'top_n',
                'feature': 'floor_area',
                'rank': rank,
                'label': f"{get_ordinal_suffix(rank)} largest floor area for sale",
                'urgencyLevel': 'medium' if rank <= 3 else 'low'
            })

    # MASTER BEDROOM SIZE
    MASTER_KEYWORDS = ['master', 'main bed', 'main bedroom', 'primary', 'king main',
                       'bedroom 1', 'bed 1', 'bedroom 01', 'bed 01', 'sleeping 1']
    master_area = get_room_area(property_doc, MASTER_KEYWORDS, fallback_largest_bedroom=True)

    if master_area and master_area > 0:
        larger_masters = []
        for p in for_sale_properties:
            if p.get('_id') == property_doc.get('_id'):
                continue
            p_master_area = get_room_area(p, MASTER_KEYWORDS, fallback_largest_bedroom=True)
            if p_master_area and p_master_area >= master_area:
                larger_masters.append(p)

        if len(larger_masters) == 0:
            insights.append({
                'type': 'only_one',
                'feature': 'master_bedroom',
                'label': f"Only property with master bedroom over {master_area:.1f}m²",
                'urgencyLevel': 'high'
            })
        elif len(larger_masters) <= 2:
            rank = len(larger_masters) + 1
            insights.append({
                'type': 'top_n',
                'feature': 'master_bedroom',
                'rank': rank,
                'label': f"{get_ordinal_suffix(rank)} largest master bedroom for sale",
                'urgencyLevel': 'medium'
            })

    # PERCENTILE-BASED INSIGHTS — catch properties at 90th+ percentile that
    # miss the top-5 rank threshold (e.g. rank 11/44 but 96th suburb percentile)
    fa_stats = suburb_stats_data.get('floor_area', {})
    fa_percentile = compute_floor_area_percentile(floor_area, fa_stats) if floor_area else None

    if fa_percentile and fa_percentile >= 90:
        # Only add if no rank-based floor_area insight already exists
        has_fa_insight = any(i['feature'] == 'floor_area' for i in insights)
        if not has_fa_insight:
            fa_median = fa_stats.get('median')
            insights.append({
                'type': 'percentile',
                'feature': 'floor_area',
                'percentile': fa_percentile,
                'label': f"Larger than {fa_percentile}% of {suburb_display} properties ({floor_area:.0f}m² vs {fa_median:.0f}m² median)" if fa_median else f"Larger than {fa_percentile}% of {suburb_display} properties",
                'urgencyLevel': 'medium' if fa_percentile >= 95 else 'low'
            })

    bed_count = property_doc.get('bedrooms')
    bed_dist = suburb_stats_data.get('bedrooms', {}).get('distribution', {})
    bed_percentile = compute_bedroom_percentile(bed_count, bed_dist)

    if bed_percentile and bed_percentile >= 90:
        has_bed_insight = any(i['feature'] in ('bedrooms', 'master_bedroom') for i in insights)
        if not has_bed_insight:
            insights.append({
                'type': 'percentile',
                'feature': 'bedrooms',
                'percentile': bed_percentile,
                'label': f"More bedrooms than {bed_percentile}% of {suburb_display} properties ({bed_count} beds)",
                'urgencyLevel': 'low'
            })

    return insights


def calculate_property_insights() -> None:
    monitor = MonitorClient(
        system="orchestrator",
        pipeline="orchestrator_daily",
        process_id="15",
        process_name="Calculate Property Insights",
    )
    monitor.start()

    mongo_uri = os.getenv("COSMOS_CONNECTION_STRING") or os.getenv(
        "MONGODB_URI", "mongodb://localhost:27017/"
    )
    client = MongoClient(
        mongo_uri, retryWrites=False, tls=True, tlsAllowInvalidCertificates=True
    )
    db = client["Gold_Coast"]
    stats_collection = db["suburb_statistics"]

    processed = with_insights = errors = 0

    try:
        print("=" * 80)
        print("CALCULATE PROPERTY INSIGHTS — Guarded Run")
        print("=" * 80)
        print(f"Started at: {datetime.now():%Y-%m-%d %H:%M:%S}\n")

        all_cols = set(
            cosmos_retry(lambda: db.list_collection_names(), "list_collection_names")
        )
        suburb_names = [s for s in TARGET_SUBURBS if s in all_cols]
        if not suburb_names:
            raise EmptyWorkSetError("No target suburb collections available.")

        properties_by_suburb: Dict[str, List[Dict[str, Any]]] = {}
        for suburb in suburb_names:
            coll = db[suburb]
            docs = cosmos_retry(
                lambda c=coll: list(
                    c.find({"price": {"$exists": True, "$ne": None}})
                ),
                f"load_properties[{suburb}]",
                log=print,
            )
            if docs:
                properties_by_suburb[suburb] = docs

        total_candidates = sum(len(v) for v in properties_by_suburb.values())
        if total_candidates == 0:
            raise EmptyWorkSetError("No properties found for insights generation.")

        print(
            f"Found {total_candidates} properties across "
            f"{len(properties_by_suburb)} suburbs\n"
        )

        for idx, (suburb, suburb_properties) in enumerate(
            properties_by_suburb.items(), 1
        ):
            print(
                f"\n[{idx}/{len(properties_by_suburb)}] Processing {suburb} "
                f"({len(suburb_properties)} properties)"
            )
            suburb_coll = db[suburb]

            suburb_stats = cosmos_retry(
                lambda: stats_collection.find_one(
                    {"suburb": suburb, "property_type": "House"}
                ),
                f"load_suburb_stats[{suburb}]",
                log=print,
            ) or {"suburb": suburb, "statistics": {}}

            # Live fallbacks for distributions
            live_bed_dist: Dict[str, int] = {}
            live_bath_dist: Dict[str, int] = {}
            live_parking_dist: Dict[str, int] = {}

            for prop in suburb_properties:
                b = prop.get("bedrooms")
                if b and b > 0:
                    live_bed_dist[str(int(b))] = live_bed_dist.get(str(int(b)), 0) + 1
                ba = prop.get("bathrooms") or prop.get("baths")
                if ba and ba > 0:
                    live_bath_dist[str(int(ba))] = live_bath_dist.get(str(int(ba)), 0) + 1
                pk = prop.get("car_spaces") or prop.get("carspaces") or prop.get("parking")
                if pk and pk > 0:
                    live_parking_dist[str(int(pk))] = live_parking_dist.get(str(int(pk)), 0) + 1

            stats_data = suburb_stats.get("statistics", {})
            stats_data.setdefault("bedrooms", {}).setdefault(
                "distribution", live_bed_dist
            )
            stats_data.setdefault("bathrooms", {}).setdefault(
                "distribution", live_bath_dist
            )
            stats_data.setdefault("parking", {}).setdefault(
                "distribution", live_parking_dist
            )

            if live_bed_dist and not stats_data["bedrooms"].get("median"):
                vals = [
                    int(k) for k, v in live_bed_dist.items() for _ in range(v)
                ]
                vals.sort()
                stats_data["bedrooms"]["median"] = vals[len(vals) // 2] if vals else None

            if live_bath_dist and not stats_data["bathrooms"].get("median"):
                vals = [
                    int(k) for k, v in live_bath_dist.items() for _ in range(v)
                ]
                vals.sort()
                stats_data["bathrooms"]["median"] = vals[len(vals) // 2] if vals else None

            if live_parking_dist and not stats_data["parking"].get("median"):
                vals = [
                    int(k) for k, v in live_parking_dist.items() for _ in range(v)
                ]
                vals.sort()
                stats_data["parking"]["median"] = vals[len(vals) // 2] if vals else None

            suburb_stats["statistics"] = stats_data

            suburb_insights = 0

            # Only compute + write insights for active listings — historical
            # data is used above for distribution stats but doesn't need insight writes.
            # This reduces writes from ~26K to ~161, saving thousands of RU.
            active_properties = [
                p for p in suburb_properties
                if p.get("listing_status") == "for_sale"
            ]
            print(
                f"  Active for_sale: {len(active_properties)} / {len(suburb_properties)} total"
            )

            for prop in active_properties:
                processed += 1
                try:
                    rarity_insights = calculate_rarity_insights(
                        prop, suburb_stats, suburb_properties
                    )
                    enriched_data = prop.get("enriched_data") or {}
                    suburb_stats_data = suburb_stats.get("statistics", {})
                    suburb_display = suburb.replace("_", " ").title()
                    total_for_sale = (
                        suburb_stats.get("currently_for_sale", {}).get("total_count", 0)
                    )

                    bed_count = prop.get("bedrooms")
                    bed_dist = suburb_stats_data.get("bedrooms", {}).get(
                        "distribution", {}
                    )
                    bed_median = suburb_stats_data.get("bedrooms", {}).get("median")
                    bed_percentile = compute_bedroom_percentile(bed_count, bed_dist)
                    bed_comparison = build_suburb_comparison(
                        bed_count,
                        bed_median,
                        suburb_display,
                        bed_percentile,
                        "bedroom counts",
                        total_for_sale,
                    )

                    floor_area = enriched_data.get("floor_area_sqm")
                    fa_stats = suburb_stats_data.get("floor_area", {})
                    fa_median = fa_stats.get("median")
                    fa_percentile = compute_floor_area_percentile(floor_area, fa_stats)
                    fa_comparison = build_suburb_comparison(
                        floor_area,
                        fa_median,
                        suburb_display,
                        fa_percentile,
                        "floor areas",
                        total_for_sale,
                    )

                    bath_count = prop.get("bathrooms") or prop.get("baths")
                    bath_dist = suburb_stats_data.get("bathrooms", {}).get(
                        "distribution", {}
                    )
                    bath_median = suburb_stats_data.get("bathrooms", {}).get("median")
                    bath_percentile = (
                        compute_bedroom_percentile(bath_count, bath_dist)
                        if bath_count and bath_dist
                        else None
                    )
                    bath_comparison = (
                        build_suburb_comparison(
                            bath_count,
                            bath_median,
                            suburb_display,
                            bath_percentile,
                            "bathroom counts",
                            total_for_sale,
                        )
                        if bath_percentile
                        else None
                    )

                    parking_count = (
                        prop.get("car_spaces") or prop.get("carspaces") or prop.get("parking")
                    )
                    parking_dist = suburb_stats_data.get("parking", {}).get(
                        "distribution", {}
                    ) or suburb_stats_data.get("car_spaces", {}).get("distribution", {})
                    parking_median = suburb_stats_data.get("parking", {}).get(
                        "median"
                    ) or suburb_stats_data.get("car_spaces", {}).get("median")
                    parking_percentile = (
                        compute_bedroom_percentile(parking_count, parking_dist)
                        if parking_count and parking_dist
                        else None
                    )
                    parking_comparison = (
                        build_suburb_comparison(
                            parking_count,
                            parking_median,
                            suburb_display,
                            parking_percentile,
                            "parking spaces",
                            total_for_sale,
                        )
                        if parking_percentile
                        else None
                    )

                    lot_size_val = enriched_data.get("lot_size_sqm")
                    lot_rarity = [r for r in rarity_insights if r["feature"] == "lot_size"]

                    update_fields = {
                        "property_insights.bedrooms": {
                            "value": bed_count,
                            "rarity_insights": [
                                r
                                for r in rarity_insights
                                if r["feature"] in ["bedrooms", "master_bedroom"]
                            ],
                            **({"suburbComparison": bed_comparison} if bed_comparison else {}),
                        },
                        "property_insights.bathrooms": {
                            "value": bath_count,
                            "rarity_insights": [],
                            **({"suburbComparison": bath_comparison} if bath_comparison else {}),
                        },
                        "property_insights.parking": {
                            "value": parking_count,
                            "rarity_insights": [],
                            **({"suburbComparison": parking_comparison} if parking_comparison else {}),
                        },
                        "property_insights.floor_area": {
                            "value": floor_area,
                            "rarity_insights": [
                                r
                                for r in rarity_insights
                                if r["feature"] in ["floor_area", "kitchen", "living"]
                            ],
                            **({"suburbComparison": fa_comparison} if fa_comparison else {}),
                        },
                        "property_insights.lot_size.value": lot_size_val,
                        "property_insights.lot_size.rarity_insights": lot_rarity,
                        "property_insights_updated": datetime.utcnow(),
                    }

                    cosmos_retry(
                        lambda coll=suburb_coll, pid=prop["_id"], payload=update_fields: coll.update_one(
                            {"_id": pid}, {"$set": payload}
                        ),
                        f"update_property_insights[{suburb}]",
                        log=print,
                    )
                    sleep_with_jitter()

                    if rarity_insights:
                        with_insights += 1
                        suburb_insights += 1

                except Exception as exc:  # pylint: disable=broad-except
                    errors += 1
                    if errors <= 5:
                        print(f"  ✗ Error processing property: {exc}")

            print(
                f"  ✓ Processed {len(suburb_properties)} properties, "
                f"{suburb_insights} with unique insights"
            )

        error_ratio = errors / processed if processed else 1.0
        monitor.log_metric("properties_processed", processed)
        monitor.log_metric("properties_with_insights", with_insights)
        monitor.log_metric("errors", errors)
        monitor.log_metric("error_ratio", round(error_ratio, 4))

        if processed == 0:
            raise EmptyWorkSetError("No properties were processed.")

        if error_ratio > 0.05:
            raise RuntimeError(
                f"Error ratio {error_ratio:.2%} exceeds threshold; marking failure."
            )

        if errors:
            monitor.log_warning(
                f"{errors} properties failed ({error_ratio:.2%}); retry on next run."
            )

        monitor.finish(status="success")

        if with_insights:
            print("\nSample property with insights:")
            sample = None
            for suburb in suburb_names:
                sample = cosmos_retry(
                    lambda: db[suburb].find_one(
                        {
                            "property_insights.floor_area.rarity_insights": {
                                "$exists": True,
                                "$ne": [],
                            }
                        }
                    ),
                    f"sample[{suburb}]",
                    log=print,
                )
                if sample:
                    break
            if sample:
                print(f"  Address: {sample.get('address')}")
                insights = sample.get("property_insights", {})
                for stat_type in ["floor_area", "lot_size", "bedrooms"]:
                    if stat_type in insights and insights[stat_type].get("rarity_insights"):
                        print(f"\n  {stat_type.replace('_', ' ').title()}:")
                        for rarity in insights[stat_type]["rarity_insights"]:
                            print(f"    [{rarity['urgencyLevel'].upper()}] {rarity['label']}")

    except EmptyWorkSetError as exc:
        monitor.log_error(str(exc))
        monitor.finish(status="failed")
        raise
    except Exception as exc:  # pylint: disable=broad-except
        monitor.log_error(f"Unhandled error: {exc}")
        monitor.finish(status="failed")
        raise
    finally:
        client.close()


if __name__ == "__main__":
    calculate_property_insights()
