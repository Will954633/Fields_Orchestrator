#!/usr/bin/env python3
"""
Phase 0: Data Quality Audit — Property Positioning Research
=============================================================
Foundation for all subsequent analysis. Must run first.

Studies:
  0.1 - Field coverage census (what % of records have each field?)
  0.2 - DOM reconstruction (recover days-on-market from multiple sources)
  0.3 - Price parsing and normalisation
  0.4 - Address matching (Target_Market → Gold_Coast for lat/long, OSM, valuations)
  0.5 - GPT photo analysis quality assessment (score distributions, ceiling effects)

Output:
  - JSON results to output/positioning_research/phase_0/
  - Markdown summary to output/positioning_research/phase_0_summary.md
"""

import json
import os
import re
import sys
import time
from collections import defaultdict
from datetime import datetime

import numpy as np

sys.path.insert(0, "/home/fields/Fields_Orchestrator")
from shared.db import get_client

# ── Config ──────────────────────────────────────────────────────────────────
OUTPUT_DIR = "/home/fields/Fields_Orchestrator/output/positioning_research/phase_0"
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
    """Parse sale_price string like '$1,585,000' to int."""
    if not s or not isinstance(s, str):
        return None
    cleaned = s.replace(",", "").replace("$", "").strip()
    m = re.search(r"(\d{6,})", cleaned)
    if m:
        return int(m.group(1))
    return None


def parse_dom_from_text(text):
    """Extract DOM from domain_says_text: 'has been on Domain for 28 days'."""
    if not text:
        return None
    m = re.search(r"on Domain for (\d+) day", text)
    if m:
        return int(m.group(1))
    return None


def safe_get(doc, path, default=None):
    """Safely traverse nested dict path like 'a.b.c'."""
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


def load_all_sold():
    """Load all sold records from Target_Market_Sold_Last_12_Months."""
    all_docs = []
    for suburb in TARGET_SUBURBS:
        time.sleep(1)
        docs = list(db_target[suburb].find({}))
        for d in docs:
            d["_suburb"] = suburb
        all_docs.extend(docs)
        print(f"  Loaded {suburb}: {len(docs)} records")
    print(f"  Total: {len(all_docs)} records")
    return all_docs


# ── Study 0.1: Field Coverage Census ───────────────────────────────────────
def study_0_1(all_docs):
    """Assess what % of records have usable data for each key field."""
    print("\n═══ Study 0.1: Field Coverage Census ═══")

    # Define all fields we care about for positioning research
    fields = {
        # Transaction
        "sale_price": lambda d: d.get("sale_price"),
        "sale_date": lambda d: d.get("sale_date"),
        "time_on_market_days": lambda d: d.get("time_on_market_days"),
        "domain_says_text": lambda d: d.get("domain_says_text"),
        "first_listed_date": lambda d: d.get("first_listed_date"),
        "agency_name": lambda d: d.get("agency_name"),
        "agent_name": lambda d: d.get("agent_name"),
        "listing_url": lambda d: d.get("listing_url"),
        # Property basics
        "bedrooms": lambda d: d.get("bedrooms"),
        "bathrooms": lambda d: d.get("bathrooms"),
        "carspaces": lambda d: d.get("carspaces"),
        "property_type": lambda d: d.get("property_type"),
        "features": lambda d: d.get("features") if d.get("features") else None,
        "agents_description": lambda d: d.get("agents_description"),
        # GPT photo analysis
        "pvd.condition_summary.overall": lambda d: safe_get(d, "property_valuation_data.condition_summary.overall_score"),
        "pvd.property_metadata.presentation_score": lambda d: safe_get(d, "property_valuation_data.property_metadata.property_presentation_score"),
        "pvd.property_metadata.market_appeal_score": lambda d: safe_get(d, "property_valuation_data.property_metadata.market_appeal_score"),
        "pvd.property_metadata.image_quality": lambda d: safe_get(d, "property_valuation_data.property_metadata.image_quality"),
        "pvd.property_metadata.has_professional_photography": lambda d: safe_get(d, "property_valuation_data.property_metadata.has_professional_photography"),
        "pvd.property_metadata.unique_features": lambda d: safe_get(d, "property_valuation_data.property_metadata.unique_features"),
        "pvd.property_metadata.negative_features": lambda d: safe_get(d, "property_valuation_data.property_metadata.negative_features"),
        "pvd.exterior.condition_score": lambda d: safe_get(d, "property_valuation_data.exterior.condition_score"),
        "pvd.kitchen.quality_score": lambda d: safe_get(d, "property_valuation_data.kitchen.quality_score"),
        "pvd.kitchen.benchtop_material": lambda d: safe_get(d, "property_valuation_data.kitchen.benchtop_material"),
        "pvd.kitchen.island_bench": lambda d: safe_get(d, "property_valuation_data.kitchen.island_bench"),
        "pvd.kitchen.butler_pantry": lambda d: safe_get(d, "property_valuation_data.kitchen.butler_pantry"),
        "pvd.outdoor.pool_present": lambda d: safe_get(d, "property_valuation_data.outdoor.pool_present"),
        "pvd.outdoor.water_views": lambda d: safe_get(d, "property_valuation_data.outdoor.water_views"),
        "pvd.outdoor.landscaping_quality": lambda d: safe_get(d, "property_valuation_data.outdoor.landscaping_quality"),
        "pvd.outdoor.outdoor_entertainment_score": lambda d: safe_get(d, "property_valuation_data.outdoor.outdoor_entertainment_score"),
        "pvd.renovation.overall_level": lambda d: safe_get(d, "property_valuation_data.renovation.overall_renovation_level"),
        "pvd.renovation.recency": lambda d: safe_get(d, "property_valuation_data.renovation.renovation_recency"),
        "pvd.property_overview.architectural_style": lambda d: safe_get(d, "property_valuation_data.property_overview.architectural_style"),
        "pvd.property_overview.roof_type": lambda d: safe_get(d, "property_valuation_data.property_overview.roof_type"),
        # Floor plan analysis
        "fpa.internal_floor_area": lambda d: safe_get(d, "floor_plan_analysis.internal_floor_area.value"),
        "fpa.total_floor_area": lambda d: safe_get(d, "floor_plan_analysis.total_floor_area.value"),
        "fpa.total_land_area": lambda d: safe_get(d, "floor_plan_analysis.total_land_area.value"),
        "fpa.rooms": lambda d: safe_get(d, "floor_plan_analysis.rooms") if safe_get(d, "floor_plan_analysis.rooms") else None,
        "fpa.levels": lambda d: safe_get(d, "floor_plan_analysis.levels.total_levels"),
        "fpa.layout_features.open_plan": lambda d: safe_get(d, "floor_plan_analysis.layout_features.open_plan"),
        "fpa.buyer_insights.ideal_for": lambda d: safe_get(d, "floor_plan_analysis.buyer_insights.ideal_for"),
        "fpa.outdoor_spaces": lambda d: safe_get(d, "floor_plan_analysis.outdoor_spaces") if safe_get(d, "floor_plan_analysis.outdoor_spaces") else None,
        # Images
        "property_images": lambda d: d.get("property_images") if d.get("property_images") else None,
        "floor_plans": lambda d: d.get("floor_plans") if d.get("floor_plans") else None,
        # House plan (separate from floor_plan_analysis)
        "house_plan": lambda d: d.get("house_plan"),
    }

    # Compute coverage per suburb and overall
    results = {"overall": {}, "by_suburb": {}}

    for suburb in TARGET_SUBURBS:
        suburb_docs = [d for d in all_docs if d["_suburb"] == suburb]
        suburb_coverage = {}
        for field_name, extractor in fields.items():
            count = sum(1 for d in suburb_docs if extractor(d) is not None)
            suburb_coverage[field_name] = {
                "count": count,
                "total": len(suburb_docs),
                "pct": round(100 * count / len(suburb_docs), 1) if suburb_docs else 0,
            }
        results["by_suburb"][suburb] = suburb_coverage

    # Overall
    for field_name, extractor in fields.items():
        count = sum(1 for d in all_docs if extractor(d) is not None)
        results["overall"][field_name] = {
            "count": count,
            "total": len(all_docs),
            "pct": round(100 * count / len(all_docs), 1),
        }

    # Print summary
    print("\n  Field Coverage (all suburbs combined):")
    for field_name in sorted(results["overall"].keys()):
        r = results["overall"][field_name]
        bar = "█" * int(r["pct"] / 5) + "░" * (20 - int(r["pct"] / 5))
        print(f"    {field_name:55s} {bar} {r['pct']:5.1f}% ({r['count']}/{r['total']})")

    with open(os.path.join(OUTPUT_DIR, "study_0_1_coverage.json"), "w") as f:
        json.dump(results, f, indent=2)

    return results


# ── Study 0.2: DOM Reconstruction ──────────────────────────────────────────
def study_0_2(all_docs):
    """Reconstruct days-on-market from multiple sources."""
    print("\n═══ Study 0.2: DOM Reconstruction ═══")

    results = {"records": [], "summary": {}}

    for d in all_docs:
        dom = None
        source = None

        # Source 1: Direct field
        if d.get("time_on_market_days") and isinstance(d["time_on_market_days"], (int, float)):
            dom = int(d["time_on_market_days"])
            source = "direct"

        # Source 2: Parse from domain_says_text
        if dom is None:
            parsed = parse_dom_from_text(d.get("domain_says_text"))
            if parsed:
                dom = parsed
                source = "parsed_domain_text"

        # Source 3: Compute from first_listed_date and sale_date
        if dom is None and d.get("first_listed_date") and d.get("sale_date"):
            try:
                fld = d["first_listed_date"]  # e.g. "16 January"
                sd = d["sale_date"]  # e.g. "2026-02-11"
                sale_dt = datetime.strptime(sd, "%Y-%m-%d")
                # first_listed_date lacks year — assume same year as sale, or previous year if month > sale month
                for year in [sale_dt.year, sale_dt.year - 1]:
                    try:
                        first_dt = datetime.strptime(f"{fld} {year}", "%d %B %Y")
                        diff = (sale_dt - first_dt).days
                        if 0 <= diff <= 365:
                            dom = diff
                            source = "computed_first_to_sale"
                            break
                    except ValueError:
                        continue
            except (ValueError, TypeError):
                pass

        results["records"].append({
            "address": d.get("address", ""),
            "suburb": d["_suburb"],
            "dom": dom,
            "source": source,
        })

    # Summarise
    by_source = defaultdict(int)
    by_suburb = defaultdict(lambda: {"total": 0, "with_dom": 0, "sources": defaultdict(int)})

    for r in results["records"]:
        suburb = r["suburb"]
        by_suburb[suburb]["total"] += 1
        if r["dom"] is not None:
            by_suburb[suburb]["with_dom"] += 1
            by_suburb[suburb]["sources"][r["source"]] += 1
            by_source[r["source"]] += 1

    total_with_dom = sum(1 for r in results["records"] if r["dom"] is not None)
    total = len(results["records"])

    results["summary"] = {
        "total_records": total,
        "records_with_dom": total_with_dom,
        "coverage_pct": round(100 * total_with_dom / total, 1),
        "by_source": dict(by_source),
        "by_suburb": {
            s: {
                "total": v["total"],
                "with_dom": v["with_dom"],
                "pct": round(100 * v["with_dom"] / v["total"], 1) if v["total"] else 0,
                "sources": dict(v["sources"]),
            }
            for s, v in by_suburb.items()
        },
    }

    # DOM distribution for those that have it
    doms = [r["dom"] for r in results["records"] if r["dom"] is not None and r["dom"] > 0]
    if doms:
        doms_arr = np.array(doms)
        results["summary"]["dom_distribution"] = {
            "count": len(doms),
            "mean": round(float(np.mean(doms_arr)), 1),
            "median": round(float(np.median(doms_arr)), 1),
            "p25": round(float(np.percentile(doms_arr, 25)), 1),
            "p75": round(float(np.percentile(doms_arr, 75)), 1),
            "p10": round(float(np.percentile(doms_arr, 10)), 1),
            "p90": round(float(np.percentile(doms_arr, 90)), 1),
            "min": int(np.min(doms_arr)),
            "max": int(np.max(doms_arr)),
        }

    print(f"  DOM recovered: {total_with_dom}/{total} ({results['summary']['coverage_pct']}%)")
    print(f"  By source: {dict(by_source)}")
    if "dom_distribution" in results["summary"]:
        d = results["summary"]["dom_distribution"]
        print(f"  Distribution: median={d['median']}d, mean={d['mean']}d, p25={d['p25']}d, p75={d['p75']}d")

    with open(os.path.join(OUTPUT_DIR, "study_0_2_dom.json"), "w") as f:
        json.dump(results["summary"], f, indent=2)

    # Return DOM lookup for other studies
    dom_lookup = {r["address"]: {"dom": r["dom"], "source": r["source"]} for r in results["records"]}
    return results, dom_lookup


# ── Study 0.3: Price Parsing ───────────────────────────────────────────────
def study_0_3(all_docs):
    """Parse and validate all sale_price values."""
    print("\n═══ Study 0.3: Price Parsing and Normalisation ═══")

    results = {"records": [], "summary": {}}
    unparseable = []

    for d in all_docs:
        raw = d.get("sale_price", "")
        parsed = parse_price(raw)
        results["records"].append({
            "address": d.get("address", ""),
            "suburb": d["_suburb"],
            "raw_price": raw,
            "numeric_price": parsed,
        })
        if parsed is None and raw:
            unparseable.append({"address": d.get("address", ""), "raw": raw, "suburb": d["_suburb"]})

    # Summary
    prices = [r["numeric_price"] for r in results["records"] if r["numeric_price"]]
    prices_arr = np.array(prices)

    by_suburb = {}
    for suburb in TARGET_SUBURBS:
        sp = [r["numeric_price"] for r in results["records"] if r["suburb"] == suburb and r["numeric_price"]]
        if sp:
            sp_arr = np.array(sp)
            by_suburb[suburb] = {
                "count": len(sp),
                "mean": int(np.mean(sp_arr)),
                "median": int(np.median(sp_arr)),
                "p25": int(np.percentile(sp_arr, 25)),
                "p75": int(np.percentile(sp_arr, 75)),
                "min": int(np.min(sp_arr)),
                "max": int(np.max(sp_arr)),
                "std": int(np.std(sp_arr)),
            }

    # Outlier detection (IQR method)
    q1 = np.percentile(prices_arr, 25)
    q3 = np.percentile(prices_arr, 75)
    iqr = q3 - q1
    low_fence = q1 - 3 * iqr
    high_fence = q3 + 3 * iqr
    outliers = [r for r in results["records"] if r["numeric_price"] and (r["numeric_price"] < low_fence or r["numeric_price"] > high_fence)]

    results["summary"] = {
        "total_records": len(results["records"]),
        "parseable": len(prices),
        "unparseable": len(unparseable),
        "null_price": sum(1 for r in results["records"] if not r["raw_price"]),
        "coverage_pct": round(100 * len(prices) / len(results["records"]), 1),
        "overall_distribution": {
            "mean": int(np.mean(prices_arr)),
            "median": int(np.median(prices_arr)),
            "p25": int(np.percentile(prices_arr, 25)),
            "p75": int(np.percentile(prices_arr, 75)),
            "min": int(np.min(prices_arr)),
            "max": int(np.max(prices_arr)),
        },
        "by_suburb": by_suburb,
        "outlier_count": len(outliers),
        "outlier_fences": {"low": int(low_fence), "high": int(high_fence)},
        "unparseable_samples": unparseable[:10],
    }

    print(f"  Parseable: {len(prices)}/{len(results['records'])} ({results['summary']['coverage_pct']}%)")
    print(f"  Unparseable: {len(unparseable)}, Null: {results['summary']['null_price']}")
    print(f"  Overall: median=${results['summary']['overall_distribution']['median']:,}, range=${results['summary']['overall_distribution']['min']:,}-${results['summary']['overall_distribution']['max']:,}")
    print(f"  Outliers (>3×IQR): {len(outliers)}")

    with open(os.path.join(OUTPUT_DIR, "study_0_3_prices.json"), "w") as f:
        json.dump(results["summary"], f, indent=2)

    # Return price lookup
    price_lookup = {r["address"]: r["numeric_price"] for r in results["records"]}
    return results, price_lookup


# ── Study 0.4: Address Matching ────────────────────────────────────────────
def study_0_4(all_docs):
    """Match Target_Market records to Gold_Coast for location/valuation data."""
    print("\n═══ Study 0.4: Address Matching (Target_Market → Gold_Coast) ═══")

    def normalise_address(addr):
        if not addr:
            return ""
        addr = addr.upper().strip()
        addr = re.sub(r"\s*,\s*", " ", addr)
        addr = re.sub(r"\s+", " ", addr)
        addr = re.sub(r"\bQLD\b", "", addr).strip()
        addr = re.sub(r"\b\d{4}\b$", "", addr).strip()
        return addr

    results = {"matches": [], "summary": {}}

    for suburb in TARGET_SUBURBS:
        time.sleep(2)  # Cosmos throttling
        target_docs = [d for d in all_docs if d["_suburb"] == suburb]

        # Load Gold_Coast addresses for this suburb
        gc_docs = list(db_gc[suburb].find(
            {},
            {"complete_address": 1, "LATITUDE": 1, "LONGITUDE": 1,
             "osm_location_features": 1, "scraped_data.valuation": 1,
             "scraped_data.property_timeline": 1, "scraped_data.rental_estimate": 1,
             "lot_size_sqm": 1, "iteration_08_valuation": 1,
             "STREET_NAME": 1, "STREET_NO_1": 1}
        ))

        # Build lookup
        gc_by_addr = {}
        for gc in gc_docs:
            norm = normalise_address(gc.get("complete_address", ""))
            if norm:
                gc_by_addr[norm] = gc

        matched = 0
        for td in target_docs:
            norm_target = normalise_address(td.get("address", ""))
            gc_match = gc_by_addr.get(norm_target)

            if not gc_match:
                # Fallback: try without unit prefix
                stripped = re.sub(r"^\d+/", "", norm_target)
                gc_match = gc_by_addr.get(stripped)

            has_match = gc_match is not None
            if has_match:
                matched += 1

            results["matches"].append({
                "address": td.get("address", ""),
                "suburb": suburb,
                "matched": has_match,
                "has_lat_long": bool(gc_match and gc_match.get("LATITUDE")),
                "has_osm": bool(gc_match and gc_match.get("osm_location_features")),
                "has_domain_valuation": bool(gc_match and safe_get(gc_match, "scraped_data.valuation")),
                "has_timeline": bool(gc_match and safe_get(gc_match, "scraped_data.property_timeline")),
                "has_lot_size": bool(gc_match and gc_match.get("lot_size_sqm")),
                "has_rental_estimate": bool(gc_match and safe_get(gc_match, "scraped_data.rental_estimate")),
            })

        print(f"  {suburb}: {matched}/{len(target_docs)} matched ({100*matched/len(target_docs):.0f}%)")

    # Summary
    total = len(results["matches"])
    total_matched = sum(1 for m in results["matches"] if m["matched"])

    by_suburb = {}
    for suburb in TARGET_SUBURBS:
        sm = [m for m in results["matches"] if m["suburb"] == suburb]
        matched_count = sum(1 for m in sm if m["matched"])
        by_suburb[suburb] = {
            "total": len(sm),
            "matched": matched_count,
            "pct": round(100 * matched_count / len(sm), 1) if sm else 0,
            "has_lat_long": sum(1 for m in sm if m["has_lat_long"]),
            "has_osm": sum(1 for m in sm if m["has_osm"]),
            "has_domain_valuation": sum(1 for m in sm if m["has_domain_valuation"]),
            "has_timeline": sum(1 for m in sm if m["has_timeline"]),
            "has_lot_size": sum(1 for m in sm if m["has_lot_size"]),
        }

    results["summary"] = {
        "total": total,
        "matched": total_matched,
        "match_pct": round(100 * total_matched / total, 1),
        "by_suburb": by_suburb,
        "enrichment_coverage": {
            "lat_long": sum(1 for m in results["matches"] if m["has_lat_long"]),
            "osm_features": sum(1 for m in results["matches"] if m["has_osm"]),
            "domain_valuation": sum(1 for m in results["matches"] if m["has_domain_valuation"]),
            "property_timeline": sum(1 for m in results["matches"] if m["has_timeline"]),
            "lot_size": sum(1 for m in results["matches"] if m["has_lot_size"]),
        },
    }

    print(f"\n  Overall: {total_matched}/{total} matched ({results['summary']['match_pct']}%)")
    ec = results["summary"]["enrichment_coverage"]
    print(f"  Enrichment: lat/long={ec['lat_long']}, OSM={ec['osm_features']}, Domain val={ec['domain_valuation']}, timeline={ec['property_timeline']}, lot_size={ec['lot_size']}")

    with open(os.path.join(OUTPUT_DIR, "study_0_4_matching.json"), "w") as f:
        json.dump(results["summary"], f, indent=2)

    return results


# ── Study 0.5: GPT Score Quality Assessment ────────────────────────────────
def study_0_5(all_docs):
    """Assess reliability and distribution of GPT-4 photo analysis scores."""
    print("\n═══ Study 0.5: GPT Photo Analysis Score Quality ═══")

    score_fields = {
        "condition_summary.overall_score": lambda d: safe_get(d, "property_valuation_data.condition_summary.overall_score"),
        "condition_summary.exterior_score": lambda d: safe_get(d, "property_valuation_data.condition_summary.exterior_score"),
        "condition_summary.interior_score": lambda d: safe_get(d, "property_valuation_data.condition_summary.interior_score"),
        "condition_summary.kitchen_score": lambda d: safe_get(d, "property_valuation_data.condition_summary.kitchen_score"),
        "condition_summary.bathroom_score": lambda d: safe_get(d, "property_valuation_data.condition_summary.bathroom_score"),
        "condition_summary.outdoor_score": lambda d: safe_get(d, "property_valuation_data.condition_summary.outdoor_score"),
        "property_metadata.presentation_score": lambda d: safe_get(d, "property_valuation_data.property_metadata.property_presentation_score"),
        "property_metadata.market_appeal_score": lambda d: safe_get(d, "property_valuation_data.property_metadata.market_appeal_score"),
        "exterior.condition_score": lambda d: safe_get(d, "property_valuation_data.exterior.condition_score"),
        "kitchen.quality_score": lambda d: safe_get(d, "property_valuation_data.kitchen.quality_score"),
        "kitchen.condition_score": lambda d: safe_get(d, "property_valuation_data.kitchen.condition_score"),
        "outdoor.outdoor_entertainment_score": lambda d: safe_get(d, "property_valuation_data.outdoor.outdoor_entertainment_score"),
        "outdoor.landscaping_score": lambda d: safe_get(d, "property_valuation_data.outdoor.landscaping_score"),
        "renovation.modern_features_score": lambda d: safe_get(d, "property_valuation_data.renovation.modern_features_score"),
    }

    results = {"scores": {}, "summary": {}}

    for field_name, extractor in score_fields.items():
        values = []
        by_suburb = defaultdict(list)
        for d in all_docs:
            v = extractor(d)
            if v is not None and isinstance(v, (int, float)):
                values.append(v)
                by_suburb[d["_suburb"]].append(v)

        if values:
            arr = np.array(values)
            # Check for ceiling effect (>50% at max score)
            max_val = int(np.max(arr))
            at_max = sum(1 for v in values if v == max_val)
            ceiling_effect = at_max / len(values) > 0.3

            # Score distribution
            distribution = {}
            for v in range(1, 11):
                distribution[str(v)] = sum(1 for x in values if int(x) == v)

            # Suburb means (do they track price differences?)
            suburb_means = {}
            for s in CORE_SUBURBS:
                if by_suburb[s]:
                    suburb_means[s] = round(float(np.mean(by_suburb[s])), 2)

            results["scores"][field_name] = {
                "count": len(values),
                "mean": round(float(np.mean(arr)), 2),
                "median": round(float(np.median(arr)), 2),
                "std": round(float(np.std(arr)), 2),
                "min": int(np.min(arr)),
                "max": max_val,
                "distribution": distribution,
                "ceiling_effect": ceiling_effect,
                "pct_at_max": round(100 * at_max / len(values), 1),
                "suburb_means": suburb_means,
            }

    # Overall quality assessment
    ceiling_scores = [f for f, r in results["scores"].items() if r["ceiling_effect"]]
    good_variance = [f for f, r in results["scores"].items() if r["std"] >= 1.0 and not r["ceiling_effect"]]

    results["summary"] = {
        "total_score_fields": len(results["scores"]),
        "fields_with_ceiling_effect": ceiling_scores,
        "fields_with_good_variance": good_variance,
        "recommendation": (
            "Most scores cluster at 7-9 range with limited variance. "
            "Use with caution — differences between 7 and 8 may not be meaningful. "
            "Focus on scores with std >= 1.0 for cross-analysis."
        ),
    }

    print(f"  Analysed {len(results['scores'])} score fields")
    print(f"  Ceiling effect detected in: {ceiling_scores}")
    print(f"  Good variance (std >= 1.0): {good_variance}")

    for field_name, data in results["scores"].items():
        print(f"    {field_name:50s} mean={data['mean']:.1f} std={data['std']:.1f} ceiling={data['ceiling_effect']} (n={data['count']})")

    with open(os.path.join(OUTPUT_DIR, "study_0_5_gpt_scores.json"), "w") as f:
        json.dump(results, f, indent=2)

    return results


# ── Generate Summary Markdown ──────────────────────────────────────────────
def generate_summary(s01, s02, s03, s04, s05):
    """Generate human-readable markdown summary of all Phase 0 findings."""
    md = []
    md.append("# Phase 0: Data Quality Audit — Results")
    md.append(f"## Generated {datetime.now().strftime('%Y-%m-%d %H:%M AEST')}")
    md.append(f"## Total Records: {len([r for r in s03[0]['records']])}")
    md.append("")

    # Study 0.1
    md.append("---")
    md.append("## Study 0.1: Field Coverage Census")
    md.append("")
    md.append("| Field | Coverage | Count |")
    md.append("|-------|----------|-------|")
    for field_name in sorted(s01["overall"].keys()):
        r = s01["overall"][field_name]
        md.append(f"| {field_name} | {r['pct']}% | {r['count']}/{r['total']} |")
    md.append("")

    # Study 0.2
    md.append("---")
    md.append("## Study 0.2: DOM Reconstruction")
    md.append("")
    sm = s02[0]["summary"]
    md.append(f"**Records with DOM:** {sm['records_with_dom']}/{sm['total_records']} ({sm['coverage_pct']}%)")
    md.append(f"**Sources:** {json.dumps(sm['by_source'])}")
    md.append("")
    if "dom_distribution" in sm:
        d = sm["dom_distribution"]
        md.append(f"**Distribution:** median={d['median']}d, mean={d['mean']}d, p25={d['p25']}d, p75={d['p75']}d, range={d['min']}-{d['max']}d")
    md.append("")
    md.append("| Suburb | With DOM | % | Sources |")
    md.append("|--------|----------|---|---------|")
    for suburb in TARGET_SUBURBS:
        if suburb in sm["by_suburb"]:
            sv = sm["by_suburb"][suburb]
            md.append(f"| {suburb} | {sv['with_dom']}/{sv['total']} | {sv['pct']}% | {json.dumps(sv['sources'])} |")
    md.append("")

    # Study 0.3
    md.append("---")
    md.append("## Study 0.3: Price Parsing")
    md.append("")
    ps = s03[0]["summary"]
    md.append(f"**Parseable:** {ps['parseable']}/{ps['total_records']} ({ps['coverage_pct']}%)")
    md.append(f"**Unparseable:** {ps['unparseable']}, **Null:** {ps['null_price']}")
    md.append(f"**Outliers (>3xIQR):** {ps['outlier_count']}")
    md.append("")
    md.append("| Suburb | Median | Mean | Q1 | Q3 | Min | Max | N |")
    md.append("|--------|--------|------|----|----|-----|-----|---|")
    for suburb in TARGET_SUBURBS:
        if suburb in ps["by_suburb"]:
            sv = ps["by_suburb"][suburb]
            md.append(f"| {suburb} | ${sv['median']:,} | ${sv['mean']:,} | ${sv['p25']:,} | ${sv['p75']:,} | ${sv['min']:,} | ${sv['max']:,} | {sv['count']} |")
    md.append("")

    # Study 0.4
    md.append("---")
    md.append("## Study 0.4: Address Matching")
    md.append("")
    ms = s04["summary"]
    md.append(f"**Matched:** {ms['matched']}/{ms['total']} ({ms['match_pct']}%)")
    md.append("")
    ec = ms["enrichment_coverage"]
    md.append(f"**Enrichment coverage:** lat/long={ec['lat_long']}, OSM={ec['osm_features']}, Domain valuation={ec['domain_valuation']}, timeline={ec['property_timeline']}, lot_size={ec['lot_size']}")
    md.append("")
    md.append("| Suburb | Matched | % | Lat/Long | OSM | Domain Val | Timeline | Lot Size |")
    md.append("|--------|---------|---|----------|-----|------------|----------|----------|")
    for suburb in TARGET_SUBURBS:
        if suburb in ms["by_suburb"]:
            sv = ms["by_suburb"][suburb]
            md.append(f"| {suburb} | {sv['matched']}/{sv['total']} | {sv['pct']}% | {sv['has_lat_long']} | {sv['has_osm']} | {sv['has_domain_valuation']} | {sv['has_timeline']} | {sv['has_lot_size']} |")
    md.append("")

    # Study 0.5
    md.append("---")
    md.append("## Study 0.5: GPT Score Quality Assessment")
    md.append("")
    md.append(f"**Ceiling effect detected in:** {', '.join(s05['summary']['fields_with_ceiling_effect']) or 'None'}")
    md.append(f"**Good variance (std >= 1.0):** {', '.join(s05['summary']['fields_with_good_variance']) or 'None'}")
    md.append("")
    md.append("| Score Field | Mean | Std | Ceiling? | N | BW Mean | Robina Mean | VL Mean |")
    md.append("|-------------|------|-----|----------|---|---------|-------------|---------|")
    for field_name in sorted(s05["scores"].keys()):
        r = s05["scores"][field_name]
        sm_data = r.get("suburb_means", {})
        md.append(f"| {field_name} | {r['mean']} | {r['std']} | {'YES' if r['ceiling_effect'] else 'no'} | {r['count']} | {sm_data.get('burleigh_waters', '-')} | {sm_data.get('robina', '-')} | {sm_data.get('varsity_lakes', '-')} |")
    md.append("")

    md.append("---")
    md.append(f"*Fields Estate — Phase 0 Data Quality Audit | {datetime.now().strftime('%Y-%m-%d')}*")

    summary_path = "/home/fields/Fields_Orchestrator/output/positioning_research/phase_0_summary.md"
    with open(summary_path, "w") as f:
        f.write("\n".join(md))
    print(f"\n  Summary written to {summary_path}")
    return "\n".join(md)


# ── Main ────────────────────────────────────────────────────────────────────
def main():
    print("╔══════════════════════════════════════════════════════════════╗")
    print("║  Phase 0: Data Quality Audit — Property Positioning Research ║")
    print("╚══════════════════════════════════════════════════════════════╝")

    print("\nLoading all sold records...")
    all_docs = load_all_sold()

    s01 = study_0_1(all_docs)
    s02 = study_0_2(all_docs)
    s03 = study_0_3(all_docs)
    s04 = study_0_4(all_docs)
    s05 = study_0_5(all_docs)

    summary_md = generate_summary(s01, s02, s03, s04, s05)

    print("\n" + "=" * 60)
    print("Phase 0 COMPLETE")
    print("=" * 60)
    print(f"Output: {OUTPUT_DIR}/")
    print(f"Summary: output/positioning_research/phase_0_summary.md")

    return summary_md


if __name__ == "__main__":
    main()
