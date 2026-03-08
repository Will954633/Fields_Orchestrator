#!/usr/bin/env python3
"""
push-ghost-draft.py — Push draft articles directly to Ghost CMS

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

    # Update an existing draft:
    python3 scripts/push-ghost-draft.py --update <post_id> --md-file updated.md

Requires:
    source /home/fields/venv/bin/activate
    GHOST_ADMIN_API_KEY in /home/fields/Fields_Orchestrator/.env
    pip: PyJWT, requests, markdown (for --md-file)
"""

import sys
import os
import time
import argparse
import json
import jwt
import requests

# ---------------------------------------------------------------------------
# Config
# ---------------------------------------------------------------------------

ENV_PATH = "/home/fields/Fields_Orchestrator/.env"
GHOST_URL = "https://fields-articles.ghost.io"
GHOST_ADMIN_BASE = f"{GHOST_URL}/ghost/api/admin"
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


def get_ghost_token():
    """Create a short-lived JWT for Ghost Admin API."""
    api_key = os.environ.get("GHOST_ADMIN_API_KEY", "")
    if not api_key or ":" not in api_key:
        print("ERROR: GHOST_ADMIN_API_KEY not set or invalid format (expected id:secret)")
        sys.exit(1)
    api_id, secret = api_key.split(":")
    iat = int(time.time())
    payload = {"iat": iat, "exp": iat + 300, "aud": "/admin/"}
    token = jwt.encode(
        payload,
        bytes.fromhex(secret),
        algorithm="HS256",
        headers={"kid": api_id, "typ": "JWT", "alg": "HS256"},
    )
    return token


def ghost_headers():
    return {
        "Authorization": f"Ghost {get_ghost_token()}",
        "Content-Type": "application/json",
    }


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


# ---------------------------------------------------------------------------
# Commands
# ---------------------------------------------------------------------------

def create_post(title, html, tags=None, excerpt=None, feature_image=None,
                slug=None, publish=False):
    """Create a new Ghost post (draft by default)."""
    post_data = {
        "title": title,
        "html": html,
        "status": "published" if publish else "draft",
    }
    if tags:
        post_data["tags"] = [{"name": t} for t in tags]
    if excerpt:
        post_data["custom_excerpt"] = excerpt
    if feature_image:
        post_data["feature_image"] = feature_image
    if slug:
        post_data["slug"] = slug

    r = requests.post(
        f"{GHOST_ADMIN_BASE}/posts/",
        json={"posts": [post_data]},
        headers=ghost_headers(),
    )

    if r.status_code in (200, 201):
        post = r.json()["posts"][0]
        status_label = "PUBLISHED" if publish else "DRAFT"
        print(f"{status_label} created successfully!")
        print(f"  Title:  {post['title']}")
        print(f"  ID:     {post['id']}")
        print(f"  Slug:   {post['slug']}")
        print(f"  Status: {post['status']}")
        print(f"  URL:    {post.get('url', 'N/A')}")
        print(f"  Edit:   {GHOST_URL}/ghost/#/editor/post/{post['id']}")

        if publish:
            print("\nTriggering Netlify rebuild...")
            rb = requests.post(NETLIFY_BUILD_HOOK)
            if rb.status_code == 200:
                print("Netlify rebuild triggered. Site will update in ~2-3 minutes.")
            else:
                print(f"WARNING: Netlify rebuild returned {rb.status_code}")
        return post
    else:
        print(f"ERROR: Ghost returned {r.status_code}")
        try:
            err = r.json()
            print(json.dumps(err, indent=2))
        except Exception:
            print(r.text)
        sys.exit(1)


def update_post(post_id, html=None, title=None, tags=None, excerpt=None,
                feature_image=None, publish=False):
    """Update an existing Ghost post."""
    # Fetch current post to get updated_at (required by Ghost)
    r = requests.get(
        f"{GHOST_ADMIN_BASE}/posts/{post_id}/",
        headers=ghost_headers(),
    )
    if r.status_code == 404:
        print(f"ERROR: Post {post_id} not found.")
        sys.exit(1)
    r.raise_for_status()
    current = r.json()["posts"][0]

    update_data = {"updated_at": current["updated_at"]}
    if html:
        update_data["html"] = html
    if title:
        update_data["title"] = title
    if tags:
        update_data["tags"] = [{"name": t} for t in tags]
    if excerpt:
        update_data["custom_excerpt"] = excerpt
    if feature_image:
        update_data["feature_image"] = feature_image
    if publish:
        update_data["status"] = "published"

    r = requests.put(
        f"{GHOST_ADMIN_BASE}/posts/{post_id}/",
        json={"posts": [update_data]},
        headers=ghost_headers(),
    )

    if r.status_code == 200:
        post = r.json()["posts"][0]
        print(f"UPDATED successfully!")
        print(f"  Title:  {post['title']}")
        print(f"  ID:     {post['id']}")
        print(f"  Status: {post['status']}")
        print(f"  Edit:   {GHOST_URL}/ghost/#/editor/post/{post['id']}")

        if publish and current["status"] == "draft":
            print("\nTriggering Netlify rebuild...")
            rb = requests.post(NETLIFY_BUILD_HOOK)
            if rb.status_code == 200:
                print("Netlify rebuild triggered.")
        return post
    else:
        print(f"ERROR: Ghost returned {r.status_code}")
        try:
            print(json.dumps(r.json(), indent=2))
        except Exception:
            print(r.text)
        sys.exit(1)


def list_drafts():
    """List all Ghost draft posts."""
    page = 1
    drafts = []
    while True:
        r = requests.get(
            f"{GHOST_ADMIN_BASE}/posts/",
            headers=ghost_headers(),
            params={
                "fields": "id,title,slug,status,created_at,updated_at",
                "filter": "status:draft",
                "limit": 100,
                "page": page,
                "order": "updated_at desc",
            },
        )
        r.raise_for_status()
        data = r.json()
        posts = data.get("posts", [])
        if not posts:
            break
        drafts.extend(posts)
        meta = data.get("meta", {}).get("pagination", {})
        if page >= meta.get("pages", 1):
            break
        page += 1

    if not drafts:
        print("No drafts found in Ghost.")
        return

    print(f"{'UPDATED':<22} {'ID':<26} {'TITLE'}")
    print("-" * 80)
    for d in drafts:
        updated = (d.get("updated_at") or "")[:19].replace("T", " ")
        print(f"{updated:<22} {d['id']:<26} {d.get('title', '(untitled)')}")
    print(f"\n{len(drafts)} draft(s)")


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def main():
    parser = argparse.ArgumentParser(
        description="Push draft articles directly to Ghost CMS",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=(
            "Examples:\n"
            "  %(prog)s --title 'My Article' --md-file article.md\n"
            "  %(prog)s --title 'My Article' --html '<p>Hello</p>' --tag market-insight\n"
            "  %(prog)s --title 'My Article' --html-file article.html --publish\n"
            "  %(prog)s --update POST_ID --md-file updated.md\n"
            "  %(prog)s --list-drafts\n"
        ),
    )

    # Content source (mutually exclusive)
    content = parser.add_mutually_exclusive_group()
    content.add_argument("--html", help="Inline HTML content")
    content.add_argument("--html-file", help="Path to an HTML file")
    content.add_argument("--md-file", help="Path to a Markdown file (converted to HTML)")

    # Post metadata
    parser.add_argument("--title", help="Article title (required for new posts)")
    parser.add_argument("--tag", action="append", dest="tags", help="Tag name (repeatable)")
    parser.add_argument("--excerpt", help="Custom excerpt / meta description")
    parser.add_argument("--feature-image", help="URL for the feature/hero image")
    parser.add_argument("--slug", help="URL slug (auto-generated from title if omitted)")
    parser.add_argument("--publish", action="store_true", help="Publish immediately instead of draft")

    # Update mode
    parser.add_argument("--update", metavar="POST_ID", help="Update an existing post by ID")

    # List mode
    parser.add_argument("--list-drafts", action="store_true", help="List all draft posts")

    args = parser.parse_args()
    load_env()

    # --- List drafts ---
    if args.list_drafts:
        list_drafts()
        return

    # --- Update existing post ---
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

        update_post(
            args.update,
            html=html,
            title=args.title,
            tags=args.tags,
            excerpt=args.excerpt,
            feature_image=args.feature_image,
            publish=args.publish,
        )
        return

    # --- Create new post ---
    if not args.title:
        print("ERROR: --title is required for new posts.")
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

    create_post(
        title=args.title,
        html=html,
        tags=args.tags,
        excerpt=args.excerpt,
        feature_image=args.feature_image,
        slug=args.slug,
        publish=args.publish,
    )


if __name__ == "__main__":
    main()
