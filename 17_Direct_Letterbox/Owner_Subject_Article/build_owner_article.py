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
import subject_trajectory as traj_mod                          # noqa: E402

# ---------------------------------------------------------------- constants

SUBURBS = ["robina", "varsity_lakes", "burleigh_waters"]

# Published Fields articles the piece links out to for the "why" and "what next"
# questions -- we draw the reader to our own longer analysis rather than trying to
# forecast in this format. Titles are the real published titles; verified present
# 2026-08-24. The month-stamped market updates age; refresh these slugs when a new
# monthly update publishes.
SITE = "https://fieldsestate.com.au"
ARTICLE_LINKS = {
    "fundamentals": ("The fundamentals of the Gold Coast market",
                     f"{SITE}/articles/fundamentals-of-the-gold-coast-market"),
    "about_to_fall": ("Is the Gold Coast market about to fall?",
                      f"{SITE}/articles/is-the-gold-coast-market-about-to-fall"),
    "what_drives": ("What drives Gold Coast house prices",
                    f"{SITE}/articles/what-drives-gold-coast-house-prices"),
    "gc_update": ("Gold Coast market update — August 2026",
                  f"{SITE}/articles/gold-coast-market-update-august-2026"),
    "robina_update": ("Robina market update — August 2026",
                      f"{SITE}/articles/robina-market-update-august-2026"),
    "robina_intel": ("Robina market intelligence",
                     f"{SITE}/market-intelligence/Robina"),
}


def _link(key: str) -> str:
    title, url = ARTICLE_LINKS[key]
    return f"[{title}]({url})"


def _intel_link(suburb_display: str) -> str:
    """Market-intelligence link for the ARTICLE's suburb, not a hardcoded one. The
    site routes /market-intelligence/<Hyphenated-Suburb> (see suburbNormalize)."""
    slug = suburb_display.replace(" ", "-")
    return f"[{suburb_display} market intelligence]({SITE}/market-intelligence/{slug})"

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


def _month_label(month: str) -> str:
    """'2026-06' -> 'June 2026'."""
    try:
        return datetime.strptime(month, "%Y-%m").strftime("%B %Y")
    except (ValueError, TypeError):
        return str(month)


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


def check_dom_prose_consistency(md: str, dom: dict | None) -> list[str]:
    """The days-on-market prose must not claim a direction the chart's own year-ago
    delta contradicts. The passage is now DERIVED from that delta, so this cannot fire
    on the current code -- it is a belt-and-braces guard against a future edit
    reintroducing a hardcoded trend verb, which is exactly how the passage once shipped
    saying Burleigh Waters' time on market had 'stretched to N days, from around half
    that a year ago' while the chart showed it had SHORTENED (37 -> 29). See
    logs/fix-history/2026-08-24.md [OWNER-ARTICLE-DOM-HARDCODED-INVERTED].
    """
    problems: list[str] = []
    if not dom or not dom.get("timeline"):
        return problems
    tl = dom["timeline"]
    lp = (tl[-1].get("period") or "") if tl else ""
    year_ago = None
    if "-Q" in lp:
        y, qn = lp.split("-Q")
        for p in tl:
            if p.get("period") == f"{int(y) - 1}-Q{qn}" \
                    and p.get("median_days_on_market"):
                year_ago = p["median_days_on_market"]
                break
    if year_ago is None:
        return problems
    delta = dom["latest"] - year_ago
    # Scope to the one sentence that states the year-ago comparison, so we test the
    # DERIVED trend verb and not, say, the "Our reading" recap's "has not lengthened".
    sents = [s.lower() for s in re.split(r"(?<=[.!?])\s+", md)
             if "time on market" in s.lower() and "year earlier" in s.lower()]
    if not sents:                              # DOM year-ago claim not rendered
        return problems
    blob = " ".join(sents)
    said_longer = "lengthened" in blob or "stretched" in blob
    said_shorter = "shorter than" in blob or "shortened" in blob
    if delta <= -1 and said_longer:
        problems.append(
            f"DOM prose says time on market lengthened, but the chart's year-ago delta "
            f"is {delta:+.0f} days (it shortened, {lp}) — a hardcoded trend verb has "
            f"drifted from the data")
    if delta >= 1 and said_shorter:
        problems.append(
            f"DOM prose says time on market shortened, but the chart's year-ago delta "
            f"is {delta:+.0f} days (it lengthened, {lp}) — a hardcoded trend verb has "
            f"drifted from the data")
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


def _load_json(name: str) -> dict | None:
    """Best-effort load of a context file. Returns None if missing/unreadable so
    the consuming Q3 sub-passage simply omits itself, like every other optional
    section -- a missing fundamentals file must never break the article."""
    try:
        with open(os.path.join(HERE, name)) as fh:
            return json.load(fh)
    except (OSError, ValueError):
        return None


def load_fundamentals() -> dict | None:
    """Migration + affordability facts (human-curated, cited). Staleness-gated the
    same way as macro: an old fundamentals block omits itself rather than printing
    figures that may have moved."""
    data = _load_json("fundamentals_context.json")
    if not data:
        return None
    try:
        age = (datetime.utcnow() - datetime.strptime(data["as_at"], "%Y-%m-%d")).days
        if age > data.get("max_age_days", 120):
            return None
    except (KeyError, ValueError):
        pass
    return data


# ---------------------------------------------------------------- composition

def comparison_cards(cmp: dict, fb) -> str:
    """Two real homes side by side — Gold Coast left, Sydney right — Street View
    photo over a facts row, the land figure emphasised as the value gap. Returns a
    self-contained HTML block (photos are embedded data URIs)."""
    def card(side, home):
        price = fb.money(f"cmp_{side}_price", home["price"])
        land = fb.num(f"cmp_{side}_land", home["land"])
        beds = fb.num(f"cmp_{side}_beds", home["beds"])
        facts = f"{beds} bed"
        if home.get("baths"):                       # Sydney cards carry no bath count
            facts += f' &middot; {fb.num(f"cmp_{side}_baths", home["baths"])} bath'
        facts += f' &middot; <b class="cmp-land">{land} m&sup2;</b>'
        return (
            f'<div class="cmp-card">'
            f'<div class="cmp-tag">{_esc_html(home["label"])}</div>'
            f'<img class="cmp-img" src="{home["photo_data_uri"]}" '
            f'alt="A home in {_esc_html(home["suburb"])}" loading="lazy">'
            f'<div class="cmp-body">'
            f'<div class="cmp-suburb">{_esc_html(home["suburb"])}</div>'
            f'<div class="cmp-price">{price}</div>'
            f'<div class="cmp-facts">{facts}</div>'
            f'<div class="cmp-ctx">{_esc_html(home["context"])}</div>'
            f'</div></div>')
    gc, syd = cmp.get("gc"), cmp.get("syd")
    if not (gc and syd and gc.get("photo_data_uri") and syd.get("photo_data_uri")):
        return ""
    attr = _esc_html(cmp.get("attribution", "Street View, Google"))
    # only claim "near the same price" when the two are within ~10%
    near = min(gc["price"], syd["price"]) >= max(gc["price"], syd["price"]) * 0.90
    lead = "Two real homes, near the same price: a " if near else "Two real homes: a "
    return (
        '<figure class="cmp">'
        f'<div class="cmp-grid">{card("gc", gc)}{card("syd", syd)}</div>'
        f'<figcaption class="cmp-cap">{lead}'
        f'{fb.num("cmp_gc_land2", gc["land"])} m&sup2; block on the Gold Coast against '
        f'a {fb.num("cmp_syd_land2", syd["land"])} m&sup2; block in Sydney. Photos: '
        f'{attr}. Sold-price facts from {_esc_html(gc["source"])} and '
        f'{_esc_html(syd["source"])}.</figcaption></figure>')


def _esc_html(s) -> str:
    return (str(s).replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;"))


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

    # Subject demand-driver attributes, for Q4. Minted only where used.
    feat = ((((subj.get("valuation_data") or {}).get("subject_property") or {})
             .get("features") or {}).get("basic") or {})
    md_ = (b["macro"] or {}).get("derived") or {}
    mv, sm, dom, tj = b["movement"], b["suburb"], b["dom"], b["trajectory"]

    P = []
    # ---- figure numbering + citation registry (Will, 2026-08-25) -----------------
    _figw = ["One", "Two", "Three", "Four", "Five", "Six", "Seven", "Eight", "Nine",
             "Ten"]
    _figc = {"n": 0}

    def _fig(cap):
        """Prefix a chart caption with its running figure number: 'Figure One — ...'."""
        _figc["n"] += 1
        w = _figw[_figc["n"] - 1] if _figc["n"] <= len(_figw) else str(_figc["n"])
        return f"Figure {w} — {cap}"

    _sups = "⁰¹²³⁴⁵⁶⁷⁸⁹"
    _refwords = ["one", "two", "three", "four", "five", "six", "seven", "eight", "nine",
                 "ten"]
    _refs: list[str] = []

    def _refmark(n):
        return "".join(_sups[int(d)] for d in str(n))

    def _refword(n):
        return _refwords[n - 1] if n <= len(_refwords) else str(n)

    def _cite(entry):
        """Register a reference; return a superscript that HYPERLINKS to its entry in the
        References section. Deduped by text. Anchor ids use words (#ref-one) so no ASCII
        digit reaches the markdown -- FactBook.verify only sees the unicode superscript,
        which it ignores."""
        if entry not in _refs:
            _refs.append(entry)
        n = _refs.index(entry) + 1
        return f"[{_refmark(n)}](#ref-{_refword(n)})"

    for _sn in (1, 2, 3, 4):          # section numbers are furniture, not figures
        fb.num(f"sec_{_sn}", _sn)
    # ---- H1 + hero, then the NATIONAL PICTURE FIRST ----------------------------
    # Will's structure: paint the macro picture first (prices falling elsewhere),
    # from which it follows a local owner may fear the same -> the Key Question.
    P.append(f"# Prices are falling across the country. Will {short} fall too?\n")

    # ---- the national picture (heading computed from the macro history) --------
    if b["macro"]:
        # Templated, no-LLM headline built from the computed macro history. The full
        # form ("falling for N months … Brisbane, previously positive, just tipped
        # down in <month>") needs >=2 southern-falling months AND a Brisbane flip;
        # until the history supports both it degrades to the sourced-safe line.
        streak = md_.get("southern_falling_streak_months")
        just = md_.get("brisbane_just_turned")
        latest_name = md_.get("brisbane_latest_month_name")
        if streak and streak >= 2 and just and latest_name:
            head = (f"Southern markets have been falling for "
                    f"{fb.word_count('macro_streak', streak)} months and Brisbane, "
                    f"previously positive, just tipped down in "
                    f"{fb.date('macro_bris_month', latest_name)}")
        else:
            head = "The southern capitals are falling"
            bris = md_.get("brisbane_latest_pct")
            if isinstance(bris, (int, float)) and bris < 0:
                head += ", and Brisbane has slipped too"
        P.append(f"## {head}\n")
        # Will's three-paragraph opening (2026-08-25). Figures are still pulled from the
        # macro stats `numbers` arrays so a monthly macro update flows through and every
        # number stays minted; the wording drops the minus signs (fell/declined/edged
        # lower). Falls back to the prior sourced-safe join if the stats shape changes.
        _st = {s.get("id"): s for s in b["macro"]["stats"]}

        def _mn(sid, i):
            try:
                return _st[sid]["numbers"][i]
            except (KeyError, IndexError, TypeError):
                return None
        _cotp = (_st.get("cotality_monthly") or {}).get("period", "")
        _cotm = _cotp.split()[0] if _cotp else "the latest month"
        nat, syd, mel, bris, adl = (_mn("cotality_monthly", i) for i in range(5))
        cash = _mn("rba_cash_rate", 0)
        cpih, cpit = _mn("abs_cpi", 0), _mn("abs_cpi", 1)
        wpx = _mn("westpac_expectations", 0)
        if None not in (nat, syd, mel, bris, adl, cash, cpih, cpit, wpx):
            def _u(x):                       # unsigned one-dp percent (no minus)
                return f"{abs(x):.1f}%"
            P.append(fb.allow_literal(
                f"The downturn is no longer theoretical; it is showing up in the data. "
                f"National home values fell {_u(nat)} in {_cotm} — the sharpest monthly "
                f"decline since December 2022. Sydney and Melbourne led the falls, down "
                f"{_u(syd)} and {_u(mel)} respectively, while Brisbane declined {_u(bris)} "
                f"and Adelaide edged {_u(adl)} lower (Cotality, {_cotp})."))
            P.append(fb.allow_literal(
                f"The pressure is coming from stubborn inflation and higher interest "
                f"rates. The RBA cash rate remains at {cash:.2f}% following increases in "
                f"February, March and May, while annual headline inflation reached "
                f"{cpih:.1f}% and trimmed-mean inflation {cpit:.1f}% in the June quarter "
                f"(RBA; ABS)."))
            P.append(fb.allow_literal(
                f"Buyers are also becoming less confident. Westpac's House Price "
                f"Expectations Index fell {abs(wpx):.0f}% in {_cotm} to its lowest level "
                f"in three years — although almost half of respondents still expected "
                f"prices to rise. Taken together, the evidence points to a national "
                f"housing market under genuine pressure."))
        else:
            bits = [fb.allow_literal(f"{s['text']} ({s['source']}, {s['period']})")
                    for s in b["macro"]["stats"]]
            P.append("The falls are real where they are being measured. "
                     + " ".join(x + "." for x in bits)
                     + " That is a fair picture of a national market under pressure.\n")

        # SITUATION, completed: why did the national market fall? (cited research)
        wt = b["macro"].get("why_turned")
        if wt:
            _wtt = wt["text"]
            _q = "So why are they falling?"
            if _wtt.startswith(_q):                     # onto its own line, spaced
                P.append(fb.allow_literal(_q))
                _wtt = _wtt[len(_q):].strip()
            P.append(fb.allow_literal(_wtt) + " "
                     + fb.allow_literal(wt["amplifier_note"])
                     + f" ({fb.allow_literal(wt['source'])}; the fuller picture is in "
                     f"{_link('about_to_fall')}).\n")

        # COMPLICATION (Minto C): the Gold Coast has so far bucked the national move.
        P.append(
            f"Yet the Gold Coast has so far not followed. Prices in {b['suburb_display']} "
            f"have held — risen, even — while the national market fell, bucking the trend. "
            f"The question that raises is whether it lasts: does the Gold Coast keep "
            f"defying the national move, or eventually turn with it?\n")

    # ---- the QUESTION (Minto Q): the same question, in the owner's terms --------
    P.append(
        f"## The Key Question: Property markets are declining in major national cities; "
        f"will the value of {short} decline too?\n")
    P.append(
        f"That is the suburb's question in its most personal form — the one that matters to "
        f"you as the owner. Let us work through it the way an analyst would, in four steps "
        f"from your home outward: whether its own estimate is falling now, what "
        f"{b['suburb_display']} as a whole is doing, why the two can move differently, and "
        f"which forces could shape its value from here.\n")

    # ==== 1. Is the value of your home declining right now? =====================
    P.append("## 1. Is the value of your home declining right now?\n")
    if tj:
        svg, cap = charts_mod.trajectory_chart(tj, b["suburb_display"], fb,
                                               subject_label=b["address_short"])
        if svg:
            charts["trajectory"] = svg
            span = fb.num("traj_span", tj["span_months"])
            subj_move = fb.pct("traj_subj", tj["subject_full_pct"])
            subj_dir = "risen" if tj["subject_full_pct"] >= 0 else "eased"
            P.append(
                f"Let's start by taking a look at the valuation trajectory of your home "
                f"right now. Figure One below shows the valuation of your home, calculated "
                f"by nearby comparable sales at four different points in time over {span} "
                f"months.\n")
            P.append(f"**On this evidence it has {subj_dir} {subj_move}.**\n")
            P.append("{{CHART:trajectory}}")
            P.append(f"*{_fig(cap)}*\n")
            # The follow-on acknowledges what the chart actually shows -- flat/up read as
            # 'holding'; a genuine decline gets its own honest framing. Thresholded on the
            # subject's 18-month move so the sentence can never contradict the line above.
            subj_pct = tj["subject_full_pct"]
            if subj_pct <= -3:
                P.append(
                    f"Now we have our first data point, the price trajectory of your own "
                    f"home, and we can see it is showing some downward movement. We "
                    f"recognise that this is just one data point and, taken by itself, could "
                    f"be misleading — there are a number of reasons single valuations can be "
                    f"variable. We need more market context to confirm whether that "
                    f"direction is reflected in the broader market.\n")
            else:
                hold = ("holding — if anything, edging up —" if subj_pct >= 3
                        else "holding broadly steady")
                P.append(
                    f"Now we have our first data point, the price trajectory of your own "
                    f"home, and some comfort that the valuation is {hold} for now. What we "
                    f"need next is some greater context beyond just this one sample. The "
                    f"next ring out is to look at what's happening at the suburb level.\n")

    # ==== 2. What is your suburb doing? ========================================
    P.append(f"## 2. What is {b['suburb_display']} doing?\n")
    P.append(
        f"Your home is one data point. The suburb around it is the next ring out, and it "
        f"is measured two ways: the rolling median price, and how long homes take to "
        f"sell.\n")

    # Median price first, then days on market.
    yoy = None
    if sm:
        yoy = fb.pct("suburb_yoy", sm["yoy_pct"])
        window = fb.num("median_window_months", 12)
        n_sales = fb.num("n_suburb_sales", sm["n_now"])
        med_dir = "risen" if sm["yoy_pct"] >= 0 else "eased"
        P.append(
            f"On price, the {b['suburb_display']} rolling {window}-month house median has "
            f"**{med_dir} {yoy}** year-on-year, across {n_sales} sales.\n")
        if sm.get("series"):
            svg, cap = charts_mod.median_price_chart(sm["series"], b["suburb_display"], fb)
            if svg:
                charts["median"] = svg
                P.append("{{CHART:median}}")
                P.append(f"*{_fig(cap)}*\n")

    # Corroboration between the median chart and the days-on-market chart: does your
    # home's own 18-month trajectory agree with the suburb? (The old split-the-comps
    # "-2.7%" line was cut: that small-sample short-window signal is noise -- WS5.)
    # We state the suburb as DIRECTION only here, not a second percentage: the headline
    # above already owns the suburb-growth number (its 12-month YoY figure). Quoting the
    # trajectory's 18-month suburb % here read as the same "suburb median" disagreeing
    # with itself (6.9% vs 5.8%) a paragraph apart -- so we keep the subject's own
    # 18-month move (the trajectory's unique contribution) and give the suburb a word.
    if tj and sm:
        same = tj.get("same_direction")
        sub_up = tj["median_full_pct"] >= 0
        sub_dir, sub_opp = ("up", "down") if sub_up else ("down", "up")
        span = fb.num("traj_span2", tj["span_months"])
        subj = fb.pct("traj_subj2", tj["subject_full_pct"])
        if same:
            P.append(
                f"**And your home's own trajectory agrees with the suburb. Over the "
                f"{span} months we tracked, your estimate moved {subj} — and the suburb's "
                f"median moved the same way, {sub_dir} rather than {sub_opp}.**\n")
            P.append(f"**Your home has been moving with its suburb, not against it.**\n")
        else:
            P.append(
                f"**Over the {span} months we tracked, your estimate moved {subj}, while "
                f"the suburb's median moved the other way — the two have diverged.**\n")

    if dom and dom.get("timeline"):
        svg, cap = charts_mod.dom_chart(dom["timeline"], b["suburb_display"], fb)
        if svg:
            charts["dom"] = svg
            latest = fb.num("dom_latest", dom["latest"])
            sd = b["suburb_display"]
            if sm is not None:
                med_up = sm["yoy_pct"] >= 0
                moved = "risen" if med_up else "eased"
                price_word = "still rising" if med_up else "easing"
            else:
                moved, price_word = "moved", "moving"
            # PIVOT — sits ABOVE the days-on-market chart (Will 2026-08-25): frame the two
            # price points already seen, then turn to buyer demand, ahead of the chart.
            P.append(
                f"We need to consider these two data points together. The {sd} median has "
                f"{moved} over the past year, but a price is a lagging number: it confirms "
                f"what buyers have already done, not what they are about to do. The more "
                f"forward-looking signal is buyer demand — how quickly homes are selling.\n")
            P.append(
                f"Next, we need to take a close look at how the number of days homes are "
                f"taking to sell is changing. This is a key buyer demand signal, with low "
                f"numbers representing high buyer demand (homes selling quickly) and high "
                f"numbers indicating low buyer demand (homes taking longer to sell).\n")
            P.append("{{CHART:dom}}")
            P.append(f"*{_fig(cap)}*\n")

            # Early interpretation of the price vs time-on-market signals the reader has
            # now seen, grounded in the leading-indicator research. Every claim here is
            # DERIVED from the same timeline the chart draws -- the year-ago figure and
            # the DIRECTION of the move are read off the 2025-QN point, never asserted --
            # so the prose cannot contradict the picture beside it. It once did: a
            # hardcoded "from around half that a year ago" claimed DOM had doubled, when
            # Burleigh Waters' had in fact SHORTENED (37 -> 29 days). Sign-aware on both
            # price and liquidity; strictly no forecast.
            tl = dom["timeline"]
            _days = [p.get("median_days_on_market") for p in tl
                     if p.get("median_days_on_market")]
            dlo = fb.num("dom_range_lo", int(min(_days)))
            dhi = fb.num("dom_range_hi", int(max(_days)))
            # the SAME-quarter point one year earlier, straight off the chart's timeline
            year_ago = None
            lp = (tl[-1].get("period") or "") if tl else ""
            if "-Q" in lp:
                _y, _q = lp.split("-Q")
                for p in tl:
                    if p.get("period") == f"{int(_y) - 1}-Q{_q}" \
                            and p.get("median_days_on_market"):
                        year_ago = p["median_days_on_market"]
                        break
            # (item 2) The claim is substantiated by three peer-reviewed papers, one of
            # them Australian; each superscript hyperlinks to its entry in References.
            # These are real, source-verified citations (RePEc / journal sites), not
            # placeholders. The US Federal Reserve line was cut (Will).
            _P1 = ("Genesove, D. & Han, L. (2012). “Search and Matching in the Housing "
                   "Market.” Journal of Urban Economics, 72(1), 31–45.")
            _P2 = ("Carrillo, P. E. (2013). “To Sell or Not to Sell: Measuring the Heat of "
                   "the Housing Market.” Real Estate Economics, 41(2), 310–346.")
            _P3 = ("Khezr, P. & Menezes, F. (2015). “Time on the Market and Price Change: "
                   "The Case of Sydney Housing Market.” Applied Economics, 47(5), 485–498.")
            research = ("Housing-market research finds that as demand eases, homes take "
                        "longer to sell before the median itself gives way"
                        + _cite(_P1) + _cite(_P2) + _cite(_P3))
            if year_ago is not None:
                ya = fb.num("dom_year_ago", int(round(year_ago)))
                delta = dom["latest"] - year_ago
                if delta >= 3:            # lengthening -- the leading signal is moving
                    P.append(
                        f"And in {sd} it has begun to move: the median time on market "
                        f"lengthened to {latest} days last quarter, from {ya} days a year "
                        f"earlier. {research}.\n")
                    P.append(
                        f"So a market where prices are {price_word} while time on market "
                        f"lengthens is one whose early momentum may be easing — a signal "
                        f"to watch, not a fall. And {latest} days is still relatively "
                        f"quick by {sd}'s "
                        f"own recent record, which has run between {dlo} and {dhi} days "
                        f"over the past two years; the most reliable conclusion is heat "
                        f"coming out of a fast market, not that the market is in retreat.\n")
                elif delta <= -3:         # shortening -- the leading signal has NOT turned
                    P.append(
                        f"In {sd} that signal has not turned: the median time on market was "
                        f"{latest} days last quarter, shorter than the {ya} days of a year "
                        f"earlier — homes are being absorbed at least as quickly as before. "
                        f"{research} — and here that leading signal has yet to turn.\n")
                    P.append(
                        f"So the forward-looking signal and the backward-looking one point "
                        f"the same way for now: prices {price_word}, homes selling briskly. "
                        f"{latest} days sits toward the quick end of {sd}'s own recent "
                        f"record, which has run between {dlo} and {dhi} days over the past "
                        f"two years — not a market in retreat, but the number to watch, "
                        f"because buyer demand tends to turn before price does.\n")
                else:                     # roughly flat -- steady
                    P.append(
                        f"In {sd} it has barely moved: the median time on market was "
                        f"{latest} days last quarter, close to the {ya} days of a year "
                        f"earlier. {research} — so this is the signal to watch, and for now "
                        f"it is holding steady.\n")
                    P.append(
                        f"{latest} days sits within {sd}'s own recent record of {dlo} to "
                        f"{dhi} days over the past two years; prices are {price_word} and "
                        f"homes are selling at much the same pace as a year ago.\n")
            else:
                # No clean year-ago point on the chart: describe the level against the
                # two-year range only, and make no year-on-year direction claim.
                P.append(
                    f"In {sd} the median time on market was {latest} days last quarter, "
                    f"the number to watch. {research}. {latest} days sits within {sd}'s own "
                    f"recent record of {dlo} to {dhi} days over the past two years.\n")

            P.append(
                f"**Price figures alone cannot tell you where things go next — they only "
                f"tell us what has happened, not what will happen.**\n")
            P.append(
                f"For that you have to look underneath them, at the demand that drives a "
                f"market: who is moving here, whether there is work, and what people can "
                f"afford.\n")

    # ==== 3. Why is the suburb holding up differently? =========================
    # Rebuilt as real, cited fundamentals: who is moving, where the work is, and
    # what the same money buys. Every figure carries a source; the passage is
    # evidence-with-context and stops short of a conclusion, per the editorial
    # no-forecast rule -- the reader draws the inference.
    fund, lab, arb = b.get("fundamentals"), b.get("labour"), b.get("arbitrage")
    if sm and (fund or lab or arb):
        # Sign-aware: the whole "holding up differently" thesis rests on the suburb median
        # being UP while the nation falls. Do not hardcode that -- read it from sm and
        # open the other way if the suburb has itself begun to ease.
        loc_up = sm["yoy_pct"] >= 0
        loc_word = "risen" if loc_up else "eased"
        if loc_up:
            P.append(f"## 3. Why is {b['suburb_display']} holding up differently?\n")
            P.append(
                f"So two records point different ways at once: nationally, values are "
                f"falling — for the reasons set out at the start, rising rates and inflation "
                f"and stretched affordability — yet {b['suburb_display']}'s median has risen "
                f"{yoy} over the year. Those national forces reach every market; the "
                f"question is what has offset them here. The answer is not in the price "
                f"figures at all, but in who is moving, where the work is, and what the same "
                f"money buys.\n")
        else:
            P.append(f"## 3. What sits underneath {b['suburb_display']}'s market?\n")
            P.append(
                f"The national weakness set out at the start — rising rates, inflation, "
                f"stretched affordability — has reached here too: {b['suburb_display']}'s "
                f"median has eased {yoy} over the year. But a price is only the surface. "
                f"What a national average cannot see is the demand underneath a market — who "
                f"is moving, where the work is, and what the same money buys — and that is "
                f"what decides how far a market has to fall.\n")

        # -- who is moving (migration), with the land-value comparison folded in
        #    (Will 2026-08-25): trimmed to the headline interstate-gain fact, and the
        #    "what the same money buys" material moved up under this heading.
        if fund and fund.get("migration"):
            P.append(f"### Who is moving\n")
            mig0 = fund["migration"][0]
            mtext = mig0["text"].split("; New South Wales alone")[0].rstrip(" ;,")
            P.append(_upper1(fb.allow_literal(
                f"{mtext} ({mig0['source']}, {mig0['period']}).")))
            P.append("So why are people moving from Sydney to the Gold Coast?")

        if arb and arb.get("headline_comparison"):
            # arb is now this SUBURB's slice; angle drives the frame. subject_land is the
            # actual subject's block (feat), not a hardcoded constant (old bug: every
            # Robina article claimed 907 m²).
            h = arb["headline_comparison"]
            angle = arb.get("angle", "land")
            subj_land = feat.get("land_size_sqm")
            beach = fb.num("arb_beach", arb["beach_km"], dp=1)
            med_price = fb.money("arb_gc_price", arb["median_price"])
            med_land = fb.num("arb_gc_land", arb["median_land"])
            syd_price = fb.money("arb_syd_price", h["median_price"])
            syd_land = fb.num("arb_syd_land", h["median_land"])
            syd_dist = fb.num("arb_syd_cbd", h["dist_cbd_km"], dp=0)
            # Price-aware: only say "the same money" when the Sydney comp is within ~10%
            # of the local anchor. When it is materially cheaper, say so -- less money in
            # Sydney still buys far less land, further out (a stronger contrast, kept honest).
            if h["median_price"] >= arb["median_price"] * 0.90:
                syd_line = (f"The same money in Sydney reaches only the outer fringe: in "
                            f"{h['suburb']}, about {syd_dist} km from the CBD, a house sells "
                            f"for around {syd_price} on about {syd_land} m² (public sold "
                            f"records). ")
            else:
                syd_line = (f"In Sydney, even {syd_price} — less than that — reaches only "
                            f"the outer fringe: in {h['suburb']}, about {syd_dist} km from "
                            f"the CBD, that buys about {syd_land} m² (public sold records). ")
            if angle == "lifestyle":
                # smaller blocks here -- do NOT claim more land; lead on lake/coast and price
                P.append(
                    f"At about {med_price}, a {b['suburb_display']} house costs less than "
                    f"the Gold Coast's pricier suburbs, and it sits in a lake suburb about "
                    f"{beach} km from the beach. " + syd_line
                    + f"The block here is smaller — about {med_land} m² against {syd_land} "
                    f"m² there — so this is not a land story but a lifestyle and location "
                    f"one: the lake and the coast against a long commute.\n")
            else:
                this_home = (f"; this home on {fb.num('arb_subj_land', int(subj_land))} m²"
                             if subj_land else "")
                P.append(
                    f"{b['suburb_display']}'s median house, about {med_price}, sits on a "
                    f"{med_land} m² block{this_home}, {beach} km from the beach (our "
                    f"records). " + syd_line
                    + "The blocks are the fact; the beach and the commute are the context.\n")
            cmp_ex = b.get("comparison")
            if cmp_ex:
                cards = comparison_cards(cmp_ex, fb)
                if cards:
                    charts["comparison"] = cards
                    P.append("{{CHART:comparison}}")
            if fund and fund.get("affordability"):
                a = fund["affordability"]
                P.append(fb.allow_literal(
                    f"The affordability gap sits underneath it: {a['text']} ({a['source']}, "
                    f"{a['period']}). ")
                    + "For a buyer moving north, the equity that reaches an outer-fringe "
                    "block in Sydney reaches more land, closer to the water, here.\n")

        # -- where the work is (jobs) --
        if lab and lab.get("states"):
            st = lab["states"]; lbl = lab.get("labels") or {}
            q, n, v = st.get("qld", {}), st.get("nsw", {}), st.get("vic", {})
            P.append(f"### Where the work is\n")
            if all(x.get("vacancies_per_1000_employed") for x in (q, n, v)):
                # All three comparisons are DERIVED from the values, not asserted: the
                # "strongest here" claim only fires if QLD actually leads on vacancies,
                # and QLD's unemployment standing is read from the ranking rather than a
                # hardcoded "about a point above". Otherwise a data shift would leave the
                # adjectives contradicting the numbers printed beside them.
                qv = q["vacancies_per_1000_employed"]
                nv = n["vacancies_per_1000_employed"]
                vv = v["vacancies_per_1000_employed"]
                qld_vac_top = qv >= nv and qv >= vv
                lead = ("Labour demand is strongest here on a per-person basis. "
                        if qld_vac_top else
                        "Labour demand, measured per person, runs close across the three "
                        "states. ")
                vac_sent = fb.allow_literal(
                    lead + f"For every 1,000 people employed, Queensland has about "
                    f"{qv:.0f} job vacancies open, against {nv:.0f} in New South Wales and "
                    f"{vv:.0f} in Victoria ({lab['source']['vacancies']}, "
                    f"{lbl.get('vacancies_period','')}). ")

                qu, nu, vu = (q.get("unemp_3mo_avg"), n.get("unemp_3mo_avg"),
                              v.get("unemp_3mo_avg"))
                unemp_sent = ""
                if None not in (qu, nu, vu):
                    qld_low = qu <= nu and qu <= vu
                    stem = (f"Queensland's unemployment, around {qu}% over the three months "
                            f"to {lbl.get('unemp_period','')}, ")
                    tail = (f"is the lowest of the three, below New South Wales ({nu}%) and "
                            f"Victoria ({vu}%)" if qld_low else
                            f"ran alongside New South Wales ({nu}%) and Victoria ({vu}%)")
                    unemp_sent = fb.allow_literal(
                        stem + tail + f" ({lab['source']['unemployment']}). ")

                jy = q.get("jobs_added_yoy", 0) or 0
                jverb = "added" if jy >= 0 else "shed"
                jobs_sent = fb.allow_literal(
                    f"Queensland {jverb} about {round(abs(jy)/1000)*1000:,} jobs over the "
                    f"year to {lbl.get('employed_period','')}.")
                P.append(vac_sent + unemp_sent + jobs_sent + "\n")

                # Bar chart of the three states' unemployment, QLD (the lowest) highlighted.
                if None not in (qu, nu, vu):
                    bsvg, _ = charts_mod.state_bar_chart(
                        [("Queensland", qu), ("New South Wales", nu), ("Victoria", vu)],
                        fb, key="unemp", focal="Queensland",
                        title="Unemployment rate by state")
                    if bsvg:
                        charts["unemp"] = bsvg
                        P.append("{{CHART:unemp}}")
                        P.append(fb.allow_literal("*" + _fig(
                            f"Unemployment rate by state, three-month average to "
                            f"{lbl.get('unemp_period','')}. A lower rate points to tighter "
                            f"labour demand — more competition for workers, fewer people "
                            f"out of work. Source: {lab['source']['unemployment']}.") + "*\n"))

        # -- close: a summarising conclusion drawn from the demand evidence (Will
        #    2026-08-25), sign-aware so it never asserts 'holding up' on an easing suburb.
        if loc_up:
            P.append(
                f"So we can see strong underlying demand factors are holding up the "
                f"{b['suburb_display']} market and making it more resilient in the face of "
                f"the declines in major cities such as Sydney and Melbourne. What we need "
                f"to do next is look for stronger leading indicators of price moves — "
                f"specific economic metrics we can follow that often signal a market turn "
                f"in advance.\n")
        else:
            P.append(
                f"So these are the underlying demand factors — people, work, value — that "
                f"decide how far a market moves, and they are what sits beneath "
                f"{b['suburb_display']}'s softening even as the national declines reach "
                f"here. What we need to do next is look for stronger leading indicators of "
                f"price moves — specific economic metrics we can follow that often signal a "
                f"market turn in advance.\n")

    # ==== 4. What will happen in the future? ===================================
    # The payoff section: deploy Fields' own lead/lag research + the current live
    # reading of the leading indicator (QLD wages), give the reader real evidence,
    # and stop short of a conclusion. Heading is Will's; strictly no forecast [7].
    dr = (fund or {}).get("drivers_research")
    P.append("## 4. Is the Gold Coast market about to fall, and the value of your "
             "property with it?\n")
    P.append(
        f"No one can tell you for a fact what your home will be worth next year, and "
        f"anyone who names a figure is selling you a guess. But unknowable is not the same "
        f"as unreadable. A market leaves a trail before it moves, and one of the best ways "
        f"to read where it is heading is to watch the signals that turn first — not the "
        f"price, which you have already seen arrives late.\n")

    if dr:
        # our empirical lead/lag finding — the evidence, cited to our own analysis
        lag = fb.allow_literal(dr["lagging"][0]) if dr.get("lagging") else ""
        lead_join = "; ".join(fb.allow_literal(x) for x in (dr.get("leading") or []))
        income = fb.allow_literal(dr["income"]) if dr.get("income") else ""
        P.append(
            f"So we did the work. Across {fb.allow_literal(dr['scope'])}, we set out to "
            f"separate the indicators that lead {b['suburb_display']}'s prices from the "
            f"ones that only confirm them, and the answer runs against what most people "
            f"watch. The number on every front page — interest rates — is a lagging one: "
            f"{lag}. What leads, in that data, is money in people's pockets: {lead_join}. "
            f"And underneath all of it, {income} ({_upper1(dr.get('source','Fields'))}, "
            f"{_link('what_drives')}).\n")

    # the current live readings of the two leading indicators, each as a chart
    li = (lab or {}).get("leading_indicators") or {}
    wpi_i, hs_i = li.get("wpi"), li.get("household_spending")
    if wpi_i or hs_i:
        P.append(
            f"So the question worth asking is not where prices go next, but what those "
            f"leading indicators are doing now. Two of them we can read straight from the "
            f"Bureau of Statistics for Queensland, and both are below — each as the change "
            f"on a year earlier.\n")
        # Directions DERIVED from each series (as with the DOM fix): a hardcoded "eased /
        # from the high fours / held up" inverts silently if the data moves. We read the
        # two-year move and the last-year slope off the series itself.
        def _clean(series):
            return [p["value"] for p in series if p.get("value") is not None]

        wage_eased = None
        if wpi_i and wpi_i.get("series"):
            svg, cap = charts_mod.indicator_chart(
                wpi_i["title"], wpi_i["subtitle"], wpi_i["series"], wpi_i["source"], fb, "wpi")
            if svg:
                charts["wpi"] = svg
                wv = _clean(wpi_i["series"])
                last_v, start_v = wpi_i["latest"], wv[0]
                wage_eased = last_v < start_v
                long_word = "eased" if wage_eased else "risen"
                back = wv[-5] if len(wv) >= 5 else wv[0]          # ~4 quarters ago
                recent, pos = last_v - back, last_v > 0
                if not pos:
                    trend = "It has now turned negative"
                elif abs(recent) < 0.3:
                    trend = ("It is still positive but no longer accelerating — over the "
                             "past year broadly flat")
                elif recent < 0:
                    trend = "It is still positive but has kept easing over the past year"
                else:
                    trend = "It is positive and has picked up a little over the past year"
                wp = fb.allow_literal(f"{last_v:.1f}%")
                sv = fb.allow_literal(f"{start_v:.1f}%")
                P.append(
                    f"Wage growth — the indicator with the longest lead in our analysis — "
                    f"has {long_word} over the past two years, from about {sv} to about "
                    f"{wp} a year ({wpi_i['source']}, {wpi_i['period']}). {trend}. In our "
                    f"data, accelerating wages preceded price growth three to four months "
                    f"on, and fading wages preceded softer conditions.\n")
                P.append("{{CHART:wpi}}")
                P.append(f"*{_fig(cap)}*\n")

        spend_word = None
        if hs_i and hs_i.get("series"):
            svg, cap = charts_mod.indicator_chart(
                hs_i["title"], hs_i["subtitle"], hs_i["series"], hs_i["source"], fb, "hs")
            if svg:
                charts["hs"] = svg
                hv = _clean(hs_i["series"])
                h_last = hs_i["latest"]
                h_back = hv[-13] if len(hv) >= 13 else hv[0]      # ~12 months ago
                h_delta = h_last - h_back
                spend_word = ("picked up" if h_delta >= 0.5
                              else "softened" if h_delta <= -0.5 else "held broadly steady")
                hp = fb.allow_literal(f"{h_last:.1f}%")
                contrast = ""                                     # only if data diverges
                if wage_eased and spend_word != "softened":
                    contrast = " Where pay growth has eased, the till has not."
                elif wage_eased is False and spend_word == "softened":
                    contrast = " Where pay growth has firmed, spending has not followed."
                P.append(
                    f"Household spending — the strongest gauge of market strength in our "
                    f"analysis, and a proxy for the confidence that precedes a purchase — "
                    f"has {spend_word}, running about {hp} a year ({hs_i['source']}, "
                    f"{hs_i['period']}).{contrast}\n")
                P.append("{{CHART:hs}}")
                P.append(f"*{_fig(cap)}*\n")

        q = ((lab or {}).get("states") or {}).get("qld") or {}
        vac = q.get("vacancies_per_1000_employed")
        vac_clause = (f"the roughly {fb.allow_literal(f'{vac:.0f}')} job vacancies per "
                      f"thousand workers and the migration north from the last section"
                      if vac else "the migration and jobs from the last section")
        pay_phrase = ("pay growth easing" if wage_eased
                      else "pay growth firming" if wage_eased is False else "pay growth")
        spend_phrase = {"picked up": "spending rising", "softened": "spending softening",
                        "held broadly steady": "spending holding"}.get(spend_word, "spending")
        P.append(
            f"Set the two against each other — {pay_phrase}, {spend_phrase} — and "
            f"beside {vac_clause}, and you are looking at the forward part of the picture "
            f"in one place.\n")

    # the home's own attributes — one input, not the whole answer
    land = feat.get("land_size_sqm")
    micro = feat.get("micro_location_premium_pct")
    bits = []
    if land:
        bits.append(f"a {fb.num('q4_land', land)} m² block")
    if feat.get("pool_present"):
        bits.append("a pool")
    if isinstance(micro, (int, float)) and abs(micro) >= 0.03:
        bits.append(f"a position our model reads at a {fb.pct('q4_micro', micro * 100)} "
                    f"premium to the suburb")
    if bits:
        joined = (", ".join(bits[:-1]) + (", and " if len(bits) > 1 else "") + bits[-1])
        P.append(
            f"Closer in, your own house is what a buyer here weighs directly: {joined} — "
            f"the features the comparable sales show buyers paying up for.\n")

    # A calibrated assessment: what the evidence says NOW, not a forecast. SIGN-AWARE --
    # it branches on the actual direction of the home estimate, the suburb median and
    # days-on-market, so it reads correctly on a home/suburb that is easing, not only on
    # one that is rising. Reports indicators + characterises the present state; never a
    # price prediction.
    if tj and sm:
        subj_pct, med_pct = tj["subject_full_pct"], sm["yoy_pct"]
        subj_up, med_up = subj_pct >= 0, med_pct >= 0
        s_move = fb.pct("read_subj", subj_pct)
        m_move = fb.pct("read_yoy", med_pct)
        s_span = fb.num("read_span", tj["span_months"])
        s_word = "risen" if subj_up else "eased"
        m_word = "risen" if med_up else "eased"
        dom_yoy = (b["dom"] or {}).get("yoy_days")
        dom_rising = isinstance(dom_yoy, (int, float)) and dom_yoy > 0

        if subj_up and med_up:
            lead = (f"**Our reading: there is no evidence yet that {short} is declining.** "
                    f"Its own estimate has {s_word} {s_move} over the {s_span} months to "
                    f"today, and {b['suburb_display']}'s median {m_word} {m_move} over the "
                    f"year — both still pointing up. ")
            if dom_rising:
                mid = ("What has changed is the pace, not the price — the lengthening time "
                       "on market, and wage growth that has eased even as spending has "
                       "held, describe a market carrying less momentum than a year ago. "
                       "The honest characterisation of the evidence is slower growth and "
                       "greater uncertainty, not a market that has turned down. ")
            else:
                mid = ("Time on market has not lengthened, and household spending has held "
                       "even as wage growth eased — the momentum signals are, for now, "
                       "steady. The honest characterisation of the evidence is continued, "
                       "if unhurried, growth. ")
        elif (not subj_up) and (not med_up):
            lead = (f"**Our reading: {short} has begun to ease, in step with its suburb.** "
                    f"Its own estimate has {s_word} {s_move} over the {s_span} months to "
                    f"today, and {b['suburb_display']}'s median {m_word} {m_move} over the "
                    f"year — {b['suburb_display']} is now participating in the national "
                    f"softening rather than resisting it. ")
            mid = (f"With time on market {'lengthening' if dom_rising else 'holding'} and "
                   f"the leading signals off their highs, the honest characterisation is a "
                   f"market that has turned, gently, and warrants watching closely. ")
        else:
            lead = (f"**Our reading: the signals for {short} are mixed.** Its own estimate "
                    f"has {s_word} {s_move} over the {s_span} months to today, while "
                    f"{b['suburb_display']}'s median has {m_word} {m_move} over the year — the "
                    f"two point different ways, which on a small sample is a caution "
                    f"against reading either as settled. ")
            mid = ("The honest characterisation is a market losing momentum without yet a "
                   "clear direction. ")
        P.append(
            lead + mid
            + f"That is what the data says today, not a promise about next year; were the "
            f"signals that lead prices to roll over, this reading would move with them.\n")
    # A monitoring framework: what Fields would watch, and the conditional it rests on.
    # Historical relationship + 'if X then historically Y', not a forecast; names data
    # to follow, not an action to take.
    # Reformatted (Will 2026-08-25): unbolded and broken into scannable dials + short
    # lines, so a reader's eye can pick out the labels of what to watch.
    P.append("So here is what we would be watching from here, and would suggest you "
             "watch too — four dials:")
    P.append("- **Wage growth**")
    P.append("- **The oil price** that drove the recent inflation")
    P.append("- **Household spending**")
    P.append("- **Time on market**")
    P.append(fb.allow_literal(
        "Our own concern: wage growth has already slowed, while the inflation pressure "
        "behind the rate rises has not fully resolved."))
    P.append("**" + fb.allow_literal(
        "If wage growth keeps falling and household spending turns down with it, that is "
        "the combination that has — in our data — preceded softer prices 3 to 4 months "
        "on. A days-on-market figure that keeps climbing would be the earliest "
        "confirmation.") + "**")
    P.append("None of that has happened yet. These are simply the dials worth watching.\n")
    P.append(
        f"To go further: {_link('fundamentals')} on what the Gold Coast market rests on, "
        f"and {_intel_link(b['suburb_display'])} for how {b['suburb_display']} is trading "
        f"right now.\n")

    # ==== limits ===============================================================
    P.append("## What this can't tell you\n")
    mae2 = fb.pct("mae2", MAE_PCT, signed=False)
    limits = (
        f"We publish this method's mean absolute error: about {mae2} in this price range. "
        f"{n_comps.capitalize()} sales sit behind your home's estimate -- a small number, "
        f"stated plainly so you can weigh it. ")
    if sm:
        limits += (f"The {b['suburb_display']} median rests on {fb.num('n_suburb_sales2', sm['n_now'])} "
                   f"recorded sales, which is a sample of the suburb's activity rather than "
                   f"all of it. ")
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

    # ---- References: the empirical research cited above, superscript-numbered --------
    if _refs:
        P.append("## References\n")
        for _i, _entry in enumerate(_refs, 1):
            P.append(fb.allow_literal(
                f"[[ref:{_refword(_i)}]]{_refmark(_i)} {_entry}"))

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
h3{font:600 1.06rem/1.35 -apple-system,Segoe UI,Roboto,sans-serif;margin:2rem 0 .6rem;
 color:var(--ink)}
a{color:var(--accent)}
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
.cmp{margin:1.9rem 0 1.6rem}
.cmp-grid{display:grid;grid-template-columns:1fr 1fr;gap:1rem}
.cmp-card{border:1px solid var(--rule);border-radius:12px;overflow:hidden;
 background:var(--tint)}
.cmp-tag{font:600 11px/1 -apple-system,Segoe UI,Roboto,sans-serif;letter-spacing:.1em;
 text-transform:uppercase;color:var(--accent);padding:.7rem .8rem .5rem}
.cmp-img{display:block;width:100%;height:auto;aspect-ratio:640/420;object-fit:cover;
 background:var(--band)}
.cmp-body{padding:.75rem .85rem .9rem}
.cmp-suburb{font:600 15px/1.2 -apple-system,Segoe UI,Roboto,sans-serif;color:var(--ink)}
.cmp-price{font:700 20px/1.15 -apple-system,Segoe UI,Roboto,sans-serif;color:var(--ink);
 margin:.15rem 0 .3rem;font-variant-numeric:tabular-nums}
.cmp-facts{font:400 13.5px/1.4 -apple-system,Segoe UI,Roboto,sans-serif;color:var(--muted)}
.cmp-land{color:var(--accent);font-weight:700}
.cmp-ctx{font:400 12.5px/1.4 -apple-system,Segoe UI,Roboto,sans-serif;color:var(--muted);
 margin-top:.25rem}
.cmp-cap{font:400 12.5px/1.5 -apple-system,Segoe UI,Roboto,sans-serif;color:var(--muted);
 margin:.7rem 0 0}
@media (max-width:30rem){.cmp-grid{grid-template-columns:1fr}}
@media print{.cmp-card{break-inside:avoid}.cmp-grid{gap:.6rem}}
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
        # Extract markdown links first so their URLs are not touched by the
        # entity-escaping below, then restore as anchors.
        links = []

        def _stash(m):
            links.append((m.group(1), m.group(2)))
            return f"\x00L{len(links)-1}\x00"
        # links: external https, and internal #fragment anchors (reference superscripts)
        s = re.sub(r"\[([^\]]+)\]\(((?:https?://|#)[^)]+)\)", _stash, s)
        # reference targets [[ref:word]] -> an id span (stashed past the escaper)
        anchors = []

        def _astash(m):
            anchors.append(m.group(1))
            return f"\x00A{len(anchors)-1}\x00"
        s = re.sub(r"\[\[ref:([a-z]+)\]\]", _astash, s)
        s = (s.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")
              .replace("--", "&mdash;"))
        s = re.sub(r"\*\*(.+?)\*\*", r"<strong>\1</strong>", s)
        s = re.sub(r"(?<!\*)\*(?!\*)(.+?)(?<!\*)\*(?!\*)", r"<em>\1</em>", s)
        for i, (text, url) in enumerate(links):
            anchor = (f'<a href="{url}" style="color:var(--accent);'
                      f'text-decoration:underline">{text}</a>')
            s = s.replace(f"\x00L{i}\x00", anchor)
        for i, word in enumerate(anchors):
            s = s.replace(f"\x00A{i}\x00", f'<span id="ref-{word}"></span>')
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
        if ln.startswith("- "):
            items = []
            while i < len(lines) and lines[i].startswith("- "):
                items.append(f"<li>{inline(lines[i][2:])}</li>")
                i += 1
            out.append("<ul>" + "".join(items) + "</ul>")
            continue
        if ln.startswith("### "):
            out.append(f"<h3>{inline(ln[4:])}</h3>")
        elif ln.startswith("## "):
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
          variant="report", skip_trajectory=False):
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
    # Loud, unconditional warning if the national headline would rest on placeholder
    # macro figures. A provisional-fed "falling for N months" claim must never reach
    # print unnoticed -- this fires on every build until the months are confirmed.
    if macro and (macro.get("derived") or {}).get("uses_provisional"):
        print("    ⚠ MACRO HEADLINE USES PROVISIONAL DATA: the 'falling for N months / "
              "Brisbane previously positive' claim rests on placeholder figures in "
              "macro_context.json. Replace the provisional months with real Cotality "
              "figures and rerun update_macro_context.py before mailing.", file=sys.stderr)
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

    # Four point-in-time valuations of THIS home (18/12/6/0 months ago), each run
    # through the real engine as-of that date. Fail-soft: a home whose older
    # anchors cannot be valued (thin historical pool) simply omits the section, the
    # same way every other optional passage guards itself. Never let its cost or a
    # failure break the article -- it is enrichment, not a load-bearing figure.
    trajectory = None
    if not skip_trajectory:
        try:
            trajectory = traj_mod.TrajectoryEngine(client, suburb_key).compute(doc)
        except Exception as e:                              # noqa: BLE001
            if verbose:
                print(f"    ! trajectory section omitted: {type(e).__name__}: {e}",
                      file=sys.stderr)

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
        "trajectory": trajectory,
        "fundamentals": load_fundamentals(),
        "labour": _load_json("labour_context.json"),
        # arbitrage + comparison are now suburb-keyed; select this suburb's slice.
        "arbitrage": (_load_json("arbitrage_context.json") or {}).get(suburb_key),
        "comparison": (_load_json("comparison_examples.json") or {}).get(suburb_key),
    }

    md, fb, charts = compose(bundle, variant)

    dom_prose = check_dom_prose_consistency(md, dom)
    if dom_prose:
        return {"ok": False, "stage": "consistency", "address": full_addr,
                "errors": dom_prose, "markdown": md}

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
        _archival = re.sub(r"\{\{CHART:(\w+)\}\}",
                           lambda m: f"*[chart: {m.group(1)}]*", md)
        _archival = re.sub(r"\[\[ref:[a-z]+\]\]", "", _archival)   # strip anchor markers
        fh.write(_archival)

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
    ap.add_argument("--no-trajectory", action="store_true",
                    help="skip the 4-point price-trajectory section (faster; the "
                         "section runs the valuation engine 4x)")
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
                  a.skip_market_check, a.no_hero, variant=v,
                  skip_trajectory=a.no_trajectory)
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
