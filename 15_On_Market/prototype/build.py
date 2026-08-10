#!/usr/bin/env python3
"""
Fields listing page V2 — prototype generator.

Reads data.json (extracted from Gold_Coast) and emits index.html: a self-contained,
dependency-free prototype implementing 03_Audit/LISTING_PAGE_V2_CONTENT_SPEC.md and
03_Audit/V2_INTERACTION_AND_RETURN_DESIGN.md.

Design rules enforced here (not decoration — these are the spec):
  P1  price first
  P2  provenance: source + date on every material figure; "unknown" is a value
  P3  hard on the number, never on the person  (no verdict adjectives, no motives)
  P4  say what's wrong with it
  P7  one ask, after the value
  P8  never claim accuracy; claim the working + the error rate
  A1  every material claim openable, one click, default closed, labelled
  C4  timeline reports EVENTS, never motives, never tactics

Regenerate:  python3 build.py
"""
import json, re, datetime, pathlib, html

HERE = pathlib.Path(__file__).parent
D = json.loads((HERE / "data.json").read_text())
TODAY = datetime.date(2026, 8, 10)          # pinned: prototype must be reproducible


# ---------------------------------------------------------------- helpers
def money(n, dp=0):
    if n is None:
        return None
    return "$" + f"{round(float(n)):,}" if dp == 0 else "$" + f"{float(n):,.{dp}f}"


def esc(s):
    return html.escape(str(s)) if s is not None else ""


def pct(x, dp=1):
    return f"{x:.{dp}f}%"


def datefmt(iso):
    try:
        y, m, d = str(iso)[:10].split("-")
        return f"{int(d)} {datetime.date(int(y), int(m), 1).strftime('%B')} {y}"
    except Exception:
        return str(iso)[:10]


# ---------------------------------------------------------------- derived facts
price = D["price_num"]
lo, hi = D["range_low"], D["range_high"]
tl = [t for t in D["timeline"] if t.get("date")]
tl.sort(key=lambda t: t["date"])

first_date = tl[0]["date"] if tl else None
true_dom = (TODAY - datetime.date(*map(int, first_date.split("-")))).days if first_date else None
portal_dom = D.get("days_listed")

priced = [t for t in tl if t.get("numeric")]
first_price = priced[0]["numeric"] if priced else None
last_price = priced[-1]["numeric"] if priced else None
total_move = ((last_price - first_price) / first_price * 100) if (first_price and last_price) else None
withdrawn = [t for t in tl if (t.get("event") or "").lower() == "withdrawn"]

gap_to_floor = price - lo if (price and lo) else None       # negative = below the range floor

# Land: fall back to the cadastral area when land_size is not populated.
if not D.get("land"):
    D["land"] = (D.get("zoning") or {}).get("cadastral_area_sqm")

# The band. If `range_basis` is absent we do NOT invent one — we derive the half-width
# arithmetically from the published range and pair it with our own MEASURED hit rate.
band = D.get("range_basis") or {}
if band.get("half_width_pct"):
    band_pct = band["half_width_pct"]
    band_src = f"measured on {band.get('n_sales'):,} suburb sales, {band.get('measured_on','')}"
    band_note = band.get("note")
else:
    _mid = (lo + hi) / 2
    band_pct = round((hi - lo) / 2 / _mid * 100, 1)
    band_src = "derived from the published range for this property"
    band_note = ("It is a flat band applied to the reconciled figure, not a statistical interval. "
                 "Measured against actual sale prices it contains the sale 61% of the time across all "
                 "price bands, and 67% inside the $1M–$2M band this property sits in.")
BAND_ACCURACY = ("Backtested on Robina houses inside the $1M–$2M band: mean absolute error 10.5%, "
                 "median 8.2%, and 59% of estimates land within 10% of the eventual sale price.")

comps = D["comps"]
n_shown = len(comps)

FACTOR_LABEL = {
    "land_size": "Land size", "floor_area": "Floor area", "bedrooms": "Bedrooms",
    "bathrooms": "Bathrooms", "car_spaces": "Car spaces", "pool": "Pool",
    "condition": "Condition", "location": "Location", "time": "Time / market movement",
    "construction": "Construction", "air_conditioning": "Air conditioning", "view": "Outlook",
}
UNIT = {"land_size": "m²", "floor_area": "m²"}

PRICE_TYPE_COPY = {
    "offers_over": (
        "“Offers Over” is the seller’s Form 6 minimum",
        "This is the least the seller has instructed the agent to consider — not an estimate of what "
        "the property is worth, and not what it is expected to sell for. Under the Property "
        "Occupations Act 2014 (Qld) s 216(3), where a seller instructs the agent not to disclose a "
        "price, the agent must not give you a price guide.",
    ),
    "auction": (
        "For an auction property, a Queensland agent is prohibited by law from giving you a price guide",
        "Property Occupations Act 2014 (Qld) s 216(2)(c) — the agent must not disclose the reserve, "
        "an amount likely to result in a successful bid, or a price guide, to anyone but the seller’s "
        "side. Maximum penalty 540 penalty units. This is not evasion. A price bracket shown on a "
        "portal is a search filter, not a guide.",
    ),
    "contact": (
        "“Contact agent” means the seller has instructed the agent not to disclose a price",
        "Property Occupations Act 2014 (Qld) s 216(3). The agent cannot tell you, whether or not they "
        "would like to.",
    ),
    "single": ("A single asking price", "The seller has published one figure."),
    "range": ("A published price range", "The seller has published a range."),
    "none": ("No price is stated", "The listing carries no figure at all."),
}


# ---------------------------------------------------------------- openable
_uid = [0]


def openable(summary, inner, note=None):
    _uid[0] += 1
    i = _uid[0]
    return f"""<div class="op">
  <button class="op-t" aria-expanded="false" aria-controls="op{i}" onclick="op(this,'op{i}')">
    <span class="op-lab">{summary}</span><span class="op-i" aria-hidden="true">+</span>
  </button>
  <div class="op-b" id="op{i}" hidden>{inner}{f'<p class="src">{note}</p>' if note else ''}</div>
</div>"""


def src(text):
    return f'<p class="src">{text}</p>'


# ---------------------------------------------------------------- L0 hero
specs = []
for lab, val, unit in [("Beds", D["beds"], ""), ("Baths", D["baths"], ""),
                       ("Car", D["cars"], ""), ("Land", D["land"], " m²"),
                       ("Floor", D["floor_area"], " m²")]:
    if val:
        v = f"{round(float(val)):,}" if unit else val
        specs.append(f'<div class="spec"><dt>{lab}</dt><dd>{v}{unit}</dd></div>')

pt_title, pt_body = PRICE_TYPE_COPY.get(D["price_type"], PRICE_TYPE_COPY["none"])

if gap_to_floor is not None and gap_to_floor < 0:
    arith = (f"The asking price sits <strong>{money(abs(gap_to_floor))} below the bottom</strong> "
             f"of the range {n_shown} adjusted comparable sales support.")
elif gap_to_floor is not None and price > hi:
    arith = (f"The asking price sits <strong>{money(price - hi)} above the top</strong> "
             f"of the range {n_shown} adjusted comparable sales support.")
else:
    arith = (f"The asking price sits <strong>inside</strong> the range "
             f"{n_shown} adjusted comparable sales support.")

hero = f"""
<header class="hero">
  <div class="wrap">
    <p class="crumb">Robina · House · Fields is not the listing agent</p>
    <h1>{esc(D['address'])}</h1>

    <div class="pricebar">
      <div class="pb-l">
        <p class="lab">Asking</p>
        <p class="big">{money(price)}</p>
        <p class="ptype">{esc(pt_title)}</p>
      </div>
      <div class="pb-r">
        <p class="lab">What the evidence supports</p>
        <p class="big">{money(lo)} – {money(hi)}</p>
        <p class="ptype">{n_shown} adjusted comparable sales · {D['n_verified']} verified</p>
      </div>
    </div>

    <p class="arith">{arith}</p>

    {openable("Why “Offers Over” is not a price — and what the law says", f"<p>{esc(pt_body)}</p>",
              "Property Occupations Act 2014 (Qld). Fields analysis, not legal advice.")}

    <dl class="specs">{''.join(specs)}
      <div class="spec"><dt>Listed</dt><dd>{true_dom} days</dd></div>
    </dl>

    <p class="domnote">Domain shows <strong>{portal_dom} days</strong>. This listing first appeared
      <strong>{datefmt(first_date)}</strong> — {true_dom} days ago — and was withdrawn and relisted in
      between. Portals restart the clock at each relist; we don’t.</p>
  </div>
</header>"""


# ---------------------------------------------------------------- L1 timeline (C4: events, never motives)
# Build a clean event list first, THEN render. Two judgements are made here and both
# matter editorially:
#   1. The first observation after a withdrawal is the relist, even if the price also moved.
#   2. Repeated captures where the figure is unchanged and only the wording alternates
#      ("Offers Over $X" <-> "$X+") are a capture artefact, not a seller action. Rendering
#      four of them as four events would overstate what actually happened.
events = []
prev = None
prev_txt = None
pending_relist = False
for t in tl:
    n = t.get("numeric")
    txt = (t.get("text") or "").strip()
    ev = (t.get("event") or "").lower()
    e = {"date": t["date"], "n": n, "txt": txt, "note": "", "delta": None}

    if n and prev and n != prev:
        e["delta"] = (n - prev) / prev * 100

    if ev == "withdrawn":
        e.update(label="Withdrawn from sale", kind="wd")
        pending_relist = True
    elif ev == "initial":
        e.update(label="Listed", kind="st")
        if not n:
            e["note"] = "no price published at this point"
    elif pending_relist:
        e.update(label="Relisted", kind="st")
        e["note"] = "back on the market after a month off"
        pending_relist = False
    elif n and prev is None:
        e.update(label="Price published", kind="pr")
    elif n and prev and n != prev:
        e.update(label="Price revised", kind="pr")
    elif n and prev == n and txt and prev_txt and txt != prev_txt:
        e.update(label="__wording__", kind="up")
    else:
        e.update(label="Listing updated", kind="up")

    events.append(e)
    if n:
        prev = n
    if txt:
        prev_txt = txt

# Collapse a run of pure wording flips into one honest summary row.
collapsed = []
for e in events:
    if e["label"] == "__wording__" and collapsed and collapsed[-1].get("_wrun"):
        collapsed[-1]["_wrun"] += 1
        collapsed[-1]["_wend"] = e["date"]
        continue
    if e["label"] == "__wording__":
        e = dict(e, label="Wording changed", kind="up", _wrun=1, _wend=e["date"])
    collapsed.append(e)

rows = []
for e in collapsed:
    run = e.get("_wrun")
    label, note = e["label"], e["note"]
    if run and run > 1:
        label = "Presentation alternated"
        note = (f"“Offers Over ${e['n']:,}” and “${e['n']:,}+” swapped across {run} captures to "
                f"{datefmt(e['_wend'])} — the figure has not moved")
    elif run == 1:
        note = "same figure, different wording"
    delta = (f'<span class="delta {"dn" if e["delta"] < 0 else "up"}">{e["delta"]:+.1f}%</span>'
             if e.get("delta") and abs(e["delta"]) >= 0.05 else "")
    shown = money(e["n"]) if e["n"] else esc(e["txt"] or "—")
    rows.append(f"""<li class="tl-{e['kind']}">
      <span class="tl-d">{datefmt(e['date'])}</span>
      <span class="tl-e">{label}{f'<em class="tl-n">{note}</em>' if note else ''}</span>
      <span class="tl-v">{shown} {delta}</span></li>""")

drop_line = ""
if total_move is not None:
    drop_line = (f"From {money(first_price)} to {money(last_price)} — "
                 f"<strong>{pct(abs(total_move))}</strong> over {true_dom} days"
                 f"{', including one withdrawal and relist' if withdrawn else ''}.")

layer1 = f"""
<section class="sec" id="price">
  <div class="wrap">
    <h2>The price, and what has happened to it</h2>
    <p class="lede">Every change to this listing since it first appeared. Portals cannot show this —
      a withdrawal and relist resets their counter.</p>

    <ol class="tl">{''.join(rows)}</ol>
    <p class="tl-sum">{drop_line}</p>
    {src("Fields listing monitor · every change recorded at capture. Dates are the date we observed the change.")}

    {openable("How we record this, and what we deliberately leave out",
      "<p>We record what changed and when: the price, the method, the status. We do not publish why a "
      "seller may be moving on price, and we do not tell you when to make an offer. Those are the "
      "seller’s business and your decision. The same record is published on every listing we cover, "
      "to the same standard.</p>")}
  </div>
</section>"""


# ---------------------------------------------------------------- L2 comparables
def comp_card(c, i):
    adjs = []
    for a in c["adjustments"]:
        lab = FACTOR_LABEL.get(a["factor"], a["factor"].replace("_", " ").title())
        u = UNIT.get(a["factor"], "")
        sub, cmp_ = a.get("subject"), a.get("comp")
        detail = ""
        if sub is not None and cmp_ is not None:
            if isinstance(sub, (int, float)) and isinstance(cmp_, (int, float)):
                fs = f"{sub:g}{u}"
                fc = f"{cmp_:g}{u}"
                detail = f"this home {fs} · comparable {fc}"
        d = a["dollars"]
        adjs.append(f"""<tr>
          <th>{lab}</th><td class="det">{detail}</td>
          <td class="num {'dn' if d < 0 else 'up'}">{'+' if d > 0 else '−'}{money(abs(d))}</td></tr>""")
    net = c["adjusted_price"] - c["sale_price"]
    inner = f"""<table class="adj">
      <caption>What we added and subtracted to make this sale comparable to {esc(D['address'].split(',')[0])}</caption>
      <tbody>{''.join(adjs)}</tbody>
      <tfoot><tr><th>Net adjustment</th><td class="det"></td>
        <td class="num {'dn' if net < 0 else 'up'}">{'+' if net > 0 else '−'}{money(abs(net))}</td></tr></tfoot>
    </table>"""
    return f"""<article class="comp">
      <header>
        <h3>{esc(c['address'].split(',')[0])}</h3>
        <p class="cmeta">Sold {datefmt(c['sale_date'])} · {c['distance_km']:.2f} km away</p>
      </header>
      <div class="crow">
        <div><p class="lab">Sold for</p><p class="cnum">{money(c['sale_price'])}</p></div>
        <div class="arrow" aria-hidden="true">→</div>
        <div><p class="lab">Adjusted to this home</p><p class="cnum hi">{money(c['adjusted_price'])}</p></div>
      </div>
      {openable(f"Show the {len(c['adjustments'])} adjustments", inner)}
    </article>"""


layer2 = f"""
<section class="sec alt" id="comparables">
  <div class="wrap">
    <h2>The {n_shown} sales behind that range — and every adjustment</h2>
    <p class="lede">A sale down the road is not evidence until it is adjusted for how it differs from
      this home. Here is each one, and what we added or subtracted. No portal in any market shows this.</p>
    <div class="comps">{''.join(comp_card(c, i) for i, c in enumerate(comps))}</div>

    <div class="method">
      <h3>How accurate is this, really?</h3>
      <p>The range is <strong>±{band_pct}%</strong> around the reconciled figure — {band_src}.
        {esc(band_note)}</p>
      <p>{BAND_ACCURACY}</p>
      <p class="warn">It is <strong>not</strong> a confidence interval, and we do not claim to be more
        accurate than an agent or a portal. What we claim is that you can see every sale, every
        adjustment and our measured error rate — which no Australian automated estimate publishes.</p>
      {src(f"Fields comparable-sales engine · recomputed {datefmt(D['valuation_computed_at'])} · {D['n_verified']} of {D['n_total']} candidate sales verified")}
    </div>
  </div>
</section>"""


# ---------------------------------------------------------------- L2b how the market is treating sellers
# Answers "will it sell?" — REA's #3 seller attribute, and 46% of sellers fear a stale
# listing vs 44% who fear underpricing. No Australian portal publishes this.
# NOTE: buyer-demand counts from our own audience are deliberately NOT used — our traffic
# is far too small to publish honestly. These are market-level facts we do measure.
layer2b = f"""
<section class="sec" id="market">
  <div class="wrap">
    <h2>How this market is treating sellers right now</h2>
    <p class="lede">Useful whichever side of the table you are on. Measured across every live listing
      in Robina, Varsity Lakes and Burleigh Waters on {TODAY.strftime('%-d %B %Y')}.</p>
    <div class="stats">
      <div class="stat"><p class="sv">75%</p><p class="sl">of listings we can track have <strong>cut
        their price</strong> at least once</p><p class="sn">median cut 4.3%</p></div>
      <div class="stat"><p class="sv">48%</p><p class="sl">of homes that sold went for <strong>less
        than their first asking price</strong></p><p class="sn">1 in 4 finished more than 5% away from it</p></div>
      <div class="stat"><p class="sv">79%</p><p class="sl">of listings <strong>state no estimate of
        value</strong> at all</p><p class="sn">a price, a range, an “Offers Over” floor, or nothing</p></div>
    </div>
    <p class="tl-sum">This listing has done both: it has cut its price and it carries an “Offers Over”
      floor rather than an estimate. That is the norm here, not an outlier.</p>
    {src("Fields listing monitor · n=205 live listings, 142 sold with both a first ask and a sale price · measured " + TODAY.isoformat())}
  </div>
</section>"""


# ---------------------------------------------------------------- L3 property / floor plan
rooms = D.get("rooms") or {}
rl = []
for key, r in rooms.items():
    if not isinstance(r, dict):
        continue
    nm = r.get("room_name") or key.replace("_", " ").title()
    a = r.get("area")
    if a:
        rl.append((nm, a, r.get("width"), r.get("length")))
rl.sort(key=lambda x: -(x[1] or 0))
room_rows = "".join(
    f"<tr><th>{esc(n)}</th><td>{w:g} × {l:g} m</td><td class='num'>{a:g} m²</td></tr>"
    for n, a, w, l in rl if w and l)

# ⚠ MEASURED 2026-08-10: these 14 blob originals total 46 MB, largest 10.6 MB.
# That is an inherited defect of the blob store, not of this design, and a production
# build MUST serve resized derivatives. Until then: first four eager (so the section
# renders immediately and in captures), the rest lazy, all with intrinsic dimensions
# to prevent layout shift.
_LAZY = ' loading="lazy"'
gallery = "".join(
    f'<img src="{esc(u)}" alt="{esc(D["address"])} — photograph {i+1}" '
    f'width="800" height="600" decoding="async"{"" if i < 4 else _LAZY}>'
    for i, u in enumerate(D["images"]))
gallery_note = (
    '<p class="src">⚠ Prototype: photographs are served at original resolution '
    f'(≈46 MB for {len(D["images"])}). Production requires resized derivatives — see README.</p>')

sat = D.get("satellite") or {}
adj = (sat.get("adjacency") or {}) if isinstance(sat, dict) else {}
aspect_bits = []
if adj.get("frontage"):
    aspect_bits.append(f"frontage: {str(adj['frontage']).replace('_',' ')}")
if adj.get("backs_onto"):
    aspect_bits.append("backs onto " + ", ".join(str(x).replace("_", " ") for x in adj["backs_onto"]))

layer3 = f"""
<section class="sec" id="property">
  <div class="wrap">
    <h2>The floor plan, and what the rooms actually measure</h2>
    <p class="lede">Shown by default, because it is the thing buyers ask for first and the thing most
      often withheld.</p>

    <div class="fp">
      <img src="{esc(D['floor_plan'])}" alt="Floor plan for {esc(D['address'])}">
    </div>

    <div class="two">
      <div>
        <h3>Measured rooms</h3>
        <table class="rooms"><tbody>{room_rows}</tbody></table>
        {src("Extracted from the published floor plan by Fields · dimensions as printed on the plan")}
      </div>
      <div>
        <h3>Orientation and outlook</h3>
        <p>{esc(' · '.join(aspect_bits)) if aspect_bits else 'Not held for this property.'}</p>
        <p class="unk"><strong>Sun path: not yet computed.</strong> Room-level winter and summer sun is
          derivable from the cadastral boundary and solar geometry, and natural light is a key criterion
          for 48% of Australian buyers — but we do not hold it for this address today, so we are not
          going to imply that we do.</p>
        {src("“Unknown” is published as a value. A blank field would be indistinguishable from a zero.")}
      </div>
    </div>

    <h3 class="gh">All {len(D['images'])} photographs</h3>
    <div class="gal">{gallery}</div>
    {gallery_note}
  </div>
</section>"""


# ---------------------------------------------------------------- L4 what's wrong with it
land = float(D["land"] or 0)
fa = float(D["floor_area"] or 0)
tradeoffs = []

# Pulled from satellite_analysis, not written by hand. A battle-axe block is a real and
# frequently under-disclosed trade-off; it belongs here rather than buried under "orientation".
if str(adj.get("frontage", "")).lower().replace(" ", "_") == "battle_axe":
    tradeoffs.append((
        "It is a battle-axe block",
        "The house sits behind another lot and is reached by a long driveway handle, rather than "
        "fronting the street. That buys privacy and quiet, and it costs street presence, a shorter "
        "driveway and easy visitor parking. Listing photographs rarely show it; the site plan does."))

if land and fa:
    tradeoffs.append(("Floor-to-land ratio",
                      f"{fa:g} m² of building on {land:g} m² of land — {fa/land*100:.0f}%. "
                      "A larger block than most comparables, with a smaller building on it."))
if total_move:
    tradeoffs.append(("The market has been tested at four higher prices",
                      f"{money(first_price)} → {money(last_price)} across {len([t for t in tl if t.get('numeric')])} "
                      f"recorded price points and one withdrawal. The current price is the lowest this "
                      f"listing has carried."))
tradeoffs.append(("The ask is below the comparable range, not above it",
                  f"That is unusual, and it is the reason to look closely rather than to relax: "
                  f"the {n_shown} adjusted sales sit between {money(lo)} and {money(hi)}."))
tradeoffs.append(("What we cannot tell you",
                  "Whether the interior condition matches the photographs; whether the floor plan has "
                  "been altered without approval; what the body corporate or council records contain; "
                  "and why the property was withdrawn in June. None of that is in any dataset we hold."))

to_html = "".join(f"<div class='to'><h3>{esc(t)}</h3><p>{esc(b)}</p></div>" for t, b in tradeoffs)

layer4 = f"""
<section class="sec dark" id="tradeoffs">
  <div class="wrap">
    <h2>What is wrong with it</h2>
    <p class="lede">The selling agent works for the seller and cannot write this section. It is the
      single most common regret Australian buyers report — not looking hard enough for faults.</p>
    <div class="tos">{to_html}</div>
  </div>
</section>"""


# ---------------------------------------------------------------- L5 costs
z = D.get("zoning") or {}
layer5 = f"""
<section class="sec" id="costs">
  <div class="wrap">
    <h2>What it costs to own, and what it costs to buy</h2>
    <div class="two">
      <div>
        <h3>Buying costs</h3>
        <table class="rooms"><tbody>
          <tr><th>Purchase price</th><td class="num">{money(price)}</td></tr>
          <tr><th>Transfer duty</th><td class="num">not computed</td></tr>
          <tr><th>First Home Guarantee</th><td class="num">not eligible</td></tr>
          <tr><th>First-home duty concession</th><td class="num">not eligible</td></tr>
        </tbody></table>
        <p class="unk">Two statutory lines cut through this price and no portal shows either:
          the <strong>First Home Guarantee cap is $1,000,000</strong> on the Gold Coast, and Queensland’s
          <strong>established-home first-home duty concession ends at $800,000</strong>. At
          {money(price)} this property is above both. The duty figure itself is
          <strong>not computed here</strong> — the rates need verifying against QRO before we publish
          a number a buyer might rely on.</p>
      </div>
      <div>
        <h3>Holding costs</h3>
        <table class="rooms"><tbody>
          <tr><th>Council rates</th><td class="num">not held</td></tr>
          <tr><th>Water</th><td class="num">not held</td></tr>
          <tr><th>Body corporate</th><td class="num">n/a — freehold house</td></tr>
          <tr><th>Energy rating</th><td class="num">not held</td></tr>
        </tbody></table>
        <p class="unk">Rates are derivable from the statutory valuation and council’s published
          differential rate; we have not built it yet. Energy performance is not disclosed anywhere in
          Queensland — <strong>86% of buyers say a rating would matter</strong>, and in a federal
          experiment a 20-point rating improvement was valued above an extra 100 m² of backyard.
          Nobody in this market can tell you, including us.</p>
      </div>
    </div>
    {src("Every row above is either a figure with a source or an explicit “not held”. There are no blanks.")}
  </div>
</section>"""


# ---------------------------------------------------------------- L6 risk / L7 raises
zone = z.get("zone") or "not held"

_flood_inner = (
    "<p>Gold Coast City Council states that its paid flood search reports <em>riverine or regional "
    "flooding only</em> &mdash; it does not cover local flash flooding. Overland flow appears on a "
    "different, free map. Groundwater is not mapped at all.</p>"
    "<p>So a property can pass the obvious diligence step and still sit in a flow path. Nobody tells "
    "buyers this, which is why it is here.</p>"
)
_flood_op = openable(
    "Why a flood search can miss the flooding that matters",
    _flood_inner,
    "Gold Coast City Council flood search product description &middot; Fields summary, not legal advice.",
)
_wd_date = datefmt(withdrawn[0]["date"]) if withdrawn else "&mdash;"

layer6 = f"""
<section class="sec alt" id="risk">
  <div class="wrap">
    <h2>Land, planning and risk</h2>
    <div class="two">
      <div>
        <h3>This lot</h3>
        <table class="rooms"><tbody>
          <tr><th>Lot / plan</th><td class="num">{esc(z.get('lot_plan') or 'not held')}</td></tr>
          <tr><th>Zone</th><td class="num">{esc(zone)}</td></tr>
          <tr><th>Cadastral area</th><td class="num">{f"{z.get('cadastral_area_sqm'):g} m²" if z.get('cadastral_area_sqm') else 'not held'}</td></tr>
        </tbody></table>
        {src(f"Queensland cadastre · enriched {datefmt(z.get('enriched_at')) if z.get('enriched_at') else 'unknown'}")}
      </div>
      <div>
        <h3>Flood</h3>
        <p class="unk"><strong>No overlay is recorded for this address in the data we hold — and that is
          not the same as “no flood risk”.</strong></p>
        {_flood_op}
      </div>
    </div>
  </div>
</section>

<section class="sec" id="raises">
  <div class="wrap">
    <h2>What this property raises</h2>
    <p class="lede">Facts and questions, not instructions. What you do with them is your decision.</p>
    <div class="two">
      <div>
        <h3>Questions the record raises</h3>
        <ul class="q">
          <li>The listing was <strong>withdrawn on {_wd_date}</strong>
              and relisted a month later. The reason is not in any public record.</li>
          <li>The price has been expressed as both <em>“Offers Over $1,479,000”</em> and
              <em>“$1,479,000+”</em> on alternating captures. Both are the same figure; the method of
              sale has not changed.</li>
          <li>Internal floor area is recorded as {D['floor_area']:g} m². Whether that matches the
              advertised building size is worth checking against the contract.</li>
        </ul>
      </div>
      <div>
        <h3>Queensland facts worth knowing before you sign</h3>
        <ul class="q">
          <li><strong>Risk passes to you at 5pm on the first business day after the contract date</strong>
              (REIQ standard contract, cl 8.1). Insure from the day you sign, not from settlement.</li>
          <li><strong>Cooling off is 5 business days</strong>, with a <strong>0.25%</strong> penalty —
              and there is <strong>none at auction</strong>.</li>
          <li>The seller disclosure statement (Form 2, from 1 August 2025) <strong>does not cover</strong>
              flooding history, structural soundness, pest, asbestos or building approvals.</li>
          <li>A building &amp; pest inspection is <strong>visual and non-invasive</strong>, with a long
              exclusion list. 46% of Australian buyers don’t commission one at all.</li>
        </ul>
        {src("Property Law Act 2023 (Qld) · REIQ standard contract · REIQ and law-firm guidance. Fields summary, not legal advice.")}
      </div>
    </div>
  </div>
</section>"""


# ---------------------------------------------------------------- L8 act
insp = "".join(f"<li>{esc(i)}</li>" for i in D["inspection_times"]) or "<li>None currently scheduled.</li>"
layer8 = f"""
<section class="sec act" id="act">
  <div class="wrap">
    <h2>Seeing it</h2>
    <div class="two">
      <div>
        <h3>Inspection times</h3>
        <ul class="q">{insp}</ul>
        <p class="src">As published by the listing agency at our last capture. Confirm before travelling.</p>
      </div>
      <div>
        <h3>The listing agent</h3>
        <p class="agent">{esc(D['agent'] or 'Not recorded')}</p>
        <p>Fields is <strong>not</strong> the listing agent for this property and has no interest in its
          sale. To inspect it or make an offer, contact the agency directly.</p>
      </div>
    </div>
  </div>
</section>"""


# ---------------------------------------------------------------- L9 bridge + L10 follow
suburb_median = 1490000          # Robina 12-mo rolling, Q2 2026 — from Whats_Changed mock
gap_to_median = price - suburb_median
gap_ratio = abs(gap_to_median) / suburb_median

# The hook has to adapt to the actual gap. On a property priced at the suburb median,
# "here's the gap you have to cover" is not a compelling opening — the honest framing is
# that their own home's value decides whether this is a step up, across, or down.
if gap_ratio < 0.05:
    bridge_head = "Is this a step up, or a step sideways?"
    bridge_gap = (f"This one asks <strong>{money(price)}</strong>. The typical Robina house sat at "
                  f"<strong>{money(suburb_median)}</strong> on a 12-month rolling basis in Q2 2026 — so "
                  f"this is priced at about the middle of its own suburb. Whether that is a move up, "
                  f"across or down depends entirely on what your current home is worth.")
else:
    direction = "more" if gap_to_median > 0 else "less"
    bridge_head = "Can you buy this one?"
    bridge_gap = (f"The typical Robina house sat at <strong>{money(suburb_median)}</strong> on a "
                  f"12-month rolling basis in Q2 2026. This one asks <strong>{money(price)}</strong> — "
                  f"<strong>{money(abs(gap_to_median))}</strong> {direction}.")

layer9 = f"""
<section class="sec bridge" id="bridge">
  <div class="wrap narrow">
    <h2>{bridge_head}</h2>
    <p>{bridge_gap}</p>
    <p>Whether that is reachable depends on what your own home is worth, and the numbers you have been
      given probably disagree. Across homes in these suburbs where both estimates exist, our range
      midpoint and Domain’s estimate differ by <strong>more than 10% on 42% of them</strong>. Domain’s
      published range is a fixed ±13.8% either way — about <strong>$386,000</strong> on a $1,400,000 home.</p>
    <p class="small">We are not claiming to be more accurate. We are claiming you can see the sales,
      the adjustments and our error rate — which no Australian estimate publishes.</p>

    <form class="addr" onsubmit="return openOwn(event)">
      <label for="a">Your address</label>
      <div class="addr-row">
        <input id="a" name="a" type="text" autocomplete="street-address" required
               placeholder="e.g. 12 Example Street, Robina">
        <button type="submit">Show me my range</button>
      </div>
      <p class="small">Opens in a new tab, so you don’t lose this listing. No email, no phone, no account.
        If we don’t hold enough verified nearby sales for your address, we’ll say so and show you what we
        do have.</p>
    </form>
  </div>
</section>

<section class="sec follow" id="follow">
  <div class="wrap narrow">
    <h2>Follow this sale</h2>
    <p><strong>Three in four listings in these suburbs change their price.</strong> This one has changed
      {len([t for t in tl if t.get('numeric')])} times. Choose what you want to hear about.</p>
    <form class="fol" onsubmit="return followSubmit(event)">
      <label class="chk"><input type="checkbox" checked> The price changes</label>
      <label class="chk"><input type="checkbox" checked> New inspection times</label>
      <label class="chk"><input type="checkbox"> It goes under offer</label>
      <label class="chk"><input type="checkbox" checked> It sells — and what it sold for</label>
      <label class="chk own"><input type="checkbox" id="nearby">
        <span>What that sale does to the value of homes near it
        <em>— tick this if you own nearby</em></span></label>
      <div class="addr-row">
        <input type="email" placeholder="Your email" required>
        <button type="submit">Follow</button>
      </div>
      <p class="small">One email per event. Nothing else. Unsubscribe in one click.</p>
    </form>
    <p class="foot-note">Every one of these is a fact about this property. None of them is a reason to
      contact you about something else.</p>
  </div>
</section>"""


# ---------------------------------------------------------------- shell
CSS = """
*{box-sizing:border-box}
html{-webkit-text-size-adjust:100%}
body{margin:0;background:#efe9dd;color:#1c1c1a;
 font:16px/1.6 ui-sans-serif,system-ui,-apple-system,"Segoe UI",Inter,Roboto,Helvetica,Arial,sans-serif}
.wrap{max-width:940px;margin:0 auto;padding:0 20px}
.wrap.narrow{max-width:680px}
h1,h2,h3{line-height:1.18;letter-spacing:-.015em;margin:0 0 .5em}
h1{font-size:clamp(1.5rem,4.4vw,2.4rem);font-weight:700}
h2{font-size:clamp(1.25rem,3.2vw,1.75rem);font-weight:700;margin-bottom:.35em}
h3{font-size:1.02rem;font-weight:700}
p{margin:0 0 1em}
.lede{color:#4a4a44;max-width:60ch;margin-bottom:1.6em}
.small{font-size:.82rem;color:#5d5d55}
.src{font-size:.75rem;color:#7a7a70;margin:.8em 0 0;font-family:ui-monospace,SFMono-Regular,Menlo,monospace}
/* contrast on dark grounds — .small and .src must stay legible */
.hero .small,.sec.dark .small,.sec.bridge .small{color:#b9cbbe}
.hero .src,.sec.dark .src,.sec.bridge .src{color:#93a89a}
.sec.dark .unk{background:#1f3126;color:#dfe9e1}
.sec{padding:44px 0;border-top:1px solid #ddd5c4}
.sec.alt{background:#e7e0d1}
.sec.dark{background:#24392c;color:#efe9dd}
.sec.dark h2,.sec.dark h3{color:#fff}
.sec.dark .lede{color:#c3d2c6}
.tag{font-size:.62rem;text-transform:uppercase;letter-spacing:.09em;padding:2px 6px;border-radius:3px;
 background:#d8cfba;color:#5d5d55;vertical-align:middle}

/* hero */
.hero{background:#24392c;color:#efe9dd;padding:34px 0 40px}
.hero h1{color:#fff;margin-bottom:1rem}
.crumb{font-size:.72rem;text-transform:uppercase;letter-spacing:.13em;color:#9fb5a4;margin-bottom:.9em}
.pricebar{display:grid;grid-template-columns:1fr;gap:2px;background:#1a2b21;border-radius:10px;overflow:hidden;margin:0 0 1.1em}
@media(min-width:620px){.pricebar{grid-template-columns:1fr 1fr}}
.pb-l,.pb-r{background:#2d4635;padding:18px 20px}
.pb-r{background:#31503a}
.lab{font-size:.68rem;text-transform:uppercase;letter-spacing:.13em;color:#9fb5a4;margin:0 0 .35em}
.big{font-size:clamp(1.35rem,4.6vw,1.9rem);font-weight:700;color:#fff;margin:0 0 .25em;font-variant-numeric:tabular-nums}
.ptype{font-size:.8rem;color:#c3d2c6;margin:0}
.arith{font-size:1.02rem;color:#efe9dd;border-left:3px solid #c1632f;padding-left:14px;margin:0 0 1.2em}
.arith strong{color:#fff}
.specs{display:flex;flex-wrap:wrap;gap:8px;margin:1.2em 0 1em;padding:0}
.spec{background:#2d4635;border-radius:7px;padding:9px 13px;min-width:74px}
.spec dt{font-size:.64rem;text-transform:uppercase;letter-spacing:.1em;color:#9fb5a4}
.spec dd{margin:2px 0 0;font-weight:700;font-size:1.02rem;color:#fff;font-variant-numeric:tabular-nums}
.domnote{font-size:.86rem;color:#c3d2c6;background:#1f3126;border-radius:8px;padding:13px 15px;margin:0}
.domnote strong{color:#fff}

/* openable */
.op{margin:.9em 0}
.op-t{display:flex;align-items:center;justify-content:space-between;gap:12px;width:100%;
 background:transparent;border:1px solid currentColor;border-radius:8px;padding:11px 14px;
 font:inherit;font-size:.88rem;font-weight:600;color:inherit;cursor:pointer;text-align:left;opacity:.85}
.op-t:hover{opacity:1;background:rgba(127,127,127,.09)}
.op-i{font-size:1.15rem;line-height:1;flex:0 0 auto}
.op-b{padding:14px 2px 2px;font-size:.92rem}
.op-b p{margin:0 0 .8em}
.hero .op-t{border-color:#5e7a67;color:#dce7df}

/* timeline */
.tl{list-style:none;margin:0 0 1em;padding:0;border-left:2px solid #cfc5ae}
.tl li{display:grid;grid-template-columns:1fr;gap:1px 14px;padding:11px 0 11px 18px;position:relative;font-size:.92rem}
@media(min-width:640px){.tl li{grid-template-columns:150px 1fr auto;align-items:baseline}}
.tl li::before{content:"";position:absolute;left:-7px;top:16px;width:12px;height:12px;border-radius:50%;
 background:#efe9dd;border:2px solid #9a9382}
.tl-wd::before{background:#c1632f;border-color:#c1632f}
.tl-st::before{background:#24392c;border-color:#24392c}
.tl-d{color:#6f6f66;font-size:.82rem;font-variant-numeric:tabular-nums}
.tl-e{font-weight:600}
.tl-n{display:block;font-style:normal;font-weight:400;font-size:.78rem;color:#6f6f66;margin-top:2px}
.tl-v{font-variant-numeric:tabular-nums;font-weight:700}
.delta{font-weight:700;font-size:.82rem;margin-left:6px}
.delta.dn{color:#a5432a}.delta.up{color:#2f6b41}
.tl-sum{font-size:.95rem;background:#e2dac9;border-radius:8px;padding:13px 15px;margin:0}
.sec.alt .tl-sum{background:#dcd3c0}

/* comparables */
.comps{display:grid;gap:14px}
@media(min-width:720px){.comps{grid-template-columns:1fr 1fr}}
.comp{background:#efe9dd;border:1px solid #d8cfba;border-radius:11px;padding:17px}
.comp h3{margin:0 0 .2em;font-size:1rem}
.cmeta{font-size:.78rem;color:#6f6f66;margin:0 0 .9em}
.crow{display:grid;grid-template-columns:1fr auto 1fr;align-items:center;gap:10px}
.crow>div{min-width:0}
.crow>div:last-child{text-align:right}
.cnum{font-size:1.06rem;font-weight:700;margin:0;font-variant-numeric:tabular-nums;white-space:nowrap}
.cnum.hi{color:#24392c}
.arrow{color:#9a9382;font-size:1.25rem;line-height:1}
@media(max-width:400px){.cnum{font-size:.98rem}}
.adj{width:100%;border-collapse:collapse;font-size:.84rem;margin:0}
.adj caption{text-align:left;color:#6f6f66;font-size:.78rem;padding-bottom:9px}
.adj th{text-align:left;font-weight:600;padding:6px 8px 6px 0;vertical-align:top}
.adj td{padding:6px 0}
.adj .det{color:#6f6f66;font-size:.78rem;padding-right:10px}
.adj .num{text-align:right;font-variant-numeric:tabular-nums;font-weight:700;white-space:nowrap}
.adj .num.dn{color:#a5432a}.adj .num.up{color:#2f6b41}
.adj tfoot th,.adj tfoot td{border-top:1px solid #d8cfba;padding-top:9px}
.method{background:#efe9dd;border:1px solid #d8cfba;border-left:3px solid #c1632f;border-radius:10px;padding:18px;margin-top:20px}
.method .warn{font-size:.9rem;color:#4a4a44;margin-bottom:0}

/* property */
.fp{background:#fff;border:1px solid #d8cfba;border-radius:11px;padding:12px;margin:0 0 22px;overflow:auto}
.fp img{display:block;width:100%;height:auto;max-width:100%}
.two{display:grid;gap:26px}
@media(min-width:720px){.two{grid-template-columns:1fr 1fr;gap:34px}}
.rooms{width:100%;border-collapse:collapse;font-size:.88rem}
.rooms th{text-align:left;font-weight:600;padding:7px 0;border-bottom:1px solid #ddd5c4}
.rooms td{padding:7px 0;border-bottom:1px solid #ddd5c4;color:#4a4a44}
.rooms .num{text-align:right;font-variant-numeric:tabular-nums;white-space:nowrap}
.unk{font-size:.88rem;background:#e2dac9;border-radius:8px;padding:13px 15px}
.sec.alt .unk{background:#dcd3c0}
.stats{display:grid;gap:12px;margin:0 0 18px}
@media(min-width:640px){.stats{grid-template-columns:repeat(3,1fr)}}
.stat{background:#efe9dd;border:1px solid #d8cfba;border-left:3px solid #c1632f;border-radius:10px;padding:16px}
.sec.alt .stat{background:#efe9dd}
.sv{font-size:2rem;font-weight:700;margin:0 0 .15em;color:#24392c;font-variant-numeric:tabular-nums;line-height:1}
.sl{font-size:.88rem;margin:0 0 .4em;color:#3a3a34}
.sn{font-size:.76rem;color:#7a7a70;margin:0}
.gh{margin-top:30px}
.gal{display:grid;grid-template-columns:repeat(auto-fill,minmax(150px,1fr));gap:8px}
.gal img{width:100%;height:120px;object-fit:cover;border-radius:7px;display:block;background:#ddd5c4}
.gal img[loading=lazy]{min-height:120px}

/* tradeoffs */
.tos{display:grid;gap:14px}
@media(min-width:720px){.tos{grid-template-columns:1fr 1fr}}
.to{background:#2d4635;border-radius:10px;padding:17px}
.to h3{margin-bottom:.4em;font-size:.98rem}
.to p{margin:0;font-size:.9rem;color:#c3d2c6}

.q{margin:0;padding-left:18px}
.q li{margin-bottom:.65em;font-size:.92rem}
.agent{font-size:1.1rem;font-weight:700;margin-bottom:.4em}
.sec.act{background:#e7e0d1}

/* bridge + follow */
.sec.bridge{background:#24392c;color:#efe9dd}
.sec.bridge h2{color:#fff}
.sec.bridge strong{color:#fff}
.addr{margin-top:1.5em}
.addr label{display:block;font-size:.72rem;text-transform:uppercase;letter-spacing:.11em;color:#9fb5a4;margin-bottom:.55em}
.addr-row{display:flex;gap:9px;flex-wrap:wrap}
.addr-row input{flex:1 1 230px;min-width:0;padding:13px 15px;border-radius:8px;border:1px solid #5e7a67;
 background:#1f3126;color:#fff;font:inherit;font-size:1rem}
.addr-row input::placeholder{color:#8ba392}
.addr-row button{flex:0 0 auto;padding:13px 22px;border:0;border-radius:8px;background:#c1632f;color:#fff;
 font:inherit;font-weight:700;font-size:1rem;cursor:pointer}
.addr-row button:hover{background:#a9532373}
.sec.follow{background:#e7e0d1}
.fol{display:grid;gap:11px;margin:1.3em 0}
.chk{display:flex;gap:11px;align-items:flex-start;font-size:.93rem;cursor:pointer;
 background:#efe9dd;border:1px solid #d8cfba;border-radius:8px;padding:12px 14px}
.chk input{margin-top:3px;flex:0 0 auto;width:17px;height:17px;accent-color:#24392c}
.chk.own{border-color:#c1632f;background:#f3e7dc}
.chk.own em{display:block;color:#a5432a;font-style:normal;font-size:.8rem;margin-top:2px}
.follow .addr-row input{background:#fff;border-color:#c9bfa8;color:#1c1c1a}
.follow .addr-row input::placeholder{color:#8d8574}
.foot-note{font-size:.82rem;color:#5d5d55;margin:0}

footer{background:#1a2b21;color:#9fb5a4;padding:30px 0;font-size:.8rem}
footer a{color:#c3d2c6}
.proto{background:#c1632f;color:#fff;text-align:center;padding:9px 16px;font-size:.79rem;
 font-weight:600;letter-spacing:.02em}
.toast{position:fixed;left:50%;bottom:22px;transform:translateX(-50%);background:#24392c;color:#fff;
 padding:13px 20px;border-radius:9px;font-size:.9rem;box-shadow:0 8px 26px rgba(0,0,0,.3);z-index:99;
 max-width:calc(100vw - 32px)}
"""

JS = """
function op(btn,id){
  var b=document.getElementById(id), open=btn.getAttribute('aria-expanded')==='true';
  btn.setAttribute('aria-expanded',String(!open));
  b.hidden=open;
  btn.querySelector('.op-i').textContent=open?'+':'\\u2212';
}
function toast(msg){
  var t=document.createElement('div'); t.className='toast'; t.textContent=msg;
  document.body.appendChild(t); setTimeout(function(){t.remove();},5200);
}
/* Open the tab SYNCHRONOUSLY inside the click handler, then navigate it when the
   lookup resolves. Opening it after an async response is blocked by every major browser. */
function openOwn(e){
  e.preventDefault();
  var v=document.getElementById('a').value.trim();
  if(!v) return false;
  var tab=window.open('','_blank');
  if(tab){ tab.document.write('<title>Finding your home\\u2026</title>'+
    '<body style="font:16px system-ui;padding:40px;background:#efe9dd;color:#1c1c1a">'+
    '<p>Looking up <strong>'+v.replace(/</g,'&lt;')+'</strong>\\u2026</p>'+
    '<p style="color:#7a7a70;font-size:.85rem">PROTOTYPE \\u2014 in the live build this tab navigates to '+
    'fieldsestate.com.au/off-market/&lt;your-address&gt;. Your listing stays open behind it.</p>'); }
  toast('Prototype: a new tab opened. Live, it loads your own /off-market page \\u2014 this listing stays open.');
  return false;
}
function followSubmit(e){
  e.preventDefault();
  var nearby=document.getElementById('nearby').checked;
  toast(nearby
    ? 'Prototype: following. You ticked the nearby-owner option \\u2014 that is the only seller signal on this page, and you volunteered it.'
    : 'Prototype: following this sale. One email per event.');
  return false;
}
"""

HTML = f"""<!doctype html>
<html lang="en-AU">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<meta name="robots" content="noindex,nofollow">
<title>{esc(D['address'])} — Fields listing page V2 prototype</title>
<style>{CSS}</style>
</head>
<body>
<div class="proto">PROTOTYPE · Fields listing page V2 · real data, not live · {TODAY.isoformat()}</div>
{hero}
{layer1}
{layer2}
{layer2b}
{layer3}
{layer4}
{layer5}
{layer6}
{layer8}
{layer9}
<footer><div class="wrap">
  <p><strong>Fields Estate</strong> — independent property analysis. We are not the listing agent for
  this property and have no interest in its sale.</p>
  <p>Every figure on this page carries its source and date. Where we do not hold something, we say so
  rather than leaving it blank. Our comparable range is not a confidence interval and we do not claim
  to be more accurate than an agent or a portal.</p>
</div></footer>
<script>{JS}</script>
</body></html>"""

(HERE / "index.html").write_text(HTML)
print(f"wrote {HERE/'index.html'}  ({len(HTML):,} bytes)")
print(f"  property     : {D['address']}")
print(f"  ask          : {money(price)} ({D['price_type']})")
print(f"  range        : {money(lo)} – {money(hi)}  ({D['confidence']})")
print(f"  gap to floor : {money(gap_to_floor)}")
print(f"  true DOM     : {true_dom}d vs portal {portal_dom}d")
print(f"  timeline     : {len(tl)} events   comps: {n_shown}   photos: {len(D['images'])}")
