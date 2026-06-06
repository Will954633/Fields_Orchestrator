"""
Scarcity narrative resolver — Opus turns the structured selling stack
(anchors + differentiators from scarcity_features, plus walk distances from
the POI layer) into the mini-site hero strings.

Editorial frame (rewritten 2026-06-07): the hero line no longer leads with
a single "rare" feature. It names the COMBINATION that makes the home suit
one buyer, then closes on Fields' job — finding that buyer. Shape:

  "Your strongest selling features are not just the {anchor1} and {anchor2}.
   It is the combination: {full stack}. Our job is to find the buyer who
   values that combination most — then give them enough confidence to
   compete for it."

The first two sentences are model-written (it assembles the stack into
natural prose). The CLOSING sentence is appended deterministically so the
brand promise is always identical, and it ADAPTS: the "compete for it"
scarcity framing is only used when the anchor combination is genuinely
uncommon in the cohort (matching/total <= SCARCE_SHARE). Otherwise it
closes on presentation, honestly.

Output strings:
  - headline: combination sentence(s) + deterministic close
  - combinatorialMatch: the count receipt
  - walkingDistanceMonopoly: tightest school/beach proximity line, or ""

Editorial guardrails (system prompt + validation): no advice, no
predictions, no forbidden words, exact figures, cite catchment + period.

Output schema (None on failure):
    {
      "headline": "...",
      "combinatorialMatch": "...",
      "walkingDistanceMonopoly": "..." or "",
      "generated_at": "...",
      "model": "claude-opus-4-7",
      "inputs_snapshot": {...},
      "attempt": 1,
    }
"""
from __future__ import annotations

import json
import logging
import os
import time
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

from scripts.property_reports.scarcity_features import SCARCE_SHARE, SCARCE_MIN_COHORT

logger = logging.getLogger(__name__)


MAX_RETRIES = 3
RETRY_BACKOFF_SECONDS = [2, 5, 12]
MODEL = "claude-opus-4-7"
MAX_TOKENS = 900

# POI categories that count as a walkable combination differentiator, and the
# walk ceiling (metres) under which they're "walkable". Beach is handled by
# the near-beach anchor + walkingDistanceMonopoly, so it's excluded here.
WALKABLE_CATEGORIES = {"school", "park", "childcare", "station", "train", "shops", "shopping"}
WALKABLE_CEILING_M = 1000

# Fixed closing sentences. Selected deterministically by scarcity.
CLOSE_SCARCE = (
    "Our job is to find the buyer who values that combination most — "
    "then give them enough confidence to compete for it."
)
CLOSE_COMMON = (
    "Our job is to find the buyer who values that combination most and "
    "present it so they recognise what they are looking at."
)


SYSTEM_PROMPT = """You write the opening of a seller-facing hero line describing what makes a property's COMBINATION of features suited to a specific buyer.

You are given the home's ANCHORS (mainstream features buyers screen on — land, floor area, pool, bedrooms) and its DIFFERENTIATORS (buyer-specific tippers — single-level living, a study, a short walk to a school/park). The point you must make: each feature on its own is common, but together they are uncommon, and that combination is what a particular buyer wants.

Output ONLY valid JSON in this exact shape:
{
  "combinationSentence": "TWO sentences. First: 'Your strongest selling features are not just the {one or two anchors named generically}.' Second: 'It is the combination: {the full stack, listed concretely with their real figures, anchors and differentiators interleaved naturally}.'",
  "combinatorialMatch": "single short phrase, 10-25 words: the count receipt (K of N active listings across the catchment match this combination)",
  "walkingDistanceMonopoly": "single sentence, 20-50 words, OR empty string if no proximity is genuinely tight"
}

ABSOLUTE RULES — violation triggers regeneration:
  1. NO ADVICE. Never tell the reader what to do.
  2. NO PREDICTIONS. Conditional language only.
  3. NO FORBIDDEN WORDS: stunning, nestled, boasting, rare opportunity, robust market, hot market, booming, breathtaking, magnificent, luxurious, prestigious.
  4. EXACT FIGURES — land area, distances and counts verbatim from the input. Never round transaction counts.
  5. Use ONLY the features provided. Do NOT invent features, rooms, or proximities.
  6. The "not just" clause names ONE or TWO anchors generically (e.g. "the pool, the land or the four bedrooms"). The "It is the combination:" clause lists the WHOLE stack with concrete figures.

STRUCTURE OF combinationSentence:
  - Sentence 1: "Your strongest selling features are not just the {one or two anchors, generic}."
  - Sentence 2: "It is the combination: {4 to 5 features, leading with the most DISTINCTIVE ones — single-level living, walkability, premium finish — then the mainstream anchors}." Concrete, with figures. Light factual connective words are fine ("single-level family living", "a private pool", "813 m² of land", "a 425-metre walk to Robina State School"). No marketing adjectives.
  - Keep the combination to AT MOST 5 features. If more were provided, choose the strongest and most differentiating and omit the weakest. Do not list every feature for its own sake.
  - Do NOT write the closing "our job is to find the buyer" sentence — that is appended automatically. End after the combination sentence.

combinatorialMatch: a compact, ACCURATE data-receipt. The K-of-N number covers ONLY the counted anchors you are given — NOT the differentiators. So phrase it as "Only K of N active listings across the catchment share this home's {counted anchors, e.g. four-plus bedrooms, comparable land and a pool}", and you MAY add ", before single-level living and walkability narrow it further" when differentiators exist. NEVER call the counted number a match for the "whole combination" — the differentiators are not in it.

walkingDistanceMonopoly: ONLY non-empty if at least one POI walking distance is <= 800m and the POI is a school or beach. Format: "{N} metres walking to {POI name} — closer than the typical {suburb} home." No claims you can't substantiate.

VOICE: plain, declarative, data over performance. No marketing language.

If the combination is genuinely COMMON in the cohort (you will be told), the combinationSentence should still name the combination honestly but not imply scarcity — the appended close handles that.

Return ONLY the JSON. No markdown, no preamble, no trailing text."""


def _walkable_differentiators(pois: List[Dict[str, Any]]) -> List[str]:
    """Turn the POI walk data into combination-ready phrases for schools,
    parks, childcare, stations and shops within the walkable ceiling. Returns
    the two closest, sorted, so the combination stays tight (a school usually
    beats a park; the nearest wins)."""
    cand: List[tuple] = []
    for poi in pois or []:
        cat = str(poi.get("category", "")).lower()
        metres = poi.get("walkMetres")
        if cat in WALKABLE_CATEGORIES and isinstance(metres, (int, float)) and 0 < metres <= WALKABLE_CEILING_M:
            name = poi.get("name") or cat.title()
            cand.append((metres, f"a {int(metres)}-metre walk to {name}"))
    cand.sort(key=lambda x: x[0])
    return [phrase for _, phrase in cand[:2]]


def _format_inputs(
    anchors: List[Dict[str, str]],
    differentiators: List[Dict[str, str]],
    walk_phrases: List[str],
    matching_full_stack: int,
    active_listings_total: int,
    counted_anchors_query: str,
    catchment_suburbs: List[str],
    cohort_premiums: List[Dict[str, Any]],
    pois: List[Dict[str, Any]],
    suburb: str,
    address: str,
    is_scarce: bool,
) -> str:
    """Render inputs as a tidy facts block for the model."""
    lines = [
        f"SUBJECT ADDRESS: {address}",
        f"SUBJECT SUBURB: {suburb}",
        f"CATCHMENT SUBURBS ({len(catchment_suburbs)}): {', '.join(catchment_suburbs)}",
        f"ACTIVE LISTINGS WITH ENGINE-FEATURE DATA IN CATCHMENT: {active_listings_total}",
        f"ACTIVE LISTINGS MATCHING THE COUNTED ANCHORS: {matching_full_stack}",
        f"WHAT THE {matching_full_stack}-OF-{active_listings_total} NUMBER MEASURES (the counted anchors ONLY): {counted_anchors_query}",
        f"  → the differentiators (single-level, walkability, finish) are NOT in this count; they narrow it further.",
        f"IS THIS COMBINATION UNCOMMON IN THE COHORT? {'YES — uncommon' if is_scarce else 'NO — fairly common'}",
        "",
        "ANCHORS (mainstream — name ONE or TWO of these generically in the 'not just' clause):",
    ]
    for a in anchors:
        lines.append(f"  - {a['label']}: {a.get('value', '')}  (phrase it as: \"{a.get('phrase', a['label'])}\")")
    if not anchors:
        lines.append("  (none — the home has no standout mainstream feature)")

    lines.append("")
    lines.append("DIFFERENTIATORS (buyer-specific tippers — weave into the combination):")
    for d in differentiators:
        lines.append(f"  - {d['label']}: {d.get('value', '')}  (phrase it as: \"{d.get('phrase', d['label'])}\")")
    for w in walk_phrases:
        lines.append(f"  - Walkable proximity  (phrase it as: \"{w}\")")
    if not differentiators and not walk_phrases:
        lines.append("  (none beyond the anchors)")

    lines.append("")
    lines.append("FULL COMBINATION TO ASSEMBLE (anchors + differentiators, in this order):")
    full = (
        [a.get("phrase", a["label"]) for a in anchors]
        + [d.get("phrase", d["label"]) for d in differentiators]
        + walk_phrases
    )
    lines.append("  " + " ; ".join(full) if full else "  (none)")

    lines.append("")
    lines.append("SOLD COHORT PREMIUMS (last 24 months in catchment):")
    for p in cohort_premiums:
        rel = "RELIABLE" if p.get("reliable") else "small-sample"
        pct = p.get("premium_pct")
        if pct is None:
            continue
        sign = "+" if pct >= 0 else ""
        lines.append(
            f"  - {p['feature_label']}: {sign}{pct:.1f}% premium "
            f"(n_with={p['n_with']}, n_without={p['n_without']}, {rel})"
        )

    lines.append("")
    lines.append("WALKING DISTANCES (Mapbox routes):")
    for poi in pois or []:
        lines.append(f"  - {poi['name']} ({poi['category']}): {poi['walkMetres']} metres")
    if not pois:
        lines.append("  (none computed)")

    return "\n".join(lines)


def _validate_output(parsed: Dict[str, Any]) -> Optional[str]:
    """Return error message if output fails validation, None if ok."""
    if not isinstance(parsed, dict):
        return "not a dict"
    for key in ("combinationSentence", "combinatorialMatch", "walkingDistanceMonopoly"):
        if key not in parsed:
            return f"missing key: {key}"
        if not isinstance(parsed[key], str):
            return f"{key} is not a string"

    combo = parsed["combinationSentence"].strip()
    if len(combo) < 40 or len(combo) > 500:
        return f"combinationSentence length {len(combo)} out of range"
    if "not just" not in combo.lower():
        return "combinationSentence missing the 'not just' framing"
    if "combination" not in combo.lower():
        return "combinationSentence missing the 'combination' framing"

    blob = (combo + " " + parsed["combinatorialMatch"] + " " + parsed["walkingDistanceMonopoly"]).lower()

    forbidden = [
        "stunning", "nestled", "boasting", "rare opportunity", "robust market",
        "hot market", "booming", "breathtaking", "magnificent", "luxurious", "prestigious",
    ]
    hit = [w for w in forbidden if w in blob]
    if hit:
        return f"forbidden word(s): {hit}"

    advice_patterns = [
        "you should", "we recommend", "now is a good time",
        "now is the time", "we suggest", "you must",
    ]
    advice_hit = [p for p in advice_patterns if p in blob]
    if advice_hit:
        return f"advice pattern(s): {advice_hit}"

    pred_patterns = [
        "prices will rise", "prices will fall", "the market will increase",
        "the market will decrease", "values will increase", "values will decrease",
    ]
    pred_hit = [p for p in pred_patterns if p in blob]
    if pred_hit:
        return f"prediction pattern(s): {pred_hit}"

    return None


def _is_scarce(matching: int, total: int, n_differentiators: int = 0) -> bool:
    """Whether the combination is uncommon enough to justify the
    'compete for it' close.

    The COUNT only covers the mainstream anchors (the features with reliable
    cohort coverage). The differentiators (single-level, walkability, premium
    finish) further narrow the real buyer pool but aren't counted — so each
    one relaxes the share threshold the anchor match must clear. A moderate
    anchor match plus several real differentiators is genuinely competitive
    territory; a moderate anchor match with none is not."""
    if total < SCARCE_MIN_COHORT:
        return False
    if matching <= 0:
        return True
    # Each differentiator relaxes the bar, but the top is capped at 0.25 — even
    # with several differentiators, a home matched by more than 1-in-4 actives
    # on its anchors is not "compete for it" territory.
    threshold = min(SCARCE_SHARE + 0.05 * min(n_differentiators, 2), 0.25)
    return (matching / total) <= threshold


def resolve_scarcity_narrative(
    scarcity_features: Dict[str, Any],
    pois: Optional[List[Dict[str, Any]]],
    suburb: str,
    address: str,
) -> Optional[Dict[str, Any]]:
    """Generate the hero strings. Returns None on permanent failure."""
    if not scarcity_features:
        return None

    anchors = scarcity_features.get("anchor_features") or []
    differentiators = scarcity_features.get("differentiator_features") or []
    matching = scarcity_features.get("active_matching_full_stack") or 0
    total = scarcity_features.get("active_listings_total") or 0
    catchment = scarcity_features.get("catchment_suburbs") or []
    premiums = scarcity_features.get("cohort_premiums") or []
    counted_anchors_query = scarcity_features.get("active_matching_query") or "the counted anchors"

    # Back-compat: if a caller passed the old shape (notable_features only),
    # treat all notables as anchors so the resolver still produces a line.
    if not anchors and not differentiators:
        notable = scarcity_features.get("notable_features") or []
        anchors = [n for n in notable if n.get("tier") != "differentiator"]
        differentiators = [n for n in notable if n.get("tier") == "differentiator"]
        if not anchors and notable:
            anchors = notable

    walk_phrases = _walkable_differentiators(pois or [])
    n_diff = len(differentiators) + len(walk_phrases)

    # The "not just X — it is the combination" framing needs at least two
    # elements in the stack. A home with a single feature would produce a
    # tautological line ("not just X. It is the combination: X."), so leave the
    # slot pending rather than emit a degraded hero. Most house submissions
    # clear this easily; it mainly filters thin unit/villa stacks.
    stack_size = len(anchors) + len(differentiators) + len(walk_phrases)
    if stack_size < 2:
        logger.info(f"  scarcity narrative skipped — stack too thin ({stack_size} feature) for combination framing")
        return None

    is_scarce = _is_scarce(matching, total, n_diff)
    close = CLOSE_SCARCE if is_scarce else CLOSE_COMMON

    api_key = os.environ.get("ANTHROPIC_API_KEY")
    if not api_key:
        logger.warning("ANTHROPIC_API_KEY not set — skipping scarcity narrative")
        return None

    try:
        from anthropic import Anthropic
    except ImportError:
        logger.warning("anthropic package not installed — skipping scarcity narrative")
        return None

    client = Anthropic(api_key=api_key)
    user_prompt = _format_inputs(
        anchors, differentiators, walk_phrases, matching, total, counted_anchors_query,
        catchment, premiums, pois or [], suburb, address, is_scarce,
    )

    last_error: Optional[str] = None
    for attempt in range(1, MAX_RETRIES + 1):
        try:
            response = client.messages.create(
                model=MODEL,
                max_tokens=MAX_TOKENS,
                system=SYSTEM_PROMPT,
                messages=[{"role": "user", "content": user_prompt}],
            )
        except Exception as e:
            last_error = f"API error attempt {attempt}: {e}"
            logger.warning(f"  {last_error}")
            if attempt < MAX_RETRIES:
                time.sleep(RETRY_BACKOFF_SECONDS[min(attempt - 1, len(RETRY_BACKOFF_SECONDS) - 1)])
            continue

        try:
            raw = "".join(
                getattr(b, "text", "") for b in response.content
                if getattr(b, "type", None) == "text"
            ).strip()
            if raw.startswith("```"):
                raw = raw.split("\n", 1)[1].rsplit("```", 1)[0].strip()
                if raw.startswith("json\n"):
                    raw = raw[5:].strip()
            parsed = json.loads(raw)
        except (json.JSONDecodeError, KeyError, AttributeError, IndexError) as e:
            last_error = f"parse error attempt {attempt}: {e}"
            logger.warning(f"  {last_error}")
            if attempt < MAX_RETRIES:
                time.sleep(RETRY_BACKOFF_SECONDS[min(attempt - 1, len(RETRY_BACKOFF_SECONDS) - 1)])
            continue

        validation_err = _validate_output(parsed)
        if validation_err:
            last_error = f"validation failed attempt {attempt}: {validation_err}"
            logger.warning(f"  {last_error}")
            if attempt < MAX_RETRIES:
                time.sleep(RETRY_BACKOFF_SECONDS[min(attempt - 1, len(RETRY_BACKOFF_SECONDS) - 1)])
            continue

        # Deterministic close — the brand promise is identical every time and
        # adapts to whether the combination is genuinely uncommon. Returned as a
        # SEPARATE field so the frontend can render it on its own line, bold,
        # below the combination sentence.
        return {
            "headline": parsed["combinationSentence"].strip(),
            "closingLine": close,
            "combinatorialMatch": parsed["combinatorialMatch"].strip(),
            "walkingDistanceMonopoly": parsed["walkingDistanceMonopoly"].strip(),
            "generated_at": datetime.now(timezone.utc).isoformat(),
            "model": MODEL,
            "attempt": attempt,
            "is_scarce": is_scarce,
            "inputs_snapshot": {
                "suburb": suburb,
                "address": address,
                "n_anchors": len(anchors),
                "n_differentiators": len(differentiators) + len(walk_phrases),
                "matching": matching,
                "total": total,
            },
        }

    logger.error(f"scarcity_narrative: all {MAX_RETRIES} attempts failed — last_error={last_error}")
    return {"error": last_error, "attempts": MAX_RETRIES}


def cohort_premiums_to_sold_cohort_premiums(cohort_premiums: List[Dict[str, Any]]) -> List[Dict[str, str]]:
    """Deterministic mapping: turn the structured cohort_premiums into the
    mini-site's `soldCohortPremiums` array shape. Only include reliable
    premiums to avoid surfacing noise."""
    out: List[Dict[str, str]] = []
    for p in cohort_premiums or []:
        if not p.get("reliable"):
            continue
        pct = p.get("premium_pct")
        if pct is None:
            continue
        sign = "+" if pct >= 0 else ""
        out.append({
            "feature": p["feature_label"],
            "premium": f"{sign}{pct:.1f}%",
        })
    return out
