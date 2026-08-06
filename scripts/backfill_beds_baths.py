#!/usr/bin/env python3
"""
backfill_beds_baths.py — fill top-level bedrooms/bathrooms from the fallback
paths in config/canonical_attributes.yaml.

WHY (2026-08-06). The top-level `bedrooms` field is null on 4,941 off-market
houses across the three target suburbs. A missing bedroom count is not cosmetic:

  * `competitor_matcher.resolve_competitor_map()` returns None outright — no
    substitute set, so the competition panel cannot render at all
  * `scarcity_features` loses its anchor stack, so the rarity claim collapses
    (28 Wedgebill fell to a single anchor matching 54% of the market)
  * `precompute_valuations` treated the home as having ZERO bedrooms until the
    same-day fix, subtracting the full per-bedroom rate against every comparable

72% of those homes carry the count in `scraped_data_v2.bedrooms`, which nothing
reads. This writes it to the field every consumer already looks at.

Provenance is recorded on each document so the write is auditable and reversible:

    bedrooms_source = {"path": "scraped_data_v2.bedrooms",
                       "backfilled_at": "...", "script": "backfill_beds_baths"}

DRY RUN BY DEFAULT.

    python3 scripts/backfill_beds_baths.py                 # report only
    python3 scripts/backfill_beds_baths.py --apply
    python3 scripts/backfill_beds_baths.py --apply --suburb robina
    python3 scripts/backfill_beds_baths.py --revert        # undo backfilled values
"""
import argparse
import os
import sys
from datetime import datetime, timezone

sys.path.insert(0, "/home/fields/Fields_Orchestrator")
from dotenv import load_dotenv
from pymongo import UpdateOne

from src.mongo_client_factory import get_mongo_client

SUBURBS = ["robina", "varsity_lakes", "burleigh_waters"]

# Ordered exactly as config/canonical_attributes.yaml source_priority.
PATHS = {
    "bedrooms": ["scraped_data_v2.bedrooms",
                 "scraped_data.features.bedrooms",
                 "property_valuation_data.layout.number_of_bedrooms"],
    "bathrooms": ["scraped_data_v2.bathrooms",
                  "scraped_data.features.bathrooms",
                  "property_valuation_data.layout.number_of_bathrooms"],
}


def dig(doc, path):
    cur = doc
    for part in path.split("."):
        if not isinstance(cur, dict):
            return None
        cur = cur.get(part)
    return cur


def plausible(field, v):
    """Reject junk before it becomes a canonical fact."""
    if not isinstance(v, (int, float)) or isinstance(v, bool):
        return False
    v = float(v)
    if v != int(v) or v < 1:
        return False
    return v <= (12 if field == "bedrooms" else 10)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--apply", action="store_true", help="write (default: dry run)")
    ap.add_argument("--revert", action="store_true", help="undo values this script wrote")
    ap.add_argument("--suburb", default=None)
    args = ap.parse_args()

    load_dotenv("/home/fields/Fields_Orchestrator/.env")
    db = get_mongo_client()["Gold_Coast"]
    subs = [args.suburb] if args.suburb else SUBURBS
    now = datetime.now(timezone.utc).isoformat()

    if args.revert:
        for s in subs:
            for field in PATHS:
                r = db[s].update_many(
                    {f"{field}_source.script": "backfill_beds_baths"},
                    {"$unset": {field: "", f"{field}_source": ""}})
                print(f"  {s}.{field}: reverted {r.modified_count}")
        return 0

    grand = {"bedrooms": 0, "bathrooms": 0}
    rejected = 0
    for s in subs:
        ops = []
        found = {"bedrooms": 0, "bathrooms": 0}
        by_path = {}
        cur = db[s].find(
            {"listing_status": {"$exists": False}, "property_type": "House",
             "$or": [{"bedrooms": None}, {"bedrooms": {"$exists": False}},
                     {"bathrooms": None}, {"bathrooms": {"$exists": False}}]})
        for doc in cur:
            sets = {}
            for field, paths in PATHS.items():
                if doc.get(field) is not None:
                    continue
                for p in paths:
                    v = dig(doc, p)
                    if v is None:
                        continue
                    if not plausible(field, v):
                        globals()["_rej"] = globals().get("_rej", 0) + 1
                        continue
                    sets[field] = int(v)
                    sets[f"{field}_source"] = {"path": p, "backfilled_at": now,
                                               "script": "backfill_beds_baths"}
                    found[field] += 1
                    by_path[p] = by_path.get(p, 0) + 1
                    break
            if sets:
                ops.append(UpdateOne({"_id": doc["_id"]}, {"$set": sets}))

        print(f"\n  {s}")
        for f_ in PATHS:
            print(f"    {f_:<10} fillable: {found[f_]:>6,}")
            grand[f_] += found[f_]
        for p, n in sorted(by_path.items(), key=lambda x: -x[1]):
            print(f"       via {p:<52} {n:>6,}")

        if args.apply and ops:
            for i in range(0, len(ops), 400):
                db[s].bulk_write(ops[i:i + 400], ordered=False)
            print(f"    ✅ wrote {len(ops):,} documents")
        elif ops:
            print(f"    (dry run — would write {len(ops):,} documents)")

    print(f"\n  TOTAL bedrooms {grand['bedrooms']:,} · bathrooms {grand['bathrooms']:,}"
          f" · rejected as implausible {globals().get('_rej', 0):,}")
    if not args.apply:
        print("\n  DRY RUN. Re-run with --apply to write. --revert undoes it.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
