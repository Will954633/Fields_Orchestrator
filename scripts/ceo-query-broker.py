#!/home/fields/venv/bin/python3
"""
Read-only query broker for CEO agents and founder reviews.

This script exposes a narrow set of approved queries instead of broad shell or
database access. It is intended to be called locally on the orchestrator VM.
"""

from __future__ import annotations

import argparse
import time
from datetime import datetime, timedelta
from typing import Any

from ceo_agent_lib import dumps_json, get_client, load_founder_truths, now_aest, retry_cosmos_read, to_jsonable


def get_pipeline_collection(sm):
    process_runs = sm["process_runs"]
    if retry_cosmos_read(lambda: process_runs.count_documents({}, limit=1)) > 0:
        return process_runs, "process_runs"
    return sm["orchestrator_runs"], "orchestrator_runs"


def parse_dt(value: Any) -> datetime | None:
    if isinstance(value, datetime):
        return value
    if isinstance(value, str) and value:
        try:
            return datetime.fromisoformat(value.replace("Z", "+00:00"))
        except ValueError:
            return None
    return None


def sort_rows(rows: list[dict[str, Any]], key: str, *, reverse: bool = True) -> list[dict[str, Any]]:
    return sorted(rows, key=lambda row: str(row.get(key, "")), reverse=reverse)


def safe_float(value: Any) -> float:
    try:
        return float(value or 0)
    except (TypeError, ValueError):
        return 0.0


def safe_int(value: Any) -> int:
    try:
        return int(value or 0)
    except (TypeError, ValueError):
        return 0


def get_aest_date_label(value: Any) -> str | None:
    dt = parse_dt(value)
    if not dt:
        return None
    return dt.astimezone(now_aest().tzinfo).strftime("%Y-%m-%d")


def is_weekly_process(row: dict[str, Any]) -> bool:
    process_id = safe_int(row.get("process_id"))
    if process_id in {102, 104}:
        return True
    text = " ".join(str(row.get(key, "")) for key in ("name", "description", "pipeline")).lower()
    return "all suburbs" in text or "weekly" in text


def summarize_step_group(rows: list[dict[str, Any]], expected_ids: set[int] | None = None) -> dict[str, Any]:
    expected_ids = expected_ids or set()
    statuses = [str(row.get("status", "unknown")).lower() for row in rows]
    seen_ids = {safe_int(row.get("process_id")) for row in rows if row.get("process_id") is not None}
    missing_ids = sorted(pid for pid in expected_ids if pid not in seen_ids)
    failed = sum(1 for status in statuses if status in {"failed", "error"})
    running = sum(1 for status in statuses if status in {"running", "in_progress"})
    success = sum(1 for status in statuses if status in {"success", "completed"})
    if not rows:
        level = "critical"
    elif failed or missing_ids:
        level = "critical"
    elif running:
        level = "warning"
    else:
        level = "ok"
    return {
        "status": level,
        "total_steps": len(rows),
        "success_steps": success,
        "failed_steps": failed,
        "running_steps": running,
        "missing_expected_ids": missing_ids,
        "steps": to_jsonable(rows),
    }


def last_expected_weekly_date() -> str:
    current = now_aest()
    days_since_sunday = (current.weekday() + 1) % 7
    return (current - timedelta(days=days_since_sunday)).strftime("%Y-%m-%d")


def build_ad_alerts(
    fb_profiles: list[dict[str, Any]],
    attributions: dict[str, dict[str, Any]],
    google_profiles: list[dict[str, Any]],
    recent_decisions: list[dict[str, Any]],
    active_experiments: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    alerts: list[dict[str, Any]] = []

    for profile in fb_profiles:
        effective_status = str(profile.get("effective_status", "")).upper()
        if effective_status in {
            "ACTIVE",
            "PAUSED",
            "ARCHIVED",
            "CAMPAIGN_PAUSED",
            "ADSET_PAUSED",
        }:
            continue
        alerts.append(
            {
                "severity": "medium",
                "channel": "facebook",
                "title": f"Facebook ad status needs review: {profile.get('name', 'Unknown ad')}",
                "detail": f"effective_status={effective_status or 'unknown'}",
            }
        )

    for profile in fb_profiles:
        ad_id = str(profile.get("_id", ""))
        spend = safe_float(profile.get("last_7d", {}).get("spend_aud"))
        sessions = safe_int((attributions.get(ad_id) or {}).get("sessions"))
        if spend >= 20 and sessions == 0:
            alerts.append(
                {
                    "severity": "medium",
                    "channel": "facebook",
                    "title": f"Facebook spend without sessions: {profile.get('name', 'Unknown ad')}",
                    "detail": f"${spend:.2f} spent in 7d with 0 attributed sessions.",
                }
            )

    for profile in google_profiles:
        status = str(profile.get("status", "")).upper()
        impressions = safe_int(profile.get("total_impressions"))
        clicks = safe_int(profile.get("total_clicks"))
        conversions = safe_float(profile.get("total_conversions"))
        cost = safe_float(profile.get("total_cost"))
        if status == "ENABLED" and impressions == 0:
            alerts.append(
                {
                    "severity": "medium",
                    "channel": "google",
                    "title": f"Google campaign enabled with no impressions: {profile.get('campaign_name', 'Unknown campaign')}",
                    "detail": "Campaign is enabled but has not started delivering.",
                }
            )
        if status == "ENABLED" and clicks >= 20 and conversions == 0 and cost >= 20:
            alerts.append(
                {
                    "severity": "high",
                    "channel": "google",
                    "title": f"Google campaign spending without conversions: {profile.get('campaign_name', 'Unknown campaign')}",
                    "detail": f"${cost:.2f} spent, {clicks} clicks, 0 conversions.",
                }
            )

    if recent_decisions and not active_experiments:
        alerts.append(
            {
                "severity": "low",
                "channel": "cross_channel",
                "title": "Ad experiment state is only partially structured",
                "detail": "Recent ad decisions exist, but system_monitor.ad_experiments is empty, so experiment completion tracking is weak.",
            }
        )

    return alerts


def fetch_ops_summary(sm) -> dict[str, Any]:
    run_coll, run_source = get_pipeline_collection(sm)
    runs = list(run_coll.find({}, {"_id": 0}).limit(20))
    latest_run = sort_rows(runs, "started_at")[0] if runs else None
    latest_errors = list(sm["watchdog_runs"].find({}, {"_id": 0}).limit(20))
    latest_errors = sort_rows(latest_errors, "started_at")
    latest_props = list(
        sm["ceo_proposals"].find(
            {"agent": {"$ne": "system"}},
            {"_id": 0, "agent": 1, "date": 1, "status": 1, "updated_at": 1},
        ).limit(30)
    )
    latest_props.sort(key=lambda row: (row.get("date", ""), str(row.get("updated_at", ""))), reverse=True)
    return {
        "generated_at": now_aest().isoformat(),
        "pipeline_source": run_source,
        "latest_run": to_jsonable(latest_run),
        "recent_watchdog_runs": to_jsonable(latest_errors[:5]),
        "recent_proposals": to_jsonable(latest_props[:10]),
    }


def fetch_orchestrator_health(sm) -> dict[str, Any]:
    current = now_aest()
    cutoff = current - timedelta(days=14)
    process_rows = list(
        sm["process_runs"].find(
            {"system": "orchestrator", "started_at": {"$gte": cutoff}},
            {"_id": 0},
        ).limit(500)
    )
    process_rows = sort_rows(process_rows, "started_at")

    daily_rows = [row for row in process_rows if str(row.get("pipeline", "")) == "orchestrator_daily"]
    daily_groups: dict[str, list[dict[str, Any]]] = {}
    for row in daily_rows:
        label = get_aest_date_label(row.get("started_at"))
        if label:
            daily_groups.setdefault(label, []).append(row)

    latest_daily_date = max(daily_groups) if daily_groups else None
    latest_daily_rows = sort_rows(daily_groups.get(latest_daily_date, []), "process_id", reverse=False)
    daily_summary = summarize_step_group(latest_daily_rows)
    daily_summary["date"] = latest_daily_date

    weekly_rows = [row for row in process_rows if is_weekly_process(row)]
    weekly_groups: dict[str, list[dict[str, Any]]] = {}
    for row in weekly_rows:
        label = get_aest_date_label(row.get("started_at"))
        if label:
            weekly_groups.setdefault(label, []).append(row)

    latest_weekly_date = max(weekly_groups) if weekly_groups else None
    latest_weekly_rows = sort_rows(weekly_groups.get(latest_weekly_date, []), "process_id", reverse=False)
    weekly_summary = summarize_step_group(latest_weekly_rows, expected_ids={102, 104})
    weekly_summary["date"] = latest_weekly_date
    weekly_summary["expected_last_run_date"] = last_expected_weekly_date()

    tuesday_check_required = current.strftime("%A") == "Tuesday"
    tuesday_check_passed = (
        not tuesday_check_required
        or (
            latest_weekly_date == weekly_summary["expected_last_run_date"]
            and weekly_summary["status"] == "ok"
            and daily_summary["status"] in {"ok", "warning"}
        )
    )

    alerts: list[dict[str, Any]] = []
    if daily_summary["status"] in {"critical", "warning"}:
        alerts.append(
            {
                "severity": "high" if daily_summary["status"] == "critical" else "medium",
                "title": "Daily orchestrator needs attention",
                "detail": f"Latest daily run {latest_daily_date or 'unknown'} has status {daily_summary['status']}.",
            }
        )
    if latest_weekly_date is None:
        alerts.append(
            {
                "severity": "high",
                "title": "Weekly orchestrator evidence is missing",
                "detail": "No recent weekly all-suburbs steps were found for processes 102/104.",
            }
        )
    elif latest_weekly_date != weekly_summary["expected_last_run_date"]:
        alerts.append(
            {
                "severity": "high",
                "title": "Weekly orchestrator looks stale",
                "detail": f"Most recent weekly run is {latest_weekly_date}; expected {weekly_summary['expected_last_run_date']}.",
            }
        )
    elif weekly_summary["status"] != "ok":
        alerts.append(
            {
                "severity": "high",
                "title": "Weekly orchestrator did not complete cleanly",
                "detail": f"Latest weekly run {latest_weekly_date} has status {weekly_summary['status']}.",
            }
        )

    return {
        "generated_at": current.isoformat(),
        "today": current.strftime("%A"),
        "tuesday_check_required": tuesday_check_required,
        "tuesday_check_passed": tuesday_check_passed,
        "daily": to_jsonable(daily_summary),
        "weekly": to_jsonable(weekly_summary),
        "alerts": alerts,
    }


def fetch_pipeline_runs(sm, days: int, limit: int) -> dict[str, Any]:
    cutoff = now_aest() - timedelta(days=days)
    run_coll, run_source = get_pipeline_collection(sm)
    rows = list(run_coll.find({"started_at": {"$gte": cutoff}}, {"_id": 0}).limit(limit * 5))
    rows = sort_rows(rows, "started_at")
    return {"days": days, "limit": limit, "pipeline_source": run_source, "runs": to_jsonable(rows[:limit])}


def fetch_website_metrics(sm, days: int) -> dict[str, Any]:
    cutoff = (now_aest() - timedelta(days=days)).strftime("%Y-%m-%d")
    rows = list(sm["website_daily_metrics"].find({"date": {"$gte": cutoff}}, {"_id": 0}))
    rows = sort_rows(rows, "date")
    return {"days": days, "rows": to_jsonable(rows)}


def fetch_ad_metrics(sm, days: int, limit: int) -> dict[str, Any]:
    cutoff = (now_aest() - timedelta(days=days)).strftime("%Y-%m-%d")
    fb = list(sm["ad_daily_metrics"].find({"date": {"$gte": cutoff}}, {"_id": 0}).limit(limit * 4))
    google = list(sm["google_ads_daily_metrics"].find({"date": {"$gte": cutoff}}, {"_id": 0}).limit(limit * 4))
    fb = sort_rows(fb, "date")
    google = sort_rows(google, "date")

    fb_profiles = list(sm["ad_profiles"].find({}).limit(limit * 3))
    fb_profiles = sort_rows(fb_profiles, "updated_at")
    google_profiles = list(sm["google_ads_profiles"].find({}, {"_id": 0}).limit(limit * 3))
    google_profiles = sort_rows(google_profiles, "last_updated")
    attr_rows = list(sm["ad_attribution"].find({}).limit(limit * 3))
    attr_rows = sort_rows(attr_rows, "updated_at")
    attr_map = {str(row.get("ad_id") or row.get("_id")): row for row in attr_rows if row.get("_id") != "summary"}
    attr_summary = next((row for row in attr_rows if row.get("_id") == "summary"), {})

    active_experiments = list(sm["ad_experiments"].find({"status": "active"}, {"_id": 0}).limit(20))
    active_experiments = sort_rows(active_experiments, "created_at")
    recent_experiments = list(sm["ad_experiments"].find({}, {"_id": 0}).limit(40))
    recent_experiments = sort_rows(recent_experiments, "created_at")
    recent_decisions = list(sm["ad_decisions"].find({}, {"_id": 0}).limit(40))
    recent_decisions = sort_rows(recent_decisions, "created_at")

    top_fb_ads = []
    for profile in fb_profiles:
        ad_id = str(profile.get("_id", ""))
        attr = attr_map.get(ad_id, {})
        top_fb_ads.append(
            {
                "ad_id": ad_id,
                "name": profile.get("name"),
                "campaign_name": profile.get("campaign_name"),
                "effective_status": profile.get("effective_status"),
                "spend_7d": safe_float(profile.get("last_7d", {}).get("spend_aud")),
                "impressions_7d": safe_int(profile.get("last_7d", {}).get("impressions")),
                "link_clicks_7d": safe_int(profile.get("last_7d", {}).get("link_clicks")),
                "sessions": safe_int(attr.get("sessions")),
                "engagement_rate": safe_float(attr.get("engagement_rate")),
                "cost_per_session": attr.get("cost_per_session"),
            }
        )
    top_fb_ads.sort(
        key=lambda row: (
            -safe_int(row.get("sessions")),
            safe_float(row.get("cost_per_session")) if row.get("cost_per_session") is not None else 999999,
            -safe_float(row.get("spend_7d")),
        )
    )

    google_campaigns = []
    for profile in google_profiles:
        google_campaigns.append(
            {
                "campaign_id": profile.get("campaign_id"),
                "campaign_name": profile.get("campaign_name"),
                "status": profile.get("status"),
                "channel_type": profile.get("channel_type"),
                "daily_budget": safe_float(profile.get("daily_budget")),
                "total_impressions": safe_int(profile.get("total_impressions")),
                "total_clicks": safe_int(profile.get("total_clicks")),
                "total_cost": safe_float(profile.get("total_cost")),
                "total_conversions": safe_float(profile.get("total_conversions")),
                "overall_ctr": safe_float(profile.get("overall_ctr")),
            }
        )
    google_campaigns.sort(key=lambda row: (-safe_float(row.get("total_cost")), -safe_int(row.get("total_clicks"))))

    alerts = build_ad_alerts(
        fb_profiles,
        attr_map,
        google_profiles,
        recent_decisions[:10],
        active_experiments,
    )
    truths = load_founder_truths()
    documented_learnings = ((truths.get("ads") or {}).get("established_learnings") or [])

    return {
        "generated_at": now_aest().isoformat(),
        "days": days,
        "documented_learnings": documented_learnings,
        "alerts": alerts,
        "facebook": {
            "daily_metrics": to_jsonable(fb[:limit]),
            "account_summary": {
                "total_ads": len(fb_profiles),
                "active_ads": sum(1 for row in fb_profiles if str(row.get("effective_status", "")).upper() == "ACTIVE"),
                "spend_7d": round(sum(safe_float(row.get("last_7d", {}).get("spend_aud")) for row in fb_profiles), 2),
                "impressions_7d": sum(safe_int(row.get("last_7d", {}).get("impressions")) for row in fb_profiles),
                "link_clicks_7d": sum(safe_int(row.get("last_7d", {}).get("link_clicks")) for row in fb_profiles),
                "sessions_total": safe_int(attr_summary.get("total_fb_sessions")),
                "engaged_sessions_total": safe_int(attr_summary.get("total_engaged_sessions")),
                "cost_per_session": attr_summary.get("cost_per_session"),
            },
            "top_ads": top_fb_ads[:10],
        },
        "google": {
            "daily_metrics": to_jsonable(google[:limit]),
            "account_summary": {
                "campaigns": len(google_profiles),
                "enabled_campaigns": sum(1 for row in google_profiles if str(row.get("status", "")).upper() == "ENABLED"),
                "total_impressions": sum(safe_int(row.get("total_impressions")) for row in google_profiles),
                "total_clicks": sum(safe_int(row.get("total_clicks")) for row in google_profiles),
                "total_cost": round(sum(safe_float(row.get("total_cost")) for row in google_profiles), 2),
                "total_conversions": round(sum(safe_float(row.get("total_conversions")) for row in google_profiles), 2),
            },
            "campaigns": google_campaigns[:10],
        },
        "experiments": {
            "active": to_jsonable(active_experiments[:10]),
            "recent": to_jsonable(recent_experiments[:10]),
            "recent_decisions": to_jsonable(recent_decisions[:10]),
        },
    }


def fetch_proposal_outcomes(sm, days: int, limit: int) -> dict[str, Any]:
    cutoff = (now_aest() - timedelta(days=days)).strftime("%Y-%m-%d")
    rows = list(sm["ceo_proposal_outcomes"].find({"date": {"$gte": cutoff}}, {"_id": 0}).limit(limit * 3))
    rows.sort(key=lambda row: (row.get("date", ""), str(row.get("updated_at", ""))), reverse=True)
    return {"days": days, "rows": to_jsonable(rows[:limit])}


def fetch_timeline(sm, days: int) -> dict[str, Any]:
    cutoff_iso = (now_aest() - timedelta(days=days)).isoformat()
    cutoff_date = (now_aest() - timedelta(days=days)).strftime("%Y-%m-%d")
    run_coll, run_source = get_pipeline_collection(sm)
    timeline = {
        "pipeline_runs": list(run_coll.find({"started_at": {"$gte": now_aest() - timedelta(days=days)}}, {"_id": 0}).limit(50)),
        "website_deploys": list(sm["website_deploy_events"].find({"timestamp": {"$gte": cutoff_iso}}, {"_id": 0}).limit(50)),
        "website_changes": list(sm["website_change_log"].find({"created_at": {"$gte": cutoff_iso}}, {"_id": 0}).limit(50)),
        "proposal_outcomes": list(sm["ceo_proposal_outcomes"].find({"date": {"$gte": cutoff_date}}, {"_id": 0}).limit(50)),
        "proposals": list(sm["ceo_proposals"].find({"date": {"$gte": cutoff_date}}, {"_id": 0}).limit(50)),
    }
    timeline["pipeline_runs"] = sort_rows(timeline["pipeline_runs"], "started_at")
    timeline["website_deploys"] = sort_rows(timeline["website_deploys"], "timestamp")
    timeline["website_changes"] = sort_rows(timeline["website_changes"], "created_at")
    timeline["proposal_outcomes"].sort(key=lambda row: (row.get("date", ""), str(row.get("updated_at", ""))), reverse=True)
    timeline["proposals"].sort(key=lambda row: (row.get("date", ""), str(row.get("updated_at", ""))), reverse=True)
    return {"days": days, "pipeline_source": run_source, "timeline": to_jsonable(timeline)}


def fetch_collection_counts(sm) -> dict[str, Any]:
    keys = [
        "ceo_proposals",
        "ceo_runs",
        "ceo_briefs",
        "ceo_tasks",
        "ceo_memory",
        "ceo_proposal_outcomes",
        "website_daily_metrics",
        "website_change_log",
        "website_deploy_events",
        "ad_daily_metrics",
        "ad_experiments",
        "ad_decisions",
        "google_ads_daily_metrics",
        "google_ads_profiles",
    ]
    counts = {name: retry_cosmos_read(lambda coll=sm[name]: coll.count_documents({})) for name in keys}
    return {"generated_at": now_aest().isoformat(), "counts": counts}


def fetch_active_listings() -> dict[str, Any]:
    client = get_client()
    try:
        db_gc = client["Gold_Coast"]
        skip = {"suburb_median_prices", "suburb_statistics", "change_detection_snapshots"}
        counts = {}
        coll_names = retry_cosmos_read(lambda: db_gc.list_collection_names())
        for coll in sorted(coll_names):
            if coll.startswith("system") or coll in skip:
                continue
            total = retry_cosmos_read(lambda coll_name=coll: db_gc[coll_name].count_documents({"listing_status": "for_sale"}))
            if total > 0:
                counts[coll] = total
            time.sleep(0.12)
        return {"generated_at": now_aest().isoformat(), "counts": counts}
    finally:
        client.close()


def main() -> None:
    parser = argparse.ArgumentParser(description="Read-only query broker for CEO tools")
    sub = parser.add_subparsers(dest="command", required=True)

    sub.add_parser("founder-truths")
    sub.add_parser("ops-summary")
    sub.add_parser("orchestrator-health")
    counts_p = sub.add_parser("collection-counts")
    counts_p.set_defaults(limit=0)
    sub.add_parser("active-listings")

    runs_p = sub.add_parser("pipeline-runs")
    runs_p.add_argument("--days", type=int, default=7)
    runs_p.add_argument("--limit", type=int, default=20)

    web_p = sub.add_parser("website-metrics")
    web_p.add_argument("--days", type=int, default=7)

    ad_p = sub.add_parser("ad-metrics")
    ad_p.add_argument("--days", type=int, default=7)
    ad_p.add_argument("--limit", type=int, default=50)

    outcomes_p = sub.add_parser("proposal-outcomes")
    outcomes_p.add_argument("--days", type=int, default=30)
    outcomes_p.add_argument("--limit", type=int, default=50)

    timeline_p = sub.add_parser("timeline")
    timeline_p.add_argument("--days", type=int, default=14)

    args = parser.parse_args()

    if args.command == "founder-truths":
        print(dumps_json(load_founder_truths()))
        return
    if args.command == "active-listings":
        print(dumps_json(fetch_active_listings()))
        return

    client = get_client()
    sm = client["system_monitor"]
    try:
        if args.command == "ops-summary":
            payload = fetch_ops_summary(sm)
        elif args.command == "orchestrator-health":
            payload = fetch_orchestrator_health(sm)
        elif args.command == "collection-counts":
            payload = fetch_collection_counts(sm)
        elif args.command == "pipeline-runs":
            payload = fetch_pipeline_runs(sm, args.days, args.limit)
        elif args.command == "website-metrics":
            payload = fetch_website_metrics(sm, args.days)
        elif args.command == "ad-metrics":
            payload = fetch_ad_metrics(sm, args.days, args.limit)
        elif args.command == "proposal-outcomes":
            payload = fetch_proposal_outcomes(sm, args.days, args.limit)
        elif args.command == "timeline":
            payload = fetch_timeline(sm, args.days)
        else:
            raise RuntimeError(f"Unsupported command: {args.command}")
        print(dumps_json(payload))
    finally:
        client.close()


if __name__ == "__main__":
    main()
