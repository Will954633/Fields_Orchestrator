"""Shared display rounding for the working valuation range.

The working range (``valuation.model_range``) is computed precisely, but for
DISPLAY we round each end to the nearest $100k (normal, half-up) so the
seller-facing figures read as a considered band rather than a machine-precise
output (e.g. ``$1,307,342`` → ``$1,300,000``).

This is PRESENTATION ONLY — the stored ``valuation.model_range`` is never
modified. Every place that shows the working range to a user (buyers tab,
activity feed, narrative prompt context) routes through here so the rounding
is consistent.
"""
from __future__ import annotations

import math
from typing import Any, Dict, Optional, Tuple


def round_to_100k(v: int) -> int:
    """Normal rounding (half up) to the nearest $100,000."""
    return int(math.floor(v / 100_000 + 0.5)) * 100_000


def display_range(
    valuation_range: Optional[Dict[str, Any]]
) -> Optional[Tuple[int, int, str]]:
    """Return ``(low, high, "$lo – $hi")`` with each end rounded to the nearest
    $100k, or ``None`` when there is no usable range. Falls back to the exact
    figures if rounding would collapse the band to a single $100k bucket.
    """
    if not (valuation_range and valuation_range.get("low") and valuation_range.get("high")):
        return None
    low = round_to_100k(int(valuation_range["low"]))
    high = round_to_100k(int(valuation_range["high"]))
    if low >= high:  # degenerate after rounding — keep the exact band
        low, high = int(valuation_range["low"]), int(valuation_range["high"])
    return low, high, f"${low:,} – ${high:,}"
