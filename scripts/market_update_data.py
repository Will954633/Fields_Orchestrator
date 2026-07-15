#!/usr/bin/env python3
"""
Pull all verified market data needed for a quarterly market update video script.

Data sources (source of truth — matches fieldsestate.com.au charts):
  - Gold_Coast.precomputed_market_charts  → sales volume, days on market, market cycle, turnover
  - Gold_Coast.precomputed_indexed_prices → quarterly median, rolling 12m median
  - Gold_Coast.sqm_asking_prices          → SQM Research asking price trends

Usage:
  python3 scripts/market_update_data.py --suburb burleigh_waters
  python3 scripts/market_update_data.py --suburb burleigh_waters --quarters 12
  python3 scripts/market_update_data.py --suburb burleigh_waters --compare robina varsity_lakes
"""

import argparse
import os
import sys
import statistics
from datetime import datetime
from pymongo import MongoClient


def get_db():
    conn = os.environ.get("COSMOS_CONNECTION_STRING")
    if not conn:
        print("ERROR: COSMOS_CONNECTION_STRING not set. Run:")
        print("  set -a && source /home/fields/Fields_Orchestrator/.env && set +a")
        sys.exit(1)
    client = MongoClient(conn)
    return client["Gold_Coast"]


def pull_suburb_data(db, suburb, num_quarters=12):
    """Pull all chart data for a single suburb."""
    data = {"suburb": suburb}

    # 1. Sales Volume
    doc = db["precomputed_market_charts"].find_one({"_id": f"{suburb}_sales_volume"})
    if doc:
        data["sales_volume"] = {
            "timeline": doc.get("timeline", []),
            "seasonal_trend": doc.get("seasonal_trend", []),
            "historical_average": doc.get("historical_average"),
            "yoy_change": doc.get("yoy_change"),
        }
    else:
        data["sales_volume"] = None

    # 2. Days on Market
    doc = db["precomputed_market_charts"].find_one({"_id": f"{suburb}_days_on_market"})
    if doc:
        data["days_on_market"] = {
            "timeline": doc.get("timeline", []),
            "historical_average": doc.get("historical_average"),
            "historical_median": doc.get("historical_median"),
            "latest_quarter_median": doc.get("latest_quarter_median"),
            "yoy_change_days": doc.get("yoy_change_days"),
        }
    else:
        data["days_on_market"] = None

    # 3. Market Cycle
    doc = db["precomputed_market_charts"].find_one({"_id": f"{suburb}_market_cycle"})
    if doc:
        data["market_cycle"] = {
            "score": doc.get("score"),
            "phase": doc.get("phase"),
            "metrics": doc.get("metrics", {}),
        }
    else:
        data["market_cycle"] = None

    # 4. Turnover Rate
    doc = db["precomputed_market_charts"].find_one({"_id": f"{suburb}_turnover_rate"})
    if doc:
        data["turnover"] = {
            "total_stock": doc.get("total_stock"),
            "timeline": doc.get("timeline", []),
        }
    else:
        data["turnover"] = None

    # 5. Quarterly Median Prices + Rolling 12m
    doc = db["precomputed_indexed_prices"].find_one({"_id": suburb})
    if doc:
        data["median_prices"] = {
            "quarterly": doc.get("indexed_series", []),
            "rolling_12m": doc.get("rolling_12m_median_series", []),
            "current_rolling_12m": doc.get("rolling_12m_median_price"),
            "rolling_12m_yoy_pct": doc.get("rolling_12m_yoy_pct"),
            "total_growth_pct": doc.get("total_growth_pct"),
            "in_progress_quarter": doc.get("in_progress_quarter"),
        }
    else:
        data["median_prices"] = None

    # 6. SQM Asking Prices (latest)
    doc = db["sqm_asking_prices"].find_one({"_id": suburb})
    if doc:
        series = doc.get("series", [])
        latest = series[-1] if series else {}
        four_weeks_ago = series[-5] if len(series) >= 5 else {}
        one_year_ago = series[-53] if len(series) >= 53 else {}
        data["sqm_asking"] = {
            "latest": latest,
            "four_weeks_ago": four_weeks_ago,
            "one_year_ago": one_year_ago,
            "postcode_coverage": doc.get("postcode_coverage"),
        }
    else:
        data["sqm_asking"] = None

    return data


def get_current_quarter():
    """Return the current in-progress quarter string, e.g. '2026-Q2'."""
    now = datetime.now()
    q = (now.month - 1) // 3 + 1
    return f"{now.year}-Q{q}"


def get_last_completed_quarter(timeline):
    """Return the last timeline entry that isn't the current in-progress quarter."""
    current_q = get_current_quarter()
    for entry in reversed(timeline):
        if entry.get("period") != current_q:
            return entry
    return timeline[-1] if timeline else None


def format_price(p):
    if p is None:
        return "N/A"
    return f"${p:,.0f}"


def print_report(data, num_quarters=12):
    suburb = data["suburb"].replace("_", " ").title()
    print(f"\n{'='*70}")
    print(f"  MARKET UPDATE DATA — {suburb}")
    print(f"  Generated: {datetime.now().strftime('%Y-%m-%d %H:%M AEST')}")
    print(f"{'='*70}")

    # --- Sales Volume ---
    sv = data.get("sales_volume")
    if sv:
        timeline = sv["timeline"][-num_quarters:]
        latest = timeline[-1] if timeline else {}
        prev_q = timeline[-2] if len(timeline) >= 2 else {}
        yoy_q = None
        for t in timeline:
            if t["period"][-2:] == latest.get("period", "")[-2:] and t["period"] != latest.get("period"):
                yoy_q = t

        print(f"\n--- SALES VOLUME (houses only, deduplicated) ---")
        current_q = get_current_quarter()
        print(f"{'Quarter':<12} {'Sales':>6} {'YoY':>8} {'Moving Avg':>12}")
        print(f"{'-'*40}")
        for t in timeline:
            yoy = f"{t['yoy_change']:+.1f}%" if t.get("yoy_change") is not None else "—"
            ma = f"{t['moving_avg']:.1f}" if t.get("moving_avg") is not None else "—"
            flag = " ← IN PROGRESS" if t["period"] == current_q else ""
            print(f"{t['period']:<12} {t['sales_count']:>6} {yoy:>8} {ma:>12}{flag}")

        print(f"\nHistorical quarterly average: {sv['historical_average']}")
        print(f"Latest YoY change: {sv['yoy_change']}%")

        # Seasonal context
        if sv.get("seasonal_trend"):
            current_q = latest.get("period", "")[-2:]
            for s in sv["seasonal_trend"]:
                if s["quarter"] == current_q:
                    diff_pct = ((latest["sales_count"] - s["avg_sales_volume"]) / s["avg_sales_volume"]) * 100
                    print(f"10yr seasonal avg for {current_q}: {s['avg_sales_volume']:.0f} (current is {diff_pct:+.0f}% vs seasonal)")

    # --- Median Prices ---
    mp = data.get("median_prices")
    if mp:
        quarterly = [q for q in mp["quarterly"] if q["period"] >= "Q1 2023"][-num_quarters:]
        rolling = [r for r in mp["rolling_12m"] if r.get("period", r.get("quarter", "")) >= "Q1 2023"][-num_quarters:]

        print(f"\n--- MEDIAN HOUSE PRICE (quarterly) ---")
        print(f"{'Quarter':<12} {'Median':>14} {'Txns':>6}")
        print(f"{'-'*34}")
        for q in quarterly:
            print(f"{q['period']:<12} {format_price(q['median_price']):>14} {q['transaction_count']:>6}")

        print(f"\n--- ROLLING 12-MONTH MEDIAN ---")
        print(f"{'Quarter':<12} {'Median':>14} {'Txns':>6}")
        print(f"{'-'*34}")
        for r in rolling:
            period = r.get("period") or r.get("quarter")
            median = r.get("rolling_median") or r.get("rollingMedian")
            count = r.get("transaction_count") or r.get("transactionCount", "?")
            print(f"{period:<12} {format_price(median):>14} {count:>6}")

        print(f"\nCurrent rolling 12m median: {format_price(mp['current_rolling_12m'])}")
        print(f"Rolling 12m YoY growth: {mp['rolling_12m_yoy_pct']}%")
        print(f"10-year total growth: {mp['total_growth_pct']}%")

        # Calculate QoQ for latest
        if len(quarterly) >= 2:
            curr = quarterly[-1]["median_price"]
            prev = quarterly[-2]["median_price"]
            if curr and prev:
                qoq = ((curr - prev) / prev) * 100
                print(f"Latest QoQ change: {qoq:+.1f}% ({format_price(prev)} → {format_price(curr)})")

    # --- Days on Market ---
    dom = data.get("days_on_market")
    if dom:
        timeline = dom["timeline"][-num_quarters:]
        print(f"\n--- DAYS ON MARKET ---")
        print(f"{'Quarter':<12} {'Median':>8} {'Avg':>8} {'Count':>6} {'Quick<30d':>10} {'Slow>90d':>10}")
        print(f"{'-'*56}")
        for t in timeline:
            med = f"{t['median_days_on_market']:.0f}d" if t.get("median_days_on_market") is not None else "—"
            avg = f"{t['avg_days_on_market']:.0f}d" if t.get("avg_days_on_market") is not None else "—"
            quick = f"{t['quick_sales_pct']:.0f}%" if t.get("quick_sales_pct") is not None else "—"
            slow = f"{t['slow_sales_pct']:.0f}%" if t.get("slow_sales_pct") is not None else "—"
            print(f"{t['period']:<12} {med:>8} {avg:>8} {t.get('transaction_count', '?'):>6} {quick:>10} {slow:>10}")

        print(f"\nHistorical median: {dom['historical_median']} days")
        print(f"Latest quarter median: {dom['latest_quarter_median']} days")
        print(f"YoY change: {dom['yoy_change_days']} days")

    # --- Market Cycle ---
    mc = data.get("market_cycle")
    if mc:
        print(f"\n--- MARKET CYCLE ---")
        print(f"Score: {mc['score']}/100 — {mc['phase']}")
        for k, v in mc.get("metrics", {}).items():
            print(f"  {k}: {v}")

    # --- Turnover ---
    to = data.get("turnover")
    if to:
        print(f"\n--- ANNUAL TURNOVER ---")
        print(f"Total housing stock: {to['total_stock']:,}")
        print(f"{'Year':<8} {'Sales':>6} {'Rate':>8}")
        print(f"{'-'*24}")
        for t in to["timeline"][-5:]:
            print(f"{t['year']:<8} {t['sales']:>6} {t['turnover_rate']:>7.2f}%")

    # --- SQM Asking Prices ---
    sqm = data.get("sqm_asking")
    if sqm and sqm.get("latest"):
        print(f"\n--- SQM ASKING PRICES (latest: {sqm['latest'].get('date', '?')}) ---")
        print(f"Note: Postcode covers {sqm.get('postcode_coverage', '?')}")
        l = sqm["latest"]
        print(f"  Houses: {format_price(l.get('houses_all'))}")
        print(f"  Units:  {format_price(l.get('units_all'))}")
        if sqm.get("one_year_ago") and sqm["one_year_ago"].get("houses_all"):
            yoy_h = ((l["houses_all"] - sqm["one_year_ago"]["houses_all"]) / sqm["one_year_ago"]["houses_all"]) * 100
            yoy_u = ((l["units_all"] - sqm["one_year_ago"]["units_all"]) / sqm["one_year_ago"]["units_all"]) * 100
            print(f"  Houses YoY: {yoy_h:+.1f}%")
            print(f"  Units YoY:  {yoy_u:+.1f}%")


def print_comparison(all_data):
    """Print a side-by-side comparison table."""
    if len(all_data) < 2:
        return

    print(f"\n{'='*70}")
    print(f"  SUBURB COMPARISON")
    print(f"{'='*70}")

    headers = [d["suburb"].replace("_", " ").title() for d in all_data]
    col_w = 18

    print(f"\n{'Metric':<30}" + "".join(f"{h:>{col_w}}" for h in headers))
    print("-" * (30 + col_w * len(headers)))

    rows = []

    # Latest quarterly median
    row = ["Quarterly Median"]
    for d in all_data:
        mp = d.get("median_prices", {})
        q = mp.get("quarterly", []) if mp else []
        val = format_price(q[-1]["median_price"]) if q else "—"
        row.append(val)
    rows.append(row)

    # Rolling 12m
    row = ["Rolling 12m Median"]
    for d in all_data:
        mp = d.get("median_prices", {}) if d.get("median_prices") else {}
        row.append(format_price(mp.get("current_rolling_12m")))
    rows.append(row)

    # YoY growth
    row = ["12m YoY Growth"]
    for d in all_data:
        mp = d.get("median_prices", {}) if d.get("median_prices") else {}
        v = mp.get("rolling_12m_yoy_pct")
        row.append(f"{v:+.1f}%" if v is not None else "—")
    rows.append(row)

    # Sales volume (last completed quarter, not in-progress)
    row = ["Q Sales Volume"]
    for d in all_data:
        sv = d.get("sales_volume", {}) if d.get("sales_volume") else {}
        tl = sv.get("timeline", [])
        entry = get_last_completed_quarter(tl) if tl else None
        if entry:
            row.append(f"{entry['sales_count']} ({entry['period']})")
        else:
            row.append("—")
    rows.append(row)

    # Volume YoY (from last completed quarter)
    row = ["Volume YoY"]
    for d in all_data:
        sv = d.get("sales_volume", {}) if d.get("sales_volume") else {}
        tl = sv.get("timeline", [])
        entry = get_last_completed_quarter(tl) if tl else None
        if entry and entry.get("yoy_change") is not None:
            row.append(f"{entry['yoy_change']:+.1f}%")
        else:
            row.append("—")
    rows.append(row)

    # DOM
    row = ["Median DOM"]
    for d in all_data:
        dom = d.get("days_on_market", {}) if d.get("days_on_market") else {}
        v = dom.get("latest_quarter_median")
        row.append(f"{v}d" if v is not None else "—")
    rows.append(row)

    # DOM YoY
    row = ["DOM YoY Change"]
    for d in all_data:
        dom = d.get("days_on_market", {}) if d.get("days_on_market") else {}
        v = dom.get("yoy_change_days")
        row.append(f"{v:+.1f}d" if v is not None else "—")
    rows.append(row)

    # Market cycle
    row = ["Market Phase"]
    for d in all_data:
        mc = d.get("market_cycle", {}) if d.get("market_cycle") else {}
        row.append(mc.get("phase", "—"))
    rows.append(row)

    # 10yr growth
    row = ["10yr Growth"]
    for d in all_data:
        mp = d.get("median_prices", {}) if d.get("median_prices") else {}
        v = mp.get("total_growth_pct")
        row.append(f"{v:+.1f}%" if v is not None else "—")
    rows.append(row)

    for row in rows:
        print(f"{row[0]:<30}" + "".join(f"{v:>{col_w}}" for v in row[1:]))


def main():
    parser = argparse.ArgumentParser(description="Pull market update data for video scripts")
    parser.add_argument("--suburb", required=True, help="Primary suburb (e.g. burleigh_waters)")
    parser.add_argument("--compare", nargs="*", help="Comparison suburbs (e.g. robina varsity_lakes)")
    parser.add_argument("--quarters", type=int, default=12, help="Number of quarters to show (default 12)")
    args = parser.parse_args()

    db = get_db()

    # Primary suburb
    primary = pull_suburb_data(db, args.suburb, args.quarters)
    print_report(primary, args.quarters)

    # Comparison suburbs
    all_data = [primary]
    if args.compare:
        for comp in args.compare:
            comp_data = pull_suburb_data(db, comp, args.quarters)
            print_report(comp_data, args.quarters)
            all_data.append(comp_data)

    if len(all_data) > 1:
        print_comparison(all_data)

    print(f"\n{'='*70}")
    print(f"  DATA SOURCES (all match fieldsestate.com.au charts)")
    print(f"{'='*70}")
    print(f"  Volume:  precomputed_market_charts.{{suburb}}_sales_volume")
    print(f"  Price:   precomputed_indexed_prices.{{suburb}}")
    print(f"  DOM:     precomputed_market_charts.{{suburb}}_days_on_market")
    print(f"  Cycle:   precomputed_market_charts.{{suburb}}_market_cycle")
    print(f"  Asking:  sqm_asking_prices.{{suburb}}")
    print(f"{'='*70}\n")


if __name__ == "__main__":
    main()
