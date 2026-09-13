#!/usr/bin/env python3
"""build_gc_segments.py → public/data/gc_segments.json — the Gold Coast segment
drill-downs (houses vs units, by bedroom, suburb league table) for the GC overview.

CROSS-SECTIONAL, last 12 months, one consistent basis — so the time-series
basis-seam ([GC-COMPOSITE-BASIS-BREAK]) does NOT apply here.

Sources, each used for its strength (see fix-history 2026-09-13):
  - PRICE + VOLUME + BEDS: system_monitor.onthehouse_sold — the COMPLETE source
    (agent + Valuer-General + RP). Houses and units.
  - DAYS ON MARKET: system_monitor.domain_sold — agent-listed sales carry
    listed+sold dates; DOM only exists for agent-listed sales anyway.

Editorial: medians shown WITH sample size (Will's requirement), ranges/comparables
not single valuations, houses vs units labelled, no advice/forecast. Segments with
too few sales to be meaningful are suppressed, not shown thin.

Usage: python3 scripts/build_gc_segments.py [--out PATH] [--dry-run]
"""
import argparse
import statistics
import sys
from datetime import date, datetime, timedelta, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from shared.db import get_client  # noqa: E402
from shared.env import load_env  # noqa: E402

DEFAULT_OUT = Path("/home/fields/Feilds_Website/01_Website/public/data/gc_segments.json")
MIN_N = 8                 # a segment needs >= this many priced sales to publish
MIN_N_DOM = 8             # and this many DOM observations to show a DOM figure
UNIT_TYPES_OTH = ["Unit", "Apartment", "Townhouse", "DuplexSemi-detached",
                  "Semi-Detached", "Villa"]


def med(xs):
    return round(statistics.median(xs)) if xs else None


def band(xs):
    """Inter-quartile range as the honest 'most sales fell between' band."""
    if len(xs) < 8:
        return None
    xs = sorted(xs)
    lo = xs[len(xs) // 4]
    hi = xs[(3 * len(xs)) // 4]
    return [round(lo), round(hi)]


def build(dry_run=False, out_path=DEFAULT_OUT):
    sm = get_client()["system_monitor"]
    oth, dom = sm["onthehouse_sold"], sm["domain_sold"]
    cut = (date.today() - timedelta(days=365)).isoformat()

    # ---- PRICE/VOLUME/BEDS from onthehouse (complete) ----
    def oth_rows(dwelling):
        q = {"sold_date": {"$gte": cut}, "sale_price": {"$nin": [None, 0]}}
        q["property_type"] = "House" if dwelling == "house" else {"$in": UNIT_TYPES_OTH}
        return list(oth.find(q, {"sale_price": 1, "beds": 1, "suburb_key": 1}))

    houses, units = oth_rows("house"), oth_rows("unit")

    # ---- DOM from domain_sold (agent-listed) ----
    def dom_days(dwelling, beds=None, suburb=None):
        q = {"sold_date": {"$gte": cut}, "dwelling": dwelling,
             "dom_days": {"$ne": None}}
        if beds is not None:
            q["beds"] = beds
        if suburb is not None:
            q["suburb_key"] = suburb
        return [d["dom_days"] for d in dom.find(q, {"dom_days": 1})
                if 0 <= (d["dom_days"] or -1) <= 730]

    def summarise(rows, dwelling, beds=None, suburb=None):
        prices = [r["sale_price"] for r in rows]
        doms = dom_days(dwelling, beds, suburb)
        return {
            "n": len(prices),
            "median": med(prices),
            "iqr": band(prices),
            "dom_median": med(doms) if len(doms) >= MIN_N_DOM else None,
            "dom_n": len(doms),
        }

    # Overall houses vs units
    overview = {
        "house": summarise(houses, "house"),
        "unit": summarise(units, "unit"),
    }

    # Bedroom buckets differ by dwelling: houses run 2..6+, units 1..4 (a "5/6-bed
    # unit" is an apartment-block/complex artifact, not a real category; studios and
    # 1-beds ARE real units). The top bucket collapses everything at-or-above it.
    def dom_gte(dwelling, floor):
        return [d["dom_days"] for d in dom.find(
            {"sold_date": {"$gte": cut}, "dwelling": dwelling,
             "beds": {"$gte": floor}, "dom_days": {"$ne": None}}, {"dom_days": 1})
            if 0 <= (d["dom_days"] or -1) <= 730]

    def by_bed(rows, dwelling, buckets, top_floor, top_label):
        out = []
        for b, label in buckets:
            sub = [r for r in rows if r.get("beds") == b]
            s = summarise(sub, dwelling, beds=b)
            if s["n"] >= MIN_N:
                out.append({"bed": label, **s})
        top = [r for r in rows if (r.get("beds") or 0) >= top_floor]
        st = summarise(top, dwelling)
        if st["n"] >= MIN_N:
            doms = dom_gte(dwelling, top_floor)
            st["dom_median"] = med(doms) if len(doms) >= MIN_N_DOM else None
            st["dom_n"] = len(doms)
            out.append({"bed": top_label, **st})
        return out

    beds = {
        "house": by_bed(houses, "house", [(2, "2 bed"), (3, "3 bed"), (4, "4 bed"), (5, "5 bed")], 6, "6+ bed"),
        "unit": by_bed(units, "unit", [(1, "1 bed"), (2, "2 bed"), (3, "3 bed")], 4, "4+ bed"),
    }

    # Suburb league table (houses) — median price, count, DOM; sorted by median desc
    league = []
    subs = {r["suburb_key"] for r in houses}
    for s in subs:
        rows = [r for r in houses if r["suburb_key"] == s]
        summ = summarise(rows, "house", suburb=s)
        if summ["n"] >= MIN_N:
            league.append({"suburb": s.rsplit("-", 1)[0].replace("-", " ").title(),
                           "suburb_key": s, **{k: summ[k] for k in
                           ("n", "median", "dom_median", "dom_n")}})
    league.sort(key=lambda x: x["median"], reverse=True)

    out = {
        "generated": datetime.now(timezone.utc).strftime("%Y-%m-%d"),
        "window": "Last 12 months",
        "overview": overview,
        "beds": beds,
        "league": league,
        "sources": {
            "price": "Fields transaction records via onthehouse (agent + Valuer-General "
                     "+ CoreLogic) — the complete sold record",
            "dom": "Days on market from agent-listed sales (Domain) — a marketing "
                   "campaign length, so government/private transfers are excluded",
        },
    }

    print(f"houses: {overview['house']['n']} priced, median ${overview['house']['median']:,}, "
          f"DOM {overview['house']['dom_median']}d (n={overview['house']['dom_n']})")
    print(f"units:  {overview['unit']['n']} priced, median ${overview['unit']['median']:,}, "
          f"DOM {overview['unit']['dom_median']}d (n={overview['unit']['dom_n']})")
    print(f"bed buckets: houses {[b['bed'] for b in beds['house']]}, "
          f"units {[b['bed'] for b in beds['unit']]}")
    print(f"league: {len(league)} suburbs (top ${league[0]['median']:,} {league[0]['suburb']}, "
          f"bottom ${league[-1]['median']:,} {league[-1]['suburb']})")

    if overview["house"]["n"] < 50 or len(league) < 20:
        raise RuntimeError(f"suspiciously thin output (houses {overview['house']['n']}, "
                           f"league {len(league)}) — upstream sold data may be broken")
    if dry_run:
        print("(dry run — nothing written)")
        return
    import json
    out_path.write_text(json.dumps(out, separators=(",", ":")) + "\n")
    print(f"wrote {out_path} ({out_path.stat().st_size:,} bytes)")


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", type=Path, default=DEFAULT_OUT)
    ap.add_argument("--dry-run", action="store_true")
    args = ap.parse_args()
    load_env()
    build(dry_run=args.dry_run, out_path=args.out)
