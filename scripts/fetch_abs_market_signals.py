#!/usr/bin/env python3
"""
Fetch market signals (economic indicators) from ABS API and write to MongoDB.

Data sources (all free, no API key required):
  - Wage Price Index (QLD): ABS WPI dataflow
  - Retail Turnover (QLD): ABS RT dataflow
  - Housing Lending (QLD): ABS LEND_HOUSING dataflow

Writes to: system_monitor.market_signals

Schedule: Weekly cron (ABS publishes quarterly, but weekly ensures we catch
new releases promptly and keeps the "last updated" timestamp fresh).

Usage:
  python3 scripts/fetch_abs_market_signals.py          # fetch + write to MongoDB
  python3 scripts/fetch_abs_market_signals.py --dry-run # fetch + print, don't write
"""

import argparse
import json
import os
import sys
from datetime import datetime, timezone

import requests
import yaml
from pymongo import MongoClient

ABS_BASE = "https://api.data.abs.gov.au/data"

# --- ABS API query definitions ---

INDICATORS = {
    "wage_price_index": {
        "displayName": "Wage Growth (QLD)",
        "dataflow": "WPI",
        # MEASURE=3 (YoY%), INDEX=THRPEB, SECTOR=7 (Priv+Pub), INDUSTRY=TOT, TSEST=10 (Orig), REGION=3 (QLD), FREQ=Q
        "key": "3.THRPEB.7.TOT.10.3.Q",
        "frequency": "quarterly",
        "unit": "%",
        "format_fn": "percent",
        "description_templates": {
            "UP": "Rising wages support buyer purchasing power",
            "DOWN": "Slowing wage growth may reduce purchasing power",
            "STABLE": "Steady wage growth maintains purchasing power",
        },
        "suburb_descriptions": {
            "robina": {"UP": "Rising wages support buyer purchasing power", "DOWN": "Slowing wage growth may reduce purchasing power", "STABLE": "Steady wage growth maintains purchasing power"},
            "burleigh_waters": {"UP": "Rising wages support premium property demand", "DOWN": "Slowing wage growth may cool premium demand", "STABLE": "Steady wage growth maintains demand"},
            "varsity_lakes": {"UP": "Rising incomes support university precinct demand", "DOWN": "Slowing wage growth may reduce buyer capacity", "STABLE": "Steady incomes maintain local demand"},
            "worongary": {"UP": "Strong wage growth supports acreage market", "DOWN": "Slowing wages may reduce lifestyle property demand", "STABLE": "Steady wages maintain acreage demand"},
            "mudgeeraba": {"UP": "Wage growth supports family market", "DOWN": "Slowing wages may reduce family buyer demand", "STABLE": "Steady wages maintain family market"},
            "reedy_creek": {"UP": "Wage growth supports hinterland market", "DOWN": "Slowing wages may reduce hinterland demand", "STABLE": "Steady wages maintain hinterland demand"},
            "merrimac": {"UP": "Rising wages support family market demand", "DOWN": "Slowing wages may reduce buyer activity", "STABLE": "Steady wages maintain market activity"},
            "carrara": {"UP": "Wage growth supports affordable market segment", "DOWN": "Slowing wages may reduce buyer capacity", "STABLE": "Steady wages maintain entry-level demand"},
        },
    },
    "retail_turnover": {
        "displayName": "Consumer Spending",
        "dataflow": "RT",
        # MEASURE=M1 (Current $), INDUSTRY=20 (Total), TSEST=10 (Orig), REGION=3 (QLD), FREQ=M (Monthly)
        "key": "M1.20.10.3.M",
        "frequency": "monthly",
        "unit": "$M",
        "format_fn": "dollars_billions",
        "description_templates": {
            "UP": "Strong retail activity indicates economic confidence",
            "DOWN": "Declining spending signals economic caution",
            "STABLE": "Steady consumer spending maintains confidence",
        },
        "suburb_descriptions": {
            "robina": {"UP": "Strong retail activity indicates economic confidence", "DOWN": "Declining spending signals economic caution", "STABLE": "Steady spending maintains confidence"},
            "burleigh_waters": {"UP": "Strong consumer confidence in coastal markets", "DOWN": "Declining spending may signal cooling sentiment", "STABLE": "Steady consumer activity in coastal markets"},
            "varsity_lakes": {"UP": "Strong economic activity near Robina Town Centre", "DOWN": "Declining spending may signal reduced activity", "STABLE": "Steady economic activity near Robina Town Centre"},
            "worongary": {"UP": "Economic strength drives lifestyle property demand", "DOWN": "Reduced spending may cool lifestyle markets", "STABLE": "Steady economic activity supports demand"},
            "mudgeeraba": {"UP": "Strong consumer activity supports family market", "DOWN": "Reduced spending may dampen demand", "STABLE": "Steady consumer activity"},
            "reedy_creek": {"UP": "Strong consumer confidence", "DOWN": "Declining consumer confidence", "STABLE": "Moderate consumer activity"},
            "merrimac": {"UP": "Strong economic fundamentals", "DOWN": "Economic headwinds emerging", "STABLE": "Steady economic fundamentals"},
            "carrara": {"UP": "Strong consumer confidence", "DOWN": "Declining consumer confidence", "STABLE": "Steady consumer activity"},
        },
    },
    "lending_housing": {
        "displayName": "Housing Lending (QLD)",
        "dataflow": "LEND_HOUSING",
        # FIN_VAL.NEWCOMMITS.DV8368.TOTDWELL.TOT.DV5167 (Owner-occ).10 (Orig).3 (QLD).Q
        "key": "FIN_VAL.NEWCOMMITS.DV8368.TOTDWELL.TOT.DV5167.10.3.Q",
        "frequency": "quarterly",
        "unit": "$M",
        "format_fn": "dollars_billions",
        "description_templates": {
            "UP": "Growing lending supports market activity",
            "DOWN": "Tightening credit may slow market activity",
            "STABLE": "Stable lending maintains market conditions",
        },
        "suburb_descriptions": {
            "robina": {"UP": "Easier access to finance supports market activity", "DOWN": "Tightening credit may slow activity", "STABLE": "Stable lending conditions"},
            "burleigh_waters": {"UP": "Credit growth supports premium market segment", "DOWN": "Tightening credit may cool premium demand", "STABLE": "Stable credit conditions"},
            "varsity_lakes": {"UP": "Finance accessibility supports first home buyers", "DOWN": "Tightening credit may reduce first-time buyer access", "STABLE": "Stable finance accessibility"},
            "worongary": {"UP": "Finance availability supports higher price points", "DOWN": "Tightening credit may constrain lifestyle purchases", "STABLE": "Stable finance availability"},
            "mudgeeraba": {"UP": "Growing lending supports family market", "DOWN": "Tightening credit may reduce buyer pool", "STABLE": "Stable lending conditions"},
            "reedy_creek": {"UP": "Growing lending supports hinterland purchases", "DOWN": "Tightening credit may constrain demand", "STABLE": "Stable lending conditions"},
            "merrimac": {"UP": "Growing lending supports market demand", "DOWN": "Tightening credit may slow demand", "STABLE": "Stable lending maintains demand"},
            "carrara": {"UP": "Finance accessibility supports entry-level buyers", "DOWN": "Tightening credit may limit entry-level access", "STABLE": "Stable finance accessibility"},
        },
    },
}

SUBURBS = [
    "robina", "burleigh_waters", "varsity_lakes",
    "worongary", "mudgeeraba", "reedy_creek",
    "merrimac", "carrara",
]

SUBURB_DISPLAY = {
    "robina": "Robina",
    "burleigh_waters": "Burleigh Waters",
    "varsity_lakes": "Varsity Lakes",
    "worongary": "Worongary",
    "mudgeeraba": "Mudgeeraba",
    "reedy_creek": "Reedy Creek",
    "merrimac": "Merrimac",
    "carrara": "Carrara",
}


def fetch_abs_data(dataflow: str, key: str, start_period: str = "2022-Q1") -> dict:
    """Fetch data from ABS SDMX JSON API (v2 format)."""
    url = f"{ABS_BASE}/{dataflow}/{key}"
    params = {"startPeriod": start_period, "format": "jsondata"}
    resp = requests.get(url, params=params, timeout=30)
    resp.raise_for_status()
    return resp.json()


def parse_abs_timeseries(raw: dict) -> list[dict]:
    """Parse ABS SDMX JSON v2 into list of {period, value}."""
    ds = raw["data"]["dataSets"][0]
    series = list(ds["series"].values())[0]
    obs = series["observations"]
    periods = raw["data"]["structures"][0]["dimensions"]["observation"][0]["values"]

    results = []
    for i, p in enumerate(periods):
        val = obs.get(str(i), [None])[0]
        if val is not None:
            results.append({"period": p["id"], "value": val})

    # Sort by period
    results.sort(key=lambda x: x["period"])
    return results


def format_value(value: float, format_fn: str) -> str:
    """Format a numeric value for display."""
    if format_fn == "percent":
        return f"{value}%"
    elif format_fn == "dollars_billions":
        billions = value / 1000.0
        return f"${billions:.1f}B"
    return str(value)


def determine_trend(current: float, previous: float) -> str:
    """Determine trend direction based on percentage change between periods."""
    if current is None or previous is None:
        return "STABLE"
    pct_change = ((current - previous) / abs(previous)) * 100 if previous != 0 else 0
    if pct_change > 2.0:
        return "UP"
    elif pct_change < -2.0:
        return "DOWN"
    return "STABLE"


def determine_signal(trend: str, indicator: str, current_raw: float) -> str:
    """Determine signal strength based on trend, indicator type, and absolute level.

    Wage growth: >3% is bullish regardless of trend direction (still positive growth).
    Lending: absolute level matters more than direction.
    Retail: direction matters most.
    """
    if indicator == "wage_price_index":
        # Wage growth above 3% is still supportive even if decelerating
        if current_raw is not None and current_raw >= 3.0:
            return "BULLISH" if trend != "DOWN" else "NEUTRAL"
        elif current_raw is not None and current_raw < 2.0:
            return "BEARISH"
        return "NEUTRAL" if trend == "DOWN" else "BULLISH"

    # For lending and retail: direction-based
    if trend == "UP":
        return "BULLISH"
    elif trend == "DOWN":
        return "BEARISH"
    return "NEUTRAL"


def quarter_label(period: str) -> str:
    """Convert period to human-readable quarter label. e.g. '2025-Q4' -> 'Q4 2025'"""
    if "-Q" in period:
        parts = period.split("-Q")
        return f"Q{parts[1]} {parts[0]}"
    # Monthly: '2025-06' -> 'Jun 2025'
    try:
        dt = datetime.strptime(period, "%Y-%m")
        return dt.strftime("%b %Y")
    except ValueError:
        return period


def get_latest_quarter_from_monthly(timeseries: list[dict]) -> tuple[float, float, str]:
    """For monthly data, aggregate to latest complete quarter and previous quarter."""
    if not timeseries:
        return None, None, ""

    # Group by quarter
    quarters = {}
    for entry in timeseries:
        period = entry["period"]  # e.g. "2025-06"
        try:
            dt = datetime.strptime(period, "%Y-%m")
            q = (dt.month - 1) // 3 + 1
            q_key = f"{dt.year}-Q{q}"
        except ValueError:
            continue
        if q_key not in quarters:
            quarters[q_key] = []
        quarters[q_key].append(entry["value"])

    # Only use complete quarters (3 months)
    complete = {k: sum(v) for k, v in quarters.items() if len(v) == 3}
    if not complete:
        # Fall back to any quarter with data
        complete = {k: sum(v) for k, v in quarters.items()}

    sorted_q = sorted(complete.keys())
    if len(sorted_q) >= 2:
        return complete[sorted_q[-1]], complete[sorted_q[-2]], sorted_q[-1]
    elif len(sorted_q) == 1:
        return complete[sorted_q[0]], None, sorted_q[0]
    return None, None, ""


def aggregate_monthly_to_quarterly(timeseries: list[dict]) -> list[dict]:
    """Convert monthly timeseries to quarterly totals for chart display."""
    quarters = {}
    for entry in timeseries:
        period = entry["period"]
        try:
            dt = datetime.strptime(period, "%Y-%m")
            q = (dt.month - 1) // 3 + 1
            q_key = f"{dt.year}-Q{q}"
        except ValueError:
            continue
        if q_key not in quarters:
            quarters[q_key] = []
        quarters[q_key].append(entry["value"])

    # Only include complete quarters (3 months)
    result = []
    for q_key in sorted(quarters.keys()):
        if len(quarters[q_key]) == 3:
            result.append({"period": q_key, "value": round(sum(quarters[q_key]), 1)})
    return result


def build_market_signals(dry_run: bool = False):
    """Fetch all ABS data and build market signals documents."""

    print("Fetching ABS data...")
    indicator_data = {}

    for ind_key, ind_cfg in INDICATORS.items():
        try:
            print(f"  Fetching {ind_cfg['displayName']}...")
            raw = fetch_abs_data(ind_cfg["dataflow"], ind_cfg["key"])
            timeseries = parse_abs_timeseries(raw)

            if ind_cfg["frequency"] == "monthly":
                current_val, prev_val, latest_period = get_latest_quarter_from_monthly(timeseries)
            else:
                # Quarterly: take last two entries
                if len(timeseries) >= 2:
                    current_val = timeseries[-1]["value"]
                    prev_val = timeseries[-2]["value"]
                    latest_period = timeseries[-1]["period"]
                elif len(timeseries) == 1:
                    current_val = timeseries[0]["value"]
                    prev_val = None
                    latest_period = timeseries[0]["period"]
                else:
                    current_val, prev_val, latest_period = None, None, ""

            trend = determine_trend(current_val, prev_val)
            signal = determine_signal(trend, ind_key, current_val)

            # For monthly data, aggregate timeseries to quarterly for charts
            if ind_cfg["frequency"] == "monthly":
                chart_ts = aggregate_monthly_to_quarterly(timeseries)
            else:
                chart_ts = timeseries

            indicator_data[ind_key] = {
                "currentValue": format_value(current_val, ind_cfg["format_fn"]) if current_val else "N/A",
                "previousValue": format_value(prev_val, ind_cfg["format_fn"]) if prev_val else "N/A",
                "currentRaw": current_val,
                "previousRaw": prev_val,
                "trend": trend,
                "signal": signal,
                "latestPeriod": latest_period,
                "latestPeriodLabel": quarter_label(latest_period),
                "timeseries": chart_ts[-12:],  # Keep last 12 quarters for trend chart
            }

            print(f"    Latest: {latest_period} = {format_value(current_val, ind_cfg['format_fn']) if current_val else 'N/A'}")
            print(f"    Previous: {format_value(prev_val, ind_cfg['format_fn']) if prev_val else 'N/A'}")
            print(f"    Trend: {trend} -> {signal}")

        except Exception as e:
            print(f"    ERROR fetching {ind_key}: {e}", file=sys.stderr)
            indicator_data[ind_key] = {
                "currentValue": "N/A",
                "previousValue": "N/A",
                "currentRaw": None,
                "previousRaw": None,
                "trend": "STABLE",
                "signal": "NEUTRAL",
                "latestPeriod": "",
                "latestPeriodLabel": "",
                "timeseries": [],
            }

    # Determine the latest quarter across all indicators
    all_periods = [d["latestPeriod"] for d in indicator_data.values() if d["latestPeriod"]]
    latest_quarter = max(all_periods) if all_periods else "Unknown"
    latest_quarter_label = quarter_label(latest_quarter)

    # Build per-suburb documents
    now = datetime.now(timezone.utc)
    suburb_docs = {}

    for suburb in SUBURBS:
        signals = []
        for ind_key, ind_cfg in INDICATORS.items():
            data = indicator_data[ind_key]
            trend = data["trend"]

            # Get suburb-specific description
            suburb_descs = ind_cfg.get("suburb_descriptions", {}).get(suburb, ind_cfg["description_templates"])
            description = suburb_descs.get(trend, ind_cfg["description_templates"].get(trend, ""))

            signals.append({
                "indicator": ind_key,
                "displayName": ind_cfg["displayName"],
                "currentValue": data["currentValue"],
                "previousValue": data["previousValue"],
                "trend": trend,
                "signal": data["signal"],
                "description": description,
                "lastUpdated": latest_quarter_label,
            })

        # Overall sentiment: majority vote
        bullish_count = sum(1 for s in signals if s["signal"] == "BULLISH")
        bearish_count = sum(1 for s in signals if s["signal"] == "BEARISH")
        if bullish_count > len(signals) / 2:
            overall = "BULLISH"
        elif bearish_count > len(signals) / 2:
            overall = "BEARISH"
        else:
            overall = "NEUTRAL"

        suburb_docs[suburb] = {
            "suburb": suburb,
            "displayName": SUBURB_DISPLAY[suburb],
            "overallSentiment": overall,
            "lastUpdated": latest_quarter_label,
            "signals": signals,
        }

    # Build the unified document for MongoDB
    doc = {
        "_id": "market_signals_latest",
        "updated_at": now,
        "latest_quarter": latest_quarter,
        "latest_quarter_label": latest_quarter_label,
        "raw_indicators": {k: {
            "currentValue": v["currentValue"],
            "previousValue": v["previousValue"],
            "currentRaw": v["currentRaw"],
            "previousRaw": v["previousRaw"],
            "trend": v["trend"],
            "signal": v["signal"],
            "latestPeriod": v["latestPeriod"],
            "latestPeriodLabel": v["latestPeriodLabel"],
            "timeseries": v["timeseries"],
        } for k, v in indicator_data.items()},
        "suburbs": suburb_docs,
    }

    if dry_run:
        print("\n=== DRY RUN — would write to system_monitor.market_signals ===")
        print(json.dumps(doc, indent=2, default=str))
        return doc

    # Write to MongoDB
    print("\nWriting to MongoDB (system_monitor.market_signals)...")
    cfg_path = os.path.join(os.path.dirname(__file__), "..", "config", "settings.yaml")
    with open(cfg_path) as f:
        cfg = yaml.safe_load(f)

    client = MongoClient(cfg["mongodb"]["uri"])
    db = client["system_monitor"]
    coll = db["market_signals"]

    # Upsert the single document
    coll.replace_one({"_id": "market_signals_latest"}, doc, upsert=True)
    print(f"  Written. Latest quarter: {latest_quarter_label}")

    # Also write a historical snapshot (for trend tracking over time)
    history_doc = {
        "quarter": latest_quarter,
        "updated_at": now,
        "indicators": {k: {
            "currentRaw": v["currentRaw"],
            "previousRaw": v["previousRaw"],
            "trend": v["trend"],
            "signal": v["signal"],
        } for k, v in indicator_data.items()},
    }
    coll.update_one(
        {"quarter": latest_quarter},
        {"$set": history_doc},
        upsert=True,
    )
    print(f"  Historical snapshot for {latest_quarter} saved.")

    client.close()
    return doc


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Fetch ABS market signals and write to MongoDB")
    parser.add_argument("--dry-run", action="store_true", help="Fetch and print without writing to DB")
    args = parser.parse_args()

    build_market_signals(dry_run=args.dry_run)
