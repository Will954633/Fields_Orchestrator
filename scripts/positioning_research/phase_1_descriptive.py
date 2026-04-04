#!/usr/bin/env python3
"""
Phase 1: Descriptive Statistics — Property Positioning Research
================================================================
"What does this market look like?"

Studies:
  1.1 - Market size and composition (volume, type mix, bedroom distribution)
  1.2 - Price distributions per suburb/type/bedroom
  1.3 - $/sqm distributions (internal floor area and land)
  1.4 - Lot size distributions and segmentation
  1.5 - Feature frequency (what's universal vs rare?)
  1.6 - Condition and renovation profiles
  1.7 - Agency market share
  1.8 - DOM distributions (using reconstructed DOM from Gold_Coast timeline)
  1.9 - Monthly time series (volume, median price, seasonal patterns)

Depends on: Phase 0 (clean data, price parsing, address matching)
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

# ── Config ──────────────────────────────────────────────────────────────────
OUTPUT_DIR = "/home/fields/Fields_Orchestrator/output/positioning_research/phase_1"
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


def stats(values):
    """Compute standard stats for a list of numbers."""
    if not values:
        return None
    arr = np.array(values)
    return {
        "count": len(values),
        "mean": round(float(np.mean(arr)), 1),
        "median": round(float(np.median(arr)), 1),
        "p10": round(float(np.percentile(arr, 10)), 1),
        "p25": round(float(np.percentile(arr, 25)), 1),
        "p75": round(float(np.percentile(arr, 75)), 1),
        "p90": round(float(np.percentile(arr, 90)), 1),
        "min": round(float(np.min(arr)), 1),
        "max": round(float(np.max(arr)), 1),
        "std": round(float(np.std(arr)), 1),
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


def load_all_sold():
    all_docs = []
    for suburb in TARGET_SUBURBS:
        time.sleep(1)
        docs = list(db_target[suburb].find({}))
        for d in docs:
            d["_suburb"] = suburb
            d["_numeric_price"] = parse_price(d.get("sale_price"))
        all_docs.extend(docs)
        print(f"  Loaded {suburb}: {len(docs)}")
    print(f"  Total: {len(all_docs)}")
    return all_docs


def load_gc_timeline_dom(all_docs):
    """Load DOM from Gold_Coast property_timeline for matched records."""
    print("\n  Loading DOM from Gold_Coast property timelines...")
    dom_count = 0
    for suburb in TARGET_SUBURBS:
        time.sleep(2)
        suburb_docs = [d for d in all_docs if d["_suburb"] == suburb]

        gc_docs = list(db_gc[suburb].find(
            {"scraped_data.property_timeline": {"$exists": True}},
            {"complete_address": 1, "scraped_data.property_timeline": 1}
        ))

        gc_by_addr = {}
        for gc in gc_docs:
            norm = normalise_address(gc.get("complete_address", ""))
            if norm:
                gc_by_addr[norm] = gc

        for td in suburb_docs:
            # Already has DOM?
            if td.get("_dom"):
                continue

            # Try direct field first
            if td.get("time_on_market_days") and isinstance(td["time_on_market_days"], (int, float)):
                td["_dom"] = int(td["time_on_market_days"])
                td["_dom_source"] = "direct"
                dom_count += 1
                continue

            # Try Gold_Coast timeline match
            norm = normalise_address(td.get("address", ""))
            gc_match = gc_by_addr.get(norm)
            if not gc_match:
                stripped = re.sub(r"^\d+/", "", norm)
                gc_match = gc_by_addr.get(stripped)

            if gc_match:
                timeline = safe_get(gc_match, "scraped_data.property_timeline") or []
                for event in timeline:
                    if event.get("is_sold") and event.get("days_on_market"):
                        td["_dom"] = int(event["days_on_market"])
                        td["_dom_source"] = "gc_timeline"
                        dom_count += 1
                        break

    total_with_dom = sum(1 for d in all_docs if d.get("_dom"))
    print(f"  DOM recovered: {total_with_dom}/{len(all_docs)} ({100*total_with_dom/len(all_docs):.1f}%)")
    return all_docs


# ── Study 1.1: Market Size and Composition ─────────────────────────────────
def study_1_1(all_docs):
    print("\n═══ Study 1.1: Market Size and Composition ═══")
    results = {}

    for suburb in TARGET_SUBURBS:
        sd = [d for d in all_docs if d["_suburb"] == suburb]

        # Monthly volume
        monthly = defaultdict(int)
        for d in sd:
            dt = d.get("sale_date", "")
            if dt and len(dt) >= 7:
                monthly[dt[:7]] += 1

        # Property type
        types = Counter(d.get("property_type", "Unknown") for d in sd)

        # Bedrooms
        beds = Counter(d.get("bedrooms") for d in sd if d.get("bedrooms"))

        # Bathrooms
        baths = Counter(d.get("bathrooms") for d in sd if d.get("bathrooms"))

        results[suburb] = {
            "total_sales": len(sd),
            "monthly_volume": dict(sorted(monthly.items())),
            "avg_monthly": round(len(sd) / max(len(monthly), 1), 1),
            "property_types": dict(types.most_common()),
            "bedrooms": dict(sorted(beds.items())),
            "bathrooms": dict(sorted(baths.items())),
        }

        print(f"  {suburb}: {len(sd)} sales, avg {results[suburb]['avg_monthly']}/month")
        print(f"    Types: {dict(types.most_common(3))}")
        print(f"    Beds: {dict(sorted(beds.items()))}")

    with open(os.path.join(OUTPUT_DIR, "study_1_1_composition.json"), "w") as f:
        json.dump(results, f, indent=2)
    return results


# ── Study 1.2: Price Distributions ─────────────────────────────────────────
def study_1_2(all_docs):
    print("\n═══ Study 1.2: Price Distributions ═══")
    results = {}

    for suburb in TARGET_SUBURBS:
        sd = [d for d in all_docs if d["_suburb"] == suburb]
        prices = [d["_numeric_price"] for d in sd if d["_numeric_price"]]

        # Overall
        suburb_stats = stats(prices)

        # By property type
        by_type = {}
        for ptype in set(d.get("property_type", "Unknown") for d in sd):
            tp = [d["_numeric_price"] for d in sd if d.get("property_type") == ptype and d["_numeric_price"]]
            if len(tp) >= 5:
                by_type[ptype] = stats(tp)

        # By bedroom count
        by_beds = {}
        for beds in sorted(set(d.get("bedrooms") for d in sd if d.get("bedrooms"))):
            bp = [d["_numeric_price"] for d in sd if d.get("bedrooms") == beds and d["_numeric_price"]]
            if len(bp) >= 5:
                by_beds[str(beds)] = stats(bp)

        # Skewness
        if prices:
            arr = np.array(prices)
            mean = np.mean(arr)
            std = np.std(arr)
            if std > 0:
                skew = float(np.mean(((arr - mean) / std) ** 3))
            else:
                skew = 0
        else:
            skew = None

        results[suburb] = {
            "overall": suburb_stats,
            "skewness": round(skew, 2) if skew is not None else None,
            "by_property_type": by_type,
            "by_bedrooms": by_beds,
        }

        if suburb_stats:
            skew_str = f"{skew:.2f}" if skew is not None else "N/A"
            print(f"  {suburb}: median=${suburb_stats['median']:,.0f}, mean=${suburb_stats['mean']:,.0f}, skew={skew_str}")

    with open(os.path.join(OUTPUT_DIR, "study_1_2_prices.json"), "w") as f:
        json.dump(results, f, indent=2)
    return results


# ── Study 1.3: $/sqm Distributions ────────────────────────────────────────
def study_1_3(all_docs):
    print("\n═══ Study 1.3: $/sqm Distributions ═══")
    results = {}

    for suburb in TARGET_SUBURBS:
        sd = [d for d in all_docs if d["_suburb"] == suburb]

        # $/sqm using internal floor area
        ppsqm_internal = []
        for d in sd:
            price = d["_numeric_price"]
            area = safe_get(d, "floor_plan_analysis.internal_floor_area.value")
            if price and area and isinstance(area, (int, float)) and 30 < area < 1500:
                ppsqm_internal.append(price / area)

        # $/sqm using total land area
        ppsqm_land = []
        for d in sd:
            price = d["_numeric_price"]
            land = safe_get(d, "floor_plan_analysis.total_land_area.value")
            if price and land and isinstance(land, (int, float)) and 50 < land < 50000:
                ppsqm_land.append(price / land)

        results[suburb] = {
            "per_sqm_internal": stats(ppsqm_internal),
            "per_sqm_land": stats(ppsqm_land),
        }

        if ppsqm_internal:
            s = stats(ppsqm_internal)
            print(f"  {suburb}: $/sqm(internal) median=${s['median']:,.0f}, avg=${s['mean']:,.0f} (n={s['count']})")
        if ppsqm_land:
            s = stats(ppsqm_land)
            print(f"           $/sqm(land) median=${s['median']:,.0f}, avg=${s['mean']:,.0f} (n={s['count']})")

    with open(os.path.join(OUTPUT_DIR, "study_1_3_ppsqm.json"), "w") as f:
        json.dump(results, f, indent=2)
    return results


# ── Study 1.4: Lot Size Distributions ──────────────────────────────────────
def study_1_4(all_docs):
    print("\n═══ Study 1.4: Lot Size Distributions ═══")
    results = {}

    for suburb in TARGET_SUBURBS:
        sd = [d for d in all_docs if d["_suburb"] == suburb]

        lot_sizes = []
        for d in sd:
            ls = safe_get(d, "floor_plan_analysis.total_land_area.value")
            if ls and isinstance(ls, (int, float)) and 50 < ls < 50000:
                lot_sizes.append(ls)

        # Segmentation
        segments = {"micro_under_300": 0, "standard_300_700": 0, "large_700_1200": 0, "acreage_1200_plus": 0}
        for ls in lot_sizes:
            if ls < 300:
                segments["micro_under_300"] += 1
            elif ls < 700:
                segments["standard_300_700"] += 1
            elif ls < 1200:
                segments["large_700_1200"] += 1
            else:
                segments["acreage_1200_plus"] += 1

        results[suburb] = {
            "distribution": stats(lot_sizes),
            "segments": segments,
            "segment_pct": {k: round(100 * v / len(lot_sizes), 1) if lot_sizes else 0 for k, v in segments.items()},
        }

        if lot_sizes:
            s = stats(lot_sizes)
            print(f"  {suburb}: median={s['median']:.0f}sqm, avg={s['mean']:.0f}sqm (n={s['count']})")
            print(f"    Segments: {segments}")

    with open(os.path.join(OUTPUT_DIR, "study_1_4_lots.json"), "w") as f:
        json.dump(results, f, indent=2)
    return results


# ── Study 1.5: Feature Frequency ───────────────────────────────────────────
def study_1_5(all_docs):
    print("\n═══ Study 1.5: Feature Frequency Analysis ═══")
    results = {}

    # GPT-detected features (binary/categorical)
    gpt_features = {
        "pool_present": lambda d: safe_get(d, "property_valuation_data.outdoor.pool_present"),
        "water_views": lambda d: safe_get(d, "property_valuation_data.outdoor.water_views"),
        "island_bench": lambda d: safe_get(d, "property_valuation_data.kitchen.island_bench"),
        "butler_pantry": lambda d: safe_get(d, "property_valuation_data.kitchen.butler_pantry"),
        "has_professional_photography": lambda d: safe_get(d, "property_valuation_data.property_metadata.has_professional_photography"),
        "open_plan": lambda d: safe_get(d, "floor_plan_analysis.layout_features.open_plan"),
        "alfresco_present": lambda d: any(
            (os or {}).get("type") in ["alfresco", "patio", "deck", "verandah", "terrace", "balcony", "covered_patio", "pergola"]
            for os in (safe_get(d, "floor_plan_analysis.outdoor_spaces") or [])
        ) if safe_get(d, "floor_plan_analysis.outdoor_spaces") else None,
    }

    # Categorical features
    cat_features = {
        "pool_type": lambda d: safe_get(d, "property_valuation_data.outdoor.pool_type"),
        "benchtop_material": lambda d: safe_get(d, "property_valuation_data.kitchen.benchtop_material"),
        "architectural_style": lambda d: safe_get(d, "property_valuation_data.property_overview.architectural_style"),
        "cladding_material": lambda d: safe_get(d, "property_valuation_data.exterior.cladding_material"),
        "roof_type": lambda d: safe_get(d, "property_valuation_data.property_overview.roof_type"),
        "renovation_level": lambda d: safe_get(d, "property_valuation_data.renovation.overall_renovation_level"),
        "renovation_recency": lambda d: safe_get(d, "property_valuation_data.renovation.renovation_recency"),
        "maintenance_level": lambda d: safe_get(d, "property_valuation_data.condition_summary.maintenance_level"),
        "garage_type": lambda d: safe_get(d, "property_valuation_data.exterior.garage_type"),
        "image_quality": lambda d: safe_get(d, "property_valuation_data.property_metadata.image_quality"),
        "water_view_type": lambda d: safe_get(d, "property_valuation_data.outdoor.water_view_type"),
    }

    for suburb in TARGET_SUBURBS:
        sd = [d for d in all_docs if d["_suburb"] == suburb]
        total = len(sd)

        # Binary features
        binary_results = {}
        for fname, extractor in gpt_features.items():
            true_count = sum(1 for d in sd if extractor(d) is True)
            false_count = sum(1 for d in sd if extractor(d) is False)
            null_count = total - true_count - false_count
            binary_results[fname] = {
                "true": true_count,
                "false": false_count,
                "null": null_count,
                "prevalence_pct": round(100 * true_count / total, 1) if total else 0,
            }

        # Categorical features
        categorical_results = {}
        for fname, extractor in cat_features.items():
            values = [extractor(d) for d in sd if extractor(d) is not None]
            counts = Counter(values)
            categorical_results[fname] = {
                "distribution": dict(counts.most_common()),
                "total_with_data": len(values),
                "most_common": counts.most_common(1)[0] if counts else None,
            }

        # Listing features[] array
        all_features = []
        for d in sd:
            feats = d.get("features") or []
            all_features.extend(feats)
        feature_counts = Counter(all_features)

        results[suburb] = {
            "binary_features": binary_results,
            "categorical_features": categorical_results,
            "listing_features_top20": dict(feature_counts.most_common(20)),
        }

    # Print summary for core suburbs
    for suburb in CORE_SUBURBS:
        print(f"\n  {suburb.upper()}:")
        for fname, data in results[suburb]["binary_features"].items():
            print(f"    {fname:40s} {data['prevalence_pct']:5.1f}%")

    with open(os.path.join(OUTPUT_DIR, "study_1_5_features.json"), "w") as f:
        json.dump(results, f, indent=2)
    return results


# ── Study 1.6: Condition and Renovation Profiles ──────────────────────────
def study_1_6(all_docs):
    print("\n═══ Study 1.6: Condition and Renovation Profiles ═══")
    results = {}

    for suburb in TARGET_SUBURBS:
        sd = [d for d in all_docs if d["_suburb"] == suburb]

        # Overall condition scores
        cond_scores = [safe_get(d, "property_valuation_data.condition_summary.overall_score")
                       for d in sd if safe_get(d, "property_valuation_data.condition_summary.overall_score")]
        cond_dist = Counter(int(s) for s in cond_scores if isinstance(s, (int, float)))

        # Sub-scores
        sub_scores = {}
        for field in ["exterior_score", "interior_score", "kitchen_score", "bathroom_score", "outdoor_score"]:
            vals = [safe_get(d, f"property_valuation_data.condition_summary.{field}")
                    for d in sd if safe_get(d, f"property_valuation_data.condition_summary.{field}")]
            sub_scores[field] = stats([v for v in vals if isinstance(v, (int, float))])

        # Renovation level
        reno_levels = Counter(safe_get(d, "property_valuation_data.renovation.overall_renovation_level")
                              for d in sd if safe_get(d, "property_valuation_data.renovation.overall_renovation_level"))

        # Renovation recency
        reno_recency = Counter(safe_get(d, "property_valuation_data.renovation.renovation_recency")
                               for d in sd if safe_get(d, "property_valuation_data.renovation.renovation_recency"))

        results[suburb] = {
            "overall_condition": stats(cond_scores),
            "condition_distribution": dict(sorted(cond_dist.items())),
            "sub_scores": sub_scores,
            "renovation_level": dict(reno_levels.most_common()),
            "renovation_recency": dict(reno_recency.most_common()),
        }

        print(f"  {suburb}: condition avg={stats(cond_scores)['mean'] if cond_scores else 'N/A'}")
        print(f"    Renovation: {dict(reno_levels.most_common(4))}")

    with open(os.path.join(OUTPUT_DIR, "study_1_6_condition.json"), "w") as f:
        json.dump(results, f, indent=2)
    return results


# ── Study 1.7: Agency Market Share ─────────────────────────────────────────
def study_1_7(all_docs):
    print("\n═══ Study 1.7: Agency Market Share ═══")
    results = {}

    for suburb in TARGET_SUBURBS:
        sd = [d for d in all_docs if d["_suburb"] == suburb]
        total = len(sd)

        agencies = defaultdict(lambda: {"count": 0, "total_value": 0, "prices": []})
        for d in sd:
            ag = d.get("agency_name", "Unknown")
            agencies[ag]["count"] += 1
            if d["_numeric_price"]:
                agencies[ag]["total_value"] += d["_numeric_price"]
                agencies[ag]["prices"].append(d["_numeric_price"])

        # Market share and stats
        agency_list = []
        for ag, data in agencies.items():
            entry = {
                "agency": ag,
                "sales": data["count"],
                "market_share_pct": round(100 * data["count"] / total, 1),
                "total_volume": data["total_value"],
                "avg_price": int(np.mean(data["prices"])) if data["prices"] else 0,
                "median_price": int(np.median(data["prices"])) if data["prices"] else 0,
            }
            agency_list.append(entry)

        agency_list.sort(key=lambda x: -x["sales"])

        # Concentration (Herfindahl index)
        shares = [a["market_share_pct"] / 100 for a in agency_list]
        hhi = sum(s ** 2 for s in shares)
        top3_share = sum(a["market_share_pct"] for a in agency_list[:3])

        results[suburb] = {
            "total_sales": total,
            "unique_agencies": len(agency_list),
            "top_10": agency_list[:10],
            "herfindahl_index": round(hhi, 4),
            "top3_combined_share": round(top3_share, 1),
            "concentration": "high" if hhi > 0.15 else "moderate" if hhi > 0.10 else "fragmented",
        }

        print(f"  {suburb}: {len(agency_list)} agencies, HHI={hhi:.3f} ({results[suburb]['concentration']}), top3={top3_share:.0f}%")
        for a in agency_list[:3]:
            print(f"    {a['agency']}: {a['sales']} sales ({a['market_share_pct']}%), avg=${a['avg_price']:,}")

    with open(os.path.join(OUTPUT_DIR, "study_1_7_agencies.json"), "w") as f:
        json.dump(results, f, indent=2)
    return results


# ── Study 1.8: DOM Distributions ───────────────────────────────────────────
def study_1_8(all_docs):
    print("\n═══ Study 1.8: DOM Distributions ═══")
    results = {}

    for suburb in TARGET_SUBURBS:
        sd = [d for d in all_docs if d["_suburb"] == suburb]
        doms = [d["_dom"] for d in sd if d.get("_dom") and d["_dom"] > 0]

        if doms:
            dom_stats = stats(doms)
            quick = sum(1 for d in doms if d <= 14)
            fast = sum(1 for d in doms if d <= 21)
            normal = sum(1 for d in doms if 21 < d <= 60)
            slow = sum(1 for d in doms if 60 < d <= 120)
            stale = sum(1 for d in doms if d > 120)

            results[suburb] = {
                "distribution": dom_stats,
                "segments": {
                    "quick_under_14d": {"count": quick, "pct": round(100 * quick / len(doms), 1)},
                    "fast_14_21d": {"count": fast - quick, "pct": round(100 * (fast - quick) / len(doms), 1)},
                    "normal_21_60d": {"count": normal, "pct": round(100 * normal / len(doms), 1)},
                    "slow_60_120d": {"count": slow, "pct": round(100 * slow / len(doms), 1)},
                    "stale_over_120d": {"count": stale, "pct": round(100 * stale / len(doms), 1)},
                },
                "dom_source_breakdown": Counter(d.get("_dom_source") for d in sd if d.get("_dom")),
            }
            # Make Counter serializable
            results[suburb]["dom_source_breakdown"] = dict(results[suburb]["dom_source_breakdown"])
            print(f"  {suburb}: median={dom_stats['median']:.0f}d, avg={dom_stats['mean']:.0f}d, n={dom_stats['count']}")
        else:
            results[suburb] = {"distribution": None, "note": "No DOM data available"}
            print(f"  {suburb}: NO DOM DATA")

    with open(os.path.join(OUTPUT_DIR, "study_1_8_dom.json"), "w") as f:
        json.dump(results, f, indent=2)
    return results


# ── Study 1.9: Monthly Time Series ────────────────────────────────────────
def study_1_9(all_docs):
    print("\n═══ Study 1.9: Monthly Time Series ═══")
    results = {"all_suburbs": {}, "by_suburb": {}}

    # All suburbs combined
    monthly_all = defaultdict(lambda: {"count": 0, "prices": []})
    for d in all_docs:
        dt = d.get("sale_date", "")
        if dt and len(dt) >= 7 and d["_numeric_price"]:
            month = dt[:7]
            monthly_all[month]["count"] += 1
            monthly_all[month]["prices"].append(d["_numeric_price"])

    for month in sorted(monthly_all.keys()):
        data = monthly_all[month]
        data["median_price"] = int(np.median(data["prices"]))
        data["mean_price"] = int(np.mean(data["prices"]))
        del data["prices"]

    results["all_suburbs"] = dict(sorted(monthly_all.items()))

    # Per suburb
    for suburb in TARGET_SUBURBS:
        sd = [d for d in all_docs if d["_suburb"] == suburb]
        monthly = defaultdict(lambda: {"count": 0, "prices": []})
        for d in sd:
            dt = d.get("sale_date", "")
            if dt and len(dt) >= 7 and d["_numeric_price"]:
                month = dt[:7]
                monthly[month]["count"] += 1
                monthly[month]["prices"].append(d["_numeric_price"])

        for month in monthly:
            monthly[month]["median_price"] = int(np.median(monthly[month]["prices"]))
            del monthly[month]["prices"]

        results["by_suburb"][suburb] = dict(sorted(monthly.items()))

    # Seasonal analysis (by calendar month across all data)
    by_cal_month = defaultdict(lambda: {"count": 0, "prices": []})
    for d in all_docs:
        dt = d.get("sale_date", "")
        if dt and len(dt) >= 7 and d["_numeric_price"]:
            cal_month = int(dt[5:7])
            by_cal_month[cal_month]["count"] += 1
            by_cal_month[cal_month]["prices"].append(d["_numeric_price"])

    seasonal = {}
    for m in sorted(by_cal_month.keys()):
        data = by_cal_month[m]
        month_name = datetime(2026, m, 1).strftime("%B")
        seasonal[month_name] = {
            "volume": data["count"],
            "median_price": int(np.median(data["prices"])),
        }
    results["seasonal_pattern"] = seasonal

    print("  Monthly time series computed")
    print(f"  Months covered: {len(results['all_suburbs'])}")
    print("\n  Seasonal pattern:")
    for month, data in seasonal.items():
        print(f"    {month:12s}: {data['volume']:3d} sales, median=${data['median_price']:,}")

    with open(os.path.join(OUTPUT_DIR, "study_1_9_timeseries.json"), "w") as f:
        json.dump(results, f, indent=2)
    return results


# ── Generate Summary ───────────────────────────────────────────────────────
def generate_summary(s11, s12, s13, s14, s15, s16, s17, s18, s19):
    md = []
    md.append("# Phase 1: Descriptive Statistics — \"What Does This Market Look Like?\"")
    md.append(f"## Generated {datetime.now().strftime('%Y-%m-%d %H:%M AEST')}")
    md.append("")

    # 1.1 Market Size
    md.append("---")
    md.append("## 1.1 Market Size and Composition")
    md.append("")
    md.append("| Suburb | Total Sales | Avg/Month | Top Property Type | Top Bedroom Count |")
    md.append("|--------|------------|-----------|-------------------|-------------------|")
    for suburb in TARGET_SUBURBS:
        d = s11[suburb]
        top_type = max(d["property_types"], key=d["property_types"].get)
        top_bed = max(d["bedrooms"], key=d["bedrooms"].get)
        md.append(f"| {suburb} | {d['total_sales']} | {d['avg_monthly']} | {top_type} ({d['property_types'][top_type]}) | {top_bed}-bed ({d['bedrooms'][top_bed]}) |")
    md.append("")

    # 1.2 Price Distributions
    md.append("---")
    md.append("## 1.2 Price Distributions")
    md.append("")
    md.append("| Suburb | Median | Mean | P25 | P75 | Skew | N |")
    md.append("|--------|--------|------|-----|-----|------|---|")
    for suburb in TARGET_SUBURBS:
        d = s12[suburb]["overall"]
        if d:
            md.append(f"| {suburb} | ${d['median']:,.0f} | ${d['mean']:,.0f} | ${d['p25']:,.0f} | ${d['p75']:,.0f} | {s12[suburb]['skewness']} | {d['count']} |")
    md.append("")

    # By bedrooms for core suburbs
    for suburb in CORE_SUBURBS:
        md.append(f"\n**{suburb.replace('_', ' ').title()} by bedrooms:**\n")
        md.append("| Beds | Median | Mean | N |")
        md.append("|------|--------|------|---|")
        for beds, data in sorted(s12[suburb]["by_bedrooms"].items()):
            md.append(f"| {beds} | ${data['median']:,.0f} | ${data['mean']:,.0f} | {data['count']} |")

    # 1.3 $/sqm
    md.append("\n---")
    md.append("## 1.3 Price Per Square Metre")
    md.append("")
    md.append("### Internal Floor Area")
    md.append("| Suburb | Median $/sqm | Mean $/sqm | P25 | P75 | N |")
    md.append("|--------|-------------|----------|-----|-----|---|")
    for suburb in TARGET_SUBURBS:
        d = s13[suburb]["per_sqm_internal"]
        if d:
            md.append(f"| {suburb} | ${d['median']:,.0f} | ${d['mean']:,.0f} | ${d['p25']:,.0f} | ${d['p75']:,.0f} | {d['count']} |")
    md.append("")

    if any(s13[s]["per_sqm_land"] for s in TARGET_SUBURBS):
        md.append("### Land Area")
        md.append("| Suburb | Median $/sqm | N |")
        md.append("|--------|-------------|---|")
        for suburb in TARGET_SUBURBS:
            d = s13[suburb]["per_sqm_land"]
            if d:
                md.append(f"| {suburb} | ${d['median']:,.0f} | {d['count']} |")
        md.append("")

    # 1.4 Lot Sizes
    md.append("---")
    md.append("## 1.4 Lot Size Distributions")
    md.append("")
    md.append("| Suburb | Median | Mean | <300sqm | 300-700 | 700-1200 | 1200+ | N |")
    md.append("|--------|--------|------|---------|---------|----------|-------|---|")
    for suburb in TARGET_SUBURBS:
        d = s14[suburb]
        if d["distribution"]:
            sp = d["segment_pct"]
            md.append(f"| {suburb} | {d['distribution']['median']:.0f}sqm | {d['distribution']['mean']:.0f}sqm | {sp['micro_under_300']}% | {sp['standard_300_700']}% | {sp['large_700_1200']}% | {sp['acreage_1200_plus']}% | {d['distribution']['count']} |")
    md.append("")

    # 1.5 Feature Frequency
    md.append("---")
    md.append("## 1.5 Feature Frequency (Core Suburbs)")
    md.append("")
    md.append("| Feature | Robina | Varsity Lakes | Burleigh Waters |")
    md.append("|---------|--------|---------------|-----------------|")
    for feat in ["pool_present", "water_views", "island_bench", "butler_pantry", "open_plan", "alfresco_present", "has_professional_photography"]:
        row = f"| {feat} |"
        for suburb in CORE_SUBURBS:
            pct = s15[suburb]["binary_features"].get(feat, {}).get("prevalence_pct", "-")
            row += f" {pct}% |"
        md.append(row)
    md.append("")

    # Categorical highlights
    for suburb in CORE_SUBURBS:
        md.append(f"\n**{suburb.replace('_', ' ').title()} — Key Categoricals:**")
        for cat in ["benchtop_material", "architectural_style", "renovation_level"]:
            data = s15[suburb]["categorical_features"].get(cat, {})
            if data.get("distribution"):
                top3 = dict(list(data["distribution"].items())[:3])
                md.append(f"- {cat}: {top3}")
    md.append("")

    # 1.6 Condition
    md.append("---")
    md.append("## 1.6 Condition and Renovation Profiles")
    md.append("")
    md.append("| Suburb | Avg Condition | Condition Distribution | Top Renovation Level |")
    md.append("|--------|--------------|----------------------|---------------------|")
    for suburb in TARGET_SUBURBS:
        d = s16[suburb]
        cond = d["overall_condition"]
        reno = d["renovation_level"]
        top_reno = max(reno, key=reno.get) if reno else "N/A"
        md.append(f"| {suburb} | {cond['mean'] if cond else 'N/A'}/10 | {d['condition_distribution']} | {top_reno} ({reno.get(top_reno, 0)}) |")
    md.append("")

    # 1.7 Agency
    md.append("---")
    md.append("## 1.7 Agency Market Share")
    md.append("")
    for suburb in CORE_SUBURBS:
        d = s17[suburb]
        md.append(f"\n### {suburb.replace('_', ' ').title()} — {d['unique_agencies']} agencies, HHI={d['herfindahl_index']} ({d['concentration']})")
        md.append("")
        md.append("| Rank | Agency | Sales | Share | Avg Price |")
        md.append("|------|--------|-------|-------|-----------|")
        for i, a in enumerate(d["top_10"], 1):
            md.append(f"| {i} | {a['agency']} | {a['sales']} | {a['market_share_pct']}% | ${a['avg_price']:,} |")
    md.append("")

    # 1.8 DOM
    md.append("---")
    md.append("## 1.8 Days on Market")
    md.append("")
    has_dom = any(s18[s].get("distribution") for s in TARGET_SUBURBS)
    if has_dom:
        md.append("| Suburb | Median | Mean | <=14d | 14-21d | 21-60d | 60-120d | >120d | N |")
        md.append("|--------|--------|------|-------|--------|--------|---------|-------|---|")
        for suburb in TARGET_SUBURBS:
            d = s18[suburb]
            if d.get("distribution"):
                ds = d["distribution"]
                seg = d["segments"]
                md.append(f"| {suburb} | {ds['median']:.0f}d | {ds['mean']:.0f}d | {seg['quick_under_14d']['pct']}% | {seg['fast_14_21d']['pct']}% | {seg['normal_21_60d']['pct']}% | {seg['slow_60_120d']['pct']}% | {seg['stale_over_120d']['pct']}% | {ds['count']} |")
    else:
        md.append("**DOM data is extremely sparse (0.8% coverage). DOM-dependent analyses require DOM reconstruction from Gold_Coast property timelines.**")
    md.append("")

    # 1.9 Seasonal
    md.append("---")
    md.append("## 1.9 Seasonal Patterns")
    md.append("")
    md.append("| Month | Volume | Median Price |")
    md.append("|-------|--------|-------------|")
    for month, data in s19["seasonal_pattern"].items():
        md.append(f"| {month} | {data['volume']} | ${data['median_price']:,} |")
    md.append("")

    # Key findings
    md.append("---")
    md.append("## Key Findings Summary")
    md.append("")

    # Find most/least expensive suburb
    price_ranking = sorted(TARGET_SUBURBS, key=lambda s: s12[s]["overall"]["median"] if s12[s]["overall"] else 0, reverse=True)
    price_parts = []
    for s in price_ranking:
        if s12[s]["overall"]:
            med = s12[s]["overall"]["median"]
            price_parts.append(f"{s} (${med:,.0f})")
    md.append(f"1. **Price hierarchy:** {' > '.join(price_parts)}")

    # $/sqm ranking
    ppsqm_ranking = sorted(
        [s for s in TARGET_SUBURBS if s13[s]["per_sqm_internal"]],
        key=lambda s: s13[s]["per_sqm_internal"]["median"],
        reverse=True
    )
    if ppsqm_ranking:
        ppsqm_parts = []
        for s in ppsqm_ranking[:5]:
            med = s13[s]["per_sqm_internal"]["median"]
            ppsqm_parts.append(f"{s} (${med:,.0f})")
        md.append(f"2. **$/sqm ranking:** {' > '.join(ppsqm_parts)}")

    md.append("")
    md.append("---")
    md.append(f"*Fields Estate — Phase 1 Descriptive Statistics | {datetime.now().strftime('%Y-%m-%d')}*")

    summary_path = "/home/fields/Fields_Orchestrator/output/positioning_research/phase_1_summary.md"
    with open(summary_path, "w") as f:
        f.write("\n".join(md))
    print(f"\n  Summary written to {summary_path}")
    return "\n".join(md)


# ── Main ────────────────────────────────────────────────────────────────────
def main():
    print("╔═══════════════════════════════════════════════════════════════╗")
    print("║  Phase 1: Descriptive Statistics — Positioning Research       ║")
    print("╚═══════════════════════════════════════════════════════════════╝")

    print("\nLoading all sold records...")
    all_docs = load_all_sold()
    all_docs = load_gc_timeline_dom(all_docs)

    s11 = study_1_1(all_docs)
    s12 = study_1_2(all_docs)
    s13 = study_1_3(all_docs)
    s14 = study_1_4(all_docs)
    s15 = study_1_5(all_docs)
    s16 = study_1_6(all_docs)
    s17 = study_1_7(all_docs)
    s18 = study_1_8(all_docs)
    s19 = study_1_9(all_docs)

    generate_summary(s11, s12, s13, s14, s15, s16, s17, s18, s19)

    print("\n" + "=" * 60)
    print("Phase 1 COMPLETE")
    print("=" * 60)


if __name__ == "__main__":
    main()
