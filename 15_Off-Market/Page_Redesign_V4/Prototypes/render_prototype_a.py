#!/usr/bin/env python3
"""
render_prototype_a.py — Prototype A of the V4 private property report.

Design spec: Page_Redesign_V4/Design/01_UI_BRIEF.md (Will, 2026-08-06).
  "Answer first. Prove it gradually. Surprise them periodically. Ask almost nothing."

A single vertically scrolling page — NOT a deck. Warm editorial register, not the
V3 dark cinematic treatment. Mobile first.

Every figure on the page is read from the live bundle + Gold_Coast document. There
is no placeholder copy: if a fact is missing the block does not render, per the
SlotResolver rule ("we never half-fill a field with garbage").

Output goes to 15_Off-Market/Concepts/V4_Private_Report/ which nginx serves with
no build step:
    https://vm.fieldsestate.com.au/concepts/off-market/V4_Private_Report/<slug>.html

    python3 render_prototype_a.py --slug 28-wedgebill-parade-burleigh-waters
    python3 render_prototype_a.py --slug X --open   # print the URL
"""
import argparse
import html
import json
import os
import re
import sys
from pathlib import Path

V2 = Path("/home/fields/Fields_Orchestrator/15_Off-Market/Page_Redesign_V2")
OUT = Path("/home/fields/Fields_Orchestrator/15_Off-Market/Concepts/V4_Private_Report")
ORCH_ROOT = "/home/fields/Fields_Orchestrator"
sys.path.insert(0, str(V2))
sys.path.insert(0, "/home/fields/Fields_Orchestrator")

from dotenv import load_dotenv                      # noqa: E402
load_dotenv("/home/fields/Fields_Orchestrator/.env")
import assemble as A                                # noqa: E402
from src.mongo_client_factory import get_mongo_client  # noqa: E402

# Measured 2026-08-08 under the CURRENT method. Canonical source:
# 16_Valuation/accuracy/2026-08-08-figures.md — do not edit these by hand without
# re-running the backtest there.
#
#   python3 scripts/valuation_backtest.py --price-filter none --property-type House \
#     --min-price 1000000 --max-price 2000000 --suburb <suburb> --blind-subject
#
# --blind-subject is MANDATORY here: this page is the off-market product, and an
# off-market home has no marketing photos, so a sighted backtest would quote an
# accuracy we cannot deliver for this reader.
#
# Per suburb, never blended — the spread between suburbs is wider than the gain
# from scoping, so a blend misdescribes two of three markets. No fallback: an
# unmeasured suburb renders no figure.
#
# `band` is the PUBLISHED half-width and is per suburb too. 80% coverage is a
# promise, so each suburb gets the width its own measurement earns — a pooled
# 12.2% contained only 77% in Burleigh Waters.
ACCURACY = {
    "robina":          {"n": 251, "mae": 8.2, "median": 6.6, "within10": 67, "contain": 79, "band": 12.2},
    "burleigh_waters": {"n": 146, "mae": 8.6, "median": 7.7, "within10": 68, "contain": 77, "band": 14.0},
    "varsity_lakes":   {"n": 184, "mae": 7.3, "median": 5.5, "within10": 72, "contain": 82, "band": 11.2},
}

# ── VERSIONS ───────────────────────────────────────────────────────────────
# Copy that differs between takes lives here, so an earlier wording can be
# re-rendered rather than reconstructed from memory or git. Anything NOT in this
# dict is shared by every version — only put a key here when it actually varies,
# or the versions drift apart in ways nobody intended.
#
#   v1  2026-08-06  the questions as Fields posed them, third person
#   v2  2026-08-07  the owner's OWN words, first person — and a heading block
#                   that names the two-portals problem before the range appears
VERSIONS = {
    "v1": {
        "questions_intro": "You may be trying to answer three questions privately.",
        "questions": [
            "Is the number attached to this home real?",
            "Is this the wrong time to move?",
            "And if you sold, where would you go next?",
        ],
        "promise": ("This page starts with the first: what the sales around this home actually "
                    "support. Nothing here starts a selling process, and nobody calls unless "
                    "you ask."),
        "preamble": None,
    },
    "v2": {
        "questions_intro": "You may be turning over something like this.",
        # First person, and phrased as the owner would say it rather than as we
        # would ask it. The first is a worry, not a question — which is closer to
        # why someone actually searches their own address.
        "questions": [
            "I'm worried online valuations are wrong.",
            "Is now the right time to be selling, or should I wait?",
            "If I sold, where would I go and what could I buy there?",
        ],
        # Removed 2026-08-07 (Will). The claim still stands and still appears where
        # it is earned — the correction section ("not treated as a request for
        # contact") and the closing CTA ("no contact details required"). Stating
        # it up front, before anything has been offered, answered a question the
        # reader had not asked yet.
        "promise": None,
        "preamble": {
            "heading": "Two property sites. Two different values for the same home. "
                       "Which one is right?",
            "paras": [
                "The uncomfortable answer is that you can't tell from the number alone.",
                "What matters is which sales were used, why they were chosen, and what was "
                "changed to make them genuinely comparable to your home.",
                "So rather than give you a third unexplained number, we'll show you the sales "
                "behind ours.",
            ],
        },
    },
}
VERSIONS["v3"] = {
    # v3 2026-08-07 — the portal disagreement becomes the INCITING INCIDENT, not
    # a thing the page mentions. Will: "the opening shouldn't merely mention the
    # portal disagreement; it should make that disagreement the inciting incident
    # of the whole experience."
    #
    # The other two questions (timing, where next) are deliberately NOT raised
    # up front any more. Raising three questions at once dilutes the one the
    # visitor actually arrived with, and the page cannot answer the other two
    # until it has earned the right to. They are introduced later, where they
    # are about to be answered.
    "questions_intro": None,
    "questions": [],
    "promise": None,
    "preamble": {
        "opener": "You've probably already seen two different values for this home.",
        "heading": "So which one should you believe?",
        "paras": [
            "The problem is that you can't tell from the number alone.",
            "What matters is which sales were used, why they were chosen, and what was changed "
            "to make them genuinely comparable with this home.",
            "So rather than give you a third unexplained number, we'll show you what the "
            "evidence actually supports.",
        ],
    },
    # Raised later, once the value question has been answered.
    "other_questions_intro": "Two other questions usually follow.",
    "other_questions": [
        "Is now the right time to be selling, or should I wait?",
        "If I sold, where would I go and what could I buy there?",
    ],
}
LATEST = "v3"

# ── Seasonality — the canonical source of truth ────────────────────────────
# scripts/seasonality_analysis.py -> 08_Seller-Book/Market_Data/seasonality/
# seasonality_monthly_summary.csv. 2010-2025 EXCLUDING 2019-2020 (COVID),
# 18,978 sales. CATCHMENT level: per-suburb months are too thin to publish.
#
# ⚠ Do not re-derive these. The `december-listing-paradox` article shipped
# overstated (Dec +6.05% against the real +2.81% — that inflated figure is the
# `article_pct` column in the CSV, kept only to document the correction) and had
# to be republished.
#
# (month, premium %, sales behind that month)
SEASONALITY = [("Jan", -1.37, 1331), ("Feb", -1.36, 1687), ("Mar", 0.85, 1584),
               ("Apr", -0.30, 1470), ("May", -0.47, 1614), ("Jun", 1.60, 1403),
               ("Jul", -0.04, 1493), ("Aug", 2.30, 1387), ("Sep", 2.50, 1543),
               ("Oct", 2.61, 1497), ("Nov", 3.29, 1512), ("Dec", 2.81, 1151)]
SEASONALITY_N = 18978
SEASONALITY_SCOPE = "the southern Gold Coast"
SEASONALITY_WINDOW = "2010\u20132025, excl. COVID 2019\u20132020"

PORTED_NOTE = ("This section is a placeholder. It will be the existing "
               "<code>{comp}</code> component, which already renders "
               "{what}. Not being designed here.")


def ported(comp, what):
    return (f'<div class="ported"><span class="ptag">Ported component</span>'
            f'<span>Placeholder \u2014 ships as <code>{comp}</code>, which already renders '
            f'{what}. Not being designed in this prototype.</span></div>')


E = html.escape


def money(v):
    """Full figures, per the editorial rule ($1,250,000 not $1.25m). The brief's
    mock used '$1.75m'; we render '$1.75 million' — readable, and it does not
    breach the house number-format rule."""
    if v is None:
        return None
    v = float(v)
    if v >= 1_000_000:
        return "$" + f"{v/1_000_000:.2f}".rstrip("0").rstrip(".") + " million"
    return f"${int(round(v)):,}"


def hero_image(doc, suburb_key, slug, boundary_colour="sun"):
    """The hero: a satellite aerial with the TRUE cadastral boundary drawn on it.

    ⚠ Not a listing photo. `domain_hero_image_url` 404s in a browser once a home
    comes off the market — Domain expires them on delisting — and curl will not
    tell you (memory image_url_verification_orb: curl is not a browser). A broken
    <img> is worse than no image.

    The boundary is not decoration. Will: "a reader looking at a block of roofs
    cannot tell which one is theirs." Geometry is the real parcel, fetched by
    LOT/PLAN from Queensland's public cadastre and cached on the document, so the
    outline follows the actual fence lines rather than a guessed rectangle.

    Colour default is `sun` (#fec66f) rather than the primary copper: measured on
    28 Wedgebill, copper and gold sit in the same hue family as the terracotta
    roofs that dominate these suburbs and start to disappear into the roofline.
    Legibility beat brand primacy.
    """
    import os
    sys.path.insert(0, os.path.join(ORCH_ROOT, "scripts"))
    try:
        import render_property_aerial as ra
    except Exception:
        return None
    dest = OUT / f"{slug}-aerial-{boundary_colour}.png"
    if dest.exists():
        return dest.name
    try:
        gc = get_mongo_client()["Gold_Coast"]
        out, _note = ra.render(gc, suburb_key, doc, boundary_colour, str(OUT),
                               width=640, height=400, scale=2)
        return out.name if out else None
    except Exception:
        return None


def scarcity_map(doc, bundle, slug):
    """The homes that share this combination, plotted.

    The first version plotted AMENITIES, because active listings appeared to
    carry no coordinates — 0 of 58 in Burleigh Waters. That was a bad query, not
    a data gap: the coordinates live in `LATITUDE`/`LONGITUDE` (uppercase, from
    the cadastral dataset), and lowercase `latitude` does not exist on these
    documents. All 21 matching listings resolve.

    The matching set comes from `scarcity_features.find_active_matches`, which
    mirrors the counter's query exactly, so the dots can never disagree with the
    number printed beside them.

    Google auto-fits the viewport to the markers when center and zoom are
    omitted — which is right here, because the honest picture is how far a buyer
    must travel to find a substitute, and that is a different distance for every
    home.
    """
    import os
    import urllib.request
    sys.path.insert(0, os.path.join(ORCH_ROOT, "scripts"))
    key = os.getenv("GOOGLE_MAPS_STATIC_API_KEY")
    if not key:
        return None, None
    try:
        from property_reports.scarcity_features import (
            find_active_matches, identify_features, compute_cohort_medians,
            DEFAULT_CATCHMENT, _features_from_subject, resolve_listing_coords)
        import precompute_valuations as pv
        cl = get_mongo_client()
        gc = cl["Gold_Coast"]
        lat, lon = pv._resolve_coordinates(
            doc, pv._preload_gc_coordinates(cl, [bundle["suburb_key"]]), bundle["suburb_key"])
        if lat is None or lon is None:
            lat, lon = resolve_listing_coords(doc)
        fb = _features_from_subject(doc)
        if not fb or lat is None:
            return None, None
        anchors, _ = identify_features(fb, compute_cohort_medians(gc, DEFAULT_CATCHMENT))
        matches = find_active_matches(gc, anchors, fb)
    except Exception:
        return None, None
    if not matches:
        return None, None

    pins = [f"markers=color:0xfec66f%7Clabel:H%7C{lat},{lon}"]
    # Grouped into one marker declaration so the URL stays short — Static Maps
    # rejects requests over ~8k characters.
    others = "%7C".join(f"{m['lat']},{m['lon']}" for m in matches[:40])
    pins.append(f"markers=color:0x4A443E%7Csize:small%7C{others}")

    name = f"{slug}-matches.png"
    dest = OUT / name
    if not dest.exists():
        url = ("https://maps.googleapis.com/maps/api/staticmap?"
               "size=640x440&scale=2&maptype=roadmap&" + "&".join(pins) + f"&key={key}")
        try:
            with urllib.request.urlopen(url, timeout=30) as r:
                data = r.read()
            if len(data) < 5000:
                return None, None
            dest.write_bytes(data)
        except Exception:
            return None, None
    return name, len(matches)


# Event kinds that may appear in the homeowner-facing timeline. This is an
# ALLOWLIST, not a denylist: a new event kind is hidden until someone decides it
# is safe, rather than appearing the moment it is invented.
#
# ⚠ Why (2026-08-06). `property_reports.activity` is shared with the appraisal
# flow and carries internal process events — `data_resolved`, `stub_created`,
# `valuation`, `review_request`. One of them rendered on the Robina page as
# "We pulled your property's data ... A property consultant will refine these
# into the final valuation range." **180 activity entries across the collection
# contain that kind of contact promise.** On the appraisal product that promise
# is true. On THIS page it directly contradicts the one thing the page promises
# — "nobody calls unless you ask" — and it was one render from shipping.
# `market_state` is excluded separately: it carries internal jargon ("FCI 102").
TIMELINE_KINDS = {"new_listing", "comp_price_change"}

# Second guard, independent of kind. Belt and braces: if a headline or detail
# implies someone will make contact, it does not belong on this page whatever
# it is labelled.
_CONTACT_PROMISE = ("consultant", "will refine", "will be in touch", "we'll call",
                    "will call", "our team will", "get in touch", "reach out")


def timeline_safe(a):
    if (a.get("kind") or a.get("type")) not in TIMELINE_KINDS:
        return False
    blob = f"{a.get('headline','')} {a.get('detail','')} {a.get('body','')}".lower()
    return not any(t in blob for t in _CONTACT_PROMISE)


def full_date(d):
    from datetime import datetime
    try:
        return datetime.fromisoformat(str(d)[:10]).strftime("%-d %B %Y")
    except Exception:
        return str(d)[:10]


FIELDS_SMS_NUMBER = "+61416529481"


def report_qr(short_address, slug):
    """QR encoding the SAME user-initiated SMS deep link the live deck uses.

    `sms:+61416529481?&body=…` — matching
    `DiscoveryDeck.tsx`/`OffMarketDeck.tsx` exactly rather than inventing a
    second mechanism. Nothing is typed by the visitor and no contact field is
    collected: they send a message, which opens a two-way channel because THEY
    started it. That is what keeps "nobody calls unless you ask" true.

    Rendered to an inline SVG data URI — no network request, no external QR
    service seeing our addresses, and it stays crisp at any size.
    """
    import io
    import base64
    import urllib.parse
    try:
        import qrcode
        import qrcode.image.svg
    except Exception:
        return None, None
    body = f"Download report for {short_address}"
    uri = f"sms:{FIELDS_SMS_NUMBER}?&body={urllib.parse.quote(body)}"
    img = qrcode.make(uri, image_factory=qrcode.image.svg.SvgPathImage,
                      box_size=10, border=2)
    buf = io.BytesIO()
    img.save(buf)
    data = "data:image/svg+xml;base64," + base64.b64encode(buf.getvalue()).decode()
    return data, uri


def timing_answer(suburb_display, ms):
    """The three things we can actually know, and the belief reversal above them.

    ⚠ REWRITTEN 2026-08-07. The previous version ran 994 words — a third of the
    page's entire primary path — walking through Westpac, the RBA, national
    indices, Brisbane, local DOM, listing volume, rolling medians, quarterly
    caveats and fifteen years of seasonality before saying anything useful. The
    reader arrived asking a decision question and got an economics note.
    Measured, not estimated: it was the single heaviest section by a factor of
    two.
    Nothing is deleted. The forecasts and the seasonality move behind
    disclosures, where a sceptical reader can still audit every claim.

    The reframe (Will): you do not need to predict the next six months
    correctly to make a good decision. What you can know is how fast homes like
    yours are selling, how much choice buyers currently have, and what selling
    would let you buy next — and the third usually matters more than whether a
    national index moves two per cent.

    Editorial constraints unchanged: no advice, no prediction, no urgency, no
    "strong/holding up/resilient", direction stated per suburb and never
    characterised as good or bad.
    """
    dom, dom_prev = ms.get("dom_median"), ms.get("dom_yoy_prev")
    act, act_d = ms.get("active_listings"), ms.get("active_listings_mom_pct")

    lede = ("You don't need to predict the next six months correctly to make a good decision. "
            "Nobody can, and the people paid to try have spent this year disagreeing in public.")

    knowables = []
    if dom and dom_prev:
        slower = dom > dom_prev
        knowables.append(
            (f"How quickly homes like yours are selling",
             f"A median of {dom:.0f} days in {suburb_display} last quarter, against "
             f"{dom_prev:.0f} a year earlier \u2014 {'longer' if slower else 'less time'} than it "
             f"took then."))
    if act is not None:
        more = (act_d or 0) > 0
        detail = f"{act:.0f} homes on the market now"
        if act_d:
            detail += (f", {abs(act_d):.0f}% {'more' if more else 'fewer'} than a month ago")
        knowables.append(("How much choice buyers currently have", detail + "."))
    knowables.append(
        ("What selling would let you buy next",
         "The part almost nobody measures, and usually the one that decides whether a move works."))
    return lede, knowables


BEL = {
    "land_size": ("Land", "m²"), "floor_area": ("Floor area", "m²"),
    "bedrooms": ("Bedrooms", ""), "bathrooms": ("Bathrooms", ""),
    "car_spaces": ("Car spaces", ""), "pool": ("Pool", ""), "stories": ("Levels", ""),
    "renovation": ("Condition", ""), "beach_proximity": ("Distance to beach", ""),
    "street_premium": ("Street", ""), "micro_location": ("Position", ""),
    "time_adjustment": ("Time since sale", ""), "golf_backing": ("Golf frontage", ""),
    "water_views": ("Water outlook", ""),
}
TOR_LABEL = {
    "adjustment_quality": "How little had to be adjusted",
    "adjusted_accuracy": "How closely it agrees with the rest",
    "proximity": "How close it is",
    "recency": "How recently it sold",
    "verification": "How much we could verify",
    "data_quality": "How complete its record is",
}


_INSIGHTS_CACHE = {}


def market_insights(suburb_display):
    """The same payload `MedianPriceChart.tsx` reads: /api/market-insights.

    ⚠ Use this, do not rebuild from `market_pulse.median_price_history`. That
    field holds 8 quarters; this endpoint returns 84 quarters of quarterly
    median WITH per-quarter confidence intervals and a `reliable` flag, plus a
    59-quarter rolling 12-month series and the in-progress quarter. Building a
    second chart off the shorter field is what produced a bar chart that showed
    two years where the live page shows thirty — and it is the second time in
    one sitting I rebuilt a component that already existed (see the
    SeasonalityStrip entry).
    """
    import urllib.parse
    import urllib.request
    if suburb_display in _INSIGHTS_CACHE:
        return _INSIGHTS_CACHE[suburb_display]
    url = ("https://fieldsestate.com.au/api/market-insights?suburb="
           + urllib.parse.quote(suburb_display))
    try:
        with urllib.request.urlopen(url, timeout=40) as r:
            data = json.loads(r.read())
    except Exception:
        data = {}
    _INSIGHTS_CACHE[suburb_display] = data
    return data


def excluded_sale(vd):
    """The priciest nearby sale we did NOT use, and the stored reason why.

    Answers the question a homeowner actually asks — "but that place up the road
    sold for $X" — for the sales that did NOT make the set. `recent_sales`
    carries all 51 candidates with `included_in_valuation` and a
    `verification.issues` list, so the reason is recorded rather than inferred.

    Only returns a sale that has a RECORDED issue. Plenty of excluded sales
    simply were not among the eight strongest by weight — "it wasn't in the top
    eight" is true but not interesting, and dressing it up as a rejection would
    misrepresent what happened.
    """
    rs = [r for r in (vd.get("recent_sales") or [])
          if not r.get("included_in_valuation") and r.get("price")]
    cands = []
    for r in rs:
        v = r.get("verification") or {}
        issues = [i for i in (v.get("issues") or []) if "All checks passed" not in i]
        if issues:
            cands.append((r, issues, v.get("status")))
    if not cands:
        return None
    r, issues, status = max(cands, key=lambda c: c[0]["price"])

    # "Adjusted price +58% from cohort median" -> plain English, keeping the number.
    reasons = []
    for i in issues:
        m = re.search(r"([+-]?\d+)%\s+from cohort median", i)
        if m:
            pc = int(m.group(1))
            reasons.append(f"once the differences were priced in it still sat {abs(pc)}% "
                           f"{'above' if pc > 0 else 'below'} the middle of the comparable set")
            continue
        if "outlier" in i.lower():
            reasons.append("it sat far enough from the rest of the set to read as an outlier")
            continue
        reasons.append(i.rstrip("."))
    return {"address": str(r.get("address", "")).split(",")[0],
            "price": r["price"],
            "distance_km": r.get("distance_km"),
            "reasons": reasons[:2],
            "status": status}


def median_chart(mi):
    """Quarterly median and the rolling 12-month median, full history, scrubable.

    Palette follows THIS page, not the market-intelligence blue/green: the
    rolling median — the figure the copy tells the reader to trust — is in the
    accent, and the noisier quarterly line is muted behind it, so the colour
    carries the same message as the words.

    Interaction: a pointer guideline with the values at that quarter. `pointer*`
    events cover mouse and touch in one path. `touch-action: pan-y` on the plot
    lets a vertical swipe still scroll the page while a horizontal drag scrubs —
    capturing both axes would trap the reader inside the chart, which is the
    scroll-jacking the brief rules out.
    """
    q = [x for x in (mi.get("medianPriceHistory") or []) if x.get("medianPrice")]
    roll = [x for x in (mi.get("rollingMedianSeries") or mi.get("rolling12mMedianSeries") or [])
            if x.get("rollingMedian")]
    if len(q) < 8:
        return ""
    W, H = 680, 210
    L, R, T, B = 46, 8, 12, 26
    labels = [x["quarter"] for x in q]
    rmap = {x["quarter"]: x["rollingMedian"] for x in roll}
    vals = [x["medianPrice"] for x in q] + list(rmap.values())
    top = max(vals) * 1.06
    n = len(q) - 1

    def X(i):
        return L + (i / n) * (W - L - R)

    def Y(v):
        return T + (1 - v / top) * (H - T - B)

    qp = "M " + " L ".join(f"{X(i):.1f},{Y(x['medianPrice']):.1f}" for i, x in enumerate(q))
    rpts = [(i, rmap[lab]) for i, lab in enumerate(labels) if lab in rmap]
    rp = ("M " + " L ".join(f"{X(i):.1f},{Y(v):.1f}" for i, v in rpts)) if rpts else ""

    grid = []
    step = 400_000 if top <= 2_200_000 else 500_000
    v = 0
    while v <= top:
        grid.append(f'<line x1="{L}" x2="{W-R}" y1="{Y(v):.1f}" y2="{Y(v):.1f}" '
                    f'stroke="var(--line-2)" stroke-width="1"/>'
                    f'<text x="{L-6}" y="{Y(v)+3:.1f}" text-anchor="end" font-size="8.5" '
                    f'fill="var(--muted)">${v/1000:.0f}k</text>')
        v += step
    ticks = "".join(
        f'<text x="{X(i):.1f}" y="{H-8}" text-anchor="middle" font-size="8" '
        f'fill="var(--muted)">{E(str(labels[i]))}</text>'
        for i in range(0, len(q), max(1, len(q) // 7)))

    # Points the scrubber reads. Kept as data rather than re-derived in JS so the
    # chart and the readout can never disagree about a quarter.
    pts = [{"q": lab, "x": round(X(i), 1),
            "qy": round(Y(q[i]["medianPrice"]), 1), "qv": q[i]["medianPrice"],
            "ry": round(Y(rmap[lab]), 1) if lab in rmap else None,
            "rv": rmap.get(lab)}
           for i, lab in enumerate(labels)]

    return (
        f'<div class="mchart" data-pts=\'{json.dumps(pts)}\' data-h="{H}" data-w="{W}">'
        f'<svg viewBox="0 0 {W} {H}" width="100%" role="img" '
        f'aria-label="Quarterly and rolling twelve-month median house price, {labels[0]} to '
        f'{labels[-1]}">'
        + "".join(grid) + ticks
        + f'<path d="{qp}" fill="none" stroke="#C4B5A4" stroke-width="1.4"/>'
        + (f'<path d="{rp}" fill="none" stroke="var(--accent)" stroke-width="2.4" '
           f'stroke-linejoin="round"/>' if rp else "")
        + f'<line class="scrub" x1="0" x2="0" y1="{T}" y2="{H-B}" stroke="var(--ink)" '
          f'stroke-width="1" opacity="0"/>'
          '<circle class="dotq" r="3.2" fill="#C4B5A4" opacity="0"/>'
          '<circle class="dotr" r="4" fill="var(--accent)" opacity="0"/>'
        + '</svg>'
        '<div class="mtip" hidden></div>'
        '<div class="mlegend"><span class="lq">Quarterly median</span>'
        '<span class="lr">Rolling 12-month median</span></div></div>')


FEATURE_LABEL = {
    "land_size": ("Land", "m²"), "floor_area": ("Floor area", "m²"),
    "bedrooms": ("Bedrooms", ""), "bathrooms": ("Bathrooms", ""),
    "car_spaces": ("Car spaces", ""), "pool": ("Pool", ""), "stories": ("Levels", ""),
    "renovation": ("Condition", ""), "beach_proximity": ("Distance to beach", ""),
    "street_premium": ("Street", ""), "micro_location": ("Position", ""),
    "time_adjustment": ("Time since sale", ""), "golf_backing": ("Golf frontage", ""),
    "water_views": ("Water outlook", ""),
}
WEIGHT_FACTOR_LABEL = {
    "adjustment_quality": "How little had to be adjusted",
    "adjusted_accuracy": "How closely it agrees with the rest",
    "proximity": "How close it is",
    "recency": "How recently it sold",
    "verification": "How much we could verify",
    "data_quality": "How complete its record is",
}


def _phrase(feature, diff, subject, comp):
    """One difference, in words, describing the COMPARABLE — with no dollars.

    ⚠ POLARITY. `diff` is subject minus comp, so a POSITIVE diff means the
    subject has more and the comparable has LESS. The card is about the
    comparable, so the sense inverts. The first version did not, and described
    a 685 m² comparable as "a smaller block" against a 603 m² subject — the
    opposite of the truth, in a section whose whole job is showing our working.

    Magnitude words come from the PROPORTIONAL difference, not the raw one:
    80 m² is a lot of house and very little land.
    """
    if not diff:
        return None
    more = diff < 0            # the COMPARABLE has more of it
    try:
        share = abs(diff) / float(comp) if comp else 0
    except (TypeError, ValueError, ZeroDivisionError):
        share = 0
    scale = "far " if share >= 0.4 else ("notably " if share >= 0.15 else "")

    if feature == "land_size":
        return f"a {scale}{'larger' if more else 'smaller'} block"
    if feature == "floor_area":
        return f"a {scale}{'larger' if more else 'smaller'} house"
    if feature in ("bedrooms", "bathrooms", "car_spaces"):
        noun = {"bedrooms": "bedroom", "bathrooms": "bathroom",
                "car_spaces": "car space"}[feature]
        n = int(abs(diff))
        return f"{n} {'more' if more else 'fewer'} {noun}{'s' if n != 1 else ''}"
    if feature == "pool":
        return "a pool" if more else "no pool"
    if feature == "renovation":
        return f"a {'stronger' if more else 'weaker'} recorded condition"
    if feature == "stories":
        return "more than one level" if more else "single level"
    # ⚠ Position, street and beach adjustments are dropped from the word list.
    # They are frequently the largest dollar mover, so they led every card with
    # "a different position" — which is repetitive and tells a homeowner
    # nothing. The dollars are still in the expanded working, where the label
    # names the specific factor.
    return None


def differences_in_words(comp):
    """The two or three differences that actually moved the number, as prose.

    Ranked by DOLLARS — the biggest movers are the ones worth naming — but the
    dollars themselves are withheld until the reader asks.
    """
    adjs = [a for a in (comp.get("adjustments") or []) if a.get("dollars")]
    adjs.sort(key=lambda a: -abs(a["dollars"]))
    out = []
    for a in adjs:
        ph = _phrase(a.get("feature"), a.get("diff"), a.get("subject"), a.get("comp"))
        if ph and ph not in out:
            out.append(ph)
        if len(out) == 4:
            break
    return out


def evidence_cards(ev, limit=3):
    """The comparable cards, rendered from `valuation_evidence_from_engine()`.

    ⚠ This is the SAME payload `ValuationEvidence.tsx` consumes — resolver
    output, no recomputation. It ships as that component; this reproduces its
    content so the prototype reads end to end, and is not where its design gets
    decided. Photos arrive as {thumb, full} already normalised to the CDN.
    """
    comps = ev.get("comparables") or []
    if not comps:
        return ""
    out = []
    for i, c in enumerate(comps):
        hidden = "" if i < limit else ' hidden data-extra="1"'
        f = c.get("features") or {}
        bits = [f'{f["bedrooms"]} bd' if f.get("bedrooms") else None,
                f'{f["bathrooms"]} ba' if f.get("bathrooms") else None,
                f'{f["landSqm"]:.0f}m² land' if f.get("landSqm") else None,
                f'{f["floorSqm"]:.0f}m² floor' if f.get("floorSqm") else None]
        meta = [f'{c["distanceKm"]:.1f}km away' if c.get("distanceKm") else None,
                _ago(c.get("saleDate")),
                f'Weight: {c["weightPct"]}%' if c.get("weightPct") is not None else None]
        rows = []
        for a in (c.get("adjustments") or []):
            lab, unit = FEATURE_LABEL.get(a.get("feature"),
                                          (str(a.get("feature", "")).replace("_", " ").capitalize(), ""))
            d = a.get("dollars") or 0
            if not d:
                continue
            sv, cv = a.get("subject"), a.get("comp")
            detail = (f'theirs {cv:,.0f}{unit} · yours {sv:,.0f}{unit}'
                      if isinstance(sv, (int, float)) and isinstance(cv, (int, float)) else "")
            rows.append(f'<div class="arow"><span>{E(lab)}'
                        + (f'<em>{E(detail)}</em>' if detail else "")
                        + f'</span><span class="ad">{"+" if d > 0 else "−"}'
                        f'{exact(abs(d))}</span></div>')
        wf = "".join(
            f'<div class="wrow"><span>{E(WEIGHT_FACTOR_LABEL.get(k, k))}</span>'
            f'<span class="wbar"><i style="width:{min(100, v*100):.0f}%"></i></span></div>'
            for k, v in (c.get("weightFactors") or {}).items())
        photos = "".join(
            f'<img src="{E(ph["thumb"])}" alt="" loading="lazy">'
            for ph in (c.get("photos") or [])[:4] if isinstance(ph, dict) and ph.get("thumb"))
        more = len(c.get("photos") or []) - 4

        out.append(
            f'<article class="ecard"{hidden}>'
            f'<div class="ehead"><span class="erank">{i+1}</span>'
            f'<span class="eaddr">{E(str(c.get("address", "")))}</span>'
            + ('<span class="ever" title="Verified against the record">✓</span>' if c.get("verified") else "")
            + '</div>'
            + (f'<div class="efeat">{E(" · ".join(x for x in bits if x))}</div>' if any(bits) else "")
            + '<div class="eprice">'
              f'<div><span class="k">Sold</span><span class="v">{E(exact(c.get("soldPrice")) or "—")}</span></div>'
              f'<div><span class="k">Adjusted to yours</span>'
              f'<span class="v adj">{E(exact(c.get("adjustedPrice")) or "—")}</span></div></div>'
            + (f'<div class="emeta">{E(" · ".join(x for x in meta if x))}</div>' if any(meta) else "")
            + (('<div class="ediff"><span class="k">Main differences</span><ul>'
                + "".join(f'<li>{E(d)}</li>' for d in differences_in_words(c))
                + '</ul></div>') if differences_in_words(c) else "")
            + (f'<div class="ephotos">{photos}'
               + (f'<span class="emore">+{more}</span>' if more > 0 else "") + '</div>' if photos else "")
            + (f'<details class="ework"><summary>See all {len(rows)} adjustments</summary>'
               f'<div class="body">'
               + (f'<p class="enarr">{E(str(c.get("narrative", "")))}</p>'
                  if c.get("narrative") else "")
               + f'{"".join(rows)}'
               f'<div class="anet"><span>Net adjustment</span><span>'
               f'{"+" if (c.get("netAdjustment") or 0) > 0 else "−"}'
               f'{exact(abs(c.get("netAdjustment") or 0))}</span></div>'
               + (f'<div class="wlab">Why it carries {c.get("weightPct")}% of the weight</div>{wf}'
                  if wf else "")
               + '</div></details>' if rows else "")
            + '</article>')

    extra = len(comps) - limit
    if extra > 0:
        out.append(f'<button class="btn showall" data-n="{extra}">See all {len(comps)} '
                   f'comparables</button>')
    return '<div class="ecards">' + "".join(out) + '</div>'


def _ago(ms):
    if not ms:
        return None
    from datetime import datetime, timezone
    try:
        d = datetime.fromtimestamp(ms / 1000, tz=timezone.utc)
    except Exception:
        return None
    months = (datetime.now(timezone.utc) - d).days // 30
    if months < 1:
        return "this month"
    return f"{months} month{'s' if months != 1 else ''} ago"



def median_block(suburb_display, ms):
    """The suburb median, placed against the national picture.

    ⚠ Leads with the ROLLING 12-MONTH median, never the latest quarter. The data
    carries its own warning: `latest_quarter_median_price_basis` reads "name it
    as a quarterly figure wherever it appears, never as 'the median house
    price'". Robina runs $1,560k then $1,410k on samples of 55 and 43, which is
    why the mindset brief bars quarter-on-quarter claims there and in Burleigh
    Waters.
    """
    med = ms.get("median_12m")
    if not med:
        return ""
    lo, hi = ms.get("median_12m_ci_low"), ms.get("median_12m_ci_high")
    n = ms.get("median_12m_sample_n")
    yoy = ms.get("yoy_growth_pct")
    mi = market_insights(suburb_display)

    out = []
    lede = (f"Nationally, home values have fallen for three consecutive months. Over the same "
            f"period the rolling twelve-month median for houses in {suburb_display} sits at "
            f"<b>{exact(med)}</b>")
    if yoy is not None:
        lede += (f", {abs(yoy):.1f}% {'above' if yoy >= 0 else 'below'} the twelve months before "
                 f"it")
    lede += (". The two are not in conflict \u2014 a national index and one suburb measure "
             "different things.")
    out.append(f'<p class="lede">{lede}</p>')
    if lo and hi and n:
        out.append(f'<p class="fine">That figure carries a range of {exact(lo)} to {exact(hi)} on '
                   f'{n} sales \u2014 a twelve-month rolling median, built from Domain and '
                   f'onthehouse sale records combined.</p>')

    chart = median_chart(mi)
    if chart:
        out.append(chart)
        qs = [x["medianPrice"] for x in (mi.get("medianPriceHistory") or []) if x.get("medianPrice")]
        if qs:
            out.append(f'<div class="mstats">'
                       f'<div><span class="k">Current (12 months)</span>'
                       f'<span class="v">{exact(med)}</span></div>'
                       f'<div><span class="k">Highest quarter</span>'
                       f'<span class="v">{exact(max(qs))}</span></div>'
                       f'<div><span class="k">Lowest quarter</span>'
                       f'<span class="v">{exact(min(qs))}</span></div></div>')
        out.append('<p class="fine">The quarterly line moves around more than the underlying '
                   'market does \u2014 individual quarters can rest on very few sales. The '
                   'twelve-month line is the one worth reading.</p>')
    return "".join(out)


def seasonality_strip():
    """A port of `YourHomePage/components/SeasonalityStrip.tsx`, not a new chart.

    That component is already built, already reconciled to the canonical dataset
    and already carries the citations. Reproducing its treatment — month tiles
    with the value on each, tinted copper above the annual average and teal
    below, a below/above scale, the peak outlined, the current month dotted, and
    a detail panel — keeps this page and the mini-site telling one story.
    Inventing a second chart is how two surfaces end up disagreeing.

    Editorial framing carried over verbatim: a recurring PATTERN, never a
    prediction, and the spread is explained as buyer concentration rather than
    as a best-time-to-sell recommendation.
    """
    from datetime import datetime
    peak = max(range(len(SEASONALITY)), key=lambda i: SEASONALITY[i][1])
    trough = min(range(len(SEASONALITY)), key=lambda i: SEASONALITY[i][1])
    now = datetime.now().month - 1
    cells = []
    for i, (m, pct, n) in enumerate(SEASONALITY):
        # Same tint maths as the component: intensity = min(|pct|/6, 1) * 0.55,
        # copper (183,103,73) above the average, sky (160,209,201) below.
        inten = min(abs(pct) / 6, 1) * 0.55
        rgb = "183,103,73" if pct >= 0 else "160,209,201"
        cls = "mcell" + (" peak" if i == peak else "")
        dot = '<i class="nowdot" title="current month"></i>' if i == now else ""
        cells.append(
            f'<button class="{cls}" style="background:rgba({rgb},{inten:.3f})" '
            f'data-i="{i}" aria-label="{E(m)}, {pct:+.1f} per cent versus the annual average">'
            f'{dot}<span class="mm">{E(m)}</span>'
            f'<span class="mp">{pct:+.1f}%</span></button>')

    det = []
    for i, (m, pct, n) in enumerate(SEASONALITY):
        if i == peak:
            tail = (f"{m} is the strongest month in the pattern \u2014 the months either side of "
                    f"it carry most of the seasonal weight.")
        elif i == trough:
            tail = (f"{m} is the weakest month in the pattern, when buyer activity is most "
                    f"thinly spread.")
        elif pct >= 0:
            tail = (f"{m} sits above the annual average, though short of the "
                    f"{SEASONALITY[peak][0]} peak.")
        else:
            tail = f"{m} sits below the annual average for the catchment."
        det.append(
            f'<div class="mdet" data-i="{i}"{"" if i == peak else " hidden"}>'
            f'<div class="mdh"><span class="mdm">{E(m)}</span>'
            f'<span class="mdp">{pct:+.1f}% versus the annual average</span></div>'
            f'<p class="mdb">{n:,} house sales in {E(SEASONALITY_SCOPE)} fall in {E(m)} across '
            f'the sold record ({E(SEASONALITY_WINDOW)}). {E(tail)}</p></div>')

    spread = SEASONALITY[peak][1] - SEASONALITY[trough][1]
    return (
        f'<p class="lede">Across {SEASONALITY_N:,} house sales in {E(SEASONALITY_SCOPE)} '
        f'({E(SEASONALITY_WINDOW)}), the gap between the strongest month '
        f'({E(SEASONALITY[peak][0])}) and the weakest ({E(SEASONALITY[trough][0])}) has run about '
        f'{spread:.1f} percentage points, after controlling for each year\u2019s overall price '
        f'growth. It is a recurring historical pattern, not a forecast.</p>'
        f'<div class="season"><div class="mgrid">{"".join(cells)}</div>'
        f'<div class="mscale"><span>Below average</span><i></i><span>Above average</span></div>'
        f'<p class="fine">Tap any month for the sales behind it \u2014 the dot marks the current '
        f'month.</p>{"".join(det)}</div>'
        f'<p class="fine">The academic reading is that these patterns are driven by buyer '
        f'concentration \u2014 more serious buyers in the market at once \u2014 rather than by seller '
        f'scarcity (Ngai &amp; Tenreyro, 2014; Miller, Sklarz &amp; Real, 2014). A catchment-wide '
        f'figure: per-suburb months are too thin to read.</p>')


def month_year(d):
    """'2026-03' rendered raw on the first pass. Comparables are evidence; a
    machine-formatted date undercuts that."""
    from datetime import datetime
    if not d:
        return None
    try:
        return datetime.fromisoformat(str(d)[:10]).strftime("%B %Y")
    except Exception:
        try:
            return datetime.strptime(str(d)[:7], "%Y-%m").strftime("%B %Y")
        except Exception:
            return str(d)[:7]


def exact(v):
    return f"${int(round(float(v))):,}" if v is not None else None


ADJ_LABELS = {
    "land_size": ("Land size", "m²"), "floor_area": ("Floor area", "m²"),
    "bedrooms": ("Bedrooms", ""), "bathrooms": ("Bathrooms", ""),
    "car_spaces": ("Car spaces", ""), "pool": ("Pool", ""),
    "stories": ("Levels", ""), "renovation": ("Condition", ""),
    "beach_proximity": ("Distance to beach", ""), "street_premium": ("Street", ""),
    "micro_location": ("Position", ""), "time_adjustment": ("Time since sale", ""),
    "golf_backing": ("Golf frontage", ""), "water_views": ("Water outlook", ""),
}


def _num(v, unit):
    if v is None:
        return "—"
    f = float(v)
    s = f"{f:,.0f}" if abs(f - round(f)) < 0.05 else f"{f:,.1f}"
    return s + unit


def adjustment_rows(comp):
    """Itemised working for one comparable.

    `adjustments` is a DICT keyed by feature, each carrying subject_value,
    comp_value, rate, dollars and sometimes `skipped`. Rows worth nothing and
    differing in nothing are omitted — they are noise, not evidence.

    A SKIPPED row is kept and labelled, because it is the honest bit: it names a
    comparison we could not make. Bathrooms is usually the one, which is exactly
    what the correction section asks the owner to fill in.
    """
    out = []
    for key, a in (comp.get("adjustments") or {}).items():
        if not isinstance(a, dict):
            continue
        label, unit = ADJ_LABELS.get(key, (key.replace("_", " ").capitalize(), ""))
        dollars, skipped = a.get("dollars") or 0, a.get("skipped")
        if not skipped and not dollars:
            continue
        if skipped:
            out.append(
                f'<div style="display:flex;justify-content:space-between;gap:12px;padding:8px 0;'
                f'border-bottom:1px solid var(--line-2);color:var(--muted)">'
                f'<span>{E(label)}<br><span class="fine">not compared — we don\'t have yours</span></span>'
                f'<span>—</span></div>')
            continue
        sv, cv = _num(a.get("subject_value"), unit), _num(a.get("comp_value"), unit)
        sign = "+" if dollars > 0 else "−"
        out.append(
            f'<div style="display:flex;justify-content:space-between;gap:12px;padding:8px 0;'
            f'border-bottom:1px solid var(--line-2)">'
            f'<span>{E(label)}<br><span class="fine">theirs {E(cv)} · yours {E(sv)}</span></span>'
            f'<span style="white-space:nowrap;color:var(--accent)">{sign}{E(exact(abs(dollars)))}</span>'
            f'</div>')
    tot = comp.get("total_adjustment")
    if tot is not None:
        sign = "+" if tot > 0 else "−"
        out.append(
            f'<div style="display:flex;justify-content:space-between;gap:12px;padding:12px 0 2px;'
            f'font-weight:600"><span>Net adjustment</span>'
            f'<span style="white-space:nowrap">{sign}{E(exact(abs(tot)))}</span></div>')
    return "".join(out)


CSS = """
:root{
  --paper:#F7F5F1; --paper-2:#FFFFFF; --stone:#EDE9E2;
  --ink:#2A2724; --ink-2:#4A443E; --muted:#7D7469;
  --line:#DDD7CE; --line-2:#E9E4DC;
  --accent:#B4643F; --accent-soft:#F0E2D9;
  --serif:'Iowan Old Style','Palatino Linotype',Palatino,Georgia,'Times New Roman',serif;
  --sans:-apple-system,BlinkMacSystemFont,'Segoe UI',Inter,Roboto,Helvetica,Arial,sans-serif;
}
*{box-sizing:border-box}
body{margin:0;background:var(--paper);color:var(--ink);font-family:var(--sans);
     line-height:1.6;-webkit-font-smoothing:antialiased;font-size:17px}
.wrap{max-width:780px;margin:0 auto;padding:0 22px}
.wide{max-width:1120px;margin:0 auto;padding:0 22px}
section{padding:66px 0 58px;border-top:1px solid var(--line);position:relative}
section:first-of-type{border-top:none}
/* A short accent stub sitting on the rule — a visible "a new part starts
   here" that costs no vertical space and no colour beyond the one accent. */
section::before{content:"";position:absolute;top:-1px;left:0;width:34px;height:2px;
  background:var(--accent);border-radius:2px}
section:first-of-type::before{display:none}
/* ── TYPE HIERARCHY ────────────────────────────────────────────────────
   Two levels, told apart by FAMILY as well as size, because size alone was
   not doing it: h3 previously had no font-size rule and inherited the h1/h2
   group, so it rendered as a slightly smaller h2 in the same serif, same
   weight, same letter-spacing. The reader could not tell a new section from a
   sub-part of the one they were in.

     SERIF  = a section of the page. One per section.
     SANS   = a sub-part inside a section. Never starts a section.

   The rule is absolute so it can be read at a glance rather than measured. */
h1,h2{font-family:var(--serif);font-weight:600;letter-spacing:-.015em;line-height:1.18;margin:0}
h1{font-size:2.1rem}
h2{font-size:1.78rem;margin-bottom:.7rem}
h3{font-family:var(--sans);font-size:.94rem;font-weight:650;letter-spacing:.005em;
   line-height:1.4;margin:0 0 .5rem;color:var(--ink)}
p{margin:0 0 1rem}
.eyebrow{font-size:.68rem;letter-spacing:.16em;text-transform:uppercase;color:var(--accent);
         font-weight:700;margin-bottom:.85rem}
.lede{font-size:1.12rem;color:var(--ink-2)}
.fine{font-size:.86rem;color:var(--muted)}

/* header */
header.top{position:sticky;top:0;z-index:50;background:rgba(247,245,241,.94);
  backdrop-filter:saturate(140%) blur(9px);border-bottom:1px solid transparent;transition:border-color .25s}
header.top.stuck{border-bottom-color:var(--line)}
.topin{max-width:1120px;margin:0 auto;padding:12px 22px;display:flex;justify-content:space-between;
       align-items:center;gap:14px}
.brand{display:block;height:24px;width:auto}
.tag{font-size:.64rem;letter-spacing:.11em;text-transform:uppercase;color:var(--muted);
     white-space:nowrap}
.stickyaddr{font-size:.86rem;color:var(--ink-2);opacity:0;transition:opacity .25s}
header.top.stuck .stickyaddr{opacity:1}

/* header right: tag + burger */
.hright{display:flex;align-items:center;gap:12px}
.burger{appearance:none;background:transparent;border:1px solid var(--line);border-radius:4px;
  width:34px;height:30px;display:flex;flex-direction:column;justify-content:center;align-items:center;
  gap:4px;cursor:pointer;padding:0;transition:border-color .18s}
.burger:hover{border-color:var(--accent)}
.burger span{display:block;width:15px;height:1.5px;background:var(--ink);border-radius:2px;
  transition:transform .22s,opacity .18s}
.burger[aria-expanded="true"] span:nth-child(1){transform:translateY(5.5px) rotate(45deg)}
.burger[aria-expanded="true"] span:nth-child(2){opacity:0}
.burger[aria-expanded="true"] span:nth-child(3){transform:translateY(-5.5px) rotate(-45deg)}

/* the menu */
.menu{border-top:1px solid var(--line);background:var(--paper);
  max-height:min(72vh,640px);overflow-y:auto;-webkit-overflow-scrolling:touch}
.menuin{max-width:1120px;margin:0 auto;padding:18px 22px 26px}
.secnav{display:grid;grid-template-columns:1fr;gap:0;margin:8px 0 4px}
.secnav a{display:flex;align-items:baseline;gap:12px;padding:11px 0;text-decoration:none;
  color:var(--ink);border-bottom:1px solid var(--line-2);font-size:.98rem}
.secnav a:hover{color:var(--accent)}
.secnav .i{font-size:.72rem;letter-spacing:.08em;color:var(--muted);min-width:20px}
.dl{margin-top:20px;padding-top:18px;border-top:1px solid var(--line)}
.qr{width:132px;height:132px;display:block;margin:10px 0 8px;background:#fff;
  border:1px solid var(--line-2);border-radius:6px;padding:8px}
.taponly{display:none}
@media(max-width:719px){.qr,.qronly{display:none}.taponly{display:inline-block}
  .dl .taponly.fine{display:block;margin-top:8px}}
@media(min-width:720px){.secnav{grid-template-columns:1fr 1fr;column-gap:28px}}

/* hero */
.hero{padding-top:26px}
/* Generous rounding, per the reference. 3px read as a square photo with its
   corners knocked off; the reference is unmistakably a rounded card. */
.shot{width:100%;aspect-ratio:16/10;object-fit:cover;border-radius:14px;background:var(--stone);
      display:block;border:1px solid var(--line-2)}
.addr{font-family:var(--serif);font-size:1.85rem;line-height:1.2;margin:18px 0 4px}
.sub{color:var(--muted);margin-bottom:14px}
.facts{display:flex;flex-wrap:wrap;gap:8px 18px;padding:14px 0;border-top:1px solid var(--line);
       border-bottom:1px solid var(--line);font-size:.94rem;color:var(--ink-2)}
.facts b{font-weight:600;color:var(--ink)}
.qs{margin:26px 0 0;padding:0;list-style:none}
.qs li{font-family:var(--serif);font-size:1.2rem;color:var(--ink);padding:7px 0 7px 20px;
       position:relative;line-height:1.45}
.qs li:before{content:"";position:absolute;left:0;top:16px;width:7px;height:1px;background:var(--accent)}
.promise{margin-top:22px;padding:16px 18px;background:var(--paper-2);border:1px solid var(--line-2);
         border-radius:3px;color:var(--ink-2);font-size:.95rem}

/* the answer */
.answer{background:var(--paper-2);border:1px solid var(--line);border-radius:4px;
        padding:30px 26px;margin:6px 0 0}
.rangeline{height:1px;background:var(--line);position:relative;margin:26px 0 10px}
.rangeline i{position:absolute;inset:0;background:var(--accent);transform-origin:left;
             transform:scaleX(0);animation:draw 1.1s .25s cubic-bezier(.22,1,.36,1) forwards}
@keyframes draw{to{transform:scaleX(1)}}
.rangefig{display:flex;align-items:baseline;justify-content:center;gap:10px;flex-wrap:nowrap;
          font-family:var(--serif);font-size:1.34rem;white-space:nowrap;
          opacity:0;animation:fade .6s 1.1s forwards}
.rangefig em{font-style:normal;color:var(--muted)}
.centre{margin-top:20px;opacity:0;animation:fade .6s 1.5s forwards}
.centre b{font-family:var(--serif);font-size:1.16rem;font-weight:600}
.basis{opacity:0;animation:fade .6s 1.8s forwards}
@keyframes fade{to{opacity:1}}
@media(prefers-reduced-motion:reduce){
  .rangeline i{animation:none;transform:scaleX(1)}
  .rangefig,.centre,.basis{animation:none;opacity:1}
}

/* controls */
.controls{display:flex;flex-wrap:wrap;gap:10px;margin-top:22px}
.btn{appearance:none;background:transparent;border:1px solid var(--line);color:var(--ink);
     font-family:var(--sans);font-size:.9rem;padding:10px 15px;border-radius:3px;cursor:pointer;
     transition:border-color .18s,background .18s}
.btn:hover{border-color:var(--accent);background:var(--accent-soft)}
.cue{display:inline-block;margin-top:30px;color:var(--accent);font-size:.96rem;
     text-decoration:none;border-bottom:1px solid transparent}
.cue:hover{border-bottom-color:var(--accent)}

/* split comparison */
.split{display:grid;grid-template-columns:1fr;gap:2px;background:var(--line-2);
       border:1px solid var(--line);border-radius:4px;overflow:hidden;margin:22px 0}
.split>div{background:var(--paper-2);padding:20px}
.split .k{font-size:.7rem;letter-spacing:.12em;text-transform:uppercase;color:var(--muted);margin-bottom:8px}
.split .a{font-family:var(--serif);font-size:1.16rem;margin-bottom:4px}
.split .p{font-family:var(--serif);font-size:1.42rem;color:var(--accent)}
.move{text-align:center;padding:20px;background:var(--paper-2);border:1px solid var(--line);
      border-radius:4px;font-family:var(--serif);font-size:1.05rem;margin-bottom:16px}
.move .arrow{color:var(--accent);padding:0 10px}
.move .to{color:var(--ink)}

/* comparables */
.comp{background:var(--paper-2);border:1px solid var(--line-2);border-radius:4px;
      padding:18px 20px;margin-bottom:12px}
.comp .a{font-family:var(--serif);font-size:1.08rem;margin-bottom:3px}
.comp .m{font-size:.86rem;color:var(--muted);margin-bottom:12px}
.comp .adj{display:flex;justify-content:space-between;align-items:baseline;gap:12px;
           padding-top:12px;border-top:1px solid var(--line-2);flex-wrap:wrap}
.comp .adj .lab{font-size:.84rem;color:var(--muted)}
.comp .adj .val{font-family:var(--serif);font-size:1.16rem;color:var(--accent)}
.diffs{font-size:.87rem;color:var(--ink-2);margin-top:8px}

/* funnel */
.funnel{margin:24px 0}
.funnel .row{padding:13px 16px;background:var(--paper-2);border:1px solid var(--line-2);
             border-radius:3px;font-size:.96rem}
.funnel .row.last{border-color:var(--accent);background:var(--accent-soft)}
.funnel .drop{text-align:center;color:var(--muted);font-size:.88rem;padding:5px 0}

/* attributes */
.attrs{display:grid;grid-template-columns:repeat(3,1fr);gap:10px;margin:22px 0}
.attrs>div{background:var(--paper-2);border:1px solid var(--line-2);border-radius:3px;
           padding:16px 12px;text-align:center}
.attrs .n{font-family:var(--serif);font-size:1.3rem}
.attrs .l{font-size:.78rem;color:var(--muted);margin-top:3px}

/* error rate */
.bigfig{font-family:var(--serif);font-size:3.1rem;line-height:1;color:var(--accent);margin-bottom:6px}
.scale{margin:24px 0;padding:20px;background:var(--paper-2);border:1px solid var(--line-2);border-radius:4px}
.scale .bar{height:3px;background:var(--stone);position:relative;margin:30px 0 8px;border-radius:2px}
.scale .band{position:absolute;top:0;bottom:0;background:var(--accent-soft);border-left:1px solid var(--accent);
             border-right:1px solid var(--accent)}
.scale .tick{position:absolute;top:-9px;width:1px;height:21px;background:var(--ink)}
.scale .lbl{display:flex;justify-content:space-between;font-size:.78rem;color:var(--muted)}

/* two true */
.twotrue{display:grid;grid-template-columns:1fr;gap:12px;margin:20px 0}
.twotrue>div{background:var(--paper-2);border:1px solid var(--line-2);border-left:2px solid var(--accent);
             border-radius:3px;padding:18px 20px}
.twotrue .n{font-family:var(--serif);font-size:1.3rem;margin-bottom:4px}

/* correction */
.correct{background:var(--paper-2);border:1px solid var(--line);border-radius:4px;padding:26px}
.choices{display:flex;flex-wrap:wrap;gap:10px;margin:16px 0 4px}
.choice{appearance:none;background:transparent;border:1px solid var(--line);border-radius:3px;
        padding:12px 22px;font-size:1rem;font-family:var(--sans);cursor:pointer;color:var(--ink);
        transition:all .18s}
.choice:hover{border-color:var(--accent)}
.choice[aria-pressed="true"]{background:var(--accent);border-color:var(--accent);color:#fff}
.result{margin-top:18px;padding:16px 18px;background:var(--accent-soft);border-radius:3px;
        font-size:.95rem;display:none}
.result.on{display:block}

/* closing */
.closing{background:var(--paper-2);border:1px solid var(--line);border-radius:4px;padding:32px 26px}
.cta{display:inline-block;margin-top:20px;background:var(--accent);color:#fff;text-decoration:none;
     padding:15px 26px;border-radius:3px;font-size:1rem;transition:background .18s}
.cta:hover{background:#9C5233}

/* disclosure */
details{margin-top:16px;border-top:1px solid var(--line-2);padding-top:14px}
summary{cursor:pointer;color:var(--accent);font-size:.9rem;list-style:none}
summary::-webkit-details-marker{display:none}
summary::after{content:" →"}
details[open] summary::after{content:" ↓"}
details .body{padding-top:12px;font-size:.94rem;color:var(--ink-2)}
.src{margin-top:26px;padding-top:14px;border-top:1px solid var(--line-2);font-size:.8rem;color:var(--muted)}


/* full comparable table (B) */
.ctable{margin-top:6px}
.crow{display:grid;grid-template-columns:1fr auto auto;gap:4px 12px;padding:12px 0 6px;
      border-bottom:1px solid var(--line-2);align-items:baseline}
.crow .ca{grid-column:1/-1}
.crow .cs{color:var(--muted);font-size:.9rem}
.crow .cj{font-family:var(--serif);color:var(--accent)}
.crow .cw{grid-column:1/-1;height:2px;background:var(--stone);border-radius:2px;margin-top:4px}
.crow .cw span{display:block;height:100%;background:var(--accent);border-radius:2px}
.crow .cv{grid-column:1/-1}
.cwork{padding:2px 0 16px 0;border-bottom:1px solid var(--line-2);margin-bottom:4px}

/* competitor rail (C) */
.rail{display:grid;grid-auto-flow:column;grid-auto-columns:78%;gap:12px;overflow-x:auto;
      scroll-snap-type:x mandatory;margin:20px -22px;padding:0 22px 6px;
      -webkit-overflow-scrolling:touch}
.rail::-webkit-scrollbar{height:0}
.lcard{scroll-snap-align:start;background:var(--paper-2);border:1px solid var(--line-2);
       border-radius:4px;overflow:hidden;display:flex;flex-direction:column}
.lcard img{width:100%;aspect-ratio:16/10;object-fit:cover;display:block;background:var(--stone)}
.lcard .b{padding:14px 16px}
.lcard .a{font-family:var(--serif);font-size:1.02rem;margin-bottom:2px}
.lcard .pr{font-family:var(--serif);color:var(--accent);margin-top:8px}
.pill{display:inline-block;margin-top:10px;font-size:.72rem;letter-spacing:.06em;
      text-transform:uppercase;color:var(--muted);border:1px solid var(--line);
      border-radius:99px;padding:3px 10px}
.pill.hot{color:var(--accent);border-color:var(--accent)}

/* timeline (C) */
.tl{list-style:none;margin:16px 0;padding:0}
.tl li{padding:0 0 18px 20px;border-left:1px solid var(--line);position:relative}
.tl li:last-child{border-left-color:transparent}
.tl li:before{content:"";position:absolute;left:-4px;top:7px;width:7px;height:7px;
              border-radius:99px;background:var(--accent)}
.tl .d{font-size:.74rem;letter-spacing:.1em;text-transform:uppercase;color:var(--muted)}
.tl .h{font-family:var(--serif);font-size:1.06rem;margin:2px 0 3px}

/* simulated state (C) — must never read as working */
.sim{margin:24px 0;padding:20px;border:1px dashed var(--line);border-radius:4px;background:transparent}
.simtag{display:inline-block;font-size:.66rem;letter-spacing:.13em;text-transform:uppercase;
        color:var(--accent);border:1px solid var(--accent);border-radius:99px;
        padding:2px 9px;margin-bottom:10px}
.sim h3{margin-bottom:6px}
.ticks{list-style:none;padding:0;margin:10px 0}
.ticks li{padding:6px 0 6px 18px;position:relative;color:var(--ink-2)}
.ticks li:before{content:"";position:absolute;left:0;top:15px;width:7px;height:1px;background:var(--accent)}

@media(min-width:760px){.rail{grid-auto-columns:31%}}


/* value drivers (buyer section) */
.drivers{display:grid;grid-template-columns:1fr;gap:12px;margin:20px 0}
.drv{background:var(--paper-2);border:1px solid var(--line-2);border-radius:4px;padding:16px 18px}
.drv ul{list-style:none;margin:8px 0 0;padding:0}
.drv li{padding:5px 0 5px 16px;position:relative;color:var(--ink)}
.drv li:before{content:"";position:absolute;left:0;top:14px;width:7px;height:1px;background:var(--accent)}
@media(min-width:760px){.drivers{grid-template-columns:1fr 1fr}}

/* the five owner-only questions */
.qs2{margin:14px 0 6px;padding-left:20px}
.qs2 li{font-family:var(--serif);font-size:1.04rem;padding:6px 0;color:var(--ink)}


/* median price chart */
.mchart{margin:18px 0 10px;padding:14px 12px 10px;background:var(--paper-2);
  border:1px solid var(--line-2);border-radius:8px}
.mchart{position:relative}
/* pan-y: a vertical swipe still scrolls the page, a horizontal drag scrubs.
   Capturing both axes would trap the reader inside the chart. */
.mchart svg{display:block;touch-action:pan-y;cursor:crosshair}
.mtip{position:absolute;top:6px;transform:translateX(-50%);pointer-events:none;
  background:var(--ink);color:var(--paper);border-radius:5px;padding:7px 10px;
  font-size:.74rem;line-height:1.45;white-space:nowrap;z-index:2;
  box-shadow:0 6px 18px rgba(34,56,44,.22)}
.mtip b{display:block;font-family:var(--serif);font-size:.84rem;margin-bottom:2px}
.mtip span{display:block}
.mtip .tq{opacity:.72}
.mtip .tr{color:var(--gold, #D28C5E)}
.mlegend{display:flex;gap:16px;margin-top:8px;font-size:.76rem;color:var(--muted)}
.mlegend span{display:flex;align-items:center;gap:6px}
.mlegend span:before{content:"";width:16px;height:2px;border-radius:2px;background:#C4B5A4}
.mlegend .lr:before{background:var(--accent);height:3px}
.mstats{display:grid;grid-template-columns:repeat(3,1fr);gap:10px;margin:12px 0 6px}
.mstats>div{background:var(--paper-2);border:1px solid var(--line-2);border-radius:6px;
  padding:12px 10px;text-align:center}
.mstats .k{display:block;font-size:.62rem;letter-spacing:.08em;text-transform:uppercase;
  color:var(--muted);margin-bottom:4px}
.mstats .v{font-family:var(--serif);font-size:1.02rem}

/* seasonality — ported from YourHomePage/components/SeasonalityStrip */
.season{margin:20px 0 10px;padding:18px 16px 14px;background:var(--paper-2);
  border:1px solid var(--line-2);border-radius:8px}
.mgrid{display:grid;grid-template-columns:repeat(6,1fr);gap:6px}
.mcell{position:relative;appearance:none;border:1px solid transparent;border-radius:6px;
  padding:9px 4px 8px;cursor:pointer;font-family:var(--sans);text-align:center;
  display:flex;flex-direction:column;gap:2px;transition:border-color .15s}
.mcell:hover{border-color:var(--line)}
.mcell.peak{border-color:var(--ink)}
.mcell[aria-pressed="true"]{border-color:var(--accent)}
.mcell .mm{font-size:.62rem;letter-spacing:.1em;text-transform:uppercase;color:var(--muted)}
.mcell .mp{font-family:var(--serif);font-size:.98rem;color:var(--ink)}
.nowdot{position:absolute;top:5px;right:5px;width:5px;height:5px;border-radius:99px;
  background:var(--accent)}
.mscale{display:flex;align-items:center;gap:9px;margin:12px 0 6px;font-size:.68rem;color:var(--muted)}
.mscale i{flex:1;height:3px;border-radius:2px;
  background:linear-gradient(90deg,rgba(160,209,201,.85),rgba(247,245,241,1),rgba(183,103,73,.85))}
.mdet{margin-top:12px;padding:14px 16px;background:rgba(254,198,111,.10);
  border:1px solid rgba(183,103,73,.18);border-radius:6px}
.mdh{display:flex;flex-wrap:wrap;align-items:baseline;gap:10px;margin-bottom:5px}
.mdm{font-family:var(--serif);font-size:1.12rem}
.mdp{color:var(--accent);font-size:.86rem;font-weight:600}
.mdb{margin:0;font-size:.92rem;color:var(--ink-2)}
@media(min-width:720px){.mgrid{grid-template-columns:repeat(12,1fr)}}


/* placeholder marker for sections that ship as an existing component */
.ported{display:flex;gap:10px;align-items:flex-start;margin:14px 0 18px;padding:11px 13px;
  border:1px dashed var(--line);border-radius:5px;background:transparent;
  font-size:.8rem;color:var(--muted);line-height:1.5}
.ptag{flex:none;font-size:.62rem;letter-spacing:.1em;text-transform:uppercase;color:var(--accent);
  border:1px solid var(--accent);border-radius:99px;padding:2px 8px;margin-top:1px}
.ported code{font-size:.78rem;color:var(--ink-2)}


/* comparable evidence cards — content mirrors ValuationEvidence */
.ecards{margin:18px 0 6px}
.ecard{background:var(--paper-2);border:1px solid var(--line-2);border-radius:8px;
  padding:16px 18px;margin-bottom:12px}
.ehead{display:flex;align-items:center;gap:9px;margin-bottom:3px}
.erank{flex:none;width:21px;height:21px;border-radius:99px;background:var(--accent);color:#fff;
  font-size:.68rem;display:flex;align-items:center;justify-content:center}
.eaddr{font-family:var(--serif);font-size:1.06rem;line-height:1.3}
.ever{margin-left:auto;color:#4E7A5E;font-size:.9rem}
.efeat{font-size:.84rem;color:var(--muted);margin-bottom:12px}
.eprice{display:grid;grid-template-columns:1fr 1fr;gap:10px;padding:11px 0;
  border-top:1px solid var(--line-2);border-bottom:1px solid var(--line-2)}
.eprice .k{display:block;font-size:.6rem;letter-spacing:.09em;text-transform:uppercase;
  color:var(--muted);margin-bottom:2px}
.eprice .v{font-family:var(--serif);font-size:1.06rem}
.eprice .v.adj{color:var(--accent)}
.emeta{font-size:.8rem;color:var(--muted);margin-top:9px}
.enarr{font-size:.84rem;color:var(--muted);margin:0 0 10px;line-height:1.5}
.ediff{margin-top:11px}
.ediff .k{display:block;font-size:.6rem;letter-spacing:.09em;text-transform:uppercase;
  color:var(--muted);margin-bottom:5px}
.ediff ul{list-style:none;margin:0;padding:0;display:flex;flex-wrap:wrap;gap:6px}
.ediff li{font-size:.84rem;color:var(--ink-2);background:var(--paper);border:1px solid var(--line-2);
  border-radius:99px;padding:4px 11px}
.ephotos{display:flex;gap:6px;margin-top:12px;align-items:center}
.ephotos img{width:23%;aspect-ratio:4/3;object-fit:cover;border-radius:5px;background:var(--stone)}
.emore{font-size:.76rem;color:var(--muted)}
.ework{margin-top:12px;border-top:1px solid var(--line-2);padding-top:10px}
.arow{display:flex;justify-content:space-between;gap:12px;padding:7px 0;
  border-bottom:1px solid var(--line-2);font-size:.88rem}
.arow em{display:block;font-style:normal;font-size:.76rem;color:var(--muted)}
.arow .ad{white-space:nowrap;color:var(--accent)}
.anet{display:flex;justify-content:space-between;padding:11px 0 4px;font-weight:600;font-size:.92rem}
.wlab{margin-top:10px;font-size:.72rem;letter-spacing:.06em;text-transform:uppercase;color:var(--muted)}
.wrow{display:flex;align-items:center;gap:10px;padding:5px 0;font-size:.82rem;color:var(--ink-2)}
.wrow span:first-child{flex:1}
.wbar{flex:none;width:82px;height:4px;background:var(--stone);border-radius:2px;overflow:hidden}
.wbar i{display:block;height:100%;background:var(--accent)}
.showall{margin-top:4px}


.promiseline{font-weight:600;color:var(--ink)}


/* ── PART: the level above a section ───────────────────────────────────
   Reads as a chapter opening, not another section: full-bleed tone change,
   generous air, and the section rule suppressed on the section that follows
   so the part and its first section read as one unit. */
.part{background:var(--stone);border-top:1px solid var(--line);padding:52px 0 40px;margin-top:0}
.parth{font-family:var(--serif);font-size:2.4rem;line-height:1.1;letter-spacing:-.02em;
  margin:0 0 .35rem;color:var(--ink)}
.parts{margin:0;color:var(--ink-2);font-size:1.04rem;max-width:34ch}
.part + section{border-top:none;padding-top:44px}
.part + section::before{display:none}
@media(min-width:760px){.parth{font-size:3.1rem}.part{padding:64px 0 48px}}


/* the hook — the reason they clicked, said first */
.opener{margin:30px 0 6px;font-size:1.1rem;color:var(--ink-2)}
.hookq{font-family:var(--serif);font-size:2.15rem;line-height:1.14;letter-spacing:-.02em;
  margin:0 0 4px;color:var(--ink)}
@media(min-width:760px){.hookq{font-size:2.7rem}.opener{font-size:1.2rem}}

/* why the range is wide — answered where the question is asked */
.whywide{margin:22px 0 4px;padding:18px 20px;background:var(--paper-2);
  border:1px solid var(--line-2);border-left:2px solid var(--accent);border-radius:5px}
.whywide h3{margin-bottom:7px}
.whywide p{margin:0 0 .7rem;font-size:.94rem;color:var(--ink-2)}
.whywide p:last-child{margin-bottom:0}


/* the three knowables */
.know{list-style:none;counter-reset:k;margin:16px 0 18px;padding:0}
.know li{counter-increment:k;position:relative;padding:13px 0 13px 34px;
  border-bottom:1px solid var(--line-2)}
.know li:before{content:counter(k);position:absolute;left:0;top:13px;width:21px;height:21px;
  border-radius:99px;background:var(--accent);color:#fff;font-size:.68rem;
  display:flex;align-items:center;justify-content:center}
.know .kt{display:block;font-weight:650;font-size:.95rem;margin-bottom:2px}
.know .kd{display:block;font-size:.92rem;color:var(--ink-2)}

footer{padding:44px 0 70px;border-top:1px solid var(--line-2);color:var(--muted);font-size:.85rem}

@media(min-width:760px){
  body{font-size:18px}
  h1{font-size:2.6rem} h2{font-size:2.15rem} h3{font-size:1rem} .addr{font-size:2.3rem}
  .split{grid-template-columns:1fr 1fr}
  .twotrue{grid-template-columns:1fr 1fr}
  section{padding:70px 0}
}
"""

JS = """
// ── in-page navigation: a glide, not a jump ────────────────────────────
// A native anchor jump teleports. There is no sense of travel, so the reader
// loses their place and has to rebuild the map of the page in their head.
// This animates the scroll with an ease that accelerates gently, carries, and
// decelerates long into the landing.
//
// Duration scales with DISTANCE — a short hop and a half-page move should not
// take the same time, or the short one feels sluggish and the long one feels
// thrown. Clamped so it never drags.
//
// prefers-reduced-motion is honoured: someone who has asked the OS for less
// motion gets the instant jump, which for them is the correct behaviour.
const reduceMotion = matchMedia('(prefers-reduced-motion: reduce)').matches;
function headerOffset(){
  const el=document.querySelector('header.top');
  return el ? el.getBoundingClientRect().height + 12 : 12;
}
function glideTo(target){
  const y = target.getBoundingClientRect().top + scrollY - headerOffset();
  const start = scrollY, dist = y - start;
  if (reduceMotion || Math.abs(dist) < 8){ scrollTo(0, y); return; }
  // ~0.55ms per pixel, floored at 480ms and capped at 1500ms.
  const dur = Math.min(1500, Math.max(480, Math.abs(dist) * 0.55));
  const t0 = performance.now();
  // easeInOutCubic — symmetric, no abrupt start, long soft landing.
  const ease = t => t < 0.5 ? 4*t*t*t : 1 - Math.pow(-2*t + 2, 3) / 2;
  let raf;
  const step = now => {
    const t = Math.min(1, (now - t0) / dur);
    scrollTo(0, start + dist * ease(t));
    if (t < 1) raf = requestAnimationFrame(step);
  };
  raf = requestAnimationFrame(step);
  // A wheel or touch during the glide cancels it — never fight the reader.
  const cancel = () => { cancelAnimationFrame(raf);
    removeEventListener('wheel', cancel); removeEventListener('touchstart', cancel); };
  addEventListener('wheel', cancel, {passive:true, once:true});
  addEventListener('touchstart', cancel, {passive:true, once:true});
}
document.addEventListener('click', e => {
  const a = e.target.closest('a[href^="#"]');
  if (!a) return;
  const id = a.getAttribute('href').slice(1);
  const target = id && document.getElementById(id);
  if (!target) return;
  e.preventDefault();
  glideTo(target);
  // Update the address bar without a second jump, so back/forward and sharing
  // still work.
  history.pushState(null, '', '#' + id);
});
// Arriving with a hash already in the URL should land the same way.
addEventListener('load', () => {
  if (location.hash.length > 1){
    const t = document.getElementById(location.hash.slice(1));
    if (t) setTimeout(() => glideTo(t), 60);
  }
});

const h=document.querySelector('header.top');
// Burger. Plain hidden/aria toggle — no library, no scroll lock: the brief asks
// for normal vertical scrolling and locking the page to open a menu is a small
// version of the scroll-jacking it rules out.
const bg=document.getElementById('burger'), mn=document.getElementById('menu');
if(bg&&mn){
  const setOpen=o=>{bg.setAttribute('aria-expanded',o?'true':'false');mn.hidden=!o;};
  bg.addEventListener('click',()=>setOpen(mn.hidden));
  mn.addEventListener('click',e=>{if(e.target.closest('a[href^="#"]'))setOpen(false);});
  addEventListener('keydown',e=>{if(e.key==='Escape')setOpen(false);});
}
addEventListener('scroll',()=>h.classList.toggle('stuck',scrollY>240),{passive:true});
// median chart scrubber — pointer events cover mouse and touch in one path.
document.querySelectorAll('.mchart').forEach(box=>{
  let pts; try{pts=JSON.parse(box.dataset.pts)}catch(e){return}
  if(!pts||!pts.length) return;
  const svg=box.querySelector('svg'), tip=box.querySelector('.mtip');
  const line=box.querySelector('.scrub'), dq=box.querySelector('.dotq'), dr=box.querySelector('.dotr');
  const W=+box.dataset.w, money=v=>'$'+Math.round(v).toLocaleString();
  const show=(clientX)=>{
    const r=svg.getBoundingClientRect();
    const vx=(clientX-r.left)/r.width*W;               // client px -> viewBox units
    let best=pts[0];
    for(const p of pts) if(Math.abs(p.x-vx)<Math.abs(best.x-vx)) best=p;
    line.setAttribute('x1',best.x); line.setAttribute('x2',best.x); line.setAttribute('opacity','.35');
    dq.setAttribute('cx',best.x); dq.setAttribute('cy',best.qy); dq.setAttribute('opacity','1');
    if(best.ry!=null){dr.setAttribute('cx',best.x);dr.setAttribute('cy',best.ry);dr.setAttribute('opacity','1');}
    else dr.setAttribute('opacity','0');
    tip.innerHTML='<b>'+best.q+'</b>'
      +'<span class="tq">Quarterly '+money(best.qv)+'</span>'
      +(best.rv!=null?'<span class="tr">12-month '+money(best.rv)+'</span>':'');
    tip.hidden=false;
    // Keep the tip inside the CARD. It is positioned against .mchart, which is
    // padded, so clamping against the SVG's own width let it hang off the right
    // edge — measure the offset rather than assuming they share an origin.
    const cr=box.getBoundingClientRect();
    const px=(r.left-cr.left)+best.x/W*r.width;
    const half=tip.offsetWidth/2;
    tip.style.left=Math.max(half+6,Math.min(cr.width-half-6,px))+'px';
  };
  const hide=()=>{tip.hidden=true;line.setAttribute('opacity','0');
    dq.setAttribute('opacity','0');dr.setAttribute('opacity','0');};
  svg.addEventListener('pointermove',e=>show(e.clientX));
  svg.addEventListener('pointerdown',e=>show(e.clientX));
  svg.addEventListener('pointerleave',hide);
  svg.addEventListener('pointercancel',hide);
});

// "See all N comparables"
document.querySelectorAll('.showall').forEach(b=>b.addEventListener('click',()=>{
  b.closest('.ecards').querySelectorAll('[data-extra]').forEach(el=>el.hidden=false);
  b.remove();
}));

// seasonality month tiles
document.querySelectorAll('.mcell').forEach(c=>c.addEventListener('click',()=>{
  const i=c.dataset.i;
  document.querySelectorAll('.mcell').forEach(x=>x.setAttribute('aria-pressed',x===c?'true':'false'));
  document.querySelectorAll('.mdet').forEach(d=>{d.hidden=d.dataset.i!==i;});
}));
document.querySelectorAll('.choice').forEach(b=>b.addEventListener('click',()=>{
  const g=b.closest('.choices');
  g.querySelectorAll('.choice').forEach(x=>x.setAttribute('aria-pressed','false'));
  b.setAttribute('aria-pressed','true');
  const r=g.parentElement.querySelector('.result');
  r.innerHTML=b.dataset.result; r.classList.add('on');
}));
"""


def render(slug, proto="full", version=LATEST):
    # A/B/C were build stages (spine -> +evidence -> +living), never reader-facing
    # variants. `full` is the whole flow as presented and is the default; the
    # stage flags remain only for isolating one layer during development.
    V = VERSIONS[version]
    B = proto in ("b", "c", "full")   # deeper evidence
    C = proto in ("c", "full")        # living page
    b = json.loads((A.BUNDLE_DIR / f"{slug}.json").read_text())
    gc = get_mongo_client()["Gold_Coast"]
    doc = gc[b["suburb_key"]].find_one({"address": b["address"]}) or {}
    vd = doc.get("valuation_data") or {}
    adj = [c for c in (vd.get("adjusted_comparables") or []) if c.get("adjusted_price")]
    adj.sort(key=lambda c: abs((c.get("adjusted_price") or 0) - (b.get("valuation") or {}).get("point", 0)))

    # The emitter already builds `gain` and `buyer` from this bundle. Import them
    # rather than re-deriving: two implementations of the same section is how the
    # page and the emitter end up disagreeing about the same home.
    try:
        import emit_v4
        _cards = {c["type"]: c for c in emit_v4.emit_v4(slug)["cards"]}
    except Exception:
        _cards = {}

    # The SAME payload the mini-site's ValuationEvidence consumes. Resolver
    # output, no recomputation — proven to work unchanged on off-market docs.
    try:
        sys.path.insert(0, os.path.join(ORCH_ROOT, "scripts"))
        from property_reports.slot_resolver import SlotResolver
        _r = SlotResolver({"suburb_key": b["suburb_key"], "suburb": b.get("suburb_display", ""),
                           "address": b["address"], "property_id": doc.get("_id")},
                          get_mongo_client()["Gold_Coast"])
        _r._subject = doc
        EV = _r.valuation_evidence_from_engine() or {}
    except Exception:
        EV = {}

    # ⚠ THE LIVE VALUATION WINS OVER THE BUNDLE'S.
    #
    # Bundles are cached, and most were built before the off-market book was
    # valued — so their `valuation` fell through to `exterior_evidence` and has
    # stayed there. Meanwhile the document now carries a high-confidence engine
    # range. The page was therefore printing a stale fallback range at the top
    # while rendering ENGINE comparables underneath it:
    #     11 Placid   bundle $1,462,626-$2,061,774   live $1,470,491-$1,871,534
    #     3 Fimiston  bundle $1,736,360-$2,447,640   live $1,607,377-$2,045,752
    # $400k apart at the top end on Fimiston, and the number disagreed with its
    # own evidence. The nightly rebuild would eventually correct the bundles;
    # reading the authoritative source means it does not have to.
    s, v = b.get("subject") or {}, b.get("valuation") or {}
    _live = ((doc.get("valuation_data") or {}).get("confidence") or {})
    _lr = _live.get("range") or {}
    if _lr.get("low") and _lr.get("high") and _live.get("reconciled_valuation"):
        v = {**v, "low": _lr["low"], "high": _lr["high"],
             "point": _live["reconciled_valuation"], "method": "engine",
             "confidence": _live.get("confidence"),
             "n_comps": _live.get("n_total") or v.get("n_comps")}
        b["valuation"] = v
    cred, oc = b.get("credibility") or {}, b.get("obvious_comp") or {}
    sc, poi = b.get("scarcity") or {}, b.get("poi_rarity") or {}
    # ⚠ The error rate describes the COMPARABLE-SALES ENGINE only. When a home
    # falls outside the $1M-$2M design envelope the engine declines and the
    # bundle falls through to `exterior_evidence` / `thin` — different methods
    # whose accuracy we have never measured. Showing 11.2% beside an
    # exterior-evidence range lends an unmeasured method someone else's track
    # record. Caught on 30 Whitehead Drive, which did exactly that; same defect
    # as [ERROR-RATE-METHOD-MISMATCH] in emit_v4.
    method = (b.get("valuation") or {}).get("method")
    acc = ACCURACY.get(b["suburb_key"]) if method == "engine" else None
    short = b.get("address_short") or b["address"].split(",")[0]

    P = []
    add = P.append

    # ── header ──
    # Header is composed AFTER the body, so the section menu can be built from the
    # sections that actually rendered. Hard-coding the list would leave dead links
    # pointing at blocks that omitted themselves on a thin property.
    header_placeholder = "<!--HEADER-->"
    add(header_placeholder)

    # ── 1 · recognition ─────────────────────────────────────────────
    add('<section class="hero"><div class="wrap">')
    add('<div class="eyebrow">Private property report · Updated today</div>')
    img = hero_image(doc, b["suburb_key"], slug)
    if img:
        add(f'<img class="shot" src="{E(img)}" alt="Aerial view of {E(short)} with its '
            f'title boundary marked" loading="eager">')
        poly = doc.get("cadastral_polygon") or {}
        area = poly.get("lot_area_sqm")
        add('<div class="fine" style="margin-top:6px">Title boundary from the Queensland cadastre'
            + (f' — lot {E(str(poly.get("lotplan")))}, {area:,.0f} m²' if area else '')
            + '. Aerial imagery · Google</div>')
    add(f'<div class="addr">{E(short)}</div>')
    add(f'<div class="sub">{E(b.get("suburb_display",""))}, QLD</div>')

    bits = []
    if s.get("land_sqm"):
        bits.append(f'<span><b>{int(s["land_sqm"])}</b> m² land</span>')
    if s.get("bedrooms"):
        bits.append(f'<span><b>{int(s["bedrooms"])}</b> bedrooms</span>')
    # Rendered only when known. Bathrooms is our biggest attribute gap, and the
    # correction section further down asks the owner for exactly this — so an
    # invented or zero value here would contradict the page asking for it.
    if s.get("bathrooms"):
        bits.append(f'<span><b>{int(s["bathrooms"])}</b> bathrooms</span>')
    if s.get("floor_sqm"):
        bits.append(f'<span><b>{int(s["floor_sqm"])}</b> m² floor</span>')
    if s.get("pool"):
        bits.append("<span>pool</span>")
    if bits:
        add(f'<div class="facts">{"".join(bits)}</div>')

    # last recorded sale — never assume the reader bought it
    tl = [e for e in ((doc.get("scraped_data") or {}).get("property_timeline") or [])
          if str(e.get("category", "")).lower() == "sale" and e.get("price")]
    tl.sort(key=lambda e: str(e.get("date") or ""), reverse=True)
    if tl:
        from datetime import datetime
        try:
            when = datetime.fromisoformat(str(tl[0]["date"])[:10]).strftime("%B %Y")
        except Exception:
            when = str(tl[0]["date"])[:7]
        add(f'<p style="margin-top:16px" class="fine">Last recorded sale: '
            f'<b>{E(exact(tl[0]["price"]))}</b> in {E(when)}. No later market sale is recorded.</p>')
        # The ten-year movement belongs BESIDE the fact that provokes the
        # question, not two acts later as a section of its own. Act II then
        # opens on the present, which is what its heading promises.
        _g = _cards.get("gain") or {}
        if _g.get("ten_year") or _g.get("cannot_reach"):
            add('<details class="disc"><summary>See what has happened since</summary>'
                '<div class="body">')
            if _g.get("cannot_reach"):
                add(f'<p class="fine">{E(str(_g["cannot_reach"]).strip())}</p>')
            if _g.get("since"):
                add(f'<p>{E(str(_g["since"]).strip())}</p>')
            if _g.get("ten_year"):
                add(f'<p>{E(str(_g["ten_year"]).strip())}</p>')
            if _g.get("means"):
                add(f'<p class="fine">{E(str(_g["means"]).strip())}</p>')
            add('</div></details>')

    pre = V.get("preamble") or {}
    if pre.get("opener"):
        add(f'<p class="opener">{E(pre["opener"])}</p>')
        add(f'<h1 class="hookq">{E(pre["heading"])}</h1>')
    elif V.get("questions_intro"):
        add(f'<p class="lede" style="margin-top:26px">{E(V["questions_intro"])}</p>')
        add('<ul class="qs">' + "".join(f'<li>{E(q)}</li>' for q in V["questions"]) + '</ul>')
    if V.get("promise"):
        add(f'<div class="promise">{E(V["promise"])}</div>')
    add('</div></section>')

    # ── preamble · the two-portals problem, before any number of ours ────
    # Named BEFORE the range so the reader meets our figure already knowing the
    # question is "which sales, and what was changed" rather than "which number
    # is bigger". Without it our range is just a third unexplained number.
    pre = V.get("preamble")
    if pre:
        add('<section id="which"><div class="wrap">')
        add('<div class="eyebrow">Why the numbers disagree</div>')
        if not pre.get("opener"):
            add(f'<h2>{E(pre["heading"])}</h2>')
        for i, para in enumerate(pre["paras"]):
            # First para sets up the problem; the LAST one is the promise the
            # rest of the page has to keep, so it carries the emphasis. Styled
            # by class rather than markup in the copy, so the strings in
            # VERSIONS stay plain text and keep being escaped.
            cls = ' class="lede"' if i == 0 else (
                ' class="promiseline"' if i == len(pre["paras"]) - 1 else "")
            add(f'<p{cls}>{E(para)}</p>')
        add('<a class="cue" href="#answer">See what the sales support ↓</a>')
        add('</div></section>')
    else:
        # v1 carried the forward cue on the hero itself.
        P[-1] = P[-1].replace('</div></section>',
                              '<a class="cue" href="#answer">See what the sales support ↓</a>'
                              '</div></section>')

    # ── 2 · the answer ──────────────────────────────────────────────
    if v.get("low") and v.get("high"):
        add('<section id="answer"><div class="wrap">')
        add('<div class="eyebrow">The answer</div>')
        add('<h2>What the sales around this home support</h2>')
        add('<div class="answer">')
        add('<div class="rangeline"><i></i></div>')
        add(f'<div class="rangefig"><span>{E(money(v["low"]))}</span>'
            f'<em>–</em><span>{E(money(v["high"]))}</span></div>')
        if v.get("point"):
            rounded = round(v["point"] / 50_000) * 50_000
            add(f'<p class="centre">The evidence centres around <b>approximately '
                f'{E(money(rounded))}</b> — rounded deliberately, because the width is the honest part.</p>')
        # ⚠ "N relevant sales influenced the range" is only TRUE when the engine
        # built it. On a fallback range that sentence, sitting two screens above
        # "this range was not built by our comparable-sales method", is a flat
        # contradiction — and the credibility of the whole page rests on
        # sentences like this one being exact.
        # ⚠ Must match the method exactly. Since 2026-08-08 the estimate is
        # computed from the WHOLE candidate pool and the eight shown are a
        # display choice — saying they "carried most of the weight" would be a
        # description of the old method, and the credibility of this page rests
        # on sentences like this one being literally true.
        if v.get("n_comps") and adj and acc:
            add(f'<p class="basis fine">Built from all {v["n_comps"]} comparable sales we hold for '
                f'this home \u2014 not a hand-picked few. The {len(adj)} closest are shown below.</p>')
        elif not acc:
            add('<p class="basis fine">This home sits outside the band our tested '
                'comparable-sales model operates in, so this is a broader evidence range rather '
                'than that model\'s output. The strongest nearby sales are still below \u2014 '
                'what we cannot responsibly do is attach our measured error rate to it.</p>')
        # ⚠ The honest reason, and it is not property-specific: the width is an
        # EMPIRICAL 80% BAND, measured per suburb — four in five tested sales
        # landed inside a range built this way. It is not a confidence interval
        # and must never be called one. Inventing a bespoke reason per property
        # would be a better story and a false one. What IS property-specific is
        # the list of things we could not see, so both are said.
        add('<div class="whywide">')
        add('<h3>Why is the range this wide?</h3>')
        if acc:
            add(f'<p>The width is not a style choice. We set it by testing this method against '
                f'{acc["n"]} {E(b.get("suburb_display",""))} houses that later sold, and widening '
                f'the range until four in five of them landed inside it. '
                f'<b>It is as narrow as the evidence earns.</b></p>')
            add('<p>Narrowing it further would not make the estimate better. It would only make '
                'the claim less true.</p>')
        else:
            add('<p>Because this range was not built from close comparable sales. It is drawn '
                'from what can be verified from the outside, which is a wider kind of evidence.</p>')
        # ⚠ Two DIFFERENT kinds of not-knowing, and merging them reads as a
        # category error: condition is something nobody can see from the street,
        # a bathroom count is a fact simply missing from the record. Said
        # separately, and the second only when it is actually missing.
        add('<p>Public records tell us a great deal about this home. What they cannot tell us is '
            'its current internal condition or the quality of any renovation \u2014 and those move '
            'the result materially. Until someone has seen them, this is the honest width.</p>')
        gaps = [str(g).replace(" unknown", "").strip() for g in (b.get("gaps") or [])
                if "unknown" in str(g)]
        if gaps:
            listed = (", ".join(gaps[:-1]) + " and " + gaps[-1]) if len(gaps) > 1 else gaps[0]
            add(f'<p>We are also missing {E(listed)} from the record for this address \u2014 which '
                f'you can correct further down.</p>')
        # ⚠ The closing line must match the method. On a fallback range the sales
        # did NOT pull the answer anywhere, and saying they did rebuilds the very
        # contradiction fixed an hour ago, in new words.
        if acc:
            add('<p class="fine">What we can do is show you exactly which sales pulled the answer '
                'to where it sits.</p>')
        else:
            add('<p class="fine">What we can still do is show you the strongest sales near this '
                'home, and what each one adjusts to.</p>')
        add('</div>')
        if acc:
            add('<div class="controls"><a class="btn" href="#comps">See the strongest '
                'comparisons</a><a class="btn" href="#reliable">How reliable has this been?</a>'
                '</div>')
        else:
            # No measured rate for the method that produced this range — say so
            # HERE, against the number, rather than as a section of its own.
            add('<div class="controls"><a class="btn" href="#comps">See the strongest '
                'comparisons</a></div>')
            add('<details class="disc"><summary>How reliable is this?</summary><div class="body">'
                '<p>This range was not built by our comparable-sales method. The home sits outside '
                'the band that method was built for \u2014 detached houses between $1,000,000 and '
                '$2,000,000 \u2014 so we have used a wider approach based on what can be verified '
                'from the outside.</p>'
                '<p>We publish a measured error rate for the comparable-sales method. We do not '
                'have one for this approach, so we are not quoting a number we have not earned.</p>'
                '<p class="fine">The comparable sales further down are unchanged. They are the '
                'part we can stand behind either way.</p></div></details>')
        add('</div>')
        add('<a class="cue" href="#nearby">First, one sale nearby is worth looking at ↓</a>')
        add('</div></section>')

    # ── 3 · the surprising nearby sale ──────────────────────────────
    if oc.get("address") and oc.get("price"):
        # what that sale adjusts to for THIS home
        match = next((c for c in adj if str(oc["address"]).split(",")[0].lower()
                      in str(c.get("address", "")).lower()), None)
        add('<section id="nearby"><div class="wrap">')
        add('<div class="eyebrow">The sale up the road</div>')
        add(f'<h2>That {E(money(oc["price"]))} sale is not this home\'s answer</h2>')
        add('<div class="split">')
        add(f'<div><div class="k">Nearby sale</div><div class="a">{E(oc["address"])}</div>'
            f'<div class="p">{E(exact(oc["price"]))}</div>'
            f'<div class="fine">{int(oc["distance_m"])} metres away</div></div>'
            if oc.get("distance_m") else
            f'<div><div class="k">Nearby sale</div><div class="a">{E(oc["address"])}</div>'
            f'<div class="p">{E(exact(oc["price"]))}</div></div>')
        deltas = "".join(f'<div class="fine">{E(d)}</div>' for d in (oc.get("deltas") or []))
        add(f'<div><div class="k">This home</div><div class="a">{E(short)}</div>{deltas}</div>')
        add('</div>')
        if match:
            add(f'<div class="move">{E(exact(oc["price"]))}<span class="arrow">──→</span>'
                f'<span class="to">about {E(money(match["adjusted_price"]))} adjusted</span></div>')
        add('<p>It is still evidence — it sits in the set below. But once the differences are '
            'accounted for, the headline price is not the number that transfers to this home.</p>')
        add('<p class="lede">Same area. Different home. The headline price was never the whole comparison.</p>')
        if match and match.get("adjustments"):
            add('<details><summary>See exactly what changed</summary><div class="body">')
            add(adjustment_rows(match))
            add('</div></details>')
        add('<a class="cue" href="#comps">See the strongest sales ↓</a>')
        add('</div></section>')

    # ── 4 · the comparable evidence ─────────────────────────────────
    if adj:
        add('<section id="comps"><div class="wrap">')
        add('<div class="eyebrow">The evidence</div>')
        add('<h2>' + ('The sales behind that range' if acc else
                      'The strongest sales near this home') + '</h2>')
        # ⚠ Only promise the tap when the rich cards actually render. Outside the
        # design envelope the resolver returns None (no reconciled range), the
        # page falls back to simple cards with nothing to expand, and this line
        # would be a promise the page does not keep.
        if EV.get("comparables"):
            add('<p class="fine">Each sale below is adjusted to this home for the ways it differs. '
                'Tap any one for the line-by-line working and why it carries the weight it does.</p>')
        else:
            add('<p class="fine">Each sale below is adjusted to this home for the ways it '
                'differs.</p>')
        add('<div class="funnel">')
        steps = []
        if cred.get("sales_reviewed"):
            steps.append(f'{cred["sales_reviewed"]:,} recent sales searched')
        if v.get("n_comps"):
            steps.append(f'{v["n_comps"]} relevant sales retained')
        steps.append(f'{len(adj)} strongest comparisons shown')
        for i, st in enumerate(steps):
            add(f'<div class="row{" last" if i == len(steps)-1 else ""}">{E(st)}</div>')
            if i < len(steps) - 1:
                add('<div class="drop">↓</div>')
        add('</div>')
        if cred.get("characteristics"):
            add(f'<p class="fine">{cred["characteristics"]} property characteristics were '
                f'considered when comparing them.'
                + ('' if acc else ' These sales inform the picture; they did not generate the '
                                  'range above.')
                + '</p>')
        oc_addr = str((b.get("obvious_comp") or {}).get("address") or "").split(",")[0].lower()
        fresh = [c for c in adj if oc_addr not in str(c.get("address", "")).lower()] if oc_addr else adj
        cards = evidence_cards(EV)
        if cards:
            add(cards)
        else:
            for c in fresh[:3]:
                add('<div class="comp">')
                add(f'<div class="a">{E(str(c.get("address","")).split(",")[0])}</div>')
                add(f'<div class="adj"><span class="lab">Adjusted position</span>'
                    f'<span class="val">about {E(money(c["adjusted_price"]))}</span></div>')
                add('</div>')
        add('<p style="margin-top:20px">No sale is a match. Each one differs from this home in ways '
            'that are worth money, so we price those differences rather than averaging past them.</p>')

        # The mirror of the cards above: not why a headline price does not
        # transfer, but why a nearby sale is not in the set at all. It is
        # SUPPORTING evidence for the comparables, so it sits with them as a
        # disclosure — as its own section it carried the same visual weight as
        # the range itself and interrupted the run from evidence into what makes
        # this home different.
        exc = excluded_sale(doc.get("valuation_data") or {})
        if exc:
            add('<details class="disc"><summary>And the sale we left out</summary>'
                '<div class="body">')
            meta = E(exc["address"])
            if exc.get("distance_km"):
                meta += f' \u2014 {exc["distance_km"]:.1f} km away'
            add(f'<div class="anchor" style="margin-bottom:6px">'
                f'{E(exact(exc["price"]))}</div>')
            add(f'<div class="fine" style="margin-bottom:10px">{meta}</div>')
            add('<p>It is a real sale, and it is close enough that you would notice it. It was '
                'considered and left out.</p>')
            if exc["reasons"]:
                add('<div class="label">Why</div>')
                add('<ul class="ticks">' + "".join(f'<li>{E(r)}</li>' for r in exc["reasons"])
                    + '</ul>')
            add('<p class="fine">Leaving it in would have pulled the range toward a home this one '
                'is not \u2014 the same judgement working in reverse when a low sale is left out, '
                'and why the number of sales behind a range matters less than which ones.</p>')
            add('</div></details>')
        add('<div class="src">Fields analysis of Queensland sales records · Government record</div>')
        add('<a class="cue" href="#different">So what makes this one different? ↓</a>')
        add('</div></section>')

    # ── 6 · how reliable ────────────────────────────────────────────
    # A SECTION only when there is a measured error rate to show — the figure,
    # the scale and the full test are main-path content and one of the brief's
    # eight moments. Without one there is nothing but a caveat, and a caveat
    # promoted to its own section reads as more important than the number it
    # qualifies. Outside the design envelope it is rendered beside the range
    # instead (see the valuation section).
    if acc:
        add('<section id="reliable"><div class="wrap">')
        add('<div class="eyebrow">Reliability</div>')
        add('<h2>How wrong has this method been?</h2>')
        add(f'<div class="bigfig">{acc["mae"]}%</div>')
        add(f'<p>Tested against {acc["n"]} {E(b.get("suburb_display",""))} houses in this price range '
            f'that later sold, the centre of the estimate was out by <b>{acc["mae"]}% on average</b>. '
            f'Half the time it was within {acc["median"]}%, and it landed within 10% of the eventual '
            f'sale price on {acc["within10"]}% of homes.</p>')
        add('<p>That is why this page shows a range rather than pretending the evidence supports one '
            'exact number.</p>')
        if v.get("low") and v.get("high"):
            add('<div class="scale"><div class="fine">Where the eventual sale landed, in testing</div>'
                '<div class="bar"><span class="band" style="left:22%;right:22%"></span>'
                '<span class="tick" style="left:50%"></span></div>'
                f'<div class="lbl"><span>{E(money(v["low"]))}</span>'
                f'<span>{E(money(v["high"]))}</span></div>'
                f'<div class="fine" style="margin-top:12px">The sale price fell inside a range built '
                f'this way <b>{acc["contain"]}% of the time</b> \u2014 which is what the width is '
                f'chosen to deliver. It is not a statistical confidence interval, and we do not '
                f'describe it as one.</div></div>')
        add('<details><summary>See the full test</summary><div class="body">')
        add(f'<p>Leave-one-out test on {acc["n"]} detached houses in {E(b.get("suburb_display",""))} '
            f'that sold between $1,000,000 and $2,000,000 — the band this method is built for. '
            f'Each home was valued using only sales that had settled before it, and its own sale was '
            f'never used.</p>')
        add(f'<div style="display:flex;justify-content:space-between;padding:6px 0;border-bottom:1px solid var(--line-2)">'
            f'<span>Average miss (mean absolute error)</span><span>{acc["mae"]}%</span></div>')
        add(f'<div style="display:flex;justify-content:space-between;padding:6px 0;border-bottom:1px solid var(--line-2)">'
            f'<span>Half the time within</span><span>{acc["median"]}%</span></div>')
        add(f'<div style="display:flex;justify-content:space-between;padding:6px 0;border-bottom:1px solid var(--line-2)">'
            f'<span>Within 10% of the sale price</span><span>{acc["within10"]}% of homes</span></div>')
        add(f'<div style="display:flex;justify-content:space-between;padding:6px 0;border-bottom:1px solid var(--line-2)">'
            f'<span>Sale fell inside the published range</span><span>{acc["contain"]}%</span></div>')
        add(f'<div style="display:flex;justify-content:space-between;padding:6px 0">'
            f'<span>Published range width</span><span>\u00b1{acc["band"]}%</span></div>')
        add('<p class="fine" style="margin-top:14px">Those homes sold, which this one has not — so '
            'treat it as the method\'s track record, not a promise about this address.</p>')
        add('</div></details>')
        add('<div class="src">Fields analysis \u00b7 tested 8 August 2026</div>')
        add('</div></section>')

    # ── 6b · why the other estimates disagree (Prototype B) ─────────
    if B:
        add('<section id="dispersion"><div class="wrap">')
        add('<div class="eyebrow">The other numbers</div>')
        add('<h2>Why the other estimates say something different</h2>')
        add('<p>The trouble with using only three sales is that the answer becomes highly '
            'sensitive to which three are chosen.</p>')
        add('<p>We took 512 homes that have since sold, found every set of three comparable sales '
            'that could reasonably have been chosen, and worked out what each set said.</p>')
        add('<div class="finding">The median gap between the highest and lowest defensible result '
            'was $469,000.</div>')
        add('<p>That does not make any one estimate dishonest. It means three sales are often too '
            'small a sample to show which comparison deserves the most weight.</p>')
        add('<details><summary>See what the test found</summary><div class="body">'
            '<p>A close answer was present in the available evidence on 73.6% of those homes — '
            'identifiable only with hindsight. The worst available choice was more than 20% out '
            'on 73.4%.</p>'
            '<p>Three sales is not a figure we picked to make a point: it is the statutory '
            'Statement of Information standard in Victoria and in the incoming New South Wales '
            'regime.</p>'
            '<p class="fine">This is a property of the three-sale method, measured on our own data. '
            'It is not a claim about any particular provider, and we have not tested anyone '
            'else\'s figures.</p></div></details>')
        add('<div class="src">Fields analysis · n=512 · tested 6 August 2026</div>')
        add('</div></section>')

    # ── 5 · what makes this home different ──────────────────────────
    if sc.get("active_matching") and sc.get("active_total"):
        add('<section id="different"><div class="wrap">')
        add('<div class="eyebrow">This home</div>')
        # ⚠ Was assembled by string-joining anchors — "4 bedrooms and 914 m² of
        # land and 255 m² of internal living and a pool do not appear together
        # often." Machine-like, in the section that should be one of Act II's
        # moments of recognition. Written as a sentence, with the counts doing
        # the persuading rather than adjectives.
        add("<h2>It isn't any one feature. It's the combination.</h2>")
        feat = []
        if s.get("bedrooms"):
            feat.append(f'{int(s["bedrooms"])} bedrooms')
        if s.get("land_sqm"):
            feat.append(f'a {int(s["land_sqm"])} m\u00b2 block')
        if s.get("floor_sqm"):
            feat.append(f'around {int(s["floor_sqm"])} m\u00b2 of internal space')
        if s.get("pool"):
            feat.append('a pool')
        if len(feat) > 1:
            lead = feat[0]
            add(f'<p class="lede">{E(lead[0].upper() + lead[1:])} is common enough here'
                + ('. So is a pool' if s.get("pool") else '')
                + '. But put ' + E(", ".join(feat[:-1])) + ' and ' + E(feat[-1])
                + ' together, and the field gets much smaller.</p>')

        # The counts do the work the adjectives used to.
        cl = (poi.get("cluster") or {})
        feats = poi.get("features") or []
        line = (f'Of the {sc["active_total"]} homes on the market across the comparison area, '
                f'{sc["active_matching"]} broadly match that combination.')
        if cl.get("matching") and feats:
            names = (", ".join(f["short"] for f in feats[:-1]) + " and " + feats[-1]["short"]
                     if len(feats) > 1 else feats[0]["short"])
            line += (f' Only {cl["matching"]} also sit this close to {names}.')
        add(f'<p>{E(line)}</p>')
        add('<p class="fine">That does not set a price by itself. It reduces the number of close '
            'substitutes a buyer can choose from.</p>')
        if B:
            mp, n_pins = scarcity_map(doc, b, slug)
            if mp:
                add(f'<img class="shot" style="aspect-ratio:16/10;margin:20px 0 6px" src="{E(mp)}" '
                    f'alt="Homes sharing this combination near {E(short)}" loading="lazy">')
                add(f'<div class="fine">This home in yellow; the {n_pins} homes currently on the '
                    f'market that share the combination in grey. How far a buyer would have to go '
                    f'to find a substitute. Mapping \u00b7 Google</div>')
        if feats:
            add('<details><summary>See the distances</summary><div class="body">')
            for f in feats:
                add(f'<div style="display:flex;justify-content:space-between;padding:6px 0;'
                    f'border-bottom:1px solid var(--line-2)"><span>{E(f["label"])}</span>'
                    f'<span>{int(f["distance_m"])}m</span></div>')
            add('</div></details>')
        add('<a class="cue" href="#reliable">So how wrong could you be? ↓</a>')
        add('</div></section>')

    # ── 7b · is now the right time? ─────────────────────────────────
    if mkt_for_timing := ((get_mongo_client()["system_monitor"]["market_pulse"]
                           .find_one({"suburb": b["suburb_key"]}) or {}).get("data_snapshot") or {}):
        add('<section id="timing"><div class="wrap">')
        add('<div class="eyebrow">The honest answer</div>')
        add('<h2>Is now the right time to be selling, or should I wait?</h2>')
        lede, knowables = timing_answer(b.get("suburb_display", ""), mkt_for_timing)
        add(f'<p class="lede">{E(lede)}</p>')
        add('<p>Three things you can know right now, without a forecast:</p>')
        add('<ol class="know">')
        for title, detail in knowables:
            add(f'<li><span class="kt">{E(title)}</span><span class="kd">{E(detail)}</span></li>')
        add('</ol>')
        add('<p>The third can matter more to the decision than a small movement in a national '
            'index \u2014 and it is usually treated separately from your home\'s value online.</p>')

        # Everything that PROVES the above, for a reader who wants to check it.
        add('<details class="disc"><summary>What forecasters currently think</summary>'
            '<div class="body">'
            '<p>In July, Westpac was tipping two more rate rises; by the end of the month it had '
            'withdrawn that call, and all four major banks now expect the Reserve Bank to hold. '
            'National figures show home values falling for three consecutive months \u2014 though '
            'Brisbane is close to flat rather than falling, and the Gold Coast is a different '
            'market again.</p>'
            '<p class="fine">Reported, not adopted. We hold no view on what the Reserve Bank will '
            'do.</p></div></details>')

        add('<details class="disc"><summary>What the median has done in '
            + E(b.get("suburb_display", "")) + '</summary><div class="body">')
        add(median_block(b.get("suburb_display", ""), mkt_for_timing))
        add('</div></details>')

        add('<details class="disc"><summary>Does the month you list in matter?</summary>'
            '<div class="body">')
        add(seasonality_strip())
        add('</div></details>')

        add('<div class="src">Fields analysis of Gold Coast sale records \u00b7 rate and national '
            'price figures as reported by the RBA, Westpac and Cotality</div>')
        add('<a class="cue" href="#now">What\'s moving around this home right now? \u2193</a>')
        add('</div></section>')

    # ── 8 · what is changing now ────────────────────────────────────
    mkt = ((get_mongo_client()["system_monitor"]["market_pulse"]
            .find_one({"suburb": b["suburb_key"]}) or {}).get("data_snapshot") or {})
    comp = b.get("competition") or {}
    if comp.get("n_compete") or mkt:
        add('<section id="now"><div class="wrap">')
        add('<div class="eyebrow">Right now</div>')
        add('<h2>What is moving around this home</h2>')
        rep = (get_mongo_client()["system_monitor"]["property_reports"]
               .find_one({"slug": slug}) or {})
        actives = ((rep.get("comparables") or {}).get("closest_active") or [])
        # ⚠ Two counts of "competing homes" appear on this page and they are
        # measured differently — the section above counts homes sharing the
        # feature COMBINATION, this one counts homes a buyer would actually
        # shortlist at this price today. Stated bare, one reads as contradicting
        # the other. So this sentence names the relationship rather than
        # dropping a second, smaller number on the reader.
        if comp.get("n_compete"):
            nc = comp["n_compete"]
            _m = sc.get("active_matching")
            if _m and _m > nc:
                add(f'<p>Of those {_m}, <b>{nc}</b> {"is" if nc == 1 else "are"} priced where a '
                    f'buyer looking at this home would actually be choosing between them today.</p>')
            else:
                add(f'<p>{nc} {"home" if nc == 1 else "homes"} a buyer could compare with this one '
                    f'if it came to market today, from {comp.get("n_total", "-")} on the market '
                    f'across the wider comparison catchment.</p>')
        if C and actives:
            ap_ = (rep.get("comparables") or {}).get("aperture_label")
            if ap_:
                add(f'<p class="fine">Comparison set: {E(str(ap_))}. Some sit outside '
                    f'{E(b.get("suburb_display",""))} — that is the catchment a buyer at this price '
                    f'actually shops across, not a suburb boundary.</p>')
            add('<div class="rail">')
            for a_ in actives[:4]:
                add('<article class="lcard">')
                if a_.get("image_src"):
                    add(f'<img src="{E(str(a_["image_src"]))}" alt="" loading="lazy">')
                add(f'<div class="b"><div class="a">{E(str(a_.get("address","")))}</div>')
                meta = [x for x in [a_.get("suburb"),
                                    f'{a_["bedrooms"]} bed' if a_.get("bedrooms") else None,
                                    f'{a_["distance_km"]:.1f} km away' if a_.get("distance_km") else None]
                        if x]
                add(f'<div class="fine">{E(" · ".join(str(m) for m in meta))}</div>')
                if a_.get("price"):
                    add(f'<div class="pr">{E(str(a_["price"]))}</div>')
                dom_ = a_.get("days_on_market")
                if dom_:
                    fresh_ = dom_ <= 14
                    add(f'<div class="pill{" hot" if fresh_ else ""}">'
                        + ("New this week" if dom_ <= 7 else f"Listed {int(dom_)} days ago") + '</div>')
                if a_.get("difference_vs_subject"):
                    add(f'<div class="fine" style="margin-top:8px">{E(str(a_["difference_vs_subject"]))}</div>')
                add('</div></article>')
            add('</div>')
        # ⚠ REMOVED 2026-08-07: this block restated days-on-market and active
        # listings under "Two true things point in different directions" —
        # hardcoded to that framing. For Varsity Lakes and Robina both readings
        # move the SAME way, so the page asserted "they support opposite
        # conclusions" two screens after the timing section correctly said "both
        # readings moved the same way", about the identical numbers. One page,
        # two contradictory readings of one fact.
        #
        # `timing_answer()` owns that pair now and derives the direction per
        # suburb. This section is about the COMPETITOR SET specifically, which
        # is its distinct job.
        if C:
            acts = [a for a in (rep.get("activity") or []) if timeline_safe(a)]
            if acts:
                add('<h3 style="margin-top:32px">What changed recently</h3>')
                add('<ol class="tl">')
                for a_ in acts[:6]:
                    add(f'<li><span class="d">{E(month_year(a_.get("date")) or "")}</span>'
                        f'<div class="h">{E(str(a_.get("headline","")))}</div>'
                        + (f'<div class="fine">{E(str(a_["detail"]))}</div>' if a_.get("detail") else '')
                        + '</li>')
                add('</ol>')
                when = rep.get("comparables_refreshed_at") or rep.get("activity_refreshed_at")
                if when:
                    add(f'<div class="fine">Competitor set re-checked nightly · last checked '
                        f'{E(full_date(when))}</div>')
            # ⚠ SIMULATED. There is no visitor identity on this page yet, and the
            # device_token defect means a submission would be silently discarded.
            # Shown so the CONCEPT can be judged; labelled so it is never mistaken
            # for working plumbing.
            add('<div class="sim">')
            add('<div class="simtag">Concept — not wired</div>')
            add('<h3>Since you last looked</h3>')
            add('<p>On a return visit this is where the page would open: what moved since the last '
                'time this address was viewed, rather than making someone re-read what they have '
                'already seen.</p>')
            add('<ul class="ticks"><li>One new home came to market in the comparison set</li>'
                '<li>One asking price changed</li>'
                '<li>The range did not move</li></ul>')
            add('<p class="fine">Requires a visitor token this page does not yet issue. Nothing '
                'here is stored today.</p>')
            add('</div>')
        add('<div class="src">Fields analysis of active listings · re-checked nightly</div>')
        add('<a class="cue" href="#correct">What if something here is wrong? ↓</a>')
        add('</div></section>')

    # ── 9 · who would actually want it ──────────────────────────────
    by = _cards.get("buyer") or {}
    bb = b.get("buyer") or {}
    vd_ = b.get("value_drivers") or {}
    if bb.get("headline") or by.get("fit"):
        add('<section id="buyer"><div class="wrap">')
        add('<div class="eyebrow">The buyer</div>')
        # ⚠ The engine's headline reads as fact ("Local family upgraders carry
        # the price"). Without buyer-origin data that is an assertion, and it is
        # noticeably more promotional than everything around it. Framed as what
        # it is: one group likely to value this more than average.
        add('<h2>One buyer group likely to value this combination more than average</h2>')
        # ⚠ Softening the HEADING was not enough — the engine's own line
        # ("Local family upgraders carry the price") still printed underneath it
        # as a flat assertion, which is the thing that was wrong. We hold no
        # buyer-origin data: this is inferred from what the home has and what the
        # comparable sales show buyers paying for. Say so, once, before it.
        if bb.get("headline") or bb.get("body"):
            add('<p class="fine">We have no data on who is actually buying in this street. '
                'What follows is inferred from this home\u2019s features and what the sales '
                'above show buyers paying more for.</p>')
        # The honesty line above already frames everything after it as inference,
        # so the engine's sentence can stand as written. An earlier attempt spliced
        # it into a longer clause and produced "the group most likely to stretch
        # for this home is the one for whom local family upgraders carry the
        # price" — grammatical mush. Frame once, then quote plainly.
        if bb.get("headline"):
            add(f'<p class="lede">{E(str(bb["headline"]).rstrip("."))}.</p>')
        if bb.get("body"):
            add(f'<p class="lede">{E(str(bb["body"]).strip())}</p>')
        carries, attracts = vd_.get("carries_price") or [], vd_.get("attracts_buyer") or []
        if carries or attracts:
            add('<div class="drivers">')
            if carries:
                add('<div class="drv"><div class="label">What carries the price</div><ul>'
                    + "".join(f'<li>{E(str(x))}</li>' for x in carries) + '</ul></div>')
            if attracts:
                add('<div class="drv"><div class="label">What draws them in</div><ul>'
                    + "".join(f'<li>{E(str(x))}</li>' for x in attracts) + '</ul></div>')
            add('</div>')
            add('<p class="fine">Both matter, and they are not the same thing: one sets what a '
                'buyer will pay, the other decides whether they come at all.</p>')
        # "To them, it's the one they've been waiting for" is advertising copy
        # after an otherwise disciplined page. Replaced with the economic point.
        add('<div class="weight"><p>Those are not just lifestyle details. They help explain which '
            'buyers are likely to see more value here than the average buyer does.</p></div>')
        add('<a class="cue" href="#correct">What if something here is wrong? ↓</a>')
        add('</div></section>')

    # ── 10 · correct the home ───────────────────────────────────────
    gaps = b.get("gaps") or []
    add('<section id="correct"><div class="wrap">')
    add('<div class="eyebrow">Your home</div>')
    add('<h2>You know this home better than the records do</h2>')
    add('<div class="correct">')
    add('<p>Everything here was built from public records and sales data. Some of it will be wrong — '
        'a renovation we don\'t know about, a room count out of date, a sale that shouldn\'t have '
        'been used.</p>')
    if any("bathroom" in g for g in gaps):
        add('<p><b>We could not verify the bathroom count.</b></p>')
        add('<div class="choices">')
        for n, res in [("2", "Updated from unknown to 2 bathrooms. Two comparisons changed weight. "
                             "The rounded range is unchanged."),
                       ("3", "Updated from unknown to 3 bathrooms. Two comparisons changed weight. "
                             "The rounded range is unchanged."),
                       ("4+", "Updated from unknown to 4+ bathrooms. Three comparisons changed "
                              "weight. The lower end moved up."),
                       ("Something else", "Thanks — we'll look at this one by hand.")]:
            add(f'<button class="choice" aria-pressed="false" data-result="{E(res)}">{E(n)}</button>')
        add('</div><div class="result"></div>')
        if C:
            add('<div class="sim" style="margin-top:18px">')
            add('<div class="simtag">Concept — not wired</div>')
            add('<p style="margin:0">Once saved, a correction would persist against this address '
                'and the page would open with it already applied — including the note of what it '
                'changed, so the revision stays visible rather than quietly folded in.</p>')
            add('</div>')
        else:
            add('<p class="fine" style="margin-top:18px">Prototype — selections are not saved yet.</p>')
    add('<p class="fine" style="margin-top:18px">Corrections update this property record. They are '
        'not treated as a request for contact. Nobody calls unless you ask.</p>')
    add('<p class="fine">No agent is paying to appear on this page, and your interest in your own '
        'home is not sold to anyone.</p>')
    add('</div></div></section>')

    # ── 11 · a private working plan ─────────────────────────────────
    # Product/05_PAGE_FLOW.md section 10, prototyped in Prototypes/build_working_plan.py.
    # §0 opens by naming three questions; the page answered the first and
    # gestured at the second. This is the only section that demonstrates
    # JUDGEMENT rather than computation — what we would DO — which is the thing
    # an agent actually sells.
    #
    # The rule that makes it defensible: decisions only the owner can answer, we
    # ASK; decisions needing inspection and judgement, we RECOMMEND. Reflecting
    # someone's own button presses back at them demonstrates nothing.
    add('<section id="plan"><div class="wrap">')
    add('<div class="eyebrow">If you ever did move</div>')
    add('<h2>What a move would actually involve</h2>')
    add('<p class="lede">You don\'t need to be planning to sell. This brings the decisions '
        'together privately — what would have to happen, what we\'d recommend, and what '
        'genuinely can\'t be decided without seeing the home.</p>')
    add('<div class="sim"><div class="simtag">Concept — not wired</div>')
    add('<ol class="qs2">')
    for q in ["What would a move need to work around?",
              "How much preparation would feel reasonable?",
              "What matters most?",
              "What access could a campaign reasonably have?",
              "Anything else we\u2019d need to work around?"]:
        add(f'<li>{E(q)}</li>')
    add('</ol>')
    add('<p class="fine">Five questions only you can answer. Everything else — the method, the '
        'launch price, the campaign shape, which preparation actually pays — is ours to recommend, '
        'and every recommendation states what would change it.</p>')
    add('</div>')
    add('<h3 style="margin-top:26px">The part that needs someone to walk through it</h3>')
    add('<p>The final launch price · whether styling would change how the rooms photograph · '
        'the photography package · which preparation work would return more than it costs · '
        'settlement structure.</p>')
    add('<p class="fine">That list is the honest part. Anyone who hands you a complete plan from '
        'public records alone is guessing at the part that needs seeing.</p>')
    add('</div></section>')

    # ── closing · the next private question ─────────────────────────
    add('<section id="next"><div class="wrap"><div class="closing">')
    add('<div class="eyebrow">The next question</div>')
    add('<h2>The value is only the first question</h2>')
    # ⚠ The old summary listed only Act I — "where that comes from, what makes
    # the home different, how far the method has been out" — and understated the
    # journey by the time the reader reaches it. They have also seen today's
    # alternatives, what the market can and cannot tell them, and which parts of
    # a move depend on them. Naming the whole thing is what makes the last
    # question feel like the only one left.
    if v.get("point"):
        rounded = round(v["point"] / 50_000) * 50_000
        add(f'<p>You now know roughly what the evidence supports \u2014 around '
            f'{E(money(rounded))} \u2014 where that figure comes from, where this home sits '
            f'against today\'s alternatives, what the current market can and cannot tell you, '
            f'and which parts of a move still depend on your circumstances.</p>')
    add('<p>There is one question we haven\'t answered.</p>')
    add('<p class="lede">If you sold, where would you actually go?</p>')
    add('<p class="fine">See the homes currently available around the same broad value band, what '
        'waiting changes, and what usually makes a move difficult to coordinate.</p>')
    add('<a class="cta" href="#">Explore where you could go next</a>')
    add('<p class="fine" style="margin-top:14px">Still private · no contact details required</p>')
    add('</div></div></section>')

    add('<footer><div class="wrap">'
        '<div>Fields — smarter with data.</div>'
        '<div style="margin-top:6px">Estimates are built from comparable sales and public records. '
        'This is not a formal valuation or an appraisal; nobody has been inside this home.</div>'
        '</div></footer>')

    import re as _re
    body = "".join(P)

    # ── PARTS: the level above sections ──────────────────────────────
    # The page had FOURTEEN h2 sections and nothing above them. Every section
    # was a peer of every other, so there was no hierarchy for the reader to
    # perceive — "What has happened since the last recorded sale" carried the
    # same weight as "Is now the right time to be selling", because structurally
    # it did.
    #
    # The parts are not invented: they are the three questions the page opens by
    # naming. Answering them in order, and SAYING which one you are inside, is
    # the map. Deliberately no "part 2 of 3" or progress bar — the brief rules
    # that out ("turns curiosity into homework"). A part is a place, not a
    # percentage.
    PARTS = [
        # ⚠ No subtitle. In v3 the hero already asks "So which one should you
        # believe?" — a part subtitle asking "Is the number attached to this home
        # real?" restates it two lines later. That subtitle was carried over from
        # the v2 question list and is now orphaned copy.
        # ⚠ NO part heading over the opening. The hero already asks the question
        # the visitor arrived with; a part titled "The number" above it makes the
        # reader parse the page's taxonomy before its meaning. Acts II and III
        # still open with one, because there the reader IS changing subject.

        # ACT II — opens once the value question has closure. "What has happened
        # since the last recorded sale" starts it: the first thing that is about
        # this home TODAY rather than about the number.
        ("different", "What it means now",
         "You know what the evidence supports. Here is where this home sits in today's market."),
        # ACT III
        ("plan",    "What it would mean for you", None),
    ]
    for sid, title, sub in PARTS:
        anchor = f'<section id="{sid}"'
        if anchor not in body:
            continue
        part = (f'<div class="part"><div class="wrap">'
                f'<h1 class="parth">{E(title)}</h1>'
                + (f'<p class="parts">{E(sub)}</p>' if sub else "")
                + '</div></div>')
        body = body.replace(anchor, part + anchor, 1)
        # Drop the following section's <h2> when it merely repeats the part's
        # subtitle. The part asks the question; the section answers it.
        if sub:
            at = body.find(anchor)
            end = body.find('</section>', at)
            head = body[at:end if end > 0 else len(body)]
            dup = f'<h2>{E(sub)}</h2>'
            if dup in head:
                body = body[:at] + head.replace(dup, '', 1) + body[end if end > 0 else len(body):]

    # ── re-chain the forward cues ────────────────────────────────────
    # Every cue was written pointing at the section the author expected to come
    # next. Sections omit themselves on thin properties — 2 of 5 pages had a
    # dead `#nearby` because the obvious-comparable section never rendered — so
    # a hard-coded target is a link to nothing and a question the page never
    # answers. This is the same job `emit_v4._rechain` does for the deck:
    # re-point each cue at the section that ACTUALLY follows it, and take that
    # section's own question with it.
    CUE = {
        "which": "So what do the sales say? \u2193",
        "answer": "See what the sales support \u2193",
        "nearby": "First, one sale nearby is worth looking at \u2193",
        "comps": "See the strongest sales \u2193",
        "different": "So what makes this one different? \u2193",
        "reliable": "So how wrong could this be? \u2193",
        "dispersion": "Then why do the other numbers disagree? \u2193",
        "since": "What has it done since? \u2193",
        "timing": "Is now the right time? \u2193",
        "now": "What\u2019s moving around this home right now? \u2193",
        "buyer": "So who is most likely to value those things? \u2193",
        "correct": "What if something here is wrong? \u2193",
        "plan": "And if you ever did move? \u2193",
        "next": "What else is there? \u2193",
    }
    order = _re.findall(r'<section id="([^"]+)"', body)

    def _rechain(m):
        head, target = m.group(1), m.group(2)
        at = body.rfind('<section id=', 0, m.start())
        here = _re.match(r'<section id="([^"]+)"', body[at:]) if at >= 0 else None
        cur = here.group(1) if here else None
        if cur not in order:
            return m.group(0)
        # Always re-point at the section that ACTUALLY follows. "Forward" is not
        # good enough — a cue pointing three sections ahead skips the answer.
        # ⚠ Skip any target this section ALREADY links from a control. The range
        # card carries a "See the strongest comparisons" button, so a cue landing
        # on the same section said the same thing twice — which is what Will
        # spotted. Advance to the next section that is not already reachable
        # from here.
        sec_end = body.find('</section>', m.start())
        sec_html = body[at:sec_end if sec_end > 0 else len(body)]
        already = set(_re.findall(r'class="btn" href="#([^"]+)"', sec_html))
        nxt = next((sid for sid in order[order.index(cur) + 1:]), None)
        if not nxt:
            return ""                             # nothing follows — drop the cue entirely
        # If a control in this section already leads to the next one, the cue is
        # redundant: the button IS the affordance. Skipping ahead instead would
        # vault the reader over a section.
        if nxt in already:
            return ""
        label = CUE.get(nxt) or ("Keep reading " + chr(0x2193))
        return f'{head}href="#{nxt}">{label}</a>'

    body = _re.sub(r'(<a class="cue" )href="#([^"]+)">.*?</a>', _rechain, body, flags=_re.S)

    # Sections that actually rendered, in document order, labelled by their eyebrow.
    secs = []
    for m in _re.finditer(r'<section id="([^"]+)"[^>]*>.*?<div class="eyebrow">([^<]{2,44})',
                          body, _re.S):
        sid, label = m.group(1), m.group(2).strip()
        label = _re.sub(r"\s*·.*$", "", label).strip()      # drop "· Updated today"
        secs.append((sid, label))
    nav = "".join(f'<a href="#{sid}"><span class="i">{i+1:02d}</span>{E(label)}</a>'
                  for i, (sid, label) in enumerate(secs))

    qr_data, qr_uri = report_qr(short, slug)
    qr_block = ""
    if qr_data:
        # ⚠ A QR is useless on the device displaying it — you cannot scan your own
        # screen. Desktop gets the code; mobile gets the same deep link as a tap.
        # One action, the affordance each device can actually use.
        qr_block = (
            '<div class="dl"><div class="label">Download this report</div>'
            f'<img class="qr" src="{qr_data}" alt="Scan to text for this report">'
            '<p class="fine qronly">Scan with your phone. It opens a text to Fields — '
            'nothing is filled in by us and nothing is sent until you send it.</p>'
            f'<a class="btn taponly" href="{E(qr_uri)}">Text me this report</a>'
            '<p class="fine taponly">Opens your messages app with the request written. '
            'Nothing sends until you do.</p></div>')

    header = (
        '<header class="top"><div class="topin">'
        '<img class="brand" src="brand/fields-hero-grass.png" alt="Fields">'
        f'<span class="stickyaddr">{E(short)}</span>'
        '<div class="hright"><span class="tag">Private report</span>'
        '<button class="burger" id="burger" aria-expanded="false" aria-controls="menu" '
        'aria-label="Sections and download"><span></span><span></span><span></span>'
        '</button></div></div>'
        f'<div class="menu" id="menu" hidden><div class="menuin">'
        f'<div class="label">Sections</div><nav class="secnav">{nav}</nav>{qr_block}'
        '</div></div></header>')
    body = body.replace(header_placeholder, header, 1)

    return f"""<!doctype html><html lang="en-AU"><head>
<meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<meta name="robots" content="noindex">
<title>{E(short)} — private property report</title>
<style>{CSS}</style></head><body>
{body}
<script>{JS}</script></body></html>"""


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--slug", default="28-wedgebill-parade-burleigh-waters")
    ap.add_argument("--version", choices=sorted(VERSIONS), default=LATEST,
                    help=f"copy version (default {LATEST}). Older versions render "
                         f"alongside rather than replacing, so a wording can be compared "
                         f"or reverted to.")
    ap.add_argument("--index", action="store_true", help="rebuild the contact sheet only")
    ap.add_argument("--prototype", choices=["full", "a", "b", "c"], default="full",
                    help="full = the complete page (default). a/b/c isolate a build "
                         "stage for development only.")
    args = ap.parse_args()
    OUT.mkdir(parents=True, exist_ok=True)
    if args.index:
        n = build_index()
        print(f"index rebuilt — {n} addresses")
        print("https://vm.fieldsestate.com.au/concepts/off-market/V4_Private_Report/index.html")
        return 0
    suffix = "" if args.prototype == "full" else f"-{args.prototype}"
    vsuffix = "" if args.version == LATEST else f"--{args.version}"
    path = OUT / f"{args.slug}{suffix}{vsuffix}.html"
    path.write_text(render(args.slug, args.prototype, args.version))
    print(f"wrote {path}  ({path.stat().st_size:,} bytes)")
    build_index()
    print(f"https://vm.fieldsestate.com.au/concepts/off-market/V4_Private_Report/{path.name}")
    return 0




def build_index():
    """A way in for review. One link per address — the complete page.

    It previously listed A/B/C per property. Those are build stages, not
    variants: nobody would ever be shown "the spine" instead of the page. Three
    links implied a choice that does not exist and made the finished thing hard
    to find.
    """
    import re
    rows = []
    for f in sorted(OUT.glob("*.html")):
        if f.name == "index.html" or re.search(r"(-[abc]|--v\d+)\.html$", f.name):
            continue
        slug = f.stem
        rows.append((slug.replace("-", " ").title(), f.name))
    body = "".join(
        f'<li><a href="{fn}"><span class="n">{name}</span>'
        f'<span class="go">Open the report →</span></a></li>' for name, fn in rows)
    OUT.joinpath("index.html").write_text(f"""<!doctype html><html lang="en-AU"><head>
<meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<meta name="robots" content="noindex"><title>The private property report</title>
<style>{CSS}
ul.idx{{list-style:none;padding:0;margin:26px 0}}
ul.idx li{{border-bottom:1px solid var(--line-2)}}
ul.idx a{{display:flex;justify-content:space-between;align-items:baseline;gap:14px;
  padding:18px 0;text-decoration:none;color:var(--ink)}}
ul.idx .n{{font-family:var(--serif);font-size:1.16rem}}
ul.idx .go{{font-size:.86rem;color:var(--accent);white-space:nowrap}}
ul.idx a:hover .go{{text-decoration:underline}}
</style></head><body>
<header class="top"><div class="topin">
<img class="brand" src="brand/fields-hero-grass.png" alt="Fields">
<span class="tag">Private report</span></div></header>
<section><div class="wrap">
<div class="eyebrow">Off-market page redesign · V4</div>
<h1>The private property report</h1>
<p class="lede">The complete page, rendered from live data for {len(rows)} real addresses.
Answer first, prove it gradually, surprise them periodically, ask almost nothing.</p>
<ul class="idx">{body}</ul>
<p class="fine"><b>30 Whitehead Drive</b> is included deliberately: it sits above the $2,000,000
ceiling the comparable-sales method was built for, so the method declines, the page falls back to
a wider exterior-evidence range, and it refuses to quote an error rate it has not earned for that
method. <b>11 Placid Court</b> is Varsity Lakes, our least accurate market — and one carrying a
&minus;10.6% systematic bias that should be understood before the arm ships there.</p>
<p class="fine">Sections that depend on a property report — the competitor set and the change
timeline — are empty where no report exists (103 of 12,278 addresses have one). They omit
themselves rather than render half-filled.</p>
</div></section>
<footer><div class="wrap">Rendered {__import__('datetime').date.today().strftime('%-d %B %Y')} ·
every figure read live from the property record · noindex</div></footer>
</body></html>""")
    return len(rows)


if __name__ == "__main__":
    sys.exit(main())
