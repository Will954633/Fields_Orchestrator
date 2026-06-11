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

# Repo-root import (this file lives at scripts/property_reports/, shared/ at repo root)
import sys as _sys
from pathlib import Path as _Path
_REPO = _Path(__file__).resolve().parents[2]
if str(_REPO) not in _sys.path:
    _sys.path.insert(0, str(_REPO))
from shared.domain_urls import to_bucket_api_url, is_bucket_api  # noqa: E402

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
# Claude (Anthropic) vision — PRIMARY engine
# ---------------------------------------------------------------------- #
# Claude is tried first for both classification and analysis (see
# _classify_one / analyse_floor_plan). The OpenAI client below it is a dormant
# fallback only, used when Claude is unavailable but an OpenAI key is set —
# kept because the 2026-06 OpenAI quota exhaustion showed the value of a
# second vision source.
_ANTHROPIC_CLIENT = None
# Sonnet, not Opus: floor-plan reading is structured OCR, where Sonnet leads on
# extraction accuracy at ~40% of Opus's cost. Opus-tier was burning credits fast
# on the cohort backfill (~1,200 plans/run). Override via FLOORPLAN_CLAUDE_MODEL.
_CLAUDE_VISION_MODEL = os.environ.get("FLOORPLAN_CLAUDE_MODEL", "claude-sonnet-4-6")
_CLAUDE_MEDIA_TYPES = {"image/jpeg", "image/png", "image/gif", "image/webp"}


def _anthropic_client():
    """Lazy singleton for the Claude fallback. None if SDK or key missing."""
    global _ANTHROPIC_CLIENT
    if _ANTHROPIC_CLIENT is not None:
        return _ANTHROPIC_CLIENT
    key = os.environ.get("ANTHROPIC_API_KEY")
    if not key:
        return None
    try:
        import anthropic
    except ImportError:
        logger.debug("  anthropic SDK not installed — no Claude vision fallback")
        return None
    _ANTHROPIC_CLIENT = anthropic.Anthropic(api_key=key)
    return _ANTHROPIC_CLIENT


def _claude_vision_text(url: str, prompt: str, max_tokens: int = 1200) -> Optional[str]:
    """Run a single vision prompt through Claude, returning the raw text (or
    None if the fallback is unavailable / the call fails). Fetches the image and
    sends it base64 — Domain bucket URLs aren't reliably fetchable by the
    provider, so we proxy the bytes ourselves."""
    client = _anthropic_client()
    if not client or not url:
        return None
    try:
        import base64
        import requests
        r = requests.get(url, timeout=30)
        r.raise_for_status()
        ctype = (r.headers.get("content-type") or "").split(";")[0].strip().lower()
        c = r.content
        # Magic-byte sniff — CDN sometimes mislabels (e.g. GIF as image/jpeg), which 400s.
        if c[:3] == b"\xff\xd8\xff":
            media = "image/jpeg"
        elif c[:8] == b"\x89PNG\r\n\x1a\n":
            media = "image/png"
        elif c[:6] in (b"GIF87a", b"GIF89a"):
            media = "image/gif"
        elif c[:4] == b"RIFF" and c[8:12] == b"WEBP":
            media = "image/webp"
        else:
            media = ctype if ctype in _CLAUDE_MEDIA_TYPES else "image/jpeg"
        b64 = base64.standard_b64encode(c).decode()
        resp = client.messages.create(
            model=_CLAUDE_VISION_MODEL,
            max_tokens=max_tokens,
            temperature=0,
            messages=[{
                "role": "user",
                "content": [
                    {"type": "image", "source": {"type": "base64", "media_type": media, "data": b64}},
                    {"type": "text", "text": prompt},
                ],
            }],
        )
        return (resp.content[0].text if resp.content else "") or ""
    except Exception as e:
        logger.warning(f"  claude vision fallback threw on {url[:80]}: {e}")
        return None


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
    """Return True iff the URL is a floor plan. Safe to call on any URL.

    Claude is the primary engine; the OpenAI path is retained only as a dormant
    fallback for the (unlikely) case Claude is unavailable but an OpenAI key is.
    """
    txt = _claude_vision_text(url, CLASSIFY_PROMPT, max_tokens=8)
    if txt is not None:
        return "YES" in txt.strip().upper()
    client = _client()
    if client:
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
            return "YES" in (resp.choices[0].message.content or "").strip().upper()
        except Exception as e:
            logger.debug(f"  classify_one (openai fallback) threw on {url[:80]}: {e}")
    return False


def classify_photos_for_floor_plan(urls: List[str], max_workers: int = 6) -> List[str]:
    """Run classifier across a photo list in parallel. Returns the URLs
    flagged YES, preserving original order. Uses Claude vision (primary);
    returns [] only if no vision provider (Claude or OpenAI) is configured."""
    if not urls:
        return []
    if not _anthropic_client() and not _client():
        logger.info("  floor_plan classifier: no vision provider configured — skipping")
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
  "stated_internal_area_sqm": 173,          // the INTERNAL / LIVING area PRINTED in the plan's area summary box (null if not printed)
  "stated_garage_area_sqm": 33,             // the GARAGE area printed in the summary box (null if not printed)
  "stated_external_area_sqm": 107,          // the EXTERNAL / COVERED / PORCH / ALFRESCO area printed (null if not printed)
  "stated_total_area_sqm": 313,             // the TOTAL / APPROX TOTAL area printed in the summary box (null if not printed)
  "total_internal_area_sqm": 173,           // best internal-living figure: prefer stated_internal; else sum of room areas
  "area_source": "printed_summary",         // "printed_summary" if read from a printed box, "room_sum" if you summed rooms, "none" if unknown
  "number_of_levels": 1,                    // 1, 2, or 3
  "has_garage": true,                       // boolean
  "has_pool_in_plan": false,                // boolean — is a pool drawn on the plan?
  "notes": "Short factual notes about the layout (≤140 chars)."
}

Rules:
- FIRST look for a printed area summary box on the plan (often a table or list reading "Internal", "Living", "Garage", "Porch/Alfresco/External", "Total" or "Approx Total" with m² figures). Transcribe those EXACTLY into the stated_* fields. These printed figures are authoritative — do NOT compute them.
- "Internal" / "Living" area is habitable internal space EXCLUDING garage and covered outdoor. Put that in stated_internal_area_sqm and in total_internal_area_sqm, and set area_source to "printed_summary".
- Only if there is NO printed summary box, sum the room areas into total_internal_area_sqm and set area_source to "room_sum".
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

    Claude is the primary engine (lower hallucination on diagrams, and it reads
    the printed area-summary box reliably). The OpenAI path is a dormant
    fallback only — used if Claude is unavailable but an OpenAI key is set.
    """
    if not url:
        return None
    raw = _claude_vision_text(url, ANALYSE_PROMPT, max_tokens=1200) or ""
    if not raw:
        client = _client()
        if client:
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
            except Exception as e:
                logger.warning(f"  analyse_floor_plan (openai fallback) threw: {e}")
    if not raw:
        return None
    parsed = _extract_json(raw)
    if not parsed or not isinstance(parsed, dict):
        logger.warning(f"  analyse_floor_plan: bad JSON response: {raw[:140]}")
        return None
    return _enrich_room_areas(parsed)


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

    # Normalize every Domain CDN URL to its bucket-api equivalent. The CDN
    # encodes a signed-resize hash that can silently return a thumbnail;
    # bucket-api bypasses signing and always serves the original full-res
    # file. No-op for non-Domain URLs.
    floor_plan_urls = [to_bucket_api_url(u) for u in floor_plan_urls]

    # Pick the best floor plan URL for analysis. Prefer bucket-api (always
    # full-res), then /fit-in/5760x3240 variants, then longest URL.
    sorted_urls = sorted(
        floor_plan_urls,
        key=lambda u: (
            is_bucket_api(u),
            "/fit-in/" in u,
            "5760" in u or "3240" in u,
            len(u),
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
