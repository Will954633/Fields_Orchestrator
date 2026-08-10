#!/usr/bin/env python3
"""unit_valuation.py — a comparable-sales range for an attached dwelling. (Plan F3/F4/F5)

WHY A PARALLEL METHOD AND NOT AN EXTENSION
------------------------------------------
The house method's own measurement is 10.3% MAE on houses and 18.0% on attached stock
that slipped through it. It is built around a floor-area adjustment because detached
houses are heterogeneous. Units are not: the same 2-bed in the same building is a
near-identical substitute. So this method changes the comparable, not the adjustment.

Measured on our own data before writing a line of this:

    same-complex, same-bed, time-adjusted, leave-one-out (n=4,093 / 281 cohorts)
        median abs error   9.07%      (house method, in-envelope: 8.2%)
        MAE               12.19%      (house method: 10.5%)
        within 10%         54.8%      (house method: 59%)

and reachability is what makes it viable: 85.8% of off-market units have a
same-complex priced sale, against 24.3% that have a same-complex FLOOR AREA donor.
That is why the comparable is the sale and not the $/m2 — floor area is a refinement
here, not a gate.

WHAT THIS REPLACES
------------------
`SlotResolver.valuation_model_range()` (Tier 3) queries
`{listing_status: "sold", bedrooms: N}` with NO property_type clause and takes the
median +/-10%. For a 3-bed unit that is a 3-bed HOUSE median: measured +23% in Robina
and +33% in Varsity Lakes. See fix-history [OFFMARKET-UNIT-THIN-RANGE-HOUSE-COMPS].
This module refuses where that one guessed.

REFUSAL IS A VALID OUTPUT. Per CLAUDE.md the page may not "borrow a track record this
home's figure has not earned". If the class-matched pool is too thin, return a decline
with a reason - never widen the net until a number appears.
"""
from __future__ import annotations

import re
import statistics as st
from collections import defaultdict

from shared.dwelling_type import classify_dwelling

MIN_COMPS = 3
PREFERRED_COMPS = 12
MAX_AGE_YEARS = 8          # outer bound; MAX_UPLIFT is the real constraint
# ⚠ A SALE THAT NEEDS A HUGE UPLIFT IS NOT EVIDENCE, IT IS AN INDEX PROJECTION.
# Found by reading a rendered page: 1/23 Thorngate Drive priced off four comps, three
# of them 4-6 years old, including a 2020 sale of $334,300 carried to $718,962 — a
# +115% adjustment. The published number would have been mostly index, presented to the
# reader as "the sales it is built from". Anything past this threshold is dropped and
# the drop is DISCLOSED, because a quietly smaller comp set looks identical to a
# genuinely thin one.
MAX_UPLIFT = 0.60          # +60%: roughly three years of the fastest attached growth
OLD_COMP_YEARS = 3         # beyond this a comp is disclosed as leaning on the index
BAND_PCT = 19.8            # measured P80 error of this method - NOT a confidence interval
_TIERS = ("same_complex_same_beds", "same_complex_any_beds",
          "same_subtype_same_beds_suburb")


def _num(v):
    if v is None:
        return None
    if isinstance(v, (int, float)):
        return float(v) or None
    s = re.sub(r"[^0-9.]", "", str(v))
    try:
        f = float(s)
    except ValueError:
        return None
    return f or None


def _year(s):
    m = re.search(r"(19|20)\d{2}", str(s or ""))
    return int(m.group(0)) if m else None


def _quarter(s):
    m = re.match(r"(\d{4})-(\d{2})", str(s or ""))
    if not m:
        return None
    return f"{m.group(1)}-Q{(int(m.group(2)) - 1) // 3 + 1}"


class UnitValuer:
    """Holds the suburb's attached index so a batch run deflates consistently."""

    def __init__(self, gc, suburb_key):
        self.gc = gc
        self.suburb = suburb_key
        s = gc["unit_market_series"].find_one({"_id": suburb_key}) or {}
        self.index = {r["period"]: r["rolling_median"]
                      for r in (s.get("rolling_12m") or [])}
        # Per-bedroom indices. The all-attached headline is MIX-CONTAMINATED: on Robina
        # it rose 35% over two years while 2-bed rose 18% and 3-bed 29%, because the mix
        # shifted toward larger dwellings. Deflating a 2-bed by the headline inflated a
        # real 2024 sale by 43%. Always prefer the bedroom-matched series.
        self.bed_index = {b: {r["period"]: r["rolling_median"] for r in rows}
                          for b, rows in (s.get("rolling_12m_by_bedrooms") or {}).items()}
        self.latest_period = s.get("latest_period")
        self.latest_median = s.get("latest_rolling_median")
        # The current quarter is PARTIAL - its rolling window is short (n=45 against
        # 68-73 for complete quarters) and its median moves on whatever happened to
        # settle early. Deflating TO it inflates every comparable. The headline already
        # excludes it; the deflator has to as well, or the two disagree.
        self.in_progress = s.get("in_progress_period")
        self._cache = {}

    def _usable(self, idx):
        return {p: v for p, v in idx.items() if p != self.in_progress} or idx

    # -- deflation ---------------------------------------------------------
    def _pick_index(self, beds):
        """Bedroom-matched index if it exists and covers the period; else the headline,
        flagged so the caller can say which was used."""
        if beds is not None:
            idx = self._usable(self.bed_index.get(str(int(beds))) or {})
            if idx and len(idx) >= 8:
                return idx, f"{int(beds)}-bedroom attached index"
        return self._usable(self.index), "all-attached index (mix-sensitive)"

    def deflate(self, price, date, beds=None):
        """Bring a past sale to today using the ATTACHED index, bedroom-matched where
        possible - never the house index.

        Returns (adjusted, factor, basis) or (None, None, reason). A sale we cannot
        deflate is DROPPED, not passed through at face value - an undeflated 2019 sale
        silently drags the answer down and looks identical to a correct one.
        """
        q = _quarter(date)
        if not q:
            return None, None, "no date"
        idx, label = self._pick_index(beds)
        if not idx:
            return None, None, "no attached index for this suburb"
        periods = sorted(idx)
        base = idx.get(q)
        if base is None:
            earlier = [p for p in periods if p <= q]
            if not earlier:
                return None, None, "sale predates the index"
            base = idx[earlier[-1]]
        # Deflate TO the same index's latest point, not to a different series' latest -
        # mixing bases is how a 43% adjustment appeared where growth was 18%.
        now = idx[periods[-1]]
        if not base or not now:
            return None, None, "index gap"
        return price * (now / base), now / base, label

    # -- comparable pools --------------------------------------------------
    def _sales_in(self, query, subject_id=None):
        proj = {"street_address": 1, "address": 1, "complete_address": 1,
                "property_type": 1, "classified_property_type": 1, "bedrooms": 1,
                "bathrooms": 1, "sale_price": 1, "sold_date": 1, "listing_status": 1,
                "complex_plan": 1, "complex_cms": 1, "complex_name_cadastre": 1,
                "scraped_data.features.property_type": 1,
                "scraped_data_v2.property_type": 1,
                "scraped_data.property_timeline": 1,
                "enriched_data.transactions": 1,
                "floor_area_sqm": 1, "internal_living_area_sqm": 1,
                "enriched_data.floor_area_sqm": 1}
        out = []
        for d in self.gc[self.suburb].find(query, proj):
            if subject_id is not None and d["_id"] == subject_id:
                continue
            eff = (d.get("street_address") or d.get("address")
                   or d.get("complete_address") or "")
            if classify_dwelling({**d, "street_address": eff}) != "attached":
                continue
            events = []
            for t in ((d.get("enriched_data") or {}).get("transactions") or []):
                if isinstance(t, dict):
                    events.append((t.get("date"), t.get("price")))
            for e in ((d.get("scraped_data") or {}).get("property_timeline") or []):
                if isinstance(e, dict) and e.get("is_sold"):
                    events.append((e.get("date"), e.get("price")))
            if d.get("listing_status") == "sold":
                events.append((d.get("sold_date"), d.get("sale_price")))
            best = None
            for date, price in events:
                p, y = _num(price), _year(date)
                if not p or not y:
                    continue
                if best is None or str(date) > str(best[0]):
                    best = (str(date)[:10], p)
            if not best:
                continue
            out.append({"address": eff, "date": best[0], "price": best[1],
                        "beds": d.get("bedrooms"), "baths": d.get("bathrooms"),
                        "floor": (_num(d.get("floor_area_sqm"))
                                  or _num(d.get("internal_living_area_sqm"))
                                  or _num((d.get("enriched_data") or {}).get("floor_area_sqm"))),
                        "complex": d.get("complex_name_cadastre"),
                        "plan": d.get("complex_plan")})
        return out

    def comparables(self, subject):
        """Walk the tiers outward and STOP at the first that clears MIN_COMPS.

        Walking further would find more sales but worse ones - the whole premise is
        that a same-complex same-bed sale is a better comparable than a nearer-in-time
        one from another building. The tier actually used is reported, because a
        reader is entitled to know whether their figure came from their own building.
        """
        sid = subject.get("_id")
        beds = subject.get("bedrooms")
        plan = subject.get("complex_plan")
        cms = subject.get("complex_cms")
        cutoff = None
        tried = []

        def fresh(rows):
            now = 2026
            return [r for r in rows if _year(r["date"]) and now - _year(r["date"]) <= MAX_AGE_YEARS]

        scope = {}
        if cms:
            scope = {"complex_cms": cms}
        elif plan:
            scope = {"complex_plan": plan}

        if scope and beds:
            rows = fresh(self._sales_in({**scope, "bedrooms": beds}, sid))
            tried.append(("same_complex_same_beds", len(rows)))
            if len(rows) >= MIN_COMPS:
                return rows, "same_complex_same_beds", tried
        if scope:
            rows = fresh(self._sales_in(dict(scope), sid))
            tried.append(("same_complex_any_beds", len(rows)))
            if len(rows) >= MIN_COMPS:
                return rows, "same_complex_any_beds", tried
        if beds and subject.get("complex_subtype"):
            rows = fresh(self._sales_in(
                {"complex_subtype": subject["complex_subtype"], "bedrooms": beds}, sid))
            tried.append(("same_subtype_same_beds_suburb", len(rows)))
            if len(rows) >= MIN_COMPS:
                return rows[:80], "same_subtype_same_beds_suburb", tried
        return [], None, tried

    # -- the range ---------------------------------------------------------
    def value(self, subject):
        comps, tier, tried = self.comparables(subject)
        if not comps:
            return {"method": "declined", "decline_reason": "no_class_matched_comparables",
                    "tried": tried,
                    "explain": ("No sale in this scheme, and too few same-type sales of "
                                "this size in the suburb, to support a range.")}
        adj, dropped, over = [], 0, 0
        for c in comps:
            a, factor, basis = self.deflate(c["price"], c["date"], c.get("beds"))
            if a is None:
                dropped += 1
                continue
            if factor is not None and factor - 1 > MAX_UPLIFT:
                over += 1
                continue
            adj.append({**c, "adjusted": a, "factor": factor, "basis": basis})
        if len(adj) < MIN_COMPS:
            return {"method": "declined",
                    "decline_reason": ("comparables_too_old" if over else
                                       "comparables_not_deflatable"),
                    "tried": tried, "dropped": dropped, "dropped_too_old": over,
                    "explain": ("Sales exist in this scheme but the attached price index "
                                "does not reach far enough back to bring them to today.")}
        adj.sort(key=lambda r: r["date"], reverse=True)
        used = adj[:PREFERRED_COMPS]
        prices = sorted(r["adjusted"] for r in used)
        point = st.median(prices)
        return {
            "method": "same_complex_comparables",
            "tier": tier,
            "point": int(point),
            "low": int(point * (1 - BAND_PCT / 100)),
            "high": int(point * (1 + BAND_PCT / 100)),
            "band_pct": BAND_PCT,
            "n_comps": len(used),
            "n_available": len(adj),
            "dropped_undeflatable": dropped,
            "dropped_too_old": over,
            "old_comp_share": round(
                sum(1 for r in used
                    if _year(r["date"]) and 2026 - _year(r["date"]) > OLD_COMP_YEARS)
                / max(1, len(used)), 2),
            "comparables": [{"address": r["address"], "date": r["date"],
                             "sold": int(r["price"]), "adjusted": int(r["adjusted"]),
                             "beds": r["beds"], "complex": r["complex"]}
                            for r in used],
            "tried": tried,
            "band_basis": (f"±{BAND_PCT}% is the measured P80 error of this method on "
                           f"leave-one-out testing (n=4,093). It is NOT a statistical "
                           f"confidence interval and is NOT yet a published figure — "
                           f"it needs a production-shaped backtest first."),
        }

    # -- floor area (F4) ---------------------------------------------------
    def impute_floor_area(self, subject):
        """Same-complex, same-bed median. Measured 5.2% median error / 67% within 10%,
        against 15.9% / 28% for a suburb-wide same-bed median. Always returned as
        DERIVED — an imputed figure must never be presented as a measured one."""
        beds = subject.get("bedrooms")
        scope = ({"complex_cms": subject.get("complex_cms")} if subject.get("complex_cms")
                 else {"complex_plan": subject.get("complex_plan")}
                 if subject.get("complex_plan") else None)
        if not scope or not beds:
            return None
        rows = [r["floor"] for r in self._sales_in({**scope, "bedrooms": beds},
                                                   subject.get("_id")) if r.get("floor")]
        # also take non-sold neighbours - a floor area does not require a sale
        proj = {"floor_area_sqm": 1, "internal_living_area_sqm": 1,
                "enriched_data.floor_area_sqm": 1}
        for d in self.gc[self.suburb].find({**scope, "bedrooms": beds}, proj):
            if d["_id"] == subject.get("_id"):
                continue
            f = (_num(d.get("floor_area_sqm")) or _num(d.get("internal_living_area_sqm"))
                 or _num((d.get("enriched_data") or {}).get("floor_area_sqm")))
            if f and 20 < f < 400:
                rows.append(f)
        if len(rows) < 2:
            return None
        return {"value": round(st.median(rows)), "n": len(rows), "derived": True,
                "basis": f"median of {len(rows)} same-bedroom dwellings in this scheme",
                "accuracy": "5.2% median error on leave-one-out testing (n=424)"}
