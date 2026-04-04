#!/usr/bin/env python3
"""
Generate Property Positioning Analysis
========================================
Applies the Fields Positioning Playbook v5.0 to individual properties using
a single Claude Opus 4.6 call per property. Produces a two-tier output:

  - public: data-backed statements (scarcity, $/sqm, buyer profile, brackets)
  - gated:  strategic recommendations (pricing, pre-sale, agency, campaign)

Pre-computes quantitative data ($/sqm, scarcity counts, bracket analysis,
street stats) in Python before the API call — the model synthesises, not
calculates.

Usage:
    # Single property:
    python generate_positioning_analysis.py --slug 21-indooroopilly-court-robina

    # By address:
    python generate_positioning_analysis.py --address "21 Indooroopilly Court"

    # All properties that already have ai_analysis but no positioning:
    python generate_positioning_analysis.py --backfill

    # Dry run (print prompt, no API call):
    python generate_positioning_analysis.py --slug ... --dry-run

    # Force regenerate:
    python generate_positioning_analysis.py --slug ... --force
"""

from __future__ import annotations

import argparse
import json
import math
import os
import re
import statistics
import sys
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

import anthropic
from pymongo import MongoClient

REPO_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO_ROOT))

from shared.monitor_client import MonitorClient
from shared.ru_guard import cosmos_retry, sleep_with_jitter

TARGET_SUBURBS = ["robina", "varsity_lakes", "burleigh_waters"]

MODEL = "claude-opus-4-6"
MAX_TOKENS = 8000  # Structured JSON output needs room

# Portal price brackets (Domain/REA standard search filters)
PRICE_BRACKETS = [
    (0, 400_000, "Under $400K"),
    (400_000, 500_000, "$400K-$500K"),
    (500_000, 600_000, "$500K-$600K"),
    (600_000, 700_000, "$600K-$700K"),
    (700_000, 800_000, "$700K-$800K"),
    (800_000, 900_000, "$800K-$900K"),
    (900_000, 1_000_000, "$900K-$1M"),
    (1_000_000, 1_250_000, "$1M-$1.25M"),
    (1_250_000, 1_500_000, "$1.25M-$1.5M"),
    (1_500_000, 2_000_000, "$1.5M-$2M"),
    (2_000_000, 2_500_000, "$2M-$2.5M"),
    (2_500_000, 3_000_000, "$2.5M-$3M"),
    (3_000_000, 5_000_000, "$3M-$5M"),
    (5_000_000, 999_999_999, "$5M+"),
]


# ---------------------------------------------------------------------------
# Price parsing
# ---------------------------------------------------------------------------

def parse_price_numeric(prop: Dict) -> Optional[float]:
    """Extract a numeric price from a property document."""
    # Try direct numeric fields
    for key in ("price_numeric", "price_value"):
        v = prop.get(key)
        if v and isinstance(v, (int, float)) and v > 50_000:
            return float(v)

    # Try valuation as proxy
    val = prop.get("valuation_data", {}).get("confidence", {}).get("reconciled_valuation")
    if val and val > 50_000:
        return float(val)

    # Parse price string
    price_str = str(prop.get("price_display") or prop.get("price") or "")
    m = re.search(r'\$?([\d,]+)', price_str.replace(',', '').replace(' ', ''))
    if m:
        try:
            v = float(m.group(1).replace(',', ''))
            if v > 50_000:
                return v
        except ValueError:
            pass

    return None


def get_floor_area(prop: Dict) -> Optional[float]:
    """Get internal floor area in sqm."""
    # Prefer enriched internal floor area
    internal = prop.get("enriched_data", {}).get("floor_area_sqm")
    if internal and internal > 30:
        return float(internal)

    # Fall back to total floor area
    total = (
        prop.get("total_floor_area")
        or (prop.get("floor_plan_analysis") or {}).get("total_floor_area_sqm")
        or (prop.get("house_plan") or {}).get("floor_area_sqm")
        or prop.get("floor_area_sqm")
    )
    if total and total > 30:
        return float(total)

    return None


# ---------------------------------------------------------------------------
# Pre-computation layer — all done in Python before the API call
# ---------------------------------------------------------------------------

def parse_sale_price(val) -> Optional[float]:
    """Parse a sale_price string like '$1,520,000' to float."""
    if isinstance(val, (int, float)) and val > 50_000:
        return float(val)
    if isinstance(val, str):
        m = re.search(r'[\$]?([\d,]+)', val.replace(' ', ''))
        if m:
            try:
                v = float(m.group(1).replace(',', ''))
                if v > 50_000:
                    return v
            except ValueError:
                pass
    return None


def compute_price_per_sqm(prop: Dict, db, suburb: str) -> Dict:
    """Compute $/sqm for the property and suburb median."""
    price = parse_price_numeric(prop)
    floor_area = get_floor_area(prop)

    if not price or not floor_area:
        return {
            "property_rate": None,
            "suburb_median_rate": None,
            "position": "unknown",
            "position_pct": None,
            "data_available": False,
        }

    property_rate = round(price / floor_area, 0)

    # Suburb median $/sqm from sold properties
    # Sold records use sale_price (string) and total_floor_area
    sold_query = {
        "listing_status": "sold",
        "sale_price": {"$exists": True},
        "total_floor_area": {"$exists": True, "$gt": 30},
    }
    sold_props = cosmos_retry(
        lambda: list(db[suburb].find(sold_query, {
            "sale_price": 1, "sold_price": 1, "total_floor_area": 1,
            "enriched_data.floor_area_sqm": 1,
        }).limit(400)),
        f"sqm_sold_{suburb}",
    )

    rates = []
    for s in sold_props:
        sp = parse_sale_price(s.get("sale_price")) or parse_sale_price(s.get("sold_price"))
        fa = s.get("enriched_data", {}).get("floor_area_sqm") or s.get("total_floor_area", 0)
        if sp and sp > 50_000 and fa and fa > 30:
            rates.append(sp / fa)

    if not rates:
        return {
            "property_rate": property_rate,
            "suburb_median_rate": None,
            "position": "unknown",
            "position_pct": None,
            "data_available": True,
            "n_sold_with_floor_area": 0,
        }

    suburb_median = statistics.median(rates)
    diff_pct = round(((property_rate - suburb_median) / suburb_median) * 100, 1)

    if diff_pct > 2:
        position = "above"
    elif diff_pct < -2:
        position = "below"
    else:
        position = "at"

    return {
        "property_rate": round(property_rate),
        "suburb_median_rate": round(suburb_median),
        "position": position,
        "position_pct": abs(diff_pct),
        "data_available": True,
        "n_sold_with_floor_area": len(rates),
    }


def compute_scarcity(prop: Dict, db, suburb: str) -> Dict:
    """Count similar properties currently for sale in the suburb."""
    beds = prop.get("bedrooms")
    prop_type = prop.get("classified_property_type") or prop.get("property_type", "House")

    features = prop.get("features") or []
    features_lower = [f.lower() for f in features] if features else []
    has_pool = any("pool" in f for f in features_lower) or bool(
        prop.get("satellite_analysis", {}).get("categories", {}).get("pool_visible")
    )

    lot_size = prop.get("lot_size_sqm") or prop.get("land_area", 0)

    # Build feature combos to count
    base_query = {"listing_status": "for_sale", "property_type": prop_type}

    # Exact bed match
    bed_query = {**base_query, "bedrooms": beds} if beds else base_query
    bed_count = cosmos_retry(
        lambda: db[suburb].count_documents(bed_query),
        f"scarcity_beds_{suburb}",
    )

    # Beds + pool
    pool_count = None
    if has_pool and beds:
        pool_query = {
            **base_query, "bedrooms": beds,
            "$or": [
                {"features": {"$regex": "pool", "$options": "i"}},
                {"satellite_analysis.categories.pool_visible": True},
            ],
        }
        pool_count = cosmos_retry(
            lambda: db[suburb].count_documents(pool_query),
            f"scarcity_pool_{suburb}",
        )

    # Large block (>700sqm)
    large_block_count = None
    if lot_size and lot_size > 700:
        large_query = {**base_query, "lot_size_sqm": {"$gte": 700}}
        if beds:
            large_query["bedrooms"] = beds
        large_block_count = cosmos_retry(
            lambda: db[suburb].count_documents(large_query),
            f"scarcity_large_{suburb}",
        )

    # Find the most compelling (lowest count) scarcity combo
    combos = []
    if beds:
        combos.append({"count": bed_count, "combo": f"{beds}-bed {prop_type.lower()}"})
    if pool_count is not None:
        combos.append({"count": pool_count, "combo": f"{beds}-bed {prop_type.lower()} with pool"})
    if large_block_count is not None:
        size_desc = f"{int(lot_size)}sqm+" if lot_size else "large"
        combos.append({"count": large_block_count, "combo": f"{beds}-bed {prop_type.lower()} on {size_desc} block"})

    # Pick the rarest
    if combos:
        best = min(combos, key=lambda x: x["count"])
    else:
        best = {"count": bed_count or 0, "combo": prop_type.lower()}

    return {
        "best_combo": best["combo"],
        "best_count": best["count"],
        "all_combos": combos,
        "has_pool": has_pool,
        "lot_size": lot_size,
    }


def compute_bracket_analysis(prop: Dict, db, suburb: str) -> Dict:
    """Count competing listings in each portal price bracket."""
    price = parse_price_numeric(prop)

    # Count active listings per bracket
    active_listings = cosmos_retry(
        lambda: list(db[suburb].find(
            {"listing_status": "for_sale"},
            {"price": 1, "price_display": 1, "price_numeric": 1, "price_value": 1,
             "valuation_data.confidence.reconciled_valuation": 1},
        )),
        f"brackets_{suburb}",
    )

    bracket_counts = {}
    property_bracket = None

    for low, high, label in PRICE_BRACKETS:
        bracket_counts[label] = 0

    for listing in active_listings:
        lp = parse_price_numeric(listing)
        if not lp:
            continue
        for low, high, label in PRICE_BRACKETS:
            if low <= lp < high:
                bracket_counts[label] = bracket_counts.get(label, 0) + 1
                break

    if price:
        for low, high, label in PRICE_BRACKETS:
            if low <= price < high:
                property_bracket = label
                break

    return {
        "property_bracket": property_bracket,
        "competing_in_bracket": bracket_counts.get(property_bracket, 0) if property_bracket else None,
        "all_brackets": {k: v for k, v in bracket_counts.items() if v > 0},
        "total_active": len(active_listings),
    }


def compute_street_stats(prop: Dict, db, suburb: str) -> Dict:
    """Sold properties on the same street vs suburb median."""
    street = prop.get("STREET_NAME", "")
    street_type = prop.get("STREET_TYPE", "")

    if not street:
        # Try to parse from address
        addr = prop.get("address", "")
        parts = addr.split(",")[0].strip().split()
        if len(parts) >= 3:
            # "21 Indooroopilly Court" -> street=Indooroopilly, type=Court
            street = parts[1] if len(parts) > 1 else ""
            street_type = parts[2] if len(parts) > 2 else ""

    if not street:
        return {"available": False}

    # Find sold on same street
    street_sold = cosmos_retry(
        lambda: list(db[suburb].find({
            "listing_status": "sold",
            "sale_price": {"$exists": True},
            "$or": [
                {"STREET_NAME": street.upper()},
                {"address": {"$regex": f"\\b{re.escape(street)}\\b", "$options": "i"}},
            ],
        }, {"sale_price": 1, "sold_price": 1, "sold_date": 1, "address": 1, "bedrooms": 1}).limit(30)),
        f"street_{suburb}",
    )

    if not street_sold:
        return {"available": False, "street": f"{street} {street_type}"}

    street_prices = []
    for s in street_sold:
        p = parse_sale_price(s.get("sale_price")) or parse_sale_price(s.get("sold_price"))
        if p:
            street_prices.append(p)
    if not street_prices:
        return {"available": False, "street": f"{street} {street_type}"}

    # Suburb median sold price (all types)
    suburb_sold = cosmos_retry(
        lambda: list(db[suburb].find(
            {"listing_status": "sold", "sale_price": {"$exists": True}},
            {"sale_price": 1, "sold_price": 1},
        ).limit(500)),
        f"suburb_median_{suburb}",
    )
    suburb_prices = []
    for s in suburb_sold:
        p = parse_sale_price(s.get("sale_price")) or parse_sale_price(s.get("sold_price"))
        if p:
            suburb_prices.append(p)

    street_median = statistics.median(street_prices)
    suburb_median = statistics.median(suburb_prices) if suburb_prices else None

    premium_pct = None
    if suburb_median and suburb_median > 0:
        premium_pct = round(((street_median - suburb_median) / suburb_median) * 100, 1)

    return {
        "available": True,
        "street": f"{street} {street_type}".strip(),
        "n_sold": len(street_prices),
        "street_median": round(street_median),
        "suburb_median": round(suburb_median) if suburb_median else None,
        "premium_pct": premium_pct,
        "recent_sales": [
            {
                "address": s.get("address", ""),
                "sold_price": parse_sale_price(s.get("sale_price")) or parse_sale_price(s.get("sold_price")),
                "sold_date": str(s.get("sold_date", ""))[:10],
            }
            for s in sorted(street_sold, key=lambda x: x.get("sold_date", ""), reverse=True)[:5]
        ],
    }


def classify_archetype(prop: Dict) -> str:
    """Rule-based property archetype classification."""
    beds = prop.get("bedrooms", 0) or 0
    floor_area = get_floor_area(prop) or 0
    lot_size = prop.get("lot_size_sqm") or prop.get("land_area", 0) or 0
    features = prop.get("features") or []
    features_lower = [f.lower() for f in features]

    has_pool = any("pool" in f for f in features_lower)
    is_waterfront = any(w in " ".join(features_lower) for w in ("water", "lake", "canal", "river"))
    prop_type = (prop.get("classified_property_type") or prop.get("property_type", "")).lower()
    storeys = prop.get("floor_plan_analysis", {}).get("levels", 1) or 1

    if is_waterfront and has_pool:
        return "premium_waterfront_entertainer"
    if is_waterfront:
        return "premium_waterfront_entertainer"
    if has_pool and beds >= 4 and floor_area >= 200:
        return "family_entertainer_with_pool"
    if "duplex" in prop_type or "villa" in prop_type or "townhouse" in prop_type:
        return "duplex_villa"
    if beds <= 3 and floor_area < 150 and lot_size < 500:
        return "compact_starter_downsizer"
    if lot_size > 800 and floor_area < 150:
        return "original_large_block"
    if storeys >= 2 and beds >= 4:
        return "two_storey_family"
    if beds >= 5 or floor_area >= 280:
        return "large_family_home"

    # Check renovation level
    condition = prop.get("property_valuation_data", {}).get("condition_summary", {})
    reno_score = condition.get("overall_score", 5)
    if reno_score >= 8:
        return "renovated_family_home"

    return "standard_family_home"


def compute_dom_percentile(prop: Dict, db, suburb: str) -> Dict:
    """Where this property's DOM sits vs suburb distribution."""
    dom = prop.get("days_on_domain") or prop.get("days_on_market")
    if not dom:
        return {"available": False}

    # Get DOM for all active listings
    active = cosmos_retry(
        lambda: list(db[suburb].find(
            {"listing_status": "for_sale", "days_on_domain": {"$exists": True, "$gt": 0}},
            {"days_on_domain": 1},
        )),
        f"dom_{suburb}",
    )

    all_dom = sorted([a["days_on_domain"] for a in active if a.get("days_on_domain")])
    if not all_dom:
        return {"available": True, "dom": dom, "percentile": None}

    # Percentile rank
    below = sum(1 for d in all_dom if d < dom)
    percentile = round((below / len(all_dom)) * 100)

    return {
        "available": True,
        "dom": dom,
        "percentile": percentile,
        "suburb_median_dom": round(statistics.median(all_dom)),
        "n_active": len(all_dom),
    }


def get_comparable_sales(prop: Dict, db, suburb: str) -> List[Dict]:
    """Get recent comparable sales for the property (from valuation data or DB)."""
    # First try valuation_data.recent_sales (curated by valuation model)
    val_sales = prop.get("valuation_data", {}).get("recent_sales", [])
    if val_sales:
        # Sort by distance (closest = most comparable)
        val_sales_sorted = sorted(val_sales, key=lambda x: x.get("distance_km", 999))
        return [
            {
                "address": c.get("address", ""),
                "sold_price": c.get("original_sale_price") or c.get("price"),
                "sold_date": str(c.get("sale_date", ""))[:10],
                "distance_km": c.get("distance_km"),
                "utility_index": c.get("utility_index"),
            }
            for c in val_sales_sorted[:8]
        ]

    # Fall back to DB sold records with matching beds
    beds = prop.get("bedrooms")
    query = {
        "listing_status": "sold",
        "sale_price": {"$exists": True},
    }
    if beds:
        query["bedrooms"] = beds

    sales = cosmos_retry(
        lambda: list(db[suburb].find(query, {
            "address": 1, "sale_price": 1, "sold_date": 1, "bedrooms": 1,
            "total_floor_area": 1, "lot_size_sqm": 1,
        }).limit(50)),
        f"comps_{suburb}",
    )
    sales.sort(key=lambda x: x.get("sold_date", ""), reverse=True)

    return [
        {
            "address": s.get("address", ""),
            "sold_price": parse_sale_price(s.get("sale_price")),
            "sold_date": str(s.get("sold_date", ""))[:10],
            "bedrooms": s.get("bedrooms"),
            "floor_area": s.get("total_floor_area"),
            "lot_size": s.get("lot_size_sqm"),
        }
        for s in sales[:8]
    ]


# ---------------------------------------------------------------------------
# Prompt construction
# ---------------------------------------------------------------------------

def load_system_prompt() -> str:
    """Load the positioning agent system prompt from config."""
    prompt_path = REPO_ROOT / "config" / "positioning_agent_prompt.md"
    if not prompt_path.exists():
        print(f"[ERROR] Prompt file not found: {prompt_path}")
        sys.exit(1)
    return prompt_path.read_text()


def build_user_prompt(
    prop: Dict,
    precomputed: Dict,
    comparables: List[Dict],
    suburb_display: str,
) -> str:
    """Assemble the user prompt with property data + pre-computed metrics."""
    lines = []

    # Property details
    lines.append("## PROPERTY DATA")
    lines.append(f"Address: {prop.get('address', 'Unknown')}")
    lines.append(f"Suburb: {suburb_display}")
    lines.append(f"Price: {prop.get('price_display') or prop.get('price') or 'Not disclosed'}")

    price_num = parse_price_numeric(prop)
    if price_num:
        lines.append(f"Price (numeric): ${price_num:,.0f}")

    prop_type = prop.get("classified_property_type") or prop.get("property_type", "Unknown")
    lines.append(f"Property type: {prop_type}")
    lines.append(f"Bedrooms: {prop.get('bedrooms', '?')} | Bathrooms: {prop.get('bathrooms', '?')} | Car: {prop.get('carspaces') or prop.get('car_spaces', '?')}")

    floor_area = get_floor_area(prop)
    if floor_area:
        lines.append(f"Internal floor area: {floor_area} sqm")
    lot_size = prop.get("lot_size_sqm") or prop.get("land_area")
    if lot_size:
        lines.append(f"Lot size: {lot_size} sqm")

    dom = prop.get("days_on_domain") or prop.get("days_on_market")
    if dom:
        lines.append(f"Days on market: {dom}")

    agent = prop.get("agent_name") or prop.get("listing_agent", {}).get("name")
    agency = prop.get("agency_name") or prop.get("agency")
    if agent:
        lines.append(f"Agent: {agent}" + (f", {agency}" if agency else ""))

    features = prop.get("features") or []
    if features:
        lines.append(f"Features: {', '.join(features)}")

    # Valuation
    vd = prop.get("valuation_data", {}).get("confidence", {})
    reconciled = vd.get("reconciled_valuation")
    val_range = vd.get("range", {})
    if reconciled:
        lines.append(f"\nFields Valuation: ${reconciled:,.0f} (range: ${val_range.get('low', 0):,.0f} - ${val_range.get('high', 0):,.0f})")
        lines.append(f"Valuation confidence: {vd.get('confidence', 'unknown')}")

    # Transaction history
    history = prop.get("transactions") or []
    if history:
        lines.append("\nTransaction history (EXACT prices):")
        for h in history[:8]:
            price_h = h.get("price") or h.get("sold_price")
            if price_h:
                lines.append(f"  - {h.get('date', '?')}: ${price_h:,}")

    # AI editorial summary (if exists)
    ai = prop.get("ai_analysis", {})
    if ai.get("quick_take"):
        lines.append(f"\nEditorial summary: {ai['quick_take']}")

    # Condition summary
    condition = prop.get("property_valuation_data", {}).get("condition_summary", {})
    if condition.get("overall_score"):
        lines.append(f"\nCondition score: {condition['overall_score']}/10")
        if condition.get("summary"):
            lines.append(f"Condition notes: {condition['summary']}")

    # Satellite/location
    sat = prop.get("satellite_analysis", {})
    if sat.get("narrative", {}).get("surrounding_land_use"):
        lines.append(f"\nLocation context: {sat['narrative']['surrounding_land_use']}")

    # Zoning
    zoning = prop.get("zoning_data", {})
    if zoning.get("zone"):
        lines.append(f"Zoning: {zoning['zone']}")
    if zoning.get("flood_overlay"):
        lines.append(f"Flood overlay: {zoning['flood_overlay']}")

    # -------------------------------------------------------------------
    # Pre-computed metrics (Python-calculated, model uses as inputs)
    # -------------------------------------------------------------------
    lines.append("\n## PRE-COMPUTED METRICS (verified — use these numbers directly)")

    # $/sqm
    sqm = precomputed["price_per_sqm"]
    lines.append(f"\n### $/sqm Analysis")
    if sqm["data_available"] and sqm["property_rate"]:
        lines.append(f"Property $/sqm: ${sqm['property_rate']:,.0f}")
        if sqm["suburb_median_rate"]:
            lines.append(f"Suburb median $/sqm (sold): ${sqm['suburb_median_rate']:,.0f} (n={sqm.get('n_sold_with_floor_area', '?')})")
            lines.append(f"Position: {sqm['position']} median by {sqm['position_pct']}%")
    else:
        lines.append("Insufficient data for $/sqm calculation")

    # Scarcity
    sc = precomputed["scarcity"]
    lines.append(f"\n### Scarcity Counts")
    for combo in sc.get("all_combos", []):
        lines.append(f"  {combo['combo']}: {combo['count']} currently for sale in {suburb_display}")

    # Brackets
    br = precomputed["brackets"]
    lines.append(f"\n### Portal Bracket Analysis")
    if br["property_bracket"]:
        lines.append(f"This property's bracket: {br['property_bracket']} ({br['competing_in_bracket']} competing)")
    lines.append(f"Total active listings in {suburb_display}: {br['total_active']}")
    for label, count in sorted(br["all_brackets"].items(), key=lambda x: x[1], reverse=True):
        lines.append(f"  {label}: {count}")

    # Street stats
    st = precomputed["street_stats"]
    lines.append(f"\n### Street-Level Data")
    if st.get("available"):
        lines.append(f"Street: {st['street']}")
        lines.append(f"Sales on this street: {st['n_sold']}")
        lines.append(f"Street median: ${st['street_median']:,}")
        if st.get("suburb_median"):
            lines.append(f"Suburb median: ${st['suburb_median']:,}")
            if st.get("premium_pct") is not None:
                sign = "+" if st["premium_pct"] > 0 else ""
                lines.append(f"Street premium/discount: {sign}{st['premium_pct']}%")
    else:
        lines.append("No sold data on this street")

    # Archetype
    lines.append(f"\n### Archetype: {precomputed['archetype']}")

    # DOM
    dp = precomputed["dom"]
    if dp.get("available"):
        lines.append(f"\n### Days on Market Context")
        lines.append(f"This property: {dp['dom']} days")
        lines.append(f"Suburb median DOM (active): {dp.get('suburb_median_dom', '?')} days")
        if dp.get("percentile") is not None:
            lines.append(f"Percentile: {dp['percentile']}th (higher = longer than peers)")

    # Comparable sales
    if comparables:
        lines.append(f"\n### Comparable Sales ({len(comparables)} properties)")
        for c in comparables:
            parts = [c.get("address", "?")]
            if c.get("sold_price"):
                parts.append(f"${c['sold_price']:,}")
            if c.get("sold_date"):
                parts.append(c["sold_date"])
            if c.get("bedrooms"):
                parts.append(f"{c['bedrooms']}bed")
            if c.get("floor_area"):
                parts.append(f"{c['floor_area']}sqm")
            lines.append(f"  - {' | '.join(parts)}")

    lines.append("\n## INSTRUCTIONS")
    lines.append("Return ONLY valid JSON matching the schema in your system prompt.")
    lines.append("All public section statements must be DATA STATEMENTS, not advice.")
    lines.append("Use the pre-computed metrics above as authoritative — do not recalculate.")

    return "\n".join(lines)


# ---------------------------------------------------------------------------
# API call + post-processing
# ---------------------------------------------------------------------------

def call_positioning_agent(
    system_prompt: str,
    user_prompt: str,
    api_key: str,
) -> Dict:
    """Make the Claude API call and parse JSON response."""
    client = anthropic.Anthropic(api_key=api_key)

    response = client.messages.create(
        model=MODEL,
        max_tokens=MAX_TOKENS,
        system=system_prompt,
        messages=[{"role": "user", "content": user_prompt}],
    )

    result_text = response.content[0].text.strip()

    # Strip markdown fences if present
    if result_text.startswith("```"):
        result_text = result_text.split("\n", 1)[1]
        if result_text.endswith("```"):
            result_text = result_text.rsplit("```", 1)[0]
        result_text = result_text.strip()

    try:
        result = json.loads(result_text)
    except json.JSONDecodeError as e:
        print(f"  [ERROR] Failed to parse JSON: {e}")
        print(f"  Raw output (first 500 chars): {result_text[:500]}")
        raise

    # Token usage
    usage = response.usage
    input_tokens = usage.input_tokens
    output_tokens = usage.output_tokens
    # Approximate cost: Opus input=$15/MTok, output=$75/MTok
    cost = (input_tokens * 15 / 1_000_000) + (output_tokens * 75 / 1_000_000)

    print(f"  Tokens: {input_tokens:,} in / {output_tokens:,} out | ~${cost:.2f}")

    return result


def validate_output(result: Dict, precomputed: Dict) -> Tuple[bool, List[str]]:
    """Validate the API output against expected schema and data."""
    issues = []

    # Check required top-level keys
    for key in ("public", "gated", "version", "confidence"):
        if key not in result:
            issues.append(f"Missing top-level key: {key}")

    public = result.get("public", {})
    gated = result.get("gated", {})

    # Check public sections
    for key in ("scarcity", "price_per_sqm", "buyer_profile", "market_context",
                "bracket_intelligence", "hook_card"):
        if key not in public:
            issues.append(f"Missing public.{key}")

    # Check gated sections
    for key in ("pricing_strategy", "pre_sale_recommendations", "agency_recommendation",
                "campaign_structure"):
        if key not in gated:
            issues.append(f"Missing gated.{key}")

    # Validate scarcity count matches pre-computed
    sc = precomputed["scarcity"]
    api_count = public.get("scarcity", {}).get("count")
    if api_count is not None and sc["best_count"] is not None:
        if api_count != sc["best_count"]:
            issues.append(f"Scarcity count mismatch: API={api_count}, computed={sc['best_count']}")

    # Check no advice language in public sections
    advice_words = ["you should", "we recommend", "consider buying", "consider selling", "now is a good time"]
    public_text = json.dumps(public).lower()
    for phrase in advice_words:
        if phrase in public_text:
            issues.append(f"Public section contains advice language: '{phrase}'")

    is_valid = len(issues) == 0
    return is_valid, issues


def post_process(result: Dict, precomputed: Dict, prop: Dict) -> Dict:
    """Post-process the API output — fix any data issues, add metadata."""
    # Override scarcity count with pre-computed value
    if "public" in result and "scarcity" in result["public"]:
        result["public"]["scarcity"]["count"] = precomputed["scarcity"]["best_count"]

    # Override $/sqm with pre-computed values
    sqm = precomputed["price_per_sqm"]
    if "public" in result and "price_per_sqm" in result["public"]:
        if sqm["data_available"] and sqm["property_rate"]:
            result["public"]["price_per_sqm"]["property_rate"] = sqm["property_rate"]
            result["public"]["price_per_sqm"]["suburb_median_rate"] = sqm["suburb_median_rate"]
            result["public"]["price_per_sqm"]["position"] = sqm["position"]
            result["public"]["price_per_sqm"]["position_pct"] = sqm["position_pct"]

    # Add metadata
    result["generated_at"] = datetime.now(timezone.utc).isoformat()
    result["version"] = result.get("version", "1.0")
    result["archetype"] = precomputed["archetype"]
    # Sanitize bracket keys for MongoDB ($ prefix not allowed)
    brackets_clean = dict(precomputed["brackets"])
    if "all_brackets" in brackets_clean:
        brackets_clean["all_brackets"] = {
            k.replace("$", ""): v for k, v in brackets_clean["all_brackets"].items()
        }
    result["precomputed"] = {
        "price_per_sqm": sqm,
        "scarcity": precomputed["scarcity"],
        "brackets": brackets_clean,
        "street_stats": precomputed["street_stats"],
        "dom": precomputed["dom"],
    }

    return result


# ---------------------------------------------------------------------------
# Main processing
# ---------------------------------------------------------------------------

def process_property(
    db, suburb: str, prop: Dict, api_key: str,
    force: bool = False, dry_run: bool = False,
) -> Optional[Dict]:
    """Run the full positioning pipeline for one property."""
    address = prop.get("address", "Unknown")
    prop_id = prop["_id"]

    # Skip if already has positioning (unless force)
    if not force and prop.get("positioning_analysis") and prop["positioning_analysis"].get("version"):
        print(f"[SKIP] {address} — already has positioning_analysis (use --force)")
        return prop["positioning_analysis"]

    # Dependency gate: require ai_analysis
    if not prop.get("ai_analysis") or not prop["ai_analysis"].get("quick_take"):
        if not force:
            print(f"[SKIP] {address} — no ai_analysis (run editorial pipeline first, or use --force)")
            return None

    print(f"\n{'='*60}")
    print(f"POSITIONING: {address}")
    print(f"{'='*60}")

    suburb_display = suburb.replace("_", " ").title()

    # Pre-computation
    print("[1/4] Pre-computing metrics...")
    precomputed = {
        "price_per_sqm": compute_price_per_sqm(prop, db, suburb),
        "scarcity": compute_scarcity(prop, db, suburb),
        "brackets": compute_bracket_analysis(prop, db, suburb),
        "street_stats": compute_street_stats(prop, db, suburb),
        "archetype": classify_archetype(prop),
        "dom": compute_dom_percentile(prop, db, suburb),
    }

    sqm = precomputed["price_per_sqm"]
    sc = precomputed["scarcity"]
    prop_rate = f"${sqm['property_rate']:,.0f}" if sqm.get("property_rate") else "N/A"
    sub_rate = f"${sqm['suburb_median_rate']:,.0f}" if sqm.get("suburb_median_rate") else "N/A"
    print(f"  $/sqm: {prop_rate} (suburb median: {sub_rate})")
    print(f"  Scarcity: {sc['best_count']} x '{sc['best_combo']}' in {suburb_display}")
    print(f"  Archetype: {precomputed['archetype']}")

    # Comparable sales
    print("[2/4] Fetching comparable sales...")
    comparables = get_comparable_sales(prop, db, suburb)
    print(f"  Found {len(comparables)} comparables")

    # Build prompts
    system_prompt = load_system_prompt()
    user_prompt = build_user_prompt(prop, precomputed, comparables, suburb_display)

    if dry_run:
        print(f"\n--- SYSTEM PROMPT ({len(system_prompt)} chars) ---")
        print(system_prompt[:500] + "...")
        print(f"\n--- USER PROMPT ({len(user_prompt)} chars) ---")
        print(user_prompt)
        return None

    # API call
    print("[3/4] Calling Claude Opus...")
    try:
        result = call_positioning_agent(system_prompt, user_prompt, api_key)
    except Exception as e:
        print(f"  [ERROR] API call failed: {e}")
        # Store error state
        error_doc = {
            "status": "failed",
            "error": str(e),
            "generated_at": datetime.now(timezone.utc).isoformat(),
        }
        cosmos_retry(lambda: db[suburb].update_one(
            {"_id": prop_id},
            {"$set": {"positioning_analysis": error_doc}},
        ), "store_error")
        return None

    # Validate
    is_valid, issues = validate_output(result, precomputed)
    if issues:
        print(f"  [WARN] Validation issues ({len(issues)}):")
        for issue in issues:
            print(f"    - {issue}")

    # Post-process
    result = post_process(result, precomputed, prop)
    result["status"] = "published" if is_valid else "needs_review"

    # Store
    print("[4/4] Storing positioning analysis...")
    cosmos_retry(lambda: db[suburb].update_one(
        {"_id": prop_id},
        {"$set": {"positioning_analysis": result}},
    ), "store_positioning")
    print(f"  Stored ({result['status']})")

    # Print summary
    public = result.get("public", {})
    hook = public.get("hook_card", {})
    print(f"\n  Hook headline: {hook.get('headline', '?')}")
    print(f"  Hook teaser: {hook.get('teaser', '?')}")

    gated = result.get("gated", {})
    pricing = gated.get("pricing_strategy", {})
    if pricing.get("recommended_range_low"):
        print(f"  Pricing: ${pricing['recommended_range_low']:,.0f} - ${pricing.get('recommended_range_high', 0):,.0f}")

    return result


# ---------------------------------------------------------------------------
# Find property helpers
# ---------------------------------------------------------------------------

def find_suburb_for_slug(db, slug: str) -> Optional[Tuple[str, Dict]]:
    """Search target suburbs for a property by slug."""
    for suburb in TARGET_SUBURBS:
        doc = cosmos_retry(
            lambda s=suburb: db[s].find_one({"url_slug": slug, "listing_status": "for_sale"}),
            f"find_slug_{suburb}",
        )
        if doc:
            return suburb, doc
    return None


def find_suburb_for_address(db, address: str) -> Optional[Tuple[str, Dict]]:
    """Search target suburbs for a property by address substring."""
    for suburb in TARGET_SUBURBS:
        doc = cosmos_retry(
            lambda s=suburb: db[s].find_one({
                "address": {"$regex": address, "$options": "i"},
                "listing_status": "for_sale",
            }),
            f"find_addr_{suburb}",
        )
        if doc:
            return suburb, doc
    return None


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def main():
    parser = argparse.ArgumentParser(
        description="Generate property positioning analysis using Claude Opus"
    )
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument("--slug", help="Property URL slug")
    group.add_argument("--address", help="Address substring to match")
    group.add_argument("--backfill", action="store_true",
                       help="Process all properties with ai_analysis but no positioning")
    parser.add_argument("--force", action="store_true",
                        help="Regenerate even if positioning exists")
    parser.add_argument("--suburb", help="Restrict to one suburb")
    parser.add_argument("--dry-run", action="store_true",
                        help="Show prompt but don't call Claude")
    parser.add_argument("--mock", action="store_true",
                        help="Use mock API response for testing (no API call)")
    args = parser.parse_args()

    # API key — try multiple sources
    api_key = os.environ.get("ANTHROPIC_SONNET_API_KEY") or os.environ.get("ANTHROPIC_API_KEY")
    if not api_key and not args.dry_run:
        print("[ERROR] No ANTHROPIC_API_KEY in environment")
        sys.exit(1)

    # DB connection
    conn_str = os.environ.get("COSMOS_CONNECTION_STRING")
    if not conn_str:
        print("[ERROR] No COSMOS_CONNECTION_STRING in environment")
        sys.exit(1)

    client = MongoClient(conn_str)
    db = client["Gold_Coast"]

    if args.slug:
        result = find_suburb_for_slug(db, args.slug)
        if not result:
            print(f"[ERROR] No active listing found with slug '{args.slug}'")
            sys.exit(1)
        suburb, prop = result
        print(f"Found in {suburb}: {prop.get('address')}")
        process_property(db, suburb, prop, api_key, force=args.force, dry_run=args.dry_run)

    elif args.address:
        result = find_suburb_for_address(db, args.address)
        if not result:
            print(f"[ERROR] No active listing found matching '{args.address}'")
            sys.exit(1)
        suburb, prop = result
        print(f"Found in {suburb}: {prop.get('address')}")
        process_property(db, suburb, prop, api_key, force=args.force, dry_run=args.dry_run)

    elif args.backfill:
        suburbs = [args.suburb] if args.suburb else TARGET_SUBURBS
        total = 0
        skipped = 0
        for suburb in suburbs:
            query = {
                "listing_status": "for_sale",
                "ai_analysis": {"$exists": True},
            }
            if not args.force:
                query["positioning_analysis"] = {"$exists": False}

            props = cosmos_retry(
                lambda s=suburb: list(db[s].find(query)),
                f"backfill_{suburb}",
            )
            print(f"\n{suburb}: {len(props)} properties to process")

            for prop in props:
                try:
                    result = process_property(
                        db, suburb, prop, api_key,
                        force=args.force, dry_run=args.dry_run,
                    )
                    if result:
                        total += 1
                    else:
                        skipped += 1
                    sleep_with_jitter(1.0)  # Rate limiting
                except Exception as e:
                    print(f"[ERROR] Failed on {prop.get('address', '?')}: {e}")

        print(f"\nDone. Processed {total}, skipped {skipped}.")

    client.close()


if __name__ == "__main__":
    main()
