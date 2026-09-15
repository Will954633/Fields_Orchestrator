#!/usr/bin/env python3
"""
Build public/data/gc_dom_by_type.json — the static data behind the Gold-Coast-wide
"days on market, houses vs units" chart on /news/gold-coast.

WHY THIS SCRIPT EXISTS
----------------------
The per-suburb DOM charts (precompute_market_charts.py) and the existing
`gold_coast_days_on_market` aggregate are HOUSES ONLY — the ingestion pipeline
hard-filters `property_type == "House"`. The unit sold-history sits in the SAME
`scraped_data.property_timeline` records (measured 2026-09-16: ~165k unit sales
with days_on_market, ~8k/yr 2016-2025 — comparable volume to houses), it was
simply never surfaced. This script pools the raw DOM records across the same
63-suburb composite panel that feeds the median-price chart on that page, splits
them House vs Unit, and computes the same trailing/seasonal series the suburb
charts use — so the new chart is an exact, methodology-matched sibling, not a
weighted-median-of-medians approximation.

METHOD (mirrors calculate_days_on_market_data in precompute_market_charts.py)
  * Panel: the eligible suburb set from compute_gc_composite() (kept in sync with
    the price chart above it — do not hardcode).
  * Sources per suburb: (A) scraped_data.property_timeline is_sold events over the
    last 10 years; (C) listing_status='sold' over the last 12 months. Property type
    resolved in Python (classified_property_type -> scraped features -> property_type)
    and bucketed; non-residential / land / unknown dropped.
  * DOM validity: 3 < days_on_market < 365 (the pipeline's own outlier gate, and the
    "excludes 3 days or fewer" pre-sold exclusion the basis_note documents).
  * Pool ALL panel suburbs' records per type, dedupe the same sale seen by >1 source
    (_dedupe_dom_records — keys on address/_id, so it collapses correctly across the
    pooled set), then compute:
      - trailing_3m_series / trailing_12m_series : monthly rolling-median points
      - seasonal_trend                           : 12 per-calendar-month typicals
                                                   (10yr, excl. 2020-2021 COVID)
      - trailing_3m / trailing_12m               : the headline tile, ending last
                                                   completed month.

The frontend range pills (12 months / 3 years) simply slice the monthly series;
the window pills (Rolling 3-mo / 12-mo) pick which series; the pill (Houses / Units)
picks which `series.*` block.

Ongoing refresh: wire into run_monthly_market_precompute.sh (after the DOM backfill
+ dom charts). Self-reports via job_run so a silent failure shows STALE/ERROR on the
Systems Health sheet.

Usage:
  python3 scripts/build_gc_dom_by_type.py [--out PATH] [--dry-run] [--suburbs a,b,c]
"""
import argparse
import json
import sys
import time
from collections import defaultdict
from datetime import datetime, timedelta
from pathlib import Path
from statistics import median, mean

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
sys.path.insert(0, str(Path(__file__).resolve().parent))
sys.path.insert(0, "/home/fields/Feilds_Website/08_Market_Narrative_Engine")

from shared.db import get_client  # noqa: E402
from shared.env import load_env  # noqa: E402
from build_gc_leading_indicators import PARENT_JSON, compute_gc_composite  # noqa: E402
from job_status import job_run  # noqa: E402

# Reuse the exact, battle-tested helpers from the suburb DOM builder so the two
# charts measure the same thing the same way.
from precompute_market_charts import (  # noqa: E402
    _dedupe_dom_records,
    _monthly_trailing_series,
    _rolling_median_window,
    _trailing_12m_dom,
    _resolve_dom_address,
    _add_months,
    _month_end,
)

DEFAULT_OUT = Path("/home/fields/Feilds_Website/01_Website/public/data/gc_dom_by_type.json")

# Property-type buckets. HOUSE matches the existing houses-only series exactly so
# the GC house line is continuous with every per-suburb chart. UNIT is the
# attached/strata residential family; land, commercial and unknowns are dropped
# (NOT folded into units) so "Units" means what a reader thinks it means.
HOUSE_TYPES = {"House"}
UNIT_TYPES = {
    "Unit", "Unit/Apartment", "Apartment", "Townhouse", "Villa",
    "Duplex", "Duplex/Semi-Detached", "Semi-Detached", "Studio", "Terrace", "Flat",
}

MONTH_NAMES = ['Jan', 'Feb', 'Mar', 'Apr', 'May', 'Jun',
               'Jul', 'Aug', 'Sep', 'Oct', 'Nov', 'Dec']

# GC-wide volume is ~15-40x a single suburb, so a monthly window carries hundreds
# of sales. These floors just trim the sparse leading edge of the earliest months.
MIN_N_3M = 12
MIN_N_12M = 30

BASIS_NOTE = (
    "Median days advertised on Domain listings, final campaign, pooled across the "
    "Gold Coast composite suburb panel. Excludes sales advertised 3 days or fewer "
    "(pre-sold / off-market stock listed only to record a result). Houses and units "
    "are counted separately. Not comparable with figures published by other "
    "providers, whose definitions differ."
)


def _resolve_ptype(doc):
    """Same precedence as _get_listing_status_sold: validated vision label first,
    raw scraped feature next, top-level property_type last."""
    return (doc.get("classified_property_type")
            or (doc.get("scraped_data", {}) or {}).get("features", {}).get("property_type")
            or doc.get("property_type", "Unknown"))


def _bucket(ptype):
    if ptype in HOUSE_TYPES:
        return "house"
    if ptype in UNIT_TYPES:
        return "unit"
    return None


def _gather_timeline(coll, start_str, end_str):
    """All is_sold timeline events with a valid DOM in [start,end], carrying the
    type-resolution fields and dedupe-identity fields. Bucketing is done by the
    caller in Python (no server-side property_type filter — we want both types
    from one scan)."""
    pipeline = [
        {'$unwind': '$scraped_data.property_timeline'},
        {'$match': {
            'scraped_data.property_timeline.is_sold': True,
            'scraped_data.property_timeline.date': {'$gte': start_str, '$lte': end_str},
        }},
        {'$addFields': {
            'timeline_date': {'$dateFromString': {'dateString': '$scraped_data.property_timeline.date'}},
            'dom': '$scraped_data.property_timeline.days_on_market',
        }},
        {'$match': {'dom': {'$ne': None, '$gt': 3, '$lt': 365}}},
        {'$project': {
            'date': '$timeline_date',
            'days_on_market': '$dom',
            'address': 1,
            'scraped_address': '$scraped_data.address',
            'complete_address': '$complete_address',
            'classified_property_type': 1,
            'features_property_type': '$scraped_data.features.property_type',
            'property_type': 1,
        }},
    ]
    out = []
    for r in coll.aggregate(pipeline):
        ptype = (r.get("classified_property_type")
                 or r.get("features_property_type")
                 or r.get("property_type", "Unknown"))
        b = _bucket(ptype)
        if b is None:
            continue
        r['address'] = _resolve_dom_address(r)
        r['source'] = 'timeline'
        out.append((b, r))
    return out


def _gather_listing_status(coll, start_str, end_str):
    """listing_status='sold' records (recent-window freshness, catches sales not yet
    in the published timeline). Bucketed by resolved type."""
    cursor = coll.find(
        {"listing_status": "sold", "sold_date": {"$gte": start_str, "$lte": end_str}},
        {"sold_date": 1, "days_on_market": 1, "classified_property_type": 1,
         "scraped_data.features.property_type": 1, "property_type": 1, "_id": 1, "address": 1},
    )
    out = []
    for doc in cursor:
        dom = doc.get("days_on_market")
        if dom is None or not (3 < dom < 365):
            continue
        sd = doc.get("sold_date")
        if not sd:
            continue
        try:
            dt = sd if isinstance(sd, datetime) else datetime.strptime(str(sd)[:10], "%Y-%m-%d")
        except (ValueError, TypeError):
            continue
        b = _bucket(_resolve_ptype(doc))
        if b is None:
            continue
        out.append((b, {
            "_id": doc.get("_id"),
            "address": doc.get("address"),
            "date": dt,
            "days_on_market": dom,
            "source": "listing_status",
        }))
    return out


def _series_for_type(records, last_y, last_m):
    """Given a deduped record pool for one type, build the frontend payload."""
    records = sorted(records, key=lambda x: x['date'])
    last_completed_end = _month_end(last_y, last_m)

    trailing_3m_series = _monthly_trailing_series(records, 3, last_y, last_m, min_n=MIN_N_3M)
    trailing_12m_series = _monthly_trailing_series(records, 12, last_y, last_m, min_n=MIN_N_12M)
    trailing_12m = _trailing_12m_dom(records, last_completed_end)
    trailing_3m = _rolling_median_window(records, last_completed_end, 3)

    # Seasonal: per-calendar-month typical over 10 years, excluding 2020-2021.
    seasonal_data = defaultdict(list)
    for r in records:
        if r['date'].year not in (2020, 2021):
            seasonal_data[r['date'].month].append(r['days_on_market'])
    seasonal_trend = []
    for m in range(1, 13):
        vals = seasonal_data.get(m)
        if vals:
            seasonal_trend.append({
                'month': m,
                'month_name': MONTH_NAMES[m - 1],
                'avg_days': round(mean(vals), 1),
                'median_days': round(median(vals), 1),
            })

    return {
        'trailing_3m_series': trailing_3m_series,
        'trailing_12m_series': trailing_12m_series,
        'trailing_3m': trailing_3m,
        'trailing_12m': trailing_12m,
        'seasonal_trend': seasonal_trend,
        'sample_size': len(records),
    }


def build(dry_run=False, out_path=DEFAULT_OUT, suburbs=None):
    load_env()

    parent = json.loads(PARENT_JSON.read_text())
    quarters = parent["quarters"]
    qidx = {q: i for i, q in enumerate(quarters)}
    panel = sorted(compute_gc_composite(quarters, qidx)["eligible"])
    if suburbs:
        panel = [s for s in panel if s in set(suburbs)]

    db = get_client()["Gold_Coast"]
    now = datetime.now()
    ten_years = (now - timedelta(days=365 * 10)).strftime('%Y-%m-%d')
    now_str = now.strftime('%Y-%m-%d')
    cutoff_12m = (now - timedelta(days=365)).strftime('%Y-%m-%d')

    pools = {"house": [], "unit": []}
    existing_addr = {"house": set(), "unit": set()}  # de-dup listing_status vs timeline cheaply
    for i, s in enumerate(panel):
        coll = db[s]
        try:
            tl = _gather_timeline(coll, ten_years, now_str)
            ls = _gather_listing_status(coll, cutoff_12m, now_str)
        except Exception as e:
            print(f"  {s}: ERROR {e}")
            continue
        for b, r in tl:
            pools[b].append(r)
        for b, r in ls:
            pools[b].append(r)
        print(f"  [{i+1}/{len(panel)}] {s}: timeline {len(tl)}, listing_status {len(ls)}")
        # Rate-limit courtesy for Cosmos RU across many heavy unwind aggregations.
        if i < len(panel) - 1:
            time.sleep(1.5)

    # Last completed month (a partial current month never drags the headline).
    last_y, last_m = _add_months(now.year, now.month, -1)

    series = {}
    dedupe_stats = {}
    for b in ("house", "unit"):
        deduped, stats = _dedupe_dom_records(pools[b])
        dedupe_stats[b] = stats
        series[b] = _series_for_type(deduped, last_y, last_m)
        print(f"  {b}: {stats['input_records']} raw -> {stats['output_records']} sales "
              f"({stats['collapsed_duplicates']} collapsed); "
              f"3m pts={len(series[b]['trailing_3m_series'])}, "
              f"12m pts={len(series[b]['trailing_12m_series'])}, "
              f"headline12m={ (series[b]['trailing_12m'] or {}).get('median_days_on_market') }")

    out = {
        "generated": datetime.now().strftime("%Y-%m-%d"),
        "panel_size": len(panel),
        "basis_note": BASIS_NOTE,
        "series": series,
        "dedupe_stats": dedupe_stats,
    }

    # Rule 7b — assert an OUTCOME, not merely that nothing threw. A GC-wide pool
    # that produced no usable house OR unit trend line means the source is broken,
    # not that the market went quiet; refuse to write a hollow file over a good one.
    for b in ("house", "unit"):
        if len(series[b]['trailing_3m_series']) < 6:
            raise RuntimeError(
                f"{b} trailing_3m_series has only {len(series[b]['trailing_3m_series'])} "
                f"points (pool={series[b]['sample_size']}) — upstream DOM data is "
                f"missing, not empty. Not writing gc_dom_by_type.json.")

    if dry_run:
        print(json.dumps({k: v for k, v in out.items() if k != "series"}, indent=2, default=str))
        for b in ("house", "unit"):
            print(f"\n{b} trailing_3m_series (last 5): {series[b]['trailing_3m_series'][-5:]}")
            print(f"{b} seasonal_trend: {series[b]['seasonal_trend']}")
        return out

    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(json.dumps(out, default=str, separators=(",", ":")))
    print(f"\nWrote {out_path} ({out_path.stat().st_size} bytes)")
    return out


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", type=Path, default=DEFAULT_OUT)
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--suburbs", help="comma-separated subset (testing)")
    args = ap.parse_args()
    subs = [x.strip() for x in args.suburbs.split(",")] if args.suburbs else None

    # Self-report: STALE if the monthly cron stops firing, ERROR if it raises.
    with job_run("build_gc_dom_by_type", cadence_hours=24 * 31,
                 title="GC days-on-market by type (houses/units) JSON") as beat:
        out = build(dry_run=args.dry_run, out_path=args.out, suburbs=subs)
        h = (out["series"]["house"]["trailing_12m"] or {})
        u = (out["series"]["unit"]["trailing_12m"] or {})
        beat.detail = (f"houses {h.get('median_days_on_market')}d (n={h.get('transaction_count')}), "
                       f"units {u.get('median_days_on_market')}d (n={u.get('transaction_count')})")
        beat.metrics = {
            "panel_size": out["panel_size"],
            "house_pool": out["series"]["house"]["sample_size"],
            "unit_pool": out["series"]["unit"]["sample_size"],
        }


if __name__ == "__main__":
    main()
