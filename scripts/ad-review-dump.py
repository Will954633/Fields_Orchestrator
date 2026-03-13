#!/usr/bin/env python3
"""
Ad Review Data Dump — pulls all Facebook ad performance data for interactive analysis.

Outputs a structured summary of every ad's performance, attribution, demographics,
and website outcomes. Designed to be read by Claude during interactive ad review sessions.

Usage:
    python3 scripts/ad-review-dump.py                  # Full dump (all ads)
    python3 scripts/ad-review-dump.py --active         # Active ads only
    python3 scripts/ad-review-dump.py --id <ad_id>     # Single ad deep dive
    python3 scripts/ad-review-dump.py --top 10         # Top 10 by spend
    python3 scripts/ad-review-dump.py --days 7         # Daily metrics window (default: 14)
    python3 scripts/ad-review-dump.py --json           # Output as JSON (for piping)
    python3 scripts/ad-review-dump.py --summary        # High-level summary only
"""

import os
import sys
import json
import argparse
from datetime import datetime, timezone, timedelta
from collections import defaultdict
from dotenv import load_dotenv
from pymongo import MongoClient

load_dotenv("/home/fields/Fields_Orchestrator/.env")
COSMOS_URI = os.environ["COSMOS_CONNECTION_STRING"]


def connect():
    client = MongoClient(COSMOS_URI)
    return client, client["system_monitor"], client["CRM_All_Data"]


def fmt_money(v):
    if v is None:
        return "n/a"
    return f"${v:,.2f}" if v >= 1 else f"${v:.3f}"


def fmt_pct(v):
    if v is None:
        return "n/a"
    return f"{v:.1f}%"


def fmt_num(v):
    if v is None:
        return "n/a"
    return f"{v:,}"


def get_account_summary(sm, crm):
    """High-level account summary across all ads."""
    profiles = list(sm["ad_profiles"].find())
    attribution_summary = sm["ad_attribution"].find_one({"_id": "summary"})

    active = [p for p in profiles if p.get("effective_status") == "ACTIVE"]
    paused = [p for p in profiles if p.get("effective_status") == "PAUSED"]

    # Aggregate spend
    total_spend_7d = sum(p.get("last_7d", {}).get("spend_aud", 0) for p in profiles)
    total_spend_14d = sum(p.get("last_14d", {}).get("spend_aud", 0) for p in profiles)
    total_impressions_7d = sum(p.get("last_7d", {}).get("impressions", 0) for p in profiles)
    total_clicks_7d = sum(p.get("last_7d", {}).get("clicks", 0) for p in profiles)
    total_link_clicks_7d = sum(p.get("last_7d", {}).get("link_clicks", 0) for p in profiles)

    # Website sessions from attribution
    total_sessions = attribution_summary.get("total_fb_sessions", 0) if attribution_summary else 0
    total_engaged = attribution_summary.get("total_engaged_sessions", 0) if attribution_summary else 0
    fb_share = attribution_summary.get("fb_session_share", 0) if attribution_summary else 0

    avg_ctr = (total_clicks_7d / total_impressions_7d * 100) if total_impressions_7d > 0 else 0
    cost_per_click = (total_spend_7d / total_clicks_7d) if total_clicks_7d > 0 else 0
    cost_per_session = (total_spend_7d / total_sessions) if total_sessions > 0 else 0

    return {
        "total_ads": len(profiles),
        "active_ads": len(active),
        "paused_ads": len(paused),
        "spend_7d": total_spend_7d,
        "spend_14d": total_spend_14d,
        "impressions_7d": total_impressions_7d,
        "clicks_7d": total_clicks_7d,
        "link_clicks_7d": total_link_clicks_7d,
        "avg_ctr_7d": avg_ctr,
        "cost_per_click_7d": cost_per_click,
        "website_sessions": total_sessions,
        "engaged_sessions": total_engaged,
        "fb_session_share": fb_share,
        "cost_per_session": cost_per_session,
    }


def get_ad_detail(sm, crm, ad_id, days=14):
    """Deep dive into a single ad."""
    profile = sm["ad_profiles"].find_one({"_id": ad_id})
    attribution = sm["ad_attribution"].find_one({"_id": ad_id})
    demographics = sm["ad_demographics"].find_one({"_id": ad_id})
    placements = sm["ad_placements"].find_one({"_id": ad_id})

    # Daily metrics
    cutoff = (datetime.now(timezone.utc) - timedelta(days=days)).strftime("%Y-%m-%d")
    daily = list(sm["ad_daily_metrics"].find({
        "ad_id": ad_id,
        "date": {"$gte": cutoff}
    }).sort("date", 1))

    # Recent sessions from this ad
    sessions = list(crm["sessions"].find({
        "utm.content": ad_id,
    }).sort("_id", -1).limit(20))

    return {
        "profile": profile,
        "attribution": attribution,
        "demographics": demographics,
        "placements": placements,
        "daily_metrics": daily,
        "recent_sessions": sessions,
    }


def print_summary(summary):
    """Print account-level summary."""
    print("=" * 70)
    print("FACEBOOK ADS — ACCOUNT SUMMARY")
    print("=" * 70)
    print(f"  Ads: {summary['active_ads']} active, {summary['paused_ads']} paused, {summary['total_ads']} total")
    print(f"  Spend (7d): {fmt_money(summary['spend_7d'])}  |  (14d): {fmt_money(summary['spend_14d'])}")
    print(f"  Impressions (7d): {fmt_num(summary['impressions_7d'])}")
    print(f"  Clicks (7d): {fmt_num(summary['clicks_7d'])}  |  Link clicks: {fmt_num(summary['link_clicks_7d'])}")
    print(f"  Avg CTR (7d): {fmt_pct(summary['avg_ctr_7d'])}  |  CPC: {fmt_money(summary['cost_per_click_7d'])}")
    print(f"  Website sessions (FB): {fmt_num(summary['website_sessions'])}  |  Engaged: {fmt_num(summary['engaged_sessions'])}")
    print(f"  FB share of all sessions: {fmt_pct(summary['fb_session_share'])}")
    print(f"  Cost per session: {fmt_money(summary['cost_per_session'])}")
    print()


def print_ad_table(profiles, attributions_map):
    """Print sortable ad table."""
    print("=" * 70)
    print("PER-AD PERFORMANCE")
    print("=" * 70)

    for i, p in enumerate(profiles):
        ad_id = p["_id"]
        attr = attributions_map.get(ad_id, {})
        status = p.get("effective_status", "?")[:3]
        name = p.get("name", "Unknown")[:55]
        campaign = p.get("campaign_name", "")[:40]

        s7 = p.get("last_7d", {})
        s14 = p.get("last_14d", {})

        spend_7d = s7.get("spend_aud", 0)
        impressions = s7.get("impressions", 0)
        clicks = s7.get("clicks", 0)
        ctr = s7.get("ctr", 0)
        cpm = s7.get("cpm_aud", 0)
        link_clicks = s7.get("link_clicks", 0)

        sessions = attr.get("sessions", 0)
        eng_rate = attr.get("engagement_rate", 0)
        bounce_rate = attr.get("bounce_rate", 0)
        avg_dur = attr.get("avg_duration_seconds", 0)
        cost_per_sess = attr.get("cost_per_session")
        props_viewed = attr.get("properties_viewed_count", 0)

        print(f"\n  [{status}] #{i+1} — {name}")
        print(f"  Campaign: {campaign}")
        print(f"  Ad ID: {ad_id}")
        print(f"  --- FB Metrics (7d) ---")
        print(f"    Spend: {fmt_money(spend_7d)}  |  Impressions: {fmt_num(impressions)}  |  CPM: {fmt_money(cpm)}")
        print(f"    Clicks: {fmt_num(clicks)}  |  Link clicks: {fmt_num(link_clicks)}  |  CTR: {fmt_pct(ctr)}")

        if s14:
            print(f"  --- FB Metrics (14d) ---")
            print(f"    Spend: {fmt_money(s14.get('spend_aud', 0))}  |  Impressions: {fmt_num(s14.get('impressions', 0))}  |  CTR: {fmt_pct(s14.get('ctr', 0))}")

        if sessions > 0:
            print(f"  --- Website Attribution ---")
            print(f"    Sessions: {sessions}  |  Eng rate: {fmt_pct(eng_rate)}  |  Bounce: {fmt_pct(bounce_rate)}")
            print(f"    Avg duration: {avg_dur}s  |  Properties viewed: {props_viewed}  |  $/session: {fmt_money(cost_per_sess)}")

            # Entry pages
            entry_pages = attr.get("entry_pages", [])
            if entry_pages:
                entries = ", ".join(f"{ep['path']} ({ep['count']})" for ep in entry_pages[:3])
                print(f"    Entry pages: {entries}")

        # Creative info
        creative = p.get("creative", {})
        if creative:
            if creative.get("image_description"):
                print(f"  --- Creative ---")
                print(f"    Image: {creative['image_description'][:80]}")
            if creative.get("body"):
                print(f"    Text: {creative['body'][:100]}...")

        # Funnel
        if sessions > 0 and impressions > 0:
            print(f"  --- Funnel ---")
            print(f"    {fmt_num(impressions)} imp → {fmt_num(clicks)} click → {fmt_num(link_clicks)} link → {sessions} session → {round(sessions * eng_rate / 100)} engaged")

    print()


def print_ad_detail(data, ad_id):
    """Print deep dive for a single ad."""
    p = data["profile"]
    if not p:
        print(f"Ad {ad_id} not found in ad_profiles.")
        return

    print("=" * 70)
    print(f"AD DEEP DIVE: {p.get('name', 'Unknown')}")
    print("=" * 70)

    # Profile
    print(f"  Ad ID: {ad_id}")
    print(f"  Campaign: {p.get('campaign_name', '?')}  |  Adset: {p.get('adset_name', '?')}")
    print(f"  Status: {p.get('effective_status', '?')}")
    print(f"  Objective: {p.get('objective', '?')}")
    print(f"  Created: {p.get('created_time', '?')}")

    # Creative
    creative = p.get("creative", {})
    if creative:
        print(f"\n  --- Creative ---")
        print(f"  Title: {creative.get('title', 'n/a')}")
        print(f"  Body: {creative.get('body', 'n/a')}")
        print(f"  Link: {creative.get('link_url', 'n/a')}")
        print(f"  CTA: {creative.get('call_to_action', 'n/a')}")
        if creative.get("image_url"):
            print(f"  Image URL: {creative['image_url']}")
        if creative.get("image_description"):
            print(f"  Image desc: {creative['image_description']}")
        if creative.get("image_category"):
            print(f"  Image category: {creative['image_category']}")

    # Targeting
    targeting = p.get("targeting", {})
    if targeting:
        print(f"\n  --- Targeting ---")
        for k, v in targeting.items():
            print(f"  {k}: {json.dumps(v, default=str)[:100]}")

    # Performance windows
    for window in ["last_7d", "last_14d", "last_30d", "lifetime"]:
        metrics = p.get(window, {})
        if metrics and metrics.get("impressions", 0) > 0:
            print(f"\n  --- {window.replace('_', ' ').title()} ---")
            print(f"    Spend: {fmt_money(metrics.get('spend_aud', 0))}  |  Impressions: {fmt_num(metrics.get('impressions', 0))}")
            print(f"    Clicks: {fmt_num(metrics.get('clicks', 0))}  |  CTR: {fmt_pct(metrics.get('ctr', 0))}")
            print(f"    CPM: {fmt_money(metrics.get('cpm_aud', 0))}  |  CPC: {fmt_money(metrics.get('cpc_aud', 0))}")
            print(f"    Link clicks: {fmt_num(metrics.get('link_clicks', 0))}  |  Reach: {fmt_num(metrics.get('reach', 0))}")

    # Attribution
    attr = data["attribution"]
    if attr:
        print(f"\n  --- Website Attribution ---")
        print(f"    Sessions: {attr.get('sessions', 0)}  |  Unique visitors: {attr.get('unique_visitors', 0)}")
        print(f"    Engagement: B:{attr.get('engagement', {}).get('bounce', 0)} L:{attr.get('engagement', {}).get('light', 0)} E:{attr.get('engagement', {}).get('engaged', 0)} D:{attr.get('engagement', {}).get('deep', 0)}")
        print(f"    Engagement rate: {fmt_pct(attr.get('engagement_rate', 0))}  |  Bounce rate: {fmt_pct(attr.get('bounce_rate', 0))}")
        print(f"    Avg duration: {attr.get('avg_duration_seconds', 0)}s  |  Avg scroll: {attr.get('avg_scroll_depth', 0)}%")
        print(f"    Return visitors: {attr.get('return_visitors', 0)} ({fmt_pct(attr.get('return_rate', 0))})")
        print(f"    Properties viewed: {attr.get('properties_viewed_count', 0)}")
        print(f"    Cost/session: {fmt_money(attr.get('cost_per_session'))}  |  Cost/engaged: {fmt_money(attr.get('cost_per_engaged_session'))}")

        if attr.get("entry_pages"):
            print(f"    Entry pages:")
            for ep in attr["entry_pages"]:
                print(f"      {ep['path']} — {ep['count']} sessions")

        if attr.get("top_pages"):
            print(f"    Top pages viewed:")
            for tp in attr["top_pages"][:5]:
                print(f"      {tp['path']} — {tp['views']} views")

        if attr.get("geo_cities"):
            print(f"    Visitor cities:")
            for gc in attr["geo_cities"][:5]:
                print(f"      {gc['city']} — {gc['count']}")

        if attr.get("devices"):
            print(f"    Devices: {attr['devices']}")

    # Demographics
    demo = data["demographics"]
    if demo and demo.get("breakdowns"):
        print(f"\n  --- Demographics ---")
        for b in sorted(demo["breakdowns"], key=lambda x: x.get("spend", 0), reverse=True)[:10]:
            print(f"    {b.get('age', '?')} {b.get('gender', '?')}: "
                  f"spend={fmt_money(b.get('spend', 0))} imp={fmt_num(b.get('impressions', 0))} "
                  f"clicks={b.get('clicks', 0)} ctr={fmt_pct(b.get('ctr', 0))}")

    # Placements
    plc = data["placements"]
    if plc and plc.get("breakdowns"):
        print(f"\n  --- Placements ---")
        for b in sorted(plc["breakdowns"], key=lambda x: x.get("spend", 0), reverse=True)[:10]:
            print(f"    {b.get('publisher_platform', '?')}/{b.get('platform_position', '?')}: "
                  f"spend={fmt_money(b.get('spend', 0))} imp={fmt_num(b.get('impressions', 0))} "
                  f"clicks={b.get('clicks', 0)} ctr={fmt_pct(b.get('ctr', 0))}")

    # Daily trend
    daily = data["daily_metrics"]
    if daily:
        print(f"\n  --- Daily Metrics (last {len(daily)} days) ---")
        print(f"    {'Date':<12} {'Spend':>8} {'Imp':>7} {'Click':>6} {'CTR':>6} {'CPC':>6}")
        for d in daily:
            print(f"    {d.get('date', '?'):<12} "
                  f"{fmt_money(d.get('spend', 0)):>8} "
                  f"{fmt_num(d.get('impressions', 0)):>7} "
                  f"{d.get('clicks', 0):>6} "
                  f"{fmt_pct(d.get('ctr', 0)):>6} "
                  f"{fmt_money(d.get('cpc', 0)):>6}")

    # Recent sessions
    sessions = data["recent_sessions"]
    if sessions:
        print(f"\n  --- Recent Website Sessions (last {len(sessions)}) ---")
        for s in sessions[:10]:
            pages = s.get("pages", [])
            entry = pages[0].get("path", "/") if pages else "?"
            eng = s.get("metrics", {}).get("engagement", "?")
            dur = s.get("metrics", {}).get("duration_seconds") or s.get("total_time_seconds", 0)
            scroll = s.get("metrics", {}).get("max_scroll_depth", 0)
            ts = s.get("session_start", s.get("_id", ""))
            city = s.get("geo", {}).get("city", "?") if s.get("geo") else "?"
            print(f"    {str(ts)[:19]}  entry={entry:<30}  eng={eng:<8}  dur={dur}s  scroll={scroll}%  city={city}")

    print()


def main():
    parser = argparse.ArgumentParser(description="Ad Review Data Dump")
    parser.add_argument("--active", action="store_true", help="Active ads only")
    parser.add_argument("--id", type=str, help="Single ad deep dive")
    parser.add_argument("--top", type=int, default=0, help="Top N by spend")
    parser.add_argument("--days", type=int, default=14, help="Daily metrics window")
    parser.add_argument("--json", action="store_true", help="Output as JSON")
    parser.add_argument("--summary", action="store_true", help="Summary only")
    parser.add_argument("--sort", choices=["spend", "ctr", "impressions", "sessions", "engagement"],
                        default="spend", help="Sort order for ad table")
    args = parser.parse_args()

    client, sm, crm = connect()

    # Single ad deep dive
    if args.id:
        data = get_ad_detail(sm, crm, args.id, days=args.days)
        if args.json:
            # Clean ObjectId for JSON serialization
            def clean(obj):
                if isinstance(obj, dict):
                    return {k: clean(v) for k, v in obj.items() if k != "_id" or isinstance(v, str)}
                if isinstance(obj, list):
                    return [clean(i) for i in obj]
                return str(obj) if hasattr(obj, '__str__') and not isinstance(obj, (str, int, float, bool, type(None))) else obj
            print(json.dumps(clean(data), indent=2, default=str))
        else:
            print_ad_detail(data, args.id)
        client.close()
        return

    # Account summary
    summary = get_account_summary(sm, crm)

    if args.json and args.summary:
        print(json.dumps(summary, indent=2, default=str))
        client.close()
        return

    if not args.json:
        print_summary(summary)

    if args.summary:
        client.close()
        return

    # Load all profiles and attributions
    profiles = list(sm["ad_profiles"].find())
    attributions = {a["_id"]: a for a in sm["ad_attribution"].find({"_id": {"$ne": "summary"}})}

    # Filter
    if args.active:
        profiles = [p for p in profiles if p.get("effective_status") == "ACTIVE"]

    # Sort
    sort_keys = {
        "spend": lambda p: p.get("last_7d", {}).get("spend_aud", 0),
        "ctr": lambda p: p.get("last_7d", {}).get("ctr", 0),
        "impressions": lambda p: p.get("last_7d", {}).get("impressions", 0),
        "sessions": lambda p: attributions.get(p["_id"], {}).get("sessions", 0),
        "engagement": lambda p: attributions.get(p["_id"], {}).get("engagement_rate", 0),
    }
    profiles.sort(key=sort_keys[args.sort], reverse=True)

    if args.top > 0:
        profiles = profiles[:args.top]

    if args.json:
        result = {"summary": summary, "ads": []}
        for p in profiles:
            ad_id = p["_id"]
            attr = attributions.get(ad_id, {})
            # Remove mongo ObjectId issues
            p.pop("_id", None)
            attr.pop("_id", None)
            result["ads"].append({"profile": p, "attribution": attr})
        print(json.dumps(result, indent=2, default=str))
    else:
        print_ad_table(profiles, attributions)

    client.close()


if __name__ == "__main__":
    main()
