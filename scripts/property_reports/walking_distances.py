"""
Walking distance resolver — finds the nearest school, supermarket, park, and
beach from the subject property and computes walking distance to each.

Architecture:
  - POI lookup: OpenStreetMap Overpass API (free, structured POI data)
  - Walking route: Mapbox Directions API (paid, actual route distance)

Mapbox Geocoding was unsuitable for POI search — it returns streets that
contain a keyword (e.g. "School Road") rather than actual school buildings.
OSM has dedicated tags (`amenity=school`, `shop=supermarket`, `leisure=park`,
`natural=beach`) that match what we want.

Output schema (matches the frontend `Poi` type in homeFixture.ts):
    [
      {"name": "All Saints Anglican School", "category": "school",
       "walkMetres": 387, "lat": ..., "lng": ...},
      ...
    ]

Usage:
    from scripts.property_reports.walking_distances import resolve_pois
    pois = resolve_pois(lat, lng)
"""
from __future__ import annotations

import json
import logging
import math
import os
import urllib.parse
import urllib.request
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)


OVERPASS_ENDPOINTS = [
    "https://overpass-api.de/api/interpreter",
    "https://overpass.kumi.systems/api/interpreter",
    "https://overpass.openstreetmap.ru/api/interpreter",
]
OVERPASS_RETRY_BACKOFF = [1, 3]  # short backoffs — keep total resolver time under control
MAPBOX_DIRECTIONS = "https://api.mapbox.com/directions/v5/mapbox/walking"
MAPBOX_DRIVING = "https://api.mapbox.com/directions/v5/mapbox/driving"

# Global circuit breaker — if we detect 'network unreachable' or DNS failure,
# stop trying further endpoints / retries for this resolution. Avoids the
# 6-minute worst-case where every Overpass query exhausts all mirrors.
NETWORK_DEAD_PATTERNS = ["network is unreachable", "name or service not known", "temporary failure in name resolution"]

# OSM tag queries per category. The category string in the output matches
# the frontend Poi.category enum.
POI_CATEGORIES = [
    {
        "key": "primary_school",
        "category": "school",
        "label": "Nearest primary school",
        "filter": '["amenity"="school"]["isced:level"~"^1"]',
        "fallback_filter": '["amenity"="school"]',
        "radius_m": 3000,
        "limit": 1,
    },
    {
        "key": "secondary_school",
        "category": "school",
        "label": "Nearest secondary school",
        "filter": '["amenity"="school"]["isced:level"~"^[23]"]',
        "fallback_filter": None,  # primary fallback already covers schools
        "radius_m": 5000,
        "limit": 1,
    },
    {
        "key": "supermarket",
        "category": "shops",
        "label": "Nearest supermarket",
        "filter": '["shop"="supermarket"]',
        "fallback_filter": None,
        "radius_m": 3000,
        "limit": 1,
    },
    {
        "key": "park",
        "category": "park",
        "label": "Nearest park / reserve",
        "filter": '["leisure"="park"]',
        "fallback_filter": '["leisure"~"^(garden|nature_reserve|park)$"]',
        "radius_m": 2000,
        "limit": 1,
    },
    {
        "key": "childcare",
        "category": "childcare",
        "label": "Nearest childcare / kindergarten",
        # OSM tags childcare under amenity=childcare; kindergartens vary
        # (amenity=kindergarten, sometimes school with isced:level 0).
        "filter": '["amenity"="childcare"]',
        "fallback_filter": '["amenity"~"^(kindergarten|childcare)$"]',
        "radius_m": 2000,
        "limit": 1,
    },
    {
        "key": "train_station",
        "category": "station",
        "label": "Nearest train station",
        # Heavy-rail stations only (railway=station). The southern Gold Coast
        # line serves Robina and Varsity Lakes; exclude tram_stop/halt which
        # aren't relevant to these suburbs and would add noise.
        "filter": '["railway"="station"]["station"!="subway"]',
        "fallback_filter": '["railway"="station"]',
        "radius_m": 4000,
        "limit": 1,
    },
    {
        "key": "beach",
        "category": "beach",
        "label": "Nearest beach",
        "filter": '["natural"="beach"]',
        "fallback_filter": None,
        "radius_m": 15000,  # Gold Coast properties up to 15km from coast
        "limit": 1,
    },
]

MAX_WALK_METRES = 8000  # cap walking distance — anything further isn't really "walkable"
WALKABLE_THRESHOLD_M = 1000  # at/under this is a genuine walk (~12 min); beyond is a "short drive"


def _http_get(url: str, timeout: float = 12.0) -> Optional[bytes]:
    try:
        req = urllib.request.Request(url, headers={"User-Agent": "Fields-Mini-Site/1.0"})
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            if resp.status >= 400:
                logger.warning(f"HTTP {resp.status}: {url[:100]}")
                return None
            return resp.read()
    except Exception as e:
        logger.warning(f"HTTP request failed: {e}")
        return None


def _http_post_overpass(query: str, timeout: float = 12.0) -> Optional[Dict[str, Any]]:
    """POST a query to Overpass. Tries multiple mirrors and retries on 5xx /
    timeouts. Tighter timeout (12s) + shorter backoff than Day 6 to keep
    total resolver wall-time under ~90 seconds in the worst case. Network-dead
    patterns short-circuit the whole retry tree."""
    data = urllib.parse.urlencode({"data": query}).encode("utf-8")
    last_err: Optional[str] = None

    for endpoint in OVERPASS_ENDPOINTS:
        for attempt in range(len(OVERPASS_RETRY_BACKOFF) + 1):
            try:
                req = urllib.request.Request(
                    endpoint,
                    data=data,
                    headers={
                        "User-Agent": "Fields-Mini-Site/1.0",
                        "Content-Type": "application/x-www-form-urlencoded",
                    },
                )
                with urllib.request.urlopen(req, timeout=timeout) as resp:
                    if resp.status >= 500:
                        last_err = f"{endpoint} HTTP {resp.status}"
                        if attempt < len(OVERPASS_RETRY_BACKOFF):
                            import time
                            time.sleep(OVERPASS_RETRY_BACKOFF[attempt])
                            continue
                        break
                    if resp.status >= 400:
                        last_err = f"{endpoint} HTTP {resp.status}"
                        return None
                    return json.loads(resp.read().decode("utf-8"))
            except Exception as e:
                err_str = str(e).lower()
                last_err = f"{endpoint}: {e}"
                # Circuit breaker — network is dead, skip all remaining retries
                if any(pat in err_str for pat in NETWORK_DEAD_PATTERNS):
                    logger.warning(f"Overpass network unreachable — aborting all retries: {last_err}")
                    return None
                if attempt < len(OVERPASS_RETRY_BACKOFF):
                    import time
                    time.sleep(OVERPASS_RETRY_BACKOFF[attempt])
                    continue
                break
        logger.warning(f"Overpass endpoint exhausted: {last_err}")

    logger.warning(f"Overpass all endpoints failed: {last_err}")
    return None


def _haversine_metres(lat1: float, lng1: float, lat2: float, lng2: float) -> int:
    R = 6371000.0
    p1 = math.radians(lat1)
    p2 = math.radians(lat2)
    dp = math.radians(lat2 - lat1)
    dl = math.radians(lng2 - lng1)
    a = math.sin(dp / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(dl / 2) ** 2
    c = 2 * math.atan2(math.sqrt(a), math.sqrt(1 - a))
    return int(R * c)


def _overpass_nearest(lat: float, lng: float, filter_clause: str, radius_m: int, limit: int = 5) -> List[Dict[str, Any]]:
    """Return up to `limit` POIs of the given filter, sorted by straight-line distance asc."""
    query = (
        "[out:json][timeout:20];"
        "("
        f'node{filter_clause}(around:{radius_m},{lat},{lng});'
        f'way{filter_clause}(around:{radius_m},{lat},{lng});'
        ")"
        ";out center 30;"
    )
    data = _http_post_overpass(query)
    if not data:
        return []

    elements = data.get("elements") or []
    items: List[Dict[str, Any]] = []
    for el in elements:
        # Nodes have lat/lon directly; ways have center.lat/center.lon
        e_lat = el.get("lat") or (el.get("center") or {}).get("lat")
        e_lng = el.get("lon") or (el.get("center") or {}).get("lon")
        if e_lat is None or e_lng is None:
            continue
        tags = el.get("tags") or {}
        name = tags.get("name") or tags.get("name:en") or tags.get("operator")
        if not name:
            continue
        d = _haversine_metres(lat, lng, e_lat, e_lng)
        items.append({"name": name, "lat": e_lat, "lng": e_lng, "straight_m": d})
    items.sort(key=lambda x: x["straight_m"])
    return items[:limit]


def _walking_metres(from_lat: float, from_lng: float, to_lat: float, to_lng: float, token: str) -> Optional[int]:
    url = (
        f"{MAPBOX_DIRECTIONS}/"
        f"{from_lng},{from_lat};{to_lng},{to_lat}"
        f"?overview=false&access_token={token}"
    )
    raw = _http_get(url)
    if not raw:
        return None
    try:
        data = json.loads(raw)
        routes = data.get("routes") or []
        if not routes:
            return None
        return int(routes[0].get("distance") or 0)
    except (json.JSONDecodeError, KeyError, TypeError):
        return None


def _driving_seconds(from_lat: float, from_lng: float, to_lat: float, to_lng: float, token: str) -> Optional[int]:
    """Typical drive time in seconds along the Mapbox driving route. Used for
    the "short drive" tier (POIs beyond WALKABLE_THRESHOLD_M) so we never label
    a multi-kilometre route a 'walk'."""
    url = (
        f"{MAPBOX_DRIVING}/"
        f"{from_lng},{from_lat};{to_lng},{to_lat}"
        f"?overview=false&access_token={token}"
    )
    raw = _http_get(url)
    if not raw:
        return None
    try:
        data = json.loads(raw)
        routes = data.get("routes") or []
        if not routes:
            return None
        return int(routes[0].get("duration") or 0)
    except (json.JSONDecodeError, KeyError, TypeError):
        return None


def resolve_pois(lat: float, lng: float, *, mapbox_token: Optional[str] = None) -> List[Dict[str, Any]]:
    """Return per-category nearest-POI list with walking distances.

    Always returns a list (possibly empty). Skips categories where no POI is
    within the configured radius or where the walking route exceeds
    MAX_WALK_METRES.
    """
    token = mapbox_token or os.environ.get("MAPBOX_TOKEN") or os.environ.get("VITE_MAPBOX_TOKEN")
    if not token:
        logger.warning("MAPBOX_TOKEN not set — skipping walking distance resolution")
        return []

    out: List[Dict[str, Any]] = []
    seen_names: set = set()

    for cat in POI_CATEGORIES:
        # Try the primary filter first, fall back if zero results
        candidates = _overpass_nearest(lat, lng, cat["filter"], cat["radius_m"], limit=5)
        if not candidates and cat.get("fallback_filter"):
            candidates = _overpass_nearest(lat, lng, cat["fallback_filter"], cat["radius_m"], limit=5)
        if not candidates:
            continue

        # Pick the closest by straight-line distance, then verify walking distance
        chosen = None
        chosen_walk = None
        for c in candidates:
            name_lower = c["name"].lower().strip()
            if name_lower in seen_names:
                continue
            walk_m = _walking_metres(lat, lng, c["lat"], c["lng"], token)
            if walk_m is None:
                continue
            if walk_m > MAX_WALK_METRES * 2:  # really far, skip
                continue
            chosen = c
            chosen_walk = walk_m
            break

        if not chosen or chosen_walk is None:
            continue

        seen_names.add(chosen["name"].lower().strip())
        entry = {
            "key": cat["key"],
            "name": chosen["name"],
            "category": cat["category"],
            "walkMetres": chosen_walk,
            "lat": chosen["lat"],
            "lng": chosen["lng"],
        }
        # Beyond a genuine walk (~1km), a metres-of-walking figure is misleading.
        # Attach a real drive time so the frontend can render the "short drive"
        # tier honestly ("Miami Beach — 9 min drive") rather than "6,250 m walk".
        if chosen_walk > WALKABLE_THRESHOLD_M:
            drive_s = _driving_seconds(lat, lng, chosen["lat"], chosen["lng"], token)
            if drive_s:
                entry["driveSeconds"] = drive_s
        out.append(entry)

    out.sort(key=lambda p: p["walkMetres"])
    return out
