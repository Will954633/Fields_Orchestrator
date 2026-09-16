#!/usr/bin/env python3
"""build_capitals_dom_json.py — bake public/data/gc_vs_capitals_dom.json, the data
behind the Gold-Coast-vs-capitals days-on-market comparison on /news/gold-coast.

Four cities × two property types, one DOM definition throughout:
  * Gold Coast  — pooled over the SAME 63-suburb composite panel as the page's other
    charts, read from system_monitor.domain_sold (the running GC cron).
  * Sydney / Melbourne / Brisbane — pooled over the price-band-matched panels
    selected by screen_panel.py (panel.json), read from system_monitor.domain_sold_capitals.

Every city is measured via Domain searchListings DOM (soldDate − dateListed,
agent-listed sales) so the comparison is internally consistent. Houses pool over
each city's HOUSE panel, units over its UNIT panel — genuinely price-matched per line.

Reuses precompute_market_charts monthly-rolling helpers so the series shape matches
the other DOM charts. No seasonal overlay here (4 lines already); the frontend gets
trailing-3m and trailing-12m monthly series per city per type, plus headline stats.

Usage: python3 scripts/capitals_dom/build_capitals_dom_json.py [--dry-run] [--out PATH]
"""
import argparse
import json
import sys
from datetime import datetime
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
sys.path.insert(0, str(HERE.parent))
sys.path.insert(0, str(HERE.parent.parent))
sys.path.insert(0, "/home/fields/Feilds_Website/08_Market_Narrative_Engine")

from shared.db import get_client  # noqa: E402
from shared.env import load_env  # noqa: E402
from job_status import job_run  # noqa: E402
from build_gc_leading_indicators import PARENT_JSON, compute_gc_composite  # noqa: E402
from precompute_market_charts import (  # noqa: E402
    _monthly_trailing_series, _rolling_median_window, _trailing_12m_dom,
    _add_months, _month_end,
)

DEFAULT_OUT = Path("/home/fields/Feilds_Website/01_Website/public/data/gc_vs_capitals_dom.json")

CITY_META = [
    {"key": "gold_coast", "label": "Gold Coast", "color": "#166534", "state": None},
    {"key": "greater_sydney", "label": "Greater Sydney", "color": "#b76749", "state": "NSW"},
    {"key": "greater_melbourne", "label": "Greater Melbourne", "color": "#8b5cf6", "state": "VIC"},
    {"key": "greater_brisbane", "label": "Greater Brisbane", "color": "#0284c7", "state": "QLD"},
]

MIN_N_3M = 10
MIN_N_12M = 25


def _records(rows):
    """domain_sold rows -> the {date, days_on_market} shape the helpers expect."""
    out = []
    for r in rows:
        dom = r.get("dom_days")
        sd = r.get("sold_date")
        if dom is None or not sd:
            continue
        try:
            out.append({"date": datetime.fromisoformat(str(sd)[:10]), "days_on_market": dom})
        except ValueError:
            continue
    return out


def _series(records, last_y, last_m):
    records = sorted(records, key=lambda x: x["date"])
    end = _month_end(last_y, last_m)
    return {
        "trailing_3m_series": _monthly_trailing_series(records, 3, last_y, last_m, MIN_N_3M),
        "trailing_12m_series": _monthly_trailing_series(records, 12, last_y, last_m, MIN_N_12M),
        "trailing_3m": _rolling_median_window(records, end, 3),
        "trailing_12m": _trailing_12m_dom(records, end),
        "sample_size": len(records),
    }


def _gc_panel_slugs(db):
    """GC composite 63-suburb panel, expressed as domain_sold suburb_key slugs."""
    parent = json.loads(PARENT_JSON.read_text())
    quarters = parent["quarters"]
    elig = set(compute_gc_composite(quarters, {q: i for i, q in enumerate(quarters)})["eligible"])
    # domain_sold suburb_key is a slug like "robina-4226"; its suburb part is elig-named.
    slugs = set()
    for key in db["domain_sold"].distinct("suburb_key"):
        stem = key.rsplit("-", 1)[0].replace("-", "_")
        if stem in elig:
            slugs.add(key)
    return slugs, len(elig)


def build(dry_run=False, out_path=DEFAULT_OUT):
    load_env()
    db = get_client()["system_monitor"]
    panel = json.loads((HERE / "panel.json").read_text())

    now = datetime.now()
    last_y, last_m = _add_months(now.year, now.month, -1)

    cities = {}
    for cm in CITY_META:
        if cm["key"] == "gold_coast":
            slugs, panel_size = _gc_panel_slugs(db)
            house_rows = list(db["domain_sold"].find(
                {"suburb_key": {"$in": list(slugs)}, "dwelling": "house", "dom_days": {"$ne": None}},
                {"sold_date": 1, "dom_days": 1}))
            unit_rows = list(db["domain_sold"].find(
                {"suburb_key": {"$in": list(slugs)}, "dwelling": "unit", "dom_days": {"$ne": None}},
                {"sold_date": 1, "dom_days": 1}))
            hp_size = up_size = panel_size
        else:
            st = cm["state"]
            h_slugs = [s["slug"] for s in panel["house_panel"][st]]
            u_slugs = [s["slug"] for s in panel["unit_panel"][st]]
            hp_size, up_size = len(h_slugs), len(u_slugs)
            house_rows = list(db["domain_sold_capitals"].find(
                {"suburb_key": {"$in": h_slugs}, "dwelling": "house", "dom_days": {"$ne": None}},
                {"sold_date": 1, "dom_days": 1}))
            unit_rows = list(db["domain_sold_capitals"].find(
                {"suburb_key": {"$in": u_slugs}, "dwelling": "unit", "dom_days": {"$ne": None}},
                {"sold_date": 1, "dom_days": 1}))

        house = _series(_records(house_rows), last_y, last_m)
        unit = _series(_records(unit_rows), last_y, last_m)
        house["panel_size"] = hp_size
        unit["panel_size"] = up_size
        cities[cm["key"]] = {"label": cm["label"], "color": cm["color"],
                             "house": house, "unit": unit}
        h12 = (house["trailing_12m"] or {}).get("median_days_on_market")
        u12 = (unit["trailing_12m"] or {}).get("median_days_on_market")
        print(f"  {cm['label']:<18} house: {hp_size} suburbs, n={house['sample_size']}, "
              f"12m={h12}d | unit: {up_size} suburbs, n={unit['sample_size']}, 12m={u12}d")

    out = {
        "generated": now.strftime("%Y-%m-%d"),
        "basis_note": (
            "Median days on market — the gap between a listing's advertised date and its "
            "sold date — for agent-listed sales, from Domain. Gold Coast is our full "
            "composite suburb panel; Sydney, Melbourne and Brisbane are panels of suburbs "
            "price-matched to the Gold Coast (house median ~$1.2-1.7M, unit median "
            "~$0.78-1.15M) so like is compared with like. Houses and units counted "
            "separately. Not comparable with figures published by other providers, whose "
            "definitions differ."),
        "bands": panel.get("generated_bands", {}),
        "cities": cities,
    }

    # Rule 7b — every city must have a usable line, or the comparison is hollow.
    for cm in CITY_META:
        for t in ("house", "unit"):
            n = len(cities[cm["key"]][t]["trailing_3m_series"])
            if n < 6:
                raise RuntimeError(
                    f"{cm['label']} {t} trailing_3m_series has {n} points "
                    f"(pool={cities[cm['key']][t]['sample_size']}) — panel too thin or "
                    f"scrape incomplete. Not writing gc_vs_capitals_dom.json.")

    if dry_run:
        print("\n(dry-run — not written)")
        return out
    out_path.write_text(json.dumps(out, default=str, separators=(",", ":")))
    print(f"\nWrote {out_path} ({out_path.stat().st_size} bytes)")
    return out


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", type=Path, default=DEFAULT_OUT)
    ap.add_argument("--dry-run", action="store_true")
    args = ap.parse_args()
    with job_run("build_capitals_dom_json", cadence_hours=31 * 24,
                 title="GC vs capitals days-on-market JSON") as beat:
        out = build(dry_run=args.dry_run, out_path=args.out)
        parts = []
        for cm in CITY_META:
            h = (out["cities"][cm["key"]]["house"]["trailing_12m"] or {}).get("median_days_on_market")
            parts.append(f"{cm['label'].split()[-1]} {h}d")
        beat.detail = "houses 12m: " + ", ".join(parts)


if __name__ == "__main__":
    main()
