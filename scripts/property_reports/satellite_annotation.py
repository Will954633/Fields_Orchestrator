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

# Used when we have a boundary polygon drawn on the image
USER_PROMPT_TEMPLATE = """\
Analyse this satellite image of a residential property at {address} in {suburb}, Gold Coast, Australia.

The image is {width}x{height} pixels. The subject property boundary is drawn as a YELLOW polygon outline on the image.

Return up to 6 bounding boxes for features actually visible in this image. Use these categories:

- "subject"   → the subject property's lot/structure (exactly ONE — tight box around the building/structure inside the yellow boundary).
- "amenity"   → pool, outdoor entertaining area, driveway, garage — ONLY if the feature is INSIDE the yellow boundary polygon. Do NOT annotate any feature outside the boundary, even if clearly visible.
- "detractant"→ busy road, power lines, commercial building, construction (these may be outside the boundary — they affect the property from beyond its edges)
- "context"   → park, reserve, school, waterway, golf course (NAMED features only)

Rules:
- CRITICAL: "amenity" boxes must fall INSIDE the yellow boundary polygon. If a pool or any other amenity is on a neighbouring lot (outside the boundary), do NOT include it.
- One "subject" box maximum. Keep it tight to the building footprint inside the boundary.
- Skip "context" boxes for generic neighbouring lots — only named destinations.
- Boxes MUST be tight. Returning 0 amenities is correct if none exist inside the boundary.
- Labels max 3 words, no trailing period.
"""

# Fallback prompt when no boundary polygon is available
USER_PROMPT_TEMPLATE_NO_BOUNDARY = """\
Analyse this satellite image of a residential property at {address} in {suburb}, Gold Coast, Australia.

The image is {width}x{height} pixels and the subject property is near the centre.

Return up to 6 bounding boxes for features actually visible in this image. Use these categories:

- "subject"   → the subject property's lot/structure (include exactly ONE if identifiable). Tight box around the building/lot, not the whole image.
- "amenity"   → pool, outdoor entertaining area, mature trees, driveway, garage — ONLY if located on the subject property's lot. Do NOT annotate pools, garages, or other amenities on neighbouring lots.
- "detractant"→ busy road, power lines, commercial building, construction
- "context"   → park, reserve, school, waterway, golf course (NAMED features only — do NOT label neighbouring lots or generic surroundings)

Rules:
- One "subject" box maximum.
- CRITICAL: "amenity" features must be on the subject property, not a neighbour's lot. If a pool or outdoor area is on a neighbouring property, do NOT create an amenity box for it.
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


# ---------------------------------------------------------------------- #
# Lot boundary: Mercator projection + drawing
# ---------------------------------------------------------------------- #

# Google Maps Static API tile at zoom z with scale s:
#   image size = size_px * s  (e.g. 640*2 = 1280)
#   world size at zoom z = 256 * 2^z  (logical pixels, scale=1)
#   tile covers the same geographic area regardless of scale — scale just 2×s pixel density

def _mercator_y(lat_deg: float, world_size: float) -> float:
    lat_rad = math.radians(lat_deg)
    return (math.pi - math.log(math.tan(math.pi / 4 + lat_rad / 2))) * world_size / (2 * math.pi)


def latlng_to_pixel(
    lat: float,
    lng: float,
    center_lat: float,
    center_lng: float,
    zoom: int,
    img_width: int,
    img_height: int,
    tile_scale: int = 2,
) -> Tuple[int, int]:
    """Project a lat/lng to pixel coordinates on a Google Maps Static satellite tile.

    tile_scale=2 means the image is twice the logical pixel density (retina).
    The tile covers the same area as a scale=1 tile; each logical pixel = tile_scale physical pixels.
    """
    world_size = 256 * (2 ** zoom)  # logical pixels at this zoom
    # Logical-pixel world coordinates
    cx = (center_lng + 180) / 360 * world_size
    cy = _mercator_y(center_lat, world_size)
    px = (lng + 180) / 360 * world_size
    py = _mercator_y(lat, world_size)
    # Physical pixel offset from image centre
    x = (px - cx) * tile_scale + img_width / 2
    y = (py - cy) * tile_scale + img_height / 2
    return (int(round(x)), int(round(y)))


def draw_lot_boundary(
    image_bytes: bytes,
    ring: List[Tuple[float, float]],  # (lng, lat) pairs
    center_lat: float,
    center_lng: float,
    zoom: int,
    tile_scale: int = 2,
    colour: str = "#FFE000",  # bright yellow — visible on satellite imagery
    stroke_px: int = 4,
) -> Tuple[bytes, List[Tuple[int, int]]]:
    """Draw the lot boundary polygon on the image.

    Returns (annotated_image_bytes, ring_pixels) where ring_pixels is the
    projected polygon in image-pixel coordinates — used for cropping.
    """
    with Image.open(io.BytesIO(image_bytes)) as im:
        if im.mode not in ("RGB", "RGBA"):
            im = im.convert("RGB")
        out = im.copy()

    w, h = out.size
    ring_pixels = [
        latlng_to_pixel(lat, lng, center_lat, center_lng, zoom, w, h, tile_scale)
        for lng, lat in ring
    ]

    draw = ImageDraw.Draw(out)
    for i in range(stroke_px):
        offset_ring = [(x - i, y - i) for x, y in ring_pixels]
        draw.polygon(offset_ring, outline=colour)
        offset_ring = [(x + i, y + i) for x, y in ring_pixels]
        draw.polygon(offset_ring, outline=colour)
    draw.polygon(ring_pixels, outline=colour)

    buf = io.BytesIO()
    out.save(buf, format="PNG", optimize=True)
    return buf.getvalue(), ring_pixels


def crop_to_boundary(
    image_bytes: bytes,
    ring_pixels: List[Tuple[int, int]],
    margin_factor: float = 1.5,
) -> Tuple[bytes, Tuple[int, int, int, int]]:
    """Crop the image to the polygon bounding box + a margin.

    margin_factor=1.5 adds a margin equal to 150% of the lot's own
    width/height on each side, keeping enough context for GPT to understand
    the neighbourhood but filling the frame more with the subject lot.

    Returns (cropped_bytes, crop_box) where crop_box = (x_min, y_min, x_max, y_max)
    in original image coordinates. The caller uses crop_box to translate
    GPT bbox coordinates back to the full image space if needed.
    """
    with Image.open(io.BytesIO(image_bytes)) as im:
        img_w, img_h = im.size

    xs = [p[0] for p in ring_pixels]
    ys = [p[1] for p in ring_pixels]
    lot_x_min, lot_x_max = min(xs), max(xs)
    lot_y_min, lot_y_max = min(ys), max(ys)
    lot_w = lot_x_max - lot_x_min
    lot_h = lot_y_max - lot_y_min

    margin_x = int(lot_w * margin_factor)
    margin_y = int(lot_h * margin_factor)

    crop_x_min = max(0, lot_x_min - margin_x)
    crop_y_min = max(0, lot_y_min - margin_y)
    crop_x_max = min(img_w, lot_x_max + margin_x)
    crop_y_max = min(img_h, lot_y_max + margin_y)

    crop_box = (crop_x_min, crop_y_min, crop_x_max, crop_y_max)

    with Image.open(io.BytesIO(image_bytes)) as im:
        if im.mode not in ("RGB", "RGBA"):
            im = im.convert("RGB")
        cropped = im.crop(crop_box)

    buf = io.BytesIO()
    cropped.save(buf, format="PNG", optimize=True)
    return buf.getvalue(), crop_box


# ---------------------------------------------------------------------- #
# Point-in-polygon filter — drop features whose bbox falls outside the lot
# ---------------------------------------------------------------------- #

def _point_in_polygon(x: float, y: float, polygon: List[Tuple[int, int]]) -> bool:
    """Ray-casting point-in-polygon test. Returns True if (x, y) is inside the
    closed polygon. Edge cases (point exactly on boundary) → treat as inside."""
    if not polygon or len(polygon) < 3:
        return True  # No polygon to filter against — let everything through.
    inside = False
    n = len(polygon)
    j = n - 1
    for i in range(n):
        xi, yi = polygon[i]
        xj, yj = polygon[j]
        if ((yi > y) != (yj > y)) and (x < (xj - xi) * (y - yi) / ((yj - yi) or 1e-9) + xi):
            inside = not inside
        j = i
    return inside


def _bbox_overlap_polygon(box: Tuple[int, int, int, int], polygon: List[Tuple[int, int]]) -> float:
    """Approximate fraction of the bbox area that falls inside the polygon.
    Samples a 5x5 grid of points inside the box; returns the fraction inside.
    Cheap, no shapely dependency, accurate enough to distinguish "inside",
    "edge-overlap", and "outside" buckets."""
    if not polygon:
        return 1.0
    x_min, y_min, x_max, y_max = box
    if x_max <= x_min or y_max <= y_min:
        return 0.0
    hits = 0
    total = 0
    for i in range(1, 6):
        for j in range(1, 6):
            x = x_min + (x_max - x_min) * i / 6.0
            y = y_min + (y_max - y_min) * j / 6.0
            if _point_in_polygon(x, y, polygon):
                hits += 1
            total += 1
    return hits / total if total else 0.0


def filter_features_against_boundary(
    features: List["Feature"],
    ring_pixels: List[Tuple[int, int]],
) -> List["Feature"]:
    """Drop amenity features whose bbox falls largely outside the cadastral
    boundary. Subject features are always kept (the GPT identification of
    "this is the subject lot" is trusted whenever a yellow polygon is on
    screen). Detractants/context are kept too — they're meant to be off-lot.

    Thresholds:
      - amenity: ≥30% of bbox area must overlap the polygon. Driveways
        legitimately straddle the lot edge so a hard "centre inside" test
        rejects them; 30% area-overlap keeps the edge cases.
    """
    if not ring_pixels or len(ring_pixels) < 3:
        return features
    out: List[Feature] = []
    for f in features:
        if f.category != "amenity":
            out.append(f)
            continue
        overlap = _bbox_overlap_polygon(f.bbox, ring_pixels)
        if overlap >= 0.30:
            out.append(f)
        else:
            logger.info(
                f"  satellite_annotation: dropped '{f.label}' ({f.category}) — "
                f"only {overlap*100:.0f}% of bbox inside lot boundary"
            )
    return out


def detect_features(
    image_bytes: bytes,
    address: str,
    suburb: str,
    model: str = "gpt-4o",
    timeout_s: int = 60,
    has_boundary: bool = False,
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

    prompt_template = USER_PROMPT_TEMPLATE if has_boundary else USER_PROMPT_TEMPLATE_NO_BOUNDARY
    payload = {
        "model": model,
        "messages": [
            {"role": "system", "content": SYSTEM_PROMPT},
            {
                "role": "user",
                "content": [
                    {
                        "type": "text",
                        "text": prompt_template.format(
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
    center_lat: Optional[float] = None,
    center_lng: Optional[float] = None,
    zoom: int = 19,
    tile_scale: int = 2,
) -> Optional[Dict[str, Any]]:
    """Render an annotated satellite PNG with the cadastral lot boundary
    (yellow polygon) and the Fields drop pin on the subject home.

    GPT-based feature detection (pool/driveway/garage bboxes) was removed —
    the model's spatial accuracy on satellite tiles was unreliable enough that
    boxes regularly landed on the wrong pixel region (pool on a tree, driveway
    on grass). The honest visual is the cadastral lot itself plus the pin.

    The categorical + narrative analysis still runs over this same image via
    `step117_satellite_analysis.analyse_satellite_image()` — that call now
    receives the boundary-marked image so the prompt can constrain GPT to
    "only describe features INSIDE the yellow polygon".

    Returns:
        {
          "annotated_image_bytes": bytes,   # tile + yellow boundary + drop pin
          "boundary_marked_bytes": bytes,   # tile + yellow boundary (no pin) —
                                            # the version passed to GPT for analysis
          "boundary_polygon": [[x,y], ...] | None,  # pixel-space ring
          "features": [],                   # empty — kept for back-compat
        }
    or None on failure.
    """
    ring_pixels: Optional[List[Tuple[int, int]]] = None
    boundary_bytes: bytes = image_bytes  # tile + boundary (no pin), fed to GPT

    if center_lat is not None and center_lng is not None:
        try:
            from scripts.property_reports.lot_boundary import fetch_boundary
        except ImportError:
            try:
                from lot_boundary import fetch_boundary  # when run from scripts/property_reports/
            except ImportError:
                fetch_boundary = None  # type: ignore

        if fetch_boundary is not None:
            ring = fetch_boundary(center_lat, center_lng)
            if ring:
                logger.info("  satellite_annotation: got boundary polygon (%d vertices)", len(ring))
                boundary_bytes, ring_pixels = draw_lot_boundary(
                    image_bytes, ring, center_lat, center_lng, zoom, tile_scale
                )
            else:
                logger.info("  satellite_annotation: boundary fetch returned no polygon — using full tile")

    # Draw the drop pin on top of the boundary-marked image. No feature boxes.
    annotated_bytes, display_features = draw_annotations(
        boundary_bytes, [], pin_pixel=pin_pixel,
    )
    return {
        "annotated_image_bytes": annotated_bytes,
        # Boundary-only version (no pin) — passed to step117 GPT analysis so the
        # categorical/narrative prompt can constrain GPT to inside the polygon.
        "boundary_marked_bytes": boundary_bytes,
        # Persisted on the doc so future runs can detect "annotation generated
        # before the boundary code existed" and trigger an upgrade.
        "boundary_polygon": [[int(x), int(y)] for x, y in ring_pixels] if ring_pixels else None,
        "features": [],  # kept for back-compat; box-bounding removed
    }
