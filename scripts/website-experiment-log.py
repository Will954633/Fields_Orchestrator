#!/usr/bin/env python3
"""
Website Experiment Log — tracks A/B tests on website changes.

Mirrors ad-experiment-log.py pattern. Stores structured experiment records
in system_monitor.website_experiments with baseline/progress/verdict snapshots.

Usage:
    python3 scripts/website-experiment-log.py create \
        --name "CTA green vs blue" \
        --hypothesis "Green CTA increases property detail visits by 15%" \
        --variant-key cta_color \
        --variants "control:Blue CTA,green_cta:Green CTA" \
        --pages "/for-sale" \
        --target-metric property_detail_ctr \
        --min-sessions 100

    python3 scripts/website-experiment-log.py snapshot --experiment <ID>
    python3 scripts/website-experiment-log.py review --experiment <ID>
    python3 scripts/website-experiment-log.py close --experiment <ID> --verdict winner --learnings "..."
    python3 scripts/website-experiment-log.py list
    python3 scripts/website-experiment-log.py history
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
    """Capture current website metrics for comparison."""
    from zoneinfo import ZoneInfo
    aest = ZoneInfo("Australia/Brisbane")
    today = datetime.now(aest)
    cutoff = (today - timedelta(days=days)).strftime("%Y-%m-%d")
    today_str = today.strftime("%Y-%m-%d")

    docs = list(sm["website_daily_metrics"].find({
        "date": {"$gte": cutoff, "$lte": today_str}
    }))

    if not docs:
        return {"error": "No daily metrics data", "period_days": days}

    total_sessions = sum(d.get("sessions", {}).get("total", 0) for d in docs)
    total_bounce = sum(d.get("engagement", {}).get("bounce", 0) for d in docs)
    durations = [d["engagement"]["avg_duration_seconds"] for d in docs
                 if d.get("engagement", {}).get("avg_duration_seconds", 0) > 0]

    snapshot = {
        "captured_at": datetime.now(timezone.utc).isoformat(),
        "period_days": days,
        "sessions_total": total_sessions,
        "bounce_rate": round(total_bounce / total_sessions * 100, 1) if total_sessions else 0,
        "avg_duration": round(sum(durations) / len(durations), 1) if durations else 0,
        "engagement": {
            "bounce": sum(d.get("engagement", {}).get("bounce", 0) for d in docs),
            "light": sum(d.get("engagement", {}).get("light", 0) for d in docs),
            "engaged": sum(d.get("engagement", {}).get("engaged", 0) for d in docs),
            "deep": sum(d.get("engagement", {}).get("deep", 0) for d in docs),
        },
    }

    # Extract per-variant data from experiments field
    variant_data = {}
    for d in docs:
        for key, variants in d.get("experiments", {}).items():
            if key not in variant_data:
                variant_data[key] = {}
            for vid, metrics in variants.items():
                if vid not in variant_data[key]:
                    variant_data[key][vid] = {"sessions": 0, "engaged": 0, "bounce_rate_sum": 0, "count": 0}
                variant_data[key][vid]["sessions"] += metrics.get("sessions", 0)
                variant_data[key][vid]["engaged"] += metrics.get("engaged", 0)
                if metrics.get("bounce_rate", 0) > 0:
                    variant_data[key][vid]["bounce_rate_sum"] += metrics["bounce_rate"]
                    variant_data[key][vid]["count"] += 1

    if variant_data:
        snapshot["variants"] = {}
        for key, variants in variant_data.items():
            snapshot["variants"][key] = {}
            for vid, data in variants.items():
                snapshot["variants"][key][vid] = {
                    "sessions": data["sessions"],
                    "engaged": data["engaged"],
                    "avg_bounce_rate": round(data["bounce_rate_sum"] / data["count"], 1) if data["count"] else 0,
                }

    return snapshot


def cmd_create(args, sm):
    """Create a new website experiment."""
    # Parse variants: "control:Blue CTA,green_cta:Green CTA"
    variants = []
    for v in args.variants.split(","):
        parts = v.strip().split(":", 1)
        vid = parts[0].strip()
        desc = parts[1].strip() if len(parts) > 1 else vid
        weight = 100 // len(args.variants.split(","))
        variants.append({"id": vid, "description": desc, "weight": weight})

    pages = [p.strip() for p in args.pages.split(",")] if args.pages else []

    baseline = take_metrics_snapshot(sm, pages=pages)

    doc = {
        "name": args.name,
        "hypothesis": args.hypothesis,
        "status": "active",
        "variant_key": args.variant_key,
        "variants": variants,
        "target_pages": pages,
        "target_metric": args.target_metric or None,
        "min_sessions_per_variant": args.min_sessions or 100,
        "baseline_snapshot": baseline,
        "snapshots": [],
        "verdict": None,
        "winning_variant": None,
        "learnings": None,
        "created_at": datetime.now(timezone.utc).isoformat(),
        "closed_at": None,
    }

    result = sm["website_experiments"].insert_one(doc)
    exp_id = str(result.inserted_id)

    print(f"✅ Experiment created: {exp_id}")
    print(f"  Name: {args.name}")
    print(f"  Hypothesis: {args.hypothesis}")
    print(f"  Variant key: {args.variant_key}")
    print(f"  Variants: {len(variants)}")
    for v in variants:
        print(f"    - {v['id']}: {v['description']} ({v['weight']}%)")
    print(f"  Pages: {', '.join(pages) if pages else 'all'}")
    print(f"  Min sessions/variant: {args.min_sessions or 100}")
    print(f"\n  Add to your React component:")
    print(f"    const variant = getVariant('{args.variant_key}', "
          f"[{', '.join(repr(v['id']) for v in variants)}]);")
    return exp_id


def cmd_snapshot(args, sm):
    """Take a progress snapshot for an experiment."""
    from bson import ObjectId
    exp = sm["website_experiments"].find_one({"_id": ObjectId(args.experiment)})
    if not exp:
        print(f"Experiment {args.experiment} not found")
        return

    snapshot = take_metrics_snapshot(sm, pages=exp.get("target_pages"))
    sm["website_experiments"].update_one(
        {"_id": ObjectId(args.experiment)},
        {"$push": {"snapshots": {
            "taken_at": datetime.now(timezone.utc).isoformat(),
            "label": args.label if hasattr(args, "label") and args.label else None,
            "metrics": snapshot,
        }}}
    )
    print(f"✅ Snapshot taken for: {exp['name']}")
    print(f"  Total snapshots: {len(exp.get('snapshots', [])) + 1}")
    print(f"  Sessions in snapshot: {snapshot.get('sessions_total', 0)}")


def cmd_review(args, sm):
    """Review baseline vs current for an experiment."""
    from bson import ObjectId
    exp = sm["website_experiments"].find_one({"_id": ObjectId(args.experiment)})
    if not exp:
        print(f"Experiment {args.experiment} not found")
        return

    current = take_metrics_snapshot(sm, pages=exp.get("target_pages"))
    baseline = exp.get("baseline_snapshot", {})

    print(f"{'=' * 60}")
    print(f"EXPERIMENT REVIEW: {exp['name']}")
    print(f"{'=' * 60}")
    print(f"  Hypothesis: {exp['hypothesis']}")
    print(f"  Status: {exp['status']}")
    print(f"  Created: {exp['created_at'][:10]}")
    print(f"  Variant key: {exp.get('variant_key', '?')}")
    print(f"  Snapshots taken: {len(exp.get('snapshots', []))}")

    # Overall metrics comparison
    print(f"\n--- Overall Metrics (baseline → current) ---")
    b_sess = baseline.get("sessions_total", 0)
    c_sess = current.get("sessions_total", 0)
    print(f"  Sessions:     {b_sess} → {c_sess}")
    print(f"  Bounce rate:  {baseline.get('bounce_rate', 0):.1f}% → {current.get('bounce_rate', 0):.1f}%")
    print(f"  Avg duration: {baseline.get('avg_duration', 0):.1f}s → {current.get('avg_duration', 0):.1f}s")

    # Per-variant comparison
    variant_key = exp.get("variant_key", "")
    c_variants = current.get("variants", {}).get(variant_key, {})
    if c_variants:
        print(f"\n--- Per-Variant Metrics (last 7d) ---")
        for v in exp.get("variants", []):
            vid = v["id"]
            vd = c_variants.get(vid, {})
            print(f"\n  {vid} ({v['description']}):")
            print(f"    Sessions: {vd.get('sessions', 0)}")
            print(f"    Engaged:  {vd.get('engaged', 0)}")
            print(f"    Bounce:   {vd.get('avg_bounce_rate', 0):.1f}%")
    else:
        print(f"\n  ⚠ No per-variant data yet — experiment needs traffic with variant tracking")

    # Check if we have enough data
    min_sessions = exp.get("min_sessions_per_variant", 100)
    all_have_enough = all(
        c_variants.get(v["id"], {}).get("sessions", 0) >= min_sessions
        for v in exp.get("variants", [])
    ) if c_variants else False

    if all_have_enough:
        print(f"\n  ✅ All variants have {min_sessions}+ sessions — ready to close")
    else:
        print(f"\n  ⏳ Need {min_sessions} sessions/variant before closing")


def cmd_close(args, sm):
    """Close an experiment with a verdict."""
    from bson import ObjectId
    exp = sm["website_experiments"].find_one({"_id": ObjectId(args.experiment)})
    if not exp:
        print(f"Experiment {args.experiment} not found")
        return

    final = take_metrics_snapshot(sm, pages=exp.get("target_pages"))

    sm["website_experiments"].update_one(
        {"_id": ObjectId(args.experiment)},
        {"$set": {
            "status": "closed",
            "verdict": args.verdict,
            "winning_variant": args.winner if hasattr(args, "winner") and args.winner else None,
            "learnings": args.learnings or "",
            "closed_at": datetime.now(timezone.utc).isoformat(),
        }, "$push": {"snapshots": {
            "taken_at": datetime.now(timezone.utc).isoformat(),
            "label": "final",
            "metrics": final,
        }}}
    )
    print(f"✅ Experiment closed: {exp['name']}")
    print(f"  Verdict: {args.verdict}")
    if hasattr(args, "winner") and args.winner:
        print(f"  Winner: {args.winner}")
    if args.learnings:
        print(f"  Learnings: {args.learnings}")


def cmd_list(args, sm):
    """List all experiments."""
    experiments = list(sm["website_experiments"].find())
    experiments.sort(key=lambda e: e.get("created_at", ""), reverse=True)

    if not experiments:
        print("No website experiments logged yet.")
        return

    print(f"{'Status':<10} {'Created':<12} {'Key':<20} {'Name':<30} {'Verdict'}")
    print("-" * 85)
    for exp in experiments:
        status = exp.get("status", "?")
        created = exp.get("created_at", "")[:10]
        key = exp.get("variant_key", "?")[:20]
        name = exp.get("name", "?")[:30]
        verdict = exp.get("verdict") or "-"
        print(f"{status:<10} {created:<12} {key:<20} {name:<30} {verdict}")


def cmd_history(args, sm):
    """Full history of closed experiments."""
    experiments = list(sm["website_experiments"].find({"status": "closed"}))
    experiments.sort(key=lambda e: e.get("created_at", ""), reverse=True)

    if not experiments:
        print("No closed website experiments yet.")
        return

    for exp in experiments:
        print(f"\n{'=' * 60}")
        print(f"  {exp.get('name', '?')}")
        print(f"  Hypothesis: {exp.get('hypothesis', '?')}")
        print(f"  Period: {exp.get('created_at', '')[:10]} → {exp.get('closed_at', '')[:10]}")
        print(f"  Variant key: {exp.get('variant_key', '?')}")
        print(f"  Verdict: {exp.get('verdict', '?')}")
        if exp.get("winning_variant"):
            print(f"  Winner: {exp['winning_variant']}")
        print(f"  Learnings: {exp.get('learnings', '-')}")
        print(f"  Snapshots: {len(exp.get('snapshots', []))}")


def main():
    parser = argparse.ArgumentParser(description="Website Experiment Log")
    sub = parser.add_subparsers(dest="command")

    # create
    create_p = sub.add_parser("create", help="Create a new experiment")
    create_p.add_argument("--name", required=True, help="Experiment name")
    create_p.add_argument("--hypothesis", required=True, help="What you're testing")
    create_p.add_argument("--variant-key", required=True,
                          help="Key for variant assignment (e.g. cta_color)")
    create_p.add_argument("--variants", required=True,
                          help="Comma-separated id:description pairs (e.g. 'control:Blue,green:Green')")
    create_p.add_argument("--pages", help="Comma-separated target page paths")
    create_p.add_argument("--target-metric", help="Primary success metric name")
    create_p.add_argument("--min-sessions", type=int, default=100,
                          help="Min sessions per variant for significance (default: 100)")

    # snapshot
    snap_p = sub.add_parser("snapshot", help="Take a progress snapshot")
    snap_p.add_argument("--experiment", required=True, help="Experiment ID")
    snap_p.add_argument("--label", help="Optional label (e.g. 'midpoint')")

    # review
    rev_p = sub.add_parser("review", help="Review baseline vs current")
    rev_p.add_argument("--experiment", required=True, help="Experiment ID")

    # close
    close_p = sub.add_parser("close", help="Close an experiment")
    close_p.add_argument("--experiment", required=True, help="Experiment ID")
    close_p.add_argument("--verdict", required=True,
                         choices=["winner", "loser", "inconclusive", "mixed"],
                         help="Experiment verdict")
    close_p.add_argument("--winner", help="Winning variant ID")
    close_p.add_argument("--learnings", help="What we learned")

    # list
    sub.add_parser("list", help="List all experiments")

    # history
    sub.add_parser("history", help="History of closed experiments")

    args = parser.parse_args()
    if not args.command:
        parser.print_help()
        return

    client, sm = connect()

    if args.command == "create":
        cmd_create(args, sm)
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
