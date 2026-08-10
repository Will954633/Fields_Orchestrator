#!/usr/bin/env python3
"""
telegram_notify.py — Send notifications via the Fields Telegram bot.

Usage:
    python3 scripts/telegram_notify.py "Your message here"
    python3 scripts/telegram_notify.py --market-pulse-reminder
    python3 scripts/telegram_notify.py --check-chat-id
"""

import os
import sys
import argparse
import requests
from datetime import datetime

BOT_TOKEN = os.environ.get("TELEGRAM_BOT_TOKEN", "")
# Will's chat ID — set after first interaction with bot
CHAT_ID = os.environ.get("TELEGRAM_CHAT_ID", "")


class TelegramSendError(Exception):
    """Raised when a Telegram notification could not be sent.

    Deliberately a normal Exception (not SystemExit via sys.exit) so that the
    `except Exception` blocks used by nearly every caller in the fleet actually
    catch it — sys.exit(1) raises SystemExit, a BaseException, which those
    callers were silently NOT catching, turning "the alert failed to send"
    into "the whole calling script crashed uncaught."
    """


def send_message(text: str, chat_id: str = None, parse_mode: str = "Markdown"):
    """Send a message via the Telegram bot. Raises TelegramSendError on failure."""
    cid = chat_id or CHAT_ID
    if not cid:
        print("ERROR: No TELEGRAM_CHAT_ID set. Send a message to @WillFieldsBot first.")
        raise TelegramSendError("missing TELEGRAM_CHAT_ID")
    if not BOT_TOKEN:
        print("ERROR: No TELEGRAM_BOT_TOKEN set.")
        raise TelegramSendError("missing TELEGRAM_BOT_TOKEN")

    url = f"https://api.telegram.org/bot{BOT_TOKEN}/sendMessage"
    payload = {"chat_id": cid, "text": text}
    if parse_mode:
        payload["parse_mode"] = parse_mode
    resp = requests.post(url, json=payload, timeout=10)
    data = resp.json()
    if not data.get("ok") and parse_mode and data.get("error_code") == 400:
        # Markdown entity-parse failures (e.g. URLs containing "_") — retry as plain text
        resp = requests.post(url, json={"chat_id": cid, "text": text}, timeout=10)
        data = resp.json()
    if not data.get("ok"):
        print(f"ERROR: {data}")
        _record_send(cid, text, ok=False, error=str(data)[:300])
        raise TelegramSendError(str(data))
    print(f"Message sent to {cid}")
    _record_send(cid, text, ok=True,
                 message_id=(data.get("result") or {}).get("message_id"))
    return data


DIGEST_COLLECTION = "telegram_digest"


def queue_message(text: str, source: str, heading: str = None):
    """Queue `text` for the next morning digest instead of sending it now.

    Opt-in, never global. Routine status reporting — the nightly health board, the
    Brain 3 refresh line, the ops triage cycle — arrives at 01:00/03:35/07:15 and is
    read in one sitting hours later, so four separate buzzes buy nothing. Anything
    genuinely time-sensitive (a new lead, a hot lead, the whale, a failed backup)
    must keep calling send_message() directly and does.

    Falls back to sending immediately if the queue write fails: a digest entry that
    silently vanishes would be strictly worse than an extra notification.
    """
    try:
        import sys as _sys
        from datetime import timezone
        _sys.path.insert(0, "/home/fields/Fields_Orchestrator")
        from shared.db import get_client
        get_client()["system_monitor"][DIGEST_COLLECTION].insert_one({
            "queued_at": datetime.now(timezone.utc),
            "source": source,
            "heading": heading or source,
            "text": text,
            "sent": False,
        })
        print(f"[digest] queued {len(text)} chars from {source}")
        return True
    except Exception as e:
        print(f"(digest queue failed: {e} — sending immediately instead)")
        try:
            send_message(text, parse_mode="")
        except Exception as e2:
            print(f"(immediate fallback also failed: {e2})")
        return False


def _record_send(chat_id, text, ok, error=None, message_id=None):
    """Audit every outbound message to system_monitor.telegram_sends.

    Autonomous agents report "Telegram sent" in their own cycle docs, and until
    2026-08-05 there was NO way to check that claim from this side: nothing
    recorded outbound messages and ceo_chat_messages stores only INBOUND. An
    agent's most load-bearing output was therefore the one thing it could not be
    held to. This closes that — the claim is now falsifiable.

    Best-effort and never raises: an audit-write failure must not turn a
    delivered message into a crashed caller (same reasoning as TelegramSendError
    being a normal Exception).
    """
    try:
        import sys as _sys
        from datetime import timezone
        _sys.path.insert(0, "/home/fields/Fields_Orchestrator")
        from shared.db import get_client
        doc = {
            "sent_at": datetime.now(timezone.utc),
            "chat_id": str(chat_id),
            "ok": bool(ok),
            "chars": len(text or ""),
            # Full text, not a preview: the point is to be able to confirm WHAT
            # was claimed to have been sent, not merely that something was.
            "text": text,
            # Who sent it — argv[0] is the entry point, so an agent cycle is
            # distinguishable from a cron reminder without extra plumbing.
            "sender": os.path.basename(_sys.argv[0] or "?"),
            "caller_env": os.environ.get("CYCLE_STAMP") or None,
        }
        if message_id is not None:
            doc["message_id"] = message_id
        if error:
            doc["error"] = error
        get_client()["system_monitor"]["telegram_sends"].insert_one(doc)
    except Exception as e:
        print(f"(telegram send-audit failed: {e})")


def market_pulse_reminder():
    """Send the monthly market pulse reminder."""
    month = datetime.now().strftime("%B %Y")

    policy_line = "⚠️ No cached policy research brief found — ask Claude to research it first."
    try:
        import os as _os
        from pymongo import MongoClient as _MC
        conn = _os.environ.get("COSMOS_CONNECTION_STRING")
        if conn:
            _client = _MC(conn)
            _doc = _client["system_monitor"]["policy_research_briefs"].find_one(sort=[("generated_at", -1)])
            _client.close()
            if _doc:
                age_days = (datetime.now(_doc["generated_at"].tzinfo) - _doc["generated_at"]).days
                policy_line = (
                    f"✅ Policy research brief ready ({_doc.get('month_label', '?')}, {age_days}d old) — "
                    f"`python3 scripts/fetch_policy_research.py --show-latest`"
                )
    except Exception:
        pass  # best-effort — never let this block the core reminder

    text = (
        f"📊 *Market Metrics Update — {month}*\n\n"
        f"Time to update the market metrics summaries for this month.\n\n"
        f"Open a Claude Code session and run:\n"
        f"`python3 scripts/manual_market_pulse.py --show-data`\n\n"
        f"This will show you all the current data for each category. "
        f"Then we'll write the summaries together.\n\n"
        f"{policy_line}\n\n"
        f"⏰ If not done by the 3rd, the AI will auto-generate them."
    )
    send_message(text)


def check_chat_id():
    """Check for updates and print chat IDs."""
    url = f"https://api.telegram.org/bot{BOT_TOKEN}/getUpdates"
    resp = requests.get(url, timeout=10)
    data = resp.json()
    if not data.get("ok"):
        print(f"ERROR: {data}")
        return

    results = data.get("result", [])
    if not results:
        print("No messages received yet. Send a message to @WillFieldsBot first.")
        return

    for update in results:
        msg = update.get("message", {})
        chat = msg.get("chat", {})
        print(f"Chat ID: {chat.get('id')} | Name: {chat.get('first_name', '')} {chat.get('last_name', '')} | Username: @{chat.get('username', '')}")
        print(f"  Message: {msg.get('text', '')}")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Send Telegram notifications")
    parser.add_argument("message", nargs="?", help="Message to send")
    parser.add_argument("--market-pulse-reminder", action="store_true", help="Send monthly pulse reminder")
    parser.add_argument("--check-chat-id", action="store_true", help="Check for chat ID from recent messages")
    parser.add_argument("--queue", metavar="SOURCE",
                        help="Queue for the next morning digest instead of sending now")
    args = parser.parse_args()

    try:
        if args.check_chat_id:
            check_chat_id()
        elif args.market_pulse_reminder:
            market_pulse_reminder()
        elif args.message and args.queue:
            queue_message(args.message, source=args.queue)
        elif args.message:
            send_message(args.message)
        else:
            parser.print_help()
    except TelegramSendError as e:
        print(f"FATAL: notification not sent — {e}")
        sys.exit(1)
