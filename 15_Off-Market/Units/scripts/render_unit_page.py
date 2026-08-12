#!/usr/bin/env python3
"""render_unit_page.py — the visual PROTOTYPE of a unit off-market page.

Same facts as `render_unit_report.py`, different medium: both consume
`unit_page_data.assemble()` and neither computes anything. If the markdown and the
page ever disagree, that is a bug in the data layer, not in a renderer.

Output is standalone HTML written into 15_Off-Market/Concepts/Unit_Page_Prototype/,
which nginx serves with NO BUILD STEP at
    https://vm.fieldsestate.com.au/concepts/off-market/Unit_Page_Prototype/<slug>.html

⚠ A path on disk is not a deliverable. Will reviews things in a browser, so anything
meant to be looked at has to exist at a URL (see memory `concept_previews_path`).

⚠ NOT THE LIVE PAGE. This is a prototype for judging layout and copy before any of it
is built in React. It carries a visible banner saying so, and `noindex`, because ~14.6k
real off-market URLs are indexed and a stray prototype must never join them.

TYPE + SPACING follow the live V4 page so the two can be compared honestly: the same
serif display face for figures, the same numbered part dividers, the same restraint
about colour. Where this prototype differs visually it should be because the CONTENT
differs, not because the prototype was styled by a different hand.
"""
from __future__ import annotations

import argparse
import datetime as dt
import html
import re
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))

from unit_page_data import assemble, GAPS, card_of      # noqa: E402

OUT = HERE.parent.parent / "Concepts" / "Unit_Page_Prototype"
OUT.mkdir(parents=True, exist_ok=True)
BASE_URL = "https://vm.fieldsestate.com.au/concepts/off-market/Unit_Page_Prototype"


def e(s):
    return html.escape(str(s if s is not None else ""))


def money(v):
    try:
        return f"${float(v):,.0f}"
    except Exception:
        return "—"


def money_m(v):
    try:
        f = float(v)
    except Exception:
        return "—"
    if f >= 1_000_000:
        return f"${f/1_000_000:.2f} million"
    # Sub-million rounded to the nearest thousand: $925,955 is a false precision on a
    # figure whose honest width is +/-19.8%, and it read as noise beside "$1.02 million".
    return f"${round(f/1000)*1000:,.0f}"


def display_address(a):
    """Title-case a SHOUTED address for display, leaving correctly-cased ones alone.

    Two forms exist: `101/60 Riverwalk Avenue, Robina QLD 4226` and
    `137/25 LAKE ORR DRIVE ROBINA QLD 4220`. Rendering the second raw put a shouted H1
    on the page beside a properly-cased one — same product, two voices. Mirrors
    `effectivePropertyAddress()` in src/lib/db.server.ts, including its known cosmetic
    imperfection: MCPHERSON title-cases to Mcpherson, not McPherson.
    """
    a = str(a or "").strip()
    if not a or not a.isupper():
        return a
    out = a.title()
    # State abbreviations must not be title-cased.
    return re.sub(r"\b(Qld|Nsw|Vic|Act|Sa|Wa|Nt|Tas)\b",
                  lambda m: m.group(0).upper(), out)


SUBURB_TAIL = re.compile(
    r"\s+(ROBINA|VARSITY LAKES|BURLEIGH WATERS|Robina|Varsity Lakes|Burleigh Waters)\s*$")


def short_addr(a):
    """`115/60 RIVERWALK AVENUE ROBINA QLD 4226` -> `115/60 Riverwalk Avenue`.

    Two forms exist in the data: comma-separated (`…Avenue, Robina QLD 4226`) and
    shouted with no comma (`…AVENUE ROBINA QLD 4226`). Stripping only the state and
    postcode left "Robina" dangling on the second form, so the same building rendered
    two ways in one table — which reads as a data error to the owner looking at it."""
    a = re.sub(r",?\s*(QLD|Qld)\s*\d{4}\s*$", "", str(a or "")).strip()
    a = a.split(",")[0].strip()
    a = SUBURB_TAIL.sub("", a).strip()
    return a.title() if a.isupper() else a


CSS = """
:root{
  --ink:#1a1a18; --muted:#6b6b63; --line:#e0ddd4; --bg:#faf9f6;
  --panel:#fff; --accent:#7c4a2d; --soft:#f2efe7; --good:#2f5d3f;
}
*{box-sizing:border-box}
body{margin:0;background:var(--bg);color:var(--ink);
  font:16px/1.65 -apple-system,BlinkMacSystemFont,"Segoe UI",Helvetica,Arial,sans-serif;
  -webkit-font-smoothing:antialiased}
.wrap{max-width:720px;margin:0 auto;padding:0 22px}
.serif{font-family:"Iowan Old Style","Palatino Linotype",Palatino,Georgia,serif}
.banner{background:#2b2a26;color:#f3f0e8;font-size:13px;padding:9px 0;text-align:center;
  letter-spacing:.02em}
.banner b{color:#f7d9a0}
header.rep{border-bottom:1px solid var(--line);padding:26px 0 20px;margin-bottom:8px}
.eyebrow{font-size:11px;letter-spacing:.16em;text-transform:uppercase;color:var(--muted)}
h1{font-size:30px;line-height:1.22;margin:10px 0 6px;font-weight:600}
.sub{color:var(--muted);font-size:15px}
.facts{display:flex;flex-wrap:wrap;gap:8px 18px;margin:16px 0 0;font-size:14px;color:var(--muted)}
.facts b{color:var(--ink);font-weight:600}
section{padding:34px 0;border-top:1px solid var(--line)}
.part{display:flex;align-items:baseline;gap:14px;margin:0 0 6px}
.part .num{font-size:40px;color:var(--accent);opacity:.55;font-weight:600;line-height:1}
.part .lbl{font-size:11px;letter-spacing:.16em;text-transform:uppercase;color:var(--muted)}
h2{font-size:23px;line-height:1.3;margin:14px 0 10px;font-weight:600}
h3{font-size:17px;margin:26px 0 8px;font-weight:600}
p{margin:0 0 14px}
.lead{font-size:18px}
.panel{background:var(--panel);border:1px solid var(--line);border-radius:12px;
  padding:22px;margin:18px 0}
.range{font-size:33px;letter-spacing:-.01em;margin:2px 0 4px;font-weight:600}
.point{font-size:15px;color:var(--muted)}
.point b{color:var(--ink)}
table{width:100%;border-collapse:collapse;font-size:14px;margin:10px 0 6px}
th{text-align:left;font-size:11px;letter-spacing:.1em;text-transform:uppercase;
  color:var(--muted);font-weight:600;padding:0 8px 8px 0;border-bottom:1px solid var(--line)}
td{padding:9px 8px 9px 0;border-bottom:1px solid var(--soft)}
td.n,th.n{text-align:right}
.scroll{overflow-x:auto;-webkit-overflow-scrolling:touch}
.note{font-size:13px;color:var(--muted);margin-top:8px}
.kv{display:grid;grid-template-columns:1fr auto;gap:9px 16px;font-size:15px;margin:6px 0 0}
.kv div:nth-child(even){text-align:right;font-weight:600}
.kv div:nth-child(odd){color:var(--muted)}
.gap{background:#fdf6e8;border-left:3px solid #d8a44a;padding:11px 14px;margin:14px 0;
  font-size:13.5px;color:#5c4a26;border-radius:0 8px 8px 0}
.gap b{color:#3d3116}
.derived{background:#eef3ee;border-left:3px solid var(--good);padding:11px 14px;margin:14px 0;
  font-size:13.5px;color:#2c4433;border-radius:0 8px 8px 0}
.refuse{border:1px solid var(--line);border-radius:12px;padding:22px;background:var(--panel)}
.refuse h3{margin-top:0}
ul.poi{list-style:none;padding:0;margin:8px 0 0}
ul.poi li{display:flex;justify-content:space-between;padding:7px 0;
  border-bottom:1px solid var(--soft);font-size:15px}
ul.poi li span:last-child{color:var(--muted);font-variant-numeric:tabular-nums}
footer{padding:34px 0 60px;color:var(--muted);font-size:12.5px;border-top:1px solid var(--line)}
@media (max-width:520px){h1{font-size:25px}.range{font-size:27px}.part .num{font-size:32px}}
"""


def part(n, label, blurb):
    return (f'<div class="part"><div class="num serif">{n}</div>'
            f'<div class="lbl">{e(label)}</div></div>'
            f'<p class="sub">{e(blurb)}</p>')


def gapbox(code, extra=""):
    return (f'<div class="gap"><b>GAP [{e(code)}]</b> — {e(GAPS.get(code, ""))}.'
            + (f' {e(extra)}' if extra else "") + '</div>')


def build_html(d):
    a = d["address"]
    cx = d["complex"] or {}
    mkt = d["market"] or {}
    val = d["valuation"] or {}
    S = []
    W = S.append

    W('<div class="banner">PROTOTYPE — not the live page, not published. '
      'Rendered from live data to review layout and copy. '
      '<b>Bands are measured per suburb on a leakage-free backtest.</b></div>')
    W('<div class="wrap">')

    # ---- header
    W('<header class="rep">')
    W('<div class="eyebrow">Private property report</div>')
    W(f'<h1 class="serif">{e(display_address(a))}</h1>')
    facts = []
    if d["bedrooms"]:
        facts.append(f'<span><b>{d["bedrooms"]}</b> bedrooms</span>')
    if d["bathrooms"]:
        facts.append(f'<span><b>{d["bathrooms"]}</b> bathrooms</span>')
    if d["floor_area"]:
        facts.append(f'<span><b>{int(d["floor_area"])} m²</b> internal</span>')
    elif d["floor_area_imputed"]:
        facts.append(f'<span><b>~{d["floor_area_imputed"]["value"]} m²</b> internal</span>')
    if facts:
        W(f'<div class="facts">{"".join(facts)}</div>')
    W(f'<p class="sub" style="margin-top:14px">Updated {dt.date.today():%A %-d %B %Y}</p>')
    W('</header>')

    # ---- the building
    W('<section>')
    W('<div class="eyebrow">The building</div>')
    if cx:
        name = cx.get("complex_name") or "an unnamed scheme"
        kind = {"building_units": "an apartment building with shared common property",
                "group_title": "a villa and townhouse complex",
                "survey_plan": "a strata complex"}.get(cx.get("subtype"), "a complex")
        W(f'<h2>One of {e(d["scheme_size"])} homes in {e(name)}</h2>')
        W(f'<p class="lead">This home sits in {e(kind)}'
          + (f', community titles scheme {e(cx["cms_number"])}' if cx.get("cms_number") else "")
          + '.</p>')
        if cx.get("storeys_band"):
            W(f'<p>The buildings stand <b>{e(cx["storeys_band"])}</b>'
              + (f' (about {cx["building_height_m"]:.0f} m)' if cx.get("building_height_m") else "")
              + '. Derived from Queensland LiDAR captured in 2022 — accurate to within one '
                'storey nine times in ten, which is why it is a band and not a number.</p>')
        if cx.get("lift_inferred") == "yes":
            W('<p>At that height it will have a lift — <b>inferred from the building, not '
              'recorded</b>. No source we hold publishes lift presence.</p>')
        if cx.get("common_property_sqm"):
            # ⚠ Building-format schemes have no per-apartment cadastral polygon, so
            # lot_area_median_sqm is absent — printing "the typical lot is 0 m²" reads
            # as broken data. Only state it when the cadastre actually holds it.
            # ⚠ ALSO SUPPRESS IMPLAUSIBLY SMALL LOTS. In a building-format scheme the
            # cadastral "lot" can be a nominal footprint — Vantage Burleigh reported 9 m²,
            # which reads as broken data next to a 20-storey tower. Under 30 m² it is a
            # cadastral artifact, not a dwelling.
            lot_med = cx.get("lot_area_median_sqm")
            tail = (f', and the typical lot in it is {int(lot_med)} m²'
                    if lot_med and lot_med >= 30 else '')
            W(f'<p>The scheme holds <b>{int(cx["common_property_sqm"]):,} m²</b> of common '
              f'property{tail}.</p>')
        W('<p class="note">Scheme detail from the Queensland cadastre (CC-BY 4.0) — '
          '© State of Queensland. Dwelling count is ours: the cadastre records base '
          'parcels, not one polygon per apartment.</p>')
    else:
        W('<h2>We could not match this home to a scheme</h2>')
        W('<p>It carries no cadastral lot and plan, so the complex layer cannot reach it.</p>')
    if d["floor_area_imputed"]:
        i = d["floor_area_imputed"]
        W(f'<div class="derived"><b>Derived figure.</b> The ~{i["value"]} m² above is the '
          f'median of {i["n"]} same-bedroom homes in this scheme — not a measured area for '
          f'this home. {e(i["accuracy"])}.</div>')
    if "C2" in d["gaps"]:
        W(gapbox("C2"))
    W(gapbox("C3", "Lift is inferred where the building is tall enough."))
    W('</section>')

    # ---- part 01 valuation
    W('<section>')
    W(part("01", "The valuation",
           "What the sales in this building support, and how far the method has been tested."))
    if val.get("method") == "same_complex_comparables":
        tier = {"same_complex_same_beds":
                f'other {d["bedrooms"]}-bedroom homes that have sold in this same scheme',
                "same_complex_any_beds": "other homes that have sold in this same scheme",
                "same_subtype_same_beds_suburb":
                f'{d["bedrooms"]}-bedroom homes of the same kind sold across {d["suburb"]}'}
        W('<div class="panel">')
        W('<div class="eyebrow">What the sales support</div>')
        W(f'<div class="range serif">{e(money_m(val["low"]))} – {e(money_m(val["high"]))}</div>')
        W(f'<div class="point">The evidence centres around <b>{e(money_m(val["point"]))}</b> — '
          'rounded deliberately, because the width is the honest part.</div>')
        W('</div>')
        W(f'<p>It is built from <b>{val["n_comps"]}</b> '
          f'{e(tier.get(val.get("tier"), "comparable sales"))}'
          + (f' ({val["n_available"]} were available)' if val.get("n_available", 0) > val["n_comps"] else "")
          + '.</p>')
        if val.get("tier") == "same_subtype_same_beds_suburb":
            W('<div class="gap"><b>Worth saying plainly.</b> No sale in this home\'s own '
              'scheme could be used, so this range comes from similar homes elsewhere in the '
              'suburb. That is a weaker comparison than a sale in the same building.</div>')
        W('<h3>The sales it is built from</h3>')
        W('<div class="scroll"><table><thead><tr><th>Sold</th><th>Address</th>'
          '<th class="n">Beds</th><th class="n">Sold for</th>'
          '<th class="n">Brought to today</th></tr></thead><tbody>')
        for c in val["comparables"][:8]:
            W(f'<tr><td>{e(c["date"][:7])}</td><td>{e(short_addr(c["address"]))}</td>'
              f'<td class="n">{e(c.get("beds") or "—")}</td>'
              f'<td class="n">{e(money(c["sold"]))}</td>'
              f'<td class="n">{e(money(c["adjusted"]))}</td></tr>')
        W('</tbody></table></div>')
        drops = []
        if val.get("dropped_too_old"):
            drops.append(f'{val["dropped_too_old"]} older sale'
                         f'{"s" if val["dropped_too_old"] != 1 else ""} left out because '
                         'bringing them to today would have taken more than a 60% uplift — '
                         'at that distance the figure is the index, not the sale')
        if val.get("dropped_undeflatable"):
            drops.append(f'{val["dropped_undeflatable"]} the index could not reach')
        W(f'<p class="note">Each sale is brought to today using the {e(d["suburb"])} '
          'attached-dwelling index, bedroom-matched — not the house index'
          + (', with ' + e(' and '.join(drops)) if drops else '')
          + '.</p>')
        W('<h3>How wide the range is, and why</h3>')
        acc = val.get("accuracy") or {}
        if val.get("publishable") and acc:
            W(f'<p>The width is <b>±{val["band_pct"]}%</b>. We set it by testing this method '
              f'against <b>{acc["n"]:,}</b> {e(d["suburb"])} attached sales, without letting '
              f'it see the sale it was predicting — and widening the band until four in five '
              f'landed inside.</p>')
            W('<div class="panel"><div class="kv">')
            W(f'<div>Median error</div><div>{acc["median"]}%</div>')
            W(f'<div>Within 10% of the eventual sale</div><div>{acc["within10"]}%</div>')
            W(f'<div>Sales tested</div><div>{acc["n"]:,}</div>')
            W('</div></div>')
            W('<p class="note">An empirical band from observed error — <b>not</b> a statistical '
              'confidence interval. It is as narrow as the evidence earns; narrowing it '
              'further would not make the estimate better, only the claim less true.</p>')
        else:
            W(f'<div class="gap"><b>Not fit to publish for this suburb.</b> '
              f'{e(val.get("band_basis", ""))} '
              + (f'On this cohort the method landed within 10% on only {acc["within10"]}% of '
                 f'homes (n={acc["n"]:,}), against 68% in Robina. The range above is shown '
                 f'here for review; it should not go on a live page until the sample and the '
                 f'accuracy improve.' if acc else '')
              + '</div>')
    else:
        W('<div class="refuse">')
        W('<h3>We are not going to put a figure on this home</h3>')
        W(f'<p>{e(val.get("explain", ""))}</p>')
        if val.get("decline_reason") == "comparables_too_old":
            W(f'<p>There have been sales in this scheme, but the most recent usable one is '
              f'far enough back that carrying it to today would take more than a 60% uplift. '
              f'That figure would be the index doing the work, not the sale — so we are not '
              f'going to publish it as though it were evidence.</p>')
        W('<p class="note">A range built from homes that are not genuinely comparable would '
          'be worse than no range. As more sales settle in this scheme, that can change — '
          'this page is rebuilt nightly.</p>')
        W('</div>')
    W('</section>')

    # ---- part 02 the market
    W('<section>')
    W(part("02", "The market it sits in",
           "Units and townhouses in this suburb — not the house market."))
    if mkt.get("latest_rolling_median"):
        W('<div class="panel"><div class="kv">')
        W(f'<div>Median attached price, {e(d["suburb"])}</div>'
          f'<div>{e(money(mkt["latest_rolling_median"]))}</div>')
        if mkt.get("yoy_pct") is not None:
            W(f'<div>Change on a year earlier</div><div>{mkt["yoy_pct"]:+.1f}%</div>')
        if mkt.get("median_days_on_market"):
            W(f'<div>Median days on market</div><div>{mkt["median_days_on_market"]}</div>')
        W(f'<div>Attached homes for sale now</div><div>{mkt.get("active_listings", "—")}</div>')
        W('</div></div>')
        W('<div class="gap"><b>What this median is and is not.</b> It covers units, '
          'apartments, townhouses, villas and duplexes together, so it moves with the mix of '
          'what sold as well as with price. On Robina it rose 35% over two years while '
          '2-bedroom homes rose 18% and 3-bedroom 29% — faster than either. It is context '
          'for a decision, not a second estimate of this home, and the valuation above uses '
          'the bedroom-matched series instead.</div>')
        W(f'<p class="note">{e(mkt.get("basis", ""))}. Medians only — sale volume is not '
          'published, because Domain\'s sold capture misses an estimated 40–50% of '
          'transactions.</p>')
    W('</section>')

    # ---- part 03 the location
    prox = d["proximity"] or {}
    if prox:
        W('<section>')
        W(part("03", "At the doorstep", "What is within walking distance."))
        rows = []
        seen = set()
        shown = 0
        W('<ul class="poi">')
        for _k, v in prox.items():
            if not (isinstance(v, dict) and v.get("name")) or v["name"] in seen:
                continue
            seen.add(v["name"])
            dm = v.get("distance_m") or v.get("m")
            # The heading says "within walking distance", so anything beyond ~1.2 km
            # makes the section a lie. Miami Beach at 5,697 m was rendering under it.
            if not dm or dm > 1200:
                continue
            W(f'<li><span>{e(v["name"])}</span><span>{int(dm)} m</span></li>')
            shown += 1
            if shown >= 6:
                break
        W('</ul>')
        W('</section>')

    # ---- dispersion (reused verbatim from the live engine)
    disp = d["dispersion_card"]
    if disp:
        W('<section>')
        W('<div class="eyebrow">The other numbers</div>')
        W('<h2>Why three sites can give you three different values</h2>')
        for k in ("setup", "test", "finding", "means"):
            if disp.get(k):
                cls = ' class="lead"' if k == "finding" else ""
                W(f'<p{cls}>{e(disp[k])}</p>')
        W('</section>')

    W('<section>')
    W(gapbox("E5"))
    W(gapbox("G1"))
    W('</section>')

    W('<footer>')
    W(f'Prototype rendered {dt.date.today():%-d %B %Y} from live data · '
      f'slug <code>{e(d["slug"])}</code> · dwelling class {e(d["dwelling_class"])} · '
      f'valuation method {e(val.get("method"))}'
      + (f' / {e(val.get("tier"))}' if val.get("tier") else "") + '<br>'
      'Fields Estate — internal review artifact. Not published, not indexed.')
    W('</footer>')
    W('</div>')

    title = f"{short_addr(a)} — unit page prototype"
    return (f'<!doctype html><html lang="en-AU"><head><meta charset="utf-8">'
            f'<meta name="viewport" content="width=device-width,initial-scale=1">'
            f'<meta name="robots" content="noindex,nofollow">'
            f'<title>{e(title)}</title><style>{CSS}</style></head>'
            f'<body>{"".join(S)}</body></html>')


def main():
    ap = argparse.ArgumentParser()
    g = ap.add_mutually_exclusive_group(required=True)
    g.add_argument("--slug")
    g.add_argument("--address")
    g.add_argument("--slugs", nargs="+")
    args = ap.parse_args()

    targets = args.slugs or [args.slug or args.address]
    built = []
    for t in targets:
        try:
            d = assemble(slug=t) if (args.slug or args.slugs) else assemble(address=t)
        except Exception as ex:
            print(f"  FAIL {t}: {type(ex).__name__}: {ex}", file=sys.stderr)
            continue
        p = OUT / f"{d['slug']}.html"
        p.write_text(build_html(d))
        built.append((d, p))
        print(f"  {p.name}  ({len(d['gaps'])} gaps, {d['valuation'].get('method')})")

    if built:
        idx = ['<!doctype html><html><head><meta charset="utf-8">',
               '<meta name="robots" content="noindex,nofollow">',
               '<title>Unit page prototypes</title><style>', CSS, '</style></head><body>',
               '<div class="banner">PROTOTYPE INDEX — internal review only</div>',
               '<div class="wrap"><header class="rep">',
               '<div class="eyebrow">Fields Estate</div>',
               '<h1 class="serif">Unit page prototypes</h1>',
               '<p class="sub">Attached-dwelling off-market pages, rendered from live data. '
               'Chosen to cover different failure modes: a tower, a low-rise, a townhouse '
               'group, and a home the method refuses to value.</p></header><section>']
        for d, p in built:
            cx = d["complex"] or {}
            v = d["valuation"]
            # ⚠ RANGE, NOT A POINT. CLAUDE.md Rule 5: comparable ranges, never a single
            # figure as the headline number. The index is internal, but the habit has to
            # be the same in both places or the wrong one gets copied into React.
            # money_m only converts above $1M, so a raw $925,955 sat beside
            # "$1.02 million" in the same list — round the sub-million case too.
            rng = (f'{money_m(v["low"])} – {money_m(v["high"])}'
                   if v.get("low") else "no figure — the method declined")
            bits = [f'{d["scheme_size"]} homes' if d["scheme_size"] else "",
                    cx.get("storeys_band") or "", rng]
            idx.append(f'<p style="margin-bottom:18px"><a href="{e(p.name)}" '
                       f'style="font-size:18px;color:var(--accent)">{e(short_addr(d["address"]))}</a>'
                       f'<br><span class="note">{e(" · ".join(x for x in bits if x))}</span></p>')
        idx.append('</section></div></body></html>')
        (OUT / "index.html").write_text("".join(idx))
        print(f"\n  index -> {BASE_URL}/index.html")
    return 0


if __name__ == "__main__":
    sys.exit(main())
