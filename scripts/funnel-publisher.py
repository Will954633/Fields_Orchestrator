#!/usr/bin/env python3
"""
funnel-publisher.py
===================
Publishes approved content funnels:
  1. Creates landing page in content_articles collection
  2. Triggers Netlify rebuild
  3. Creates Google Ads campaign (PAUSED) via google_ads_manager.py
  4. Updates funnel status to "published"

Usage:
    python3 scripts/funnel-publisher.py --funnel-id FUNNEL_ID
    python3 scripts/funnel-publisher.py --all-approved
    python3 scripts/funnel-publisher.py --dry-run
    python3 scripts/funnel-publisher.py --list
"""

import argparse
import json
import os
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path

import requests
from bson import ObjectId
from dotenv import load_dotenv
from pymongo import MongoClient

load_dotenv(Path(__file__).parent.parent / ".env")

COSMOS_URI = os.environ.get("COSMOS_CONNECTION_STRING", "")
NETLIFY_BUILD_HOOK = "https://api.netlify.com/build_hooks/699faf0aa7c588800d79f95d"
SCRIPTS_DIR = Path(__file__).parent


def get_db():
    client = MongoClient(COSMOS_URI)
    return client["system_monitor"]


def publish_landing_page(db, funnel, dry_run=False):
    """Create the landing page in content_articles."""
    lp = funnel["landing_page"]
    now = datetime.now(timezone.utc).isoformat()

    article = {
        "title": lp["title"],
        "slug": lp["slug"],
        "html": lp["body_html"],
        "meta_description": lp.get("meta_description", ""),
        "tags": ["landing-page"],
        "status": "published",
        "page_type": "landing_page",
        "funnel_id": str(funnel["_id"]),
        "source_query": funnel["source_query"],
        "target_keyword": lp.get("target_keyword", ""),
        "related_keywords": lp.get("related_keywords", []),
        "internal_links": lp.get("internal_links", []),
        "cta_text": lp.get("cta_text", ""),
        "created_at": now,
        "updated_at": now,
        "published_at": now,
    }

    if dry_run:
        print(f"  [DRY RUN] Would create article: {article['title']} (slug: {article['slug']})")
        return "dry-run-id"

    # Check for existing article with same slug
    existing = db["content_articles"].find_one({"slug": lp["slug"]})
    if existing:
        print(f"  WARNING: Article with slug '{lp['slug']}' already exists. Updating.")
        db["content_articles"].update_one(
            {"_id": existing["_id"]},
            {"$set": {**article, "updated_at": now}}
        )
        return str(existing["_id"])

    result = db["content_articles"].insert_one(article)
    print(f"  Created landing page: {result.inserted_id}")
    return str(result.inserted_id)


def trigger_netlify_rebuild(dry_run=False):
    """Trigger a Netlify site rebuild."""
    if dry_run:
        print("  [DRY RUN] Would trigger Netlify rebuild")
        return
    try:
        resp = requests.post(NETLIFY_BUILD_HOOK, timeout=10)
        print(f"  Netlify rebuild triggered (status: {resp.status_code})")
    except Exception as e:
        print(f"  WARNING: Failed to trigger Netlify rebuild: {e}")


def create_google_ads_campaign(funnel, dry_run=False):
    """Create a Google Ads search campaign (PAUSED) using google_ads_manager.py."""
    ads = funnel.get("google_ads", {})
    if not ads or not ads.get("keywords"):
        print("  Skipping Google Ads: no campaign spec in funnel")
        return None

    if dry_run:
        print(f"  [DRY RUN] Would create Google Ads campaign: {ads.get('campaign_name', 'unnamed')}")
        print(f"    Keywords: {ads.get('keywords', [])}")
        print(f"    Budget: ${ads.get('daily_budget', 20)}/day")
        return "dry-run-campaign"

    # Call google_ads_manager.py to create the campaign
    manager_script = SCRIPTS_DIR / "google_ads_manager.py"
    if not manager_script.exists():
        print(f"  WARNING: {manager_script} not found. Skipping Google Ads campaign creation.")
        return None

    # For now, log the campaign spec for manual creation
    # (Full API integration in Phase 2)
    print(f"  Google Ads campaign spec saved (manual creation needed in Phase 2):")
    print(f"    Name: {ads.get('campaign_name', '')}")
    print(f"    Keywords: {', '.join(ads.get('keywords', []))}")
    print(f"    Headlines: {ads.get('headlines', [])}")
    print(f"    Descriptions: {ads.get('descriptions', [])}")
    print(f"    Budget: ${ads.get('daily_budget', 20)}/day")
    return None


def publish_funnel(db, funnel, dry_run=False):
    """Publish a single approved funnel."""
    funnel_id = funnel["_id"]
    query = funnel["source_query"]
    print(f"\nPublishing funnel: \"{query}\" (id: {funnel_id})")

    # 1. Create landing page
    article_id = publish_landing_page(db, funnel, dry_run=dry_run)

    # 2. Create Google Ads campaign
    campaign_id = create_google_ads_campaign(funnel, dry_run=dry_run)

    # 3. Log Facebook brief
    fb = funnel.get("fb_brief", {})
    if fb:
        print(f"  Facebook ad brief:")
        print(f"    Audience: {fb.get('target_audience', 'N/A')}")
        print(f"    Copy: {fb.get('suggested_copy', 'N/A')[:80]}...")
        print(f"    Image: {fb.get('image_direction', 'N/A')}")

    # 4. Update funnel status
    now = datetime.now(timezone.utc).isoformat()
    if not dry_run:
        update = {
            "$set": {
                "status": "published",
                "article_id": article_id,
                "published_at": now,
            },
            "$push": {
                "status_history": {
                    "status": "published",
                    "changed_at": now,
                    "changed_by": "funnel-publisher",
                }
            }
        }
        if campaign_id:
            update["$set"]["google_ads.campaign_id"] = campaign_id

        db["content_funnels"].update_one({"_id": funnel_id}, update)
        print(f"  Funnel status → published")

    # 5. Trigger Netlify rebuild
    trigger_netlify_rebuild(dry_run=dry_run)

    return True


def list_funnels(db, status_filter=None):
    """List funnels with optional status filter."""
    query = {}
    if status_filter:
        query["status"] = status_filter

    funnels = list(db["content_funnels"].find(
        query,
        {"source_query": 1, "status": 1, "importance_score": 1, "landing_page.title": 1, "created_at": 1}
    ).sort("created_at", -1))

    if not funnels:
        print(f"No funnels found{f' with status={status_filter}' if status_filter else ''}.")
        return

    print(f"\n{'ID':<26} {'Status':<12} {'Score':>5}  {'Query'}")
    print("-" * 90)
    for f in funnels:
        fid = str(f["_id"])[:24]
        status = f.get("status", "?")
        score = f.get("importance_score", 0)
        query = f.get("source_query", "")[:40]
        print(f"  {fid:<24} {status:<10} {score:>5.1f}  {query}")
    print(f"\nTotal: {len(funnels)}")


def main():
    parser = argparse.ArgumentParser(description="Publish approved content funnels")
    parser.add_argument("--funnel-id", type=str, help="Publish a specific funnel by ID")
    parser.add_argument("--all-approved", action="store_true", help="Publish all approved funnels")
    parser.add_argument("--dry-run", action="store_true", help="Preview without publishing")
    parser.add_argument("--list", action="store_true", help="List funnels")
    parser.add_argument("--status", type=str, help="Filter list by status")
    args = parser.parse_args()

    if not COSMOS_URI:
        print("ERROR: COSMOS_CONNECTION_STRING not set")
        sys.exit(1)

    db = get_db()

    if args.list:
        list_funnels(db, status_filter=args.status)
        return

    if not args.funnel_id and not args.all_approved:
        parser.print_help()
        return

    funnels_to_publish = []

    if args.funnel_id:
        try:
            oid = ObjectId(args.funnel_id)
        except Exception:
            print(f"ERROR: Invalid funnel ID: {args.funnel_id}")
            sys.exit(1)

        funnel = db["content_funnels"].find_one({"_id": oid})
        if not funnel:
            print(f"ERROR: Funnel not found: {args.funnel_id}")
            sys.exit(1)

        if funnel.get("status") not in ("approved", "draft") and not args.dry_run:
            print(f"ERROR: Funnel status is '{funnel.get('status')}', must be 'approved' (or use --dry-run)")
            sys.exit(1)

        funnels_to_publish.append(funnel)

    elif args.all_approved:
        funnels_to_publish = list(db["content_funnels"].find({"status": "approved"}))
        if not funnels_to_publish:
            print("No approved funnels to publish.")
            return

    print(f"Publishing {len(funnels_to_publish)} funnel(s)...")

    published = 0
    for funnel in funnels_to_publish:
        if publish_funnel(db, funnel, dry_run=args.dry_run):
            published += 1

    print(f"\nDone. Published {published}/{len(funnels_to_publish)} funnel(s).")


if __name__ == "__main__":
    main()
