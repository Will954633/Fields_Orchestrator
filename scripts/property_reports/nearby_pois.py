"""
nearby_pois.py — nearest-POI-per-category lookup against the pre-harvested
Google Places dataset (`Gold_Coast_POIs.pois`, built by scripts/harvest_pois.py).

Pure local haversine against an in-process cache of the (small, static)
harvested collection — no external API calls, same latency profile as
compute_georeference() in on_demand_valuation.py, but built on real harvested
POIs (~790 places, 9 suburbs) instead of a hand-typed list of ~8 landmarks.
Cross-validated against live OSM + Mapbox routing on 2026-07-23 (see
logs/fix-history) — equal or better accuracy, without the Overpass rate-limit
and 100s+ latency risk of live per-property lookups.

Usage:
    from scripts.property_reports.nearby_pois import resolve_nearby_pois
    pois = resolve_nearby_pois(lat, lon, gc_db)   # gc_db = client["Gold_Coast"]
"""
import json
import math
import os
import urllib.request

_CACHE = {}  # poi_type -> list of {name, latitude, longitude} — cached per-process

CATEGORIES = [
    "primary_school", "secondary_school", "childcare",
    "supermarket", "park", "cafe", "beach", "train_station",
]


def _haversine_km(lat1, lon1, lat2, lon2):
    r = 6371.0
    p1, p2 = math.radians(lat1), math.radians(lat2)
    dlat = math.radians(lat2 - lat1)
    dlon = math.radians(lon2 - lon1)
    a = math.sin(dlat / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(dlon / 2) ** 2
    return r * 2 * math.asin(math.sqrt(a))


def _load_category(gc_db, poi_type):
    if poi_type not in _CACHE:
        coll = gc_db.client["Gold_Coast_POIs"]["pois"]
        _CACHE[poi_type] = list(coll.find(
            {"poi_type": poi_type},
            {"name": 1, "latitude": 1, "longitude": 1, "_id": 0},
        ))
    return _CACHE[poi_type]


def resolve_nearby_pois(lat, lon, gc_db, categories=None):
    """Nearest POI per category (straight-line km), sourced from the
    pre-harvested Google Places dataset. Returns {} if lat/lon missing."""
    if lat is None or lon is None:
        return {}
    out = {}
    for cat in (categories or CATEGORIES):
        items = _load_category(gc_db, cat)
        best, best_km = None, None
        for it in items:
            plat, plon = it.get("latitude"), it.get("longitude")
            if plat is None or plon is None:
                continue
            d = _haversine_km(lat, lon, plat, plon)
            if best_km is None or d < best_km:
                best, best_km = it, d
        if best is not None:
            out[cat] = {
                "name": best["name"],
                "distance_km": round(best_km, 2),
                "distance_m": int(round(best_km * 1000)),
                "latitude": best.get("latitude"),
                "longitude": best.get("longitude"),
            }
    return out


# Category -> the "category" string positioning_object.py / scarcity_narrative.py
# expect (matches walking_distances.py's original POI_CATEGORIES vocabulary).
# Beach excluded — scarcity_narrative handles beach proximity via its own
# near-beach anchor, not the walkable-differentiator phrase. Cafe excluded —
# not in scarcity_narrative's WALKABLE_CATEGORIES.
_WALKABLE_CATEGORY_MAP = {
    "primary_school": "school",
    "secondary_school": "school",
    "childcare": "childcare",
    "supermarket": "shops",
    "park": "park",
    "train_station": "station",
}
# Straight-line prefilter — only bother routing candidates plausibly within
# scarcity_narrative's 1000m walkable ceiling (buffered, since a real route is
# never shorter than straight-line).
_ROUTE_CHECK_CEILING_M = 1200
MAPBOX_DIRECTIONS_URL = "https://api.mapbox.com/directions/v5/mapbox/walking"


def _real_walk_metres(from_lat, from_lon, to_lat, to_lon, token):
    url = (
        f"{MAPBOX_DIRECTIONS_URL}/{from_lon},{from_lat};{to_lon},{to_lat}"
        f"?overview=false&access_token={token}"
    )
    try:
        req = urllib.request.Request(url, headers={"User-Agent": "Fields-Off-Market/1.0"})
        with urllib.request.urlopen(req, timeout=8) as resp:
            data = json.loads(resp.read().decode("utf-8"))
        routes = data.get("routes") or []
        return int(routes[0]["distance"]) if routes else None
    except Exception:
        return None


def to_walking_poi_list(proximity, subject_lat, subject_lon, mapbox_token=None):
    """Convert resolve_nearby_pois()'s straight-line proximity dict into the
    {name, category, walkMetres} shape positioning_object.py / scarcity_narrative.py
    expect — with REAL routed walking distance, not straight-line, for every
    candidate returned. Only candidates plausibly within walking range get a
    (single, targeted) Mapbox Directions call; anything the route pushes over
    the walkable ceiling, or that Mapbox can't route, is dropped rather than
    shown with an unverified distance. Intended for the decoupled, cached-once
    narrative path — NOT the fast per-pageview intel path (adds real latency).
    """
    token = mapbox_token or os.environ.get("MAPBOX_TOKEN") or os.environ.get("VITE_MAPBOX_TOKEN")
    if not token or subject_lat is None or subject_lon is None:
        return []
    out = []
    seen = set()
    for cat, entry in (proximity or {}).items():
        mapped = _WALKABLE_CATEGORY_MAP.get(cat)
        if not mapped or entry.get("distance_m") is None or entry["distance_m"] > _ROUTE_CHECK_CEILING_M:
            continue
        dedupe_key = (entry["name"], mapped)
        if dedupe_key in seen:
            continue
        walk_m = _real_walk_metres(subject_lat, subject_lon, entry.get("latitude"), entry.get("longitude"), token) \
            if entry.get("latitude") is not None else None
        if walk_m is None:
            continue
        seen.add(dedupe_key)
        out.append({"name": entry["name"], "category": mapped, "walkMetres": walk_m})
    return out
