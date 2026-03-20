#!/usr/bin/env python3
"""
Price Change & Withdrawal Tracker
===================================
Tracks asking prices on active listings so we can calculate vendor discount
when a property sells. Detects price reductions and increases between runs.

For each active listing:
  1. If no price_history exists, seeds it with the current price (event: "initial")
  2. If the current price differs from the last recorded price, appends a new entry (event: "change")

Also writes summary events to system_monitor.price_change_events for dashboard/reporting.

Usage:
    python3 scripts/track_price_changes.py                  # Target market (3 suburbs)
    python3 scripts/track_price_changes.py --all             # All suburbs
    python3 scripts/track_price_changes.py --report          # Show recent price changes
    python3 scripts/track_price_changes.py --report --days 7 # Last 7 days
    python3 scripts/track_price_changes.py --dry-run         # Preview only
    python3 scripts/track_price_changes.py --no-fail         # Exit 0 on errors

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
    sys.path.insert(0, '/home/fields/Fields_Orchestrator')
    from shared.monitor_client import MonitorClient
    _MONITOR_AVAILABLE = True
except ImportError:
    _MONITOR_AVAILABLE = False

# Configuration
DATABASE_NAME = 'Gold_Coast'
TARGET_SUBURBS = ["robina", "varsity_lakes", "burleigh_waters"]
COSMOS_RETRY_ATTEMPTS = 3
SYSTEM_MONITOR_DB = 'system_monitor'
EXCLUDE_COLLECTIONS = {
    'system.', 'suburb_median_prices', 'suburb_statistics',
    'change_detection_snapshots', 'address_search_index'
}


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


def parse_price_numeric(price_text):
    """Extract a numeric dollar value from Domain's free-text price strings.

    Returns an integer (cents dropped) or None if unparseable.

    Examples:
        "$1,250,000"                    -> 1250000
        "Offers Over $2,395,000"        -> 2395000
        "Offers Above $850,000"         -> 850000
        "From $1,800,000"               -> 1800000
        "$850,000 - $935,000"           -> 892500  (midpoint)
        "$850,000 to $935,000"          -> 892500  (midpoint)
        "Auction"                       -> None
        "Contact Agent"                 -> None
        "Price on Application"          -> None
        "Interest Above $2,000,000"     -> 2000000
        "SOLD - $2,130,000"             -> 2130000
    """
    if not price_text or not isinstance(price_text, str):
        return None

    text = price_text.strip()

    # Skip unparseable formats
    lower = text.lower()
    if any(kw in lower for kw in ['auction', 'contact agent', 'price on application',
                                   'expression of interest', 'eoi', 'by negotiation',
                                   'submit all offers']):
        return None

    # Find all dollar amounts in the string
    amounts = re.findall(r'\$[\d,]+(?:\.\d{2})?', text)
    if not amounts:
        return None

    def parse_one(s):
        s = s.replace('$', '').replace(',', '')
        try:
            return int(float(s))
        except ValueError:
            return None

    parsed = [parse_one(a) for a in amounts]
    parsed = [p for p in parsed if p is not None and p > 10000]  # filter garbage

    if not parsed:
        return None

    if len(parsed) == 1:
        return parsed[0]

    # Range — return midpoint
    if len(parsed) == 2:
        return (parsed[0] + parsed[1]) // 2

    # Multiple amounts — take the first reasonable one
    return parsed[0]


def track_suburb(db, monitor_db, suburb, run_id, dry_run=False):
    """Track price changes for all active listings in a suburb.

    Returns dict with counts: seeded, changed, unchanged, errors.
    """
    collection = db[suburb]
    events_coll = monitor_db['price_change_events']

    now_iso = datetime.utcnow().isoformat()
    now_aest = get_aest_now()

    # Get all active listings
    props = list(retry_db(lambda: list(collection.find(
        {"listing_status": "for_sale"},
        {"address": 1, "price": 1, "price_history": 1, "days_on_domain": 1,
         "first_listed_timestamp": 1, "listing_url": 1}
    ))))

    counts = {"seeded": 0, "changed": 0, "unchanged": 0, "errors": 0}

    for prop in props:
        try:
            current_price = prop.get("price", "")
            history = prop.get("price_history", [])
            address = prop.get("address", "unknown")
            dom = prop.get("days_on_domain")

            if not history:
                # First time — seed with current price
                entry = {
                    "price_text": current_price,
                    "price_numeric": parse_price_numeric(current_price),
                    "recorded_at": now_iso,
                    "run_id": run_id,
                    "event": "initial"
                }
                if not dry_run:
                    retry_db(lambda: collection.update_one(
                        {"_id": prop["_id"]},
                        {"$set": {"price_history": [entry]}}
                    ))
                counts["seeded"] += 1

            elif history[-1].get("price_text") != current_price:
                # Price changed
                old_text = history[-1].get("price_text", "")
                old_numeric = history[-1].get("price_numeric")
                new_numeric = parse_price_numeric(current_price)

                entry = {
                    "price_text": current_price,
                    "price_numeric": new_numeric,
                    "recorded_at": now_iso,
                    "run_id": run_id,
                    "event": "change"
                }

                # Calculate change percentage if both prices are numeric
                change_pct = None
                if old_numeric and new_numeric and old_numeric > 0:
                    change_pct = round((new_numeric - old_numeric) / old_numeric * 100, 2)

                direction = "unknown"
                if change_pct is not None:
                    direction = "reduction" if change_pct < 0 else "increase"

                print(f"  PRICE CHANGE: {address}")
                print(f"    {old_text} -> {current_price}")
                if change_pct is not None:
                    print(f"    {change_pct:+.1f}% ({direction})")

                if not dry_run:
                    # Append to price_history array
                    retry_db(lambda: collection.update_one(
                        {"_id": prop["_id"]},
                        {"$push": {"price_history": entry}}
                    ))

                    # Write event to system_monitor for reporting
                    event_doc = {
                        "date": now_aest.strftime("%Y-%m-%d"),
                        "suburb": suburb,
                        "address": address,
                        "property_id": str(prop["_id"]),
                        "old_price_text": old_text,
                        "old_price_numeric": old_numeric,
                        "new_price_text": current_price,
                        "new_price_numeric": new_numeric,
                        "change_pct": change_pct,
                        "direction": direction,
                        "days_on_market": dom,
                        "event": f"price_{direction}",
                        "recorded_at": now_iso,
                        "run_id": run_id,
                    }
                    retry_db(lambda: events_coll.insert_one(event_doc))

                counts["changed"] += 1
            else:
                counts["unchanged"] += 1

            time.sleep(0.1)  # gentle on Cosmos

        except Exception as e:
            print(f"  ERROR: {prop.get('address', 'unknown')}: {e}")
            counts["errors"] += 1

    return counts


def run_tracking(suburbs, dry_run=False):
    """Main tracking loop across all suburbs."""
    conn_str = os.environ.get("COSMOS_CONNECTION_STRING") or os.environ.get("MONGODB_URI")
    if not conn_str:
        print("ERROR: No COSMOS_CONNECTION_STRING or MONGODB_URI set")
        sys.exit(1)

    client = MongoClient(conn_str)
    db = client[DATABASE_NAME]
    monitor_db = client[SYSTEM_MONITOR_DB]
    client.admin.command("ping")
    print(f"  MongoDB connected — {DATABASE_NAME}")

    now_aest = get_aest_now()
    run_id = now_aest.strftime("%Y-%m-%d_%H-%M")

    totals = {"seeded": 0, "changed": 0, "unchanged": 0, "errors": 0}

    try:
        for suburb in suburbs:
            print(f"\n--- {suburb} ---")
            counts = track_suburb(db, monitor_db, suburb, run_id, dry_run)
            for k in totals:
                totals[k] += counts[k]
            print(f"  Seeded: {counts['seeded']}, Changed: {counts['changed']}, "
                  f"Unchanged: {counts['unchanged']}, Errors: {counts['errors']}")
            time.sleep(0.3)
    finally:
        client.close()

    print(f"\n{'='*60}")
    print(f"  PRICE TRACKING RESULTS")
    print(f"  New listings seeded:  {totals['seeded']}")
    print(f"  Price changes found:  {totals['changed']}")
    print(f"  Unchanged:            {totals['unchanged']}")
    print(f"  Errors:               {totals['errors']}")
    if dry_run:
        print(f"  (DRY RUN — no DB changes made)")
    print(f"{'='*60}")

    return totals


def show_report(days=30):
    """Show recent price change events."""
    conn_str = os.environ.get("COSMOS_CONNECTION_STRING") or os.environ.get("MONGODB_URI")
    client = MongoClient(conn_str)
    monitor_db = client[SYSTEM_MONITOR_DB]

    cutoff = (datetime.utcnow() - timedelta(days=days)).isoformat()

    events = list(monitor_db['price_change_events'].find(
        {"recorded_at": {"$gte": cutoff}},
        {"_id": 0}
    ).sort("recorded_at", -1).limit(50))

    print(f"\n{'='*60}")
    print(f"  PRICE CHANGE EVENTS (last {days} days)")
    print(f"{'='*60}")

    if not events:
        print(f"  No price changes recorded in the last {days} days.")
    else:
        reductions = [e for e in events if e.get("direction") == "reduction"]
        increases = [e for e in events if e.get("direction") == "increase"]
        print(f"  Total events: {len(events)}")
        print(f"  Reductions:   {len(reductions)}")
        print(f"  Increases:    {len(increases)}")

        print(f"\n  Recent changes:")
        for e in events[:20]:
            pct = e.get("change_pct")
            pct_str = f"{pct:+.1f}%" if pct is not None else "N/A"
            dom = e.get("days_on_market", "?")
            print(f"    {e.get('date')} | {e.get('suburb'):20s} | {e.get('address', '?')[:40]:40s} | "
                  f"{pct_str:8s} | DOM: {dom}")

    # Also show listings with price_history in the main DB
    db = client[DATABASE_NAME]
    for suburb in TARGET_SUBURBS:
        with_history = db[suburb].count_documents({"price_history": {"$exists": True, "$ne": []}})
        total_active = db[suburb].count_documents({"listing_status": "for_sale"})
        print(f"\n  {suburb}: {with_history}/{total_active} active listings have price history")

    print(f"{'='*60}")
    client.close()


def main():
    parser = argparse.ArgumentParser(description="Track price changes on active listings")
    parser.add_argument('--all', action='store_true', help='Track all suburbs (not just target market)')
    parser.add_argument('--dry-run', action='store_true', help='Preview only, no DB changes')
    parser.add_argument('--report', action='store_true', help='Show recent price changes')
    parser.add_argument('--days', type=int, default=30, help='Days to look back for report (default: 30)')
    parser.add_argument('--suburbs', nargs='+', help='Specific suburb collection names')
    parser.add_argument('--no-fail', action='store_true', help='Exit 0 even on errors')
    args = parser.parse_args()

    if args.report:
        show_report(args.days)
        return

    # Monitor client for ops dashboard
    monitor = MonitorClient(
        system="orchestrator", pipeline="orchestrator_daily",
        process_id="115", process_name="Track Price Changes"
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
                   if not any(c.startswith(ex) for ex in EXCLUDE_COLLECTIONS)
                   and c not in EXCLUDE_COLLECTIONS]
        client.close()
    else:
        suburbs = TARGET_SUBURBS

    print(f"\nPrice Change Tracker")
    print(f"  Suburbs: {len(suburbs)}")
    print(f"  Mode: {'DRY RUN' if args.dry_run else 'LIVE'}")
    print(f"  Time: {get_aest_now().strftime('%Y-%m-%d %H:%M')} AEST")

    try:
        totals = run_tracking(suburbs, dry_run=args.dry_run)
        if monitor:
            monitor.finish(status="success")
    except Exception as e:
        print(f"\nFATAL ERROR: {e}")
        import traceback
        traceback.print_exc()
        if monitor:
            monitor.finish(status="error")
        if not args.no_fail:
            sys.exit(1)


if __name__ == "__main__":
    main()
