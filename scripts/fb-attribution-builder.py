#!/usr/bin/env python3
"""
Facebook Attribution Builder — joins ad performance with website session outcomes.

Reads ad_profiles (from fb-metrics-collector.py) and CRM_All_Data.sessions,
then computes per-ad website attribution metrics:
  - Sessions driven, unique visitors
  - Engagement breakdown (bounce/light/engaged/deep)
  - Avg duration, max scroll depth
  - Pages viewed, properties viewed, searches made
  - Entry pages (which article/page they landed on)
  - Geographic breakdown of visitors
  - Multi-session visitors (return rate)
  - Cost per website session, cost per engaged session

Writes to:
  - system_monitor.ad_attribution  : per-ad attribution doc
  - Updates system_monitor.ad_profiles with attribution field

Schedule: Daily at 23:15 AEST (after fb-metrics-collector at 23:00)

Usage:
    python3 scripts/fb-attribution-builder.py
    python3 scripts/fb-attribution-builder.py --print    # Print without saving
    python3 scripts/fb-attribution-builder.py --days 30  # Attribution window (default: 30)
"""

import os
import sys
import json
import time
import argparse
from datetime import datetime, timezone, timedelta
from collections import defaultdict
from dotenv import load_dotenv
from pymongo import MongoClient, UpdateOne
from pymongo.errors import BulkWriteError

load_dotenv("/home/fields/Fields_Orchestrator/.env")

COSMOS_URI = os.environ["COSMOS_CONNECTION_STRING"]


def build_attribution(days=30, print_only=False):
    """Build per-ad attribution from CRM session data."""
    client = MongoClient(COSMOS_URI)
    sm = client["system_monitor"]
    crm = client["CRM_All_Data"]
    now = datetime.now(timezone.utc)
    cutoff = now - timedelta(days=days)

    # ---------------------------------------------------------------
    # 1. Load ad profiles for name/spend lookup
    # ---------------------------------------------------------------
    print("Loading ad profiles...")
    profiles = {p["_id"]: p for p in sm["ad_profiles"].find()}
    print(f"  {len(profiles)} ad profiles loaded")

    # ---------------------------------------------------------------
    # 2. Load all FB-attributed sessions within the window
    # ---------------------------------------------------------------
    print(f"Loading sessions (last {days} days with utm.content)...")
    sessions = list(crm["sessions"].find({
        "utm.content": {"$exists": True, "$ne": None},
        "utm.source": "fb",
    }))
    print(f"  {len(sessions)} FB-attributed sessions found")

    # Also load sessions with fbclid but no utm.content
    fbclid_sessions = list(crm["sessions"].find({
        "utm.fbclid": {"$exists": True, "$ne": None},
        "utm.content": {"$exists": False},
    }))
    if fbclid_sessions:
        print(f"  + {len(fbclid_sessions)} sessions with fbclid only (no ad_id mapping)")

    # ---------------------------------------------------------------
    # 3. Load visitor data for geo + return visit analysis
    # ---------------------------------------------------------------
    print("Loading visitor data...")
    visitor_ips = set()
    for s in sessions:
        ip = s.get("ip_raw") or s.get("ip_hash", "")
        if ip:
            visitor_ips.add(ip)

    visitors_by_ip = {}
    if visitor_ips:
        for v in crm["visitors"].find({"ip_raw": {"$in": list(visitor_ips)}}):
            visitors_by_ip[v["ip_raw"]] = v
    print(f"  {len(visitors_by_ip)} unique visitors loaded")

    # ---------------------------------------------------------------
    # 4. Group sessions by ad_id (utm.content)
    # ---------------------------------------------------------------
    sessions_by_ad = defaultdict(list)
    for s in sessions:
        ad_id = s["utm"]["content"]
        sessions_by_ad[ad_id].append(s)

    print(f"  Sessions map to {len(sessions_by_ad)} unique ads")

    # ---------------------------------------------------------------
    # 5. Build attribution per ad
    # ---------------------------------------------------------------
    print("Computing per-ad attribution...")
    attributions = []

    for ad_id, ad_sessions in sessions_by_ad.items():
        profile = profiles.get(ad_id, {})
        spend_7d = profile.get("last_7d", {}).get("spend_aud", 0)
        spend_14d = profile.get("last_14d", {}).get("spend_aud", 0)

        # Session metrics
        unique_ips = set()
        engagement_counts = {"bounce": 0, "light": 0, "engaged": 0, "deep": 0}
        durations = []
        scroll_depths = []
        entry_pages = defaultdict(int)
        pages_visited = defaultdict(int)
        properties_viewed = set()
        searches = []
        geo_cities = defaultdict(int)
        devices = defaultdict(int)

        for s in ad_sessions:
            ip = s.get("ip_raw", "")
            unique_ips.add(ip)

            # Engagement
            eng = (s.get("metrics", {}).get("engagement") or "bounce")
            engagement_counts[eng] = engagement_counts.get(eng, 0) + 1

            # Duration
            dur = s.get("metrics", {}).get("duration_seconds") or s.get("total_time_seconds", 0)
            if dur:
                durations.append(dur)

            # Scroll depth
            scroll = s.get("metrics", {}).get("max_scroll_depth", 0)
            if scroll:
                scroll_depths.append(scroll)

            # Entry page (first page in session)
            pages = s.get("pages", [])
            if pages:
                entry_path = pages[0].get("path", "/")
                entry_pages[entry_path] += 1

            # All pages visited
            for page in pages:
                path = page.get("path", "")
                if path and page.get("event_type") in ("pageview", "scroll", "session_start"):
                    pages_visited[path] += 1

                # Property views
                if page.get("event_type") == "property_view" and page.get("property_id"):
                    properties_viewed.add(page["property_id"])

                # Searches
                if page.get("event_type") == "search" and page.get("search_query"):
                    searches.append(page["search_query"])

            # Visitor geo
            visitor = visitors_by_ip.get(ip, {})
            city = visitor.get("geo", {}).get("city", "Unknown")
            geo_cities[city] += 1
            device = visitor.get("device_type", "unknown")
            devices[device] += 1

        # Return visitors (those with >1 session from any source)
        return_visitors = 0
        for ip in unique_ips:
            visitor = visitors_by_ip.get(ip, {})
            if visitor.get("total_sessions", 0) > 1:
                return_visitors += 1

        total_sessions = len(ad_sessions)
        unique_visitors = len(unique_ips)
        engaged_sessions = engagement_counts.get("engaged", 0) + engagement_counts.get("deep", 0)
        avg_duration = round(sum(durations) / len(durations), 1) if durations else 0
        avg_scroll = round(sum(scroll_depths) / len(scroll_depths), 1) if scroll_depths else 0
        bounce_rate = round(engagement_counts["bounce"] / total_sessions * 100, 1) if total_sessions > 0 else 0
        engagement_rate = round(engaged_sessions / total_sessions * 100, 1) if total_sessions > 0 else 0

        # Cost metrics (using last 7d spend)
        cost_per_session = round(spend_7d / total_sessions, 2) if total_sessions > 0 and spend_7d > 0 else None
        cost_per_engaged = round(spend_7d / engaged_sessions, 2) if engaged_sessions > 0 and spend_7d > 0 else None

        # Sort entry pages by count
        top_entry_pages = sorted(entry_pages.items(), key=lambda x: x[1], reverse=True)[:5]
        top_pages = sorted(pages_visited.items(), key=lambda x: x[1], reverse=True)[:10]

        attribution = {
            "_id": ad_id,
            "ad_id": ad_id,
            "ad_name": profile.get("name", "Unknown"),
            "campaign_name": profile.get("campaign_name", "Unknown"),
            "effective_status": profile.get("effective_status", "unknown"),
            # Session metrics
            "sessions": total_sessions,
            "unique_visitors": unique_visitors,
            "return_visitors": return_visitors,
            "return_rate": round(return_visitors / unique_visitors * 100, 1) if unique_visitors > 0 else 0,
            # Engagement
            "engagement": engagement_counts,
            "engagement_rate": engagement_rate,
            "bounce_rate": bounce_rate,
            # Duration & scroll
            "avg_duration_seconds": avg_duration,
            "avg_scroll_depth": avg_scroll,
            # Content interaction
            "entry_pages": [{"path": p, "count": c} for p, c in top_entry_pages],
            "top_pages": [{"path": p, "views": c} for p, c in top_pages],
            "properties_viewed": list(properties_viewed),
            "properties_viewed_count": len(properties_viewed),
            "search_queries": searches[:20],
            "has_property_views": len(properties_viewed) > 0,
            "has_searches": len(searches) > 0,
            # Geography
            "geo_cities": [{"city": c, "count": n} for c, n in
                           sorted(geo_cities.items(), key=lambda x: x[1], reverse=True)[:10]],
            # Devices
            "devices": dict(devices),
            # Cost metrics
            "spend_7d": spend_7d,
            "cost_per_session": cost_per_session,
            "cost_per_engaged_session": cost_per_engaged,
            # Ad performance context (from ad_profiles)
            "ad_ctr_7d": profile.get("last_7d", {}).get("ctr", 0),
            "ad_impressions_7d": profile.get("last_7d", {}).get("impressions", 0),
            "ad_clicks_7d": profile.get("last_7d", {}).get("clicks", 0),
            # Conversion funnel
            "funnel": {
                "impressions": profile.get("last_7d", {}).get("impressions", 0),
                "clicks": profile.get("last_7d", {}).get("clicks", 0),
                "link_clicks": profile.get("last_7d", {}).get("link_clicks", 0),
                "sessions": total_sessions,
                "engaged_sessions": engaged_sessions,
                "property_views": len(properties_viewed),
            },
            # Metadata
            "attribution_window_days": days,
            "computed_at": now.isoformat(),
        }

        attributions.append(attribution)

    # Sort by sessions descending
    attributions.sort(key=lambda a: a["sessions"], reverse=True)

    # ---------------------------------------------------------------
    # 6. Build summary
    # ---------------------------------------------------------------
    total_fb_sessions = sum(a["sessions"] for a in attributions)
    total_engaged = sum(a["engagement"].get("engaged", 0) + a["engagement"].get("deep", 0) for a in attributions)
    total_fb_visitors = len(set().union(*(
        set(s.get("ip_raw", "") for s in ad_sessions)
        for ad_sessions in sessions_by_ad.values()
    )))

    summary = {
        "_id": "summary",
        "total_fb_sessions": total_fb_sessions,
        "total_fb_visitors": total_fb_visitors,
        "total_engaged_sessions": total_engaged,
        "ads_with_sessions": len(attributions),
        "ads_without_sessions": len(profiles) - len(attributions),
        "total_sessions_all_sources": crm["sessions"].count_documents({}),
        "fb_session_share": round(total_fb_sessions / max(crm["sessions"].count_documents({}), 1) * 100, 1),
        "attribution_window_days": days,
        "computed_at": now.isoformat(),
        # Top performing ads by engagement rate
        "top_by_engagement": [
            {"ad_id": a["ad_id"], "name": a["ad_name"][:60],
             "sessions": a["sessions"], "engagement_rate": a["engagement_rate"]}
            for a in sorted(
                [a for a in attributions if a["sessions"] >= 2],
                key=lambda a: a["engagement_rate"], reverse=True
            )[:5]
        ],
        # Top by session volume
        "top_by_volume": [
            {"ad_id": a["ad_id"], "name": a["ad_name"][:60],
             "sessions": a["sessions"], "engagement_rate": a["engagement_rate"]}
            for a in attributions[:5]
        ],
    }

    # ---------------------------------------------------------------
    # 7. Print results
    # ---------------------------------------------------------------
    print(f"\n--- Attribution Summary ---")
    print(f"  FB sessions: {total_fb_sessions} / {summary['total_sessions_all_sources']} total "
          f"({summary['fb_session_share']}%)")
    print(f"  Unique FB visitors: {total_fb_visitors}")
    print(f"  Engaged sessions: {total_engaged}")
    print(f"  Ads with sessions: {len(attributions)}")

    print(f"\n--- Per-Ad Attribution ---")
    for a in attributions[:10]:
        eng_str = (f"B:{a['engagement']['bounce']} L:{a['engagement']['light']} "
                   f"E:{a['engagement']['engaged']} D:{a['engagement']['deep']}")
        cost_str = f"${a['cost_per_session']:.2f}/sess" if a['cost_per_session'] else "n/a"
        print(f"  [{a['effective_status'][:3]}] {a['ad_name'][:55]}")
        print(f"    Sessions: {a['sessions']} | Visitors: {a['unique_visitors']} | "
              f"Eng rate: {a['engagement_rate']}% | Avg: {a['avg_duration_seconds']}s | "
              f"Scroll: {a['avg_scroll_depth']}% | {cost_str}")
        print(f"    Engagement: {eng_str}")
        if a["entry_pages"]:
            print(f"    Entry: {a['entry_pages'][0]['path']}")
        if a["properties_viewed_count"] > 0:
            print(f"    Properties viewed: {a['properties_viewed_count']}")

    if print_only:
        return

    # ---------------------------------------------------------------
    # 8. Save to MongoDB
    # ---------------------------------------------------------------
    print("\nSaving to MongoDB...")

    # Save attribution docs
    ops = [UpdateOne({"_id": a["_id"]}, {"$set": a}, upsert=True) for a in attributions]
    ops.append(UpdateOne({"_id": "summary"}, {"$set": summary}, upsert=True))

    # Batch write to avoid RU throttling
    for i in range(0, len(ops), 5):
        batch = ops[i:i + 5]
        retries = 0
        while retries < 3:
            try:
                sm["ad_attribution"].bulk_write(batch, ordered=False)
                break
            except BulkWriteError:
                retries += 1
                time.sleep(1)
        if i + 5 < len(ops):
            time.sleep(0.5)

    print(f"  ad_attribution: {len(attributions)} ads + summary")

    # Update ad_profiles with attribution summary
    profile_ops = []
    for a in attributions:
        profile_ops.append(UpdateOne(
            {"_id": a["ad_id"]},
            {"$set": {
                "attribution": {
                    "sessions": a["sessions"],
                    "unique_visitors": a["unique_visitors"],
                    "engagement_rate": a["engagement_rate"],
                    "bounce_rate": a["bounce_rate"],
                    "avg_duration_seconds": a["avg_duration_seconds"],
                    "avg_scroll_depth": a["avg_scroll_depth"],
                    "properties_viewed_count": a["properties_viewed_count"],
                    "cost_per_session": a["cost_per_session"],
                    "cost_per_engaged_session": a["cost_per_engaged_session"],
                    "return_rate": a["return_rate"],
                    "computed_at": now.isoformat(),
                }
            }}
        ))

    for i in range(0, len(profile_ops), 5):
        batch = profile_ops[i:i + 5]
        retries = 0
        while retries < 3:
            try:
                sm["ad_profiles"].bulk_write(batch, ordered=False)
                break
            except BulkWriteError:
                retries += 1
                time.sleep(1)
        if i + 5 < len(profile_ops):
            time.sleep(0.5)

    print(f"  ad_profiles: updated {len(profile_ops)} with attribution data")

    client.close()
    print("\nDone.")


def main():
    parser = argparse.ArgumentParser(description="Facebook Attribution Builder")
    parser.add_argument("--print", action="store_true", help="Print without saving")
    parser.add_argument("--days", type=int, default=30,
                        help="Attribution window in days (default: 30)")
    args = parser.parse_args()

    print(f"[{datetime.now(timezone.utc).isoformat()}] Facebook Attribution Builder starting...")
    build_attribution(days=args.days, print_only=getattr(args, "print"))


if __name__ == "__main__":
    main()
