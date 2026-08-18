#!/usr/bin/env python3
"""
render_gc_relaunch_cards.py — the Gold Coast relaunch set (1080x1080).

⚠ EACH CARD IS RENDERED IN THE VARIANT THAT ACTUALLY PRODUCED THE LEAD.
The "dark vs light is null" result is a MAIN EFFECT across 23 angles (p=0.51). It does not
license swapping the variant of a specific winner you are trying to replicate — hold what
you are not testing. Per-angle, the lead-producing variants were:

    AN2  missmillion   -> LIGHT  (2 leads, both selling_intent:yes, $17.50/Yes)
                          the dark twin ran 319 impressions and produced 0
    AN3  neighbour     -> DARK   (2 leads off 91 reach in one day; light: 283 impr, 0 leads)
    AN15 150k gap      -> DARK   (1 Yes @ $25.63; light: 204 impr, 0 leads)

CSS below is lifted verbatim from render_test_cards.py so the replicas are identical in
treatment to the creatives that ran — same gradient, same coral #e0645b, same bar geometry.
Only the figures and labels change.

Every figure is verified. See AN3_GC_REBUILD_2026-08-18.md and
15_Off-Market/Page_Redesign_V4/Prototypes/RESULT_dispersion_512.md.

Run: source /home/fields/venv/bin/activate && python3 render_gc_relaunch_cards.py
Out: creatives_gc_relaunch/*.png
"""
import os, base64, subprocess, tempfile, shutil
from PIL import Image

# Official brand lockup (Hero = wordmark + F mark, 1194x360). Three colourways:
#   Grass  #21382C — for light/bone grounds
#   Birch  #E6DED3 — for dark grounds
#   Copper #B86849 — not used here; the card accent is the proven coral #e0645b and
#                    swapping it would change a variable the winning creatives held.
LOGOS = "/home/fields/Fields_Orchestrator/00_Run_Commands/Logo_Files/logo_pack"
LOGO = {
    "grass": f"{LOGOS}/1-Grass/\u2022 PNG/1-Fields-Hero-Grass.png",
    # NB: the Birch folder's hero file is misnamed "-Grass" upstream; the pixels are Birch.
    "birch": f"{LOGOS}/2-Birch/\u2022 PNG/1-Fields-Hero-Grass.png",
}


def logo_uri(key):
    with open(LOGO[key], "rb") as f:
        return "data:image/png;base64," + base64.b64encode(f.read()).decode()

ROOT = os.path.dirname(os.path.abspath(__file__))
OUT = os.path.join(ROOT, "creatives_gc_relaunch")

CSS = """
*{box-sizing:border-box;margin:0;padding:0}
html,body{width:1080px;height:1080px;overflow:hidden;background:#11161b}
body{font-family:system-ui,-apple-system,'Segoe UI',Roboto,sans-serif;-webkit-font-smoothing:antialiased}
.card{position:absolute;top:0;left:0;width:1080px;height:1080px;color:#f3efe6;overflow:hidden}
.brand{position:absolute;top:52px;left:56px;z-index:5}
/* 1194x360 lockup at 54px tall -> 179px wide. Optical size matched to the old
   34px wordmark so the composition below it is unchanged. */
.brand img{height:54px;width:auto;display:block}
.data{display:flex;flex-direction:column;justify-content:center;height:100%;padding:96px 72px;gap:30px;background:radial-gradient(120% 100% at 78% 8%,#33434c,#212c33 46%,#161f26 100%)}
.data.bone{background:#f3efe6;color:#1a232a}
.klabel{font-size:30px;letter-spacing:.16em;text-transform:uppercase;color:#9aa3a3;font-weight:600}
.data.bone .klabel{color:#7c766a}
.klabel.sm{font-size:25px;letter-spacing:.11em}
.statement{font-size:76px;line-height:1.05;font-weight:850;letter-spacing:-.025em;max-width:16ch}
.statement.sm{font-size:60px}
.statement.xs{font-size:54px;max-width:19ch}
/* keep multi-word emphasis together — 'a million' was orphaning its article */
.statement em{font-family:Georgia,serif;font-style:italic;font-weight:500;color:#e0645b;white-space:nowrap}
.data.bone .statement em{color:#c24a41}
.sub{font-size:33px;line-height:1.42;color:#aeb6b5;max-width:27ch}
.data.bone .sub{color:#5f665f}
.footer{position:absolute;bottom:52px;left:72px;right:72px;font-size:23px;color:#7f8887;letter-spacing:.03em;line-height:1.5}
.data.bone .footer{color:#8a857a}
.twonum{display:flex;flex-direction:column;width:100%;margin:6px 0}
.trow{display:flex;align-items:baseline;justify-content:space-between;gap:24px;padding:34px 0;border-bottom:2px dashed rgba(255,255,255,.2)}
.data.bone .trow{border-bottom-color:rgba(0,0,0,.15)}
.trow .lab{font-size:32px;letter-spacing:.1em;text-transform:uppercase;color:#9aa3a3;white-space:nowrap}
.data.bone .trow .lab{color:#7c766a}
.trow .fig{font-size:60px;font-weight:840;font-variant-numeric:tabular-nums;white-space:nowrap}
.trow .fig.est{color:#c2cac7;text-decoration:line-through;text-decoration-color:rgba(230,120,104,.85);text-decoration-thickness:3px}
.data.bone .trow .fig.est{color:#9aa0a3}
.trow .fig.bad{color:#e0645b;font-family:Georgia,serif;font-style:italic;font-weight:600}
.data.bone .trow .fig.bad{color:#c24a41}
.trow .fig.calm{color:#9aa3a3}
.trow.last{border-bottom:none}
.bars{display:flex;flex-direction:column;gap:36px;width:100%;margin:6px 0}
.bl{display:flex;justify-content:space-between;gap:20px;font-size:30px;color:#aeb6b5;margin-bottom:16px}
.data.bone .bl{color:#5f665f}
.bl .v{color:#fff;font-weight:800;font-size:38px;white-space:nowrap}
.data.bone .bl .v{color:#1a232a}
.track{height:32px;border-radius:16px;background:rgba(255,255,255,.11);overflow:hidden}
.data.bone .track{background:rgba(0,0,0,.08)}
.fill{height:100%;border-radius:16px}
/* widths are the real ratio: 4 days against 61 days -> 7% and 100% */
.fast .fill{width:7%;background:#7fb890}
.slow .fill{width:100%;background:#e0645b}
"""


def card(inner, bone, footer):
    # Grass on the bone ground, Birch on the dark ground — contrast, not decoration.
    b = f'<div class="brand"><img src="{logo_uri("grass" if bone else "birch")}" alt="Fields"></div>'
    return (f'<div class="card"><div class="data{" bone" if bone else ""}">'
            f'{b}{inner}<div class="footer">{footer}</div></div></div>')


# base -> (inner html, bone?, footer)
CARDS = {
    # ---- GC2 · LIGHT, because AN2_missmillion_LIGHT is the variant that produced both
    # Yes-intent leads. Copy held close to the creative that ran; the figures were
    # already the Gold Coast ones, and both now verify against our sold data. ----
    "GC2_missmillion_light": (
        '<div class="klabel">One home · one online estimate</div>'
        '<div class="twonum">'
        '<div class="trow"><span class="lab">Online estimate</span>'
        '<span class="fig est">$1,440,000</span></div>'
        '<div class="trow last"><span class="lab">Actually sold for</span>'
        '<span class="fig bad">$2,500,000</span></div>'
        '</div>'
        '<div class="statement sm">Wrong by over <em>a million</em> — rated '
        '&ldquo;high confidence.&rdquo;</div>'
        '<div class="sub">How far off is the number for a home like yours?</div>',
        True,
        "130 Christine Avenue, Burleigh Waters · sold 20 April 2026 · public record<br>"
        "Online estimate published November 2025 · range $1,240,000–$1,640,000"),

    # ---- GC3 · DARK with the bar treatment, matching AN3_neighbour_DARK exactly.
    # Numbers rebuilt from a real pair; the inherited $55,000/59-day claim does not exist
    # in our data. Bar labels are now purely factual — the originals ("Priced to the
    # evidence" / "Priced ahead of it") asserted a cause we cannot observe and implicitly
    # judged an identifiable listing agent. ----
    "GC3_neighbourpair_dark": (
        '<div class="klabel sm">Two near-identical homes · same suburb</div>'
        '<div class="statement sm">One sold for <em>$120,000 more</em> — '
        'and 57 days faster.</div>'
        '<div class="bars">'
        '<div class="bar fast"><div class="bl"><span>Sold for $1,400,000</span>'
        '<span class="v">4 days</span></div>'
        '<div class="track"><div class="fill"></div></div></div>'
        '<div class="bar slow"><div class="bl"><span>Sold for $1,280,000</span>'
        '<span class="v">61 days</span></div>'
        '<div class="track"><div class="fill"></div></div></div>'
        '</div>'
        '<div class="sub">Same kind of home, same land. The difference wasn’t '
        'the house.</div>',
        False,
        "Varsity Lakes · both 3 bed, 2 bath, 2 car, 350 m² · sold three weeks apart in "
        "October and November 2025 · Domain property timeline, public records"),

    # ---- GC5 · DARK, because AN15_150kgap_DARK is the variant that produced the Yes.
    # AN15's ANGLE is retained; its PREMISE is replaced. The original blamed the agent's
    # incentive ("to list fast, not to list right") — a verdict on an identified class
    # (POA ss207-209) and a premise the same study measured as FALSE (agent vs Fields is
    # a coin flip, n=512). What that study DOES support is indeterminacy: a statement
    # about the METHOD that indicts nobody. Figure and framing match what we already
    # publish on /offmarket. ----

    # ---- GC6 · DARK, matching AN28_thesplit_DARK (the variant that produced its lead).
    # BENCH ASSET — not live. AN28's angle is the most seller-selective copy in the library
    # ("% of asking price achieved" is meaningless to a buyer), but its inherited figures
    # (top quarter 98-99%, bottom 90-93%) do NOT hold here: locally the top quarter sells
    # ABOVE asking. Recomputed 2026-08-18 by find_scenarios.py asking-quartiles.
    # ⚠ n=48 and BIASED — 86% of sold docs carry the fossilised listing_price, and auctions
    # have no advertised price at all. The sample is private-treaty sales that advertised a
    # fixed price, and the card must say so. Never write "in a typical suburb". ----
    "GC6_thesplit_dark": (
        '<div class="klabel sm">48 recent sales · advertised price vs sold price</div>'
        '<div class="twonum">'
        '<div class="trow"><span class="lab">Top quarter got</span>'
        '<span class="fig bad">102%</span></div>'
        '<div class="trow last"><span class="lab">Bottom quarter got</span>'
        '<span class="fig calm">95%</span></div>'
        '</div>'
        '<div class="statement xs">The top quarter sold <em>above</em> asking. '
        'The bottom quarter took 5% less.</div>'
        '<div class="sub">On a $1,500,000 home, that spread is about $110,000.</div>',
        False,
        "48 private-treaty house sales in Robina, Varsity Lakes and Burleigh Waters that "
        "advertised a fixed price. Auctions excluded — no advertised price to compare. "
        "Public records."),

    "GC5_thechoice_dark": (
        '<div class="klabel sm">512 sold homes · every defensible trio tested</div>'
        '<div class="statement xs">Two honest agents. Same rules, same sales. '
        '<em>$469,000</em> apart.</div>'
        '<div class="sub">Three comparable sales is the standard method. The answer '
        'depends almost entirely on which three get picked.</div>',
        False,
        "512 sold houses $1,000,000–$2,000,000 in Robina, Varsity Lakes and Burleigh "
        "Waters. Every possible set of three comparables enumerated, subject excluded, "
        "no hindsight. Median gap between the highest and lowest."),
}


def render():
    os.makedirs(OUT, exist_ok=True)
    tmp = tempfile.mkdtemp(prefix="gc_relaunch_")
    chrome = shutil.which("google-chrome") or shutil.which("chromium-browser")
    if not chrome:
        raise SystemExit("no chrome/chromium on PATH")
    for base, (inner, bone, foot) in CARDS.items():
        html = (f"<!doctype html><html><head><meta charset=utf-8><style>{CSS}</style>"
                f"</head><body>{card(inner, bone, foot)}</body></html>")
        hp = f"{tmp}/{base}.html"
        open(hp, "w").write(html)
        raw = f"{tmp}/{base}_raw.png"
        subprocess.run(
            [chrome, "--headless=new", "--no-sandbox", "--disable-gpu", "--hide-scrollbars",
             "--force-device-scale-factor=1", "--window-size=1080,1200",
             f"--screenshot={raw}", f"file://{hp}"],
            stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, check=True)
        Image.open(raw).convert("RGB").crop((0, 0, 1080, 1080)).save(f"{OUT}/{base}.png")
        print(f"  {base}.png  ({'light' if bone else 'dark'})")
    shutil.rmtree(tmp, ignore_errors=True)
    print(f"Done -> {OUT}/ ({len(CARDS)} cards)")


if __name__ == "__main__":
    render()
