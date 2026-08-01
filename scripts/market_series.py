#!/usr/bin/env python3
"""
market_series.py — shared helpers for reading Gold_Coast.precomputed_indexed_prices.

Why this exists: `rolling_12m_median_series` is NOT a contiguous quarterly series.
`precompute_union_prices.py` drops any quarter it could not recompute on the union
basis ("leave it out rather than mix bases"), so the surviving entries are sparse and
irregular — Robina's runs Q3 1991, Q3 1992, Q4 1992, Q2 1993, ... with multi-year gaps.

That makes positional indexing (`series[-21]` for "five years back") silently wrong:
on the current data it lands on Q4 2017 for Robina and Q2 2015 for Varsity Lakes,
producing "five-year growth" figures of 129% and 159%. Always match on the period
LABEL, never on position. See fix-history [PULSE-FIVE-YEAR-INDEX-MISLABEL].
"""
from __future__ import annotations

QUARTERS_IN_5Y_LABEL = 5  # years, matched by label — not a positional offset


def period_tuple(period):
    """'Q2 2026' -> (2026, 2). Returns None if unparseable."""
    if not period or not isinstance(period, str):
        return None
    parts = period.split()
    if len(parts) != 2 or not parts[0].startswith("Q"):
        return None
    try:
        return int(parts[1]), int(parts[0][1:])
    except ValueError:
        return None


def complete_rolling_points(doc):
    """Sorted, in-progress-free rolling-median points that have a parseable period."""
    pts = [
        r for r in (doc.get("rolling_12m_median_series") or [])
        if not r.get("is_in_progress")
        and r.get("rolling_median")
        and period_tuple(r.get("period"))
    ]
    pts.sort(key=lambda r: period_tuple(r["period"]))
    return pts


def five_year_growth(doc, years=QUARTERS_IN_5Y_LABEL):
    """
    Growth in the 12-month rolling median over `years`, matched on the SAME quarter
    `years` earlier (Q2 2026 -> Q2 2021). Returns None when that exact quarter is
    absent — better to say nothing than to compare against whatever happens to sit
    at a fixed offset in a sparse series.
    """
    pts = complete_rolling_points(doc)
    if not pts:
        return None

    latest = pts[-1]
    ly, lq = period_tuple(latest["period"])
    target = (ly - years, lq)
    match = next((r for r in pts if period_tuple(r["period"]) == target), None)
    if not match:
        return None

    then, now = match["rolling_median"], latest["rolling_median"]
    if not then or not now:
        return None

    return {
        "growth_pct": round((now / then - 1) * 100, 1),
        "from_period": match["period"],
        "from_median": then,
        "to_period": latest["period"],
        "to_median": now,
        "years": years,
        "basis": "rolling_12m_median, same-quarter match",
    }
