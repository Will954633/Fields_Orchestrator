#!/usr/bin/env python3
"""
Search Intent Analyser — data-driven discovery of what people actually ask.

This is a BOTTOM-UP analyser. It does NOT use predefined categories or the
Halo Strategy taxonomy. Instead it discovers clusters, themes, and signals
directly from the raw search data.

Produces:
  1. Frequency-ranked signals — what queries appear most across seeds
  2. Emergent clusters — groups of queries that share n-gram phrases
  3. Fear/anxiety monitor — every fear signal with source and frequency
  4. Suburb-specific insights — what people ask about each target suburb
  5. Question discovery — actual questions people type, ranked by frequency
  6. Velocity alerts — new/growing queries vs previous period
  7. Content gap scan — which discovered questions have no matching article
  8. Reddit pulse — real discussions, sentiment, and emerging concerns

Collections read (system_monitor):
  - search_suggestions, search_paa_questions, search_reddit_posts
  - search_ad_queries, search_console_queries, content_articles

Collection written:
  - search_intent_analysis — one doc per run

Usage:
    python3 scripts/search-intent-analyser.py                  # Full analysis + save
    python3 scripts/search-intent-analyser.py --dry-run        # Analyse + print, don't save
    python3 scripts/search-intent-analyser.py --report         # Print latest saved analysis
    python3 scripts/search-intent-analyser.py --days 14        # Lookback window (default: 14)
"""

import os
import re
import sys
import math
import argparse
from datetime import datetime, timezone, timedelta
from collections import defaultdict, Counter

from dotenv import load_dotenv
from pymongo import MongoClient

load_dotenv("/home/fields/Fields_Orchestrator/.env")

COSMOS_URI = os.environ["COSMOS_CONNECTION_STRING"]
AEST = timezone(timedelta(hours=10))

TARGET_SUBURBS = ["robina", "burleigh waters", "varsity lakes", "burleigh", "varsity"]
STOPWORDS = frozenset(
    "a an the and or but in on of to for is it at by as with from my i we you he she "
    "they this that these those do does did are was were be been being have has had not "
    "no so if how what when where why which who whom can could should would will shall "
    "may might must very much more most some any all each every than about up down out "
    "into over after before between under again further then once here there its".split()
)

# ---------------------------------------------------------------------------
# Data loading
# ---------------------------------------------------------------------------
def load_all_data(sm_db, cutoff):
    """Load all raw data from MongoDB."""
    data = {}

    # Autocomplete: flatten to (suggestion_text, seed_query, intent, suburb, date)
    suggestions = []
    for doc in sm_db["search_suggestions"].find({"date": {"$gte": cutoff}}):
        for s in doc.get("suggestions", []):
            suggestions.append({
                "text": s.lower().strip(),
                "seed": doc.get("seed_query", ""),
                "intent": doc.get("intent", ""),
                "suburb": doc.get("suburb", ""),
                "date": doc.get("date", ""),
                "source": "autocomplete",
            })
    data["suggestions"] = suggestions

    # YouTube autocomplete: same structure, tagged as "youtube" source
    yt_suggestions = []
    for doc in sm_db["search_youtube_suggestions"].find({"date": {"$gte": cutoff}}):
        for s in doc.get("suggestions", []):
            yt_suggestions.append({
                "text": s.lower().strip(),
                "seed": doc.get("seed_query", ""),
                "intent": doc.get("intent", ""),
                "suburb": doc.get("suburb", ""),
                "date": doc.get("date", ""),
                "source": "youtube",
            })
    data["youtube"] = yt_suggestions

    # PAA questions
    paa = []
    for doc in sm_db["search_paa_questions"].find({"date": {"$gte": cutoff}}):
        paa.append({
            "text": doc.get("question", "").lower().strip(),
            "seed": doc.get("seed_query", ""),
            "prefix": doc.get("prefix", ""),
            "date": doc.get("date", ""),
            "source": "paa",
        })
    data["paa"] = paa

    # Reddit
    reddit = []
    for doc in sm_db["search_reddit_posts"].find({"date": {"$gte": cutoff}}):
        reddit.append({
            "title": doc.get("title", ""),
            "text": (doc.get("title", "") + " " + (doc.get("selftext") or "")).lower().strip(),
            "subreddit": doc.get("subreddit", ""),
            "sentiment": doc.get("sentiment", "neutral"),
            "intent": doc.get("intent", ""),
            "permalink": doc.get("permalink", ""),
            "date": doc.get("date", ""),
            "source": "reddit",
        })
    data["reddit"] = reddit

    # Google Ads
    ads = []
    for doc in sm_db["search_ad_queries"].find({"date": {"$gte": cutoff}}):
        ads.append({
            "text": doc.get("search_term", "").lower().strip(),
            "impressions": doc.get("impressions", 0),
            "clicks": doc.get("clicks", 0),
            "cost": doc.get("cost_aud", 0),
            "date": doc.get("date", ""),
            "source": "google_ads",
        })
    data["ads"] = ads

    # GSC
    gsc = []
    for doc in sm_db["search_console_queries"].find({"date": {"$gte": cutoff}}):
        gsc.append({
            "text": doc.get("query", "").lower().strip(),
            "impressions": doc.get("impressions", 0),
            "clicks": doc.get("clicks", 0),
            "position": doc.get("position", 0),
            "date": doc.get("date", ""),
            "source": "gsc",
        })
    data["gsc"] = gsc

    # Google Trends
    trends = []
    for doc in sm_db["search_trends"].find({"date": {"$gte": cutoff}}):
        iot = doc.get("interest_over_time", [])
        rising = doc.get("related_queries_rising", [])
        top_related = doc.get("related_queries_top", [])
        max_interest = max((p.get("value", 0) for p in iot), default=0)
        recent_vals = [p.get("value", 0) for p in iot[-4:]]
        recent_avg = sum(recent_vals) / len(recent_vals) if recent_vals else 0
        # Trend direction: compare last 4 weeks to previous 4 weeks
        prev_vals = [p.get("value", 0) for p in iot[-8:-4]]
        prev_avg = sum(prev_vals) / len(prev_vals) if prev_vals else 0
        if prev_avg > 0:
            trend_direction = round((recent_avg - prev_avg) / prev_avg * 100)
        elif recent_avg > 0:
            trend_direction = 100  # new activity
        else:
            trend_direction = 0

        trends.append({
            "keyword": doc.get("keyword", ""),
            "max_interest": max_interest,
            "recent_avg": round(recent_avg, 1),
            "trend_direction": trend_direction,  # +/- percentage
            "rising_queries": [{"query": r.get("query", ""), "value": str(r.get("value", ""))} for r in rising],
            "top_related": [{"query": r.get("query", ""), "value": r.get("value", 0)} for r in top_related],
            "weekly_data": [{"week": p.get("week", ""), "value": p.get("value", 0)} for p in iot],
            "source": "trends",
        })
    data["trends"] = trends

    # Articles
    articles = []
    for doc in sm_db["content_articles"].find({"status": "published"}, {"title": 1, "slug": 1, "tags": 1, "custom_excerpt": 1}):
        title = doc.get("title", "").lower()
        excerpt = (doc.get("custom_excerpt") or "").lower()
        tags = []
        for t in (doc.get("tags") or []):
            tags.append((t.get("name", "") if isinstance(t, dict) else str(t)).lower())
        articles.append({
            "title": doc.get("title", ""),
            "slug": doc.get("slug", ""),
            "searchable": f"{title} {excerpt} {' '.join(tags)}",
        })
    data["articles"] = articles

    return data


# ---------------------------------------------------------------------------
# Analysis 1: Frequency-ranked signals
# ---------------------------------------------------------------------------
def analyse_frequency(data):
    """Rank all suggestions by how often they appear across different seeds."""
    freq = Counter()
    seed_spread = defaultdict(set)  # query → set of seeds that surfaced it

    for s in data["suggestions"]:
        text = s["text"]
        freq[text] += 1
        seed_spread[text].add(s["seed"])

    # YouTube suggestions
    for s in data["youtube"]:
        text = s["text"]
        freq[text] += 1
        seed_spread[text].add(f"yt:{s['seed']}")

    # Also count PAA and Reddit contributions
    for q in data["paa"]:
        freq[q["text"]] += 1
        seed_spread[q["text"]].add(f"paa:{q['seed']}")

    ranked = []
    for text, count in freq.most_common(200):
        ranked.append({
            "query": text,
            "frequency": count,
            "seed_spread": len(seed_spread[text]),
            "seeds": sorted(seed_spread[text])[:5],
        })

    return ranked


# ---------------------------------------------------------------------------
# Analysis 2: Emergent clusters (n-gram based, no predefined categories)
# ---------------------------------------------------------------------------
def analyse_clusters(data):
    """Discover topic clusters from 2-gram and 3-gram phrase frequency."""
    all_texts = set()
    for s in data["suggestions"]:
        all_texts.add(s["text"])
    for s in data["youtube"]:
        all_texts.add(s["text"])
    for q in data["paa"]:
        all_texts.add(q["text"])

    # Extract 2-grams and 3-grams
    bigrams = Counter()
    trigrams = Counter()

    for text in all_texts:
        words = [w for w in text.split() if w not in STOPWORDS and len(w) > 2]
        for i in range(len(words) - 1):
            bigrams[f"{words[i]} {words[i+1]}"] += 1
        for i in range(len(words) - 2):
            trigrams[f"{words[i]} {words[i+1]} {words[i+2]}"] += 1

    # Build clusters: for each significant phrase, find all queries containing it
    clusters = []
    seen_phrases = set()

    # Prefer trigrams (more specific), then bigrams
    for phrase, count in trigrams.most_common(100):
        if count < 3:
            break
        # Skip if this phrase is a subset of an already-seen cluster
        if any(phrase in sp for sp in seen_phrases):
            continue
        seen_phrases.add(phrase)
        matching = sorted([t for t in all_texts if phrase in t])
        clusters.append({
            "phrase": phrase,
            "query_count": len(matching),
            "frequency": count,
            "sample_queries": matching[:10],
        })

    for phrase, count in bigrams.most_common(200):
        if count < 4:
            break
        if any(phrase in sp for sp in seen_phrases):
            continue
        # Skip very generic bigrams
        if phrase in ("gold coast", "real estate", "house prices", "property market"):
            continue
        seen_phrases.add(phrase)
        matching = sorted([t for t in all_texts if phrase in t])
        clusters.append({
            "phrase": phrase,
            "query_count": len(matching),
            "frequency": count,
            "sample_queries": matching[:10],
        })

    clusters.sort(key=lambda c: -c["query_count"])
    return clusters[:50]


# ---------------------------------------------------------------------------
# Analysis 3: Fear/anxiety monitor
# ---------------------------------------------------------------------------
FEAR_PATTERNS = [
    (re.compile(r'\b(crash|crashes|crashing)\b'), "crash"),
    (re.compile(r'\b(bubble)\b'), "bubble"),
    (re.compile(r'\b(fall|falling|fell)\b'), "price fall"),
    (re.compile(r'\b(drop|dropping|dropped)\b'), "price drop"),
    (re.compile(r'\b(overpriced|over.?valued)\b'), "overvaluation"),
    (re.compile(r'\b(stress|stressed)\b'), "stress"),
    (re.compile(r"\bcan'?t afford\b"), "affordability"),
    (re.compile(r'\b(negative equity)\b'), "negative equity"),
    (re.compile(r'\b(worst time)\b'), "timing fear"),
    (re.compile(r'\b(downturn|recession)\b'), "economic fear"),
    (re.compile(r'\b(flood|flooding)\b'), "flood risk"),
    (re.compile(r'\b(crime|unsafe|dangerous)\b'), "safety"),
    (re.compile(r'\b(scam|rip.?off|ripped)\b'), "trust"),
    (re.compile(r'\b(losing|lost money)\b'), "loss"),
]


def analyse_fears(data):
    """Find every fear signal across all sources, categorised by fear type."""
    fears = []  # {text, source, fear_type, frequency}
    seen = {}

    def check_text(text, source, extra=None):
        for pattern, fear_type in FEAR_PATTERNS:
            if pattern.search(text):
                key = text.lower().strip()
                if key in seen:
                    seen[key]["frequency"] += 1
                    seen[key]["sources"].add(source)
                else:
                    entry = {
                        "text": text.strip(),
                        "fear_type": fear_type,
                        "frequency": 1,
                        "sources": {source},
                    }
                    if extra:
                        entry.update(extra)
                    seen[key] = entry
                return

    # Autocomplete suggestions
    for s in data["suggestions"]:
        check_text(s["text"], "autocomplete")

    # PAA questions
    for q in data["paa"]:
        check_text(q["text"], "paa")

    # Reddit posts
    for r in data["reddit"]:
        check_text(r["text"], "reddit", {"subreddit": r.get("subreddit", "")})

    # GSC
    for g in data["gsc"]:
        check_text(g["text"], "gsc")

    # Convert sets and sort
    for entry in seen.values():
        entry["sources"] = sorted(entry["sources"])
        fears.append(entry)
    fears.sort(key=lambda f: -f["frequency"])

    # Group by fear type
    by_type = defaultdict(list)
    for f in fears:
        by_type[f["fear_type"]].append(f)

    return {
        "total": len(fears),
        "by_type": {k: {"count": len(v), "signals": v[:15]} for k, v in sorted(by_type.items(), key=lambda x: -len(x[1]))},
        "all": fears[:100],
    }


# ---------------------------------------------------------------------------
# Analysis 4: Suburb-specific insights
# ---------------------------------------------------------------------------
def analyse_suburbs(data):
    """What people specifically ask about each target suburb."""
    suburbs = {}

    for suburb_name in ["robina", "burleigh waters", "varsity lakes"]:
        short = suburb_name.split()[0]  # "robina", "burleigh", "varsity"
        queries = set()
        questions = []
        fears_list = []
        lifestyle = []  # non-property queries (schools, safety, lifestyle)

        all_texts = set()
        for s in data["suggestions"]:
            if short in s["text"]:
                all_texts.add(s["text"])
        for q in data["paa"]:
            if short in q["text"]:
                all_texts.add(q["text"])

        for text in all_texts:
            queries.add(text)
            # Classify
            if text.startswith(("how", "why", "what", "can", "should", "do ", "is ", "when", "where")):
                questions.append(text)
            for pattern, fear_type in FEAR_PATTERNS:
                if pattern.search(text):
                    fears_list.append({"text": text, "fear_type": fear_type})
                    break
            if any(w in text for w in ["school", "live", "safe", "crime", "flood", "lifestyle", "family", "shops", "good place"]):
                lifestyle.append(text)

        # Non-property queries (interesting signals — what else people associate with the suburb)
        non_property = [q for q in queries
                       if not any(w in q for w in ["for sale", "for rent", "real estate", "houses for", "property for"])]

        suburbs[suburb_name] = {
            "total_queries": len(queries),
            "questions": sorted(questions)[:20],
            "fears": fears_list[:10],
            "lifestyle": sorted(lifestyle)[:15],
            "non_property": sorted(non_property)[:20],
            "top_queries": sorted(queries, key=len)[:20],
        }

    return suburbs


# ---------------------------------------------------------------------------
# Analysis 5: Question discovery
# ---------------------------------------------------------------------------
def analyse_questions(data):
    """All question-format queries, ranked by how often they appeared."""
    questions = Counter()
    sources = defaultdict(set)

    for s in data["suggestions"]:
        text = s["text"]
        if text.startswith(("how", "why", "what", "can", "should", "do ", "is ", "when", "where")):
            questions[text] += 1
            sources[text].add("autocomplete")

    for s in data["youtube"]:
        text = s["text"]
        if text.startswith(("how", "why", "what", "can", "should", "do ", "is ", "when", "where")):
            questions[text] += 1
            sources[text].add("youtube")

    for q in data["paa"]:
        text = q["text"]
        questions[text] += 1
        sources[text].add("paa")

    for r in data["reddit"]:
        title = r.get("title", "").lower().strip()
        if title.endswith("?") or title.startswith(("how", "why", "what", "can", "should", "is ", "when", "where", "do ")):
            questions[title] += 1
            sources[title].add("reddit")

    ranked = []
    for text, count in questions.most_common(200):
        # Filter out non-Australian queries
        if any(loc in text for loc in ["california", "florida", "texas", "ontario", "new york", "uk ", "toronto", "india", " nj", " ny"]):
            continue
        ranked.append({
            "question": text,
            "frequency": count,
            "sources": sorted(sources[text]),
        })

    return ranked


# ---------------------------------------------------------------------------
# Analysis 6: Velocity — new and growing signals
# ---------------------------------------------------------------------------
def analyse_velocity(sm_db, current_cutoff, previous_cutoff):
    """Compare current period to previous period to find emerging signals."""
    # Current period suggestions (Google + YouTube)
    current = set()
    for coll in ["search_suggestions", "search_youtube_suggestions"]:
        for doc in sm_db[coll].find({"date": {"$gte": current_cutoff}}):
            for s in doc.get("suggestions", []):
                current.add(s.lower().strip())
    for doc in sm_db["search_paa_questions"].find({"date": {"$gte": current_cutoff}}):
        current.add(doc.get("question", "").lower().strip())

    # Previous period
    previous = set()
    for coll in ["search_suggestions", "search_youtube_suggestions"]:
        for doc in sm_db[coll].find({"date": {"$gte": previous_cutoff, "$lt": current_cutoff}}):
            for s in doc.get("suggestions", []):
                previous.add(s.lower().strip())
    for doc in sm_db["search_paa_questions"].find({"date": {"$gte": previous_cutoff, "$lt": current_cutoff}}):
        previous.add(doc.get("question", "").lower().strip())

    new_queries = sorted(current - previous)

    # Frequency comparison for growing queries
    curr_freq = Counter()
    for coll in ["search_suggestions", "search_youtube_suggestions"]:
        for doc in sm_db[coll].find({"date": {"$gte": current_cutoff}}):
            for s in doc.get("suggestions", []):
                curr_freq[s.lower().strip()] += 1
    prev_freq = Counter()
    for coll in ["search_suggestions", "search_youtube_suggestions"]:
        for doc in sm_db[coll].find({"date": {"$gte": previous_cutoff, "$lt": current_cutoff}}):
            for s in doc.get("suggestions", []):
                prev_freq[s.lower().strip()] += 1

    growing = []
    for q, curr_count in curr_freq.items():
        prev_count = prev_freq.get(q, 0)
        if prev_count > 0 and curr_count > prev_count * 1.5:
            growing.append({
                "query": q,
                "previous": prev_count,
                "current": curr_count,
                "growth_pct": round((curr_count - prev_count) / prev_count * 100),
            })
    growing.sort(key=lambda g: -g["growth_pct"])

    return {
        "new_query_count": len(new_queries),
        "new_queries": new_queries[:80],
        "growing": growing[:30],
    }


# ---------------------------------------------------------------------------
# Analysis 7: Content gaps
# ---------------------------------------------------------------------------
def analyse_content_gaps(questions, articles):
    """Which questions have no matching article?"""
    if not articles:
        return {"total_questions": len(questions), "covered": 0, "uncovered": len(questions), "coverage_pct": 0, "gaps": questions[:50]}

    article_corpus = " ".join(a["searchable"] for a in articles)

    covered = []
    uncovered = []

    for q_entry in questions:
        text = q_entry["question"]
        # Extract significant words
        words = [w for w in text.split() if w not in STOPWORDS and len(w) > 3]
        if not words:
            continue
        matches = sum(1 for w in words if w in article_corpus)
        coverage = matches / len(words)

        if coverage >= 0.6:
            covered.append(q_entry)
        else:
            uncovered.append(q_entry)

    total = len(covered) + len(uncovered)
    return {
        "total_questions": total,
        "covered": len(covered),
        "uncovered": len(uncovered),
        "coverage_pct": round(len(covered) / total * 100, 1) if total else 0,
        "gaps": uncovered[:60],
    }


# ---------------------------------------------------------------------------
# Analysis 8: Reddit pulse
# ---------------------------------------------------------------------------
def analyse_reddit(data):
    """Summarise Reddit discussion themes and sentiment."""
    posts = data["reddit"]
    if not posts:
        return {"total": 0}

    sentiment = Counter(p.get("sentiment", "neutral") for p in posts)
    by_sub = defaultdict(list)
    for p in posts:
        by_sub[p.get("subreddit", "?")].append(p)

    # Find the most-discussed topics (from titles)
    title_words = Counter()
    for p in posts:
        words = [w for w in p.get("title", "").lower().split()
                if w not in STOPWORDS and len(w) > 3]
        for w in words:
            title_words[w] += 1

    return {
        "total": len(posts),
        "sentiment": dict(sentiment),
        "by_subreddit": {sub: {
            "count": len(ps),
            "posts": [{"title": p["title"], "sentiment": p.get("sentiment", "neutral"),
                       "permalink": p.get("permalink", "")} for p in ps[:15]],
        } for sub, ps in sorted(by_sub.items(), key=lambda x: -len(x[1]))},
        "top_words": title_words.most_common(20),
        "fear_posts": [{"title": p["title"], "subreddit": p.get("subreddit", ""), "permalink": p.get("permalink", "")}
                      for p in posts if p.get("sentiment") == "fear"][:20],
    }


# ---------------------------------------------------------------------------
# Analysis 9: Trends analysis
# ---------------------------------------------------------------------------
def analyse_trends(data):
    """Summarise Google Trends data — rising queries, momentum, weekly patterns."""
    trends = data.get("trends", [])
    if not trends:
        return {"total": 0}

    # Sort by recent_avg (proxy for search volume)
    by_volume = sorted(trends, key=lambda t: -t.get("recent_avg", 0))

    # Collect all rising queries across all keywords
    all_rising = []
    for t in trends:
        for rq in t.get("rising_queries", []):
            all_rising.append({
                "query": rq["query"],
                "value": rq["value"],  # "Breakout" or percentage
                "parent_keyword": t["keyword"],
            })
    # Sort: "Breakout" first, then by numeric value
    def rising_sort(r):
        v = r["value"]
        if isinstance(v, str) and "breakout" in v.lower():
            return (0, 0)
        try:
            return (1, -int(str(v).replace("%", "").replace("+", "").replace(",", "")))
        except (ValueError, TypeError):
            return (2, 0)
    all_rising.sort(key=rising_sort)

    # Momentum: which keywords are accelerating vs declining
    momentum = []
    for t in trends:
        td = t.get("trend_direction", 0)
        momentum.append({
            "keyword": t["keyword"],
            "recent_avg": t["recent_avg"],
            "max_interest": t["max_interest"],
            "trend_direction": td,
            "direction_label": "rising" if td > 10 else ("falling" if td < -10 else "stable"),
            "weekly_data": t.get("weekly_data", []),
        })
    momentum.sort(key=lambda m: -abs(m["trend_direction"]))

    return {
        "total": len(trends),
        "by_volume": [{
            "keyword": t["keyword"],
            "recent_avg": t["recent_avg"],
            "max_interest": t["max_interest"],
            "trend_direction": t["trend_direction"],
        } for t in by_volume],
        "rising_queries": all_rising[:40],
        "momentum": momentum,
        "keywords_rising": [m for m in momentum if m["direction_label"] == "rising"],
        "keywords_falling": [m for m in momentum if m["direction_label"] == "falling"],
        "keywords_stable": [m for m in momentum if m["direction_label"] == "stable"],
    }


# ---------------------------------------------------------------------------
# Analysis 10: Importance scoring
# ---------------------------------------------------------------------------
def score_importance(data, frequency, questions, fears, trends_analysis):
    """
    Assign a composite importance score to every unique query.
    Combines: seed spread, cross-source presence, Google Trends volume,
    GSC impressions, fear signal presence, and frequency.
    """
    # Build a unified query → signals map
    query_signals = defaultdict(lambda: {
        "sources": set(),
        "frequency": 0,
        "seed_spread": 0,
        "gsc_impressions": 0,
        "gsc_clicks": 0,
        "gsc_position": 0,
        "trends_volume": 0,
        "trend_direction": 0,
        "is_fear": False,
        "is_question": False,
        "ad_impressions": 0,
    })

    # From frequency analysis (has seed_spread)
    freq_map = {f["query"]: f for f in frequency}

    # Autocomplete
    for s in data["suggestions"]:
        q = query_signals[s["text"]]
        q["sources"].add("autocomplete")
        q["frequency"] += 1

    # YouTube
    for s in data["youtube"]:
        q = query_signals[s["text"]]
        q["sources"].add("youtube")
        q["frequency"] += 1

    # PAA — all PAA entries are questions by definition
    for p in data["paa"]:
        q = query_signals[p["text"]]
        q["sources"].add("paa")
        q["frequency"] += 1
        q["is_question"] = True

    # Reddit
    for r in data["reddit"]:
        title = r.get("title", "").lower().strip()
        if title:
            q = query_signals[title]
            q["sources"].add("reddit")
            q["frequency"] += 1

    # GSC
    for g in data["gsc"]:
        q = query_signals[g["text"]]
        q["sources"].add("gsc")
        q["gsc_impressions"] = max(q["gsc_impressions"], g.get("impressions", 0))
        q["gsc_clicks"] = max(q["gsc_clicks"], g.get("clicks", 0))
        q["gsc_position"] = g.get("position", 0)

    # Google Ads
    for a in data["ads"]:
        q = query_signals[a["text"]]
        q["sources"].add("google_ads")
        q["ad_impressions"] = max(q["ad_impressions"], a.get("impressions", 0))

    # Copy seed_spread from frequency analysis
    for text, info in freq_map.items():
        query_signals[text]["seed_spread"] = info.get("seed_spread", 0)

    # Mark fear queries
    fear_texts = set()
    for f_entry in fears.get("all", []):
        fear_texts.add(f_entry["text"].lower().strip())
    for text in fear_texts:
        if text in query_signals:
            query_signals[text]["is_fear"] = True

    # Mark questions
    question_texts = set(q["question"] for q in questions)
    for text in question_texts:
        if text in query_signals:
            query_signals[text]["is_question"] = True

    # Map Google Trends volume to matching queries
    trends_volume_map = {}
    for t in data.get("trends", []):
        kw = t.get("keyword", "").lower()
        trends_volume_map[kw] = {
            "recent_avg": t.get("recent_avg", 0),
            "trend_direction": t.get("trend_direction", 0),
        }

    for text, signals in query_signals.items():
        # Direct match
        if text in trends_volume_map:
            signals["trends_volume"] = trends_volume_map[text]["recent_avg"]
            signals["trend_direction"] = trends_volume_map[text]["trend_direction"]
        else:
            # Partial match: if a trends keyword is contained in the query
            for kw, tv in trends_volume_map.items():
                if kw in text or text in kw:
                    signals["trends_volume"] = max(signals["trends_volume"], tv["recent_avg"])
                    if abs(tv["trend_direction"]) > abs(signals["trend_direction"]):
                        signals["trend_direction"] = tv["trend_direction"]

    # Calculate composite score
    scored = []
    for text, signals in query_signals.items():
        if not text or len(text) < 3:
            continue

        score = 0.0

        # 1. Cross-source presence (0-30 pts) — most important
        source_count = len(signals["sources"])
        score += min(source_count * 10, 30)

        # 2. Frequency (0-20 pts)
        score += min(signals["frequency"] * 2, 20)

        # 3. Seed spread (0-15 pts)
        score += min(signals["seed_spread"] * 3, 15)

        # 4. GSC impressions (0-15 pts) — real search volume
        if signals["gsc_impressions"] > 0:
            score += min(math.log10(signals["gsc_impressions"] + 1) * 5, 15)

        # 5. Google Trends volume (0-10 pts)
        if signals["trends_volume"] > 0:
            score += min(signals["trends_volume"] / 10, 10)

        # 6. Trend momentum bonus (0-5 pts)
        if signals["trend_direction"] > 20:
            score += min(signals["trend_direction"] / 20, 5)

        # 7. Fear signal bonus (+5 pts) — fears deserve attention
        if signals["is_fear"]:
            score += 5

        # 8. Question bonus (+3 pts) — questions are actionable
        if signals["is_question"]:
            score += 3

        # 9. Ad impressions (0-7 pts) — people spend money on these
        if signals["ad_impressions"] > 0:
            score += min(math.log10(signals["ad_impressions"] + 1) * 3, 7)

        scored.append({
            "query": text,
            "score": round(score, 1),
            "source_count": source_count,
            "sources": sorted(signals["sources"]),
            "frequency": signals["frequency"],
            "seed_spread": signals["seed_spread"],
            "gsc_impressions": signals["gsc_impressions"],
            "gsc_clicks": signals["gsc_clicks"],
            "trends_volume": signals["trends_volume"],
            "trend_direction": signals["trend_direction"],
            "is_fear": signals["is_fear"],
            "is_question": signals["is_question"],
            "ad_impressions": signals["ad_impressions"],
        })

    scored.sort(key=lambda s: -s["score"])

    # Score distribution
    scores = [s["score"] for s in scored]
    if scores:
        avg_score = sum(scores) / len(scores)
        max_score = max(scores)
        high_importance = len([s for s in scores if s >= 40])
        medium_importance = len([s for s in scores if 20 <= s < 40])
        low_importance = len([s for s in scores if s < 20])
    else:
        avg_score = max_score = high_importance = medium_importance = low_importance = 0

    return {
        "total_scored": len(scored),
        "avg_score": round(avg_score, 1),
        "max_score": max_score,
        "distribution": {
            "high": high_importance,
            "medium": medium_importance,
            "low": low_importance,
        },
        "top_queries": scored[:100],
        "top_fears": [s for s in scored if s["is_fear"]][:30],
        "top_questions": [s for s in scored if s["is_question"]][:30],
        "all_scored_questions": [s for s in scored if s["is_question"]],
    }


# ---------------------------------------------------------------------------
# Report
# ---------------------------------------------------------------------------
def print_analysis(analysis):
    """Print formatted analysis to stdout."""
    print(f"\n{'='*70}")
    print(f"SEARCH INTENT ANALYSIS — {analysis.get('date', '?')}  (data-driven, bottom-up)")
    print(f"{'='*70}")

    src = analysis.get("source_counts", {})
    print(f"Data: {analysis.get('total_records', 0)} records from {len(src)} sources")
    for s, c in sorted(src.items(), key=lambda x: -x[1]):
        print(f"  {s}: {c}")

    # 1. Top signals
    freq = analysis.get("frequency", [])
    if freq:
        print(f"\n--- TOP SIGNALS (queries appearing across multiple seeds) ---")
        for f in freq[:25]:
            spread = f.get("seed_spread", 0)
            print(f"  {f['frequency']:>3}x  (spread: {spread} seeds)  {f['query']}")

    # 2. Emergent clusters
    clusters = analysis.get("clusters", [])
    if clusters:
        print(f"\n--- EMERGENT CLUSTERS (discovered from n-gram analysis) ---")
        for c in clusters[:20]:
            print(f"\n  \"{c['phrase']}\" — {c['query_count']} queries")
            for q in c.get("sample_queries", [])[:4]:
                print(f"    • {q}")

    # 3. Fear monitor
    fears = analysis.get("fears", {})
    if fears.get("total"):
        print(f"\n--- FEAR MONITOR ({fears['total']} signals) ---")
        for fear_type, info in fears.get("by_type", {}).items():
            print(f"\n  {fear_type.upper()} ({info['count']} signals):")
            for s in info.get("signals", [])[:5]:
                sources = ", ".join(s.get("sources", []))
                print(f"    {s['frequency']}x [{sources}] {s['text']}")

    # 4. Suburb insights
    suburbs = analysis.get("suburbs", {})
    if suburbs:
        print(f"\n--- SUBURB INSIGHTS ---")
        for suburb, info in suburbs.items():
            print(f"\n  {suburb.upper()} ({info['total_queries']} queries)")
            if info.get("fears"):
                print(f"    Fears:")
                for f in info["fears"][:5]:
                    print(f"      😰 [{f['fear_type']}] {f['text']}")
            if info.get("lifestyle"):
                print(f"    Lifestyle queries:")
                for q in info["lifestyle"][:5]:
                    print(f"      🏠 {q}")
            if info.get("non_property"):
                print(f"    Non-property (what else people associate):")
                for q in info["non_property"][:8]:
                    print(f"      • {q}")

    # 5. Top questions
    questions = analysis.get("questions", [])
    if questions:
        print(f"\n--- TOP QUESTIONS ({len(questions)} discovered) ---")
        for q in questions[:25]:
            sources = ", ".join(q.get("sources", []))
            print(f"  {q['frequency']:>2}x [{sources}] {q['question']}")

    # 6. Velocity
    velocity = analysis.get("velocity", {})
    new_qs = velocity.get("new_queries", [])
    growing = velocity.get("growing", [])
    if new_qs:
        print(f"\n--- NEW THIS PERIOD ({velocity.get('new_query_count', 0)} queries) ---")
        for q in new_qs[:20]:
            print(f"  NEW  {q}")
    if growing:
        print(f"\n--- GROWING QUERIES ---")
        for g in growing[:10]:
            print(f"  +{g['growth_pct']:>3}%  {g['query']}")

    # 7. Content gaps
    gaps = analysis.get("content_gaps", {})
    if gaps:
        print(f"\n--- CONTENT GAPS ---")
        print(f"  Questions found: {gaps.get('total_questions', 0)}")
        print(f"  Covered: {gaps.get('covered', 0)} ({gaps.get('coverage_pct', 0)}%)")
        print(f"  Uncovered: {gaps.get('uncovered', 0)}")
        for g in gaps.get("gaps", [])[:20]:
            print(f"    ? {g['question']}")

    # 8. Reddit
    reddit = analysis.get("reddit_pulse", {})
    if reddit.get("total"):
        print(f"\n--- REDDIT PULSE ({reddit['total']} posts) ---")
        sent = reddit.get("sentiment", {})
        total_r = reddit["total"]
        print(f"  Sentiment: fear {sent.get('fear',0)}/{total_r} | hope {sent.get('hope',0)}/{total_r} | neutral {sent.get('neutral',0)}/{total_r}")
        for sub, info in reddit.get("by_subreddit", {}).items():
            print(f"\n  r/{sub} ({info['count']} posts):")
            for p in info.get("posts", [])[:8]:
                sent_icon = "!" if p["sentiment"] == "fear" else ("+" if p["sentiment"] == "hope" else " ")
                print(f"    {sent_icon} {p['title'][:75]}")

    # 9. Google Trends
    trends = analysis.get("trends_analysis", {})
    if trends.get("total"):
        print(f"\n--- GOOGLE TRENDS ({trends['total']} keywords tracked) ---")
        rising_kw = trends.get("keywords_rising", [])
        falling_kw = trends.get("keywords_falling", [])
        stable_kw = trends.get("keywords_stable", [])
        print(f"  Momentum: {len(rising_kw)} rising, {len(falling_kw)} falling, {len(stable_kw)} stable")

        if rising_kw:
            print(f"\n  RISING:")
            for m in rising_kw[:10]:
                print(f"    +{m['trend_direction']:>3}%  {m['keyword']} (vol: {m['recent_avg']})")
        if falling_kw:
            print(f"\n  FALLING:")
            for m in falling_kw[:5]:
                print(f"    {m['trend_direction']:>4}%  {m['keyword']} (vol: {m['recent_avg']})")

        rq = trends.get("rising_queries", [])
        if rq:
            print(f"\n  TOP RISING QUERIES (Google's breakout/growing signals):")
            for r in rq[:15]:
                label = f"BREAKOUT" if "breakout" in str(r["value"]).lower() else f"+{r['value']}"
                print(f"    {label:>12}  {r['query']}  (from: {r['parent_keyword']})")

    # 10. Importance scoring
    importance = analysis.get("importance", {})
    if importance.get("total_scored"):
        dist = importance.get("distribution", {})
        print(f"\n--- IMPORTANCE SCORING ({importance['total_scored']} queries scored) ---")
        print(f"  Distribution: {dist.get('high', 0)} high / {dist.get('medium', 0)} medium / {dist.get('low', 0)} low")
        print(f"  Avg score: {importance.get('avg_score', 0)} / Max: {importance.get('max_score', 0)}")

        top = importance.get("top_queries", [])
        if top:
            print(f"\n  TOP 25 QUERIES BY IMPORTANCE:")
            print(f"  {'Score':>5}  {'Src':>3}  {'Freq':>4}  {'GSC':>6}  {'Trend':>5}  Query")
            for q in top[:25]:
                trend_str = f"+{q['trend_direction']}%" if q['trend_direction'] > 0 else (f"{q['trend_direction']}%" if q['trend_direction'] < 0 else "")
                flags = ""
                if q.get("is_fear"): flags += " [FEAR]"
                if q.get("is_question"): flags += " [Q]"
                print(f"  {q['score']:>5.1f}  {q['source_count']:>3}  {q['frequency']:>4}  {q['gsc_impressions']:>6}  {trend_str:>5}  {q['query'][:60]}{flags}")

        top_fears = importance.get("top_fears", [])
        if top_fears:
            print(f"\n  TOP FEARS BY IMPORTANCE:")
            for q in top_fears[:10]:
                print(f"    {q['score']:>5.1f}  {q['query'][:65]}")

    print(f"\n{'='*70}\n")


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------
def main():
    parser = argparse.ArgumentParser(description="Search Intent Analyser (data-driven)")
    parser.add_argument("--days", type=int, default=14, help="Lookback window (default: 14)")
    parser.add_argument("--dry-run", action="store_true", help="Analyse + print, don't save")
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

    now = datetime.now(AEST)
    date_str = now.strftime("%Y-%m-%d")
    current_cutoff = (now - timedelta(days=args.days)).strftime("%Y-%m-%d")
    previous_cutoff = (now - timedelta(days=args.days * 2)).strftime("%Y-%m-%d")

    print(f"Search Intent Analyser — {now.strftime('%Y-%m-%d %H:%M AEST')}")
    print(f"Lookback: {args.days} days (cutoff: {current_cutoff})\n")

    # Load data
    print("Loading data...")
    data = load_all_data(sm_db, current_cutoff)
    source_counts = {
        "autocomplete": len(data["suggestions"]),
        "youtube": len(data["youtube"]),
        "paa": len(data["paa"]),
        "reddit": len(data["reddit"]),
        "google_ads": len(data["ads"]),
        "gsc": len(data["gsc"]),
        "trends": len(data["trends"]),
    }
    total = sum(source_counts.values())
    print(f"  {total} records loaded")

    # Run all analyses
    print("\n[1/10] Frequency analysis...")
    frequency = analyse_frequency(data)
    print(f"  Top signal: \"{frequency[0]['query']}\" ({frequency[0]['frequency']}x)" if frequency else "  No data")

    print("[2/10] Cluster discovery...")
    clusters = analyse_clusters(data)
    print(f"  {len(clusters)} emergent clusters found")

    print("[3/10] Fear monitor...")
    fears = analyse_fears(data)
    print(f"  {fears['total']} fear signals across {len(fears['by_type'])} categories")

    print("[4/10] Suburb insights...")
    suburbs = analyse_suburbs(data)
    for name, info in suburbs.items():
        print(f"  {name}: {info['total_queries']} queries, {len(info['fears'])} fears, {len(info['lifestyle'])} lifestyle")

    print("[5/10] Question discovery...")
    questions = analyse_questions(data)
    print(f"  {len(questions)} unique questions ranked")

    print("[6/10] Velocity detection...")
    velocity = analyse_velocity(sm_db, current_cutoff, previous_cutoff)
    print(f"  {velocity['new_query_count']} new queries, {len(velocity['growing'])} growing")

    print("[7/10] Content gap scan...")
    content_gaps = analyse_content_gaps(questions, data["articles"])
    print(f"  {content_gaps['covered']}/{content_gaps['total_questions']} covered ({content_gaps['coverage_pct']}%)")

    print("[8/10] Reddit pulse...")
    reddit_pulse = analyse_reddit(data)
    print(f"  {reddit_pulse.get('total', 0)} posts analysed")

    print("[9/10] Trends analysis...")
    trends_analysis = analyse_trends(data)
    rising = len(trends_analysis.get("keywords_rising", []))
    falling = len(trends_analysis.get("keywords_falling", []))
    print(f"  {trends_analysis.get('total', 0)} keywords — {rising} rising, {falling} falling")

    print("[10/10] Importance scoring...")
    importance = score_importance(data, frequency, questions, fears, trends_analysis)
    dist = importance.get("distribution", {})
    print(f"  {importance['total_scored']} queries scored — {dist.get('high', 0)} high / {dist.get('medium', 0)} medium / {dist.get('low', 0)} low")

    # Assemble
    analysis = {
        "_id": f"analysis_{date_str}",
        "date": date_str,
        "lookback_days": args.days,
        "total_records": total,
        "source_counts": source_counts,
        "frequency": frequency[:100],
        "clusters": clusters,
        "fears": fears,
        "suburbs": suburbs,
        "questions": questions,
        "velocity": velocity,
        "content_gaps": content_gaps,
        "reddit_pulse": reddit_pulse,
        "trends_analysis": trends_analysis,
        "importance": importance,
        "analysed_at": datetime.now(timezone.utc).isoformat(),
    }

    print_analysis(analysis)

    if args.dry_run:
        print("--- DRY RUN (not saved) ---")
        client.close()
        return

    print("Saving to MongoDB...")

    # Extract all_scored_questions into a separate document to stay under Cosmos 2MB limit
    all_scored_q = analysis.get("importance", {}).pop("all_scored_questions", [])

    for attempt in range(5):
        try:
            sm_db["search_intent_analysis"].update_one(
                {"_id": analysis["_id"]}, {"$set": analysis}, upsert=True
            )
            break
        except Exception as e:
            if "16500" in str(e) or "429" in str(e):
                import re
                wait = 0.5 * (attempt + 1)
                m = re.search(r"RetryAfterMs=(\d+)", str(e))
                if m:
                    wait = max(wait, int(m.group(1)) / 1000)
                print(f"  Rate limited, waiting {wait:.1f}s...")
                time.sleep(wait)
            else:
                raise

    sm_db["search_intent_analysis"].create_index("date")
    print("  Saved to search_intent_analysis")

    # Save scored questions as a separate document
    if all_scored_q:
        scored_doc = {
            "_id": f"scored_questions_{date_str}",
            "date": date_str,
            "questions": all_scored_q,
            "total": len(all_scored_q),
        }
        for attempt in range(5):
            try:
                sm_db["search_scored_questions"].update_one(
                    {"_id": scored_doc["_id"]}, {"$set": scored_doc}, upsert=True
                )
                break
            except Exception as e:
                if "16500" in str(e) or "429" in str(e):
                    wait = 0.5 * (attempt + 1)
                    time.sleep(wait)
                else:
                    raise
        sm_db["search_scored_questions"].create_index("date")
        print(f"  Saved {len(all_scored_q)} scored questions to search_scored_questions")

    # Prune
    prune_cutoff = (now - timedelta(days=90)).strftime("%Y-%m-%d")
    pruned = sm_db["search_intent_analysis"].delete_many({"date": {"$lt": prune_cutoff}})
    if pruned.deleted_count:
        print(f"  Pruned {pruned.deleted_count} old analyses")
    pruned2 = sm_db["search_scored_questions"].delete_many({"date": {"$lt": prune_cutoff}})
    if pruned2.deleted_count:
        print(f"  Pruned {pruned2.deleted_count} old scored questions")

    print("\nDone.")
    client.close()


if __name__ == "__main__":
    main()
