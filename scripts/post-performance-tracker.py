#!/usr/bin/env python3
"""
Post Performance Tracker — fetches engagement metrics for recent Facebook posts
and writes verdicts to institutional memory.

Runs every 6 hours via cron. Checks posts that haven't been finalized yet.
- Posts >24h old: fetch and save engagement metrics + organic post insights
- Posts >72h old: write a verdict to fb_ad_tests (institutional memory) and mark finalized

Two independent metric layers are stored on each fb_page_posts document:
  engagement — likes/comments/shares from the post edges (unchanged, legacy)
  insights   — the Graph API /insights edge (post_clicks, reactions by type, ...)

Usage:
    python3 scripts/post-performance-tracker.py                    # Run tracker
    python3 scripts/post-performance-tracker.py --dry-run          # Show what would happen
    python3 scripts/post-performance-tracker.py --refresh-insights # Re-collect insights on
                                                                   # finalized posts too
    python3 scripts/post-performance-tracker.py --backfill-articles # Link posts to articles
"""

import os
import re
import sys
import argparse
import requests
from datetime import datetime, timezone, timedelta
from dateutil import parser as dateparser
from dotenv import load_dotenv
from pymongo import MongoClient
from bson import ObjectId

load_dotenv("/home/fields/Fields_Orchestrator/.env")

ADS_TOKEN = os.environ["FACEBOOK_ADS_TOKEN"]
PAGE_ID = os.environ["FACEBOOK_PAGE_ID"]
API_VERSION = os.environ.get("FACEBOOK_API_VERSION", "v18.0")
BASE = f"https://graph.facebook.com/{API_VERSION}"
COSMOS_URI = os.environ["COSMOS_CONNECTION_STRING"]


# Organic post insight metrics we ask for, in priority order.
#
# NOTE (verified live 2026-08-13, token has read_insights granted):
# Meta removed the post-level impressions/reach family from the Graph API — every one of
# post_impressions, post_impressions_unique, post_impressions_organic, post_engaged_users,
# post_clicks_unique and post_negative_feedback returns
#   (#100) The value must be a valid insights metric
# on BOTH v18.0 and v23.0. That is a deprecation, not a permission problem. We still REQUEST
# them (cheap, and they come back the day Meta restores or renames them) but degrade per
# metric so one refusal never costs us the rest. What actually returns data today is
# post_clicks, post_clicks_by_type, post_reactions_by_type_total, post_reactions_like_total,
# post_activity_by_action_type, post_fan_reach (reach among page fans — the only reach-ish
# number left) and the post_video_* family.
INSIGHT_METRICS = [
    "post_impressions",
    "post_impressions_unique",
    "post_clicks",
    "post_clicks_by_type",
    "post_reactions_by_type_total",
    "post_reactions_like_total",
    "post_activity_by_action_type",
    "post_fan_reach",
    "post_video_views",
    "post_video_views_organic",
]

# Metrics we already know Meta refuses — logged as "deprecated" rather than "error" so a real
# new breakage stands out in the logs.
KNOWN_DEPRECATED = {
    "post_impressions",
    "post_impressions_unique",
    "post_impressions_organic",
    "post_impressions_organic_unique",
    "post_engaged_users",
    "post_clicks_unique",
    "post_negative_feedback",
}

ARTICLE_LINK_RE = re.compile(r"/articles?/([A-Za-z0-9][A-Za-z0-9_-]*)")


def fb_get(path, params=None, token=None):
    p = {"access_token": token or ADS_TOKEN, **(params or {})}
    r = requests.get(f"{BASE}{path}", params=p, timeout=15)
    r.raise_for_status()
    return r.json()


def get_page_token():
    data = fb_get(f"/{PAGE_ID}", {"fields": "access_token"})
    return data["access_token"]


def get_unfinalized_posts(include_finalized=False):
    """Get posts that haven't been finalized yet (or all posts, for an insights refresh)."""
    client = MongoClient(COSMOS_URI)
    sm = client["system_monitor"]
    query = {} if include_finalized else {"finalized": {"$ne": True}}
    posts = list(sm["fb_page_posts"].find(query).sort("_id", -1).limit(50))
    client.close()
    return posts


def fetch_post_engagement(post_id, page_token):
    """Fetch engagement metrics for a single post."""
    try:
        data = fb_get(
            f"/{post_id}",
            {"fields": "likes.summary(true),comments.summary(true),shares,created_time"},
            token=page_token,
        )
        likes = data.get("likes", {}).get("summary", {}).get("total_count", 0)
        comments = data.get("comments", {}).get("summary", {}).get("total_count", 0)
        shares = data.get("shares", {}).get("count", 0)
        return {
            "likes": likes,
            "comments": comments,
            "shares": shares,
            "total_engagements": likes + comments + shares,
        }
    except requests.exceptions.HTTPError as e:
        # Post might have been deleted or is not accessible
        return {"error": str(e), "likes": 0, "comments": 0, "shares": 0, "total_engagements": 0}
    except Exception as e:
        return {"error": str(e), "likes": 0, "comments": 0, "shares": 0, "total_engagements": 0}


def _insights_request(post_id, metrics, page_token):
    """Ask the /insights edge for a list of metrics. Returns (values, error_message)."""
    try:
        data = fb_get(
            f"/{post_id}/insights",
            {"metric": ",".join(metrics)},
            token=page_token,
        )
    except requests.exceptions.HTTPError as e:
        msg = ""
        try:
            msg = e.response.json().get("error", {}).get("message", "")
        except Exception:
            msg = str(e)
        return None, msg or str(e)
    except Exception as e:
        return None, str(e)

    values = {}
    for row in data.get("data", []):
        name = row.get("name")
        vals = row.get("values") or []
        values[name] = vals[0].get("value") if vals else None
    return values, None


def fetch_post_insights(post_id, page_token):
    """Fetch the Graph API /insights edge for a post.

    Facebook rejects the whole batch if ANY requested metric is invalid, so we try the batch
    first (one call) and fall back to one call per metric on failure. A metric that is refused
    is recorded in `unavailable` with its reason — never silently reported as zero.
    """
    result = {
        "metrics": {},
        "unavailable": {},
        "api_version": API_VERSION,
        "collected_at": datetime.now(timezone.utc).isoformat(),
    }

    values, err = _insights_request(post_id, INSIGHT_METRICS, page_token)
    if values is not None:
        result["metrics"] = values
        for m in INSIGHT_METRICS:
            if m not in values:
                result["unavailable"][m] = "not returned by API"
        return result

    # Batch refused — degrade to one request per metric so a single bad metric costs nothing.
    result["batch_error"] = err
    for metric in INSIGHT_METRICS:
        vals, merr = _insights_request(post_id, [metric], page_token)
        if vals is None:
            reason = merr or "unknown error"
            if metric in KNOWN_DEPRECATED and "valid insights metric" in reason:
                reason = f"deprecated by Meta ({reason})"
            result["unavailable"][metric] = reason
        elif metric in vals:
            result["metrics"][metric] = vals[metric]
        else:
            result["unavailable"][metric] = "not returned by API"
    return result


def summarise_insights(insights):
    """One-line human summary of the insight metrics that actually came back."""
    m = insights.get("metrics", {})
    if not m:
        return "no insight metrics available"
    parts = []
    for name, val in m.items():
        if isinstance(val, dict):
            if not val:
                continue
            val = ", ".join(f"{k}={v}" for k, v in val.items())
        if val in (None, 0, "", {}):
            continue
        parts.append(f"{name}={val}")
    return ", ".join(parts) if parts else "all available metrics zero"


def update_post_insights(post_doc_id, insights):
    """Write the insights sub-document. Does NOT touch the legacy `engagement` field."""
    client = MongoClient(COSMOS_URI)
    sm = client["system_monitor"]
    sm["fb_page_posts"].update_one(
        {"_id": post_doc_id},
        {"$set": {"insights": insights}},
    )
    client.close()


# ── Article linkage ──────────────────────────────────────────────────────

def resolve_article_from_link(link, articles_coll):
    """Given a post `link`, resolve it to (article_id, article_slug) or (None, None).

    Handles both URL shapes we have used:
      /article/<mongo _id>    (the two 2026-03-05 posts)
      /articles/<slug>        (current public route)
    """
    if not link or not isinstance(link, str):
        return None, None
    match = ARTICLE_LINK_RE.search(link)
    if not match:
        return None, None
    token = match.group(1)

    doc = None
    if re.fullmatch(r"[0-9a-fA-F]{24}", token):
        try:
            doc = articles_coll.find_one({"_id": ObjectId(token)})
        except Exception:
            doc = None
        if doc is None:
            # Articles migrated from Ghost carry string _id values, and the pre-migration
            # id lives on as `ghost_id` — the two 2026-03-05 links use that older id.
            doc = articles_coll.find_one({"_id": token}) or \
                articles_coll.find_one({"ghost_id": token})
    if doc is None:
        doc = articles_coll.find_one({"slug": token})

    if doc is None:
        # The link is unambiguously an article link but we cannot find the article.
        # Return the identifier we have rather than inventing one.
        return (token, None) if len(token) == 24 else (None, token)

    return str(doc["_id"]), doc.get("slug")


def backfill_article_links(dry_run=False):
    """Populate article_id / article_slug on posts whose `link` points at an article.

    Posts with no article link are left untouched (fields stay absent/null) — we never
    guess which article an un-linked post was about.
    """
    client = MongoClient(COSMOS_URI)
    sm = client["system_monitor"]
    posts = list(sm["fb_page_posts"].find({}))
    articles = sm["content_articles"]

    linked = 0
    for post in posts:
        if post.get("article_id"):
            continue
        link = post.get("link")
        if isinstance(link, str) and link.lower() == "none":
            link = None
        article_id, slug = resolve_article_from_link(link, articles)
        if not article_id and not slug:
            continue
        print(f"  [{post.get('post_id')}] {link}")
        print(f"    -> article_id={article_id} article_slug={slug}")
        if not dry_run:
            sm["fb_page_posts"].update_one(
                {"_id": post["_id"]},
                {"$set": {"article_id": article_id, "article_slug": slug}},
            )
        linked += 1

    client.close()
    print(f"{'Would link' if dry_run else 'Linked'} {linked} post(s) to articles; "
          f"{len(posts) - linked} left untouched.")
    return linked


def update_post_metrics(post_doc_id, metrics):
    """Write engagement metrics back to the post document."""
    client = MongoClient(COSMOS_URI)
    sm = client["system_monitor"]
    sm["fb_page_posts"].update_one(
        {"_id": post_doc_id},
        {"$set": {
            "engagement": metrics,
            "last_checked": datetime.now(timezone.utc).isoformat(),
        }}
    )
    client.close()


def write_verdict(post, metrics, insights=None):
    """Write a verdict to institutional memory (fb_ad_tests)."""
    total = metrics.get("total_engagements", 0)

    # Determine verdict based on engagement
    if total >= 10:
        verdict = "strong"
    elif total >= 3:
        verdict = "moderate"
    else:
        verdict = "weak"

    doc = {
        "type": "post_performance",
        "post_id": post.get("post_id", ""),
        "message_preview": post.get("message", "")[:150],
        "template_type": post.get("template_type", "unknown"),
        "content_type": post.get("content_type", "text"),
        "source": post.get("source", "unknown"),
        "posted_at": post.get("posted_at", ""),
        "article_id": post.get("article_id"),
        "article_slug": post.get("article_slug"),
        "metrics": {
            "likes": metrics.get("likes", 0),
            "comments": metrics.get("comments", 0),
            "shares": metrics.get("shares", 0),
            "total_engagements": total,
        },
        "insights": (insights or {}).get("metrics", {}),
        "insights_unavailable": sorted((insights or {}).get("unavailable", {}).keys()),
        "verdict": verdict,
        "finalized_at": datetime.now(timezone.utc).isoformat(),
    }

    client = MongoClient(COSMOS_URI)
    sm = client["system_monitor"]
    sm["fb_ad_tests"].insert_one(doc)
    client.close()

    return verdict


def finalize_post(post_doc_id):
    """Mark a post as finalized so we don't check it again."""
    client = MongoClient(COSMOS_URI)
    sm = client["system_monitor"]
    sm["fb_page_posts"].update_one(
        {"_id": post_doc_id},
        {"$set": {"finalized": True}}
    )
    client.close()


def parse_post_time(post):
    """Parse the posted_at field, handling various formats."""
    posted_at = post.get("posted_at", "")
    if not posted_at:
        return None
    try:
        return dateparser.parse(posted_at)
    except Exception:
        return None


def main():
    ap = argparse.ArgumentParser(description="Track Facebook post performance")
    ap.add_argument("--dry-run", action="store_true", help="Show what would happen")
    ap.add_argument("--refresh-insights", action="store_true",
                    help="Also (re)collect /insights on already-finalized posts")
    ap.add_argument("--backfill-articles", action="store_true",
                    help="Populate article_id/article_slug from post links, then exit")
    args = ap.parse_args()

    print(f"[{datetime.now(timezone.utc).isoformat()}] Post Performance Tracker starting...")

    if args.backfill_articles:
        print("Backfilling article links...")
        backfill_article_links(dry_run=args.dry_run)
        return

    posts = get_unfinalized_posts(include_finalized=args.refresh_insights)
    if not posts:
        print("No unfinalized posts to check.")
        return

    label = "post(s)" if args.refresh_insights else "unfinalized post(s)"
    print(f"Found {len(posts)} {label}")

    page_token = get_page_token()
    now = datetime.now(timezone.utc)

    checked = 0
    finalized_count = 0

    for post in posts:
        post_id = post.get("post_id", "")
        posted_at = parse_post_time(post)
        message_preview = post.get("message", "")[:60]

        if not post_id:
            print(f"  Skipping post with no post_id: {post.get('_id')}")
            continue

        if not posted_at:
            print(f"  Skipping post with unparseable date: {post_id}")
            continue

        # Make posted_at timezone-aware if it isn't
        if posted_at.tzinfo is None:
            posted_at = posted_at.replace(tzinfo=timezone.utc)

        age_hours = (now - posted_at).total_seconds() / 3600

        if age_hours < 24:
            print(f"  [{post_id}] Too recent ({age_hours:.1f}h) — skipping")
            continue

        print(f"  [{post_id}] Age: {age_hours:.1f}h — \"{message_preview}...\"")

        if args.dry_run:
            if age_hours >= 72:
                print(f"    -> Would finalize (>72h)")
            else:
                print(f"    -> Would fetch metrics")
            continue

        # Fetch engagement
        metrics = fetch_post_engagement(post_id, page_token)
        checked += 1

        if metrics.get("error"):
            print(f"    -> Error fetching: {metrics['error'][:80]}")

        print(f"    -> Likes: {metrics['likes']}, Comments: {metrics['comments']}, Shares: {metrics['shares']}")

        # Update metrics on the post doc
        update_post_metrics(post["_id"], metrics)

        # Organic insights (separate sub-document — never overwrites `engagement`)
        insights = fetch_post_insights(post_id, page_token)
        update_post_insights(post["_id"], insights)
        print(f"    -> Insights: {summarise_insights(insights)}")
        if insights.get("unavailable"):
            for name, reason in insights["unavailable"].items():
                print(f"       unavailable: {name} — {reason[:90]}")

        # Already-finalized posts are only here for an insights refresh — do not re-verdict.
        if post.get("finalized"):
            continue

        # If >72h, finalize with verdict
        if age_hours >= 72:
            verdict = write_verdict(post, metrics, insights)
            finalize_post(post["_id"])
            finalized_count += 1
            print(f"    -> Verdict: {verdict.upper()} — written to institutional memory")

    if args.dry_run:
        print("\n(Dry run — nothing written)")
    else:
        print(f"\nDone. Checked: {checked}, Finalized: {finalized_count}")


if __name__ == "__main__":
    main()
