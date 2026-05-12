#!/usr/bin/env python3
"""
appraisal_data_pull.py — Aggregate every data point needed for a property appraisal report.

Pulls from multiple sources (Cosmos Gold_Coast, valuation engine output, ABS catchment data,
backtest results) into a single JSON document that the V5 appraisal template will consume.

Usage:
    python3 scripts/appraisal_data_pull.py --address "13 Terrace Court, Merrimac, QLD 4226"
    python3 scripts/appraisal_data_pull.py --property-id 690bd7e68b8f5465926045d7
    python3 scripts/appraisal_data_pull.py --address "..." --output /tmp/appraisal.json

Output structure mirrors `09_Appraisals/Version_Four/data/appraisal_data_spec.md`.
Fields the script cannot derive automatically (human input, AI-generated content)
are emitted as null with a `_todo` marker.
"""

from __future__ import annotations

import argparse
import json
import os
import re
import sys
from datetime import datetime
from pathlib import Path
from typing import Any, Optional

from bson import ObjectId

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from shared.db import get_client, normalize_suburb, TARGET_SUBURBS

# -- Constants ---------------------------------------------------------------

REPO_ROOT = Path(__file__).resolve().parent.parent
ABS_DATA_JSON = REPO_ROOT / "09_Appraisals" / "Version_Four" / "data" / "abs_census_2021" / "hhi_distribution_combined.json"

CATCHMENT_POAS = ["4220", "4226", "4227"]

# Map of attribute names in `adjustment_result.adjustments` → human-friendly receipt-page labels.
# Used for rendering the Comp-by-Comp page.
ADJUSTMENT_LABELS = {
    "land_size": "Land area",
    "floor_area": "Floor area",
    "bedrooms": "Bedrooms",
    "bathrooms": "Bathrooms",
    "car_spaces": "Car spaces",
    "pool": "Pool",
    "stories": "Stories",
    "renovation": "Renovation level",
    "water_views": "Water views",
    "cladding": "Cladding",
    "kitchen": "Kitchen",
    "ac_type": "Air conditioning",
    "build_year": "Build year",
    "beach_distance": "Beach proximity",
    "dual_living": "Dual-living configuration",
    "outlook": "Outlook",
    "boundary": "Boundary",
    "cul_de_sac": "Cul-de-sac",
    "bushland_boundary": "Bushland boundary",
}


# -- Property lookup ---------------------------------------------------------

def find_property(*, property_id: Optional[str] = None, address: Optional[str] = None,
                  suburb_hint: Optional[str] = None) -> tuple[dict, str]:
    """
    Return (property_doc, suburb_collection_name).

    Strategy:
    - If property_id given: search across all TARGET_SUBURBS collections
    - If address given: parse suburb from address, search that collection
    - If suburb_hint given: restrict search to that collection
    """
    client = get_client()
    db = client["Gold_Coast"]

    candidate_suburbs = TARGET_SUBURBS
    if suburb_hint:
        candidate_suburbs = [normalize_suburb(suburb_hint)]
    elif address:
        # parse "..., Merrimac, QLD 4226" → "merrimac"
        m = re.search(r",\s*([A-Za-z ]+?)\s*,\s*QLD", address, re.IGNORECASE)
        if m:
            candidate_suburbs = [normalize_suburb(m.group(1))]

    for suburb in candidate_suburbs:
        coll = db[suburb]
        if property_id:
            try:
                doc = coll.find_one({"_id": ObjectId(property_id)})
            except Exception:
                doc = coll.find_one({"_id": property_id})
            if doc:
                return doc, suburb
        elif address:
            doc = coll.find_one({"address": {"$regex": re.escape(address.strip()), "$options": "i"}})
            if doc:
                return doc, suburb

    raise LookupError(f"Property not found (id={property_id}, address={address}, suburb={suburb_hint})")


# -- Data extractors ---------------------------------------------------------

def extract_property_details(doc: dict, suburb: str) -> dict:
    """Subject property metadata for the cover, headers, valuation page."""
    return {
        "suburb_collection": suburb,
        "address": doc.get("address"),
        "address_short": doc.get("street_address") or _shorten_address(doc.get("address", "")),
        "suburb": doc.get("suburb"),
        "state": "QLD",
        "postcode": doc.get("postcode"),
        "bedrooms": doc.get("bedrooms"),
        "bathrooms": doc.get("bathrooms"),
        "car_spaces": doc.get("car_spaces"),
        "floor_area_sqm": _safe_num(doc.get("floor_area") or doc.get("floor_area_sqm")),
        "land_size_sqm": _safe_num(doc.get("land_size") or doc.get("land_size_sqm")),
        "property_type": doc.get("property_type"),
        "listing_status": doc.get("listing_status"),
        "features": {
            "pool": _bool(doc.get("pool_present") or doc.get("pool")),
            "dual_living": _bool(doc.get("dual_living")),
            "water_views": _bool(doc.get("water_views")),
            "renovation_level": doc.get("renovation_level"),
            "condition_score": doc.get("condition_score") or
                               (doc.get("property_valuation_data", {}) or {})
                                   .get("condition_summary", {}).get("overall_condition_score"),
        },
        "photography": {
            "domain_images": doc.get("images", []),
            "blob_images": doc.get("blob_images", []),
            "twilight_images": doc.get("twilight_images", []),  # may not exist
        },
    }


def extract_valuation(doc: dict) -> dict:
    """Reconciled range, confidence, comp set, per-attribute evidence — from valuation_data."""
    vd = doc.get("valuation_data") or {}
    if not vd:
        return {"_present": False}

    conf = vd.get("confidence") or {}
    summary = vd.get("summary") or {}
    rates_obj = vd.get("adjustment_rates") or {}

    # Build the comp set — include any comp with included_in_valuation=True
    # (both recent_sale and current_listing series are valid evidence)
    raw_comps = vd.get("comparables", [])
    valued_comps = [c for c in raw_comps if c.get("included_in_valuation")]

    def _weight_value(comp):
        w = comp.get("weight")
        if isinstance(w, dict):
            return float(w.get("normalized") or w.get("raw_weight") or 0)
        try:
            return float(w or 0)
        except (TypeError, ValueError):
            return 0.0

    valued_comps.sort(key=_weight_value, reverse=True)

    comp_records = []
    for c in valued_comps:
        adj = c.get("adjustment_result") or {}
        adjustments_dict = adj.get("adjustments") or {}
        adj_rows = []
        for key, payload in adjustments_dict.items():
            if not isinstance(payload, dict):
                continue
            dollars = payload.get("dollars", 0)
            diff = payload.get("diff", 0)
            label = ADJUSTMENT_LABELS.get(key, key.replace("_", " ").title())
            adj_rows.append({
                "key": key,
                "label": label,
                "subject_value": payload.get("subject_value"),
                "comp_value": payload.get("comp_value"),
                "diff": diff,
                "rate_per_unit": payload.get("rate"),
                "adjustment_dollars": dollars,
            })

        w = c.get("weight")
        comp_records.append({
            "address": c.get("address"),
            "series": c.get("series"),  # 'recent_sale' or 'current_listing'
            "comp_price": c.get("price"),
            "distance_km": c.get("distance_km"),
            "weight_normalized": _weight_value(c),
            "weight_raw": w.get("raw_weight") if isinstance(w, dict) else None,
            "weight_factors": w.get("factors") if isinstance(w, dict) else None,
            "adjusted_estimate": adj.get("adjusted_price"),
            "total_adjustment": adj.get("total_adjustment"),
            "total_adjustment_pct": adj.get("total_adjustment_pct"),
            "adjustments": adj_rows,
            "features": (c.get("features") or {}).get("basic", {}),
            "verification": c.get("verification"),
            "data_quality_pct": c.get("_data_quality_pct"),
            "images": c.get("images", [])[:3],
        })

    return {
        "_present": True,
        "computed_at": vd.get("computed_at"),
        "reconciled_valuation": conf.get("reconciled_valuation"),
        "range_low": (conf.get("range") or {}).get("low"),
        "range_high": (conf.get("range") or {}).get("high"),
        "confidence_level": conf.get("confidence"),
        "std_dev": conf.get("std_dev"),
        "cv": conf.get("cv"),
        "n_total_comps": summary.get("n_comps"),
        "n_included": summary.get("n_included_in_valuation"),
        "n_verified": conf.get("n_verified"),
        "comp_set": comp_records,
        "adjustment_rates_source": rates_obj.get("source"),
        "adjustment_rates_sample_size": rates_obj.get("sample_size"),
    }


def extract_cohort_medians(suburb: str, subject_bedrooms: Optional[int]) -> dict:
    """
    Cohort medians for the valuation page header — 4bd baseline and subject-bedroom cohort.

    Reads from `system_monitor.precomputed_market_charts` if available; otherwise
    falls back to live queries on the catchment collections.
    """
    client = get_client()
    sm = client["system_monitor"]
    gc = client["Gold_Coast"]

    # Try precomputed first
    chart = None
    try:
        chart = sm["precomputed_market_charts"].find_one({"suburb": suburb, "metric": "median_price_by_bedrooms"})
    except Exception:
        pass

    cohort_4bd = None
    cohort_subject = None

    if chart:
        # Schema varies — if it exists, parse out 4bd and subject-bd entries
        # Conservative: just attempt key lookups
        data = chart.get("data") or {}
        cohort_4bd = data.get("4") or data.get(4)
        if subject_bedrooms:
            cohort_subject = data.get(str(subject_bedrooms)) or data.get(subject_bedrooms)

    # Fallback: query catchment sold properties directly
    if cohort_4bd is None or cohort_subject is None:
        catchment_suburbs = ["robina", "varsity_lakes", "burleigh_waters", "burleigh_heads", "merrimac"]
        cohort_4bd = cohort_4bd or _query_cohort_median(gc, catchment_suburbs, bedrooms=4)
        if subject_bedrooms and cohort_subject is None:
            cohort_subject = _query_cohort_median(gc, catchment_suburbs, bedrooms=subject_bedrooms)

    lift_pct = None
    if cohort_4bd and cohort_subject and cohort_4bd.get("median") and cohort_subject.get("median"):
        lift_pct = round((cohort_subject["median"] / cohort_4bd["median"] - 1) * 100, 1)

    return {
        "cohort_4bd": cohort_4bd,
        "cohort_subject_bedrooms": cohort_subject,
        "subject_bedrooms": subject_bedrooms,
        "raw_lift_pct": lift_pct,
        "catchment_poas": CATCHMENT_POAS,
    }


def _parse_price_string(s) -> Optional[float]:
    """Parse '$1,520,000' or 'SOLD - $1,520,000' → 1520000.0. Return None if unparseable."""
    if s is None:
        return None
    if isinstance(s, (int, float)):
        return float(s) if s > 0 else None
    if not isinstance(s, str):
        return None
    m = re.search(r"\$\s*([\d,]+(?:\.\d+)?)", s)
    if not m:
        return None
    try:
        return float(m.group(1).replace(",", ""))
    except ValueError:
        return None


def _query_cohort_median(gc_db, suburbs: list, bedrooms: int, days_back: int = 365) -> Optional[dict]:
    """
    Live query — median sold price for {bedrooms}-bedroom homes across catchment suburbs.

    Looks at properties with listing_status='sold' AND a parseable sale_price/sold_date
    within the last `days_back` days.
    """
    from datetime import timedelta
    cutoff_iso = (datetime.utcnow() - timedelta(days=days_back)).strftime("%Y-%m-%d")

    prices = []
    for s in suburbs:
        try:
            coll = gc_db[s]
            cursor = coll.find(
                {
                    "listing_status": "sold",
                    "bedrooms": bedrooms,
                    "$or": [
                        {"sale_date": {"$gte": cutoff_iso}},
                        {"sold_date": {"$gte": cutoff_iso}},
                    ],
                },
                {"sale_price": 1, "sold_price": 1, "listing_price": 1},
            ).limit(1500)
            for d in cursor:
                # Try numeric sold_price first, then parse sale_price string, then listing_price
                price = (
                    d.get("sold_price")
                    if isinstance(d.get("sold_price"), (int, float)) and d.get("sold_price", 0) > 0
                    else _parse_price_string(d.get("sale_price"))
                    or _parse_price_string(d.get("listing_price"))
                )
                if price and price > 0:
                    prices.append(price)
        except Exception:
            continue

    if not prices:
        return None
    prices.sort()
    n = len(prices)
    median = prices[n // 2] if n % 2 else (prices[n // 2 - 1] + prices[n // 2]) / 2
    return {"median": int(median), "n": n}


def extract_backtest_mae() -> dict:
    """Fields valuation engine accuracy from the most recent backtest."""
    client = get_client()
    sm = client["system_monitor"]
    try:
        doc = sm["valuation_accuracy"].find_one(sort=[("computed_at", -1)])
    except Exception:
        doc = None

    return {
        "fields_mae_pct": (doc or {}).get("mae_pct", 11.4),
        "n_properties_backtested": (doc or {}).get("n_properties", 1270),
        "domain_mae_pct": 15.0,  # benchmark, static
        "computed_at": (doc or {}).get("computed_at"),
        "_source_present": doc is not None,
    }


def extract_catchment_demographics() -> dict:
    """ABS Census 2021 household income data — read from persisted JSON."""
    if not ABS_DATA_JSON.exists():
        return {"_present": False, "_note": f"Missing file: {ABS_DATA_JSON}"}
    with open(ABS_DATA_JSON) as f:
        data = json.load(f)

    thresholds = data.get("top_tier_thresholds", {})
    top_decile = thresholds.get(">=$4000/wk", {})
    top_quintile = thresholds.get(">=$3000/wk", {})

    return {
        "_present": True,
        "geography": data["geography"],
        "source": data["source"],
        "total_households": data["total_households_combined"],
        "per_poa": data["per_poa"],
        "top_decile_floor_aud": top_decile.get("annual_floor", 208000),
        "top_decile_households": top_decile.get("households", 3593),
        "top_decile_pct": top_decile.get("pct_of_catchment", 10.3),
        "top_quintile_floor_aud": top_quintile.get("annual_floor", 156000),
        "top_quintile_households": top_quintile.get("households", 7311),
        "top_quintile_pct": top_quintile.get("pct_of_catchment", 21.0),
        "median_weekly_hhi_per_poa": data["median_weekly_household_income"],
        "_data_path": str(ABS_DATA_JSON),
    }


def extract_ai_editorial(doc: dict) -> dict:
    """AI-generated editorial content already on the property — varies in availability."""
    ai = doc.get("ai_analysis") or {}
    return {
        "_present": bool(ai),
        "status": ai.get("status"),
        "generated_at": ai.get("generated_at"),
        "model": ai.get("model"),
        "drafts": ai.get("drafts", []),
        "final": ai.get("final"),  # final published draft if present
        "_note": "Appraisal needs additional AI content not in this field — persona narratives, scarcity claim, trade-offs prose. See spec doc.",
    }


def _human_input_slots() -> dict:
    """Slots that require seller intake / Will's judgement — emitted with TODO markers."""
    return {
        "seller_name": {"_todo": "Seller name for 'Prepared for {name}' on cover + inside cover"},
        "report_date_override": {"_todo": "Optional date override; defaults to today's month/year"},
        "recommended_list_price": {"_todo": "Will's judgement, post-inspection; applies precise-pricing protocol"},
        "list_price_rationale": {"_todo": "1-2 sentence rationale: portal bracket, round-number positioning"},
        "target_sale_price_low": {"_todo": "Will's target range low (e.g. $2,000,000)"},
        "target_sale_price_high": {"_todo": "Will's target range high (e.g. $2,050,000)"},
        "target_sale_rationale": {"_todo": "1-2 sentence rationale for target range"},
        "persona_overrides": {
            "_todo": "Per-persona willingness-to-pay ranges. Default: derived from valuation engine + persona lift factor.",
            "format": "[{persona_rank: 'primary', wtp_low: 1850000, wtp_high: 2050000}, ...]",
        },
    }


# -- Helpers -----------------------------------------------------------------

def _safe_num(v):
    if v is None:
        return None
    try:
        return float(v)
    except (ValueError, TypeError):
        return None


def _bool(v):
    if v is None:
        return None
    if isinstance(v, bool):
        return v
    if isinstance(v, (int, float)):
        return bool(v)
    if isinstance(v, str):
        return v.strip().lower() in ("yes", "true", "1", "y")
    return None


def _shorten_address(addr: str) -> str:
    """'13 Terrace Court, Merrimac, QLD 4226' → '13 Terrace Court'"""
    return addr.split(",")[0].strip() if addr else ""


# -- Build --------------------------------------------------------------------

def build_appraisal_data(*, property_id: Optional[str], address: Optional[str],
                         suburb_hint: Optional[str]) -> dict:
    doc, suburb_coll = find_property(property_id=property_id, address=address, suburb_hint=suburb_hint)
    prop = extract_property_details(doc, suburb_coll)
    val = extract_valuation(doc)
    cohort = extract_cohort_medians(suburb_coll, subject_bedrooms=prop.get("bedrooms"))
    backtest = extract_backtest_mae()
    demographics = extract_catchment_demographics()
    ai_editorial = extract_ai_editorial(doc)
    human = _human_input_slots()

    return {
        "_meta": {
            "schema_version": "1.0",
            "generated_at": datetime.utcnow().isoformat() + "Z",
            "property_mongo_id": str(doc["_id"]),
            "suburb_collection": suburb_coll,
            "spec_doc": "09_Appraisals/Version_Four/data/appraisal_data_spec.md",
        },
        "property": prop,
        "valuation": val,
        "cohort": cohort,
        "backtest": backtest,
        "demographics": demographics,
        "ai_editorial_existing": ai_editorial,
        "human_inputs_required": human,
    }


# -- CLI ---------------------------------------------------------------------

def main():
    p = argparse.ArgumentParser(description="Pull all data needed for a property appraisal.")
    p.add_argument("--property-id", help="Mongo _id of the property")
    p.add_argument("--address", help="Property address (e.g. '13 Terrace Court, Merrimac, QLD 4226')")
    p.add_argument("--suburb", help="Optional suburb hint when ID-only lookup is ambiguous")
    p.add_argument("--output", "-o", help="Output JSON path (default: stdout)")
    p.add_argument("--pretty", action="store_true", help="Pretty-print JSON")
    args = p.parse_args()

    if not args.property_id and not args.address:
        p.error("Provide --property-id or --address")

    try:
        data = build_appraisal_data(
            property_id=args.property_id,
            address=args.address,
            suburb_hint=args.suburb,
        )
    except LookupError as e:
        print(f"ERROR: {e}", file=sys.stderr)
        sys.exit(2)

    payload = json.dumps(data, default=str, indent=2 if args.pretty else None)

    if args.output:
        with open(args.output, "w") as f:
            f.write(payload)
        print(f"Wrote {args.output} ({len(payload):,} bytes)", file=sys.stderr)
    else:
        print(payload)


if __name__ == "__main__":
    main()
