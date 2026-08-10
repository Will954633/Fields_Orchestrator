#!/usr/bin/env python3
"""ingest_storeys.py — storeys band per complex from QLD LiDAR. (Plan E2)

A unit owner knows whether they live in a 3-storey walk-up or a 20-storey tower, and a
page that cannot say which does not sound like it knows the building. There is no
storeys field in any source we pay for (verified: not in Domain's payload, not in
PropRadar, not in onthehouse), and the Gold Coast council layer that appears to have
`NO_OF_STOREYS` covers council-owned assets only — libraries and amenities blocks, zero
residential.

QLD publishes LiDAR-derived building outlines free under CC-BY 4.0:
    .../Structure/BuildingsAndSettlements/MapServer/11  "Building outlines [generated]"
    height = bsm_max (building surface model) - dtm_centre (terrain at centre)

⚠ PUBLISH A BAND, NEVER A NUMBER. Calibrated against OSM buildings carrying
`building:levels`, 4.3 m/storey gives 59% exact and 90% within ±1 storey — good enough
to say "4-6 storeys", not good enough to say "5". Worse, it CANNOT separate 1 from 2
(medians 8.5 m vs 9.0 m; tree canopy inflates low-rise), so everything under ~3 storeys
is reported as "low-rise" rather than guessed.

⚠ CAPTURED APR-JUN 2022. Anything built since is missing, and a complex that returns no
building is not necessarily unbuilt. Absence is recorded as unknown, never as zero.
"""
from __future__ import annotations

import argparse
import json
import statistics as st
import sys
import time
import urllib.parse
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))
try:
    from shared.env import load_env
    load_env()
except Exception:
    pass

from shared.db import get_client                    # noqa: E402
from scripts.job_status import job_run              # noqa: E402

LAYER = ("https://spatial-gis.information.qld.gov.au/arcgis/rest/services/"
         "Structure/BuildingsAndSettlements/MapServer/11/query")
UA = {"User-Agent": "FieldsEstate/1.0 (property research; will@fieldsestate.com.au)"}
M_PER_STOREY = 4.3
MIN_FOOTPRINT = 90          # m² — smaller outlines are garages, sheds, bin stores
SEARCH_M = 70


def _get(params, retries=3):
    url = LAYER + "?" + urllib.parse.urlencode(params)
    for a in range(retries):
        try:
            with urllib.request.urlopen(urllib.request.Request(url, headers=UA), timeout=60) as r:
                return json.load(r)
        except Exception:
            if a == retries - 1:
                raise
            time.sleep(1.5 * (a + 1))


def band(storeys):
    """Bands, not point values — see the module docstring."""
    if storeys is None:
        return None
    if storeys <= 2:
        return "low-rise (1–2 storeys)"
    if storeys <= 3:
        return "3 storeys"
    if storeys <= 6:
        return f"{max(3, storeys - 1)}–{storeys + 1} storeys"
    if storeys <= 12:
        return f"{storeys - 2}–{storeys + 2} storeys"
    return f"about {round(storeys / 5) * 5} storeys"


def storeys_at(lat, lon):
    r = _get({"geometry": f"{lon},{lat}", "geometryType": "esriGeometryPoint", "inSR": 4326,
              "distance": SEARCH_M, "units": "esriSRUnit_Meter",
              "spatialRel": "esriSpatialRelIntersects",
              "outFields": "bsm_max,dtm_centre,dimension_m2",
              "returnGeometry": "false", "f": "json"})
    if not r or "error" in r:
        return None, 0, None
    rows = []
    for f in (r.get("features") or []):
        a = f["attributes"]
        h = (a.get("bsm_max") or 0) - (a.get("dtm_centre") or 0)
        area = a.get("dimension_m2") or 0
        if h > 2 and area >= MIN_FOOTPRINT:
            rows.append((h, area))
    if not rows:
        return None, 0, None
    # The TALLEST substantial outline, not the mean: a tower beside its own carpark
    # would otherwise average down to something neither building is.
    h = max(r_[0] for r_ in rows)
    return max(1, round(h / M_PER_STOREY)), len(rows), round(h, 1)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--limit", type=int)
    ap.add_argument("--min-dwellings", type=int, default=2)
    args = ap.parse_args()

    with job_run("units_storeys_ingest", cadence_hours=720,
                 title="Units — LiDAR storeys band per complex") as beat:
        gc = get_client()["Gold_Coast"]
        targets = list(gc["complexes"].find(
            {"dwellings_in_data": {"$gte": args.min_dwellings}},
            {"suburb_key": 1, "plan": 1, "complex_name": 1, "dwellings_in_data": 1}))
        if args.limit:
            targets = targets[:args.limit]
        print(f"  {len(targets)} complexes with >= {args.min_dwellings} dwellings")

        done = found = 0
        for c in targets:
            pts = [(d.get("LATITUDE"), d.get("LONGITUDE")) for d in
                   gc[c["suburb_key"]].find(
                       {"complex_plan": c["plan"], "LATITUDE": {"$exists": True, "$ne": None}},
                       {"LATITUDE": 1, "LONGITUDE": 1}).limit(25)]
            pts = [(a, b) for a, b in pts if a and b]
            if not pts:
                continue
            lat = st.median([p[0] for p in pts])
            lon = st.median([p[1] for p in pts])
            try:
                s, n, h = storeys_at(lat, lon)
            except Exception as e:
                print(f"    ! {c['plan']}: {type(e).__name__}", file=sys.stderr)
                continue
            done += 1
            if s:
                found += 1
                gc["complexes"].update_one({"_id": c["_id"]}, {"$set": {
                    "storeys_estimate": s, "storeys_band": band(s),
                    "building_height_m": h, "storeys_buildings_seen": n,
                    "storeys_source": ("QLD LiDAR building outlines (CC-BY 4.0), "
                                       "captured Apr–Jun 2022; 4.3 m/storey, "
                                       "90% within ±1 storey"),
                }})
            if done % 100 == 0:
                print(f"    {done}/{len(targets)} probed, {found} with a building")
            time.sleep(0.15)

        beat.metrics = {"probed": done, "with_building": found,
                        "coverage_pct": round(found / done * 100, 1) if done else 0}
        beat.detail = f"{found} of {done} complexes got a storeys band"
        # Rule 7b — probing thousands of real addresses against a statewide building
        # layer and matching none means the service or the geometry broke.
        if done and found == 0:
            raise RuntimeError(f"probed {done} complexes and matched 0 buildings — "
                               "the LiDAR query or the coordinates are broken")
        if done == 0:
            raise RuntimeError("no complexes had usable coordinates to probe")
    return 0


if __name__ == "__main__":
    sys.exit(main())
