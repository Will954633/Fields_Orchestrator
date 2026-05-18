"""
Scarcity narrative resolver — Opus 4.7 turns the structured scarcity data
(Day 7 notable features + active match count, Day 8 cohort premiums, Day 4
walking distances) into three user-facing strings:

  - headline: the load-bearing scarcity claim ("Of 174 active listings...
    only 2 match your full stack")
  - combinatorialMatch: short subhead with the count + catchment span
  - walkingDistanceMonopoly: qualitative line about uncommon proximity, if
    any walking distance is notably tight; otherwise omitted

The sold cohort premium TABLE itself isn't narrative — it's transformed
deterministically from cohort_premiums in slot_resolver.py. Opus only
writes the prose.

Editorial guardrails (system prompt): no advice, no predictions, no
forbidden words, exact figures, cite source + period.

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

logger = logging.getLogger(__name__)


MAX_RETRIES = 3
RETRY_BACKOFF_SECONDS = [2, 5, 12]
MODEL = "claude-opus-4-7"
MAX_TOKENS = 900


SYSTEM_PROMPT = """You write three short pieces of seller-facing text describing what makes a property's feature stack uncommon in its catchment.

Output ONLY valid JSON in this exact shape:
{
  "headline": "single sentence, 25-45 words, the load-bearing scarcity claim",
  "combinatorialMatch": "single short phrase, 10-25 words, the count + catchment span",
  "walkingDistanceMonopoly": "single sentence, 20-50 words, OR empty string if no proximity is genuinely uncommon"
}

ABSOLUTE RULES — violation triggers regeneration:
  1. NO ADVICE. Never tell the reader what to do.
  2. NO PREDICTIONS. Conditional language only.
  3. NO FORBIDDEN WORDS: stunning, nestled, boasting, rare opportunity, robust market, hot market, booming, breathtaking, magnificent.
  4. EXACT FIGURES — numbers and prices verbatim from the input. Never round transaction counts.
  5. Cite the catchment span (e.g. "across 9 southern Gold Coast suburbs", "in the Burleigh Waters cohort").
  6. The headline must name the SPECIFIC features that make the stack uncommon — bedroom band, land tier, pool, water views, beach distance — NOT generic descriptors.

STRUCTURE:
  - headline: lead with the count ("Of N active listings across the catchment, only K share..."), then enumerate the features in the order they were given.
  - combinatorialMatch: a compact data-receipt for the headline ("K of N active listings across 4 catchment suburbs").
  - walkingDistanceMonopoly: ONLY return non-empty if at least one POI walking distance is ≤ 800m and the POI is a school or beach. Otherwise return empty string "". Format: "{N} metres walking to {POI name} — closer than the typical {suburb} home." No claims you can't substantiate.

VOICE:
  - Plain, declarative. No marketing language.
  - Match the V4 PDF "data over performance" tone established in the editorial system prompt.
  - If the feature stack is COMMON (matching_full_stack > 20% of total_active), the headline should reflect that honestly — e.g. "Your home shares this combination with 47 of 174 active listings; the differentiation will come from condition, photography, and presentation rather than feature scarcity."

Return ONLY the JSON. No markdown, no preamble, no trailing text."""


def _format_inputs(
    notable_features: List[Dict[str, str]],
    matching_full_stack: int,
    active_listings_total: int,
    catchment_suburbs: List[str],
    cohort_premiums: List[Dict[str, Any]],
    pois: List[Dict[str, Any]],
    suburb: str,
    address: str,
) -> str:
    """Render inputs as a tidy facts block for the model."""
    lines = [
        f"SUBJECT ADDRESS: {address}",
        f"SUBJECT SUBURB: {suburb}",
        f"CATCHMENT SUBURBS: {', '.join(catchment_suburbs)}",
        f"ACTIVE LISTINGS WITH ENGINE-FEATURE DATA IN CATCHMENT: {active_listings_total}",
        f"ACTIVE LISTINGS MATCHING THE FULL FEATURE STACK: {matching_full_stack}",
        "",
        "NOTABLE FEATURES (the stack):",
    ]
    for f in notable_features:
        lines.append(f"  - {f['label']} ({f['value']})")
    if not notable_features:
        lines.append("  (none — feature stack is standard for the cohort)")

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
    for key in ("headline", "combinatorialMatch", "walkingDistanceMonopoly"):
        if key not in parsed:
            return f"missing key: {key}"
        if not isinstance(parsed[key], str):
            return f"{key} is not a string"

    headline = parsed["headline"].strip()
    if len(headline) < 40 or len(headline) > 400:
        return f"headline length {len(headline)} out of range"

    combined = (headline + " " + parsed["combinatorialMatch"] + " " + parsed["walkingDistanceMonopoly"]).lower()

    forbidden = [
        "stunning", "nestled", "boasting", "rare opportunity", "robust market",
        "hot market", "booming", "breathtaking", "magnificent",
    ]
    hit = [w for w in forbidden if w in combined]
    if hit:
        return f"forbidden word(s): {hit}"

    advice_patterns = [
        "you should", "we recommend", "now is a good time",
        "now is the time", "we suggest", "you must",
    ]
    advice_hit = [p for p in advice_patterns if p in combined]
    if advice_hit:
        return f"advice pattern(s): {advice_hit}"

    pred_patterns = [
        "prices will rise", "prices will fall", "the market will increase",
        "the market will decrease", "values will increase", "values will decrease",
    ]
    pred_hit = [p for p in pred_patterns if p in combined]
    if pred_hit:
        return f"prediction pattern(s): {pred_hit}"

    return None


def resolve_scarcity_narrative(
    scarcity_features: Dict[str, Any],
    pois: Optional[List[Dict[str, Any]]],
    suburb: str,
    address: str,
) -> Optional[Dict[str, Any]]:
    """Generate the three scarcity strings. Returns None on permanent failure."""
    if not scarcity_features:
        return None

    notable = scarcity_features.get("notable_features") or []
    matching = scarcity_features.get("active_matching_full_stack") or 0
    total = scarcity_features.get("active_listings_total") or 0
    catchment = scarcity_features.get("catchment_suburbs") or []
    premiums = scarcity_features.get("cohort_premiums") or []

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
        notable, matching, total, catchment, premiums, pois or [], suburb, address,
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
            # Strip any markdown code fences the model might wrap with
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

        return {
            "headline": parsed["headline"].strip(),
            "combinatorialMatch": parsed["combinatorialMatch"].strip(),
            "walkingDistanceMonopoly": parsed["walkingDistanceMonopoly"].strip(),
            "generated_at": datetime.now(timezone.utc).isoformat(),
            "model": MODEL,
            "attempt": attempt,
            "inputs_snapshot": {
                "suburb": suburb,
                "address": address,
                "n_notable": len(notable),
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
