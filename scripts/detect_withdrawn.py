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
from pymongo import MongoClient

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


def check_listing_status(session, listing_url):
    """Check if a listing URL is still active on Domain.

    Returns:
        "active"    — HTTP 200, listing still live
        "withdrawn" — HTTP 301 to /property-profile/ or HTTP 404
        "error"     — request failed
    """
    for attempt in range(1, MAX_RETRIES + 1):
        try:
            r = session.get(listing_url, timeout=REQUEST_TIMEOUT, allow_redirects=False)

            if r.status_code == 200:
                return "active"
            elif r.status_code == 301:
                location = r.headers.get("Location", "")
                if "/property-profile/" in location:
                    return "withdrawn"
                # 301 to somewhere else — could be URL change, treat as active
                return "active"
            elif r.status_code == 404:
                return "withdrawn"
            elif r.status_code == 429:
                print(f"    Rate limited (429), waiting {RETRY_DELAY * 2}s")
                time.sleep(RETRY_DELAY * 2)
                continue
            else:
                print(f"    Unexpected HTTP {r.status_code} for {listing_url}")
                if attempt < MAX_RETRIES:
                    time.sleep(RETRY_DELAY)
                    continue
                return "error"
        except Exception as e:
            print(f"    Request error: {e}")
            if attempt < MAX_RETRIES:
                time.sleep(RETRY_DELAY)
                continue
            return "error"

    return "error"


def run_withdrawn_detection(suburbs, dry_run=False):
    """Main detection loop."""
    conn_str = os.environ.get("COSMOS_CONNECTION_STRING") or os.environ.get("MONGODB_URI")
    if not conn_str:
        print("ERROR: No COSMOS_CONNECTION_STRING or MONGODB_URI set")
        sys.exit(1)

    client = MongoClient(conn_str)
    db = client[DATABASE_NAME]
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
                        retry_db(lambda: collection.update_one(
                            {"_id": prop["_id"]},
                            {"$set": {
                                "listing_status": "withdrawn",
                                "withdrawn_date": today_aest,
                                "withdrawn_detected_at": now_iso,
                                "detection_method": "listing_url_redirect_check",
                                "last_updated": now_iso,
                            }}
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
    conn_str = os.environ.get("COSMOS_CONNECTION_STRING") or os.environ.get("MONGODB_URI")
    client = MongoClient(conn_str)
    db = client[DATABASE_NAME]

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
        conn_str = os.environ.get("COSMOS_CONNECTION_STRING") or os.environ.get("MONGODB_URI")
        client = MongoClient(conn_str)
        db = client[DATABASE_NAME]
        suburbs = [c for c in db.list_collection_names()
                   if not c.startswith('system.') and c not in (
                       'suburb_median_prices', 'suburb_statistics',
                       'change_detection_snapshots', 'address_search_index')]
        client.close()
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
