"""
Cohort premium computation — for each notable feature on a subject, compute
the median sale-price premium that feature commanded in recent sold cohort.

Method:
  - Pull sold cohort from Gold_Coast.<catchment_suburbs> with sale_price and
    valuation_data.subject_property.features.basic (last 24 months by default).
  - For each notable feature, partition the cohort into "has feature" vs
    "doesn't have feature".
  - Compute median sale price of each partition.
  - Premium % = (median_with - median_without) / median_without * 100.
  - Report sample sizes so the seller can judge reliability.

This is descriptive, not predictive. The output reads as "homes with X
sold for a median Y% above homes without it in the same cohort" — past
tense, exact figures, sample size cited.

Output schema:
    [
      {
        "feature_key": "pool",
        "feature_label": "Pool",
        "premium_pct": 6.8,
        "n_with": 142,
        "n_without": 318,
        "median_with": 1485000,
        "median_without": 1390000,
        "reliable": True,
      },
      ...
    ]

A premium is flagged `reliable: False` if either partition has < 20 sales
or the premium magnitude is < 2% (within noise threshold).
"""
from __future__ import annotations

import logging
import statistics
from typing import Any, Dict, List, Optional

from pymongo.database import Database

logger = logging.getLogger(__name__)


# Engine feature path (same as scarcity_features.py)
_F = "valuation_data.subject_property.features.basic"

# Min sample size per partition before we trust the premium
MIN_SAMPLE_SIZE = 20
# Premium within ±2% counts as noise — drop reliability flag
NOISE_THRESHOLD_PCT = 2.0
# Cohort time window
COHORT_MONTHS = 24


# Feature key → predicate that returns True if a sold doc has the feature.
# Mirrors scarcity_features.FEATURE_RULES but reads from sold cohort docs.
def _has_feature(key: str, sold_doc: Dict[str, Any]) -> Optional[bool]:
    """Returns True if sold_doc has the feature, False if it doesn't, None
    if we can't tell (so the doc is excluded from that feature's cohort)."""
    feat = ((sold_doc.get("valuation_data") or {}).get("subject_property") or {}).get("features") or {}
    basic = feat.get("basic") or {}
    if not basic:
        return None  # no engine features → can't tell

    if key in ("bedrooms_5plus",):
        bed = basic.get("bedrooms")
        return None if bed is None else bed >= 5
    if key in ("bedrooms_6plus",):
        bed = basic.get("bedrooms")
        return None if bed is None else bed >= 6
    if key == "bathrooms_3plus":
        bath = basic.get("bathrooms")
        return None if bath is None else bath >= 3
    if key == "land_large":
        land = basic.get("land_size_sqm")
        return None if land is None else land >= 900
    if key == "land_extra_large":
        land = basic.get("land_size_sqm")
        return None if land is None else land >= 1500
    if key == "floor_large":
        floor = basic.get("floor_area_sqm")
        return None if floor is None else floor >= 250
    if key == "pool":
        return bool(basic.get("pool_present")) if "pool_present" in basic else None
    if key == "water_views":
        return bool(basic.get("water_views")) if "water_views" in basic else None
    if key == "near_beach_2km":
        d = basic.get("beach_distance_km")
        return None if d is None else (0 < d <= 2.0)
    if key == "near_beach_1km":
        d = basic.get("beach_distance_km")
        return None if d is None else (0 < d <= 1.0)
    if key == "two_storey":
        s = basic.get("number_of_stories")
        return None if s is None else s >= 2
    if key == "single_level":
        s = basic.get("number_of_stories")
        return None if s is None else s == 1
    # Relative-anchor keys (scarcity_features 2026-06-07). The subject qualifies
    # by cohort percentile, but the sold-cohort premium split uses a fixed bar
    # so the comparison is a stable "homes with vs without" partition.
    if key == "land_anchor":
        land = basic.get("land_size_sqm")
        return None if land is None else land >= 700
    if key == "floor_anchor":
        floor = basic.get("floor_area_sqm")
        return None if floor is None else floor >= 200
    if key == "bedrooms_anchor":
        bed = basic.get("bedrooms")
        return None if bed is None else bed >= 4
    if key == "high_quality_finish":
        rq = basic.get("renovation_quality_score")
        ks = basic.get("kitchen_score")
        if rq is None or ks is None:
            return None
        return rq >= 9 and ks >= 9
    return None


def _parse_price(v: Any) -> Optional[float]:
    if v is None:
        return None
    if isinstance(v, (int, float)):
        return float(v)
    if isinstance(v, str):
        import re
        digits = re.sub(r"[^\d.]", "", v)
        try:
            return float(digits) if digits else None
        except ValueError:
            return None
    return None


def _load_cohort(db: Database, catchment_suburbs: List[str]) -> List[Dict[str, Any]]:
    """Load sold properties from the catchment with sale_price + engine features."""
    out: List[Dict[str, Any]] = []
    projection = {
        "sale_price": 1, "sold_price": 1, "last_sold_price": 1,
        "sale_date": 1, "valuation_data.subject_property.features.basic": 1,
    }
    for suburb in catchment_suburbs:
        try:
            coll = db[suburb]
        except Exception:
            continue
        try:
            cursor = coll.find(
                {
                    "listing_status": "sold",
                    f"{_F}.bedrooms": {"$exists": True},
                },
                projection,
            ).limit(500)
            for doc in cursor:
                price = _parse_price(
                    doc.get("sale_price") or doc.get("sold_price") or doc.get("last_sold_price")
                )
                if not price or price < 100000 or price > 20000000:
                    continue
                doc["_parsed_price"] = price
                out.append(doc)
        except Exception as e:
            logger.debug(f"  cohort load failed for {suburb}: {e}")
    return out


# Clean, table-ready labels for the premium UI. The prose labels carried on
# the feature dicts ("a pool", "813 m² block") read oddly in a table, so the
# premium table uses these noun forms keyed by feature_key.
PREMIUM_LABELS = {
    "bedrooms_anchor": "4+ bedrooms",
    "bedrooms_5plus": "5+ bedrooms",
    "bedrooms_6plus": "6+ bedrooms",
    "bathrooms_3plus": "3+ bathrooms",
    "land_anchor": "Large block",
    "land_large": "Large block (900m²+)",
    "land_extra_large": "Extra-large block",
    "floor_anchor": "Large internal",
    "floor_large": "Large internal (250m²+)",
    "pool": "Pool",
    "water_views": "Water views",
    "near_beach_2km": "Within 2km of a beach",
    "near_beach_1km": "Within 1km of a beach",
    "single_level": "Single-level",
    "two_storey": "Two-storey",
    "high_quality_finish": "Premium finish",
}


def _premium_label(key: str, fallback: str) -> str:
    return PREMIUM_LABELS.get(key, fallback)


def compute_cohort_premiums(
    notable_features: List[Dict[str, str]],
    db: Database,
    catchment_suburbs: List[str],
) -> List[Dict[str, Any]]:
    """For each notable feature, compute the median premium in the sold cohort."""
    if not notable_features:
        return []

    cohort = _load_cohort(db, catchment_suburbs)
    if len(cohort) < 50:
        logger.warning(f"  cohort too small for premium analysis: {len(cohort)} sales")
        # Still emit but flag everything as unreliable
        return [
            {
                "feature_key": n["key"],
                "feature_label": _premium_label(n["key"], n["label"]),
                "premium_pct": None,
                "n_with": 0,
                "n_without": 0,
                "median_with": None,
                "median_without": None,
                "reliable": False,
                "note": f"Cohort too small ({len(cohort)} sales) for premium analysis",
            }
            for n in notable_features
        ]

    results: List[Dict[str, Any]] = []
    for n in notable_features:
        key = n["key"]
        with_prices: List[float] = []
        without_prices: List[float] = []
        for doc in cohort:
            has = _has_feature(key, doc)
            if has is None:
                continue
            if has:
                with_prices.append(doc["_parsed_price"])
            else:
                without_prices.append(doc["_parsed_price"])

        if not with_prices or not without_prices:
            results.append({
                "feature_key": key,
                "feature_label": _premium_label(n["key"], n["label"]),
                "premium_pct": None,
                "n_with": len(with_prices),
                "n_without": len(without_prices),
                "median_with": None,
                "median_without": None,
                "reliable": False,
                "note": "Empty partition",
            })
            continue

        m_with = statistics.median(with_prices)
        m_without = statistics.median(without_prices)
        premium = (m_with - m_without) / m_without * 100

        reliable = (
            len(with_prices) >= MIN_SAMPLE_SIZE
            and len(without_prices) >= MIN_SAMPLE_SIZE
            and abs(premium) >= NOISE_THRESHOLD_PCT
        )

        results.append({
            "feature_key": key,
            "feature_label": _premium_label(n["key"], n["label"]),
            "premium_pct": round(premium, 1),
            "n_with": len(with_prices),
            "n_without": len(without_prices),
            "median_with": int(m_with),
            "median_without": int(m_without),
            "reliable": reliable,
        })

    return results
