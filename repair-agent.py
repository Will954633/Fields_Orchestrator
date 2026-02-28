#!/usr/bin/env python3
"""
repair-agent.py
Fields Orchestrator — Data Coverage Repair Agent

Polls system_monitor.repair_requests every 5 minutes.
When a pending repair is found, determines which enrichment processes
need to run for the given suburb and triggers them sequentially.

Repair requests are written by:
  1. The data-coverage-check.mjs scheduled function (auto, when coverage < threshold)
  2. The OpsPage RepairQueuePanel (manual, dashboard button)

Deployed to VM at: /home/fields/Fields_Orchestrator/repair-agent.py

Usage:
    python3 repair-agent.py
    python3 repair-agent.py --dry-run
    python3 repair-agent.py --once
"""

import os
import sys
import time
import signal
import logging
import argparse
import subprocess
from datetime import datetime, timezone
from pathlib import Path
import yaml

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [repair-agent] %(levelname)s %(message)s",
    handlers=[
        logging.StreamHandler(sys.stdout),
        logging.FileHandler("/home/fields/Fields_Orchestrator/logs/repair-agent.log"),
    ],
)
log = logging.getLogger("repair-agent")

POLL_INTERVAL_SECONDS = 300  # 5 minutes
BASE_DIR = Path("/home/fields/Feilds_Website")

# Map coverage metric → which process IDs to run to fix it
METRIC_TO_PROCESSES = {
    "valuation":    ["6", "18"],
    "floor_plan":   ["106"],
    "photo_tour":   ["105"],
    "transactions": ["12", "13"],
    "insights":     ["14", "15"],
}

# All enrichment processes in dependency order (for "fix all" repair)
FULL_ENRICHMENT_ORDER = ["106", "105", "6", "11", "12", "13", "14", "16", "15", "17", "18"]


def get_mongo_uri():
    settings_path = Path("/home/fields/Fields_Orchestrator/config/settings.yaml")
    with open(settings_path) as f:
        settings = yaml.safe_load(f)
    return settings["mongodb"]["uri"]


def load_process_commands():
    config_path = Path("/home/fields/Fields_Orchestrator/config/process_commands.yaml")
    with open(config_path) as f:
        config = yaml.safe_load(f)
    return {str(p["id"]): p for p in config.get("processes", [])}


def run_process(process_id, proc_config, suburb=None, dry_run=False):
    """Run a single process, optionally scoped to a suburb."""
    command = proc_config["command"]
    working_dir = proc_config.get("working_dir", str(BASE_DIR))
    timeout_s = proc_config.get("estimated_duration_minutes", 60) * 60 + 300

    # Inject suburb env var so scripts can scope their work
    env = {**os.environ}
    if suburb:
        env["TARGET_SUBURB"] = suburb

    log.info(f"  Running process {process_id} — {proc_config['name']}")
    if dry_run:
        log.info(f"  [DRY RUN] {command} (cwd={working_dir})")
        return True

    try:
        result = subprocess.run(
            command, shell=True, cwd=working_dir,
            capture_output=True, text=True, timeout=timeout_s, env=env,
        )
        if result.returncode == 0:
            log.info(f"  Process {process_id} completed (exit 0)")
            return True
        else:
            log.warning(f"  Process {process_id} exited {result.returncode}")
            if result.stderr:
                log.warning(f"  stderr: {result.stderr[-500:]}")
            return False
    except subprocess.TimeoutExpired:
        log.error(f"  Process {process_id} timed out after {timeout_s}s")
        return False
    except Exception as e:
        log.error(f"  Process {process_id} error: {e}")
        return False


def handle_repair(repair_doc, process_map, dry_run=False):
    suburb = repair_doc.get("suburb")
    metric = repair_doc.get("metric")  # specific metric to fix, or None for full repair

    log.info(f"Repair {repair_doc['_id']}: suburb={suburb}, metric={metric}")

    # Determine which processes to run
    if metric and metric in METRIC_TO_PROCESSES:
        process_ids = METRIC_TO_PROCESSES[metric]
        log.info(f"  Targeted repair for metric={metric}: processes {process_ids}")
    else:
        process_ids = FULL_ENRICHMENT_ORDER
        log.info(f"  Full enrichment repair: {process_ids}")

    errors = []
    for pid in process_ids:
        proc_config = process_map.get(pid)
        if not proc_config:
            log.warning(f"  No config for process {pid}, skipping")
            continue
        success = run_process(pid, proc_config, suburb=suburb, dry_run=dry_run)
        if not success:
            errors.append(pid)
            # Don't abort — continue with remaining processes

    status = "completed" if not errors else "failed"
    result_summary = f"Ran processes {process_ids}. Errors in: {errors}" if errors else f"Ran {len(process_ids)} processes successfully."
    return status, result_summary, errors


def poll_once(db, process_map, dry_run=False):
    col = db["repair_requests"]

    docs = list(col.find({"status": "pending"}).limit(5))
    docs.sort(key=lambda d: d.get("created_at", datetime.min))

    if not docs:
        return 0

    doc = docs[0]
    repair_id = doc["_id"]

    # Claim it
    claimed = col.find_one_and_update(
        {"_id": repair_id, "status": "pending"},
        {"$set": {"status": "running", "started_at": datetime.now(timezone.utc)}},
    )
    if claimed is None:
        return 0

    status, result_summary, errors = handle_repair(doc, process_map, dry_run=dry_run)

    col.update_one(
        {"_id": repair_id},
        {"$set": {
            "status": status,
            "finished_at": datetime.now(timezone.utc),
            "result_summary": result_summary,
            "error": ", ".join(f"process {p}" for p in errors) if errors else None,
        }},
    )

    log.info(f"Repair {repair_id}: {status} — {result_summary}")
    return 1


def main():
    parser = argparse.ArgumentParser(description="Fields Repair Agent")
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--once", action="store_true")
    args = parser.parse_args()

    log.info("repair-agent starting up")

    shutdown = [False]
    def handle_sigterm(sig, frame):
        log.info("SIGTERM received, shutting down")
        shutdown[0] = True
    signal.signal(signal.SIGTERM, handle_sigterm)

    try:
        from pymongo import MongoClient
        uri = get_mongo_uri()
        client = MongoClient(uri, serverSelectionTimeoutMS=10000, retryWrites=False)
        db = client["system_monitor"]
        log.info("Connected to MongoDB")
    except Exception as e:
        log.error(f"MongoDB connection failed: {e}")
        sys.exit(1)

    try:
        process_map = load_process_commands()
        log.info(f"Loaded {len(process_map)} processes")
    except Exception as e:
        log.error(f"Failed to load process_commands.yaml: {e}")
        sys.exit(1)

    log.info(f"Polling every {POLL_INTERVAL_SECONDS}s for repair requests...")

    while not shutdown[0]:
        try:
            processed = poll_once(db, process_map, dry_run=args.dry_run)
            if processed == 0 and not args.once:
                for _ in range(POLL_INTERVAL_SECONDS):
                    if shutdown[0]:
                        break
                    time.sleep(1)
            elif args.once:
                log.info("--once: exiting")
                break
        except Exception as e:
            log.error(f"Poll error: {e}")
            if not args.once:
                time.sleep(POLL_INTERVAL_SECONDS)
            else:
                break

    log.info("repair-agent stopped")


if __name__ == "__main__":
    main()
