#!/usr/bin/env python3
"""
Build public/data/gc_overview.json — the static data file behind the Gold Coast
overview panel on /news/gold-coast (hero stats + composite median chart + the
"GC vs capitals" indexed race).

Shares compute_gc_composite() with build_gc_leading_indicators.py so the median
chart and the explorer's momentum series come from the SAME composite (61-suburb
panel, interpolated gaps, fixed transaction weights, composition guard — see that
script's header for the method and the tail-artifact rationale).

Capitals data: `Gold_Coast.precomputed_macro_indicators` → `abs_tvd_gccsa`
(ABS Total Value of Dwellings Table 2 via SDMX, CC BY 4.0 — written by
scripts/fetch_abs_tvd.py, quarterly). Established-house medians for Greater
Sydney / Melbourne / Brisbane. The frontend indexes all series to 100 at the
first common quarter.

Refresh: baked snapshot, regenerate after the monthly precompute (wire into
run_monthly_market_precompute.sh alongside build_gc_leading_indicators.py when
the page ships — flagged in the scoping report).

Usage: python3 scripts/build_gc_overview_json.py [--out PATH] [--dry-run]
"""
import argparse
import json
import sys
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
sys.path.insert(0, str(Path(__file__).resolve().parent))
from shared.db import get_client  # noqa: E402
from shared.env import load_env  # noqa: E402
from build_gc_leading_indicators import PARENT_JSON, compute_gc_composite  # noqa: E402

DEFAULT_OUT = Path("/home/fields/Feilds_Website/01_Website/public/data/gc_overview.json")

# Collections in Gold_Coast that are NOT suburb collections (skip when counting
# live listings). Anything else lowercase_with_underscores is treated as a suburb.
NON_SUBURB_PREFIXES = (
    "precomputed_", "sqm_", "propradar_", "address_", "suburb_", "schema_",
    "system_", "narrative_", "coverage_",
)


def count_active_listings(db):
    total, suburbs_with = 0, 0
    for name in db.list_collection_names():
        if name.startswith(NON_SUBURB_PREFIXES) or not name.replace("_", "").isalpha():
            continue
        n = db[name].count_documents({"listing_status": "for_sale"})
        if n:
            total += n
            suburbs_with += 1
    return total, suburbs_with


def build(dry_run=False, out_path=DEFAULT_OUT):
    parent = json.loads(PARENT_JSON.read_text())
    quarters = parent["quarters"]
    qidx = {q: i for i, q in enumerate(quarters)}

    composite, momentum, eligible, _weights, mom_pts = compute_gc_composite(quarters, qidx)

    median_series = [
        {"q": quarters[i], "v": round(composite[i])}
        for i in range(len(quarters))
        if composite[i] is not None
    ]
    last_i = max(i for i in range(len(quarters)) if composite[i] is not None)

    db = get_client()["Gold_Coast"]
    active_listings, active_suburbs = count_active_listings(db)
    if active_listings == 0:
        raise RuntimeError("counted 0 active listings across all suburb collections — "
                           "scraper output is broken, not an empty market; not writing")

    macro = db["precomputed_macro_indicators"].find_one(
        {"_id": "macro_indicators"}, {"abs_tvd_gccsa": 1}
    ) or {}
    tvd = (macro.get("abs_tvd_gccsa") or {}).get("series") or {}
    capitals = {}
    for city_key, series in tvd.items():
        pts = [
            {"q": p["quarter"], "v": p["median_established_house_price"]}
            for p in series
            if p.get("median_established_house_price") and p["quarter"] in qidx
        ]
        if len(pts) >= 20:
            capitals[city_key] = pts
    if len(capitals) < 3:
        print(f"WARNING: only {len(capitals)} capital-city series available "
              f"({sorted(capitals)}) — page will hide the comparison chart")

    out = {
        "generated": datetime.now(timezone.utc).strftime("%Y-%m-%d"),
        "snapshot": {
            "median": round(composite[last_i]),
            "median_quarter": quarters[last_i],
            "yoy_pct": momentum[mom_pts[-1]],
            "suburbs": len(eligible),
            "active_listings": active_listings,
            "active_suburbs": active_suburbs,
        },
        "median_series": median_series,
        "capitals": capitals,
        "sources": {
            "gc": f"Fields transaction records — {len(eligible)}-suburb transaction-weighted "
                  "composite of rolling 12-month medians, houses",
            "capitals": "ABS Total Value of Dwellings (Table 2, GCCSA established-house "
                        "median transfer prices), CC BY 4.0",
        },
    }

    print(f"snapshot: median {out['snapshot']['median']:,} ({out['snapshot']['median_quarter']}) "
          f"· YoY {out['snapshot']['yoy_pct']}% · {active_listings} active across "
          f"{active_suburbs} suburbs · capitals: {sorted(capitals)} "
          f"({', '.join(str(len(v)) for v in capitals.values())} pts)")
    if dry_run:
        print("(dry run — nothing written)")
        return
    out_path.write_text(json.dumps(out, separators=(",", ":")) + "\n")
    print(f"wrote {out_path} ({out_path.stat().st_size:,} bytes)")


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", type=Path, default=DEFAULT_OUT)
    ap.add_argument("--dry-run", action="store_true")
    args = ap.parse_args()
    load_env()
    build(dry_run=args.dry_run, out_path=args.out)
