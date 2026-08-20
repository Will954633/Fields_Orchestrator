"""shared/block_geometry.py — frontage, depth, rectangularity from cadastral rings.

Conjunction Program Tier 2.3. Turns `cadastral_polygon.rings` (a list of
[lng, lat] pairs) into the physical block facts the buyer story leans on, so
"rectangular" / "usable" / "~20m frontage" are measured, never estimated from an
aerial. This is the library the comp builder and the dossier both call.

93 Burleigh Street was described in a draft thesis as "rectangular" — the cadastre
shows a wedge (front ~19.9m, rear ~18.4m, sides ~40.9m / ~49.0m). This module exists
so that class of overclaim is caught before it reaches a buyer.

Method: rings are projected to a local east-north metre plane (equirectangular about
the polygon centroid — accurate to <0.1% over a suburban lot), then:
  * area via the shoelace formula
  * a minimum-area bounding rectangle via rotating calipers over the convex hull
  * rectangularity = polygon_area / bounding_rectangle_area  (1.0 == perfect rectangle)
  * frontage estimated as the SHORTER bounding-rectangle side, depth as the longer
    (a suburban lot is far deeper than wide; the short side faces the street). This is
    an estimate and is labelled as one — a true frontage needs the street edge, which
    the cadastre alone does not identify.

No external geometry deps — pure Python so it runs anywhere the pipeline does.
"""

import math
from typing import Optional, List, Tuple, Dict

_EARTH_R = 6378137.0  # WGS84 equatorial radius, metres


def _project(rings_lnglat: List[List[float]], lat0: float, lon0: float) -> List[Tuple[float, float]]:
    """Equirectangular projection of [lng,lat] points to local (east, north) metres."""
    coslat = math.cos(math.radians(lat0))
    out = []
    for lng, lat in rings_lnglat:
        e = math.radians(lng - lon0) * _EARTH_R * coslat
        n = math.radians(lat - lat0) * _EARTH_R
        out.append((e, n))
    return out


def _shoelace_area(pts: List[Tuple[float, float]]) -> float:
    a = 0.0
    n = len(pts)
    for i in range(n):
        x1, y1 = pts[i]
        x2, y2 = pts[(i + 1) % n]
        a += x1 * y2 - x2 * y1
    return abs(a) / 2.0


def _convex_hull(pts: List[Tuple[float, float]]) -> List[Tuple[float, float]]:
    pts = sorted(set(pts))
    if len(pts) <= 2:
        return pts

    def cross(o, a, b):
        return (a[0] - o[0]) * (b[1] - o[1]) - (a[1] - o[1]) * (b[0] - o[0])

    lower = []
    for p in pts:
        while len(lower) >= 2 and cross(lower[-2], lower[-1], p) <= 0:
            lower.pop()
        lower.append(p)
    upper = []
    for p in reversed(pts):
        while len(upper) >= 2 and cross(upper[-2], upper[-1], p) <= 0:
            upper.pop()
        upper.append(p)
    return lower[:-1] + upper[:-1]


def _min_area_rect(hull: List[Tuple[float, float]]) -> Tuple[float, float, float]:
    """Rotating-calipers minimum-area bounding rectangle. Returns (width, length, area)."""
    if len(hull) < 3:
        xs = [p[0] for p in hull]
        ys = [p[1] for p in hull]
        w = (max(xs) - min(xs)) or 0.0
        h = (max(ys) - min(ys)) or 0.0
        return (min(w, h), max(w, h), w * h)

    best = None
    n = len(hull)
    for i in range(n):
        x1, y1 = hull[i]
        x2, y2 = hull[(i + 1) % n]
        ex, ey = x2 - x1, y2 - y1
        elen = math.hypot(ex, ey)
        if elen == 0:
            continue
        ux, uy = ex / elen, ey / elen      # edge direction
        vx, vy = -uy, ux                   # normal
        min_u = min_v = float("inf")
        max_u = max_v = float("-inf")
        for px, py in hull:
            du = px * ux + py * uy
            dv = px * vx + py * vy
            min_u, max_u = min(min_u, du), max(max_u, du)
            min_v, max_v = min(min_v, dv), max(max_v, dv)
        w = max_u - min_u
        h = max_v - min_v
        area = w * h
        if best is None or area < best[2]:
            best = (min(w, h), max(w, h), area)
    return best


def compute_block_geometry(cadastral_polygon: Optional[Dict]) -> Optional[Dict]:
    """From a `cadastral_polygon` dict (with `rings`) return measured block facts, or None.

    Returns:
      {
        area_sqm, perimeter_m,
        frontage_m_est, depth_m_est,   # from the min-area rectangle; ESTIMATES
        rectangularity,                # 0..1, polygon area / bounding-rect area
        shape_label,                   # 'rectangular' | 'regular' | 'irregular' | 'wedge/irregular'
        edges_m,                       # sorted list of boundary edge lengths
        n_corners,
        note
      }
    """
    if not cadastral_polygon:
        return None
    rings = cadastral_polygon.get("rings")
    if not rings or not rings[0] or len(rings[0]) < 4:
        return None

    ring = rings[0]
    # Drop the duplicate closing vertex if present.
    if ring[0] == ring[-1]:
        ring = ring[:-1]
    if len(ring) < 3:
        return None

    lat0 = sum(p[1] for p in ring) / len(ring)
    lon0 = sum(p[0] for p in ring) / len(ring)
    pts = _project(ring, lat0, lon0)

    area = _shoelace_area(pts)
    edges = []
    for i in range(len(pts)):
        x1, y1 = pts[i]
        x2, y2 = pts[(i + 1) % len(pts)]
        edges.append(math.hypot(x2 - x1, y2 - y1))
    perimeter = sum(edges)

    hull = _convex_hull(pts)
    width, length, rect_area = _min_area_rect(hull)
    rectangularity = (area / rect_area) if rect_area > 0 else None

    if rectangularity is None:
        shape = "unknown"
    elif rectangularity >= 0.95:
        shape = "rectangular"
    elif rectangularity >= 0.85:
        shape = "regular"
    elif rectangularity >= 0.70:
        shape = "wedge/irregular"
    else:
        shape = "irregular"

    return {
        "area_sqm": round(area, 1),
        "perimeter_m": round(perimeter, 1),
        "frontage_m_est": round(width, 1),
        "depth_m_est": round(length, 1),
        "rectangularity": round(rectangularity, 3) if rectangularity is not None else None,
        "shape_label": shape,
        "edges_m": sorted(round(e, 1) for e in edges),
        "n_corners": len(ring),
        "note": ("frontage/depth are the short/long sides of the minimum-area bounding "
                 "rectangle — estimates; a true street frontage needs the road-facing edge, "
                 "which the cadastre alone does not identify."),
    }
