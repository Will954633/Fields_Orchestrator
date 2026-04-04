#!/usr/bin/env python3
"""
Phase 6: Text Analysis — Property Positioning Research
=======================================================
"What language sells?"

Studies:
  6.1 - Description length and complexity vs outcomes
  6.2 - Keyword frequency and impact
  6.3 - Description vs reality gap
"""

import json, os, re, sys, time
from collections import defaultdict, Counter
from datetime import datetime
import numpy as np
from scipy import stats as scipy_stats

sys.path.insert(0, "/home/fields/Fields_Orchestrator")
from shared.db import get_client

OUTPUT_DIR = "/home/fields/Fields_Orchestrator/output/positioning_research/phase_6"
os.makedirs(OUTPUT_DIR, exist_ok=True)
TARGET_SUBURBS = ["robina", "varsity_lakes", "burleigh_waters", "mudgeeraba", "merrimac", "carrara", "worongary", "reedy_creek"]
CORE_SUBURBS = ["robina", "varsity_lakes", "burleigh_waters"]

client = get_client()
db_target = client["Target_Market_Sold_Last_12_Months"]
db_gc = client["Gold_Coast"]

def parse_price(s):
    if not s or not isinstance(s, str): return None
    m = re.search(r"(\d{6,})", s.replace(",", "").replace("$", ""))
    return int(m.group(1)) if m else None

def safe_get(doc, path, default=None):
    parts = path.split(".")
    cur = doc
    for p in parts:
        if isinstance(cur, dict): cur = cur.get(p)
        else: return default
        if cur is None: return default
    return cur

def normalise_address(addr):
    if not addr: return ""
    addr = addr.upper().strip()
    addr = re.sub(r"\s*,\s*", " ", addr)
    addr = re.sub(r"\s+", " ", addr)
    addr = re.sub(r"\bQLD\b", "", addr).strip()
    addr = re.sub(r"\b\d{4}\b$", "", addr).strip()
    return addr

def calc_stats(values):
    if not values or len(values) < 2: return None
    a = np.array(values)
    return {"count": len(values), "mean": round(float(np.mean(a)), 1), "median": round(float(np.median(a)), 1)}

def spearman_corr(x, y):
    if len(x) < 10 or len(x) != len(y): return None, None
    try:
        r, p = scipy_stats.spearmanr(x, y)
        return round(float(r), 3), round(float(p), 4)
    except: return None, None

def load_all_data():
    print("Loading data...")
    all_docs = []
    for suburb in TARGET_SUBURBS:
        time.sleep(1)
        docs = list(db_target[suburb].find({}))
        for d in docs:
            d["_suburb"] = suburb
            d["_numeric_price"] = parse_price(d.get("sale_price"))
            ifa = safe_get(d, "floor_plan_analysis.internal_floor_area.value")
            d["_ppsqm"] = (d["_numeric_price"] / ifa) if (d["_numeric_price"] and ifa and isinstance(ifa, (int, float)) and ifa > 30) else None
        all_docs.extend(docs)

    # DOM from Gold_Coast
    gc_lookup = {}
    for suburb in TARGET_SUBURBS:
        time.sleep(4)
        try:
            for gc in db_gc[suburb].find({}, {"complete_address": 1, "scraped_data.property_timeline": 1}):
                norm = normalise_address(gc.get("complete_address", ""))
                if norm: gc_lookup[norm] = gc
        except Exception as e:
            if "16500" in str(e):
                print(f"  RU throttled on {suburb}, waiting...")
                time.sleep(10)

    for d in all_docs:
        if d.get("time_on_market_days") and isinstance(d["time_on_market_days"], (int, float)):
            d["_dom"] = int(d["time_on_market_days"]); continue
        norm = normalise_address(d.get("address", ""))
        gc = gc_lookup.get(norm) or gc_lookup.get(re.sub(r"^\d+/", "", norm))
        if gc:
            for ev in (safe_get(gc, "scraped_data.property_timeline") or []):
                if ev.get("is_sold") and ev.get("days_on_market"):
                    d["_dom"] = int(ev["days_on_market"]); break

    print(f"  {len(all_docs)} records")
    return all_docs


# ── Study 6.1: Description Length/Complexity vs Outcomes ──────────────────
def study_6_1(all_docs):
    print("\n═══ Study 6.1: Description Length and Complexity ═══")
    results = {}

    for suburb in CORE_SUBURBS:
        sd = [d for d in all_docs if d["_suburb"] == suburb and d.get("agents_description") and d["_numeric_price"]]

        rows = []
        for d in sd:
            desc = d["agents_description"]
            words = desc.split()
            word_count = len(words)
            sentence_count = max(1, len(re.split(r'[.!?]+', desc)))
            unique_words = len(set(w.lower() for w in words))
            unique_ratio = unique_words / word_count if word_count > 0 else 0
            avg_word_len = np.mean([len(w) for w in words]) if words else 0
            has_emoji = bool(re.search(r'[\U0001F300-\U0001F9FF]', desc))
            exclamation_count = desc.count("!")

            rows.append({
                "word_count": word_count,
                "sentence_count": sentence_count,
                "unique_ratio": round(unique_ratio, 3),
                "avg_word_len": round(avg_word_len, 1),
                "has_emoji": has_emoji,
                "exclamation_count": exclamation_count,
                "price": d["_numeric_price"],
                "ppsqm": d.get("_ppsqm"),
                "dom": d.get("_dom"),
            })

        # Correlations
        word_counts = [r["word_count"] for r in rows]
        prices = [r["price"] for r in rows]
        ppsqm = [r["ppsqm"] for r in rows if r["ppsqm"]]
        wc_for_ppsqm = [r["word_count"] for r in rows if r["ppsqm"]]
        doms = [r["dom"] for r in rows if r.get("dom") and r["dom"] > 0]
        wc_for_dom = [r["word_count"] for r in rows if r.get("dom") and r["dom"] > 0]

        wc_price_r, wc_price_p = spearman_corr(word_counts, prices)
        wc_ppsqm_r, wc_ppsqm_p = spearman_corr(wc_for_ppsqm, ppsqm)
        wc_dom_r, wc_dom_p = spearman_corr(wc_for_dom, doms)

        # Bucket analysis (short vs medium vs long descriptions)
        buckets = {"short_under_50": [], "medium_50_100": [], "long_100_200": [], "very_long_200_plus": []}
        for r in rows:
            wc = r["word_count"]
            if wc < 50: buckets["short_under_50"].append(r)
            elif wc < 100: buckets["medium_50_100"].append(r)
            elif wc < 200: buckets["long_100_200"].append(r)
            else: buckets["very_long_200_plus"].append(r)

        bucket_stats = {}
        for bname, docs in buckets.items():
            bp = [r["price"] for r in docs]
            bd = [r["dom"] for r in docs if r.get("dom") and r["dom"] > 0]
            bucket_stats[bname] = {
                "count": len(docs),
                "median_price": int(np.median(bp)) if bp else None,
                "median_dom": round(float(np.median(bd)), 1) if bd else None,
            }

        results[suburb] = {
            "description_stats": {
                "word_count": calc_stats(word_counts),
                "unique_ratio": calc_stats([r["unique_ratio"] for r in rows]),
            },
            "correlations": {
                "word_count_vs_price": {"r": wc_price_r, "p": wc_price_p},
                "word_count_vs_ppsqm": {"r": wc_ppsqm_r, "p": wc_ppsqm_p},
                "word_count_vs_dom": {"r": wc_dom_r, "p": wc_dom_p},
            },
            "by_length_bucket": bucket_stats,
        }

        wc_stats = calc_stats(word_counts)
        print(f"  {suburb}: avg {wc_stats['mean']:.0f} words, median {wc_stats['median']:.0f}")
        print(f"    words→price: r={wc_price_r}, words→$/sqm: r={wc_ppsqm_r}, words→DOM: r={wc_dom_r}")

    with open(os.path.join(OUTPUT_DIR, "study_6_1_length.json"), "w") as f:
        json.dump(results, f, indent=2)
    return results


# ── Study 6.2: Keyword Frequency and Impact ───────────────────────────────
def study_6_2(all_docs):
    print("\n═══ Study 6.2: Keyword Frequency and Impact ═══")
    results = {}

    # Target keywords (property marketing vocabulary)
    keywords = [
        "renovated", "modern", "spacious", "entertainer", "family", "luxury",
        "pool", "waterfront", "canal", "views", "private", "quiet", "open plan",
        "kitchen", "stone", "natural light", "indoor outdoor", "alfresco",
        "master suite", "ensuite", "walk-in", "ducted", "air conditioning",
        "solar", "double garage", "side access", "corner", "cul-de-sac",
        "school", "shops", "parkland", "lifestyle", "immaculate", "pristine",
        "opportunity", "potential", "investor", "downsizer", "first home",
        "low maintenance", "north facing", "tropical", "resort", "dream",
        "large block", "land", "shed", "granny flat", "dual living",
        "timber", "polished", "Hampton", "Hamptons", "coastal", "contemporary",
    ]

    for suburb in CORE_SUBURBS:
        sd = [d for d in all_docs if d["_suburb"] == suburb and d.get("agents_description") and d["_numeric_price"]]

        keyword_results = []
        for kw in keywords:
            kw_lower = kw.lower()
            with_kw = [d for d in sd if kw_lower in d["agents_description"].lower()]
            without_kw = [d for d in sd if kw_lower not in d["agents_description"].lower()]

            if len(with_kw) < 5 or len(without_kw) < 5:
                continue

            with_prices = [d["_numeric_price"] for d in with_kw]
            without_prices = [d["_numeric_price"] for d in without_kw]
            with_ppsqm = [d["_ppsqm"] for d in with_kw if d.get("_ppsqm")]
            without_ppsqm = [d["_ppsqm"] for d in without_kw if d.get("_ppsqm")]
            with_dom = [d["_dom"] for d in with_kw if d.get("_dom") and d["_dom"] > 0]
            without_dom = [d["_dom"] for d in without_kw if d.get("_dom") and d["_dom"] > 0]

            price_premium = round(100 * (np.median(with_prices) / np.median(without_prices) - 1), 1)
            ppsqm_premium = round(100 * (np.median(with_ppsqm) / np.median(without_ppsqm) - 1), 1) if with_ppsqm and without_ppsqm else None
            dom_diff = round(float(np.median(with_dom) - np.median(without_dom)), 1) if with_dom and without_dom else None

            keyword_results.append({
                "keyword": kw,
                "frequency": len(with_kw),
                "frequency_pct": round(100 * len(with_kw) / len(sd), 1),
                "price_premium_pct": price_premium,
                "ppsqm_premium_pct": ppsqm_premium,
                "dom_diff_days": dom_diff,
            })

        # Sort by |price_premium|
        keyword_results.sort(key=lambda x: abs(x["price_premium_pct"]), reverse=True)

        results[suburb] = {
            "total_listings": len(sd),
            "keywords": keyword_results,
            "top_premium_keywords": [k for k in keyword_results if k["price_premium_pct"] > 10][:10],
            "top_discount_keywords": [k for k in keyword_results if k["price_premium_pct"] < -10][:10],
            "top_speed_keywords": [k for k in keyword_results if k.get("dom_diff_days") and k["dom_diff_days"] < -5][:10],
        }

        print(f"\n  {suburb.upper()} ({len(sd)} listings):")
        print(f"    Top premium keywords:")
        for k in results[suburb]["top_premium_keywords"][:5]:
            print(f"      '{k['keyword']}': +{k['price_premium_pct']}% price, {k['frequency']} listings ({k['frequency_pct']}%)")
        print(f"    Top discount keywords:")
        for k in results[suburb]["top_discount_keywords"][:5]:
            print(f"      '{k['keyword']}': {k['price_premium_pct']}% price, {k['frequency']} listings ({k['frequency_pct']}%)")

    with open(os.path.join(OUTPUT_DIR, "study_6_2_keywords.json"), "w") as f:
        json.dump(results, f, indent=2)
    return results


# ── Study 6.3: Description vs Reality Gap ─────────────────────────────────
def study_6_3(all_docs):
    print("\n═══ Study 6.3: Description vs Reality Gap ═══")
    results = {}

    claim_checks = {
        "claims_renovated": {
            "text_match": lambda desc: any(w in desc.lower() for w in ["renovated", "brand new kitchen", "new bathroom"]),
            "reality_check": lambda d: safe_get(d, "property_valuation_data.renovation.overall_renovation_level") in ("fully_renovated", "new_build"),
        },
        "claims_pool": {
            "text_match": lambda desc: "pool" in desc.lower(),
            "reality_check": lambda d: safe_get(d, "property_valuation_data.outdoor.pool_present") is True,
        },
        "claims_views": {
            "text_match": lambda desc: any(w in desc.lower() for w in ["views", "water views", "canal views"]),
            "reality_check": lambda d: safe_get(d, "property_valuation_data.outdoor.water_views") is True,
        },
    }

    for suburb in CORE_SUBURBS:
        sd = [d for d in all_docs if d["_suburb"] == suburb and d.get("agents_description") and d["_numeric_price"]]

        suburb_results = {}
        for claim_name, checks in claim_checks.items():
            claims_it = [d for d in sd if checks["text_match"](d["agents_description"])]
            doesnt_claim = [d for d in sd if not checks["text_match"](d["agents_description"])]

            # Of those that claim it, how many actually have it?
            accurate = [d for d in claims_it if checks["reality_check"](d)]
            inaccurate = [d for d in claims_it if not checks["reality_check"](d)]

            accuracy_rate = round(100 * len(accurate) / len(claims_it), 1) if claims_it else 0

            suburb_results[claim_name] = {
                "claims_count": len(claims_it),
                "claims_pct": round(100 * len(claims_it) / len(sd), 1),
                "accurate": len(accurate),
                "inaccurate": len(inaccurate),
                "accuracy_rate": accuracy_rate,
            }

        results[suburb] = suburb_results

        print(f"\n  {suburb.upper()}:")
        for claim, data in suburb_results.items():
            print(f"    {claim:25s} claims={data['claims_count']} ({data['claims_pct']}%), accurate={data['accuracy_rate']}%")

    with open(os.path.join(OUTPUT_DIR, "study_6_3_reality_gap.json"), "w") as f:
        json.dump(results, f, indent=2)
    return results


# ── Summary ────────────────────────────────────────────────────────────────
def generate_summary(s61, s62, s63):
    md = []
    md.append("# Phase 6: Text Analysis — \"What Language Sells?\"")
    md.append(f"## Generated {datetime.now().strftime('%Y-%m-%d %H:%M AEST')}")

    md.append("\n---\n## 6.1 Description Length vs Outcomes")
    for suburb in CORE_SUBURBS:
        r = s61[suburb]
        md.append(f"\n### {suburb.replace('_',' ').title()}")
        wc = r["description_stats"]["word_count"]
        md.append(f"- Average description: {wc['mean']:.0f} words (median {wc['median']:.0f})")
        c = r["correlations"]
        md.append(f"- Word count → price: r={c['word_count_vs_price']['r']}")
        md.append(f"- Word count → $/sqm: r={c['word_count_vs_ppsqm']['r']}")
        md.append(f"- Word count → DOM: r={c['word_count_vs_dom']['r']}")
        md.append("\n| Length Bucket | Count | Median Price | Median DOM |")
        md.append("|-------------|-------|-------------|-----------|")
        for bname, data in r["by_length_bucket"].items():
            price = f"${data['median_price']:,}" if data["median_price"] else "-"
            dom = f"{data['median_dom']}d" if data["median_dom"] else "-"
            md.append(f"| {bname} | {data['count']} | {price} | {dom} |")

    md.append("\n---\n## 6.2 Keyword Impact")
    for suburb in CORE_SUBURBS:
        r = s62[suburb]
        md.append(f"\n### {suburb.replace('_',' ').title()}")
        md.append("\n**Premium keywords (listings with this word sell for MORE):**")
        md.append("| Keyword | Frequency | Price Premium | $/sqm Premium | DOM Diff |")
        md.append("|---------|-----------|--------------|---------------|---------|")
        for k in r["top_premium_keywords"][:8]:
            ppsqm = f"{k['ppsqm_premium_pct']:+.1f}%" if k["ppsqm_premium_pct"] is not None else "-"
            dom = f"{k['dom_diff_days']:+.1f}d" if k["dom_diff_days"] is not None else "-"
            md.append(f"| {k['keyword']} | {k['frequency']} ({k['frequency_pct']}%) | {k['price_premium_pct']:+.1f}% | {ppsqm} | {dom} |")

        md.append("\n**Discount keywords (listings with this word sell for LESS):**")
        md.append("| Keyword | Frequency | Price Premium | DOM Diff |")
        md.append("|---------|-----------|--------------|---------|")
        for k in r["top_discount_keywords"][:8]:
            dom = f"{k['dom_diff_days']:+.1f}d" if k["dom_diff_days"] is not None else "-"
            md.append(f"| {k['keyword']} | {k['frequency']} ({k['frequency_pct']}%) | {k['price_premium_pct']:+.1f}% | {dom} |")

    md.append("\n---\n## 6.3 Description vs Reality")
    for suburb in CORE_SUBURBS:
        r = s63[suburb]
        md.append(f"\n### {suburb.replace('_',' ').title()}")
        md.append("| Claim | Listings Making Claim | Accuracy |")
        md.append("|-------|----------------------|----------|")
        for claim, data in r.items():
            md.append(f"| {claim} | {data['claims_count']} ({data['claims_pct']}%) | {data['accuracy_rate']}% |")

    md.append(f"\n---\n*Fields Estate — Phase 6 | {datetime.now().strftime('%Y-%m-%d')}*")
    path = "/home/fields/Fields_Orchestrator/output/positioning_research/phase_6_summary.md"
    with open(path, "w") as f:
        f.write("\n".join(md))
    print(f"\n  Summary: {path}")

def main():
    print("╔═══════════════════════════════════════════════════════════════╗")
    print("║  Phase 6: Text Analysis — Positioning Research                ║")
    print("╚═══════════════════════════════════════════════════════════════╝")
    all_docs = load_all_data()
    s61 = study_6_1(all_docs)
    s62 = study_6_2(all_docs)
    s63 = study_6_3(all_docs)
    generate_summary(s61, s62, s63)
    print("\n" + "=" * 60)
    print("Phase 6 COMPLETE")
    print("=" * 60)

if __name__ == "__main__":
    main()
