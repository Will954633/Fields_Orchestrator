#!/usr/bin/env python3
"""
Download case-study property photos for The Fields Quarterly Issue 01.

Stores them locally at pipeline/output/photos/ so the rendered PDF is
self-contained (independent of Azure blob storage availability).

USAGE:
    python3 pipeline/download_photos.py
"""

import os
import sys
import urllib.request
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent.parent
sys.path.insert(0, str(ROOT))

from shared.db import get_db  # noqa: E402

OUTPUT_DIR = HERE / "output" / "photos"
OUTPUT_DIR.mkdir(parents=True, exist_ok=True)


def download(url: str, dest: Path, force: bool = False) -> bool:
    if dest.exists() and not force:
        print(f"  exists: {dest.name}")
        return True
    try:
        req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
        with urllib.request.urlopen(req, timeout=30) as resp:
            data = resp.read()
        dest.write_bytes(data)
        print(f"  saved: {dest.name} ({len(data)/1024:.0f} KB)")
        return True
    except Exception as e:
        print(f"  ERROR: {url}\n    {e}")
        return False


def main():
    db = get_db("Gold_Coast")
    sm = db.client["system_monitor"]

    targets = [
        # (filename, suburb_collection, address_pattern, description)
        ("27_bittern_avenue_burleigh_waters.jpg", "burleigh_waters", "27 Bittern Avenue", "Tension case study"),
        ("32_outrigger_drive_robina.jpg", "robina", "32 Outrigger Drive", "Robina case study"),
        ("17_north_shore_avenue_varsity_lakes.jpg", "varsity_lakes", "17 North Shore Avenue", "Varsity Lakes case study"),
    ]

    for filename, suburb, addr, desc in targets:
        print(f"\n{desc} — {addr}")
        coll = db[suburb]
        doc = coll.find_one({"address": {"$regex": addr, "$options": "i"}})
        if not doc:
            print(f"  not found in DB")
            continue

        # Prefer photo_tour_order (curated front_exterior) → original_images first → blob
        url = None

        # Try photo_tour_order for the curated front_exterior shot
        tour = doc.get("photo_tour_order", [])
        for entry in tour:
            if isinstance(entry, dict) and entry.get("tour_section") == "front_exterior":
                url = entry.get("url")
                if url:
                    print(f"  using curated front_exterior")
                    break

        # Fallback: first image in property_images_original
        if not url:
            originals = doc.get("property_images_original", []) or doc.get("scraped_property_images", [])
            if originals:
                url = originals[0]
                print(f"  using property_images_original[0]")

        if not url:
            print(f"  no URL found")
            continue

        download(url, OUTPUT_DIR / filename)

    # Banksia Broadway — pull from article feature_image
    print(f"\nBurleigh Waters case study — 27 Banksia Broadway")
    a = sm["content_articles"].find_one({"slug": {"$regex": "1550000-burleigh"}})
    if a:
        url = a.get("feature_image")
        if url:
            print(f"  using article feature_image")
            download(url, OUTPUT_DIR / "27_banksia_broadway_burleigh_waters.jpg")

    print(f"\nAll photos saved to {OUTPUT_DIR}")


if __name__ == "__main__":
    main()
