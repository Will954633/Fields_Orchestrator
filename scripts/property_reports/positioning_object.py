"""
Positioning object — the single deterministic source of truth for every
positioning-flavoured surface on the mini-site (hero, selling thesis,
lead-buyer, Right-Buyer tab).

Why this exists: the page currently has 4-5 independent LLM calls each
recomputing "what kind of home is this", which produced (a) the same
feature stack recited 5-6 times and (b) outright contradictions — the hero
said "compete for it" (scarce) while the thesis said "not a feature-scarcity
play". This module computes ONE object so all surfaces agree and each renders
a distinct SLICE rather than re-pitching the whole stack.

Architecture (mirrors the proven scarcity hero pattern):
  - Python scores archetypes, selects anti-frames, splits price-vs-buyer
    drivers, derives ONE scarcity verdict, and builds the allowed/forbidden
    claim lists — all deterministic.
  - Because each mini-site is seen by exactly one reader (their own home),
    templated rendering is fine and desirable: the rendered thesis slices
    here are deterministic templates, not LLM output. An optional LLM polish
    can be layered later, but the default is QC-able and reproducible.

Key correctness rules baked in:
  1. ONE scarcity_verdict (reuses scarcity_narrative._is_scarce) — every
     surface obeys it, killing the hero/thesis contradiction.
  2. "school-zone" is ALWAYS forbidden (we have walk distance, not verified
     catchment) — surfaces must say "X-metre walk to <school>".
  3. price_drivers (what carries $/sqm) are kept SEPARATE from buyer_drivers
     (what attracts the buyer). Per positioning playbook v5.0, a pool does
     not drive $/sqm — it attracts the buyer. Surfaces must not conflate them.
  4. Anti-frames are SELECTED by truth + relevance (a genuine misread risk
     with disqualifying evidence), never enumerated. We never assert a
     negative that contradicts the scarcity verdict.

Output: see resolve_positioning_object() docstring.
"""
from __future__ import annotations

import logging
from typing import Any, Dict, List, Optional

from pymongo.database import Database

from scripts.property_reports.scarcity_features import resolve_scarcity_features
from scripts.property_reports.scarcity_narrative import _is_scarce, _walkable_differentiators

logger = logging.getLogger(__name__)


# --------------------------------------------------------------------------- #
# Frame vocabulary
# --------------------------------------------------------------------------- #
# Each archetype: a noun for the frame, a short "built around" lead phrase, and
# whether it's an ASSUMABLE frame (one a Gold Coast buyer might wrongly default
# to) so it can become an anti-frame when the evidence disqualifies it.
FRAMES: Dict[str, Dict[str, Any]] = {
    "school_walk_family": {
        "noun": "family home built around the walk to school",
        "lead": "the school walk and single-level family living",
        "assumable": False,
    },
    "land_lifestyle_family": {
        "noun": "land-and-lifestyle family home",
        "lead": "land, space and family living",
        "assumable": False,
    },
    "beachside_lifestyle": {
        "noun": "beachside lifestyle home",
        "lead": "beach proximity and coastal living",
        "assumable": True,
    },
    "turnkey_downsizer": {
        "noun": "low-maintenance single-level home",
        "lead": "single-level, low-maintenance living",
        "assumable": True,
    },
    "renovator_valueadd": {
        "noun": "value-add home in a strong location",
        "lead": "location and land with room to improve",
        "assumable": False,
    },
    "prestige_privacy": {
        "noun": "private, premium home",
        "lead": "land, privacy and presentation",
        "assumable": True,
    },
    "scarcity_play": {
        "noun": "hard-to-replicate combination",
        "lead": "a combination the market rarely offers",
        "assumable": True,
    },
}

# Anti-frames are their OWN catalogue (not reused archetype nouns) so the
# rejected-angle wording is always clean and never contradicts a lead feature
# (e.g. we must never tell a single-level home "not a single-level home"). Each
# fires only on disqualifying evidence, and `scarcity_play` can NEVER fire when
# the home is scarce — that's the rule that killed the hero/thesis contradiction.
# GC buyers default to "beachside" first, so it leads the order.
# Suburbs close enough to the coast that "beachside lifestyle" is a plausible
# default assumption worth explicitly disqualifying. Robina/Varsity Lakes and
# the other inland suburbs were never beachside candidates for ANY property —
# telling the reader "not beachside" there answers a question nobody asked
# (Will's feedback, 2026-07-23). Extend this list if a genuinely coastal
# suburb (Mermaid Beach, Miami, etc.) is ever added to TARGET_SUBURBS.
COASTAL_ADJACENT_SUBURBS = {"burleigh_waters", "burleigh_heads"}

ANTI_FRAMES: Dict[str, Dict[str, Any]] = {
    "beachside_lifestyle": {
        "noun": "a beachside lifestyle home",
        "test": lambda f: f["notCoastal"] and f["coastalAdjacentSuburb"],
        "reason": lambda f: f"it's {f['_beach_km']:.1f} km from the coast, so the beach isn't the draw",
    },
    "turnkey_renovation": {
        "noun": "a turnkey renovation",
        "test": lambda f: (not f["turnkey"]) and 0 < f["_reno"] < 9,
        "reason": lambda f: "it presents well but isn't a full renovation, so we won't lead on finish or price a premium the data won't defend",
    },
    "scarcity_play": {
        "noun": "a feature-scarcity play",
        "test": lambda f: f["common"] and not f["scarce"],
        "reason": lambda f: "its feature mix is well represented among active listings, so the angle is buyer-fit, not scarcity",
    },
}
ANTI_FRAME_ORDER = ["beachside_lifestyle", "turnkey_renovation", "scarcity_play"]

# Feature key -> which driver bucket. price_drivers carry $/sqm; buyer_drivers
# attract the buyer but (per playbook) do NOT drive $/sqm.
PRICE_DRIVER = {
    "land_anchor": "land",
    "floor_anchor": "internal floor area",
    "bedrooms_anchor": "bedroom count",
    "bathrooms_3plus": "bathroom count",
    "near_beach_1km": "beach proximity",
    "near_beach_2km": "beach proximity",
    "water_views": "the water outlook",
}
BUYER_DRIVER = {
    "pool": "the pool",
    "single_level": "single-level living",
    "high_quality_finish": "the finish",
}


def _num(v: Any) -> Optional[float]:
    if isinstance(v, (int, float)):
        return float(v)
    return None


def _nearest_school_walk_m(pois: List[Dict[str, Any]]) -> Optional[int]:
    best = None
    for p in pois or []:
        if str(p.get("category", "")).lower() == "school":
            m = p.get("walkMetres")
            if isinstance(m, (int, float)) and (best is None or m < best):
                best = m
    return int(best) if best is not None else None


def _compute_flags(
    fb: Dict[str, Any], scarcity: Dict[str, Any], pois: List[Dict[str, Any]],
    liquidity: Optional[Dict[str, Any]] = None, price_anchor: Optional[float] = None,
    suburb_key: Optional[str] = None,
) -> Dict[str, Any]:
    cohort = scarcity.get("cohort_stats") or {}
    land = _num(fb.get("land_size_sqm"))
    land_median = cohort.get("land_median")
    beach_km = _num(fb.get("beach_distance_km"))
    school_m = _nearest_school_walk_m(pois)
    reno = _num(fb.get("renovation_quality_score")) or 0
    matching = scarcity.get("active_matching_full_stack") or 0
    total = scarcity.get("active_listings_total") or 0
    n_diff = len(scarcity.get("differentiator_features") or []) + len(_walkable_differentiators(pois))
    scarce = _is_scarce(matching, total, n_diff, has_countable_anchors=bool(scarcity.get("anchor_features")))

    # Affordable-for-its-suburb + genuinely faster-selling — gated on real,
    # per-suburb precomputed evidence (precompute_price_tier_liquidity.py),
    # never assumed. Found 2026-07-23: true in Robina/Burleigh Waters houses
    # (~45-52% faster), flat in Varsity Lakes over the same window — so
    # `liquidity.qualifies` must be checked per suburb, not treated as a
    # universal "affordable = fast" rule. Only meaningful for a house-like
    # subject (the benchmark itself is House-only).
    affordable_fast_mover = False
    liquidity_gap_pct = None
    liquidity_lower_dom = None
    liquidity_upper_dom = None
    is_house_like = (land or 0) > 0
    if liquidity and liquidity.get("qualifies") and price_anchor and is_house_like:
        lower_tier = (liquidity.get("tiers") or {}).get("lower") or {}
        lower_max = lower_tier.get("max_price")
        if lower_max and price_anchor <= lower_max:
            affordable_fast_mover = True
            liquidity_gap_pct = liquidity.get("gap_pct")
            liquidity_lower_dom = lower_tier.get("median_dom")
            liquidity_upper_dom = ((liquidity.get("tiers") or {}).get("upper") or {}).get("median_dom")

    return {
        "veryStrongSchoolWalk": school_m is not None and school_m <= 500,
        "schoolWalkAdvantage": school_m is not None and school_m <= 800,
        "nearBeach": beach_km is not None and beach_km <= 1.5,
        "beachAdjacent": beach_km is not None and 1.5 < beach_km <= 3.0,
        "notCoastal": beach_km is not None and beach_km > 3.5,
        "familyScale": (fb.get("bedrooms") or 0) >= 4 and land is not None
                       and (land_median is None or land >= land_median),
        "largeLand": land is not None and land_median is not None and land >= land_median * 1.12,
        "singleLevel": (fb.get("number_of_stories") or 0) == 1 and (land or 0) >= 200,
        "pool": bool(fb.get("pool_present")),
        "waterViews": bool(fb.get("water_views")),
        "turnkey": reno >= 9,
        "dated": 0 < reno <= 4,
        "scarce": scarce,
        "common": total > 0 and (matching / total) > 0.25,
        "affordableFastMover": affordable_fast_mover,
        "coastalAdjacentSuburb": (suburb_key or "").lower() in COASTAL_ADJACENT_SUBURBS,
        # raw values for evidence strings
        "_beach_km": beach_km,
        "_school_m": school_m,
        "_reno": reno,
        "_liquidity_gap_pct": liquidity_gap_pct,
        "_liquidity_lower_dom": liquidity_lower_dom,
        "_liquidity_upper_dom": liquidity_upper_dom,
    }


def _score(flag: bool, weight: int) -> int:
    return weight if flag else 0


def _score_archetypes(f: Dict[str, Any]) -> Dict[str, int]:
    return {
        "school_walk_family":
            _score(f["veryStrongSchoolWalk"], 3) + _score(f["schoolWalkAdvantage"], 1)
            + _score(f["familyScale"], 2) + _score(f["singleLevel"], 1) + _score(f["pool"], 1),
        "land_lifestyle_family":
            _score(f["familyScale"], 2) + _score(f["largeLand"], 2)
            + _score(f["pool"], 2) + _score(f["singleLevel"], 1),
        "beachside_lifestyle":
            _score(f["nearBeach"], 4) + _score(f["beachAdjacent"], 2) + _score(f["waterViews"], 2),
        "turnkey_downsizer":
            _score(f["singleLevel"], 2) + _score(f["turnkey"], 3),
        "renovator_valueadd":
            _score(f["dated"], 3) + _score(f["largeLand"], 1),
        "prestige_privacy":
            _score(f["largeLand"], 2) + _score(f["turnkey"], 1) + _score(f["waterViews"], 1),
        "scarcity_play":
            _score(f["scarce"], 4) - _score(f["common"], 3) + _score(f["waterViews"], 1),
        # value_liquidity_play deliberately excluded from the frame competition
        # (2026-07-23, Will's feedback): "sells fast because it's affordably
        # priced" is a market-DEMAND fact, not a seller-positioning STRATEGY —
        # it was winning "primary_frame" and producing a "how we'd position
        # it" headline that wasn't actually about positioning. affordableFastMover
        # and its evidence are still computed and exposed (see `evidence.liquidity`
        # below) for use as a comfort/demand note elsewhere, just never as a frame.
    }


def _select_anti_frames(f: Dict[str, Any]) -> List[Dict[str, str]]:
    """Pick up to two assumable angles a buyer might wrongly default to, that
    this home clearly is NOT, each with disqualifying evidence. Selected by
    truth + relevance, never enumerated; capped at two so it reads as a
    deliberate 'what we wouldn't claim', not a form letter."""
    out: List[Dict[str, str]] = []
    for key in ANTI_FRAME_ORDER:
        spec = ANTI_FRAMES[key]
        try:
            if spec["test"](f):
                out.append({"frame": key, "noun": spec["noun"], "reason": spec["reason"](f)})
        except Exception as e:
            logger.debug(f"  anti-frame {key} test threw: {e}")
        if len(out) >= 2:
            break
    return out


def _split_drivers(scarcity: Dict[str, Any], pois: List[Dict[str, Any]]) -> Dict[str, List[str]]:
    anchors = scarcity.get("anchor_features") or []
    diffs = scarcity.get("differentiator_features") or []
    price: List[str] = []
    buyer: List[str] = []
    for a in anchors:
        label = PRICE_DRIVER.get(a["key"]) or BUYER_DRIVER.get(a["key"])
        if not label:
            continue
        (price if a["key"] in PRICE_DRIVER else buyer).append(label)
    for d in diffs:
        label = BUYER_DRIVER.get(d["key"])
        if label:
            buyer.append(label)
    # walkable POIs are buyer drivers
    for w in _walkable_differentiators(pois):
        buyer.append(w)
    # de-dupe preserving order
    def _dedupe(xs):
        seen = set(); out = []
        for x in xs:
            if x not in seen:
                seen.add(x); out.append(x)
        return out
    return {"price": _dedupe(price), "buyer": _dedupe(buyer)}


def _build_forbidden(f: Dict[str, Any]) -> List[str]:
    forbidden = ["school-zone", "school zone", "in the catchment", "catchment guaranteed"]
    if not (f["nearBeach"] or f["beachAdjacent"]):
        forbidden += ["coastal", "beachside", "walk to the beach", "walk to beach"]
    if not f["turnkey"]:
        forbidden += ["turnkey", "renovated throughout", "fully renovated"]
    if not f["scarce"]:
        forbidden += ["rare", "scarce", "one of only", "hard to replace", "irreplaceable"]
    # universal marketing words
    forbidden += ["stunning", "nestled", "boasting", "rare opportunity", "must-see", "dream home"]
    return forbidden


_NUM_WORDS = {1: "one", 2: "two", 3: "three", 4: "four", 5: "five", 6: "six", 7: "seven", 8: "eight"}

# Order price drivers read best in a lead line (land first, then space, then beds).
_PRICE_LEAD_ORDER = ["land", "internal floor area", "bedroom count", "bathroom count",
                     "beach proximity", "the water outlook"]


def _soft_lead_phrases(
    primary: str, drivers: Dict[str, List[str]], fb: Dict[str, Any],
    pois: List[Dict[str, Any]],
) -> List[str]:
    """Warm, abstracted lead phrases for the thesis (the precise figures live in
    the hero, so the thesis names the drivers softly): e.g. 'the land, the
    four-bedroom layout and the walk to school'."""
    beds = fb.get("bedrooms")
    bed_word = _NUM_WORDS.get(int(beds), str(int(beds))) if isinstance(beds, (int, float)) else None
    soft = {
        "land": "the land",
        "internal floor area": "the internal space",
        "bedroom count": f"the {bed_word}-bedroom layout" if bed_word else "the bedroom count",
        "bathroom count": "the bathroom count",
        "beach proximity": "the beach proximity",
        "the water outlook": "the water outlook",
    }
    # top two price drivers, in reading order
    price = sorted(drivers.get("price", []), key=lambda d: _PRICE_LEAD_ORDER.index(d)
                   if d in _PRICE_LEAD_ORDER else 99)
    lead = [soft.get(d, d) for d in price[:2]]

    # the frame's signature buyer driver, abstracted
    sig = None
    if primary == "school_walk_family":
        if any(str(p.get("category", "")).lower() == "school" for p in pois or []):
            sig = "the walk to school"
    elif primary == "turnkey_downsizer":
        sig = "single-level living"
    elif primary == "land_lifestyle_family":
        sig = "the pool" if "the pool" in drivers.get("buyer", []) else "the outdoor space"
    elif primary == "beachside_lifestyle":
        sig = "the beach proximity"
    if sig and sig not in lead:
        lead.append(sig)
    # Frames without a signature case above (scarcity_play, renovator_valueadd,
    # prestige_privacy) and with zero price drivers would otherwise return an
    # empty list here — producing "We'd lead on  — and let the right buyer..."
    # (a real bug found 2026-07-23 building the off-market deck's positioning
    # card). Prefer the home's REAL buyer drivers (concrete — a differentiator
    # or a walkable POI — beats a vague archetype description every time);
    # only fall back to the frame's own generic descriptor when the home
    # genuinely has nothing concrete to name at all.
    if not lead:
        lead = list(drivers.get("buyer", []))[:2]
    return lead or [soft.get(d, d) for d in price[:1]] or [FRAMES[primary]["lead"]]


def _join(items: List[str]) -> str:
    items = [i for i in items if i]
    if not items:
        return ""
    if len(items) == 1:
        return items[0]
    return ", ".join(items[:-1]) + " and " + items[-1]


def resolve_positioning_object(
    subject_doc: Dict[str, Any],
    db: Database,
    suburb_display: str,
    scarcity: Optional[Dict[str, Any]] = None,
    pois: Optional[List[Dict[str, Any]]] = None,
    price_anchor: Optional[float] = None,
) -> Optional[Dict[str, Any]]:
    """Compute the single positioning object for one property.

    `scarcity` and `pois` may be passed in (slot_resolver already computes
    them) to avoid recomputation; if omitted, scarcity is resolved here.

    Returns None if the home has no usable feature data. Otherwise:
    {
      "primary_frame": str, "secondary_frame": str|None,
      "frame_scores": {...},
      "anti_frames": [{"frame","noun","reason"}, ...],   # SELECTED, evidence-backed
      "stack": [str, ...],                                # canonical feature phrases
      "buyer": str,
      "drivers": {"price": [...], "buyer": [...]},        # what carries $/sqm vs attracts buyer
      "scarcity_verdict": "uncommon_combination"|"common_combination",
      "scarcity_receipt": {"matching": int, "total": int},
      "cohort_premiums": [...],                           # reliable only
      "forbidden_claims": [...],
      "render": {                                         # deterministic slices
        "thesis": {"headline","frameLine","leadLine"},
        "antiFrame": {"label","items":[{"noun","reason"}]},
        "leadBuyer": {"headline","body"},
      },
      "evidence": {...},
    }
    """
    if scarcity is None:
        scarcity = resolve_scarcity_features(subject_doc, db)
    if not scarcity or not scarcity.get("notable_features"):
        return None

    fb = scarcity.get("features_basic_snapshot") or {}
    pois = pois or []

    # Price anchor (caller-supplied override, else the engine's own
    # reconciled-range midpoint if valued) + the per-suburb precomputed
    # liquidity benchmark — both best-effort, feed the value_liquidity_play
    # frame only, everything else works unaffected if either is missing.
    # Off-market docs almost never carry a cached valuation_data range (the
    # off-market deck's own range comes from a client-side nearby-comps
    # calc instead) — offmarket_intel_poller.py passes a comps-based
    # price_anchor explicitly for that path; slot_resolver's mini-site call
    # doesn't pass one and falls back to the cached engine valuation below.
    if price_anchor is None:
        try:
            rng = ((subject_doc.get("valuation_data") or {}).get("confidence") or {}).get("range") or {}
            if rng.get("low") and rng.get("high"):
                price_anchor = (rng["low"] + rng["high"]) / 2
        except Exception:
            price_anchor = None
    liquidity = None
    suburb_key = subject_doc.get("suburb_key")
    if suburb_key:
        try:
            liquidity = db["precomputed_price_tier_liquidity"].find_one({"_id": f"{suburb_key}_House"})
        except Exception:
            liquidity = None

    flags = _compute_flags(fb, scarcity, pois, liquidity=liquidity, price_anchor=price_anchor, suburb_key=suburb_key)
    scores = _score_archetypes(flags)
    ranked = sorted(scores.items(), key=lambda kv: kv[1], reverse=True)
    primary = ranked[0][0] if ranked and ranked[0][1] > 0 else None
    if not primary:
        return None
    secondary = None
    if len(ranked) > 1 and ranked[1][1] > 0 and ranked[1][1] >= 0.5 * ranked[0][1]:
        secondary = ranked[1][0]

    anti = _select_anti_frames(flags)
    drivers = _split_drivers(scarcity, pois)
    verdict = "uncommon_combination" if flags["scarce"] else "common_combination"
    forbidden = _build_forbidden(flags)

    # canonical stack phrases (from the scarcity engine, same wording as the hero)
    anchors = scarcity.get("anchor_features") or []
    diffs = scarcity.get("differentiator_features") or []
    stack = ([d.get("phrase", d["label"]) for d in diffs]
             + [a.get("phrase", a["label"]) for a in anchors])

    buyer = "local family upgraders" if "family" in primary else "buyers who value this combination"

    # ---- deterministic render ----
    frame_noun = FRAMES[primary]["noun"]
    frame_line = f"A {suburb_display} {frame_noun}."
    lead_phrases = _soft_lead_phrases(primary, drivers, fb, pois)
    lead_line = (
        f"We'd lead on {_join(lead_phrases)} — and let the right buyer "
        f"see themselves in it."
    )
    anti_items = [{"noun": a["noun"], "reason": a["reason"]} for a in anti]

    lead_buyer_body = (
        f"They compete hardest because {_join(drivers['buyer'][:3])} is what they "
        f"can't replicate at a lower price point."
        if drivers["buyer"] else
        f"They're the cohort this combination is built for."
    )

    return {
        "primary_frame": primary,
        "secondary_frame": secondary,
        "frame_scores": scores,
        "anti_frames": anti,
        "stack": stack,
        "buyer": buyer,
        "drivers": drivers,
        "scarcity_verdict": verdict,
        "scarcity_receipt": {
            "matching": scarcity.get("active_matching_full_stack") or 0,
            "total": scarcity.get("active_listings_total") or 0,
        },
        "cohort_premiums": [
            {"feature": p["feature_label"], "premium_pct": p["premium_pct"]}
            for p in (scarcity.get("cohort_premiums") or []) if p.get("reliable")
        ],
        "forbidden_claims": forbidden,
        "render": {
            "thesis": {
                "headline": "How we'd position your home",
                "frameLine": frame_line,
                "leadLine": lead_line,
            },
            "antiFrame": {
                "label": "What we wouldn't claim",
                "items": anti_items,
            },
            "leadBuyer": {
                "headline": f"{buyer.capitalize()} carry the price",
                "body": lead_buyer_body,
            },
        },
        "evidence": {
            "beach_distance_km": flags["_beach_km"],
            "school_walk_m": flags["_school_m"],
            "renovation_score": flags["_reno"],
            "liquidity": {
                "gap_pct": flags["_liquidity_gap_pct"],
                "lower_median_dom": flags["_liquidity_lower_dom"],
                "upper_median_dom": flags["_liquidity_upper_dom"],
            } if flags.get("affordableFastMover") else None,
            "flags": {k: v for k, v in flags.items() if not k.startswith("_")},
        },
    }
