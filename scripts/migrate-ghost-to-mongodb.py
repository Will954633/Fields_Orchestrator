#!/usr/bin/env python3
"""
migrate-ghost-to-mongodb.py — One-time migration of Ghost CMS articles to MongoDB

Fetches all published posts from Ghost Content API and inserts them into
system_monitor.content_articles in MongoDB.

Usage:
    source /home/fields/venv/bin/activate
    python3 scripts/migrate-ghost-to-mongodb.py [--dry-run] [--include-drafts]

Requires:
    GHOST_CONTENT_API_KEY and COSMOS_CONNECTION_STRING in .env
"""

import os
import sys
import json
import argparse
from datetime import datetime, timezone

ENV_PATH = "/home/fields/Fields_Orchestrator/.env"
GHOST_HOST = "https://fields-articles.ghost.io"


def load_env():
    if not os.path.exists(ENV_PATH):
        print(f"ERROR: {ENV_PATH} not found")
        sys.exit(1)
    with open(ENV_PATH) as f:
        for line in f:
            line = line.strip()
            if line and not line.startswith("#") and "=" in line:
                key, _, val = line.partition("=")
                val = val.strip().strip('"').strip("'")
                os.environ.setdefault(key.strip(), val)


def fetch_ghost_posts(include_drafts=False):
    """Fetch all posts from Ghost Content API."""
    import requests

    api_key = os.environ.get("GHOST_CONTENT_API_KEY", "")
    if not api_key:
        print("ERROR: GHOST_CONTENT_API_KEY not set")
        sys.exit(1)

    status_filter = "status:published" if not include_drafts else "status:published,status:draft"

    params = {
        "key": api_key,
        "fields": "id,title,slug,excerpt,published_at,updated_at,created_at,feature_image,custom_excerpt,html,status",
        "filter": status_filter,
        "limit": "all",
        "include": "tags,authors",
    }

    url = f"{GHOST_HOST}/ghost/api/content/posts/"
    print(f"Fetching from Ghost: {url}")

    r = requests.get(url, params=params)
    if r.status_code != 200:
        print(f"ERROR: Ghost API returned {r.status_code}: {r.text[:500]}")
        sys.exit(1)

    posts = r.json().get("posts", [])
    print(f"Fetched {len(posts)} posts from Ghost")
    return posts


def transform_ghost_post(post):
    """Transform a Ghost post to our MongoDB article document format."""
    tags = [t.get("slug", "") for t in (post.get("tags") or []) if t.get("slug")]
    author = (post.get("authors") or [{}])[0]

    return {
        "ghost_id": post.get("id"),  # Keep reference for deduplication
        "title": post.get("title", ""),
        "slug": post.get("slug", ""),
        "html": post.get("html", ""),
        "status": post.get("status", "draft"),
        "tags": tags,
        "custom_excerpt": post.get("custom_excerpt") or post.get("excerpt") or "",
        "feature_image": post.get("feature_image") or "",
        "author": author.get("name", "Fields Research"),
        "author_slug": author.get("slug", "fields"),
        "author_image": author.get("profile_image", ""),
        "created_at": post.get("created_at") or datetime.now(timezone.utc).isoformat(),
        "updated_at": post.get("updated_at") or datetime.now(timezone.utc).isoformat(),
        "published_at": post.get("published_at"),
    }


def main():
    parser = argparse.ArgumentParser(description="Migrate Ghost CMS articles to MongoDB")
    parser.add_argument("--dry-run", action="store_true", help="Show what would be migrated without writing")
    parser.add_argument("--include-drafts", action="store_true", help="Also migrate draft posts")
    args = parser.parse_args()

    load_env()

    posts = fetch_ghost_posts(include_drafts=args.include_drafts)

    if not posts:
        print("No posts to migrate.")
        return

    docs = [transform_ghost_post(p) for p in posts]

    if args.dry_run:
        print(f"\n--- DRY RUN: Would migrate {len(docs)} articles ---")
        for d in docs:
            word_count = len((d["html"] or "").replace("<", " <").split()) if d["html"] else 0
            print(f"  [{d['status'].upper():10}] {d['title'][:60]:<60} ({word_count} words, {len(d['tags'])} tags)")
        print(f"\nTotal: {len(docs)} articles")
        return

    # Connect to MongoDB
    from pymongo import MongoClient
    uri = os.environ.get("COSMOS_CONNECTION_STRING", "")
    if not uri:
        print("ERROR: COSMOS_CONNECTION_STRING not set")
        sys.exit(1)

    client = MongoClient(uri, serverSelectionTimeoutMS=10000, retryWrites=False)
    db = client.system_monitor
    coll = db.content_articles

    # Check for existing articles to avoid duplicates
    existing_ghost_ids = set()
    for doc in coll.find({}, {"ghost_id": 1}):
        if doc.get("ghost_id"):
            existing_ghost_ids.add(doc["ghost_id"])

    new_docs = [d for d in docs if d.get("ghost_id") not in existing_ghost_ids]
    skipped = len(docs) - len(new_docs)

    if skipped > 0:
        print(f"Skipping {skipped} already-migrated articles (matched by ghost_id)")

    if not new_docs:
        print("All articles already migrated. Nothing to do.")
        client.close()
        return

    # Insert
    result = coll.insert_many(new_docs)
    print(f"\nMigrated {len(result.inserted_ids)} articles to system_monitor.content_articles")

    for d in new_docs:
        print(f"  [{d['status'].upper():10}] {d['title'][:70]}")

    print(f"\nDone. Run a Netlify rebuild to update the website:")
    print(f"  curl -s -X POST https://api.netlify.com/build_hooks/699faf0aa7c588800d79f95d")

    client.close()


if __name__ == "__main__":
    main()
