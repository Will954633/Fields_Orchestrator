"""
Cohort premium computation — for each notable feature on a subject, measure
what the sold cohort actually paid for it, at three levels of scrutiny:

  1. Headline gap   — raw median of homes WITH the feature vs WITHOUT.
                      This is the number a portal or listing agent quotes.
                      It bundles the feature with everything it comes with.
  2. Like-for-like  — the same comparison inside matched bedroom strata
                      (or on a price-per-square-metre basis for features
                      where bedroom strata are the feature itself).
  3. Controlled     — where the Fields controlled research (2,153 sales,
                      hedonic $/sqm analysis across the three target
                      suburbs) has a verified finding, it is the final word.

The point of the three layers is honesty: most headline gaps shrink under
scrutiny because features travel together — pool homes are bigger homes on
bigger blocks. We show the shrink instead of hiding it. A feature is then
classified:

  price_driver   — the gap survives like-for-like comparison; buyers in
                   this cohort paid for the feature itself.
  bundled        — the headline gap mostly reflects the homes the feature
                   comes with (size, beds, land), not the feature.
  demand_feature — controlled research found no significant price effect,
                   but the feature changes WHO searches for the home
                   (e.g. pool: portal buyers filter to pool-only).
  headline_only  — sample too small to control; raw gap reported with an
                   explicit "uncontrolled" flag, never as a value claim.

Everything here is deterministic and reproducible from the sold cohort —
no model in the loop. Narrative modules receive the controlled framing via
premium_prompt_lines() so generated prose cannot quote a headline gap as
the feature's standalone value.

Output schema (per feature):
    {
      "feature_key": "pool",
      "feature_label": "Pool",
      # layer 1 — headline gap (legacy fields, kept for compatibility)
      "premium_pct": 29.0,
      "n_with": 113, "n_without": 91,
      "median_with": 1600000, "median_without": 1240000,
      "reliable": True,
      # layer 2 — like-for-like
      "like_for_like_pct": 13.0,        # None if no qualifying strata
      "like_for_like_basis": "bedroom-stratified",  # or "per-sqm"
      "strata": [{"bedrooms": 3, "n_with": 22, "n_without": 44, "premium_pct": 11.9}, ...],
      "per_sqm_pct": 7.5,               # None where not meaningful
      "per_sqm_n_with": 108, "per_sqm_n_without": 75,
      # context
      "composition": {"floor_with": 185, "floor_without": 149,
                       "land_with": 671, "land_without": 500,
                       "beds_with": 4, "beds_without": 3},
      "dom_with": 29, "dom_without": 26,    # None if sample thin
      "prevalence_pct": 55.4,               # share of cohort sales WITH it
      # layer 3 + verdict
      "research": {"range": "+0.6% to +3.7%", "significant": False,
                    "note": "..."},          # only where verified research exists
      "classification": "demand_feature",
      "verdict": "one-sentence, data-only",
    }
"""
from __future__ import annotations

import logging
import statistics
from typing import Any, Dict, List, Optional

from pymongo.database import Database

logger = logging.getLogger(__name__)


# Engine feature path (same as scarcity_features.py)
_F = "valuation_data.subject_property.features.basic"

# Min sample size per partition before we trust the headline gap
MIN_SAMPLE_SIZE = 20
# Min sample per side inside a bedroom stratum before the stratum counts
MIN_STRATUM_SIZE = 8
# Premium within ±2% counts as noise
NOISE_THRESHOLD_PCT = 2.0
# Cohort time window
COHORT_MONTHS = 24
# DOM medians only reported when both sides have at least this many
MIN_DOM_SAMPLE = 15


# ---------------------------------------------------------------------------
# Verified findings from the Fields controlled research (2,153 sales, hedonic
# price-per-sqm analysis across Robina, Burleigh Waters, Varsity Lakes —
# the same analysis quoted in Before You List, p19 and ch.6). Only features
# with a finding we can stand behind appear here. Do NOT add entries without
# a verifiable source — this map overrides the cohort arithmetic.
# ---------------------------------------------------------------------------
RESEARCH_FINDINGS: Dict[str, Dict[str, Any]] = {
    "pool": {
        "range": "+0.6% to +3.7%",
        "significant": False,
        "classification": "demand_feature",
        "note": (
            "Across 2,153 sales in the three target suburbs, the relationship "
            "between having a pool and price per square metre is between 0.6% "
            "and 3.7% — not statistically significant. The pool correlates "
            "with larger, newer homes; it is along for the ride, not driving "
            "the price."
        ),
    },
    "high_quality_finish": {
        "range": "near zero",
        "significant": False,
        "classification": "bundled",
        "note": (
            "Renovation and finish-quality scores showed near-zero "
            "correlation with price per square metre in the Fields "
            "controlled analysis (p > 0.1)."
        ),
    },
}

# How each feature is controlled. Bedroom features can't be stratified by
# bedrooms (the stratum IS the feature); floor-size features can't use
# per-sqm (it mechanically erases the feature being measured); land features
# can't either — $/sqm falls with floor size and big-block homes have
# systematically bigger floors, so the rung would understate land's effect
# rather than control for anything.
_NO_BEDROOM_STRATA = {"bedrooms_anchor", "bedrooms_5plus", "bedrooms_6plus"}
_NO_PER_SQM = {"floor_anchor", "floor_large", "land_anchor", "land_large", "land_extra_large"}


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


def _basic(doc: Dict[str, Any]) -> Dict[str, Any]:
    return (
        ((doc.get("valuation_data") or {}).get("subject_property") or {}).get("features") or {}
    ).get("basic") or {}


def _load_cohort(db: Database, catchment_suburbs: List[str]) -> List[Dict[str, Any]]:
    """Load sold properties from the catchment with sale_price + engine features."""
    out: List[Dict[str, Any]] = []
    projection = {
        "sale_price": 1, "sold_price": 1, "last_sold_price": 1,
        "sale_date": 1, "days_on_market": 1,
        "valuation_data.subject_property.features.basic": 1,
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


def _median(values: List[float]) -> Optional[float]:
    return statistics.median(values) if values else None


def _pct_gap(m_with: Optional[float], m_without: Optional[float]) -> Optional[float]:
    if m_with is None or m_without is None or not m_without:
        return None
    return (m_with - m_without) / m_without * 100


def _stratified_premium(
    with_docs: List[Dict[str, Any]], without_docs: List[Dict[str, Any]]
) -> tuple:
    """Bedroom-stratified premium: compare medians inside each bedroom count
    where both sides have MIN_STRATUM_SIZE+ sales, weight by stratum size.
    Returns (weighted_pct or None, strata detail list)."""
    strata: List[Dict[str, Any]] = []
    weighted_sum = 0.0
    weight_total = 0
    beds_present = sorted({
        _basic(d).get("bedrooms") for d in with_docs + without_docs
        if _basic(d).get("bedrooms") is not None
    })
    for bed in beds_present:
        wp = [d["_parsed_price"] for d in with_docs if _basic(d).get("bedrooms") == bed]
        np_ = [d["_parsed_price"] for d in without_docs if _basic(d).get("bedrooms") == bed]
        if len(wp) < MIN_STRATUM_SIZE or len(np_) < MIN_STRATUM_SIZE:
            continue
        prem = _pct_gap(_median(wp), _median(np_))
        if prem is None:
            continue
        n = len(wp) + len(np_)
        weighted_sum += prem * n
        weight_total += n
        strata.append({
            "bedrooms": bed,
            "n_with": len(wp),
            "n_without": len(np_),
            "premium_pct": round(prem, 1),
        })
    if not weight_total:
        return None, strata
    return round(weighted_sum / weight_total, 1), strata


def _per_sqm_premium(
    with_docs: List[Dict[str, Any]], without_docs: List[Dict[str, Any]]
) -> tuple:
    """Price-per-floor-sqm comparison — controls for home size.
    Returns (pct or None, n_with, n_without)."""
    wp = [
        d["_parsed_price"] / _basic(d)["floor_area_sqm"]
        for d in with_docs
        if _basic(d).get("floor_area_sqm")
    ]
    np_ = [
        d["_parsed_price"] / _basic(d)["floor_area_sqm"]
        for d in without_docs
        if _basic(d).get("floor_area_sqm")
    ]
    if len(wp) < MIN_SAMPLE_SIZE or len(np_) < MIN_SAMPLE_SIZE:
        return None, len(wp), len(np_)
    pct = _pct_gap(_median(wp), _median(np_))
    return (round(pct, 1) if pct is not None else None), len(wp), len(np_)


def _composition(
    with_docs: List[Dict[str, Any]], without_docs: List[Dict[str, Any]]
) -> Dict[str, Optional[float]]:
    """Median floor / land / bedrooms for each side — the 'what the feature
    comes bundled with' evidence."""
    def med_of(docs: List[Dict[str, Any]], field: str) -> Optional[float]:
        vals = [_basic(d).get(field) for d in docs]
        vals = [v for v in vals if isinstance(v, (int, float)) and v > 0]
        return round(statistics.median(vals), 0) if vals else None

    return {
        "floor_with": med_of(with_docs, "floor_area_sqm"),
        "floor_without": med_of(without_docs, "floor_area_sqm"),
        "land_with": med_of(with_docs, "land_size_sqm"),
        "land_without": med_of(without_docs, "land_size_sqm"),
        "beds_with": med_of(with_docs, "bedrooms"),
        "beds_without": med_of(without_docs, "bedrooms"),
    }


def _dom_medians(
    with_docs: List[Dict[str, Any]], without_docs: List[Dict[str, Any]]
) -> tuple:
    def doms(docs):
        return [
            d["days_on_market"] for d in docs
            if isinstance(d.get("days_on_market"), (int, float)) and 0 < d["days_on_market"] < 400
        ]
    wd, nd = doms(with_docs), doms(without_docs)
    if len(wd) < MIN_DOM_SAMPLE or len(nd) < MIN_DOM_SAMPLE:
        return None, None
    return round(statistics.median(wd)), round(statistics.median(nd))


def _classify(
    key: str,
    raw_pct: Optional[float],
    lfl_pct: Optional[float],
) -> tuple:
    """Returns (classification, verdict). Research overrides win; otherwise
    the like-for-like behaviour decides. Verdicts are data-only — they
    describe what the cohort shows, never what the reader should do."""
    research = RESEARCH_FINDINGS.get(key)
    if research:
        cls = research["classification"]
        if cls == "demand_feature":
            verdict = (
                "Controlled analysis found no statistically significant price "
                "lift from this feature itself. Its measurable role is demand: "
                "it keeps the home inside feature-filtered buyer searches."
            )
        else:
            verdict = (
                "The headline gap reflects the homes this feature comes with, "
                "not the feature — controlled analysis found near-zero "
                "standalone effect."
            )
        return cls, verdict

    if lfl_pct is None:
        return "headline_only", (
            "The cohort is too small to compare like-for-like, so only the "
            "uncontrolled gap is shown. Treat it as a description of the "
            "homes that sold, not the feature's standalone value."
        )
    if lfl_pct >= NOISE_THRESHOLD_PCT:
        if raw_pct is not None and raw_pct > 0 and lfl_pct < raw_pct * 0.6:
            verdict = (
                f"Part of the headline gap is the company this feature keeps, "
                f"but a {lfl_pct:+.1f}% gap survives like-for-like comparison "
                f"— buyers in this cohort paid for the feature itself."
            )
        else:
            verdict = (
                f"The gap holds at {lfl_pct:+.1f}% when homes are compared "
                f"like-for-like — buyers in this cohort paid for the feature "
                f"itself."
            )
        return "price_driver", verdict
    return "bundled", (
        "Compared like-for-like, the gap falls inside the noise threshold — "
        "the headline number mostly reflects the larger homes this feature "
        "comes with."
    )


def compute_cohort_premiums(
    notable_features: List[Dict[str, str]],
    db: Database,
    catchment_suburbs: List[str],
) -> List[Dict[str, Any]]:
    """For each notable feature, compute the premium at every level of
    scrutiny the cohort supports, plus composition and demand context."""
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
                "like_for_like_pct": None,
                "classification": "headline_only",
                "note": f"Cohort too small ({len(cohort)} sales) for premium analysis",
            }
            for n in notable_features
        ]

    results: List[Dict[str, Any]] = []
    for n in notable_features:
        key = n["key"]
        with_docs: List[Dict[str, Any]] = []
        without_docs: List[Dict[str, Any]] = []
        for doc in cohort:
            has = _has_feature(key, doc)
            if has is None:
                continue
            (with_docs if has else without_docs).append(doc)

        if not with_docs or not without_docs:
            results.append({
                "feature_key": key,
                "feature_label": _premium_label(n["key"], n["label"]),
                "premium_pct": None,
                "n_with": len(with_docs),
                "n_without": len(without_docs),
                "median_with": None,
                "median_without": None,
                "reliable": False,
                "like_for_like_pct": None,
                "classification": "headline_only",
                "note": "Empty partition",
            })
            continue

        with_prices = [d["_parsed_price"] for d in with_docs]
        without_prices = [d["_parsed_price"] for d in without_docs]
        m_with = statistics.median(with_prices)
        m_without = statistics.median(without_prices)
        raw_pct = _pct_gap(m_with, m_without)

        reliable = (
            len(with_prices) >= MIN_SAMPLE_SIZE
            and len(without_prices) >= MIN_SAMPLE_SIZE
            and raw_pct is not None
            and abs(raw_pct) >= NOISE_THRESHOLD_PCT
        )

        # Layer 2 — like-for-like
        strat_pct, strata = (None, [])
        if key not in _NO_BEDROOM_STRATA:
            strat_pct, strata = _stratified_premium(with_docs, without_docs)
        sqm_pct, sqm_n_with, sqm_n_without = (None, 0, 0)
        if key not in _NO_PER_SQM:
            sqm_pct, sqm_n_with, sqm_n_without = _per_sqm_premium(with_docs, without_docs)

        if strat_pct is not None:
            lfl_pct, lfl_basis = strat_pct, "bedroom-stratified"
        elif sqm_pct is not None:
            lfl_pct, lfl_basis = sqm_pct, "per-sqm"
        else:
            lfl_pct, lfl_basis = None, None

        dom_with, dom_without = _dom_medians(with_docs, without_docs)
        prevalence = round(len(with_docs) / (len(with_docs) + len(without_docs)) * 100, 1)

        classification, verdict = _classify(key, raw_pct, lfl_pct)

        row: Dict[str, Any] = {
            "feature_key": key,
            "feature_label": _premium_label(n["key"], n["label"]),
            "premium_pct": round(raw_pct, 1) if raw_pct is not None else None,
            "n_with": len(with_prices),
            "n_without": len(without_prices),
            "median_with": int(m_with),
            "median_without": int(m_without),
            "reliable": reliable,
            "like_for_like_pct": lfl_pct,
            "like_for_like_basis": lfl_basis,
            "strata": strata,
            "per_sqm_pct": sqm_pct,
            "per_sqm_n_with": sqm_n_with,
            "per_sqm_n_without": sqm_n_without,
            "composition": _composition(with_docs, without_docs),
            "dom_with": dom_with,
            "dom_without": dom_without,
            "prevalence_pct": prevalence,
            "classification": classification,
            "verdict": verdict,
        }
        research = RESEARCH_FINDINGS.get(key)
        if research:
            row["research"] = {
                "range": research["range"],
                "significant": research["significant"],
                "note": research["note"],
            }
        results.append(row)

    return results


def premium_prompt_lines(cohort_premiums: List[Dict[str, Any]]) -> List[str]:
    """The honest representation of premiums for narrative model prompts.
    Replaces the old raw-only feed so generated prose can never quote a
    headline gap as a feature's standalone value."""
    lines = [
        "SOLD COHORT FEATURE EVIDENCE (last 24 months in catchment).",
        "RULES: never present a 'headline gap' as the feature's standalone value-add.",
        "Quote only the like-for-like figure or the controlled-research finding as",
        "the feature's value. Headline gaps may only appear with the explanation",
        "that they bundle the feature with larger/better homes.",
    ]
    for p in cohort_premiums or []:
        raw = p.get("premium_pct")
        if raw is None:
            continue
        lfl = p.get("like_for_like_pct")
        cls = p.get("classification", "headline_only")
        bits = [f"headline gap {raw:+.1f}% (n_with={p['n_with']}, n_without={p['n_without']})"]
        if lfl is not None:
            bits.append(f"like-for-like {lfl:+.1f}% ({p.get('like_for_like_basis')})")
        research = p.get("research")
        if research:
            sig = "significant" if research.get("significant") else "NOT statistically significant"
            bits.append(f"controlled research: {research['range']} ({sig})")
        bits.append(f"classification: {cls}")
        lines.append(f"  - {p['feature_label']}: " + " | ".join(bits))
    return lines
