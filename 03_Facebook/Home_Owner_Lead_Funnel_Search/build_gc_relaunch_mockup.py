#!/usr/bin/env python3
"""
build_gc_relaunch_mockup.py — review page for the Gold Coast relaunch ad set.

Separate artifact from the Valuation-category mockups (V1 0e7ef5f8…, V2 133b158f…).
Those were about Campaign 1 entry architecture; this is the seller-intent Home Owner
funnel, relaunched locally after the Brisbane copy-discovery test.

Run: source /home/fields/venv/bin/activate && python3 build_gc_relaunch_mockup.py
Out: mockup/gc_relaunch_review.html
"""
import base64, io, os
from PIL import Image

ROOT = os.path.dirname(os.path.abspath(__file__))
CARDS = os.path.join(ROOT, "creatives_gc_relaunch")
OUT = os.path.join(ROOT, "mockup")
EMBED_W = 760


def data_uri(path):
    im = Image.open(path).convert("RGB").resize((EMBED_W, EMBED_W), Image.LANCZOS)
    buf = io.BytesIO()
    im.save(buf, format="JPEG", quality=88, optimize=True)
    return "data:image/jpeg;base64," + base64.b64encode(buf.getvalue()).decode()


ADS = [
    {
        "id": "GC2", "file": "GC2_missmillion_light.png",
        "name": "Missed by a million",
        "variant": "Light — as it ran",
        "verdict": "Proven", "vkind": "proven",
        "why": ("The only angle in the entire Brisbane test that produced a "
                "<b>repeat selling-intent lead</b> — 2 of 2 answered "
                "<code>selling_intent: yes</code>, at $17.50 each. Every other angle "
                "managed one Yes or none."),
        "primary": (
            "An online estimate valued a Burleigh Waters home at $1,440,000. "
            "It sold for $2,500,000.\n\n"
            "The estimate carried a published range of $1,240,000 to $1,640,000, and was "
            "rated “high confidence.” The sale came in $860,000 above the top of it.\n\n"
            "These tools have never walked through your home. They read what is on paper.\n\n"
            "Curious what the comparable sales near you actually say about a home like "
            "yours? We’ll show you the range."),
        "headline": "An online estimate said $1,440,000. It sold for $2,500,000.",
        "desc": "Recent comparable sales near you, as a range. No pitch.",
        "evidence": [
            ("130 Christine Avenue, Burleigh Waters", "verified in <code>Gold_Coast.burleigh_waters</code>"),
            ("Estimate $1,440,000 · range $1,240,000–$1,640,000 · label “High”", "<code>domain_valuation_at_listing</code>, dated Nov 2025"),
            ("Sold $2,500,000 on 20 April 2026", "<code>sale_price</code> — the only trustworthy sold field"),
            ("Error $1,060,000 (73.6%) · <code>within_range: false</code>", "meets our publication rule"),
        ],
        "note": ("Estimate is dated <b>five months before</b> the sale, so this is a "
                 "genuine forward test rather than a portal that simply hadn’t caught up. "
                 "We quote the portal’s own confidence label as a fact about its output — "
                 "permitted — and never name the portal."),
    },
    {
        "id": "GC3", "file": "GC3_neighbourpair_dark.png",
        "name": "The neighbour pair",
        "variant": "Dark — as it ran",
        "verdict": "Rebuilt", "vkind": "rebuilt",
        "why": ("Highest lead rate of anything we ran — <b>2 leads from 91 people "
                "reached, in a single day on $8.07</b>. That is 2.20% lead-per-reach "
                "against the winner’s 0.35%. It was written off on those 2 leads both "
                "answering “no”, which at the test’s own 57% base rate happens 18.5% of "
                "the time by chance. Under-tested, not beaten."),
        "primary": (
            "Two homes in Varsity Lakes. Both three bedrooms, two bathrooms, two car "
            "spaces. Both on exactly 350 square metres.\n\n"
            "One sold in 4 days for $1,400,000. The other took 61 days and sold for "
            "$1,280,000.\n\n"
            "They sold three weeks apart, so the market barely moved between them. The "
            "difference wasn’t the market — and on paper, it wasn’t the house either.\n\n"
            "Curious what the recent sales near you actually say about a home like yours? "
            "We’ll show you the range."),
        "headline": "Same suburb, same house, same land. $120,000 apart.",
        "desc": "Recent comparable sales near you, as a range. No pitch.",
        "evidence": [
            ("14 Bergamo Drive — 4 days on market, $1,400,000, 10 Oct 2025", "Domain property timeline"),
            ("19 Tourangeau Crescent — 61 days, $1,280,000, 3 Nov 2025", "Domain property timeline"),
            ("Both 3 bed / 2 bath / 2 car · both exactly 350 m²", "<code>land_size_sqm</code>"),
            ("Same <code>days_on_market_source</code> for both", "identical measurement basis"),
        ],
        "note": ("⚠ The inherited copy claimed <b>$55,000 more and 59 days faster</b>. "
                 "That pair <b>does not exist</b> in our data — 838 rows searched across "
                 "both days-on-market fields, zero matches. The “61 days” in the old copy "
                 "is what led to the real pair, and the real gap is <b>$120,000</b>. Two "
                 "claims were also removed: “came down” (no price reduction is recorded) "
                 "and the causal line about pricing, which was a verdict on an "
                 "identifiable listing agent."),
    },
    {
        "id": "GC5", "file": "GC5_thechoice_dark.png",
        "name": "Which three",
        "variant": "Dark — as it ran",
        "verdict": "Premise rebuilt", "vkind": "rebuilt",
        "why": ("AN15's <b>angle</b> is kept and its <b>premise</b> replaced. The original "
                "blamed the agent's motive — “the incentive was to list fast, not to list "
                "right” — which is a verdict on an identified class, and a premise the "
                "same study measured as <b>false</b> (agent vs Fields on accuracy is a "
                "coin flip). What that study does support is <b>indeterminacy</b>, which "
                "indicts nobody and is the stronger claim. Dark, because that is the "
                "variant that produced AN15's Yes."),
        "primary": (
            "Three comparable sales. That is the standard method for valuing a home — and "
            "it is more fragile than it looks.\n\n"
            "We took 512 homes that later sold and enumerated every reasonable set of "
            "three comparable sales that could have been selected before the result was "
            "known. For the typical home, the gap between the highest and lowest "
            "defensible three-sale estimate was $469,000.\n\n"
            "That does not mean one answer was dishonest. It means choosing only a few "
            "sales makes the answer highly sensitive to which ones happen to be chosen.\n\n"
            "Curious what the full comparable set says about a home like yours? We'll show "
            "you the range."),
        "headline": "Two honest agents can be $469,000 apart.",
        "desc": "Recent comparable sales near you, as a range. No pitch.",
        "evidence": [
            ("512 sold houses $1,000,000–$2,000,000, the three target suburbs", "<code>RESULT_dispersion_512.md</code>, run 2026-08-06"),
            ("Pool matched on type, beds, baths and land \u00b120%, sold in the prior 12 months", "median qualifying pool 21 sales"),
            ("Every possible trio enumerated \u00b7 subject excluded \u00b7 no sale on or after its date", "no hindsight"),
            ("Median spread 32.9% = $469,000 \u00b7 exceeds 20% of value on 77.0% of homes", "this is the published figure on /offmarket"),
        ],
        "note": ("⚠ I previously advised against $469,000 in favour of $227,500. That was "
                 "<b>wrong</b>, and it came from conflating two different studies. $227,500 "
                 "is from a separate experiment using a deliberately strict pool (6 months, "
                 "2km, land <i>and</i> floor area \u00b120%). $469,000 is from this one, whose pool "
                 "matches on type, beds, baths and land — a perfectly defensible "
                 "construction, and the figure we already publish on /offmarket. The real "
                 "constraint is narrower than I stated: do not attach $469,000 to the QLD "
                 "statutory three-comparable definition, because the statutory pool is "
                 "<i>wider</i> (5km, crossing suburbs) and that would misattribute the "
                 "population."),
    },
]

EXCLUDED = [
    ("AN14 — the 7-day window", "1 Yes @ $26.52",
     "Its claim — 100 buyer views on day 1 falling to 25 by day 7 and 17 by day 30, with "
     "a price reduction lifting views to 29 for a single day — has <b>no provenance in "
     "our data or a cited source</b>. It may well be true and may well be someone else's "
     "study, but we would have to stand behind it. It is also time-decay framing, which "
     "is on the funnel's dead-angle list. Hold until the source is established — this is "
     "recoverable, not dead."),
    ("AN1 and AN4 — “89% overvalued”", "0 leads",
     "Both sit in the same paused GC campaign and would go live with it. They claim "
     "“We tested 1,689 online home-value estimates on the Gold Coast. 89% were "
     "overvalued.” That benchmark is <b>hindsight-contaminated</b> — 91.8% of those "
     "estimates were captured after the sale, leaving a clean subset of 21. "
     "<b>Enable the ads individually, never the campaign.</b>"),
]


FORM = {
    "id": "1961613607744103",
    "name": "Fields — Seller Intent (report) v1 — name+email+phone",
    "status": "ACTIVE",
    "steps": [
        ("Intro card", "See what the comparable sales say your home is worth",
         "Recent comparable sales near you — adjusted for your home and shown as a range, "
         "not a single guess. From a licensed Gold Coast agent. No pitch.",
         "By continuing you agree Fields Real Estate may call, SMS or email you about your "
         "property and our market data — opt out anytime by replying STOP. We're a "
         "data-first service, not a call centre.", "Get started"),
        ("Question", "Are you considering selling in the next 12 months?",
         "Yes&nbsp;&nbsp;·&nbsp;&nbsp;Maybe, exploring&nbsp;&nbsp;·&nbsp;&nbsp;No, just curious",
         "This single answer is what separates a $17.50 lead from a worthless one. It is "
         "the field the whole ranking in section 02 is built on.", "Next"),
        ("Contact", "Full name · Email · Phone number",
         "Pre-filled by Meta from the profile — the reason instant forms convert at all.",
         "Phone is included deliberately: prior testing showed it does not suppress volume "
         "on this account, and without it nobody can be called.", "Submit"),
        ("Thank you", "Got it.",
         "Will will call you shortly to walk through the numbers for a home like yours. "
         "Want a head start? Enter your address now.",
         "Button: <b>View my home's data</b> → fieldsestate.com.au/analyse-your-home",
         "View my home's data"),
    ],
}

CSS = """
:root{
  --bg:#faf9f6; --panel:#fffefb; --edge:#e2ddd2; --edge2:#efece4;
  --ink:#1c1f1c; --ink2:#4f544d; --ink3:#837f74;
  --accent:#7a5c2e; --accent-soft:#f3ebdc;
  --proven:#3d6b45; --proven-soft:#e7f0e8;
  --rebuilt:#8a5a24; --rebuilt-soft:#f6ebdd;
  --new:#3f5f7a; --new-soft:#e6eef4;
  --warn:#a8402c; --warn-soft:#f8e8e4;
  --mono:ui-monospace,SFMono-Regular,Menlo,Consolas,monospace;
}
@media (prefers-color-scheme:dark){:root{
  --bg:#16181a; --panel:#1e2124; --edge:#33383c; --edge2:#282c2f;
  --ink:#f0f0ee; --ink2:#adb2ad; --ink3:#7f847e;
  --accent:#d8b678; --accent-soft:#2b2318;
  --proven:#8dc398; --proven-soft:#1d2a20;
  --rebuilt:#d9a468; --rebuilt-soft:#2c2117;
  --new:#8fb6d4; --new-soft:#1b262e;
  --warn:#e08a72; --warn-soft:#2e1d19;
}}
:root[data-theme="dark"]{
  --bg:#16181a; --panel:#1e2124; --edge:#33383c; --edge2:#282c2f;
  --ink:#f0f0ee; --ink2:#adb2ad; --ink3:#7f847e;
  --accent:#d8b678; --accent-soft:#2b2318;
  --proven:#8dc398; --proven-soft:#1d2a20;
  --rebuilt:#d9a468; --rebuilt-soft:#2c2117;
  --new:#8fb6d4; --new-soft:#1b262e;
  --warn:#e08a72; --warn-soft:#2e1d19;
}
:root[data-theme="light"]{
  --bg:#faf9f6; --panel:#fffefb; --edge:#e2ddd2; --edge2:#efece4;
  --ink:#1c1f1c; --ink2:#4f544d; --ink3:#837f74;
  --accent:#7a5c2e; --accent-soft:#f3ebdc;
  --proven:#3d6b45; --proven-soft:#e7f0e8;
  --rebuilt:#8a5a24; --rebuilt-soft:#f6ebdd;
  --new:#3f5f7a; --new-soft:#e6eef4;
  --warn:#a8402c; --warn-soft:#f8e8e4;
}
*{box-sizing:border-box}
body{margin:0;background:var(--bg);color:var(--ink);
 font:16px/1.62 system-ui,-apple-system,'Segoe UI',Roboto,sans-serif;-webkit-font-smoothing:antialiased}
.wrap{max-width:1120px;margin:0 auto;padding:0 24px 110px}
code{font-family:var(--mono);font-size:.85em;background:var(--edge2);padding:.12em .38em;
 border-radius:4px;color:var(--ink2)}
i{font-family:Georgia,serif}
header{padding:74px 0 34px;border-bottom:1px solid var(--edge)}
.tag{display:inline-block;font:600 11.5px/1 var(--mono);letter-spacing:.15em;text-transform:uppercase;
 color:var(--accent);background:var(--accent-soft);border:1px solid var(--accent);
 border-radius:100px;padding:7px 13px;margin-bottom:20px}
h1{font-size:clamp(29px,4.4vw,48px);line-height:1.05;margin:0 0 16px;letter-spacing:-.028em;
 font-weight:800;text-wrap:balance;max-width:20ch}
.lede{font-size:18px;color:var(--ink2);max-width:68ch;margin:0}
.lede b{color:var(--ink);font-weight:650}
.warnbox{margin-top:26px;padding:15px 18px;background:var(--panel);border:1px solid var(--edge);
 border-left:3px solid var(--warn);border-radius:0 8px 8px 0;font-size:14.5px;color:var(--ink2);max-width:76ch}
section{padding-top:62px}
.sh{display:flex;align-items:baseline;gap:14px;margin-bottom:8px}
.sn{font:700 12px/1 var(--mono);letter-spacing:.12em;color:var(--accent)}
h2{font-size:clamp(21px,2.5vw,27px);margin:0;letter-spacing:-.02em;font-weight:750}
.sd{color:var(--ink2);max-width:70ch;margin:0 0 32px;font-size:15.5px}
.ad{display:grid;grid-template-columns:minmax(300px,420px) 1fr;gap:34px;
 padding:30px 0;border-top:1px solid var(--edge)}
.ad:first-of-type{border-top:none;padding-top:6px}
.col{min-width:0}
.hd{display:flex;align-items:center;gap:11px;flex-wrap:wrap;margin-bottom:14px}
.aid{font:700 13px/1 var(--mono);color:var(--ink3)}
.anm{font-size:21px;font-weight:760;letter-spacing:-.018em}
.vd{font:600 10.5px/1 var(--mono);letter-spacing:.09em;text-transform:uppercase;
 padding:6px 10px;border-radius:100px}
.vd.proven{color:var(--proven);background:var(--proven-soft);border:1px solid var(--proven)}
.vd.rebuilt{color:var(--rebuilt);background:var(--rebuilt-soft);border:1px solid var(--rebuilt)}
.vd.new{color:var(--new);background:var(--new-soft);border:1px solid var(--new)}
.var{font:600 10.5px/1 var(--mono);letter-spacing:.07em;color:var(--ink3);background:var(--edge2);border:1px solid var(--edge);border-radius:100px;padding:6px 10px}
.fb{background:var(--panel);border:1px solid var(--edge);border-radius:12px;overflow:hidden}
.fbtop{display:flex;align-items:center;gap:10px;padding:12px 13px 9px}
.av{width:38px;height:38px;border-radius:50%;flex:0 0 38px;background:linear-gradient(135deg,#d9645b,#e69084)}
.fbn{font-size:13.5px;font-weight:650;line-height:1.25}
.fbm{font-size:11.5px;color:var(--ink3);display:flex;align-items:center;gap:5px}
.fbm svg{width:11px;height:11px;fill:currentColor}
.fbtxt{padding:2px 13px 11px;font-size:14px;line-height:1.45;white-space:pre-wrap}
.more{color:var(--ink3)}
.fold{display:flex;align-items:center;gap:9px;padding:0 13px 9px;
 font:600 9.5px/1 var(--mono);letter-spacing:.11em;text-transform:uppercase;color:var(--warn)}
.fold:before,.fold:after{content:"";height:1px;background:var(--warn);opacity:.38;flex:1}
.fbimg{display:block;width:100%;border-top:1px solid var(--edge2);border-bottom:1px solid var(--edge2)}
.fbfoot{display:flex;align-items:center;gap:12px;padding:11px 13px;background:var(--edge2)}
.fbfl{flex:1;min-width:0}
.fbfd{font-size:11px;color:var(--ink3);text-transform:uppercase;letter-spacing:.05em}
.fbfh{font-size:13.5px;font-weight:650;line-height:1.3;margin-top:2px}
.fbb{flex:0 0 auto;font-size:12.5px;font-weight:650;padding:8px 13px;border-radius:6px;
 background:var(--edge);color:var(--ink2)}
.blk{margin-bottom:20px}
.blk:last-child{margin-bottom:0}
.blbl{font:600 10.5px/1 var(--mono);letter-spacing:.11em;text-transform:uppercase;
 color:var(--ink3);margin-bottom:9px}
.btxt{font-size:14.5px;color:var(--ink2);line-height:1.62}
.btxt b{color:var(--ink);font-weight:650}
.ev{list-style:none;margin:0;padding:0;display:flex;flex-direction:column;gap:9px}
.ev li{display:grid;grid-template-columns:auto 1fr;gap:11px;align-items:start;font-size:13.5px}
.ev .tick{color:var(--proven);font-weight:800;line-height:1.5}
.ev .claim{color:var(--ink);font-weight:600}
.ev .src{color:var(--ink3);font-size:12.5px;display:block;font-weight:400;margin-top:1px}
.excl{display:flex;flex-direction:column;gap:16px}
.ex{display:grid;grid-template-columns:auto 1fr;gap:18px;align-items:start;background:var(--panel);
 border:1px solid var(--edge);border-left:3px solid var(--warn);border-radius:0 10px 10px 0;padding:17px 19px}
.exm{font:600 10.5px/1 var(--mono);letter-spacing:.08em;color:var(--ink3);
 background:var(--edge2);border-radius:100px;padding:6px 10px;white-space:nowrap;margin-top:2px}
.ext{font-size:16px;font-weight:700;margin-bottom:6px;letter-spacing:-.014em}
.exd{font-size:14px;color:var(--ink2);line-height:1.6}
table{width:100%;border-collapse:collapse;font-size:14px;margin-top:6px}
th{text-align:left;font:600 10.5px/1 var(--mono);letter-spacing:.09em;text-transform:uppercase;
 color:var(--ink3);padding:0 12px 10px 0;border-bottom:1px solid var(--edge)}
td{padding:11px 12px 11px 0;border-bottom:1px solid var(--edge2);color:var(--ink2);
 font-variant-numeric:tabular-nums}
td.n{color:var(--ink);font-weight:650}
tr.hi td{color:var(--ink);font-weight:600}
.tw{overflow-x:auto}
.form{display:grid;grid-template-columns:repeat(auto-fit,minmax(250px,1fr));gap:18px}
.fs{background:var(--panel);border:1px solid var(--edge);border-radius:12px;padding:18px 19px;
 display:flex;flex-direction:column;gap:10px}
.fstep{font:600 10.5px/1 var(--mono);letter-spacing:.11em;text-transform:uppercase;color:var(--accent)}
.fh{font-size:16px;font-weight:700;line-height:1.3;letter-spacing:-.012em}
.fb2{font-size:13.5px;color:var(--ink2);line-height:1.55}
.fleg{font-size:12px;color:var(--ink3);line-height:1.5;padding-top:9px;border-top:1px dashed var(--edge)}
.fbtn{margin-top:auto;background:var(--edge2);border:1px solid var(--edge);border-radius:7px;
 padding:10px;text-align:center;font-size:12.5px;font-weight:650;color:var(--ink2)}
footer{margin-top:76px;padding-top:26px;border-top:1px solid var(--edge);font-size:13px;
 color:var(--ink3);display:flex;justify-content:space-between;gap:18px;flex-wrap:wrap}
@media(max-width:820px){.ad{grid-template-columns:1fr;gap:24px}}
"""

GLOBE = ('<svg viewBox="0 0 16 16"><path d="M8 1a7 7 0 100 14A7 7 0 008 1zm0 1.5c.9 0 '
         '1.9 1.6 2.2 3.9H5.8C6.1 4.1 7.1 2.5 8 2.5zM5.6 6.9h4.8a13 13 0 010 2.2H5.6a13 '
         '13 0 010-2.2zm.2 3.7h4.4C9.9 12.9 8.9 14.5 8 14.5s-1.9-1.6-2.2-3.9zm6-3.7h2.2a5.5 '
         '5.5 0 010 2.2h-2.2a14 14 0 000-2.2zm-.3-1.5a8.6 8.6 0 00-1-2.7 5.5 5.5 0 012.6 '
         '2.7h-1.6zm-7 0H2.9a5.5 5.5 0 012.6-2.7 8.6 8.6 0 00-1 2.7zM2.4 6.9h2.2a14 14 0 '
         '000 2.2H2.4a5.5 5.5 0 010-2.2zm.5 3.7h1.6a8.6 8.6 0 001 2.7 5.5 5.5 0 01-2.6-2.7zm'
         '8.2 2.7a8.6 8.6 0 001-2.7h1.6a5.5 5.5 0 01-2.6 2.7z"/></svg>')

ROWS = [
    ("AN2 missed a million", "855", "$51.19", "2", "2", "$17.50", True),
    ("AN15 the $150k gap", "486", "$40.69", "1", "1", "$25.63", True),
    ("AN14 the 7-day window", "684", "$45.01", "1", "1", "$26.52", False),
    ("AN3 the neighbour", "341", "$24.28", "2", "0", "—", True),
    ("AN10 stale listing", "400", "$33.29", "0", "0", "—", False),
    ("AN13 reno return", "451", "$32.69", "0", "0", "—", False),
    ("AN5 national crash", "509", "$32.31", "0", "0", "—", False),
]


def build():
    os.makedirs(OUT, exist_ok=True)
    ads = []
    for a in ADS:
        d = dict(a); d["img"] = data_uri(os.path.join(CARDS, a["file"])); ads.append(d)

    blocks = ""
    for a in ads:
        ev = "".join(
            f'<li><span class="tick">✓</span><span><span class="claim">{c}</span>'
            f'<span class="src">{s}</span></span></li>' for c, s in a["evidence"])
        blocks += (
            f'<div class="ad">'
            f'<div class="col">'
            f'<div class="hd"><span class="aid">{a["id"]}</span>'
            f'<span class="anm">{a["name"]}</span>'
            f'<span class="vd {a["vkind"]}">{a["verdict"]}</span>'
            f'<span class="var">{a["variant"]}</span></div>'
            f'<div class="fb">'
            f'<div class="fbtop"><div class="av"></div><div>'
            f'<div class="fbn">Fields Real Estate</div>'
            f'<div class="fbm">Sponsored · {GLOBE}</div></div></div>'
            f'<div class="fbtxt" data-full="{a["primary"].replace(chr(34), "&quot;")}"></div>'
            f'<div class="fold">fold</div>'
            f'<img class="fbimg" src="{a["img"]}" alt="{a["name"]} creative">'
            f'<div class="fbfoot"><div class="fbfl">'
            f'<div class="fbfd">Instant form · name, email, phone</div>'
            f'<div class="fbfh">{a["headline"]}</div></div>'
            f'<div class="fbb">Learn more</div></div></div>'
            f'</div>'
            f'<div class="col">'
            f'<div class="blk"><div class="blbl">Why it is in the set</div>'
            f'<div class="btxt">{a["why"]}</div></div>'
            f'<div class="blk"><div class="blbl">Every figure, and where it came from</div>'
            f'<ul class="ev">{ev}</ul></div>'
            f'<div class="blk"><div class="blbl">Note</div>'
            f'<div class="btxt">{a["note"]}</div></div>'
            f'</div></div>')

    excl = "".join(
        f'<div class="ex"><span class="exm">{m}</span>'
        f'<div><div class="ext">{t}</div><div class="exd">{d}</div></div></div>'
        for t, m, d in EXCLUDED)

    formsteps = "".join(
        f'<div class="fs"><div class="fstep">{st}</div><div class="fh">{h}</div>'
        f'<div class="fb2">{b}</div><div class="fleg">{leg}</div>'
        f'<div class="fbtn">{btn}</div></div>'
        for st, h, b, leg, btn in FORM["steps"])

    rows = "".join(
        f'<tr class="{"hi" if hi else ""}"><td class="n">{n}</td><td>{r}</td><td>{s}</td>'
        f'<td>{l}</td><td class="n">{y}</td><td class="n">{c}</td></tr>'
        for n, r, s, l, y, c, hi in ROWS)

    js = """
const FOLD_AT = 125;
document.querySelectorAll('.fbtxt').forEach(el => {
  const flat = el.dataset.full.replace(/\\n+/g, ' ');
  if (flat.length <= FOLD_AT) { el.textContent = flat; return; }
  const raw = flat.slice(0, FOLD_AT);
  const head = raw.slice(0, raw.lastIndexOf(' ')).replace(/[,\\u2014\\u2013-]$/, '').trim();
  el.textContent = head + '\\u2026 ';
  const s = document.createElement('span');
  s.className = 'more'; s.textContent = 'See more';
  el.appendChild(s);
});
"""

    html = f"""<title>Gold Coast relaunch — the three seller ads</title>
<style>{CSS}</style>
<div class="wrap">
<header>
  <div class="tag">Home Owner funnel · Gold Coast relaunch</div>
  <h1>Three ads worth putting local money behind.</h1>
  <p class="lede">The 56-ad test that produced these ran in <b>Brisbane and the Sunshine
  Coast with the Gold Coast excluded</b>, on deliberately geo-neutral copy. It was copy
  discovery, not a performance benchmark — our own note on it says the funnel
  <b>shape</b> transfers and the <b>economics do not</b>. So these are rebuilt for the
  target market and every figure re-verified against our own sold data.</p>
  <div class="warnbox"><b>Cost per lead is the wrong yardstick here.</b> The whole test
  produced 7 leads and only 4 answered <code>selling_intent: yes</code>. The cheapest ad
  in the account produced none of them. Everything below is ranked on cost per
  <i>Yes</i>, and on how little exposure each angle has actually had.</div>
</header>

<section>
  <div class="sh"><span class="sn">01</span><h2>The set</h2></div>
  <p class="sd">One proven, one rebuilt, one new. Each shown as it appears in the feed
  with the 125-character fold marked, beside the provenance for every number on the card.</p>
  {blocks}
</section>

<section>
  <div class="sh"><span class="sn">02</span><h2>What the Brisbane test actually showed</h2></div>
  <p class="sd">Reach is people, not impressions. Only three ads of fifty-six ever produced
  a single selling-intent lead — and the three highlighted rows are the three carried forward.</p>
  <div class="tw"><table>
    <thead><tr><th>angle</th><th>reach</th><th>spend</th><th>leads</th><th>yes</th><th>$/yes</th></tr></thead>
    <tbody>{rows}</tbody>
  </table></div>
  <p class="sd" style="margin-top:18px">AN10, AN13 and AN5 are there for contrast: they
  ran the highest click-through rates on the account — 10.9%, 10.4%, 10.0% — and produced
  <b>zero leads between them</b>. Click-through is not the thing to optimise.</p>
</section>

<section>
  <div class="sh"><span class="sn">03</span><h2>Deliberately left out</h2></div>
  <p class="sd">Two of these produced a selling-intent lead and are still excluded. That is
  not caution for its own sake — each has a specific problem that spend would make worse.</p>
  <div class="excl">{excl}</div>
</section>

<section>
  <div class="sh"><span class="sn">04</span><h2>The form all three open</h2></div>
  <p class="sd">One instant form, held constant across all three ads — so the creative is the
  only variable. It already exists and is <b>ACTIVE</b>: form <code>1961613607744103</code>.
  This is the exact live copy, not a draft.</p>
  <div class="form">{formsteps}</div>
  <div class="warnbox" style="margin-top:24px"><b>⚠ The thank-you page makes a promise.</b>
  “<i>Will will call you shortly to walk through the numbers</i>” is a written commitment,
  and it is the difference between these forms and the Brisbane test form — that one
  deliberately ended on “Your details are in.” with no button, because out-of-market leads
  were never going to be served. Switching these on means somebody phones every Yes. That
  is the open question from earlier in the week, and it is now the gating one.</div>
</section>

<footer>
  <span>Fields Real Estate · 03_Facebook/Home_Owner_Lead_Funnel_Search</span>
  <span>Figures verified against Gold_Coast sold data, 18 August 2026</span>
</footer>
</div>
<script>{js}</script>
"""
    p = os.path.join(OUT, "gc_relaunch_review.html")
    open(p, "w").write(html)
    print(f"{p}  ({os.path.getsize(p)/1024:.0f} KB)")


if __name__ == "__main__":
    build()
