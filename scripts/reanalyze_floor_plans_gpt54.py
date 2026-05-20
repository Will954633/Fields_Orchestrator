#!/usr/bin/env python3
"""
One-off script: Re-analyze all active listing floor plans with gpt-5.4-2026-03-05.
Replaces bad gpt-5-nano room dimensions in floor_plan_analysis and parsed_rooms.
"""

import base64
import json
import os
import sys
import time
from datetime import datetime
from io import BytesIO

import requests
from PIL import Image
from pymongo import MongoClient

MODEL = "gpt-5.4-2026-03-05"
TARGET_SUBURBS = [
    "robina", "varsity_lakes", "burleigh_waters", "burleigh_heads",
    "mudgeeraba", "reedy_creek", "merrimac", "worongary", "carrara",
]
INTER_REQUEST_DELAY = 0.5  # seconds between API calls

PROMPT = """You are a professional floor plan analyst. Analyze this floor plan and extract ONLY the essential measurements and room counts.

Provide your analysis in this EXACT JSON format:

{
    "internal_floor_area": {"value": <number or null>, "unit": "sqm", "notes": "Internal living area only"},
    "total_floor_area": {"value": <number or null>, "unit": "sqm", "notes": "Total including garage"},
    "total_land_area": {"value": <number or null>, "unit": "sqm"},
    "bedrooms": {"total_count": <number>, "list": ["Master Bedroom", "Bedroom 2", etc]},
    "bathrooms": {"total_count": <number>, "full_bathrooms": <number>, "powder_rooms": <number>, "ensuites": <number>},
    "parking": {"garage_spaces": <number>, "carport_spaces": <number>, "garage_type": "single"|"double"|"triple"|null},
    "levels": {"total_levels": <number>, "level_names": ["Ground Floor", etc]},
    "rooms": [
        {
            "room_name": "Room Name",
            "room_type": "bedroom|bathroom|kitchen|living|dining|laundry|garage|media|family|study|deck|porch|ensuite|other",
            "level": "Ground Floor",
            "dimensions": {"length": <number or null>, "width": <number or null>, "area": <number or null>, "unit": "m"}
        }
    ]
}

INSTRUCTIONS:
1. Extract ALL room dimensions shown on the floor plan — READ THE TEXT LABELS CAREFULLY
2. Floor plans often have dimensions printed as "X.X m x Y.Y m - ZZ m2" — transcribe these EXACTLY
3. Count ALL bedrooms (no limit - could be 1, 2, 3, 4, 5, 6+)
4. Distinguish internal floor area from total floor area
5. List every room with its dimensions if shown
6. Use null for missing data
7. Be accurate and thorough with measurements

Return ONLY valid JSON, no additional text."""


_DOMAIN_CDN_RE = __import__("re").compile(
    r"rimh2\.domainstatic\.com\.au/[^/]+(?:/filters:[^/]+)?/(.+)"
)


def _to_bucket_api_url(url: str) -> str:
    """Convert Domain CDN URL to bucket-api (full resolution, no signed hash)."""
    m = _DOMAIN_CDN_RE.search(url)
    if m:
        return f"https://bucket-api.domain.com.au/v1/bucket/image/{m.group(1)}"
    return url


MIN_FLOOR_PLAN_PIXELS = 500  # shortest side below this → treat as thumbnail


def download_and_encode(url: str) -> str | None:
    def _fetch(u):
        resp = requests.get(u, timeout=30, headers={"User-Agent": "Mozilla/5.0"})
        resp.raise_for_status()
        return resp.content

    try:
        content = _fetch(url)
        img = Image.open(BytesIO(content))
        # If CDN served a thumbnail, retry with bucket-api full-res URL
        if min(img.size) < MIN_FLOOR_PLAN_PIXELS:
            fallback = _to_bucket_api_url(url)
            if fallback != url:
                print(f"    CDN thumbnail ({img.size[0]}×{img.size[1]}), retrying bucket-api...")
                content = _fetch(fallback)
                img = Image.open(BytesIO(content))
        if img.mode not in ("RGB", "L"):
            img = img.convert("RGB")
        buf = BytesIO()
        img.save(buf, format="JPEG", quality=95)
        return f"data:image/jpeg;base64,{base64.b64encode(buf.getvalue()).decode()}"
    except Exception as e:
        print(f"    Failed to download {url}: {e}")
        return None


def call_gpt54(image_data_uri: str) -> dict | None:
    headers = {
        "Content-Type": "application/json",
        "Authorization": f"Bearer {os.environ['OPENAI_API_KEY']}",
    }
    payload = {
        "model": MODEL,
        "messages": [
            {
                "role": "user",
                "content": [
                    {"type": "text", "text": PROMPT},
                    {"type": "image_url", "image_url": {"url": image_data_uri, "detail": "high"}},
                ],
            }
        ],
        "max_completion_tokens": 16384,
        "response_format": {"type": "json_object"},
    }
    resp = requests.post(
        "https://api.openai.com/v1/chat/completions",
        headers=headers,
        json=payload,
        timeout=120,
    )
    if resp.status_code != 200:
        print(f"    API error {resp.status_code}: {resp.text[:300]}")
        return None
    content = resp.json()["choices"][0]["message"]["content"]
    return json.loads(content)


def build_parsed_rooms(rooms: list) -> dict:
    """Convert rooms list to parsed_rooms dict for website display."""
    parsed = {}
    bedroom_count = 0
    for room in rooms:
        rt = room.get("room_type", "other")
        name = room.get("room_name", "Unknown")
        dims = room.get("dimensions", {})

        if rt in ("bedroom",):
            bedroom_count += 1
            key = "bedroom" if bedroom_count == 1 else f"bedroom_{bedroom_count}"
        elif rt in ("living", "living_room"):
            key = "living_room"
        elif rt in ("dining", "dining_room"):
            key = "dining_room"
        elif rt in ("family", "family_room"):
            key = "family_room"
        elif rt in ("media", "media_room", "cinema"):
            key = "cinema_room"
        else:
            key = rt.lower().replace(" ", "_")

        # Avoid duplicate keys
        if key in parsed:
            key = f"{key}_{bedroom_count}" if "bedroom" not in key else key

        parsed[key] = {
            "length": dims.get("length"),
            "width": dims.get("width"),
            "area": dims.get("area"),
            "source": MODEL,
            "room_name": name,
        }
    return parsed


def main():
    client = MongoClient(os.environ["COSMOS_CONNECTION_STRING"])
    db = client["Gold_Coast"]

    total = 0
    success = 0
    errors = 0
    skipped = 0

    for suburb in TARGET_SUBURBS:
        coll = db[suburb]
        props = list(
            coll.find(
                {"floor_plans": {"$exists": True, "$ne": []}, "listing_status": "for_sale"},
                {"address": 1, "floor_plans": 1},
            )
        )
        if not props:
            continue

        print(f"\n{'='*60}")
        print(f"{suburb.upper()}: {len(props)} properties with floor plans")
        print(f"{'='*60}")

        for i, prop in enumerate(props, 1):
            total += 1
            addr = prop.get("address", str(prop["_id"]))
            fp_urls = prop.get("floor_plans", [])

            if not fp_urls:
                skipped += 1
                continue

            fp_url = fp_urls[0]  # Use first floor plan
            print(f"  [{i}/{len(props)}] {addr}")

            try:
                encoded = download_and_encode(fp_url)
                if not encoded:
                    errors += 1
                    continue

                result = call_gpt54(encoded)
                if not result:
                    errors += 1
                    continue

                rooms = result.get("rooms", [])
                parsed = build_parsed_rooms(rooms)

                # Build floor_plan_analysis update
                fpa = {
                    "internal_floor_area": result.get("internal_floor_area", {}),
                    "total_floor_area": result.get("total_floor_area", {}),
                    "total_land_area": result.get("total_land_area", {}),
                    "levels": {
                        "total_levels": result.get("levels", {}).get("total_levels", 1),
                        "level_details": [
                            {"level_name": ln, "floor_area": {"value": None, "unit": "sqm"}}
                            for ln in result.get("levels", {}).get("level_names", ["Ground Floor"])
                        ],
                    },
                    "rooms": [
                        {
                            "room_type": r.get("room_type", "other"),
                            "room_name": r.get("room_name", "Unknown"),
                            "level": r.get("level", "Ground Floor"),
                            "dimensions": {
                                "length": r.get("dimensions", {}).get("length"),
                                "width": r.get("dimensions", {}).get("width"),
                                "unit": "m",
                                "area": r.get("dimensions", {}).get("area"),
                                "area_unit": "sqm",
                            },
                            "features": [],
                            "notes": "",
                        }
                        for r in rooms
                    ],
                    "model_used": MODEL,
                    "reanalyzed_at": datetime.utcnow(),
                    "reanalysis_reason": "batch re-analysis: gpt-5-nano → gpt-5.4",
                }

                # Also update total_floor_area at root level if available
                tfa = result.get("total_floor_area", {}).get("value")
                update_set = {
                    "floor_plan_analysis": fpa,
                    "parsed_rooms": parsed,
                    "parsed_rooms_updated": datetime.utcnow(),
                }
                if tfa:
                    update_set["total_floor_area"] = float(tfa)

                coll.update_one({"_id": prop["_id"]}, {"$set": update_set})
                success += 1
                room_count = len(rooms)
                print(f"    ✓ {room_count} rooms extracted")

            except Exception as e:
                errors += 1
                print(f"    ✗ Error: {e}")

            time.sleep(INTER_REQUEST_DELAY)

    print(f"\n{'='*60}")
    print(f"COMPLETE: {success} succeeded, {errors} errors, {skipped} skipped out of {total}")
    print(f"{'='*60}")

    client.close()


if __name__ == "__main__":
    main()
