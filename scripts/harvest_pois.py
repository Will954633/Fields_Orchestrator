#!/usr/bin/env python3
"""
harvest_pois.py — Fetch Points of Interest from Google Places API
and store them in Gold_Coast_POIs.pois collection.

Categories harvested:
  - supermarket (Woolworths, Coles, Aldi)
  - park (parks & green spaces)
  - childcare (day care / preschool)
  - primary_school
  - secondary_school (high school)
  - cafe

Usage:
  python3 scripts/harvest_pois.py              # harvest all suburbs + categories
  python3 scripts/harvest_pois.py --dry-run    # show what would be fetched
  python3 scripts/harvest_pois.py --stats      # show current POI counts
"""

import os
import sys
import json
import time
import math
import argparse
import requests
from datetime import datetime, timezone
from pymongo import MongoClient

# ---------------------------------------------------------------------------
# Config
# ---------------------------------------------------------------------------

API_KEY = os.environ.get("GOOGLE_PLACES_API_KEY", "")

# Suburb centroids and search radii (metres)
SUBURBS = {
    "robina":          {"lat": -28.0777, "lng": 153.3898, "radius": 4000},
    "burleigh_waters": {"lat": -28.0920, "lng": 153.4250, "radius": 3500},
    "varsity_lakes":   {"lat": -28.0890, "lng": 153.4050, "radius": 3500},
    "burleigh_heads":  {"lat": -28.0880, "lng": 153.4480, "radius": 2500},
    "mudgeeraba":      {"lat": -28.0830, "lng": 153.3660, "radius": 4000},
    "reedy_creek":     {"lat": -28.1100, "lng": 153.3800, "radius": 3500},
    "merrimac":        {"lat": -28.0560, "lng": 153.3830, "radius": 3000},
    "worongary":       {"lat": -28.0970, "lng": 153.3530, "radius": 3000},
    "carrara":         {"lat": -28.0230, "lng": 153.3660, "radius": 3500},
}

# Google Places Nearby Search categories
# Each entry: (our_category, google_type, optional keyword filter)
SEARCH_CONFIGS = [
    # Supermarkets — search by keyword to get specific chains
    ("supermarket", "supermarket", "Woolworths"),
    ("supermarket", "supermarket", "Coles"),
    ("supermarket", "supermarket", "Aldi"),
    # Parks & green spaces
    ("park", "park", None),
    # Childcare / preschool
    ("childcare", "school", "childcare"),
    ("childcare", "school", "preschool"),
    ("childcare", "school", "day care"),
    # Primary schools
    ("primary_school", "school", "primary school"),
    ("primary_school", "primary_school", None),
    # Secondary schools
    ("secondary_school", "school", "high school"),
    ("secondary_school", "secondary_school", None),
    # Cafes
    ("cafe", "cafe", None),
]

NEARBY_SEARCH_URL = "https://maps.googleapis.com/maps/api/place/nearbysearch/json"


def haversine_km(lat1, lng1, lat2, lng2):
    """Great-circle distance in km."""
    R = 6371.0
    dlat = math.radians(lat2 - lat1)
    dlng = math.radians(lng2 - lng1)
    a = math.sin(dlat / 2) ** 2 + math.cos(math.radians(lat1)) * math.cos(math.radians(lat2)) * math.sin(dlng / 2) ** 2
    return R * 2 * math.asin(math.sqrt(a))


def fetch_nearby(lat, lng, radius, place_type, keyword=None):
    """Call Google Places Nearby Search. Returns list of results."""
    params = {
        "location": f"{lat},{lng}",
        "radius": radius,
        "type": place_type,
        "key": API_KEY,
    }
    if keyword:
        params["keyword"] = keyword

    all_results = []
    while True:
        resp = requests.get(NEARBY_SEARCH_URL, params=params, timeout=15)
        resp.raise_for_status()
        data = resp.json()

        if data.get("status") not in ("OK", "ZERO_RESULTS"):
            print(f"  WARNING: API returned status={data.get('status')}: {data.get('error_message', '')}")
            break

        all_results.extend(data.get("results", []))

        # Follow pagination if available
        next_token = data.get("next_page_token")
        if next_token:
            time.sleep(2)  # Google requires ~2s delay before using next_page_token
            params = {"pagetoken": next_token, "key": API_KEY}
        else:
            break

    return all_results


def normalize_result(result, category, discovered_suburb):
    """Convert a Google Places result to our POI document format."""
    loc = result.get("geometry", {}).get("location", {})
    return {
        "place_id": result.get("place_id", ""),
        "name": result.get("name", ""),
        "poi_type": category,
        "latitude": loc.get("lat"),
        "longitude": loc.get("lng"),
        "address": result.get("vicinity", ""),
        "rating": result.get("rating"),
        "user_ratings_total": result.get("user_ratings_total", 0),
        "google_types": result.get("types", []),
        "business_status": result.get("business_status", ""),
        "discovered_in_suburb": discovered_suburb,
        "last_updated": datetime.now(timezone.utc),
    }


def main():
    parser = argparse.ArgumentParser(description="Harvest POIs from Google Places API")
    parser.add_argument("--dry-run", action="store_true", help="Show what would be fetched without writing")
    parser.add_argument("--stats", action="store_true", help="Show current POI counts and exit")
    parser.add_argument("--suburb", type=str, help="Only harvest for a specific suburb")
    parser.add_argument("--category", type=str, help="Only harvest a specific category")
    args = parser.parse_args()

    if not API_KEY:
        print("ERROR: GOOGLE_PLACES_API_KEY not set in environment")
        sys.exit(1)

    # Connect to MongoDB
    from dotenv import load_dotenv
    load_dotenv("/home/fields/Fields_Orchestrator/.env")
    conn_str = os.environ.get("COSMOS_CONNECTION_STRING", "")
    client = MongoClient(conn_str)
    db = client["Gold_Coast_POIs"]
    coll = db["pois"]

    if args.stats:
        total = coll.count_documents({})
        print(f"\nTotal POIs in database: {total}")
        pipeline = [{"$group": {"_id": "$poi_type", "count": {"$sum": 1}}}]
        for doc in coll.aggregate(pipeline):
            print(f"  {doc['_id']}: {doc['count']}")

        # By suburb
        pipeline2 = [{"$group": {"_id": "$discovered_in_suburb", "count": {"$sum": 1}}}]
        print("\nBy discovery suburb:")
        for doc in coll.aggregate(pipeline2):
            print(f"  {doc['_id']}: {doc['count']}")
        return

    suburbs_to_search = SUBURBS
    if args.suburb:
        if args.suburb not in SUBURBS:
            print(f"Unknown suburb: {args.suburb}. Available: {list(SUBURBS.keys())}")
            sys.exit(1)
        suburbs_to_search = {args.suburb: SUBURBS[args.suburb]}

    search_configs = SEARCH_CONFIGS
    if args.category:
        search_configs = [s for s in SEARCH_CONFIGS if s[0] == args.category]
        if not search_configs:
            cats = list(set(s[0] for s in SEARCH_CONFIGS))
            print(f"Unknown category: {args.category}. Available: {cats}")
            sys.exit(1)

    total_inserted = 0
    total_updated = 0
    total_skipped = 0
    seen_place_ids = set()

    for suburb_name, suburb_info in suburbs_to_search.items():
        print(f"\n{'='*60}")
        print(f"Suburb: {suburb_name} (centre: {suburb_info['lat']}, {suburb_info['lng']}, radius: {suburb_info['radius']}m)")
        print(f"{'='*60}")

        for category, place_type, keyword in search_configs:
            label = f"{category}" + (f" ({keyword})" if keyword else "")
            print(f"\n  Searching: {label} [type={place_type}]...")

            if args.dry_run:
                print(f"    [DRY RUN] Would search {NEARBY_SEARCH_URL} with type={place_type}, keyword={keyword}")
                continue

            results = fetch_nearby(
                suburb_info["lat"], suburb_info["lng"],
                suburb_info["radius"], place_type, keyword
            )
            print(f"    Found {len(results)} results")

            for r in results:
                pid = r.get("place_id", "")
                if not pid:
                    continue

                # Deduplicate within this run
                dedup_key = f"{pid}_{category}"
                if dedup_key in seen_place_ids:
                    total_skipped += 1
                    continue
                seen_place_ids.add(dedup_key)

                doc = normalize_result(r, category, suburb_name)

                # Filter out irrelevant results for specific searches
                name_lower = doc["name"].lower()

                # For supermarket keyword searches, verify the result is actually that chain
                if keyword in ("Woolworths", "Coles", "Aldi"):
                    if keyword.lower() not in name_lower:
                        total_skipped += 1
                        continue

                # Skip permanently closed businesses
                if doc["business_status"] == "CLOSED_PERMANENTLY":
                    total_skipped += 1
                    continue

                # Upsert by place_id + poi_type
                result = coll.update_one(
                    {"place_id": pid, "poi_type": category},
                    {"$set": doc},
                    upsert=True
                )
                if result.upserted_id:
                    total_inserted += 1
                elif result.modified_count:
                    total_updated += 1

            # Rate limit between searches
            time.sleep(0.3)

    print(f"\n{'='*60}")
    print(f"DONE — Inserted: {total_inserted}, Updated: {total_updated}, Skipped: {total_skipped}")
    print(f"{'='*60}")

    # Print final stats
    total = coll.count_documents({})
    print(f"\nTotal POIs now in database: {total}")
    pipeline = [{"$group": {"_id": "$poi_type", "count": {"$sum": 1}}}]
    for doc in coll.aggregate(pipeline):
        print(f"  {doc['_id']}: {doc['count']}")


if __name__ == "__main__":
    main()
