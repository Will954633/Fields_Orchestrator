"""
On-demand photo recovery for the live resolver chain.

The nightly scraper captures `property_images_original` (full-res bucket-api
URLs) reliably for currently-listed homes, but sparse for sold/off-market
ones — Domain's Apollo state only surfaces the most-recent sale's hero in
that field. For older photos the scraper instead captures `domain_image_urls`,
which are rimh2 (Thumbor) URLs signed for a fixed 150×100 output.

KEY INSIGHT: Each rimh2 URL embeds the original image's path on Domain's
static bucket (e.g. `16539274_1_1_230628_111035-w1920-h1333`). That same
path served from `https://b.domainstatic.com.au/<path>` returns the
full-res JPEG (1920×1333, ~600 KB+) with no auth required.

So we don't actually need to re-scrape Domain. We can transform the
thumbnails we already have into full-res URLs via URL surgery alone —
zero new HTTP calls, runs in microseconds.

Used by the resolver chain when `property_images_original` has fewer than
THIN_THRESHOLD unique full-res photos.
"""

from __future__ import annotations

import logging
import re
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)

# Below this many unique full-res photos, fire the recovery path.
THIN_THRESHOLD = 6

# Match the path tail in a rimh2 URL:
# https://rimh2.domainstatic.com.au/<sig>=/<size_dir>/.../filters:.../<PATH>
# where <PATH> looks like "16539274_1_1_230628_111035-w1920-h1333"
# We accept either:
#   - .../<PATH>(?: more) at the end of the URL
#   - .../<PATH>?<query>
_PATH_TAIL = re.compile(
    r"/(?P<path>\d+_\d+_\d+_\d+_\d+-w\d+-h\d+)(?:[?#]|$)"
)


def _full_res_url_from_thumb(rimh2_url: str) -> Optional[str]:
    """Transform a Domain rimh2 thumbnail URL into the full-res
    b.domainstatic.com.au URL by lifting the image-path tail.

    Returns None if the URL doesn't carry an extractable path."""
    if not rimh2_url or "rimh2.domainstatic.com.au" not in rimh2_url:
        return None
    m = _PATH_TAIL.search(rimh2_url + "?")  # add ? so end-of-string matches
    if not m:
        return None
    return f"https://b.domainstatic.com.au/{m.group('path')}"


def _unique_fullres_count(doc: Dict[str, Any]) -> int:
    """Count unique full-res photos already on the doc (bucket-api URLs,
    b.domainstatic URLs, or rimh2 URLs with a /fit-in/ size directive)."""
    originals = doc.get("property_images_original") or []
    refreshed = doc.get("property_images_refreshed") or []
    candidates = list(originals) + list(refreshed)
    seen = set()
    for u in candidates:
        if not isinstance(u, str):
            continue
        u = u.rstrip("\\").strip()
        if not u:
            continue
        if (
            "bucket-api.domain.com.au" in u
            or "b.domainstatic.com.au" in u
            or "/fit-in/" in u
        ):
            seen.add(u)
    return len(seen)


def needs_refresh(doc: Dict[str, Any], threshold: int = THIN_THRESHOLD) -> bool:
    """True when the doc has fewer than threshold unique full-res photos
    AND the doc has thumbnail URLs available to transform."""
    if _unique_fullres_count(doc) >= threshold:
        return False
    return bool(doc.get("domain_image_urls") or (
        (doc.get("scraped_data_v2") or {}).get("image_urls")
    ))


def recover_photos(doc: Dict[str, Any], coll=None) -> List[str]:
    """Build a list of full-res photo URLs for this doc by transforming the
    thumbnail URLs already in `domain_image_urls` (or scraped_data_v2.image_urls
    as a fallback) into b.domainstatic.com.au URLs. Optionally writes the
    result to `property_images_refreshed` on the subject doc.

    Returns the list of recovered URLs in source-order (gallery position 1
    first). Empty list if no thumbnails exist or none can be transformed.
    """
    sources: List[str] = []
    seen = set()

    # Combine sources, preserving order. domain_image_urls is the most
    # commonly populated; scraped_data_v2.image_urls is the v2-scrape copy.
    for src_field in ("domain_image_urls",):
        for u in (doc.get(src_field) or []):
            if isinstance(u, str) and u not in seen:
                seen.add(u)
                sources.append(u)
    v2 = doc.get("scraped_data_v2") or {}
    for u in (v2.get("image_urls") or []):
        if isinstance(u, str) and u not in seen:
            seen.add(u)
            sources.append(u)

    if not sources:
        return []

    recovered: List[str] = []
    recovered_paths = set()
    for url in sources:
        full = _full_res_url_from_thumb(url)
        if not full:
            continue
        # Dedupe by the underlying image path
        path = full.rsplit("/", 1)[-1]
        if path in recovered_paths:
            continue
        recovered_paths.add(path)
        recovered.append(full)

    if not recovered:
        return []

    if coll is not None and doc.get("_id"):
        from datetime import datetime
        try:
            coll.update_one(
                {"_id": doc["_id"]},
                {"$set": {
                    "property_images_refreshed": recovered,
                    "property_images_refreshed_at": datetime.utcnow(),
                }},
            )
            logger.info(
                f"  recover_photos: wrote {len(recovered)} full-res URLs "
                f"to subject doc (transformed from {len(sources)} thumbnails)"
            )
        except Exception as e:
            logger.warning(f"  recover_photos write failed: {e}")

    return recovered
