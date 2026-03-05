#!/usr/bin/env python3
"""
Fetch Facebook Ads insights and store in MongoDB system_monitor collection.
Run daily (or on demand) to keep the ops dashboard current.

Usage:
    python3 scripts/facebook-ads-insights.py
    python3 scripts/facebook-ads-insights.py --print   # print without saving
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

TOKEN = os.environ["FACEBOOK_ADS_TOKEN"]
AD_ACCOUNT_ID = os.environ["FACEBOOK_AD_ACCOUNT_ID"]
API_VERSION = os.environ.get("FACEBOOK_API_VERSION", "v18.0")
BASE = f"https://graph.facebook.com/{API_VERSION}"
COSMOS_URI = os.environ["COSMOS_CONNECTION_STRING"]


def fb_get(path, params=None):
    p = {"access_token": TOKEN, **(params or {})}
    r = requests.get(f"{BASE}{path}", params=p, timeout=15)
    r.raise_for_status()
    return r.json()


def fetch_insights(date_preset="last_7d"):
    fields = "impressions,reach,clicks,spend,ctr,cpc,cpm,frequency,actions,cost_per_action_type"
    data = fb_get(f"/{AD_ACCOUNT_ID}/insights", {
        "fields": fields,
        "date_preset": date_preset,
        "level": "account",
    })
    return data.get("data", [{}])[0]


def fetch_campaigns():
    data = fb_get(f"/{AD_ACCOUNT_ID}/campaigns", {
        "fields": "name,status,objective,daily_budget,lifetime_budget",
        "limit": 20,
    })
    return data.get("data", [])


def fetch_daily_spend(days=14):
    """Per-day spend breakdown for sparkline chart."""
    data = fb_get(f"/{AD_ACCOUNT_ID}/insights", {
        "fields": "spend,impressions,clicks",
        "date_preset": f"last_{days}d",
        "time_increment": 1,
        "level": "account",
    })
    return data.get("data", [])


def fetch_ads():
    """Fetch all ads with status, creative details, and campaign info."""
    data = fb_get(f"/{AD_ACCOUNT_ID}/ads", {
        "fields": ("name,status,effective_status,campaign_id,adset_id,"
                   "creative{id,body,title,thumbnail_url,image_url,link_url,object_story_spec},"
                   "campaign{name,objective,status},"
                   "adset{name,status}"),
        "limit": 50,
        "filtering": json.dumps([{
            "field": "effective_status",
            "operator": "IN",
            "value": ["ACTIVE", "PAUSED", "CAMPAIGN_PAUSED",
                      "ADSET_PAUSED", "PENDING_REVIEW"],
        }]),
    })
    return data.get("data", [])


def fetch_ad_insights():
    """Fetch per-ad performance metrics for the last 7 days."""
    data = fb_get(f"/{AD_ACCOUNT_ID}/insights", {
        "fields": ("ad_id,ad_name,impressions,reach,clicks,spend,"
                   "ctr,cpc,cpm,frequency,actions,cost_per_action_type"),
        "date_preset": "last_7d",
        "level": "ad",
        "limit": 50,
    })
    return data.get("data", [])


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

    # Extract article IDs from ad link URLs
    # Ad links look like: https://fieldsestate.com.au/article/69a623cfebbfe70001709927
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

    # Summarise by category
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


def build_snapshot():
    today = fb_get(f"/{AD_ACCOUNT_ID}/insights", {
        "fields": "impressions,reach,clicks,spend,ctr,cpc,frequency",
        "date_preset": "today",
        "level": "account",
    }).get("data", [{}])
    today = today[0] if today else {}

    last7 = fetch_insights("last_7d")
    last30 = fetch_insights("last_30d")
    campaigns = fetch_campaigns()
    daily = fetch_daily_spend(14)

    active_campaigns = [c for c in campaigns if c.get("status") == "ACTIVE"]

    # Extract link clicks from actions array
    def get_action(actions, action_type):
        for a in (actions or []):
            if a.get("action_type") == action_type:
                return a.get("value", "0")
        return "0"

    link_clicks_7d = get_action(last7.get("actions", []), "link_click")

    # Per-ad data
    ads_meta = fetch_ads()
    ad_insights_raw = fetch_ad_insights()

    # Build insights lookup by ad_id
    insights_by_id = {}
    for row in ad_insights_raw:
        ad_id = row.get("ad_id")
        actions = row.get("actions", [])
        lc = get_action(actions, "link_click")
        lpv = get_action(actions, "landing_page_view")
        vc = get_action(actions, "view_content")
        cost_per = row.get("cost_per_action_type", [])
        cpvc = get_action(cost_per, "view_content") if cost_per else "0"
        insights_by_id[ad_id] = {
            "impressions": int(row.get("impressions", 0)),
            "reach": int(row.get("reach", 0)),
            "clicks": int(row.get("clicks", 0)),
            "link_clicks": int(lc),
            "landing_page_views": int(lpv),
            "view_content": int(vc),
            "cost_per_view_content": float(cpvc) if cpvc != "0" else None,
            "spend_aud": float(row.get("spend", 0)),
            "ctr": float(row.get("ctr", 0)),
            "cpc": float(row.get("cpc", 0)) if row.get("cpc") else None,
            "cpm": float(row.get("cpm", 0)),
            "frequency": float(row.get("frequency", 0)),
        }

    # Merge metadata with insights
    ads = []
    for ad in ads_meta:
        ad_id = ad.get("id")
        campaign = ad.get("campaign", {})
        adset = ad.get("adset", {})
        creative = ad.get("creative", {})
        perf = insights_by_id.get(ad_id, {})

        ads.append({
            "ad_id": ad_id,
            "name": ad.get("name", ""),
            "status": ad.get("status", ""),
            "effective_status": ad.get("effective_status", ""),
            "campaign_id": ad.get("campaign_id", ""),
            "campaign_name": campaign.get("name", ""),
            "campaign_objective": campaign.get("objective", ""),
            "adset_id": ad.get("adset_id", ""),
            "adset_name": adset.get("name", ""),
            "creative_id": creative.get("id", ""),
            "creative_body": (creative.get("body") or "")[:200],
            "creative_title": creative.get("title", ""),
            "creative_thumbnail": creative.get("thumbnail_url", ""),
            "link_url": (creative.get("object_story_spec", {})
                         .get("link_data", {}).get("link", "")),
            "last_7d": perf,
        })

    # Article-ad coverage gap: which articles have ads, which don't
    article_ad_coverage = build_article_ad_coverage(ads)

    return {
        "fetched_at": datetime.now(timezone.utc).isoformat(),
        "ad_account_id": AD_ACCOUNT_ID,
        "today": {
            "impressions": int(today.get("impressions", 0)),
            "reach": int(today.get("reach", 0)),
            "clicks": int(today.get("clicks", 0)),
            "spend_aud": float(today.get("spend", 0)),
            "ctr": float(today.get("ctr", 0)),
            "cpc": float(today.get("cpc", 0)) if today.get("cpc") else None,
            "frequency": float(today.get("frequency", 0)),
        },
        "last_7d": {
            "impressions": int(last7.get("impressions", 0)),
            "reach": int(last7.get("reach", 0)),
            "clicks": int(last7.get("clicks", 0)),
            "link_clicks": int(link_clicks_7d),
            "landing_page_views": int(get_action(last7.get("actions", []), "landing_page_view")),
            "view_content": int(get_action(last7.get("actions", []), "view_content")),
            "spend_aud": float(last7.get("spend", 0)),
            "ctr": float(last7.get("ctr", 0)),
            "cpc": float(last7.get("cpc", 0)) if last7.get("cpc") else None,
            "cpm": float(last7.get("cpm", 0)),
            "frequency": float(last7.get("frequency", 0)),
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
            for d in daily
        ],
        "ads": ads,
        "ads_count": len(ads),
        "ads_active_count": len([a for a in ads if a.get("effective_status") == "ACTIVE"]),
        "article_ad_coverage": article_ad_coverage,
    }


def save_to_mongo(snapshot):
    client = MongoClient(COSMOS_URI)
    db = client["system_monitor"]
    db["facebook_ads"].replace_one({"_id": "latest"}, {"_id": "latest", **snapshot}, upsert=True)
    # Daily history snapshot for trend analysis
    today_str = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    history_doc = {
        "_id": today_str,
        "ads": snapshot.get("ads", []),
        "account_7d": snapshot.get("last_7d", {}),
        "fetched_at": snapshot["fetched_at"],
    }
    db["facebook_ads_history"].replace_one({"_id": today_str}, history_doc, upsert=True)
    client.close()
    print("Saved to system_monitor.facebook_ads + facebook_ads_history")


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--print", action="store_true", help="Print without saving to DB")
    args = parser.parse_args()

    print("Fetching Facebook Ads insights...")
    snapshot = build_snapshot()

    if args.print:
        print(json.dumps(snapshot, indent=2))
    else:
        print(json.dumps(snapshot, indent=2))
        save_to_mongo(snapshot)
        print(f"Done. Spend last 7d: ${snapshot['last_7d']['spend_aud']:.2f} AUD, "
              f"Impressions: {snapshot['last_7d']['impressions']:,}, "
              f"Active campaigns: {snapshot['campaigns']['active']}, "
              f"Ads tracked: {snapshot['ads_count']} ({snapshot['ads_active_count']} active)")


if __name__ == "__main__":
    main()
