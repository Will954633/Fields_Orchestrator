"""
Market narrative resolver — Opus 4.7 writes a 50-90 word paragraph
explaining what the suburb's market numbers mean for a seller right now.

This is the first narrative-LLM resolver in the mini-site chain (Day 5 of
the 14-day rollout). The pattern it establishes — system prompt with
editorial guardrails + structured input + retry + schema validation +
audit trail — gets reused by the scarcity/positioning/buyers resolvers.

Editorial rules (from CLAUDE.md, replicated in the prompt):
  - No advice. NEVER tell the reader what to do.
  - No predictions. Use conditional language only.
  - No forbidden words: "stunning", "nestled", "boasting", "rare
    opportunity", "robust market".
  - Cite data source + period.
  - Single transaction figures are exact, never rounded.

Inputs:
  - market: dict with active_listings_count, sold_transaction_count,
    rolling_12m_yoy_pct, median_dom, median_dom_historical,
    growth_since_baseline_pct, rolling_12m_median
  - suburb: display name (e.g. "Robina")
  - bedroom_band: optional int — subject's bedroom count for cohort framing

Output (None on failure):
  {
    "text": "Robina recorded 2,373 sold transactions...",
    "generated_at": "2026-05-18T11:30:00Z",
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
from typing import Any, Dict, Optional

logger = logging.getLogger(__name__)


MAX_RETRIES = 3
RETRY_BACKOFF_SECONDS = [2, 5, 12]  # exponential-ish

MODEL = "claude-opus-4-7"
MAX_TOKENS = 600


SYSTEM_PROMPT = """You write a short paragraph (50-90 words, one paragraph) describing what a suburb's current market data means for a property seller.

ABSOLUTE RULES — violate any and the output will be rejected:
  1. NO ADVICE. Never tell the reader what to do ("you should", "consider", "now is a good time"). Data only.
  2. NO PREDICTIONS. Use conditional language ("if X continues, the data suggests Y"). Never "prices will rise/fall".
  3. NO FORBIDDEN WORDS: stunning, nestled, boasting, rare opportunity, robust market, hot market, booming.
  4. EXACT FIGURES only. Don't round transaction counts or prices. "$1,250,000" not "$1.25m".
  5. CITE the period and source ("over the past 24 months", "Fields suburb cohort", "Abelson et al. 2005 for wage-price linkage").

STRUCTURE:
  - One paragraph, 50-90 words.
  - Lead with the most load-bearing fact (typically transaction volume or active stock).
  - Include 2-3 supporting numbers from the data.
  - End with one sentence of interpretation in conditional tense ("if wage growth holds at X, the data points to ...").
  - If you reference wages leading prices, cite Abelson et al. (2005) — r=0.940 correlation, 1.71× income elasticity for Gold Coast.

VOICE:
  - Plain, declarative. No marketing language.
  - Address the seller directly ("your suburb", "the cohort against which your home will be compared").
  - Honest about limitations. If a number is small or backwards-looking, say so.

Return ONLY the paragraph text. No JSON wrapper, no preamble, no markdown."""


def _format_market_for_prompt(market: Dict[str, Any], suburb: str, bedroom_band: Optional[int]) -> str:
    """Render the market dict as a tidy facts block for the model."""
    lines = [f"SUBURB: {suburb}"]
    if bedroom_band:
        lines.append(f"SUBJECT BEDROOM BAND: {bedroom_band}")
    lines.append("")
    lines.append("CURRENT MARKET DATA:")
    fields = [
        ("active_listings_count", "Active listings (all bands)"),
        ("sold_transaction_count", "Sold transactions (24-month cohort)"),
        ("rolling_12m_median", "Rolling 12-month median sale price"),
        ("rolling_12m_yoy_pct", "Rolling 12-month median YoY change (%)"),
        ("median_dom", "Median days-on-market (current quarter)"),
        ("median_dom_historical", "Median days-on-market (historical)"),
        ("dom_yoy_change", "Days-on-market YoY change"),
        ("growth_since_baseline_pct", "Growth since baseline (%)"),
        ("baseline_period", "Baseline period"),
        ("latest_median_price", "Latest quarter median price"),
    ]
    for key, label in fields:
        v = market.get(key)
        if v is None:
            continue
        if "price" in key or key == "rolling_12m_median":
            try:
                v = f"${int(v):,}"
            except (TypeError, ValueError):
                pass
        lines.append(f"  - {label}: {v}")
    return "\n".join(lines)


def _validate_output(text: str) -> Optional[str]:
    """Return error message if text fails validation, None if ok."""
    if not text or len(text.strip()) < 50:
        return "output too short"
    if len(text) > 1200:
        return "output too long"

    forbidden = ["stunning", "nestled", "boasting", "rare opportunity", "robust market", "hot market", "booming"]
    lower = text.lower()
    hit = [w for w in forbidden if w in lower]
    if hit:
        return f"forbidden word(s) found: {hit}"

    # Hard-bounce advice patterns
    advice_patterns = [
        "you should",
        "we recommend",
        "now is a good time",
        "now is the time",
        "we suggest",
        "you must",
    ]
    advice_hit = [p for p in advice_patterns if p in lower]
    if advice_hit:
        return f"advice pattern(s) found: {advice_hit}"

    # Reject confident future-tense predictions
    pred_patterns = ["prices will rise", "prices will fall", "the market will", "values will increase", "values will decrease"]
    pred_hit = [p for p in pred_patterns if p in lower]
    if pred_hit:
        return f"prediction pattern(s) found: {pred_hit}"

    return None


def resolve_market_narrative(
    market: Dict[str, Any],
    suburb: str,
    bedroom_band: Optional[int] = None,
    *,
    address: Optional[str] = None,
) -> Optional[Dict[str, Any]]:
    """Generate the market narrative with retry. Returns None if all attempts
    fail validation or the API call errors out."""

    if not market or not suburb:
        return None

    api_key = os.environ.get("ANTHROPIC_API_KEY")
    if not api_key:
        logger.warning("ANTHROPIC_API_KEY not set — skipping market narrative")
        return None

    try:
        from anthropic import Anthropic
    except ImportError:
        logger.warning("anthropic package not installed — skipping market narrative")
        return None

    client = Anthropic(api_key=api_key)
    user_prompt = _format_market_for_prompt(market, suburb, bedroom_band)

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

        # Extract text from response content blocks
        try:
            text = "".join(
                getattr(b, "text", "") for b in response.content
                if getattr(b, "type", None) == "text"
            ).strip()
        except Exception as e:
            last_error = f"response parse error attempt {attempt}: {e}"
            logger.warning(f"  {last_error}")
            continue

        validation_err = _validate_output(text)
        if validation_err:
            last_error = f"validation failed attempt {attempt}: {validation_err}"
            logger.warning(f"  {last_error}")
            if attempt < MAX_RETRIES:
                time.sleep(RETRY_BACKOFF_SECONDS[min(attempt - 1, len(RETRY_BACKOFF_SECONDS) - 1)])
            continue

        return {
            "text": text,
            "generated_at": datetime.now(timezone.utc).isoformat(),
            "model": MODEL,
            "inputs_snapshot": {
                "suburb": suburb,
                "bedroom_band": bedroom_band,
                "address": address,
                "market": {k: v for k, v in market.items() if v is not None},
            },
            "attempt": attempt,
        }

    logger.error(f"market_narrative: all {MAX_RETRIES} attempts failed — last_error={last_error}")
    return {"error": last_error, "attempts": MAX_RETRIES}
