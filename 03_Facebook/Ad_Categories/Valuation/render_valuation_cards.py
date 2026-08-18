#!/usr/bin/env python3
"""
render_valuation_cards.py — Concept A creatives for the Valuation ad category.

Extends the proven card system from
03_Facebook/Home_Owner_Lead_Funnel_Search/render_test_cards.py (which produced the
champion AN2_missmillion_light: 7.16% CTR, 2 leads @ A$17.50, both "Yes" intent).

LIGHT/BONE ONLY — dark-vs-light is a measured null (p=0.51 across 23 angles), so
rendering both doubles the review surface for a settled question.

Every figure here is verified. See 02_CONCEPT_A_BUILD.md for provenance and the
publication rules (notably: only rows where `within_range` is false).

Output: creatives_valuation/{base}.png (1080x1080)
Run: source /home/fields/venv/bin/activate && python3 render_valuation_cards.py
"""
import os, subprocess, tempfile, shutil
from PIL import Image

ROOT = os.path.dirname(os.path.abspath(__file__))
OUT = os.path.join(ROOT, "creatives_valuation")

CSS = """
*{box-sizing:border-box;margin:0;padding:0}
html,body{width:1080px;height:1080px;overflow:hidden;background:#f3efe6}
body{font-family:system-ui,-apple-system,'Segoe UI',Roboto,sans-serif;-webkit-font-smoothing:antialiased}
.card{position:absolute;top:0;left:0;width:1080px;height:1080px;color:#1a232a;overflow:hidden}
.brand{position:absolute;top:52px;left:56px;z-index:5;font-size:34px;font-weight:800;color:#1a232a;display:flex;align-items:center;gap:16px;opacity:.96}
.brand .m{width:40px;height:40px;border-radius:9px;background:linear-gradient(135deg,#d9645b,#e69084)}
.data{display:flex;flex-direction:column;justify-content:center;height:100%;padding:96px 72px;gap:30px;background:#f3efe6}
/* 24px/.10em keeps the longest label ("... · VARSITY LAKES", 45 chars) on ONE line.
   Held identical across all cards — they are reviewed side by side, so a size that
   varies per card reads as a design inconsistency rather than a fit. */
.klabel{font-size:24px;letter-spacing:.10em;text-transform:uppercase;color:#7c766a;font-weight:600;white-space:nowrap}
.statement{font-size:76px;line-height:1.05;font-weight:850;letter-spacing:-.025em;max-width:16ch}
.statement.sm{font-size:60px}
.statement.xs{font-size:54px;max-width:19ch}
.statement em{font-family:Georgia,serif;font-style:italic;font-weight:500;color:#c24a41}
.sub{font-size:33px;line-height:1.42;color:#5f665f;max-width:27ch}
.footer{position:absolute;bottom:52px;left:72px;right:72px;font-size:24px;color:#8a857a;letter-spacing:.03em;line-height:1.5}
.twonum{display:flex;flex-direction:column;width:100%;margin:6px 0}
.trow{display:flex;align-items:baseline;justify-content:space-between;gap:24px;padding:34px 0;border-bottom:2px dashed rgba(0,0,0,.15)}
.trow .lab{font-size:30px;letter-spacing:.1em;text-transform:uppercase;color:#7c766a;white-space:nowrap}
.trow .fig{font-size:60px;font-weight:840;font-variant-numeric:tabular-nums;text-align:right}
/* a range string is ~23 chars — must step down AND nowrap, or it breaks after the
   en-dash and leaves it dangling at the end of line 1 (caught in review 2026-08-17) */
.trow .fig.range{font-size:40px;color:#6f7676;letter-spacing:-.01em;white-space:nowrap}
.trow .fig.est{color:#9aa0a3;text-decoration:line-through;text-decoration-color:rgba(194,74,65,.85);text-decoration-thickness:3px}
.trow .fig.bad{color:#c24a41;font-family:Georgia,serif;font-style:italic;font-weight:600}
.trow.last{border-bottom:none}
"""


def card(inner, footer=None):
    f = f'<div class="footer">{footer}</div>' if footer else ''
    brand = '<div class="brand"><span class="m"></span>Fields</div>'
    return f'<div class="card"><div class="data">{brand}{inner}{f}</div></div>'


INNER = {
    # ---- P1: PLAN-ALIGNED. Campaign 1 / Territory A / Static Ad A1,
    # "A number isn't a valuation" — the message the marketing plan actually
    # specifies ("worth a range, and there should be evidence behind it"),
    # carried by our own 3-comp sensitivity research rather than by a
    # competitor's miss. Figure is the STRICT pool median ($227,500), the only
    # one that survives a hostile screen — see 00_EVIDENCE_BASE.md §4.
    "P1_range_not_number": (
        '<div class="klabel">313 recent house sales · every possible trio tested</div>'
        '<div class="statement xs">Pick three different sales to compare it with, '
        'and the answer moves <em>$227,500</em>.</div>'
        '<div class="sub">Your home isn’t worth a number. It’s worth a range '
        '— and there should be evidence behind it.</div>'
    ),
    # ---- C1: Release 1 is Competition, not Value Evidence (doc 03: "Begin with
    # Competition"; doc 04 build order puts Value Evidence at 18 of 19). This is the
    # held-constant Competition ad. It makes NO quantified claim on purpose — the
    # reasoning is the message, and a published competitor count is currently
    # unsafe (closest_active caps at 6; doc 00 names that as a guardrail). ----
    "C1_competitive_set": (
        '<div class="klabel">The competitive set · Gold Coast</div>'
        '<div class="statement xs">The home buyers compare yours with may not be '
        '<em>the one you think</em>.</div>'
        '<div class="sub">Not every nearby sale is a rival. Buyers weigh a home '
        'against what they could realistically choose instead.</div>'
    ),
    # ---- A1: the stronger claim. Above the TOP of their own published range. ----
    "A1_geraldton_range": (
        '<div class="klabel">One home · one online estimate · Robina</div>'
        '<div class="twonum">'
        '<div class="trow"><span class="lab">Online estimate</span>'
        '<span class="fig range">$1,170,000 – $1,550,000</span></div>'
        '<div class="trow last"><span class="lab">Sold at auction</span>'
        '<span class="fig bad">$2,020,000</span></div>'
        '</div>'
        '<div class="statement xs"><em>$470,000</em> above the top of its own range '
        '— rated &ldquo;high confidence.&rdquo;</div>'
        '<div class="sub">What does the estimate say about a home like yours?</div>'
    ),
    # ---- A2: the champion's exact two-number structure. Bigger number. ----
    "A2_geraldton_mid": (
        '<div class="klabel">One home · one online estimate · Robina</div>'
        '<div class="twonum">'
        '<div class="trow"><span class="lab">Online estimate</span>'
        '<span class="fig est">$1,360,000</span></div>'
        '<div class="trow last"><span class="lab">Sold at auction</span>'
        '<span class="fig bad">$2,020,000</span></div>'
        '</div>'
        '<div class="statement sm">Out by <em>$660,000</em> — rated '
        '&ldquo;high confidence.&rdquo;</div>'
        '<div class="sub">What does the estimate say about a home like yours?</div>'
    ),
    # ---- A3: Varsity Lakes ad set. Most relatable house, dollar-exact verification. ----
    "A3_brier_range": (
        '<div class="klabel">One home · one online estimate · Varsity Lakes</div>'
        '<div class="twonum">'
        '<div class="trow"><span class="lab">Online estimate</span>'
        '<span class="fig range">$880,000 – $1,160,000</span></div>'
        '<div class="trow last"><span class="lab">Sold at auction</span>'
        '<span class="fig bad">$1,302,000</span></div>'
        '</div>'
        '<div class="statement xs"><em>$142,000</em> above the top of its own range '
        '— rated &ldquo;high confidence.&rdquo;</div>'
        '<div class="sub">What does the estimate say about a home like yours?</div>'
    ),
    # ---- A4: backup. Strongest corroboration in the set, but waterfront. ----
    "A4_vanderbilt_asking": (
        '<div class="klabel">One home · one online estimate · Varsity Lakes</div>'
        '<div class="twonum">'
        '<div class="trow"><span class="lab">Online estimate</span>'
        '<span class="fig est">$1,520,000</span></div>'
        '<div class="trow"><span class="lab">Agent asked</span>'
        '<span class="fig range">Offers over $2,000,000</span></div>'
        '<div class="trow last"><span class="lab">Sold for</span>'
        '<span class="fig bad">$1,895,000</span></div>'
        '</div>'
        '<div class="statement xs">The asking price and the sale price both sat '
        '<em>above</em> the estimate.</div>'
        '<div class="sub">What does the estimate say about a home like yours?</div>'
    ),
}

FOOT = {
    "P1_range_not_number":
        "Median spread across 313 detached house sales $1,000,000–$2,000,000 in "
        "Robina, Varsity Lakes and Burleigh Waters. Comparables: sold within "
        "6 months and 2km, land and floor area within 20%.",
    "C1_competitive_set":
        "Fields Real Estate · local property analysis",
    "A1_geraldton_range":
        "33 Geraldton Drive, Robina · sold 28 May 2026 · public record<br>"
        "Online estimate as published November 2025",
    "A2_geraldton_mid":
        "33 Geraldton Drive, Robina · sold 28 May 2026 · public record<br>"
        "Online estimate as published November 2025",
    "A3_brier_range":
        "39 Brier Crescent, Varsity Lakes · sold 16 May 2026 · public record<br>"
        "Online estimate as published November 2025",
    "A4_vanderbilt_asking":
        "20 Vanderbilt Court, Varsity Lakes · sold 7 July 2026 · public record<br>"
        "Online estimate as published November 2025",
}


def render():
    os.makedirs(OUT, exist_ok=True)
    tmp = tempfile.mkdtemp(prefix="valuation_cards_")
    chrome = shutil.which("google-chrome") or shutil.which("chromium-browser")
    if not chrome:
        raise SystemExit("no chrome/chromium on PATH")
    for base, inner in INNER.items():
        body = card(inner, FOOT.get(base))
        html = (f"<!doctype html><html><head><meta charset=utf-8>"
                f"<style>{CSS}</style></head><body>{body}</body></html>")
        hp = f"{tmp}/{base}.html"
        open(hp, "w").write(html)
        raw = f"{tmp}/{base}_raw.png"
        subprocess.run(
            [chrome, "--headless=new", "--no-sandbox", "--disable-gpu",
             "--hide-scrollbars", "--force-device-scale-factor=1",
             "--window-size=1080,1200", f"--screenshot={raw}", f"file://{hp}"],
            stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, check=True)
        Image.open(raw).convert("RGB").crop((0, 0, 1080, 1080)).save(f"{OUT}/{base}.png")
        print(f"  {base}.png")
    shutil.rmtree(tmp, ignore_errors=True)
    print(f"Done -> {OUT}/ ({len(INNER)} cards)")


if __name__ == "__main__":
    render()
