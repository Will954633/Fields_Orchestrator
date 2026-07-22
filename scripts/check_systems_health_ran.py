#!/usr/bin/env python3
"""
check_systems_health_ran.py — "who watches the watchmen" for the Fields
Systems Health sheet (scripts/main_site_health_to_sheet.py, 01:00 AEST cron).

That script is the alerting backbone for the entire business — but until
2026-07-22 the only thing checking it had actually run was a self-referential
row inside its OWN output ("this sheet, self-evidently running"), which is a
no-op: if the script crashes before writing anything, that row simply never
gets written either, and nothing says so.

This is a deliberately separate, minimal script:
  - Does NOT import main_site_health_check.py / main_site_health_to_sheet.py /
    minisite_health_check.py — a bug in any of those must not also disable
    the thing checking for that bug.
  - Checks two independent signals: (1) the cron's own log file actually
    shows a successful completion line from within the last ~30h, and
    (2) the Google Sheet itself was actually modified within that window
    (via the Drive API directly, SA auth) — this is the strongest signal,
    since it's proof the write actually landed, not just that the process
    didn't crash before printing something.
  - Alerts directly via telegram_notify on any failure. If BOTH this script
    and telegram_notify.py's own dependencies are broken at once, there is
    no lower backstop — Telegram is this business's single alerting channel
    today (see docstring note in maybe_alert()). That's a known, accepted
    limit, not an oversight.

Usage:
  python3 scripts/check_systems_health_ran.py            # check + alert on failure
  python3 scripts/check_systems_health_ran.py --no-alert  # check + print only
"""
from __future__ import annotations
import argparse
import os
import sys
from datetime import datetime, timedelta, timezone

try:
    from zoneinfo import ZoneInfo
    AEST = ZoneInfo("Australia/Brisbane")
except ImportError:  # pragma: no cover
    AEST = timezone(timedelta(hours=10))

ORCH_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
LOG_PATH = os.path.join(ORCH_DIR, "logs", "main-site-health.log")
KNOWN_SHEET_ID = "1Oa7uZv0shzsxftDYJJ3WErxhr7OZMf_SOxRFawbSgTk"
SA_KEY = "/home/fields/.gcp-floor-plan-vision.json"
EXPECTED_RUN_HOUR_AEST = 1  # 01:00 AEST daily cron
MAX_AGE_HOURS = 30  # generous buffer over the 24h cadence


def check_log():
    """(ok, detail). Log mtime recent + a "Synced" success line near the tail."""
    if not os.path.exists(LOG_PATH):
        return False, f"log file not found: {LOG_PATH}"
    mtime = datetime.fromtimestamp(os.path.getmtime(LOG_PATH), tz=timezone.utc)
    age_h = (datetime.now(timezone.utc) - mtime).total_seconds() / 3600
    if age_h > MAX_AGE_HOURS:
        return False, f"log not updated in {age_h:.1f}h (expected every ~24h)"
    try:
        with open(LOG_PATH, "rb") as f:
            f.seek(max(0, os.path.getsize(LOG_PATH) - 4000), os.SEEK_SET)
            tail = f.read().decode("utf-8", errors="ignore")
    except OSError as e:
        return False, f"could not read log tail: {e}"
    if "Synced" not in tail:
        return False, f"log updated {age_h:.1f}h ago but no 'Synced' success line in tail — likely crashed mid-run"
    return True, f"log fresh ({age_h:.1f}h old), success line present"


def check_sheet_modified():
    """(ok, detail). Drive file's own modifiedTime, independent of any log."""
    try:
        from google.oauth2 import service_account
        from googleapiclient.discovery import build
        creds = service_account.Credentials.from_service_account_file(
            SA_KEY, scopes=["https://www.googleapis.com/auth/drive.readonly"])
        drive = build("drive", "v3", credentials=creds)
        f = drive.files().get(fileId=KNOWN_SHEET_ID, fields="modifiedTime,name").execute()
    except Exception as e:
        return False, f"could not query Drive API: {type(e).__name__}: {e}"
    mtime_s = f.get("modifiedTime")
    if not mtime_s:
        return False, "Drive API returned no modifiedTime"
    mtime = datetime.fromisoformat(mtime_s.replace("Z", "+00:00"))
    age_h = (datetime.now(timezone.utc) - mtime).total_seconds() / 3600
    if age_h > MAX_AGE_HOURS:
        return False, f"sheet '{f.get('name')}' last modified {age_h:.1f}h ago (expected every ~24h)"
    return True, f"sheet last modified {age_h:.1f}h ago"


def set_env_from_file():
    # python-dotenv, not a hand-rolled parser (standardised 2026-07-23).
    from dotenv import load_dotenv
    load_dotenv(os.path.join(ORCH_DIR, ".env"), override=False)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--no-alert", action="store_true")
    args = ap.parse_args()
    set_env_from_file()

    log_ok, log_detail = check_log()
    sheet_ok, sheet_detail = check_sheet_modified()
    now_aest = datetime.now(timezone.utc).astimezone(AEST)

    print(f"[{now_aest:%Y-%m-%d %H:%M AEST}] Fields Systems Health run-check")
    print(f"  log:   {'OK' if log_ok else 'FAIL'} — {log_detail}")
    print(f"  sheet: {'OK' if sheet_ok else 'FAIL'} — {sheet_detail}")

    if log_ok and sheet_ok:
        return

    if args.no_alert:
        print("(would have alerted — --no-alert set)")
        return

    try:
        from telegram_notify import send_message, TelegramSendError
    except Exception as e:
        print(f"FATAL: check failed AND telegram unavailable ({e}) — no alert could be sent")
        sys.exit(1)

    lines = [f"🔴 Fields Systems Health did not run as expected "
             f"({now_aest:%Y-%m-%d %H:%M AEST})"]
    if not log_ok:
        lines.append(f"• Log: {log_detail}")
    if not sheet_ok:
        lines.append(f"• Sheet: {sheet_detail}")
    lines.append("Check logs/main-site-health.log on the VM and run "
                 "main_site_health_to_sheet.py manually.")
    try:
        send_message("\n".join(lines), parse_mode="")
    except TelegramSendError as e:
        print(f"FATAL: alert failed to send: {e}")
        sys.exit(1)


if __name__ == "__main__":
    main()
