#!/usr/bin/env python3
"""
Website Change Log — tracks website changes, hypotheses, and impact measurements.

Mirrors ad-experiment-log.py pattern. Stores structured change records in
system_monitor.website_change_log with baseline metrics snapshots for
before/after impact analysis.

Usage:
    python3 scripts/website-change-log.py log \
        --title "Redesign property card CTA" \
        --type layout_change \
        --hypothesis "Larger green CTA increases property detail visits" \
        --files "src/components/PropertyCard.tsx,PropertyCard.module.css" \
        --pages "/for-sale" \
        --commit abc123 \
        --tags "cta,conversion"

    python3 scripts/website-change-log.py review --change <ID>
        # Compare baseline vs post-change metrics (7+ days after deploy)

    python3 scripts/website-change-log.py list
        # List all changes

    python3 scripts/website-change-log.py pending
        # Show changes 7+ days old without a review
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
    return client, client["system_monitor"]


def take_metrics_snapshot(sm, pages=None, days=7):
    """
    Capture a baseline metrics snapshot from website_daily_metrics.
    Returns aggregated metrics over the last N days, optionally scoped to pages.
    """
    from zoneinfo import ZoneInfo
    aest = ZoneInfo("Australia/Brisbane")
    today = datetime.now(aest)
    cutoff = (today - timedelta(days=days)).strftime("%Y-%m-%d")
    today_str = today.strftime("%Y-%m-%d")

    docs = list(sm["website_daily_metrics"].find({
        "date": {"$gte": cutoff, "$lte": today_str}
    }))

    if not docs:
        return {"error": "No daily metrics data available", "period_days": days}

    # Aggregate across all days
    total_sessions = sum(d.get("sessions", {}).get("total", 0) for d in docs)
    total_bounce = sum(d.get("engagement", {}).get("bounce", 0) for d in docs)
    durations = [d.get("engagement", {}).get("avg_duration_seconds", 0) for d in docs
                 if d.get("engagement", {}).get("avg_duration_seconds", 0) > 0]
    scrolls = [d.get("engagement", {}).get("avg_scroll_depth", 0) for d in docs
               if d.get("engagement", {}).get("avg_scroll_depth", 0) > 0]

    snapshot = {
        "captured_at": datetime.now(timezone.utc).isoformat(),
        "period_days": days,
        "date_range": f"{cutoff} → {today_str}",
        "days_with_data": len([d for d in docs if d.get("sessions", {}).get("total", 0) > 0]),
        "sessions_total": total_sessions,
        "bounce_rate": round(total_bounce / total_sessions * 100, 1) if total_sessions else 0,
        "avg_duration_seconds": round(sum(durations) / len(durations), 1) if durations else 0,
        "avg_scroll_depth": round(sum(scrolls) / len(scrolls), 1) if scrolls else 0,
        "engagement": {
            "bounce": sum(d.get("engagement", {}).get("bounce", 0) for d in docs),
            "light": sum(d.get("engagement", {}).get("light", 0) for d in docs),
            "engaged": sum(d.get("engagement", {}).get("engaged", 0) for d in docs),
            "deep": sum(d.get("engagement", {}).get("deep", 0) for d in docs),
        },
        "sources": {
            "facebook": sum(d.get("sources", {}).get("facebook", 0) for d in docs),
            "google": sum(d.get("sources", {}).get("google", 0) for d in docs),
            "direct": sum(d.get("sources", {}).get("direct", 0) for d in docs),
            "other": sum(d.get("sources", {}).get("other", 0) for d in docs),
        },
    }

    # Page-scoped metrics if requested
    if pages:
        page_metrics = {}
        for page_path in pages:
            page_views = 0
            page_sessions = 0
            for d in docs:
                p_data = d.get("pages", {}).get(page_path, {})
                page_views += p_data.get("views", 0)
                page_sessions += p_data.get("unique_sessions", 0)
            page_metrics[page_path] = {
                "views": page_views,
                "unique_sessions": page_sessions,
            }
        snapshot["page_metrics"] = page_metrics

    return snapshot


def cmd_log(args, sm):
    """Log a website change with baseline metrics snapshot."""
    from zoneinfo import ZoneInfo
    aest = ZoneInfo("Australia/Brisbane")

    files = [f.strip() for f in args.files.split(",")] if args.files else []
    pages = [p.strip() for p in args.pages.split(",")] if args.pages else []
    tags = [t.strip() for t in args.tags.split(",")] if args.tags else []

    # Auto-capture baseline
    baseline = take_metrics_snapshot(sm, pages=pages if pages else None)

    doc = {
        "date": datetime.now(aest).strftime("%Y-%m-%d"),
        "type": args.type,
        "title": args.title,
        "hypothesis": args.hypothesis or None,
        "files_changed": files,
        "pages_affected": pages,
        "deploy_commit": args.commit or None,
        "baseline_snapshot": baseline,
        "impact_snapshot": None,
        "tags": tags,
        "reasoning": args.reasoning or None,
        "reviewed": False,
        "review_notes": None,
        "created_at": datetime.now(timezone.utc).isoformat(),
    }

    result = sm["website_change_log"].insert_one(doc)
    change_id = str(result.inserted_id)

    print(f"✅ Change logged: {change_id}")
    print(f"  Title: {args.title}")
    print(f"  Type: {args.type}")
    if args.hypothesis:
        print(f"  Hypothesis: {args.hypothesis}")
    print(f"  Files: {len(files)}")
    print(f"  Pages: {', '.join(pages) if pages else 'all'}")
    print(f"  Baseline: {baseline.get('sessions_total', 0)} sessions over "
          f"{baseline.get('period_days', 7)} days")
    return change_id


def cmd_review(args, sm):
    """Review a change: compare baseline vs post-change metrics."""
    from bson import ObjectId

    change = sm["website_change_log"].find_one({"_id": ObjectId(args.change)})
    if not change:
        print(f"Change {args.change} not found")
        return

    pages = change.get("pages_affected", [])
    impact = take_metrics_snapshot(sm, pages=pages if pages else None)

    # Save the impact snapshot
    sm["website_change_log"].update_one(
        {"_id": ObjectId(args.change)},
        {"$set": {
            "impact_snapshot": impact,
            "reviewed": True,
            "review_notes": args.notes if hasattr(args, "notes") and args.notes else None,
        }}
    )

    baseline = change.get("baseline_snapshot", {})

    print(f"{'=' * 60}")
    print(f"CHANGE REVIEW: {change.get('title', '?')}")
    print(f"{'=' * 60}")
    print(f"  Type: {change.get('type', '?')}")
    print(f"  Date: {change.get('date', '?')}")
    if change.get("hypothesis"):
        print(f"  Hypothesis: {change['hypothesis']}")
    print(f"  Files: {', '.join(change.get('files_changed', []))}")
    print(f"  Pages: {', '.join(pages) if pages else 'all'}")

    print(f"\n--- Before vs After ---")
    b_sessions = baseline.get("sessions_total", 0)
    i_sessions = impact.get("sessions_total", 0)
    delta_sessions = i_sessions - b_sessions
    pct = round(delta_sessions / b_sessions * 100, 1) if b_sessions else 0

    print(f"  Sessions:     {b_sessions:>6} → {i_sessions:>6}  ({'+' if delta_sessions >= 0 else ''}{delta_sessions}, {'+' if pct >= 0 else ''}{pct}%)")

    b_bounce = baseline.get("bounce_rate", 0)
    i_bounce = impact.get("bounce_rate", 0)
    delta_bounce = round(i_bounce - b_bounce, 1)
    print(f"  Bounce rate:  {b_bounce:>5.1f}% → {i_bounce:>5.1f}%  ({'+' if delta_bounce >= 0 else ''}{delta_bounce}pp)")

    b_dur = baseline.get("avg_duration_seconds", 0)
    i_dur = impact.get("avg_duration_seconds", 0)
    delta_dur = round(i_dur - b_dur, 1)
    print(f"  Avg duration: {b_dur:>5.1f}s → {i_dur:>5.1f}s  ({'+' if delta_dur >= 0 else ''}{delta_dur}s)")

    b_scroll = baseline.get("avg_scroll_depth", 0)
    i_scroll = impact.get("avg_scroll_depth", 0)
    delta_scroll = round(i_scroll - b_scroll, 1)
    print(f"  Avg scroll:   {b_scroll:>5.1f}% → {i_scroll:>5.1f}%  ({'+' if delta_scroll >= 0 else ''}{delta_scroll}pp)")

    # Engagement comparison
    b_eng = baseline.get("engagement", {})
    i_eng = impact.get("engagement", {})
    print(f"\n  Engagement:")
    for tier in ["bounce", "light", "engaged", "deep"]:
        bv = b_eng.get(tier, 0)
        iv = i_eng.get(tier, 0)
        print(f"    {tier:>8}: {bv:>4} → {iv:>4}  ({'+' if iv - bv >= 0 else ''}{iv - bv})")

    # Page-level comparison if available
    b_pages = baseline.get("page_metrics", {})
    i_pages = impact.get("page_metrics", {})
    if b_pages or i_pages:
        print(f"\n  Page metrics:")
        all_paths = set(list(b_pages.keys()) + list(i_pages.keys()))
        for path in sorted(all_paths):
            bp = b_pages.get(path, {})
            ip = i_pages.get(path, {})
            bv = bp.get("views", 0)
            iv = ip.get("views", 0)
            print(f"    {path}: {bv} → {iv} views")

    print(f"\n  ✅ Impact snapshot saved and change marked as reviewed")


def cmd_list(args, sm):
    """List all website changes."""
    query = {}
    if hasattr(args, "days") and args.days:
        cutoff = (datetime.now(timezone.utc) - timedelta(days=args.days)).isoformat()
        query["created_at"] = {"$gte": cutoff}
    if hasattr(args, "reviewed") and args.reviewed is not None:
        if args.reviewed == "yes":
            query["reviewed"] = True
        elif args.reviewed == "no":
            query["reviewed"] = False

    changes = list(sm["website_change_log"].find(query))
    changes.sort(key=lambda c: c.get("created_at", ""), reverse=True)

    if not changes:
        print("No website changes logged yet.")
        return

    print(f"{'Date':<12} {'Type':<16} {'Reviewed':<10} {'Title':<40}")
    print("-" * 80)
    for c in changes:
        date = c.get("date", "?")
        ctype = c.get("type", "?")[:16]
        reviewed = "✅" if c.get("reviewed") else "⏳"
        title = c.get("title", "?")[:40]
        print(f"{date:<12} {ctype:<16} {reviewed:<10} {title}")

    print(f"\nTotal: {len(changes)} change(s)")


def cmd_pending(args, sm):
    """Show changes that are 7+ days old and unreviewed."""
    cutoff = (datetime.now(timezone.utc) - timedelta(days=7)).isoformat()
    pending = list(sm["website_change_log"].find({
        "reviewed": False,
        "created_at": {"$lt": cutoff},
    }))
    pending.sort(key=lambda c: c.get("created_at", ""))

    if not pending:
        print("✅ No pending reviews — all changes have been reviewed!")
        return

    print(f"⚠ {len(pending)} change(s) pending review (7+ days old):\n")
    for c in pending:
        change_id = str(c["_id"])
        days_old = (datetime.now(timezone.utc) -
                    datetime.fromisoformat(c.get("created_at", "2026-01-01")
                                          .replace("Z", "+00:00"))).days
        print(f"  [{c.get('type', '?')}] {c.get('title', '?')}")
        print(f"    ID: {change_id}")
        print(f"    Date: {c.get('date', '?')} ({days_old} days ago)")
        if c.get("hypothesis"):
            print(f"    Hypothesis: {c['hypothesis']}")
        print()

    print(f"Review with: python3 scripts/website-change-log.py review --change <ID>")


def main():
    parser = argparse.ArgumentParser(description="Website Change Log")
    sub = parser.add_subparsers(dest="command")

    # log
    log_p = sub.add_parser("log", help="Log a website change")
    log_p.add_argument("--title", required=True, help="Short description of the change")
    log_p.add_argument("--type", required=True,
                       choices=["layout_change", "copy_change", "new_page", "bug_fix",
                                "performance", "style_change", "feature", "config"],
                       help="Type of change")
    log_p.add_argument("--hypothesis", help="Expected impact (for testable changes)")
    log_p.add_argument("--files", help="Comma-separated list of files changed")
    log_p.add_argument("--pages", help="Comma-separated list of affected page paths")
    log_p.add_argument("--commit", help="GitHub commit SHA")
    log_p.add_argument("--tags", help="Comma-separated tags for searchability")
    log_p.add_argument("--reasoning", help="Why this change was made")

    # review
    rev_p = sub.add_parser("review", help="Review a change (baseline vs post-change)")
    rev_p.add_argument("--change", required=True, help="Change ID")
    rev_p.add_argument("--notes", help="Review notes")

    # list
    list_p = sub.add_parser("list", help="List all changes")
    list_p.add_argument("--days", type=int, help="Only show changes from last N days")
    list_p.add_argument("--reviewed", choices=["yes", "no"],
                        help="Filter by review status")

    # pending
    sub.add_parser("pending", help="Show changes pending review (7+ days old)")

    args = parser.parse_args()
    if not args.command:
        parser.print_help()
        return

    client, sm = connect()

    if args.command == "log":
        cmd_log(args, sm)
    elif args.command == "review":
        cmd_review(args, sm)
    elif args.command == "list":
        cmd_list(args, sm)
    elif args.command == "pending":
        cmd_pending(args, sm)

    client.close()


if __name__ == "__main__":
    main()
