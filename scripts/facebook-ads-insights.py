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
    }


def save_to_mongo(snapshot):
    client = MongoClient(COSMOS_URI)
    db = client["system_monitor"]
    col = db["facebook_ads"]
    col.replace_one({"_id": "latest"}, {"_id": "latest", **snapshot}, upsert=True)
    client.close()
    print("Saved to system_monitor.facebook_ads")


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
              f"Active campaigns: {snapshot['campaigns']['active']}")


if __name__ == "__main__":
    main()
