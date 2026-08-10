#!/usr/bin/env python3
"""
lambda_production.py — how much adjustment is optimal, measured the way
PRODUCTION reconciles rather than the way the backtest does.

WHY A SECOND HARNESS
───────────────────────────────────────────────────────────────────────────────
`adjustment_accuracy.py` swept adjustment strength over `included_points` — the
8 displayed comparables. Production does not do that. `precompute_valuations.
calculate_confidence()` is handed the FULL candidate pool, and every point in it
carries a normalised weight. Reconciling over 8 instead of ~49 is one of the two
changes documented as producing the current published figures (the other is the
λ=0.80 reliability shrinkage), so a sweep over the 8 measures a method we do not
ship.

⚠ `valuation_backtest.py` does neither. Line 528 reconciles from
`included_points`, and `apply_adjustment_reliability` is never imported. So the
backtest as it stands cannot reproduce the configuration our own accuracy
document describes — which is what this script exists to settle.

⚠ RE-RUNNING THIS AFTER 2026-08-10 NEEDS ONE CORRECTION
───────────────────────────────────────────────────────────────────────────────
`valuation_backtest.py` was aligned with production on 2026-08-10 and now applies
`apply_adjustment_reliability` itself. So `adjustment_result.adjusted_price` is
already shrunk to lambda=0.80, and sweeping over it sweeps 0 -> 0.8, not 0 -> 1.
The jsonl this script's published result came from predates that fix, so its
`adj_est` IS full strength and the recorded sweep stands. To re-run, either
divide the adjustment back out by `_ADJUSTMENT_RELIABILITY` or temporarily set
that constant to 1.0 — otherwise every lambda on the axis is really 0.8x itself.

THE SWEEP IS ANALYTIC, AND EXACTLY EQUIVALENT
───────────────────────────────────────────────────────────────────────────────
Shrinkage is linear in the adjustment, so shrinking each comparable and then
weighting is identical to weighting and then shrinking:

    Σ wᵢ·[rawᵢ + λ(adjᵢ − rawᵢ)]  ≡  Σwᵢ·rawᵢ + λ(Σwᵢ·adjᵢ − Σwᵢ·rawᵢ)

so one backtest run per home yields every λ. No re-running the pipeline 11 times.

⚠ SUBURB CALIBRATION IS APPLIED, because the shipped figure carries it — and it
is a multiplier, so it does not cancel out of an error comparison.

    python3 lambda_production.py --limit 25
    python3 lambda_production.py
"""
import argparse, json, os, sys, time
from statistics import mean, median

sys.path.insert(0, "/home/fields/Fields_Orchestrator/scripts")
sys.path.insert(0, "/home/fields/Feilds_Website/07_Valuation_Comps")

from dotenv import load_dotenv
from pymongo import MongoClient

import valuation_backtest as vb
from precompute_valuations import (
    resolve_land_size, resolve_floor_area, normalize_weights, _SUBURB_CALIBRATION,
)

SUBURBS = ["robina", "varsity_lakes", "burleigh_waters"]


def pool_estimates(all_points, suburb):
    """(unadjusted, fully-adjusted) weighted means over the FULL candidate pool,
    normalised and calibrated exactly as production does."""
    pts = [p for p in all_points
           if (p.get("adjustment_result") or {}).get("adjusted_price") and p.get("price")]
    if len(pts) < 2:
        return None, None
    normalize_weights(pts)          # production normalises over what it reconciles
    cal = _SUBURB_CALIBRATION.get(suburb, 1.0)
    raw = adj = den = 0.0
    for p in pts:
        w = (p.get("weight") or {}).get("normalized") or 0
        if not w:
            continue
        raw += p["price"] * w
        adj += p["adjustment_result"]["adjusted_price"] * w
        den += w
    if not den:
        return None, None
    return raw / den * cal, adj / den * cal


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--limit", type=int)
    ap.add_argument("--out", default="lambda_production.jsonl")
    args = ap.parse_args()

    load_dotenv("/home/fields/Fields_Orchestrator/.env")
    db = MongoClient(os.environ["COSMOS_CONNECTION_STRING"],
                     serverSelectionTimeoutMS=30000, socketTimeoutMS=120000)["Gold_Coast"]

    sold_by_suburb = {s: list(db[s].find({"listing_status": "sold"})) for s in SUBURBS}
    subjects = []
    for sub in SUBURBS:
        for doc in sold_by_suburb[sub]:
            price = vb.extract_sale_price(doc)
            if not price or not (1_000_000 <= price <= 2_000_000):
                continue
            if doc.get("property_type") != "House":
                continue
            if not resolve_floor_area(doc) or not resolve_land_size(doc):
                continue
            doc["_collection"] = sub
            subjects.append(doc)
    if args.limit:
        subjects = subjects[: args.limit]
    print(f"\n{len(subjects)} eligible sold houses\n")

    rows, t0 = [], time.time()
    with open(args.out, "w") as out:
        for i, subject in enumerate(subjects):
            sub = subject["_collection"]
            actual = vb.extract_sale_price(subject)
            try:
                res = vb.backtest_single_property(
                    db, subject, sold_by_suburb.get(sub, []), sold_by_suburb, {}, {},
                    median_cache={}, street_premium_cache={})
            except Exception as e:
                print(f"  [{i}] ERROR {e}")
                continue
            if not res or not res.get("all_points"):
                continue
            raw_est, adj_est = pool_estimates(res["all_points"], sub)
            if not raw_est or not adj_est:
                continue
            rec = {"id": str(subject["_id"]), "suburb": sub, "actual": actual,
                   "n_pool": len(res["all_points"]), "raw_est": raw_est, "adj_est": adj_est}
            rows.append(rec)
            out.write(json.dumps(rec) + "\n")
            out.flush()
            if len(rows) % 50 == 0:
                print(f"  {len(rows)} done ({(time.time()-t0)/60:.1f} min)")

    # Rule 7b — an empty result is a broken harness, not a finding.
    if not rows:
        raise RuntimeError("0 homes produced a pool estimate — the harness is broken")

    n = len(rows)

    def at(lam):
        errs, devs = [], []
        for r in rows:
            est = r["raw_est"] + lam * (r["adj_est"] - r["raw_est"])
            errs.append(abs(est - r["actual"]) / r["actual"] * 100)
            devs.append(abs(r["actual"] - est) / est * 100)
        devs.sort()
        w10 = sum(1 for e in errs if e <= 10) / n * 100
        return mean(errs), median(errs), devs[min(n - 1, int(0.80 * n))], w10

    print(f"\n{'='*72}\nADJUSTMENT STRENGTH, RECONCILED OVER THE FULL POOL   n={n}\n{'='*72}")
    print(f"  {'lambda':>7}{'MAE':>10}{'median':>10}{'80% band':>12}{'within 10%':>13}")
    best = (9e9, None)
    for i in range(0, 11):
        lam = i / 10
        m, md, band, w10 = at(lam)
        tag = "  <- SHIPPED" if lam == 0.8 else ("  <- none" if lam == 0 else "")
        print(f"  {lam:>7.1f}{m:>9.2f}%{md:>9.2f}%   ±{band:>8.2f}%{w10:>12.1f}%{tag}")
        if m < best[0]:
            best = (m, lam)
    print(f"\n  error-minimising lambda = {best[1]:.1f} (MAE {best[0]:.2f}%)")
    shipped = at(0.8)[0]
    print(f"  shipped lambda=0.8 MAE {shipped:.2f}%  ->  best {best[0]:.2f}%  "
          f"({(shipped-best[0])/shipped*100:+.1f}% available)")


if __name__ == "__main__":
    main()
