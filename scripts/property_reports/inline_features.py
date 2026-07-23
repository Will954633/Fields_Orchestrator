"""
Inline feature derivation for on-demand mini-site builds.

Mirrors `precompute_valuations.py:basic_features()` but stripped to the
data-shape logic only — no DB connections, no nightly-batch dependencies.
Lets the resolver chain produce a `features.basic` dict from whatever
fields a property doc already carries (scraped data, photo analysis,
floor-plan extraction, cadastral), even if `precompute_valuations.py`
hasn't run for that property.

The product target is off-market homeowners — the precompute job runs
only on the for-sale cohort, so the resolver MUST be able to produce a
features.basic on its own for the typical submission.

The returned dict is drop-in compatible with the precompute output, so
`scarcity_features.identify_notable_features()`, the positioning resolver,
the personas resolver, and the buyers resolver can all consume it
identically.

Fields populated depend on what the source doc has:
  - bedrooms/bathrooms/car_spaces/floor_area/land_size  → always when
    the cadastral + Domain scrape has been done
  - pool_present, number_of_stories, water_views, kitchen_score,
    renovation_level, cladding_level, ac_ducted  → only when
    `property_valuation_data` (GPT photo analysis) has populated them
  - renovation_quality_score → only when condition_summary is present

Returns None only when the doc lacks even basic inventory data.
"""

from __future__ import annotations

import re
from typing import Any, Dict, Optional


# Mirrored from precompute_valuations.py — needed by the rules in
# scarcity_features.py. Keep in sync if the source map changes.
RENOVATION_LEVEL_MAP = {
    "original_condition": 1,
    "needs_renovation": 1,
    "dated": 2,
    "cosmetically_updated": 3,
    "partially_renovated": 4,
    "fully_renovated": 5,
    "renovated": 5,
    "premium_renovation": 5,
}

CLADDING_MATERIAL_MAP = {
    "weatherboard": 1,
    "fibre_cement": 1,
    "brick": 2,
    "brick_veneer": 2,
    "rendered_brick": 3,
    "render": 3,
    "stone": 4,
    "natural_stone": 4,
}


def _resolve_numeric(val: Any) -> Optional[float]:
    """Best-effort numeric coercion. Returns None for non-numeric values."""
    if val is None:
        return None
    if isinstance(val, (int, float)):
        return float(val)
    if isinstance(val, str):
        try:
            return float(val.replace(",", "").strip())
        except (TypeError, ValueError):
            return None
    return None


# Minimum believable internal area (m²) for a dwelling. Below this, a value is
# almost certainly a single room dimension scraped by mistake, not floor area.
_MIN_FLOOR_AREA = 40


def resolve_floor_areas(doc: Dict[str, Any]):
    """Resolve a property's floor areas on ONE consistent definition.

    Returns (internal_living_sqm, building_area_sqm, source).

    The two are physically different and MUST NOT be conflated:
      • internal_living — habitable internal area, EXCLUDING garage / covered
        outdoor. This is what the cohort/scarcity comparison and the seller-facing
        "internal" figure should use.
      • building_area   — Domain `total_floor_area` / `house_plan.floor_area_sqm`,
        which is internal + garage (sometimes + covered patio). A DIFFERENT metric.

    Internal-living priority (most authoritative first):
      1. stated internal read off the floor plan's printed summary box
         (`internal_living_area_sqm` / `floor_plan.stated_internal_area_sqm`)
      2. floor_plan_analysis.internal_floor_area  (vision, internal-tagged)
      3. ollama_floor_plan_analysis ... internal_floor_area
      4. enriched_data.floor_area_sqm  (internal-living enrichment)
      5. legacy doc.floor_area_sqm / pvd.layout.floor_area_sqm (ambiguous, but
         historically internal more often than not)
    Building-area (`total_floor_area` then `house_plan.floor_area_sqm`) is used
    for `internal` ONLY as a last resort, tagged `building_fallback`, so a property
    is never dropped for missing floor area — but cohort math can exclude the tag.

    IMPORTANT: this logic is mirrored verbatim in
    Feilds_Website/07_Valuation_Comps/precompute_valuations.py::resolve_floor_area —
    keep the two in sync or the subject and its cohort diverge.
    """
    pvd = doc.get("property_valuation_data") or {}
    layout = pvd.get("layout") if isinstance(pvd.get("layout"), dict) else {}
    fpa = doc.get("floor_plan_analysis") if isinstance(doc.get("floor_plan_analysis"), dict) else {}
    enriched = doc.get("enriched_data") if isinstance(doc.get("enriched_data"), dict) else {}
    house_plan = doc.get("house_plan") if isinstance(doc.get("house_plan"), dict) else {}
    fp = doc.get("floor_plan") if isinstance(doc.get("floor_plan"), dict) else {}
    ofpa = doc.get("ollama_floor_plan_analysis") if isinstance(doc.get("ollama_floor_plan_analysis"), dict) else {}
    ofpa_data = ofpa.get("floor_plan_data") if isinstance(ofpa.get("floor_plan_data"), dict) else {}

    def _ofpa_internal():
        v = ofpa_data.get("internal_floor_area")
        return _resolve_numeric(v.get("value") if isinstance(v, dict) else v)

    stated = (
        _resolve_numeric(doc.get("internal_living_area_sqm"))
        or _resolve_numeric(fp.get("stated_internal_area_sqm"))
    )
    internal_candidates = [
        (stated, "stated_plan_label"),
        (_resolve_numeric(fpa.get("internal_floor_area")), "floor_plan_vision"),
        (_resolve_numeric(enriched.get("floor_area_sqm")), "enriched_internal"),
        # ollama is an OLDER vision pass and has been seen to misread the plan
        # total (e.g. 204 m² where the plan states 173) — kept as a signal but
        # ranked below the enrichment figure.
        (_ofpa_internal(), "ollama_vision"),
        (_resolve_numeric(doc.get("floor_area_sqm")), "legacy_floor_area"),
        (_resolve_numeric(layout.get("floor_area_sqm")), "legacy_layout"),
    ]
    internal_living, source = None, None
    for val, src in internal_candidates:
        if val and val >= _MIN_FLOOR_AREA:
            internal_living, source = val, src
            break

    building_area = (
        _resolve_numeric(doc.get("total_floor_area"))
        or _resolve_numeric(house_plan.get("floor_area_sqm"))
    )
    if building_area and building_area < _MIN_FLOOR_AREA:
        building_area = None

    # Physical sanity: internal-living CANNOT exceed building area (building =
    # internal + garage + covered outdoor). When a vision/enrichment figure
    # exceeds the measured building area beyond rounding tolerance, that source
    # is unreliable for THIS home — distrust it and use the building area.
    if (internal_living and building_area
            and source != "building_fallback"
            and internal_living > building_area * 1.02):
        internal_living, source = building_area, "building_fallback"

    if internal_living is None and building_area:
        # No internal-living source at all — fall back to building area so the
        # property keeps a floor-area value, but tag it so cohort math can tell.
        internal_living, source = building_area, "building_fallback"

    return internal_living, building_area, source


def derive_features_basic(doc: Dict[str, Any]) -> Optional[Dict[str, Any]]:
    """
    Build a features.basic dict from whatever the source doc has. Returns
    None only if the doc lacks BOTH bedrooms and bathrooms (i.e. truly
    cadastral-only with no scrape data ever).

    Field sources, in order of preference:
      bedrooms/bathrooms/car_spaces → top-level scrape fields
      floor_area_sqm                → top-level, then house_plan, then floor_plan_analysis
      land_size_sqm                 → cadastral lot_size_sqm, then scraped land_size_sqm
      pool_present, number_of_stories, water_views, kitchen_score,
      renovation_level, cladding_level, ac_ducted → property_valuation_data
      renovation_quality_score      → derived from condition_summary if present
    """
    if not doc:
        return None

    pvd = doc.get("property_valuation_data") or {}
    fpa = doc.get("floor_plan_analysis") or {}
    house_plan = doc.get("house_plan") if isinstance(doc.get("house_plan"), dict) else {}
    enriched = doc.get("enriched_data") or {}

    bedrooms = doc.get("bedrooms")
    bathrooms = doc.get("bathrooms")
    car_spaces = doc.get("car_spaces") or doc.get("carspaces") or doc.get("parking")

    # Floor area — resolve INTERNAL LIVING area on one consistent definition.
    floor_area, building_area, floor_area_source = resolve_floor_areas(doc)

    fpa_land = fpa.get("total_land_area")
    if isinstance(fpa_land, dict):
        fpa_land = fpa_land.get("value")
    land_size = (
        _resolve_numeric(doc.get("lot_size_sqm"))
        or _resolve_numeric(doc.get("land_size_sqm"))
        or _resolve_numeric((pvd.get("layout") or {}).get("land_size_sqm"))
        or _resolve_numeric(enriched.get("lot_size_sqm"))
        or _resolve_numeric(fpa_land)
    )

    # Sanity flip — a scraped floor_area > 500 with no land = the scrape
    # likely captured land into floor_area (a known Domain anomaly).
    if floor_area and floor_area > 500 and not land_size:
        land_size = floor_area
        floor_area = None

    # Street View signals — universal baseline asset for any address with
    # Google imagery. Populated by `inline_street_view.py`. We map the GPT-4o
    # visual findings into the same fields the precompute engine produces, so
    # the scarcity / positioning / personas / buyers chain treats them as
    # first-class inputs even when the property has never been listed.
    sv_cats = ((doc.get("street_view_analysis") or {}).get("categories")) or {}
    sv_dwelling = sv_cats.get("dwelling") or {}
    sv_parking = sv_cats.get("parking") or {}
    sv_exterior = sv_cats.get("exterior") or {}

    # Visual-inference estimated_bedrooms — only use when the doc has no
    # measured value. Format on doc is "3-bed" | "4-bed" | "5+ bed" | "unknown".
    if bedrooms is None:
        est = (sv_dwelling.get("estimated_bedrooms") or "").lower()
        m = re.match(r"(\d+)", est)
        if m:
            try:
                bedrooms = int(m.group(1))
            except ValueError:
                pass

    # If we have literally nothing useful, bail.
    if bedrooms is None and bathrooms is None and not land_size and not floor_area:
        return None

    # PVD-derived features (photo analysis output). Default to safe values
    # when the GPT pass hasn't run for this property — these rules just
    # won't fire in scarcity_features.
    outdoor = pvd.get("outdoor") or {}
    overview = pvd.get("property_overview") or {}
    exterior = pvd.get("exterior") or {}
    kitchen = pvd.get("kitchen") or {}
    renovation = pvd.get("renovation") or {}
    metadata = pvd.get("property_metadata") or {}

    pool_present = bool(outdoor.get("pool_present")) if outdoor else False
    water_views = bool(outdoor.get("water_views")) if outdoor else False

    # Aerial signals — corroborate / fill in when the photo pass missed them.
    sa = doc.get("satellite_analysis") or {}
    sa_cats = sa.get("categories") or {}
    amenity = sa_cats.get("amenity_premiums") or {}
    if amenity.get("pool_visible"):
        pool_present = True
    water_prox = amenity.get("water_proximity") or "none"
    if water_prox in ("ocean_view", "canal_front", "lake_front", "river_front"):
        water_views = True

    number_of_stories = overview.get("number_of_stories") if overview else None
    if not number_of_stories:
        # Photo-analysis structural section (GPT-4 vision). The editorial /
        # valuation vision pipeline writes stories to pvd.structural, NOT to
        # pvd.property_overview — so for most listed properties this is where it
        # actually lives. Reading only property_overview stranded stories on
        # ~9,600 core-suburb docs (measured 2026-07-23), which silently
        # suppressed the single_level differentiator and, for otherwise-average
        # homes, left the scarcity/positioning cards empty (54 Heights Drive).
        structural = pvd.get("structural") if isinstance(pvd.get("structural"), dict) else {}
        number_of_stories = structural.get("number_of_stories")
    if not number_of_stories:
        # Fallback: floor-plan analysis levels
        fpa_levels = fpa.get("levels") or {}
        if isinstance(fpa_levels, dict):
            number_of_stories = fpa_levels.get("total_levels")
        # Final fallback: house_plan number_of_levels
        if not number_of_stories:
            number_of_stories = house_plan.get("number_of_levels")
        # Street View kerb inference — last fallback for Tier-3 (no listing)
        if not number_of_stories:
            sv_storeys = sv_dwelling.get("storeys")
            if isinstance(sv_storeys, int) and 1 <= sv_storeys <= 4:
                number_of_stories = sv_storeys

    renovation_level_raw = renovation.get("overall_renovation_level") if renovation else None
    renovation_level = RENOVATION_LEVEL_MAP.get(renovation_level_raw, None)
    if renovation_level is None:
        # Street View condition_impression as fallback
        sv_condition = (sv_dwelling.get("condition_impression") or "").lower()
        sv_condition_to_level = {
            "recently_renovated": 5,
            "well_maintained": 4,
            "dated_but_sound": 3,
            "needs_cosmetic_work": 2,
            "needs_major_work": 1,
        }
        renovation_level = sv_condition_to_level.get(sv_condition, 3)
        if not renovation_level_raw and sv_condition in sv_condition_to_level:
            renovation_level_raw = sv_condition

    cladding_raw = exterior.get("cladding_material") if exterior else None
    cladding_level = CLADDING_MATERIAL_MAP.get(cladding_raw, None)
    if cladding_level is None:
        # Street View cladding fallback. Note the field name on SV is
        # `primary_cladding` and values use underscores (e.g. "rendered").
        sv_cladding = (sv_exterior.get("primary_cladding") or "").lower()
        sv_cladding_to_level = {
            "weatherboard": 1, "hardiplank_fibro": 1,
            "brick": 2, "mixed": 2,
            "rendered": 3,
            "stone": 4,
        }
        cladding_level = sv_cladding_to_level.get(sv_cladding, 2)
        if not cladding_raw and sv_cladding in sv_cladding_to_level:
            cladding_raw = sv_cladding

    # Car spaces — derive from Street View garage when no scraped value
    if not car_spaces:
        sv_garage = (sv_parking.get("garage") or "").lower()
        sv_garage_to_spaces = {
            "triple_attached": 3,
            "double_attached": 2,
            "single_attached": 1,
            "carport": 1,
            "none_visible": 0,
        }
        if sv_garage in sv_garage_to_spaces:
            car_spaces = sv_garage_to_spaces[sv_garage]

    kitchen_score = kitchen.get("quality_score") if kitchen else None

    ac_type = metadata.get("air_conditioning", "") if metadata else ""
    ac_ducted = ac_type == "ducted"

    return {
        "bedrooms": bedrooms,
        "bathrooms": bathrooms,
        "car_spaces": car_spaces,
        "floor_area_sqm": floor_area,
        "building_area_sqm": building_area,
        "floor_area_source": floor_area_source,
        "land_size_sqm": land_size,
        "pool_present": pool_present,
        "number_of_stories": number_of_stories,
        "renovation_level": renovation_level,
        "renovation_level_raw": renovation_level_raw,
        "water_views": water_views,
        "cladding_level": cladding_level,
        "cladding_raw": cladding_raw,
        "kitchen_score": kitchen_score,
        "ac_ducted": ac_ducted,
        # Quality score depends on condition_summary which is only present
        # post-photo-analysis. None is fine — only the "premium finish"
        # rule reads it.
        "renovation_quality_score": None,
    }
