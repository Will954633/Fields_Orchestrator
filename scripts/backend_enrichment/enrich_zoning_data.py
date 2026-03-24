#!/usr/bin/env python3
"""
Enrich Zoning Data
==================
Queries Gold Coast City Council ArcGIS Feature Services to add zoning,
building height, minimum lot size, flood assessment, and residential
density data to each property document.

Data sources (free, no auth required):
  - City_Plan_Zoning: zone classification by LOT_PLAN
  - Building_height_v6: max height by coordinates
  - Minimum_lot_size: min subdivision lot size by coordinates
  - Residential_density: density classification by coordinates
  - Flood_assessment_required_v6: flood overlay by coordinates

Usage:
    python enrich_zoning_data.py                    # all target suburbs, missing only
    python enrich_zoning_data.py --suburb robina     # single suburb
    python enrich_zoning_data.py --address "27 Seville"  # single property
    python enrich_zoning_data.py --force             # re-enrich all
"""

from __future__ import annotations

import argparse
import os
import sys
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional

import requests
from pymongo import MongoClient

REPO_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO_ROOT))

from shared.ru_guard import cosmos_retry, sleep_with_jitter

TARGET_SUBURBS = ["robina", "varsity_lakes", "burleigh_waters"]

# ---------------------------------------------------------------------------
# ArcGIS Feature Service endpoints (Gold Coast City Council — public, no auth)
# ---------------------------------------------------------------------------

ARCGIS_BASE = "https://services.arcgis.com/3vStCH7NDoBOZ5zn/arcgis/rest/services"

SERVICES = {
    "zoning": f"{ARCGIS_BASE}/City_Plan_Zoning/FeatureServer/0/query",
    "building_height": f"{ARCGIS_BASE}/Building_height_v6/FeatureServer/0/query",
    "min_lot_size": f"{ARCGIS_BASE}/Minimum_lot_size/FeatureServer/0/query",
    "residential_density": f"{ARCGIS_BASE}/Residential_density/FeatureServer/0/query",
    "flood_assessment": f"{ARCGIS_BASE}/Flood_assessment_required_v6/FeatureServer/0/query",
    "heritage": f"{ARCGIS_BASE}/Heritage_Listed_Area/FeatureServer/0/query",
}

TIMEOUT = 15  # seconds per request


# ---------------------------------------------------------------------------
# Query helpers
# ---------------------------------------------------------------------------

def query_by_lot_plan(service_url: str, lot_plan: str, out_fields: str = "*") -> List[Dict]:
    """Query an ArcGIS service by LOT_PLAN attribute."""
    try:
        resp = requests.post(service_url, data={
            "where": f"LOT_PLAN='{lot_plan}'",
            "outFields": out_fields,
            "returnGeometry": "false",
            "f": "json",
        }, timeout=TIMEOUT)
        resp.raise_for_status()
        data = resp.json()
        return [f["attributes"] for f in data.get("features", [])]
    except Exception as e:
        print(f"    [WARN] LOT_PLAN query failed: {e}")
        return []


def query_by_point(service_url: str, lat: float, lng: float, out_fields: str = "*") -> List[Dict]:
    """Query an ArcGIS service by point-in-polygon spatial query."""
    geometry = f'{{"x":{lng},"y":{lat},"spatialReference":{{"wkid":4326}}}}'
    try:
        resp = requests.post(service_url, data={
            "geometry": geometry,
            "geometryType": "esriGeometryPoint",
            "spatialRel": "esriSpatialRelIntersects",
            "outFields": out_fields,
            "returnGeometry": "false",
            "f": "json",
        }, timeout=TIMEOUT)
        resp.raise_for_status()
        data = resp.json()
        return [f["attributes"] for f in data.get("features", [])]
    except Exception as e:
        print(f"    [WARN] Spatial query failed: {e}")
        return []


def get_centroid_from_zone(lot_plan: str) -> Optional[tuple]:
    """Get centroid coordinates from the zoning polygon for a lot/plan."""
    try:
        resp = requests.post(SERVICES["zoning"], data={
            "where": f"LOT_PLAN='{lot_plan}'",
            "outFields": "LOT_PLAN",
            "returnGeometry": "true",
            "outSR": "4326",
            "f": "json",
        }, timeout=TIMEOUT)
        resp.raise_for_status()
        data = resp.json()
        features = data.get("features", [])
        if not features:
            return None
        rings = features[0].get("geometry", {}).get("rings", [[]])
        if not rings or not rings[0]:
            return None
        xs = [p[0] for p in rings[0]]
        ys = [p[1] for p in rings[0]]
        return (sum(ys) / len(ys), sum(xs) / len(xs))  # (lat, lng)
    except Exception as e:
        print(f"    [WARN] Centroid lookup failed: {e}")
        return None


def batch_query_zoning(lot_plans: List[str]) -> Dict[str, Dict]:
    """Batch query zoning for up to 50 lot/plans at once."""
    if not lot_plans:
        return {}
    # ArcGIS IN clause
    in_clause = ",".join(f"'{lp}'" for lp in lot_plans)
    try:
        resp = requests.post(SERVICES["zoning"], data={
            "where": f"LOT_PLAN IN ({in_clause})",
            "outFields": "LVL1_ZONE,LVL2_ZONE,ZONE_PRECINCT,LOT_PLAN",
            "returnGeometry": "false",
            "f": "json",
        }, timeout=TIMEOUT * 2)
        resp.raise_for_status()
        data = resp.json()
        results = {}
        for f in data.get("features", []):
            attrs = f["attributes"]
            lp = attrs.get("LOT_PLAN", "")
            results[lp] = {
                "zone": attrs.get("LVL1_ZONE"),
                "zone_detail": attrs.get("LVL2_ZONE"),
                "zone_precinct": attrs.get("ZONE_PRECINCT"),
            }
        return results
    except Exception as e:
        print(f"    [WARN] Batch zoning query failed: {e}")
        return {}


# ---------------------------------------------------------------------------
# Main enrichment for a single property
# ---------------------------------------------------------------------------

def enrich_property_zoning(prop: Dict) -> Optional[Dict]:
    """Build zoning_data for a single property document."""
    # Construct LOT_PLAN
    lot = prop.get("LOT") or prop.get("cadastral_lot") or ""
    plan = prop.get("PLAN") or prop.get("cadastral_plan") or ""
    lot_plan = f"{lot}{plan}" if lot and plan else None

    if not lot_plan:
        return None

    result = {
        "lot_plan": lot_plan,
        "enriched_at": datetime.now(timezone.utc).isoformat(),
    }

    # 1. Zoning (by LOT_PLAN)
    zone_results = query_by_lot_plan(
        SERVICES["zoning"], lot_plan,
        "LVL1_ZONE,LVL2_ZONE,ZONE_PRECINCT,Shape__Area"
    )
    if zone_results:
        z = zone_results[0]
        result["zone"] = z.get("LVL1_ZONE")
        result["zone_detail"] = z.get("LVL2_ZONE")
        result["zone_precinct"] = z.get("ZONE_PRECINCT")
        result["cadastral_area_sqm"] = round(z.get("Shape__Area", 0), 1) if z.get("Shape__Area") else None

    # 2. Get coordinates for spatial queries
    lat = prop.get("latitude")
    lng = prop.get("longitude")
    if not lat or not lng:
        # Try to get centroid from zoning polygon
        centroid = get_centroid_from_zone(lot_plan)
        if centroid:
            lat, lng = centroid
            result["coordinates_source"] = "zone_centroid"
        else:
            # No coordinates available — can only do LOT_PLAN queries
            return result

    result["latitude"] = lat
    result["longitude"] = lng

    # 3. Building height (spatial)
    time.sleep(0.3)
    height_results = query_by_point(SERVICES["building_height"], lat, lng)
    if height_results:
        h = height_results[0]
        result["max_building_height_m"] = h.get("HEIGHT_IN_METRES") or h.get("MAX_HEIGHT")
        result["max_storeys"] = h.get("STOREY_NUMBER") or h.get("MAX_STOREYS")

    # 4. Minimum lot size (spatial)
    time.sleep(0.3)
    mls_results = query_by_point(SERVICES["min_lot_size"], lat, lng)
    if mls_results:
        m = mls_results[0]
        result["min_lot_size_sqm"] = m.get("MLS") or m.get("MIN_LOT_SIZE")

    # 5. Residential density (spatial)
    time.sleep(0.3)
    density_results = query_by_point(SERVICES["residential_density"], lat, lng)
    if density_results:
        d = density_results[0]
        result["residential_density"] = d.get("Residential_Density") or d.get("RES_DENSITY")

    # 6. Flood assessment (spatial)
    time.sleep(0.3)
    flood_results = query_by_point(SERVICES["flood_assessment"], lat, lng)
    if flood_results:
        result["flood_overlay"] = True
        result["flood_description"] = flood_results[0].get("OVL2_DESC")
    else:
        result["flood_overlay"] = False

    # 7. Heritage (spatial)
    time.sleep(0.3)
    heritage_results = query_by_point(SERVICES["heritage"], lat, lng)
    if heritage_results:
        result["heritage_listed"] = True
    else:
        result["heritage_listed"] = False

    # Derive subdivision potential
    if result.get("zone") and result.get("cadastral_area_sqm") and result.get("min_lot_size_sqm"):
        area = result["cadastral_area_sqm"]
        mls = result["min_lot_size_sqm"]
        if isinstance(mls, (int, float)) and mls > 0:
            potential_lots = int(area / mls)
            result["subdivision_potential_lots"] = potential_lots
            result["subdivision_possible"] = potential_lots >= 2

    return result


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main():
    parser = argparse.ArgumentParser(description="Enrich properties with zoning data from Gold Coast City Council")
    parser.add_argument("--address", help="Single property by address substring")
    parser.add_argument("--suburb", help="Single suburb")
    parser.add_argument("--force", action="store_true", help="Re-enrich even if zoning_data exists")
    parser.add_argument("--new-listings", action="store_true", help="Only process listings <=7 days old")
    parser.add_argument("--days", type=int, default=7, help="Days threshold for --new-listings")
    parser.add_argument("--dry-run", action="store_true", help="Show what would be enriched")
    args = parser.parse_args()

    conn_str = os.environ.get("COSMOS_CONNECTION_STRING")
    if not conn_str:
        print("[ERROR] No COSMOS_CONNECTION_STRING")
        sys.exit(1)

    client = MongoClient(conn_str)
    db = client["Gold_Coast"]

    if args.address:
        # Single property
        for suburb in TARGET_SUBURBS:
            doc = db[suburb].find_one({
                "address": {"$regex": args.address, "$options": "i"},
                "listing_status": "for_sale",
            })
            if doc:
                print(f"Found: {doc.get('address')} in {suburb}")
                result = enrich_property_zoning(doc)
                if result:
                    print(f"\n=== ZONING DATA ===")
                    for k, v in result.items():
                        print(f"  {k}: {v}")
                    if not args.dry_run:
                        cosmos_retry(
                            lambda: db[suburb].update_one(
                                {"_id": doc["_id"]},
                                {"$set": {"zoning_data": result}}
                            ),
                            "store_zoning"
                        )
                        print(f"\n[OK] Stored zoning_data")
                else:
                    print("[WARN] Could not enrich — missing LOT/PLAN")
                client.close()
                return
        print(f"[ERROR] No active listing matching '{args.address}'")
        client.close()
        return

    # Batch mode
    suburbs = [args.suburb] if args.suburb else TARGET_SUBURBS
    total = 0

    for suburb in suburbs:
        query = {"listing_status": "for_sale"}
        if not args.force:
            query["zoning_data"] = {"$exists": False}
        if args.new_listings:
            query["days_on_domain"] = {"$lte": args.days}

        props = cosmos_retry(
            lambda s=suburb: list(db[s].find(query, {
                "address": 1, "LOT": 1, "PLAN": 1, "cadastral_lot": 1,
                "cadastral_plan": 1, "latitude": 1, "longitude": 1,
            })),
            f"list_{suburb}"
        )
        if not props:
            continue

        print(f"\n{suburb}: {len(props)} properties to enrich")

        # Batch zoning query first (faster than individual)
        lot_plans = []
        lp_to_id = {}
        for p in props:
            lot = p.get("LOT") or p.get("cadastral_lot") or ""
            plan = p.get("PLAN") or p.get("cadastral_plan") or ""
            lp = f"{lot}{plan}"
            if lot and plan:
                lot_plans.append(lp)
                lp_to_id[lp] = p["_id"]

        # Batch in groups of 50
        batch_zones = {}
        for i in range(0, len(lot_plans), 50):
            batch = lot_plans[i:i+50]
            batch_zones.update(batch_query_zoning(batch))
            time.sleep(0.5)

        print(f"  Batch zoning: {len(batch_zones)}/{len(lot_plans)} matched")

        for prop in props:
            address = prop.get("address", "?")
            if args.dry_run:
                print(f"  [DRY] {address}")
                total += 1
                continue

            result = enrich_property_zoning(prop)
            if not result:
                print(f"  [SKIP] {address} — no LOT/PLAN")
                continue

            try:
                cosmos_retry(
                    lambda p=prop, r=result: db[suburb].update_one(
                        {"_id": p["_id"]},
                        {"$set": {"zoning_data": r}}
                    ),
                    "store_zoning"
                )
                zone = result.get("zone", "?")
                flood = "FLOOD" if result.get("flood_overlay") else ""
                subdiv = f"subdiv={result.get('subdivision_potential_lots', '?')}" if result.get("subdivision_possible") else ""
                print(f"  [OK] {address}: {zone} {flood} {subdiv}")
                total += 1
                sleep_with_jitter(0.3)
            except Exception as e:
                print(f"  [ERROR] {address}: {e}")

    print(f"\nDone. Enriched {total} properties.")
    client.close()


if __name__ == "__main__":
    main()
