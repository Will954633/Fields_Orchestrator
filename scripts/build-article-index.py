#!/usr/bin/env python3
"""
Article Index Builder — fetches all published Ghost articles and stores
a structured index in system_monitor.article_index for the marketing advisor.

Usage:
    python3 scripts/build-article-index.py              # Build index
    python3 scripts/build-article-index.py --print       # Print index, don't save
"""

import os
import re
import json
import argparse
import requests
from datetime import datetime, timezone
from dotenv import load_dotenv
from pymongo import MongoClient

load_dotenv("/home/fields/Fields_Orchestrator/.env")

GHOST_HOST = "https://fields-articles.ghost.io"
GHOST_CONTENT_API_KEY = os.environ["GHOST_CONTENT_API_KEY"]
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


def fetch_all_posts():
    """Fetch all published posts from Ghost Content API."""
    url = f"{GHOST_HOST}/ghost/api/content/posts/"
    params = {
        "key": GHOST_CONTENT_API_KEY,
        "fields": "id,title,slug,excerpt,custom_excerpt,published_at,updated_at,feature_image,html",
        "filter": "status:published",
        "limit": "all",
        "include": "tags,authors",
    }
    r = requests.get(url, params=params, timeout=30)
    r.raise_for_status()
    return r.json().get("posts", [])


def resolve_category(tags):
    """Determine category + scope from Ghost tags."""
    if not tags:
        return "market-analysis", "agnostic", None
    for tag in tags:
        slug = tag.get("slug", "")
        if slug in TAG_TO_CATEGORY:
            info = TAG_TO_CATEGORY[slug]
            return info["category"], info["scope"], slug
    return "market-analysis", "agnostic", None


def resolve_suburbs(post, scope):
    """Determine suburbs from post slug and tags."""
    if scope == "agnostic":
        return []
    post_slug = post.get("slug", "")
    matched = [s for s in SUBURB_SLUGS if s in post_slug]
    if matched:
        return [s.replace("-", "_") for s in matched]
    tags = post.get("tags", [])
    if tags:
        tagged = [t.get("slug", "") for t in tags if t.get("slug", "") in SUBURB_SLUGS]
        if tagged:
            return [s.replace("-", "_") for s in tagged]
    return []


def extract_key_topics(post):
    """Extract key topics from title and tags."""
    topics = set()
    for tag in post.get("tags", []):
        slug = tag.get("slug", "")
        if slug:
            topics.add(slug)
    title_lower = (post.get("title", "") or "").lower()
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


def build_index(posts):
    """Transform Ghost posts into index documents."""
    docs = []
    for post in posts:
        tags = post.get("tags", [])
        category, scope, matched_tag = resolve_category(tags)
        suburbs = resolve_suburbs(post, scope)
        topics = extract_key_topics(post)
        wc = word_count(post.get("html", ""))

        doc = {
            "_id": post["id"],
            "title": post.get("title", ""),
            "slug": post.get("slug", ""),
            "url": f"https://fieldsestate.com.au/article/{post['id']}",
            "excerpt": post.get("custom_excerpt") or post.get("excerpt", "") or "",
            "category": category,
            "scope": scope,
            "matched_tag": matched_tag,
            "suburbs": suburbs,
            "tags": [t.get("slug", "") for t in tags if t.get("slug")],
            "published_at": post.get("published_at", ""),
            "updated_at": post.get("updated_at", ""),
            "feature_image": post.get("feature_image"),
            "key_topics": topics,
            "word_count": wc,
            "author": (post.get("authors", [{}]) or [{}])[0].get("name", "Fields Research"),
            "indexed_at": datetime.now(timezone.utc).isoformat(),
        }
        docs.append(doc)
    return docs


def save_index(docs):
    """Save index to MongoDB using upserts."""
    client = MongoClient(COSMOS_URI)
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

    client.close()
    return saved


def main():
    parser = argparse.ArgumentParser(description="Build article index from Ghost CMS")
    parser.add_argument("--print", action="store_true", help="Print index without saving")
    args = parser.parse_args()

    print(f"[{datetime.now(timezone.utc).isoformat()}] Article Index Builder starting...")
    print(f"Fetching articles from {GHOST_HOST}...")

    posts = fetch_all_posts()
    print(f"Fetched {len(posts)} published articles")

    docs = build_index(posts)

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
        return

    saved = save_index(docs)
    print(f"\nSaved {saved} articles to system_monitor.article_index")


if __name__ == "__main__":
    main()
