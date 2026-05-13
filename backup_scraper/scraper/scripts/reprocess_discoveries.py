#!/usr/bin/env python3
"""
Re-run the (updated) HybridExtractor against already-scraped raw_data in
`Gold_Coast.new_url_discoveries` and refresh the cadastral snapshot fields.

Use when the extractor has been improved (new fields added, regex fixes)
and you want existing scrapes to benefit without waiting for a full
re-crawl. Idempotent — safe to re-run.

Usage:
    python3 reprocess_discoveries.py [--suburb robina] [--limit 100] [--dry-run]
"""

import argparse
import sys
from datetime import datetime, timezone
from pathlib import Path

from pymongo import MongoClient

UTC = timezone.utc
SCRIPT_DIR = Path(__file__).resolve().parent
sys.path.insert(0, str(SCRIPT_DIR.parent))

from hybrid_extraction_poc import HybridExtractor  # noqa: E402
from url_tracker import URLTracker, SNAPSHOT_FIELDS, _normalise_address  # noqa: E402


def reprocess(suburb: str, limit: int, dry_run: bool):
    client = MongoClient("mongodb://localhost:27017/")
    db = client["Gold_Coast"]
    disc_coll = db["new_url_discoveries"]
    suburb_coll = db[suburb.lower()]

    hybrid = HybridExtractor(use_ai_fallback=False)

    # Walk discoveries (latest first per address) — only the most recent per
    # address is worth reprocessing, so dedupe in-flight.
    cursor = disc_coll.find(
        {"suburb": suburb, "raw_data": {"$exists": True, "$ne": {}}},
        no_cursor_timeout=True,
    ).sort("discovered_at", -1)

    seen_addrs = set()
    processed = 0
    snapshot_updates = 0
    fields_added = {f: 0 for f in SNAPSHOT_FIELDS}

    for disc in cursor:
        addr = disc.get("complete_address", "")
        addr_norm = _normalise_address(addr)
        if not addr_norm or addr_norm in seen_addrs:
            continue
        seen_addrs.add(addr_norm)

        raw_data = disc.get("raw_data")
        if not raw_data or not isinstance(raw_data, dict):
            continue

        try:
            extracted = hybrid.extract_property_data(raw_data)
            images = hybrid.filter_images(raw_data)
            floor_plans = hybrid.filter_floor_plans(raw_data)
            new_doc = hybrid.create_mongodb_document(extracted, raw_data, images, floor_plans)
        except Exception as e:
            print(f"  ⚠️ extraction failed for {addr[:50]}: {e}")
            continue

        processed += 1
        if processed % 50 == 0:
            print(f"  ... reprocessed {processed} addresses")
        if limit and processed >= limit:
            break

        if dry_run:
            continue

        # Update discovery doc's extracted_data
        disc_coll.update_one(
            {"_id": disc["_id"]},
            {
                "$set": {
                    "extracted_data": new_doc,
                    "reprocessed_at": datetime.now(UTC),
                    "extractor_version": "phase3_2026_05_13",
                }
            },
        )

        # Update suburb snapshot — same logic as URLTracker._upsert_property_snapshot
        snapshot = {
            f"backup_scraper.{k}": new_doc.get(k)
            for k in SNAPSHOT_FIELDS
            if new_doc.get(k) not in (None, [], "")
        }
        for k in SNAPSHOT_FIELDS:
            if new_doc.get(k) not in (None, [], ""):
                fields_added[k] += 1
        snapshot.update(
            {
                "backup_scraper.listing_url": disc.get("new_url", ""),
                "backup_scraper.agency": disc.get("agency_keyword", "unknown"),
                "backup_scraper.last_scraped_at": disc.get("discovered_at"),
                "backup_scraper.address_input": addr,
            }
        )
        status = new_doc.get("listing_status")
        if status:
            snapshot["listing_status"] = status
            snapshot["scrape_source"] = "backup_scraper"

        # Cadastral fallback for lot_size / lat / lng
        cad = suburb_coll.find_one(
            {"complete_address_norm": addr_norm, "cadastral_match": {"$ne": False}},
            {"lot_size_sqm": 1, "LATITUDE": 1, "LONGITUDE": 1, "_id": 0},
        )
        if cad:
            if not new_doc.get("land_size_sqm") and cad.get("lot_size_sqm"):
                snapshot["backup_scraper.land_size_sqm_from_cadastral"] = cad["lot_size_sqm"]
            if cad.get("LATITUDE") is not None:
                snapshot["backup_scraper.latitude"] = cad["LATITUDE"]
            if cad.get("LONGITUDE") is not None:
                snapshot["backup_scraper.longitude"] = cad["LONGITUDE"]

        # Match cadastral by norm, fall back to listings-only stub create
        existing = suburb_coll.find_one(
            {"complete_address_norm": addr_norm}, {"_id": 1}
        )
        if existing:
            suburb_coll.update_one({"_id": existing["_id"]}, {"$set": snapshot})
            snapshot_updates += 1

    cursor.close()

    print(f"\n  reprocessed: {processed} addresses")
    print(f"  snapshot updates: {snapshot_updates}")
    print(f"  fields populated (cumulative across all snapshots):")
    for f, n in sorted(fields_added.items(), key=lambda x: -x[1]):
        if n > 0:
            print(f"    {f:25} {n}")


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--suburb", action="append", help="Suburb (repeatable). Default: all 3.")
    parser.add_argument("--limit", type=int, default=0, help="Limit per suburb (0 = no limit).")
    parser.add_argument("--dry-run", action="store_true", help="Run extraction but don't write.")
    args = parser.parse_args()

    suburbs = args.suburb or ["robina", "varsity_lakes", "burleigh_waters"]
    for s in suburbs:
        print(f"\n=== {s} ===")
        reprocess(s, args.limit, args.dry_run)
    print("\n=== Done ===")


if __name__ == "__main__":
    main()
