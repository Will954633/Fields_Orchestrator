#!/usr/bin/env python3
"""
Build public/data/gc_dom_by_type.json — the static data behind the Gold-Coast-wide
"How Long Are Gold Coast Homes Taking to Sell?" (houses vs units) chart on
/news/gold-coast.

DATA SOURCE — system_monitor.domain_sold  (CHANGED 2026-09-16, see below)
-------------------------------------------------------------------------
This chart is now sourced from `system_monitor.domain_sold` — the running Domain
`searchListings` GC cron (soldDate − dateListed DOM, agent-listed sales) — the SAME
source that feeds the "Do Homes Sell Faster Here or in the Big Cities?" chart. It
was PREVIOUSLY built from `scraped_data.property_timeline` + `listing_status='sold'`
pooled per suburb, and that is exactly what made it wrong.

WHY THE SWITCH (root cause)
  property_timeline backfills SLOWLY: a sale only enters a property's timeline once
  we re-scrape THAT property after Domain has posted the sale to its history. Homes
  with long campaigns are still in our nightly scrape at sale time, so their sold
  event lands fast; quick sales leave the market between passes and only surface on
  a later sweep — months later. So the recent trailing window was both under-counted
  AND skewed slow. Measured 2026-09-16, same window/panel/type: timeline gave median
  61d (n=317) while domain_sold gave 39d (n=780); at 12 months they AGREE (28 vs 29)
  because the timeline has backfilled by then. domain_sold is a fresh, near-complete
  snapshot of Domain's current sold set and does not have this recency lag. See
  docs/DATA_CAPTURE_TWO_PIPELINES.md and logs/fix-history/2026-09-16.md.

METHOD
  * Panel: the eligible 63-suburb set from compute_gc_composite() (kept in sync with
    the price chart above it — do not hardcode). Mapped to domain_sold suburb_key
    slugs ("robina-4226").
  * Records: domain_sold rows for the panel, split by the normalised `dwelling`
    field (house / unit; "other" dropped). One row per listing_id (already unique).
  * DOM validity: 3 < dom_days < 365 (the pipeline's own outlier gate, and the
    "excludes 3 days or fewer" pre-sold exclusion the basis_note documents).
  * Then the SAME trailing/seasonal computation the other DOM charts use:
      - trailing_3m_series / trailing_12m_series : monthly rolling-median points
      - seasonal_trend                           : 12 per-calendar-month typicals
                                                   (10yr, excl. 2020-2021 COVID)
      - trailing_3m / trailing_12m               : the headline tile, ending last
                                                   completed month.

The frontend range pills (12 months / 3 years) slice the monthly series; the window
pills (Rolling 3-mo / 12-mo) pick which series; the pill (Houses / Units) picks which
`series.*` block. Output schema is unchanged — no frontend change required.

Ongoing refresh: wire into run_monthly_market_precompute.sh (after the GC domain_sold
cron). Self-reports via job_run so a silent failure shows STALE/ERROR on the Systems
Health sheet.

Usage:
  python3 scripts/build_gc_dom_by_type.py [--out PATH] [--dry-run] [--suburbs a,b,c]
"""
import argparse
import json
import sys
from collections import defaultdict
from datetime import datetime
from pathlib import Path
from statistics import median, mean

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
sys.path.insert(0, str(Path(__file__).resolve().parent))
sys.path.insert(0, "/home/fields/Feilds_Website/08_Market_Narrative_Engine")

from shared.db import get_client  # noqa: E402
from shared.env import load_env  # noqa: E402
from build_gc_leading_indicators import PARENT_JSON, compute_gc_composite  # noqa: E402
from job_status import job_run  # noqa: E402

# Reuse the exact, battle-tested trailing/rolling helpers so every DOM chart on the
# page measures the same thing the same way.
from precompute_market_charts import (  # noqa: E402
    _monthly_trailing_series,
    _rolling_median_window,
    _trailing_12m_dom,
    _add_months,
    _month_end,
)

DEFAULT_OUT = Path("/home/fields/Feilds_Website/01_Website/public/data/gc_dom_by_type.json")

MONTH_NAMES = ['Jan', 'Feb', 'Mar', 'Apr', 'May', 'Jun',
               'Jul', 'Aug', 'Sep', 'Oct', 'Nov', 'Dec']

# GC-wide volume is ~15-40x a single suburb, so a monthly window carries hundreds
# of sales. These floors just trim the sparse leading edge of the earliest months.
MIN_N_3M = 12
MIN_N_12M = 30

BASIS_NOTE = (
    "Median days on market — advertised date to sold date, agent-listed sales, from "
    "Domain — pooled across the Gold Coast composite suburb panel. Excludes sales "
    "advertised 3 days or fewer (pre-sold / off-market stock listed only to record a "
    "result). Houses and units are counted separately. Not comparable with figures "
    "published by other providers, whose definitions differ."
)


def _gc_panel_slugs(ds, elig):
    """GC composite panel expressed as domain_sold suburb_key slugs ("robina-4226")."""
    slugs = set()
    for key in ds.distinct("suburb_key"):
        stem = key.rsplit("-", 1)[0].replace("-", "_")
        if stem in elig:
            slugs.add(key)
    return slugs


def _gather_domain_sold(ds, slugs, dwelling):
    """domain_sold rows for the panel, one per listing_id, shaped as the {date,
    days_on_market} records the series helpers expect. 3 < dom < 365 outlier gate."""
    out = []
    seen = set()
    cursor = ds.find(
        {"suburb_key": {"$in": list(slugs)}, "dwelling": dwelling, "dom_days": {"$ne": None}},
        {"sold_date": 1, "dom_days": 1, "listing_id": 1, "address": 1},
    )
    for r in cursor:
        dom = r.get("dom_days")
        if dom is None or not (3 < dom < 365):
            continue
        sd = r.get("sold_date")
        if not sd:
            continue
        lid = r.get("listing_id")
        if lid is not None:
            if lid in seen:
                continue
            seen.add(lid)
        try:
            dt = sd if isinstance(sd, datetime) else datetime.fromisoformat(str(sd)[:10])
        except (ValueError, TypeError):
            continue
        out.append({"date": dt, "days_on_market": dom,
                    "address": r.get("address"), "_id": lid})
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
    elig = set(compute_gc_composite(quarters, qidx)["eligible"])
    if suburbs:
        elig = {s for s in elig if s in set(suburbs)}

    ds = get_client()["system_monitor"]["domain_sold"]
    slugs = _gc_panel_slugs(ds, elig)
    now = datetime.now()

    pools = {}
    for b in ("house", "unit"):
        pools[b] = _gather_domain_sold(ds, slugs, b)
        print(f"  {b}: {len(pools[b])} sold records from domain_sold "
              f"({len(slugs)} panel suburbs)")

    # Last completed month (a partial current month never drags the headline).
    last_y, last_m = _add_months(now.year, now.month, -1)

    series = {}
    for b in ("house", "unit"):
        series[b] = _series_for_type(pools[b], last_y, last_m)
        print(f"  {b}: pool={series[b]['sample_size']}; "
              f"3m pts={len(series[b]['trailing_3m_series'])}, "
              f"12m pts={len(series[b]['trailing_12m_series'])}, "
              f"headline3m={ (series[b]['trailing_3m'] or {}).get('median_days_on_market') }, "
              f"headline12m={ (series[b]['trailing_12m'] or {}).get('median_days_on_market') }")

    out = {
        "generated": datetime.now().strftime("%Y-%m-%d"),
        "panel_size": len(elig),
        "basis_note": BASIS_NOTE,
        "source": "domain_sold",
        "series": series,
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
