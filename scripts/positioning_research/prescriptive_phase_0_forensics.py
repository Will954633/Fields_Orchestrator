#!/usr/bin/env python3
"""
Prescriptive Phase 0: Outperformer Forensics
=============================================
"What did the winners do differently?"

Studies:
  0.1 - Outperformer forensic analysis (properties that beat Domain valuation)
  0.2 - Fast-seller vs slow-seller controlled comparison
  0.3 - Agency-archetype match analysis
  0.4 - Description pattern mining
  0.5 - Photo count/quality vs outcomes (controlled)
"""

import json, os, re, sys, time
from collections import defaultdict, Counter
from datetime import datetime
import numpy as np
from scipy import stats as scipy_stats

sys.path.insert(0, "/home/fields/Fields_Orchestrator")
from shared.db import get_client

OUTPUT_DIR = "/home/fields/Fields_Orchestrator/output/positioning_research/prescriptive/phase_0"
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
    return {"count": len(values), "mean": round(float(np.mean(a)), 1), "median": round(float(np.median(a)), 1)}

def normalise_address(addr):
    if not addr: return ""
    addr = addr.upper().strip()
    addr = re.sub(r"\s*,\s*", " ", addr)
    addr = re.sub(r"\s+", " ", addr)
    addr = re.sub(r"\bQLD\b", "", addr).strip()
    addr = re.sub(r"\b\d{4}\b$", "", addr).strip()
    return addr

def classify_archetype(d):
    """Classify a property into an archetype."""
    beds = d.get("bedrooms", 0)
    reno = safe_get(d, "property_valuation_data.renovation.overall_renovation_level") or ""
    pool = safe_get(d, "property_valuation_data.outdoor.pool_present") is True
    water = safe_get(d, "property_valuation_data.outdoor.water_views") is True
    area = d.get("_floor_area") or 0
    cond = safe_get(d, "property_valuation_data.condition_summary.overall_score") or 7
    ptype = d.get("property_type", "House")
    lot = d.get("_lot_size") or safe_get(d, "floor_plan_analysis.total_land_area.value") or 0
    if isinstance(lot, dict): lot = lot.get("value", 0) or 0

    if ptype in ("Duplex", "Villa"):
        return "duplex_villa"
    elif reno in ("original", "tired") or (isinstance(cond, (int, float)) and cond <= 6):
        if lot and isinstance(lot, (int, float)) and lot > 700:
            return "original_large_block"
        return "original_standard"
    elif reno == "new_build":
        return "new_build"
    elif water and pool and beds >= 4:
        return "premium_waterfront_entertainer"
    elif pool and beds >= 4 and area > 200:
        return "family_entertainer_with_pool"
    elif reno == "fully_renovated" and beds >= 4:
        return "renovated_family_home"
    elif beds >= 5:
        return "large_family_home"
    elif beds <= 3 and area and area < 150:
        return "compact_starter_downsizer"
    elif safe_get(d, "floor_plan_analysis.levels.total_levels") and safe_get(d, "floor_plan_analysis.levels.total_levels") >= 2:
        return "two_storey_family"
    else:
        return "standard_family_home"

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
            d["_floor_area"] = ifa if isinstance(ifa, (int, float)) and ifa and ifa > 30 else None
            d["_ppsqm"] = (d["_numeric_price"] / d["_floor_area"]) if d["_numeric_price"] and d["_floor_area"] else None
        all_docs.extend(docs)

    gc_lookup = {}
    for suburb in TARGET_SUBURBS:
        time.sleep(4)
        retries = 0
        while retries < 3:
            try:
                for gc in db_gc[suburb].find({}, {"complete_address": 1, "scraped_data.property_timeline": 1, "scraped_data.valuation": 1, "lot_size_sqm": 1}):
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
            d["_domain_val"] = safe_get(gc, "scraped_data.valuation")
            d["_lot_size"] = gc.get("lot_size_sqm")
            for ev in (safe_get(gc, "scraped_data.property_timeline") or []):
                if ev.get("is_sold") and ev.get("days_on_market"):
                    d["_dom"] = int(ev["days_on_market"]); break
        if not d.get("_dom") and d.get("time_on_market_days") and isinstance(d["time_on_market_days"], (int, float)):
            d["_dom"] = int(d["time_on_market_days"])

        # Compute premium vs Domain
        dv_mid = safe_get(d, "_domain_val.mid") if d.get("_domain_val") else None
        d["_domain_premium"] = ((d["_numeric_price"] / dv_mid - 1) * 100) if (d["_numeric_price"] and dv_mid and isinstance(dv_mid, (int, float)) and dv_mid > 0) else None

        # Classify archetype
        d["_archetype"] = classify_archetype(d)

    print(f"  {len(all_docs)} records loaded")
    return all_docs


def profile_group(docs, label=""):
    """Build a comprehensive profile of a group of properties."""
    prices = [d["_numeric_price"] for d in docs if d["_numeric_price"]]
    ppsqm = [d["_ppsqm"] for d in docs if d.get("_ppsqm")]
    doms = [d["_dom"] for d in docs if d.get("_dom") and d["_dom"] > 0]
    premiums = [d["_domain_premium"] for d in docs if d.get("_domain_premium") is not None]
    areas = [d["_floor_area"] for d in docs if d.get("_floor_area")]

    agencies = Counter(d.get("agency_name") for d in docs if d.get("agency_name"))
    months = Counter(int(d.get("sale_date", "2026-06")[5:7]) for d in docs if d.get("sale_date") and len(d["sale_date"]) >= 7)
    reno = Counter(safe_get(d, "property_valuation_data.renovation.overall_renovation_level") for d in docs
                   if safe_get(d, "property_valuation_data.renovation.overall_renovation_level"))
    cond_scores = [safe_get(d, "property_valuation_data.condition_summary.overall_score") for d in docs
                   if safe_get(d, "property_valuation_data.condition_summary.overall_score")]
    pres_scores = [safe_get(d, "property_valuation_data.property_metadata.property_presentation_score") for d in docs
                   if safe_get(d, "property_valuation_data.property_metadata.property_presentation_score")]
    appeal_scores = [safe_get(d, "property_valuation_data.property_metadata.market_appeal_score") for d in docs
                     if safe_get(d, "property_valuation_data.property_metadata.market_appeal_score")]
    pool_pct = round(100 * sum(1 for d in docs if safe_get(d, "property_valuation_data.outdoor.pool_present") is True) / len(docs), 1) if docs else 0
    water_pct = round(100 * sum(1 for d in docs if safe_get(d, "property_valuation_data.outdoor.water_views") is True) / len(docs), 1) if docs else 0

    # Description stats
    desc_lengths = [len(d.get("agents_description", "").split()) for d in docs if d.get("agents_description")]
    img_counts = [len(d.get("property_images", [])) for d in docs if d.get("property_images")]

    # First words in description
    first_words = []
    for d in docs:
        desc = d.get("agents_description", "")
        if desc:
            first_words.append(" ".join(desc.split()[:5]))

    return {
        "count": len(docs),
        "price": calc_stats(prices),
        "ppsqm": calc_stats(ppsqm),
        "dom": calc_stats(doms),
        "domain_premium": calc_stats(premiums),
        "floor_area": calc_stats(areas),
        "pool_pct": pool_pct,
        "water_views_pct": water_pct,
        "avg_condition": round(float(np.mean(cond_scores)), 1) if cond_scores else None,
        "avg_presentation": round(float(np.mean(pres_scores)), 1) if pres_scores else None,
        "avg_appeal": round(float(np.mean(appeal_scores)), 1) if appeal_scores else None,
        "top_agencies": dict(agencies.most_common(5)),
        "top_months": dict(months.most_common(3)),
        "renovation": dict(reno.most_common(3)),
        "avg_desc_words": round(float(np.mean(desc_lengths)), 0) if desc_lengths else None,
        "avg_image_count": round(float(np.mean(img_counts)), 0) if img_counts else None,
        "sample_openings": first_words[:5],
    }


# ── Study 0.1: Outperformer Forensics ────────────────────────────────────
def study_0_1(all_docs):
    print("\n═══ Study 0.1: Outperformer Forensic Analysis ═══")
    results = {}

    # Split into outperformers vs underperformers
    with_premium = [d for d in all_docs if d.get("_domain_premium") is not None]
    outperformers = [d for d in with_premium if d["_domain_premium"] > 0]
    underperformers = [d for d in with_premium if d["_domain_premium"] < -10]
    middle = [d for d in with_premium if -10 <= d["_domain_premium"] <= 0]

    print(f"  With Domain valuation: {len(with_premium)}")
    print(f"  Outperformers (>0%): {len(outperformers)}")
    print(f"  Middle (-10% to 0%): {len(middle)}")
    print(f"  Underperformers (<-10%): {len(underperformers)}")

    # Overall comparison
    results["overall"] = {
        "outperformers": profile_group(outperformers, "outperformers"),
        "middle": profile_group(middle, "middle"),
        "underperformers": profile_group(underperformers, "underperformers"),
    }

    # Per archetype
    archetypes = set(d["_archetype"] for d in with_premium)
    results["by_archetype"] = {}
    for arch in sorted(archetypes):
        arch_out = [d for d in outperformers if d["_archetype"] == arch]
        arch_under = [d for d in underperformers if d["_archetype"] == arch]
        if len(arch_out) >= 3 and len(arch_under) >= 3:
            results["by_archetype"][arch] = {
                "outperformers": profile_group(arch_out),
                "underperformers": profile_group(arch_under),
            }
            out_p = results["by_archetype"][arch]["outperformers"]
            under_p = results["by_archetype"][arch]["underperformers"]
            print(f"\n  {arch}:")
            print(f"    OUT n={out_p['count']}: pres={out_p['avg_presentation']}, cond={out_p['avg_condition']}, pool={out_p['pool_pct']}%, water={out_p['water_views_pct']}%")
            print(f"    UNDER n={under_p['count']}: pres={under_p['avg_presentation']}, cond={under_p['avg_condition']}, pool={under_p['pool_pct']}%, water={under_p['water_views_pct']}%")
            print(f"    OUT agencies: {list(out_p['top_agencies'].keys())[:3]}")
            print(f"    UNDER agencies: {list(under_p['top_agencies'].keys())[:3]}")

    with open(os.path.join(OUTPUT_DIR, "study_0_1_outperformers.json"), "w") as f:
        json.dump(results, f, indent=2, default=str)
    return results


# ── Study 0.2: Fast vs Slow Controlled Comparison ────────────────────────
def study_0_2(all_docs):
    print("\n═══ Study 0.2: Fast-Seller vs Slow-Seller (Price-Controlled) ═══")
    results = {}

    for suburb in CORE_SUBURBS:
        sd = [d for d in all_docs if d["_suburb"] == suburb and d.get("_dom") and d["_dom"] > 0 and d["_numeric_price"]]
        if len(sd) < 20:
            continue

        # Split into price quartiles first (to control for price)
        prices = sorted([d["_numeric_price"] for d in sd])
        p50 = np.median(prices)

        suburb_results = {}
        for price_tier, tier_docs in [
            ("below_median", [d for d in sd if d["_numeric_price"] < p50]),
            ("above_median", [d for d in sd if d["_numeric_price"] >= p50]),
        ]:
            if len(tier_docs) < 10:
                continue
            doms = sorted([d["_dom"] for d in tier_docs])
            q25_dom = np.percentile(doms, 25)
            q75_dom = np.percentile(doms, 75)

            fast = [d for d in tier_docs if d["_dom"] <= q25_dom]
            slow = [d for d in tier_docs if d["_dom"] >= q75_dom]

            if len(fast) >= 3 and len(slow) >= 3:
                suburb_results[price_tier] = {
                    "fast_sellers": profile_group(fast),
                    "slow_sellers": profile_group(slow),
                    "fast_dom_threshold": round(float(q25_dom)),
                    "slow_dom_threshold": round(float(q75_dom)),
                }

                fp = suburb_results[price_tier]["fast_sellers"]
                sp = suburb_results[price_tier]["slow_sellers"]
                print(f"\n  {suburb} ({price_tier}):")
                print(f"    FAST (≤{q25_dom:.0f}d) n={fp['count']}: pres={fp['avg_presentation']}, cond={fp['avg_condition']}, desc={fp['avg_desc_words']}w, imgs={fp['avg_image_count']}")
                print(f"    SLOW (≥{q75_dom:.0f}d) n={sp['count']}: pres={sp['avg_presentation']}, cond={sp['avg_condition']}, desc={sp['avg_desc_words']}w, imgs={sp['avg_image_count']}")
                print(f"    FAST agencies: {list(fp['top_agencies'].keys())[:3]}")
                print(f"    SLOW agencies: {list(sp['top_agencies'].keys())[:3]}")
                print(f"    FAST months: {fp['top_months']}")
                print(f"    SLOW months: {sp['top_months']}")

        results[suburb] = suburb_results

    with open(os.path.join(OUTPUT_DIR, "study_0_2_fast_vs_slow.json"), "w") as f:
        json.dump(results, f, indent=2, default=str)
    return results


# ── Study 0.3: Agency-Archetype Match ────────────────────────────────────
def study_0_3(all_docs):
    print("\n═══ Study 0.3: Agency-Archetype Match ═══")
    results = {}

    for suburb in CORE_SUBURBS:
        sd = [d for d in all_docs if d["_suburb"] == suburb and d["_numeric_price"]]

        # Compute cohort medians for premium calculation
        cohort_medians = {}
        for d in sd:
            beds = d.get("bedrooms")
            if beds:
                cohort_medians.setdefault(beds, []).append(d["_numeric_price"])
        for k in cohort_medians:
            cohort_medians[k] = np.median(cohort_medians[k])

        # Agency × archetype matrix
        matrix = defaultdict(lambda: defaultdict(lambda: {"prices": [], "doms": [], "premiums": []}))
        for d in sd:
            ag = d.get("agency_name")
            if not ag:
                continue
            arch = d["_archetype"]
            matrix[ag][arch]["prices"].append(d["_numeric_price"])
            if d.get("_dom") and d["_dom"] > 0:
                matrix[ag][arch]["doms"].append(d["_dom"])
            beds = d.get("bedrooms")
            if beds and beds in cohort_medians and cohort_medians[beds] > 0:
                prem = (d["_numeric_price"] / cohort_medians[beds] - 1) * 100
                matrix[ag][arch]["premiums"].append(prem)

        # Find best agency per archetype
        best_per_arch = {}
        for arch in set(d["_archetype"] for d in sd):
            arch_agencies = []
            for ag, archs in matrix.items():
                if arch in archs and len(archs[arch]["prices"]) >= 3:
                    data = archs[arch]
                    med_prem = round(float(np.median(data["premiums"])), 1) if data["premiums"] else None
                    med_dom = round(float(np.median(data["doms"])), 1) if data["doms"] else None
                    arch_agencies.append({
                        "agency": ag,
                        "sales": len(data["prices"]),
                        "median_premium": med_prem,
                        "median_dom": med_dom,
                    })
            arch_agencies.sort(key=lambda x: -(x["median_premium"] or -999))
            best_per_arch[arch] = arch_agencies[:5]

        results[suburb] = best_per_arch

        print(f"\n  {suburb.upper()}:")
        for arch, agencies in sorted(best_per_arch.items()):
            if agencies:
                best = agencies[0]
                dom_str = f", {best['median_dom']:.0f}d" if best['median_dom'] else ""
                prem_str = f"+{best['median_premium']:.1f}%" if best['median_premium'] is not None else "N/A"
                print(f"    {arch:35s} → {best['agency']} ({best['sales']} sales, {prem_str}{dom_str})")

    with open(os.path.join(OUTPUT_DIR, "study_0_3_agency_archetype.json"), "w") as f:
        json.dump(results, f, indent=2, default=str)
    return results


# ── Study 0.4: Description Pattern Mining ────────────────────────────────
def study_0_4(all_docs):
    print("\n═══ Study 0.4: Description Pattern Mining ═══")
    results = {}

    for suburb in CORE_SUBURBS:
        sd = [d for d in all_docs if d["_suburb"] == suburb and d.get("agents_description") and d["_numeric_price"]]

        # What do descriptions OPEN with?
        opening_patterns = {
            "lifestyle_opening": r"^(welcome|discover|experience|imagine|embrace|escape|enjoy)",
            "feature_opening": r"^(this|a |an |the |featuring|offering|boasting|presenting)",
            "location_opening": r"^(located|situated|set |nestled|positioned|tucked)",
            "urgency_opening": r"^(don.t miss|rare|unique|once|first time|brand new|just|now)",
            "address_opening": r"^\d+\s",
        }

        pattern_outcomes = defaultdict(lambda: {"prices": [], "doms": [], "premiums": [], "count": 0})
        for d in sd:
            desc = d["agents_description"].strip()
            for pattern_name, regex in opening_patterns.items():
                if re.match(regex, desc, re.IGNORECASE):
                    pattern_outcomes[pattern_name]["count"] += 1
                    pattern_outcomes[pattern_name]["prices"].append(d["_numeric_price"])
                    if d.get("_dom") and d["_dom"] > 0:
                        pattern_outcomes[pattern_name]["doms"].append(d["_dom"])
                    if d.get("_domain_premium") is not None:
                        pattern_outcomes[pattern_name]["premiums"].append(d["_domain_premium"])
                    break

        # Feature mention order (what gets mentioned in first 20 words)
        first_features = Counter()
        feature_keywords = ["bedroom", "bathroom", "pool", "kitchen", "garage", "garden",
                           "family", "entertain", "living", "outdoor", "water", "view",
                           "renovated", "modern", "spacious", "private", "quiet"]
        for d in sd:
            desc = d.get("agents_description", "").lower()
            first_20 = " ".join(desc.split()[:20])
            for kw in feature_keywords:
                if kw in first_20:
                    first_features[kw] += 1

        # Tone classification
        tones = defaultdict(lambda: {"prices": [], "doms": [], "count": 0})
        luxury_words = {"luxury", "luxurious", "premium", "prestige", "exclusive", "bespoke", "exquisite"}
        urgency_words = {"rare", "don't miss", "once in", "must see", "act now", "won't last"}
        factual_markers = {"sqm", "m2", "bedroom", "bathroom", "car", "land"}

        for d in sd:
            desc_lower = d.get("agents_description", "").lower()
            words = set(desc_lower.split())

            if words & luxury_words:
                tone = "luxury_aspirational"
            elif any(uw in desc_lower for uw in urgency_words):
                tone = "urgency"
            elif len(words & factual_markers) >= 2:
                tone = "factual_specs"
            else:
                tone = "lifestyle_narrative"

            tones[tone]["count"] += 1
            tones[tone]["prices"].append(d["_numeric_price"])
            if d.get("_dom") and d["_dom"] > 0:
                tones[tone]["doms"].append(d["_dom"])

        results[suburb] = {
            "opening_patterns": {
                k: {"count": v["count"], "pct": round(100 * v["count"] / len(sd), 1),
                    "median_price": int(np.median(v["prices"])) if v["prices"] else None,
                    "median_dom": round(float(np.median(v["doms"])), 1) if v["doms"] else None,
                    "median_premium": round(float(np.median(v["premiums"])), 1) if v["premiums"] else None}
                for k, v in pattern_outcomes.items() if v["count"] >= 3
            },
            "first_20_word_features": dict(first_features.most_common(15)),
            "tone_analysis": {
                k: {"count": v["count"], "pct": round(100 * v["count"] / len(sd), 1),
                    "median_price": int(np.median(v["prices"])) if v["prices"] else None,
                    "median_dom": round(float(np.median(v["doms"])), 1) if v["doms"] else None}
                for k, v in tones.items() if v["count"] >= 3
            },
        }

        print(f"\n  {suburb.upper()}:")
        print(f"    Opening patterns:")
        for p, data in sorted(results[suburb]["opening_patterns"].items(), key=lambda x: -x[1]["count"]):
            prem_str = f", premium={data['median_premium']:+.1f}%" if data['median_premium'] is not None else ""
            print(f"      {p:25s} {data['count']:3d} ({data['pct']:4.1f}%) dom={data['median_dom'] or '-'}d{prem_str}")
        print(f"    First-mentioned features: {dict(list(results[suburb]['first_20_word_features'].items())[:5])}")
        print(f"    Tone analysis:")
        for t, data in sorted(results[suburb]["tone_analysis"].items(), key=lambda x: -x[1]["count"]):
            print(f"      {t:25s} {data['count']:3d} ({data['pct']:4.1f}%) ${data['median_price']:,} dom={data['median_dom'] or '-'}d")

    with open(os.path.join(OUTPUT_DIR, "study_0_4_descriptions.json"), "w") as f:
        json.dump(results, f, indent=2)
    return results


# ── Study 0.5: Photo Count/Quality vs Outcomes ──────────────────────────
def study_0_5(all_docs):
    print("\n═══ Study 0.5: Photo Count and Quality vs Outcomes ═══")
    results = {}

    for suburb in CORE_SUBURBS:
        sd = [d for d in all_docs if d["_suburb"] == suburb and d["_numeric_price"]]

        # Photo count buckets
        photo_buckets = defaultdict(lambda: {"prices": [], "doms": [], "premiums": []})
        for d in sd:
            imgs = d.get("property_images", [])
            if not imgs:
                continue
            count = len(imgs)
            if count < 20:
                bucket = "under_20"
            elif count < 40:
                bucket = "20_to_40"
            elif count < 60:
                bucket = "40_to_60"
            elif count < 80:
                bucket = "60_to_80"
            else:
                bucket = "80_plus"

            photo_buckets[bucket]["prices"].append(d["_numeric_price"])
            if d.get("_dom") and d["_dom"] > 0:
                photo_buckets[bucket]["doms"].append(d["_dom"])
            if d.get("_domain_premium") is not None:
                photo_buckets[bucket]["premiums"].append(d["_domain_premium"])

        # Presentation score vs outcomes (binned to reduce ceiling effect)
        pres_buckets = {"low_7_or_below": [], "medium_8": [], "high_9_plus": []}
        for d in sd:
            ps = safe_get(d, "property_valuation_data.property_metadata.property_presentation_score")
            if ps and isinstance(ps, (int, float)):
                if ps <= 7:
                    pres_buckets["low_7_or_below"].append(d)
                elif ps <= 8:
                    pres_buckets["medium_8"].append(d)
                else:
                    pres_buckets["high_9_plus"].append(d)

        # Floor plan availability vs outcomes
        has_fp = [d for d in sd if d.get("floor_plans") and len(d["floor_plans"]) > 0]
        no_fp = [d for d in sd if not d.get("floor_plans") or len(d.get("floor_plans", [])) == 0]

        results[suburb] = {
            "photo_count_buckets": {
                k: {"count": len(v["prices"]),
                    "median_price": int(np.median(v["prices"])) if v["prices"] else None,
                    "median_dom": round(float(np.median(v["doms"])), 1) if v["doms"] else None,
                    "median_premium": round(float(np.median(v["premiums"])), 1) if v["premiums"] else None}
                for k, v in photo_buckets.items()
            },
            "presentation_score_impact": {
                k: profile_group(v) for k, v in pres_buckets.items() if len(v) >= 5
            },
            "floor_plan_impact": {
                "with_floor_plan": {"count": len(has_fp), "median_price": int(np.median([d["_numeric_price"] for d in has_fp if d["_numeric_price"]])) if has_fp else None},
                "without_floor_plan": {"count": len(no_fp), "median_price": int(np.median([d["_numeric_price"] for d in no_fp if d["_numeric_price"]])) if no_fp else None},
            },
        }

        print(f"\n  {suburb.upper()}:")
        print(f"    Photo count vs outcomes:")
        for bucket in ["under_20", "20_to_40", "40_to_60", "60_to_80", "80_plus"]:
            data = results[suburb]["photo_count_buckets"].get(bucket, {})
            if data.get("count"):
                prem_str = f", premium={data['median_premium']:+.1f}%" if data.get("median_premium") is not None else ""
                print(f"      {bucket:12s} n={data['count']:3d}  dom={data.get('median_dom', '-') or '-'}d{prem_str}")

        print(f"    Presentation score impact:")
        for level, data in results[suburb]["presentation_score_impact"].items():
            dom_str = f"dom={data['dom']['median']:.0f}d" if data.get("dom") else "dom=N/A"
            print(f"      {level:20s} n={data['count']:3d}  {dom_str}  pres={data['avg_presentation']}")

    with open(os.path.join(OUTPUT_DIR, "study_0_5_photos.json"), "w") as f:
        json.dump(results, f, indent=2, default=str)
    return results


# ── Summary ────────────────────────────────────────────────────────────────
def generate_summary(s01, s02, s03, s04, s05):
    md = []
    md.append("# Prescriptive Phase 0: Outperformer Forensics")
    md.append(f"## \"What Did The Winners Do Differently?\"")
    md.append(f"### Generated {datetime.now().strftime('%Y-%m-%d %H:%M AEST')}")

    # 0.1
    md.append("\n---\n## 0.1 Outperformer vs Underperformer Profile")
    overall = s01.get("overall", {})
    for group_name in ["outperformers", "middle", "underperformers"]:
        g = overall.get(group_name, {})
        if g:
            md.append(f"\n**{group_name.title()}** (n={g['count']}):")
            md.append(f"- Avg condition: {g.get('avg_condition', '-')}/10, Avg presentation: {g.get('avg_presentation', '-')}/10")
            md.append(f"- Pool: {g.get('pool_pct', 0)}%, Water views: {g.get('water_views_pct', 0)}%")
            md.append(f"- Avg desc length: {g.get('avg_desc_words', '-')} words, Avg images: {g.get('avg_image_count', '-')}")
            md.append(f"- Top agencies: {list(g.get('top_agencies', {}).keys())[:3]}")
            md.append(f"- Top months: {g.get('top_months', {})}")
            md.append(f"- Renovation: {g.get('renovation', {})}")

    md.append("\n### By Archetype")
    for arch, data in s01.get("by_archetype", {}).items():
        out = data.get("outperformers", {})
        under = data.get("underperformers", {})
        md.append(f"\n**{arch}:**")
        md.append(f"| Metric | Outperformers (n={out.get('count',0)}) | Underperformers (n={under.get('count',0)}) |")
        md.append(f"|--------|---------------|-----------------|")
        md.append(f"| Condition | {out.get('avg_condition','-')}/10 | {under.get('avg_condition','-')}/10 |")
        md.append(f"| Presentation | {out.get('avg_presentation','-')}/10 | {under.get('avg_presentation','-')}/10 |")
        md.append(f"| Pool | {out.get('pool_pct',0)}% | {under.get('pool_pct',0)}% |")
        md.append(f"| Water views | {out.get('water_views_pct',0)}% | {under.get('water_views_pct',0)}% |")
        md.append(f"| Top agencies | {list(out.get('top_agencies',{}).keys())[:2]} | {list(under.get('top_agencies',{}).keys())[:2]} |")

    # 0.2
    md.append("\n---\n## 0.2 Fast-Seller vs Slow-Seller (Price-Controlled)")
    for suburb in CORE_SUBURBS:
        sr = s02.get(suburb, {})
        for tier, data in sr.items():
            fp = data.get("fast_sellers", {})
            sp = data.get("slow_sellers", {})
            md.append(f"\n**{suburb.replace('_',' ').title()} ({tier})** — Fast ≤{data.get('fast_dom_threshold','-')}d vs Slow ≥{data.get('slow_dom_threshold','-')}d")
            md.append(f"| Metric | Fast (n={fp.get('count',0)}) | Slow (n={sp.get('count',0)}) |")
            md.append(f"|--------|------|------|")
            md.append(f"| Condition | {fp.get('avg_condition','-')}/10 | {sp.get('avg_condition','-')}/10 |")
            md.append(f"| Presentation | {fp.get('avg_presentation','-')}/10 | {sp.get('avg_presentation','-')}/10 |")
            md.append(f"| Desc words | {fp.get('avg_desc_words','-')} | {sp.get('avg_desc_words','-')} |")
            md.append(f"| Images | {fp.get('avg_image_count','-')} | {sp.get('avg_image_count','-')} |")
            md.append(f"| Top agencies | {list(fp.get('top_agencies',{}).keys())[:3]} | {list(sp.get('top_agencies',{}).keys())[:3]} |")
            md.append(f"| Top months | {fp.get('top_months',{})} | {sp.get('top_months',{})} |")

    # 0.3
    md.append("\n---\n## 0.3 Best Agency by Property Archetype")
    for suburb in CORE_SUBURBS:
        md.append(f"\n### {suburb.replace('_',' ').title()}")
        md.append("| Archetype | Best Agency | Sales | Premium |")
        md.append("|-----------|-----------|-------|---------|")
        for arch, agencies in sorted(s03.get(suburb, {}).items()):
            if agencies:
                a = agencies[0]
                prem = f"+{a['median_premium']:.1f}%" if a.get("median_premium") is not None else "-"
                md.append(f"| {arch} | {a['agency']} | {a['sales']} | {prem} |")

    # 0.4
    md.append("\n---\n## 0.4 Description Patterns")
    for suburb in CORE_SUBURBS:
        r = s04.get(suburb, {})
        md.append(f"\n### {suburb.replace('_',' ').title()}")
        md.append("\n**Opening patterns:**")
        md.append("| Pattern | Count | Median DOM | Domain Premium |")
        md.append("|---------|-------|-----------|---------------|")
        for p, data in sorted(r.get("opening_patterns", {}).items(), key=lambda x: -x[1]["count"]):
            dom = f"{data['median_dom']}d" if data.get("median_dom") else "-"
            prem = f"{data['median_premium']:+.1f}%" if data.get("median_premium") is not None else "-"
            md.append(f"| {p} | {data['count']} ({data['pct']}%) | {dom} | {prem} |")

        md.append(f"\n**Tone analysis:**")
        md.append("| Tone | Count | Median Price | Median DOM |")
        md.append("|------|-------|-------------|-----------|")
        for t, data in sorted(r.get("tone_analysis", {}).items(), key=lambda x: -x[1]["count"]):
            dom = f"{data['median_dom']}d" if data.get("median_dom") else "-"
            price = f"${data['median_price']:,}" if data['median_price'] else "-"
            md.append(f"| {t} | {data['count']} ({data['pct']}%) | {price} | {dom} |")

    # 0.5
    md.append("\n---\n## 0.5 Photo Count and Quality")
    for suburb in CORE_SUBURBS:
        r = s05.get(suburb, {})
        md.append(f"\n### {suburb.replace('_',' ').title()}")
        md.append("| Photo Count | Count | Median DOM | Domain Premium |")
        md.append("|------------|-------|-----------|---------------|")
        for bucket in ["under_20", "20_to_40", "40_to_60", "60_to_80", "80_plus"]:
            data = r.get("photo_count_buckets", {}).get(bucket, {})
            if data.get("count"):
                dom = f"{data['median_dom']}d" if data.get("median_dom") else "-"
                prem = f"{data['median_premium']:+.1f}%" if data.get("median_premium") is not None else "-"
                md.append(f"| {bucket} | {data['count']} | {dom} | {prem} |")

    md.append(f"\n---\n*Fields Estate — Prescriptive Phase 0 | {datetime.now().strftime('%Y-%m-%d')}*")

    path = "/home/fields/Fields_Orchestrator/output/positioning_research/prescriptive/phase_0_summary.md"
    with open(path, "w") as f:
        f.write("\n".join(md))
    print(f"\n  Summary: {path}")


def main():
    print("╔═══════════════════════════════════════════════════════════════╗")
    print("║  Prescriptive Phase 0: Outperformer Forensics                ║")
    print("╚═══════════════════════════════════════════════════════════════╝")
    all_docs = load_all_data()
    s01 = study_0_1(all_docs)
    s02 = study_0_2(all_docs)
    s03 = study_0_3(all_docs)
    s04 = study_0_4(all_docs)
    s05 = study_0_5(all_docs)
    generate_summary(s01, s02, s03, s04, s05)
    print("\n" + "=" * 60)
    print("Prescriptive Phase 0 COMPLETE")
    print("=" * 60)

if __name__ == "__main__":
    main()
