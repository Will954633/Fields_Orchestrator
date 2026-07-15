#!/usr/bin/env python3
"""
fix_article_charts.py — Embed base64 charts into published articles that have broken image URLs.

Finds published articles in system_monitor.content_articles where <img> tags point to
dead Ghost CDN, broken fieldsestate.com.au/images/, or __CHART_*__ placeholders,
and replaces them with base64-encoded PNGs from the generated/ folders.
"""

import base64
import os
import re
import sys
from pathlib import Path
from bson import ObjectId
from pymongo import MongoClient
from dotenv import load_dotenv

load_dotenv("/home/fields/Fields_Orchestrator/.env")

GENERATED = Path("/home/fields/fields-automation/generated")

client = MongoClient(os.environ["COSMOS_CONNECTION_STRING"],
                     serverSelectionTimeoutMS=10000, retryWrites=False)
coll = client.system_monitor.content_articles


def b64_data_uri(png_path: Path) -> str:
    """Encode a PNG as a base64 data URI."""
    data = base64.b64encode(png_path.read_bytes()).decode("ascii")
    return f"data:image/png;base64,{data}"


# ---------------------------------------------------------------------------
# Mapping: article MongoDB _id → chart file locations on disk
# ---------------------------------------------------------------------------
# Format: { mongo_id: { "url_pattern_or_placeholder": "local_path_to_png" } }

ARTICLE_CHART_MAP = {
    # --- Is Now Good Time to BUY ---
    "69b0b51bb97b98bfc59392fd": {  # Buy Burleigh Waters
        "burleigh-waters-buy/chart_growth.png": GENERATED / "is_now_good_time/burleigh_waters/chart_growth.png",
        "burleigh-waters-buy/chart_volume.png": GENERATED / "is_now_good_time/burleigh_waters/chart_volume.png",
        "burleigh-waters-buy/chart_dom.png": GENERATED / "is_now_good_time/burleigh_waters/chart_dom.png",
    },
    "69b095431acf26181538572d": {  # Buy Robina (Ghost CDN URLs)
        "chart_growth": GENERATED / "is_now_good_time/robina/chart_growth.png",
        "chart_volume": GENERATED / "is_now_good_time/robina/chart_volume.png",
        "chart_dom": GENERATED / "is_now_good_time/robina/chart_dom.png",
    },
    "69b0b51bb97b98bfc59392fe": {  # Buy Varsity Lakes
        "varsity-lakes-buy/chart_growth.png": GENERATED / "is_now_good_time/varsity_lakes/chart_growth.png",
        "varsity-lakes-buy/chart_volume.png": GENERATED / "is_now_good_time/varsity_lakes/chart_volume.png",
        "varsity-lakes-buy/chart_dom.png": GENERATED / "is_now_good_time/varsity_lakes/chart_dom.png",
    },
    # --- Is Now Good Time to SELL ---
    "69b0b51bb97b98bfc59392ff": {  # Sell Burleigh Waters
        "burleigh-waters-sell/chart_price.png": GENERATED / "is_now_good_time_sell/burleigh_waters/chart_price.png",
        "burleigh-waters-sell/chart_dom_seasonal.png": GENERATED / "is_now_good_time_sell/burleigh_waters/chart_dom_seasonal.png",
        "burleigh-waters-sell/chart_supply.png": GENERATED / "is_now_good_time_sell/burleigh_waters/chart_supply.png",
    },
    "69b0b51bb97b98bfc5939300": {  # Sell Robina
        "robina-sell/chart_price.png": GENERATED / "is_now_good_time_sell/robina/chart_price.png",
        "robina-sell/chart_dom_seasonal.png": GENERATED / "is_now_good_time_sell/robina/chart_dom_seasonal.png",
        "robina-sell/chart_supply.png": GENERATED / "is_now_good_time_sell/robina/chart_supply.png",
    },
    "69b0b51bb97b98bfc5939301": {  # Sell Varsity Lakes
        "varsity-lakes-sell/chart_price.png": GENERATED / "is_now_good_time_sell/varsity_lakes/chart_price.png",
        "varsity-lakes-sell/chart_dom_seasonal.png": GENERATED / "is_now_good_time_sell/varsity_lakes/chart_dom_seasonal.png",
        "varsity-lakes-sell/chart_supply.png": GENERATED / "is_now_good_time_sell/varsity_lakes/chart_supply.png",
    },
    # --- Auction vs Private Treaty (Ghost CDN URLs) ---
    "69b095431acf26181538572e": {
        "chart_price_convergence": GENERATED / "auction_vs_pt_seller/visualizations/chart_price_convergence.png",
        "chart_adoption_rate": GENERATED / "auction_vs_pt_seller/visualizations/chart_adoption_rate.png",
        "chart_clearance_by_tier": GENERATED / "auction_vs_pt_seller/visualizations/chart_clearance_by_tier.png",
        "chart_clearance_annual": GENERATED / "auction_vs_pt_seller/visualizations/chart_clearance_annual.png",
    },
    # --- Robina Sales Volume Surges ---
    "69b0b51eb97b98bfc593930b": {
        "robina-volume-surge/chart_market_insight.png": GENERATED / "market_insight/2026-03-08_robina-volume-surge-supply-squeeze-2026-q1/chart_market_insight.png",
    },
}

# Also check: beach_distance and price_per_sqm might be missing 2nd charts
EXTRA_CHART_CHECK = {
    "69b11e84730ee5329e886fd8": {  # Beach Distance - should have 2 charts
        "charts": [
            GENERATED / "beach_distance_price_impact/visualizations/price_by_beach_distance.png",
            GENERATED / "beach_distance_price_impact/visualizations/beach_premium_curve.png",
        ],
    },
    "69b11e900c1b262f8d56a53d": {  # Price Per Sqm - should have 2 charts
        "charts": [
            GENERATED / "price_per_sqm_benchmarking/visualizations/psqm_by_lot_bucket.png",
            GENERATED / "price_per_sqm_benchmarking/visualizations/psqm_trend_by_year.png",
        ],
    },
}


def fix_article(mongo_id: str, chart_map: dict, dry_run: bool = False):
    """Replace broken image URLs with base64 data URIs in a published article."""
    doc = coll.find_one({"_id": ObjectId(mongo_id)}, {"title": 1, "html": 1, "status": 1})
    if not doc:
        print(f"  [NOT FOUND] {mongo_id}")
        return False

    html = doc.get("html", "")
    title = doc.get("title", "untitled")[:60]
    original_html = html
    replaced = 0

    for url_pattern, local_path in chart_map.items():
        if not local_path.exists():
            print(f"  ⚠️  Chart file missing: {local_path}")
            continue

        data_uri = b64_data_uri(local_path)

        # Strategy 1: Replace src attributes containing the URL pattern
        # Match <img src="...url_pattern...">
        def replace_src(m):
            nonlocal replaced
            src = m.group(1)
            if url_pattern in src:
                replaced += 1
                return f'src="{data_uri}"'
            return m.group(0)

        html = re.sub(r'src="([^"]*)"', replace_src, html)

    if replaced == 0:
        print(f"  [NO MATCH] {mongo_id} | {title} — no URL patterns matched")
        # Print current src values for debugging
        srcs = re.findall(r'src="([^"]{10,80})', html)
        for s in srcs[:5]:
            print(f"    current src: {s}")
        return False

    if dry_run:
        print(f"  [DRY RUN] {mongo_id} | {title} — would replace {replaced} chart(s)")
        return True

    # Update MongoDB
    coll.update_one(
        {"_id": ObjectId(mongo_id)},
        {"$set": {"html": html}}
    )
    print(f"  ✅ {mongo_id} | {title} — replaced {replaced} chart(s)")
    return True


def main():
    dry_run = "--dry-run" in sys.argv
    if dry_run:
        print("=== DRY RUN MODE ===\n")

    total = 0
    fixed = 0

    print("--- Fixing articles with broken chart URLs ---\n")
    for mongo_id, chart_map in ARTICLE_CHART_MAP.items():
        total += 1
        if fix_article(mongo_id, chart_map, dry_run):
            fixed += 1

    print(f"\n--- Fixed {fixed}/{total} articles ---")

    # Check the "already base64" articles for missing 2nd charts
    print("\n--- Checking articles that might be missing additional charts ---")
    for mongo_id, info in EXTRA_CHART_CHECK.items():
        doc = coll.find_one({"_id": ObjectId(mongo_id)}, {"title": 1, "html": 1})
        if not doc:
            continue
        html = doc.get("html", "")
        b64_count = html.count("data:image/png;base64")
        expected = len(info["charts"])
        title = doc.get("title", "")[:60]
        if b64_count < expected:
            print(f"  ⚠️  {mongo_id} | {title} — has {b64_count} charts, expected {expected}")
        else:
            print(f"  ✅ {mongo_id} | {title} — has {b64_count}/{expected} charts")


if __name__ == "__main__":
    main()
