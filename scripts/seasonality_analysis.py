#!/usr/bin/env python3
"""
Seasonality analysis — canonical, reproducible source of truth.

Builds the Fields seasonal-timing dataset from the per-property sale history
("Sale" events in property_timeline) across the 8 Southern Gold Coast suburbs,
then runs the matched-cohort, annual-average-baseline analysis that backs the
"When Should You Sell?" article and the house mini-site seasonality strip.

WHY THIS EXISTS
    The corrected article (slug december-listing-paradox) documented its method
    but its analysis script was lost (it lived in /tmp). The only committed
    seasonal script used a discredited March/April/May baseline. This script is
    the single, auditable replacement: same input every run, row-level CSV
    published alongside the figures.

DATASET
    Source: Gold_Coast.<suburb> documents, sale events unioned from three
    timeline paths (deduplicated within and across documents):
        - scraped_data.property_timeline[]            (date, price, type)
        - scraped_data_v2.timeline[]                  (event_date, event_price)
        - scraped_data_apr01_recovered.property_timeline[]
    A sale event = category == "Sale" / is_sold, with a parseable date and a
    plausible price. Property type + bedroom count come from the current doc
    (same matching assumption the article used).

METHOD (matched cohort, annual-average baseline)
    stratum  = (suburb, property_type, bedrooms, year)
    For each stratum with >= MIN_STRATUM_SALES sales spanning >= MIN_STRATUM_MONTHS
    distinct months:
        annual_median        = median(price) over the whole stratum-year
        month_median[m]      = median(price) in that stratum-year-month
        deviation[m]         = (month_median - annual_median) / annual_median
        deviation winsorized to +/- WINSOR
    Each month's headline figure = weighted mean of its stratum deviations,
    weight = number of sales in that (stratum, month).

OUTPUTS  (written to 08_Seller-Book/Market_Data/seasonality_v2/)
    sales_dataset_<window>.csv     row-level publishable dataset
    monthly_summary_<window>.csv   12-row month -> premium table
    strata_detail_<window>.csv     per-(stratum,month) deviations
    RUN_SUMMARY_<window>.md        human-readable summary + article delta

USAGE
    python3 scripts/seasonality_analysis.py                 # 2020-2025 (primary)
    python3 scripts/seasonality_analysis.py --start 2010    # custom window
    python3 scripts/seasonality_analysis.py --suburb robina # single suburb
"""

from __future__ import annotations
import argparse
import csv
import os
import re
import statistics
from collections import defaultdict
from datetime import datetime

from src.mongo_client_factory import get_mongo_client

SUBURBS = [
    "robina", "varsity_lakes", "burleigh_waters", "mudgeeraba",
    "merrimac", "carrara", "worongary", "reedy_creek",
]
TIMELINE_PATHS = [
    ("scraped_data", "property_timeline", "date", "price", "type"),
    ("scraped_data_v2", "timeline", "event_date", "event_price", "price_description"),
    ("scraped_data_apr01_recovered", "property_timeline", "date", "price", "type"),
]
MONTHS = ["Jan", "Feb", "Mar", "Apr", "May", "Jun",
          "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"]

# Tunable, documented analysis parameters.
WINSOR = 0.30              # +/-30% cap on stratum-month deviations
MIN_STRATUM_SALES = 6      # min sales in a stratum-year to use it
MIN_STRATUM_MONTHS = 3     # min distinct months in a stratum-year to use it
PRICE_MIN, PRICE_MAX = 100_000, 30_000_000

OUT_DIR = os.path.join(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
    "08_Seller-Book", "Market_Data", "seasonality_v2",
)

# Article figures (annual-average baseline) for the delta report.
ARTICLE_PCT = {
    "Jan": -3.83, "Feb": -1.74, "Mar": -0.93, "Apr": 0.09, "May": 2.29, "Jun": 1.25,
    "Jul": 0.55, "Aug": 1.43, "Sep": 3.84, "Oct": 5.46, "Nov": 5.45, "Dec": 6.05,
}
ARTICLE_TOTAL = 13_585


def parse_price(v):
    if v is None:
        return None
    if isinstance(v, (int, float)):
        p = float(v)
    else:
        m = re.search(r"(\d[\d,]*)", str(v).replace(" ", ""))
        if not m:
            return None
        p = float(m.group(1).replace(",", ""))
    return p if PRICE_MIN <= p <= PRICE_MAX else None


def parse_date(v):
    if not v:
        return None
    s = str(v)
    m = re.search(r"(\d{4})-(\d{2})-(\d{2})", s)
    if m:
        y, mo = int(m.group(1)), int(m.group(2))
    else:
        m = re.search(r"([A-Za-z]{3})\s+(\d{4})", s)  # "Oct 2016"
        if not m:
            return None
        try:
            mo = MONTHS.index(m.group(1).title()[:3]) + 1
        except ValueError:
            return None
        y = int(m.group(2))
    if not (1 <= mo <= 12) or not (1900 <= y <= 2100):
        return None
    return y, mo


def extract_sales(db, suburb):
    """Yield deduplicated sale rows for one suburb."""
    proj = {p[0]: 1 for p in TIMELINE_PATHS}
    proj.update({"property_type": 1, "bedrooms": 1, "ADDRESS_PID": 1,
                 "address": 1, "complete_address": 1})
    seen = set()  # (address_key, year, month, price) across docs
    for doc in db[suburb].find({}, proj):
        addr = (doc.get("ADDRESS_PID") or doc.get("complete_address")
                or doc.get("address") or str(doc.get("_id")))
        ptype = (doc.get("property_type") or "Unknown").strip().title()
        beds = doc.get("bedrooms")
        try:
            beds = int(beds) if beds is not None else None
        except (ValueError, TypeError):
            beds = None
        doc_seen = set()  # within-doc dedup across the 3 paths
        for root, key, dfield, pfield, mfield in TIMELINE_PATHS:
            node = doc.get(root) or {}
            events = node.get(key) if isinstance(node, dict) else None
            for e in (events or []):
                cat = str(e.get("category") or e.get("type") or "").lower()
                if "sale" not in cat and not e.get("is_sold"):
                    continue
                pd = parse_date(e.get(dfield))
                price = parse_price(e.get(pfield))
                if not pd or price is None:
                    continue
                y, mo = pd
                ddk = (y, mo, int(price))
                if ddk in doc_seen:
                    continue
                doc_seen.add(ddk)
                gk = (addr, y, mo, int(price))
                if gk in seen:
                    continue
                seen.add(gk)
                yield {
                    "suburb": suburb, "address": addr, "year": y, "month": mo,
                    "month_name": MONTHS[mo - 1], "price": price,
                    "property_type": ptype, "bedrooms": beds,
                    "method": str(e.get(mfield) or "").strip(),
                }


def winsorize(x, cap):
    return max(-cap, min(cap, x))


def run(rows, start, end, exclude_years=()):
    exclude_years = set(exclude_years)
    rows = [r for r in rows if start <= r["year"] <= end
            and r["year"] not in exclude_years
            and r["bedrooms"] is not None]
    # Group into strata: (suburb, type, beds, year)
    strata = defaultdict(list)
    for r in rows:
        strata[(r["suburb"], r["property_type"], r["bedrooms"], r["year"])].append(r)

    # month -> list of (deviation, weight)
    month_devs = defaultdict(list)
    strata_detail = []
    used_strata = 0
    used_sales = 0
    for key, recs in strata.items():
        months_present = {r["month"] for r in recs}
        if len(recs) < MIN_STRATUM_SALES or len(months_present) < MIN_STRATUM_MONTHS:
            continue
        annual_median = statistics.median(r["price"] for r in recs)
        if annual_median <= 0:
            continue
        used_strata += 1
        by_month = defaultdict(list)
        for r in recs:
            by_month[r["month"]].append(r["price"])
        for mo, prices in by_month.items():
            mm = statistics.median(prices)
            dev = winsorize((mm - annual_median) / annual_median, WINSOR)
            w = len(prices)
            month_devs[mo].append((dev, w))
            used_sales += w
            strata_detail.append({
                "suburb": key[0], "property_type": key[1], "bedrooms": key[2],
                "year": key[3], "month": MONTHS[mo - 1], "n_sales": w,
                "month_median": round(mm), "annual_median": round(annual_median),
                "deviation_pct": round(dev * 100, 3),
            })

    summary = []
    for i, name in enumerate(MONTHS, start=1):
        dw = month_devs.get(i, [])
        tw = sum(w for _, w in dw)
        wmean = sum(d * w for d, w in dw) / tw if tw else 0.0
        summary.append({
            "month": name, "premium_pct": round(wmean * 100, 2),
            "strata": len(dw), "comparisons": tw,
        })
    return summary, strata_detail, used_strata, used_sales, len(rows)


def write_outputs(window, rows, summary, strata_detail, totals):
    os.makedirs(OUT_DIR, exist_ok=True)
    used_strata, used_sales, n_rows = totals

    ds = os.path.join(OUT_DIR, f"sales_dataset_{window}.csv")
    with open(ds, "w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=["suburb", "address", "year", "month",
                                          "month_name", "price", "property_type",
                                          "bedrooms", "method"])
        w.writeheader()
        for r in sorted(rows, key=lambda x: (x["suburb"], x["year"], x["month"])):
            w.writerow(r)

    ms = os.path.join(OUT_DIR, f"monthly_summary_{window}.csv")
    with open(ms, "w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=["month", "premium_pct", "strata",
                                          "comparisons", "article_pct", "delta_pp"])
        w.writeheader()
        for s in summary:
            art = ARTICLE_PCT[s["month"]]
            s2 = dict(s, article_pct=art,
                      delta_pp=round(s["premium_pct"] - art, 2))
            w.writerow(s2)

    sd = os.path.join(OUT_DIR, f"strata_detail_{window}.csv")
    with open(sd, "w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=["suburb", "property_type", "bedrooms",
                                          "year", "month", "n_sales",
                                          "month_median", "annual_median",
                                          "deviation_pct"])
        w.writeheader()
        w.writerows(strata_detail)

    return ds, ms, sd


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--start", type=int, default=2020)
    ap.add_argument("--end", type=int, default=2025)
    ap.add_argument("--exclude-years", default="",
                    help="comma-separated years to drop, e.g. 2019,2020 (COVID)")
    ap.add_argument("--suburb", default=None, help="single suburb (default: all 8)")
    args = ap.parse_args()

    exclude_years = {int(y) for y in args.exclude_years.split(",") if y.strip()}
    suburbs = [args.suburb] if args.suburb else SUBURBS
    excl_tag = ("_excl" + "-".join(str(y) for y in sorted(exclude_years))) if exclude_years else ""
    window = f"{args.start}_{args.end}{excl_tag}" + (f"_{args.suburb}" if args.suburb else "")

    c = get_mongo_client()
    db = c["Gold_Coast"]

    print(f"Extracting sale history from timelines ({', '.join(suburbs)}) ...")
    all_rows = []
    for s in suburbs:
        srows = list(extract_sales(db, s))
        all_rows.extend(srows)
        print(f"  {s:18} unique sale events (all-time): {len(srows)}")
    print(f"Total unique sale events (all-time): {len(all_rows)}")

    # Per-year density (with bedrooms) over the requested span.
    yr_counts = defaultdict(int)
    for r in all_rows:
        if args.start <= r["year"] <= args.end and r["bedrooms"] is not None:
            yr_counts[r["year"]] += 1
    print("\nSales by year (with bedrooms) over span:")
    for y in range(args.start, args.end + 1):
        flag = "  [EXCLUDED]" if y in exclude_years else ""
        print(f"  {y}: {yr_counts.get(y, 0):5}{flag}")

    summary, strata_detail, used_strata, used_sales, n_in_window = run(
        all_rows, args.start, args.end, exclude_years)

    # The publishable dataset = rows inside the window, excluded years removed.
    pub_rows = [r for r in all_rows if args.start <= r["year"] <= args.end
                and r["year"] not in exclude_years and r["bedrooms"] is not None]
    ds, ms, sd = write_outputs(window, pub_rows, summary, strata_detail,
                               (used_strata, used_sales, len(pub_rows)))

    print(f"\n=== MATCHED-COHORT SEASONALITY ({args.start}-{args.end}) ===")
    print(f"Sales in window (with bedrooms): {len(pub_rows)}")
    print(f"Strata used: {used_strata} | sales in matched strata: {used_sales}")
    print(f"\n{'Month':5} {'Fields %':>9} {'Article %':>10} {'Delta pp':>9} "
          f"{'Strata':>7} {'Comparisons':>12}")
    h1 = h2 = 0.0
    for i, s in enumerate(summary):
        art = ARTICLE_PCT[s["month"]]
        print(f"{s['month']:5} {s['premium_pct']:>9.2f} {art:>10.2f} "
              f"{s['premium_pct']-art:>9.2f} {s['strata']:>7} {s['comparisons']:>12}")
        if i < 6:
            h1 += s["premium_pct"]
        else:
            h2 += s["premium_pct"]
    print(f"\nH1 (Jan-Jun) avg: {h1/6:+.2f}%   H2 (Jul-Dec) avg: {h2/6:+.2f}%")
    print(f"Article total sales: {ARTICLE_TOTAL} | our window total: {len(pub_rows)}")
    print(f"\nOutputs:\n  {ds}\n  {ms}\n  {sd}")


if __name__ == "__main__":
    main()
