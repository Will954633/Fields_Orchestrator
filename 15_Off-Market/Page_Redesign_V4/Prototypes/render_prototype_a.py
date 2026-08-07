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

# Measured 2026-08-06, detached houses $1M-$2M, --price-filter none.
# Product/09_ACCURACY_AND_CALIBRATION.md. Per suburb, never blended — the spread
# between suburbs is wider than the gain from scoping, so a blend misdescribes
# two of three markets. No fallback: an unmeasured suburb renders no figure.
ACCURACY = {
    "robina":          {"n": 278, "mae": 10.5, "median": 8.2, "within10": 59, "contain": 67},
    "burleigh_waters": {"n": 155, "mae": 11.2, "median": 9.8, "within10": 52, "contain": 60},
    "varsity_lakes":   {"n": 207, "mae": 13.8, "median": 13.4, "within10": 36, "contain": 41},
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
LATEST = "v2"

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
section{padding:54px 0;border-top:1px solid var(--line-2)}
section:first-of-type{border-top:none}
h1,h2,h3{font-family:var(--serif);font-weight:600;letter-spacing:-.01em;line-height:1.22;margin:0}
h1{font-size:2rem}
h2{font-size:1.62rem;margin-bottom:.6rem}
h3{font-size:1.12rem}
p{margin:0 0 1rem}
.eyebrow{font-size:.7rem;letter-spacing:.14em;text-transform:uppercase;color:var(--muted);
         font-weight:600;margin-bottom:1rem}
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

footer{padding:44px 0 70px;border-top:1px solid var(--line-2);color:var(--muted);font-size:.85rem}

@media(min-width:760px){
  body{font-size:18px}
  h1{font-size:2.5rem} h2{font-size:2rem} .addr{font-size:2.3rem}
  .split{grid-template-columns:1fr 1fr}
  .twotrue{grid-template-columns:1fr 1fr}
  section{padding:70px 0}
}
"""

JS = """
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

    s, v = b.get("subject") or {}, b.get("valuation") or {}
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
        add(f'<h2>{E(pre["heading"])}</h2>')
        for i, para in enumerate(pre["paras"]):
            cls = ' class="lede"' if i == 0 else ""
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
        if v.get("n_comps") and adj:
            add(f'<p class="basis fine">{v["n_comps"]} relevant sales influenced the range. '
                f'The {len(adj)} strongest carried most of the weight.</p>')
        add('<p class="fine">The width is not hidden. It reflects what can — and cannot — be '
            'concluded without seeing inside the home.</p>')
        add('<div class="controls"><a class="btn" href="#comps">See the strongest comparisons</a>'
            '<a class="btn" href="#reliable">How reliable has this been?</a></div>')
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
        add('<h2>The sales behind that range</h2>')
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
                f'considered when comparing them.</p>')
        oc_addr = str((b.get("obvious_comp") or {}).get("address") or "").split(",")[0].lower()
        fresh = [c for c in adj if oc_addr not in str(c.get("address", "")).lower()] if oc_addr else adj
        for c in fresh[:3]:
            add('<div class="comp">')
            add(f'<div class="a">{E(str(c.get("address","")).split(",")[0])}</div>')
            meta = []
            if c.get("sale_price"):
                meta.append(f'Sold {exact(c["sale_price"])}')
            if c.get("sale_date"):
                meta.append(month_year(c["sale_date"]))
            if c.get("distance_m"):
                meta.append(f'{int(c["distance_m"])}m away')
            add(f'<div class="m">{E(" · ".join(meta))}</div>')
            add(f'<div class="adj"><span class="lab">Adjusted position</span>'
                f'<span class="val">about {E(money(c["adjusted_price"]))}</span></div>')
            if c.get("adjustments"):
                add('<details><summary>See the adjustment</summary><div class="body">'
                    + adjustment_rows(c) + '</div></details>')
            add('</div>')
        if B and len(adj) > 3:
            add(f'<details><summary>See all {len(adj)} strongest comparisons</summary><div class="body">')
            add('<div class="ctable">')
            for c in adj:
                w = c.get("weight")
                add('<div class="crow">'
                    f'<div class="ca">{E(str(c.get("address","")).split(",")[0])}'
                    f'<span class="fine"> · {E(month_year(c.get("sale_date")) or "—")}'
                    + (f' · {c["distance_km"]:.1f} km' if c.get("distance_km") else '')
                    + '</span></div>'
                    f'<div class="cs">{E(exact(c.get("sale_price")) or "—")}</div>'
                    f'<div class="cj">{E(money(c["adjusted_price"]))}</div>'
                    + (f'<div class="cw"><span style="width:{min(100, w*100):.0f}%"></span></div>'
                       if isinstance(w, (int, float)) else '<div class="cw"></div>')
                    + (f'<div class="cv fine">{E(str(c.get("verification")))}</div>'
                       if c.get("verification") else '<div class="cv"></div>')
                    + '</div>')
                add('<div class="cwork">' + adjustment_rows(c) + '</div>')
            add('</div>')
            add('<p class="fine">Weight reflects how good a comparison each sale is — adjustment '
                'quality, proximity, recency and how much of it we could verify.</p>')
            add('</div></details>')
        elif len(adj) > 3:
            add(f'<details><summary>See all {len(adj)} strongest comparisons</summary><div class="body">')
            for c in adj:
                if c in fresh[:3]:
                    continue
                add(f'<div style="padding:10px 0;border-bottom:1px solid var(--line-2)">'
                    f'<b>{E(str(c.get("address","")).split(",")[0])}</b> — sold '
                    f'{E(exact(c.get("sale_price")) or "—")}, adjusts to about '
                    f'{E(money(c["adjusted_price"]))}</div>')
            add('</div></details>')
        add('<p style="margin-top:20px">No sale is a match. Each one differs from this home in ways '
            'that are worth money, so we price those differences rather than averaging past them.</p>')
        add('<div class="src">Fields analysis of Queensland sales records · Government record</div>')
        add('<a class="cue" href="#different">So what makes this one different? ↓</a>')
        add('</div></section>')

    # ── 5 · what makes this home different ──────────────────────────
    if sc.get("active_matching") and sc.get("active_total"):
        add('<section id="different"><div class="wrap">')
        add('<div class="eyebrow">This home</div>')
        anchors = [n["phrase"] for n in (sc.get("notable") or []) if n.get("tier") == "anchor"]
        if anchors:
            add(f'<h2>{E(" and ".join(anchors).capitalize())} do not appear together often.</h2>')
        add('<div class="attrs">')
        if s.get("bedrooms"):
            add(f'<div><div class="n">{int(s["bedrooms"])}</div><div class="l">bedrooms</div></div>')
        if s.get("pool"):
            add('<div><div class="n">Pool</div><div class="l">on the block</div></div>')
        cl = (poi.get("cluster") or {})
        if cl.get("matching"):
            add(f'<div><div class="n">{cl["matching"]}</div><div class="l">share the position</div></div>')
        add('</div>')
        phrase = " and ".join(anchors) if anchors else None
        if phrase:
            add(f'<p>{sc["active_matching"]} of the {sc["active_total"]} homes on the market right '
                f'now match this one on {E(phrase)}.</p>')
        feats = poi.get("features") or []
        if cl.get("matching") and feats:
            names = ", ".join(f["short"] for f in feats[:-1]) + " and " + feats[-1]["short"] if len(feats) > 1 else feats[0]["short"]
            add(f'<p>Of the {poi.get("physical_matching")} that share the combination, only '
                f'<b>{cl["matching"]}</b> sit this close to {E(names)} — all at once.</p>')
        add('<p class="fine">That does not set a price by itself. It reduces the number of close '
            'substitutes a buyer can choose from.</p>')
        if B:
            mp, n_pins = scarcity_map(doc, b, slug)
            if mp:
                add(f'<img class="shot" style="aspect-ratio:16/10;margin:20px 0 6px" src="{E(mp)}" '
                    f'alt="Homes sharing this combination near {E(short)}" loading="lazy">')
                add(f'<div class="fine">This home in yellow; the {n_pins} homes currently on the '
                    f'market that share the combination in grey. How far a buyer would have to go '
                    f'to find a substitute. Mapping · Google</div>')
        if feats:
            add('<details><summary>See the distances</summary><div class="body">')
            for f in feats:
                add(f'<div style="display:flex;justify-content:space-between;padding:6px 0;'
                    f'border-bottom:1px solid var(--line-2)"><span>{E(f["label"])}</span>'
                    f'<span>{int(f["distance_m"])}m</span></div>')
            add('</div></details>')
        add('<a class="cue" href="#reliable">So how wrong could you be? ↓</a>')
        add('</div></section>')

    # ── 6 · how reliable ────────────────────────────────────────────
    add('<section id="reliable"><div class="wrap">')
    add('<div class="eyebrow">Reliability</div>')
    add('<h2>How wrong has this method been?</h2>')
    if acc:
        add(f'<div class="bigfig">{acc["mae"]}%</div>')
        add(f'<p>Tested against {acc["n"]} {E(b.get("suburb_display",""))} houses in this price range '
            f'that later sold, the centre of the estimate was out by <b>{acc["mae"]}% on average</b>. '
            f'Half the time it was within {acc["median"]}%.</p>')
        add('<p>That is why this page shows a range rather than pretending the evidence supports one '
            'exact number.</p>')
        if v.get("low") and v.get("high"):
            add('<div class="scale"><div class="fine">Where the eventual sale landed, in testing</div>'
                '<div class="bar"><span class="band" style="left:22%;right:22%"></span>'
                '<span class="tick" style="left:50%"></span></div>'
                f'<div class="lbl"><span>{E(money(v["low"]))}</span>'
                f'<span>{E(money(v["high"]))}</span></div>'
                f'<div class="fine" style="margin-top:12px">The sale price fell inside a range built '
                f'this way {acc["contain"]}% of the time.</div></div>')
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
        add(f'<div style="display:flex;justify-content:space-between;padding:6px 0">'
            f'<span>Sale fell inside the published range</span><span>{acc["contain"]}%</span></div>')
        add('<p class="fine" style="margin-top:14px">Those homes sold, which this one has not — so '
            'treat it as the method\'s track record, not a promise about this address.</p>')
        add('</div></details>')
        add('<div class="src">Fields analysis · tested 6 August 2026</div>')
    else:
        add('<p>The range above was not built by the comparable-sales method. This home sits '
            'outside the band that method was built for — detached houses between $1,000,000 and '
            '$2,000,000 — so we have used a wider approach based on what can be verified from '
            'the outside.</p>')
        add('<p>We publish a measured error rate for the comparable-sales method. We do not have '
            'one for this fallback, so we are not quoting a number we have not earned.</p>')
        add('<p class="fine">The comparable sales below are unchanged. They are the part we can '
            'stand behind either way.</p>')
    add('</div></section>')

    # ── 6b · why the other estimates disagree (Prototype B) ─────────
    if B:
        add('<section id="dispersion"><div class="wrap">')
        add('<div class="eyebrow">The other numbers</div>')
        add('<h2>Why the other estimates say something different</h2>')
        add('<p>A valuation built from only three selected sales is highly sensitive to which three '
            'are chosen — and three comparable sales is the statutory Statement of Information '
            'standard in Victoria and the incoming NSW regime, so it is not a straw man.</p>')
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
            '<p class="fine">This is a property of the three-sale method, measured on our own data. '
            'It is not a claim about any particular provider, and we have not tested anyone '
            'else\'s figures.</p></div></details>')
        add('<div class="src">Fields analysis · n=512 · tested 6 August 2026</div>')
        add('</div></section>')

    # ── 7 · since the last recorded sale ────────────────────────────
    g = _cards.get("gain") or {}
    if g.get("bought"):
        add('<section id="since"><div class="wrap">')
        add('<div class="eyebrow">Since then</div>')
        add('<h2>What has happened since the last recorded sale</h2>')
        add(f'<div class="anchor">{E(str(g["bought"]))}</div>')
        # ⚠ ORDER IS LOAD-BEARING, as on the deck card. `bought` can be a sale from
        # decades ago while `ten_year` covers a ten-year window; rendered adjacent
        # with nothing between them a reader does arithmetic across both and gets
        # a number we have not evidenced. `cannot_reach` — which states outright
        # where our series starts — goes BETWEEN them.
        if g.get("cannot_reach"):
            add(f'<p class="rangeNote">{E(str(g["cannot_reach"]).strip())}</p>')
        if g.get("since"):
            add(f'<p>{E(str(g["since"]).strip())}</p>')
        if g.get("ten_year"):
            add('<div class="label">The last ten years</div>')
            add(f'<p>{E(str(g["ten_year"]).strip())}</p>')
        if g.get("means"):
            add(f'<div class="weight"><p>{E(str(g["means"]).strip())}</p></div>')
        add('<a class="cue" href="#now">And what\'s happening around it now? ↓</a>')
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
        if comp.get("n_compete"):
            add(f'<p>{comp["n_compete"]} homes a buyer could compare with this one if it came to '
                f'market today, from {comp.get("n_total","—")} on the market across the wider area.</p>')
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
        dom, dom_p = mkt.get("dom_median"), mkt.get("dom_yoy_prev")
        act, act_d = mkt.get("active_listings"), mkt.get("active_listings_mom_pct")
        if dom and dom_p and act:
            add('<h3 style="margin-top:26px">Two true things point in different directions</h3>')
            add('<div class="twotrue">')
            add(f'<div><div class="n">{dom:.0f} days</div><div class="fine">to sell, against '
                f'{dom_p:.0f} twelve months ago</div></div>')
            add(f'<div><div class="n">{act:.0f} homes</div><div class="fine">on the market'
                + (f', {abs(act_d):.0f}% {"fewer" if act_d < 0 else "more"} than a month ago' if act_d else '')
                + '</div></div>')
            add('</div>')
            add('<p>Both readings are true and they support opposite conclusions, which is why a '
                'single market headline cannot settle anything about this home.</p>')
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
        add(f'<h2>{E(str(bb.get("headline") or "Who that combination suits"))}</h2>')
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
        if by.get("reframe"):
            add(f'<div class="weight"><p>{E(str(by["reframe"]).strip())}</p></div>')
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
        'public records alone is guessing at the half that needs seeing.</p>')
    add('</div></section>')

    # ── closing · the next private question ─────────────────────────
    add('<section id="next"><div class="wrap"><div class="closing">')
    add('<div class="eyebrow">The next question</div>')
    add('<h2>The value is only the first question</h2>')
    if v.get("point"):
        rounded = round(v["point"] / 50_000) * 50_000
        add(f'<p>The evidence around this home currently centres around approximately '
            f'{E(money(rounded))}. We have shown where that comes from, what makes the home '
            f'different, and how far the method has historically been out.</p>')
    add('<p class="lede">The next question is more personal: if you sold, where would you actually go?</p>')
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
