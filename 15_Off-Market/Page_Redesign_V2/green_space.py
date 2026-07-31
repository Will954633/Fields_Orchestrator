#!/usr/bin/env python3
"""
green_space.py — PROTOTYPE: scalable "what's at your boundary?" from OSM POLYGONS
and LINES.

Our POI data is 788 Google POINTS — a distance to a point can't tell you
adjacency. This does: a ONE-TIME bulk harvest of every Gold Coast boundary
feature from OpenStreetMap — parks, bushland, reserves, golf courses, water and
waterways (PREMIUM), plus commercial / retail / industrial land, railway lines
and main roads (DETRACTOR) — then a point-to-nearest-EDGE distance for any
property. Deterministic, free, scalable to all 312k properties (no per-property
AI; satellite covers only ~5% of stock).

  python3 green_space.py --harvest      # one-time: fetch features -> cache json
  python3 green_space.py --test LAT LON # classify a point (premium + detractor)

Geometry by hand (no shapely): equirectangular projection to metres, ray-cast
point-in-polygon for closed rings, point-to-segment distance for polygon edges
and open lines (waterways, rail, roads).
"""
import sys
import json
import math
import argparse
from pathlib import Path

import requests

HERE = Path(__file__).resolve().parent
CACHE = HERE / "green_space_polygons.json"
BBOX = (-28.16, 153.31, -27.98, 153.48)   # 9 southern-GC suburbs: S,W,N,E

OVERPASS_ENDPOINTS = [
    "https://maps.mail.ru/osm/tools/overpass/api/interpreter",
    "https://overpass-api.de/api/interpreter",
    "https://overpass.kumi.systems/api/interpreter",
]
UA = {"User-Agent": "FieldsEstate-boundary-prototype/1.0 (will@fieldsestate.com.au)"}

# (osm_key, osm_value) -> (friendly label, polarity). First match wins.
CLASS = {
    ("leisure", "nature_reserve"): ("nature reserve", "premium"),
    ("natural", "wood"): ("bushland", "premium"),
    ("natural", "scrub"): ("bushland", "premium"),
    ("natural", "heath"): ("bushland", "premium"),
    ("landuse", "forest"): ("bushland", "premium"),
    ("leisure", "park"): ("park", "premium"),
    ("leisure", "golf_course"): ("golf course", "premium"),
    ("landuse", "recreation_ground"): ("reserve", "premium"),
    ("leisure", "recreation_ground"): ("reserve", "premium"),
    ("landuse", "village_green"): ("reserve", "premium"),
    ("leisure", "garden"): ("gardens", "premium"),
    ("natural", "water"): ("water", "premium"),
    ("natural", "wetland"): ("wetland", "premium"),
    ("natural", "beach"): ("beach", "premium"),
    ("waterway", "river"): ("river", "premium"),
    ("waterway", "canal"): ("canal", "premium"),
    ("waterway", "stream"): ("creek", "premium"),
    ("landuse", "grass"): ("open space", "premium"),
    ("landuse", "meadow"): ("open space", "premium"),
    # detractors
    ("landuse", "commercial"): ("commercial land", "detractor"),
    ("landuse", "retail"): ("a retail/shopping area", "detractor"),
    ("landuse", "industrial"): ("industrial land", "detractor"),
    ("railway", "rail"): ("a railway line", "detractor"),
    ("highway", "motorway"): ("a motorway", "detractor"),
    ("highway", "trunk"): ("a main road", "detractor"),
    ("highway", "primary"): ("a main road", "detractor"),
}


def _query(bbox):
    s, w, n, e = bbox
    b = f"({s},{w},{n},{e})"
    return f"""[out:json][timeout:180];
(
  way["leisure"~"park|nature_reserve|garden|golf_course|recreation_ground"]{b};
  way["landuse"~"recreation_ground|forest|grass|meadow|village_green|commercial|retail|industrial"]{b};
  way["natural"~"wood|scrub|heath|water|wetland|beach"]{b};
  way["waterway"~"river|canal|stream"]{b};
  way["railway"="rail"]{b};
  way["highway"~"motorway|trunk|primary"]{b};
  relation["leisure"~"park|nature_reserve|golf_course"]{b};
  relation["natural"~"water|wood"]{b};
  relation["landuse"~"forest|commercial|industrial"]{b};
);
out geom;"""


def _class_of(tags):
    for (k, v), meta in CLASS.items():
        if tags.get(k) == v:
            return meta
    return ("green space", "premium")


def _closed(ring):
    return len(ring) >= 4 and abs(ring[0][0] - ring[-1][0]) < 1e-9 and abs(ring[0][1] - ring[-1][1]) < 1e-9


def harvest(bbox=BBOX):
    q = _query(bbox)
    data = None
    for ep in OVERPASS_ENDPOINTS:
        try:
            r = requests.post(ep, data={"data": q}, headers=UA, timeout=180)
            if r.status_code == 200 and r.text.strip().startswith("{"):
                data = r.json()
                print(f"  fetched from {ep.split('/')[2]}", file=sys.stderr)
                break
            print(f"  {ep.split('/')[2]} -> {r.status_code}", file=sys.stderr)
        except Exception as ex:
            print(f"  {ep.split('/')[2]} ERR {str(ex)[:80]}", file=sys.stderr)
    if not data:
        raise SystemExit("all Overpass endpoints failed")

    feats = []

    def add(tags, geom):
        ring = [(g["lat"], g["lon"]) for g in geom if "lat" in g]
        if len(ring) < 2:
            return
        label, polarity = _class_of(tags)
        feats.append({"name": tags.get("name"), "kind": label, "polarity": polarity,
                      "closed": _closed(ring), "ring": ring})

    for el in data.get("elements", []):
        tags = el.get("tags", {}) or {}
        if el.get("type") == "way":
            add(tags, el.get("geometry") or [])
        elif el.get("type") == "relation":
            for m in el.get("members", []):
                if m.get("role") in ("outer", "", None) and m.get("geometry"):
                    add(tags, m["geometry"])

    CACHE.write_text(json.dumps(feats))
    from collections import Counter
    kinds = Counter(f"{p['kind']}/{p['polarity']}" for p in feats)
    print(f"→ {len(feats)} features cached to {CACHE.name}", file=sys.stderr)
    print(f"  {dict(kinds)}", file=sys.stderr)
    return feats


# --------- geometry (local equirectangular metres) ---------

def _project(lat, lon, lat0):
    return (math.radians(lon) * math.cos(math.radians(lat0)) * 6371000,
            math.radians(lat) * 6371000)


def _pt_seg(px, py, ax, ay, bx, by):
    dx, dy = bx - ax, by - ay
    if dx == 0 and dy == 0:
        return math.hypot(px - ax, py - ay)
    t = max(0.0, min(1.0, ((px - ax) * dx + (py - ay) * dy) / (dx * dx + dy * dy)))
    return math.hypot(px - (ax + t * dx), py - (ay + t * dy))


def _in_ring(px, py, ring_xy):
    inside = False
    n = len(ring_xy)
    j = n - 1
    for i in range(n):
        xi, yi = ring_xy[i]
        xj, yj = ring_xy[j]
        if ((yi > py) != (yj > py)) and (px < (xj - xi) * (py - yi) / (yj - yi) + xi):
            inside = not inside
        j = i
    return inside


_FEATS = None
_GRID = None
_CELL = 0.005   # ~500m cells; > any search radius, so a 3x3 neighbourhood covers it


def load():
    global _FEATS
    if _FEATS is None:
        _FEATS = json.loads(CACHE.read_text()) if CACHE.exists() else []
    return _FEATS


def _cell(lat, lon):
    return (int(math.floor(lat / _CELL)), int(math.floor(lon / _CELL)))


def _build_grid():
    """Spatial hash: feature index -> every grid cell its bbox touches. Turns the
    per-property scan from O(all features) into O(features in the 3x3 nbhd)."""
    global _GRID
    if _GRID is not None:
        return _GRID
    _GRID = {}
    for i, p in enumerate(load()):
        lats = [c[0] for c in p["ring"]]
        lons = [c[1] for c in p["ring"]]
        for cy in range(_cell(min(lats), min(lons))[0], _cell(max(lats), max(lons))[0] + 1):
            for cx in range(_cell(min(lats), min(lons))[1], _cell(max(lats), max(lons))[1] + 1):
                _GRID.setdefault((cy, cx), []).append(i)
    return _GRID


def _candidates(lat, lon):
    grid = _build_grid()
    cy, cx = _cell(lat, lon)
    seen = set()
    for dy in (-1, 0, 1):
        for dx in (-1, 0, 1):
            for i in grid.get((cy + dy, cx + dx), ()):
                seen.add(i)
    feats = load()
    return [feats[i] for i in seen]


def _edge_dist(px, py, ring_xy, closed):
    d = min(_pt_seg(px, py, *ring_xy[i], *ring_xy[i + 1]) for i in range(len(ring_xy) - 1))
    if closed and _in_ring(px, py, ring_xy):
        return 0.0
    return d


def _relation(edge_m, polarity):
    if polarity == "premium":
        if edge_m <= 25:
            return "backs onto"
        if edge_m <= 80:
            return "adjoins"
        if edge_m <= 200:
            return "steps from"
        return None
    else:  # detractor — only matters close
        if edge_m <= 30:
            return "backs onto"
        if edge_m <= 90:
            return "close to"
        return None


def classify(lat, lon):
    """Nearest PREMIUM and nearest DETRACTOR boundary feature for a point."""
    if lat is None or lon is None:
        return None
    px, py = _project(lat, lon, lat)
    best = {"premium": None, "detractor": None}
    for p in _candidates(lat, lon):
        ring_xy = [_project(la, lo, lat) for la, lo in p["ring"]]
        e = round(_edge_dist(px, py, ring_xy, p["closed"]), 1)
        slot = p["polarity"]
        cur = best.get(slot)
        if cur is None or e < cur["edge_m"]:
            best[slot] = {"name": p["name"], "kind": p["kind"], "edge_m": e}
    out = {}
    for slot in ("premium", "detractor"):
        g = best[slot]
        if not g:
            continue
        rel = _relation(g["edge_m"], slot)
        if rel:
            g["relation"] = rel
            out[slot] = g
    return out or None


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--harvest", action="store_true")
    ap.add_argument("--test", nargs=2, type=float, metavar=("LAT", "LON"))
    args = ap.parse_args()
    if args.harvest:
        harvest()
    if args.test:
        print(json.dumps(classify(*args.test), indent=2))


if __name__ == "__main__":
    main()
