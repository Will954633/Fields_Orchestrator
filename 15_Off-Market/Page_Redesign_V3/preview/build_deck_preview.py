#!/usr/bin/env python3
"""
build_deck_preview.py — assemble the local V3 deck preview.

Renders the REAL deck for a real slug: card copy comes from the
`system_monitor.offmarket_discovery` document, not from a mockup, so what you
review is what the reader gets. Cards 00–04 for now; 05–10 are unchanged from
the live deck and are not part of the V3 work.

The intro is a fixed full-screen overlay that lives in the SAME document as the
deck, not an iframe: it releases a scroll lock and then scrolls the real page to
card 00, and neither works cleanly across a frame boundary. So rather than
keeping a second copy of it, this injects the deck's markup into
`intro/matrix-intro.html`. The intro stays the single source.

Run:
  set -a && source /home/fields/Fields_Orchestrator/.env && set +a
  python3 intro_tokens.py --slug <slug> --out tokens.json    # once per home
  python3 build_deck_preview.py [--slug <slug>]

Then: https://vm.fieldsestate.com.au/concepts/off-market-v3/preview/deck.html
"""

from __future__ import annotations

import argparse
import html
import json
import os
import re
import subprocess
import sys
from pathlib import Path

import yaml
from pymongo import MongoClient

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "intro"))
import intro_tokens  # noqa: E402

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent
INTRO = ROOT / "intro" / "matrix-intro.html"
MEDIA = ROOT / "angle_media.yaml"
OUT = HERE / "deck.html"

# ── the claim step ────────────────────────────────────────────────────────────
# The reader texts US to claim their site, so the whole thing hangs off one
# number. This is Will's JustCall line, given 2026-08-04 and verified against
# GET /v2.1/phone-numbers: number_type Mobile, sms_compliance Verified,
# capabilities call/sms/mms all Yes, owner will.simpson@blueoceans.com.au.
#
# IT IS A LIVE NUMBER. Anything built here now reaches a real handset, so a test
# send is a real message to a real person — it needs asking for, not assuming.
SMS_NUMBER = "+61440131629"            # E.164, what the sms: link dials
SMS_NUMBER_DISPLAY = "0440 131 629"    # what a human reads
SMS_NUMBER_IS_PLACEHOLDER = False
TOKENS = HERE / "tokens.json"

# land_prestige, so the retriever appears and its ball can demonstrate the
# card 03 -> 04 detach. Override with --slug.
DEFAULT_SLUG = "16-moorabbin-place-robina"

E = lambda s: html.escape(str(s or ""), quote=False)


# ── data ─────────────────────────────────────────────────────────────────────

def load_doc(slug: str) -> dict:
    uri = os.environ.get("COSMOS_CONNECTION_STRING")
    if not uri:
        raise SystemExit("COSMOS_CONNECTION_STRING not set — "
                         "set -a && source /home/fields/Fields_Orchestrator/.env && set +a")
    doc = MongoClient(uri)["system_monitor"]["offmarket_discovery"].find_one({"slug": slug})
    if not doc:
        raise SystemExit(f"no deck doc for slug: {slug}")
    return doc


def pick_emblem(doc: dict, cfg: dict) -> dict | None:
    """Which drawing this home gets. `lead_angle` is already on every doc and is
    currently unread by React — no builder change needed."""
    angle = doc.get("lead_angle")
    if angle in cfg.get("text_only", []):
        return None
    entry = (cfg.get("angles") or {}).get(angle)
    if not entry:
        return None
    stem = entry["emblem"]
    # parkland and water_adjacent cover visually different things depending on
    # the OSM kind that triggered them — a golf course is not a park.
    kind = ((doc.get("green_space") or {}).get("premium") or {}).get("kind")
    routed = (cfg.get("kind_routes") or {}).get(angle, {}).get(kind)
    if routed:
        stem = routed
        entry = {**entry, **(cfg.get("emblems_by_kind") or {}).get(stem, {})}
    reveal = (cfg.get("reveals") or {}).get(stem, {})
    return {"stem": stem, "caption": entry.get("caption") or "",
            "detach": entry.get("detach"), "mode": reveal.get("mode", "develop"),
            "angle": angle, "kind": kind}


# ── card renderers ───────────────────────────────────────────────────────────

def card_shell(n: int, total: int, body: str, wide: bool, extra_id: str = "",
               bare: bool = False) -> str:
    """`bare` means the body brings its own wrapper — cards 05-10 want
    `.inner.stagger` so their content arrives line by line, where 01-04 use the
    plain wrapper the live deck uses."""
    chap = f'<div class="chapter">{n:02d}&nbsp;&nbsp;/&nbsp;&nbsp;{total:02d}</div>'
    # Every card gets an id. Cards 05-10 had none, so anything addressing them by
    # id silently no-opped — the screenshot pass scrolled nowhere and shot card
    # 04 five times over without erroring.
    cid = extra_id or "card-%02d" % n
    idattr = f' id="{cid}"' 
    body = body.replace("{CHAPTER}", chap)
    if bare:
        return f'  <section class="card reveal"{idattr} data-n="{n}">\n{body}  </section>\n'
    inner = "innerWide" if wide else "inner"
    return (f'  <section class="card reveal"{idattr} data-n="{n}">\n'
            f'    <div class="{inner}">\n{body}    </div>\n  </section>\n')


def render_01(c: dict, doc: dict, total: int) -> str:
    creds = "".join(
        f'        <li><span class="fig">{E(x.get("fig"))}</span> {E(x.get("text"))}</li>\n'
        for x in c.get("credibility") or [])
    # The matrix has just printed this address, so the headline no longer
    # announces the find — the address settles in above it as an anchor.
    body = (f'      {{CHAPTER}}\n'
            f'      <p class="place">{E(c.get("address"))}</p>\n'
            f'      <h1>Then we went to work.</h1>\n'
            f'      <p class="lede">{E(c.get("lede"))}</p>\n'
            f'      <ul class="cred">\n{creds}      </ul>\n'
            f'      <span class="next">↓ {E(c.get("next"))}</span>\n')
    return card_shell(c["n"], total, body, wide=False, extra_id="card-01")


def render_02(c: dict, total: int) -> str:
    # Two columns with an EMPTY right cell, so the text column's left edge does
    # not jump when the drawing arrives on card 03. Without it the copy slides
    # sideways and the emblem reads as a layout change rather than as something
    # arriving beside copy that stayed put.
    body = (f'      <div class="colText stagger">\n'
            f'        {{CHAPTER}}\n'
            f'        <p class="answer">{E(c.get("answer"))}</p>\n'
            f'        <h2>{E(c.get("headline"))}</h2>\n'
            f'        <p class="p">{E(c.get("body"))}</p>\n'
            f'        <span class="next">↓ {E(c.get("next"))}</span>\n'
            f'      </div>\n'
            f'      <div class="colEmpty" aria-hidden="true"></div>\n')
    return card_shell(c["n"], total, body, wide=True, extra_id="card-02")


def render_03(c: dict, total: int, em: dict | None) -> str:
    bits = [f'        {{CHAPTER}}',
            f'        <p class="answer">{E(c.get("answer"))}</p>',
            f'        <h2>{E(c.get("lead"))}</h2>']
    if c.get("boundary_line"):
        bits.append(f'        <p class="p">{E(c["boundary_line"])}</p>')
    if c.get("features"):
        bits.append(f'        <div class="label">{E(c.get("features_intro"))}</div>')
        bits.append('        <ul class="ticks">' +
                    "".join(f'<li>{E(f)}</li>' for f in c["features"]) + '</ul>')
    if c.get("rarity"):
        bits.append(f'        <div class="rare">{E(c["rarity"])}</div>')
    if c.get("doorstep"):
        bits.append(f'        <div class="label">{E(c.get("doorstep_intro"))}</div>')
        # No <b> when there is no distance — the "a short drive to X (1.2km)"
        # entries are a sentence, not a measurement. Matches DiscoveryDeck.tsx:141.
        def _step(d):
            dist = d.get("dist")
            lead = f"<b>{E(dist)}</b> " if dist else ""
            return f'<li>{lead}{E(d.get("name"))}</li>'
        rows = "".join(_step(d) for d in c["doorstep"])
        bits.append(f'        <ul class="doorstep">{rows}</ul>')
    if c.get("insight"):
        bits.append(f'        <p class="insight">{E(c["insight"])}</p>')
    bits.append(f'        <span class="next">↓ {E(c.get("next"))}</span>')

    media = '      <div class="colEmpty" aria-hidden="true"></div>\n'
    if em:
        # No src and preload="none" on purpose: with preload="auto" the clip
        # downloads on first paint while the reader is still on card 02, whether
        # or not they ever scroll far enough to see it. It is attached on the
        # reader's first scroll gesture instead.
        media = (
            f'      <figure class="media" id="media">\n'
            f'        <div class="mediaGlow" aria-hidden="true"></div>\n'
            f'        <div class="mediaFrame">\n'
            f'          <video id="emblem" muted playsinline preload="none"\n'
            f'                 data-src="media/{em["stem"]}.mp4"\n'
            f'                 aria-label="{E(em["caption"])}"></video>\n'
            # Covers the fruit's spot on the held final frame the moment it
            # detaches, so the tree is not left wearing the fruit that just fell
            # off it. Cloned from the video's own pixels rather than re-inverted
            # from the master, so it matches the encode exactly.
            + (f'          <img class="fruitPatch" id="fruitPatch"\n'
               f'               src="media/fruit_patch.png" alt="" aria-hidden="true">\n'
               if em.get("detach") == "fruit" else "")
            + f'        </div>\n'
            f'        <figcaption class="caption"><span>{E(em["caption"])}</span>\n'
            f'          <button class="replay" id="replay" type="button">Replay</button>\n'
            f'        </figcaption>\n'
            f'      </figure>\n')
    body = f'      <div class="colText stagger">\n' + "\n".join(bits) + "\n      </div>\n" + media
    return card_shell(c["n"], total, body, wide=True, extra_id="card-03")


def render_04(c: dict, total: int) -> str:
    bits = [f'        {{CHAPTER}}',
            f'        <p class="answer">{E(c.get("answer"))}</p>',
            f'        <h2>{E(c.get("headline"))}</h2>']
    f = c.get("filters") or {}
    if f.get("body"):
        bits.append(f'        <p class="p">{E(f["body"])}</p>')
    if f.get("items"):
        bits.append(f'        <div class="label">{E(f.get("intro"))}</div>')
        bits.append('        <ul class="ticks">' +
                    "".join(f'<li>{E(i)}</li>' for i in f["items"]) + '</ul>')
    if c.get("close") or f.get("close"):
        bits.append(f'        <p class="p">{E(c.get("close") or f.get("close"))}</p>')
    w = c.get("wait") or {}
    if w.get("line"):
        bits.append(f'        <div class="weight"><p>{E(w.get("intro"))}</p>'
                    f'<small>{E(w["line"])}</small></div>')
    bits.append(f'        <span class="next">↓ {E(c.get("next"))}</span>')
    body = (f'      <div class="colFruit" aria-hidden="true"></div>\n'
            f'      <div class="colText stagger">\n' + "\n".join(bits) + "\n      </div>\n")
    return card_shell(c["n"], total, body, wide=True, extra_id="card-04")



def render_05(c: dict, total: int) -> str:
    rows = ""
    steps = c.get("funnel") or []
    for i, f in enumerate(steps):
        cls = " final" if f.get("final") or i == len(steps) - 1 else ""
        rows += (f'<div class="tier{cls}"><span class="k">{E(f.get("label"))}</span>'
                 f'<span class="v">{E(f.get("value"))}</span></div>')
        if i < len(steps) - 1:
            rows += '<div class="drop" aria-hidden="true">↓</div>'
    bits = [f'        {{CHAPTER}}',
            f'        <p class="answer">{E(c.get("answer"))}</p>',
            f'        <h2>{E(c.get("headline"))}</h2>',
            f'        <div class="funnel">{rows}</div>']
    if c.get("none_note"):
        bits.append(f'        <p class="p">{E(c["none_note"])}</p>')
    bits.append(f'        <span class="next">↓ {E(c.get("next"))}</span>')
    return card_shell(c["n"], total, "      <div class=\"inner stagger\">\n"
                      + "\n".join(bits) + "\n      </div>\n", wide=False, bare=True)


def render_06(c: dict, total: int) -> str:
    comp = c.get("comp") or {}
    deltas = "".join(f'<li>{E(d)}</li>' for d in comp.get("deltas") or [])
    dist = f' · {comp["distance_m"]}m away' if comp.get("distance_m") else ""
    bits = [f'        {{CHAPTER}}',
            f'        <p class="answer">{E(c.get("answer"))}</p>',
            f'        <h2>{E(c.get("looks"))}</h2>',
            f'        <div class="comp"><div class="compHead">'
            f'<span class="addr">{E(comp.get("address"))}</span>'
            f'<span class="price">{E(comp.get("price"))}</span></div>'
            f'<div class="compMeta">Sold{E(dist)}</div></div>',
            f'        <div class="label">{E(c.get("reveal_intro"))}</div>',
            f'        <ul class="deltas">{deltas}</ul>',
            f'        <p class="p">{E(c.get("close"))}</p>']
    if c.get("insight"):
        bits.append(f'        <p class="insight">{E(c["insight"])}</p>')
    bits.append(f'        <span class="next">↓ {E(c.get("next"))}</span>')
    return card_shell(c["n"], total, "      <div class=\"inner stagger\">\n"
                      + "\n".join(bits) + "\n      </div>\n", wide=False, bare=True)


def render_07(c: dict, total: int) -> str:
    def col(block, cls):
        if not block:
            return ""
        items = "".join(f'<li>{E(i)}</li>' for i in block.get("items") or [])
        return (f'<div class="drv {cls}"><div class="label">{E(block.get("intro"))}</div>'
                f'<ul>{items}</ul></div>')
    bits = [f'        {{CHAPTER}}',
            f'        <p class="answer">{E(c.get("answer"))}</p>',
            f'        <div class="drivers">{col(c.get("strengthens"), "up")}'
            f'{col(c.get("negotiate"), "down")}</div>',
            f'        <p class="p">{E(c.get("close"))}</p>']
    if c.get("insight"):
        bits.append(f'        <p class="insight">{E(c["insight"])}</p>')
    bits.append(f'        <span class="next">↓ {E(c.get("next"))}</span>')
    return card_shell(c["n"], total, "      <div class=\"inner stagger\">\n"
                      + "\n".join(bits) + "\n      </div>\n", wide=False, bare=True)


def render_08(c: dict, total: int) -> str:
    bits = [f'        {{CHAPTER}}',
            f'        <p class="answer">{E(c.get("answer"))}</p>',
            f'        <h2>{E(c.get("portrait"))}</h2>']
    if c.get("fit"):
        bits.append(f'        <p class="p">{E(c["fit"])}</p>')
    if c.get("reframe"):
        bits.append(f'        <div class="weight"><p>{E(c["reframe"])}</p></div>')
    bits.append(f'        <span class="next">↓ {E(c.get("next"))}</span>')
    return card_shell(c["n"], total, "      <div class=\"inner stagger\">\n"
                      + "\n".join(bits) + "\n      </div>\n", wide=False, bare=True)


def render_09(c: dict, total: int) -> str:
    basis = "".join(f'<li>{E(b)}</li>' for b in c.get("basis") or [])
    bits = [f'        {{CHAPTER}}',
            f'        <p class="answer">{E(c.get("answer"))}</p>',
            f'        <div class="label">{E(c.get("likely_intro"))}</div>',
            f'        <div class="anchor">{E(c.get("anchor"))}</div>',
            f'        <div class="label">{E(c.get("range_intro"))}</div>',
            f'        <div class="range">{E(c.get("range"))}</div>']
    if c.get("range_note"):
        bits.append(f'        <p class="rangeNote">{E(c["range_note"])}</p>')
    if c.get("tier_caveat"):
        bits.append(f'        <p class="rangeNote">{E(c["tier_caveat"])}</p>')
    if basis:
        bits.append(f'        <div class="label">Based on</div><ul class="ticks">{basis}</ul>')
    if c.get("closing"):
        bits.append(f'        <p class="p">{E(c["closing"])}</p>')
    bits.append(f'        <span class="next">↓ {E(c.get("next"))}</span>')
    return card_shell(c["n"], total, "      <div class=\"inner stagger\">\n"
                      + "\n".join(bits) + "\n      </div>\n", wide=False, bare=True)


def render_10(c: dict, total: int) -> str:
    avoid = "".join(f'<li>{E(a)}</li>' for a in c.get("avoid") or [])
    bits = [f'        {{CHAPTER}}',
            f'        <p class="answer">{E(c.get("answer"))}</p>',
            f'        <h2>{E(c.get("frame_line"))}</h2>',
            f'        <p class="p">{E(c.get("lead_line"))}</p>']
    if avoid:
        bits.append(f'        <div class="label">What we would not lead on</div>'
                    f'<ul class="avoid">{avoid}</ul>')
    # Card 10's `next` is null in the data — the CTA used to carry the flow, and
    # that moved to card 11, leaving the only card in the deck with nothing
    # pointing forward. Static here rather than in the document because the card
    # it points at is static too. deck.js turns it into a link by DOM order.
    # A question in the seller's voice, like every other cue in the deck — the
    # register should not change at the exact moment the deck starts asking.
    bits.append('        <span class="next">↓ What else is there?</span>')
    # No CTA here any more — card 11 is the ask, and two buttons back to back
    # would make the reader choose between them rather than continue.
    return card_shell(c["n"], total, "      <div class=\"inner stagger\">\n"
                      + "\n".join(bits) + "\n      </div>\n", wide=False, bare=True)


# The offer. Identical for every property — nothing here is generated — so it
# lives in the builder like card 00 rather than in the deck document.
INSIDE = [
    "Every photo analysed",
    "Your strongest buyer groups",
    "Updated competing homes",
    "Full valuation with every adjustment explained",
    "The buyers most likely to compete for your home",
    "Your recommended selling strategy",
    "Answers to the major selling decisions",
    "A private message line with Will",
]


def render_11(n: int, total: int) -> str:
    ticks = "".join(f"<li>{E(t)}</li>" for t in INSIDE)
    bits = [
        '        {CHAPTER}',
        # The deck's pattern is a short lead-in ABOVE the heading — every other
        # card reads that way, so putting this line below would break the rhythm
        # at the one moment we are asking for something.
        "        <p class=\"answer\">You&rsquo;ve just seen the discoveries that "
        "stood out first.</p>",
        '        <h2>Would you like to go deeper?</h2>',
        "        <p class=\"p\">We&rsquo;ll now build a private website dedicated "
        "entirely to your home.</p>",
        "        <p class=\"p\">It takes around 3 minutes because every section is "
        "generated specifically for your property&mdash;not loaded from a "
        "template.</p>",
        "        <div class=\"label\">Inside you&rsquo;ll find:</div>"
        f'<ul class="ticks">{ticks}</ul>',
        "        <p class=\"ready\">We&rsquo;re now ready to build your home&rsquo;s "
        "private website.</p>",
        # The clock is a masked SVG, not the U+23F1 stopwatch character. That
        # glyph is missing from plenty of font stacks and renders as a tofu box
        # — it did exactly that on the first build here.
        '        <p class="buildTime">Estimated build time: around 3 minutes</p>',
        # The neon tube, from Concepts/illuminus_sign_concept/button.html.
        # Two stacked copies of the word: `.neonGlass` is the unlit tube and
        # never changes, `.neonLit` is the discharge. Both are real text — the
        # link reads correctly to a screen reader and to Google.
        '        <div class="neonWrap">',
        '          <span class="neonBounce" aria-hidden="true"></span>',
        '          <a class="neon" href="#build-strategy">',
        '            <svg class="neonFrame" aria-hidden="true"></svg>',
        '            <span class="neonWord">',
        '              <span class="neonGlass" aria-hidden="true">Start building</span>',
        '              <span class="neonLit">Start building</span>',
        '            </span>',
        '          </a>',
        '        </div>',
    ]
    return card_shell(n, total, "      <div class=\"inner stagger\">\n"
                      + "\n".join(bits) + "\n      </div>\n", wide=False,
                      bare=True, extra_id="card-11")


RENDERERS = {
    "competition": render_05, "comparable": render_06, "value_drivers": render_07,
    "buyer": render_08, "valuation": render_09, "strategy": render_10,
}


# Pressing the neon runs the shatter instead of following its href. It stays a
# real anchor so it is keyboard-operable and announces itself as a link; the
# preventDefault is here rather than in outro-deck.js so the module stays
# reusable and the deck owns the decision.
OUTRO_WIRE = """<script>
(() => {
  "use strict";
  const cta = document.querySelector(".neon");
  if (!cta) return;

  // Fetch the 1.9MB of crack artwork when the offer card comes into view, not at
  // page load. Ready by the time anyone presses; never downloaded at all by a
  // reader who leaves earlier.
  const card = document.getElementById("card-11");
  if (card) {
    const io = new IntersectionObserver((es) => {
      for (const e of es) if (e.isIntersecting) { io.disconnect(); FieldsCrack.preload(); }
    }, { rootMargin: "0px 0px 60% 0px" });
    io.observe(card);
  }
  const go = (e) => {
    e.preventDefault();
    if (FieldsOutro.running) return;
    // Strike where the finger actually landed. A keyboard activation has no
    // coordinates, so fall back to the centre of the button itself.
    const r = cta.getBoundingClientRect();
    const x = e.clientX || (r.left + r.width / 2);
    const y = e.clientY || (r.top + r.height / 2);
    FieldsOutro.play(x, y);
  };
  cta.addEventListener("click", go);
})();
</script>
"""


# ── assembly ─────────────────────────────────────────────────────────────────

CHAPTER_RE = re.compile(
    r'(<div class="chapter">)\d+(&nbsp;&nbsp;/&nbsp;&nbsp;)\d+(</div>)')


def renumber(card_html: str, n: int, total: int) -> str:
    """Number cards by the order they actually RENDER.

    The emitter's `n` is a slot index and it drops cards it has no data for, so
    a nine-card deck was printing "10 / 09" on its last card and skipping 06
    entirely. The reader is counting sections on a screen, not slots in a
    schema. Rewriting the chapter here keeps every renderer untouched.
    """
    return CHAPTER_RE.sub(
        lambda m: f"{m.group(1)}{n:02d}{m.group(2)}{total:02d}{m.group(3)}",
        card_html, count=1)


def build_deck_html(doc: dict, em: dict | None) -> str:
    by_type = {c["type"]: c for c in doc["cards"]}
    # Count what will actually render, +1 for the offer card, BEFORE emitting —
    # the denominator has to be right on card 01.
    total = (sum(1 for t in ("recognition", "hook", "reveal", "explanation")
                 if t in by_type)
             + sum(1 for c in doc["cards"] if c["type"] in RENDERERS)
             + 1)
    seq = 0
    out = ['<main id="deck">\n',
           # CARD 00 — headline only, unnumbered on purpose. The matrix ends on a
           # machine statement (an address in code); this is the human voice
           # arriving, and it only carries that if nothing shares the screen.
           '  <section class="card reveal" id="card-00">\n'
           '    <span class="glow" aria-hidden="true"></span>\n'
           '    <div class="inner"><h1>We found your home.</h1></div>\n'
           '  </section>\n']
    if "recognition" in by_type:
        seq += 1; out.append(renumber(render_01(by_type["recognition"], doc, total), seq, total))
    if "hook" in by_type:
        seq += 1; out.append(renumber(render_02(by_type["hook"], total), seq, total))
    if "reveal" in by_type:
        seq += 1; out.append(renumber(render_03(by_type["reveal"], total, em), seq, total))
    if "explanation" in by_type:
        seq += 1; out.append(renumber(render_04(by_type["explanation"], total), seq, total))
    # 05-10 in the order the builder emits them, skipping any the emitter
    # dropped for want of data — which is why `n` can reach 10 on a deck that
    # renders 9 cards.
    for card in doc["cards"]:
        fn = RENDERERS.get(card["type"])
        if fn:
            seq += 1
            out.append(renumber(fn(card, total), seq, total))
    seq += 1
    out.append(render_11(seq, total))
    out.append("</main>\n")
    return "".join(out)


def claim_config(doc: dict) -> str:
    """The `window.__FIELDS_CLAIM` blob: address, number, and a prebuilt QR.

    THE QR IS BUILT HERE, NOT IN THE BROWSER. The message is address-specific, so
    it has to be generated per deck anyway, and generating it at build time means
    no QR library ships to the reader and nothing is fetched at runtime — which
    the artifact CSP would block regardless.

    TWO DIFFERENT ENCODINGS, ON PURPOSE. The in-page button uses an `sms:` URI,
    where iOS wants `sms:NUMBER&body=` and everyone else wants `?body=` —
    claim.js picks per device. A QR code cannot pick, because it is scanned by a
    phone we know nothing about, so it uses `SMSTO:NUMBER:MESSAGE`, the format
    QR readers have agreed on for exactly this reason.

    UNVERIFIED: nothing here has been scanned by a real phone. The QR path needs
    testing on both an iPhone and an Android before it goes anywhere near a
    reader — see CLAIM_STEP.md.
    """
    import segno

    address = doc.get("address_short") or ""
    body = f"SEND {address}"
    qr = segno.make(f"SMSTO:{SMS_NUMBER}:{body}", error="m")
    svg = qr.svg_inline(scale=4, border=2, dark="#000000", light="#ffffff")
    return ("<script>window.__FIELDS_CLAIM = {"
            f" address: {json.dumps(address)},"
            f" number: {json.dumps(SMS_NUMBER)},"
            f" numberDisplay: {json.dumps(SMS_NUMBER_DISPLAY)},"
            f" placeholder: {json.dumps(SMS_NUMBER_IS_PLACEHOLDER)},"
            f" qr: {json.dumps(svg)} }};</script>\n")


def locality_of(doc: dict) -> str:
    """Suburb, state and postcode — NOT the street address.

    The intro prints STREET then LOCALITY on consecutive lines. Passing the
    deck's `cards[0].address` here (which is "16 Moorabbin Place, Robina")
    made the field print the address twice, once bare and once with the suburb
    appended.
    """
    suburb = doc.get("suburb_display") or ""
    pc = intro_tokens.POSTCODE.get(doc.get("suburb_key") or "", "")
    return f"{suburb}, QLD {pc}".strip().rstrip(",")


def build_one(slug: str, out_path: Path, cfg: dict) -> dict:
    doc = load_doc(slug)
    em = pick_emblem(doc, cfg)
    if em and not (HERE / "media" / f"{em['stem']}.mp4").exists():
        print(f"  ! media/{em['stem']}.mp4 missing — run reveals/render_all_decks.sh")

    # Per-home recognition tokens, generated here rather than read from a file:
    # a stale tokens.json would silently rain another home's streets, which is
    # exactly the bug this replaced.
    tok = json.dumps(intro_tokens.build(slug), separators=(",", ":"))

    html_ = INTRO.read_text()
    assert "</head>" in html_ and "<script>" in html_ and "</body>" in html_, \
        "intro markup changed shape"
    # Assets sit beside deck.html; the examples live one level down.
    rel = "../" if out_path.parent != HERE else ""
    css = (HERE / "deck.css").read_text()
    js = (HERE / "deck.js").read_text()
    deck = build_deck_html(doc, em).replace('src="media/', f'src="{rel}media/') \
                                   .replace('data-src="media/', f'data-src="{rel}media/')
    cfg_js = ('<script>window.__FIELDS_INTRO = {'
              f' street: {json.dumps(doc.get("address_short"))},'
              f' locality: {json.dumps(locality_of(doc))},'
              f' tokens: {tok} }};</script>\n')
    js += "<script>\n" + (HERE / "neon_cta.js").read_text() + "</script>\n"

    # The outro. Assets resolve against the DOCUMENT, so the base has to be set
    # before crack.js and signal-bed.js load — the deck sits two directories
    # below them.
    outro = ROOT / "outro"
    js += (f'<script>window.FIELDS_OUTRO_BASE = "{rel}../outro/";</script>\n'
           + "<script>\n" + (outro / "glass-audio.js").read_text() + "</script>\n"
           + "<script>\n" + (outro / "signal-bed.js").read_text() + "</script>\n"
           + "<script>\n" + (outro / "crack.js").read_text() + "</script>\n"
           + "<script>\n" + (outro / "outro-deck.js").read_text() + "</script>\n"
           + claim_config(doc)
           + "<script>\n" + (outro / "claim.js").read_text() + "</script>\n"
           + OUTRO_WIRE)

    # The fruit leaving the tree only exists for the pandanus. The other seven
    # emblems have nothing that could plausibly detach, so they get no script at
    # all rather than a disabled one — see fruit_roll.js and PLAN.md.
    if em and em.get("detach") == "fruit":
        js += "<script>\n" + (HERE / "fruit_roll.js").read_text().replace(
            '"../media/', f'"{rel or "./"}media/') + "</script>\n"

    html_ = html_.replace("</head>", css + "</head>", 1)
    html_ = html_.replace("<script>", cfg_js + "<script>", 1)
    html_ = html_.replace("</body>", deck + js + "</body>", 1)
    html_ = html_.replace("<title>Digital Rain — Local Recognition Sequence</title>",
                          f"<title>{E(doc.get('address_short'))}, "
                          f"{E(doc.get('suburb_display'))} — Fields</title>", 1)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(html_)
    return {"slug": slug, "suburb": doc.get("suburb_display"),
            "address": doc.get("address_short"), "angle": doc.get("lead_angle"),
            "emblem": em["stem"] if em else None, "cards": len(doc["cards"]),
            "kb": round(out_path.stat().st_size / 1024)}


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--slug", default=DEFAULT_SLUG)
    ap.add_argument("--all", action="store_true",
                    help="build every slug in Page_Redesign_V2/output into examples/")
    a = ap.parse_args()
    cfg = yaml.safe_load(MEDIA.read_text())

    if not a.all:
        r = build_one(a.slug, OUT, cfg)
        print(f"{r['slug']}  angle={r['angle']}  emblem={r['emblem'] or 'none (text-only)'}"
              f"  cards={r['cards']}  {r['kb']} KB")
        return

    src = ROOT.parent / "Page_Redesign_V2" / "output"
    slugs = sorted(p.stem for p in src.glob("*.md") if p.stem not in ("ALL", "INDEX"))
    rows = []
    for slug in slugs:
        try:
            r = build_one(slug, HERE / "examples" / f"{slug}.html", cfg)
        except SystemExit as e:
            print(f"  ! {slug}: {e}")
            continue
        rows.append(r)
        print(f"  {r['address']:<26} {r['suburb']:<16} {r['angle']:<15} "
              f"{r['emblem'] or '—':<9} {r['cards']:>2} cards  {r['kb']:>3} KB")
    (HERE / "examples" / "index.json").write_text(json.dumps(rows, indent=2))
    print(f"\nwrote {len(rows)} examples to preview/examples/")


if __name__ == "__main__":
    main()
