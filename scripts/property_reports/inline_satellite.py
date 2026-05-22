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
    doc. Quick check: must have an image_url + at least one category bucket.
    URLs pointing at the disabled legacy Azure blob host don't count — those
    images return 403, so we treat the analysis as needing a full re-run."""
    sa = doc.get("satellite_analysis") or {}
    url = sa.get("satellite_image_url") or ""
    if not url:
        return False
    if "blob.core.windows.net" in url:
        # Dead Azure host — the categories may still be valid but we can't
        # serve the image. Re-fetch fresh.
        return False
    cats = sa.get("categories") or {}
    return bool(cats) and any(cats.values())


def _has_annotated_image(doc: Dict[str, Any]) -> bool:
    """An annotation counts as current only if it also carries the cadastral
    `boundary_polygon`. Annotations generated before the 2026-05-20 boundary
    code shipped lack that field — when we detect the gap, we re-run so the
    yellow lot polygon + point-in-polygon filter both apply."""
    sa = doc.get("satellite_analysis") or {}
    if not sa.get("annotated_image_url"):
        return False
    # Older annotations (pre-boundary) don't carry boundary_polygon — treat as
    # stale so the upgrade pass refreshes them.
    return bool(sa.get("boundary_polygon"))


def _fetch_image_bytes_from_url(url: str) -> Optional[bytes]:
    """Download image bytes from a URL — used when we need to re-annotate
    an existing satellite tile but only have its URL."""
    import requests
    try:
        r = requests.get(url, timeout=20)
        if r.status_code == 200 and r.headers.get("content-type", "").startswith("image/"):
            return r.content
    except Exception as e:
        logger.warning(f"  satellite: fetch existing image failed: {e}")
    return None


def _annotate_and_upload(
    image_bytes: bytes,
    address: str,
    suburb_key: str,
    property_id: str,
    db_label: str,
    center_lat: Optional[float] = None,
    center_lng: Optional[float] = None,
) -> Optional[Dict[str, Any]]:
    """Run the bbox-detection pass, draw annotations + Fields drop pin,
    upload the annotated PNG. Returns {'url', 'features'} or None on failure.

    Passing center_lat/center_lng enables cadastral boundary fetch + crop:
    the lot boundary is drawn as a yellow polygon, the image is cropped to
    the lot + context margin, and GPT is instructed to only annotate features
    inside the boundary.
    """
    s117 = _get_step117()
    if not s117:
        return None
    try:
        from scripts.property_reports import satellite_annotation as sa_anno
    except Exception as e:
        logger.warning(f"  satellite_annotation import failed: {e}")
        return None

    result = sa_anno.annotate(
        image_bytes,
        address=address,
        suburb=suburb_key,
        center_lat=center_lat,
        center_lng=center_lng,
        zoom=s117.SATELLITE_ZOOM,
        tile_scale=s117.SATELLITE_SCALE,
    )
    if not result:
        return None

    annotated_bytes = result["annotated_image_bytes"]
    blob_name_path = f"{db_label}/{suburb_key or 'unknown'}/{property_id or 'unknown'}/satellite/aerial_z{s117.SATELLITE_ZOOM}_annotated.png"
    annotated_url = None
    try:
        from shared import blob_storage  # type: ignore
        annotated_url = blob_storage.upload(
            s117.BLOB_CONTAINER, blob_name_path, annotated_bytes,
            content_type="image/png",
            cache_control="public, max-age=31536000",
        )
    except Exception as e:
        logger.warning(f"  satellite_annotation: upload failed: {e}")

    return {
        "annotated_image_url": annotated_url,
        "features": result.get("features") or [],
        "boundary_polygon": result.get("boundary_polygon"),
    }


def _sync_property_reports(property_id: str, satellite_record: Dict[str, Any]) -> None:
    """Mirror updated satellite data into system_monitor.property_reports.

    property_reports caches a snapshot of the source doc. When satellite
    analysis is regenerated inline, that cache goes stale unless we sync it
    here. Matches on property_id (the source doc _id as a string).
    """
    try:
        from shared.db import get_client
        client = get_client()
        sm_coll = client["system_monitor"]["property_reports"]
        fields = {
            "satellite.satellite_image_url":  satellite_record.get("satellite_image_url"),
            "satellite.annotated_image_url":  satellite_record.get("annotated_image_url"),
            "satellite.features":             satellite_record.get("features") or [],
            "satellite.categories":           satellite_record.get("categories") or {},
            "satellite.narrative":            satellite_record.get("narrative") or {},
            "satellite.processed_at":         satellite_record.get("processed_at"),
            "property.satellite.satellite_image_url": satellite_record.get("satellite_image_url"),
            "property.satellite.annotated_image_url": satellite_record.get("annotated_image_url"),
            "property.satellite.features":    satellite_record.get("features") or [],
            "property.satellite.categories":  satellite_record.get("categories") or {},
            "property.satellite.narrative":   satellite_record.get("narrative") or {},
        }
        # Drop None values to avoid overwriting good data with nulls
        fields = {k: v for k, v in fields.items() if v is not None}
        result = sm_coll.update_many(
            {"property_id": property_id},
            {"$set": fields},
        )
        if result.modified_count:
            logger.info(
                "  satellite: synced to property_reports (%d doc%s)",
                result.modified_count,
                "s" if result.modified_count != 1 else "",
            )
    except Exception as exc:
        logger.warning("  satellite: property_reports sync failed: %s", exc)


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
    s117 = _get_step117()
    if not s117:
        return None
    if not s117.GOOGLE_MAPS_API_KEY:
        logger.info("  satellite: GOOGLE_MAPS_STATIC_API_KEY not set — skipping")
        return None

    address = subject_doc.get("address") or ""
    property_id = str(subject_doc.get("_id") or "")

    # ── Path A: doc already has analysis ──────────────────────────────
    # If annotation is also already cached, return as-is at $0 cost.
    # Otherwise, re-annotate the existing image without re-running the
    # structured analysis (cheap upgrade for legacy docs).
    if _has_existing_analysis(subject_doc):
        sa = subject_doc.get("satellite_analysis") or {}
        if _has_annotated_image(subject_doc):
            logger.info("  satellite: existing analysis + annotation on doc — reusing")
            return sa

        logger.info("  satellite: existing analysis without annotation — upgrading")
        existing_bytes = _fetch_image_bytes_from_url(sa.get("satellite_image_url") or "")
        if existing_bytes:
            # Pull db_label from the existing satellite_image_url path so the
            # annotated tile lands under the same path prefix (sold/.. vs
            # for_sale/..) — keeps blob layout consistent per property.
            existing_url = sa.get("satellite_image_url") or ""
            existing_label = db_label
            for candidate in ("sold", "for_sale", "active"):
                if f"/{candidate}/" in existing_url:
                    existing_label = candidate
                    break
            latlng_existing = _subject_latlng(subject_doc)
            anno = _annotate_and_upload(
                existing_bytes, address=address,
                suburb_key=suburb_key, property_id=property_id, db_label=existing_label,
                center_lat=latlng_existing[0] if latlng_existing else None,
                center_lng=latlng_existing[1] if latlng_existing else None,
            )
            if anno:
                sa["annotated_image_url"] = anno["annotated_image_url"]
                sa["features"] = anno["features"]
                sa["boundary_polygon"] = anno.get("boundary_polygon")
                if db_subject_coll is not None and subject_doc.get("_id"):
                    try:
                        db_subject_coll.update_one(
                            {"_id": subject_doc["_id"]},
                            {"$set": {
                                "satellite_analysis.annotated_image_url": anno["annotated_image_url"],
                                "satellite_analysis.features": anno["features"],
                                "satellite_analysis.boundary_polygon": anno.get("boundary_polygon"),
                            }},
                        )
                    except Exception as e:
                        logger.warning(f"  satellite: write-back of annotation failed: {e}")
                _sync_property_reports(property_id, sa)
        return sa

    # ── Path B: no analysis yet — full fresh pass ─────────────────────
    latlng = _subject_latlng(subject_doc)

    image_bytes = s117.fetch_satellite_image(
        lat=latlng[0] if latlng else None,
        lng=latlng[1] if latlng else None,
        address=address or None,
    )
    if not image_bytes:
        logger.warning(f"  satellite: image fetch failed for {address}")
        return None

    image_url = None
    try:
        image_url = s117.upload_satellite_to_blob(
            None, image_bytes, suburb_key or "unknown",
            property_id or "unknown", db_label=db_label,
        )
    except Exception as e:
        logger.warning(f"  satellite: blob upload failed (continuing without URL): {e}")

    analysis = s117.analyse_satellite_image(image_bytes, address, suburb_key or "")
    if not analysis:
        logger.warning(f"  satellite: GPT analysis returned nothing for {address}")
        return None

    # Annotation pass — bounding boxes + Fields drop pin on the same image.
    # Pass lat/lng so the cadastral boundary can be fetched and drawn.
    anno = _annotate_and_upload(
        image_bytes, address=address,
        suburb_key=suburb_key, property_id=property_id, db_label=db_label,
        center_lat=latlng[0] if latlng else None,
        center_lng=latlng[1] if latlng else None,
    )

    record = {
        "categories": analysis.get("categories") or {},
        "narrative": analysis.get("narrative") or {},
        "satellite_image_url": image_url,
        "annotated_image_url": (anno or {}).get("annotated_image_url"),
        "features": (anno or {}).get("features") or [],
        "boundary_polygon": (anno or {}).get("boundary_polygon"),
        "processed_at": datetime.utcnow(),
        "zoom_level": s117.SATELLITE_ZOOM,
        "image_size": s117.SATELLITE_SIZE,
        "model": s117.GPT_MODEL,
        "source": "inline_resolver",
    }

    if db_subject_coll is not None and subject_doc.get("_id"):
        try:
            db_subject_coll.update_one(
                {"_id": subject_doc["_id"]},
                {"$set": {"satellite_analysis": record}},
            )
        except Exception as e:
            logger.warning(f"  satellite: write-back failed: {e}")

    _sync_property_reports(property_id, record)

    logger.info(
        f"  satellite analysis generated for {address}: "
        f"{len(record['categories'])} category buckets, "
        f"{len(record['narrative'])} narrative fields, "
        f"{len(record['features'])} features bounded, "
        f"annotated_url={'yes' if record.get('annotated_image_url') else 'no'}"
    )
    return record
