"""
Inline floor-plan classification + room-dimension analysis for the live
resolver chain.

The nightly batch pipeline runs floor-plan classification (step CA-006) and
a partial structural analysis (`house_plan`), but only on properties that
the batch has visited. For an on-demand submission of an off-market home
the resolver must do its own pass — otherwise the user gets no floor-plan
view and no room-by-room layout.

Two functions:

  classify_photos_for_floor_plan(urls) → list[str]
      Run GPT-4o-mini "is this a floor plan?" against each URL. Returns
      the URLs the model flagged YES. ~$0.001 per image.

  analyse_floor_plan(url) → dict
      Run GPT-4o vision against a single floor-plan image. Extracts room
      labels, dimensions, areas, total internal area, level count, and a
      confidence score. ~$0.05 per floor plan.

Output of `analyse_floor_plan` is the dict surfaced to the frontend at
`property.floor_plan` — see the schema documented inline.
"""

from __future__ import annotations

import json
import logging
import os
import re
from concurrent.futures import ThreadPoolExecutor, as_completed
from typing import Any, Dict, List, Optional

from openai import OpenAI

logger = logging.getLogger(__name__)

_CLIENT: Optional[OpenAI] = None


def _client() -> Optional[OpenAI]:
    """Lazy singleton. Returns None if no API key — caller skips work."""
    global _CLIENT
    if _CLIENT is not None:
        return _CLIENT
    key = os.environ.get("OPENAI_API_KEY")
    if not key:
        return None
    _CLIENT = OpenAI(api_key=key)
    return _CLIENT


# ---------------------------------------------------------------------- #
# Classification (a) — pick floor plans out of a photo list
# ---------------------------------------------------------------------- #

CLASSIFY_PROMPT = (
    "You are classifying property listing images. "
    "Is this image an architectural floor plan (a top-down 2D diagram of "
    "room layouts, walls, and dimensions)? "
    "Answer with exactly one word: YES or NO."
)


def _classify_one(url: str, model: str = "gpt-4o-mini") -> bool:
    """Return True iff the URL is a floor plan. Safe to call on any URL."""
    client = _client()
    if not client:
        return False
    try:
        resp = client.chat.completions.create(
            model=model,
            messages=[{
                "role": "user",
                "content": [
                    {"type": "text", "text": CLASSIFY_PROMPT},
                    {"type": "image_url", "image_url": {"url": url, "detail": "low"}},
                ],
            }],
            max_tokens=4,
            temperature=0,
        )
        raw = (resp.choices[0].message.content or "").strip().upper()
        return "YES" in raw
    except Exception as e:
        logger.debug(f"  classify_one threw on {url[:80]}: {e}")
        return False


def classify_photos_for_floor_plan(urls: List[str], max_workers: int = 6) -> List[str]:
    """Run classifier across a photo list in parallel. Returns the URLs
    flagged YES, preserving original order. Quietly returns [] if no
    OPENAI_API_KEY is set."""
    if not urls:
        return []
    if not _client():
        logger.info("  floor_plan classifier: OPENAI_API_KEY missing — skipping")
        return []

    results: Dict[int, bool] = {}
    with ThreadPoolExecutor(max_workers=max_workers) as pool:
        futures = {pool.submit(_classify_one, u): i for i, u in enumerate(urls)}
        for fut in as_completed(futures):
            idx = futures[fut]
            try:
                results[idx] = fut.result()
            except Exception:
                results[idx] = False
    return [urls[i] for i in range(len(urls)) if results.get(i)]


# ---------------------------------------------------------------------- #
# Structural analysis (c) — extract room dims + layout
# ---------------------------------------------------------------------- #

ANALYSE_PROMPT = """You are extracting structured data from an architectural floor plan image.

Return JSON ONLY, matching this exact schema:

{
  "rooms": [
    {
      "label": "Master Bedroom",           // human-readable room name from the plan
      "dimensions": "4.2 x 3.8",            // dimensions as printed on the plan, in metres (or empty string if not printed)
      "area_sqm": 15.96                     // computed or printed area in m² (or null)
    }
  ],
  "total_internal_area_sqm": 228,           // sum or as printed on the plan, m²
  "number_of_levels": 1,                    // 1, 2, or 3
  "has_garage": true,                       // boolean
  "has_pool_in_plan": false,                // boolean — is a pool drawn on the plan?
  "notes": "Short factual notes about the layout (≤140 chars)."
}

Rules:
- Use ONLY values that are visible or explicitly readable from the plan.
- If a value isn't in the plan, use null (for numbers) or an empty string (for text).
- Room labels MUST come from the plan — don't invent rooms not shown.
- Dimensions: report them in the format printed on the plan (typically "L x W" in metres).
- Output VALID JSON. No prose, no markdown fences, no surrounding commentary.
"""


_DIM_RE = re.compile(r"(?P<l>\d+(?:\.\d+)?)\s*[x×]\s*(?P<w>\d+(?:\.\d+)?)")


def _area_from_dims(dim_str: str) -> Optional[float]:
    """Parse "4.2 x 3.8" → 15.96. Returns None if not parseable."""
    if not dim_str:
        return None
    m = _DIM_RE.search(dim_str)
    if not m:
        return None
    try:
        return round(float(m.group("l")) * float(m.group("w")), 2)
    except (TypeError, ValueError):
        return None


def _enrich_room_areas(layout: Dict[str, Any]) -> Dict[str, Any]:
    """Compute area_sqm from dimensions where the model returned null. The
    vision pass is reliable on dimensions but inconsistent on computed
    areas, so we do the multiplication ourselves."""
    rooms = layout.get("rooms")
    if not isinstance(rooms, list):
        return layout
    for r in rooms:
        if not isinstance(r, dict):
            continue
        if r.get("area_sqm") in (None, 0):
            r["area_sqm"] = _area_from_dims(r.get("dimensions") or "")
    return layout


def _extract_json(text: str) -> Optional[Dict[str, Any]]:
    """Pull a JSON object out of the model's response. Tolerant to stray
    backticks or surrounding text."""
    if not text:
        return None
    # Strip code fences
    text = text.strip()
    if text.startswith("```"):
        text = re.sub(r"^```(?:json)?\s*", "", text)
        text = re.sub(r"\s*```$", "", text)
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        # Try to extract the largest {...} block
        m = re.search(r"\{[\s\S]*\}", text)
        if m:
            try:
                return json.loads(m.group(0))
            except json.JSONDecodeError:
                return None
        return None


def analyse_floor_plan(url: str, model: str = "gpt-4o") -> Optional[Dict[str, Any]]:
    """Run vision analysis against a floor-plan image. Returns the
    structured layout dict or None on failure.

    Use the higher-detail model (gpt-4o, not mini) — room labels and small
    printed dimensions on a floor plan need careful reading.
    """
    client = _client()
    if not client or not url:
        return None
    try:
        resp = client.chat.completions.create(
            model=model,
            messages=[{
                "role": "user",
                "content": [
                    {"type": "text", "text": ANALYSE_PROMPT},
                    {"type": "image_url", "image_url": {"url": url, "detail": "high"}},
                ],
            }],
            max_tokens=900,
            temperature=0,
        )
        raw = resp.choices[0].message.content or ""
        parsed = _extract_json(raw)
        if not parsed or not isinstance(parsed, dict):
            logger.warning(f"  analyse_floor_plan: bad JSON response: {raw[:140]}")
            return None
        return _enrich_room_areas(parsed)
    except Exception as e:
        logger.warning(f"  analyse_floor_plan threw: {e}")
        return None


# ---------------------------------------------------------------------- #
# Public entrypoint — used by slot_resolver
# ---------------------------------------------------------------------- #

def resolve_floor_plan(
    candidate_urls: List[str],
    existing_extracted: Optional[List[str]] = None,
) -> Optional[Dict[str, Any]]:
    """End-to-end. Given a set of photo URLs (the recovered gallery) and
    optionally any pre-classified floor-plan URLs from the nightly batch,
    return a dict:

        {
          "url": "<best-res floor-plan URL>",
          "alt_urls": [<other floor plans>],
          "layout": { rooms[], total_internal_area_sqm, number_of_levels,
                      has_garage, has_pool_in_plan, notes },
          "generated_at": "<iso>",
          "model": "gpt-4o",
        }

    Skips classification when `existing_extracted` is non-empty (the nightly
    batch already picked the floor plans — no need to re-spend GPT-4o-mini).
    Returns None when no floor plans are identifiable or analysis fails.
    """
    from datetime import datetime

    floor_plan_urls: List[str] = []
    if existing_extracted:
        # Trust the prior batch — they've already classified.
        floor_plan_urls = [u for u in existing_extracted if isinstance(u, str)]
    elif candidate_urls:
        logger.info(f"  floor_plan classifier: scanning {len(candidate_urls)} photos")
        floor_plan_urls = classify_photos_for_floor_plan(candidate_urls)
        logger.info(f"  floor_plan classifier: {len(floor_plan_urls)} floor plan(s) identified")

    if not floor_plan_urls:
        return None

    # Pick the highest-resolution floor plan URL for analysis. Domain
    # serves floor plans at both signed-thumb size and at /fit-in/5760x3240/
    # (the high-res variant). Prefer fit-in URLs first.
    sorted_urls = sorted(
        floor_plan_urls,
        key=lambda u: (
            "/fit-in/" in u,
            "5760" in u or "3240" in u,
            len(u),  # longer URL ≈ more detail-rich path
        ),
        reverse=True,
    )
    best_url = sorted_urls[0]

    layout = analyse_floor_plan(best_url)
    if not layout:
        # Even without structural analysis, surface the floor plan image.
        return {
            "url": best_url,
            "alt_urls": sorted_urls[1:],
            "layout": None,
            "generated_at": datetime.utcnow().isoformat() + "Z",
            "model": None,
        }

    logger.info(
        f"  floor_plan analysis: {len(layout.get('rooms') or [])} rooms, "
        f"{layout.get('total_internal_area_sqm')} m², "
        f"{layout.get('number_of_levels')} level(s)"
    )
    return {
        "url": best_url,
        "alt_urls": sorted_urls[1:],
        "layout": layout,
        "generated_at": datetime.utcnow().isoformat() + "Z",
        "model": "gpt-4o",
    }
