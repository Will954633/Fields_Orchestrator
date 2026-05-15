"""Buyer-persona archetypes for the §02 right page.

A persona library indexed by `catchment_tier` + `subject_class` so the
appraisal can auto-pick the right three avatars without per-appraisal
manual curation. For Phase B v1, only the southern-GC-premium tier is
populated (covers the 4 target suburbs at $1.5M+).

Each persona has:
  - id, label, share_default (used when ops UI hasn't overridden)
  - demographics (age band, income band, motivation, life stage)
  - evidence_note (ABS table or cohort reference)
  - willingness_multiplier (applied to the valuation reconciled mid)
  - feature_weights: per-attribute affinity (0.0–1.0) — used to compute
    match-bar fills

Layer-4 override path: the ops dashboard can supply a `personas` array
on the appraisal_pipeline record to fully override this library for a
specific subject (e.g. premium waterfront, atypical buyer mix).
"""

from __future__ import annotations

from typing import Any

# ---------------------------------------------------------------------------
# Persona library — southern GC premium catchment ($1.5M+)
# ---------------------------------------------------------------------------

SOUTHERN_GC_PREMIUM_PERSONAS = [
    {
        "id": "established_owner_occupier",
        "rank_label": "01 · Primary",
        "rank_class": "primary",
        "label": "Established Owner-Occupier",
        "demographics": "50–65 yrs · equity-funded buyer (retirement income, not income-led) · downsizing within the southern Gold Coast.",
        "evidence_note": "Catchment: 10,366 owned-outright dwellings and 16,190 residents aged 50–65 across POA 4226 + 4227 + 4220.",
        "share_default": 35,
        "willingness_multiplier_low": 0.95,
        "willingness_multiplier_high": 1.05,
        "feature_weights": {
            "bedrooms_high": 0.5,   # they prefer right-sized, not maximal
            "dual_living": 0.4,
            "pool": 0.7,
            "cul_de_sac": 1.0,
            "bushland_boundary": 1.0,
            "condition_high": 0.95,
            "outdoor_high": 0.8,
        },
    },
    {
        "id": "multi_generational_family",
        "rank_label": "02 · Secondary",
        "rank_class": "secondary",
        "label": "Multi-Generational Family",
        "demographics": "40–55 yrs · top-quintile combined household income (≥$156K, top 21% of catchment) · three generations consolidating under one roof.",
        "evidence_note": "Smaller raw catchment, but configuration-driven — feature-match lifts the share above raw demographics.",
        "share_default": 30,
        "willingness_multiplier_low": 1.00,
        "willingness_multiplier_high": 1.10,
        "feature_weights": {
            "bedrooms_high": 1.0,
            "dual_living": 1.0,
            "pool": 0.85,
            "cul_de_sac": 1.0,
            "bushland_boundary": 0.7,
            "condition_high": 0.85,
            "outdoor_high": 0.9,
        },
    },
    {
        "id": "relocating_high_income_family",
        "rank_label": "03 · Tertiary",
        "rank_class": "tertiary",
        "label": "Relocating High-Income Family",
        "demographics": "35–50 yrs · top-decile household income (≥$208K, top 10% of catchment) · moving to the Gold Coast from Sydney or Melbourne.",
        "evidence_note": "Inflow context: ABS Regional Population reports +9,800 interstate movers into Gold Coast LGA 2022-23; ~30% land in the southern GC catchment.",
        "share_default": 20,
        "willingness_multiplier_low": 0.93,
        "willingness_multiplier_high": 1.00,
        "feature_weights": {
            "bedrooms_high": 0.85,
            "dual_living": 0.5,
            "pool": 1.0,
            "cul_de_sac": 0.6,
            "bushland_boundary": 0.95,
            "condition_high": 0.85,
            "outdoor_high": 1.0,
        },
    },
]


# ---------------------------------------------------------------------------
# Subject-attribute → persona match-bar values
# ---------------------------------------------------------------------------


def _subject_attributes(subject: dict) -> dict[str, bool | int]:
    """Reduce the subject doc to the boolean/numeric attributes the persona
    feature_weights table references."""
    pvd = subject.get("property_valuation_data") or {}
    outdoor = pvd.get("outdoor") or {}
    meta = pvd.get("property_metadata") or {}
    overview = pvd.get("property_overview") or {}
    sat = ((subject.get("satellite_analysis") or {}).get("categories") or {})
    backs = (sat.get("adjacency") or {}).get("backs_onto") or []
    frontage = (sat.get("adjacency") or {}).get("frontage") or ""

    beds = subject.get("bedrooms") or 0
    bushland = (
        isinstance(backs, list) and any("bushland" in str(b).lower() or "reserve" in str(b).lower() for b in backs)
    )
    cul_de_sac = "cul_de_sac" in str(frontage).lower()
    return {
        "bedrooms_high": beds >= 5,
        "dual_living": bool(meta.get("has_study") and meta.get("has_home_office")),
        "pool": bool(outdoor.get("pool_present")),
        "cul_de_sac": cul_de_sac,
        "bushland_boundary": bushland,
        "condition_high": (overview.get("overall_condition_score") or 0) >= 9,
        "outdoor_high": (outdoor.get("outdoor_entertainment_score") or 0) >= 9,
    }


def _match_bars_for(persona: dict, subject_attrs: dict[str, bool | int]) -> list[dict]:
    """Build the 5-row match-bar grid for a persona, given the subject's
    actual feature values. Each row is rendered as 5 dots (full/half/empty)
    in the template — the fill count is `round(weight * 5)` when the subject
    has the feature, 0 otherwise."""
    rows = []
    feature_labels = [
        ("bedrooms_high", "Six bedrooms"),
        ("dual_living", "Dual-living"),
        ("pool", "Pool"),
        ("cul_de_sac", "Cul-de-sac"),
        ("bushland_boundary", "Bushland"),
    ]
    for key, label in feature_labels:
        weight = persona["feature_weights"].get(key, 0.5)
        if subject_attrs.get(key):
            fill = round(weight * 5)
            dots = [_dot_state(i, fill) for i in range(5)]
        else:
            # Subject doesn't have this feature → all empty
            dots = ["empty"] * 5
        rows.append({"label": label, "dots": dots})
    return rows


def _dot_state(i: int, fill: int) -> str:
    """Translate (position, fill) → 'full' | 'half' | 'empty'. fill counts
    use halves implicitly when weight rounds awkwardly."""
    if i < fill - 0.5:
        return "full"
    if i < fill:
        return "half"
    return "empty"


def _willingness_range(persona: dict, mid_value: float) -> str:
    """Format a $X.XM–$Y.YM range from the persona's multipliers and the
    reconciled valuation mid."""
    if not mid_value or mid_value <= 0:
        return ""
    low = mid_value * persona["willingness_multiplier_low"]
    high = mid_value * persona["willingness_multiplier_high"]
    return f"${low / 1_000_000:.2f}M – ${high / 1_000_000:.2f}M"


def resolve_personas(subject: dict, valuation_mid: float | None = None) -> list[dict]:
    """Return the three personas for this subject, fully populated.
    Defaults to the southern-GC-premium library; overrides via the ops UI
    pass through unchanged."""
    library = SOUTHERN_GC_PREMIUM_PERSONAS  # only tier populated for Phase B v1
    attrs = _subject_attributes(subject)
    out = []
    for p in library:
        out.append({
            "id": p["id"],
            "rank_label": p["rank_label"],
            "rank_class": p["rank_class"],
            "label": p["label"],
            "demographics": p["demographics"],
            "evidence_note": p["evidence_note"],
            "share_pct": p["share_default"],
            "match_bars": _match_bars_for(p, attrs),
            "willingness_range": _willingness_range(p, valuation_mid) if valuation_mid else "",
        })
    return out
