#!/usr/bin/env python3
"""
Website Metrics Collector — Daily aggregate visitor metrics for trend analysis.

Mirrors fb-metrics-collector.py pattern. Reads from CRM_All_Data.sessions
(populated by visitor-track.mjs) and writes daily aggregates to
system_monitor.website_daily_metrics.

Collections written:
  - website_daily_metrics : one doc per day (90-day retention)

Usage:
    python3 scripts/website-metrics-collector.py                # Collect today's metrics
    python3 scripts/website-metrics-collector.py --date 2026-03-15  # Specific date
    python3 scripts/website-metrics-collector.py --backfill 14  # Last 14 days
    python3 scripts/website-metrics-collector.py --print        # Print without saving
    python3 scripts/website-metrics-collector.py --dry-run      # Show what would be collected
"""

import os
import sys
import json
import time
import argparse
import traceback
from datetime import datetime, timezone, timedelta
from dotenv import load_dotenv
from pymongo import MongoClient
from pymongo.errors import OperationFailure

load_dotenv("/home/fields/Fields_Orchestrator/.env")
COSMOS_URI = os.environ["COSMOS_CONNECTION_STRING"]
RETENTION_DAYS = 90

# Bot IP prefixes to exclude (mirrors visitor-track.mjs and system-monitor.mjs)
BOT_IP_PREFIXES = [
    "3.2", "3.6", "13.2", "18.", "34.", "35.8", "35.9",
    "44.2", "52.5", "52.6", "54.2", "54.6",
    "173.252.", "31.13.", "66.220.", "69.63.", "69.171.",
    "157.240.", "129.134.", "185.89.", "204.15.20.",
]

# Owner/team IPs to exclude
EXCLUDED_IPS = {"72.14.201.170", "220.233.219.90", "35.189.1.73"}


def build_bot_filter():
    """Build a MongoDB filter that excludes bot IPs and owner IPs."""
    regex = "^(" + "|".join(p.replace(".", "\\.") for p in BOT_IP_PREFIXES) + ")"
    return {
        "ip_raw": {
            "$not": {"$regex": regex},
            "$nin": list(EXCLUDED_IPS),
        }
    }


def cosmos_retry(fn, max_retries=3):
    """Retry a MongoDB operation on Cosmos DB 16500 throttling errors."""
    for attempt in range(max_retries):
        try:
            return fn()
        except OperationFailure as e:
            if e.code == 16500 and attempt < max_retries - 1:
                retry_ms = 200
                details = str(e.details) if hasattr(e, "details") else str(e)
                if "RetryAfterMs" in details:
                    import re
                    m = re.search(r"RetryAfterMs[\":]?\s*(\d+)", details)
                    if m:
                        retry_ms = int(m.group(1))
                wait = min(retry_ms / 1000 + 0.2, 5.0)
                print(f"  ⚠ Cosmos throttled (attempt {attempt+1}), waiting {wait:.1f}s")
                time.sleep(wait)
            else:
                raise


def connect():
    """Connect to MongoDB and return CRM + system_monitor databases."""
    client = MongoClient(COSMOS_URI)
    crm = client["CRM_All_Data"]
    sm = client["system_monitor"]
    return client, crm, sm


def collect_day_metrics(crm, sm, target_date):
    """
    Collect metrics for a single day from CRM_All_Data.sessions.

    Args:
        crm: CRM_All_Data database handle
        sm: system_monitor database handle
        target_date: date string "YYYY-MM-DD"

    Returns:
        dict: The daily metrics document
    """
    sessions_col = crm["sessions"]
    visitors_col = crm["visitors"]
    bot_filter = build_bot_filter()

    # Parse date boundaries (AEST = UTC+10)
    from zoneinfo import ZoneInfo
    aest = ZoneInfo("Australia/Brisbane")
    day_start_aest = datetime.strptime(target_date, "%Y-%m-%d").replace(tzinfo=aest)
    day_end_aest = day_start_aest + timedelta(days=1)
    day_start_utc = day_start_aest.astimezone(timezone.utc)
    day_end_utc = day_end_aest.astimezone(timezone.utc)

    day_filter = {
        **bot_filter,
        "session_start": {"$gte": day_start_utc, "$lt": day_end_utc},
    }

    print(f"\n📊 Collecting metrics for {target_date}...")

    # ── 1. Session counts ──
    total_sessions = cosmos_retry(lambda: sessions_col.count_documents(day_filter))
    print(f"  Sessions: {total_sessions}")

    if total_sessions == 0:
        return {
            "_id": target_date,
            "date": target_date,
            "collected_at": datetime.now(timezone.utc).isoformat(),
            "sessions": {"total": 0, "unique_visitors": 0, "returning": 0,
                         "mobile": 0, "desktop": 0, "tablet": 0},
            "engagement": {"bounce": 0, "light": 0, "engaged": 0, "deep": 0,
                           "bounce_rate": 0, "avg_duration_seconds": 0, "avg_scroll_depth": 0},
            "pages": {},
            "sources": {"facebook": 0, "google": 0, "direct": 0, "other": 0},
            "actions": {"property_views": 0, "searches": 0, "cta_clicks": 0,
                        "deep_scrolls_75pct": 0},
            "experiments": {},
        }

    # ── 2. Unique visitors + returning ──
    visitor_agg = cosmos_retry(lambda: list(sessions_col.aggregate([
        {"$match": day_filter},
        {"$group": {"_id": "$ip_raw", "count": {"$sum": 1}}},
    ])))
    unique_visitors = len(visitor_agg)
    returning_ips = set(v["_id"] for v in visitor_agg if v["count"] > 1)

    # Also check if these IPs have sessions before this day
    all_day_ips = [v["_id"] for v in visitor_agg]
    prior_returning = set()
    if all_day_ips:
        # Check in batches to avoid huge $in queries
        for i in range(0, len(all_day_ips), 50):
            batch = all_day_ips[i:i+50]
            prior_agg = cosmos_retry(lambda b=batch: list(sessions_col.aggregate([
                {"$match": {**bot_filter, "ip_raw": {"$in": b},
                            "session_start": {"$lt": day_start_utc}}},
                {"$group": {"_id": "$ip_raw"}},
            ])))
            prior_returning.update(r["_id"] for r in prior_agg)
            time.sleep(0.3)

    returning_count = len(returning_ips | prior_returning)

    # ── 3. Device breakdown ──
    device_agg = cosmos_retry(lambda: list(sessions_col.aggregate([
        {"$match": day_filter},
        {"$lookup": {
            "from": "visitors",
            "localField": "ip_raw",
            "foreignField": "ip_raw",
            "as": "visitor",
        }},
        {"$unwind": {"path": "$visitor", "preserveNullAndEmptyArrays": True}},
        {"$group": {
            "_id": {"$ifNull": ["$visitor.device_type", "unknown"]},
            "count": {"$sum": 1},
        }},
    ])))
    devices = {d["_id"]: d["count"] for d in device_agg}

    print(f"  Unique visitors: {unique_visitors}, returning: {returning_count}")

    # ── 4. Engagement breakdown ──
    engagement_agg = cosmos_retry(lambda: list(sessions_col.aggregate([
        {"$match": {**day_filter, "metrics.engagement": {"$exists": True}}},
        {"$group": {"_id": "$metrics.engagement", "count": {"$sum": 1}}},
    ])))
    engagement = {e["_id"]: e["count"] for e in engagement_agg}
    bounce_count = engagement.get("bounce", 0)
    bounce_rate = round(bounce_count / total_sessions * 100, 1) if total_sessions > 0 else 0

    # Average duration (non-bounce sessions)
    duration_agg = cosmos_retry(lambda: list(sessions_col.aggregate([
        {"$match": {**day_filter, "metrics.is_bounce": False,
                    "metrics.duration_seconds": {"$gt": 0}}},
        {"$group": {
            "_id": None,
            "avg_duration": {"$avg": "$metrics.duration_seconds"},
            "avg_scroll": {"$avg": "$metrics.max_scroll_depth"},
        }},
    ])))
    avg_duration = round(duration_agg[0]["avg_duration"], 1) if duration_agg else 0
    avg_scroll = round(duration_agg[0].get("avg_scroll", 0) or 0, 1) if duration_agg else 0

    print(f"  Engagement: bounce={bounce_count}, light={engagement.get('light', 0)}, "
          f"engaged={engagement.get('engaged', 0)}, deep={engagement.get('deep', 0)}")

    # ── 5. Page-level metrics (top 20) ──
    page_agg = cosmos_retry(lambda: list(sessions_col.aggregate([
        {"$match": day_filter},
        {"$unwind": "$pages"},
        {"$match": {"pages.event_type": "pageview"}},
        {"$group": {
            "_id": "$pages.path",
            "views": {"$sum": 1},
            "unique_sessions": {"$addToSet": "$session_id"},
        }},
        {"$addFields": {"unique_sessions_count": {"$size": "$unique_sessions"}}},
        {"$sort": {"unique_sessions_count": -1}},
        {"$limit": 20},
    ])))

    pages = {}
    for p in page_agg:
        pages[p["_id"]] = {
            "views": p["views"],
            "unique_sessions": p["unique_sessions_count"],
        }

    # Get per-page duration and scroll from session-level data for top pages
    top_paths = list(pages.keys())[:10]
    for path in top_paths:
        path_stats = cosmos_retry(lambda pp=path: list(sessions_col.aggregate([
            {"$match": {**day_filter, "pages.path": pp, "metrics.is_bounce": False}},
            {"$group": {
                "_id": None,
                "avg_duration": {"$avg": "$metrics.duration_seconds"},
                "avg_scroll": {"$avg": "$metrics.max_scroll_depth"},
            }},
        ])))
        if path_stats:
            pages[path]["avg_duration"] = round(path_stats[0].get("avg_duration", 0) or 0, 1)
            pages[path]["avg_scroll"] = round(path_stats[0].get("avg_scroll", 0) or 0, 1)
        time.sleep(0.2)

    # ── 6. Traffic sources (classify in Python to avoid Cosmos $regexMatch issues) ──
    all_sessions = cosmos_retry(lambda: list(sessions_col.find(
        day_filter, {"entry_referrer": 1, "utm": 1}
    )))
    sources = {"facebook": 0, "google": 0, "direct": 0, "other": 0}
    for s in all_sessions:
        ref = (s.get("entry_referrer") or "").lower()
        utm_source = ((s.get("utm") or {}).get("source") or "").lower()
        if "facebook.com" in ref or "fb.com" in ref or "l.facebook" in ref or utm_source == "fb":
            sources["facebook"] += 1
        elif "google." in ref or utm_source == "google":
            sources["google"] += 1
        elif not ref or "fieldsestate.com" in ref:
            sources["direct"] += 1
        else:
            sources["other"] += 1

    print(f"  Sources: fb={sources.get('facebook', 0)}, google={sources.get('google', 0)}, "
          f"direct={sources.get('direct', 0)}, other={sources.get('other', 0)}")

    # ── 7. Key actions ──
    property_views = cosmos_retry(lambda: sessions_col.count_documents({
        **day_filter, "metrics.has_property_view": True,
    }))
    searches = cosmos_retry(lambda: sessions_col.count_documents({
        **day_filter, "metrics.has_search": True,
    }))
    cta_clicks = cosmos_retry(lambda: sessions_col.count_documents({
        **day_filter, "metrics.has_click": True,
    }))
    deep_scrolls = cosmos_retry(lambda: sessions_col.count_documents({
        **day_filter, "metrics.max_scroll_depth": {"$gte": 75},
    }))

    print(f"  Actions: property_views={property_views}, searches={searches}, "
          f"clicks={cta_clicks}, deep_scrolls={deep_scrolls}")

    # ── 8. Active experiment variant metrics ──
    experiments_data = {}
    try:
        active_experiments = cosmos_retry(
            lambda: list(sm["website_experiments"].find({"status": "active"}))
        )
        for exp in active_experiments:
            variant_key = exp.get("variant_key", "")
            if not variant_key:
                continue
            # Look for variant data in session pages (event payloads include active_variants)
            variant_ids = [v["id"] for v in exp.get("variants", [])]
            exp_data = {}
            for vid in variant_ids:
                # Sessions where active_variants.<key> == vid
                v_filter = {
                    **day_filter,
                    f"pages.active_variants.{variant_key}": vid,
                }
                v_sessions = cosmos_retry(lambda f=v_filter: sessions_col.count_documents(f))
                if v_sessions > 0:
                    v_engagement = cosmos_retry(lambda f=v_filter: list(sessions_col.aggregate([
                        {"$match": f},
                        {"$group": {
                            "_id": "$metrics.engagement",
                            "count": {"$sum": 1},
                        }},
                    ])))
                    v_eng = {e["_id"]: e["count"] for e in v_engagement}
                    v_bounce = v_eng.get("bounce", 0)
                    exp_data[vid] = {
                        "sessions": v_sessions,
                        "bounce_rate": round(v_bounce / v_sessions * 100, 1) if v_sessions else 0,
                        "engaged": v_eng.get("engaged", 0) + v_eng.get("deep", 0),
                    }
                    time.sleep(0.2)
            if exp_data:
                experiments_data[variant_key] = exp_data
    except Exception:
        # website_experiments collection may not exist yet
        pass

    # ── Build final document ──
    doc = {
        "_id": target_date,
        "date": target_date,
        "collected_at": datetime.now(timezone.utc).isoformat(),
        "sessions": {
            "total": total_sessions,
            "unique_visitors": unique_visitors,
            "returning": returning_count,
            "mobile": devices.get("mobile", 0),
            "desktop": devices.get("desktop", 0),
            "tablet": devices.get("tablet", 0),
        },
        "engagement": {
            "bounce": bounce_count,
            "light": engagement.get("light", 0),
            "engaged": engagement.get("engaged", 0),
            "deep": engagement.get("deep", 0),
            "bounce_rate": bounce_rate,
            "avg_duration_seconds": avg_duration,
            "avg_scroll_depth": avg_scroll,
        },
        "pages": pages,
        "sources": {
            "facebook": sources.get("facebook", 0),
            "google": sources.get("google", 0),
            "direct": sources.get("direct", 0),
            "other": sources.get("other", 0),
        },
        "actions": {
            "property_views": property_views,
            "searches": searches,
            "cta_clicks": cta_clicks,
            "deep_scrolls_75pct": deep_scrolls,
        },
        "experiments": experiments_data,
    }

    return doc


def save_metrics(sm, doc):
    """Upsert a daily metrics document to MongoDB."""
    cosmos_retry(lambda: sm["website_daily_metrics"].replace_one(
        {"_id": doc["_id"]},
        doc,
        upsert=True,
    ))
    print(f"  ✅ Saved to website_daily_metrics[{doc['_id']}]")


def prune_old(sm):
    """Remove documents older than RETENTION_DAYS."""
    cutoff = (datetime.now(timezone.utc) - timedelta(days=RETENTION_DAYS)).strftime("%Y-%m-%d")
    result = cosmos_retry(lambda: sm["website_daily_metrics"].delete_many(
        {"date": {"$lt": cutoff}}
    ))
    if result.deleted_count > 0:
        print(f"  🗑 Pruned {result.deleted_count} docs older than {cutoff}")


def check_pending_reviews(sm):
    """Check for website changes that are 7+ days old and unreviewed."""
    try:
        cutoff = (datetime.now(timezone.utc) - timedelta(days=7)).isoformat()
        pending = list(sm["website_change_log"].find({
            "reviewed": False,
            "created_at": {"$lt": cutoff},
        }))
        if pending:
            print(f"\n⚠ {len(pending)} website change(s) pending review (7+ days old):")
            for c in pending:
                print(f"  - [{c.get('type', '?')}] {c.get('title', 'untitled')} "
                      f"({c.get('date', '?')})")
    except Exception:
        pass  # Collection may not exist yet


def main():
    parser = argparse.ArgumentParser(description="Website daily metrics collector")
    parser.add_argument("--date", help="Collect for specific date (YYYY-MM-DD)")
    parser.add_argument("--backfill", type=int, help="Backfill last N days")
    parser.add_argument("--print", dest="print_only", action="store_true",
                        help="Print metrics without saving")
    parser.add_argument("--dry-run", action="store_true",
                        help="Show what would be collected")
    args = parser.parse_args()

    print("=" * 60)
    print("Website Metrics Collector")
    print("=" * 60)

    client, crm, sm = connect()

    try:
        # Determine which dates to collect
        from zoneinfo import ZoneInfo
        aest = ZoneInfo("Australia/Brisbane")
        today_aest = datetime.now(aest).strftime("%Y-%m-%d")

        if args.backfill:
            dates = []
            for i in range(args.backfill):
                d = datetime.now(aest) - timedelta(days=i)
                dates.append(d.strftime("%Y-%m-%d"))
            dates.reverse()
            print(f"Backfilling {len(dates)} days: {dates[0]} → {dates[-1]}")
        elif args.date:
            dates = [args.date]
        else:
            dates = [today_aest]

        if args.dry_run:
            print(f"\nDry run — would collect metrics for: {', '.join(dates)}")
            return

        for target_date in dates:
            doc = collect_day_metrics(crm, sm, target_date)

            if args.print_only:
                print(json.dumps(doc, indent=2, default=str))
            else:
                save_metrics(sm, doc)
                time.sleep(0.5)  # Breathe between days

        if not args.print_only:
            # Prune old data
            prune_old(sm)

            # Check for pending change reviews
            check_pending_reviews(sm)

        print(f"\n✅ Done — collected {len(dates)} day(s)")

    except Exception as e:
        print(f"\n❌ Error: {e}")
        traceback.print_exc()
        sys.exit(1)
    finally:
        client.close()


if __name__ == "__main__":
    main()
