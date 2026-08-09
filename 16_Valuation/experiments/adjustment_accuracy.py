#!/usr/bin/env python3
"""
adjustment_accuracy.py — does ADJUSTING comparables make the answer more
ACCURATE, and by how much?

WHY THIS EXISTS
───────────────────────────────────────────────────────────────────────────────
We have a measured figure for adjusting comparables — "narrows the range by
about 40%" (n=512, RESULT_dispersion_512.md §3). That is a PRECISION result. It
says the adjusted comps agree with each other more tightly than the raw ones do.
It says nothing about whether the answer moved closer to the eventual sale
price, and a narrow range can be narrowly wrong.

The only accuracy contest we have run is Fields vs an agent's 3-comp valuation,
which was a dead heat (§1) — a DIFFERENT question, because it changes the comp
set as well as the arithmetic.

Will's question is the narrower and fairer one: take the same homes, the same
comparables, the same weights, and change ONE thing — whether each comparable is
adjusted for how it differs from the subject. That isolates the adjustment.

THE TEST
───────────────────────────────────────────────────────────────────────────────
For each sold home, from one backtest run (subject excluded by _id, every sale
on/after its date dropped):

    unadjusted estimate = Σ(raw sale price   × weight)   ← label-matching
    adjusted   estimate = Σ(adjusted price   × weight)   ← our method

Both use the SAME comparables and the SAME weights, so the only difference is
the per-feature adjustment. Error is |estimate − actual sale price| ÷ actual.

⚠ THE UNADJUSTED ARM IS DELIBERATELY GENEROUS. It inherits our comp SELECTION,
which already screens for similar land, floor area and recency. A real
label-match on "4 bed, 2 bath, roughly this size" would be a weaker baseline, so
whatever improvement this measures is a LOWER BOUND on the value of adjusting.
Any published figure must be quoted as such.

    python3 adjustment_accuracy.py --limit 25      # smoke test
    python3 adjustment_accuracy.py                 # full run
"""
import argparse
import json
import os
import sys
import time
from statistics import mean, median

sys.path.insert(0, "/home/fields/Fields_Orchestrator/scripts")
sys.path.insert(0, "/home/fields/Feilds_Website/07_Valuation_Comps")
sys.path.insert(0, "/home/fields/Fields_Orchestrator/15_Off-Market/Page_Redesign_V4/Prototypes")

from dotenv import load_dotenv
from pymongo import MongoClient

import valuation_backtest as vb
from precompute_valuations import resolve_land_size, resolve_floor_area

SUBURBS = ["robina", "varsity_lakes", "burleigh_waters"]


def weighted(points, key):
    """Σ(value × normalised weight) ÷ Σ(weight) over the comparables."""
    num = den = 0.0
    for p in points:
        w = ((p.get("weight") or {}).get("normalized")) or 0
        if not w:
            continue
        if key == "raw":
            v = p.get("price")
        else:
            v = (p.get("adjustment_result") or {}).get("adjusted_price")
        if not v:
            continue
        num += v * w
        den += w
    return (num / den) if den else None


def pctl(vals, q):
    s = sorted(vals)
    return s[min(len(s) - 1, int(q * len(s)))]


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--limit", type=int)
    ap.add_argument("--min-price", type=int, default=1_000_000)
    ap.add_argument("--max-price", type=int, default=2_000_000)
    ap.add_argument("--out", default="adjustment_accuracy.jsonl")
    args = ap.parse_args()

    load_dotenv("/home/fields/Fields_Orchestrator/.env")
    client = MongoClient(os.environ["COSMOS_CONNECTION_STRING"],
                         serverSelectionTimeoutMS=30000, socketTimeoutMS=120000)
    db = client["Gold_Coast"]

    sold_by_suburb, coords, timelines = {}, {}, {}
    median_cache, street_cache = {}, {}
    for sub in SUBURBS:
        sold_by_suburb[sub] = list(db[sub].find({"listing_status": "sold"}))

    subjects = []
    for sub in SUBURBS:
        for doc in sold_by_suburb[sub]:
            price = vb.extract_sale_price(doc)
            if not price or not (args.min_price <= price <= args.max_price):
                continue
            if doc.get("property_type") != "House":
                continue
            if not resolve_floor_area(doc) or not resolve_land_size(doc):
                continue
            doc["_collection"] = sub
            subjects.append(doc)
    if args.limit:
        subjects = subjects[: args.limit]
    print(f"\n{len(subjects)} eligible sold houses (${args.min_price:,}-${args.max_price:,})\n")

    rows, t0 = [], time.time()
    with open(args.out, "w") as out:
        for i, subject in enumerate(subjects):
            sub = subject["_collection"]
            actual = vb.extract_sale_price(subject)
            try:
                res = vb.backtest_single_property(
                    db, subject, sold_by_suburb.get(sub, []), sold_by_suburb,
                    coords, timelines,
                    median_cache=median_cache, street_premium_cache=street_cache)
            except Exception as e:
                print(f"  [{i}] {str(subject.get('address'))[:40]} ERROR {e}")
                continue
            if not res or not res.get("included_points"):
                continue
            pts = res["included_points"]
            raw_est = weighted(pts, "raw")
            adj_est = weighted(pts, "adj")
            if not raw_est or not adj_est:
                continue
            rec = {
                "id": str(subject["_id"]),
                "suburb": sub,
                "address": subject.get("address"),
                "actual": actual,
                "n_comps": len(pts),
                "raw_est": raw_est,
                "adj_est": adj_est,
                "raw_err": abs(raw_est - actual) / actual * 100,
                "adj_err": abs(adj_est - actual) / actual * 100,
            }
            rows.append(rec)
            out.write(json.dumps(rec) + "\n")
            out.flush()
            if len(rows) % 25 == 0:
                print(f"  {len(rows)} done ({(time.time()-t0)/60:.1f} min)")

    # ── Rule 7b: an empty result is a failure, not a finding ──────────────
    if not rows:
        raise RuntimeError("0 homes produced both an adjusted and an unadjusted "
                           "estimate — the harness is broken, not the data")

    raw = [r["raw_err"] for r in rows]
    adj = [r["adj_err"] for r in rows]
    better = sum(1 for r in rows if r["adj_err"] < r["raw_err"])
    n = len(rows)

    print(f"\n{'='*66}\nADJUSTED vs UNADJUSTED — same comps, same weights   n={n}\n{'='*66}")
    print(f"  {'':22}{'unadjusted':>12}{'adjusted':>12}{'change':>12}")
    for label, fn in (("mean error", mean), ("median error", median)):
        a, b = fn(raw), fn(adj)
        print(f"  {label:22}{a:>11.2f}%{b:>11.2f}%{(b-a)/a*100:>11.1f}%")
    for q, nm in ((0.75, "p75 error"), (0.90, "p90 error")):
        a, b = pctl(raw, q), pctl(adj, q)
        print(f"  {nm:22}{a:>11.2f}%{b:>11.2f}%{(b-a)/a*100:>11.1f}%")
    for t in (10, 15):
        a = sum(1 for e in raw if e <= t) / n * 100
        b = sum(1 for e in adj if e <= t) / n * 100
        print(f"  {'within '+str(t)+'%':22}{a:>11.1f}%{b:>11.1f}%{b-a:>+11.1f}pp")
    print(f"\n  adjusting improved the answer on {better}/{n} homes ({better/n*100:.1f}%)")
    print(f"  mean error cut from {mean(raw):.2f}% to {mean(adj):.2f}% "
          f"— a {(mean(raw)-mean(adj))/mean(raw)*100:.1f}% reduction in average error")


if __name__ == "__main__":
    main()
