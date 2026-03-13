#!/usr/bin/env python3
"""
Search Intent Analyser — turns raw search data into actionable intelligence.

Runs after search-intent-collector.py and produces:
  1. Topic × Question hierarchy — groups queries under Halo Strategy topics
  2. Velocity alerts — new queries, growing queries, Reddit spikes
  3. Content gap report — unmatched questions vs existing articles
  4. Weekly digest — top actionable insights saved to MongoDB

Collections read (system_monitor):
  - search_suggestions, search_paa_questions, search_reddit_posts
  - search_trends, search_ad_queries, search_console_queries
  - search_intent_summary, content_articles

Collection written:
  - search_intent_analysis — one doc per run with full analysis

Usage:
    python3 scripts/search-intent-analyser.py                  # Full analysis + save
    python3 scripts/search-intent-analyser.py --dry-run        # Analyse + print, don't save
    python3 scripts/search-intent-analyser.py --report         # Print latest saved analysis
    python3 scripts/search-intent-analyser.py --days 7         # Lookback window (default: 14)

Schedule: Run after each collector run (cron or manual).
"""

import os
import re
import sys
import argparse
from datetime import datetime, timezone, timedelta
from collections import defaultdict

import yaml
from dotenv import load_dotenv
from pymongo import MongoClient, UpdateOne
from pymongo.errors import BulkWriteError

load_dotenv("/home/fields/Fields_Orchestrator/.env")

COSMOS_URI = os.environ["COSMOS_CONNECTION_STRING"]
AEST = timezone(timedelta(hours=10))
HALO_SEEDS_PATH = os.path.join(os.path.dirname(os.path.dirname(__file__)), "config", "halo_seeds.yaml")

# ---------------------------------------------------------------------------
# Topic taxonomy — loaded from halo_seeds.yaml
# ---------------------------------------------------------------------------
def load_topic_taxonomy():
    """Load Halo Strategy topics and build keyword matchers for each."""
    if not os.path.exists(HALO_SEEDS_PATH):
        return {}

    with open(HALO_SEEDS_PATH) as f:
        data = yaml.safe_load(f) or {}

    taxonomy = {}

    for topic_key, topic in (data.get("topics") or {}).items():
        # Build keyword set from seeds + fears
        keywords = set()
        for seed in topic.get("seeds", []):
            # Strip {suburb} placeholder, split into significant words
            clean = re.sub(r"\{suburb\}", "", seed).strip()
            for word in clean.lower().split():
                if len(word) > 3 and word not in ("with", "this", "that", "from", "your", "does", "what", "have"):
                    keywords.add(word)
        for fear in topic.get("fears", []):
            for word in fear.lower().split():
                if len(word) > 3 and word not in ("with", "this", "that", "from", "your", "does", "what", "have"):
                    keywords.add(word)

        taxonomy[topic_key] = {
            "display": topic_key.replace("_", " ").title(),
            "weight": topic.get("weight", 0),
            "keywords": keywords,
            "seeds": topic.get("seeds", []),
            "fears": topic.get("fears", []),
        }

    # Add avatar topics
    for avatar_key, avatar in (data.get("avatars") or {}).items():
        keywords = set()
        for text in avatar.get("fears", []) + avatar.get("barriers", []):
            for word in text.lower().split():
                if len(word) > 3 and word not in ("with", "this", "that", "from", "your", "does", "what", "have"):
                    keywords.add(word)

        taxonomy[f"avatar_{avatar_key}"] = {
            "display": avatar_key.replace("_", " ").title() + " (Avatar)",
            "weight": avatar.get("weight", 0),
            "keywords": keywords,
            "seeds": [],
            "fears": avatar.get("fears", []),
        }

    return taxonomy


def classify_topic(text, taxonomy):
    """Assign a query to the best-matching topic based on keyword overlap."""
    text_lower = text.lower()
    text_words = set(text_lower.split())

    best_topic = "uncategorised"
    best_score = 0

    for topic_key, info in taxonomy.items():
        # Score = number of keyword matches, weighted slightly by topic weight
        matches = text_words & info["keywords"]
        # Also check for multi-word keyword phrases in the text
        phrase_bonus = 0
        for seed in info.get("seeds", []) + info.get("fears", []):
            clean = re.sub(r"\{suburb\}", "", seed).strip().lower()
            if len(clean) > 8 and clean in text_lower:
                phrase_bonus += 2

        score = len(matches) + phrase_bonus
        if score > best_score:
            best_score = score
            best_topic = topic_key

    return best_topic if best_score >= 1 else "uncategorised"


# ---------------------------------------------------------------------------
# Data loading
# ---------------------------------------------------------------------------
def load_all_queries(sm_db, cutoff_date):
    """Load all queries from all sources within the date window."""
    queries = []  # list of {text, source, intent, sentiment, topic, date, meta}

    # Autocomplete suggestions (flatten)
    for doc in sm_db["search_suggestions"].find({"date": {"$gte": cutoff_date}}):
        for s in doc.get("suggestions", []):
            queries.append({
                "text": s.lower().strip(),
                "source": "autocomplete",
                "intent": doc.get("intent", "other"),
                "date": doc.get("date", ""),
                "seed": doc.get("seed_query", ""),
            })

    # PAA questions
    for doc in sm_db["search_paa_questions"].find({"date": {"$gte": cutoff_date}}):
        queries.append({
            "text": doc.get("question", "").lower().strip(),
            "source": "paa",
            "intent": "",  # will classify
            "date": doc.get("date", ""),
            "seed": doc.get("seed_query", ""),
        })

    # Reddit posts (title as query)
    for doc in sm_db["search_reddit_posts"].find({"date": {"$gte": cutoff_date}}):
        queries.append({
            "text": doc.get("title", "").lower().strip(),
            "source": "reddit",
            "intent": doc.get("intent", "other"),
            "sentiment": doc.get("sentiment", "neutral"),
            "date": doc.get("date", ""),
            "subreddit": doc.get("subreddit", ""),
        })

    # Google Ads search terms
    for doc in sm_db["search_ad_queries"].find({"date": {"$gte": cutoff_date}}):
        queries.append({
            "text": doc.get("search_term", "").lower().strip(),
            "source": "google_ads",
            "intent": "",
            "date": doc.get("date", ""),
            "impressions": doc.get("impressions", 0),
            "clicks": doc.get("clicks", 0),
        })

    # GSC queries
    for doc in sm_db["search_console_queries"].find({"date": {"$gte": cutoff_date}}):
        queries.append({
            "text": doc.get("query", "").lower().strip(),
            "source": "gsc",
            "intent": "",
            "date": doc.get("date", ""),
            "impressions": doc.get("impressions", 0),
            "clicks": doc.get("clicks", 0),
            "position": doc.get("position", 0),
        })

    return queries


def load_articles(sm_db):
    """Load published articles with titles and tags for content gap matching."""
    articles = []
    for doc in sm_db["content_articles"].find({"status": "published"}, {"title": 1, "slug": 1, "tags": 1, "custom_excerpt": 1}):
        title = doc.get("title", "").lower()
        excerpt = (doc.get("custom_excerpt") or "").lower()
        tags = []
        for t in (doc.get("tags") or []):
            if isinstance(t, dict):
                tags.append(t.get("name", "").lower())
            else:
                tags.append(str(t).lower())

        articles.append({
            "title": doc.get("title", ""),
            "slug": doc.get("slug", ""),
            "tags": tags,
            "searchable": f"{title} {excerpt} {' '.join(tags)}",
        })
    return articles


# ---------------------------------------------------------------------------
# Analysis functions
# ---------------------------------------------------------------------------
def build_topic_hierarchy(queries, taxonomy):
    """Group all queries under topics, producing parent → child structure."""
    hierarchy = defaultdict(lambda: {
        "queries": [],
        "sources": defaultdict(int),
        "unique_queries": set(),
        "question_count": 0,
    })

    for q in queries:
        topic = classify_topic(q["text"], taxonomy)
        q["topic"] = topic
        node = hierarchy[topic]
        node["unique_queries"].add(q["text"])
        node["sources"][q["source"]] += 1
        if q["text"].startswith(("how", "why", "what", "can", "should", "do ", "is ", "when", "where")):
            node["question_count"] += 1

    # Convert sets to counts for serialisation
    result = {}
    for topic_key, node in hierarchy.items():
        display = taxonomy.get(topic_key, {}).get("display", topic_key.replace("_", " ").title())
        weight = taxonomy.get(topic_key, {}).get("weight", 0)
        unique = node["unique_queries"]
        result[topic_key] = {
            "display": display,
            "weight": weight,
            "unique_query_count": len(unique),
            "question_count": node["question_count"],
            "sources": dict(node["sources"]),
            "top_queries": sorted(unique, key=lambda x: len(x))[:20],  # Shortest = most specific
        }

    return result


def detect_velocity(sm_db, current_cutoff, previous_cutoff):
    """Detect new and growing queries by comparing current vs previous window."""
    alerts = {
        "new_queries": [],        # appeared in current but not previous
        "growing_queries": [],    # seen_count increased >50%
        "reddit_spikes": [],      # Reddit posts with unusual engagement
    }

    # --- New PAA questions ---
    current_paa = set()
    for doc in sm_db["search_paa_questions"].find({"date": {"$gte": current_cutoff}}):
        current_paa.add(doc.get("question", "").lower().strip())

    previous_paa = set()
    for doc in sm_db["search_paa_questions"].find({"date": {"$gte": previous_cutoff, "$lt": current_cutoff}}):
        previous_paa.add(doc.get("question", "").lower().strip())

    new_paa = current_paa - previous_paa
    alerts["new_queries"] = sorted(new_paa)[:50]

    # --- New autocomplete suggestions ---
    current_auto = set()
    for doc in sm_db["search_suggestions"].find({"date": {"$gte": current_cutoff}}):
        for s in doc.get("suggestions", []):
            current_auto.add(s.lower().strip())

    previous_auto = set()
    for doc in sm_db["search_suggestions"].find({"date": {"$gte": previous_cutoff, "$lt": current_cutoff}}):
        for s in doc.get("suggestions", []):
            previous_auto.add(s.lower().strip())

    new_auto = current_auto - previous_auto
    # Merge with new_paa (deduplicated)
    all_new = sorted((new_paa | new_auto) - set(alerts["new_queries"]))
    alerts["new_queries"].extend(all_new[:50])
    alerts["new_queries"] = alerts["new_queries"][:100]

    # --- Growing autocomplete suggestions ---
    # Count how many times each suggestion appears across seed queries
    def count_suggestions(date_filter):
        counts = defaultdict(int)
        for doc in sm_db["search_suggestions"].find(date_filter):
            for s in doc.get("suggestions", []):
                counts[s.lower().strip()] += 1
        return counts

    current_counts = count_suggestions({"date": {"$gte": current_cutoff}})
    previous_counts = count_suggestions({"date": {"$gte": previous_cutoff, "$lt": current_cutoff}})

    for query, curr_count in current_counts.items():
        prev_count = previous_counts.get(query, 0)
        if prev_count > 0 and curr_count > prev_count * 1.5:
            alerts["growing_queries"].append({
                "query": query,
                "previous": prev_count,
                "current": curr_count,
                "growth": round((curr_count - prev_count) / prev_count * 100),
            })

    alerts["growing_queries"].sort(key=lambda x: -x["growth"])
    alerts["growing_queries"] = alerts["growing_queries"][:30]

    # --- Reddit spikes (posts with high engagement relative to average) ---
    reddit_docs = list(sm_db["search_reddit_posts"].find(
        {"date": {"$gte": current_cutoff}},
        {"title": 1, "subreddit": 1, "score": 1, "num_comments": 1, "sentiment": 1, "permalink": 1},
    ))

    if reddit_docs:
        # RSS doesn't give score/comments, but check for ones that do have them
        scored = [d for d in reddit_docs if d.get("score", 0) > 0 or d.get("num_comments", 0) > 0]
        if scored:
            avg_engagement = sum(d.get("score", 0) + d.get("num_comments", 0) for d in scored) / len(scored)
            for doc in scored:
                engagement = doc.get("score", 0) + doc.get("num_comments", 0)
                if engagement > avg_engagement * 2:
                    alerts["reddit_spikes"].append({
                        "title": doc.get("title", ""),
                        "subreddit": doc.get("subreddit", ""),
                        "engagement": engagement,
                        "sentiment": doc.get("sentiment", "neutral"),
                    })
        # Also include all unique Reddit post titles as signals (even without scores)
        alerts["reddit_topics"] = list({d.get("title", ""): d.get("sentiment", "neutral") for d in reddit_docs}.items())[:30]

    return alerts


def find_content_gaps(queries, articles, taxonomy):
    """Cross-reference discovered questions against existing articles."""
    gaps = []

    # Build a set of question-like queries
    questions = set()
    for q in queries:
        text = q["text"]
        if text.startswith(("how", "why", "what", "can", "should", "do ", "is ", "when", "where")):
            questions.add(text)

    # For each question, check if any article covers it
    article_text = " ".join(a["searchable"] for a in articles)

    covered = []
    uncovered = []

    for question in sorted(questions):
        # Check if key words from the question appear in article text
        words = [w for w in question.split() if len(w) > 3
                 and w not in ("what", "does", "with", "this", "that", "from", "your", "have",
                               "much", "many", "should", "when", "where", "which", "could")]
        if not words:
            continue

        # A question is "covered" if >=60% of its significant words appear in article corpus
        matches = sum(1 for w in words if w in article_text)
        coverage = matches / len(words) if words else 0

        topic = classify_topic(question, taxonomy)

        entry = {
            "question": question,
            "topic": topic,
            "coverage": round(coverage, 2),
            "source_count": sum(1 for q in queries if q["text"] == question),
        }

        if coverage >= 0.6:
            covered.append(entry)
        else:
            uncovered.append(entry)

    # Sort uncovered by how many sources surfaced the question (higher = more important)
    uncovered.sort(key=lambda x: (-x["source_count"], x["question"]))

    # Group uncovered by topic
    gaps_by_topic = defaultdict(list)
    for entry in uncovered:
        gaps_by_topic[entry["topic"]].append(entry)

    return {
        "total_questions": len(questions),
        "covered": len(covered),
        "uncovered": len(uncovered),
        "coverage_pct": round(len(covered) / len(questions) * 100, 1) if questions else 0,
        "top_uncovered": uncovered[:40],
        "gaps_by_topic": {k: v[:10] for k, v in sorted(gaps_by_topic.items(), key=lambda x: -len(x[1]))},
    }


def build_digest(hierarchy, velocity, content_gaps, queries):
    """Build a concise weekly digest of actionable insights."""
    insights = []

    # Insight 1: Biggest uncovered topic
    if content_gaps["gaps_by_topic"]:
        biggest_gap = max(content_gaps["gaps_by_topic"].items(), key=lambda x: len(x[1]))
        insights.append({
            "type": "content_gap",
            "priority": "high",
            "message": f"Biggest content gap: '{biggest_gap[0].replace('_', ' ')}' — {len(biggest_gap[1])} unanswered questions discovered",
            "action": f"Write an article addressing: {', '.join(e['question'][:60] for e in biggest_gap[1][:3])}",
        })

    # Insight 2: New queries emerging
    new_count = len(velocity.get("new_queries", []))
    if new_count > 0:
        samples = velocity["new_queries"][:3]
        insights.append({
            "type": "velocity",
            "priority": "medium",
            "message": f"{new_count} new queries detected this period",
            "action": f"Review new signals: {', '.join(s[:50] for s in samples)}",
        })

    # Insight 3: Growing queries
    growing = velocity.get("growing_queries", [])
    if growing:
        top = growing[0]
        insights.append({
            "type": "velocity",
            "priority": "medium",
            "message": f"Growing query: '{top['query']}' (+{top['growth']}% vs previous period)",
            "action": "Consider creating targeted content or ad copy for this rising query",
        })

    # Insight 4: Reddit sentiment
    reddit_queries = [q for q in queries if q.get("source") == "reddit"]
    if reddit_queries:
        fear_count = sum(1 for q in reddit_queries if q.get("sentiment") == "fear")
        hope_count = sum(1 for q in reddit_queries if q.get("sentiment") == "hope")
        total = len(reddit_queries)
        if fear_count > hope_count and fear_count > total * 0.3:
            insights.append({
                "type": "sentiment",
                "priority": "high",
                "message": f"Reddit sentiment skewing fearful: {fear_count}/{total} posts ({fear_count/total*100:.0f}%)",
                "action": "Consider reassuring content addressing common fears (market crash, rate rises)",
            })
        elif hope_count > fear_count:
            insights.append({
                "type": "sentiment",
                "priority": "low",
                "message": f"Reddit sentiment is positive: {hope_count}/{total} posts hopeful",
                "action": "Market receptive — good time for buyer-focused content",
            })

    # Insight 5: Content coverage score
    cov_pct = content_gaps.get("coverage_pct", 0)
    insights.append({
        "type": "coverage",
        "priority": "info",
        "message": f"Content coverage: {cov_pct}% of discovered questions have matching articles",
        "action": f"{content_gaps['uncovered']} questions remain uncovered" if content_gaps["uncovered"] else "Good coverage — focus on depth over breadth",
    })

    return insights


# ---------------------------------------------------------------------------
# Report printing
# ---------------------------------------------------------------------------
def print_analysis(analysis):
    """Print formatted analysis report to stdout."""
    print(f"\n{'='*65}")
    print(f"SEARCH INTENT ANALYSIS — {analysis.get('date', '?')}")
    print(f"{'='*65}")
    print(f"Queries analysed: {analysis.get('total_queries', 0)} from {analysis.get('total_sources', 0)} sources")
    print(f"Lookback: {analysis.get('lookback_days', 14)} days")

    # Topic hierarchy
    hierarchy = analysis.get("topic_hierarchy", {})
    if hierarchy:
        print(f"\n--- TOPIC HIERARCHY ({len(hierarchy)} topics) ---")
        sorted_topics = sorted(hierarchy.items(), key=lambda x: -x[1].get("unique_query_count", 0))
        for topic_key, info in sorted_topics[:15]:
            display = info.get("display", topic_key)
            uq = info.get("unique_query_count", 0)
            qc = info.get("question_count", 0)
            weight = info.get("weight", 0)
            sources = info.get("sources", {})
            src_str = ", ".join(f"{k}:{v}" for k, v in sorted(sources.items(), key=lambda x: -x[1]))
            weight_str = f" ({weight}%)" if weight else ""
            print(f"\n  {display}{weight_str} — {uq} queries, {qc} questions")
            print(f"    Sources: {src_str}")
            top = info.get("top_queries", [])
            for q in top[:5]:
                print(f"      • {q}")
            if len(top) > 5:
                print(f"      ... +{len(top) - 5} more")

    # Velocity alerts
    velocity = analysis.get("velocity", {})
    new_queries = velocity.get("new_queries", [])
    growing = velocity.get("growing_queries", [])

    if new_queries:
        print(f"\n--- NEW QUERIES ({len(new_queries)} emerged) ---")
        for q in new_queries[:15]:
            print(f"  NEW  {q}")
        if len(new_queries) > 15:
            print(f"  ... +{len(new_queries) - 15} more")

    if growing:
        print(f"\n--- GROWING QUERIES ---")
        for g in growing[:10]:
            print(f"  +{g['growth']:>3}%  {g['query']}")

    reddit_spikes = velocity.get("reddit_spikes", [])
    if reddit_spikes:
        print(f"\n--- REDDIT SPIKES ---")
        for r in reddit_spikes[:5]:
            print(f"  [{r['sentiment']}] r/{r['subreddit']}: {r['title'][:65]} (engagement: {r['engagement']})")

    # Content gaps
    gaps = analysis.get("content_gaps", {})
    if gaps:
        print(f"\n--- CONTENT GAPS ---")
        print(f"  Total questions discovered: {gaps.get('total_questions', 0)}")
        print(f"  Covered by articles:        {gaps.get('covered', 0)} ({gaps.get('coverage_pct', 0)}%)")
        print(f"  Uncovered:                  {gaps.get('uncovered', 0)}")

        gaps_by_topic = gaps.get("gaps_by_topic", {})
        if gaps_by_topic:
            print(f"\n  Top uncovered topics:")
            for topic, entries in sorted(gaps_by_topic.items(), key=lambda x: -len(x[1]))[:8]:
                print(f"    {topic.replace('_', ' ').title()} ({len(entries)} gaps):")
                for e in entries[:3]:
                    print(f"      ? {e['question'][:70]}")

    # Digest
    digest = analysis.get("digest", [])
    if digest:
        print(f"\n--- ACTIONABLE INSIGHTS ---")
        for i, insight in enumerate(digest, 1):
            priority = insight.get("priority", "info").upper()
            print(f"\n  [{priority}] {insight.get('message', '')}")
            print(f"    -> {insight.get('action', '')}")

    print(f"\n{'='*65}\n")


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------
def main():
    parser = argparse.ArgumentParser(description="Search Intent Analyser")
    parser.add_argument("--days", type=int, default=14, help="Lookback window in days (default: 14)")
    parser.add_argument("--dry-run", action="store_true", help="Analyse and print but don't save to MongoDB")
    parser.add_argument("--report", action="store_true", help="Print latest saved analysis")
    args = parser.parse_args()

    client = MongoClient(COSMOS_URI)
    sm_db = client["system_monitor"]

    if args.report:
        doc = sm_db["search_intent_analysis"].find_one(sort=[("date", -1)])
        if doc:
            print_analysis(doc)
        else:
            print("No analysis found. Run the analyser first.")
        client.close()
        return

    print(f"Search Intent Analyser — {datetime.now(AEST).strftime('%Y-%m-%d %H:%M AEST')}")
    print(f"Lookback: {args.days} days\n")

    # Date boundaries
    now = datetime.now(AEST)
    current_cutoff = (now - timedelta(days=args.days)).strftime("%Y-%m-%d")
    previous_cutoff = (now - timedelta(days=args.days * 2)).strftime("%Y-%m-%d")
    date_str = now.strftime("%Y-%m-%d")

    # Load taxonomy
    taxonomy = load_topic_taxonomy()
    print(f"Loaded {len(taxonomy)} topics from halo_seeds.yaml")

    # Load all queries
    print("Loading queries from all sources...")
    queries = load_all_queries(sm_db, current_cutoff)
    print(f"  {len(queries)} total query records loaded")

    # Deduplicate by text
    unique_texts = set(q["text"] for q in queries if q["text"])
    print(f"  {len(unique_texts)} unique query strings")

    # Load articles
    articles = load_articles(sm_db)
    print(f"  {len(articles)} published articles loaded")

    # --- Analysis ---
    print("\n[1/4] Building topic hierarchy...")
    hierarchy = build_topic_hierarchy(queries, taxonomy)
    print(f"  {len(hierarchy)} topics identified")

    print("[2/4] Detecting velocity signals...")
    velocity = detect_velocity(sm_db, current_cutoff, previous_cutoff)
    print(f"  {len(velocity.get('new_queries', []))} new queries, "
          f"{len(velocity.get('growing_queries', []))} growing, "
          f"{len(velocity.get('reddit_spikes', []))} Reddit spikes")

    print("[3/4] Finding content gaps...")
    content_gaps = find_content_gaps(queries, articles, taxonomy)
    print(f"  {content_gaps['total_questions']} questions, "
          f"{content_gaps['covered']} covered ({content_gaps['coverage_pct']}%), "
          f"{content_gaps['uncovered']} uncovered")

    print("[4/4] Building digest...")
    digest = build_digest(hierarchy, velocity, content_gaps, queries)
    print(f"  {len(digest)} actionable insights")

    # Source breakdown
    source_counts = defaultdict(int)
    for q in queries:
        source_counts[q.get("source", "unknown")] += 1

    # Assemble analysis document
    analysis = {
        "_id": f"analysis_{date_str}",
        "date": date_str,
        "lookback_days": args.days,
        "total_queries": len(queries),
        "unique_queries": len(unique_texts),
        "total_sources": len(source_counts),
        "source_breakdown": dict(source_counts),
        "topic_hierarchy": hierarchy,
        "velocity": velocity,
        "content_gaps": content_gaps,
        "digest": digest,
        "analysed_at": datetime.now(timezone.utc).isoformat(),
    }

    # Print
    print_analysis(analysis)

    if args.dry_run:
        print("--- DRY RUN (not saved) ---")
        client.close()
        return

    # Save to MongoDB
    print("Saving analysis to MongoDB...")
    sm_db["search_intent_analysis"].update_one(
        {"_id": analysis["_id"]}, {"$set": analysis}, upsert=True
    )
    sm_db["search_intent_analysis"].create_index("date")
    print("  Saved to search_intent_analysis")

    # Prune old analyses (keep 90 days)
    cutoff_prune = (now - timedelta(days=90)).strftime("%Y-%m-%d")
    pruned = sm_db["search_intent_analysis"].delete_many({"date": {"$lt": cutoff_prune}})
    if pruned.deleted_count:
        print(f"  Pruned {pruned.deleted_count} old analyses")

    print("\nDone.")
    client.close()


if __name__ == "__main__":
    main()
