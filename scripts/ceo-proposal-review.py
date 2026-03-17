#!/home/fields/venv/bin/python3
"""
Record CEO proposal decisions and outcomes.

This closes the loop between proposal generation and real-world results so the
management agents can learn from accepted, rejected, and measured work.
"""

from __future__ import annotations

import argparse
from datetime import timedelta
from typing import Any

from ceo_agent_lib import dumps_json, get_client, now_aest, slugify


def find_proposal(sm, agent: str, date: str) -> dict[str, Any]:
    proposal = sm["ceo_proposals"].find_one({"agent": agent, "date": date})
    if not proposal:
        raise RuntimeError(f"Proposal not found for agent={agent} date={date}")
    return proposal


def normalize_title(title: str) -> str:
    return " ".join(title.split()).strip()


def find_proposal_item(proposal: dict[str, Any], title: str) -> dict[str, Any]:
    wanted = normalize_title(title).lower()
    for item in proposal.get("proposals", []):
        if normalize_title(item.get("title", "")).lower() == wanted:
            return item
    raise RuntimeError(f"Proposal item not found: {title}")


def record_review(sm, args) -> dict[str, Any]:
    proposal = find_proposal(sm, args.agent, args.date)
    item = find_proposal_item(proposal, args.title)
    now = now_aest().isoformat()
    status = args.decision
    proposal_id = f"{args.date}_{args.agent}_{slugify(item['title'])}"
    outcome_doc = {
        "_id": proposal_id,
        "agent": args.agent,
        "date": args.date,
        "proposal_title": item["title"],
        "decision": status,
        "decision_notes": args.notes,
        "decided_at": now,
        "reviewed_by": args.reviewed_by,
        "updated_at": now,
        "status": "reviewed",
    }
    sm["ceo_proposal_outcomes"].update_one(
        {"_id": proposal_id},
        {"$set": outcome_doc, "$setOnInsert": {"created_at": now}},
        upsert=True,
    )

    item_reviews = proposal.get("proposal_reviews", [])
    item_reviews = [r for r in item_reviews if r.get("proposal_title") != item["title"]]
    item_reviews.append(
        {
            "proposal_title": item["title"],
            "decision": status,
            "notes": args.notes,
            "reviewed_by": args.reviewed_by,
            "reviewed_at": now,
        }
    )
    overall_status = args.overall_status or proposal.get("status") or "pending_review"
    sm["ceo_proposals"].update_one(
        {"_id": proposal["_id"]},
        {
            "$set": {
                "status": overall_status,
                "review_notes": args.notes,
                "reviewed_by": args.reviewed_by,
                "updated_at": now,
                "proposal_reviews": item_reviews,
            }
        },
    )
    return outcome_doc


def record_outcome(sm, args) -> dict[str, Any]:
    proposal = find_proposal(sm, args.agent, args.date)
    item = find_proposal_item(proposal, args.title)
    proposal_id = f"{args.date}_{args.agent}_{slugify(item['title'])}"
    now = now_aest().isoformat()
    measured_after_days = args.measured_after_days
    outcome_doc = {
        "agent": args.agent,
        "date": args.date,
        "proposal_title": item["title"],
        "result": args.result,
        "impact_summary": args.impact_summary,
        "measured_after_days": measured_after_days,
        "metrics": args.metrics,
        "updated_at": now,
        "status": "measured",
    }
    sm["ceo_proposal_outcomes"].update_one(
        {"_id": proposal_id},
        {"$set": outcome_doc, "$setOnInsert": {"created_at": now}},
        upsert=True,
    )

    sm["ceo_memory"].update_one(
        {"record_type": "proposal_outcome", "proposal_id": proposal_id},
        {
            "$set": {
                "record_type": "proposal_outcome",
                "proposal_id": proposal_id,
                "agent": args.agent,
                "title": item["title"],
                "result": args.result,
                "impact_summary": args.impact_summary,
                "measured_after_days": measured_after_days,
                "metrics": args.metrics,
                "last_seen": now,
            },
            "$setOnInsert": {
                "first_seen": now,
                "times_seen": 0,
            },
            "$inc": {"times_seen": 1},
        },
        upsert=True,
    )
    return outcome_doc


def list_recent(sm, days: int) -> list[dict[str, Any]]:
    cutoff = (now_aest() - timedelta(days=days)).strftime("%Y-%m-%d")
    return list(
        sm["ceo_proposal_outcomes"]
        .find({"date": {"$gte": cutoff}}, {"_id": 0})
        .sort("updated_at", -1)
        .limit(100)
    )


def main() -> None:
    parser = argparse.ArgumentParser(description="Review and score CEO proposals")
    sub = parser.add_subparsers(dest="command", required=True)

    review = sub.add_parser("review")
    review.add_argument("--agent", required=True)
    review.add_argument("--date", required=True)
    review.add_argument("--title", required=True)
    review.add_argument("--decision", required=True, choices=["accepted", "rejected", "deferred"])
    review.add_argument("--notes", required=True)
    review.add_argument("--reviewed-by", default="will")
    review.add_argument("--overall-status", default="reviewed")

    outcome = sub.add_parser("outcome")
    outcome.add_argument("--agent", required=True)
    outcome.add_argument("--date", required=True)
    outcome.add_argument("--title", required=True)
    outcome.add_argument("--result", required=True, choices=["fixed", "improved", "no_impact", "regressed", "not_implemented"])
    outcome.add_argument("--impact-summary", required=True)
    outcome.add_argument("--measured-after-days", type=int, default=7)
    outcome.add_argument("--metrics", default="{}")

    listing = sub.add_parser("list")
    listing.add_argument("--days", type=int, default=30)

    args = parser.parse_args()
    client = get_client()
    sm = client["system_monitor"]
    try:
        if args.command == "review":
            payload = record_review(sm, args)
        elif args.command == "outcome":
            payload = record_outcome(sm, args)
        else:
            payload = list_recent(sm, args.days)
        print(dumps_json(payload))
    finally:
        client.close()


if __name__ == "__main__":
    main()
