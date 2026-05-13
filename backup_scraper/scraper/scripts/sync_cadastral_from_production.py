#!/usr/bin/env python3
"""
Sync cadastral baseline records from production Cosmos DB to local Mongo.

Production has slightly more recent cadastral coverage than this VM's local
Mongo (Nov 2025 snapshot). Pulls cadastral-only fields (no listings, no
enrichments) so the backup scraper has the same address universe to work
against, while remaining genuinely independent of Domain.com.au.

Cadastral fields synced (everything *not* derived from Domain scraping):
    _id, ADDRESS_PID, complete_address, complete_address_norm,
    STREET_NO_1, STREET_NO_2, STREET_NAME, STREET_TYPE, STREET_SUFFIX,
    UNIT_NUMBER, UNIT_SUFFIX, UNIT_TYPE,
    LATITUDE, LONGITUDE, POSTCODE, LOCALITY, LOCAL_AUTHORITY, LGA_CODE,
    LOT, PLAN, LOTPLAN_STATUS, ADDRESS_STATUS, ADDRESS_STANDARD,
    PROPERTY_NAME, DATUM, GEOCODE_TYPE,
    lot_size_sqm, lot_size_calc_sqm, lot_size_sqm_source,
    cadastral_accuracy, cadastral_enriched_at,
    is_strata_title, parcel_state, property_tenure, property_tenure_desc,
    qscf_feature_name, postcode_distance_km, postcode_enriched_at

NOT synced (independent-of-Domain principle):
    scraped_data, valuation_data, ai_analysis, listing_status, price,
    bedrooms/bathrooms/etc, image_history, anything from production
    scraper that originates from Domain.

Match key: complete_address_norm. New addresses are inserted with
cadastral_match=true. Existing backup records get cadastral fields updated
in place (so any backup_scraper.* listing snapshot is preserved).

Usage:
    python3 sync_cadastral_from_production.py [--suburb robina] [--dry-run]

Run on the production VM (has COSMOS_CONNECTION_STRING). Outputs an
upload bundle to /tmp/cadastral_sync_{suburb}.json which can be applied
on the backup VM with --apply.
"""

import argparse
import json
import os
import re
import sys
from datetime import datetime, timezone
from pathlib import Path

from pymongo import MongoClient, UpdateOne

UTC = timezone.utc

# Cadastral-only field list — explicitly exclude anything Domain-derived.
CADASTRAL_FIELDS = {
    "ADDRESS_PID",
    "complete_address",
    "STREET_NO_1",
    "STREET_NO_1_SUFFIX",
    "STREET_NO_2",
    "STREET_NO_2_SUFFIX",
    "STREET_NAME",
    "STREET_TYPE",
    "STREET_SUFFIX",
    "UNIT_NUMBER",
    "UNIT_SUFFIX",
    "UNIT_TYPE",
    "LATITUDE",
    "LONGITUDE",
    "POSTCODE",
    "LOCALITY",
    "LOCAL_AUTHORITY",
    "LGA_CODE",
    "LOT",
    "PLAN",
    "LOTPLAN_STATUS",
    "ADDRESS_STATUS",
    "ADDRESS_STANDARD",
    "PROPERTY_NAME",
    "DATUM",
    "GEOCODE_TYPE",
    "lot_size_sqm",
    "lot_size_calc_sqm",
    "lot_size_sqm_source",
    "cadastral_accuracy",
    "cadastral_enriched_at",
    "is_strata_title",
    "parcel_state",
    "property_tenure",
    "property_tenure_desc",
    "qscf_feature_name",
    "postcode_distance_km",
    "postcode_enriched_at",
    # The display fields too — needed by the property URL tracker
    "address",
    "street_address",
    "postcode",
    "suburb",
    "display_postcode",
    "complete_address_norm",
}


STREET_ABBREV = {
    "AVE": "AVENUE", "AV": "AVENUE", "RD": "ROAD", "DR": "DRIVE", "DRV": "DRIVE",
    "CT": "COURT", "CRT": "COURT", "PL": "PLACE", "CRES": "CRESCENT", "CR": "CRESCENT",
    "CCT": "CIRCUIT", "CIR": "CIRCUIT", "CCKT": "CIRCUIT", "WY": "WAY",
    "BLVD": "BOULEVARD", "TCE": "TERRACE", "TER": "TERRACE", "HWY": "HIGHWAY",
    "PDE": "PARADE", "CL": "CLOSE", "LN": "LANE", "GR": "GROVE",
}


def normalise(addr: str) -> str:
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


def export_from_production(suburb: str, out_path: Path):
    """Run on production VM — exports cadastral-only docs to JSON."""
    sys.path.insert(0, "/home/fields/Fields_Orchestrator")
    from shared.db import get_gold_coast_db  # type: ignore

    prod_db = get_gold_coast_db()
    coll = prod_db[suburb]
    print(f"  Production {suburb}: {coll.count_documents({})} total docs")

    docs = []
    for doc in coll.find({}, {f: 1 for f in CADASTRAL_FIELDS}):
        d = {k: v for k, v in doc.items() if k in CADASTRAL_FIELDS}
        addr = d.get("complete_address", "")
        if not addr:
            continue
        d["complete_address_norm"] = normalise(addr)
        docs.append(d)

    out_path.write_text(json.dumps(docs, default=str))
    print(f"  Wrote {len(docs):,} cadastral docs to {out_path}")
    return len(docs)


def apply_to_backup(suburb: str, in_path: Path, dry_run: bool = False, mongo_uri: str = "mongodb://localhost:27017/"):
    """Run on backup VM — upserts production cadastral docs into local Mongo.

    Fast path: load all existing complete_address_norm → _id mappings once,
    then iterate the production bundle in memory to build bulk upserts.
    """
    client = MongoClient(mongo_uri)
    db = client["Gold_Coast"]
    coll = db[suburb]

    docs = json.loads(in_path.read_text())
    print(f"  Loaded {len(docs):,} production cadastral docs from {in_path}")

    # Single pass to build the address→_id map
    print(f"  Indexing existing local addresses...")
    existing_map = {}
    for d in coll.find({}, {"complete_address_norm": 1, "_id": 1}):
        norm = d.get("complete_address_norm")
        if norm:
            existing_map[norm] = d["_id"]
    print(f"  Local has {len(existing_map):,} indexed addresses")

    inserts = 0
    updates = 0
    bulk = []

    for d in docs:
        addr_norm = d.get("complete_address_norm") or normalise(d.get("complete_address", ""))
        if not addr_norm:
            continue

        d.pop("_id", None)
        d["complete_address_norm"] = addr_norm

        for k in ("cadastral_enriched_at", "postcode_enriched_at"):
            v = d.get(k)
            if isinstance(v, str):
                try:
                    d[k] = datetime.fromisoformat(v.replace("Z", "+00:00"))
                except Exception:
                    d.pop(k, None)

        existing_id = existing_map.get(addr_norm)
        if existing_id is not None:
            # Update only cadastral fields — preserve backup_scraper.* + listing_status
            update_set = {k: v for k, v in d.items() if v is not None}
            for forbidden in ("backup_scraper", "scrape_source", "listing_status", "last_updated"):
                update_set.pop(forbidden, None)
            update_set["cadastral_match"] = True  # promote any prior stubs
            bulk.append(UpdateOne({"_id": existing_id}, {"$set": update_set}))
            updates += 1
        else:
            d["cadastral_match"] = True
            d["cadastral_synced_at"] = datetime.now(UTC)
            bulk.append(UpdateOne(
                {"complete_address_norm": addr_norm},
                {"$setOnInsert": d},
                upsert=True,
            ))
            inserts += 1

        if len(bulk) >= 1000:
            if not dry_run:
                coll.bulk_write(bulk, ordered=False)
            bulk.clear()

    if bulk and not dry_run:
        coll.bulk_write(bulk, ordered=False)

    print(f"  inserts: {inserts:,}, updates: {updates:,}, dry_run: {dry_run}")
    if not dry_run:
        print(f"  backup {suburb} now has: {coll.count_documents({}):,} total, "
              f"{coll.count_documents({'cadastral_match': {'$ne': False}}):,} cadastral, "
              f"{coll.count_documents({'cadastral_match': False}):,} listings-only orphans")


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--suburb", action="append", help="Suburb (repeatable). Default: all 3.")
    parser.add_argument("--export", action="store_true", help="Export from production Cosmos to JSON bundle (run on prod VM).")
    parser.add_argument("--apply", action="store_true", help="Apply JSON bundle to local Mongo (run on backup VM).")
    parser.add_argument("--dry-run", action="store_true", help="--apply only — preview without writes.")
    parser.add_argument("--bundle-dir", default="/tmp", help="Where bundles live.")
    args = parser.parse_args()

    suburbs = args.suburb or ["robina", "varsity_lakes", "burleigh_waters"]
    bundle_dir = Path(args.bundle_dir)
    bundle_dir.mkdir(parents=True, exist_ok=True)

    if args.export:
        for s in suburbs:
            print(f"\n=== EXPORT {s} ===")
            export_from_production(s, bundle_dir / f"cadastral_sync_{s}.json")
    elif args.apply:
        for s in suburbs:
            print(f"\n=== APPLY {s} ===")
            apply_to_backup(s, bundle_dir / f"cadastral_sync_{s}.json", dry_run=args.dry_run)
    else:
        parser.error("Specify --export or --apply")


if __name__ == "__main__":
    main()
