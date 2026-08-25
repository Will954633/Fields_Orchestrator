#!/usr/bin/env python3
"""Owner-Subject Article -> printable direct-mail PDF with a per-address QR code.

This is a THIN BRANCH over `build_owner_article.py`. It does not re-implement any
data, copy, factbook or guardrail logic: it calls `build()` -- so every editorial
gate, minted figure and cross-surface check still runs and still hard-fails the
build -- then adds the two things a mailed sheet needs that the on-screen article
does not:

  1. A QR code (and printed fallback URL) to THIS home's off-market page,
     https://fieldsestate.com.au/off-market/<url_slug>. That page is the campaign
     entry point (README §1): the reader scans, lands on our page for their own
     address, and engagement there is what classifies them as a lead.
  2. A faithful A4 print PDF, rendered through headless Chrome so the article's own
     `@media print` stylesheet, inline-SVG charts and data-URI photos come out
     exactly as designed (weasyprint mangles aspect-ratio / CSS-var / SVG here).

Why the QR does not break the no-CTA rule: it points at the reader's OWN data, not
an offer. The panel copy stays data-framed -- no "sell", "appraisal", "contact",
no urgency. It is an address of a page, printed the way we'd print a footnote's
URL. (Flagged for Will 2026-08-26: this is the one outward-pointing element on an
otherwise CTA-free piece.)

Guards it adds on top of build()'s:
  * The subject must have a `url_slug` -- no slug, no QR, no mail (hard fail).
  * The off-market page must actually resolve 200 live before we print a QR to it
    (a broken QR on unsolicited mail is worse than none -- README §8 spirit).
    `--skip-url-check` bypasses for dev only, never for a real run.

Usage:
    source /home/fields/venv/bin/activate
    set -a && source /home/fields/Fields_Orchestrator/.env && set +a
    cd /home/fields/Fields_Orchestrator/14_Articles/Owner_Subject_Article

    python3 build_owner_mailer.py --address "20 Heidelberg Circuit, Robina"
    python3 build_owner_mailer.py --address "..." --variant anchor --out-dir ./mail_batch

Exit codes mirror build(): 0 ok · 2 rejected by a guard · 3 failed checks · 4 the
off-market page did not resolve.
"""
from __future__ import annotations

import argparse
import os
import re
import sys
import urllib.request
import urllib.error

import base64
import io

import segno

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)

import build_owner_article as boa  # noqa: E402  (sets up shared/ path, SITE, etc.)

SITE = boa.SITE
OFFMARKET_URL = SITE + "/off-market/{slug}"

# Deep-link marker the off-market page (OffMarketV5) reads: on arrival it lands
# on the hero, then smooth-scrolls down to the "Your market update" section this
# teaser previews (id="v5-market-update"). Only the SCANNED/CLICKED target
# carries it; the printed fallback URL a reader types by hand stays clean (they
# just land at the top of the page, which is fine). See OffMarketV5.tsx.
OFFMARKET_QR_QUERY = "?from=mailer"


def _qr_target(url: str) -> str:
    """The URL to ENCODE IN A QR / put behind an <a> — the clean page URL plus the
    mailer deep-link marker. Kept separate from the human-typed fallback text."""
    return url + OFFMARKET_QR_QUERY

# Will's WSJ-style hedcut, the same portrait the website byline uses.
PORTRAIT_PATH = ("/home/fields/Feilds_Website/01_Website/src/assets/fields/"
                 "will-simpson-hedcut.webp")
BYLINE_NAME = "Will Simpson"
# The Fields wordmark used by the mailer_v2 direct-mail pieces -- reused here so the
# printed article shares that established visual identity (green/cream/terracotta).
LOGO_WHITE_PATH = ("/home/fields/Fields_Orchestrator/11_House_Mini_Site/_shared/"
                   "mailer_v2/assets/fields-logo-white.png")
TAGLINE = "Smarter with data"


# ------------------------------------------------------------------ shared assets
def qr_png_datauri(url: str, scale: int = 16, error: str = "q") -> str:
    """A scannable QR as a base64 PNG data-URI. border=4 is the mandatory quiet zone;
    a raster PNG (not inline SVG) scales predictably inside a fixed print box."""
    buf = io.BytesIO()
    segno.make(url, error=error).save(buf, kind="png", scale=scale, border=4,
                                      dark="#15171a")
    return "data:image/png;base64," + base64.b64encode(buf.getvalue()).decode("ascii")


def _img_datauri(path: str, box: int | None = None) -> str | None:
    """Embed a local image as a (optionally downscaled) PNG data-URI, or None."""
    try:
        from PIL import Image
    except Exception:                                            # noqa: BLE001
        return None
    if not os.path.exists(path):
        return None
    im = Image.open(path)
    if im.mode not in ("RGB", "RGBA"):
        im = im.convert("RGBA")
    if box:
        im.thumbnail((box, box), Image.LANCZOS)
    buf = io.BytesIO()
    im.save(buf, format="PNG", optimize=True)
    return "data:image/png;base64," + base64.b64encode(buf.getvalue()).decode("ascii")


def _portrait_datauri() -> str | None:
    return _img_datauri(PORTRAIT_PATH, box=200)


def _logo_datauri() -> str | None:
    return _img_datauri(LOGO_WHITE_PATH)


# ------------------------------------------------------------------ url_slug
def resolve_slug(client, address, suburb=None):
    """Return (url_slug, full_address, suburb_key) for the subject, or (None, ..).

    Reuses build_owner_article.resolve_subject so we resolve the SAME document the
    article was written about -- never a different one that happens to match.
    """
    doc, suburb_key = boa.resolve_subject(client, address, suburb)
    if not doc:
        return None, None, None
    return doc.get("url_slug"), (doc.get("address") or doc.get("complete_address")), suburb_key


def url_resolves(url: str, timeout: int = 20) -> tuple[bool, str]:
    """True iff the off-market page returns 200 and is not a soft-404 fallback.

    The React loader resolves by url_slug; a bad slug renders the app shell with a
    200 but a not-found title, so we check the title too, not just the status.
    """
    req = urllib.request.Request(
        url, headers={"User-Agent": "Mozilla/5.0 (FieldsMailer/1.0)"})
    try:
        with urllib.request.urlopen(req, timeout=timeout) as r:
            if r.status != 200:
                return False, f"HTTP {r.status}"
            body = r.read(60000).decode("utf-8", "replace").lower()
    except urllib.error.HTTPError as e:
        return False, f"HTTP {e.code}"
    except Exception as e:                                        # noqa: BLE001
        return False, f"{type(e).__name__}: {e}"
    if "off-market" not in body and "off market" not in body:
        return False, "page did not identify as an off-market report"
    if "not found" in body or "404" in body[:20000] and "page not found" in body:
        return False, "soft-404 (slug did not resolve to a property)"
    return True, "200"


# ------------------------------------------------------------------ page furniture
def brandbar_html() -> str:
    """Full-bleed green letterhead: Fields wordmark + tagline, matching mailer_v2."""
    logo = _logo_datauri()
    mark = (f'<img src="{logo}" alt="Fields">' if logo
            else '<span class="wordmark">FIELDS</span>')
    return (f'<div class="brandbar">{mark}'
            f'<span class="tag">{TAGLINE}<b>.</b></span></div>')


def byline_frontqr_html(url: str) -> str:
    """Sits UNDER the hero aerial (Will's request): Will's byline on the left, the
    'front-page' QR to this home's off-market page on the right."""
    portrait = _portrait_datauri()
    avatar = (f'<img class="byline-avatar" src="{portrait}" alt="{BYLINE_NAME}">'
              if portrait else "")
    target = _qr_target(url)
    return f"""
<div class="underhero">
  <div class="byline">{avatar}
    <span class="byline-txt"><span class="byline-name">{BYLINE_NAME}</span>
      <span class="byline-role">Fields Real Estate</span></span></div>
  <a class="front-qr" href="{target}" aria-label="Scan for the full data on this address">
    <span class="front-qr-cap">Scan for<br>your full data</span>
    <img src="{qr_png_datauri(target)}" alt="QR to this home's off-market page">
  </a>
</div>
"""


def qr_panel_html(url: str, address_short: str) -> str:
    """The closing call-out, styled as the mailer_v2 CTA band: full-bleed green,
    the QR in a warm-paper tile, cream copy. Data-framed, no CTA verb."""
    img = (f'<img class="qr-img" alt="Scan for {address_short}" '
           f'src="{qr_png_datauri(_qr_target(url))}">')
    return f"""
<section class="qr-panel" aria-label="Off-market page for this address">
  <div class="qr-code">{img}</div>
  <div class="qr-copy">
    <div class="qr-kicker">The full data set for this address</div>
    <p class="qr-lede">Every comparable sale behind these figures &mdash; each one
      adjusted to {address_short} &mdash; is on the page we prepared for this home.
      Scan the code, or type the address below.</p>
    <div class="qr-url">{url.replace('https://', '')}</div>
  </div>
</section>
"""


# Small per-link QR for the printed edition: a reader who cannot click needs a way
# to reach each linked page. error='m' keeps a ~55-char URL to a ~33-module code
# that stays scannable at the ~13mm printed size.
_LINK_A = re.compile(r'<a href="(https?://[^"]+)"([^>]*)>(.*?)</a>', re.DOTALL)


def add_link_qrs(html: str) -> tuple[str, int]:
    """Append a small scannable QR immediately after every external hyperlink so the
    printed piece is self-navigable. In-document #ref anchors are left untouched."""
    cache: dict[str, str] = {}
    n = 0

    def repl(m):
        nonlocal n
        href, attrs, text = m.group(1), m.group(2), m.group(3)
        if href not in cache:
            cache[href] = qr_png_datauri(href, scale=12, error="m")
        n += 1
        return (f'<span class="lnkqr-wrap"><a href="{href}"{attrs}>{text}</a>'
                f'<img class="lnkqr" src="{cache[href]}" '
                f'alt="QR to {href}"></span>')

    return _LINK_A.sub(repl, html), n


# The mailer's visual language, mirroring 11_House_Mini_Site/_shared/mailer_v2:
# warm cream paper, deep forest green blocks, terracotta serif accents. Applied as
# an OVERRIDE over the article's variable-driven CSS, so the inline-SVG charts,
# tables and callouts recolour to the palette automatically (they read --accent,
# --ink, --muted, --rule from these variables).
MAIL_CSS = """
:root,:root[data-theme=light],:root[data-theme=dark]{
 --ink:#2a2a24!important;--muted:#7a8a80!important;--rule:#d8cfc1!important;
 --bg:#efe8de!important;--accent:#22382c!important;--tint:#fdf3ec!important;
 --band:#f4ece2!important;
 --terra:#b76749;--terra-dark:#8d4d33;--green:#22382c;--green-deep:#1b2d24;
 --sand:#c9b9a0;--paper:#fdf3ec;--sage:#7a8a80}
@media (prefers-color-scheme:dark){:root{
 --ink:#2a2a24!important;--muted:#7a8a80!important;--rule:#d8cfc1!important;
 --bg:#efe8de!important;--accent:#22382c!important;--tint:#fdf3ec!important;
 --band:#f4ece2!important}}
*{-webkit-print-color-adjust:exact;print-color-adjust:exact}

body{background:var(--paper)}
.wrap{max-width:none;margin:0;padding:0}

/* --- brand letterhead (inset block, rounded) --- */
.brandbar{background:var(--green);display:flex;align-items:center;
 justify-content:space-between;padding:5.5mm 7mm;margin:0 0 8mm!important;
 border-radius:2.5mm}
.brandbar img{height:8mm;width:auto;display:block}
.brandbar .wordmark{font:700 20pt/1 Georgia,serif;color:var(--paper);letter-spacing:.02em}
.brandbar .tag{font:400 13pt/1 Georgia,serif;color:var(--sand);letter-spacing:-.01em}
.brandbar .tag b{color:#c98a52}

/* --- eyebrow / kicker --- */
.flag{color:var(--terra-dark)!important;font-weight:700;letter-spacing:.18em;
 margin-bottom:1rem!important}

/* --- display type: serif headlines, editorial serif body kept --- */
h1{font-family:Georgia,'Liberation Serif',serif!important;font-weight:400!important;
 color:var(--green-deep)!important;font-size:2.35rem!important;line-height:1.1!important;
 letter-spacing:-.01em}
h1 strong,h1 b{color:var(--terra)!important;font-weight:400!important}
h2{font-family:Georgia,'Liberation Serif',serif!important;font-weight:400!important;
 color:var(--green-deep)!important;font-size:1.55rem!important;
 border-top:1px solid var(--rule)!important;padding-top:1.6rem!important;
 margin-top:2.8rem!important}
h2 strong{color:var(--terra)!important;font-weight:400}
h3{color:var(--green-deep)!important}
a{color:var(--terra-dark)!important}
strong{color:var(--green-deep)}
body>.wrap>p:first-of-type{color:#4a453d!important}
/* consequence-style lead: the first body paragraph gets a terracotta rule */
.hero + .underhero + p{border-left:2.5pt solid var(--terra);padding-left:5mm}

/* --- hero aerial --- */
.hero{border:1px solid var(--rule)!important;border-radius:3mm!important;
 box-shadow:0 3mm 8mm rgba(34,56,44,.14);margin:0 0 0!important}
.hero img{max-height:290px;object-fit:cover;object-position:center}
.hero figcaption{background:var(--paper);color:var(--sage)!important}

/* --- byline + front QR, UNDER the hero --- */
.underhero{display:flex;justify-content:space-between;align-items:center;gap:1rem;
 padding:4mm 0 0;margin:3.5mm 0 2rem!important;border-bottom:1px solid var(--rule)}
.byline{display:flex;align-items:center;gap:.7rem}
.byline-avatar{width:48px;height:48px;border-radius:50%;object-fit:cover;
 border:2px solid var(--terra)}
.byline-txt{display:flex;flex-direction:column;line-height:1.2}
.byline-name{font:700 15px/1.2 'Liberation Sans',-apple-system,Segoe UI,sans-serif;
 color:var(--green-deep)}
.byline-role{font:400 11px/1.3 'Liberation Sans',-apple-system,Segoe UI,sans-serif;
 letter-spacing:.08em;text-transform:uppercase;color:var(--sage);margin-top:1px}
.front-qr{display:flex;align-items:center;gap:.55rem;text-decoration:none;flex:none}
.front-qr img{width:60px;height:60px;background:var(--paper);border:1px solid var(--rule);
 border-radius:5px;padding:3px;box-sizing:border-box}
.front-qr-cap{font:700 10px/1.25 'Liberation Sans',-apple-system,Segoe UI,sans-serif;
 letter-spacing:.06em;text-transform:uppercase;color:var(--terra-dark);text-align:right}

/* --- comparison + tables: warm accents --- */
.cmp-tag{color:var(--terra-dark)!important}
.cmp-land{color:var(--terra)!important}
.cmp-price{color:var(--green-deep)!important}
.cmp-card{background:var(--paper)!important;box-shadow:0 2mm 5mm rgba(34,56,44,.10)}
td:nth-child(5){color:var(--green-deep)!important}
th{border-bottom-color:var(--green)!important}

/* --- per-link QR chips (print edition) --- */
.lnkqr-wrap{white-space:normal}
.lnkqr{width:50px;height:50px;vertical-align:middle;margin:0 3px 0 6px;
 background:var(--paper);border:1px solid var(--rule);border-radius:4px;padding:2px;
 box-sizing:border-box;image-rendering:crisp-edges}

/* --- closing CTA band (inset green block, mailer_v2 language) --- */
.qr-panel{display:grid;grid-template-columns:150px 1fr;gap:1.5rem;align-items:center;
 margin:3rem 0 0!important;padding:8mm 8mm;background:var(--green)!important;
 border:none!important;border-radius:2.5mm!important;color:var(--paper);
 break-inside:avoid;page-break-inside:avoid}
.qr-code{width:150px;height:150px;background:var(--paper);border:none;
 border-radius:2.5mm;padding:5px;box-sizing:border-box}
.qr-code .qr-img{width:100%;height:100%;display:block;image-rendering:crisp-edges}
.qr-kicker{font:700 10pt/1 'Liberation Sans',-apple-system,Segoe UI,sans-serif;
 letter-spacing:.14em;text-transform:uppercase;color:var(--sand)!important;
 margin-bottom:.6rem}
.qr-lede{font:400 13.5pt/1.5 Georgia,'Liberation Serif',serif;color:var(--paper)!important;
 margin:0 0 .8rem}
.qr-url{font:700 12pt/1.3 'Liberation Sans',monospace;color:var(--sand)!important;
 word-break:break-all;letter-spacing:.2pt}

/* --- foot --- */
.foot{color:var(--sage)!important;border-top-color:var(--rule)!important}

@media print{.hero{box-shadow:none}.cmp-card{box-shadow:none}}
"""


def build_mail_html(html: str, url: str, address_short: str) -> tuple[str, int]:
    """Transform the article HTML into the print/mail edition (mailer_v2 visual
    language): brandbar, byline + front QR UNDER the hero, per-link QR chips, and the
    closing green CTA panel. Returns (html, n_link_qrs)."""
    # 1. CSS -- append to the last </style> so our overrides win the cascade.
    html = html.replace("</style>", MAIL_CSS + "</style>", 1)

    # 2. Brandbar at the very top of the content column.
    html = html.replace('<div class="flag">', brandbar_html() + '<div class="flag">', 1)
    # Drop the redundant "Fields &middot; " now that the wordmark is in the brandbar.
    html = html.replace('<div class="flag">Fields &middot; prepared for this address</div>',
                        '<div class="flag">Prepared for this address</div>', 1)

    # 3. Byline + front QR, immediately AFTER the hero aerial (Will's request).
    top = byline_frontqr_html(url)
    hero = re.search(r'<figure class="hero">.*?</figure>', html, re.DOTALL)
    if hero:
        html = html[:hero.end()] + top + html[hero.end():]
    else:                       # --no-hero: place it right after the <h1>
        html = re.sub(r"(</h1>)", r"\1" + top, html, count=1)

    # 4. Per-link QR chips (before the panel, whose URL text is not an <a>).
    html, n_links = add_link_qrs(html)

    # 5. Closing CTA panel, just inside the closing .wrap div.
    marker = "</div></body></html>"
    if marker not in html:
        raise RuntimeError("could not find wrap-close marker to inject QR panel")
    html = html.replace(marker, qr_panel_html(url, address_short) + marker, 1)
    return html, n_links


# ------------------------------------------------------------------ PDF render
def html_to_pdf(html_path: str, pdf_path: str, margin: str = "13mm"):
    """Render the mailer HTML to A4 print PDF via headless Chrome (faithful to the
    article's own print stylesheet). file:// so local data-URI/relative assets load.
    margin='0' for the fixed-box teaser (full-bleed); '13mm' for the flowed article."""
    from playwright.sync_api import sync_playwright

    exe = next((p for p in ("/usr/bin/google-chrome",
                            "/usr/bin/google-chrome-stable",
                            "/usr/bin/chromium-browser") if os.path.exists(p)), None)
    file_url = "file://" + os.path.abspath(html_path)
    with sync_playwright() as p:
        launch = {"executable_path": exe} if exe else {}
        browser = p.chromium.launch(**launch)
        page = browser.new_page()
        # Force the light print palette regardless of the renderer's theme.
        page.emulate_media(media="print", color_scheme="light")
        page.goto(file_url, wait_until="networkidle")
        # Force every image to load and finish decoding before printing. Without
        # this, `loading="lazy"` images below the fold (the comparison-home cards)
        # never enter the viewport in a headless print snapshot and render blank.
        page.evaluate("""async () => {
            const imgs = Array.from(document.images);
            imgs.forEach(i => { i.loading = 'eager'; });
            await Promise.all(imgs.map(i =>
                (i.complete && i.naturalWidth) ? Promise.resolve()
                    : i.decode().catch(() => {})));
        }""")
        # Uniform page margins keep body copy off the sheet edge on every one of the
        # ~9 flowed pages; the brandbar and CTA are inset blocks (not full-bleed),
        # which a long multi-page document handles far more predictably than bleed.
        # The teaser passes margin='0' — it is a fixed 210x297 box that bleeds.
        page.pdf(path=pdf_path, format="A4", print_background=True,
                 margin={"top": margin, "bottom": margin, "left": margin, "right": margin})
        browser.close()


# ================================================================== TEASER
# A separate deliverable from the full article: a fixed two-page A4 sheet that
# invites the recipient to scan the QR and read the complete analysis on their
# off-market page. Designed to be posted FLAT in a C4 envelope (Will, 2026-08-26):
# feels like a private property briefing, not a flyer. Low density on purpose.
#
# Its three headline figures are read from the SAME helpers the full article uses
# (subject_trajectory, precomputed_indexed_prices, precomputed_market_charts), so a
# teaser and the article/website can never show one owner two different numbers.

def _fmt_pct(v: float) -> str:
    return f"{v:+.1f}%"


_MONTHS = {"Jan": "January", "Feb": "February", "Mar": "March", "Apr": "April",
           "May": "May", "Jun": "June", "Jul": "July", "Aug": "August",
           "Sep": "September", "Oct": "October", "Nov": "November", "Dec": "December"}


def _full_month(date_label: str | None) -> str:
    """'Feb 2026' -> 'February'. Falls back to the label as given."""
    if not date_label:
        return ""
    return _MONTHS.get(date_label.split()[0], date_label.split()[0])


def _move_word(pct: float) -> str:
    """A factual, non-predictive verb for a six-month move, so the caption speaks to
    the movement without asserting a trend."""
    if pct <= -0.75:
        return "eased back"
    if pct < 0.75:
        return "held steady"
    return "edged higher"


def teaser_facts(client, address, suburb=None, skip_market_check=False,
                 out_dir=".") -> dict:
    """Resolve the subject and compute the teaser's three figures + aerial.
    Returns {ok:True, ...} or {ok:False, stage, errors}. Guards for the specific
    'holding, but signals worth watching' story the copy tells: a home that is
    FALLING, or a suburb that is EASING, would make the templated lines untrue, so
    those are rejected rather than silently inverted (the article is sign-aware;
    this teaser variant is written for one sign)."""
    doc, suburb_key = boa.resolve_subject(client, address, suburb)
    if not doc:
        return {"ok": False, "stage": "resolve", "errors": [f"no subject for {address!r}"]}
    full_addr = doc.get("address") or doc.get("complete_address")
    slug = doc.get("url_slug")
    if not slug:
        return {"ok": False, "stage": "slug", "address": full_addr,
                "errors": [f"{full_addr} has no url_slug"]}

    reasons = boa.guard_subject(client, doc, suburb_key, skip_market_check)
    if reasons:
        return {"ok": False, "stage": "guard", "address": full_addr, "errors": reasons}

    median = boa.suburb_median_series(client, suburb_key)
    dom = boa.suburb_dom(client, suburb_key)
    try:
        traj = boa.traj_mod.TrajectoryEngine(client, suburb_key).compute(doc)
    except Exception as e:                                       # noqa: BLE001
        traj = None
    missing = [n for n, v in (("trajectory", traj), ("suburb median", median),
                              ("days-on-market", dom)) if not v]
    if missing:
        return {"ok": False, "stage": "data", "address": full_addr,
                "errors": [f"teaser needs {', '.join(missing)} and it is unavailable"]}

    # Figures 1 & 2 are the SIX-MONTH move -- Feb reading to today (Will, 2026-08-26),
    # read from the trajectory anchors (6-months-ago vs now): the home's own estimate
    # and the suburb's rolling-12m median at each of those two dates. Figure 3 is DOM,
    # unchanged (its own year-on-year comparison).
    pts = {p["months_ago"]: p for p in (traj.get("points") or [])}
    p6, p0 = pts.get(6), pts.get(0)
    latest = dom.get("latest")
    yoy_days = dom.get("yoy_days")
    if not p6 or not p0 or latest is None or yoy_days is None:
        return {"ok": False, "stage": "data", "address": full_addr,
                "errors": ["a required teaser figure is missing from its source"]}

    def _pct(a, b):
        return ((b - a) / a * 100.0) if a else None
    home_6m = _pct(p6.get("mid"), p0.get("mid"))
    suburb_6m = _pct(p6.get("median"), p0.get("median"))
    if home_6m is None or suburb_6m is None:
        return {"ok": False, "stage": "data", "address": full_addr,
                "errors": ["could not compute the six-month move from the trajectory"]}

    month_from = _full_month(p6.get("date_label"))   # e.g. "February"
    month_to = _full_month(p0.get("date_label"))     # e.g. "August"

    # The copy's premise: this home is HOLDING (roughly flat to modestly up over the
    # six months), the suburb is holding, and selling has slowed. Reject anything the
    # fixed wording would misdescribe -- a clearly falling or surging home ("still
    # holding its value" would be untrue either way), a falling suburb, or DOM that is
    # shortening ("homes are taking longer to sell" untrue). Honest rejection, not a
    # defect: an easing/surging variant would need its own copy.
    HOME_BAND, SUBURB_BAND = (-2.0, 8.0), (-2.0, 15.0)
    bad = []
    if not (HOME_BAND[0] <= home_6m <= HOME_BAND[1]):
        bad.append(f"home 6-month move {home_6m:+.1f}% is outside the holding band "
                   f"{HOME_BAND[0]:+.0f}..{HOME_BAND[1]:+.0f}% this copy describes")
    if not (SUBURB_BAND[0] <= suburb_6m <= SUBURB_BAND[1]):
        bad.append(f"suburb 6-month move {suburb_6m:+.1f}% is outside "
                   f"{SUBURB_BAND[0]:+.0f}..{SUBURB_BAND[1]:+.0f}%")
    if yoy_days <= 0:
        bad.append(f"days-on-market changed {yoy_days:+g}d (not lengthening), so "
                   f"'homes are taking longer to sell' would be untrue")
    if bad:
        return {"ok": False, "stage": "narrative", "address": full_addr,
                "errors": bad + ["an easing/surging teaser variant would be needed here"]}

    hero = boa.build_hero(client, doc, suburb_key, slug, out_dir)
    aerial_uri = _img_datauri(os.path.join(out_dir, hero["file"])) if hero else None

    return {
        "ok": True, "address": full_addr, "url_slug": slug, "suburb_key": suburb_key,
        "address_short": full_addr.split(",")[0].strip(),
        "suburb_display": suburb_key.replace("_", " ").title(),
        "home_6m": home_6m, "suburb_6m": suburb_6m,
        "home_move_word": _move_word(home_6m),
        "month_from": month_from, "month_to": month_to,
        "dom_now": int(round(latest)), "dom_prev": int(round(latest - yoy_days)),
        "aerial_uri": aerial_uri, "aerial_cap": (hero or {}).get("caption", ""),
    }


TEASER_CSS = """
@page{size:A4;margin:0}
*{box-sizing:border-box;margin:0;padding:0}
:root{--green:#22382c;--green-deep:#1b2d24;--terra:#b76749;--terra-dark:#8d4d33;
 --sand:#c9b9a0;--paper:#fdf3ec;--cream:#efe8de;--sage:#7a8a80;--ink:#2a2a24;
 --line:#d8cfc1}
html,body{font-family:'Liberation Sans',-apple-system,Segoe UI,Roboto,sans-serif;
 color:var(--ink);-webkit-print-color-adjust:exact;print-color-adjust:exact}
.serif{font-family:Georgia,'Liberation Serif',serif}
.page{width:210mm;height:297mm;position:relative;overflow:hidden;
 background:var(--paper);page-break-after:always}
.page:last-child{page-break-after:auto}
.pad{padding:0 20mm}
.brandbar{background:var(--green);color:var(--paper);display:flex;align-items:center;
 justify-content:space-between;padding:6mm 20mm}
.brandbar img{height:8mm;width:auto;display:block}
.brandbar .tag{font:400 13pt/1 Georgia,serif;color:var(--sand);letter-spacing:-.01em}
.brandbar .tag b{color:#c98a52}
.kicker{color:var(--terra-dark);font-size:10.5pt;letter-spacing:2.6pt;font-weight:700;
 text-transform:uppercase}

/* ---- FRONT ---- */
.front .top{padding:10mm 20mm 7mm}
.front h1{font-size:31pt;line-height:1.08;color:var(--green-deep);font-weight:400;
 letter-spacing:-.3pt;margin-top:4mm}
.front h1 b{color:var(--terra);font-weight:400}
.aerialband{width:210mm;height:150mm;position:relative;background:var(--cream)}
.aerialband img{width:100%;height:100%;object-fit:cover;display:block}
.aerialcap{position:absolute;left:0;right:0;bottom:0;background:rgba(27,45,36,.72);
 color:var(--paper);font-size:8.5pt;letter-spacing:.2pt;padding:2.6mm 20mm}
.front .lede{font-size:15pt;line-height:1.5;color:#3f3a32;margin-top:9mm;max-width:150mm}
.front .lede b{color:var(--green-deep)}
.front .foot{position:absolute;left:0;right:0;bottom:0;padding:0 20mm 16mm}
.front .inside{font-size:11.5pt;line-height:1.55;color:#4a453d;
 border-left:2.5pt solid var(--terra);padding-left:6mm;max-width:150mm}
.front .turn{margin-top:7mm;font:700 13pt/1 Georgia,serif;color:var(--terra-dark)}

/* ---- BACK ---- */
.back .top{padding:11mm 20mm 0}
.back h2{font-size:22pt;line-height:1.14;color:var(--green-deep);font-weight:400;
 letter-spacing:-.2pt}
.back h2 b{color:var(--terra);font-weight:400}
.figs{display:flex;gap:8mm;margin:9mm 0 6mm;padding:0 20mm}
.figs .fig{flex:1;text-align:left;border-top:2.5pt solid var(--green)}
.figs .n{font-family:Georgia,'Liberation Serif',serif;font-size:34pt;line-height:1.05;
 color:var(--terra);margin-top:3mm}
.figs .n span{font-size:15pt;color:var(--sage)}
.figs .l{font-size:9.5pt;line-height:1.4;color:#4a453d;margin-top:2.5mm}
.back .body{font-size:11.5pt;line-height:1.58;color:#3f3a32;margin:0 0 4mm;max-width:158mm}
.back .body b{color:var(--green-deep)}
/* --- question teasers: what the article answers --- */
.questions{margin-top:5mm}
.qkicker{color:var(--terra-dark);font-size:9.5pt;letter-spacing:2.2pt;font-weight:700;
 text-transform:uppercase;margin-bottom:5mm}
.qitem{padding:3.2mm 0;border-top:1px solid var(--line)}
.qitem:first-of-type{border-top:none;padding-top:0}
.qitem h3{font:400 14.5pt/1.2 Georgia,'Liberation Serif',serif;color:var(--green-deep);
 margin-bottom:1.6mm}
.qitem p{font-size:10.5pt;line-height:1.45;color:#4a453d;max-width:150mm}
.quotebox{display:flex;gap:7mm;align-items:center;margin:6mm 0;padding:6mm 7mm;
 background:var(--cream);border-radius:2.5mm}
.quotebox .portrait{width:30mm;height:30mm;border-radius:50%;object-fit:cover;
 border:2.5pt solid var(--terra);flex:0 0 auto}
.quotebox .quote{font:400 12.5pt/1.5 Georgia,'Liberation Serif',serif;color:var(--green-deep);
 font-style:italic}
.quotebox .sig{margin-top:3mm;font-family:'Liberation Sans',sans-serif;font-style:normal;
 font-size:10pt;color:var(--ink);line-height:1.35}
.quotebox .sig b{color:var(--green-deep)}
.respond{margin:0 20mm 15mm;background:var(--green);color:var(--paper);border-radius:2.5mm;
 display:flex;gap:9mm;align-items:center;padding:8mm 9mm}
.respond h3{font:400 16.5pt/1.2 Georgia,'Liberation Serif',serif;color:var(--paper);
 margin-bottom:3mm}
.respond p{font-size:10.5pt;line-height:1.5;color:#dcd3c4;margin-bottom:3mm}
.respond .scan{color:var(--sand);font-weight:700}
.respond-l{flex:1}
.respond .readlink{margin-top:4mm;font:700 11.5pt/1.4 'Liberation Sans',sans-serif;
 color:var(--paper)}
.respond .readlink span{display:block;color:var(--sand);font-weight:700;
 font-size:10.5pt;margin-top:1mm;letter-spacing:.2pt}
.respond-qr{flex:0 0 auto;background:var(--paper);border-radius:2.5mm;padding:4mm}
.respond-qr img{display:block;width:40mm;height:40mm}
"""


def teaser_html(f: dict, url: str) -> str:
    logo = _logo_datauri()
    mark = (f'<img src="{logo}" alt="Fields">' if logo
            else '<span class="serif" style="color:#fdf3ec;font-size:20pt">FIELDS</span>')
    brand = (f'<div class="brandbar">{mark}'
             f'<span class="tag">{TAGLINE}<b>.</b></span></div>')
    addr = f["address_short"]
    suburb = f["suburb_display"]
    portrait = _portrait_datauri()
    portrait_img = (f'<img class="portrait" src="{portrait}" alt="{BYLINE_NAME}">'
                    if portrait else "")
    aerial = (f'<img src="{f["aerial_uri"]}" alt="Aerial of {addr} with its boundary">'
              if f.get("aerial_uri") else "")
    # The SCANNED QR carries ?from=mailer so the off-market page smooth-scrolls to
    # the "Your market update" section this teaser previews; the printed link text
    # a reader types by hand stays clean (they land at the top, which is fine).
    qr = qr_png_datauri(_qr_target(url), scale=16, error="q")
    urltext = url.replace("https://", "")

    front = f"""
<div class="page front">
  {brand}
  <div class="top">
    <div class="kicker">Prepared for this address</div>
    <h1 class="serif">Prices are falling.<br><b>Could {addr} be next?</b></h1>
  </div>
  <div class="aerialband">{aerial}<div class="aerialcap">{f['aerial_cap']}</div></div>
  <div class="pad">
    <p class="lede">Sydney and Melbourne have turned. Brisbane has slipped.<br>
      But {suburb} &mdash; and this home &mdash; have not followed them.
      <b>We investigated why.</b></p>
  </div>
  <div class="foot">
    <p class="inside">Inside the analysis: how this home&rsquo;s estimated value has moved,
      why {suburb} has resisted the national decline, and the signals that could warn of
      a change.</p>
    <div class="turn">Turn over for what we found &rarr;</div>
  </div>
</div>
"""

    back = f"""
<div class="page back">
  {brand}
  <div class="top">
    <h2 class="serif">This home is still holding its value.<br>
      <b>But the market underneath it is beginning to change.</b></h2>
  </div>
  <div class="figs">
    <div class="fig"><div class="n serif">{_fmt_pct(f['home_6m'])}</div>
      <div class="l">This home&rsquo;s estimated value has {f['home_move_word']}
        since {f['month_from']}</div></div>
    <div class="fig"><div class="n serif">{_fmt_pct(f['suburb_6m'])}</div>
      <div class="l">The {suburb} median over the same six months,
        {f['month_from']} to {f['month_to']}</div></div>
    <div class="fig"><div class="n serif">{f['dom_now']} <span>days</span></div>
      <div class="l">Typical time to sell, up from {f['dom_prev']} days</div></div>
  </div>
  <div class="quotebox" style="margin-left:20mm;margin-right:20mm">
    {portrait_img}
    <div class="quote">&ldquo;The Gold Coast is underpinned by a strong economy that has served
      us well up until now. However, some key leading indicators of price change are starting
      to show early signs of moving. Those are the signals I&rsquo;ll be watching next.&rdquo;
      <div class="sig"><b>{BYLINE_NAME}</b><br>Fields Real Estate</div></div>
  </div>
  <div class="pad questions">
    <div class="qkicker">The questions the full analysis answers</div>
    <div class="qitem"><h3 class="serif">Why did the wider market turn down?</h3>
      <p>We set out the forces behind the national fall &mdash; inflation, interest rates
        and buyer confidence &mdash; with the figures behind each.</p></div>
    <div class="qitem"><h3 class="serif">Why is the Gold Coast holding while others fall?</h3>
      <p>We examine the fundamentals underneath it &mdash; interstate migration, local jobs
        and what the same money buys &mdash; for the structural differences.</p></div>
    <div class="qitem"><h3 class="serif">Will the Gold Coast turn down too?</h3>
      <p>We look closely at the indicators shown to move before prices do. Four key metrics
        are beginning to show early signals worth watching.</p></div>
  </div>
  <div class="respond">
    <div class="respond-l">
      <p class="scan">Scan to read the complete analysis prepared for {addr}.</p>
      <div class="readlink">Read your property analysis &rarr;<span>{urltext}</span></div>
    </div>
    <div class="respond-qr"><img src="{qr}" alt="Scan for the full analysis of {addr}"></div>
  </div>
</div>
"""
    return (f'<!doctype html><html lang="en"><head><meta charset="utf-8">\n'
            f'<meta name="robots" content="noindex">\n<style>{TEASER_CSS}</style>'
            f'</head><body>{front}{back}</body></html>\n')


def verify_teaser_pdf(pdf_path: str, f: dict) -> list[str]:
    """mailer_v2 lesson: `.page` is overflow:hidden, so overlong copy is SILENTLY
    cropped and the PDF still looks plausible. Assert 2 pages and that every
    load-bearing string is actually present in the extracted text."""
    import subprocess
    errs = []
    try:
        info = subprocess.run(["pdfinfo", pdf_path], capture_output=True, text=True)
        pages = next((int(l.split(":")[1]) for l in info.stdout.splitlines()
                      if l.startswith("Pages:")), None)
        if pages != 2:
            errs.append(f"expected 2 pages, got {pages}")
        txt = subprocess.run(["pdftotext", "-nopgbrk", pdf_path, "-"],
                             capture_output=True, text=True).stdout
    except Exception as e:                                       # noqa: BLE001
        return [f"could not read back the PDF for verification: {e}"]
    folded = re.sub(r"\s+", " ", txt).lower()
    must = [f["address_short"].lower(), _fmt_pct(f["home_6m"]).lower(),
            _fmt_pct(f["suburb_6m"]).lower(), f"{f['dom_now']} days",
            f"up from {f['dom_prev']} days", "turn over for what we found",
            "why did the wider market turn down", "will the gold coast turn down too",
            "read your property analysis", "will simpson"]
    for m in must:
        if re.sub(r"\s+", " ", m) not in folded:
            errs.append(f"load-bearing line missing from artwork: {m!r}")
    return errs


def build_teaser(address, suburb=None, out_dir=None, skip_market_check=False,
                 skip_url_check=False, verbose=True) -> dict:
    client = boa.get_db()
    out_dir = out_dir or os.path.join(HERE, "output_teaser")
    os.makedirs(out_dir, exist_ok=True)

    f = teaser_facts(client, address, suburb, skip_market_check, out_dir)
    if not f.get("ok"):
        return f

    url = OFFMARKET_URL.format(slug=f["url_slug"])
    if not skip_url_check:
        ok, why = url_resolves(url)
        if not ok:
            return {"ok": False, "stage": "url", "address": f["address"], "url": url,
                    "errors": [f"off-market page did not resolve ({why}): {url}"]}

    slug = boa.slugify(f["address"])
    html = teaser_html(f, url)
    html_path = os.path.join(out_dir, f"{slug}.teaser.html")
    with open(html_path, "w", encoding="utf-8") as fh:
        fh.write(html)
    pdf_path = os.path.join(out_dir, f"{slug}.teaser.pdf")
    html_to_pdf(html_path, pdf_path, margin="0")

    layout = verify_teaser_pdf(pdf_path, f)
    if layout:
        bad = pdf_path.replace(".teaser.pdf", ".teaser.REJECTED.pdf")
        os.replace(pdf_path, bad)
        return {"ok": False, "stage": "artwork", "address": f["address"],
                "errors": layout, "rejected_pdf": bad}

    return {"ok": True, "address": f["address"], "offmarket_url": url,
            "url_slug": f["url_slug"], "teaser_html": html_path, "pdf": pdf_path,
            "figures": {"home_6m": f"{_fmt_pct(f['home_6m'])} ({f['home_move_word']} "
                        f"since {f['month_from']})",
                        "suburb_6m": _fmt_pct(f["suburb_6m"]),
                        "dom": f"{f['dom_now']} days (was {f['dom_prev']})"}}


# ------------------------------------------------------------------ orchestration
def build_mailer(address, suburb=None, out_dir=None, variant="report",
                 skip_market_check=False, skip_url_check=False, no_hero=False,
                 skip_trajectory=False, verbose=True):
    client = boa.get_db()

    slug, full_addr, suburb_key = resolve_slug(client, address, suburb)
    if not full_addr:
        return {"ok": False, "stage": "resolve",
                "errors": [f"no subject found for {address!r}"]}
    if not slug:
        return {"ok": False, "stage": "slug", "address": full_addr,
                "errors": [f"{full_addr} has no url_slug -- cannot build a QR to its "
                           "off-market page; refusing to mail"]}

    offmarket = OFFMARKET_URL.format(slug=slug)

    # Verify the QR target actually resolves before we print it onto posted mail.
    if not skip_url_check:
        ok, why = url_resolves(offmarket)
        if not ok:
            return {"ok": False, "stage": "url", "address": full_addr, "url": offmarket,
                    "errors": [f"off-market page did not resolve ({why}): {offmarket}"]}

    # The article itself -- all gates run here and can still hard-fail.
    out_dir = out_dir or os.path.join(HERE, "output_mail")
    r = boa.build(address, suburb, out_dir, want_html=True,
                  skip_market_check=skip_market_check, no_hero=no_hero,
                  variant=variant, skip_trajectory=skip_trajectory, verbose=verbose)
    if not r.get("ok"):
        return r

    article_slug = r["slug"]
    address_short = full_addr.split(",")[0].strip()
    with open(r["html"], encoding="utf-8") as fh:
        html = fh.read()

    mail_html, n_link_qrs = build_mail_html(html, offmarket, address_short)
    mail_html_path = os.path.join(out_dir, f"{article_slug}.mailer.html")
    with open(mail_html_path, "w", encoding="utf-8") as fh:
        fh.write(mail_html)

    pdf_path = os.path.join(out_dir, f"{article_slug}.pdf")
    html_to_pdf(mail_html_path, pdf_path)

    r.update({"mailer_html": mail_html_path, "pdf": pdf_path,
              "offmarket_url": offmarket, "url_slug": slug, "n_link_qrs": n_link_qrs})
    return r


def main():
    ap = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--address", required=True)
    ap.add_argument("--suburb", choices=boa.SUBURBS)
    ap.add_argument("--out-dir")
    ap.add_argument("--variant", default="report",
                    choices=["report"] + sorted(boa.variants_mod.VARIANTS),
                    help="composition angle; see variants.py")
    ap.add_argument("--no-hero", action="store_true")
    ap.add_argument("--no-trajectory", action="store_true")
    ap.add_argument("--skip-market-check", action="store_true",
                    help="skip PropRadar mailability guard (dev only -- never for print)")
    ap.add_argument("--skip-url-check", action="store_true",
                    help="skip the live off-market-page resolve check (dev only)")
    ap.add_argument("--teaser", action="store_true",
                    help="build the 2-page A4 teaser cover (invites the scan) instead "
                         "of the full article PDF")
    a = ap.parse_args()

    if a.teaser:
        r = build_teaser(a.address, a.suburb, a.out_dir,
                         skip_market_check=a.skip_market_check,
                         skip_url_check=a.skip_url_check)
        if not r.get("ok"):
            print(f"REJECTED at {r['stage']}: {r.get('address') or a.address}", file=sys.stderr)
            for e in r.get("errors", []):
                print(f"  - {e}", file=sys.stderr)
            sys.exit({"resolve": 2, "slug": 2, "guard": 2, "data": 2, "narrative": 2,
                      "url": 4, "artwork": 3}.get(r["stage"], 2))
        print(f"OK  {r['address']}  (teaser)")
        print(f"    off-market  {r['offmarket_url']}")
        print(f"    pdf         {r['pdf']}")
        print(f"    figures     home {r['figures']['home_6m']} · "
              f"suburb {r['figures']['suburb_6m']} · DOM {r['figures']['dom']}")
        return

    r = build_mailer(a.address, a.suburb, a.out_dir, a.variant,
                     skip_market_check=a.skip_market_check,
                     skip_url_check=a.skip_url_check, no_hero=a.no_hero,
                     skip_trajectory=a.no_trajectory)

    if not r.get("ok"):
        print(f"REJECTED at {r['stage']}: {r.get('address') or a.address}", file=sys.stderr)
        for e in r.get("errors", []):
            print(f"  - {e}", file=sys.stderr)
        sys.exit({"resolve": 2, "slug": 2, "guard": 2, "comps": 2, "consistency": 3,
                  "checks": 3, "url": 4}.get(r["stage"], 2))

    print(f"OK  {r['address']}")
    print(f"    off-market  {r['offmarket_url']}")
    print(f"    pdf         {r['pdf']}")
    print(f"    mailer html {r['mailer_html']}")
    for w in r.get("warnings", []):
        print(f"    ? WARN {w['label']} line {w['line']}: {w['match']!r} -- {w['why']}")


if __name__ == "__main__":
    main()
