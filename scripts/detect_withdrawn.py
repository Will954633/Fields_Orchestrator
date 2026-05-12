#!/usr/bin/env python3
"""
Withdrawn Property Detector
============================
Detects properties that have been withdrawn/delisted from Domain.com.au.

Detection method:
  - For each property with listing_status="for_sale", send a HEAD request
    to the listing URL with allow_redirects=False.
  - HTTP 200 = still active on Domain.
  - HTTP 301 redirect to /property-profile/ = listing removed (withdrawn/off-market).
  - HTTP 404 = listing no longer exists (also treat as withdrawn).

Runs after sold detection (steps 103/104) so sold properties are already
flagged and won't be checked here.

Usage:
    python3 scripts/detect_withdrawn.py                          # Target market (3 suburbs)
    python3 scripts/detect_withdrawn.py --all                    # All suburbs
    python3 scripts/detect_withdrawn.py --dry-run                # Preview only
    python3 scripts/detect_withdrawn.py --report                 # Show current withdrawn counts

Requires:
    source /home/fields/venv/bin/activate
    set -a && source /home/fields/Fields_Orchestrator/.env && set +a
"""

import os
import re
import sys
import time
import argparse
from datetime import datetime, timezone, timedelta

REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, REPO_ROOT)

from shared.env import load_env  # type: ignore
from shared.db import get_client, get_db  # type: ignore

load_env()

try:
    from curl_cffi.requests import Session
except ImportError:
    print("ERROR: curl_cffi not installed. Install with: pip install curl_cffi")
    sys.exit(1)

try:
    sys.path.insert(0, '/home/fields/Fields_Orchestrator')
    from shared.monitor_client import MonitorClient
    _MONITOR_AVAILABLE = True
except ImportError:
    _MONITOR_AVAILABLE = False

# Bright Data Web Unlocker (bypasses Akamai on individual listing URLs)
from shared.domain_fetch import fetch_with_status as _domain_fetch_with_status

# Configuration
DATABASE_NAME = 'Gold_Coast'
TARGET_SUBURBS = ["robina", "varsity_lakes", "burleigh_waters"]
REQUEST_DELAY = 1.5          # seconds between requests (be polite to Domain)
REQUEST_TIMEOUT = 15         # seconds per request
MAX_RETRIES = 2              # retry failed requests
RETRY_DELAY = 3              # seconds between retries
COSMOS_RETRY_ATTEMPTS = 3    # DB write retries


def get_aest_now():
    """Get current time in AEST (UTC+10)."""
    return datetime.now(timezone.utc) + timedelta(hours=10)


def retry_db(fn, max_retries=COSMOS_RETRY_ATTEMPTS):
    """Retry a DB operation on Cosmos 429 errors."""
    for attempt in range(max_retries):
        try:
            return fn()
        except Exception as e:
            err = str(e)
            if "16500" in err or "429" in err or "RequestRateTooLarge" in err:
                m = re.search(r'RetryAfterMs=(\d+)', err)
                wait = int(m.group(1)) / 1000.0 if m else (1.0 * (attempt + 1))
                time.sleep(min(wait, 5.0))
                continue
            raise
    return fn()


_TITLE_RE = re.compile(r'<title[^>]*>([^<]+)</title>', re.IGNORECASE)


def check_listing_status(session, listing_url):
    """Check if a listing URL is still active on Domain.

    Routes through Bright Data Web Unlocker (bypasses Akamai).

    Returns:
        "active"    — listing still live on Domain
        "withdrawn" — listing removed (404, /property-profile/ redirect, or "off the market" body)
        "sold"      — Domain still serves the page but title shows "Sold ..." — step 103 should
                       have already caught this; we return "active" here to avoid stomping its work
        "error"     — fetch failed
    """
    result = _domain_fetch_with_status(listing_url, retries=MAX_RETRIES, timeout=REQUEST_TIMEOUT)
    if not result:
        return "error"

    status = result.get('status', 0)
    final_url = result.get('url', '') or ''
    body = result.get('body', '') or ''

    if status == 404:
        return "withdrawn"

    # Domain redirects withdrawn listings to /property-profile/<slug>
    if '/property-profile/' in final_url:
        return "withdrawn"

    if status != 200:
        return "error"

    # Status 200 but title may reflect terminal state. Domain serves the listing page
    # for sold properties with title "Sold <address> on <date> ...".
    title_match = _TITLE_RE.search(body)
    title = title_match.group(1).strip() if title_match else ''
    title_lower = title.lower()

    if title_lower.startswith('sold '):
        # Step 103 owns sold detection — don't touch from here
        return "active"

    # Explicit withdrawn markers in Domain copy
    body_lower = body.lower()
    if 'no longer for sale' in body_lower or 'off the market' in body_lower:
        return "withdrawn"

    return "active"


def run_withdrawn_detection(suburbs, dry_run=False):
    """Main detection loop."""
    client = get_client()
    db = get_db(DATABASE_NAME)
    client.admin.command("ping")
    print(f"  MongoDB connected — {DATABASE_NAME}")

    session = Session(impersonate="chrome120")
    print(f"  curl_cffi session ready (chrome120 impersonation)")

    now_iso = datetime.utcnow().isoformat()
    today_aest = get_aest_now().strftime("%Y-%m-%d")

    totals = {"checked": 0, "withdrawn": 0, "active": 0, "errors": 0, "skipped": 0}

    try:
        for suburb in suburbs:
            collection = db[suburb]

            # Get all for_sale properties with a listing_url
            props = list(retry_db(lambda: list(collection.find(
                {"listing_status": "for_sale", "listing_url": {"$exists": True, "$ne": None}},
                {"address": 1, "listing_url": 1, "listing_status": 1}
            ))))

            print(f"\n--- {suburb} ({len(props)} for_sale properties) ---")

            for prop in props:
                listing_url = prop.get("listing_url", "")
                address = prop.get("address", "unknown")

                if not listing_url or not listing_url.startswith("http"):
                    totals["skipped"] += 1
                    continue

                totals["checked"] += 1
                status = check_listing_status(session, listing_url)

                if status == "withdrawn":
                    totals["withdrawn"] += 1
                    print(f"  WITHDRAWN: {address}")
                    if not dry_run:
                        # Fetch full doc to capture asking price before status change
                        full_doc = retry_db(lambda: collection.find_one({"_id": prop["_id"]}))
                        listing_price = full_doc.get("price") if full_doc else None
                        price_history = full_doc.get("price_history", []) if full_doc else []

                        update_fields = {
                            "listing_status": "withdrawn",
                            "withdrawn_date": today_aest,
                            "withdrawn_detected_at": now_iso,
                            "detection_method": "listing_url_redirect_check",
                            "last_updated": now_iso,
                            "listing_price": listing_price,
                        }

                        # Append final "withdrawn" entry to price_history
                        if listing_price:
                            sys.path.insert(0, '/home/fields/Fields_Orchestrator/scripts')
                            from track_price_changes import parse_price_numeric
                            price_history.append({
                                "price_text": listing_price,
                                "price_numeric": parse_price_numeric(listing_price),
                                "recorded_at": now_iso,
                                "run_id": today_aest,
                                "event": "withdrawn"
                            })
                            update_fields["price_history"] = price_history

                        retry_db(lambda: collection.update_one(
                            {"_id": prop["_id"]},
                            {"$set": update_fields}
                        ))
                elif status == "active":
                    totals["active"] += 1
                else:
                    totals["errors"] += 1
                    print(f"  ERROR: {address} — could not determine status")

                time.sleep(REQUEST_DELAY)

    finally:
        session.close()
        client.close()

    print(f"\n{'='*60}")
    print(f"  RESULTS")
    print(f"  Checked:   {totals['checked']}")
    print(f"  Active:    {totals['active']}")
    print(f"  Withdrawn: {totals['withdrawn']}")
    print(f"  Errors:    {totals['errors']}")
    print(f"  Skipped:   {totals['skipped']} (no listing URL)")
    if dry_run:
        print(f"  (DRY RUN — no DB changes made)")
    print(f"{'='*60}")

    return totals


def show_report():
    """Show current withdrawn property counts across all suburbs."""
    client = get_client()
    db = get_db(DATABASE_NAME)

    print(f"\n{'='*60}")
    print(f"  WITHDRAWN PROPERTIES REPORT")
    print(f"{'='*60}")

    collections = [c for c in db.list_collection_names()
                   if not c.startswith('system.') and c not in (
                       'suburb_median_prices', 'suburb_statistics',
                       'change_detection_snapshots', 'address_search_index')]
    total = 0
    for coll_name in sorted(collections):
        count = db[coll_name].count_documents({"listing_status": "withdrawn"})
        if count > 0:
            print(f"  {coll_name:30s}  {count} withdrawn")
            total += count
        time.sleep(0.3)  # gentle on Cosmos

    print(f"\n  Total withdrawn: {total}")
    print(f"{'='*60}")
    client.close()


def main():
    parser = argparse.ArgumentParser(description="Detect withdrawn/delisted properties")
    parser.add_argument('--all', action='store_true', help='Check all suburbs (not just target market)')
    parser.add_argument('--dry-run', action='store_true', help='Preview only, no DB changes')
    parser.add_argument('--report', action='store_true', help='Show current withdrawn counts')
    parser.add_argument('--suburbs', nargs='+', help='Specific suburb collection names')
    parser.add_argument('--no-fail', action='store_true', help='Exit 0 even on errors')
    args = parser.parse_args()

    if args.report:
        show_report()
        return

    # Monitor client for ops dashboard
    monitor = MonitorClient(
        system="orchestrator", pipeline="orchestrator_daily",
        process_id="113", process_name="Detect Withdrawn Properties"
    ) if _MONITOR_AVAILABLE else None
    if monitor:
        monitor.start()

    if args.suburbs:
        suburbs = args.suburbs
    elif args.all:
        db = get_db(DATABASE_NAME)
        suburbs = [c for c in db.list_collection_names()
                   if not c.startswith('system.') and c not in (
                       'suburb_median_prices', 'suburb_statistics',
                       'change_detection_snapshots', 'address_search_index')]
    else:
        suburbs = TARGET_SUBURBS

    print(f"\nWithdrawn Property Detector")
    print(f"  Suburbs: {len(suburbs)}")
    print(f"  Mode: {'DRY RUN' if args.dry_run else 'LIVE'}")
    print(f"  Time: {get_aest_now().strftime('%Y-%m-%d %H:%M')} AEST")

    try:
        totals = run_withdrawn_detection(suburbs, dry_run=args.dry_run)

        if monitor:
            monitor.finish(status="success")
    except Exception as e:
        print(f"\nFATAL ERROR: {e}")
        if monitor:
            monitor.finish(status="error")
        if not args.no_fail:
            sys.exit(1)


if __name__ == "__main__":
    main()
