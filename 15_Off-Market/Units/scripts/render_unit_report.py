#!/usr/bin/env python3
"""render_unit_report.py — address -> markdown report for an attached dwelling.

WHY THIS EXISTS
---------------
The unit page's copy is the product. Reviewing it as a deploy is slow and expensive;
reviewing it as a document is neither. This renders the FULL prose of a unit page in
the same section order as the live house page
(`/off-market/27-huntingdale-crescent-robina`), so the writing can be judged and
rewritten long before any of it reaches React.

Sections either render real content or emit an explicit marker naming the workstream
in UNITS_DEVELOPMENT_PLAN.md that closes them:

    > **GAP [E2]** - no storeys band ...

so the document doubles as a progress tracker. Done = a sampled report with no GAPs.

THE ONE ARCHITECTURAL RULE (plan item I4)
-----------------------------------------
This renders what the engines return; it must never compute a fact of its own.
Facts come from:
    fact_bundle.build() / emit_v4()   - the existing deck engine (POI, rarity, copy)
    Gold_Coast.complexes              - ingest_complexes.py      (E1)
    Gold_Coast.unit_market_series     - build_unit_market_series.py (D1)
    unit_valuation.UnitValuer         - unit_valuation.py        (F3/F4)
If report and page ever disagree, that is a bug in one of those, not here.

USAGE
    python3 render_unit_report.py --address "1/3 Laurel Oak Drive, Robina"
    python3 render_unit_report.py --slug 101-60-riverwalk-avenue-robina
    python3 render_unit_report.py --sample 8 --summary
"""
from __future__ import annotations

import argparse
import datetime as _dt
import json
import re
import sys
import traceback
from pathlib import Path

HERE = Path(__file__).resolve().parent
UNITS = HERE.parent
ROOT = UNITS.parent.parent
ENGINE = ROOT / "15_Off-Market" / "Page_Redesign_V2"
for p in (str(ROOT), str(ENGINE), str(HERE)):
    if p not in sys.path:
        sys.path.insert(0, p)

try:
    from shared.env import load_env
    load_env()
except Exception:
    pass

from shared.dwelling_type import classify_dwelling          # noqa: E402
from shared.db import get_client                            # noqa: E402
from unit_valuation import UnitValuer                       # noqa: E402

OUT_DIR = UNITS / "artifacts" / "unit_reports"
OUT_DIR.mkdir(parents=True, exist_ok=True)
CORE_SUBURBS = ["robina", "varsity_lakes", "burleigh_waters"]

GAPS = {
    "B2": "dwelling_class is not persisted; classification is computed live here",
    "C2": "no floor area recorded and none imputable from this scheme",
    "C3": "no complex amenity data — lift, pool, gym, secure parking (structuredFeatures[] not stored)",
    "E2": "no storeys band — QLD LiDAR buildings layer not yet ingested",
    "E5": "no body-corporate levy — lawful only as an owner's agent (Phase 4)",
    "G1": "copy below is the house voice; copy_units_v4.yaml does not exist yet",
    "G2": "scarcity cohort is untyped — this counts the DETACHED HOUSE market",
    "G5": "buyer archetype is a detached-house persona",
}

_SKIP_KEYS = {"type", "n", "_canon", "next"}
_LEAD = ("answer", "questions_intro", "headline", "range", "anchor_intro", "anchor",
         "anchor_note", "tier_caveat")


def gap(code, extra=""):
    line = f"> **GAP [{code}]** — {GAPS.get(code, 'unspecified')}."
    if extra:
        line += f"\n>\n> {extra}"
    return line + "\n"


def money(v):
    try:
        return f"${float(v):,.0f}"
    except Exception:
        return None


def money_m(v):
    try:
        f = float(v)
    except Exception:
        return None
    if f >= 1_000_000:
        return f"${f/1_000_000:.2f} million"
    # Round sub-million to the nearest thousand — $925,955 is false precision on a
    # figure whose honest width is ±19.8%. Must match render_unit_page.money_m or the
    # two surfaces show a reader different numbers for the same home; that divergence
    # was caught by check_renderer_consistency.py, which is why it exists.
    return f"${round(f/1000)*1000:,.0f}"


def _norm(s):
    return re.sub(r"[^a-z0-9]+", " ", (s or "").lower()).strip()


def effective_address(d):
    return d.get("address") or d.get("complete_address") or d.get("street_address") or ""


PROJ = {"url_slug": 1, "address": 1, "complete_address": 1, "street_address": 1,
        "property_type": 1, "classified_property_type": 1, "PLAN": 1, "LOT": 1,
        "scraped_data.features.property_type": 1, "scraped_data_v2.property_type": 1,
        "PROPERTY_NAME": 1, "UNIT_NUMBER": 1, "bedrooms": 1, "bathrooms": 1,
        "car_spaces": 1, "floor_area_sqm": 1, "internal_living_area_sqm": 1,
        "enriched_data.floor_area_sqm": 1, "enriched_data.transactions": 1,
        "complex_plan": 1, "complex_cms": 1, "complex_name_cadastre": 1,
        "complex_lot_count": 1, "complex_subtype": 1, "listing_status": 1}


def resolve(address, slug):
    gc = get_client()["Gold_Coast"]
    if slug:
        for s in CORE_SUBURBS:
            d = gc[s].find_one({"url_slug": slug}, PROJ)
            if d:
                return d, s
        return None, None
    want = _norm(address)
    head = address.split(",")[0].strip()
    for s in CORE_SUBURBS:
        for field in ("address", "complete_address", "street_address"):
            for d in gc[s].find({field: {"$regex": re.escape(head), "$options": "i"}},
                                PROJ).limit(60):
                if want in _norm(effective_address(d)):
                    return d, s
    return None, None


def card_of(cards, t):
    for c in cards:
        if c.get("type") == t:
            return c
    return None


def render_card(c):
    if not c:
        return ""
    order = [k for k in _LEAD if k in c] + [k for k in c if k not in _LEAD and k not in _SKIP_KEYS]
    out = []
    for k in order:
        v = c.get(k)
        if v is None or k in _SKIP_KEYS:
            continue
        if isinstance(v, str):
            if v.strip():
                out.append(v.strip())
        elif isinstance(v, (list, tuple)):
            items = [str(i).strip() for i in v if str(i).strip()]
            if items:
                out.append("\n".join(f"- {i}" for i in items))
        elif isinstance(v, dict):
            body = v.get("body") or ""
            if body:
                out.append(f"**{v.get('label') or k.replace('_',' ')}** — {body}")
    return "\n\n".join(out)


def short_addr(a):
    """`220/60 Riverwalk Avenue, Robina QLD 4226` -> `220/60 Riverwalk Avenue`.
    Truncating at a fixed width instead produced `...Robina QLD 42`, which reads as
    a data error to anyone looking at their own building."""
    a = re.sub(r",?\s*(QLD|Qld|NSW|VIC)\s*\d{4}\s*$", "", str(a or "")).strip()
    a = a.split(",")[0].strip()
    return re.sub(r"\s+", " ", a).title() if a.isupper() else a


def floor_of(d):
    for k in ("floor_area_sqm", "internal_living_area_sqm"):
        v = d.get(k)
        if v:
            return v
    return (d.get("enriched_data") or {}).get("floor_area_sqm")


# ---------------------------------------------------------------------------
def build_report(doc, suburb, bundle, cards, notes, gc):
    addr = effective_address(doc)
    disp = (suburb or "").replace("_", " ").title()
    cls = classify_dwelling({**doc, "street_address": addr})
    b = bundle or {}
    L, W = [], None
    L = []
    W = L.append

    cx = gc["complexes"].find_one({"_id": f"{suburb}:{doc.get('complex_plan')}"}) if doc.get("complex_plan") else None
    mkt = gc["unit_market_series"].find_one({"_id": suburb}) or {}
    V = UnitValuer(gc, suburb)
    val = V.value(doc)
    imputed = V.impute_floor_area(doc)
    floor = floor_of(doc)

    W(f"# {addr}")
    W("")
    W(f"*Private property report · rendered {_dt.date.today():%A %-d %B %Y}*")
    W("")
    W("> **Harness output — not published anywhere.** Rendered from the live engines so the "
      "prose can be reviewed as a document. GAP markers name the workstream that closes them.")
    W("")

    # ---------------- 0 · header ------------------------------------------
    W("## 0 · The header")
    W("")
    bits = []
    if doc.get("bedrooms"):
        bits.append(f"{doc['bedrooms']} bedrooms")
    if doc.get("bathrooms"):
        bits.append(f"{doc['bathrooms']} bathrooms")
    if floor:
        bits.append(f"{int(floor)} m² internal")
    elif imputed:
        bits.append(f"~{imputed['value']} m² internal *(derived)*")
    W(f"**{addr}**")
    W("")
    W(" · ".join(bits) if bits else "_no attributes recorded_")
    W("")
    if cx:
        who = cx.get("complex_name") or "an unnamed scheme"
        n = (cx.get("dwellings_in_scheme_data") or cx.get("scheme_lot_count")
             or cx.get("lot_count"))
        kind = {"building_units": "an apartment building with shared common property",
                "group_title": "a villa and townhouse complex",
                "survey_plan": "a strata complex"}.get(cx.get("subtype"), "a complex")
        W(f"This home is one of **{n} homes** in **{who}** — {kind}"
          + (f", community titles scheme {cx['cms_number']}" if cx.get("cms_number") else "") + ".")
        W("")
        if cx.get("storeys_band"):
            W(f"The buildings in it stand **{cx['storeys_band']}**"
              + (f" (about {cx['building_height_m']:.0f} m)" if cx.get("building_height_m") else "")
              + ". Derived from Queensland LiDAR building outlines captured in 2022 — "
                "accurate to within one storey nine times in ten, which is why it is "
                "stated as a band rather than a number.")
            W("")
        if cx.get("lift_inferred") == "yes":
            W("At that height it will have a lift — **inferred from the building, not "
              "recorded**; no source we hold publishes lift presence.")
            W("")
        if cx.get("lot_area_median_sqm"):
            W(f"The typical lot in this scheme is {int(cx['lot_area_median_sqm'])} m²"
              + (f", and the scheme holds {int(cx['common_property_sqm']):,} m² of common property"
                 if cx.get("common_property_sqm") else "") + ".")
            W("")
        W("*Source: Queensland cadastre (CC-BY 4.0) — © State of Queensland.*")
        W("")
    else:
        W(gap("E2", "No scheme could be matched for this dwelling — it has no cadastral "
                    "LOT/PLAN, so the complex layer cannot reach it."))
    if imputed and not floor:
        W(f"> **Derived figure.** The {imputed['value']} m² above is the median of "
          f"{imputed['n']} same-bedroom dwellings in this scheme, not a measured area for "
          f"this home. Method error 5.2% median on leave-one-out testing.")
        W("")
    elif not floor and not imputed:
        W(gap("C2"))
    if not (cx and cx.get("storeys_band")):
        W(gap("E2"))
    if not cx or not cx.get("lift_inferred"):
        W(gap("C3"))
    else:
        W(gap("C3", "Lift is inferred above; pool, gym, secure parking and on-site "
                    "management are still unknown."))
    W("---")
    W("")

    # ---------------- 1 · what's changed ----------------------------------
    W("## 1 · The last six months — what's changed recently")
    W("")
    if mkt.get("latest_rolling_median"):
        yoy = mkt.get("yoy_pct")
        W(f"**{mkt['latest_period']}** — the median price for an attached dwelling in "
          f"{disp} stands at **{money(mkt['latest_rolling_median'])}** on a 12-month rolling "
          f"basis" + (f", {yoy:+.1f}% on a year earlier" if yoy is not None else "") + ".")
        W("")
        if mkt.get("median_days_on_market"):
            W(f"Units and townhouses here are taking a median of "
              f"**{mkt['median_days_on_market']} days** to sell "
              f"(n={mkt['dom_sample']}), and **{mkt['active_listings']}** are on the market now.")
            W("")
        W("> **What this median is and is not.** It covers units, apartments, townhouses, "
          "villas and duplexes together, so it moves with the mix of what sold as well as "
          "with price. Measured on Robina it rose 35% over two years while 2-bedroom homes "
          "rose 18% and 3-bedroom 29% — faster than either, because the mix shifted toward "
          "larger dwellings. It is context for a decision, not a second estimate of this "
          "home, and the valuation above uses the bedroom-matched series instead.")
        W("")
        W(f"*{mkt['basis']}. Medians only — sale volume is not published, because Domain's "
          f"sold capture misses an estimated 40–50% of transactions.*")
        W("")
    else:
        W(gap("D1"))
    W("---")
    W("")

    # ---------------- 2 · Part 01 the valuation ---------------------------
    W("## 2 · Part 01 — The valuation")
    W("")
    if val.get("method") == "same_complex_comparables":
        tier_words = {
            "same_complex_same_beds": f"other {doc.get('bedrooms')}-bedroom homes that have sold in this same scheme",
            "same_complex_any_beds": "other homes that have sold in this same scheme",
            "same_subtype_same_beds_suburb": f"{doc.get('bedrooms')}-bedroom homes of the same kind that have sold across {disp}",
        }
        W("### What the sales support")
        W("")
        W(f"**{money_m(val['low'])} – {money_m(val['high'])}**")
        W("")
        W(f"The evidence centres around **{money_m(val['point'])}** — rounded deliberately, "
          f"because the width is the honest part.")
        W("")
        W(f"It is built from **{val['n_comps']}** {tier_words.get(val['tier'], 'comparable sales')}"
          f"{f' ({val[chr(110)+chr(95)+chr(97)+chr(118)+chr(97)+chr(105)+chr(108)+chr(97)+chr(98)+chr(108)+chr(101)]} were available)' if val.get('n_available',0) > val['n_comps'] else ''}.")
        W("")
        if val["tier"] == "same_subtype_same_beds_suburb":
            W("> **Worth saying plainly:** no sale in this home's own scheme could be used, so "
              "this range comes from similar homes elsewhere in the suburb. That is a weaker "
              "comparison than a sale in the same building, and the figure should be read as such.")
            W("")
        W("### The sales it is built from")
        W("")
        W("| Sold | Address | Beds | Sold for | Brought to today |")
        W("|---|---|---|---:|---:|")
        for c in val["comparables"][:8]:
            W(f"| {c['date'][:7]} | {short_addr(c['address'])} | {c['beds'] or '—'} | "
              f"{money(c['sold'])} | {money(c['adjusted'])} |")
        W("")
        W(f"*Each sale is brought to today using the {disp} attached-dwelling price index — "
          f"not the house index. Sales the index cannot reach are dropped"
          + (f" ({val['dropped_undeflatable']} here)" if val.get("dropped_undeflatable") else "")
          + ", never carried at face value.*")
        W("")
        W("### How wide the range is, and why")
        W("")
        W(f"The published width is ±{val['band_pct']}%.")
        W("")
        W(f"> ⚠ **Not publishable yet.** {val['band_basis']}")
        W("")
    else:
        W("### We are not going to put a figure on this home")
        W("")
        W(val.get("explain", ""))
        W("")
        W(f"*Decline reason: `{val.get('decline_reason')}`. Tiers attempted: "
          f"{', '.join(f'{t}={n}' for t, n in val.get('tried', []))}.*")
        W("")
        W("> This is the correct output, not a hole — a range built from homes that are not "
          "genuinely comparable would be worse than no range. The page should say so and "
          "explain what would change it.")
        W("")
    for t, label in (("dispersion", "Why three sites can give three different values"),):
        c = card_of(cards, t)
        if c:
            W(f"### {label}")
            W("")
            W(render_card(c))
            W("")
    W("---")
    W("")

    # ---------------- 3 · Part 02 the home itself -------------------------
    W("## 3 · Part 02 — The home itself")
    W("")
    if cx:
        n = (cx.get("dwellings_in_scheme_data") or cx.get("scheme_lot_count")
             or cx.get("lot_count") or 0)
        if n >= 2:
            W(f"### Where it sits in {cx.get('complex_name') or 'the scheme'}")
            W("")
            W(f"There are **{n}** lots in this scheme. That is the number a buyer is really "
              f"choosing between — the closest substitute for this home is another home in "
              f"this building, not a house down the road.")
            W("")
    prox = (b.get("proximity") or {})
    if prox:
        W("### At the doorstep")
        W("")
        seen_poi = set()
        for k, v in prox.items():
            if not (isinstance(v, dict) and v.get("name")):
                continue
            if v["name"] in seen_poi:      # same place, two categories
                continue
            seen_poi.add(v["name"])
            dm = v.get("distance_m") or v.get("m")
            W(f"- {v['name']}" + (f" — {int(dm)}m" if dm else ""))
            if len(seen_poi) >= 6:
                break
        W("")
    bc = card_of(cards, "buyer")
    if bc:
        W("### The buyer")
        W("")
        W(render_card(bc))
        W("")
        W(gap("G5", "Rendered above verbatim from the house engine. For this dwelling it is "
                    "the wrong persona — note any promise of a yard, block or backyard."))
    sc = b.get("scarcity") or {}
    if sc.get("active_total"):
        W(gap("G2", f"Engine rarity figures for this home: {sc.get('active_matching')} of "
                    f"{sc.get('active_total')}. That denominator is the detached-house active "
                    f"pool. The attached equivalent is {mkt.get('active_listings','?')} on the "
                    f"market in {disp}."))
    W(gap("E5"))
    W("---")
    W("")

    # ---------------- 4 · Part 03 where that leaves you -------------------
    W("## 4 · Part 03 — Where that leaves you")
    W("")
    if mkt.get("latest_rolling_median"):
        W("### The market a move would happen in")
        W("")
        W("| | |")
        W("|---|---|")
        W(f"| Median attached price, {disp} | **{money(mkt['latest_rolling_median'])}** "
          f"({mkt['latest_period']}, 12-month rolling) |")
        if mkt.get("yoy_pct") is not None:
            W(f"| Change on a year earlier | {mkt['yoy_pct']:+.1f}% |")
        if mkt.get("median_days_on_market"):
            W(f"| Median days on market | {mkt['median_days_on_market']} (n={mkt['dom_sample']}) |")
        W(f"| Attached homes for sale now | {mkt['active_listings']} |")
        W("")
        q = [r for r in (mkt.get("quarterly") or []) if not r.get("thin")]
        recent = [r for r in q if r["period"] >= "2024-Q1"
                  and r["period"] != mkt.get("in_progress_period")]
        if len(recent) >= 4:
            W("Recent quarterly medians:")
            W("")
            W("| Quarter | Median | Sales |")
            W("|---|---:|---:|")
            for r in recent[-8:]:
                W(f"| {r['period']} | {money(r['median'])} | {r['count']} |")
            W("")
            W(f"*{len(q)} quarters back to {q[0]['period']} clear the 8-sale threshold; "
              f"{mkt.get('in_progress_period')} is still in progress and is excluded from "
              f"the headline and the year-on-year figure.*")
            W("")
    else:
        W(gap("D1"))
    cc = card_of(cards, "control")
    if cc:
        W("### You know this home better than the records do")
        W("")
        W(render_card(cc))
        W("")
    W(gap("G1"))
    W("---")
    W("")

    # ---------------- appendix --------------------------------------------
    W("## Appendix — diagnostics")
    W("")
    W("| | |")
    W("|---|---|")
    W(f"| Slug | `{doc.get('url_slug')}` |")
    W(f"| Dwelling class | {cls} |")
    W(f"| Scheme | {(cx or {}).get('complex_name') or '—'} · {doc.get('complex_plan') or '—'} · "
      f"{(cx or {}).get('cms_number') or '—'} |")
    W(f"| Scheme size | {(cx or {}).get('dwellings_in_scheme_data') or '—'} dwellings "
      f"(cadastre parcels: {(cx or {}).get('cadastre_lot_count') or '—'}) |")
    W(f"| Subtype | {(cx or {}).get('subtype') or '—'} |")
    W(f"| Valuation | {val.get('method')}{' / ' + str(val.get('tier')) if val.get('tier') else ''} |")
    W(f"| Floor area | {int(floor) if floor else ('~%d (derived)' % imputed['value'] if imputed else '—')} |")
    W(f"| Deck cards emitted | {len(cards)} of 11 |")
    W("")
    if b.get("gaps"):
        W("Engine-reported gaps: " + ", ".join(f"`{g}`" for g in b["gaps"]))
        W("")
    if notes:
        for n_ in notes:
            W(f"- {n_}")
        W("")
    codes = sorted(set(re.findall(r"\*\*GAP \[([A-Z]\d)\]", "\n".join(L))))
    W(f"**GAP markers: {len(codes)}** — {', '.join(codes) if codes else 'none'}")
    W("")
    return "\n".join(x for x in L if x is not None), codes


def render_one(address=None, slug=None, quiet=True):
    notes = []
    doc, suburb = resolve(address, slug)
    if not doc:
        raise LookupError(f"no document for {address or slug}")
    slug = doc.get("url_slug")
    if not slug:
        raise LookupError("document has no url_slug")
    gc = get_client()["Gold_Coast"]

    import fact_bundle
    import emit_v4 as E4
    bundle, cards = None, []
    try:
        bundle = fact_bundle.build(slug, suburb)
        (fact_bundle.BUNDLE_DIR / f"{slug}.json").write_text(
            json.dumps(bundle, indent=2, default=str))
        cards = (E4.emit_v4(slug) or {}).get("cards") or []
    except SystemExit as e:
        notes.append(f"deck engine refused: {e}")
    except Exception as e:
        notes.append(f"deck engine raised {type(e).__name__}: {e}")
        if not quiet:
            traceback.print_exc()

    md, codes = build_report(doc, suburb, bundle, cards, notes, gc)
    return slug, md, codes, len(cards)


def sample_addresses(n=8):
    """One of each FAILURE MODE. Spread across cadastral subtype, scheme (never two
    lots from one scheme) and sale history — a subject with a same-complex sale and
    one without exercise completely different paths."""
    import random
    random.seed(11)
    gc = get_client()["Gold_Coast"]
    pools = {}
    for pre in ("BUP", "GTP", "SP"):
        cand = []
        for s in CORE_SUBURBS:
            for d in gc[s].find({"PLAN": {"$regex": f"^{pre}"},
                                 "url_slug": {"$exists": True, "$nin": [None, ""]}},
                                PROJ).limit(1500):
                if classify_dwelling({**d, "street_address": effective_address(d)}) == "attached":
                    cand.append(d)
        random.shuffle(cand)
        pools[pre] = cand
    picks, seen = [], set()
    for i in range(n * 4):
        pre = ("BUP", "GTP", "SP")[i % 3]
        want = (i // 3) % 2 == 0
        for d in pools.get(pre, []):
            scheme = d.get("complex_plan") or re.sub(r"^\d+", "", str(d.get("PLAN") or ""))
            if scheme in seen:
                continue
            has = bool((d.get("enriched_data") or {}).get("transactions"))
            if has != want:
                continue
            seen.add(scheme)
            picks.append(d["url_slug"])
            pools[pre].remove(d)
            break
        if len(picks) >= n:
            break
    return picks[:n]


def main():
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    g = ap.add_mutually_exclusive_group(required=True)
    g.add_argument("--address")
    g.add_argument("--slug")
    g.add_argument("--batch")
    g.add_argument("--sample", type=int, metavar="N")
    ap.add_argument("--out")
    ap.add_argument("--summary", action="store_true")
    args = ap.parse_args()

    if args.address:
        targets = [(args.address, None)]
    elif args.slug:
        targets = [(None, args.slug)]
    elif args.batch:
        targets = []
        for line in Path(args.batch).read_text().splitlines():
            line = line.strip()
            if line and not line.startswith("#"):
                targets.append((None, line) if re.fullmatch(r"[a-z0-9-]+", line) else (line, None))
    else:
        targets = [(None, s) for s in sample_addresses(args.sample)]

    rows = []
    for address, slug in targets:
        try:
            slug_out, md, codes, ncards = render_one(address, slug)
        except Exception as e:
            print(f"  FAIL  {address or slug}: {type(e).__name__}: {e}", file=sys.stderr)
            continue
        out = Path(args.out) if (args.out and len(targets) == 1) else OUT_DIR / f"{slug_out}.md"
        out.write_text(md)
        print(f"  {out.name}  ({ncards} cards, {len(codes)} gaps)")
        rows.append((slug_out, codes))

    if args.summary or len(rows) > 1:
        from collections import Counter
        c = Counter(code for _s, codes in rows for code in codes)
        print(f"\n  {len(rows)} report(s) · GAP markers by workstream")
        for code, n in sorted(c.items()):
            print(f"  {code:5s} {n:4d}/{len(rows)}  {GAPS.get(code,'')[:72]}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
