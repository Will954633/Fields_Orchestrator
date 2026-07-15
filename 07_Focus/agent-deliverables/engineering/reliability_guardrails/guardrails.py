#!/usr/bin/env python3
"""Machine-checkable guardrails for exported ops snapshots."""

from __future__ import annotations

import argparse
import json
import re
from collections import Counter
from dataclasses import dataclass
from datetime import datetime, time, timedelta, timezone
from pathlib import Path
from typing import Any


AEST = timezone(timedelta(hours=10))


@dataclass
class BackupHealth:
    running: bool
    pid: int | None
    zero_yield_events: int
    last_cycle_zero_yield: bool
    http_403_sources: list[str]
    configured_suburbs: list[str]
    summary_available: bool
    summary_error: str | None

    def to_dict(self) -> dict[str, Any]:
        return {
            "running": self.running,
            "pid": self.pid,
            "zero_yield_events": self.zero_yield_events,
            "last_cycle_zero_yield": self.last_cycle_zero_yield,
            "http_403_sources": self.http_403_sources,
            "configured_suburbs": self.configured_suburbs,
            "summary_available": self.summary_available,
            "summary_error": self.summary_error,
        }


def load_text(path: Path) -> str:
    return path.read_text(encoding="utf-8")


def load_json(path: Path) -> Any:
    return json.loads(load_text(path))


def parse_backup_health(context_root: Path) -> BackupHealth:
    backup_root = context_root / "backup-scraper"
    status_text = load_text(backup_root / "status.txt")
    log_text = load_text(backup_root / "recent_log.txt")
    summary_text = load_text(backup_root / "discovered_urls_summary.txt")
    entrypoint_text = load_text(backup_root / "code" / "url_tracking_run.py")

    pid_match = re.search(r"RUNNING\s+PID:\s*(\d+)", status_text)
    running = "✅ RUNNING" in status_text
    pid = int(pid_match.group(1)) if pid_match else None

    zero_yield_events = len(re.findall(r"\[Pass 0 done\]\s+0 new URLs processed", status_text + "\n" + log_text))
    last_cycle_zero_yield = bool(
        re.search(r"Last cycle summary:.*?new URLs: 0", status_text, flags=re.DOTALL)
        or re.search(r"New URLs discovered:\s+0", log_text)
    )

    http_403_sources: list[str] = []
    current_agency: str | None = None
    for line in log_text.splitlines():
        agency_match = re.match(r"---\s+(.+?)\s+---", line.strip())
        if agency_match:
            current_agency = agency_match.group(1)
            continue
        if "ERROR: HTTP 403" in line and current_agency and current_agency not in http_403_sources:
            http_403_sources.append(current_agency)

    suburbs_match = re.search(r"suburbs=\[(.*?)\]", entrypoint_text, flags=re.DOTALL)
    configured_suburbs = []
    if suburbs_match:
        configured_suburbs = re.findall(r"'([^']+)'", suburbs_match.group(1))

    summary_available = "timed out" not in summary_text.lower() and "ssh exception" not in summary_text.lower()
    summary_error = None if summary_available else summary_text.strip()

    return BackupHealth(
        running=running,
        pid=pid,
        zero_yield_events=zero_yield_events,
        last_cycle_zero_yield=last_cycle_zero_yield,
        http_403_sources=http_403_sources,
        configured_suburbs=configured_suburbs,
        summary_available=summary_available,
        summary_error=summary_error,
    )


def expected_weekly_run_date(generated_at: datetime, run_day: int = 6, run_time_local: time = time(20, 30)) -> datetime.date:
    """Return the last weekly due date whose run window has fully opened.

    `run_day` uses Python weekday numbering where Monday=0 and Sunday=6.
    """
    local_dt = generated_at.astimezone(AEST)
    days_since_run_day = (local_dt.weekday() - run_day) % 7
    candidate_date = (local_dt - timedelta(days=days_since_run_day)).date()
    candidate_dt = datetime.combine(candidate_date, run_time_local, tzinfo=AEST)
    if local_dt < candidate_dt:
        candidate_date = candidate_date - timedelta(days=7)
    return candidate_date


def evaluate_weekly_freshness(context_root: Path) -> dict[str, Any]:
    data = load_json(context_root / "metrics" / "orchestrator_health.json")
    generated_at = datetime.fromisoformat(data["generated_at"])
    weekly = data["weekly"]
    expected = expected_weekly_run_date(generated_at)
    recorded_expected = weekly.get("expected_last_run_date")
    actual_date = weekly.get("date")
    should_be_stale = actual_date != expected.isoformat()
    exporter_false_alert = recorded_expected != expected.isoformat()

    return {
        "generated_at": generated_at.astimezone(AEST).isoformat(),
        "actual_weekly_run_date": actual_date,
        "recorded_expected_last_run_date": recorded_expected,
        "due_window_expected_last_run_date": expected.isoformat(),
        "reported_freshness": weekly.get("freshness"),
        "should_be_stale_by_due_window": should_be_stale,
        "exporter_false_alert": exporter_false_alert,
    }


def summarize_watchdog_recurrence(context_root: Path, min_count: int = 3) -> dict[str, int]:
    fix_root = context_root / "fix-history"
    counts: Counter[str] = Counter()
    for path in sorted(fix_root.glob("*.md")):
        for line in load_text(path).splitlines():
            if line.startswith("## [WATCHDOG]"):
                counts[line.split(" — ", 1)[0]] += 1
    return {name: count for name, count in counts.items() if count >= min_count}


def build_report(context_root: Path) -> dict[str, Any]:
    backup = parse_backup_health(context_root)
    weekly = evaluate_weekly_freshness(context_root)
    watchdog = summarize_watchdog_recurrence(context_root)
    return {
        "generated_at_utc": datetime.now(timezone.utc).isoformat(),
        "backup_scraper": backup.to_dict(),
        "weekly_orchestrator": weekly,
        "watchdog_recurrence": watchdog,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--context-root", default="context", help="Path to exported context root")
    parser.add_argument("--output", help="Optional JSON output path")
    args = parser.parse_args()

    report = build_report(Path(args.context_root))
    output = json.dumps(report, indent=2)
    if args.output:
        Path(args.output).write_text(output + "\n", encoding="utf-8")
    else:
        print(output)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
