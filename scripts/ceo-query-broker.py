#!/home/fields/venv/bin/python3
"""
Read-only query broker for CEO agents and founder reviews.

This script exposes a narrow set of approved queries instead of broad shell or
database access. It is intended to be called locally on the orchestrator VM.
"""

from __future__ import annotations

import argparse
from datetime import timedelta
from typing import Any

import time

from ceo_agent_lib import dumps_json, get_client, load_founder_truths, now_aest, retry_cosmos_read, to_jsonable


def get_pipeline_collection(sm):
    process_runs = sm["process_runs"]
    if retry_cosmos_read(lambda: process_runs.count_documents({}, limit=1)) > 0:
        return process_runs, "process_runs"
    return sm["orchestrator_runs"], "orchestrator_runs"


def fetch_ops_summary(sm) -> dict[str, Any]:
    run_coll, run_source = get_pipeline_collection(sm)
    runs = list(run_coll.find({}, {"_id": 0}).limit(20))
    latest_run = sorted(runs, key=lambda row: str(row.get("started_at", "")), reverse=True)[0] if runs else None
    latest_errors = list(sm["watchdog_runs"].find({}, {"_id": 0}).limit(20))
    latest_errors.sort(key=lambda row: str(row.get("started_at", "")), reverse=True)
    latest_props = list(sm["ceo_proposals"].find({"agent": {"$ne": "system"}}, {"_id": 0, "agent": 1, "date": 1, "status": 1, "updated_at": 1}).limit(30))
    latest_props.sort(key=lambda row: (row.get("date", ""), str(row.get("updated_at", ""))), reverse=True)
    return {
        "generated_at": now_aest().isoformat(),
        "pipeline_source": run_source,
        "latest_run": to_jsonable(latest_run),
        "recent_watchdog_runs": to_jsonable(latest_errors[:5]),
        "recent_proposals": to_jsonable(latest_props[:10]),
    }


def fetch_pipeline_runs(sm, days: int, limit: int) -> dict[str, Any]:
    cutoff = now_aest() - timedelta(days=days)
    run_coll, run_source = get_pipeline_collection(sm)
    rows = list(run_coll.find({"started_at": {"$gte": cutoff}}, {"_id": 0}).limit(limit * 5))
    rows.sort(key=lambda row: str(row.get("started_at", "")), reverse=True)
    return {"days": days, "limit": limit, "pipeline_source": run_source, "runs": to_jsonable(rows[:limit])}


def fetch_website_metrics(sm, days: int) -> dict[str, Any]:
    cutoff = (now_aest() - timedelta(days=days)).strftime("%Y-%m-%d")
    rows = list(sm["website_daily_metrics"].find({"date": {"$gte": cutoff}}, {"_id": 0}))
    rows.sort(key=lambda row: row.get("date", ""), reverse=True)
    return {"days": days, "rows": to_jsonable(rows)}


def fetch_ad_metrics(sm, days: int, limit: int) -> dict[str, Any]:
    cutoff = (now_aest() - timedelta(days=days)).strftime("%Y-%m-%d")
    fb = list(sm["ad_daily_metrics"].find({"date": {"$gte": cutoff}}, {"_id": 0}).limit(limit * 4))
    google = list(sm["google_ads_daily_metrics"].find({"date": {"$gte": cutoff}}, {"_id": 0}).limit(limit * 4))
    fb.sort(key=lambda row: row.get("date", ""), reverse=True)
    google.sort(key=lambda row: row.get("date", ""), reverse=True)
    return {"days": days, "facebook": to_jsonable(fb[:limit]), "google": to_jsonable(google[:limit])}


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
    timeline["pipeline_runs"].sort(key=lambda row: str(row.get("started_at", "")), reverse=True)
    timeline["website_deploys"].sort(key=lambda row: row.get("timestamp", ""), reverse=True)
    timeline["website_changes"].sort(key=lambda row: row.get("created_at", ""), reverse=True)
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
