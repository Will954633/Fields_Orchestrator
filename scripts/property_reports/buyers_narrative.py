"""
Buyers narrative resolver — Opus 4.7 writes the three sections of the
BuyersTab: thesis, catchment, campaign math.

Reads the same upstream context as positioning + personas (scarcity_features,
cohort_premiums, pois, valuation_range) so the buyers section coheres with
the positioning frame and the 3 personas already generated.

Output schema:
  {
    "thesis": {
      "headline": "single sentence ≤ 25 words",
      "body": ["paragraph", "paragraph"],          // 2-3 paragraphs
      "statBlocks": [{"value": "string", "label": "string"}, ...]   // 2-3 cards
    },
    "catchment": {
      "headline": "single sentence",
      "body": ["paragraph"],                       // 1-2 paragraphs
      "locations": [
        {"label": "string", "share": "string", "reasoning": "string"},
        ...                                        // exactly 3 origin cohorts
      ]
    },
    "campaignMath": {
      "headline": "single sentence",
      "body": "paragraph",
      "statBlocks": [{"value": "string", "label": "string"}, ...]   // 2 cards
    }
  }

The 3 catchment.locations align with the 3 personas already generated —
each persona's origin geography becomes one catchment row.
"""
from __future__ import annotations

import json
import logging
import os
import re
import time
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)


MAX_RETRIES = 3
RETRY_BACKOFF_SECONDS = [2, 5, 12]
MODEL = "claude-opus-4-7"
MAX_TOKENS = 2800

# Channels Fields does NOT operate + claims of data Fields does NOT have. The
# catchment section used to assert a back-test against an "open-home register"
# and "buyer-origin data" that don't exist; the model also borrowed legacy
# agent tactics. Any of these in the generated prose triggers regeneration.
# Allowed (our real method): "direct approach", "letterbox", "direct mail".
# Only terms that are NEVER legitimate on this page. (The catchment disclaimer
# legitimately needs to SAY it's "not a buyer register / not back-tested", so
# those words are policed by the prompt — told to avoid them — not hard-banned
# here, which would also reject the honest negation.)
FORBIDDEN_CHANNELS = [
    "newsletter", "noticeboard", "flyer", "school gate", "school-gate",
    "word of mouth", "word-of-mouth", "mailer", "mailing list", "newspaper",
    "real-estate-section", "real estate section", "linkedin",
    "custom audience", "open-home register", "open home register",
]


SYSTEM_PROMPT = """You write the three sections of a seller-facing "Buyers" tab on a southern Gold Coast property mini-site: a scarcity thesis, a buyer catchment breakdown, and a campaign-math passive/active pool model.

# CONTEXT — the rest of the mini-site

This property has already been analysed:
  - Scarcity: notable feature stack + how many other actives match
  - Cohort premiums: median sale-price deltas per feature
  - Positioning: angle + reasoning + vocabulary palette + sample listing copy
  - Personas: 3 buyer profiles already identified, each with whyThisHome + whereFound

Your three sections need to COHERE with the personas (their geographies become the catchment rows) and the scarcity/positioning numbers (re-use the same active-listing counts and feature stack).

# HOW FIELDS REACHES BUYERS — catchment.reasoning and campaignMath MUST use ONLY these

Fields finds buyers in more ways than a portal listing does. Describe reach using ONLY the channels Fields actually operates:
  - Conversion-optimised paid campaigns on Facebook and Instagram — BROAD prospecting (Fields' own performance data shows broad targeting outperforms narrow / "custom" audiences), plus retargeting people who have already engaged with Fields content or the listing.
  - YouTube video reach into the local market.
  - Google Ads on active search intent (e.g. "<suburb> family home", school-catchment queries).
  - Fields' own buyer audience — people who follow Fields market data and subscribe — reached and re-engaged directly.
  - DIRECT APPROACH (the point of difference): Fields identifies the nearby homes whose owners typically move up into a home like this and contacts them directly, reaching buyers not searching the portals yet. Describe as METHOD, conditionally. NEVER state a count.
  - The major portals (Domain, realestate.com.au) are table stakes; the point of difference is reaching BEYOND them.

NEVER mention these — Fields does NOT do them: school newsletters, noticeboards, school-gate word-of-mouth, print mailers, flyers, newspaper / real-estate-section ads, LinkedIn outreach, "Will's network", mailing lists, "custom audiences" as a prospecting lever, or any open-home register or buyer-origin dataset. Fields has NO measured buyer-origin data and has held NO open homes — never claim a back-test against either.

# SECTION RULES

## 1. thesis
The scarcity thesis: WHY this property reaches a smaller, more motivated buyer pool than a generic listing in the same bracket. Lead with the combinatorial-match count from the input. Cite features from the stack. Two short paragraphs (60-100 words each). StatBlocks: 2-3 cards (e.g. "2 of 178" + "3 personas weighted" + "$1.88M–$2.40M working range") that data-receipt the thesis.

## 2. catchment
This is NOT a measured buyer-origin breakdown — Fields has no buyer register or open-home data. It is the set of buyer pools we'd TARGET and where we'd weight the campaign, informed by how households typically move up within the southern Gold Coast, the suburb's 24-month sold cohort, and school / commute catchment logic. Headline frames it as targeting/strategy (e.g. "The buyer pools we'd target — and where we'd weight the search"). Body: 1-2 paragraphs (50-90 words each) making clear the cohorts are INFORMED BY move-up patterns and the suburb's sold market, and are a targeting strategy rather than measured data. Convey that in plain language — do NOT use the words "back-test", "register", or "buyer-origin" (say e.g. "a targeting strategy, not a measured count of where past buyers came from"). Locations: exactly 3 rows aligning to the 3 personas — `label` is the cohort/geography, `share` is where we'd WEIGHT the campaign as a SHORT verbal label ("Primary focus", "Secondary focus", "Supporting") — a strategy choice, NEVER a measured proportion or percentage — `reasoning` (30-60 words) ties the cohort to the real Fields channel that reaches it (see HOW FIELDS REACHES BUYERS).

## 3. campaignMath
Reach framed as general market structure — NO invented precision. In this price bracket a large share of qualified buyers are not actively searching the portals at any one time; present this as a normal market dynamic, NOT as a Fields measurement, and do NOT state any active/passive percentage or number. Headline: "The reach we'd build" or similar. Body: 1 paragraph (60-100 words) naming the bracket from the working valuation range and explaining the campaign reaches beyond active portal searchers to the passive pool, through Fields' real channels. StatBlocks: exactly 2 qualitative cards about reach with NO numbers or percentages (e.g. {"value":"Beyond the portals","label":"…"}, {"value":"Five channels","label":"…"}).

# OUTPUT FORMAT

Return ONLY valid JSON in this exact shape — no markdown, no preamble:

{
  "thesis": {
    "headline": "string",
    "body": ["string", "string"],
    "statBlocks": [{"value": "string", "label": "string"}]
  },
  "catchment": {
    "headline": "string",
    "body": ["string"],
    "locations": [{"label": "string", "share": "string", "reasoning": "string"}]
  },
  "campaignMath": {
    "headline": "string",
    "body": "string",
    "statBlocks": [{"value": "string", "label": "string"}]
  }
}

# ABSOLUTE RULES — violation triggers regeneration

1. EXACTLY 3 entries in catchment.locations. They MUST align 1:1 to the 3 personas in the input — same buyer-cohort labels and geographies.
2. NO ADVICE TO THE SELLER. Describe the buyer pool, not what to do about it.
3. NO PREDICTIONS. Conditional language for buyer behaviour only.
4. NO FORBIDDEN WORDS in prose: stunning, nestled, boasting, rare opportunity, robust market, hot market, breathtaking, magnificent, must-see, dream home, executive.
5. EXACT FIGURES from input. Re-use the combinatorial match count, the working valuation range, the active-listing total.
6. thesis.statBlocks 2-3 items, campaignMath.statBlocks EXACTLY 2 items.
7. thesis.body 2-3 paragraphs, catchment.body 1-2 paragraphs.
8. catchment.share is a SHORT campaign-weight label (e.g. "Primary focus"), NEVER a measured proportion or percentage. catchment must NOT claim a measured buyer origin, an open-home register, a back-test, or origin percentages.
9. campaignMath contains NO percentages or invented active/passive numbers.
10. CHANNELS in catchment.reasoning and campaignMath may reference ONLY the channels in HOW FIELDS REACHES BUYERS. Forbidden channels trigger regeneration.

# VOICE

Plain, declarative, data-first. Address the seller's report indirectly — "this property reaches", "the campaign would build". Match the V4 PDF tone."""


def _format_inputs(
    address: str,
    suburb: str,
    features_basic: Dict[str, Any],
    notable_features: List[Dict[str, str]],
    matching_full_stack: int,
    active_listings_total: int,
    cohort_premiums: List[Dict[str, Any]],
    personas: List[Dict[str, Any]],
    pois: List[Dict[str, Any]],
    valuation_range: Optional[Dict[str, Any]] = None,
) -> str:
    lines = [
        f"SUBJECT: {address} ({suburb})",
        "",
        "PROPERTY FACTS:",
    ]
    for k, label in [
        ("bedrooms", "Bedrooms"),
        ("bathrooms", "Bathrooms"),
        ("land_size_sqm", "Land (m²)"),
        ("floor_area_sqm", "Internal floor (m²)"),
        ("pool_present", "Pool"),
        ("water_views", "Water views"),
        ("beach_distance_km", "Beach distance (km)"),
    ]:
        v = features_basic.get(k)
        if v is not None:
            lines.append(f"  - {label}: {v}")

    lines.append("")
    lines.append("NOTABLE FEATURES (the stack):")
    for f in notable_features or []:
        lines.append(f"  - {f['label']}")

    lines.append("")
    lines.append(
        f"COMBINATORIAL MATCH: {matching_full_stack} of {active_listings_total} "
        f"active listings in the catchment carry this full stack."
    )

    if valuation_range and valuation_range.get("low"):
        lines.append("")
        lines.append(
            f"WORKING VALUATION RANGE: ${valuation_range['low']:,} – ${valuation_range['high']:,}"
        )

    lines.append("")
    lines.append("SOLD COHORT PREMIUMS (last 24 months, reliable only):")
    for p in cohort_premiums or []:
        if not p.get("reliable") or p.get("premium_pct") is None:
            continue
        sign = "+" if p["premium_pct"] >= 0 else ""
        lines.append(
            f"  - {p['feature_label']}: {sign}{p['premium_pct']:.1f}% (n_with={p['n_with']})"
        )

    lines.append("")
    lines.append(f"THE 3 PERSONAS (already generated — your catchment.locations must align to these):")
    for i, p in enumerate(personas or [], start=1):
        lines.append(f"  Persona {i}: {p.get('label')}")
        lines.append(f"    Brief: {p.get('brief')}")
        lines.append(f"    Where found: {p.get('whereFound')}")

    lines.append("")
    lines.append("WALKING DISTANCES (Mapbox routes):")
    for poi in pois or []:
        lines.append(f"  - {poi['name']} ({poi['category']}): {poi['walkMetres']} metres")

    return "\n".join(lines)


def _validate_output(parsed: Any) -> Optional[str]:
    if not isinstance(parsed, dict):
        return "not a dict"
    for key in ("thesis", "catchment", "campaignMath"):
        if key not in parsed:
            return f"missing key: {key}"

    thesis = parsed.get("thesis") or {}
    if not isinstance(thesis.get("headline"), str) or len(thesis["headline"]) < 20:
        return "thesis.headline too short"
    body = thesis.get("body")
    if not isinstance(body, list) or not (2 <= len(body) <= 3):
        return f"thesis.body must be 2-3 paragraphs, got {len(body) if isinstance(body, list) else 'n/a'}"
    for i, p in enumerate(body):
        if not isinstance(p, str) or len(p) < 80:
            return f"thesis.body[{i}] too short ({len(p) if isinstance(p, str) else 'n/a'})"
    sb = thesis.get("statBlocks") or []
    if not isinstance(sb, list) or not (2 <= len(sb) <= 3):
        return f"thesis.statBlocks must be 2-3 items, got {len(sb) if isinstance(sb, list) else 'n/a'}"
    for s in sb:
        if not isinstance(s, dict) or not s.get("value") or not s.get("label"):
            return "thesis.statBlocks entry missing value/label"

    catch = parsed.get("catchment") or {}
    if not isinstance(catch.get("headline"), str) or len(catch["headline"]) < 20:
        return "catchment.headline too short"
    cbody = catch.get("body")
    if not isinstance(cbody, list) or not (1 <= len(cbody) <= 3):
        return f"catchment.body must be 1-3 paragraphs"
    locs = catch.get("locations") or []
    if not isinstance(locs, list) or len(locs) != 3:
        return f"catchment.locations must be exactly 3 entries, got {len(locs) if isinstance(locs, list) else 'n/a'}"
    for i, l in enumerate(locs):
        for key in ("label", "share", "reasoning"):
            if not isinstance(l.get(key), str) or not l[key].strip():
                return f"catchment.locations[{i}] missing {key}"
        if len(l["reasoning"]) < 40:
            return f"catchment.locations[{i}].reasoning too short"
        # share is a campaign-weight label, not a measured proportion.
        if len(l["share"]) > 24 or "%" in l["share"]:
            return f"catchment.locations[{i}].share must be a short weight label, no percentage"

    cm = parsed.get("campaignMath") or {}
    if not isinstance(cm.get("headline"), str) or len(cm["headline"]) < 15:
        return "campaignMath.headline too short"
    if not isinstance(cm.get("body"), str) or len(cm["body"]) < 80:
        return "campaignMath.body too short"
    cm_sb = cm.get("statBlocks") or []
    if not isinstance(cm_sb, list) or len(cm_sb) != 2:
        return f"campaignMath.statBlocks must be exactly 2 items"
    for s in cm_sb:
        if not isinstance(s, dict) or not s.get("value") or not s.get("label"):
            return "campaignMath.statBlocks entry missing value/label"

    # Editorial guardrails on prose
    prose_parts = [
        thesis["headline"],
        " ".join(body),
        catch["headline"],
        " ".join(cbody),
        " ".join(l["reasoning"] for l in locs),
        cm["headline"],
        cm["body"],
    ]
    prose = " ".join(prose_parts).lower()
    forbidden = [
        "stunning", "nestled", "boasting", "rare opportunity", "robust market",
        "hot market", "breathtaking", "magnificent", "must-see", "dream home",
    ]
    hit = [w for w in forbidden if w in prose]
    if hit:
        return f"forbidden word(s): {hit}"
    advice = ["you should", "we recommend", "now is a good time", "now is the time"]
    advice_hit = [p for p in advice if p in prose]
    if advice_hit:
        return f"advice pattern(s): {advice_hit}"

    # Fabricated channels / claims of buyer-origin data Fields does not have.
    ch_hit = [w for w in FORBIDDEN_CHANNELS if w in prose]
    if ch_hit:
        return f"forbidden channel/claim in prose: {ch_hit}"

    # campaignMath must carry NO invented active/passive precision.
    cm_prose = " ".join([cm.get("body", "")] + [str(s.get("value", "")) + " " + str(s.get("label", "")) for s in cm_sb])
    if re.search(r"\d\s*%", cm_prose):
        return "campaignMath must not contain a percentage (no invented active/passive precision)"

    return None


def resolve_buyers_narrative(
    address: str,
    suburb: str,
    features_basic: Dict[str, Any],
    notable_features: List[Dict[str, str]],
    matching_full_stack: int,
    active_listings_total: int,
    cohort_premiums: List[Dict[str, Any]],
    personas: List[Dict[str, Any]],
    pois: List[Dict[str, Any]],
    valuation_range: Optional[Dict[str, Any]] = None,
) -> Optional[Dict[str, Any]]:
    """Generate the buyers tab content. Requires personas already generated.
    Returns None on permanent failure."""

    if not personas or len(personas) < 3:
        logger.warning("  buyers narrative requires 3 personas — skipping")
        return None

    api_key = os.environ.get("ANTHROPIC_API_KEY")
    if not api_key:
        logger.warning("ANTHROPIC_API_KEY not set — skipping buyers narrative")
        return None

    try:
        from anthropic import Anthropic
    except ImportError:
        logger.warning("anthropic not installed — skipping buyers narrative")
        return None

    client = Anthropic(api_key=api_key)
    user_prompt = _format_inputs(
        address, suburb, features_basic or {}, notable_features or [],
        matching_full_stack or 0, active_listings_total or 0,
        cohort_premiums or [], personas, pois or [], valuation_range,
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
            "thesis": parsed["thesis"],
            "catchment": parsed["catchment"],
            "campaignMath": parsed["campaignMath"],
            "generated_at": datetime.now(timezone.utc).isoformat(),
            "model": MODEL,
            "attempt": attempt,
        }

    logger.error(f"buyers_narrative: all {MAX_RETRIES} attempts failed — last_error={last_error}")
    return {"error": last_error, "attempts": MAX_RETRIES}
