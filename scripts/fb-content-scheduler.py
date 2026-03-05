#!/usr/bin/env python3
"""
Facebook Content Scheduler — posts the right content pillar on the right day.

Runs daily via cron. Determines today's content pillar from the weekly calendar,
checks ads performance to adjust template weights, and posts programmatically.
No LLM required for 5 of 7 days.

Weekly Calendar (AEST):
    Mon  → Local photo (fb-photo-manager.py)
    Tue  → Data snapshot (fb-page-post.py, weighted by ads performance)
    Wed  → Article share (skip — handled by marketing-advisor.py)
    Thu  → Seller insight (fb-page-post.py --template seller_insight)
    Fri  → Buyer intelligence (fb-page-post.py --template buyer_intelligence)
    Sat  → Local photo (fb-photo-manager.py, different theme from Mon)
    Sun  → Weekly market wrap (fb-page-post.py --template weekly_wrap)

Usage:
    python3 scripts/fb-content-scheduler.py              # Post today's content
    python3 scripts/fb-content-scheduler.py --dry-run    # Preview without posting
    python3 scripts/fb-content-scheduler.py --day tue     # Force a specific day's pillar
    python3 scripts/fb-content-scheduler.py --status      # Show weekly plan + ads signals
"""

import os
import sys
import json
import subprocess
import argparse
from datetime import datetime, timezone, timedelta
from dotenv import load_dotenv
from pymongo import MongoClient

load_dotenv("/home/fields/Fields_Orchestrator/.env")

COSMOS_URI = os.environ["COSMOS_CONNECTION_STRING"]
VENV_PYTHON = "/home/fields/venv/bin/python3"
SCRIPTS_DIR = "/home/fields/Fields_Orchestrator/scripts"

# Day-of-week → content pillar
# 0=Mon, 1=Tue, 2=Wed, 3=Thu, 4=Fri, 5=Sat, 6=Sun
WEEKLY_CALENDAR = {
    0: "photo",              # Monday — local photography
    1: "data_snapshot",      # Tuesday — weighted by ads performance
    2: "article_share",      # Wednesday — marketing advisor handles this
    3: "seller_insight",     # Thursday — seller-focused data
    4: "buyer_intelligence", # Friday — buyer-focused data
    5: "photo",              # Saturday — local photography
    6: "weekly_wrap",        # Sunday — weekly market summary
}

# Templates for data_snapshot day — weighted by ads feedback
DATA_SNAPSHOT_TEMPLATES = [
    "suburb_snapshot",
    "price_comparison",
    "listing_count",
    "bedroom_breakdown",
]


def get_aest_now():
    """Get current time in AEST (UTC+10)."""
    return datetime.now(timezone.utc) + timedelta(hours=10)


def already_posted_today(pillar):
    """Check if we've already posted this pillar today."""
    client = MongoClient(COSMOS_URI)
    sm = client["system_monitor"]

    today = get_aest_now().strftime("%Y-%m-%d")

    # Check fb_page_posts for today
    recent = list(sm["fb_page_posts"].find({}, {"_id": 0, "posted_at": 1, "template_type": 1}).sort("_id", -1).limit(10))
    for post in recent:
        posted_date = post.get("posted_at", "")[:10]
        if posted_date == today:
            client.close()
            return True

    # For photo posts, check photo_inventory
    if pillar == "photo":
        photos = list(sm["photo_inventory"].find({"posted": True}, {"posted_at": 1}).sort("_id", -1).limit(5))
        for p in photos:
            if p.get("posted_at", "")[:10] == today:
                client.close()
                return True

    client.close()
    return False


def get_ads_performance_weights():
    """Read ads performance data and compute template weights.

    Returns a dict of {template_name: weight} where higher = more likely to be chosen.
    Based on what's working in paid ads → organic should follow the same themes.
    """
    client = MongoClient(COSMOS_URI)
    sm = client["system_monitor"]

    weights = {t: 1.0 for t in DATA_SNAPSHOT_TEMPLATES}  # Default equal weights

    ads_doc = sm["facebook_ads"].find_one({"_id": "latest"})
    if not ads_doc:
        client.close()
        return weights

    ads = ads_doc.get("ads", [])
    active_ads = [a for a in ads if a.get("effective_status") == "ACTIVE"]

    if not active_ads:
        client.close()
        return weights

    # Compute average CTR
    ctrs = [a.get("last_7d", {}).get("ctr", 0) for a in active_ads]
    avg_ctr = sum(ctrs) / len(ctrs) if ctrs else 0

    # Classify each ad by theme based on its content/article
    # High CTR ads → boost similar organic templates
    for ad in active_ads:
        m = ad.get("last_7d", {})
        ctr = m.get("ctr", 0)
        impressions = m.get("impressions", 0)

        if impressions < 100:
            continue  # Not enough data

        name_lower = ad.get("name", "").lower()
        link = ad.get("link_url", "").lower()

        # Map ad themes to organic templates
        # "Is Now Good Time to Buy" → buyer timing → buyer_intelligence
        # "What Does Median Money Buy" → pricing → price_comparison
        # "Interstate Migration" → macro trend → suburb_snapshot
        # "Fastest-Moving Year" → seller speed → seller_insight (but also listing_count)

        if ctr > avg_ctr:
            # This ad outperforms — boost similar organic content
            boost = 1.0 + (ctr - avg_ctr) / max(avg_ctr, 0.1)
            if any(kw in name_lower for kw in ["buy", "buyer", "median", "price"]):
                weights["price_comparison"] *= boost
                weights["bedroom_breakdown"] *= boost
            if any(kw in name_lower for kw in ["sell", "seller", "moving", "fast"]):
                weights["suburb_snapshot"] *= boost
                weights["listing_count"] *= boost
            if any(kw in name_lower for kw in ["migration", "growth", "trend"]):
                weights["suburb_snapshot"] *= boost
        elif ctr < avg_ctr * 0.5 and impressions >= 500:
            # This ad significantly underperforms — reduce similar organic
            dampen = 0.5
            if "photo" in name_lower or "brand" in name_lower:
                pass  # Don't penalise organic for brand ad failures

    # Also factor in post performance verdicts
    verdicts = list(sm["fb_ad_tests"].find(
        {"type": "post_performance"},
        {"_id": 0, "template_type": 1, "verdict": 1}
    ).sort("_id", -1).limit(30))

    verdict_scores = {"strong": 1.5, "moderate": 1.0, "weak": 0.6}
    for v in verdicts:
        tt = v.get("template_type", "")
        score = verdict_scores.get(v.get("verdict", ""), 1.0)
        if tt in weights:
            weights[tt] *= score

    # Normalise so weights sum roughly to len(templates)
    total = sum(weights.values())
    if total > 0:
        factor = len(weights) / total
        weights = {k: v * factor for k, v in weights.items()}

    client.close()
    return weights


def pick_weighted_template(weights):
    """Pick a template using weighted random selection."""
    import random
    templates = list(weights.keys())
    w = [weights[t] for t in templates]
    return random.choices(templates, weights=w, k=1)[0]


def get_top_ad_insight():
    """Extract the best-performing ad's core thesis for organic repurposing.

    Returns a dict with the insight or None if no suitable ad found.
    Only repurposes an ad if it hasn't been repurposed recently.
    """
    client = MongoClient(COSMOS_URI)
    sm = client["system_monitor"]

    ads_doc = sm["facebook_ads"].find_one({"_id": "latest"})
    if not ads_doc:
        client.close()
        return None

    ads = ads_doc.get("ads", [])
    # Find top performer with real engagement
    candidates = [
        a for a in ads
        if a.get("effective_status") == "ACTIVE"
        and a.get("last_7d", {}).get("impressions", 0) >= 300
        and a.get("last_7d", {}).get("ctr", 0) >= 0.4
        and a.get("link_url")
    ]
    if not candidates:
        client.close()
        return None

    candidates.sort(key=lambda a: a["last_7d"]["ctr"], reverse=True)
    top = candidates[0]

    # Check if we've already repurposed this ad's article recently
    link = top.get("link_url", "")
    article_id = ""
    if "/article/" in link:
        article_id = link.split("/article/")[-1].split("?")[0]

    if article_id:
        # Check recent page posts for this article
        recent = list(sm["fb_page_posts"].find({}, {"_id": 0, "link": 1}).sort("_id", -1).limit(20))
        for p in recent:
            if article_id in (p.get("link") or ""):
                client.close()
                return None  # Already shared recently

    # Get article details from index
    article = None
    if article_id:
        article = sm["article_index"].find_one({"_id": article_id})

    client.close()
    return {
        "ad_name": top.get("name", ""),
        "ctr": top["last_7d"]["ctr"],
        "impressions": top["last_7d"]["impressions"],
        "link_clicks": top["last_7d"].get("link_clicks", 0),
        "article_id": article_id,
        "article_title": article.get("title", "") if article else "",
        "article_category": article.get("category", "") if article else "",
        "article_suburbs": article.get("suburbs", []) if article else [],
    }


def post_photo(dry_run=False):
    """Post a local photo via fb-photo-manager.py."""
    cmd = [VENV_PYTHON, f"{SCRIPTS_DIR}/fb-photo-manager.py", "post"]
    if dry_run:
        cmd.append("--dry-run")

    result = subprocess.run(
        cmd, capture_output=True, text=True, timeout=90,
        env={**os.environ, "PATH": os.environ.get("PATH", "")}
    )
    print(result.stdout)
    if result.stderr:
        # Filter CosmosDB warnings
        for line in result.stderr.split("\n"):
            if "UserWarning" not in line and "CosmosDB" not in line and line.strip():
                print(f"  stderr: {line}", file=sys.stderr)
    return result.returncode == 0


def post_data_template(template_name, dry_run=False):
    """Post a specific data template via fb-page-post.py."""
    cmd = [VENV_PYTHON, f"{SCRIPTS_DIR}/fb-page-post.py", "--generate", "--template", template_name]
    if not dry_run:
        cmd.append("--post")

    result = subprocess.run(
        cmd, capture_output=True, text=True, timeout=30,
        env={**os.environ, "PATH": os.environ.get("PATH", "")}
    )
    print(result.stdout)
    if result.returncode != 0 and result.stderr:
        for line in result.stderr.split("\n"):
            if "UserWarning" not in line and "CosmosDB" not in line and line.strip():
                print(f"  stderr: {line}", file=sys.stderr)
    return result.returncode == 0


def show_status():
    """Show the weekly content plan and ads performance signals."""
    now = get_aest_now()
    print(f"\n=== FB Content Scheduler Status ===")
    print(f"Current time: {now.strftime('%A %Y-%m-%d %H:%M')} AEST\n")

    day_names = ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"]
    pillar_labels = {
        "photo": "Local Photo (fb-photo-manager)",
        "data_snapshot": "Data Snapshot (weighted template)",
        "article_share": "Article Share (marketing-advisor)",
        "seller_insight": "Seller Insight (programmatic)",
        "buyer_intelligence": "Buyer Intelligence (programmatic)",
        "weekly_wrap": "Weekly Market Wrap (programmatic)",
    }

    print("Weekly Calendar:")
    for day_idx, pillar in WEEKLY_CALENDAR.items():
        marker = " ←" if day_idx == now.weekday() else ""
        llm = "LLM" if pillar == "article_share" else "caption" if pillar == "photo" else "no LLM"
        print(f"  {day_names[day_idx]:3s}  {pillar_labels[pillar]:45s}  [{llm}]{marker}")

    # Ads performance weights
    print(f"\nData Snapshot Weights (from ads performance):")
    weights = get_ads_performance_weights()
    total_w = sum(weights.values())
    for template, w in sorted(weights.items(), key=lambda x: -x[1]):
        pct = w / total_w * 100 if total_w > 0 else 25
        bar = "█" * int(pct / 5)
        print(f"  {template:20s}  {pct:5.1f}%  {bar}")

    # Top ad insight
    print(f"\nTop Ad Insight (for organic repurposing):")
    insight = get_top_ad_insight()
    if insight:
        print(f"  Ad: {insight['ad_name']}")
        print(f"  CTR: {insight['ctr']:.2f}% ({insight['impressions']} impressions)")
        if insight["article_title"]:
            print(f"  Article: {insight['article_title']}")
            print(f"  Category: {insight['article_category']}")
    else:
        print(f"  No eligible ad for repurposing (need CTR >= 0.4%, 300+ impressions)")

    # Photo inventory
    client = MongoClient(COSMOS_URI)
    sm = client["system_monitor"]
    photo_avail = sm["photo_inventory"].count_documents({"posted": {"$ne": True}})
    photo_total = sm["photo_inventory"].count_documents({})
    posts_today = already_posted_today("any")
    client.close()

    print(f"\nPhoto Inventory: {photo_avail}/{photo_total} available (~{photo_avail} days)")
    print(f"Already posted today: {'Yes' if posts_today else 'No'}")


def log_scheduler_run(pillar, template, success, dry_run):
    """Log this scheduler run to MongoDB."""
    if dry_run:
        return
    client = MongoClient(COSMOS_URI)
    sm = client["system_monitor"]
    sm["fb_scheduler_runs"].update_one(
        {"_id": get_aest_now().strftime("%Y-%m-%d")},
        {"$set": {
            "date": get_aest_now().strftime("%Y-%m-%d"),
            "day_of_week": get_aest_now().strftime("%A"),
            "pillar": pillar,
            "template": template,
            "success": success,
            "run_at": datetime.now(timezone.utc).isoformat(),
        }},
        upsert=True,
    )
    client.close()


def main():
    parser = argparse.ArgumentParser(description="FB Content Scheduler — daily content posting")
    parser.add_argument("--dry-run", action="store_true", help="Preview without posting")
    parser.add_argument("--day", type=str, help="Force a specific day (mon/tue/wed/thu/fri/sat/sun)")
    parser.add_argument("--status", action="store_true", help="Show weekly plan and ads signals")
    args = parser.parse_args()

    if args.status:
        show_status()
        return

    now = get_aest_now()
    day_idx = now.weekday()

    if args.day:
        day_map = {"mon": 0, "tue": 1, "wed": 2, "thu": 3, "fri": 4, "sat": 5, "sun": 6}
        day_idx = day_map.get(args.day.lower()[:3])
        if day_idx is None:
            print(f"ERROR: Unknown day '{args.day}'")
            sys.exit(1)

    pillar = WEEKLY_CALENDAR[day_idx]
    day_name = ["Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday"][day_idx]

    print(f"[{now.strftime('%Y-%m-%d %H:%M')} AEST] Content Scheduler — {day_name}")
    print(f"Pillar: {pillar}")

    if not args.dry_run and already_posted_today(pillar):
        print("Already posted today. Skipping.")
        return

    success = False
    template_used = pillar

    if pillar == "photo":
        print("Posting local photo...")
        success = post_photo(dry_run=args.dry_run)
        template_used = "photo"

    elif pillar == "data_snapshot":
        # Use ads-weighted template selection
        weights = get_ads_performance_weights()
        template = pick_weighted_template(weights)
        print(f"Template selected: {template} (weights: {', '.join(f'{k}={v:.1f}' for k, v in weights.items())})")
        success = post_data_template(template, dry_run=args.dry_run)
        template_used = template

    elif pillar == "article_share":
        print("Wednesday = article share day. This is handled by marketing-advisor.py.")
        print("Run: python3 scripts/marketing-advisor.py")
        print("Skipping automated post.")
        return

    elif pillar == "seller_insight":
        print("Posting seller insight...")
        success = post_data_template("seller_insight", dry_run=args.dry_run)
        template_used = "seller_insight"

    elif pillar == "buyer_intelligence":
        print("Posting buyer intelligence...")
        success = post_data_template("buyer_intelligence", dry_run=args.dry_run)
        template_used = "buyer_intelligence"

    elif pillar == "weekly_wrap":
        print("Posting weekly market wrap...")
        success = post_data_template("weekly_wrap", dry_run=args.dry_run)
        template_used = "weekly_wrap"

    # Log the run
    log_scheduler_run(pillar, template_used, success, args.dry_run)

    if success:
        print(f"\nDone. {pillar} posted successfully.")
    elif not args.dry_run:
        print(f"\nWARNING: {pillar} post may have failed. Check logs.")


if __name__ == "__main__":
    main()
