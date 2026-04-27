#!/usr/bin/env python3
"""
Bulk Satellite Analysis Runner

Streams through ALL properties in target suburb collections using a simple
cursor (no $exists query — Cosmos can't index missing fields efficiently).
Skips properties that already have satellite_analysis in Python.

Usage:
    python3 scripts/run_satellite_bulk.py --batch-size 200
    python3 scripts/run_satellite_bulk.py --suburb robina --batch-size 500
"""

from __future__ import annotations

import argparse
import base64
import json
import os
import sys
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, Optional

import requests
from openai import OpenAI
from pymongo import MongoClient

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT))
from shared.ru_guard import cosmos_retry, sleep_with_jitter
from shared import blob_storage  # type: ignore

# ---------------------------------------------------------------------------
# Config — import from step117
# ---------------------------------------------------------------------------

TARGET_SUBURBS = ["robina", "varsity_lakes", "burleigh_waters"]
DATABASE_NAME = "Gold_Coast"
GOOGLE_MAPS_API_KEY = os.getenv("GOOGLE_MAPS_STATIC_API_KEY", os.getenv("GOOGLE_PLACES_API_KEY", ""))
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY", "")
AZURE_STORAGE_CONNECTION_STRING = os.getenv("AZURE_STORAGE_CONNECTION_STRING", "")
BLOB_CONTAINER = "property-images"

SATELLITE_ZOOM = 19
SATELLITE_SIZE = "640x640"
SATELLITE_SCALE = 2
GPT_MODEL = "gpt-5.4"
MAPS_API_DELAY = 0.2
GPT_DELAY = 1.0

# Import the prompts from step117
sys.path.insert(0, str(REPO_ROOT / "scripts"))
from step117_satellite_analysis import SYSTEM_PROMPT, USER_PROMPT


def fetch_satellite_image(address: str, lat=None, lng=None) -> Optional[bytes]:
    center = f"{lat},{lng}" if lat and lng else address
    try:
        resp = requests.get(
            "https://maps.googleapis.com/maps/api/staticmap",
            params={
                "center": center, "zoom": SATELLITE_ZOOM, "size": SATELLITE_SIZE,
                "maptype": "satellite", "scale": SATELLITE_SCALE, "key": GOOGLE_MAPS_API_KEY,
            },
            timeout=15,
        )
        if resp.status_code == 200 and "image/" in resp.headers.get("content-type", ""):
            return resp.content
        print(f"    ✗ Maps {resp.status_code}")
        return None
    except Exception as e:
        print(f"    ✗ Maps error: {e}")
        return None


def analyse_image(image_bytes: bytes, address: str, suburb: str) -> Optional[Dict]:
    client = OpenAI(api_key=OPENAI_API_KEY)
    b64 = base64.b64encode(image_bytes).decode("utf-8")
    try:
        resp = client.chat.completions.create(
            model=GPT_MODEL,
            messages=[
                {"role": "system", "content": SYSTEM_PROMPT},
                {"role": "user", "content": [
                    {"type": "text", "text": USER_PROMPT.format(
                        address=address, suburb=suburb.replace("_", " ").title()
                    )},
                    {"type": "image_url", "image_url": {
                        "url": f"data:image/png;base64,{b64}", "detail": "high"
                    }},
                ]},
            ],
            max_completion_tokens=2500, temperature=0.2,
            response_format={"type": "json_object"},
        )
        content = resp.choices[0].message.content
        return json.loads(content) if content else None
    except Exception as e:
        print(f"    ✗ GPT: {e}")
        return None


def upload_to_blob(_unused, image_bytes: bytes, suburb: str, prop_id: str) -> Optional[str]:
    blob_name = f"all/{suburb}/{prop_id}/satellite/aerial_z{SATELLITE_ZOOM}.png"
    return blob_storage.upload(
        BLOB_CONTAINER, blob_name, image_bytes,
        content_type="image/png", cache_control="public, max-age=31536000",
    )


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--batch-size", type=int, default=200)
    parser.add_argument("--suburb", type=str, default="")
    args = parser.parse_args()

    suburbs = [args.suburb] if args.suburb else TARGET_SUBURBS

    print("Connecting to MongoDB...", flush=True)
    uri = os.getenv("COSMOS_CONNECTION_STRING") or "mongodb://localhost:27017/"
    client = MongoClient(uri, retryWrites=False, **({"tls": True, "tlsAllowInvalidCertificates": True} if "cosmos.azure.com" in uri else {}))
    db = client[DATABASE_NAME]
    print("Connected.", flush=True)

    blob_service = object()  # legacy positional; shared.blob_storage handles backend selection
    print(f"Blob backend: {os.getenv('BLOB_BACKEND', 'local')} (container '{BLOB_CONTAINER}')", flush=True)

    print("=" * 80, flush=True)
    print(f"BULK SATELLITE ANALYSIS — streaming cursor, batch {args.batch_size}")
    print(f"Suburbs: {', '.join(suburbs)}")
    print(f"Started: {time.strftime('%Y-%m-%d %H:%M:%S')}")
    print("=" * 80)

    total_processed = 0
    total_success = 0
    total_skipped = 0
    total_errors = 0
    limit = args.batch_size

    for suburb in suburbs:
        if total_success >= limit:
            break

        coll = db[suburb]
        print(f"\n--- {suburb} ---", flush=True)

        # Paginate through docs in small batches of 20 using _id cursor
        # This avoids Cosmos RU exhaustion from scanning large collections
        PAGE_SIZE = 20
        last_id = None

        while total_success < limit:
            # Build paginated query — include docs with address OR complete_address OR LATITUDE
            query: Dict[str, Any] = {
                "$or": [
                    {"address": {"$exists": True, "$ne": ""}},
                    {"complete_address": {"$exists": True, "$ne": ""}},
                    {"LATITUDE": {"$exists": True}},
                ]
            }
            if last_id is not None:
                query = {"$and": [{"_id": {"$gt": last_id}}, query]}

            page = cosmos_retry(
                lambda c=coll, q=query: list(
                    c.find(q, {
                        "address": 1, "street_address": 1, "complete_address": 1,
                        "geocoded_coordinates": 1, "satellite_analysis": 1,
                        "LATITUDE": 1, "LONGITUDE": 1,
                        "STREET_NO_1": 1, "STREET_NAME": 1, "STREET_TYPE": 1,
                        "UNIT_NUMBER": 1, "LOCALITY": 1, "POSTCODE": 1,
                    })
                    .sort("_id", 1)
                    .limit(PAGE_SIZE)
                ),
                f"{suburb}.page",
                log=print,
            )

            if not page:
                print(f"  No more documents in {suburb}")
                break

            last_id = page[-1]["_id"]
            time.sleep(0.5)  # RU cooldown between pages

            for doc in page:
                if total_success >= limit:
                    break

                # Skip if already analysed
                if doc.get("satellite_analysis"):
                    total_skipped += 1
                    continue

                # Extract address — try multiple field patterns
                address = (
                    doc.get("address")
                    or doc.get("complete_address")
                    or doc.get("street_address")
                    or ""
                )
                # Build address from cadastral fields if needed
                if not address and doc.get("STREET_NAME"):
                    parts = []
                    if doc.get("UNIT_NUMBER"):
                        parts.append(f"{doc['UNIT_NUMBER']}/")
                    if doc.get("STREET_NO_1"):
                        parts.append(str(doc["STREET_NO_1"]))
                    parts.append(doc.get("STREET_NAME", ""))
                    if doc.get("STREET_TYPE"):
                        parts.append(doc["STREET_TYPE"])
                    parts.append(doc.get("LOCALITY", ""))
                    parts.append(f"QLD {doc.get('POSTCODE', '')}")
                    address = " ".join(p for p in parts if p).strip()

                if not address:
                    continue

                total_processed += 1

                # Extract coordinates — try geocoded_coordinates then cadastral LATITUDE/LONGITUDE
                geo = doc.get("geocoded_coordinates") or {}
                lat = geo.get("latitude") or doc.get("LATITUDE")
                lng = geo.get("longitude") or doc.get("LONGITUDE")
                if lat:
                    lat = float(lat)
                if lng:
                    lng = float(lng)

                if lat and lng:
                    print(f"  [{total_success+1}/{limit}] {address} ({lat:.5f}, {lng:.5f})")
                else:
                    print(f"  [{total_success+1}/{limit}] {address} (address lookup)")

                start = time.time()

                # 1. Fetch satellite
                img = fetch_satellite_image(address, lat, lng)
                if not img:
                    total_errors += 1
                    continue
                time.sleep(MAPS_API_DELAY)

                # 2. Upload to blob
                blob_url = upload_to_blob(blob_service, img, suburb, str(doc["_id"]))
                if blob_url:
                    print(f"    ☁ Blob saved")

                # 3. GPT analysis
                analysis = analyse_image(img, address, suburb)
                if not analysis:
                    total_errors += 1
                    continue
                time.sleep(GPT_DELAY)

                # 4. Save to MongoDB
                if blob_url:
                    analysis["satellite_image_url"] = blob_url

                duration = time.time() - start
                cosmos_retry(
                    lambda c=coll, did=doc["_id"], a=analysis, d=duration: c.update_one(
                        {"_id": did},
                        {"$set": {"satellite_analysis": {
                            **a,
                            "processed_at": datetime.now(timezone.utc),
                            "processing_duration_seconds": round(d, 2),
                            "zoom_level": SATELLITE_ZOOM, "model": GPT_MODEL,
                        }}}
                    ),
                    f"{suburb}.save",
                    log=print,
                )
                sleep_with_jitter()

                total_success += 1
                cats = analysis.get("categories", {})
                backs = cats.get("adjacency", {}).get("backs_onto", [])
                setting = analysis.get("narrative", {}).get("overall_setting", "")[:70]
                print(f"    ✓ {duration:.0f}s | {', '.join(backs)} | {setting}")

                if total_success % 20 == 0:
                    print(f"\n  === Progress: {total_success}/{limit} done, {total_errors} errors, {total_skipped} skipped ===\n")

    print("\n" + "=" * 80)
    print(f"COMPLETE: {total_success} analysed, {total_errors} errors, {total_skipped} already done")
    print("=" * 80)
    client.close()


if __name__ == "__main__":
    main()
