#!/usr/bin/env python3
"""
Website Deploy Tracker — logs Netlify deployment events to MongoDB.

Called after each `gh api` push of website files. Logs the deployment
event and links it to any matching website_change_log entry.

Usage:
    python3 scripts/website-deploy-tracker.py log \
        --commit abc123def \
        --files "src/components/PropertyCard.tsx,PropertyCard.module.css" \
        --message "Redesign property card CTA"

    python3 scripts/website-deploy-tracker.py list
        # List recent deploy events

    python3 scripts/website-deploy-tracker.py list --days 7
        # List deploys from last 7 days
"""

import os
import sys
import argparse
from datetime import datetime, timezone, timedelta
from dotenv import load_dotenv
from pymongo import MongoClient

load_dotenv("/home/fields/Fields_Orchestrator/.env")
COSMOS_URI = os.environ["COSMOS_CONNECTION_STRING"]


def connect():
    client = MongoClient(COSMOS_URI)
    return client, client["system_monitor"]


def cmd_log(args, sm):
    """Log a website deployment event."""
    files = [f.strip() for f in args.files.split(",")] if args.files else []

    doc = {
        "commit_sha": args.commit,
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "trigger": "github_push",
        "status": "success",
        "files_changed": files,
        "message": args.message or None,
        "change_log_id": None,
    }

    # Try to link to a website_change_log entry with matching commit
    if args.commit:
        change = sm["website_change_log"].find_one({"deploy_commit": args.commit})
        if change:
            doc["change_log_id"] = change["_id"]
            print(f"  Linked to change log: {change.get('title', '?')}")

    result = sm["website_deploy_events"].insert_one(doc)
    print(f"✅ Deploy event logged: {str(result.inserted_id)}")
    print(f"  Commit: {args.commit}")
    print(f"  Files: {len(files)}")
    if args.message:
        print(f"  Message: {args.message}")


def cmd_list(args, sm):
    """List recent deployment events."""
    query = {}
    if args.days:
        cutoff = (datetime.now(timezone.utc) - timedelta(days=args.days)).isoformat()
        query["timestamp"] = {"$gte": cutoff}

    deploys = list(sm["website_deploy_events"].find(query))
    deploys.sort(key=lambda d: d.get("timestamp", ""), reverse=True)

    if not deploys:
        print("No deploy events found.")
        return

    print(f"{'Timestamp':<22} {'Commit':<12} {'Files':>5}  {'Message'}")
    print("-" * 70)
    for d in deploys[:30]:
        ts = d.get("timestamp", "?")[:19]
        commit = (d.get("commit_sha") or "?")[:10]
        files = len(d.get("files_changed", []))
        msg = (d.get("message") or "-")[:30]
        print(f"{ts:<22} {commit:<12} {files:>5}  {msg}")

    print(f"\nTotal: {len(deploys)} deploy(s)")


def main():
    parser = argparse.ArgumentParser(description="Website Deploy Tracker")
    sub = parser.add_subparsers(dest="command")

    # log
    log_p = sub.add_parser("log", help="Log a deployment event")
    log_p.add_argument("--commit", required=True, help="GitHub commit SHA")
    log_p.add_argument("--files", help="Comma-separated list of files changed")
    log_p.add_argument("--message", help="Deploy message/description")

    # list
    list_p = sub.add_parser("list", help="List recent deploys")
    list_p.add_argument("--days", type=int, help="Only show deploys from last N days")

    args = parser.parse_args()
    if not args.command:
        parser.print_help()
        return

    client, sm = connect()

    if args.command == "log":
        cmd_log(args, sm)
    elif args.command == "list":
        cmd_list(args, sm)

    client.close()


if __name__ == "__main__":
    main()
