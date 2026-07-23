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
import math

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
            }
    return out
