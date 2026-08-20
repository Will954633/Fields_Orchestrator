#!/usr/bin/env python3
"""
backfill_cadastral_polygons.py — fill `cadastral_polygon.rings` by point-in-polygon.

WHY (2026-08-20). Block geometry (frontage / depth / rectangularity) is derived from
`cadastral_polygon.rings`, but only ~40 of ~417 in-window sold docs per target suburb
carry it — the canonical writer (render_property_aerial.py) only fetches a polygon when
a report is rendered, and resolves it by LOT/PLAN (a where-clause), so any sold document
that was never rendered has no geometry even though its coordinates are on file.

This backfill resolves the parcel DIRECTLY from the document's own lat/long by a
point-in-polygon query against the same public source layer:

    Queensland Government cadastre — PlanningCadastre/LandParcelPropertyFramework,
    MapServer layer 4, queried with an esriGeometryPoint + esriSpatialRelIntersects.
    Public, free, WGS84. Returns lotplan, lot_area and the parcel rings for the ONE
    parcel the point falls inside. No local shapefile / GeoJSON / cadastre collection
    exists on the VM — this live service is the source of truth the pipeline already
    uses (see scripts/render_property_aerial.py and scripts/property_reports/lot_boundary.py).

Field confirmed via scripts/db_fields.py --find cadastral / rings:
    Gold_Coast.<suburb>.cadastral_polygon.rings   array[array[array[float]]]  ([lng,lat])
Coordinate fields confirmed (Rule 8):
    LATITUDE / LONGITUDE  (float, primary, ~82% fill on sold docs)
    geocoded_coordinates.latitude / .longitude    (fallback)

The written object matches render_property_aerial.py's shape so downstream consumers
(which read `cadastral_polygon.rings`, `.lot_area_sqm`, `.boundary_scope`) are unaffected,
plus provenance:
    cadastral_polygon.source        = "point_in_polygon_backfill"
    cadastral_polygon.backfilled_at = ISO8601

Rule 7 / 7b: self-registers a heartbeat and asserts an outcome — a run that HAD
candidates but resolved none raises (source unreachable), distinct from a run with
nothing to backfill (success). Idempotent: docs that already have rings are skipped.

Usage:
    python3 scripts/backfill_cadastral_polygons.py                       # dry-run, all 3 target suburbs
    python3 scripts/backfill_cadastral_polygons.py --suburb burleigh_waters
    python3 scripts/backfill_cadastral_polygons.py --apply --suburb burleigh_waters --limit 50
"""
from __future__ import annotations

import argparse
import json
import math
import os
import sys
import time
import urllib.parse
import urllib.request
from datetime import datetime, timezone

ORCH = "/home/fields/Fields_Orchestrator"
sys.path.insert(0, ORCH)
sys.path.insert(0, os.path.join(ORCH, "scripts"))

from shared.env import load_env                                  # noqa: E402
from shared.db import get_client                                 # noqa: E402
from src.mongo_client_factory import cosmos_retry                # noqa: E402
from job_status import job_run                                   # noqa: E402

QLD_CADASTRE = ("https://spatial-gis.information.qld.gov.au/arcgis/rest/services/"
                "PlanningCadastre/LandParcelPropertyFramework/MapServer/4/query")

TARGET_SUBURBS = ["burleigh_waters", "robina", "varsity_lakes"]

SOLD_MISSING = {
    "listing_status": "sold",
    "cadastral_polygon.rings": {"$exists": False},
}


# ── coordinates ──────────────────────────────────────────────────────────────

def coords_for(doc):
    """(lat, lng) from the document, or None. LATITUDE/LONGITUDE first (primary,
    highest fill), then geocoded_coordinates as a fallback."""
    lat, lng = doc.get("LATITUDE"), doc.get("LONGITUDE")
    if isinstance(lat, (int, float)) and isinstance(lng, (int, float)):
        return float(lat), float(lng)
    gc = doc.get("geocoded_coordinates") or {}
    lat, lng = gc.get("latitude"), gc.get("longitude")
    if isinstance(lat, (int, float)) and isinstance(lng, (int, float)):
        return float(lat), float(lng)
    return None


# ── source layer: point-in-polygon ──────────────────────────────────────────

def fetch_parcel_at(lat, lng):
    """Return {rings, lot_area_sqm, lotplan} for the parcel CONTAINING (lat,lng),
    or None if the point falls on no parcel. Raises on transport failure so the
    caller can tell 'no parcel here' from 'service unreachable' (Rule 7b)."""
    q = urllib.parse.urlencode({
        "geometry": f'{{"x":{lng},"y":{lat},"spatialReference":{{"wkid":4326}}}}',
        "geometryType": "esriGeometryPoint",
        "spatialRel": "esriSpatialRelIntersects",
        "outFields": "lotplan,lot_area",
        "returnGeometry": "true",
        "outSR": "4326",
        "f": "json",
    })
    with urllib.request.urlopen(f"{QLD_CADASTRE}?{q}", timeout=30) as r:
        data = json.loads(r.read())
    if data.get("error"):
        raise RuntimeError(f"cadastre error: {data['error']}")
    feats = data.get("features") or []
    if not feats:
        return None
    # A point intersects exactly one parcel; if the service returns more (edge/vertex
    # coincidence) take the one with the largest ring — the enclosing lot.
    best, best_area = None, -1.0
    for f in feats:
        rings = [[[float(p[0]), float(p[1])] for p in ring]
                 for ring in ((f.get("geometry") or {}).get("rings") or [])]
        if not rings:
            continue
        a = max(_ring_area_deg(r) for r in rings)
        if a > best_area:
            attrs = f.get("attributes") or {}
            best_area = a
            best = {
                "rings": rings,
                "lot_area_sqm": (float(attrs["lot_area"])
                                 if attrs.get("lot_area") not in (None, "") else None),
                "lotplan": attrs.get("lotplan"),
            }
    return best


# ── geometry helpers (verification) ──────────────────────────────────────────

def _ring_area_deg(ring):
    """Shoelace area in degrees^2 — only used to rank rings against each other."""
    if len(ring) < 3:
        return 0.0
    a = 0.0
    for i in range(len(ring) - 1):
        a += ring[i][0] * ring[i + 1][1] - ring[i + 1][0] * ring[i][1]
    return abs(a) * 0.5


def polygon_area_sqm(rings):
    """Approximate area of a [lng,lat] ring set in square metres, via an
    equirectangular projection about the ring centroid latitude. Good to ~0.1%
    over a single parcel — enough to sanity-check against the document's land size."""
    if not rings or not rings[0]:
        return 0.0
    outer = rings[0]
    lat0 = sum(p[1] for p in outer) / len(outer)
    m_per_deg_lat = 111_320.0
    m_per_deg_lng = 111_320.0 * math.cos(math.radians(lat0))
    total = 0.0
    for idx, ring in enumerate(rings):
        pts = [(p[0] * m_per_deg_lng, p[1] * m_per_deg_lat) for p in ring]
        a = 0.0
        for i in range(len(pts) - 1):
            a += pts[i][0] * pts[i + 1][1] - pts[i + 1][0] * pts[i][1]
        a = abs(a) * 0.5
        total += -a if idx else a          # inner rings (holes) subtract
    return max(total, 0.0)


# ── backfill ─────────────────────────────────────────────────────────────────

def candidates(col, limit=None):
    q = dict(SOLD_MISSING)
    cur = col.find(q, {"LATITUDE": 1, "LONGITUDE": 1, "geocoded_coordinates": 1,
                       "address": 1, "ADDRESS": 1, "lot_size_sqm": 1,
                       "LANDSIZE": 1, "land_area": 1})
    if limit:
        cur = cur.limit(limit)
    return list(cur)


def run_suburb(gc, suburb, apply, limit, verify, pause=0.25):
    col = gc[suburb]
    docs = candidates(col, limit)
    with_coords = [d for d in docs if coords_for(d)]
    stats = {"candidates": len(docs), "with_coords": len(with_coords),
             "resolved": 0, "written": 0, "no_parcel": 0, "no_coords": len(docs) - len(with_coords)}
    checks = []

    if not apply:
        return stats, checks

    for d in with_coords:
        lat, lng = coords_for(d)
        try:
            parcel = fetch_parcel_at(lat, lng)
        except Exception as exc:                                # transport / service error
            raise RuntimeError(f"{suburb}: cadastre lookup failed at ({lat},{lng}): {exc}") from exc
        if not parcel:
            stats["no_parcel"] += 1
            time.sleep(pause)
            continue
        stats["resolved"] += 1
        parcel["boundary_scope"] = "lot"
        parcel["source"] = "point_in_polygon_backfill"
        parcel["backfilled_at"] = datetime.now(timezone.utc).isoformat()
        cosmos_retry(col.update_one, {"_id": d["_id"]},
                     {"$set": {"cadastral_polygon": parcel}})
        stats["written"] += 1

        if verify and len(checks) < 5:
            known = d.get("lot_size_sqm") or d.get("LANDSIZE") or d.get("land_area")
            geom_area = polygon_area_sqm(parcel["rings"])
            checks.append({
                "id": str(d["_id"]),
                "address": d.get("address") or d.get("ADDRESS"),
                "lotplan": parcel.get("lotplan"),
                "cadastre_lot_area_sqm": parcel.get("lot_area_sqm"),
                "recomputed_area_sqm": round(geom_area, 1),
                "doc_land_size_sqm": known,
            })
        time.sleep(pause)

    return stats, checks


def main():
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--suburb", help="scope to one suburb collection")
    ap.add_argument("--limit", type=int, help="max candidate docs per suburb")
    ap.add_argument("--apply", action="store_true",
                    help="actually query + write (default is dry-run, counts only)")
    ap.add_argument("--dry-run", action="store_true", help="explicit dry-run (default)")
    ap.add_argument("--no-verify", action="store_true",
                    help="skip area-match spot checks on written docs")
    args = ap.parse_args()

    load_env()
    apply = args.apply and not args.dry_run
    suburbs = [args.suburb] if args.suburb else TARGET_SUBURBS

    with job_run("backfill_cadastral_polygons", cadence_hours=24 * 7,
                 title="Cadastral Polygon Backfill (point-in-polygon)") as beat:
        client = get_client()
        gc = client["Gold_Coast"]

        totals = {"candidates": 0, "with_coords": 0, "resolved": 0,
                  "written": 0, "no_parcel": 0, "no_coords": 0}
        all_checks = []
        mode = "APPLY" if apply else "DRY-RUN"
        print(f"=== backfill_cadastral_polygons [{mode}] "
              f"suburbs={suburbs} limit={args.limit} ===")

        for sub in suburbs:
            stats, checks = run_suburb(gc, sub, apply, args.limit, not args.no_verify)
            all_checks += checks
            for k in totals:
                totals[k] += stats[k]
            print(f"  {sub:16s} candidates={stats['candidates']:4d}  "
                  f"with_coords={stats['with_coords']:4d}  "
                  f"resolved={stats['resolved']:4d}  written={stats['written']:4d}  "
                  f"no_parcel={stats['no_parcel']:3d}  no_coords={stats['no_coords']:3d}")

        if all_checks:
            print("\n  area-match spot checks (recomputed vs cadastre vs doc land size):")
            for c in all_checks:
                print(f"    {c['lotplan']:>14s}  cadastre={c['cadastre_lot_area_sqm']}  "
                      f"recomputed={c['recomputed_area_sqm']}  doc={c['doc_land_size_sqm']}  "
                      f"| {c['address']}")

        beat.metrics = totals
        beat.detail = (f"{mode}: {totals['written']} written, "
                       f"{totals['resolved']} resolved of {totals['with_coords']} with coords "
                       f"({totals['candidates']} candidates)")

        # Rule 7b — assert an outcome, don't merely fail to throw.
        if apply:
            if totals["with_coords"] == 0:
                # Nothing to backfill — a genuinely drained queue, not a failure.
                print("\n  nothing to backfill (no candidates with coordinates).")
            elif totals["resolved"] == 0:
                # Input existed but the source resolved nothing → the source is broken,
                # not empty. Never record this as success.
                raise RuntimeError(
                    f"had {totals['with_coords']} candidates with coordinates but resolved "
                    f"0 parcels — cadastre lookup is broken, not the data empty.")
        print(f"\n{beat.detail}")


if __name__ == "__main__":
    main()
