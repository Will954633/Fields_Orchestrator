#!/usr/bin/env python3
"""
generate_mailers_v2.py — homeowner mailer, version two.

Separate from V1 in every respect: its own folder, template, assets and output.
Neither reads the other. V1 is untouched and still runnable.

WHAT CHANGED, AND WHY
---------------------
V1 sold the analysis. V2 sells the finding. The distinction decides whether the
mailer gets scanned, because the owner does not want to know how thorough we
are — they want to know what we found out about their house.

1. The three statistics are no longer fixed. `hooks.py` builds every finding the
   report can support, scores it, and lets the best one lead. Distance to a
   school now has to earn its slot and usually does not.
2. Page 1 withholds. It states counts and never the answers — which homes, which
   strengths, which trade-offs, which buyer. V1 printed the buyer persona's
   description on page 2, which closed the loop it had just opened.
3. The layout is asymmetric: one dominant finding, two supporting. Three equal
   cards told the reader all three mattered equally.
4. Analytical volume ("49 comparable sales reviewed") moved out of the headline
   cards and into a proof line. It is evidence that the finding is trustworthy,
   not a finding.
5. The "valuation follows within three business days" line is gone. It turned
   "your analysis is ready" into "your analysis is partly ready" at the exact
   moment of conversion. Instead the readiness gate now REQUIRES a real
   valuation, so the promise is true when the envelope lands.
6. The QR points at `#market`, the tab that actually shows the competing homes.
   V1 promised "see the homes buyers would compare with yours" and landed the
   scanner on tab 01, which shows their own home's data.
7. "Your PRIVATE home report" is gone — the URL is public, if unlisted, and an
   exclusivity claim we cannot defend is not worth the trust it costs.

USAGE:
  python3 generate_mailers_v2.py --slug 25-huntingdale-crescent-robina
  python3 generate_mailers_v2.py --all-ready --combine
  python3 generate_mailers_v2.py --slug <s> --dry-run   # show selected findings, no PDF
  python3 generate_mailers_v2.py --audit               # score every report, print the pool
"""
import argparse
import os
import sys
from datetime import datetime

sys.path.insert(0, "/home/fields/Fields_Orchestrator")
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import qrcode
import requests
from weasyprint import HTML

from shared.db import get_client  # noqa: E402

from grammar import Count  # noqa: E402
from hooks import select, build_findings  # noqa: E402

HERE = os.path.dirname(os.path.abspath(__file__))
TEMPLATE = os.path.join(HERE, "mailer_v2_template.html")
ASSETS = os.path.join(HERE, "assets")
GEN = os.path.join(ASSETS, "gen")
OUT = os.path.join(HERE, "output")
BASE_URL = "https://fieldsestate.com.au"
UTM = "utm_source=mailer&utm_medium=print&utm_campaign=home_report_v2"
GREEN = (34, 56, 44)
PAPER = (253, 243, 236)

# The competing-homes tab. The mailer's promise is "see the homes buyers would
# compare with yours"; `/your-home/<slug>` alone opens on tab 01 (the owner's
# own data) and the competing listings sit in tab 02. `#market` is an existing
# deep-link the page already honours — see YourHomePage.tsx parseTab().
DEEP_LINK = "#market"


# Postcodes for every locality we mail into. A wrong postcode on a printed
# envelope is not a cosmetic defect — it can stop delivery outright, and it is
# the one claim on the page the reader can check instantly.
#
# ⚠ Robina street addresses are ALWAYS 4226. 4230 is Robina Town Centre PO
# boxes and locked bags only and must never appear on a posted address.
# ⚠ 4213 is the trap: Mudgeeraba and Worongary are legitimately 4213, so a 4213
# on a Robina record looks plausible. That is exactly how
# "819 Legend Trail, Robina, QLD 4213" reached the artwork.
POSTCODES = {
    "robina": "4226",
    "merrimac": "4226",
    "clear island waters": "4226",
    "varsity lakes": "4227",
    "reedy creek": "4227",
    "burleigh waters": "4220",
    "mudgeeraba": "4213",
    "worongary": "4213",
    "carrara": "4211",
    "nerang": "4211",
    "mermaid waters": "4218",
}
PO_BOX_ONLY = {"4230": "Robina Town Centre PO boxes and locked bags"}


def check_postal_address(address):
    """Reasons this address must not be printed on an envelope."""
    import re
    m = re.search(r",\s*([A-Za-z ]+?),?\s*QLD\s*(\d{4})\s*$", (address or "").strip())
    if not m:
        return [f"cannot parse a QLD postal address from {address!r}"]
    locality, pc = m.group(1).strip().lower(), m.group(2)
    if pc in PO_BOX_ONLY:
        return [f"postcode {pc} is {PO_BOX_ONLY[pc]} — never a street delivery"]
    expected = POSTCODES.get(locality)
    if expected is None:
        return [f"{locality.title()} is not a locality we have a postcode for — add it to POSTCODES"]
    if pc != expected:
        return [f"{locality.title()} addresses are {expected}, not {pc} — mail may not be delivered"]
    return []


def parse_address(address):
    parts = [p.strip() for p in address.split(",") if p.strip()]
    return parts[0], " ".join(parts[1:]).upper()


def download(url, dest):
    r = requests.get(url, timeout=45, allow_redirects=True,
                     headers={"User-Agent": "Mozilla/5.0 (Fields mailer v2)"})
    r.raise_for_status()
    if len(r.content) < 800:
        raise ValueError(f"tiny image {len(r.content)}B")
    with open(dest, "wb") as f:
        f.write(r.content)
    return dest


def make_qr(slug):
    # utm_content carries the mailed slug so a scan is attributable to exactly
    # one posted envelope — the basis of per-address uplift measurement
    # (scripts/samantha/mailout_uplift_tracking.md). campaign is _v2 so the two
    # versions never pool in reporting.
    url = f"{BASE_URL}/your-home/{slug}?{UTM}&utm_content={slug}{DEEP_LINK}"
    qr = qrcode.QRCode(error_correction=qrcode.constants.ERROR_CORRECT_M, box_size=20, border=4)
    qr.add_data(url)
    qr.make(fit=True)
    img = qr.make_image(fill_color=GREEN, back_color=PAPER)
    os.makedirs(os.path.join(GEN, slug), exist_ok=True)
    path = os.path.join(GEN, slug, "qr.png")
    img.save(path)
    return url, f"assets/gen/{slug}/qr.png"


def _g(d, *path, default=None):
    cur = d
    for k in path:
        if not isinstance(cur, dict):
            return default
        cur = cur.get(k)
    return default if cur is None else cur


# ---------------------------------------------------------------------------
# readiness
# ---------------------------------------------------------------------------
def check_ready(doc):
    """Reasons this address cannot be mailed. Empty list = ready.

    Stricter than V1 on purpose. V1 shipped mailers whose valuation was still
    pending and admitted it on the page; V2 removes that admission, so the gate
    has to make it untrue rather than unsaid.
    """
    reasons = []
    ss = doc.get("slot_status") or {}
    sf = doc.get("scarcity_features") or {}

    # the postal address is the first claim on the page and the only one that
    # decides whether the envelope arrives at all
    reasons += check_postal_address(doc.get("address"))

    if doc.get("build_state") != "complete":
        reasons.append(f"build_state={doc.get('build_state')}")
    if ss.get("scarcity") != "approved":
        reasons.append("scarcity slot not approved")
    if ss.get("competitor_matches") != "approved":
        reasons.append("competitor_matches slot not approved")

    # a real, consultant-reviewed valuation — the reason we can drop the
    # "within three business days" caveat
    if ss.get("comps") != "approved":
        reasons.append("comps slot not approved (valuation not reviewed)")
    method = _g(doc, "valuation", "model_range", "method")
    if method in (None, "thin"):
        reasons.append(f"valuation method={method!r} (no real working range)")

    # the real competitive measure, not the ≤6 plotted set — see hooks._funnel
    funnel = _g(doc, "slots", "competitor_map", "ranked_comparison", "funnel", default={})
    if funnel.get("close_tier") is None:
        reasons.append("no funnel.close_tier (competitor ranking never ran)")
    if not _g(doc, "comparables", "closest_active", default=[]):
        reasons.append("no competing listings to name")
    if not sf.get("active_listings_total"):
        reasons.append("no active_listings_total")
    # Page 2 asks four questions and promises an answer to each. Two of them —
    # "who is most likely to value your home highly" and "what could strengthen
    # or weaken its position" — are answered from positioning.personas and
    # positioning.tradeOffs. 4 of 25 otherwise-mailable reports carry neither,
    # so the mailer would promise two sections the scan cannot deliver. Same
    # principle as the valuation gate above: make the claim true, not unsaid.
    pos = doc.get("positioning") or {}
    if not (pos.get("personas") or []):
        reasons.append("no buyer persona (page 2 Q3 would be unanswerable)")
    if not (pos.get("tradeOffs") or []):
        reasons.append("no trade-offs (page 2 Q4 would be unanswerable)")

    if not (doc.get("property") or {}).get("photos"):
        reasons.append("no hero photo")
    if not _g(doc, "property", "satellite", "satellite_image_url"):
        reasons.append("no aerial")
    return reasons


# ---------------------------------------------------------------------------
# copy assembly
# ---------------------------------------------------------------------------
def support_card_html(f):
    unit = f'<span class="unit">{f.unit}</span>' if f.unit else ""
    # a worded value ("3 strengths · 3 trade-offs") cannot render at numeral size
    long = " long" if len(strip(f.number)) > 6 else ""
    return (
        '        <div class="stat">\n'
        f'          <div class="big serif{long}">{f.number}{unit}</div>\n'
        '          <div class="txt">\n'
        f'            <div class="lab">{f.label}</div>\n'
        f'            <div class="sub">{f.sub}</div>\n'
        '          </div>\n'
        '        </div>'
    )


def funnel_html(hero):
    """Render the narrowing as 230 → 91 → 2.

    "Broadly similar" replaces the in-house phrase "size and type band" — no
    homeowner thinks about their house that way. The widest figure is named as
    the buyer search area rather than "near you", because the geography is part
    of the methodology and vagueness there reads as hand-waving.
    """
    if not hero.funnel:
        return ""
    total, in_band, close = hero.funnel
    if not total or not in_band or in_band >= total or close > in_band:
        return ""
    a = '<span class="arw">&rarr;</span>'
    return (
        '          <div class="funnel">'
        f'<b>{total}</b> for sale in the buyer search area{a}'
        f'<b>{in_band}</b> broadly similar to yours{a}'
        f'<b>{close}</b> genuinely competing'
        '</div>'
    )


def proof_line(doc):
    """Analytical volume, demoted to evidence.

    Phrased as an output rather than an input where we can: reviewing 49 sales
    is effort, finding which of them matter is a conclusion.
    """
    n = _g(doc, "valuation", "model_range", "comp_count") or len(_g(doc, "valuation", "comps", default=[]))
    total = _g(doc, "scarcity_features", "active_listings_total")
    bits = []
    if n:
        bits.append(f"<b>{n} recent sales</b> analysed to work out which ones actually bear on your home&rsquo;s value")
    if total:
        bits.append(f"<b>{total} homes for sale</b> reviewed to find the ones you are really competing with")
    return " &nbsp;·&nbsp; ".join(bits) if bits else ""


def competition_sentence(doc):
    """Page 2, item 01 — worded from the same source as the headline.

    Never introduces a second competitor number. V1's page 2 reused the capped
    array while page 1 quoted a different figure, which is how a reader ends up
    asking "is it 5 or 57?".
    """
    close, in_band, _total = _funnel_local(doc)
    plotted = len(_g(doc, "comparables", "closest_active", default=[]))
    c = Count(close)
    narrowed = f", narrowed from {in_band} broadly similar homes." if in_band else "."
    # "broadly similar", not "in your home's band" — no homeowner thinks in
    # bands, and the phrase reads as internal jargon leaking onto the page.
    #
    # The singular is a different SENTENCE, not a different word: you cannot
    # "choose between" one listing, and "their prices" has no referent.
    return c.pick(
        zero=("<b>Nothing currently for sale</b> closely competes with your home. We show "
              f"the {plotted} nearest substitutes anyway &mdash; named, mapped, and watched "
              "as their prices and status change."),
        one=("The <b>one listing</b> a buyer would most realistically compare with yours "
             "&mdash; named, mapped and watched as its price and status change" + narrowed),
        many=(f"The <b>{close} listings</b> a buyer would realistically choose between "
              "&mdash; named, mapped, and watched as their prices and status change" + narrowed),
    )


def _funnel_local(doc):
    f = _g(doc, "slots", "competitor_map", "ranked_comparison", "funnel", default={})
    return (f.get("close_tier"),
            _g(doc, "comparables", "active_in_band") or f.get("in_band"),
            _g(doc, "scarcity_features", "active_listings_total") or f.get("active_total"))


def also_line(hero, cands, support):
    """The second open loop: name what else was found, answer none of it.

    Only ever mentions findings that genuinely exist on this report, never
    repeats what is already on the page, and — importantly — honours the same
    CONFLICTS rules the card selection does. Without that last part this
    paragraph reintroduces the contradiction the cards were kept apart to
    avoid: a page headlined "only 7 closely compete" would go on to promise
    "how rare your home's combination is (57 of 206)", and the reader is back
    to asking which number is real.
    """
    said = {hero.kind} | set(hero.conflicts) | {f.kind for f in support}
    for f in support:
        said |= set(f.conflicts)
    parts = []
    for f in cands:
        if f.kind in said:
            continue
        # kept short: page 1 has a hard vertical budget (see .frontbody), and
        # this paragraph is the last thing before the CTA band
        phrase = {
            "competition": "the homes a buyer would choose between",
            "advantages_tradeoffs": "where your home has an edge &mdash; and where a buyer may hesitate",
            "scarcity": "how rare your home&rsquo;s combination really is",
            "buyer": "the buyer most likely to value it highly",
            "land_rank": "how your block compares with its cohort",
            "feature_rarity": "which feature appears to separate the stronger local sales",
            "recent_activity": "what changed in your competing set this month",
            "school_walk": "the everyday distances a buyer weighs",
        }.get(f.kind)
        if phrase:
            parts.append(phrase)
            said.add(f.kind)
        if len(parts) == 2:
            break
    # Fallback: on a property where every scored finding already appears on the
    # page, there is nothing left to tease and the paragraph collapses, leaving
    # a hole above the CTA. The four page-2 questions always have answers (the
    # gate guarantees it), so tease whichever of those the cards have not
    # already covered. This keeps the second open loop on every mailer.
    if len(parts) < 2:
        for kind, phrase in (
            ("buyer", "the buyer group most likely to value it highly"),
            ("advantages_tradeoffs", "where your home has an edge &mdash; and where a buyer may hesitate"),
            ("competition", "which recent sales actually set the benchmark for yours"),
        ):
            if kind not in said and phrase not in parts:
                parts.append(phrase)
                said.add(kind)
            if len(parts) == 2:
                break

    if not parts:
        return ""
    if len(parts) == 1:
        body = parts[0]
    else:
        body = ", ".join(parts[:-1]) + ", and " + parts[-1]
    return f"We also found <b>{body}</b>. None of it is on this page."


def cta2_lines(hero, doc):
    """Page 2's closing CTA — as specific as page 1's.

    "See what we found" is the weakest line on either page and it sat at the
    exact point where the scan should close. Curiosity carries the first visit;
    the come-back-later benefit is real but secondary until they have been once,
    so it moves to the line beneath.
    """
    close, _in_band, _total = _funnel_local(doc)
    c = Count(close)
    if hero.kind == "no_competition" or c.is_zero:
        return ("Nothing for sale closely competes with your home.",
                "See what we compared it against &mdash; and where yours stands.")

    # NOT "where yours has the edge over them". That asserts superiority over
    # the whole competing set, and on a property whose own analysis found 1
    # strength against 3 trade-offs it is simply not supported — 120 Glen
    # Eagles is exactly that shape. The honest version is also the stronger
    # one: it opens two loops (where do I win, where do I lose) instead of one,
    # and a sender willing to say "gives one away" is read as an assessment
    # rather than an approach.
    n_adv = len(_g(doc, "scarcity_features", "notable_features", default=[]))
    n_tr = len(_g(doc, "positioning", "tradeOffs", default=[]))
    then = ("And where yours has an advantage &mdash; or gives one away."
            if (n_adv and n_tr) else
            c.pick(zero="", one="And where yours stands against it.",
                   many="And where yours stands against them."))
    # The singular headline says WHY that one home matters rather than just
    # counting it — a single competitor is a sharper fact than six.
    head = c.pick(
        zero="",
        one="See the home buyers are most likely to compare with yours.",
        many=f"See the {close} homes we found.",
    )
    return (head, then)


def peek_1(doc):
    """Skim-layer prompt for page 2, item 01. Counts, never names.

    "See the 1 property" is both clumsy and weaker than "See which property" —
    the latter keeps the loop open, which is the whole job of these prompts.
    """
    close, _in_band, _total = _funnel_local(doc)
    return Count(close).pick(
        zero="See what we compared it against &rarr;",
        one="See which property &rarr;",
        many=f"See the {close} properties &rarr;",
    )


def cta_lines(hero):
    """Headline + the intensifier beneath it. Matched to whatever led page 1, so
    the promise the QR makes is the promise the landing tab keeps."""
    return {
        "competition": (hero.number == "1" and
                        ("See the home buyers are most likely to compare with yours.",
                         "And where yours stands against it.") or
                        ("See the homes buyers would compare with yours.",
                         "And where yours stands against them.")),
        "advantages_tradeoffs": ("See what is working in your home&rsquo;s favour.",
                                 "And what a buyer may weigh against it."),
        "scarcity": ("See how rare your home&rsquo;s combination really is.",
                     "And which buyer is looking for exactly that."),
        "buyer": ("See the buyer most likely to value your home.",
                  "And what they pay more for."),
    }.get(hero.kind, ("See what we found about your home.",
                      "And the evidence behind it."))


def build_context(doc):
    street, locality = parse_address(doc["address"])
    hero, support, cands = select(doc, n_support=2)
    cta_head, cta_then = cta_lines(hero)
    cta2_head, cta2_then = cta2_lines(hero, doc)

    return {
        "doc": doc,
        "slug": doc["slug"],
        "street": street,
        "locality": locality,
        "hero": hero,
        "support": support,
        "cands": cands,
        "hero_img": (doc["property"]["photos"][0]["url"]),
        "aerial_img": _g(doc, "property", "satellite", "satellite_image_url"),
        "competition_sentence": competition_sentence(doc),
        "comps_reviewed": (_g(doc, "valuation", "model_range", "comp_count")
                           or len(_g(doc, "valuation", "comps", default=[]))),
        "proof": proof_line(doc),
        "also": also_line(hero, cands, support),
        "cta_head": cta_head,
        "cta_then": cta_then,
        "cta2_head": cta2_head,
        "cta2_then": cta2_then,
        "peek_1": peek_1(doc),
    }


def render(ctx, dry=False):
    slug, hero = ctx["slug"], ctx["hero"]
    url, qr_rel = make_qr(slug)
    gdir = os.path.join(GEN, slug)
    hero_rel, aer_rel = f"assets/gen/{slug}/hero.jpg", f"assets/gen/{slug}/aerial.png"
    if not dry:
        download(ctx["hero_img"], os.path.join(gdir, "hero.jpg"))
        download(ctx["aerial_img"], os.path.join(gdir, "aerial.png"))

    repl = {
        "{{STREET}}": ctx["street"],
        "{{LOCALITY}}": ctx["locality"],
        "{{HERO_HEADLINE}}": hero.hero_headline,
        "{{HERO_CONSEQUENCE}}": hero.hero_consequence or "",
        "{{HERO_NUMBER}}": hero.number,
        "{{HERO_UNIT}}": hero.unit,
        "{{HERO_LABEL}}": hero.label,
        "{{HERO_SUB}}": hero.sub,
        "{{HERO_FUNNEL}}": funnel_html(hero),
        "{{SUPPORT_CARDS}}": "\n".join(support_card_html(f) for f in ctx["support"]),
        "{{PROOF_LINE}}": ctx["proof"],
        "{{ALSO_LINE}}": ctx["also"],
        "{{CTA_HEADLINE}}": ctx["cta_head"],
        "{{CTA_THEN}}": ctx["cta_then"],
        "{{CTA2_HEADLINE}}": ctx["cta2_head"],
        "{{CTA2_THEN}}": ctx["cta2_then"],
        "{{PEEK_1}}": ctx["peek_1"],
        "{{COMPETITION_SENTENCE}}": ctx["competition_sentence"],
        "{{COMPS_REVIEWED}}": str(ctx["comps_reviewed"]),
        "{{HERO_IMG}}": hero_rel,
        "{{AERIAL_IMG}}": aer_rel,
        "{{QR_IMG}}": qr_rel,
    }
    html = open(TEMPLATE, encoding="utf-8").read()
    for k, v in repl.items():
        html = html.replace(k, v)

    # A leftover placeholder means the template and the generator have drifted;
    # printing a mailer that says "{{HERO_SUB}}" is worse than failing.
    import re
    leftover = set(re.findall(r"\{\{[A-Z_]+\}\}", html))
    if leftover:
        raise ValueError(f"unfilled placeholders: {sorted(leftover)}")

    print(f"  ✓ {ctx['street']}, {ctx['locality']}")
    print(f"      LEADS WITH  [{hero.kind}  score {hero.score:.0f}]  {strip(hero.hero_headline)}")
    for f in ctx["support"]:
        print(f"      supporting  [{f.kind}  score {f.score:.0f}]  {f.number} — {strip(f.label)}")
    dropped = [f.kind for f in ctx["cands"] if f is not hero and f not in ctx["support"]]
    if dropped:
        print(f"      not used    {', '.join(dropped)}")
    print(f"      QR → {url}")

    if dry:
        return None
    os.makedirs(OUT, exist_ok=True)
    out_pdf = os.path.join(OUT, f"{slug}.pdf")

    # Render once, measure the laid-out boxes, then write the same document.
    document = HTML(string=html, base_url=HERE).render()
    layout_problems = verify_layout(document)
    document.write_pdf(out_pdf)

    problems = layout_problems + verify_pdf(out_pdf, ctx)
    if problems:
        # keep the file so the fault can be looked at, but never let it into a
        # print run silently
        bad = out_pdf.replace(".pdf", ".REJECTED.pdf")
        os.replace(out_pdf, bad)
        raise ValueError("artwork verification failed → " + bad + "\n        - "
                         + "\n        - ".join(problems))
    print("      verified: 2 pages, all copy present on the artwork")
    return out_pdf


def strip(s):
    import re
    s = re.sub(r"<[^>]+>", "", s or "")
    for ent, ch in (("&mdash;", "—"), ("&rsquo;", "'"), ("&ldquo;", "“"),
                    ("&rdquo;", "”"), ("&sup2;", "²"), ("&thinsp;", " "),
                    ("&nbsp;", " "), ("&middot;", "·"), ("&amp;", "&"),
                    ("&rarr;", "→"), ("&#8209;", "‑")):
        s = s.replace(ent, ch)
    return s


def _boxes_by_class(page_box):
    """{css class -> (top, bottom)} for every laid-out box on a page.

    WeasyPrint keeps the source element on each box, so the real geometry of the
    artwork is readable before anything is written to disk.
    """
    found = {}

    def walk(box):
        el = getattr(box, "element", None)
        cls = (el.get("class") if el is not None and hasattr(el, "get") else None)
        if cls:
            try:
                top = box.position_y
                bottom = top + box.height
            except (AttributeError, TypeError):
                top = bottom = None
            if top is not None:
                for c in cls.split():
                    prev = found.get(c)
                    found[c] = (min(prev[0], top), max(prev[1], bottom)) if prev else (top, bottom)
        for child in getattr(box, "children", []):
            walk(child)

    walk(page_box)
    return found


def verify_layout(document):
    """Measure the page instead of guessing at it.

    Page 1's flowing copy ends with `.also`, and `.cta` is absolutely positioned
    across the bottom. Nothing in the normal flow knows the CTA is there, so an
    overlong paragraph renders underneath it — present in the PDF, invisible on
    paper.

    Character budgets were the first attempt at guarding this and they are the
    wrong instrument: they bound each string separately, while the real
    constraint is CUMULATIVE. On 213 Acanthus Avenue the hero headline wrapped
    to three lines instead of two, which pushed everything down; the also-line
    was comfortably inside its own limit and still got cut in half by the green
    band. A proxy for a geometric constraint fails whenever some other element
    moves. This measures the collision directly.
    """
    problems = []
    for i, page in enumerate(document.pages, start=1):
        boxes = _boxes_by_class(page._page_box)
        page_h = page.height
        cta = boxes.get("cta")
        if not cta:
            problems.append(f"page {i}: no CTA band found — template changed?")
            continue
        cta_top = cta[0]
        # every element that flows normally on this page
        for cls in ("also", "imgcap", "proof", "findings", "conseq", "trust", "items"):
            box = boxes.get(cls)
            if not box:
                continue
            top, bottom = box
            if top >= cta_top:          # legitimately inside/after the band
                continue
            if bottom > cta_top:
                problems.append(
                    f"page {i}: .{cls} runs {bottom - cta_top:.1f}pt past the top of the "
                    f"CTA band — it will print underneath the green panel")
            if bottom > page_h:
                problems.append(
                    f"page {i}: .{cls} runs {bottom - page_h:.1f}pt off the bottom of the "
                    f"page — it will be cropped")
    return problems


def verify_pdf(path, ctx):
    """Assert the copy we composed actually appears on the printed page.

    `.page` is a fixed 210×297mm box with `overflow:hidden`, so content that no
    longer fits is not pushed to another page — it is silently cropped. A single
    extra line of hook copy can therefore delete the closing paragraph from the
    artwork with no error anywhere, and the PDF still looks plausible. This
    caught exactly that: the "We also found…" line rendered underneath the CTA
    band and vanished from the output.

    So we extract the text back out and check the load-bearing lines survived.
    """
    import re
    import subprocess
    r = subprocess.run(["pdftotext", path, "-"], capture_output=True, text=True)
    if r.returncode != 0:
        return ["pdftotext failed — could not verify the artwork"]
    # Compare with whitespace, case and typographic variants all folded away.
    # Four separate things in this artwork break a naive substring match, and
    # every one is a rendering artefact rather than missing copy:
    #   · line breaks split a sentence anywhere
    #   · `text-transform:uppercase` — the source case is not the printed case
    #   · `letter-spacing` makes pdftotext emit "T E M P L AT E" for "TEMPLATE"
    #   · `&rsquo;` is written as an entity but PRINTS as ’ (U+2019), so a probe
    #     carrying an ASCII apostrophe never matches the extracted text
    _FOLD = str.maketrans({
        "’": "'", "‘": "'", "“": '"', "”": '"',
        "—": "-", "–": "-", "−": "-", " ": "",
        " ": "", "²": "2", "·": "·",
    })

    def norm(s):
        return re.sub(r"\s+", "", (s or "").translate(_FOLD)).lower()

    got = norm(r.stdout)

    pages = r.stdout.count("\f")
    problems = []
    if pages != 2:
        problems.append(f"expected a 2-page A4 duplex, got {pages} page(s)")

    # Page 1 has a hard vertical budget. Text extraction proves copy EXISTS in
    # the PDF; it cannot prove the copy is visible, because the CTA band is
    # absolutely positioned and will happily render on top of an overlong
    # paragraph. So the flowing copy is also budgeted by length.
    # Support cards are ~55mm × 22mm. Overflowing them does not clip — the
    # label simply wraps onto an extra line and renders ON TOP of the sub. That
    # is invisible to text extraction (both strings are present in the PDF), so
    # a length budget is the only check that catches it.
    # Number/verb agreement. Every count on this page is data-driven, so a
    # string that reads correctly for n=3 can be wrong for n=1 and no one sees
    # it until a property with n=1 comes along. This has now shipped twice —
    # "3 buyers may weigh against it" and "1 Home ... that closely compete with
    # yours" — so it is worth a check rather than another pair of eyes.
    agreement = [
        (r"\b1 [A-Za-z]+s\b(?! ago)", "'1' followed by a plural noun"),
        (r"\b1 [A-Za-z]+ (?:for sale )?that closely compete\b", "singular subject with 'compete'"),
        (r"\b1 (?:thing|home|listing|property) [^.]{0,40}\b(?:are|have|were)\b",
         "singular subject with a plural verb"),
    ]
    for txt in [strip(ctx["hero"].hero_headline), strip(ctx["hero"].label),
                strip(ctx["hero"].sub), strip(ctx["also"]), strip(ctx["cta2_head"]),
                strip(ctx["cta2_then"]), strip(ctx["competition_sentence"]),
                strip(ctx["peek_1"])] + \
               [strip(f.label) for f in ctx["support"]] + \
               [strip(f.sub) for f in ctx["support"]]:
        for pat, why in agreement:
            m = re.search(pat, txt or "", re.I)
            if m:
                problems.append(f"number agreement — {why}: {m.group(0)!r} in {txt[:70]!r}")

    for f in ctx["support"]:
        for part, text, limit in (("label", strip(f.label), 52),
                                  ("sub", strip(f.sub), 78)):
            if len(text) > limit:
                problems.append(
                    f"{f.kind} card {part} is {len(text)} chars, over the {limit}-char "
                    f"support-card budget — it will overlap the line below")

    for name, text, limit in (
        ("hero headline", strip(ctx["hero"].hero_headline), 105),
        ("consequence", strip(ctx["hero"].hero_consequence), 190),
        ("also line", strip(ctx["also"]), 215),
        ("proof line", strip(ctx["proof"]), 210),
    ):
        if len(text or "") > limit:
            problems.append(
                f"{name} is {len(text)} chars, over the {limit}-char page-1 budget "
                f"— it will render under the CTA band")

    required = {
        "hero headline": strip(ctx["hero"].hero_headline),
        "consequence line": strip(ctx["hero"].hero_consequence),
        "hero card label": strip(ctx["hero"].label),
        "proof line": strip(ctx["proof"]),
        "also line": strip(ctx["also"]),
        "CTA headline": strip(ctx["cta_head"]),
        "image caption": "and its parcel",
        "friction remover": "No login.",
        "back-page Q1": "what would buyers",
        "back-page Q4": "What could strengthen",
        "page-2 CTA": strip(ctx["cta2_head"]),
        "skim prompt 01": strip(ctx["peek_1"]).replace("→", "").strip(),
        "skim prompt 04": "See the strengths and trade-offs",
        "objection: not a template": "Not a suburb",
        "objection: not an algorithm": "Not just an",
        "objection: not a snapshot": "Not a one-off",
        "objection: not a funnel": "Not a sales",
    }
    for name, text in required.items():
        probe = norm(text)[:60]
        if probe and probe not in got:
            problems.append(f"missing from artwork ({name}): {strip(text)[:70]!r}")

    # Check the SUB lines too, not just the labels. Verifying only labels let a
    # whole class of defect hide: the support cards were undersized, so their
    # sub-text was being clipped by the card's own bounds on several mailers
    # while the label above it rendered fine and the check passed.
    for f in ctx["support"] + [ctx["hero"]]:
        for part, text in (("label", f.label), ("sub", f.sub)):
            if norm(strip(text))[:60] not in got:
                problems.append(
                    f"{f.kind} card {part} clipped or missing: {strip(text)[:70]!r}")
    return problems


def audit(col):
    """Score every complete report without generating anything.

    Answers the two questions that decide a print run: how many addresses can we
    actually mail, and what would each of them lead with.
    """
    docs = list(col.find({"build_state": "complete"}))
    ready, blocked = [], []
    for d in docs:
        reasons = check_ready(d)
        (blocked if reasons else ready).append((d, reasons))
    print(f"{len(docs)} complete reports · {len(ready)} mailable · {len(blocked)} blocked\n")
    print("MAILABLE — what each would lead with:")
    lead_counts = {}
    for d, _ in ready:
        try:
            hero, support, _c = select(d)
            lead_counts[hero.kind] = lead_counts.get(hero.kind, 0) + 1
            print(f"  {d['slug']:<42} {hero.kind:<22} +{', '.join(f.kind for f in support)}")
        except ValueError as e:
            print(f"  {d['slug']:<42} NO HERO FINDING — {e}")
    print("\n  lead distribution:", dict(sorted(lead_counts.items(), key=lambda x: -x[1])))
    print(f"\nBLOCKED ({len(blocked)}):")
    tally = {}
    for d, reasons in blocked:
        for r in reasons:
            key = r.split("(")[0].strip()
            tally[key] = tally.get(key, 0) + 1
    for k, v in sorted(tally.items(), key=lambda x: -x[1]):
        print(f"  {v:3d}  {k}")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--slug", nargs="+")
    ap.add_argument("--all-ready", action="store_true",
                    help="every address passing the V2 readiness gate")
    ap.add_argument("--combine", action="store_true")
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--audit", action="store_true")
    ap.add_argument("--force", action="store_true",
                    help="generate despite readiness failures (proofing only — never post these)")
    args = ap.parse_args()

    col = get_client()["system_monitor"]["property_reports"]
    if args.audit:
        return audit(col)
    if not args.slug and not args.all_ready:
        ap.error("pass --slug <slug...>, --all-ready, or --audit")

    if args.slug:
        docs = list(col.find({"slug": {"$in": args.slug}}))
    else:
        docs = [d for d in col.find({"build_state": "complete"}) if not check_ready(d)]
    if not docs:
        print("No matching reports.")
        return

    print(f"{'DRY RUN — ' if args.dry_run else ''}generating {len(docs)} V2 mailer(s):\n")
    pdfs, skipped = [], 0
    for d in docs:
        reasons = check_ready(d)
        if reasons and not args.force:
            print(f"  ✗ {d.get('slug')}: not ready — {'; '.join(reasons)}")
            skipped += 1
            continue
        if reasons:
            print(f"  ! {d.get('slug')}: FORCED despite — {'; '.join(reasons)}")
        try:
            p = render(build_context(d), dry=args.dry_run)
            if p:
                pdfs.append(p)
        except Exception as e:
            print(f"  ✗ {d.get('slug')}: {e}")
            skipped += 1

    if args.combine and pdfs:
        from pypdf import PdfWriter
        w = PdfWriter()
        for p in pdfs:
            w.append(p)
        combined = os.path.join(OUT, "all_mailers_v2.pdf")
        with open(combined, "wb") as f:
            w.write(f)
        print(f"\nCombined → {combined} ({len(pdfs)} recipients)")

    print(f"\nDone. {len(pdfs)} PDF(s), {skipped} skipped.")
    # A run that produces nothing is a failure, not an empty queue (CLAUDE.md 7b)
    if not args.dry_run and not pdfs and docs:
        raise SystemExit(f"produced 0 mailers from {len(docs)} candidate report(s)")


if __name__ == "__main__":
    main()
