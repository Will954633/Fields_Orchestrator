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

    # Floor area — try several locations, weighted toward measured values
    floor_area = (
        _resolve_numeric(doc.get("floor_area_sqm"))
        or _resolve_numeric((pvd.get("layout") or {}).get("floor_area_sqm"))
        or _resolve_numeric(fpa.get("internal_floor_area"))
        or _resolve_numeric(house_plan.get("floor_area_sqm"))
        or _resolve_numeric(enriched.get("floor_area_sqm"))
        or _resolve_numeric(doc.get("total_floor_area"))
    )

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
        # Fallback: floor-plan analysis levels
        fpa_levels = fpa.get("levels") or {}
        if isinstance(fpa_levels, dict):
            number_of_stories = fpa_levels.get("total_levels")
        # Final fallback: house_plan number_of_levels
        if not number_of_stories:
            number_of_stories = house_plan.get("number_of_levels")

    renovation_level_raw = renovation.get("overall_renovation_level") if renovation else None
    renovation_level = RENOVATION_LEVEL_MAP.get(renovation_level_raw, 3)

    cladding_raw = exterior.get("cladding_material") if exterior else None
    cladding_level = CLADDING_MATERIAL_MAP.get(cladding_raw, 2)

    kitchen_score = kitchen.get("quality_score") if kitchen else None

    ac_type = metadata.get("air_conditioning", "") if metadata else ""
    ac_ducted = ac_type == "ducted"

    return {
        "bedrooms": bedrooms,
        "bathrooms": bathrooms,
        "car_spaces": car_spaces,
        "floor_area_sqm": floor_area,
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
