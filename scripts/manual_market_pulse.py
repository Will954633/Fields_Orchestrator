#!/usr/bin/env python3
"""
manual_market_pulse.py — Manual market pulse update tool for collaborative sessions.

This script provides the data infrastructure for manually writing market
summaries with Claude in a VS Code session. It can:

1. Show all current data for each category (--show-data)
2. Show current summaries (--show-current)
3. Write a manual summary for a specific category (--write)
4. Check if manual updates exist for this month (--check)

Manual summaries are stored in the same system_monitor.market_pulse collection
but marked with source="manual". The automated fallback (generate_market_pulse.py)
checks for these and skips categories that have been manually updated this month.

Usage:
    python3 scripts/manual_market_pulse.py --show-data                    # all data
    python3 scripts/manual_market_pulse.py --show-data --category sell-now # one category
    python3 scripts/manual_market_pulse.py --show-current                 # current summaries
    python3 scripts/manual_market_pulse.py --check                        # check monthly status
    python3 scripts/manual_market_pulse.py --write --suburb robina --category sell-now \\
        --verdict sellers_advantage --summary "Your summary text here"
"""

import os
import sys
import json
import argparse
from datetime import datetime
from pymongo import MongoClient

TARGET_SUBURBS = ["robina", "burleigh_waters", "varsity_lakes"]
DISPLAY_NAMES = {
    "robina": "Robina",
    "burleigh_waters": "Burleigh Waters",
    "varsity_lakes": "Varsity Lakes",
}

CATEGORIES = {
    "sell-now": "Should I Sell Now?",
    "buy": "Is Now a Good Time to Buy?",
    "crash-risk": "Crash Risk",
    "overview": "Market Overview",
    "houses-vs-units": "Houses vs Units",
    "direction": "Market Direction",
    "suburb-compare": "Suburb Comparison",
}

VERDICTS = {
    "sell-now": ["strong_sellers_market", "sellers_advantage", "balanced", "buyers_advantage", "strong_buyers_market"],
    "buy": ["strong_buyer_conditions", "moderate_buyer_conditions", "neutral", "limited_buyer_power", "very_limited_buyer_power"],
    "crash-risk": ["very_low_risk", "low_risk", "moderate_risk", "elevated_risk", "high_risk"],
    "overview": ["strong_growth", "moderate_growth", "stable", "cooling", "declining"],
    "houses-vs-units": ["houses_strongly_outperforming", "houses_outperforming", "similar_performance", "units_outperforming", "units_strongly_outperforming"],
    "direction": ["strongly_rising", "rising", "plateauing", "softening", "declining"],
    "suburb-compare": ["top_performer", "above_average", "mid_pack", "below_average", "underperformer"],
}


def get_db():
    conn_str = os.environ.get("COSMOS_CONNECTION_STRING")
    if not conn_str:
        print("ERROR: COSMOS_CONNECTION_STRING not set")
        sys.exit(1)
    client = MongoClient(conn_str)
    return client


def show_data(suburb=None, category=None):
    """Display all current market data for writing summaries."""
    client = get_db()
    gc = client["Gold_Coast"]
    sm = client["system_monitor"]

    suburbs = [suburb] if suburb else TARGET_SUBURBS

    for s in suburbs:
        display = DISPLAY_NAMES.get(s, s)
        print(f"\n{'='*70}")
        print(f"  {display}")
        print(f"{'='*70}")

        # --- Price data ---
        idx = gc["precomputed_indexed_prices"].find_one({"_id": s})
        if idx:
            series = idx.get("indexed_series", [])
            if series:
                latest = series[-1]
                print(f"\n  📈 MEDIAN PRICE: ${latest.get('median_price', 0):,.0f} ({latest.get('period', '')})")
                if len(series) >= 2:
                    prev = series[-2]
                    qoq = ((latest['median_price'] - prev['median_price']) / prev['median_price'] * 100) if prev['median_price'] else 0
                    print(f"     QoQ change: {qoq:+.1f}%")
                if len(series) >= 5:
                    year_ago = series[-5]
                    yoy = ((latest['median_price'] - year_ago['median_price']) / year_ago['median_price'] * 100) if year_ago['median_price'] else 0
                    print(f"     YoY change: {yoy:+.1f}%")
                print(f"     Transactions: {latest.get('transaction_count', '?')} in quarter")

        # --- DOM ---
        dom = gc["precomputed_market_charts"].find_one({"_id": f"{s}_days_on_market"})
        if dom:
            timeline = dom.get("dom_timeline", dom.get("timeline", []))
            if timeline:
                latest_dom = timeline[-1]
                print(f"\n  ⏱️  DAYS ON MARKET: {latest_dom.get('median_days_on_market', '?')} days median ({latest_dom.get('period', '')})")
                print(f"     Average: {latest_dom.get('avg_days_on_market', '?')} days")
                print(f"     Quick sales (<30d): {latest_dom.get('quick_sales_pct', '?')}%")

        # --- Sales Volume ---
        sv = gc["precomputed_market_charts"].find_one({"_id": f"{s}_sales_volume"})
        if sv:
            timeline = sv.get("timeline", [])
            if timeline:
                latest_sv = timeline[-1]
                print(f"\n  📊 SALES VOLUME: {latest_sv.get('sales_count', '?')} sales ({latest_sv.get('period', '')})")
                print(f"     YoY change: {latest_sv.get('yoy_change', '?')}%")

        # --- Active Listings ---
        al = gc["precomputed_active_listings"].find_one({"_id": s})
        if al:
            snapshots = al.get("snapshots", [])
            if snapshots:
                print(f"\n  🏘️  ACTIVE LISTINGS: {snapshots[-1].get('active_listings', '?')}")

        # --- Absorption Rate ---
        from datetime import timedelta
        active = gc[s].count_documents({"listing_status": "for_sale"})
        ninety_days_ago = (datetime.now() - timedelta(days=90)).strftime("%Y-%m-%d")
        sold_90d = gc[s].count_documents({"listing_status": "sold", "sold_date": {"$gte": ninety_days_ago}})
        monthly_sales = sold_90d / 3.0 if sold_90d > 0 else 0
        absorption = round(active / monthly_sales, 1) if monthly_sales > 0 else None
        print(f"\n  ⚖️  ABSORPTION RATE: {absorption} months ({active} active / {monthly_sales:.0f} monthly sales)")

        # --- Turnover ---
        tr = gc["precomputed_market_charts"].find_one({"_id": f"{s}_turnover_rate"})
        if tr:
            timeline = tr.get("timeline", [])
            if timeline:
                latest_tr = timeline[-1]
                print(f"\n  🔄 TURNOVER: {latest_tr.get('turnover_rate', '?')}% ({latest_tr.get('year', '')})")

        # --- SQM Asking Prices ---
        sqm = gc["sqm_asking_prices"].find_one({"suburb": {"$regex": display, "$options": "i"}})
        if sqm:
            series = sqm.get("series", [])
            if series:
                latest_sqm = series[-1]
                print(f"\n  💰 ASKING PRICES (SQM {latest_sqm.get('date', '')}):")
                print(f"     Houses: ${latest_sqm.get('houses_all', 0):,.0f}")
                print(f"     Units:  ${latest_sqm.get('units_all', 0):,.0f}")
                print(f"     Gap:    ${(latest_sqm.get('houses_all', 0) - latest_sqm.get('units_all', 0)):,.0f}")

        # --- Market Signals ---
        signals_doc = sm["market_signals"].find_one({"_id": "market_signals_latest"})
        if signals_doc:
            suburb_signals = signals_doc.get("suburbs", {}).get(s, {})
            if suburb_signals:
                print(f"\n  📡 MARKET SIGNALS: Overall {suburb_signals.get('overallSentiment', '?')}")
                for sig in suburb_signals.get("signals", []):
                    emoji = {"BULLISH": "🟢", "NEUTRAL": "🟡", "BEARISH": "🔴"}.get(sig.get("signal", ""), "⚪")
                    print(f"     {emoji} {sig.get('displayName', '?')}: {sig.get('currentValue', '?')} ({sig.get('trend', '?')}) → {sig.get('signal', '?')}")

        # --- Price Events ---
        events = list(sm["price_change_events"].find(
            {"suburb": {"$regex": s.replace("_", " "), "$options": "i"}},
            {"direction": 1, "change_pct": 1, "_id": 0}
        ).limit(50))
        reductions = len([e for e in events if e.get("direction") == "reduction"])
        print(f"\n  📉 PRICE ADJUSTMENTS: {reductions} reductions out of {len(events)} events")

        # --- Capital gain comparison ---
        print(f"\n  🏆 CAPITAL GAIN COMPARISON (indexed):")
        for cs in TARGET_SUBURBS:
            cs_idx = gc["precomputed_indexed_prices"].find_one({"_id": cs})
            if cs_idx:
                cs_series = cs_idx.get("indexed_series", [])
                if cs_series:
                    print(f"     {DISPLAY_NAMES.get(cs, cs)}: index={cs_series[-1].get('index_value', '?')}, median=${cs_series[-1].get('median_price', 0):,.0f}")

    client.close()


def show_current():
    """Show current summaries for all suburbs and categories."""
    client = get_db()
    db = client["system_monitor"]

    for doc in db["market_pulse"].find({}, {"data_snapshot": 0}).sort([("suburb", 1), ("category", 1)]):
        source = doc.get("source", "auto")
        gen = doc.get("generated_at", "")
        if isinstance(gen, datetime):
            gen = gen.strftime("%Y-%m-%d")
        print(f"\n{'─'*60}")
        print(f"{doc.get('suburb_display', '?')} | {doc.get('category_title', '?')} | [{source}] | {gen}")
        print(f"Verdict: {doc.get('verdict', '?')}")
        print(f"{doc.get('summary', '')}")

    client.close()


def check_monthly_status():
    """Check if manual updates exist for the current month."""
    client = get_db()
    db = client["system_monitor"]

    month_start = datetime.now().replace(day=1, hour=0, minute=0, second=0, microsecond=0)
    print(f"Checking for updates since {month_start.strftime('%Y-%m-%d')}...\n")

    for suburb in TARGET_SUBURBS:
        display = DISPLAY_NAMES.get(suburb, suburb)
        manual_count = 0
        auto_count = 0
        missing = []

        for cat_id, cat_title in CATEGORIES.items():
            doc = db["market_pulse"].find_one({"suburb": suburb, "category": cat_id})
            if not doc:
                missing.append(cat_id)
                continue

            gen = doc.get("generated_at")
            if isinstance(gen, datetime) and gen >= month_start:
                if doc.get("source") == "manual":
                    manual_count += 1
                else:
                    auto_count += 1
            else:
                missing.append(cat_id)

        total = len(CATEGORIES)
        done = manual_count + auto_count
        print(f"{display}: {done}/{total} updated this month ({manual_count} manual, {auto_count} auto)")
        if missing:
            print(f"  Missing: {', '.join(missing)}")

    client.close()


def write_summary(suburb, category, verdict, summary, key_signals=None):
    """Write a manual summary to MongoDB."""
    client = get_db()
    db = client["system_monitor"]

    if category not in CATEGORIES:
        print(f"ERROR: Unknown category '{category}'. Valid: {list(CATEGORIES.keys())}")
        sys.exit(1)

    if verdict not in VERDICTS.get(category, []):
        print(f"ERROR: Invalid verdict '{verdict}' for {category}.")
        print(f"  Valid: {VERDICTS[category]}")
        sys.exit(1)

    doc = {
        "suburb": suburb,
        "suburb_display": DISPLAY_NAMES.get(suburb, suburb),
        "category": category,
        "category_title": CATEGORIES[category],
        "summary": summary,
        "verdict": verdict,
        "key_signals": key_signals or [],
        "source": "manual",
        "generated_at": datetime.now(),
        "model": "human+claude",
    }

    db["market_pulse"].update_one(
        {"suburb": suburb, "category": category},
        {"$set": doc},
        upsert=True,
    )

    print(f"✅ Written: {DISPLAY_NAMES.get(suburb, suburb)} / {CATEGORIES[category]}")
    print(f"   Verdict: {verdict}")
    print(f"   Summary: {summary[:100]}...")

    client.close()


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Manual market pulse update tool")
    parser.add_argument("--show-data", action="store_true", help="Show all current market data")
    parser.add_argument("--show-current", action="store_true", help="Show current pulse summaries")
    parser.add_argument("--check", action="store_true", help="Check monthly update status")
    parser.add_argument("--write", action="store_true", help="Write a manual summary")
    parser.add_argument("--suburb", type=str, help="Suburb key (e.g. robina)")
    parser.add_argument("--category", type=str, help="Category ID (e.g. sell-now)")
    parser.add_argument("--verdict", type=str, help="Verdict string")
    parser.add_argument("--summary", type=str, help="Summary text")
    parser.add_argument("--signals", type=str, help="Key signals as JSON array")
    args = parser.parse_args()

    if args.show_data:
        show_data(suburb=args.suburb, category=args.category)
    elif args.show_current:
        show_current()
    elif args.check:
        check_monthly_status()
    elif args.write:
        if not all([args.suburb, args.category, args.verdict, args.summary]):
            print("ERROR: --write requires --suburb, --category, --verdict, and --summary")
            sys.exit(1)
        signals = json.loads(args.signals) if args.signals else []
        write_summary(args.suburb, args.category, args.verdict, args.summary, signals)
    else:
        parser.print_help()
