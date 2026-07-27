"""
link_property_ids.py — match PropRadar sold records to our Gold_Coast property docs
by normalised address, write `propradar_property_id` onto matched docs, and emit a
coverage-gap worklist (PropRadar addresses we have NO document for → candidates for
new off-market pages).

Reads PropRadar records from Gold_Coast.propradar_sold (populated by ingest_sold.py).
For validation before the full backfill, --pr-json <file> can substitute a raw
suburb `/sold` dump instead of the collection.

Usage:
    python3 scripts/propradar/link_property_ids.py --suburb robina --dry-run
    python3 scripts/propradar/link_property_ids.py --suburb robina --apply
    python3 scripts/propradar/link_property_ids.py --suburb robina --pr-json /tmp/robina.json --dry-run
"""
from __future__ import annotations

import argparse
import datetime
import json
import os
import sys
from collections import defaultdict

sys.path.insert(0, "/home/fields/Fields_Orchestrator")
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from shared.db import get_gold_coast_db, cosmos_retry  # noqa: E402
from addr_match import normalize_address  # noqa: E402

SUBURBS = {
    "robina": ("Robina", 4226),
    "burleigh_waters": ("Burleigh Waters", 4220),
    "varsity_lakes": ("Varsity Lakes", 4227),
}
_STATUS_RANK = {"for_sale": 0, "under_contract": 0, "sold": 0}


def build_our_index(coll, suburb_name, postcode):
    """Normalised-address -> chosen doc, resolving collisions deterministically."""
    buckets = defaultdict(list)
    for d in coll.find({"address": {"$exists": True, "$ne": None}},
                       {"address": 1, "listing_status": 1, "url_slug": 1}):
        k = normalize_address(d["address"], suburb_name, postcode)
        if k:
            buckets[k].append(d)
    chosen, collisions = {}, 0
    for k, docs in buckets.items():
        if len(docs) > 1:
            collisions += 1
            docs = sorted(docs, key=lambda d: (
                _STATUS_RANK.get(d.get("listing_status"), 1),   # prefer a real listing
                len(d.get("url_slug") or ""),                   # prefer canonical (shorter) slug
                str(d["_id"]),
            ))
        chosen[k] = docs[0]
    return chosen, collisions


def load_pr_props(db, suburb_key, pr_json):
    """distinct PropRadar property_id -> address (from collection or a raw json dump)."""
    props = {}
    if pr_json:
        for r in json.load(open(pr_json)):
            if r.get("property_id"):
                props[r["property_id"]] = r.get("address")
    else:
        for r in db["propradar_sold"].find({"suburb_key": suburb_key},
                                            {"property_id": 1, "address": 1}):
            props[r["property_id"]] = r.get("address")
    return props


def link(suburb_key, apply, pr_json=None):
    name, pc = SUBURBS[suburb_key]
    db = get_gold_coast_db()
    coll = db[suburb_key]
    our_index, collisions = build_our_index(coll, name, pc)
    pr_props = load_pr_props(db, suburb_key, pr_json)

    matched, gaps = [], []
    for pid, addr in pr_props.items():
        doc = our_index.get(normalize_address(addr, name, pc))
        (matched if doc else gaps).append((pid, addr, doc))

    total = len(pr_props)
    print(f"\n{name}: PropRadar properties={total} | our distinct addresses={len(our_index)} "
          f"(collisions={collisions})")
    print(f"  MATCHED {len(matched)}/{total} = {100*len(matched)//max(1,total)}%  "
          f"| coverage-gaps {len(gaps)}")
    print("  gap sample:", [a for _, a, _ in gaps[:8]])

    if not apply:
        print("  (dry-run — nothing written)")
        return matched, gaps

    now = datetime.datetime.now(datetime.timezone.utc).isoformat()
    for pid, addr, doc in matched:
        cosmos_retry(
            lambda d=doc, p=pid: coll.update_one(
                {"_id": d["_id"]},
                {"$set": {"propradar_property_id": p, "propradar_linked_at": now}}),
            f"link:{pid}")
    gapcoll = db["propradar_coverage_gaps"]
    for pid, addr, _ in gaps:
        cosmos_retry(
            lambda p=pid, a=addr: gapcoll.replace_one(
                {"_id": p},
                {"_id": p, "suburb_key": suburb_key, "address": a,
                 "status": "pending", "found_at": now, "source": "propradar"},
                upsert=True),
            f"gap:{pid}")
    print(f"  wrote propradar_property_id to {len(matched)} docs; "
          f"{len(gaps)} gaps → Gold_Coast.propradar_coverage_gaps")
    return matched, gaps


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--suburb", choices=list(SUBURBS), required=True)
    ap.add_argument("--pr-json", help="raw /sold dump for validation (bypasses propradar_sold)")
    ap.add_argument("--apply", action="store_true")
    ap.add_argument("--dry-run", action="store_true")
    args = ap.parse_args()
    link(args.suburb, args.apply and not args.dry_run, args.pr_json)


if __name__ == "__main__":
    main()
