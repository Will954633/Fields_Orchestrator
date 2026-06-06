#!/usr/bin/env python3
"""
backfill_stated_floor_area.py — populate `internal_living_area_sqm` on subject
docs by reading the PRINTED internal-area label off each floor plan.

This is the authoritative ground-truth pass behind the floor-area methodology
fix: the canonical resolver (inline_features.resolve_floor_areas /
precompute_valuations.resolve_floor_area) prefers `internal_living_area_sqm` /
`floor_plan.stated_internal_area_sqm` above every other signal. Once enough of
the cohort carries a stated internal, the valuation recompute can run on
read-off-the-plan internal-living areas instead of noisy fallbacks.

For each property (core suburbs, for_sale + sold) that has a floor plan and no
stated internal yet, run the floor-plan vision pass (gpt-4o, now extracting the
printed "Internal / Garage / External / Total" summary box) and, when a printed
internal figure is found and passes a sanity check (40-2000 m², not exceeding the
measured building area), write it to the subject doc.

Usage:
    python3 -m scripts.property_reports.backfill_stated_floor_area [--suburb robina]
        [--limit N] [--force] [--dry-run] [--sleep 0.3]
"""
from __future__ import annotations

import argparse
import logging
import os
import sys
import time
from collections import Counter

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
logger = logging.getLogger("backfill_stated_floor_area")

CORE_SUBURBS = ["robina", "varsity_lakes", "burleigh_waters"]
FP_FIELDS = ["floor_plans_v2_extracted", "floor_plans", "floor_plans_original", "scraped_floor_plans"]


def best_fp_url(doc, to_bucket, is_bucket):
    for f in FP_FIELDS:
        urls = doc.get(f)
        if isinstance(urls, list) and urls:
            cand = [to_bucket(u) for u in urls if isinstance(u, str)]
            if cand:
                cand.sort(key=lambda u: (is_bucket(u), "/fit-in/" in u, "5760" in u or "3240" in u, len(u)), reverse=True)
                return cand[0]
    return None


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--suburb", action="append", help="Limit to suburb(s); default = core three")
    ap.add_argument("--limit", type=int, default=0, help="Max properties to process (0 = all)")
    ap.add_argument("--force", action="store_true", help="Re-read even if internal_living_area_sqm set")
    ap.add_argument("--dry-run", action="store_true", help="Read + report, do not write")
    ap.add_argument("--sleep", type=float, default=0.3, help="Seconds between vision calls")
    args = ap.parse_args()

    sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))
    from shared.db import get_client
    from scripts.property_reports.inline_floor_plan import analyse_floor_plan, to_bucket_api_url, is_bucket_api

    suburbs = args.suburb or CORE_SUBURBS
    client = get_client()
    gc = client["Gold_Coast"]

    stats = Counter()
    processed = 0
    for sk in suburbs:
        coll = gc[sk]
        q = {"listing_status": {"$in": ["for_sale", "sold"]}}
        if not args.force:
            q["internal_living_area_sqm"] = {"$exists": False}
        q["$or"] = [{f: {"$exists": True, "$ne": []}} for f in FP_FIELDS]
        cur = coll.find(q, {f: 1 for f in FP_FIELDS} | {"total_floor_area": 1, "address": 1, "display_address": 1})
        for d in cur:
            if args.limit and processed >= args.limit:
                break
            url = best_fp_url(d, to_bucket_api_url, is_bucket_api)
            if not url:
                stats["no_fp_url"] += 1
                continue
            processed += 1
            stats["processed"] += 1
            try:
                layout = analyse_floor_plan(url)
            except Exception as e:
                logger.warning(f"  vision error: {e}")
                stats["vision_error"] += 1
                time.sleep(args.sleep)
                continue
            if not layout:
                stats["vision_none"] += 1
                time.sleep(args.sleep)
                continue

            stated = layout.get("stated_internal_area_sqm")
            src = layout.get("area_source")
            if not stated and src == "printed_summary":
                stated = layout.get("total_internal_area_sqm")
            try:
                stated = float(stated) if stated is not None else None
            except (TypeError, ValueError):
                stated = None

            if not stated:
                stats["no_printed_internal"] += 1
                time.sleep(args.sleep)
                continue
            if not (40 <= stated <= 2000):
                stats["implausible"] += 1
                time.sleep(args.sleep)
                continue
            building = d.get("total_floor_area")
            try:
                building = float(building) if building is not None else None
            except (TypeError, ValueError):
                building = None
            if building and stated > building * 1.05:
                # printed "internal" exceeds measured building area — suspect read
                stats["exceeds_building"] += 1
                time.sleep(args.sleep)
                continue

            stats["backfilled"] += 1
            addr = d.get("address") or d.get("display_address") or d.get("_id")
            logger.info(f"  {sk}: {str(addr)[:42]:42} internal_living={stated} (building={building})")
            if not args.dry_run:
                coll.update_one(
                    {"_id": d["_id"]},
                    {"$set": {
                        "internal_living_area_sqm": stated,
                        "internal_living_area_source": "floor_plan_printed_label",
                    }},
                )
            time.sleep(args.sleep)
        if args.limit and processed >= args.limit:
            break

    logger.info("=== BACKFILL SUMMARY ===")
    for k, v in sorted(stats.items()):
        logger.info(f"  {k}: {v}")
    if stats["processed"]:
        hit = 100 * stats["backfilled"] / stats["processed"]
        logger.info(f"  printed-internal hit rate: {hit:.0f}%")
    return 0


if __name__ == "__main__":
    sys.exit(main())
