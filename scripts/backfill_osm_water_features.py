#!/usr/bin/env python3
"""
Backfill `osm_location_features.water_features` for the target suburbs.

WHY THIS EXISTS
───────────────────────────────────────────────────────────────────────────────
Water views are being valued as waterfront. `detect_waterfront()` treats a GPT-4
Vision read of the marketing photos (`outdoor.water_views`) as sufficient evidence
of frontage, and `precompute_valuations.py` then compares those homes only to
genuine water-frontage sales. Measured 2026-08-07 over 625 detached houses:

    flagged waterfront ....... 59 homes, median error +8.0%, MAE 13.5%, 73% high
    of which NOT waterfront
    by geometry .............. 41 homes (69%), median error +10.4%, MAE 14.9%

`shared/waterfront.py::classify_water_relationship()` fixes this by deciding
frontage from geometry instead of photographs — but **53% of homes had no
`water_features` block at all**, so it could not be trusted as the cohort
authority. This job closes that gap.

WHY IT DOES NOT CALL THE API PER PROPERTY
───────────────────────────────────────────────────────────────────────────────
The original enricher issued one Overpass query per property. For ~24,000
properties that is both extremely slow and an unreasonable load on a free public
service. Water geometry does not vary by property — only the distance to it does.

So this fetches **every water feature in the region once** (351 elements, ~78s)
and computes distances locally. One request replaces ~24,000.

⚠ The whole `overpass-api.de` family (including lz4. and z.) returns **406** to
this VM regardless of User-Agent. `overpass.kumi.systems` and
`overpass.private.coffee` both work. Do not "fix" a 406 by removing the
User-Agent — without one you get 406 everywhere.

⚠ ADDED BEYOND THE ORIGINAL SCHEMA: `lakefront`. The original
`extract_water_features()` sets `waterfront_type` for canal, coastline and river
only — a home ON a lake got `waterfront_type: 'none'` and
`waterfront_premium_eligible: False`. Two of our three target suburbs are lake
suburbs and 167 of 351 water elements in the region are `natural=water`, so the
original logic could not see the most common kind of frontage we have. Homes
within 30 m of a water body now get `waterfront_type: 'lakefront'`, matching the
threshold the original uses for rivers.

⚠ THE TAG SET MUST MATCH `WATER_TYPES`. A first version of the regional query
omitted `drain` and `ditch` — which `WATER_TYPES` handles — and produced
distances up to 200 m too large on the Burleigh Waters drainage canals, while
agreeing to 0.0 m everywhere else. Validated against properties whose value the
per-property API had already stored; keep that check when changing the query.
"""

import json
import math
import os
import sys
import time
from collections import defaultdict

_HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.dirname(_HERE))   # repo root, for shared.*
sys.path.insert(0, _HERE)                    # scripts/, for job_status

import requests

from shared.env import load_env
from shared.db import get_gold_coast_db
from job_status import job_run

load_env()

SUBURBS = ("robina", "varsity_lakes", "burleigh_waters")

# Padded ~1 km beyond the coordinate extent of the three suburbs, so water just
# outside the boundary still registers for homes on the edge.
BBOX = (-28.1115, 153.3528, -28.0392, 153.4562)  # S, W, N, E

MIRRORS = (
    "https://overpass.kumi.systems/api/interpreter",
    "https://overpass.private.coffee/api/interpreter",
)
USER_AGENT = ("FieldsEstate-PropertyValuation/1.0 "
              "(+https://fieldsestate.com.au; will@fieldsestate.com.au)")

GEOMETRY_CACHE = "/tmp/gc_water_geometry.json"

# Thresholds, matching the original extract_water_features() where they exist.
CANAL_FRONT_M = 30
CANAL_ADJACENT_M = 100
COASTLINE_FRONT_M = 50
RIVER_FRONT_M = 30
LAKE_FRONT_M = 30      # added — see module docstring

WATER_TYPES = {
    "river": "river", "stream": "stream", "canal": "canal",
    "riverbank": "river", "drain": "drain", "ditch": "ditch",
}


# ── geometry ─────────────────────────────────────────────────────────────────

def _to_metres(lat, lon, lat0):
    """Local equirectangular projection. Accurate to well under a metre over a
    region this small, and far cheaper than haversine per segment."""
    return (math.radians(lon) * 6371000.0 * math.cos(math.radians(lat0)),
            math.radians(lat) * 6371000.0)


def _point_segment_distance(px, py, ax, ay, bx, by):
    dx, dy = bx - ax, by - ay
    if dx == 0 and dy == 0:
        return math.hypot(px - ax, py - ay)
    t = max(0.0, min(1.0, ((px - ax) * dx + (py - ay) * dy) / (dx * dx + dy * dy)))
    return math.hypot(px - (ax + t * dx), py - (ay + t * dy))


def fetch_water_geometry(use_cache=True):
    """Fetch every water element in the region. One request, not one per property."""
    if use_cache and os.path.exists(GEOMETRY_CACHE):
        with open(GEOMETRY_CACHE) as fh:
            data = json.load(fh)
        print(f"  using cached geometry: {len(data.get('elements', []))} elements")
        return data

    s, w, n, e = BBOX
    query = f"""[out:json][timeout:180];
(
  way["natural"="water"]({s},{w},{n},{e});
  way["waterway"~"^(river|stream|canal|riverbank|drain|ditch)$"]({s},{w},{n},{e});
  way["natural"="wetland"]({s},{w},{n},{e});
  way["landuse"="reservoir"]({s},{w},{n},{e});
  relation["natural"="water"]({s},{w},{n},{e});
  way["natural"="coastline"]({s},{w},{n},{e});
);
out geom;"""

    last_error = None
    for mirror in MIRRORS:
        try:
            started = time.time()
            resp = requests.post(mirror, data={"data": query},
                                 headers={"User-Agent": USER_AGENT}, timeout=240)
            if resp.status_code == 200:
                data = resp.json()
                print(f"  {mirror.split('//')[1].split('/')[0]}: "
                      f"{len(data.get('elements', []))} elements in {time.time() - started:.0f}s")
                with open(GEOMETRY_CACHE, "w") as fh:
                    json.dump(data, fh)
                return data
            last_error = f"{mirror} returned {resp.status_code}"
            print(f"  {last_error}")
        except Exception as exc:            # noqa: BLE001 — try the next mirror
            last_error = f"{mirror}: {type(exc).__name__}: {exc}"
            print(f"  {last_error}")

    # Rule 7b: a job that cannot reach its data source must FAIL, not quietly
    # write nothing and report success.
    raise RuntimeError(f"no Overpass mirror answered — last error: {last_error}")


def build_index(osm_data, lat0):
    """Bucket every water segment into a 250 m grid so each property only tests
    nearby geometry. Without this it is 26,000 properties x every segment."""
    grid = defaultdict(list)
    cell = 250.0
    kept = 0
    for element in osm_data.get("elements", []):
        tags = element.get("tags") or {}
        if "waterway" in tags:
            wtype = WATER_TYPES.get(tags["waterway"], "waterway")
        elif tags.get("natural") in ("water", "wetland") or tags.get("landuse") == "reservoir":
            wtype = "water_body"
        elif tags.get("natural") == "coastline":
            wtype = "coastline"
        else:
            continue

        geometry = element.get("geometry") or []
        if len(geometry) < 2:
            continue
        pts = [_to_metres(g["lat"], g["lon"], lat0) for g in geometry]
        name = tags.get("name", "Unnamed")
        for i in range(len(pts) - 1):
            (ax, ay), (bx, by) = pts[i], pts[i + 1]
            seg = (ax, ay, bx, by, wtype, name)
            kept += 1
            for cx in range(int(min(ax, bx) // cell), int(max(ax, bx) // cell) + 1):
                for cy in range(int(min(ay, by) // cell), int(max(ay, by) // cell) + 1):
                    grid[(cx, cy)].append(seg)
    return grid, cell, kept


def nearest_water(px, py, grid, cell, max_radius_m=2000):
    """Nearest segment of each water type, expanding the search ring until found."""
    best = {}
    rings = 1
    while rings * cell <= max_radius_m:
        cx0, cy0 = int(px // cell), int(py // cell)
        seen = set()
        for cx in range(cx0 - rings, cx0 + rings + 1):
            for cy in range(cy0 - rings, cy0 + rings + 1):
                for seg in grid.get((cx, cy), ()):
                    if id(seg) in seen:
                        continue
                    seen.add(id(seg))
                    ax, ay, bx, by, wtype, name = seg
                    d = _point_segment_distance(px, py, ax, ay, bx, by)
                    if wtype not in best or d < best[wtype][0]:
                        best[wtype] = (d, name)
        # One extra ring beyond the first hit, so a slightly-further-but-closer
        # segment in an adjacent cell is not missed.
        if best and rings >= 2:
            break
        rings += 1
    return best


def water_features(px, py, grid, cell):
    """Build the water_features block, schema-identical to the original."""
    best = nearest_water(px, py, grid, cell)
    out = {
        "distance_to_water_m": None,
        "nearest_water_type": None,
        "canal_frontage": False,
        "canal_adjacent": False,
        "waterfront_type": "none",
        "waterfront_premium_eligible": False,
        "distance_to_canal_m": None,
    }
    if not best:
        return out

    wtype, (dist, _name) = min(best.items(), key=lambda kv: kv[1][0])
    out["distance_to_water_m"] = round(dist, 1)
    out["nearest_water_type"] = wtype

    if "canal" in best:
        canal_d = best["canal"][0]
        out["distance_to_canal_m"] = round(canal_d, 1)
        if canal_d < CANAL_FRONT_M:
            out["canal_frontage"] = True
            out["waterfront_type"] = "canal_front"
            out["waterfront_premium_eligible"] = True
        elif canal_d < CANAL_ADJACENT_M:
            out["canal_adjacent"] = True
            out["waterfront_type"] = "canal_adjacent"

    if wtype == "coastline" and dist < COASTLINE_FRONT_M:
        out["waterfront_type"] = "oceanfront"
        out["waterfront_premium_eligible"] = True
    elif wtype == "river" and dist < RIVER_FRONT_M:
        out["waterfront_type"] = "riverfront"
        out["waterfront_premium_eligible"] = True
    elif wtype == "water_body" and dist < LAKE_FRONT_M and out["waterfront_type"] == "none":
        # Added 2026-08-07 — the original set no type for lakes at all.
        out["waterfront_type"] = "lakefront"
        out["waterfront_premium_eligible"] = True

    return out


def main():
    force = "--force" in sys.argv
    limit = None
    if "--limit" in sys.argv:
        limit = int(sys.argv[sys.argv.index("--limit") + 1])

    with job_run("backfill_osm_water_features", cadence_hours=168,
                 title="OSM Water Features Backfill") as beat:
        osm_data = fetch_water_geometry()
        lat0 = (BBOX[0] + BBOX[2]) / 2
        grid, cell, n_segments = build_index(osm_data, lat0)
        if n_segments == 0:
            raise RuntimeError("water geometry parsed to 0 segments — the query or "
                               "the response shape changed")
        print(f"  indexed {n_segments} water segments")

        db = get_gold_coast_db()
        written = skipped = no_coords = 0
        eligible = 0

        for suburb in SUBURBS:
            query = {"LATITUDE": {"$exists": True}, "LONGITUDE": {"$exists": True}}
            if not force:
                query["osm_location_features.water_features"] = {"$exists": False}
            cursor = db[suburb].find(query, {"LATITUDE": 1, "LONGITUDE": 1})
            if limit:
                cursor = cursor.limit(limit)

            for doc in cursor:
                eligible += 1
                try:
                    lat, lon = float(doc["LATITUDE"]), float(doc["LONGITUDE"])
                except (TypeError, ValueError):
                    no_coords += 1
                    continue
                px, py = _to_metres(lat, lon, lat0)
                feats = water_features(px, py, grid, cell)
                if feats["distance_to_water_m"] is None:
                    skipped += 1
                    continue
                # Dotted $set so a co-existing road_classification block survives.
                db[suburb].update_one(
                    {"_id": doc["_id"]},
                    {"$set": {
                        "osm_location_features.water_features": feats,
                        "osm_location_features.metadata.water_backfilled_at":
                            time.strftime("%Y-%m-%dT%H:%M:%S"),
                        "osm_location_features.metadata.water_source":
                            "regional_overpass_batch_v1",
                    }},
                )
                written += 1
            print(f"  {suburb}: {written} written so far")

        beat.metrics = {"written": written, "eligible": eligible,
                        "no_coords": no_coords, "no_water_found": skipped,
                        "segments": n_segments}

        # Rule 7b — name the zero-output path and raise on it. An empty queue is
        # success (everything already backfilled); eligible-but-nothing-written is
        # a failure wearing a success costume.
        if eligible and not written:
            raise RuntimeError(
                f"{eligible} properties were eligible but 0 were written "
                f"({no_coords} bad coords, {skipped} no water within range) — "
                "the geometry index or the coordinate fields are broken")

        beat.detail = f"{written} properties given water_features ({eligible} eligible)"
        print(f"\n  wrote {written} / {eligible} eligible "
              f"({no_coords} bad coords, {skipped} no water in range)")


if __name__ == "__main__":
    main()
