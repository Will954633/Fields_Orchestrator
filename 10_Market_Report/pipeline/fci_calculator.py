#!/usr/bin/env python3
"""
Fields Conviction Index (FCI) — calculator.

The FCI is the proprietary headline number for The Fields Quarterly. It
combines indexed price, sales volume, and days-on-market into a single
composite, rebased so a value of 100 represents a typical southern Gold
Coast quarter (2020 baseline).

DESIGNED FORMULA (per strategy/03_content_blueprint.md §1):
    40% indexed price + 20% sale-to-list + 20% stock-on-market vs 5yr baseline + 20% inverse DOM

V1 IMPLEMENTATION (this file):
The designed formula needs four components. Two of them — sale-to-list ratio
and historical stock-on-market — are not yet available in precomputed form
across the required history. The current available components are:

  - Indexed price            (40 quarters, Q2 2016 → present)
  - Sales volume             (40 quarters, Q2 2016 → present, from .transaction_count)
  - Days-on-market median    (12 quarters, Q2 2023 → present)

V1 weights (renormalised to 1.0 over available components):

  Recent quarters (DOM available):    50% indexed price + 25% volume + 25% inverse DOM
  Earlier quarters (DOM not avail.):  67% indexed price + 33% volume

The output series is the same single-number index — readers see a continuous
line. The methodology page discloses the construction transparently.

V2 (planned): once sale-to-list data is backfilled into a precomputed
collection, this calculator will switch to the four-component formula. The
historical FCI numbers will shift; that shift is itself a publishable event.

USAGE:
    python3 pipeline/fci_calculator.py
    # writes:
    #   pipeline/output/fci_series.csv   (long format, all suburbs + composite)
    #   pipeline/output/fci_chart.png    (5-year chart, single brand colour)
"""

import os
import sys
from pathlib import Path
from datetime import datetime
import csv
import json

import numpy as np
import matplotlib.pyplot as plt
import matplotlib.dates as mdates

# Allow running from anywhere
HERE = Path(__file__).resolve().parent
ROOT = HERE.parent.parent  # Fields_Orchestrator
sys.path.insert(0, str(ROOT))

from shared.db import get_db  # noqa: E402

OUTPUT_DIR = HERE / "output"
OUTPUT_DIR.mkdir(exist_ok=True)

# Configuration ----------------------------------------------------------------

CORE_SUBURBS = ["robina", "burleigh_waters", "varsity_lakes"]

# Composite is a transaction-weighted average of the three core suburbs.
# (Implementation note: weighting by transaction count gives bigger suburbs
# more influence, which matches how an analyst would think of "the southern
# Gold Coast" — it's not an arithmetic mean of three equal markets.)

# Rebase point — FCI = 100 here.
REBASE_PERIOD = "Q1 2020"

# Z-score window — components are normalised against their own history over
# this many years to produce comparable contributions.
Z_WINDOW_YEARS = 5

# Brand palette (matches strategy/04_visual_format_spec.md)
BRAND_BLUE = "#003D5B"
SLATE = "#6B7280"
CREAM = "#F7F4EE"
CHARCOAL = "#1A1A1A"
LIGHT_GREY = "#9CA3AF"


# ----------------------------------------------------------------------------
# Data loading
# ----------------------------------------------------------------------------

def parse_period(period_str):
    """
    Parse 'Q2 2016' or '2023-Q2' into a sortable date.

    Note: indexed_series stores end-of-quarter dates (Q1=Mar, Q2=Jun, Q3=Sep, Q4=Dec).
    We normalise everything to end-of-quarter so cross-collection joins work.
    """
    s = period_str.strip()
    if "-" in s:
        # '2023-Q2' format
        year_str, q_str = s.split("-")
        q = int(q_str.replace("Q", ""))
        year = int(year_str)
    else:
        # 'Q2 2016' format
        q_str, year_str = s.split()
        q = int(q_str.replace("Q", ""))
        year = int(year_str)
    end_of_q_month = {1: 3, 2: 6, 3: 9, 4: 12}[q]
    return datetime(year, end_of_q_month, 1)


def canonical_period(period_str):
    """Normalise both 'Q2 2016' and '2023-Q2' to canonical 'YYYY-Qn'."""
    s = period_str.strip()
    if "-" in s:
        year_str, q_str = s.split("-")
        q = int(q_str.replace("Q", ""))
        year = int(year_str)
    else:
        q_str, year_str = s.split()
        q = int(q_str.replace("Q", ""))
        year = int(year_str)
    return f"{year}-Q{q}"


def load_indexed_and_volume(db, suburb):
    """
    Returns a list of dicts, one per quarter:
        {date, period, median_price, index_value, transaction_count}
    """
    doc = db["precomputed_indexed_prices"].find_one({"_id": suburb})
    if not doc or "indexed_series" not in doc:
        return []
    out = []
    for entry in doc["indexed_series"]:
        out.append({
            "suburb": suburb,
            "date": entry.get("date") if isinstance(entry.get("date"), datetime) else parse_period(entry["period"]),
            "period": entry["period"],
            "median_price": entry.get("median_price"),
            "index_value": entry.get("index_value"),
            "transaction_count": entry.get("transaction_count"),
        })
    return sorted(out, key=lambda x: x["date"])


def load_dom(db, suburb):
    """
    Returns a dict: {canonical_period -> median_dom}
    Keyed by canonical period string (e.g. '2023-Q2') for safe cross-collection joining.
    """
    doc = db["precomputed_market_charts"].find_one({"_id": f"{suburb}_days_on_market"})
    if not doc or "timeline" not in doc:
        return {}
    out = {}
    for entry in doc["timeline"]:
        cp = canonical_period(entry["period"])
        med = entry.get("median_days_on_market")
        if med is not None:
            out[cp] = med
    return out


def load_sales_volume(db, suburb):
    """
    Returns a dict: {canonical_period -> sales_count}
    From precomputed_market_charts.{suburb}_sales_volume — same source the website uses.
    Excludes the in-progress (current) quarter to avoid the partial-data distortion.
    """
    doc = db["precomputed_market_charts"].find_one({"_id": f"{suburb}_sales_volume"})
    if not doc or "timeline" not in doc:
        return {}
    # Determine in-progress quarter to skip (matches the rule used in generate_charts)
    today = datetime.now()
    current_q = (today.month - 1) // 3 + 1
    in_progress_period = canonical_period(f"{today.year}-Q{current_q}")
    out = {}
    for entry in doc["timeline"]:
        cp = canonical_period(entry["period"])
        if cp == in_progress_period:
            continue
        sc = entry.get("sales_count")
        if sc is not None:
            out[cp] = sc
    return out


# ----------------------------------------------------------------------------
# FCI computation
# ----------------------------------------------------------------------------

def z_score(series, window_years=Z_WINDOW_YEARS):
    """
    Rolling z-score: each point z-scored against the trailing window-years
    of values up to and including that point.

    Returns numpy array same length as series; np.nan where window is too short.

    series: list of (date, value) tuples, sorted by date.
    """
    n = len(series)
    z = np.full(n, np.nan)
    for i in range(n):
        cutoff_date = series[i][0]
        window_start = cutoff_date.replace(year=cutoff_date.year - window_years)
        window_vals = [v for d, v in series[:i + 1] if d >= window_start and v is not None]
        if len(window_vals) >= 4:  # need at least 4 quarters of history
            mu = float(np.mean(window_vals))
            sd = float(np.std(window_vals, ddof=1)) if len(window_vals) > 1 else 0.0
            if sd > 0:
                z[i] = (series[i][1] - mu) / sd
            else:
                z[i] = 0.0
    return z


def compute_fci_for_suburb(db, suburb):
    """
    Compute FCI series for one suburb.
    Returns list of dicts: {date, period, fci, components, components_used}

    Volume basis (v2):
      - Where precomputed_market_charts sales_volume covers the period
        (post Q2 2023), we use sales_count from there — same number the
        website's market-narrative endpoint serves and the same number the
        report prose cites. Z-scored against its own (~3-year) history.
      - For older periods, we fall back to indexed_series.transaction_count
        from precomputed_indexed_prices, z-scored against its own history.
      - This produces a small discontinuity at the boundary (mid-2023). The
        methodology page discloses this; the historical context is preserved
        and the recent FCI reading aligns with prose figures.
    """
    indexed = load_indexed_and_volume(db, suburb)
    dom = load_dom(db, suburb)  # {canonical_period -> median_dom}
    broad_volume = load_sales_volume(db, suburb)  # {canonical_period -> sales_count}

    if not indexed:
        return []

    # ---- Price series (always from indexed_series) ----
    price_series = [(e["date"], e["index_value"]) for e in indexed if e["index_value"] is not None]
    z_price = z_score(price_series)
    price_z_by_cp = {canonical_period(e["period"]): z for e, z in zip(indexed, z_price) if e["index_value"] is not None}

    # ---- Volume: two parallel series, each z-scored against its own basis ----
    # Strict (indexed_series.transaction_count) covers the full history
    strict_vol_series = [(e["date"], e["transaction_count"]) for e in indexed if e["transaction_count"] is not None]
    z_vol_strict = z_score(strict_vol_series)
    vol_strict_z_by_cp = {canonical_period(e["period"]): z for e, z in zip(indexed, z_vol_strict) if e["transaction_count"] is not None}

    # Broad (sales_volume.sales_count) covers post-2023-Q2 only
    broad_items_sorted = sorted(broad_volume.items(), key=lambda kv: parse_period(kv[0]))
    broad_vol_pairs = [(parse_period(cp), v) for cp, v in broad_items_sorted]
    z_vol_broad = z_score(broad_vol_pairs)
    broad_cp_sorted = [cp for cp, _ in broad_items_sorted]
    vol_broad_z_by_cp = dict(zip(broad_cp_sorted, z_vol_broad))

    # ---- DOM (always from precomputed_market_charts.days_on_market) ----
    dom_pairs = sorted([(parse_period(cp), -m) for cp, m in dom.items()])  # negate so higher = better
    z_dom = z_score(dom_pairs)
    dom_canonical_periods = sorted(dom.keys(), key=parse_period)
    dom_z_by_cp = dict(zip(dom_canonical_periods, z_dom))

    out = []
    for entry in indexed:
        d = entry["date"]
        cp = canonical_period(entry["period"])
        zp = price_z_by_cp.get(cp)
        zd = dom_z_by_cp.get(cp)

        # Volume z-score: prefer broad (sales_volume.sales_count, matches website
        # + prose) when available, else fall back to strict (indexed_series).
        zv_broad = vol_broad_z_by_cp.get(cp)
        zv_strict = vol_strict_z_by_cp.get(cp)
        if zv_broad is not None and not np.isnan(zv_broad):
            zv = zv_broad
            volume_basis = "sales_volume.sales_count"
        elif zv_strict is not None and not np.isnan(zv_strict):
            zv = zv_strict
            volume_basis = "indexed_series.transaction_count"
        else:
            zv = None
            volume_basis = None

        if zp is None or np.isnan(zp):
            # Can't compute without price
            continue

        if zd is not None and not np.isnan(zd):
            # Full 3-component
            w_price, w_volume, w_dom = 0.50, 0.25, 0.25
            components_used = f"price+volume({volume_basis})+dom"
        else:
            # 2-component
            w_price, w_volume, w_dom = 0.67, 0.33, 0.0
            components_used = f"price+volume({volume_basis})"

        zv_eff = zv if (zv is not None and not np.isnan(zv)) else 0.0
        zd_eff = zd if (zd is not None and not np.isnan(zd)) else 0.0

        composite_z = w_price * zp + w_volume * zv_eff + w_dom * zd_eff

        # Map z to FCI scale: FCI = 100 + 10 * z
        fci = 100 + 10 * composite_z

        # Pull the actual count we used (for transparency in CSV output)
        if volume_basis == "sales_volume.sales_count":
            tc = broad_volume.get(cp)
        else:
            tc = entry.get("transaction_count")

        out.append({
            "suburb": suburb,
            "date": d,
            "period": entry["period"],
            "fci": fci,
            "z_price": float(zp) if zp is not None and not np.isnan(zp) else None,
            "z_volume": float(zv) if zv is not None and not np.isnan(zv) else None,
            "z_dom": float(zd) if zd is not None and not np.isnan(zd) else None,
            "components_used": components_used,
            "volume_basis": volume_basis,
            "median_price": entry["median_price"],
            "transaction_count": tc,
        })

    return out


def rebase_to(series, rebase_period):
    """Shift the series so FCI at rebase_period = 100."""
    rebase_val = None
    for row in series:
        if row["period"] == rebase_period:
            rebase_val = row["fci"]
            break
    if rebase_val is None:
        # Find nearest
        target = parse_period(rebase_period)
        nearest = min(series, key=lambda r: abs((r["date"] - target).days))
        rebase_val = nearest["fci"]
        print(f"  WARN: '{rebase_period}' not in series; using nearest {nearest['period']} ({rebase_val:.2f})")
    delta = 100 - rebase_val
    for row in series:
        row["fci"] = row["fci"] + delta
    return series


def compute_composite(suburb_series_dict):
    """
    Transaction-weighted composite of the suburb FCIs.
    suburb_series_dict: {suburb: [series rows]}
    Returns: list of composite rows
    """
    # Find common periods
    periods = None
    for s in suburb_series_dict.values():
        ps = {row["period"] for row in s}
        periods = ps if periods is None else periods & ps

    composite = []
    for period in sorted(periods, key=parse_period):
        weights = []
        values = []
        for suburb, series in suburb_series_dict.items():
            row = next((r for r in series if r["period"] == period), None)
            if row and row["fci"] is not None:
                weights.append(row.get("transaction_count") or 0)
                values.append(row["fci"])
        if values and sum(weights) > 0:
            fci = sum(v * w for v, w in zip(values, weights)) / sum(weights)
        elif values:
            fci = sum(values) / len(values)
        else:
            continue
        composite.append({
            "suburb": "southern_gold_coast",
            "date": parse_period(period),
            "period": period,
            "fci": fci,
            "transaction_count": sum(weights) if weights else 0,
        })
    return composite


# ----------------------------------------------------------------------------
# Output
# ----------------------------------------------------------------------------

def write_csv(all_series, path):
    fieldnames = ["suburb", "period", "date", "fci", "z_price", "z_volume", "z_dom",
                  "components_used", "median_price", "transaction_count"]
    with open(path, "w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=fieldnames, extrasaction="ignore")
        w.writeheader()
        for row in all_series:
            r = dict(row)
            if isinstance(r.get("date"), datetime):
                r["date"] = r["date"].strftime("%Y-%m-%d")
            w.writerow(r)


def plot_fci(suburb_series_dict, composite, path):
    fig, ax = plt.subplots(figsize=(11, 6.5), dpi=150)
    fig.patch.set_facecolor(CREAM)
    ax.set_facecolor("#FFFFFF")

    # Suburb lines (lighter)
    suburb_colors = {
        "robina": "#7AA8C2",
        "burleigh_waters": BRAND_BLUE,
        "varsity_lakes": SLATE,
    }
    suburb_labels = {
        "robina": "Robina",
        "burleigh_waters": "Burleigh Waters",
        "varsity_lakes": "Varsity Lakes",
    }

    for suburb, series in suburb_series_dict.items():
        dates = [r["date"] for r in series]
        fcis = [r["fci"] for r in series]
        ax.plot(dates, fcis, color=suburb_colors[suburb], linewidth=1.2, alpha=0.7,
                label=suburb_labels[suburb], zorder=2)

    # Composite line (heavy, brand)
    if composite:
        dates = [r["date"] for r in composite]
        fcis = [r["fci"] for r in composite]
        ax.plot(dates, fcis, color=CHARCOAL, linewidth=2.4,
                label="Southern Gold Coast (composite)", zorder=3)

    # Reference lines
    ax.axhline(100, color=LIGHT_GREY, linewidth=0.8, linestyle="-", zorder=1)
    ax.axhline(115, color=LIGHT_GREY, linewidth=0.5, linestyle="--", zorder=1, alpha=0.6)
    ax.axhline(85, color=LIGHT_GREY, linewidth=0.5, linestyle="--", zorder=1, alpha=0.6)

    # Annotations on the right margin
    ax.text(ax.get_xlim()[1], 115, " tight", color=LIGHT_GREY, fontsize=8,
            verticalalignment="center")
    ax.text(ax.get_xlim()[1], 100, " baseline", color=LIGHT_GREY, fontsize=8,
            verticalalignment="center")
    ax.text(ax.get_xlim()[1], 85, " buyers' advantage", color=LIGHT_GREY, fontsize=8,
            verticalalignment="center")

    # Format
    ax.set_title("Fields Conviction Index — southern Gold Coast",
                 fontsize=14, color=CHARCOAL, loc="left", weight="semibold", pad=14)
    ax.text(0.0, 1.025,
            f"Q1 2020 baseline = 100. Composite is transaction-weighted across the three core suburbs. "
            f"V1 implementation uses indexed price + sales volume + days-on-market.",
            transform=ax.transAxes, fontsize=8, color=SLATE)
    ax.set_xlabel("")
    ax.set_ylabel("FCI", fontsize=10, color=CHARCOAL)
    ax.tick_params(axis="both", colors=CHARCOAL, labelsize=9)
    ax.spines["top"].set_visible(False)
    ax.spines["right"].set_visible(False)
    ax.spines["left"].set_color(LIGHT_GREY)
    ax.spines["bottom"].set_color(LIGHT_GREY)
    ax.grid(axis="y", color=LIGHT_GREY, linewidth=0.3, alpha=0.4)
    ax.xaxis.set_major_locator(mdates.YearLocator())
    ax.xaxis.set_major_formatter(mdates.DateFormatter("%Y"))
    ax.legend(loc="lower left", frameon=False, fontsize=9, ncol=2)

    # Source line
    fig.text(0.02, 0.02,
             "Source: Fields Real Estate (precomputed_indexed_prices, precomputed_market_charts). "
             "FCI v1: 50% price + 25% volume + 25% inverse DOM where DOM available; otherwise 67%/33% price/volume.",
             fontsize=7, color=SLATE)

    plt.tight_layout(rect=[0, 0.04, 1, 1])
    plt.savefig(path, facecolor=CREAM, dpi=150, bbox_inches="tight")
    plt.close()


def write_summary(all_series, composite, path):
    """Plain-text summary of the FCI series for the README."""
    lines = []
    lines.append("# FCI v1 — Output Summary\n")
    lines.append(f"Generated: {datetime.now().isoformat(timespec='seconds')}\n")
    lines.append(f"Rebase: {REBASE_PERIOD} = 100\n")
    lines.append(f"Z-score window: {Z_WINDOW_YEARS} years rolling\n\n")

    lines.append("## Latest values\n\n")
    lines.append("| Suburb | Period | FCI | Components used |\n")
    lines.append("|---|---|---|---|\n")

    by_suburb = {}
    for row in all_series:
        by_suburb.setdefault(row["suburb"], []).append(row)
    for suburb, series in by_suburb.items():
        latest = series[-1]
        lines.append(f"| {suburb} | {latest['period']} | {latest['fci']:.1f} | "
                     f"{latest.get('components_used', 'n/a')} |\n")
    if composite:
        latest_c = composite[-1]
        lines.append(f"| **Southern Gold Coast** | **{latest_c['period']}** | **{latest_c['fci']:.1f}** | composite |\n")

    lines.append("\n## Range across history\n\n")
    lines.append("| Suburb | Min FCI | Max FCI | Min period | Max period |\n")
    lines.append("|---|---|---|---|---|\n")
    for suburb, series in by_suburb.items():
        sorted_s = sorted(series, key=lambda r: r["fci"])
        mn, mx = sorted_s[0], sorted_s[-1]
        lines.append(f"| {suburb} | {mn['fci']:.1f} | {mx['fci']:.1f} | {mn['period']} | {mx['period']} |\n")
    if composite:
        sorted_c = sorted(composite, key=lambda r: r["fci"])
        mn, mx = sorted_c[0], sorted_c[-1]
        lines.append(f"| **Southern Gold Coast** | **{mn['fci']:.1f}** | **{mx['fci']:.1f}** | "
                     f"**{mn['period']}** | **{mx['period']}** |\n")

    lines.append("\n## Series length per suburb\n\n")
    for suburb, series in by_suburb.items():
        first, last = series[0], series[-1]
        lines.append(f"- **{suburb}**: {len(series)} quarters ({first['period']} → {last['period']})\n")
    if composite:
        first, last = composite[0], composite[-1]
        lines.append(f"- **Southern Gold Coast composite**: {len(composite)} quarters ({first['period']} → {last['period']})\n")

    with open(path, "w") as f:
        f.writelines(lines)


# ----------------------------------------------------------------------------
# Main
# ----------------------------------------------------------------------------

def main():
    db = get_db("Gold_Coast")
    print("Computing FCI for core suburbs...")
    suburb_series = {}
    for suburb in CORE_SUBURBS:
        print(f"  {suburb}")
        series = compute_fci_for_suburb(db, suburb)
        if not series:
            print(f"    WARN: no series produced for {suburb}")
            continue
        # Rebase to common period
        series = rebase_to(series, REBASE_PERIOD)
        suburb_series[suburb] = series

    print("\nComputing southern Gold Coast composite...")
    composite = compute_composite(suburb_series)
    if composite:
        composite = rebase_to(composite, REBASE_PERIOD)

    # Output
    all_rows = []
    for s in suburb_series.values():
        all_rows.extend(s)
    all_rows.extend(composite)

    csv_path = OUTPUT_DIR / "fci_series.csv"
    chart_path = OUTPUT_DIR / "fci_chart.png"
    summary_path = OUTPUT_DIR / "fci_summary.md"

    write_csv(all_rows, csv_path)
    print(f"\n  Wrote {csv_path}")

    plot_fci(suburb_series, composite, chart_path)
    print(f"  Wrote {chart_path}")

    write_summary(all_rows, composite, summary_path)
    print(f"  Wrote {summary_path}")

    # Quick-look in stdout
    print("\n=== Latest FCI values ===")
    for suburb, series in suburb_series.items():
        latest = series[-1]
        print(f"  {suburb:20s} {latest['period']:10s}  FCI = {latest['fci']:6.1f}  "
              f"({latest.get('components_used', 'n/a')})")
    if composite:
        latest_c = composite[-1]
        print(f"  {'COMPOSITE':20s} {latest_c['period']:10s}  FCI = {latest_c['fci']:6.1f}")


if __name__ == "__main__":
    main()
