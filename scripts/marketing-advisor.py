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
        "name": "suggest_article_post",
        "description": "Suggest a Facebook post that delivers genuine market insight and links to a specific published article on fieldsestate.com.au. Write 3-5 sentences of original analysis using live market data, targeted at a specific audience. The article link gives readers the full picture. This is the PRIMARY tool — use it for most suggestions.",
        "input_schema": {
            "type": "object",
            "properties": {
                "article_id": {
                    "type": "string",
                    "description": "The Ghost post ID of the article to link to (from article_index)."
                },
                "article_title": {
                    "type": "string",
                    "description": "Title of the article being linked (for verification)."
                },
                "article_url": {
                    "type": "string",
                    "description": "Full URL: https://fieldsestate.com.au/article/{article_id}"
                },
                "insight_text": {
                    "type": "string",
                    "description": "The full Facebook post text. 3-5 sentences of original analysis using specific numbers from the market data. Do NOT just summarize the article — deliver a standalone insight that makes the reader want to read more."
                },
                "audience": {
                    "type": "string",
                    "description": "Who specifically benefits from this insight.",
                    "enum": ["buyers_robina", "buyers_burleigh_waters", "buyers_varsity_lakes",
                             "sellers_robina", "sellers_burleigh_waters", "sellers_varsity_lakes",
                             "buyers_gold_coast", "sellers_gold_coast",
                             "investors_gold_coast", "general_gold_coast"]
                },
                "reasoning": {
                    "type": "string",
                    "description": "Why this post, why now, why this article. Must reference: (1) specific data signal from market_intelligence, (2) why this audience needs this insight, (3) what changed that makes it timely."
                },
                "priority": {
                    "type": "integer",
                    "description": "1 = do this first, 2 = important, 3 = nice to have",
                    "enum": [1, 2, 3]
                }
            },
            "required": ["article_id", "article_title", "article_url", "insight_text",
                          "audience", "reasoning", "priority"]
        }
    },
    {
        "name": "suggest_page_post",
        "description": "Suggest an organic Facebook post WITHOUT linking to an article. Use ONLY when no published article is relevant. The post must still deliver genuine market insight using live data — not just list facts.",
        "input_schema": {
            "type": "object",
            "properties": {
                "message": {
                    "type": "string",
                    "description": "The full post text. 3-5 sentences of original market analysis with specific numbers."
                },
                "reasoning": {
                    "type": "string",
                    "description": "Why this post, why now. Explain why no existing article is suitable."
                },
                "priority": {
                    "type": "integer",
                    "enum": [1, 2, 3]
                },
                "link": {
                    "type": "string",
                    "description": "Optional URL (e.g. fieldsestate.com.au/for-sale or /market)"
                }
            },
            "required": ["message", "reasoning", "priority"]
        }
    },
    {
        "name": "suggest_pipeline_run",
        "description": "Suggest running an article generation pipeline. Only suggest if there's a clear reason (e.g. new sold data, stale content, market shift that warrants new analysis).",
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
    {
        "name": "suggest_ad_pause",
        "description": "Recommend pausing an underperforming Facebook ad. Use when an ad has accumulated enough data (1,000+ impressions) but is clearly underperforming relative to other ads in the account. Cite specific metrics.",
        "input_schema": {
            "type": "object",
            "properties": {
                "ad_id": {
                    "type": "string",
                    "description": "The Facebook ad ID to pause."
                },
                "ad_name": {
                    "type": "string",
                    "description": "Name of the ad (for verification)."
                },
                "campaign_name": {
                    "type": "string",
                    "description": "Campaign this ad belongs to."
                },
                "metrics_cited": {
                    "type": "string",
                    "description": "Specific metrics justifying the pause (e.g., 'CTR 0.0% on 968 impressions, $2.47 spent with 0 clicks, 0 link clicks')."
                },
                "reasoning": {
                    "type": "string",
                    "description": "Full reasoning: why pause, what's wrong, what would be better."
                },
                "priority": {
                    "type": "integer",
                    "enum": [1, 2, 3]
                }
            },
            "required": ["ad_id", "ad_name", "campaign_name", "metrics_cited", "reasoning", "priority"]
        }
    },
    {
        "name": "suggest_ad_edit",
        "description": "Recommend editing the creative of an existing Facebook ad. Use when an ad has decent reach but poor engagement — suggesting the copy, headline, or CTA could be improved rather than the ad being paused entirely.",
        "input_schema": {
            "type": "object",
            "properties": {
                "ad_id": {
                    "type": "string",
                    "description": "The Facebook ad ID to edit."
                },
                "ad_name": {
                    "type": "string",
                    "description": "Name of the ad."
                },
                "campaign_name": {
                    "type": "string",
                    "description": "Campaign this ad belongs to."
                },
                "field": {
                    "type": "string",
                    "description": "Which creative field to change.",
                    "enum": ["body", "headline", "cta"]
                },
                "current_value": {
                    "type": "string",
                    "description": "The current value of the field being changed."
                },
                "proposed_value": {
                    "type": "string",
                    "description": "The new value to replace it with."
                },
                "reasoning": {
                    "type": "string",
                    "description": "Why this change, what hypothesis it tests, what metric should improve."
                },
                "priority": {
                    "type": "integer",
                    "enum": [1, 2, 3]
                }
            },
            "required": ["ad_id", "ad_name", "campaign_name", "field", "current_value",
                          "proposed_value", "reasoning", "priority"]
        }
    },
    {
        "name": "suggest_ad_create",
        "description": "Propose creating a new Facebook ad. Use to scale winning content themes (exploit) or test untried article/audience combinations (explore). New ads are always created in PAUSED state for Will to review before activating.",
        "input_schema": {
            "type": "object",
            "properties": {
                "ad_name": {
                    "type": "string",
                    "description": "Descriptive name for the ad (e.g. 'Is Now a Good Time to Buy: Burleigh Waters')."
                },
                "adset_id": {
                    "type": "string",
                    "description": "The ad set ID to place this ad in (from facebook_ads.ads context — use an existing traffic ad set)."
                },
                "article_id": {
                    "type": "string",
                    "description": "Ghost article ID to link to (from article_index)."
                },
                "article_url": {
                    "type": "string",
                    "description": "Full article URL: https://fieldsestate.com.au/article/{article_id}"
                },
                "headline": {
                    "type": "string",
                    "description": "The ad headline/title. Should be the article title or a compelling variant."
                },
                "body": {
                    "type": "string",
                    "description": "The ad copy. 3-5 sentences of data-led insight that makes someone want to click through. Follow editorial voice: specific numbers, no hype."
                },
                "image_source": {
                    "type": "string",
                    "description": "Use 'article_feature_image' to auto-download the article's Ghost feature image, or provide an existing image_hash from the ad account."
                },
                "strategy": {
                    "type": "string",
                    "description": "Is this scaling a proven winner (exploit) or testing a new hypothesis (explore)?",
                    "enum": ["exploit", "explore"]
                },
                "reasoning": {
                    "type": "string",
                    "description": "What pattern or data supports this ad? For exploit: which winning ad pattern are you replicating? For explore: what hypothesis are you testing?"
                },
                "priority": {
                    "type": "integer",
                    "enum": [1, 2, 3]
                }
            },
            "required": ["ad_name", "adset_id", "article_id", "article_url",
                          "headline", "body", "image_source", "strategy", "reasoning", "priority"]
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

    # 10. Post performance verdicts (institutional memory feedback)
    verdicts = list(sm["fb_ad_tests"].find(
        {"type": "post_performance"},
        {"_id": 0}
    ).sort("_id", -1).limit(20))
    ctx["post_verdicts"] = verdicts

    # 11. Article index (for matching insights to articles)
    article_docs = list(sm["article_index"].find(
        {},
        {"_id": 1, "title": 1, "url": 1, "excerpt": 1, "category": 1,
         "suburbs": 1, "tags": 1, "published_at": 1, "key_topics": 1}
    ))
    # Convert _id to string for JSON serialisation
    for doc in article_docs:
        doc["article_id"] = str(doc.pop("_id"))
    ctx["article_index"] = article_docs
    ctx["article_count"] = len(article_docs)

    # 12. Market intelligence snapshot
    intel_doc = sm["market_intelligence_snapshot"].find_one({"_id": "latest"})
    if intel_doc:
        intel_doc.pop("_id", None)
        ctx["market_intelligence"] = intel_doc

    # 13. Current date/time
    ctx["current_time"] = datetime.now(timezone.utc).isoformat()
    ctx["current_time_aest"] = (datetime.now(timezone.utc) + timedelta(hours=10)).strftime("%Y-%m-%d %H:%M AEST")

    client.close()
    return ctx


def build_system_prompt(ctx):
    """Build the system prompt with current stage context."""
    stage = ctx.get("marketing_stage", {})
    stage_num = stage.get("stage", 0)
    stage_name = stage.get("stage_name", "Cold Start")
    article_count = ctx.get("article_count", 0)
    intel = ctx.get("market_intelligence", {})
    high_urgency = intel.get("summary", {}).get("high_urgency", 0)

    return f"""You are the Fields Estate property intelligence advisor. Your job is to distribute genuine market insight to buyers and sellers on the Gold Coast via Facebook posts.

Mantra: "Right data to the right person at the right time."

## Current Stage: {stage_num} — {stage_name}

## Your Mission
Every post must pass the "Would I find this useful?" test. You are NOT a social media scheduler. You are a property intelligence distribution engine. Each post should help a buyer or seller make a better decision, backed by specific data.

Before suggesting any post, evaluate it against this framework:
- WHO: Which buyer/seller segment benefits? (Be specific: "First-home buyers in Robina")
- WHAT: What specific market signal or insight am I delivering?
- WHY NOW: What changed in the data that makes this timely?
- WHERE NEXT: Which article gives them the full picture?
- DATA: What specific numbers back this up?

If you cannot answer all five, do not suggest the post.

## Tools (in order of preference)
1. **suggest_article_post** (PRIMARY) — Write 3-5 sentences of original market analysis using live data, linked to a specific published article.
2. **suggest_ad_create** — Propose a new Facebook ad linking to an article. Always created PAUSED for Will to review. Mark as "exploit" (scaling a winner) or "explore" (testing new).
3. **suggest_page_post** (SECONDARY) — Only when no published article matches the insight.
4. **suggest_pipeline_run** — Trigger article generation when data warrants new content.
5. **suggest_insight** — Strategic observations for Will.
6. **suggest_ad_pause** — Recommend pausing an underperforming ad (must cite specific metrics).
7. **suggest_ad_edit** — Recommend changing ad copy/headline/CTA (must explain hypothesis).

## Article Library
You have {article_count} published articles. Check the article_index in your context to find the right article for each insight. Match by suburb, category, and key_topics.

Article categories:
- market-analysis: State of market, suburb comparisons, price trends
- market-update: How It Sold (recent sales case studies), Watch This Sale (listing spotlights)
- suburb-profile: Major projects, infrastructure (Light Rail, Olympics, etc.)
- buyer-guide: Timing strategy, what to look for, auction playbook
- seller-guide: Pricing strategy, market positioning

## Target Market — CRITICAL
Fields Estate's target suburbs are **Robina**, **Varsity Lakes**, and **Burleigh Waters** ONLY. All posts, ads, and content suggestions MUST focus on these three suburbs. Do NOT suggest content about Worongary, Merrimac, Mudgeeraba, Carrara, Reedy Creek, Burleigh Heads, or any other suburb — even if data or articles exist for them. We track data for surrounding suburbs to inform analysis, but our audience is buyers and sellers in these three suburbs only.

## Market Intelligence
You have {len(intel.get('insights', []))} fresh insights from tonight's data pipeline ({high_urgency} high-urgency signals). Start with high-urgency insights when choosing what to post about.

## Editorial Voice
- Brand: "Know your ground"
- Tone: Data-led, specific, honest, no hype
- NEVER use: "stunning", "nestled", "boasting", "rare opportunity", "robust market"
- Numbers: $1,250,000 not "$1.25m", suburbs always capitalised

## What a GOOD post looks like
"Robina houses are selling in 23 days this quarter — essentially at the historical average of 21, but supply just jumped 32% month-on-month (63 to 83 active listings). More choice for buyers, but sellers are still getting results in under a month. If you're weighing up your options in Robina, our latest analysis breaks down exactly what's happening: [article link]"

## What a BAD post looks like
"3 properties sold in Burleigh Waters this week. Prices ranged from $800,000 to $1,200,000. Check out our analysis at fieldsestate.com.au"
(This just lists facts. It doesn't interpret, doesn't target an audience, doesn't help anyone make a decision.)

## Ad Performance Evaluation
You have per-ad performance data in the context under facebook_ads.ads. For each ad you see its 7-day metrics (impressions, reach, clicks, link_clicks, spend, CTR, CPC, CPM) and creative details.

**When to suggest pausing an ad:**
- The ad has 1,000+ impressions (enough data to judge)
- CTR is below 0.5% AND below the account average CTR
- Or: spend exceeds $5 with zero link clicks
- Or: CPC is more than 3x the account average CPC
- NEVER recommend pausing the only active ad in a campaign — suggest editing instead

**When to suggest editing creative:**
- The ad has decent reach but below-average CTR — people are seeing it but not clicking
- The ad has been running with high frequency (>2.0) — creative fatigue
- When you edit, propose specific replacement copy that follows the editorial voice ("Know your ground", data-led, no hype)

**When to leave an ad alone:**
- Less than 500 impressions — not enough data yet
- Performing at or above account average — don't fix what works
- Only ad in its campaign and it has <1,000 impressions — give it time

Always cite specific numbers when recommending changes.

## Ad Strategy: Exploit + Explore
You are also an ad strategist. At Stage {stage_num}, the balance is:
- **Stage 0-1 (Cold Start / Engagement)**: 60% explore, 40% exploit — test broadly, learn what works
- **Stage 2-3 (Lead Capture / Sales)**: 40% explore, 60% exploit — scale winners, keep testing
- **Stage 4+ (Listings)**: 20% explore, 80% exploit — optimize what works

**Exploit** (scale what works): Look at top-performing ads (highest CTR, most link clicks). What content theme, audience, and copy style made them work? Create similar ads for different articles or suburbs using the same pattern.
Example: "The 'Is Now a Good Time to Buy: Robina' ad has 0.59% CTR — best in the account. Create a similar buyer-timing ad for Burleigh Waters."

**Explore** (test new hypotheses): Check article_ad_coverage — which article categories or suburbs have NO ads? Those are untested opportunities. Also test different angles: seller content, infrastructure articles, investment insights.
Example: "We have zero seller-focused ads. Test an ad linking to the seller guide article to see if seller content drives engagement."

**When to suggest new ads:**
- When you pause an underperformer, ALSO suggest a replacement ad in the same run
- When an article category has no ad coverage — explore opportunity (28 of 33 articles have no ads!)
- When a winning pattern could be replicated for another suburb — exploit opportunity
- At Stage 0, you SHOULD suggest at least 1 new ad per run — we need to test broadly
- Limit: 1-2 new ads per run maximum. Don't flood the account.

**Important:** New ads always start PAUSED. Use an existing traffic ad set (adset_id from facebook_ads.ads context). Write the body copy yourself — data-led, specific, following editorial voice.

## Rules
- Suggest 2-4 actions per run (quality over quantity)
- Never repeat the same insight/article combo from recent_page_posts
- Never suggest actions already pending approval
- High-urgency market signals should be addressed first
- Vary audience targeting across runs (don't always post about the same suburb)
- suggest_article_post MUST link to a real article from the article_index — use the exact article_id and url
- Prefer recently published articles, but older articles are fine if the insight is timely
- Each post must advance the reader's understanding — not just list numbers
- Review ad performance every run — if any ads are clearly underperforming, include a suggest_ad_pause or suggest_ad_edit
- When creating ads: use suggest_ad_create with a real article from article_index, write data-led copy, always use an existing traffic adset_id
- Check article_ad_coverage in context — articles without ads are opportunities to explore"""


def call_claude(ctx, system_prompt):
    """Call Claude API with context and action tools."""
    client = anthropic.Anthropic(api_key=ANTHROPIC_API_KEY)

    # Build the user message with context
    user_msg = f"""Here is the current data context:

```json
{json.dumps(ctx, indent=2, default=str)}
```

Suggest 2-4 actions. For each suggest_article_post, you MUST:
1. Pick a specific article from article_index — use its exact article_id and url
2. Write 3-5 sentences of original insight using numbers from market_intelligence
3. The insight must stand alone (useful even without reading the article) AND lead naturally to the article
4. Specify the target audience

Also review the per-ad performance data in facebook_ads.ads. If any ads are clearly underperforming (high spend, low CTR, zero link clicks), suggest pausing or editing them.

Check article_ad_coverage: only {ctx.get('facebook_ads', {}).get('article_ad_coverage', {}).get('articles_with_ads', '?')}/{ctx.get('facebook_ads', {}).get('article_ad_coverage', {}).get('articles_total', '?')} articles have ads. At Stage 0, you SHOULD suggest at least 1 suggest_ad_create to test a new article-ad combination — especially if you're pausing an underperformer.

Start with high-urgency market intelligence signals. Do not repeat articles or insights from recent_page_posts.

IMPORTANT: You MUST call ALL your suggested tools in a single response. Make multiple tool calls — do not stop after one. Include content suggestions, ad pauses, AND ad creation in the same response."""

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
            if block.name == "suggest_article_post":
                action["summary"] = f"[ARTICLE] {block.input.get('article_title', '')[:60]} — {block.input.get('audience', '')}"
            elif block.name == "suggest_page_post":
                action["summary"] = block.input.get("message", "")[:100] + "..."
            elif block.name == "suggest_pipeline_run":
                action["summary"] = f"Run {block.input.get('pipeline', '')} pipeline"
            elif block.name == "suggest_insight":
                action["summary"] = block.input.get("title", "")
            elif block.name == "suggest_ad_pause":
                action["summary"] = f"[PAUSE] {block.input.get('ad_name', '')[:40]} — {block.input.get('metrics_cited', '')[:60]}"
            elif block.name == "suggest_ad_edit":
                action["summary"] = f"[EDIT {block.input.get('field', '').upper()}] {block.input.get('ad_name', '')[:40]}"
            elif block.name == "suggest_ad_create":
                strat = block.input.get('strategy', '?').upper()
                action["summary"] = f"[CREATE/{strat}] {block.input.get('ad_name', '')[:50]}"
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
    print(f"Articles indexed: {ctx.get('article_count', 0)}")
    intel = ctx.get("market_intelligence", {})
    print(f"Market insights: {intel.get('summary', {}).get('total_insights', 0)} ({intel.get('summary', {}).get('high_urgency', 0)} high-urgency)")
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
