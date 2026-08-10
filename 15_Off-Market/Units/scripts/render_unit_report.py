#!/usr/bin/env python3
"""render_unit_report.py — address -> markdown report for an attached dwelling.

WHY THIS EXISTS
---------------
The unit page's copy is the product. Reviewing it as a deploy is slow and expensive;
reviewing it as a document is neither. This renders the FULL prose of a unit page in
the same section order as the live house page
(`/off-market/27-huntingdale-crescent-robina`), so the writing can be judged and
rewritten long before any of it reaches React.

Every section either renders real content or emits an explicit marker:

    > GAP [D1] - no unit price series exists for Robina.
    >   The house median would be wrong here. Section suppressed.

so the document doubles as a progress tracker. The project is done when a sampled
report contains no GAP markers.

THE ONE ARCHITECTURAL RULE (plan item I4)
-----------------------------------------
This is a NEW OUTPUT FORMAT FOR THE EXISTING ENGINE, not a new engine. It calls
`fact_bundle.build()` and `emit_v4.emit_v4()` and renders what they return. It must
never compute a fact of its own. If it did, report and page would drift, and we would
have re-created the exact defect class the audit is full of - one concept, two
implementations, one maintained. See 15_Off-Market/Units/UNITS_COVERAGE_AUDIT.md.

USAGE
-----
    python3 render_unit_report.py --address "1/3 Laurel Oak Drive, Robina"
    python3 render_unit_report.py --slug 1-3-laurel-oak-drive-robina
    python3 render_unit_report.py --sample 8            # one of each subtype
    python3 render_unit_report.py --batch addresses.txt --summary
"""
from __future__ import annotations

import argparse
import datetime as _dt
import json
import os
import re
import sys
import traceback
from pathlib import Path

HERE = Path(__file__).resolve().parent
UNITS = HERE.parent
ROOT = UNITS.parent.parent                      # Fields_Orchestrator
ENGINE = ROOT / "15_Off-Market" / "Page_Redesign_V2"

for p in (str(ROOT), str(ENGINE)):
    if p not in sys.path:
        sys.path.insert(0, p)

try:
    from shared.env import load_env
    load_env()
except Exception:
    pass

from shared.dwelling_type import classify_dwelling          # noqa: E402
from shared.db import get_client                            # noqa: E402

OUT_DIR = UNITS / "artifacts" / "unit_reports"
OUT_DIR.mkdir(parents=True, exist_ok=True)

CORE_SUBURBS = ["robina", "varsity_lakes", "burleigh_waters"]

# ---------------------------------------------------------------------------
# GAP registry - every marker names the workstream that closes it, so the report
# is a checklist against UNITS_DEVELOPMENT_PLAN.md rather than a list of regrets.
# ---------------------------------------------------------------------------
GAPS = {
    "B2": "dwelling_class is not persisted; classification is computed live here",
    "C2": "no floor area on this dwelling (Domain internalArea not yet read)",
    "C3": "no complex amenity data (structuredFeatures[] not yet stored)",
    "D1": "no unit price series exists for this suburb; the house median would be wrong here",
    "D3": "no unit days-on-market or unit active-listing count",
    "E1": "no complex entity - CTS number, scheme name and scheme size not yet ingested",
    "E2": "no storeys band - QLD LiDAR buildings layer not yet ingested",
    "F3": "no unit valuation - the comparables engine is house-only and refuses attached stock",
    "F4": "no floor area and no same-complex donor to impute one from",
    "G1": "copy is house-shaped; copy_units_v4.yaml does not exist yet",
    "G2": "scarcity cohort is untyped - this counts the DETACHED HOUSE market",
    "G3": "green_space makes a boundary claim from a single geocode; invalid for a scheme",
    "G4": "hero is a cadastral lot; for a unit the parcel is the whole scheme",
    "G5": "buyer archetype is a detached-house persona",
    "F5": ("the engine emitted a RANGE for this unit, derived from HOUSE sales — "
           "`_thin_valuation_range` filters on bedrooms with no property_type clause"),
    "D4": "the market card quotes house days-on-market and house listing counts",
}

# Card keys that are chaining/plumbing, not prose.
_SKIP_KEYS = {"type", "n", "_canon", "next"}
# Preferred lead order; anything else follows in declaration order.
_LEAD = ("answer", "questions_intro", "headline", "range", "anchor_intro", "anchor",
         "anchor_note", "tier_caveat")


def gap(code: str, extra: str = "") -> str:
    body = GAPS.get(code, "unspecified")
    line = f"> **GAP [{code}]** — {body}."
    if extra:
        line += f"\n>\n> {extra}"
    return line + "\n"


# ---------------------------------------------------------------------------
# Resolution
# ---------------------------------------------------------------------------
def _norm(s: str) -> str:
    return re.sub(r"[^a-z0-9]+", " ", (s or "").lower()).strip()


def resolve(address: str | None, slug: str | None):
    """address|slug -> (doc, suburb_key). Never guesses a field name; reads the
    effective-address chain the route uses (address || complete_address)."""
    gc = get_client()["Gold_Coast"]
    proj = {"url_slug": 1, "address": 1, "complete_address": 1, "street_address": 1,
            "property_type": 1, "classified_property_type": 1, "PLAN": 1, "LOT": 1,
            "scraped_data.features.property_type": 1, "scraped_data_v2.property_type": 1,
            "PROPERTY_NAME": 1, "UNIT_NUMBER": 1, "bedrooms": 1, "bathrooms": 1}
    if slug:
        for s in CORE_SUBURBS:
            d = gc[s].find_one({"url_slug": slug}, proj)
            if d:
                return d, s
        return None, None

    want = _norm(address)
    # exact-ish first, then contains - address lives in three different fields
    for s in CORE_SUBURBS:
        for field in ("address", "complete_address", "street_address"):
            for d in gc[s].find({field: {"$regex": re.escape(address.split(",")[0].strip()),
                                         "$options": "i"}}, proj).limit(60):
                eff = d.get("address") or d.get("complete_address") or d.get("street_address") or ""
                if _norm(eff).startswith(want[:len(want)]) or want in _norm(eff):
                    return d, s
    return None, None


def effective_address(d: dict) -> str:
    return (d.get("address") or d.get("complete_address")
            or d.get("street_address") or "")


def subtype_of(d: dict) -> str:
    """Cadastral PLAN prefix - verified 93% filled on attached stock, and a 7.5x
    enriched signal vs houses. BUP = building with common property (lift likely);
    GTP = villa/townhouse group; SP = ambiguous; RP = freehold."""
    plan = str(d.get("PLAN") or "").upper()
    m = re.match(r"^([A-Z]+)", plan)
    pre = m.group(1) if m else ""
    return {"BUP": "BUP (building, common property — apartment)",
            "GTP": "GTP (group title — villa/townhouse)",
            "SP": "SP (survey plan — ambiguous)",
            "RP": "RP (freehold — probably not attached)"}.get(pre, pre or "unknown")


# ---------------------------------------------------------------------------
# Rendering helpers
# ---------------------------------------------------------------------------
def money(v):
    try:
        return f"${float(v):,.0f}"
    except Exception:
        return None


def card_of(cards, ctype):
    for c in cards:
        if c.get("type") == ctype:
            return c
    return None


def para(*bits):
    return "\n\n".join(b for b in bits if b)


def render_card(c):
    """Render a card as prose in the engine's own order, so the report reads as the
    page would. Lists become bullets; nested reveal blocks become a detail line.
    Chaining keys are dropped - they are plumbing between cards, not copy."""
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
            label = v.get("label") or k.replace("_", " ")
            body = v.get("body") or ""
            if body:
                out.append(f"**{label}** — {body}")
    return "\n\n".join(out)


# ---------------------------------------------------------------------------
# The report
# ---------------------------------------------------------------------------
def build_report(doc, suburb, bundle, cards, notes):
    addr = effective_address(doc)
    sub_display = (suburb or "").replace("_", " ").title()
    cls = classify_dwelling({**doc, "street_address": addr})
    b = bundle or {}
    feat = b.get("subject") or {}
    L = []
    W = L.append

    W(f"# {addr}")
    W("")
    W(f"*Private property report · rendered {_dt.date.today():%A %-d %B %Y}*")
    W("")
    W(f"> **Harness note.** This is the markdown proof of the unit page, rendered from the "
      f"live engine (`fact_bundle` → `emit_v4`). It is not published anywhere. "
      f"GAP markers name the workstream in `UNITS_DEVELOPMENT_PLAN.md` that closes them.")
    W("")
    W("| | |")
    W("|---|---|")
    W(f"| Slug | `{doc.get('url_slug')}` |")
    W(f"| Suburb | {sub_display} |")
    W(f"| Dwelling class | **{cls}** (computed live — {GAPS['B2']}) |")
    W(f"| Cadastral subtype | {subtype_of(doc)} |")
    W(f"| Complex name | {doc.get('PROPERTY_NAME') or '—'} |")
    W(f"| Cards emitted | {len(cards)} of 11 |")
    W("")
    W("---")
    W("")

    # ---------------- Section 0 - hero -------------------------------------
    W("## 0 · The header")
    W("")
    bits = []
    if feat.get("bedrooms"):
        bits.append(f"{feat['bedrooms']} bedrooms")
    if feat.get("bathrooms"):
        bits.append(f"{feat['bathrooms']} bathrooms")
    if feat.get("floor_sqm"):
        bits.append(f"{feat['floor_sqm']} m² floor")
    W(f"**{addr}**")
    W("")
    W(" · ".join(bits) if bits else "_no attributes recorded_")
    W("")
    if not feat.get("floor_sqm"):
        W(gap("C2"))
    arrival = card_of(cards, "recognition")
    if arrival:
        W(render_card(arrival))
        W("")
    W(gap("G4", "The house page shows a title boundary and land size here. For a unit the "
                "cadastral parcel is the whole scheme — it would show ~40 neighbours' roofs. "
                "Replacement is complex name + scheme size + storeys band."))
    W(gap("E1"))
    W(gap("E2"))
    W("---")
    W("")

    # ---------------- Section 1 - what's changed ---------------------------
    W("## 1 · The last six months — what's changed recently")
    W("")
    W(gap("D1", "The house page shows suburb median, days-on-market and comparable sales here. "
                "Every one of those series is houses-only by construction "
                "(`precompute_union_prices.py` filters `classify_dwelling == house`)."))
    W(gap("D3"))
    W("---")
    W("")

    # ---------------- Section 2 - Part 01 the valuation --------------------
    W("## 2 · Part 01 — The valuation")
    W("")
    for t, label in (("valuation", "The range"), ("evidence", "The evidence"),
                     ("comparable", "The sale up the road"), ("method", "Reliability"),
                     ("dispersion", "Why three sites disagree")):
        c = card_of(cards, t)
        if c:
            W(f"### {label}")
            W("")
            W(render_card(c))
            W("")
    v = b.get("valuation") or {}
    vcard = card_of(cards, "valuation")
    if v and v.get("low") and v.get("method") in (None, "thin", "model", "exterior_evidence"):
        W(gap("F5",
              f"Engine emitted **{vcard.get('range') if vcard else money(v.get('low'))}** for this "
              f"dwelling via `method={v.get('method')}`, n_comps={v.get('n_comps')}. "
              f"⚠ **This is not a refusal — it is a number.** The V4 React page suppresses it "
              f"(it requires `valuation_data.confidence.range.low`), but the DISCOVERY DECK "
              f"renders this card, and the deck is the default in every non-V4 suburb. "
              f"Verify before shipping the unit arm."))
    elif not v or not v.get("low"):
        W(gap("F3", "This is the honest refusal the page would show. It is correct today — but "
                    "the target is a same-complex method that earns a range, not a permanent "
                    "refusal. See Workstream F."))
    W("---")
    W("")

    # ---------------- Section 3 - Part 02 the home itself ------------------
    W("## 3 · Part 02 — The home itself")
    W("")
    for t, label in (("reveal", "What stood out"), ("competition", "The comparison set"),
                     ("buyer", "The buyer")):
        c = card_of(cards, t)
        if c:
            W(f"### {label}")
            W("")
            W(render_card(c))
            W("")
    comp = card_of(cards, "competition")
    if comp and any(isinstance(x, str) and re.search(r"\bhomes?\b|\bdays\b|on the market", x)
                    for x in comp.values()):
        W(gap("D4", "The market copy rendered above draws on `precomputed_market_charts` "
                    "(days-on-market) and `precomputed_active_listings` — both keyed by suburb "
                    "only, both houses-only by construction. Presented here as this dwelling's "
                    "market."))
    sc = b.get("scarcity") or {}
    if sc.get("active_total") or sc.get("active_matching"):
        W(gap("G2", f"Rendered above: {sc.get('active_matching')} of {sc.get('active_total')}. "
                    f"That denominator is the **detached-house** active pool "
                    f"(`scarcity_features.count_active_matches` has no property_type filter). "
                    f"On the live site this is what produces \"107 of 233 nearby homes\"."))
    if b.get("green_space"):
        W(gap("G3", f"Engine returned: `{json.dumps(b['green_space'], default=str)[:160]}`. "
                    f"Suppress for attached dwellings."))
    if card_of(cards, "buyer"):
        W(gap("G5"))
    W("---")
    W("")

    # ---------------- Section 4 - Part 03 where that leaves you ------------
    W("## 4 · Part 03 — Where that leaves you")
    W("")
    for t, label in (("gain", "What it has done since you bought"),
                     ("control", "What you know that we don't")):
        c = card_of(cards, t)
        if c:
            W(f"### {label}")
            W("")
            W(render_card(c))
            W("")
    W(gap("D1", "The house page closes with suburb median, median trend chart, days-on-market "
                "and \"N houses for sale\". All house series."))
    W("")
    W("---")
    W("")

    # ---------------- Diagnostics -----------------------------------------
    W("## Appendix — engine diagnostics")
    W("")
    W("Which of the 11 emitters produced a card for this dwelling:")
    W("")
    W("| # | card type | emitted |")
    W("|---|---|---|")
    order = ["recognition", "valuation", "evidence", "comparable", "reveal", "method",
             "dispersion", "gain", "competition", "buyer", "control"]
    for i, t in enumerate(order):
        W(f"| {i:02d} | `{t}` | {'yes' if card_of(cards, t) else '—'} |")
    W("")
    if b.get("gaps"):
        W("Engine-reported gaps: " + ", ".join(f"`{g}`" for g in b["gaps"]))
        W("")
    if notes:
        W("Harness notes:")
        for n in notes:
            W(f"- {n}")
        W("")
    codes = sorted(set(re.findall(r"\*\*GAP \[([A-Z]\d)\]", "\n".join(L))))
    W(f"**GAP markers in this report: {len(codes)}** — {', '.join(codes) if codes else 'none'}")
    W("")
    return "\n".join(L), codes


# ---------------------------------------------------------------------------
def render_one(address=None, slug=None, quiet=False):
    notes = []
    doc, suburb = resolve(address, slug)
    if not doc:
        raise LookupError(f"no document for {address or slug} in {CORE_SUBURBS}")
    slug = doc.get("url_slug")
    if not slug:
        raise LookupError(f"document has no url_slug: {effective_address(doc)}")

    import fact_bundle
    import emit_v4 as E4

    bundle, cards = None, []
    try:
        bundle = fact_bundle.build(slug, suburb)
        (fact_bundle.BUNDLE_DIR / f"{slug}.json").write_text(
            json.dumps(bundle, indent=2, default=str))
    except SystemExit as e:
        notes.append(f"fact_bundle.build refused: {e}")
    except Exception as e:
        notes.append(f"fact_bundle.build raised {type(e).__name__}: {e}")
        if not quiet:
            traceback.print_exc()
    if bundle is not None:
        try:
            cards = (E4.emit_v4(slug) or {}).get("cards") or []
        except Exception as e:
            notes.append(f"emit_v4 raised {type(e).__name__}: {e}")
            if not quiet:
                traceback.print_exc()

    md, codes = build_report(doc, suburb, bundle, cards, notes)
    return slug, md, codes, len(cards)


def sample_addresses(n=8):
    """One of each FAILURE MODE, not n of the same.

    The first version of this returned six `1/1 ...` addresses because it broke on
    the first match per suburb - six samples, one failure mode, and a false sense of
    coverage. Sampling here is deliberately spread across cadastral subtype, complex
    (never two lots from one scheme) and sale history, because a unit with a
    same-complex sale and one without exercise completely different engine paths.
    """
    import random
    random.seed(11)
    gc = get_client()["Gold_Coast"]
    proj = {"url_slug": 1, "address": 1, "complete_address": 1, "street_address": 1,
            "property_type": 1, "classified_property_type": 1, "PLAN": 1,
            "scraped_data.features.property_type": 1, "scraped_data_v2.property_type": 1,
            "enriched_data.transactions": 1, "PROPERTY_NAME": 1}
    pools = {}
    for pre in ("BUP", "GTP", "SP"):
        cand = []
        for s in CORE_SUBURBS:
            for d in gc[s].find({"PLAN": {"$regex": f"^{pre}"},
                                 "url_slug": {"$exists": True, "$nin": [None, ""]}},
                                proj).limit(1500):
                eff = effective_address(d)
                if classify_dwelling({**d, "street_address": eff}) != "attached":
                    continue
                cand.append(d)
        random.shuffle(cand)
        pools[pre] = cand

    picks, seen_scheme = [], set()
    # alternate subtypes, and inside each alternate has-sales / no-sales
    for i in range(n * 4):
        pre = ("BUP", "GTP", "SP")[i % 3]
        want_sales = (i // 3) % 2 == 0
        pool = pools.get(pre) or []
        for d in pool:
            scheme = re.sub(r"^\d+", "", str(d.get("PLAN") or "")) or d.get("PROPERTY_NAME")
            if scheme in seen_scheme:
                continue
            has = bool(((d.get("enriched_data") or {}).get("transactions")))
            if has != want_sales:
                continue
            seen_scheme.add(scheme)
            why = f"{pre}, {'has' if has else 'no'} sale history"
            picks.append((d["url_slug"], why))
            pool.remove(d)
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
    g.add_argument("--batch", help="file of addresses or slugs, one per line")
    g.add_argument("--sample", type=int, metavar="N",
                   help="render N dwellings spread across cadastral subtypes")
    ap.add_argument("--out", help="output path (single mode)")
    ap.add_argument("--summary", action="store_true", help="print a GAP summary table")
    args = ap.parse_args()

    targets = []
    if args.address:
        targets = [(args.address, None)]
    elif args.slug:
        targets = [(None, args.slug)]
    elif args.batch:
        for line in Path(args.batch).read_text().splitlines():
            line = line.strip()
            if line and not line.startswith("#"):
                targets.append((None, line) if re.fullmatch(r"[a-z0-9-]+", line) else (line, None))
    else:
        targets = [(None, s) for s, _why in sample_addresses(args.sample)]

    rows = []
    for address, slug in targets:
        try:
            slug_out, md, codes, ncards = render_one(address, slug, quiet=True)
        except Exception as e:
            print(f"  FAIL  {address or slug}: {type(e).__name__}: {e}", file=sys.stderr)
            rows.append((address or slug, None, ["FAILED"], 0))
            continue
        out = Path(args.out) if (args.out and len(targets) == 1) else OUT_DIR / f"{slug_out}.md"
        out.write_text(md)
        print(f"  {out}  ({ncards} cards, {len(codes)} gaps)")
        rows.append((slug_out, out, codes, ncards))

    if args.summary or len(rows) > 1:
        from collections import Counter
        c = Counter(code for _s, _o, codes, _n in rows for code in codes)
        print(f"\n  {len(rows)} report(s) · GAP markers by workstream")
        print(f"  {'code':6s} {'hits':>5s}  what closes it")
        for code, n in sorted(c.items()):
            print(f"  {code:6s} {n:5d}  {GAPS.get(code, '')[:74]}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
