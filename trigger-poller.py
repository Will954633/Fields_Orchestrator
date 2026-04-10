#!/usr/bin/env python3
"""
trigger-poller.py
Fields Orchestrator — Manual Trigger Poller

Polls system_monitor.trigger_requests every 30 seconds.
When a pending trigger is found, runs the corresponding process command
from process_commands.yaml and updates the document with the result.

Deployed to VM at: /home/fields/Fields_Orchestrator/trigger-poller.py
Run as a systemd service: fields-trigger-poller.service

Usage:
    python3 trigger-poller.py
    python3 trigger-poller.py --dry-run    # Print what would run without executing
    python3 trigger-poller.py --once       # Process one batch then exit (for testing)
"""

import os
import sys
import time
import signal
import logging
import argparse
import subprocess
import yaml
from datetime import datetime, timezone
from pathlib import Path

# ---------------------------------------------------------------------------
# Setup
# ---------------------------------------------------------------------------

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [trigger-poller] %(levelname)s %(message)s",
    handlers=[
        logging.StreamHandler(sys.stdout),
        logging.FileHandler("/home/fields/Fields_Orchestrator/logs/trigger-poller.log"),
    ],
)
log = logging.getLogger("trigger-poller")

# ---------------------------------------------------------------------------
# Config
# ---------------------------------------------------------------------------

POLL_INTERVAL_SECONDS = 30
MAX_OUTPUT_TAIL_CHARS = 3000  # Store last N chars of stdout/stderr in MongoDB
BASE_DIR = Path("/home/fields/Feilds_Website")

# ---------------------------------------------------------------------------
# MongoDB
# ---------------------------------------------------------------------------

def get_mongo_uri():
    settings_path = Path("/home/fields/Fields_Orchestrator/config/settings.yaml")
    with open(settings_path) as f:
        settings = yaml.safe_load(f)
    return settings["mongodb"]["uri"]


def get_monitor_db():
    from pymongo import MongoClient
    uri = get_mongo_uri()
    client = MongoClient(uri, serverSelectionTimeoutMS=10000, retryWrites=False)
    return client["system_monitor"]


# ---------------------------------------------------------------------------
# Process command lookup
# ---------------------------------------------------------------------------

def load_process_commands():
    config_path = Path("/home/fields/Fields_Orchestrator/config/process_commands.yaml")
    with open(config_path) as f:
        config = yaml.safe_load(f)
    return {str(p["id"]): p for p in config.get("processes", [])}


# ---------------------------------------------------------------------------
# Execute a single trigger
# ---------------------------------------------------------------------------

def run_trigger(trigger_doc, process_map, dry_run=False):
    process_id = str(trigger_doc["process_id"])
    trigger_id = trigger_doc["_id"]

    proc_config = process_map.get(process_id)
    if not proc_config:
        log.error(f"No process config found for process_id={process_id}")
        return {"status": "failed", "error": f"Unknown process_id: {process_id}"}

    command = proc_config["command"]
    working_dir = proc_config.get("working_dir", str(BASE_DIR))
    timeout_seconds = proc_config.get("estimated_duration_minutes", 60) * 60 + 300  # +5min buffer

    # Substitute PIPELINE_ID placeholder with value from trigger note field
    note = trigger_doc.get("note", "")
    if "PIPELINE_ID" in command and note:
        command = command.replace("PIPELINE_ID", note)

    log.info(f"Trigger {trigger_id}: Running process {process_id} — {proc_config['name']}")
    log.info(f"  Command: {command}")
    log.info(f"  Working dir: {working_dir}")

    if dry_run:
        log.info(f"  [DRY RUN] Would execute: {command}")
        return {"status": "completed", "exit_code": 0, "output_tail": "[dry run]"}

    try:
        result = subprocess.run(
            command,
            shell=True,
            cwd=working_dir,
            capture_output=True,
            text=True,
            timeout=timeout_seconds,
            env={**os.environ, "TRIGGERED_BY": "dashboard"},
        )

        combined = ""
        if result.stdout:
            combined += result.stdout
        if result.stderr:
            combined += "\n--- STDERR ---\n" + result.stderr

        output_tail = combined[-MAX_OUTPUT_TAIL_CHARS:] if len(combined) > MAX_OUTPUT_TAIL_CHARS else combined

        if result.returncode == 0:
            log.info(f"Trigger {trigger_id}: Process {process_id} completed successfully (exit 0)")
            return {"status": "completed", "exit_code": 0, "output_tail": output_tail}
        else:
            log.warning(f"Trigger {trigger_id}: Process {process_id} exited with code {result.returncode}")
            return {"status": "failed", "exit_code": result.returncode, "output_tail": output_tail}

    except subprocess.TimeoutExpired:
        log.error(f"Trigger {trigger_id}: Process {process_id} timed out after {timeout_seconds}s")
        return {"status": "failed", "exit_code": None, "output_tail": f"Timed out after {timeout_seconds}s"}
    except Exception as e:
        log.error(f"Trigger {trigger_id}: Unexpected error: {e}")
        return {"status": "failed", "exit_code": None, "output_tail": str(e)}


# ---------------------------------------------------------------------------
# Poll loop
# ---------------------------------------------------------------------------

def publish_approved_posts(db, dry_run=False):
    """Check for approved Facebook posts and publish them."""
    col = db["fb_pending_posts"]
    approved = list(col.find({"status": "approved"}).limit(5))
    if not approved:
        return 0

    log.info(f"Found {len(approved)} approved post(s) to publish")
    if dry_run:
        log.info("DRY RUN — skipping publish")
        return 0

    cmd = [
        "/home/fields/venv/bin/python3",
        "/home/fields/Fields_Orchestrator/scripts/fb-page-post.py",
        "--publish-approved",
    ]
    try:
        result = subprocess.run(
            cmd, capture_output=True, text=True, timeout=60,
            env={**os.environ, "PATH": os.environ.get("PATH", "")},
        )
        log.info(f"publish-approved exit={result.returncode}")
        if result.stdout:
            for line in result.stdout.strip().split("\n"):
                log.info(f"  {line}")
        if result.returncode != 0 and result.stderr:
            log.error(f"  stderr: {result.stderr[-500:]}")
    except Exception as e:
        log.error(f"publish-approved error: {e}")

    return len(approved)


def poll_once(db, process_map, dry_run=False):
    # Check for approved Facebook posts first
    publish_approved_posts(db, dry_run=dry_run)

    col = db["trigger_requests"]

    # Find the oldest pending trigger
    docs = list(col.find({"status": "pending"}).limit(10))
    docs.sort(key=lambda d: d.get("created_at", datetime.min))

    if not docs:
        return 0

    # Process one at a time to avoid overloading the VM
    doc = docs[0]
    trigger_id = doc["_id"]

    # Claim it — mark as running
    result = col.find_one_and_update(
        {"_id": trigger_id, "status": "pending"},
        {"$set": {"status": "running", "started_at": datetime.now(timezone.utc)}},
    )
    if result is None:
        # Already claimed by another poller instance (shouldn't happen, but safe)
        return 0

    outcome = run_trigger(doc, process_map, dry_run=dry_run)

    col.update_one(
        {"_id": trigger_id},
        {"$set": {
            "status": outcome["status"],
            "finished_at": datetime.now(timezone.utc),
            "exit_code": outcome.get("exit_code"),
            "output_tail": outcome.get("output_tail"),
        }},
    )

    log.info(f"Trigger {trigger_id} finished with status={outcome['status']}")
    return 1


def main():
    parser = argparse.ArgumentParser(description="Fields Trigger Poller")
    parser.add_argument("--dry-run", action="store_true", help="Print commands without executing")
    parser.add_argument("--once", action="store_true", help="Process one batch then exit")
    args = parser.parse_args()

    log.info("trigger-poller starting up")
    if args.dry_run:
        log.info("DRY RUN mode — no commands will execute")

    # Graceful shutdown on SIGTERM
    shutdown = [False]
    def handle_sigterm(sig, frame):
        log.info("SIGTERM received, shutting down gracefully")
        shutdown[0] = True
    signal.signal(signal.SIGTERM, handle_sigterm)

    try:
        db = get_monitor_db()
        log.info("Connected to system_monitor database")
    except Exception as e:
        log.error(f"Failed to connect to MongoDB: {e}")
        sys.exit(1)

    try:
        process_map = load_process_commands()
        log.info(f"Loaded {len(process_map)} process configurations")
    except Exception as e:
        log.error(f"Failed to load process_commands.yaml: {e}")
        sys.exit(1)

    log.info(f"Polling every {POLL_INTERVAL_SECONDS}s for trigger requests...")

    while not shutdown[0]:
        try:
            processed = poll_once(db, process_map, dry_run=args.dry_run)
            if processed == 0 and not args.once:
                # Nothing to do — sleep before next poll
                for _ in range(POLL_INTERVAL_SECONDS):
                    if shutdown[0]:
                        break
                    time.sleep(1)
            elif args.once:
                log.info("--once mode: exiting after one poll cycle")
                break
        except Exception as e:
            log.error(f"Poll error: {e}")
            if not args.once:
                time.sleep(POLL_INTERVAL_SECONDS)
            else:
                break

    log.info("trigger-poller stopped")


if __name__ == "__main__":
    main()
