#!/usr/bin/env python3
"""
brain2_util.py — shared helpers for the Brain 2 nightly builders.

Why: the nightly PostHog HogQL queries occasionally get a 504 Gateway Timeout on
the heaviest scans (full attribution scan, AI-referral scan). A single failure
used to kill that builder for the night with no alert, leaving ad_downstream /
organic_journeys silently stale (observed 2026-07-18). These helpers add:
  • hog_retry()   — PostHog query with exponential backoff on 5xx / timeout / URLError
  • alert_failure() — Telegram ping when a builder ultimately fails, so a stale
                      night is visible instead of silent.
"""
import os, json, time, sys, urllib.request, urllib.error

# 3 retries after the first attempt: waits 5s, 15s, 45s (transient 504s clear fast).
_RETRY_WAITS = (5, 15, 45)


def hog_retry(pid, key, sql, timeout=120):
    """POST a HogQL query to PostHog, retrying on transient failures.

    Retries on HTTP 5xx, socket timeout, and URLError (network blips). Re-raises
    immediately on 4xx (auth/query errors — retrying won't help) and re-raises the
    last error if every attempt fails.
    """
    body = json.dumps({"query": {"kind": "HogQLQuery", "query": sql}}).encode()
    url = f"https://us.posthog.com/api/projects/{pid}/query/"
    last = None
    for attempt in range(len(_RETRY_WAITS) + 1):
        try:
            req = urllib.request.Request(
                url, data=body,
                headers={"Authorization": f"Bearer {key}", "Content-Type": "application/json"})
            return json.loads(urllib.request.urlopen(req, timeout=timeout).read())["results"]
        except urllib.error.HTTPError as e:
            last = e
            if e.code < 500:
                raise  # 4xx won't be fixed by retrying
        except (urllib.error.URLError, TimeoutError, ConnectionError) as e:
            last = e
        if attempt < len(_RETRY_WAITS):
            wait = _RETRY_WAITS[attempt]
            print(f"  [hog_retry] {type(last).__name__} "
                  f"{getattr(last, 'code', '')} — retry {attempt + 1}/{len(_RETRY_WAITS)} in {wait}s",
                  file=sys.stderr)
            time.sleep(wait)
    raise last


def alert_failure(builder_name, err):
    """Telegram alert that a Brain 2 nightly builder failed after retries."""
    token = os.environ.get("TELEGRAM_BOT_TOKEN")
    chat = os.environ.get("TELEGRAM_CHAT_ID")
    if not (token and chat):
        return
    text = (f"⚠️ *Brain 2 builder failed*\n_{builder_name}_\n\n"
            f"`{type(err).__name__}: {str(err)[:200]}`\n\n"
            f"Data is stale for tonight — re-run: "
            f"`python3 scripts/brain2/{builder_name}.py`")
    try:
        urllib.request.urlopen(urllib.request.Request(
            f"https://api.telegram.org/bot{token}/sendMessage",
            data=json.dumps({"chat_id": chat, "text": text, "parse_mode": "Markdown"}).encode(),
            headers={"Content-Type": "application/json"}), timeout=20)
    except Exception as e:
        print(f"  [alert_failure] telegram send failed: {e}", file=sys.stderr)
