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

# Fields Advantage — 04. Rewrite removes the universal-claim "Most agents
# market to buyers already searching on the portals" (Rule 7).
FIELDS_ADVANTAGE_04 = {
    "label": "FIELDS ADVANTAGE — 04",
    "body": (
        "The campaign starts with the buyer most likely to pay the premium, "
        "then builds reach to find them across the platforms where their "
        "attention actually is — realestate.com.au, Domain, Facebook, "
        "Instagram, YouTube and Google. The campaign is built around the "
        "buyer avatar from Section 02, not a generic list of channels. "
        "<strong>Premium prices come from competition — Fields' job is to "
        "find the second passionate buyer in the room, because the cost of "
        "missing that buyer is too great to ignore.</strong>"
    ),
}

# Fields Advantage — 05. Rewrite removes "Most agents list features. Fields
# turns them into desire" (Rule 7 universal-claim).
FIELDS_ADVANTAGE_05 = {
    "label": "FIELDS ADVANTAGE — 05",
    "body": (
        "<strong>Fields builds the presentation around the buyer most likely "
        "to pay the premium.</strong> Photography, listing copy, editorial "
        "storytelling and feature emphasis are all calibrated to <em>how that "
        "buyer will experience the home</em> — not just what the home "
        "contains. The work is to turn features into desire."
    ),
}

# Fields Advantage — 06. Rewrite removes "Real estate has a trust problem"
# (industry-level negative observation reframed to focus on what Fields
# delivers without characterising the industry).
FIELDS_ADVANTAGE_06 = {
    "label": "FIELDS ADVANTAGE — 06",
    "body": (
        "<strong>Buyers need evidence they can trust.</strong> Fields' "
        "valuation work, property editorial, campaign reporting and "
        "buyer-facing analysis are designed to reduce uncertainty at every "
        "stage of the sale. <strong>When the price, the strengths and the "
        "trade-offs are visible, confidence rises — and confident buyers "
        "are more likely to compete.</strong>"
    ),
}

# Fields Advantage — 03. New copy per framework doc (replaces "Most
# appraisals rely on a handful of comparable sales" — flagged as B13 in
# the claim audit. We don't characterise the industry; we describe what
# we do).
FIELDS_ADVANTAGE_03 = {
    "label": "FIELDS ADVANTAGE — 03",
    "body": (
        "Fields' valuation engine analyses <strong>1,696 sold transactions across the "
        "southern Gold Coast</strong>, measuring how individual attributes influence "
        "price: bedrooms, pools, land size, floor area, cul-de-sac position, condition, "
        "outlook and more. The engine runs the full cohort, then narrows the evidence "
        "to the homes most relevant to yours. <strong>Every major pricing assumption "
        "is anchored to observed market evidence — listed transparently on the "
        "next page.</strong>"
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


# ---------------------------------------------------------------------------
# Section 03 right — Valuation derivation
# ---------------------------------------------------------------------------


def _format_dollar_compact(n: float | int | None) -> str:
    if not n: return ""
    return f"${n/1_000_000:.2f}M"


def _format_dollar_exact(n: float | int | None) -> str:
    if not n: return ""
    return f"${int(n):,}"


def _cohort_median(suburbs: list[str], bedrooms: int, months: int = 12) -> tuple[int | None, int]:
    """Return (median_sale_price, n) for the bedroom cohort in catchment.
    Reads sold_price from sold records in the last N months. Cosmos sometimes
    stores sale_price as string '$X,YYY,YYY' so we parse defensively."""
    import re
    db = get_client()["Gold_Coast"]
    cutoff = (datetime.now(timezone.utc) - timedelta(days=months*30 + 5)).strftime("%Y-%m-%d")
    prices: list[float] = []
    for s in suburbs:
        for d in db[s].find({
            "listing_status": "sold",
            "sold_date": {"$gte": cutoff},
            "property_type": "House",
            "bedrooms": bedrooms,
        }, {"sale_price": 1, "sold_price": 1, "listing_price": 1}):
            p = d.get("sold_price")
            if isinstance(p, (int, float)) and p > 0:
                prices.append(float(p)); continue
            raw = d.get("sale_price") or d.get("listing_price")
            if isinstance(raw, (int, float)) and raw > 0:
                prices.append(float(raw)); continue
            if isinstance(raw, str):
                m = re.search(r'(\d[\d,\.]+)', raw.replace("$", ""))
                if m:
                    try: prices.append(float(m.group(1).replace(",", "")))
                    except ValueError: pass
    if not prices: return (None, 0)
    prices.sort()
    n = len(prices)
    median = prices[n//2] if n % 2 else (prices[n//2 - 1] + prices[n//2]) / 2
    return (int(median), n)


def section_03_right(
    subject_id: str,
    catchment: list[str] | None = None,
    months: int = 12,
) -> dict:
    """Section 03 right page — "The range, derived." (valuation evidence)

    Returns the render payload. Cohort medians + n come from direct queries;
    evidence_stack (per-attribute weights) defaults to a manual baseline and
    is overridable via editorial_overrides for per-subject tuning. Derived
    range comes from `valuation_data.summary` on the property doc (populated
    by the comparable-sales engine upstream).
    """
    subject = get_subject(subject_id)
    catchment = catchment or catchment_for(subject)
    beds = subject.get("bedrooms") or 4

    # Cohort medians — baseline is 4-bed, primary is subject's bedroom count
    base_median, base_n = _cohort_median(catchment, bedrooms=4, months=months)
    subj_median, subj_n = _cohort_median(catchment, bedrooms=beds, months=months)
    lift_pct = round((subj_median - base_median) / base_median * 100) if (base_median and subj_median) else None

    # Reconciled range — `valuation_data.confidence` holds the canonical
    # range/midpoint; `summary` carries metadata counts. (Schema spans both
    # nested objects for historical reasons.)
    val = subject.get("valuation_data") or {}
    summary = val.get("summary") or {}
    conf_obj = val.get("confidence") or {}
    range_obj = conf_obj.get("range") or {}
    range_low = range_obj.get("low") or summary.get("reconciled_low")
    range_high = range_obj.get("high") or summary.get("reconciled_high")
    range_mid = conf_obj.get("reconciled_valuation") or summary.get("reconciled_value") or summary.get("reconciled_mid")
    n_comps = summary.get("n_included_in_valuation") or summary.get("n_comps") or len(val.get("comparables") or [])
    confidence = conf_obj.get("confidence", "")

    # Pending state: valuation engine has not produced a range yet. The page
    # renders a clear "analyst review required" notice instead of fragments
    # like " – ." and an empty derived-range banner. Analyst sets the comp
    # set + confirms valuation via the Appraisal Pipeline panel in the ops
    # dashboard, after which the valuation engine writes valuation_data.
    pending_review = not (range_low and range_high)

    as_at = datetime.now(timezone.utc).strftime("%-d %B %Y")

    sub_record = {
        "section": "03_right",
        "subject_id": str(subject["_id"]),
        "subject_address": subject.get("complete_address"),
        "catchment": catchment,
        "cohort_baseline": {"bedrooms": 4, "median": base_median, "n": base_n},
        "cohort_subject": {"bedrooms": beds, "median": subj_median, "n": subj_n},
        "lift_pct": lift_pct,
        "reconciled_range": {"low": range_low, "high": range_high, "mid": range_mid},
        "n_comps": n_comps,
        "confidence": confidence,
        "as_at_date": datetime.now(timezone.utc).isoformat(),
        "valid_until": (datetime.now(timezone.utc) + timedelta(days=7)).isoformat(),
        "framework_version": "2026-05-15",
    }

    return {
        "pending_review": pending_review,
        "headline_dollar_range": f"{_format_dollar_compact(range_low)} – {_format_dollar_compact(range_high)}",
        "headline_html_template": '<span class="copper">{range}.</span> The range, derived.',
        "subhead": "Anchored in the cohort. Narrowed to the homes most relevant to yours.",
        "cohort_anchor_html": (
            f"{_n_word(4)}-bedroom homes, southern Gold Coast, last 12 months — "
            f"<strong>median {_format_dollar_exact(base_median)}</strong> (n={base_n}).<br>"
            f"{_n_word(beds)}-bedroom homes, same cohort — "
            f"<strong>median {_format_dollar_exact(subj_median)}</strong> (n={subj_n})."
            + (f"<br><span class=\"lift\">A +{lift_pct}% raw lift, before further attribute weighting.</span>" if lift_pct else "")
        ),
        "synthesis": {
            "low": _format_dollar_compact(range_low),
            "high": _format_dollar_compact(range_high),
            "mid": _format_dollar_compact(range_mid),
            "confidence": confidence,
        },
        "n_comps": n_comps,
        "confidence_label": confidence,
        "caption": (
            f"Source: Fields valuation engine · catchment {_format_suburbs(catchment)} · "
            f"sold transactions last {months} months · n_comparables={n_comps} · "
            f"{as_at} · methodology at fieldsestate.com.au/methodology"
        ),
        "advantage_box": FIELDS_ADVANTAGE_03,
        "substantiation_record": sub_record,
    }


def _n_word(n: int) -> str:
    """Spell out small numbers for narrative copy."""
    words = ["zero","one","two","three","four","five","six","seven","eight","nine"]
    if isinstance(n, int) and 0 <= n <= 9: return words[n]
    return str(n)


# ---------------------------------------------------------------------------
# Sections 04, 05, 06 — smaller payloads (mostly editorial; framework-compliant
# Fields Advantage boxes are the key compliance lift on these pages).
# ---------------------------------------------------------------------------


ADJUSTMENT_LABELS = {
    "floor_area": "Floor area",
    "land_size": "Land area",
    "land_area": "Land area",
    "bedrooms": "Bedrooms",
    "bathrooms": "Bathrooms",
    "car_spaces": "Car spaces",
    "pool": "Pool",
    "dual_living": "Dual-living configuration",
    "cul_de_sac": "Cul-de-sac",
    "bushland_boundary": "Bushland boundary",
    "boundary": "Boundary",
    "outlook": "Outlook",
    "kitchen": "Kitchen",
    "renovation": "Renovation level",
    "build_year": "Build year",
    "stories": "Stories",
    "water_views": "Water views",
    "ac_type": "Air conditioning",
    "cladding": "Cladding",
    "beach_distance": "Beach proximity",
}


def section_03_receipts(
    subject_id: str,
    top_n: int = 2,
    catchment: list[str] | None = None,
) -> dict:
    """§03 receipts (comp-by-comp adjustments) page payload.

    Pulls the top-N most heavily weighted comparables from
    `valuation_data.comparables` and assembles per-comp adjustment cards.
    Each card lists every non-zero adjustment with subject vs comp values
    and the dollar adjustment.

    The B14-flagged "Domain accuracy" line in the legacy V4 page is
    removed here — replaced with Fields' own backtest figure plus a
    methodology link (per framework Rule 4, Rule 8).
    """
    subject = get_subject(subject_id)
    catchment = catchment or catchment_for(subject)

    val = subject.get("valuation_data") or {}
    raw_comps = val.get("comparables") or []
    valued = [c for c in raw_comps if c.get("included_in_valuation")]

    def _wnum(c):
        w = c.get("weight")
        if isinstance(w, dict):
            return float(w.get("normalized") or w.get("raw_weight") or 0)
        try: return float(w or 0)
        except (TypeError, ValueError): return 0.0

    valued.sort(key=_wnum, reverse=True)

    cards = []
    rest_weight_pct = 0
    for i, c in enumerate(valued):
        if i >= top_n:
            rest_weight_pct += round(_wnum(c) * 100)
            continue
        adj = c.get("adjustment_result") or {}
        adj_dict = adj.get("adjustments") or {}
        rows = []
        for key, payload in adj_dict.items():
            if not isinstance(payload, dict):
                continue
            dollars = payload.get("dollars", 0) or 0
            diff = payload.get("diff")
            if dollars == 0 and (diff in (0, None)):
                continue
            label = ADJUSTMENT_LABELS.get(key, key.replace("_", " ").title())
            rows.append({
                "key": key,
                "label": label,
                "diff": diff,
                "subject_value": payload.get("subject_value"),
                "comp_value": payload.get("comp_value"),
                "adjustment_dollars": dollars,
            })
        weight = _wnum(c)
        adjusted_total = adj.get("adjusted_total") or adj.get("adjusted_estimate") or 0
        sold_price = c.get("sold_price") or c.get("sale_price")
        if isinstance(sold_price, str):
            import re
            m = re.search(r'(\d[\d,\.]+)', sold_price.replace("$", ""))
            sold_price = float(m.group(1).replace(",", "")) if m else None
        cards.append({
            "rank_label": f"Comp {i+1:02d}",
            "address": c.get("address") or c.get("street_address") or "Unknown",
            "sold_price": int(sold_price) if sold_price else None,
            "distance_km": c.get("distance_km") or c.get("distance"),
            "adjustments": rows,
            "adjusted_total": int(adjusted_total) if adjusted_total else None,
            "weight_pct": round(weight * 100),
            "sold_date": c.get("sold_date") or c.get("sale_date"),
        })

    rest_count = max(0, len(valued) - top_n)
    as_at = datetime.now(timezone.utc).strftime("%-d %B %Y")
    return {
        "pending_review": len(cards) == 0,
        "headline_html": 'What went into <span class="copper">your valuation</span>.',
        "subhead": f"The specific adjustments behind the range — comp by comp.",
        "cards": cards,
        "rest_count": rest_count,
        "rest_weight_pct": rest_weight_pct,
        "backtest_stat": {
            # B14 rework: Fields-only figure, no Domain comparison. Link to /methodology
            "mae_pct": 11.4,
            "n_sales": 1270,
            "label": f"mean absolute error across our published backtest, against 1,270 actual Gold Coast sales. The methodology is at fieldsestate.com.au/methodology.",
        },
        "caption": (
            f"Source: Fields valuation engine · subject {_format_suburbs(catchment)} catchment · "
            f"valuation_data.comparables (n_total={len(valued)}, n_shown={min(top_n, len(valued))}) · "
            f"{as_at} · methodology at fieldsestate.com.au/methodology"
        ),
        "substantiation_record": {
            "section": "03_receipts",
            "subject_id": str(subject["_id"]),
            "subject_address": subject.get("complete_address"),
            "n_comps_total": len(valued),
            "n_comps_shown": min(top_n, len(valued)),
            "rest_weight_pct": rest_weight_pct,
            "as_at_date": datetime.now(timezone.utc).isoformat(),
            "valid_until": (datetime.now(timezone.utc) + timedelta(days=7)).isoformat(),
            "framework_version": "2026-05-15",
        },
    }


def section_recommendation(
    subject_id: str,
    pipeline_record: dict | None = None,
    *,
    page_number: int = 11,
) -> dict:
    """Page 11 (mid-document) and Page 18 (final synthesis) recommendation
    block. Both pages share the same data shape — listing price, target sale
    price range, derived range, gap dollars, and the four conditions of the
    precise-pricing protocol. Page 18 is the synthesis recap.

    Inputs come from either:
        - pipeline_record.recommendation (preferred — analyst-confirmed values)
        - subject.valuation_data.confidence.range (fallback — model output)
    """
    subject = get_subject(subject_id)
    pipeline_record = pipeline_record or {}
    rec = pipeline_record.get("recommendation") or {}

    # Local short-address helper (avoid circular import with render.py)
    addr = subject.get("street_address") or subject.get("complete_address") or ""
    short_addr = addr.title() if addr.isupper() else addr

    def _to_int(v):
        if v is None: return None
        if isinstance(v, (int, float)): return int(v)
        if isinstance(v, str):
            import re
            m = re.search(r'(\d[\d,]*)', v.replace("$", ""))
            return int(m.group(1).replace(",", "")) if m else None
        return None

    listing_price = _to_int(rec.get("listing_price"))
    target_sale_price = _to_int(rec.get("target_sale_price"))
    derived_low = _to_int(rec.get("derived_range_low"))
    derived_high = _to_int(rec.get("derived_range_high"))
    gap = _to_int(rec.get("gap_dollars"))

    # Fall back to valuation_data if pipeline_record is missing values
    val = subject.get("valuation_data") or {}
    conf = val.get("confidence") or {}
    rng = conf.get("range") or {}
    if derived_low is None:
        derived_low = _to_int(rng.get("low"))
    if derived_high is None:
        derived_high = _to_int(rng.get("high"))

    # Auto-derive target_sale_price range if only midpoint provided
    target_low, target_high = None, None
    if target_sale_price:
        target_low = target_sale_price
        # If derived_high > target_sale_price, use derived_high; else add ~3%
        target_high = derived_high if (derived_high and derived_high > target_sale_price) else int(target_sale_price * 1.025)

    # Pending until the analyst sets listing_price + target_sale_price via the
    # Appraisal Pipeline panel. Both prices are analyst-set (not engine-derived)
    # because the recommendation reflects market judgement on top of the
    # valuation range.
    pending_review = not (listing_price and target_low)

    return {
        "pending_review": pending_review,
        "headline_html": f'Our recommendation for <span class="copper">{short_addr or "this home"}</span>.',
        "subhead": "Built from the derived range. Refined for buyer behaviour." if page_number == 11
                    else "Six forces, one strategy, one specific recommendation.",
        "listing_price": listing_price,
        "target_sale_price_low": target_low,
        "target_sale_price_high": target_high,
        "derived_range_low": derived_low,
        "derived_range_high": derived_high,
        "gap_dollars": gap,
        "page_number": page_number,
        "campaign_duration_days": "25 – 45",
        "estimated_inspections": "30 – 45",
        "substantiation_record": {
            "section": f"recommendation_p{page_number}",
            "subject_id": str(subject["_id"]),
            "subject_address": subject.get("complete_address"),
            "listing_price": listing_price,
            "target_sale_price": target_sale_price,
            "derived_range": {"low": derived_low, "high": derived_high},
            "from_pipeline": bool(rec),
            "as_at_date": datetime.now(timezone.utc).isoformat(),
            "framework_version": "2026-05-15",
        },
    }


def section_04_right(subject_id: str, catchment: list[str] | None = None) -> dict:
    """§04 right — "Active buyers find listings. Passive buyers we find for you."
    Three reach modes + 28-day campaign model stat block."""
    subject = get_subject(subject_id)
    catchment = catchment or catchment_for(subject)
    as_at = datetime.now(timezone.utc).strftime("%-d %B %Y")
    return {
        "headline_html": 'Active buyers find listings. <span class="copper">Passive buyers we find for you.</span>',
        "subhead": "Reach is built from the buyer avatar in Section 02, not a generic channel list.",
        "modes": [
            {"num": "01", "label": "Active buyer", "desc": "Searching for a home like yours today. They will find your listing on a portal — Fields makes sure your listing competes for their attention there.", "channels": "realestate.com.au · Domain · Google Search"},
            {"num": "02", "label": "Passive buyer", "desc": "Matches your home's buyer avatar — but isn't searching this week. The larger pool, and the source of price competition.", "channels": "Facebook · Instagram · YouTube · Google Display"},
            {"num": "03", "label": "Retargeting (active and passive, after engagement)", "desc": "The buyer who has already engaged — visited the listing, watched the video, read the editorial — and needs repeated exposure to convert from interest to inspection.", "channels": "Across every platform where they continue to spend attention"},
        ],
        "campaign_model": {
            "impressions_low": 40000, "impressions_high": 60000,
            "engagements_low": 75, "engagements_high": 120,
            "inspections_low": 35, "inspections_high": 50,
            "window_days": 28,
        },
        "caption": (
            f"Source: Industry campaign benchmarks validated against the last 90 days · "
            f"ABS Census 2021 catchment ({_format_suburbs(catchment)}) · "
            f"28-day campaign window · {as_at} · methodology at fieldsestate.com.au/methodology"
        ),
        "advantage_box": FIELDS_ADVANTAGE_04,
        "substantiation_record": {
            "section": "04_right",
            "subject_id": str(subject["_id"]),
            "catchment": catchment,
            "as_at_date": datetime.now(timezone.utc).isoformat(),
            "valid_until": (datetime.now(timezone.utc) + timedelta(days=7)).isoformat(),
            "framework_version": "2026-05-15",
        },
    }


def section_05_right(subject_id: str) -> dict:
    """§05 right — "Presentation turns features into desire." Photography
    contrast (standard vs Fields twilight) + +118% stat + three-row
    presentation strategy."""
    subject = get_subject(subject_id)
    return {
        "headline_html": 'Presentation turns features into <span class="copper">desire.</span>',
        "subhead": "Photography, listing copy and editorial storytelling are all calibrated to how the right buyer will experience the home.",
        "photo_contrast_stat": {
            "uplift_pct": 118,
            "label": "more online views with professional photography vs phone-grade images.",
            "source": "Before You List · Ch. 4 · Fields photography study (n=1,475 Gold Coast listings, paired comparison)",
        },
        "presentation_rows": [
            {"num": "01", "label": "The story",
             "desc": "Listing copy that places the buyer inside the home, not in front of it. Sensory, specific, calm: mornings on the rear deck, children in the pool, permanent greenery beyond, and no through-traffic in front."},
            {"num": "02", "label": "The imagery",
             "desc": "Twilight and golden-hour photography focused on the rear entertaining zone, pool, bushland boundary, kitchen-to-deck transition and quiet cul-de-sac setting. No flat midday light. No generic real-estate photography."},
            {"num": "03", "label": "The buyer emphasis",
             "desc": "The same home, three stories — one per persona from Section 02."},
        ],
        "advantage_box": FIELDS_ADVANTAGE_05,
        "substantiation_record": {
            "section": "05_right",
            "subject_id": str(subject["_id"]),
            "as_at_date": datetime.now(timezone.utc).isoformat(),
            "valid_until": (datetime.now(timezone.utc) + timedelta(days=7)).isoformat(),
            "framework_version": "2026-05-15",
        },
    }


def section_06_right(subject_id: str) -> dict:
    """§06 right — "The evidence buyers need, made visible." Three structural
    assets (price/trade-offs/method) + relationship premium stat."""
    subject = get_subject(subject_id)
    return {
        "headline_html": 'The evidence buyers need, <span class="copper">made visible.</span>',
        "subhead": "Three structural assets that reduce uncertainty — and protect the bid that comes with it.",
        "assets": [
            {"num": "01", "label": "The price, traceable",
             "desc": "Comparable sales named. Adjustments shown. The buyer can see why the price exists, not just where the agent wants it to land. No vague appeal to \"the market.\" No price built on opinion alone."},
            {"num": "02", "label": "The trade-offs, named",
             "desc": "The strengths are made clear. So are the constraints. When trade-offs are named first, the buyer does not have to go looking for hidden problems."},
            {"num": "03", "label": "The method, open",
             "desc": "Campaign reach, buyer engagement and inspection feedback are tracked and reported clearly. No invented pressure. No vague claims of interest. The negotiation is grounded in evidence, not theatre."},
        ],
        "relationship_premium_stat": {
            "uplift_pct": 9.6,
            "label": "higher sale prices in our cohort analysis of agents who invest deeply in buyer relationships — about $96,000 on a $1M home. Confidence shows up in the bid.",
            "source": "Before You List · Ch. 6 · Fields relationship-premium study (n=1,475 GC sales)",
        },
        "advantage_box": FIELDS_ADVANTAGE_06,
        "substantiation_record": {
            "section": "06_right",
            "subject_id": str(subject["_id"]),
            "as_at_date": datetime.now(timezone.utc).isoformat(),
            "valid_until": (datetime.now(timezone.utc) + timedelta(days=7)).isoformat(),
            "framework_version": "2026-05-15",
        },
    }
