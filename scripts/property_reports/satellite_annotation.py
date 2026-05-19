"""
Bounding-box annotation for the on-demand satellite image.

Mirrors the pattern from
`07_Valuation_Comps/.../floorplan_processing/gpt_bbox_detector.py`
(floor-plan two-level box detector) — same JSON-schema GPT-vision call,
same PIL ImageDraw overlay — but for satellite imagery. Used by
`scripts/property_reports/inline_satellite.py` so the aerial we ship to
the seller's house website carries visible proof of the analysis pass:
bounding boxes around the subject lot, pool, garage, outdoor areas,
nearby parks/waterways, and a Fields-styled drop pin on the subject home.

The annotated PNG is uploaded to blob storage alongside the raw tile.
The resolver writes both URLs to `property.satellite`; the frontend
prefers the annotated one when present.
"""

from __future__ import annotations

import base64
import io
import json
import logging
import math
import os
import re
from dataclasses import dataclass
from typing import Any, Dict, List, Optional, Tuple

import requests
from PIL import Image, ImageDraw, ImageFont

logger = logging.getLogger(__name__)


# Category → outline colour. Tuned for visibility on satellite imagery
# (avoids greens/blues that blend into the background).
_COLOURS = {
    "subject": "#B06B2F",     # Fields copper — the subject lot
    "amenity": "#2563EB",     # Blue — pool, outdoor entertaining
    "detractant": "#E11D48",  # Red — power lines, busy roads
    "context": "#059669",     # Green — parks, schools, surrounding
}

# Pin colour matches the subject-lot copper so it's clearly "ours"
_PIN_COLOUR = "#B06B2F"
_PIN_INNER = "#FFFFFF"


# ---------------------------------------------------------------------- #
# GPT vision — detect labeled bounding boxes
# ---------------------------------------------------------------------- #

SYSTEM_PROMPT = (
    "You are a property analyst annotating a satellite image. "
    "Identify visible features on the image and return tight pixel-coordinate "
    "bounding boxes for each. Return only valid JSON matching the provided schema."
)

USER_PROMPT_TEMPLATE = """\
Analyse this satellite image of a residential property at {address} in {suburb}, Gold Coast, Australia.

The image is {width}x{height} pixels and the subject property is at the centre.

Return up to 6 bounding boxes for features actually visible in this image. Use these categories:

- "subject"   → the subject property's lot/structure (include exactly ONE if identifiable). Tight box around the building/lot, not the whole image.
- "amenity"   → pool, outdoor entertaining area, mature trees, driveway, garage. Each as its own box.
- "detractant"→ busy road, power lines, commercial building, construction
- "context"   → park, reserve, school, waterway, golf course (NAMED features only — do NOT label neighbouring lots or generic surroundings)

Rules:
- One "subject" box maximum.
- Skip "context" boxes that just say "neighbouring lot" — those add no value.
- Boxes MUST be tight. No oversized boxes around the whole image. No subject box bigger than 30% of the image area.
- Skip features that aren't clearly visible. Returning 0 amenities is fine.
- Labels max 3 words, no trailing period.
"""

_SCHEMA = {
    "type": "object",
    "additionalProperties": False,
    "properties": {
        "features": {
            "type": "array",
            "minItems": 0,
            "maxItems": 8,
            "items": {
                "type": "object",
                "additionalProperties": False,
                "properties": {
                    "label": {"type": "string"},
                    "category": {"type": "string", "enum": ["subject", "amenity", "detractant", "context"]},
                    "confidence": {"type": "string", "enum": ["high", "medium", "low"]},
                    "bbox": {
                        "type": "object",
                        "additionalProperties": False,
                        "properties": {
                            "x_min": {"type": "integer"},
                            "y_min": {"type": "integer"},
                            "x_max": {"type": "integer"},
                            "y_max": {"type": "integer"},
                        },
                        "required": ["x_min", "y_min", "x_max", "y_max"],
                    },
                },
                "required": ["label", "category", "bbox", "confidence"],
            },
        }
    },
    "required": ["features"],
}


@dataclass
class Feature:
    label: str
    category: str
    bbox: Tuple[int, int, int, int]  # (x_min, y_min, x_max, y_max)
    confidence: str


def detect_features(
    image_bytes: bytes,
    address: str,
    suburb: str,
    model: str = "gpt-4o",
    timeout_s: int = 60,
) -> List[Feature]:
    """Run GPT vision to identify labeled bounding boxes on a satellite tile."""
    api_key = os.environ.get("OPENAI_API_KEY")
    if not api_key:
        logger.warning("  satellite_annotation: OPENAI_API_KEY missing")
        return []

    try:
        with Image.open(io.BytesIO(image_bytes)) as im:
            width, height = im.size
    except Exception as e:
        logger.warning(f"  satellite_annotation: image decode failed: {e}")
        return []

    b64 = base64.b64encode(image_bytes).decode("utf-8")
    data_url = f"data:image/png;base64,{b64}"

    payload = {
        "model": model,
        "messages": [
            {"role": "system", "content": SYSTEM_PROMPT},
            {
                "role": "user",
                "content": [
                    {
                        "type": "text",
                        "text": USER_PROMPT_TEMPLATE.format(
                            address=address,
                            suburb=(suburb or "").replace("_", " ").title(),
                            width=width,
                            height=height,
                        ),
                    },
                    {"type": "image_url", "image_url": {"url": data_url, "detail": "high"}},
                ],
            },
        ],
        "response_format": {
            "type": "json_schema",
            "json_schema": {"name": "satellite_features", "schema": _SCHEMA, "strict": True},
        },
        "max_completion_tokens": 900,
    }

    try:
        resp = requests.post(
            "https://api.openai.com/v1/chat/completions",
            headers={"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"},
            json=payload,
            timeout=timeout_s,
        )
    except Exception as e:
        logger.warning(f"  satellite_annotation: POST failed: {e}")
        return []

    if resp.status_code != 200:
        logger.warning(f"  satellite_annotation: HTTP {resp.status_code} — {resp.text[:200]}")
        return []

    try:
        body = resp.json()
        content = body["choices"][0]["message"]["content"]
        parsed = json.loads(content)
    except (KeyError, json.JSONDecodeError) as e:
        logger.warning(f"  satellite_annotation: parse failed: {e}")
        return []

    out: List[Feature] = []
    for item in parsed.get("features") or []:
        if not isinstance(item, dict):
            continue
        bb = item.get("bbox") or {}
        try:
            box = (int(bb["x_min"]), int(bb["y_min"]), int(bb["x_max"]), int(bb["y_max"]))
        except (KeyError, TypeError, ValueError):
            continue
        # Sanity-clamp to image bounds
        box = (
            max(0, min(box[0], width - 1)),
            max(0, min(box[1], height - 1)),
            max(0, min(box[2], width - 1)),
            max(0, min(box[3], height - 1)),
        )
        if box[2] <= box[0] or box[3] <= box[1]:
            continue
        out.append(
            Feature(
                label=str(item.get("label") or "").strip()[:40],
                category=str(item.get("category") or "context").lower(),
                bbox=box,
                confidence=str(item.get("confidence") or "medium").lower(),
            )
        )
    return out


# ---------------------------------------------------------------------- #
# PIL drawing — annotate the image with features + Fields drop pin
# ---------------------------------------------------------------------- #

def _try_load_font(size: int) -> Optional[ImageFont.ImageFont]:
    """Best-effort font load. Falls back to PIL default if no system fonts."""
    candidates = [
        "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf",
        "/usr/share/fonts/truetype/liberation/LiberationSans-Bold.ttf",
        "/usr/share/fonts/truetype/freefont/FreeSansBold.ttf",
    ]
    for path in candidates:
        if os.path.exists(path):
            try:
                return ImageFont.truetype(path, size)
            except Exception:
                continue
    try:
        return ImageFont.load_default()
    except Exception:
        return None


def _draw_pin(draw: ImageDraw.ImageDraw, cx: int, cy: int, radius: int = 22) -> None:
    """Draw a Fields-styled drop pin at (cx, cy). Pin tip points to the
    coordinate; the head sits above. Filled copper circle + white inner dot
    + thin black outline for contrast against any background."""
    head_r = radius
    # Pin body (teardrop): a circle + a triangular tail pointing down to (cx, cy)
    head_y = cy - int(radius * 1.4)
    # Outline (black for contrast)
    draw.ellipse(
        (cx - head_r - 2, head_y - head_r - 2, cx + head_r + 2, head_y + head_r + 2),
        outline="#111111", fill=None, width=3,
    )
    draw.polygon(
        [(cx - head_r * 0.55, head_y + head_r * 0.6), (cx + head_r * 0.55, head_y + head_r * 0.6), (cx, cy)],
        fill=_PIN_COLOUR, outline="#111111",
    )
    # Filled copper head
    draw.ellipse(
        (cx - head_r, head_y - head_r, cx + head_r, head_y + head_r),
        fill=_PIN_COLOUR, outline="#111111", width=2,
    )
    # White inner dot
    inner_r = max(4, head_r // 3)
    draw.ellipse(
        (cx - inner_r, head_y - inner_r, cx + inner_r, head_y + inner_r),
        fill=_PIN_INNER,
    )


def _draw_numbered_badge(
    draw: ImageDraw.ImageDraw,
    number: int,
    box: Tuple[int, int, int, int],
    colour: str,
    font: Optional[ImageFont.ImageFont],
    image_size: Tuple[int, int],
    radius: int = 16,
) -> None:
    """Draw a small numbered circle badge at the top-left of the bounding box.
    Keeps the image visually clean — labels live in the frontend legend,
    not on top of clustered boxes."""
    img_w, img_h = image_size
    x_min, y_min, _, _ = box
    # Sit the badge half-inside / half-outside the box at the top-left corner.
    cx = max(radius + 1, x_min)
    cy = max(radius + 1, y_min)
    # Filled circle with thin outline + bold white number
    draw.ellipse(
        (cx - radius, cy - radius, cx + radius, cy + radius),
        fill=colour, outline="#111111", width=2,
    )
    text = str(number)
    if font is not None:
        l, t, r, b = draw.textbbox((0, 0), text, font=font)
        tw, th = (r - l, b - t)
    else:
        tw, th = (len(text) * 8, 14)
    draw.text((cx - tw // 2 - l if font else cx - tw // 2,
               cy - th // 2 - t if font else cy - th // 2),
              text, fill="#FFFFFF", font=font)


def draw_annotations(
    image_bytes: bytes,
    features: List[Feature],
    pin_pixel: Optional[Tuple[int, int]] = None,
    stroke_px: int = 4,
) -> Tuple[bytes, List[Feature]]:
    """Render a copy of the image with each feature's bounding box outlined
    + a label, and a Fields-styled drop pin at `pin_pixel` (defaults to the
    image centre, where the Google Maps Static tile's centred subject sits)."""
    with Image.open(io.BytesIO(image_bytes)) as im:
        if im.mode not in ("RGB", "RGBA"):
            im = im.convert("RGB")
        out = im.copy()

    draw = ImageDraw.Draw(out)
    width, height = out.size
    font = _try_load_font(size=max(14, height // 50))

    # Boxes first — subject last so its colour sits on top of any overlap.
    # Numbered badges keep the image clean; labels are rendered by the
    # frontend as a legend beside/below the image, using the `features` list.
    sorted_features = sorted(features, key=lambda f: 1 if f.category == "subject" else 0)
    badge_font = _try_load_font(size=max(15, height // 45))
    for idx, feat in enumerate(sorted_features, start=1):
        colour = _COLOURS.get(feat.category, "#444444")
        x_min, y_min, x_max, y_max = feat.bbox
        # Stroke-px-thick outline by drawing concentric rects
        for i in range(stroke_px):
            draw.rectangle(
                (x_min - i, y_min - i, x_max + i, y_max + i),
                outline=colour,
            )
        _draw_numbered_badge(
            draw, idx, feat.bbox, colour, badge_font, (width, height),
            radius=max(14, height // 50),
        )

    # Drop pin (default: image centre, where the Google tile is geocoded)
    if pin_pixel is None:
        pin_pixel = (width // 2, height // 2)
    _draw_pin(draw, pin_pixel[0], pin_pixel[1], radius=max(18, height // 36))

    # Encode back to PNG bytes
    buf = io.BytesIO()
    out.save(buf, format="PNG", optimize=True)
    # Return the features in the SAME display order as the badge numbering so
    # the frontend legend stays aligned with the on-image numbers.
    return buf.getvalue(), sorted_features


# ---------------------------------------------------------------------- #
# Public entrypoint
# ---------------------------------------------------------------------- #

def annotate(
    image_bytes: bytes,
    address: str,
    suburb: str,
    pin_pixel: Optional[Tuple[int, int]] = None,
) -> Optional[Dict[str, Any]]:
    """Detect features and render an annotated PNG. Returns:
        {
          "annotated_image_bytes": bytes,
          "features": [{label, category, confidence, bbox}, ...]
        }
    or None on failure.
    """
    features = detect_features(image_bytes, address, suburb)
    if not features:
        # Still annotate with just the drop pin — gives the marketing benefit
        # of "our tech is looking" even when no features were detected.
        logger.info("  satellite_annotation: 0 features detected — drawing pin only")

    annotated_bytes, display_features = draw_annotations(image_bytes, features, pin_pixel=pin_pixel)
    return {
        "annotated_image_bytes": annotated_bytes,
        "features": [
            {
                "number": idx,
                "label": f.label,
                "category": f.category,
                "confidence": f.confidence,
                "bbox": list(f.bbox),
            }
            for idx, f in enumerate(display_features, start=1)
        ],
    }
