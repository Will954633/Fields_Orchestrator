#!/usr/bin/env python3
"""
Compare two comparable-sales methods on ONE sold property.

  METHOD A — "agent"   : what a real estate agent valuation gives you. THREE
                         comparable sales, same property type, same bedroom count,
                         same bathroom count, roughly similar lot size. Raw sale
                         prices, no adjustments of any kind. (Three comps is also
                         the statutory Statement of Information standard in VIC and
                         the incoming NSW regime.)
  METHOD B — "Fields"  : the production adjusted-comparables method, via
                         valuation_backtest.backtest_single_property().

With only three comps the answer depends heavily on WHICH three. Rather than pick a
flattering triple, this enumerates EVERY combination of three from the qualifying
pool and reports the distribution — best case, median case, worst case — plus two
named picks an agent might plausibly make (three most recent, three closest on land).

Both methods are held to the SAME fairness rules, or the comparison is worthless:
  * the subject is excluded from its own comparable pool (by _id)
  * every sale dated ON OR AFTER the subject's sale date is dropped (no hindsight)

For each method we report the range of values and the midpoint derived from that
range, then score both against what the home actually sold for.

    python3 compare_comp_methods.py --suburb robina --match Moorabbin

Notes
  * DO NOT use precompute_valuations.precompute_property_valuation() on a home that
    has already sold — its sold-comp filter tests type/price/12-month window only,
    so the subject's own sale returns as its own top-weighted comparable and the
    valuation simply reproduces the sale price. backtest_single_property() is the
    only path that excludes the subject and its future correctly.
  * sale_price is stored as a STRING ("$1,620,000"). Parse in Python; a numeric
    Mongo predicate silently matches nothing.
  * land size lives in lot_size_sqm / lot_size_calc_sqm, not land_size. Both
    methods resolve it through the same helper so neither is disadvantaged.
"""
import argparse
import os
import re
import sys
from datetime import datetime, timedelta
from itertools import combinations
from statistics import median

sys.path.insert(0, "/home/fields/Fields_Orchestrator/scripts")
sys.path.insert(0, "/home/fields/Feilds_Website/07_Valuation_Comps")

from dotenv import load_dotenv
from pymongo import MongoClient

import valuation_backtest as vb
from precompute_valuations import resolve_land_size, resolve_floor_area

SUBURBS = ["robina", "varsity_lakes", "burleigh_waters"]


def money(v):
    return "n/a" if v is None else f"${v:,.0f}"


def pct(v):
    return "n/a" if v is None else f"{v:+.1f}%"


def basic_method(subject, pool, land_tolerance, window_months):
    """Label matching: same type, same beds, same baths, land within tolerance.

    Applies the identical subject-exclusion and no-hindsight rules as the Fields
    path. Returns (comps, notes) where each comp is (address, price, land, date).
    """
    subject_id = str(subject["_id"])
    s_beds = subject.get("bedrooms")
    s_baths = subject.get("bathrooms")
    s_land = resolve_land_size(subject)
    s_type = subject.get("property_type", "House")
    s_date = vb.get_sold_date(subject)

    cutoff = None
    if s_date and window_months:
        cutoff = s_date - timedelta(days=int(window_months * 30.44))

    lo = s_land * (1 - land_tolerance) if s_land else None
    hi = s_land * (1 + land_tolerance) if s_land else None

    comps, dropped = [], {"self": 0, "future": 0, "type": 0, "beds": 0,
                          "baths": 0, "land": 0, "price": 0, "window": 0}

    for doc in pool:
        if str(doc["_id"]) == subject_id:
            dropped["self"] += 1
            continue
        d = vb.get_sold_date(doc)
        if s_date and d and d >= s_date:          # no hindsight
            dropped["future"] += 1
            continue
        if cutoff and d and d < cutoff:
            dropped["window"] += 1
            continue
        if doc.get("property_type", "") != s_type:
            dropped["type"] += 1
            continue
        if s_beds is not None and doc.get("bedrooms") != s_beds:
            dropped["beds"] += 1
            continue
        if s_baths is not None and doc.get("bathrooms") != s_baths:
            dropped["baths"] += 1
            continue
        land = resolve_land_size(doc)
        if lo is not None:
            if land is None or land < lo or land > hi:
                dropped["land"] += 1
                continue
        price = vb.extract_sale_price(doc)
        if not price:
            dropped["price"] += 1
            continue
        comps.append((doc.get("address", "?"), price, land,
                      d.strftime("%Y-%m-%d") if d else "?"))

    comps.sort(key=lambda c: c[1])
    return comps, dropped


def triple_stats(triple):
    """Range low/high/width and derived midpoint for a set of raw comps."""
    prices = [c[1] for c in triple]
    lo, hi = min(prices), max(prices)
    return lo, hi, hi - lo, (lo + hi) / 2


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--suburb", default="robina", choices=SUBURBS)
    ap.add_argument("--match", default="Moorabbin",
                    help="address regex to pick the subject")
    ap.add_argument("--n-comps", type=int, default=3,
                    help="basic method: how many comparables (default 3, the "
                         "agent / Statement of Information standard)")
    ap.add_argument("--land-tolerance", type=float, default=0.20,
                    help="basic method: +/- fraction on land size (default 0.20)")
    ap.add_argument("--window-months", type=int, default=12,
                    help="basic method: months of prior sales to look at "
                         "(0 = all prior sales)")
    args = ap.parse_args()

    load_dotenv("/home/fields/Fields_Orchestrator/.env")
    client = MongoClient(os.environ["COSMOS_CONNECTION_STRING"],
                         retryWrites=False, serverSelectionTimeoutMS=30000,
                         socketTimeoutMS=120000)
    db = client["Gold_Coast"]

    # ---- subject -----------------------------------------------------------
    subject = db[args.suburb].find_one(
        {"listing_status": "sold",
         "address": {"$regex": args.match, "$options": "i"}})
    if not subject:
        sys.exit(f"No sold property matching {args.match!r} in {args.suburb}")
    subject["_collection"] = args.suburb

    actual = vb.extract_sale_price(subject)
    s_date = vb.get_sold_date(subject)

    print("=" * 78)
    print("COMPARABLE METHOD COMPARISON")
    print("=" * 78)
    print(f"Subject      : {subject.get('address')}")
    print(f"Sold         : {s_date.strftime('%Y-%m-%d') if s_date else '?'}"
          f"  for  {money(actual)}")
    print(f"Attributes   : {subject.get('bedrooms')} bed / "
          f"{subject.get('bathrooms')} bath / "
          f"{resolve_land_size(subject)} sqm land / "
          f"{resolve_floor_area(subject)} sqm floor")

    # ---- load the shared pool ---------------------------------------------
    print("\nLoading sold comparables ...")
    sold_by_suburb = (vb._load_sold_comparables(client)
                      if vb._load_sold_comparables else
                      {s: list(db[s].find({"listing_status": "sold"}))
                       for s in SUBURBS})
    print(f"  {sum(len(v) for v in sold_by_suburb.values())} sold records")

    print("Loading coordinates and timelines ...")
    keys = list(sold_by_suburb.keys())
    coords = vb._preload_gc_coordinates(client, keys) if vb._preload_gc_coordinates else {}
    timelines = vb._preload_gc_timelines(client, keys) if vb._preload_gc_timelines else {}

    print("Building median + street premium caches (slow, ~minutes) ...")
    median_cache = vb._build_suburb_median_cache(sold_by_suburb) if vb._build_suburb_median_cache else {}
    street_cache = vb._build_street_premium_cache(sold_by_suburb, median_cache) if vb._build_street_premium_cache else {}
    print(f"  {len(median_cache)} medians, {len(street_cache)} streets")

    pool = sold_by_suburb.get(args.suburb, [])

    # ---- METHOD A ----------------------------------------------------------
    comps, dropped = basic_method(subject, pool, args.land_tolerance,
                                  args.window_months)
    win = f"last {args.window_months} months" if args.window_months else "all prior sales"
    print("\n" + "-" * 78)
    print(f"METHOD A — AGENT VALUATION: {args.n_comps} COMPS  "
          f"({subject.get('bedrooms')} bed, {subject.get('bathrooms')} bath, "
          f"land ±{args.land_tolerance:.0%}, {win})")
    print("-" * 78)

    a_low = a_high = a_mid = None
    a_dist = None

    if len(comps) < args.n_comps:
        print(f"  Only {len(comps)} qualifying sales — need {args.n_comps}. "
              f"Dropped: {dropped}")
    else:
        print(f"  Qualifying pool ({len(comps)} sales, "
              f"choose {args.n_comps} = "
              f"{len(list(combinations(range(len(comps)), args.n_comps)))} "
              f"possible selections):")
        for addr, price, land, d in comps:
            print(f"    {money(price):>12}  {d}  {str(land) + ' sqm':>10}  {addr}")
        print(f"  (pool {len(pool)}; dropped {dropped})")

        # Every possible selection of n_comps — the honest spread
        rows = []
        for triple in combinations(comps, args.n_comps):
            lo, hi, width, mid = triple_stats(triple)
            e = (mid - actual) / actual * 100 if actual else None
            rows.append((abs(e) if e is not None else 9e9, e, lo, hi, width, mid, triple))
        rows.sort()

        best, worst = rows[0], rows[-1]
        med = rows[len(rows) // 2]
        a_dist = {"best": best, "median": med, "worst": worst, "n": len(rows)}

        print(f"\n  ALL {len(rows)} possible {args.n_comps}-comp selections, "
              f"scored on midpoint error:")
        print(f"    {'':<14}{'RANGE WIDTH':>14}{'MIDPOINT':>14}{'ERROR':>10}")
        for label, r in (("best case", best), ("median case", med),
                         ("worst case", worst)):
            print(f"    {label:<14}{money(r[4]):>14}{money(r[5]):>14}{pct(r[1]):>10}")

        widths = sorted(r[4] for r in rows)
        errs = sorted(abs(r[1]) for r in rows)
        print(f"    median range width {money(widths[len(widths) // 2])}   "
              f"median |error| {errs[len(errs) // 2]:.1f}%")

        # Two selections an agent might plausibly defend
        by_recent = sorted(comps, key=lambda c: c[3], reverse=True)[:args.n_comps]
        s_land = resolve_land_size(subject)
        by_land = sorted(
            [c for c in comps if c[2] is not None],
            key=lambda c: abs(c[2] - s_land))[:args.n_comps] if s_land else []

        print(f"\n  Two selections an agent could defend:")
        for label, sel in (("3 most recent", by_recent),
                           ("3 closest on land", by_land)):
            if len(sel) < args.n_comps:
                continue
            lo, hi, width, mid = triple_stats(sel)
            e = (mid - actual) / actual * 100 if actual else None
            print(f"    {label:<20}{money(lo)} -> {money(hi)}   "
                  f"mid {money(mid)}   {pct(e)}")
            for addr, price, land, d in sel:
                print(f"        {money(price):>12}  {d}  {addr}")

        # Headline Method A figure = the MEDIAN case, not the best case.
        _, _, a_low, a_high, _, a_mid, _ = med

    # ---- METHOD B ----------------------------------------------------------
    print("\n" + "-" * 78)
    print("METHOD B — FIELDS ADJUSTED COMPARABLES")
    print("-" * 78)
    res = vb.backtest_single_property(
        db, subject, pool, sold_by_suburb, coords, timelines,
        median_cache=median_cache, street_premium_cache=street_cache)

    if not res:
        print("  Valuation returned None.")
        b_low = b_high = b_mid = b_rec = None
    else:
        for pt in sorted(res["included_points"],
                         key=lambda p: p["adjustment_result"]["adjusted_price"]):
            raw = pt["price"]
            adj = pt["adjustment_result"]["adjusted_price"]
            # total_adjustment_pct is a FRACTION — x100 before display
            apct = pt["adjustment_result"].get("total_adjustment_pct")
            src = pt.get("_source_doc") or {}
            print(f"  {money(raw):>12} -> {money(adj):>12}  "
                  f"({apct * 100:+.1f}%)  {src.get('address', '?')}"
                  if apct is not None else
                  f"  {money(raw):>12} -> {money(adj):>12}   {src.get('address', '?')}")

        b_low = res.get("range_low")
        b_high = res.get("range_high")
        b_rec = res.get("reconciled_valuation")
        b_mid = (b_low + b_high) / 2 if b_low and b_high else None
        print(f"\n  n = {res['n_included']} included of {res['n_total_comps']} "
              f"assessed   confidence: {res.get('confidence')}")
        print(f"  Range     : {money(b_low)}  ->  {money(b_high)}   "
              f"width {money(b_high - b_low) if b_low and b_high else 'n/a'}")
        print(f"  Midpoint  : {money(b_mid)}")
        print(f"  Reconciled: {money(b_rec)}   <- the production figure "
              f"(weighted mean, not the midpoint)")

    # ---- scoreboard --------------------------------------------------------
    def err(v):
        return None if (v is None or not actual) else (v - actual) / actual * 100

    print("\n" + "=" * 78)
    print(f"SCOREBOARD   actual sale price {money(actual)}")
    print("=" * 78)
    print(f"{'':<26}{'RANGE WIDTH':>16}{'MIDPOINT':>16}{'MIDPOINT ERR':>16}")
    print(f"{'A  agent, median case':<26}"
          f"{money(a_high - a_low) if a_low else 'n/a':>16}"
          f"{money(a_mid):>16}{pct(err(a_mid)):>16}")
    print(f"{'B  Fields adjusted':<26}"
          f"{money(b_high - b_low) if b_low else 'n/a':>16}"
          f"{money(b_mid):>16}{pct(err(b_mid)):>16}")
    if b_rec:
        print(f"{'B  Fields reconciled':<26}{'':>16}{money(b_rec):>16}"
              f"{pct(err(b_rec)):>16}")

    if a_low and b_low:
        narrowing = (1 - (b_high - b_low) / (a_high - a_low)) * 100
        print(f"\n  Range narrowing A -> B : {narrowing:+.0f}%")
        for label, lo, hi in (("A", a_low, a_high), ("B", b_low, b_high)):
            inside = "INSIDE" if lo <= actual <= hi else "OUTSIDE"
            print(f"  Actual price is {inside} range {label}")

    print("\n  n=1. One property proves nothing about the distribution — see")
    print("  Adjusted-Comparables-Evidence.md §5 before quoting any of this.")


if __name__ == "__main__":
    main()
