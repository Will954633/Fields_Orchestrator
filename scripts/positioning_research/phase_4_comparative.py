#!/usr/bin/env python3
"""
Phase 4: Comparative Analysis — Property Positioning Research
==============================================================
"How do segments differ?"

Studies:
  4.1 - Suburb vs suburb (pure suburb premium, controlling for characteristics)
  4.2 - Agency vs agency (performance scorecard)
  4.3 - Renovated vs original (full impact profile)
  4.4 - Houses vs units/duplex/villa
"""

import json, os, re, sys, time
from collections import defaultdict, Counter
from datetime import datetime
import numpy as np
from scipy import stats as scipy_stats

sys.path.insert(0, "/home/fields/Fields_Orchestrator")
from shared.db import get_client

OUTPUT_DIR = "/home/fields/Fields_Orchestrator/output/positioning_research/phase_4"
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

def calc_stats(values):
    if not values or len(values) < 2: return None
    a = np.array(values)
    return {"count": len(values), "mean": round(float(np.mean(a)), 1), "median": round(float(np.median(a)), 1),
            "p25": round(float(np.percentile(a, 25)), 1), "p75": round(float(np.percentile(a, 75)), 1)}

def normalise_address(addr):
    if not addr: return ""
    addr = addr.upper().strip()
    addr = re.sub(r"\s*,\s*", " ", addr)
    addr = re.sub(r"\s+", " ", addr)
    addr = re.sub(r"\bQLD\b", "", addr).strip()
    addr = re.sub(r"\b\d{4}\b$", "", addr).strip()
    return addr

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
            d["_floor_area"] = ifa if isinstance(ifa, (int, float)) and ifa and ifa > 30 else None
        all_docs.extend(docs)
    print(f"  {len(all_docs)} records")

    # DOM from Gold_Coast
    gc_lookup = {}
    for suburb in TARGET_SUBURBS:
        time.sleep(2)
        for gc in db_gc[suburb].find({}, {"complete_address": 1, "scraped_data.property_timeline": 1}):
            norm = normalise_address(gc.get("complete_address", ""))
            if norm: gc_lookup[norm] = gc

    dom_count = 0
    for d in all_docs:
        if d.get("time_on_market_days") and isinstance(d["time_on_market_days"], (int, float)):
            d["_dom"] = int(d["time_on_market_days"]); dom_count += 1; continue
        norm = normalise_address(d.get("address", ""))
        gc = gc_lookup.get(norm) or gc_lookup.get(re.sub(r"^\d+/", "", norm))
        if gc:
            for ev in (safe_get(gc, "scraped_data.property_timeline") or []):
                if ev.get("is_sold") and ev.get("days_on_market"):
                    d["_dom"] = int(ev["days_on_market"]); dom_count += 1; break
    print(f"  DOM: {dom_count}")
    return all_docs


# ── Study 4.1: Suburb vs Suburb (controlled) ──────────────────────────────
def study_4_1(all_docs):
    print("\n═══ Study 4.1: Suburb vs Suburb — Controlled Comparison ═══")

    # Compare $/sqm for 4-bed houses across suburbs (most common segment)
    results = {"controlled_comparison_4bed_house": {}, "all_ppsqm": {}}

    for suburb in TARGET_SUBURBS:
        # 4-bed houses with $/sqm
        sd = [d for d in all_docs if d["_suburb"] == suburb and d.get("_ppsqm")
              and d.get("bedrooms") == 4 and d.get("property_type") == "House"]
        ppsqm = [d["_ppsqm"] for d in sd]
        if ppsqm:
            results["controlled_comparison_4bed_house"][suburb] = calc_stats(ppsqm)

        # All properties $/sqm
        all_p = [d["_ppsqm"] for d in all_docs if d["_suburb"] == suburb and d.get("_ppsqm")]
        if all_p:
            results["all_ppsqm"][suburb] = calc_stats(all_p)

    # Rank by $/sqm
    ranking = sorted(results["controlled_comparison_4bed_house"].items(),
                     key=lambda x: x[1]["median"] if x[1] else 0, reverse=True)

    # Compute premium relative to cheapest
    if ranking:
        base = ranking[-1][1]["median"]
        results["suburb_premium_vs_cheapest"] = {}
        for suburb, data in ranking:
            if data:
                prem = round(100 * (data["median"] / base - 1), 1)
                results["suburb_premium_vs_cheapest"][suburb] = {
                    "median_ppsqm": data["median"],
                    "premium_pct": prem,
                    "count": data["count"],
                }

    print("\n  4-bed house $/sqm ranking:")
    for suburb, data in ranking:
        if data:
            prem = results["suburb_premium_vs_cheapest"][suburb]["premium_pct"]
            print(f"    {suburb:20s} ${data['median']:,.0f}/sqm  ({prem:+.1f}% vs cheapest)  n={data['count']}")

    with open(os.path.join(OUTPUT_DIR, "study_4_1_suburb_comparison.json"), "w") as f:
        json.dump(results, f, indent=2)
    return results


# ── Study 4.2: Agency vs Agency Scorecard ─────────────────────────────────
def study_4_2(all_docs):
    print("\n═══ Study 4.2: Agency Performance Scorecard ═══")
    results = {}

    for suburb in CORE_SUBURBS:
        sd = [d for d in all_docs if d["_suburb"] == suburb and d["_numeric_price"]]

        # Compute cohort medians (suburb-bedroom)
        cohort_medians = {}
        for d in sd:
            beds = d.get("bedrooms")
            if beds:
                cohort_medians.setdefault(beds, []).append(d["_numeric_price"])
        for k in cohort_medians:
            cohort_medians[k] = np.median(cohort_medians[k])

        suburb_median_dom = np.median([d["_dom"] for d in sd if d.get("_dom") and d["_dom"] > 0]) if any(d.get("_dom") for d in sd) else None

        agencies = defaultdict(lambda: {"prices": [], "doms": [], "premiums": []})
        for d in sd:
            ag = d.get("agency_name")
            if not ag: continue
            agencies[ag]["prices"].append(d["_numeric_price"])
            if d.get("_dom") and d["_dom"] > 0:
                agencies[ag]["doms"].append(d["_dom"])
            beds = d.get("bedrooms")
            if beds and beds in cohort_medians and cohort_medians[beds] > 0:
                prem = (d["_numeric_price"] / cohort_medians[beds] - 1) * 100
                agencies[ag]["premiums"].append(prem)

        scorecards = []
        for ag, data in agencies.items():
            if len(data["prices"]) < 5:
                continue
            median_premium = round(float(np.median(data["premiums"])), 1) if data["premiums"] else None
            median_dom = round(float(np.median(data["doms"])), 1) if data["doms"] else None
            dom_residual = round(median_dom - suburb_median_dom, 1) if median_dom and suburb_median_dom else None

            # Quadrant classification
            fast = dom_residual is not None and dom_residual < 0
            expensive = median_premium is not None and median_premium > 0
            if fast and expensive:
                quadrant = "STAR (fast + above market)"
            elif fast and not expensive:
                quadrant = "QUICK (fast + below market)"
            elif not fast and expensive:
                quadrant = "SLOW_PREMIUM (slow + above market)"
            else:
                quadrant = "UNDERPERFORMER (slow + below market)"

            scorecards.append({
                "agency": ag,
                "sales": len(data["prices"]),
                "avg_price": int(np.mean(data["prices"])),
                "median_price": int(np.median(data["prices"])),
                "median_premium_vs_cohort_pct": median_premium,
                "median_dom": median_dom,
                "dom_residual": dom_residual,
                "quadrant": quadrant,
            })

        scorecards.sort(key=lambda x: -(x["median_premium_vs_cohort_pct"] or -999))

        results[suburb] = {
            "suburb_median_dom": round(float(suburb_median_dom), 1) if suburb_median_dom else None,
            "agencies": scorecards,
        }

        print(f"\n  {suburb.upper()} (suburb DOM: {suburb_median_dom:.0f}d):")
        for s in scorecards[:8]:
            prem_str = f"{s['median_premium_vs_cohort_pct']:+.1f}%" if s['median_premium_vs_cohort_pct'] is not None else "N/A"
            dom_str = f"{s['median_dom']:.0f}d ({s['dom_residual']:+.0f})" if s['median_dom'] else "no DOM"
            print(f"    {s['agency']:40s} {s['sales']:2d} sales  premium={prem_str:>7s}  DOM={dom_str:>12s}  [{s['quadrant']}]")

    with open(os.path.join(OUTPUT_DIR, "study_4_2_agency_scorecard.json"), "w") as f:
        json.dump(results, f, indent=2)
    return results


# ── Study 4.3: Renovated vs Original ──────────────────────────────────────
def study_4_3(all_docs):
    print("\n═══ Study 4.3: Renovated vs Original — Full Comparison ═══")
    results = {}

    for suburb in CORE_SUBURBS:
        sd = [d for d in all_docs if d["_suburb"] == suburb and d["_numeric_price"]]

        reno_groups = {
            "fully_renovated": [d for d in sd if safe_get(d, "property_valuation_data.renovation.overall_renovation_level") == "fully_renovated"],
            "cosmetically_updated": [d for d in sd if safe_get(d, "property_valuation_data.renovation.overall_renovation_level") == "cosmetically_updated"],
            "original_or_partial": [d for d in sd if safe_get(d, "property_valuation_data.renovation.overall_renovation_level") in ("original", "partially_renovated", "tired")],
            "new_build": [d for d in sd if safe_get(d, "property_valuation_data.renovation.overall_renovation_level") == "new_build"],
        }

        group_profiles = {}
        for gname, docs in reno_groups.items():
            if len(docs) < 3:
                continue
            prices = [d["_numeric_price"] for d in docs if d["_numeric_price"]]
            ppsqm = [d["_ppsqm"] for d in docs if d.get("_ppsqm")]
            doms = [d["_dom"] for d in docs if d.get("_dom") and d["_dom"] > 0]
            beds = Counter(d.get("bedrooms") for d in docs if d.get("bedrooms"))
            areas = [d["_floor_area"] for d in docs if d.get("_floor_area")]
            pool_pct = round(100 * sum(1 for d in docs if safe_get(d, "property_valuation_data.outdoor.pool_present") is True) / len(docs), 1)

            group_profiles[gname] = {
                "count": len(docs),
                "price": calc_stats(prices),
                "ppsqm": calc_stats(ppsqm),
                "dom": calc_stats(doms),
                "typical_beds": beds.most_common(1)[0][0] if beds else None,
                "median_floor_area": round(float(np.median(areas)), 0) if areas else None,
                "pool_pct": pool_pct,
            }

        results[suburb] = group_profiles

        print(f"\n  {suburb.upper()}:")
        for gname, prof in sorted(group_profiles.items(), key=lambda x: x[1]["ppsqm"]["median"] if x[1]["ppsqm"] else 0, reverse=True):
            price_med = f"${prof['price']['median']:,.0f}" if prof['price'] else "-"
            ppsqm_med = f"${prof['ppsqm']['median']:,.0f}" if prof['ppsqm'] else "-"
            dom_med = f"{prof['dom']['median']:.0f}d" if prof['dom'] else "-"
            print(f"    {gname:25s} n={prof['count']:3d}  price={price_med:>12s}  $/sqm={ppsqm_med:>8s}  DOM={dom_med:>5s}  area={prof['median_floor_area'] or '-'}sqm")

    with open(os.path.join(OUTPUT_DIR, "study_4_3_renovation.json"), "w") as f:
        json.dump(results, f, indent=2)
    return results


# ── Study 4.4: Houses vs Units/Duplex/Villa ──────────────────────────────
def study_4_4(all_docs):
    print("\n═══ Study 4.4: Houses vs Duplex/Villa ═══")
    results = {}

    for suburb in CORE_SUBURBS:
        sd = [d for d in all_docs if d["_suburb"] == suburb and d["_numeric_price"]]

        type_groups = defaultdict(list)
        for d in sd:
            pt = d.get("property_type", "Unknown")
            if pt == "House":
                type_groups["House"].append(d)
            else:
                type_groups["Duplex/Villa/Other"].append(d)

        group_profiles = {}
        for gname, docs in type_groups.items():
            prices = [d["_numeric_price"] for d in docs if d["_numeric_price"]]
            ppsqm = [d["_ppsqm"] for d in docs if d.get("_ppsqm")]
            doms = [d["_dom"] for d in docs if d.get("_dom") and d["_dom"] > 0]
            beds = Counter(d.get("bedrooms") for d in docs if d.get("bedrooms"))
            areas = [d["_floor_area"] for d in docs if d.get("_floor_area")]

            group_profiles[gname] = {
                "count": len(docs),
                "price": calc_stats(prices),
                "ppsqm": calc_stats(ppsqm),
                "dom": calc_stats(doms),
                "typical_beds": beds.most_common(1)[0][0] if beds else None,
                "bed_distribution": dict(sorted(beds.items())),
                "median_floor_area": round(float(np.median(areas)), 0) if areas else None,
            }

        results[suburb] = group_profiles

        print(f"\n  {suburb.upper()}:")
        for gname, prof in group_profiles.items():
            price_med = f"${prof['price']['median']:,.0f}" if prof['price'] else "-"
            ppsqm_med = f"${prof['ppsqm']['median']:,.0f}" if prof['ppsqm'] else "-"
            print(f"    {gname:25s} n={prof['count']:3d}  price={price_med:>12s}  $/sqm={ppsqm_med:>8s}  beds={prof['typical_beds']}  area={prof['median_floor_area'] or '-'}sqm")

    with open(os.path.join(OUTPUT_DIR, "study_4_4_property_types.json"), "w") as f:
        json.dump(results, f, indent=2)
    return results


# ── Summary ────────────────────────────────────────────────────────────────
def generate_summary(s41, s42, s43, s44):
    md = []
    md.append("# Phase 4: Comparative Analysis — \"How Do Segments Differ?\"")
    md.append(f"## Generated {datetime.now().strftime('%Y-%m-%d %H:%M AEST')}")

    md.append("\n---\n## 4.1 Suburb Ranking (4-bed houses, $/sqm)")
    md.append("| Rank | Suburb | Median $/sqm | Premium vs Cheapest | N |")
    md.append("|------|--------|-------------|--------------------|----|")
    ranking = sorted(s41.get("suburb_premium_vs_cheapest", {}).items(), key=lambda x: -x[1]["premium_pct"])
    for i, (suburb, data) in enumerate(ranking, 1):
        md.append(f"| {i} | {suburb} | ${data['median_ppsqm']:,.0f} | {data['premium_pct']:+.1f}% | {data['count']} |")

    md.append("\n---\n## 4.2 Agency Scorecards")
    for suburb in CORE_SUBURBS:
        r = s42[suburb]
        md.append(f"\n### {suburb.replace('_',' ').title()} (suburb DOM: {r['suburb_median_dom']}d)")
        md.append("| Agency | Sales | Premium vs Cohort | Median DOM | DOM Residual | Quadrant |")
        md.append("|--------|-------|-------------------|-----------|-------------|----------|")
        for a in r["agencies"][:10]:
            prem = f"{a['median_premium_vs_cohort_pct']:+.1f}%" if a['median_premium_vs_cohort_pct'] is not None else "N/A"
            dom = f"{a['median_dom']:.0f}d" if a['median_dom'] else "-"
            res = f"{a['dom_residual']:+.0f}d" if a['dom_residual'] is not None else "-"
            md.append(f"| {a['agency']} | {a['sales']} | {prem} | {dom} | {res} | {a['quadrant']} |")

    md.append("\n---\n## 4.3 Renovated vs Original")
    for suburb in CORE_SUBURBS:
        md.append(f"\n### {suburb.replace('_',' ').title()}")
        md.append("| Level | Count | Median Price | Median $/sqm | Median DOM | Area |")
        md.append("|-------|-------|-------------|-------------|-----------|------|")
        for level, prof in sorted(s43[suburb].items(), key=lambda x: x[1]["ppsqm"]["median"] if x[1]["ppsqm"] else 0, reverse=True):
            price = f"${prof['price']['median']:,.0f}" if prof['price'] else "-"
            ppsqm = f"${prof['ppsqm']['median']:,.0f}" if prof['ppsqm'] else "-"
            dom = f"{prof['dom']['median']:.0f}d" if prof['dom'] else "-"
            md.append(f"| {level} | {prof['count']} | {price} | {ppsqm} | {dom} | {prof['median_floor_area'] or '-'}sqm |")

    md.append("\n---\n## 4.4 Houses vs Duplex/Villa")
    for suburb in CORE_SUBURBS:
        md.append(f"\n### {suburb.replace('_',' ').title()}")
        md.append("| Type | Count | Median Price | Median $/sqm | Beds | Area |")
        md.append("|------|-------|-------------|-------------|------|------|")
        for gname, prof in s44[suburb].items():
            price = f"${prof['price']['median']:,.0f}" if prof['price'] else "-"
            ppsqm = f"${prof['ppsqm']['median']:,.0f}" if prof['ppsqm'] else "-"
            md.append(f"| {gname} | {prof['count']} | {price} | {ppsqm} | {prof['typical_beds']}-bed | {prof['median_floor_area'] or '-'}sqm |")

    md.append(f"\n---\n*Fields Estate — Phase 4 | {datetime.now().strftime('%Y-%m-%d')}*")
    path = "/home/fields/Fields_Orchestrator/output/positioning_research/phase_4_summary.md"
    with open(path, "w") as f:
        f.write("\n".join(md))
    print(f"\n  Summary: {path}")

def main():
    print("╔═══════════════════════════════════════════════════════════════╗")
    print("║  Phase 4: Comparative Analysis — Positioning Research         ║")
    print("╚═══════════════════════════════════════════════════════════════╝")
    all_docs = load_all_data()
    s41 = study_4_1(all_docs)
    s42 = study_4_2(all_docs)
    s43 = study_4_3(all_docs)
    s44 = study_4_4(all_docs)
    generate_summary(s41, s42, s43, s44)
    print("\n" + "=" * 60)
    print("Phase 4 COMPLETE")
    print("=" * 60)

if __name__ == "__main__":
    main()
