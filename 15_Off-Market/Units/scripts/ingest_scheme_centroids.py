#!/usr/bin/env python3
"""ingest_scheme_centroids.py — a real location for every strata scheme.

WHY THIS EXISTS
---------------
The statutory comparable set (Property Occupations Act 2014 (Qld) Sch 2) requires sales
"within a 5km radius" of the subject. We could not compute that: coordinates are on
**0.7% of indexed attached dwellings** (48 of 5,120 in Robina carry
`georeference_data.coordinates.latitude`, 78 carry `geocoded_coordinates.latitude`).
Geocoding 4,967 unit addresses would be slow, cost money, and be WRONG in a specific way —
a geocoder resolves `12/45 Smith St` to the street, so every unit in a tower lands on a
slightly different point that implies precision we do not have.

The scheme centroid is not a workaround for the missing per-unit geocode. It is the
**correct** geometry for attached stock: every home in one building genuinely shares one
location, and the cadastre knows exactly where the parcel is. A per-unit geocode would be
noisier AND less true.

⚠ `returnCentroid=true` IS SILENTLY IGNORED BY THIS SERVICE.
It is a documented ArcGIS parameter, the server accepts the request, returns HTTP 200 and
a well-formed feature set — with `"centroid": null` on every feature. Nothing errors. So
we request full geometry and compute the centroid here. A caller who trusted the parameter
would get None for every scheme and conclude the cadastre has no geometry, which is false.

Writes `centroid_lat` / `centroid_lon` / `centroid_basis` onto `Gold_Coast.complexes`.
"""
from __future__ import annotations

import argparse
import datetime as dt
import json
import sys
import time
import urllib.parse
import urllib.request
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent.parent.parent
for p in (str(ROOT), str(HERE)):
    if p not in sys.path:
        sys.path.insert(0, p)

try:
    from shared.env import load_env
    load_env()
except Exception:
    pass

from pymongo import UpdateOne                      # noqa: E402
from shared.db import get_client                   # noqa: E402
from scripts.job_status import job_run             # noqa: E402

SERVICE = ("https://spatial-gis.information.qld.gov.au/arcgis/rest/services/"
           "PlanningCadastre/LandParcelPropertyFramework/MapServer/4/query")
LICENCE = "CC-BY 4.0 — © State of Queensland (Department of Resources)"
PAGE = 400          # smaller than the attribute ingest: geometry payloads are ~40x larger
SUBURBS = {"robina": "Robina", "varsity_lakes": "Varsity Lakes",
           "burleigh_waters": "Burleigh Waters"}

# Gold Coast sanity box. A centroid outside this is a projection error, not a location.
LAT_MIN, LAT_MAX = -28.30, -27.70
LON_MIN, LON_MAX = 153.20, 153.60


def _get(params, retries=4):
    url = SERVICE + "?" + urllib.parse.urlencode(params)
    last = None
    for i in range(retries):
        try:
            with urllib.request.urlopen(url, timeout=180) as r:
                return json.load(r)
        except Exception as e:            # noqa: BLE001
            last = e
            time.sleep(2 * (i + 1))
    raise RuntimeError(f"cadastre unreachable after {retries} tries: {last}")


def ring_centroid(ring):
    """Area-weighted centroid of one ring (the shoelace formula).

    Not the mean of the vertices: cadastral parcels have unevenly spaced points along
    curved boundaries, so a vertex mean drifts toward whichever edge was surveyed in most
    detail. For a long battle-axe parcel that is tens of metres off.
    """
    if len(ring) < 3:
        return None
    a = cx = cy = 0.0
    for i in range(len(ring) - 1):
        x0, y0 = ring[i][0], ring[i][1]
        x1, y1 = ring[i + 1][0], ring[i + 1][1]
        cross = x0 * y1 - x1 * y0
        a += cross
        cx += (x0 + x1) * cross
        cy += (y0 + y1) * cross
    if abs(a) < 1e-12:                      # degenerate/zero-area ring
        xs = [p[0] for p in ring]
        ys = [p[1] for p in ring]
        return sum(xs) / len(xs), sum(ys) / len(ys)
    a *= 0.5
    return cx / (6 * a), cy / (6 * a)


def ring_area(ring):
    if len(ring) < 3:
        return 0.0
    a = 0.0
    for i in range(len(ring) - 1):
        a += ring[i][0] * ring[i + 1][1] - ring[i + 1][0] * ring[i][1]
    return abs(a) * 0.5


def fetch_geometry(locality: str):
    """Every strata parcel in a locality, with geometry, paged to completion."""
    where = (f"UPPER(locality)='{locality.upper()}' AND ("
             "plan LIKE 'BUP%' OR plan LIKE 'GTP%' OR plan LIKE 'SP%')")
    out, offset = [], 0
    while True:
        d = _get({"where": where, "outFields": "lotplan,plan",
                  "returnGeometry": "true", "outSR": "4326",
                  "resultOffset": offset, "resultRecordCount": PAGE, "f": "json"})
        if "error" in d:
            raise RuntimeError(f"ArcGIS error for {locality}: {d['error']}")
        feats = d.get("features") or []
        out += feats
        if not d.get("exceededTransferLimit") or not feats:
            break
        offset += len(feats)
    return out


def centroids_for(locality: str):
    """plan -> (lat, lon), area-weighted across every parcel on that plan.

    A scheme can span several parcels (222 of ours do). Weighting by area rather than
    averaging parcel centroids keeps a large residential block from being dragged toward
    a small adjoining utility lot.
    """
    acc = {}
    for f in fetch_geometry(locality):
        plan = (f.get("attributes") or {}).get("plan")
        rings = (f.get("geometry") or {}).get("rings") or []
        if not plan or not rings:
            continue
        # The outer ring is the largest; inner rings are holes and must not vote.
        outer = max(rings, key=ring_area)
        c = ring_centroid(outer)
        if not c:
            continue
        lon, lat = c[0], c[1]
        if not (LAT_MIN <= lat <= LAT_MAX and LON_MIN <= lon <= LON_MAX):
            continue
        w = ring_area(outer)
        s = acc.setdefault(plan, [0.0, 0.0, 0.0, 0])
        s[0] += lat * w
        s[1] += lon * w
        s[2] += w
        s[3] += 1
    out = {}
    for plan, (slat, slon, w, n) in acc.items():
        if w <= 0:
            continue
        out[plan] = (round(slat / w, 6), round(slon / w, 6), n)
    return out


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--suburb")
    ap.add_argument("--dry-run", action="store_true")
    args = ap.parse_args()
    targets = ({args.suburb: SUBURBS[args.suburb]} if args.suburb else SUBURBS)

    with job_run("units_scheme_centroids", cadence_hours=720,
                 title="Units — scheme centroids from the QLD cadastre") as beat:
        gc = get_client()["Gold_Coast"]
        col = gc["complexes"]
        total = located = 0

        for key, locality in targets.items():
            cents = centroids_for(locality)
            ops = []
            for d in col.find({"suburb_key": key}, {"plan": 1}):
                total += 1
                c = cents.get(d.get("plan"))
                if not c:
                    continue
                located += 1
                ops.append(UpdateOne({"_id": d["_id"]}, {"$set": {
                    "centroid_lat": c[0], "centroid_lon": c[1],
                    "centroid_parcels": c[2],
                    "centroid_basis": "area-weighted cadastral parcel centroid",
                    "centroid_source": "qld_cadastre_layer4",
                    "centroid_licence": LICENCE,
                    "centroid_at": dt.datetime.utcnow()}}))
            if ops and not args.dry_run:
                col.bulk_write(ops, ordered=False)
            print(f"  {key:17s} {len(cents):5,} plans located in the cadastre")

        pct = located / max(1, total) * 100
        beat.metrics = {"schemes": total, "located": located, "located_pct": round(pct, 1)}
        beat.detail = f"{located:,} of {total:,} schemes located ({pct:.1f}%)"
        print(f"\n  SCHEMES WITH A CENTROID: {located:,} of {total:,} ({pct:.1f}%)")

        # Rule 7b — the zero-output paths. The cadastre is a published dataset and these
        # plans came from it, so a run that locates nothing means the service changed its
        # geometry contract (exactly what returnCentroid already does silently), never
        # that the schemes moved.
        if total == 0:
            raise RuntimeError("0 schemes read from complexes — ingest_complexes has not run")
        if located == 0:
            raise RuntimeError(
                "0 of the schemes could be located, yet every one of them was READ from "
                "this same service — the geometry response shape has changed")
        if pct < 60:
            raise RuntimeError(
                f"only {pct:.1f}% located; the attribute ingest reaches ~90% of these "
                "plans, so a large gap means paging stopped early or rings are empty")
    return 0


if __name__ == "__main__":
    sys.exit(main())
