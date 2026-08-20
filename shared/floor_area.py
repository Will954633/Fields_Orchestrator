"""shared/floor_area.py — one resolver for internal living area, used everywhere.

[FLOOR-AREA-TOTAL-AS-INTERNAL], 2026-08-20. Three different quantities were being
stored under two field names and consumed under a third meaning:

  * internal living area (Domain / onthehouse / vision "internal")
  * "total_floor_area" = parse_room_dimensions.py's SUM of every room that happens
    to carry dimensions — which for 93 Burleigh St summed the covered alfresco
    (8.0x3.5) and the double carport (6.2x5.7) and produced 331 against a true
    internal of 220
  * building footprint incl. garage / covered outdoor

`enrich_properties_for_sale.py:get_floor_area()` silently degraded internal -> total
-> that room-sum, and `generate_suburb_statistics.py` built its percentile SCALE from
the room-sum while subjects came from the (mostly internal) enriched field. Only ~10%
of listings ended up measured on the same quantity as the scale they were ranked
against, and 9 live listings published a carport-and-alfresco total as "internal".

This module is the fix: ONE resolver that returns only explicitly-internal figures,
returns None rather than substituting a total, and flags disagreement. The writer, the
suburb-statistics builder and the editorial prompt all call it, so the subject value
and the scale can never again be different quantities.

Rule 7b applied to reads: "no internal measurement" must be distinguishable from "here
is a number" — hence the (value, source, conflict) triple and the None return.
"""

from typing import Optional, Tuple

# Internal-area sources in descending trust. Each entry is (dotted_path, label).
# All of these are *internal living area* by definition — none is a building total.
_INTERNAL_SOURCES = [
    ("floor_plan_analysis.internal_floor_area.value", "floor_plan_internal"),
    ("ollama_floor_plan_analysis.floor_plan_data.internal_floor_area.value", "ollama_floor_plan_internal"),
    ("processing_status.internal_floor_area_sqm", "photo_analysis_internal"),
    ("scraped_data_v2.internal_area_sqm", "domain_internal"),
    ("onthehouse_data.floor_area_sqm", "onthehouse_internal"),
]

# Building-total sources (kept separate, never returned as "internal").
_BUILDING_SOURCES = [
    ("floor_plan_analysis.total_floor_area.value", "floor_plan_total"),
    ("ollama_floor_plan_analysis.floor_plan_data.total_floor_area.value", "ollama_floor_plan_total"),
    ("processing_status.total_floor_area_sqm", "photo_analysis_total"),
    ("total_floor_area", "room_dimension_sum"),
]

# Two internal sources that disagree by more than this fraction => flag as conflict.
_CONFLICT_FRACTION = 0.15


def _dig(doc: dict, dotted: str):
    cur = doc
    for part in dotted.split("."):
        if not isinstance(cur, dict):
            return None
        cur = cur.get(part)
        if cur is None:
            return None
    return cur


def _as_float(v):
    try:
        f = float(v)
        return f if f > 0 else None
    except (TypeError, ValueError):
        return None


def resolve_internal_floor_area(doc: dict) -> Tuple[Optional[float], Optional[str], bool]:
    """Return (value, source, conflict) for INTERNAL living area only.

    * value:    best internal figure in m², or None if no internal source exists.
    * source:   label of the source used (see _INTERNAL_SOURCES), or None.
    * conflict: True when two internal sources disagree by > _CONFLICT_FRACTION —
                the caller should decline to assert a precise figure.

    Never returns a building total or a room-dimension sum. If you want the total,
    call resolve_building_area().
    """
    candidates = []  # (value, source) best-first
    for path, label in _INTERNAL_SOURCES:
        v = _as_float(_dig(doc, path))
        if v is not None:
            candidates.append((v, label))

    if not candidates:
        return (None, None, False)

    best, source = candidates[0]
    conflict = any(
        other is not None and abs(best - other) / max(best, other) > _CONFLICT_FRACTION
        for other, _ in candidates[1:]
    )
    return (best, source, conflict)


def resolve_building_area(doc: dict) -> Tuple[Optional[float], Optional[str]]:
    """Return (value, source) for the building/total area, or (None, None).

    This is the sum-including-outbuildings quantity. It is a legitimate figure to
    STORE (e.g. as building_area_sqm) but must never be presented to a reader as
    internal living area.
    """
    for path, label in _BUILDING_SOURCES:
        v = _as_float(_dig(doc, path))
        if v is not None:
            return (v, label)
    return (None, None)
