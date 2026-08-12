"""Truthful location facts for appraisal claims.

WHY THIS MODULE EXISTS
----------------------
On 2026-08-13 two sample reports made two false claims about real homes:
5 Chantilly Place was described as having "a permanent bushland boundary"
(it adjoins a golf course, 71 m away) and 16 Cheltenham Drive as having "a
cul-de-sac head position" (it faces Cheltenham Drive, a main road). Both
claims came from `pick_highlight.py` and `personas.py` reading raw GPT
vision enums off `satellite_analysis.categories.*` via substring match:

    bushland = "bushland" in backs_onto or "bushland" in green_space_proximity
    cul_de_sac = "cul_de_sac" in frontage

Three separate defects in that:

1. `green_space_proximity` is a PROXIMITY field. The value "bushland_adjacent"
   was being read as a BOUNDARY claim, so a home whose own `backs_onto` said
   `["residential_only"]` was still described as backing onto bushland. The
   report contradicted its own source field.
2. The vision categories are one un-versioned GPT call with no confidence
   score. `config/canonical_attributes.yaml` scores `gpt_satellite` at 0.70,
   the lowest non-degenerate tier — and neither caller consulted it.
3. `osm_location_features.road_classification.is_cul_de_sac` was sitting on
   the same document, said `false` for both homes, and was never read.

The V3 /off-market page never used vision for any of this, which is why it
never made these mistakes. This module ports its evidence standard:

  * cul-de-sac      -> OSM road classification, authoritative, no inference
  * green boundary  -> green_space.classify(): a NAMED OSM feature plus a
                       MEASURED edge distance in metres plus a threshold

RULES ENCODED HERE — do not loosen without re-reading the incident above:
  - A boundary claim requires `relation` in ("backs onto", "adjoins").
    "steps from" (<=200 m) is proximity, NOT a boundary.
  - "Bushland" requires the OSM feature to actually BE bushland or a nature
    reserve. A golf course, a park and a sports field are none of those, and
    must be named for what they are.
  - A *permanent bushland boundary* additionally requires "backs onto"
    (<=25 m). Adjoining at 80 m is not a boundary.
  - Absence of evidence is never a claim. A missing field yields False, and
    the caller must omit the feature rather than assert its opposite.
"""

from __future__ import annotations

import sys
from pathlib import Path
from typing import Any

_REPO_ROOT = Path(__file__).resolve().parents[2]
_V2_DIR = _REPO_ROOT / "15_Off-Market" / "Page_Redesign_V2"

# OSM `kind` values that may honestly be called bushland. Everything else in
# green_space.CLASS ("golf course", "park", "reserve", "open space", "water"…)
# is a green boundary but is NOT bushland and must be named literally.
BUSHLAND_KINDS = {"bushland", "nature reserve"}

# Relations that constitute a BOUNDARY rather than mere proximity.
BOUNDARY_RELATIONS = ("backs onto", "adjoins")


def _green_space():
    """Import the V3 green-space classifier lazily.

    Kept lazy because it loads a ~4 MB OSM polygon cache and builds a spatial
    hash on first use; an appraisal that never asks about boundaries should
    not pay for it.
    """
    if str(_V2_DIR) not in sys.path:
        sys.path.insert(0, str(_V2_DIR))
    import green_space  # type: ignore
    return green_space


def _dig(doc: dict, path: str) -> Any:
    cur: Any = doc
    for key in path.split("."):
        if not isinstance(cur, dict):
            return None
        cur = cur.get(key)
    return cur


def resolve(subject: dict) -> dict:
    """Return verified location facts for a subject property.

    Keys:
        cul_de_sac        bool  — OSM only. False when unknown.
        faces_major_road  bool
        corner_lot        bool
        boundary          dict|None — {name, kind, relation, edge_m} for the
                          nearest PREMIUM feature, only when it qualifies as a
                          boundary. None otherwise.
        detractor         dict|None — same shape, nearest negative feature.
        bushland_boundary bool  — kind is genuinely bushland/nature reserve AND
                          relation is "backs onto".
        green_boundary    bool  — any qualifying premium boundary.
    """
    road = _dig(subject, "osm_location_features.road_classification") or {}

    facts: dict[str, Any] = {
        # Strict identity, not truthiness: a missing field must not become a
        # claim, and `is_cul_de_sac` is the only field permitted to assert this.
        "cul_de_sac": road.get("is_cul_de_sac") is True,
        "faces_major_road": road.get("faces_major_road") is True,
        "corner_lot": road.get("is_corner_lot") is True,
        "boundary": None,
        "detractor": None,
        "bushland_boundary": False,
        "green_boundary": False,
    }

    lat = subject.get("LATITUDE") or subject.get("latitude")
    lon = subject.get("LONGITUDE") or subject.get("longitude")
    if lat is None or lon is None:
        return facts

    try:
        found = _green_space().classify(lat, lon) or {}
    except Exception:
        # No cache, no network, malformed geometry — all mean "we cannot
        # substantiate a boundary", which is silence, not a negative claim.
        return facts

    premium = found.get("premium")
    if premium and premium.get("relation") in BOUNDARY_RELATIONS:
        facts["boundary"] = premium
        facts["green_boundary"] = True
        facts["bushland_boundary"] = (
            premium.get("kind") in BUSHLAND_KINDS
            and premium.get("relation") == "backs onto"
        )

    detractor = found.get("detractor")
    if detractor and detractor.get("relation") in ("backs onto", "close to"):
        facts["detractor"] = detractor

    return facts


def boundary_phrase(facts: dict) -> str | None:
    """Human phrase for the boundary, naming the feature for what it is.

    "backs onto Belmore Close Reserve" / "adjoins Palmer Gold Coast golf club".
    Returns None when there is nothing substantiated to say.
    """
    boundary = facts.get("boundary")
    if not boundary:
        return None
    name = (boundary.get("name") or "").strip()
    relation = boundary.get("relation")
    if not name:
        return f"{relation} {boundary.get('kind') or 'open space'}"
    return f"{relation} {name}"


def boundary_label(facts: dict) -> str | None:
    """Short label for a feature chip — the KIND, never a guess.

    Returns e.g. "Bushland", "Golf course", "Park". None when unsubstantiated.
    """
    boundary = facts.get("boundary")
    if not boundary:
        return None
    kind = (boundary.get("kind") or "").strip()
    return kind[:1].upper() + kind[1:] if kind else None
