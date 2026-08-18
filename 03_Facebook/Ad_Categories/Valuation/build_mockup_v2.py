#!/usr/bin/env python3
"""
build_mockup_v2.py — the SPEC-CALIBRATED proposal, built as a separate artifact so it
can be compared side by side with V1 (mockup/concept_a_review.html, artifact
0e7ef5f8-1e0c-4787-9b7b-9235500966e9). V1 is deliberately left untouched.

What changed and why is in 03_PLAN_CALIBRATION.md v2. In short, the Cold-Meta Entry
specs (docs 00-04, 2026-08-17) hold the AD constant and vary the ENTRY, so V2 is not
four competing creatives — it is one ad per territory and the three entry
architectures behind it.

Run: source /home/fields/venv/bin/activate && python3 build_mockup_v2.py
Out: mockup/concept_v2_review.html
"""
import base64, io, json, os
from PIL import Image

ROOT = os.path.dirname(os.path.abspath(__file__))
CARDS = os.path.join(ROOT, "creatives_valuation")
OUT = os.path.join(ROOT, "mockup")
EMBED_W = 760


def data_uri(path):
    im = Image.open(path).convert("RGB").resize((EMBED_W, EMBED_W), Image.LANCZOS)
    buf = io.BytesIO()
    im.save(buf, format="JPEG", quality=88, optimize=True)
    return "data:image/jpeg;base64," + base64.b64encode(buf.getvalue()).decode()


# ------------------------------------------------------------------ the two ads
ADS = [
    {
        "id": "C1",
        "file": "C1_competitive_set.png",
        "territory": "Competition",
        "rank": "Release 1 — this is what actually launches first",
        "rank_kind": "now",
        "primary": (
            "The home buyers compare yours with may not be the one you think.\n\n"
            "Buyers don’t weigh a home against every property in the suburb. They "
            "weigh it against the alternatives they could realistically choose "
            "instead — which is often not the nearest sale, and not the one with the "
            "same bedroom count.\n\n"
            "See the homes we’d actually put in the competitive set for a property."),
        "headline": "See the competition for a property",
        "desc": "No phone number or email required.",
        "cta": "Learn more",
        "why": (
            "Doc 03: “<em>Begin with Competition.</em>” Doc 04’s build order runs 19 "
            "items and Value Evidence is number 18 — the territories after Competition "
            "are “<em>configuration and content extensions rather than separate "
            "one-off landing pages.</em>” So this is the ad the first experiment "
            "actually needs."),
        "note": (
            "Makes no quantified claim, on purpose. A published competitor count is "
            "currently unsafe — <code>closest_active</code> caps at 6, and doc 00 lists "
            "“<em>never use a display-limited array as the source of a published ‘we "
            "found X homes’ count</em>” as a non-negotiable guardrail."),
    },
    {
        "id": "VE1",
        "file": "P1_range_not_number.png",
        "territory": "Value Evidence",
        "rank": "Build item 18 of 19 — the ad you asked for, banked",
        "rank_kind": "later",
        "primary": (
            "Any three recent sales can be used to value a home. Pick a different "
            "three, and the answer moves.\n\n"
            "We tested every possible trio across 313 recent house sales in Robina, "
            "Varsity Lakes and Burleigh Waters. At the median, the gap between the "
            "best-case and worst-case trio was $227,500.\n\n"
            "That is why your home isn’t worth a number. It’s worth a range — and "
            "there should be evidence behind it.\n\n"
            "See which sales actually matter for a property."),
        "headline": "See the evidence behind the range",
        "desc": "No phone number or email required.",
        "cta": "Learn more",
        "why": (
            "Doc 00 asks proof to “<em>demonstrate reasoning, not merely output</em>” "
            "and to prove the product rather than the brand. This is the only creative "
            "we hold that teaches the Fields method instead of pointing at a "
            "competitor’s mistake — so it can serve as both the held-constant ad and "
            "the seed of the Value Evidence proof module."),
        "note": (
            "The fold now lands on a complete thought (96 characters), which was the "
            "defect in V1’s lead creative. $227,500 is the strict-pool median — the "
            "only figure that survives a hostile screen. See "
            "<code>00_EVIDENCE_BASE.md</code> §4 and its warning about $469,000."),
    },
]

# ------------------------------------------------- the three entry architectures
ARMS = [
    {
        "id": "A",
        "name": "Direct property resolution",
        "role": "Control",
        "role_kind": "control",
        "gist": "Ad → matching headline → property search → the promised result.",
        "spec": ("“<em>This should remain the control. Do not remove it because a "
                 "proof-first route feels intuitively better.</em>”"),
        "screen": [
            ("h", "Which homes would buyers actually compare this property with?"),
            ("p", "Buyers do not evaluate a home against every property in the suburb. "
                  "They weigh it against the alternatives they could realistically "
                  "choose instead."),
            ("p", "Choose a property and we’ll narrow the surrounding market to the "
                  "homes we think a similar buyer would most genuinely weigh against it."),
            ("field", "Which property should we analyse?"),
            ("cta", "See the competition"),
            ("re", "No phone number or email is required to view the analysis."),
        ],
        "risk": ("The visitor has almost no evidence Fields can deliver the analysis "
                 "before being asked for a sensitive property identifier."),
    },
    {
        "id": "B",
        "name": "Micro-proof bridge",
        "role": "Lead hypothesis",
        "role_kind": "lead",
        "gist": "Ad → headline → one compact real demonstration → property search → result.",
        "spec": ("“<em>The address request arrives after Fields has demonstrated that a "
                 "specific computational product exists.</em>”"),
        "screen": [
            ("h", "Which homes would buyers actually compare this property with?"),
            ("p", "Same suburb and similar price does not automatically mean the same "
                  "buyer. We narrow the market using the things that change the choice "
                  "a buyer is actually making."),
            ("eyebrow", "Example — how the comparison changes"),
            ("card", ("Looks comparable", "Nearby. Similar asking range.",
                      "Same bedroom count and broad price position.")),
            ("card", ("Stronger competitor",
                      "Further away, but closer in layout, land and likely buyer.",
                      "The same buyer could realistically choose this instead.")),
            ("card", ("Weaker competitor", "Very close and recently sold.",
                      "Different property type or buyer problem being solved.")),
            ("p", "That is the analysis we run around individual properties."),
            ("field", "Search an address…"),
            ("cta", "See the competition"),
            ("re", "No phone number or email is required to view the analysis."),
        ],
        "risk": ("Too much proof could partially satisfy the curiosity and reduce "
                 "address entry. That is precisely what Experiment 1 measures."),
    },
    {
        "id": "C",
        "name": "Full example property",
        "role": "Challenger",
        "role_kind": "challenger",
        "gist": ("Ad → a labelled real example the visitor can explore → contextual CTA "
                 "→ property search → their property opens on the same section."),
        "spec": ("“<em>Example analysis — local property.</em>” / “<em>Address withheld "
                 "for this example.</em>” Never let it look like a live private account."),
        "screen": [
            ("h", "Here is how Fields identifies the homes a buyer would genuinely compare."),
            ("label", "Example analysis — local property · Address withheld for this example"),
            ("card", ("Included", "Similar land, layout, condition and likely buyer.",
                      "Why this one? →")),
            ("card", ("Lower relevance", "Similar price position, different site.",
                      "Why this one? →")),
            ("card", ("Excluded", "Closest sale. Materially different buying decision.",
                      "Why this one? →")),
            ("p", "Want to see the competitive set for another property?"),
            ("field", "Search a property…"),
            ("cta", "See the competition"),
        ],
        "risk": ("The example can become the destination rather than the bridge. Doc 02 "
                 "names this the “satisfaction risk” and bans blurring the example "
                 "behind a search gate to manage it."),
    },
]

# --------------------------------------------------------- what the click leads to
JOURNEY = [
    ("Property resolution",
     "Not conversion. “<em>Address entry is not conversion. It is property "
     "resolution.</em>” One unambiguous autocomplete hit proceeds straight through — no "
     "confirmation step added merely to establish ownership.",
     ["Never “Is this your home?” — only “Is this the property you meant?”",
      "No name, phone, email or ownership question at this stage",
      "A property search is not a seller-intent event, and that must survive into the CRM"]),
    ("The promised answer, ungated",
     "The clicked promise is the first meaningful paint. Competition opens on "
     "Competition. A flash of the default valuation tab before routing counts as a "
     "<code>promise_integrity_failure</code> even if the final tab is right.",
     ["Property context → promise headline → the set → reasons and differences → "
      "coverage and confidence",
      "“<em>Valuation does not dominate the first result.</em>”",
      "Consumable end to end with no identity"]),
    ("One adjacent insight",
     "A single continuous next gap, not a generic “learn more” card and not "
     "manufactured urgency.",
     ["“You’ve seen what buyers could choose instead. The next question is where this "
      "property appears stronger, weaker or simply different.”",
      "CTA: See where this property stands"]),
    ("Contextual router",
     "Only after value has landed. Never a seller-intent interrogation, and “just "
     "curious” is a complete, legitimate end state.",
     ["Could we move from here?", "Would improving something change the position?",
      "Would waiting change the competition?", "Just keep tracking this property"]),
    ("Continuity — identity buys a job",
     "The job is chosen <em>before</em> contact details are requested, and permission is "
     "scoped to that job alone.",
     ["“Tell me when another genuinely comparable home sells.”",
      "“Tell me when a new property starts competing directly with this one.”",
      "“Let me know when new evidence materially changes this range.”",
      "Selecting a job does not grant unrelated call permission"]),
]

BARRED = [
    ("The instant lead form", "form <code>2116153228999527</code> — name, email, phone",
     "“<em>Never require phone or email to reveal the clicked answer.</em>”"),
    ("The seller-intent qualifier",
     "“Are you considering selling in the next 12 months?”",
     "“<em>Never infer seller intent from a property search alone.</em>” Campaign 1 is "
     "“<em>not primarily a seller-intent campaign</em>.”"),
    ("A/B of four creatives", "A1 vs A2 vs A3 vs A4 running together",
     "“<em>Hold constant: Meta ad… Vary only: pre-address proof depth.</em>”"),
    ("The two-landing-page test", "two pages, same form",
     "“<em>Use sequential evidence accumulation rather than a large matrix of "
     "simultaneous A/B variants at current traffic volumes.</em>”"),
    ("Booking a real valuation", "“a real valuation done by a real person”",
     "“<em>The appraisal should emerge as an information requirement.</em>” "
     "“<em>If Will immediately tries to book an appraisal, the handoff was probably "
     "premature.</em>”"),
]

BLOCKERS = [
    ("blocker", "Competitor count reads a display-capped array",
     "<code>closest_active</code> caps at 6; the canonical source is "
     "<code>funnel.close_tier</code>. Named as a guardrail in doc 00, a data rule in "
     "doc 02 and an acceptance criterion in doc 04 E6 — and Release 1 <em>is</em> "
     "Competition, whose proof module and first result both publish that count. "
     "Diagnosed, not fixed: it is a production write awaiting a go-ahead."),
    ("blocker", "No mapping from spec to our stack",
     "Across all five documents there is no file path, route, Netlify function, Mongo "
     "field, or mention of PostHog. Nobody has bound <code>CampaignEntryDefinition</code> "
     "to the mini-site or the 17 launch-blocking events to our analytics. Until that "
     "exists, “launch-ready” cannot be assessed at all."),
    ("blocker", "17 launch-blocking events, none of them firing",
     "<code>campaign_entry_viewed · proof_viewed · property_search_started · "
     "property_selected · promise_generation_succeeded · promise_generation_failed · "
     "promise_result_viewed · promise_result_consumed · adjacent_insight_viewed · "
     "router_viewed · router_choice_selected · continuity_action_selected · "
     "identity_requested · permission_granted · continuity_created · "
     "second_interaction · promise_integrity_failure</code>"),
    ("open", "Was “Territory A / Static Ad A1” deliberate?",
     "That naming exists only in the older strategy doc. If the intent is to run Value "
     "Evidence ahead of Competition regardless, that is a conscious override of "
     "“begin with Competition” — worth making on purpose rather than by accident."),
    ("open", "No numbers anywhere in the specs",
     "No budget, no sample size, no significance threshold, no runtime, no kill rule. "
     "Doc 03’s only stopping language is “directionally stable across enough traffic.” "
     "Someone has to decide what a first test costs and when it ends."),
    ("open", "Is there a person to answer leads?",
     "Less urgent under these specs — the ad no longer produces leads — but it fully "
     "gates “Ask Will”, which is the end of the journey above."),
]

CSS = """
:root{
  --bg:#f6f5f2; --panel:#fffefc; --edge:#ddd9d1; --edge2:#eae7e0;
  --ink:#1b1f21; --ink2:#4d5457; --ink3:#7d8487;
  --accent:#2f6f6a; --accent-soft:#e6efed; --on-accent:#ffffff;
  --warn:#a8442f; --warn-soft:#f7e9e5;
  --ok:#3d6b45; --ok-soft:#e8f0e9;
  --mono:ui-monospace,SFMono-Regular,Menlo,Consolas,monospace;
}
@media (prefers-color-scheme:dark){:root{
  --bg:#131618; --panel:#1b1f22; --edge:#2e3438; --edge2:#252b2e;
  --ink:#eef0f0; --ink2:#a8b1b4; --ink3:#7b8488;
  --accent:#6fbdb4; --accent-soft:#1d2d2c; --on-accent:#0f1618;
  --warn:#e08a72; --warn-soft:#2e211d;
  --ok:#8bc196; --ok-soft:#1e2a20;
}}
:root[data-theme="dark"]{
  --bg:#131618; --panel:#1b1f22; --edge:#2e3438; --edge2:#252b2e;
  --ink:#eef0f0; --ink2:#a8b1b4; --ink3:#7b8488;
  --accent:#6fbdb4; --accent-soft:#1d2d2c; --on-accent:#0f1618;
  --warn:#e08a72; --warn-soft:#2e211d;
  --ok:#8bc196; --ok-soft:#1e2a20;
}
:root[data-theme="light"]{
  --bg:#f6f5f2; --panel:#fffefc; --edge:#ddd9d1; --edge2:#eae7e0;
  --ink:#1b1f21; --ink2:#4d5457; --ink3:#7d8487;
  --accent:#2f6f6a; --accent-soft:#e6efed; --on-accent:#ffffff;
  --warn:#a8442f; --warn-soft:#f7e9e5;
  --ok:#3d6b45; --ok-soft:#e8f0e9;
}
*{box-sizing:border-box}
body{margin:0;background:var(--bg);color:var(--ink);
  font:16px/1.6 system-ui,-apple-system,'Segoe UI',Roboto,sans-serif;
  -webkit-font-smoothing:antialiased}
.wrap{max-width:1180px;margin:0 auto;padding:0 24px 120px}
code{font-family:var(--mono);font-size:.86em;background:var(--edge2);
  padding:.12em .38em;border-radius:4px;color:var(--ink2)}
em{font-family:Georgia,'Times New Roman',serif;font-style:italic}

/* ---- masthead ---- */
header{padding:72px 0 36px;border-bottom:1px solid var(--edge)}
.vtag{display:inline-block;font:600 12px/1 var(--mono);letter-spacing:.14em;
  text-transform:uppercase;color:var(--accent);background:var(--accent-soft);
  border:1px solid var(--accent);border-radius:100px;padding:7px 13px;margin-bottom:20px}
h1{font-size:clamp(30px,4.6vw,50px);line-height:1.06;margin:0 0 16px;
  letter-spacing:-.028em;font-weight:800;text-wrap:balance;max-width:19ch}
.lede{font-size:18px;color:var(--ink2);max-width:66ch;margin:0}
.lede b{color:var(--ink);font-weight:650}
.cmp{margin-top:26px;padding:15px 18px;border:1px solid var(--edge);
  border-left:3px solid var(--accent);border-radius:0 8px 8px 0;background:var(--panel);
  font-size:14.5px;color:var(--ink2);max-width:74ch}

/* ---- section scaffold ---- */
section{padding-top:68px}
.sh{display:flex;align-items:baseline;gap:14px;margin-bottom:8px}
.sn{font:700 12px/1 var(--mono);letter-spacing:.12em;color:var(--accent)}
h2{font-size:clamp(21px,2.6vw,28px);margin:0;letter-spacing:-.02em;font-weight:750}
.sd{color:var(--ink2);max-width:70ch;margin:0 0 30px;font-size:15.5px}

/* ---- feed ---- */
.feed{display:grid;grid-template-columns:repeat(auto-fit,minmax(330px,1fr));gap:34px}
.slot{min-width:0}
.rank{display:inline-flex;align-items:center;gap:8px;font:600 11.5px/1 var(--mono);
  letter-spacing:.08em;text-transform:uppercase;padding:6px 11px;border-radius:100px;
  margin-bottom:12px}
.rank.now{color:var(--ok);background:var(--ok-soft);border:1px solid var(--ok)}
.rank.later{color:var(--ink3);background:var(--edge2);border:1px solid var(--edge)}
.terr{font-size:20px;font-weight:750;letter-spacing:-.015em;margin:0 0 14px}
.fb{background:var(--panel);border:1px solid var(--edge);border-radius:12px;
  overflow:hidden}
.fbtop{display:flex;align-items:center;gap:10px;padding:12px 13px 9px}
.av{width:38px;height:38px;border-radius:50%;flex:0 0 38px;
  background:linear-gradient(135deg,#d9645b,#e69084)}
.fbn{font-size:13.5px;font-weight:650;line-height:1.25}
.fbm{font-size:11.5px;color:var(--ink3);display:flex;align-items:center;gap:5px}
.fbm svg{width:11px;height:11px;fill:currentColor}
.fbtxt{padding:2px 13px 11px;font-size:14px;line-height:1.45;white-space:pre-wrap}
.more{color:var(--ink3);cursor:pointer}
.fold{display:flex;align-items:center;gap:9px;padding:0 13px 9px;
  font:600 9.5px/1 var(--mono);letter-spacing:.11em;text-transform:uppercase;
  color:var(--warn)}
.fold:before,.fold:after{content:"";height:1px;background:var(--warn);opacity:.4;flex:1}
.fbimg{display:block;width:100%;border-top:1px solid var(--edge2);
  border-bottom:1px solid var(--edge2)}
.fbfoot{display:flex;align-items:center;gap:12px;padding:11px 13px;background:var(--edge2)}
.fbfl{flex:1;min-width:0}
.fbfd{font-size:11px;color:var(--ink3);text-transform:uppercase;letter-spacing:.05em}
.fbfh{font-size:13.5px;font-weight:650;line-height:1.3;margin-top:2px}
.fbb{flex:0 0 auto;font-size:12.5px;font-weight:650;padding:8px 13px;border-radius:6px;
  background:var(--edge);color:var(--ink2)}
.ann{margin-top:14px;font-size:13.5px;color:var(--ink2);line-height:1.55}
.ann + .ann{margin-top:9px;padding-top:11px;border-top:1px dashed var(--edge)}
.ann b{color:var(--ink);font-weight:650}

/* ---- arms ---- */
.arms{display:grid;grid-template-columns:repeat(auto-fit,minmax(300px,1fr));gap:22px}
.arm{background:var(--panel);border:1px solid var(--edge);border-radius:12px;
  padding:20px;display:flex;flex-direction:column;gap:13px}
.arm.lead{border-color:var(--accent);box-shadow:0 0 0 1px var(--accent)}
.armh{display:flex;align-items:baseline;gap:10px;flex-wrap:wrap}
.armid{font:700 12px/1 var(--mono);color:var(--ink3)}
.armn{font-size:17px;font-weight:700;letter-spacing:-.012em}
.pill{font:600 10.5px/1 var(--mono);letter-spacing:.08em;text-transform:uppercase;
  padding:5px 9px;border-radius:100px}
.pill.control{color:var(--ink3);background:var(--edge2);border:1px solid var(--edge)}
.pill.lead{color:var(--accent);background:var(--accent-soft);border:1px solid var(--accent)}
.pill.challenger{color:var(--warn);background:var(--warn-soft);border:1px solid var(--warn)}
.gist{font-size:13.5px;color:var(--ink2)}
.mock{background:var(--bg);border:1px solid var(--edge);border-radius:9px;padding:16px;
  display:flex;flex-direction:column;gap:10px}
.mh{font-size:16px;font-weight:700;line-height:1.25;letter-spacing:-.012em}
.mp{font-size:12.5px;color:var(--ink2);line-height:1.5}
.meye{font:600 10px/1 var(--mono);letter-spacing:.11em;text-transform:uppercase;
  color:var(--ink3)}
.mlab{font:600 10px/1.4 var(--mono);letter-spacing:.06em;color:var(--accent);
  background:var(--accent-soft);border:1px dashed var(--accent);border-radius:5px;
  padding:7px 9px}
.mcard{border:1px solid var(--edge);border-radius:7px;padding:10px 11px;background:var(--panel)}
.mct{font-size:12px;font-weight:700;margin-bottom:3px}
.mcb{font-size:11.5px;color:var(--ink2);line-height:1.45}
.mcw{font-size:11px;color:var(--ink3);margin-top:4px;font-style:italic}
.mfield{border:1px solid var(--edge);border-radius:7px;padding:11px 12px;
  background:var(--panel);font-size:12.5px;color:var(--ink3)}
/* the CTA sits on the accent, which inverts between themes — carry its own token
   rather than hard-coding white, or the dark accent renders white-on-mint */
.mcta{background:var(--accent);color:var(--on-accent);text-align:center;
  border-radius:7px;padding:11px;font-size:13px;font-weight:700}
.mre{font-size:11px;color:var(--ink3);text-align:center}
.risk{font-size:12.5px;color:var(--ink2);padding-top:12px;border-top:1px dashed var(--edge)}
.risk b{color:var(--ink);font-weight:650}
.specq{font-size:12.5px;color:var(--ink2);border-left:2px solid var(--accent);
  padding-left:11px}

/* ---- journey ---- */
.jr{display:flex;flex-direction:column}
.jstep{display:grid;grid-template-columns:52px 1fr;gap:20px;padding-bottom:30px;
  position:relative}
.jstep:not(:last-child):before{content:"";position:absolute;left:25px;top:44px;bottom:0;
  width:1px;background:var(--edge)}
.jnum{width:50px;height:50px;border-radius:50%;border:1px solid var(--edge);
  background:var(--panel);display:flex;align-items:center;justify-content:center;
  font:700 15px/1 var(--mono);color:var(--accent);position:relative;z-index:1}
.jbody{padding-top:5px;min-width:0}
.jt{font-size:17.5px;font-weight:700;letter-spacing:-.015em;margin-bottom:6px}
.jd{font-size:14px;color:var(--ink2);max-width:70ch;margin-bottom:11px}
.jl{list-style:none;margin:0;padding:0;display:flex;flex-direction:column;gap:7px}
.jl li{font-size:13.5px;color:var(--ink2);padding-left:18px;position:relative;line-height:1.5}
.jl li:before{content:"";position:absolute;left:0;top:.62em;width:6px;height:6px;
  border-radius:50%;background:var(--accent);opacity:.55}

/* ---- barred ---- */
.barred{display:grid;grid-template-columns:repeat(auto-fit,minmax(300px,1fr));gap:16px}
.bx{background:var(--panel);border:1px solid var(--edge);border-left:3px solid var(--warn);
  border-radius:0 10px 10px 0;padding:16px 18px}
.bt{font-size:15px;font-weight:700;margin-bottom:5px}
.bwas{font-size:12.5px;color:var(--ink3);text-decoration:line-through;
  text-decoration-color:var(--warn);margin-bottom:9px}
.bwhy{font-size:13px;color:var(--ink2);line-height:1.55}

/* ---- blockers ---- */
.bl{display:flex;flex-direction:column;gap:14px}
.br{display:grid;grid-template-columns:auto 1fr;gap:16px;align-items:start;
  background:var(--panel);border:1px solid var(--edge);border-radius:10px;padding:16px 18px}
.bc{font:600 10.5px/1 var(--mono);letter-spacing:.09em;text-transform:uppercase;
  padding:6px 10px;border-radius:100px;white-space:nowrap;margin-top:2px}
.bc.blocker{color:var(--warn);background:var(--warn-soft);border:1px solid var(--warn)}
.bc.open{color:var(--ink3);background:var(--edge2);border:1px solid var(--edge)}
.brt{font-size:15.5px;font-weight:700;margin-bottom:5px;letter-spacing:-.012em}
.brd{font-size:13.5px;color:var(--ink2);line-height:1.6}

footer{margin-top:80px;padding-top:26px;border-top:1px solid var(--edge);
  font-size:13px;color:var(--ink3);display:flex;justify-content:space-between;
  gap:18px;flex-wrap:wrap}
@media(max-width:640px){
  .jstep{grid-template-columns:38px 1fr;gap:14px}
  .jnum{width:36px;height:36px;font-size:12px}
  .jstep:not(:last-child):before{left:18px;top:40px}
}
"""

GLOBE = ('<svg viewBox="0 0 16 16"><path d="M8 1a7 7 0 100 14A7 7 0 008 1zm0 1.5c.9 0 '
         '1.9 1.6 2.2 3.9H5.8C6.1 4.1 7.1 2.5 8 2.5zM5.6 6.9h4.8a13 13 0 010 2.2H5.6a13 '
         '13 0 010-2.2zm.2 3.7h4.4C9.9 12.9 8.9 14.5 8 14.5s-1.9-1.6-2.2-3.9zm6-3.7h2.2a5.5 '
         '5.5 0 010 2.2h-2.2a14 14 0 000-2.2zm-.3-1.5a8.6 8.6 0 00-1-2.7 5.5 5.5 0 012.6 '
         '2.7h-1.6zm-7 0H2.9a5.5 5.5 0 012.6-2.7 8.6 8.6 0 00-1 2.7zM2.4 6.9h2.2a14 14 0 '
         '000 2.2H2.4a5.5 5.5 0 010-2.2zm.5 3.7h1.6a8.6 8.6 0 001 2.7 5.5 5.5 0 01-2.6-2.7zm'
         '8.2 2.7a8.6 8.6 0 001-2.7h1.6a5.5 5.5 0 01-2.6 2.7z"/></svg>')


def screen_html(rows):
    out = []
    for kind, val in rows:
        if kind == "h":
            out.append(f'<div class="mh">{val}</div>')
        elif kind == "p":
            out.append(f'<div class="mp">{val}</div>')
        elif kind == "eyebrow":
            out.append(f'<div class="meye">{val}</div>')
        elif kind == "label":
            out.append(f'<div class="mlab">{val}</div>')
        elif kind == "card":
            t, b, w = val
            out.append(f'<div class="mcard"><div class="mct">{t}</div>'
                       f'<div class="mcb">{b}</div><div class="mcw">{w}</div></div>')
        elif kind == "field":
            out.append(f'<div class="mfield">{val}</div>')
        elif kind == "cta":
            out.append(f'<div class="mcta">{val}</div>')
        elif kind == "re":
            out.append(f'<div class="mre">{val}</div>')
    return "".join(out)


def build():
    os.makedirs(OUT, exist_ok=True)
    ads = []
    for a in ADS:
        d = dict(a)
        d["img"] = data_uri(os.path.join(CARDS, a["file"]))
        ads.append(d)

    feed = "".join(
        f'<div class="slot" data-id="{a["id"]}">'
        f'<div class="rank {a["rank_kind"]}">{a["rank"]}</div>'
        f'<div class="terr">{a["territory"]}</div>'
        f'<div class="fb">'
        f'<div class="fbtop"><div class="av"></div><div>'
        f'<div class="fbn">Fields Real Estate</div>'
        f'<div class="fbm">Sponsored · {GLOBE}</div></div></div>'
        f'<div class="fbtxt" data-full="{a["primary"].replace(chr(34), "&quot;")}"></div>'
        f'<div class="fold">fold</div>'
        f'<img class="fbimg" src="{a["img"]}" alt="{a["territory"]} creative">'
        f'<div class="fbfoot"><div class="fbfl">'
        f'<div class="fbfd">fieldsestate.com.au</div>'
        f'<div class="fbfh">{a["headline"]}</div></div>'
        f'<div class="fbb">{a["cta"]}</div></div></div>'
        f'<div class="ann"><b>Why this one.</b> {a["why"]}</div>'
        f'<div class="ann"><b>Note.</b> {a["note"]}</div>'
        f'</div>' for a in ads)

    arms = "".join(
        f'<div class="arm {"lead" if x["role_kind"]=="lead" else ""}">'
        f'<div class="armh"><span class="armid">{x["id"]}</span>'
        f'<span class="armn">{x["name"]}</span>'
        f'<span class="pill {x["role_kind"]}">{x["role"]}</span></div>'
        f'<div class="gist">{x["gist"]}</div>'
        f'<div class="specq">{x["spec"]}</div>'
        f'<div class="mock">{screen_html(x["screen"])}</div>'
        f'<div class="risk"><b>Risk.</b> {x["risk"]}</div>'
        f'</div>' for x in ARMS)

    journey = "".join(
        f'<div class="jstep"><div class="jnum">{i+1}</div><div class="jbody">'
        f'<div class="jt">{t}</div><div class="jd">{d}</div>'
        f'<ul class="jl">{"".join(f"<li>{b}</li>" for b in bl)}</ul>'
        f'</div></div>' for i, (t, d, bl) in enumerate(JOURNEY))

    barred = "".join(
        f'<div class="bx"><div class="bt">{t}</div>'
        f'<div class="bwas">{w}</div><div class="bwhy">{y}</div></div>'
        for t, w, y in BARRED)

    blockers = "".join(
        f'<div class="br"><span class="bc {k}">{"blocker" if k=="blocker" else "open"}</span>'
        f'<div><div class="brt">{t}</div><div class="brd">{d}</div></div></div>'
        for k, t, d in BLOCKERS)

    js = """
const FOLD_AT = 125;
document.querySelectorAll('.fbtxt').forEach(el => {
  const flat = el.dataset.full.replace(/\\n+/g, ' ');
  if (flat.length <= FOLD_AT) { el.textContent = flat; return; }
  // Facebook breaks at a word boundary, not mid-word — walk back to the last space.
  const raw = flat.slice(0, FOLD_AT);
  const head = raw.slice(0, raw.lastIndexOf(' ')).replace(/[,\\u2014\\u2013-]$/, '').trim();
  el.textContent = head + '\\u2026 ';
  const more = document.createElement('span');
  more.className = 'more';
  more.textContent = 'See more';
  el.appendChild(more);
});
"""

    html = f"""<title>Valuation ads — V2, calibrated to the Campaign 1 specs</title>
<style>{CSS}</style>
<div class="wrap">
<header>
  <div class="vtag">Version 2 · calibrated</div>
  <h1>One ad, held constant. Three ways into it.</h1>
  <p class="lede">V1 proposed four creatives competing against each other, opening a Meta
  instant form. The Cold-Meta Entry specs published on 17 August do the opposite: they
  <b>hold the ad constant and vary what happens after the click</b>, and they bar the form
  outright. This is that proposal rebuilt to the specification.</p>
  <div class="cmp">V1 is left exactly as it was so the two can be read side by side. The
  creatives below are the real 1080&times;1080 render output, not an approximation — the
  same files that would upload to Meta.</div>
</header>

<section>
  <div class="sh"><span class="sn">01</span><h2>The ad</h2></div>
  <p class="sd">Doc 03 makes the creative a constant, not a variable: “<em>Use one strong
  static, question-led Meta ad and hold it constant across all entry variants.</em>” So
  there is one ad per territory rather than a bake-off — and the territory that launches
  first is not the one this folder was built around.</p>
  <div class="feed">{feed}</div>
</section>

<section>
  <div class="sh"><span class="sn">02</span><h2>What replaces the form</h2></div>
  <p class="sd">The first experiment is proof depth. Same ad, same audience, same result
  page — the only thing that changes is how much of the product a cold visitor sees before
  being asked which property to analyse. None of the three asks for a name, a phone number
  or an email.</p>
  <div class="arms">{arms}</div>
</section>

<section>
  <div class="sh"><span class="sn">03</span><h2>Where the click actually goes</h2></div>
  <p class="sd">The governing idea is that the visitor should feel they are instructing a
  property-analysis tool, not identifying themselves to an agent. Identity comes last, and
  only to buy a service the person has chosen.</p>
  <div class="jr">{journey}</div>
</section>

<section>
  <div class="sh"><span class="sn">04</span><h2>What V1 contained that the specs bar</h2></div>
  <p class="sd">Not preferences — these appear in the non-negotiable guardrail list, the
  “what not to build first” list, or the acceptance criteria.</p>
  <div class="barred">{barred}</div>
</section>

<section>
  <div class="sh"><span class="sn">05</span><h2>Before this can run</h2></div>
  <p class="sd">Two of these are on the critical path for Release 1. The rest need a
  decision rather than a build.</p>
  <div class="bl">{blockers}</div>
</section>

<footer>
  <span>Fields Real Estate · 03_Facebook/Ad_Categories/Valuation</span>
  <span>Calibrated against docs 00–04, Cold-Meta Entry Architecture, 17 Aug 2026</span>
</footer>
</div>
<script>{js}</script>
"""
    p = os.path.join(OUT, "concept_v2_review.html")
    open(p, "w").write(html)
    print(f"{p}  ({os.path.getsize(p)/1024:.0f} KB)")


if __name__ == "__main__":
    build()
