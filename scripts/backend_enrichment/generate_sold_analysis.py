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

# ---------------------------------------------------------------- benchmark layer
def build_benchmarks(db, suburb):
    """Compute suburb + bed-band price benchmarks from our own sold House corpus."""
    prices, doms, sqm = [], [], []
    by_band, by_quarter = {}, {}
    for d in db[suburb].find({"listing_status": "sold", "property_type": "House"}):
        p = parse_price(d.get("sale_price"), d.get("listing_price"), d.get("last_sale_price"))
        if not p:
            continue
        prices.append(p)
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
    }

def segment_for(p, bench):
    """Return (label, array) — bed-band if it has enough samples, else all-houses."""
    bb = bed_band(p.get("bedrooms"))
    arr = bench["by_band"].get(bb) if bb else None
    if arr and len(arr) >= MIN_SEGMENT_N:
        return f"{bb} Robina houses".replace("Robina", bench["suburb"].replace("_", " ").title()), sorted(arr)
    disp = bench["suburb"].replace("_", " ").title()
    return f"{disp} houses", bench["prices"]

# ---------------------------------------------------------------- insight modules
# Each: (property, bench) -> Insight dict {type,text,evidence,tier,score} or None.
# `score` = notability (higher floats to the top). `tier` = data richness.

def m_price_vs_market(p, bench):
    price = parse_price(p.get("sale_price"), p.get("listing_price"))
    if not price or not bench["prices"]:
        return None
    label, arr = segment_for(p, bench)
    med = st.median(arr)
    delta = price - med
    pc = pctile(price, arr)
    if abs(delta) < max(0.02 * med, 15000):
        rel = f"in line with the {label} median of {money(med)}"
    else:
        rel = f"{money(abs(delta))} {'above' if delta > 0 else 'below'} the {label} median of {money(med)}"
    text = (f"Sold for {money(price)} — {rel} "
            f"({ordinal(pc)} percentile of {len(arr)} comparable sales).")
    return {"type": "price_vs_market", "text": text,
            "evidence": {"price": price, "median": med, "delta": delta,
                         "percentile": pc, "n": len(arr)},
            "tier": 1, "score": 40 + abs(delta) / max(med, 1) * 60}

def m_campaign_speed(p, bench):
    dom = p.get("days_on_market")
    if not isinstance(dom, (int, float)) or not bench["dom_median"]:
        return None
    med = bench["dom_median"]
    if dom <= med * 0.6:
        frame = f"notably faster than the suburb-wide median of {med:.0f} days"
    elif dom >= med * 1.5:
        frame = f"a longer campaign than the suburb-wide median of {med:.0f} days"
    else:
        frame = f"close to the suburb-wide median of {med:.0f} days"
    text = f"On the market {int(dom)} days before selling — {frame}."
    return {"type": "campaign_speed", "text": text,
            "evidence": {"dom": int(dom), "dom_median": med},
            "tier": 2, "score": 25 + abs(dom - med) / max(med, 1) * 30}

def m_configuration(p, bench):
    beds, baths = p.get("bedrooms"), p.get("bathrooms")
    car = p.get("carspaces", p.get("car_spaces"))
    if not beds:
        return None
    parts = [f"{int(beds)} bed"]
    if baths: parts.append(f"{int(baths)} bath")
    if car: parts.append(f"{int(car)} car")
    cfg = " / ".join(parts)
    fa = (p.get("floor_plan_analysis") or {}).get("internal_floor_area")
    tail = ""
    if isinstance(fa, (int, float)) and fa > 30 and bench["sqm"]:
        tail = f" across {fa:.0f} sqm of internal living"
    text = f"A {cfg} home{tail}."
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
    facts = []
    lvl = reno.get("overall_renovation_level")
    RENO = {"fully_renovated": "a fully renovated home",
            "extensively_renovated": "an extensively renovated home",
            "cosmetically_updated": "a cosmetically updated home",
            "partially_renovated": "a partially updated home",
            "original": "a home in original condition with scope to update"}
    if lvl in RENO:
        facts.append(RENO[lvl])
    if kit.get("benchtop_material") and kit.get("benchtop_material") != "unknown":
        km = kit["benchtop_material"]
        facts.append(f"{km} kitchen benchtops" + (" with premium appliances"
                     if kit.get("appliances_quality") == "premium" else ""))
    if score:
        facts.append(f"an overall condition of {int(score)}/10")
    if not facts:
        return None
    if len(facts) == 1:
        body = facts[0]
    else:
        body = ", ".join(facts[:-1]) + f", and {facts[-1]}"
    text = "Photo analysis shows " + body + "."
    # notability: strong (renovated / high score) OR clear update-opportunity both interesting
    notable = (score or 5)
    return {"type": "condition_finish", "text": text,
            "evidence": {"overall_condition_score": score, "renovation_level": lvl},
            "tier": 2, "score": 20 + abs((notable) - 5) * 4}

def m_character(p, bench):
    po = (p.get("property_valuation_data") or {}).get("property_overview") or {}
    style = po.get("architectural_style")
    stories = po.get("number_of_stories")
    if not style or style == "unknown":
        return None
    bits = f"{style} home"
    if stories:
        bits = f"{'single' if stories == 1 else 'two' if stories == 2 else stories}-level {style} home"
    text = f"{bits[0].upper()}{bits[1:]}."
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
    text = (f"Transacted in {q}, when the {disp} house median sat around "
            f"{money(med)} across {len(qarr)} recorded sales.")
    return {"type": "market_timing", "text": text,
            "evidence": {"quarter": q, "quarter_median": med, "n": len(qarr)},
            "tier": 2, "score": 12}

MODULES = [m_price_vs_market, m_campaign_speed, m_configuration,
           m_condition_finish, m_character, m_market_timing]

# ---------------------------------------------------------------- assembly
def build_headline(top, p):
    price = parse_price(p.get("sale_price"), p.get("listing_price"))
    if top and top["type"] == "price_vs_market":
        ev = top["evidence"]
        suburb_disp = (p.get("suburb") or "").strip()
        # Only lead the headline with a delta when it's positive (above median).
        # At/below median → neutral price headline (objective delta stays in the body).
        if ev["delta"] > max(0.02 * ev["median"], 15000):
            return f"Sold for {money(price)} — {money(ev['delta'])} above the {suburb_disp} house median"
        return f"Sold for {money(price)} in {suburb_disp}"
    if price:
        return f"Sold for {money(price)}"
    return f"Sold in {p.get('suburb','')}"

def build_summary(selected):
    # stitch top insights into a short objective paragraph
    return " ".join(s["text"] for s in selected[:3])

def analyse(p, bench):
    insights = [ins for m in MODULES if (ins := m(p, bench))]
    insights.sort(key=lambda x: x["score"], reverse=True)
    price = parse_price(p.get("sale_price"), p.get("listing_price"))
    completeness = round(len([i for i in insights]) / len(MODULES), 2)
    top = insights[0] if insights else None
    analysis = {
        "version": 1,
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
    real = parse_price(p.get("sale_price"), p.get("listing_price"))
    for ins in analysis["insights"]:
        if ins["type"] == "price_vs_market":
            if ins["evidence"]["price"] != real:
                problems.append("price mismatch vs source")
    return (not problems), problems

# ---------------------------------------------------------------- runner
def process(db, suburb, p, bench, dry, write):
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
    stats = {"published": 0, "needs_review": 0, "skipped_no_price": 0}
    for p in cur:
        if not parse_price(p.get("sale_price"), p.get("listing_price")):
            stats["skipped_no_price"] += 1
            continue
        status, ok = process(db, args.suburb, p, bench, args.dry_run, write)
        stats[status] = stats.get(status, 0) + 1
    print(f"\n[done] {stats}  (write={write})")
    client.close()

if __name__ == "__main__":
    main()
