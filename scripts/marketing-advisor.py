#!/usr/bin/env python3
"""
Marketing Advisor — Claude-powered marketing decision engine.

Collects all available data (FB ads, page metrics, stage tracker, listings,
post history, institutional memory), sends it to Claude, and writes
suggested actions to the marketing_actions queue for human approval.

Usage:
    python3 scripts/marketing-advisor.py              # Run advisor, write actions to DB
    python3 scripts/marketing-advisor.py --print       # Print context + actions, don't save
    python3 scripts/marketing-advisor.py --dry-run     # Call Claude but don't write to DB
"""

import os
import sys
import json
import argparse
from datetime import datetime, timezone, timedelta
from dotenv import load_dotenv
from pymongo import MongoClient
import anthropic

load_dotenv("/home/fields/Fields_Orchestrator/.env")

COSMOS_URI = os.environ["COSMOS_CONNECTION_STRING"]
ANTHROPIC_API_KEY = os.environ.get("ANTHROPIC_API_KEY") or open("/etc/environment").read().split("ANTHROPIC_API_KEY=")[1].split("\n")[0].strip().strip('"')

# ── Action tools for Claude ─────────────────────────────────────────────

ACTION_TOOLS = [
    {
        "name": "suggest_page_post",
        "description": "Suggest an organic post to the Facebook page. The post will be queued for human approval before publishing. Use live data from the context to create data-led, insight-driven posts. Follow the Fields editorial voice: no superlatives, no real estate clichés, data-first.",
        "input_schema": {
            "type": "object",
            "properties": {
                "message": {
                    "type": "string",
                    "description": "The full post text to publish to the Facebook page. Include line breaks for readability."
                },
                "reasoning": {
                    "type": "string",
                    "description": "Why this post, why now. Reference data or patterns from institutional memory."
                },
                "priority": {
                    "type": "integer",
                    "description": "1 = do this first, 2 = important, 3 = nice to have",
                    "enum": [1, 2, 3]
                },
                "link": {
                    "type": "string",
                    "description": "Optional URL to attach to the post (e.g. fieldsestate.com.au/for-sale)"
                }
            },
            "required": ["message", "reasoning", "priority"]
        }
    },
    {
        "name": "suggest_ad_edit",
        "description": "Suggest editing an existing Facebook ad's copy (headline or body text). Only suggest changes backed by performance data or institutional memory patterns.",
        "input_schema": {
            "type": "object",
            "properties": {
                "campaign_name": {
                    "type": "string",
                    "description": "Name of the campaign containing the ad"
                },
                "field": {
                    "type": "string",
                    "description": "Which field to edit",
                    "enum": ["headline", "body", "cta"]
                },
                "current_value": {
                    "type": "string",
                    "description": "Current text (if known from context)"
                },
                "proposed_value": {
                    "type": "string",
                    "description": "New text to replace it with"
                },
                "reasoning": {
                    "type": "string",
                    "description": "Why this change. Reference performance data."
                },
                "priority": {
                    "type": "integer",
                    "enum": [1, 2, 3]
                }
            },
            "required": ["campaign_name", "field", "proposed_value", "reasoning", "priority"]
        }
    },
    {
        "name": "suggest_pipeline_run",
        "description": "Suggest running an article generation pipeline. Only suggest if there's a clear reason (e.g. new sold data, stale content, performance gap).",
        "input_schema": {
            "type": "object",
            "properties": {
                "pipeline": {
                    "type": "string",
                    "description": "Which pipeline to run",
                    "enum": ["how_it_sold", "watch_this_sale", "is_now_good_time", "light_rail", "update_pass"]
                },
                "reasoning": {
                    "type": "string",
                    "description": "Why run this pipeline now"
                },
                "priority": {
                    "type": "integer",
                    "enum": [1, 2, 3]
                }
            },
            "required": ["pipeline", "reasoning", "priority"]
        }
    },
    {
        "name": "suggest_insight",
        "description": "Share an observation, pattern, or recommendation that doesn't map to a specific action. Use this for strategic notes, warnings, or things Will should know.",
        "input_schema": {
            "type": "object",
            "properties": {
                "title": {
                    "type": "string",
                    "description": "Short title for the insight (max 60 chars)"
                },
                "body": {
                    "type": "string",
                    "description": "The full insight text"
                },
                "priority": {
                    "type": "integer",
                    "enum": [1, 2, 3]
                }
            },
            "required": ["title", "body", "priority"]
        }
    },
]


# ── Context collection ───────────────────────────────────────────────────

def collect_context():
    """Pull all data sources into a single context dict for Claude."""
    client = MongoClient(COSMOS_URI)
    ctx = {}

    # 1. Marketing stage
    sm = client["system_monitor"]
    stage_doc = sm["marketing_stage"].find_one({"_id": "current"})
    if stage_doc:
        stage_doc.pop("_id", None)
        ctx["marketing_stage"] = stage_doc

    # 2. Facebook Ads snapshot
    ads_doc = sm["facebook_ads"].find_one({"_id": "latest"})
    if ads_doc:
        ads_doc.pop("_id", None)
        ctx["facebook_ads"] = ads_doc

    # 3. Recent page posts (last 14 days from our log)
    # CosmosDB: sort by _id (always indexed) instead of posted_at
    recent_posts = list(sm["fb_page_posts"].find(
        {},
        {"_id": 0}
    ).sort("_id", -1).limit(20))
    ctx["recent_page_posts"] = recent_posts
    ctx["recent_page_posts_count"] = len(recent_posts)

    # 4. Institutional memory (past test results)
    past_tests = list(sm["fb_ad_tests"].find(
        {},
        {"_id": 0}
    ).sort("_id", -1).limit(20))
    ctx["institutional_memory"] = past_tests

    # 5. Active listing counts per suburb
    fs_db = client["Gold_Coast_Currently_For_Sale"]
    suburb_counts = {}
    for col_name in fs_db.list_collection_names():
        if col_name in ("suburb_median_prices", "suburb_statistics",
                        "change_detection_snapshots"):
            continue
        count = fs_db[col_name].count_documents({})
        if count > 0:
            suburb_counts[col_name] = count
    ctx["active_listings"] = suburb_counts
    ctx["total_active_listings"] = sum(suburb_counts.values())

    # 6. Suburb median prices (if available)
    medians = {}
    stats_col = fs_db["suburb_statistics"]
    for doc in stats_col.find({}, {"_id": 0, "suburb": 1, "median_price": 1,
                                    "total_listings": 1, "avg_days_on_market": 1}):
        sub = doc.get("suburb", "unknown")
        medians[sub] = doc
    if medians:
        ctx["suburb_statistics"] = medians

    # 7. Recent sold properties (sample from each suburb)
    sold_db = client["Gold_Coast_Recently_Sold"]
    recent_sold = []
    for col_name in sold_db.list_collection_names():
        try:
            docs = list(sold_db[col_name].find(
                {},
                {"_id": 0, "address": 1, "price": 1, "suburb": 1,
                 "sold_date": 1, "bedrooms": 1, "property_type": 1}
            ).sort("_id", -1).limit(5))
            recent_sold.extend(docs)
        except Exception:
            pass
    ctx["recent_sold_count"] = len(recent_sold)
    if recent_sold:
        ctx["recent_sold_sample"] = recent_sold[:10]

    # 8. Previous advisor runs (last 3)
    prev_runs = list(sm["marketing_advisor_runs"].find(
        {},
        {"_id": 0, "run_at": 1, "actions_suggested": 1, "actions_approved": 1}
    ).sort("_id", -1).limit(3))
    ctx["previous_advisor_runs"] = prev_runs

    # 9. Pending actions still awaiting approval
    pending = list(sm["marketing_actions"].find(
        {"status": "pending_approval"},
        {"_id": 0, "action_type": 1, "summary": 1, "created_at": 1}
    ).sort("_id", -1).limit(10))
    ctx["pending_actions"] = pending

    # 10. Current date/time
    ctx["current_time"] = datetime.now(timezone.utc).isoformat()
    ctx["current_time_aest"] = (datetime.now(timezone.utc) + timedelta(hours=10)).strftime("%Y-%m-%d %H:%M AEST")

    client.close()
    return ctx


def build_system_prompt(ctx):
    """Build the system prompt with current stage context."""
    stage = ctx.get("marketing_stage", {})
    stage_num = stage.get("stage", 0)
    stage_name = stage.get("stage_name", "Cold Start")
    stage_obj = stage.get("stage_objective", "Awareness / Reach")

    return f"""You are the Fields Estate marketing advisor. You run 2-3 times per day and suggest marketing actions for Will Simpson to approve.

## Current Stage: {stage_num} — {stage_name}
Objective: {stage_obj}

## Your Role
- Analyse all available data and suggest 2-5 prioritised actions
- Every suggestion must include clear reasoning backed by data
- Only suggest actions appropriate to the current stage
- Use the tools provided to structure your suggestions

## Stage 0 Rules (Cold Start)
- Focus on organic page posts with real data from live listings
- Post variety: suburb snapshots, price comparisons, listing counts, bedroom breakdowns
- No selling, no calls to action about services — pure data and insight
- Content should be interesting to a stranger who doesn't know Fields Estate
- Track what content types get saves and shares (these are the signals that matter)
- Ad objective should be awareness/reach, not traffic or conversions

## Editorial Voice
- Brand tagline: "Know your ground"
- Never use: "stunning", "nestled", "boasting", "rare opportunity", "robust market"
- Numbers: $1,250,000 not "$1.25m", suburbs always capitalised
- Tone: data-led, honest, no hype

## What NOT to suggest
- Don't suggest the same type of post that was just posted recently (check recent_page_posts)
- Don't suggest actions that are already pending approval (check pending_actions)
- Don't suggest ad changes if there's insufficient performance data
- Don't suggest budget increases at Stage 0
- Don't repeat insights from previous runs

## Data Available
You'll receive a JSON context with: marketing stage + milestones, Facebook Ads performance, recent page posts, listing data by suburb, sold data, institutional memory from past tests, and previous advisor run summaries.

Use this data to make specific, actionable suggestions. Reference specific numbers, suburbs, and trends."""


def call_claude(ctx, system_prompt):
    """Call Claude API with context and action tools."""
    client = anthropic.Anthropic(api_key=ANTHROPIC_API_KEY)

    # Build the user message with context
    user_msg = f"""Here is the current data context:

```json
{json.dumps(ctx, indent=2, default=str)}
```

IMPORTANT: You MUST suggest between 3 and 5 actions using the tools. Each action must be a separate tool call. Aim for variety — mix different action types (page posts, insights, pipeline runs). For page posts, write the COMPLETE post text ready to publish, using specific numbers from the data.

Do not repeat the same content type as the most recent page post. Start with a brief analysis (2-3 sentences), then make your tool calls."""

    response = client.messages.create(
        model="claude-sonnet-4-20250514",
        max_tokens=4096,
        system=system_prompt,
        tools=ACTION_TOOLS,
        messages=[{"role": "user", "content": user_msg}],
    )

    return response


def extract_actions(response):
    """Extract tool use blocks from Claude's response."""
    actions = []
    text_parts = []

    for block in response.content:
        if block.type == "tool_use":
            action = {
                "action_type": block.name,
                "tool_use_id": block.id,
                **block.input,
            }
            # Build a summary for display
            if block.name == "suggest_page_post":
                action["summary"] = block.input.get("message", "")[:100] + "..."
            elif block.name == "suggest_ad_edit":
                action["summary"] = f"Edit {block.input.get('field', '')} on {block.input.get('campaign_name', '')}"
            elif block.name == "suggest_pipeline_run":
                action["summary"] = f"Run {block.input.get('pipeline', '')} pipeline"
            elif block.name == "suggest_insight":
                action["summary"] = block.input.get("title", "")
            actions.append(action)
        elif block.type == "text":
            text_parts.append(block.text)

    return actions, "\n".join(text_parts)


def save_actions(actions, run_summary):
    """Write actions to MongoDB marketing_actions queue."""
    client = MongoClient(COSMOS_URI)
    sm = client["system_monitor"]
    now = datetime.now(timezone.utc).isoformat()

    action_ids = []
    for i, action in enumerate(actions):
        doc = {
            "action_type": action["action_type"],
            "status": "pending_approval",
            "priority": action.get("priority", 2),
            "summary": action.get("summary", ""),
            "details": {k: v for k, v in action.items()
                        if k not in ("action_type", "summary", "tool_use_id")},
            "reasoning": action.get("reasoning", ""),
            "created_at": now,
            "run_id": run_summary["run_id"],
            "sequence": i + 1,
        }
        result = sm["marketing_actions"].insert_one(doc)
        action_ids.append(str(result.inserted_id))

    # Log the run
    run_summary["action_ids"] = action_ids
    sm["marketing_advisor_runs"].insert_one(run_summary)

    client.close()
    return action_ids


def main():
    parser = argparse.ArgumentParser(description="Marketing Advisor — Claude-powered action suggestions")
    parser.add_argument("--print", action="store_true", help="Print context without calling Claude")
    parser.add_argument("--dry-run", action="store_true", help="Call Claude but don't save to DB")
    args = parser.parse_args()

    print(f"[{datetime.now(timezone.utc).isoformat()}] Marketing Advisor starting...")

    # Collect context
    print("Collecting context...")
    ctx = collect_context()

    if args.print:
        print(json.dumps(ctx, indent=2, default=str))
        return

    # Build prompt and call Claude
    system_prompt = build_system_prompt(ctx)
    print(f"Context collected: {len(json.dumps(ctx, default=str)):,} chars")
    print(f"Stage: {ctx.get('marketing_stage', {}).get('stage', '?')} — {ctx.get('marketing_stage', {}).get('stage_name', '?')}")
    print(f"Active listings: {ctx.get('total_active_listings', 0)}")
    print(f"Pending actions: {len(ctx.get('pending_actions', []))}")
    print()

    print("Calling Claude...")
    response = call_claude(ctx, system_prompt)
    actions, commentary = extract_actions(response)

    print(f"\nClaude suggested {len(actions)} actions:")
    for i, action in enumerate(actions, 1):
        priority_label = {1: "HIGH", 2: "MEDIUM", 3: "LOW"}.get(action.get("priority", 2), "?")
        print(f"  {i}. [{priority_label}] {action['action_type']}: {action.get('summary', '')}")
        if action.get("reasoning"):
            print(f"     Reason: {action['reasoning'][:120]}")

    if commentary:
        print(f"\nCommentary:\n{commentary[:500]}")

    if args.dry_run:
        print("\n(Dry run — actions not saved)")
        return

    # Save to MongoDB
    run_id = f"run_{datetime.now(timezone.utc).strftime('%Y%m%d_%H%M%S')}"
    run_summary = {
        "run_id": run_id,
        "run_at": datetime.now(timezone.utc).isoformat(),
        "actions_suggested": len(actions),
        "actions_approved": 0,
        "actions_rejected": 0,
        "commentary": commentary[:500] if commentary else "",
        "context_size_chars": len(json.dumps(ctx, default=str)),
        "model": "claude-sonnet-4-20250514",
        "stage": ctx.get("marketing_stage", {}).get("stage", 0),
    }

    action_ids = save_actions(actions, run_summary)
    print(f"\nSaved {len(action_ids)} actions to system_monitor.marketing_actions")
    print(f"Run ID: {run_id}")
    print("Actions are pending approval in the Marketing Monitor tab.")


if __name__ == "__main__":
    main()
