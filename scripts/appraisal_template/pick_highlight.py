"""Highlight-attribute ranker.

Given a subject property, produces a ranked list of candidate attribute
combinations the subject matches, each scored by rarity in the catchment.

This is the auto-input to Layer 4 (human-in-the-loop): the ranker surfaces
3-5 strong options, the human picks one. Picks live ~30 seconds, not
30 minutes.

Candidate menu — starter set (will iterate with testing per Phase A plan):
  - bedrooms exact (if >= 4)
  - bedrooms >= subject (if >= 5)
  - bathrooms >= subject (if >= 3)
  - car spaces >= subject (if >= 3)
  - land_size >= subject
  - pool_present
  - has_study AND has_home_office
  - condition_score >= 8 / 9
  - outdoor_entertainment >= 9
  - water_views
  - solar_visible
  - Pairs:
      bedrooms >= 5 AND pool
      bedrooms >= 5 AND condition >= 9
      bedrooms >= 5 AND outdoor_entertainment >= 9
      bedrooms >= 5 AND (has_study AND has_home_office)
      pool AND condition >= 9
      pool AND outdoor_entertainment >= 9

A candidate is INCLUDED only if the subject matches it (no point ranking an
attribute the subject doesn't have). A candidate is EXCLUDED if it would
match >= 30% of the catchment (not distinctive enough to be a highlight).
"""

from __future__ import annotations

from typing import Any, Optional

from . import data_pull


# ---------------------------------------------------------------------------
# Candidate definitions
# ---------------------------------------------------------------------------


def _subject_value(subject: dict, path: str) -> Any:
    """Navigate a dotted path into the subject doc. Returns None on miss."""
    cur: Any = subject
    for k in path.split("."):
        if isinstance(cur, dict):
            cur = cur.get(k)
        else:
            return None
    return cur


def _candidates_for(subject: dict) -> list[dict]:
    """Build the candidate list for this subject — only candidates the
    subject actually matches are returned."""
    beds = subject.get("bedrooms") or 0
    baths = subject.get("bathrooms") or 0
    cars = subject.get("carspaces") or subject.get("car_spaces") or 0
    land = subject.get("land_size_sqm") or 0
    pool = _subject_value(subject, "property_valuation_data.outdoor.pool_present") or False
    alfresco = _subject_value(subject, "property_valuation_data.outdoor.alfresco_present") or False
    outdoor_score = _subject_value(subject, "property_valuation_data.outdoor.outdoor_entertainment_score") or 0
    water_views = _subject_value(subject, "property_valuation_data.outdoor.water_views") or False
    has_study = _subject_value(subject, "property_valuation_data.property_metadata.has_study") or False
    has_office = _subject_value(subject, "property_valuation_data.property_metadata.has_home_office") or False
    solar = _subject_value(subject, "property_valuation_data.property_metadata.solar_visible") or False
    condition = _subject_value(subject, "property_valuation_data.property_overview.overall_condition_score") or 0

    cands: list[dict] = []

    # Single-attribute candidates
    if beds >= 4:
        cands.append(_cand(f"{_n(beds)} bedrooms", {"bedrooms": beds}, "exact-bedrooms"))
    if beds >= 5:
        cands.append(_cand(
            f"{_n(beds)} or more bedrooms",
            {"bedrooms": {"$gte": beds}},
            "min-bedrooms",
        ))
    if baths >= 3:
        cands.append(_cand(
            f"{_n(baths)} or more bathrooms",
            {"bathrooms": {"$gte": baths}},
            "min-bathrooms",
        ))
    if cars >= 3:
        cands.append(_cand(
            f"{_n(cars)} or more car spaces",
            {"carspaces": {"$gte": cars}},
            "min-carspaces",
        ))
    if land >= 600:
        # Use a tier-aligned threshold so it doesn't tie to one exact subject
        threshold = _floor_tier(land, [600, 700, 800, 1000])
        cands.append(_cand(
            f"land of {threshold} m² or more",
            {"land_size_sqm": {"$gte": threshold}},
            "min-land",
        ))
    if pool:
        cands.append(_cand("a pool", {"property_valuation_data.outdoor.pool_present": True}, "has-pool"))
    if has_study and has_office:
        cands.append(_cand(
            "both a study and a home office",
            {
                "property_valuation_data.property_metadata.has_study": True,
                "property_valuation_data.property_metadata.has_home_office": True,
            },
            "study-plus-office",
        ))
    if condition >= 9:
        cands.append(_cand(
            "move-in condition (9 or higher of 10)",
            {"property_valuation_data.property_overview.overall_condition_score": {"$gte": 9}},
            "condition-9plus",
        ))
    elif condition >= 8:
        cands.append(_cand(
            "move-in condition (8 or higher of 10)",
            {"property_valuation_data.property_overview.overall_condition_score": {"$gte": 8}},
            "condition-8plus",
        ))
    if outdoor_score >= 9:
        cands.append(_cand(
            "outdoor entertainment scoring 9 or higher of 10",
            {"property_valuation_data.outdoor.outdoor_entertainment_score": {"$gte": 9}},
            "outdoor-9plus",
        ))
    if water_views:
        cands.append(_cand("water views", {"property_valuation_data.outdoor.water_views": True}, "water-views"))
    if solar:
        cands.append(_cand("solar visible", {"property_valuation_data.property_metadata.solar_visible": True}, "solar"))

    # Pair candidates — the high-value combinations
    if beds >= 5 and pool:
        cands.append(_cand(
            f"{_n(beds)} or more bedrooms with a pool",
            {"bedrooms": {"$gte": beds}, "property_valuation_data.outdoor.pool_present": True},
            "beds+pool",
        ))
    if beds >= 5 and condition >= 9:
        cands.append(_cand(
            f"{_n(beds)} or more bedrooms in move-in condition",
            {
                "bedrooms": {"$gte": beds},
                "property_valuation_data.property_overview.overall_condition_score": {"$gte": 9},
            },
            "beds+condition",
        ))
    if beds >= 5 and outdoor_score >= 9:
        cands.append(_cand(
            f"{_n(beds)} or more bedrooms with outdoor entertainment 9 or higher",
            {
                "bedrooms": {"$gte": beds},
                "property_valuation_data.outdoor.outdoor_entertainment_score": {"$gte": 9},
            },
            "beds+outdoor",
        ))
    if beds >= 5 and has_study and has_office:
        cands.append(_cand(
            f"{_n(beds)} or more bedrooms with both a study and home office",
            {
                "bedrooms": {"$gte": beds},
                "property_valuation_data.property_metadata.has_study": True,
                "property_valuation_data.property_metadata.has_home_office": True,
            },
            "beds+study+office",
        ))
    if pool and condition >= 9:
        cands.append(_cand(
            "a pool and move-in condition (9 or higher)",
            {
                "property_valuation_data.outdoor.pool_present": True,
                "property_valuation_data.property_overview.overall_condition_score": {"$gte": 9},
            },
            "pool+condition",
        ))
    if pool and outdoor_score >= 9:
        cands.append(_cand(
            "a pool and outdoor entertainment 9 or higher",
            {
                "property_valuation_data.outdoor.pool_present": True,
                "property_valuation_data.outdoor.outdoor_entertainment_score": {"$gte": 9},
            },
            "pool+outdoor",
        ))

    return cands


def _cand(description: str, filter_dict: dict, key: str) -> dict:
    """Construct a candidate record."""
    return {
        "key": key,
        "description": description,
        "short_label": description,
        "filter": filter_dict,
    }


def _n(n: int) -> str:
    words = ["zero", "one", "two", "three", "four", "five", "six", "seven", "eight", "nine"]
    if 0 <= n <= 9:
        return words[n]
    return str(n)


def _floor_tier(value: float, tiers: list[int]) -> int:
    """Snap a continuous value down to the nearest tier threshold."""
    last = tiers[0]
    for t in tiers:
        if value >= t:
            last = t
        else:
            break
    return last


# ---------------------------------------------------------------------------
# Ranker
# ---------------------------------------------------------------------------


def rank(
    subject: dict,
    catchment: Optional[list[str]] = None,
    months: int = 12,
    top_n: int = 5,
    max_share: float = 0.30,
) -> list[dict]:
    """Rank candidate highlight attributes by rarity in the catchment.

    Returns the top N candidates, each with:
        - description, short_label, filter, key (from candidate definition)
        - count (number of universe matches)
        - share (count / universe_total)
        - ratio_str (e.g. "5 / 458")

    Candidates with share >= max_share (default 30%) are dropped — they're
    not distinctive enough to be a highlight.
    """
    catchment = catchment or data_pull.DEFAULT_CATCHMENT
    db = __import__("shared.db", fromlist=["get_client"]).get_client()["Gold_Coast"]
    base = data_pull.universe_filter(months)
    universe_total = sum(db[s].count_documents(base) for s in catchment)
    if universe_total == 0:
        return []

    cands = _candidates_for(subject)
    ranked = []
    for c in cands:
        full_filter = {**base, **c["filter"]}
        count = sum(db[s].count_documents(full_filter) for s in catchment)
        share = count / universe_total
        if share >= max_share:
            continue  # not distinctive enough
        if count == 0:
            # Genuine "zero like this" — keep, that's a powerful story.
            ratio_str = f"0 / {universe_total}"
        else:
            ratio_str = f"{count} / {universe_total}"
        ranked.append({
            **c,
            "count": count,
            "share": share,
            "ratio_str": ratio_str,
            "universe_total": universe_total,
        })

    # Sort by rarity (smallest share first). Ties: prefer single-attribute
    # over compound (cleaner story) — sort secondary by filter length.
    ranked.sort(key=lambda x: (x["share"], len(x["filter"])))
    return ranked[:top_n]
