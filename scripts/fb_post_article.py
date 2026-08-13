#!/usr/bin/env python3
"""
Post a published article to the Fields Real Estate Facebook page, organically.

The post copy is composed from the article's OWN hook — custom_excerpt if it has one,
otherwise the first paragraph of its html stripped to text — plus the public article URL.
Nothing is written by this script beyond trimming, so the article's editorial review is the
copy's editorial review. As a backstop the composed text is checked against the CLAUDE.md
Rule 5 editorial rules and the post is REFUSED (not silently sanitised) on a breach.

Usage:
    python3 scripts/fb_post_article.py --list                       # Published articles
    python3 scripts/fb_post_article.py --id <slug|_id> --dry-run    # Compose, print, stop
    python3 scripts/fb_post_article.py --id <slug|_id> --post       # Publish for real

Posting requires --post. Everything else is a dry run.
"""

import os
import re
import sys
import html as htmllib
import argparse
from datetime import datetime, timezone

from dotenv import load_dotenv
from pymongo import MongoClient
from bson import ObjectId

load_dotenv("/home/fields/Fields_Orchestrator/.env")

COSMOS_URI = os.environ["COSMOS_CONNECTION_STRING"]
SITE_BASE = "https://fieldsestate.com.au"
ARTICLE_URL = SITE_BASE + "/articles/{slug}"
MAX_HOOK_CHARS = 500

TAGLINE = "Fields Real Estate: Smarter with data."

# ── Editorial rules (CLAUDE.md Rule 5) ───────────────────────────────────

FORBIDDEN_WORDS = ["stunning", "nestled", "boasting", "rare opportunity", "robust market"]

# No advice — never tell the reader what to do.
ADVICE_PATTERNS = [
    (r"\byou should\b", "tells the reader what to do"),
    (r"\byou need to\b", "tells the reader what to do"),
    (r"\bconsider (?:buying|selling|listing)\b", "advises a course of action"),
    (r"\bnow is (?:a good|the) time\b", "advises timing"),
    (r"\bnow'?s the time\b", "advises timing"),
    (r"\b(?:don'?t|do not) (?:wait|miss|hesitate)\b", "advises a course of action"),
    (r"\bact (?:now|fast)\b", "advises a course of action"),
    (r"\bwe recommend\b", "gives advice"),
    (r"\bthe smart move\b", "gives advice"),
]

# No predictions — report indicators, never forecast.
PREDICTION_PATTERNS = [
    (r"\bprices will\b", "predicts prices"),
    (r"\bwill (?:rise|fall|climb|drop|surge|crash|keep rising|keep falling)\b", "predicts a move"),
    (r"\bis (?:set|poised|expected) to\b", "predicts a move"),
    (r"\bwe expect\b", "predicts"),
    (r"\bforecast(?:s|ing)?\b", "predicts"),
    (r"\bby (?:the end of|next) (?:year|quarter)[^.]{0,40}\bwill\b", "predicts"),
]

# $1.25m / $1.25M shorthand — the house style is $1,250,000.
SHORTHAND_PRICE_RE = re.compile(r"\$\s*\d+(?:\.\d+)?\s*[mMkK]\b")

# A street address in the opening line next to a dollar figure = a single-property valuation
# in a headline. Comparable RANGES are fine; one address + one figure is not.
STREET_RE = re.compile(
    r"\b\d+[A-Za-z]?\s+[A-Z][A-Za-z'-]+(?:\s+[A-Z][A-Za-z'-]+)*\s+"
    r"(?:Street|St|Road|Rd|Avenue|Ave|Drive|Dr|Court|Ct|Crescent|Cres|Place|Pl|"
    r"Parade|Pde|Terrace|Tce|Way|Lane|Close|Boulevard|Blvd|Circuit|Cct)\b"
)
DOLLAR_RE = re.compile(r"\$\s*[\d,]+")

# ...unless the figure is a RECORDED SALE PRICE. CLAUDE.md requires exact transaction prices
# and forbids single VALUATIONS in headlines — an address plus the price it actually sold for
# is a fact, an address plus what we think it is worth is the thing the rule bans.
SOLD_PRICE_RE = re.compile(
    r"\b(?:sold|sells|selling price|sale price|achieved|auctioned|fetched|settled|"
    r"changed hands|traded|went for|result)\b",
    re.IGNORECASE,
)

# Language that makes a figure an ESTIMATE of worth. This always refuses, sold context or not.
VALUATION_RE = re.compile(
    r"\b(?:worth|valued at|valuation|we value|estimate[ds]?|could (?:sell|fetch)|"
    r"should (?:sell|fetch)|price guide)\b",
    re.IGNORECASE,
)

SUBURBS = [
    "Robina", "Burleigh Waters", "Burleigh Heads", "Varsity Lakes", "Mermaid Waters",
    "Miami", "Palm Beach", "Broadbeach", "Surfers Paradise", "Mudgeeraba", "Nerang",
    "Reedy Creek", "Clear Island Waters", "Gold Coast",
]


URL_RE = re.compile(r"https?://\S+")


def check_editorial(text):
    """Return a list of rule breaches in the composed post text. Empty list = clean.

    URLs are excluded from the check — a slug is lowercase and hyphenated by design, so
    checking it would flag every article link as an uncapitalised suburb.
    """
    text = URL_RE.sub(" ", text)
    breaches = []
    lowered = text.lower()

    for word in FORBIDDEN_WORDS:
        if word in lowered:
            breaches.append(f'forbidden word: "{word}"')

    for pattern, why in ADVICE_PATTERNS:
        m = re.search(pattern, text, re.IGNORECASE)
        if m:
            breaches.append(f'no-advice rule: "{m.group(0)}" — {why}')

    for pattern, why in PREDICTION_PATTERNS:
        m = re.search(pattern, text, re.IGNORECASE)
        if m:
            breaches.append(f'no-prediction rule: "{m.group(0)}" — {why}')

    m = SHORTHAND_PRICE_RE.search(text)
    if m:
        breaches.append(
            f'number format: "{m.group(0)}" — use the full figure ($1,250,000), not shorthand'
        )

    # Suburbs must be capitalised.
    for suburb in SUBURBS:
        if re.search(r"\b" + re.escape(suburb.lower()) + r"\b", text):
            breaches.append(f'suburb not capitalised: "{suburb.lower()}" should be "{suburb}"')

    # Single-property valuation in the opening line.
    # Sold context is read from the whole post, not just the headline: "$2,545,000 at 27
    # Warrina Crescent" is a completed transaction the body makes explicit. But any wording
    # that frames the figure as an estimate of worth refuses regardless.
    first_line = text.strip().split("\n", 1)[0]
    sold_context = SOLD_PRICE_RE.search(text) and not VALUATION_RE.search(first_line)
    if (STREET_RE.search(first_line) and DOLLAR_RE.search(first_line)
            and not sold_context):
        breaches.append(
            "single valuation in headline: the opening line pairs a street address with a "
            "dollar figure — use a comparable range instead"
        )

    return breaches


# ── Article loading + composition ────────────────────────────────────────

def get_db():
    client = MongoClient(COSMOS_URI)
    return client, client["system_monitor"]


def find_article(sm, identifier):
    """Look an article up by slug or _id (ObjectId or legacy string id)."""
    coll = sm["content_articles"]
    doc = coll.find_one({"slug": identifier})
    if doc:
        return doc
    if re.fullmatch(r"[0-9a-fA-F]{24}", identifier):
        try:
            doc = coll.find_one({"_id": ObjectId(identifier)})
        except Exception:
            doc = None
        if doc:
            return doc
    return coll.find_one({"_id": identifier})


def html_to_text(fragment):
    """Strip an HTML fragment to plain text."""
    text = re.sub(r"(?is)<(script|style).*?</\1>", " ", fragment or "")
    text = re.sub(r"(?i)<br\s*/?>", "\n", text)
    text = re.sub(r"(?s)<[^>]+>", " ", text)
    text = htmllib.unescape(text)
    return re.sub(r"[ \t]+", " ", text).strip()


def first_paragraph(article_html):
    """First <p> of the article body that is not just the title, as plain text."""
    for match in re.finditer(r"(?is)<p[^>]*>(.*?)</p>", article_html or ""):
        text = html_to_text(match.group(1))
        if len(text) >= 40:
            return text
    return html_to_text(article_html)[:MAX_HOOK_CHARS]


def trim_to_sentence(text, limit=MAX_HOOK_CHARS):
    """Trim to `limit` chars on a sentence boundary where possible."""
    text = text.strip()
    if len(text) <= limit:
        return text
    cut = text[:limit]
    for sep in (". ", "! ", "? "):
        idx = cut.rfind(sep)
        if idx > limit * 0.5:
            return cut[: idx + 1].strip()
    return cut.rsplit(" ", 1)[0].strip() + "..."


def compose_post(article):
    """Compose the Facebook post text from the article's own hook. Returns (text, hook_source)."""
    excerpt = (article.get("custom_excerpt") or "").strip()
    if excerpt:
        hook, source = excerpt, "custom_excerpt"
    else:
        hook, source = first_paragraph(article.get("html", "")), "html first paragraph"

    hook = trim_to_sentence(hook)
    if not hook:
        raise ValueError("article has neither a custom_excerpt nor a usable first paragraph")

    slug = article.get("slug")
    if not slug:
        raise ValueError("article has no slug — cannot build a public URL")

    url = ARTICLE_URL.format(slug=slug)
    title = (article.get("title") or "").strip()

    parts = [p for p in (title, hook, url, TAGLINE) if p]
    return "\n\n".join(parts), source, url


# ── Posting ──────────────────────────────────────────────────────────────

def _load_fb_page_post():
    """Import scripts/fb-page-post.py (hyphenated name) so we reuse its Graph API code."""
    import importlib.util
    path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "fb-page-post.py")
    spec = importlib.util.spec_from_file_location("fb_page_post", path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def log_article_post(sm, article, post_id, message, url, hook_source):
    """Write the fb_page_posts document so post-performance-tracker.py picks it up."""
    doc = {
        "post_id": post_id,
        "message": message[:200],
        "link": url,
        "template_type": "article_promo",
        "content_type": "text",
        "article_id": str(article["_id"]),
        "article_slug": article.get("slug"),
        "article_title": article.get("title"),
        "hook_source": hook_source,
        "posted_at": datetime.now(timezone.utc).isoformat(),
        "source": "fb_post_article.py",
        "finalized": False,
    }
    sm["fb_page_posts"].insert_one(doc)
    return doc


def list_published(sm, limit=25):
    docs = sm["content_articles"].find(
        {"status": "published"}, {"slug": 1, "title": 1, "published_at": 1}
    ).sort("published_at", -1).limit(limit)
    for d in docs:
        print(f"  {str(d.get('published_at', ''))[:10]}  {d.get('slug')}")
        print(f"      {d.get('title')}")


def main():
    ap = argparse.ArgumentParser(description="Post a published article to the Facebook page")
    ap.add_argument("--id", type=str, help="Article slug or _id")
    ap.add_argument("--list", action="store_true", help="List published articles and exit")
    ap.add_argument("--dry-run", action="store_true", help="Compose and print without posting")
    ap.add_argument("--post", action="store_true", help="Actually publish to Facebook")
    args = ap.parse_args()

    client, sm = get_db()
    try:
        if args.list:
            list_published(sm)
            return

        if not args.id:
            ap.print_help()
            sys.exit(1)

        article = find_article(sm, args.id)
        if not article:
            print(f"ERROR: no article found for '{args.id}' (tried slug and _id).")
            sys.exit(1)

        status = article.get("status")
        if status != "published":
            print(f"ERROR: refusing to post '{article.get('slug')}' — status is "
                  f"'{status}', not 'published'. Publish it first.")
            sys.exit(1)

        try:
            message, hook_source, url = compose_post(article)
        except ValueError as e:
            print(f"ERROR: {e}")
            sys.exit(1)

        breaches = check_editorial(message)

        print(f"Article: {article.get('title')}")
        print(f"Slug:    {article.get('slug')}")
        print(f"_id:     {article['_id']}")
        print(f"Hook:    {hook_source}")
        print(f"URL:     {url}")
        print("\n--- Composed post ---\n")
        print(message)
        print(f"\n--- ({len(message)} chars) ---")

        if breaches:
            print("\nREFUSED — the composed copy breaches the editorial rules (CLAUDE.md Rule 5):")
            for b in breaches:
                print(f"  - {b}")
            print("\nFix the article's excerpt/opening, then re-run. Nothing was posted.")
            sys.exit(2)

        print("\nEditorial check: PASS")

        if not args.post:
            print("\n(Dry run — add --post to publish)")
            return

        fb = _load_fb_page_post()
        print("\nPublishing to Facebook page...")
        post_id = fb.post_to_page(message, link=url)
        log_article_post(sm, article, post_id, message, url, hook_source)
        print(f"Published! Post ID: {post_id}")
        print(f"View: https://facebook.com/{post_id}")
        print("Logged to system_monitor.fb_page_posts — the tracker will collect insights.")
    finally:
        client.close()


if __name__ == "__main__":
    main()
