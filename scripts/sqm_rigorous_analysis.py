#!/usr/bin/env python3
"""
Rigorous analysis of SQM asking prices vs actual sale prices.
Tests: monthly resolution, Granger causality, cross-correlation,
asking premium dynamics, turning point analysis.
"""

import sys
import warnings
warnings.filterwarnings('ignore')

import yaml
import numpy as np
import pandas as pd
from pymongo import MongoClient
from datetime import datetime
import re

# ─── Connect to MongoDB ───
with open("/home/fields/Fields_Orchestrator/config/settings.yaml") as f:
    cfg = yaml.safe_load(f)
client = MongoClient(cfg["mongodb"]["uri"])
db = client["Gold_Coast"]

# ─── Postcode → suburb mapping (based on SQM coverage notes) ───
POSTCODE_MAP = {
    "4216": {
        "name": "Robina area (4216)",
        "suburbs": ["robina", "merrimac", "clear_island_waters"],
    },
    "4226": {
        "name": "Burleigh area (4226)",
        "suburbs": ["burleigh_waters", "burleigh_heads", "miami"],
    },
    "4227": {
        "name": "Varsity Lakes area (4227)",
        "suburbs": ["varsity_lakes", "reedy_creek"],
    },
}


def parse_price(price_str):
    """Parse price string like '$1,520,000' to float."""
    if not price_str or not isinstance(price_str, str):
        return None
    cleaned = re.sub(r'[^\d.]', '', price_str)
    try:
        val = float(cleaned)
        return val if 50000 < val < 20000000 else None
    except (ValueError, TypeError):
        return None


def load_sqm_monthly(postcode):
    """Load SQM weekly data, aggregate to monthly medians."""
    doc = db["sqm_asking_prices"].find_one({"postcode": postcode})
    if not doc:
        return None

    rows = []
    for entry in doc["series"]:
        dt = pd.to_datetime(entry["date"])
        rows.append({
            "date": dt,
            "houses_all": entry.get("houses_all"),
            "units_all": entry.get("units_all"),
            "combined": entry.get("combined"),
        })

    df = pd.DataFrame(rows)
    df = df.set_index("date")
    # Resample to monthly medians
    monthly = df.resample("MS").median()
    monthly = monthly.dropna(subset=["combined"])
    return monthly


def load_sold_monthly(suburbs, property_type_filter=None):
    """Load sold records from multiple suburb collections, aggregate to monthly medians."""
    records = []
    for suburb in suburbs:
        coll = db[suburb]
        query = {"listing_status": "sold", "sold_date": {"$exists": True}, "sale_price": {"$exists": True}}
        for doc in coll.find(query, {"sale_price": 1, "sold_date": 1, "property_type": 1}):
            price = parse_price(doc.get("sale_price"))
            date_str = doc.get("sold_date")
            ptype = doc.get("property_type", "")

            if not price or not date_str:
                continue

            if property_type_filter and property_type_filter.lower() not in (ptype or "").lower():
                continue

            try:
                dt = pd.to_datetime(date_str)
            except:
                continue

            records.append({"date": dt, "sale_price": price, "property_type": ptype})

    if not records:
        return None

    df = pd.DataFrame(records)
    df["month"] = df["date"].dt.to_period("M").dt.to_timestamp()

    monthly = df.groupby("month").agg(
        median_sale_price=("sale_price", "median"),
        mean_sale_price=("sale_price", "mean"),
        count=("sale_price", "count"),
    )
    monthly.index.name = "date"
    return monthly


def run_analysis(postcode, info):
    """Run full analysis for one postcode area."""
    print(f"\n{'='*80}")
    print(f"  ANALYSIS: {info['name']}")
    print(f"  Suburbs: {', '.join(info['suburbs'])}")
    print(f"{'='*80}")

    # Load data
    sqm = load_sqm_monthly(postcode)
    sold = load_sold_monthly(info["suburbs"])

    if sqm is None:
        print("  ERROR: No SQM data found")
        return
    if sold is None:
        print("  ERROR: No sold data found")
        return

    print(f"\n  SQM monthly data points: {len(sqm)} ({sqm.index.min().strftime('%Y-%m')} to {sqm.index.max().strftime('%Y-%m')})")
    print(f"  Sold monthly data points: {len(sold)} ({sold.index.min().strftime('%Y-%m')} to {sold.index.max().strftime('%Y-%m')})")

    # Also load houses-only sold data for comparison with houses_all asking
    sold_houses = load_sold_monthly(info["suburbs"], property_type_filter="house")
    if sold_houses is not None:
        print(f"  Sold houses-only data points: {len(sold_houses)} ({sold_houses.index.min().strftime('%Y-%m')} to {sold_houses.index.max().strftime('%Y-%m')})")

    # Merge on common months
    merged = sqm[["combined", "houses_all", "units_all"]].join(sold[["median_sale_price", "count"]], how="inner")
    merged = merged.dropna(subset=["combined", "median_sale_price"])

    if len(merged) < 6:
        print(f"  WARNING: Only {len(merged)} overlapping months — insufficient for meaningful analysis")
        if len(merged) > 0:
            print(f"  Overlap period: {merged.index.min().strftime('%Y-%m')} to {merged.index.max().strftime('%Y-%m')}")
        return

    print(f"\n  Overlapping months: {len(merged)} ({merged.index.min().strftime('%Y-%m')} to {merged.index.max().strftime('%Y-%m')})")
    print(f"  Monthly sale counts: min={merged['count'].min()}, median={merged['count'].median():.0f}, max={merged['count'].max()}")

    # Also merge houses-only if available
    merged_houses = None
    if sold_houses is not None:
        merged_houses = sqm[["houses_all"]].join(sold_houses[["median_sale_price", "count"]], how="inner")
        merged_houses = merged_houses.dropna(subset=["houses_all", "median_sale_price"])
        merged_houses = merged_houses.rename(columns={"median_sale_price": "house_sale_price"})

    # ─── 1. LEVEL CORRELATIONS ───
    print(f"\n{'─'*60}")
    print("  1. LEVEL CORRELATIONS (monthly)")
    print(f"{'─'*60}")

    from scipy import stats

    r_combined, p_combined = stats.pearsonr(merged["combined"], merged["median_sale_price"])
    print(f"  SQM combined asking vs median sale price: r={r_combined:.4f}, p={p_combined:.4g}")

    r_houses, p_houses = stats.pearsonr(merged["houses_all"], merged["median_sale_price"])
    print(f"  SQM houses asking vs median sale price: r={r_houses:.4f}, p={p_houses:.4g}")

    if merged_houses is not None and len(merged_houses) >= 6:
        r_hh, p_hh = stats.pearsonr(merged_houses["houses_all"], merged_houses["house_sale_price"])
        print(f"  SQM houses asking vs houses-only sale price: r={r_hh:.4f}, p={p_hh:.4g}")

    # ─── 2. RATE-OF-CHANGE CORRELATIONS ───
    print(f"\n{'─'*60}")
    print("  2. RATE-OF-CHANGE CORRELATIONS")
    print(f"{'─'*60}")

    for window_name, window in [("1-month", 1), ("3-month", 3), ("6-month", 6), ("12-month", 12)]:
        asking_roc = merged["combined"].pct_change(window).dropna()
        sale_roc = merged["median_sale_price"].pct_change(window).dropna()
        common = asking_roc.index.intersection(sale_roc.index)
        if len(common) >= 5:
            r, p = stats.pearsonr(asking_roc[common], sale_roc[common])
            print(f"  {window_name} rate-of-change: r={r:.4f}, p={p:.4g}, n={len(common)}")

    # ─── 3. CROSS-CORRELATION FUNCTION ───
    print(f"\n{'─'*60}")
    print("  3. CROSS-CORRELATION FUNCTION (monthly lags -12 to +12)")
    print(f"{'─'*60}")
    print("  Positive lag = asking prices LEAD sale prices")
    print("  Negative lag = sale prices LEAD asking prices")
    print()

    # Use log-returns for stationarity
    asking_ret = np.log(merged["combined"]).diff().dropna()
    sale_ret = np.log(merged["median_sale_price"]).diff().dropna()
    common_idx = asking_ret.index.intersection(sale_ret.index)
    asking_ret = asking_ret[common_idx]
    sale_ret = sale_ret[common_idx]

    best_lag = 0
    best_corr = 0
    ccf_results = []

    for lag in range(-12, 13):
        if lag > 0:
            x = asking_ret.iloc[:-lag] if lag < len(asking_ret) else asking_ret
            y = sale_ret.iloc[lag:] if lag < len(sale_ret) else sale_ret
        elif lag < 0:
            x = asking_ret.iloc[-lag:]
            y = sale_ret.iloc[:lag]
        else:
            x = asking_ret
            y = sale_ret

        min_len = min(len(x), len(y))
        if min_len < 5:
            continue
        x = x.iloc[:min_len]
        y = y.iloc[:min_len]

        r, p = stats.pearsonr(x.values, y.values)
        ccf_results.append((lag, r, p, min_len))

        marker = ""
        if abs(r) > abs(best_corr):
            best_corr = r
            best_lag = lag
            marker = " ◄ BEST"

        bar = "█" * int(abs(r) * 40)
        sign = "+" if r > 0 else "-"
        sig = "*" if p < 0.05 else " "
        print(f"  Lag {lag:+3d}: r={r:+.4f} {sig} (n={min_len:3d}) {sign}{bar}{marker}")

    print(f"\n  Best cross-correlation: lag={best_lag:+d}, r={best_corr:+.4f}")
    if best_lag > 0:
        print(f"  → Asking prices lead sale prices by ~{best_lag} month(s)")
    elif best_lag < 0:
        print(f"  → Sale prices lead asking prices by ~{abs(best_lag)} month(s)")
    else:
        print(f"  → Contemporaneous (no lead/lag)")

    # ─── 4. GRANGER CAUSALITY ───
    print(f"\n{'─'*60}")
    print("  4. GRANGER CAUSALITY TESTS")
    print(f"{'─'*60}")

    try:
        from statsmodels.tsa.stattools import grangercausalitytests, adfuller

        # Check stationarity first
        print("\n  Stationarity tests (ADF) on log-returns:")
        adf_asking = adfuller(asking_ret.values, maxlag=6)
        adf_sale = adfuller(sale_ret.values, maxlag=6)
        print(f"    Asking log-returns: ADF stat={adf_asking[0]:.4f}, p={adf_asking[1]:.4g} {'(stationary)' if adf_asking[1] < 0.05 else '(NON-stationary)'}")
        print(f"    Sale log-returns:   ADF stat={adf_sale[0]:.4f}, p={adf_sale[1]:.4g} {'(stationary)' if adf_sale[1] < 0.05 else '(NON-stationary)'}")

        # If not stationary in log-returns, try second differencing
        use_asking = asking_ret.values
        use_sale = sale_ret.values
        diff_label = "log-returns"

        if adf_asking[1] > 0.05 or adf_sale[1] > 0.05:
            print("    → One or both series non-stationary in log-returns, trying second differences...")
            asking_d2 = np.diff(asking_ret.values)
            sale_d2 = np.diff(sale_ret.values)
            adf2a = adfuller(asking_d2, maxlag=6)
            adf2s = adfuller(sale_d2, maxlag=6)
            print(f"    Asking 2nd diff: ADF stat={adf2a[0]:.4f}, p={adf2a[1]:.4g}")
            print(f"    Sale 2nd diff:   ADF stat={adf2s[0]:.4f}, p={adf2s[1]:.4g}")
            if adf2a[1] < 0.05 and adf2s[1] < 0.05:
                use_asking = asking_d2
                use_sale = sale_d2
                diff_label = "2nd-differenced log-returns"

        # Prepare Granger data
        min_len = min(len(use_asking), len(use_sale))
        granger_data = np.column_stack([use_sale[:min_len], use_asking[:min_len]])

        max_lag = min(6, min_len // 4)
        if max_lag >= 1 and min_len >= 10:
            print(f"\n  Testing: 'Do asking price changes Granger-cause sale price changes?'")
            print(f"  Using {diff_label}, max_lag={max_lag}, n={min_len}")
            print()

            results_ask_to_sale = grangercausalitytests(granger_data, maxlag=max_lag, verbose=False)
            for lag_i in range(1, max_lag + 1):
                if lag_i in results_ask_to_sale:
                    f_test = results_ask_to_sale[lag_i][0]['ssr_ftest']
                    chi2_test = results_ask_to_sale[lag_i][0]['ssr_chi2test']
                    sig = "***" if f_test[1] < 0.01 else "**" if f_test[1] < 0.05 else "*" if f_test[1] < 0.10 else ""
                    print(f"    Lag {lag_i}: F={f_test[0]:.3f}, p={f_test[1]:.4f} {sig}")

            # Reverse direction
            granger_data_rev = np.column_stack([use_asking[:min_len], use_sale[:min_len]])
            print(f"\n  Testing: 'Do sale price changes Granger-cause asking price changes?'")
            print()

            results_sale_to_ask = grangercausalitytests(granger_data_rev, maxlag=max_lag, verbose=False)
            for lag_i in range(1, max_lag + 1):
                if lag_i in results_sale_to_ask:
                    f_test = results_sale_to_ask[lag_i][0]['ssr_ftest']
                    sig = "***" if f_test[1] < 0.01 else "**" if f_test[1] < 0.05 else "*" if f_test[1] < 0.10 else ""
                    print(f"    Lag {lag_i}: F={f_test[0]:.3f}, p={f_test[1]:.4f} {sig}")
        else:
            print(f"  WARNING: Insufficient data for Granger test (n={min_len}, need ≥10)")

    except ImportError:
        print("  ERROR: statsmodels not installed — skipping Granger tests")
    except Exception as e:
        print(f"  ERROR in Granger test: {e}")

    # ─── 5. ASKING PRICE PREMIUM ANALYSIS ───
    print(f"\n{'─'*60}")
    print("  5. ASKING PRICE PREMIUM ANALYSIS")
    print(f"{'─'*60}")

    merged["premium"] = merged["combined"] / merged["median_sale_price"]
    merged["premium_pct"] = (merged["premium"] - 1) * 100

    print(f"\n  Premium = (asking / sale) - 1, as percentage")
    print(f"  Mean premium: {merged['premium_pct'].mean():.1f}%")
    print(f"  Median premium: {merged['premium_pct'].median():.1f}%")
    print(f"  Std dev: {merged['premium_pct'].std():.1f}%")
    print(f"  Min: {merged['premium_pct'].min():.1f}% ({merged['premium_pct'].idxmin().strftime('%Y-%m')})")
    print(f"  Max: {merged['premium_pct'].max():.1f}% ({merged['premium_pct'].idxmax().strftime('%Y-%m')})")

    # Premium stability test
    print(f"\n  Premium time series:")
    for idx, row in merged.iterrows():
        bar = "█" * int(abs(row['premium_pct']) / 2)
        sign = "+" if row['premium_pct'] > 0 else "-"
        print(f"    {idx.strftime('%Y-%m')}: {sign}{abs(row['premium_pct']):5.1f}% {sign}{bar}  (n={int(row['count'])} sales)")

    # Does premium predict future price changes?
    print(f"\n  Does premium predict future sale price changes?")
    for horizon in [1, 3, 6]:
        future_ret = merged["median_sale_price"].pct_change(horizon).shift(-horizon)
        valid = merged["premium_pct"].notna() & future_ret.notna()
        if valid.sum() >= 5:
            r, p = stats.pearsonr(merged.loc[valid, "premium_pct"], future_ret[valid])
            print(f"    Premium vs {horizon}-month forward sale return: r={r:.4f}, p={p:.4g}, n={valid.sum()}")
            if r < -0.2 and p < 0.1:
                print(f"      → When premium EXPANDS, sale prices tend to FALL (negative correlation)")
            elif r > 0.2 and p < 0.1:
                print(f"      → When premium EXPANDS, sale prices tend to RISE (positive correlation)")

    # Premium change predicting price changes
    print(f"\n  Does premium CHANGE predict future sale price changes?")
    premium_chg = merged["premium_pct"].diff()
    for horizon in [1, 3, 6]:
        future_ret = merged["median_sale_price"].pct_change(horizon).shift(-horizon)
        valid = premium_chg.notna() & future_ret.notna()
        if valid.sum() >= 5:
            r, p = stats.pearsonr(premium_chg[valid], future_ret[valid])
            print(f"    Premium change vs {horizon}-month forward sale return: r={r:.4f}, p={p:.4g}, n={valid.sum()}")

    # ─── 6. TURNING POINT ANALYSIS ───
    print(f"\n{'─'*60}")
    print("  6. TURNING POINT ANALYSIS")
    print(f"{'─'*60}")

    # Smooth both series with 3-month rolling average to reduce noise
    asking_smooth = merged["combined"].rolling(3, center=True).mean().dropna()
    sale_smooth = merged["median_sale_price"].rolling(3, center=True).mean().dropna()

    # Compute monthly changes
    asking_chg = asking_smooth.diff()
    sale_chg = sale_smooth.diff()

    # Find turning points (sign changes in the smoothed change)
    def find_turning_points(series):
        """Find months where direction changes."""
        tps = []
        for i in range(1, len(series)):
            if series.iloc[i-1] > 0 and series.iloc[i] < 0:
                tps.append((series.index[i], "peak", "rising→falling"))
            elif series.iloc[i-1] < 0 and series.iloc[i] > 0:
                tps.append((series.index[i], "trough", "falling→rising"))
        return tps

    asking_tps = find_turning_points(asking_chg)
    sale_tps = find_turning_points(sale_chg)

    print(f"\n  Asking price turning points (3m smoothed): {len(asking_tps)}")
    for dt, kind, desc in asking_tps:
        print(f"    {dt.strftime('%Y-%m')}: {kind} ({desc})")

    print(f"\n  Sale price turning points (3m smoothed): {len(sale_tps)}")
    for dt, kind, desc in sale_tps:
        print(f"    {dt.strftime('%Y-%m')}: {kind} ({desc})")

    # Match turning points
    if asking_tps and sale_tps:
        print(f"\n  Turning point matching (nearest same-type turning point):")
        leads = []
        for a_dt, a_kind, a_desc in asking_tps:
            # Find nearest sale turning point of same type
            best_match = None
            best_diff = None
            for s_dt, s_kind, s_desc in sale_tps:
                if s_kind == a_kind:
                    diff_months = (s_dt.year - a_dt.year) * 12 + (s_dt.month - a_dt.month)
                    if best_diff is None or abs(diff_months) < abs(best_diff):
                        best_diff = diff_months
                        best_match = s_dt

            if best_match is not None and abs(best_diff) <= 12:
                if best_diff > 0:
                    lead_str = f"asking leads by {best_diff}m"
                elif best_diff < 0:
                    lead_str = f"sale leads by {abs(best_diff)}m"
                else:
                    lead_str = "simultaneous"
                print(f"    {a_kind:6s} @ {a_dt.strftime('%Y-%m')} → sale {a_kind} @ {best_match.strftime('%Y-%m')} ({lead_str})")
                leads.append(best_diff)

        if leads:
            avg_lead = np.mean(leads)
            print(f"\n    Average lead: {avg_lead:+.1f} months")
            if avg_lead > 0:
                print(f"    → On average, asking prices turn {abs(avg_lead):.1f} months BEFORE sale prices")
            elif avg_lead < 0:
                print(f"    → On average, sale prices turn {abs(avg_lead):.1f} months BEFORE asking prices")
            else:
                print(f"    → On average, they turn simultaneously")

    # ─── 7. SUMMARY STATISTICS TABLE ───
    print(f"\n{'─'*60}")
    print("  7. DATA SUMMARY")
    print(f"{'─'*60}")
    print(f"\n  Monthly asking (combined):")
    print(f"    Start: ${merged['combined'].iloc[0]:,.0f}")
    print(f"    End:   ${merged['combined'].iloc[-1]:,.0f}")
    print(f"    Total change: {((merged['combined'].iloc[-1] / merged['combined'].iloc[0]) - 1) * 100:.1f}%")

    print(f"\n  Monthly median sale price:")
    print(f"    Start: ${merged['median_sale_price'].iloc[0]:,.0f}")
    print(f"    End:   ${merged['median_sale_price'].iloc[-1]:,.0f}")
    print(f"    Total change: {((merged['median_sale_price'].iloc[-1] / merged['median_sale_price'].iloc[0]) - 1) * 100:.1f}%")

    return merged


# ─── Run for all postcodes ───
print("╔" + "═"*78 + "╗")
print("║  SQM ASKING PRICES vs ACTUAL SALE PRICES — RIGOROUS ANALYSIS              ║")
print("║  Monthly resolution, Granger causality, cross-correlation, premium, turns  ║")
print("╚" + "═"*78 + "╝")

all_results = {}
for postcode, info in POSTCODE_MAP.items():
    result = run_analysis(postcode, info)
    if result is not None:
        all_results[postcode] = result

# ─── Cross-postcode comparison ───
if len(all_results) > 1:
    print(f"\n\n{'='*80}")
    print("  CROSS-POSTCODE COMPARISON")
    print(f"{'='*80}")

    for postcode, merged in all_results.items():
        info = POSTCODE_MAP[postcode]
        premium_mean = merged["premium_pct"].mean()
        premium_std = merged["premium_pct"].std()

        from scipy import stats
        asking_ret = np.log(merged["combined"]).diff().dropna()
        sale_ret = np.log(merged["median_sale_price"]).diff().dropna()
        common = asking_ret.index.intersection(sale_ret.index)
        if len(common) >= 5:
            r, p = stats.pearsonr(asking_ret[common], sale_ret[common])
        else:
            r, p = 0, 1

        print(f"\n  {info['name']}:")
        print(f"    Months of overlap: {len(merged)}")
        print(f"    Log-return correlation: r={r:.4f}, p={p:.4g}")
        print(f"    Mean premium: {premium_mean:.1f}% ± {premium_std:.1f}%")
        print(f"    Premium range: {merged['premium_pct'].min():.1f}% to {merged['premium_pct'].max():.1f}%")

print(f"\n\n{'='*80}")
print("  ANALYSIS COMPLETE")
print(f"{'='*80}")
