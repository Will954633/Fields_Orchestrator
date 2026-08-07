#!/usr/bin/env python3
"""
generate_sold_analysis.py — deterministic, zero-LLM editorial for SOLD property pages.

Houses only (v1). No LLM calls: every claim is computed from structured data and
benchmarked against our own sold corpus (self-referential, free). Output is a
`sold_analysis` field on the property doc, parallel to `ai_analysis`.

Tone contract (Will, 2026-07-17):
  - Objective, data-driven, adds value — never generic.
  - Never talks a property down; trade-offs framed as value, never flaws.
  - Acceptable to BOTH buyers and sellers (a seller reading their own page should
    feel it was reported honestly, not judged).
  - Sold PRICE is a transacted fact — usable in headlines (unlike our estimates).
  - No advice, no predictions, exact figures, cite source + sample size.

See scripts/brain2/sold_editorial_scoping.md for the full design.

Usage:
  python generate_sold_analysis.py --suburb robina --dry-run --limit 8
  python generate_sold_analysis.py --slug 4-springvale-street-robina --dry-run
  python generate_sold_analysis.py --suburb robina --backfill        # writes + auto-publishes
"""
from __future__ import annotations
import argparse, hashlib, json, os, re, statistics as st, sys
from datetime import datetime, timezone

from pymongo import MongoClient

# Waterfront is out of editorial scope (see shared/waterfront.py) — sold pages for
# waterfront homes get no sold_analysis either. Orchestrator root on path first.
sys.path.insert(0, "/home/fields/Fields_Orchestrator")
from shared.waterfront import detect_waterfront  # noqa: E402

MIN_SEGMENT_N = 8            # below this, fall back to the parent (all-houses) segment
FORBIDDEN = ["stunning", "nestled", "boasting", "rare opportunity", "robust market"]
ADVICE = re.compile(r"\b(you should|we recommend|consider (buying|selling)|now is|"
                    r"negotiate|don'?t overpay|will (rise|fall|increase|drop)|"
                    r"good time to|worth buying)\b", re.I)

# ---------------------------------------------------------------- parsing helpers
def parse_price(*vals):
    for v in vals:
        if isinstance(v, (int, float)) and v > 0:
            return int(v)
        if isinstance(v, str):
            m = re.search(r"\$?\s*([\d,]{4,})", v)
            if m:
                n = int(m.group(1).replace(",", ""))
                if n >= 50000:
                    return n
    return None

def parse_date(s):
    if not isinstance(s, str):
        return None
    try:
        return datetime.strptime(s[:10], "%Y-%m-%d").date()
    except ValueError:
        return None

def money(n):
    return f"${n:,.0f}"

def ordinal(n):
    n = int(n)
    if 10 <= n % 100 <= 20:
        suf = "th"
    else:
        suf = {1: "st", 2: "nd", 3: "rd"}.get(n % 10, "th")
    return f"{n}{suf}"

def bed_band(beds):
    try:
        b = int(beds)
    except (TypeError, ValueError):
        return None
    if b <= 2: return "2 bed or fewer"
    if b == 3: return "3 bed"
    if b == 4: return "4 bed"
    return "5+ bed"

def pctile(v, arr):
    """Percentage of the sample strictly below v (0-100)."""
    if not arr:
        return None
    return round(100 * sum(1 for x in arr if x < v) / len(arr))

def quarter(d):
    return f"Q{(d.month - 1)//3 + 1} {d.year}"

# ---------------------------------------------------------------- prose helpers
# Copy rewrite 2026-08-05 (Will: "that doesn't make sense... sounds like a
# template"). Every string a reader sees is written as a sentence a person would
# say out loud. The numbers are unchanged — only the words around them.
#
# House style (CLAUDE.md + the property editorial prompt):
#   - "typically sell for", not "median" — the precise word stays on the evidence
#     line under each sentence, where it is labelled and unambiguous.
#   - Spell small numbers in prose ("four bedrooms"), keep figures for money.
#   - Australian quarter names ("the June quarter of 2025", not "Q2 2025").
NUM_WORDS = {1: "one", 2: "two", 3: "three", 4: "four", 5: "five",
             6: "six", 7: "seven", 8: "eight", 9: "nine", 10: "ten"}

def numword(n):
    """Spell out 1-10; larger numbers stay as digits."""
    try:
        i = int(n)
    except (TypeError, ValueError):
        return str(n)
    return NUM_WORDS.get(i, str(i))

# Australian convention names a quarter by its LAST month (ABS style).
_QUARTER_MONTH = {1: "March", 2: "June", 3: "September", 4: "December"}

def quarter_phrase(d):
    """'the June quarter of 2025' — how an Australian reader says Q2 2025."""
    return f"the {_QUARTER_MONTH[(d.month - 1)//3 + 1]} quarter of {d.year}"

# (plural, singular) per bed-band. Both forms are written out rather than derived,
# because naive singularisation produced "the typical five-bedroom and larger
# house in Varsity Lakes".
_BANDS = {
    "2 bed or fewer": ("two-bedroom and smaller houses", "two-bedroom or smaller house"),
    "3 bed":          ("three-bedroom houses",           "three-bedroom house"),
    "4 bed":          ("four-bedroom houses",            "four-bedroom house"),
    "5+ bed":         ("five-bedroom-plus houses",       "five-bedroom-plus house"),
}

def band_phrase(band, suburb_disp, singular=False):
    """'four-bedroom houses in Robina' — the bed-band as readable English.

    Replaces the old "4 bed Robina houses", a noun pile no one would say.
    """
    plural, single = _BANDS.get(band, ("houses", "house"))
    return f"{single if singular else plural} in {suburb_disp}"

def singularise_segment(label):
    """'four-bedroom houses in Robina' -> 'four-bedroom house in Robina'."""
    for plural, single in _BANDS.values():
        if label.startswith(plural + " in "):
            return label.replace(plural + " in ", single + " in ", 1)
    return label.replace("houses in ", "house in ", 1)

# ---------------------------------------------------------------- benchmark layer
def build_benchmarks(db, suburb):
    """Compute suburb + bed-band price benchmarks from our own sold House corpus.

    ⚠ `listing_price` is deliberately NOT in the price chain. It is the ASKING price, and
    a sold analysis has no business treating one as a transaction — the same defect fixed
    in the article path as [HOWITSOLD-ASKING-PRICE-CAMPAIGN] (2026-08-05) and missed here.
    Measured cost of removing it: 3 documents in Robina, 3 in Burleigh Waters, 0 in
    Varsity Lakes. Six records against a correctness defect on ~767 public pages.

    The corpus is unbounded in time by design rather than by oversight: our sold records
    only reach back about two years, so a window changes almost nothing while costing
    samples. Measured 2026-08-08 — Robina all-time and 24-month medians are IDENTICAL
    ($1,475,000, n=371 both); Burleigh Waters $1,860,000 vs $1,865,000; Varsity Lakes
    $1,300,000 vs $1,350,000 on 71 fewer sales. So the fix is DISCLOSURE, not truncation:
    the returned `period_from`/`period_to` let the copy state what the benchmark covers.
    """
    prices, doms, sqm = [], [], []
    by_band, by_quarter = {}, {}
    sold_dates = []
    for d in db[suburb].find({"listing_status": "sold", "property_type": "House"}):
        p = parse_price(d.get("sale_price"), d.get("last_sale_price"))
        if not p:
            continue
        prices.append(p)
        _sd = parse_date(d.get("sold_date"))
        if _sd:
            sold_dates.append(_sd)
        bb = bed_band(d.get("bedrooms"))
        if bb:
            by_band.setdefault(bb, []).append(p)
        sd = parse_date(d.get("sold_date"))
        if sd:
            by_quarter.setdefault(quarter(sd), []).append(p)
        if isinstance(d.get("days_on_market"), (int, float)):
            doms.append(d["days_on_market"])
        fa = (d.get("floor_plan_analysis") or {}).get("internal_floor_area")
        if isinstance(fa, (int, float)) and fa > 30:
            sqm.append(p / fa)
    prices.sort()
    return {
        "suburb": suburb,
        "prices": prices,
        "by_band": by_band,
        "by_quarter": {q: sorted(v) for q, v in by_quarter.items()},
        "doms": sorted(doms),
        "sqm": sorted(sqm),
        "n": len(prices),
        "median": st.median(prices) if prices else None,
        "dom_median": st.median(doms) if doms else None,
        "sqm_median": st.median(sqm) if sqm else None,
        # Actual span of the corpus behind every figure above, so the copy can say what it
        # is rather than implying an open-ended market truth.
        "period_from": min(sold_dates).strftime("%b %Y") if sold_dates else None,
        "period_to": max(sold_dates).strftime("%b %Y") if sold_dates else None,
    }

def segment_for(p, bench):
    """Return (label, array) — bed-band if it has enough samples, else all-houses.

    The label is a readable noun phrase ("four-bedroom houses in Robina"), so it
    drops straight into a sentence.
    """
    disp = bench["suburb"].replace("_", " ").title()
    bb = bed_band(p.get("bedrooms"))
    arr = bench["by_band"].get(bb) if bb else None
    if arr and len(arr) >= MIN_SEGMENT_N:
        return band_phrase(bb, disp), sorted(arr)
    return f"houses in {disp}", bench["prices"]

# ---------------------------------------------------------------- insight modules
# Each: (property, bench) -> Insight dict {type,text,evidence,tier,score} or None.
# `score` = notability (higher floats to the top). `tier` = data richness.

def m_price_vs_market(p, bench):
    # NOT p["listing_price"] — the whole sentence below is "it SOLD for X". Falling back
    # to the asking price would state an aspiration as a transaction. If we have no sale
    # price for this home, there is no price-vs-market insight to write.
    price = parse_price(p.get("sale_price"), p.get("last_sale_price"))
    if not price or not bench["prices"]:
        return None
    label, arr = segment_for(p, bench)
    med = st.median(arr)
    delta = price - med
    pc = pctile(price, arr)
    # "51st percentile of 179 comparable sales" is analyst shorthand. A reader
    # who has never seen a percentile still understands "51% of them sold for
    # less" — same number, no glossary required.
    # "typically go for" is present tense and reads as a claim about today's market. The
    # corpus is historical and ours, so the verb is past and the span is stated.
    if abs(delta) < max(0.02 * med, 15000):
        lead = (f"At {money(price)}, it sold within {money(abs(delta))} of the median "
                f"{label} have sold for — {money(med)}.")
    else:
        lead = (f"At {money(price)}, it sold {money(abs(delta))} "
                f"{'above' if delta > 0 else 'below'} the {money(med)} median "
                f"{label} have sold for.")
    span = ""
    if bench.get("period_from") and bench.get("period_to"):
        span = (f" from {bench['period_from']}" if bench["period_from"] == bench["period_to"]
                else f" from {bench['period_from']} to {bench['period_to']}")
    text = (f"{lead} Of the {len(arr)} comparable sales we hold{span}, {pc}% went for "
            f"less. That is the sales we record, not every sale in the suburb.")
    # Base score sits above every other module's ceiling (campaign_speed tops out
    # at 55) so the price ALWAYS leads. This is the one fact the page exists to
    # answer — a reader who searched the address wants the sale price first, not
    # how long the campaign ran. Before this, a fast campaign could out-score the
    # price and 48 Tullamarine Drive opened with "It found a buyer in 2 days".
    return {"type": "price_vs_market", "text": text,
            "evidence": {"price": price, "median": med, "delta": delta,
                         "percentile": pc, "n": len(arr), "segment": label},
            "tier": 1, "score": 60 + abs(delta) / max(med, 1) * 60}

def m_campaign_speed(p, bench):
    dom = p.get("days_on_market")
    if not isinstance(dom, (int, float)) or not bench["dom_median"]:
        return None
    med = bench["dom_median"]
    disp = bench["suburb"].replace("_", " ").title()
    if dom <= med * 0.6:
        text = (f"It found a buyer in {int(dom)} days. The typical {disp} house "
                f"takes {med:.0f}.")
    elif dom >= med * 1.5:
        text = (f"It took {int(dom)} days to sell, against {med:.0f} for the "
                f"typical {disp} house.")
    else:
        text = (f"It took {int(dom)} days to sell — about the same as the typical "
                f"{disp} house, at {med:.0f}.")
    return {"type": "campaign_speed", "text": text,
            "evidence": {"dom": int(dom), "dom_median": med},
            "tier": 2, "score": 25 + abs(dom - med) / max(med, 1) * 30}

def m_configuration(p, bench):
    beds, baths = p.get("bedrooms"), p.get("bathrooms")
    car = p.get("carspaces", p.get("car_spaces"))
    if not beds:
        return None
    # "A 4 bed / 2 bath / 2 car home." is listing-portal shorthand. Written out,
    # it reads like a sentence instead of a spec line.
    parts = [f"{numword(beds)} bedroom{'s' if int(beds) != 1 else ''}"]
    if baths:
        parts.append(f"{numword(baths)} bathroom{'s' if int(baths) != 1 else ''}")
    if car:
        parts.append(f"parking for {numword(car)}")
    if len(parts) > 1:
        cfg = ", ".join(parts[:-1]) + f" and {parts[-1]}"
    else:
        cfg = parts[0]
    fa = (p.get("floor_plan_analysis") or {}).get("internal_floor_area")
    tail = ""
    if isinstance(fa, (int, float)) and fa > 30 and bench["sqm"]:
        tail = f", across {fa:.0f} sqm of internal living"
    text = f"{cfg[0].upper()}{cfg[1:]}{tail}."
    return {"type": "configuration", "text": text,
            "evidence": {"bedrooms": int(beds), "bathrooms": int(baths) if baths else None},
            "tier": 1, "score": 15}

def m_condition_finish(p, bench):
    """Report photo-analysis quality signals — value-framed, never talking down."""
    pva = p.get("property_valuation_data") or {}
    po = pva.get("property_overview") or {}
    reno = pva.get("renovation") or {}
    kit = pva.get("kitchen") or {}
    cs = pva.get("condition_summary") or {}
    score = po.get("overall_condition_score") or cs.get("overall_score")
    if score is None and not reno:
        return None
    # "Photo analysis shows a partially updated home, laminate kitchen benchtops,
    # and an overall condition of 7/10." — three unlike things in one list, led by
    # a machine noun. Split into what the photos showed, then what we scored it.
    lvl = reno.get("overall_renovation_level")
    RENO = {"fully_renovated": "a fully renovated house",
            "extensively_renovated": "an extensively renovated house",
            "cosmetically_updated": "a cosmetically updated house",
            "partially_renovated": "a partially updated house",
            "original": "a house in original condition, with room to update"}
    km = kit.get("benchtop_material")
    if km in (None, "", "unknown", "other"):
        km = None
    kitchen = None
    if km:
        kitchen = f"{km} kitchen benchtops"
        if kit.get("appliances_quality") == "premium":
            kitchen += " and premium appliances"

    sentences = []
    if lvl in RENO and kitchen:
        sentences.append(f"The listing photos show {RENO[lvl]}, with {kitchen}.")
    elif lvl in RENO:
        sentences.append(f"The listing photos show {RENO[lvl]}.")
    elif kitchen:
        sentences.append(f"The listing photos show {kitchen}.")
    if score:
        # "We scored" — says who made the judgement, which the old phrasing hid.
        sentences.append(
            f"We scored its overall condition {int(score)} out of 10"
            + (" from those photos." if sentences else " from the listing photos.")
        )
    if not sentences:
        return None
    text = " ".join(sentences)
    # notability: strong (renovated / high score) OR clear update-opportunity both interesting
    notable = (score or 5)
    return {"type": "condition_finish", "text": text,
            "evidence": {"overall_condition_score": score, "renovation_level": lvl},
            "tier": 2, "score": 20 + abs((notable) - 5) * 4}

def m_character(p, bench):
    po = (p.get("property_valuation_data") or {}).get("property_overview") or {}
    style = po.get("architectural_style")
    stories = po.get("number_of_stories")
    # "other" is what the classifier stores when it cannot tell — it was reaching
    # the page as "Single-level other home." Skip rather than publish a placeholder.
    if not style or style in ("unknown", "other", "unspecified"):
        return None
    levels = {1: "single-level", 2: "two-level", 3: "three-level"}.get(stories)
    if levels:
        text = f"It's a {levels} {style} house."
    else:
        text = f"It's a {style} house."
    return {"type": "character", "text": text,
            "evidence": {"architectural_style": style, "stories": stories},
            "tier": 3, "score": 8}

def m_market_timing(p, bench):
    sd = parse_date(p.get("sold_date"))
    if not sd:
        return None
    q = quarter(sd)
    qarr = bench["by_quarter"].get(q)
    if not qarr or len(qarr) < MIN_SEGMENT_N:
        return None
    med = st.median(qarr)
    disp = bench["suburb"].replace("_", " ").title()
    # "Transacted in Q2 2025" is trade-speak on both counts.
    # "typically", not "on average" — the figure is a median, and the two are not
    # the same thing. Every plain-English substitution still has to be true.
    text = (f"The sale went through in {quarter_phrase(sd)}, when houses in {disp} "
            f"were typically selling for {money(med)}, across {len(qarr)} "
            f"recorded sales.")
    return {"type": "market_timing", "text": text,
            "evidence": {"quarter": q, "quarter_median": med, "n": len(qarr)},
            "tier": 2, "score": 12}

MODULES = [m_price_vs_market, m_campaign_speed, m_configuration,
           m_condition_finish, m_character, m_market_timing]

# ---------------------------------------------------------------- assembly
def build_headline(top, p):
    """The page's H1. The address sits directly beneath it, so the headline must
    add something the address doesn't.

    The old at-or-below-median headline was "Sold for $1,550,000 in Robina" —
    which Will flagged, correctly. The suburb is already in the dateline, the
    address line and the breadcrumb directly around it, so "in Robina" was both
    redundant and awkwardly hung off the end. Replacing the place with the DATE
    fixes the sentence and adds real information: how current this sale is, which
    is the first thing anyone judging a comparable wants to know.
    """
    price = parse_price(p.get("sale_price"), p.get("last_sale_price"))
    if not price:
        return f"Sold in {(p.get('suburb') or '').strip()}".strip()

    sd = parse_date(p.get("sold_date"))
    when = f" in {sd.strftime('%B %Y')}" if sd else ""

    if top and top["type"] == "price_vs_market":
        ev = top["evidence"]
        suburb_disp = (p.get("suburb") or "").strip()
        # Lead with the delta ONLY when it is positive. A seller reading their own
        # page should not be met with an H1 announcing they sold under the median
        # — the figure is still reported, objectively, in the body. This is the
        # value-framing rule, and the rewrite preserves it deliberately.
        if ev["delta"] > max(0.02 * ev["median"], 15000):
            # Name the segment the delta was ACTUALLY measured against. It is the
            # bed-band ("three-bedroom houses in Varsity Lakes") whenever that has
            # enough samples, so the old "the typical Varsity Lakes house" was
            # comparing against one number and crediting it to another.
            seg = ev.get("segment") or f"houses in {suburb_disp}"
            return (f"Sold for {money(price)} — {money(ev['delta'])} above the "
                    f"typical {singularise_segment(seg)}")
    return f"Sold for {money(price)}{when}"

def build_summary(selected):
    """Two sentences, used as the page's meta description.

    Kept to the top two insights: the on-page renderer suppresses the summary
    when it merely repeats them, so this exists to be a good SERP snippet rather
    than a second copy of the page.
    """
    return " ".join(s["text"] for s in selected[:2])

def analyse(p, bench):
    insights = [ins for m in MODULES if (ins := m(p, bench))]
    insights.sort(key=lambda x: x["score"], reverse=True)
    price = parse_price(p.get("sale_price"), p.get("last_sale_price"))
    completeness = round(len([i for i in insights]) / len(MODULES), 2)
    top = insights[0] if insights else None
    analysis = {
        "version": 2,          # v2 = 2026-08-05 copy rewrite (prose, not templates)
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "generator": "generate_sold_analysis.py",
        "status": "published",
        "headline": build_headline(top, p),
        "summary": build_summary(insights),
        "insights": [{k: i[k] for k in ("type", "text", "evidence", "tier")} for i in insights],
        "benchmarks_used": {"suburb": bench["suburb"], "n": bench["n"],
                            "median": bench["median"]},
        "sources": ["Domain sold record", "Fields photo analysis (GPT-4 Vision)"],
        "data_completeness": completeness,
        "source_hash": source_hash(p),
    }
    return analysis

def source_hash(p):
    key = json.dumps({k: p.get(k) for k in
                      ("sale_price", "sold_date", "bedrooms", "bathrooms",
                       "carspaces", "days_on_market")}, sort_keys=True, default=str)
    return hashlib.sha1(key.encode()).hexdigest()[:12]

# ---------------------------------------------------------------- verification
def verify(analysis, p):
    """Re-derive numeric claims + lint tone. Returns (ok, problems)."""
    problems = []
    blob = analysis["headline"] + " " + analysis["summary"] + " " + \
           " ".join(i["text"] for i in analysis["insights"])
    low = blob.lower()
    for w in FORBIDDEN:
        if w in low:
            problems.append(f"forbidden word: {w}")
    if ADVICE.search(blob):
        problems.append("advice/prediction language detected")
    # price claim must parse back to the real sold price
    real = parse_price(p.get("sale_price"), p.get("last_sale_price"))
    for ins in analysis["insights"]:
        if ins["type"] == "price_vs_market":
            if ins["evidence"]["price"] != real:
                problems.append("price mismatch vs source")
    return (not problems), problems

# ---------------------------------------------------------------- runner
def process(db, suburb, p, bench, dry, write):
    # WATERFRONT GATE — no sold editorial for waterfront homes (out of scope, 2026-07-26).
    if detect_waterfront(p)["is_waterfront"]:
        print(f"[SKIP] {p.get('address')} — waterfront (sold editorial withheld, out of scope)")
        if write and not p.get("is_waterfront"):
            db[suburb].update_one({"_id": p["_id"]}, {"$set": {"is_waterfront": True}})
        return "skipped_waterfront", False
    a = analyse(p, bench)
    ok, problems = verify(a, p)
    if not ok:
        a["status"] = "needs_review"
        a["_verify_problems"] = problems
    if dry:
        print(f"\n{'='*70}\n{p.get('address')}  [{a['status']}]  completeness={a['data_completeness']}")
        print(f"HEADLINE: {a['headline']}")
        print(f"SUMMARY:  {a['summary']}")
        for i in a["insights"]:
            print(f"   • ({i['type']}) {i['text']}")
        if problems:
            print(f"   !! {problems}")
    if write and ok:
        db[suburb].update_one({"_id": p["_id"]}, {"$set": {"sold_analysis": a}})
    return a["status"], ok

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--suburb", default="robina")
    ap.add_argument("--slug")
    ap.add_argument("--backfill", action="store_true")
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--limit", type=int, default=0)
    args = ap.parse_args()

    client = MongoClient(os.environ["COSMOS_CONNECTION_STRING"])
    db = client["Gold_Coast"]
    bench = build_benchmarks(db, args.suburb)
    print(f"[benchmarks] {args.suburb}: n={bench['n']} houses, "
          f"median={money(bench['median']) if bench['median'] else 'n/a'}, "
          f"DOM median={bench['dom_median']}")

    q = {"listing_status": "sold", "property_type": "House"}
    if args.slug:
        q["url_slug"] = args.slug
    cur = db[args.suburb].find(q)
    if args.limit:
        cur = cur.limit(args.limit)

    write = args.backfill and not args.dry_run
    stats = {"published": 0, "needs_review": 0, "skipped_no_price": 0, "retracted": 0}
    for p in cur:
        if not parse_price(p.get("sale_price"), p.get("last_sale_price")):
            stats["skipped_no_price"] += 1
            # A plain `continue` would leave any EXISTING sold_analysis live. That matters
            # now that `listing_price` is no longer accepted as a sale price: the pages
            # that lose their price are exactly the ones whose published copy states an
            # ASKING price as the sold figure. Skipping would quietly preserve the defect
            # this change exists to remove, so retract instead.
            if p.get("sold_analysis"):
                stats["retracted"] += 1
                print(f"  RETRACT {p.get('address') or p.get('_id')} — no recorded sale "
                      f"price; removing sold_analysis that quoted the asking price")
                if write:
                    db[args.suburb].update_one({"_id": p["_id"]},
                                               {"$unset": {"sold_analysis": ""}})
            continue
        status, ok = process(db, args.suburb, p, bench, args.dry_run, write)
        stats[status] = stats.get(status, 0) + 1
    print(f"\n[done] {stats}  (write={write})")
    client.close()

if __name__ == "__main__":
    main()
