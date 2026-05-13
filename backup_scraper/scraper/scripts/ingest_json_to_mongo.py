#!/usr/bin/env python3
"""
Backfill local MongoDB from discovered_urls/*.json snapshots.

Walks every JSON file under discovered_urls/{suburb}/, deduplicates by address,
and populates three collections in the local Gold_Coast database:

  property_url_tracking  — every (address, url) ever seen, with first/last_seen
  new_url_discoveries    — the latest meaningful scrape per address (status != None)
  {suburb}                — denormalized current snapshot merged onto cadastral docs

Run after rewriting url_tracker.py and before restarting the service so the new
URLTracker has accurate state. Idempotent — safe to re-run.

Usage:
    python3 ingest_json_to_mongo.py [--suburb robina] [--dry-run]
"""

import argparse
import json
import os
import re
import sys
import time
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path

from pymongo import MongoClient

UTC = timezone.utc

SCRIPT_DIR = Path(__file__).resolve().parent
SCRAPER_DIR = SCRIPT_DIR.parent
DISCOVERED_DIR = SCRAPER_DIR / "discovered_urls"

LOCAL_URI = "mongodb://localhost:27017/"
DB_NAME = "Gold_Coast"

# Status priority — when multiple files exist per address, prefer the
# strongest signal. "for_sale" wins over "unknown" but "sold" wins over "for_sale".
STATUS_PRIORITY = {
    "sold": 5,
    "leased": 4,
    "withdrawn": 3,
    "for_sale": 2,
    "unknown": 1,
    None: 0,
    "": 0,
}

SNAPSHOT_FIELDS = (
    "listing_status",
    "bedrooms",
    "bathrooms",
    "carspaces",
    "property_type",
    "sale_price",
    "sold_date",
    "land_size_sqm",
    "description",
    "features",
    "property_images",
    "listing_url",
    "extraction_method",
    "extraction_confidence",
    "agents_description",
    "og_title",
)


STREET_ABBREV = {
    "AVE": "AVENUE", "AV": "AVENUE", "RD": "ROAD", "DR": "DRIVE", "DRV": "DRIVE",
    "CT": "COURT", "CRT": "COURT", "PL": "PLACE", "CRES": "CRESCENT", "CR": "CRESCENT",
    "CCT": "CIRCUIT", "CIR": "CIRCUIT", "CCKT": "CIRCUIT", "WY": "WAY",
    "BLVD": "BOULEVARD", "TCE": "TERRACE", "TER": "TERRACE", "HWY": "HIGHWAY",
    "PDE": "PARADE", "CL": "CLOSE", "LN": "LANE", "GR": "GROVE",
}


def normalise_address(addr: str) -> str:
    """Mirrors url_tracker._normalise_address — see that for full doc."""
    if not addr:
        return ""
    cleaned = re.sub(r"\s+", " ", addr.replace(",", " ").strip().upper())
    tokens = cleaned.split()
    expanded = [
        STREET_ABBREV.get(tok, tok) if 0 < i < len(tokens) - 3 else tok
        for i, tok in enumerate(tokens)
    ]
    return " ".join(expanded)


def parse_timestamp_from_filename(name: str):
    """Filenames look like 2026-04-24_03-40-13_..._agency.json"""
    m = re.match(r"^(\d{4}-\d{2}-\d{2})_(\d{2}-\d{2}-\d{2})_", name)
    if not m:
        return None
    try:
        return datetime.strptime(f"{m.group(1)} {m.group(2)}", "%Y-%m-%d %H-%M-%S").replace(tzinfo=UTC)
    except ValueError:
        return None


def walk_suburb(suburb_dir: Path):
    """Yield (filepath, parsed_timestamp) sorted oldest → newest."""
    files = []
    for fp in suburb_dir.glob("*.json"):
        ts = parse_timestamp_from_filename(fp.name)
        if ts:
            files.append((fp, ts))
    files.sort(key=lambda x: x[1])
    return files


def load_json_safe(fp: Path):
    try:
        with open(fp, "r") as f:
            return json.load(f)
    except (json.JSONDecodeError, OSError):
        return None


def discovery_address(payload: dict, fallback: str = "") -> str:
    di = payload.get("discovery_info") or {}
    addr = (
        di.get("verified_address")
        if di.get("address_match")
        else di.get("address")
    ) or di.get("address") or fallback
    return addr or ""


def ingest_suburb(db, suburb: str, dry_run: bool = False):
    suburb_dir = DISCOVERED_DIR / suburb
    if not suburb_dir.exists():
        print(f"  ⚠️  {suburb_dir} does not exist — skipping")
        return

    print(f"\n=== Suburb: {suburb} ===")
    files = walk_suburb(suburb_dir)
    print(f"  Files (with valid timestamps): {len(files):,}")
    if not files:
        return

    # Pass 1 — index everything in memory by address.
    # address_norm -> {
    #   "address": original-cased canonical,
    #   "urls": {url: {agency_keyword, title, first_seen, last_seen, check_count}},
    #   "best": (priority, ts, file_payload, ts)   ← best snapshot to commit
    # }
    by_address = {}
    start = time.time()

    for idx, (fp, ts) in enumerate(files, 1):
        if idx % 5000 == 0:
            print(f"  ... scanned {idx:,}/{len(files):,} files ({time.time()-start:.0f}s)")

        payload = load_json_safe(fp)
        if not payload:
            continue

        address = discovery_address(payload)
        if not address:
            continue
        addr_norm = normalise_address(address)
        if not addr_norm:
            continue

        di = payload.get("discovery_info") or {}
        extracted = payload.get("extracted_data") or {}
        url = di.get("new_url") or extracted.get("listing_url") or ""
        agency = di.get("agency_keyword") or "unknown"
        status = payload.get("listing_status") or extracted.get("listing_status")

        # Track URL
        if url and not url.startswith("recheck"):  # synthetic 'unknown' files have empty url
            bucket = by_address.setdefault(
                addr_norm,
                {"address": address, "urls": {}, "best": None, "best_file": None},
            )
            url_entry = bucket["urls"].setdefault(
                url,
                {
                    "url": url,
                    "agency_keyword": agency,
                    "title": di.get("title", ""),
                    "first_seen": ts,
                    "last_seen": ts,
                    "check_count": 0,
                },
            )
            url_entry["last_seen"] = max(url_entry["last_seen"], ts)
            url_entry["check_count"] += 1
            # Address case can drift — prefer the most recent observation
            bucket["address"] = address

        # Track best file for snapshot — highest priority status, latest ts.
        bucket = by_address.setdefault(
            addr_norm,
            {"address": address, "urls": {}, "best": None, "best_file": None},
        )
        priority = STATUS_PRIORITY.get(status, 0)
        candidate = (priority, ts.timestamp())
        if bucket["best"] is None or candidate > bucket["best"]:
            bucket["best"] = candidate
            bucket["best_file"] = (fp, ts, payload)

    elapsed = time.time() - start
    print(f"  Scanned {len(files):,} files in {elapsed:.1f}s")
    print(f"  Unique addresses: {len(by_address):,}")

    if dry_run:
        # Show breakdown
        status_counts = defaultdict(int)
        for bucket in by_address.values():
            if bucket["best_file"]:
                _, _, payload = bucket["best_file"]
                status = payload.get("listing_status") or "NULL"
                status_counts[status] += 1
        print(f"  Status breakdown (latest-strongest per address):")
        for status, n in sorted(status_counts.items(), key=lambda x: -x[1]):
            print(f"    {status}: {n:,}")
        return

    # Pass 2 — write to Mongo.
    tracking_coll = db["property_url_tracking"]
    discoveries_coll = db["new_url_discoveries"]
    suburb_coll = db[suburb.lower()]

    inserted_tracking = 0
    updated_tracking = 0
    inserted_discoveries = 0
    snapshot_matched = 0
    snapshot_inserted = 0
    snapshot_skipped_no_status = 0

    now = datetime.now(UTC)

    for addr_norm, bucket in by_address.items():
        address = bucket["address"]
        url_entries = list(bucket["urls"].values())

        # ── property_url_tracking upsert ───────────────────────────────────────
        existing = tracking_coll.find_one(
            {"complete_address_norm": addr_norm, "suburb": suburb}
        )
        if existing:
            # Merge: keep existing entries, update last_seen/check_count for collisions
            existing_urls = {u["url"]: u for u in existing.get("known_urls", [])}
            for entry in url_entries:
                if entry["url"] in existing_urls:
                    e = existing_urls[entry["url"]]
                    e["last_seen"] = max(e.get("last_seen", entry["last_seen"]), entry["last_seen"])
                    e["check_count"] = max(e.get("check_count", 0), entry["check_count"])
                else:
                    existing_urls[entry["url"]] = entry
            merged = list(existing_urls.values())
            tracking_coll.update_one(
                {"_id": existing["_id"]},
                {
                    "$set": {
                        "known_urls": merged,
                        "total_urls_found": len(merged),
                        "last_checked": max([e["last_seen"] for e in merged] + [now]),
                        "complete_address": address,
                    }
                },
            )
            updated_tracking += 1
        else:
            tracking_coll.insert_one(
                {
                    "complete_address": address,
                    "complete_address_norm": addr_norm,
                    "suburb": suburb,
                    "known_urls": url_entries,
                    "total_urls_found": len(url_entries),
                    "last_checked": max([e["last_seen"] for e in url_entries] + [now]),
                    "check_count": 1,
                }
            )
            inserted_tracking += 1

        # ── new_url_discoveries: insert ONE entry for the latest-strongest file ──
        best_file = bucket["best_file"]
        if best_file:
            fp, ts, payload = best_file
            di = payload.get("discovery_info") or {}
            extracted = payload.get("extracted_data") or {}

            # Skip duplicate insertion if we already backfilled this exact file path
            existing_disc = discoveries_coll.find_one(
                {"json_file_path": str(fp)}, {"_id": 1}
            )
            if not existing_disc:
                discoveries_coll.insert_one(
                    {
                        "complete_address": address,
                        "complete_address_norm": addr_norm,
                        "suburb": suburb,
                        "new_url": di.get("new_url", ""),
                        "agency_keyword": di.get("agency_keyword", "unknown"),
                        "title": di.get("title", ""),
                        "is_recheck": False,
                        "discovered_at": ts,
                        "raw_data": payload.get("raw_data") or {},
                        "extracted_data": extracted,
                        "previous_urls": [],
                        "is_first_url": False,
                        "total_urls_now": len(url_entries),
                        "processed": True,
                        "saved_to_json": True,
                        "json_file_path": str(fp),
                        "ingested_from_backfill": True,
                    }
                )
                inserted_discoveries += 1

            # ── suburb collection snapshot merge ──────────────────────────────
            status = payload.get("listing_status") or extracted.get("listing_status")
            if not status:
                snapshot_skipped_no_status += 1
                continue

            snapshot = {}
            for k in SNAPSHOT_FIELDS:
                v = extracted.get(k)
                if v is not None:
                    snapshot[f"backup_scraper.{k}"] = v
            snapshot.update(
                {
                    "backup_scraper.listing_url": di.get("new_url", ""),
                    "backup_scraper.agency": di.get("agency_keyword", "unknown"),
                    "backup_scraper.last_scraped_at": ts,
                    "backup_scraper.address_input": address,
                    "listing_status": status,
                    "scrape_source": "backup_scraper",
                    "last_updated": ts,
                }
            )

            # Match on complete_address_norm (populated by remediate_cadastral_norm.py)
            matched = suburb_coll.find_one_and_update(
                {"complete_address_norm": addr_norm},
                {"$set": snapshot},
                projection={"_id": 1},
            )
            if matched:
                snapshot_matched += 1
            else:
                suburb_coll.insert_one(
                    {
                        "complete_address": address,
                        "complete_address_norm": addr_norm,
                        "cadastral_match": False,
                        "first_seen_at": ts,
                        **snapshot,
                    }
                )
                snapshot_inserted += 1

    print(f"  property_url_tracking: +{inserted_tracking:,} new, {updated_tracking:,} updated")
    print(f"  new_url_discoveries:   +{inserted_discoveries:,} new entries")
    print(
        f"  {suburb} snapshots:     {snapshot_matched:,} merged onto cadastral, "
        f"{snapshot_inserted:,} inserted standalone, {snapshot_skipped_no_status:,} skipped (no status)"
    )


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--suburb",
        action="append",
        help="Suburb to ingest (can be repeated). Default: all three.",
    )
    parser.add_argument("--dry-run", action="store_true", help="Scan only, no writes.")
    args = parser.parse_args()

    suburbs = args.suburb or ["robina", "varsity_lakes", "burleigh_waters"]

    client = MongoClient(LOCAL_URI)
    db = client[DB_NAME]

    # Ensure indexes (no-op if already present)
    db["property_url_tracking"].create_index(
        [("complete_address_norm", 1), ("suburb", 1)], unique=True
    )
    db["property_url_tracking"].create_index([("last_checked", -1)])
    db["new_url_discoveries"].create_index([("discovered_at", -1)])
    db["new_url_discoveries"].create_index([("complete_address_norm", 1), ("suburb", 1)])
    db["new_url_discoveries"].create_index([("json_file_path", 1)], unique=False)

    for suburb in suburbs:
        ingest_suburb(db, suburb, dry_run=args.dry_run)

    print("\n=== Done ===")


if __name__ == "__main__":
    main()
