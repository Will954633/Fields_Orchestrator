#!/usr/bin/env python3
"""
Harvest the two sources the V4 research session could not reach:

  1. Reddit      — via the PullPush archive API (api.pullpush.io). Free, no auth,
                   full comment/submission bodies with full-text search.
                   ARCHIVE ENDS 2025-05-19 — nothing newer is retrievable this way.
  2. PropertyChat — via Bright Data Web Unlocker (propertychat.com.au returns 403
                   to a direct fetch from this VM; the Unlocker gets 200).

Reddit is NOT reachable directly: reddit.com returns 403 to the VM, WebFetch refuses
the host, Bright Data refuses reddit.com without a completed KYC form, and every
public redlib/libreddit mirror tested sits behind an Anubis bot-check.

Output: raw JSON/HTML into sources/, so every quote in the evidence doc stays traceable.

Usage:
    python3 harvest_reddit_propertychat.py [--reddit] [--propertychat]
"""

import argparse
import json
import os
import re
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

import requests

HERE = Path(__file__).resolve().parent
SOURCES = HERE / "sources"
SOURCES.mkdir(exist_ok=True)

PULLPUSH = "https://api.pullpush.io/reddit/search/{kind}/"
BRIGHTDATA = "https://api.brightdata.com/request"

# PullPush is a volunteer-run archive — keep well under its rate limit.
# 1.2s was far too fast: it 429'd 127 requests in one run and lost most of the corpus.
PP_DELAY = 4.0
PP_BACKOFF = 15           # seconds, doubled per retry
PP_MAX_RETRIES = 5
PP_MAX_PAGES = 6          # 100 results/page
ARCHIVE_END = 1747612800  # 2025-05-19, the newest data PullPush holds

AU_SUBS = [
    "AusProperty", "AusFinance", "australia", "melbourne",
    "sydney", "brisbane", "AusRenovation", "AusPropertyChat",
]

# Terms distinctive enough to search across all of Reddit (no subreddit filter):
# they are Australian by construction, so global search stays on-topic.
GLOBAL_TERMS = [
    "underquoting",
    "realestate.com.au",
    "domain.com.au",
    "PropTrack",
    "property.com.au",
    "Domain home price guide",
    "REA listing",
]

# Generic phrases that only make sense scoped to an Australian subreddit.
SCOPED_TERMS = [
    "price guide",
    "contact agent",
    "property value estimate",
    "estimate wrong",
    "house valuation online",
    "strata fees listing",
    "body corporate fees",
    "flood risk listing",
    "no price listed",
    "auction price guide",
]


def _ts(rec):
    """PullPush returns created_utc as int on some records and str on others."""
    try:
        return int(float(rec.get("created_utc") or 0))
    except (TypeError, ValueError):
        return 0


def _pp(kind, **params):
    """One PullPush call, with backoff on 429.

    PullPush rate-limits aggressively. Treating a 429 as an empty result silently
    drops evidence — an early run lost the entire 'underquoting' corpus (568
    records) that way and reported success. So 429 must be retried, not swallowed,
    and an exhausted retry budget must be recorded as a failure.
    """
    for attempt in range(PP_MAX_RETRIES):
        try:
            r = requests.get(PULLPUSH.format(kind=kind), params=params, timeout=90)
            if r.status_code == 200:
                return r.json().get("data", []), True
            if r.status_code == 429:
                wait = PP_BACKOFF * (2 ** attempt)
                print(f"    429 — backing off {wait}s "
                      f"(attempt {attempt+1}/{PP_MAX_RETRIES})", file=sys.stderr)
                time.sleep(wait)
                continue
            print(f"    ! HTTP {r.status_code} for {params}", file=sys.stderr)
            return [], False
        except Exception as e:
            print(f"    ! {type(e).__name__}: {e}", file=sys.stderr)
            time.sleep(PP_BACKOFF * (2 ** attempt))
    print(f"    !! GAVE UP after {PP_MAX_RETRIES} attempts: {params}", file=sys.stderr)
    return [], False


def pp_search(kind, q, subreddit=None):
    """Full-text search with backwards pagination via the `before` cursor.

    Returns (records, failed_pages). A non-zero failed_pages means this query is
    under-harvested and the caller must report it rather than assume completeness.
    """
    out, before, failed = [], ARCHIVE_END, 0
    for _ in range(PP_MAX_PAGES):
        params = {"q": q, "size": 100, "before": before, "sort": "desc"}
        if subreddit:
            params["subreddit"] = subreddit
        batch, ok = _pp(kind, **params)
        time.sleep(PP_DELAY)
        if not ok:
            failed += 1
            break
        if not batch:
            break
        out.extend(batch)
        oldest = min(_ts(x) for x in batch)
        if oldest >= before:      # cursor stopped moving — stop rather than loop
            break
        before = oldest
        if len(batch) < 100:
            break
    return out, failed


def slim(rec, kind):
    """Keep only what a quote needs to be verifiable. Full text is preserved."""
    ts = _ts(rec)
    base = {
        "kind": kind,
        "id": rec.get("id"),
        "subreddit": rec.get("subreddit"),
        "author": rec.get("author"),
        "created_utc": ts,
        "date": datetime.fromtimestamp(ts, timezone.utc).strftime("%Y-%m-%d"),
        "score": rec.get("score"),
        "permalink": "https://www.reddit.com" + (rec.get("permalink") or ""),
    }
    if kind == "submission":
        base["title"] = rec.get("title")
        base["text"] = rec.get("selftext") or ""
        base["num_comments"] = rec.get("num_comments")
    else:
        base["text"] = rec.get("body") or ""
        base["link_id"] = rec.get("link_id")
    return base


def harvest_reddit():
    seen, records = set(), []
    incomplete = []

    def add(result, kind, label):
        batch, failed = result
        if failed:
            incomplete.append(label)
        new = 0
        for rec in batch:
            key = (kind, rec.get("id"))
            if key in seen or not rec.get("id"):
                continue
            # [deleted]/[removed] bodies carry no evidentiary value
            body = rec.get("body") or rec.get("selftext") or ""
            if body.strip() in ("[deleted]", "[removed]"):
                continue
            seen.add(key)
            records.append(slim(rec, kind))
            new += 1
        flag = "  [INCOMPLETE]" if failed else ""
        print(f"  {label}: +{new} new (total {len(records)}){flag}")

    print("== Reddit via PullPush (archive ends 2025-05-19) ==")
    for term in GLOBAL_TERMS:
        for kind in ("comment", "submission"):
            add(pp_search(kind, term), kind, f"[all] {kind} q={term!r}")

    for sub in AU_SUBS:
        for term in SCOPED_TERMS:
            for kind in ("comment", "submission"):
                add(pp_search(kind, term, subreddit=sub), kind,
                    f"[r/{sub}] {kind} q={term!r}")

    records.sort(key=lambda r: r["created_utc"], reverse=True)
    dates = [r["date"] for r in records] or ["-"]
    payload = {
        "harvested_at": datetime.now(timezone.utc).isoformat(),
        "method": "api.pullpush.io Reddit archive (submissions + comments)",
        "limitation": ("PullPush holds nothing after 2025-05-19. Reddit content from "
                       "2025-05-19 onward is NOT represented. reddit.com itself is 403 "
                       "from this VM; Bright Data requires KYC for reddit.com; redlib "
                       "mirrors are behind Anubis bot-checks."),
        "terms_global": GLOBAL_TERMS,
        "terms_scoped": SCOPED_TERMS,
        "subreddits_scoped": AU_SUBS,
        "count": len(records),
        "date_range": [min(dates), max(dates)],
        "incomplete_queries": incomplete,
        "records": records,
    }
    path = SOURCES / "reddit_pullpush_raw.json"
    path.write_text(json.dumps(payload, indent=1, ensure_ascii=False))
    print(f"\n-> {len(records)} records, {min(dates)}..{max(dates)} -> {path}")
    if incomplete:
        print(f"!! {len(incomplete)} queries hit the rate limit and are UNDER-HARVESTED:")
        for q in incomplete:
            print(f"     {q}")


# ---------------------------------------------------------------- PropertyChat

def brightdata_fetch(url, tries=3):
    key = os.environ.get("BRIGHTDATA_API_KEY")
    zone = os.environ.get("BRIGHTDATA_ZONE", "web_unlocker2")
    if not key:
        print("  ! BRIGHTDATA_API_KEY not set", file=sys.stderr)
        return None
    for attempt in range(tries):
        try:
            r = requests.post(
                BRIGHTDATA,
                headers={"Authorization": f"Bearer {key}",
                         "Content-Type": "application/json"},
                json={"zone": zone, "url": url, "format": "raw"},
                timeout=180,
            )
            upstream = r.headers.get("x-brd-status-code")
            if r.status_code == 200 and upstream in ("200", None) and len(r.text) > 5000:
                return r.text
            print(f"    retry {attempt+1}: brd={r.status_code} upstream={upstream} "
                  f"len={len(r.text)}", file=sys.stderr)
        except Exception as e:
            print(f"    retry {attempt+1}: {type(e).__name__}: {e}", file=sys.stderr)
        time.sleep(4)
    return None


# XenForo wraps each post in <li id="post-N" ... data-author="X">. Parse per-post
# BLOCKS, not by scanning the whole page: the page also carries a "recent activity"
# sidebar full of <abbr class="DateTime"> elements dated today, and a naive
# whole-page date scan stamps every historical post with the harvest date.
_POSTBLOCK_RE = re.compile(
    r'<li id="post-(\d+)"[^>]*data-author="([^"]*)"[^>]*>(.*?)(?=<li id="post-\d+"|<div class="pageNavLinkGroup)',
    re.S)
_BODY_RE = re.compile(
    r'<blockquote[^>]*class="[^"]*messageText[^"]*"[^>]*>(.*?)</blockquote>', re.S)
# Posts older than ~a week render as a span with a title; recent ones as an abbr.
_SPAN_DATE_RE = re.compile(r'<span class="DateTime"[^>]*title="([^"]*)"')
_ABBR_DATE_RE = re.compile(r'<abbr class="DateTime"[^>]*data-datestring="([^"]*)"')
_TITLE_RE = re.compile(r'<title>(.*?)</title>', re.S)

_MONTHS = {m: i for i, m in enumerate(
    ["Jan", "Feb", "Mar", "Apr", "May", "Jun",
     "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"], 1)}


def norm_date(raw):
    """'23rd Feb, 2007 at 8:55 AM' / '6th Aug, 2026' -> '2007-02-23'. '' if unparseable."""
    if not raw:
        return ""
    m = re.search(r'(\d{1,2})\w{2}\s+(\w{3})\w*,?\s+(\d{4})', raw)
    if not m:
        return ""
    day, mon, year = m.group(1), m.group(2)[:3].title(), m.group(3)
    if mon not in _MONTHS:
        return ""
    return f"{year}-{_MONTHS[mon]:02d}-{int(day):02d}"


def strip_html(fragment):
    f = re.sub(r'<script.*?</script>', ' ', fragment, flags=re.S)
    f = re.sub(r'<br\s*/?>', '\n', f)
    f = re.sub(r'</p>', '\n', f)
    f = re.sub(r'<[^>]+>', '', f)
    f = (f.replace('&quot;', '"').replace('&#039;', "'").replace('&amp;', '&')
          .replace('&lt;', '<').replace('&gt;', '>').replace('&nbsp;', ' ')
          .replace('&uarr;', ''))
    # XenForo renders an inline quote of another member as
    #   "<name> said: ↑ <their words> Click to expand..."
    # inside a div (not a nested blockquote), so tag-stripping leaves the quoted
    # member's words sitting in this post's text. Left in, it attributes one
    # member's words to another — fatal for a quotation-based evidence document.
    f = re.sub(r'\S+\s+said:.*?Click to expand\.\.\.',
               ' [quoting another post] ', f, flags=re.S)
    return re.sub(r'\n{3,}', '\n\n', re.sub(r'[ \t]+', ' ', f)).strip()


def parse_thread(html, url):
    posts = []
    for post_id, author, block in _POSTBLOCK_RE.findall(html):
        body = _BODY_RE.search(block)
        if not body:
            continue
        text = strip_html(body.group(1))
        if len(text) < 25:
            continue
        d = _SPAN_DATE_RE.search(block) or _ABBR_DATE_RE.search(block)
        posts.append({
            "post_id": post_id,
            "author": author,
            "date": norm_date(d.group(1)) if d else "",
            "url": f"{url}#post-{post_id}",
            "text": text,
        })
    title = _TITLE_RE.search(html)
    return {
        "url": url,
        "title": strip_html(title.group(1)) if title else "",
        "post_count": len(posts),
        "posts": posts,
    }


def find_threads(queries):
    """PropertyChat search needs a session; use Google via Bright Data instead."""
    found = {}
    for q in queries:
        url = ("https://www.google.com/search?num=30&q="
               + requests.utils.quote(f"site:propertychat.com.au {q}"))
        html = brightdata_fetch(url)
        if not html:
            print(f"  search failed: {q}")
            continue
        hits = set(re.findall(
            r'https://www\.propertychat\.com\.au/community/threads/[a-z0-9\-\.]+/', html))
        for h in hits:
            found.setdefault(h, q)
        print(f"  search {q!r}: {len(hits)} threads")
        time.sleep(2)
    return found


def harvest_propertychat():
    print("== PropertyChat via Bright Data Web Unlocker ==")
    queries = [
        "PropTrack estimate accuracy",
        "underquoting price guide",
        "realestate.com.au estimate wrong",
        "domain price estimate inaccurate",
        "contact agent no price",
        "portal listing data wrong",
    ]
    threads = find_threads(queries)

    # The thread the earlier session identified by name but could not read.
    threads.setdefault(
        "https://www.propertychat.com.au/community/threads/"
        "accuracy-of-proptrack-data-in-realestate-com-au-valuations-nsw.86228/",
        "known-target")

    print(f"\n  {len(threads)} unique threads to fetch")
    out = []
    for i, (url, via) in enumerate(sorted(threads.items()), 1):
        html = brightdata_fetch(url)
        if not html:
            print(f"  [{i}/{len(threads)}] FAILED {url}")
            continue
        parsed = parse_thread(html, url)
        parsed["found_via"] = via
        out.append(parsed)
        print(f"  [{i}/{len(threads)}] {parsed['post_count']:>3} posts — "
              f"{parsed['title'][:70]}")
        time.sleep(2)

    payload = {
        "harvested_at": datetime.now(timezone.utc).isoformat(),
        "method": ("Bright Data Web Unlocker. propertychat.com.au returns HTTP 403 to a "
                   "direct fetch from this VM and to WebFetch; the Unlocker returns 200."),
        "thread_count": len(out),
        "post_count": sum(t["post_count"] for t in out),
        "threads": out,
    }
    path = SOURCES / "propertychat_raw.json"
    path.write_text(json.dumps(payload, indent=1, ensure_ascii=False))
    print(f"\n-> {len(out)} threads / {payload['post_count']} posts -> {path}")


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--reddit", action="store_true")
    ap.add_argument("--propertychat", action="store_true")
    a = ap.parse_args()
    if not (a.reddit or a.propertychat):
        a.reddit = a.propertychat = True
    if a.reddit:
        harvest_reddit()
    if a.propertychat:
        harvest_propertychat()
