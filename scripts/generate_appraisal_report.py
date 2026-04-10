#!/usr/bin/env python3
"""
Generate Appraisal Report — Generalized for Any Gold Coast Suburb
=================================================================
Builds an 11-page branded PDF seller appraisal report from:
  - Dynamic comparable sales selection (any suburb)
  - Suburb-specific adjustment rates (from precompute_valuations)
  - AI-generated editorial content (Claude)
  - Dynamic room assessments, market stats, satellite data, POIs

Can be triggered by:
  - Pipeline: --pipeline-id <ObjectId>  (reads from appraisal_pipeline)
  - Manual:   --address X --client Y --suburb Z [--sell-timeline T]

Output: output/seller_reports/YYYY-MM-DD_<slug>_<client>_v2.pdf
"""
from __future__ import annotations

import argparse
import json
import os
import re
import subprocess
import sys
import tempfile
import urllib.request
from datetime import datetime, timezone, timedelta
from math import radians, cos, sin, asin, sqrt
from pathlib import Path
from typing import Any, Optional
from zoneinfo import ZoneInfo

from jinja2 import Environment, FileSystemLoader
from pymongo import MongoClient
from bson import ObjectId

AEST = ZoneInfo("Australia/Brisbane")
ROOT = Path("/home/fields/Fields_Orchestrator")
TEMPLATE_DIR = ROOT / "templates"
OUTPUT_DIR = ROOT / "output" / "seller_reports"

RESEARCH_STATS = "2,153 sold properties, 60+ studies, and 14 academic papers"
TOTAL_SOLD_TRACKED = "2,100+"

# ---------------------------------------------------------------------------
# Suburb adjustment rates (from precompute_valuations.py methodology)
# ---------------------------------------------------------------------------
SUBURB_ADJUSTMENT_RATES = {
    'Robina':          {'land_per_sqm': 500, 'floor_per_sqm': 2500, 'per_bedroom': 90000, 'per_bathroom': 65000, 'per_car_space': 40000, 'per_pool': 80000, 'per_storey': 50000, 'per_renovation_level': 60000, 'per_water_view': 150000, 'per_ac_ducted': 25000, 'per_kitchen_point': 15000, 'condition_pct_per_point': 0.05},
    'Mudgeeraba':      {'land_per_sqm': 375, 'floor_per_sqm': 2200, 'per_bedroom': 85000, 'per_bathroom': 57000, 'per_car_space': 35000, 'per_pool': 70000, 'per_storey': 45000, 'per_renovation_level': 55000, 'per_water_view': 120000, 'per_ac_ducted': 20000, 'per_kitchen_point': 12000, 'condition_pct_per_point': 0.05},
    'Varsity Lakes':   {'land_per_sqm': 550, 'floor_per_sqm': 2500, 'per_bedroom': 100000, 'per_bathroom': 65000, 'per_car_space': 40000, 'per_pool': 80000, 'per_storey': 50000, 'per_renovation_level': 60000, 'per_water_view': 180000, 'per_ac_ducted': 25000, 'per_kitchen_point': 15000, 'condition_pct_per_point': 0.05},
    'Burleigh Waters': {'land_per_sqm': 1000, 'floor_per_sqm': 3000, 'per_bedroom': 125000, 'per_bathroom': 85000, 'per_car_space': 45000, 'per_pool': 90000, 'per_storey': 60000, 'per_renovation_level': 80000, 'per_water_view': 250000, 'per_ac_ducted': 30000, 'per_kitchen_point': 20000, 'condition_pct_per_point': 0.05},
    'Merrimac':        {'land_per_sqm': 375, 'floor_per_sqm': 2000, 'per_bedroom': 75000, 'per_bathroom': 50000, 'per_car_space': 35000, 'per_pool': 65000, 'per_storey': 40000, 'per_renovation_level': 50000, 'per_water_view': 100000, 'per_ac_ducted': 18000, 'per_kitchen_point': 10000, 'condition_pct_per_point': 0.05},
    'Reedy Creek':     {'land_per_sqm': 275, 'floor_per_sqm': 2500, 'per_bedroom': 110000, 'per_bathroom': 75000, 'per_car_space': 40000, 'per_pool': 80000, 'per_storey': 50000, 'per_renovation_level': 65000, 'per_water_view': 130000, 'per_ac_ducted': 25000, 'per_kitchen_point': 15000, 'condition_pct_per_point': 0.05},
    'Worongary':       {'land_per_sqm': 225, 'floor_per_sqm': 2500, 'per_bedroom': 115000, 'per_bathroom': 80000, 'per_car_space': 40000, 'per_pool': 80000, 'per_storey': 50000, 'per_renovation_level': 65000, 'per_water_view': 130000, 'per_ac_ducted': 25000, 'per_kitchen_point': 15000, 'condition_pct_per_point': 0.05},
    'Carrara':         {'land_per_sqm': 400, 'floor_per_sqm': 2200, 'per_bedroom': 80000, 'per_bathroom': 55000, 'per_car_space': 35000, 'per_pool': 65000, 'per_storey': 40000, 'per_renovation_level': 50000, 'per_water_view': 100000, 'per_ac_ducted': 18000, 'per_kitchen_point': 10000, 'condition_pct_per_point': 0.05},
}
DEFAULT_RATES = {'land_per_sqm': 450, 'floor_per_sqm': 2500, 'per_bedroom': 85000, 'per_bathroom': 60000, 'per_car_space': 35000, 'per_pool': 75000, 'per_storey': 45000, 'per_renovation_level': 55000, 'per_water_view': 120000, 'per_ac_ducted': 20000, 'per_kitchen_point': 12000, 'condition_pct_per_point': 0.05}

RENO_LEVELS = {"original": 1, "partially_renovated": 2, "cosmetically_updated": 3, "fully_renovated": 4, "new_build": 5}


def fmt(n):
    return f"${n:,.0f}" if n else "$0"


def fmt_signed(n):
    return f"+${n:,.0f}" if n >= 0 else f"-${abs(n):,.0f}"


def get_db():
    conn = os.environ.get("COSMOS_CONNECTION_STRING")
    if not conn:
        sys.exit("[ERROR] COSMOS_CONNECTION_STRING not set")
    client = MongoClient(conn, retryReads=True, retryWrites=True)
    return client


def cosmos_retry(func, *args, max_retries=5, **kwargs):
    """Retry on Cosmos DB 16500 (TooManyRequests)."""
    import time
    from pymongo.errors import OperationFailure
    for attempt in range(max_retries):
        try:
            return func(*args, **kwargs)
        except OperationFailure as e:
            if e.code == 16500 and attempt < max_retries - 1:
                retry_ms = 1000
                try:
                    retry_ms = int(str(e).split("RetryAfterMs=")[1].split(",")[0])
                except Exception:
                    pass
                wait = max(retry_ms / 1000, 1) * (1.5 ** attempt)
                print(f"  [RU] Throttled, waiting {wait:.1f}s (attempt {attempt + 1})")
                time.sleep(wait)
            else:
                raise


def haversine_km(lat1, lon1, lat2, lon2):
    lat1, lon1, lat2, lon2 = map(radians, [lat1, lon1, lat2, lon2])
    dlat = lat2 - lat1
    dlon = lon2 - lon1
    a = sin(dlat / 2) ** 2 + cos(lat1) * cos(lat2) * sin(dlon / 2) ** 2
    return 6371 * 2 * asin(sqrt(a))


# ---------------------------------------------------------------------------
# Property lookup
# ---------------------------------------------------------------------------
def find_property(client, suburb: str, address: str):
    col = client["Gold_Coast"][suburb]
    for field in ["address", "complete_address", "street_address", "display_address"]:
        doc = cosmos_retry(col.find_one, {field: {"$regex": address, "$options": "i"}})
        if doc:
            return doc
    return None


# ---------------------------------------------------------------------------
# Dynamic comparable selection
# ---------------------------------------------------------------------------
def select_comps(client, suburb: str, subject: dict, max_comps: int = 5) -> list:
    """Find best comparable sold properties dynamically."""
    col = client["Gold_Coast"][suburb]
    s_beds = subject.get("bedrooms") or 3
    s_land = subject.get("land_size_sqm") or subject.get("lot_size_sqm") or 0
    s_lat = subject.get("latitude") or subject.get("lat")
    s_lon = subject.get("longitude") or subject.get("lng") or subject.get("lon")
    s_addr = (subject.get("address") or "").lower()
    s_is_unit = bool(re.match(r"^\d+/\d+", s_addr.strip()))

    # Get sold houses in last 18 months
    cutoff = (datetime.now(timezone.utc) - timedelta(days=548)).strftime("%Y-%m-%d")
    sold_query = {
        "listing_status": "sold",
        "property_type": {"$regex": "house", "$options": "i"},
    }
    sold_docs = cosmos_retry(lambda: list(col.find(sold_query)))

    candidates = []
    for doc in sold_docs:
        # Filter: sold date must be recent
        sold_date = str(doc.get("sold_date", ""))
        if sold_date < cutoff:
            continue

        # Filter: bedroom band ±1
        c_beds = doc.get("bedrooms")
        if c_beds is None or abs(c_beds - s_beds) > 1:
            continue

        # Filter: don't mix units and houses
        c_addr = (doc.get("address") or "").lower()
        c_is_unit = bool(re.match(r"^\d+/\d+", c_addr.strip()))
        if s_is_unit != c_is_unit:
            continue

        # Filter: don't mix acreage with suburban
        c_land = doc.get("land_size_sqm") or doc.get("lot_size_sqm") or 0
        s_is_acreage = float(s_land) > 5000 if s_land else False
        c_is_acreage = float(c_land) > 5000 if c_land else False
        if s_is_acreage != c_is_acreage:
            continue

        # Must have a sold price
        price = _parse_price(doc.get("sold_price") or doc.get("sale_price") or doc.get("last_sold_price"))
        if not price:
            continue

        # Score: proximity + recency + bedroom match + data quality
        score = 0.0

        # Proximity (max 30 points)
        if s_lat and s_lon:
            c_lat = doc.get("latitude") or doc.get("lat")
            c_lon = doc.get("longitude") or doc.get("lng") or doc.get("lon")
            if c_lat and c_lon:
                dist = haversine_km(float(s_lat), float(s_lon), float(c_lat), float(c_lon))
                score += max(0, 30 - dist * 15)  # Within 2km = 0 penalty

        # Recency (max 25 points)
        try:
            days_ago = (datetime.now(timezone.utc) - datetime.fromisoformat(sold_date.replace("Z", "+00:00"))).days
        except Exception:
            days_ago = 365
        score += max(0, 25 - days_ago / 15)

        # Bedroom match (max 20 points)
        score += 20 if c_beds == s_beds else 10

        # Data quality — has photo analysis (max 15 points)
        pvd = doc.get("property_valuation_data", {})
        if pvd:
            score += 10
        if doc.get("floor_plan_analysis"):
            score += 5

        # Land size similarity (max 10 points)
        if s_land and c_land:
            land_ratio = min(float(s_land), float(c_land)) / max(float(s_land), float(c_land))
            score += land_ratio * 10

        candidates.append((score, price, doc))

    # Sort by score descending, take top N
    candidates.sort(key=lambda x: x[0], reverse=True)
    return [doc for _, _, doc in candidates[:max_comps]]


def _parse_price(val) -> Optional[float]:
    if isinstance(val, (int, float)):
        return float(val) if val > 0 else None
    if not isinstance(val, str):
        return None
    cleaned = re.sub(r"[$,\s]", "", val)
    m = re.match(r"^(\d+\.?\d*)m$", cleaned, re.IGNORECASE)
    if m:
        return float(m.group(1)) * 1_000_000
    try:
        n = float(cleaned)
        return n if n > 0 else None
    except ValueError:
        return None


# ---------------------------------------------------------------------------
# Adjustments
# ---------------------------------------------------------------------------
def get_rates(suburb_display: str) -> dict:
    """Get adjustment rates for a suburb."""
    # Try exact match, then title case, then lowercase
    for key in [suburb_display, suburb_display.title(), suburb_display.replace("_", " ").title()]:
        if key in SUBURB_ADJUSTMENT_RATES:
            return SUBURB_ADJUSTMENT_RATES[key]
    return DEFAULT_RATES


def compute_adjustments(subject: dict, comp: dict, rates: dict) -> list[dict]:
    """Compute line-by-line adjustments from comp to subject."""
    R = rates
    adjs = []

    def add(label, subj_val, comp_val, rate, unit=""):
        if subj_val is None or comp_val is None:
            return
        diff = subj_val - comp_val
        if abs(diff) < 0.01:
            return
        value = int(diff * rate)
        if unit:
            diff_str = f"{diff:+.0f} {unit}"
        else:
            diff_str = f"{diff:+.0f}"
        adjs.append({"label": label, "diff": diff_str, "value": value, "display": fmt_signed(value)})

    s_pvd = subject.get("property_valuation_data", {})
    c_pvd = comp.get("property_valuation_data", {})
    s_fpa = subject.get("floor_plan_analysis", {})
    c_fpa = comp.get("floor_plan_analysis", {})

    # Land
    s_land = subject.get("land_size_sqm") or subject.get("lot_size_sqm")
    c_land = comp.get("land_size_sqm") or comp.get("lot_size_sqm")
    if s_land and c_land:
        add("Land area", float(s_land), float(c_land), R["land_per_sqm"], "m\u00b2")

    # Floor area
    s_floor = s_fpa.get("internal_floor_area", {}).get("value") or subject.get("floor_area_sqm")
    c_floor = c_fpa.get("internal_floor_area", {}).get("value") or comp.get("floor_area_sqm")
    if s_floor and c_floor:
        add("Internal floor area", float(s_floor), float(c_floor), R["floor_per_sqm"], "m\u00b2")

    # Beds / Baths / Cars
    s_beds = subject.get("bedrooms")
    c_beds = comp.get("bedrooms")
    add("Bedrooms", s_beds, c_beds, R["per_bedroom"])
    add("Bathrooms", subject.get("bathrooms"), comp.get("bathrooms"), R["per_bathroom"])
    add("Car spaces", subject.get("car_spaces") or subject.get("carspaces"), comp.get("car_spaces") or comp.get("carspaces"), R["per_car_space"])

    # Pool
    s_pool = 1 if s_pvd.get("outdoor", {}).get("pool_present") else 0
    c_pool = 1 if c_pvd.get("outdoor", {}).get("pool_present") else 0
    if s_pool != c_pool:
        adjs.append({"label": "Pool", "diff": f"{s_pool - c_pool:+d}", "value": (s_pool - c_pool) * R["per_pool"], "display": fmt_signed((s_pool - c_pool) * R["per_pool"])})

    # Storey
    s_st = s_pvd.get("property_overview", {}).get("number_of_stories") or 1
    c_st = c_pvd.get("property_overview", {}).get("number_of_stories") or 1
    add("Storeys", min(s_st, 3), min(c_st, 3), R["per_storey"])

    # Renovation level
    s_reno = RENO_LEVELS.get(s_pvd.get("renovation", {}).get("overall_renovation_level"), 3)
    c_reno = RENO_LEVELS.get(c_pvd.get("renovation", {}).get("overall_renovation_level"), 3)
    add("Renovation level", s_reno, c_reno, R["per_renovation_level"])

    # Water views
    s_water = 1 if s_pvd.get("outdoor", {}).get("water_views") else 0
    c_water = 1 if c_pvd.get("outdoor", {}).get("water_views") else 0
    if s_water != c_water:
        adjs.append({"label": "Water views", "diff": f"{s_water - c_water:+d}", "value": (s_water - c_water) * R["per_water_view"], "display": fmt_signed((s_water - c_water) * R["per_water_view"])})

    # AC
    s_ac_type = s_pvd.get("property_metadata", {}).get("air_conditioning", "")
    c_ac_type = c_pvd.get("property_metadata", {}).get("air_conditioning", "")
    s_ac = 1 if s_ac_type == "ducted" else 0
    c_ac = 1 if c_ac_type == "ducted" else 0
    if s_ac != c_ac:
        adjs.append({"label": "Ducted AC", "diff": f"{s_ac - c_ac:+d}", "value": (s_ac - c_ac) * R["per_ac_ducted"], "display": fmt_signed((s_ac - c_ac) * R["per_ac_ducted"])})

    # Kitchen
    s_kit = s_pvd.get("kitchen", {}).get("quality_score")
    c_kit = c_pvd.get("kitchen", {}).get("quality_score")
    add("Kitchen quality", s_kit, c_kit, R["per_kitchen_point"])

    # Condition (percentage-based)
    s_cond = s_pvd.get("property_overview", {}).get("overall_condition_score")
    c_cond = c_pvd.get("property_overview", {}).get("overall_condition_score")
    if s_cond and c_cond and s_cond != c_cond:
        comp_price = _parse_price(comp.get("sold_price") or comp.get("sale_price") or comp.get("last_sold_price")) or 0
        diff_pts = s_cond - c_cond
        pct = R.get("condition_pct_per_point", 0.05)
        val = int(diff_pts * pct * comp_price)
        adjs.append({"label": "Overall condition", "diff": f"{diff_pts:+.0f} pts", "value": val, "display": fmt_signed(val)})

    return adjs


def time_adjust(sold_date_val, monthly_rate: float = 0.005) -> float:
    """Time adjustment multiplier: 0.5%/month appreciation."""
    try:
        if isinstance(sold_date_val, datetime):
            sold = sold_date_val
        else:
            sold = datetime.fromisoformat(str(sold_date_val).replace("Z", "+00:00"))
        # Ensure timezone-aware
        if sold.tzinfo is None:
            sold = sold.replace(tzinfo=timezone.utc)
        months = (datetime.now(timezone.utc) - sold).days / 30.44
        return 1 + months * monthly_rate
    except Exception:
        return 1.0


def build_top_comps(subject: dict, comp_docs: list[dict], rates: dict) -> list[dict]:
    cards = []
    for doc in comp_docs:
        sold_price = _parse_price(doc.get("sold_price") or doc.get("sale_price") or doc.get("last_sold_price"))
        if not sold_price:
            continue
        sold_date = str(doc.get("sold_date", ""))
        adjs = compute_adjustments(subject, doc, rates)
        total_adj = sum(a["value"] for a in adjs)
        time_mult = time_adjust(sold_date)
        adjusted = int((sold_price + total_adj) * time_mult)
        addr = doc.get("display_address") or doc.get("complete_address") or doc.get("address") or "?"
        # Clean up address for display
        for suffix in [" QLD ", " Qld "]:
            if suffix in addr:
                addr = addr.split(suffix)[0]

        cards.append({
            "address": addr,
            "sold_display": fmt(sold_price),
            "sold_price": sold_price,
            "date": sold_date[:10] if sold_date else "?",
            "beds": doc.get("bedrooms", "?"),
            "baths": doc.get("bathrooms", "?"),
            "land": doc.get("land_size_sqm") or doc.get("lot_size_sqm") or "?",
            "adjustments": adjs,
            "total_adj": total_adj,
            "total_adj_display": fmt_signed(total_adj),
            "time_factor": f"{time_mult:.3f}",
            "adjusted_total": adjusted,
            "adjusted_total_display": fmt(adjusted),
        })
    cards.sort(key=lambda c: c["adjusted_total"])
    return cards


# ---------------------------------------------------------------------------
# Room assessments (fully dynamic from property_valuation_data)
# ---------------------------------------------------------------------------
def build_room_assessments(pvd: dict) -> list[dict]:
    rooms = []
    mapping = [
        ("Kitchen", "kitchen", ["quality_score", "benchtop_material", "age_description"]),
        ("Bathrooms", "bathrooms", ["quality_score", "fixtures_quality", "age_description"]),
        ("Living Areas", "living_areas", ["quality_score", "flooring_material", "natural_light"]),
        ("Master Bedroom", "master_bedroom", ["quality_score", "ensuite_quality", "walk_in_robe"]),
        ("Exterior", "exterior", ["cladding_material", "roof_condition", "overall_facade_score"]),
        ("Outdoor", "outdoor", ["pool_present", "entertaining_area_sqm", "landscaping_quality"]),
    ]
    for label, key, fields in mapping:
        data = pvd.get(key, {})
        if not data or isinstance(data, list):
            continue
        score = data.get("quality_score") or data.get("overall_facade_score") or data.get("overall_condition_score")
        details = []
        for f in fields:
            v = data.get(f)
            if v is not None and f != "quality_score":
                details.append(f"{f.replace('_', ' ').title()}: {v}")
        rooms.append({"name": label, "score": score, "details": details})
    return rooms


# ---------------------------------------------------------------------------
# Market stats
# ---------------------------------------------------------------------------
def get_market_stats(client, suburb):
    col = client["Gold_Coast"][suburb]
    for_sale = cosmos_retry(col.count_documents, {"listing_status": "for_sale"})
    sold = cosmos_retry(lambda: list(col.find({"listing_status": "sold", "property_type": {"$regex": "house", "$options": "i"}})))
    cutoff = (datetime.now(timezone.utc) - timedelta(days=365)).strftime("%Y-%m-%d")
    prices = []
    for s in sold:
        date = str(s.get("sold_date", ""))
        if date < cutoff:
            continue
        p = _parse_price(s.get("sold_price") or s.get("sale_price") or s.get("last_sold_price"))
        if p:
            prices.append(int(p))
    median = sorted(prices)[len(prices) // 2] if prices else 0
    return {"median": fmt(median), "houses_sold_12m": str(len(prices)), "currently_listed": str(for_sale)}


# ---------------------------------------------------------------------------
# AI-generated editorial content (Claude)
# ---------------------------------------------------------------------------
def generate_editorial(prop: dict, top_comps: list, market_stats: dict, rates: dict, suburb: str) -> dict:
    """Generate ALL editorial content via Claude — headline, verdict, value equations, buyer profiles, positioning."""
    try:
        import anthropic
    except ImportError:
        print("  [WARN] anthropic not installed, using minimal editorial")
        return _minimal_editorial(prop, top_comps, market_stats)

    api_key = os.environ.get("ANTHROPIC_API_KEY")
    if not api_key:
        print("  [WARN] ANTHROPIC_API_KEY not set, using minimal editorial")
        return _minimal_editorial(prop, top_comps, market_stats)

    client = anthropic.Anthropic(api_key=api_key)

    # Build property summary
    pvd = prop.get("property_valuation_data", {})
    fpa = prop.get("floor_plan_analysis", {})
    beds = prop.get("bedrooms", "?")
    baths = prop.get("bathrooms", "?")
    cars = prop.get("car_spaces") or prop.get("carspaces") or "?"
    land = prop.get("land_size_sqm") or prop.get("lot_size_sqm") or "?"
    floor_area = fpa.get("internal_floor_area", {}).get("value") or prop.get("floor_area_sqm") or "?"
    condition = pvd.get("property_overview", {}).get("overall_condition_score") or "?"
    pool = "yes" if pvd.get("outdoor", {}).get("pool_present") else "no"
    stories = pvd.get("property_overview", {}).get("number_of_stories") or 1
    reno = pvd.get("renovation", {}).get("overall_renovation_level") or "unknown"
    kitchen = pvd.get("kitchen", {}).get("benchtop_material") or "unknown"
    ac = pvd.get("property_metadata", {}).get("air_conditioning") or "unknown"
    address = prop.get("complete_address") or prop.get("address") or "?"

    # Build comp summary
    comp_text = "\n".join([
        f"  - {c['address']}: sold {c['sold_display']} ({c['date']}), adjusted to {c['adjusted_total_display']} for subject"
        for c in top_comps
    ])

    # Adjusted prices for valuation range
    adj_prices = [c["adjusted_total"] for c in top_comps if c.get("adjusted_total")]
    val_low = min(adj_prices) if adj_prices else 0
    val_high = max(adj_prices) if adj_prices else 0
    val_mid = int(sum(adj_prices) / len(adj_prices)) if adj_prices else 0

    # Nearby POIs for context
    pois = prop.get("nearby_pois", {}).get("by_category", {})
    schools = [s["name"] for s in pois.get("primary_school", [])[:2]]
    poi_text = f"Nearby schools: {', '.join(schools)}" if schools else "No nearby schools data"

    # Scarcity data
    scarcity_text = f"{beds}-bedroom homes in {suburb}"

    prompt = f"""You are the Fields Estate editorial team. Generate ALL editorial content for a seller appraisal report.

PROPERTY: {address}
{beds} bedrooms, {baths} bathrooms, {cars} car spaces.
{land} sqm land, {floor_area} sqm internal, {stories}-storey, condition {condition}/10.
Pool: {pool}. Renovation: {reno}. Kitchen: {kitchen}. AC: {ac}.
{poi_text}

COMPARABLE ADJUSTMENTS (used to derive valuation):
{comp_text}

VALUATION RANGE: {fmt(val_low)} to {fmt(val_high)} (mid-point {fmt(val_mid)})

MARKET: {suburb} median {market_stats['median']}. {market_stats['houses_sold_12m']} houses sold in 12m. {market_stats['currently_listed']} currently listed.

RULES (MANDATORY):
- Frame as "we would" not "you should". No advice language. No "you should sell/buy/consider".
- No forbidden words: stunning, nestled, boasting, rare opportunity, robust market.
- Be specific — cite the data (comparable addresses, prices, percentages).
- Price format: $1,250,000 not $1.25m. Suburbs always capitalised.
- Every trade-off is value, not a flaw. A seller should read this and feel their property is positioned honestly.
- No predictions: use conditional language ("if X, data suggests Y").

Return JSON with these keys:

{{
  "headline": "One sentence: what the data shows about this property's position (cite median, comp range)",
  "sub_headline": "One sentence: key differentiators and scarcity statement",
  "verdict": "3-4 sentences: valuation range with evidence, recommended listing range, primary value drivers. Cite specific comp addresses and adjusted prices.",
  "strengths": ["3-4 bullet points: specific features with dollar impacts from the adjustment data"],
  "trade_off": "One sentence: the main trade-off, framed as value (not a flaw)",
  "value_equations": [
    {{"title": "Feature name", "body": "2-3 sentences explaining what the data shows about this feature's value impact. Cite specific comparables.", "reframe": "One sentence reframing any negative as value", "positive": true}}
  ],
  "buyer_profiles": [
    {{"name": "Profile name", "description": "2 sentences: who this buyer is and why this property fits them"}}
  ],
  "scarcity_count": "Number of similar properties that sold in 12 months (e.g. '5')",
  "scarcity_statement": "One sentence about scarcity (e.g. 'five-bedroom homes sold in {suburb} in 12 months')",
  "lifestyle_narrative": "2-3 sentences: the lifestyle this property offers, grounded in data (proximity to schools, parks, etc.)",
  "pricing_cards": [
    {{"label": "Strategy name", "range": "$X - $Y", "rationale": "1-2 sentences citing comparable evidence"}}
  ],
  "feature_positioning": [
    {{"feature": "Feature name", "impact": "$XX,XXX", "strategy": "How to leverage this in marketing"}}
  ],
  "campaign_structure": "2-3 sentences: recommended campaign approach",
  "photography_strategy": "2 sentences: what to photograph and why",
  "open_home_strategy": "2 sentences: approach to inspections"
}}

Generate 5-7 value_equations, 3 buyer_profiles, 3-4 pricing_cards, and 4-6 feature_positioning items.
Return ONLY valid JSON."""

    try:
        resp = client.messages.create(
            model="claude-sonnet-4-20250514",
            max_tokens=4000,
            messages=[{"role": "user", "content": prompt}],
        )
        text = resp.content[0].text.strip()
        if text.startswith("```"):
            text = re.sub(r"^```\w*\n?", "", text)
            text = re.sub(r"\n?```$", "", text)
        editorial = json.loads(text)
        print("  Claude editorial generated successfully")
        return editorial
    except Exception as e:
        print(f"  [WARN] Claude editorial failed: {e}")
        return _minimal_editorial(prop, top_comps, market_stats)


def _minimal_editorial(prop: dict, top_comps: list, market_stats: dict) -> dict:
    """Fallback when Claude is unavailable — data-only, no prose."""
    adj_prices = [c["adjusted_total"] for c in top_comps if c.get("adjusted_total")]
    val_low = min(adj_prices) if adj_prices else 0
    val_high = max(adj_prices) if adj_prices else 0
    beds = prop.get("bedrooms", "?")
    suburb = prop.get("suburb", "?")

    return {
        "headline": f"Based on {len(top_comps)} adjusted comparable sales, this property sits above the {suburb} median of {market_stats['median']}",
        "sub_headline": f"A {beds}-bedroom property with adjusted comparable range of {fmt(val_low)} to {fmt(val_high)}",
        "verdict": f"Based on {len(top_comps)} adjusted comparable sales ranging from {fmt(val_low)} to {fmt(val_high)}, this property's estimated selling range is {fmt(val_low)} to {fmt(val_high)}, subject to property analyst inspection.",
        "strengths": [f"Adjusted comparable range: {fmt(val_low)} to {fmt(val_high)}"],
        "trade_off": "Refer to detailed comparable analysis for specific adjustments",
        "value_equations": [],
        "buyer_profiles": [{"name": "Target buyer", "description": f"Buyers seeking a {beds}-bedroom property in {suburb}"}],
        "scarcity_count": market_stats.get("houses_sold_12m", "?"),
        "scarcity_statement": f"houses sold in {suburb} in the last 12 months",
        "lifestyle_narrative": "",
        "pricing_cards": [{"label": "Comparable Range", "range": f"{fmt(val_low)} \u2013 {fmt(val_high)}", "rationale": f"Based on {len(top_comps)} adjusted comparable sales"}],
        "feature_positioning": [],
        "campaign_structure": "",
        "photography_strategy": "",
        "open_home_strategy": "",
    }


# ---------------------------------------------------------------------------
# Photo download
# ---------------------------------------------------------------------------
def download_photos(prop: dict, work_dir: Path) -> dict:
    photos_dir = work_dir / "photos"
    photos_dir.mkdir(exist_ok=True)
    images = prop.get("property_images", [])
    paths = {}

    # Dynamic: take first available for each role
    # Hero = first image, kitchen = try index 3, living = try index 7, aerial = try index 2
    roles = [
        ("hero", [0, 1]),
        ("exterior", [1, 0]),
        ("kitchen", [3, 4, 2]),
        ("living", [7, 6, 5]),
        ("aerial", [2, 8, 9]),
        ("pool", [1, 0, 4]),
    ]
    for name, indices in roles:
        found = False
        for idx in indices:
            if idx < len(images):
                local = photos_dir / f"{name}.jpg"
                try:
                    urllib.request.urlretrieve(images[idx], str(local))
                    paths[name] = str(local)
                    found = True
                    break
                except Exception:
                    continue
        if not found:
            paths[name] = ""
    return paths


# ---------------------------------------------------------------------------
# Seasonality
# ---------------------------------------------------------------------------
def build_seasonality_section(sell_timeline: str, suburb: str) -> str:
    now = datetime.now(AEST)
    if sell_timeline in ("3-6months", "3-6 months"):
        start_month = now.month + 3
        end_month = now.month + 6
        return (
            f"A 3\u20136 month timeline places your likely listing window in the second half of the year. "
            f"Our analysis of 13,585 Gold Coast sales (2020\u20132025) shows the second half consistently "
            f"outperforms the first half on price. September and October are historically strong months \u2014 "
            f"buyer activity increases post-winter. Our research shows properties priced correctly from "
            f"day one and selling within 15\u201321 days achieve the highest final prices "
            f"(from analysis of 44,937 Gold Coast sales)."
        )
    elif sell_timeline in ("1-3months", "1-3 months"):
        return (
            f"A 1\u20133 month timeline means listing soon. May is historically the fastest-selling month "
            f"across the Gold Coast corridor. While winter months see slightly lower buyer volumes, "
            f"serious buyers remain active and competition from other sellers drops. Our research shows "
            f"properties priced correctly from day one and selling within 15\u201321 days achieve the highest prices."
        )
    elif sell_timeline == "asap":
        return (
            f"For an immediate listing, current market conditions show balanced activity in {suburb}. "
            f"Our research across 44,937 sales shows properties priced correctly from day one and "
            f"selling within 15\u201321 days achieve the highest final prices. Speed of preparation is key."
        )
    return (
        f"Our analysis of 13,585 Gold Coast sales (2020\u20132025) shows the second half of the year "
        f"consistently outperforms the first half on price. Timing your listing to align with "
        f"buyer activity peaks \u2014 typically September\u2013November \u2014 can improve both sale price and days on market."
    )


# ---------------------------------------------------------------------------
# POI builder
# ---------------------------------------------------------------------------
def build_key_pois(prop: dict) -> list[dict]:
    pois = prop.get("nearby_pois", {}).get("by_category", {})
    key = []
    for school in pois.get("primary_school", [])[:2]:
        key.append({"name": school["name"], "category": "School (K-12)", "distance": f"{school['distance_m']}m walk"})
    for s in pois.get("park", [])[:2]:
        key.append({"name": s["name"], "category": "Park / Reserve", "distance": f"{s['distance_m']}m"})
    for s in pois.get("cafe", [])[:1]:
        key.append({"name": s["name"], "category": "Cafe", "distance": f"{s['distance_m']}m"})
    for s in pois.get("supermarket", [])[:1]:
        key.append({"name": s["name"], "category": "Supermarket", "distance": f"{s['distance_m']}m"})
    for s in pois.get("childcare", [])[:1]:
        key.append({"name": s["name"], "category": "Childcare", "distance": f"{s['distance_m']}m"})
    for s in pois.get("secondary_school", [])[:1]:
        if s["name"] not in [p["name"] for p in key]:
            key.append({"name": s["name"], "category": "Secondary School", "distance": f"{s['distance_m']}m"})
    return key[:8]


# ---------------------------------------------------------------------------
# Satellite label formatter
# ---------------------------------------------------------------------------
def _fmt_sat_label(val: str) -> str:
    if not val:
        return ""
    return val.replace("_", " ").title()


# ---------------------------------------------------------------------------
# HTML rendering
# ---------------------------------------------------------------------------
def render_html(prop, client_name, top_comps, room_assessments, editorial,
                market_stats, photo_paths, suburb_display: str,
                sell_timeline: str = "", sell_timeline_label: str = "") -> str:
    env = Environment(loader=FileSystemLoader(str(TEMPLATE_DIR)))
    template = env.get_template("seller_report_v2.html")

    pvd = prop.get("property_valuation_data", {})
    fpa = prop.get("floor_plan_analysis", {})

    # Derive valuation ranges from comps
    adj_prices = [c["adjusted_total"] for c in top_comps if c.get("adjusted_total")]
    val_low = min(adj_prices) if adj_prices else 0
    val_high = max(adj_prices) if adj_prices else 0
    # Listing range: tighten by ~5%
    listing_low = int(val_low * 1.02) if val_low else 0
    listing_high = int(val_high * 0.95) if val_high else 0
    if listing_high < listing_low:
        listing_low, listing_high = listing_high, listing_low

    context = {
        "client_name": client_name,
        "report_date": datetime.now(AEST).strftime("%d %B %Y"),
        "street_address": prop.get("street_address") or prop.get("address", ""),
        "suburb": suburb_display,
        "postcode": prop.get("postcode", ""),
        "bedrooms": prop.get("bedrooms", "?"),
        "bathrooms": prop.get("bathrooms", "?"),
        "land_size": int(float(prop.get("land_size_sqm") or prop.get("lot_size_sqm") or 0)),
        "internal_area": fpa.get("internal_floor_area", {}).get("value") or prop.get("floor_area_sqm") or "?",
        "condition_score": pvd.get("property_overview", {}).get("overall_condition_score") or "?",
        # Valuation ranges (derived from comps)
        "selling_range_low": fmt(val_low),
        "selling_range_high": fmt(val_high),
        "listing_range_low": fmt(listing_low),
        "listing_range_high": fmt(listing_high),
        # Fields Take (from Claude editorial)
        "headline": editorial.get("headline", ""),
        "sub_headline": editorial.get("sub_headline", ""),
        "verdict": editorial.get("verdict", ""),
        "strengths": editorial.get("strengths", []),
        "trade_off": editorial.get("trade_off", ""),
        # Comps
        "top_comps": top_comps,
        "adj_sample_size": market_stats.get("houses_sold_12m", "?"),
        # Room assessments
        "room_assessments": room_assessments,
        # Value equations
        "value_equations": editorial.get("value_equations", []),
        # Buyer profiles
        "buyer_profiles": editorial.get("buyer_profiles", []),
        "not_ideal_for": [],
        "scarcity_count": editorial.get("scarcity_count", "?"),
        "scarcity_statement": editorial.get("scarcity_statement", ""),
        # Market
        "suburb_median": market_stats.get("median", "N/A"),
        "houses_sold_12m": market_stats.get("houses_sold_12m", "?"),
        "currently_listed": market_stats.get("currently_listed", "?"),
        # Positioning
        "lifestyle_narrative": editorial.get("lifestyle_narrative", ""),
        "pricing_cards": editorial.get("pricing_cards", []),
        "feature_positioning": editorial.get("feature_positioning", []),
        "campaign_structure": editorial.get("campaign_structure", ""),
        "photography_strategy": editorial.get("photography_strategy", ""),
        "open_home_strategy": editorial.get("open_home_strategy", ""),
        "research_stats": RESEARCH_STATS,
        "total_sold_tracked": TOTAL_SOLD_TRACKED,
        # Photos
        "hero_photo": f"file://{photo_paths.get('hero', '')}",
        "exterior_photo": f"file://{photo_paths.get('exterior', '')}",
        "kitchen_photo": f"file://{photo_paths.get('kitchen', '')}",
        "living_photo": f"file://{photo_paths.get('living', '')}",
        "aerial_photo": f"file://{photo_paths.get('aerial', '')}",
        "pool_photo": f"file://{photo_paths.get('pool', '')}",
        "logo_path": f"file://{TEMPLATE_DIR / 'fields-logo-transparent.png'}",
        "logo_white_path": f"file://{TEMPLATE_DIR / 'fields-logo-white.png'}",
        # Satellite analysis
        "satellite_image_url": prop.get("satellite_analysis", {}).get("satellite_image_url", ""),
        "sat_green_space": _fmt_sat_label(prop.get("satellite_analysis", {}).get("categories", {}).get("amenity_premiums", {}).get("green_space_proximity", "")),
        "sat_frontage": _fmt_sat_label(prop.get("satellite_analysis", {}).get("categories", {}).get("adjacency", {}).get("frontage", "")),
        "sat_overall_setting": prop.get("satellite_analysis", {}).get("narrative", {}).get("overall_setting", ""),
        "sat_road_proximity": prop.get("satellite_analysis", {}).get("narrative", {}).get("road_proximity", ""),
        # POI data
        "key_pois": build_key_pois(prop),
        # Seasonality
        "sell_timeline_label": sell_timeline_label,
        "sell_window": "",
        "seasonality_section": build_seasonality_section(sell_timeline, suburb_display),
    }

    return template.render(**context)


# ---------------------------------------------------------------------------
# HTML to PDF
# ---------------------------------------------------------------------------
def html_to_pdf(html_path: str, pdf_path: str) -> bool:
    for chrome in ["google-chrome", "chromium-browser", "chromium"]:
        try:
            subprocess.run([chrome, "--version"], capture_output=True, check=True)
            break
        except (subprocess.CalledProcessError, FileNotFoundError):
            chrome = None
    if not chrome:
        return False

    cmd = [chrome, "--headless", "--disable-gpu", "--no-sandbox", "--disable-software-rasterizer",
           f"--print-to-pdf={pdf_path}", "--print-to-pdf-no-header",
           "--run-all-compositor-stages-before-draw", "--virtual-time-budget=5000",
           f"file://{html_path}"]
    result = subprocess.run(cmd, capture_output=True, text=True, timeout=60)
    return result.returncode == 0


# ---------------------------------------------------------------------------
# Pipeline integration
# ---------------------------------------------------------------------------
def update_pipeline(pipeline_id: str, stage: str, report_path: str = None):
    """Update appraisal_pipeline document."""
    try:
        client = get_db()
        db = client["system_monitor"]
        now = datetime.now(timezone.utc)
        update = {
            "$set": {"stage": stage, "updated_at": now},
            "$push": {"stage_history": {"stage": stage, "at": now.isoformat()}},
        }
        if report_path:
            update["$set"]["report_path"] = report_path
        db["appraisal_pipeline"].update_one({"_id": ObjectId(pipeline_id)}, update)
        print(f"  Pipeline {pipeline_id} → {stage}")
    except Exception as e:
        print(f"  [WARN] Pipeline update failed: {e}")


def notify_telegram(message: str):
    """Send Telegram notification."""
    try:
        import requests
        token = os.environ.get("TELEGRAM_BOT_TOKEN")
        chat_id = os.environ.get("TELEGRAM_CHAT_ID")
        if token and chat_id:
            requests.post(f"https://api.telegram.org/bot{token}/sendMessage",
                          json={"chat_id": chat_id, "text": message}, timeout=10)
    except Exception:
        pass


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------
def main():
    parser = argparse.ArgumentParser(description="Generate Appraisal Report")
    parser.add_argument("--pipeline-id", help="Pipeline document ObjectId (reads address/suburb/client from DB)")
    parser.add_argument("--address", help="Property address (partial match)")
    parser.add_argument("--client", help="Client name")
    parser.add_argument("--suburb", help="Suburb collection name (lowercase)")
    parser.add_argument("--sell-timeline", default="3-6months")
    parser.add_argument("--skip-ai", action="store_true")
    args = parser.parse_args()

    db_client = get_db()

    # Load from pipeline or CLI args
    if args.pipeline_id:
        pipeline = db_client["system_monitor"]["appraisal_pipeline"].find_one({"_id": ObjectId(args.pipeline_id)})
        if not pipeline:
            sys.exit(f"[ERROR] Pipeline {args.pipeline_id} not found")
        address = pipeline["address"]
        client_name = pipeline["name"]
        suburb_key = pipeline["suburb_key"]
        suburb_display = pipeline.get("suburb", suburb_key.replace("_", " ").title())
        sell_timeline = pipeline.get("sell_timeline", "3-6months")
        # Mark as generating
        update_pipeline(args.pipeline_id, "report_generating")
    else:
        if not args.address or not args.client or not args.suburb:
            sys.exit("[ERROR] Provide --pipeline-id OR --address + --client + --suburb")
        address = args.address
        client_name = args.client
        suburb_key = args.suburb
        suburb_display = suburb_key.replace("_", " ").title()
        sell_timeline = args.sell_timeline

    print(f"Generating Appraisal Report: {address} for {client_name} ({suburb_display})")

    # 1. Find property
    prop = find_property(db_client, suburb_key, address)
    if not prop:
        msg = f"[ERROR] Property not found: {address} in {suburb_key}"
        print(msg)
        if args.pipeline_id:
            update_pipeline(args.pipeline_id, "error")
        sys.exit(msg)
    print(f"  Found: {prop.get('complete_address') or prop.get('address')}")

    # 2. Get adjustment rates for this suburb
    rates = get_rates(suburb_display)
    print(f"  Rates: {suburb_display} ({'custom' if suburb_display in SUBURB_ADJUSTMENT_RATES or suburb_display.title() in SUBURB_ADJUSTMENT_RATES else 'default'})")

    # 3. Dynamic comp selection
    print("  Selecting comparables...")
    comp_docs = select_comps(db_client, suburb_key, prop, max_comps=5)
    print(f"  Found {len(comp_docs)} comparables")
    for doc in comp_docs:
        addr = doc.get("display_address") or doc.get("complete_address") or "?"
        price = doc.get("sold_price") or doc.get("sale_price") or "?"
        print(f"    {addr}: {price}")

    if len(comp_docs) < 2:
        msg = f"[ERROR] Insufficient comparables ({len(comp_docs)}) for {address}"
        print(msg)
        if args.pipeline_id:
            update_pipeline(args.pipeline_id, "error")
        sys.exit(msg)

    # 4. Compute adjustments
    print("  Computing adjustments...")
    top_comps = build_top_comps(prop, comp_docs, rates)

    # 5. Room assessments
    print("  Building room assessments...")
    room_assessments = build_room_assessments(prop.get("property_valuation_data", {}))

    # 6. Market stats
    print("  Loading market stats...")
    market_stats = get_market_stats(db_client, suburb_key)

    # 7. Photos
    work_dir = Path(tempfile.mkdtemp(prefix="appraisal_"))
    print("  Downloading photos...")
    photo_paths = download_photos(prop, work_dir)

    # 8. AI editorial (or minimal fallback)
    if args.skip_ai:
        editorial = _minimal_editorial(prop, top_comps, market_stats)
    else:
        print("  Generating editorial via Claude...")
        editorial = generate_editorial(prop, top_comps, market_stats, rates, suburb_display)

    # 9. Render HTML
    timeline_labels = {"asap": "ASAP", "1-3months": "1\u20133 Months", "3-6months": "3\u20136 Months", "not-sure": "Flexible"}
    print("  Rendering HTML...")
    html = render_html(prop, client_name, top_comps, room_assessments, editorial,
                       market_stats, photo_paths, suburb_display,
                       sell_timeline=sell_timeline,
                       sell_timeline_label=timeline_labels.get(sell_timeline, sell_timeline))
    html_path = work_dir / "report.html"
    html_path.write_text(html)

    # 10. Convert to PDF
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    slug = address.lower().replace(" ", "-").replace(",", "").replace("'", "")
    pdf_name = f"{datetime.now(AEST).strftime('%Y-%m-%d')}_{slug}_{client_name.lower()}_v2.pdf"
    pdf_path = OUTPUT_DIR / pdf_name

    print("  Converting to PDF...")
    if html_to_pdf(str(html_path), str(pdf_path)):
        size_kb = pdf_path.stat().st_size / 1024
        print(f"\n  PDF: {pdf_path} ({size_kb:.0f} KB)")

        # Create tracking record so the analyst can preview via the same viewer link
        tracking_id = None
        try:
            sys.path.insert(0, str(ROOT / "tracking-server"))
            from send_report import create_tracking_record, count_pdf_pages
            subject = f"Your Property Appraisal \u2014 {address}"
            total_pages = count_pdf_pages(str(pdf_path))
            monitor_db = db_client["system_monitor"]
            tracking_id = create_tracking_record(
                monitor_db,
                pipeline["email"] if args.pipeline_id else "preview@fieldsestate.com.au",
                client_name, address, str(pdf_path), subject, total_pages,
            )
            print(f"  Tracking ID: {tracking_id}")
            print(f"  Preview: https://vm.fieldsestate.com.au/track/view/{tracking_id}")
        except Exception as e:
            print(f"  [WARN] Tracking record creation failed: {e}")

        # Update pipeline if applicable
        if args.pipeline_id:
            extra = {"report_path": str(pdf_path)}
            if tracking_id:
                extra["tracking_id"] = tracking_id
            update_pipeline(args.pipeline_id, "draft_ready", str(pdf_path))
            # Also set tracking_id directly
            if tracking_id:
                db_client["system_monitor"]["appraisal_pipeline"].update_one(
                    {"_id": ObjectId(args.pipeline_id)},
                    {"$set": {"tracking_id": tracking_id}},
                )
            notify_telegram(
                f"Draft appraisal report ready for review:\n{address}\nClient: {client_name}\n"
                f"Preview: https://vm.fieldsestate.com.au/track/view/{tracking_id}" if tracking_id else
                f"Draft appraisal report ready for review:\n{address}\nClient: {client_name}"
            )
    else:
        print(f"\n  [ERROR] PDF conversion failed. HTML at: {html_path}")
        if args.pipeline_id:
            update_pipeline(args.pipeline_id, "error")


if __name__ == "__main__":
    main()
