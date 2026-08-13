#!/usr/bin/env python3
"""statutory_comparables.py — the SECOND comparable set: recent sales nearby.

WHY A SECOND SET RATHER THAN A REPLACEMENT
------------------------------------------
Our primary set prefers a sale in the SAME BUILDING over a more recent sale somewhere
else, because two 2-bedroom homes in one complex are near-identical in a way two detached
houses never are. That is the better comparison and it is why the method measures a 6.3%
median error in Robina against the house engine's 8.2%.

But it is not the STATUTORY comparison. A Comparative Market Analysis under the Property
Occupations Act 2014 (Qld) Sch 2 means at least three sales:
    * within the previous SIX MONTHS,
    * of property of a similar standard or condition,
    * within a 5km radius.
82.6% of our same-complex comparables are older than six months, so the primary set does
not satisfy it — which is exactly what the page's disclaimer says.

This module builds the statutory set alongside it. The page then shows both, and the
reader can see the trade the method is making instead of being asked to trust it. It also
means a compliant CMA already exists the moment a seller asks, rather than being something
we would have to go and construct.

⚠ SAME BEDROOM COUNT IS REQUIRED, NOT PREFERRED.
The obvious way to lift coverage is to accept a 3-bedroom comparable for a 2-bedroom
subject and adjust by the observed bedroom step (Robina medians: 1bd $712,500, 2bd
$870,000, 3bd $1,090,000, 4bd $1,315,000 — a fairly stable ~1.22-1.25x per bedroom).
We do NOT do this. Those medians conflate bedroom count with everything correlated with
it: floor area, car spaces, aspect, building age. Adjusting a 3-bed down by 22% to stand
for a 2-bed prices the bedroom AND silently prices all of that, so the "adjustment" is
mostly the confound. Requiring the same bedroom count costs coverage and buys a
comparable that is actually comparable. Where we cannot find three, we decline — the same
posture as the primary method.

⚠ DISTANCE IS SCHEME-TO-SCHEME. See ingest_scheme_centroids.py: per-unit coordinates exist
on 0.7% of indexed stock, and a geocode of `12/45 Smith St` resolves to the street anyway.
Every home in one building shares one location, so the scheme centroid is the correct
geometry here, not a substitute for a missing one.
"""
from __future__ import annotations

import math
import re
import statistics as st

from shared.dwelling_type import classify_dwelling
from unit_valuation import (bedrooms_of, sale_price, _year, _num,
                            plausible_for_scheme, dedupe_sales)

RADIUS_KM = 5.0            # POA Sch 2
WINDOW_MONTHS = 6          # POA Sch 2
MIN_COMPS = 3              # POA Sch 2 ("at least 3 comparable sales")
MAX_SHOW = 8
# A floor-area adjustment is only credible over a modest span; beyond it the homes are
# different products, not the same product in a different size.
FLOOR_ADJ_MAX = 0.25
FLOOR_ADJ_RATE = 0.55      # $ moves ~0.55x the proportional floor-area difference

_SUBURB_COLLECTIONS = ("robina", "varsity_lakes", "burleigh_waters")


def haversine_km(lat1, lon1, lat2, lon2):
    R = 6371.0
    p1, p2 = math.radians(lat1), math.radians(lat2)
    dp = math.radians(lat2 - lat1)
    dl = math.radians(lon2 - lon1)
    h = math.sin(dp / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(dl / 2) ** 2
    return 2 * R * math.asin(math.sqrt(h))


def _months_between(iso_a, iso_b):
    """Whole months from iso_a to iso_b, both YYYY-MM-DD."""
    try:
        ya, ma = int(iso_a[:4]), int(iso_a[5:7])
        yb, mb = int(iso_b[:4]), int(iso_b[5:7])
    except (ValueError, TypeError):
        return None
    return (yb - ya) * 12 + (mb - ma)


class StatutoryComparables:
    """Builds the 5km / 6-month set. One instance per run, pool loaded once.

    The pool spans ALL THREE suburb collections, not just the subject's own: the three
    suburbs sit within 4.04km of each other (Robina->Burleigh Waters, measured from the
    cadastral centroids), so a 5km radius genuinely crosses them. Scoping to one
    collection would silently apply a suburb filter the Act does not ask for and would
    drop the nearest sales for anyone near a boundary.
    """

    def __init__(self, gc, today_iso, valuers=None):
        self.gc = gc
        self.today = today_iso
        self.valuers = valuers or {}
        self.centroids = {}
        for d in gc["complexes"].find(
                {}, {"plan": 1, "suburb_key": 1, "centroid_lat": 1, "centroid_lon": 1}):
            if d.get("centroid_lat") is not None:
                self.centroids[d["_id"]] = (d["centroid_lat"], d["centroid_lon"])
        self.pool = self._load_pool()

    # -- location ---------------------------------------------------------
    def locate(self, suburb_key, plan):
        if not plan:
            return None
        return self.centroids.get(f"{suburb_key}:{plan}")

    # -- the recent-sale pool ---------------------------------------------
    def _load_pool(self):
        """Every attached sale in the last WINDOW_MONTHS, across all three suburbs."""
        proj = {"url_slug": 1, "address": 1, "complete_address": 1, "street_address": 1,
                "property_type": 1, "classified_property_type": 1, "bedrooms": 1,
                "scraped_data.features.property_type": 1,
                "scraped_data_v2.property_type": 1,
                "scraped_data.features.bedrooms": 1, "scraped_data_v2.bedrooms": 1,
                "scraped_data_apr01_recovered.features.bedrooms": 1,
                "property_valuation_data.layout.number_of_bedrooms": 1,
                "bathrooms": 1, "sale_price": 1, "sold_date": 1, "listing_status": 1,
                "complex_plan": 1, "complex_cms": 1,
                "scraped_data.property_timeline": 1,
                "enriched_data.transactions": 1,
                "floor_area_sqm": 1, "internal_living_area_sqm": 1,
                "enriched_data.floor_area_sqm": 1}
        rows = []
        for suburb in _SUBURB_COLLECTIONS:
            for d in self.gc[suburb].find({}, proj):
                eff = (d.get("address") or d.get("complete_address")
                       or d.get("street_address") or "")
                if classify_dwelling({**d, "street_address": eff}) != "attached":
                    continue
                plan = d.get("complex_plan")
                loc = self.locate(suburb, plan)
                if not loc:
                    continue
                beds = bedrooms_of(d)
                if not beds:
                    continue          # cannot satisfy "similar standard" without it
                for date, price in self._sales_of(d):
                    m = _months_between(date, self.today)
                    if m is None or m < 0 or m > WINDOW_MONTHS:
                        continue
                    rows.append({
                        "slug": d.get("url_slug"), "address": eff, "date": date,
                        "price": price, "beds": beds, "baths": d.get("bathrooms"),
                        "plan": plan, "suburb": suburb, "lat": loc[0], "lon": loc[1],
                        "floor": (_num(d.get("floor_area_sqm"))
                                  or _num(d.get("internal_living_area_sqm"))
                                  or _num((d.get("enriched_data") or {}).get("floor_area_sqm"))),
                    })
        return self._dedupe(rows)

    @staticmethod
    def _dedupe(rows):
        """One row per real-world sale.

        ⚠ DEDUPLICATING WITHIN A DOCUMENT IS NOT ENOUGH. `_sales_of` already collapses the
        same sale arriving from `transactions`, the timeline and the sold fields. But the
        SAME sale also arrives from separate DOCUMENTS — the off-market discovery
        duplicate-document problem is known and unfixed, so one dwelling can hold two
        records with different `_id`s and the same address.

        Caught in review: a first run put "1/29 Mountain Ash Circuit" in one comparable set
        twice, same date, same $1,300,000. A duplicate is worse than a missing comparable
        because it silently DOUBLE-WEIGHTS one sale in the median while the count says the
        evidence is broader than it is. Keyed on address + date + price rather than on
        document id, because the document is the thing that is duplicated.
        """
        seen, out = set(), []
        for r in rows:
            key = (re.sub(r"[^a-z0-9]", "", (r["address"] or "").lower()),
                   r["date"], int(r["price"]))
            if key in seen:
                continue
            seen.add(key)
            out.append(r)
        return out

    @staticmethod
    def _sales_of(doc):
        """Every recorded sale, through the ONE price parser.

        sale_price() applies the sanity band on every branch. That is not defensive
        styling: the same three modules once counted weekly RENTS as sales because the
        parser checked the band only on the string branch and returned numerics
        unchecked — 1,044 of Robina's 8,316 attached "sales" were rents, and the
        backtest read 4,171% MAE before anyone noticed.
        """
        out = []
        for t in ((doc.get("enriched_data") or {}).get("transactions") or []):
            if isinstance(t, dict):
                p = sale_price(t.get("price"))
                if p:
                    out.append((str(t.get("date") or "")[:10], p))
        for e in ((doc.get("scraped_data") or {}).get("property_timeline") or []):
            if isinstance(e, dict) and e.get("is_sold"):
                p = sale_price(e.get("price"))
                if p:
                    out.append((str(e.get("date") or "")[:10], p))
        if doc.get("listing_status") == "sold":
            p = sale_price(doc.get("sale_price"))
            if p:
                out.append((str(doc.get("sold_date") or "")[:10], p))
        # dedupe_sales, not set(): the same sale arrives under two DATES from
        # different sources, so exact-tuple dedupe misses it entirely.
        return dedupe_sales([(d, p) for d, p in out if len(d) == 10])

    # -- choosing WHICH sales are the comparable ones ----------------------
    def _most_comparable(self, rows, subject, keep=12):
        """Rank by observable similarity and keep the closest matches.

        "Within 5km in the last six months" is a catchment, not a comparable set. In our
        three suburbs it returns a median of 25 sales spanning 72% of the median price,
        because a 2-bedroom home beside the beach in Burleigh Waters and a 2-bedroom
        townhouse in western Robina are both "a 2-bedroom attached dwelling within 5km".
        The Act asks for comparable sales; handing over the whole catchment would be
        padding the count with sales we know are not comparable.

        ⚠ THE SCORE MUST NOT CONTAIN PRICE, DIRECTLY OR INDIRECTLY.
        Ranking comparables by how close their price sits to an expected value — or to
        the pool median — selects the evidence to agree with the answer and then reports
        the agreement as accuracy. Our own house selector already scores comps on
        closeness to the MEDIAN, which is why its backtest flatters it. Everything below
        is a property of the HOME (distance, size, bathrooms) or of the SALE DATE. A
        reader could verify every term without knowing what anything sold for.
        """
        subj_floor = (_num(subject.get("floor_area_sqm"))
                      or _num(subject.get("internal_living_area_sqm"))
                      or _num((subject.get("enriched_data") or {}).get("floor_area_sqm")))
        subj_baths = _num(subject.get("bathrooms"))

        def score(r):
            s = r["km"] / RADIUS_KM                       # 0 at the door, 1 at the limit
            if subj_floor and r.get("floor"):
                s += min(1.0, abs(subj_floor - r["floor"]) / subj_floor) * 1.5
            else:
                s += 0.35                                  # unknown size is a real penalty
            if subj_baths and _num(r.get("baths")):
                s += min(1.0, abs(subj_baths - _num(r["baths"])) * 0.5)
            m = _months_between(r["date"], self.today) or 0
            s += (m / WINDOW_MONTHS) * 0.4                 # recency, gently
            return s

        return sorted(rows, key=score)[:keep]

    # -- the set ----------------------------------------------------------
    def for_subject(self, subject, suburb_key):
        """Returns the statutory set for one home, or a stated reason it cannot be built."""
        plan = subject.get("complex_plan")
        loc = self.locate(suburb_key, plan)
        if not loc:
            return {"available": False, "reason": "no_location",
                    "explain": "This home's scheme could not be located in the cadastre, "
                               "so a distance test cannot be applied."}
        beds = bedrooms_of(subject)
        if not beds:
            return {"available": False, "reason": "no_bedrooms",
                    "explain": "We do not hold a bedroom count for this home, so we "
                               "cannot match it to sales of a similar standard."}

        sid = subject.get("url_slug")
        near = []
        for r in self.pool:
            if r["beds"] != beds:
                continue                      # same bedroom count is required — see module docstring
            if r["slug"] and r["slug"] == sid:
                continue                      # never comp a home against itself
            km = haversine_km(loc[0], loc[1], r["lat"], r["lon"])
            if km > RADIUS_KM:
                continue
            near.append({**r, "km": round(km, 2)})

        if len(near) >= 4:
            med = st.median([r["price"] for r in near])
            near = [r for r in near if plausible_for_scheme(r["price"], med)]

        near = self._most_comparable(near, subject)

        if len(near) < MIN_COMPS:
            return {"available": False, "reason": "insufficient_recent_sales",
                    "n_found": len(near), "beds": beds,
                    "explain": (f"Only {len(near)} sale{'' if len(near) == 1 else 's'} of a "
                                f"{beds}-bedroom attached home settled within 5km in the last "
                                f"six months — fewer than the three a Comparative Market "
                                f"Analysis requires.")}

        # Adjust each sale to this home. Inside a six-month window the time component is
        # small by construction, which is the whole point of the statutory test.
        adjusted = []
        subj_floor = (_num(subject.get("floor_area_sqm"))
                      or _num(subject.get("internal_living_area_sqm"))
                      or _num((subject.get("enriched_data") or {}).get("floor_area_sqm")))
        V = self.valuers.get(suburb_key)
        for r in sorted(near, key=lambda x: (x["km"], -_iso_key(x["date"]))):
            price = r["price"]
            notes = []
            if V is not None:
                out, factor, _basis = V.deflate(price, r["date"], beds)
                if out:
                    price = out
                    if factor and abs(factor - 1) >= 0.005:
                        notes.append(f"{(factor - 1) * 100:+.1f}% for timing")
            if subj_floor and r.get("floor"):
                diff = (subj_floor - r["floor"]) / r["floor"]
                if abs(diff) <= FLOOR_ADJ_MAX:
                    adj = diff * FLOOR_ADJ_RATE
                    price *= (1 + adj)
                    if abs(adj) >= 0.005:
                        notes.append(f"{adj * 100:+.1f}% for floor area")
            adjusted.append({
                "address": r["address"], "date": r["date"], "beds": r["beds"],
                "km": r["km"], "sold": int(round(r["price"])),
                "adjusted": int(round(price)),
                "adjustments": ", ".join(notes) if notes else "no adjustment needed",
            })

        vals = sorted(a["adjusted"] for a in adjusted)
        return {
            "available": True,
            "n_comps": len(adjusted),
            "beds": beds,
            "radius_km": RADIUS_KM,
            "window_months": WINDOW_MONTHS,
            "low": vals[0],
            "high": vals[-1],
            "median": int(st.median(vals)),
            "comparables": adjusted[:MAX_SHOW],
            "n_shown": min(len(adjusted), MAX_SHOW),
            "basis": ("at least three sales of the same bedroom count, settled within six "
                      "months, within a 5km radius, each adjusted to this home"),
        }


def _iso_key(d):
    try:
        return int(str(d)[:4] + str(d)[5:7] + str(d)[8:10])
    except (ValueError, TypeError):
        return 0
