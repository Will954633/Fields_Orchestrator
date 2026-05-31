#!/usr/bin/env python3
"""
Backfill photos + floor plans for sold homes that were captured as sold-only
records (no media). These "RED" records have a listing_url but were never
scraped at the property-detail level — typically homes that sold without us
catching them as an active for-sale listing.

For each such home we re-fetch its Domain detail page via the production
Bright Data Web Unlocker path (shared.domain_fetch.fetch_html) and parse it with
the production detail parser (html_parser.parse_listing_html), then $set the
media + descriptive fields onto the existing Gold_Coast doc WITHOUT touching the
clean sold_date / sale_price already stored.

Once media lands, the nightly enrichment steps (110 blob download, floor-plan
analysis, photo analysis, feature extraction) derive the rest.

Usage:
  python3 scripts/backfill_sold_media.py --dry-run            # preview
  python3 scripts/backfill_sold_media.py --limit 3            # do 3 (smoke test)
  python3 scripts/backfill_sold_media.py                      # full run (core suburbs, 6mo)
  python3 scripts/backfill_sold_media.py --suburbs robina --days 182
"""
import os
import sys
import time
import argparse
from datetime import datetime, timedelta

# Repo root (so `shared` package resolves regardless of cwd)
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
# Production detail-page parser (extracts property_images, floor_plans, features, etc.)
PARSER_DIR = "/home/fields/Property_Data_Scraping/07_Undetectable_method/00_Production_System/02_Individual_Property_Google_Search"
sys.path.insert(0, PARSER_DIR)

from shared.domain_fetch import fetch_html  # Bright Data Web Unlocker (Akamai bypass)
from shared.db import get_client

CORE_SUBURBS = ["robina", "burleigh_waters", "varsity_lakes"]


def is_red(doc):
    """A sold home with no photos and no floor plans, but a re-scrapeable URL."""
    if doc.get("property_images") or doc.get("floor_plans"):
        return False
    return bool(doc.get("listing_url"))


def build_update(parsed):
    """Map parsed detail-page fields → DB $set, only for fields with real values.
    Never includes sold_date / sale_price — those stay as-is on the existing doc."""
    out = {}
    imgs = parsed.get("property_images") or []
    fplans = parsed.get("floor_plans") or []
    if imgs:
        out["property_images"] = imgs
        out["property_images_original"] = imgs
        out["images_uploaded_to_blob"] = False  # let nightly blob step (110) pick these up
    if fplans:
        out["floor_plans"] = fplans
        out["floor_plans_original"] = fplans
    for src, dst in [
        ("features", "features"),
        ("agents_description", "agents_description"),
        ("description", "description"),
        ("property_type", "property_type"),
        ("agent_name", "agent_name"),
        ("agency", "agency_name"),
        ("og_title", "og_title"),
    ]:
        v = parsed.get(src)
        if v:
            out[dst] = v
    return out, len(imgs), len(fplans)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--suburbs", nargs="+", default=CORE_SUBURBS)
    ap.add_argument("--days", type=int, default=182, help="sold-within window (default 182 = ~6mo)")
    ap.add_argument("--limit", type=int, default=0, help="cap number of homes (0 = no cap)")
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--sleep", type=float, default=1.5, help="seconds between fetches")
    args = ap.parse_args()

    cutoff = (datetime.now() - timedelta(days=args.days)).strftime("%Y-%m-%d")
    client = get_client()
    gc = client["Gold_Coast"]

    # Gather RED targets across suburbs
    targets = []
    for s in args.suburbs:
        col = gc[s]
        for d in col.find({"listing_status": "sold", "sold_date": {"$gte": cutoff}}):
            if is_red(d):
                targets.append((s, d))
    targets.sort(key=lambda t: str(t[1].get("sold_date")), reverse=True)
    if args.limit:
        targets = targets[: args.limit]

    print(f"RED targets (sold since {cutoff}, no media, has url): {len(targets)}")
    if args.dry_run:
        for s, d in targets[:20]:
            print(f"  [{s}] {str(d.get('sold_date'))[:10]} | {d.get('address','')[:50]} | {d.get('listing_url')}")
        if len(targets) > 20:
            print(f"  ... and {len(targets)-20} more")
        return

    ok = fail = no_media = 0
    total_imgs = total_fp = 0
    for i, (s, d) in enumerate(targets, 1):
        url = d["listing_url"]
        addr = d.get("address", "")[:45]
        try:
            html = fetch_html(url)
            if not html or len(html) < 5000:
                print(f"  [{i}/{len(targets)}] FETCH-FAIL {s} | {addr}")
                fail += 1
                time.sleep(args.sleep)
                continue
            from html_parser import parse_listing_html
            parsed = parse_listing_html(html, d.get("address", ""))
            update, ni, nf = build_update(parsed)
            if ni == 0 and nf == 0:
                print(f"  [{i}/{len(targets)}] NO-MEDIA  {s} | {addr} (listing likely delisted)")
                no_media += 1
                time.sleep(args.sleep)
                continue
            update["media_backfilled_at"] = datetime.now().isoformat()
            gc[s].update_one({"_id": d["_id"]}, {"$set": update})
            total_imgs += ni
            total_fp += nf
            ok += 1
            print(f"  [{i}/{len(targets)}] OK  {s} | {addr} | +{ni} photos +{nf} floorplans")
        except Exception as e:
            print(f"  [{i}/{len(targets)}] ERROR {s} | {addr} | {e}")
            fail += 1
        time.sleep(args.sleep)

    print(f"\nDone. updated={ok} no_media={no_media} failed={fail} | added {total_imgs} photos, {total_fp} floor plans")
    print("Next nightly run: step 110 downloads images to blob; floor-plan/photo analysis derives floor area, rooms, condition, features.")


if __name__ == "__main__":
    main()
