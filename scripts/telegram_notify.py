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

def send_message(text: str, chat_id: str = None, parse_mode: str = "Markdown"):
    """Send a message via the Telegram bot."""
    cid = chat_id or CHAT_ID
    if not cid:
        print("ERROR: No TELEGRAM_CHAT_ID set. Send a message to @WillFieldsBot first.")
        sys.exit(1)
    if not BOT_TOKEN:
        print("ERROR: No TELEGRAM_BOT_TOKEN set.")
        sys.exit(1)

    url = f"https://api.telegram.org/bot{BOT_TOKEN}/sendMessage"
    resp = requests.post(url, json={
        "chat_id": cid,
        "text": text,
        "parse_mode": parse_mode,
    }, timeout=10)
    data = resp.json()
    if not data.get("ok"):
        print(f"ERROR: {data}")
        sys.exit(1)
    print(f"Message sent to {cid}")
    return data


def market_pulse_reminder():
    """Send the monthly market pulse reminder."""
    month = datetime.now().strftime("%B %Y")
    text = (
        f"📊 *Market Metrics Update — {month}*\n\n"
        f"Time to update the market metrics summaries for this month.\n\n"
        f"Open a Claude Code session and run:\n"
        f"`python3 scripts/manual_market_pulse.py --show-data`\n\n"
        f"This will show you all the current data for each category. "
        f"Then we'll write the summaries together.\n\n"
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
    args = parser.parse_args()

    if args.check_chat_id:
        check_chat_id()
    elif args.market_pulse_reminder:
        market_pulse_reminder()
    elif args.message:
        send_message(args.message)
    else:
        parser.print_help()
