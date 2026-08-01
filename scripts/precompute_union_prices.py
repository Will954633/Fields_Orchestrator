#!/usr/bin/env python3
"""
precompute_union_prices.py — corrected price/volume series for the market
intelligence page, computed from the Domain ∪ onthehouse union.

WHY (2026-08-01)
----------------
The live series had four compounding defects, found while auditing the Q2
newsletter against realestate.com.au:

1. `recalibrate_charts.py` overwrote our 12-month median with PropRadar's, via a
   scalar factor anchored on a MEAN OF FOUR QUARTERLY MEDIANS (not a 12-month
   median). PropRadar reports 240 Burleigh Waters house sales against REA's 195
   at a 10% lower median, and its BW `unit_price` is null despite 75 unit sales —
   its house/unit split for that suburb is broken. Result: BW published at
   $1,625,976 against a REA-comparable $1,855,550-$1,910,000.
2. The same script scaled `transaction_count` by ONE uniform factor, which
   assumes capture is constant over time. It is not — Domain's share of the
   union runs 89% / 39% / 43% across Q4 2025 / Q1 2026 / Q2 2026 for Robina, so
   the factor preserved settlement lag as if it were a market signal.
3. Dwelling-type was filtered on the type FIELD alone, so unit-numbered
   addresses sat inside the house median and 14-50 records per suburb with no
   type were dropped silently. See `shared/dwelling_type.py`.
4. Single-quarter medians were published as headline figures. Bootstrapped 90%
   CIs put them at +/-5-9% (BW Q4 2025 at +/-16.9%), so no recent quarter-on-quarter
   move is distinguishable from noise.

WHAT THIS DOES
--------------
* House-only via the shared classifier, counting (not dropping) unknowns.
* Last 12 months from the Domain ∪ onthehouse union, joined on the integration's
  own `address_key`.
* Earlier history from Domain property timelines — the union cannot reach back,
  because onthehouse's sold index is a 12-month window. This is disclosed in the
  output as `union_from`, and history is labelled Domain-recorded.
* A bootstrap 90% CI on every median, so the page can publish a range.
* Volume ONLY for the union window. Splicing union counts onto Domain-only
  history would show a +30-160% step that is us getting better at looking, not
  the market moving.

Writes to `precomputed_indexed_prices_staging` and diffs against live. It does
NOT touch the live collection — promote deliberately with --promote once the
diff has been read.

Usage:
    python3 scripts/precompute_union_prices.py                 # staging + diff
    python3 scripts/precompute_union_prices.py --promote       # also write live
"""
from __future__ import annotations

import argparse
import random
import re
import statistics
import sys
from collections import defaultdict
from datetime import datetime, timedelta
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "scripts"))

from shared.db import get_client                      # noqa: E402
from shared.dwelling_type import classify_dwelling    # noqa: E402
from onthehouse.matching import address_key           # noqa: E402

SUBURBS = ["robina", "burleigh_waters", "varsity_lakes"]
STAGING = "precomputed_indexed_prices_staging"
LIVE = "precomputed_indexed_prices"

PRICE_FLOOR = 150_000
PRICE_CEILING = 10_000_000
MIN_N_QUARTER = 5          # below this a quarterly median is not reported at all
BOOTSTRAP_N = 2000
BASELINE_PERIOD = "Q1 2020"

random.seed(42)            # reproducible CIs — the same data must give the same range


def qtr(date_str: str) -> str:
    y, m = int(date_str[:4]), int(date_str[5:7])
    return f"Q{(m - 1) // 3 + 1} {y}"


def qsort(period: str):
    q, y = period.split()
    return (int(y), int(q[1:]))


def current_quarter() -> str:
    """The quarter we are standing in. It is ALWAYS incomplete, and including it
    in a '12-month' median silently shortens the window — on 1 Aug, a window
    ending Q3 2026 is nine complete months plus one week of sales."""
    now = datetime.utcnow()
    return f"Q{(now.month - 1) // 3 + 1} {now.year}"


def parse_price(val):
    if isinstance(val, str):
        digits = re.sub(r"[^0-9]", "", val)
        val = int(digits) if digits else None
    if not isinstance(val, (int, float)):
        return None
    val = int(val)
    return val if PRICE_FLOOR <= val <= PRICE_CEILING else None


def bootstrap_ci(values, confidence=0.90):
    """90% CI for the median. Reported so the page can publish a range instead of
    false precision — a suburb median on 40 sales is not a point estimate."""
    if len(values) < MIN_N_QUARTER:
        return None, None
    draws = sorted(
        statistics.median(random.choices(values, k=len(values)))
        for _ in range(BOOTSTRAP_N)
    )
    lo = draws[int((1 - confidence) / 2 * BOOTSTRAP_N)]
    hi = draws[int((1 - (1 - confidence) / 2) * BOOTSTRAP_N)]
    return int(lo), int(hi)


def load_domain_history(gc, suburb, counters):
    """Every sale we hold for houses in this suburb, from property timelines.

    Timelines are per-property sale histories embedded by the Domain scrape, which
    is why history reaches back to 2016 while the sold-listing feed only covers
    recent months. Deduped on (address, date) so a property appearing in both the
    timeline and the sold feed is counted once.
    """
    sales = {}
    projection = {
        "street_address": 1, "suburb": 1, "property_type": 1,
        "classified_property_type": 1, "sale_price": 1, "sold_date": 1,
        "sale_date": 1, "listing_status": 1,
        "scraped_data.features.property_type": 1,
        "scraped_data.property_timeline": 1,
        "scraped_data_v2.property_type": 1,
    }
    for doc in gc[suburb].find({}, projection):
        bucket = classify_dwelling(doc)
        # Count only SALES-BEARING docs. The suburb collections are mostly cadastral
        # records with no transaction history, so counting every doc made the
        # exclusion figures look catastrophic when the `unknown` bucket actually
        # holds 44/17/18 sold events across the three suburbs — noise, not loss.
        timeline = ((doc.get("scraped_data") or {}).get("property_timeline")) or []
        has_sales = doc.get("listing_status") == "sold" or any(
            isinstance(e, dict) and e.get("is_sold") for e in timeline
        )
        if bucket != "house":
            if has_sales:
                counters[bucket] += 1
            continue
        if has_sales:
            counters["house"] += 1
        key = address_key(doc.get("street_address") or "", doc.get("suburb"))
        if not key:
            counters["no_address_key"] += 1
            continue

        # (a) the property's own sale history
        timeline = ((doc.get("scraped_data") or {}).get("property_timeline")) or []
        for event in timeline:
            if not isinstance(event, dict) or not event.get("is_sold"):
                continue
            date = str(event.get("date") or "")[:10]
            price = parse_price(event.get("price"))
            if len(date) == 10 and price:
                sales[(key, date)] = price

        # (b) the sold-listing record itself
        if doc.get("listing_status") == "sold":
            date = str(doc.get("sold_date") or doc.get("sale_date") or "")[:10]
            price = parse_price(doc.get("sale_price"))
            if len(date) == 10 and price:
                sales[(key, date)] = price
    return sales


def load_onthehouse(sm, suburb, counters):
    """onthehouse sold overlay — a 12-month window, houses only, priced sales.

    Price-withheld records (24% of sold houses) carry sale_price None and are
    counted, not silently skipped: they are real transactions we cannot price, and
    excluding them without saying so would misstate volume.
    """
    sales = {}
    pattern = "^" + suburb.replace("_", "-")
    for doc in sm["onthehouse_sold"].find({"suburb_key": {"$regex": pattern}}):
        if classify_dwelling(doc) != "house":
            counters["oth_not_house"] += 1
            continue
        date = str(doc.get("sold_date") or "")[:10]
        if len(date) != 10:
            continue
        if doc.get("price_withheld") or not doc.get("sale_price"):
            counters["oth_price_withheld"] += 1
            continue
        price = parse_price(doc.get("sale_price"))
        key = doc.get("match_key") or address_key(doc.get("address") or "")
        if price and key:
            sales[(key, date)] = price
    return sales


def build_series(sales, union_from):
    """Quarterly and rolling-12-month medians with CIs.

    Quarterly medians are reported but flagged `reliable: False` when the CI is
    wider than +/-7%, because a +/-9% quarterly figure cannot support a statement
    about a 5% quarter-on-quarter move.
    """
    by_quarter = defaultdict(list)
    for (_, date), price in sales.items():
        by_quarter[qtr(date)].append(price)

    in_progress = current_quarter()
    quarterly = []
    for period in sorted(by_quarter, key=qsort):
        prices = by_quarter[period]
        if len(prices) < MIN_N_QUARTER:
            continue
        median = int(statistics.median(prices))
        lo, hi = bootstrap_ci(prices)
        margin = max(median - lo, hi - median) / median if lo else None
        quarterly.append({
            "period": period,
            "median_price": median,
            "transaction_count": len(prices),
            "ci_low": lo,
            "ci_high": hi,
            "ci_margin_pct": round(margin * 100, 1) if margin else None,
            "reliable": bool(margin and margin <= 0.07),
            "is_in_progress": period == in_progress,
            "basis": "union" if qsort(period) >= qsort(union_from) else "domain_only",
        })

    # index the quarterly medians so a constant proportional coverage bias cancels
    base = next((q["median_price"] for q in quarterly if q["period"] == BASELINE_PERIOD), None)
    if base:
        for q in quarterly:
            q["index_value"] = round(q["median_price"] / base * 100, 2)

    # rolling 12-month: pools 4 quarters, which is what makes coverage variation
    # wash out (CI tightens from +/-5-17% to +/-3-8%)
    rolling = []
    # in-progress quarters are excluded outright — a rolling median that ends on a
    # part-quarter is not a 12-month median, and it is exactly the kind of moving
    # denominator that manufactures a "decline"
    periods = [q["period"] for q in quarterly if not q["is_in_progress"]]
    for i in range(3, len(periods)):
        window = periods[i - 3:i + 1]
        pooled = [p for (_, d), p in sales.items() if qtr(d) in window]
        if len(pooled) < MIN_N_QUARTER:
            continue
        median = int(statistics.median(pooled))
        lo, hi = bootstrap_ci(pooled)
        rolling.append({
            "period": periods[i],
            "rolling_median": median,
            "transaction_count": len(pooled),
            "ci_low": lo, "ci_high": hi,
            "ci_margin_pct": round(max(median - lo, hi - median) / median * 100, 1) if lo else None,
        })
    return quarterly, rolling


def promote_medians(gc, suburb, live, staged, quarterly, rolling, latest, union_from):
    """Field-level merge onto the live doc: MEDIANS AND CIs ONLY.

    `transaction_count` is deliberately left exactly as it is. The volume consumer
    (`market-insights.mjs:677` `salesVolume: q.transaction_count || 0`) coerces a
    missing count to ZERO, so nulling pre-union quarters would render years of
    history as a flat line at zero — worse than the coverage step it was meant to
    avoid. Volume is corrected in its own change, with the frontend, not here.

    Also preserved: `*_raw` fields (recalibrate_charts.py seeds originals off them
    on first touch — clobbering them would make the next run scale already-scaled
    values) and `in_progress_quarter`.
    """
    by_period = {q["period"]: q for q in quarterly}
    roll_by_period = {r["period"]: r for r in rolling}

    merged_series = []
    for entry in (live.get("indexed_series") or []):
        new = by_period.get(entry.get("period"))
        if new:
            entry["median_price"] = new["median_price"]
            entry["ci_low"] = new["ci_low"]
            entry["ci_high"] = new["ci_high"]
            entry["ci_margin_pct"] = new["ci_margin_pct"]
            entry["reliable"] = new["reliable"]
            entry["basis"] = new["basis"]
            entry["median_sample_n"] = new["transaction_count"]   # NOT transaction_count
            if "index_value" in new:
                entry["index_value"] = new["index_value"]
        merged_series.append(entry)
    # quarters the union found that the old Domain-only series never had
    known = {e.get("period") for e in merged_series}
    for period, new in by_period.items():
        if period not in known:
            merged_series.append({k: v for k, v in new.items() if k != "transaction_count"}
                                 | {"median_sample_n": new["transaction_count"]})
    merged_series.sort(key=lambda e: qsort(e["period"]))

    # Drop the in-progress quarter outright. build_series() already excludes it, so
    # any live entry for it would survive the merge on the OLD basis with no CI —
    # and for Robina that stale point sits ABOVE Q2 2026, which would render as the
    # rolling line ticking up when nothing of the sort happened.
    in_progress = current_quarter()
    merged_rolling = []
    for entry in (live.get("rolling_12m_median_series") or []):
        period = entry.get("period")
        if period == in_progress or entry.get("is_in_progress"):
            continue
        new = roll_by_period.get(period)
        if new:
            entry["rolling_median"] = new["rolling_median"]
            entry["ci_low"], entry["ci_high"] = new["ci_low"], new["ci_high"]
            entry["ci_margin_pct"] = new["ci_margin_pct"]
            entry["transaction_count"] = new["transaction_count"]
        elif not entry.get("ci_low"):
            # never recomputed on the union basis — leave it out rather than mix bases
            continue
        merged_rolling.append(entry)
    known_r = {e.get("period") for e in merged_rolling}
    merged_rolling += [r for p, r in roll_by_period.items() if p not in known_r]
    merged_rolling.sort(key=lambda e: qsort(e["period"]))

    # YoY recomputed from OUR rolling series — the live value was PropRadar's
    # growth_1y_pct, part of the same substitution this change removes.
    yoy = None
    if len(merged_rolling) >= 5:
        prior = merged_rolling[-5].get("rolling_median")
        if prior:
            yoy = round((latest["rolling_median"] / prior - 1) * 100, 1)

    complete = [q for q in quarterly if not q["is_in_progress"]]
    update = {
        "indexed_series": merged_series,
        "rolling_12m_median_series": merged_rolling,
        "rolling_12m_median_price": latest["rolling_median"],
        "rolling_12m_ci_low": latest["ci_low"],
        "rolling_12m_ci_high": latest["ci_high"],
        "rolling_12m_ci_margin_pct": latest["ci_margin_pct"],
        "rolling_12m_median_sample_n": latest["transaction_count"],
        "union_from": union_from,
        "volume_series_valid_from": union_from,
        "method": staged["method"],
        "coverage": staged["coverage"],
        "median_computed_at": datetime.utcnow(),
        "median_source": "domain_union_onthehouse",
        "calibration_superseded": (
            "PropRadar median anchor removed 2026-08-01 — it substituted a median "
            "from a different dwelling population (240 BW house sales vs REA's 195 "
            "at a 10% lower median; BW unit_price null). Medians now computed from "
            "the Domain union onthehouse transaction set."
        ),
    }
    if yoy is not None:
        update["rolling_12m_yoy_pct"] = yoy
    if complete:
        update["latest_price"] = complete[-1]["median_price"]
    gc[LIVE].update_one({"_id": suburb}, {"$set": update})


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--promote", action="store_true",
                    help="also write to the live collection (read the diff first)")
    args = ap.parse_args()

    client = get_client()
    gc, sm = client["Gold_Coast"], client["system_monitor"]
    union_from = qtr((datetime.utcnow() - timedelta(days=365)).strftime("%Y-%m-%d"))
    print(f"union window starts {union_from}\n")

    for suburb in SUBURBS:
        counters = defaultdict(int)
        domain = load_domain_history(gc, suburb, counters)
        oth = load_onthehouse(sm, suburb, counters)
        overlap = len(set(domain) & set(oth))
        sales = dict(domain)
        sales.update(oth)

        quarterly, rolling = build_series(sales, union_from)
        if not rolling:
            print(f"{suburb}: insufficient data")
            continue
        latest = rolling[-1]

        doc = {
            "_id": suburb, "suburb": suburb,
            "indexed_series": quarterly,
            "rolling_12m_median_series": rolling,
            "rolling_12m_median_price": latest["rolling_median"],
            "rolling_12m_ci_low": latest["ci_low"],
            "rolling_12m_ci_high": latest["ci_high"],
            "rolling_12m_ci_margin_pct": latest["ci_margin_pct"],
            "rolling_12m_transaction_count": latest["transaction_count"],
            "baseline_period": BASELINE_PERIOD,
            "union_from": union_from,
            "volume_series_valid_from": union_from,
            "method": {
                "sources": ["domain_property_timeline", "domain_sold", "onthehouse_sold"],
                "join": "address_key (unit|number|street|suburb)",
                "dwelling_filter": "shared.dwelling_type.classify_dwelling == house",
                "note": ("Volume is only comparable from union_from. Earlier quarters are "
                         "Domain-recorded only and undercount by roughly 25-55%. Quarterly "
                         "medians carry a 90% CI; those with reliable=false are too wide to "
                         "support a quarter-on-quarter claim."),
            },
            "coverage": {
                "domain_sales": len(domain), "onthehouse_sales": len(oth),
                "overlap": overlap, "union_sales": len(sales),
                "excluded_attached": counters["attached"],
                "excluded_unknown_type": counters["unknown"],
                "onthehouse_price_withheld": counters["oth_price_withheld"],
            },
            "computed_at": datetime.utcnow(),
        }
        gc[STAGING].replace_one({"_id": suburb}, doc, upsert=True)
        live = gc[LIVE].find_one({"_id": suburb}) or {}
        old = live.get("rolling_12m_median_price")

        if args.promote:
            promote_medians(gc, suburb, live, doc, quarterly, rolling, latest, union_from)
        shift = f"{(latest['rolling_median'] / old - 1) * 100:+.1f}%" if old else "n/a"
        print(f"== {suburb}")
        print(f"   12m median  {latest['rolling_median']:>10,}  "
              f"(90% CI {latest['ci_low']:,}-{latest['ci_high']:,}, "
              f"+/-{latest['ci_margin_pct']}%, n={latest['transaction_count']})")
        print(f"   live was    {old if old else 'n/a':>10}   shift {shift}")
        print(f"   sales: domain {len(domain)} + oth {len(oth)} - overlap {overlap} = {len(sales)}")
        print(f"   excluded: attached {counters['attached']}, unknown-type {counters['unknown']}, "
              f"oth price-withheld {counters['oth_price_withheld']}")
        unreliable = [q["period"] for q in quarterly[-6:] if not q["reliable"]]
        print(f"   last 6 quarters too noisy to publish QoQ: {unreliable or 'none'}\n")

    print(f"staged -> Gold_Coast.{STAGING}" + ("  (AND PROMOTED TO LIVE)" if args.promote else ""))


if __name__ == "__main__":
    main()
