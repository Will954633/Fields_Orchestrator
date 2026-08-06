#!/usr/bin/env python3
"""
Batch test: is the agent 3-comp valuation a lottery, and is Fields the steadier answer?

For every eligible sold home we compute:

  * the FULL set of possible agent valuations — every combination of 3 comps drawn
    from the qualifying pool (same type, same beds, same baths, land within
    tolerance, sold in the 12 months before the subject), scored as the midpoint of
    that triple's price range
  * the Fields adjusted-comparables valuation
  * the actual sale price

That gives, per property: how far apart two honest agents could land using identical
rules on identical data (DISPERSION), and where Fields sits in that cloud.

The claim being tested is NOT "Fields is more accurate". It is:
    a 3-comp valuation is indeterminate — the answer depends on which 3 you pick —
    and Fields returns one auditable answer instead of a draw from a distribution.

Both methods obey the same fairness rules: subject excluded by _id, every sale on or
after the subject's sale date dropped.

    python3 batch_dispersion.py --limit 20              # smoke test
    python3 batch_dispersion.py                          # full run

Writes results.jsonl + prints a summary. Resumable: re-running skips properties
already in the jsonl.
"""
import argparse
import json
import os
import random
import sys
import time
from itertools import combinations
from statistics import median, mean

sys.path.insert(0, "/home/fields/Fields_Orchestrator/scripts")
sys.path.insert(0, "/home/fields/Feilds_Website/07_Valuation_Comps")

from dotenv import load_dotenv
from pymongo import MongoClient

import valuation_backtest as vb
from precompute_valuations import resolve_land_size, resolve_floor_area

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from compare_comp_methods import basic_method, triple_stats

SUBURBS = ["robina", "varsity_lakes", "burleigh_waters"]
MAX_DRAWS = 5000          # if C(n,3) exceeds this, sample instead of enumerate
SEED = 20260806           # fixed: the run must be reproducible


def pctl(sorted_vals, q):
    if not sorted_vals:
        return None
    return sorted_vals[min(len(sorted_vals) - 1, int(len(sorted_vals) * q))]


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--n-comps", type=int, default=3)
    ap.add_argument("--land-tolerance", type=float, default=0.20)
    ap.add_argument("--window-months", type=int, default=12)
    ap.add_argument("--min-price", type=int, default=1_000_000)
    ap.add_argument("--max-price", type=int, default=2_000_000)
    ap.add_argument("--limit", type=int)
    ap.add_argument("--out", default="dispersion_results.jsonl")
    args = ap.parse_args()

    rng = random.Random(SEED)
    load_dotenv("/home/fields/Fields_Orchestrator/.env")
    client = MongoClient(os.environ["COSMOS_CONNECTION_STRING"], retryWrites=False,
                         serverSelectionTimeoutMS=30000, socketTimeoutMS=120000)
    db = client["Gold_Coast"]

    done = set()
    if os.path.exists(args.out):
        with open(args.out) as fh:
            for line in fh:
                try:
                    done.add(json.loads(line)["id"])
                except Exception:
                    pass
        print(f"Resuming — {len(done)} already done")

    print("Loading sold comparables ...")
    sold_by_suburb = (vb._load_sold_comparables(client) if vb._load_sold_comparables
                      else {s: list(db[s].find({"listing_status": "sold"})) for s in SUBURBS})
    keys = list(sold_by_suburb.keys())
    coords = vb._preload_gc_coordinates(client, keys) if vb._preload_gc_coordinates else {}
    timelines = vb._preload_gc_timelines(client, keys) if vb._preload_gc_timelines else {}
    print("Building caches (once) ...")
    median_cache = vb._build_suburb_median_cache(sold_by_suburb) if vb._build_suburb_median_cache else {}
    street_cache = vb._build_street_premium_cache(sold_by_suburb, median_cache) if vb._build_street_premium_cache else {}
    print(f"  {len(median_cache)} medians, {len(street_cache)} streets")

    # Eligible subjects
    subjects = []
    for sub in SUBURBS:
        for doc in db[sub].find({"listing_status": "sold"}):
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
        subjects = subjects[:args.limit]
    print(f"\n{len(subjects)} eligible sold homes "
          f"(${args.min_price:,}-${args.max_price:,}, houses, 3 suburbs)\n")

    t0 = time.time()
    written = 0
    with open(args.out, "a") as out:
        for i, subject in enumerate(subjects):
            sid = str(subject["_id"])
            if sid in done:
                continue
            sub = subject["_collection"]
            actual = vb.extract_sale_price(subject)
            pool = sold_by_suburb.get(sub, [])

            comps, _ = basic_method(subject, pool, args.land_tolerance,
                                   args.window_months)
            if len(comps) < args.n_comps:
                continue

            # every possible agent valuation (or a fixed random sample if huge)
            total = 1
            for k in range(args.n_comps):
                total = total * (len(comps) - k) // (k + 1)
            if total <= MAX_DRAWS:
                draws = list(combinations(comps, args.n_comps))
                sampled = False
            else:
                draws = [tuple(rng.sample(comps, args.n_comps))
                         for _ in range(MAX_DRAWS)]
                sampled = True

            mids, errs = [], []
            for t in draws:
                _, _, _, mid = triple_stats(t)
                mids.append(mid)
                errs.append(abs(mid - actual) / actual * 100)

            try:
                res = vb.backtest_single_property(
                    db, subject, pool, sold_by_suburb, coords, timelines,
                    median_cache=median_cache, street_premium_cache=street_cache)
            except Exception as e:
                print(f"  [{i}] {subject.get('address','?')[:40]} FIELDS ERROR {e}")
                continue
            if not res or not res.get("reconciled_valuation"):
                continue

            f_val = res["reconciled_valuation"]
            f_err = abs(f_val - actual) / actual * 100
            se = sorted(errs)
            sm = sorted(mids)

            rec = {
                "id": sid,
                "address": subject.get("address"),
                "suburb": sub,
                "actual": actual,
                "pool_n": len(comps),
                "draws": len(draws),
                "sampled": sampled,
                # DISPERSION — how far apart two honest agents could land
                "agent_mid_min": sm[0],
                "agent_mid_max": sm[-1],
                "agent_spread_pct": (sm[-1] - sm[0]) / actual * 100,
                "agent_err_min": se[0],
                "agent_err_p25": pctl(se, 0.25),
                "agent_err_median": se[len(se) // 2],
                "agent_err_p75": pctl(se, 0.75),
                "agent_err_max": se[-1],
                # FIELDS
                "fields_val": f_val,
                "fields_err": f_err,
                "fields_conf": res.get("confidence"),
                "fields_n_comps": res.get("n_included"),
                "fields_in_range": bool(res.get("range_low") and res.get("range_high")
                                        and res["range_low"] <= actual <= res["range_high"]),
                # head to head
                "share_agent_beats_fields": sum(1 for e in errs if e < f_err) / len(errs),
                "fields_beats_agent_median": f_err < se[len(se) // 2],
            }
            out.write(json.dumps(rec) + "\n")
            out.flush()
            written += 1
            if written % 10 == 0:
                el = time.time() - t0
                print(f"  {written} done ({i+1}/{len(subjects)} scanned) "
                      f"{el/60:.1f} min elapsed")

    print(f"\nWrote {written} records to {args.out} in {(time.time()-t0)/60:.1f} min")

    # ---- summary -----------------------------------------------------------
    rows = [json.loads(l) for l in open(args.out)]
    if not rows:
        return
    n = len(rows)
    print("\n" + "=" * 72)
    print(f"SUMMARY — {n} properties")
    print("=" * 72)

    def line(label, vals, unit="%"):
        s = sorted(vals)
        print(f"  {label:<42}{s[0]:>7.1f}{pctl(s,0.25):>9.1f}"
              f"{s[len(s)//2]:>9.1f}{pctl(s,0.75):>9.1f}{s[-1]:>9.1f}")

    print(f"  {'':<42}{'min':>7}{'p25':>9}{'median':>9}{'p75':>9}{'max':>9}")
    line("agent spread (max-min midpoint, % of sale)",
         [r["agent_spread_pct"] for r in rows])
    line("agent |error| median per property", [r["agent_err_median"] for r in rows])
    line("agent |error| BEST case per property", [r["agent_err_min"] for r in rows])
    line("agent |error| WORST case per property", [r["agent_err_max"] for r in rows])
    line("Fields |error|", [r["fields_err"] for r in rows])

    beats = sum(1 for r in rows if r["fields_beats_agent_median"])
    share = mean(r["share_agent_beats_fields"] for r in rows)
    print(f"\n  Fields beats the agent's MEDIAN draw : {beats}/{n} = {beats/n*100:.1f}%")
    print(f"  Mean share of agent draws that beat Fields : {share*100:.1f}%")
    print(f"  => a randomly-selected agent triple beats Fields "
          f"{share*100:.0f}% of the time")
    print(f"  Fields range contains the sale price : "
          f"{sum(1 for r in rows if r['fields_in_range'])/n*100:.1f}%")
    print(f"\n  Median agent pool size: {median([r['pool_n'] for r in rows]):.0f} "
          f"qualifying sales")


if __name__ == "__main__":
    main()
