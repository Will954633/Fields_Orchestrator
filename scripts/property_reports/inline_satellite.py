"""
On-demand aerial / satellite analysis for the live resolver chain.

The nightly batch step 117 fetches a Google Maps Static satellite tile
(zoom 19, with a red pin on the lot) and runs a structured vision pass
that returns two blocks:

  - `categories`: machine-readable buckets (adjacency, detractants,
    amenity_premiums, lot_characteristics, neighbourhood) — used by
    downstream resolvers and the frontend filters.
  - `narrative`: a free-form structured dict (surrounding_land_use,
    road_proximity, green_cover, lot_assessment, neighbour_density,
    pool_and_outdoor, flood_drainage_risk, construction_activity,
    parking_access, buyer_highlights, overall_setting).

Coverage from that batch is sparse (~6% on Robina, <2% on the other core
suburbs). The product target is off-market homeowners — every submitted
address needs aerial analysis, so the resolver must run it on-demand
when the doc lacks it.

This module:
  - returns the existing `satellite_analysis` field unchanged if present;
  - otherwise geocodes the address, fetches the tile, uploads to blob,
    runs the GPT vision pass, writes back to the subject doc, and returns
    the same shape.

Cost when triggered: ~$0.05 in GPT vision + 1 Google Maps Static call
(free under 100k/day). When the doc already has analysis: $0, instant.
"""

from __future__ import annotations

import logging
import os
import sys
from datetime import datetime
from typing import Any, Dict, Optional

logger = logging.getLogger(__name__)

# Lazy-import target — we don't want to pull the whole step117 module
# (with its CLI parser, batch loops, etc.) into the resolver process.
_step117 = None


def _get_step117():
    """Import step117 lazily so the resolver module stays light when no
    on-demand satellite work happens."""
    global _step117
    if _step117 is not None:
        return _step117
    try:
        sys.path.insert(
            0,
            os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..")),
        )
        import scripts.step117_satellite_analysis as mod
        _step117 = mod
        return mod
    except Exception as e:
        logger.warning(f"  step117 import failed: {e}")
        return None


def _has_existing_analysis(doc: Dict[str, Any]) -> bool:
    """True if the nightly batch already produced a usable result for this
    doc. Quick check: must have an image_url + at least one category bucket."""
    sa = doc.get("satellite_analysis") or {}
    if not sa.get("satellite_image_url"):
        return False
    cats = sa.get("categories") or {}
    return bool(cats) and any(cats.values())


def _subject_latlng(doc: Dict[str, Any]) -> Optional[tuple]:
    """Pull lat/lng from the doc — same logic as the resolver's
    subject_latlng() helper."""
    lat = doc.get("LATITUDE") or doc.get("latitude") or doc.get("lat")
    lng = doc.get("LONGITUDE") or doc.get("longitude") or doc.get("lng")
    if lat is None or lng is None:
        return None
    try:
        return (float(lat), float(lng))
    except (TypeError, ValueError):
        return None


def resolve_satellite(
    subject_doc: Dict[str, Any],
    suburb_key: str,
    db_subject_coll=None,
    db_label: str = "for_sale",
) -> Optional[Dict[str, Any]]:
    """End-to-end resolver for the property's aerial view.

    Returns the existing satellite_analysis dict when one is on the doc.
    Otherwise:
      1. Get lat/lng (from doc, or geocode the address).
      2. Fetch a Google Maps Static satellite image (with red pin on the lot).
      3. Upload it to blob storage so the frontend can render it.
      4. Run the GPT vision pass for structured categories + narrative.
      5. Write the result to `satellite_analysis` on the subject doc.
      6. Return the dict.

    Returns None on hard failures (missing API keys, no coordinates,
    geocoding/network error).
    """
    if _has_existing_analysis(subject_doc):
        logger.info("  satellite: existing analysis on doc — reusing")
        return subject_doc.get("satellite_analysis")

    s117 = _get_step117()
    if not s117:
        return None

    if not s117.GOOGLE_MAPS_API_KEY:
        logger.info("  satellite: GOOGLE_MAPS_STATIC_API_KEY not set — skipping")
        return None

    address = subject_doc.get("address") or ""
    suburb_display = (subject_doc.get("suburb") or suburb_key or "").replace("_", " ").title()
    latlng = _subject_latlng(subject_doc)

    # 1) Fetch the satellite tile
    image_bytes = s117.fetch_satellite_image(
        lat=latlng[0] if latlng else None,
        lng=latlng[1] if latlng else None,
        address=address or None,
    )
    if not image_bytes:
        logger.warning(f"  satellite: image fetch failed for {address}")
        return None

    # 2) Upload to blob (best-effort — don't block analysis on upload error)
    property_id = str(subject_doc.get("_id") or "")
    image_url = None
    try:
        image_url = s117.upload_satellite_to_blob(
            None, image_bytes, suburb_key or "unknown",
            property_id or "unknown", db_label=db_label,
        )
    except Exception as e:
        logger.warning(f"  satellite: blob upload failed (continuing without URL): {e}")

    # 3) GPT vision pass
    analysis = s117.analyse_satellite_image(image_bytes, address, suburb_key or suburb_display)
    if not analysis:
        logger.warning(f"  satellite: GPT analysis returned nothing for {address}")
        return None

    record = {
        "categories": analysis.get("categories") or {},
        "narrative": analysis.get("narrative") or {},
        "satellite_image_url": image_url,
        "processed_at": datetime.utcnow(),
        "zoom_level": s117.SATELLITE_ZOOM,
        "image_size": s117.SATELLITE_SIZE,
        "model": s117.GPT_MODEL,
        "source": "inline_resolver",
    }

    # 4) Write back so the next visit doesn't repeat the spend
    if db_subject_coll is not None and subject_doc.get("_id"):
        try:
            db_subject_coll.update_one(
                {"_id": subject_doc["_id"]},
                {"$set": {"satellite_analysis": record}},
            )
        except Exception as e:
            logger.warning(f"  satellite: write-back failed: {e}")

    logger.info(
        f"  satellite analysis generated for {address}: "
        f"{len(record['categories'])} category buckets, "
        f"{len(record['narrative'])} narrative fields, "
        f"image_url={'yes' if image_url else 'no'}"
    )
    return record
