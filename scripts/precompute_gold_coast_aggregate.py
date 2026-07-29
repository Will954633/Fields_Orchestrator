#!/usr/bin/env python3
"""
precompute_gold_coast_aggregate.py — WTA-013: mint the Gold-Coast city-wide aggregate docs.

The /market-metrics/Gold-Coast page (which receives ~all AI-engine traffic) had no server-side
median/DOM because no `gold_coast` precomputed doc existed — so its stat block + the WTA-012
citable Q&A rendered nothing. This aggregates the three TRACKED core suburbs (Robina, Varsity
Lakes, Burleigh Waters) into a `gold_coast` doc — TRANSACTION-WEIGHTED, so it's methodologically
consistent with the per-suburb pipeline output. The frontend loader picks it up automatically
(suburbSlugToCollection('Gold-Coast') == 'gold_coast') — no website deploy.

Editorial (Rule 5): this is the aggregate of Fields' *tracked* Gold Coast suburbs, not all 85 —
the frontend source line is scoped accordingly (companion edit to buildMarketFaq).

Writes: Gold_Coast.precomputed_indexed_prices (_id=gold_coast),
        Gold_Coast.precomputed_market_charts (_id=gold_coast_days_on_market),
        Gold_Coast.precomputed_active_listings (_id=gold_coast).
Self-monitored (job_run). Run once + monthly (after the suburb precomputes refresh).

Usage: python3 precompute_gold_coast_aggregate.py [--dry-run]
"""
import argparse
import os
import sys
from collections import defaultdict

sys.path.insert(0, "/home/fields/Fields_Orchestrator")
sys.path.insert(0, "/home/fields/Fields_Orchestrator/scripts")
from shared.db import get_gold_coast_db  # noqa: E402

CORE = ["robina", "varsity_lakes", "burleigh_waters"]


def _wmedian(pairs):
    """transaction-weighted mean of (value, weight) — the city-wide aggregate."""
    num = sum(v * w for v, w in pairs if v is not None and w)
    den = sum(w for v, w in pairs if v is not None and w)
    return (num / den) if den else None


def build(dry_run=False):
    db = get_gold_coast_db()
    price_docs = {s: db["precomputed_indexed_prices"].find_one({"_id": s}) for s in CORE}
    dom_docs = {s: db["precomputed_market_charts"].find_one({"_id": f"{s}_days_on_market"}) for s in CORE}
    lst_docs = {s: db["precomputed_active_listings"].find_one({"_id": s}) for s in CORE}

    # --- aggregate indexed_series (txn-weighted median per quarter) ---
    by_period = defaultdict(list)  # period -> [(median, txn)]
    for s, d in price_docs.items():
        for q in (d or {}).get("indexed_series", []):
            by_period[q.get("period")].append((q.get("median_price"), q.get("transaction_count") or 0))
    # keep periods in the order of the longest suburb series
    order = []
    for s in CORE:
        for q in (price_docs.get(s) or {}).get("indexed_series", []):
            if q.get("period") not in order:
                order.append(q.get("period"))
    indexed_series = []
    for p in order:
        pairs = by_period.get(p, [])
        med = _wmedian(pairs)
        txn = sum(w for _, w in pairs)
        if med:
            indexed_series.append({"period": p, "median_price": round(med), "transaction_count": txn})
    latest = indexed_series[-1] if indexed_series else None

    # rolling 12m YoY: txn-weighted avg of the suburbs' own computed yoy
    yoy_pairs = [((price_docs[s] or {}).get("rolling_12m_yoy_pct"),
                  ((price_docs[s] or {}).get("indexed_series") or [{}])[-1].get("transaction_count") or 0)
                 for s in CORE]
    rolling_yoy = _wmedian(yoy_pairs)

    price_doc = {
        "_id": "gold_coast", "suburb": "Gold Coast",
        "scope": "tracked_suburbs", "tracked_suburbs": CORE,
        "indexed_series": indexed_series,
        "rolling_12m_yoy_pct": round(rolling_yoy, 1) if rolling_yoy is not None else None,
        "latest_price": latest["median_price"] if latest else None,
        "transaction_count": latest["transaction_count"] if latest else None,
        "quarters_count": len(indexed_series),
        "note": "Transaction-weighted aggregate of Fields' tracked Gold Coast suburbs (not all 85).",
    }

    # --- aggregate DOM timeline (txn-weighted per period) ---
    dom_by_period = defaultdict(list)
    dom_order = []
    for s in CORE:
        for q in (dom_docs.get(s) or {}).get("timeline", []):
            per = q.get("period")
            txn = next((x.get("transaction_count") for x in (price_docs.get(s) or {}).get("indexed_series", [])
                        if x.get("period") == per), 1) or 1
            dom_by_period[per].append((q.get("median_days_on_market"), txn))
            if per not in dom_order:
                dom_order.append(per)
    dom_timeline = []
    for p in dom_order:
        m = _wmedian(dom_by_period.get(p, []))
        if m is not None:
            dom_timeline.append({"period": p, "median_days_on_market": round(m, 1)})
    dom_doc = {"_id": "gold_coast_days_on_market", "scope": "tracked_suburbs", "timeline": dom_timeline}

    # --- active listings (sum of core) ---
    total_listings = sum(int((lst_docs.get(s) or {}).get("active_listings") or
                             (lst_docs.get(s) or {}).get("count") or 0) for s in CORE)
    lst_doc = {"_id": "gold_coast", "scope": "tracked_suburbs", "active_listings": total_listings,
               "tracked_suburbs": CORE}

    print(f"gold_coast aggregate: median={price_doc['latest_price']} yoy={price_doc['rolling_12m_yoy_pct']}% "
          f"txn={price_doc['transaction_count']} DOM={dom_timeline[-1]['median_days_on_market'] if dom_timeline else None} "
          f"listings={total_listings} · {len(indexed_series)} quarters")

    if not dry_run:
        db["precomputed_indexed_prices"].replace_one({"_id": "gold_coast"}, price_doc, upsert=True)
        db["precomputed_market_charts"].replace_one({"_id": "gold_coast_days_on_market"}, dom_doc, upsert=True)
        db["precomputed_active_listings"].replace_one({"_id": "gold_coast"}, lst_doc, upsert=True)
        print("written to Gold_Coast precomputed collections.")
    return price_doc


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--dry-run", action="store_true")
    args = ap.parse_args()
    try:
        from job_status import job_run
    except Exception:
        job_run = None
    if job_run and not args.dry_run:
        with job_run("gold_coast_aggregate", cadence_hours=24 * 35,
                     title="Gold-Coast market aggregate (WTA-013)") as beat:
            d = build(dry_run=False)
            beat.detail = f"median={d['latest_price']} yoy={d['rolling_12m_yoy_pct']}%"
    else:
        build(dry_run=args.dry_run)


if __name__ == "__main__":
    main()
