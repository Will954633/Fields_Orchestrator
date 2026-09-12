#!/usr/bin/env python3
"""
Fetch ABS "Total Value of Dwellings" (TVD) Table 2 — median price and count of
established-house and attached-dwelling transfers by GCCSA — for the capitals
we compare the Gold Coast against.

Data source: ABS Data API (SDMX), dataflow ABS/RES_DWELL
  "Residential Dwellings: Unstratified Medians and Transfer Counts by Dwelling
   Type, GCCSA and Rest of State" — this IS TVD Table 2. No auth required.
  Licence: CC BY 4.0 (ABS).

Measures (CL_RES_DWELL_MEASURES):
  1 = Number of Established House Transfers          (UNIT_MULT 0, units)
  2 = Number of Attached Dwelling Transfers          (UNIT_MULT 0, units)
  3 = Median Price of Established House Transfers    (UNIT_MULT 3, $ thousands)
  4 = Median Price of Attached Dwelling Transfers    (UNIT_MULT 3, $ thousands)
The unit multiplier is read from each series' UNIT_MULT attribute (never
hardcoded) and prices are stored as whole dollars.

Writes ONE top-level block via $set on key `abs_tvd_gccsa` of the single doc
Gold_Coast.precomputed_macro_indicators {_id: "macro_indicators"} — no other
keys are touched.

Guards (CLAUDE.md Rule 7b — assert an outcome, don't just avoid throwing):
  - raise if any city yields < MIN_QUARTERS quarters;
  - raise if the newest quarter for any city is OLDER than what is already
    stored, or the series would shrink — a truncated fetch must never
    overwrite good data.

Heartbeat: job_run("fetch_abs_tvd", cadence_hours=24*95) — TVD is quarterly
with a ~12-week publication lag, so ~95 days keeps one release per cycle.

Usage:
  python3 scripts/fetch_abs_tvd.py            # fetch + write + heartbeat
  python3 scripts/fetch_abs_tvd.py --dry-run  # fetch + print, no write/heartbeat

NOTE: the most recent 1-2 quarters are preliminary (OBS_STATUS 'p') and are
revised upward by ABS as late transfer settlements arrive — counts especially.
We store the current vintage as-is; each quarterly re-run refreshes the full
history, which picks up revisions automatically.
"""

import argparse
import json
import os
import sys
from datetime import datetime, timezone

import requests

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))

from job_status import job_run  # noqa: E402

ABS_DATA_URL = "https://data.api.abs.gov.au/rest/data/RES_DWELL/{key}"
UA = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/120.0 Safari/537.36")

MEASURES = {  # CL_RES_DWELL_MEASURES code -> output field name
    "1": "established_house_transfers",
    "2": "attached_dwelling_transfers",
    "3": "median_established_house_price",
    "4": "median_attached_dwelling_price",
}
PRICE_MEASURES = {"3", "4"}

REGIONS = {  # CL_GCCSA code -> output city key
    "1GSYD": "greater_sydney",
    "2GMEL": "greater_melbourne",
    "3GBRI": "greater_brisbane",
}

START_PERIOD = "2001-Q1"   # ask for everything; ABS returns what exists
MIN_QUARTERS = 20          # per-city floor — fewer means a broken fetch


def fetch_res_dwell() -> dict:
    """One API call: all 4 measures x 3 GCCSAs, quarterly, full history."""
    key = "+".join(MEASURES) + "." + "+".join(REGIONS) + ".Q"
    url = ABS_DATA_URL.format(key=key)
    resp = requests.get(
        url,
        params={"startPeriod": START_PERIOD, "format": "jsondata"},
        headers={"User-Agent": UA},
        timeout=60,
    )
    resp.raise_for_status()
    return resp.json()


def parse_series(raw: dict) -> dict:
    """SDMX JSON v2 -> {city_key: [{quarter, <field>: value, ...}, ...]}.

    Series keys are positional indices into the structure's series dimensions;
    prices are scaled to whole dollars using each series' UNIT_MULT attribute.
    """
    struct = raw["data"]["structures"][0]
    sdims = struct["dimensions"]["series"]
    dim_codes = {d["id"]: [v["id"] for v in d["values"]] for d in sdims}
    dim_order = [d["id"] for d in sdims]
    periods = [p["id"] for p in struct["dimensions"]["observation"][0]["values"]]

    # UNIT_MULT is a series-level attribute; values index into its value list.
    attr_defs = struct.get("attributes", {}).get("series", [])
    unit_mult_pos, unit_mult_vals = None, []
    for pos, a in enumerate(attr_defs):
        if a["id"] == "UNIT_MULT":
            unit_mult_pos = pos
            unit_mult_vals = [int(v["id"]) for v in a["values"]]

    out = {city: {} for city in REGIONS.values()}  # city -> {quarter: {field: val}}
    for skey, sval in raw["data"]["dataSets"][0]["series"].items():
        idx = [int(i) for i in skey.split(":")]
        codes = {dim_order[i]: dim_codes[dim_order[i]][idx[i]] for i in range(len(idx))}
        measure, region = codes["MEASURE"], codes["REGION"]
        if measure not in MEASURES or region not in REGIONS:
            continue
        field = MEASURES[measure]
        city = REGIONS[region]

        scale = 1
        if measure in PRICE_MEASURES:
            if unit_mult_pos is None:
                raise RuntimeError("UNIT_MULT attribute missing — cannot verify "
                                   "price scale; refusing to guess")
            mult = unit_mult_vals[sval["attributes"][unit_mult_pos]]
            scale = 10 ** mult

        for oi, oval in sval["observations"].items():
            if oval[0] is None:
                continue
            quarter = periods[int(oi)]
            rec = out[city].setdefault(quarter, {})
            v = float(oval[0]) * scale
            rec[field] = int(round(v))

    # dicts -> sorted arrays ("YYYY-Qn" sorts correctly lexicographically)
    series = {}
    for city, by_q in out.items():
        series[city] = [{"quarter": q, **fields} for q, fields in sorted(by_q.items())]
    return series


def sanity_check(series: dict, existing_block: dict | None):
    """Rule 7b guards. Raises on truncated/backwards data."""
    for city in REGIONS.values():
        rows = series.get(city, [])
        n = len(rows)
        if n < MIN_QUARTERS:
            raise RuntimeError(
                f"{city}: only {n} quarters fetched (need >= {MIN_QUARTERS}) — "
                f"ABS RES_DWELL fetch is broken or truncated, not empty")
        # every row must have the two core house fields
        missing = [r["quarter"] for r in rows
                   if "median_established_house_price" not in r
                   or "established_house_transfers" not in r]
        if len(missing) > 2:  # tolerate a preliminary tail quarter or two
            raise RuntimeError(f"{city}: {len(missing)} quarters missing core house "
                               f"fields (e.g. {missing[:3]}) — column mapping broken")
        # magnitude check: a median transfer price below $100K or above $10M
        # means the unit scaling is wrong, not that the market moved
        latest_price = next(
            (r["median_established_house_price"] for r in reversed(rows)
             if "median_established_house_price" in r), None)
        if latest_price is None or not (100_000 <= latest_price <= 10_000_000):
            raise RuntimeError(f"{city}: latest median {latest_price!r} outside "
                               f"$100K-$10M — unit scaling is wrong; refusing to write")

    if existing_block:
        old = existing_block.get("series", {})
        for city, old_rows in old.items():
            if not old_rows:
                continue
            new_rows = series.get(city, [])
            old_last = max(r["quarter"] for r in old_rows)
            new_last = max(r["quarter"] for r in new_rows) if new_rows else ""
            if new_last < old_last:
                raise RuntimeError(
                    f"{city}: newest fetched quarter {new_last} is older than "
                    f"stored {old_last} — refusing to overwrite good data")
            if len(new_rows) < len(old_rows) - 2:  # small revisions tolerated
                raise RuntimeError(
                    f"{city}: fetched {len(new_rows)} quarters but "
                    f"{len(old_rows)} already stored — truncated fetch, refusing")


def main():
    ap = argparse.ArgumentParser(description="Fetch ABS TVD Table 2 GCCSA medians")
    ap.add_argument("--dry-run", action="store_true",
                    help="fetch + print, no DB write, no heartbeat")
    args = ap.parse_args()

    print("Fetching ABS RES_DWELL (TVD Table 2) ...")
    series = parse_series(fetch_res_dwell())

    if args.dry_run:
        for city, rows in series.items():
            print(f"\n{city}: {len(rows)} quarters "
                  f"({rows[0]['quarter']} -> {rows[-1]['quarter']})")
            print(json.dumps(rows[-3:], indent=2))
        return

    from shared.env import load_env  # noqa: E402  (Rule 7 checklist item 3)
    load_env()
    from shared.db import get_client  # noqa: E402
    from src.mongo_client_factory import cosmos_retry  # noqa: E402

    with job_run("fetch_abs_tvd", cadence_hours=24 * 95,
                 title="ABS TVD capitals medians (quarterly)") as beat:
        coll = get_client()["Gold_Coast"]["precomputed_macro_indicators"]
        existing = coll.find_one({"_id": "macro_indicators"},
                                 {"abs_tvd_gccsa": 1}) or {}
        sanity_check(series, existing.get("abs_tvd_gccsa"))

        block = {
            "updated_at": datetime.now(timezone.utc),
            "source": "ABS Total Value of Dwellings (Table 2), CC BY 4.0",
            "dataflow": "ABS/RES_DWELL via data.api.abs.gov.au",
            "series": series,
        }
        cosmos_retry(coll.update_one, {"_id": "macro_indicators"},
                     {"$set": {"abs_tvd_gccsa": block}}, upsert=True)

        latest = {c: rows[-1] for c, rows in series.items()}
        beat.metrics = {c: len(rows) for c, rows in series.items()}
        beat.detail = "; ".join(
            f"{c}: {len(series[c])}q to {latest[c]['quarter']}, "
            f"house median ${latest[c].get('median_established_house_price', 0):,}"
            for c in series)
        print("Written to Gold_Coast.precomputed_macro_indicators.abs_tvd_gccsa")
        print(beat.detail)


if __name__ == "__main__":
    main()
