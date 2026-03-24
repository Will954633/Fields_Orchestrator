#!/usr/bin/env python3
"""
Batch Photo & Floor Plan Enrichment — Valuation-Grade Schema (For Sale)
Last Edit: 24/02/2026

Processes all unprocessed documents across all 8 target market suburb collections in
Gold_Coast_Currently_For_Sale. Writes property_valuation_data, floor_plan_analysis,
and processing_status to each document.

These fields are preserved when a property sells and is migrated to Gold_Coast_Recently_Sold
by monitor_sold_properties.py (which copies the entire document).

Features:
  - Skips already-processed documents (processing_status.images_processed = True)
  - Resumes from where it left off if interrupted
  - Retry on transient errors (up to MAX_RETRIES per document)
  - Rate limiting between calls to avoid OpenAI throttling

Run:
    python3 enrich_for_sale_batch.py                        # all 8 target market suburbs
    python3 enrich_for_sale_batch.py --collection robina    # single collection
    python3 enrich_for_sale_batch.py --limit 5              # test run
    python3 enrich_for_sale_batch.py --dry-run              # count only
"""

import os
import sys
import json
import base64
import time
import re
import logging
import argparse
from datetime import datetime, timezone
from io import BytesIO
from pathlib import Path

import requests
from PIL import Image
from pymongo import MongoClient
from pymongo.errors import OperationFailure
from openai import OpenAI
from dotenv import load_dotenv


def _cosmos_retry(func, *args, max_retries=5, **kwargs):
    """Execute a MongoDB operation with Cosmos DB 429 retry logic.
    Matches shared/ru_guard.py: 5 attempts, broad error detection, exponential backoff.
    """
    _RETRY_AFTER_RE = re.compile(r"RetryAfterMs[\":]?\s*(\d+)", re.IGNORECASE)
    for attempt in range(max_retries):
        try:
            return func(*args, **kwargs)
        except OperationFailure as e:
            msg = str(e).lower()
            is_throttled = (
                getattr(e, 'code', None) == 16500
                or "toomanyrequests" in msg
                or "requestratetoolarge" in msg
                or "429" in msg
            )
            if is_throttled and attempt < max_retries - 1:
                details_str = str(getattr(e, 'details', ''))
                match = _RETRY_AFTER_RE.search(details_str) or _RETRY_AFTER_RE.search(str(e))
                wait_ms = int(match.group(1)) if match else 500
                sleep_s = min(max(0.3, wait_ms / 1000.0 + 0.25), 5.0)
                time.sleep(sleep_s)
                continue
            raise

# ---------------------------------------------------------------------------
# CONFIGURATION
# ---------------------------------------------------------------------------
DATABASE_NAME = "Gold_Coast"
COLLECTIONS   = [
    "robina",
    "varsity_lakes",
    "burleigh_waters",
]

GPT_MODEL        = "gpt-5.4-2026-03-05"
MAX_TOKENS       = 16000
MAX_PHOTOS       = 20       # cap photos per property
IMAGE_TIMEOUT    = 15       # seconds per image download
REQUEST_TIMEOUT  = 180      # seconds for each GPT call
MAX_RETRIES      = 3        # retries per document on error
RETRY_DELAY      = 10       # seconds between retries
INTER_DOC_DELAY  = 2        # seconds between documents (rate limiting)

LOG_DIR = Path("logs")
LOG_DIR.mkdir(exist_ok=True)

# ---------------------------------------------------------------------------
# PROMPTS (identical to enrich_batch.py in Sold_In_Last_12_Months_8_Suburbs)
# ---------------------------------------------------------------------------
PHOTO_ANALYSIS_PROMPT = """
You are a professional property valuer analysing real estate listing photos for use in market comparison valuations (comparable sales analysis). Your output must use EXACT controlled vocabulary so that MongoDB queries can filter and compare properties consistently.

Analyse all provided property photos and return ONLY a valid JSON object matching this structure. Use null for any field not visible or determinable.

CONTROLLED VOCABULARY — use ONLY these exact strings for categorical fields:

building_type: "house" | "duplex" | "townhouse" | "unit"
architectural_style: "contemporary" | "colonial" | "queenslander" | "federation" | "ranch" | "hamptons" | "other"
roof_type: "tile" | "colorbond" | "metal" | "slate" | "flat"
overall_condition: "excellent" | "good" | "fair" | "poor"
cladding_material: "brick" | "render" | "weatherboard" | "fibro" | "composite" | "stone" | "vinyl"
condition (surfaces/paint/tiles/flooring): "new" | "good" | "fair" | "poor"
paint_condition: "new" | "good" | "fair" | "poor" | "peeling"
window_type: "aluminium" | "timber" | "upvc" | "double_glazed"
driveway_type: "concrete" | "pavers" | "gravel" | "asphalt" | "exposed_aggregate" | "none"
garage_type: "none" | "carport" | "single_garage" | "double_garage" | "triple_garage"
  IMPORTANT — garage vs carport distinction:
    "single_garage" / "double_garage" / "triple_garage" = fully ENCLOSED with walls and a door (roller door or panel lift), built-in or attached to the house. Cars are secured inside.
    "carport" = open-sided structure on posts/poles with a roof but NO enclosing walls. Cars are covered but not enclosed.
    "none" = no covered parking at all.
    When in doubt from photos, look for roller/panel lift doors = garage. Open sides with posts = carport.
fence_type: "none" | "timber" | "colorbond" | "brick" | "pool_fence" | "mixed"
benchtop_material: "stone" | "laminate" | "timber" | "concrete" | "corian"
cabinet_style: "modern" | "hampton" | "traditional" | "shaker" | "handleless"
appliances_quality: "premium" | "standard" | "budget"
splashback_type: "tile" | "glass" | "stone"
natural_light: "excellent" | "good" | "average" | "poor"
vanity_style: "modern" | "traditional" | "floating" | "built_in"
shower_type: "walk_in" | "frameless" | "semi_frameless" | "shower_over_bath" | "enclosed"
fixtures_quality: "premium" | "standard" | "budget"
flooring_type: "carpet" | "timber" | "hybrid" | "tiles" | "vinyl" | "concrete" | "laminate"
ceiling_height: "standard" | "high" | "very_high"
area_label (living areas): "living_room" | "dining_room" | "family_room" | "rumpus" | "media_room"
pool_type: "none" | "inground" | "above_ground" | "lap" | "plunge"
alfresco_size: "small" | "medium" | "large"
landscaping_quality: "manicured" | "well_maintained" | "average" | "overgrown"
overall_renovation_level: "new_build" | "fully_renovated" | "partially_renovated" | "cosmetically_updated" | "original" | "tired"
renovation_recency: "0_5_years" | "5_10_years" | "10_20_years" | "20_plus_years" | "unknown"
maintenance_level: "well_maintained" | "average" | "needs_work" | "poor"
air_conditioning: "ducted" | "split_system" | "none" | "unknown"
image_quality: "professional" | "good" | "average" | "poor"
water_view_type: "none" | "ocean" | "river" | "canal" | "lake" | "bay"
prestige_tier: "standard" | "elevated" | "prestige" | "ultra_prestige"

PRESTIGE TIER — classify the overall build quality and design calibre visible in the photos:
  "standard" = Typical suburban home. Builder-grade finishes, standard layouts, basic materials. Brick, tile roof, laminate benchtops, enclosed showers, standard ceiling heights. No standout design intent. This is the vast majority of homes.
  "elevated" = Above-average home with quality upgrades. May have stone benchtops, good fixtures, renovated kitchen/bathroom, or tasteful cosmetic renovation. Still a conventional design — not architect-designed. Quality is above average but the home does not command a premium beyond its physical features.
  "prestige" = Architect-designed or builder-prestige home that is visually in a different class. Indicators: bespoke design elements (feature walls, void spaces, custom joinery, statement lighting), premium material palette throughout (herringbone timber, natural stone, timber cladding), frameless glass, high or raked ceilings, seamless indoor-outdoor design with oversized openings, and a cohesive design language across the whole property. The home looks like it belongs in an architectural or lifestyle magazine. These homes typically sell for 50-100% above median for their suburb.
  "ultra_prestige" = Landmark or trophy home. Multiple signature features: dramatic architectural statement visible from the street, resort-style grounds, bespoke everything, materials and craftsmanship that are clearly in the top 1% (e.g. imported stone, full automation, commercial-grade kitchen). Extremely rare — only 1-2% of properties should receive this rating.

Key distinction: "elevated" is a nice home well-maintained or nicely renovated. "prestige" is a fundamentally different product — the architecture, materials, and design intent place it in a separate market segment where comparable sales from standard homes are irrelevant.

SCORES: All _score fields use integer 1-10:
  10=exceptional/luxury, 8-9=high quality, 6-7=good/well maintained,
  4-5=average/acceptable, 2-3=below average, 1=poor/significant issues

{
  "property_overview": {
    "building_type": <building_type>,
    "number_of_stories": <integer>,
    "architectural_style": <architectural_style>,
    "roof_type": <roof_type>,
    "overall_condition_score": <1-10>,
    "overall_condition": <overall_condition>
  },

  "exterior": {
    "cladding_material": <cladding_material>,
    "cladding_condition": <condition>,
    "paint_condition": <paint_condition>,
    "window_type": <window_type>,
    "driveway_type": <driveway_type>,
    "garage_type": <garage_type>,
    "garage_condition": <condition or null>,
    "fence_type": <fence_type>,
    "condition_score": <1-10>
  },

  "kitchen": {
    "visible": <true|false>,
    "benchtop_material": <benchtop_material or null>,
    "cabinet_style": <cabinet_style or null>,
    "cabinet_condition": <condition or null>,
    "appliances_quality": <appliances_quality or null>,
    "splashback_type": <splashback_type or null>,
    "island_bench": <true|false>,
    "butler_pantry": <true|false>,
    "natural_light": <natural_light or null>,
    "condition_score": <1-10 or null>,
    "quality_score": <1-10 or null>
  },

  "bathrooms": [
    {
      "bathroom_label": "main_bathroom" | "ensuite_master" | "ensuite_bed2" | "ensuite_bed3" | "powder_room",
      "visible": <true|false>,
      "vanity_style": <vanity_style or null>,
      "tile_condition": <condition or null>,
      "shower_type": <shower_type or null>,
      "bath_present": <true|false>,
      "fixtures_quality": <fixtures_quality or null>,
      "natural_light": <natural_light or null>,
      "condition_score": <1-10 or null>,
      "quality_score": <1-10 or null>
    }
  ],

  "bedrooms": [
    {
      "bedroom_label": "master" | "bedroom_2" | "bedroom_3" | "bedroom_4" | "bedroom_5",
      "visible": <true|false>,
      "flooring_type": <flooring_type or null>,
      "flooring_condition": <condition or null>,
      "paint_condition": <condition or null>,
      "natural_light": <natural_light or null>,
      "ceiling_height": <ceiling_height or null>,
      "built_in_wardrobe": <true|false>,
      "walk_in_robe": <true|false>,
      "ensuite": <true|false>,
      "condition_score": <1-10 or null>,
      "quality_score": <1-10 or null>
    }
  ],

  "living_areas": [
    {
      "area_label": <area_label>,
      "visible": <true|false>,
      "flooring_type": <flooring_type or null>,
      "flooring_condition": <condition or null>,
      "natural_light": <natural_light or null>,
      "ceiling_height": <ceiling_height or null>,
      "open_plan_with_kitchen": <true|false>,
      "condition_score": <1-10 or null>,
      "quality_score": <1-10 or null>
    }
  ],

  "outdoor": {
    "pool_present": <true|false>,
    "pool_type": <pool_type>,
    "pool_condition": <condition or null>,
    "pool_condition_score": <1-10 or null>,
    "alfresco_present": <true|false>,
    "alfresco_covered": <true|false or null>,
    "alfresco_size": <alfresco_size or null>,
    "outdoor_kitchen_bbq": <true|false>,
    "landscaping_quality": <landscaping_quality or null>,
    "landscaping_score": <1-10 or null>,
    "outdoor_entertainment_score": <1-10 or null>,
    "water_views": <true|false>,
    "water_view_type": <water_view_type>,
    "water_view_quality_score": <1-10 or null>
  },

  "renovation": {
    "overall_renovation_level": <overall_renovation_level>,
    "renovation_recency": <renovation_recency>,
    "kitchen_renovated": <true|false>,
    "bathrooms_renovated": <true|false>,
    "flooring_updated": <true|false>,
    "modern_features_score": <1-10>
  },

  "condition_summary": {
    "exterior_score": <1-10>,
    "interior_score": <1-10>,
    "kitchen_score": <1-10 or null>,
    "bathroom_score": <1-10 or null>,
    "outdoor_score": <1-10 or null>,
    "overall_score": <1-10>,
    "maintenance_level": <maintenance_level>
  },

  "property_metadata": {
    "has_study": <true|false>,
    "has_home_office": <true|false>,
    "smart_home_features": <true|false>,
    "solar_visible": <true|false>,
    "air_conditioning": <air_conditioning>,
    "property_presentation_score": <1-10>,
    "market_appeal_score": <1-10>,
    "prestige_tier": <prestige_tier>,
    "unique_features": [<string>, ...],
    "negative_features": [<string>, ...],
    "image_quality": <image_quality>,
    "has_professional_photography": <true|false>,
    "total_images_analyzed": <integer>
  }
}

IMPORTANT NOTES:
- Include one entry per visible bedroom, bathroom, and living area — label them in order (master, bedroom_2, etc.)
- DO NOT count swimming pools as water views. Water views = ocean, river, canal, lake, bay only.
- For bedrooms: if you can only see 2 of 4 bedrooms, include 2 entries with visible=true and infer the others with visible=false if clearly present
- Return ONLY valid JSON, no text outside the JSON object
"""

FLOOR_PLAN_PROMPT = """You are a professional floor plan analyst. Analyze the provided floor plan image(s) and extract ALL useful information that a home buyer would want to know.

Please provide a comprehensive analysis in JSON format with the following structure:

{
    "internal_floor_area": {
        "value": <number or null>,
        "unit": "sqm" or "m2" or null,
        "confidence": "high" | "medium" | "low",
        "notes": "Internal living area only - excludes garage, porches, external storage"
    },
    "total_floor_area": {
        "value": <number or null>,
        "unit": "sqm" or "m2" or null,
        "confidence": "high" | "medium" | "low",
        "notes": "Total building footprint including garage, porches, covered areas"
    },
    "external_floor_area": {
        "value": <number or null>,
        "unit": "sqm" or "m2" or null,
        "confidence": "high" | "medium" | "low",
        "source": "explicit_label" | "calculated",
        "notes": "Covered external areas only (garage, alfresco, porch, carport). If labelled explicitly on plan (e.g. 'External 33.4 m2') use that value and set source to 'explicit_label'. Otherwise calculate as total_floor_area minus internal_floor_area and set source to 'calculated'. Use null if neither internal nor total area is known."
    },
    "total_land_area": {
        "value": <number or null>,
        "unit": "sqm" or "m2" or null,
        "confidence": "high" | "medium" | "low",
        "notes": "any relevant notes"
    },
    "levels": {
        "total_levels": <number>,
        "level_details": [
            {
                "level_name": "Ground Floor" | "First Floor" | "Second Floor" | etc,
                "floor_area": {
                    "value": <number or null>,
                    "unit": "sqm" or "m2" or null
                }
            }
        ]
    },
    "rooms": [
        {
            "room_type": "living_room" | "kitchen" | "dining_room" | "bedroom" | "bathroom" | "laundry" | "garage" | "study" | "family_room" | "rumpus" | "media_room" | "powder_room" | "ensuite" | "walk_in_robe" | "balcony" | "patio" | "deck" | "alfresco" | "entry" | "hallway" | "storage" | "other",
            "room_name": "specific name from floor plan (e.g., 'Master Bedroom', 'Bedroom 1', 'Main Bathroom')",
            "level": "Ground Floor" | "First Floor" | etc,
            "dimensions": {
                "length": <number or null>,
                "width": <number or null>,
                "unit": "m" | "meters" | null,
                "area": <number or null>,
                "area_unit": "sqm" | "m2" | null
            },
            "features": [
                "list of features like 'ensuite', 'walk-in robe', 'built-in wardrobes', 'air conditioning', etc"
            ],
            "notes": "any additional relevant information"
        }
    ],
    "bedrooms": {
        "total_count": <number>,
        "details": "summary of all bedrooms"
    },
    "bathrooms": {
        "total_count": <number>,
        "full_bathrooms": <number>,
        "powder_rooms": <number>,
        "ensuites": <number>,
        "details": "summary of all bathrooms"
    },
    "parking": {
        "garage_spaces": <number>,
        "carport_spaces": <number>,
        "total_spaces": <number>,
        "garage_type": "single" | "double" | "triple" | "tandem" | null,
        "notes": "any relevant parking details"
    },
    "outdoor_spaces": [
        {
            "type": "balcony" | "patio" | "deck" | "alfresco" | "courtyard" | "garden" | "terrace" | "pool",
            "level": "Ground Floor" | "First Floor" | etc,
            "dimensions": {
                "length": <number or null>,
                "width": <number or null>,
                "area": <number or null>,
                "unit": "sqm" | "m2" | null
            },
            "features": ["covered", "uncovered", "access from living room", etc]
        }
    ],
    "layout_features": {
        "open_plan": true | false,
        "split_level": true | false,
        "flow_description": "description of how rooms connect and flow",
        "highlights": ["key selling points of the layout"]
    },
    "additional_features": [
        "any other notable features like 'study nook', 'butler's pantry', 'wine cellar', 'home office', 'gym area', etc"
    ],
    "buyer_insights": {
        "ideal_for": ["families", "couples", "retirees", "investors", etc],
        "key_benefits": ["list of main selling points"],
        "considerations": ["any potential drawbacks or things to note"],
        "lifestyle_suitability": "description of lifestyle this property suits"
    },
    "data_quality": {
        "floor_plan_clarity": "excellent" | "good" | "fair" | "poor",
        "measurements_available": true | false,
        "missing_information": ["list of information that couldn't be determined"],
        "confidence_overall": "high" | "medium" | "low"
    }
}

IMPORTANT INSTRUCTIONS:
1. FLOOR AREA DISTINCTION — THREE SEPARATE VALUES:
   - internal_floor_area = Living spaces only (bedrooms, living, kitchen, bathrooms, laundry, hallways). Excludes garage, alfresco, porches.
   - total_floor_area = internal PLUS all covered external areas (garage, alfresco, carport, porch, covered deck).
   - external_floor_area = covered external areas only = total minus internal.
     * FIRST: look for an explicit label on the plan such as "External 33.4 m2" or "Covered External" — if found, use it and set source="explicit_label".
     * OTHERWISE: calculate as total_floor_area - internal_floor_area and set source="calculated".
     * If only one of internal or total is shown (not both), set external_floor_area value to null.
   - Look for labels like "Internal Floor Area", "Total Floor Area", "Building Area", "External Area".

2. Extract ALL measurements shown on the floor plan - don't miss any room dimensions

3. Count ALL bedrooms - there is no upper limit, extract however many exist (could be 1, 2, 3, 4, 5, 6, or more)

4. For each room, capture:
   - Exact dimensions if shown (length x width)
   - Calculated or stated area
   - All features mentioned (ensuite, robe, island, pantry, etc.)

5. Be thorough - extract every piece of useful information visible
5. If information is not available or unclear, use null and note it in the appropriate field
6. Provide confidence levels honestly based on available information
7. In buyer_insights, think about what makes this property unique and valuable
8. Include all room types, not just bedrooms - living areas, outdoor spaces, storage, etc.
9. For outdoor spaces, include pools, patios, decks, alfresco areas, etc.
10. Note any special features like butler's pantry, study nooks, storage areas, etc.

Return ONLY valid JSON, no additional text or explanation outside the JSON structure."""


# ---------------------------------------------------------------------------
# LOGGING
# ---------------------------------------------------------------------------

def setup_logger(log_file: Path) -> logging.Logger:
    logger = logging.getLogger("enrich_for_sale_batch")
    logger.setLevel(logging.INFO)
    fmt = logging.Formatter("%(asctime)s [%(levelname)s] %(message)s", datefmt="%H:%M:%S")

    ch = logging.StreamHandler()
    ch.setFormatter(fmt)
    logger.addHandler(ch)

    fh = logging.FileHandler(log_file)
    fh.setFormatter(fmt)
    logger.addHandler(fh)

    return logger


# ---------------------------------------------------------------------------
# IMAGE HELPERS
# ---------------------------------------------------------------------------

def _image_key(url: str) -> str:
    match = re.search(r'(\d{10}_\d+_\d+_\d+_\d+)', url)
    return match.group(1) if match else url


def clean_image_urls(raw_urls: list) -> list:
    cleaned = [u.rstrip('\\').strip() for u in raw_urls if u and isinstance(u, str)]
    best: dict[str, str] = {}
    for url in cleaned:
        key = _image_key(url)
        if key not in best:
            best[key] = url
        else:
            if 'rimh2.domainstatic.com' in url:
                best[key] = url
    return list(best.values())[:MAX_PHOTOS]


def url_to_base64(url: str) -> str | None:
    try:
        resp = requests.get(url, timeout=IMAGE_TIMEOUT)
        resp.raise_for_status()
        img = Image.open(BytesIO(resp.content)).convert("RGB")
        buf = BytesIO()
        img.save(buf, format="JPEG", quality=85)
        encoded = base64.b64encode(buf.getvalue()).decode("utf-8")
        return f"data:image/jpeg;base64,{encoded}"
    except Exception:
        return None


def build_image_content(urls: list) -> list:
    blocks = []
    for url in urls:
        data_uri = url_to_base64(url)
        if data_uri:
            blocks.append({
                "type": "image_url",
                "image_url": {"url": data_uri, "detail": "high"}
            })
    return blocks


# ---------------------------------------------------------------------------
# GPT CALLS
# ---------------------------------------------------------------------------

def call_gpt(client: OpenAI, system_prompt: str, user_prompt: str, image_content: list) -> dict:
    messages = [
        {"role": "system", "content": system_prompt},
        {"role": "user", "content": [{"type": "text", "text": user_prompt}] + image_content}
    ]
    response = client.chat.completions.create(
        model=GPT_MODEL,
        messages=messages,
        max_completion_tokens=MAX_TOKENS,
        response_format={"type": "json_object"}
    )
    content = response.choices[0].message.content
    if not content or not content.strip():
        raise ValueError("Empty response from GPT")
    return json.loads(content)


def analyse_photos(client: OpenAI, photo_urls: list) -> dict:
    image_content = build_image_content(photo_urls)
    if not image_content:
        raise ValueError("No images could be downloaded")
    return call_gpt(
        client,
        system_prompt="You are a professional property valuer with expertise in market comparison analysis.",
        user_prompt=PHOTO_ANALYSIS_PROMPT,
        image_content=image_content
    )


def _backfill_room_areas(result: dict) -> dict:
    """Calculate area = width * length for any room where GPT left area as null."""
    rooms = result.get("rooms")
    if not rooms or not isinstance(rooms, list):
        return result
    for room in rooms:
        dims = room.get("dimensions")
        if not isinstance(dims, dict):
            continue
        w = dims.get("width")
        l = dims.get("length")
        a = dims.get("area")
        if w and l and not a:
            dims["area"] = round(float(w) * float(l), 2)
    return result


def analyse_floor_plans(client: OpenAI, floor_plan_urls: list) -> dict:
    image_content = build_image_content(floor_plan_urls)
    if not image_content:
        raise ValueError("No floor plan images could be downloaded")
    result = call_gpt(
        client,
        system_prompt="You are a professional floor plan analyst extracting detailed room dimensions and layout information.",
        user_prompt=FLOOR_PLAN_PROMPT,
        image_content=image_content
    )
    return _backfill_room_areas(result)


# ---------------------------------------------------------------------------
# PROCESS SINGLE DOCUMENT
# ---------------------------------------------------------------------------

def detect_water_views_from_description(doc: dict) -> dict:
    """Detect water views from agent's listing description and features list.

    Agent descriptions always mention water views if they exist — it's a
    high-value selling point that is never omitted.  This is more reliable
    than GPT-4o Vision which can confuse pools with water views.

    Returns dict with water_views, water_view_type, water_view_quality_score.
    """
    text = (doc.get("agents_description") or "").lower()
    features = [f.lower() for f in (doc.get("features") or [])]
    features_text = " ".join(features)
    combined = text + " " + features_text

    # Patterns that indicate genuine water views
    view_patterns = [
        (r'\bocean\s*view', "ocean"),
        (r'\bsea\s*view', "ocean"),
        (r'\bbeach\s*view', "ocean"),
        (r'\briver\s*view', "river"),
        (r'\briver\s*front', "river"),
        (r'\bcanal\s*view', "canal"),
        (r'\bcanal\s*front', "canal"),
        (r'\blake\s*view', "lake"),
        (r'\blake\s*front', "lake"),
        (r'\bbay\s*view', "bay"),
        (r'\bwater\s*view', "lake"),      # generic "water views" — default to lake for GC suburbs
        (r'\bwater\s*front', "lake"),
        (r'\bwaterfront', "lake"),
    ]

    for pattern, view_type in view_patterns:
        if re.search(pattern, combined):
            return {
                "water_views": True,
                "water_view_type": view_type,
                "water_view_quality_score": 7,  # conservative default; agent said it exists
            }

    return {
        "water_views": False,
        "water_view_type": "none",
        "water_view_quality_score": None,
    }


def process_document(doc: dict, collection, client: OpenAI, logger: logging.Logger) -> dict:
    doc_id = doc["_id"]
    address = doc.get("address", str(doc_id))

    raw_images = doc.get("property_images", [])
    raw_floor_plans = doc.get("floor_plans", [])

    photo_urls = clean_image_urls(raw_images)
    floor_plan_urls = [u.rstrip('\\').strip() for u in raw_floor_plans if u and isinstance(u, str)]

    if not photo_urls:
        logger.warning(f"  SKIP (no photos): {address}")
        _cosmos_retry(collection.update_one, {"_id": doc_id}, {"$set": {
            "processing_status": {
                "images_processed": True,
                "skipped": True,
                "skip_reason": "no_photos",
                "processed_at": datetime.now(timezone.utc),
                "model_used": GPT_MODEL
            }
        }})
        return {"success": False, "skipped": True, "had_floor_plan": False, "error": "no_photos"}

    now = datetime.now(timezone.utc)

    # --- Call 1: Photos ---
    photo_result = analyse_photos(client, photo_urls)

    # --- Call 2: Floor plans (if any) ---
    floor_plan_result = None
    if floor_plan_urls:
        try:
            floor_plan_result = analyse_floor_plans(client, floor_plan_urls)
        except Exception as e:
            logger.warning(f"  Floor plan analysis failed for {address}: {e}")

    # --- Build update ---
    processing_status = {
        "images_processed": True,
        "photos_analysed": len(photo_urls),
        "floor_plan_analysed": floor_plan_result is not None,
        "floor_plans_analysed": len(floor_plan_urls) if floor_plan_result else 0,
        "processed_at": now,
        "model_used": GPT_MODEL
    }

    if floor_plan_result:
        internal = floor_plan_result.get("internal_floor_area") or {}
        external = floor_plan_result.get("external_floor_area") or {}
        total    = floor_plan_result.get("total_floor_area") or {}
        processing_status["internal_floor_area_sqm"] = internal.get("value")
        processing_status["external_floor_area_sqm"] = external.get("value")
        processing_status["total_floor_area_sqm"]    = total.get("value")

    # Override GPT's water_views with description-based detection (more reliable)
    water = detect_water_views_from_description(doc)
    if "outdoor" not in photo_result:
        photo_result["outdoor"] = {}
    photo_result["outdoor"]["water_views"] = water["water_views"]
    photo_result["outdoor"]["water_view_type"] = water["water_view_type"]
    photo_result["outdoor"]["water_view_quality_score"] = water["water_view_quality_score"]

    update_set = {
        "property_valuation_data": photo_result,
        "processing_status": processing_status
    }
    if floor_plan_result:
        update_set["floor_plan_analysis"] = floor_plan_result

    _cosmos_retry(collection.update_one, {"_id": doc_id}, {"$set": update_set})

    return {
        "success": True,
        "skipped": False,
        "had_floor_plan": floor_plan_result is not None,
        "error": None
    }


# ---------------------------------------------------------------------------
# MAIN
# ---------------------------------------------------------------------------

def main():
    parser = argparse.ArgumentParser(description="Batch enrichment for Gold_Coast_Currently_For_Sale")
    parser.add_argument("--dry-run",    action="store_true", help="Count documents only, no GPT calls")
    parser.add_argument("--collection", type=str,            help="Process a single collection only")
    parser.add_argument("--limit",      type=int, default=0, help="Max documents to process (0=all)")
    args = parser.parse_args()

    load_dotenv(dotenv_path=".env")
    COSMOS_URI = os.getenv("COSMOS_CONNECTION_STRING")
    OPENAI_KEY = os.getenv("OPENAI_API_KEY")

    if not COSMOS_URI:
        sys.exit("ERROR: COSMOS_CONNECTION_STRING not found in .env")
    if not OPENAI_KEY:
        sys.exit("ERROR: OPENAI_API_KEY not found in .env")

    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    log_file = LOG_DIR / f"enrich_for_sale_{ts}.log"
    logger = setup_logger(log_file)

    logger.info("=" * 70)
    logger.info("BATCH ENRICHMENT — FOR SALE — VALUATION-GRADE SCHEMA")
    logger.info(f"Database: {DATABASE_NAME}")
    logger.info("=" * 70)
    logger.info(f"Log file: {log_file}")

    mongo = MongoClient(COSMOS_URI, serverSelectionTimeoutMS=20000)
    db = mongo[DATABASE_NAME]
    client = OpenAI(api_key=OPENAI_KEY) if not args.dry_run else None

    target_collections = [args.collection] if args.collection else COLLECTIONS

    FS_FILTER = {"listing_status": "for_sale"}

    grand_total = grand_todo = 0
    for col_name in target_collections:
        col = db[col_name]
        total = _cosmos_retry(col.count_documents, FS_FILTER)
        todo  = _cosmos_retry(col.count_documents, {**FS_FILTER, "$or": [
            {"processing_status.images_processed": {"$ne": True}},
            {"property_valuation_data.condition_summary": {"$exists": False}}
        ]})
        logger.info(f"  {col_name:<20} for_sale={total}  to_process={todo}")
        grand_total += total
        grand_todo  += todo

    logger.info(f"\n  Grand total: {grand_total}  To process: {grand_todo}")

    if args.limit:
        logger.info(f"  Limit: {args.limit} documents")
    if args.dry_run:
        logger.info("  DRY RUN — no GPT calls will be made")
        mongo.close()
        return 0

    logger.info("")

    run_stats = {
        "processed": 0,
        "succeeded": 0,
        "failed": 0,
        "skipped": 0,
        "with_floor_plan": 0,
        "errors": []
    }

    run_start = time.time()
    docs_processed = 0

    for col_name in target_collections:
        col = db[col_name]
        col_count = 0
        col_start = time.time()

        for doc in col.find(FS_FILTER):
            if args.limit and docs_processed >= args.limit:
                break

            # Skip already processed — but re-process if condition_summary is missing
            # (stale flag from pre-listing cadastral processing)
            ps = doc.get("processing_status") or {}
            if ps.get("images_processed"):
                pvd = doc.get("property_valuation_data") or {}
                if pvd.get("condition_summary"):
                    continue

            address = doc.get("address", str(doc["_id"]))
            docs_processed += 1
            col_count += 1
            run_stats["processed"] += 1

            logger.info(f"[{col_name}] ({docs_processed}/{grand_todo}) {address}")

            success = False
            for attempt in range(1, MAX_RETRIES + 1):
                try:
                    result = process_document(doc, col, client, logger)

                    if result["skipped"]:
                        run_stats["skipped"] += 1
                        success = True
                        break

                    run_stats["succeeded"] += 1
                    if result["had_floor_plan"]:
                        run_stats["with_floor_plan"] += 1

                    elapsed = time.time() - run_start
                    rate = docs_processed / elapsed * 60 if elapsed > 0 else 0
                    logger.info(f"  ✓ done (floor_plan={result['had_floor_plan']}) | {rate:.1f} docs/min")
                    success = True
                    break

                except Exception as e:
                    logger.warning(f"  Attempt {attempt}/{MAX_RETRIES} failed: {e}")
                    if attempt < MAX_RETRIES:
                        time.sleep(RETRY_DELAY)

            if not success:
                run_stats["failed"] += 1
                run_stats["errors"].append({"address": address, "collection": col_name, "id": str(doc["_id"])})
                logger.error(f"  ✗ FAILED after {MAX_RETRIES} attempts: {address}")
                _cosmos_retry(col.update_one, {"_id": doc["_id"]}, {"$set": {
                    "processing_status.enrichment_failed": True,
                    "processing_status.last_error_at": datetime.now(timezone.utc)
                }})

            time.sleep(INTER_DOC_DELAY)

        col_elapsed = time.time() - col_start
        logger.info(f"\n  [{col_name}] Completed {col_count} documents in {col_elapsed/60:.1f} min\n")

        if args.limit and docs_processed >= args.limit:
            break

    total_elapsed = time.time() - run_start
    logger.info("=" * 70)
    logger.info("RUN COMPLETE")
    logger.info("=" * 70)
    logger.info(f"  Total processed:    {run_stats['processed']}")
    logger.info(f"  Succeeded:          {run_stats['succeeded']}")
    logger.info(f"  With floor plan:    {run_stats['with_floor_plan']}")
    logger.info(f"  Skipped (no photos):{run_stats['skipped']}")
    logger.info(f"  Failed:             {run_stats['failed']}")
    logger.info(f"  Total time:         {total_elapsed/60:.1f} min")
    if run_stats["processed"] > 0:
        logger.info(f"  Avg time/doc:       {total_elapsed/run_stats['processed']:.1f}s")

    if run_stats["errors"]:
        logger.info(f"\n  Failed documents:")
        for e in run_stats["errors"]:
            logger.info(f"    [{e['collection']}] {e['address']} ({e['id']})")

    mongo.close()
    return 0


if __name__ == "__main__":
    sys.exit(main())
