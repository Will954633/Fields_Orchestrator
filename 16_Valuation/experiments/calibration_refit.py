#!/usr/bin/env python3
"""
calibration_refit.py — re-derive the per-suburb calibration factors on the
ALIGNED backtest, and validate them on homes that were not used to fit them.

WHY
───────────────────────────────────────────────────────────────────────────────
`_SUBURB_CALIBRATION` in precompute_valuations.py was derived 2026-08-07, BEFORE
the two changes of 2026-08-08 (reconciling over the full candidate pool, and the
λ=0.80 adjustment reliability shrinkage) improved the method. Those constants
correct a systematic LOW bias that the improved method no longer has, so they now
overshoot: with the backtest aligned to production on 2026-08-10, Robina's bias
reads **+2.0% (overvalues)** where the factor assumes −1.9% (undervalues).

The constant's own comment says "⚠ RE-MEASURE THESE … re-derive after any method
change". A method change happened. This is that re-derivation.

METHOD
───────────────────────────────────────────────────────────────────────────────
1. Run the pipeline with calibration DISABLED (`_SUBURB_CALIBRATION` emptied in
   this process), so every estimate is the method's raw output.
2. Split each suburb's homes deterministically into FIT and HOLDOUT halves by a
   hash of the property id — stable across re-runs, and independent of price,
   date or address.
3. Derive each factor on the FIT half only, as the MEDIAN of actual ÷ estimate.
   ⚠ Median, not mean: a handful of large misses drag a mean factor into
   correcting for outliers rather than for bias, and this multiplies EVERY
   valuation in the suburb.
4. Report current vs new on the HOLDOUT half. A factor that does not beat the
   incumbent out-of-sample does not ship.

⚠ THIS FITS ONE NUMBER PER SUBURB ON A FEW HUNDRED HOMES. Treat a small
improvement as noise. The bar for replacing a shipped constant is that the
holdout agrees with the fit on direction and rough size.

    python3 calibration_refit.py --limit 30      # smoke test
    python3 calibration_refit.py                 # full run
"""
import argparse, hashlib, json, os, sys, time
from statistics import mean, median

sys.path.insert(0, "/home/fields/Fields_Orchestrator/scripts")
sys.path.insert(0, "/home/fields/Feilds_Website/07_Valuation_Comps")

from dotenv import load_dotenv
from pymongo import MongoClient

import precompute_valuations as PV

# ⚠ MUST HAPPEN BEFORE the backtest module reads it. Emptying the table makes
# suburb_calibration_factor() return 1.0 for every suburb, so what comes back is
# the method's uncalibrated output and any candidate factor can be applied
# afterwards without re-running the pipeline.
_ORIGINAL_CALIBRATION = dict(PV._SUBURB_CALIBRATION)
PV._SUBURB_CALIBRATION.clear()

import valuation_backtest as vb
from precompute_valuations import resolve_land_size, resolve_floor_area

SUBURBS = ["robina", "varsity_lakes", "burleigh_waters"]


def fold(doc_id: str) -> str:
    """Stable FIT/HOLDOUT split — a hash of the id, not its order or price."""
    h = hashlib.sha256(doc_id.encode()).hexdigest()
    return "fit" if int(h[:8], 16) % 2 == 0 else "holdout"


def summarise(rows, factor):
    """How the method performs on these homes with `factor` applied."""
    errs, biases, devs = [], [], []
    for r in rows:
        est = r["est"] * factor
        errs.append(abs(est - r["actual"]) / r["actual"] * 100)
        biases.append((est - r["actual"]) / r["actual"] * 100)
        devs.append(abs(r["actual"] - est) / est * 100)
    devs.sort()
    n = len(rows)
    return {
        "n": n,
        "mae": mean(errs),
        "median_err": median(errs),
        "mean_bias": mean(biases),
        "median_bias": median(biases),
        "within10": sum(1 for e in errs if e <= 10) / n * 100,
        "band80": devs[min(n - 1, int(0.80 * n))],
    }


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--limit", type=int)
    ap.add_argument("--out", default="calibration_refit.jsonl")
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
    print(f"\n{len(subjects)} eligible sold houses · calibration DISABLED for the run\n")

    rows, t0 = [], time.time()
    with open(args.out, "w") as out:
        for i, subject in enumerate(subjects):
            sub = subject["_collection"]
            actual = vb.extract_sale_price(subject)
            try:
                res = vb.backtest_single_property(
                    db, subject, sold_by_suburb.get(sub, []), sold_by_suburb, {}, {},
                    median_cache={}, street_premium_cache={}, blind_subject=True)
            except Exception as e:
                print(f"  [{i}] ERROR {e}")
                continue
            est = (res or {}).get("reconciled_valuation")
            if not est:
                continue
            sid = str(subject["_id"])
            rec = {"id": sid, "suburb": sub, "actual": actual, "est": est, "fold": fold(sid)}
            rows.append(rec)
            out.write(json.dumps(rec) + "\n")
            out.flush()
            if len(rows) % 50 == 0:
                print(f"  {len(rows)} done ({(time.time()-t0)/60:.1f} min)")

    # Rule 7b — nothing measured is a broken harness, not a finding.
    if not rows:
        raise RuntimeError("0 homes produced an uncalibrated estimate — harness broken")

    print(f"\n{'='*78}\nCALIBRATION REFIT — fitted on half, judged on the other half\n{'='*78}")
    for sub in SUBURBS:
        srows = [r for r in rows if r["suburb"] == sub]
        fit = [r for r in srows if r["fold"] == "fit"]
        hold = [r for r in srows if r["fold"] == "holdout"]
        if len(fit) < 30 or len(hold) < 30:
            print(f"\n  {sub}: too few homes (fit {len(fit)}, holdout {len(hold)}) — no refit")
            continue
        new_factor = median(r["actual"] / r["est"] for r in fit)
        cur_factor = _ORIGINAL_CALIBRATION.get(sub, 1.0)

        print(f"\n  ── {sub}  (fit n={len(fit)}, holdout n={len(hold)}) "
              f"─────────────────────────────")
        print(f"     current factor {cur_factor:.4f}   →   refitted {new_factor:.4f}")
        print(f"     {'':22}{'current':>12}{'refitted':>12}{'none (1.0)':>13}")
        a, b, c = (summarise(hold, cur_factor), summarise(hold, new_factor),
                   summarise(hold, 1.0))
        for label, key, unit in (("MAE", "mae", "%"), ("median error", "median_err", "%"),
                                 ("mean bias", "mean_bias", "%"),
                                 ("median bias", "median_bias", "%"),
                                 ("within 10%", "within10", "%"),
                                 ("80% band", "band80", "%")):
            print(f"     {label:22}{a[key]:>11.2f}{unit}{b[key]:>11.2f}{unit}{c[key]:>12.2f}{unit}")
        verdict = ("REFIT WINS" if abs(b["mean_bias"]) < abs(a["mean_bias"]) and b["mae"] <= a["mae"]
                   else "no clear win — do not ship")
        print(f"     → {verdict} on held-out homes")


if __name__ == "__main__":
    main()
