#!/usr/bin/env python3
"""
Phase 2: Bivariate Analysis — Property Positioning Research
=============================================================
"What co-varies with price and DOM?"

Studies:
  2.1 - Price vs structural features (bedrooms, bathrooms, floor area, lot size)
  2.2 - Price vs location features (canal, cul-de-sac, traffic, major road)
  2.3 - Price vs water proximity and views
  2.4 - Price vs condition and renovation
  2.5 - Price vs kitchen/bathroom quality
  2.6 - Price vs outdoor amenity (pool, landscaping)
  2.7 - DOM vs ALL property characteristics
  2.8 - DOM vs pricing strategy
  2.9 - DOM vs agency

Depends on: Phase 0 + Phase 1
"""

import json
import os
import re
import sys
import time
from collections import defaultdict, Counter
from datetime import datetime

import numpy as np
from scipy import stats as scipy_stats

sys.path.insert(0, "/home/fields/Fields_Orchestrator")
from shared.db import get_client

OUTPUT_DIR = "/home/fields/Fields_Orchestrator/output/positioning_research/phase_2"
os.makedirs(OUTPUT_DIR, exist_ok=True)

TARGET_SUBURBS = [
    "robina", "varsity_lakes", "burleigh_waters",
    "mudgeeraba", "merrimac", "carrara",
    "worongary", "reedy_creek",
]
CORE_SUBURBS = ["robina", "varsity_lakes", "burleigh_waters"]

client = get_client()
db_target = client["Target_Market_Sold_Last_12_Months"]
db_gc = client["Gold_Coast"]


# ── Helpers ─────────────────────────────────────────────────────────────────
def parse_price(s):
    if not s or not isinstance(s, str):
        return None
    cleaned = s.replace(",", "").replace("$", "").strip()
    m = re.search(r"(\d{6,})", cleaned)
    return int(m.group(1)) if m else None


def safe_get(doc, path, default=None):
    parts = path.split(".")
    current = doc
    for p in parts:
        if isinstance(current, dict):
            current = current.get(p)
        else:
            return default
        if current is None:
            return default
    return current


def calc_stats(values):
    if not values or len(values) < 2:
        return None
    arr = np.array(values)
    return {
        "count": len(values),
        "mean": round(float(np.mean(arr)), 1),
        "median": round(float(np.median(arr)), 1),
        "std": round(float(np.std(arr)), 1),
        "p25": round(float(np.percentile(arr, 25)), 1),
        "p75": round(float(np.percentile(arr, 75)), 1),
    }


def normalise_address(addr):
    if not addr:
        return ""
    addr = addr.upper().strip()
    addr = re.sub(r"\s*,\s*", " ", addr)
    addr = re.sub(r"\s+", " ", addr)
    addr = re.sub(r"\bQLD\b", "", addr).strip()
    addr = re.sub(r"\b\d{4}\b$", "", addr).strip()
    return addr


def mann_whitney(group_a, group_b):
    """Mann-Whitney U test, returns U statistic and p-value."""
    if len(group_a) < 5 or len(group_b) < 5:
        return None, None
    try:
        u, p = scipy_stats.mannwhitneyu(group_a, group_b, alternative="two-sided")
        return round(float(u), 1), round(float(p), 4)
    except Exception:
        return None, None


def spearman_corr(x, y):
    """Spearman rank correlation."""
    if len(x) < 10 or len(x) != len(y):
        return None, None
    try:
        r, p = scipy_stats.spearmanr(x, y)
        return round(float(r), 3), round(float(p), 4)
    except Exception:
        return None, None


# ── Data Loading ────────────────────────────────────────────────────────────
def load_all_data():
    """Load sold records + Gold_Coast matches for location/valuation data."""
    print("Loading sold records...")
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
    print(f"  Loaded {len(all_docs)} sold records")

    # Load Gold_Coast matches for location + valuation
    print("Loading Gold_Coast matches...")
    gc_lookup = {}
    for suburb in TARGET_SUBURBS:
        time.sleep(2)
        gc_docs = list(db_gc[suburb].find(
            {},
            {"complete_address": 1, "LATITUDE": 1, "LONGITUDE": 1,
             "osm_location_features": 1, "scraped_data.valuation": 1,
             "scraped_data.property_timeline": 1, "lot_size_sqm": 1}
        ))
        for gc in gc_docs:
            norm = normalise_address(gc.get("complete_address", ""))
            if norm:
                gc_lookup[norm] = gc

    # Match and enrich
    matched = 0
    dom_count = 0
    for d in all_docs:
        norm = normalise_address(d.get("address", ""))
        gc = gc_lookup.get(norm)
        if not gc:
            gc = gc_lookup.get(re.sub(r"^\d+/", "", norm))

        d["_gc"] = gc
        if gc:
            matched += 1
            d["_lat"] = gc.get("LATITUDE")
            d["_lon"] = gc.get("LONGITUDE")
            d["_osm"] = gc.get("osm_location_features")
            d["_domain_val"] = safe_get(gc, "scraped_data.valuation")
            d["_lot_size"] = gc.get("lot_size_sqm")

            # DOM from timeline
            timeline = safe_get(gc, "scraped_data.property_timeline") or []
            for event in timeline:
                if event.get("is_sold") and event.get("days_on_market"):
                    d["_dom"] = int(event["days_on_market"])
                    dom_count += 1
                    break

        # DOM from direct field (fallback)
        if not d.get("_dom") and d.get("time_on_market_days") and isinstance(d["time_on_market_days"], (int, float)):
            d["_dom"] = int(d["time_on_market_days"])
            dom_count += 1

    print(f"  Matched: {matched}/{len(all_docs)}, DOM: {dom_count}")
    return all_docs


# ── Study 2.1: Price vs Structural Features ────────────────────────────────
def study_2_1(all_docs):
    print("\n═══ Study 2.1: Price vs Structural Features ═══")
    results = {}

    for suburb in CORE_SUBURBS:
        sd = [d for d in all_docs if d["_suburb"] == suburb and d["_numeric_price"]]

        # Marginal value of bedrooms
        by_beds = defaultdict(list)
        for d in sd:
            b = d.get("bedrooms")
            if b and 2 <= b <= 6:
                by_beds[b].append(d["_numeric_price"])

        bed_analysis = {}
        prev_median = None
        for b in sorted(by_beds.keys()):
            prices = by_beds[b]
            median = int(np.median(prices))
            marginal = (median - prev_median) if prev_median else None
            bed_analysis[str(b)] = {
                "median_price": median,
                "count": len(prices),
                "marginal_value": marginal,
            }
            prev_median = median

        # Correlation: floor area vs price
        fa_prices = [(safe_get(d, "floor_plan_analysis.internal_floor_area.value"), d["_numeric_price"])
                     for d in sd if safe_get(d, "floor_plan_analysis.internal_floor_area.value") and d["_numeric_price"]]
        fa_x = [p[0] for p in fa_prices if isinstance(p[0], (int, float)) and p[0] > 30]
        fa_y = [p[1] for p in fa_prices if isinstance(p[0], (int, float)) and p[0] > 30]
        fa_corr, fa_p = spearman_corr(fa_x, fa_y)

        # Correlation: lot size vs price
        lot_prices = [(d.get("_lot_size"), d["_numeric_price"])
                      for d in sd if d.get("_lot_size") and d["_numeric_price"]]
        lot_x = [p[0] for p in lot_prices if isinstance(p[0], (int, float)) and p[0] > 50]
        lot_y = [p[1] for p in lot_prices if isinstance(p[0], (int, float)) and p[0] > 50]
        lot_corr, lot_p = spearman_corr(lot_x, lot_y)

        # Bathrooms marginal
        by_baths = defaultdict(list)
        for d in sd:
            b = d.get("bathrooms")
            if b and 1 <= b <= 4:
                by_baths[b].append(d["_numeric_price"])
        bath_analysis = {}
        prev_median = None
        for b in sorted(by_baths.keys()):
            prices = by_baths[b]
            median = int(np.median(prices))
            bath_analysis[str(b)] = {
                "median_price": median,
                "count": len(prices),
                "marginal_value": (median - prev_median) if prev_median else None,
            }
            prev_median = median

        results[suburb] = {
            "bedrooms": bed_analysis,
            "bathrooms": bath_analysis,
            "floor_area_vs_price": {"spearman_r": fa_corr, "p_value": fa_p, "n": len(fa_x)},
            "lot_size_vs_price": {"spearman_r": lot_corr, "p_value": lot_p, "n": len(lot_x)},
        }

        print(f"  {suburb}:")
        print(f"    Floor area→price: r={fa_corr}, p={fa_p}, n={len(fa_x)}")
        print(f"    Lot size→price: r={lot_corr}, p={lot_p}, n={len(lot_x)}")
        for b, data in bed_analysis.items():
            mv = f"+${data['marginal_value']:,}" if data['marginal_value'] else "base"
            print(f"    {b}-bed: ${data['median_price']:,} ({mv}, n={data['count']})")

    with open(os.path.join(OUTPUT_DIR, "study_2_1_structural.json"), "w") as f:
        json.dump(results, f, indent=2)
    return results


# ── Study 2.2: Price vs Location Features ──────────────────────────────────
def study_2_2(all_docs):
    print("\n═══ Study 2.2: Price vs Location Features ═══")
    results = {}

    for suburb in CORE_SUBURBS:
        sd = [d for d in all_docs if d["_suburb"] == suburb and d["_numeric_price"] and d.get("_osm")]

        location_tests = {}

        # Cul-de-sac vs not
        cds_yes = [d["_numeric_price"] for d in sd if safe_get(d, "_osm.road_classification.is_cul_de_sac") is True]
        cds_no = [d["_numeric_price"] for d in sd if safe_get(d, "_osm.road_classification.is_cul_de_sac") is False]
        u, p = mann_whitney(cds_yes, cds_no)
        location_tests["cul_de_sac"] = {
            "yes": calc_stats(cds_yes), "no": calc_stats(cds_no),
            "premium_pct": round(100 * (np.median(cds_yes) / np.median(cds_no) - 1), 1) if cds_yes and cds_no else None,
            "mann_whitney_p": p,
        }

        # Corner lot vs not
        corner_yes = [d["_numeric_price"] for d in sd if safe_get(d, "_osm.road_classification.is_corner_lot") is True]
        corner_no = [d["_numeric_price"] for d in sd if safe_get(d, "_osm.road_classification.is_corner_lot") is False]
        u, p = mann_whitney(corner_yes, corner_no)
        location_tests["corner_lot"] = {
            "yes": calc_stats(corner_yes), "no": calc_stats(corner_no),
            "premium_pct": round(100 * (np.median(corner_yes) / np.median(corner_no) - 1), 1) if corner_yes and corner_no else None,
            "mann_whitney_p": p,
        }

        # Faces major road vs not
        major_yes = [d["_numeric_price"] for d in sd if safe_get(d, "_osm.road_classification.faces_major_road") is True]
        major_no = [d["_numeric_price"] for d in sd if safe_get(d, "_osm.road_classification.faces_major_road") is False]
        u, p = mann_whitney(major_yes, major_no)
        location_tests["faces_major_road"] = {
            "yes": calc_stats(major_yes), "no": calc_stats(major_no),
            "discount_pct": round(100 * (np.median(major_yes) / np.median(major_no) - 1), 1) if major_yes and major_no else None,
            "mann_whitney_p": p,
        }

        # Traffic exposure score correlation
        traffic_pairs = [(safe_get(d, "_osm.road_classification.traffic_exposure_score"), d["_numeric_price"])
                         for d in sd if safe_get(d, "_osm.road_classification.traffic_exposure_score") is not None]
        tx = [p[0] for p in traffic_pairs]
        ty = [p[1] for p in traffic_pairs]
        tr, tp = spearman_corr(tx, ty)
        location_tests["traffic_exposure"] = {"spearman_r": tr, "p_value": tp, "n": len(tx)}

        # Canal frontage
        canal_yes = [d["_numeric_price"] for d in sd if safe_get(d, "_osm.water_features.canal_frontage") is True]
        canal_no = [d["_numeric_price"] for d in sd if safe_get(d, "_osm.water_features.canal_frontage") is False]
        u, p = mann_whitney(canal_yes, canal_no)
        location_tests["canal_frontage"] = {
            "yes": calc_stats(canal_yes), "no": calc_stats(canal_no),
            "premium_pct": round(100 * (np.median(canal_yes) / np.median(canal_no) - 1), 1) if canal_yes and canal_no else None,
            "mann_whitney_p": p,
        }

        results[suburb] = location_tests

        print(f"\n  {suburb}:")
        for test, data in location_tests.items():
            if "premium_pct" in data and data["premium_pct"] is not None:
                sig = "***" if data.get("mann_whitney_p") and data["mann_whitney_p"] < 0.01 else "**" if data.get("mann_whitney_p") and data["mann_whitney_p"] < 0.05 else ""
                yes_n = data.get("yes", {}).get("count", 0) if data.get("yes") else 0
                no_n = data.get("no", {}).get("count", 0) if data.get("no") else 0
                print(f"    {test:25s} premium={data['premium_pct']:+.1f}% p={data.get('mann_whitney_p')} (yes={yes_n}, no={no_n}) {sig}")
            elif "spearman_r" in data:
                print(f"    {test:25s} r={data['spearman_r']}, p={data['p_value']}, n={data['n']}")

    with open(os.path.join(OUTPUT_DIR, "study_2_2_location.json"), "w") as f:
        json.dump(results, f, indent=2)
    return results


# ── Study 2.3: Price vs Water ──────────────────────────────────────────────
def study_2_3(all_docs):
    print("\n═══ Study 2.3: Price vs Water Proximity and Views ═══")
    results = {}

    for suburb in CORE_SUBURBS:
        sd = [d for d in all_docs if d["_suburb"] == suburb and d["_numeric_price"]]

        # Water views (from GPT analysis)
        wv_yes = [d["_numeric_price"] for d in sd if safe_get(d, "property_valuation_data.outdoor.water_views") is True]
        wv_no = [d["_numeric_price"] for d in sd if safe_get(d, "property_valuation_data.outdoor.water_views") is False]
        u, p = mann_whitney(wv_yes, wv_no)

        # Water view type breakdown
        wv_types = defaultdict(list)
        for d in sd:
            wvt = safe_get(d, "property_valuation_data.outdoor.water_view_type")
            if wvt and wvt != "none" and d["_numeric_price"]:
                wv_types[wvt].append(d["_numeric_price"])

        # $/sqm comparison
        wv_ppsqm_yes = [d["_ppsqm"] for d in sd if safe_get(d, "property_valuation_data.outdoor.water_views") is True and d.get("_ppsqm")]
        wv_ppsqm_no = [d["_ppsqm"] for d in sd if safe_get(d, "property_valuation_data.outdoor.water_views") is False and d.get("_ppsqm")]

        # Distance to water (from OSM)
        dist_pairs = []
        for d in sd:
            dist = safe_get(d, "_osm.water_features.distance_to_water_m")
            if dist and isinstance(dist, (int, float)) and d["_numeric_price"]:
                dist_pairs.append((dist, d["_numeric_price"]))
        dx = [p[0] for p in dist_pairs]
        dy = [p[1] for p in dist_pairs]
        dist_corr, dist_p = spearman_corr(dx, dy)

        results[suburb] = {
            "water_views_impact": {
                "with_views": calc_stats(wv_yes),
                "without_views": calc_stats(wv_no),
                "price_premium_pct": round(100 * (np.median(wv_yes) / np.median(wv_no) - 1), 1) if wv_yes and wv_no else None,
                "price_premium_dollar": int(np.median(wv_yes) - np.median(wv_no)) if wv_yes and wv_no else None,
                "mann_whitney_p": p,
            },
            "ppsqm_comparison": {
                "with_views": calc_stats(wv_ppsqm_yes),
                "without_views": calc_stats(wv_ppsqm_no),
                "ppsqm_premium_pct": round(100 * (np.median(wv_ppsqm_yes) / np.median(wv_ppsqm_no) - 1), 1) if wv_ppsqm_yes and wv_ppsqm_no else None,
            },
            "by_view_type": {vt: calc_stats(prices) for vt, prices in wv_types.items()},
            "distance_to_water": {"spearman_r": dist_corr, "p_value": dist_p, "n": len(dx)},
        }

        wvi = results[suburb]["water_views_impact"]
        print(f"  {suburb}:")
        print(f"    Water views: +{wvi['price_premium_pct']}% (+${wvi['price_premium_dollar']:,}), p={wvi['mann_whitney_p']}")
        ppsqm_prem = results[suburb]["ppsqm_comparison"]["ppsqm_premium_pct"]
        print(f"    $/sqm premium: +{ppsqm_prem}%")
        print(f"    Distance→price: r={dist_corr}, n={len(dx)}")

    with open(os.path.join(OUTPUT_DIR, "study_2_3_water.json"), "w") as f:
        json.dump(results, f, indent=2)
    return results


# ── Study 2.4: Price vs Condition/Renovation ───────────────────────────────
def study_2_4(all_docs):
    print("\n═══ Study 2.4: Price vs Condition and Renovation ═══")
    results = {}

    for suburb in CORE_SUBURBS:
        sd = [d for d in all_docs if d["_suburb"] == suburb and d.get("_ppsqm")]

        # Condition score vs $/sqm
        cond_buckets = defaultdict(list)
        for d in sd:
            cs = safe_get(d, "property_valuation_data.condition_summary.overall_score")
            if cs and isinstance(cs, (int, float)):
                cond_buckets[int(cs)].append(d["_ppsqm"])

        # Renovation level vs $/sqm
        reno_buckets = defaultdict(list)
        for d in sd:
            rl = safe_get(d, "property_valuation_data.renovation.overall_renovation_level")
            if rl:
                reno_buckets[rl].append(d["_ppsqm"])

        # Renovation recency vs $/sqm
        recency_buckets = defaultdict(list)
        for d in sd:
            rr = safe_get(d, "property_valuation_data.renovation.renovation_recency")
            if rr:
                recency_buckets[rr].append(d["_ppsqm"])

        # Spearman: condition vs $/sqm
        cond_pairs = [(safe_get(d, "property_valuation_data.condition_summary.overall_score"), d["_ppsqm"])
                      for d in sd if safe_get(d, "property_valuation_data.condition_summary.overall_score")]
        cx = [p[0] for p in cond_pairs]
        cy = [p[1] for p in cond_pairs]
        cond_corr, cond_p = spearman_corr(cx, cy)

        results[suburb] = {
            "condition_vs_ppsqm": {
                "by_score": {str(k): calc_stats(v) for k, v in sorted(cond_buckets.items()) if len(v) >= 3},
                "spearman_r": cond_corr,
                "p_value": cond_p,
            },
            "renovation_vs_ppsqm": {
                "by_level": {k: calc_stats(v) for k, v in reno_buckets.items() if len(v) >= 3},
            },
            "recency_vs_ppsqm": {
                "by_recency": {k: calc_stats(v) for k, v in recency_buckets.items() if len(v) >= 3},
            },
        }

        print(f"  {suburb}: condition→$/sqm r={cond_corr}, p={cond_p}")
        for level, data in sorted(results[suburb]["renovation_vs_ppsqm"]["by_level"].items(), key=lambda x: x[1]["median"] if x[1] else 0, reverse=True):
            if data:
                print(f"    {level:25s} median $/sqm=${data['median']:,.0f} (n={data['count']})")

    with open(os.path.join(OUTPUT_DIR, "study_2_4_condition.json"), "w") as f:
        json.dump(results, f, indent=2)
    return results


# ── Study 2.5: Price vs Kitchen/Bathroom Quality ──────────────────────────
def study_2_5(all_docs):
    print("\n═══ Study 2.5: Price vs Kitchen/Bathroom Quality ═══")
    results = {}

    for suburb in CORE_SUBURBS:
        sd = [d for d in all_docs if d["_suburb"] == suburb and d.get("_ppsqm")]

        # Island bench
        ib_yes = [d["_ppsqm"] for d in sd if safe_get(d, "property_valuation_data.kitchen.island_bench") is True]
        ib_no = [d["_ppsqm"] for d in sd if safe_get(d, "property_valuation_data.kitchen.island_bench") is False]
        u, p = mann_whitney(ib_yes, ib_no)

        # Benchtop material
        bt_buckets = defaultdict(list)
        for d in sd:
            bt = safe_get(d, "property_valuation_data.kitchen.benchtop_material")
            if bt:
                bt_buckets[bt].append(d["_ppsqm"])

        # Appliances quality
        aq_buckets = defaultdict(list)
        for d in sd:
            aq = safe_get(d, "property_valuation_data.kitchen.appliances_quality")
            if aq:
                aq_buckets[aq].append(d["_ppsqm"])

        # Kitchen quality score correlation
        kq_pairs = [(safe_get(d, "property_valuation_data.kitchen.quality_score"), d["_ppsqm"])
                    for d in sd if safe_get(d, "property_valuation_data.kitchen.quality_score")]
        kqx = [p[0] for p in kq_pairs]
        kqy = [p[1] for p in kq_pairs]
        kq_corr, kq_p = spearman_corr(kqx, kqy)

        # Bathroom fixtures quality
        fix_buckets = defaultdict(list)
        for d in sd:
            baths = safe_get(d, "property_valuation_data.bathrooms") or []
            if isinstance(baths, list):
                for bath in baths:
                    if isinstance(bath, dict):
                        fq = bath.get("fixtures_quality")
                        if fq:
                            fix_buckets[fq].append(d["_ppsqm"])
                            break

        results[suburb] = {
            "island_bench": {
                "with": calc_stats(ib_yes), "without": calc_stats(ib_no),
                "premium_pct": round(100 * (np.median(ib_yes) / np.median(ib_no) - 1), 1) if ib_yes and ib_no else None,
                "mann_whitney_p": p,
            },
            "benchtop_material": {k: calc_stats(v) for k, v in bt_buckets.items() if len(v) >= 3},
            "appliances_quality": {k: calc_stats(v) for k, v in aq_buckets.items() if len(v) >= 3},
            "kitchen_quality_score": {"spearman_r": kq_corr, "p_value": kq_p, "n": len(kqx)},
            "bathroom_fixtures": {k: calc_stats(v) for k, v in fix_buckets.items() if len(v) >= 3},
        }

        ib = results[suburb]["island_bench"]
        print(f"  {suburb}:")
        print(f"    Island bench: {'+' if ib['premium_pct'] and ib['premium_pct'] > 0 else ''}{ib['premium_pct']}% $/sqm, p={ib['mann_whitney_p']}")
        print(f"    Kitchen quality→$/sqm: r={kq_corr}, p={kq_p}")
        for mat, data in sorted(results[suburb]["benchtop_material"].items(), key=lambda x: x[1]["median"] if x[1] else 0, reverse=True):
            if data:
                print(f"    {mat:20s} $/sqm=${data['median']:,.0f} (n={data['count']})")

    with open(os.path.join(OUTPUT_DIR, "study_2_5_kitchen_bath.json"), "w") as f:
        json.dump(results, f, indent=2)
    return results


# ── Study 2.6: Price vs Outdoor Amenity ────────────────────────────────────
def study_2_6(all_docs):
    print("\n═══ Study 2.6: Price vs Outdoor Amenity ═══")
    results = {}

    for suburb in CORE_SUBURBS:
        sd = [d for d in all_docs if d["_suburb"] == suburb and d.get("_ppsqm")]

        # Pool
        pool_yes = [d["_ppsqm"] for d in sd if safe_get(d, "property_valuation_data.outdoor.pool_present") is True]
        pool_no = [d["_ppsqm"] for d in sd if safe_get(d, "property_valuation_data.outdoor.pool_present") is False]
        u, p = mann_whitney(pool_yes, pool_no)

        # Pool type breakdown
        pool_types = defaultdict(list)
        for d in sd:
            pt = safe_get(d, "property_valuation_data.outdoor.pool_type")
            if pt and pt != "none":
                pool_types[pt].append(d["_ppsqm"])

        # Landscaping quality
        land_buckets = defaultdict(list)
        for d in sd:
            lq = safe_get(d, "property_valuation_data.outdoor.landscaping_quality")
            if lq:
                land_buckets[lq].append(d["_ppsqm"])

        # Outdoor entertainment score correlation
        oe_pairs = [(safe_get(d, "property_valuation_data.outdoor.outdoor_entertainment_score"), d["_ppsqm"])
                    for d in sd if safe_get(d, "property_valuation_data.outdoor.outdoor_entertainment_score")]
        oex = [p[0] for p in oe_pairs]
        oey = [p[1] for p in oe_pairs]
        oe_corr, oe_p = spearman_corr(oex, oey)

        results[suburb] = {
            "pool_impact": {
                "with_pool": calc_stats(pool_yes), "without_pool": calc_stats(pool_no),
                "ppsqm_premium_pct": round(100 * (np.median(pool_yes) / np.median(pool_no) - 1), 1) if pool_yes and pool_no else None,
                "mann_whitney_p": p,
            },
            "pool_type": {k: calc_stats(v) for k, v in pool_types.items() if len(v) >= 3},
            "landscaping_quality": {k: calc_stats(v) for k, v in land_buckets.items() if len(v) >= 3},
            "entertainment_score": {"spearman_r": oe_corr, "p_value": oe_p, "n": len(oex)},
        }

        pi = results[suburb]["pool_impact"]
        print(f"  {suburb}:")
        print(f"    Pool: {'+' if pi['ppsqm_premium_pct'] and pi['ppsqm_premium_pct'] > 0 else ''}{pi['ppsqm_premium_pct']}% $/sqm, p={pi['mann_whitney_p']}")
        print(f"    Entertainment score→$/sqm: r={oe_corr}")

    with open(os.path.join(OUTPUT_DIR, "study_2_6_outdoor.json"), "w") as f:
        json.dump(results, f, indent=2)
    return results


# ── Study 2.7: DOM vs ALL Characteristics ──────────────────────────────────
def study_2_7(all_docs):
    print("\n═══ Study 2.7: DOM vs Property Characteristics ═══")
    results = {}

    docs_with_dom = [d for d in all_docs if d.get("_dom") and d["_dom"] > 0 and d["_suburb"] in CORE_SUBURBS]
    print(f"  Records with DOM in core suburbs: {len(docs_with_dom)}")

    # Correlations with DOM
    dom_correlations = {}

    numeric_fields = {
        "condition_overall": lambda d: safe_get(d, "property_valuation_data.condition_summary.overall_score"),
        "presentation_score": lambda d: safe_get(d, "property_valuation_data.property_metadata.property_presentation_score"),
        "market_appeal_score": lambda d: safe_get(d, "property_valuation_data.property_metadata.market_appeal_score"),
        "kitchen_quality": lambda d: safe_get(d, "property_valuation_data.kitchen.quality_score"),
        "outdoor_entertainment": lambda d: safe_get(d, "property_valuation_data.outdoor.outdoor_entertainment_score"),
        "landscaping_score": lambda d: safe_get(d, "property_valuation_data.outdoor.landscaping_score"),
        "modern_features_score": lambda d: safe_get(d, "property_valuation_data.renovation.modern_features_score"),
        "numeric_price": lambda d: d["_numeric_price"],
        "bedrooms": lambda d: d.get("bedrooms"),
        "floor_area": lambda d: safe_get(d, "floor_plan_analysis.internal_floor_area.value"),
    }

    for fname, extractor in numeric_fields.items():
        pairs = [(extractor(d), d["_dom"]) for d in docs_with_dom if extractor(d) is not None and isinstance(extractor(d), (int, float))]
        x = [p[0] for p in pairs]
        y = [p[1] for p in pairs]
        r, p = spearman_corr(x, y)
        dom_correlations[fname] = {"spearman_r": r, "p_value": p, "n": len(x)}

    # Binary features vs DOM
    binary_tests = {}
    for fname, extractor in [
        ("pool", lambda d: safe_get(d, "property_valuation_data.outdoor.pool_present")),
        ("water_views", lambda d: safe_get(d, "property_valuation_data.outdoor.water_views")),
        ("island_bench", lambda d: safe_get(d, "property_valuation_data.kitchen.island_bench")),
    ]:
        yes_dom = [d["_dom"] for d in docs_with_dom if extractor(d) is True]
        no_dom = [d["_dom"] for d in docs_with_dom if extractor(d) is False]
        u, p = mann_whitney(yes_dom, no_dom)
        binary_tests[fname] = {
            "yes_dom": calc_stats(yes_dom), "no_dom": calc_stats(no_dom),
            "dom_difference_days": round(np.median(yes_dom) - np.median(no_dom), 1) if yes_dom and no_dom else None,
            "mann_whitney_p": p,
        }

    # Renovation level vs DOM
    reno_dom = defaultdict(list)
    for d in docs_with_dom:
        rl = safe_get(d, "property_valuation_data.renovation.overall_renovation_level")
        if rl:
            reno_dom[rl].append(d["_dom"])

    results = {
        "correlations": dom_correlations,
        "binary_features": binary_tests,
        "renovation_vs_dom": {k: calc_stats(v) for k, v in reno_dom.items() if len(v) >= 5},
        "total_records": len(docs_with_dom),
    }

    print("\n  DOM Correlations (sorted by |r|):")
    for fname, data in sorted(dom_correlations.items(), key=lambda x: abs(x[1]["spearman_r"] or 0), reverse=True):
        sig = "***" if data["p_value"] and data["p_value"] < 0.01 else "**" if data["p_value"] and data["p_value"] < 0.05 else ""
        print(f"    {fname:30s} r={data['spearman_r']:+.3f}  p={data['p_value']}  n={data['n']} {sig}")

    print("\n  Binary Features vs DOM:")
    for fname, data in binary_tests.items():
        print(f"    {fname:20s} diff={data['dom_difference_days']:+.1f}d  p={data['mann_whitney_p']}")

    with open(os.path.join(OUTPUT_DIR, "study_2_7_dom_drivers.json"), "w") as f:
        json.dump(results, f, indent=2)
    return results


# ── Study 2.8: DOM vs Pricing Strategy ─────────────────────────────────────
def study_2_8(all_docs):
    print("\n═══ Study 2.8: DOM vs Pricing Strategy ═══")
    results = {}

    for suburb in CORE_SUBURBS:
        sd = [d for d in all_docs if d["_suburb"] == suburb and d.get("_dom") and d["_dom"] > 0 and d["_numeric_price"]]

        # Price percentile within suburb-bedroom cohort
        # First compute cohort medians
        cohort_medians = {}
        for d in all_docs:
            if d["_suburb"] == suburb and d["_numeric_price"] and d.get("bedrooms"):
                key = d["bedrooms"]
                cohort_medians.setdefault(key, []).append(d["_numeric_price"])
        for k in cohort_medians:
            cohort_medians[k] = np.median(cohort_medians[k])

        price_position_pairs = []
        for d in sd:
            beds = d.get("bedrooms")
            if beds and beds in cohort_medians and cohort_medians[beds] > 0:
                position = (d["_numeric_price"] / cohort_medians[beds] - 1) * 100
                price_position_pairs.append((position, d["_dom"]))

        if price_position_pairs:
            px = [p[0] for p in price_position_pairs]
            py = [p[1] for p in price_position_pairs]
            r, p = spearman_corr(px, py)

            # Bucket analysis
            above = [d for pos, d in price_position_pairs if pos > 10]
            at_market = [d for pos, d in price_position_pairs if -10 <= pos <= 10]
            below = [d for pos, d in price_position_pairs if pos < -10]

            results[suburb] = {
                "price_position_vs_dom": {"spearman_r": r, "p_value": p, "n": len(px)},
                "by_position": {
                    "above_10pct": calc_stats(above),
                    "at_market": calc_stats(at_market),
                    "below_10pct": calc_stats(below),
                },
            }

            print(f"  {suburb}: price position→DOM r={r}, p={p}, n={len(px)}")
            if above:
                print(f"    Above 10%: median DOM={np.median(above):.0f}d (n={len(above)})")
            if at_market:
                print(f"    At market: median DOM={np.median(at_market):.0f}d (n={len(at_market)})")
            if below:
                print(f"    Below 10%: median DOM={np.median(below):.0f}d (n={len(below)})")

    # Domain valuation comparison
    print("\n  Sale price vs Domain valuation:")
    for suburb in CORE_SUBURBS:
        sd = [d for d in all_docs if d["_suburb"] == suburb and d.get("_domain_val") and d["_numeric_price"]]
        premiums = []
        for d in sd:
            dv_mid = safe_get(d, "_domain_val.mid")
            if dv_mid and isinstance(dv_mid, (int, float)) and dv_mid > 0:
                prem = (d["_numeric_price"] / dv_mid - 1) * 100
                premiums.append(prem)

        if premiums:
            results.setdefault(suburb, {})["domain_valuation_comparison"] = {
                "distribution": calc_stats(premiums),
                "sold_above_pct": round(100 * sum(1 for p in premiums if p > 0) / len(premiums), 1),
                "sold_below_pct": round(100 * sum(1 for p in premiums if p < 0) / len(premiums), 1),
            }
            print(f"  {suburb}: median diff={np.median(premiums):+.1f}%, above Domain: {sum(1 for p in premiums if p > 0)}/{len(premiums)}")

    with open(os.path.join(OUTPUT_DIR, "study_2_8_pricing.json"), "w") as f:
        json.dump(results, f, indent=2)
    return results


# ── Study 2.9: DOM vs Agency ──────────────────────────────────────────────
def study_2_9(all_docs):
    print("\n═══ Study 2.9: DOM vs Agency ═══")
    results = {}

    for suburb in CORE_SUBURBS:
        sd = [d for d in all_docs if d["_suburb"] == suburb and d.get("_dom") and d["_dom"] > 0]
        suburb_median_dom = np.median([d["_dom"] for d in sd]) if sd else 0

        agencies = defaultdict(list)
        for d in sd:
            ag = d.get("agency_name")
            if ag:
                agencies[ag].append(d["_dom"])

        agency_results = []
        for ag, doms in agencies.items():
            if len(doms) >= 3:
                residual = np.median(doms) - suburb_median_dom
                agency_results.append({
                    "agency": ag,
                    "sales_with_dom": len(doms),
                    "median_dom": round(float(np.median(doms)), 1),
                    "mean_dom": round(float(np.mean(doms)), 1),
                    "dom_residual": round(float(residual), 1),
                })

        agency_results.sort(key=lambda x: x["median_dom"])

        results[suburb] = {
            "suburb_median_dom": round(float(suburb_median_dom), 1),
            "agencies": agency_results,
        }

        print(f"\n  {suburb} (suburb median: {suburb_median_dom:.0f}d):")
        for a in agency_results[:5]:
            print(f"    {a['agency']:40s} median={a['median_dom']:.0f}d (residual={a['dom_residual']:+.1f}d, n={a['sales_with_dom']})")
        if len(agency_results) > 5:
            print(f"    ... and {len(agency_results)-5} more")

    with open(os.path.join(OUTPUT_DIR, "study_2_9_agency_dom.json"), "w") as f:
        json.dump(results, f, indent=2)
    return results


# ── Generate Summary ───────────────────────────────────────────────────────
def generate_summary(s21, s22, s23, s24, s25, s26, s27, s28, s29):
    md = []
    md.append("# Phase 2: Bivariate Analysis — \"What Co-Varies With Price and DOM?\"")
    md.append(f"## Generated {datetime.now().strftime('%Y-%m-%d %H:%M AEST')}")
    md.append("")

    # 2.1 Structural
    md.append("---")
    md.append("## 2.1 Price vs Structural Features")
    md.append("")
    for suburb in CORE_SUBURBS:
        r = s21[suburb]
        md.append(f"### {suburb.replace('_',' ').title()}")
        md.append(f"- Floor area → price: r={r['floor_area_vs_price']['spearman_r']} (n={r['floor_area_vs_price']['n']})")
        md.append(f"- Lot size → price: r={r['lot_size_vs_price']['spearman_r']} (n={r['lot_size_vs_price']['n']})")
        md.append("")
        md.append("| Bedrooms | Median Price | Marginal Value | N |")
        md.append("|----------|-------------|----------------|---|")
        for b, data in sorted(r["bedrooms"].items()):
            mv = f"+${data['marginal_value']:,}" if data['marginal_value'] else "base"
            md.append(f"| {b} | ${data['median_price']:,} | {mv} | {data['count']} |")
        md.append("")

    # 2.2 Location
    md.append("---")
    md.append("## 2.2 Price vs Location Features")
    md.append("")
    md.append("| Feature | Robina | Varsity Lakes | Burleigh Waters |")
    md.append("|---------|--------|---------------|-----------------|")
    for feat in ["cul_de_sac", "corner_lot", "faces_major_road", "canal_frontage"]:
        row = f"| {feat} |"
        for suburb in CORE_SUBURBS:
            data = s22.get(suburb, {}).get(feat, {})
            prem = data.get("premium_pct") or data.get("discount_pct")
            p_val = data.get("mann_whitney_p")
            sig = "***" if p_val and p_val < 0.01 else "**" if p_val and p_val < 0.05 else ""
            row += f" {prem:+.1f}% {sig} |" if prem is not None else " N/A |"
        md.append(row)
    md.append("")

    # 2.3 Water
    md.append("---")
    md.append("## 2.3 Water Views Impact")
    md.append("")
    md.append("| Suburb | Price Premium | $/sqm Premium | Dollar Premium | p-value |")
    md.append("|--------|-------------|---------------|----------------|---------|")
    for suburb in CORE_SUBURBS:
        wvi = s23[suburb]["water_views_impact"]
        ppsqm = s23[suburb]["ppsqm_comparison"]["ppsqm_premium_pct"]
        md.append(f"| {suburb} | +{wvi['price_premium_pct']}% | +{ppsqm}% | +${wvi['price_premium_dollar']:,} | {wvi['mann_whitney_p']} |")
    md.append("")

    # 2.4 Condition
    md.append("---")
    md.append("## 2.4 Condition and Renovation vs $/sqm")
    md.append("")
    for suburb in CORE_SUBURBS:
        r = s24[suburb]
        md.append(f"### {suburb.replace('_',' ').title()} (condition→$/sqm r={r['condition_vs_ppsqm']['spearman_r']})")
        if r["renovation_vs_ppsqm"]["by_level"]:
            md.append("| Renovation Level | Median $/sqm | N |")
            md.append("|-----------------|-------------|---|")
            for level, data in sorted(r["renovation_vs_ppsqm"]["by_level"].items(), key=lambda x: x[1]["median"] if x[1] else 0, reverse=True):
                if data:
                    md.append(f"| {level} | ${data['median']:,.0f} | {data['count']} |")
        md.append("")

    # 2.5 Kitchen/Bath
    md.append("---")
    md.append("## 2.5 Kitchen and Bathroom Quality vs $/sqm")
    md.append("")
    for suburb in CORE_SUBURBS:
        r = s25[suburb]
        ib = r["island_bench"]
        md.append(f"### {suburb.replace('_',' ').title()}")
        p_str = f"p={ib['mann_whitney_p']}" if ib['mann_whitney_p'] else ""
        md.append(f"- Island bench: {'+' if ib['premium_pct'] and ib['premium_pct'] > 0 else ''}{ib['premium_pct']}% $/sqm {p_str}")
        md.append(f"- Kitchen quality→$/sqm: r={r['kitchen_quality_score']['spearman_r']}")
        if r["benchtop_material"]:
            md.append("| Benchtop | Median $/sqm | N |")
            md.append("|----------|-------------|---|")
            for mat, data in sorted(r["benchtop_material"].items(), key=lambda x: x[1]["median"] if x[1] else 0, reverse=True):
                if data:
                    md.append(f"| {mat} | ${data['median']:,.0f} | {data['count']} |")
        md.append("")

    # 2.6 Outdoor
    md.append("---")
    md.append("## 2.6 Outdoor Amenity vs $/sqm")
    md.append("")
    md.append("| Suburb | Pool $/sqm Premium | p-value | Entertainment→$/sqm r |")
    md.append("|--------|-------------------|---------|----------------------|")
    for suburb in CORE_SUBURBS:
        pi = s26[suburb]["pool_impact"]
        oe = s26[suburb]["entertainment_score"]
        md.append(f"| {suburb} | {'+' if pi['ppsqm_premium_pct'] and pi['ppsqm_premium_pct'] > 0 else ''}{pi['ppsqm_premium_pct']}% | {pi['mann_whitney_p']} | {oe['spearman_r']} |")
    md.append("")

    # 2.7 DOM Drivers
    md.append("---")
    md.append("## 2.7 DOM Drivers (Core Suburbs Combined)")
    md.append("")
    md.append("### Numeric Correlations with DOM")
    md.append("| Factor | Spearman r | p-value | N | Interpretation |")
    md.append("|--------|-----------|---------|---|----------------|")
    for fname, data in sorted(s27["correlations"].items(), key=lambda x: abs(x[1]["spearman_r"] or 0), reverse=True):
        r_val = data["spearman_r"] or 0
        interp = "higher → slower" if r_val > 0.05 else "higher → faster" if r_val < -0.05 else "no effect"
        sig = "***" if data["p_value"] and data["p_value"] < 0.01 else "**" if data["p_value"] and data["p_value"] < 0.05 else ""
        md.append(f"| {fname} | {r_val:+.3f} | {data['p_value']} | {data['n']} | {interp} {sig} |")
    md.append("")

    md.append("### Binary Features vs DOM")
    md.append("| Feature | DOM Difference | p-value |")
    md.append("|---------|---------------|---------|")
    for fname, data in s27["binary_features"].items():
        md.append(f"| {fname} | {data['dom_difference_days']:+.1f} days | {data['mann_whitney_p']} |")
    md.append("")

    # 2.8 Pricing Strategy
    md.append("---")
    md.append("## 2.8 Pricing Strategy vs DOM")
    md.append("")
    for suburb in CORE_SUBURBS:
        r = s28.get(suburb, {})
        if "price_position_vs_dom" in r:
            pp = r["price_position_vs_dom"]
            md.append(f"### {suburb.replace('_',' ').title()} (r={pp['spearman_r']}, n={pp['n']})")
            bp = r.get("by_position", {})
            for pos, data in bp.items():
                if data:
                    md.append(f"- {pos}: median DOM={data['median']:.0f}d (n={data['count']})")
        if "domain_valuation_comparison" in r:
            dv = r["domain_valuation_comparison"]
            md.append(f"- vs Domain valuation: median diff={dv['distribution']['median']:+.1f}%, above={dv['sold_above_pct']}%, below={dv['sold_below_pct']}%")
        md.append("")

    # 2.9 Agency DOM
    md.append("---")
    md.append("## 2.9 Agency Speed (DOM)")
    md.append("")
    for suburb in CORE_SUBURBS:
        r = s29[suburb]
        md.append(f"### {suburb.replace('_',' ').title()} (suburb median: {r['suburb_median_dom']}d)")
        md.append("| Agency | Median DOM | Residual | N |")
        md.append("|--------|-----------|----------|---|")
        for a in r["agencies"][:8]:
            md.append(f"| {a['agency']} | {a['median_dom']:.0f}d | {a['dom_residual']:+.1f}d | {a['sales_with_dom']} |")
        md.append("")

    md.append("---")
    md.append(f"*Fields Estate — Phase 2 Bivariate Analysis | {datetime.now().strftime('%Y-%m-%d')}*")

    path = "/home/fields/Fields_Orchestrator/output/positioning_research/phase_2_summary.md"
    with open(path, "w") as f:
        f.write("\n".join(md))
    print(f"\n  Summary: {path}")
    return "\n".join(md)


# ── Main ────────────────────────────────────────────────────────────────────
def main():
    print("╔═══════════════════════════════════════════════════════════════╗")
    print("║  Phase 2: Bivariate Analysis — Positioning Research           ║")
    print("╚═══════════════════════════════════════════════════════════════╝")

    all_docs = load_all_data()

    s21 = study_2_1(all_docs)
    s22 = study_2_2(all_docs)
    s23 = study_2_3(all_docs)
    s24 = study_2_4(all_docs)
    s25 = study_2_5(all_docs)
    s26 = study_2_6(all_docs)
    s27 = study_2_7(all_docs)
    s28 = study_2_8(all_docs)
    s29 = study_2_9(all_docs)

    generate_summary(s21, s22, s23, s24, s25, s26, s27, s28, s29)

    print("\n" + "=" * 60)
    print("Phase 2 COMPLETE")
    print("=" * 60)


if __name__ == "__main__":
    main()
