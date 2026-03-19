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
            {"system": "orchestrator", "started_at": {"$gte": cutoff}, "status": {"$nin": ["failed_stale"]}},
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
    rows = list(run_coll.find({"started_at": {"$gte": cutoff}}, {"_id": 0}).sort("started_at", -1).limit(limit * 5))
    rows = sort_rows(rows, "started_at")
    return {"days": days, "limit": limit, "pipeline_source": run_source, "runs": to_jsonable(rows[:limit])}


def fetch_website_metrics(sm, days: int) -> dict[str, Any]:
    """Fetch website analytics from PostHog API (replaced MongoDB CRM tracker 2026-03-19)."""
    import os, json
    from urllib.request import Request, urlopen

    api_key = os.environ.get("POSTHOG_PERSONAL_API_KEY", "")
    project_id = os.environ.get("POSTHOG_PROJECT_ID", "348370")
    if not api_key:
        return {"source": "posthog", "error": "POSTHOG_PERSONAL_API_KEY not set", "days": days}

    base = f"https://us.i.posthog.com/api/projects/{project_id}"
    headers = {"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"}
    cutoff = (now_aest() - timedelta(days=days)).isoformat()

    result: dict[str, Any] = {"source": "posthog", "days": days}

    try:
        # Aggregate events by day using PostHog's query API
        query_payload = json.dumps({"query": {
            "kind": "EventsQuery",
            "select": ["event", "properties.$current_url", "properties.$referring_domain", "properties.utm_source", "timestamp"],
            "after": cutoff,
            "limit": 1000,
            "event": "$pageview",
        }}).encode()
        req = Request(f"{base}/query/", data=query_payload, headers=headers, method="POST")
        with urlopen(req, timeout=30) as resp:
            data = json.loads(resp.read())

        rows = data.get("results", [])
        columns = data.get("columns", [])

        # Aggregate by day
        daily: dict[str, dict] = {}
        sources: dict[str, int] = {}
        pages: dict[str, int] = {}
        for row in rows:
            ts = row[4][:10] if len(row) > 4 and row[4] else "unknown"
            url = row[1] or ""
            ref = row[2] or "direct"
            utm = row[3] or ""

            day = daily.setdefault(ts, {"date": ts, "pageviews": 0})
            day["pageviews"] += 1

            source = utm if utm else ("facebook" if "facebook" in ref or "fb" in ref else "google" if "google" in ref else ref if ref else "direct")
            sources[source] = sources.get(source, 0) + 1

            path = url.split("fieldsestate.com.au")[-1].split("?")[0] if "fieldsestate.com.au" in url else url
            pages[path] = pages.get(path, 0) + 1

        result["daily"] = sorted(daily.values(), key=lambda d: d["date"])
        result["total_pageviews"] = sum(d["pageviews"] for d in daily.values())
        result["sources"] = dict(sorted(sources.items(), key=lambda x: -x[1])[:10])
        result["top_pages"] = dict(sorted(pages.items(), key=lambda x: -x[1])[:15])

        # Get feature flag info for experiments
        req2 = Request(f"{base}/feature_flags/", headers=headers)
        with urlopen(req2, timeout=15) as resp2:
            flags_data = json.loads(resp2.read())
        flags = [{"key": f["key"], "active": f["active"], "variants": list((f.get("filters", {}).get("multivariate", {}) or {}).get("variants", []))}
                 for f in flags_data.get("results", []) if f.get("key") in ("for_sale_page_v1", "discover_mode_v1")]
        result["experiments"] = flags

    except Exception as exc:
        result["error"] = str(exc)

    return result


def fetch_experiment_results(days: int) -> dict[str, Any]:
    """Fetch per-variant experiment data from PostHog for CEO agents."""
    import os, json
    from urllib.request import Request, urlopen
    from collections import defaultdict

    api_key = os.environ.get("POSTHOG_PERSONAL_API_KEY", "")
    project_id = os.environ.get("POSTHOG_PROJECT_ID", "348370")
    if not api_key:
        return {"source": "posthog", "error": "POSTHOG_PERSONAL_API_KEY not set", "days": days}

    base = f"https://us.i.posthog.com/api/projects/{project_id}"
    headers = {"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"}
    cutoff = (now_aest() - timedelta(days=days)).isoformat()
    result: dict[str, Any] = {"source": "posthog", "days": days, "experiments": {}}

    EXPERIMENT_FLAGS = ["for_sale_page_v1", "discover_mode_v1", "for_sale_signup_gate"]

    try:
        # 1. Feature flag calls — variant assignment counts
        query = json.dumps({"query": {
            "kind": "EventsQuery",
            "select": [
                "properties.$feature_flag",
                "properties.$feature_flag_response",
                "distinct_id",
                "timestamp",
            ],
            "after": cutoff,
            "limit": 2000,
            "event": "$feature_flag_called",
        }}).encode()
        req = Request(f"{base}/query/", data=query, headers=headers, method="POST")
        with urlopen(req, timeout=30) as resp:
            flag_data = json.loads(resp.read())

        # Build user→variant mapping per flag
        user_variants: dict[str, dict[str, str]] = defaultdict(dict)  # {distinct_id: {flag: variant}}
        variant_users: dict[str, dict[str, set]] = defaultdict(lambda: defaultdict(set))  # {flag: {variant: {users}}}
        for row in flag_data.get("results", []):
            flag, variant, uid = row[0], row[1], row[2]
            if flag and variant and uid:
                user_variants[uid][flag] = variant
                variant_users[flag][variant].add(uid)

        # 2. Pageviews — attribute to variants via distinct_id
        query = json.dumps({"query": {
            "kind": "EventsQuery",
            "select": ["properties.$current_url", "distinct_id", "timestamp"],
            "after": cutoff,
            "limit": 2000,
            "event": "$pageview",
        }}).encode()
        req = Request(f"{base}/query/", data=query, headers=headers, method="POST")
        with urlopen(req, timeout=30) as resp:
            pv_data = json.loads(resp.read())

        # 3. Custom events — attribute to variants
        custom_events: list[tuple] = []
        for evt in ["property_view", "tab_switch", "signup_gate_shown", "signup_gate_complete"]:
            query = json.dumps({"query": {
                "kind": "EventsQuery",
                "select": ["event", "distinct_id", "timestamp"],
                "after": cutoff,
                "limit": 500,
                "event": evt,
            }}).encode()
            req = Request(f"{base}/query/", data=query, headers=headers, method="POST")
            with urlopen(req, timeout=30) as resp:
                evt_data = json.loads(resp.read())
            for row in evt_data.get("results", []):
                custom_events.append((row[0], row[1], row[2]))

        # 4. Build per-experiment summary
        for flag in EXPERIMENT_FLAGS:
            if flag not in variant_users:
                continue
            exp: dict[str, Any] = {"flag": flag, "variants": {}}

            for variant, users in variant_users[flag].items():
                v_data: dict[str, Any] = {
                    "unique_users": len(users),
                    "pageviews": 0,
                    "page_breakdown": defaultdict(int),
                    "events": defaultdict(int),
                }

                # Count pageviews for users in this variant
                for row in pv_data.get("results", []):
                    url, uid = row[0] or "", row[1]
                    if uid in users:
                        v_data["pageviews"] += 1
                        path = url.split("fieldsestate.com.au")[-1].split("?")[0] if "fieldsestate.com.au" in url else url
                        v_data["page_breakdown"][path] += 1

                # Count custom events for users in this variant
                for evt_name, uid, _ts in custom_events:
                    if uid in users:
                        v_data["events"][evt_name] += 1

                v_data["page_breakdown"] = dict(sorted(v_data["page_breakdown"].items(), key=lambda x: -x[1])[:10])
                v_data["events"] = dict(v_data["events"])
                v_data["pages_per_user"] = round(v_data["pageviews"] / max(len(users), 1), 1)
                exp["variants"][variant] = v_data

            exp["total_users"] = sum(len(u) for u in variant_users[flag].values())
            result["experiments"][flag] = exp

        # 5. Overall funnel summary
        all_uids_with_pv = {row[1] for row in pv_data.get("results", [])}
        all_uids_with_events = {uid for _, uid, _ in custom_events}
        event_counts = defaultdict(int)
        for evt_name, _, _ in custom_events:
            event_counts[evt_name] += 1

        result["funnel_summary"] = {
            "total_visitors": len(all_uids_with_pv),
            "visitors_with_engagement": len(all_uids_with_pv & all_uids_with_events),
            "engagement_rate": round(len(all_uids_with_pv & all_uids_with_events) / max(len(all_uids_with_pv), 1) * 100, 1),
            "event_totals": dict(event_counts),
        }

    except Exception as exc:
        result["error"] = str(exc)

    return result


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


def fetch_cost_summary(sm, days: int) -> dict[str, Any]:
    """Fetch cost tracking data for agent analysis."""
    cutoff = (now_aest() - timedelta(days=days)).strftime("%Y-%m-%d")
    rows = list(retry_cosmos_read(
        lambda: sm["cost_tracking"].find({"date": {"$gte": cutoff}}, {"_id": 0})
    ))
    rows.sort(key=lambda r: r.get("date", ""))

    if not rows:
        return {"generated_at": now_aest().isoformat(), "days": days, "data": [], "note": "no cost data — run cost-collector.py first"}

    total = sum(r.get("total_daily_aud", 0) for r in rows)
    cat_totals: dict[str, float] = {}
    platform_totals: dict[str, float] = {}
    for row in rows:
        for cat, val in row.get("by_category", {}).items():
            cat_totals[cat] = cat_totals.get(cat, 0) + val
        for plat, pdata in row.get("platforms", {}).items():
            spend = pdata.get("spend_aud", 0)
            platform_totals[plat] = platform_totals.get(plat, 0) + spend

    daily_avg = total / len(rows) if rows else 0
    # Trend: last 7 days vs prior 7 days
    recent = [r for r in rows if r["date"] >= (now_aest() - timedelta(days=7)).strftime("%Y-%m-%d")]
    prior = [r for r in rows if r["date"] < (now_aest() - timedelta(days=7)).strftime("%Y-%m-%d")]
    recent_avg = sum(r.get("total_daily_aud", 0) for r in recent) / max(len(recent), 1)
    prior_avg = sum(r.get("total_daily_aud", 0) for r in prior) / max(len(prior), 1)
    trend_pct = round((recent_avg - prior_avg) / max(prior_avg, 0.01) * 100, 1) if prior_avg > 0 else 0

    # Flag cost anomalies (days where spend > 2x average)
    anomalies = [
        {"date": r["date"], "total": r.get("total_daily_aud", 0), "ratio": round(r.get("total_daily_aud", 0) / max(daily_avg, 0.01), 1)}
        for r in rows if r.get("total_daily_aud", 0) > daily_avg * 2
    ]

    return {
        "generated_at": now_aest().isoformat(),
        "days": days,
        "days_with_data": len(rows),
        "summary": {
            "total_aud": round(total, 2),
            "daily_average_aud": round(daily_avg, 2),
            "projected_monthly_aud": round(daily_avg * 30, 2),
            "trend_7d_vs_prior_pct": trend_pct,
        },
        "by_category": {k: round(v, 2) for k, v in sorted(cat_totals.items(), key=lambda x: -x[1])},
        "by_platform": {k: round(v, 2) for k, v in sorted(platform_totals.items(), key=lambda x: -x[1])},
        "anomalies": anomalies,
        "daily": to_jsonable([{
            "date": r["date"],
            "total": r.get("total_daily_aud", 0),
            "advertising": r.get("by_category", {}).get("advertising", 0),
            "ai_compute": r.get("by_category", {}).get("ai_compute", 0),
            "infrastructure": r.get("by_category", {}).get("infrastructure", 0),
        } for r in rows]),
    }


def fetch_collection_counts(sm) -> dict[str, Any]:
    keys = [
        "ceo_proposals",
        "ceo_runs",
        "ceo_briefs",
        "ceo_tasks",
        "ceo_memory",
        "ceo_proposal_outcomes",
        # website_daily_metrics DEPRECATED 2026-03-19: replaced by PostHog
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

    exp_p = sub.add_parser("experiment-results")
    exp_p.add_argument("--days", type=int, default=7)

    ad_p = sub.add_parser("ad-metrics")
    ad_p.add_argument("--days", type=int, default=7)
    ad_p.add_argument("--limit", type=int, default=50)

    outcomes_p = sub.add_parser("proposal-outcomes")
    outcomes_p.add_argument("--days", type=int, default=30)
    outcomes_p.add_argument("--limit", type=int, default=50)

    timeline_p = sub.add_parser("timeline")
    timeline_p.add_argument("--days", type=int, default=14)

    cost_p = sub.add_parser("cost-summary")
    cost_p.add_argument("--days", type=int, default=30)

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
        elif args.command == "experiment-results":
            payload = fetch_experiment_results(args.days)
        elif args.command == "ad-metrics":
            payload = fetch_ad_metrics(sm, args.days, args.limit)
        elif args.command == "proposal-outcomes":
            payload = fetch_proposal_outcomes(sm, args.days, args.limit)
        elif args.command == "timeline":
            payload = fetch_timeline(sm, args.days)
        elif args.command == "cost-summary":
            payload = fetch_cost_summary(sm, args.days)
        else:
            raise RuntimeError(f"Unsupported command: {args.command}")
        print(dumps_json(payload))
    finally:
        client.close()


if __name__ == "__main__":
    main()
