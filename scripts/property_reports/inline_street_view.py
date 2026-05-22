"""
On-demand Google Street View capture + GPT-4o vision analysis.

For any address with lat/lng (which is every cadastral hit), Google Static
Street View gives us a ground-level view of the front of the home. We
fetch it, upload to blob, run a structured GPT-4o vision pass for the
buyer-relevant signals visible from the kerb, persist the result.

This is a universal baseline asset, not Tier-3-only:
  - Tier 1 / 2 (currently or previously listed): used as a hero-photo
    fallback when Domain photos are thin, and corroborates / fills gaps
    in `property_valuation_data` (storeys, condition, garage).
  - Tier 3 (cadastral-only): the primary visual evidence alongside the
    satellite — feeds `derive_features_basic` so the scarcity / positioning /
    personas / buyers chain still has something to work with.

Cost when triggered: ~$0.05 in GPT vision + 1 Street View Static API call
(free under 100k/day). Cached on the doc — subsequent visits free.
"""

from __future__ import annotations

import base64
import json
import logging
import os
from datetime import datetime
from typing import Any, Dict, Optional, Tuple

import requests

logger = logging.getLogger(__name__)

_TIMEOUT = 15
_IMAGE_SIZE = "640x640"  # max for free tier
_FOV = 80                # field of view (degrees) — wide enough to show whole house
_PITCH = 0               # slight downward tilt → -5 to -10 for tighter framing
_HEADING = None          # let Google pick (auto-aimed at the address)
_GPT_MODEL = "gpt-4o"
_BLOB_CONTAINER = "property-images"


SYSTEM_PROMPT = """You are a property analyst reviewing a Google Street View image of a residential property on the Gold Coast, Queensland, Australia.

Analyse the image from the perspective of a potential buyer viewing the home from the kerb. Be specific and factual — describe what you can actually see, not what you assume.

Return your analysis as a JSON object with TWO sections:

1. **"categories"** — structured categorical data used as inputs for valuation models and downstream resolvers. Every field MUST use ONLY the allowed values listed.
2. **"narrative"** — short free-form descriptions.

```json
{
  "categories": {
    "dwelling": {
      "storeys": 1,
      "estimated_bedrooms": "3-bed | 4-bed | 5+ bed | unknown",
      "style": "queenslander | hamptons | modern | contemporary | federation | mid_century | brick_veneer | rendered | mediterranean | duplex | townhouse | other | unknown",
      "approximate_build_era": "pre_1960 | 1960s_1980s | 1990s_2000s | 2010s | new_build | unknown",
      "condition_impression": "well_maintained | dated_but_sound | needs_cosmetic_work | needs_major_work | recently_renovated | unknown"
    },
    "frontage": {
      "fencing": "open | low_fence | tall_fence_or_wall | hedge | gated | mixed",
      "front_yard": "open_lawn | landscaped | concreted | gravelled | sparse | unknown",
      "entry": "ground_level | elevated_steps | gated_pathway | unknown",
      "porch_or_verandah": "covered_porch | covered_verandah | covered_balcony | none | unknown"
    },
    "exterior": {
      "primary_cladding": "brick | rendered | weatherboard | hardiplank_fibro | stone | mixed | unknown",
      "roof_type": "tile_pitched | colorbond_pitched | flat | mixed | unknown",
      "roof_condition": "good | fair | poor | unknown"
    },
    "parking": {
      "garage": "double_attached | single_attached | triple_attached | carport | none_visible | unknown",
      "driveway": "concrete | pavers | gravel | asphalt | none_visible | unknown"
    },
    "street_context": {
      "street_type": "quiet_residential | busy_arterial | cul_de_sac_or_court | corner_lot | acreage_lane | unknown",
      "street_appeal": "premium | good | average | below_average",
      "kerb_appeal_relative_to_street": "above_average | average | below_average"
    }
  },
  "narrative": {
    "frontage_description": "1-2 sentences describing what a buyer sees driving past — the dwelling, the front yard, the entry. Plain language.",
    "street_setting": "1-2 sentences about the street the property sits on — character, density, tree canopy.",
    "buyer_appeal": ["3-5 short bullets of what's visually appealing to a buyer"],
    "visible_trade_offs": ["1-3 short bullets of any visible drawbacks — proximity to street, dated façade, missing garage, etc. Empty array if nothing notable."],
    "kerb_summary": "One-sentence kerb impression for the seller."
  }
}
```

RULES:
- Use ONLY the allowed values from the category lists above. If you cannot determine a value, use "unknown".
- Storeys is a literal integer (1, 2, or 3). Don't guess if part of the home is obscured.
- estimated_bedrooms is a rough visual inference — frontage scale + visible windows. Use "unknown" if you can't make a defensible estimate.
- Describe ONLY what's visible. Do not infer pool / outdoor entertaining / yard size from a kerb-only view.
- Output VALID JSON. No prose around it, no markdown fences."""


USER_PROMPT_TEMPLATE = """Analyse this Google Street View image of a property at: {address}

The property is in the suburb of {suburb}, Gold Coast, Queensland, Australia.

The image is a kerb-level view of the front of the home. Focus your analysis on what a buyer would see standing on the street."""


# ---------------------------------------------------------------------- #
# Fetch + upload
# ---------------------------------------------------------------------- #

def _api_key() -> Optional[str]:
    """Street View Static needs its own enabled-and-restricted key. Falls
    back to the shared Maps Static key if the dedicated var isn't set
    (rarely useful in practice — that key is usually restricted to other
    APIs)."""
    return (
        os.environ.get("GOOGLE_STREETVIEW_API_KEY")
        or os.environ.get("GOOGLE_MAPS_STATIC_API_KEY")
    )


def fetch_street_view_image(lat: float, lng: float) -> Optional[bytes]:
    """Pull a Google Static Street View image at the given coordinates.
    Returns the raw JPEG bytes, or None when no imagery is available at
    that location (Google returns a 'no imagery' placeholder we filter out
    via the metadata endpoint first)."""
    api_key = _api_key()
    if not api_key:
        logger.warning("  street_view: GOOGLE_STREETVIEW_API_KEY not set")
        return None

    # Hit the metadata endpoint first — confirms imagery exists at this
    # location. Free, returns 'ZERO_RESULTS' for addresses Google has no
    # Street View coverage for. Saves a wasted image fetch.
    try:
        meta_url = "https://maps.googleapis.com/maps/api/streetview/metadata"
        meta_resp = requests.get(meta_url, params={
            "location": f"{lat},{lng}",
            "key": api_key,
        }, timeout=_TIMEOUT)
        meta = meta_resp.json() if meta_resp.status_code == 200 else {}
        if meta.get("status") != "OK":
            logger.info(f"  street_view: no imagery at {lat},{lng} (status={meta.get('status')})")
            return None
    except Exception as e:
        logger.warning(f"  street_view: metadata check failed: {e}")
        # Continue to image fetch — metadata is advisory.

    # Fetch the actual image
    params = {
        "location": f"{lat},{lng}",
        "size": _IMAGE_SIZE,
        "fov": _FOV,
        "pitch": _PITCH,
        "key": api_key,
        "return_error_code": "true",  # explicit 404 if no imagery
    }
    if _HEADING is not None:
        params["heading"] = _HEADING

    try:
        resp = requests.get(
            "https://maps.googleapis.com/maps/api/streetview",
            params=params, timeout=_TIMEOUT,
        )
        if resp.status_code == 200 and resp.headers.get("content-type", "").startswith("image/"):
            return resp.content
        logger.info(f"  street_view: fetch returned {resp.status_code}: {resp.text[:120]}")
        return None
    except Exception as e:
        logger.warning(f"  street_view: fetch failed: {e}")
        return None


def upload_street_view_to_blob(
    image_bytes: bytes,
    suburb_key: str,
    property_id: str,
    db_label: str = "for_sale",
) -> Optional[str]:
    """Upload the Street View JPEG to blob storage and return the public URL."""
    try:
        from shared import blob_storage  # type: ignore
    except ImportError as e:
        logger.warning(f"  street_view: blob_storage import failed: {e}")
        return None
    blob_name = f"{db_label}/{suburb_key or 'unknown'}/{property_id or 'unknown'}/street_view/front.jpg"
    try:
        return blob_storage.upload(
            _BLOB_CONTAINER, blob_name, image_bytes,
            content_type="image/jpeg",
            cache_control="public, max-age=31536000",
        )
    except Exception as e:
        logger.warning(f"  street_view: blob upload failed: {e}")
        return None


# ---------------------------------------------------------------------- #
# GPT-4o vision analysis
# ---------------------------------------------------------------------- #

def analyse_street_view(
    image_bytes: bytes,
    address: str,
    suburb: str,
    model: str = _GPT_MODEL,
    timeout_s: int = 60,
) -> Optional[Dict[str, Any]]:
    """Send the Street View image to GPT-4o for buyer-perspective analysis."""
    api_key = os.environ.get("OPENAI_API_KEY")
    if not api_key:
        logger.warning("  street_view: OPENAI_API_KEY missing")
        return None

    b64 = base64.b64encode(image_bytes).decode("utf-8")
    user_text = USER_PROMPT_TEMPLATE.format(
        address=address,
        suburb=(suburb or "").replace("_", " ").title(),
    )

    payload = {
        "model": model,
        "messages": [
            {"role": "system", "content": SYSTEM_PROMPT},
            {
                "role": "user",
                "content": [
                    {"type": "text", "text": user_text},
                    {
                        "type": "image_url",
                        "image_url": {"url": f"data:image/jpeg;base64,{b64}", "detail": "high"},
                    },
                ],
            },
        ],
        "max_completion_tokens": 1500,
        "temperature": 0.2,
        "response_format": {"type": "json_object"},
    }

    try:
        resp = requests.post(
            "https://api.openai.com/v1/chat/completions",
            headers={"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"},
            json=payload, timeout=timeout_s,
        )
    except Exception as e:
        logger.warning(f"  street_view: POST failed: {e}")
        return None
    if resp.status_code != 200:
        logger.warning(f"  street_view: HTTP {resp.status_code} — {resp.text[:200]}")
        return None
    try:
        body = resp.json()
        content = body["choices"][0]["message"]["content"]
        parsed = json.loads(content)
    except (KeyError, json.JSONDecodeError) as e:
        logger.warning(f"  street_view: parse failed: {e}")
        return None

    if not isinstance(parsed, dict):
        return None
    return parsed


# ---------------------------------------------------------------------- #
# Public entrypoint — used by slot_resolver
# ---------------------------------------------------------------------- #

def _has_existing_streetview(doc: Dict[str, Any]) -> bool:
    """True if the cached street_view_analysis is present + usable.
    Dead Azure blob URLs are treated as no-cache so we re-fetch."""
    sv = doc.get("street_view_analysis") or {}
    url = sv.get("street_view_image_url") or ""
    if not url:
        return False
    if "blob.core.windows.net" in url:
        return False
    cats = sv.get("categories") or {}
    return bool(cats) and any(cats.values())


def _subject_latlng(doc: Dict[str, Any]) -> Optional[Tuple[float, float]]:
    lat = doc.get("LATITUDE") or doc.get("latitude") or doc.get("lat")
    lng = doc.get("LONGITUDE") or doc.get("longitude") or doc.get("lng")
    if lat is None or lng is None:
        return None
    try:
        return (float(lat), float(lng))
    except (TypeError, ValueError):
        return None


def resolve_street_view(
    subject_doc: Dict[str, Any],
    suburb_key: str,
    db_subject_coll=None,
    db_label: str = "for_sale",
) -> Optional[Dict[str, Any]]:
    """End-to-end Street View resolver.

    Returns the cached `street_view_analysis` when one is on the doc.
    Otherwise: fetch the Street View image → upload to blob → GPT vision
    analysis → write back to the subject doc → return the dict.

    Returns None when:
      - no lat/lng available
      - Google has no Street View imagery at the location
      - API key missing
      - GPT analysis fails
    """
    if _has_existing_streetview(subject_doc):
        logger.info("  street_view: existing analysis on doc — reusing")
        return subject_doc.get("street_view_analysis")

    latlng = _subject_latlng(subject_doc)
    if not latlng:
        logger.info("  street_view: no lat/lng on doc — skipping")
        return None

    image_bytes = fetch_street_view_image(latlng[0], latlng[1])
    if not image_bytes:
        # No imagery available — common for private roads, new estates,
        # heavily hedged frontages. Mark this on the doc so we don't retry
        # every visit.
        if db_subject_coll is not None and subject_doc.get("_id"):
            try:
                db_subject_coll.update_one(
                    {"_id": subject_doc["_id"]},
                    {"$set": {"street_view_analysis": {
                        "status": "no_imagery_available",
                        "checked_at": datetime.utcnow(),
                    }}},
                )
            except Exception:
                pass
        return None

    property_id = str(subject_doc.get("_id") or "")
    image_url = upload_street_view_to_blob(
        image_bytes, suburb_key or "unknown", property_id, db_label=db_label,
    )

    address = subject_doc.get("address") or ""
    analysis = analyse_street_view(image_bytes, address, suburb_key or "")
    if not analysis:
        logger.warning(f"  street_view: GPT analysis returned nothing for {address}")
        return None

    record = {
        "categories": analysis.get("categories") or {},
        "narrative": analysis.get("narrative") or {},
        "street_view_image_url": image_url,
        "processed_at": datetime.utcnow(),
        "model": _GPT_MODEL,
        "source": "inline_resolver",
        "fov": _FOV,
        "pitch": _PITCH,
    }

    if db_subject_coll is not None and subject_doc.get("_id"):
        try:
            db_subject_coll.update_one(
                {"_id": subject_doc["_id"]},
                {"$set": {"street_view_analysis": record}},
            )
        except Exception as e:
            logger.warning(f"  street_view: write-back failed: {e}")

    cats = record["categories"]
    logger.info(
        f"  street_view analysis generated for {address}: "
        f"{len(cats)} category buckets · "
        f"storeys={(cats.get('dwelling') or {}).get('storeys')} · "
        f"est_beds={(cats.get('dwelling') or {}).get('estimated_bedrooms')} · "
        f"style={(cats.get('dwelling') or {}).get('style')} · "
        f"image_url={'yes' if image_url else 'no'}"
    )
    return record
