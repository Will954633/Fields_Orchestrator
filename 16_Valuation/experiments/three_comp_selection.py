#!/usr/bin/env python3
"""
Three-comparable selection sensitivity — the film run.

Extends 15_Off-Market/Page_Redesign_V4/Prototypes/batch_dispersion.py (2026-08-06,
n=512, "median spread $469,000") with the questions the film actually needs:

  1. How sensitive is the headline spread to the definition of a "defensible"
     triple? The 2026-08-06 run used a 12-month, same-suburb pool with NO price
     sanity and NO distance cap. The Queensland statutory CMA is three similar
     properties sold in the previous SIX months within FIVE km. Those are not the
     same pool, and the film says the statutory one on screen.

  2. Do any ex-ante selection rules — closest, most recent, most similar — reliably
     find the right three? This is the question that turns "agents disagree" into
     "the method is indeterminate".

  3. Pairwise disagreement: two agents each pick a defensible triple independently.
     How often do they land >10% / >15% / >20% apart?

Fairness rules inherited from the original run, and they are the whole validity of
this: the subject is excluded by _id, and every sale dated on or after the subject's
own sale date is dropped. No hindsight anywhere.

Fields' own error is NOT recomputed here — it is joined by _id from the original
dispersion_results.jsonl so both runs describe the identical valuation.

    python3 three_comp_selection.py --limit 25     # smoke test
    python3 three_comp_selection.py                # full run (~10 min)
"""
import argparse
import io
import json
import math
import os
import random
import sys
import time
import contextlib
from datetime import timedelta
from itertools import combinations
from statistics import median, mean

sys.path.insert(0, "/home/fields/Fields_Orchestrator/scripts")
sys.path.insert(0, "/home/fields/Feilds_Website/07_Valuation_Comps")

_quiet = io.StringIO()
with contextlib.redirect_stdout(_quiet):
    from dotenv import load_dotenv
    from pymongo import MongoClient
    import valuation_backtest as vb
    from precompute_valuations import resolve_land_size, resolve_floor_area

SUBJECT_SUBURBS = ["robina", "varsity_lakes", "burleigh_waters"]
MAX_DRAWS = 5000
N_PAIRS = 2000
SEED = 20260811

PRIOR_RUN = ("/home/fields/Fields_Orchestrator/15_Off-Market/Page_Redesign_V4"
             "/Prototypes/dispersion_results.jsonl")


def haversine(a, b):
    lat1, lon1 = a
    lat2, lon2 = b
    p1, p2 = math.radians(lat1), math.radians(lat2)
    dp = p2 - p1
    dl = math.radians(lon2 - lon1)
    h = math.sin(dp / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(dl / 2) ** 2
    return 6371 * 2 * math.asin(math.sqrt(h))


def latlon(doc):
    for a, b in (("LATITUDE", "LONGITUDE"), ("latitude", "longitude")):
        la, lo = doc.get(a), doc.get(b)
        if isinstance(la, (int, float)) and isinstance(lo, (int, float)) and la and lo:
            return (float(la), float(lo))
    return None


def flatten(doc, suburb):
    """One comparable, reduced to only what the selection rules need."""
    price = vb.extract_sale_price(doc)
    date = vb.get_sold_date(doc)
    if not price or not date:
        return None
    return {
        "id": str(doc["_id"]),
        "suburb": suburb,
        "price": float(price),
        "date": date,
        "ptype": doc.get("property_type", ""),
        "beds": doc.get("bedrooms"),
        "baths": doc.get("bathrooms"),
        "land": resolve_land_size(doc),
        "floor": resolve_floor_area(doc),
        "xy": latlon(doc),
    }


# ── pool definitions ────────────────────────────────────────────────────────
# Each is a claim about what "a defensible comparable" means. The headline number
# is only as strong as the loosest one that still supports it.

def build_pool(subj, universe, *, months, radius_km, land_tol,
               floor_tol=None, same_suburb=False):
    out = []
    cutoff = subj["date"] - timedelta(days=int(months * 30.44)) if months else None
    lo = subj["land"] * (1 - land_tol) if (subj["land"] and land_tol) else None
    hi = subj["land"] * (1 + land_tol) if (subj["land"] and land_tol) else None
    flo = subj["floor"] * (1 - floor_tol) if (subj["floor"] and floor_tol) else None
    fhi = subj["floor"] * (1 + floor_tol) if (subj["floor"] and floor_tol) else None

    for c in universe:
        if c["id"] == subj["id"]:
            continue
        if c["date"] >= subj["date"]:                     # no hindsight
            continue
        if cutoff and c["date"] < cutoff:
            continue
        if same_suburb and c["suburb"] != subj["suburb"]:
            continue
        if c["ptype"] != subj["ptype"]:
            continue
        if subj["beds"] is not None and c["beds"] != subj["beds"]:
            continue
        if subj["baths"] is not None and c["baths"] != subj["baths"]:
            continue
        if lo is not None and (c["land"] is None or not lo <= c["land"] <= hi):
            continue
        if flo is not None and (c["floor"] is None or not flo <= c["floor"] <= fhi):
            continue
        d = None
        if radius_km is not None:
            if not (subj["xy"] and c["xy"]):
                continue
            d = haversine(subj["xy"], c["xy"])
            if d > radius_km:
                continue
        elif subj["xy"] and c["xy"]:
            d = haversine(subj["xy"], c["xy"])
        e = dict(c)
        e["dist_km"] = d
        out.append(e)
    return out


POOLS = {
    # exactly what the 2026-08-06 $469,000 run used — reproduced as the control
    "as_run_12mo_suburb": dict(months=12, radius_km=None, land_tol=0.20,
                               same_suburb=True),
    # what the film says on screen: QLD statutory CMA
    "statutory_6mo_5km": dict(months=6, radius_km=5.0, land_tol=0.20),
    # statutory + the physical-similarity screen any competent agent applies
    "statutory_plus_floor": dict(months=6, radius_km=5.0, land_tol=0.20,
                                 floor_tol=0.20),
    # the tightest pool a hostile reviewer could demand
    "strict_6mo_2km_floor": dict(months=6, radius_km=2.0, land_tol=0.20,
                                 floor_tol=0.20),
}


# ── scoring a triple ────────────────────────────────────────────────────────
def score_midpoint(t):
    p = [c["price"] for c in t]
    return (min(p) + max(p)) / 2


def score_mean(t):
    return mean(c["price"] for c in t)


SCORERS = {"midpoint": score_midpoint, "mean": score_mean}


# ── ex-ante selection rules ─────────────────────────────────────────────────
# Every one of these uses ONLY information available before the sale. None may
# touch the subject's sale price — that is the whole point of the question.

def rule_closest(pool, subj):
    ok = [c for c in pool if c["dist_km"] is not None]
    return sorted(ok, key=lambda c: c["dist_km"])[:3]


def rule_recent(pool, subj):
    return sorted(pool, key=lambda c: c["date"], reverse=True)[:3]


def rule_similar_floor(pool, subj):
    ok = [c for c in pool if c["floor"]]
    if not subj["floor"]:
        return []
    return sorted(ok, key=lambda c: abs(c["floor"] - subj["floor"]))[:3]


def rule_similar_land(pool, subj):
    ok = [c for c in pool if c["land"]]
    if not subj["land"]:
        return []
    return sorted(ok, key=lambda c: abs(c["land"] - subj["land"]))[:3]


def _norm_rank(pool, key):
    """Rank position 0..1 within the pool on a distance-like key (lower better)."""
    vals = sorted(set(v for v in (key(c) for c in pool) if v is not None))
    if not vals:
        return {}
    idx = {v: i / max(1, len(vals) - 1) for i, v in enumerate(vals)}
    return idx


def rule_composite(pool, subj):
    """Floor + land + distance + recency, equally weighted. The rule a thorough
    agent would describe themselves as following."""
    if not (subj["floor"] and subj["land"]):
        return []
    usable = [c for c in pool if c["floor"] and c["land"] and c["dist_km"] is not None]
    if len(usable) < 3:
        return []
    rf = _norm_rank(usable, lambda c: abs(c["floor"] - subj["floor"]))
    rl = _norm_rank(usable, lambda c: abs(c["land"] - subj["land"]))
    rd = _norm_rank(usable, lambda c: c["dist_km"])
    rr = _norm_rank(usable, lambda c: (subj["date"] - c["date"]).days)

    def sc(c):
        return (rf[abs(c["floor"] - subj["floor"])] + rl[abs(c["land"] - subj["land"])]
                + rd[c["dist_km"]] + rr[(subj["date"] - c["date"]).days])
    return sorted(usable, key=sc)[:3]


def rule_median_price(pool, subj):
    """Three comps nearest the pool's own median price. Ex ante — it uses the
    comparables' prices, never the subject's."""
    m = median([c["price"] for c in pool])
    return sorted(pool, key=lambda c: abs(c["price"] - m))[:3]


def rule_ppsm(pool, subj):
    """Three comps nearest the pool's median $/sqm of floor area, applied to the
    subject. The most sophisticated rule available without our adjustment layer."""
    ok = [c for c in pool if c["floor"]]
    if len(ok) < 3 or not subj["floor"]:
        return []
    m = median([c["price"] / c["floor"] for c in ok])
    return sorted(ok, key=lambda c: abs(c["price"] / c["floor"] - m))[:3]


RULES = {
    "closest_3": rule_closest,
    "most_recent_3": rule_recent,
    "similar_floor_3": rule_similar_floor,
    "similar_land_3": rule_similar_land,
    "composite_3": rule_composite,
    "nearest_pool_median_3": rule_median_price,
    "nearest_median_ppsm_3": rule_ppsm,
}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--limit", type=int)
    ap.add_argument("--out", default="three_comp_selection.jsonl")
    args = ap.parse_args()

    rng = random.Random(SEED)
    load_dotenv("/home/fields/Fields_Orchestrator/.env")
    client = MongoClient(os.environ["COSMOS_CONNECTION_STRING"], retryWrites=False,
                         serverSelectionTimeoutMS=30000, socketTimeoutMS=120000)
    db = client["Gold_Coast"]

    prior = {}
    if os.path.exists(PRIOR_RUN):
        for line in open(PRIOR_RUN):
            try:
                r = json.loads(line)
                prior[r["id"]] = r
            except Exception:
                pass
    print(f"joined {len(prior)} rows from the 2026-08-06 run", file=sys.stderr)

    with contextlib.redirect_stdout(_quiet):
        sold_by_suburb = vb._load_sold_comparables(client)

    universe = []
    for sub, docs in sold_by_suburb.items():
        for d in docs:
            f = flatten(d, sub)
            if f:
                universe.append(f)
    print(f"universe: {len(universe)} sold records across "
          f"{len(sold_by_suburb)} suburbs", file=sys.stderr)

    subjects = []
    for sub in SUBJECT_SUBURBS:
        for doc in db[sub].find({"listing_status": "sold"}):
            price = vb.extract_sale_price(doc)
            if not price or not (1_000_000 <= price <= 2_000_000):
                continue
            if doc.get("property_type") != "House":
                continue
            if not resolve_floor_area(doc) or not resolve_land_size(doc):
                continue
            f = flatten(doc, sub)
            if f:
                subjects.append(f)
    if args.limit:
        subjects = subjects[:args.limit]
    print(f"{len(subjects)} eligible subjects", file=sys.stderr)

    t0 = time.time()
    with open(args.out, "w") as out:
        for i, subj in enumerate(subjects):
            actual = subj["price"]
            rec = {"id": subj["id"], "suburb": subj["suburb"], "actual": actual,
                   "fields_err": (prior.get(subj["id"]) or {}).get("fields_err"),
                   "pools": {}}

            for pname, cfg in POOLS.items():
                pool = build_pool(subj, universe, **cfg)
                if len(pool) < 3:
                    rec["pools"][pname] = {"n": len(pool)}
                    continue

                total = len(pool) * (len(pool) - 1) * (len(pool) - 2) // 6
                if total <= MAX_DRAWS:
                    draws = list(combinations(pool, 3))
                    sampled = False
                else:
                    draws = [tuple(rng.sample(pool, 3)) for _ in range(MAX_DRAWS)]
                    sampled = True

                entry = {"n": len(pool), "draws": len(draws), "sampled": sampled}

                for sname, scorer in SCORERS.items():
                    vals = [scorer(t) for t in draws]
                    errs = sorted(abs(v - actual) / actual * 100 for v in vals)
                    vs = sorted(vals)
                    entry[sname] = {
                        "min": vs[0], "max": vs[-1],
                        "spread_pct": (vs[-1] - vs[0]) / actual * 100,
                        "spread_dollars": vs[-1] - vs[0],
                        "err_min": errs[0],
                        "err_median": errs[len(errs) // 2],
                        "err_max": errs[-1],
                        "err_mean": mean(errs),
                        "oracle_within_2pct": errs[0] < 2.0,
                        "within10_share": sum(1 for e in errs if e <= 10) / len(errs),
                    }
                    # pairwise disagreement between two independent honest agents
                    if len(vals) >= 2:
                        gaps = []
                        for _ in range(N_PAIRS):
                            a, b = rng.choice(vals), rng.choice(vals)
                            mid = (a + b) / 2
                            if mid:
                                gaps.append(abs(a - b) / mid * 100)
                        if gaps:
                            gs = sorted(gaps)
                            entry[sname]["pair_gap_median"] = gs[len(gs) // 2]
                            for th in (10, 15, 20):
                                entry[sname][f"pair_gap_over_{th}"] = \
                                    sum(1 for g in gaps if g > th) / len(gaps)

                # ex-ante rules, scored both ways
                entry["rules"] = {}
                for rname, fn in RULES.items():
                    try:
                        t = fn(pool, subj)
                    except Exception:
                        t = []
                    if len(t) != 3:
                        continue
                    r = {}
                    for sname, scorer in SCORERS.items():
                        v = scorer(t)
                        r[sname] = {"val": v,
                                    "err": abs(v - actual) / actual * 100}
                    entry["rules"][rname] = r
                rec["pools"][pname] = entry

            out.write(json.dumps(rec, default=str) + "\n")
            if (i + 1) % 25 == 0:
                print(f"  {i+1}/{len(subjects)}  {(time.time()-t0)/60:.1f} min",
                      file=sys.stderr)

    print(f"done in {(time.time()-t0)/60:.1f} min -> {args.out}", file=sys.stderr)


if __name__ == "__main__":
    main()
