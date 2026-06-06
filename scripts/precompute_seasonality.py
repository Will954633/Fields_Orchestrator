#!/usr/bin/env python3
"""
Precompute monthly sale-price seasonality per suburb → Gold_Coast.precomputed_seasonality.

Source of truth: each property's `scraped_data.property_timeline` sold events (the same
multi-year House sold series that feeds precomputed_indexed_prices). For each suburb we:

  1. Pull every sold (date, price) for House sales over the window.
  2. Detrend by dividing each sale by its YEAR median — this removes market growth so a
     month's figure reflects SEASON, not the fact that later years sold higher.
  3. Average the detrended ratio within each calendar month → a seasonal premium vs the
     annual baseline. Report the per-month sale count so reliability is transparent.

Guards (editorial: cite limitations, respect sample size):
  - Require >= MIN_TOTAL House sales over the window and >= MIN_PER_MONTH in every month;
    otherwise the suburb is skipped (no seasonality doc written → slot stays pending).

Usage:
  python3 scripts/precompute_seasonality.py                 # core + report suburbs
  python3 scripts/precompute_seasonality.py --suburb robina
  python3 scripts/precompute_seasonality.py --all-report-suburbs
"""
from __future__ import annotations
import argparse
import os
import statistics as stats
import sys
import time
from collections import defaultdict
from datetime import datetime, timezone

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from pymongo import MongoClient
from pymongo.errors import OperationFailure

MONTHS = ["Jan", "Feb", "Mar", "Apr", "May", "Jun",
          "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"]
CORE_SUBURBS = ["robina", "varsity_lakes", "burleigh_waters"]
WINDOW_START = "2015-01-01"
MIN_TOTAL = 150        # min House sales over the whole window
MIN_PER_MONTH = 8      # min House sales in every calendar month
PROPERTY_TYPE = "House"


def get_conn():
    conn = os.environ.get("COSMOS_CONNECTION_STRING")
    if not conn:
        env_path = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), ".env")
        for line in open(env_path):
            if line.startswith("COSMOS_CONNECTION_STRING="):
                conn = line.split("=", 1)[1].strip().strip('"')
                break
    return conn


def cosmos_retry(fn, label, tries=5):
    delay = 1.0
    for i in range(tries):
        try:
            return fn()
        except OperationFailure as e:
            if e.code == 16500 and i < tries - 1:
                time.sleep(delay)
                delay *= 1.5
                continue
            raise


def fetch_sold(gc_db, suburb_key):
    """Return list of (year:int, month:int, price:float) for House sold timeline events."""
    pipeline = [
        {"$unwind": "$scraped_data.property_timeline"},
        {"$match": {
            "scraped_data.property_timeline.is_sold": True,
            "scraped_data.property_timeline.price": {"$ne": None, "$gt": 0},
            "scraped_data.features.property_type": PROPERTY_TYPE,
            "scraped_data.property_timeline.date": {"$gte": WINDOW_START},
        }},
        {"$project": {"_id": 0,
                      "date": "$scraped_data.property_timeline.date",
                      "price": "$scraped_data.property_timeline.price"}},
    ]
    rows = cosmos_retry(lambda: list(gc_db[suburb_key].aggregate(pipeline)),
                        f"{suburb_key}.seasonality")
    out = []
    for r in rows:
        d = str(r.get("date") or "")
        if len(d) < 7:
            continue
        try:
            y, m = int(d[0:4]), int(d[5:7])
            p = float(r["price"])
        except (ValueError, TypeError):
            continue
        if 1 <= m <= 12 and p > 0:
            out.append((y, m, p))
    return out


def compute_seasonality(sold):
    """Detrend by year median, average detrended ratio per calendar month."""
    if len(sold) < MIN_TOTAL:
        return None, f"only {len(sold)} House sales (< {MIN_TOTAL})"

    by_year = defaultdict(list)
    for y, m, p in sold:
        by_year[y].append(p)
    year_median = {y: stats.median(ps) for y, ps in by_year.items() if ps}

    ratios = defaultdict(list)   # month -> [price/year_median]
    all_ratios = []
    for y, m, p in sold:
        ym = year_median.get(y)
        if ym and ym > 0:
            r = p / ym
            ratios[m].append(r)
            all_ratios.append(r)

    counts = {m: len(ratios[m]) for m in range(1, 13)}
    thin = [MONTHS[m - 1] for m in range(1, 13) if counts[m] < MIN_PER_MONTH]
    if thin:
        return None, f"thin months {thin} (< {MIN_PER_MONTH} sales)"

    # Median-based + centred on the overall median ratio. Medians are robust to the
    # right-skew of prices (mean(price)/median > 1 would otherwise push every month
    # positive); centring makes premiums genuine deviations from the annual norm.
    base = stats.median(all_ratios)
    months = []
    for m in range(1, 13):
        premium = (stats.median(ratios[m]) / base - 1.0) * 100.0
        months.append({"month": MONTHS[m - 1],
                       "premiumPct": round(premium, 1),
                       "soldCount": counts[m]})

    prem = [mo["premiumPct"] for mo in months]
    years = sorted(by_year.keys())
    return {
        "months": months,
        "peakMonthIndex": prem.index(max(prem)),
        "troughMonthIndex": prem.index(min(prem)),
        "scopeLabel": f"{PROPERTY_TYPE} sales",
        "windowLabel": f"{years[0]}–{years[-1]}",
        "totalSales": len(sold),
        "method": "year-median detrended; premium = mean(price/year_median) − 1",
    }, "ok"


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--suburb", help="single suburb_key")
    ap.add_argument("--all-report-suburbs", action="store_true",
                    help="core + every suburb that has a property_report")
    args = ap.parse_args()

    client = MongoClient(get_conn())
    gc = client["Gold_Coast"]

    if args.suburb:
        suburbs = [args.suburb]
    else:
        suburbs = list(CORE_SUBURBS)
        report_subs = client["system_monitor"]["property_reports"].distinct("suburb_key")
        for s in report_subs:
            if s and s not in suburbs:
                suburbs.append(s)

    now = datetime.now(timezone.utc)
    col = gc["precomputed_seasonality"]
    written = 0
    for sub in suburbs:
        if sub not in gc.list_collection_names():
            print(f"  {sub}: no collection — skip")
            continue
        sold = fetch_sold(gc, sub)
        result, msg = compute_seasonality(sold)
        if result is None:
            print(f"  {sub}: SKIP — {msg}")
            continue
        doc = {"_id": sub, "suburb_key": sub, **result, "last_updated": now}
        cosmos_retry(lambda: col.replace_one({"_id": sub}, doc, upsert=True),
                     f"{sub}.write")
        peak = result["months"][result["peakMonthIndex"]]
        trough = result["months"][result["troughMonthIndex"]]
        print(f"  {sub}: {result['totalSales']} sales {result['windowLabel']} | "
              f"peak {peak['month']} {peak['premiumPct']:+.1f}% · "
              f"trough {trough['month']} {trough['premiumPct']:+.1f}%")
        written += 1

    print(f"\nWrote {written}/{len(suburbs)} suburb seasonality docs → precomputed_seasonality")
    client.close()


if __name__ == "__main__":
    main()
