#!/usr/bin/env python3
"""
precompute_living_map.py — Phase 0 of the Living Map hero.

Builds the `living_map` object for a property: the data the interactive aerial
hero (LivingMapHero.tsx) consumes on `/property/:id` and `/offmarket/:slug`.
Everything here is PRECOMPUTED and served as static blob tiles + plain JSON — no
AI, no per-request third-party call. Runtime cost per view ≈ $0.

    python3 scripts/precompute_living_map.py --suburb robina --limit 10
    python3 scripts/precompute_living_map.py --address "8 Trinity Place, Robina"
    python3 scripts/precompute_living_map.py --self-test        # credential-free

Reference material (read before touching this): /home/fields/living_map_ref/
  README.md   — the data contract + compliance rules
  PLAN.md     — §2 the contract, §3 this job
  sample_living_map_data.json — 2 real Robina instances of the output shape
  prototype_living_map.html   — the signed-off canvas engine that consumes it

WHAT IT ASSEMBLES (per property), all sources validated in the prototype:
  center     — parcel centroid via render_property_aerial.fit_zoom()   (reused)
  tiles      — Google Static Maps satellite, house z20 / street z17 (per property)
               + suburb z14 / city z10 (shared per-suburb / global). Blob URLs.
  parcel     — QLD cadastre rings via render_property_aerial.polygon_for() (reused)
  pois       — OSM Overpass places -> straight-line metres -> OSRM drive time/km,
               walk time ESTIMATED (straight_km * 1.35 / 4.8 * 60)
  routes     — OSRM route geometry to a fixed set of key destinations
  comps      — the PIPELINE's valuation output (adjusted_comparables), read at
               BUILD time, NEVER a live `valuation_data.comparables` query (that
               field flip-flops empty mid-recompute — it bit us repeatedly).
               Addresses geocoded via Nominatim with an on-disk cache.
  catchments — QLD ArcGIS point query (primary + junior-secondary zones)
  subject_value — the valuation RANGE {estimate, low, high}, not a headline figure

⛔ NO 3D / building extrusion. The `buildings3d`/`sun_lat` keys in the sample are a
   REMOVED dead end (LiDAR footprints are noisy blobs) — do not build them.

Self-monitoring (CLAUDE.md Rule 7/7b): the run body is wrapped in job_run(); the
zero-output path (0 built though listings exist) RAISES. A per-property failure
never advances the "last built" watermark for that property. Every optional layer
that can't be computed is recorded in build_notes.gaps[] and the property still
builds.
"""
from __future__ import annotations

import os
import sys

# ⚠ scripts/email.py shadows the stdlib `email` package when this file is run
# from scripts/ (its own dir is sys.path[0]). urllib.request -> http.client ->
# email.parser would then import the wrong module. Drop the script dir before the
# network stdlib imports, then restore the paths we need for local imports.
_HERE = os.path.dirname(os.path.abspath(__file__))
sys.path[:] = [p for p in sys.path if os.path.abspath(p or ".") != _HERE]
import email.parser  # noqa: E402,F401  — force stdlib resolution before urllib

import argparse       # noqa: E402
import json           # noqa: E402
import math           # noqa: E402
import time           # noqa: E402
import urllib.parse   # noqa: E402
import urllib.request # noqa: E402
from datetime import datetime, timezone  # noqa: E402
from pathlib import Path                  # noqa: E402

sys.path.insert(0, os.path.dirname(_HERE))   # repo root, for shared.*
sys.path.insert(0, _HERE)                    # scripts/, for job_status + render_property_aerial

# ── constants ────────────────────────────────────────────────────────────────

VERSION = 1

# Static Maps tile geometry (matches the prototype: 640² native, scale 2 => 1280²).
TILE_PX = 640
TILE_SCALE = 2
# Per-property zooms + the shared wide tiles. house/street are unique to a
# property; suburb/city are shared (one per suburb, one global) to keep the
# Static Maps bill tiny — see PLAN §3.
ZOOM_HOUSE, ZOOM_STREET, ZOOM_SUBURB, ZOOM_CITY = 20, 17, 14, 10

JPEG_QUALITY = 82

BLOB_ROOT = Path("/data/blobs/property-images/livingmap")
PUBLIC_ROOT = "https://blobs.fieldsestate.com.au/property-images/livingmap"

SUBURBS = ("robina", "varsity_lakes", "burleigh_waters")

# Nominatim geocode cache — comp addresses repeat heavily across ~8k properties,
# so a shared on-disk cache turns most geocodes into a dict lookup (PLAN §3).
GEOCODE_CACHE = Path(_HERE).parent / "data" / "livingmap_geocode_cache.json"

OVERPASS_URL = os.environ.get("OVERPASS_URL", "https://overpass-api.de/api/interpreter")
# Self-hosted OSRM on this VM (Docker, QLD/AU extract) → http://localhost:5000. Falls
# back to the public demo when OSRM_BASE is unset, so a dev run still works, but the
# 8k backfill/nightly job MUST set OSRM_BASE to the local server (the public demo
# rate-limits at volume — PLAN §3).
OSRM_BASE = os.environ.get("OSRM_BASE", "https://router.project-osrm.org")
NOMINATIM_URL = os.environ.get("NOMINATIM_URL", "https://nominatim.openstreetmap.org/search")
USER_AGENT = "FieldsEstate-LivingMap/1.0 (will@fieldsestate.com.au)"

QLD_CATCHMENT = ("https://spatial-gis.information.qld.gov.au/arcgis/rest/services/"
                 "Society/SchoolsAndSchoolCatchments/MapServer/{layer}/query")

# POI categories -> Overpass filters. Straight-line nearest of each is kept.
POI_QUERIES = {
    "School":   'node["amenity"="school"]',
    "Station":  'node["railway"="station"]',
    "Mall":     'node["shop"="mall"]',
    "Hospital": 'node["amenity"="hospital"]',
    "Beach":    'node["natural"="beach"]',
}

# Fixed routed destinations for v1 (PLAN §7 decision 1). Precomputed only — no
# live per-user routing. Colours mirror the prototype's route palette.
KEY_DESTINATIONS = [
    {"name": "Surfers Paradise", "lat": -28.002373, "lon": 153.430545, "color": "#f2a900"},
    {"name": "Gold Coast Airport", "lat": -28.164443, "lon": 153.505333, "color": "#5a7db0"},
    {"name": "Robina Town Centre", "lat": -28.069700, "lon": 153.386400, "color": "#8fe388"},
    {"name": "Burleigh Beach", "lat": -28.090300, "lon": 153.459700, "color": "#e78fb0"},
]


# ── geometry / georeference ──────────────────────────────────────────────────
# The forward Web-Mercator projection is reused verbatim from render_property_aerial
# (TILE=256 world units). We add the inverse so a pixel in the rendered tile maps
# back to lat/lon — the seam the canvas needs and the thing the self-test checks.

TILE = 256


def _project(lat, lon):
    """Web-Mercator world coordinate (256-tile units) — same as
    render_property_aerial._project. Forward: lat/lon -> world x,y."""
    siny = min(max(math.sin(math.radians(lat)), -0.9999), 0.9999)
    return (TILE * (0.5 + lon / 360.0),
            TILE * (0.5 - math.log((1 + siny) / (1 - siny)) / (4 * math.pi)))


def _unproject(x, y):
    """Inverse of _project: world x,y (256-tile units) -> (lat, lon)."""
    lon = (x / TILE - 0.5) * 360.0
    n = (0.5 - y / TILE) * (4 * math.pi)
    # (1+siny)/(1-siny) = e^n  =>  siny = (e^n - 1)/(e^n + 1) = tanh(n/2)
    siny = math.tanh(n / 2.0)
    lat = math.degrees(math.asin(min(max(siny, -0.9999), 0.9999)))
    return (lat, lon)


def latlon_to_pixel(lat, lon, clat, clon, zoom, width=TILE_PX * TILE_SCALE,
                    height=TILE_PX * TILE_SCALE, scale=TILE_SCALE):
    """(lat,lon) -> pixel (px,py) in a `width`x`height` aerial centred on
    (clat,clon) at `zoom`/`scale`. Forward transform, matching
    render_property_aerial.draw_boundary.to_px()."""
    f = (2 ** zoom) * scale
    cx, cy = _project(clat, clon)
    x, y = _project(lat, lon)
    return ((x - cx) * f + width / 2.0, (y - cy) * f + height / 2.0)


def pixel_to_latlon(px, py, clat, clon, zoom, width=TILE_PX * TILE_SCALE,
                    height=TILE_PX * TILE_SCALE, scale=TILE_SCALE):
    """Inverse of latlon_to_pixel: pixel -> (lat,lon). This is the georeference
    the canvas uses to place a tap on the map, and the round-trip the self-test
    verifies to 1e-4 deg."""
    f = (2 ** zoom) * scale
    cx, cy = _project(clat, clon)
    world_x = (px - width / 2.0) / f + cx
    world_y = (py - height / 2.0) / f + cy
    return _unproject(world_x, world_y)


def haversine_m(lat1, lon1, lat2, lon2):
    """Great-circle straight-line distance in metres."""
    r = 6371000.0
    p1, p2 = math.radians(lat1), math.radians(lat2)
    dp = math.radians(lat2 - lat1)
    dl = math.radians(lon2 - lon1)
    a = math.sin(dp / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(dl / 2) ** 2
    return 2 * r * math.asin(min(1.0, math.sqrt(a)))


def bearing_deg(lat1, lon1, lat2, lon2):
    """Initial compass bearing (degrees, 0=N) from point 1 to point 2."""
    y = math.sin(math.radians(lon2 - lon1)) * math.cos(math.radians(lat2))
    x = (math.cos(math.radians(lat1)) * math.sin(math.radians(lat2))
         - math.sin(math.radians(lat1)) * math.cos(math.radians(lat2))
         * math.cos(math.radians(lon2 - lon1)))
    return (math.degrees(math.atan2(y, x)) + 360.0) % 360.0


_COMPASS = ["N", "NE", "E", "SE", "S", "SW", "W", "NW"]


def compass(bearing):
    """8-point compass label for a bearing in degrees."""
    return _COMPASS[int((bearing + 22.5) % 360 // 45)]


def estimate_walk_min(straight_km):
    """Walk time ESTIMATE (label it as estimated to the reader): straight-line
    distance * 1.35 detour factor / 4.8 km·h walking speed, in minutes."""
    return round(straight_km * 1.35 / 4.8 * 60)


def expand_school_name(name):
    """QLD catchment `centre_name` uses abbreviations; expand to the full name.
    `X SS` -> `X State School`; `X SHS` -> `X State High School`."""
    if not name:
        return name
    n = name.strip()
    if n.endswith(" SHS"):
        return n[:-4] + " State High School"
    if n.endswith(" SS"):
        return n[:-3] + " State School"
    return n


# ── pure assembly (offline-testable) ─────────────────────────────────────────

def build_pois(center, raw_pois, drive_table):
    """Assemble the pois[] contract from nearest-per-category raw places, the
    drive-time table, and the estimated walk time.

    `raw_pois`   : list of {name, cat, lat, lon}
    `drive_table`: {(lat,lon): {"drive_min": int, "drive_km": float}} keyed by the
                   POI coord (from OSRM `table`); missing entries degrade to None.
    """
    out = []
    for p in raw_pois:
        m = haversine_m(center["lat"], center["lon"], p["lat"], p["lon"])
        dt = drive_table.get((p["lat"], p["lon"]), {})
        out.append({
            "name": p["name"],
            "cat": p["cat"],
            "lat": p["lat"],
            "lon": p["lon"],
            "straight_m": round(m),
            "drive_min": dt.get("drive_min"),
            "drive_km": dt.get("drive_km"),
            "walk_min": estimate_walk_min(m / 1000.0),
        })
    return out


def build_comps(center, raw_comps, geocode):
    """Assemble comps[] from the PIPELINE's valuation output (adjusted_comparables).

    `raw_comps`: list of dicts with address, sale_price (EXACT), sale_date,
                 adjusted_price, total_adjustment_pct, distance_km.
    `geocode`  : {address: (lat, lon)} — Nominatim results (cached). A comp that
                 can't be geocoded is dropped from the map layer (it has no pin)
                 but the miss is surfaced by the caller into build_notes.gaps.

    Prices are kept EXACT (never rounded) per CLAUDE.md Rule 5.
    """
    out = []
    for c in raw_comps:
        addr = (c.get("address") or "").strip()
        latlon = geocode.get(addr)
        if not latlon:
            continue
        lat, lon = latlon
        # Prefer the pipeline's own distance_km; fall back to computing it.
        dist = c.get("distance_km")
        if dist is None:
            dist = round(haversine_m(center["lat"], center["lon"], lat, lon) / 1000.0, 2)
        brg = bearing_deg(center["lat"], center["lon"], lat, lon)
        out.append({
            "address": addr,
            "sale_price": c.get("sale_price"),          # EXACT, never rounded
            "sale_date": c.get("sale_date"),
            "adjusted_price": c.get("adjusted_price"),
            "adj_pct": c.get("total_adjustment_pct"),
            "distance_km": dist,
            "bearing": round(brg),
            "compass": compass(brg),
            "lat": lat,
            "lon": lon,
        })
    return out


def subject_value_from_valuation(valuation_data):
    """The valuation RANGE {estimate, low, high} (never a single headline figure).

    Read from `valuation_data.confidence`. Returns None when the property is
    `directional_only` (outside the $1M–$2M design envelope — the point estimate
    and range are deliberately suppressed there; see README / valuation_design_envelope)
    or when the range is absent.
    """
    if not valuation_data:
        return None
    meta = valuation_data.get("metadata") or {}
    if meta.get("directional_only"):
        return None
    conf = valuation_data.get("confidence") or {}
    est = conf.get("reconciled_valuation")
    rng = conf.get("range") or {}
    low, high = rng.get("low"), rng.get("high")
    if est is None or low is None or high is None:
        return None
    return {"estimate": est, "low": low, "high": high}


def comps_from_valuation(valuation_data):
    """The build-time comp source. Reads `valuation_data.adjusted_comparables` —
    NEVER `valuation_data.comparables`, which flip-flops empty mid-recompute (the
    bug this rule exists to avoid; confirmed live 2026-08-24: `comparables` was []
    while `adjusted_comparables` held 8 entries on the same doc).

    Returns [] on absence. Each entry carries address / sale_price / sale_date /
    adjusted_price / total_adjustment_pct / distance_km.
    """
    if not valuation_data:
        return []
    return list(valuation_data.get("adjusted_comparables") or [])


def rings_latlon(poly):
    """Cadastre rings from polygon_for() are [[(lon,lat), ...], ...]. The contract
    stores [[[lat,lon], ...], ...]."""
    out = []
    for ring in (poly.get("rings") or []):
        out.append([[float(p[1]), float(p[0])] for p in ring])
    return out


def assemble_living_map(*, prop_id, address, center, tiles, parcel, pois, routes,
                        comps, catchments, subject_value, gaps):
    """Combine the computed layers into the `living_map` contract object. Pure —
    no network, no I/O. Every optional layer may be empty/None; `gaps` records
    what couldn't be computed so the frontend hides those controls."""
    return {
        "version": VERSION,
        "computed_at": datetime.now(timezone.utc).isoformat(),
        "id": prop_id,
        "address": address,
        "center": center,                 # {lat, lon}
        "tiles": tiles,                   # {house, street, suburb, city} blob URLs
        "parcel": parcel,                 # {rings, lotplan, area_sqm} or None
        "pois": pois,                     # list
        "routes": routes,                 # list
        "comps": comps,                   # list
        "catchments": catchments,         # list
        "subject_value": subject_value,   # {estimate, low, high} or None
        "build_notes": {"gaps": gaps},
    }


# ── network layers (build-time only; never called by the self-test) ───────────

def _http_get(url, timeout=30, headers=None):
    req = urllib.request.Request(url, headers={"User-Agent": USER_AGENT, **(headers or {})})
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return r.read()


def fetch_static_tile(lat, lon, zoom, key):
    """One Google Static Maps satellite tile as raw bytes (640² scale 2)."""
    url = ("https://maps.googleapis.com/maps/api/staticmap?"
           f"center={lat},{lon}&zoom={zoom}&size={TILE_PX}x{TILE_PX}"
           f"&scale={TILE_SCALE}&maptype=satellite&key={key}")
    data = _http_get(url)
    if len(data) < 5000:
        raise RuntimeError("static map returned an error tile")
    return data


def write_tile_blob(data, rel_path):
    """Save a tile as JPEG q82 to the blob store (mirrors batch_render_aerials'
    on-disk blob write) and return its public URL. `rel_path` is relative to
    BLOB_ROOT / PUBLIC_ROOT, e.g. "robina/<id>/house.jpg"."""
    import io
    from PIL import Image
    out = BLOB_ROOT / rel_path
    out.parent.mkdir(parents=True, exist_ok=True)
    Image.open(io.BytesIO(data)).convert("RGB").save(out, "JPEG", quality=JPEG_QUALITY, optimize=True)
    return f"{PUBLIC_ROOT}/{rel_path}"


def fetch_overpass_pois(center, radius_m=5000):
    """Nearest place of each category within radius. Returns list of
    {name, cat, lat, lon}. Best-effort — a failure returns [] and is recorded
    as a gap by the caller."""
    parts = []
    for cat, filt in POI_QUERIES.items():
        parts.append(f'{filt}(around:{radius_m},{center["lat"]},{center["lon"]});')
    q = f"[out:json][timeout:25];({''.join(parts)});out center;"
    # Overpass public API returns transient 429/504 under load; retry with backoff
    # rather than dropping POIs (the drive/walk-time layer) to a gap. Self-host or
    # add a mirror before real volume (PLAN §3).
    url = f"{OVERPASS_URL}?data={urllib.parse.quote(q)}"
    data = None
    for attempt in range(4):
        try:
            data = json.loads(_http_get(url, timeout=45))
            break
        except Exception:                                   # noqa: BLE001
            if attempt == 3:
                raise
            time.sleep(3 * (attempt + 1))
    # Bucket by category, keep straight-line nearest of each.
    best = {}
    for el in data.get("elements", []):
        tags = el.get("tags", {})
        lat = el.get("lat") or (el.get("center") or {}).get("lat")
        lon = el.get("lon") or (el.get("center") or {}).get("lon")
        if lat is None or lon is None:
            continue
        cat = None
        if tags.get("amenity") == "school":
            cat = "School"
        elif tags.get("railway") == "station":
            cat = "Station"
        elif tags.get("shop") == "mall":
            cat = "Mall"
        elif tags.get("amenity") == "hospital":
            cat = "Hospital"
        elif tags.get("natural") == "beach":
            cat = "Beach"
        if not cat:
            continue
        m = haversine_m(center["lat"], center["lon"], lat, lon)
        if cat not in best or m < best[cat][0]:
            best[cat] = (m, {"name": tags.get("name") or cat, "cat": cat,
                             "lat": lat, "lon": lon})
    return [v[1] for v in best.values()]


def osrm_drive_table(center, points):
    """Drive time (min) + distance (km) from `center` to each point via OSRM
    `table`. Returns {(lat,lon): {"drive_min", "drive_km"}}. Best-effort."""
    if not points:
        return {}
    coords = f"{center['lon']},{center['lat']};" + ";".join(
        f"{p['lon']},{p['lat']}" for p in points)
    # NOTE: a `destinations=` param makes the OSRM public demo 400 ("Query string
    # malformed"); omit it. With only sources=0 the row is [self, p1, p2, …], so
    # point i is at index i+1. Params are urlencoded (raw commas also 400).
    url = (f"{OSRM_BASE}/table/v1/driving/{coords}?"
           + urllib.parse.urlencode({"sources": 0, "annotations": "duration,distance"}))
    data = json.loads(_http_get(url))
    durs = (data.get("durations") or [[]])[0]
    dists = (data.get("distances") or [[]])[0]
    out = {}
    for i, p in enumerate(points):
        d = durs[i + 1] if i + 1 < len(durs) else None
        km = dists[i + 1] if i + 1 < len(dists) else None
        out[(p["lat"], p["lon"])] = {
            "drive_min": round(d / 60.0) if d is not None else None,
            "drive_km": round(km / 1000.0, 1) if km is not None else None,
        }
    return out


def osrm_route(center, dest):
    """Full route geometry center->dest via OSRM `route`. Returns
    {name, color, min, km, geom:[[lat,lon]]} or None. Best-effort."""
    coords = f"{center['lon']},{center['lat']};{dest['lon']},{dest['lat']}"
    url = f"{OSRM_BASE}/route/v1/driving/{coords}?overview=full&geometries=geojson"
    data = json.loads(_http_get(url))
    routes = data.get("routes") or []
    if not routes:
        return None
    r = routes[0]
    geom = [[c[1], c[0]] for c in (r.get("geometry") or {}).get("coordinates", [])]
    return {
        "name": dest["name"],
        "color": dest["color"],
        "min": round(r.get("duration", 0) / 60.0),
        "km": round(r.get("distance", 0) / 1000.0, 1),
        "geom": geom,
    }


def _load_geocode_cache():
    if GEOCODE_CACHE.exists():
        try:
            return json.loads(GEOCODE_CACHE.read_text())
        except Exception:
            return {}
    return {}


def _save_geocode_cache(cache):
    GEOCODE_CACHE.parent.mkdir(parents=True, exist_ok=True)
    GEOCODE_CACHE.write_text(json.dumps(cache))


def geocode_addresses(addresses, cache):
    """Geocode comp addresses via Nominatim with an on-disk cache. Throttled to
    ≤1 req/s (PLAN §3). Returns {address: (lat, lon)}; addresses that fail to
    geocode are simply absent. Mutates `cache` in place."""
    out = {}
    for addr in addresses:
        if not addr:
            continue
        if addr in cache:
            if cache[addr]:
                out[addr] = tuple(cache[addr])
            continue
        q = urllib.parse.urlencode({"q": addr + ", QLD, Australia",
                                    "format": "json", "limit": 1})
        try:
            data = json.loads(_http_get(f"{NOMINATIM_URL}?{q}"))
        except Exception:
            data = []
        if data:
            latlon = (float(data[0]["lat"]), float(data[0]["lon"]))
            cache[addr] = latlon
            out[addr] = latlon
        else:
            cache[addr] = None       # negative cache — don't re-hit a dead address
        time.sleep(1.1)              # Nominatim usage policy: ≤1 req/s
    return out


def fetch_catchments(center):
    """Primary (layer 1) + junior-secondary (layer 2) QLD school catchment zones
    for the point. Returns list of {level, school, poly:[[lat,lon]]}. Best-effort."""
    out = []
    for layer, level in ((1, "Primary"), (2, "Junior Secondary")):
        q = urllib.parse.urlencode({
            "geometry": f"{center['lon']},{center['lat']}",
            "geometryType": "esriGeometryPoint",
            "inSR": "4326",
            "spatialRel": "esriSpatialRelIntersects",
            "outFields": "centre_name",
            "returnGeometry": "true",
            "f": "geojson",
        })
        try:
            data = json.loads(_http_get(f"{QLD_CATCHMENT.format(layer=layer)}?{q}"))
        except Exception:
            continue
        for feat in data.get("features", []):
            name = expand_school_name((feat.get("properties") or {}).get("centre_name"))
            geom = feat.get("geometry") or {}
            rings = []
            if geom.get("type") == "Polygon":
                rings = geom.get("coordinates") or []
            elif geom.get("type") == "MultiPolygon":
                # flatten to the outer ring of each polygon
                rings = [poly[0] for poly in (geom.get("coordinates") or []) if poly]
            # take the largest ring as the display polygon
            best = max(rings, key=len) if rings else []
            poly = [[c[1], c[0]] for c in best]
            if poly:
                out.append({"level": level, "school": name, "poly": poly})
    return out


# ── per-property build ───────────────────────────────────────────────────────

class BuildResult:
    def __init__(self):
        self.n = 0
        self.gaps = 0            # count of properties that built with >=1 gap
        self.tiles = 0          # Static Maps tiles fetched
        self.failed = 0
        self.eligible = 0


def build_one(gc, suburb, doc, key, geocode_cache, shared_tiles):
    """Build the living_map object for one property and persist it to the doc.

    Returns (living_map_dict, gaps_list) on success, or (None, reason) if the
    property cannot build at all (no center). Optional-layer misses go into
    `gaps` and the property still builds. Raises on nothing — the caller counts
    outcomes and applies the Rule 7b zero-output assertion across the batch.
    """
    from render_property_aerial import polygon_for, fit_zoom
    gaps = []
    tiles_fetched = 0

    # ── center + parcel (reuse the proven cadastre code) ──────────────────────
    poly = polygon_for(gc, suburb, doc)
    parcel = None
    if poly and poly.get("rings"):
        zoom, clat, clon = fit_zoom(poly["rings"], TILE_PX, TILE_PX, TILE_SCALE)
        center = {"lat": clat, "lon": clon}
        parcel = {
            "rings": rings_latlon(poly),
            "lotplan": poly.get("lotplan"),
            "area_sqm": poly.get("lot_area_sqm"),
        }
    else:
        # No parcel -> fall back to the stored point. Without either we cannot
        # place a single layer, so this is the property's real zero-output path.
        lat, lon = doc.get("LATITUDE"), doc.get("LONGITUDE")
        if lat is None or lon is None:
            return None, "no parcel geometry and no coordinates"
        center = {"lat": float(lat), "lon": float(lon)}
        gaps.append("parcel: no cadastre geometry on file")

    # ── tiles (per-property house/street; shared suburb/city) ─────────────────
    tiles = {}
    try:
        tiles["house"] = write_tile_blob(
            fetch_static_tile(center["lat"], center["lon"], ZOOM_HOUSE, key),
            f"{suburb}/{doc['_id']}/house.jpg")
        tiles["street"] = write_tile_blob(
            fetch_static_tile(center["lat"], center["lon"], ZOOM_STREET, key),
            f"{suburb}/{doc['_id']}/street.jpg")
        tiles_fetched += 2
    except Exception as e:                                  # noqa: BLE001
        gaps.append(f"tiles: house/street fetch failed ({type(e).__name__})")
    # Shared wide tiles: one per suburb (z14), one global (z10). Computed once
    # per batch and reused — see run().
    tiles["suburb"] = shared_tiles.get(("suburb", suburb))
    tiles["city"] = shared_tiles.get(("city", "gc"))
    for k in ("suburb", "city"):
        if not tiles.get(k):
            gaps.append(f"tiles: {k} tile unavailable")

    # ── POIs + drive times ────────────────────────────────────────────────────
    pois = []
    try:
        raw = fetch_overpass_pois(center)
        table = osrm_drive_table(center, raw)
        pois = build_pois(center, raw, table)
        if not pois:
            gaps.append("pois: none found within radius")
    except Exception as e:                                  # noqa: BLE001
        gaps.append(f"pois: fetch failed ({type(e).__name__})")

    # ── routes to key destinations ────────────────────────────────────────────
    routes = []
    for dest in KEY_DESTINATIONS:
        try:
            rt = osrm_route(center, dest)
            if rt:
                routes.append(rt)
        except Exception:                                  # noqa: BLE001
            pass
    if len(routes) < len(KEY_DESTINATIONS):
        gaps.append(f"routes: {len(routes)}/{len(KEY_DESTINATIONS)} destinations routed")

    # ── comps (from the pipeline valuation output, NOT a live comparables query)
    valuation_data = doc.get("valuation_data") or {}
    raw_comps = comps_from_valuation(valuation_data)
    comps = []
    if raw_comps:
        addrs = [c.get("address") for c in raw_comps]
        geo = geocode_addresses(addrs, geocode_cache)
        comps = build_comps(center, raw_comps, geo)
        missed = len(raw_comps) - len(comps)
        if missed:
            gaps.append(f"comps: {missed}/{len(raw_comps)} comp addresses failed to geocode")
    else:
        gaps.append("comps: no adjusted_comparables in valuation output")

    # ── catchments ────────────────────────────────────────────────────────────
    catchments = []
    try:
        catchments = fetch_catchments(center)
        if not catchments:
            gaps.append("catchments: no QLD zone intersects this point")
    except Exception as e:                                  # noqa: BLE001
        gaps.append(f"catchments: fetch failed ({type(e).__name__})")

    # ── subject value (range, not headline) ───────────────────────────────────
    subject_value = subject_value_from_valuation(valuation_data)
    if subject_value is None:
        gaps.append("subject_value: no in-envelope valuation range")

    living_map = assemble_living_map(
        prop_id=str(doc["_id"]), address=doc.get("address"), center=center,
        tiles=tiles, parcel=parcel, pois=pois, routes=routes, comps=comps,
        catchments=catchments, subject_value=subject_value, gaps=gaps)

    # Persist. Only the successful build advances anything — a property that
    # returned None above never reaches here, so its "last built" is untouched.
    gc[suburb].update_one({"_id": doc["_id"]},
                          {"$set": {"living_map": living_map,
                                    "living_map_built_at": living_map["computed_at"]}})
    return living_map, (gaps, tiles_fetched)


def _shared_tile(kind, sub_or_center, key, shared_tiles):
    """Fetch a shared wide tile once and cache its URL. suburb/city tiles are
    identical for every property in a suburb / the whole book, so we never pay
    for them per property."""
    (lat, lon, zoom, rel, cache_key) = sub_or_center
    if cache_key in shared_tiles:
        return
    try:
        data = fetch_static_tile(lat, lon, zoom, key)
        shared_tiles[cache_key] = write_tile_blob(data, rel)
    except Exception:                                       # noqa: BLE001
        shared_tiles[cache_key] = None


# suburb centroids for the shared z14 tile; the z10 city tile is one Gold-Coast-wide.
SUBURB_CENTROIDS = {
    "robina": (-28.0703, 153.3860),
    "varsity_lakes": (-28.0870, 153.3830),
    "burleigh_waters": (-28.0900, 153.4360),
}
CITY_CENTROID = (-28.0167, 153.4000)


def run(args):
    """Iterate the requested properties and build a living_map for each. Returns
    a BuildResult. Never advances a per-property watermark on a failed property."""
    from shared.db import get_gold_coast_db
    gc = get_gold_coast_db()
    key = os.getenv("GOOGLE_MAPS_STATIC_API_KEY")
    if not key:
        raise RuntimeError("GOOGLE_MAPS_STATIC_API_KEY not set")

    geocode_cache = _load_geocode_cache()
    shared_tiles = {}
    result = BuildResult()

    suburbs = [args.suburb] if args.suburb else list(SUBURBS)

    # Pre-warm shared wide tiles for the suburbs in scope + the one city tile.
    _shared_tile("city", (*CITY_CENTROID, ZOOM_CITY, "_shared/city.jpg", ("city", "gc")),
                 key, shared_tiles)
    for s in suburbs:
        c = SUBURB_CENTROIDS.get(s)
        if c:
            _shared_tile("suburb", (*c, ZOOM_SUBURB, f"_shared/{s}.jpg", ("suburb", s)),
                         key, shared_tiles)

    for suburb in suburbs:
        if args.address:
            docs = [d for d in [gc[suburb].find_one({"address": args.address})] if d]
        elif args.offmarket:
            # Off-market stock = has cadastre (LOT/PLAN), not sold/for-sale. Mirrors
            # batch_render_aerials' off-market query. These docs carry the same
            # valuation_data (~72% of them), so comps/subject_value populate as-is;
            # the rest degrade gracefully.
            q = {"listing_status": {"$nin": ["sold", "for_sale"]},
                 "LOT": {"$nin": [None, ""]}, "PLAN": {"$nin": [None, ""]}}
            if not args.force:
                q["living_map"] = {"$exists": False}
            cur = gc[suburb].find(q)
            if args.limit:
                cur = cur.limit(args.limit)
            docs = list(cur)
        else:
            q = {"listing_status": "for_sale"}
            if not args.force:
                q["living_map"] = {"$exists": False}
            cur = gc[suburb].find(q)
            if args.limit:
                cur = cur.limit(args.limit)
            docs = list(cur)

        for doc in docs:
            result.eligible += 1
            try:
                lm, info = build_one(gc, suburb, doc, key, geocode_cache, shared_tiles)
            except Exception as e:                          # noqa: BLE001
                result.failed += 1
                print(f"  ✗ {doc.get('address','?')}: {type(e).__name__}: {e}")
                continue
            if lm is None:
                result.failed += 1
                print(f"  – {doc.get('address','?')}: {info}")
                continue
            gaps, tiles_fetched = info
            result.n += 1
            result.tiles += tiles_fetched
            if gaps:
                result.gaps += 1
            print(f"  ✓ {doc.get('address','?')[:48]:<48} "
                  f"{len(gaps)} gap(s), {tiles_fetched} tile(s)")

    _save_geocode_cache(geocode_cache)
    return result


def main():
    from shared.env import load_env
    load_env()

    # Re-resolve service endpoints AFTER load_env() — the module-level defaults (l.92-98)
    # are read at import, BEFORE .env is loaded. Without this, OSRM_BASE=http://localhost:5000
    # in .env (the self-hosted OSRM) would be ignored unless it were also a real exported
    # env var. This makes both paths work (Rule 7.3: load your own environment).
    global OSRM_BASE, NOMINATIM_URL, OVERPASS_URL
    OSRM_BASE = os.environ.get("OSRM_BASE", OSRM_BASE)
    NOMINATIM_URL = os.environ.get("NOMINATIM_URL", NOMINATIM_URL)
    OVERPASS_URL = os.environ.get("OVERPASS_URL", OVERPASS_URL)

    ap = argparse.ArgumentParser(description="Living Map precompute (Phase 0)")
    ap.add_argument("--suburb", choices=list(SUBURBS))
    ap.add_argument("--address")
    ap.add_argument("--limit", type=int)
    ap.add_argument("--offmarket", action="store_true",
                    help="build for off-market stock (cadastre LOT/PLAN, not sold/for-sale) — for /offmarket pages")
    ap.add_argument("--force", action="store_true",
                    help="rebuild even if a living_map already exists")
    ap.add_argument("--self-test", action="store_true",
                    help="credential-free assembly + georeference round-trip check")
    args = ap.parse_args()

    if args.self_test:
        return self_test()

    from job_status import job_run
    # Distinct heartbeat per mode so the on-market (daily) and off-market (weekly)
    # nightly runs don't overwrite each other's status on the health board.
    _job = os.environ.get("LIVING_MAP_JOB_NAME",
                          "precompute_living_map_offmarket" if args.offmarket
                          else "precompute_living_map")
    _cadence = 24 * 7 if args.offmarket else 24
    with job_run(_job, cadence_hours=_cadence,
                 title="Living Map precompute" + (" (off-market)" if args.offmarket else "")) as beat:
        # Was there any input at all? An empty for-sale set is a legitimate "no
        # work to do"; input-present-but-nothing-built is a failure (Rule 7b).
        result = run(args)
        beat.metrics = {"built": result.n, "gaps": result.gaps,
                        "tiles": result.tiles, "failed": result.failed}
        if result.eligible and result.n == 0:
            raise RuntimeError(
                f"{result.eligible} listings eligible but 0 living_maps built "
                f"({result.failed} failed) — upstream (cadastre / Static Maps key / "
                f"valuation output) is broken, not empty")
        beat.detail = (f"{result.n} built ({result.gaps} partial), "
                       f"{result.tiles} tiles, {result.failed} failed")
        print(f"\n  built {result.n} · partial {result.gaps} · "
              f"failed {result.failed} · tiles {result.tiles}")
    return 0


# ── self-test (no network, no credentials) ───────────────────────────────────

CONTRACT_KEYS = {"version", "computed_at", "id", "address", "center", "tiles",
                 "parcel", "pois", "routes", "comps", "catchments",
                 "subject_value", "build_notes"}


def self_test():
    """Exit 0 iff: (1) pixel<->lat/lon georeference round-trips within 1e-4 deg on
    sample points, and (2) a living_map dict assembled from sample inputs has
    exactly the contract keys — all with NO network/credentials."""
    ok = True

    # (1) Georeference round-trip on real sample points.
    ref = Path("/home/fields/living_map_ref/sample_living_map_data.json")
    sample_points = []
    if ref.exists():
        data = json.loads(ref.read_text())
        for inst in data:
            clat, clon = inst["lat"], inst["lon"]
            # centre, parcel vertices, comps, poi coords — a spread of real points
            pts = [(clat, clon)]
            for ring in (inst.get("parcel") or []):
                pts += [(p[0], p[1]) for p in ring[:3]]
            for c in (inst.get("comps") or [])[:3]:
                pts.append((c["lat"], c["lon"]))
            for p in (inst.get("pois") or [])[:3]:
                pts.append((p["lat"], p["lon"]))
            sample_points.append((clat, clon, pts))
    else:
        # Fallback synthetic points if the reference file is absent.
        sample_points = [(-28.0698, 153.3922,
                          [(-28.0698, 153.3922), (-28.0705, 153.3930), (-28.0690, 153.3915)])]

    max_err = 0.0
    n_checked = 0
    for clat, clon, pts in sample_points:
        for zoom in (ZOOM_HOUSE, ZOOM_STREET, ZOOM_SUBURB):
            for (lat, lon) in pts:
                px, py = latlon_to_pixel(lat, lon, clat, clon, zoom)
                rlat, rlon = pixel_to_latlon(px, py, clat, clon, zoom)
                err = max(abs(rlat - lat), abs(rlon - lon))
                max_err = max(max_err, err)
                n_checked += 1
    print(f"[1] georeference round-trip: {n_checked} points, max error {max_err:.2e} deg", end=" ")
    if max_err < 1e-4:
        print("✓")
    else:
        print("✗ (exceeds 1e-4)")
        ok = False

    # Sanity: a known pixel offset must move lat/lon in the right direction.
    clat, clon, zoom = -28.0698, 153.3922, ZOOM_HOUSE
    W = H = TILE_PX * TILE_SCALE
    c_lat, c_lon = pixel_to_latlon(W / 2, H / 2, clat, clon, zoom)
    if not (abs(c_lat - clat) < 1e-9 and abs(c_lon - clon) < 1e-9):
        print("[1b] centre pixel does not map back to centre ✗")
        ok = False
    right_lat, right_lon = pixel_to_latlon(W / 2 + 100, H / 2, clat, clon, zoom)
    down_lat, _ = pixel_to_latlon(W / 2, H / 2 + 100, clat, clon, zoom)
    if not (right_lon > clon and down_lat < clat):
        print("[1c] pixel axes point the wrong way ✗")
        ok = False

    # (2) Assemble a living_map from sample-derived inputs — pure, offline.
    inst = data[0] if ref.exists() else {
        "id": "test", "addr": "1 Test St", "lat": clat, "lon": clon,
        "parcel": [[[clat, clon], [clat + 1e-4, clon], [clat, clon + 1e-4]]],
        "parcel_lotplan": "1RP1", "parcel_area": 500.0,
        "pois": [{"name": "P", "cat": "School", "lat": clat + 1e-3, "lon": clon}],
        "comps": [{"address": "2 Test St", "price": 1000000,
                   "lat": clat + 1e-3, "lon": clon + 1e-3, "dist": 0.2}],
        "catchments": [{"level": "Primary", "school": "Test SS",
                        "poly": [[clat, clon]]}],
    }
    center = {"lat": inst["lat"], "lon": inst["lon"]}

    # POIs: reuse the sample raw shape; drive table empty -> drive fields None,
    # walk time still estimated. Exercises build_pois end-to-end.
    raw_pois = [{"name": p["name"], "cat": p["cat"], "lat": p["lat"], "lon": p["lon"]}
                for p in (inst.get("pois") or [])]
    pois = build_pois(center, raw_pois, {})
    assert all(p["walk_min"] is not None for p in pois), "walk estimate missing"
    assert all(p["straight_m"] >= 0 for p in pois), "straight_m negative"

    # Comps: build from a synthetic *valuation output* (adjusted_comparables), with
    # a geocode dict standing in for Nominatim. Proves comps_from_valuation reads
    # adjusted_comparables and ignores an (empty) live `comparables` field.
    fake_valuation = {
        "comparables": [],   # the flip-flop field — must be IGNORED
        "adjusted_comparables": [
            {"address": "81 Thorngate Drive", "sale_price": 1410000.0,
             "sale_date": "2026-03-03", "adjusted_price": 1385000,
             "total_adjustment_pct": -0.018, "distance_km": 0.51},
        ],
        "confidence": {"reconciled_valuation": 1500000,
                       "range": {"low": 1320000, "high": 1680000}},
        "metadata": {"directional_only": False},
    }
    raw_comps = comps_from_valuation(fake_valuation)
    assert len(raw_comps) == 1, "comps_from_valuation must read adjusted_comparables, not comparables"
    geo = {"81 Thorngate Drive": (center["lat"] + 1e-3, center["lon"] + 1e-3)}
    comps = build_comps(center, raw_comps, geo)
    assert comps and comps[0]["sale_price"] == 1410000.0, "exact sale price not preserved"
    assert "compass" in comps[0] and "bearing" in comps[0], "bearing/compass missing"

    subject_value = subject_value_from_valuation(fake_valuation)
    assert subject_value == {"estimate": 1500000, "low": 1320000, "high": 1680000}, \
        "subject_value range wrong"
    # directional_only must suppress the range.
    assert subject_value_from_valuation({**fake_valuation,
                                         "metadata": {"directional_only": True}}) is None, \
        "directional_only did not suppress the range"

    # School-name expansion.
    assert expand_school_name("Robina SS") == "Robina State School"
    assert expand_school_name("Varsity College SHS") == "Varsity College State High School"

    parcel = None
    if inst.get("parcel"):
        # sample parcel rings are already [[lat,lon]] — wrap into the contract shape.
        parcel = {"rings": inst["parcel"], "lotplan": inst.get("parcel_lotplan"),
                  "area_sqm": inst.get("parcel_area")}
    catchments = [{"level": c["level"], "school": expand_school_name(c["school"]),
                   "poly": c["poly"]} for c in (inst.get("catchments") or [])]

    lm = assemble_living_map(
        prop_id=str(inst["id"]), address=inst.get("addr"), center=center,
        tiles={"house": "u://house", "street": "u://street",
               "suburb": "u://suburb", "city": "u://city"},
        parcel=parcel, pois=pois, routes=[], comps=comps,
        catchments=catchments, subject_value=subject_value,
        gaps=["routes: 0/4 destinations routed (offline self-test)"])

    keys = set(lm.keys())
    print(f"[2] living_map keys: {sorted(keys)}", end=" ")
    if keys == CONTRACT_KEYS:
        print("✓")
    else:
        print(f"✗ (missing {CONTRACT_KEYS - keys}, extra {keys - CONTRACT_KEYS})")
        ok = False

    # tiles sub-contract
    if set(lm["tiles"].keys()) != {"house", "street", "suburb", "city"}:
        print("[2b] tiles keys wrong ✗")
        ok = False
    # build_notes.gaps present and a list
    if not isinstance(lm.get("build_notes", {}).get("gaps"), list):
        print("[2c] build_notes.gaps not a list ✗")
        ok = False

    # (3) job_run wrapper + zero-output raise must exist in the source.
    src = Path(__file__).read_text()
    checks = [
        ('job_run("precompute_living_map"' in src, "job_run wrapper present"),
        ("cadence_hours=24" in src, "cadence_hours=24"),
        ("raise RuntimeError" in src and "eligible" in src, "zero-output RAISE"),
        ("load_env()" in src, "load_env() called"),
        ("adjusted_comparables" in src, "reads adjusted_comparables (not live comparables)"),
    ]
    for passed, label in checks:
        print(f"[3] {label}: {'✓' if passed else '✗'}")
        ok = ok and passed

    print("\nSELF-TEST", "PASSED" if ok else "FAILED")
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
