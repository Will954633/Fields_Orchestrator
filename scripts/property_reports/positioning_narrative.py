"""
Positioning narrative resolver — Opus 4.7 produces the five positioning
fields for the mini-site PositioningTab:

  - frame.angle: 1-2 sentence positioning angle for this specific property
  - frame.reasoning: why this angle vs alternatives
  - vocabulary.use[]: 5-7 phrases anchored to verifiable facts
  - vocabulary.avoid[]: 5-8 forbidden marketing words specific to this brief
  - vocabulary.avoidNote: 1-2 sentence rationale
  - tradeOffs[]: 2-3 apparent flaws + reframe + evidence
  - photography[]: 4-6 shot briefs with what each proves
  - sampleParagraph: 100-130 word listing opener in proposed voice

Personas live in a separate resolver (Day 11) since they're reused by the
Buyers tab and need a different prompt structure.

Knowledge base: positioning playbook v5.0 (60+ studies, 14 academic
papers, 2,153 sold properties), inlined into the system prompt.
"""
from __future__ import annotations

import json
import logging
import os
import time
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

from scripts.property_reports.valuation_format import display_range
from scripts.property_reports.cohort_premiums import premium_prompt_lines

logger = logging.getLogger(__name__)


MAX_RETRIES = 3
RETRY_BACKOFF_SECONDS = [2, 5, 12]
MODEL = "claude-opus-4-7"
MAX_TOKENS = 3000


SYSTEM_PROMPT = """You are the Fields Estate positioning strategist. You analyse a property and its market context to produce the positioning section of a seller-facing mini-site.

# POSITIONING PLAYBOOK v5.0 (condensed from 60+ studies, 14 academic papers, 2,153 sold properties)

## What drives price (in order)
1. LOCATION (suburb + street) — 67% $/sqm variance between suburbs. Street-level premiums ±40%.
2. SIZE (floor area) — strongest single predictor (r=0.68-0.79).
3. BEDROOM COUNT — each bedroom adds $255K-$607K depending on suburb.

## What does NOT drive $/sqm
- Renovation level (in Robina/Varsity Lakes, fully renovated = LOWER $/sqm than original. Burleigh Waters is the exception: reno adds +14%).
- Kitchen finishes (island bench, stone benchtop — no significant impact, p>0.1).
- Pool (+0.6-3.7% $/sqm — not significant).
- Condition score (near-zero correlation with $/sqm).
- Corner lots (DISCOUNT: -14% in Robina and Burleigh Waters).

## Pricing & scarcity rules
- Scarcity must be REAL and VERIFIABLE from the database. NEVER manufactured urgency ("Don't miss out!").
- SAMPLE-RELATIVE ONLY: we never had a census of every sale — only a Domain-scraped indicative sample. Express rarity as position vs the typical sampled home or as a share within our disclosed sample ("above 88% of our sample of N sold homes"), ALWAYS naming the sample. NEVER "the only one", "no other home", "1 of only X", or any wording implying a complete count of all sales.
- Burleigh Waters urgency-opening = 33d DOM vs 20.5d for factual openings.
- Frame trade-offs honestly. Every apparent flaw is value when anchored to a buyer need.

## Forbidden marketing words (universal)
stunning, nestled, boasting, rare opportunity, robust market, hot market, breathtaking, magnificent, must-see, dream home, executive

# OUTPUT FORMAT

Return ONLY valid JSON in this exact shape — no markdown, no preamble, no trailing text:

{
  "frame": {
    "angle": "string — 1-2 sentences (40-80 words). The single positioning angle for this property, written declaratively. Lead with what the data says is genuinely uncommon, in the order a target buyer weighs it.",
    "reasoning": "string — 60-120 words. Why this angle, not another. Reference the specific notable features, the catchment context, the cohort evidence. End with what the angle deliberately does NOT lead with and why."
  },
  "vocabulary": {
    "use": [
      {"term": "string — 2-6 word phrase that could appear in listing copy", "anchoredTo": "string — the specific fact this phrase rests on. Cite the number."}
    ],
    "avoid": ["string", "string"],
    "avoidNote": "string — 1-2 sentences explaining why those words harm this listing specifically."
  },
  "tradeOffs": [
    {
      "apparent": "string — what a sceptical buyer might raise",
      "reframe": "string — how to address it honestly without burying it",
      "evidence": "string — the specific fact that supports the reframe"
    }
  ],
  "photography": [
    {"slot": "string — short label, e.g. 'HERO — front elevation'", "brief": "string — what to shoot, lighting, time of day", "proves": "string — the specific claim this image substantiates"}
  ],
  "genericParagraph": "string — 50-90 words. The OPPOSITE of the Fields voice: how an ordinary agent would write this home's opener — generic adjectives, no evidence, no named buyer. This is a deliberate BAD example shown side-by-side with sampleParagraph to make the Fields skill visible. It SHOULD use the hype words (stunning, nestled, boasting, rare opportunity, etc.) — that is its purpose. Do NOT include any real figures here.",
  "sampleParagraph": "string — 100-130 words. A worked example of the listing opener in this voice, using the angle, addressing the trade-offs, employing the vocabulary palette. Read it back: every phrase should be defensible from the input data."
}

# ABSOLUTE RULES — violation triggers regeneration

1. NO ADVICE. Don't tell the seller what to do. The mini-site is the consultant's positioning READ-OUT, not advice.
2. NO PREDICTIONS. Use conditional language only. Never "prices will rise/fall".
3. EXACT FIGURES. Numbers verbatim from the input. Land sizes, floor areas, bedroom counts, transaction counts — never round or paraphrase.
4. FORBIDDEN WORDS: stunning, nestled, boasting, rare opportunity, robust market, hot market, breathtaking, magnificent, must-see, dream home, executive (in narrative text). The vocabulary.avoid list itself MAY contain these words since that's its purpose.
5. CITE the catchment span when relevant ("across the nine-suburb southern Gold Coast catchment").
6. 5-7 entries in vocabulary.use, 5-8 in vocabulary.avoid, 2-3 in tradeOffs, 4-6 in photography.
7. sampleParagraph must be 90-140 words inclusive (counted by whitespace-split).

# VOICE
- Plain, declarative. No marketing language.
- Match the V4 PDF tone: "data over performance".
- Address the seller directly when natural. The reader is the property owner, not a buyer.
- Honest. If a feature is common, say so."""


def _format_inputs(
    address: str,
    suburb: str,
    features_basic: Dict[str, Any],
    notable_features: List[Dict[str, str]],
    matching_full_stack: int,
    active_listings_total: int,
    cohort_premiums: List[Dict[str, Any]],
    pois: List[Dict[str, Any]],
    valuation_range: Optional[Dict[str, Any]] = None,
) -> str:
    """Render the structured inputs as a tidy facts block for the model."""
    lines = [
        f"SUBJECT: {address} ({suburb})",
        "",
        "PROPERTY FACTS:",
    ]
    fb_fields = [
        ("bedrooms", "Bedrooms"),
        ("bathrooms", "Bathrooms"),
        ("car_spaces", "Car spaces"),
        ("land_size_sqm", "Land (m²)"),
        ("floor_area_sqm", "Internal floor (m²)"),
        ("approximate_build_year", "Approximate build year"),
        ("number_of_stories", "Stories"),
        ("pool_present", "Pool"),
        ("water_views", "Water views"),
        ("beach_distance_km", "Beach distance (km)"),
        ("ac_ducted", "Ducted AC"),
        ("renovation_level_raw", "Renovation level"),
        ("renovation_quality_score", "Renovation quality (0-10)"),
        ("kitchen_score", "Kitchen quality (0-10)"),
        ("cladding_raw", "Cladding"),
    ]
    for k, label in fb_fields:
        v = features_basic.get(k)
        if v is not None:
            lines.append(f"  - {label}: {v}")

    lines.append("")
    lines.append("NOTABLE FEATURES (engine-identified):")
    for f in notable_features or []:
        lines.append(f"  - {f['label']} ({f['value']})")
    if not notable_features:
        lines.append("  (none — feature stack is standard for the cohort)")

    lines.append("")
    lines.append(
        f"COMBINATORIAL MATCH: {matching_full_stack} of {active_listings_total} active listings in the southern Gold Coast catchment carry this full feature stack."
    )

    lines.append("")
    lines.extend(premium_prompt_lines(cohort_premiums))

    lines.append("")
    lines.append("WALKING DISTANCES (Mapbox routes):")
    for poi in pois or []:
        lines.append(f"  - {poi['name']} ({poi['category']}): {poi['walkMetres']} metres")
    if not pois:
        lines.append("  (none computed)")

    _dr = display_range(valuation_range)
    if _dr:
        lines.append("")
        lines.append(
            f"WORKING VALUATION RANGE: ${_dr[0]:,} – ${_dr[1]:,} (engine pre-consultant, "
            f"rounded to the nearest $100k for display)"
        )

    return "\n".join(lines)


def _validate_output(parsed: Dict[str, Any]) -> Optional[str]:
    """Schema + editorial validation. Returns error string if invalid."""
    if not isinstance(parsed, dict):
        return "not a dict"

    # Required top-level keys
    for key in ("frame", "vocabulary", "tradeOffs", "photography", "sampleParagraph", "genericParagraph"):
        if key not in parsed:
            return f"missing key: {key}"

    # frame shape
    frame = parsed.get("frame") or {}
    if not isinstance(frame.get("angle"), str) or len(frame["angle"]) < 30:
        return "frame.angle missing or too short"
    if not isinstance(frame.get("reasoning"), str) or len(frame["reasoning"]) < 60:
        return "frame.reasoning missing or too short"

    # vocabulary shape
    vocab = parsed.get("vocabulary") or {}
    use = vocab.get("use") or []
    if not isinstance(use, list) or len(use) < 4 or len(use) > 10:
        return f"vocabulary.use should be 4-10 items, got {len(use) if isinstance(use, list) else 'n/a'}"
    for v in use:
        if not isinstance(v, dict) or not v.get("term") or not v.get("anchoredTo"):
            return "vocabulary.use entry missing term/anchoredTo"
    avoid = vocab.get("avoid") or []
    if not isinstance(avoid, list) or len(avoid) < 4 or len(avoid) > 12:
        return f"vocabulary.avoid should be 4-12 items, got {len(avoid) if isinstance(avoid, list) else 'n/a'}"
    if not isinstance(vocab.get("avoidNote"), str):
        return "vocabulary.avoidNote missing"

    # tradeOffs shape
    trade = parsed.get("tradeOffs") or []
    if not isinstance(trade, list) or len(trade) < 2 or len(trade) > 5:
        return f"tradeOffs should be 2-5 items, got {len(trade) if isinstance(trade, list) else 'n/a'}"
    for t in trade:
        if not all(isinstance(t.get(k), str) and t.get(k) for k in ("apparent", "reframe", "evidence")):
            return "tradeOffs entry missing apparent/reframe/evidence"

    # photography
    photo = parsed.get("photography") or []
    if not isinstance(photo, list) or len(photo) < 3 or len(photo) > 8:
        return f"photography should be 3-8 items, got {len(photo) if isinstance(photo, list) else 'n/a'}"
    for p in photo:
        if not all(isinstance(p.get(k), str) and p.get(k) for k in ("slot", "brief", "proves")):
            return "photography entry missing slot/brief/proves"

    # sampleParagraph word count
    sp = parsed.get("sampleParagraph") or ""
    word_count = len(sp.split())
    if word_count < 80 or word_count > 160:
        return f"sampleParagraph word count {word_count} out of 80-160 range"

    # genericParagraph is the deliberate "ordinary agent" example — it MUST exist
    # and read as generic, but it is intentionally exempt from the forbidden-word
    # guardrail below (hype words are the point of the contrast).
    gp = parsed.get("genericParagraph") or ""
    gp_words = len(gp.split())
    if gp_words < 35 or gp_words > 120:
        return f"genericParagraph word count {gp_words} out of 35-120 range"

    # Editorial guardrails on the prose fields (not vocabulary.avoid, not genericParagraph)
    prose = " ".join([
        frame["angle"], frame["reasoning"], vocab.get("avoidNote", ""),
        " ".join(t["apparent"] + " " + t["reframe"] + " " + t["evidence"] for t in trade),
        " ".join(p["brief"] + " " + p["proves"] for p in photo),
        sp,
    ]).lower()

    forbidden = [
        "stunning", "nestled", "boasting", "rare opportunity", "robust market",
        "hot market", "breathtaking", "magnificent", "must-see", "dream home",
    ]
    hit = [w for w in forbidden if w in prose]
    if hit:
        return f"forbidden word(s) in prose: {hit}"

    advice = ["you should", "we recommend", "now is a good time", "now is the time"]
    advice_hit = [p for p in advice if p in prose]
    if advice_hit:
        return f"advice pattern(s): {advice_hit}"

    pred = ["prices will rise", "prices will fall", "values will increase", "values will decrease"]
    pred_hit = [p for p in pred if p in prose]
    if pred_hit:
        return f"prediction pattern(s): {pred_hit}"

    return None


def resolve_positioning_narrative(
    address: str,
    suburb: str,
    features_basic: Dict[str, Any],
    notable_features: List[Dict[str, str]],
    matching_full_stack: int,
    active_listings_total: int,
    cohort_premiums: List[Dict[str, Any]],
    pois: List[Dict[str, Any]],
    valuation_range: Optional[Dict[str, Any]] = None,
) -> Optional[Dict[str, Any]]:
    """Generate the positioning narrative. Returns None on permanent failure."""

    api_key = os.environ.get("ANTHROPIC_API_KEY")
    if not api_key:
        logger.warning("ANTHROPIC_API_KEY not set — skipping positioning narrative")
        return None

    try:
        from anthropic import Anthropic
    except ImportError:
        logger.warning("anthropic package not installed — skipping positioning narrative")
        return None

    client = Anthropic(api_key=api_key)
    user_prompt = _format_inputs(
        address, suburb, features_basic or {}, notable_features or [],
        matching_full_stack or 0, active_listings_total or 0,
        cohort_premiums or [], pois or [], valuation_range,
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

        return {
            "frame": parsed["frame"],
            "vocabulary": parsed["vocabulary"],
            "tradeOffs": parsed["tradeOffs"],
            "photography": parsed["photography"],
            "sampleParagraph": parsed["sampleParagraph"],
            "genericParagraph": parsed["genericParagraph"],
            "generated_at": datetime.now(timezone.utc).isoformat(),
            "model": MODEL,
            "attempt": attempt,
        }

    logger.error(f"positioning_narrative: all {MAX_RETRIES} attempts failed — last_error={last_error}")
    return {"error": last_error, "attempts": MAX_RETRIES}
