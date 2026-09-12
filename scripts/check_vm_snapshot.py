#!/usr/bin/env python3
"""
VM boot-disk snapshot freshness watch (Rule 7 companion to the GCP schedule).

The `fields-vm-daily-snapshot` resource policy (created 2026-09-12) snapshots the
100GB boot disk daily at 18:00 UTC (04:00 AEST), 14-day retention. GCP runs it
silently and will not alert if it stops (policy detached, quota, billing). This
watcher asserts a READY snapshot of the boot disk exists and is recent, and
heartbeats to system_monitor.job_runs so the Systems Health sheet shows it.

Cron: 40 4 * * * (AEST), i.e. 40 minutes after the scheduled snapshot window opens.
"""

import json
import subprocess
import sys
from datetime import datetime, timezone

sys.path.insert(0, "/home/fields/Fields_Orchestrator")
sys.path.insert(0, "/home/fields/Fields_Orchestrator/scripts")

from shared.env import load_env
from job_status import job_run

DISK = "fields-orchestrator-vm"
MAX_AGE_H = 36  # one missed daily run + slack


def newest_ready_snapshot():
    out = subprocess.run(
        ["gcloud", "compute", "snapshots", "list",
         "--filter", f"sourceDisk~{DISK}$ AND status=READY",
         "--format", "json(name,creationTimestamp,diskSizeGb)"],
        capture_output=True, text=True, timeout=120)
    if out.returncode != 0:
        raise RuntimeError(f"gcloud snapshots list rc={out.returncode}: {out.stderr.strip()[:300]}")
    snaps = json.loads(out.stdout or "[]")
    if not snaps:
        return None, None
    newest = max(snaps, key=lambda s: s["creationTimestamp"])
    created = datetime.fromisoformat(newest["creationTimestamp"])
    return newest, (datetime.now(timezone.utc) - created).total_seconds() / 3600


def main():
    load_env()
    with job_run("vm_snapshot_freshness", cadence_hours=24,
                 title="VM Boot-Disk Snapshot Freshness") as beat:
        newest, age_h = newest_ready_snapshot()
        # Rule 7b: zero snapshots, or an old one, is the failure this exists for —
        # the schedule silently stopping is indistinguishable from working unless
        # we assert on the outcome.
        if newest is None:
            raise RuntimeError(f"no READY snapshot of {DISK} exists — the daily "
                               "snapshot schedule is not producing snapshots")
        beat.metrics = {"age_hours": round(age_h, 1)}
        if age_h > MAX_AGE_H:
            raise RuntimeError(
                f"newest snapshot {newest['name']} is {age_h:.0f}h old "
                f"(max {MAX_AGE_H}h) — the daily schedule has stopped firing")
        beat.detail = f"{newest['name']} ({age_h:.1f}h old)"
    return 0


if __name__ == "__main__":
    sys.exit(main())
