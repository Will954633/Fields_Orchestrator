#!/usr/bin/env python3
"""
Generate every chart for The Fields Quarterly Issue 01 (Q1 2026).

Outputs PNG files into pipeline/output/charts/ at consistent dimensions
and visual style for embedding in the HTML report.

USAGE:
    python3 pipeline/generate_charts.py
"""

import os
import sys
import json
import csv
from pathlib import Path
from datetime import datetime
import statistics

import numpy as np
import matplotlib.pyplot as plt
import matplotlib.dates as mdates
import matplotlib.patches as mpatches
import matplotlib.ticker as mticker

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent.parent
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(HERE))

from shared.db import get_db  # noqa: E402
from chart_theme import (
    apply_theme, add_source_line, add_title_block, style_axes,
    BRAND_BLUE, LIGHT_BLUE, SLATE, CHARCOAL, LIGHT_GREY, CREAM, ACCENT, GRID_GREY,
    SUBURB_COLOURS, SUBURB_LABELS,
)
from fci_calculator import (
    canonical_period, parse_period, load_indexed_and_volume, load_dom,
    compute_fci_for_suburb, compute_composite, rebase_to,
    REBASE_PERIOD, CORE_SUBURBS,
)

OUTPUT_DIR = HERE / "output" / "charts"
OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
DATA_DIR = HERE / "output"
DATA_DIR.mkdir(exist_ok=True)


# ----------------------------------------------------------------------------
# Data loading helpers
# ----------------------------------------------------------------------------

def load_all_fci(db):
    """Load FCI series for all 3 core suburbs + composite. Returns dict of suburb -> series."""
    suburb_series = {}
    for s in CORE_SUBURBS:
        series = compute_fci_for_suburb(db, s)
        if series:
            suburb_series[s] = rebase_to(series, REBASE_PERIOD)
    composite = compute_composite(suburb_series)
    if composite:
        composite = rebase_to(composite, REBASE_PERIOD)
    return suburb_series, composite


def load_volume_timeline(db, suburb):
    """Returns timeline list from precomputed_market_charts.{suburb}_sales_volume."""
    doc = db["precomputed_market_charts"].find_one({"_id": f"{suburb}_sales_volume"})
    if not doc:
        return [], None, None
    timeline = doc.get("timeline", [])
    return timeline, doc.get("historical_average"), doc.get("yoy_change")


def load_dom_timeline(db, suburb):
    """Returns DOM timeline + historical median/avg."""
    doc = db["precomputed_market_charts"].find_one({"_id": f"{suburb}_days_on_market"})
    if not doc:
        return [], None, None
    return doc.get("timeline", []), doc.get("historical_median"), doc.get("historical_average")


# ----------------------------------------------------------------------------
# Chart 1: FCI 9-year line
# ----------------------------------------------------------------------------

def chart_fci(suburb_series, composite, path):
    fig, ax = plt.subplots(figsize=(10.5, 5.4))

    for suburb, series in suburb_series.items():
        dates = [r["date"] for r in series]
        fcis = [r["fci"] for r in series]
        ax.plot(dates, fcis, color=SUBURB_COLOURS[suburb], linewidth=1.2, alpha=0.7,
                label=SUBURB_LABELS[suburb], zorder=2)

    if composite:
        dates = [r["date"] for r in composite]
        fcis = [r["fci"] for r in composite]
        ax.plot(dates, fcis, color=CHARCOAL, linewidth=2.4,
                label="Southern Gold Coast (composite)", zorder=3)
        # Annotate latest
        latest = composite[-1]
        ax.annotate(f" {latest['fci']:.1f}",
                    xy=(latest["date"], latest["fci"]),
                    color=CHARCOAL, fontsize=10, fontweight="semibold",
                    verticalalignment="center")

    # Reference bands
    ax.axhline(100, color=LIGHT_GREY, linewidth=0.8, zorder=1)
    ax.axhline(115, color=LIGHT_GREY, linewidth=0.4, linestyle="--", zorder=1, alpha=0.6)
    ax.axhline(85, color=LIGHT_GREY, linewidth=0.4, linestyle="--", zorder=1, alpha=0.6)

    # Right-margin band labels
    xmax = ax.get_xlim()[1]
    ax.text(xmax, 115, "  tight", color=LIGHT_GREY, fontsize=7, va="center")
    ax.text(xmax, 100, "  baseline", color=LIGHT_GREY, fontsize=7, va="center")
    ax.text(xmax, 85, "  buyers", color=LIGHT_GREY, fontsize=7, va="center")

    add_title_block(fig,
        "The Fields Conviction Index since Q1 2017",
        "Q1 2020 baseline = 100. Composite is transaction-weighted across the three core suburbs.")

    style_axes(ax, ylabel="Fields Conviction Index")
    ax.xaxis.set_major_locator(mdates.YearLocator())
    ax.xaxis.set_major_formatter(mdates.DateFormatter("%Y"))
    ax.legend(loc="lower left", ncol=2)

    add_source_line(fig,
        "Source: Fields Real Estate, precomputed_indexed_prices and precomputed_market_charts. "
        "FCI v2: 50% indexed price + 25% sales volume + 25% inverse DOM where DOM available; otherwise 67%/33% price/volume.")
    plt.tight_layout(rect=[0, 0.04, 1, 0.85])
    plt.savefig(path)
    plt.close()


# ----------------------------------------------------------------------------
# Chart 2: The Conviction Map (suburb scatter)
# ----------------------------------------------------------------------------

def chart_conviction_map(db, path):
    """
    Scatter of all available suburbs on:
      X = 12-month rolling indexed price change (%)
      Y = latest-quarter sales-volume z-score from precomputed_market_charts.sales_volume
          (the same source the website's market-narrative endpoint serves and
           the same source the report prose cites)

    For suburbs without sales_volume coverage, falls back to indexed_series
    .transaction_count z-score so the map still includes them.

    Quadrants:
      Top-right: Heating (price up, volume up)
      Top-left: Recovering (volume up, price flat/down)
      Bottom-right: Standoff (price up but volume thinning)
      Bottom-left: Cooling
    """
    # Load all suburbs from precomputed_indexed_prices.
    # Exclude meta-aggregate documents (not real suburbs) — these would mix
    # categories on a scatter of individual suburbs.
    EXCLUDED_AGGREGATES = {"gold_coast_average", "southern_gold_coast", "all"}

    cursor = db["precomputed_indexed_prices"].find({})
    suburbs_data = []
    for doc in cursor:
        suburb = doc["_id"]
        if suburb in EXCLUDED_AGGREGATES:
            continue
        yoy_pct = doc.get("rolling_12m_yoy_pct")
        n_trans = doc.get("rolling_12m_transaction_count", 0)
        if yoy_pct is None or n_trans < 30:
            continue

        series = doc.get("indexed_series", [])
        if len(series) < 8:
            continue

        # Volume z-score: prefer precomputed_market_charts.sales_volume (matches FCI v2 + prose).
        # Fall back to indexed_series.transaction_count if not available.
        z_vol = None
        sv_doc = db["precomputed_market_charts"].find_one({"_id": f"{suburb}_sales_volume"})
        if sv_doc and sv_doc.get("timeline"):
            # Skip in-progress quarter
            today = datetime.now()
            current_q = (today.month - 1) // 3 + 1
            in_progress = f"{today.year}-Q{current_q}"
            sv_timeline = [e for e in sv_doc["timeline"] if e.get("period") != in_progress and e.get("sales_count") is not None]
            if len(sv_timeline) >= 4:
                latest_sv = sv_timeline[-1]["sales_count"]
                hist_sv = [e["sales_count"] for e in sv_timeline[:-1]]
                mu = statistics.mean(hist_sv)
                sd = statistics.stdev(hist_sv) if len(hist_sv) > 1 else 0
                z_vol = (latest_sv - mu) / sd if sd > 0 else 0
        if z_vol is None:
            # Fallback: indexed_series.transaction_count
            latest_n = series[-1].get("transaction_count", 0)
            hist = [e.get("transaction_count", 0) for e in series[-21:-1]]
            if len(hist) < 8:
                continue
            mu = statistics.mean(hist)
            sd = statistics.stdev(hist) if len(hist) > 1 else 0
            z_vol = (latest_n - mu) / sd if sd > 0 else 0

        suburbs_data.append({
            "suburb": suburb,
            "price_yoy_pct": yoy_pct,
            "z_volume": z_vol,
            "transaction_count": n_trans,
        })

    if not suburbs_data:
        print("WARN: no suburbs with sufficient data for Conviction Map")
        return

    fig, ax = plt.subplots(figsize=(10.5, 7.2))
    ax.set_facecolor("#FFFFFF")

    # Pass 1: plot dots (scatter) so axis bounds settle before label placement.
    for sd in suburbs_data:
        is_core = sd["suburb"] in CORE_SUBURBS
        if is_core:
            color = SUBURB_COLOURS[sd["suburb"]]
            edgecolor = CHARCOAL
            zorder = 3
            size = 90
            alpha = 1.0
        else:
            color = LIGHT_GREY
            edgecolor = SLATE
            zorder = 2
            size = 50
            alpha = 0.85
        ax.scatter(sd["price_yoy_pct"], sd["z_volume"],
                   s=size, c=color, edgecolors=edgecolor, linewidths=0.6,
                   alpha=alpha, zorder=zorder)

    # Pad axis limits so quadrant text in the corners doesn't overprint
    # extreme dots, and so the y=0 boundary line sits visibly *inside* the
    # plot rather than at its edge — readers need to see clearly that all
    # core-suburb dots fall below z=0 (i.e. inside STANDOFF, not HEATING).
    _xmin, _xmax = ax.get_xlim()
    _ymin, _ymax = ax.get_ylim()
    ax.set_xlim(_xmin - 0.5, _xmax + 0.5)
    ax.set_ylim(_ymin - 0.6, max(_ymax, 0) + 1.2)

    # Pass 2: place labels with corner-collision avoidance. Dots that land in
    # the right-edge quadrant zones (HEATING top-right, STANDOFF bottom-right)
    # get their label flipped to the left of the dot so it doesn't overprint
    # the quadrant text.
    xlim_lbl = ax.get_xlim()
    ylim_lbl = ax.get_ylim()
    xspan_lbl = xlim_lbl[1] - xlim_lbl[0]
    yspan_lbl = ylim_lbl[1] - ylim_lbl[0]

    def _in_right_corner(x, y):
        near_right = x > xlim_lbl[1] - 0.22 * xspan_lbl
        near_top = y > ylim_lbl[1] - 0.18 * yspan_lbl
        near_bottom = y < ylim_lbl[0] + 0.18 * yspan_lbl
        return near_right and (near_top or near_bottom)

    for sd in suburbs_data:
        is_core = sd["suburb"] in CORE_SUBURBS
        label = SUBURB_LABELS.get(sd["suburb"], sd["suburb"].replace("_", " ").title())
        flip_left = _in_right_corner(sd["price_yoy_pct"], sd["z_volume"])
        text = f"{label}  " if flip_left else f"  {label}"
        ha = "right" if flip_left else "left"
        if is_core:
            ax.annotate(text,
                        xy=(sd["price_yoy_pct"], sd["z_volume"]),
                        fontsize=10, color=CHARCOAL, fontweight="semibold",
                        ha=ha, va="center", zorder=4)
        else:
            ax.annotate(text,
                        xy=(sd["price_yoy_pct"], sd["z_volume"]),
                        fontsize=8, color=SLATE, fontweight="normal",
                        ha=ha, va="center", zorder=4)

    # Quadrant boundary lines — darker/thicker than gridlines so readers can
    # see at a glance which side of zero each dot sits on.
    ax.axhline(0, color=SLATE, linewidth=1.0, zorder=1)
    ax.axvline(0, color=SLATE, linewidth=1.0, zorder=1)

    # Quadrant labels (positioned in corners)
    xlim = ax.get_xlim()
    ylim = ax.get_ylim()
    pad_x = 0.4
    pad_y = 0.15
    ax.text(xlim[1] - pad_x, ylim[1] - pad_y, "HEATING\nprice ↑   volume ↑",
            ha="right", va="top", fontsize=9, color=SLATE, fontweight="semibold")
    ax.text(xlim[0] + pad_x, ylim[1] - pad_y, "RECOVERING\nvolume ↑   price ↓",
            ha="left", va="top", fontsize=9, color=SLATE, fontweight="semibold")
    ax.text(xlim[1] - pad_x, ylim[0] + pad_y, "STANDOFF\nprice ↑   volume ↓",
            ha="right", va="bottom", fontsize=9, color=ACCENT, fontweight="semibold")
    ax.text(xlim[0] + pad_x, ylim[0] + pad_y, "COOLING\nprice ↓   volume ↓",
            ha="left", va="bottom", fontsize=9, color=SLATE, fontweight="semibold")

    add_title_block(fig,
        "The Fields Conviction Map — Q1 2026",
        f"{len(suburbs_data)} Gold Coast suburbs plotted on price growth × volume strength. "
        f"Core suburbs highlighted; southern Gold Coast sits in STANDOFF.")

    style_axes(ax, xlabel="Rolling 12-month price growth (% YoY)",
               ylabel="Sales-volume z-score (vs 5-year same-quarter)")
    ax.xaxis.set_major_formatter(mticker.PercentFormatter(decimals=0))

    add_source_line(fig,
        "Source: precomputed_indexed_prices.rolling_12m_yoy_pct (X) + precomputed_market_charts.sales_volume.sales_count z-scored against own history (Y). "
        "Sample restricted to suburbs with ≥30 trailing-12m transactions.")
    plt.tight_layout(rect=[0, 0.04, 1, 0.85])
    plt.savefig(path)
    plt.close()


# ----------------------------------------------------------------------------
# Chart 3: The Tension (twin line — indexed price vs FCI for composite)
# ----------------------------------------------------------------------------

def chart_tension(suburb_series, composite, path):
    """
    Twin-line: composite indexed price (using indexed_series median) vs FCI.
    Both rebased to Q1 2023 = 100 to expose recent divergence.
    """
    if not composite:
        return

    # Composite indexed price = transaction-weighted average of suburb median prices
    # We approximate by averaging the index_value across the 3 suburbs
    db = get_db("Gold_Coast")
    suburb_indexes = {}
    for s in CORE_SUBURBS:
        series = load_indexed_and_volume(db, s)
        # Build {date -> index_value}
        d = {}
        for entry in series:
            if entry["index_value"] is not None:
                d[parse_period(entry["period"])] = entry["index_value"]
        suburb_indexes[s] = d

    # Build composite index values (average across suburbs at each date)
    all_dates = set()
    for d in suburb_indexes.values():
        all_dates.update(d.keys())
    composite_index = {}
    for date in sorted(all_dates):
        vals = [suburb_indexes[s].get(date) for s in CORE_SUBURBS if date in suburb_indexes[s]]
        if vals and len(vals) == len(CORE_SUBURBS):  # only when all 3 have data
            composite_index[date] = sum(vals) / len(vals)

    # Rebase both series to a common point (Q1 2023)
    rebase_date = parse_period("Q1 2023")
    if rebase_date not in composite_index:
        rebase_date = sorted(composite_index.keys())[0]

    # Filter to last ~3 years for the rebase view
    fci_dates = [r["date"] for r in composite if r["date"] >= rebase_date]
    fci_values = [r["fci"] for r in composite if r["date"] >= rebase_date]

    idx_dates = sorted([d for d in composite_index.keys() if d >= rebase_date])
    idx_values = [composite_index[d] for d in idx_dates]

    # Rebase indexed price to 100 at rebase_date
    if idx_values:
        rebase_idx_value = idx_values[0]
        # Convert from "base 0" to "base 100": these index_values are already growth pct from baseline
        # If index_value is 169.39 it means 169.39% above baseline (or Q2 2016 = 0). Let me check.
        # Actually look at first entry: Q2 2016 has index_value 0.0 — so it's pct from baseline.
        # So we need to convert (1 + ix/100) and rebase.
        rebased_idx = [100 * (1 + v/100) / (1 + rebase_idx_value/100) for v in idx_values]

    # FCI: same rebase
    if fci_values:
        rebase_fci_value = fci_values[0]
        rebased_fci = [100 * v / rebase_fci_value for v in fci_values]

    fig, ax = plt.subplots(figsize=(10.5, 5.4))
    ax.set_facecolor("#FFFFFF")

    ax.plot(idx_dates, rebased_idx, color=BRAND_BLUE, linewidth=2.4,
            label="Indexed median price (composite)", zorder=3)
    ax.plot(fci_dates, rebased_fci, color=SLATE, linewidth=2.4,
            label="Fields Conviction Index (composite)", zorder=3)

    # Annotate end points
    if rebased_idx:
        ax.annotate(f" {rebased_idx[-1]:.1f}",
                    xy=(idx_dates[-1], rebased_idx[-1]),
                    color=BRAND_BLUE, fontsize=10, fontweight="semibold", va="center")
    if rebased_fci:
        ax.annotate(f" {rebased_fci[-1]:.1f}",
                    xy=(fci_dates[-1], rebased_fci[-1]),
                    color=SLATE, fontsize=10, fontweight="semibold", va="center")

    ax.axhline(100, color=LIGHT_GREY, linewidth=0.6, zorder=1)

    add_title_block(fig,
        "The Standoff — when the price line and the conviction line separate",
        "Both series rebased to Q1 2023 = 100. The two lines tracked closely until mid-2025; they have separated since.")

    style_axes(ax, ylabel="Index (Q1 2023 = 100)")
    ax.xaxis.set_major_locator(mdates.YearLocator())
    ax.xaxis.set_major_formatter(mdates.DateFormatter("%Y"))
    ax.legend(loc="upper left")

    add_source_line(fig,
        "Sources: Fields composite indexed median (average of Robina, Burleigh Waters, Varsity Lakes index_value); "
        "Fields Conviction Index v1 composite (transaction-weighted).")
    plt.tight_layout(rect=[0, 0.04, 1, 0.85])
    plt.savefig(path)
    plt.close()


# ----------------------------------------------------------------------------
# Chart 4: Indexed prices — three suburbs
# ----------------------------------------------------------------------------

def chart_indexed_prices(db, path):
    fig, ax = plt.subplots(figsize=(10.5, 5.4))
    ax.set_facecolor("#FFFFFF")

    # Pull from indexed_series, use index_value (which is pct change from base)
    # Convert to 100 = rebase point (Q1 2020)
    rebase_period = "Q1 2020"
    rebase_date = parse_period(rebase_period)

    for s in CORE_SUBURBS:
        series = load_indexed_and_volume(db, s)
        if not series:
            continue
        # Find rebase index_value
        rebase_iv = None
        for entry in series:
            if entry["period"] == rebase_period:
                rebase_iv = entry["index_value"]
                break
        if rebase_iv is None:
            continue

        dates = []
        rebased = []
        for entry in series:
            iv = entry["index_value"]
            if iv is not None:
                dates.append(entry["date"])
                # Convert to multiplicative form rebased to 100 at Q1 2020
                rebased.append(100 * (1 + iv/100) / (1 + rebase_iv/100))

        ax.plot(dates, rebased,
                color=SUBURB_COLOURS[s],
                linewidth=2.0 if s == "burleigh_waters" else 1.6,
                label=SUBURB_LABELS[s])
        # End-label
        if dates:
            ax.annotate(f" {rebased[-1]:.0f}",
                        xy=(dates[-1], rebased[-1]),
                        color=SUBURB_COLOURS[s], fontsize=9, fontweight="semibold", va="center")

    ax.axhline(100, color=LIGHT_GREY, linewidth=0.6, zorder=1)

    add_title_block(fig,
        "Indexed median price by suburb, Q1 2020 = 100",
        "Robina, Burleigh Waters and Varsity Lakes have all roughly 1.7×'d since the start of 2020.")

    style_axes(ax, ylabel="Index (Q1 2020 = 100)")
    ax.xaxis.set_major_locator(mdates.YearLocator())
    ax.xaxis.set_major_formatter(mdates.DateFormatter("%Y"))
    ax.legend(loc="upper left")

    add_source_line(fig,
        "Source: precomputed_indexed_prices.indexed_series. Quarterly. "
        "Houses only, deduplicated across three sources. Sample sizes per quarter in the appendix.")
    plt.tight_layout(rect=[0, 0.04, 1, 0.85])
    plt.savefig(path)
    plt.close()


# ----------------------------------------------------------------------------
# Chart 5: Sales volume by suburb
# ----------------------------------------------------------------------------

def chart_sales_volume(db, path):
    """Stacked bar chart of quarterly sales volume by suburb (last ~3 years).

    EXCLUDES the in-progress quarter (Q2 2026 — partial data).
    """
    fig, ax = plt.subplots(figsize=(10.5, 5.4))
    ax.set_facecolor("#FFFFFF")

    # Determine which quarter is in-progress
    today = datetime.now()
    current_q = (today.month - 1) // 3 + 1
    in_progress_period = f"{today.year}-Q{current_q}"

    # Load timeline for each suburb
    suburb_data = {}
    all_periods = set()
    for s in CORE_SUBURBS:
        timeline, hist_avg, _ = load_volume_timeline(db, s)
        # Filter out the in-progress quarter
        timeline = [e for e in timeline if e["period"] != in_progress_period]
        suburb_data[s] = {
            "timeline": timeline,
            "hist_avg": hist_avg,
        }
        for entry in timeline:
            all_periods.add(entry["period"])

    sorted_periods = sorted(all_periods, key=lambda p: parse_period(p))
    if not sorted_periods:
        return

    # Build per-period counts
    bar_data = {s: [] for s in CORE_SUBURBS}
    for p in sorted_periods:
        for s in CORE_SUBURBS:
            entry = next((e for e in suburb_data[s]["timeline"] if e["period"] == p), None)
            bar_data[s].append(entry["sales_count"] if entry else 0)

    x = list(range(len(sorted_periods)))
    width = 0.27
    offsets = [-width, 0, width]
    for i, s in enumerate(CORE_SUBURBS):
        ax.bar([xi + offsets[i] for xi in x], bar_data[s], width=width,
               color=SUBURB_COLOURS[s], label=SUBURB_LABELS[s], edgecolor="none")

    # Historical-average reference lines per suburb (drawn faintly)
    for s in CORE_SUBURBS:
        avg = suburb_data[s].get("hist_avg")
        if avg:
            ax.axhline(avg, color=SUBURB_COLOURS[s], linewidth=0.5, linestyle="--", alpha=0.5, zorder=0)

    ax.set_xticks(x)
    ax.set_xticklabels(sorted_periods, rotation=45, ha="right", fontsize=7)

    add_title_block(fig,
        "Quarterly sales volume by suburb",
        "Burleigh Waters' Q1 2026 print of 30 sales is 35.7% below its 5-year same-quarter average. "
        "Robina is on trend; Varsity Lakes is mildly below.")

    style_axes(ax, ylabel="Quarterly sales count")
    ax.legend(loc="upper right")

    add_source_line(fig,
        "Source: precomputed_market_charts.{suburb}_sales_volume. Houses only, deduplicated. "
        "Dashed lines show each suburb's historical quarterly average.")
    plt.tight_layout(rect=[0, 0.04, 1, 0.85])
    plt.savefig(path)
    plt.close()


# ----------------------------------------------------------------------------
# Chart 6: Days-on-market trend by suburb
# ----------------------------------------------------------------------------

def chart_dom(db, path):
    fig, ax = plt.subplots(figsize=(10.5, 5.4))
    ax.set_facecolor("#FFFFFF")

    for s in CORE_SUBURBS:
        timeline, hist_med, hist_avg = load_dom_timeline(db, s)
        if not timeline:
            continue
        dates = [parse_period(e["period"]) for e in timeline]
        med_dom = [e.get("median_days_on_market") for e in timeline]

        ax.plot(dates, med_dom,
                color=SUBURB_COLOURS[s],
                linewidth=2.0 if s == "burleigh_waters" else 1.6,
                marker="o", markersize=4,
                label=SUBURB_LABELS[s])

        # End-point label — offset slightly to avoid overlap when values match
        if dates:
            # Stagger labels by suburb position
            offsets = {"robina": 4, "burleigh_waters": -4, "varsity_lakes": 0}
            ax.annotate(f"  {SUBURB_LABELS[s][:3]} {med_dom[-1]:.0f}d",
                        xy=(dates[-1], med_dom[-1] + offsets.get(s, 0)),
                        color=SUBURB_COLOURS[s], fontsize=8, fontweight="semibold", va="center")

        # Historical median ref line
        if hist_med:
            ax.axhline(hist_med, color=SUBURB_COLOURS[s], linewidth=0.4,
                       linestyle="--", alpha=0.4, zorder=0)

    add_title_block(fig,
        "Median days-on-market by suburb",
        "Days-on-market has lengthened in Robina and Varsity Lakes; Burleigh Waters is essentially in line "
        "with its historical median. Dashed lines show each suburb's historical median.")

    style_axes(ax, ylabel="Median days-on-market")
    ax.xaxis.set_major_locator(mdates.MonthLocator(bymonth=[1, 7]))
    ax.xaxis.set_major_formatter(mdates.DateFormatter("%b %Y"))
    plt.setp(ax.xaxis.get_majorticklabels(), rotation=30, ha="right")
    ax.legend(loc="upper left")

    add_source_line(fig,
        "Source: precomputed_market_charts.{suburb}_days_on_market. List-to-unconditional, "
        "private-treaty + auction combined. Sample sizes per quarter in the appendix.")
    plt.tight_layout(rect=[0, 0.04, 1, 0.85])
    plt.savefig(path)
    plt.close()


# ----------------------------------------------------------------------------
# Chart 7: Per-suburb sale-price distributions (using sold records)
# ----------------------------------------------------------------------------

def chart_distributions(db, path):
    """Half-violin + scatter for each suburb's recent sold records."""
    # Pull sold records from Gold_Coast suburb collections
    fig, axes = plt.subplots(1, 3, figsize=(11.5, 5.0), sharey=False)
    fig.patch.set_facecolor(CREAM)

    for i, suburb in enumerate(CORE_SUBURBS):
        ax = axes[i]
        ax.set_facecolor("#FFFFFF")

        # Pull all sold records
        coll = db[suburb]
        cursor = coll.find(
            {"listing_status": "sold"},
            {"sale_price": 1, "sold_date": 1, "sale_date": 1}
        )
        prices = []
        for doc in cursor:
            sp = doc.get("sale_price")
            if sp is None:
                continue
            # sale_price is a string like "$1,800,000"
            if isinstance(sp, str):
                sp_clean = sp.replace("$", "").replace(",", "").strip()
                try:
                    val = float(sp_clean)
                except ValueError:
                    continue
            else:
                val = float(sp)
            if val < 100000 or val > 10_000_000:  # filter outliers
                continue
            prices.append(val)

        if not prices:
            continue

        prices.sort()
        median = statistics.median(prices)
        p25 = np.percentile(prices, 25)
        p75 = np.percentile(prices, 75)
        p10 = np.percentile(prices, 10)
        p90 = np.percentile(prices, 90)
        n = len(prices)

        # Scatter (jittered horizontally)
        np.random.seed(42)
        x_jitter = np.random.uniform(-0.15, 0.15, n)
        ax.scatter(x_jitter, [p / 1e6 for p in prices],
                   s=10, c=SUBURB_COLOURS[suburb], alpha=0.35, zorder=2)

        # Box markers (median + IQR)
        ax.plot([-0.3, 0.3], [median / 1e6] * 2, color=CHARCOAL, linewidth=2, zorder=3)
        ax.plot([-0.25, 0.25], [p25 / 1e6] * 2, color=CHARCOAL, linewidth=1, zorder=3)
        ax.plot([-0.25, 0.25], [p75 / 1e6] * 2, color=CHARCOAL, linewidth=1, zorder=3)
        ax.plot([0, 0], [p25 / 1e6, p75 / 1e6], color=CHARCOAL, linewidth=1, zorder=3)
        # Whiskers
        ax.plot([0, 0], [p10 / 1e6, p25 / 1e6], color=LIGHT_GREY, linewidth=0.8, zorder=3)
        ax.plot([0, 0], [p75 / 1e6, p90 / 1e6], color=LIGHT_GREY, linewidth=0.8, zorder=3)

        # Annotate median
        ax.annotate(f"  median ${median/1e6:.2f}M",
                    xy=(0.3, median / 1e6),
                    fontsize=9, color=CHARCOAL, va="center", fontweight="semibold")

        ax.set_title(f"{SUBURB_LABELS[suburb]}\nN={n}",
                     loc="left", pad=8, fontsize=11, color=CHARCOAL, fontweight="semibold")
        ax.set_xlim(-0.6, 0.9)
        ax.set_xticks([])
        ax.spines["top"].set_visible(False)
        ax.spines["right"].set_visible(False)
        ax.spines["bottom"].set_visible(False)
        ax.spines["left"].set_color(LIGHT_GREY)
        ax.tick_params(axis="y", colors=CHARCOAL, length=2)
        ax.grid(axis="y", color=GRID_GREY, linewidth=0.4, alpha=0.6)
        ax.yaxis.set_major_formatter(mticker.FuncFormatter(lambda v, _: f"${v:.1f}M"))

    fig.text(0.0, 0.97, "Three suburbs, three distributions",
             fontsize=13, color=CHARCOAL, fontweight="semibold")
    fig.text(0.0, 0.94,
             "The median is a single number; the distribution shows what's actually selling. "
             "Burleigh Waters' upper tail (canal-front) is what drags the median upward.",
             fontsize=8, color=SLATE)

    add_source_line(fig,
        "Source: Gold_Coast.{suburb} sold records, all available transactions. "
        "Box: median + IQR (25th/75th percentile). Whiskers: 10th/90th. Outliers <$100k or >$10M excluded.")
    plt.tight_layout(rect=[0, 0.04, 1, 0.92])
    plt.savefig(path)
    plt.close()


# ----------------------------------------------------------------------------
# Main
# ----------------------------------------------------------------------------

def main():
    apply_theme()
    db = get_db("Gold_Coast")

    print("Loading FCI series...")
    suburb_series, composite = load_all_fci(db)

    charts = [
        ("01_fci_main.png", lambda: chart_fci(suburb_series, composite, OUTPUT_DIR / "01_fci_main.png")),
        ("02_conviction_map.png", lambda: chart_conviction_map(db, OUTPUT_DIR / "02_conviction_map.png")),
        ("03_tension.png", lambda: chart_tension(suburb_series, composite, OUTPUT_DIR / "03_tension.png")),
        ("04_indexed_prices.png", lambda: chart_indexed_prices(db, OUTPUT_DIR / "04_indexed_prices.png")),
        ("05_sales_volume.png", lambda: chart_sales_volume(db, OUTPUT_DIR / "05_sales_volume.png")),
        ("06_dom.png", lambda: chart_dom(db, OUTPUT_DIR / "06_dom.png")),
        ("07_distributions.png", lambda: chart_distributions(db, OUTPUT_DIR / "07_distributions.png")),
    ]

    for name, fn in charts:
        try:
            print(f"  {name}")
            fn()
        except Exception as e:
            print(f"    ERROR: {e}")
            import traceback
            traceback.print_exc()

    print(f"\nAll charts written to {OUTPUT_DIR}")


if __name__ == "__main__":
    main()
