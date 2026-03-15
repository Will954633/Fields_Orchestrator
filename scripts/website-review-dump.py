#!/usr/bin/env python3
"""
Website Review Dump — Interactive website performance review with change impact.

Mirrors ad-review-dump.py. Pulls from website_daily_metrics, website_change_log,
website_experiments, website_deploy_events, and CRM_All_Data.sessions.

Usage:
    python3 scripts/website-review-dump.py                # Full dump (14 days)
    python3 scripts/website-review-dump.py --days 7       # Last 7 days
    python3 scripts/website-review-dump.py --page /for-sale   # Single page deep dive
    python3 scripts/website-review-dump.py --changes      # Show changes + impact
    python3 scripts/website-review-dump.py --experiments   # Show active experiments
    python3 scripts/website-review-dump.py --summary      # High-level only
    python3 scripts/website-review-dump.py --json         # Machine-readable output
"""

import os
import sys
import json
import argparse
from datetime import datetime, timezone, timedelta
from dotenv import load_dotenv
from pymongo import MongoClient

load_dotenv("/home/fields/Fields_Orchestrator/.env")
COSMOS_URI = os.environ["COSMOS_CONNECTION_STRING"]


def connect():
    client = MongoClient(COSMOS_URI)
    sm = client["system_monitor"]
    crm = client["CRM_All_Data"]
    return client, sm, crm


def dump_daily_trend(sm, days, page_filter=None, as_json=False):
    """Print daily metrics trend table."""
    from zoneinfo import ZoneInfo
    aest = ZoneInfo("Australia/Brisbane")
    cutoff = (datetime.now(aest) - timedelta(days=days)).strftime("%Y-%m-%d")

    docs = list(sm["website_daily_metrics"].find({"date": {"$gte": cutoff}}))
    docs.sort(key=lambda d: d.get("date", ""))

    if as_json:
        return docs

    if not docs:
        print("  No daily metrics data found.")
        return

    print(f"\n{'Date':<12} {'Sess':>5} {'Uniq':>5} {'Ret':>4} "
          f"{'Bounce':>7} {'Light':>5} {'Eng':>4} {'Deep':>4} "
          f"{'Dur':>6} {'FB':>4} {'Ggl':>4} {'Dir':>4}")
    print("-" * 85)

    total_sessions = 0
    total_bounce = 0
    for d in docs:
        s = d.get("sessions", {})
        e = d.get("engagement", {})
        src = d.get("sources", {})
        sess = s.get("total", 0)
        total_sessions += sess
        total_bounce += e.get("bounce", 0)

        # Highlight if page filter applies
        if page_filter:
            p_data = d.get("pages", {}).get(page_filter, {})
            views = p_data.get("views", 0)
            suffix = f"  [{page_filter}: {views} views]"
        else:
            suffix = ""

        dur = e.get("avg_duration_seconds", 0)
        dur_str = f"{dur:.0f}s" if dur < 60 else f"{dur/60:.1f}m"

        print(f"{d['date']:<12} {sess:>5} {s.get('unique_visitors', 0):>5} "
              f"{s.get('returning', 0):>4} "
              f"{e.get('bounce', 0):>4}({e.get('bounce_rate', 0):>4.0f}%) "
              f"{e.get('light', 0):>5} {e.get('engaged', 0):>4} {e.get('deep', 0):>4} "
              f"{dur_str:>6} {src.get('facebook', 0):>4} {src.get('google', 0):>4} "
              f"{src.get('direct', 0):>4}{suffix}")

    # Summary row
    avg_bounce = round(total_bounce / total_sessions * 100, 1) if total_sessions else 0
    days_with_data = len([d for d in docs if d.get("sessions", {}).get("total", 0) > 0])
    avg_per_day = round(total_sessions / days_with_data) if days_with_data else 0
    print("-" * 85)
    print(f"  Total: {total_sessions} sessions over {days_with_data} days "
          f"({avg_per_day}/day avg, {avg_bounce}% bounce rate)")


def dump_changes(sm, days, as_json=False):
    """Print recent website changes with impact data."""
    cutoff = (datetime.now(timezone.utc) - timedelta(days=days)).isoformat()
    changes = list(sm["website_change_log"].find({"created_at": {"$gte": cutoff}}))
    changes.sort(key=lambda c: c.get("created_at", ""), reverse=True)

    if as_json:
        return changes

    if not changes:
        print("\n  No website changes in the last {} days.".format(days))
        return

    print(f"\n{'=' * 60}")
    print(f"WEBSITE CHANGES (last {days} days)")
    print(f"{'=' * 60}")

    pending = 0
    for c in changes:
        reviewed = "✅" if c.get("reviewed") else "⏳"
        if not c.get("reviewed"):
            pending += 1

        print(f"\n  {reviewed} [{c.get('type', '?')}] {c.get('title', '?')}")
        print(f"     Date: {c.get('date', '?')} | Files: {len(c.get('files_changed', []))}")
        if c.get("hypothesis"):
            print(f"     Hypothesis: {c['hypothesis']}")
        if c.get("pages_affected"):
            print(f"     Pages: {', '.join(c['pages_affected'])}")

        # Impact comparison
        b = c.get("baseline_snapshot", {})
        i = c.get("impact_snapshot")
        if i:
            b_sess = b.get("sessions_total", 0)
            i_sess = i.get("sessions_total", 0)
            delta = i_sess - b_sess
            pct = round(delta / b_sess * 100, 1) if b_sess else 0
            print(f"     Impact: {b_sess} → {i_sess} sessions "
                  f"({'+' if delta >= 0 else ''}{delta}, {'+' if pct >= 0 else ''}{pct}%)")
            print(f"     Bounce: {b.get('bounce_rate', 0):.1f}% → {i.get('bounce_rate', 0):.1f}%")

    print(f"\n  Total: {len(changes)} changes, {pending} pending review")


def dump_experiments(sm, as_json=False):
    """Print active and recent experiments."""
    experiments = list(sm["website_experiments"].find())
    experiments.sort(key=lambda e: e.get("created_at", ""), reverse=True)

    if as_json:
        return experiments

    if not experiments:
        print("\n  No website experiments logged yet.")
        return

    active = [e for e in experiments if e.get("status") == "active"]
    closed = [e for e in experiments if e.get("status") == "closed"]

    if active:
        print(f"\n{'=' * 60}")
        print(f"ACTIVE EXPERIMENTS ({len(active)})")
        print(f"{'=' * 60}")
        for exp in active:
            print(f"\n  {exp.get('name', '?')}")
            print(f"    Key: {exp.get('variant_key', '?')}")
            print(f"    Hypothesis: {exp.get('hypothesis', '?')}")
            print(f"    Started: {exp.get('created_at', '')[:10]}")
            print(f"    Variants: ", end="")
            for v in exp.get("variants", []):
                print(f"{v['id']} ({v.get('weight', '?')}%) ", end="")
            print()
            print(f"    Snapshots: {len(exp.get('snapshots', []))}")

    if closed:
        print(f"\n{'=' * 60}")
        print(f"CLOSED EXPERIMENTS ({len(closed)})")
        print(f"{'=' * 60}")
        for exp in closed[:5]:
            verdict = exp.get("verdict", "?")
            emoji = "🏆" if verdict == "winner" else "❌" if verdict == "loser" else "🤷"
            print(f"\n  {emoji} {exp.get('name', '?')} — {verdict}")
            print(f"    Period: {exp.get('created_at', '')[:10]} → {exp.get('closed_at', '')[:10]}")
            if exp.get("learnings"):
                print(f"    Learnings: {exp['learnings']}")


def dump_deploys(sm, days, as_json=False):
    """Print recent deploy events."""
    cutoff = (datetime.now(timezone.utc) - timedelta(days=days)).isoformat()
    deploys = list(sm["website_deploy_events"].find({"timestamp": {"$gte": cutoff}}))
    deploys.sort(key=lambda d: d.get("timestamp", ""), reverse=True)

    if as_json:
        return deploys

    if not deploys:
        return

    print(f"\n  Deploys in last {days} days: {len(deploys)}")
    for d in deploys[:10]:
        commit = (d.get("commit_sha") or "?")[:8]
        files = len(d.get("files_changed", []))
        msg = d.get("message") or "-"
        ts = d.get("timestamp", "?")[:16]
        print(f"    {ts} [{commit}] {files} files — {msg}")


def main():
    parser = argparse.ArgumentParser(description="Website Performance Review Dump")
    parser.add_argument("--days", type=int, default=14, help="Review period (default: 14)")
    parser.add_argument("--page", help="Deep dive on a specific page path")
    parser.add_argument("--changes", action="store_true", help="Show changes + impact only")
    parser.add_argument("--experiments", action="store_true", help="Show experiments only")
    parser.add_argument("--summary", action="store_true", help="High-level summary only")
    parser.add_argument("--json", dest="as_json", action="store_true", help="JSON output")
    args = parser.parse_args()

    client, sm, crm = connect()

    try:
        if args.as_json:
            output = {}
            output["daily"] = dump_daily_trend(sm, args.days, args.page, as_json=True)
            output["changes"] = dump_changes(sm, args.days, as_json=True)
            output["experiments"] = dump_experiments(sm, as_json=True)
            output["deploys"] = dump_deploys(sm, args.days, as_json=True)
            print(json.dumps(output, indent=2, default=str))
            return

        print("=" * 60)
        print(f"WEBSITE PERFORMANCE REVIEW — Last {args.days} days")
        print("=" * 60)

        if args.changes:
            dump_changes(sm, args.days)
            return

        if args.experiments:
            dump_experiments(sm)
            return

        # Full dump
        dump_daily_trend(sm, args.days, args.page)

        if not args.summary:
            dump_deploys(sm, args.days)
            dump_changes(sm, args.days)
            dump_experiments(sm)

    finally:
        client.close()


if __name__ == "__main__":
    main()
