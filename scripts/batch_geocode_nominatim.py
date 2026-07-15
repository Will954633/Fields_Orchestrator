#!/usr/bin/env python3
"""
Batch Geocode — Nominatim

Geocodes all properties in target suburb collections that don't yet have
geocoded_coordinates. Uses the free Nominatim API with a 1.1s delay between
requests to respect rate limits.

Usage:
    python3 scripts/batch_geocode_nominatim.py
    python3 scripts/batch_geocode_nominatim.py --batch-size 500
    python3 scripts/batch_geocode_nominatim.py --suburbs robina,varsity_lakes
"""

from __future__ import annotations

import argparse
import os
import sys
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional

import requests
from pymongo import MongoClient

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT))

from shared.ru_guard import cosmos_retry, sleep_with_jitter  # type: ignore

# ---------------------------------------------------------------------------
# Config
# ---------------------------------------------------------------------------

TARGET_SUBURBS = ["robina", "varsity_lakes", "burleigh_waters"]
DATABASE_NAME = "Gold_Coast"
NOMINATIM_URL = "https://nominatim.openstreetmap.org/search"
NOMINATIM_DELAY = 1.1  # seconds between requests (respect rate limit)
USER_AGENT = "FieldsEstate/1.0 (will@fieldsestate.com.au)"

CANDIDATE_QUERY = {
    "$and": [
        {"address": {"$exists": True, "$ne": ""}},
        {
            "$or": [
                {"geocoded_coordinates": {"$exists": False}},
                {"geocoded_coordinates": None},
            ]
        },
    ]
}


def geocode_address(address: str) -> Optional[Dict[str, Any]]:
    """Geocode an address via Nominatim. Returns {latitude, longitude, display_name} or None."""
    try:
        resp = requests.get(
            NOMINATIM_URL,
            params={
                "q": address,
                "format": "json",
                "limit": 1,
                "countrycodes": "au",
            },
            headers={"User-Agent": USER_AGENT},
            timeout=10,
        )
        if resp.status_code == 200 and resp.json():
            result = resp.json()[0]
            return {
                "latitude": float(result["lat"]),
                "longitude": float(result["lon"]),
                "display_name": result.get("display_name", ""),
                "source": "nominatim",
                "geocoded_at": datetime.now(timezone.utc),
            }
        return None
    except Exception as exc:
        print(f"    ✗ Nominatim error: {exc}")
        return None


def main():
    parser = argparse.ArgumentParser(description="Batch geocode properties via Nominatim")
    parser.add_argument("--batch-size", type=int, default=0, help="Limit (0=unlimited)")
    parser.add_argument("--suburbs", type=str, default="", help="Comma-separated suburb list")
    parser.add_argument("--no-fail", action="store_true")
    args = parser.parse_args()

    suburbs = [s.strip().lower().replace(" ", "_") for s in args.suburbs.split(",") if s.strip()] if args.suburbs else TARGET_SUBURBS

    uri = os.getenv("COSMOS_CONNECTION_STRING") or os.getenv("MONGODB_URI") or "mongodb://localhost:27017/"
    client = MongoClient(uri, retryWrites=False, **({"tls": True, "tlsAllowInvalidCertificates": True} if "cosmos.azure.com" in uri else {}))
    db = client[DATABASE_NAME]

    collections = set(cosmos_retry(lambda: db.list_collection_names(), "list_collections", log=print))
    suburbs = [s for s in suburbs if s in collections]

    print("=" * 80)
    print("BATCH GEOCODE — Nominatim")
    print("=" * 80)
    print(f"Started: {time.strftime('%Y-%m-%d %H:%M:%S')}")
    print(f"Suburbs: {', '.join(suburbs)}")
    print(f"Rate: 1 request per {NOMINATIM_DELAY}s\n")

    total_processed = 0
    total_success = 0
    total_failed = 0
    limit_remaining = args.batch_size if args.batch_size > 0 else float("inf")

    for suburb in suburbs:
        if limit_remaining <= 0:
            break

        coll = db[suburb]
        batch_limit = min(int(limit_remaining), 5000) if args.batch_size > 0 else 0

        def _count(c=coll):
            return c.count_documents(CANDIDATE_QUERY)
        count = cosmos_retry(_count, f"{suburb}.count", log=print)
        print(f"\n{suburb}: {count} properties need geocoding")

        if count == 0:
            continue

        def _fetch(c=coll, lim=batch_limit):
            cursor = c.find(CANDIDATE_QUERY, {"address": 1, "street_address": 1})
            if lim > 0:
                cursor = cursor.limit(lim)
            return list(cursor)

        docs = cosmos_retry(_fetch, f"{suburb}.fetch", log=print)

        for idx, doc in enumerate(docs, 1):
            if limit_remaining <= 0:
                break

            address = doc.get("address", doc.get("street_address", ""))
            if not address:
                continue

            total_processed += 1
            limit_remaining -= 1

            coords = geocode_address(address)
            time.sleep(NOMINATIM_DELAY)

            if coords:
                total_success += 1
                cosmos_retry(
                    lambda c=coll, did=doc["_id"], co=coords: c.update_one(
                        {"_id": did}, {"$set": {"geocoded_coordinates": co}}
                    ),
                    f"{suburb}.update",
                    log=print,
                )
                sleep_with_jitter()
                if idx % 50 == 0 or idx == 1:
                    print(f"  [{idx}/{len(docs)}] ✓ {address} → ({coords['latitude']:.6f}, {coords['longitude']:.6f})")
            else:
                total_failed += 1
                if idx % 50 == 0 or idx == 1:
                    print(f"  [{idx}/{len(docs)}] ✗ {address} — not found")

            if idx % 100 == 0:
                print(f"  [Progress] {idx}/{len(docs)} — ✓ {total_success} ✗ {total_failed}")

    print("\n" + "=" * 80)
    print("GEOCODING COMPLETE")
    print(f"  Processed: {total_processed}")
    print(f"  Success:   {total_success}")
    print(f"  Failed:    {total_failed}")
    eta_remaining = (sum(
        cosmos_retry(lambda c=db[s]: c.count_documents(CANDIDATE_QUERY), f"{s}.final_count", log=print)
        for s in suburbs
    )) * NOMINATIM_DELAY
    if eta_remaining > 0:
        print(f"  Remaining: ~{eta_remaining / 3600:.1f} hours at current rate")
    print("=" * 80)

    client.close()


if __name__ == "__main__":
    main()
