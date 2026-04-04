#!/usr/bin/env python3
"""
Phase 7+8: Spatial & Temporal Analysis — Property Positioning Research
======================================================================
Phase 7: "Where matters?" — Street-level premiums, proximity gradients
Phase 8: "When matters?" — Seasonal patterns, market momentum, capital growth
"""

import json, os, re, sys, time
from collections import defaultdict, Counter
from datetime import datetime
import numpy as np
from scipy import stats as scipy_stats

sys.path.insert(0, "/home/fields/Fields_Orchestrator")
from shared.db import get_client

OUTPUT_DIR_7 = "/home/fields/Fields_Orchestrator/output/positioning_research/phase_7"
OUTPUT_DIR_8 = "/home/fields/Fields_Orchestrator/output/positioning_research/phase_8"
os.makedirs(OUTPUT_DIR_7, exist_ok=True)
os.makedirs(OUTPUT_DIR_8, exist_ok=True)
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
    return {"count": len(values), "mean": round(float(np.mean(a)), 1), "median": round(float(np.median(a)), 1)}

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
        all_docs.extend(docs)

    # Gold_Coast match for coordinates + timeline + road data
    gc_lookup = {}
    for suburb in TARGET_SUBURBS:
        time.sleep(4)
        retries = 0
        while retries < 3:
            try:
                for gc in db_gc[suburb].find({}, {
                    "complete_address": 1, "LATITUDE": 1, "LONGITUDE": 1,
                    "STREET_NAME": 1, "osm_location_features": 1,
                    "scraped_data.property_timeline": 1, "scraped_data.valuation": 1
                }):
                    norm = normalise_address(gc.get("complete_address", ""))
                    if norm: gc_lookup[norm] = gc
                break
            except Exception as e:
                if "16500" in str(e):
                    retries += 1; time.sleep(5 * retries)
                else: raise

    for d in all_docs:
        norm = normalise_address(d.get("address", ""))
        gc = gc_lookup.get(norm) or gc_lookup.get(re.sub(r"^\d+/", "", norm))
        if gc:
            d["_lat"] = gc.get("LATITUDE")
            d["_lon"] = gc.get("LONGITUDE")
            d["_street"] = gc.get("STREET_NAME")
            d["_osm"] = gc.get("osm_location_features")
            d["_timeline"] = safe_get(gc, "scraped_data.property_timeline") or []
            # DOM
            for ev in d["_timeline"]:
                if ev.get("is_sold") and ev.get("days_on_market"):
                    d["_dom"] = int(ev["days_on_market"]); break
        if not d.get("_dom") and d.get("time_on_market_days") and isinstance(d["time_on_market_days"], (int, float)):
            d["_dom"] = int(d["time_on_market_days"])

    print(f"  {len(all_docs)} records, {sum(1 for d in all_docs if d.get('_lat'))} with coords")
    return all_docs


# ── Study 7.2: Street-Level Premium Analysis ─────────────────────────────
def study_7_2(all_docs):
    print("\n═══ Study 7.2: Street-Level Premium Analysis ═══")
    results = {}

    for suburb in CORE_SUBURBS:
        sd = [d for d in all_docs if d["_suburb"] == suburb and d.get("_ppsqm") and d.get("_street")]
        suburb_median_ppsqm = np.median([d["_ppsqm"] for d in sd])

        streets = defaultdict(list)
        for d in sd:
            streets[d["_street"]].append(d["_ppsqm"])

        street_results = []
        for street, ppsqms in streets.items():
            if len(ppsqms) < 3:
                continue
            median_ppsqm = np.median(ppsqms)
            premium = round(100 * (median_ppsqm / suburb_median_ppsqm - 1), 1)
            street_results.append({
                "street": street,
                "sales": len(ppsqms),
                "median_ppsqm": round(float(median_ppsqm), 0),
                "premium_pct": premium,
            })

        street_results.sort(key=lambda x: -x["premium_pct"])
        results[suburb] = {
            "suburb_median_ppsqm": round(float(suburb_median_ppsqm), 0),
            "streets_analysed": len(street_results),
            "premium_streets": street_results[:10],
            "discount_streets": street_results[-10:],
        }

        print(f"\n  {suburb.upper()} (median $/sqm: ${suburb_median_ppsqm:,.0f}):")
        print(f"    Top premium streets:")
        for s in street_results[:5]:
            print(f"      {s['street']:25s} ${s['median_ppsqm']:,.0f}/sqm ({s['premium_pct']:+.1f}%) n={s['sales']}")
        print(f"    Top discount streets:")
        for s in street_results[-3:]:
            print(f"      {s['street']:25s} ${s['median_ppsqm']:,.0f}/sqm ({s['premium_pct']:+.1f}%) n={s['sales']}")

    with open(os.path.join(OUTPUT_DIR_7, "study_7_2_streets.json"), "w") as f:
        json.dump(results, f, indent=2)
    return results


# ── Study 7.4: Traffic/Road Impact ────────────────────────────────────────
def study_7_4(all_docs):
    print("\n═══ Study 7.4: Traffic and Road Exposure ═══")
    results = {}

    for suburb in CORE_SUBURBS:
        sd = [d for d in all_docs if d["_suburb"] == suburb and d.get("_ppsqm") and d.get("_osm")]

        # Road type vs $/sqm
        road_types = defaultdict(list)
        for d in sd:
            rt = safe_get(d, "_osm.road_classification.nearest_road_type")
            if rt: road_types[rt].append(d["_ppsqm"])

        # Traffic score buckets
        traffic_buckets = {"low_1_3": [], "medium_4_6": [], "high_7_10": []}
        for d in sd:
            ts = safe_get(d, "_osm.road_classification.traffic_exposure_score")
            if ts and isinstance(ts, (int, float)):
                if ts <= 3: traffic_buckets["low_1_3"].append(d["_ppsqm"])
                elif ts <= 6: traffic_buckets["medium_4_6"].append(d["_ppsqm"])
                else: traffic_buckets["high_7_10"].append(d["_ppsqm"])

        results[suburb] = {
            "by_road_type": {rt: calc_stats(ppsqms) for rt, ppsqms in road_types.items() if len(ppsqms) >= 3},
            "by_traffic_exposure": {tb: calc_stats(ppsqms) for tb, ppsqms in traffic_buckets.items() if ppsqms},
        }

        print(f"\n  {suburb.upper()}:")
        for rt, data in sorted(results[suburb]["by_road_type"].items(), key=lambda x: x[1]["median"] if x[1] else 0, reverse=True):
            if data:
                print(f"    {rt:20s} $/sqm=${data['median']:,.0f} (n={data['count']})")
        for tb, data in results[suburb]["by_traffic_exposure"].items():
            if data:
                print(f"    traffic {tb:12s} $/sqm=${data['median']:,.0f} (n={data['count']})")

    with open(os.path.join(OUTPUT_DIR_7, "study_7_4_traffic.json"), "w") as f:
        json.dump(results, f, indent=2)
    return results


# ── Study 8.1: Seasonal Patterns ─────────────────────────────────────────
def study_8_1(all_docs):
    print("\n═══ Study 8.1: Seasonal Patterns ═══")
    results = {}

    for suburb in CORE_SUBURBS:
        sd = [d for d in all_docs if d["_suburb"] == suburb and d["_numeric_price"]]

        by_month = defaultdict(lambda: {"prices": [], "doms": [], "count": 0})
        for d in sd:
            dt = d.get("sale_date", "")
            if dt and len(dt) >= 7:
                month = int(dt[5:7])
                by_month[month]["prices"].append(d["_numeric_price"])
                by_month[month]["count"] += 1
                if d.get("_dom") and d["_dom"] > 0:
                    by_month[month]["doms"].append(d["_dom"])

        annual_median = np.median([d["_numeric_price"] for d in sd])
        monthly_results = {}
        for m in range(1, 13):
            data = by_month[m]
            month_name = datetime(2026, m, 1).strftime("%B")
            median_price = int(np.median(data["prices"])) if data["prices"] else None
            price_index = round(100 * median_price / annual_median, 1) if median_price else None
            median_dom = round(float(np.median(data["doms"])), 1) if data["doms"] else None

            monthly_results[month_name] = {
                "volume": data["count"],
                "median_price": median_price,
                "price_index": price_index,
                "median_dom": median_dom,
            }

        # Find best/worst months
        volumes = {m: d["volume"] for m, d in monthly_results.items() if d["volume"] > 0}
        prices = {m: d["price_index"] for m, d in monthly_results.items() if d["price_index"]}
        doms = {m: d["median_dom"] for m, d in monthly_results.items() if d["median_dom"]}

        results[suburb] = {
            "monthly": monthly_results,
            "best_price_month": max(prices, key=prices.get) if prices else None,
            "worst_price_month": min(prices, key=prices.get) if prices else None,
            "fastest_dom_month": min(doms, key=doms.get) if doms else None,
            "slowest_dom_month": max(doms, key=doms.get) if doms else None,
            "peak_volume_month": max(volumes, key=volumes.get) if volumes else None,
        }

        print(f"\n  {suburb.upper()}:")
        print(f"    Best price month: {results[suburb]['best_price_month']}")
        print(f"    Fastest DOM month: {results[suburb]['fastest_dom_month']}")
        print(f"    Peak volume: {results[suburb]['peak_volume_month']}")

    with open(os.path.join(OUTPUT_DIR_8, "study_8_1_seasonal.json"), "w") as f:
        json.dump(results, f, indent=2)
    return results


# ── Study 8.4: Capital Growth by Hold Period ─────────────────────────────
def study_8_4(all_docs):
    print("\n═══ Study 8.4: Capital Growth by Hold Period ═══")
    results = {}

    for suburb in CORE_SUBURBS:
        sd = [d for d in all_docs if d["_suburb"] == suburb and d["_numeric_price"] and d.get("_timeline")]

        growth_records = []
        for d in sd:
            current_price = d["_numeric_price"]
            sale_date_str = d.get("sale_date", "")
            if not sale_date_str: continue
            try:
                current_date = datetime.strptime(sale_date_str, "%Y-%m-%d")
            except: continue

            # Find previous sale in timeline
            for ev in d["_timeline"]:
                if ev.get("is_sold") and ev.get("price") and isinstance(ev["price"], (int, float)) and ev["price"] > 100000:
                    prev_date_str = ev.get("date", "")
                    try:
                        prev_date = datetime.strptime(prev_date_str, "%Y-%m-%d")
                    except: continue

                    years_held = (current_date - prev_date).days / 365.25
                    if years_held < 0.5 or years_held > 30:
                        continue

                    total_growth = (current_price / ev["price"] - 1) * 100
                    annual_growth = ((current_price / ev["price"]) ** (1 / years_held) - 1) * 100
                    dollar_gain = current_price - ev["price"]

                    growth_records.append({
                        "years_held": round(years_held, 1),
                        "total_growth_pct": round(total_growth, 1),
                        "annual_growth_pct": round(annual_growth, 1),
                        "dollar_gain": dollar_gain,
                        "prev_price": ev["price"],
                        "current_price": current_price,
                    })
                    break  # Only most recent previous sale

        if not growth_records:
            results[suburb] = {"note": "no growth data"}
            continue

        # Bucket by hold period
        buckets = {"1_3_years": [], "3_7_years": [], "7_15_years": [], "15_plus_years": []}
        for r in growth_records:
            yh = r["years_held"]
            if yh < 3: buckets["1_3_years"].append(r)
            elif yh < 7: buckets["3_7_years"].append(r)
            elif yh < 15: buckets["7_15_years"].append(r)
            else: buckets["15_plus_years"].append(r)

        bucket_stats = {}
        for bname, records in buckets.items():
            if len(records) < 3:
                continue
            annual_growths = [r["annual_growth_pct"] for r in records]
            total_growths = [r["total_growth_pct"] for r in records]
            dollar_gains = [r["dollar_gain"] for r in records]
            bucket_stats[bname] = {
                "count": len(records),
                "median_annual_growth": round(float(np.median(annual_growths)), 1),
                "mean_annual_growth": round(float(np.mean(annual_growths)), 1),
                "median_total_growth": round(float(np.median(total_growths)), 1),
                "median_dollar_gain": int(np.median(dollar_gains)),
            }

        results[suburb] = {
            "total_records": len(growth_records),
            "by_hold_period": bucket_stats,
            "overall_median_annual": round(float(np.median([r["annual_growth_pct"] for r in growth_records])), 1),
        }

        print(f"\n  {suburb.upper()} ({len(growth_records)} records with prior sale):")
        for bname, data in bucket_stats.items():
            print(f"    {bname:15s} median annual={data['median_annual_growth']:+.1f}%/yr  total={data['median_total_growth']:+.1f}%  gain=${data['median_dollar_gain']:,} (n={data['count']})")

    with open(os.path.join(OUTPUT_DIR_8, "study_8_4_capital_growth.json"), "w") as f:
        json.dump(results, f, indent=2)
    return results


# ── Summary ────────────────────────────────────────────────────────────────
def generate_summary(s72, s74, s81, s84):
    md = []
    md.append("# Phase 7+8: Spatial & Temporal Analysis")
    md.append(f"## Generated {datetime.now().strftime('%Y-%m-%d %H:%M AEST')}")

    # 7.2 Streets
    md.append("\n---\n## 7.2 Street-Level Premium Analysis")
    for suburb in CORE_SUBURBS:
        r = s72.get(suburb, {})
        md.append(f"\n### {suburb.replace('_',' ').title()} (suburb median: ${r.get('suburb_median_ppsqm', 0):,.0f}/sqm)")
        md.append("\n**Premium streets:**")
        md.append("| Street | Median $/sqm | Premium | Sales |")
        md.append("|--------|-------------|---------|-------|")
        for s in r.get("premium_streets", [])[:8]:
            md.append(f"| {s['street']} | ${s['median_ppsqm']:,.0f} | {s['premium_pct']:+.1f}% | {s['sales']} |")
        md.append("\n**Discount streets:**")
        md.append("| Street | Median $/sqm | Discount | Sales |")
        md.append("|--------|-------------|----------|-------|")
        for s in r.get("discount_streets", [])[-5:]:
            md.append(f"| {s['street']} | ${s['median_ppsqm']:,.0f} | {s['premium_pct']:+.1f}% | {s['sales']} |")

    # 7.4 Traffic
    md.append("\n---\n## 7.4 Traffic Exposure Impact")
    for suburb in CORE_SUBURBS:
        r = s74.get(suburb, {})
        md.append(f"\n### {suburb.replace('_',' ').title()}")
        if r.get("by_road_type"):
            md.append("| Road Type | Median $/sqm | N |")
            md.append("|-----------|-------------|---|")
            for rt, data in sorted(r["by_road_type"].items(), key=lambda x: x[1]["median"] if x[1] else 0, reverse=True):
                if data: md.append(f"| {rt} | ${data['median']:,.0f} | {data['count']} |")
        if r.get("by_traffic_exposure"):
            md.append("\n| Traffic Level | Median $/sqm | N |")
            md.append("|--------------|-------------|---|")
            for tb, data in r["by_traffic_exposure"].items():
                if data: md.append(f"| {tb} | ${data['median']:,.0f} | {data['count']} |")

    # 8.1 Seasonal
    md.append("\n---\n## 8.1 Seasonal Patterns")
    for suburb in CORE_SUBURBS:
        r = s81.get(suburb, {})
        md.append(f"\n### {suburb.replace('_',' ').title()}")
        md.append(f"- Best price month: **{r.get('best_price_month', 'N/A')}**")
        md.append(f"- Fastest selling: **{r.get('fastest_dom_month', 'N/A')}**")
        md.append(f"- Peak volume: **{r.get('peak_volume_month', 'N/A')}**")
        md.append("\n| Month | Volume | Median Price | Price Index | Median DOM |")
        md.append("|-------|--------|-------------|------------|-----------|")
        for month, data in r.get("monthly", {}).items():
            price = f"${data['median_price']:,}" if data['median_price'] else "-"
            idx = f"{data['price_index']}" if data['price_index'] else "-"
            dom = f"{data['median_dom']}d" if data['median_dom'] else "-"
            md.append(f"| {month} | {data['volume']} | {price} | {idx} | {dom} |")

    # 8.4 Capital Growth
    md.append("\n---\n## 8.4 Capital Growth by Hold Period")
    for suburb in CORE_SUBURBS:
        r = s84.get(suburb, {})
        if "by_hold_period" not in r: continue
        md.append(f"\n### {suburb.replace('_',' ').title()} (median annual growth: {r.get('overall_median_annual', 'N/A')}%)")
        md.append("| Hold Period | Median Annual Growth | Median Total Growth | Median $ Gain | N |")
        md.append("|-----------|---------------------|--------------------|--------------|----|")
        for bp, data in r.get("by_hold_period", {}).items():
            md.append(f"| {bp} | {data['median_annual_growth']:+.1f}%/yr | {data['median_total_growth']:+.1f}% | ${data['median_dollar_gain']:,} | {data['count']} |")

    md.append(f"\n---\n*Fields Estate — Phase 7+8 | {datetime.now().strftime('%Y-%m-%d')}*")
    path = "/home/fields/Fields_Orchestrator/output/positioning_research/phase_7_8_summary.md"
    with open(path, "w") as f:
        f.write("\n".join(md))
    print(f"\n  Summary: {path}")

def main():
    print("╔═══════════════════════════════════════════════════════════════╗")
    print("║  Phase 7+8: Spatial & Temporal — Positioning Research         ║")
    print("╚═══════════════════════════════════════════════════════════════╝")
    all_docs = load_all_data()
    s72 = study_7_2(all_docs)
    s74 = study_7_4(all_docs)
    s81 = study_8_1(all_docs)
    s84 = study_8_4(all_docs)
    generate_summary(s72, s74, s81, s84)
    print("\n" + "=" * 60)
    print("Phase 7+8 COMPLETE")
    print("=" * 60)

if __name__ == "__main__":
    main()
