#!/usr/bin/env python3
"""
Top up `Gold_Coast.address_search_index` with addresses we already hold but that
were never indexed.

WHY THIS EXISTS
---------------
`address_search_index` was built exactly once — every row's ObjectId timestamps to
2026-03-07 — by `scripts/build-address-index.mjs`, and nothing rebuilds it. Six
months of new cadastral rows and sold-listing addresses have accumulated in the
suburb collections since. Measured 2026-09-06 over the three core suburbs:
**1,843 of 25,177 addresses (7.3%) we hold are absent from the index**, 1,002 of
them unit addresses.

They are not invisible — `address-search.mjs` falls back to scanning the suburb
collections when the indexed path returns nothing — but that fallback measured
**~11 seconds** live (10.7s-12.0s over four probes) against ~0.2-0.6s on the
indexed path. The address search is the single highest-value action on the site
(reward_ledger: 47x lift to the seller reward), it is keystroke-debounced, and its
zero-result state renders nothing at all, so an 11-second wait is indistinguishable
from a broken box.

This script is an ADDITIVE top-up only. It inserts rows for addresses that are
missing; it never updates or deletes an existing row. A future full rebuild
supersedes it harmlessly.

Usage:
    python3 scripts/topup_address_search_index.py --dry-run
    python3 scripts/topup_address_search_index.py --suburbs varsity_lakes,robina,burleigh_waters
"""
import argparse
import re
import sys
import time

sys.path.insert(0, "/home/fields/Fields_Orchestrator")
from shared.db import get_client  # noqa: E402
from shared.env import load_env  # noqa: E402

INDEX_COLLECTION = "address_search_index"
DEFAULT_SUBURBS = ["varsity_lakes", "robina", "burleigh_waters"]
TARGET_MARKET = {
    "robina", "mudgeeraba", "varsity_lakes", "carrara",
    "reedy_creek", "burleigh_waters", "merrimac", "worongary",
}
BATCH = 50  # small batches: Cosmos 429s on anything larger here


def norm(a):
    return re.sub(r"\s+", " ", (a or "").upper()).strip()


def display_name(key):
    return " ".join(w.capitalize() for w in key.split("_"))


def index_doc(src, suburb_key):
    """Mirror the field set build-address-index.mjs writes, from a source doc."""
    addr = norm(src.get("complete_address"))
    images = src.get("images") if isinstance(src.get("images"), list) else []
    scraped = src.get("scraped_data") or {}
    street_no = src.get("STREET_NO_1") or ""
    street_name = (src.get("STREET_NAME") or "").upper()
    street_type = (src.get("STREET_TYPE") or "").upper()
    # address_display: "3 Lumley Street" — number + street, no suburb/state.
    disp = f"{street_no} {street_name} {street_type}".strip()
    disp = " ".join(w.capitalize() for w in disp.split()) if disp else ""
    return {
        "address": addr,
        "address_display": disp,
        "street_no": str(street_no),
        "street_name": street_name,
        "street_type": street_type,
        "source_id": src["_id"],
        "suburb_key": suburb_key,
        "suburb": display_name(suburb_key),
        "postcode": src.get("POSTCODE") or "",
        "property_type": src.get("PROPERTY_TYPE") or "Residential",
        "has_images": len(images) > 0,
        "image_count": len(images),
        "bedrooms": scraped.get("bedrooms"),
        "bathrooms": scraped.get("bathrooms"),
        "car_spaces": scraped.get("car_spaces"),
        "is_target_market": suburb_key in TARGET_MARKET,
        "topup_source": "topup_address_search_index.py",  # provenance, additive only
    }


def insert_with_retry(coll, batch, attempts=6):
    for i in range(attempts):
        try:
            coll.insert_many(batch, ordered=False)
            return len(batch)
        except Exception as exc:  # Cosmos 16500 / 429 -> back off
            if "16500" in str(exc) or "429" in str(exc) or "RetryAfterMs" in str(exc):
                time.sleep(1.5 * (i + 1))
                continue
            raise
    raise RuntimeError("insert_with_retry exhausted retries")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--suburbs", default=",".join(DEFAULT_SUBURBS))
    ap.add_argument("--dry-run", action="store_true")
    args = ap.parse_args()

    load_env()
    db = get_client()["Gold_Coast"]
    idx = db[INDEX_COLLECTION]

    grand_missing = grand_inserted = 0
    for suburb in [s.strip() for s in args.suburbs.split(",") if s.strip()]:
        have = {norm(r["address"]) for r in idx.find({"suburb_key": suburb}, {"address": 1})}
        src_by_addr = {}
        for r in db[suburb].find(
            {"complete_address": {"$exists": True, "$ne": None}},
            {"complete_address": 1, "STREET_NO_1": 1, "STREET_NAME": 1,
             "STREET_TYPE": 1, "POSTCODE": 1, "PROPERTY_TYPE": 1,
             "images": 1, "scraped_data.bedrooms": 1, "scraped_data.bathrooms": 1,
             "scraped_data.car_spaces": 1},
        ):
            a = norm(r["complete_address"])
            if a and a not in have:
                src_by_addr.setdefault(a, r)  # first doc wins; index dedupes on display anyway

        missing = list(src_by_addr.values())
        grand_missing += len(missing)
        print(f"{suburb}: {len(have)} indexed, {len(missing)} missing")
        if args.dry_run:
            for r in missing[:5]:
                print("    e.g.", norm(r["complete_address"]))
            continue

        batch, inserted = [], 0
        for r in missing:
            batch.append(index_doc(r, suburb))
            if len(batch) >= BATCH:
                inserted += insert_with_retry(idx, batch)
                batch = []
        if batch:
            inserted += insert_with_retry(idx, batch)
        grand_inserted += inserted
        print(f"  inserted {inserted}")

    # Rule 7b applied to a one-shot: assert an outcome, do not merely not-throw.
    if not args.dry_run and grand_missing > 0 and grand_inserted == 0:
        raise RuntimeError(
            f"{grand_missing} addresses were missing but 0 were inserted — the write path is broken"
        )
    print(f"\nTOTAL missing={grand_missing} inserted={grand_inserted}")


if __name__ == "__main__":
    main()
