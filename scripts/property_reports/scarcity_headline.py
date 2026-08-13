"""
scarcity_headline.py — deterministic scarcity hero, no LLM.

Produces the three strings the Opus `scarcity_narrative` used to write:
`headline` (the combination sentence), `combinatorialMatch` (the count receipt)
and `walkingDistanceMonopoly`. Same output shape, so `slot_resolver` and the
frontend consume it unchanged.

Deterministic on purpose. The model was not composing here — it was ORDERING
and JOINING fragments that `scarcity_features.py` had already written:
`FEATURE_RULES` stores a finished `phrase` per feature ("813 m² of land",
"a pool", "single-level living"), and `scarcity_narrative._format_inputs`
handed the model the whole stack pre-assembled, with the sentence frame
dictated word-for-word in the system prompt and the closing line already
selected in Python. What remained was string work, so it is done as string work.

Templating also makes the editorial rules structural rather than hoped-for:
  - every figure is copied from the resolver, never re-derived or rounded
  - only phrases the resolver actually produced can appear — nothing invented
  - the K-of-N receipt can only ever describe the COUNTED anchors, which is the
    distinction the prompt had to spend a paragraph defending and the LLM still
    got wrong (positioning_narrative.py:161 still carries the older over-claim)
  - forbidden marketing words cannot occur; none are in the vocabulary

Variants: scarce | common. Returns None when the stack is too thin to make a
combination claim, matching the LLM path's own guard.
"""
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

# Fixed closing sentences — identical to scarcity_narrative.CLOSE_SCARCE /
# CLOSE_COMMON, which were already selected deterministically there.
CLOSE_SCARCE = (
    "Our job is to find the buyer who values that combination most — "
    "then give them enough confidence to compete for it."
)
CLOSE_COMMON = (
    "Our job is to find the buyer who values that combination most and "
    "present it so they recognise what they are looking at."
)

# Most features are named in sentence 1 generically ("not just the pool"). The
# phrase itself is too concrete for that clause, so each anchor carries a short
# generic form. Anything without an entry falls back to its phrase.
_GENERIC = {
    "pool":            lambda f: "the pool",
    "land_anchor":     lambda f: "the land",
    "floor_anchor":    lambda f: "the floor area",
    "bathrooms_3plus": lambda f: "the bathrooms",
    "water_views":     lambda f: "the water views",
    "near_beach_1km":  lambda f: "the beach proximity",
    "near_beach_2km":  lambda f: "the beach proximity",
    # Bedrooms read better with the number: "not just the four bedrooms".
    "bedrooms_anchor": lambda f: f"the {_words(f.get('phrase',''))}",
}

# Which anchors are the most mainstream — i.e. the ones a buyer screens on and
# therefore the honest subject of "not just ...". Ordered by preference.
_MAINSTREAM_ORDER = ("pool", "bedrooms_anchor", "land_anchor", "floor_anchor",
                     "bathrooms_3plus", "water_views", "near_beach_1km", "near_beach_2km")

_NUMBER_WORDS = {1: "one", 2: "two", 3: "three", 4: "four", 5: "five",
                 6: "six", 7: "seven", 8: "eight", 9: "nine", 10: "ten"}

# Cap per the original spec: at most 5 features in the combination.
_MAX_COMBINATION = 5
# walkingDistanceMonopoly only fires for a school or beach inside this radius.
_MONOPOLY_CEILING_M = 800
_MONOPOLY_CATEGORIES = {"school", "beach"}


def _words(phrase: str) -> str:
    """'4 bedrooms' -> 'four bedrooms'. Leaves anything unexpected alone."""
    parts = (phrase or "").split(" ", 1)
    if len(parts) == 2 and parts[0].isdigit():
        n = int(parts[0])
        if n in _NUMBER_WORDS:
            return f"{_NUMBER_WORDS[n]} {parts[1]}"
    return phrase or ""


def _article(n: int) -> str:
    """'a' or 'an' for a spoken number: 824 -> "an eight hundred..." -> 'an';
    419 -> "a four hundred..." -> 'a'. Only 8-, 11- and 18-leading numbers take
    'an'. Without this the templates emitted "a 824-metre walk"."""
    s = str(int(n))
    if s.startswith("8"):
        return "an"
    if len(s) >= 2 and s[:2] in ("11", "18"):
        return "an"
    return "a"


def _join(items: List[str], conj: str = "and") -> str:
    items = [i for i in items if i]
    if not items:
        return ""
    if len(items) == 1:
        return items[0]
    if len(items) == 2:
        return f"{items[0]} {conj} {items[1]}"
    return ", ".join(items[:-1]) + f" {conj} {items[-1]}"


def _generic_name(f: Dict[str, Any]) -> str:
    fn = _GENERIC.get(f.get("key"))
    return fn(f) if fn else (f.get("phrase") or f.get("label") or "")


def _not_just_clause(anchors: List[Dict[str, Any]]) -> str:
    """Name ONE or TWO anchors generically, most mainstream first."""
    ranked = sorted(
        anchors,
        key=lambda f: _MAINSTREAM_ORDER.index(f["key"])
        if f.get("key") in _MAINSTREAM_ORDER else len(_MAINSTREAM_ORDER),
    )
    names = [_generic_name(f) for f in ranked[:2]]
    return _join([n for n in names if n], conj="or")


# Within the anchors, the combination should keep the DISTINCTIVE ones when the
# 5-feature cap bites. A pool or water views separate a home; a floor-area figure
# rarely does. Without this the cap silently dropped "a pool" from a stack whose
# own opening line said "not just the pool".
_ANCHOR_INTEREST = ("pool", "water_views", "near_beach_1km", "near_beach_2km",
                    "land_anchor", "bedrooms_anchor", "floor_anchor", "bathrooms_3plus")


def _combination_phrases(anchors, differentiators, walk_phrases) -> List[str]:
    """Differentiators lead, then walkables, then the anchors most likely to
    distinguish the home — the ordering the prompt specified and
    positioning_object.py already uses."""
    ranked_anchors = sorted(
        anchors,
        key=lambda f: _ANCHOR_INTEREST.index(f["key"])
        if f.get("key") in _ANCHOR_INTEREST else len(_ANCHOR_INTEREST),
    )
    out = [d.get("phrase") or d.get("label") for d in differentiators]
    out += list(walk_phrases or [])
    out += [a.get("phrase") or a.get("label") for a in ranked_anchors]
    return [p for p in out if p][:_MAX_COMBINATION]


def _counted_anchor_names(anchors: List[Dict[str, Any]]) -> str:
    """Describe ONLY the counted anchors, for the K-of-N receipt. These are the
    features the active-listing query actually filtered on — the differentiators
    are deliberately excluded, because they are not in the count."""
    return _join([a.get("phrase") or a.get("label") for a in anchors])


def _monopoly(pois: List[Dict[str, Any]], suburb: str) -> str:
    best = None
    for p in pois or []:
        cat = (p.get("category") or "").lower()
        m = p.get("walkMetres")
        if cat in _MONOPOLY_CATEGORIES and isinstance(m, (int, float)) and m <= _MONOPOLY_CEILING_M:
            if best is None or m < best["walkMetres"]:
                best = p
    if not best:
        return ""
    return (f"{int(best['walkMetres'])} metres walking to {best['name']} — "
            f"closer than the typical {suburb} home.")


def resolve_scarcity_headline(
    scarcity_features: Dict[str, Any],
    pois: Optional[List[Dict[str, Any]]] = None,
    suburb: str = "",
    address: str = "",
    is_scarce: Optional[bool] = None,
) -> Optional[Dict[str, Any]]:
    """Return the scarcity hero object, or None when the stack is too thin.

    Output keys match the LLM path exactly so slot_resolver is unchanged:
    headline, closingLine, combinatorialMatch, walkingDistanceMonopoly.
    """
    sf = scarcity_features or {}
    anchors = [f for f in (sf.get("anchor_features") or []) if f.get("phrase") or f.get("label")]
    diffs = [f for f in (sf.get("differentiator_features") or []) if f.get("phrase") or f.get("label")]
    suburb = (suburb or "").strip() or "the suburb"

    walk_phrases: List[str] = []
    for p in pois or []:
        m = p.get("walkMetres")
        if (p.get("category") or "").lower() in {"school", "park", "childcare", "station",
                                                 "train", "shops", "shopping"} \
                and isinstance(m, (int, float)) and m <= 1000:
            walk_phrases.append(f"{_article(m)} {int(m)}-metre walk to {p.get('name')}")
    walk_phrases = walk_phrases[:1]  # one is enough; more crowds the sentence

    combination = _combination_phrases(anchors, diffs, walk_phrases)
    # Same guard as the LLM path: without at least two features there is no
    # "combination" to claim, and a one-feature hero would overstate.
    if len(combination) < 2 or not anchors:
        return None

    if is_scarce is None:
        total = sf.get("active_listings_total")
        match = sf.get("active_matching_full_stack")
        is_scarce = bool(total and match is not None and match / total <= 0.25)

    headline = (
        f"Your strongest selling features are not just {_not_just_clause(anchors)}. "
        f"It is the combination: {_join(combination)}."
    )

    match = sf.get("active_matching_full_stack")
    total = sf.get("active_listings_total")
    if isinstance(match, int) and isinstance(total, int) and total > 0:
        receipt = (f"Only {match} of {total} active listings across the catchment share "
                   f"this home's {_counted_anchor_names(anchors)}")
        if diffs or walk_phrases:
            narrower_list = ([d.get("phrase") or d.get("label") for d in diffs]
                             + (["walkability"] if walk_phrases else []))
            verb = "narrow" if len(narrower_list) > 1 else "narrows"
            receipt += f", before {_join(narrower_list)} {verb} it further"
        receipt += "."
    else:
        receipt = ""

    return {
        "headline": headline,
        "closingLine": CLOSE_SCARCE if is_scarce else CLOSE_COMMON,
        "combinatorialMatch": receipt,
        "walkingDistanceMonopoly": _monopoly(pois, suburb),
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "model": None,
        "method": "deterministic-v1",
        "is_scarce": bool(is_scarce),
    }
