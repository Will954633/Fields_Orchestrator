#!/usr/bin/env python3
"""
Keep-warm + uptime watchdog for the /for-sale-v3 feed API.

Runs every 5 min (cron). Pings the decision-feed-v3 Netlify function so it never
goes cold (cold starts open a fresh Cosmos connection and can 500 — which would
break the live paid-carousel funnel). Also state-aware alerts Will on Telegram
ONLY on transitions (up→down and down→up), so a sustained outage doesn't spam.

Added 2026-07-27 alongside the Buyer Brief carousel campaign (buyerbrief_carousel_v1).
"""
import json
import os
import sys
import time
from datetime import datetime, timezone

import requests

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from telegram_notify import send_message  # noqa: E402

URL = "https://fieldsestate.com.au/api/v1/properties/decision-feed-v3"
STATE_FILE = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "logs", "keep_warm_forsale_state.json")
TIMEOUT = 25


def ping():
    """Return (ok: bool, detail: str). Two attempts to shrug off a single cold-start miss."""
    last = ""
    for attempt in range(2):
        try:
            r = requests.get(URL, timeout=TIMEOUT)
            if r.status_code == 200 and len(r.content) > 1000:
                return True, f"200 {len(r.content)}b {r.elapsed.total_seconds():.2f}s"
            last = f"HTTP {r.status_code} ({len(r.content)}b)"
        except Exception as e:
            last = f"{type(e).__name__}: {e}"
        if attempt == 0:
            time.sleep(6)
    return False, last


def load_state():
    try:
        return json.load(open(os.path.normpath(STATE_FILE)))
    except Exception:
        return {"status": "ok"}


def save_state(s):
    json.dump(s, open(os.path.normpath(STATE_FILE), "w"))


def main():
    now = datetime.now(timezone.utc).isoformat()
    ok, detail = ping()
    prev = load_state().get("status", "ok")
    cur = "ok" if ok else "down"
    print(f"[{now}] feed-v3 {cur.upper()} — {detail}")

    if cur == "down" and prev == "ok":
        try:
            send_message(f"🔴 /for-sale-v3 feed API DOWN\n{URL}\n{detail}\n(retried once; paid carousel funnel affected)")
        except Exception as e:
            print("telegram alert failed:", e)
    elif cur == "ok" and prev == "down":
        try:
            send_message(f"🟢 /for-sale-v3 feed API RECOVERED — {detail}")
        except Exception as e:
            print("telegram recovery alert failed:", e)

    save_state({"status": cur, "detail": detail, "at": now})


if __name__ == "__main__":
    main()
