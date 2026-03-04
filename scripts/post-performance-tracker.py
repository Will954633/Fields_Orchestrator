#!/usr/bin/env python3
"""
Post Performance Tracker — fetches engagement metrics for recent Facebook posts
and writes verdicts to institutional memory.

Runs every 6 hours via cron. Checks posts that haven't been finalized yet.
- Posts >24h old: fetch and save engagement metrics
- Posts >72h old: write a verdict to fb_ad_tests (institutional memory) and mark finalized

Usage:
    python3 scripts/post-performance-tracker.py              # Run tracker
    python3 scripts/post-performance-tracker.py --dry-run     # Show what would happen
"""

import os
import sys
import argparse
import requests
from datetime import datetime, timezone, timedelta
from dateutil import parser as dateparser
from dotenv import load_dotenv
from pymongo import MongoClient

load_dotenv("/home/fields/Fields_Orchestrator/.env")

ADS_TOKEN = os.environ["FACEBOOK_ADS_TOKEN"]
PAGE_ID = os.environ["FACEBOOK_PAGE_ID"]
API_VERSION = os.environ.get("FACEBOOK_API_VERSION", "v18.0")
BASE = f"https://graph.facebook.com/{API_VERSION}"
COSMOS_URI = os.environ["COSMOS_CONNECTION_STRING"]


def fb_get(path, params=None, token=None):
    p = {"access_token": token or ADS_TOKEN, **(params or {})}
    r = requests.get(f"{BASE}{path}", params=p, timeout=15)
    r.raise_for_status()
    return r.json()


def get_page_token():
    data = fb_get(f"/{PAGE_ID}", {"fields": "access_token"})
    return data["access_token"]


def get_unfinalized_posts():
    """Get posts that haven't been finalized yet."""
    client = MongoClient(COSMOS_URI)
    sm = client["system_monitor"]
    posts = list(sm["fb_page_posts"].find(
        {"finalized": {"$ne": True}}
    ).sort("_id", -1).limit(50))
    client.close()
    return posts


def fetch_post_engagement(post_id, page_token):
    """Fetch engagement metrics for a single post."""
    try:
        data = fb_get(
            f"/{post_id}",
            {"fields": "likes.summary(true),comments.summary(true),shares,created_time"},
            token=page_token,
        )
        likes = data.get("likes", {}).get("summary", {}).get("total_count", 0)
        comments = data.get("comments", {}).get("summary", {}).get("total_count", 0)
        shares = data.get("shares", {}).get("count", 0)
        return {
            "likes": likes,
            "comments": comments,
            "shares": shares,
            "total_engagements": likes + comments + shares,
        }
    except requests.exceptions.HTTPError as e:
        # Post might have been deleted or is not accessible
        return {"error": str(e), "likes": 0, "comments": 0, "shares": 0, "total_engagements": 0}
    except Exception as e:
        return {"error": str(e), "likes": 0, "comments": 0, "shares": 0, "total_engagements": 0}


def update_post_metrics(post_doc_id, metrics):
    """Write engagement metrics back to the post document."""
    client = MongoClient(COSMOS_URI)
    sm = client["system_monitor"]
    sm["fb_page_posts"].update_one(
        {"_id": post_doc_id},
        {"$set": {
            "engagement": metrics,
            "last_checked": datetime.now(timezone.utc).isoformat(),
        }}
    )
    client.close()


def write_verdict(post, metrics):
    """Write a verdict to institutional memory (fb_ad_tests)."""
    total = metrics.get("total_engagements", 0)

    # Determine verdict based on engagement
    if total >= 10:
        verdict = "strong"
    elif total >= 3:
        verdict = "moderate"
    else:
        verdict = "weak"

    doc = {
        "type": "post_performance",
        "post_id": post.get("post_id", ""),
        "message_preview": post.get("message", "")[:150],
        "template_type": post.get("template_type", "unknown"),
        "content_type": post.get("content_type", "text"),
        "source": post.get("source", "unknown"),
        "posted_at": post.get("posted_at", ""),
        "metrics": {
            "likes": metrics.get("likes", 0),
            "comments": metrics.get("comments", 0),
            "shares": metrics.get("shares", 0),
            "total_engagements": total,
        },
        "verdict": verdict,
        "finalized_at": datetime.now(timezone.utc).isoformat(),
    }

    client = MongoClient(COSMOS_URI)
    sm = client["system_monitor"]
    sm["fb_ad_tests"].insert_one(doc)
    client.close()

    return verdict


def finalize_post(post_doc_id):
    """Mark a post as finalized so we don't check it again."""
    client = MongoClient(COSMOS_URI)
    sm = client["system_monitor"]
    sm["fb_page_posts"].update_one(
        {"_id": post_doc_id},
        {"$set": {"finalized": True}}
    )
    client.close()


def parse_post_time(post):
    """Parse the posted_at field, handling various formats."""
    posted_at = post.get("posted_at", "")
    if not posted_at:
        return None
    try:
        return dateparser.parse(posted_at)
    except Exception:
        return None


def main():
    ap = argparse.ArgumentParser(description="Track Facebook post performance")
    ap.add_argument("--dry-run", action="store_true", help="Show what would happen")
    args = ap.parse_args()

    print(f"[{datetime.now(timezone.utc).isoformat()}] Post Performance Tracker starting...")

    posts = get_unfinalized_posts()
    if not posts:
        print("No unfinalized posts to check.")
        return

    print(f"Found {len(posts)} unfinalized post(s)")

    page_token = get_page_token()
    now = datetime.now(timezone.utc)

    checked = 0
    finalized_count = 0

    for post in posts:
        post_id = post.get("post_id", "")
        posted_at = parse_post_time(post)
        message_preview = post.get("message", "")[:60]

        if not post_id:
            print(f"  Skipping post with no post_id: {post.get('_id')}")
            continue

        if not posted_at:
            print(f"  Skipping post with unparseable date: {post_id}")
            continue

        # Make posted_at timezone-aware if it isn't
        if posted_at.tzinfo is None:
            posted_at = posted_at.replace(tzinfo=timezone.utc)

        age_hours = (now - posted_at).total_seconds() / 3600

        if age_hours < 24:
            print(f"  [{post_id}] Too recent ({age_hours:.1f}h) — skipping")
            continue

        print(f"  [{post_id}] Age: {age_hours:.1f}h — \"{message_preview}...\"")

        if args.dry_run:
            if age_hours >= 72:
                print(f"    -> Would finalize (>72h)")
            else:
                print(f"    -> Would fetch metrics")
            continue

        # Fetch engagement
        metrics = fetch_post_engagement(post_id, page_token)
        checked += 1

        if metrics.get("error"):
            print(f"    -> Error fetching: {metrics['error'][:80]}")

        print(f"    -> Likes: {metrics['likes']}, Comments: {metrics['comments']}, Shares: {metrics['shares']}")

        # Update metrics on the post doc
        update_post_metrics(post["_id"], metrics)

        # If >72h, finalize with verdict
        if age_hours >= 72:
            verdict = write_verdict(post, metrics)
            finalize_post(post["_id"])
            finalized_count += 1
            print(f"    -> Verdict: {verdict.upper()} — written to institutional memory")

    if args.dry_run:
        print("\n(Dry run — nothing written)")
    else:
        print(f"\nDone. Checked: {checked}, Finalized: {finalized_count}")


if __name__ == "__main__":
    main()
