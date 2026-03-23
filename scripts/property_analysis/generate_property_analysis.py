#!/usr/bin/env python3
"""
Multi-Agent Property Analysis Generator

Generates an independent editorial analysis article for a property listing
using a 4-phase multi-agent pipeline:
  Phase 1: 5 specialist agents analyse their domains in parallel
  Phase 2: Editorial agent writes a draft article from the briefs
  Phase 3: 5 specialists review the draft in parallel
  Phase 4: Editorial agent produces the final article

Usage:
    python3 scripts/property_analysis/generate_property_analysis.py \
        --slug 21-indooroopilly-court-robina

    python3 scripts/property_analysis/generate_property_analysis.py \
        --slug 21-indooroopilly-court-robina --dry-run

    python3 scripts/property_analysis/generate_property_analysis.py \
        --slug 21-indooroopilly-court-robina --phase 1  # briefs only
"""

import os
import sys
import json
import time
import argparse
import hashlib
import concurrent.futures
from datetime import datetime, timezone, timedelta
from pathlib import Path

import anthropic
from pymongo import MongoClient
import yaml

# ── Config ──────────────────────────────────────────────────────────────────
SCRIPT_DIR = Path(__file__).parent
PROMPTS_DIR = SCRIPT_DIR / "prompts"
PROJECT_ROOT = SCRIPT_DIR.parent.parent
AEST = timezone(timedelta(hours=10))

MODEL = "claude-sonnet-4-6"
MAX_TOKENS_BRIEF = 1024
MAX_TOKENS_REVIEW = 512
MAX_TOKENS_ARTICLE = 4096
MAX_RETRIES = 3

SPECIALIST_AGENTS = ["space", "condition", "valuation", "market", "location"]

# Suburb display name mapping
SUBURB_DISPLAY = {
    "robina": "Robina",
    "burleigh_waters": "Burleigh Waters",
    "varsity_lakes": "Varsity Lakes",
    "burleigh_heads": "Burleigh Heads",
    "mudgeeraba": "Mudgeeraba",
    "reedy_creek": "Reedy Creek",
    "merrimac": "Merrimac",
    "worongary": "Worongary",
    "carrara": "Carrara",
}


# ── Database ────────────────────────────────────────────────────────────────
def get_clients():
    """Get MongoDB client and Anthropic client."""
    config_path = PROJECT_ROOT / "config" / "settings.yaml"
    with open(config_path) as f:
        cfg = yaml.safe_load(f)
    mongo = MongoClient(cfg["mongodb"]["uri"])

    api_key = os.environ.get("ANTHROPIC_API_KEY")
    if not api_key:
        raise RuntimeError("ANTHROPIC_API_KEY not set")
    anth = anthropic.Anthropic(api_key=api_key)

    return mongo, anth


# ── Data Collection ─────────────────────────────────────────────────────────
def collect_property_data(mongo, slug: str) -> dict:
    """Collect all data for a property from MongoDB."""
    db = mongo["Gold_Coast"]

    # Find the property across suburb collections
    prop = None
    suburb_slug = None
    for suburb in SUBURB_DISPLAY:
        prop = db[suburb].find_one({"url_slug": slug})
        if prop:
            suburb_slug = suburb
            break

    if not prop:
        raise ValueError(f"Property not found: {slug}")

    prop["_id"] = str(prop["_id"])

    # Check required data
    if not prop.get("valuation_data"):
        raise ValueError(f"Property {slug} has no valuation data — skipping")
    if not prop.get("property_valuation_data") and not prop.get("image_analysis"):
        # Check if there's condition data in valuation_data
        vd = prop.get("valuation_data", {})
        sp = vd.get("subject_property", {}).get("features", {})
        if not sp.get("npui_breakdown"):
            raise ValueError(f"Property {slug} has no condition/vision data — skipping")

    # Collect suburb context
    suburb_display = SUBURB_DISPLAY.get(suburb_slug, suburb_slug.replace("_", " ").title())

    # Get suburb medians
    medians = _get_suburb_medians(db, suburb_slug)

    # Get market data
    market_data = _get_market_data(db, suburb_slug, suburb_display)

    # Get suburb listing stats for comparison
    listing_stats = _get_listing_stats(db, suburb_slug)

    return {
        "property": prop,
        "suburb_slug": suburb_slug,
        "suburb_display": suburb_display,
        "medians": medians,
        "market": market_data,
        "listing_stats": listing_stats,
    }


def _get_suburb_medians(db, suburb_slug: str) -> list:
    """Get recent quarterly medians for the suburb."""
    med_doc = db["suburb_median_prices"].find_one(
        {"suburb": suburb_slug, "property_type": "House"}
    )
    if not med_doc:
        return []
    data = med_doc.get("data", [])
    # Last 8 quarters
    recent = [d for d in data if d.get("date", "") >= "2024-Q1"]
    return recent


def _get_market_data(db, suburb_slug: str, suburb_display: str) -> dict:
    """Collect market metrics from precomputed collections."""
    result = {}

    # DOM data
    dom_doc = db["precomputed_market_charts"].find_one(
        {"suburb": suburb_display, "chart_type": "dom"}
    )
    if dom_doc:
        result["dom"] = {
            "latest_median": dom_doc.get("latest_quarter_median"),
            "yoy_change_days": dom_doc.get("yoy_change_days"),
            "timeline": dom_doc.get("timeline", [])[-8:],  # last 8 quarters
        }

    time.sleep(0.3)

    # Indexed prices
    idx_doc = db["precomputed_indexed_prices"].find_one({"suburb": suburb_display})
    if idx_doc:
        result["indexed"] = {
            "total_growth_pct": idx_doc.get("total_growth_pct"),
            "rolling_12m_median": idx_doc.get("rolling_12m_median_price"),
            "annual_growth_rate": idx_doc.get("annual_growth_rate_latest"),
        }

    time.sleep(0.3)

    # Active listings
    listings_doc = db["precomputed_active_listings"].find_one(
        {"suburb": suburb_display}
    )
    if listings_doc:
        snapshots = listings_doc.get("snapshots", [])
        if snapshots:
            latest = snapshots[-1] if snapshots else {}
            result["active_listings"] = {
                "current": latest.get("count"),
                "mom_change": latest.get("mom_delta"),
            }

    time.sleep(0.3)

    # Market pulse
    sm = db.client["system_monitor"]
    pulse = sm["market_pulse"].find_one(
        {"suburb": {"$regex": suburb_slug, "$options": "i"}},
    )
    if pulse:
        pulse.pop("_id", None)
        result["pulse"] = pulse

    return result


def _get_listing_stats(db, suburb_slug: str) -> dict:
    """Get stats about current listings in the suburb for comparison."""
    collection = db[suburb_slug]

    listings = list(collection.find(
        {"listing_status": "for_sale"},
        {
            "bedrooms": 1, "bathrooms": 1, "carspaces": 1,
            "lot_size_sqm": 1, "total_floor_area": 1,
            "price": 1, "days_on_domain": 1,
        }
    ))

    if not listings:
        return {"count": 0}

    beds = [l.get("bedrooms", 0) for l in listings if l.get("bedrooms")]
    baths = [l.get("bathrooms", 0) for l in listings if l.get("bathrooms")]
    cars = [l.get("carspaces", 0) for l in listings if l.get("carspaces")]
    lots = [l.get("lot_size_sqm", 0) for l in listings if l.get("lot_size_sqm")]

    import statistics
    return {
        "count": len(listings),
        "median_beds": statistics.median(beds) if beds else None,
        "median_baths": statistics.median(baths) if baths else None,
        "median_cars": statistics.median(cars) if cars else None,
        "median_lot": round(statistics.median(lots)) if lots else None,
    }


# ── Data Package Builders ──────────────────────────────────────────────────
def build_space_package(data: dict) -> str:
    """Build the data prompt for the space/layout agent."""
    prop = data["property"]
    stats = data["listing_stats"]
    insights = prop.get("property_insights", {})

    floor_area = prop.get("total_floor_area") or prop.get("house_plan", {}).get("floor_area_sqm")
    lot_size = prop.get("lot_size_sqm", 0)
    flr = round(floor_area / lot_size, 2) if floor_area and lot_size else None

    lines = [
        f"## PROPERTY: {prop['address']}",
        f"Type: {prop.get('property_type', 'House')} | Tenure: {prop.get('property_tenure_desc', 'Unknown')}",
        f"Bedrooms: {prop.get('bedrooms')} | Bathrooms: {prop.get('bathrooms')} | Parking: {prop.get('carspaces')}",
        f"Lot size: {lot_size} sqm | Floor area: {floor_area} sqm | Levels: {prop.get('house_plan', {}).get('number_of_levels', 'Unknown')}",
        f"Floor-to-land ratio: {flr}",
        f"Year built: ~{prop.get('valuation_data', {}).get('subject_property', {}).get('features', {}).get('basic', {}).get('approximate_build_year', 'Unknown')}",
        "",
        "## ROOM DIMENSIONS (from floor plan analysis)",
    ]

    parsed = prop.get("parsed_rooms", {})
    fpa = prop.get("floor_plan_analysis", {})
    rooms = fpa.get("rooms", [])
    if rooms:
        for r in rooms:
            dims = r.get("dimensions", {})
            area = dims.get("area", "?")
            lines.append(
                f"- {r.get('room_name', '?')}: {dims.get('length', '?')}m x {dims.get('width', '?')}m = {area} sqm"
                f"  Features: {', '.join(r.get('features', [])) or 'none'}"
            )
    elif parsed:
        for key, room in parsed.items():
            lines.append(
                f"- {room.get('room_name', key)}: {room.get('length', '?')}m x {room.get('width', '?')}m = {room.get('area', '?')} sqm"
            )

    lines.append("")
    lines.append(f"## SUBURB LISTING COMPARISON ({data['suburb_display']}, {stats.get('count', 0)} active listings)")
    lines.append(f"Suburb median bedrooms: {stats.get('median_beds')}")
    lines.append(f"Suburb median bathrooms: {stats.get('median_baths')}")
    lines.append(f"Suburb median parking: {stats.get('median_cars')}")
    lines.append(f"Suburb median lot size: {stats.get('median_lot')} sqm")

    # Add percentiles from property_insights
    for feat in ["bedrooms", "bathrooms", "parking", "lot_size"]:
        fi = insights.get(feat, {})
        sc = fi.get("suburbComparison", {})
        if sc:
            lines.append(f"{feat} percentile: {sc.get('percentile')}th — {sc.get('narrative', '')}")

    features = prop.get("features", [])
    if features:
        lines.append(f"\nFeatures: {', '.join(features)}")

    return "\n".join(lines)


def build_condition_package(data: dict) -> str:
    """Build the data prompt for the condition agent."""
    prop = data["property"]
    vd = prop.get("valuation_data", {})
    sp = vd.get("subject_property", {}).get("features", {})
    basic = sp.get("basic", {})
    npui = sp.get("npui_breakdown", {})

    # Try to get detailed condition from property_valuation_data first
    pvd = prop.get("property_valuation_data", {})

    lines = [
        f"## PROPERTY: {prop['address']}",
        f"Type: {prop.get('property_type', 'House')} | Built: ~{basic.get('approximate_build_year', 'Unknown')}",
        f"Construction: {basic.get('cladding_raw', 'Unknown')}",
        f"Renovation level: {basic.get('renovation_level', 'Unknown')}/5",
        f"Pool: {'Yes' if basic.get('pool_present') else 'No'}",
        f"AC: {'Ducted' if basic.get('ac_ducted') else 'Split system / none'}",
        "",
        "## CONDITION SCORES",
    ]

    # Extract condition data from various possible sources
    if pvd and isinstance(pvd, dict):
        # New format with detailed room analysis
        for area in ["kitchen", "bathrooms", "bedrooms", "living_areas", "exterior", "outdoor"]:
            area_data = pvd.get(area, {})
            if isinstance(area_data, dict):
                score = area_data.get("score", area_data.get("quality_score", "?"))
                desc = area_data.get("description", area_data.get("summary", ""))
                features_list = area_data.get("features", [])
                feat_str = ", ".join(features_list) if features_list else ""
                lines.append(f"- {area.replace('_', ' ').title()}: {score}/10 — {desc}")
                if feat_str:
                    lines.append(f"  Features: {feat_str}")
        overall = pvd.get("overall_condition", pvd.get("condition_summary", {}))
        if isinstance(overall, dict):
            lines.append(f"\nOverall condition: {overall.get('score', '?')}/10 — {overall.get('description', '')}")
    else:
        # Fall back to NPUI inputs for condition proxies
        inputs = npui.get("inputs", {})
        condition_keys = {
            "interior.overall_interior_condition_score": "Interior overall",
            "interior.kitchen_quality_score": "Kitchen quality",
            "interior.bathroom_quality_score": "Bathroom quality",
            "exterior.overall_exterior_condition_score": "Exterior overall",
            "renovation.modern_features_score": "Modern features",
            "layout.layout_efficiency_score": "Layout efficiency",
            "interior.natural_light_score": "Natural light",
            "outdoor.outdoor_entertainment_score": "Outdoor entertainment",
            "outdoor.landscaping_quality_score": "Landscaping",
        }
        for key, label in condition_keys.items():
            val = inputs.get(key)
            if val is not None:
                lines.append(f"- {label}: {val}/10")

    lines.append("")
    lines.append("## FEATURES PRESENT")
    features = prop.get("features", [])
    lines.append(", ".join(features) if features else "None listed")

    lines.append("")
    lines.append("## FEATURES COMMONLY EXPECTED AT THIS PRICE POINT")
    lines.append("(Note which of these the property LACKS)")
    lines.append("- Ensuite to master bedroom")
    lines.append("- Ducted air conditioning")
    lines.append("- Double garage")
    lines.append("- Pool (common above $1M in Gold Coast suburbs)")
    lines.append("- Modern kitchen with stone benchtops")
    lines.append("- Multiple bathrooms (2+)")

    return "\n".join(lines)


def build_valuation_package(data: dict) -> str:
    """Build the data prompt for the valuation agent."""
    prop = data["property"]
    vd = prop.get("valuation_data", {})
    conf = vd.get("confidence", {})
    medians = data["medians"]

    lines = [
        f"## PROPERTY: {prop['address']}",
        f"Listed price: {prop.get('price', 'Unknown')}",
        f"Days on market: {prop.get('days_on_domain', 'Unknown')}",
        f"First listed: {prop.get('first_listed_date', 'Unknown')}",
        "",
        "## OUR VALUATION ESTIMATE",
        f"Reconciled valuation: ${conf.get('reconciled_valuation', 0):,.0f}" if conf.get('reconciled_valuation') else "Reconciled valuation: Not available",
        f"Confidence: {conf.get('confidence', 'Unknown')}",
        f"Range: ${conf.get('range', {}).get('low', 0):,.0f} — ${conf.get('range', {}).get('high', 0):,.0f}" if conf.get('range') else "",
        f"Coefficient of variation: {conf.get('cv', '?')}",
        f"Verified comparables: {conf.get('n_verified', '?')} of {conf.get('n_total', '?')} analysed",
    ]

    # Top comparables
    comps = vd.get("comparables", [])
    if comps:
        lines.append("")
        lines.append(f"## TOP COMPARABLE SALES ({len(comps)} total)")
        for i, c in enumerate(comps[:5]):
            basic = c.get("features", {}).get("basic", {})
            adj = c.get("adjustment_result", {})
            lines.append(f"\nComp {i+1}: {c.get('address', '?')}")
            lines.append(f"  Sold: ${c.get('price', 0):,.0f}" if c.get('price') else "  Sold: ?")
            lines.append(f"  Beds/Bath/Car: {basic.get('bedrooms', '?')}/{basic.get('bathrooms', '?')}/{basic.get('car_spaces', '?')}")
            lines.append(f"  Land: {basic.get('land_size_sqm', '?')} sqm | Floor: {basic.get('floor_area_sqm', '?')} sqm")
            lines.append(f"  Distance: {c.get('distance_km', '?')} km")
            lines.append(f"  Adjusted price: ${adj.get('adjusted_price', 0):,.0f}" if adj.get('adjusted_price') else "")
            lines.append(f"  Weight in estimate: {c.get('weight', {}).get('normalized', '?')}")

    # Transaction history
    transactions = prop.get("transactions", [])
    timeline = prop.get("scraped_data", {}).get("property_timeline", [])
    if transactions or timeline:
        lines.append("")
        lines.append("## TRANSACTION HISTORY")
        for t in (timeline or transactions):
            date = t.get("date", "?")
            cat = t.get("category", t.get("source", ""))
            price = t.get("price", "?")
            dom = t.get("days_on_market", "")
            if isinstance(price, (int, float)) and price > 0:
                lines.append(f"- {date}: {cat} — ${price:,.0f}" + (f" ({dom} days on market)" if dom else ""))
            elif isinstance(price, (int, float)):
                lines.append(f"- {date}: {cat} — ${price}/week" if cat == "Rental" else f"- {date}: {cat}")

    # Rental estimate
    rental = prop.get("scraped_data", {}).get("rental_estimate", {})
    if rental:
        lines.append(f"\nRental estimate: ${rental.get('weekly_rent', '?')}/week | Yield: {rental.get('yield', '?')}%")

    # Suburb medians
    if medians:
        lines.append("")
        lines.append(f"## SUBURB MEDIAN PRICES ({data['suburb_display']} houses)")
        for m in medians[-6:]:
            lines.append(f"- {m['date']}: ${m['median']:,.0f} ({m['count']} sales)")

    return "\n".join(lines)


def build_market_package(data: dict) -> str:
    """Build the data prompt for the market context agent."""
    prop = data["property"]
    market = data["market"]
    medians = data["medians"]
    stats = data["listing_stats"]

    lines = [
        f"## SUBURB: {data['suburb_display']}",
        f"Property being analysed: {prop['address']}",
        f"Property price point: {prop.get('price', 'Auction/Contact Agent')}",
        "",
        "## QUARTERLY MEDIAN PRICES (houses)",
    ]

    for m in medians[-8:]:
        lines.append(f"- {m['date']}: ${m['median']:,.0f} ({m['count']} sales)")

    # Indexed data
    idx = market.get("indexed", {})
    if idx:
        lines.append("")
        lines.append("## PRICE GROWTH")
        if idx.get("rolling_12m_median"):
            lines.append(f"Rolling 12-month median: ${idx['rolling_12m_median']:,.0f}")
        if idx.get("annual_growth_rate") is not None:
            lines.append(f"Annual growth rate (latest): {idx['annual_growth_rate']}")
        if idx.get("total_growth_pct") is not None:
            lines.append(f"Total indexed growth: {idx['total_growth_pct']}")

    # DOM
    dom = market.get("dom", {})
    if dom:
        lines.append("")
        lines.append("## DAYS ON MARKET")
        if dom.get("latest_median"):
            lines.append(f"Current median DOM: {dom['latest_median']} days")
        if dom.get("yoy_change_days") is not None:
            lines.append(f"YoY change: {dom['yoy_change_days']} days")
        tl = dom.get("timeline", [])
        if tl:
            lines.append("Recent quarters:")
            for t in tl[-6:]:
                lines.append(f"  - {t.get('quarter', '?')}: {t.get('median', '?')} days ({t.get('count', '?')} sales)")

    # Active listings
    al = market.get("active_listings", {})
    if al:
        lines.append("")
        lines.append("## SUPPLY")
        lines.append(f"Active listings: {al.get('current', '?')}")
        if al.get("mom_change") is not None:
            lines.append(f"Month-on-month change: {al['mom_change']}")

    lines.append(f"\nTotal listings currently for sale: {stats.get('count', '?')}")

    # Market pulse
    pulse = market.get("pulse", {})
    if pulse:
        lines.append("")
        lines.append("## MARKET PULSE (macro signals)")
        for key in ["verdict", "wages", "spending", "lending", "cpi", "dwelling_supply", "asx"]:
            if key in pulse:
                val = pulse[key]
                if isinstance(val, dict):
                    lines.append(f"- {key}: {val.get('summary', val.get('direction', json.dumps(val)))}")
                else:
                    lines.append(f"- {key}: {val}")

    return "\n".join(lines)


def build_location_package(data: dict) -> str:
    """Build the data prompt for the location agent."""
    prop = data["property"]
    pois = prop.get("nearby_pois", {}).get("by_category", {})
    osm = prop.get("osm_location_features", {})
    basic = prop.get("valuation_data", {}).get("subject_property", {}).get("features", {}).get("basic", {})

    lines = [
        f"## PROPERTY: {prop['address']}",
        f"Suburb: {data['suburb_display']}",
        f"Coordinates: {prop.get('LATITUDE', '?')}, {prop.get('LONGITUDE', '?')}",
        f"Beach distance: {basic.get('beach_distance_km', '?')} km",
        f"Street premium: {basic.get('street_premium_pct', 0):.1%}" if basic.get('street_premium_pct') else "",
        f"Micro-location premium: {basic.get('micro_location_premium_pct', 0):.1%}" if basic.get('micro_location_premium_pct') else "",
        "",
    ]

    # Road/street classification
    road = osm.get("road_classification", {})
    if road:
        lines.append("## STREET & ROAD")
        lines.append(f"Nearest road type: {road.get('nearest_road_type', '?')}")
        lines.append(f"Is corner lot: {road.get('is_corner_lot', '?')}")
        lines.append(f"Is cul-de-sac/court: {road.get('is_cul_de_sac', '?')}")
        lines.append(f"Traffic exposure score: {road.get('traffic_exposure_score', '?')}/10")
        lines.append(f"Faces major road: {road.get('faces_major_road', '?')}")
        lines.append("")

    # Water features
    water = osm.get("water_features", {})
    if water:
        lines.append("## WATER FEATURES")
        lines.append(f"Distance to water: {water.get('distance_to_water_m', '?')} m")
        lines.append(f"Water type: {water.get('nearest_water_type', '?')}")
        lines.append(f"Canal frontage: {water.get('canal_frontage', False)}")
        lines.append(f"Waterfront premium eligible: {water.get('waterfront_premium_eligible', False)}")
        lines.append("")

    # POIs by category
    lines.append("## NEARBY AMENITIES")
    for category in ["primary_school", "secondary_school", "supermarket", "childcare",
                     "park", "cafe", "gym", "train_station", "shopping_mall"]:
        items = pois.get(category, [])
        if items:
            lines.append(f"\n### {category.replace('_', ' ').title()}")
            for item in items[:3]:
                dist = item.get("distance_km", item.get("distance_m", "?"))
                if isinstance(dist, (int, float)) and dist > 100:
                    dist_str = f"{dist}m" if dist < 1000 else f"{dist/1000:.1f}km" if isinstance(dist, (int, float)) else f"{dist}"
                else:
                    dist_str = f"{dist}km" if isinstance(dist, (int, float)) else str(dist)
                rating = item.get("rating", "")
                rating_str = f" (rating: {rating})" if rating else ""
                lines.append(f"  - {item.get('name', '?')} — {dist_str}{rating_str}")

    # Amenity counts
    pois_1km = sum(
        len([p for p in items if p.get("distance_km", 99) <= 1.0])
        for items in pois.values()
    )
    pois_2km = sum(
        len([p for p in items if p.get("distance_km", 99) <= 2.0])
        for items in pois.values()
    )
    lines.append(f"\nAmenities within 1km: {pois_1km}")
    lines.append(f"Amenities within 2km: {pois_2km}")

    return "\n".join(lines)


# ── Agent Execution ─────────────────────────────────────────────────────────
def load_prompt(name: str) -> str:
    """Load a prompt file."""
    path = PROMPTS_DIR / name
    with open(path) as f:
        return f.read()


def call_sonnet(client, system: str, user: str, max_tokens: int) -> str:
    """Call Claude Sonnet with retry logic."""
    for attempt in range(MAX_RETRIES):
        try:
            response = client.messages.create(
                model=MODEL,
                max_tokens=max_tokens,
                system=system,
                messages=[{"role": "user", "content": user}],
            )
            return response.content[0].text.strip()
        except Exception as e:
            if attempt < MAX_RETRIES - 1:
                wait = (attempt + 1) * 5
                print(f"    ⚠ API error (attempt {attempt+1}): {e} — retrying in {wait}s")
                time.sleep(wait)
            else:
                raise


def run_specialist(client, agent_name: str, data_package: str) -> str:
    """Run a single specialist agent."""
    system_prompt = load_prompt("editorial_rules.md")
    agent_prompt = load_prompt(f"agent_{agent_name}.md")
    full_system = f"{agent_prompt}\n\n---\n\n{system_prompt}"

    brief = call_sonnet(client, full_system, data_package, MAX_TOKENS_BRIEF)
    return brief


def run_review(client, agent_name: str, original_brief: str, draft: str) -> str:
    """Run a specialist review of the editorial draft."""
    system_prompt = load_prompt("editorial_rules.md")
    review_prompt = load_prompt("agent_review.md")
    full_system = f"{review_prompt}\n\n---\n\n{system_prompt}"

    user_content = (
        f"## YOUR ORIGINAL BRIEF ({agent_name.upper()} ANALYST)\n\n"
        f"{original_brief}\n\n"
        f"---\n\n"
        f"## DRAFT ARTICLE TO REVIEW\n\n"
        f"{draft}"
    )

    review = call_sonnet(client, full_system, user_content, MAX_TOKENS_REVIEW)
    return review


def run_editorial(client, basics: str, briefs: dict,
                  phase: str = "draft", draft: str = None, reviews: dict = None) -> str:
    """Run the editorial synthesis agent (draft or final pass)."""
    system_prompt = load_prompt("editorial_rules.md")

    if phase == "draft":
        editorial_prompt = load_prompt("agent_editorial.md")
        full_system = f"{editorial_prompt}\n\n---\n\n{system_prompt}"

        user_content = f"## PROPERTY BASICS\n\n{basics}\n\n"
        for name, brief in briefs.items():
            user_content += f"---\n\n## {name.upper()} ANALYST BRIEF\n\n{brief}\n\n"

    elif phase == "final":
        editorial_prompt = load_prompt("agent_editorial_final.md")
        full_system = f"{editorial_prompt}\n\n---\n\n{system_prompt}"

        user_content = f"## DRAFT ARTICLE\n\n{draft}\n\n---\n\n## SPECIALIST REVIEWS\n\n"
        for name, review in reviews.items():
            user_content += f"### {name.upper()} Review\n{review}\n\n"

    article = call_sonnet(client, full_system, user_content, MAX_TOKENS_ARTICLE)
    return article


# ── Structured Data Builder ─────────────────────────────────────────────────
def build_structured_data(data: dict) -> dict:
    """Build the structured data for template-driven visuals."""
    prop = data["property"]
    vd = prop.get("valuation_data", {})
    conf = vd.get("confidence", {})
    stats = data["listing_stats"]
    medians = data["medians"]
    basic = vd.get("subject_property", {}).get("features", {}).get("basic", {})
    npui = vd.get("subject_property", {}).get("features", {}).get("npui_breakdown", {})
    inputs = npui.get("inputs", {})

    floor_area = prop.get("total_floor_area") or prop.get("house_plan", {}).get("floor_area_sqm")
    lot_size = prop.get("lot_size_sqm", 0)

    # Feature comparison
    feature_comparison = {
        "bedrooms": {"value": prop.get("bedrooms"), "median": stats.get("median_beds")},
        "bathrooms": {"value": prop.get("bathrooms"), "median": stats.get("median_baths")},
        "parking": {"value": prop.get("carspaces"), "median": stats.get("median_cars")},
        "lot_size": {"value": lot_size, "median": stats.get("median_lot"), "unit": "sqm"},
        "floor_area": {"value": floor_area, "unit": "sqm"},
        "floor_to_land_ratio": {"value": round(floor_area / lot_size, 2) if floor_area and lot_size else None},
    }

    # Condition summary from NPUI inputs
    condition_summary = {}
    condition_map = {
        "kitchen": "interior.kitchen_quality_score",
        "bathrooms": "interior.bathroom_quality_score",
        "interior": "interior.overall_interior_condition_score",
        "exterior": "exterior.overall_exterior_condition_score",
        "outdoor": "outdoor.outdoor_entertainment_score",
        "natural_light": "interior.natural_light_score",
        "layout": "layout.layout_efficiency_score",
    }
    for label, key in condition_map.items():
        val = inputs.get(key)
        if val is not None:
            condition_summary[label] = val

    # Valuation range
    valuation_range = {
        "estimate": conf.get("reconciled_valuation"),
        "low": conf.get("range", {}).get("low"),
        "high": conf.get("range", {}).get("high"),
        "confidence": conf.get("confidence"),
        "n_verified": conf.get("n_verified"),
        "n_total": conf.get("n_total"),
        "cv": conf.get("cv"),
    }

    # Suburb trend
    suburb_trend = []
    for m in medians[-6:]:
        suburb_trend.append({
            "quarter": m["date"],
            "median": m["median"],
            "count": m["count"],
        })

    # Transaction timeline
    timeline_data = []
    timeline = prop.get("scraped_data", {}).get("property_timeline", [])
    transactions = prop.get("transactions", [])
    for t in (timeline or transactions):
        entry = {
            "date": t.get("date"),
            "category": t.get("category", t.get("source", "")),
            "price": t.get("price"),
            "days_on_market": t.get("days_on_market"),
            "type": t.get("type", ""),
        }
        timeline_data.append(entry)

    # Location scorecard
    pois = prop.get("nearby_pois", {}).get("by_category", {})
    location_scorecard = {}
    for category in ["primary_school", "secondary_school", "supermarket", "childcare", "park", "cafe"]:
        items = pois.get(category, [])
        if items:
            nearest = items[0]
            location_scorecard[category] = {
                "name": nearest.get("name"),
                "distance_km": nearest.get("distance_km"),
            }
    location_scorecard["beach_distance_km"] = basic.get("beach_distance_km")

    # Price position
    price_position = {
        "estimate": conf.get("reconciled_valuation"),
        "suburb_median": medians[-1]["median"] if medians else None,
        "suburb_median_quarter": medians[-1]["date"] if medians else None,
        "listing_price": prop.get("price"),
    }

    return {
        "feature_comparison": feature_comparison,
        "condition_summary": condition_summary,
        "valuation_range": valuation_range,
        "suburb_trend": suburb_trend,
        "transaction_timeline": timeline_data,
        "location_scorecard": location_scorecard,
        "price_position": price_position,
    }


# ── Property Basics (for editorial agent) ──────────────────────────────────
def build_basics_text(data: dict) -> str:
    """Build a short basics text for the editorial agent."""
    prop = data["property"]
    basic = prop.get("valuation_data", {}).get("subject_property", {}).get("features", {}).get("basic", {})
    floor_area = prop.get("total_floor_area") or prop.get("house_plan", {}).get("floor_area_sqm")

    photo_url = ""
    images = prop.get("property_images", prop.get("scraped_property_images", []))
    if images:
        photo_url = images[0] if isinstance(images[0], str) else images[0].get("url", "")

    lines = [
        f"Address: {prop['address']}",
        f"Type: {prop.get('property_type', 'House')} | Tenure: {prop.get('property_tenure_desc', 'Freehold')}",
        f"Bedrooms: {prop.get('bedrooms')} | Bathrooms: {prop.get('bathrooms')} | Parking: {prop.get('carspaces')}",
        f"Lot: {prop.get('lot_size_sqm', '?')} sqm | Floor: {floor_area or '?'} sqm | Built: ~{basic.get('approximate_build_year', '?')}",
        f"Price: {prop.get('price', 'Unknown')}",
        f"Listed: {prop.get('first_listed_date', '?')}",
        f"Agent: {prop.get('agent_name', '?')} — {prop.get('agency', '?')}",
        f"Suburb: {data['suburb_display']}",
        f"Photo URL (ONE photo only): {photo_url}",
        "",
        "CRITICAL: Fields Estate is NOT the listing agent. The article must include a disclaimer",
        f"directing all enquiries to {prop.get('agent_name', 'the listing agent')} at {prop.get('agency', 'the listing agency')}.",
    ]
    return "\n".join(lines)


# ── Storage ─────────────────────────────────────────────────────────────────
def store_analysis(mongo, slug: str, article_text: str, structured: dict,
                   briefs: dict, reviews: dict, data: dict):
    """Store the generated analysis in MongoDB."""
    prop = data["property"]
    sm = mongo["system_monitor"]

    # Parse meta tags from the article
    meta_title = ""
    meta_description = ""
    photo_caption = ""
    if "<!-- META -->" in article_text:
        meta_section = article_text.split("<!-- META -->")[1]
        for line in meta_section.strip().split("\n"):
            line = line.strip()
            if line.startswith("title:"):
                meta_title = line[6:].strip()
            elif line.startswith("description:"):
                meta_description = line[12:].strip()
            elif line.startswith("photo_caption:"):
                photo_caption = line[14:].strip()

    # Strip meta section from article body
    article_body = article_text.split("<!-- META -->")[0].strip() if "<!-- META -->" in article_text else article_text

    # Get first photo URL
    images = prop.get("property_images", prop.get("scraped_property_images", []))
    photo_url = ""
    if images:
        photo_url = images[0] if isinstance(images[0], str) else images[0].get("url", "")

    doc = {
        "property_id": prop["_id"],
        "slug": slug,
        "address": prop["address"],
        "suburb": data["suburb_slug"],
        "suburb_display": data["suburb_display"],

        "article_markdown": article_body,
        "meta_title": meta_title or f"{prop['address']} — Independent Analysis | Fields Estate",
        "meta_description": meta_description or f"Independent property analysis for {prop['address']}.",
        "headline": article_body.split("\n")[0].lstrip("# ").strip() if article_body else "",

        "listing_agent": prop.get("agent_name", ""),
        "listing_agency": prop.get("agency", ""),

        "reconciled_valuation": structured.get("valuation_range", {}).get("estimate"),
        "confidence_level": structured.get("valuation_range", {}).get("confidence"),

        "structured_data": structured,
        "photo_url": photo_url,
        "photo_caption": photo_caption,

        "briefs": briefs,
        "reviews": reviews,

        "generated_at": datetime.now(AEST).isoformat(),
        "generated_by": MODEL,
        "listing_status": prop.get("listing_status", "for_sale"),
        "status": "draft",  # manual review before publishing
    }

    sm["property_analyses"].update_one(
        {"slug": slug},
        {"$set": doc, "$setOnInsert": {"created_at": datetime.now(AEST).isoformat()}},
        upsert=True,
    )
    print(f"\n✅ Stored analysis for {slug} in system_monitor.property_analyses")
    return doc


# ── Main Pipeline ───────────────────────────────────────────────────────────
def generate_analysis(mongo, anthropic_client, slug: str,
                      dry_run: bool = False, stop_after_phase: int = None):
    """Run the full 4-phase multi-agent pipeline."""
    print(f"\n{'='*60}")
    print(f"GENERATING ANALYSIS: {slug}")
    print(f"{'='*60}")

    # Collect data
    print("\n📦 Collecting property data...")
    data = collect_property_data(mongo, slug)
    prop = data["property"]
    print(f"   Property: {prop['address']}")
    print(f"   Suburb: {data['suburb_display']}")
    print(f"   Beds/Bath/Car: {prop.get('bedrooms')}/{prop.get('bathrooms')}/{prop.get('carspaces')}")

    # Build data packages
    print("\n📋 Building data packages...")
    packages = {
        "space": build_space_package(data),
        "condition": build_condition_package(data),
        "valuation": build_valuation_package(data),
        "market": build_market_package(data),
        "location": build_location_package(data),
    }

    if dry_run:
        print("\n--- DRY RUN: Data packages ---")
        for name, pkg in packages.items():
            print(f"\n{'='*40} {name.upper()} {'='*40}")
            print(pkg[:1500])
            print("..." if len(pkg) > 1500 else "")
        return

    # ── PHASE 1: Specialist briefs ──
    print("\n🔬 Phase 1: Running specialist agents in parallel...")
    briefs = {}
    with concurrent.futures.ThreadPoolExecutor(max_workers=5) as executor:
        futures = {
            executor.submit(run_specialist, anthropic_client, name, pkg): name
            for name, pkg in packages.items()
        }
        for future in concurrent.futures.as_completed(futures):
            name = futures[future]
            try:
                briefs[name] = future.result()
                print(f"   ✅ {name} brief complete ({len(briefs[name])} chars)")
            except Exception as e:
                print(f"   ❌ {name} brief FAILED: {e}")
                briefs[name] = f"(Brief unavailable due to error: {e})"

    if stop_after_phase == 1:
        print("\n--- Phase 1 briefs ---")
        for name, brief in briefs.items():
            print(f"\n{'='*40} {name.upper()} {'='*40}")
            print(brief)
        return

    # ── PHASE 2: Editorial draft ──
    print("\n✏️  Phase 2: Editorial agent writing draft...")
    basics = build_basics_text(data)
    draft = run_editorial(anthropic_client, basics, briefs, phase="draft")
    print(f"   ✅ Draft complete ({len(draft.split())} words)")

    if stop_after_phase == 2:
        print("\n--- Draft article ---")
        print(draft)
        return

    # ── PHASE 3: Specialist reviews ──
    print("\n🔍 Phase 3: Specialist reviews in parallel...")
    reviews = {}
    with concurrent.futures.ThreadPoolExecutor(max_workers=5) as executor:
        futures = {
            executor.submit(run_review, anthropic_client, name, briefs[name], draft): name
            for name in SPECIALIST_AGENTS
        }
        for future in concurrent.futures.as_completed(futures):
            name = futures[future]
            try:
                reviews[name] = future.result()
                print(f"   ✅ {name} review complete")
            except Exception as e:
                print(f"   ⚠️  {name} review failed (proceeding): {e}")
                reviews[name] = "(Review unavailable)"

    if stop_after_phase == 3:
        print("\n--- Reviews ---")
        for name, review in reviews.items():
            print(f"\n--- {name.upper()} ---")
            print(review)
        return

    # ── PHASE 4: Editorial final ──
    print("\n📝 Phase 4: Editorial agent producing final article...")
    final = run_editorial(
        anthropic_client, basics, briefs,
        phase="final", draft=draft, reviews=reviews
    )
    print(f"   ✅ Final article complete ({len(final.split())} words)")

    # Build structured data
    structured = build_structured_data(data)

    # Store
    doc = store_analysis(mongo, slug, final, structured, briefs, reviews, data)

    # Print summary
    print(f"\n{'='*60}")
    print(f"COMPLETE: {slug}")
    print(f"  Title: {doc['meta_title']}")
    print(f"  Words: {len(final.split())}")
    print(f"  Status: {doc['status']} (set to 'published' when ready)")
    print(f"{'='*60}")

    return doc


# ── CLI ─────────────────────────────────────────────────────────────────────
if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Generate property analysis article")
    parser.add_argument("--slug", required=True, help="Property URL slug")
    parser.add_argument("--dry-run", action="store_true", help="Show data packages without calling API")
    parser.add_argument("--phase", type=int, help="Stop after phase N (1-4)")
    args = parser.parse_args()

    mongo, anth = get_clients()
    generate_analysis(mongo, anth, args.slug,
                      dry_run=args.dry_run,
                      stop_after_phase=args.phase)
