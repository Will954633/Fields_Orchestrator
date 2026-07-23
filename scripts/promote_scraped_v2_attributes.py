#!/usr/bin/env python3
"""
Promote scraped_data_v2 attributes to the canonical top-level fields.

Why this exists (2026-07-23)
----------------------------
The v2 Domain-profile scraper (`scrape_property_profiles.py`) stores every
attribute it captures INSIDE the `scraped_data_v2` sub-document, and its
"mirror to top-level" block only promotes the hero image, image URLs and
address — NOT land area, internal area, parking or property type. The feature
engine (`inline_features.derive_features_basic`) and the website off-market
loader read the CANONICAL top-level fields (`lot_size_sqm`, `floor_area_sqm`,
`car_spaces`, `property_type`), so any property whose v1 scrape missed land but
whose v2 scrape captured it ends up with those fields null.

Consequence: the off-market swipe deck's scarcity + positioning cards never
generate (no notable features → honest bail), and the deck shows no land size.
Measured 2026-07-23: 3,084 docs across robina/burleigh_waters/varsity_lakes/
merrimac had land stranded in scraped_data_v2 with both top-level land fields
null. 54 Heights Drive Robina was the reported case.

What it does
------------
For each doc that has a `scraped_data_v2`, copy these to the top level ONLY
when the canonical target is missing/empty (never overwrites curated or
enrichment-derived values, so it's safe to re-run):

    scraped_data_v2.land_area_sqm   -> lot_size_sqm      (50..20000 sqm guard)
    scraped_data_v2.internal_area_sqm -> floor_area_sqm  (20..2000 sqm guard)
    scraped_data_v2.parking_spaces  -> car_spaces        (>0 only)
    scraped_data_v2.property_type   -> property_type     (non-empty)

Usage
-----
    python3 scripts/promote_scraped_v2_attributes.py --dry-run
    python3 scripts/promote_scraped_v2_attributes.py                # all service suburbs
    python3 scripts/promote_scraped_v2_attributes.py --suburb robina
    python3 scripts/promote_scraped_v2_attributes.py --slug 54-heights-drive-robina
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from shared.db import get_client  # noqa: E402

try:
    from src.mongo_client_factory import cosmos_retry  # noqa: E402
except Exception:  # pragma: no cover — fallback if factory path differs
    def cosmos_retry(fn, *a, **k):
        return fn(*a, **k)

SERVICE_SUBURBS = [
    "robina",
    "burleigh_waters",
    "varsity_lakes",
    "merrimac",
    "mudgeeraba",
    "reedy_creek",
    "worongary",
]


def _num(v):
    try:
        f = float(v)
        return f if f > 0 else None
    except (TypeError, ValueError):
        return None


def _missing(doc, field):
    """True when a top-level field is absent/null/empty — safe to fill."""
    v = doc.get(field)
    return v is None or v == "" or v == 0


def build_update(doc: dict) -> dict:
    """Return the $set patch for one doc (only fields worth promoting)."""
    v2 = doc.get("scraped_data_v2")
    if not isinstance(v2, dict):
        return {}

    patch: dict = {}

    # Land — the field that actually unblocks scarcity/positioning + land display.
    if _missing(doc, "lot_size_sqm") and _missing(doc, "land_size_sqm"):
        land = _num(v2.get("land_area_sqm"))
        if land and 50 <= land <= 20000:
            patch["lot_size_sqm"] = land

    # Internal floor area — lowest-priority legacy slot; resolve_floor_areas
    # still prefers any floor-plan/vision measurement over this.
    enr = doc.get("enriched_data") if isinstance(doc.get("enriched_data"), dict) else {}
    if _missing(doc, "floor_area_sqm") and not _num(enr.get("floor_area_sqm")):
        fa = _num(v2.get("internal_area_sqm"))
        if fa and 20 <= fa <= 2000:
            patch["floor_area_sqm"] = fa

    # Parking — promote only a positive count (0 on Domain usually means
    # "none listed", i.e. unknown, not a measured zero).
    if _missing(doc, "car_spaces"):
        cs = _num(v2.get("parking_spaces"))
        if cs:
            patch["car_spaces"] = int(cs)

    # Property type — lets the deck know when a property is a unit/townhouse so
    # comps can be filtered by type (see memory: offmarket_ladder_arm).
    if _missing(doc, "property_type"):
        pt = v2.get("property_type")
        if isinstance(pt, str) and pt.strip():
            patch["property_type"] = pt.strip()

    return patch


def run(suburbs, dry_run=False, slug=None):
    gc = get_client()["Gold_Coast"]
    grand = {"scanned": 0, "updated": 0, "lot_size_sqm": 0, "floor_area_sqm": 0,
             "car_spaces": 0, "property_type": 0}

    for suburb in suburbs:
        col = gc[suburb]
        query = {"scraped_data_v2": {"$exists": True}}
        if slug:
            query["url_slug"] = slug
        proj = {"scraped_data_v2": 1, "url_slug": 1, "lot_size_sqm": 1,
                "land_size_sqm": 1, "floor_area_sqm": 1, "enriched_data.floor_area_sqm": 1,
                "car_spaces": 1, "property_type": 1}

        s_scanned = s_updated = 0
        for doc in col.find(query, proj):
            s_scanned += 1
            patch = build_update(doc)
            if not patch:
                continue
            s_updated += 1
            for k in patch:
                grand[k] = grand.get(k, 0) + 1
            if not dry_run:
                cosmos_retry(col.update_one, {"_id": doc["_id"]}, {"$set": patch})

        grand["scanned"] += s_scanned
        grand["updated"] += s_updated
        if s_scanned:
            print(f"  {suburb:<16} scanned={s_scanned:>6}  updated={s_updated:>6}")

    print("\n=== summary ({}) ===".format("DRY-RUN" if dry_run else "WRITTEN"))
    print(f"  docs scanned:  {grand['scanned']}")
    print(f"  docs updated:  {grand['updated']}")
    print(f"    lot_size_sqm   set: {grand['lot_size_sqm']}")
    print(f"    floor_area_sqm set: {grand['floor_area_sqm']}")
    print(f"    car_spaces     set: {grand['car_spaces']}")
    print(f"    property_type  set: {grand['property_type']}")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--suburb", help="single suburb collection (default: all service suburbs)")
    ap.add_argument("--slug", help="single property url_slug (implies its suburb via --suburb or scans all)")
    ap.add_argument("--dry-run", action="store_true")
    args = ap.parse_args()

    suburbs = [args.suburb] if args.suburb else SERVICE_SUBURBS
    run(suburbs, dry_run=args.dry_run, slug=args.slug)


if __name__ == "__main__":
    main()
