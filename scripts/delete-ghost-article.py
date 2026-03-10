#!/usr/bin/env python3
"""
delete-ghost-article.py — Delete articles from MongoDB (replaces Ghost CMS)

Articles are stored in system_monitor.content_articles collection.

Usage:
    python3 scripts/delete-ghost-article.py <article_id> [--dry-run] [--no-rebuild]
    python3 scripts/delete-ghost-article.py --list              # list all articles
    python3 scripts/delete-ghost-article.py --search "keyword"  # search by title

Examples:
    # Preview what would be deleted (safe):
    python3 scripts/delete-ghost-article.py 67cfa3b1... --dry-run

    # Delete and trigger Netlify rebuild:
    python3 scripts/delete-ghost-article.py 67cfa3b1...

    # Delete without rebuild:
    python3 scripts/delete-ghost-article.py 67cfa3b1... --no-rebuild

    # List all articles (title, id, status):
    python3 scripts/delete-ghost-article.py --list

    # Search articles by keyword:
    python3 scripts/delete-ghost-article.py --search "migration"

Requires:
    source /home/fields/venv/bin/activate
    COSMOS_CONNECTION_STRING in /home/fields/Fields_Orchestrator/.env
"""

import sys
import os
import argparse

# ---------------------------------------------------------------------------
# Config
# ---------------------------------------------------------------------------

ENV_PATH = "/home/fields/Fields_Orchestrator/.env"
NETLIFY_BUILD_HOOK = "https://api.netlify.com/build_hooks/699faf0aa7c588800d79f95d"


def load_env():
    """Load .env file into os.environ."""
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


def get_collection():
    """Get the content_articles collection."""
    from pymongo import MongoClient
    uri = os.environ.get("COSMOS_CONNECTION_STRING", "")
    if not uri:
        print("ERROR: COSMOS_CONNECTION_STRING not set")
        sys.exit(1)
    client = MongoClient(uri, serverSelectionTimeoutMS=10000, retryWrites=False)
    return client.system_monitor.content_articles


# ---------------------------------------------------------------------------
# Commands
# ---------------------------------------------------------------------------

def list_articles():
    """List all articles."""
    coll = get_collection()
    articles = list(coll.find({}, {
        "title": 1, "status": 1, "published_at": 1, "updated_at": 1, "tags": 1
    }))

    if not articles:
        print("No articles found.")
        return

    print(f"{'STATUS':<12} {'ID':<26} {'TITLE'}")
    print("-" * 90)
    for a in articles:
        status = a.get("status", "draft").upper()
        aid = str(a["_id"])
        title = a.get("title", "(untitled)")
        marker = "*" if status == "PUBLISHED" else " "
        print(f"{status:<12} {aid:<26} {marker}{title}")
    print(f"\nTotal: {len(articles)} articles")


def search_articles(keyword):
    """Search articles by title keyword."""
    coll = get_collection()
    # Cosmos DB doesn't support $regex well, so fetch all and filter client-side
    articles = list(coll.find({}, {
        "title": 1, "status": 1, "published_at": 1, "tags": 1
    }))

    kw = keyword.lower()
    matched = [a for a in articles if kw in (a.get("title", "") or "").lower()]

    if not matched:
        print(f"No articles matching '{keyword}'.")
        return

    print(f"{'STATUS':<12} {'ID':<26} {'TITLE'}")
    print("-" * 80)
    for a in matched:
        status = a.get("status", "draft").upper()
        print(f"{status:<12} {str(a['_id']):<26} {a.get('title', '(untitled)')}")
    print(f"\n{len(matched)} result(s)")


def delete_article(article_id, dry_run=False, no_rebuild=False):
    """Delete an article by ID."""
    from bson import ObjectId
    coll = get_collection()

    try:
        oid = ObjectId(article_id)
    except Exception:
        print(f"ERROR: Invalid article ID: {article_id}")
        sys.exit(1)

    article = coll.find_one({"_id": oid})
    if not article:
        print(f"ERROR: Article {article_id} not found.")
        sys.exit(1)

    title = article.get("title", "(untitled)")
    status = article.get("status", "draft")
    print(f"Article found:")
    print(f"  Title:  {title}")
    print(f"  ID:     {article_id}")
    print(f"  Status: {status}")
    print(f"  Tags:   {', '.join(article.get('tags', []))}")
    print()

    if dry_run:
        print("[DRY RUN] Would delete this article. Run without --dry-run to proceed.")
        return

    coll.delete_one({"_id": oid})
    print(f'DELETED: "{title}" ({article_id})')

    # Trigger Netlify rebuild if was published
    if status == "published" and not no_rebuild:
        print("\nTriggering Netlify rebuild to remove article from website...")
        try:
            import requests
            rb = requests.post(NETLIFY_BUILD_HOOK)
            if rb.status_code == 200:
                print("Netlify rebuild triggered. Site will update in ~2-3 minutes.")
            else:
                print(f"WARNING: Netlify rebuild returned {rb.status_code}")
        except Exception as e:
            print(f"WARNING: Could not trigger rebuild: {e}")
    elif no_rebuild:
        print("\n--no-rebuild flag set. Remember to trigger a Netlify rebuild when ready:")
        print(f"  curl -s -X POST {NETLIFY_BUILD_HOOK}")
    else:
        print("\nArticle was a draft — no rebuild needed.")


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def main():
    parser = argparse.ArgumentParser(
        description="Delete articles from MongoDB",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="Examples:\n"
               "  %(prog)s --list\n"
               "  %(prog)s --search migration\n"
               "  %(prog)s 67cfa3b1... --dry-run\n"
               "  %(prog)s 67cfa3b1...\n",
    )
    parser.add_argument("article_id", nargs="?", help="Article ID to delete")
    parser.add_argument("--list", action="store_true", help="List all articles")
    parser.add_argument("--search", metavar="KEYWORD", help="Search articles by title")
    parser.add_argument("--dry-run", action="store_true", help="Preview without deleting")
    parser.add_argument("--no-rebuild", action="store_true", help="Skip Netlify rebuild")
    args = parser.parse_args()

    load_env()

    if args.list:
        list_articles()
    elif args.search:
        search_articles(args.search)
    elif args.article_id:
        delete_article(args.article_id, dry_run=args.dry_run, no_rebuild=args.no_rebuild)
    else:
        parser.print_help()
        sys.exit(1)


if __name__ == "__main__":
    main()
