#!/usr/bin/env python3
"""backtest_statutory_comparables.py — is the statutory set actually worse?

The page is about to make a claim in public: that we prefer a sale in the SAME BUILDING
over a more recent sale nearby, and that this is the better comparison despite failing the
statutory recency test. That has to be measured before it is printed, or it is a
preference dressed as a finding.

METHOD — leakage-free, and scored on the SAME homes by the SAME machinery.
Every scoring primitive here (`load`, `build_index`, `deflate_to`, `predict`, `quarter`)
is imported from backtest_unit_valuation rather than reimplemented, so the same-complex
column is EXACTLY production's measured method and any difference between the columns is
the comparable set, not two subtly different harnesses.

For each sale from --from-year on, both methods predict it using only sales that settled
strictly before the subject's sale quarter:
    same-complex  production tiers, prefers the subject's own building, reaches back 8yrs
    statutory     median of the <=12 most comparable sales, same bedroom count, within
                  5km, settled in the SIX MONTHS BEFORE the subject's sale
Only homes where BOTH produced an answer are scored, so neither method can win by quietly
declining the hard ones.
"""
from __future__ import annotations

import argparse
import json
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

from shared.db import get_client                         # noqa: E402
from backtest_unit_valuation import (SUBURBS, load, build_index, deflate_to,   # noqa: E402
                                     predict, quarter, year)
from unit_valuation import _num                          # noqa: E402
from statutory_comparables import (haversine_km, _months_between,      # noqa: E402
                                   RADIUS_KM, WINDOW_MONTHS, MIN_COMPS,
                                   FLOOR_ADJ_MAX, FLOOR_ADJ_RATE)

MAX_STAT_COMPS = 12


def attach_locations(gc, rows, suburb):
    """Give each row its scheme centroid, floor area and bathroom count.

    ⚠ FLOOR AND BATHS MATTER HERE EVEN THOUGH `load()` DOES NOT RETURN THEM.
    Production ranks candidate comparables on distance, floor area, bathrooms and
    recency. If the backtest left floor/baths as None it would rank on distance and
    recency ALONE, uniformly applying the unknown-size penalty to every candidate — a
    measurably different selector from the one being shipped. The backtest would then be
    honest about a method we do not run. `load()` is left untouched because the published
    same-complex accuracy figures were measured with it.
    """
    cent = {}
    for d in gc["complexes"].find({"suburb_key": suburb},
                                  {"plan": 1, "centroid_lat": 1, "centroid_lon": 1}):
        if d.get("centroid_lat") is not None:
            cent[d.get("plan")] = (d["centroid_lat"], d["centroid_lon"])

    attrs = {}
    for d in gc[suburb].find({}, {"bathrooms": 1, "floor_area_sqm": 1,
                                  "internal_living_area_sqm": 1,
                                  "enriched_data.floor_area_sqm": 1}):
        attrs[d["_id"]] = (
            _num(d.get("floor_area_sqm")) or _num(d.get("internal_living_area_sqm"))
            or _num((d.get("enriched_data") or {}).get("floor_area_sqm")),
            _num(d.get("bathrooms")))

    n = with_floor = 0
    for r in rows:
        loc = cent.get(r.get("plan"))
        if loc:
            r["lat"], r["lon"] = loc
            n += 1
        r["floor"], r["baths"] = attrs.get(r["id"], (None, None))
        with_floor += bool(r["floor"])
    return n, with_floor


def statutory_predict(subject, sale_q, sale_date, all_rows, idx_beds, idx_all):
    """Median of the most comparable sales settled in the 6 months before the subject's.

    ⚠ The ranking uses distance, floor area, bathrooms and recency — never price. Ranking
    comparables by closeness to an expected value selects the evidence to agree with the
    answer and then reports the agreement as accuracy.
    """
    if not subject.get("lat"):
        return None, 0
    beds = subject.get("beds")
    if not beds:
        return None, 0

    near = []
    for r in all_rows:
        if r["id"] == subject["id"] or r["beds"] != beds or not r.get("lat"):
            continue
        km = haversine_km(subject["lat"], subject["lon"], r["lat"], r["lon"])
        if km > RADIUS_KM:
            continue
        for date, price in r["sales"]:
            q = quarter(date)
            if not q or q >= sale_q:                  # the future does not exist
                continue
            m = _months_between(date, sale_date)
            if m is None or m < 0 or m > WINDOW_MONTHS:
                continue
            near.append({"date": date, "q": q, "price": price, "km": km,
                         "floor": r.get("floor"), "baths": r.get("baths")})
    if len(near) < MIN_COMPS:
        return None, len(near)

    sf, sb = subject.get("floor"), subject.get("baths")

    def score(r):
        s = r["km"] / RADIUS_KM
        s += (min(1.0, abs(sf - r["floor"]) / sf) * 1.5) if (sf and r["floor"]) else 0.35
        if sb and r["baths"]:
            s += min(1.0, abs(sb - r["baths"]) * 0.5)
        s += ((_months_between(r["date"], sale_date) or 0) / WINDOW_MONTHS) * 0.4
        return s

    idx = (idx_beds.get(str(beds)) if beds else None) or idx_all.get("all")
    adj = []
    for r in sorted(near, key=score)[:MAX_STAT_COMPS]:
        price = r["price"]
        v, _f = deflate_to(idx, price, r["q"], sale_q)
        if v is not None:
            price = v
        if sf and r["floor"]:
            diff = (sf - r["floor"]) / r["floor"]
            if abs(diff) <= FLOOR_ADJ_MAX:
                price *= (1 + diff * FLOOR_ADJ_RATE)
        adj.append(price)
    return (st.median(adj), len(near)) if len(adj) >= MIN_COMPS else (None, len(near))


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--from-year", type=int, default=2023)
    ap.add_argument("--out", default=str(HERE.parent / "artifacts" / "backtest_statutory.json"))
    args = ap.parse_args()

    gc = get_client()["Gold_Coast"]
    pairs, per_sub = [], defaultdict(list)
    no_loc = 0
    floor_cov = {}

    for suburb in SUBURBS:
        rows = load(gc, suburb)
        located, with_floor = attach_locations(gc, rows, suburb)
        no_loc += len(rows) - located
        floor_cov[suburb] = (with_floor, len(rows))
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
                comp, tier, _n = predict(r, q, by_cms, by_plan, by_sub, idx_all, idx_beds)
                stat, pool_n = statutory_predict(r, q, date, rows, idx_beds, idx_all)
                if comp is None or stat is None:
                    continue
                pairs.append({
                    "suburb": suburb, "actual": actual, "comp": comp, "stat": stat,
                    "tier": tier, "pool": pool_n,
                    "e_comp": abs(comp - actual) / actual * 100,
                    "e_stat": abs(stat - actual) / actual * 100})
                per_sub[suburb].append(pairs[-1])

    if not pairs:
        print("no home had BOTH methods produce an answer — nothing to compare")
        return 1

    def stats(rs, key):
        e = sorted(x[f"e_{key}"] for x in rs)
        return {"n": len(e), "median": round(st.median(e), 2),
                "mae": round(st.mean(e), 2),
                "within10": round(sum(1 for x in e if x <= 10) / len(e) * 100, 1),
                "p80": round(e[int(len(e) * 0.8)], 2)}

    print(f"\n  STATUTORY vs SAME-COMPLEX — scored on the same {len(pairs):,} sales, "
          f"from {args.from_year}")
    print(f"  (rows with no scheme centroid, excluded from both: {no_loc:,})")
    for k, (a, b) in sorted(floor_cov.items()):
        print(f"    {k:18s} floor area known on {a:,}/{b:,} ({a/max(1,b)*100:.0f}%)")
    print()
    hdr = f"  {'cohort':20s} {'n':>6s} | {'STATUTORY 5km/6mo':>28s} | {'SAME-COMPLEX':>28s}"
    print(hdr)
    print(f"  {'':20s} {'':>6s} | {'median':>8s} {'MAE':>7s} {'<10%':>6s} {'P80':>5s} |"
          f" {'median':>8s} {'MAE':>7s} {'<10%':>6s} {'P80':>5s}")
    res = {"overall": {}, "by_suburb": {}}
    for label, rs in [("OVERALL", pairs)] + sorted(per_sub.items()):
        if len(rs) < 20:
            continue
        a, b = stats(rs, "stat"), stats(rs, "comp")
        (res["overall"] if label == "OVERALL" else res["by_suburb"].setdefault(label, {})
         ).update({"statutory": a, "same_complex": b})
        print(f"  {label:20s} {a['n']:>6,} | {a['median']:>7.1f}% {a['mae']:>6.1f}% "
              f"{a['within10']:>5.1f}% {a['p80']:>4.1f}% | "
              f"{b['median']:>7.1f}% {b['mae']:>6.1f}% {b['within10']:>5.1f}% {b['p80']:>4.1f}%")

    better = sum(1 for p in pairs if p["e_comp"] < p["e_stat"])
    res["same_complex_closer_pct"] = round(better / len(pairs) * 100, 1)
    res["n_pairs"] = len(pairs)
    res["method"] = ("leakage-free; both methods scored on identical sales using the "
                     "backtest_unit_valuation primitives; statutory ranking uses "
                     "distance/floor/baths/recency only, never price")
    print(f"\n  same-complex is closer on {better:,} of {len(pairs):,} sales "
          f"({better/len(pairs)*100:.1f}%)")

    Path(args.out).parent.mkdir(parents=True, exist_ok=True)
    Path(args.out).write_text(json.dumps(res, indent=2))
    print(f"  written: {args.out}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
