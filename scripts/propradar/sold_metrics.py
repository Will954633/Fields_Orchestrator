"""
sold_metrics.py — recent sold-rate / volume metrics from Gold_Coast.propradar_sold
(the PropRadar settlement-based feed). This supplies the reliable SOLD denominator
that the Domain scrape under-counts ~2x; numerators like active-listing inventory stay
ours (they're accurate). All property types by default, matching the existing
months-of-supply scope.
"""
from __future__ import annotations

from datetime import datetime, timezone, timedelta

COLLECTION = "propradar_sold"


def _recent_sold_dates(db, suburb_key, property_type=None, window_days=120):
    q = {"suburb_key": suburb_key}
    if property_type:
        q["property_type"] = property_type
    cutoff = (datetime.now(timezone.utc) - timedelta(days=window_days)).strftime("%Y-%m-%d")
    q["sold_date"] = {"$gte": cutoff}
    return sorted(d["sold_date"] for d in db[COLLECTION].find(q, {"sold_date": 1})
                  if d.get("sold_date"))


def monthly_sell_rate(db, suburb_key, property_type=None, window_days=120):
    """Sales per 30 days across the available recent window (>=30d span)."""
    dates = _recent_sold_dates(db, suburb_key, property_type, window_days)
    if len(dates) < 2:
        return None
    d0 = datetime.strptime(dates[0], "%Y-%m-%d")
    d1 = datetime.strptime(dates[-1], "%Y-%m-%d")
    span_days = max((d1 - d0).days, 30)
    return len(dates) / (span_days / 30.0)


def months_of_supply(db, suburb_key, active_count, property_type=None, window_days=120):
    """(months_of_supply, monthly_rate) or (None, None) if no PropRadar data yet."""
    rate = monthly_sell_rate(db, suburb_key, property_type, window_days)
    if not rate:
        return None, None
    return round(active_count / rate, 1), round(rate, 1)


def annualized_volume(db, suburb_key, property_type=None, window_days=120):
    """Current sell-rate projected to 12 months (labelled as run-rate, not a literal tally)."""
    rate = monthly_sell_rate(db, suburb_key, property_type, window_days)
    return round(rate * 12) if rate else None
