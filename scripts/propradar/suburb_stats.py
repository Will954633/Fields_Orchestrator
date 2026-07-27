"""
suburb_stats.py — accessor for Gold_Coast.propradar_suburb_stats (the authoritative
PropRadar /suburbs snapshot, validated vs realestate.com.au). House-scoped headline
metrics for repointing generators off our under-captured / premium-skewed counts.
"""
from __future__ import annotations

COLLECTION = "propradar_suburb_stats"


def house_headline(db, suburb_key):
    """Authoritative house metrics for a suburb, or None if not ingested yet."""
    d = db[COLLECTION].find_one({"_id": suburb_key})
    if not d:
        return None
    md = d.get("market_dynamics") or {}
    meds = d.get("medians") or {}
    gh = (d.get("growth") or {}).get("house") or {}
    return {
        "median_price": meds.get("house_price"),
        "growth_1y_pct": gh.get("1y_pct"),
        "growth_qtr_pct": gh.get("qtr_pct"),
        "sales_12mo": md.get("house_sales_12mo"),
        "inventory_months": md.get("house_inventory_months"),
        "dom": md.get("house_days_on_market"),
        "heat": md.get("house_heat_score"),
        "as_of": d.get("as_of"),
    }
