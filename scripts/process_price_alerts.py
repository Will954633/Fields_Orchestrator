#!/usr/bin/env python3
"""
Price Alert Processor
=====================
Runs after track_price_changes.py to notify subscribers about price changes
and listing status updates on properties they're watching.

Flow:
  1. Query recent price_change_events (last 24h by default)
  2. Match against active price_alert_subscriptions
  3. For each match, create a notification record
  4. Send notifications (Telegram to Will for now, email later)

Collections used:
  - system_monitor.price_alert_subscriptions  (read)
  - system_monitor.price_change_events        (read)
  - system_monitor.price_alert_notifications  (write)

Usage:
    python3 scripts/process_price_alerts.py                 # Process last 24h
    python3 scripts/process_price_alerts.py --hours 48      # Custom window
    python3 scripts/process_price_alerts.py --dry-run       # Preview only
    python3 scripts/process_price_alerts.py --stats         # Show subscription stats
    python3 scripts/process_price_alerts.py --subscribe     # Add a subscription
        --email user@example.com --property-id 660a...

Requires:
    source /home/fields/venv/bin/activate
    set -a && source /home/fields/Fields_Orchestrator/.env && set +a
"""

import os
import sys
import json
import argparse
from datetime import datetime, timezone, timedelta
from bson import ObjectId

sys.path.insert(0, '/home/fields/Fields_Orchestrator')

from shared.env import load_env
from shared.db import get_client, get_db
from shared.ru_guard import cosmos_retry

load_env()

DATABASE_NAME = 'Gold_Coast'
SYSTEM_DB = 'system_monitor'

AEST = timezone(timedelta(hours=10))


def get_aest_now():
    return datetime.now(timezone.utc).replace(tzinfo=None) + timedelta(hours=10)


def get_collections(client):
    sm = client[SYSTEM_DB]
    return {
        'subscriptions': sm['price_alert_subscriptions'],
        'notifications': sm['price_alert_notifications'],
        'events': sm['price_change_events'],
    }


# ---------------------------------------------------------------------------
# Subscribe / Unsubscribe
# ---------------------------------------------------------------------------

def subscribe(client, email, property_id, address=None, suburb=None,
              price_text=None, price_numeric=None):
    """Add or reactivate a price alert subscription."""
    colls = get_collections(client)
    pid = ObjectId(property_id) if isinstance(property_id, str) else property_id

    # Look up property details if not provided
    if not address or not suburb:
        gc = client[DATABASE_NAME]
        for coll_name in gc.list_collection_names():
            if coll_name.startswith('system.'):
                continue
            doc = gc[coll_name].find_one({'_id': pid})
            if doc:
                address = address or doc.get('complete_address') or doc.get('address', 'Unknown')
                suburb = suburb or coll_name
                price_text = price_text or doc.get('price', '')
                if not price_numeric:
                    price_numeric = _parse_price_numeric(price_text)
                break

    now = datetime.utcnow()

    def _do_upsert():
        return colls['subscriptions'].update_one(
            {'email': email, 'property_id': pid},
            {
                '$set': {
                    'status': 'active',
                    'updated_at': now,
                },
                '$setOnInsert': {
                    'email': email,
                    'property_id': pid,
                    'address': address or 'Unknown',
                    'suburb': suburb or 'unknown',
                    'price_text_at_subscribe': price_text or '',
                    'price_numeric_at_subscribe': price_numeric,
                    'listing_status_at_subscribe': 'for_sale',
                    'created_at': now,
                    'notification_count': 0,
                    'last_notified_at': None,
                }
            },
            upsert=True
        )

    result = cosmos_retry(_do_upsert, "subscribe_upsert")
    action = 'created' if result.upserted_id else 'reactivated'
    print(f"Subscription {action}: {email} → {address or pid}")
    return action


def unsubscribe(client, email, property_id=None):
    """Deactivate subscription(s)."""
    colls = get_collections(client)
    query = {'email': email}
    if property_id:
        query['property_id'] = ObjectId(property_id) if isinstance(property_id, str) else property_id

    def _do_update():
        return colls['subscriptions'].update_many(
            query,
            {'$set': {'status': 'unsubscribed', 'updated_at': datetime.utcnow()}}
        )

    result = cosmos_retry(_do_update, "unsubscribe")
    print(f"Unsubscribed {result.modified_count} subscription(s) for {email}")
    return result.modified_count


# ---------------------------------------------------------------------------
# Price Alert Processing
# ---------------------------------------------------------------------------

def process_alerts(client, hours=24, dry_run=False):
    """Match recent price events against active subscriptions and create notifications."""
    colls = get_collections(client)
    cutoff = datetime.utcnow() - timedelta(hours=hours)

    # Get active subscriptions
    subs = list(colls['subscriptions'].find({'status': 'active'}))
    if not subs:
        print("No active subscriptions. Nothing to process.")
        return 0

    # Build lookup: property_id → list of subscriptions
    sub_by_pid = {}
    for s in subs:
        pid = s['property_id']
        sub_by_pid.setdefault(pid, []).append(s)

    print(f"Active subscriptions: {len(subs)} across {len(sub_by_pid)} properties")

    # Get recent price change events
    events = list(colls['events'].find({
        'recorded_at': {'$gte': cutoff}
    }))
    print(f"Price change events in last {hours}h: {len(events)}")

    # Also check for listing status changes (sold, withdrawn)
    gc = client[DATABASE_NAME]
    status_changes = _detect_status_changes(gc, sub_by_pid.keys())

    notifications = []

    # Match price events to subscriptions
    for event in events:
        pid = event.get('property_id')
        if pid not in sub_by_pid:
            continue

        for sub in sub_by_pid[pid]:
            notif = {
                'subscription_id': sub['_id'],
                'email': sub['email'],
                'property_id': pid,
                'address': sub.get('address', event.get('address', 'Unknown')),
                'suburb': sub.get('suburb', event.get('suburb', 'unknown')),
                'event_type': 'price_change',
                'old_price_text': event.get('old_price_text'),
                'old_price_numeric': event.get('old_price_numeric'),
                'new_price_text': event.get('new_price_text'),
                'new_price_numeric': event.get('new_price_numeric'),
                'change_pct': event.get('change_pct'),
                'direction': event.get('direction'),
                'created_at': datetime.utcnow(),
                'sent': False,
                'sent_at': None,
            }
            notifications.append(notif)

    # Match status changes to subscriptions
    for change in status_changes:
        pid = change['property_id']
        if pid not in sub_by_pid:
            continue

        for sub in sub_by_pid[pid]:
            notif = {
                'subscription_id': sub['_id'],
                'email': sub['email'],
                'property_id': pid,
                'address': sub.get('address', change.get('address', 'Unknown')),
                'suburb': sub.get('suburb', 'unknown'),
                'event_type': 'status_change',
                'old_status': 'for_sale',
                'new_status': change['new_status'],
                'created_at': datetime.utcnow(),
                'sent': False,
                'sent_at': None,
            }
            notifications.append(notif)

    print(f"Notifications to create: {len(notifications)}")

    if dry_run:
        for n in notifications:
            print(f"  [DRY RUN] {n['email']} → {n['address']}: "
                  f"{n['event_type']} ({n.get('direction', n.get('new_status', '?'))})")
        return len(notifications)

    # Write notifications
    created = 0
    for n in notifications:
        try:
            colls['notifications'].insert_one(n)
            created += 1

            # Update subscription stats
            colls['subscriptions'].update_one(
                {'_id': n['subscription_id']},
                {
                    '$set': {'last_notified_at': datetime.utcnow()},
                    '$inc': {'notification_count': 1}
                }
            )
        except Exception as e:
            print(f"  Error creating notification for {n['email']}: {e}")

    print(f"Notifications created: {created}")

    # Send notifications
    sent = _send_notifications(colls, created_only=True)
    print(f"Notifications sent: {sent}")

    return created


def _detect_status_changes(gc_db, watched_property_ids):
    """Check if any watched properties have changed to sold/withdrawn."""
    changes = []
    pid_list = list(watched_property_ids)
    if not pid_list:
        return changes

    for coll_name in gc_db.list_collection_names():
        if coll_name.startswith('system.') or coll_name in {
            'suburb_median_prices', 'suburb_statistics',
            'change_detection_snapshots', 'address_search_index'
        }:
            continue

        try:
            docs = list(gc_db[coll_name].find(
                {
                    '_id': {'$in': pid_list},
                    'listing_status': {'$in': ['sold', 'withdrawn', 'off_market']}
                },
                {'_id': 1, 'listing_status': 1, 'complete_address': 1, 'address': 1}
            ))
            for doc in docs:
                changes.append({
                    'property_id': doc['_id'],
                    'new_status': doc['listing_status'],
                    'address': doc.get('complete_address') or doc.get('address', 'Unknown'),
                })
        except Exception:
            continue

    return changes


def _send_notifications(colls, created_only=True):
    """Send unsent notifications. Currently via Telegram; email later."""
    query = {'sent': False}
    unsent = list(colls['notifications'].find(query).limit(50))
    if not unsent:
        return 0

    sent_count = 0
    for n in unsent:
        msg = _format_notification_message(n)
        success = _send_telegram(msg)

        if success:
            colls['notifications'].update_one(
                {'_id': n['_id']},
                {'$set': {'sent': True, 'sent_at': datetime.utcnow(), 'channel': 'telegram'}}
            )
            sent_count += 1

    return sent_count


def _format_notification_message(n):
    """Format a human-readable notification message."""
    address = n.get('address', 'Unknown property')
    suburb = (n.get('suburb', '')).replace('_', ' ').title()

    if n['event_type'] == 'price_change':
        direction = n.get('direction', 'change')
        old_p = n.get('old_price_text', '?')
        new_p = n.get('new_price_text', '?')
        pct = n.get('change_pct')
        pct_str = f" ({pct:+.1f}%)" if pct else ""

        emoji = "📉" if direction == "reduction" else "📈"
        return (
            f"{emoji} *Price Alert — {suburb}*\n"
            f"📍 {address}\n"
            f"Price {direction}: {old_p} → {new_p}{pct_str}\n"
            f"_Subscriber: {n['email']}_"
        )
    elif n['event_type'] == 'status_change':
        status = n.get('new_status', 'unknown')
        emoji = "🔴" if status == 'sold' else "⚪"
        return (
            f"{emoji} *Status Alert — {suburb}*\n"
            f"📍 {address}\n"
            f"Listing now: {status.replace('_', ' ').title()}\n"
            f"_Subscriber: {n['email']}_"
        )
    else:
        return f"🔔 Alert for {address}: {n['event_type']}"


def _send_telegram(message):
    """Send a message via Telegram bot."""
    import requests
    token = os.environ.get('TELEGRAM_BOT_TOKEN')
    chat_id = os.environ.get('TELEGRAM_CHAT_ID')
    if not token or not chat_id:
        print("  Telegram not configured (missing TELEGRAM_BOT_TOKEN or TELEGRAM_CHAT_ID)")
        return False

    try:
        resp = requests.post(
            f"https://api.telegram.org/bot{token}/sendMessage",
            json={
                'chat_id': chat_id,
                'text': message,
                'parse_mode': 'Markdown',
                'disable_web_page_preview': True,
            },
            timeout=10
        )
        if resp.status_code == 200:
            return True
        print(f"  Telegram error: {resp.status_code} {resp.text[:200]}")
        return False
    except Exception as e:
        print(f"  Telegram send failed: {e}")
        return False


# ---------------------------------------------------------------------------
# Price parsing (mirrors track_price_changes.py)
# ---------------------------------------------------------------------------

def _parse_price_numeric(price_text):
    """Extract numeric price from text. Returns None if unparseable."""
    if not price_text:
        return None
    text = str(price_text).strip().upper()

    # Skip non-numeric prices
    skip_patterns = ['AUCTION', 'CONTACT', 'EXPRESSION', 'EOI', 'POA',
                     'PRICE ON APPLICATION', 'BY NEGOTIATION', 'SUBMIT ALL OFFERS']
    if any(p in text for p in skip_patterns):
        return None

    # Find all dollar amounts
    amounts = []
    for m in __import__('re').finditer(r'\$?([\d,]+(?:\.\d+)?)\s*[KkMm]?', text):
        raw = m.group(0).replace('$', '').replace(',', '').strip()
        multiplier = 1
        if raw.upper().endswith('M'):
            multiplier = 1_000_000
            raw = raw[:-1]
        elif raw.upper().endswith('K'):
            multiplier = 1_000
            raw = raw[:-1]
        try:
            val = float(raw) * multiplier
            if val > 50_000:  # Plausible property price
                amounts.append(val)
        except ValueError:
            continue

    if not amounts:
        return None
    if len(amounts) == 1:
        return amounts[0]
    # Range — return midpoint
    return (amounts[0] + amounts[-1]) / 2


# ---------------------------------------------------------------------------
# Stats
# ---------------------------------------------------------------------------

def show_stats(client):
    """Print subscription statistics."""
    colls = get_collections(client)

    total = colls['subscriptions'].count_documents({})
    active = colls['subscriptions'].count_documents({'status': 'active'})
    unsub = colls['subscriptions'].count_documents({'status': 'unsubscribed'})

    total_notifs = colls['notifications'].count_documents({})
    sent_notifs = colls['notifications'].count_documents({'sent': True})
    pending_notifs = colls['notifications'].count_documents({'sent': False})

    print(f"=== Price Alert Stats ===")
    print(f"Subscriptions: {total} total ({active} active, {unsub} unsubscribed)")
    print(f"Notifications: {total_notifs} total ({sent_notifs} sent, {pending_notifs} pending)")

    # Recent notifications
    recent = list(colls['notifications'].find().sort('created_at', -1).limit(5))
    if recent:
        print(f"\nRecent notifications:")
        for n in recent:
            print(f"  {n.get('created_at', '?')} | {n.get('email')} | "
                  f"{n.get('address', '?')} | {n.get('event_type')} | "
                  f"sent={n.get('sent')}")


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def main():
    parser = argparse.ArgumentParser(description='Process price alert subscriptions')
    parser.add_argument('--hours', type=int, default=24,
                        help='Look back window in hours (default: 24)')
    parser.add_argument('--dry-run', action='store_true',
                        help='Preview notifications without creating/sending')
    parser.add_argument('--stats', action='store_true',
                        help='Show subscription statistics')
    parser.add_argument('--subscribe', action='store_true',
                        help='Add a new subscription')
    parser.add_argument('--unsubscribe', action='store_true',
                        help='Remove a subscription')
    parser.add_argument('--email', type=str, help='Subscriber email')
    parser.add_argument('--property-id', type=str, help='Property ObjectId')
    parser.add_argument('--send-pending', action='store_true',
                        help='Retry sending unsent notifications')

    args = parser.parse_args()
    client = get_client()

    if args.stats:
        show_stats(client)
        return

    if args.subscribe:
        if not args.email or not args.property_id:
            parser.error("--subscribe requires --email and --property-id")
        subscribe(client, args.email, args.property_id)
        return

    if args.unsubscribe:
        if not args.email:
            parser.error("--unsubscribe requires --email")
        unsubscribe(client, args.email, args.property_id)
        return

    if args.send_pending:
        colls = get_collections(client)
        sent = _send_notifications(colls)
        print(f"Sent {sent} pending notification(s)")
        return

    count = process_alerts(client, hours=args.hours, dry_run=args.dry_run)
    print(f"\nDone. {count} notification(s) processed.")


if __name__ == '__main__':
    main()
