#!/usr/bin/env python3
"""
Domain Valuation Monitor

Tracks Domain.com.au property valuations before and after listing.
Captures screenshots as evidence of valuation changes when properties
are listed for sale.

Workflow:
1. BASELINE CAPTURE: For all properties in target suburbs that are NOT listed,
   capture their Domain property profile page valuation ("before" snapshot).
2. DETECT NEW LISTINGS: When a property transitions to "for_sale" status,
   capture the valuation again ("after" snapshot).
3. COMPARE: Generate comparison data showing how Domain changed their
   valuation to match the listing price.
4. EXPORT: Write data for the public website.

Usage:
    python3 monitor.py baseline          # Capture baseline valuations for unlisted properties
    python3 monitor.py check-listings    # Check for new listings and capture "after" valuations
    python3 monitor.py export            # Export comparison data for website
    python3 monitor.py capture-one "28 Federal Place, Robina, QLD 4226" before
"""

import os
import sys
import json
import subprocess
import time
import re
from datetime import datetime, timezone, timedelta
from pathlib import Path

# Add parent directory for imports
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from pymongo import MongoClient
import yaml

# --- Config ---
SCRIPT_DIR = Path(__file__).parent
CAPTURE_SCRIPT = SCRIPT_DIR / "capture-screenshot.js"
SCREENSHOTS_DIR = SCRIPT_DIR / "screenshots"
EXPORT_DIR = SCRIPT_DIR / "website" / "data"
AEST = timezone(timedelta(hours=10))

# Target suburbs for monitoring (Gold Coast focus)
TARGET_SUBURBS = [
    "robina",
    "burleigh_waters",
    "varsity_lakes",
]

# How many unlisted properties to baseline per run (to be polite to Domain)
BASELINE_BATCH_SIZE = 20

# Delay between captures (seconds)
CAPTURE_DELAY = 5


def get_db():
    """Connect to MongoDB."""
    config_path = Path(__file__).parent.parent / "config" / "settings.yaml"
    with open(config_path) as f:
        cfg = yaml.safe_load(f)
    client = MongoClient(cfg["mongodb"]["uri"])
    return client["Gold_Coast"]


def get_monitor_collection():
    """Get the valuation_monitor collection in system_monitor DB."""
    config_path = Path(__file__).parent.parent / "config" / "settings.yaml"
    with open(config_path) as f:
        cfg = yaml.safe_load(f)
    client = MongoClient(cfg["mongodb"]["uri"])
    return client["system_monitor"]["valuation_tracker"]


def address_to_slug(address):
    """Convert address to URL-safe slug."""
    slug = address.lower()
    slug = re.sub(r"[,]", "", slug)
    slug = re.sub(r"\s+", "-", slug)
    slug = re.sub(r"[^a-z0-9-]", "", slug)
    return slug


def capture_property(address, label, output_dir=None):
    """Capture a single property's valuation screenshot."""
    slug = address_to_slug(address)
    if output_dir is None:
        output_dir = SCREENSHOTS_DIR / slug

    result = subprocess.run(
        [
            "node",
            str(CAPTURE_SCRIPT),
            "--address",
            address,
            "--output",
            str(output_dir),
            "--label",
            label,
        ],
        capture_output=True,
        text=True,
        timeout=120,
        cwd=str(SCRIPT_DIR.parent),
    )

    if result.returncode != 0:
        print(f"  ✗ FAILED: {result.stderr.strip()}")
        return None

    # Read the captured data
    data_file = output_dir / f"{label}-data.json"
    if data_file.exists():
        with open(data_file) as f:
            return json.load(f)
    return None


def cmd_baseline():
    """Capture baseline valuations for properties not currently listed."""
    print("=== Baseline Valuation Capture ===")
    print(f"Target suburbs: {', '.join(TARGET_SUBURBS)}")

    db = get_db()
    monitor = get_monitor_collection()
    captured = 0

    for suburb in TARGET_SUBURBS:
        collection = db[suburb]

        # Find properties that are NOT for_sale and have an address
        # These are either sold or cadastral records
        properties = list(
            collection.find(
                {
                    "listing_status": {"$nin": ["for_sale"]},
                    "address": {"$exists": True, "$ne": ""},
                },
                {"address": 1, "listing_status": 1, "_id": 1},
            ).limit(BASELINE_BATCH_SIZE)
        )

        print(f"\n{suburb}: {len(properties)} candidate properties")

        for prop in properties:
            address = prop["address"]
            slug = address_to_slug(address)

            # Skip if we already have a baseline for this property
            existing = monitor.find_one({"slug": slug, "baseline_captured": True})
            if existing:
                print(f"  ⏭ {address} (already baselined)")
                continue

            print(f"  📸 Capturing baseline: {address}")
            data = capture_property(address, "before")

            if data and data.get("valuation", {}).get("estimateMid"):
                # Store in MongoDB
                monitor.update_one(
                    {"slug": slug},
                    {
                        "$set": {
                            "address": address,
                            "suburb": suburb,
                            "slug": slug,
                            "baseline_captured": True,
                            "baseline_date": datetime.now(AEST).isoformat(),
                            "baseline_valuation": data["valuation"],
                            "baseline_screenshot": f"{slug}/before-valuation.png",
                            "baseline_full_screenshot": f"{slug}/before-full.png",
                            "listing_detected": False,
                            "updated_at": datetime.now(AEST).isoformat(),
                        },
                        "$setOnInsert": {
                            "created_at": datetime.now(AEST).isoformat(),
                        },
                    },
                    upsert=True,
                )
                captured += 1
                print(f"    ✓ Baseline: {data['valuation']['estimateMid']} ({data['valuation'].get('accuracy', 'unknown')} accuracy)")
            else:
                print(f"    ✗ No valuation data found")

            time.sleep(CAPTURE_DELAY)

            if captured >= BASELINE_BATCH_SIZE:
                print(f"\nReached batch limit ({BASELINE_BATCH_SIZE}). Run again for more.")
                break

        if captured >= BASELINE_BATCH_SIZE:
            break

    print(f"\n=== Captured {captured} baselines ===")


def cmd_check_listings():
    """Check for properties that have been newly listed and capture 'after' valuations."""
    print("=== Checking for New Listings ===")

    db = get_db()
    monitor = get_monitor_collection()
    captures = 0

    # Find all baselined properties
    baselined = list(monitor.find({"baseline_captured": True, "listing_detected": False}))
    print(f"Monitoring {len(baselined)} baselined properties for new listings")

    for entry in baselined:
        suburb = entry["suburb"]
        address = entry["address"]
        slug = entry["slug"]

        # Check if this property is now listed for sale
        collection = db[suburb]
        prop = collection.find_one(
            {"address": address, "listing_status": "for_sale"},
            {"listing_url": 1, "price_text": 1, "first_seen": 1, "_id": 0},
        )

        if prop:
            print(f"\n  🔴 NEW LISTING DETECTED: {address}")
            print(f"     Listing URL: {prop.get('listing_url', 'N/A')}")
            print(f"     Price: {prop.get('price_text', 'N/A')}")

            # Capture the "after" valuation
            print(f"     📸 Capturing post-listing valuation...")
            data = capture_property(address, "after")

            if data and data.get("valuation", {}).get("estimateMid"):
                before = entry.get("baseline_valuation", {})
                after = data["valuation"]

                monitor.update_one(
                    {"slug": slug},
                    {
                        "$set": {
                            "listing_detected": True,
                            "listing_date": datetime.now(AEST).isoformat(),
                            "listing_url": prop.get("listing_url"),
                            "listing_price_text": prop.get("price_text"),
                            "after_valuation": after,
                            "after_screenshot": f"{slug}/after-valuation.png",
                            "after_full_screenshot": f"{slug}/after-full.png",
                            "after_date": datetime.now(AEST).isoformat(),
                            "valuation_changed": before.get("estimateMid") != after.get("estimateMid"),
                            "updated_at": datetime.now(AEST).isoformat(),
                        },
                    },
                )

                print(f"     Before: {before.get('estimateMid', 'N/A')} → After: {after.get('estimateMid', 'N/A')}")
                if before.get("estimateMid") != after.get("estimateMid"):
                    print(f"     ⚠️  VALUATION CHANGED!")
                else:
                    print(f"     No change detected")

                captures += 1
            else:
                print(f"     ✗ Failed to capture post-listing valuation")

            time.sleep(CAPTURE_DELAY)

    print(f"\n=== Captured {captures} post-listing valuations ===")


def cmd_capture_one(address, label):
    """Capture a single property's valuation."""
    print(f"Capturing {label} valuation for: {address}")
    data = capture_property(address, label)
    if data:
        val = data.get("valuation", {})
        print(f"  Estimate: {val.get('estimateLow', '?')} - {val.get('estimateMid', '?')} - {val.get('estimateHigh', '?')}")
        print(f"  Accuracy: {val.get('accuracy', 'unknown')}")
        print(f"  For sale: {val.get('isForSale', False)}")
        print(f"  Updated: {val.get('updatedDate', 'unknown')}")
    else:
        print("  Failed to capture valuation")


def cmd_export():
    """Export comparison data for the website."""
    print("=== Exporting Comparison Data ===")

    monitor = get_monitor_collection()
    EXPORT_DIR.mkdir(parents=True, exist_ok=True)

    # Get all properties where listing was detected (have before + after)
    comparisons = list(monitor.find({"listing_detected": True}).sort("listing_date", -1))

    # Also get all baselined properties for the full picture
    all_tracked = list(monitor.find({}).sort("updated_at", -1))

    export_data = {
        "generated_at": datetime.now(AEST).isoformat(),
        "total_tracked": len(all_tracked),
        "total_with_changes": sum(1 for c in comparisons if c.get("valuation_changed")),
        "comparisons": [],
        "monitored": [],
    }

    for c in comparisons:
        entry = {
            "address": c["address"],
            "suburb": c["suburb"],
            "slug": c["slug"],
            "listing_url": c.get("listing_url"),
            "listing_price": c.get("listing_price_text"),
            "before": {
                "date": c.get("baseline_date"),
                "low": c.get("baseline_valuation", {}).get("estimateLow"),
                "mid": c.get("baseline_valuation", {}).get("estimateMid"),
                "high": c.get("baseline_valuation", {}).get("estimateHigh"),
                "accuracy": c.get("baseline_valuation", {}).get("accuracy"),
                "screenshot": c.get("baseline_screenshot"),
            },
            "after": {
                "date": c.get("after_date"),
                "low": c.get("after_valuation", {}).get("estimateLow"),
                "mid": c.get("after_valuation", {}).get("estimateMid"),
                "high": c.get("after_valuation", {}).get("estimateHigh"),
                "accuracy": c.get("after_valuation", {}).get("accuracy"),
                "screenshot": c.get("after_screenshot"),
            },
            "valuation_changed": c.get("valuation_changed", False),
        }
        export_data["comparisons"].append(entry)

    for t in all_tracked:
        export_data["monitored"].append({
            "address": t["address"],
            "suburb": t["suburb"],
            "status": "listed" if t.get("listing_detected") else "monitoring",
            "baseline_valuation": t.get("baseline_valuation", {}).get("estimateMid"),
            "baseline_date": t.get("baseline_date"),
        })

    export_path = EXPORT_DIR / "comparisons.json"
    with open(export_path, "w") as f:
        json.dump(export_data, f, indent=2)

    print(f"Exported {len(export_data['comparisons'])} comparisons to {export_path}")
    print(f"Total tracked: {export_data['total_tracked']}")
    print(f"Valuation changes detected: {export_data['total_with_changes']}")


def cmd_status():
    """Show current monitoring status."""
    monitor = get_monitor_collection()

    total = monitor.count_documents({})
    baselined = monitor.count_documents({"baseline_captured": True})
    listed = monitor.count_documents({"listing_detected": True})
    changed = monitor.count_documents({"valuation_changed": True})

    print("=== Valuation Monitor Status ===")
    print(f"Total tracked:       {total}")
    print(f"Baselined:           {baselined}")
    print(f"Listings detected:   {listed}")
    print(f"Valuations changed:  {changed}")

    if changed > 0:
        print("\nRecent changes:")
        for doc in monitor.find({"valuation_changed": True}).sort("listing_date", -1).limit(5):
            before = doc.get("baseline_valuation", {}).get("estimateMid", "?")
            after = doc.get("after_valuation", {}).get("estimateMid", "?")
            print(f"  {doc['address']}: {before} → {after}")


if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("Usage:")
        print("  python3 monitor.py baseline          # Capture baseline valuations")
        print("  python3 monitor.py check-listings    # Check for new listings")
        print("  python3 monitor.py export            # Export data for website")
        print("  python3 monitor.py status            # Show monitoring status")
        print('  python3 monitor.py capture-one "ADDRESS" before|after')
        sys.exit(1)

    cmd = sys.argv[1]

    if cmd == "baseline":
        cmd_baseline()
    elif cmd == "check-listings":
        cmd_check_listings()
    elif cmd == "export":
        cmd_export()
    elif cmd == "status":
        cmd_status()
    elif cmd == "capture-one":
        if len(sys.argv) < 4:
            print('Usage: python3 monitor.py capture-one "ADDRESS" before|after')
            sys.exit(1)
        cmd_capture_one(sys.argv[2], sys.argv[3])
    else:
        print(f"Unknown command: {cmd}")
        sys.exit(1)
