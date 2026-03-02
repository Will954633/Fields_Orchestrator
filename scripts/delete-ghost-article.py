#!/usr/bin/env python3
"""
delete-ghost-article.py — Delete articles from Ghost CMS

Usage:
    python3 scripts/delete-ghost-article.py <article_id> [--dry-run] [--no-rebuild]
    python3 scripts/delete-ghost-article.py --list              # list all posts
    python3 scripts/delete-ghost-article.py --search "keyword"  # search by title

Examples:
    # Preview what would be deleted (safe):
    python3 scripts/delete-ghost-article.py 69a52e9eebbfe7000170982b --dry-run

    # Delete and trigger Netlify rebuild:
    python3 scripts/delete-ghost-article.py 69a52e9eebbfe7000170982b

    # Delete without rebuild:
    python3 scripts/delete-ghost-article.py 69a52e9eebbfe7000170982b --no-rebuild

    # List all posts (title, id, status):
    python3 scripts/delete-ghost-article.py --list

    # Search posts by keyword:
    python3 scripts/delete-ghost-article.py --search "migration"

Requires:
    - GHOST_ADMIN_API_KEY in /home/fields/Fields_Orchestrator/.env
    - pip: PyJWT, requests
"""

import sys
import os
import time
import argparse
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
    return {"Authorization": f"Ghost {get_ghost_token()}"}


# ---------------------------------------------------------------------------
# Commands
# ---------------------------------------------------------------------------

def list_posts():
    """List all Ghost posts (published + draft)."""
    page = 1
    all_posts = []
    while True:
        r = requests.get(
            f"{GHOST_ADMIN_BASE}/posts/",
            headers=ghost_headers(),
            params={
                "fields": "id,title,slug,status,published_at,updated_at",
                "limit": 100,
                "page": page,
                "order": "published_at desc",
            },
        )
        r.raise_for_status()
        data = r.json()
        posts = data.get("posts", [])
        if not posts:
            break
        all_posts.extend(posts)
        meta = data.get("meta", {}).get("pagination", {})
        if page >= meta.get("pages", 1):
            break
        page += 1

    if not all_posts:
        print("No posts found in Ghost.")
        return

    print(f"{'STATUS':<10} {'ID':<26} {'TITLE'}")
    print("-" * 80)
    for p in all_posts:
        status = p.get("status", "?")
        pid = p.get("id", "?")
        title = p.get("title", "(untitled)")
        marker = "*" if status == "published" else " "
        print(f"{status:<10} {pid:<26} {marker}{title}")
    print(f"\nTotal: {len(all_posts)} posts")


def search_posts(keyword):
    """Search Ghost posts by title keyword."""
    r = requests.get(
        f"{GHOST_ADMIN_BASE}/posts/",
        headers=ghost_headers(),
        params={
            "fields": "id,title,slug,status,published_at",
            "filter": f"title:~'{keyword}'",
            "limit": "all",
        },
    )
    r.raise_for_status()
    posts = r.json().get("posts", [])
    if not posts:
        # Ghost filter can be finicky — fall back to client-side search
        r2 = requests.get(
            f"{GHOST_ADMIN_BASE}/posts/",
            headers=ghost_headers(),
            params={
                "fields": "id,title,slug,status,published_at",
                "limit": "all",
            },
        )
        r2.raise_for_status()
        all_posts = r2.json().get("posts", [])
        kw = keyword.lower()
        posts = [p for p in all_posts if kw in (p.get("title", "") or "").lower()]

    if not posts:
        print(f"No posts matching '{keyword}'.")
        return

    print(f"{'STATUS':<10} {'ID':<26} {'TITLE'}")
    print("-" * 70)
    for p in posts:
        print(f"{p['status']:<10} {p['id']:<26} {p.get('title', '(untitled)')}")
    print(f"\n{len(posts)} result(s)")


def get_post(post_id):
    """Fetch a single post by ID."""
    r = requests.get(
        f"{GHOST_ADMIN_BASE}/posts/{post_id}/",
        headers=ghost_headers(),
        params={"fields": "id,title,slug,status,published_at"},
    )
    if r.status_code == 404:
        return None
    r.raise_for_status()
    posts = r.json().get("posts", [])
    return posts[0] if posts else None


def delete_post(post_id, dry_run=False, no_rebuild=False):
    """Delete a Ghost post by ID."""
    post = get_post(post_id)
    if not post:
        print(f"ERROR: Post {post_id} not found in Ghost.")
        sys.exit(1)

    title = post.get("title", "(untitled)")
    status = post.get("status", "?")
    print(f"Article found:")
    print(f"  Title:  {title}")
    print(f"  ID:     {post_id}")
    print(f"  Status: {status}")
    print()

    if dry_run:
        print("[DRY RUN] Would delete this article. Run without --dry-run to proceed.")
        return

    # Delete via Admin API
    r = requests.delete(
        f"{GHOST_ADMIN_BASE}/posts/{post_id}/",
        headers=ghost_headers(),
    )

    if r.status_code == 204:
        print(f"DELETED: \"{title}\" ({post_id})")
    elif r.status_code == 404:
        print(f"Post {post_id} was already deleted or does not exist.")
    else:
        print(f"ERROR: Ghost returned {r.status_code}")
        print(r.text)
        sys.exit(1)

    # Trigger Netlify rebuild
    if not no_rebuild:
        print("\nTriggering Netlify rebuild to remove article from website...")
        rb = requests.post(NETLIFY_BUILD_HOOK)
        if rb.status_code == 200:
            print("Netlify rebuild triggered. Site will update in ~2-3 minutes.")
        else:
            print(f"WARNING: Netlify rebuild returned {rb.status_code}: {rb.text}")
            print("You may need to trigger manually: curl -s -X POST", NETLIFY_BUILD_HOOK)
    else:
        print("\n--no-rebuild flag set. Remember to trigger a Netlify rebuild when ready:")
        print(f"  curl -s -X POST {NETLIFY_BUILD_HOOK}")


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def main():
    parser = argparse.ArgumentParser(
        description="Delete articles from Ghost CMS",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="Examples:\n"
               "  %(prog)s --list\n"
               "  %(prog)s --search migration\n"
               "  %(prog)s 69a52e9eebbfe7000170982b --dry-run\n"
               "  %(prog)s 69a52e9eebbfe7000170982b\n",
    )
    parser.add_argument("article_id", nargs="?", help="Ghost article ID to delete")
    parser.add_argument("--list", action="store_true", help="List all Ghost posts")
    parser.add_argument("--search", metavar="KEYWORD", help="Search posts by title")
    parser.add_argument("--dry-run", action="store_true", help="Preview without deleting")
    parser.add_argument("--no-rebuild", action="store_true", help="Skip Netlify rebuild")
    args = parser.parse_args()

    load_env()

    if args.list:
        list_posts()
    elif args.search:
        search_posts(args.search)
    elif args.article_id:
        delete_post(args.article_id, dry_run=args.dry_run, no_rebuild=args.no_rebuild)
    else:
        parser.print_help()
        sys.exit(1)


if __name__ == "__main__":
    main()
