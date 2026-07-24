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
    client = MongoClient(conn, retryReads=True, retryWrites=False)
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

    # Sort by score descending, take top 3 (tight comp set = higher quality report)
    candidates.sort(key=lambda x: x[0], reverse=True)
    return [doc for _, _, doc in candidates[:min(max_comps, 3)]]


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


def _format_sold_date(iso_date: str) -> str:
    """Convert '2025-10-07' → '7 October 2025'. Falls back to the raw string on failure."""
    if not iso_date:
        return "?"
    try:
        d = datetime.strptime(iso_date[:10], "%Y-%m-%d")
        return d.strftime("%-d %B %Y")  # %-d strips leading zero on Linux
    except Exception:
        return iso_date[:10]


def _months_between(iso_date: str) -> int:
    """Months from sold_date to now (always >= 0)."""
    if not iso_date:
        return 0
    try:
        d = datetime.strptime(iso_date[:10], "%Y-%m-%d")
        now = datetime.now()
        return max(0, (now.year - d.year) * 12 + (now.month - d.month))
    except Exception:
        return 0


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
        # Clean up address — remove suburb, state, postcode for compact display
        import re as _re
        addr = _re.sub(r'\s+(QLD|Qld|qld)\s+\d{4}\s*$', '', addr)
        addr = _re.sub(r'\s+(ROBINA|MERRIMAC|BURLEIGH WATERS|VARSITY LAKES|MUDGEERABA|REEDY CREEK|WORONGARY|CARRARA)\s*$', '', addr, flags=_re.IGNORECASE)
        addr = addr.strip().strip(",")

        # Pull internal floor area + condition score from comp's own data — both can be None
        c_fpa = doc.get("floor_plan_analysis", {}) or {}
        c_internal = (c_fpa.get("internal_floor_area") or {}).get("value") or doc.get("floor_area_sqm")
        c_pvd = doc.get("property_valuation_data", {}) or {}
        c_overview = c_pvd.get("property_overview", {}) or {}
        c_condition = c_overview.get("overall_condition_score")
        c_beds = doc.get("bedrooms")
        c_baths = doc.get("bathrooms")
        c_cars = doc.get("car_spaces") or doc.get("carspaces")
        # Build "5bd 3ba 4car" config string with only the fields we have
        config_parts = []
        if c_beds is not None: config_parts.append(f"{c_beds}bd")
        if c_baths is not None: config_parts.append(f"{c_baths}ba")
        if c_cars is not None: config_parts.append(f"{c_cars}car")
        config = " ".join(config_parts) if config_parts else "?"

        # Time adjustment: dollar effect of the time multiplier on the (sold + total_adj) base
        # time_mult is e.g. 1.045 → 4.5% appreciation since sale; the time adjustment in dollars
        # is what was added by that multiplier.
        pre_time = sold_price + total_adj
        time_adj_dollars = adjusted - pre_time
        months_ago = _months_between(sold_date)

        # Narrative (best-effort one-liner). We don't synthesise from agent description because
        # those tend to be marketing-speak; surface a structural one-liner instead.
        narrative_parts = []
        if c_overview.get("overall_condition") and c_overview.get("overall_condition") != "good":
            narrative_parts.append(c_overview["overall_condition"].title())
        reno_level = (c_pvd.get("renovation", {}) or {}).get("overall_renovation_level")
        if reno_level:
            narrative_parts.append(reno_level.replace("_", " ").title())
        outdoor = c_pvd.get("outdoor", {}) or {}
        if outdoor.get("pool_present"):
            narrative_parts.append("Pool")
        narrative = ". ".join(narrative_parts) + ("." if narrative_parts else "")

        cards.append({
            "address": addr,
            "sold_display": fmt(sold_price),
            "sold_price": sold_price,
            "date": sold_date[:10] if sold_date else "?",
            "date_display": _format_sold_date(sold_date),
            "beds": c_beds if c_beds is not None else "?",
            "baths": c_baths if c_baths is not None else "?",
            "cars": c_cars if c_cars is not None else "?",
            "config": config,
            "land": doc.get("land_size_sqm") or doc.get("lot_size_sqm") or "?",
            "internal": int(c_internal) if c_internal is not None else None,
            "condition": c_condition if c_condition is not None else None,
            "adjustments": adjs,
            "total_adj": total_adj,
            "total_adj_display": fmt_signed(total_adj),
            "time_factor": f"{time_mult:.3f}",
            "time_adj_dollars": time_adj_dollars,
            "time_adj_display": fmt_signed(time_adj_dollars) if time_adj_dollars else "",
            "months_ago": months_ago,
            "adjusted_total": adjusted,
            "adjusted_total_display": fmt(adjusted),
            "narrative": narrative,
        })
    cards.sort(key=lambda c: c["adjusted_total"])
    return cards


# ---------------------------------------------------------------------------
# Room assessments (fully dynamic from property_valuation_data)
# ---------------------------------------------------------------------------
# String-rated condition → /10 score. Used as fallback when a per-room
# `quality_score` field isn't populated (which is most of the time on the current
# enrichment pipeline). Derived from the AI vision pipeline's vocab.
_CONDITION_TO_SCORE = {
    "excellent": 9, "very_good": 8, "good": 7, "fair": 6, "poor": 5, "very_poor": 4,
    "modern": 8, "contemporary": 8, "updated": 8, "renovated": 8, "new": 9,
    "dated": 5, "original": 5, "tired": 4,
}


def _derive_room_score(room_data: dict, condition_field_priorities: list[str], pvd_overall_score) -> int | None:
    """Best-effort score derivation:
       1. Explicit `quality_score` if set (rare on current data)
       2. Highest mapped condition string from the priority list (good/excellent/dated/etc.)
       3. Fallback to overall property condition score
       4. None if nothing usable
    """
    if not isinstance(room_data, dict):
        return None
    explicit = room_data.get("quality_score") or room_data.get("overall_facade_score")
    if isinstance(explicit, (int, float)) and explicit > 0:
        return int(explicit)
    # Try condition-string derivation
    candidates = []
    for f in condition_field_priorities:
        v = room_data.get(f)
        if isinstance(v, str):
            mapped = _CONDITION_TO_SCORE.get(v.lower().replace(" ", "_"))
            if mapped:
                candidates.append(mapped)
        elif isinstance(v, (int, float)) and v > 0:
            candidates.append(int(v))
    if candidates:
        # Take the highest-scoring derivation (most generous reasonable read)
        return max(candidates)
    # Fallback to overall property condition
    if isinstance(pvd_overall_score, (int, float)) and pvd_overall_score > 0:
        return int(pvd_overall_score)
    return None


def _collapse_room_array(arr) -> dict | None:
    """Reduce an array of room entries (bathrooms[], living_areas[]) to a single
    representative dict by picking the entry with the highest quality_score
    (falling back to condition_score, then first visible entry).

    The enrichment pipeline emits arrays per the schema in
    enrich_for_sale_batch.py; the report renders a single card per room category,
    so we surface the best-rated representative.
    """
    if not isinstance(arr, list) or not arr:
        return None
    visible = [r for r in arr if isinstance(r, dict) and r.get("visible") is not False]
    if not visible:
        return None

    def _rank(entry: dict) -> float:
        for f in ("quality_score", "condition_score"):
            v = entry.get(f)
            if isinstance(v, (int, float)) and v > 0:
                return float(v)
        return 0.0

    return max(visible, key=_rank)


def _extract_master_bedroom(pvd: dict) -> dict | None:
    """The schema stores all bedrooms in pvd['bedrooms'] as an array, with the
    master tagged via bedroom_label='master'. Find and return that entry.
    """
    bedrooms = pvd.get("bedrooms")
    if not isinstance(bedrooms, list):
        return None
    for b in bedrooms:
        if isinstance(b, dict) and b.get("bedroom_label") == "master":
            return b
    return None


def build_room_assessments(pvd: dict) -> list[dict]:
    """Build /10 condition cards for the 'Property Through Our Eyes' page.

    Skips rooms where we have no usable data — better to show fewer accurate
    cards than to render 'None/10' placeholders that look like data quality issues.
    """
    if not isinstance(pvd, dict):
        return []
    overall_score = (pvd.get("property_overview", {}) or {}).get("overall_condition_score")
    # Each tuple: (display_name, pvd_key, condition_field_priorities, detail_fields_to_render)
    # Detail field names match the enrichment schema in enrich_for_sale_batch.py.
    mapping = [
        ("Kitchen",         "kitchen",         ["cabinet_condition", "quality_score"], ["benchtop_material", "cabinet_style", "appliances_quality"]),
        ("Bathrooms",       "bathrooms",       ["quality_score", "condition_score", "fixtures_quality"], ["fixtures_quality", "tile_condition", "vanity_style"]),
        ("Living Areas",    "living_areas",    ["quality_score", "condition_score"], ["flooring_type", "natural_light", "ceiling_height"]),
        ("Master Bedroom",  "master_bedroom",  ["quality_score", "condition_score"], ["walk_in_robe", "ensuite", "flooring_type"]),
        ("Exterior",        "exterior",        ["cladding_condition", "paint_condition", "overall_facade_score", "quality_score"], ["cladding_material", "paint_condition", "roof_type"]),
        ("Outdoor",         "outdoor",         ["pool_condition", "landscaping_quality", "quality_score", "pool_condition_score"], ["pool_type", "pool_condition", "alfresco_size", "landscaping_quality"]),
    ]
    rooms = []
    for label, key, score_fields, detail_fields in mapping:
        data = pvd.get(key)
        # Master bedroom is stored inside bedrooms[] — pull it out by label.
        if key == "master_bedroom" and not isinstance(data, dict):
            data = _extract_master_bedroom(pvd)
        # Bathrooms / living_areas (and any future array-shaped room) are emitted
        # as arrays by the enrichment schema; collapse to the best representative.
        if isinstance(data, list):
            data = _collapse_room_array(data)
        if not data or not isinstance(data, dict):
            continue
        score = _derive_room_score(data, score_fields, overall_score)
        if score is None:
            continue  # skip rooms with no usable score — better than 'None/10'
        details = []
        for f in detail_fields:
            v = data.get(f)
            if v is None or v == "" or v is False:
                continue
            label_display = f.replace("_", " ").title()
            if isinstance(v, bool):
                value_display = "Yes"
            elif isinstance(v, str):
                value_display = v.replace("_", " ").title()
            else:
                value_display = v
            details.append(f"{label_display}: {value_display}")
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
# Original tier for this script. _claude_backend preserves the Opus tier when
# routing through the Max CLI (its alias mapping keys off "opus" in the string).
EDITORIAL_MODEL = os.environ.get("APPRAISAL_EDITORIAL_MODEL", "claude-opus-4-20250514")


def _claude_model() -> str:
    """Resolve the model the configured backend should use for this script."""
    try:
        sys.path.insert(0, str(Path(__file__).resolve().parent / "property_reports"))
        from _claude_backend import get_client_and_model
        _, model = get_client_and_model(EDITORIAL_MODEL)
        return model or EDITORIAL_MODEL
    except Exception:
        return EDITORIAL_MODEL


def generate_editorial(prop: dict, top_comps: list, market_stats: dict, rates: dict, suburb: str, scarcity_stats: dict = None) -> dict:
    """Generate ALL editorial content via Claude — headline, verdict, value equations, buyer profiles, positioning."""
    # Route through the shared backend resolver (Max CLI / OpenRouter / Vertex /
    # direct API) rather than building a raw pay-as-you-go client. The direct API
    # has no credit balance, so this previously fell straight through to
    # _minimal_editorial and shipped placeholder prose in a real appraisal PDF.
    try:
        sys.path.insert(0, str(Path(__file__).resolve().parent / "property_reports"))
        from _claude_backend import get_client_and_model
        client, editorial_model = get_client_and_model(EDITORIAL_MODEL)
    except Exception as e:
        print(f"  [WARN] Claude backend unavailable ({e}), using minimal editorial")
        return _minimal_editorial(prop, top_comps, market_stats)

    if client is None:
        print("  [WARN] no Claude backend configured, using minimal editorial")
        return _minimal_editorial(prop, top_comps, market_stats)

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

    # Build detailed adjustment summary for each comp
    adj_detail = ""
    for c in top_comps:
        adj_lines = []
        for a in c.get("adjustments", []):
            adj_lines.append(f"      {a['label']}: {a['diff']} = {a['display']}")
        adj_detail += f"  {c['address']}: sold {c['sold_display']} ({c['date']})\n"
        adj_detail += f"    Total property adjustment: {c['total_adj_display']}\n"
        adj_detail += f"    Time adjustment factor: {c['time_factor']}\n"
        adj_detail += f"    Adjusted value for subject: {c['adjusted_total_display']}\n"
        if adj_lines:
            adj_detail += f"    Line-item adjustments:\n" + "\n".join(adj_lines) + "\n"

    # Build scarcity block for the prompt — feeds the AI sample-relative,
    # disclosed positioning facts (percentile vs the typical sampled home; share
    # of the sample carrying the standout combination). We never had a census of
    # all sold homes — only a labelled indicative Domain-scraped sample — so the
    # AI must cite these WITH the sample disclosure and never as census claims.
    scarcity_stats = scarcity_stats or {}
    scarcity_total = scarcity_stats.get("total_12m_sales", 0) or 0
    scarcity_lines = scarcity_stats.get("statements") or []
    scarcity_block = "\n".join(f"  - {s}" for s in scarcity_lines) if scarcity_lines else "  - (no sample context available — fall back to general suburb stats, and do not imply completeness)"

    prompt = f"""You are the Fields Estate editorial team writing a seller appraisal report. This must be PUBLICATION QUALITY — specific, data-dense, honest, and compelling. Every claim must cite data.

PROPERTY: {address}
{beds} bedrooms, {baths} bathrooms, {cars} car spaces.
{land} sqm land, {floor_area} sqm internal, {stories}-storey, condition {condition}/10.
Pool: {pool}. Renovation: {reno}. Kitchen: {kitchen}. AC: {ac}.
{poi_text}

COMPARABLE SALES WITH FULL ADJUSTMENT DETAIL:
{adj_detail}

VALUATION RANGE: {fmt(val_low)} to {fmt(val_high)} (mid-point {fmt(val_mid)})

MARKET CONTEXT: {suburb} median {market_stats['median']}. {market_stats['houses_sold_12m']} houses sold in 12m. {market_stats['currently_listed']} currently listed.

SAMPLE-RELATIVE POSITIONING FACTS (measured against our indicative sample of {scarcity_total} Domain-scraped sold properties — NOT a census of every sale. Cite these to back feature_positioning entries, but you MUST carry the sample disclosure when you do, and you MUST NOT reword them into census claims):
{scarcity_block}

CRITICAL FRAMING RULE (legal/accuracy): We do not have a record of every home that sold — only what we scraped from Domain, and of that a representative sample. So you may say "this property sits above 88% of our sample of N sold {suburb} homes" or "within our sample of N, X% combined these features", ALWAYS naming the sample and window. You must NEVER write "the only one sold this year", "exceeds every house sold", "no other home has", "1 of only X homes", or any wording that implies a complete count of all sales. Rarity is expressed relative to the disclosed sample and to the typical home — never as an absolute census.

QUALITY STANDARD — follow this example of what "good" looks like:

Example headline: "Your property sits well above the Merrimac median, supported by three recent comparable sales"
Example strength bullet: "9/10 condition with stone benchtops, inground pool, outdoor kitchen, and 52.5 sqm entertaining deck — roughly $165,000–$230,000 of renovation already done"
Example value equation: "Land: 658 m² — mid-sized for Merrimac. 3 Islay Court sold on 769 m² and 7 Nicklaus Court on 825 m². At $375/m², that's $40,000–$63,000 less land value. But the outdoor package on this property — inground pool (excellent condition), 5.25 m² covered deck, outdoor kitchen — would cost $195,000–$145,000 to replicate. The outdoor infrastructure more than compensates for the land gap."
Example trade-off: "658 sqm lot (107 sqm less than the nearest comp), 221 sqm internal floor area, and a two-storey layout that rules out single-level living"

RULES (MANDATORY):
- Frame as "we would" not "you should". NEVER give advice. Data only — reader draws conclusions.
- No forbidden words ANYWHERE in the output: stunning, nestled, boasting, rare opportunity, robust market, must-see, dream home, won't last, act fast, don't miss, exquisite, tranquil oasis. The validator REJECTS any output containing these phrases.
- INOCULATION (mandatory): of the 5 value_equations, AT LEAST 2 MUST be "trade-off" panels — they identify a measurement where the property is BELOW comparables (smaller land, smaller floor area, lower condition, fewer car spaces, single-level when 2-storey is preferred, etc.) and then reframe that trade-off as value. Set `positive: false` on those panels. Reports where all 5 panels are positive read as marketing brochures, not honest analysis.
- CAMPAIGN CONSISTENCY (mandatory): for Gold Coast properties, the DEFAULT recommendation is private treaty (per Frino, Peat & Wright 2012, n=1.2M; REA Group 2014 — 72% of buyers skip auction listings without price guides). Only recommend auction if the property is genuinely unique (waterfront with no comparable sale, architecturally significant, deceased estate requiring auction by law). If you DO recommend auction in `campaign_structure`, the first sentence must explicitly state why the property qualifies as one of these exceptions. Do not recommend auction by default for premium homes — premium price and auction-suitability are not the same thing.
- Cite specific comp addresses, prices, adjustment figures, and percentages.
- Price format: $1,250,000 not $1.25m. Suburbs always capitalised.
- Every trade-off must be reframed as value — a seller reading this should feel their property is positioned honestly and favourably.
- No predictions. Use conditional language ("if X, data suggests Y").
- Be SPECIFIC — mention actual room sizes, materials, distances, scores. Generic statements are unacceptable.

Return JSON with these keys:

{{
  "headline": "One sentence citing the comparable range and median position. Must include specific numbers.",
  "sub_headline": "One sentence: key differentiators with specifics (bedroom count, pool, condition score, scarcity). Include a scarcity data point.",
  "verdict": "4-5 sentences: Start with 'Based on [N] adjusted comparable sales ranging from [X] to [Y]...'. State the selling range, recommended listing range, and the 3-4 primary value drivers with dollar references. Cite at least 2 comp addresses by name.",
  "strengths": ["3-4 bullets, each with SPECIFIC dollar impacts or measurements. E.g. 'Pool and outdoor package valued at approximately $X based on adjustment data from [comp address]'. Never generic."],
  "trade_off": "One sentence with specific measurements — what the property gives up AND why it doesn't matter (reframe as value).",
  "value_equations": [
    {{"title": "Feature: specific measurement", "body": "3-4 sentences. MUST cite at least one comp by address. State the dollar impact from the adjustment data. Compare specific measurements (sqm, scores, features). End with the net value implication.", "reframe": "One sentence: the bold editorial reframe — why this feature is actually an advantage even if it looks like a weakness. Written in italics-worthy confident tone.", "positive": true}}
  ],
  "buyer_profiles": [
    {{"name": "Specific buyer persona (e.g. 'Young family upgrading from 3-bed')", "description": "3 sentences: Who they are, why this property fits (cite specific features), and what drives their purchase decision. Reference nearby schools, parks, or lifestyle features by name."}}
  ],
  "not_ideal_for": ["3-4 short bullet points naming buyer types this property does NOT suit. Inoculation: name what THIS specific property's structural features (size, layout, condition, location) make it unsuitable for. Examples: 'Single-level seekers' (for two-storey homes), 'Buyers needing 3+ car garaging' (for narrow blocks), 'Families wanting acreage feel' (for sub-600 sqm), 'Pet-free buyers concerned about previous animal residency' (only if applicable from data). Each item under 8 words. Be specific to THIS property's structural characteristics, not generic."],
  "scarcity_count": "Exact number of similar-spec properties that sold in the suburb in 12 months",
  "scarcity_statement": "Specific scarcity statement citing bedroom count, key features, and the total sold number. E.g. 'five-bedroom homes sold in Merrimac in 12 months — out of 58 total sales. Only 1 had a pool.'",
  "lifestyle_narrative": "3-4 sentences grounded in POI data. Name specific schools, parks, shops with distances. Paint the daily life picture.",
  "pricing_cards": [
    {{"label": "Strategy name (e.g. 'Aspirational Pricing')", "range": "$X,XXX,XXX — $X,XXX,XXX", "rationale": "2-3 sentences citing specific comparable evidence for this price bracket."}}
  ],
  "feature_positioning": [
    {{
      "feature": "Title format: 'Feature name — $ figure or scarcity claim'. Examples: 'Dual Living Configuration — $354,868 value differential', 'Pool + 52.5 sqm Covered Deck + Outdoor Kitchen — $95,000-$145,000 to replicate', 'All Saints Anglican School — 150m from boundary', 'Genuine Scarcity — 5 sales in 12 months, 1 with a pool'. The TITLE ITSELF must contain a number (a dollar adjustment, a replacement-cost range, a distance, a count). NEVER 'Pool and outdoor entertainment' — always 'Pool... — $X,XXX-$Y,YYY differential'.",
      "strategy": "3-4 sentences. SENTENCE 1: lead with the hard data claim — quote the comp adjustment dollar value if available, OR cite a scarcity statement from the SCARCITY DATA block above (use the exact numbers — e.g. 'Of {scarcity_total} suburb sales in 12 months, only N had X'). SENTENCE 2: explain the buyer-pool implication of that scarcity / value (e.g. 'eliminates 90% of competing stock', 'activates multi-generational buyers who have almost no options in this suburb'). SENTENCE 3: name the marketing/photography action. SENTENCE 4 (optional): one bold reframe. DO NOT lead with photography directions — lead with the data."
    }}
  ],
  "campaign_structure": "3-4 sentences: specific campaign approach — duration, channels, staging priorities, open home schedule. Reference the property's specific strengths.",
  "photography_strategy": "3 sentences: specific rooms/angles to prioritise, time of day, what to stage. Reference the property's actual features (pool, kitchen, deck, etc.).",
  "open_home_strategy": "3 sentences: approach to inspections — what to highlight on the walk-through, where to start, what creates the emotional peak.",
  "negotiation_plan": {{
    "intro": "One sentence framing the page. Suggested: 'Three offer scenarios we have already thought about, so the response is rehearsed before offer day.'",
    "scenarios": [
      {{"label": "Early high offer (week 1)", "timing": "Days 4–10 of the campaign, often after the first or second weekend's open homes.", "buyer": "Specific buyer-type description (e.g. 'Interstate relocator on a tight settlement timeline', 'Local upgrader who has missed multiple homes already this quarter'). Reference the buyer pool from this property's specific market.", "response": "3-4 sentences naming the Fields response: hold firm vs counter, why, what we'd say. Reference the property's specific value drivers as anchors. Do NOT use the word 'auction'."}},
      {{"label": "Mid-range cluster (weeks 2–3)", "timing": "Week 2-3 — multiple offers within $50k-$100k of each other.", "buyer": "Specific description of the most likely cluster (e.g. 'Multiple Marymount families', 'Three downsizers from acreage all chasing the same low-maintenance lifestyle'). Property-specific.", "response": "3-4 sentences naming the Fields response: best-and-final vs sequential negotiation, why, the 1-2 levers we'd use to break the tie."}},
      {{"label": "Late low offer (week 4+)", "timing": "Week 4 onward — campaign has slowed, buyer pool narrowed.", "buyer": "Specific description (e.g. 'Bargain-hunter testing for vendor fatigue', 'Conservative buyer waiting for a price reduction').", "response": "3-4 sentences naming the Fields response: when to engage vs when to refuse, what concessions we would and wouldn't accept, the reframe we use to restore competitive tension. Reference the property's strongest positioning data."}}
    ],
    "closing": "One sentence: 'These responses are templates, not scripts — the negotiation always adapts to the actual buyer in front of us. The point is that we have already thought about it. Offer day should not be the first day we think about how to respond.'"
  }},
  "limits_of_evidence": {{
    "intro": "One sentence introducing why this section exists. Frame as: we want you to know what we couldn't see, so you can weigh our analysis honestly.",
    "items": [
      {{"title": "Interior condition", "body": "2-3 sentences. State that our score is derived from photos, name a specific signal an in-person inspection might find (e.g. dampness, hidden mould, dated wiring, structural cracks, sub-floor issues), and quantify the % range impact (e.g. 3-8%) if that signal were present."}},
      {{"title": "Recent build defects or repairs", "body": "2-3 sentences. State we have no record of repairs to roof, waterproofing, structural elements, or recent insurance claims. Mention what a pest-and-building report could change."}},
      {{"title": "Neighbour disputes / fence lines / overlooks", "body": "2-3 sentences. State this isn't visible from our data sources. Note that boundary disputes and informal fence-line agreements only surface in the contract/disclosure phase."}},
      {{"title": "Council DAs and infrastructure proposals within 500m", "body": "2-3 sentences. State we monitor council DAs but minor proposals or recently-approved works affecting view lines or noise can shift desirability. (For units only: substitute body corporate / strata health — recent special levies, scheduled major works, sinking fund balance — which we read from the disclosure but cannot independently verify.)"}}
    ],
    "closing": "One sentence reaffirming why an in-person inspection by our property analyst matters before signing. Honest, not dismissive."
  }},
  "morning_in_this_home": "Length: 200-250 words. AIM FOR THE TOP OF THE RANGE (240 words) — better to slightly trim a long draft than to fall short of 200, because the validator rejects below 170. Style: present-tense sensory narrative, written as if you ARE a prospective buyer experiencing the home for the first time. Short clean sentences. ABSOLUTE RULES: (a) NEVER use 'you' or 'your' — the narrator IS a buyer, so 'you' may not appear at all (write in 1st-person 'I' or implied present-tense like 'the kettle is on'); (b) MUST reference at least one named POI from `nearby_pois` (a specific school, park, beach, reserve, by name); (c) MUST reference at least one named feature of THIS property (the pool, the deck, the kitchen island, the wetland boundary, the cul-de-sac, etc.); (d) MUST reference a named time of day or moment (Saturday morning, dusk, twilight, etc.); (e) MUST end on a quiet sensory image — an animal, a sound, a texture — NOT a conclusion or pitch; (f) DO NOT IMPLY THE SELLER OWNS ANY OBJECT NOT IN THE PROPERTY DATA. The waterfront/canal/lake properties especially are a hallucination trap — DO NOT write 'the boat waits on its trailer', 'the family boat', 'the kayak in the garage', 'the jet ski', 'the bikes hanging in the garage', 'the Mustang', 'their Tesla', 'the dog by the door', 'the cat on the windowsill'. These all imply belongings we have no record of. ALLOWED equivalents that describe activity AROUND the property: 'a boat puttering past on the waterway', 'a kayaker glides upstream', 'a paddleboarder navigates the bend', 'a neighbour walking a dog past the fence', 'a kookaburra calls from the eucalypt', 'cars heading toward the M1'. The narrator is a buyer experiencing the home, not the current owner — describe what is OBSERVABLE from the home (pool, deck, kitchen, view, neighbours, traffic, wildlife), NOT what the seller might own. Reference ONLY: items present in the property data (pool, deck, kitchen, room types, gardens), named POIs from `nearby_pois`, public landmarks, and generic family-life moments (kids, coffee, weekend mornings, lawnmowers, birds, distant traffic). DO NOT name a specific car model, boat, motorcycle, jet ski, art collection, school event ('weekend fair', 'rugby game'), named neighbour, named pet, or specific weekend activity unless that item is explicitly present in the property's data fields. When in doubt, omit. No real-estate clichés. No advice. No 'you should'. Think Cereal magazine, not a brochure."
}}

Generate EXACTLY 5 value_equations: AT LEAST 2 must be trade-off panels (positive: false) where the property sits BELOW a comparable on a measurable axis, and the reframe explains why that trade-off creates value. The other 3 are positive value drivers (positive: true) anchored in specific comp-adjustment data. Suggested categories: land size, internal floor area, condition/renovation, key feature (pool/kitchen/outdoor/dual-living/etc), location/school proximity, layout (storey count), kitchen quality. Buyer scarcity is handled by the `scarcity_statement` field; this property's main trade-off is handled by the dedicated `trade_off` field — do NOT duplicate them as value_equations. Five well-evidenced value_equations beat seven thin ones; the page layout is calibrated for 5.

Generate 3 not_ideal_for items — short bullets (under 8 words each) naming the specific buyer types this property's STRUCTURAL features make unsuitable. Be specific to the property, not generic.
Generate EXACTLY 3 buyer_profiles (primary, secondary, tertiary).
Generate EXACTLY 4 pricing_cards (aspirational, competitive, strategic, floor).
Generate EXACTLY 5-6 feature_positioning items. The LAST item MUST be a "Genuine Scarcity" entry titled with the strongest scarcity number from the SCARCITY DATA block above (typically the killer-combo or zero-count statement, e.g. "Genuine Scarcity — 0 sales in 12 months matched this combination"). Its strategy field must restate the scarcity statement using the exact numbers from the data block, explain why this is the strongest positioning lever available, and close by noting we would never use manufactured urgency in premium markets because the data speaks for itself. Do NOT skip this item.
Generate EXACTLY 4 limits_of_evidence.items (interior_condition, build_defects, neighbour_disputes, council_DAs_or_strata) — this is the new "What We Did Not See" section.
The morning_in_this_home narrative is for the new buyer-perspective page — pay close attention to the absolute rules. If you cannot satisfy all five rules, regenerate this single field internally before returning JSON.

OUTPUT FORMAT (CRITICAL — parser is strict):
- Return ONLY a single valid JSON object. Nothing else.
- No markdown fences (no ```json or ```).
- No prose before the opening curly brace.
- No prose after the closing curly brace — no word counts, no compliance notes, no "Here is the JSON:", no explanation, nothing.
- Your entire response must be parseable by json.loads() on the raw text."""

    try:
        resp = client.messages.create(
            model=editorial_model,
            max_tokens=6000,
            messages=[{"role": "user", "content": prompt}],
        )
        text = resp.content[0].text.strip()
        # Strip markdown code fences if Claude wrapped the JSON
        if text.startswith("```"):
            text = re.sub(r"^```\w*\n?", "", text)
            text = re.sub(r"\n?```$", "", text)
        # Skip any prose before the first '{'
        first_brace = text.find("{")
        if first_brace > 0:
            text = text[first_brace:]
        # Use raw_decode so any trailing prose / word counts / commentary after the JSON
        # object don't break parsing. (Claude occasionally ignores "no commentary" — defend.)
        decoder = json.JSONDecoder()
        editorial, end_idx = decoder.raw_decode(text)
        trailing = text[end_idx:].strip()
        if trailing:
            print(f"  [INFO] Claude appended {len(trailing)} chars after JSON; ignored.")
        print("  Claude editorial generated successfully")
        return editorial
    except Exception as e:
        print(f"  [WARN] Claude editorial failed: {e}")
        return _minimal_editorial(prop, top_comps, market_stats)


def regenerate_morning_narrative(client, prop: dict, current_morning: str, target_low: int = 200, target_high: int = 250, max_retries: int = 2) -> str:
    """Regenerate morning_in_this_home until it lands within target word range, or give up after max_retries.

    Cost: ~$0.50 per retry (single-field Claude call, max_tokens 1500).
    Returns the original `current_morning` if all retries fail.
    """
    morning = current_morning
    wc = len(morning.split())
    if target_low <= wc <= target_high:
        return morning  # already in range

    address = prop.get("complete_address") or prop.get("address", "the property")
    nearby_pois = prop.get("nearby_pois", {}).get("by_category", {})
    poi_names = []
    for cat in ["primary_school", "secondary_school", "park", "cafe", "supermarket", "beach"]:
        for p in nearby_pois.get(cat, [])[:2]:
            if p.get("name"):
                poi_names.append(p["name"])
    poi_hint = ", ".join(poi_names[:6]) if poi_names else "(no named POIs available)"

    for attempt in range(max_retries):
        direction = "EXPAND TO 200-250 WORDS" if wc < target_low else "TRIM TO 200-250 WORDS"
        print(f"  M11 retry {attempt + 1}/{max_retries}: current {wc} words, target 200-250")

        retry_prompt = f"""Below is a morning_in_this_home narrative for {address}. It is currently {wc} words. The required length is 200-250 words.

{direction}. Keep the same sensory tone, named POIs, and property features.

ABSOLUTE RULES (the validator will reject violations):
- Do NOT use 'you' or 'your' addressing the seller. The narrator IS a buyer.
- Do NOT use forbidden words: stunning, nestled, boasting, rare opportunity, robust market, must-see, dream home, won't last, perfect for, exquisite, tranquil oasis.
- Do NOT IMPLY THE SELLER OWNS ANY OBJECT not in the property data. Specifically forbidden: 'the boat waits', 'the family boat', 'the kayak in the garage', 'the jet ski', 'the bikes', 'the Mustang/Tesla', 'the dog/cat', 'their X' where X is a vehicle/pet/hobby gear. These imply belongings we have no record of.
- Allowed equivalents that describe activity AROUND the home: 'a boat puttering past on the waterway', 'a kayaker glides upstream', 'a paddleboarder navigates the bend', 'a neighbour walking a dog past the fence', 'a kookaburra calls from the eucalypt', 'cars heading toward the M1'.
- The narrator is a prospective buyer experiencing the home — describe what is OBSERVABLE from the home (pool, deck, kitchen, view, neighbours, traffic, wildlife), NOT what the seller might own.

Available named POIs to reference if needed: {poi_hint}

Return ONLY the new narrative text. No JSON, no quotes around it, no commentary, no word count.

Current narrative:
\"\"\"
{morning}
\"\"\""""
        try:
            resp = client.messages.create(
                model=_claude_model(),
                max_tokens=1500,
                messages=[{"role": "user", "content": retry_prompt}],
            )
            new_morning = resp.content[0].text.strip().strip('"').strip("'").strip()
            # Strip any leading/trailing triple quotes that Claude might wrap with
            new_morning = re.sub(r'^\s*"""', '', new_morning)
            new_morning = re.sub(r'"""\s*$', '', new_morning)
            new_wc = len(new_morning.split())
            print(f"  M11 retry {attempt + 1}: {wc} → {new_wc} words")
            if target_low <= new_wc <= target_high:
                return new_morning
            morning = new_morning
            wc = new_wc
        except Exception as e:
            print(f"  M11 retry {attempt + 1} failed: {e}")
            return current_morning  # fall back to original on API failure

    # All retries used and still out of range — return the best attempt
    print(f"  M11 retries exhausted; returning best attempt at {wc} words")
    return morning


def _minimal_editorial(prop: dict, top_comps: list, market_stats: dict) -> dict:
    """Fallback when Claude is unavailable — data-driven, no AI prose but not empty."""
    adj_prices = [c["adjusted_total"] for c in top_comps if c.get("adjusted_total")]
    val_low = min(adj_prices) if adj_prices else 0
    val_high = max(adj_prices) if adj_prices else 0
    val_mid = int(sum(adj_prices) / len(adj_prices)) if adj_prices else 0
    beds = prop.get("bedrooms", "?")
    baths = prop.get("bathrooms", "?")
    suburb = prop.get("suburb", "?")
    pvd = prop.get("property_valuation_data", {})
    condition = pvd.get("property_overview", {}).get("overall_condition_score", "?")
    pool = "with pool" if pvd.get("outdoor", {}).get("pool_present") else ""
    land = prop.get("land_size_sqm") or prop.get("lot_size_sqm") or "?"

    # Build value equations from adjustment data
    value_equations = []
    if top_comps:
        # Land
        value_equations.append({
            "title": f"Land: {land} m\u00b2",
            "body": f"Compared against {len(top_comps)} recent sales in {suburb}. Land size adjustments ranged from {top_comps[0].get('adjustments', [{}])[0].get('display', 'N/A')} to {top_comps[-1].get('adjustments', [{}])[0].get('display', 'N/A') if len(top_comps) > 1 else 'N/A'} across comparables.",
            "reframe": "Land size is one factor among many — condition, layout, and outdoor amenities often outweigh raw lot dimensions.",
            "positive": True,
        })
        # Condition
        if condition != "?":
            value_equations.append({
                "title": f"Condition: {condition}/10",
                "body": f"An overall condition score of {condition}/10 positions this property relative to the comparable set. Condition adjustments are applied as a percentage of sale price, reflecting the cost a buyer would incur to match this level of finish.",
                "reframe": "The condition score reflects the current state — every property has a score, and this data point helps buyers understand what they are getting for the price.",
                "positive": condition >= 7,
            })

    # Build strengths from top adjustment line items
    strengths = []
    for c in top_comps[:2]:
        for adj in c.get("adjustments", []):
            if adj["value"] > 20000:
                strengths.append(f"{adj['label']}: {adj['display']} adjustment vs {c['address']}")
            if len(strengths) >= 3:
                break
        if len(strengths) >= 3:
            break
    if not strengths:
        strengths = [f"Adjusted comparable range: {fmt(val_low)} to {fmt(val_high)}"]

    comp_addresses = [c["address"] for c in top_comps]
    comp_cite = " and ".join(comp_addresses[:2]) if len(comp_addresses) >= 2 else comp_addresses[0] if comp_addresses else "comparable sales"

    return {
        "headline": f"Based on {len(top_comps)} adjusted comparable sales, this property sits {'above' if val_mid > int(market_stats.get('median', '$0').replace('$', '').replace(',', '') or 0) else 'around'} the {suburb} median of {market_stats['median']}",
        "sub_headline": f"A {beds}-bedroom {pool} property with an adjusted comparable range of {fmt(val_low)} to {fmt(val_high)}",
        "verdict": f"Based on {len(top_comps)} adjusted comparable sales — {comp_cite} — ranging from {fmt(val_low)} to {fmt(val_high)}, we estimate a selling range of {fmt(val_low)} to {fmt(val_high)}, with a recommended listing range of {fmt(round(val_mid * 0.97 / 5000) * 5000)} to {fmt(round(val_mid * 1.03 / 5000) * 5000)}, subject to property analyst inspection.",
        "strengths": strengths,
        "trade_off": f"Refer to the detailed comparable adjustment analysis for feature-by-feature value impacts",
        "value_equations": value_equations,
        "buyer_profiles": [
            {"name": f"Families seeking {beds} bedrooms in {suburb}", "description": f"Buyers looking for a {beds}-bedroom home in {suburb} with proximity to local schools and amenities. This property's specification matches the most active buyer segment in the suburb."},
            {"name": "Upgraders from smaller homes", "description": f"Owners of 2-3 bedroom properties in the southern Gold Coast corridor looking to upsize. {suburb}'s median of {market_stats['median']} offers value relative to beachside suburbs."},
            {"name": "Investors seeking rental yield", "description": f"With {market_stats.get('currently_listed', '?')} properties currently listed and {market_stats.get('houses_sold_12m', '?')} sales in the last 12 months, {suburb} shows balanced supply and demand."},
        ],
        "scarcity_count": market_stats.get("houses_sold_12m", "?"),
        "scarcity_statement": f"{beds}-bedroom houses sold in {suburb} in the last 12 months",
        "lifestyle_narrative": f"Located in {suburb}, this property offers access to local schools, parks, and shopping within the southern Gold Coast corridor.",
        "pricing_cards": [
            {"label": "Aspirational", "range": f"{fmt(val_high)} +", "rationale": f"At the top of the comparable range, supported by {comp_addresses[-1] if comp_addresses else 'the highest comparable'}."},
            {"label": "Competitive", "range": f"{fmt(round(val_mid / 5000) * 5000)} \u2013 {fmt(round(val_high * 0.97 / 5000) * 5000)}", "rationale": f"Mid-range positioning designed to attract multiple offers within the first 3 weeks."},
            {"label": "Strategic", "range": f"{fmt(round(val_low * 1.02 / 5000) * 5000)} \u2013 {fmt(round(val_mid / 5000) * 5000)}", "rationale": f"Below the mid-point to generate urgency and competition among buyers."},
        ],
        "feature_positioning": [],
        "campaign_structure": f"A 3-4 week campaign with professional photography, targeted digital advertising to {suburb} and surrounding suburbs, and weekend open homes.",
        "photography_strategy": f"Prioritise the front elevation, main living areas, kitchen, and outdoor spaces. Shoot in the morning for natural light.",
        "open_home_strategy": f"Saturday open homes from 10-10:30am. Start at the front entrance and guide through living areas before revealing outdoor spaces last for maximum impact.",
    }


# ---------------------------------------------------------------------------
# Photo download
# ---------------------------------------------------------------------------
def download_photos(prop: dict, work_dir: Path) -> dict:
    photos_dir = work_dir / "photos"
    photos_dir.mkdir(exist_ok=True)
    images = prop.get("property_images", [])
    paths = {}

    # Per-property local cache fallback (used when blob storage is unavailable
    # or for offline preview runs). Files named hero.jpg, exterior.jpg, etc.
    cache_dir = ROOT / "cache" / "property_photos" / str(prop.get("_id", ""))

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
            cached = cache_dir / f"{name}.jpg"
            if cached.is_file():
                paths[name] = str(cached)
            else:
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
# M13 — Risk + Protection panel data builder
# ---------------------------------------------------------------------------
# Per-suburb median DOM (days on market) for M22 outcome projection — sourced
# from seller book Chapter 2 analysis of 13,585 Gold Coast sales 2020-2025.
SUBURB_DOM_DAYS = {
    "Robina": 24,
    "Burleigh Waters": 26,
    "Varsity Lakes": 26,
    "Merrimac": 30,
    "Mudgeeraba": 32,
    "Reedy Creek": 28,
    "Worongary": 32,
    "Carrara": 30,
}
_DEFAULT_DOM = 28


def build_risk_data(prop: dict, suburb: str) -> dict:
    """Build the M13 Risk + Protection panel data — facts only, no AI.

    Returns a dict consumable by the template:
    {
      'intro': str,
      'items': [{'category', 'status', 'status_color', 'detail', 'source'}, ...],
      'closing': str,
    }

    Categories rendered (in order; some skipped if data unavailable):
      1. Flood overlay (council)
      2. Insurance flood probability (ICA)
      3. Zoning
      4. Heritage listing
      5. Beach/coastal proximity (where data exists)
      6. Traffic & street position (from satellite analysis)
      7. School proximity (from POIs)
      8. Property tenure
      9. Body corporate / strata (units only)
      10. Council DAs within 500m — DEFERRED (we don't yet automate this)
      11. Easements / encumbrances — DEFERRED (title search territory)
    """
    zd = prop.get("zoning_data", {}) or {}
    sa = prop.get("satellite_analysis", {}) or {}
    pois = prop.get("nearby_pois", {}).get("by_category", {}) or {}
    items = []

    # 1. Flood overlay (council)
    if zd:
        if zd.get("flood_overlay"):
            ground = zd.get("flood_ground_level_m")
            designated = zd.get("flood_designated_level_m")
            depth_desc = zd.get("flood_depth_description", "")
            note = zd.get("flood_risk_note") or zd.get("flood_description") or ""
            detail_parts = []
            if ground is not None and designated is not None:
                detail_parts.append(f"Ground level {ground}m AHD, designated flood level {designated}m AHD")
            if note:
                detail_parts.append(note)
            if depth_desc:
                detail_parts.append(f"Modelled depth: {depth_desc}")
            items.append({
                "category": "Flood overlay (council)",
                "status": "OVERLAY APPLIES",
                "status_color": "amber",
                "detail": ". ".join(p for p in detail_parts if p) or "Property sits within the council's flood overlay.",
                "source": "Gold Coast City Council planning scheme",
            })
        else:
            items.append({
                "category": "Flood overlay (council)",
                "status": "CLEAR",
                "status_color": "green",
                "detail": (
                    f"No flood overlay on Gold Coast City Council mapping. "
                    f"Ground level sits at {zd.get('flood_ground_level_m')}m AHD."
                    if zd.get("flood_ground_level_m") is not None
                    else "No flood overlay on Gold Coast City Council mapping."
                ),
                "source": "Gold Coast City Council planning scheme",
            })
    else:
        items.append({
            "category": "Flood overlay (council)",
            "status": "NOT YET ASSESSED",
            "status_color": "neutral",
            "detail": "Council flood-overlay enrichment not yet run on this property. We'll verify before listing.",
            "source": "Gold Coast City Council planning scheme (deferred)",
        })

    # 2. Insurance flood zone (ICA)
    if zd:
        ica = zd.get("ica_flood_zones", {}) or {}
        in_zone = zd.get("in_any_ica_zone")
        if in_zone is False:
            items.append({
                "category": "Insurance flood zone (ICA)",
                "status": "NO ZONE",
                "status_color": "green",
                "detail": "Property is NOT in any Insurance Council of Australia flood probability zone — insurer-assessed risk is at the lowest tier.",
                "source": "Insurance Council of Australia (ICA) flood probability mapping",
            })
        elif in_zone is True:
            zones_in = [k for k, v in ica.items() if v]
            zones_label = ", ".join(zones_in).replace("_", " ") if zones_in else "ICA zone"
            items.append({
                "category": "Insurance flood zone (ICA)",
                "status": zones_label.upper(),
                "status_color": "amber",
                "detail": f"Property sits within ICA's {zones_label} probability zone — insurer pricing and underwriting will reflect this.",
                "source": "Insurance Council of Australia (ICA) flood probability mapping",
            })

    # 3. Zoning
    if zd.get("zone"):
        items.append({
            "category": "Zoning",
            "status": str(zd["zone"]).upper(),
            "status_color": "neutral",
            "detail": f"Cadastral area {zd.get('cadastral_area_sqm', '?')} sqm, lot/plan {zd.get('lot_plan', '?')}.",
            "source": "Gold Coast City Council planning scheme",
        })

    # 4. Heritage listing
    if zd:
        listed = zd.get("heritage_listed")
        items.append({
            "category": "Heritage listing",
            "status": "LISTED" if listed else "NOT LISTED",
            "status_color": "amber" if listed else "green",
            "detail": (
                "Property is heritage-listed; modifications subject to heritage approval."
                if listed else
                "Property is not on any heritage register — no heritage-related modification constraints."
            ),
            "source": "Queensland heritage register",
        })

    # 5. Beach / coastal proximity (BW + similar)
    beach_km = prop.get("nearest_beach_distance_km")
    if beach_km is not None:
        beach_name = prop.get("nearest_beach_name") or "the nearest beach"
        items.append({
            "category": "Coastal proximity",
            "status": f"{beach_km:.1f} km",
            "status_color": "green",
            "detail": f"Direct distance to {beach_name}: {beach_km:.1f} km.",
            "source": "Geocoded distance to mapped beach",
        })

    # 6. Traffic & street position (satellite)
    sa_categories = sa.get("categories", {}) or {}
    setting_cat = sa_categories.get("overall_setting", {}) or {}
    road_cat = sa_categories.get("road_proximity", {}) or {}
    traffic_signal = (road_cat.get("category") or "").lower()
    setting_signal = (setting_cat.get("category") or "").lower()
    if traffic_signal or setting_signal:
        narrative = sa.get("narrative", {}) or {}
        narrative_text = narrative.get("road_proximity") or narrative.get("overall_setting") or ""
        if traffic_signal in ("main_road", "highway", "arterial"):
            status, color = "EXPOSED", "amber"
        elif traffic_signal in ("standard_street", "local"):
            status, color = "STANDARD STREET", "green"
        elif traffic_signal in ("cul_de_sac_head", "cul_de_sac"):
            status, color = "CUL-DE-SAC", "green"
        else:
            status, color = "ASSESSED", "neutral"
        items.append({
            "category": "Traffic & street position",
            "status": status,
            "status_color": color,
            "detail": (narrative_text or "Aerial assessment of street type, frontage and traffic exposure.")[:280],
            "source": "Aerial imagery analysis",
        })

    # 7. School proximity (closest primary + secondary)
    primary = (pois.get("primary_school") or [{}])[0] if pois.get("primary_school") else None
    secondary = (pois.get("secondary_school") or [{}])[0] if pois.get("secondary_school") else None
    if primary or secondary:
        chunks = []
        if primary:
            chunks.append(f"{primary.get('name')} ({primary.get('distance_m','?')}m walk)")
        if secondary:
            chunks.append(f"{secondary.get('name')} ({secondary.get('distance_m','?')}m walk)")
        items.append({
            "category": "School proximity",
            "status": "CLOSEST SCHOOLS NAMED",
            "status_color": "neutral",
            "detail": (
                "Closest schools by walking distance: "
                + "; ".join(chunks)
                + ". State-school catchment status should be confirmed via the Queensland Department of Education catchment finder."
            ),
            "source": "Aerial proximity + Queensland Department of Education catchment finder (link)",
        })

    # 8. Property tenure
    tenure = prop.get("property_tenure_desc") or prop.get("property_tenure")
    if tenure:
        items.append({
            "category": "Property tenure",
            "status": str(tenure).upper(),
            "status_color": "green",
            "detail": "Tenure as registered on the Queensland title.",
            "source": "Queensland Land Registry",
        })

    # 9. Body corporate / strata (units only — flagged via property_type or is_strata_title)
    is_strata = bool(prop.get("is_strata_title")) or "unit" in (prop.get("property_type") or "").lower() or "townhouse" in (prop.get("property_type") or "").lower()
    if is_strata:
        items.append({
            "category": "Body corporate / strata",
            "status": "DISCLOSURE REQUIRED",
            "status_color": "amber",
            "detail": "As a strata-titled property, the body corporate disclosure (sinking fund balance, recent special levies, scheduled major works) sits in the contract pack. We summarise it before listing — it is the most common contract-stage delay for unit sales.",
            "source": "Body corporate disclosure (Form 13)",
        })

    # 10. Council development applications within 500m — DEFERRED
    items.append({
        "category": "Council DAs within 500m",
        "status": "NOT YET ASSESSED",
        "status_color": "neutral",
        "detail": "Live development-application monitoring within 500m is on our roadmap. Recommend a PD Online check before contract signature — we'll run this with you if you list.",
        "source": "Gold Coast City Council PD Online (deferred)",
    })

    # 11. Easements / encumbrances — DEFERRED
    items.append({
        "category": "Easements / encumbrances",
        "status": "TITLE SEARCH",
        "status_color": "neutral",
        "detail": "Easements (drainage, utilities), restrictive covenants, and registered encumbrances appear on the title search. We commission this before listing as part of the campaign-prep checklist.",
        "source": "Queensland Land Registry title search (commissioned at listing)",
    })

    return {
        "intro": (
            "Buyers Google flood, schools, council DAs, and easements in their first 30 minutes "
            "of considering your home. We do those searches first — both to surface anything "
            "material before listing, and to shorten the buyer's decision time when they inspect."
        ),
        "items": items,
        "closing": (
            "Most of these checks have a status of CLEAR, NO ZONE, or STANDARD STREET — that is "
            "useful evidence for the listing. Where a status is NOT YET ASSESSED, we run the check "
            "before the campaign starts. Where it is amber or red, we surface it in the listing "
            "narrative rather than letting a buyer discover it late in the contract."
        ),
    }


# ---------------------------------------------------------------------------
# M22 — Outcome projection (overpricing penalty math)
# ---------------------------------------------------------------------------
def build_outcome_projection(listing_low: int, listing_high: int, selling_low: int, selling_high: int, suburb: str) -> dict:
    """Compute side-by-side outcome scenarios for correctly-priced vs overpriced listings.

    Research basis (locked):
      Taylor 1999            — properties >10% overpriced take 2-5x longer to sell
      Zillow Research 2019   — n=25,000; 12%+ overpriced are 50% less likely to sell in 60 days
      Knight 2002            — price-reduction stigma reduces final sale price by ~3-5% vs correctly priced equivalent
      Anglin/Rutherford/Springer 2003 — overpricing >10% triggers multiple price-reduction spiral

    Returns:
    {
      'correct': {'list_price', 'estimated_dom_days', 'final_sale_price', 'marketing_cost', 'net_to_vendor', 'description'},
      'overpriced': {... same keys ..., 'overpricing_pct'},
      'difference': {'price_delta', 'dom_delta_days', 'pct_difference'},
      'sources': [<citations>],
    }
    """
    # Inputs
    list_mid = (listing_low + listing_high) // 2
    sell_mid = (selling_low + selling_high) // 2
    dom = SUBURB_DOM_DAYS.get(suburb, _DEFAULT_DOM)

    # Marketing cost — illustrative baseline for a 4-week campaign.
    # Standard: REA Premiere + photography + signboard + signage + virtual tour ≈ $4,500
    # Extended (overpriced): repeat photography + price-reduction processing + signage refresh ≈ $7,000
    correct_marketing = 4500
    overpriced_marketing = 7000

    # SCENARIO A — correctly priced day 1
    correct_list = list_mid
    correct_final_low = sell_mid - 10000  # tight band around midpoint
    correct_final_high = sell_mid + 25000
    correct_final = (correct_final_low + correct_final_high) // 2
    correct_net = correct_final - correct_marketing
    correct_dom = dom

    # SCENARIO B — overpriced 12% above the recommended listing midpoint
    overpricing_pct = 12
    overpriced_list = int(list_mid * (1 + overpricing_pct / 100))
    # Taylor 1999 mid-range of 2-5x DOM; use 3x as a middle estimate
    overpriced_dom = dom * 3
    # Knight 2002 stigma effect: ~5% below correctly-priced equivalent final
    overpriced_final = int(correct_final * 0.95)
    overpriced_net = overpriced_final - overpriced_marketing

    delta_price = correct_net - overpriced_net
    delta_dom = overpriced_dom - correct_dom

    return {
        "correct": {
            "label": "Priced correctly from day one",
            "list_price": correct_list,
            "list_price_fmt": fmt(correct_list),
            "estimated_dom_days": correct_dom,
            "final_sale_price": correct_final,
            "final_sale_fmt": fmt(correct_final),
            "marketing_cost": correct_marketing,
            "marketing_cost_fmt": fmt(correct_marketing),
            "net_to_vendor": correct_net,
            "net_to_vendor_fmt": fmt(correct_net),
            "description": f"Listed within the recommended range, sells in line with {suburb}'s typical {correct_dom}-day window. Marketing budget covers a 4-week campaign with professional photography, REA Premiere, and standard signage.",
        },
        "overpriced": {
            "label": f"Priced {overpricing_pct}% above recommendation",
            "overpricing_pct": overpricing_pct,
            "list_price": overpriced_list,
            "list_price_fmt": fmt(overpriced_list),
            "estimated_dom_days": overpriced_dom,
            "final_sale_price": overpriced_final,
            "final_sale_fmt": fmt(overpriced_final),
            "marketing_cost": overpriced_marketing,
            "marketing_cost_fmt": fmt(overpriced_marketing),
            "net_to_vendor": overpriced_net,
            "net_to_vendor_fmt": fmt(overpriced_net),
            "description": f"Listed {overpricing_pct}% above the recommended range. Sits on the market roughly 3x longer (Taylor 1999), takes a price reduction at week 5-6, and finally sells at approximately 95% of the correctly-priced final price (Knight 2002 stigma effect). Marketing costs rise from extended campaign duration and price-reduction processing.",
        },
        "difference": {
            "price_delta": delta_price,
            "price_delta_fmt": fmt(delta_price),
            "dom_delta_days": delta_dom,
            "pct_difference": round(delta_price / max(correct_net, 1) * 100, 1),
        },
        "sources": [
            "Taylor (1999) — overpriced properties take 2-5x longer to sell",
            "Knight (2002) — price-reduction stigma reduces final sale price by 3-5%",
            "Anglin, Rutherford & Springer (2003) — overpricing triggers multiple-reduction spiral",
            "Zillow Research (2019, n=25,000) — 12%+ overpriced are 50% less likely to sell in 60 days",
        ],
    }


# ---------------------------------------------------------------------------
# M18 — Pre-sale Recommendations data builder
# ---------------------------------------------------------------------------
# ---------------------------------------------------------------------------
# Scarcity statistics — feature-level "N sold in 12 months" hooks
# ---------------------------------------------------------------------------
def compute_scarcity_stats(client, prop: dict, suburb_key: str, top_comps: list) -> dict:
    """Sample-relative scarcity context for the subject property.

    We never had a census of all sold homes — only a labelled indicative sample
    of Domain-scraped sales (system_monitor.sample_manifest). So instead of
    absolute "only K of M sold" census counts, this returns where the subject
    sits vs the typical *sampled* home (percentile) and what share of the sample
    carries its standout feature combination — every statement disclosing the
    sample size, window, and source. Backed by the canonical golden-record layer
    (Gold_Coast.property_attributes), so each number is reproducible via
    scripts/property_reports/verify_claim.py.

    Returns the same {total_12m_sales, statements, subject_features} keys the
    editorial prompt consumes, plus a structured `sample_context` block.
    """
    if str(ROOT) not in sys.path:
        sys.path.insert(0, str(ROOT))
    try:
        from scripts.property_reports import canonical_resolver as _cr
        from scripts.property_reports import sample_context as _sc
    except Exception as e:
        print(f"  scarcity: sample-context unavailable ({e}); emitting empty block")
        return {"total_12m_sales": 0, "statements": [], "subject_features": {}}

    # Resolve the subject's canonical attributes + scarcity hits from whatever
    # the property doc carries (no write — just the in-memory golden record).
    try:
        rec = _cr.build_record(prop, suburb_key, _cr.load_spec(), in_sample=False)
        ctx = _sc.compute_context(rec["attributes"], rec["scarcity_hits"],
                                  suburb=suburb_key,
                                  same_type=rec.get("property_type"),
                                  client=client)
        statements = _sc.phrase(ctx)
    except Exception as e:
        print(f"  scarcity: sample-relative context failed ({e})")
        return {"total_12m_sales": 0, "statements": [], "subject_features": {}}

    a = rec["attributes"]
    return {
        # cohort size of the disclosed sample (NOT a census total)
        "total_12m_sales": ctx["cohort"]["n"],
        "sample_context": ctx,
        "subject_features": {
            "beds": a.get("bedrooms"), "cars": a.get("car_spaces"),
            "land": a.get("land_size_sqm"), "internal": a.get("floor_area_sqm"),
            "condition": a.get("condition_score"), "pool": a.get("pool_present"),
        },
        "statements": statements,
    }


def build_pre_sale_roi(prop: dict, suburb_display: str) -> dict:
    """Load pre-sale ROI items from config/pre_sale_roi.yaml, filter by conditional_on.

    Each item's `conditional_on` is a Python expression evaluated against:
      condition (overall_condition_score, default 7), pool_present (bool), suburb (str).
    Items without `conditional_on` always render.
    Returns {} if YAML can't be loaded — template guards via {% if %}.
    """
    config_path = ROOT / "config" / "pre_sale_roi.yaml"
    if not config_path.exists():
        return {}
    try:
        import yaml
        cfg = yaml.safe_load(config_path.read_text())
    except Exception as e:
        print(f"  [WARN] pre_sale_roi.yaml load failed: {e}")
        return {}

    # Per-suburb override (not yet used; reserved for tier multipliers later)
    suburb_key = suburb_display.lower().replace(" ", "_")
    section = cfg.get(suburb_key) or cfg.get("default") or {}
    if not section:
        return {}

    pvd = prop.get("property_valuation_data", {}) or {}
    overview = pvd.get("property_overview", {}) or {}
    condition = overview.get("overall_condition_score") or 7
    pool_present = bool((pvd.get("outdoor", {}) or {}).get("pool_present"))
    eval_ctx = {
        "condition": condition,
        "pool_present": pool_present,
        "suburb": suburb_display,
    }

    filtered = []
    for item in section.get("items", []) or []:
        cond_expr = item.get("conditional_on")
        if cond_expr:
            try:
                if not eval(cond_expr, {"__builtins__": {}}, eval_ctx):
                    continue
            except Exception:
                # Keep the item if the expression fails to parse — better to over-include than drop
                pass
        filtered.append({
            "action": item.get("action", ""),
            "cost": item.get("cost", ""),
            "recovery": item.get("recovery", ""),
            "note": item.get("note", "").strip(),
        })

    return {
        "items": filtered,
        "closing": section.get("closing", "").strip() or None,
    }


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
                sell_timeline: str = "", sell_timeline_label: str = "",
                rates: dict = None, pipeline_record: dict | None = None,
                positioning: bool = False) -> str:
    env = Environment(loader=FileSystemLoader(str(TEMPLATE_DIR)))
    template = env.get_template("seller_report_v2.html")
    rates = rates or {}

    # Phase A appraisal template system — compute Section 01 right HTML.
    # Graceful fallback: if anything goes wrong, leave it None and the
    # template falls back to the legacy scarcity-banner.
    section_01_right_html = None
    try:
        if pipeline_record and pipeline_record.get("highlight_chosen_key"):
            from scripts.appraisal_template import render as _render
            editorial_overrides = pipeline_record.get("section_01_editorial_overrides") or {}
            section_01_right_html = _render.render_section_01_right_html(
                str(prop["_id"]),
                highlight_key=pipeline_record["highlight_chosen_key"],
                editorial_overrides=editorial_overrides,
                write_substantiation=True,
            )
    except Exception as e:
        print(f"[WARN] §01 right template render failed, using legacy banner: {e}")
        section_01_right_html = None

    # ── Positioning-report variant (cold off-market recipient) ──────────────
    # Retitle + derive the live-version URL and a vector QR for the opener page.
    # When positioning=False these vars are inert (template falls back to default).
    if positioning:
        report_title = "Private Property Positioning Report"
        report_title_short = "Property Positioning Report"
    else:
        report_title = "Property Position Report"
        report_title_short = "Property Position Report"
    live_url, qr_live_uri = "", ""
    if positioning:
        import re as _re
        _addr = (prop.get("street_address") or prop.get("address") or "").split(",")[0]
        _slug = _re.sub(r"[^a-z0-9]+", "-", f"{_addr} {suburb_display}".strip().lower()).strip("-")
        live_url = f"https://fieldsestate.com.au/your-home/{_slug}#home" if _slug else "https://fieldsestate.com.au"
        try:
            import segno
            qr_live_uri = segno.make(live_url, error="m").svg_data_uri(
                dark="#22382C", light="#ffffff", border=3, scale=1)
        except Exception as _e:
            print(f"  [WARN] positioning QR generation failed: {_e}")

    pvd = prop.get("property_valuation_data", {})
    fpa = prop.get("floor_plan_analysis", {})

    # Derive valuation ranges from comps
    adj_prices = [c["adjusted_total"] for c in top_comps if c.get("adjusted_total")]
    val_low = min(adj_prices) if adj_prices else 0
    val_high = max(adj_prices) if adj_prices else 0
    val_mid = int(sum(adj_prices) / len(adj_prices)) if adj_prices else 0
    # Listing range: tighter band around the middle — recommended pricing bracket
    spread = val_high - val_low
    listing_low = int(val_mid - spread * 0.2) if val_mid else 0
    listing_high = int(val_mid + spread * 0.15) if val_mid else 0
    # Round to nearest $5,000 for clean presentation
    listing_low = round(listing_low / 5000) * 5000
    listing_high = round(listing_high / 5000) * 5000

    raw_street = prop.get("street_address") or prop.get("address", "")
    # Stack the street address onto multiple lines for the cover copper tab.
    # "13 Terrace Court" → "13<br>Terrace<br>Court"
    _stack_words = raw_street.split()
    street_address_stacked = "<br>".join(_stack_words) if _stack_words else raw_street
    report_date_now = datetime.now(AEST)

    context = {
        "client_name": client_name,
        "report_date": report_date_now.strftime("%d %B %Y"),
        "report_date_upper": report_date_now.strftime("%d %B %Y").upper(),
        "street_address": raw_street,
        "street_address_stacked": street_address_stacked,
        "icons_dir": f"file://{TEMPLATE_DIR / 'icons'}",
        "suburb": suburb_display,
        "postcode": prop.get("postcode", ""),
        "bedrooms": prop.get("bedrooms", "?"),
        "bathrooms": prop.get("bathrooms", "?"),
        "land_size": int(float(prop.get("land_size_sqm") or prop.get("lot_size_sqm") or 0)),
        "internal_area": fpa.get("internal_floor_area", {}).get("value") or prop.get("floor_area_sqm") or "?",
        "condition_score": pvd.get("property_overview", {}).get("overall_condition_score") or "?",
        # Feature pills — conditional in the template so they only render when the data supports them.
        # Pool: read directly from valuation data. Dual living: check several plausible Mongo paths
        # plus a top-level prop flag, defaulting False if no signal — better to under-claim than mis-claim.
        "has_pool": bool(pvd.get("outdoor", {}).get("pool_present")),
        "has_dual_living": bool(
            pvd.get("layout", {}).get("dual_living")
            or pvd.get("dual_living")
            or prop.get("dual_living")
            or prop.get("has_dual_living")
        ),
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
        "not_ideal_for": editorial.get("not_ideal_for", []),
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
        # Phase 1 modules (M6 + M11) — new fields, optional in older cached editorials.
        # Template guards via {% if %} so old editorial JSONs render unchanged.
        "limits_of_evidence": editorial.get("limits_of_evidence"),
        "morning_in_this_home": editorial.get("morning_in_this_home", ""),
        # Phase 2 / Sprint 2 modules (M13 + M22) — pure data, no AI involvement.
        # Template guards via {% if %} for backwards compat with older renders.
        "risk_data": build_risk_data(prop, suburb_display),
        "outcome_projection": build_outcome_projection(
            listing_low, listing_high, val_low, val_high, suburb_display,
        ),
        # Print Master modules (M4 methodology rates, M18 pre-sale, M21 negotiation).
        # Each guarded with {% if %} so a digital-only render isn't broken.
        "rate_land": rates.get("land_per_sqm"),
        "rate_floor": rates.get("floor_per_sqm"),
        "rate_bed": fmt(rates.get("per_bedroom", 0)).replace("$",""),
        "rate_bath": fmt(rates.get("per_bathroom", 0)).replace("$",""),
        "rate_car": fmt(rates.get("per_car_space", 0)).replace("$",""),
        "rate_pool": fmt(rates.get("per_pool", 0)).replace("$",""),
        "rate_reno": fmt(rates.get("per_renovation_level", 0)).replace("$",""),
        "pre_sale_roi": build_pre_sale_roi(prop, suburb_display),
        "negotiation_plan": editorial.get("negotiation_plan"),
        "research_stats": RESEARCH_STATS,
        "total_sold_tracked": TOTAL_SOLD_TRACKED,
        # Photos — emit empty string (not "file://") when absent so {% if %} guards work
        "hero_photo": (f"file://{photo_paths['hero']}" if photo_paths.get('hero') else ""),
        "exterior_photo": (f"file://{photo_paths['exterior']}" if photo_paths.get('exterior') else ""),
        "kitchen_photo": (f"file://{photo_paths['kitchen']}" if photo_paths.get('kitchen') else ""),
        "living_photo": (f"file://{photo_paths['living']}" if photo_paths.get('living') else ""),
        "aerial_photo": (f"file://{photo_paths['aerial']}" if photo_paths.get('aerial') else ""),
        "pool_photo": (f"file://{photo_paths['pool']}" if photo_paths.get('pool') else ""),
        "logo_path": f"file://{TEMPLATE_DIR / 'fields-logo-transparent.png'}",
        "logo_white_path": f"file://{TEMPLATE_DIR / 'fields-logo-white.png'}",
        # Satellite analysis — prefer the annotated tile (bounding boxes + Fields
        # drop pin) when the inline_satellite resolver has produced one. Falls
        # back to the raw Google Maps tile when annotation hasn't run yet.
        "satellite_image_url": (
            prop.get("satellite_analysis", {}).get("annotated_image_url")
            or prop.get("satellite_analysis", {}).get("satellite_image_url", "")
        ),
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
        # Phase A appraisal template system — new §01 right HTML block, or
        # None to fall back to the legacy scarcity-banner.
        "section_01_right_html": section_01_right_html,
        # Positioning-report variant fields (inert unless positioning=True)
        "positioning": positioning,
        "report_title": report_title,
        "report_title_short": report_title_short,
        "live_url": live_url,
        "qr_live_uri": qr_live_uri,
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
    parser.add_argument("--skip-ai", action="store_true",
                        help="Skip Claude editorial; use _minimal_editorial fallback")
    parser.add_argument("--reuse-editorial", metavar="PATH",
                        help="Path to a saved editorial JSON to load instead of regenerating "
                             "(skips Claude — useful for visual/template iteration without burning credits)")
    parser.add_argument("--strict", action="store_true",
                        help="Run scripts/editorial_review.py against the editorial JSON before render; "
                             "abort if any FAIL-severity check fails")
    parser.add_argument("--positioning", action="store_true",
                        help="Positioning-report variant for cold off-market recipients (no prior contact): "
                             "retitles to 'Private Property Positioning Report' and adds a 'why you've "
                             "received this' opener. Warm-lead appraisal render is unchanged without this flag.")
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
        pipeline = None  # manual mode has no pipeline record (fixes UnboundLocalError in render_html call)
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

    # 4b. Compute scarcity stats — feature-level "N sold in 12 months" hooks for feature_positioning
    print("  Computing scarcity statistics...")
    scarcity_stats = compute_scarcity_stats(db_client, prop, suburb_key, top_comps)

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

    # 8. AI editorial — three modes:
    #    --reuse-editorial PATH : load JSON from disk (no AI call, no $$ burn)
    #    --skip-ai              : use _minimal_editorial fallback (placeholder content — for testing only)
    #    default                : call Claude and cache the JSON next to the PDF for future reuse
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    slug = address.lower().replace(" ", "-").replace(",", "").replace("'", "")
    pdf_name = f"{datetime.now(AEST).strftime('%Y-%m-%d')}_{slug}_{client_name.lower()}_v2.pdf"
    pdf_path = OUTPUT_DIR / pdf_name
    editorial_json_path = pdf_path.with_name(pdf_path.stem.replace("_v2", "") + "_editorial.json")

    if args.reuse_editorial:
        reuse_path = Path(args.reuse_editorial)
        if not reuse_path.exists():
            sys.exit(f"[ERROR] --reuse-editorial path not found: {reuse_path}")
        print(f"  Loading editorial from {reuse_path} (no AI call)")
        editorial = json.loads(reuse_path.read_text())
    elif args.skip_ai:
        editorial = _minimal_editorial(prop, top_comps, market_stats)
    else:
        print("  Generating editorial via Claude...")
        editorial = generate_editorial(prop, top_comps, market_stats, rates, suburb_display, scarcity_stats=scarcity_stats)
        # Regenerate the morning_in_this_home narrative if the length is out of range.
        # Word-count compliance varies between properties (BW kept undershooting on premium-property
        # density), so we use a targeted single-field retry rather than tuning the whole-prompt
        # blunt instrument. ~$0.50 per retry, max 2 retries.
        if not args.skip_ai and editorial.get("morning_in_this_home"):
            try:
                sys.path.insert(0, str(Path(__file__).resolve().parent / "property_reports"))
                from _claude_backend import get_client_and_model
                client_anth, _ = get_client_and_model(EDITORIAL_MODEL)
                if client_anth is None:
                    raise RuntimeError("no Claude backend configured")
                editorial["morning_in_this_home"] = regenerate_morning_narrative(
                    client_anth, prop, editorial["morning_in_this_home"]
                )
            except Exception as e:
                print(f"  [WARN] M11 regen loop unavailable: {e}")
        # Cache the editorial alongside the PDF so future renders can --reuse-editorial it.
        try:
            editorial_json_path.write_text(json.dumps(editorial, indent=2, ensure_ascii=False))
            print(f"  Editorial cached: {editorial_json_path}")
        except Exception as e:
            print(f"  [WARN] Could not cache editorial JSON: {e}")

    # 8b. Optional editorial review gate.
    # Always informational; only blocks if --strict.
    try:
        sys.path.insert(0, str(ROOT / "scripts"))
        from editorial_review import validate_editorial
        review = validate_editorial(editorial)
        fail_n = len(review.fails)
        warn_n = len(review.warns)
        if fail_n or warn_n:
            print(f"  Editorial review: {fail_n} fail, {warn_n} warn")
            for c in review.fails:
                print(f"    FAIL  {c.name}: {c.detail}")
            for c in review.warns:
                print(f"    warn  {c.name}: {c.detail}")
        else:
            print(f"  Editorial review: PASS ({len(review.checks)}/{len(review.checks)})")
        if args.strict and not review.passed:
            sys.exit("[ERROR] Editorial review failed under --strict; aborting render.")
    except ImportError:
        pass  # editorial_review module not available; skip gate

    # 9. Render HTML
    timeline_labels = {"asap": "ASAP", "1-3months": "1\u20133 Months", "3-6months": "3\u20136 Months", "not-sure": "Flexible"}
    print("  Rendering HTML...")
    html = render_html(prop, client_name, top_comps, room_assessments, editorial,
                       market_stats, photo_paths, suburb_display,
                       sell_timeline=sell_timeline,
                       sell_timeline_label=timeline_labels.get(sell_timeline, sell_timeline),
                       rates=rates,
                       pipeline_record=pipeline,
                       positioning=args.positioning)
    html_path = work_dir / "report.html"
    html_path.write_text(html)

    # 10. Convert to PDF (pdf_path already computed in step 8 for editorial caching)
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
