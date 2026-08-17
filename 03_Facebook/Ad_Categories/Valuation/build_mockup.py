#!/usr/bin/env python3
"""
build_mockup.py — assembles the Concept A review mockup as a single self-contained
HTML file, with the real 1080x1080 creatives embedded as data URIs.

The cards shown are the ACTUAL render output of render_valuation_cards.py — the same
PNGs that would upload to Meta — not an approximation.

Run: source /home/fields/venv/bin/activate && python3 build_mockup.py
Out: mockup/concept_a_review.html
"""
import base64, io, json, os
from PIL import Image

ROOT = os.path.dirname(os.path.abspath(__file__))
CARDS = os.path.join(ROOT, "creatives_valuation")
OUT = os.path.join(ROOT, "mockup")

# Feed renders at ~470px wide; 760 keeps it crisp on 2x displays without bloating
# the file past a few hundred KB per card.
EMBED_W = 760


def data_uri(path):
    im = Image.open(path).convert("RGB")
    im = im.resize((EMBED_W, EMBED_W), Image.LANCZOS)
    buf = io.BytesIO()
    im.save(buf, format="JPEG", quality=88, optimize=True)
    return "data:image/jpeg;base64," + base64.b64encode(buf.getvalue()).decode()


# ---------------------------------------------------------------- ad definitions
ADS = [
    {
        "id": "A1",
        "file": "A1_geraldton_range.png",
        "name": "A1 — above their range",
        "set": "Robina",
        "recommended": True,
        "primary": ("An online estimate put a Robina house between $1,170,000 and "
                    "$1,550,000. It sold at auction for $2,020,000 — $470,000 above "
                    "the top of that range.\n\nThe estimate was rated “high "
                    "confidence.” There was no price guide and no asking price: the "
                    "number came from open bidding on the day.\n\nWe hold the online "
                    "estimate and the sale price for 56 Robina homes sold in the last six "
                    "months. Most were close. Some were not. From the outside there is no "
                    "way to tell which one a home is.\n\nSee the sales, and what the "
                    "comparable sales say about a home like yours."),
        "headline": "Sold $470,000 above its own estimate",
        "desc": "Robina sales, last six months. Public record.",
        "note": ("The stronger claim — unarguable on the estimate's own published "
                 "numbers, and it discloses that the estimate was a range rather than a "
                 "point. Weaker headline number than A2."),
    },
    {
        "id": "A2",
        "file": "A2_geraldton_mid.png",
        "name": "A2 — the bigger number",
        "set": "Robina",
        "recommended": False,
        "primary": ("An online estimate valued a Robina house at $1,360,000. It sold at "
                    "auction for $2,020,000.\n\nThat estimate was rated “high "
                    "confidence.” There was no price guide — the price came from "
                    "open bidding on the day, so it cannot be put down to an optimistic "
                    "asking price.\n\nWe hold the online estimate and the sale price for 56 "
                    "Robina homes sold in the last six months. Most were close. Some were "
                    "not. There is no way to tell from the outside which one a home "
                    "is.\n\nSee the sales, and what the comparable sales say about a home "
                    "like yours."),
        "headline": "Estimated $1,360,000. Sold $2,020,000.",
        "desc": "Robina sales, last six months. Public record.",
        "note": ("The closest replica of the champion (AN2, 7.16% CTR, 2 leads @ A$17.50). "
                 "Bigger, more legible number — but “out by $660,000” "
                 "measures against the midpoint, which a sceptic can dispute."),
    },
    {
        "id": "A3",
        "file": "A3_brier_range.png",
        "name": "A3 — Varsity Lakes",
        "set": "Varsity Lakes",
        "recommended": True,
        "primary": ("An online estimate put a Varsity Lakes house between $880,000 and "
                    "$1,160,000. It sold at auction for $1,302,000 — $142,000 above the "
                    "top of that range.\n\nThe estimate was rated “high "
                    "confidence.” A three-bedroom house on 708 square metres, sold "
                    "under the hammer in May.\n\nWe hold the online estimate and the sale "
                    "price for 31 Varsity Lakes homes sold in the last six months. Most "
                    "were close. Some were not. From the outside there is no way to tell "
                    "which one a home is.\n\nSee the sales, and what the comparable sales "
                    "say about a home like yours."),
        "headline": "Sold $142,000 above its own estimate",
        "desc": "Varsity Lakes sales, last six months. Public record.",
        "note": ("The Varsity Lakes ad set. Smallest gap of the four, but the selling "
                 "agency's own sold page states the price and date to the dollar — the "
                 "most defensible row we hold. A modest 3-bed reads as “a home like "
                 "mine” to this audience."),
    },
    {
        "id": "A4",
        "file": "A4_vanderbilt_asking.png",
        "name": "A4 — backup (waterfront)",
        "set": "Varsity Lakes · held back",
        "recommended": False,
        "primary": ("An online estimate valued a Varsity Lakes house at $1,520,000. The "
                    "agent asked offers over $2,000,000. It sold for $1,895,000.\n\nThe "
                    "estimate was rated “high confidence.” Both the asking price "
                    "and the price a buyer actually paid sat well above it.\n\nWe hold the "
                    "online estimate and the sale price for 31 Varsity Lakes homes sold in "
                    "the last six months. Most were close. Some were not.\n\nSee the sales, "
                    "and what the comparable sales say about a home like yours."),
        "headline": "Asked $2,000,000. Estimated $1,520,000.",
        "desc": "Varsity Lakes sales, last six months. Public record.",
        "note": ("Strongest corroboration in the set — asking price AND sale price both "
                 "above the estimate, so it cannot be blamed on either side. Held back "
                 "because it is a waterfront home with a pontoon, and waterfront is out of "
                 "scope for our valuation method: the ad would attract owners we cannot "
                 "serve."),
    },
]

FORM = {
    "intro_title": "Free seller report — what online estimates get wrong",
    "intro_body": ("The free Fields seller report: how online home estimates miss, and how "
                   "to read the comparable sales that actually set a price. From a licensed "
                   "agent. No pitch."),
    "consent": ("By continuing you agree Fields Real Estate may email, SMS or call you "
                "about our property data — opt out anytime by replying STOP. No spam, "
                "ever."),
    "question": "Are you considering selling in the next 12 months?",
    "options": ["Yes", "Maybe, exploring", "No, just curious"],
    "fields": [("Full name", "Will Simpson"), ("Email", "will@example.com.au"),
               ("Phone number", "0400 000 000")],
    "button": "Get the free report",
    "ty_title": "Thanks — that’s all we need.",
    "ty_body": "Your details are in.",
}


def build():
    os.makedirs(OUT, exist_ok=True)
    for ad in ADS:
        ad["img"] = data_uri(os.path.join(CARDS, ad["file"]))
    payload = json.dumps({"ads": ADS, "form": FORM})

    html = TEMPLATE.replace("/*__DATA__*/", payload)
    path = os.path.join(OUT, "concept_a_review.html")
    open(path, "w").write(html)
    kb = os.path.getsize(path) / 1024
    print(f"  concept_a_review.html  ({kb:.0f} KB)")
    return path


TEMPLATE = r"""<title>Valuation ads — Concept A review</title>
<style>
/* ---------------------------------------------------------------- tokens
   A cool graphite workbench. Deliberately NOT warm: the bone creatives are the
   only warm surface on the page, so colour judgement on them stays accurate.
   Terracotta appears only as annotation. Meta blue is quarantined to feed chrome. */
:root{
  --ground:#eef0f2; --surface:#fff; --sunken:#e3e6e9;
  --line:#d3d8dd; --line-soft:#e4e8eb;
  --ink:#15181c; --body:#3d454d; --muted:#6b747d; --faint:#98a1aa;
  --accent:#b8453a; --accent-soft:#f2ddd9;
  --meta:#1877f2; --meta-ink:#050505; --meta-muted:#65676b;
  --good:#2f7d4f; --good-soft:#dcefe3;
  --warn:#8a5a00; --warn-soft:#f6e8cc;
  --feed:#fff; --feed-chrome:#f0f2f5;
  --shadow:0 1px 2px rgba(16,24,32,.08),0 8px 24px -12px rgba(16,24,32,.18);
}
@media (prefers-color-scheme:dark){
  :root{
    --ground:#101316; --surface:#181c20; --sunken:#0b0e10;
    --line:#282e34; --line-soft:#20262b;
    --ink:#e9edf1; --body:#c0c8cf; --muted:#8b949d; --faint:#69727a;
    --accent:#e0776a; --accent-soft:#3a221e;
    --meta:#2d88ff; --meta-ink:#e4e6eb; --meta-muted:#b0b3b8;
    --good:#6cc48d; --good-soft:#1b2f22;
    --warn:#d6a441; --warn-soft:#302512;
    --feed:#242526; --feed-chrome:#3a3b3c;
    --shadow:0 1px 2px rgba(0,0,0,.4),0 8px 24px -12px rgba(0,0,0,.6);
  }
}
:root[data-theme="dark"]{
  --ground:#101316; --surface:#181c20; --sunken:#0b0e10;
  --line:#282e34; --line-soft:#20262b;
  --ink:#e9edf1; --body:#c0c8cf; --muted:#8b949d; --faint:#69727a;
  --accent:#e0776a; --accent-soft:#3a221e;
  --meta:#2d88ff; --meta-ink:#e4e6eb; --meta-muted:#b0b3b8;
  --good:#6cc48d; --good-soft:#1b2f22;
  --warn:#d6a441; --warn-soft:#302512;
  --feed:#242526; --feed-chrome:#3a3b3c;
  --shadow:0 1px 2px rgba(0,0,0,.4),0 8px 24px -12px rgba(0,0,0,.6);
}
:root[data-theme="light"]{
  --ground:#eef0f2; --surface:#fff; --sunken:#e3e6e9;
  --line:#d3d8dd; --line-soft:#e4e8eb;
  --ink:#15181c; --body:#3d454d; --muted:#6b747d; --faint:#98a1aa;
  --accent:#b8453a; --accent-soft:#f2ddd9;
  --meta:#1877f2; --meta-ink:#050505; --meta-muted:#65676b;
  --good:#2f7d4f; --good-soft:#dcefe3;
  --warn:#8a5a00; --warn-soft:#f6e8cc;
  --feed:#fff; --feed-chrome:#f0f2f5;
  --shadow:0 1px 2px rgba(16,24,32,.08),0 8px 24px -12px rgba(16,24,32,.18);
}

*{box-sizing:border-box}
body{
  margin:0;background:var(--ground);color:var(--body);
  font-family:system-ui,-apple-system,"Segoe UI",Roboto,sans-serif;
  font-size:15px;line-height:1.55;-webkit-font-smoothing:antialiased;
}
h1,h2,h3{color:var(--ink);text-wrap:balance;margin:0}
.wrap{max-width:1180px;margin:0 auto;padding:0 24px 96px}

/* ---------------------------------------------------------------- header */
.top{border-bottom:1px solid var(--line);background:var(--surface);margin-bottom:36px}
.top-in{max-width:1180px;margin:0 auto;padding:26px 24px 22px;
  display:flex;flex-wrap:wrap;gap:20px;align-items:flex-end;justify-content:space-between}
.eyebrow{font-size:11px;letter-spacing:.15em;text-transform:uppercase;
  color:var(--muted);font-weight:650;margin-bottom:7px}
h1{font-family:Georgia,"Times New Roman",serif;font-weight:400;
  font-size:clamp(25px,3.4vw,35px);line-height:1.12;letter-spacing:-.015em}
h1 em{font-style:italic;color:var(--accent)}
.status{display:flex;gap:8px;flex-wrap:wrap;align-items:center}
.pill{font-size:11.5px;font-weight:650;letter-spacing:.04em;padding:5px 11px;
  border-radius:999px;border:1px solid var(--line);color:var(--muted);white-space:nowrap}
.pill.draft{background:var(--warn-soft);color:var(--warn);border-color:transparent}

/* ---------------------------------------------------------------- controls */
.bar{display:flex;flex-wrap:wrap;gap:10px;align-items:center;margin-bottom:30px}
button{font:inherit;cursor:pointer}
.tog{display:inline-flex;background:var(--sunken);border:1px solid var(--line);
  border-radius:9px;padding:3px;gap:3px}
.tog button{border:0;background:none;color:var(--muted);font-size:13px;font-weight:600;
  padding:7px 15px;border-radius:6px;transition:background .15s,color .15s}
.tog button[aria-pressed="true"]{background:var(--surface);color:var(--ink);
  box-shadow:0 1px 2px rgba(0,0,0,.1)}
button:focus-visible{outline:2px solid var(--accent);outline-offset:2px}
.hint{font-size:12.5px;color:var(--faint);margin-left:auto}

/* ---------------------------------------------------------------- section */
section{margin-bottom:64px;scroll-margin-top:20px}
.shead{display:flex;align-items:baseline;gap:14px;flex-wrap:wrap;
  padding-bottom:13px;border-bottom:1px solid var(--line);margin-bottom:26px}
.shead h2{font-family:Georgia,serif;font-weight:400;font-size:23px;letter-spacing:-.01em}
.shead .n{font-size:11px;letter-spacing:.14em;text-transform:uppercase;
  color:var(--faint);font-weight:650;font-variant-numeric:tabular-nums}
.lede{max-width:66ch;color:var(--body);margin:-10px 0 26px}

/* ---------------------------------------------------------------- ad grid */
.grid{display:grid;grid-template-columns:repeat(auto-fit,minmax(330px,1fr));gap:34px}
.unit{display:flex;flex-direction:column;gap:0}
.utop{display:flex;align-items:center;gap:9px;margin-bottom:11px;flex-wrap:wrap}
.utop h3{font-size:15px;font-weight:680;letter-spacing:-.005em}
.tag{font-size:10.5px;font-weight:700;letter-spacing:.08em;text-transform:uppercase;
  padding:3px 8px;border-radius:5px;background:var(--sunken);color:var(--muted)}
.tag.rec{background:var(--good-soft);color:var(--good)}
.tag.hold{background:var(--warn-soft);color:var(--warn)}

/* ---------------------------------------------------------------- feed post */
.post{background:var(--feed);border:1px solid var(--line);border-radius:11px;
  overflow:hidden;box-shadow:var(--shadow)}
.ph{display:flex;align-items:center;gap:9px;padding:12px 13px 9px}
.av{width:40px;height:40px;border-radius:50%;flex:none;
  background:linear-gradient(135deg,#d9645b,#e69084);
  display:flex;align-items:center;justify-content:center;
  color:#fff;font-weight:800;font-size:19px;font-family:Georgia,serif}
.pn{font-size:14px;font-weight:650;color:var(--meta-ink);line-height:1.25}
.pm{font-size:12px;color:var(--meta-muted);display:flex;align-items:center;gap:4px}
.dots{margin-left:auto;color:var(--meta-muted);font-size:19px;letter-spacing:1px;
  align-self:flex-start;padding-top:2px}
.ptext{padding:0 13px 11px;font-size:14.5px;line-height:1.4;color:var(--meta-ink);
  white-space:pre-wrap;word-break:break-word}
.more{color:var(--meta-muted);font-weight:600;cursor:pointer;background:none;border:0;
  padding:0;font-size:14.5px;font-family:inherit}
.more:hover{text-decoration:underline}
.pimg{display:block;width:100%;aspect-ratio:1;object-fit:cover;
  background:var(--sunken);border-block:1px solid var(--line-soft)}
.pfoot{display:flex;align-items:center;gap:12px;padding:11px 13px;
  background:var(--feed-chrome)}
.pfoot .txt{min-width:0;flex:1}
.pfoot .hl{font-size:14.5px;font-weight:680;color:var(--meta-ink);line-height:1.3;
  letter-spacing:-.005em}
.pfoot .ds{font-size:12.5px;color:var(--meta-muted);margin-top:2px}
.cta{flex:none;background:var(--sunken);color:var(--meta-ink);border:0;
  border-radius:6px;padding:9px 13px;font-size:13.5px;font-weight:680;white-space:nowrap}
.pacts{display:flex;border-top:1px solid var(--line-soft);padding:3px 8px}
.pacts span{flex:1;text-align:center;padding:7px 0;font-size:13px;font-weight:620;
  color:var(--meta-muted)}

/* ---------------------------------------------------------------- fold */
.fold{display:block;position:relative;margin:9px 0 3px;height:1px;
  background:repeating-linear-gradient(90deg,var(--accent) 0 6px,transparent 6px 11px);
  opacity:.85}
.fold b{position:absolute;right:0;top:-8px;background:var(--feed);padding-left:7px;
  font-size:9.5px;font-weight:750;letter-spacing:.1em;text-transform:uppercase;
  color:var(--accent)}
.foldnote{font-size:12px;color:var(--accent);padding:0 13px 10px;line-height:1.4}

.note{font-size:13px;color:var(--muted);line-height:1.5;margin-top:12px;
  padding-left:12px;border-left:2px solid var(--line)}

/* ---------------------------------------------------------------- form flow */
.flow{display:grid;grid-template-columns:repeat(auto-fit,minmax(250px,1fr));gap:20px}
.step{background:var(--surface);border:1px solid var(--line);border-radius:11px;
  overflow:hidden;display:flex;flex-direction:column;box-shadow:var(--shadow)}
.slab{font-size:10.5px;letter-spacing:.12em;text-transform:uppercase;font-weight:700;
  color:var(--faint);padding:11px 15px 0}
.sbody{padding:11px 15px 17px;display:flex;flex-direction:column;gap:10px;flex:1}
.sbody h4{margin:0;font-size:15px;font-weight:680;color:var(--ink);line-height:1.3}
.sbody p{margin:0;font-size:13px;color:var(--body);line-height:1.5}
.consent{font-size:11px;color:var(--faint);line-height:1.45}
.opt{border:1px solid var(--line);border-radius:7px;padding:9px 12px;font-size:13.5px;
  color:var(--body);display:flex;align-items:center;gap:9px}
.opt i{width:14px;height:14px;border-radius:50%;border:1.5px solid var(--faint);flex:none}
.opt.sel{border-color:var(--meta);color:var(--ink);font-weight:600}
.opt.sel i{border-color:var(--meta);border-width:4px}
.fld{border:1px solid var(--line);border-radius:7px;padding:8px 12px;background:var(--sunken)}
.fld .k{font-size:10.5px;color:var(--faint);letter-spacing:.05em;text-transform:uppercase;
  font-weight:650}
.fld .v{font-size:13.5px;color:var(--faint);margin-top:1px}
.sbtn{background:var(--meta);color:#fff;border:0;border-radius:7px;padding:10px;
  font-size:14px;font-weight:680;text-align:center;margin-top:auto}
.tick{width:38px;height:38px;border-radius:50%;background:var(--good-soft);color:var(--good);
  display:flex;align-items:center;justify-content:center;font-size:20px;font-weight:800}

/* ---------------------------------------------------------------- callouts */
.cols{display:grid;grid-template-columns:repeat(auto-fit,minmax(290px,1fr));gap:18px}
.card{background:var(--surface);border:1px solid var(--line);border-radius:11px;
  padding:19px 21px;box-shadow:var(--shadow)}
.card h3{font-size:14px;font-weight:700;margin-bottom:11px;letter-spacing:-.005em;
  display:flex;align-items:center;gap:8px}
.card ul{margin:0;padding-left:17px;display:flex;flex-direction:column;gap:8px}
.card li{font-size:13.5px;line-height:1.5}
.card li b{color:var(--ink);font-weight:660}
.dot{width:7px;height:7px;border-radius:50%;flex:none}
.dot.r{background:var(--accent)} .dot.g{background:var(--good)} .dot.w{background:var(--warn)}
code{font-family:ui-monospace,SFMono-Regular,Menlo,monospace;font-size:12.5px;
  background:var(--sunken);padding:1px 5px;border-radius:4px;color:var(--ink)}

.foot{border-top:1px solid var(--line);padding-top:20px;font-size:12.5px;color:var(--faint);
  display:flex;flex-wrap:wrap;gap:6px 18px}

@media (max-width:640px){
  .wrap{padding:0 16px 64px} .top-in{padding:20px 16px 18px}
  .hint{margin-left:0;width:100%}
}
@media (prefers-reduced-motion:reduce){*{transition:none!important;animation:none!important}}
</style>

<header class="top">
  <div class="top-in">
    <div>
      <div class="eyebrow">Facebook · Valuation category · Concept A</div>
      <h1>What the estimate said,<br>and what the house <em>actually sold for</em></h1>
    </div>
    <div class="status">
      <span class="pill draft">Draft — not approved</span>
      <span class="pill">No spend authorised</span>
    </div>
  </div>
</header>

<div class="wrap">

  <div class="bar">
    <div class="tog" role="group" aria-label="Primary text display">
      <button id="bFold" aria-pressed="true">As posted</button>
      <button id="bFull" aria-pressed="false">Expanded</button>
    </div>
    <div class="tog" role="group" aria-label="Which ads to show">
      <button id="bAll" aria-pressed="true">All four</button>
      <button id="bRec" aria-pressed="false">Recommended only</button>
    </div>
    <span class="hint">Cards are the real 1080×1080 render output — the same files that
      would upload to Meta.</span>
  </div>

  <section>
    <div class="shead">
      <span class="n">01</span>
      <h2>In the feed</h2>
    </div>
    <p class="lede">Facebook truncates primary text at roughly 125 characters on mobile.
      The dashed rule marks where the fold lands — most people never tap “See more”, so
      whatever sits above it is the whole ad for most of the audience.</p>
    <div class="grid" id="grid"></div>
  </section>

  <section>
    <div class="shead">
      <span class="n">02</span>
      <h2>The instant form it opens</h2>
    </div>
    <p class="lede">This is the form that produced <b>all seven leads</b> of the last test
      (<code>2116153228999527</code>) — reproduced exactly, including the question order.
      Selling intent is asked <em>first</em>, and there is no address field: an address
      killed two earlier variants outright.</p>
    <div class="flow" id="flow"></div>
  </section>

  <section>
    <div class="shead">
      <span class="n">03</span>
      <h2>Before this can run</h2>
    </div>
    <div class="cols">
      <div class="card">
        <h3><span class="dot g"></span>Settled</h3>
        <ul>
          <li><b>Every sale price verified</b> against primary listing pages — Domain’s
            own sold record and, for Brier Crescent, the selling agency’s.</li>
          <li><b>Estimates predate the sales.</b> All 29 candidate rows checked; the
            November snapshot is the one honest slice of that field.</li>
          <li><b>Only rows outside the estimate’s own range</b> are published — if a sale
            lands inside it, the claim is refutable on their own numbers.</li>
          <li><b>No portal is named</b>, no person is judged, no advice is given.</li>
        </ul>
      </div>
      <div class="card">
        <h3><span class="dot w"></span>Open questions</h3>
        <ul>
          <li><b>A1 or A2?</b> The stronger claim, or the bigger number. Cheap to settle
            by running both.</li>
          <li><b>Varsity now, or Robina first?</b> Adds a third ad set.</li>
          <li><b>Is the $2,020,000 sale a problem?</b> It sits $20,000 outside the band
            our valuation method can answer in.</li>
        </ul>
      </div>
      <div class="card">
        <h3><span class="dot r"></span>Blockers</h3>
        <ul>
          <li><b>No follow-up loop.</b> A$1,743 spent → 21 leads → 6 contacted → 0 booked
            calls. This ad promises a real valuation by a real person.</li>
          <li><b>Facebook clicks arrive unattributable</b> — <code>fbclid</code> is
            stripped before the page’s JavaScript loads. Blocks the landing page, not the
            instant form.</li>
          <li><b>Geo-block shows Meta’s reviewers a block page</b>, risking disapproval on
            any ad pointing at the site.</li>
        </ul>
      </div>
    </div>
  </section>

  <div class="foot">
    <span>33 Geraldton Drive · 39 Brier Crescent · 20 Vanderbilt Court — all public record</span>
    <span>Online estimates as published November 2025</span>
    <span>Evidence: 00_EVIDENCE_BASE.md · Build: 02_CONCEPT_A_BUILD.md</span>
  </div>
</div>

<script>
const DATA = /*__DATA__*/;
const FOLD_AT = 125;              // Meta's mobile truncation, approximate
let showFold = true, recOnly = false;

function esc(s){return s.replace(/[&<>]/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;'}[c]))}

function renderAds(){
  const g = document.getElementById('grid');
  g.innerHTML = '';
  DATA.ads.filter(a => !recOnly || a.recommended).forEach(ad => {
    // Real truncation, computed — not a hand-placed guess.
    const flat = ad.primary.replace(/\n+/g,' ');
    const cut  = flat.length > FOLD_AT;
    // Facebook breaks at a word boundary, not mid-word — walk back to the last space.
    let head = flat;
    if (cut) {
      const raw = flat.slice(0, FOLD_AT);
      head = raw.slice(0, raw.lastIndexOf(' ')).replace(/[,—–-]$/,'').trim();
    }

    const body = showFold
      ? `${esc(head)}<span class="fold"><b>fold</b></span>… <button class="more"
           data-x="1">See more</button>`
      : esc(ad.primary);

    const lastWord = head.trim().split(/\s+/).slice(-4).join(' ');
    const foldNote = (showFold && cut)
      ? `<div class="foldnote">Most people read to here: “…${esc(lastWord)}”</div>` : '';

    const tag = ad.recommended
      ? '<span class="tag rec">Recommended</span>'
      : (ad.id === 'A4' ? '<span class="tag hold">Held back</span>' : '');

    const el = document.createElement('div');
    el.className = 'unit';
    el.innerHTML = `
      <div class="utop">
        <h3>${esc(ad.name)}</h3>${tag}
        <span class="tag">${esc(ad.set)}</span>
      </div>
      <div class="post">
        <div class="ph">
          <div class="av">F</div>
          <div>
            <div class="pn">Fields Real Estate</div>
            <div class="pm">Sponsored ·
              <svg width="12" height="12" viewBox="0 0 16 16" fill="none"
                   stroke="currentColor" stroke-width="1.2" aria-hidden="true">
                <circle cx="8" cy="8" r="6.4"/><ellipse cx="8" cy="8" rx="2.7" ry="6.4"/>
                <path d="M1.9 5.8h12.2M1.9 10.2h12.2"/>
              </svg>
            </div>
          </div>
          <div class="dots" aria-hidden="true">···</div>
        </div>
        <div class="ptext">${body}</div>
        ${foldNote}
        <img class="pimg" src="${ad.img}" alt="Ad creative ${esc(ad.id)}: ${esc(ad.headline)}">
        <div class="pfoot">
          <div class="txt">
            <div class="hl">${esc(ad.headline)}</div>
            <div class="ds">${esc(ad.desc)}</div>
          </div>
          <span class="cta">Learn more</span>
        </div>
        <div class="pacts"><span>Like</span><span>Comment</span><span>Share</span></div>
      </div>
      <div class="note">${esc(ad.note)}</div>`;

    const btn = el.querySelector('.more');
    if (btn) btn.addEventListener('click', e => {
      e.target.closest('.ptext').innerHTML = esc(ad.primary);
    });
    g.appendChild(el);
  });
}

function renderForm(){
  const f = DATA.form;
  document.getElementById('flow').innerHTML = `
    <div class="step">
      <div class="slab">1 · Intro card</div>
      <div class="sbody">
        <h4>${esc(f.intro_title)}</h4>
        <p>${esc(f.intro_body)}</p>
        <p class="consent">${esc(f.consent)}</p>
        <div class="sbtn">Continue</div>
      </div>
    </div>
    <div class="step">
      <div class="slab">2 · Qualifier</div>
      <div class="sbody">
        <h4>${esc(f.question)}</h4>
        ${f.options.map((o,i)=>`<div class="opt${i===0?' sel':''}"><i></i>${esc(o)}</div>`).join('')}
        <div class="sbtn">Continue</div>
      </div>
    </div>
    <div class="step">
      <div class="slab">3 · Contact — prefilled by Facebook</div>
      <div class="sbody">
        ${f.fields.map(([k,v])=>`<div class="fld"><div class="k">${esc(k)}</div>
          <div class="v">${esc(v)}</div></div>`).join('')}
        <div class="sbtn">${esc(f.button)}</div>
      </div>
    </div>
    <div class="step">
      <div class="slab">4 · Thank you</div>
      <div class="sbody">
        <div class="tick" aria-hidden="true">✓</div>
        <h4>${esc(f.ty_title)}</h4>
        <p>${esc(f.ty_body)}</p>
        <p class="consent">The out-of-market test ended here deliberately. A live Gold
          Coast form needs a real next step — and a person behind it.</p>
      </div>
    </div>`;
}

function wire(a, b, set){
  a.addEventListener('click', ()=>{ set(true);
    a.setAttribute('aria-pressed','true'); b.setAttribute('aria-pressed','false'); renderAds(); });
  b.addEventListener('click', ()=>{ set(false);
    b.setAttribute('aria-pressed','true'); a.setAttribute('aria-pressed','false'); renderAds(); });
}
wire(document.getElementById('bFold'), document.getElementById('bFull'), v=>showFold=v);
wire(document.getElementById('bRec'), document.getElementById('bAll'), v=>recOnly=v);

renderAds();
renderForm();
</script>
"""

if __name__ == "__main__":
    build()
