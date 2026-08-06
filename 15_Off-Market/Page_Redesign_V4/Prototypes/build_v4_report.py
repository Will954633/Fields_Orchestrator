#!/usr/bin/env python3
"""
build_v4_report.py — render the V4 off-market flow as markdown for one address.

Reads the EXISTING fact bundle (Page_Redesign_V2/fact_bundle.py), which already
assembles obvious_comp, scarcity, green_space, POIs, valuation, buyer and
value_drivers. This only changes the SEQUENCE and the COPY, per
Product/05_PAGE_FLOW.md.

    python3 build_v4_report.py --slug 26-moorabbin-place-robina --suburb robina
    python3 build_v4_report.py --slug 27-huntingdale-crescent-robina --backtest

`--backtest` additionally runs valuation_backtest.backtest_single_property() to
get per-comparable ADJUSTED prices. Only valid for a home that has already sold —
it excludes the subject by _id and drops every sale on/after its sale date. Never
use precompute_property_valuation() on a sold home: its comp filter lets the
subject's own sale back in as its own top comparable.

Every section reports whether it rendered, so the output doubles as a coverage
audit. Sections that cannot render say why — per the flow doc, stating why a
figure is absent is a credential, not an apology.
"""
import argparse
import os
import re
import sys
from datetime import datetime

HERE = os.path.dirname(os.path.abspath(__file__))
ORCH = "/home/fields/Fields_Orchestrator"
sys.path.insert(0, os.path.join(ORCH, "15_Off-Market/Page_Redesign_V2"))
sys.path.insert(0, os.path.join(ORCH, "scripts"))
sys.path.insert(0, "/home/fields/Feilds_Website/07_Valuation_Comps")

import fact_bundle                                        # noqa: E402
from src.mongo_client_factory import get_mongo_client      # noqa: E402

MISSING = []          # (section, reason) — the coverage audit


def money(v):
    try:
        return f"${int(round(float(v))):,}"
    except Exception:
        return None


def money_m(v):
    """Consumer-facing money: millions to 2dp. A range precise to the dollar
    reads as algorithmic output and contradicts "the width is the honest part"."""
    try:
        f = float(v)
    except Exception:
        return None
    if f >= 1_000_000:
        return "$" + f"{f/1_000_000:.2f}".rstrip("0").rstrip(".") + " million"
    return f"${int(round(f)):,}"


def anchor(low, high, point=None):
    """assemble._anchor — rounded to $50k, spelled in millions. Deliberately
    approximate: an exact central figure reads as false precision."""
    base = point if point else (low + high) / 2
    r = round(base / 50000) * 50000
    m = f"{r / 1_000_000:.2f}".rstrip("0").rstrip(".")
    return f"${m} million"


def _humanise_query(q):
    """compute_intel returns e.g. '5 bedrooms · 798 m² · 240 m² · Yes' — the bare
    'Yes' is the pool flag and reads as a data leak on the page."""
    if not q:
        return "its core combination"
    parts = [p.strip() for p in str(q).split("·")]
    out = []
    for i, p in enumerate(parts):
        if p.lower() in ("yes", "true"):
            out.append("a pool")
        elif p.lower() in ("no", "false"):
            continue
        elif p.endswith("m²"):
            # first m² is land, second is internal floor area
            seen = sum(1 for x in out if "m²" in x)
            out.append(f"{p} of {'floor area' if seen else 'land'}")
        else:
            out.append(p)
    return ", ".join(out[:-1]) + " and " + out[-1] if len(out) > 1 else (out[0] if out else "its core combination")


def skip(section, reason):
    MISSING.append((section, reason))
    return f"> *[{section} — not rendered: {reason}]*\n"


# ── data helpers ────────────────────────────────────────────────────────────

def last_sale(gc, suburb_key, address):
    """The most recent PRICED sale for this exact address.

    ⚠ Two traps, both found by rendering a real property:
      1. Match on the FULL address. An earlier version regexed on
         `slug.split("-")[0]` — the street number — so "26-moorabbin-place"
         searched for "26" and matched any address containing 26. It returned
         another home's sale history under this home's heading. This is the §0
         hard fact, the single most load-bearing line on the page.
      2. Prefer the doc's own sale over the timeline. `property_timeline` is the
         historical record and lags a just-completed sale, so a home that sold
         last month can report a sale from 2016.
    """
    doc = gc[suburb_key].find_one({"address": address},
                                  {"scraped_data.property_timeline": 1,
                                   "sale_price": 1, "sold_date": 1,
                                   "listing_status": 1})
    if not doc:
        return None
    if doc.get("listing_status") == "sold" and doc.get("sale_price") and doc.get("sold_date"):
        digits = re.sub(r"[^\d]", "", str(doc["sale_price"]))
        if digits:
            return {"date": doc["sold_date"], "price": int(digits), "_source": "own sale"}
    tl = ((doc.get("scraped_data") or {}).get("property_timeline")) or []
    sales = [e for e in tl
             if str(e.get("category", "")).lower() == "sale" and e.get("price")]
    if not sales:
        return None
    sales.sort(key=lambda e: str(e.get("date") or ""), reverse=True)
    s = dict(sales[0]); s["_source"] = "property_timeline"
    return s


def market_snapshot(suburb_key):
    """market_pulse.data_snapshot for this suburb.

    ⚠ Read `data_snapshot` ONLY. `summary` and `narrative.pillars` go stale
    independently and a partial $set touches only what it names (CLAUDE.md Rule 6).
    """
    from pymongo import MongoClient
    c = MongoClient(os.environ["COSMOS_CONNECTION_STRING"], retryWrites=False)
    d = c["system_monitor"]["market_pulse"].find_one({"suburb": suburb_key})
    return (d or {}).get("data_snapshot") or {}


def held_years(date_str):
    try:
        d = datetime.fromisoformat(str(date_str)[:10])
        return round((datetime.now() - d).days / 365.25, 1)
    except Exception:
        return None


# ── sections ────────────────────────────────────────────────────────────────

def s0_arrival(b, ls):
    f = b.get("subject") or {}
    out = [f"# {b.get('address_short') or b['address']}",
           f"### {b.get('suburb_display')}, QLD", ""]
    bits = []
    if f.get("land_sqm"):
        bits.append(f"{f['land_sqm']} m²")
    if f.get("bedrooms"):
        bits.append(f"{f['bedrooms']} bed")
    if f.get("bathrooms"):
        bits.append(f"{f['bathrooms']} bath")
    if bits:
        out.append(" · ".join(bits))
    if ls:
        # ⚠ Never say "held X years" — we do not know the current owner bought it,
        # and telling someone their own history wrongly is unrecoverable.
        d = str(ls.get("date"))[:10]
        try:
            human = datetime.fromisoformat(d).strftime("%B %Y")
        except Exception:
            human = d[:7]
        out += ["", f"**Last recorded sale: {money(ls['price'])} in {human}.** "
                    f"No later market sale is recorded."]
    else:
        out += ["", skip("§0 last-sale fact", "no priced sale in property_timeline")]
    out += ["",
            "**You may be trying to answer three questions privately.**", "",
            "Is the number attached to this home real? Is this the wrong time to move? "
            "And if you sold, where would you go next?", "",
            "This page starts with the first: what the sales around this home actually "
            "support. There is nothing to fill in and no account to create — the whole "
            "page is here.", "",
            "*↓ So what is it worth?*"]
    return "\n".join(out)


def s1_range(b):
    v = b.get("valuation") or {}
    lo, hi = v.get("low"), v.get("high")
    out = ["## What the sales around it say", ""]
    if not (lo and hi):
        out += [
            "We can't put a range on this home yet.", "",
            skip("§1 range", "no valuation_data on the subject — on-demand build not run"),
            "",
            "*The flow doc's fallback applies here: state precisely which figure is missing "
            "and why. Saying why a number is absent is worth more than the number.*",
        ]
        return "\n".join(out)
    out += [f"**{money_m(lo)} – {money_m(hi)}**", ""]
    out.append(f"The evidence centres around **{anchor(lo, hi, v.get('point'))}** — rounded "
               f"deliberately, because the width is the honest part.")
    n = v.get("n_comps")
    shown = len(globals().get("_PERSISTED") or [])
    if n and shown:
        out.append(f"\n{n} sales were close enough to influence the range. The {shown} "
                   f"strongest comparisons are shown below.")
    elif n:
        out.append(f"\n{n} sales were close enough to influence the range.")
    out += [""]
    # The engine already writes the honest-limits paragraph for exterior-only
    # subjects (`confidence_reason`). It is better than anything written here and
    # it is generated per property — use it rather than re-authoring it.
    if v.get("confidence_reason"):
        out += ["", f"> {v['confidence_reason']}"]
    out += ["", "*↓ How did you get to that?*"]
    return "\n".join(out)


def s2_working(b, adjusted):
    out = ["## The sales behind that range, and what we changed about each one", ""]
    cred = b.get("credibility") or {}
    # A funnel must NARROW. The old line read
    # "2,999 sales reviewed → 7,066 homes compared" — more homes than sales, so it
    # read as scale rather than selection. The persuasive act is REJECTION.
    v = b.get("valuation") or {}
    steps = [x for x in (
        (f"{cred['sales_reviewed']:,} recent sales searched" if cred.get("sales_reviewed") else None),
        (f"{v['n_comps']} relevant sales retained" if v.get("n_comps") else None),
        (f"{len(adjusted)} strongest comparisons shown" if adjusted else None),
    ) if x]
    if steps:
        out += ["> " + "  →  ".join(steps), ""]
        if cred.get("characteristics"):
            out += [f"> *{cred['characteristics']} property characteristics considered "
                    f"for each.*", ""]

    if adjusted:
        out.append("| Comparable | Sold | Adjusted position |")
        out.append("|---|---|---|")
        for p in sorted(adjusted, key=lambda x: x["adj"])[:3]:
            when = f" · {p['when']}" if p.get("when") else ""
            out.append(f"| {p['address']}{when} | {money_m(p['raw'])} | "
                       f"**about {money_m(p['adj'])}** |")
        if len(adjusted) > 3:
            out.append("")
            out.append(f"▸ **REVEAL —** *See all {len(adjusted)} comparisons and every "
                       f"adjustment* (the full per-feature dollar working)")
        out.append("")
    else:
        out.append(skip("§2 adjusted comparables",
                        "no adjusted comp set — run with --backtest (sold homes) "
                        "or precompute for an unsold subject"))

    oc = b.get("obvious_comp")
    if oc and oc.get("price"):
        out += ["", "### That sale up the road is not this home's answer", "",
                f"**{oc['address']} — sold {money(oc['price'])}"
                + (f", {oc.get('distance_m')}m away.**" if oc.get("distance_m") else ".**"),
                "", "Looks like the same home. But against yours:"]
        for d in (oc.get("deltas") or []):
            out.append(f"- {d}")
        out += ["", "It is still evidence — it sits in the comparison set above. But once "
                    "those differences are accounted for, the headline price is not the "
                    "number that transfers to this home."]
    else:
        out.append(skip("§2 obvious comparable", "no priced nearby sale found"))

    sc = b.get("scarcity") or {}
    pr = b.get("poi_rarity") or {}
    # ⚠ Do not assert rarity that the numbers don't support. On 28 Wedgebill the
    # anchor stack collapsed to "a pool" (bedrooms and bathrooms unknown), giving
    # "101 of 188 match" — a majority — under copy claiming the combination is
    # uncommon. Per SlotResolver's rule: leave it out rather than half-fill it.
    n_match, n_tot = sc.get("active_matching"), sc.get("active_total")
    anchors = [x for x in str(sc.get("query") or "").split("·") if x.strip()]
    share = (n_match / n_tot) if (n_match and n_tot) else None
    if n_match is not None and (share is None or share > 0.25 or len(anchors) < 2):
        # n_tot / share can be None when compute_intel returns a partial result —
        # never format a None into the reason string.
        detail = (f"{n_match}/{n_tot} match on {len(anchors)} anchor(s)"
                  + (f" ({share:.0%} of the market)" if share is not None else ""))
        out.append(skip("§2 scarcity",
                        f"claim not supported — {detail}. Rarity copy would be false here"))
    elif n_match is not None:
        out += ["", "### What makes this home less common among today's listings", "",
                f"{sc.get('active_matching')} of the {sc.get('active_total')} homes on the "
                f"market right now match this one on {_humanise_query(sc.get('query'))}."]
        feats = (pr.get("features") or [])
        best = min(feats, key=lambda x: x.get("matching", 9e9)) if feats else None
        if best and pr.get("physical_matching"):
            shorts = [f.get("short") for f in feats if f.get("short")]
            phrase = (", ".join(shorts[:-1]) + " and " + shorts[-1]) if len(shorts) > 1 else (shorts[0] if shorts else "")
            verb = "is" if best["matching"] == 1 else "are"
            out.append(f"\nOf the {pr['physical_matching']} homes nearby that share your core "
                       f"combination, only **{best['matching']}** {verb} also this close to "
                       f"{phrase} — all at once.")
        out += ["", "**What this means:** that does not set a price by itself. It affects "
                    "how many close substitutes a buyer can choose from — and part of the "
                    "range's width comes from how few recent sales share the combination."]
    else:
        out.append(skip("§2 scarcity", "no scarcity result from compute_intel"))

    vd = b.get("value_drivers") or {}
    carries = vd.get("carries_price") or []
    levers = b.get("negotiation_levers") or []
    if carries or levers:
        out += ["", "### What carries the price", ""]
        if carries:
            out.append("**What strengthens your position:** " + ", ".join(f"↑ {c}" for c in carries))
        if levers:
            out.append("\n**Where a buyer may focus:** " + ", ".join(f"↓ {l}" for l in levers))
        # "Knowing both" is only true when both sides rendered.
        out.append("\n**Both matter: they are why nearby sales cannot be read across "
                   "without adjustment.**" if (carries and levers)
                   else "\n**That is one reason nearby sales cannot be read across without "
                        "adjustment.**")
    out += ["", "*↓ So how wrong could you be?*"]
    return "\n".join(out)


def s3_method():
    return """## What this is, and what it isn't

This is an estimate built from comparable sales. It is not a formal valuation, and it isn't an
appraisal — a valuer inspects the property and carries professional liability for the figure.
Nobody has been inside this home.

**What we do:** take sales of homes near this one, adjust each for the ways it differs, weight
them by how good a comparison they are, and publish the spread.

**What we won't do:** use anything that happened after the fact. Every sale behind this figure
closed *before* today. That is the easiest way for a number like this to flatter itself, and
it's worth knowing we've ruled it out.

Across the homes we've tested, adjusting narrows the spread by about **40%**, and narrows it at
all **nine times out of ten**.

**How wrong we are:** [ERROR RATE — pin one figure with its sample and date. 11.1% and 11.6%
are both in circulation.]

*↓ Then why do the other numbers disagree?*"""


def s4_dispersion():
    return """## Why the other estimates say something different

You just watched a sale become a different number once we priced the differences. That is what
choosing a different set of sales does to the answer.

A valuation built from only three selected sales is highly sensitive to which three are chosen —
and three comparable sales is the statutory Statement of Information standard in Victoria and
the incoming NSW regime, so it is not a straw man.

We tested what that produces. We took 512 homes that have since sold, found every set of three
comparable sales that could reasonably have been chosen, and worked out what each set said.

**The median gap between the highest and lowest defensible result was $469,000.**

**What this means:** that does not make any one estimate dishonest. It means three sales are
often too small a sample to show which comparison deserves the most weight.

▸ **REVEAL —** *See what the test found*
  (a close answer was present in the available evidence on 73.6% of those homes — identifiable
  only with hindsight; the worst available choice was more than 20% out on 73.4%)

*↓ What has it actually done for me?*"""


def s5_gain(ls, ms, suburb_display):
    if not ls:
        return skip("§5 gain trajectory", "no prior sale on record")
    hist = ms.get("median_price_history") or []
    out = [f"## Bought {str(ls.get('date'))[:7]} for {money(ls['price'])}", ""]
    y = held_years(ls.get("date"))
    if not hist:
        out.append(skip("§5 trajectory", "no median_price_history for this suburb"))
        return "\n".join(out)

    first, last = hist[0], hist[-1]
    span_start, span_end = first.get("period"), last.get("period")
    # Can the index actually reach back to the purchase? Usually not.
    try:
        buy_year = int(str(ls["date"])[:4])
    except Exception:
        buy_year = None
    idx_start_year = int(str(span_start).split()[-1]) if span_start else None

    if buy_year and idx_start_year and buy_year < idx_start_year:
        # ⚠ Do NOT index a purchase the series cannot reach. Say so — per the
        # suppression rule, why a figure is missing is worth more than the figure.
        out += [
            f"That was **{y} years ago**. We can't trace a line from it to today: our quarterly "
            f"median series for {suburb_display} starts at {span_start}, and everything before "
            f"that is outside what we can measure.",
            "",
            f"What we can say is what the suburb has done over the window we do hold — the "
            f"{suburb_display} median moved from {money(first.get('median_price'))} "
            f"({span_start}) to {money(last.get('median_price'))} ({span_end}).",
        ]
        if ms.get("ten_year_growth_pct") and ms.get("ten_year_start_price"):
            out += ["", f"We do hold a broader ten-year suburb series, which moved from "
                        f"{money_m(ms['ten_year_start_price'])} to "
                        f"{money_m(ms.get('ten_year_end_price'))} — about "
                        f"{round(ms['ten_year_growth_pct'])}%. Two different series, stated "
                        f"separately rather than spliced."]
        out += ["", "**What this means:** the gap between what you paid and what the sales say "
                    "today is real, but it isn't one we can draw as a single line — and a line "
                    "we can't evidence is worth less than saying so."]
    else:
        out += [f"Since then the {suburb_display} median has moved from "
                f"{money(first.get('median_price'))} ({span_start}) to "
                f"{money(last.get('median_price'))} ({span_end})."]
    out += ["", "*↓ The bank said something lower — why?*"]
    return "\n".join(out)


def s6_lender(b):
    v = b.get("valuation") or {}
    if not v.get("high"):
        return skip("§6 lender", "no range, so no upper bound to state")
    return """▸ **REVEAL —** *My bank gave me a lower number — why?*

A lender is assessing the property as security for a loan, not preparing a selling strategy.
The instructions, assumptions and risk tolerance are different, and that commonly produces a
more conservative result than an open-market estimate. It is not a comment on the home.

*↓ And what's happening around it now?*"""


def s7_moving(b):
    out = ["## What's changed around this home", ""]
    comp = b.get("competition") or {}
    if comp.get("n_compete") is not None:
        # ⚠ ONE count, from ONE source. An earlier build printed compute_intel's
        # n_compete (4), then len(closest_active) (6), then listed 4 — three
        # numbers for the same thing. A visible arithmetic contradiction voids
        # every careful figure above it.
        pass
    else:
        out.append(skip("§7 competitors", "no competition result"))
    buyer = b.get("buyer") or {}
    if buyer.get("portrait"):
        out += ["", "### Who that combination suits", "", f"**{buyer['portrait']}**", "",
                "**Right now it's your home. To them, it's the one they've been waiting for.**"]
    rep = globals().get("_REPORT") or {}
    comps = rep.get("comparables") or {}
    active = comps.get("closest_active") or []
    events = rep.get("comparable_events") or []
    if active:
        # This home is NOT on the market — it cannot be "competing".
        out += ["", f"**{len(active)} homes a buyer could compare with this one if it came to "
                    f"market today**"]
        for a in active:
            price = a.get("price")
            # ⚠ Source price strings are free text and some are malformed
            # ("Offers over $1.449"). Show only what parses cleanly.
            if price and re.search(r"\$\s*\d+\.\d{1,3}\s*$", str(price).strip()):
                price = None
            bits = [x for x in (a.get("address"), price,
                                f"{a.get('bedrooms')} bed" if a.get("bedrooms") else None) if x]
            line = " · ".join(str(x) for x in bits)
            diff = a.get("differenceVsSubject") or a.get("difference_vs_subject")
            out.append(f"- {line}" + (f" — *{diff}*" if diff else ""))
        # The aperture label is an honesty device: it says how far we had to look.
        if comps.get("aperture_label"):
            out.append(f"\n*Comparison set: {comps['aperture_label']}.*")
        if (globals().get("_MS") or {}).get("active_listings") is not None:
            ms_ = globals()["_MS"]
            out.append(f"*{ms_['active_listings']} houses are on the market in "
                       f"{b.get('suburb_display')}; {(b.get('scarcity') or {}).get('active_total')} "
                       f"across the wider comparison catchment.*")
    if events:
        out += ["", "### What's moved recently", ""]
        for e in events[:5]:
            out.append(f"- **{str(e.get('date'))[:10]}** — {e.get('headline') or e.get('kind')}")
    if not active and not events:
        out.append(skip("§7 change log", "no competitor set or events for this address"))
    ms = globals().get("_MS") or {}
    if ms.get("dom_median") and ms.get("dom_yoy_prev"):
        now, prev = ms["dom_median"], ms["dom_yoy_prev"]
        now_i = int(round(float(now))); prev_i = int(round(float(prev)))
        faster = now < prev
        out += ["", "### Two true things that point in different directions", "",
                f"Homes here are selling **{'faster' if faster else 'more slowly'}** than a year "
                f"ago — a median of **{now_i} days**, against **{prev_i}** twelve months "
                f"earlier"
                + "."]
        if ms.get("active_listings") is not None and ms.get("active_listings_mom_pct") is not None:
            out.append(f"\nBut there is less to choose from: **{ms['active_listings']} homes** are "
                       f"on the market, {abs(ms['active_listings_mom_pct'])}% "
                       f"{'fewer' if ms['active_listings_mom_pct'] < 0 else 'more'} than a month ago.")
        out += ["", "Both readings are true and they support opposite conclusions, which is why "
                    "a single market headline can't settle anything about this home."]
        if ms.get("current_median_price") and ms.get("yoy_growth_pct") is not None:
            out += ["", f"| 12-month median | {money(ms['current_median_price'])} |",
                    "|---|---|",
                    f"| Year on year | {ms['yoy_growth_pct']:+}% |",
                    f"| Median days on market | {now_i} |",
                    f"| Same quarter a year earlier | {prev_i} |"]
        if ms.get("qoq_suppressed_reason"):
            # ⚠ The stored value mixes the REASON with an editorial INSTRUCTION to
            # us ("Do not state a QoQ change"). Rendering it whole leaks internal
            # direction onto a consumer page. Keep the reason, drop the order.
            raw = str(ms["qoq_suppressed_reason"])
            reason = re.split(r"(?i)\.\s*(?:do not|don't|never)\b", raw)[0].rstrip(". ")
            import re as _re
            ns = _re.findall(r"n=(\d+)", raw)
            human = (f"We're not showing a quarter-on-quarter price change. Only {ns[0]} and "
                     f"{ns[1]} sales sit behind the two quarters — too few to separate a real "
                     f"movement from ordinary variation." if len(ns) >= 2
                     else f"{reason}. We're not showing a quarter-on-quarter figure.")
            out += ["", f"*{human}*"]
        basis = ms.get("current_median_price_basis")
        out += ["", f"`Source: {basis or 'Fields analysis of sold records'} · "
                    f"Last reviewed: {str(ms.get('data_date'))[:10]}`"]
    else:
        out.append(skip("§7 market indicators", "no market_pulse snapshot for this suburb"))
    out += ["", "*↓ Is there anything under it I should know?*"]
    return "\n".join(out)


def s8_exposure(b):
    gs = b.get("green_space") or {}
    if (b.get("suburb_key") or "") != "burleigh_waters":
        return skip("§8 exposure",
                    "flood context exists for Burleigh Waters only "
                    "(config/flood_context_burleigh_waters.md)")
    return "## Flood and overlays\n\n[flood context for this address]"


def s9_control(b):
    gaps = b.get("gaps") or []
    ask = ""
    if any("bathroom" in g for g in gaps):
        ask = ("\n\n### One thing we could not verify: the bathroom count\n\n"
               "Is it 2, 3, or something else?\n\n"
               "*[ 2 ] [ 3 ] [ 4 ] [ other ]* → *Updated. Rebuilding the comparison now…*\n\n"
               "A specific gap is a better invitation than a blank box — and it is a real one: "
               "the range above was built without a bathroom adjustment.")
    return """## This is your home's page. You can change it.

Everything here was built from public records and sales data. Some of it will be wrong — a
renovation we don't know about, a room count out of date, a sale that shouldn't have been used.

**[ See everything we hold on this home ]**

Tell us what's wrong, and we'll fix it and rebuild the figure in front of you.

**No agent is paying to appear on this page, and your interest in your own home is not sold to
anyone.** Fields is the agency that built it — there is no third party being handed your
address.

⚠ *DECISION 2026-08-06 (Will): the page carries NO promise about contact, in either direction.
"Nobody calls unless you ask" is removed from §0 and §9. Rationale: the page is a lead surface
and the business depends on it; a promise the model cannot keep is worse than no promise, and
`offmarket-intent-alert.mjs` already fires on reaching the end of a deck. Outreach is physical
mail to the property address — not cold calling.*

⚠ *What replaces it is stronger and stays true: REA books a homeowner's engagement with its own
estimate as a "seller lead delivered to our customers", with Pro-tier agents receiving 36% more
of them. The differentiator was never "we won't contact you" — it is **"we don't sell you to
whoever pays most."** That survives the business model intact, and it is defensible from REA's
own filings.*""" + ask


# ── main ────────────────────────────────────────────────────────────────────

def get_adjusted(slug, suburb):
    """Per-comparable adjusted prices via the backtest path (sold homes only)."""
    import valuation_backtest as vb
    from precompute_valuations import resolve_land_size, resolve_floor_area  # noqa: F401
    client = get_mongo_client()
    db = client["Gold_Coast"]
    stem = slug.split("-")[0] + " " + slug.split("-")[1] if "-" in slug else slug
    subject = db[suburb].find_one({"listing_status": "sold",
                                   "address": {"$regex": stem, "$options": "i"}})
    if not subject:
        return None
    subject["_collection"] = suburb
    sold_by_suburb = vb._load_sold_comparables(client)
    keys = list(sold_by_suburb.keys())
    coords = vb._preload_gc_coordinates(client, keys)
    timelines = vb._preload_gc_timelines(client, keys)
    mc = vb._build_suburb_median_cache(sold_by_suburb)
    sc = vb._build_street_premium_cache(sold_by_suburb, mc)
    res = vb.backtest_single_property(db, subject, sold_by_suburb.get(suburb, []),
                                      sold_by_suburb, coords, timelines,
                                      median_cache=mc, street_premium_cache=sc)
    if not res:
        return None
    out = []
    for p in res["included_points"]:
        src = p.get("_source_doc") or {}
        out.append({"address": src.get("address", "?"),
                    "raw": p["price"],
                    "adj": p["adjustment_result"]["adjusted_price"],
                    "pct": p["adjustment_result"].get("total_adjustment_pct")})
    return out


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--slug", required=True)
    ap.add_argument("--suburb", default=None)
    ap.add_argument("--backtest", action="store_true",
                    help="sold homes only — adds per-comparable adjusted prices")
    ap.add_argument("--out", default=None)
    ap.add_argument("--audit", action="store_true",
                    help="append the dev coverage audit — NEVER for a homeowner-facing render")
    args = ap.parse_args()

    b = fact_bundle.build(args.slug, args.suburb)
    # Prefer the engine's own persisted adjusted comparables (added to
    # valuation_data 2026-08-06) over the backtest path — it works for unsold
    # subjects, which is the actual off-market surface.
    if not args.backtest:
        _gc = get_mongo_client()["Gold_Coast"]
        _d = _gc[b["suburb_key"]].find_one({"address": b["address"]},
                                           {"valuation_data.adjusted_comparables": 1})
        _ac = ((_d or {}).get("valuation_data") or {}).get("adjusted_comparables") or []
        if _ac:
            globals()["_PERSISTED"] = [
                {"address": c.get("address"), "raw": c.get("sale_price"),
                 "adj": c.get("adjusted_price"), "pct": c.get("total_adjustment_pct"),
                 "when": (str(c.get("sale_date"))[:7] if c.get("sale_date") else None)}
                for c in _ac if c.get("adjusted_price")]
    gc = get_mongo_client()["Gold_Coast"]
    ls = last_sale(gc, b["suburb_key"], b["address"])
    adjusted = (get_adjusted(args.slug, b["suburb_key"]) if args.backtest
                else globals().get("_PERSISTED"))
    globals()["_MS"] = market_snapshot(b["suburb_key"])
    globals()["_REPORT"] = (get_mongo_client()["system_monitor"]["property_reports"]
                            .find_one({"slug": args.slug}) or {})
    adjusted = (get_adjusted(args.slug, b["suburb_key"]) if args.backtest
                else globals().get("_PERSISTED"))
    globals()["_MS"] = market_snapshot(b["suburb_key"])
    globals()["_REPORT"] = (get_mongo_client()["system_monitor"]["property_reports"]
                            .find_one({"slug": args.slug}) or {})

    parts = [s0_arrival(b, ls), s1_range(b), s2_working(b, adjusted), s3_method(),
             s4_dispersion(), s5_gain(ls, globals()["_MS"], b["suburb_display"]),
             s6_lender(b), s7_moving(b),
             s8_exposure(b), s9_control(b)]
    md = "\n\n---\n\n".join(parts)

    # ⚠ DEV INSTRUMENTATION ONLY. "Coverage audit" and "fact_bundle gaps" must
    # never render to a homeowner. Gated behind --audit.
    if args.audit:
        md += "\n\n---\n\n## Coverage audit\n\n"
        if MISSING:
            md += f"**{len(MISSING)} block(s) did not render:**\n\n"
            for sec, why in MISSING:
                md += f"- **{sec}** — {why}\n"
        else:
            md += "Everything rendered.\n"
        if b.get("gaps"):
            md += "\n**fact_bundle gaps:** " + "; ".join(b["gaps"]) + "\n"

    out = args.out or os.path.join(HERE, f"report_{args.slug}.md")
    with open(out, "w") as fh:
        fh.write(md)
    print(md)
    print(f"\n→ {out}", file=sys.stderr)


if __name__ == "__main__":
    main()
