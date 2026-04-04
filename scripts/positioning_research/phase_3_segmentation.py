#!/usr/bin/env python3
"""
Phase 3: Segmentation — Property Positioning Research
======================================================
"What natural groups exist?"

Studies:
  3.1 - Natural price tiers per suburb (entry/upgrader/premium/prestige)
  3.2 - Buyer archetype segmentation
  3.3 - Property archetype clustering
  3.4 - Geographic micro-markets (spatial price clusters)

Depends on: Phase 0, 1, 2
"""

import json
import os
import re
import sys
import time
from collections import defaultdict, Counter
from datetime import datetime

import numpy as np

sys.path.insert(0, "/home/fields/Fields_Orchestrator")
from shared.db import get_client

OUTPUT_DIR = "/home/fields/Fields_Orchestrator/output/positioning_research/phase_3"
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

    # Gold_Coast match for lat/long
    print("Loading Gold_Coast for coordinates...")
    gc_lookup = {}
    for suburb in TARGET_SUBURBS:
        time.sleep(2)
        for gc in db_gc[suburb].find({}, {"complete_address": 1, "LATITUDE": 1, "LONGITUDE": 1, "lot_size_sqm": 1}):
            norm = normalise_address(gc.get("complete_address", ""))
            if norm: gc_lookup[norm] = gc

    for d in all_docs:
        norm = normalise_address(d.get("address", ""))
        gc = gc_lookup.get(norm) or gc_lookup.get(re.sub(r"^\d+/", "", norm))
        if gc:
            d["_lat"] = gc.get("LATITUDE")
            d["_lon"] = gc.get("LONGITUDE")
            d["_lot_size"] = gc.get("lot_size_sqm")

    return all_docs


# ── Study 3.1: Natural Price Tiers ────────────────────────────────────────
def study_3_1(all_docs):
    print("\n═══ Study 3.1: Natural Price Tiers ═══")
    results = {}

    for suburb in TARGET_SUBURBS:
        sd = [d for d in all_docs if d["_suburb"] == suburb and d["_numeric_price"]]
        prices = sorted([d["_numeric_price"] for d in sd])
        if not prices:
            continue

        # Use quartile-based tiers (natural breaks)
        p25 = np.percentile(prices, 25)
        p50 = np.percentile(prices, 50)
        p75 = np.percentile(prices, 75)

        tiers = {
            "entry": {"range": f"<${int(p25):,}", "threshold": p25},
            "core": {"range": f"${int(p25):,}-${int(p50):,}", "threshold": p50},
            "premium": {"range": f"${int(p50):,}-${int(p75):,}", "threshold": p75},
            "prestige": {"range": f">${int(p75):,}", "threshold": float("inf")},
        }

        # Profile each tier
        for tier_name, tier_info in tiers.items():
            if tier_name == "entry":
                tier_docs = [d for d in sd if d["_numeric_price"] < p25]
            elif tier_name == "core":
                tier_docs = [d for d in sd if p25 <= d["_numeric_price"] < p50]
            elif tier_name == "premium":
                tier_docs = [d for d in sd if p50 <= d["_numeric_price"] < p75]
            else:
                tier_docs = [d for d in sd if d["_numeric_price"] >= p75]

            beds = Counter(d.get("bedrooms") for d in tier_docs if d.get("bedrooms"))
            types = Counter(d.get("property_type") for d in tier_docs if d.get("property_type"))
            reno = Counter(safe_get(d, "property_valuation_data.renovation.overall_renovation_level") for d in tier_docs
                          if safe_get(d, "property_valuation_data.renovation.overall_renovation_level"))
            pool_pct = round(100 * sum(1 for d in tier_docs if safe_get(d, "property_valuation_data.outdoor.pool_present") is True) / len(tier_docs), 1) if tier_docs else 0
            water_pct = round(100 * sum(1 for d in tier_docs if safe_get(d, "property_valuation_data.outdoor.water_views") is True) / len(tier_docs), 1) if tier_docs else 0
            areas = [d["_floor_area"] for d in tier_docs if d.get("_floor_area")]

            tier_info["count"] = len(tier_docs)
            tier_info["price_stats"] = calc_stats([d["_numeric_price"] for d in tier_docs])
            tier_info["typical_beds"] = beds.most_common(1)[0][0] if beds else None
            tier_info["bed_distribution"] = dict(sorted(beds.items()))
            tier_info["property_type"] = dict(types.most_common(3))
            tier_info["renovation"] = dict(reno.most_common(3))
            tier_info["pool_pct"] = pool_pct
            tier_info["water_views_pct"] = water_pct
            tier_info["median_floor_area"] = round(float(np.median(areas)), 0) if areas else None

        results[suburb] = tiers

        print(f"\n  {suburb.upper()}:")
        for tier_name, info in tiers.items():
            print(f"    {tier_name:10s} {info['range']:25s} n={info['count']:3d}  beds={info['typical_beds']}  pool={info['pool_pct']:4.0f}%  water={info['water_views_pct']:4.0f}%  area={info['median_floor_area'] or '-'}sqm  reno={list(info['renovation'].keys())[:2]}")

    with open(os.path.join(OUTPUT_DIR, "study_3_1_price_tiers.json"), "w") as f:
        json.dump(results, f, indent=2)
    return results


# ── Study 3.2: Buyer Archetype Segmentation ───────────────────────────────
def study_3_2(all_docs):
    print("\n═══ Study 3.2: Buyer Archetype Segmentation ═══")
    results = {}

    for suburb in CORE_SUBURBS:
        sd = [d for d in all_docs if d["_suburb"] == suburb]

        # Extract buyer insights from floor plan analysis
        buyer_counts = Counter()
        buyer_to_properties = defaultdict(list)

        for d in sd:
            ideal_for = safe_get(d, "floor_plan_analysis.buyer_insights.ideal_for") or []
            for buyer_type in ideal_for:
                bt = buyer_type.lower().strip()
                buyer_counts[bt] += 1
                buyer_to_properties[bt].append(d)

        # Profile each archetype
        archetypes = {}
        for bt, count in buyer_counts.most_common(8):
            if count < 5:
                continue
            props = buyer_to_properties[bt]
            prices = [d["_numeric_price"] for d in props if d["_numeric_price"]]
            beds = Counter(d.get("bedrooms") for d in props if d.get("bedrooms"))
            areas = [d["_floor_area"] for d in props if d.get("_floor_area")]
            pool_pct = round(100 * sum(1 for d in props if safe_get(d, "property_valuation_data.outdoor.pool_present") is True) / len(props), 1)
            levels = Counter(safe_get(d, "floor_plan_analysis.levels.total_levels") for d in props
                            if safe_get(d, "floor_plan_analysis.levels.total_levels"))

            archetypes[bt] = {
                "count": count,
                "share_pct": round(100 * count / len(sd), 1),
                "median_price": int(np.median(prices)) if prices else None,
                "typical_beds": beds.most_common(1)[0][0] if beds else None,
                "bed_distribution": dict(sorted(beds.items())),
                "median_floor_area": round(float(np.median(areas)), 0) if areas else None,
                "pool_pct": pool_pct,
                "typical_levels": levels.most_common(1)[0][0] if levels else None,
            }

        results[suburb] = archetypes

        print(f"\n  {suburb.upper()}:")
        for bt, info in sorted(archetypes.items(), key=lambda x: -x[1]["count"]):
            print(f"    {bt:30s} n={info['count']:3d} ({info['share_pct']:4.1f}%)  ${info['median_price']:>10,}  {info['typical_beds']}-bed  {info['median_floor_area'] or '-'}sqm  pool={info['pool_pct']:.0f}%")

    with open(os.path.join(OUTPUT_DIR, "study_3_2_buyer_archetypes.json"), "w") as f:
        json.dump(results, f, indent=2)
    return results


# ── Study 3.3: Property Archetype Clustering ──────────────────────────────
def study_3_3(all_docs):
    print("\n═══ Study 3.3: Property Archetype Clustering ═══")
    results = {}

    for suburb in CORE_SUBURBS:
        sd = [d for d in all_docs if d["_suburb"] == suburb and d["_numeric_price"]]

        # Rule-based archetypes (more interpretable than k-means for this domain)
        archetypes = defaultdict(list)

        for d in sd:
            beds = d.get("bedrooms", 0)
            price = d["_numeric_price"] or 0
            reno = safe_get(d, "property_valuation_data.renovation.overall_renovation_level") or ""
            pool = safe_get(d, "property_valuation_data.outdoor.pool_present") is True
            water = safe_get(d, "property_valuation_data.outdoor.water_views") is True
            area = d.get("_floor_area") or 0
            levels = safe_get(d, "floor_plan_analysis.levels.total_levels") or 1
            lot = d.get("_lot_size") or safe_get(d, "floor_plan_analysis.total_land_area.value") or 0
            cond = safe_get(d, "property_valuation_data.condition_summary.overall_score") or 7
            ptype = d.get("property_type", "House")

            # Classification rules
            if ptype in ("Duplex", "Villa"):
                archetypes["duplex_villa"].append(d)
            elif reno in ("original", "tired") or (isinstance(cond, (int, float)) and cond <= 6):
                if lot and isinstance(lot, (int, float)) and lot > 700:
                    archetypes["original_large_block"].append(d)
                else:
                    archetypes["original_standard"].append(d)
            elif reno == "new_build":
                archetypes["new_build"].append(d)
            elif water and pool and beds >= 4:
                archetypes["premium_waterfront_entertainer"].append(d)
            elif pool and beds >= 4 and area > 200:
                archetypes["family_entertainer_with_pool"].append(d)
            elif reno == "fully_renovated" and beds >= 4:
                archetypes["renovated_family_home"].append(d)
            elif beds >= 5:
                archetypes["large_family_home"].append(d)
            elif beds <= 3 and area and area < 150:
                archetypes["compact_starter_downsizer"].append(d)
            elif levels >= 2:
                archetypes["two_storey_family"].append(d)
            else:
                archetypes["standard_family_home"].append(d)

        # Profile each archetype
        suburb_results = {}
        for arch_name, docs in sorted(archetypes.items(), key=lambda x: -len(x[1])):
            if len(docs) < 3:
                continue
            prices = [d["_numeric_price"] for d in docs if d["_numeric_price"]]
            areas = [d["_floor_area"] for d in docs if d.get("_floor_area")]
            beds = Counter(d.get("bedrooms") for d in docs if d.get("bedrooms"))
            pool_pct = round(100 * sum(1 for d in docs if safe_get(d, "property_valuation_data.outdoor.pool_present") is True) / len(docs), 1)

            suburb_results[arch_name] = {
                "count": len(docs),
                "share_pct": round(100 * len(docs) / len(sd), 1),
                "price_stats": calc_stats(prices),
                "median_floor_area": round(float(np.median(areas)), 0) if areas else None,
                "typical_beds": beds.most_common(1)[0][0] if beds else None,
                "pool_pct": pool_pct,
            }

        results[suburb] = suburb_results

        print(f"\n  {suburb.upper()}:")
        for arch, info in sorted(suburb_results.items(), key=lambda x: -x[1]["count"]):
            ps = info["price_stats"]
            med_price = f"${ps['median']:,.0f}" if ps else "N/A"
            print(f"    {arch:35s} n={info['count']:3d} ({info['share_pct']:4.1f}%)  {med_price:>12s}  {info['median_floor_area'] or '-'}sqm  pool={info['pool_pct']:.0f}%")

    with open(os.path.join(OUTPUT_DIR, "study_3_3_property_archetypes.json"), "w") as f:
        json.dump(results, f, indent=2)
    return results


# ── Study 3.4: Geographic Micro-Markets ───────────────────────────────────
def study_3_4(all_docs):
    print("\n═══ Study 3.4: Geographic Micro-Markets ═══")
    results = {}

    for suburb in CORE_SUBURBS:
        sd = [d for d in all_docs if d["_suburb"] == suburb and d.get("_lat") and d.get("_lon") and d["_numeric_price"]]
        if len(sd) < 20:
            print(f"  {suburb}: insufficient geo data ({len(sd)} records)")
            continue

        # Simple grid-based micro-markets (0.005 degree ~= 500m)
        grid_size = 0.005
        grid_cells = defaultdict(list)
        for d in sd:
            gx = round(d["_lat"] / grid_size) * grid_size
            gy = round(d["_lon"] / grid_size) * grid_size
            grid_cells[(round(gx, 4), round(gy, 4))].append(d)

        # Find significant clusters (5+ sales)
        suburb_median = np.median([d["_numeric_price"] for d in sd])
        micro_markets = []

        for (lat, lon), docs in grid_cells.items():
            if len(docs) < 5:
                continue
            prices = [d["_numeric_price"] for d in docs]
            median_price = int(np.median(prices))
            premium_pct = round(100 * (median_price / suburb_median - 1), 1)

            # Sample addresses
            addrs = [d.get("address", "") for d in docs[:3]]

            micro_markets.append({
                "lat": lat,
                "lon": lon,
                "count": len(docs),
                "median_price": median_price,
                "premium_vs_suburb_pct": premium_pct,
                "sample_addresses": addrs,
                "classification": "premium" if premium_pct > 15 else "discount" if premium_pct < -15 else "at_market",
            })

        micro_markets.sort(key=lambda x: -x["premium_vs_suburb_pct"])

        results[suburb] = {
            "suburb_median": int(suburb_median),
            "records_with_geo": len(sd),
            "micro_markets": micro_markets,
            "premium_zones": [m for m in micro_markets if m["classification"] == "premium"],
            "discount_zones": [m for m in micro_markets if m["classification"] == "discount"],
        }

        premium_count = len(results[suburb]["premium_zones"])
        discount_count = len(results[suburb]["discount_zones"])
        print(f"  {suburb}: {len(sd)} geo records, {len(micro_markets)} micro-markets, {premium_count} premium, {discount_count} discount")
        for mm in micro_markets[:3]:
            print(f"    {mm['premium_vs_suburb_pct']:+.1f}% ${mm['median_price']:,} (n={mm['count']}) — {mm['sample_addresses'][0][:50]}")
        if micro_markets:
            print(f"    ...")
            for mm in micro_markets[-2:]:
                print(f"    {mm['premium_vs_suburb_pct']:+.1f}% ${mm['median_price']:,} (n={mm['count']}) — {mm['sample_addresses'][0][:50]}")

    with open(os.path.join(OUTPUT_DIR, "study_3_4_micro_markets.json"), "w") as f:
        json.dump(results, f, indent=2)
    return results


# ── Summary ────────────────────────────────────────────────────────────────
def generate_summary(s31, s32, s33, s34):
    md = []
    md.append("# Phase 3: Segmentation — \"What Natural Groups Exist?\"")
    md.append(f"## Generated {datetime.now().strftime('%Y-%m-%d %H:%M AEST')}")
    md.append("")

    # 3.1 Price Tiers
    md.append("---")
    md.append("## 3.1 Natural Price Tiers")
    md.append("")
    for suburb in CORE_SUBURBS:
        tiers = s31.get(suburb, {})
        md.append(f"### {suburb.replace('_',' ').title()}")
        md.append("| Tier | Range | Count | Typical Beds | Pool % | Water % | Median Area | Top Renovation |")
        md.append("|------|-------|-------|-------------|--------|---------|-------------|----------------|")
        for tier_name in ["entry", "core", "premium", "prestige"]:
            t = tiers.get(tier_name, {})
            reno_top = list(t.get("renovation", {}).keys())[:1]
            md.append(f"| {tier_name} | {t.get('range','-')} | {t.get('count',0)} | {t.get('typical_beds','-')}-bed | {t.get('pool_pct',0):.0f}% | {t.get('water_views_pct',0):.0f}% | {t.get('median_floor_area','-')}sqm | {reno_top[0] if reno_top else '-'} |")
        md.append("")

    # 3.2 Buyer Archetypes
    md.append("---")
    md.append("## 3.2 Buyer Archetypes")
    md.append("")
    for suburb in CORE_SUBURBS:
        archs = s32.get(suburb, {})
        md.append(f"### {suburb.replace('_',' ').title()}")
        md.append("| Buyer Type | Count | Share | Median Price | Typical Beds | Floor Area | Pool % |")
        md.append("|-----------|-------|-------|-------------|-------------|------------|--------|")
        for bt, info in sorted(archs.items(), key=lambda x: -x[1]["count"]):
            mp = f"${info['median_price']:,}" if info['median_price'] else "-"
            md.append(f"| {bt} | {info['count']} | {info['share_pct']}% | {mp} | {info['typical_beds'] or '-'}-bed | {info['median_floor_area'] or '-'}sqm | {info['pool_pct']:.0f}% |")
        md.append("")

    # 3.3 Property Archetypes
    md.append("---")
    md.append("## 3.3 Property Archetypes")
    md.append("")
    for suburb in CORE_SUBURBS:
        archs = s33.get(suburb, {})
        md.append(f"### {suburb.replace('_',' ').title()}")
        md.append("| Archetype | Count | Share | Median Price | Floor Area | Pool % |")
        md.append("|-----------|-------|-------|-------------|------------|--------|")
        for arch, info in sorted(archs.items(), key=lambda x: -x[1]["count"]):
            ps = info["price_stats"]
            mp = f"${ps['median']:,.0f}" if ps else "-"
            md.append(f"| {arch} | {info['count']} | {info['share_pct']}% | {mp} | {info['median_floor_area'] or '-'}sqm | {info['pool_pct']:.0f}% |")
        md.append("")

    # 3.4 Micro-Markets
    md.append("---")
    md.append("## 3.4 Geographic Micro-Markets")
    md.append("")
    for suburb in CORE_SUBURBS:
        r = s34.get(suburb, {})
        if not r:
            continue
        md.append(f"### {suburb.replace('_',' ').title()} (suburb median: ${r['suburb_median']:,})")
        md.append("")

        premium = r.get("premium_zones", [])
        if premium:
            md.append("**Premium zones (>+15% vs suburb):**")
            for mm in premium[:5]:
                md.append(f"- {mm['premium_vs_suburb_pct']:+.1f}% (${mm['median_price']:,}, n={mm['count']}) — near {mm['sample_addresses'][0][:60]}")

        discount = r.get("discount_zones", [])
        if discount:
            md.append("\n**Discount zones (<-15% vs suburb):**")
            for mm in discount[:5]:
                md.append(f"- {mm['premium_vs_suburb_pct']:+.1f}% (${mm['median_price']:,}, n={mm['count']}) — near {mm['sample_addresses'][0][:60]}")
        md.append("")

    md.append("---")
    md.append(f"*Fields Estate — Phase 3 Segmentation | {datetime.now().strftime('%Y-%m-%d')}*")

    path = "/home/fields/Fields_Orchestrator/output/positioning_research/phase_3_summary.md"
    with open(path, "w") as f:
        f.write("\n".join(md))
    print(f"\n  Summary: {path}")
    return "\n".join(md)


def main():
    print("╔═══════════════════════════════════════════════════════════════╗")
    print("║  Phase 3: Segmentation — Positioning Research                 ║")
    print("╚═══════════════════════════════════════════════════════════════╝")
    all_docs = load_all_data()
    s31 = study_3_1(all_docs)
    s32 = study_3_2(all_docs)
    s33 = study_3_3(all_docs)
    s34 = study_3_4(all_docs)
    generate_summary(s31, s32, s33, s34)
    print("\n" + "=" * 60)
    print("Phase 3 COMPLETE")
    print("=" * 60)

if __name__ == "__main__":
    main()
