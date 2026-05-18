"""
Hero photo selection — score property photos with GPT-4o-mini and pick the
best exterior shot for the mini-site hero.

The Domain scraper sometimes picks a poor first image (a floor plan, an
interior corner, a small detail). GPT-4o-mini scores each photo on its
suitability as a hero — wide exterior framing, lighting, the whole house
visible — and we promote the highest-scored one.

Day 6 resilience: photos are pre-downloaded as bytes and sent to OpenAI
as base64 data URLs. The Domain CDN serves slowly enough that OpenAI's
URL-fetch timeout triggers; downloading server-side first eliminates that
race. Each photo download has its own short timeout — if a photo can't be
fetched in time we just exclude it from the scoring set rather than
fail the whole resolver.

Cost: ~$0.001-0.002 per resolution (4-6 photos at 'low' detail).

Usage:
    from scripts.property_reports.hero_photo import score_and_pick_hero
    result = score_and_pick_hero(photo_urls)
    # → { "hero_url": "...", "scores": [{"url": ..., "score": 0-100, "reason": ...}], "model": "gpt-4o-mini" }
"""
from __future__ import annotations

import base64
import concurrent.futures
import json
import logging
import os
import urllib.request
from typing import Any, Dict, List, Optional, Tuple

logger = logging.getLogger(__name__)


MAX_CANDIDATES = 8       # cap to keep cost predictable
DETAIL_LEVEL = "low"     # 512x512 = ~85 tokens per image vs 'high' = ~1100+
PHOTO_FETCH_TIMEOUT = 8.0  # per-image; OpenAI's own download timeout is shorter
MAX_PHOTO_BYTES = 4 * 1024 * 1024  # 4MB safety cap; Domain images are ~150-400KB

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


def _download_one(url: str) -> Optional[Tuple[str, str]]:
    """Fetch a single photo. Returns (url, base64-data-url) or None on failure.

    The Domain CDN occasionally serves slowly. Capping per-photo at
    PHOTO_FETCH_TIMEOUT means a slow image just gets excluded from the
    scoring set rather than blocking the whole resolver.
    """
    try:
        req = urllib.request.Request(url, headers={"User-Agent": "Fields-Mini-Site/1.0"})
        with urllib.request.urlopen(req, timeout=PHOTO_FETCH_TIMEOUT) as resp:
            content_type = resp.headers.get("Content-Type", "image/jpeg").split(";")[0].strip()
            if not content_type.startswith("image/"):
                return None
            data = resp.read(MAX_PHOTO_BYTES + 1)
            if len(data) > MAX_PHOTO_BYTES:
                logger.debug(f"  photo too large ({len(data)} bytes), skip: {url[:80]}")
                return None
            b64 = base64.b64encode(data).decode("ascii")
            return (url, f"data:{content_type};base64,{b64}")
    except Exception as e:
        logger.debug(f"  photo fetch failed {url[:60]}: {e}")
        return None


def _download_in_parallel(urls: List[str]) -> List[Tuple[str, str]]:
    """Fetch up to len(urls) photos concurrently. Order preserved by URL match."""
    results: Dict[str, Optional[Tuple[str, str]]] = {url: None for url in urls}
    with concurrent.futures.ThreadPoolExecutor(max_workers=min(8, len(urls))) as ex:
        future_to_url = {ex.submit(_download_one, url): url for url in urls}
        for fut in concurrent.futures.as_completed(future_to_url, timeout=PHOTO_FETCH_TIMEOUT * 2):
            url = future_to_url[fut]
            try:
                results[url] = fut.result()
            except Exception:
                results[url] = None
    return [r for r in (results[url] for url in urls) if r is not None]


def score_and_pick_hero(photo_urls: List[str], *, max_photos: int = MAX_CANDIDATES) -> Optional[Dict[str, Any]]:
    """Score a list of photo URLs and return the best one for hero usage.

    Returns None on any failure (API key missing, network error, malformed
    response) so the caller can fall back to the scraper's hero pick.

    Day 6: photos are pre-downloaded server-side and sent to OpenAI as
    base64 data URLs. This avoids the Domain CDN timeout issues that hit
    the URL-fetch path.
    """
    api_key = os.environ.get("OPENAI_API_KEY")
    if not api_key:
        logger.warning("OPENAI_API_KEY not set — skipping AI hero selection")
        return None
    if not photo_urls:
        return None

    candidates = photo_urls[:max_photos]

    # Pre-download in parallel. Photos that fail to fetch are dropped from
    # the scoring set rather than blocking the resolver.
    downloaded = _download_in_parallel(candidates)
    if not downloaded:
        logger.warning("hero photo: zero photos downloaded successfully — skipping AI selection")
        return None

    if len(downloaded) < len(candidates):
        logger.info(
            f"  hero photo: {len(downloaded)}/{len(candidates)} photos fetched ({len(candidates) - len(downloaded)} timed out)"
        )

    try:
        # Defer import so the module loads even without openai installed
        from openai import OpenAI
    except ImportError:
        logger.warning("openai package not installed — skipping AI hero selection")
        return None

    client = OpenAI(api_key=api_key)

    # Build the user content with base64 data URLs in the same order as `downloaded`
    user_content: List[Dict[str, Any]] = [
        {"type": "text", "text": f"Score these {len(downloaded)} photos. Index 0..{len(downloaded)-1}."}
    ]
    candidates = [url for url, _ in downloaded]  # rebind so index→url stays consistent
    for _, data_url in downloaded:
        user_content.append({
            "type": "image_url",
            "image_url": {"url": data_url, "detail": DETAIL_LEVEL},
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
