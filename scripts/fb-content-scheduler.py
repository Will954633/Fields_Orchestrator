#!/usr/bin/env python3
"""
Facebook Content Scheduler — 2x/day property-data-first posting.

Posts the right content at the right time, twice daily:
  MORNING (6:30am AEST) — utility/data posts people use during their day
  EVENING (5:00pm AEST) — analysis/insight posts for end-of-day browsing

Weekly Calendar (AEST):
    MORNING:
      Mon  → Sold results (what sold last week)
      Tue  → Entry price watch (cheapest per suburb)
      Wed  → Median showcase (what median money buys)
      Thu  → Open home spotlight (standout property preview)
      Fri  → Weekend preview (3-5 notable open homes)
      Sat  → 6am: Your open home list for today
      Sun  → Local photo (1x/week)

    EVENING:
      Mon  → New to market (freshest listings)
      Tue  → Data snapshot (ads-weighted template)
      Wed  → Price movement (stale + fresh listings)
      Thu  → Buyer intelligence (price bracket comparison)
      Fri  → Open home spotlight (don't miss this weekend)
      Sat  → Seller insight (market competition data)
      Sun  → Sold preview (weekend sales teaser)

Usage:
    python3 scripts/fb-content-scheduler.py --slot morning         # Post morning content
    python3 scripts/fb-content-scheduler.py --slot evening         # Post evening content
    python3 scripts/fb-content-scheduler.py --slot morning --dry-run
    python3 scripts/fb-content-scheduler.py --day fri --slot morning
    python3 scripts/fb-content-scheduler.py --status               # Show full weekly plan
"""

import os
import sys
import subprocess
import argparse
from datetime import datetime, timezone, timedelta
from dotenv import load_dotenv
from pymongo import MongoClient

load_dotenv("/home/fields/Fields_Orchestrator/.env")

COSMOS_URI = os.environ["COSMOS_CONNECTION_STRING"]
VENV_PYTHON = "/home/fields/venv/bin/python3"
SCRIPTS_DIR = "/home/fields/Fields_Orchestrator/scripts"

# Day-of-week → content pillar (0=Mon, 1=Tue ... 6=Sun)
MORNING_CALENDAR = {
    0: "sold_results",        # Monday — what sold last week
    1: "entry_price_watch",   # Tuesday — cheapest per suburb
    2: "median_showcase",     # Wednesday — what median money buys
    3: "open_home_spotlight",  # Thursday — standout property preview
    4: "weekend_preview",     # Friday — 3-5 notable open homes for the weekend
    5: "saturday_open_list",  # Saturday 6am — full open home list
    6: "photo",               # Sunday — weekly local photo (1x/week)
}

EVENING_CALENDAR = {
    0: "new_to_market",       # Monday — freshest listings this week
    1: "data_snapshot",       # Tuesday — ads-weighted template
    2: "price_movement",      # Wednesday — stale listings + fresh arrivals
    3: "buyer_intelligence",  # Thursday — price bracket comparison
    4: "open_home_spotlight",  # Friday — don't miss this weekend
    5: "seller_insight",      # Saturday — seller competition data
    6: "sold_preview",        # Sunday — preview of weekend sales (full results Mon)
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


def already_posted_slot(slot):
    """Check if we've already posted for this slot (morning/evening) today."""
    client = MongoClient(COSMOS_URI)
    sm = client["system_monitor"]
    today = get_aest_now().strftime("%Y-%m-%d")

    run = sm["fb_scheduler_runs"].find_one({"_id": f"{today}_{slot}"})
    client.close()
    return run is not None and run.get("success", False)


def get_ads_performance_weights():
    """Read ads performance data and compute template weights for data_snapshot day.

    Higher weight = more likely to be chosen. Based on what's working in paid ads.
    """
    client = MongoClient(COSMOS_URI)
    sm = client["system_monitor"]

    weights = {t: 1.0 for t in DATA_SNAPSHOT_TEMPLATES}

    ads_doc = sm["facebook_ads"].find_one({"_id": "latest"})
    if not ads_doc:
        client.close()
        return weights

    ads = ads_doc.get("ads", [])
    active_ads = [a for a in ads if a.get("effective_status") == "ACTIVE"]

    if not active_ads:
        client.close()
        return weights

    ctrs = [a.get("last_7d", {}).get("ctr", 0) for a in active_ads]
    avg_ctr = sum(ctrs) / len(ctrs) if ctrs else 0

    for ad in active_ads:
        m = ad.get("last_7d", {})
        ctr = m.get("ctr", 0)
        impressions = m.get("impressions", 0)

        if impressions < 100:
            continue

        name_lower = ad.get("name", "").lower()

        if ctr > avg_ctr:
            boost = 1.0 + (ctr - avg_ctr) / max(avg_ctr, 0.1)
            if any(kw in name_lower for kw in ["buy", "buyer", "median", "price"]):
                weights["price_comparison"] *= boost
                weights["bedroom_breakdown"] *= boost
            if any(kw in name_lower for kw in ["sell", "seller", "moving", "fast"]):
                weights["suburb_snapshot"] *= boost
                weights["listing_count"] *= boost
            if any(kw in name_lower for kw in ["migration", "growth", "trend"]):
                weights["suburb_snapshot"] *= boost

    # Factor in post performance verdicts
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

    # Normalise
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
    """Show the full 2x/day weekly content plan and ads performance signals."""
    now = get_aest_now()
    print(f"\n=== FB Content Scheduler Status ===")
    print(f"Current time: {now.strftime('%A %Y-%m-%d %H:%M')} AEST\n")

    day_names = ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"]

    pillar_labels = {
        "photo": "Local Photo (1x/week)",
        "data_snapshot": "Data Snapshot (ads-weighted)",
        "price_movement": "Price Movement (stale + fresh)",
        "seller_insight": "Seller Insight",
        "buyer_intelligence": "Buyer Intelligence",
        "sold_preview": "Sold Preview (weekend sales)",
        "sold_results": "Sold Results (last week)",
        "entry_price_watch": "Entry Price Watch",
        "median_showcase": "Median Price Showcase",
        "open_home_spotlight": "Open Home Spotlight",
        "weekend_preview": "Weekend Open Home Preview",
        "saturday_open_list": "Saturday Open Home List",
        "new_to_market": "New to Market",
    }

    print("MORNING (6:30am AEST, Saturday 6am):")
    for day_idx, pillar in MORNING_CALENDAR.items():
        marker = " <-" if day_idx == now.weekday() else ""
        label = pillar_labels.get(pillar, pillar)
        llm = "caption" if pillar == "photo" else "no LLM"
        print(f"  {day_names[day_idx]:3s}  {label:40s}  [{llm}]{marker}")

    print(f"\nEVENING (5:00pm AEST):")
    for day_idx, pillar in EVENING_CALENDAR.items():
        marker = " <-" if day_idx == now.weekday() else ""
        label = pillar_labels.get(pillar, pillar)
        llm = "no LLM"
        print(f"  {day_names[day_idx]:3s}  {label:40s}  [{llm}]{marker}")

    # Ads performance weights
    print(f"\nData Snapshot Weights (from ads performance):")
    weights = get_ads_performance_weights()
    total_w = sum(weights.values())
    for template, w in sorted(weights.items(), key=lambda x: -x[1]):
        pct = w / total_w * 100 if total_w > 0 else 25
        bar = "=" * int(pct / 5)
        print(f"  {template:20s}  {pct:5.1f}%  {bar}")

    # Today's posting status
    client = MongoClient(COSMOS_URI)
    sm = client["system_monitor"]
    today = now.strftime("%Y-%m-%d")

    morning_run = sm["fb_scheduler_runs"].find_one({"_id": f"{today}_morning"})
    evening_run = sm["fb_scheduler_runs"].find_one({"_id": f"{today}_evening"})

    print(f"\nToday's Status ({today}):")
    if morning_run:
        print(f"  Morning: {morning_run.get('template', '?')} — {'posted' if morning_run.get('success') else 'FAILED'}")
    else:
        print(f"  Morning: not yet posted")
    if evening_run:
        print(f"  Evening: {evening_run.get('template', '?')} — {'posted' if evening_run.get('success') else 'FAILED'}")
    else:
        print(f"  Evening: not yet posted")

    # Photo inventory
    photo_avail = sm["photo_inventory"].count_documents({"posted": {"$ne": True}})
    photo_total = sm["photo_inventory"].count_documents({})
    client.close()

    print(f"\nPhoto Inventory: {photo_avail}/{photo_total} available (~{photo_avail} weeks at 1x/week)")


def log_scheduler_run(slot, pillar, template, success, dry_run):
    """Log this scheduler run to MongoDB."""
    if dry_run:
        return
    client = MongoClient(COSMOS_URI)
    sm = client["system_monitor"]
    today = get_aest_now().strftime("%Y-%m-%d")
    sm["fb_scheduler_runs"].update_one(
        {"_id": f"{today}_{slot}"},
        {"$set": {
            "date": today,
            "slot": slot,
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
    parser = argparse.ArgumentParser(description="FB Content Scheduler — 2x/day property-data posting")
    parser.add_argument("--slot", type=str, choices=["morning", "evening"], help="Which slot to post (morning/evening)")
    parser.add_argument("--dry-run", action="store_true", help="Preview without posting")
    parser.add_argument("--day", type=str, help="Force a specific day (mon/tue/wed/thu/fri/sat/sun)")
    parser.add_argument("--status", action="store_true", help="Show weekly plan and signals")
    args = parser.parse_args()

    if args.status:
        show_status()
        return

    if not args.slot:
        print("ERROR: --slot morning or --slot evening is required.")
        print("Use --status to see the weekly plan.")
        sys.exit(1)

    now = get_aest_now()
    day_idx = now.weekday()

    if args.day:
        day_map = {"mon": 0, "tue": 1, "wed": 2, "thu": 3, "fri": 4, "sat": 5, "sun": 6}
        day_idx = day_map.get(args.day.lower()[:3])
        if day_idx is None:
            print(f"ERROR: Unknown day '{args.day}'")
            sys.exit(1)

    calendar = MORNING_CALENDAR if args.slot == "morning" else EVENING_CALENDAR
    pillar = calendar[day_idx]
    day_name = ["Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday"][day_idx]

    print(f"[{now.strftime('%Y-%m-%d %H:%M')} AEST] Content Scheduler — {day_name} {args.slot}")
    print(f"Pillar: {pillar}")

    if not args.dry_run and already_posted_slot(args.slot):
        print(f"Already posted {args.slot} slot today. Skipping.")
        return

    success = False
    template_used = pillar

    if pillar == "photo":
        print("Posting weekly local photo...")
        success = post_photo(dry_run=args.dry_run)
        template_used = "photo"

    elif pillar == "data_snapshot":
        # Use ads-weighted template selection
        weights = get_ads_performance_weights()
        template = pick_weighted_template(weights)
        print(f"Template selected: {template} (weights: {', '.join(f'{k}={v:.1f}' for k, v in weights.items())})")
        success = post_data_template(template, dry_run=args.dry_run)
        template_used = template

    elif pillar in (
        "open_home_spotlight", "entry_price_watch", "median_showcase",
        "weekend_preview", "saturday_open_list", "sold_results",
        "new_to_market", "seller_insight", "buyer_intelligence",
        "sold_preview", "price_movement",
        "suburb_snapshot", "listing_count", "bedroom_breakdown",
    ):
        print(f"Posting {pillar}...")
        success = post_data_template(pillar, dry_run=args.dry_run)
        template_used = pillar

    else:
        print(f"ERROR: Unknown pillar '{pillar}'")
        sys.exit(1)

    # Log the run
    log_scheduler_run(args.slot, pillar, template_used, success, args.dry_run)

    if success:
        print(f"\nDone. {args.slot} post ({pillar}) posted successfully.")
    elif not args.dry_run:
        print(f"\nWARNING: {args.slot} post ({pillar}) may have failed. Check logs.")


if __name__ == "__main__":
    main()
