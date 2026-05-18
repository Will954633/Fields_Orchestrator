"""
Hero photo selection — score property photos with GPT-4o-mini and pick the
best exterior shot for the mini-site hero.

The Domain scraper sometimes picks a poor first image (a floor plan, an
interior corner, a small detail). GPT-4o-mini scores each photo on its
suitability as a hero — wide exterior framing, lighting, the whole house
visible — and we promote the highest-scored one.

Cost: ~$0.001-0.002 per resolution (4-6 photos at 'low' detail).

Usage:
    from scripts.property_reports.hero_photo import score_and_pick_hero
    result = score_and_pick_hero(photo_urls)
    # → { "hero_url": "...", "scores": [{"url": ..., "score": 0-100, "reason": ...}], "model": "gpt-4o-mini" }
"""
from __future__ import annotations

import json
import logging
import os
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)


MAX_CANDIDATES = 8       # cap to keep cost predictable
DETAIL_LEVEL = "low"     # 512x512 = ~85 tokens per image vs 'high' = ~1100+

SYSTEM_PROMPT = """You score property photos for hero-image suitability on a seller-facing report.

Each photo gets a score 0-100 and one short reason. Prefer:
  - Wide exterior shots that frame the whole house
  - Front elevations (street view) with the facade visible
  - Drone / aerial shots that show the property in context
  - Well-lit, daytime images
  - Clean composition (minimal cars, garbage bins, real estate signs in frame)

Score lower:
  - Floor plans, blueprints, site plans
  - Tight interior details (kitchen, bedroom, bathroom close-ups)
  - Single-feature shots (just the pool, just a window, just the front door)
  - Twilight / dawn photos (often dramatic but harder to read at thumbnail size)
  - Photos with heavy real-estate agent branding overlaid

Return JSON ONLY in the format:
{"scores": [{"index": 0, "score": 87, "reason": "Wide exterior, sun-lit facade"}]}

No prose, no markdown, just the JSON object."""


def score_and_pick_hero(photo_urls: List[str], *, max_photos: int = MAX_CANDIDATES) -> Optional[Dict[str, Any]]:
    """Score a list of photo URLs and return the best one for hero usage.

    Returns None on any failure (API key missing, network error, malformed
    response) so the caller can fall back to the scraper's hero pick.
    """
    api_key = os.environ.get("OPENAI_API_KEY")
    if not api_key:
        logger.warning("OPENAI_API_KEY not set — skipping AI hero selection")
        return None
    if not photo_urls:
        return None

    candidates = photo_urls[:max_photos]

    try:
        # Defer import so the module loads even without openai installed
        from openai import OpenAI
    except ImportError:
        logger.warning("openai package not installed — skipping AI hero selection")
        return None

    client = OpenAI(api_key=api_key)

    user_content: List[Dict[str, Any]] = [
        {"type": "text", "text": f"Score these {len(candidates)} photos. Index 0..{len(candidates)-1}."}
    ]
    for url in candidates:
        user_content.append({
            "type": "image_url",
            "image_url": {"url": url, "detail": DETAIL_LEVEL},
        })

    try:
        response = client.chat.completions.create(
            model="gpt-4o-mini",
            messages=[
                {"role": "system", "content": SYSTEM_PROMPT},
                {"role": "user", "content": user_content},
            ],
            response_format={"type": "json_object"},
            temperature=0.1,
            max_tokens=600,
        )
    except Exception as e:
        logger.warning(f"Hero photo scoring API call failed: {e}")
        return None

    try:
        raw = response.choices[0].message.content
        parsed = json.loads(raw)
        scores = parsed.get("scores") or []
    except (json.JSONDecodeError, KeyError, AttributeError) as e:
        logger.warning(f"Hero photo scoring JSON parse failed: {e}")
        return None

    if not scores:
        return None

    # Normalise + sort by score desc
    valid = []
    for s in scores:
        idx = s.get("index")
        if not isinstance(idx, int) or idx < 0 or idx >= len(candidates):
            continue
        score = s.get("score")
        if not isinstance(score, (int, float)):
            continue
        valid.append({
            "url": candidates[idx],
            "score": int(score),
            "reason": (s.get("reason") or "").strip()[:140],
        })

    if not valid:
        return None

    valid.sort(key=lambda x: x["score"], reverse=True)
    top = valid[0]
    return {
        "hero_url": top["url"],
        "hero_score": top["score"],
        "hero_reason": top["reason"],
        "scores": valid,
        "model": "gpt-4o-mini",
    }
