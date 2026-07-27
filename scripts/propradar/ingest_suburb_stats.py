"""
ingest_suburb_stats.py — pull PropRadar's authoritative /suburbs snapshot per core
suburb into Gold_Coast.propradar_suburb_stats.

These precomputed stats (median, growth, sales_12mo, inventory_months, DOM, heat) are
the source of truth for headline market metrics — validated 2026-07-27 against
realestate.com.au (identical medians on Robina & Varsity). This is the reliable feed;
the /sold ROW feed (propradar_sold) is truncated and used only for coverage-gap
discovery + individual sold records, NOT for counting volume.

One call per suburb. Idempotent upsert keyed by suburb_key.

Usage:
    python3 scripts/propradar/ingest_suburb_stats.py --all --apply
    python3 scripts/propradar/ingest_suburb_stats.py --suburb robina --dry-run
"""
from __future__ import annotations

import argparse
import datetime
import os
import sys
import urllib.parse

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(os.path.dirname(HERE))
sys.path.insert(0, ROOT)
sys.path.insert(0, HERE)

from shared.db import get_gold_coast_db, cosmos_retry  # noqa: E402
import propradar_client as pr  # noqa: E402

SUBURBS = {
    "robina": ("Robina", 4226),
    "burleigh_waters": ("Burleigh Waters", 4220),
    "varsity_lakes": ("Varsity Lakes", 4227),
}
COLLECTION = "propradar_suburb_stats"


def ingest(suburb_key: str, apply: bool):
    name, pc = SUBURBS[suburb_key]
    data, hdr = pr.call("/suburbs/QLD/" + urllib.parse.quote(name))
    md = data.get("market_dynamics") or {}
    meds = data.get("medians") or {}
    gr = data.get("growth") or {}
    now = datetime.datetime.now(datetime.timezone.utc).isoformat()
    doc = {
        "_id": suburb_key,
        "suburb": name,
        "postcode": pc,
        "medians": meds,
        "growth": gr,
        "yields": data.get("yields"),
        "market_dynamics": md,
        "data_quality_flags": data.get("data_quality_flags"),
        "as_of": data.get("as_of"),
        "source": "propradar",
        "fetched_at": now,
    }
    gh = (gr.get("house") or {})
    print(f"{name}: median ${meds.get('house_price')} | 1y {gh.get('1y_pct')}% | "
          f"sales12 {md.get('house_sales_12mo')} | inv {md.get('house_inventory_months')}mo | "
          f"dom {md.get('house_days_on_market')} | heat {md.get('house_heat_score')} "
          f"| as_of {data.get('as_of')} | ratelimit_remaining={hdr.get('x-ratelimit-remaining')}")
    if apply:
        db = get_gold_coast_db()
        cosmos_retry(lambda: db[COLLECTION].replace_one({"_id": suburb_key}, doc, upsert=True),
                     f"{COLLECTION}.upsert:{suburb_key}")
        print(f"  upserted → Gold_Coast.{COLLECTION}")
    else:
        print("  (dry-run — nothing written)")
    return doc


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--suburb", choices=list(SUBURBS))
    ap.add_argument("--all", action="store_true")
    ap.add_argument("--apply", action="store_true")
    ap.add_argument("--dry-run", action="store_true")
    args = ap.parse_args()
    targets = list(SUBURBS) if args.all else ([args.suburb] if args.suburb else [])
    if not targets:
        ap.error("pass --suburb <name> or --all")
    for s in targets:
        ingest(s, args.apply and not args.dry_run)


if __name__ == "__main__":
    main()
