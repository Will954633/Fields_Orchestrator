#!/usr/bin/env python3
"""
build_owner_article.py -- generate the OWNER-SUBJECT article for one address.

What this is
------------
A short printed piece about ONE off-market home, posted to that address. The
reader owns it and did not ask for us to write it. It sets recent nearby sales,
each adjusted to their home, against the national headlines, and stops there.

  * The RANGE of adjusted comparables is the valuation. Never a single figure,
    never in a headline.
  * No CTA, no invitation, no mention of selling or appraisals. Reading as
    solicitation is the failure mode for unsolicited mail about someone's home.
  * No confidence grade. Measured across 512 sold homes the label is
    non-discriminating (high 56.0% range-hit vs medium 57.5%), so printing it
    would tell the reader something untrue about how much to trust the number.

Copy is composed deterministically in Python rather than by an LLM. That is what
makes `factbook.verify()` meaningful: every figure on the page is minted from the
data bundle, and any figure that is not fails the build. It also makes a run
reproducible and free.

    python3 build_owner_article.py --address "20 Heidelberg Circuit, Robina"
    python3 build_owner_article.py --address "..." --out-dir /path --html
    python3 build_owner_article.py --list-candidates --suburb robina --limit 20

Exit codes: 0 ok - 2 subject rejected by a guard - 3 failed fact-check/guardrails.
"""
from __future__ import annotations

import argparse
import json
import os
import re
import sys
from datetime import datetime, timedelta, timezone
from statistics import median

HERE = os.path.dirname(os.path.abspath(__file__))
ORCH = "/home/fields/Fields_Orchestrator"
sys.path.insert(0, ORCH)
sys.path.insert(0, os.path.join(ORCH, "scripts"))
sys.path.insert(0, "/home/fields/Feilds_Website/07_Valuation_Comps")

from factbook import FactBook                                  # noqa: E402
import guardrails                                              # noqa: E402
import charts as charts_mod                                    # noqa: E402
import variants as variants_mod                                # noqa: E402

# ---------------------------------------------------------------- constants

SUBURBS = ["robina", "varsity_lakes", "burleigh_waters"]

# Design envelope. Outside this band the method cannot go -- a weighted mean of
# adjusted comparables can never exceed its priciest comparable, and the pool is
# dominated by mid-market sales. See memory valuation_design_envelope.
ENVELOPE_MIN = 1_000_000
ENVELOPE_MAX = 2_000_000

# Comp distance p90 across 1,197 sampled homes is 2.04 km, so 2.0 km keeps ~89%
# of comps and removes the tail that produced "near your street" over 2.5 km.
RADIUS_KM = 2.0
RADIUS_MAX_KM = 3.0
RADIUS_STEP_KM = 0.5
MIN_COMPS = 4

# Measured accuracy INSIDE the envelope, backtest run with --price-filter none
# (the default `sale` anchor prunes comps using the subject's own sale price --
# target leakage). Robina n=278. See CLAUDE.md Valuation System.
MAE_PCT = 10.5


# ---------------------------------------------------------------- helpers

def _upper1(s: str) -> str:
    """Capitalise the first letter ONLY. str.capitalize() lower-cases the rest,
    which would quietly de-capitalise street names later in the sentence."""
    return s[:1].upper() + s[1:] if s else s


def slugify(address: str) -> str:
    s = re.sub(r"[,]", "", address.lower())
    s = re.sub(r"\bqld\b|\b\d{4}\b", "", s)
    return re.sub(r"-+", "-", re.sub(r"[^a-z0-9]+", "-", s)).strip("-")


def fmt_date(value) -> str | None:
    """'2026-05-05' or ms-epoch -> '5 May 2026'."""
    dt = None
    if isinstance(value, (int, float)):
        dt = datetime.fromtimestamp(value / 1000, tz=timezone.utc)
    elif isinstance(value, str):
        for f in ("%Y-%m-%d", "%Y-%m-%dT%H:%M:%S"):
            try:
                dt = datetime.strptime(value[:19] if "T" in value else value, f)
                break
            except ValueError:
                continue
    elif isinstance(value, datetime):
        dt = value
    if not dt:
        return None
    return f"{dt.day} {dt.strftime('%B %Y')}"


def parse_date(value) -> datetime | None:
    if isinstance(value, (int, float)):
        return datetime.fromtimestamp(value / 1000, tz=timezone.utc).replace(tzinfo=None)
    if isinstance(value, datetime):
        return value.replace(tzinfo=None)
    if isinstance(value, str):
        for f in ("%Y-%m-%d", "%Y-%m-%dT%H:%M:%S"):
            try:
                return datetime.strptime(value[:19] if "T" in value else value, f)
            except ValueError:
                continue
    return None


# ---------------------------------------------------------------- data layer

def get_db():
    from shared.db import get_client
    return get_client()


def resolve_subject(client, address: str, suburb: str | None = None):
    """Find the subject document. Returns (doc, suburb_key)."""
    gc = client["Gold_Coast"]
    street = address.split(",")[0].strip()
    rx = {"$regex": f"^{re.escape(street)}", "$options": "i"}
    for key in ([suburb] if suburb else SUBURBS):
        doc = gc[key].find_one({"address": rx}) or gc[key].find_one({"complete_address": rx})
        if doc:
            return doc, key
    return None, None


def guard_subject(client, doc, suburb_key, skip_market_check=False) -> list[str]:
    """Reasons this address must NOT receive the article. Empty == clear."""
    reasons = []
    addr = doc.get("address") or doc.get("complete_address") or ""

    status = (doc.get("listing_status") or "").lower()
    if status in ("for_sale", "under_contract"):
        reasons.append(f"our records show listing_status={status!r} -- do not mail a listed home")

    vd = doc.get("valuation_data") or {}
    if not vd:
        reasons.append("no valuation_data on the document")
        return reasons
    if (vd.get("metadata") or {}).get("directional_only"):
        reasons.append("valuation is directional_only -- outside the design envelope")

    comps = vd.get("adjusted_comparables") or []
    if len(comps) < MIN_COMPS:
        reasons.append(f"only {len(comps)} adjusted comparables (need {MIN_COMPS})")

    # Envelope test on the EVIDENCE, not on a stored point estimate.
    adj = [c.get("adjusted_price") for c in comps if c.get("adjusted_price")]
    if adj:
        mid = (min(adj) + max(adj)) / 2
        if not (ENVELOPE_MIN <= mid <= ENVELOPE_MAX):
            reasons.append(
                f"adjusted-comparable midpoint ${mid:,.0f} is outside the "
                f"${ENVELOPE_MIN:,}-${ENVELOPE_MAX:,} design envelope")

    # PropRadar: covers every suburb and answers "is it listed with someone else".
    if not skip_market_check:
        try:
            from propradar import market_status
            st = market_status.check(addr, db=client["system_monitor"])
            ok, why = market_status.verdict(st)
            if not ok:
                reasons.append(f"PropRadar: {why}")
        except Exception as e:            # never let the guard's own failure pass a home
            reasons.append(f"market-status check could not run ({type(e).__name__}: {e})")
    return reasons


def select_comps(vd: dict) -> tuple[list[dict], float, bool]:
    """Radius-filtered comparables.

    The engine has no radius filter -- distance is only a WEIGHT, decaying
    linearly to zero at 5 km. That is why a prototype claimed "near your street"
    over comps reaching 2.57 km. Here distance is a hard gate, widened in steps
    only if too few remain, and the copy always states the true span.

    Returns (comps sorted by adjusted price, radius used, whether it widened).
    """
    comps = [c for c in (vd.get("adjusted_comparables") or [])
             if c.get("adjusted_price") and c.get("distance_km") is not None]
    radius = RADIUS_KM
    while radius <= RADIUS_MAX_KM:
        kept = [c for c in comps if c["distance_km"] <= radius]
        if len(kept) >= MIN_COMPS:
            return sorted(kept, key=lambda c: c["adjusted_price"]), radius, radius > RADIUS_KM
        radius = round(radius + RADIUS_STEP_KM, 1)
    return [], RADIUS_MAX_KM, True


UNION_SOURCE = "domain_union_onthehouse"


def suburb_median_series(client, suburb_key: str) -> dict | None:
    """Rolling 12-month house median + YoY, read from the promoted union pipeline.

    This used to recompute the median here from `Gold_Coast.<suburb>` sold records.
    That was wrong in a way that mattered, because this article is POSTED to the
    owner's address:

      * it read Domain-only sold events, the source we know misses 40-50% of real
        sales, while `precompute_union_prices.py` builds the median from the
        Domain u onthehouse union (see memory `union_median_pipeline`);
      * it classified dwellings by substring on `property_type`, a different
        classifier from the union pipeline's, so it was a different population;
      * it carried no CI and no provenance, and the copy called the result
        "independently measured" -- which reads to an owner as corroborated when it
        meant the opposite;
      * `check_union_median_integrity.py` guards `precomputed_indexed_prices`, so a
        green integrity check said nothing at all about this path.

    The original docstring's reason was sound but over-applied: the rolling SERIES is
    sparse and must never be indexed positionally, which argues against walking
    `rolling_12m_median_series`, not against reading the promoted SCALARS that
    `precompute_union_prices.py` writes precisely so consumers don't have to.

    Provenance is gated. If `median_source` is not the union, or the scalars are
    missing, this returns None and the caller omits the suburb-median passage
    entirely. Omission is the correct failure mode here -- falling back to a weaker
    median is how the $2,115,000 / +23.6% Burleigh Waters retraction happened.
    """
    doc = client["Gold_Coast"]["precomputed_indexed_prices"].find_one({"_id": suburb_key})
    if not doc:
        return None
    if doc.get("median_source") != UNION_SOURCE:
        # Something overwrote the union promotion. Do not publish a median off it.
        return None

    m_now = doc.get("rolling_12m_median_price")
    n_now = doc.get("rolling_12m_median_sample_n")
    yoy = doc.get("rolling_12m_yoy_pct")
    if not m_now or not n_now or yoy is None:
        return None

    return {
        "median_now": m_now,
        "n_now": n_now,
        "yoy_pct": yoy,
        "ci_low": doc.get("rolling_12m_ci_low"),
        "ci_high": doc.get("rolling_12m_ci_high"),
        "ci_margin_pct": doc.get("rolling_12m_ci_margin_pct"),
        "median_source": doc["median_source"],
        "median_computed_at": doc.get("median_computed_at"),
        # For the chart only. ⚠ SPARSE -- Robina skips Q2 2021 -> Q4 2021 -> Q2 2023,
        # and is missing Q3 2024 even inside the recent window. The chart MUST place
        # points by true quarter ordinal and break the line across gaps; walking this
        # by index would space non-consecutive quarters evenly and invent continuity.
        "series": doc.get("rolling_12m_median_series") or [],
    }


def suburb_dom(client, suburb_key: str) -> dict | None:
    """Median days on market -- READ from `precomputed_market_charts`, the same
    collection the Market Intelligence page renders, so the two surfaces cannot
    disagree.

    Why DOM is publishable off a partial sample when sales VOLUME is not: our own
    cross-check against PropRadar (memory `data_source_undercapture_reset`) found
    days-on-market and price growth matched closely -- Varsity 23-26 vs 23,
    Burleigh 33 vs 33 -- while scraped sold VOLUME under-counts by ~2x. A median
    is robust to sampling; a count is precisely what sampling destroys. So the
    median is the published figure and `transaction_count` appears only as the
    sample size beneath each point, never as a market fact of its own.
    """
    gc = client["Gold_Coast"]
    d = (gc["precomputed_market_charts"].find_one({"_id": f"{suburb_key}_days_on_market"})
         or gc["precomputed_market_charts"].find_one(
             {"suburb": suburb_key, "chart_type": "days_on_market"}))
    if not d or d.get("latest_quarter_median") is None:
        return None
    return {"latest": d["latest_quarter_median"],
            "yoy_days": d.get("yoy_change_days"),
            "timeline": d.get("timeline") or []}


def check_surface_consistency(client, suburb_key: str, dom: dict | None) -> list[str]:
    """The article's figures must equal what the public pages already show.

    CLAUDE.md Rule 6 exists because a Market Pulse rewrite once left a third
    content layer stale and produced one page showing three different absorption
    rates. The same failure ACROSS surfaces is worse: the owner is holding a
    printed sheet and looking at the website, and cannot see which is stale. The
    check is two queries, so there is no reason not to run it every build.
    """
    problems = []
    if not dom:
        return problems
    seen = {(p.get("data_snapshot") or {}).get("dom_median")
            for p in client["system_monitor"]["market_pulse"].find(
                {"suburb": suburb_key}, {"data_snapshot.dom_median": 1})}
    seen.discard(None)
    for v in seen:
        if abs(float(v) - float(dom["latest"])) > 0.51:
            problems.append(
                f"days-on-market disagreement for {suburb_key}: market_pulse (the "
                f"Market Intelligence pages) shows {v}, precomputed_market_charts "
                f"shows {dom['latest']}")
    return problems


def comp_movement(comps: list[dict]) -> dict | None:
    """Split the comps in half by SALE DATE and compare mean adjusted price.

    This is the payoff of the format: local evidence, adjusted to one home,
    reproducing the suburb trend. Report DIRECTION -- a decimal-place match on
    half-sets this small is luck, and MAE is wider than the movement described.
    """
    dated = [(parse_date(c.get("sale_date")), c) for c in comps]
    dated = [(d, c) for d, c in dated if d]
    if len(dated) < 4:
        return None
    dated.sort(key=lambda t: t[0])
    half = len(dated) // 2
    early, late = dated[:half], dated[half:]
    e_mean = sum(c["adjusted_price"] for _, c in early) / len(early)
    l_mean = sum(c["adjusted_price"] for _, c in late) / len(late)
    return {
        "early_mean": e_mean, "late_mean": l_mean,
        "n_early": len(early), "n_late": len(late),
        "early_from": early[0][0], "early_to": early[-1][0],
        "late_from": late[0][0], "late_to": late[-1][0],
        "pct": (l_mean - e_mean) / e_mean * 100.0,
    }


def worked_example(comps: list[dict], subject_feat: dict) -> dict | None:
    """The comp whose adjustments best SHOW the mechanism: largest total move."""
    best = max(comps, key=lambda c: abs(c.get("total_adjustment") or 0), default=None)
    if not best:
        return None
    labels = {
        "land_size": ("land", "sqm"), "floor_area": ("internal floor area", "sqm"),
        "bathrooms": ("bathrooms", ""), "bedrooms": ("bedrooms", ""),
        "pool": ("pool", ""), "car_spaces": ("car spaces", ""),
        "renovation": ("renovation level", ""), "condition": ("condition", ""),
        "kitchen": ("kitchen", ""), "stories": ("levels", ""),
    }
    moves = []
    for key, a in (best.get("adjustments") or {}).items():
        d = a.get("dollars")
        if not d:
            continue
        label, unit = labels.get(key, (key.replace("_", " "), ""))
        moves.append({
            "key": key, "label": label, "unit": unit, "dollars": d,
            "subject": a.get("subject_value"), "comp": a.get("comp_value"),
        })
    moves.sort(key=lambda m: abs(m["dollars"]), reverse=True)
    return {"comp": best, "moves": moves[:3], "n_other": max(0, len(moves) - 3)}


def load_macro() -> tuple[dict | None, str | None]:
    path = os.path.join(HERE, "macro_context.json")
    with open(path) as fh:
        data = json.load(fh)
    as_at = datetime.strptime(data["as_at"], "%Y-%m-%d")
    age = (datetime.utcnow() - as_at).days
    if age > data.get("max_age_days", 45):
        return None, (f"macro_context.json is {age} days old (max "
                      f"{data['max_age_days']}) -- refresh it before printing")
    return data, None


# ---------------------------------------------------------------- composition

def compose(bundle: dict, variant: str = "report") -> tuple[str, FactBook, dict]:
    fb = FactBook()
    charts: dict[str, str] = {}
    if variant != "report":
        S = variants_mod.Sections(bundle, fb, charts, {
            "fmt_date": fmt_date, "parse_date": parse_date, "upper1": _upper1,
            "charts_mod": charts_mod, "MAE_PCT": MAE_PCT,
        })
        builder, _desc = variants_mod.VARIANTS[variant]
        return "\n".join(builder(S, MIN_COMPS, RADIUS_KM)), fb, charts
    b = bundle
    comps, subj = b["comps"], b["subject"]
    short = fb.address("subject_addr", b["address_short"])

    n_comps = fb.word_count("n_comps", len(comps))
    radius = fb.num("radius_km", b["radius_km"], dp=1)
    nearest = min(comps, key=lambda c: c["distance_km"])
    furthest = max(comps, key=lambda c: c["distance_km"])
    d_near = fb.num("d_nearest", nearest["distance_km"], dp=2)
    d_far = fb.num("d_furthest", furthest["distance_km"], dp=2)

    dates = sorted(d for d in (parse_date(c.get("sale_date")) for c in comps) if d)
    first_sale = fb.date("first_sale", fmt_date(dates[0]))
    last_sale = fb.date("last_sale", fmt_date(dates[-1]))

    adj = [c["adjusted_price"] for c in comps]
    raw = [c["sale_price"] for c in comps]
    adj_low, adj_high = fb.money("adj_low", min(adj)), fb.money("adj_high", max(adj))
    raw_low, raw_high = fb.money("raw_low", min(raw)), fb.money("raw_high", max(raw))
    spread = fb.money("adj_spread", max(adj) - min(adj))

    P = []
    P.append(f"# {n_comps.capitalize()} sales near your street, weighed against the headlines\n")
    P.append(
        f"You have read that house prices are falling. The {n_comps} most recent sales "
        f"within {radius} km of {short}, once each is adjusted to your home, and "
        f"{b['suburb_display']}'s own recorded median point a different way from the "
        f"national numbers. This piece sets the two side by side; it does not decide "
        f"between them for you.\n")

    # ---- macro
    if b["macro"]:
        bits = [fb.allow_literal(f"{s['text']} ({s['source']}, {s['period']})")
                for s in b["macro"]["stats"]]
        P.append("## What the headlines say\n")
        P.append("The falls are real where they are being measured. "
                 + " ".join(x + "." for x in bits)
                 + " That is a fair picture of a national market under pressure.\n")

    # ---- what sold
    P.append("## What sold near you\n")
    P.append(
        f"{n_comps.capitalize()} houses have sold close to yours between {first_sale} and "
        f"{last_sale}. The nearest is "
        f"{fb.address('nearest_addr', nearest['address'].split(',')[0])}, {d_near} km away; "
        f"the furthest in this set is {d_far} km. They are the evidence here, because a "
        f"sale down the road is a real transaction, not an estimate.\n")

    we = b["worked"]
    if we:
        c = we["comp"]
        c_addr = fb.address("we_addr", c["address"].split(",")[0])
        c_price = fb.money("we_price", c["sale_price"])
        c_adj = fb.money("we_adj", c["adjusted_price"])
        c_date = fb.date("we_date", fmt_date(c.get("sale_date")))
        clauses = []
        for i, m in enumerate(we["moves"]):
            verb = "we add" if m["dollars"] > 0 else "we subtract"
            amt = fb.money(f"we_move_{i}", abs(m["dollars"]))
            if m["unit"] == "sqm" and m["subject"] is not None and m["comp"] is not None:
                sv = fb.num(f"we_subj_{i}", m["subject"])
                cv = fb.num(f"we_comp_{i}", m["comp"])
                clauses.append(f"it has {cv} sqm of {m['label']} against your {sv}, "
                               f"so {verb} {amt}")
            else:
                clauses.append(f"on {m['label']}, {verb} {amt}")
        tail = (f", with {fb.word_count('we_other', we['n_other'])} smaller differences"
                if we["n_other"] else "")
        P.append(
            f"A raw sale price is not directly comparable to your home, though, because no "
            f"two houses are the same. Take {c_addr}, which sold on {c_date} for "
            f"**{c_price}** -- a real sale price. " + _upper1("; ".join(clauses))
            + f"{tail}. Those differences restate that sale as **{c_adj}** -- an estimate of "
            f"what that same buyer would likely have paid for a home like yours. Every sale "
            f"below has been through the same process.\n")

    P.append("| Address | Distance | Sold | Sale price | Adjusted for your home |")
    P.append("|---|---|---|---|---|")
    for i, c in enumerate(comps):
        P.append(
            f"| {fb.address(f'ca{i}', c['address'].split(',')[0])} "
            f"| {fb.num(f'd{i}', c['distance_km'], dp=2)} km "
            f"| {fb.date(f'sd{i}', fmt_date(c.get('sale_date')))} "
            f"| {fb.money(f'sp{i}', c['sale_price'])} "
            f"| {fb.money(f'ap{i}', c['adjusted_price'])} |")
    P.append("")

    # ---- the range
    P.append("## What these sales say about your home\n")
    P.append(
        f"Raw, those {n_comps} homes sold between {raw_low} and {raw_high}. Adjusted to your "
        f"home, they land between **{adj_low} and {adj_high}** -- a range built from "
        f"{n_comps} sales. That spread of {spread} is the estimate. It is not one number, "
        f"and it should not be read as one; the width is the honest part, reflecting how "
        f"the {n_comps} homes genuinely differed from yours.\n")

    # ---- how long homes are taking to sell
    # Placed before the median section deliberately. The owner's first question is
    # "will it sell at all", not "what is the number" -- and the homeowner brief
    # §8.3 says to lead with time-on-market over medians, because it is more
    # reliable in our data and cannot accidentally become advice.
    dom = b["dom"]
    if dom and dom.get("timeline"):
        svg, cap = charts_mod.dom_chart(dom["timeline"], b["suburb_display"], fb)
        if svg:
            charts["dom"] = svg
            latest = fb.num("dom_latest", dom["latest"])
            P.append(f"## How long homes are taking to sell in {b['suburb_display']}\n")
            P.append(
                f"Half the houses that sold in {b['suburb_display']} last quarter were "
                f"under offer within {latest} days of listing, and half took longer. "
                f"The chart below shows that figure each quarter, with the number of "
                f"sales it is measured from underneath.\n")
            P.append("{{CHART:dom}}")
            P.append(f"*{cap}*\n")

    # ---- agreement with the suburb
    mv, sm = b["movement"], b["suburb"]
    if mv and sm:
        P.append(f"## Do these sales agree with {b['suburb_display']}'s own figures?\n")
        e_mean = fb.money("early_mean", mv["early_mean"])
        l_mean = fb.money("late_mean", mv["late_mean"])
        n_e = fb.word_count("n_early", mv["n_early"])
        n_l = fb.word_count("n_late", mv["n_late"])
        move = fb.pct("comp_move", mv["pct"])
        yoy = fb.pct("suburb_yoy", sm["yoy_pct"])
        window = fb.num("median_window_months", 12)
        n_sales = fb.num("n_suburb_sales", sm["n_now"])
        P.append(
            f"Split the {n_comps} adjusted sales in half by date. The earlier {n_e}, from "
            f"{fb.date('e_from', fmt_date(mv['early_from']))} to "
            f"{fb.date('e_to', fmt_date(mv['early_to']))}, average **{e_mean}**. The later "
            f"{n_l}, from {fb.date('l_from', fmt_date(mv['late_from']))} to "
            f"{fb.date('l_to', fmt_date(mv['late_to']))}, average **{l_mean}**. That is a "
            f"move of **{move}**.\n")
        # How the two measures relate is a per-home FACT, so the sentence that
        # characterises it has to be derived, not hardcoded. The prototype was
        # written on a home where both read +5.8% and asserted agreement in fixed
        # copy; on most homes they differ, and inherited copy would overclaim.
        same_dir = (mv["pct"] > 0) == (sm["yoy_pct"] > 0)
        gap_pp = abs(mv["pct"] - sm["yoy_pct"])
        close = same_dir and gap_pp <= 2.5

        # NOT "independently measured" -- that read to an owner as corroborated, when the
        # figure was in fact our weaker Domain-only recomputation. It now comes from the
        # union pipeline, so the honest description is the one that names the sources.
        lead = (f"The {b['suburb_display']} rolling {window}-month house median moved "
                f"**{yoy}** year-on-year, across {n_sales} sales matched between Domain "
                f"and onthehouse. ")
        if close:
            verdict = ("Both point the same way, and by a similar amount.")
        elif same_dir:
            bigger = "these sales" if abs(mv["pct"]) > abs(sm["yoy_pct"]) else "the suburb median"
            verdict = (f"Both point the same way, though not by the same amount -- "
                       f"{bigger} moved further.")
        else:
            verdict = (f"These two records point in opposite directions, which is a fact "
                       f"about how little {n_comps} sales can settle rather than a "
                       f"contradiction to resolve.")
        P.append(lead + verdict + "\n")

        if sm.get("series"):
            svg, cap = charts_mod.median_price_chart(
                sm["series"], b["suburb_display"], fb)
            if svg:
                charts["median"] = svg
                P.append("{{CHART:median}}")
                P.append(f"*{cap}*\n")

        mae = fb.pct("mae", MAE_PCT, signed=False)
        halves = (n_e if mv["n_early"] == mv["n_late"] else f"{n_e} and {n_l}")
        closing = ("The direction is the reportable part; the precision either figure "
                   f"appears to show is more than {n_e} sales a side can carry."
                   if close else
                   "Neither figure is precise enough to explain the difference between "
                   "them, so the honest reading is the direction they share, not the gap.")
        P.append(
            f"Now the limits, in the same breath. Each half holds {halves} sales, which is "
            f"a very small sample. This method's own mean absolute error is about {mae} in "
            f"this price range -- wider than the movement it is describing. " + closing + "\n")

    # ---- national vs local
    if b["macro"] and sm:
        an = b["macro"].get("auction_note")
        P.append("## Where that leaves the national picture\n")
        line = (f"So the two records point differently. The national aggregate is falling, "
                f"while {b['suburb_display']}'s rolling median sits "
                f"{fb.pct('suburb_yoy2', sm['yoy_pct'])} against a year earlier. ")
        if an:
            line += (fb.allow_literal(
                f"Weekly auction clearances add a further gap of kind rather than degree: "
                f"{an['text']} ({an['source']}, {an['period']}) -- but {an['caveat']}, not "
                f"this one. ") )
        line += ("The national and the local are describing different things at different "
                 "scales.\n")
        P.append(line)

    # ---- limits
    P.append("## What this can't tell you\n")
    mae2 = fb.pct("mae2", MAE_PCT, signed=False)
    limits = (
        f"We publish this method's mean absolute error: about {mae2} in this price range. "
        f"{n_comps.capitalize()} sales sit behind the range above -- a small number, stated "
        f"plainly so you can weigh it. ")
    if sm:
        limits += (f"The {b['suburb_display']} median rests on {fb.num('n_suburb_sales2', sm['n_now'])} "
                   f"recorded sales, which is a sample of the suburb's activity rather than "
                   f"all of it. ")
        # The union pipeline carries a 90% CI. Now that we read it instead of recomputing
        # a bare median, disclose it -- it is the honest width of that figure.
        if sm.get("ci_low") and sm.get("ci_high"):
            limits += (f"Its {fb.pct('sub_ci_level', 90, signed=False, dp=0)} "
                       f"confidence range runs "
                       f"{fb.money('sub_ci_low', sm['ci_low'])} to "
                       f"{fb.money('sub_ci_high', sm['ci_high'])}. ")
    limits += (f"Sales within {radius} km of one home, over "
               f"{fb.num('span_months', b['span_months'])} months, cannot show you a whole "
               f"market or what any single buyer would do.\n")
    P.append(limits)

    if b["radius_widened"]:
        P.append(
            f"*Fewer than {fb.word_count('min_comps', MIN_COMPS)} comparable sales fell "
            f"inside the standard {fb.num('std_radius', RADIUS_KM, dp=1)} km, so the search "
            f"was widened to {radius} km for this home.*\n")

    return "\n".join(P), fb, charts


# ---------------------------------------------------------------- rendering

CSS = """
:root{--ink:#15171a;--muted:#5b6470;--rule:#e2e5ea;--bg:#fff;--accent:#0b6b4f;
 --tint:#f6f8f7;--band:#fafbfc}
*{box-sizing:border-box}
body{margin:0;background:var(--bg);color:var(--ink);
 font:18px/1.65 Georgia,'Iowan Old Style',serif;-webkit-text-size-adjust:100%}
.wrap{max-width:44rem;margin:0 auto;padding:2rem 1.25rem 5rem}
.flag{font:600 12px/1 -apple-system,Segoe UI,Roboto,sans-serif;letter-spacing:.14em;
 text-transform:uppercase;color:var(--accent);margin-bottom:1.5rem}
.hero{margin:0 0 2rem;border-radius:10px;overflow:hidden;border:1px solid var(--rule);
 background:var(--tint)}
.hero img{display:block;width:100%;height:auto}
.hero figcaption{font:400 13px/1.5 -apple-system,Segoe UI,Roboto,sans-serif;
 color:var(--muted);padding:.7rem .9rem;border-top:1px solid var(--rule)}
h1{font-size:2.05rem;line-height:1.2;letter-spacing:-.015em;margin:0 0 1.5rem}
h2{font:600 1.28rem/1.3 -apple-system,Segoe UI,Roboto,sans-serif;margin:2.75rem 0 .85rem;
 padding-top:1.5rem;border-top:1px solid var(--rule)}
p{margin:0 0 1.15rem}
body>.wrap>p:first-of-type{font-size:1.16rem;color:var(--muted)}
strong{font-weight:700}
em{color:var(--muted);font-size:.95rem}
.tw{overflow-x:auto;margin:1.75rem 0;-webkit-overflow-scrolling:touch}
table{border-collapse:collapse;width:100%;min-width:40rem;
 font:15px/1.45 -apple-system,Segoe UI,Roboto,sans-serif}
th{text-align:left;font-weight:600;font-size:12px;letter-spacing:.06em;text-transform:uppercase;
 color:var(--muted);border-bottom:2px solid var(--ink);padding:.6rem .7rem}
td{padding:.68rem .7rem;border-bottom:1px solid var(--rule);vertical-align:top}
tbody tr:nth-child(even){background:var(--band)}
td:nth-child(2),td:nth-child(4),td:nth-child(5){white-space:nowrap;
 font-variant-numeric:tabular-nums}
td:nth-child(5){font-weight:600;color:var(--accent)}
.foot{margin-top:3rem;padding-top:1.25rem;border-top:1px solid var(--rule);
 font:400 13px/1.6 -apple-system,Segoe UI,Roboto,sans-serif;color:var(--muted)}
@media (prefers-color-scheme:dark){
 :root{--ink:#e9ecf0;--muted:#9aa4b2;--rule:#2a2f36;--bg:#0f1114;--accent:#4fd1a5;
  --tint:#151a18;--band:#151920}}
:root[data-theme=dark]{--ink:#e9ecf0;--muted:#9aa4b2;--rule:#2a2f36;--bg:#0f1114;
 --accent:#4fd1a5;--tint:#151a18;--band:#151920}
:root[data-theme=light]{--ink:#15171a;--muted:#5b6470;--rule:#e2e5ea;--bg:#fff;
 --accent:#0b6b4f;--tint:#f6f8f7;--band:#fafbfc}
@media print{body{font-size:11pt}.wrap{max-width:none;padding:0}
 h2{page-break-after:avoid}table{page-break-inside:avoid}}
"""


def md_to_html(md: str, title: str, hero: dict | None,
               charts: dict | None = None) -> str:
    """Minimal, deliberate markdown -> HTML. Only the constructs we emit."""
    def inline(s):
        s = (s.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")
              .replace("--", "&mdash;"))
        s = re.sub(r"\*\*(.+?)\*\*", r"<strong>\1</strong>", s)
        s = re.sub(r"(?<!\*)\*(?!\*)(.+?)(?<!\*)\*(?!\*)", r"<em>\1</em>", s)
        return s

    out, rows, i = [], [], 0
    lines = md.splitlines()
    while i < len(lines):
        ln = lines[i]
        if ln.startswith("| "):
            rows = []
            while i < len(lines) and lines[i].startswith("|"):
                cells = [c.strip() for c in lines[i].strip("|").split("|")]
                if not all(set(c) <= set("-: ") for c in cells):
                    rows.append(cells)
                i += 1
            if rows:
                head, body = rows[0], rows[1:]
                out.append('<div class="tw"><table><thead><tr>'
                           + "".join(f"<th>{inline(c)}</th>" for c in head)
                           + "</tr></thead><tbody>")
                for r in body:
                    out.append("<tr>" + "".join(f"<td>{inline(c)}</td>" for c in r) + "</tr>")
                out.append("</tbody></table></div>")
            continue
        m_chart = re.fullmatch(r"\{\{CHART:(\w+)\}\}", ln.strip())
        if m_chart:
            svg = (charts or {}).get(m_chart.group(1))
            if svg:
                out.append(svg)
            i += 1
            continue
        if ln.startswith("## "):
            out.append(f"<h2>{inline(ln[3:])}</h2>")
        elif ln.startswith("# "):
            out.append(f"<h1>{inline(ln[2:])}</h1>")
            if hero:
                out.append(
                    f'<figure class="hero"><img src="{hero["file"]}" alt="{hero["alt"]}">'
                    f'<figcaption>{hero["caption"]}</figcaption></figure>')
        elif ln.strip():
            out.append(f"<p>{inline(ln)}</p>")
        i += 1

    return (
        '<!doctype html><html lang="en"><head><meta charset="utf-8">\n'
        '<meta name="viewport" content="width=device-width,initial-scale=1">\n'
        '<meta name="robots" content="noindex">\n'
        f"<title>{title}</title>\n<style>{CSS}{charts_mod.CSS}</style>"
        '</head><body><div class="wrap">\n'
        '<div class="flag">Fields &middot; prepared for this address</div>\n'
        + "\n".join(out)
        + '\n<div class="foot">Prepared by Fields Real Estate from recorded sales and '
          'our own adjusted-comparables method. Figures are estimates with a stated '
          'error rate, not an appraisal.</div>\n'
          "</div></body></html>\n")


def build_hero(client, doc, suburb_key, slug, out_dir) -> dict | None:
    """Satellite aerial with the true cadastral boundary drawn on it.

    NOT a listing photo: `domain_hero_image_url` is expired by Domain once a home
    comes off the market, and curl cannot tell you that (memory
    image_url_verification_orb -- curl is not a browser). A broken image on a
    piece of unsolicited mail is worse than no image. The boundary matters
    because, as Will put it, a reader looking at a block of roofs cannot tell
    which one is theirs.
    """
    try:
        import render_property_aerial as ra
    except Exception:
        return None
    try:
        gc = client["Gold_Coast"]
        out, _note = ra.render(gc, suburb_key, doc, "sun", out_dir,
                               width=640, height=420, scale=2)
        if not out:
            return None
        return {
            "file": os.path.basename(str(out)),
            "alt": f"Aerial view of {doc.get('address','this property')} with its boundary marked",
            "caption": "Your block, outlined on the current aerial. "
                       "Boundary from the Queensland public cadastre.",
        }
    except Exception:
        return None


def build_cards(bundle: dict) -> list[dict]:
    """Deterministic 'market update' card ladder for the website.

    Emits the same minted facts the article uses, as RAW numbers, so the site
    can render its own stat cards + sparklines. No AI, no extra data fetch — it
    reads only what `build()` already assembled in `bundle`. Each optional
    section (suburb median, days-on-market, macro) is independently guarded, so
    a property missing one still gets a coherent (shorter) ladder. This is what
    makes it scale to the whole off-market book: suburb facts are shared, the
    per-property work is the comps min/max already computed for the article.
    """
    b = bundle
    comps = b.get("comps") or []
    sm, dom, macro = b.get("suburb"), b.get("dom"), b.get("macro")
    suburb = b.get("suburb_display") or b.get("suburb_key") or "the suburb"
    street = b.get("address_short") or "your home"
    cards: list[dict] = []

    # 1 — hook
    cards.append({
        "type": "hook",
        "headline": "The headlines say one thing. Your street says another.",
        "sub": f"The {len(comps)} most recent sales near {street}, each adjusted to this "
               f"home, set against the national numbers.",
    })

    # 2 — national headline stat (Cotality quarter move)
    if macro and macro.get("stats"):
        s = macro["stats"][0]
        nums = s.get("numbers") or []
        q = nums[1] if len(nums) > 1 else (nums[0] if nums else None)
        if q is not None:
            cards.append({
                "type": "national-stat",
                "headline": "Nationally, values are falling",
                "stat": q, "fmt": "pct",
                "source": ", ".join(x for x in (s.get("source"), s.get("period")) if x),
            })

    # 3 — local median (+ series)
    if sm and sm.get("median_now") is not None:
        yoy = sm.get("yoy_pct")
        cards.append({
            "type": "local-median",
            "headline": (f"{suburb}'s median is {'up' if (yoy or 0) >= 0 else 'down'} "
                         f"{abs(yoy):.1f}% this year") if yoy is not None else f"{suburb}'s median",
            "stat": sm["median_now"], "fmt": "money",
            "yoy_pct": yoy,
            # Last ~16 quarters — a recent-trend sparkline, not the whole 1991→ history.
            "series": [{"period": p.get("period"), "value": p.get("rolling_median")}
                       for p in (sm.get("series") or [])
                       if p.get("rolling_median") and not p.get("is_in_progress")][-16:],
            "source": "Fields, from Domain and onthehouse.com.au records",
        })

    # 4 — days on market (+ series)
    if dom and dom.get("latest") is not None:
        cards.append({
            "type": "days-on-market",
            "headline": f"Homes here take {dom['latest']} days to sell",
            "stat": dom["latest"], "fmt": "days",
            "yoy_days": dom.get("yoy_days"),
            "series": [{"period": p.get("period"), "value": p.get("median_days_on_market")}
                       for p in (dom.get("timeline") or [])
                       if p.get("median_days_on_market") and (p.get("transaction_count") or 0) > 0],
            "source": "Fields Market Intelligence",
        })

    # 5 — nearby sales range (the valuation is always a range, never a point)
    adj = [c["adjusted_price"] for c in comps if c.get("adjusted_price") is not None]
    if adj:
        nearest = min(comps, key=lambda c: c.get("distance_km", 9e9))
        furthest = max(comps, key=lambda c: c.get("distance_km", -1.0))
        cards.append({
            "type": "nearby-range",
            "headline": "What those sales say about your home",
            "stat": [min(adj), max(adj)], "fmt": "range",
            "source": f"{len(comps)} sales, {nearest.get('distance_km', 0):.2f}"
                      f"–{furthest.get('distance_km', 0):.2f} km away",
        })

    # 6 — the contradiction (local vs national)
    if sm and sm.get("yoy_pct") is not None and macro:
        yoy = sm["yoy_pct"]
        cards.append({
            "type": "contradiction",
            "headline": "National down. " + suburb +
                        (" up." if yoy >= 0 else " softer — but not by the headline number."),
            "stat": yoy, "fmt": "pct",
            "sub": "The national aggregate and this suburb's own record point in different directions.",
            "source": "national aggregate vs suburb rolling median",
        })

    return cards


# ---------------------------------------------------------------- driver

def build(address, suburb=None, out_dir=None, want_html=True,
          skip_market_check=False, no_hero=False, verbose=True,
          variant="report"):
    client = get_db()
    doc, suburb_key = resolve_subject(client, address, suburb)
    if not doc:
        return {"ok": False, "stage": "resolve", "errors": [f"no subject found for {address!r}"]}

    full_addr = doc.get("address") or doc.get("complete_address")
    reasons = guard_subject(client, doc, suburb_key, skip_market_check)
    if reasons:
        return {"ok": False, "stage": "guard", "address": full_addr, "errors": reasons}

    vd = doc["valuation_data"]
    comps, radius, widened = select_comps(vd)
    if len(comps) < MIN_COMPS:
        return {"ok": False, "stage": "comps", "address": full_addr,
                "errors": [f"only {len(comps)} comparables within {RADIUS_MAX_KM} km"]}

    dates = sorted(d for d in (parse_date(c.get("sale_date")) for c in comps) if d)
    span_months = max(1, round((dates[-1] - dates[0]).days / 30.44))
    macro, macro_err = load_macro()
    subj_feat = ((vd.get("subject_property") or {}).get("features") or {}).get("basic") or {}

    # Days-on-market, plus the assertion that it equals what the public pages show.
    # A disagreement here is a BUILD FAILURE, not a warning: the owner may be
    # holding this sheet while looking at our website, and cannot tell which is
    # stale. Better to ship nothing than two Fields numbers for one suburb.
    dom = suburb_dom(client, suburb_key)
    inconsistent = check_surface_consistency(client, suburb_key, dom)
    if inconsistent:
        return {"ok": False, "stage": "consistency", "address": full_addr,
                "errors": inconsistent}

    bundle = {
        "subject": doc, "address_full": full_addr,
        "address_short": full_addr.split(",")[0].strip(),
        "suburb_key": suburb_key,
        "suburb_display": suburb_key.replace("_", " ").title(),
        "comps": comps, "radius_km": radius, "radius_widened": widened,
        "span_months": span_months,
        "worked": worked_example(comps, subj_feat),
        "movement": comp_movement(comps),
        "suburb": suburb_median_series(client, suburb_key),
        "dom": dom,
        "macro": macro,
    }

    md, fb, charts = compose(bundle, variant)

    unminted = fb.verify(md)
    findings = guardrails.lint(md)
    hard = guardrails.blocks(findings)
    if unminted or hard:
        return {"ok": False, "stage": "checks", "address": full_addr,
                "errors": ([f"unminted figure in copy: {u}" for u in unminted]
                           + [f"{f['label']} line {f['line']}: {f['match']!r} -- {f['why']}"
                              for f in hard]),
                "warnings": [f for f in findings if f["severity"] == "WARN"],
                "markdown": md}

    slug = slugify(full_addr)
    if variant != "report":
        slug = f"{slug}--{variant}"
    out_dir = out_dir or os.path.join(HERE, "output")
    os.makedirs(out_dir, exist_ok=True)
    md_path = os.path.join(out_dir, f"{slug}.md")
    with open(md_path, "w") as fh:
        # The markdown is the archival/plain-text form; charts are an HTML/print
        # concern, so the placeholder becomes a readable marker rather than a
        # dangling token.
        fh.write(re.sub(r"\{\{CHART:(\w+)\}\}",
                        lambda m: f"*[chart: {m.group(1)}]*", md))

    html_path = None
    if want_html:
        hero = None if no_hero else build_hero(client, doc, suburb_key, slug, out_dir)
        title = f"{bundle['address_short']} — sales near your street"
        html_path = os.path.join(out_dir, f"{slug}.html")
        with open(html_path, "w") as fh:
            fh.write(md_to_html(md, title, hero, charts))

    # Deterministic card ladder for the website "Market update" rail — same
    # minted facts as the article, emitted as raw numbers (no AI). Written
    # unconditionally so it exists even under --no-html.
    cards_path = os.path.join(out_dir, f"{slug}.cards.json")
    with open(cards_path, "w") as fh:
        json.dump({"address": bundle["address_full"],
                   "suburb": bundle.get("suburb_display"),
                   "cards": build_cards(bundle)}, fh, indent=2)

    return {"ok": True, "address": full_addr, "slug": slug, "md": md_path,
            "html": html_path, "n_comps": len(comps), "radius_km": radius,
            "radius_widened": widened, "macro_stale": macro_err,
            "warnings": [f for f in findings if f["severity"] == "WARN"],
            "markdown": md}


def list_candidates(suburb=None, limit=25):
    """Addresses that would pass the structural gates (cheap checks only)."""
    client = get_db()
    gc = client["Gold_Coast"]
    found = []
    for key in ([suburb] if suburb else SUBURBS):
        for d in gc[key].find(
                {"valuation_data.adjusted_comparables": {"$exists": True},
                 "listing_status": {"$nin": ["for_sale", "under_contract"]}},
                {"address": 1, "valuation_data.adjusted_comparables": 1,
                 "valuation_data.metadata": 1}):
            vd = d.get("valuation_data") or {}
            if (vd.get("metadata") or {}).get("directional_only"):
                continue
            comps, radius, widened = select_comps(vd)
            if len(comps) < MIN_COMPS:
                continue
            adj = [c["adjusted_price"] for c in comps]
            mid = (min(adj) + max(adj)) / 2
            if not (ENVELOPE_MIN <= mid <= ENVELOPE_MAX):
                continue
            found.append({"address": d.get("address"), "suburb": key,
                          "n_comps": len(comps), "radius_km": radius,
                          "widened": widened, "midpoint": mid})
            if len(found) >= limit:
                return found
    return found


def main():
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--address")
    ap.add_argument("--suburb", choices=SUBURBS)
    ap.add_argument("--out-dir")
    ap.add_argument("--no-html", action="store_true")
    ap.add_argument("--no-hero", action="store_true")
    ap.add_argument("--skip-market-check", action="store_true",
                    help="skip the PropRadar listed/lease guard (dev only -- never for print)")
    ap.add_argument("--variant", default="report",
                    choices=["report"] + sorted(variants_mod.VARIANTS),
                    help="composition angle; see variants.py")
    ap.add_argument("--all-variants", action="store_true",
                    help="build every variant for this address")
    ap.add_argument("--list-candidates", action="store_true")
    ap.add_argument("--limit", type=int, default=25)
    a = ap.parse_args()

    if a.list_candidates:
        for c in list_candidates(a.suburb, a.limit):
            flag = f" (widened to {c['radius_km']}km)" if c["widened"] else ""
            print(f"{c['address']}  [{c['n_comps']} comps, midpoint ${c['midpoint']:,.0f}]{flag}")
        return 0

    if not a.address:
        ap.error("--address is required (or --list-candidates)")

    wanted = (["report"] + sorted(variants_mod.VARIANTS)) if a.all_variants else [a.variant]
    rc = 0
    for v in wanted:
        r = build(a.address, a.suburb, a.out_dir, not a.no_html,
                  a.skip_market_check, a.no_hero, variant=v)
        if not r["ok"]:
            print(f"REJECTED [{v}] at {r['stage']}: {r.get('address') or a.address}",
                  file=sys.stderr)
            for e in r["errors"]:
                print(f"  - {e}", file=sys.stderr)
            rc = 3 if r["stage"] in ("checks", "consistency") else 2
            continue
        print(f"OK  [{v}]  {r['address']}  -> {os.path.basename(r['html'] or r['md'])}")
        for w in r["warnings"]:
            print(f"    ? WARN {w['label']} line {w['line']}: {w['match']!r} -- {w['why']}")
    return rc

def _unused_legacy(a, r):

    if not r["ok"]:
        print(f"REJECTED at {r['stage']}: {r.get('address') or a.address}", file=sys.stderr)
        for e in r["errors"]:
            print(f"  - {e}", file=sys.stderr)
        return 3 if r["stage"] == "checks" else 2

    print(f"OK  {r['address']}")
    print(f"    {r['n_comps']} comparables within {r['radius_km']} km"
          + ("  (radius widened)" if r["radius_widened"] else ""))
    print(f"    md   {r['md']}")
    if r["html"]:
        print(f"    html {r['html']}")
    if r["macro_stale"]:
        print(f"    ! macro section omitted: {r['macro_stale']}")
    for w in r["warnings"]:
        print(f"    ? WARN {w['label']} line {w['line']}: {w['match']!r} -- {w['why']}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
