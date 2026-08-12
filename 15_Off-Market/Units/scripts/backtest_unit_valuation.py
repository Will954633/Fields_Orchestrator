#!/usr/bin/env python3
"""backtest_unit_valuation.py — does the unit method actually work? (Plan F7)

⚠ THIS IS THE GATE. Nothing publishes a figure until this passes. The page currently
carries "±19.8%, not publishable yet" precisely because the only number we had came from
a leave-one-out check, not a production-shaped test.

WHAT "PRODUCTION-SHAPED" MEANS HERE, AND WHY THE EARLIER NUMBER DOES NOT COUNT
-----------------------------------------------------------------------------
The leave-one-out check let a subject be valued using sales that happened AFTER it. In
production the future does not exist. That is target leakage and it flatters the result.

This test instead, for each sold attached dwelling:
  1. takes its actual sale as the answer, hidden from the method;
  2. rebuilds the comparable pool using ONLY sales dated strictly BEFORE that sale;
  3. deflates those comps to the SALE'S OWN quarter, not to today — valuing a 2024 sale
     with a 2026 index is the same leak wearing a different hat;
  4. applies the same tiers, the same MIN_COMPS, the same MAX_UPLIFT cap as production;
  5. compares the prediction to what the home actually fetched.

Also excluded, deliberately:
  * the subject's own prior sales — a home's last sale is the single strongest predictor
    of its next one, and production usually has it, but including it here would measure
    "can we read a transaction record" rather than "do comparables work";
  * anything the production path would refuse. A backtest that scores only the easy
    subjects reports the accuracy of an easier product than the one we ship.

OUTPUT is per (suburb, bedrooms) as well as overall, because that is the key `ACCURACY`
must be widened to (plan F8) — a single blended figure would let one cohort's track
record be lent to another, which has already happened once on the house side.
"""
from __future__ import annotations

import argparse
import json
import re
import statistics as st
import sys
from collections import defaultdict
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent.parent.parent
for p in (str(ROOT), str(HERE)):
    if p not in sys.path:
        sys.path.insert(0, p)

try:
    from shared.env import load_env
    load_env()
except Exception:
    pass

from shared.db import get_client                       # noqa: E402
from shared.dwelling_type import classify_dwelling      # noqa: E402
from unit_valuation import (                            # noqa: E402
    MIN_COMPS, PREFERRED_COMPS, MAX_UPLIFT, MAX_AGE_YEARS, bedrooms_of, sale_price,
    plausible_for_scheme,
)

SUBURBS = ["robina", "varsity_lakes", "burleigh_waters"]
PROJ = {"street_address": 1, "address": 1, "complete_address": 1, "property_type": 1,
        "classified_property_type": 1, "bedrooms": 1, "listing_status": 1,
        "sale_price": 1, "sold_date": 1, "complex_plan": 1, "complex_cms": 1,
        "complex_subtype": 1, "scraped_data.features.property_type": 1,
        "scraped_data_v2.property_type": 1, "scraped_data.features.bedrooms": 1,
        "scraped_data_v2.bedrooms": 1,
        "scraped_data_apr01_recovered.features.bedrooms": 1,
        "property_valuation_data.layout.number_of_bedrooms": 1,
        "scraped_data.property_timeline": 1, "enriched_data.transactions": 1}


# Same single definition the method uses — the backtest's answer key must be filtered
# exactly as production filters its comparables, or it scores against rents.
num = sale_price


def quarter(s):
    m = re.match(r"(\d{4})-(\d{2})", str(s or ""))
    return f"{m.group(1)}-Q{(int(m.group(2)) - 1) // 3 + 1}" if m else None


def year(s):
    m = re.search(r"(19|20)\d{2}", str(s or ""))
    return int(m.group(0)) if m else None


def sales_of(doc):
    """Every priced, dated sale on a document."""
    out = []
    for t in ((doc.get("enriched_data") or {}).get("transactions") or []):
        if isinstance(t, dict):
            out.append((str(t.get("date") or "")[:10], num(t.get("price"))))
    for ev in ((doc.get("scraped_data") or {}).get("property_timeline") or []):
        if isinstance(ev, dict) and ev.get("is_sold"):
            out.append((str(ev.get("date") or "")[:10], num(ev.get("price"))))
    if doc.get("listing_status") == "sold":
        out.append((str(doc.get("sold_date") or "")[:10], num(doc.get("sale_price"))))
    return [(d, p) for d, p in out if p and len(d) >= 7]


def load(gc, suburb):
    """All attached dwellings with their sales and scheme keys."""
    rows = []
    for d in gc[suburb].find({}, PROJ):
        eff = (d.get("street_address") or d.get("address")
               or d.get("complete_address") or "")
        if classify_dwelling({**d, "street_address": eff}) != "attached":
            continue
        s = sales_of(d)
        if not s:
            continue
        rows.append({"id": d["_id"], "addr": eff, "beds": bedrooms_of(d),
                     "cms": d.get("complex_cms"), "plan": d.get("complex_plan"),
                     "subtype": d.get("complex_subtype"), "sales": sorted(set(s))})
    # ⚠ The ANSWER KEY needs the same filter as the comparables. A "$37,200 sale" in a
    # $900k building is not a wrong prediction, it is a wrong answer — and scoring
    # against it reported an MAE of 21.8% where the median error was 6.5%.
    for r in rows:
        pool = [p for _d, p in r["sales"]]
        if len(pool) >= 2:
            med = st.median(pool)
            r["sales"] = [(d, p) for d, p in r["sales"]
                          if plausible_for_scheme(p, med)] or r["sales"]
    by_scheme = defaultdict(list)
    for r in rows:
        key = r.get("cms") or r.get("plan")
        if key:
            by_scheme[key] += [p for _d, p in r["sales"]]
    for r in rows:
        key = r.get("cms") or r.get("plan")
        med = st.median(by_scheme[key]) if len(by_scheme.get(key) or []) >= 4 else None
        r["sales"] = [(d, p) for d, p in r["sales"] if plausible_for_scheme(p, med)]
    return [r for r in rows if r["sales"]]


def build_index(rows, by_beds=False):
    """Quarterly rolling median from the same sales the method uses, so the backtest
    deflates on the same basis production does."""
    buckets = defaultdict(lambda: defaultdict(list))
    for r in rows:
        key = str(r["beds"]) if (by_beds and r["beds"]) else "all"
        for date, price in r["sales"]:
            q = quarter(date)
            if q:
                buckets[key][q].append(price)
    out = {}
    for key, byq in buckets.items():
        qs = sorted(byq)
        roll = {}
        for i, q in enumerate(qs):
            win = [p for qq in qs[max(0, i - 3):i + 1] for p in byq[qq]]
            if len(win) >= 12:
                roll[q] = st.median(win)
        if len(roll) >= 8:
            out[key] = roll
    return out


def deflate_to(idx, price, from_q, to_q):
    """Bring a sale from one quarter to another. Returns (value, factor) or (None, None).
    ⚠ `to_q` is the SUBJECT'S sale quarter — never today. Deflating a 2024 comparable
    forward to 2026 to predict a 2024 sale would use two years the method could not
    have had."""
    if not idx:
        return None, None
    ps = sorted(idx)
    def at(q):
        if q in idx:
            return idx[q]
        earlier = [x for x in ps if x <= q]
        return idx[earlier[-1]] if earlier else None
    a, b = at(from_q), at(to_q)
    if not a or not b:
        return None, None
    return price * (b / a), b / a


def predict(subject, sale_q, rows_by_cms, rows_by_plan, rows_by_subtype, idx_all, idx_beds):
    """Reproduce production's tiers using ONLY sales strictly before `sale_q`."""
    beds = subject["beds"]
    idx = idx_beds.get(str(beds)) if beds else None
    idx = idx or idx_all.get("all")

    pool_src = (rows_by_cms.get(subject["cms"]) if subject.get("cms")
                else rows_by_plan.get(subject.get("plan")))
    def gather(src, need_beds):
        out = []
        for r in (src or []):
            if r["id"] == subject["id"]:
                continue                       # never the subject's own history
            if need_beds and r["beds"] != beds:
                continue
            for date, price in r["sales"]:
                q = quarter(date)
                if not q or q >= sale_q:
                    continue                   # the future does not exist
                if year(date) and int(sale_q[:4]) - year(date) > MAX_AGE_YEARS:
                    continue
                out.append((q, price, date, r["addr"]))
        return sorted(out, key=lambda x: x[2], reverse=True)

    for src, need_beds, tier in (
            (pool_src, True, "same_complex_same_beds"),
            (pool_src, False, "same_complex_any_beds"),
            (rows_by_subtype.get(subject.get("subtype")) if beds else None, True,
             "same_subtype_same_beds_suburb")):
        cands = gather(src, need_beds)
        adj = []
        for q, price, _d, _a in cands:
            v, f = deflate_to(idx, price, q, sale_q)
            if v is None or (f is not None and f - 1 > MAX_UPLIFT):
                continue
            adj.append(v)
            if len(adj) >= PREFERRED_COMPS:
                break
        if len(adj) >= MIN_COMPS:
            return st.median(adj), tier, len(adj)
    return None, None, 0


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--from-year", type=int, default=2023,
                    help="only score sales from this year on — recent market only")
    ap.add_argument("--out", default=str(HERE.parent / "artifacts" / "backtest_units.json"))
    args = ap.parse_args()

    gc = get_client()["Gold_Coast"]
    overall, per_sub, per_bed = [], defaultdict(list), defaultdict(list)
    tier_counts = defaultdict(int)
    scored = skipped = 0

    for suburb in SUBURBS:
        rows = load(gc, suburb)
        by_cms, by_plan, by_sub = defaultdict(list), defaultdict(list), defaultdict(list)
        for r in rows:
            if r.get("cms"):
                by_cms[r["cms"]].append(r)
            if r.get("plan"):
                by_plan[r["plan"]].append(r)
            if r.get("subtype"):
                by_sub[r["subtype"]].append(r)
        idx_all = build_index(rows, by_beds=False)
        idx_beds = build_index(rows, by_beds=True)

        for r in rows:
            for date, actual in r["sales"]:
                if not year(date) or year(date) < args.from_year:
                    continue
                q = quarter(date)
                if not q:
                    continue
                pred, tier, n = predict(r, q, by_cms, by_plan, by_sub, idx_all, idx_beds)
                if pred is None:
                    skipped += 1
                    continue
                err = abs(pred - actual) / actual * 100
                scored += 1
                tier_counts[tier] += 1
                overall.append(err)
                per_sub[suburb].append(err)
                if r["beds"]:
                    per_bed[f"{suburb}:{r['beds']}bed"].append(err)

    def stats(errs):
        if len(errs) < 20:
            return {"n": len(errs), "insufficient": True}
        e = sorted(errs)
        return {"n": len(e), "median": round(st.median(e), 2), "mae": round(st.mean(e), 2),
                "within10": round(sum(1 for x in e if x <= 10) / len(e) * 100, 1),
                "within20": round(sum(1 for x in e if x <= 20) / len(e) * 100, 1),
                "p80": round(e[int(len(e) * 0.8)], 2)}

    res = {"scored": scored, "refused": skipped,
           "coverage_pct": round(scored / max(1, scored + skipped) * 100, 1),
           "from_year": args.from_year, "overall": stats(overall),
           "by_suburb": {k: stats(v) for k, v in per_sub.items()},
           "by_suburb_bedrooms": {k: stats(v) for k, v in sorted(per_bed.items())},
           "tiers": dict(tier_counts),
           "method": ("leakage-free: comps strictly before the subject's sale quarter, "
                      "deflated to that quarter, subject's own history excluded, "
                      "production tiers/MIN_COMPS/MAX_UPLIFT applied")}
    Path(args.out).parent.mkdir(parents=True, exist_ok=True)
    Path(args.out).write_text(json.dumps(res, indent=2))

    o = res["overall"]
    print(f"\n  LEAKAGE-FREE BACKTEST — sales from {args.from_year}")
    print(f"  scored {scored:,} · refused {skipped:,} · coverage {res['coverage_pct']}%\n")
    if o.get("insufficient"):
        print("  overall: insufficient sample")
    else:
        print(f"  {'cohort':26s} {'n':>6s} {'median':>8s} {'MAE':>7s} {'<10%':>7s} {'<20%':>7s} {'P80':>7s}")
        print(f"  {'OVERALL':26s} {o['n']:>6,} {o['median']:>7.1f}% {o['mae']:>6.1f}% "
              f"{o['within10']:>6.1f}% {o['within20']:>6.1f}% {o['p80']:>6.1f}%")
        for k, v in res["by_suburb"].items():
            if not v.get("insufficient"):
                print(f"  {k:26s} {v['n']:>6,} {v['median']:>7.1f}% {v['mae']:>6.1f}% "
                      f"{v['within10']:>6.1f}% {v['within20']:>6.1f}% {v['p80']:>6.1f}%")
    print(f"\n  house baseline (in-envelope): median 8.2% · MAE 10.5% · within-10% 59%")
    print(f"  written -> {args.out}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
