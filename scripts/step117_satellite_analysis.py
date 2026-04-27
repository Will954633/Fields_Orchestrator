#!/usr/bin/env python3
"""
Step 117 — Satellite Image Analysis (Google Maps Static + GPT-5.4 Vision)

Fetches a satellite image for each target-market property using the Google Maps
Static API, sends it to GPT-5.4 for buyer-perspective analysis of surroundings,
and writes a structured `satellite_analysis` field to the property document.

What GPT analyses from the aerial view:
- Surrounding land use (parks, commercial, industrial, vacant land)
- Road proximity & traffic noise risk (arterials, cul-de-sac, highway)
- Green cover / tree canopy maturity
- Lot shape, usable space, setbacks
- Neighbour density & overlooking risk
- Pool visibility (subject + neighbours)
- Flood/drainage indicators (waterways, retention basins, low-lying areas)
- Construction / development activity nearby
- Parking & access quality
"""

from __future__ import annotations

import base64
import io
import os
import sys
import time
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional

import requests
from openai import OpenAI

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT))

from shared.env import load_env  # type: ignore
from shared.db import get_client, get_db, cosmos_retry, EmptyWorkSetError, sleep_with_jitter  # type: ignore
from shared import blob_storage  # type: ignore
from shared.monitor_client import MonitorClient  # type: ignore

load_env()

# ---------------------------------------------------------------------------
# Config
# ---------------------------------------------------------------------------

TARGET_SUBURBS = ["robina", "varsity_lakes", "burleigh_waters"]
DATABASE_NAME = "Gold_Coast"

GOOGLE_MAPS_API_KEY = os.getenv("GOOGLE_MAPS_STATIC_API_KEY", os.getenv("GOOGLE_PLACES_API_KEY", ""))
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY", "")

# Google Maps Static API settings
SATELLITE_ZOOM = 19          # Close enough to see roof, yard, neighbours
SATELLITE_SIZE = "640x640"   # Max free-tier size
SATELLITE_MAPTYPE = "satellite"
SATELLITE_SCALE = 2          # 1280x1280 actual pixels (retina)

# GPT model for vision analysis
GPT_MODEL = "gpt-5.4"

# Azure Blob Storage
AZURE_STORAGE_CONNECTION_STRING = os.getenv("AZURE_STORAGE_CONNECTION_STRING", "")
BLOB_CONTAINER = "property-images"
BLOB_DOMAIN = "blob.core.windows.net"

# Rate limiting
MAPS_API_DELAY = 0.2         # 200ms between Google Maps requests
GPT_DELAY = 1.0              # 1s between GPT calls to avoid rate limits
PROPERTY_TIMEOUT_SECONDS = int(os.getenv("STEP117_PROPERTY_TIMEOUT_SECONDS", "120"))

# ---------------------------------------------------------------------------
# Candidate query builder
# ---------------------------------------------------------------------------

def build_candidate_query(status_filter: Optional[str] = "for_sale") -> Dict[str, Any]:
    """Build the MongoDB query for properties needing satellite analysis.

    Args:
        status_filter: "for_sale", "sold", or "all" (no listing_status filter).
    """
    conditions: List[Dict[str, Any]] = [
        # Must have either geocoded coordinates OR an address to use
        {
            "$or": [
                {"geocoded_coordinates.latitude": {"$exists": True}},
                {"address": {"$exists": True, "$ne": ""}},
            ]
        },
        {
            "$or": [
                {"satellite_analysis": {"$exists": False}},
                {"satellite_analysis": None},
            ]
        },
    ]

    if status_filter == "for_sale":
        conditions.insert(0, {"listing_status": "for_sale"})
    elif status_filter == "sold":
        conditions.insert(0, {"listing_status": "sold"})
    elif status_filter == "remaining":
        # Everything that is NOT for_sale and NOT sold (cadastral, withdrawn, etc.)
        conditions.insert(0, {"listing_status": {"$nin": ["for_sale", "sold"]}})
    # "all" — no listing_status filter

    return {"$and": conditions}

# ---------------------------------------------------------------------------
# GPT Prompt
# ---------------------------------------------------------------------------

SYSTEM_PROMPT = """You are a property analyst reviewing a satellite / aerial image of a residential property on the Gold Coast, Queensland, Australia.

Analyse the image from the perspective of a potential buyer. Be specific and factual — describe what you can actually see, not what you assume.

Return your analysis as a JSON object with TWO sections:

1. **"categories"** — structured categorical data used as machine-readable inputs for valuation models and filters. Every field MUST use ONLY the allowed values listed below.
2. **"narrative"** — free-form text analysis where you describe everything you observe in detail.

```json
{
  "categories": {
    "adjacency": {
      "backs_onto": ["One or more of: busy_road, quiet_street, cul_de_sac, park, reserve, golf_course, waterway, canal, lake, bushland, commercial, shopping_centre, school, railway, power_lines, industrial, vacant_land, residential_only, highway, sports_field, church, medical_facility"],
      "frontage": "One of: standard_street, corner_lot, battle_axe, dual_frontage, cul_de_sac_head, main_road",
      "elevation_position": "One of: elevated, flat, low_lying, hilltop, slope_up, slope_down"
    },
    "detractants": {
      "traffic_noise_risk": "One of: none, low, moderate, high",
      "flight_path": false,
      "power_line_proximity": "One of: none, adjacent, nearby, overhead",
      "commercial_adjacency": "One of: none, adjacent, nearby",
      "construction_disruption": "One of: none, adjacent_development, nearby_development",
      "overlooking_risk": "One of: none, low, moderate, high",
      "flood_indicator": "One of: none, low_lying, near_waterway, retention_basin_adjacent"
    },
    "amenity_premiums": {
      "water_proximity": "One of: none, canal_front, lake_front, river_front, ocean_view, canal_adjacent, lake_adjacent",
      "green_space_proximity": "One of: none, park_adjacent, reserve_adjacent, golf_course_adjacent, golf_course_nearby, bushland_adjacent",
      "pool_visible": false,
      "outdoor_entertaining": "One of: none, basic, substantial",
      "mature_landscaping": "One of: none, moderate, extensive",
      "street_appeal": "One of: poor, average, good, excellent"
    },
    "lot_characteristics": {
      "lot_shape": "One of: regular, irregular, pie_shaped, triangular, long_narrow, flag_lot",
      "usable_yard": "One of: minimal, moderate, generous",
      "neighbour_setback": "One of: tight, standard, generous",
      "parking_provision": "One of: single_garage, double_garage, triple_garage, carport, on_street_only, unknown"
    },
    "neighbourhood": {
      "density": "One of: low, medium, high",
      "neighbourhood_quality": "One of: below_average, average, above_average, premium",
      "homogeneity": "One of: uniform, mixed, transitional"
    }
  },
  "narrative": {
    "surrounding_land_use": "Description of what surrounds the property — parks, schools, commercial, other residential, vacant land, waterways etc.",
    "road_proximity": "Describe the road network visible — is the property on a quiet street, cul-de-sac, or near a busy arterial/highway? Note any noise or traffic risk.",
    "green_cover": "Describe the tree canopy and vegetation — mature trees, landscaped gardens, sparse, heavily treed etc.",
    "lot_assessment": "Assess the lot — shape (regular/irregular), approximate usable yard space, setbacks from boundaries, any easements or retaining walls visible.",
    "neighbour_density": "How close are neighbouring structures? Is there overlooking risk? Are lots tightly packed or generous spacing?",
    "pool_and_outdoor": "Identify any pools (subject property and neighbours), outdoor entertaining areas, sheds, or outbuildings visible.",
    "flood_drainage_risk": "Note any waterways, retention basins, low-lying areas, or drainage infrastructure visible that might indicate flood risk.",
    "construction_activity": "Is there any visible construction, cleared land, or new development nearby?",
    "parking_access": "Describe driveway configuration, street parking availability, and vehicle access quality.",
    "buyer_highlights": ["List of 3-5 key positive or negative observations a buyer should know about"],
    "overall_setting": "One-sentence summary of the property's setting and character from this aerial perspective."
  }
}
```

RULES:
- **categories**: Use ONLY the allowed values listed above. If you cannot determine a value from the image, use the most conservative/neutral option (e.g. "none", "standard", "average", "unknown").
- **backs_onto**: This is an ARRAY — a property can back onto multiple things (e.g. ["park", "quiet_street"]).
- **pool_visible** and **flight_path**: These are booleans (true/false).
- **narrative**: Write freely and in detail. Describe everything you observe. This is your unrestricted analysis.
- Only describe what you can actually see in the satellite image. If something is unclear or not visible, say so. Do not fabricate details."""

USER_PROMPT = """Analyse this satellite image of a property at: {address}

The property is in the suburb of {suburb}, Gold Coast, Queensland, Australia.

IMPORTANT: The subject property is marked with a RED PIN/MARKER on the image. Only analyse the specific lot where the RED PIN sits. When assessing "backs_onto", look at what is DIRECTLY behind the rear boundary of the pinned lot — not what is nearby but separated by other lots. A park 2-3 lots away is NOT "backs_onto: park".

Provide your buyer-perspective analysis as a JSON object."""


# ---------------------------------------------------------------------------
# Stats
# ---------------------------------------------------------------------------

@dataclass
class AnalysisStats:
    processed: int = 0
    successes: int = 0
    errors: int = 0
    skipped_no_coords: int = 0
    skipped_maps_error: int = 0


# ---------------------------------------------------------------------------
# Core functions
# ---------------------------------------------------------------------------

def _geocode_address(address: str) -> Optional[tuple]:
    """Geocode a street address to (lat, lng) using Google Geocoding API.
    Returns rooftop-level coordinates or None.
    """
    try:
        resp = requests.get("https://maps.googleapis.com/maps/api/geocode/json", params={
            "address": address,
            "key": GOOGLE_MAPS_API_KEY,
        }, timeout=10)
        data = resp.json()
        if data.get("results"):
            loc = data["results"][0]["geometry"]["location"]
            return (loc["lat"], loc["lng"])
    except Exception:
        pass
    return None


def fetch_satellite_image(
    lat: Optional[float] = None,
    lng: Optional[float] = None,
    address: Optional[str] = None,
) -> Optional[bytes]:
    """Fetch satellite image from Google Maps Static API with a red pin marker.

    Geocodes the address for rooftop accuracy, then fetches a satellite image
    with a red marker at the property location so vision models can identify
    the exact lot.
    """
    url = "https://maps.googleapis.com/maps/api/staticmap"

    # Prefer geocoded address for rooftop accuracy
    pin_lat, pin_lng = lat, lng
    if address:
        geocoded = _geocode_address(address)
        if geocoded:
            pin_lat, pin_lng = geocoded

    if pin_lat and pin_lng:
        center = f"{pin_lat},{pin_lng}"
    elif address:
        center = address
    else:
        return None

    params = {
        "center": center,
        "zoom": SATELLITE_ZOOM,
        "size": SATELLITE_SIZE,
        "maptype": SATELLITE_MAPTYPE,
        "scale": SATELLITE_SCALE,
        "key": GOOGLE_MAPS_API_KEY,
    }

    # Add red pin marker at property location
    if pin_lat and pin_lng:
        params["markers"] = f"color:red|size:small|{pin_lat},{pin_lng}"

    try:
        resp = requests.get(url, params=params, timeout=15)
        if resp.status_code == 200 and resp.headers.get("content-type", "").startswith("image/"):
            return resp.content
        else:
            print(f"    ✗ Maps API returned status {resp.status_code}: {resp.text[:200]}")
            return None
    except Exception as exc:
        print(f"    ✗ Maps API request failed: {exc}")
        return None


def upload_satellite_to_blob(
    _unused,
    image_bytes: bytes,
    suburb: str,
    property_id: str,
    db_label: str = "for_sale",
) -> Optional[str]:
    """Upload satellite PNG via shared blob_storage. Returns public URL or None."""
    blob_name = f"{db_label}/{suburb}/{property_id}/satellite/aerial_z{SATELLITE_ZOOM}.png"
    return blob_storage.upload(
        BLOB_CONTAINER, blob_name, image_bytes,
        content_type="image/png",
        cache_control="public, max-age=31536000",
    )


def analyse_satellite_image(image_bytes: bytes, address: str, suburb: str) -> Optional[Dict[str, Any]]:
    """Send satellite image to GPT-5.4 for buyer-perspective analysis."""
    client = OpenAI(api_key=OPENAI_API_KEY)

    b64_image = base64.b64encode(image_bytes).decode("utf-8")

    try:
        response = client.chat.completions.create(
            model=GPT_MODEL,
            messages=[
                {"role": "system", "content": SYSTEM_PROMPT},
                {
                    "role": "user",
                    "content": [
                        {
                            "type": "text",
                            "text": USER_PROMPT.format(address=address, suburb=suburb.replace("_", " ").title()),
                        },
                        {
                            "type": "image_url",
                            "image_url": {
                                "url": f"data:image/png;base64,{b64_image}",
                                "detail": "high",
                            },
                        },
                    ],
                },
            ],
            max_completion_tokens=2500,
            temperature=0.2,
            response_format={"type": "json_object"},
        )

        content = response.choices[0].message.content
        if content:
            import json
            return json.loads(content)
        return None

    except Exception as exc:
        print(f"  ✗ GPT analysis failed: {exc}")
        return None


# ---------------------------------------------------------------------------
# MongoDB repository
# ---------------------------------------------------------------------------

class SatelliteAnalysisRepository:
    """Thin wrapper around MongoDB with RU-aware retries."""

    def __init__(self, query: Dict[str, Any]) -> None:
        self.client = get_client()
        self.db = get_db(DATABASE_NAME)
        self.query = query
        self._collections = set(
            cosmos_retry(lambda: self.db.list_collection_names(), "list_collections", log=print)
        )
        self.suburbs = [s for s in TARGET_SUBURBS if s in self._collections]

    def fetch_candidates(self, limit: int = 0) -> List[Dict[str, Any]]:
        candidates: List[Dict[str, Any]] = []
        remaining = limit if limit > 0 else float("inf")
        for suburb in self.suburbs:
            if remaining <= 0:
                break
            collection = self.db[suburb]
            q = self.query
            batch = min(int(remaining), 5000) if limit > 0 else 0

            def _load(coll=collection, query=q, lim=batch):
                cursor = coll.find(query)
                if lim > 0:
                    cursor = cursor.limit(lim)
                return list(cursor)

            docs = cosmos_retry(_load, f"{suburb}.fetch_candidates", log=print)
            for doc in docs:
                doc["_collection"] = suburb
                candidates.append(doc)
            remaining -= len(docs)
        return candidates

    def count_needing_analysis(self) -> Dict[str, int]:
        stats: Dict[str, int] = {}
        for suburb in self.suburbs:
            collection = self.db[suburb]
            q = self.query
            count = cosmos_retry(
                lambda coll=collection, query=q: coll.count_documents(query),
                f"{suburb}.count_candidates",
                log=print,
            )
            stats[suburb] = count
        return stats

    def save_analysis(
        self, document_id, suburb: str, analysis: Dict[str, Any], processing_time: float
    ):
        collection = self.db[suburb]
        cosmos_retry(
            lambda coll=collection: coll.update_one(
                {"_id": document_id},
                {
                    "$set": {
                        "satellite_analysis": {
                            **analysis,
                            "processed_at": datetime.now(timezone.utc),
                            "processing_duration_seconds": round(processing_time, 2),
                            "zoom_level": SATELLITE_ZOOM,
                            "image_size": SATELLITE_SIZE,
                            "model": GPT_MODEL,
                        }
                    }
                },
            ),
            f"{suburb}.save_satellite_analysis",
            log=print,
        )
        sleep_with_jitter()

    def close(self) -> None:
        self.client.close()


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def parse_args():
    import argparse
    parser = argparse.ArgumentParser(description="Step 117 — Satellite Image Analysis")
    parser.add_argument(
        "--status",
        choices=["for_sale", "sold", "remaining", "all"],
        default="for_sale",
        help="Filter properties by listing_status (default: for_sale)",
    )
    parser.add_argument(
        "--no-fail",
        action="store_true",
        help="Exit 0 even on errors (for pipeline resilience)",
    )
    parser.add_argument(
        "--batch-size",
        type=int,
        default=0,
        help="Limit number of properties to process (0 = unlimited)",
    )
    parser.add_argument(
        "--skip-count",
        action="store_true",
        help="Skip the expensive count_documents query (saves RUs on large collections)",
    )
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    status_filter = args.status

    STATUS_LABELS = {
        "for_sale": "Currently Listed",
        "sold": "Recently Sold",
        "remaining": "Remaining (cadastral/withdrawn/other)",
        "all": "All Properties",
    }

    monitor = MonitorClient(
        system="orchestrator",
        pipeline="orchestrator_daily",
        process_id="117",
        process_name=f"Satellite Analysis ({STATUS_LABELS[status_filter]})",
    )
    monitor.start()

    query = build_candidate_query(status_filter)
    repo = SatelliteAnalysisRepository(query)
    stats = AnalysisStats()

    # Blob path prefix based on status
    blob_label = {"for_sale": "for_sale", "sold": "sold", "remaining": "cadastral", "all": "all"}[status_filter]

    try:
        print("=" * 80)
        print(f"SATELLITE IMAGE ANALYSIS — {STATUS_LABELS[status_filter]}")
        print("=" * 80)
        print(f"Started: {time.strftime('%Y-%m-%d %H:%M:%S')}")
        print(f"Filter: --status {status_filter}")
        print(f"Model: {GPT_MODEL}")
        print(f"Zoom: {SATELLITE_ZOOM}, Size: {SATELLITE_SIZE}, Scale: {SATELLITE_SCALE}\n")

        if not GOOGLE_MAPS_API_KEY:
            raise RuntimeError("GOOGLE_MAPS_STATIC_API_KEY not set in environment")
        if not OPENAI_API_KEY:
            raise RuntimeError("OPENAI_API_KEY not set in environment")

        blob_service = object()  # legacy positional; shared.blob_storage handles backend selection
        print(f"Blob backend: {os.getenv('BLOB_BACKEND', 'local')} (container '{BLOB_CONTAINER}')")

        if not repo.suburbs:
            raise EmptyWorkSetError("No target suburb collections available.")

        if not args.skip_count:
            backlog = repo.count_needing_analysis()
            total_needing = sum(backlog.values())
            print("Needing satellite analysis per suburb:")
            for suburb, count in backlog.items():
                print(f"  - {suburb}: {count}")
            print(f"  Total: {total_needing}\n")

            if total_needing == 0:
                print("✓ All properties already have satellite analysis. Nothing to do.")
                monitor.log_metric("properties_processed", 0)
                monitor.finish(status="success")
                return
        else:
            print("Skipping count query (--skip-count)\n")

        candidates = repo.fetch_candidates(limit=args.batch_size)
        if not candidates:
            raise EmptyWorkSetError("No properties need satellite analysis.")

        print(f"Loaded {len(candidates)} candidate properties\n")

        for idx, prop in enumerate(candidates, 1):
            stats.processed += 1
            address = prop.get("address", prop.get("street_address", ""))
            suburb = prop["_collection"]
            geo = prop.get("geocoded_coordinates") or {}
            lat = geo.get("latitude")
            lng = geo.get("longitude")

            if not lat or not lng:
                if not address:
                    stats.skipped_no_coords += 1
                    print(f"  [{idx}/{len(candidates)}] ⊘ No coords or address, skipping")
                    continue
                print(f"  [{idx}/{len(candidates)}] {address} (using address, no coords)")
            else:
                print(f"  [{idx}/{len(candidates)}] {address} ({lat:.6f}, {lng:.6f})")

            start = time.time()

            # 1. Fetch satellite image (coords preferred, address fallback)
            image_bytes = fetch_satellite_image(lat=lat, lng=lng, address=address)
            if not image_bytes:
                stats.skipped_maps_error += 1
                print(f"    ✗ Could not fetch satellite image")
                continue
            time.sleep(MAPS_API_DELAY)

            # 2. Upload satellite image to blob storage
            blob_url = None
            if blob_service:
                blob_url = upload_satellite_to_blob(
                    blob_service, image_bytes, suburb, str(prop["_id"]),
                    db_label=blob_label,
                )
                if blob_url:
                    print(f"    ☁ Saved to blob")

            # 3. Send to GPT-5.4 for analysis
            analysis = analyse_satellite_image(image_bytes, address, suburb)
            if not analysis:
                stats.errors += 1
                print(f"    ✗ GPT analysis returned nothing")
                continue
            time.sleep(GPT_DELAY)

            # 4. Attach blob URL to analysis and save to MongoDB
            if blob_url:
                analysis["satellite_image_url"] = blob_url
            duration = time.time() - start
            repo.save_analysis(prop["_id"], suburb, analysis, duration)
            stats.successes += 1
            # Summary line
            narrative = analysis.get("narrative", {})
            categories = analysis.get("categories", {})
            setting = narrative.get("overall_setting", analysis.get("overall_setting", ""))
            backs = categories.get("adjacency", {}).get("backs_onto", [])
            detractants = [k for k, v in categories.get("detractants", {}).items()
                          if v not in (False, "none", None)]
            premiums = [k for k, v in categories.get("amenity_premiums", {}).items()
                       if v not in (False, "none", None)]
            print(f"    ✓ Done in {duration:.1f}s")
            print(f"      Backs onto: {', '.join(backs) if backs else 'residential_only'}")
            if detractants:
                print(f"      Detractants: {', '.join(detractants)}")
            if premiums:
                print(f"      Premiums: {', '.join(premiums)}")
            print(f"      Setting: {str(setting)[:80]}")

            if idx % 10 == 0:
                print(
                    f"\n  [Progress] {idx}/{len(candidates)} "
                    f"(✓ {stats.successes} | ✗ {stats.errors} | ⊘ {stats.skipped_no_coords + stats.skipped_maps_error})\n"
                )

        # Final stats
        print("\n" + "=" * 80)
        print("SATELLITE ANALYSIS COMPLETE")
        print(f"  Processed:          {stats.processed}")
        print(f"  Successful:         {stats.successes}")
        print(f"  GPT errors:         {stats.errors}")
        print(f"  Skipped (no coords):{stats.skipped_no_coords}")
        print(f"  Skipped (maps err): {stats.skipped_maps_error}")
        print("=" * 80)

        monitor.log_metric("properties_processed", stats.processed)
        monitor.log_metric("properties_succeeded", stats.successes)
        monitor.log_metric("errors", stats.errors)
        monitor.log_metric("skipped_no_coords", stats.skipped_no_coords)
        monitor.log_metric("skipped_maps_error", stats.skipped_maps_error)

        error_ratio = stats.errors / stats.processed if stats.processed else 0.0
        if stats.processed > 0 and error_ratio > 0.5:
            raise RuntimeError(
                f"Error ratio {error_ratio:.2%} exceeds 50% threshold; marking failure."
            )

        monitor.finish(status="success")

    except EmptyWorkSetError as exc:
        monitor.log_error(str(exc))
        monitor.finish(status="failed")
        if not args.no_fail:
            raise
    except Exception as exc:
        monitor.log_error(f"Unhandled error: {exc}")
        monitor.finish(status="failed")
        if not args.no_fail:
            raise
    finally:
        repo.close()


if __name__ == "__main__":
    main()
