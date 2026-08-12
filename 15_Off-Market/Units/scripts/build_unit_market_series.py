#!/usr/bin/env python3
"""build_unit_market_series.py — the attached-dwelling market series. (Plan D1)

WHY
---
There is no unit price series anywhere in the estate. `suburb_median_prices` is 76
documents, every one `property_type: "House"`; `precomputed_indexed_prices`,
`precomputed_market_charts` and `precomputed_active_listings` are keyed by suburb with
no dwelling dimension at all. So a unit page today shows the reader the HOUSE median,
HOUSE days-on-market and a HOUSE listing count, framed as "homes like yours".

This one build closes three things at once:
  1. the live editorial defect on unit pages,
  2. the market section of the unit report,
  3. the time-deflator the unit valuation method needs (without it, the method has to
     borrow the house index, which is a known and systematic source of error).

METHOD — deliberately the same shape as `scripts/precompute_union_prices.py`, which is
the house series, so the two are comparable rather than merely adjacent:
  * dwelling class via `shared.dwelling_type.classify_dwelling` (address-first),
  * sales from BOTH the embedded Domain property timeline and the sold-listing record,
  * deduped on (address_key, date) so a property in both is counted once,
  * quarterly medians plus a 12-month rolling median.

⚠ WHAT THIS DOES NOT PUBLISH: sale VOLUME. Domain's sold capture misses an estimated
40-50% of transactions, and that undercapture is not uniform over time, so a volume
series would show movement that is ours, not the market's. Medians survive
undercapture far better than counts do. See memory `data_source_undercapture_reset`.

⚠ SMALL-SAMPLE SUPPRESSION: a quarter with fewer than MIN_Q sales is retained in the
data but flagged `thin`. A median over 4 sales is not a market reading, and the house
series has already been burned once by publishing a 14-sale part-quarter as fact.
"""
from __future__ import annotations

import argparse
import datetime as dt
import re
import statistics as st
import sys
from collections import defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

try:
    from shared.env import load_env
    load_env()
except Exception:
    pass

sys.path.insert(0, str(Path(__file__).resolve().parent))
from shared.db import get_client                        # noqa: E402
from shared.dwelling_type import classify_dwelling       # noqa: E402
from scripts.job_status import job_run                   # noqa: E402

SUBURBS = ["robina", "varsity_lakes", "burleigh_waters"]
MIN_Q = 8          # below this a quarter is flagged thin, never silently dropped
ROLL_MIN = 12      # rolling window needs this many sales to publish a median


# ⚠ ONE definition of "is this a sale", imported — not a third copy. The duplicate that
# lived here applied its sanity band only to the string branch, so weekly rents stored as
# numbers were counted as sales and moved the median.
from unit_valuation import sale_price as parse_price   # noqa: E402


def quarter(date_str):
    m = re.match(r"(\d{4})-(\d{2})", str(date_str or ""))
    if not m:
        return None
    y, mo = int(m.group(1)), int(m.group(2))
    return f"{y}-Q{(mo - 1) // 3 + 1}"


def addr_key(doc):
    a = (doc.get("street_address") or doc.get("address")
         or doc.get("complete_address") or "")
    return re.sub(r"[^a-z0-9]+", "", a.lower()) or None


def collect(gc, suburb):
    """Every attached sale we hold, from timelines AND sold records, deduped."""
    proj = {"street_address": 1, "address": 1, "complete_address": 1, "suburb": 1,
            "property_type": 1, "classified_property_type": 1, "sale_price": 1,
            "sold_date": 1, "sale_date": 1, "listing_status": 1, "bedrooms": 1,
            "days_on_domain": 1, "days_on_market": 1,
            "scraped_data.features.property_type": 1,
            "scraped_data.property_timeline": 1,
            "scraped_data_v2.property_type": 1,
            "enriched_data.transactions": 1}
    seen, sales, doms = set(), [], []
    counters = defaultdict(int)
    for d in gc[suburb].find({}, proj):
        eff = d.get("street_address") or d.get("address") or d.get("complete_address") or ""
        bucket = classify_dwelling({**d, "street_address": eff})
        counters[bucket] += 1
        if bucket != "attached":
            continue
        key = addr_key(d)

        def add(date, price, beds):
            date = str(date or "")[:10]
            p = parse_price(price)
            if len(date) < 7 or not p:
                return
            sig = (key, date[:7], int(p))
            if sig in seen:
                counters["dedup"] += 1
                return
            seen.add(sig)
            sales.append({"date": date, "price": p, "q": quarter(date), "beds": beds})

        for e in ((d.get("scraped_data") or {}).get("property_timeline") or []):
            if isinstance(e, dict) and e.get("is_sold"):
                add(e.get("date"), e.get("price"), d.get("bedrooms"))
        for t in ((d.get("enriched_data") or {}).get("transactions") or []):
            if isinstance(t, dict):
                add(t.get("date"), t.get("price"), d.get("bedrooms"))
        if d.get("listing_status") == "sold":
            add(d.get("sold_date") or d.get("sale_date"), d.get("sale_price"), d.get("bedrooms"))
            dom = d.get("days_on_domain") or d.get("days_on_market")
            sd = str(d.get("sold_date") or "")[:10]
            if isinstance(dom, (int, float)) and 0 < dom < 730 and len(sd) == 10:
                doms.append({"days": float(dom), "q": quarter(sd)})
    return sales, doms, counters


def series(sales, price_key="price"):
    by_q = defaultdict(list)
    for s in sales:
        if s["q"]:
            by_q[s["q"]].append(s[price_key])
    qs = sorted(by_q)
    out = []
    for q in qs:
        v = sorted(by_q[q])
        out.append({"period": q, "median": int(st.median(v)), "count": len(v),
                    "thin": len(v) < MIN_Q})
    # 12-month rolling: this quarter plus the previous three.
    roll = []
    for i, q in enumerate(qs):
        window = [p for qq in qs[max(0, i - 3):i + 1] for p in by_q[qq]]
        if len(window) >= ROLL_MIN:
            roll.append({"period": q, "rolling_median": int(st.median(window)),
                         "count": len(window)})
    return out, roll


def bedroom_series(sales):
    """Per-bedroom rolling indices — the honest deflator.

    ⚠ THE ALL-ATTACHED MEDIAN IS MIX-CONTAMINATED AND MUST NOT BE USED TO DEFLATE.
    Measured on Robina, 2024-Q2 -> 2026-Q2:

        all attached  +35%      <- rises FASTER than either component
        2-bed only    +18%
        3-bed only    +29%

    That is a mix shift toward larger dwellings, not price growth, and it is Simpson's
    paradox in miniature. Deflating a 2-bed sale by the all-attached index inflated a
    real 2024 sale by 43% when 2-bed growth over the same window was 18%. Any
    consumer bringing a past sale to today MUST prefer the bedroom-matched series and
    fall back to `all` only when the matched one is too thin.
    """
    out = {}
    for bed in (1, 2, 3, 4):
        rows = [s for s in sales if s.get("beds") == bed]
        if len(rows) < ROLL_MIN * 2:
            continue
        _q, roll = series(rows)
        if roll:
            out[str(bed)] = roll
    return out


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--dry-run", action="store_true")
    args = ap.parse_args()

    with job_run("units_market_series", cadence_hours=168,
                 title="Units — attached price / DOM series") as beat:
        client = get_client()
        gc = client["Gold_Coast"]
        wrote = 0
        total_sales = 0
        summary = {}
        for suburb in SUBURBS:
            sales, doms, counters = collect(gc, suburb)
            total_sales += len(sales)
            q, roll = series(sales)
            per_bed = bedroom_series(sales)
            # The current quarter is partial - its rolling window is short and its
            # median moves on whatever happened to settle. Never headline it.
            this_q = quarter(dt.date.today().isoformat())
            complete = [r for r in roll if r["period"] != this_q]
            active = 0
            for d in gc[suburb].find({"listing_status": "for_sale"},
                                     {"street_address": 1, "address": 1, "complete_address": 1,
                                      "property_type": 1, "classified_property_type": 1,
                                      "scraped_data.features.property_type": 1,
                                      "scraped_data_v2.property_type": 1}):
                eff = d.get("street_address") or d.get("address") or d.get("complete_address") or ""
                if classify_dwelling({**d, "street_address": eff}) == "attached":
                    active += 1
            dom_recent = [x["days"] for x in doms if x["q"] and x["q"] >= "2025-Q3"]
            latest = complete[-1] if complete else (roll[-1] if roll else None)
            prior = next((r for r in reversed(complete)
                          if latest and r["period"][:4] == str(int(latest["period"][:4]) - 1)
                          and r["period"][-2:] == latest["period"][-2:]), None)
            doc = {
                "_id": suburb,
                "suburb_key": suburb,
                "dwelling_class": "attached",
                "quarterly": q,
                "rolling_12m": roll,
                "rolling_12m_by_bedrooms": per_bed,
                "in_progress_period": this_q,
                "latest_rolling_median": latest["rolling_median"] if latest else None,
                "latest_period": latest["period"] if latest else None,
                "yoy_pct": (round((latest["rolling_median"] / prior["rolling_median"] - 1) * 100, 1)
                            if latest and prior else None),
                "median_days_on_market": (round(st.median(dom_recent))
                                          if len(dom_recent) >= 5 else None),
                "dom_sample": len(dom_recent),
                "active_listings": active,
                "n_sales": len(sales),
                "basis": ("Domain property timelines ∪ enriched transactions ∪ sold listings, "
                          "deduped on address+month+price; dwelling class via "
                          "shared.dwelling_type.classify_dwelling == attached"),
                "caveats": [
                    "Medians only — sale VOLUME is not published; Domain sold capture "
                    "misses an estimated 40-50% of transactions and not uniformly over time.",
                    f"Quarters with fewer than {MIN_Q} sales are flagged `thin`.",
                    "Attached covers units, apartments, townhouses, villas and duplexes "
                    "together; it is not an apartments-only series.",
                    "⚠ The headline all-attached median is MIX-SENSITIVE. Measured on "
                    "Robina 2024-Q2→2026-Q2 it rose 35% while 2-bed rose 18% and 3-bed "
                    "29% — it rises faster than either component because the mix is "
                    "shifting toward larger dwellings. Use `rolling_12m_by_bedrooms` "
                    "for any time adjustment; the headline is context only.",
                    "The current quarter is partial and is excluded from the headline "
                    "and the year-on-year figure.",
                ],
                "generated_at": dt.datetime.utcnow(),
            }
            summary[suburb] = {"sales": len(sales), "quarters": len(q),
                               "median": doc["latest_rolling_median"],
                               "dom": doc["median_days_on_market"], "active": active}
            print(f"  {suburb}: {len(sales):5d} sales · {len(q)} quarters · "
                  f"latest rolling median "
                  f"{('$%s' % format(doc['latest_rolling_median'], ',')) if latest else '—'}"
                  f" ({doc['latest_period']}) · DOM {doc['median_days_on_market']} "
                  f"(n={doc['dom_sample']}) · {active} active")
            if not args.dry_run:
                gc["unit_market_series"].update_one({"_id": suburb}, {"$set": doc}, upsert=True)
                wrote += 1

        beat.metrics = {"suburbs": wrote, "sales": total_sales,
                        **{f"{k}_median": v["median"] for k, v in summary.items() if v["median"]}}
        beat.detail = f"{wrote} suburbs, {total_sales} attached sales"

        # Rule 7b — the zero-output path. Attached stock exists in all three suburbs;
        # zero sales means the classifier or the read broke, not that nothing sold.
        if total_sales == 0:
            raise RuntimeError("0 attached sales collected across 3 suburbs — the "
                               "classifier or the projection is broken, not the market")
        missing = [s for s, v in summary.items() if not v["median"]]
        if missing:
            raise RuntimeError(f"no rolling median produced for {missing} — "
                               f"refusing to record success on a partial series")
    return 0


if __name__ == "__main__":
    sys.exit(main())
