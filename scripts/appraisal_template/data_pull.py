"""Section-specific data assemblers for the appraisal template system.

Each `section_NN_*` function takes a subject_id and returns the full render
payload for that section. Pure transform — no rendering, no I/O beyond DB reads.

Catchment defaults to the 4 target suburbs (merrimac, robina, varsity_lakes,
burleigh_waters). Override via `catchment=` keyword for non-target subjects.
"""

from __future__ import annotations

import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Optional

REPO_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO_ROOT))

from bson import ObjectId  # type: ignore
from shared.db import get_client  # type: ignore

DEFAULT_CATCHMENT = ["merrimac", "robina", "varsity_lakes", "burleigh_waters"]
DEFAULT_LOOKBACK_DAYS = 365


# ---------------------------------------------------------------------------
# Subject + universe lookups
# ---------------------------------------------------------------------------


def get_subject(subject_id: str, suburb_hint: Optional[str] = None) -> dict:
    """Fetch the subject property doc. Searches across target catchment suburbs
    unless `suburb_hint` narrows the lookup."""
    db = get_client()["Gold_Coast"]
    oid = ObjectId(subject_id) if not isinstance(subject_id, ObjectId) else subject_id

    suburbs = [suburb_hint] if suburb_hint else DEFAULT_CATCHMENT
    for s in suburbs:
        doc = db[s].find_one({"_id": oid})
        if doc:
            doc["_suburb_collection"] = s
            return doc
    # Fallback: scan all collections
    for coll_name in db.list_collection_names():
        if coll_name.startswith("_"):
            continue
        doc = db[coll_name].find_one({"_id": oid})
        if doc:
            doc["_suburb_collection"] = coll_name
            return doc
    raise LookupError(f"Subject {subject_id} not found in Gold_Coast")


def catchment_for(subject: dict) -> list[str]:
    """Return the catchment suburbs for a subject. Default to the 4 target
    suburbs (premium southern Gold Coast). Override here later when expanding."""
    return list(DEFAULT_CATCHMENT)


def universe_filter(months: int = 12) -> dict:
    """The canonical universe definition for cohort comparisons:
    sold houses in the last N months. Reusable across sections."""
    cutoff_iso = (datetime.now(timezone.utc) - timedelta(days=months * 30 + 5)).strftime("%Y-%m-%d")
    return {
        "listing_status": "sold",
        "sold_date": {"$gte": cutoff_iso},
        "property_type": "House",
    }


def universe_count(catchment: list[str], months: int = 12) -> int:
    """Total sold houses in catchment over the last N months."""
    db = get_client()["Gold_Coast"]
    f = universe_filter(months)
    return sum(db[s].count_documents(f) for s in catchment)


def universe_docs(catchment: list[str], months: int = 12, projection: Optional[dict] = None):
    """Iterator over every universe doc. Used by the ranker to evaluate
    multiple candidate filters in a single pass."""
    db = get_client()["Gold_Coast"]
    f = universe_filter(months)
    proj = projection or {
        "_id": 1,
        "street_address": 1,
        "bedrooms": 1,
        "bathrooms": 1,
        "carspaces": 1,
        "land_size_sqm": 1,
        "property_valuation_data.outdoor.pool_present": 1,
        "property_valuation_data.outdoor.alfresco_present": 1,
        "property_valuation_data.outdoor.outdoor_entertainment_score": 1,
        "property_valuation_data.outdoor.water_views": 1,
        "property_valuation_data.property_metadata.has_study": 1,
        "property_valuation_data.property_metadata.has_home_office": 1,
        "property_valuation_data.property_metadata.solar_visible": 1,
        "property_valuation_data.property_overview.overall_condition_score": 1,
        "property_valuation_data.property_overview.number_of_stories": 1,
    }
    for s in catchment:
        for d in db[s].find(f, proj):
            d["_suburb_collection"] = s
            yield d


# ---------------------------------------------------------------------------
# Section assemblers
# ---------------------------------------------------------------------------


def section_01_right(
    subject_id: str,
    highlight: Optional[dict] = None,
    catchment: Optional[list[str]] = None,
    months: int = 12,
) -> dict:
    """Section 01 right page — "Why this home is hard to replace."

    Returns the full render payload:
        - headline
        - subhead (auto-generated from subject features)
        - satellite_image_url + callouts
        - dot_grid spec (total, highlighted_count, optional indices)
        - caption (universe disclosure auto-injected)
        - advantage_box (Fields Advantage 01 copy from framework doc)
        - substantiation_record (for dual-write by substantiation.py)

    The `highlight` arg is the human-selected attribute combination (Layer 4 in
    the template stack). If None, defaults to the top-ranked candidate from
    `pick_highlight.rank()`. Callers in the ops UI should pass the human's pick.
    """
    subject = get_subject(subject_id)
    catchment = catchment or catchment_for(subject)
    total = universe_count(catchment, months)

    # Default highlight if none provided: top-ranked from the ranker.
    if highlight is None:
        from . import pick_highlight  # local import to avoid circular
        ranked = pick_highlight.rank(subject, catchment=catchment, months=months)
        if not ranked:
            raise ValueError("No highlight candidates ranked for this subject")
        highlight = ranked[0]

    # Caption — universe disclosure inline, per framework doc Rule 2
    as_at = datetime.now(timezone.utc).strftime("%-d %B %Y")
    caption = (
        f"Source: Fields cohort analysis · "
        f"{total} houses sold across {_format_suburbs(catchment)} · "
        f"12 months to {as_at} · "
        f"{highlight['count']} had {highlight['description']} · "
        f"methodology at fieldsestate.com.au/methodology"
    )

    # Substantiation record (Layer 5)
    sub_record = {
        "section": "01_right",
        "subject_id": str(subject["_id"]),
        "subject_address": subject.get("complete_address"),
        "catchment": catchment,
        "universe_filter": universe_filter(months),
        "universe_count": total,
        "highlight": highlight,
        "as_at_date": datetime.now(timezone.utc).isoformat(),
        "valid_until": (datetime.now(timezone.utc) + timedelta(days=7)).isoformat(),
        "framework_version": "2026-05-15",
    }

    return {
        "headline": "Why this home is hard to replace.",
        "subhead": _generate_subhead(subject),
        "satellite_image_url": (subject.get("satellite_analysis") or {}).get("satellite_image_url"),
        "satellite_callouts": _auto_callouts(subject),
        "dot_grid": {
            "total": total,
            "highlighted_count": highlight["count"],
            "label_total": f"{total} sold",
            "label_highlighted": highlight["short_label"],
        },
        "caption": caption,
        "advantage_box": FIELDS_ADVANTAGE_01,
        "substantiation_record": sub_record,
    }


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _format_suburbs(catchment: list[str]) -> str:
    names = [s.replace("_", " ").title() for s in catchment]
    if len(names) <= 2:
        return " and ".join(names)
    return ", ".join(names[:-1]) + " and " + names[-1]


def _generate_subhead(subject: dict) -> str:
    """Auto-compose the 5-feature subhead line from subject data.
    For 13TC the feature line is fixed by the appraisal author for now; this
    function will become richer as we add more subjects."""
    # MVP: for the first appraisal subject, this can fall back to a manual line
    # stored on the property doc or appraisal_pipeline record.
    pvd = subject.get("property_valuation_data") or {}
    overview = pvd.get("property_overview") or {}
    outdoor = pvd.get("outdoor") or {}
    metadata = pvd.get("property_metadata") or {}

    features = []
    beds = subject.get("bedrooms")
    if beds and beds >= 5:
        features.append(f"{_n_word(beds)} bedrooms")
    if metadata.get("has_study") and metadata.get("has_home_office"):
        features.append("dual-living configuration")
    elif metadata.get("has_study"):
        features.append("dedicated study")
    if outdoor.get("pool_present"):
        features.append("a pool")
    # Cul-de-sac + bushland boundary are not yet structured on most docs;
    # they fall to the appraisal author to confirm and add.
    # Placeholder: if osm_location_features.road_classification.is_cul_de_sac:
    #     features.append("the head of a cul-de-sac")

    if not features:
        return ""
    if len(features) == 1:
        return f"This home has {features[0]} — a feature the right buyer will struggle to find."
    return (
        ", ".join(features[:-1])
        + f" and {features[-1]} — features the right buyer will struggle to find in one home."
    )


def _n_word(n: int) -> str:
    """Spell out small numbers for narrative copy. Sticks to 1-9; numerals
    for everything else."""
    words = ["zero", "one", "two", "three", "four", "five", "six", "seven", "eight", "nine"]
    if 0 <= n <= 9:
        return words[n]
    return str(n)


def _auto_callouts(subject: dict) -> list[dict]:
    """Build the attribute callouts that overlay the satellite image. Returns
    a list of {label, value} dicts; the renderer positions them visually.
    For 13TC the original V4 layout has manual positioning; future versions
    can auto-place from satellite_analysis bounding boxes."""
    callouts = []
    pvd = subject.get("property_valuation_data") or {}
    outdoor = pvd.get("outdoor") or {}
    metadata = pvd.get("property_metadata") or {}

    if metadata.get("solar_visible"):
        callouts.append({"label": "SOLAR ARRAY", "value": ""})
    if outdoor.get("pool_present"):
        callouts.append({"label": "POOL", "value": ""})
    # Cul-de-sac, bushland boundary etc. become callouts once
    # satellite_analysis is run on the subject doc.
    return callouts


# ---------------------------------------------------------------------------
# Static editorial copy — Fields Advantage 01 from the framework doc
# ---------------------------------------------------------------------------

FIELDS_ADVANTAGE_01 = {
    "label": "FIELDS ADVANTAGE — 01",
    "body": (
        "Fields' data pipeline analyses the ingredients of a home before the "
        "campaign is written: floor plan, photography, satellite imagery, land, "
        "location, comparable sales, competing stock and buyer demand.\n\n"
        "The purpose is not to produce a headline claim. The purpose is to "
        "identify the strongest buyer argument: which features matter, which "
        "buyer values them, what evidence supports the price, what trade-offs "
        "should be named, and how the campaign should be built.\n\n"
        "That is the difference between describing a home and positioning it."
    ),
}

# Fields Advantage — 02. New copy per framework doc (replaces the universal-
# negative "No agency in the southern Gold Coast operates this analysis on
# a per-listing basis" that was flagged as B6 in the claim audit).
FIELDS_ADVANTAGE_02 = {
    "label": "FIELDS ADVANTAGE — 02",
    "body": (
        "Fields' buyer-mapping model is built from <strong>2,075 sold transactions</strong>, "
        "demographics for <strong>16,190 qualified residents</strong>, and enquiry-mix "
        "benchmarks across premium catchment listings over the last 24 months. "
        "Each feature combination is matched to the persona historically willing "
        "to pay the most for it — so the campaign reaches the right person, not "
        "the largest list. <strong>The campaign is built around how that buyer "
        "experiences the home, not around what the listing contains.</strong>"
    ),
}


# ---------------------------------------------------------------------------
# Section 02 right — Three buyers. One outbids the field.
# ---------------------------------------------------------------------------


def section_02_right(
    subject_id: str,
    catchment: list[str] | None = None,
    valuation_mid: float | None = None,
) -> dict:
    """Section 02 right page — "Three buyers. One outbids the field."

    Returns the render payload for the persona triptych. Personas come from
    `personas.resolve_personas()` — defaulted from the southern-GC-premium
    library, overridable via the ops UI on the appraisal_pipeline record.

    Match-bar fills are computed from the subject's actual structured feature
    values cross-referenced against per-persona feature_weights. Willingness-
    to-pay ranges are derived from `valuation_mid` and per-persona multipliers
    (caller-supplied; pulled from valuation engine output upstream).
    """
    from . import personas

    subject = get_subject(subject_id)
    catchment = catchment or catchment_for(subject)
    resolved = personas.resolve_personas(subject, valuation_mid=valuation_mid)

    as_at = datetime.now(timezone.utc).strftime("%-d %B %Y")
    catchment_str = _format_suburbs(catchment)

    caption = (
        f"Source: ABS Census 2021 Table G33 (household income) — "
        f"POA 4226 + 4227 + 4220 · ABS Regional Population 2022-23 · "
        f"Fields sold-cohort premium analysis · {catchment_str} · "
        f"{as_at} · methodology at fieldsestate.com.au/methodology"
    )

    sub_record = {
        "section": "02_right",
        "subject_id": str(subject["_id"]),
        "subject_address": subject.get("complete_address"),
        "catchment": catchment,
        "personas_resolved": [{"id": p["id"], "share_pct": p["share_pct"]} for p in resolved],
        "valuation_mid_input": valuation_mid,
        "as_at_date": datetime.now(timezone.utc).isoformat(),
        "valid_until": (datetime.now(timezone.utc) + timedelta(days=7)).isoformat(),
        "framework_version": "2026-05-15",
    }

    return {
        "headline_html": 'Three buyers. One <span class="copper">outbids</span> the field.',
        "subhead": "Your premium price likely comes from one of these three.",
        "personas": resolved,
        "anti_fit": "Not for this home: investors seeking yield, first-home buyers, new-build seekers.",
        "caption": caption,
        "advantage_box": FIELDS_ADVANTAGE_02,
        "substantiation_record": sub_record,
    }
