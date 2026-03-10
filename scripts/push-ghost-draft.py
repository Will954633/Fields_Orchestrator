#!/usr/bin/env python3
"""
push-ghost-draft.py — Push draft articles to MongoDB (replaces Ghost CMS)

Articles are stored in system_monitor.content_articles collection.
The website reads from this collection at build time via fetch-articles.js.

Usage:
    # From an HTML file:
    python3 scripts/push-ghost-draft.py --title "My Article" --html-file article.html

    # From a Markdown file:
    python3 scripts/push-ghost-draft.py --title "My Article" --md-file article.md

    # Inline HTML:
    python3 scripts/push-ghost-draft.py --title "My Article" --html "<p>Content here.</p>"

    # With all options:
    python3 scripts/push-ghost-draft.py \
        --title "Robina Market Update — March 2026" \
        --md-file drafts/robina-update.md \
        --tag market-insight \
        --tag robina \
        --excerpt "What March data tells us about Robina pricing." \
        --feature-image "https://example.com/hero.jpg" \
        --slug "robina-market-update-march-2026"

    # Publish immediately (not draft):
    python3 scripts/push-ghost-draft.py --title "Title" --html "<p>Body</p>" --publish

    # List existing drafts:
    python3 scripts/push-ghost-draft.py --list-drafts

    # Update an existing article:
    python3 scripts/push-ghost-draft.py --update <article_id> --md-file updated.md

Requires:
    source /home/fields/venv/bin/activate
    COSMOS_CONNECTION_STRING in /home/fields/Fields_Orchestrator/.env
    pip: pymongo, markdown (for --md-file)
"""

import sys
import os
import argparse
import json
from datetime import datetime, timezone

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


def get_db():
    """Get MongoDB connection to system_monitor database."""
    from pymongo import MongoClient
    uri = os.environ.get("COSMOS_CONNECTION_STRING", "")
    if not uri:
        print("ERROR: COSMOS_CONNECTION_STRING not set")
        sys.exit(1)
    client = MongoClient(uri, serverSelectionTimeoutMS=10000, retryWrites=False)
    return client.system_monitor


# ---------------------------------------------------------------------------
# Content helpers
# ---------------------------------------------------------------------------

def read_html_file(path):
    """Read an HTML file and return its content."""
    if not os.path.exists(path):
        print(f"ERROR: File not found: {path}")
        sys.exit(1)
    with open(path) as f:
        return f.read()


def read_markdown_file(path):
    """Read a Markdown file, convert to HTML, return it."""
    if not os.path.exists(path):
        print(f"ERROR: File not found: {path}")
        sys.exit(1)
    try:
        import markdown
    except ImportError:
        print("ERROR: 'markdown' package not installed. Run: pip install markdown")
        sys.exit(1)
    with open(path) as f:
        md_text = f.read()
    html = markdown.markdown(
        md_text,
        extensions=["tables", "fenced_code", "nl2br", "smarty"],
    )
    return html


def generate_slug(title):
    """Generate a URL-friendly slug from a title."""
    import re
    slug = title.lower()
    slug = re.sub(r'[^a-z0-9]+', '-', slug)
    slug = slug.strip('-')
    return slug[:120]


# ---------------------------------------------------------------------------
# Commands
# ---------------------------------------------------------------------------

def create_article(title, html, tags=None, excerpt=None, feature_image=None,
                   slug=None, publish=False, author=None, author_slug=None):
    """Create a new article in MongoDB."""
    db = get_db()
    now = datetime.now(timezone.utc).isoformat()

    doc = {
        "title": title,
        "slug": slug or generate_slug(title),
        "html": html,
        "status": "published" if publish else "draft",
        "tags": tags or [],
        "custom_excerpt": excerpt or "",
        "feature_image": feature_image or "",
        "author": author or "Fields Research",
        "author_slug": author_slug or "fields",
        "author_image": "",
        "created_at": now,
        "updated_at": now,
        "published_at": now if publish else None,
    }

    result = db.content_articles.insert_one(doc)
    article_id = str(result.inserted_id)

    status_label = "PUBLISHED" if publish else "DRAFT"
    print(f"{status_label} created successfully!")
    print(f"  Title:  {doc['title']}")
    print(f"  ID:     {article_id}")
    print(f"  Slug:   {doc['slug']}")
    print(f"  Status: {doc['status']}")
    print(f"  Tags:   {', '.join(doc['tags'])}")

    if publish:
        print("\nTriggering Netlify rebuild...")
        try:
            import requests
            rb = requests.post(NETLIFY_BUILD_HOOK)
            if rb.status_code == 200:
                print("Netlify rebuild triggered. Site will update in ~2-3 minutes.")
            else:
                print(f"WARNING: Netlify rebuild returned {rb.status_code}")
        except Exception as e:
            print(f"WARNING: Could not trigger rebuild: {e}")

    return article_id


def update_article(article_id, html=None, title=None, tags=None, excerpt=None,
                   feature_image=None, publish=False):
    """Update an existing article in MongoDB."""
    from bson import ObjectId
    db = get_db()

    try:
        oid = ObjectId(article_id)
    except Exception:
        print(f"ERROR: Invalid article ID: {article_id}")
        sys.exit(1)

    existing = db.content_articles.find_one({"_id": oid})
    if not existing:
        print(f"ERROR: Article {article_id} not found.")
        sys.exit(1)

    now = datetime.now(timezone.utc).isoformat()
    updates = {"updated_at": now}

    if html:
        updates["html"] = html
    if title:
        updates["title"] = title
    if tags:
        updates["tags"] = tags
    if excerpt:
        updates["custom_excerpt"] = excerpt
    if feature_image:
        updates["feature_image"] = feature_image
    if publish:
        updates["status"] = "published"
        if not existing.get("published_at"):
            updates["published_at"] = now

    db.content_articles.update_one({"_id": oid}, {"$set": updates})

    print(f"UPDATED successfully!")
    print(f"  Title:  {existing.get('title', '(untitled)')}")
    print(f"  ID:     {article_id}")
    print(f"  Status: {updates.get('status', existing.get('status', 'draft'))}")

    if publish and existing.get("status") == "draft":
        print("\nTriggering Netlify rebuild...")
        try:
            import requests
            rb = requests.post(NETLIFY_BUILD_HOOK)
            if rb.status_code == 200:
                print("Netlify rebuild triggered.")
        except Exception as e:
            print(f"WARNING: Could not trigger rebuild: {e}")


def list_drafts():
    """List all draft articles from MongoDB."""
    db = get_db()
    drafts = list(db.content_articles.find({"status": "draft"}))

    if not drafts:
        print("No drafts found.")
        return

    print(f"{'UPDATED':<22} {'ID':<26} {'TITLE'}")
    print("-" * 80)
    for d in drafts:
        updated = (d.get("updated_at") or "")[:19].replace("T", " ")
        print(f"{updated:<22} {str(d['_id']):<26} {d.get('title', '(untitled)')}")
    print(f"\n{len(drafts)} draft(s)")


def list_all():
    """List all articles from MongoDB."""
    db = get_db()
    articles = list(db.content_articles.find())

    if not articles:
        print("No articles found.")
        return

    print(f"{'STATUS':<12} {'UPDATED':<22} {'ID':<26} {'TITLE'}")
    print("-" * 100)
    for a in articles:
        updated = (a.get("updated_at") or "")[:19].replace("T", " ")
        status = a.get("status", "draft").upper()
        print(f"{status:<12} {updated:<22} {str(a['_id']):<26} {a.get('title', '(untitled)')}")
    print(f"\n{len(articles)} article(s)")


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def main():
    parser = argparse.ArgumentParser(
        description="Push articles to MongoDB (replaces Ghost CMS)",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=(
            "Examples:\n"
            "  %(prog)s --title 'My Article' --md-file article.md\n"
            "  %(prog)s --title 'My Article' --html '<p>Hello</p>' --tag market-insight\n"
            "  %(prog)s --title 'My Article' --html-file article.html --publish\n"
            "  %(prog)s --update ARTICLE_ID --md-file updated.md\n"
            "  %(prog)s --list-drafts\n"
            "  %(prog)s --list-all\n"
        ),
    )

    # Content source (mutually exclusive)
    content = parser.add_mutually_exclusive_group()
    content.add_argument("--html", help="Inline HTML content")
    content.add_argument("--html-file", help="Path to an HTML file")
    content.add_argument("--md-file", help="Path to a Markdown file (converted to HTML)")

    # Post metadata
    parser.add_argument("--title", help="Article title (required for new articles)")
    parser.add_argument("--tag", action="append", dest="tags", help="Tag name (repeatable)")
    parser.add_argument("--excerpt", help="Custom excerpt / meta description")
    parser.add_argument("--feature-image", help="URL for the feature/hero image")
    parser.add_argument("--slug", help="URL slug (auto-generated from title if omitted)")
    parser.add_argument("--publish", action="store_true", help="Publish immediately instead of draft")
    parser.add_argument("--author", help="Author name (default: Fields Research)")
    parser.add_argument("--author-slug", help="Author slug (default: fields)")

    # Update mode
    parser.add_argument("--update", metavar="ARTICLE_ID", help="Update an existing article by ID")

    # List modes
    parser.add_argument("--list-drafts", action="store_true", help="List all draft articles")
    parser.add_argument("--list-all", action="store_true", help="List all articles")

    args = parser.parse_args()
    load_env()

    # --- List drafts ---
    if args.list_drafts:
        list_drafts()
        return

    # --- List all ---
    if args.list_all:
        list_all()
        return

    # --- Update existing article ---
    if args.update:
        html = None
        if args.html:
            html = args.html
        elif args.html_file:
            html = read_html_file(args.html_file)
        elif args.md_file:
            html = read_markdown_file(args.md_file)

        if not html and not args.title and not args.tags and not args.excerpt and not args.feature_image:
            print("ERROR: Nothing to update. Provide --html, --md-file, --html-file, --title, --tag, --excerpt, or --feature-image.")
            sys.exit(1)

        update_article(
            args.update,
            html=html,
            title=args.title,
            tags=args.tags,
            excerpt=args.excerpt,
            feature_image=args.feature_image,
            publish=args.publish,
        )
        return

    # --- Create new article ---
    if not args.title:
        print("ERROR: --title is required for new articles.")
        parser.print_help()
        sys.exit(1)

    html = None
    if args.html:
        html = args.html
    elif args.html_file:
        html = read_html_file(args.html_file)
    elif args.md_file:
        html = read_markdown_file(args.md_file)
    else:
        print("ERROR: Provide content via --html, --html-file, or --md-file.")
        sys.exit(1)

    create_article(
        title=args.title,
        html=html,
        tags=args.tags,
        excerpt=args.excerpt,
        feature_image=args.feature_image,
        slug=args.slug,
        publish=args.publish,
        author=args.author,
        author_slug=args.author_slug,
    )


if __name__ == "__main__":
    main()
