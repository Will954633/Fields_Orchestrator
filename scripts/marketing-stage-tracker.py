#!/usr/bin/env python3
"""
Marketing Stage Tracker — 3-stage Facebook marketing framework.

Stages:
  1. Audience Discovery  — find content that works (CPM, CTR, cost/engagement, frequency)
  2. Audience Building    — grow local audience (engagers, video viewers, website visitors, followers)
  3. Seller Conversion    — get listings (funnel: engaged → visitors → enquiries → appointments → listing)

Run daily via cron. Updates system_monitor.marketing_stage in MongoDB.

Usage:
    python3 scripts/marketing-stage-tracker.py
    python3 scripts/marketing-stage-tracker.py --print
"""

import os
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

# ── 3-Stage Framework ────────────────────────────────────────────────────

STAGES = {
    1: {
        "name": "Audience Discovery",
        "goal": "Find content that people respond to",
        "duration": "First 2-4 weeks",
    },
    2: {
        "name": "Audience Building",
        "goal": "Build a local audience",
        "duration": "Weeks 4-12",
    },
    3: {
        "name": "Seller Conversion",
        "goal": "Get listings",
        "duration": "Ongoing",
    },
}

# Health metric ranges for Stage 1
HEALTH_RANGES = {
    "cpm_7d": {
        "label": "CPM",
        "unit": "$",
        "excellent": (None, 6),       # < $6
        "normal": (6, 12),            # $6-$12
        "problem": (15, None),        # > $15
    },
    "ctr_7d": {
        "label": "CTR",
        "unit": "%",
        "excellent": (2, None),       # > 2%
        "normal": (0.5, 2),           # 0.5-2%
        "problem": (None, 0.5),       # < 0.5%
    },
    "cost_per_engagement": {
        "label": "Cost per Engagement",
        "unit": "$",
        "excellent": (0.02, 0.10),    # $0.02-$0.10
        "normal": (0.10, 0.50),       # $0.10-$0.50
        "problem": (0.50, None),      # > $0.50
    },
    "frequency_7d": {
        "label": "Frequency",
        "unit": "x",
        "excellent": (2, 4),          # 2-4x
        "normal": (1, 2),             # 1-2x (building up)
        "problem": (None, 1),         # < 1 or no data
    },
}

# Audience targets for Stage 2
AUDIENCE_TARGETS = {
    "page_engager_audience": {"target": 1000, "label": "Page Engagement Audience"},
    "video_viewers": {"target": 500, "label": "Video Viewers"},
    "website_visitors": {"target": 500, "label": "Website Visitors"},
    "page_followers": {"target": 200, "label": "Followers"},
}

# Conversion funnel for Stage 3
FUNNEL_TEMPLATE = [
    {"key": "engaged_locals", "label": "Engaged locals", "target": 1500},
    {"key": "website_visitors", "label": "Website visitors", "target": 50},
    {"key": "valuation_enquiries", "label": "Valuation enquiries", "target": 10},
    {"key": "listing_appointments", "label": "Listing appointments", "target": 2},
    {"key": "listings", "label": "Listings", "target": 1},
]

# Milestone roadmap
MILESTONE_ROADMAP = [
    {"month": "1", "target": "CTR > 1%, Cost per engagement < $0.20"},
    {"month": "2", "target": "1,000 engaged locals"},
    {"month": "3-4", "target": "3-5 appraisal enquiries"},
    {"month": "4-6", "target": "First listing"},
]

# Success benchmarks (what a mature presence looks like)
SUCCESS_BENCHMARKS = {
    "followers": 1200,
    "engagement_audience": 4000,
    "video_viewers": 2000,
    "website_visitors": 1000,
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
    """Collect all metrics from Meta APIs and existing MongoDB data."""
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

    # ── Video views (last 7 days) ──
    video_viewers = 0
    try:
        vid_insights = fb_get(
            f"/{PAGE_ID}/insights",
            {"metric": "page_video_views", "period": "week"},
            token=page_token,
        )
        for metric in vid_insights.get("data", []):
            values = metric.get("values", [])
            if values:
                video_viewers = values[-1]["value"]
    except Exception as e:
        print(f"Warning: video views fetch failed (may not have videos): {e}")

    # ── Recent posts (last 7 days engagement detail) ──
    weekly_comments = 0
    total_posts = 0
    total_post_engagements = 0
    try:
        from datetime import timedelta
        posts = fb_get(
            f"/{PAGE_ID}/posts",
            {"fields": "created_time,likes.summary(true),comments.summary(true),shares", "limit": 20},
            token=page_token,
        )
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

    # ── Cross-read ads data from facebook_ads collection (avoid duplicate API calls) ──
    cpm_7d = 0
    ctr_7d = 0
    frequency_7d = 0
    cost_per_engagement = 0
    ads_spend_7d = 0
    ads_impressions_7d = 0
    ads_clicks_7d = 0
    try:
        client = MongoClient(COSMOS_URI)
        fb_doc = client["system_monitor"]["facebook_ads"].find_one({"_id": "latest"})
        client.close()
        if fb_doc:
            last7 = fb_doc.get("last_7d", {})
            cpm_7d = last7.get("cpm", 0)
            ctr_7d = last7.get("ctr", 0)
            frequency_7d = last7.get("frequency", 0)
            cost_per_engagement = last7.get("cost_per_engagement") or 0
            ads_spend_7d = last7.get("spend_aud", 0)
            ads_impressions_7d = last7.get("impressions", 0)
            ads_clicks_7d = last7.get("clicks", 0)
    except Exception as e:
        print(f"Warning: couldn't read facebook_ads from MongoDB: {e}")
        # Fallback: fetch directly from Meta API
        try:
            insights = fb_get(f"/{AD_ACCOUNT_ID}/insights", {
                "fields": "spend,impressions,clicks,cpm,ctr,frequency,actions",
                "date_preset": "last_7d",
            })
            data = insights.get("data", [{}])
            if data:
                d = data[0]
                ads_spend_7d = float(d.get("spend", 0))
                ads_impressions_7d = int(d.get("impressions", 0))
                ads_clicks_7d = int(d.get("clicks", 0))
                cpm_7d = float(d.get("cpm", 0))
                ctr_7d = float(d.get("ctr", 0))
                frequency_7d = float(d.get("frequency", 0))
                # Calculate cost per engagement from actions
                for a in d.get("actions", []):
                    if a.get("action_type") == "page_engagement":
                        eng = int(a.get("value", 0))
                        if eng > 0:
                            cost_per_engagement = round(ads_spend_7d / eng, 4)
        except Exception as e2:
            print(f"Warning: ads fallback failed: {e2}")

    # ── Page engagement audience size (Custom Audience) ──
    page_engager_audience = 0
    # TODO: read from Custom Audience API when audience IDs are configured

    # ── Website visitors (pixel audience) ──
    website_visitors = 0
    # TODO: read from Custom Audience API when audience ID is configured

    return {
        # Stage 1 metrics
        "cpm_7d": round(cpm_7d, 2),
        "ctr_7d": round(ctr_7d, 2),
        "cost_per_engagement": round(cost_per_engagement, 4) if cost_per_engagement else 0,
        "frequency_7d": round(frequency_7d, 2),
        # Stage 2 metrics
        "page_followers": followers,
        "page_engager_audience": page_engager_audience,
        "video_viewers": video_viewers,
        "website_visitors": website_visitors,
        # Stage 3 / funnel metrics (manual tracking)
        "engaged_locals": page_engager_audience,  # Same as engagement audience
        "valuation_enquiries": 0,  # Manual
        "listing_appointments": 0,  # Manual
        "listings": 0,  # Manual
        # Supporting metrics
        "weekly_reach": weekly_reach,
        "weekly_engagements": weekly_engagements,
        "avg_post_engagements": avg_post_engagements,
        "weekly_real_comments": weekly_comments,
        "posts_with_data": all_posts_count,
        "total_posts_this_week": total_posts,
        "ads_spend_7d": ads_spend_7d,
        "ads_impressions_7d": ads_impressions_7d,
        "ads_clicks_7d": ads_clicks_7d,
    }


def evaluate_health(value, ranges):
    """Evaluate a Stage 1 metric against its health ranges. Returns 'excellent', 'normal', or 'problem'."""
    if value is None or value == 0:
        return "problem"

    lo, hi = ranges.get("excellent", (None, None))
    if lo is not None and hi is not None and lo <= value <= hi:
        return "excellent"
    if lo is not None and hi is None and value >= lo:
        return "excellent"
    if lo is None and hi is not None and value < hi:
        return "excellent"

    lo, hi = ranges.get("normal", (None, None))
    if lo is not None and hi is not None and lo <= value <= hi:
        return "normal"
    if lo is not None and hi is None and value >= lo:
        return "normal"
    if lo is None and hi is not None and value < hi:
        return "normal"

    return "problem"


def build_stage_document(metrics, current_stage):
    """Build the full marketing stage document for MongoDB."""
    stage = STAGES.get(current_stage, STAGES[1])

    # ── Stage 1: Health indicators ──
    health = {}
    for key, ranges in HEALTH_RANGES.items():
        val = metrics.get(key, 0)
        health[key] = {
            "value": val,
            "status": evaluate_health(val, ranges),
            "label": ranges["label"],
            "unit": ranges["unit"],
        }

    # ── Stage 2: Audience progress ──
    audience_progress = {}
    for key, info in AUDIENCE_TARGETS.items():
        current = metrics.get(key, 0)
        target = info["target"]
        audience_progress[key] = {
            "current": current,
            "target": target,
            "percent": min(round((current / target) * 100, 1), 100) if target > 0 else 0,
            "label": info["label"],
        }

    # ── Stage 3: Conversion funnel ──
    funnel = []
    for step in FUNNEL_TEMPLATE:
        current = metrics.get(step["key"], 0)
        funnel.append({
            "key": step["key"],
            "label": step["label"],
            "target": step["target"],
            "current": current,
        })

    # ── Milestone roadmap — check which are met ──
    milestone_roadmap = []
    m1_met = metrics.get("ctr_7d", 0) >= 1.0 and (metrics.get("cost_per_engagement", 0) > 0 and metrics.get("cost_per_engagement", 999) <= 0.20)
    m2_met = metrics.get("engaged_locals", 0) >= 1000
    m3_met = metrics.get("valuation_enquiries", 0) >= 3
    m4_met = metrics.get("listings", 0) >= 1

    for i, m in enumerate(MILESTONE_ROADMAP):
        met = [m1_met, m2_met, m3_met, m4_met][i]
        milestone_roadmap.append({**m, "met": met})

    # ── Success benchmarks ──
    success_benchmarks = {}
    benchmark_metric_map = {
        "followers": "page_followers",
        "engagement_audience": "page_engager_audience",
        "video_viewers": "video_viewers",
        "website_visitors": "website_visitors",
    }
    for label, target in SUCCESS_BENCHMARKS.items():
        metric_key = benchmark_metric_map[label]
        success_benchmarks[label] = {
            "target": target,
            "current": metrics.get(metric_key, 0),
        }

    # ── Cost per engaged local (hero metric) ──
    cpe = metrics.get("cost_per_engagement", 0)

    return {
        "_id": "current",
        "stage": current_stage,
        "stage_name": stage["name"],
        "stage_goal": stage["goal"],
        "stage_duration": stage["duration"],
        "metrics": metrics,
        "health": health,
        "audience_progress": audience_progress,
        "funnel": funnel,
        "milestone_roadmap": milestone_roadmap,
        "success_benchmarks": success_benchmarks,
        "cost_per_engaged_local": cpe,
        "last_updated": datetime.now(timezone.utc).isoformat(),
    }


def save_to_mongo(metrics):
    client = MongoClient(COSMOS_URI)
    db = client["system_monitor"]
    col = db["marketing_stage"]

    existing = col.find_one({"_id": "current"})
    current_stage = existing["stage"] if existing else 1
    # Migrate from old 0-based 5-stage system to new 1-based 3-stage system
    if current_stage not in STAGES:
        current_stage = 1

    doc = build_stage_document(metrics, current_stage)
    col.replace_one({"_id": "current"}, doc, upsert=True)

    # Daily history snapshot
    today_str = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    history_doc = {
        "date": today_str,
        "stage": current_stage,
        "metrics": metrics,
        "health": doc["health"],
    }
    db["marketing_stage_history"].replace_one(
        {"date": today_str}, history_doc, upsert=True
    )

    client.close()
    return current_stage, doc


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--print", action="store_true", help="Print without saving to DB")
    args = parser.parse_args()

    print("Collecting marketing metrics...")
    metrics = collect_metrics()

    if args.print:
        doc = build_stage_document(metrics, 1)
        del doc["_id"]
        print(json.dumps(doc, indent=2, default=str))

        print("\n--- Stage 1: Health Indicators ---")
        for key, h in doc["health"].items():
            status_icon = {"excellent": "++", "normal": "ok", "problem": "!!"}[h["status"]]
            print(f"  [{status_icon}] {h['label']}: {h['unit']}{h['value']} ({h['status']})")

        print("\n--- Stage 2: Audience Progress ---")
        for key, a in doc["audience_progress"].items():
            bar = "=" * int(a["percent"] / 5) + "." * (20 - int(a["percent"] / 5))
            print(f"  {a['label']}: [{bar}] {a['current']}/{a['target']} ({a['percent']}%)")

        print(f"\n  Hero metric — Cost per engaged local: ${doc['cost_per_engaged_local']}")
    else:
        stage, doc = save_to_mongo(metrics)
        stage_info = STAGES[stage]
        print(f"Stage {stage}: {stage_info['name']} — {stage_info['goal']}")

        print("\n  Health:")
        for key, h in doc["health"].items():
            status_icon = {"excellent": "++", "normal": "ok", "problem": "!!"}[h["status"]]
            print(f"    [{status_icon}] {h['label']}: {h['unit']}{h['value']}")

        print(f"\n  Cost per engaged local: ${doc['cost_per_engaged_local']}")
        print(f"\nSaved to system_monitor.marketing_stage")


if __name__ == "__main__":
    main()
