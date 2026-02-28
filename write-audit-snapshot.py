#!/usr/bin/env python3
"""
write-audit-snapshot.py
Fields Orchestrator — Daily Audit Log Snapshot Writer

Called by the orchestrator after each daily scrape run (after process 101).
Records a daily count snapshot per suburb to system_monitor.audit_log.
The OpsPage reads these to show count deltas and anomaly detection.

Designed to be idempotent — will not write a second snapshot for today
if one already exists for a suburb.

Usage:
    python3 write-audit-snapshot.py
"""

import sys
import logging
from datetime import datetime, timezone, date
from pathlib import Path
import yaml

logging.basicConfig(level=logging.INFO, format="%(asctime)s [audit-snapshot] %(levelname)s %(message)s")
log = logging.getLogger("audit-snapshot")

TARGET_SUBURBS = [
    "robina", "mudgeeraba", "varsity_lakes", "carrara",
    "reedy_creek", "burleigh_waters", "merrimac", "worongary",
]


def get_mongo_uri():
    settings_path = Path("/home/fields/Fields_Orchestrator/config/settings.yaml")
    with open(settings_path) as f:
        settings = yaml.safe_load(f)
    return settings["mongodb"]["uri"]


def main():
    try:
        from pymongo import MongoClient
        uri = get_mongo_uri()
        client = MongoClient(uri, serverSelectionTimeoutMS=15000, retryWrites=False)
        data_db = client["Gold_Coast_Currently_For_Sale"]
        monitor_db = client["system_monitor"]
        audit_col = monitor_db["audit_log"]
    except Exception as e:
        log.error(f"Failed to connect to MongoDB: {e}")
        sys.exit(1)

    today_str = date.today().isoformat()  # "2026-02-27"
    saved = 0
    skipped = 0

    for suburb in TARGET_SUBURBS:
        try:
            # Check if today's snapshot already exists (idempotent)
            existing = list(audit_col.find({"suburb": suburb, "snapshot_date": today_str}).limit(1))
            if existing:
                log.info(f"{suburb}: snapshot already exists for {today_str}, skipping")
                skipped += 1
                continue

            col = data_db[suburb]
            total = col.count_documents({})

            # Count how many were updated in the last 26h (proxy for "new today")
            cutoff = datetime.now(timezone.utc)
            from datetime import timedelta
            cutoff_26h = cutoff - timedelta(hours=26)
            recently_updated = col.count_documents({"last_updated": {"$gte": cutoff_26h}})

            audit_col.insert_one({
                "suburb": suburb,
                "snapshot_date": today_str,
                "snapshot_at": datetime.now(timezone.utc),
                "total_listings": total,
                "recently_updated": recently_updated,
            })
            saved += 1
            log.info(f"{suburb}: total={total}, recently_updated={recently_updated}")

        except Exception as e:
            log.error(f"Failed for {suburb}: {e}")

    log.info(f"Done. Saved {saved}, skipped {skipped} (already existed).")


if __name__ == "__main__":
    main()
