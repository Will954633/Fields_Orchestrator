#!/usr/bin/env python3
"""
Facebook Metrics Collector v2 — Granular per-ad daily performance tracking.

Replaces facebook-ads-insights.py with:
  1. Per-ad DAILY metrics (not just 7d aggregates)
  2. Full creative details (not truncated)
  3. Demographic breakdowns (age × gender) per ad
  4. Placement breakdowns (platform × position) per ad
  5. Unified ad_profiles with lifecycle events
  6. 90-day retention on all historical data
  7. Backward-compatible facebook_ads "latest" snapshot

Collections written:
  - ad_daily_metrics   : one doc per ad per day (90-day retention)
  - ad_profiles        : one doc per ad (creative, lifecycle, aggregates)
  - ad_demographics    : one doc per ad per 7d window (age × gender)
  - ad_placements      : one doc per ad per 7d window (platform × position)
  - facebook_ads       : backward-compatible "latest" snapshot
  - facebook_ads_history : backward-compatible daily snapshot (90-day retention)

Usage:
    python3 scripts/fb-metrics-collector.py                # Full collection run
    python3 scripts/fb-metrics-collector.py --quick        # Skip demographics/placements
    python3 scripts/fb-metrics-collector.py --print        # Print without saving
    python3 scripts/fb-metrics-collector.py --dry-run      # Show what would be collected
"""

import os
import sys
import json
import time
import argparse
import requests
import traceback
from datetime import datetime, timezone, timedelta
from dotenv import load_dotenv
from pymongo import MongoClient, UpdateOne
from pymongo.errors import BulkWriteError

load_dotenv("/home/fields/Fields_Orchestrator/.env")

TOKEN = os.environ["FACEBOOK_ADS_TOKEN"]
AD_ACCOUNT_ID = os.environ["FACEBOOK_AD_ACCOUNT_ID"]
PAGE_ID = os.environ.get("FACEBOOK_PAGE_ID", "")
API_VERSION = os.environ.get("FACEBOOK_API_VERSION", "v18.0")
BASE = f"https://graph.facebook.com/{API_VERSION}"
COSMOS_URI = os.environ["COSMOS_CONNECTION_STRING"]

RETENTION_DAYS = 90


# ---------------------------------------------------------------------------
# Facebook API helpers
# ---------------------------------------------------------------------------

def fb_get(path, params=None):
    """GET request to Facebook Graph API with automatic pagination."""
    p = {"access_token": TOKEN, **(params or {})}
    r = requests.get(f"{BASE}{path}", params=p, timeout=30)
    r.raise_for_status()
    return r.json()


def fb_get_all(path, params=None):
    """GET with pagination — follows 'next' links to get all results."""
    p = {"access_token": TOKEN, **(params or {})}
    results = []
    url = f"{BASE}{path}"
    while url:
        r = requests.get(url, params=p, timeout=30)
        r.raise_for_status()
        data = r.json()
        results.extend(data.get("data", []))
        url = data.get("paging", {}).get("next")
        p = {}  # params already in the 'next' URL
    return results


def get_action_value(actions, action_type):
    """Extract a value from Facebook's actions array."""
    for a in (actions or []):
        if a.get("action_type") == action_type:
            return a.get("value", "0")
    return "0"


# ---------------------------------------------------------------------------
# Data fetchers
# ---------------------------------------------------------------------------

def fetch_account_insights(date_preset="last_7d"):
    """Account-level aggregates."""
    fields = ("impressions,reach,clicks,spend,ctr,cpc,cpm,frequency,"
              "actions,cost_per_action_type")
    data = fb_get(f"/{AD_ACCOUNT_ID}/insights", {
        "fields": fields,
        "date_preset": date_preset,
        "level": "account",
    })
    return data.get("data", [{}])[0]


def fetch_account_daily(days=14):
    """Account-level daily spend/impressions/clicks for sparkline."""
    data = fb_get(f"/{AD_ACCOUNT_ID}/insights", {
        "fields": "spend,impressions,clicks",
        "date_preset": f"last_{days}d",
        "time_increment": 1,
        "level": "account",
    })
    return data.get("data", [])


def fetch_campaigns():
    """All campaigns with budget info."""
    data = fb_get(f"/{AD_ACCOUNT_ID}/campaigns", {
        "fields": "name,status,objective,daily_budget,lifetime_budget",
        "limit": 50,
    })
    return data.get("data", [])


def fetch_ads_metadata():
    """All ads with full creative details and campaign/adset info."""
    data = fb_get_all(f"/{AD_ACCOUNT_ID}/ads", {
        "fields": ("name,status,effective_status,campaign_id,adset_id,"
                   "creative{id,body,title,thumbnail_url,image_url,image_hash,"
                   "link_url,call_to_action_type,object_story_spec},"
                   "campaign{name,objective,status},"
                   "adset{name,status,targeting},"
                   "created_time,updated_time"),
        "limit": 100,
        "filtering": json.dumps([{
            "field": "effective_status",
            "operator": "IN",
            "value": ["ACTIVE", "PAUSED", "CAMPAIGN_PAUSED",
                      "ADSET_PAUSED", "PENDING_REVIEW", "WITH_ISSUES"],
        }]),
    })
    return data


def fetch_ad_daily_insights(days=14):
    """Per-ad, per-day metrics for the last N days."""
    fields = ("ad_id,ad_name,impressions,reach,clicks,spend,ctr,cpc,cpm,"
              "frequency,actions,cost_per_action_type")
    results = fb_get_all(f"/{AD_ACCOUNT_ID}/insights", {
        "fields": fields,
        "date_preset": f"last_{days}d",
        "time_increment": 1,
        "level": "ad",
        "limit": 500,
    })
    return results


def fetch_ad_lifetime_insights():
    """Per-ad lifetime metrics (all-time aggregate)."""
    fields = ("ad_id,ad_name,impressions,reach,clicks,spend,ctr,cpc,cpm,"
              "frequency,actions,cost_per_action_type")
    results = fb_get_all(f"/{AD_ACCOUNT_ID}/insights", {
        "fields": fields,
        "date_preset": "maximum",
        "level": "ad",
        "limit": 500,
    })
    return results


def fetch_ad_30d_insights():
    """Per-ad last 30d metrics."""
    fields = ("ad_id,ad_name,impressions,reach,clicks,spend,ctr,cpc,cpm,"
              "frequency,actions,cost_per_action_type")
    results = fb_get_all(f"/{AD_ACCOUNT_ID}/insights", {
        "fields": fields,
        "date_preset": "last_30d",
        "level": "ad",
        "limit": 500,
    })
    return results


def parse_aggregate_row(row):
    """Parse a non-daily insight row into a clean dict."""
    actions = row.get("actions", [])
    cost_per = row.get("cost_per_action_type", [])
    spend = float(row.get("spend", 0))
    impressions = int(row.get("impressions", 0))
    clicks = int(row.get("clicks", 0))
    link_clicks = int(get_action_value(actions, "link_click"))
    return {
        "ad_id": row.get("ad_id", ""),
        "impressions": impressions,
        "reach": int(row.get("reach", 0)),
        "clicks": clicks,
        "spend_aud": round(spend, 2),
        "ctr": round(float(row.get("ctr", 0)), 4),
        "cpc_aud": round(float(row.get("cpc", 0)), 4) if row.get("cpc") else None,
        "cpm_aud": round(float(row.get("cpm", 0)), 2) if row.get("cpm") else None,
        "frequency": round(float(row.get("frequency", 0)), 4),
        "link_clicks": link_clicks,
        "landing_page_views": int(get_action_value(actions, "landing_page_view")),
        "view_content": int(get_action_value(actions, "view_content")),
        "post_engagement": int(get_action_value(actions, "post_engagement")),
        "page_engagement": int(get_action_value(actions, "page_engagement")),
        "video_views": int(get_action_value(actions, "video_view")),
        "cost_per_link_click": (
            round(spend / link_clicks, 4) if link_clicks > 0 else None
        ),
    }


def fetch_ad_demographics():
    """Age × gender breakdown per ad (last 7d aggregate)."""
    fields = "ad_id,ad_name,impressions,reach,clicks,spend,ctr,actions"
    results = fb_get_all(f"/{AD_ACCOUNT_ID}/insights", {
        "fields": fields,
        "date_preset": "last_7d",
        "level": "ad",
        "breakdowns": "age,gender",
        "limit": 500,
    })
    return results


def fetch_ad_placements():
    """Platform × position breakdown per ad (last 7d aggregate)."""
    fields = "ad_id,ad_name,impressions,reach,clicks,spend,ctr,actions"
    results = fb_get_all(f"/{AD_ACCOUNT_ID}/insights", {
        "fields": fields,
        "date_preset": "last_7d",
        "level": "ad",
        "breakdowns": "publisher_platform,platform_position",
        "limit": 500,
    })
    return results


# ---------------------------------------------------------------------------
# Data transformation
# ---------------------------------------------------------------------------

def parse_daily_row(row):
    """Parse a per-ad daily insights row into a clean dict."""
    actions = row.get("actions", [])
    cost_per = row.get("cost_per_action_type", [])
    return {
        "ad_id": row.get("ad_id", ""),
        "ad_name": row.get("ad_name", ""),
        "date": row.get("date_start", ""),
        "impressions": int(row.get("impressions", 0)),
        "reach": int(row.get("reach", 0)),
        "clicks": int(row.get("clicks", 0)),
        "spend_aud": round(float(row.get("spend", 0)), 2),
        "ctr": round(float(row.get("ctr", 0)), 4),
        "cpc": round(float(row.get("cpc", 0)), 4) if row.get("cpc") else None,
        "cpm": round(float(row.get("cpm", 0)), 2) if row.get("cpm") else None,
        "frequency": round(float(row.get("frequency", 0)), 4),
        "link_clicks": int(get_action_value(actions, "link_click")),
        "landing_page_views": int(get_action_value(actions, "landing_page_view")),
        "view_content": int(get_action_value(actions, "view_content")),
        "post_engagement": int(get_action_value(actions, "post_engagement")),
        "page_engagement": int(get_action_value(actions, "page_engagement")),
        "video_views": int(get_action_value(actions, "video_view")),
        "cost_per_view_content": (
            round(float(get_action_value(cost_per, "view_content")), 4)
            if get_action_value(cost_per, "view_content") != "0" else None
        ),
        "cost_per_link_click": (
            round(float(get_action_value(cost_per, "link_click")), 4)
            if get_action_value(cost_per, "link_click") != "0" else None
        ),
    }


def build_ad_profile(ad_meta, daily_rows, demo_rows, placement_rows,
                     agg_30d=None, agg_lifetime=None):
    """Build a unified ad profile document from all data sources."""
    ad_id = ad_meta.get("id", "")
    creative = ad_meta.get("creative", {})
    campaign = ad_meta.get("campaign", {})
    adset = ad_meta.get("adset", {})
    story_spec = creative.get("object_story_spec", {})
    link_data = story_spec.get("link_data", {})

    # Full creative body — try multiple sources
    video_data = story_spec.get("video_data", {})
    full_body = (creative.get("body")
                 or link_data.get("message")
                 or video_data.get("message")
                 or story_spec.get("text_data", {}).get("message")
                 or "")

    # Detect catalog/dynamic ads (OSS has page_id but no link_data/video_data)
    is_catalog_ad = (not full_body
                     and "page_id" in story_spec
                     and not link_data
                     and not video_data)

    # --- Creative classification ---
    ad_name = ad_meta.get("name", "")
    campaign_name = campaign.get("name", "")

    # Content type classification based on campaign/ad name patterns
    content_type = "unknown"
    if "watch this sale" in campaign_name.lower():
        content_type = "property_spotlight"
    elif "how it sold" in campaign_name.lower():
        content_type = "sold_analysis"
    elif "is now a good time" in campaign_name.lower() or "is now a good time" in ad_name.lower():
        content_type = "market_timing"
    elif "analyst" in campaign_name.lower():
        content_type = "market_analysis"
    elif "photography" in campaign_name.lower() or "photography" in ad_name.lower():
        content_type = "brand_photography"
    elif "page like" in campaign_name.lower() or "property data" in campaign_name.lower():
        content_type = "data_post"
    elif "awareness" in campaign.get("objective", "").lower():
        content_type = "awareness"
    elif "traffic" in campaign.get("objective", "").lower():
        content_type = "traffic"

    # Text style classification
    text_style = "none"
    if full_body:
        body_lower = full_body.lower()
        if any(w in body_lower for w in ["$", "median", "price", "quartile", "%"]):
            text_style = "data_driven"
        elif any(w in body_lower for w in ["question", "?", "what does", "how much"]):
            text_style = "question_hook"
        elif any(w in body_lower for w in ["bought", "sold", "paid", "asking"]):
            text_style = "transaction_narrative"
        else:
            text_style = "editorial"
    elif is_catalog_ad:
        text_style = "dynamic_catalog"

    # Extract CTA
    cta = (creative.get("call_to_action_type") or
           link_data.get("call_to_action", {}).get("type", ""))

    # Extract image URL (try multiple sources)
    image_url = (creative.get("image_url") or
                 link_data.get("picture") or
                 creative.get("thumbnail_url") or "")

    # Link URL
    link_url = (creative.get("link_url") or
                link_data.get("link") or "")

    # Determine ad format from story spec
    ad_format = "unknown"
    if "video_data" in story_spec:
        ad_format = "video"
    elif link_data.get("child_attachments"):
        ad_format = "carousel"
    elif link_data or image_url:
        ad_format = "single_image"

    # Aggregate daily metrics for last 7d and last 14d
    agg_7d = aggregate_daily(daily_rows, days=7)
    agg_14d = aggregate_daily(daily_rows, days=14)

    # Trend: compare last 7d vs previous 7d
    recent_7d = [r for r in daily_rows if is_within_days(r["date"], 7)]
    prev_7d = [r for r in daily_rows if is_within_days(r["date"], 14)
               and not is_within_days(r["date"], 7)]
    trend = compute_trend(recent_7d, prev_7d)

    # Demographics summary
    demo_summary = summarize_demographics(demo_rows)

    # Placement summary
    placement_summary = summarize_placements(placement_rows)

    # Extract targeting from adset
    targeting_raw = adset.get("targeting", {})
    targeting = {}
    if targeting_raw:
        targeting = {
            "age_min": targeting_raw.get("age_min"),
            "age_max": targeting_raw.get("age_max"),
            "geo_locations": targeting_raw.get("geo_locations", {}),
            "custom_audiences": [
                {"id": ca.get("id", ""), "name": ca.get("name", "")}
                for ca in targeting_raw.get("custom_audiences", [])
            ],
            "excluded_custom_audiences": [
                {"id": ca.get("id", ""), "name": ca.get("name", "")}
                for ca in targeting_raw.get("excluded_custom_audiences", [])
            ],
            "targeting_automation": targeting_raw.get("targeting_automation"),
        }

    return {
        "_id": ad_id,
        "ad_id": ad_id,
        "name": ad_meta.get("name", ""),
        "status": ad_meta.get("status", ""),
        "effective_status": ad_meta.get("effective_status", ""),
        "created_time": ad_meta.get("created_time", ""),
        "updated_time": ad_meta.get("updated_time", ""),
        # Campaign & adset
        "campaign_id": ad_meta.get("campaign_id", ""),
        "campaign_name": campaign.get("name", ""),
        "campaign_objective": campaign.get("objective", ""),
        "campaign_status": campaign.get("status", ""),
        "adset_id": ad_meta.get("adset_id", ""),
        "adset_name": adset.get("name", ""),
        "adset_status": adset.get("status", ""),
        # Targeting (audiences, geo, age range)
        "targeting": targeting,
        # Creative details (FULL, not truncated)
        "creative": {
            "id": creative.get("id", ""),
            "body": full_body,
            "title": creative.get("title") or link_data.get("name", ""),
            "description": link_data.get("description", ""),
            "cta": cta,
            "format": "catalog" if is_catalog_ad else ad_format,
            "image_url": image_url,
            "image_hash": creative.get("image_hash", ""),
            "thumbnail_url": creative.get("thumbnail_url", ""),
            "link_url": link_url,
            "is_catalog_ad": is_catalog_ad,
            "content_type": content_type,
            "text_style": text_style,
        },
        # Performance aggregates
        "last_7d": agg_7d,
        "last_14d": agg_14d,
        "trend_7d_vs_prev": trend,
        # 30-day and lifetime aggregates (from API, not computed from daily)
        "last_30d": agg_30d or {},
        "lifetime": agg_lifetime or {},
        # Daily performance (last 14 days for quick charting)
        "daily": [
            {
                "date": r["date"],
                "impressions": r["impressions"],
                "clicks": r["clicks"],
                "spend_aud": r["spend_aud"],
                "ctr": r["ctr"],
                "link_clicks": r["link_clicks"],
                "landing_page_views": r["landing_page_views"],
                "view_content": r["view_content"],
                "video_views": r["video_views"],
            }
            for r in sorted(daily_rows, key=lambda x: x["date"])
        ],
        # Demographics (age × gender)
        "demographics": demo_summary,
        # Placements
        "placements": placement_summary,
        # Metadata
        "last_collected": datetime.now(timezone.utc).isoformat(),
    }


def aggregate_daily(rows, days=7):
    """Sum daily rows within the last N days into an aggregate."""
    filtered = [r for r in rows if is_within_days(r["date"], days)]
    if not filtered:
        return {"impressions": 0, "reach": 0, "clicks": 0, "spend_aud": 0}

    total_imp = sum(r["impressions"] for r in filtered)
    total_clicks = sum(r["clicks"] for r in filtered)
    total_spend = round(sum(r["spend_aud"] for r in filtered), 2)
    total_reach = sum(r["reach"] for r in filtered)
    total_link_clicks = sum(r["link_clicks"] for r in filtered)
    total_lpv = sum(r["landing_page_views"] for r in filtered)
    total_vc = sum(r["view_content"] for r in filtered)
    total_pe = sum(r["post_engagement"] for r in filtered)
    total_vv = sum(r["video_views"] for r in filtered)

    return {
        "impressions": total_imp,
        "reach": total_reach,
        "clicks": total_clicks,
        "link_clicks": total_link_clicks,
        "landing_page_views": total_lpv,
        "view_content": total_vc,
        "post_engagement": total_pe,
        "video_views": total_vv,
        "spend_aud": total_spend,
        "ctr": round(total_clicks / total_imp * 100, 4) if total_imp > 0 else 0,
        "cpc": round(total_spend / total_clicks, 4) if total_clicks > 0 else None,
        "cpm": round(total_spend / total_imp * 1000, 2) if total_imp > 0 else None,
        "cost_per_link_click": (
            round(total_spend / total_link_clicks, 4) if total_link_clicks > 0 else None
        ),
        "cost_per_view_content": (
            round(total_spend / total_vc, 4) if total_vc > 0 else None
        ),
        "days_with_data": len(filtered),
    }


def is_within_days(date_str, days):
    """Check if a YYYY-MM-DD date string is within the last N days."""
    try:
        dt = datetime.strptime(date_str, "%Y-%m-%d").replace(tzinfo=timezone.utc)
        cutoff = datetime.now(timezone.utc) - timedelta(days=days)
        return dt >= cutoff
    except (ValueError, TypeError):
        return False


def compute_trend(recent_rows, prev_rows):
    """Compare recent 7d vs previous 7d to detect trends."""
    def totals(rows):
        return {
            "impressions": sum(r["impressions"] for r in rows),
            "clicks": sum(r["clicks"] for r in rows),
            "spend": round(sum(r["spend_aud"] for r in rows), 2),
            "link_clicks": sum(r["link_clicks"] for r in rows),
            "view_content": sum(r["view_content"] for r in rows),
        }

    r = totals(recent_rows)
    p = totals(prev_rows)

    def pct_change(current, previous):
        if previous == 0:
            return None
        return round((current - previous) / previous * 100, 1)

    return {
        "impressions_change_pct": pct_change(r["impressions"], p["impressions"]),
        "clicks_change_pct": pct_change(r["clicks"], p["clicks"]),
        "spend_change_pct": pct_change(r["spend"], p["spend"]),
        "link_clicks_change_pct": pct_change(r["link_clicks"], p["link_clicks"]),
        "ctr_recent": (round(r["clicks"] / r["impressions"] * 100, 4)
                       if r["impressions"] > 0 else 0),
        "ctr_previous": (round(p["clicks"] / p["impressions"] * 100, 4)
                         if p["impressions"] > 0 else 0),
        "direction": (
            "improving" if (r["impressions"] > 0 and p["impressions"] > 0 and
                           r["clicks"] / r["impressions"] > p["clicks"] / p["impressions"])
            else "declining" if (r["impressions"] > 0 and p["impressions"] > 0)
            else "insufficient_data"
        ),
    }


def summarize_demographics(demo_rows):
    """Collapse demographic breakdown rows into a summary."""
    if not demo_rows:
        return {"segments": [], "top_segment": None}

    segments = []
    for row in demo_rows:
        imp = int(row.get("impressions", 0))
        clicks = int(row.get("clicks", 0))
        spend = float(row.get("spend", 0))
        actions = row.get("actions", [])
        segments.append({
            "age": row.get("age", ""),
            "gender": row.get("gender", ""),
            "impressions": imp,
            "clicks": clicks,
            "spend_aud": round(spend, 2),
            "ctr": round(clicks / imp * 100, 4) if imp > 0 else 0,
            "link_clicks": int(get_action_value(actions, "link_click")),
            "post_engagement": int(get_action_value(actions, "post_engagement")),
        })

    # Sort by clicks descending to find top segment
    segments.sort(key=lambda s: s["clicks"], reverse=True)
    top = segments[0] if segments else None

    return {
        "segments": segments,
        "top_segment": (
            f"{top['gender']} {top['age']}" if top and top["clicks"] > 0 else None
        ),
        "total_segments": len(segments),
    }


def summarize_placements(placement_rows):
    """Collapse placement breakdown rows into a summary."""
    if not placement_rows:
        return {"placements": [], "top_placement": None}

    placements = []
    for row in placement_rows:
        imp = int(row.get("impressions", 0))
        clicks = int(row.get("clicks", 0))
        spend = float(row.get("spend", 0))
        placements.append({
            "platform": row.get("publisher_platform", ""),
            "position": row.get("platform_position", ""),
            "impressions": imp,
            "clicks": clicks,
            "spend_aud": round(spend, 2),
            "ctr": round(clicks / imp * 100, 4) if imp > 0 else 0,
        })

    placements.sort(key=lambda p: p["impressions"], reverse=True)
    top = placements[0] if placements else None

    return {
        "placements": placements,
        "top_placement": (
            f"{top['platform']}:{top['position']}" if top else None
        ),
        "total_placements": len(placements),
    }


# ---------------------------------------------------------------------------
# Backward-compatible snapshot (same shape as facebook-ads-insights.py)
# ---------------------------------------------------------------------------

def build_legacy_snapshot(ad_profiles, campaigns, account_daily):
    """Build the backward-compatible facebook_ads 'latest' doc."""
    today_data = fetch_account_insights("today")
    last7 = fetch_account_insights("last_7d")
    last30 = fetch_account_insights("last_30d")

    active_campaigns = [c for c in campaigns if c.get("status") == "ACTIVE"]

    link_clicks_7d = get_action_value(last7.get("actions", []), "link_click")
    page_engagements_7d = int(get_action_value(last7.get("actions", []), "page_engagement"))
    spend_7d = float(last7.get("spend", 0))
    cost_per_engagement_7d = (
        round(spend_7d / page_engagements_7d, 4) if page_engagements_7d > 0 else None
    )

    # Build ads array from profiles (backward-compatible shape)
    ads = []
    for p in ad_profiles:
        ads.append({
            "ad_id": p["ad_id"],
            "name": p["name"],
            "status": p["status"],
            "effective_status": p["effective_status"],
            "campaign_id": p["campaign_id"],
            "campaign_name": p["campaign_name"],
            "campaign_objective": p["campaign_objective"],
            "adset_id": p["adset_id"],
            "adset_name": p["adset_name"],
            "creative_id": p["creative"]["id"],
            "creative_body": p["creative"]["body"][:200],
            "creative_title": p["creative"]["title"],
            "creative_thumbnail": p["creative"]["thumbnail_url"],
            "link_url": p["creative"]["link_url"],
            "last_7d": p["last_7d"],
        })

    # Article-ad coverage (reuse existing logic)
    article_ad_coverage = build_article_ad_coverage(ads)

    return {
        "fetched_at": datetime.now(timezone.utc).isoformat(),
        "ad_account_id": AD_ACCOUNT_ID,
        "today": {
            "impressions": int(today_data.get("impressions", 0)),
            "reach": int(today_data.get("reach", 0)),
            "clicks": int(today_data.get("clicks", 0)),
            "spend_aud": float(today_data.get("spend", 0)),
            "ctr": float(today_data.get("ctr", 0)),
            "cpc": float(today_data.get("cpc", 0)) if today_data.get("cpc") else None,
            "frequency": float(today_data.get("frequency", 0)),
        },
        "last_7d": {
            "impressions": int(last7.get("impressions", 0)),
            "reach": int(last7.get("reach", 0)),
            "clicks": int(last7.get("clicks", 0)),
            "link_clicks": int(link_clicks_7d),
            "landing_page_views": int(get_action_value(last7.get("actions", []), "landing_page_view")),
            "view_content": int(get_action_value(last7.get("actions", []), "view_content")),
            "spend_aud": spend_7d,
            "ctr": float(last7.get("ctr", 0)),
            "cpc": float(last7.get("cpc", 0)) if last7.get("cpc") else None,
            "cpm": float(last7.get("cpm", 0)),
            "frequency": float(last7.get("frequency", 0)),
            "page_engagements": page_engagements_7d,
            "cost_per_engagement": cost_per_engagement_7d,
        },
        "last_30d": {
            "impressions": int(last30.get("impressions", 0)),
            "reach": int(last30.get("reach", 0)),
            "clicks": int(last30.get("clicks", 0)),
            "spend_aud": float(last30.get("spend", 0)),
            "ctr": float(last30.get("ctr", 0)),
            "cpc": float(last30.get("cpc", 0)) if last30.get("cpc") else None,
        },
        "campaigns": {
            "total": len(campaigns),
            "active": len(active_campaigns),
            "names": [c["name"] for c in active_campaigns],
        },
        "daily_spend_14d": [
            {
                "date": d.get("date_start"),
                "spend_aud": float(d.get("spend", 0)),
                "impressions": int(d.get("impressions", 0)),
                "clicks": int(d.get("clicks", 0)),
            }
            for d in account_daily
        ],
        "ads": ads,
        "ads_count": len(ads),
        "ads_active_count": len([a for a in ads if a.get("effective_status") == "ACTIVE"]),
        "article_ad_coverage": article_ad_coverage,
    }


def build_article_ad_coverage(ads):
    """Compare ads' link URLs against article_index to find coverage gaps."""
    try:
        client = MongoClient(COSMOS_URI)
        sm = client["system_monitor"]
        articles = list(sm["article_index"].find(
            {}, {"_id": 1, "title": 1, "url": 1, "category": 1, "suburbs": 1}
        ))
        client.close()
    except Exception:
        return {"error": "Could not read article_index"}

    if not articles:
        return {"articles_total": 0}

    ad_article_ids = set()
    for ad in ads:
        link = ad.get("link_url", "")
        if "/article/" in link:
            article_id = link.split("/article/")[-1].split("?")[0].split("#")[0]
            ad_article_ids.add(article_id)

    articles_with_ads = []
    articles_without_ads = []
    for article in articles:
        aid = str(article["_id"])
        info = {
            "article_id": aid,
            "title": article.get("title", "")[:80],
            "category": article.get("category", ""),
            "suburbs": article.get("suburbs", []),
        }
        if aid in ad_article_ids:
            articles_with_ads.append(info)
        else:
            articles_without_ads.append(info)

    uncovered_categories = {}
    for a in articles_without_ads:
        cat = a.get("category", "unknown")
        uncovered_categories[cat] = uncovered_categories.get(cat, 0) + 1

    return {
        "articles_total": len(articles),
        "articles_with_ads": len(articles_with_ads),
        "articles_without_ads_count": len(articles_without_ads),
        "uncovered_categories": uncovered_categories,
        "covered_article_ids": [a["article_id"] for a in articles_with_ads],
        "sample_uncovered": articles_without_ads[:10],
    }


# ---------------------------------------------------------------------------
# MongoDB persistence
# ---------------------------------------------------------------------------

def batched_bulk_write(collection, ops, batch_size=10, delay=0.5, label=""):
    """Write operations in small batches with delays to avoid Cosmos DB RU throttling."""
    total_upserted = 0
    total_modified = 0
    for i in range(0, len(ops), batch_size):
        batch = ops[i:i + batch_size]
        retries = 0
        while retries < 3:
            try:
                result = collection.bulk_write(batch, ordered=False)
                total_upserted += result.upserted_count
                total_modified += result.modified_count
                break
            except BulkWriteError as bwe:
                # Some may have succeeded; count them
                total_upserted += bwe.details.get("nUpserted", 0)
                total_modified += bwe.details.get("nModified", 0)
                errors = bwe.details.get("writeErrors", [])
                throttled = [e for e in errors if e.get("code") == 16500]
                if throttled:
                    retry_ms = max(
                        (e.get("errmsg", "").split("RetryAfterMs=")[1].split(",")[0]
                         for e in throttled if "RetryAfterMs=" in e.get("errmsg", "")),
                        default="500"
                    )
                    wait = min(int(retry_ms) / 1000 + 0.2, 5.0)
                    retries += 1
                    if retries < 3:
                        time.sleep(wait)
                        # Retry only the failed ops
                        failed_indices = {e["index"] - i for e in throttled}
                        batch = [batch[j] for j in range(len(batch))
                                 if j in failed_indices]
                        continue
                # Non-throttle errors or max retries
                break
        if i + batch_size < len(ops):
            time.sleep(delay)
    if label:
        print(f"  {label}: {total_upserted} inserted, {total_modified} updated")
    return total_upserted, total_modified


def save_all(ad_profiles, daily_metrics, demographics, placements,
             legacy_snapshot):
    """Write all data to MongoDB with batched writes to avoid RU throttling."""
    client = MongoClient(COSMOS_URI)
    sm = client["system_monitor"]
    now_iso = datetime.now(timezone.utc).isoformat()
    today_str = datetime.now(timezone.utc).strftime("%Y-%m-%d")

    # 1. Ad daily metrics — one doc per ad per day
    if daily_metrics:
        ops = []
        for row in daily_metrics:
            doc_id = f"{row['ad_id']}_{row['date']}"
            ops.append(UpdateOne(
                {"_id": doc_id},
                {"$set": {**row, "_id": doc_id, "collected_at": now_iso}},
                upsert=True,
            ))
        if ops:
            batched_bulk_write(sm["ad_daily_metrics"], ops, batch_size=10,
                               delay=0.5, label="ad_daily_metrics")

    # 2. Ad profiles — one doc per ad
    if ad_profiles:
        ops = []
        for profile in ad_profiles:
            ops.append(UpdateOne(
                {"_id": profile["_id"]},
                {"$set": profile},
                upsert=True,
            ))
        if ops:
            batched_bulk_write(sm["ad_profiles"], ops, batch_size=5,
                               delay=0.8, label="ad_profiles")

    # 3. Ad demographics — one doc per ad (latest 7d window)
    if demographics:
        ops = []
        for ad_id, demo_data in demographics.items():
            doc_id = f"{ad_id}_demographics"
            ops.append(UpdateOne(
                {"_id": doc_id},
                {"$set": {
                    "_id": doc_id,
                    "ad_id": ad_id,
                    "window": "last_7d",
                    "segments": demo_data,
                    "collected_at": now_iso,
                }},
                upsert=True,
            ))
        if ops:
            batched_bulk_write(sm["ad_demographics"], ops, batch_size=5,
                               delay=0.8, label="ad_demographics")

    # 4. Ad placements — one doc per ad (latest 7d window)
    if placements:
        ops = []
        for ad_id, place_data in placements.items():
            doc_id = f"{ad_id}_placements"
            ops.append(UpdateOne(
                {"_id": doc_id},
                {"$set": {
                    "_id": doc_id,
                    "ad_id": ad_id,
                    "window": "last_7d",
                    "placements": place_data,
                    "collected_at": now_iso,
                }},
                upsert=True,
            ))
        if ops:
            batched_bulk_write(sm["ad_placements"], ops, batch_size=5,
                               delay=0.8, label="ad_placements")

    time.sleep(1)  # Breathe before legacy writes

    # 5. Legacy backward-compatible snapshot
    sm["facebook_ads"].replace_one(
        {"_id": "latest"},
        {"_id": "latest", **legacy_snapshot},
        upsert=True,
    )
    print("  facebook_ads: updated 'latest'")

    time.sleep(0.5)

    # 6. Legacy daily history
    history_doc = {
        "_id": today_str,
        "ads": legacy_snapshot.get("ads", []),
        "account_7d": legacy_snapshot.get("last_7d", {}),
        "fetched_at": now_iso,
    }
    sm["facebook_ads_history"].replace_one(
        {"_id": today_str}, history_doc, upsert=True
    )
    print(f"  facebook_ads_history: updated {today_str}")

    # 7. Prune old data beyond retention period
    prune_old_data(sm)

    client.close()


def prune_old_data(sm):
    """Remove data older than RETENTION_DAYS."""
    cutoff_date = (datetime.now(timezone.utc) - timedelta(days=RETENTION_DAYS)).strftime("%Y-%m-%d")

    # Prune ad_daily_metrics (docs with date < cutoff)
    result = sm["ad_daily_metrics"].delete_many({
        "date": {"$lt": cutoff_date}
    })
    if result.deleted_count:
        print(f"  Pruned {result.deleted_count} ad_daily_metrics docs older than {cutoff_date}")

    # Prune facebook_ads_history
    result = sm["facebook_ads_history"].delete_many({
        "_id": {"$lt": cutoff_date}
    })
    if result.deleted_count:
        print(f"  Pruned {result.deleted_count} facebook_ads_history docs older than {cutoff_date}")


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main():
    parser = argparse.ArgumentParser(description="Facebook Metrics Collector v2")
    parser.add_argument("--quick", action="store_true",
                        help="Skip demographics and placement breakdowns")
    parser.add_argument("--print", action="store_true",
                        help="Print summary without saving to DB")
    parser.add_argument("--dry-run", action="store_true",
                        help="Show what would be collected without API calls")
    args = parser.parse_args()

    print(f"[{datetime.now(timezone.utc).isoformat()}] Facebook Metrics Collector v2 starting...")

    if args.dry_run:
        print("DRY RUN — would collect:")
        print("  - Per-ad daily metrics (14 days × ~43 ads)")
        print("  - Full creative details for all ads")
        print("  - Demographic breakdowns (age × gender) per ad" if not args.quick else "  - [SKIPPED] Demographics")
        print("  - Placement breakdowns per ad" if not args.quick else "  - [SKIPPED] Placements")
        print("  - Account-level aggregates (today, 7d, 30d)")
        print("  - Campaign list")
        print(f"  - Retention: {RETENTION_DAYS} days")
        return

    # Step 1: Fetch all ads metadata
    print("Fetching ads metadata...")
    ads_meta = fetch_ads_metadata()
    print(f"  Found {len(ads_meta)} ads")

    # Step 2: Fetch per-ad daily metrics (14 days)
    print("Fetching per-ad daily metrics (14 days)...")
    raw_daily = fetch_ad_daily_insights(14)
    print(f"  Got {len(raw_daily)} daily rows")
    daily_metrics = [parse_daily_row(r) for r in raw_daily]

    # Group daily by ad_id
    daily_by_ad = {}
    for row in daily_metrics:
        daily_by_ad.setdefault(row["ad_id"], []).append(row)

    # Step 3: Demographics (unless --quick)
    demo_by_ad = {}
    if not args.quick:
        print("Fetching demographic breakdowns (age × gender)...")
        try:
            raw_demos = fetch_ad_demographics()
            print(f"  Got {len(raw_demos)} demographic rows")
            for row in raw_demos:
                ad_id = row.get("ad_id", "")
                demo_by_ad.setdefault(ad_id, []).append(row)
        except Exception as e:
            print(f"  WARNING: Demographics fetch failed: {e}")
    else:
        print("Skipping demographics (--quick mode)")

    # Step 4: Placements (unless --quick)
    placement_by_ad = {}
    if not args.quick:
        print("Fetching placement breakdowns...")
        try:
            raw_placements = fetch_ad_placements()
            print(f"  Got {len(raw_placements)} placement rows")
            for row in raw_placements:
                ad_id = row.get("ad_id", "")
                placement_by_ad.setdefault(ad_id, []).append(row)
        except Exception as e:
            print(f"  WARNING: Placements fetch failed: {e}")
    else:
        print("Skipping placements (--quick mode)")

    # Step 5: 30d and lifetime per-ad aggregates
    print("Fetching 30d per-ad aggregates...")
    agg_30d_by_ad = {}
    try:
        raw_30d = fetch_ad_30d_insights()
        for row in raw_30d:
            parsed = parse_aggregate_row(row)
            agg_30d_by_ad[parsed["ad_id"]] = parsed
        print(f"  Got 30d data for {len(agg_30d_by_ad)} ads")
    except Exception as e:
        print(f"  WARNING: 30d fetch failed: {e}")

    print("Fetching lifetime per-ad aggregates...")
    agg_lifetime_by_ad = {}
    try:
        raw_lifetime = fetch_ad_lifetime_insights()
        for row in raw_lifetime:
            parsed = parse_aggregate_row(row)
            agg_lifetime_by_ad[parsed["ad_id"]] = parsed
        print(f"  Got lifetime data for {len(agg_lifetime_by_ad)} ads")
    except Exception as e:
        print(f"  WARNING: Lifetime fetch failed: {e}")

    # Step 6: Campaigns + account daily
    print("Fetching campaigns and account daily spend...")
    campaigns = fetch_campaigns()
    account_daily = fetch_account_daily(14)

    # Step 7: Build ad profiles
    print("Building ad profiles...")
    ad_profiles = []
    for ad in ads_meta:
        ad_id = ad.get("id", "")
        profile = build_ad_profile(
            ad,
            daily_by_ad.get(ad_id, []),
            demo_by_ad.get(ad_id, []),
            placement_by_ad.get(ad_id, []),
            agg_30d=agg_30d_by_ad.get(ad_id),
            agg_lifetime=agg_lifetime_by_ad.get(ad_id),
        )
        ad_profiles.append(profile)

    # Step 8: Build legacy snapshot
    print("Building legacy-compatible snapshot...")
    legacy = build_legacy_snapshot(ad_profiles, campaigns, account_daily)

    # Summary
    active_count = len([p for p in ad_profiles if p["effective_status"] == "ACTIVE"])
    total_spend_7d = legacy["last_7d"]["spend_aud"]
    total_imp_7d = legacy["last_7d"]["impressions"]

    print(f"\n--- Summary ---")
    print(f"  Ads: {len(ad_profiles)} total, {active_count} active")
    print(f"  Daily metric rows: {len(daily_metrics)}")
    print(f"  Demographic segments: {sum(len(v) for v in demo_by_ad.values())}")
    print(f"  Placement entries: {sum(len(v) for v in placement_by_ad.values())}")
    print(f"  Spend (7d): ${total_spend_7d:.2f} AUD")
    print(f"  Impressions (7d): {total_imp_7d:,}")
    print(f"  Campaigns: {legacy['campaigns']['active']} active / {legacy['campaigns']['total']} total")

    if getattr(args, "print"):
        # Print top 5 ads by CTR
        sorted_profiles = sorted(
            [p for p in ad_profiles if p["last_7d"].get("impressions", 0) > 100],
            key=lambda p: p["last_7d"].get("ctr", 0),
            reverse=True,
        )
        print(f"\n--- Top 5 ads by CTR (min 100 impressions) ---")
        for p in sorted_profiles[:5]:
            print(f"  [{p['effective_status']}] {p['name'][:60]}")
            print(f"    CTR: {p['last_7d'].get('ctr', 0):.2f}%  "
                  f"Spend: ${p['last_7d'].get('spend_aud', 0):.2f}  "
                  f"Imp: {p['last_7d'].get('impressions', 0):,}  "
                  f"Trend: {p['trend_7d_vs_prev'].get('direction', '?')}")
        return

    # Step 9: Save everything
    print("\nSaving to MongoDB...")
    save_all(
        ad_profiles=ad_profiles,
        daily_metrics=daily_metrics,
        demographics=demo_by_ad,
        placements=placement_by_ad,
        legacy_snapshot=legacy,
    )

    print(f"\nDone. Collections updated: ad_daily_metrics, ad_profiles, "
          f"ad_demographics, ad_placements, facebook_ads, facebook_ads_history")


if __name__ == "__main__":
    try:
        main()
    except Exception as e:
        print(f"FATAL: {e}", file=sys.stderr)
        traceback.print_exc(file=sys.stderr)
        sys.exit(1)
