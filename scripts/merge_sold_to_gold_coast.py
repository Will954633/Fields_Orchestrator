#!/usr/bin/env python3
"""
merge_sold_to_gold_coast.py
============================
Enriches Gold_Coast property documents with sold data from
Target_Market_Sold_Last_12_Months.

For each record in Target_Market_Sold_Last_12_Months.<suburb>:
  1. Normalise the address to match Gold_Coast.complete_address format
  2. Find the matching document in Gold_Coast.<suburb>
  3. Merge sold fields + set listing_status = "sold"

Matching strategy:
  - Primary: normalised address (uppercase, no commas, stripped unit formatting)
  - Fallback: street number + street name substring match

Usage:
    python3 merge_sold_to_gold_coast.py --dry-run          # Preview what would change
    python3 merge_sold_to_gold_coast.py                    # Run for all suburbs
    python3 merge_sold_to_gold_coast.py --suburb robina    # Single suburb
    python3 merge_sold_to_gold_coast.py --force            # Overwrite existing sold data
"""

import argparse
import re
import sys
import time
from datetime import datetime, timezone

import yaml
from pymongo import MongoClient
from pymongo.errors import OperationFailure

# -- Config -------------------------------------------------------------------

with open("/home/fields/Fields_Orchestrator/config/settings.yaml") as f:
    _cfg = yaml.safe_load(f)

COSMOS_URI = _cfg["mongodb"]["uri"]

DB_TARGET = "Target_Market_Sold_Last_12_Months"
DB_GOLD_COAST = "Gold_Coast"

TARGET_SUBURBS = [
    "robina", "varsity_lakes", "burleigh_waters",
    "mudgeeraba", "merrimac", "carrara",
    "worongary", "reedy_creek",
]

# Fields to copy from Target_Market docs into Gold_Coast docs
SOLD_FIELDS = [
    "sale_price",
    "sale_date",
    "time_on_market_days",
    "property_type",
    "agents_description",
    "agency_name",
    "agent_name",
    "property_images",
    "floor_plans",
    "property_images_original",
    "floor_plans_original",
    "images_uploaded_to_blob",
    "images_blob_uploaded_at",
    "listing_url",
    "description",
    "og_title",
    "extraction_method",
    "extraction_date",
    "first_listed_date",
    "last_updated_date",
    "previous_sale_year",
    "domain_says_text",
    "property_valuation_data",
    "processing_status",
    "floor_plan_analysis",
    "land_size_sqm",
    "comparable_sales_count",
    "comparable_bedrooms",
    "comparable_property_type",
    "comparable_suburb",
    "source",
]


# -- Address normalisation ----------------------------------------------------

def normalise_address(raw: str) -> str:
    """
    Normalise an address string to a canonical form for matching.

    Target_Market format: "1 10 Cornell Court Varsity, Lakes, QLD 4227"
      -> "1/10 CORNELL COURT VARSITY LAKES QLD 4227"

    Gold_Coast format: "11 SOUTH BAY DRIVE VARSITY LAKES QLD 4227"
      -> already uppercase, just strip extra whitespace

    Steps:
      1. Uppercase
      2. Remove commas
      3. Detect unit/lot patterns: "X Y Street" where X is small number -> "X/Y"
      4. Strip extra whitespace
    """
    s = raw.upper().strip()
    s = s.replace(",", " ")
    s = re.sub(r"\s+", " ", s).strip()
    return s


def extract_street_key(addr: str) -> str:
    """
    Extract a simplified street key for fuzzy matching.
    "1/10 CORNELL COURT VARSITY LAKES QLD 4227" -> "10 CORNELL COURT"
    "15 CASUA DRIVE VARSITY LAKES QLD 4227" -> "15 CASUA DRIVE"

    Strips unit prefix, suburb, state, postcode.
    """
    s = addr.upper().strip().replace(",", " ")
    s = re.sub(r"\s+", " ", s).strip()

    # Remove QLD + postcode suffix
    s = re.sub(r"\s+QLD\s+\d{4}$", "", s)
    # Remove suburb name (last 1-2 words that are all caps and not street types)
    # Just keep up to the street type
    return s


def parse_target_address(raw: str) -> dict:
    """
    Parse a Target_Market address like "1 10 Cornell Court Varsity, Lakes, QLD 4227"
    into components.
    """
    s = raw.strip().replace(",", " ")
    s = re.sub(r"\s+", " ", s).strip()

    # Remove QLD + postcode
    m_post = re.search(r"\s+QLD\s+(\d{4})$", s, re.IGNORECASE)
    postcode = m_post.group(1) if m_post else ""
    if m_post:
        s = s[:m_post.start()].strip()

    # The address may have unit prefix: "1 10 Cornell Court Varsity Lakes"
    # or no unit: "73 Azzurra Drive Varsity Lakes"
    # We need to extract street number (possibly with unit) and street name

    return {"cleaned": s.upper(), "postcode": postcode}


def build_gc_address_index(gc_coll) -> dict:
    """
    Build a lookup index from Gold_Coast documents.
    Returns: {normalised_complete_address: doc_id}
    Also builds a secondary index on street number + name for fuzzy matching.
    """
    primary = {}   # normalised complete_address -> _id
    by_street = {} # "NUMBER STREETNAME" -> [_id, ...]

    for doc in gc_coll.find(
        {"complete_address": {"$exists": True}},
        {"complete_address": 1, "STREET_NO_1": 1, "STREET_NAME": 1,
         "STREET_TYPE": 1, "UNIT_NUMBER": 1, "listing_status": 1}
    ):
        ca = doc.get("complete_address", "")
        if not ca:
            continue
        norm = normalise_address(ca)
        primary[norm] = {
            "_id": doc["_id"],
            "listing_status": doc.get("listing_status"),
        }

        # Build street key: "10 CORNELL COURT"
        no = doc.get("STREET_NO_1", "")
        name = doc.get("STREET_NAME", "")
        stype = doc.get("STREET_TYPE", "")
        unit = doc.get("UNIT_NUMBER")
        if no and name:
            key = f"{no} {name} {stype}".strip().upper()
            by_street.setdefault(key, []).append({
                "_id": doc["_id"],
                "unit": unit,
                "listing_status": doc.get("listing_status"),
                "complete_address": ca,
            })

    return primary, by_street


def match_target_to_gc(tm_doc: dict, primary_idx: dict, street_idx: dict):
    """
    Try to match a Target_Market document to a Gold_Coast document.
    Returns (gc_id, match_method) or (None, None).
    """
    addr = tm_doc.get("address", "")
    if not addr:
        return None, None

    # 1. Try direct normalised address match
    norm = normalise_address(addr)
    # Remove suburb from both and try matching
    # Target: "1 10 CORNELL COURT VARSITY LAKES QLD 4227"
    # GC:     "1/10 CORNELL COURT VARSITY LAKES QLD 4227" or "10 CORNELL COURT VARSITY LAKES QLD 4227"

    if norm in primary_idx:
        return primary_idx[norm]["_id"], "exact"

    # 2. Try with unit/number reformatting
    # Target "1 10 Cornell Court" means unit 1, 10 Cornell Court
    # GC might store as "1/10 CORNELL COURT" in complete_address
    # Or GC might have UNIT_NUMBER=1, STREET_NO_1=10
    parts = parse_target_address(addr)
    cleaned = parts["cleaned"]

    # Try "X/Y" format: "1 10 CORNELL COURT" -> "1/10 CORNELL COURT"
    unit_match = re.match(r"^(\d+)\s+(\d+)\s+(.+)", cleaned)
    if unit_match:
        unit_num = unit_match.group(1)
        street_no = unit_match.group(2)
        rest = unit_match.group(3)
        # Try "UNIT/STREET REST QLD POSTCODE"
        alt = f"{unit_num}/{street_no} {rest}"
        # Remove suburb suffix to compare
        for suffix in [" VARSITY LAKES", " ROBINA", " BURLEIGH WATERS",
                       " MUDGEERABA", " MERRIMAC", " CARRARA",
                       " WORONGARY", " REEDY CREEK"]:
            alt_full = f"{alt}{suffix} QLD {parts['postcode']}"
            if alt_full in primary_idx:
                return primary_idx[alt_full]["_id"], "unit_reformat"

    # 3. Street index fuzzy match
    # Extract street number + name from target address
    # "73 AZZURRA DRIVE VARSITY LAKES" -> look for "73 AZZURRA DRIVE"
    addr_clean = re.sub(r"\s+QLD\s+\d{4}$", "", cleaned, flags=re.IGNORECASE)
    # Remove known suburb names
    for suburb in ["VARSITY LAKES", "ROBINA", "BURLEIGH WATERS",
                   "MUDGEERABA", "MERRIMAC", "CARRARA",
                   "WORONGARY", "REEDY CREEK"]:
        addr_clean = addr_clean.replace(suburb, "").strip()

    # Now addr_clean should be like "73 AZZURRA DRIVE" or "1 10 CORNELL COURT"
    if addr_clean in street_idx:
        candidates = street_idx[addr_clean]
        if len(candidates) == 1:
            return candidates[0]["_id"], "street_match"
        # Multiple matches (e.g. units in same building) — try unit match
        if unit_match:
            unit_num = unit_match.group(1)
            for c in candidates:
                if str(c.get("unit", "")) == unit_num:
                    return c["_id"], "street_unit_match"
        # If only one candidate, use it
        if len(candidates) == 1:
            return candidates[0]["_id"], "street_match"

    # 4. Try without unit prefix for street index
    if unit_match:
        street_key = f"{unit_match.group(2)} {unit_match.group(3)}"
        for suburb in ["VARSITY LAKES", "ROBINA", "BURLEIGH WATERS",
                       "MUDGEERABA", "MERRIMAC", "CARRARA",
                       "WORONGARY", "REEDY CREEK"]:
            street_key = street_key.replace(suburb, "").strip()
        if street_key in street_idx:
            candidates = street_idx[street_key]
            unit_num = unit_match.group(1)
            for c in candidates:
                if str(c.get("unit", "")) == unit_num:
                    return c["_id"], "street_unit_fallback"

    return None, None


# -- Merge logic --------------------------------------------------------------

def merge_suburb(client, suburb: str, dry_run: bool = False, force: bool = False) -> dict:
    """
    Merge sold data from Target_Market into Gold_Coast for one suburb.
    Returns stats dict.
    """
    tm_coll = client[DB_TARGET][suburb]
    gc_coll = client[DB_GOLD_COAST][suburb]

    stats = {
        "total_target": 0,
        "matched": 0,
        "updated": 0,
        "skipped_already_sold": 0,
        "unmatched": 0,
        "errors": 0,
        "unmatched_addresses": [],
    }

    print(f"\n  Building Gold_Coast.{suburb} address index...")
    primary_idx, street_idx = build_gc_address_index(gc_coll)
    print(f"  Index: {len(primary_idx)} addresses, {len(street_idx)} street keys")

    # Iterate Target_Market docs with retry for Cosmos 429
    print(f"  Reading Target_Market_Sold_Last_12_Months.{suburb}...")
    max_attempts = 3
    backoff = 2.0
    tm_docs = None
    for attempt in range(1, max_attempts + 1):
        try:
            tm_docs = list(tm_coll.find({}))
            break
        except OperationFailure as exc:
            if exc.code == 16500 and attempt < max_attempts:
                print(f"  Cosmos 429 — retrying in {backoff:.0f}s")
                time.sleep(backoff)
                backoff *= 2
            else:
                raise

    if tm_docs is None:
        print(f"  FAILED to read Target_Market docs")
        return stats

    stats["total_target"] = len(tm_docs)
    print(f"  Found {len(tm_docs)} sold records to merge")

    for tm_doc in tm_docs:
        gc_id, method = match_target_to_gc(tm_doc, primary_idx, street_idx)

        if gc_id is None:
            stats["unmatched"] += 1
            addr = tm_doc.get("address", "?")[:60]
            stats["unmatched_addresses"].append(addr)
            continue

        stats["matched"] += 1

        # Check if already sold and skip unless --force
        norm_addr = normalise_address(tm_doc.get("address", ""))
        existing = primary_idx.get(norm_addr, {})
        existing_status = existing.get("listing_status") if isinstance(existing, dict) else None

        if existing_status == "sold" and not force:
            stats["skipped_already_sold"] += 1
            continue

        # Build the update
        update_fields = {
            "listing_status": "sold",
            "sold_source": "target_market_sold_merge",
            "sold_merge_date": datetime.now(timezone.utc),
        }

        # Copy sold-specific fields
        for field in SOLD_FIELDS:
            val = tm_doc.get(field)
            if val is not None:
                update_fields[field] = val

        # Parse and set structured sold fields
        sale_price_raw = tm_doc.get("sale_price", "")
        if sale_price_raw:
            update_fields["sale_price"] = sale_price_raw
            update_fields["listing_price"] = f"SOLD - {sale_price_raw}"

        sale_date = tm_doc.get("sale_date", "")
        if sale_date:
            update_fields["sold_date"] = sale_date
            update_fields["sold_status"] = "sold"

        dom = tm_doc.get("time_on_market_days")
        if dom is not None:
            update_fields["days_on_market"] = dom

        # Set street_address and suburb for article pipeline compatibility
        addr = tm_doc.get("address", "")
        if addr:
            # Parse "1 10 Cornell Court Varsity, Lakes, QLD 4227" -> "1/10 Cornell Court"
            clean = addr.replace(",", " ").strip()
            clean = re.sub(r"\s+QLD\s+\d{4}$", "", clean, flags=re.IGNORECASE).strip()
            for s in ["Varsity Lakes", "Robina", "Burleigh Waters",
                       "Mudgeeraba", "Merrimac", "Carrara",
                       "Worongary", "Reedy Creek",
                       "varsity lakes", "robina", "burleigh waters",
                       "mudgeeraba", "merrimac", "carrara",
                       "worongary", "reedy creek"]:
                clean = re.sub(r"\s*" + re.escape(s) + r"\s*$", "", clean, flags=re.IGNORECASE).strip()

            # Reformat "1 10 Cornell Court" -> "1/10 Cornell Court"
            um = re.match(r"^(\d+)\s+(\d+)\s+(.+)", clean)
            if um:
                clean = f"{um.group(1)}/{um.group(2)} {um.group(3)}"

            update_fields["street_address"] = clean

        # Suburb display name
        suburb_display = suburb.replace("_", " ").title()
        update_fields["suburb"] = suburb_display
        update_fields["postcode"] = tm_doc.get("address", "").strip()[-4:]

        # Bedrooms/bathrooms/carspaces
        for field in ["bedrooms", "bathrooms", "carspaces"]:
            val = tm_doc.get(field)
            if val is not None:
                update_fields[field] = val

        if dry_run:
            addr_display = update_fields.get("street_address", "?")
            price = update_fields.get("sale_price", "?")
            date = update_fields.get("sold_date", "?")
            print(f"    [DRY] Would update: {addr_display} — {price} — {date} (match: {method})")
            stats["updated"] += 1
        else:
            try:
                gc_coll.update_one(
                    {"_id": gc_id},
                    {"$set": update_fields}
                )
                stats["updated"] += 1
            except Exception as exc:
                print(f"    ERROR updating {gc_id}: {exc}")
                stats["errors"] += 1

    return stats


# -- Main ---------------------------------------------------------------------

def main():
    parser = argparse.ArgumentParser(description="Merge Target_Market sold data into Gold_Coast")
    parser.add_argument("--dry-run", action="store_true", help="Preview changes without writing")
    parser.add_argument("--suburb", type=str, default=None, choices=TARGET_SUBURBS, help="Single suburb only")
    parser.add_argument("--force", action="store_true", help="Overwrite existing sold records")
    args = parser.parse_args()

    print("=" * 60)
    print("MERGE: Target_Market_Sold_Last_12_Months -> Gold_Coast")
    print(f"Started: {datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M UTC')}")
    if args.dry_run:
        print("MODE: DRY RUN (no writes)")
    print("=" * 60)

    client = MongoClient(COSMOS_URI, serverSelectionTimeoutMS=15000)
    client.admin.command("ping")
    print("Connected to MongoDB")

    suburbs = [args.suburb] if args.suburb else TARGET_SUBURBS
    grand_totals = {
        "total_target": 0, "matched": 0, "updated": 0,
        "skipped_already_sold": 0, "unmatched": 0, "errors": 0,
    }
    all_unmatched = []

    for suburb in suburbs:
        print(f"\n{'—' * 50}")
        print(f"  SUBURB: {suburb.replace('_', ' ').title()}")
        print(f"{'—' * 50}")

        stats = merge_suburb(client, suburb, dry_run=args.dry_run, force=args.force)

        for k in grand_totals:
            grand_totals[k] += stats.get(k, 0)
        all_unmatched.extend([(suburb, a) for a in stats.get("unmatched_addresses", [])])

        print(f"\n  Results for {suburb}:")
        print(f"    Target records:     {stats['total_target']}")
        print(f"    Matched:            {stats['matched']}")
        print(f"    Updated:            {stats['updated']}")
        print(f"    Already sold:       {stats['skipped_already_sold']}")
        print(f"    Unmatched:          {stats['unmatched']}")
        print(f"    Errors:             {stats['errors']}")

    # -- Summary
    print(f"\n{'=' * 60}")
    print("COMPLETE")
    print(f"  Total target records: {grand_totals['total_target']}")
    print(f"  Matched:              {grand_totals['matched']}")
    print(f"  Updated:              {grand_totals['updated']}")
    print(f"  Already sold:         {grand_totals['skipped_already_sold']}")
    print(f"  Unmatched:            {grand_totals['unmatched']}")
    print(f"  Errors:               {grand_totals['errors']}")

    if all_unmatched:
        print(f"\n  Unmatched addresses ({len(all_unmatched)}):")
        for suburb, addr in all_unmatched[:20]:
            print(f"    [{suburb}] {addr}")
        if len(all_unmatched) > 20:
            print(f"    ... and {len(all_unmatched) - 20} more")

    print("=" * 60)
    client.close()


if __name__ == "__main__":
    main()
