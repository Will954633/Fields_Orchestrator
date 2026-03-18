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
from urllib.parse import urlparse
from datetime import datetime, timezone, timedelta
from dotenv import load_dotenv
from pymongo import MongoClient
from pymongo.errors import OperationFailure

load_dotenv("/home/fields/Fields_Orchestrator/.env")
COSMOS_URI = os.environ["COSMOS_CONNECTION_STRING"]
RETENTION_DAYS = 90
MAX_REASONABLE_DURATION_SECONDS = 60 * 60

# Owner/team IPs to exclude
EXCLUDED_IPS = {"72.14.201.170", "220.233.219.90", "35.189.1.73"}

# Bot user-agent patterns (IP-based filtering removed — it was killing Facebook
# in-app browser traffic which routes through AWS/GCP infrastructure)
BOT_UA_REGEX = "bot|crawler|spider|HeadlessChrome|Puppeteer|Selenium|curl|wget|python-requests|Googlebot|facebookexternalhit|Facebot|GPTBot|ClaudeBot"


def build_bot_filter():
    """Build a MongoDB filter that excludes bots (by UA) and owner IPs."""
    return {
        "ip_raw": {"$nin": list(EXCLUDED_IPS)},
        "user_agent": {"$not": {"$regex": BOT_UA_REGEX, "$options": "i"}},
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


def normalize_page_path(path):
    """Collapse malformed absolute URLs back to canonical website paths."""
    if not path:
        return "/"
    value = str(path).strip()
    if value.startswith("fieldsestate.com.au"):
        value = f"https://{value}"
    if value.startswith("/http://") or value.startswith("/https://"):
        value = value[1:]
    if value.startswith("http://") or value.startswith("https://"):
        parsed = urlparse(value)
        normalized = parsed.path or "/"
        if parsed.query:
            normalized = f"{normalized}?{parsed.query}"
        return normalized
    if not value.startswith("/"):
        return f"/{value}"
    return value


def classify_source(session):
    """Classify traffic source with support for UTM tags, click IDs, and query param fallback."""
    ref = (session.get("entry_referrer") or "").lower()
    utm = session.get("utm") or {}
    utm_source = str(utm.get("source") or "").lower()
    utm_medium = str(utm.get("medium") or "").lower()

    # Fallback: check first page's query_params and referrer for attribution signals
    # when the utm/entry_referrer are missing (covers SPA referrer and UTM race condition)
    pages = session.get("pages") or []
    first_qp = {}
    first_page_ref = ""
    if pages and isinstance(pages, list) and len(pages) > 0:
        first_qp = pages[0].get("query_params") or {}
        first_page_ref = (pages[0].get("referrer") or "").lower()
    qp_source = str(first_qp.get("utm_source") or "").lower()
    has_gclid = bool(utm.get("gclid") or first_qp.get("gclid") or utm.get("gbraid") or first_qp.get("gbraid") or utm.get("gad_source") or first_qp.get("gad_source"))
    has_fbclid = bool(utm.get("fbclid") or first_qp.get("fbclid"))
    # Combine session-level and page-level referrer for classification
    ref = ref or first_page_ref

    if (
        utm_source in {"fb", "facebook", "ig", "instagram", "meta"}
        or qp_source in {"fb", "facebook", "ig", "instagram", "meta"}
        or "facebook.com" in ref
        or "fb.com" in ref
        or "l.facebook" in ref
        or "instagram.com" in ref
        or has_fbclid
    ):
        return "facebook"

    if (
        utm_source in {"google", "googleads", "adwords"}
        or qp_source in {"google", "googleads", "adwords"}
        or utm_medium in {"cpc", "ppc", "paid", "paid_search", "search"}
        or "google." in ref
        or "googleads." in ref
        or "googleadservices.com" in ref
        or "android-app://com.google.android.googlequicksearchbox" in ref
        or has_gclid
    ):
        return "google"

    if not ref or "fieldsestate.com" in ref:
        return "direct"

    return "other"


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
            "warnings": ["no_sessions_for_day"],
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
                    "metrics.duration_seconds": {"$gt": 0, "$lte": MAX_REASONABLE_DURATION_SECONDS}}},
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
    malformed_paths = set()
    for p in page_agg:
        raw_path = p["_id"]
        normalized_path = normalize_page_path(raw_path)
        if raw_path != normalized_path:
            malformed_paths.add(str(raw_path))
        entry = pages.setdefault(normalized_path, {"views": 0, "unique_sessions": 0})
        entry["views"] += p["views"]
        entry["unique_sessions"] += p["unique_sessions_count"]

    # Get per-page duration and scroll from page-level events, not whole-session metrics
    top_paths = list(pages.keys())[:10]
    for path in top_paths:
        raw_candidates = [path]
        if path.startswith("/"):
            raw_candidates.append(path[1:])
            raw_candidates.append(f"https://fieldsestate.com.au{path}")
            raw_candidates.append(f"/https://fieldsestate.com.au{path}")
        path_stats = cosmos_retry(lambda pp=raw_candidates: list(sessions_col.aggregate([
            {"$match": {**day_filter, "pages.path": {"$in": pp}, "metrics.is_bounce": False}},
            {"$unwind": "$pages"},
            {"$match": {
                "pages.path": {"$in": pp},
                "pages.time_on_page": {"$gte": 0, "$lte": MAX_REASONABLE_DURATION_SECONDS},
            }},
            {"$group": {
                "_id": None,
                "avg_duration": {"$avg": "$pages.time_on_page"},
                "avg_scroll": {"$avg": "$pages.scroll_depth"},
            }},
        ])))
        if path_stats:
            pages[path]["avg_duration"] = round(path_stats[0].get("avg_duration", 0) or 0, 1)
            pages[path]["avg_scroll"] = round(path_stats[0].get("avg_scroll", 0) or 0, 1)
        time.sleep(0.2)

    # ── 6. Traffic sources (classify in Python to avoid Cosmos $regexMatch issues) ──
    # Include pages (first element) for fallback referrer/query_params classification
    all_sessions = cosmos_retry(lambda: list(sessions_col.aggregate([
        {"$match": day_filter},
        {"$project": {
            "entry_referrer": 1, "utm": 1,
            "pages": {"$slice": ["$pages", 1]},
        }},
    ])))
    sources = {"facebook": 0, "google": 0, "direct": 0, "other": 0}
    for s in all_sessions:
        sources[classify_source(s)] += 1

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
    active_experiment_count = 0
    try:
        active_experiments = cosmos_retry(
            lambda: list(sm["website_experiments"].find({"status": "active"}))
        )
        active_experiment_count = len(active_experiments)
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
                    "$or": [
                        {f"active_variants.{variant_key}": vid},
                        {f"pages.active_variants.{variant_key}": vid},
                    ],
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

    impossible_duration_count = cosmos_retry(lambda: sessions_col.count_documents({
        **day_filter,
        "$or": [
            {"metrics.duration_seconds": {"$gt": MAX_REASONABLE_DURATION_SECONDS}},
            {"pages.time_on_page": {"$gt": MAX_REASONABLE_DURATION_SECONDS}},
        ],
    }))

    warnings = []
    if malformed_paths:
        warnings.append(f"normalized_{len(malformed_paths)}_malformed_page_paths")
    if impossible_duration_count:
        warnings.append(f"ignored_{impossible_duration_count}_impossible_duration_records")
    if active_experiment_count and not experiments_data:
        warnings.append("active_experiments_have_no_variant_telemetry")
    if any((s.get("utm") or {}).get("gclid") for s in all_sessions) and sources["google"] == 0:
        warnings.append("google_click_ids_present_but_google_sessions_zero")
    if any((s.get("utm") or {}).get("fbclid") for s in all_sessions) and sources["facebook"] == 0:
        warnings.append("facebook_click_ids_present_but_facebook_sessions_zero")

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
        "warnings": warnings,
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
