#!/usr/bin/env python3
"""
fpf_preflight_gmail.py — Thursday-evening pre-flight for Five Property Friday.

The Gmail OAuth token that powers all site email expires every ~7 days because
the fields-estate-ads consent screen is in "Testing" mode (see
gmail_send_token_expiry memory / fix-history [FPF-GMAIL-TOKEN]). If it dies
before the Friday 09:00 AEST FPF batch, every send fails silently.

This runs the night BEFORE (cron: Thu 18:00 AEST) and actively tests the
refresh token. On failure it Telegram-alerts Will so there's a full day to
re-auth before the batch needs it. Success is quiet (no Telegram spam) — it
just prints OK and, best-effort, records a job_runs marker so the Systems
Health "run-check" watchdog can confirm the pre-flight itself is firing.

Exit code: 0 if token alive, 1 if dead/unconfigured (for the log tail).

Usage:
    python3 scripts/fpf_preflight_gmail.py
"""
from __future__ import annotations
import os
import sys
import glob
import json

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from dotenv import load_dotenv

load_dotenv("/home/fields/Fields_Orchestrator/.env")

ORCH_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def token_status():
    """('alive'|'dead'|'unconfigured', detail). Mirrors the live refresh-token
    test in main_site_health_check.py's 'Site email (Gmail OAuth token)' check."""
    tok = os.environ.get("GMAIL_REFRESH_TOKEN", "")
    secret_files = glob.glob(os.path.join(ORCH_DIR, "client_secret_*.json"))
    if not tok or not secret_files:
        return "unconfigured", "GMAIL_REFRESH_TOKEN or client_secret_*.json missing on VM"
    try:
        import requests
        cfg = json.load(open(secret_files[0]))
        c = cfg.get("installed") or cfg.get("web") or {}
        resp = requests.post("https://oauth2.googleapis.com/token", data={
            "client_id": c.get("client_id"), "client_secret": c.get("client_secret"),
            "refresh_token": tok, "grant_type": "refresh_token"}, timeout=20)
        j = resp.json() if resp.content else {}
        if resp.status_code == 200 and j.get("access_token"):
            return "alive", "refresh token mints an access token"
        return "dead", j.get("error", f"http_{resp.status_code}")
    except Exception as e:
        return "dead", f"{type(e).__name__}: {e}"


def main():
    status, detail = token_status()
    print(f"FPF Gmail pre-flight: {status} — {detail}")

    # best-effort self-report (watchdog can confirm the pre-flight ran)
    try:
        from job_status import record_job_result
        record_job_result("fpf_preflight_gmail",
                          "success" if status == "alive" else "error", detail=f"{status}: {detail}")
    except Exception as e:
        print(f"(job_status record failed: {e})")

    if status == "alive":
        return 0

    # Token dead / unconfigured — alert with a full day of runway before Fri 09:00.
    try:
        from telegram_notify import send_message
        send_message(
            "⚠️ *Five Property Friday pre-flight — Gmail token NOT sendable*\n"
            f"Status: *{status}* ({detail}).\n\n"
            "Tomorrow's 09:00 FPF batch (and all site email) will fail unless re-authed today.\n"
            "Re-auth as *rossmax06@gmail.com* per the `gmail_send_token_expiry` memory "
            "(consent URL with `login_hint=rossmax06@gmail.com`), push the new "
            "`GMAIL_REFRESH_TOKEN` to Netlify (site+account) + VM `.env`, trigger a build.")
    except Exception as e:
        print(f"(telegram alert failed: {e})")
    return 1


if __name__ == "__main__":
    sys.exit(main())
