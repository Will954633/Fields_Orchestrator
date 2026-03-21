#!/usr/bin/env python3
"""
scrape_sqm_asking_prices.py — Fetch weekly asking price data from SQM Research

Scrapes asking price charts for target postcodes from sqmresearch.com.au.
Data is embedded as a JSON array in the page's <script> block (Highcharts data).

Stores results in Gold_Coast.sqm_asking_prices collection, one document per suburb.

Usage:
    python3 scripts/scrape_sqm_asking_prices.py          # scrape + store all
    python3 scripts/scrape_sqm_asking_prices.py --dry-run # scrape only, don't write to DB

Schedule: weekly (data updates ~weekly on SQM)
"""

import argparse
import json
import os
import re
import sys
from datetime import datetime, timezone

import yaml
from curl_cffi import requests
from pymongo import MongoClient

# Postcode → suburb mapping (primary suburb for each postcode)
POSTCODE_MAP = {
    "4216": "robina",
    "4226": "burleigh_waters",
    "4227": "varsity_lakes",
}

# Display names for labelling
DISPLAY_NAMES = {
    "robina": "Robina",
    "burleigh_waters": "Burleigh Waters",
    "varsity_lakes": "Varsity Lakes",
}

# SQM postcodes cover wider areas — note this for transparency
POSTCODE_COVERAGE = {
    "4216": "Robina, Merrimac, Clear Island Waters",
    "4226": "Burleigh Waters, Burleigh Heads, Miami",
    "4227": "Varsity Lakes, Reedy Creek",
}


def load_mongo_uri():
    cfg_path = os.path.join(os.path.dirname(__file__), "..", "config", "settings.yaml")
    with open(cfg_path) as f:
        cfg = yaml.safe_load(f)
    return cfg["mongodb"]["uri"]


def scrape_postcode(postcode):
    """Fetch asking price data for a given postcode from SQM Research."""
    url = f"https://sqmresearch.com.au/property/asking-property-prices?postcode={postcode}"
    resp = requests.get(url, impersonate="chrome120", timeout=30)
    resp.raise_for_status()

    # Extract the inline data array from the Highcharts script
    scripts = re.findall(r"<script[^>]*>(.*?)</script>", resp.text, re.DOTALL)
    for script in scripts:
        match = re.search(r"var\s+data\s*=\s*(\[\{.*?\}\])\s*;", script, re.DOTALL)
        if match:
            data = json.loads(match.group(1))
            return data

    raise ValueError(f"No chart data found for postcode {postcode}")


def transform_data(raw_data):
    """Convert raw SQM data to our storage format."""
    points = []
    for row in raw_data:
        points.append({
            "date": row["date"],
            "houses_all": row.get("houses_all"),
            "houses_3bed": row.get("houses_3"),
            "units_all": row.get("units_all"),
            "units_2bed": row.get("units_2"),
            "combined": row.get("combined"),
        })
    return points


def main():
    parser = argparse.ArgumentParser(description="Scrape SQM Research asking prices")
    parser.add_argument("--dry-run", action="store_true", help="Don't write to MongoDB")
    args = parser.parse_args()

    uri = load_mongo_uri()
    client = MongoClient(uri)
    db = client["Gold_Coast"]
    collection = db["sqm_asking_prices"]

    results = {}
    for postcode, suburb_id in POSTCODE_MAP.items():
        print(f"Scraping {suburb_id} (postcode {postcode})...")
        try:
            raw = scrape_postcode(postcode)
            points = transform_data(raw)
            results[suburb_id] = {
                "postcode": postcode,
                "count": len(points),
                "first": points[0]["date"],
                "last": points[-1]["date"],
            }
            print(f"  → {len(points)} weekly data points ({points[0]['date']} to {points[-1]['date']})")

            if not args.dry_run:
                doc = {
                    "_id": suburb_id,
                    "suburb": DISPLAY_NAMES[suburb_id],
                    "postcode": postcode,
                    "postcode_coverage": POSTCODE_COVERAGE[postcode],
                    "source": "sqmresearch.com.au",
                    "metric": "asking_prices",
                    "frequency": "weekly",
                    "series": points,
                    "data_points": len(points),
                    "date_range_start": points[0]["date"],
                    "date_range_end": points[-1]["date"],
                    "last_updated": datetime.now(timezone.utc).isoformat(),
                }
                collection.replace_one({"_id": suburb_id}, doc, upsert=True)
                print(f"  → Stored in Gold_Coast.sqm_asking_prices")

        except Exception as e:
            print(f"  ✗ Error: {e}", file=sys.stderr)
            results[suburb_id] = {"error": str(e)}

    print(f"\nDone. {'(dry run — no DB writes)' if args.dry_run else ''}")
    for suburb, info in results.items():
        if "error" in info:
            print(f"  {suburb}: FAILED — {info['error']}")
        else:
            print(f"  {suburb}: {info['count']} points, {info['first']} → {info['last']}")

    client.close()


if __name__ == "__main__":
    main()
