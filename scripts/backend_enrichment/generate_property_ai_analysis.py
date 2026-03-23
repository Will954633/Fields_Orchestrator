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

    # Photo analysis summary (GPT-4 Vision — property_valuation_data)
    pva = prop.get("property_valuation_data", {})
    if pva:
        po = pva.get("property_overview", {})
        reno = pva.get("renovation", {})
        meta = pva.get("property_metadata", {})
        cond_sum = pva.get("condition_summary", {})

        lines.append(f"\nPhoto analysis (GPT-4 Vision) — CRITICAL DATA:")
        lines.append(f"  Overall condition: {po.get('overall_condition', '?')} ({po.get('overall_condition_score', '?')}/10)")
        lines.append(f"  Architectural style: {po.get('architectural_style', '?')}")
        lines.append(f"  Stories: {po.get('number_of_stories', '?')}")

        # Renovation — key indicator of new build
        if reno:
            lines.append(f"  Renovation status: {reno.get('status', reno.get('renovation_status', '?'))}")
            lines.append(f"  Renovation age: {reno.get('estimated_age', reno.get('renovation_age', '?'))}")
            lines.append(f"  Scope: {reno.get('scope', '?')}")

        lines.append(f"  Prestige tier: {meta.get('prestige_tier', '?')}")
        lines.append(f"  Market appeal: {meta.get('market_appeal', meta.get('market_appeal_score', '?'))}/10")

        # Overall score summary
        if cond_sum:
            lines.append(f"  Overall score: {cond_sum.get('overall_score', '?')}/10")

        # Key rooms with actual sub-structure
        for room_key in ["kitchen", "bathrooms", "bedrooms", "living_areas", "outdoor", "exterior"]:
            room = pva.get(room_key, {})
            if room and isinstance(room, dict):
                # Try common score fields
                cond = room.get("condition_score", room.get("condition", "?"))
                qual = room.get("quality_score", room.get("quality", "?"))
                visible = room.get("visible", True)
                # Build feature list from notable fields
                notable = []
                for k, v in room.items():
                    if isinstance(v, str) and v not in ("true", "false", "?", "") and k not in ("visible", "room_type"):
                        if any(word in k for word in ["material", "type", "style", "bench", "pool", "view"]):
                            notable.append(f"{k}: {v}")
                feat_str = f" — {', '.join(notable[:4])}" if notable else ""
                if cond != "?" or qual != "?":
                    lines.append(f"  {room_key}: condition {cond}/10, quality {qual}/10{feat_str}")
                elif notable:
                    lines.append(f"  {room_key}: {', '.join(notable[:4])}")

        # Unique selling features
        unique = meta.get("unique_selling_features", [])
        if unique:
            lines.append(f"  Unique features: {', '.join(unique) if isinstance(unique, list) else unique}")

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


def format_medians(suburb_medians: List[Dict]) -> str:
    if not suburb_medians:
        return "  No recent data available"
    return "\n".join(f"  {d['date']}: ${d['median']:,} ({d['count']} sales)" for d in suburb_medians)


def format_competing(competing_listings: List[Dict]) -> str:
    lines = []
    for c in competing_listings[:25]:
        price = c.get("price_display", "Price TBA")
        beds = c.get("bedrooms", "?")
        baths = c.get("bathrooms", "?")
        lot = f", {c.get('lot_size_sqm')}sqm" if c.get("lot_size_sqm") else ""
        lines.append(f"  - {c.get('address', '?')}: {price} ({beds}bed/{baths}bath{lot})")
    return "\n".join(lines) if lines else "  None available"


def format_sales(recent_sales: List[Dict]) -> str:
    lines = []
    for s in recent_sales[:15]:
        price = f"${s['sold_price']:,}" if s.get("sold_price") else "?"
        date = s.get("sold_date", "?")
        beds = s.get("bedrooms", "?")
        lot = f", {s.get('lot_size_sqm')}sqm" if s.get("lot_size_sqm") else ""
        lines.append(f"  - {s.get('address', '?')}: {price} on {date} ({beds}bed{lot})")
    return "\n".join(lines) if lines else "  No recent sales data"


# ---------------------------------------------------------------------------
# Multi-agent pipeline: 3 specialist agents + 1 editor
# ---------------------------------------------------------------------------

VOICE_RULES = """RULES: No superlatives (never "stunning", "nestled", "boasting", "rare opportunity", "robust market"). Dollar figures like $1,250,000 not "$1.25m". Suburbs always capitalised. Be specific — use exact numbers. Be direct — no filler."""

def build_price_agent_prompt(prop_summary: str, medians: str, competing: str, sales: str, suburb: str) -> str:
    return f"""You are the PRICE ANALYST for Fields Estate. Your sole job is to find the price story for this property.

PROPERTY DATA:
{prop_summary}

SUBURB MEDIAN HOUSE PRICES ({suburb}, quarterly):
{medians}

COMPETING LISTINGS IN {suburb.upper()}:
{competing}

RECENT SALES IN {suburb.upper()}:
{sales}

TASK: Analyse the price data and write a briefing (150-250 words) covering:

1. TRANSACTION HISTORY: If the property has sold before, this is the most important data. What was paid? When? By whom (e.g. Public Trustee = deceased estate / forced sale)? What does the gap between then and now tell us?
2. ASKING PRICE vs SUBURB MEDIAN: How does the asking price compare to the current suburb median? Express as a ratio (e.g. 2.1x median).
3. ASKING PRICE vs COMPARABLE SALES: Are there recent sales that validate or challenge this price point?
4. PRICE SIGNAL: Is this "offers over" (i.e. a floor), auction (no ceiling), or fixed? What does that mean for the buyer?

Your briefing should identify the single most compelling price tension — the one number or comparison that would make a buyer stop and think.

{VOICE_RULES}

Write your briefing as plain text (not JSON). Start with your recommended angle in bold: **ANGLE: ...**"""


def build_property_agent_prompt(prop_summary: str) -> str:
    return f"""You are the PROPERTY ANALYST for Fields Estate. Your sole job is to assess what the buyer physically gets.

FULL PROPERTY DATA:
{prop_summary}

TASK: Analyse the physical property and write a briefing (150-250 words) covering:

1. BUILD QUALITY: What does the photo analysis tell us? Overall condition score, kitchen quality, bathroom quality, exterior condition. If the data says 9/10 across the board, that means a near-new or recently rebuilt home — SAY THAT EXPLICITLY. If renovation_status says "new build" or "0-5 years", the house has been knocked down and rebuilt.
2. LAYOUT & SIZE: Floor area, lot size, room dimensions, number of levels. How does this compare? Is it generously sized or compact?
3. UNIQUE FEATURES: Pool, lake views, waterfront, alfresco — what sets this property apart physically?
4. CONDITION vs PRICE: Does the physical quality justify what's being asked? A 9/10 condition new build is a very different proposition from a dated 1970s original.

CRITICAL: If property_valuation_data shows overall_condition_score of 8+ and renovation_status mentions "new" or "0-5 years", the property is a RECENT BUILD or COMPLETE RENOVATION. This is a KEY finding — it explains price premiums. Do not say "condition data unavailable" if scores are present.

Your briefing should identify the single most important physical characteristic that a buyer needs to understand.

{VOICE_RULES}

Write your briefing as plain text (not JSON). Start with your recommended angle in bold: **ANGLE: ...**"""


def build_market_agent_prompt(prop_summary: str, medians: str, competing: str, sales: str, suburb: str) -> str:
    return f"""You are the MARKET ANALYST for Fields Estate. Your sole job is to assess where this property sits in the current market.

PROPERTY DATA:
{prop_summary}

SUBURB MEDIAN HOUSE PRICES ({suburb}, quarterly):
{medians}

COMPETING LISTINGS IN {suburb.upper()}:
{competing}

RECENT SALES IN {suburb.upper()}:
{sales}

TASK: Analyse the market context and write a briefing (150-250 words) covering:

1. DAYS ON MARKET: How long has this been listed? What does that signal? (Fresh = untested, 30+ = potential issues, 60+ = stale)
2. SUPPLY: How many competing listings exist? Is this a crowded or thin market?
3. SUBURB TREND: Are medians rising, flat, or falling over the last 4-8 quarters? What direction is the market moving?
4. POSITIONING: Where does this property sit relative to the rest of the market? Top 10%? Middle of pack? Outlier?
5. BUYER IMPLICATIONS: Given all of the above, what leverage does a buyer have? Is this a seller's market or a buyer's market for this suburb right now?

Your briefing should identify the single most important market signal for a buyer considering this property.

{VOICE_RULES}

Write your briefing as plain text (not JSON). Start with your recommended angle in bold: **ANGLE: ...**"""


def build_editor_prompt(price_brief: str, property_brief: str, market_brief: str, address: str, suburb: str) -> str:
    return f"""You are the EDITORIAL DIRECTOR for Fields Estate. Three specialist analysts have each written a briefing on {address}. Your job is to synthesise their findings into a compelling editorial that HOOKS the reader and then delivers the evidence.

PRICE ANALYST BRIEFING:
{price_brief}

PROPERTY ANALYST BRIEFING:
{property_brief}

MARKET ANALYST BRIEFING:
{market_brief}

---

STRUCTURE:
1. HEADLINE — The hook. This is the most important line. It must make someone scrolling Google results STOP and click. The best headlines tell a STORY in under 80 characters: two data points separated by time, a price journey, a contradiction, or a question the reader can't ignore.

   GREAT HEADLINES (study these patterns):
   - "$845,000 in 2015. Now asking $3,495,000. What changed?"  ← price journey + question
   - "Sold for $650,000 five years ago. Rebuilt. Now $2.1M."   ← transformation story
   - "3 beds on 400sqm asking more than the 5-bed next door"   ← contradiction
   - "$200,000 above every comparable sale in the suburb"       ← outlier tension

   BAD HEADLINES (never do this):
   - "9/10 finish and lake views justify premium, but $3,495,000 is 1.94x the suburb median" ← too long, reads like a summary, answers itself
   - "Premium property in sought-after location" ← generic, no data
   - "Well-priced 4-bedroom home in Burleigh Waters" ← boring, no hook

   The headline should provoke a QUESTION in the reader's mind. Make them need to scroll down.

2. SUB-HEADLINE — One sentence (max 120 chars). Sets up the tension the insights will resolve. Frame the buyer's dilemma: "The rebuild explains the premium, but no comparable sale above $2M exists to confirm it."

3. INSIGHTS — 3-4 structured arguments (Minto Pyramid supporting points). Each is independent, scannable, data-rich. Together they answer the question the headline provoked.

4. VERDICT — One punchy closing sentence (max 25 words). A forward-looking signal.

OUTPUT: You must output EXACTLY this JSON structure — no markdown, no code fences, no ** bold markers, just raw JSON:

{{
  "headline": "max 80 chars — a STORY or PROVOCATION, not a summary",
  "sub_headline": "max 120 chars — the buyer's dilemma in one sentence",
  "insights": [
    {{
      "lead": "8-15 words, contains a data point, scannable on its own — NO ** markers",
      "detail": "1-2 sentences (25-50 words) supporting the lead. NO ** markers."
    }}
  ],
  "verdict": "max 25 words — forward-looking signal, not a prediction",
  "meta_title": "max 60 chars — data hook | Fields Estate",
  "meta_description": "max 155 chars — the tension + reason to click"
}}

REQUIREMENTS:
- Exactly 3-4 insights. Do NOT wrap text in ** bold markers — the frontend handles formatting.
- Each insight lead MUST contain a specific number (dollar amount, percentage, sqm, score, date, count)
- Insights should cover: (1) the price story, (2) the physical property, (3) the market context. A 4th can cover risk/opportunity.
- If the property is a new build or renovation (condition 8+/10, 0-5 years old), that MUST appear — it explains the price premium
- If purchased from the Public Trustee, that signals a deceased estate or forced sale — include this context
- DO NOT say data is "unavailable" if the briefings contain it — the analysts already extracted it.

{VOICE_RULES}"""


# ---------------------------------------------------------------------------
# Claude API call
# ---------------------------------------------------------------------------

def call_claude(prompt: str, api_key: str, max_tokens: int = 1500, parse_json: bool = True) -> Any:
    """Call Claude Sonnet. Returns parsed JSON if parse_json=True, else raw text."""
    client = anthropic.Anthropic(api_key=api_key)

    message = client.messages.create(
        model="claude-sonnet-4-6",
        max_tokens=max_tokens,
        messages=[{"role": "user", "content": prompt}],
    )

    raw = message.content[0].text.strip()

    if not parse_json:
        return raw

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


def run_multi_agent_pipeline(
    prop_summary: str,
    suburb_medians: List[Dict],
    competing_listings: List[Dict],
    recent_sales: List[Dict],
    suburb_name: str,
    address: str,
    api_key: str,
) -> Dict:
    """Run 3 specialist agents in sequence, then an editor agent to synthesise."""
    suburb_display = suburb_name.replace("_", " ").title()
    medians_str = format_medians(suburb_medians)
    competing_str = format_competing(competing_listings)
    sales_str = format_sales(recent_sales)

    # Agent 1: Price Analyst
    print("  [Agent 1/3] Price Analyst...")
    t0 = time.time()
    price_brief = call_claude(
        build_price_agent_prompt(prop_summary, medians_str, competing_str, sales_str, suburb_display),
        api_key, max_tokens=600, parse_json=False,
    )
    print(f"    Done ({time.time()-t0:.1f}s, {len(price_brief)} chars)")

    # Agent 2: Property Analyst
    print("  [Agent 2/3] Property Analyst...")
    t0 = time.time()
    property_brief = call_claude(
        build_property_agent_prompt(prop_summary),
        api_key, max_tokens=600, parse_json=False,
    )
    print(f"    Done ({time.time()-t0:.1f}s, {len(property_brief)} chars)")

    # Agent 3: Market Analyst
    print("  [Agent 3/3] Market Analyst...")
    t0 = time.time()
    market_brief = call_claude(
        build_market_agent_prompt(prop_summary, medians_str, competing_str, sales_str, suburb_display),
        api_key, max_tokens=600, parse_json=False,
    )
    print(f"    Done ({time.time()-t0:.1f}s, {len(market_brief)} chars)")

    # Editor: Synthesise into Minto Pyramid
    print("  [Editor] Synthesising...")
    t0 = time.time()
    result = call_claude(
        build_editor_prompt(price_brief, property_brief, market_brief, address, suburb_display),
        api_key, max_tokens=1500, parse_json=True,
    )
    print(f"    Done ({time.time()-t0:.1f}s)")

    # Attach the agent briefings for debugging
    result["_agent_briefings"] = {
        "price": price_brief,
        "property": property_brief,
        "market": market_brief,
    }

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

    # Run multi-agent pipeline (3 specialists + editor)
    print(f"\nRunning multi-agent pipeline (claude-sonnet-4-6)...")
    t0 = time.time()
    analysis = run_multi_agent_pipeline(
        summary, medians, competing, sales, suburb, address, api_key,
    )
    elapsed = time.time() - t0
    print(f"Pipeline complete in {elapsed:.1f}s (4 API calls)")

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
            suburb_display = suburb.replace("_", " ").title()
            medians_str = format_medians(medians)
            competing_str = format_competing(competing)
            sales_str = format_sales(sales)
            print(f"\n--- PRICE AGENT PROMPT ---\n{build_price_agent_prompt(summary, medians_str, competing_str, sales_str, suburb_display)[:800]}...")
            print(f"\n--- PROPERTY AGENT PROMPT ---\n{build_property_agent_prompt(summary)[:800]}...")
            print(f"\n--- MARKET AGENT PROMPT ---\n{build_market_agent_prompt(summary, medians_str, competing_str, sales_str, suburb_display)[:800]}...")
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
