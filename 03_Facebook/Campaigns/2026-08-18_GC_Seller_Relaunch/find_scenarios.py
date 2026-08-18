#!/usr/bin/env python3
"""
find_scenarios.py — the verified-scenario finders behind the GC Seller Relaunch creatives.

Every figure on GC2 / GC3 / GC5 / the proposed GC6 came out of one of these. Re-run any of
them to refresh a card's numbers, or to find a replacement property when one goes stale.

    source /home/fields/venv/bin/activate
    python3 find_scenarios.py avm-misses          # GC2 "missed by a million"
    python3 find_scenarios.py dom-pairs           # GC3 "the neighbour pair"
    python3 find_scenarios.py asking-quartiles    # GC6 "the split" (AN28 rebuild)
    python3 find_scenarios.py verify --address "130 Christine"

GC5's $469,000 is NOT computed here — it comes from a standing experiment,
`15_Off-Market/Page_Redesign_V4/Prototypes/RESULT_dispersion_512.md` (batch_dispersion.py,
seed 20260806). Re-run that script to refresh it.

⚠ FIELD-NAME LANDMINES (Rule 8 — all three cost time on 2026-08-18):
  • `sale_price` is the ONLY trustworthy sold figure, and it is a STRING ('$2,130,000').
    `listing_price` is 'SOLD - $X' on 86% of sold docs — a derived copy of sale_price that
    fossilises at the PREVIOUS sale on resales. Never use it as an asking price.
  • `land_size` is 6% filled. `land_size_sqm` is 69%. Searching the first one wrongly
    concludes land data is absent.
  • `days_on_market` is 69% filled on sold houses; `days_on_domain` is a separate, sparser
    field. Absence of a match in one is not absence of the pair.
"""
import argparse, re, statistics as st, sys
from datetime import datetime, timedelta
from collections import Counter

sys.path.insert(0, "/home/fields/Fields_Orchestrator")
from shared.db import get_client  # noqa: E402

SUBURBS = ["robina", "varsity_lakes", "burleigh_waters"]
PRETTY = {"robina": "Robina", "varsity_lakes": "Varsity Lakes",
          "burleigh_waters": "Burleigh Waters"}


def money(s):
    """Parse a price string. Handles '$1,440,000', '$1.5M', 'Offers Over $1,895,000'."""
    if isinstance(s, (int, float)):
        v = float(s)
        return int(v) if 200_000 < v < 20_000_000 else None
    if not isinstance(s, str):
        return None
    m = re.findall(r"\$\s?(\d[\d,.]*)\s*([mM])?", s.replace(",", ""))
    if not m:
        return None
    v, suf = m[0]
    try:
        v = float(v)
    except ValueError:
        return None
    if suf:
        v *= 1_000_000
    return int(v) if 200_000 < v < 20_000_000 else None


def when(s):
    try:
        return datetime.strptime(str(s)[:10], "%Y-%m-%d")
    except Exception:
        return None


# ───────────────────────────────────────────────────────── GC2: AVM misses
def avm_misses(db, months, limit):
    """Sold homes whose published online estimate missed, and missed OUTSIDE its own range.

    Publication rule: `within_range: false` only. A miss inside the portal's published
    range is not a story — they said it might be that.
    """
    cutoff = datetime.now() - timedelta(days=30 * months)
    rows = []
    for sub in SUBURBS:
        for d in db[sub].find(
            {"listing_status": "sold", "property_type": "House",
             "domain_valuation_accuracy.within_range": False},
            {"address": 1, "sale_price": 1, "sold_date": 1,
             "domain_valuation_at_listing": 1, "domain_valuation_accuracy": 1}):
            v, a = d.get("domain_valuation_at_listing") or {}, d.get("domain_valuation_accuracy") or {}
            sold, est = money(d.get("sale_price")), v.get("mid")
            sd, ed = when(d.get("sold_date")), when(v.get("date"))
            if not (sold and est and sd) or sd < cutoff:
                continue
            # the estimate MUST predate the sale, or it is hindsight, not a forward test
            if ed and ed >= sd:
                continue
            rows.append(dict(sub=sub, addr=d.get("address"), est=est, sold=sold,
                             low=v.get("low"), high=v.get("high"), label=v.get("accuracy"),
                             err=a.get("error_dollars"), pct=a.get("error_pct"),
                             sd=sd, ed=ed))
    rows.sort(key=lambda r: -abs(r["err"] or 0))
    print(f"AVM misses outside the portal's own published range, sold in the last "
          f"{months} months, estimate dated BEFORE the sale — n={len(rows)}\n")
    for r in rows[:limit]:
        print(f"  ${r['err']:>10,}  ({r['pct']:>6.1f}%)  {PRETTY[r['sub']]}")
        print(f"      estimate ${r['est']:>9,}  range ${r['low']:,}–${r['high']:,}  "
              f"label “{r['label']}”  as at {r['ed']:%b %Y}" if r['ed'] else "")
        print(f"      sold     ${r['sold']:>9,}  {r['sd']:%d %b %Y}   {r['addr']}\n")
    return rows


# ─────────────────────────────────────────────── GC3: matched pairs, DOM contrast
def dom_pairs(db, months, fast_max, slow_min, land_tol, price_tol, apart_max, limit):
    """Near-identical homes in one suburb where one sold fast AND higher.

    'Near-identical' has to mean something defensible: same suburb, same bed/bath, land
    within `land_tol`. Matching on bed+bath alone produces pairs $1.6M apart — waterfront
    vs not — which would be indefensible if anyone checked.
    """
    cutoff = datetime.now() - timedelta(days=30 * months)
    pool = []
    for sub in SUBURBS:
        for d in db[sub].find(
            {"listing_status": "sold", "property_type": "House",
             "days_on_market": {"$exists": True},
             "land_size_sqm": {"$exists": True, "$ne": None}},
            {"address": 1, "sale_price": 1, "days_on_market": 1, "bedrooms": 1,
             "bathrooms": 1, "car_spaces": 1, "sold_date": 1, "land_size_sqm": 1,
             "days_on_market_source": 1}):
            p, sd = money(d.get("sale_price")), when(d.get("sold_date"))
            if not (p and sd) or sd < cutoff:
                continue
            pool.append(dict(sub=sub, addr=d.get("address"), price=p, dom=d["days_on_market"],
                             beds=d.get("bedrooms"), baths=d.get("bathrooms"),
                             cars=d.get("car_spaces"), land=d["land_size_sqm"], sd=sd,
                             src=d.get("days_on_market_source")))
    hits = []
    for a in pool:
        if a["dom"] > fast_max:
            continue
        for b in pool:
            if b["sub"] != a["sub"] or b["dom"] < slow_min:
                continue
            if a["beds"] != b["beds"] or a["baths"] != b["baths"]:
                continue
            if abs(a["land"] - b["land"]) / max(a["land"], b["land"]) > land_tol:
                continue
            if abs((a["sd"] - b["sd"]).days) > apart_max:
                continue
            gap = a["price"] - b["price"]
            if gap <= 0 or gap / b["price"] > price_tol:
                continue
            hits.append((gap, b["dom"] - a["dom"], abs((a["sd"] - b["sd"]).days), a, b))
    hits.sort(key=lambda x: -x[0])
    print(f"pool={len(pool)} sold houses (last {months}mo, with DOM + land_size_sqm)")
    print(f"pairs: same suburb, same bed+bath, land within {land_tol:.0%}, price gap "
          f"<{price_tol:.0%}, sold within {apart_max}d of each other,\n"
          f"fast(<={fast_max}d) sold HIGHER than slow(>={slow_min}d) — n={len(hits)}\n")
    for gap, dg, apart, a, b in hits[:limit]:
        print(f"  +${gap:,} ({gap/b['price']*100:.1f}%)  |  {dg} days faster  |  "
              f"sold {apart} days apart  [{PRETTY[a['sub']]}]")
        for tag, x in (("FAST", a), ("SLOW", b)):
            print(f"     {tag} {x['dom']:3d}d  ${x['price']:>9,}  "
                  f"{x['beds']}bd/{x['baths']}ba/{x['cars']}car {x['land']}m²  "
                  f"{x['sd']:%d %b %Y}  {x['addr']}  [{x['src']}]")
        print()
    return hits


# ─────────────────────────────────────── GC6 / AN28: % of asking price achieved
def asking_quartiles(db, months):
    """Quartiles of (sale price / advertised asking price).

    ⚠ Only ~6% of sold houses are usable. 86% carry `listing_price` = 'SOLD - $X' (the
    fossilised derived copy), and most of the rest are 'Auction' or 'Contact Agent' with no
    number. What survives is PRIVATE-TREATY SALES THAT ADVERTISED A FIXED PRICE — auctions
    are structurally excluded. Any public use MUST say so; 'in a typical suburb' is not
    supportable from this sample.
    """
    cutoff = datetime.now() - timedelta(days=30 * months)
    rows, skipped = [], Counter()
    for sub in SUBURBS:
        for d in db[sub].find(
            {"listing_status": "sold", "property_type": "House",
             "listing_price": {"$exists": True}, "sale_price": {"$exists": True}},
            {"listing_price": 1, "sale_price": 1, "address": 1, "sold_date": 1}):
            lp = str(d["listing_price"])
            if lp.upper().startswith("SOLD"):
                skipped["fossilised 'SOLD - $X'"] += 1
                continue
            ask, sold = money(lp), money(str(d.get("sale_price")))
            if not ask:
                skipped[f"no number ({lp[:22]})" if len(lp) < 24 else "no number"] += 1
                continue
            if not sold:
                skipped["no sale_price"] += 1
                continue
            sd = when(d.get("sold_date"))
            if sd and sd < cutoff:
                skipped["older than window"] += 1
                continue
            if not 0.5 < sold / ask < 1.5:
                skipped["implausible ratio"] += 1
                continue
            rows.append((sold / ask * 100, sub, d.get("address"), ask, sold, sd))
    rows.sort()
    pct = [r[0] for r in rows]
    print(f"usable: n={len(rows)}   excluded: {sum(skipped.values())}")
    for k, v in skipped.most_common(6):
        print(f"    {v:5d}  {k}")
    if len(pct) < 8:
        print("\nnot enough to quartile."); return rows
    q1, q3 = st.quantiles(pct, n=4)[0], st.quantiles(pct, n=4)[2]
    bot = [p for p in pct if p <= q1]; top = [p for p in pct if p >= q3]
    print(f"\n  median % of asking achieved : {st.median(pct):.1f}%")
    print(f"  TOP quartile    (n={len(top):2d})      : {min(top):.1f}–{max(top):.1f}%  "
          f"(mean {st.mean(top):.1f}%)")
    print(f"  BOTTOM quartile (n={len(bot):2d})      : {min(bot):.1f}–{max(bot):.1f}%  "
          f"(mean {st.mean(bot):.1f}%)")
    d = st.mean(top) - st.mean(bot)
    print(f"  gap between quartile means   : {d:.1f} pct points")
    print(f"  on a $1,500,000 home         : ${d/100*1_500_000:,.0f}")
    print("\n  worst 5:")
    for r in rows[:5]:
        print(f"    {r[0]:6.1f}%  asked ${r[3]:>9,} sold ${r[4]:>9,}  {r[2]}")
    print("  best 5:")
    for r in rows[-5:]:
        print(f"    {r[0]:6.1f}%  asked ${r[3]:>9,} sold ${r[4]:>9,}  {r[2]}")
    return rows


# ───────────────────────────────────────────────────────────── verify one property
def verify(db, needle):
    """Dump everything a card claim might rest on, for one property."""
    for sub in SUBURBS:
        for d in db[sub].find({"address": {"$regex": needle, "$options": "i"}}):
            print("=" * 72)
            print(d.get("address"))
            for k in ("sale_price", "sold_date", "days_on_market", "days_on_market_source",
                      "land_size_sqm", "bedrooms", "bathrooms", "car_spaces",
                      "property_type", "listing_price"):
                if d.get(k) is not None:
                    print(f"  {k:24} {d[k]}")
            for k in ("domain_valuation_at_listing", "domain_valuation_accuracy"):
                if d.get(k):
                    print(f"  {k}:")
                    for kk, vv in d[k].items():
                        print(f"      {kk:20} {vv}")


def main():
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(dest="cmd", required=True)
    a = sub.add_parser("avm-misses"); a.add_argument("--months", type=int, default=8)
    a.add_argument("--limit", type=int, default=10)
    b = sub.add_parser("dom-pairs")
    b.add_argument("--months", type=int, default=12)
    b.add_argument("--fast-max", type=int, default=7)
    b.add_argument("--slow-min", type=int, default=40)
    b.add_argument("--land-tol", type=float, default=0.15)
    b.add_argument("--price-tol", type=float, default=0.20)
    b.add_argument("--apart-max", type=int, default=120)
    b.add_argument("--limit", type=int, default=8)
    c = sub.add_parser("asking-quartiles"); c.add_argument("--months", type=int, default=24)
    v = sub.add_parser("verify"); v.add_argument("--address", required=True)
    args = ap.parse_args()
    db = get_client()["Gold_Coast"]
    if args.cmd == "avm-misses":
        avm_misses(db, args.months, args.limit)
    elif args.cmd == "dom-pairs":
        dom_pairs(db, args.months, args.fast_max, args.slow_min, args.land_tol,
                  args.price_tol, args.apart_max, args.limit)
    elif args.cmd == "asking-quartiles":
        asking_quartiles(db, args.months)
    elif args.cmd == "verify":
        verify(db, args.address)


if __name__ == "__main__":
    main()
