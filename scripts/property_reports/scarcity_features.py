"""
Scarcity feature extractor — identifies which of the subject's features
are genuinely uncommon vs the suburb cohort, then counts how many other
active listings carry the same feature stack.

Reads from `valuation_data.subject_property.features.basic` (computed by
the precompute_valuations engine — same data that drives the valuation).
For each feature in the canonical list, compares the subject's value to
configurable thresholds and tags it as "notable" or not.

Output schema:
    {
        "notable_features": [
            {"key": "bedrooms_5plus", "label": "5+ bedrooms", "value": "5 bd"},
            {"key": "pool", "label": "Pool", "value": "yes"},
            {"key": "land_large", "label": "Large block", "value": "1,021 m²"},
        ],
        "active_listings_total": 79,
        "active_matching_full_stack": 4,
        "active_matching_query": "5+ bed AND pool AND >900m² land",
        "catchment_suburbs": ["robina", "burleigh_waters", "varsity_lakes"],
    }

The combinatorial-match count tells the seller "of N active listings,
only K match your full stack" — the load-bearing scarcity claim.
"""
from __future__ import annotations

import logging
from typing import Any, Dict, List, Optional, Tuple

from pymongo.database import Database

logger = logging.getLogger(__name__)


# Catchment for combinatorial-match queries — southern Gold Coast premium
# market. Always include the subject's own suburb.
DEFAULT_CATCHMENT = [
    "robina", "burleigh_waters", "varsity_lakes",
    "merrimac", "mudgeeraba", "reedy_creek", "worongary",
    "burleigh_heads", "carrara",
]


# Rules for "notable" features. Each entry: (key, label, predicate, mongo_clause).
# Predicate runs against features.basic dict. Mongo clause runs against
# Gold_Coast.<suburb> active listings.
#
# A feature is "notable" only if the threshold is met. The mongo_clause is
# what we $match on when counting how many other listings carry the stack.

# Engine feature paths — these are the dot-paths on each Gold_Coast doc
# where the precompute_valuations engine writes features.basic.*. Coverage
# is ~70% of active listings (the ones we've valued); listings without
# engine features just don't contribute to the count, which is honest.
_F = "valuation_data.subject_property.features.basic"

FEATURE_RULES = [
    {
        "key": "bedrooms_5plus",
        "label": "5+ bedrooms",
        "render": lambda b: f"{int(b.get('bedrooms'))} bedrooms",
        "applies": lambda b: (b.get("bedrooms") or 0) >= 5,
        "mongo": lambda b: {f"{_F}.bedrooms": {"$gte": 5}},
    },
    {
        "key": "bedrooms_6plus",
        "label": "6+ bedrooms",
        "render": lambda b: f"{int(b.get('bedrooms'))} bedrooms",
        "applies": lambda b: (b.get("bedrooms") or 0) >= 6,
        "mongo": lambda b: {f"{_F}.bedrooms": {"$gte": 6}},
        "supersedes": "bedrooms_5plus",
    },
    {
        "key": "bathrooms_3plus",
        "label": "3+ bathrooms",
        "render": lambda b: f"{int(b.get('bathrooms'))} bathrooms",
        "applies": lambda b: (b.get("bathrooms") or 0) >= 3,
        "mongo": lambda b: {f"{_F}.bathrooms": {"$gte": 3}},
    },
    {
        "key": "land_large",
        "label": "Large block (900m²+)",
        "render": lambda b: f"{int(b.get('land_size_sqm'))} m² block",
        "applies": lambda b: (b.get("land_size_sqm") or 0) >= 900,
        "mongo": lambda b: {f"{_F}.land_size_sqm": {"$gte": 900}},
    },
    {
        "key": "land_extra_large",
        "label": "Extra-large block (1500m²+)",
        "render": lambda b: f"{int(b.get('land_size_sqm'))} m² block",
        "applies": lambda b: (b.get("land_size_sqm") or 0) >= 1500,
        "mongo": lambda b: {f"{_F}.land_size_sqm": {"$gte": 1500}},
        "supersedes": "land_large",
    },
    {
        "key": "floor_large",
        "label": "Large internal (250m²+)",
        "render": lambda b: f"{int(b.get('floor_area_sqm'))} m² internal",
        "applies": lambda b: (b.get("floor_area_sqm") or 0) >= 250,
        "mongo": lambda b: {f"{_F}.floor_area_sqm": {"$gte": 250}},
    },
    {
        "key": "pool",
        "label": "Pool",
        "render": lambda b: "Pool",
        "applies": lambda b: bool(b.get("pool_present")),
        "mongo": lambda b: {f"{_F}.pool_present": True},
    },
    {
        "key": "water_views",
        "label": "Water views",
        "render": lambda b: "Water views",
        "applies": lambda b: bool(b.get("water_views")),
        "mongo": lambda b: {f"{_F}.water_views": True},
    },
    {
        "key": "near_beach_2km",
        "label": "Within 2km of a beach",
        "render": lambda b: f"{b.get('beach_distance_km'):.1f} km to beach",
        "applies": lambda b: (b.get("beach_distance_km") is not None
                              and 0 < (b.get("beach_distance_km") or 0) <= 2.0),
        "mongo": lambda b: {f"{_F}.beach_distance_km": {"$lte": 2.0, "$gt": 0}},
    },
    {
        "key": "near_beach_1km",
        "label": "Within 1km of a beach",
        "render": lambda b: f"{b.get('beach_distance_km'):.1f} km to beach",
        "applies": lambda b: (b.get("beach_distance_km") is not None
                              and 0 < (b.get("beach_distance_km") or 0) <= 1.0),
        "mongo": lambda b: {f"{_F}.beach_distance_km": {"$lte": 1.0, "$gt": 0}},
        "supersedes": "near_beach_2km",
    },
    {
        "key": "two_storey",
        "label": "Two-storey",
        "render": lambda b: f"{int(b.get('number_of_stories'))}-storey",
        "applies": lambda b: (b.get("number_of_stories") or 0) >= 2,
        "mongo": lambda b: {f"{_F}.number_of_stories": {"$gte": 2}},
    },
    {
        "key": "high_quality_finish",
        "label": "High-quality finish",
        "render": lambda b: "Premium finish",
        "applies": lambda b: (b.get("renovation_quality_score") or 0) >= 9
                              and (b.get("kitchen_score") or 0) >= 9,
        "mongo": lambda b: {
            f"{_F}.renovation_quality_score": {"$gte": 9},
            f"{_F}.kitchen_score": {"$gte": 9},
        },
    },
]


def _features_from_subject(subject_doc: Dict[str, Any]) -> Optional[Dict[str, Any]]:
    """Pull the features.basic block from the valuation engine output.
    Returns None if the subject hasn't been valued yet."""
    val = (subject_doc or {}).get("valuation_data") or {}
    sp = val.get("subject_property") or {}
    features = sp.get("features") or {}
    basic = features.get("basic")
    return basic if isinstance(basic, dict) else None


def identify_notable_features(features_basic: Dict[str, Any]) -> List[Dict[str, str]]:
    """Run feature rules over the basic feature dict. De-dupes when a rule
    supersedes another (e.g. 6+ bedrooms supersedes 5+ bedrooms)."""
    raw_hits = []
    for rule in FEATURE_RULES:
        try:
            if rule["applies"](features_basic):
                raw_hits.append(rule)
        except Exception as e:
            logger.debug(f"  feature rule {rule['key']} threw: {e}")

    superseded: set = {r.get("supersedes") for r in raw_hits if r.get("supersedes")}
    out = []
    for rule in raw_hits:
        if rule["key"] in superseded:
            continue
        try:
            out.append({
                "key": rule["key"],
                "label": rule["label"],
                "value": rule["render"](features_basic),
            })
        except Exception:
            out.append({"key": rule["key"], "label": rule["label"], "value": rule["label"]})
    return out


def count_active_matches(
    db: Database,
    notable: List[Dict[str, str]],
    features_basic: Dict[str, Any],
    catchment: Optional[List[str]] = None,
) -> Tuple[int, int, str, List[str]]:
    """Count active listings in the catchment that match the full feature stack.
    Returns (total_active, matching_full_stack, query_description, catchment_suburbs).

    "Full stack" = AND of all the mongo clauses for the notable features.
    Empty clauses (features we can't reliably match against) are skipped.
    """
    catchment = catchment or DEFAULT_CATCHMENT

    # Build the $and clause from each notable feature's mongo selector
    rule_by_key = {r["key"]: r for r in FEATURE_RULES}
    and_clauses: List[Dict[str, Any]] = []
    described_parts: List[str] = []
    for n in notable:
        rule = rule_by_key.get(n["key"])
        if not rule:
            continue
        clause = rule["mongo"](features_basic)
        if clause:
            and_clauses.append(clause)
            described_parts.append(rule["label"])

    # Always-on: only count for-sale listings WITH engine features (so the
    # ratio is meaningful — we can't compare a feature on a non-valued listing).
    base = {
        "listing_status": "for_sale",
        f"{_F}.bedrooms": {"$exists": True},
    }

    total_active = 0
    matching_full = 0
    for suburb in catchment:
        try:
            coll = db[suburb]
        except Exception:
            continue
        try:
            total_active += coll.count_documents(base)
            if and_clauses:
                matching_full += coll.count_documents({**base, "$and": and_clauses})
        except Exception as e:
            logger.debug(f"  count failed for {suburb}: {e}")

    description = " · ".join(described_parts) if described_parts else "no matchable features"
    return (total_active, matching_full, description, catchment)


def resolve_scarcity_features(
    subject_doc: Dict[str, Any],
    db: Database,
    catchment: Optional[List[str]] = None,
) -> Optional[Dict[str, Any]]:
    """Run the full scarcity feature extractor. Returns None if the subject
    hasn't been valued yet (features.basic missing)."""
    features_basic = _features_from_subject(subject_doc)
    if not features_basic:
        return None

    notable = identify_notable_features(features_basic)
    if not notable:
        # The home has no standout features. Still emit the empty result so
        # the page can say "no uncommon features in the cohort" honestly.
        return {
            "notable_features": [],
            "active_listings_total": 0,
            "active_matching_full_stack": 0,
            "active_matching_query": "no matchable features",
            "catchment_suburbs": catchment or DEFAULT_CATCHMENT,
            "features_basic_snapshot": features_basic,
        }

    total, matching, descr, catch = count_active_matches(db, notable, features_basic, catchment)
    return {
        "notable_features": notable,
        "active_listings_total": total,
        "active_matching_full_stack": matching,
        "active_matching_query": descr,
        "catchment_suburbs": catch,
        "features_basic_snapshot": features_basic,
    }
