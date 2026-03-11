#!/usr/bin/env python3
"""
Article Index Builder — fetches all published articles from MongoDB
(system_monitor.content_articles) and stores a structured index in
system_monitor.article_index for the marketing advisor.

Usage:
    python3 scripts/build-article-index.py              # Build index
    python3 scripts/build-article-index.py --print       # Print index, don't save
"""

import os
import re
import json
import argparse
from datetime import datetime, timezone
from dotenv import load_dotenv
from pymongo import MongoClient

load_dotenv("/home/fields/Fields_Orchestrator/.env")

COSMOS_URI = os.environ["COSMOS_CONNECTION_STRING"]

# ── Category mapping (mirrored from fetch-articles.js) ────────────────────
TAG_TO_CATEGORY = {
    "analyst":          {"category": "market-analysis", "scope": "agnostic"},
    "state-of-market":  {"category": "market-analysis", "scope": "agnostic"},
    "market-insight":   {"category": "market-analysis", "scope": "suburb-specific"},
    "watch-this-sale":  {"category": "market-update",   "scope": "suburb-specific"},
    "how-it-sold":      {"category": "market-update",   "scope": "suburb-specific"},
    "major-projects":   {"category": "suburb-profile",  "scope": "agnostic"},
    "buyer-strategy":   {"category": "buyer-guide",     "scope": "agnostic"},
    "selling-strategy": {"category": "seller-guide",    "scope": "agnostic"},
    "seller-strategy":  {"category": "seller-guide",    "scope": "agnostic"},
}

SUBURB_SLUGS = [
    "robina", "varsity-lakes", "burleigh-waters", "burleigh-heads",
    "mudgeeraba", "worongary", "reedy-creek", "merrimac",
    "palm-beach", "currumbin", "elanora", "tugun", "carrara",
]

SIGNAL_WORDS = [
    "sold", "sale", "buy", "sell", "market", "price", "growth",
    "investment", "light rail", "infrastructure", "median",
    "demand", "supply", "auction", "rental", "valuation",
    "days on market", "quarterly", "annual", "suburb",
]


def fetch_all_articles(client):
    """Fetch all published articles from system_monitor.content_articles."""
    docs = list(
        client["system_monitor"]["content_articles"].find({"status": "published"})
    )
    return docs


def resolve_category(tags):
    """Determine category + scope from tag slugs (flat string list)."""
    if not tags:
        return "market-analysis", "agnostic", None
    for slug in tags:
        if slug in TAG_TO_CATEGORY:
            info = TAG_TO_CATEGORY[slug]
            return info["category"], info["scope"], slug
    return "market-analysis", "agnostic", None


def resolve_suburbs(doc, scope):
    """Determine suburbs from article slug, tags, and title."""
    if scope == "agnostic":
        return []

    suburb_underscored = [s.replace("-", "_") for s in SUBURB_SLUGS]

    # 1. Check custom_data.suburb if present
    custom_suburb = (doc.get("custom_data") or {}).get("suburb")
    if custom_suburb and custom_suburb in suburb_underscored:
        return [custom_suburb]

    # 2. Check article slug
    post_slug = doc.get("slug", "")
    matched = [s for s in SUBURB_SLUGS if s in post_slug]
    if matched:
        return [s.replace("-", "_") for s in matched]

    # 3. Check tags
    tags = doc.get("tags", [])
    if tags:
        tagged = [t for t in tags if t in SUBURB_SLUGS or t in suburb_underscored]
        if tagged:
            return [s.replace("-", "_") for s in tagged]

    # 4. Check article title for suburb names
    title = (doc.get("title", "") or "").lower()
    if title:
        title_map = {
            "robina": "robina", "varsity lakes": "varsity_lakes",
            "burleigh waters": "burleigh_waters", "burleigh heads": "burleigh_heads",
            "mudgeeraba": "mudgeeraba", "worongary": "worongary",
            "reedy creek": "reedy_creek", "merrimac": "merrimac",
            "palm beach": "palm_beach", "currumbin": "currumbin",
            "elanora": "elanora", "tugun": "tugun", "carrara": "carrara",
        }
        title_matched = [v for k, v in title_map.items() if k in title]
        if title_matched:
            return title_matched

    return []


def extract_key_topics(doc):
    """Extract key topics from title and tags (flat string list)."""
    topics = set()
    for slug in doc.get("tags", []):
        if slug:
            topics.add(slug)
    title_lower = (doc.get("title", "") or "").lower()
    for suburb in SUBURB_SLUGS:
        if suburb.replace("-", " ") in title_lower:
            topics.add(suburb.replace("-", "_"))
    for word in SIGNAL_WORDS:
        if word in title_lower:
            topics.add(word.replace(" ", "_"))
    return list(topics - {""})


def word_count(html):
    """Estimate word count from HTML."""
    if not html:
        return 0
    text = re.sub(r'<[^>]+>', ' ', html)
    return len(text.split())


def build_index(articles):
    """Transform content_articles documents into index documents."""
    docs = []
    for article in articles:
        tags = article.get("tags", [])
        category, scope, matched_tag = resolve_category(tags)
        suburbs = resolve_suburbs(article, scope)
        topics = extract_key_topics(article)
        wc = word_count(article.get("html", ""))
        article_id = str(article["_id"])

        doc = {
            "_id": article_id,
            "title": article.get("title", ""),
            "slug": article.get("slug", ""),
            "url": f"https://fieldsestate.com.au/article/{article_id}",
            "excerpt": article.get("custom_excerpt", "") or "",
            "category": category,
            "scope": scope,
            "matched_tag": matched_tag,
            "suburbs": suburbs,
            "tags": [t for t in tags if t],
            "published_at": str(article.get("published_at", "")),
            "updated_at": str(article.get("updated_at", "")),
            "feature_image": article.get("feature_image"),
            "key_topics": topics,
            "word_count": wc,
            "author": article.get("author", "Fields Research"),
            "indexed_at": datetime.now(timezone.utc).isoformat(),
        }
        docs.append(doc)
    return docs


def save_index(client, docs):
    """Save index to MongoDB using upserts."""
    sm = client["system_monitor"]

    saved = 0
    for doc in docs:
        doc_id = doc.pop("_id")
        sm["article_index"].replace_one(
            {"_id": doc_id},
            {"_id": doc_id, **doc},
            upsert=True,
        )
        saved += 1

    # Summary metadata
    categories = {}
    for doc in docs:
        cat = doc.get("category", "unknown")
        categories[cat] = categories.get(cat, 0) + 1

    sm["article_index_meta"].replace_one(
        {"_id": "latest"},
        {
            "_id": "latest",
            "indexed_at": datetime.now(timezone.utc).isoformat(),
            "article_count": len(docs),
            "categories": categories,
        },
        upsert=True,
    )

    return saved


def main():
    parser = argparse.ArgumentParser(description="Build article index from MongoDB")
    parser.add_argument("--print", action="store_true", help="Print index without saving")
    args = parser.parse_args()

    print(f"[{datetime.now(timezone.utc).isoformat()}] Article Index Builder starting...")
    print("Fetching articles from system_monitor.content_articles...")

    client = MongoClient(COSMOS_URI)
    articles = fetch_all_articles(client)
    print(f"Fetched {len(articles)} published articles")

    docs = build_index(articles)

    # Summary
    categories = {}
    for d in docs:
        cat = d.get("category", "unknown")
        categories[cat] = categories.get(cat, 0) + 1

    print(f"\nIndex summary:")
    for cat, count in sorted(categories.items()):
        print(f"  {cat}: {count}")

    if getattr(args, "print"):
        for d in docs:
            suburbs_str = ", ".join(d.get("suburbs", [])) or "agnostic"
            print(f"\n  [{d.get('category', '')}] {d.get('title', '')}")
            print(f"    URL: {d.get('url', '')}")
            print(f"    Suburbs: {suburbs_str}")
            print(f"    Topics: {', '.join(d.get('key_topics', [])[:8])}")
            print(f"    Published: {d.get('published_at', '')[:10]}")
        client.close()
        return

    saved = save_index(client, docs)
    print(f"\nSaved {saved} articles to system_monitor.article_index")
    client.close()


if __name__ == "__main__":
    main()
