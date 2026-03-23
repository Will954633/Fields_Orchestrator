#!/usr/bin/env python3
"""
Generate Property AI Analysis
==============================
Uses Claude Sonnet to generate editorial-quality property analysis:
  - Headline (H1) with a data-driven hook
  - Sub-headline (H2)
  - Analysis paragraph
  - SEO meta title + meta description

Data pipelines fed to the model:
  1. Full property document (listing details, photo analysis, floor plan, POIs, history)
  2. Suburb median price history (recent quarters)
  3. Active competing listings in the same suburb
  4. Recent sold comparables in the suburb
  5. Domain's automated valuation (if available)

Output is stored as `ai_analysis` field on the property document in Gold_Coast DB.

Usage:
    # Single property by slug:
    python generate_property_ai_analysis.py --slug 58-jabiru-avenue-burleigh-waters

    # Single property by address substring:
    python generate_property_ai_analysis.py --address "58 Jabiru Avenue"

    # All properties in target suburbs missing analysis:
    python generate_property_ai_analysis.py --backfill

    # Regenerate even if analysis already exists:
    python generate_property_ai_analysis.py --slug 58-jabiru-avenue-burleigh-waters --force
"""

from __future__ import annotations

import argparse
import json
import os
import sys
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional

import anthropic
from pymongo import MongoClient

REPO_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO_ROOT))

from shared.monitor_client import MonitorClient
from shared.ru_guard import cosmos_retry, sleep_with_jitter

TARGET_SUBURBS = ["robina", "varsity_lakes", "burleigh_waters"]

# ---------------------------------------------------------------------------
# Data pipeline helpers — each gathers one slice of context for the prompt
# ---------------------------------------------------------------------------

def get_property_doc(db, suburb: str, slug: str = None, address: str = None) -> Optional[Dict]:
    """Pipeline 1: Full property document."""
    query: Dict[str, Any] = {"listing_status": "for_sale"}
    if slug:
        query["url_slug"] = slug
    elif address:
        query["address"] = {"$regex": address, "$options": "i"}
    else:
        return None
    return cosmos_retry(lambda: db[suburb].find_one(query), f"get_property_{suburb}")


def get_suburb_medians(db, suburb: str) -> List[Dict]:
    """Pipeline 2: Recent quarterly median prices."""
    doc = cosmos_retry(lambda: db["suburb_median_prices"].find_one({"suburb": suburb}), "get_medians")
    if not doc or "data" not in doc:
        return []
    # Last 8 quarters
    return [d for d in doc["data"] if d.get("date", "") >= "2024-Q1"]


def get_competing_listings(db, suburb: str, exclude_id=None) -> List[Dict]:
    """Pipeline 3: Active for-sale listings in the same suburb (summary only)."""
    query: Dict[str, Any] = {"listing_status": "for_sale"}
    projection = {
        "address": 1, "price_display": 1, "bedrooms": 1, "bathrooms": 1,
        "car_spaces": 1, "lot_size_sqm": 1, "property_type_classification": 1,
        "days_on_domain": 1,
    }
    results = cosmos_retry(lambda: list(db[suburb].find(query, projection).limit(60)), f"competing_{suburb}")
    if exclude_id:
        results = [r for r in results if r.get("_id") != exclude_id]
    for r in results:
        r["_id"] = str(r["_id"])
    return results


def get_recent_sales(db, suburb: str, limit: int = 20) -> List[Dict]:
    """Pipeline 4: Recent sold properties with prices."""
    query: Dict[str, Any] = {
        "listing_status": "sold",
        "sold_price": {"$exists": True, "$gt": 0},
    }
    projection = {
        "address": 1, "sold_price": 1, "sold_date": 1, "bedrooms": 1,
        "bathrooms": 1, "lot_size_sqm": 1, "property_type_classification": 1,
    }
    results = cosmos_retry(
        lambda: list(db[suburb].find(query, projection).limit(limit * 3)),
        f"recent_sales_{suburb}",
    )
    # Sort in Python — Cosmos may lack an index on sold_date
    results.sort(key=lambda x: x.get("sold_date") or "", reverse=True)
    results = results[:limit]
    for r in results:
        r["_id"] = str(r["_id"])
    return results


def extract_domain_valuation(prop: Dict) -> Optional[Dict]:
    """Pipeline 5: Domain's automated valuation from the scraped data."""
    dv = prop.get("domain_valuation") or prop.get("avm") or {}
    if not dv:
        # Try alternate location
        dv = prop.get("price_estimation", {})
    if dv and any(dv.get(k) for k in ("low", "mid", "high", "lowerPrice", "midPrice", "upperPrice")):
        return {
            "low": dv.get("low") or dv.get("lowerPrice"),
            "mid": dv.get("mid") or dv.get("midPrice"),
            "high": dv.get("high") or dv.get("upperPrice"),
            "confidence": dv.get("confidence") or dv.get("accuracy"),
        }
    return None


# ---------------------------------------------------------------------------
# Prompt construction
# ---------------------------------------------------------------------------

def build_property_summary(prop: Dict) -> str:
    """Distill the full property doc into the key facts the model needs."""
    lines = []

    # Core details
    lines.append(f"Address: {prop.get('address', 'Unknown')}")
    lines.append(f"Price: {prop.get('price_display', 'Not disclosed')}")
    lines.append(f"Type: {prop.get('property_type_classification', 'Unknown')}")
    lines.append(f"Bedrooms: {prop.get('bedrooms', '?')} | Bathrooms: {prop.get('bathrooms', '?')} | Car: {prop.get('car_spaces', '?')}")
    if prop.get("lot_size_sqm"):
        lines.append(f"Lot size: {prop['lot_size_sqm']} sqm")

    # Floor plan
    fpa = prop.get("floor_plan_analysis", {})
    if fpa.get("total_floor_area_sqm"):
        lines.append(f"Total floor area: {fpa['total_floor_area_sqm']} sqm")
    if fpa.get("levels"):
        lines.append(f"Levels: {fpa['levels']}")
    rooms = fpa.get("rooms", [])
    if rooms:
        room_strs = []
        for r in rooms:
            dims = r.get("dimensions", {})
            area = dims.get("area", "")
            room_strs.append(f"  - {r.get('room_name', '?')}: {dims.get('length', '?')}x{dims.get('width', '?')}m ({area} sqm)")
        lines.append("Room dimensions:\n" + "\n".join(room_strs))

    # Days on market
    dom = prop.get("days_on_domain") or prop.get("days_on_market")
    if dom:
        lines.append(f"Days on market: {dom}")

    # Agent
    agent = prop.get("agent_name") or prop.get("listing_agent", {}).get("name")
    agency = prop.get("agency_name") or prop.get("listing_agent", {}).get("agency")
    if agent:
        lines.append(f"Agent: {agent}" + (f", {agency}" if agency else ""))

    # Features
    features = prop.get("features") or prop.get("property_features", [])
    if features:
        lines.append(f"Features: {', '.join(features) if isinstance(features, list) else features}")

    # Transaction history — field name is "transactions"
    history = prop.get("transactions") or prop.get("property_history") or prop.get("transaction_history", [])
    if history:
        lines.append("Transaction history (previous sales/rentals):")
        for h in history[:8]:
            price = h.get("price") or h.get("sold_price") or h.get("amount", "")
            date = h.get("date") or h.get("sold_date", "")
            htype = h.get("type") or h.get("event_type", "sold")
            agency_h = h.get("agency", "")
            source = h.get("source", "")
            if price:
                lines.append(f"  - {date}: {htype} ${price:,}" + (f" ({agency_h})" if agency_h else "") + (f" [source: {source}]" if source else ""))

    # Price history on current listing
    price_hist = prop.get("price_history", [])
    if price_hist:
        lines.append("Price changes on current listing:")
        for ph in price_hist:
            lines.append(f"  - {ph.get('date') or ph.get('recorded_at', '?')}: {ph.get('price_text') or ph.get('price', '?')}")

    # Photo analysis summary
    pva = prop.get("property_valuation_data", {})
    if pva:
        lines.append(f"\nPhoto analysis (GPT-4 Vision):")
        lines.append(f"  Overall condition: {pva.get('overall_condition', '?')}/10, Style: {pva.get('style', '?')}")
        lines.append(f"  Renovation status: {pva.get('renovation_status', '?')}, Age: {pva.get('renovation_age', '?')}")
        lines.append(f"  Prestige tier: {pva.get('prestige_tier', '?')}, Market appeal: {pva.get('market_appeal', '?')}/10")
        # Key rooms
        for room_key in ["kitchen", "living_room", "master_bedroom", "outdoor_area"]:
            room = pva.get(room_key, {})
            if room:
                cond = room.get("condition", "?")
                qual = room.get("quality", "?")
                feat = room.get("notable_features", [])
                feat_str = f" — {', '.join(feat)}" if feat else ""
                lines.append(f"  {room_key}: condition {cond}/10, quality {qual}/10{feat_str}")
        unique = pva.get("unique_selling_features", [])
        if unique:
            lines.append(f"  Unique features: {', '.join(unique)}")

    # Domain valuation
    dv = extract_domain_valuation(prop)
    if dv:
        lines.append(f"\nDomain automated valuation: Low ${dv['low']:,} | Mid ${dv['mid']:,} | High ${dv['high']:,} (confidence: {dv['confidence']})")

    # Valuation data (comparable sales)
    vd = prop.get("valuation_data", {})
    if vd and vd.get("confidence", {}).get("reconciled_valuation"):
        rv = vd["confidence"]["reconciled_valuation"]
        lines.append(f"Fields comparable-sales valuation: ${rv:,.0f}")

    # Property insights (percentiles)
    insights = prop.get("property_insights", {})
    if insights:
        lines.append("\nSuburb comparison:")
        for key in ["bedrooms", "floor_area", "lot_size", "bathrooms"]:
            ins = insights.get(key, {})
            sc = ins.get("suburbComparison", {})
            if sc:
                lines.append(f"  {key}: {sc.get('narrative', '?')} (median: {sc.get('suburbMedian', '?')})")

    # POIs
    pois = prop.get("nearest_pois", {})
    if pois:
        lines.append("\nNearest points of interest:")
        for cat, poi in pois.items():
            if isinstance(poi, dict) and poi.get("name"):
                dist = poi.get("distance_m", "?")
                lines.append(f"  {cat}: {poi['name']} ({dist}m)")

    return "\n".join(lines)


def build_prompt(
    property_summary: str,
    suburb_medians: List[Dict],
    competing_listings: List[Dict],
    recent_sales: List[Dict],
    suburb_name: str,
) -> str:
    """Build the full prompt for Claude."""

    # Format medians
    median_str = "\n".join(
        f"  {d['date']}: ${d['median']:,} ({d['count']} sales)"
        for d in suburb_medians
    ) if suburb_medians else "  No recent data available"

    # Format competing listings
    comp_lines = []
    for c in competing_listings[:25]:
        price = c.get("price_display", "Price TBA")
        beds = c.get("bedrooms", "?")
        baths = c.get("bathrooms", "?")
        lot = f", {c.get('lot_size_sqm')}sqm" if c.get("lot_size_sqm") else ""
        comp_lines.append(f"  - {c.get('address', '?')}: {price} ({beds}bed/{baths}bath{lot})")
    competing_str = "\n".join(comp_lines) if comp_lines else "  None available"

    # Format recent sales
    sold_lines = []
    for s in recent_sales[:15]:
        price = f"${s['sold_price']:,}" if s.get("sold_price") else "?"
        date = s.get("sold_date", "?")
        beds = s.get("bedrooms", "?")
        lot = f", {s.get('lot_size_sqm')}sqm" if s.get("lot_size_sqm") else ""
        sold_lines.append(f"  - {s.get('address', '?')}: {price} on {date} ({beds}bed{lot})")
    sold_str = "\n".join(sold_lines) if sold_lines else "  No recent sales data"

    suburb_display = suburb_name.replace("_", " ").title()

    return f"""You are a property data analyst for Fields Estate, a property intelligence platform on the Gold Coast, Australia. Your job is to write sharp, data-led editorial copy that helps buyers make informed decisions.

PROPERTY DATA:
{property_summary}

SUBURB MEDIAN HOUSE PRICES ({suburb_display}, quarterly):
{median_str}

COMPETING LISTINGS CURRENTLY FOR SALE IN {suburb_display.upper()}:
{competing_str}

RECENT SALES IN {suburb_display.upper()}:
{sold_str}

---

TASK: Write editorial analysis for this property page. You must output EXACTLY this JSON structure — no markdown, no code fences, just raw JSON:

{{
  "headline": "...",
  "sub_headline": "...",
  "insights": [
    {{
      "lead": "Bold opening statement with a key number",
      "detail": "1-2 sentences expanding on the lead with supporting data"
    }},
    {{
      "lead": "Second bold insight",
      "detail": "Supporting detail"
    }},
    {{
      "lead": "Third bold insight",
      "detail": "Supporting detail"
    }}
  ],
  "verdict": "One punchy closing sentence — the forward-looking takeaway",
  "meta_title": "...",
  "meta_description": "..."
}}

REQUIREMENTS:

1. **headline** — A single H1 sentence (max 80 chars) that hooks with a specific data point. Lead with a number, a price gap, a percentile, a time comparison, or a market tension. The BEST headlines reveal a tension: a gap between what something sold for and what it's listed at now, or between the asking price and the suburb median, or between the automated valuation and the listing price. The reader should think "I need to read this." Make it punchy — provoke a question in the reader's mind.

2. **sub_headline** — One H2 sentence (max 120 chars) that contextualises the headline within the suburb market. It should frame the buyer's key question.

3. **insights** — An array of exactly 3-4 insight objects. Each has:
   - **lead**: A bold, punchy statement (8-15 words) that makes the reader's eye stop. Must contain a specific number or data point. Think of it as a sub-heading that tells the story on its own.
   - **detail**: 1-2 sentences (25-50 words) that support the lead with additional data, context, or implication. Connect the data point to what it means for the buyer.

   The insights should flow as a narrative:
   - Insight 1: THE PRICE STORY — What is being asked vs what was paid, or vs suburb median. If the property has prior transaction history, this is CRITICAL. The gap between purchase price and asking price IS the story.
   - Insight 2: WHAT YOU GET — The physical property (sqm, condition, build quality, layout) and how it compares to the suburb.
   - Insight 3: THE MARKET CONTEXT — Supply/demand signal, competing listings, where this sits relative to current market.
   - Insight 4 (optional): THE RISK/OPPORTUNITY — What's unknown, what the buyer can't yet confirm.

4. **verdict** — One sentence (max 25 words). A forward-looking observation about days on market, pricing tension, or what to watch. Not a prediction — a signal.

5. **meta_title** — SEO title tag (max 60 chars) that uses a data hook. Format: "[Data hook] | Fields Estate"

6. **meta_description** — SEO description (max 155 chars) with the property's key data tension and a reason to click.

VOICE: Direct, analytical, no fluff. You are the analyst who did the homework. The reader should trust you because you show your numbers, not because you used superlatives. Never use "stunning", "nestled", "boasting", "rare opportunity", or "robust market". Use dollar figures like $1,250,000 not "$1.25m". Suburbs always capitalised."""


# ---------------------------------------------------------------------------
# Claude API call
# ---------------------------------------------------------------------------

def call_claude(prompt: str, api_key: str) -> Dict:
    """Call Claude Sonnet and parse the JSON response."""
    client = anthropic.Anthropic(api_key=api_key)

    message = client.messages.create(
        model="claude-sonnet-4-6",
        max_tokens=1500,
        messages=[{"role": "user", "content": prompt}],
    )

    raw = message.content[0].text.strip()

    # Strip markdown code fences if present
    if raw.startswith("```"):
        raw = raw.split("\n", 1)[1] if "\n" in raw else raw[3:]
        if raw.endswith("```"):
            raw = raw[:-3]
        raw = raw.strip()

    try:
        result = json.loads(raw)
    except json.JSONDecodeError as e:
        print(f"[ERROR] Failed to parse Claude response as JSON: {e}")
        print(f"[DEBUG] Raw response:\n{raw[:500]}")
        raise

    # Validate required keys
    required = {"headline", "sub_headline", "insights", "verdict", "meta_title", "meta_description"}
    missing = required - set(result.keys())
    if missing:
        raise ValueError(f"Claude response missing keys: {missing}")
    if not isinstance(result.get("insights"), list) or len(result["insights"]) < 3:
        raise ValueError(f"insights must be an array of 3-4 items, got: {type(result.get('insights'))}")

    return result


# ---------------------------------------------------------------------------
# Store result
# ---------------------------------------------------------------------------

def store_analysis(db, suburb: str, property_id, analysis: Dict) -> None:
    """Write ai_analysis field to the property document."""
    analysis["generated_at"] = datetime.now(timezone.utc).isoformat()
    analysis["model"] = "claude-sonnet-4-6"

    cosmos_retry(lambda: db[suburb].update_one(
        {"_id": property_id},
        {"$set": {"ai_analysis": analysis}},
    ), "store_analysis")
    print(f"[OK] Stored ai_analysis on property {property_id}")


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def process_property(db, suburb: str, prop: Dict, api_key: str, force: bool = False) -> Dict:
    """Run the full pipeline for one property."""
    address = prop.get("address", "Unknown")
    prop_id = prop["_id"]

    if not force and prop.get("ai_analysis") and prop["ai_analysis"].get("headline"):
        print(f"[SKIP] {address} — already has ai_analysis (use --force to regenerate)")
        return prop["ai_analysis"]

    print(f"\n{'='*60}")
    print(f"Processing: {address}")
    print(f"{'='*60}")

    # Pipeline 1: property summary
    print("[1/5] Building property summary...")
    summary = build_property_summary(prop)

    # Pipeline 2: suburb medians
    print("[2/5] Fetching suburb medians...")
    medians = get_suburb_medians(db, suburb)

    # Pipeline 3: competing listings
    print("[3/5] Fetching competing listings...")
    competing = get_competing_listings(db, suburb, exclude_id=prop_id)

    # Pipeline 4: recent sales
    print("[4/5] Fetching recent sales...")
    sales = get_recent_sales(db, suburb)

    # Pipeline 5: domain valuation (already in property doc)
    print("[5/5] Extracting domain valuation...")
    dv = extract_domain_valuation(prop)
    if dv:
        print(f"  Domain AVM: ${dv['mid']:,} (low ${dv['low']:,} — high ${dv['high']:,})")
    else:
        print("  No domain valuation available")

    # Build prompt
    prompt = build_prompt(summary, medians, competing, sales, suburb)

    # Call Claude
    print(f"\nCalling Claude Sonnet (claude-sonnet-4-6)...")
    t0 = time.time()
    analysis = call_claude(prompt, api_key)
    elapsed = time.time() - t0
    print(f"Response received in {elapsed:.1f}s")

    # Print results
    print(f"\n--- GENERATED ANALYSIS ---")
    print(f"Headline:    {analysis['headline']}")
    print(f"Sub-head:    {analysis['sub_headline']}")
    for i, ins in enumerate(analysis.get('insights', []), 1):
        print(f"Insight {i}:   {ins['lead']}")
        print(f"  Detail:    {ins['detail'][:120]}...")
    print(f"Verdict:     {analysis.get('verdict', '?')}")
    print(f"Meta title:  {analysis['meta_title']}")
    print(f"Meta desc:   {analysis['meta_description']}")

    # Store
    store_analysis(db, suburb, prop_id, analysis)

    return analysis


def find_suburb_for_slug(db, slug: str) -> Optional[tuple]:
    """Search target suburbs for a property by slug. Returns (suburb, doc) or None."""
    for suburb in TARGET_SUBURBS:
        doc = cosmos_retry(lambda s=suburb: db[s].find_one({"url_slug": slug, "listing_status": "for_sale"}), f"find_slug_{suburb}")
        if doc:
            return suburb, doc
    return None


def find_suburb_for_address(db, address: str) -> Optional[tuple]:
    """Search target suburbs for a property by address substring."""
    for suburb in TARGET_SUBURBS:
        doc = cosmos_retry(lambda s=suburb: db[s].find_one({
            "address": {"$regex": address, "$options": "i"},
            "listing_status": "for_sale",
        }), f"find_addr_{suburb}")
        if doc:
            return suburb, doc
    return None


def main():
    parser = argparse.ArgumentParser(description="Generate AI property analysis using Claude Sonnet")
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument("--slug", help="Property URL slug (e.g. 58-jabiru-avenue-burleigh-waters)")
    group.add_argument("--address", help="Address substring to match")
    group.add_argument("--backfill", action="store_true", help="Process all properties missing ai_analysis")
    parser.add_argument("--force", action="store_true", help="Regenerate even if analysis exists")
    parser.add_argument("--suburb", help="Restrict to one suburb (for --backfill)")
    parser.add_argument("--dry-run", action="store_true", help="Show prompt but don't call Claude")
    args = parser.parse_args()

    # API key
    api_key = os.environ.get("ANTHROPIC_SONNET_API_KEY") or os.environ.get("ANTHROPIC_API_KEY")
    if not api_key:
        print("[ERROR] No ANTHROPIC_SONNET_API_KEY or ANTHROPIC_API_KEY in environment")
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

        if args.dry_run:
            summary = build_property_summary(prop)
            medians = get_suburb_medians(db, suburb)
            competing = get_competing_listings(db, suburb, exclude_id=prop["_id"])
            sales = get_recent_sales(db, suburb)
            prompt = build_prompt(summary, medians, competing, sales, suburb)
            print(f"\n--- PROMPT ({len(prompt)} chars) ---\n{prompt}")
            return

        process_property(db, suburb, prop, api_key, force=args.force)

    elif args.address:
        result = find_suburb_for_address(db, args.address)
        if not result:
            print(f"[ERROR] No active listing found matching '{args.address}'")
            sys.exit(1)
        suburb, prop = result
        print(f"Found in {suburb}: {prop.get('address')}")
        process_property(db, suburb, prop, api_key, force=args.force)

    elif args.backfill:
        suburbs = [args.suburb] if args.suburb else TARGET_SUBURBS
        total = 0
        for suburb in suburbs:
            query = {"listing_status": "for_sale"}
            if not args.force:
                query["ai_analysis"] = {"$exists": False}
            props = cosmos_retry(lambda s=suburb: list(db[s].find(query)), f"backfill_{suburb}")
            print(f"\n{suburb}: {len(props)} properties to process")
            for prop in props:
                try:
                    process_property(db, suburb, prop, api_key, force=args.force)
                    total += 1
                    sleep_with_jitter(0.5)  # Rate limiting between API calls
                except Exception as e:
                    print(f"[ERROR] Failed on {prop.get('address', '?')}: {e}")
        print(f"\nDone. Processed {total} properties.")

    client.close()


if __name__ == "__main__":
    main()
