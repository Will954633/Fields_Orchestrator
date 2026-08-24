#!/usr/bin/env python3
"""
build_arbitrage.py -- the "same money, what you get" comparison for the article's
Q3, computed from data rather than asserted.

Anchor: the Robina median house (our union median, n=265, with CI) sits on a median
655 m2 block (our own sold records, engine land-resolver). The subject sits on more.

Comparison: for the SAME money, what does a Sydney buyer get? We scan a basket of
Sydney suburbs on onthehouse (free, national, curl_cffi), compute each suburb's
median SOLD house price + median land + median distance-to-CBD (from per-record
lat/lon), then keep the suburbs whose median house price lands within a band around
Robina's ~$1.49M. The neutral fact that falls out is land-for-the-money: a same-
priced Sydney house sits on far less land, further out.

Framed as fact (median m2, distance), never as a knock on Sydney. Every figure is
dated and sourced (onthehouse sold, retrieved <date>; Robina from our union median).

    python3 build_arbitrage.py            # compute + write arbitrage_context.json
    python3 build_arbitrage.py --show
"""
from __future__ import annotations

import argparse
import json
import math
import os
import re
import sys
from datetime import datetime, timezone
from statistics import median

from curl_cffi import requests as cffi

HERE = os.path.dirname(os.path.abspath(__file__))
ORCH = "/home/fields/Fields_Orchestrator"
sys.path.insert(0, ORCH)
sys.path.insert(0, "/home/fields/Feilds_Website/07_Valuation_Comps")

OUT_PATH = os.path.join(HERE, "arbitrage_context.json")
SYD_CBD = (-33.8688, 151.2093)
HOUSE_TYPES = {"House", "Townhouse", "Terrace", "Duplex", "SemiDetached"}
ROBINA_MEDIAN_PRICE = 1_490_000          # our union median (precomputed_indexed_prices)
PRICE_BAND = 0.08                          # keep Sydney suburbs within +/-8% of that

# Candidate Sydney suburbs across the middle-to-outer rings where ~$1.49M is in play.
SYD_SUBURBS = [
    "kellyville-2155", "baulkham-hills-2153", "glenwood-2768", "quakers-hill-2763",
    "stanhope-gardens-2768", "the-ponds-2769", "rouse-hill-2155", "schofields-2762",
    "riverstone-2765", "marsfield-2122", "carlingford-2118", "west-ryde-2114",
    "winston-hills-2153", "seven-hills-2147", "toongabbie-2146", "girraween-2145",
    "castle-hill-2154", "cherrybrook-2126", "beecroft-2119", "eastwood-2122",
]


def _haversine(a, b):
    (lat1, lon1), (lat2, lon2) = a, b
    R = 6371.0
    p1, p2 = math.radians(lat1), math.radians(lat2)
    dp = math.radians(lat2 - lat1)
    dl = math.radians(lon2 - lon1)
    h = math.sin(dp/2)**2 + math.cos(p1)*math.cos(p2)*math.sin(dl/2)**2
    return 2 * R * math.asin(math.sqrt(h))


def _sold_records(state, suburb_pc):
    url = f"https://www.onthehouse.com.au/sold/{state}/{suburb_pc}"
    try:
        r = cffi.get(url, impersonate="chrome120", timeout=45)
    except Exception:
        return None
    if r.status_code != 200:
        return None
    html = r.text
    recs = []
    for m in re.finditer(r'\{"category":"Property"', html):
        i = m.start(); depth = 0
        for j in range(i, min(i + 9000, len(html))):
            if html[j] == "{":
                depth += 1
            elif html[j] == "}":
                depth -= 1
                if depth == 0:
                    try:
                        recs.append(json.loads(html[i:j+1]))
                    except Exception:
                        pass
                    break
    return recs


def _suburb_stats(state, suburb_pc):
    """Median sold house price / land / beds / distance-to-CBD for one suburb.
    Filtered to records whose OWN suburb matches (onthehouse pages bleed in
    neighbours). Returns None if too few priced houses."""
    target = suburb_pc.rsplit("-", 1)[0].replace("-", " ").upper()
    recs = _sold_records(state, suburb_pc)
    if recs is None:
        return None
    prices, lands, beds, dists = [], [], [], []
    for o in recs:
        addr = o.get("address") or {}
        if (addr.get("suburb") or "").upper() != target:
            continue
        if (o.get("type") or "") not in HOUSE_TYPES:
            continue
        sp = (o.get("lastSale") or {}).get("salePrice") or 0
        if not sp or sp < 50_000:
            continue
        prices.append(sp)
        if isinstance(o.get("landSize"), (int, float)) and 60 < o["landSize"] < 4000:
            lands.append(o["landSize"])
        if o.get("beds"):
            beds.append(o["beds"])
        loc = addr.get("location") or {}
        if loc.get("lat") and loc.get("lon"):
            dists.append(_haversine((loc["lat"], loc["lon"]), SYD_CBD))
    if len(prices) < 6:
        return None
    return {
        "suburb": target.title(),
        "median_price": int(median(prices)),
        "median_land": int(median(lands)) if lands else None,
        "median_beds": median(beds) if beds else None,
        "dist_cbd_km": round(median(dists), 1) if dists else None,
        "n_priced": len(prices),
        "n_land": len(lands),
    }


def build(verbose=False):
    now = datetime.now(timezone.utc)
    syd = []
    for pc in SYD_SUBURBS:
        s = _suburb_stats("nsw", pc)
        if verbose:
            print(f"  {pc}: {s}", file=sys.stderr)
        if s:
            syd.append(s)

    lo, hi = ROBINA_MEDIAN_PRICE * (1 - PRICE_BAND), ROBINA_MEDIAN_PRICE * (1 + PRICE_BAND)
    matched = [s for s in syd if lo <= s["median_price"] <= hi and s["median_land"]]
    matched.sort(key=lambda s: abs(s["median_price"] - ROBINA_MEDIAN_PRICE))

    # a robust "typical land for the money in Sydney" = median of matched suburbs' median land
    typ_land = int(median([s["median_land"] for s in matched])) if matched else None
    headline = matched[0] if matched else None

    data = {
        "_comment": "COMPUTED by build_arbitrage.py. Robina anchored on our union "
                    "median (precomputed_indexed_prices, n=265); Sydney from onthehouse "
                    "sold records (CoreLogic-backed), retrieved at retrieved_at. Present "
                    "as neutral 'same money, what you get' fact, never as a knock on Sydney.",
        "retrieved_at": now.isoformat(timespec="seconds"),
        "robina": {
            "median_price": ROBINA_MEDIAN_PRICE,
            "median_land": 655,          # our sold records, engine land-resolver, n=386
            "median_beds": 4,
            "subject_land": 907,
            "beach_km": 4.6,
            "price_source": "Fields union median (Domain + onthehouse), n=265",
            "land_source": "Fields sold records, n=386",
        },
        "price_band_pct": PRICE_BAND * 100,
        "sydney_matched": matched,
        "sydney_all": syd,
        "typical_sydney_land_for_price": typ_land,
        "headline_comparison": headline,
    }
    return data


def run(show=False, verbose=False):
    data = build(verbose)
    if not data["sydney_matched"]:
        raise RuntimeError("no Sydney suburb matched Robina's price band with land data "
                           "-- widen the candidate list or band before writing")
    with open(OUT_PATH, "w") as fh:
        json.dump(data, fh, indent=2)
        fh.write("\n")
    if show:
        print(json.dumps(data, indent=2))
    return data


def main():
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--show", action="store_true")
    ap.add_argument("--verbose", action="store_true")
    a = ap.parse_args()
    d = run(a.show, a.verbose)
    h = d["headline_comparison"]
    print(f"\nRobina ${d['robina']['median_price']:,} on {d['robina']['median_land']}m² | "
          f"typical matched-price Sydney land: {d['typical_sydney_land_for_price']}m² | "
          f"headline: {h['suburb']} ${h['median_price']:,} on {h['median_land']}m² "
          f"({h['dist_cbd_km']}km to CBD, n={h['n_priced']})", file=sys.stderr)
    return 0


if __name__ == "__main__":
    sys.exit(main())
