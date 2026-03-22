#!/usr/bin/env python3
"""
enrich_property_pois.py — Calculate nearest POI distances for each property.

Reads POIs from Gold_Coast_POIs.pois, calculates haversine distances from each
active listing's coordinates, and writes a `nearby_pois` field on the property
document in Gold_Coast.<suburb>.

No external API calls — pure math against the POI database.

Usage:
  python3 scripts/enrich_property_pois.py              # enrich all active listings
  python3 scripts/enrich_property_pois.py --suburb robina
  python3 scripts/enrich_property_pois.py --dry-run    # show what would be written
  python3 scripts/enrich_property_pois.py --stats      # show enrichment coverage
"""

import os
import sys
import math
import re
import time
import argparse
from datetime import datetime, timezone
from pymongo import MongoClient
from pymongo.errors import OperationFailure

# ---------------------------------------------------------------------------
# Config
# ---------------------------------------------------------------------------

TARGET_SUBURBS = [
    "robina", "burleigh_waters", "varsity_lakes",
    "burleigh_heads", "mudgeeraba", "reedy_creek",
    "merrimac", "worongary", "carrara",
]

# Which POI categories to include, and how many nearest to keep per category
CATEGORY_CONFIG = {
    "supermarket":      {"label": "Supermarket",       "keep": 3},  # nearest Woolworths, Coles, Aldi
    "park":             {"label": "Park",               "keep": 2},
    "childcare":        {"label": "Childcare",          "keep": 2},
    "primary_school":   {"label": "Primary School",     "keep": 2},
    "secondary_school": {"label": "Secondary School",   "keep": 2},
    "cafe":             {"label": "Cafe",               "keep": 3},
}

# Max distance (km) — POIs beyond this are not relevant
MAX_DISTANCE_KM = 15.0


def haversine_km(lat1, lng1, lat2, lng2):
    """Great-circle distance in km."""
    R = 6371.0
    dlat = math.radians(lat2 - lat1)
    dlng = math.radians(lng2 - lng1)
    a = (math.sin(dlat / 2) ** 2 +
         math.cos(math.radians(lat1)) * math.cos(math.radians(lat2)) *
         math.sin(dlng / 2) ** 2)
    return R * 2 * math.asin(math.sqrt(a))


def compute_nearby_pois(prop_lat, prop_lng, all_pois):
    """
    Given a property's coordinates and all POIs, return a structured
    nearby_pois dict with nearest POIs per category.
    """
    # Group POIs by category with distances
    category_distances = {}
    for poi in all_pois:
        poi_lat = poi.get("latitude")
        poi_lng = poi.get("longitude")
        if poi_lat is None or poi_lng is None:
            continue

        dist_km = haversine_km(prop_lat, prop_lng, poi_lat, poi_lng)
        if dist_km > MAX_DISTANCE_KM:
            continue

        cat = poi.get("poi_type", "unknown")
        if cat not in CATEGORY_CONFIG:
            continue

        if cat not in category_distances:
            category_distances[cat] = []

        category_distances[cat].append({
            "name": poi.get("name", ""),
            "distance_km": round(dist_km, 2),
            "distance_m": round(dist_km * 1000),
            "address": poi.get("address", ""),
            "rating": poi.get("rating"),
            "user_ratings_total": poi.get("user_ratings_total", 0),
            "place_id": poi.get("place_id", ""),
            "latitude": poi_lat,
            "longitude": poi_lng,
        })

    # Sort each category by distance, keep top N
    result = {}
    summary = {
        "total_within_1km": 0,
        "total_within_2km": 0,
        "closest_supermarket_km": None,
        "closest_school_km": None,
        "closest_park_km": None,
        "closest_cafe_km": None,
        "closest_childcare_km": None,
    }

    walkable = []     # < 1km
    short_drive = []  # 1-3km
    nearby = []       # 3-10km

    for cat, config in CATEGORY_CONFIG.items():
        items = category_distances.get(cat, [])
        items.sort(key=lambda x: x["distance_km"])
        top = items[:config["keep"]]
        result[cat] = top

        # Update summary
        for item in items:
            d = item["distance_km"]
            if d <= 1.0:
                summary["total_within_1km"] += 1
            if d <= 2.0:
                summary["total_within_2km"] += 1

        if top:
            closest = top[0]["distance_km"]
            if cat == "supermarket":
                summary["closest_supermarket_km"] = closest
            elif cat in ("primary_school", "secondary_school"):
                if summary["closest_school_km"] is None or closest < summary["closest_school_km"]:
                    summary["closest_school_km"] = closest
            elif cat == "park":
                summary["closest_park_km"] = closest
            elif cat == "cafe":
                summary["closest_cafe_km"] = closest
            elif cat == "childcare":
                summary["closest_childcare_km"] = closest

        # Classify into distance tiers
        for item in top:
            entry = {
                "name": item["name"],
                "category": config["label"],
                "distance_km": item["distance_km"],
                "distance_m": item["distance_m"],
                "rating": item.get("rating"),
            }
            d = item["distance_km"]
            if d <= 1.0:
                walkable.append(entry)
            elif d <= 3.0:
                short_drive.append(entry)
            else:
                nearby.append(entry)

    # Sort tiers by distance
    walkable.sort(key=lambda x: x["distance_km"])
    short_drive.sort(key=lambda x: x["distance_km"])
    nearby.sort(key=lambda x: x["distance_km"])

    return {
        "by_category": result,
        "walkable": walkable,
        "short_drive": short_drive,
        "nearby": nearby,
        "summary": summary,
        "enriched_at": datetime.now(timezone.utc),
    }


def cosmos_retry(fn, max_retries=5):
    """Retry a callable on Cosmos DB 429 (TooManyRequests)."""
    for attempt in range(max_retries):
        try:
            return fn()
        except OperationFailure as e:
            if e.code == 16500:
                # Parse RetryAfterMs from error message
                match = re.search(r"RetryAfterMs=(\d+)", str(e))
                wait_ms = int(match.group(1)) if match else 500
                wait_s = max(wait_ms / 1000.0, 0.5)
                if attempt < max_retries - 1:
                    time.sleep(wait_s * (1.5 ** attempt))
                    continue
            raise


def main():
    parser = argparse.ArgumentParser(description="Enrich properties with nearest POI distances")
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--stats", action="store_true")
    parser.add_argument("--suburb", type=str)
    parser.add_argument("--limit", type=int, default=0, help="Limit properties to process")
    args = parser.parse_args()

    from dotenv import load_dotenv
    load_dotenv("/home/fields/Fields_Orchestrator/.env")
    conn_str = os.environ.get("COSMOS_CONNECTION_STRING", "")
    client = MongoClient(conn_str)

    # Load all POIs into memory in batches to avoid Cosmos RU throttling
    poi_db = client["Gold_Coast_POIs"]
    poi_projection = {"name": 1, "poi_type": 1, "latitude": 1, "longitude": 1,
                      "address": 1, "rating": 1, "user_ratings_total": 1, "place_id": 1}
    all_pois = []
    for poi_type in CATEGORY_CONFIG.keys():
        retries = 0
        while retries < 5:
            try:
                cursor = poi_db["pois"].find({"poi_type": poi_type}, poi_projection).batch_size(50)
                batch = []
                for doc in cursor:
                    batch.append(doc)
                all_pois.extend(batch)
                print(f"  Loaded {len(batch)} {poi_type} POIs")
                break
            except OperationFailure as e:
                if e.code == 16500:
                    retries += 1
                    wait = 2 * retries
                    print(f"  Rate limited loading {poi_type}, waiting {wait}s (attempt {retries}/5)")
                    time.sleep(wait)
                else:
                    raise
        time.sleep(0.5)  # Rate limit between categories
    print(f"Loaded {len(all_pois)} POIs from Gold_Coast_POIs.pois")

    if len(all_pois) == 0:
        print("ERROR: No POIs in database. Run harvest_pois.py first.")
        sys.exit(1)

    gold_coast = client["Gold_Coast"]

    suburbs = [args.suburb] if args.suburb else TARGET_SUBURBS

    if args.stats:
        for suburb in suburbs:
            coll = gold_coast[suburb]
            total = cosmos_retry(lambda: coll.count_documents({"listing_status": "for_sale"}))
            enriched = cosmos_retry(lambda: coll.count_documents({"listing_status": "for_sale", "nearby_pois": {"$exists": True}}))
            print(f"  {suburb}: {enriched}/{total} enriched")
        return

    total_enriched = 0
    total_skipped = 0
    total_no_coords = 0

    for suburb in suburbs:
        coll = gold_coast[suburb]
        # Fetch only _id, address, lat, lng to reduce RU consumption
        query = {"listing_status": "for_sale"}
        projection = {"_id": 1, "address": 1, "full_address": 1, "latitude": 1, "longitude": 1, "LATITUDE": 1, "LONGITUDE": 1}
        props = cosmos_retry(lambda: list(coll.find(query, projection)))
        print(f"\n{suburb}: {len(props)} active listings")

        if args.limit:
            props = props[:args.limit]

        for prop in props:
            address = prop.get("address", prop.get("full_address", "unknown"))
            # Support both lowercase (scraped) and uppercase (cadastral) coordinate fields
            lat = prop.get("latitude") or prop.get("LATITUDE")
            lng = prop.get("longitude") or prop.get("LONGITUDE")
            # Convert string coords to float if needed
            if isinstance(lat, str):
                try: lat = float(lat)
                except: lat = None
            if isinstance(lng, str):
                try: lng = float(lng)
                except: lng = None

            if lat is None or lng is None:
                print(f"  SKIP (no coords): {address}")
                total_no_coords += 1
                continue

            nearby = compute_nearby_pois(lat, lng, all_pois)

            if args.dry_run:
                s = nearby["summary"]
                print(f"  {address}")
                print(f"    Within 1km: {s['total_within_1km']}, Within 2km: {s['total_within_2km']}")
                print(f"    Nearest supermarket: {s['closest_supermarket_km']}km")
                print(f"    Nearest school: {s['closest_school_km']}km")
                print(f"    Nearest park: {s['closest_park_km']}km")
                total_enriched += 1
                continue

            cosmos_retry(lambda: coll.update_one(
                {"_id": prop["_id"]},
                {"$set": {"nearby_pois": nearby}}
            ))
            total_enriched += 1
            # Throttle writes to stay within Cosmos RU limits
            time.sleep(0.3)

        print(f"  {suburb}: enriched {len([p for p in props if p.get('latitude')])} properties")

    print(f"\n{'='*60}")
    print(f"DONE — Enriched: {total_enriched}, No coords: {total_no_coords}")
    print(f"{'='*60}")


if __name__ == "__main__":
    main()
