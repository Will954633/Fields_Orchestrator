#!/usr/bin/env python3
"""
Generate Seller Position Report (PDF)
======================================
Pulls property data from Gold_Coast DB, generates a positioning strategy
via Claude, renders an HTML template, and converts to PDF via Chromium.

Usage:
    python3 scripts/generate_seller_report.py --address "13 Terrace Court" --client "Dee" --suburb merrimac
    python3 scripts/generate_seller_report.py --address "13 Terrace Court" --client "Dee" --suburb merrimac --skip-ai
    python3 scripts/generate_seller_report.py --address "13 Terrace Court" --client "Dee" --suburb merrimac --dry-run

Requires:
    source /home/fields/venv/bin/activate
    set -a && source /home/fields/Fields_Orchestrator/.env && set +a
    pip install jinja2
    google-chrome or chromium-browser in PATH
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
from datetime import datetime
from pathlib import Path
from typing import Any, Optional
from zoneinfo import ZoneInfo

from jinja2 import Environment, FileSystemLoader
from pymongo import MongoClient

AEST = ZoneInfo("Australia/Brisbane")
ROOT = Path("/home/fields/Fields_Orchestrator")
TEMPLATE_DIR = ROOT / "templates"
OUTPUT_DIR = ROOT / "output" / "seller_reports"

# Positioning research stats
RESEARCH_STATS = "2,153 sold properties, 60+ studies, and 14 academic papers"
TOTAL_SOLD_TRACKED = "2,100+"


def get_db():
    """Connect to Cosmos DB."""
    conn = os.environ.get("COSMOS_CONNECTION_STRING")
    if not conn:
        print("[ERROR] COSMOS_CONNECTION_STRING not set")
        sys.exit(1)
    client = MongoClient(conn)
    return client


def find_property(db, suburb: str, address: str) -> Optional[dict]:
    """Find a property by address substring in a suburb collection."""
    col = db["Gold_Coast"][suburb]
    doc = col.find_one({"address": {"$regex": address, "$options": "i"}})
    if doc:
        return doc
    doc = col.find_one({"complete_address": {"$regex": address, "$options": "i"}})
    if doc:
        return doc
    doc = col.find_one({"street_address": {"$regex": address, "$options": "i"}})
    if doc:
        return doc
    doc = col.find_one({"display_address": {"$regex": address, "$options": "i"}})
    return doc


def format_price(value: Any) -> str:
    """Format a number as $X,XXX,XXX."""
    if not value:
        return "N/A"
    try:
        n = int(float(str(value).replace("$", "").replace(",", "")))
        return f"${n:,}"
    except (ValueError, TypeError):
        return str(value)


def get_sold_comparables(db, suburb: str, prop: dict) -> list[dict]:
    """Get recent house sales in the suburb with prices."""
    col = db["Gold_Coast"][suburb]
    sold = list(col.find({
        "listing_status": "sold",
        "property_type": {"$regex": "house", "$options": "i"},
    }))

    results = []
    for s in sold:
        price_raw = s.get("sold_price") or s.get("sale_price") or s.get("listing_price", "")
        price_str = str(price_raw) if price_raw else ""
        if "$" not in price_str:
            continue
        match = re.sub(r"[^\d]", "", price_str.split("$")[-1].split(" ")[0])
        if not match:
            continue
        price = int(match)
        date = str(s.get("sold_date", ""))
        if date < "2025-04-01":
            continue

        land = s.get("land_size_sqm") or s.get("lot_size_sqm")
        land_val = int(float(land)) if land and float(land) > 1 else None
        price_per_sqm = f"${int(price / land_val):,}" if land_val and land_val > 50 else "—"
        addr = (s.get("display_address") or s.get("complete_address") or
                s.get("street_address") or s.get("address") or "—")
        # Clean up address
        addr = addr.replace(", QLD 4226", "").replace(", Merrimac", "").replace(" MERRIMAC QLD 4226", "")

        results.append({
            "address": addr,
            "price": price,
            "price_display": format_price(price),
            "date": date,
            "bedrooms": s.get("bedrooms", "?"),
            "bathrooms": s.get("bathrooms", "?"),
            "land_size": str(land_val) if land_val else "—",
            "price_per_sqm": price_per_sqm,
        })

    results.sort(key=lambda x: x["date"], reverse=True)
    return results[:15]


def get_market_stats(db, suburb: str) -> dict:
    """Get market summary stats for the suburb."""
    col = db["Gold_Coast"][suburb]
    for_sale = col.count_documents({"listing_status": "for_sale"})

    sold = list(col.find({
        "listing_status": "sold",
        "property_type": {"$regex": "house", "$options": "i"},
    }))

    prices_12m = []
    for s in sold:
        date = str(s.get("sold_date", ""))
        if date < "2025-04-01":
            continue
        price_raw = s.get("sold_price") or s.get("sale_price") or ""
        price_str = str(price_raw)
        if "$" in price_str:
            match = re.sub(r"[^\d]", "", price_str.split("$")[-1].split(" ")[0])
            if match:
                prices_12m.append(int(match))

    median = sorted(prices_12m)[len(prices_12m) // 2] if prices_12m else 0
    return {
        "median": format_price(median),
        "houses_sold_12m": str(len(prices_12m)),
        "currently_listed": str(for_sale),
    }


def generate_positioning_strategy(prop: dict, comparables: list, market_stats: dict) -> dict:
    """Use Claude to generate a positioning strategy for the property."""
    try:
        import anthropic
    except ImportError:
        print("[WARN] anthropic not installed, using fallback positioning")
        return _fallback_positioning(prop)

    api_key = os.environ.get("ANTHROPIC_API_KEY")
    if not api_key:
        print("[WARN] No ANTHROPIC_API_KEY, using fallback positioning")
        return _fallback_positioning(prop)

    client = anthropic.Anthropic(api_key=api_key)

    address = prop.get("street_address") or prop.get("complete_address", "the property")
    suburb = prop.get("suburb", "")
    beds = prop.get("bedrooms", "?")
    baths = prop.get("bathrooms", "?")
    land = prop.get("land_size_sqm", "?")
    internal = prop.get("floor_plan_analysis", {}).get("internal_floor_area", {}).get("value", "?")
    condition = prop.get("property_valuation_data", {}).get("property_overview", {}).get("overall_condition_score", "?")
    vd = prop.get("valuation_data", {}).get("confidence", {})
    val_range = f"${vd.get('range', {}).get('low', 0):,} — ${vd.get('range', {}).get('high', 0):,}"
    reconciled = format_price(vd.get("reconciled_valuation", 0))
    last_sale = prop.get("sale_price", "?")
    last_sale_date = prop.get("sold_date", "?")
    desc = prop.get("agents_description", "")[:800]

    comp_text = "\n".join([
        f"  - {c['address']}: {c['price_display']} ({c['date']}) {c['bedrooms']}bd {c['land_size']}sqm"
        for c in comparables[:10]
    ])

    prompt = f"""You are the Fields Estate positioning strategist. Generate a positioning strategy for a seller report PDF.

PROPERTY:
- Address: {address}, {suburb}, QLD
- Configuration: {beds} bedrooms (actually 5 beds + study), {baths} bathrooms, {prop.get('carspaces', '?')} car
- Land: {land} sqm, Internal: {internal} sqm, 2-storey contemporary
- Condition: {condition}/10 — excellent. Hamptons-themed, pool, dual living, stone benchtops, butler's pantry
- Valuation: {reconciled} (range {val_range})
- Last sold: {last_sale} on {last_sale_date}
- Previous agent description: {desc}

COMPARABLE SALES (last 12 months):
{comp_text}

MARKET: {suburb} median house price {market_stats.get('median', 'N/A')}, {market_stats.get('houses_sold_12m', '?')} houses sold in 12 months, {market_stats.get('currently_listed', '?')} currently listed.

RULES:
- No advice language ("you should"). Frame as "we would" or "the data suggests".
- No forbidden words: stunning, nestled, boasting, rare opportunity, robust market.
- No predictions. Use conditional language.
- Price format: $1,250,000 not $1.25m.
- Be specific, cite data points, not vague.

Return a JSON object with these exact keys (all string values, 2-4 sentences each):
{{
  "buyer_profile": "Who the most likely buyers are and why this property appeals to them",
  "pricing_strategy": "How we would price this property and why, referencing the valuation range and comparable data",
  "key_selling_points": "The 4-5 strongest selling points, ordered by impact, with data backing",
  "marketing_approach": "How we would market this property — campaign structure, presentation strategy, open home approach",
  "market_assessment": "Current market conditions in {suburb} and what they mean for this property's sale timeline and outcome"
}}

Return ONLY valid JSON. No markdown, no code fences."""

    try:
        response = client.messages.create(
            model="claude-sonnet-4-20250514",
            max_tokens=1500,
            messages=[{"role": "user", "content": prompt}],
        )
        text = response.content[0].text.strip()
        # Strip markdown fences if present
        if text.startswith("```"):
            text = re.sub(r"^```\w*\n?", "", text)
            text = re.sub(r"\n?```$", "", text)
        return json.loads(text)
    except Exception as e:
        print(f"[WARN] Claude positioning failed: {e}")
        return _fallback_positioning(prop)


def _fallback_positioning(prop: dict) -> dict:
    """Fallback positioning if Claude is unavailable."""
    return {
        "buyer_profile": "The primary buyer for this property is a growing or established family seeking space, dual living capability, and a finished home that requires no further renovation. The 5-bedroom plus study configuration, pool, and entertainer's deck appeal to families with school-age children who value proximity to schools and amenities in the 4226 corridor.",
        "pricing_strategy": "Based on comparable-adjusted analysis, we would position this property in the range shown above. The limited number of comparable 5-bedroom homes in Merrimac means pricing precision is particularly important — we would recommend a specific, non-round price point at the top of the relevant portal search bracket to maximise buyer visibility.",
        "key_selling_points": "Five bedrooms plus study with dual living flexibility. Inground pool with glass fencing and 52.5 sqm entertainer's deck. Condition score of 9/10 — stone benchtops, butler's pantry, premium finishes throughout. 658 sqm block in a quiet cul-de-sac position.",
        "marketing_approach": "We would lead with the lifestyle and space story — this is a home for a family that wants to stop looking. Professional photography highlighting the pool-to-deck flow, the Hamptons-inspired kitchen, and the dual living potential. Open homes designed to end at the outdoor entertaining area (peak-end rule from behavioural research).",
        "market_assessment": "The current market shows moderate activity with limited premium stock available. The low volume of comparable sales in this price bracket and configuration means less direct competition, but also fewer reference points for buyers. Pricing transparency and data-backed positioning become the critical differentiator.",
    }


def download_photos(prop: dict, work_dir: Path) -> dict[str, str]:
    """Download property photos to local paths for the report."""
    photos_dir = work_dir / "photos"
    photos_dir.mkdir(exist_ok=True)

    images = prop.get("property_images", [])
    floorplans = prop.get("floor_plans", [])
    paths = {}

    photo_map = {
        "hero": 1,       # Pool/exterior
        "exterior": 1,   # Same as hero for this property
        "kitchen": 3,    # Kitchen
        "living": 7,     # Living room
        "aerial": 2,     # Aerial/drone
        "pool": 1,       # Pool shot
    }

    for name, idx in photo_map.items():
        if idx < len(images):
            local = photos_dir / f"{name}.jpg"
            try:
                urllib.request.urlretrieve(images[idx], str(local))
                paths[name] = str(local)
            except Exception as e:
                print(f"  [WARN] Failed to download {name}: {e}")
                paths[name] = ""
        else:
            paths[name] = ""

    if floorplans:
        local = photos_dir / "floorplan.jpg"
        try:
            urllib.request.urlretrieve(floorplans[0], str(local))
            paths["floorplan"] = str(local)
        except Exception:
            paths["floorplan"] = ""

    return paths


def render_html(prop: dict, client_name: str, comparables: list, market_stats: dict,
                positioning: dict, photo_paths: dict) -> str:
    """Render the HTML template with property data."""
    env = Environment(loader=FileSystemLoader(str(TEMPLATE_DIR)))
    template = env.get_template("seller_report.html")

    vd = prop.get("valuation_data", {}).get("confidence", {})
    reconciled = vd.get("reconciled_valuation", 0)
    range_low = vd.get("range", {}).get("low", 0)
    range_high = vd.get("range", {}).get("high", 0)

    dv = prop.get("domain_valuation_at_listing", {})
    fpa = prop.get("floor_plan_analysis", {})
    pvd = prop.get("property_valuation_data", {}).get("property_overview", {})

    last_sale_raw = prop.get("sale_price", "")
    last_sale_num = int(re.sub(r"[^\d]", "", str(last_sale_raw))) if last_sale_raw else 0
    growth = reconciled - last_sale_num if reconciled and last_sale_num else 0
    growth_pct = round(growth / last_sale_num * 100) if last_sale_num else 0

    # Corrected bedrooms (5 + study, not 6)
    actual_beds = 5

    # Key features
    key_features = [
        {"title": "Dual Living", "detail": "Separate living zones across two levels"},
        {"title": "Inground Pool", "detail": "Glass-fenced pool with landscaped surrounds"},
        {"title": "Entertainer's Deck", "detail": "52.5 m² covered outdoor entertaining"},
        {"title": "Hampton's Style", "detail": "Contemporary coastal finishes throughout"},
    ]

    # Confidence note
    confidence = vd.get("confidence", "low")
    if confidence == "low":
        confidence_note = (
            f"This valuation draws on a limited number of directly comparable sales. "
            f"Five-bedroom homes with this specification are uncommon in {prop.get('suburb', 'this suburb')}, "
            f"which reduces the pool of closely matched comparables. The range shown reflects this uncertainty. "
            f"We supplement with broader market data and property-specific adjustments to ensure the estimate "
            f"is grounded, but recommend treating the range — rather than the midpoint — as the primary indicator."
        )
    elif confidence == "medium":
        confidence_note = "This valuation is based on a moderate number of comparable sales with reasonable similarity to your property."
    else:
        confidence_note = "This valuation is supported by strong comparable evidence with high similarity to your property."

    # Layout summary
    layout_summary = (
        f"Two-storey layout with {actual_beds} bedrooms plus study across {fpa.get('total_floor_area', {}).get('value', 376)} m² total. "
        f"Upper level: open-plan kitchen, dining, and living flowing to a covered balcony ({fpa.get('internal_floor_area', {}).get('value', 221)} m² internal). "
        f"Ground floor: family room, media room, two bedrooms, bathroom, and laundry — configured as a self-contained dual living zone. "
        f"Double garage ({fpa.get('total_floor_area', {}).get('value', 376) - fpa.get('internal_floor_area', {}).get('value', 221) - 95} m²) "
        f"with internal access."
    )

    context = {
        "client_name": client_name,
        "report_date": datetime.now(AEST).strftime("%d %B %Y"),
        "address": prop.get("complete_address", ""),
        "street_address": prop.get("street_address", ""),
        "suburb": prop.get("suburb", ""),
        "postcode": prop.get("postcode", "4226"),
        "property_type": prop.get("property_type", "House"),
        "bedrooms": actual_beds,
        "has_study": True,
        "bedroom_detail": "5 bedrooms plus dedicated study/home office",
        "bathrooms": prop.get("bathrooms", 3),
        "carspaces": prop.get("carspaces", 4),
        "land_size": int(prop.get("land_size_sqm", 0)),
        "internal_area": fpa.get("internal_floor_area", {}).get("value", "—"),
        "external_area": 95,
        "total_area": fpa.get("total_floor_area", {}).get("value", 376),
        "condition_score": pvd.get("overall_condition_score", "9"),
        "condition_label": pvd.get("overall_condition", "Excellent").title(),
        "valuation_display": format_price(reconciled),
        "valuation_low_display": format_price(range_low),
        "valuation_high_display": format_price(range_high),
        "last_sale_price": format_price(last_sale_num) if last_sale_num else "N/A",
        "last_sale_date": prop.get("sold_date", ""),
        "capital_growth": f"+{format_price(growth)} ({growth_pct}%)" if growth > 0 else "N/A",
        "domain_mid_display": format_price(dv.get("mid", 0)),
        "domain_low_display": format_price(dv.get("low", 0)),
        "domain_high_display": format_price(dv.get("high", 0)),
        "key_features": key_features,
        "comparables": comparables,
        "confidence_note": confidence_note,
        "layout_summary": layout_summary,
        "research_stats": RESEARCH_STATS,
        "total_sold_tracked": TOTAL_SOLD_TRACKED,
        "suburb_median": market_stats.get("median", "N/A"),
        "houses_sold_12m": market_stats.get("houses_sold_12m", "—"),
        "currently_listed": market_stats.get("currently_listed", "—"),
        # Positioning
        "buyer_profile": positioning.get("buyer_profile", ""),
        "pricing_strategy": positioning.get("pricing_strategy", ""),
        "key_selling_points": positioning.get("key_selling_points", ""),
        "marketing_approach": positioning.get("marketing_approach", ""),
        "market_assessment": positioning.get("market_assessment", ""),
        # Photos (file:// paths for Chromium)
        "hero_photo": f"file://{photo_paths.get('hero', '')}",
        "exterior_photo": f"file://{photo_paths.get('exterior', '')}",
        "kitchen_photo": f"file://{photo_paths.get('kitchen', '')}",
        "living_photo": f"file://{photo_paths.get('living', '')}",
        "aerial_photo": f"file://{photo_paths.get('aerial', '')}",
        "pool_photo": f"file://{photo_paths.get('pool', '')}",
        "floorplan_photo": f"file://{photo_paths.get('floorplan', '')}",
    }

    return template.render(**context)


def html_to_pdf(html_path: str, pdf_path: str) -> bool:
    """Convert HTML to PDF using Chromium headless."""
    chrome = None
    for candidate in ["google-chrome", "chromium-browser", "chromium"]:
        try:
            subprocess.run([candidate, "--version"], capture_output=True, check=True)
            chrome = candidate
            break
        except (subprocess.CalledProcessError, FileNotFoundError):
            continue

    if not chrome:
        print("[ERROR] No Chrome/Chromium found")
        return False

    cmd = [
        chrome,
        "--headless",
        "--disable-gpu",
        "--no-sandbox",
        "--disable-software-rasterizer",
        f"--print-to-pdf={pdf_path}",
        "--print-to-pdf-no-header",
        "--run-all-compositor-stages-before-draw",
        "--virtual-time-budget=5000",
        f"file://{html_path}",
    ]

    result = subprocess.run(cmd, capture_output=True, text=True, timeout=60)
    if result.returncode != 0:
        print(f"[ERROR] Chrome PDF failed: {result.stderr[:500]}")
        return False
    return True


def main():
    parser = argparse.ArgumentParser(description="Generate Seller Position Report PDF")
    parser.add_argument("--address", required=True, help="Address substring to match")
    parser.add_argument("--client", required=True, help="Client name for the report")
    parser.add_argument("--suburb", required=True, help="Suburb collection name (e.g. merrimac)")
    parser.add_argument("--skip-ai", action="store_true", help="Skip Claude positioning, use fallback")
    parser.add_argument("--dry-run", action="store_true", help="Render HTML only, no PDF")
    args = parser.parse_args()

    print(f"Generating Seller Position Report")
    print(f"  Address: {args.address}")
    print(f"  Client: {args.client}")
    print(f"  Suburb: {args.suburb}")
    print()

    # Connect
    client = get_db()
    db_gc = client["Gold_Coast"]

    # Find property
    prop = find_property(client, args.suburb, args.address)
    if not prop:
        print(f"[ERROR] Property not found: '{args.address}' in {args.suburb}")
        sys.exit(1)
    print(f"  Found: {prop.get('complete_address') or prop.get('street_address')}")

    # Get comparables
    print("  Loading comparable sales...")
    comparables = get_sold_comparables(client, args.suburb, prop)
    print(f"  {len(comparables)} comparable sales found")

    # Market stats
    print("  Loading market stats...")
    market_stats = get_market_stats(client, args.suburb)
    print(f"  Median: {market_stats['median']}, Sold 12m: {market_stats['houses_sold_12m']}")

    # Download photos
    work_dir = Path(tempfile.mkdtemp(prefix="seller_report_"))
    print(f"  Downloading photos to {work_dir}...")
    photo_paths = download_photos(prop, work_dir)
    print(f"  {sum(1 for v in photo_paths.values() if v)} photos downloaded")

    # Generate positioning
    if args.skip_ai:
        print("  Using fallback positioning (--skip-ai)")
        positioning = _fallback_positioning(prop)
    else:
        print("  Generating positioning strategy via Claude...")
        positioning = generate_positioning_strategy(prop, comparables, market_stats)
    print("  Positioning ready")

    # Render HTML
    print("  Rendering HTML template...")
    html = render_html(prop, args.client, comparables, market_stats, positioning, photo_paths)

    html_path = work_dir / "report.html"
    html_path.write_text(html)
    print(f"  HTML saved: {html_path}")

    if args.dry_run:
        print(f"\n  [DRY RUN] Open {html_path} to preview")
        return

    # Convert to PDF
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    slug = args.address.lower().replace(" ", "-").replace(",", "")
    date_str = datetime.now(AEST).strftime("%Y-%m-%d")
    pdf_name = f"{date_str}_{slug}_{args.client.lower()}.pdf"
    pdf_path = OUTPUT_DIR / pdf_name

    print(f"  Converting to PDF...")
    if html_to_pdf(str(html_path), str(pdf_path)):
        size_kb = pdf_path.stat().st_size / 1024
        print(f"\n  PDF generated: {pdf_path}")
        print(f"  Size: {size_kb:.0f} KB")
    else:
        print(f"\n  [ERROR] PDF generation failed. HTML available at: {html_path}")


if __name__ == "__main__":
    main()
