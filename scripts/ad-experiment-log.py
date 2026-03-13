#!/usr/bin/env python3
"""
Ad Experiment Log — tracks changes, hypotheses, and results for Facebook ad experiments.

Stores structured experiment records in system_monitor.ad_experiments.
Each experiment has: hypothesis, what changed, baseline snapshot, result snapshot, verdict.

Usage:
    python3 scripts/ad-experiment-log.py log \
        --name "Watch this sale vs Is now a good time" \
        --hypothesis "Property-specific stories get higher CTR than market timing articles" \
        --ads 120243339888070134,120243203837270134 \
        --notes "Comparing carousel watch-this-sale vs single-image market-timing"

    python3 scripts/ad-experiment-log.py snapshot --experiment <ID>
        # Takes a performance snapshot for an active experiment

    python3 scripts/ad-experiment-log.py review --experiment <ID>
        # Shows baseline vs current for analysis

    python3 scripts/ad-experiment-log.py close --experiment <ID> --verdict "winner|loser|inconclusive" \
        --learnings "What we learned"

    python3 scripts/ad-experiment-log.py list
        # List all experiments

    python3 scripts/ad-experiment-log.py history
        # Full experiment history with results
"""

import os
import sys
import json
import argparse
from datetime import datetime, timezone
from dotenv import load_dotenv
from pymongo import MongoClient

load_dotenv("/home/fields/Fields_Orchestrator/.env")
COSMOS_URI = os.environ["COSMOS_CONNECTION_STRING"]


def connect():
    client = MongoClient(COSMOS_URI)
    return client, client["system_monitor"]


def take_ad_snapshot(sm, ad_ids):
    """Capture current performance state for given ads."""
    snapshots = []
    for ad_id in ad_ids:
        profile = sm["ad_profiles"].find_one({"_id": ad_id})
        attribution = sm["ad_attribution"].find_one({"_id": ad_id})
        if not profile:
            snapshots.append({"ad_id": ad_id, "error": "not found"})
            continue

        snapshots.append({
            "ad_id": ad_id,
            "name": profile.get("name", ""),
            "effective_status": profile.get("effective_status", ""),
            "content_type": profile.get("creative", {}).get("content_type", ""),
            "text_style": profile.get("creative", {}).get("text_style", ""),
            "format": profile.get("creative", {}).get("format", ""),
            "campaign_name": profile.get("campaign_name", ""),
            "targeting": profile.get("targeting", {}),
            "last_7d": profile.get("last_7d", {}),
            "last_14d": profile.get("last_14d", {}),
            "last_30d": profile.get("last_30d", {}),
            "lifetime": profile.get("lifetime", {}),
            "attribution": {
                "sessions": (attribution or {}).get("sessions", 0),
                "engagement_rate": (attribution or {}).get("engagement_rate", 0),
                "bounce_rate": (attribution or {}).get("bounce_rate", 0),
                "avg_duration_seconds": (attribution or {}).get("avg_duration_seconds", 0),
                "cost_per_session": (attribution or {}).get("cost_per_session"),
                "properties_viewed_count": (attribution or {}).get("properties_viewed_count", 0),
            },
            "snapshot_at": datetime.now(timezone.utc).isoformat(),
        })
    return snapshots


def cmd_log(args, sm):
    """Log a new experiment."""
    ad_ids = [a.strip() for a in args.ads.split(",")]
    baseline = take_ad_snapshot(sm, ad_ids)

    doc = {
        "name": args.name,
        "hypothesis": args.hypothesis,
        "ad_ids": ad_ids,
        "status": "active",
        "created_at": datetime.now(timezone.utc).isoformat(),
        "notes": args.notes or "",
        "baseline_snapshot": baseline,
        "snapshots": [],
        "verdict": None,
        "learnings": None,
        "closed_at": None,
    }

    result = sm["ad_experiments"].insert_one(doc)
    exp_id = str(result.inserted_id)
    print(f"Experiment logged: {exp_id}")
    print(f"  Name: {args.name}")
    print(f"  Hypothesis: {args.hypothesis}")
    print(f"  Ads: {len(ad_ids)}")
    print(f"  Baseline captured with {len(baseline)} ad snapshots")
    return exp_id


def cmd_snapshot(args, sm):
    """Take a progress snapshot for an experiment."""
    from bson import ObjectId
    exp = sm["ad_experiments"].find_one({"_id": ObjectId(args.experiment)})
    if not exp:
        print(f"Experiment {args.experiment} not found")
        return

    snapshot = take_ad_snapshot(sm, exp["ad_ids"])
    sm["ad_experiments"].update_one(
        {"_id": ObjectId(args.experiment)},
        {"$push": {"snapshots": {
            "taken_at": datetime.now(timezone.utc).isoformat(),
            "ads": snapshot,
        }}}
    )
    print(f"Snapshot taken for experiment: {exp['name']}")
    print(f"  {len(snapshot)} ads captured")
    print(f"  Total snapshots: {len(exp.get('snapshots', [])) + 1}")


def cmd_review(args, sm):
    """Compare baseline vs current for an experiment."""
    from bson import ObjectId
    exp = sm["ad_experiments"].find_one({"_id": ObjectId(args.experiment)})
    if not exp:
        print(f"Experiment {args.experiment} not found")
        return

    current = take_ad_snapshot(sm, exp["ad_ids"])
    baseline = exp.get("baseline_snapshot", [])

    baseline_map = {s["ad_id"]: s for s in baseline}
    current_map = {s["ad_id"]: s for s in current}

    print(f"=" * 70)
    print(f"EXPERIMENT REVIEW: {exp['name']}")
    print(f"=" * 70)
    print(f"  Hypothesis: {exp['hypothesis']}")
    print(f"  Status: {exp['status']}")
    print(f"  Created: {exp['created_at']}")
    print(f"  Snapshots taken: {len(exp.get('snapshots', []))}")
    if exp.get("notes"):
        print(f"  Notes: {exp['notes']}")

    print(f"\n--- Baseline vs Current ---")
    for ad_id in exp["ad_ids"]:
        b = baseline_map.get(ad_id, {})
        c = current_map.get(ad_id, {})

        print(f"\n  Ad: {c.get('name', b.get('name', '?'))}")
        print(f"  Type: {c.get('content_type', '?')} / {c.get('text_style', '?')} / {c.get('format', '?')}")

        # Compare key metrics
        for window in ["last_7d", "lifetime"]:
            bw = b.get(window, {})
            cw = c.get(window, {})
            if not bw and not cw:
                continue

            b_imp = bw.get("impressions", 0)
            c_imp = cw.get("impressions", 0)
            b_ctr = bw.get("ctr", 0)
            c_ctr = cw.get("ctr", 0)
            b_spend = bw.get("spend_aud", 0)
            c_spend = cw.get("spend_aud", 0)

            delta_imp = c_imp - b_imp
            delta_spend = c_spend - b_spend

            print(f"  [{window}] Imp: {b_imp:,} → {c_imp:,} (+{delta_imp:,})")
            print(f"          CTR: {b_ctr:.2f}% → {c_ctr:.2f}%")
            print(f"          Spend: ${b_spend:.2f} → ${c_spend:.2f} (+${delta_spend:.2f})")

        # Attribution comparison
        ba = b.get("attribution", {})
        ca = c.get("attribution", {})
        if ba or ca:
            b_sess = ba.get("sessions", 0)
            c_sess = ca.get("sessions", 0)
            b_eng = ba.get("engagement_rate", 0)
            c_eng = ca.get("engagement_rate", 0)
            print(f"  [attribution] Sessions: {b_sess} → {c_sess}")
            print(f"                Eng rate: {b_eng:.1f}% → {c_eng:.1f}%")


def cmd_close(args, sm):
    """Close an experiment with a verdict."""
    from bson import ObjectId
    # Take final snapshot
    exp = sm["ad_experiments"].find_one({"_id": ObjectId(args.experiment)})
    if not exp:
        print(f"Experiment {args.experiment} not found")
        return

    final_snapshot = take_ad_snapshot(sm, exp["ad_ids"])

    sm["ad_experiments"].update_one(
        {"_id": ObjectId(args.experiment)},
        {"$set": {
            "status": "closed",
            "verdict": args.verdict,
            "learnings": args.learnings or "",
            "closed_at": datetime.now(timezone.utc).isoformat(),
        }, "$push": {"snapshots": {
            "taken_at": datetime.now(timezone.utc).isoformat(),
            "label": "final",
            "ads": final_snapshot,
        }}}
    )
    print(f"Experiment closed: {exp['name']}")
    print(f"  Verdict: {args.verdict}")
    if args.learnings:
        print(f"  Learnings: {args.learnings}")


def cmd_list(args, sm):
    """List all experiments."""
    experiments = list(sm["ad_experiments"].find().sort("_id", -1))
    if not experiments:
        print("No experiments logged yet.")
        return

    print(f"{'Status':<12} {'Created':<12} {'Name':<40} {'Ads':>4} {'Verdict':<15}")
    print("-" * 85)
    for exp in experiments:
        status = exp.get("status", "?")
        created = exp.get("created_at", "")[:10]
        name = exp.get("name", "?")[:40]
        ads = len(exp.get("ad_ids", []))
        verdict = exp.get("verdict") or "-"
        print(f"{status:<12} {created:<12} {name:<40} {ads:>4} {verdict:<15}")


def cmd_history(args, sm):
    """Full experiment history with learnings."""
    experiments = list(sm["ad_experiments"].find({"status": "closed"}).sort("_id", -1))
    if not experiments:
        print("No closed experiments yet.")
        return

    for exp in experiments:
        print(f"\n{'=' * 60}")
        print(f"  {exp.get('name', '?')}")
        print(f"  Hypothesis: {exp.get('hypothesis', '?')}")
        print(f"  Period: {exp.get('created_at', '')[:10]} → {exp.get('closed_at', '')[:10]}")
        print(f"  Verdict: {exp.get('verdict', '?')}")
        print(f"  Learnings: {exp.get('learnings', '-')}")
        print(f"  Ads tested: {len(exp.get('ad_ids', []))}")
        print(f"  Snapshots: {len(exp.get('snapshots', []))}")


def main():
    parser = argparse.ArgumentParser(description="Ad Experiment Log")
    sub = parser.add_subparsers(dest="command")

    # log
    log_p = sub.add_parser("log", help="Log a new experiment")
    log_p.add_argument("--name", required=True, help="Experiment name")
    log_p.add_argument("--hypothesis", required=True, help="What you're testing")
    log_p.add_argument("--ads", required=True, help="Comma-separated ad IDs")
    log_p.add_argument("--notes", help="Additional notes")

    # snapshot
    snap_p = sub.add_parser("snapshot", help="Take a progress snapshot")
    snap_p.add_argument("--experiment", required=True, help="Experiment ID")

    # review
    rev_p = sub.add_parser("review", help="Review baseline vs current")
    rev_p.add_argument("--experiment", required=True, help="Experiment ID")

    # close
    close_p = sub.add_parser("close", help="Close an experiment")
    close_p.add_argument("--experiment", required=True, help="Experiment ID")
    close_p.add_argument("--verdict", required=True,
                         choices=["winner", "loser", "inconclusive", "mixed"],
                         help="Experiment verdict")
    close_p.add_argument("--learnings", help="What we learned")

    # list
    sub.add_parser("list", help="List all experiments")

    # history
    sub.add_parser("history", help="Full history of closed experiments")

    args = parser.parse_args()

    if not args.command:
        parser.print_help()
        return

    client, sm = connect()

    if args.command == "log":
        cmd_log(args, sm)
    elif args.command == "snapshot":
        cmd_snapshot(args, sm)
    elif args.command == "review":
        cmd_review(args, sm)
    elif args.command == "close":
        cmd_close(args, sm)
    elif args.command == "list":
        cmd_list(args, sm)
    elif args.command == "history":
        cmd_history(args, sm)

    client.close()


if __name__ == "__main__":
    main()
