#!/usr/bin/env python3
"""
fetch_macro_indicators.py — Fetch macro indicators for crash-risk charts.

Data sources (all free, no auth):
  - Brent crude oil (FRED DCOILBRENTEU) — daily, resampled to quarterly
  - RBA cash rate (RBA F1 table) — daily, resampled to quarterly
  - RBA mortgage rates (RBA F5 table) — monthly
  - RBA 1-year term deposit rate (RBA F4 table) — monthly, back to 1981
  - QLD CPI, all groups (ABS Data API, dataflow CPI) — quarterly, back to 1948
  - Australian national house price index (FRED QAUN628BIS) — quarterly

Writes to: Gold_Coast.precomputed_macro_indicators

Usage:
    python3 scripts/fetch_macro_indicators.py          # fetch + write
    python3 scripts/fetch_macro_indicators.py --dry-run # fetch + print
"""

import time
import argparse
import csv
import io
import json
import os
import sys
from datetime import datetime, timedelta, timezone
from collections import defaultdict

import requests
import yaml
from pymongo import MongoClient


def fetch_csv(url: str) -> str:
    """Fetch CSV content from a URL.

    Tries a direct request first; on failure falls back to the Bright Data Web
    Unlocker (some sources, e.g. FRED, IP-block this VM's GCP egress). Requires
    BRIGHTDATA_API_KEY for the fallback.
    """
    try:
        resp = requests.get(url, timeout=30)
        resp.raise_for_status()
        if resp.text and len(resp.text) > 50:
            return resp.text
    except Exception as direct_err:
        last_err = direct_err
    else:
        last_err = RuntimeError("empty response")

    api_key = os.environ.get("BRIGHTDATA_API_KEY")
    if api_key:
        zone = os.environ.get("BRIGHTDATA_ZONE", "web_unlocker2")
        # Web Unlocker is reliable but flaky/slow per request — retry a few times.
        for attempt in range(3):
            try:
                r = requests.post(
                    "https://api.brightdata.com/request",
                    headers={"Content-Type": "application/json", "Authorization": f"Bearer {api_key}"},
                    json={"zone": zone, "url": url, "format": "raw"},
                    timeout=150,
                )
                if r.status_code == 200 and r.text and len(r.text) > 50:
                    return r.text
                last_err = RuntimeError(f"Bright Data http={r.status_code} len={len(r.text or '')}")
            except Exception as e:
                last_err = e
            if attempt < 2:
                time.sleep(5)
        raise RuntimeError(f"Bright Data fallback failed after retries for {url}: {last_err}")
    raise RuntimeError(f"direct fetch failed ({last_err}) and no BRIGHTDATA_API_KEY for fallback: {url}")


def fetch_brent_crude() -> tuple[list[dict], list[dict]]:
    """Fetch Brent crude oil from FRED — daily + quarterly aggregates."""
    print("  Fetching Brent crude oil (FRED)...")
    csv_text = fetch_csv(
        "https://fred.stlouisfed.org/graph/fredgraph.csv?id=DCOILBRENTEU&cosd=2015-01-01"
    )

    daily = []
    quarters = defaultdict(list)
    reader = csv.DictReader(io.StringIO(csv_text))
    for row in reader:
        date_str = row.get("DATE", row.get("observation_date", ""))
        value_str = row.get("DCOILBRENTEU", row.get("VALUE", ""))
        if not date_str or not value_str or value_str == ".":
            continue
        try:
            price = float(value_str)
            dt = datetime.strptime(date_str, "%Y-%m-%d")
            q = (dt.month - 1) // 3 + 1
            q_key = f"{dt.year}-Q{q}"
            quarters[q_key].append(price)
            daily.append({"date": date_str, "price_usd": price})
        except (ValueError, KeyError):
            continue

    quarterly = []
    for q_key in sorted(quarters.keys()):
        values = quarters[q_key]
        quarterly.append({
            "period": q_key,
            "avg_price_usd": round(sum(values) / len(values), 2),
            "max_price_usd": round(max(values), 2),
            "min_price_usd": round(min(values), 2),
            "data_points": len(values),
        })

    # Keep last 2 years of daily data (enough for the chart without bloating the doc)
    two_years_ago = (datetime.now() - timedelta(days=730)).strftime("%Y-%m-%d")
    daily_recent = [d for d in daily if d["date"] >= two_years_ago]

    print(f"    {len(quarterly)} quarters, {len(daily_recent)} daily points")
    print(f"    Latest: {daily_recent[-1]['date']} = ${daily_recent[-1]['price_usd']}")
    return quarterly, daily_recent


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

    # No lower-bound filter — the RBA's daily F1 CSV itself only extends back to
    # ~2011 (a source limit, not a filter we impose), so this already captures
    # everything available.
    result = sorted(quarters.values(), key=lambda x: x["period"])

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


def fetch_rba_term_deposit_1y() -> list[dict]:
    """Fetch the RBA's 1-year term deposit rate ($10,000) from the F4 table.

    Feeds the off-market mini-site's capital-gain "vs. the bank" benchmark —
    real monthly data back to Dec-1981, long enough to cover any purchase date
    we'll ever see. Column position is verified against the Series ID row each
    run rather than hardcoded, so an RBA column reorder fails loudly instead of
    silently reading the wrong series.
    """
    print("  Fetching RBA 1-year term deposit rate (F4)...")
    csv_text = fetch_csv("https://www.rba.gov.au/statistics/tables/csv/f4-data.csv")
    lines = [l for l in csv_text.split("\n") if l.strip()]

    header_idx = next((i for i, l in enumerate(lines) if l.startswith("Series ID")), None)
    if header_idx is None:
        raise RuntimeError("F4 CSV: 'Series ID' row not found")
    header = [p.strip() for p in lines[header_idx].split(",")]
    try:
        col = header.index("FRDIRBTD10K1Y")
    except ValueError:
        raise RuntimeError("F4 CSV: 1-year term deposit series (FRDIRBTD10K1Y) not found in header")

    quarters = {}
    for line in lines[header_idx + 1:]:
        parts = [p.strip() for p in line.split(",")]
        if len(parts) <= col or not parts[0]:
            continue
        try:
            dt = datetime.strptime(parts[0], "%d/%m/%Y")
            rate_str = parts[col]
            if not rate_str:
                continue
            rate = float(rate_str)
            q = (dt.month - 1) // 3 + 1
            q_key = f"{dt.year}-Q{q}"
            quarters[q_key] = {"period": q_key, "rate": rate}  # last month in the quarter wins
        except (ValueError, IndexError):
            continue

    result = sorted(quarters.values(), key=lambda x: x["period"])
    if result:
        print(f"    {len(result)} quarters, {result[0]['period']}–{result[-1]['period']}, "
              f"latest: {result[-1]['rate']}%")
    return result


def fetch_cpi_qld() -> list[dict]:
    """Fetch the QLD All-Groups CPI index (quarterly) from the ABS Data API.

    Same dataflow + key already live in fetch_abs_market_signals.py
    (1=Index Number, 10001=All Groups, 10=Original, 3=QLD, Q=Quarterly) — reused
    here rather than duplicated with a different key, so both scripts stay
    trivially consistent. Real quarterly data back to 1948-Q3.
    """
    print("  Fetching ABS CPI (QLD, All Groups)...")
    resp = requests.get(
        "https://data.api.abs.gov.au/rest/data/CPI/1.10001.10.3.Q",
        params={"format": "jsondata"},
        timeout=30,
    )
    resp.raise_for_status()
    payload = resp.json()

    structures = payload.get("data", {}).get("structures") or []
    datasets = payload.get("data", {}).get("dataSets") or []
    if not structures or not datasets:
        raise RuntimeError("ABS CPI response missing structures/dataSets")

    obs_dim = structures[0]["dimensions"]["observation"][0]["values"]
    series = datasets[0]["series"]
    series_key = next(iter(series))
    observations = series[series_key]["observations"]

    pairs = []
    for idx_str, arr in observations.items():
        idx = int(idx_str)
        if idx >= len(obs_dim) or not arr or arr[0] is None:
            continue
        pairs.append({"period": obs_dim[idx]["id"], "index": float(arr[0])})
    pairs.sort(key=lambda p: p["period"])

    if pairs:
        print(f"    {len(pairs)} quarters, {pairs[0]['period']}–{pairs[-1]['period']}, "
              f"latest index: {pairs[-1]['index']}")
    return pairs


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

    # Connect first so we can preserve previous values for any source that fails
    # (one IP-blocked source must not wipe the rest, or fields written by other
    # scripts such as national_asking_prices).
    conn_str = os.environ.get("COSMOS_CONNECTION_STRING")
    if not conn_str:
        cfg_path = os.path.join(os.path.dirname(__file__), "..", "config", "settings.yaml")
        with open(cfg_path) as f:
            cfg = yaml.safe_load(f)
        conn_str = cfg["mongodb"]["uri"]
    client = MongoClient(conn_str)
    db = client["Gold_Coast"]
    prev = db["precomputed_macro_indicators"].find_one({"_id": "macro_indicators"}) or {}

    failed = []

    def _try(label, fn):
        try:
            return fn()
        except Exception as e:
            failed.append(label)
            print(f"  ! {label} failed ({type(e).__name__}: {e}); keeping previous value", file=sys.stderr)
            return None

    oil = _try("brent_crude", fetch_brent_crude)
    oil_quarterly, oil_daily = oil if oil else (prev.get("brent_crude_quarterly", []), prev.get("brent_crude_daily", []))
    cash_rate = _try("rba_cash_rate", fetch_rba_cash_rate) or prev.get("rba_cash_rate_quarterly", [])
    mortgage_rate = _try("rba_mortgage_rates", fetch_rba_mortgage_rates) or prev.get("rba_mortgage_rate_quarterly", [])
    term_deposit_1y = _try("rba_term_deposit_1y", fetch_rba_term_deposit_1y) or prev.get("rba_term_deposit_1y_quarterly", [])
    cpi_qld = _try("cpi_qld", fetch_cpi_qld) or prev.get("cpi_qld_quarterly", [])
    national_prices = _try("national_house_prices", fetch_national_house_prices) or prev.get("national_house_price_index", [])
    mortgage_impact = _try("mortgage_impact", lambda: build_mortgage_impact(cash_rate, mortgage_rate)) or prev.get("mortgage_impact", {})

    # Start from the previous doc to preserve fields written by other scripts
    # (e.g. national_asking_prices / national_asking_prices_updated), then override.
    doc = {k: v for k, v in prev.items() if k != "_id"}
    doc.update({
        "_id": "macro_indicators",
        "updated_at": datetime.now(timezone.utc),
        "brent_crude_quarterly": oil_quarterly,
        "brent_crude_daily": oil_daily,
        "rba_cash_rate_quarterly": cash_rate,
        "rba_mortgage_rate_quarterly": mortgage_rate,
        "rba_term_deposit_1y_quarterly": term_deposit_1y,
        "cpi_qld_quarterly": cpi_qld,
        "national_house_price_index": national_prices,
        "mortgage_impact": mortgage_impact,
    })

    if args.dry_run:
        print("\n=== DRY RUN ===")
        print(f"Oil: {len(oil_quarterly)} quarters, {len(oil_daily)} daily")
        print(f"Cash rate: {len(cash_rate)} quarters")
        print(f"Mortgage rate: {len(mortgage_rate)} quarters")
        print(f"Term deposit (1yr): {len(term_deposit_1y)} quarters")
        print(f"CPI (QLD): {len(cpi_qld)} quarters")
        print(f"National prices: {len(national_prices)} quarters")
        print(f"\nMortgage impact summary:")
        for i in mortgage_impact.get("impact_summary", []):
            print(f"  {i['label']}: ${i['current_monthly']:,.0f}/month at {i['current_rate']}% (was ${i['year_ago_monthly']:,.0f} at {i['year_ago_rate']}%)")
        if failed:
            print(f"\n(failed sources kept at previous values: {', '.join(failed)})")
        client.close()
        return

    # Write to MongoDB (connection opened above)
    print("\nWriting to MongoDB (Gold_Coast.precomputed_macro_indicators)...")
    db["precomputed_macro_indicators"].replace_one(
        {"_id": "macro_indicators"}, doc, upsert=True
    )
    print(f"  Written successfully. Failed sources (kept previous): {', '.join(failed) if failed else 'none'}")
    client.close()


if __name__ == "__main__":
    main()
