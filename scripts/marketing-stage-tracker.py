#!/usr/bin/env python3
"""
Marketing Stage Tracker — collects Facebook page + ads metrics and
evaluates progress against growth ladder milestones.

Run daily via cron. Updates system_monitor.marketing_stage in MongoDB.

Usage:
    python3 scripts/marketing-stage-tracker.py
    python3 scripts/marketing-stage-tracker.py --print
"""

import os
import sys
import json
import argparse
import requests
from datetime import datetime, timezone
from dotenv import load_dotenv
from pymongo import MongoClient

load_dotenv("/home/fields/Fields_Orchestrator/.env")

ADS_TOKEN = os.environ["FACEBOOK_ADS_TOKEN"]
AD_ACCOUNT_ID = os.environ["FACEBOOK_AD_ACCOUNT_ID"]
PAGE_ID = os.environ["FACEBOOK_PAGE_ID"]
API_VERSION = os.environ.get("FACEBOOK_API_VERSION", "v18.0")
BASE = f"https://graph.facebook.com/{API_VERSION}"
COSMOS_URI = os.environ["COSMOS_CONNECTION_STRING"]

# ── Stage milestones ──────────────────────────────────────────────────────

MILESTONES = {
    0: {
        "name": "Cold Start",
        "objective": "Awareness / Reach",
        "exit": {
            "page_followers": 100,
            "weekly_reach": 2000,
            "weekly_post_saves": 5,
            "posts_with_data": 20,
        },
    },
    1: {
        "name": "Credibility Building",
        "objective": "Page Likes + Engagement",
        "exit": {
            "page_followers": 300,
            "avg_post_engagements": 50,
            "page_engager_audience": 500,
            "weekly_real_comments": 5,
            "weekly_post_saves": 15,
        },
    },
    2: {
        "name": "Audience Depth + Website Traffic",
        "objective": "Traffic to warm audiences",
        "exit": {
            "page_followers": 500,
            "website_pixel_audience": 1000,
            "weekly_sessions_from_fb": 200,
            "retargeting_pool": 500,
        },
    },
    3: {
        "name": "Lead Capture",
        "objective": "Lead Generation",
        "exit": {
            "email_subscribers": 100,
            "monthly_valuation_requests": 5,
            "retargeting_audience": 1000,
            "monthly_inbound_dms": 5,
        },
    },
    4: {
        "name": "Listing Presentations",
        "objective": "Conversions — appraisal bookings",
        "exit": {
            "listing_presentations": 3,
            "signed_listings": 1,
        },
    },
}


def fb_get(path, params=None, token=None):
    p = {"access_token": token or ADS_TOKEN, **(params or {})}
    r = requests.get(f"{BASE}{path}", params=p, timeout=15)
    r.raise_for_status()
    return r.json()


def get_page_token():
    data = fb_get(f"/{PAGE_ID}", {"fields": "access_token"})
    return data["access_token"]


def collect_metrics():
    page_token = get_page_token()

    # ── Page basics ──
    page_info = fb_get(f"/{PAGE_ID}", {"fields": "followers_count,fan_count"})
    followers = page_info.get("followers_count", 0)

    # ── Page insights (last 7 days) ──
    weekly_reach = 0
    weekly_engagements = 0
    try:
        insights = fb_get(
            f"/{PAGE_ID}/insights",
            {"metric": "page_impressions_unique,page_post_engagements", "period": "week"},
            token=page_token,
        )
        for metric in insights.get("data", []):
            values = metric.get("values", [])
            latest = values[-1]["value"] if values else 0
            if metric["name"] == "page_impressions_unique":
                weekly_reach = latest
            elif metric["name"] == "page_post_engagements":
                weekly_engagements = latest
    except Exception as e:
        print(f"Warning: page insights failed: {e}")

    # ── Recent posts (last 7 days engagements) ──
    weekly_saves = 0
    weekly_comments = 0
    total_posts = 0
    total_post_engagements = 0
    try:
        posts = fb_get(
            f"/{PAGE_ID}/posts",
            {
                "fields": "created_time,likes.summary(true),comments.summary(true),shares",
                "limit": 20,
            },
            token=page_token,
        )
        from datetime import timedelta
        cutoff = datetime.now(timezone.utc) - timedelta(days=7)
        for post in posts.get("data", []):
            created = datetime.fromisoformat(post["created_time"].replace("+0000", "+00:00"))
            if created >= cutoff:
                likes = post.get("likes", {}).get("summary", {}).get("total_count", 0)
                comments = post.get("comments", {}).get("summary", {}).get("total_count", 0)
                shares = post.get("shares", {}).get("count", 0) if post.get("shares") else 0
                total_post_engagements += likes + comments + shares
                weekly_comments += comments
                total_posts += 1
    except Exception as e:
        print(f"Warning: post fetch failed: {e}")

    avg_post_engagements = round(total_post_engagements / max(total_posts, 1), 1)

    # ── All-time post count ──
    all_posts_count = 0
    try:
        all_posts = fb_get(f"/{PAGE_ID}/posts", {"fields": "id", "limit": 100}, token=page_token)
        all_posts_count = len(all_posts.get("data", []))
    except Exception:
        pass

    # ── Ads performance (last 7 days) ──
    ads_spend_7d = 0
    ads_impressions_7d = 0
    ads_clicks_7d = 0
    try:
        insights = fb_get(f"/{AD_ACCOUNT_ID}/insights", {
            "fields": "spend,impressions,clicks",
            "date_preset": "last_7d",
        })
        data = insights.get("data", [{}])
        if data:
            d = data[0]
            ads_spend_7d = float(d.get("spend", 0))
            ads_impressions_7d = int(d.get("impressions", 0))
            ads_clicks_7d = int(d.get("clicks", 0))
    except Exception as e:
        print(f"Warning: ads insights failed: {e}")

    return {
        "page_followers": followers,
        "weekly_reach": weekly_reach,
        "weekly_post_saves": weekly_saves,  # Graph API v18 doesn't expose saves directly
        "weekly_engagements": weekly_engagements,
        "avg_post_engagements": avg_post_engagements,
        "weekly_real_comments": weekly_comments,
        "posts_with_data": all_posts_count,
        "total_posts_this_week": total_posts,
        "page_engager_audience": 0,  # Needs Custom Audience API (later)
        "website_pixel_audience": 0,  # Needs pixel stats (later)
        "weekly_sessions_from_fb": 0,  # Needs Google Analytics or similar
        "retargeting_pool": 0,
        "email_subscribers": 0,  # Manual update or Ghost API
        "monthly_valuation_requests": 0,  # Manual
        "monthly_inbound_dms": 0,  # Manual
        "monthly_listing_presentations": 0,  # Manual
        "signed_listings": 0,  # Manual
        "ads_spend_7d": ads_spend_7d,
        "ads_impressions_7d": ads_impressions_7d,
        "ads_clicks_7d": ads_clicks_7d,
    }


def evaluate_stage(metrics, current_stage):
    """Check if all exit milestones for the current stage are met."""
    if current_stage not in MILESTONES:
        return {"ready_to_advance": False, "progress": {}}

    exit_criteria = MILESTONES[current_stage]["exit"]
    progress = {}
    all_met = True

    for metric_name, target in exit_criteria.items():
        current = metrics.get(metric_name, 0)
        pct = min(round((current / target) * 100, 1), 100) if target > 0 else 0
        met = current >= target
        if not met:
            all_met = False
        progress[metric_name] = {
            "current": current,
            "target": target,
            "percent": pct,
            "met": met,
        }

    return {"ready_to_advance": all_met, "progress": progress}


def save_to_mongo(metrics, stage_info):
    client = MongoClient(COSMOS_URI)
    db = client["system_monitor"]
    col = db["marketing_stage"]

    existing = col.find_one({"_id": "current"})
    current_stage = existing["stage"] if existing else 0

    evaluation = evaluate_stage(metrics, current_stage)

    doc = {
        "_id": "current",
        "stage": current_stage,
        "stage_name": MILESTONES.get(current_stage, {}).get("name", "Unknown"),
        "stage_objective": MILESTONES.get(current_stage, {}).get("objective", ""),
        "stage_entered_at": existing.get("stage_entered_at", datetime.now(timezone.utc).isoformat()) if existing else datetime.now(timezone.utc).isoformat(),
        "metrics": metrics,
        "milestones": evaluation["progress"],
        "ready_to_advance": evaluation["ready_to_advance"],
        "last_updated": datetime.now(timezone.utc).isoformat(),
    }

    col.replace_one({"_id": "current"}, doc, upsert=True)

    # Also append a daily snapshot for history
    history_doc = {
        "date": datetime.now(timezone.utc).strftime("%Y-%m-%d"),
        "stage": current_stage,
        "metrics": metrics,
        "milestones": evaluation["progress"],
    }
    db["marketing_stage_history"].replace_one(
        {"date": history_doc["date"]}, history_doc, upsert=True
    )

    client.close()
    return current_stage, evaluation


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--print", action="store_true", help="Print without saving to DB")
    args = parser.parse_args()

    print("Collecting marketing metrics...")
    metrics = collect_metrics()

    if args.print:
        print(json.dumps(metrics, indent=2))
        evaluation = evaluate_stage(metrics, 0)
        print("\n--- Stage 0 milestone progress ---")
        for name, info in evaluation["progress"].items():
            bar = "=" * int(info["percent"] / 5) + "." * (20 - int(info["percent"] / 5))
            status = "DONE" if info["met"] else f"{info['percent']}%"
            print(f"  {name}: [{bar}] {info['current']}/{info['target']} ({status})")
        if evaluation["ready_to_advance"]:
            print("\n  >>> Ready to advance to Stage 1!")
    else:
        stage, evaluation = save_to_mongo(metrics, MILESTONES)
        print(f"Stage {stage}: {MILESTONES[stage]['name']}")
        for name, info in evaluation["progress"].items():
            status = "DONE" if info["met"] else f"{info['percent']}%"
            print(f"  {name}: {info['current']}/{info['target']} ({status})")
        if evaluation["ready_to_advance"]:
            print(f"\n  >>> All milestones met — ready to advance to Stage {stage + 1}!")
        print(f"\nSaved to system_monitor.marketing_stage")


if __name__ == "__main__":
    main()
