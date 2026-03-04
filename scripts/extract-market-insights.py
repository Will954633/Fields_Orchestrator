#!/usr/bin/env python3
"""
Market Intelligence Snapshot — extracts actionable insights from pre-computed
market data for the marketing advisor.

Queries: precomputed_market_charts, precomputed_indexed_prices,
         precomputed_active_listings, suburb_median_prices

Output: system_monitor.market_intelligence_snapshot

Usage:
    python3 scripts/extract-market-insights.py              # Extract and save
    python3 scripts/extract-market-insights.py --print       # Print insights only
"""

import os
import json
import argparse
from datetime import datetime, timezone
from dotenv import load_dotenv
from pymongo import MongoClient

load_dotenv("/home/fields/Fields_Orchestrator/.env")

COSMOS_URI = os.environ["COSMOS_CONNECTION_STRING"]

TARGET_SUBURBS = [
    "robina", "burleigh_waters", "varsity_lakes",
    "carrara", "worongary", "merrimac", "mudgeeraba", "reedy_creek",
]

DISPLAY_NAMES = {
    "robina": "Robina",
    "burleigh_waters": "Burleigh Waters",
    "varsity_lakes": "Varsity Lakes",
    "carrara": "Carrara",
    "worongary": "Worongary",
    "merrimac": "Merrimac",
    "mudgeeraba": "Mudgeeraba",
    "reedy_creek": "Reedy Creek",
}

# precomputed_market_charts uses Title Case suburb names
CHART_SUBURBS = {
    "robina": "Robina",
    "burleigh_waters": "Burleigh Waters",
    "varsity_lakes": "Varsity Lakes",
    "carrara": "Carrara",
    "worongary": "Worongary",
    "merrimac": "Merrimac",
    "mudgeeraba": "Mudgeeraba",
    "reedy_creek": "Reedy Creek",
}


def extract_dom_insights(gc_db):
    """Extract days-on-market trend insights."""
    insights = []
    for suburb in TARGET_SUBURBS:
        chart_suburb = CHART_SUBURBS.get(suburb, suburb)
        doc = gc_db["precomputed_market_charts"].find_one(
            {"suburb": chart_suburb, "chart_type": "days_on_market"}
        )
        if not doc:
            continue

        display = DISPLAY_NAMES.get(suburb, suburb)
        latest = doc.get("latest_quarter_median")
        historical = doc.get("historical_median")
        yoy = doc.get("yoy_change_days")

        if latest and historical:
            if latest < historical * 0.8:
                insights.append({
                    "type": "dom_fast",
                    "suburb": suburb,
                    "text": (f"{display} median days on market is {latest:.0f} days — "
                             f"well below the historical median of {historical:.0f}. "
                             f"Properties are selling faster than normal."),
                    "metric": "days_on_market",
                    "value": latest,
                    "audience": "seller",
                    "urgency": "high",
                })
            elif latest > historical * 1.3:
                insights.append({
                    "type": "dom_slow",
                    "suburb": suburb,
                    "text": (f"{display} DOM has risen to {latest:.0f} days "
                             f"(historical median: {historical:.0f}). "
                             f"Buyers have more time to evaluate."),
                    "metric": "days_on_market",
                    "value": latest,
                    "audience": "buyer",
                    "urgency": "medium",
                })
            else:
                insights.append({
                    "type": "dom_normal",
                    "suburb": suburb,
                    "text": (f"{display} median DOM is {latest:.0f} days "
                             f"(historical median: {historical:.0f}). Market pace is normal."),
                    "metric": "days_on_market",
                    "value": latest,
                    "audience": "both",
                    "urgency": "low",
                })

        if yoy is not None and abs(yoy) >= 5:
            direction = "faster" if yoy < 0 else "slower"
            insights.append({
                "type": "dom_yoy",
                "suburb": suburb,
                "text": (f"{display}: properties are selling {abs(yoy):.0f} days "
                         f"{direction} than the same quarter last year."),
                "metric": "days_on_market_yoy",
                "value": yoy,
                "audience": "both",
                "urgency": "medium" if abs(yoy) >= 10 else "low",
            })

    return insights


def extract_price_growth_insights(gc_db):
    """Extract price growth and capital appreciation insights."""
    insights = []
    for suburb in TARGET_SUBURBS:
        chart_suburb = CHART_SUBURBS.get(suburb, suburb)
        doc = gc_db["precomputed_indexed_prices"].find_one(
            {"suburb": chart_suburb}
        )
        if not doc:
            continue

        display = DISPLAY_NAMES.get(suburb, suburb)
        total_growth = doc.get("total_growth_pct")
        yoy_pct = doc.get("rolling_12m_yoy_pct")
        latest_price = doc.get("rolling_12m_median_price")
        baseline_period = doc.get("baseline_period", "baseline")

        if yoy_pct is not None and abs(yoy_pct) >= 3:
            direction = "up" if yoy_pct > 0 else "down"
            price_str = f"${latest_price:,.0f}" if latest_price else "N/A"
            insights.append({
                "type": "price_yoy",
                "suburb": suburb,
                "text": (f"{display} median house price is {direction} {abs(yoy_pct):.1f}% "
                         f"year-on-year (rolling 12-month median: {price_str})."),
                "metric": "price_growth_yoy",
                "value": yoy_pct,
                "audience": "investor" if yoy_pct > 0 else "buyer",
                "urgency": "high" if abs(yoy_pct) >= 8 else "medium",
            })

        if total_growth and total_growth > 50:
            insights.append({
                "type": "price_total_growth",
                "suburb": suburb,
                "text": (f"{display} has seen {total_growth:.0f}% total capital growth "
                         f"since {baseline_period}."),
                "metric": "total_growth",
                "value": total_growth,
                "audience": "investor",
                "urgency": "low",
            })

    return insights


def extract_supply_insights(gc_db):
    """Extract active listing supply change insights."""
    insights = []
    for suburb in TARGET_SUBURBS:
        chart_suburb = CHART_SUBURBS.get(suburb, suburb)
        doc = gc_db["precomputed_active_listings"].find_one(
            {"suburb": chart_suburb}
        )
        if not doc:
            continue

        display = DISPLAY_NAMES.get(suburb, suburb)
        snapshots = doc.get("snapshots", [])
        if len(snapshots) < 2:
            continue

        latest = snapshots[-1]
        previous = snapshots[-2]
        latest_count = latest.get("active_listings", 0)
        prev_count = previous.get("active_listings", 0)

        if prev_count == 0:
            continue

        pct_change = ((latest_count - prev_count) / prev_count) * 100

        if abs(pct_change) >= 10:
            direction = "increased" if pct_change > 0 else "decreased"
            insights.append({
                "type": "supply_change",
                "suburb": suburb,
                "text": (f"{display} active listings {direction} {abs(pct_change):.0f}% "
                         f"({prev_count} to {latest_count})."),
                "metric": "supply_mom",
                "value": pct_change,
                "current_count": latest_count,
                "audience": "buyer" if pct_change > 0 else "seller",
                "urgency": "high" if abs(pct_change) >= 20 else "medium",
            })
        else:
            insights.append({
                "type": "supply_stable",
                "suburb": suburb,
                "text": (f"{display} has {latest_count} active listings "
                         f"(stable, {pct_change:+.0f}% MoM)."),
                "metric": "supply_mom",
                "value": pct_change,
                "current_count": latest_count,
                "audience": "both",
                "urgency": "low",
            })

    return insights


def extract_market_cycle_insights(gc_db):
    """Extract market cycle score insights."""
    insights = []
    for suburb in TARGET_SUBURBS:
        chart_suburb = CHART_SUBURBS.get(suburb, suburb)
        doc = gc_db["precomputed_market_charts"].find_one(
            {"suburb": chart_suburb, "chart_type": "market_cycle"}
        )
        if not doc:
            continue

        display = DISPLAY_NAMES.get(suburb, suburb)
        score = doc.get("score")
        phase = doc.get("phase", "")

        if score is not None:
            if score >= 60:
                favour = "Favours sellers."
            elif score >= 40:
                favour = "Balanced market."
            else:
                favour = "Favours buyers."

            insights.append({
                "type": "market_cycle",
                "suburb": suburb,
                "text": f"{display} market cycle score: {score:.0f}/100 ({phase}). {favour}",
                "metric": "market_cycle_score",
                "value": score,
                "phase": phase,
                "audience": "both",
                "urgency": "medium" if score >= 70 or score <= 30 else "low",
            })

    return insights


def extract_sales_volume_insights(gc_db):
    """Extract sales volume trend insights."""
    insights = []
    for suburb in TARGET_SUBURBS:
        chart_suburb = CHART_SUBURBS.get(suburb, suburb)
        doc = gc_db["precomputed_market_charts"].find_one(
            {"suburb": chart_suburb, "chart_type": "sales_volume"}
        )
        if not doc:
            continue

        display = DISPLAY_NAMES.get(suburb, suburb)
        timeline = doc.get("timeline", [])
        if len(timeline) < 4:
            continue

        latest = timeline[-1]
        year_ago = timeline[-4] if len(timeline) >= 4 else None

        latest_count = latest.get("transaction_count", 0)
        if year_ago:
            old_count = year_ago.get("transaction_count", 0)
            if old_count > 0:
                pct_change = ((latest_count - old_count) / old_count) * 100
                if abs(pct_change) >= 20:
                    direction = "surged" if pct_change > 0 else "dropped"
                    insights.append({
                        "type": "volume_yoy",
                        "suburb": suburb,
                        "text": (f"{display} sales volume {direction} {abs(pct_change):.0f}% "
                                 f"year-on-year ({old_count} to {latest_count} transactions this quarter)."),
                        "metric": "sales_volume_yoy",
                        "value": pct_change,
                        "audience": "both",
                        "urgency": "high" if abs(pct_change) >= 40 else "medium",
                    })

    return insights


def main():
    parser = argparse.ArgumentParser(description="Extract market intelligence insights")
    parser.add_argument("--print", action="store_true", help="Print insights without saving")
    args = parser.parse_args()

    print(f"[{datetime.now(timezone.utc).isoformat()}] Market Intelligence Extractor starting...")

    client = MongoClient(COSMOS_URI)
    gc_db = client["Gold_Coast"]

    # Extract all insight types
    all_insights = []
    extractors = [
        ("Days on Market", extract_dom_insights),
        ("Price Growth", extract_price_growth_insights),
        ("Supply Changes", extract_supply_insights),
        ("Market Cycle", extract_market_cycle_insights),
        ("Sales Volume", extract_sales_volume_insights),
    ]

    for name, fn in extractors:
        insights = fn(gc_db)
        print(f"  {name}: {len(insights)} insights")
        all_insights.extend(insights)

    # Build summary
    high_urgency = len([i for i in all_insights if i.get("urgency") == "high"])
    by_suburb = {}
    by_audience = {}
    for i in all_insights:
        sub = i.get("suburb", "unknown")
        aud = i.get("audience", "unknown")
        by_suburb[sub] = by_suburb.get(sub, 0) + 1
        by_audience[aud] = by_audience.get(aud, 0) + 1

    snapshot = {
        "_id": "latest",
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "insights": all_insights,
        "summary": {
            "total_insights": len(all_insights),
            "high_urgency": high_urgency,
            "by_suburb": by_suburb,
            "by_audience": by_audience,
        },
    }

    print(f"\nTotal: {len(all_insights)} insights ({high_urgency} high-urgency)")

    if getattr(args, "print"):
        print("\n--- High urgency ---")
        for i in all_insights:
            if i.get("urgency") == "high":
                print(f"  [{i['suburb']}] {i['text']}")
        print("\n--- Medium urgency ---")
        for i in all_insights:
            if i.get("urgency") == "medium":
                print(f"  [{i['suburb']}] {i['text']}")
        print("\n--- Low urgency ---")
        for i in all_insights:
            if i.get("urgency") == "low":
                print(f"  [{i['suburb']}] {i['text']}")
        client.close()
        return

    # Save to MongoDB
    sm = client["system_monitor"]
    sm["market_intelligence_snapshot"].replace_one(
        {"_id": "latest"},
        snapshot,
        upsert=True,
    )
    client.close()

    print(f"Saved to system_monitor.market_intelligence_snapshot")


if __name__ == "__main__":
    main()
