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


# ------------------------------------------------------------------ QR panel
def qr_panel_html(url: str, address_short: str) -> str:
    """A print-safe QR call-out. Data-framed, no CTA verbs. Its own page column
    so it never splits across a page break in the PDF."""
    # A high-res PNG data-URI, not inline SVG: an <img> scales predictably inside
    # the print box where an SVG's intrinsic size fought the flex container and
    # clipped. error='q' (25% recovery) survives a fold or a coffee ring on posted
    # mail; border=4 is the mandatory 4-module quiet zone; scale=16 -> ~660px, which
    # downscales to the ~40mm printed box razor-sharp.
    buf = io.BytesIO()
    segno.make(url, error="q").save(buf, kind="png", scale=16, border=4, dark="#15171a")
    data = base64.b64encode(buf.getvalue()).decode("ascii")
    img = f'<img class="qr-img" alt="Scan for {address_short}" src="data:image/png;base64,{data}">'
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


QR_CSS = """
.qr-panel{display:grid;grid-template-columns:168px 1fr;gap:1.4rem;align-items:center;
 margin:2.4rem 0 0;padding:1.4rem 1.5rem;border:1px solid var(--rule);border-radius:14px;
 background:var(--tint);break-inside:avoid;page-break-inside:avoid}
.qr-code{width:168px;height:168px;background:#fff;border:1px solid var(--rule);
 border-radius:8px;padding:6px;box-sizing:border-box}
.qr-code .qr-img{width:100%;height:100%;display:block;image-rendering:crisp-edges}
.qr-kicker{font:700 11px/1 -apple-system,Segoe UI,Roboto,sans-serif;letter-spacing:.12em;
 text-transform:uppercase;color:var(--accent);margin-bottom:.55rem}
.qr-lede{font:400 15px/1.5 Georgia,'Times New Roman',serif;color:var(--ink);margin:0 0 .7rem}
.qr-url{font:600 14px/1.3 ui-monospace,'SF Mono',Menlo,Consolas,monospace;color:var(--muted);
 word-break:break-all}
@media (max-width:30rem){.qr-panel{grid-template-columns:1fr;justify-items:center;text-align:center}}
@media print{.qr-panel{background:#f6f8f7 !important;-webkit-print-color-adjust:exact;
 print-color-adjust:exact}}
"""


def inject_qr(html: str, url: str, address_short: str) -> str:
    """Insert the QR panel just inside the closing .wrap div, and its CSS into <head>."""
    panel = qr_panel_html(url, address_short)
    # CSS: append to the last </style> so it wins the cascade for our own classes.
    html = html.replace("</style>", QR_CSS + "</style>", 1)
    # Panel: before the .wrap-closing </div> that precedes </body>.
    marker = "</div></body></html>"
    if marker not in html:
        raise RuntimeError("could not find wrap-close marker to inject QR panel")
    return html.replace(marker, panel + marker, 1)


# ------------------------------------------------------------------ PDF render
def html_to_pdf(html_path: str, pdf_path: str):
    """Render the mailer HTML to A4 print PDF via headless Chrome (faithful to the
    article's own print stylesheet). file:// so local data-URI/relative assets load."""
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
        page.pdf(path=pdf_path, format="A4", print_background=True,
                 margin={"top": "14mm", "bottom": "14mm", "left": "14mm", "right": "14mm"})
        browser.close()


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

    mail_html = inject_qr(html, offmarket, address_short)
    mail_html_path = os.path.join(out_dir, f"{article_slug}.mailer.html")
    with open(mail_html_path, "w", encoding="utf-8") as fh:
        fh.write(mail_html)

    pdf_path = os.path.join(out_dir, f"{article_slug}.pdf")
    html_to_pdf(mail_html_path, pdf_path)

    r.update({"mailer_html": mail_html_path, "pdf": pdf_path,
              "offmarket_url": offmarket, "url_slug": slug})
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
    a = ap.parse_args()

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
