#!/usr/bin/env python3
"""
Fields Estate — Appraisal Pipeline Poller

Polls system_monitor.appraisal_pipeline every 60 seconds.
Handles timed transitions:
  - analyst_sent + 2 hours → send final report email, advance to report_delivered

Also generates the "analyst started" notification email (called by the ops
dashboard API, not by this poller — the poller only handles the delayed send).

Deployed as: fields-appraisal-poller.service
"""

import os
import sys
import json
import time
import signal
import logging
import subprocess
from datetime import datetime, timezone, timedelta
from pathlib import Path

from pymongo import MongoClient
import requests as http_requests

# ---------------------------------------------------------------------------
# Config
# ---------------------------------------------------------------------------
POLL_INTERVAL = 60  # seconds
DELIVERY_DELAY_HOURS = 2
BASE_DIR = Path("/home/fields/Fields_Orchestrator")
AEST = timezone(timedelta(hours=10))

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    handlers=[
        logging.StreamHandler(),
        logging.FileHandler(str(BASE_DIR / "logs" / "appraisal-poller.log")),
    ],
)
log = logging.getLogger("appraisal-poller")

_running = True


def handle_signal(sig, frame):
    global _running
    log.info(f"Received signal {sig}, shutting down...")
    _running = False


signal.signal(signal.SIGTERM, handle_signal)
signal.signal(signal.SIGINT, handle_signal)

# ---------------------------------------------------------------------------
# Database
# ---------------------------------------------------------------------------
_client = None


def get_db():
    global _client
    if _client is None:
        conn = os.environ.get("COSMOS_CONNECTION_STRING", "")
        if not conn:
            env_path = BASE_DIR / ".env"
            if env_path.exists():
                for line in env_path.read_text().splitlines():
                    if line.startswith("COSMOS_CONNECTION_STRING="):
                        conn = line.split("=", 1)[1].strip().strip('"').strip("'")
                        break
        _client = MongoClient(conn)
    return _client["system_monitor"]


# ---------------------------------------------------------------------------
# Telegram
# ---------------------------------------------------------------------------
def notify_telegram(message):
    token = os.environ.get("TELEGRAM_BOT_TOKEN", "")
    chat_id = os.environ.get("TELEGRAM_CHAT_ID", "")
    if not token or not chat_id:
        env_path = BASE_DIR / ".env"
        if env_path.exists():
            for line in env_path.read_text().splitlines():
                if line.startswith("TELEGRAM_BOT_TOKEN=") and not token:
                    token = line.split("=", 1)[1].strip().strip('"')
                if line.startswith("TELEGRAM_CHAT_ID=") and not chat_id:
                    chat_id = line.split("=", 1)[1].strip().strip('"')
    if not token or not chat_id:
        return
    try:
        http_requests.post(
            f"https://api.telegram.org/bot{token}/sendMessage",
            json={"chat_id": chat_id, "text": message, "parse_mode": "Markdown"},
            timeout=10,
        )
    except Exception as e:
        log.error(f"Telegram error: {e}")


# ---------------------------------------------------------------------------
# Send final report email
# ---------------------------------------------------------------------------
def send_final_report(pipeline_doc):
    """Create tracking record and send the final report email with analyst's custom body."""
    db = get_db()
    doc = pipeline_doc

    report_path = doc.get("report_path")
    if not report_path or not Path(report_path).exists():
        log.error(f"Report not found: {report_path}")
        return False

    email = doc["email"]
    name = doc["name"]
    address = doc["address"]
    custom_body = doc.get("analyst_email_body") or ""

    # Import send_report functions
    sys.path.insert(0, str(BASE_DIR / "tracking-server"))
    from send_report import (
        create_tracking_record,
        generate_email_html,
        send_via_graph,
        count_pdf_pages,
    )

    subject = f"Your Property Appraisal \u2014 {address}"
    total_pages = count_pdf_pages(report_path)

    log.info(f"Sending report to {name} <{email}> — {address} ({total_pages} pages)")

    # Create tracking record
    tracking_id = create_tracking_record(
        db, email, name, address, report_path, subject, total_pages
    )

    # Generate email HTML with analyst's custom body
    email_html = generate_email_html(
        tracking_id, name, address, subject, custom_body=custom_body
    )

    # Save email HTML
    output_dir = BASE_DIR / "output" / "tracked_emails"
    output_dir.mkdir(parents=True, exist_ok=True)
    html_path = output_dir / f"{tracking_id}.html"
    html_path.write_text(email_html)

    # Send via Microsoft Graph
    ok, output = send_via_graph(email, subject, email_html)
    if ok:
        # Update tracking record with sent_at
        db["email_tracking"].update_one(
            {"tracking_id": tracking_id},
            {"$set": {"sent_at": datetime.now(timezone.utc)}},
        )
        log.info(f"Report email sent to {email}, tracking_id={tracking_id}")
        return tracking_id
    else:
        log.error(f"Send failed: {output}")
        return False


# ---------------------------------------------------------------------------
# CRM sync
# ---------------------------------------------------------------------------
def update_crm(email, stage, tracking_id=None):
    try:
        db = get_db()
        now = datetime.now(timezone.utc)
        update = {
            "$set": {
                "appraisal_stage": stage,
                "updated_at": now,
                "last_seen": now.astimezone(AEST).strftime("%Y-%m-%d"),
            },
        }
        if tracking_id:
            update["$addToSet"] = {"tracking_ids": tracking_id}
            update["$push"] = {
                "communications": {
                    "type": "report_sent",
                    "date": now.astimezone(AEST).isoformat(),
                    "tracking_id": tracking_id,
                }
            }
        db["crm_contacts"].update_one({"email": email}, update)
    except Exception as e:
        log.error(f"CRM update error: {e}")


# ---------------------------------------------------------------------------
# Advance pipeline stage
# ---------------------------------------------------------------------------
def advance_stage(pipeline_id, new_stage, extra_set=None):
    db = get_db()
    now = datetime.now(timezone.utc)
    update = {
        "$set": {"stage": new_stage, "updated_at": now},
        "$push": {"stage_history": {"stage": new_stage, "at": now.isoformat()}},
    }
    if extra_set:
        update["$set"].update(extra_set)
    db["appraisal_pipeline"].update_one({"_id": pipeline_id}, update)
    log.info(f"Pipeline {pipeline_id} → {new_stage}")


# ---------------------------------------------------------------------------
# Poll loop
# ---------------------------------------------------------------------------
def poll_once():
    """Check for pipeline docs that need timed action."""
    db = get_db()
    now = datetime.now(timezone.utc)
    cutoff = now - timedelta(hours=DELIVERY_DELAY_HOURS)

    # Find docs in analyst_sent stage where 2+ hours have elapsed
    docs = list(db["appraisal_pipeline"].find({
        "stage": "analyst_sent",
        "analyst_sent_at": {"$lte": cutoff},
    }))

    for doc in docs:
        pipeline_id = doc["_id"]
        name = doc.get("name", "?")
        address = doc.get("address", "?")
        log.info(f"Delivering report: {name} — {address}")

        try:
            tracking_id = send_final_report(doc)
            if tracking_id:
                advance_stage(pipeline_id, "report_delivered", {"tracking_id": tracking_id})
                update_crm(doc["email"], "report_delivered", tracking_id)
                aest_now = now.astimezone(AEST).strftime("%H:%M AEST")
                notify_telegram(
                    f"*Report delivered* to {name}\n{address}\n{aest_now}\n"
                    f"Track: https://vm.fieldsestate.com.au/track/status/{tracking_id}"
                )
            else:
                log.error(f"Failed to send report for {name}")
        except Exception as e:
            log.error(f"Delivery error for {name}: {e}")


def main():
    log.info("Appraisal poller starting...")
    log.info(f"Poll interval: {POLL_INTERVAL}s, delivery delay: {DELIVERY_DELAY_HOURS}h")

    while _running:
        try:
            poll_once()
        except Exception as e:
            log.error(f"Poll error: {e}")

        # Sleep in small increments so we respond to signals
        for _ in range(POLL_INTERVAL):
            if not _running:
                break
            time.sleep(1)

    log.info("Appraisal poller stopped.")


if __name__ == "__main__":
    main()
