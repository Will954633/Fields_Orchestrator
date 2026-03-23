#!/usr/bin/env python3
"""
fetch_macro_indicators.py — Fetch macro indicators for crash-risk charts.

Data sources (all free, no auth):
  - Brent crude oil (FRED DCOILBRENTEU) — daily, resampled to quarterly
  - RBA cash rate (RBA F1 table) — daily, resampled to quarterly
  - RBA mortgage rates (RBA F5 table) — monthly
  - Australian national house price index (FRED QAUN628BIS) — quarterly

Writes to: Gold_Coast.precomputed_macro_indicators

Usage:
    python3 scripts/fetch_macro_indicators.py          # fetch + write
    python3 scripts/fetch_macro_indicators.py --dry-run # fetch + print
"""

import argparse
import csv
import io
import json
import os
import sys
from datetime import datetime, timezone
from collections import defaultdict

import requests
import yaml
from pymongo import MongoClient


def fetch_csv(url: str) -> str:
    """Fetch CSV content from a URL."""
    resp = requests.get(url, timeout=30)
    resp.raise_for_status()
    return resp.text


def fetch_brent_crude() -> list[dict]:
    """Fetch Brent crude oil quarterly averages from FRED."""
    print("  Fetching Brent crude oil (FRED)...")
    csv_text = fetch_csv(
        "https://fred.stlouisfed.org/graph/fredgraph.csv?id=DCOILBRENTEU&cosd=2015-01-01"
    )

    # Parse daily data and aggregate to quarterly
    quarters = defaultdict(list)
    reader = csv.DictReader(io.StringIO(csv_text))
    for row in reader:
        date_str = row.get("DATE", row.get("observation_date", ""))
        value_str = row.get("DCOILBRENTEU", row.get("VALUE", ""))
        if not date_str or not value_str or value_str == ".":
            continue
        try:
            dt = datetime.strptime(date_str, "%Y-%m-%d")
            q = (dt.month - 1) // 3 + 1
            q_key = f"{dt.year}-Q{q}"
            quarters[q_key].append(float(value_str))
        except (ValueError, KeyError):
            continue

    result = []
    for q_key in sorted(quarters.keys()):
        values = quarters[q_key]
        result.append({
            "period": q_key,
            "avg_price_usd": round(sum(values) / len(values), 2),
            "max_price_usd": round(max(values), 2),
            "min_price_usd": round(min(values), 2),
            "data_points": len(values),
        })

    print(f"    {len(result)} quarters, latest: {result[-1]['period']} = ${result[-1]['avg_price_usd']}")
    return result


def fetch_rba_cash_rate() -> list[dict]:
    """Fetch RBA cash rate from F1 table."""
    print("  Fetching RBA cash rate (F1)...")
    csv_text = fetch_csv("https://www.rba.gov.au/statistics/tables/csv/f1-data.csv")

    # Skip metadata rows (first ~10 lines before actual data)
    lines = csv_text.strip().split("\n")
    data_start = 0
    for i, line in enumerate(lines):
        if line.startswith("Series ID") or line.startswith("series_id"):
            data_start = i + 1
            break
        # Look for date pattern
        parts = line.split(",")
        if parts and len(parts[0]) > 8:
            try:
                datetime.strptime(parts[0].strip(), "%d-%b-%Y")
                data_start = i
                break
            except ValueError:
                continue

    # Parse daily rates, take last value per quarter
    quarters = {}
    for line in lines[data_start:]:
        parts = [p.strip() for p in line.split(",")]
        if len(parts) < 2 or not parts[0]:
            continue
        try:
            dt = datetime.strptime(parts[0], "%d-%b-%Y")
            rate = float(parts[1]) if parts[1] else None
            if rate is not None:
                q = (dt.month - 1) // 3 + 1
                q_key = f"{dt.year}-Q{q}"
                quarters[q_key] = {"period": q_key, "rate": rate, "date": parts[0]}
        except (ValueError, IndexError):
            continue

    result = sorted(quarters.values(), key=lambda x: x["period"])
    # Filter to 2015+
    result = [r for r in result if r["period"] >= "2015-Q1"]

    # Cross-check: scrape the RBA cash rate page for the authoritative current rate
    # The F1 CSV can lag by days after a rate decision
    try:
        print("    Cross-checking against RBA cash rate page...")
        page = requests.get("https://www.rba.gov.au/statistics/cash-rate/", timeout=15)
        import re
        # The RBA page lists rate decisions in order — first rate after "0.25" change entries
        # is the current rate. Extract all X.XX numbers, skip 2.30 (time) and 0.25/0.00 (changes)
        all_rates = re.findall(r'(\d\.\d{2})', page.text)
        # Filter to plausible cash rates (1.00-15.00) excluding common non-rates
        plausible = [float(r) for r in all_rates if 1.0 <= float(r) <= 15.0 and float(r) not in (2.30,)]
        # The current rate is the first plausible rate that isn't a change amount (0.25, 0.50)
        candidates = [r for r in plausible if r not in (0.25, 0.50, 0.75, 1.00)]
        live_rate = candidates[0] if candidates else None
        if live_rate is not None:
            csv_rate = result[-1]['rate'] if result else None
            if csv_rate is not None and abs(live_rate - csv_rate) > 0.01:
                print(f"    ⚠️  CSV says {csv_rate}% but RBA page says {live_rate}% — using RBA page")
                result[-1]['rate'] = live_rate
            else:
                print(f"    ✅ Confirmed: {live_rate}%")
    except Exception as e:
        print(f"    Cross-check failed (non-fatal): {e}")

    if result:
        print(f"    {len(result)} quarters, latest: {result[-1]['period']} = {result[-1]['rate']}%")
    return result


def fetch_rba_mortgage_rates() -> list[dict]:
    """Fetch standard variable mortgage rate from RBA F5 table."""
    print("  Fetching RBA mortgage rates (F5)...")
    csv_text = fetch_csv("https://www.rba.gov.au/statistics/tables/csv/f5-data.csv")

    lines = csv_text.strip().split("\n")

    # Find data start — look for Series ID row, data starts after
    data_start = 0
    for i, line in enumerate(lines):
        if line.startswith("Series ID"):
            data_start = i + 1
            break

    # Column 3 (0-indexed) = "Housing loans; Banks; Variable; Standard; Owner-occupier"
    # Date format: DD/MM/YYYY
    quarters = {}
    for line in lines[data_start:]:
        parts = [p.strip() for p in line.split(",")]
        if len(parts) < 4 or not parts[0]:
            continue
        try:
            dt = datetime.strptime(parts[0], "%d/%m/%Y")
            rate_str = parts[3]  # Standard variable owner-occupier
            if not rate_str:
                continue
            rate = float(rate_str)
            if rate > 0:
                q = (dt.month - 1) // 3 + 1
                q_key = f"{dt.year}-Q{q}"
                quarters[q_key] = {"period": q_key, "rate": rate}
        except (ValueError, IndexError):
            continue

    result = sorted(quarters.values(), key=lambda x: x["period"])
    result = [r for r in result if r["period"] >= "2015-Q1"]

    if result:
        print(f"    {len(result)} quarters, latest: {result[-1]['period']} = {result[-1]['rate']}%")
    return result


def fetch_national_house_prices() -> list[dict]:
    """Fetch Australian national house price index from FRED (BIS series)."""
    print("  Fetching national house price index (FRED/BIS)...")
    csv_text = fetch_csv(
        "https://fred.stlouisfed.org/graph/fredgraph.csv?id=QAUN628BIS&cosd=2015-01-01"
    )

    result = []
    reader = csv.DictReader(io.StringIO(csv_text))
    for row in reader:
        date_str = row.get("DATE", row.get("observation_date", ""))
        value_str = row.get("QAUN628BIS", row.get("VALUE", ""))
        if not date_str or not value_str or value_str == ".":
            continue
        try:
            dt = datetime.strptime(date_str, "%Y-%m-%d")
            q = (dt.month - 1) // 3 + 1
            result.append({
                "period": f"{dt.year}-Q{q}",
                "index_value": float(value_str),
            })
        except ValueError:
            continue

    result.sort(key=lambda x: x["period"])

    if result:
        print(f"    {len(result)} quarters, latest: {result[-1]['period']} = {result[-1]['index_value']}")
    return result


def compute_mortgage_repayment(principal: float, annual_rate: float, years: int = 30) -> float:
    """Calculate monthly mortgage repayment (P&I)."""
    monthly_rate = annual_rate / 100 / 12
    n_payments = years * 12
    if monthly_rate == 0:
        return principal / n_payments
    return principal * (monthly_rate * (1 + monthly_rate)**n_payments) / ((1 + monthly_rate)**n_payments - 1)


def build_mortgage_impact(cash_rate_history: list, mortgage_rate_history: list) -> list[dict]:
    """Build mortgage repayment impact data for typical Gold Coast properties."""
    print("  Computing mortgage impact scenarios...")

    # Typical loan amounts for Gold Coast (80% LVR)
    scenarios = [
        {"label": "Robina median", "property_price": 1_495_000, "loan": 1_196_000},
        {"label": "Burleigh Waters median", "property_price": 2_160_000, "loan": 1_728_000},
        {"label": "Varsity Lakes median", "property_price": 1_400_000, "loan": 1_120_000},
        {"label": "$800K entry", "property_price": 800_000, "loan": 640_000},
    ]

    result = []
    for entry in mortgage_rate_history[-12:]:  # Last 12 quarters
        period_data = {"period": entry["period"], "mortgage_rate": entry["rate"]}
        for scenario in scenarios:
            monthly = compute_mortgage_repayment(scenario["loan"], entry["rate"])
            period_data[f"monthly_{scenario['label'].lower().replace(' ', '_')}"] = round(monthly, 0)
        result.append(period_data)

    # Compute impact vs 12 months ago AND vs cycle low (min rate in dataset)
    if len(mortgage_rate_history) >= 5:
        current_rate = mortgage_rate_history[-1]["rate"]
        year_ago_rate = mortgage_rate_history[-5]["rate"]
        cycle_low = min(mortgage_rate_history, key=lambda x: x["rate"])
        cycle_low_rate = cycle_low["rate"]
        cycle_low_period = cycle_low["period"]

        impact = []
        for scenario in scenarios:
            current_monthly = compute_mortgage_repayment(scenario["loan"], current_rate)
            year_ago_monthly = compute_mortgage_repayment(scenario["loan"], year_ago_rate)
            cycle_low_monthly = compute_mortgage_repayment(scenario["loan"], cycle_low_rate)
            impact.append({
                "label": scenario["label"],
                "property_price": scenario["property_price"],
                "loan": scenario["loan"],
                "current_rate": current_rate,
                "year_ago_rate": year_ago_rate,
                "cycle_low_rate": cycle_low_rate,
                "cycle_low_period": cycle_low_period,
                "current_monthly": round(current_monthly, 0),
                "year_ago_monthly": round(year_ago_monthly, 0),
                "cycle_low_monthly": round(cycle_low_monthly, 0),
                "vs_year_ago": round(current_monthly - year_ago_monthly, 0),
                "vs_cycle_low": round(current_monthly - cycle_low_monthly, 0),
                "vs_cycle_low_annual": round((current_monthly - cycle_low_monthly) * 12, 0),
            })

        print(f"    Current rate: {current_rate}% | Year ago: {year_ago_rate}% | Cycle low: {cycle_low_rate}% ({cycle_low_period})")
        for i in impact:
            print(f"      {i['label']}: ${i['current_monthly']:,.0f}/month (+${i['vs_cycle_low']:,.0f} vs cycle low)")

        return {"timeline": result, "impact_summary": impact}

    return {"timeline": result, "impact_summary": []}


def main():
    parser = argparse.ArgumentParser(description="Fetch macro indicators for crash-risk charts")
    parser.add_argument("--dry-run", action="store_true", help="Fetch and print without writing")
    args = parser.parse_args()

    print("Fetching macro indicators...\n")

    oil = fetch_brent_crude()
    cash_rate = fetch_rba_cash_rate()
    mortgage_rate = fetch_rba_mortgage_rates()
    national_prices = fetch_national_house_prices()
    mortgage_impact = build_mortgage_impact(cash_rate, mortgage_rate)

    doc = {
        "_id": "macro_indicators",
        "updated_at": datetime.now(timezone.utc),
        "brent_crude_quarterly": oil,
        "rba_cash_rate_quarterly": cash_rate,
        "rba_mortgage_rate_quarterly": mortgage_rate,
        "national_house_price_index": national_prices,
        "mortgage_impact": mortgage_impact,
    }

    if args.dry_run:
        print("\n=== DRY RUN ===")
        print(f"Oil: {len(oil)} quarters")
        print(f"Cash rate: {len(cash_rate)} quarters")
        print(f"Mortgage rate: {len(mortgage_rate)} quarters")
        print(f"National prices: {len(national_prices)} quarters")
        print(f"\nMortgage impact summary:")
        for i in mortgage_impact.get("impact_summary", []):
            print(f"  {i['label']}: ${i['current_monthly']:,.0f}/month at {i['current_rate']}% (was ${i['year_ago_monthly']:,.0f} at {i['year_ago_rate']}%)")
        return

    # Write to MongoDB
    print("\nWriting to MongoDB (Gold_Coast.precomputed_macro_indicators)...")
    conn_str = os.environ.get("COSMOS_CONNECTION_STRING")
    if not conn_str:
        cfg_path = os.path.join(os.path.dirname(__file__), "..", "config", "settings.yaml")
        with open(cfg_path) as f:
            cfg = yaml.safe_load(f)
        conn_str = cfg["mongodb"]["uri"]

    client = MongoClient(conn_str)
    db = client["Gold_Coast"]
    db["precomputed_macro_indicators"].replace_one(
        {"_id": "macro_indicators"}, doc, upsert=True
    )
    print("  Written successfully.")
    client.close()


if __name__ == "__main__":
    main()
