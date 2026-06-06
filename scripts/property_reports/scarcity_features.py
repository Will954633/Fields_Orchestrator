"""
Scarcity feature extractor — identifies the subject's selling stack and
counts how rare that *combination* is in the catchment.

Design (rewritten 2026-06-07): the value of a home is rarely one rare
feature — it is a COMBINATION of mostly-common features that together suit
one buyer. So we split the stack into two tiers:

  - ANCHORS: the mainstream, big-ticket features buyers screen on (land,
    internal floor area, pool, bedroom count). Chosen RELATIVE to the
    suburb cohort (above-typical), NOT against a hardcoded absolute bar —
    an 813 m² block can be an anchor in a suburb whose median is 600 m²
    even though it never clears a fixed "900 m²+" line.
  - DIFFERENTIATORS: the buyer-specific tippers (single-level living,
    premium finish; walk-to-school/park/childcare are merged in later by
    the narrative layer from the POI walk data). These are NOT counted —
    they are uncommon-coverage signals — they only add prose colour.

The load-bearing honest number is `active_matching_full_stack`: how many
active listings match the *anchor* combination (land + floor + beds + pool
+ bath — the features with reliable cohort coverage). That small number is
the receipt that justifies the "compete for it" framing downstream. We do
NOT fold sparse-coverage features (single-level, walks) into the count, so
the ratio can never be inflated by missing data.

Reads from `valuation_data.subject_property.features.basic` (computed by
the precompute_valuations engine — same data that drives the valuation),
falling back to inline derivation for off-market submissions.

Output schema:
    {
        "notable_features": [...],          # anchors + differentiators (full stack)
        "anchor_features": [...],           # mainstream strengths only
        "differentiator_features": [...],   # buyer-specific tippers only
        "active_listings_total": 198,
        "active_matching_full_stack": 6,
        "active_matching_query": "813 m² block · 4 bedrooms · Pool",
        "catchment_suburbs": [...],
        "cohort_stats": {"land_median": 612, "floor_median": 214, "n": 174},
        "features_basic_snapshot": {...},
    }
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


# Engine feature paths — the dot-paths on each Gold_Coast doc where the
# precompute_valuations engine writes features.basic.*. Coverage is ~70% of
# active listings (the ones we've valued); listings without engine features
# just don't contribute to the count, which is honest.
_F = "valuation_data.subject_property.features.basic"


# Absolute floors below which a mainstream feature is never an anchor (stops
# a small home over-claiming in a big-block suburb). The effective bar is
# max(floor, cohort_median * ANCHOR_REL_FACTOR) when a median is available —
# i.e. an anchor must be CLEARLY above typical, not merely above the median,
# so a home only marginally larger than the cohort doesn't earn a headline slot.
ANCHOR_FLOOR = {
    "land_size_sqm": 600,
    "floor_area_sqm": 190,
    "bedrooms": 4,
}
ANCHOR_REL_FACTOR = 1.12

# When the combination count is at or below this share of the cohort, the
# stack is genuinely uncommon → downstream may use scarcity-competition
# framing. Above it, the honest line is "differentiation comes from
# presentation". The narrative layer reads matching/total and decides.
SCARCE_SHARE = 0.15
SCARCE_MIN_COHORT = 10


def _num(v: Any) -> Optional[float]:
    if isinstance(v, (int, float)):
        return float(v)
    return None


def _round_to(v: float, step: int) -> int:
    return int(round(v / step) * step)


# Rules for the selling stack. Each rule:
#   key          — stable id (also the premium key where cohort_premiums knows it)
#   tier         — "anchor" (mainstream, counted) or "differentiator" (tipper, not counted)
#   label        — clean noun for the feature class ("Pool", "Land size")
#   value        — render(basic) -> the concrete figure ("813 m²", "4 bedrooms")
#   phrase       — render(basic) -> prose fragment for the hero line ("a pool",
#                  "813 m² of land", "single-level family living")
#   applies      — predicate(basic, ctx) -> bool ; ctx carries cohort medians
#   count_clause — clause(basic) -> mongo selector for the combination count,
#                  or None to EXCLUDE from the count (sparse-coverage features)
#   supersedes   — optional key this rule replaces when both fire
#
# Anchor count clauses are SUBJECT-RELATIVE ("land >= 90% of this home's")
# so the combination count means "actives as good or better on every counted
# axis" — a clean, honest scarcity number.
FEATURE_RULES: List[Dict[str, Any]] = [
    # ---- Anchors (mainstream, counted) ----
    {
        "key": "bedrooms_anchor",
        "tier": "anchor",
        "label": "Bedrooms",
        "value": lambda b: f"{int(b['bedrooms'])} bedrooms",
        "phrase": lambda b: f"{int(b['bedrooms'])} bedrooms",
        "applies": lambda b, ctx: (b.get("bedrooms") or 0) >= ANCHOR_FLOOR["bedrooms"],
        "count_clause": lambda b: {f"{_F}.bedrooms": {"$gte": int(b["bedrooms"])}},
    },
    {
        "key": "land_anchor",
        "tier": "anchor",
        "label": "Land size",
        "value": lambda b: f"{int(b['land_size_sqm'])} m²",
        "phrase": lambda b: f"{int(b['land_size_sqm'])} m² of land",
        "applies": lambda b, ctx: _anchor_above(b.get("land_size_sqm"), "land_size_sqm", ctx),
        "count_clause": lambda b: {f"{_F}.land_size_sqm": {"$gte": _round_to(b["land_size_sqm"] * 0.9, 10)}},
    },
    {
        "key": "floor_anchor",
        "tier": "anchor",
        "label": "Internal area",
        "value": lambda b: f"{int(b['floor_area_sqm'])} m²",
        "phrase": lambda b: f"{int(b['floor_area_sqm'])} m² of internal living",
        "applies": lambda b, ctx: _anchor_above(b.get("floor_area_sqm"), "floor_area_sqm", ctx),
        "count_clause": lambda b: {f"{_F}.floor_area_sqm": {"$gte": _round_to(b["floor_area_sqm"] * 0.9, 10)}},
    },
    {
        "key": "bathrooms_3plus",
        "tier": "anchor",
        "label": "Bathrooms",
        "value": lambda b: f"{int(b['bathrooms'])} bathrooms",
        "phrase": lambda b: f"{int(b['bathrooms'])} bathrooms",
        "applies": lambda b, ctx: (b.get("bathrooms") or 0) >= 3,
        "count_clause": lambda b: {f"{_F}.bathrooms": {"$gte": 3}},
    },
    {
        "key": "pool",
        "tier": "anchor",
        "label": "Pool",
        "value": lambda b: "Yes",
        "phrase": lambda b: "a pool",
        "applies": lambda b, ctx: bool(b.get("pool_present")),
        "count_clause": lambda b: {f"{_F}.pool_present": True},
    },
    {
        "key": "water_views",
        "tier": "anchor",
        "label": "Water views",
        "value": lambda b: "Yes",
        "phrase": lambda b: "water views",
        "applies": lambda b, ctx: bool(b.get("water_views")),
        "count_clause": lambda b: {f"{_F}.water_views": True},
    },
    {
        "key": "near_beach_2km",
        "tier": "anchor",
        "label": "Beach proximity",
        "value": lambda b: f"{b['beach_distance_km']:.1f} km",
        "phrase": lambda b: f"{b['beach_distance_km']:.1f} km to the beach",
        "applies": lambda b, ctx: _in_range(b.get("beach_distance_km"), 0, 2.0),
        "count_clause": lambda b: {f"{_F}.beach_distance_km": {"$lte": 2.0, "$gt": 0}},
    },
    {
        "key": "near_beach_1km",
        "tier": "anchor",
        "label": "Beach proximity",
        "value": lambda b: f"{b['beach_distance_km']:.1f} km",
        "phrase": lambda b: f"{b['beach_distance_km']:.1f} km to the beach",
        "applies": lambda b, ctx: _in_range(b.get("beach_distance_km"), 0, 1.0),
        "count_clause": lambda b: {f"{_F}.beach_distance_km": {"$lte": 1.0, "$gt": 0}},
        "supersedes": "near_beach_2km",
    },
    # ---- Differentiators (buyer-specific tippers, NOT counted) ----
    {
        "key": "single_level",
        "tier": "differentiator",
        "label": "Single-level",
        "value": lambda b: "1 storey",
        "phrase": lambda b: "single-level living",
        "applies": lambda b, ctx: (b.get("number_of_stories") or 0) == 1,
        "count_clause": lambda b: None,
    },
    {
        "key": "high_quality_finish",
        "tier": "differentiator",
        "label": "Finish",
        "value": lambda b: "Premium",
        "phrase": lambda b: "a premium finish throughout",
        "applies": lambda b, ctx: (b.get("renovation_quality_score") or 0) >= 9
                                  and (b.get("kitchen_score") or 0) >= 9,
        "count_clause": lambda b: None,
    },
]


def _anchor_above(value: Any, field: str, ctx: Dict[str, Any]) -> bool:
    """A mainstream metric is an anchor when it clears the effective bar:
    max(absolute floor, cohort median). Falls back to the floor when no
    cohort median is available."""
    v = _num(value)
    if v is None or v <= 0:
        return False
    floor = ANCHOR_FLOOR[field]
    median = (ctx or {}).get(f"{field}_median")
    bar = max(floor, median * ANCHOR_REL_FACTOR) if median else floor
    return v >= bar


def _in_range(value: Any, lo: float, hi: float) -> bool:
    v = _num(value)
    return v is not None and lo < v <= hi


def _features_from_subject(subject_doc: Dict[str, Any]) -> Optional[Dict[str, Any]]:
    """Pull the features.basic block from the valuation engine output, or
    derive it inline if the precompute job hasn't run."""
    val = (subject_doc or {}).get("valuation_data") or {}
    sp = val.get("subject_property") or {}
    features = sp.get("features") or {}
    basic = features.get("basic")
    if isinstance(basic, dict) and basic:
        return basic
    from scripts.property_reports.inline_features import derive_features_basic
    return derive_features_basic(subject_doc)


def compute_cohort_medians(
    db: Database, catchment: List[str], cap_per_suburb: int = 400,
) -> Dict[str, Any]:
    """Median land/floor across active valued listings in the catchment, so
    anchor thresholds adapt to the local market. Light projected reads; on
    any failure returns empty so callers fall back to absolute floors."""
    base = {"listing_status": "for_sale", f"{_F}.bedrooms": {"$exists": True}}
    projection = {f"{_F}.land_size_sqm": 1, f"{_F}.floor_area_sqm": 1, "_id": 0}
    lands: List[float] = []
    floors: List[float] = []
    for suburb in catchment:
        try:
            cursor = db[suburb].find(base, projection).limit(cap_per_suburb)
        except Exception as e:
            logger.debug(f"  cohort median find failed for {suburb}: {e}")
            continue
        for doc in cursor:
            basic = (((doc.get("valuation_data") or {}).get("subject_property") or {})
                     .get("features") or {}).get("basic") or {}
            l = _num(basic.get("land_size_sqm"))
            f = _num(basic.get("floor_area_sqm"))
            if l and l > 0:
                lands.append(l)
            if f and f > 0:
                floors.append(f)

    def _median(xs: List[float]) -> Optional[float]:
        if not xs:
            return None
        xs = sorted(xs)
        n = len(xs)
        mid = n // 2
        return xs[mid] if n % 2 else (xs[mid - 1] + xs[mid]) / 2

    return {
        "land_size_sqm_median": _median(lands),
        "floor_area_sqm_median": _median(floors),
        "land_median": _median(lands),
        "floor_median": _median(floors),
        "n": max(len(lands), len(floors)),
    }


def identify_features(
    features_basic: Dict[str, Any], ctx: Optional[Dict[str, Any]] = None,
) -> Tuple[List[Dict[str, str]], List[Dict[str, str]]]:
    """Run feature rules. Returns (anchors, differentiators), each a list of
    {key, tier, label}. De-dupes superseding rules (1km beach over 2km)."""
    ctx = ctx or {}
    raw_hits = []
    for rule in FEATURE_RULES:
        try:
            if rule["applies"](features_basic, ctx):
                raw_hits.append(rule)
        except Exception as e:
            logger.debug(f"  feature rule {rule['key']} threw: {e}")

    superseded = {r.get("supersedes") for r in raw_hits if r.get("supersedes")}
    anchors: List[Dict[str, str]] = []
    diffs: List[Dict[str, str]] = []
    for rule in raw_hits:
        if rule["key"] in superseded:
            continue
        try:
            value = rule["value"](features_basic)
        except Exception:
            value = rule["label"]
        try:
            phrase = rule["phrase"](features_basic)
        except Exception:
            phrase = value
        entry = {
            "key": rule["key"], "tier": rule["tier"],
            "label": rule["label"], "value": value, "phrase": phrase,
        }
        (anchors if rule["tier"] == "anchor" else diffs).append(entry)
    return anchors, diffs


def count_active_matches(
    db: Database,
    anchors: List[Dict[str, str]],
    features_basic: Dict[str, Any],
    catchment: Optional[List[str]] = None,
) -> Tuple[int, int, str, List[str]]:
    """Count active listings matching the full ANCHOR combination.
    Returns (total_active, matching_full_stack, query_description, catchment).

    Only anchors with a non-None count_clause contribute (sparse-coverage
    features are excluded so the ratio can't be inflated by missing data)."""
    catchment = catchment or DEFAULT_CATCHMENT
    rule_by_key = {r["key"]: r for r in FEATURE_RULES}

    and_clauses: List[Dict[str, Any]] = []
    described_parts: List[str] = []
    for a in anchors:
        rule = rule_by_key.get(a["key"])
        if not rule:
            continue
        try:
            clause = rule["count_clause"](features_basic)
        except Exception:
            clause = None
        if clause:
            and_clauses.append(clause)
            described_parts.append(a.get("value") or a["label"])

    # Only count for-sale listings WITH engine features (so the ratio is
    # meaningful — we can't compare a feature on a non-valued listing).
    base = {"listing_status": "for_sale", f"{_F}.bedrooms": {"$exists": True}}

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

    description = " · ".join(described_parts) if described_parts else "no countable anchors"
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

    catch = catchment or DEFAULT_CATCHMENT
    cohort_stats = compute_cohort_medians(db, catch)
    anchors, diffs = identify_features(features_basic, cohort_stats)

    # notable_features keeps the full stack (anchors + differentiators) for
    # downstream consumers (cohort_premiums, positioning, buyers narratives).
    notable = anchors + diffs

    if not notable:
        return {
            "notable_features": [],
            "anchor_features": [],
            "differentiator_features": [],
            "active_listings_total": 0,
            "active_matching_full_stack": 0,
            "active_matching_query": "no notable features",
            "catchment_suburbs": catch,
            "cohort_stats": cohort_stats,
            "features_basic_snapshot": features_basic,
        }

    total, matching, descr, catch = count_active_matches(db, anchors, features_basic, catch)
    return {
        "notable_features": notable,
        "anchor_features": anchors,
        "differentiator_features": diffs,
        "active_listings_total": total,
        "active_matching_full_stack": matching,
        "active_matching_query": descr,
        "catchment_suburbs": catch,
        "cohort_stats": cohort_stats,
        "features_basic_snapshot": features_basic,
    }


# Back-compat shim: older callers expected identify_notable_features() to
# return the flat stack. Preserve it.
def identify_notable_features(features_basic: Dict[str, Any]) -> List[Dict[str, str]]:
    anchors, diffs = identify_features(features_basic, {})
    return anchors + diffs
