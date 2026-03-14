#!/usr/bin/env python3
"""
funnel-generator.py
===================
Reads top content gaps from search intent analysis, calls Claude API to
draft landing page content, Google Ads specs, and Facebook ad briefs.

Output is written to system_monitor.content_funnels with status "draft"
for human review in the ops dashboard Marketing Manager.

Usage:
    python3 scripts/funnel-generator.py                        # Top 1 funnel
    python3 scripts/funnel-generator.py --count 5              # Top 5
    python3 scripts/funnel-generator.py --query "specific query"
    python3 scripts/funnel-generator.py --dry-run              # Print, don't save
    python3 scripts/funnel-generator.py --list                 # Show existing funnels
"""

import argparse
import json
import os
import re
import sys
from datetime import datetime, timezone
from pathlib import Path

import anthropic
from dotenv import load_dotenv
from pymongo import MongoClient

load_dotenv(Path(__file__).parent.parent / ".env")
load_dotenv("/etc/environment", override=False)

# ── Config ────────────────────────────────────────────────────────────────────

CLAUDE_MODEL = "claude-sonnet-4-6"
ANTHROPIC_API_KEY = os.environ.get("ANTHROPIC_API_KEY", "")

COSMOS_URI = os.environ.get("COSMOS_CONNECTION_STRING", "")

# Fields Estate editorial rules
EDITORIAL_RULES = """
EDITORIAL VOICE — Fields Estate:
- Tagline: "Know your ground"
- Tone: Analytical, confident, locally grounded. Write like a knowledgeable friend who happens to be a data analyst.
- NEVER use: "stunning", "nestled", "boasting", "rare opportunity", "robust market", "in today's market"
- Numbers: $1,250,000 not "$1.25m", suburbs always capitalised (Robina, Burleigh Waters, Varsity Lakes)
- Target: Gold Coast property buyers and sellers — people making real decisions with real money
- Perspective: We are Fields Estate, a property intelligence platform on the Gold Coast
- Always cite specific data points, dollar figures, percentages — never vague generalisations
"""

TARGET_SUBURBS = ["Robina", "Burleigh Waters", "Varsity Lakes"]


def get_db():
    client = MongoClient(COSMOS_URI)
    return client["system_monitor"]


def get_latest_analysis(db):
    """Get the most recent search intent analysis document."""
    # Cosmos DB doesn't have sort index on analysed_at — fetch all and sort in Python
    docs = list(db["search_intent_analysis"].find().limit(10))
    docs.sort(key=lambda d: d.get("analysed_at", d.get("date", "")), reverse=True)
    doc = docs[0] if docs else None
    if not doc:
        print("ERROR: No search_intent_analysis found. Run search-intent-analyser.py first.")
        sys.exit(1)
    return doc


def get_published_articles(db):
    """Get all published articles for internal linking context."""
    articles = list(db["content_articles"].find(
        {"status": "published"},
        {"title": 1, "slug": 1, "tags": 1, "meta_description": 1}
    ))
    return articles


def get_existing_funnels(db):
    """Get queries that already have funnels (any status)."""
    existing = db["content_funnels"].find({}, {"source_query": 1})
    return {doc["source_query"].lower().strip() for doc in existing}


def select_top_gaps(analysis, existing_queries, count=1, specific_query=None):
    """Select top content gaps that don't already have funnels."""
    if specific_query:
        # Find this query in importance scores for metadata
        importance = analysis.get("importance", {})
        scored = importance.get("top_queries", []) + importance.get("top_fears", []) + importance.get("top_questions", [])
        score_map = {q["query"].lower().strip(): q for q in scored}

        query_lower = specific_query.lower().strip()
        if query_lower in score_map:
            return [score_map[query_lower]]
        # Not in scored list — create a minimal entry
        return [{
            "query": specific_query,
            "score": 0,
            "source_count": 0,
            "sources": [],
            "is_fear": False,
            "is_question": "?" in specific_query or specific_query.lower().startswith(("how", "what", "why", "when", "where", "does", "is", "can", "should")),
        }]

    # Get content gaps
    gaps = analysis.get("content_gaps", {})
    gap_questions = {g["question"].lower().strip(): g for g in gaps.get("gaps", [])}

    # Get importance scores
    importance = analysis.get("importance", {})
    scored = importance.get("top_queries", [])

    # Find scored queries that are also content gaps, and not already funnelled
    candidates = []
    for sq in scored:
        q_lower = sq["query"].lower().strip()
        if q_lower in existing_queries:
            continue
        # Prefer queries that are content gaps
        is_gap = q_lower in gap_questions
        # Also consider high-importance queries even if not flagged as gaps
        if is_gap or sq.get("score", 0) >= 30:
            candidate = {**sq, "is_gap": is_gap}
            if is_gap:
                candidate["gap_data"] = gap_questions[q_lower]
            candidates.append(candidate)

    # Sort: content gaps first (by importance score), then non-gaps by score
    candidates.sort(key=lambda c: (0 if c.get("is_gap") else 1, -c.get("score", 0)))

    return candidates[:count]


def build_claude_prompt(query_data, articles, analysis):
    """Build the Claude API prompt for generating funnel content."""
    query = query_data["query"]
    score = query_data.get("score", 0)
    sources = query_data.get("sources", [])
    sentiment = "fear" if query_data.get("is_fear") else ("question" if query_data.get("is_question") else "informational")

    # Build article context for internal linking
    article_list = "\n".join([
        f"- \"{a.get('title', 'Untitled')}\" — /articles/{a.get('slug', '')} (tags: {', '.join(a.get('tags', []))})"
        for a in articles[:30]
    ])

    # Get suburb data context
    suburbs_data = analysis.get("suburbs", {})
    suburb_context = ""
    for suburb in TARGET_SUBURBS:
        s_data = suburbs_data.get(suburb, suburbs_data.get(suburb.lower(), {}))
        if s_data:
            top_queries = s_data.get("top_queries", s_data.get("queries", []))[:5]
            if top_queries:
                suburb_context += f"\n{suburb}: top searches = {', '.join([q if isinstance(q, str) else q.get('query', '') for q in top_queries])}"

    # Get fear/hope context
    fears = analysis.get("fears", {})
    top_fears = fears.get("all", [])[:10] if isinstance(fears, dict) else []
    fear_context = ", ".join([f.get("text", f) if isinstance(f, dict) else str(f) for f in top_fears])

    prompt = f"""You are a content strategist for Fields Estate, a property intelligence platform on the Gold Coast, Australia.

{EDITORIAL_RULES}

## TASK
Generate a complete landing page and ad campaign for this search query that people are actively searching for but we have NO content answering:

**Query:** "{query}"
**Importance Score:** {score}/100
**Data Sources:** {', '.join(sources) if sources else 'content gap identified'}
**Sentiment:** {sentiment}

## CONTEXT
Target suburbs: Robina, Burleigh Waters, Varsity Lakes (southern Gold Coast corridor).
{suburb_context}

Top fears in the market right now: {fear_context}

## EXISTING ARTICLES (for internal linking)
{article_list}

## DELIVERABLES

Return a JSON object with these exact keys:

{{
  "title": "SEO-optimised page title (50-60 chars)",
  "slug": "url-friendly-slug-with-dashes",
  "meta_description": "Compelling meta description (150-160 chars) that answers the query directly",
  "body_html": "Full landing page HTML content (800-1200 words). Use <h2>, <h3>, <p>, <ul>, <strong> tags. Include data points, local Gold Coast context, and practical advice. End with a clear CTA section. Do NOT include <html>, <head>, or <body> wrapper tags — just the article content.",
  "internal_links": ["slug1", "slug2", "slug3"],
  "cta_text": "Clear call-to-action text for the page",
  "target_keyword": "the primary SEO keyword",
  "related_keywords": ["keyword1", "keyword2", "keyword3", "keyword4", "keyword5"],
  "google_ads": {{
    "campaign_name": "Fields — [Topic] — Search",
    "keywords": ["keyword1", "keyword2", "keyword3", "keyword4", "keyword5"],
    "headlines": ["Headline 1 (max 30 chars)", "Headline 2", "Headline 3"],
    "descriptions": ["Description 1 (max 90 chars)", "Description 2 (max 90 chars)"],
    "daily_budget": 20
  }},
  "fb_brief": {{
    "target_audience": "Description of who to target on Facebook",
    "suggested_copy": "The Facebook ad copy text (2-3 sentences)",
    "image_direction": "Description of what image to use",
    "placement": "Feed"
  }}
}}

IMPORTANT:
- The body_html must be substantial (800-1200 words), data-rich, and directly answer the search query
- Include at least 3 specific Gold Coast data points, dollar figures, or percentages
- Internal links must reference slugs from the existing articles list above
- Google Ads headlines must be 30 characters or fewer each
- Google Ads descriptions must be 90 characters or fewer each
- Return ONLY valid JSON, no markdown code fences"""

    return prompt


def generate_funnel(query_data, articles, analysis, dry_run=False):
    """Call Claude API to generate funnel content for a single query."""
    query = query_data["query"]
    print(f"\n  Generating funnel for: \"{query}\" (score: {query_data.get('score', 0)})...")

    prompt = build_claude_prompt(query_data, articles, analysis)

    client = anthropic.Anthropic(api_key=ANTHROPIC_API_KEY)

    response = client.messages.create(
        model=CLAUDE_MODEL,
        max_tokens=4000,
        system="You are a JSON-only content generator. Return only valid JSON, no explanation or markdown.",
        messages=[{"role": "user", "content": prompt}],
    )

    raw_text = response.content[0].text.strip()

    # Strip markdown code fences if present
    if raw_text.startswith("```"):
        raw_text = re.sub(r"^```(?:json)?\s*", "", raw_text)
        raw_text = re.sub(r"\s*```$", "", raw_text)

    try:
        content = json.loads(raw_text)
    except json.JSONDecodeError as e:
        print(f"  ERROR: Claude returned invalid JSON: {e}")
        print(f"  Raw response (first 500 chars): {raw_text[:500]}")
        return None

    # Build the funnel document
    now = datetime.now(timezone.utc)
    funnel = {
        "source_query": query,
        "importance_score": query_data.get("score", 0),
        "sentiment": "fear" if query_data.get("is_fear") else ("question" if query_data.get("is_question") else "informational"),
        "intent": _classify_intent(query),
        "status": "draft",
        "status_history": [{"status": "draft", "changed_at": now.isoformat(), "changed_by": "funnel-generator"}],
        "landing_page": {
            "title": content.get("title", ""),
            "slug": content.get("slug", ""),
            "meta_description": content.get("meta_description", ""),
            "body_html": content.get("body_html", ""),
            "internal_links": content.get("internal_links", []),
            "cta_text": content.get("cta_text", ""),
            "target_keyword": content.get("target_keyword", ""),
            "related_keywords": content.get("related_keywords", []),
        },
        "google_ads": content.get("google_ads", {}),
        "fb_brief": content.get("fb_brief", {}),
        "article_id": None,
        "created_at": now.isoformat(),
        "published_at": None,
    }

    if dry_run:
        print(f"\n  [DRY RUN] Would save funnel:")
        print(f"    Title: {funnel['landing_page']['title']}")
        print(f"    Slug: {funnel['landing_page']['slug']}")
        print(f"    Meta: {funnel['landing_page']['meta_description']}")
        print(f"    Body length: {len(funnel['landing_page']['body_html'])} chars")
        print(f"    Internal links: {funnel['landing_page']['internal_links']}")
        print(f"    Google Ads keywords: {funnel['google_ads'].get('keywords', [])}")
        print(f"    Facebook target: {funnel['fb_brief'].get('target_audience', '')}")
        return funnel

    return funnel


def _classify_intent(query):
    """Simple intent classification for the query."""
    q = query.lower()
    if any(w in q for w in ["sell", "selling", "sold", "agent fee", "commission"]):
        return "sell"
    if any(w in q for w in ["buy", "buying", "purchase", "afford"]):
        return "buy"
    if any(w in q for w in ["value", "valuation", "worth", "price"]):
        return "value"
    if any(w in q for w in ["invest", "rental yield", "roi", "capital gain"]):
        return "invest"
    if any(w in q for w in ["rent", "renting", "tenant", "lease"]):
        return "rent"
    return "research"


def list_funnels(db):
    """Print all existing funnels."""
    funnels = list(db["content_funnels"].find(
        {},
        {"source_query": 1, "status": 1, "importance_score": 1, "landing_page.title": 1, "created_at": 1}
    ).sort("created_at", -1))

    if not funnels:
        print("No funnels found.")
        return

    print(f"\n{'Status':<12} {'Score':>5}  {'Query':<40} {'Title'}")
    print("-" * 100)
    for f in funnels:
        status = f.get("status", "?")
        score = f.get("importance_score", 0)
        query = f.get("source_query", "")[:38]
        title = f.get("landing_page", {}).get("title", "")[:40]
        print(f"  {status:<10} {score:>5.1f}  {query:<40} {title}")
    print(f"\nTotal: {len(funnels)}")


def main():
    parser = argparse.ArgumentParser(description="Generate content marketing funnels from search intent data")
    parser.add_argument("--count", type=int, default=1, help="Number of funnels to generate (default: 1)")
    parser.add_argument("--query", type=str, help="Generate funnel for a specific query")
    parser.add_argument("--dry-run", action="store_true", help="Print output without saving to DB")
    parser.add_argument("--list", action="store_true", help="List existing funnels")
    args = parser.parse_args()

    if not COSMOS_URI:
        print("ERROR: COSMOS_CONNECTION_STRING not set")
        sys.exit(1)

    db = get_db()

    if args.list:
        list_funnels(db)
        return

    if not ANTHROPIC_API_KEY:
        print("ERROR: ANTHROPIC_API_KEY not set")
        sys.exit(1)

    # Load data
    print("Loading search intent analysis...")
    analysis = get_latest_analysis(db)
    print(f"  Analysis date: {analysis.get('date', 'unknown')}")

    articles = get_published_articles(db)
    print(f"  Published articles: {len(articles)}")

    existing = get_existing_funnels(db)
    print(f"  Existing funnels: {len(existing)}")

    # Select queries to generate funnels for
    candidates = select_top_gaps(analysis, existing, count=args.count, specific_query=args.query)
    if not candidates:
        print("\nNo suitable content gaps found for funnel generation.")
        print("  All high-importance gaps may already have funnels.")
        return

    print(f"\nGenerating {len(candidates)} funnel(s)...")

    generated = 0
    for candidate in candidates:
        funnel = generate_funnel(candidate, articles, analysis, dry_run=args.dry_run)
        if not funnel:
            continue

        if not args.dry_run:
            result = db["content_funnels"].insert_one(funnel)
            print(f"  Saved funnel: {result.inserted_id}")
            print(f"    Title: {funnel['landing_page']['title']}")
            print(f"    Status: draft (review in ops dashboard)")

        generated += 1

    print(f"\nDone. Generated {generated}/{len(candidates)} funnel(s).")
    if not args.dry_run and generated > 0:
        print("Next step: Review and approve in the ops dashboard → Marketing → Content Funnels")


if __name__ == "__main__":
    main()
