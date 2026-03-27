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
from typing import Any, Dict, List, Optional, Tuple

import anthropic
from pymongo import MongoClient

# Gemini (optional — used for data-gathering agents when --gemini-gather flag is set)
try:
    import google.generativeai as genai
    GEMINI_AVAILABLE = True
except ImportError:
    GEMINI_AVAILABLE = False

# OpenAI (optional — used for data-gathering agents when --openai-gather flag is set)
try:
    import openai as openai_module
    OPENAI_AVAILABLE = True
except ImportError:
    OPENAI_AVAILABLE = False

REPO_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO_ROOT))

from shared.monitor_client import MonitorClient
from shared.ru_guard import cosmos_retry, sleep_with_jitter

TARGET_SUBURBS = ["robina", "varsity_lakes", "burleigh_waters"]

# ---------------------------------------------------------------------------
# Configuration — all tuneable parameters in one place
# ---------------------------------------------------------------------------
PIPELINE_CONFIG = {
    "models": {
        "gather_default": "claude-opus-4-6",
        "gather_openai": "gpt-5.4",
        "gather_gemini": "gemini-3.1-pro-preview",
        "editor": "claude-opus-4-6",
        "reflection": "claude-opus-4-6",
        "fact_check": "claude-opus-4-6",
        "sabri": "claude-opus-4-6",
        "draft2": "claude-opus-4-6",
        "backfill": "claude-opus-4-6",
        "satellite_verify": "claude-opus-4-6",
    },
    "token_limits": {
        "gather": 600,
        "gather_gemini": 2000,
        "editor": 6000,
        "reflection": 1000,
        "fact_check": 1500,
        "backfill": 600,
        "sabri": 800,
        "draft2": 8000,
        "verify": 800,
    },
    "retry": {
        "max_draft2_attempts": 3,
        "fact_check_accept_threshold": 1,  # <= this many failures = accept draft
    },
}

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
        "address": 1, "price": 1, "price_display": 1, "bedrooms": 1, "bathrooms": 1,
        "car_spaces": 1, "lot_size_sqm": 1, "property_type_classification": 1,
        "days_on_domain": 1,
        "parsed_rooms.bedroom": 1, "total_floor_area": 1,
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
        "parsed_rooms.bedroom": 1, "total_floor_area": 1,
        "property_valuation_data.condition_summary.overall_score": 1,
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


def verify_satellite_claims(prop: Dict, api_key: str, db=None, suburb: str = None) -> Dict:
    """Verify satellite analysis claims using Claude Opus vision.

    Downloads the satellite image, annotates it with a red boundary marking the
    subject property, and asks Opus to verify each structured claim.
    Updates the property document in DB if corrections are made.
    """
    sat = prop.get("satellite_analysis", {})
    if not sat:
        return {}

    img_url = sat.get("satellite_image_url", "")
    if not img_url:
        return sat

    # Check if already verified
    if sat.get("opus_verified"):
        return sat

    categories = sat.get("categories", {})
    narrative = sat.get("narrative", {})
    address = prop.get("address", "Unknown")

    import requests, base64

    # Fetch a FRESH satellite image with a Google Maps red pin marker
    # This is more accurate than annotating the stored image because Google
    # geocodes the address to the correct rooftop location
    maps_key = os.getenv("GOOGLE_MAPS_STATIC_API_KEY") or os.getenv("GOOGLE_PLACES_API_KEY", "")
    lat = prop.get("LATITUDE")
    lng = prop.get("LONGITUDE")

    img_bytes = None
    if maps_key and lat and lng:
        try:
            # First geocode the address for rooftop accuracy
            geo_resp = requests.get("https://maps.googleapis.com/maps/api/geocode/json", params={
                "address": address,
                "key": maps_key,
            }, timeout=10)
            geo_data = geo_resp.json()
            if geo_data.get("results"):
                loc = geo_data["results"][0]["geometry"]["location"]
                lat, lng = loc["lat"], loc["lng"]

            map_resp = requests.get("https://maps.googleapis.com/maps/api/staticmap", params={
                "center": f"{lat},{lng}",
                "zoom": 19,
                "size": "640x640",
                "maptype": "satellite",
                "scale": 2,
                "markers": f"color:red|size:small|{lat},{lng}",
                "key": maps_key,
            }, timeout=15)
            if map_resp.status_code == 200 and map_resp.headers.get("content-type", "").startswith("image/"):
                img_bytes = map_resp.content
                print(f"  [SATELLITE] Fetched fresh satellite with Google pin at {lat:.6f},{lng:.6f}")
        except Exception as e:
            print(f"  [WARN] Google Maps pin image failed ({e}), falling back to stored image")

    # Fallback: use stored image without annotation
    if not img_bytes:
        try:
            resp = requests.get(img_url, timeout=30)
            if resp.status_code != 200:
                print(f"  [WARN] Could not download satellite image: HTTP {resp.status_code}")
                return sat
            img_bytes = resp.content
            print(f"  [SATELLITE] Fallback: using stored image (no pin)")
        except Exception as e:
            print(f"  [WARN] Satellite image download failed: {e}")
            return sat

    img_b64 = base64.standard_b64encode(img_bytes).decode("utf-8")

    # Build verification prompt
    import json as _json
    claims_text = _json.dumps(categories, indent=2)
    narrative_text = narrative.get("surrounding_land_use", "")

    prompt = f"""You are verifying satellite/aerial image analysis claims for a property at {address}.

IMPORTANT: The subject property is marked with a RED PIN/MARKER on the satellite image. The pin is placed at the geocoded rooftop location of {address}. Only assess what is directly adjacent to the lot where the RED PIN sits — not nearby properties.

A previous model analysed this aerial image and produced these structured claims:

{claims_text}

Surrounding land use narrative: "{narrative_text}"

YOUR TASK: Identify the specific lot where the RED PIN is placed. Then verify EACH claim for THAT specific lot:

1. **backs_onto** — What is DIRECTLY behind the lot where the RED PIN sits? Look at the rear boundary of THAT specific lot. Is it parkland/reserve, or are there other residential lots/houses behind it? A park nearby (even 2-3 lots away) is NOT the same as backing onto a park. Only mark "park" if the rear fence of the PIN's lot literally borders open parkland/reserve with no houses in between. If the park is nearby but separated by other lots, use "residential" for backs_onto and note "park within X lots / approximately Xm" separately.

2. **frontage** — What does the PIN's lot front onto? A quiet local street, a collector road, or a main road?

3. **parking_provision** — Is there a visible garage, carport, or driveway on the PIN's lot?

4. **pool_visible** — Is a pool clearly visible on the specific lot where the PIN sits?

5. **Any other claims** that look incorrect for the specific lot identified by the RED PIN.

OUTPUT as JSON only — no markdown, no code fences:
{{
    "corrections_needed": true/false,
    "corrected_categories": {{
        // Only include fields that need correction. Omit fields that are correct.
        // e.g. "adjacency": {{"backs_onto": ["residential"], "frontage": "standard_street"}}
    }},
    "corrected_narrative": "If the surrounding_land_use narrative is wrong, provide the corrected version. Otherwise null.",
    "verification_notes": "Brief explanation of what you verified and what you corrected."
}}"""

    client = anthropic.Anthropic(api_key=api_key)
    try:
        response = client.messages.create(
            model=PIPELINE_CONFIG["models"]["satellite_verify"],
            max_tokens=PIPELINE_CONFIG["token_limits"]["fact_check"],
            messages=[{
                "role": "user",
                "content": [
                    {
                        "type": "image",
                        "source": {
                            "type": "base64",
                            "media_type": "image/png",
                            "data": img_b64,
                        },
                    },
                    {
                        "type": "text",
                        "text": prompt,
                    },
                ],
            }],
        )

        result_text = response.content[0].text.strip()
        # Strip markdown fences if present
        if result_text.startswith("```"):
            result_text = result_text.split("\n", 1)[1]
            if result_text.endswith("```"):
                result_text = result_text.rsplit("```", 1)[0]

        result = _json.loads(result_text)

        if result.get("corrections_needed"):
            print(f"  [SATELLITE] Corrections needed: {result.get('verification_notes', '')[:120]}")

            # Apply corrections to categories
            corrected_cats = result.get("corrected_categories", {})
            for section, fields in corrected_cats.items():
                if section in categories and isinstance(fields, dict):
                    categories[section].update(fields)

            # Apply corrected narrative
            if result.get("corrected_narrative"):
                narrative["surrounding_land_use"] = result["corrected_narrative"]

            sat["categories"] = categories
            sat["narrative"] = narrative
            sat["opus_verification"] = {
                "verified_at": datetime.now(timezone.utc).isoformat(),
                "corrections_applied": True,
                "notes": result.get("verification_notes", ""),
                "corrected_fields": list(corrected_cats.keys()),
            }
        else:
            print(f"  [SATELLITE] All claims verified OK")
            sat["opus_verification"] = {
                "verified_at": datetime.now(timezone.utc).isoformat(),
                "corrections_applied": False,
                "notes": result.get("verification_notes", ""),
            }

        sat["opus_verified"] = True

        # Persist to DB
        if db is not None and suburb:
            try:
                cosmos_retry(lambda: db[suburb].update_one(
                    {"_id": prop["_id"]},
                    {"$set": {"satellite_analysis": sat}},
                ), "update_satellite_verification")
            except Exception as e:
                print(f"  [WARN] Could not persist satellite verification: {e}")

        # Update prop in-memory
        prop["satellite_analysis"] = sat
        return sat

    except Exception as e:
        print(f"  [WARN] Satellite verification failed: {e}")
        return sat


# ---------------------------------------------------------------------------
# Prompt construction
# ---------------------------------------------------------------------------

def build_property_summary(prop: Dict) -> str:
    """Distill the full property doc into the key facts the model needs."""
    lines = []

    # Core details
    lines.append(f"Address: {prop.get('address', 'Unknown')}")
    lines.append(f"Price: {prop.get('price_display') or prop.get('price') or 'Not disclosed'}")
    lines.append(f"Type: {prop.get('property_type') or prop.get('property_type_classification') or (prop.get('scraped_data', {}).get('features', {}).get('property_type')) or 'Unknown'}")
    car = prop.get('carspaces') or prop.get('car_spaces') or (prop.get('scraped_data', {}).get('features', {}).get('car_spaces'))
    lines.append(f"Bedrooms: {prop.get('bedrooms', '?')} | Bathrooms: {prop.get('bathrooms', '?')} | Car spaces: {car or '?'}")
    if prop.get("lot_size_sqm"):
        lines.append(f"Lot size: {prop['lot_size_sqm']} sqm")

    # Floor area — internal living area is the primary figure (matches website display and valuation model)
    internal_floor = prop.get("enriched_data", {}).get("floor_area_sqm")
    total_floor = (
        prop.get("total_floor_area")
        or (prop.get("floor_plan_analysis") or {}).get("total_floor_area_sqm")
        or (prop.get("house_plan") or {}).get("floor_area_sqm")
        or (prop.get("processing_status") or {}).get("total_floor_area_sqm")
    )
    if internal_floor:
        lines.append(f"Internal floor area: {internal_floor} sqm (living area — this is the figure used in valuations and shown on the website)")
        if total_floor and total_floor != internal_floor:
            lines.append(f"Total building footprint: {total_floor} sqm (includes garage, covered outdoor, external areas)")
    elif total_floor:
        lines.append(f"Total floor area: {total_floor} sqm (may include external areas — internal living area not separately confirmed)")

    # Floor plan details
    fpa = prop.get("floor_plan_analysis", {})
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

    # Days on market + first listed date
    dom = prop.get("days_on_domain") or prop.get("days_on_market")
    if dom:
        lines.append(f"Days on market: {dom}")
    first_listed = prop.get("first_listed_timestamp") or prop.get("date_first_listed")
    if first_listed:
        # Parse to readable date for the agents
        fl_str = str(first_listed)[:10]  # YYYY-MM-DD
        try:
            from datetime import datetime
            fl_date = datetime.strptime(fl_str, "%Y-%m-%d")
            lines.append(f"First listed date: {fl_date.strftime('%d %B %Y')}")
        except Exception:
            lines.append(f"First listed date: {fl_str}")

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
    # CRITICAL: These are EXACT figures from public records. Models MUST use these exact numbers.
    history = prop.get("transactions") or prop.get("property_history") or prop.get("transaction_history", [])
    if history:
        lines.append("Transaction history — EXACT FIGURES (do NOT round, modify, or approximate these prices):")
        for h in history[:8]:
            price = h.get("price") or h.get("sold_price") or h.get("amount", "")
            date = h.get("date") or h.get("sold_date", "")
            htype = h.get("type") or h.get("event_type", "sold")
            agency_h = h.get("agency", "")
            source = h.get("source", "")
            if price:
                lines.append(f"  - {date}: {htype} EXACTLY ${price:,}" + (f" ({agency_h})" if agency_h else "") + (f" [source: {source}]" if source else ""))

    # Pre-calculated growth metrics (so the model doesn't have to compute CAGR)
    if history:
        import math
        # Get last sale with a price
        last_sale = None
        for h in history:
            p = h.get("price") or h.get("sold_price") or h.get("amount")
            d = h.get("date") or h.get("sold_date")
            if p and d:
                last_sale = {"price": p, "date": d}

        if last_sale:
            # Calculate against asking price
            asking = prop.get("price_numeric") or prop.get("price_value")
            if not asking:
                # Try to parse from price string
                price_str = str(prop.get("price", ""))
                import re
                price_match = re.search(r'[\$]?([\d,]+(?:\.\d+)?)', price_str.replace(',', ''))
                if price_match:
                    try:
                        asking = float(price_match.group(1).replace(',', ''))
                        if asking < 10000:  # probably in millions format
                            asking = None
                    except ValueError:
                        asking = None

            # Also get valuation (range + midpoint for internal calculations)
            val_confidence = prop.get("valuation_data", {}).get("confidence", {})
            val = val_confidence.get("reconciled_valuation")
            val_range = val_confidence.get("range", {})
            val_range_low = val_range.get("low")
            val_range_high = val_range.get("high")

            # Add the range to the property summary for the LLM
            if val_range_low and val_range_high:
                lines.append(f"\nFIELDS VALUATION RANGE (always quote as a range, NEVER as a single figure):")
                lines.append(f"  Range: ${val_range_low:,.0f} to ${val_range_high:,.0f}")
                lines.append(f"  Based on {val_confidence.get('n_verified', 0)} verified comparable sales")
                lines.append(f"  RULE: Present this as '$X to $Y based on N comparable sales'. Never quote the midpoint.")

            reference_price = val or asking  # prefer valuation midpoint for internal growth calc
            buy_price = last_sale["price"]
            buy_date = last_sale["date"]

            if reference_price and buy_price and buy_date:
                try:
                    buy_dt = datetime.strptime(str(buy_date)[:10], "%Y-%m-%d")
                    now_dt = datetime.now()
                    years = (now_dt - buy_dt).days / 365.25
                    if years > 0.5 and buy_price > 0:
                        total_growth_pct = ((reference_price - buy_price) / buy_price) * 100
                        cagr = (math.pow(reference_price / buy_price, 1 / years) - 1) * 100
                        ref_label = "valuation midpoint (internal — do NOT quote this exact figure to users)" if val else "asking price"
                        lines.append(f"\nPRE-CALCULATED GROWTH (use these exact figures, do NOT recalculate):")
                        lines.append(f"  Last purchased: ${buy_price:,.0f} on {buy_date}")
                        lines.append(f"  Current {ref_label}: ${reference_price:,.0f}")
                        lines.append(f"  Years held: {years:.1f}")
                        lines.append(f"  Total growth: {total_growth_pct:.1f}%")
                        lines.append(f"  CAGR (compound annual growth rate): {cagr:.1f}%")
                        lines.append(f"  DO NOT attempt to recalculate these numbers. Use them exactly as shown.")
                except Exception:
                    pass

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
            reno_level = reno.get('overall_renovation_level') or reno.get('status') or reno.get('renovation_status', '?')
            reno_recency = reno.get('renovation_recency') or reno.get('estimated_age') or reno.get('renovation_age', '?')
            reno_scope = reno.get('scope', '?')
            lines.append(f"  Renovation level: {reno_level}")
            lines.append(f"  Renovation recency: {reno_recency}")
            if reno_scope != '?':
                lines.append(f"  Scope: {reno_scope}")
            # Include specific renovation flags
            for flag in ['kitchen_renovated', 'bathrooms_renovated', 'flooring_updated']:
                val = reno.get(flag)
                if val is not None:
                    lines.append(f"  {flag}: {val}")
            if reno.get('modern_features_score'):
                lines.append(f"  Modern features score: {reno['modern_features_score']}/10")

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

        # Flag garage/parking data conflict between photo analysis and satellite
        photo_garage = pva.get("exterior", {}).get("garage_type", "?")
        sat_parking = prop.get("satellite_analysis", {}).get("categories", {}).get("lot_characteristics", {}).get("parking_provision", "?")
        if photo_garage != sat_parking and photo_garage != "?" and sat_parking != "?":
            lines.append(f"\n  ⚠️ PARKING DATA CONFLICT: Photo analysis says garage_type='{photo_garage}' but satellite analysis says parking_provision='{sat_parking}'. The listing data shows {car or '?'} car spaces. Reconcile these before making claims about parking.")

        # Unique selling features
        unique = meta.get("unique_selling_features", [])
        if unique:
            lines.append(f"  Unique features: {', '.join(unique) if isinstance(unique, list) else unique}")

    # Domain valuation
    dv = extract_domain_valuation(prop)
    if dv:
        lines.append(f"\nDomain automated valuation: Low ${dv['low']:,} | Mid ${dv['mid']:,} | High ${dv['high']:,} (confidence: {dv['confidence']})")

    # Valuation data (comparable sales) — ALWAYS present as a RANGE, never a single figure
    # Price is discovered, not set. A single valuation figure implies false precision.
    vd = prop.get("valuation_data", {})
    if vd and vd.get("recent_sales"):
        # Build range from adjusted comparable prices
        adjusted_prices = []
        for sale in vd.get("recent_sales", []):
            if sale.get("included_in_valuation") and sale.get("adjustment_result", {}).get("adjusted_price"):
                adjusted_prices.append(sale["adjustment_result"]["adjusted_price"])
        if adjusted_prices:
            range_low = min(adjusted_prices)
            range_high = max(adjusted_prices)
            n_comps = len(adjusted_prices)
            lines.append(f"\nFields COMPARABLE-SALES VALUATION RANGE (based on {n_comps} adjusted comparable sales):")
            lines.append(f"  Range: ${range_low:,.0f} to ${range_high:,.0f}")
            lines.append(f"  Number of comparables: {n_comps}")
            conf = vd.get("confidence", {})
            if conf.get("confidence"):
                lines.append(f"  Confidence level: {conf['confidence']} ({n_comps} comparable{'s' if n_comps != 1 else ''})")
            lines.append(f"  IMPORTANT: Do NOT quote a single valuation figure. Always present as a range. Price is discovered by the market, not set by a model.")

    # Valuation adjustment rates — what each feature is worth in this market
    rates = vd.get("adjustment_rates", {}).get("rates", {}) if vd else {}
    if rates:
        lines.append("\nVALUATION ADJUSTMENT RATES (what each feature is worth in this market — use these to price trade-offs):")
        rate_map = [
            ("floor_per_sqm", "Floor area"),
            ("land_per_sqm", "Land"),
            ("per_bedroom", "Per bedroom"),
            ("per_bathroom", "Per bathroom"),
            ("per_car_space", "Per car space"),
            ("per_pool", "Pool"),
            ("per_kitchen_point", "Per kitchen quality point"),
            ("per_renovation_quality_point", "Per renovation quality point"),
        ]
        for key, label in rate_map:
            val = rates.get(key)
            if val and isinstance(val, (int, float)):
                lines.append(f"  {label}: ${val:,.0f}")

    # Per-comparable adjustments — specific dollar differences vs named sold properties
    for sale in vd.get("recent_sales", []) if vd else []:
        if sale.get("included_in_valuation") and sale.get("adjustment_result"):
            adj = sale["adjustment_result"]
            lines.append(f"\nCOMPARABLE SALE (used in valuation): {sale.get('address', '?')}")
            lines.append(f"  Sold price: ${sale.get('price', 0):,.0f}")
            lines.append(f"  Adjusted to subject property: ${adj.get('adjusted_price', 0):,.0f}")
            lines.append(f"  Net adjustment: ${adj.get('total_adjustment', 0):+,.0f} ({adj.get('total_adjustment_pct', 0):.1%})")
            for feat, detail in adj.get("adjustments", {}).items():
                dollars = detail.get("dollars", 0)
                if dollars and dollars != 0:
                    lines.append(f"    {feat}: subject {detail.get('subject_value')} vs comp {detail.get('comp_value')} → ${dollars:+,.0f}")

    # Property insights (percentiles)
    insights = prop.get("property_insights", {})
    if insights:
        lines.append("\nSuburb comparison:")
        for key in ["bedrooms", "floor_area", "lot_size", "bathrooms"]:
            ins = insights.get(key, {})
            sc = ins.get("suburbComparison", {})
            if sc:
                lines.append(f"  {key}: {sc.get('narrative', '?')} (median: {sc.get('suburbMedian', '?')})")

    # Beach distance — include ALL nearby beaches with walking time
    beach = prop.get("nearest_beach_name")
    beach_km = prop.get("nearest_beach_distance_km")
    beach2 = prop.get("next_nearest_beach_name")
    beach2_km = prop.get("next_nearest_beach_distance_km")
    if beach and beach_km:
        walk_min = round(beach_km / 0.08)  # ~5 km/h walking = 0.083 km/min
        lines.append(f"\nBeach proximity (IMPORTANT — this is a key selling point for Gold Coast property):")
        # Classify walking distance
        if beach_km <= 0.8:
            walk_class = "VERY SHORT WALK (under 10 minutes)"
        elif beach_km <= 1.5:
            walk_class = "EASY WALKING DISTANCE (10-20 minutes)"
        elif beach_km <= 2.5:
            walk_class = "WALKABLE (20-30 minutes, most people would walk this)"
        elif beach_km <= 4.0:
            walk_class = "BIKEABLE / SHORT DRIVE (too far for a casual walk, 5 minutes by car)"
        else:
            walk_class = "DRIVING DISTANCE (not walkable)"
        lines.append(f"  Nearest beach: {beach} ({beach_km} km, ~{walk_min} min walk — {walk_class})")
        if beach2 and beach2_km:
            walk2_min = round(beach2_km / 0.08)
            if beach2_km <= 0.8:
                walk2_class = "VERY SHORT WALK"
            elif beach2_km <= 1.5:
                walk2_class = "EASY WALKING DISTANCE"
            elif beach2_km <= 2.5:
                walk2_class = "WALKABLE"
            elif beach2_km <= 4.0:
                walk2_class = "BIKEABLE / SHORT DRIVE"
            else:
                walk2_class = "DRIVING DISTANCE"
            lines.append(f"  Next nearest: {beach2} ({beach2_km} km, ~{walk2_min} min walk — {walk2_class})")
            if "burleigh" in beach2.lower():
                lines.append(f"  NOTE: Burleigh Heads Beach is one of the most iconic beaches within a city anywhere in Australia — a major lifestyle and property value anchor for this suburb. Being within walking distance of Burleigh Beach is a genuine differentiator.")

    # Agent description — the listing agent's own words (may contain facts not in structured data)
    agent_desc = prop.get("agents_description") or prop.get("description", "")
    if agent_desc and len(agent_desc) > 50:
        lines.append(f"\nAgent description (listing copy — may contain renovation details, lifestyle framing, or features not in structured data):")
        lines.append(f"  {agent_desc[:800]}")

    # Land utilization breakdown
    lu = insights.get("lot_size", {}).get("landUtilization", {}) if insights else {}
    if lu:
        lines.append(f"\nLand utilization breakdown:")
        lines.append(f"  Building footprint: {lu.get('buildingFootprint', '?')} sqm ({lu.get('buildingFootprintPercent', '?')}%)")
        lines.append(f"  Usable yard: {lu.get('usableYard', '?')} sqm ({lu.get('usableYardPercent', '?')}%)")
        lines.append(f"  Pool area: {lu.get('poolArea', '?')} sqm")
        lines.append(f"  Covered outdoor: {lu.get('coveredOutdoor', '?')} sqm")

    # Rental estimate (useful for investor buyer persona)
    rental = prop.get("scraped_data", {}).get("rental_estimate", {})
    if rental and rental.get("weekly_rent"):
        lines.append(f"\nRental estimate: ${rental['weekly_rent']}/week (yield: {rental.get('yield', '?')}%)")

    # Parking insight percentile
    parking_ins = insights.get("parking", {}).get("suburbComparison", {}) if insights else {}
    if parking_ins and parking_ins.get("percentile"):
        lines.append(f"Parking: {parking_ins.get('narrative', '?')} (median: {parking_ins.get('suburbMedian', '?')})")

    # POIs
    pois = prop.get("nearest_pois", {})
    if pois:
        lines.append("\nNearest points of interest:")
        for cat, poi in pois.items():
            if isinstance(poi, dict) and poi.get("name"):
                dist = poi.get("distance_m", "?")
                lines.append(f"  {cat}: {poi['name']} ({dist}m)")

    # Zoning data (from Gold Coast City Council)
    zoning = prop.get("zoning_data", {})
    if zoning:
        lines.append("\nZoning & planning data (Gold Coast City Council):")
        lines.append(f"  Zone: {zoning.get('zone', '?')}")
        if zoning.get("zone_detail"):
            lines.append(f"  Zone detail: {zoning['zone_detail']}")
        if zoning.get("cadastral_area_sqm"):
            lines.append(f"  Cadastral area: {zoning['cadastral_area_sqm']} sqm")
        if zoning.get("min_lot_size_sqm"):
            lines.append(f"  Minimum lot size: {zoning['min_lot_size_sqm']} sqm")
        if zoning.get("max_building_height_m"):
            lines.append(f"  Max building height: {zoning['max_building_height_m']}m")
        if zoning.get("max_storeys"):
            lines.append(f"  Max storeys: {zoning['max_storeys']}")
        if zoning.get("residential_density"):
            lines.append(f"  Residential density: {zoning['residential_density']}")
        if zoning.get("subdivision_possible") is not None:
            lines.append(f"  Subdivision possible: {zoning['subdivision_possible']} ({zoning.get('subdivision_potential_lots', '?')} lots)")
        # Flood
        if zoning.get("flood_overlay"):
            lines.append(f"  FLOOD OVERLAY: Yes (City Plan planning designation — modelled 1-in-100-year scenario, NOT a record of past flooding)")
            lines.append(f"  Flood depth classification: {zoning.get('flood_depth_description', '?')}")
            lines.append(f"  Ground vs designated flood level: {zoning.get('flood_freeboard_m', '?')}m ({zoning.get('flood_risk_note', '?')})")
            if zoning.get("flood_floor_clearance_m") is not None:
                lines.append(f"  Floor clearance above designated flood level: {zoning['flood_floor_clearance_m']}m")
            # ICA insurance probability zones
            if zoning.get("in_any_ica_zone") is False:
                lines.append(f"  ICA INSURANCE ZONES: This property does NOT fall within ANY of the 5 ICA insurance flood probability zones (1-in-5yr through 1-in-2000yr). The insurance industry's flood model assesses this location as LOWER RISK than the council overlay implies.")
            elif zoning.get("in_any_ica_zone") is True:
                ica = zoning.get("ica_flood_zones", {})
                in_zones = [k for k, v in ica.items() if v is True]
                lines.append(f"  ICA INSURANCE ZONES: Property IS within ICA zone(s): {', '.join(in_zones)}")
            lines.append(f"  DATA SOURCE: Gold Coast City Council ArcGIS flood mapping + ICA Insurance Flood Probability Zones")
            lines.append(f"  NOTE: Recommend FloodWise Property Report and insurer quotes for complete picture. Do NOT claim 'no property has ever flooded' — flash flooding HAS occurred in Burleigh Waters (2017, 2022).")
        else:
            lines.append(f"  Flood overlay: No (this property is NOT within a Gold Coast City Plan flood assessment overlay)")
        if zoning.get("heritage_listed"):
            lines.append(f"  HERITAGE LISTED: Yes")

    # Satellite analysis (aerial image assessment)
    sat = prop.get("satellite_analysis", {})
    if sat:
        cats = sat.get("categories", {})
        narr = sat.get("narrative", {})

        lines.append("\nSatellite / aerial image analysis — IMPORTANT CONTEXT:")

        # Adjacency — what's next to the property
        adj = cats.get("adjacency", {})
        if adj:
            if adj.get("backs_onto"):
                lines.append(f"  Backs onto: {adj['backs_onto']}")
            if adj.get("frontage"):
                lines.append(f"  Frontage: {adj['frontage']}")
            if adj.get("elevation_position"):
                lines.append(f"  Elevation: {adj['elevation_position']}")

        # Detractants — negative factors
        det = cats.get("detractants", {})
        if det:
            detractants = []
            for k, v in det.items():
                if v and str(v).lower() not in ("none", "no", "false", "low", "nil", "n/a"):
                    detractants.append(f"{k.replace('_', ' ')}: {v}")
            if detractants:
                lines.append(f"  DETRACTANTS: {'; '.join(detractants)}")

        # Amenity premiums — positive factors
        amen = cats.get("amenity_premiums", {})
        if amen:
            premiums = []
            for k, v in amen.items():
                if v and str(v).lower() not in ("none", "no", "false", "low", "nil", "n/a"):
                    premiums.append(f"{k.replace('_', ' ')}: {v}")
            if premiums:
                lines.append(f"  Amenity premiums: {'; '.join(premiums)}")

        # Lot characteristics
        lot_chars = cats.get("lot_characteristics", {})
        if lot_chars:
            for k, v in lot_chars.items():
                if v and str(v).lower() not in ("none", "n/a"):
                    lines.append(f"  {k.replace('_', ' ').title()}: {v}")

        # Neighbourhood
        hood = cats.get("neighbourhood", {})
        if hood:
            for k, v in hood.items():
                if v and str(v).lower() not in ("none", "n/a"):
                    lines.append(f"  {k.replace('_', ' ').title()}: {v}")

        # Key narrative summaries
        if narr:
            for key in ["surrounding_land_use", "road_proximity", "flood_drainage_risk",
                        "construction_activity", "overall_setting"]:
                val = narr.get(key)
                if val:
                    lines.append(f"  {key.replace('_', ' ').title()}: {val}")
            highlights = narr.get("buyer_highlights", [])
            if highlights:
                lines.append(f"  Buyer highlights: {'; '.join(highlights)}")

    return "\n".join(lines)


def format_medians(suburb_medians: List[Dict]) -> str:
    if not suburb_medians:
        return "  No recent data available"
    lines = []
    # Flag the most recent quarter as THE current median
    if suburb_medians:
        latest = suburb_medians[-1]
        lines.append(f"  ⚡ CURRENT SUBURB MEDIAN: ${latest['median']:,} ({latest['date']}, {latest['count']} sales) — USE THIS FIGURE when referencing the suburb median. Do NOT use older quarters.")
        lines.append("")
    lines.append("  Quarterly history (for trend context only):")
    for d in suburb_medians:
        marker = " ← CURRENT" if d == suburb_medians[-1] else ""
        lines.append(f"    {d['date']}: ${d['median']:,} ({d['count']} sales){marker}")
    return "\n".join(lines)


def format_competing(competing_listings: List[Dict]) -> str:
    # Pre-compute price transparency stats so the model doesn't have to count
    hidden_keywords = {"contact agent", "auction", "price on application", "eoi", "expression", "submit best", "contact agent for price guide"}
    has_price = 0
    hidden_price = 0
    for c in competing_listings:
        p = (c.get("price_display") or c.get("price") or "").strip().lower()
        if not p or any(kw in p for kw in hidden_keywords):
            hidden_price += 1
        else:
            has_price += 1

    total = has_price + hidden_price
    lines = [
        f"  FACT CHECK — COMPETING LISTINGS PRICE TRANSPARENCY:",
        f"  Total active listings: {total}",
        f"  With a price guide (offers over, fixed price, etc.): {has_price}",
        f"  Without a price guide (auction, contact agent, EOI): {hidden_price}",
        f"  DO NOT claim 'all prices are hidden' or 'zero price guides' — {has_price} of {total} listings show a price.",
        f"",
    ]
    for c in competing_listings[:25]:
        price = c.get("price_display") or c.get("price") or "Price TBA"
        beds = c.get("bedrooms", "?")
        baths = c.get("bathrooms", "?")
        lot = f", {c.get('lot_size_sqm')}sqm lot" if c.get("lot_size_sqm") else ""
        floor = c.get("total_floor_area")
        floor_str = f", {floor:.0f}sqm floor" if floor else ""
        master_room = (c.get("parsed_rooms") or {}).get("bedroom", {})
        ml, mw = master_room.get("length"), master_room.get("width")
        master_str = f", master {ml*mw:.0f}sqm" if ml and mw else ""
        lines.append(f"  - {c.get('address', '?')}: {price} ({beds}bed/{baths}bath{lot}{floor_str}{master_str})")
    return "\n".join(lines) if lines else "  None available"


def format_sales(recent_sales: List[Dict]) -> str:
    lines = []
    for s in recent_sales[:15]:
        price = f"${s['sold_price']:,}" if s.get("sold_price") else "?"
        date = s.get("sold_date", "?")
        beds = s.get("bedrooms", "?")
        baths = s.get("bathrooms", "?")
        lot = f", {s.get('lot_size_sqm')}sqm lot" if s.get("lot_size_sqm") else ""
        floor = s.get("total_floor_area")
        floor_str = f", {floor:.0f}sqm floor" if floor else ""
        master_room = (s.get("parsed_rooms") or {}).get("bedroom", {})
        ml, mw = master_room.get("length"), master_room.get("width")
        master_str = f", master {ml*mw:.0f}sqm" if ml and mw else ""
        cond = (s.get("property_valuation_data") or {}).get("condition_summary", {}).get("overall_score")
        cond_str = f", cond {cond}/10" if cond else ""
        lines.append(f"  - {s.get('address', '?')}: {price} on {date} ({beds}bed/{baths}bath{lot}{floor_str}{master_str}{cond_str})")
    return "\n".join(lines) if lines else "  No recent sales data"


# ---------------------------------------------------------------------------
# Multi-agent pipeline: 3 specialist agents + 1 editor
# ---------------------------------------------------------------------------

# Load the editorial prompt guide — shared context for all agents
_EDITORIAL_PROMPT_PATH = REPO_ROOT / "config" / "property_editorial_prompt.md"
EDITORIAL_GUIDE = ""
if _EDITORIAL_PROMPT_PATH.exists():
    EDITORIAL_GUIDE = _EDITORIAL_PROMPT_PATH.read_text()

# Load flood context for Burleigh Waters — expert-level background for agents
_FLOOD_CONTEXT_PATH = REPO_ROOT / "config" / "flood_context_burleigh_waters.md"
FLOOD_CONTEXT = ""
if _FLOOD_CONTEXT_PATH.exists():
    FLOOD_CONTEXT = _FLOOD_CONTEXT_PATH.read_text()

# Load the Core Principles of Selling — shared framework for all content agents
_SELLING_PRINCIPLES_PATH = REPO_ROOT / "drafts" / "core-principles-of-selling.md"
SELLING_PRINCIPLES = ""
if _SELLING_PRINCIPLES_PATH.exists():
    SELLING_PRINCIPLES = _SELLING_PRINCIPLES_PATH.read_text()

SHARED_MISSION = f"""
THE MISSION: You are part of a team writing property editorial content for Fields Estate. Your output feeds into a final editorial on property pages that appears alongside Google search results from Domain, realestate.com.au, and every other portal.

Our editorial philosophy: **We serve the buyer first with transparent, data-driven analysis. The way we handle trade-offs, price stories, and honest assessments IS our selling method.** A seller reading our content should think: "I want Fields to sell my property — they'd position it honestly and intelligently."

You are guided by the Core Principles of Selling. These are not abstract — they are your operating instructions:

{SELLING_PRINCIPLES[:6000] if SELLING_PRINCIPLES else "(Selling principles not loaded)"}

YOUR JOB as a specialist agent:
1. Find the STORY in the data — tensions, contradictions, trade-offs, human stories
2. Frame every trade-off as a VALUE EQUATION — what does the buyer get in exchange for accepting it? Close the loop: trade-off + what upgrading costs elsewhere + what you get instead.
3. Use COMPARABLE EVIDENCE to price feature gaps — "each extra sqm of floor area costs $3,000 in this market" or "properties with 16+ sqm masters sold for $X–$Y"
4. Transfer CONFIDENCE through specificity — exact figures, named comparable sales, dollar adjustments
5. Pre-answer the buyer's objections with data, not dismissal
6. IDENTIFY THE IDEAL BUYER — who is this property built for? Name them. "This is a home for downsizers who want everything finished" or "This is for a family that values outdoor space over floor area." Then name who it's NOT for: "If you need 200+ sqm of living space, the data says look elsewhere."
7. Frame around OUTCOMES, not specs — "single-level, pool, park behind the fence, weekends are yours" not "4bd/2ba/641sqm"
8. NEVER quote a single valuation figure — always present as a RANGE from comparable sales. Price is discovered by the market, not set by a model.
9. NEVER use flood data as a lead angle or headline seed — flood overlay is addressed as the final point only
10. For supply/scarcity data, quote the LAST 12 MONTHS of sales (not 20 months). Use 6 months if it builds stronger, legitimate scarcity.
11. WALKING DISTANCE TO SIGNIFICANT POIs: If the property is within walking distance (under 2.5 km) of a significant point of interest — especially a beach, major park, school, train station, or shopping centre — this is a KEY SELLING POINT that should be considered for inclusion in the content. Being able to walk to Burleigh Heads Beach or Nobby Beach is a lifestyle differentiator that most competing properties cannot match. State the distance, the walk time, and what it means for the buyer's daily life.

VOICE: No superlatives (never "stunning", "nestled", "boasting", "rare opportunity"). Dollar figures like $1,250,000 not "$1.25m". Suburbs capitalised. Be specific. Be conversational. Every sentence must earn its place.

PLAIN LANGUAGE RULE (CRITICAL — this is how real people talk):
Your reader is a normal person browsing Google on their phone. They have NEVER heard of percentiles, adjustment models, or coefficient of variation. Write like you're talking to a friend over coffee.

BANNED JARGON — never use these terms in ANY output:
- "Xth percentile" → say "smaller than most" / "bigger than most" / "one of the largest" / "about average"
- "adjustment model" → say "what similar homes sold for"
- "coefficient of variation" → just say "the range is wide" or "the data is thin"
- "comparable-adjusted range" → say "based on what similar homes sold for"
- "reconciled valuation" → never use this term at all
- "absorption rate" → say "how fast homes are selling"
- "median" → say "typical price" or "middle of the market" (use "median" only in FAQ answers for SEO)
- "price per sqm rate" → say "what each extra square metre costs"
- "gross yield" → say "rental return" (number is fine: "3.78% rental return")

TRANSLATION EXAMPLES:
BAD: "142 sqm of floor area (30th percentile), 3 bedrooms (32nd percentile)"
GOOD: "142 sqm — smaller than most homes in the suburb. Three bedrooms, which is also below average for this area."

BAD: "The adjustment model discounts $30,000 per cladding tier"
GOOD: "In this market, weatherboard costs you about $30,000 compared to rendered walls"

BAD: "81st percentile for floor area in BURLEIGH WATERS"
GOOD: "Bigger than roughly 4 in 5 homes currently for sale in BURLEIGH WATERS"

The DATA is still precise ($30,000, 142 sqm, 4 in 5). The LANGUAGE is plain. You keep the numbers but ditch the jargon wrapper.

DATA CONFIDENCE RULES (CRITICAL — violations cause fact-check failures):
- PHOTO ANALYSIS IS REAL DATA. If photo analysis shows stone benchtops (benchtop_material: "stone"), modern cabinets (cabinet_style: "modern"), condition 9/10, pool in excellent condition — these are FACTS from our AI photo analysis. Use them confidently: "stone benchtops, modern cabinetry, 9/10 condition" — not "the renovation is undisclosed."
- What photo analysis CAN tell you: materials (stone/laminate/timber), condition scores, pool presence and condition, renovation level (fully_renovated, cosmetically_updated, etc.), cladding type, landscaping quality. USE THESE.
- What photo analysis CANNOT tell you: the exact YEAR of renovation, the COST of renovation, WHO did the work, whether council permits were obtained. For these, say "the renovation year and spend are not disclosed in the listing data."
- If a LISTING field shows "?" (like car_spaces), check the listing data and agent description for the answer. If the listing states a number of car spaces, use that. Do NOT contradict the listing based on photo analysis — our photos may not have captured the garage.
- NEVER round or modify transaction prices. Use exact figures from the data.
- ALWAYS cite the specific data field you're drawing from when making factual claims.

CRITICAL — ROOMS WITH "visible": false AND null SCORES:
When a room (bathrooms, bedrooms, living areas) has "visible": false and ALL scores are null, it means our photo analysis system NEVER SAW that room. In this case:
- Do NOT call the room "unrenovated", "untouched", "dated", "original", or any other condition claim
- Do NOT use "bathrooms_renovated": false as proof of condition — that field is INFERRED from the absence of visible evidence, not from an actual assessment of the bathrooms
- The CORRECT framing is: "condition data not available for [room] — inspect in person" or "not photographed — no condition score on record"
- You MAY note that the room was not visible and recommend inspection, but you MUST NOT characterise its condition
- This applies to ALL renovation fields for rooms that were not photographed: bathrooms_renovated, flooring_updated, etc. If the room wasn't seen, the boolean is unreliable
- AUTOMATIC FACT-CHECK FAILURE: Any claim about the condition or renovation status of a room with visible: false and null scores will be marked ❌ FAILED

UNIVERSAL RULE — ABSENCE OF EVIDENCE IS NOT EVIDENCE OF ABSENCE:
This rule applies to EVERYTHING, not just bathrooms:
- If our photo analysis says garage_type: "none" — that means we didn't photograph a garage. It does NOT mean there is no garage. The listing or agent description is the authority on what exists.
- If our photo analysis didn't capture a feature, DO NOT state the feature is missing. Just don't mention it.
- NEVER write "no confirmed X", "no X detected", "no X identified in photos", "our analysis found no X". These all imply the feature doesn't exist when we simply didn't photograph it.
- If the LISTING says 2 car spaces but our photos say garage_type: none — trust the listing. The agent has been to the property. Our camera might have missed the garage.
- When in doubt, OMIT. Silence is better than a false negative. The reader can discover the garage at inspection. They cannot un-read a claim that it doesn't exist.

PRE-CALCULATED DATA RULE: If the property summary contains a "PRE-CALCULATED GROWTH" section with total growth %, CAGR, and years held — use THOSE EXACT NUMBERS. Do NOT recalculate from transaction prices. Your mental arithmetic will be wrong. The pre-calculated figures are computed by code and verified. Use them verbatim.

NOTE: You do NOT write headlines. A separate specialist handles that. Focus on substance, evidence, and value framing.
"""


def build_price_agent_prompt(prop_summary: str, medians: str, competing: str, sales: str, suburb: str) -> str:
    return f"""You are the PRICE & VALUE ANALYST for Fields Estate.

{SHARED_MISSION}

YOUR SELLING PRINCIPLES FOCUS:
- Principle #7: Price Is a Story, Not a Number — make the price make sense through multiple reference points
- Principle #4: Objections Are Data — pre-answer "is this overpriced?" and "is this underpriced?" with evidence

YOUR DOMAIN: Price data — transaction history, asking price, suburb medians, comparable sales, adjustment rates, listing method.

PROPERTY DATA (full JSON document — CRITICAL: "visible": false and null scores mean our analysis system did not capture that room, NOT that the seller deliberately excluded it. Do NOT draw conclusions from missing data. Do NOT claim rooms are "unrenovated" or "poor" based on missing scores. Only describe what the data actually shows):
{prop_summary}

SUBURB MEDIAN HOUSE PRICES ({suburb}, quarterly):
{medians}

COMPETING LISTINGS IN {suburb.upper()}:
{competing}

RECENT SALES IN {suburb.upper()}:
{sales}

---

BUILD THE PRICE NARRATIVE:

1. THE PRICE JOURNEY: Transaction history from first sale to current asking price.
   - Growth rate (CAGR), dollar gap, what happened between sales (renovation, forced sale, etc.)
   - If sold by Public Trustee/Mortgagee — that's context the buyer needs. State it factually.

2. MULTIPLE REFERENCE POINTS: Give the buyer at least 3 ways to anchor the price:
   - How it sits vs suburb median (ratio or %)
   - Fields comparable-sales valuation (if available)
   - Domain automated estimate (if available)
   - Per-comparable adjustments — use the VALUATION ADJUSTMENT RATES data to show specific dollar gaps

3. FEATURE-PRICED TRADE-OFFS: Use adjustment rates to price what the buyer IS and ISN'T getting:
   - "Floor area is 173 sqm (median). Each additional sqm costs $3,000 in this market."
   - "Properties with a third bathroom command ~$85,000 more."
   - Name specific sold properties where possible: "22 Manakin Ave sold for $1,657,000 with a 13.9 sqm master"

4. OBJECTION RESPONSES: Pre-answer the price objections a buyer would raise:
   - "It's overpriced" → here's the comparable evidence that supports/challenges the ask
   - "It's a bargain" → here's what you're giving up for the lower price

CRITICAL — NON-NEGOTIABLE RULE: Fields NEVER quotes a single valuation figure. ALWAYS present the valuation as a RANGE (e.g. "$2,120,000 to $2,700,000 based on 2 adjusted comparables"). NEVER write "Fields values this at $X" or "Our estimate is $X". A single number implies false precision — the final price depends on buyer competition, seller expectations, and negotiation dynamics. The range IS the valuation. Every sale is different. Our comparable-sales model establishes a defensible range, not an exact answer.

WRITE your briefing as 200-300 words of plain text. Start with:
**PRICE NARRATIVE:** [The price story in 2-3 sentences — using a valuation RANGE, not a single figure]
**KEY TENSION:** [The single price question a buyer needs to answer]
**OBJECTION RESPONSES:** [Top 2 buyer objections, pre-answered with data]

Then give the full price briefing. TAG each major point with the selling principle it demonstrates:
**PRINCIPLE #7 (Price Is a Story):** [what you wrote and why]
**PRINCIPLE #4 (Objections Are Data):** [what you wrote and why]
**PRINCIPLE #11 (Price Is Discovered):** [how you framed the valuation as a range, not a number]"""


def build_property_agent_prompt(prop_summary: str, competing: str, sales: str, suburb: str) -> str:
    return f"""You are the PROPERTY & TRADE-OFFS ANALYST for Fields Estate.

{SHARED_MISSION}

YOUR SELLING PRINCIPLES FOCUS:
- Principle #3: Trust Is Built by What You Don't Say — proactively surface every trade-off before the buyer discovers it
- Principle #2: People Buy Outcomes, Not Products — frame around lifestyle and outcomes, not just spec sheets

YOUR DOMAIN: The physical property — condition, build quality, floor plan, room dimensions, features, renovation. AND how each attribute compares to competing listings and recent sales.

FULL PROPERTY DATA (raw JSON — CRITICAL: "visible": false and null scores mean our analysis system did not capture that room, NOT that the seller deliberately excluded it. Do NOT draw conclusions from missing data. Do NOT claim rooms are "unrenovated" or "poor" based on missing scores. Only describe what the data actually shows):
{prop_summary}

COMPETING LISTINGS IN {suburb.upper()}:
{competing}

RECENT SALES IN {suburb.upper()}:
{sales}

---

BUILD THE PROPERTY NARRATIVE:

1. THE BUILD STORY: Condition score, renovation status, build quality. A 9/10 rebuild justifies a premium. A 7/10 original does not. State it clearly.

2. VALUE EQUATIONS FOR EVERY TRADE-OFF:
   For EVERY attribute that is at or below the suburb average, frame it as a value equation in PLAIN LANGUAGE:
   - Name the attribute and how it compares: "The master bedroom is 14.8 sqm — smaller than most homes in the suburb"
   - NEVER use percentiles (30th percentile, 81st percentile). Say "smaller than most", "bigger than average", "one of the largest", "about typical"
   - Show what the ALTERNATIVE costs by citing competing listings or recent sales with better specs
   - Example: "The master at 14.8 sqm is on the small side. 7 Seahawk Crescent sold for $1,850,000 with a 16.3 sqm master on a similar lot. That extra space costs roughly $50,000 more — and you lose the pool."
   - ALWAYS follow the trade-off with what the buyer GETS in exchange (location, pool, renovation, outdoor space)

3. OUTCOME FRAMING: What is the buyer actually buying?
   - Not "4 bed, 2 bath, 641 sqm" — but "a finished single-level home with a pool, outdoor entertaining, and a quiet street 1.5 km from the beach"
   - What lifestyle does this property enable? Who is the ideal buyer?

4. FLOOD POSITIONING: If the property has a flood overlay, mention it ONLY as the final point. Frame factually: council planning designation, ICA assessment, zero events. NEVER lead with flood.

WRITE your briefing as 200-300 words of plain text. Start with:
**VALUE EQUATIONS:** [List the top 2-3 trade-offs, each with: what you give up + what upgrading costs + what you get instead]
**OUTCOME FRAMING:** [What the buyer is actually buying — lifestyle, not specs. Paint the picture.]
**IDEAL BUYER:** [Who is this property FOR? Name them specifically. And who is it NOT for?]

Then give the full property briefing. TAG each major point with the selling principle it demonstrates:
**PRINCIPLE #2 (Outcomes Not Products):** [how you framed lifestyle over specs]
**PRINCIPLE #3 (Trust Through Transparency):** [what trade-offs you surfaced proactively]
**PRINCIPLE #5 (Ideal Buyer):** [who you identified as the target — and who should look elsewhere]

CRITICAL DATA RULES:
- PHOTO ANALYSIS IS EVIDENCE. If it shows stone benchtops, 9/10 condition, fully_renovated — state it as fact: "stone benchtops, modern cabinetry, scored 9/10." The photos are publicly visible — this is not a guess.
- What you CAN claim from photos: materials, condition scores, renovation level, pool condition, cladding type. These are real observations.
- What you CANNOT claim: the specific year of renovation, the cost, or whether permits were obtained. Say "the renovation year and cost are not disclosed" — NOT "the renovation is undisclosed" (the renovation itself is clearly visible).
- If car_spaces is "?" and garage_type is "none" in photo analysis, DO NOT claim there is no garage. Our photos simply may not have captured it. Use the listing data or agent description for parking info. If no info exists at all, omit parking from your analysis entirely.
- Use room dimensions from competing listings and sold properties to price feature gaps.
- Every claim must be traceable to a specific field in the data."""


def build_market_agent_prompt(prop_summary: str, medians: str, competing: str, sales: str, suburb: str) -> str:
    return f"""You are the MARKET POSITION ANALYST for Fields Estate.

{SHARED_MISSION}

YOUR SELLING PRINCIPLES FOCUS:
- Principle #6: Scarcity Must Be Real to Be Effective — only cite scarcity backed by data (exact counts, verified)
- Principle #1: Selling Is a Transfer of Confidence — confidence comes from specificity and evidence, not enthusiasm

YOUR DOMAIN: Market position — days on market, supply, suburb trends, competitive landscape, buyer leverage.

PROPERTY DATA (full JSON document — CRITICAL: "visible": false and null scores mean our analysis system did not capture that room, NOT that the seller deliberately excluded it. Do NOT draw conclusions from missing data. Only describe what the data actually shows):
{prop_summary}

SUBURB MEDIAN HOUSE PRICES ({suburb}, quarterly):
{medians}

COMPETING LISTINGS IN {suburb.upper()}:
{competing}

RECENT SALES IN {suburb.upper()}:
{sales}

---

BUILD THE MARKET NARRATIVE:

1. DAYS ON MARKET — CONTEXT, NOT JUDGMENT:
   - State the DOM factually and explain what it means for this property type and price bracket
   - 0-14 days: untested. 15-45 days: normal for $2M+ bracket. 45-90: the price has been tested. 90+: extended.
   - NEVER say "the seller's leverage is gone" or coach negotiation tactics. State the data, let the buyer decide.

2. SUPPLY & SCARCITY (Principle #6 — real scarcity only):
   - Exact number of competing listings. Exact number at similar price point.
   - If this property has a rare spec combination (only 1 of 3 with 5+ beds), state it with data.
   - NEVER manufacture urgency. If there's no genuine scarcity, don't pretend there is.

3. SUBURB TREND — SPECIFIC NUMBERS IN PLAIN LANGUAGE:
   - Use "typical price" not "median" — say "The typical Robina house sold for $1,379,000 last quarter"
   - Year-on-year change with the actual percentage
   - If sample size is small (< 25 sales), flag it: "that number is based on only N sales, so take it with a grain of salt"
   - NEVER use "absorption rate", "percentile", "coefficient of variation" or any statistical jargon

4. CONFIDENCE THROUGH SPECIFICITY (Principle #1):
   - Every market claim must have a number attached. "The market is strong" → banned. "Median rose 12% YoY on 34 sales" → good.
   - How many listings show a price guide vs hidden pricing? Exact counts.

IMPORTANT: For supply/scarcity data, count sales in the LAST 12 MONTHS only. Use 6 months if it builds stronger legitimate scarcity. NEVER use timeframes longer than 12 months.

WRITE your briefing as 200-300 words of plain text. Start with:
**MARKET POSITION:** [Where this property sits in the current market — 2 sentences]
**SCARCITY EVIDENCE:** [EXACT count: "X properties with this spec currently listed. Y sold in the last 12 months." If no genuine scarcity exists, say so.]
**CONFIDENCE SIGNALS:** [The 2-3 most specific market data points the buyer needs]

Then give the full market briefing. TAG each major point with the selling principle it demonstrates:
**PRINCIPLE #1 (Transfer of Confidence):** [what specific data point builds buyer confidence]
**PRINCIPLE #6 (Scarcity Must Be Real):** [your exact scarcity count — or "no genuine scarcity"]
**PRINCIPLE #11 (Price Is Discovered):** [how competing demand and available substitutes shape this property's likely price discovery]"""


def strip_flood_from_summary(prop_summary: str) -> str:
    """Remove all flood-related lines from prop_summary — used for Sabri agent which must never see flood data."""
    flood_keywords = {"flood", "FLOOD", "ICA ", "ica_", "DFL", "freeboard", "inundation", "Designated Flood Level", "FloodWise"}
    lines = prop_summary.split("\n")
    return "\n".join(line for line in lines if not any(kw in line for kw in flood_keywords))


def build_sabri_agent_prompt(editor_body: Dict, prop_summary_sanitized: str, address: str, suburb: str) -> str:
    """Build prompt for the Sabri Suby headline specialist agent."""
    # Extract the editorial prompt headline formulas (Parts 2 and 3)
    headline_formulas = ""
    if EDITORIAL_GUIDE:
        sections = []
        keep = False
        for line in EDITORIAL_GUIDE.split("\n"):
            if line.startswith("## PART 2:") or line.startswith("## PART 3:"):
                keep = True
            elif line.startswith("## PART ") and "PART 2:" not in line and "PART 3:" not in line:
                keep = False
            if keep:
                sections.append(line)
        headline_formulas = "\n".join(sections)

    insights_text = json.dumps(editor_body.get("insights", []), indent=2, default=str)
    verdict = editor_body.get("verdict", "")

    return f"""You are the HEADLINE AND H2 WRITER for Fields Estate. A team of analysts has written a property editorial for {address}. Your job is to write the headline, sub-headline, H2s, and SEO metadata.

Your headline must pass TWO tests simultaneously:

TEST 1 — THE SELLER TEST: A homeowner considering selling their property reads this headline. Would they think "I want Fields to sell MY home"? If the headline runs the property down, highlights flaws, or makes the property look bad — it FAILS this test. A great selling agent positions a property with confidence and intelligence. The headline must demonstrate that Fields would do the same for the reader's home.

TEST 2 — THE CLICK TEST: A buyer scrolling Google results sees this headline alongside Domain, REA, and every other portal. Would they stop and click? The headline must offer something the other results don't — not by being negative, but by being SPECIFIC, HONEST, and INFORMATIVE in a way that builds trust.

The headline that passes both tests simultaneously is the one that makes the buyer think "this agent knows what they're talking about" AND makes the seller think "this is how I want my property presented."

--- CORE PRINCIPLES OF SELLING (your operating framework) ---
{SELLING_PRINCIPLES if SELLING_PRINCIPLES else "(Selling principles not loaded)"}

--- HOW SELLING PRINCIPLES APPLY TO HEADLINES ---

Principle #1 (Transfer of Confidence): The headline demonstrates that Fields has done the research. Specificity IS the hook. "Fully renovated four-bed with pool, 1.5 km from Nobby Beach — here's what the comparables say." The confidence comes from the data, not from negativity.

Principle #2 (Outcomes Not Products): The headline speaks to the life the buyer would live, not the spec sheet. "A home where the renovation is done and the park is your backyard."

Principle #3 (Trust Through Transparency): The headline acknowledges trade-offs honestly WITHOUT running the property down. "Compact floor plan, premium finish — the value equation explained." That's transparent without being negative.

Principle #7 (Price Is a Story): The headline frames the price as a narrative the buyer can understand. "What $2,345,000 buys in Burleigh Waters — and what it doesn't."

CRITICAL — WHAT NEVER TO DO:
- NEVER write a headline that makes the property look bad. "Why hasn't it sold?" or "What's wrong?" or "One of these stalls it" — these drive sellers away from Fields.
- NEVER lead with flaws, missing features, or negative framing. The body content addresses trade-offs honestly. The headline invites the reader in with intelligence, not alarm.
- NEVER use chronological price lists ("$X in year, now $Y")
- NEVER reference flood, flood overlay, or flood risk
- NEVER quote single valuation figures or $/sqm rates
- NEVER use Fields-internal language or industry jargon. Your audience is a member of the general public scrolling Google results who has NEVER heard of Fields Estate and knows nothing about our processes. Terms like "automated valuation ceiling", "comparable range", "reconciled valuation", "adjustment model", "confidence level", "SHAP adjustments" are meaningless to them. Use plain language a buyer would understand: "asking price", "what similar homes sold for", "what the data shows".
- NEVER reference Fields-specific tools, models, or methodology in the headline/sub-headline/verdict. The BODY can explain methodology. The headline must speak to a cold audience.

THE HEADLINE MUST CREATE A TENSION THE READER NEEDS TO RESOLVE BY CLICKING.

Every great property headline contains a CONTRADICTION, QUESTION, or PRICE TENSION. The reader sees it and thinks "wait, how is that possible?" or "I need to know more." Generic descriptions of the property ("Renovated 4-bed with pool") are what Domain already shows — there's zero reason to click Fields instead.

HEADLINE FORMULA — PICK THE ONE THAT FITS:

1. PRICE TENSION: Surface the gap between what you'd expect and what it costs.
   "Comparable sales say low $1M. The guide might say $1.4M. Here's what explains the gap."
   "Bought for $770K. Rebuilt from scratch. Now asking $2.975M — here's every dollar in between."

2. CURIOSITY CONTRADICTION: Two facts that seem like they shouldn't coexist.
   "7/10 kitchen, park frontage, cul-de-sac — and still one of Robina's most affordable houses. Why?"
   "9/10 finish, pool, 1 km to the beach — and it's been on the market for 47 days. Here's the data."

3. BUYER'S REAL QUESTION: Ask what the buyer is actually thinking.
   "What does 'Contact Agent' actually mean when the comps say $1M?"
   "Is this the cheapest way into Burleigh Waters — or is something missing?"

4. TRADE-OFF HOOK: Name what you get AND what you give up. Let the reader decide.
   "Park behind the fence, renovated kitchen — but 142 sqm. What are you giving up for the price?"
   "The biggest patio in the suburb. The smallest floor plan. We priced the trade-off."

NEVER WRITE THESE (they are invisible in Google results):
- "[Features] — here's what the data says" (filler ending)
- "[Features] — we ran the comparables" (who cares?)
- "[Features] — must read insights you need to know" (empty)
- Any headline that is just a list of specs with a generic hook appended

QUALITY CHECK: Read your headline out loud. If it sounds like it could be a Domain listing description, throw it out. A Fields headline makes the reader STOP SCROLLING because something doesn't add up and they need to find out why.

You are NOT allowed to change the editorial body. You write ONLY:
1. headline (max 80 chars)
2. sub_headline (max 150 chars)
3. meta_title (max 60 chars)
4. meta_description (max 155 chars)
5. suggested_h2s — one suggested H2 lead line per insight

--- THE EDITORIAL BODY (your headline must hook readers INTO this content) ---

=== BEST LINES FROM THE EDITORIAL (use these as raw material for meta_title and meta_description) ===
These are the strongest lines the editor produced. Your meta_title and meta_description should be EQUAL TO OR BETTER than the best of these. If you can't beat them, pick the most compelling one and compress it to fit.

SECTION H2s:
{chr(10).join(f'  {["The Property", "Condition & Value", "Price Analysis", "Market Position"][i] if i < 4 else "Section"}: "{ins.get("h2", ins.get("lead", ""))}"' for i, ins in enumerate(editor_body.get("insights", [])))}

LIFESTYLE HOOKS:
{chr(10).join(f'  {["The Property", "Condition & Value", "Price Analysis", "Market Position"][i] if i < 4 else "Section"}: "{ins.get("lifestyle_hook", "(none)")}"' for i, ins in enumerate(editor_body.get("insights", [])) if ins.get("lifestyle_hook"))}

VERDICT: "{verdict}"

=== END BEST LINES ===

For meta_title: Pick the single most click-worthy tension from the lines above and compress it to ≤60 chars. Or write something better. The bar is the best H2 above — not a generic summary.

NOTE: You do NOT need to write meta_description — it is automatically set to your sub_headline by the system. Focus your effort on headline, sub_headline, and meta_title.

FULL INSIGHTS (for context):
{insights_text}

--- PROPERTY DATA (context only) ---
{prop_summary_sanitized[:3000]}

---

TECHNICAL RULES:
- The headline must be SPECIFIC to this property — if you could swap the address and it still works, rewrite it

SUB-HEADLINE RULES:
The sub-headline is the second line the buyer reads. If the headline creates tension, the sub-headline ESCALATES it — it does NOT resolve it (that's what the article is for).

BAD sub-headlines (flat summaries):
- "3-bed on 460 sqm backing onto Fern Tree Park, partially renovated."
- "A cosmetically updated four-bed on a quiet crescent. Listed since 20 March 2026."

GOOD sub-headlines (escalate tension):
- "The comps say low $1M. The renovated kitchen says more. We broke down every adjustment."
- "Every comparable that sold nearby was bigger, had more bedrooms, and cost more. So what's this one actually worth?"

=== GOOGLE SEARCH RESULT INSTRUCTIONS (MOST IMPORTANT PART OF YOUR JOB) ===

The meta_title and meta_description are what appear in Google search results. This is the ONLY chance to get a click. Here's the competitive reality:

When someone searches "25 Dotterel Drive Burleigh Waters" they see:
  1. Domain.com.au — "25 Dotterel Drive, Burleigh Waters QLD 4220 | Property Details"
  2. realestate.com.au — "25 Dotterel Drive, Burleigh Waters, QLD 4220 | realestate.com.au"
  3. US — "25 Dotterel Dr — [YOUR META TITLE] | Fields Estate"

The buyer is NOT looking for us. They want Domain or REA. Our meta title must DISRUPT their scroll — make them think "wait, what's that?" and click us INSTEAD of the trusted brand.

META TITLE RULES (max 60 chars):
- Must contain the TENSION from the headline, compressed
- Must feel like it answers a question Domain CAN'T answer
- NEVER just be the address + "| Fields Estate" — that's invisible
- NEVER use "Review" or "Property Details" — that's what Domain says

BAD meta titles:
- "25 Dotterel Dr Burleigh Waters Review | Fields" (invisible, generic)
- "25 Dotterel Dr, Burleigh Waters | Fields Estate" (copy of Domain)
- "Property Analysis — 25 Dotterel Drive | Fields" (nobody cares)

GOOD meta titles (disrupt the scroll):
- "25 Dotterel Dr — $255K Below Top Comp. Why? | Fields" (price tension)
- "25 Dotterel Dr — We Priced Every Trade-Off | Fields" (curiosity)
- "Is 25 Dotterel Dr Worth $2.345M? The Data Says... | Fields" (question)
- "25 Dotterel Dr — 9/10 Finish But 3 Catches | Fields" (contradiction)

META DESCRIPTION RULES (max 155 chars):
- Opens with the most surprising or tension-creating fact
- Includes a specific number ($, sqm, score) in the first 60 chars
- Ends with an implicit reason to click: "We broke it down" / "Here's every adjustment"
- MUST feel like it promises information Domain doesn't have

BAD meta descriptions:
- "View property details, photos, and floor plans for 25 Dotterel Drive." (Domain says this)
- "Listed since 26 March 2026. Renovated 3-bed backing park." (flat summary)

GOOD meta descriptions:
- "9/10 finish, pool, 80m to park — but weatherboard, 173 sqm, no garage. We priced each trade-off. Here's what it's actually worth."
- "Comps say $960K–$1.2M. The asking price says $1.4M. We show exactly where the gap comes from — and whether the renovation justifies it."

The meta_description is your 155-character sales pitch. If it sounds like a listing description, the buyer clicks Domain instead. If it sounds like insider knowledge they can't get anywhere else, they click Fields.

OUTPUT as JSON only — no markdown, no code fences:
{{
  "headline": "max 80 chars — tension/curiosity hook that makes the buyer need to click",
  "sub_headline": "max 150 chars — escalates the headline tension, does NOT resolve it",
  "meta_title": "max 60 chars — disrupts Google scroll, contains price tension or contradiction",
  "meta_description": "max 155 chars — promises insider knowledge Domain can't offer, opens with surprising number",
  "suggested_h2s": ["H2 for insight 1", "H2 for insight 2", "H2 for insight 3"]
}}"""


def build_editor_prompt(price_brief: str, property_brief: str, market_brief: str, address: str, suburb: str, has_flood_overlay: bool = False) -> str:
    # Include the editorial guide (truncated to key sections to save tokens)
    guide_excerpt = ""
    if EDITORIAL_GUIDE:
        # Extract Parts 2, 3, 6, 7, 8 (the most important for the editor)
        sections_to_keep = []
        current_section = ""
        keep = False
        for line in EDITORIAL_GUIDE.split("\n"):
            if line.startswith("## PART "):
                if any(p in line for p in ["PART 2:", "PART 3:", "PART 5.5:", "PART 6:", "PART 7:", "PART 8:"]):
                    keep = True
                else:
                    keep = False
            if keep:
                sections_to_keep.append(line)
        guide_excerpt = "\n".join(sections_to_keep)

    return f"""You are the EDITORIAL DIRECTOR for Fields Estate. Three specialist analysts have each written a briefing on {address}. Your job is to synthesise their work into a compelling editorial body — insights, verdict, next steps, CTAs, and FAQs.

NOTE: You do NOT write the headline, sub_headline, meta_title, or meta_description. A separate Sabri Suby specialist handles those. Focus on the BODY content only.

CRITICAL RULE — MISSING DATA (READ CAREFULLY — THIS IS THE #1 RECURRING ERROR):
If a room (e.g. bathrooms, bedrooms) has "visible": false and null scores in the property_valuation_data, it means OUR PHOTO ANALYSIS SYSTEM DID NOT SEE THAT ROOM. It was not photographed or not identifiable in photos. This tells you NOTHING about its actual condition.

SPECIFICALLY: "bathrooms_renovated": false in the renovation section DOES NOT MEAN the bathrooms are unrenovated. It means our system did not detect bathroom renovation evidence in photos — BECAUSE IT NEVER SAW THE BATHROOMS. The boolean is inferred from absence, not observation.

YOU MUST NOT:
- Call rooms "unrenovated", "untouched", "dated", "original", or "not upgraded" when visible: false
- Use "bathrooms_renovated: false" as evidence of condition
- Say "unrenovated bathrooms" in the headline, verdict, insights, or trade-offs
- Frame missing data as a negative ("the bathrooms haven't been done")

YOU MUST:
- Say "condition data not available" or "not photographed — no condition score on record"
- Recommend in-person inspection for rooms without data
- Frame as a known unknown: "The bathrooms were not photographed and have no condition scores — budget accordingly or inspect carefully"

If the agent briefings below claim bathrooms are "unrenovated" based on this data, OVERRIDE THEM. The briefings are wrong on this point.

PRICE & VALUE ANALYST BRIEFING:
{price_brief}

PROPERTY & TRADE-OFFS ANALYST BRIEFING:
{property_brief}

MARKET POSITION ANALYST BRIEFING:
{market_brief}

---

YOUR FRAMEWORK: The Core Principles of Selling guide every editorial choice:
{SELLING_PRINCIPLES[:4000] if SELLING_PRINCIPLES else "(Selling principles not loaded)"}

{f"EDITORIAL STYLE GUIDE (study the examples carefully):{chr(10)}{guide_excerpt[:6000]}" if guide_excerpt else ""}

{f"FLOOD OVERLAY EXPERT CONTEXT (this property has a flood overlay — read this carefully):{chr(10)}{FLOOD_CONTEXT[:4000]}" if has_flood_overlay and FLOOD_CONTEXT else ""}

THE PRODUCT: You are writing the editorial BODY of a property page. This is NOT a data report. It reads like a smart friend who spent 3 hours researching this property and is giving the buyer the 5-minute version over coffee. Conversational, data-rich, and actionable.

CRITICAL — NO JARGON: Your audience is a member of the general public scrolling Google on their phone. They have never heard of Fields Estate. They don't know what a percentile is. They don't care about your methodology.

SPEAK PLAIN:
- "30th percentile" → "smaller than most homes in the suburb"
- "81st percentile" → "bigger than roughly 4 in 5 homes for sale here"
- "adjustment model" → "what similar homes sold for"
- "coefficient of variation" → "the range is wide because the data is thin"
- "comparable-adjusted range" → "based on recent sales of similar homes"
- "median" → "typical price" (except in SEO FAQ answers)
- "absorption rate" → "how fast homes are selling"
- "gross yield" → "rental return"

If the agent briefings below use jargon, TRANSLATE IT into plain language. The reader should feel like a knowledgeable friend is explaining the property — not like they're reading a bank report.

The verdict especially must be written for someone who has never visited fieldsestate.com.au before — plain, direct, memorable.

A separate Sabri Suby specialist will write the headline, sub-headline, meta title, and meta description AFTER you finish. You do NOT produce those fields.

QUALITY PRINCIPLES — These define what good output looks like. Follow every one:

1. ONLY SPEAK TO DATA YOU HAVE. If a room has null scores or "visible": false, omit it entirely. Do not speculate about condition, do not say "not photographed", do not say "unrenovated" unless the data explicitly confirms it. Silence is better than a guess.

2. EVERY TRADE-OFF IS A VALUE EQUATION. Never frame a weakness as a flaw. Frame it as the reason the price is what it is. "The weatherboard cladding is why this isn't $3,500,000" — not "the cladding is a negative." A seller reading this should think "Fields would present my home intelligently."

3. LEAD EVERY INSIGHT WITH A SPECIFIC NUMBER. The first thing the reader sees in each insight lead must be a concrete data point — a distance, a price, a score, a count. Not a general statement. "244 sqm, pool, 1.11 km to the beach" — not "A well-positioned family home."

4. THE VERDICT CONNECTS WEAKNESS TO PRICE ADVANTAGE. The verdict must be one sentence that a buyer would repeat to their partner. The formula: [what you get] + [what keeps the price accessible]. "The land, the floor area, and the location do the heavy lifting — the cosmetic gap is the reason you're not paying $3,500,000."

5. MAKE THE LIFESTYLE TANGIBLE IN INSIGHT 1. Use walking times, POI distances, and specific venue names from the nearby_pois data. "Saturday morning starts with coffee from Flockd — 167 metres from the front door" is 10x better than "close to local amenities."

6. THE COMPARABLE DETAIL MUST BE READABLE. When presenting comparable sale adjustments, list each adjustment clearly with the dollar amount. Do not cram 15 adjustments into a single sentence. Each comparable should read as: address, sale price, key adjustments up, key adjustments down, adjusted value.

7. DO NOT REPEAT THE SAME DATA POINT MORE THAN TWICE. If you mention "678 sqm" in insight 1, do not repeat it in insight 2, 3, and 4. Find new angles for each insight.

CRITICAL — THE ORDER OF INFORMATION:

Principle #11 says: "Emotional commitment precedes financial commitment. Buyers first decide 'I want this.' Then justify 'This is worth it.'"

This means: make the reader WANT the property first, THEN give them the data to justify the decision. Do NOT lead with the analyst's perspective (percentiles, adjustment rates, growth figures). Lead with the buyer's experience.

Think about how a great agent walks a buyer through an inspection. They don't start by saying "the floor area is 51st percentile." They start at the back door: "Look at this — park behind the fence, pool, covered entertaining for 12 people, Burleigh Beach is a 19-minute walk. This is the life you'd live here." THEN when the buyer is emotionally engaged, they address the trade-offs with evidence.

STRUCTURE — INSIGHTS MUST FOLLOW THIS ORDER:

INSIGHT 1 — WHO + OUTCOME (Principles #11, #2, #5):
Name the ideal buyer. Paint the life they'd live. Make them self-select: "that's me."
BUT — even in this section, connect lifestyle to VALUE. Why is this lifestyle available at this price?

THE LIFESTYLE HOOK COMES FIRST. Every insight has a `lifestyle_hook` field that sits ABOVE the key points. This is the emotional opener — 1-3 sentences that make the reader WANT the property before they see any data. It paints a specific moment: a Saturday morning, the school run, an evening on the deck. Then it connects that life to the price.

Example lifestyle_hook for Insight 1: "Saturday morning here looks like this: coffee run on foot, swim in the pool, kids at the park across the road, beach by mid-morning. That's the outcome you're buying — and the reason this home is priced above the suburb's $1,800,000 typical price."

Example lifestyle_hook for Insight 2 (Condition): "You walk in and the hard work is done. Stone benchtops, new flooring, renovated bathrooms. The previous owner spent $40,000–$65,000 on the rooms that matter most — and that spend is already in the price, not on your to-do list."

Example lifestyle_hook for Insight 3 (Price): "Two homes within a kilometre sold recently. One for $3.5M, one for $1.6M. After adjusting for size, condition, and features, they point to a range of $2.16M–$3.37M for this property. The asking price picks the lower half."

Example lifestyle_hook for Insight 4 (Trade-offs): "Every dollar you're NOT paying has a name. Weatherboard instead of render: $60,000. No enclosed garage: $45,000. Average floor area instead of generous: $67,000. Add them up and you see exactly why this isn't a $2.6M home."

The lifestyle_hook is NOT a feature description. It's the FEELING of living here connected to the FINANCIAL reality. If it reads like an agent listing, rewrite it.

Example H2: "Park behind the fence, renovated kitchen, cul-de-sac — and possibly one of Robina's most affordable houses. Here's what the trade-off looks like."
Example key_points: Anchor every feature to what it means for the price or the decision. "The park behind the fence means no rear neighbour — but it also means the block is only 460 sqm, which is why you're not paying $1.5M."

INSIGHT 2 — CONDITION vs PRICE (Principles #1, #5 — what the renovation saves you):
Frame the renovation as money the buyer DOESN'T have to spend. Price the gap between what's done and what's not.
Example H2: "7/10 kitchen, 8/10 bathroom — the renovation is partial, and the $80,000 gap to 'fully done' is the reason this isn't priced at $1.3M."
Example key_points: NEVER just list features. For every feature, say what it would COST if it wasn't done, or what it's WORTH compared to alternatives. "The kitchen renovation runs $25,000–$40,000 — that's money you're not spending. But the flooring hasn't been touched, and that's another $8,000–$15,000 if it bothers you."

INSIGHT 3 — THE PRICE STORY (Principles #7, #11 — comparable evidence):
Now give the financial framework. What did similar homes sell for? Where does this one sit?
Example H2: "Every comp that sold was bigger, had more bedrooms, and cost more. After adjustments, they point to $960K–$1.2M for this spec."
Example key_points: Name the comps, cite the sold prices, explain the key adjustments in plain language. "22 Camberwell Circuit sold for $1,345,000 — but that was a 4-bed on 800 sqm with 213 sqm of floor area. After adjusting down for the extra bedroom, bigger lot, and more floor space, that sale points to about $1M for a home like this one."

INSIGHT 4 — THE TRADE-OFFS THAT MAKE THE PRICE (Principles #3, #4):
This is the section that explains WHY the property is priced where it is. Every "weakness" is framed as the reason the buyer gets the price they're getting.
Example H2: "142 sqm, 3 bedrooms, no pool — that's roughly $200,000 in adjustments that keep this under $1.2M. Here's the maths."
Example key_points: Price every trade-off. "No pool — homes with a pool in Robina sell for about $50,000–$80,000 more. Three bedrooms instead of four — that's another $60,000–$90,000 based on comparable sales. Smaller than average floor plan — at $3,000 per sqm, the 30 sqm gap to the suburb average costs roughly $90,000. Add it up and you see exactly why this home is priced where it is — and what you'd need to spend to close each gap."

FLOOD — always last insight or dedicated section. Never before Insight 4.

VERDICT — One or two sentences. Short enough that someone repeats it to their partner at dinner or to their friends at a BBQ. If it's not memorable and quotable, it's too long.
Example: "The renovation is the value case. The floor area is the question. The park and the beach are the things no renovation can replicate."

NEXT STEPS — 3-4 actionable steps. These should feel like the NATURAL next step for a buyer who's done the research, NOT a legal checklist.
   - Reference the comp range and frame the offer context
   - Suggest what to confirm with the agent (renovation history, buyer feedback)
   - Recommend inspection focus areas specific to this property
   - Point to the Valuation Guide for the full comparable breakdown

6. CTA: VALUATION — A hook that makes the buyer want to see our step-by-step valuation walkthrough. Reference the specific comp count and valuation figure. Don't just say "see the valuation" — make them NEED to see it.

7. CTA: MARKET (BUY) — A hook using the suburb's recent median movement that makes the buyer want to read the market briefing. Reference specific quarterly figures.

8. CTA: MARKET (SELL) — For buyers who are selling to buy. Reference supply data (active listings count) and buyer volume.

OUTPUT: JSON — no markdown, no code fences.

NOTE: Do NOT include headline, sub_headline, meta_title, or meta_description — those are handled by the Sabri Suby specialist.

CRITICAL — THE BACKBONE OF EVERY INSIGHT IS TRADE-OFFS TO PRICE:

This is the most important instruction in the entire prompt. Every section of the editorial exists to help the buyer understand ONE thing: what am I getting for the price, and what am I giving up?

A FEATURE DUMP looks like: "The covered timber deck measures 7.5 × 2.8 metres with translucent roofing, pendant lighting, and direct access from the dining area via timber-framed glass doors."
Nobody cares. That's an agent listing. The buyer can see the photos.

A TRADE-OFF-TO-PRICE INSIGHT looks like: "The deck is 21 sqm — good for a family dinner, tight for a party of 20. Most homes at this price in Robina have a pool and a bigger outdoor area. This one trades pool and patio size for a renovated interior and park frontage."

See the difference? The second version tells the buyer what the feature MEANS in the context of what they're paying and what the alternatives look like.

EVERY KEY POINT MUST ANSWER ONE OF THESE:
- "What does this feature save you compared to alternatives?" (value)
- "What are you giving up by buying this instead of X?" (trade-off)
- "What would it cost to add this / fix this?" (upgrade cost)
- "How does this compare to what else is available at this price?" (positioning)

If a key point is just a description of a feature with dimensions, it fails. Rewrite it as a trade-off.

CRITICAL — STRUCTURED INSIGHT FORMAT (v2):
Each insight must be a structured object with separate arrays for key_points and what_this_means.
Do NOT write a single "detail" paragraph — the frontend renders key_points as individual bullet items
and what_this_means as a separate callout. Keep each key_point to 1-2 sentences max.
Use **bold** markers on key terms within key_points (e.g. "**Stone benchtops** and modern cabinetry").

For the Price Analysis insight (insight 3), include a "comparables" array with structured comparable data.
For other insights, set comparables to null.

KEY POINT WRITING RULES:
- BAD: "The kitchen features stone benchtops, shaker cabinetry, and a breakfast bar." (feature dump)
- GOOD: "The kitchen scores 7/10 — stone-look benchtops and shaker cabinetry. That's above average for the suburb, and it's already done. A kitchen renovation runs $25,000–$40,000, so this is money you're NOT spending."
- BAD: "The living room measures 6.2 × 4.3 metres with raked ceilings and exposed beams." (so what?)
- GOOD: "The living room is the biggest single space in the house at 27 sqm — raked ceilings make it feel even larger. For a 142 sqm home, the builder put the space where it counts."
- BAD: "Split-system air conditioning is installed across multiple rooms." (listing copy)
- GOOD: "Split-system AC, not ducted. A ducted retrofit would run $15,000–$25,000. At this price point, most competing homes have it. Factor that in or live with split systems."

{{
  "insights": [
    {{
      "h2": "A trade-off or tension the buyer needs resolved — with a specific number",
      "lifestyle_hook": "1-3 sentences that make the reader WANT this property. Paint the life: Saturday morning, the commute, the evening routine. This sits ABOVE the key points and is the first thing the reader sees after the H2. It must connect the lifestyle to the PRICE — why this life costs what it costs.",
      "key_points": [
        "One fact per bullet — max 2 sentences",
        "Another fact with a **bolded key term**",
        "A third fact with specific numbers: 592m, $2,495,000, 8/10"
      ],
      "key_points_label": "Key points",
      "what_this_means": [
        "What this means for the buyer — written in second person",
        "A conditional framing if relevant: If you need X, this isn't it"
      ],
      "comparables": null
    }},
    {{
      "h2": "...",
      "key_points": ["..."],
      "key_points_label": "Key points",
      "what_this_means": ["..."],
      "comparables": null
    }},
    {{
      "h2": "Price analysis lead with comparable range and asking price position",
      "key_points": [
        "Asking price positioning within the range",
        "What the discount reflects (real differences, not flaws)"
      ],
      "key_points_label": "Comparable sales",
      "what_this_means": [
        "What this price position means for the buyer"
      ],
      "comparables": [
        {{
          "address": "4 Curlew Crescent",
          "distance": "560m away",
          "sold_price": 3500000,
          "adjusted_price": 3413000,
          "summary": "Fully renovated benchmark — same bedrooms, ducted, rendered, 9/10 condition",
          "delta_label": "$918,000 below this benchmark"
        }}
      ]
    }},
    {{
      "h2": "...",
      "key_points": ["..."],
      "key_points_label": "Key points",
      "what_this_means": ["..."],
      "comparables": null
    }}
  ],
  "verdict": "The bottom line — ≤25 words, short enough to repeat at dinner or a BBQ.",
  "quick_take": {{
    "strengths": [
      "First sentence of insight 1 h2 — the lifestyle hook with a specific number",
      "First sentence of insight 2 h2 — the condition proof with scores"
    ],
    "trade_off": "First sentence of insight 4 h2 — the key trade-offs that define the price"
  }},
  "best_for": [
    "2-4 word buyer persona specific to THIS property",
    "Another buyer persona",
    "A third buyer persona"
  ],
  "not_ideal_for": [
    "2-4 word buyer persona who should NOT buy this",
    "Another mismatch persona",
    "A third mismatch persona"
  ],
  "next_steps": [
    "Actionable step 1 with specific numbers (comp range reference)",
    "Actionable step 2 (what to confirm with agent)",
    "Actionable step 3 (inspection focus areas)",
    "Actionable step 4 (point to Valuation Guide)"
  ],
  "cta_valuation": {{
    "hook": "1-2 sentences making the buyer NEED to see the valuation walkthrough. Reference comp count.",
    "label": "Walk through the valuation step by step",
    "tab": "valuation"
  }},
  "cta_market_buy": {{
    "hook": "1-2 sentences using suburb median movement to hook the buyer into the market briefing.",
    "label": "Read the [SUBURB] buyer's market briefing",
    "url": "/market-metrics/[SUBURB_SLUG]#buy"
  }},
  "cta_market_sell": {{
    "hook": "1-2 sentences about supply and timing for sell-to-buy buyers.",
    "label": "Read the [SUBURB] seller's market briefing",
    "url": "/market-metrics/[SUBURB_SLUG]#sell"
  }},
  "flood_section": {{
    "title": "Does [suburb] flood? What the data says about [address]",
    "body": "FOR OVERLAY PROPERTIES: Council designation, ground vs DFL, depth, zero events, value equation. FOR NON-OVERLAY: State no overlay clearly. ALWAYS note suburb-wide zero insurance events.",
    "source": "Gold Coast City Council ArcGIS flood mapping"
  }},
  "faqs": [
    {{
      "question": "What is [full address] worth in [year]?",
      "answer": "Based on X verified comparables... range $Y to $Z. Point to Valuation Guide."
    }},
    {{
      "question": "Is [full address] overpriced or fairly priced?",
      "answer": "Position in comparable range, what the gap reflects."
    }},
    {{
      "question": "What comparable sales support the asking price?",
      "answer": "Name top 2-3 comps with sold + adjusted prices."
    }},
    {{
      "question": "How does this property compare to others in [suburb]?",
      "answer": "Percentile data, condition scores vs market."
    }},
    {{
      "question": "Is [suburb] a good suburb to buy in right now?",
      "answer": "Median trend, supply/demand context."
    }},
    {{
      "question": "What is happening in the [suburb] property market in [year]?",
      "answer": "Median, sample size, active supply count."
    }},
    {{
      "question": "How was this property valued?",
      "answer": "Methodology summary — comparable sales adjusted for differences."
    }},
    {{
      "question": "How much is my house worth in [suburb]?",
      "answer": "CTA to /analyse-your-home with suburb context."
    }},
    {{
      "question": "Is Fields Estate the listing agent for this property?",
      "answer": "No — we provide independent analysis. Contact [agent] at [agency]."
    }}
  ]
}}

QUICK_TAKE RULES:
- strengths: exactly 2 items, each ≤1 sentence, each opens with a specific number or measurement
- trade_off: exactly 1 string, ≤1 sentence, names 2-3 things a buyer trades off at this price
- These are the 3-SECOND SCAN LAYER — a buyer who reads nothing else gets the picture

BEST_FOR / NOT_IDEAL_FOR RULES:
- Exactly 3 items each
- Each item is 2-4 words (a buyer persona label, NOT a sentence)
- Must be specific to THIS property — "Owner-occupiers" is fine, "People who like houses" is not
- Examples: "Owner-occupiers", "Families upsizing locally", "Long-term holders", "Bargain hunters", "Turnkey-only buyers", "Short-term investors", "Downsizers", "First-home buyers"

KEY_POINTS FORMATTING:
- Each bullet is one self-contained fact, max 2 sentences
- Use **bold** on the key term: "**Stone benchtops** and modern cabinetry in the kitchen"
- Numbers formatted as $1,250,000 (not $1.25m), measurements use × (not x)
- Maximum 7 key_points per insight
- For comparables insight: include comparables array AND additional key_points for non-comp observations

SUBURB SLUG MAPPING: Robina = "Robina", Varsity Lakes = "Varsity_Lakes", Burleigh Waters = "Burleigh_Waters"

REQUIREMENTS:
- 3-4 insights. NO ** bold markers — frontend handles formatting.
- Insight leads should be CONVERSATIONAL ("The renovation is real — and it's recent") not CLINICAL ("9/10 condition across all rooms")
- Each insight detail MUST answer "what does this mean for the buyer?"
- If capital gain data exists, weave it into an insight naturally — don't make it a standalone stat
- Reference comparable sales by NAME with sold price and adjustment: "22 Manakin Ave sold for $1,657,000 with a 13.9 sqm master — adjusted for the floor area gap, that's $X for this spec"
- FLOOD POSITIONING: If the property has a flood overlay, it MUST be the LAST insight or a dedicated section after all other insights. NEVER lead with flood. NEVER put flood in insights 1, 2, or 3. Flood belongs at the END only. Frame factually as council records.
- CRITICAL VALUE FRAMEWORK: Every trade-off MUST be framed as a value equation, not a flaw.
  * Use adjustment rates to price the trade-off: "The floor area is median. Each additional sqm costs $3,000. Here's what more floor area would cost you in named sold comparables."
  * NEVER take the buyer's side against the seller. NEVER coach negotiation tactics. NEVER say "the seller's leverage is gone."
  * Always anchor to LOCATION: where else in Australia can you get this close to one of the world's best beaches at this price?
  * "We show you the data. You make the decision." — this is our editorial position
  * A seller reading this should think "Fields would position my property honestly and intelligently"
- next_steps must include specific numbers (comp range for reference, inspection items specific to the property)

*** MANDATORY INSIGHT ORDER — DO NOT DEVIATE ***
Insight 1 = DESIRE + IDEAL BUYER (lifestyle, location, beach, park, who this is for — make them want it)
Insight 2 = PHYSICAL PROOF (renovation, condition, build quality — back up the desire with evidence)
Insight 3 = PRICE STORY (comparables, valuation range, where the asking price sits — justify the decision)
Insight 4 = TRADE-OFFS (floor area, any weaknesses — priced as value equations, not flaws)
If flood overlay exists: Insight 5 or dedicated flood_section AFTER all other insights.
This order is NON-NEGOTIABLE. Desire first. Data second. Trade-offs last.
- CTA hooks must contain specific suburb data (median figures, listing counts) — not generic prompts
- VERDICT: One or two sentences, short enough that someone repeats it to their partner at dinner or to their friends at a BBQ. If it's not quotable, it's too long.
- DATA CONFIDENCE: Photo analysis data (materials, scores, renovation level) IS evidence — use it confidently. What you cannot claim: the specific renovation YEAR or COST.
- VALUATION: NEVER write "$2,396,327" or any single valuation figure. ALWAYS write "comparable sales adjust to $X–$Y for this property" using the range from the valuation data. Price is discovered by the market, not set by a model.
- IDEAL BUYER: One insight should name who this property is FOR and who it's NOT for. Make it specific: "This is a home for someone who's done renovating. If you need 200+ sqm, the data says look at [specific competing property]."
- OUTCOMES: At least one insight should frame around lifestyle, not specs. What does a Saturday morning look like in this home?

CRITICAL SEO RULE — LISTING DATES vs DAY COUNTS:
- In verdict, next_steps, CTA hooks, and FAQ answers:
  NEVER write "41 days on market" or "4 days without a buyer"
  ALWAYS write "Listed since 10 February 2026" or "First listed 10 February"
- In insight DETAIL text only: day counts are OK as supporting colour
- In FAQ about time on market: ALWAYS anchor to the listing DATE

FAQS — Include 6 property-specific FAQs:
1. "What is [address] worth?" — comp count, valuation range, asking price gap, point to Valuation Guide
2. "Is [address] in a flood zone?" — council overlay data or state no overlay clearly
3. "How long has [address] been on the market?" — use listing DATE, not day count
4. "What is the [suburb] median house price in [year]?" — latest quarterly, sample size, trend
5. "What comparable sales support the valuation?" — name top 3 comps with sold + adjusted prices
6. "Has [address] been renovated?" — condition scores, renovation classification, last purchase price

CRITICAL: The current year is 2026. All listing dates, median quarters, and references should use 2026 (not 2025). Double-check any year you write.

VOICE: Conversational. Like a smart friend who happens to have all the data. No superlatives. Dollar figures like $1,250,000 not "$1.25m". Suburbs capitalised. Every sentence must earn its place."""


# ---------------------------------------------------------------------------
# Claude API call
# ---------------------------------------------------------------------------

def call_gemini(prompt: str, api_key: str, max_tokens: int = 1500, parse_json: bool = False, model: str = "gemini-2.5-flash") -> Any:
    """Call Google Gemini. Returns raw text (parse_json not supported for gathering agents)."""
    import warnings
    warnings.filterwarnings("ignore", category=FutureWarning)
    genai.configure(api_key=api_key)
    gmodel = genai.GenerativeModel(model)
    response = gmodel.generate_content(
        prompt,
        generation_config=genai.types.GenerationConfig(max_output_tokens=max_tokens),
    )
    raw = response.text.strip()
    if parse_json:
        if raw.startswith("```"):
            raw = raw.split("\n", 1)[1] if "\n" in raw else raw[3:]
            if raw.endswith("```"):
                raw = raw[:-3]
            raw = raw.strip()
        return json.loads(raw)
    return raw


def call_openai(prompt: str, api_key: str, max_tokens: int = 1500, parse_json: bool = False, model: str = "gpt-5.4") -> Any:
    """Call OpenAI GPT. Returns raw text by default."""
    client = openai_module.OpenAI(api_key=api_key)
    response = client.chat.completions.create(
        model=model,
        max_completion_tokens=max_tokens,
        messages=[{"role": "user", "content": prompt}],
    )
    raw = response.choices[0].message.content.strip()
    if parse_json:
        if raw.startswith("```"):
            raw = raw.split("\n", 1)[1] if "\n" in raw else raw[3:]
            if raw.endswith("```"):
                raw = raw[:-3]
            raw = raw.strip()
        return json.loads(raw)
    return raw


def call_claude(prompt: str, api_key: str, max_tokens: int = 1500, parse_json: bool = True, model: str = "claude-sonnet-4-6", required_keys: set = None) -> Any:
    """Call Claude. Returns parsed JSON if parse_json=True, else raw text."""
    client = anthropic.Anthropic(api_key=api_key)

    message = client.messages.create(
        model=model,
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
    required = required_keys if required_keys is not None else {"headline", "sub_headline", "insights", "verdict"}
    missing = required - set(result.keys())
    if missing:
        raise ValueError(f"Claude response missing keys: {missing}")
    if "insights" in required and (not isinstance(result.get("insights"), list) or len(result["insights"]) < 3):
        raise ValueError(f"insights must be an array of 3-4 items, got: {type(result.get('insights'))}")
    # Validate v2 insight structure (h2 + key_points) if present
    if "insights" in required and result.get("insights"):
        first = result["insights"][0]
        if "h2" not in first and "lead" not in first:
            raise ValueError("Each insight must have either 'h2' (v2) or 'lead' (v1) field")

    return result


# ---------------------------------------------------------------------------
# Pipeline sub-functions — extracted from run_multi_agent_pipeline()
# ---------------------------------------------------------------------------

def _build_gather_config(
    use_gemini_gather: bool,
    gemini_api_key: Optional[str],
    use_openai_gather: bool,
    openai_api_key: Optional[str],
    use_hybrid_gather: bool,
    api_key: str,
) -> Dict[str, Any]:
    """Build the gather mode configuration: model, label, call functions, token limits."""
    agent_model = PIPELINE_CONFIG["models"]["gather_default"]
    gather_tokens = PIPELINE_CONFIG["token_limits"]["gather"]

    if use_gemini_gather and gemini_api_key:
        gather_model = PIPELINE_CONFIG["models"]["gather_gemini"]
        gather_label = f"Gemini ({gather_model})"
        gather_tokens = PIPELINE_CONFIG["token_limits"]["gather_gemini"]
        def gather_call(prompt, max_tokens=gather_tokens):
            return call_gemini(prompt, gemini_api_key, max_tokens=max_tokens, parse_json=False, model=gather_model)
    elif use_openai_gather and openai_api_key:
        gather_model = PIPELINE_CONFIG["models"]["gather_openai"]
        gather_label = f"OpenAI ({gather_model})"
        def gather_call(prompt, max_tokens=gather_tokens):
            return call_openai(prompt, openai_api_key, max_tokens=max_tokens, parse_json=False, model=gather_model)
    else:
        gather_label = f"Claude ({agent_model})"
        def gather_call(prompt, max_tokens=gather_tokens):
            return call_claude(prompt, api_key, max_tokens=max_tokens, parse_json=False, model=agent_model)

    def hybrid_openai_call(prompt, max_tokens=gather_tokens):
        return call_openai(prompt, openai_api_key, max_tokens=max_tokens, parse_json=False, model=PIPELINE_CONFIG["models"]["gather_openai"])

    return {
        "agent_model": agent_model,
        "gather_label": gather_label,
        "gather_call": gather_call,
        "gather_tokens": gather_tokens,
        "hybrid_openai_call": hybrid_openai_call,
        "use_hybrid_gather": use_hybrid_gather,
    }


def _run_gathering_agents(
    prop_summary: str,
    medians_str: str,
    competing_str: str,
    sales_str: str,
    suburb_display: str,
    address: str,
    api_key: str,
    gather_cfg: Dict[str, Any],
) -> Dict[str, str]:
    """Run the 3 specialist gathering agents (Price, Property, Market).

    Returns {"price": brief, "property": brief, "market": brief}.
    """
    gather_call = gather_cfg["gather_call"]
    gather_tokens = gather_cfg["gather_tokens"]
    gather_label = gather_cfg["gather_label"]
    agent_model = gather_cfg["agent_model"]
    use_hybrid = gather_cfg["use_hybrid_gather"]
    hybrid_openai_call = gather_cfg["hybrid_openai_call"]

    # Agent 1: Price & Value Analyst
    agent1_label = f"OpenAI ({PIPELINE_CONFIG['models']['gather_openai']})" if use_hybrid else gather_label
    print(f"  [Agent 1/4] Price & Value Analyst ({agent1_label})...")
    t0 = time.time()
    if use_hybrid:
        price_brief = hybrid_openai_call(
            build_price_agent_prompt(prop_summary, medians_str, competing_str, sales_str, suburb_display),
            max_tokens=gather_tokens,
        )
    else:
        price_brief = gather_call(
            build_price_agent_prompt(prop_summary, medians_str, competing_str, sales_str, suburb_display),
            max_tokens=gather_tokens,
        )
    print(f"    Done ({time.time()-t0:.1f}s, {len(price_brief)} chars)")

    # Agent 2: Property & Trade-offs Analyst — ALWAYS Claude in hybrid mode (selling principles + lifestyle framing)
    agent2_label = f"Claude ({agent_model})" if use_hybrid else gather_label
    print(f"  [Agent 2/4] Property & Trade-offs Analyst ({agent2_label})...")
    t0 = time.time()
    if use_hybrid:
        property_brief = call_claude(
            build_property_agent_prompt(prop_summary, competing_str, sales_str, suburb_display),
            api_key, max_tokens=PIPELINE_CONFIG["token_limits"]["sabri"], parse_json=False, model=agent_model,
        )
    else:
        property_brief = gather_call(
            build_property_agent_prompt(prop_summary, competing_str, sales_str, suburb_display),
            max_tokens=gather_tokens + 200,
        )
    print(f"    Done ({time.time()-t0:.1f}s, {len(property_brief)} chars)")

    # Agent 3: Market Position Analyst
    agent3_label = f"OpenAI ({PIPELINE_CONFIG['models']['gather_openai']})" if use_hybrid else gather_label
    print(f"  [Agent 3/4] Market Position Analyst ({agent3_label})...")
    t0 = time.time()
    if use_hybrid:
        market_brief = hybrid_openai_call(
            build_market_agent_prompt(prop_summary, medians_str, competing_str, sales_str, suburb_display),
            max_tokens=gather_tokens,
        )
    else:
        market_brief = gather_call(
            build_market_agent_prompt(prop_summary, medians_str, competing_str, sales_str, suburb_display),
            max_tokens=gather_tokens,
        )
    print(f"    Done ({time.time()-t0:.1f}s, {len(market_brief)} chars)")

    return {"price": price_brief, "property": property_brief, "market": market_brief}


def _run_editor(
    agent_briefings: Dict[str, str],
    address: str,
    suburb_display: str,
    prop_summary: str,
    api_key: str,
) -> Dict:
    """Run the editor agent to synthesise body content from agent briefings.

    Returns the editor JSON result (insights, verdict, etc.).
    """
    print(f"  [Editor] Synthesising body ({PIPELINE_CONFIG['models']['editor']})...")
    t0 = time.time()
    result = call_claude(
        build_editor_prompt(
            agent_briefings["price"], agent_briefings["property"], agent_briefings["market"],
            address, suburb_display,
            has_flood_overlay="flood_overlay: True" in prop_summary or "Flood overlay: yes" in prop_summary.lower(),
        ),
        api_key,
        max_tokens=PIPELINE_CONFIG["token_limits"]["editor"],
        parse_json=True,
        model=PIPELINE_CONFIG["models"]["editor"],
        required_keys={"insights", "verdict"},
    )
    print(f"    Done ({time.time()-t0:.1f}s)")
    return result


def _run_sabri(
    result: Dict,
    sanitized_summary: str,
    address: str,
    suburb_display: str,
    api_key: str,
) -> Dict:
    """Run the Sabri Suby headline specialist agent.

    Returns dict with headline, sub_headline, meta_title, meta_description, suggested_h2s.
    """
    sabri_model = PIPELINE_CONFIG["models"]["sabri"]
    print(f"  [Agent 4/4] Sabri Suby Headline Specialist ({sabri_model})...")
    t0 = time.time()
    sabri_result = call_claude(
        build_sabri_agent_prompt(result, sanitized_summary, address, suburb_display),
        api_key,
        max_tokens=PIPELINE_CONFIG["token_limits"]["sabri"],
        parse_json=True,
        model=sabri_model,
        required_keys={"headline", "sub_headline", "meta_title", "meta_description"},
    )
    print(f"    Done ({time.time()-t0:.1f}s)")
    return sabri_result


def _run_reflection(
    result: Dict,
    prop_summary: str,
    agent_briefings: Dict[str, str],
    api_key: str,
) -> Optional[Dict]:
    """Run the reflection agent to critique Draft 1.

    Returns reflection dict with content_score, has_data_gaps, raw, etc., or None on failure.
    """
    print("  [Step 5] Reflection Agent — critiquing all content...")
    t0 = time.time()

    reflection_prompt = f"""You are the SENIOR EDITOR and QUALITY CONTROLLER for Fields Estate. A team of agents just produced Draft 1 of a property editorial. Your job is to critique the BODY CONTENT (insights, verdict) and the underlying data — then produce a brief for improvement.

NOTE: Headlines and meta are handled by a separate Sabri Suby specialist. Do NOT suggest headlines. Focus on content quality only.

DRAFT 1 OUTPUT:
Headline: "{result.get('headline', '')}"
Sub-headline: "{result.get('sub_headline', '')}"
Insights:
{json.dumps(result.get('insights', []), indent=2)}
Verdict: "{result.get('verdict', '')}"

RAW DATA THE AGENTS WORKED FROM:
Property summary: {prop_summary[:1500]}

Agent briefings:
PRICE: {agent_briefings['price'][:600]}
PROPERTY: {agent_briefings['property'][:600]}
MARKET: {agent_briefings['market'][:600]}

---

CRITIQUE each element. Be brutal. You are the last line of defence before a human reviews this.

1. SELLING PRINCIPLES CHECK:
   - Does each insight demonstrate a selling principle? (confidence through evidence, trust through transparency, price as story, objections pre-answered)
   - Is every trade-off framed as a value equation with a priced alternative?
   - Would a seller reading this think "Fields would position my property honestly and intelligently"?

2. INSIGHTS CRITIQUE:
   - Does each lead contain a specific number and stand alone as scannable?
   - Does each detail connect to a BUYER IMPLICATION?
   - Are there DATA CONTRADICTIONS? (e.g. lot size in data vs agent description)
   - Are there MISSED ANGLES the agents had data for but didn't use?
   - Are comparable sales cited by name with specific adjusted figures?
   - Is any insight built on LOW-CONFIDENCE data? (e.g. specific material identification from photos)

3. FLOOD POSITIONING CHECK (AUTOMATIC FAIL if violated):
   - Does flood/flood overlay appear in insights 1, 2, or 3? FAIL. Flood must be the LAST insight or a dedicated final section only.
   - Does the headline or sub-headline reference flood? FAIL.
   - NEVER suggest putting flood earlier. NEVER suggest a flood-based headline.

4. VERDICT CRITIQUE:
   - Is it memorable? Would someone repeat it at dinner?
   - Is it under 25 words?

5. SEO DATE CHECK (AUTOMATIC FAIL if violated):
   - Does the verdict contain a DAY COUNT? FAIL. Must use listing DATE.
   - Day counts are ONLY allowed in insight detail text.

6. DATA GAP ANALYSIS:
   - What data is MISSING that would make this editorial stronger?
   - Did the agents contradict each other?
   - Are there comparable sales that should be referenced but aren't?

OUTPUT as PLAIN TEXT using this exact format (not JSON):

CONTENT SCORE: X/5
CONTENT ISSUES: [bullet list]
DATA CONTRADICTIONS: [bullet list]
MISSED ANGLES: [bullet list]
DATA GAPS TO FILL: [bullet list]
FLOOD POSITION: [OK or FAIL — state where flood appears]
SUGGESTED VERDICT: [max 25 words]
OVERALL: [one paragraph assessment]

Do NOT suggest headlines. Do NOT reference flood in suggested content. Max 400 words total."""

    try:
        reflection_text = call_claude(
            reflection_prompt, api_key,
            max_tokens=PIPELINE_CONFIG["token_limits"]["reflection"],
            parse_json=False,
            model=PIPELINE_CONFIG["models"]["reflection"],
        )
        print(f"    Done ({time.time()-t0:.1f}s)")

        # Parse key fields from plain text
        reflection = {"raw": reflection_text}
        for line in reflection_text.split("\n"):
            line = line.strip()
            if line.startswith("CONTENT SCORE:"):
                reflection["content_score"] = line.split(":", 1)[1].strip()
            elif line.startswith("SUGGESTED VERDICT:"):
                reflection["suggested_verdict"] = line.split(":", 1)[1].strip()
            elif line.startswith("FLOOD POSITION:"):
                reflection["flood_position"] = line.split(":", 1)[1].strip()

        # Extract bullet lists
        has_gaps = "DATA GAPS TO FILL:" in reflection_text
        reflection["has_data_gaps"] = has_gaps

        print(f"    Content score: {reflection.get('content_score', '?')}")
        print(f"    Flood position: {reflection.get('flood_position', '?')}")

        # Print the key sections
        for section in ["CONTENT ISSUES", "DATA CONTRADICTIONS", "MISSED ANGLES", "DATA GAPS"]:
            if section + ":" in reflection_text:
                idx = reflection_text.index(section + ":")
                chunk = reflection_text[idx:idx+300].split("\n")
                for line in chunk[1:5]:
                    if line.strip().startswith("-") or line.strip().startswith("*"):
                        print(f"      [{section[:8]}] {line.strip()[:100]}")

        return reflection

    except Exception as e:
        print(f"    [WARN] Reflection failed: {e}")
        return None


def _run_backfill(
    reflection: Optional[Dict],
    prop_summary: str,
    api_key: str,
) -> str:
    """Run the data backfill agent to fill gaps identified by reflection.

    Returns backfill data text, or empty string if skipped.
    """
    if not reflection or not reflection.get("has_data_gaps"):
        print("  [Step 6] Skipped — no data gaps identified")
        return ""

    print("  [Step 6] Data Backfill Agent — filling gaps...")
    t0 = time.time()

    # Extract gap/contradiction bullets from raw text
    def _extract_section(text, header):
        if header not in text:
            return ""
        start = text.index(header) + len(header)
        lines = []
        for line in text[start:start+500].split("\n"):
            line = line.strip()
            if line.startswith("-") or line.startswith("*"):
                lines.append(line)
            elif lines and not line:
                break
            elif lines and not line.startswith("-") and not line.startswith("*"):
                break
        return "\n".join(lines)

    gaps_list = _extract_section(reflection.get("raw", ""), "DATA GAPS TO FILL:")
    contradictions_list = _extract_section(reflection.get("raw", ""), "DATA CONTRADICTIONS:")
    missed_list = _extract_section(reflection.get("raw", ""), "MISSED ANGLES:")

    backfill_prompt = f"""You are a DATA VERIFICATION agent for Fields Estate. The Reflection Agent identified gaps, contradictions, and missed angles in Draft 1 of a property editorial. Your job is to go back to the raw data and extract what was missed.

PROPERTY DATA (full):
{prop_summary}

AGENT DESCRIPTION (from the listing — may contain facts not in our structured data):
{prop_summary[prop_summary.find('Agent description:'):] if 'Agent description:' in prop_summary.lower() else 'Not available in summary — check features and description fields.'}

DATA GAPS TO FILL:
{gaps_list}

DATA CONTRADICTIONS TO RESOLVE:
{contradictions_list if contradictions_list else '  None identified'}

MISSED ANGLES TO INVESTIGATE:
{missed_list if missed_list else '  None identified'}

TASK: For each gap, contradiction, and missed angle — search the property data above and write a brief (2-3 sentences) with what you found. If the data doesn't contain the answer, say "NOT FOUND IN DATA — would require [source]."

Also: Re-read the agent description carefully. Extract any facts that the original agents missed (renovation year, specific features, seller motivation, neighbourhood details).

Write your findings as plain text. Be specific. Every claim must reference the data field it came from."""

    backfill_data = call_claude(
        backfill_prompt, api_key,
        max_tokens=PIPELINE_CONFIG["token_limits"]["backfill"],
        parse_json=False,
        model=PIPELINE_CONFIG["models"]["backfill"],
    )
    print(f"    Done ({time.time()-t0:.1f}s, {len(backfill_data)} chars)")
    return backfill_data


def _run_fact_check(
    draft: Dict,
    prop_summary: str,
    competing_str: str,
    medians_str: str,
    sales_str: str,
    api_key: str,
) -> Tuple[str, int]:
    """Run the fact-check agent on a draft.

    Returns (factcheck_text, failure_count).
    """
    print("  [Step 6.5] Fact-Check Agent — verifying all claims...")
    t0 = time.time()
    factcheck_text = ""
    failed = 0

    try:
        factcheck_prompt = f"""You are a FACT-CHECKER for Fields Estate. Your ONLY job is to verify every factual claim in Draft 1 against the raw source data below. You are not a writer — you are an auditor.

DRAFT 1:
Headline: "{draft.get('headline', '')}"
Sub-headline: "{draft.get('sub_headline', '')}"
Insights:
{json.dumps(draft.get('insights', []), indent=2)}
Verdict: "{draft.get('verdict', '')}"

RAW SOURCE DATA (COMPLETE — every field the agents had access to):
{prop_summary}

COMPETING LISTINGS DATA:
{competing_str}

SUBURB MEDIANS:
{medians_str}

RECENT SALES:
{sales_str}

INSTRUCTIONS:
Extract EVERY factual claim from Draft 1 (numbers, counts, percentages, dates, material descriptions, "all" or "none" statements). For each one, check it against the raw data.

Output format — one line per claim:
✅ VERIFIED: "[exact claim]" — source: [field/data that confirms it]
❌ FAILED: "[exact claim]" — actual data says: [what the data actually shows]
⚠️ UNVERIFIABLE: "[exact claim]" — not present in available data

CRITICAL CHECKS:
- If draft says "all listings hide their price" or "zero price guides" — COUNT the actual prices in competing listings data
- If draft cites a specific dollar amount — verify it exists in transactions or valuation data
- If draft cites a percentage or multiplier — recalculate it from the source numbers
- If draft describes a material (laminate, stone, timber) — check property_valuation_data fields
- If draft says "no comparable sales" — check if recent sales data contains any
- If draft cites days on market or a date — verify against first_listed_timestamp

VALUATION LANGUAGE RULE — DO NOT FAIL approximate valuation claims:
- Valuations are inherently ranges, not exact figures. A property valuation is an estimate, not a fact.
- If the draft says "priced below the comparable midpoint" or "in the lower half of the range" or "around $2.4M" — this is ACCEPTABLE approximate language. Do NOT fail it for not being mathematically precise.
- If the draft says "our valuation is exactly $2,396,327" — THAT should be failed, because exact single-figure valuations imply false precision.
- The correct standard: valuation claims should be directional (above/below/within range) or use ranges. Approximate language like "roughly", "around", "in the lower half" is CORRECT, not an error.

INVISIBLE ROOM RULE (AUTOMATIC FAIL):
If the draft claims a room is "unrenovated", "untouched", "dated", "not upgraded", or describes its condition — but that room has "visible": false and null condition scores in property_valuation_data — mark it ❌ FAILED. The field "bathrooms_renovated": false is UNRELIABLE when bathrooms were not photographed. The correct claim is "condition data not available" or "not photographed".

Be exhaustive on factual claims. Be lenient on valuation approximations."""

        factcheck_text = call_claude(
            factcheck_prompt, api_key,
            max_tokens=PIPELINE_CONFIG["token_limits"]["fact_check"],
            parse_json=False,
            model=PIPELINE_CONFIG["models"]["fact_check"],
        )
        print(f"    Done ({time.time()-t0:.1f}s)")

        # Count failures
        failed = factcheck_text.count("❌ FAILED")
        verified = factcheck_text.count("✅ VERIFIED")
        unverifiable = factcheck_text.count("⚠️ UNVERIFIABLE") + factcheck_text.count("⚠ UNVERIFIABLE")
        print(f"    Results: {verified} verified, {failed} FAILED, {unverifiable} unverifiable")

        # Print failures
        for line in factcheck_text.split("\n"):
            if "FAILED" in line:
                print(f"    {line.strip()[:120]}")

    except Exception as e:
        print(f"    [WARN] Fact-check failed: {e}")

    return factcheck_text, failed


def _run_draft2_loop(
    draft1: Dict,
    factcheck_text: str,
    reflection: Optional[Dict],
    backfill_data: str,
    prop_summary: str,
    competing_str: str,
    medians_str: str,
    suburb_display: str,
    address: str,
    api_key: str,
    headline_failed: bool,
    failed: int,
) -> Optional[Dict]:
    """Run the Draft 2 rewrite loop with fact-check verification.

    Returns final_draft dict, or None if all attempts fail.
    """
    MAX_RETRIES = PIPELINE_CONFIG["retry"]["max_draft2_attempts"]

    angle_instruction = ""
    if headline_failed:
        angle_instruction = """
CRITICAL: The fact-checker found that the HEADLINE ANGLE is based on fabricated data. You CANNOT patch Draft 1 — you must find a COMPLETELY NEW ANGLE for the property. Go back to the agent briefings and find a different story. The headline, sub-headline, and any insights built on the failed claims must be rewritten from scratch.
"""
    print(f"  [Step 7] Editor Draft 2 — rewriting ({failed} failures to fix)...")
    t0 = time.time()

    # Build Draft 2 body content — exclude Draft 1 headline/meta (those came from Sabri agent)
    draft1_body = {k: v for k, v in draft1.items() if k not in ("headline", "sub_headline", "meta_title", "meta_description", "_sabri_suggested_h2s")}

    draft2_prompt = f"""You are the EDITORIAL DIRECTOR for Fields Estate, writing DRAFT 2 of the property editorial BODY for {address}.

NOTE: You write BODY content only (insights, verdict, next_steps, CTAs, flood_section, FAQs). A separate Sabri Suby specialist handles headlines and meta. Do NOT include headline, sub_headline, meta_title, or meta_description.

DRAFT 1 BODY (your first attempt):
{json.dumps(draft1_body, indent=2, default=str)}

FACT-CHECK RESULTS (CRITICAL — you MUST fix every ❌ FAILED item):
{factcheck_text if factcheck_text else "Fact-check not available."}

REFLECTION AGENT FEEDBACK:
{reflection.get('raw', 'No reflection available — improve based on your own assessment.') if reflection else "No reflection available — improve based on your own assessment."}

ADDITIONAL DATA FROM BACKFILL:
{backfill_data if backfill_data else "No additional data."}

RAW PROPERTY DATA (use this to verify claims and write the flood_section — do NOT rely on Draft 1's interpretation):
{prop_summary}

---

INSTRUCTIONS FOR DRAFT 2:

0. CRITICAL: Fix every ❌ FAILED fact. If a claim was marked FAILED, correct it with actual data or REMOVE IT. Do not replace a failed claim with a new unverified claim — that just creates a new failure.
{angle_instruction}

1. FIX issues the Reflection Agent identified. Resolve data contradictions. Use missed angles ONLY if you can cite the specific data field.

2. Insight leads must be CONVERSATIONAL. Each detail must answer "what does this mean for the buyer?"

3. Reference comparable sales by NAME with specific adjusted figures. Use valuation adjustment rates to price trade-offs.

4. FLOOD POSITIONING: Flood overlay content MUST be the LAST insight or dedicated final section. NEVER in insights 1, 2, or 3.

5. Do NOT introduce new claims that weren't in Draft 1. The goal is to FIX errors, not add content. Every new number you add must be verifiable against the raw data below.

6. INCLUDE next_steps, cta_valuation, cta_market_buy, cta_market_sell, flood_section, and faqs.

7. FLOOD_SECTION: Use the SPECIFIC flood data from the RAW PROPERTY DATA above. If the data shows "FLOOD OVERLAY: Yes", include the exact depth classification, ground vs DFL measurement, and ICA insurance zone status. If "ICA INSURANCE ZONES: does NOT fall within ANY" — state this explicitly. Do NOT write generic "check the council website" when specific data is right there.

8. SEO DATE RULE: In verdict, next_steps, CTA hooks, FAQ answers — use listing DATE not day counts.

9. VERDICT: One or two sentences. Short enough that someone repeats it to their partner at dinner or to their friends at a BBQ.

SUBURB SLUG: {suburb_display.replace(' ', '_')}

OUTPUT BODY JSON — use v2 structured insight format (no headline, no meta, no markdown, no code fences):
{{
  "insights": [
    {{"h2": "...", "key_points": ["...", "..."], "key_points_label": "Key points", "what_this_means": ["..."], "comparables": null}},
    {{"h2": "...", "key_points": ["...", "..."], "key_points_label": "Key points", "what_this_means": ["..."], "comparables": null}},
    {{"h2": "...", "key_points": ["...", "..."], "key_points_label": "Comparable sales", "what_this_means": ["..."], "comparables": [{{"address":"...","distance":"...","sold_price":0,"adjusted_price":0,"summary":"...","delta_label":"..."}}]}},
    {{"h2": "...", "key_points": ["...", "..."], "key_points_label": "Key points", "what_this_means": ["..."], "comparables": null}}
  ],
  "verdict": "... uses listing DATE not day count ...",
  "quick_take": {{"strengths": ["...", "..."], "trade_off": "..."}},
  "best_for": ["...", "...", "..."],
  "not_ideal_for": ["...", "...", "..."],
  "next_steps": ["...", "...", "...", "..."],
  "cta_valuation": {{"hook": "...", "label": "Walk through the valuation step by step", "tab": "valuation"}},
  "cta_market_buy": {{"hook": "...", "label": "Read the {suburb_display} buyer's market briefing", "url": "/market-metrics/{suburb_display.replace(' ', '_')}#buy"}},
  "cta_market_sell": {{"hook": "...", "label": "Read the {suburb_display} seller's market briefing", "url": "/market-metrics/{suburb_display.replace(' ', '_')}#sell"}},
  "flood_section": {{"title": "...", "body": "...", "source": "Gold Coast City Council ArcGIS flood mapping"}},
  "faqs": [{{"question": "...", "answer": "..."}}, ...]
}}"""

    final_draft = None

    for attempt in range(1, MAX_RETRIES + 1):
        try:
            current_draft = call_claude(
                draft2_prompt, api_key,
                max_tokens=PIPELINE_CONFIG["token_limits"]["draft2"],
                parse_json=True,
                model=PIPELINE_CONFIG["models"]["draft2"],
                required_keys={"insights", "verdict"},
            )
            print(f"    Done ({time.time()-t0:.1f}s)")
            print(f"\n  --- DRAFT {attempt + 1} VERDICT: \"{current_draft.get('verdict', '')[:80]}\"")

            # Re-run fact-check on the new draft (attempts 1+)
            if attempt < MAX_RETRIES:
                print(f"  [Verify] Fact-checking Draft {attempt + 1}...")
                t0 = time.time()
                verify_prompt = f"""You are a FACT-CHECKER. Verify every factual claim in this draft against the raw data. Output ONLY lines marked ❌ FAILED — skip verified claims.

DRAFT:
{json.dumps(current_draft, indent=2, default=str)}

RAW DATA (COMPLETE):
{prop_summary}

COMPETING LISTINGS:
{competing_str}

MEDIANS:
{medians_str}

IMPORTANT: If a claim matches data in the RAW DATA above, it is VERIFIED — do not mark it as failed just because you didn't search thoroughly. Check beach distance, land utilization, rental estimates, agent description, and satellite analysis sections.

If a PRE-CALCULATED figure exists (growth %, CAGR), the draft MUST use that exact figure — do NOT recalculate from raw transaction prices.

VALUATION LANGUAGE: Approximate valuation claims are CORRECT. "Below the comparable midpoint", "in the lower half of the range", "around $2.4M" — these are acceptable. Do NOT fail directional or approximate valuation language. Only fail exact single-figure valuations like "worth exactly $2,396,327."

Output ONLY failed claims as:
❌ FAILED: "[claim]" — actual: [what data shows]

If ALL claims are verified, output: ✅ ALL CLAIMS VERIFIED"""

                verify_text = call_claude(
                    verify_prompt, api_key,
                    max_tokens=PIPELINE_CONFIG["token_limits"]["verify"],
                    parse_json=False,
                    model=PIPELINE_CONFIG["models"]["fact_check"],
                )
                verify_failures = verify_text.count("❌ FAILED")
                print(f"    {time.time()-t0:.1f}s — {verify_failures} failures found")

                if verify_failures > 0:
                    for line in verify_text.split("\n"):
                        if "FAILED" in line:
                            print(f"    {line.strip()[:120]}")

                    if verify_failures <= PIPELINE_CONFIG["retry"]["fact_check_accept_threshold"]:
                        # Minor issues — accept with note
                        print(f"    Minor issues — accepting Draft {attempt + 1} with {verify_failures} flag(s)")
                        final_draft = current_draft
                        break
                    else:
                        # Major issues — retry with corrections
                        print(f"    {verify_failures} failures — retrying (attempt {attempt + 1}/{MAX_RETRIES})...")
                        draft2_prompt = f"""Fix EVERY failed claim below. Output the corrected BODY JSON (no headline/meta — those are handled separately).

FAILED CLAIMS:
{verify_text}

PREVIOUS DRAFT:
{json.dumps(current_draft, indent=2, default=str)[:2500]}

RAW DATA (use ONLY these numbers — includes flood data for flood_section):
{prop_summary}

RULES:
- Fix or remove every ❌ FAILED claim
- NEVER use flood/overlay in insights 1, 2, or 3 — flood is LAST only
- The flood_section MUST use the specific flood data from RAW DATA above (overlay status, ground vs DFL, depth classification, ICA zones). Do NOT write generic "check the council" advice when specific data is available.
- Use listing DATE not day counts in verdict, next_steps, CTA hooks, FAQ answers
- Keep the same JSON structure but do NOT include headline, sub_headline, meta_title, meta_description

OUTPUT BODY JSON — use v2 structured format (no markdown, no code fences):
{{
  "insights": [
    {{"h2": "...", "key_points": ["...", "..."], "key_points_label": "Key points", "what_this_means": ["..."], "comparables": null}},
    {{"h2": "...", "key_points": ["...", "..."], "key_points_label": "Key points", "what_this_means": ["..."], "comparables": null}},
    {{"h2": "...", "key_points": ["...", "..."], "key_points_label": "Comparable sales", "what_this_means": ["..."], "comparables": [{{"address": "...", "distance": "...", "sold_price": 0, "adjusted_price": 0, "summary": "...", "delta_label": "..."}}]}},
    {{"h2": "...", "key_points": ["...", "..."], "key_points_label": "Key points", "what_this_means": ["..."], "comparables": null}}
  ],
  "verdict": "...",
  "quick_take": {{"strengths": ["...", "..."], "trade_off": "..."}},
  "best_for": ["...", "...", "..."],
  "not_ideal_for": ["...", "...", "..."],
  "next_steps": ["...", "...", "...", "..."],
  "cta_valuation": {{"hook": "...", "label": "Walk through the valuation step by step", "tab": "valuation"}},
  "cta_market_buy": {{"hook": "...", "label": "Read the {suburb_display} market briefing", "url": "/market-metrics/{suburb_display.replace(' ', '_')}#buy"}},
  "cta_market_sell": {{"hook": "...", "label": "Read the {suburb_display} seller briefing", "url": "/market-metrics/{suburb_display.replace(' ', '_')}#sell"}},
  "flood_section": {{"title": "...", "body": "...", "source": "Gold Coast City Council ArcGIS flood mapping"}},
  "faqs": [{{"question": "...", "answer": "..."}}, ...]
}}"""
                        t0 = time.time()
                        continue
                else:
                    print(f"    ✅ All claims verified — accepting Draft {attempt + 1}")
                    final_draft = current_draft
                    break
            else:
                # Last attempt — accept whatever we have
                print(f"    Max retries reached — accepting Draft {attempt + 1} as final")
                final_draft = current_draft
                break

        except Exception as e:
            print(f"    [WARN] Draft {attempt + 1} failed: {e}")
            if attempt == MAX_RETRIES:
                print(f"    All {MAX_RETRIES} attempts failed — keeping Draft 1")
            continue

    return final_draft


# ---------------------------------------------------------------------------
# Orchestrator: run_multi_agent_pipeline()
# ---------------------------------------------------------------------------

def run_multi_agent_pipeline(
    prop_summary: str,
    suburb_medians: List[Dict],
    competing_listings: List[Dict],
    recent_sales: List[Dict],
    suburb_name: str,
    address: str,
    api_key: str,
    use_gemini_gather: bool = False,
    gemini_api_key: str = None,
    use_openai_gather: bool = False,
    openai_api_key: str = None,
    use_hybrid_gather: bool = False,
) -> Dict:
    """Run 3 specialist agents in sequence, then an editor agent to synthesise."""
    suburb_display = suburb_name.replace("_", " ").title()
    medians_str = format_medians(suburb_medians)
    competing_str = format_competing(competing_listings)
    sales_str = format_sales(recent_sales)

    # Build gather mode configuration
    gather_cfg = _build_gather_config(
        use_gemini_gather, gemini_api_key,
        use_openai_gather, openai_api_key,
        use_hybrid_gather, api_key,
    )

    # Step 1-3: Gathering agents
    agent_briefings = _run_gathering_agents(
        prop_summary, medians_str, competing_str, sales_str,
        suburb_display, address, api_key, gather_cfg,
    )

    # Step 4: Editor synthesises body content
    result = _run_editor(agent_briefings, address, suburb_display, prop_summary, api_key)

    # Step 4b: Sabri Suby headline specialist
    sanitized_summary = strip_flood_from_summary(prop_summary)
    sabri_result = _run_sabri(result, sanitized_summary, address, suburb_display, api_key)
    result["headline"] = sabri_result["headline"]
    result["sub_headline"] = sabri_result["sub_headline"]
    result["meta_title"] = sabri_result["meta_title"]
    result["meta_description"] = sabri_result["sub_headline"]  # hardcoded: sub_headline IS the meta description
    result["_sabri_suggested_h2s"] = sabri_result.get("suggested_h2s", [])

    # -----------------------------------------------------------------------
    # DRAFT 1 COMPLETE — now reflect, backfill data gaps, and write Draft 2
    # -----------------------------------------------------------------------

    draft1 = json.loads(json.dumps(result, default=str))  # snapshot
    print(f"\n  --- DRAFT 1 HEADLINE: \"{result.get('headline', '')}\"")

    # Step 5: Reflection
    reflection = _run_reflection(result, prop_summary, agent_briefings, api_key)

    # Step 6: Backfill
    backfill_data = _run_backfill(reflection, prop_summary, api_key)

    # Step 6.5: Fact-check
    factcheck_text, failed = _run_fact_check(
        draft1, prop_summary, competing_str, medians_str, sales_str, api_key,
    )

    # Check if headline angle is invalidated by fact-check
    headline_failed = False
    for line in factcheck_text.split("\n"):
        if "FAILED" in line:
            claim_text = line.lower()
            headline_lower = draft1.get("headline", "").lower()
            if any(word in claim_text for word in headline_lower.split() if len(word) > 4):
                headline_failed = True
                break

    if headline_failed:
        print(f"    ⚠️  HEADLINE ANGLE INVALIDATED — Draft 2 must find a new angle, not patch.")

    # Early accept: if Draft 1 has few fact-check failures and no headline invalidation, skip Draft 2
    accept_threshold = PIPELINE_CONFIG["retry"]["fact_check_accept_threshold"]
    if not headline_failed and failed <= accept_threshold:
        print(f"  [Step 7] SKIPPED — Draft 1 has {failed} failure(s), accepting as final")
        result["_draft1"] = {
            "headline": draft1.get("headline"),
            "sub_headline": draft1.get("sub_headline"),
            "verdict": draft1.get("verdict"),
        }
        result["_reflection"] = reflection
        result["_backfill_data"] = backfill_data if backfill_data else None
        result["_factcheck_failures"] = failed
        result["_accepted_draft"] = 1
        result["_agent_briefings"] = agent_briefings
        return result

    # Step 7: Draft 2 loop
    final_draft = _run_draft2_loop(
        draft1, factcheck_text, reflection, backfill_data,
        prop_summary, competing_str, medians_str,
        suburb_display, address, api_key, headline_failed, failed,
    )

    # Track whether fact-checking passed
    if not final_draft:
        result["_factcheck_status"] = "failed"
        print("  ⚠️  All drafts failed fact-check — marking as failed_factcheck")

    # Apply the final draft (or fall back to Draft 1)
    if final_draft:
        result["_draft1"] = {
            "headline": draft1.get("headline"),
            "sub_headline": draft1.get("sub_headline"),
            "verdict": draft1.get("verdict"),
        }
        result["_reflection"] = reflection
        result["_backfill_data"] = backfill_data if backfill_data else None
        # Merge body content from final draft
        result["insights"] = final_draft["insights"]
        result["verdict"] = final_draft["verdict"]
        if final_draft.get("next_steps"):
            result["next_steps"] = final_draft["next_steps"]
        if final_draft.get("faqs"):
            result["faqs"] = final_draft["faqs"]
        if final_draft.get("cta_valuation"):
            result["cta_valuation"] = final_draft["cta_valuation"]
        if final_draft.get("cta_market_buy"):
            result["cta_market_buy"] = final_draft["cta_market_buy"]
        if final_draft.get("cta_market_sell"):
            result["cta_market_sell"] = final_draft["cta_market_sell"]
        if final_draft.get("flood_section"):
            result["flood_section"] = final_draft["flood_section"]

        # Re-run Sabri agent on the final body
        print("  [Sabri Re-run] Generating headline for final body...")
        t0 = time.time()
        try:
            sabri_final = _run_sabri(result, sanitized_summary, address, suburb_display, api_key)
            result["headline"] = sabri_final["headline"]
            result["sub_headline"] = sabri_final["sub_headline"]
            result["meta_title"] = sabri_final["meta_title"]
            result["meta_description"] = sabri_final["sub_headline"]  # hardcoded: sub_headline IS the meta description
            result["_sabri_suggested_h2s"] = sabri_final.get("suggested_h2s", [])
            print(f"    Done ({time.time()-t0:.1f}s) — \"{sabri_final['headline']}\"")
        except Exception as e:
            print(f"    [WARN] Sabri re-run failed: {e} — keeping Draft 1 headline")

    # Attach the agent briefings for debugging
    result["_agent_briefings"] = agent_briefings

    return result


# ---------------------------------------------------------------------------
# Store result
# ---------------------------------------------------------------------------

def _fix_year_hallucinations(analysis: Dict, prop: Dict) -> Dict:
    """Post-processing: fix common LLM year hallucinations using actual data."""
    import re
    first_listed = prop.get("first_listed_timestamp") or prop.get("date_first_listed") or ""
    fl_str = str(first_listed)[:10]  # YYYY-MM-DD
    if not fl_str or len(fl_str) < 4:
        return analysis
    correct_year = fl_str[:4]  # e.g. "2026"

    # Common hallucination: model writes 2025 instead of 2026 (or vice versa)
    wrong_years = [str(int(correct_year) - 1), str(int(correct_year) + 1)]

    # Parse the correct month-day for targeted replacement
    try:
        fl_date = datetime.strptime(fl_str, "%Y-%m-%d")
        month_day = fl_date.strftime("%d %B")  # e.g. "10 February"
        month_day_alt = fl_date.strftime("%-d %B")  # e.g. "10 February" without leading zero
    except Exception:
        return analysis

    def fix_text(text: str) -> str:
        if not isinstance(text, str):
            return text
        for wrong_year in wrong_years:
            # Fix "10 February 2025" → "10 February 2026"
            text = text.replace(f"{month_day} {wrong_year}", f"{month_day} {correct_year}")
            text = text.replace(f"{month_day_alt} {wrong_year}", f"{month_day_alt} {correct_year}")
        return text

    # Fix all text fields
    for key in ["headline", "sub_headline", "verdict", "meta_title", "meta_description"]:
        if key in analysis:
            analysis[key] = fix_text(analysis[key])
    for step in analysis.get("next_steps", []):
        idx = analysis["next_steps"].index(step)
        analysis["next_steps"][idx] = fix_text(step)
    for cta_key in ["cta_valuation", "cta_market_buy", "cta_market_sell"]:
        cta = analysis.get(cta_key, {})
        if isinstance(cta, dict) and "hook" in cta:
            cta["hook"] = fix_text(cta["hook"])
    for faq in analysis.get("faqs", []):
        faq["question"] = fix_text(faq.get("question", ""))
        faq["answer"] = fix_text(faq.get("answer", ""))
    for insight in analysis.get("insights", []):
        # v2 format (h2 + key_points + what_this_means)
        if "h2" in insight:
            insight["h2"] = fix_text(insight.get("h2", ""))
            insight["key_points"] = [fix_text(kp) for kp in insight.get("key_points", [])]
            insight["what_this_means"] = [fix_text(m) for m in insight.get("what_this_means", [])]
        # v1 format (lead + detail) — backward compat
        if "lead" in insight:
            insight["lead"] = fix_text(insight.get("lead", ""))
        if "detail" in insight:
            insight["detail"] = fix_text(insight.get("detail", ""))

    return analysis


def store_analysis(db, suburb: str, property_id, analysis: Dict) -> None:
    """Write ai_analysis field to the property document."""
    analysis["generated_at"] = datetime.now(timezone.utc).isoformat()
    analysis["model"] = PIPELINE_CONFIG["models"]["editor"]
    # If fact-check failed after all retries, mark as failed — don't show in review queue
    if analysis.get("_factcheck_status") == "failed":
        analysis["status"] = "failed_factcheck"
    else:
        analysis["status"] = analysis.get("status", "draft")  # draft until human review

    cosmos_retry(lambda: db[suburb].update_one(
        {"_id": property_id},
        {"$set": {"ai_analysis": analysis}},
    ), "store_analysis")
    print(f"[OK] Stored ai_analysis on property {property_id}")


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def process_property(db, suburb: str, prop: Dict, api_key: str, force: bool = False, use_gemini_gather: bool = False, gemini_api_key: str = None, use_openai_gather: bool = False, openai_api_key: str = None, use_hybrid_gather: bool = False) -> Dict:
    """Run the full pipeline for one property."""
    address = prop.get("address", "Unknown")
    prop_id = prop["_id"]

    if not force and prop.get("ai_analysis") and prop["ai_analysis"].get("headline"):
        print(f"[SKIP] {address} — already has ai_analysis (use --force to regenerate)")
        return prop["ai_analysis"]

    print(f"\n{'='*60}")
    print(f"Processing: {address}")
    print(f"{'='*60}")

    # Pre-step: Ensure zoning + flood + ICA data exists before generating content
    if not prop.get("zoning_data") or not prop["zoning_data"].get("ica_flood_zones"):
        print("[0/5] Enriching zoning + flood + ICA data...")
        try:
            sys.path.insert(0, str(Path(__file__).resolve().parent))
            from enrich_zoning_data import enrich_property_zoning
            zoning = enrich_property_zoning(prop)
            if zoning:
                cosmos_retry(lambda: db[suburb].update_one(
                    {"_id": prop_id},
                    {"$set": {"zoning_data": zoning}},
                ), "enrich_zoning")
                prop["zoning_data"] = zoning
                print(f"  Zoned: {zoning.get('zone', '?')} | Flood: {zoning.get('flood_overlay', '?')} | ICA: {'in zone' if zoning.get('in_any_ica_zone') else 'not in any zone'}")
            else:
                print("  [WARN] Could not enrich zoning (missing LOT/PLAN)")
        except Exception as e:
            print(f"  [WARN] Zoning enrichment failed: {e}")

    # Pre-step 2: Verify satellite claims with Claude Opus vision
    if prop.get("satellite_analysis") and not prop.get("satellite_analysis", {}).get("opus_verified"):
        print("[0.5/5] Verifying satellite analysis with Claude Opus...")
        try:
            verify_satellite_claims(prop, api_key, db=db, suburb=suburb)
        except Exception as e:
            print(f"  [WARN] Satellite verification failed: {e}")
    elif prop.get("satellite_analysis", {}).get("opus_verified"):
        v = prop["satellite_analysis"].get("opus_verification", {})
        print(f"[0.5/5] Satellite already verified — corrections: {v.get('corrections_applied', '?')}")

    # Pipeline 1: property data — pass full document to Opus (no lossy summary)
    print("[1/5] Serialising property document...")
    import json as _json
    _skip_keys = {
        '_id', 'ai_analysis', 'property_images', 'property_images_original',
        'scraped_property_images', 'image_history', 'image_analysis',
        'floor_plans', 'floor_plans_original', 'scraped_floor_plans',
        'images_blob_uploaded_at', 'images_uploaded_to_blob',
        'processing_status', 'extraction_method', 'extraction_date', 'scrape_mode',
        'scraped_at', 'last_updated', 'last_updated_date', 'last_enriched',
        'enrichment_attempted', 'enrichment_error', 'enrichment_data', 'enrichment_retry_count',
        'listing_url', 'og_title', 'source', 'url_slug', 'complete_address', 'street_address',
        'ADDRESS_PID', 'ADDRESS_STANDARD', 'ADDRESS_STATUS', 'UNIT_TYPE', 'UNIT_NUMBER',
        'UNIT_SUFFIX', 'PROPERTY_NAME', 'STREET_NO_1_SUFFIX', 'STREET_NO_2', 'STREET_NO_2_SUFFIX',
        'STREET_SUFFIX', 'LGA_CODE', 'GEOCODE_TYPE', 'LOTPLAN_STATUS', 'DATUM', 'PLAN', 'LOT',
        'property_tenure', 'property_tenure_desc', 'parcel_state', 'is_strata_title',
        'LOCAL_AUTHORITY', 'LOCALITY', 'classified_at', 'classification_model',
        'classification_confidence', 'classification_reasoning', 'classified_property_type',
        'postcode_enriched_at', 'cadastral_enriched_at', 'postcode_distance_km',
        'display_postcode', 'lot_size_sqm_source', 'lot_size_calc_sqm',
        'iteration_08_valuation', 'cadastral_accuracy',
        'parsed_rooms_updated', 'property_insights_updated', 'transactions_updated',
        'last_valuation_date',
    }
    _prop_clean = {k: v for k, v in prop.items() if k not in _skip_keys}
    # Strip satellite image URL (large, not needed for text analysis) but keep categories/narrative
    if 'satellite_analysis' in _prop_clean and isinstance(_prop_clean['satellite_analysis'], dict):
        _prop_clean['satellite_analysis'] = {k: v for k, v in _prop_clean['satellite_analysis'].items() if k != 'satellite_image_url'}

    # Annotate renovation booleans that are unreliable due to invisible rooms
    # If bathrooms have visible:false + null scores, bathrooms_renovated is UNRELIABLE
    pvd = _prop_clean.get('property_valuation_data', {})
    renovation = pvd.get('renovation', {})
    bathrooms_data = pvd.get('bathrooms', [])
    if renovation and bathrooms_data:
        all_invisible = all(
            b.get('visible') is False and b.get('condition_score') is None
            for b in bathrooms_data if isinstance(b, dict)
        )
        if all_invisible and isinstance(renovation, dict):
            renovation['_WARNING_bathrooms_renovated'] = (
                "UNRELIABLE — bathrooms were NOT photographed (visible: false, all scores null). "
                "This boolean is inferred from absence of evidence, NOT from observing the bathrooms. "
                "Do NOT use this field to claim bathrooms are 'unrenovated'. Say 'condition unknown — not photographed'."
            )
    # Same check for bedrooms
    bedrooms_data = pvd.get('bedrooms', [])
    if renovation and bedrooms_data:
        all_invisible = all(
            b.get('visible') is False and b.get('condition_score') is None
            for b in bedrooms_data if isinstance(b, dict)
        )
        if all_invisible and isinstance(renovation, dict):
            renovation['_WARNING_bedrooms'] = (
                "UNRELIABLE — bedrooms were NOT photographed. Do NOT claim condition. "
                "Say 'condition data not available'."
            )

    summary = _json.dumps(_prop_clean, indent=2, default=str)
    print(f"  Property document: {len(summary):,} chars (~{len(summary)//4:,} tokens)")

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
    gather_mode = "Gemini + Claude" if use_gemini_gather else "OpenAI + Claude" if use_openai_gather else "Hybrid (GPT-5.4 + Claude)" if use_hybrid_gather else "Claude"
    print(f"\nRunning multi-agent pipeline ({gather_mode})...")
    t0 = time.time()
    analysis = run_multi_agent_pipeline(
        summary, medians, competing, sales, suburb, address, api_key,
        use_gemini_gather=use_gemini_gather, gemini_api_key=gemini_api_key,
        use_openai_gather=use_openai_gather, openai_api_key=openai_api_key,
        use_hybrid_gather=use_hybrid_gather,
    )
    elapsed = time.time() - t0
    print(f"Pipeline complete in {elapsed:.1f}s")

    # Print results
    print(f"\n--- GENERATED ANALYSIS ---")
    print(f"Headline:    {analysis['headline']}")
    print(f"Sub-head:    {analysis['sub_headline']}")
    for i, ins in enumerate(analysis.get('insights', []), 1):
        h2 = ins.get('h2') or ins.get('lead', '?')
        print(f"Insight {i}:   {h2}")
        detail_preview = ins.get('detail', '') or ' | '.join(ins.get('key_points', [])[:2])
        print(f"  Detail:    {detail_preview[:120]}...")
    print(f"Verdict:     {analysis.get('verdict', '?')}")
    print(f"Meta title:  {analysis['meta_title']}")
    print(f"Meta desc:   {analysis['meta_description']}")

    # Post-process: fix year hallucinations before storing
    analysis = _fix_year_hallucinations(analysis, prop)

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
    group.add_argument("--new-listings", action="store_true", help="Process new listings (<=7 days) missing ai_analysis")
    group.add_argument("--backfill", action="store_true", help="Process ALL properties missing ai_analysis")
    parser.add_argument("--days", type=int, default=7, help="Days threshold for --new-listings (default 7)")
    parser.add_argument("--force", action="store_true", help="Regenerate even if analysis exists")
    parser.add_argument("--suburb", help="Restrict to one suburb")
    parser.add_argument("--dry-run", action="store_true", help="Show prompt but don't call Claude")
    parser.add_argument("--gemini-gather", action="store_true", help="Use Gemini for data-gathering agents (Price, Property, Market), keep Claude for Editor/Headline")
    parser.add_argument("--openai-gather", action="store_true", help="Use OpenAI GPT-5.4 for data-gathering agents, keep Claude for Editor/Headline")
    parser.add_argument("--hybrid-gather", action="store_true", help="GPT-5.4 for Price+Market agents, Claude for Property agent (best of both)")
    args = parser.parse_args()

    # API key
    api_key = os.environ.get("ANTHROPIC_SONNET_API_KEY") or os.environ.get("ANTHROPIC_API_KEY")
    if not api_key:
        print("[ERROR] No ANTHROPIC_SONNET_API_KEY or ANTHROPIC_API_KEY in environment")
        sys.exit(1)

    # Alternate gather model setup (optional)
    gemini_api_key = None
    openai_api_key = None
    use_gemini = args.gemini_gather
    use_openai = args.openai_gather
    use_hybrid = args.hybrid_gather
    if sum([use_gemini, use_openai, use_hybrid]) > 1:
        print("[ERROR] Cannot use more than one gather mode flag")
        sys.exit(1)
    if use_gemini:
        gemini_api_key = os.environ.get("GOOGLE_GEMINI_API_KEY")
        if not gemini_api_key:
            print("[ERROR] --gemini-gather requires GOOGLE_GEMINI_API_KEY in environment")
            sys.exit(1)
        if not GEMINI_AVAILABLE:
            print("[ERROR] --gemini-gather requires google-generativeai package")
            sys.exit(1)
        print(f"[INFO] Gemini mode: data-gathering agents will use {PIPELINE_CONFIG['models']['gather_gemini']}")
    if use_openai or use_hybrid:
        openai_api_key = os.environ.get("OPENAI_API_KEY")
        if not openai_api_key:
            print("[ERROR] --openai-gather/--hybrid-gather requires OPENAI_API_KEY in environment")
            sys.exit(1)
        if not OPENAI_AVAILABLE:
            print("[ERROR] --openai-gather/--hybrid-gather requires openai package")
            sys.exit(1)
        if use_hybrid:
            print(f"[INFO] Hybrid mode: {PIPELINE_CONFIG['models']['gather_openai']} for Price+Market, {PIPELINE_CONFIG['models']['gather_default']} for Property agent")
        else:
            print(f"[INFO] OpenAI mode: data-gathering agents will use {PIPELINE_CONFIG['models']['gather_openai']}")

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

        process_property(db, suburb, prop, api_key, force=args.force, use_gemini_gather=use_gemini, gemini_api_key=gemini_api_key, use_openai_gather=use_openai, openai_api_key=openai_api_key, use_hybrid_gather=use_hybrid)

    elif args.address:
        result = find_suburb_for_address(db, args.address)
        if not result:
            print(f"[ERROR] No active listing found matching '{args.address}'")
            sys.exit(1)
        suburb, prop = result
        print(f"Found in {suburb}: {prop.get('address')}")
        process_property(db, suburb, prop, api_key, force=args.force, use_gemini_gather=use_gemini, gemini_api_key=gemini_api_key, use_openai_gather=use_openai, openai_api_key=openai_api_key, use_hybrid_gather=use_hybrid)

    elif args.new_listings:
        suburbs = [args.suburb] if args.suburb else TARGET_SUBURBS
        total = 0
        for suburb in suburbs:
            query = {
                "listing_status": "for_sale",
                "days_on_domain": {"$lte": args.days},
            }
            if not args.force:
                query["ai_analysis"] = {"$exists": False}
            props = cosmos_retry(lambda s=suburb: list(db[s].find(query)), f"new_{suburb}")
            if props:
                print(f"\n{suburb}: {len(props)} new listings (≤{args.days}d)")
            for prop in props:
                try:
                    process_property(db, suburb, prop, api_key, force=args.force, use_gemini_gather=use_gemini, gemini_api_key=gemini_api_key, use_openai_gather=use_openai, openai_api_key=openai_api_key, use_hybrid_gather=use_hybrid)
                    total += 1
                    sleep_with_jitter(0.5)
                except Exception as e:
                    print(f"[ERROR] Failed on {prop.get('address', '?')}: {e}")
        print(f"\nDone. Processed {total} new listings.")

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
                    process_property(db, suburb, prop, api_key, force=args.force, use_gemini_gather=use_gemini, gemini_api_key=gemini_api_key, use_openai_gather=use_openai, openai_api_key=openai_api_key, use_hybrid_gather=use_hybrid)
                    total += 1
                    sleep_with_jitter(0.5)  # Rate limiting between API calls
                except Exception as e:
                    print(f"[ERROR] Failed on {prop.get('address', '?')}: {e}")
        print(f"\nDone. Processed {total} properties.")

    client.close()


if __name__ == "__main__":
    main()
