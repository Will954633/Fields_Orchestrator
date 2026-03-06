#!/usr/bin/env python3
"""
watchdog.py — Fields Orchestrator Self-Healing Watchdog

Runs every 60 minutes as a systemd service (fields-watchdog).

Full-stack health probe sequence:
  1. Guard — skip if orchestrator pipeline is currently running
  2. Scraper health — check last scrape age per target suburb
  3. DB coverage  — check each pipeline step's expected outputs are present
  4. Recent failures — query system_monitor.process_runs for failed steps
  5. API health  — check website endpoints via existing health check records
  6. Website errors — check for elevated client-side error rates

For each issue found:
  - TRANSIENT / UPSTREAM_INCOMPLETE  → auto-trigger process rerun via repair-agent
  - CODE_BUG / DATA_QUALITY / UNKNOWN → create Claude repair request (with
    pre-filled DiagnosticResult context so Claude gets straight to the point)
  - INFRASTRUCTURE                    → log only, no auto-repair
  - Any class but attempt_count >= 3  → mark NEEDS_HUMAN, stop retrying

Infinite loop prevention:
  - Before acting on any issue, count prior attempts in system_monitor.repair_requests
    for the same process_id in the last 48 hours. Cap at MAX_ATTEMPTS_PER_ISSUE=3.
  - Also scan fix history for the same error pattern.

All results written to system_monitor.watchdog_runs for the ops dashboard.

Usage:
    python3 watchdog.py                  # run loop (service mode)
    python3 watchdog.py --once           # single check then exit
    python3 watchdog.py --once --dry-run # diagnose only, no repairs queued
"""

import os
import sys
import time
import signal
import logging
import argparse
import subprocess
import yaml
from datetime import datetime, timezone, timedelta
from pathlib import Path
from typing import Optional

# ---------------------------------------------------------------------------
# Logging
# ---------------------------------------------------------------------------

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [watchdog] %(levelname)s %(message)s",
    handlers=[
        logging.StreamHandler(sys.stdout),
        logging.FileHandler("/home/fields/Fields_Orchestrator/logs/watchdog.log"),
    ],
)
log = logging.getLogger("watchdog")

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

ORCHESTRATOR_DIR  = Path("/home/fields/Fields_Orchestrator")
POLL_INTERVAL     = 3600          # seconds between full checks
MAX_ATTEMPTS      = 3             # stop retrying an issue after this many attempts
ATTEMPT_WINDOW_H  = 48            # hours to look back when counting prior attempts
STALE_SCRAPE_H    = 26            # hours before a suburb's scrape is considered stale
ACTIVE_DB         = "Gold_Coast"
TARGET_SUBURBS    = ["robina", "varsity_lakes", "burleigh_waters"]

# Coverage thresholds — % of target-suburb properties that must have the field
COVERAGE_THRESHOLDS = {
    "valuation_data":          0.70,
    "floor_plan_analysis":     0.55,   # some properties have no floor plan
    "property_insights":       0.80,
    "enriched_data":           0.80,
    "parsed_rooms":            0.55,
    "transactions":            0.20,   # many properties have no prior sale history
    "photo_tour_order":        0.70,
    "property_valuation_data": 0.55,
}

# step_id whose output is the DB field
FIELD_TO_STEP = {
    "valuation_data":          6,
    "floor_plan_analysis":     106,
    "property_insights":       15,
    "enriched_data":           16,
    "parsed_rooms":            11,
    "transactions":            12,
    "photo_tour_order":        105,
    "property_valuation_data": 108,
}

# repair-agent metric that re-runs a given step
STEP_TO_METRIC = {
    6:   "valuation",
    18:  "valuation",
    106: "floor_plan",
    105: "photo_tour",
    12:  "transactions",
    13:  "transactions",
    14:  "insights",
    15:  "insights",
    11:  "insights",
    16:  "insights",
}

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def get_mongo_uri():
    settings_path = ORCHESTRATOR_DIR / "config" / "settings.yaml"
    with open(settings_path) as f:
        s = yaml.safe_load(f)
    uri = s.get("mongodb", {}).get("uri", "")
    if "${COSMOS_CONNECTION_STRING}" in uri:
        uri = os.environ.get("COSMOS_CONNECTION_STRING", "")
    return uri


def get_client(uri: str):
    from pymongo import MongoClient
    return MongoClient(uri, serverSelectionTimeoutMS=10000, retryWrites=False)


def aest_now() -> datetime:
    from zoneinfo import ZoneInfo
    return datetime.now(timezone.utc).astimezone(ZoneInfo("Australia/Brisbane"))


def is_orchestrator_running(client) -> bool:
    """Return True if the nightly pipeline is currently active."""
    try:
        cutoff = datetime.now(timezone.utc) - timedelta(hours=4)
        doc = client["system_monitor"]["process_runs"].find_one(
            {"system": "orchestrator", "status": "running", "started_at": {"$gt": cutoff}},
        )
        return doc is not None
    except Exception:
        return False


def count_with_field(db, field: str) -> int:
    total = 0
    for suburb in TARGET_SUBURBS:
        try:
            total += db[suburb].count_documents({field: {"$exists": True}}, limit=1000)
        except Exception:
            pass
    return total


def count_total(db) -> int:
    total = 0
    for suburb in TARGET_SUBURBS:
        try:
            total += db[suburb].count_documents({"listing_status": "for_sale"}, limit=1000)
        except Exception:
            pass
    return total


def prior_attempt_count(col, process_id: str) -> int:
    """Count non-rejected repair requests for this process in the last ATTEMPT_WINDOW_H hours."""
    cutoff = datetime.now(timezone.utc) - timedelta(hours=ATTEMPT_WINDOW_H)
    return col.count_documents({
        "process_id": str(process_id),
        "status": {"$nin": ["rejected"]},
        "created_at": {"$gt": cutoff},
    })


def queue_repair(col, request_type: str, step_id: int, step_name: str,
                 diagnostic_dict: dict, metric: Optional[str], note: str,
                 log_tail: str = "") -> Optional[str]:
    """Write a repair request. Returns error_id or None if deduped."""
    cutoff = datetime.now(timezone.utc) - timedelta(hours=2)
    existing = col.find_one({
        "process_id": str(step_id),
        "status": {"$in": ["pending", "running", "awaiting_approval"]},
        "created_at": {"$gt": cutoff},
    })
    if existing:
        return None

    error_id = f"watchdog_{step_id}_{int(datetime.now(timezone.utc).timestamp())}"
    doc = {
        "status": "pending",
        "type": request_type,
        "created_at": datetime.now(timezone.utc),
        "error_id": error_id,
        "process_id": str(step_id),
        "process_name": step_name,
        "error_message": f"[WATCHDOG] {note}\n\n{log_tail}"[:2000],
        "context": note,
        "triage": diagnostic_dict,
        "source": "watchdog",
        "agent": None,
        "claude_output": None,
    }
    if metric:
        doc["metric"] = metric
    col.insert_one(doc)
    return error_id


def write_fix_history(issue: dict, action: str, result: str):
    """Append a watchdog action to today's fix history log.
    Deduplicates: only writes if the same step+cause hasn't been logged today."""
    try:
        from zoneinfo import ZoneInfo
        now = datetime.now(timezone.utc).astimezone(ZoneInfo("Australia/Brisbane"))
        date_str = now.strftime("%Y-%m-%d")
        time_str = now.strftime("%H:%M")
        fix_dir = ORCHESTRATOR_DIR / "logs" / "fix-history"
        fix_dir.mkdir(parents=True, exist_ok=True)
        fix_file = fix_dir / f"{date_str}.md"

        # Dedup: check if the same step+cause was already logged today
        step_id = issue.get("step_id", "?")
        cause = issue.get("cause", "")
        dedup_key = f"Step {step_id}"
        if fix_file.exists():
            existing = fix_file.read_text()
            # Count how many times this step was already logged today
            occurrences = existing.count(f"[WATCHDOG] {dedup_key}")
            if occurrences >= 1:
                log.info(f"  Fix history dedup: Step {step_id} already logged {occurrences}x today — skipping")
                return

        entry = (
            f"\n---\n\n"
            f"## [WATCHDOG] Step {step_id} ({issue.get('step_name','')}) — {time_str} AEST\n\n"
            f"**Failure class:** {issue.get('failure_class','?').upper()}\n"
            f"**Cause:** {cause}\n"
            f"**Action taken:** {action}\n"
            f"**Result:** {result}\n"
        )
        if issue.get("root_step"):
            entry += f"**Root step:** {issue['root_step']}\n"
        with open(fix_file, "a") as f:
            f.write(entry)
    except Exception as e:
        log.warning(f"Fix history write failed: {e}")


# ---------------------------------------------------------------------------
# Health checks
# ---------------------------------------------------------------------------

def check_scraper_health(client) -> list:
    """Check last scrape age per target suburb. Returns list of issues."""
    issues = []
    try:
        col = client["system_monitor"]["scraper_health"]
        for suburb in TARGET_SUBURBS:
            doc = col.find_one({"suburb": suburb})
            if not doc:
                issues.append({
                    "type": "stale_scrape",
                    "step_id": 101,
                    "step_name": "Scrape For-Sale Properties (Target Market)",
                    "suburb": suburb,
                    "failure_class": "upstream_incomplete",
                    "cause": f"No scraper health record found for {suburb}",
                    "root_step": None,
                    "metric": None,
                    "auto_fixable": True,
                })
                continue
            last_scrape = doc.get("last_scrape")
            if last_scrape:
                age_h = (datetime.now(timezone.utc) - last_scrape.replace(tzinfo=timezone.utc)
                         if last_scrape.tzinfo is None
                         else (datetime.now(timezone.utc) - last_scrape)).total_seconds() / 3600
                if age_h > STALE_SCRAPE_H:
                    issues.append({
                        "type": "stale_scrape",
                        "step_id": 101,
                        "step_name": "Scrape For-Sale Properties (Target Market)",
                        "suburb": suburb,
                        "failure_class": "upstream_incomplete",
                        "cause": f"{suburb} last scraped {age_h:.1f}h ago (threshold: {STALE_SCRAPE_H}h)",
                        "root_step": None,
                        "metric": None,
                        "auto_fixable": True,
                        "evidence": {"age_hours": round(age_h, 1)},
                    })
    except Exception as e:
        log.warning(f"Scraper health check error: {e}")
    return issues


def check_db_coverage(client) -> list:
    """Check each pipeline step's expected DB output coverage. Returns list of issues."""
    issues = []
    try:
        db = client[ACTIVE_DB]
        total = count_total(db)
        if total == 0:
            log.warning("No properties found in target suburb collections — skipping coverage check")
            return issues

        for field, threshold in COVERAGE_THRESHOLDS.items():
            with_field = count_with_field(db, field)
            coverage = with_field / total
            if coverage < threshold:
                step_id = FIELD_TO_STEP.get(field)
                gap = int((threshold - coverage) * total)
                issues.append({
                    "type": "low_coverage",
                    "step_id": step_id,
                    "step_name": f"Step {step_id} output ({field})",
                    "failure_class": "upstream_incomplete",
                    "cause": (
                        f"'{field}' on {with_field}/{total} properties "
                        f"({coverage:.0%} vs {threshold:.0%} threshold) — {gap} short"
                    ),
                    "root_step": None,
                    "metric": STEP_TO_METRIC.get(step_id) if step_id else None,
                    "auto_fixable": True,
                    "evidence": {
                        "field": field,
                        "with_field": with_field,
                        "total": total,
                        "coverage_pct": round(coverage * 100, 1),
                        "threshold_pct": round(threshold * 100, 1),
                    },
                })
    except Exception as e:
        log.warning(f"DB coverage check error: {e}")
    return issues


def check_collection_counts(client) -> list:
    """Check collection-level outputs (suburb_statistics, suburb_median_prices)."""
    issues = []
    try:
        db = client[ACTIVE_DB]
        # Step 14: suburb_statistics — expect at least one doc per target suburb
        stats_count = db["suburb_statistics"].count_documents({}, limit=100)
        if stats_count < len(TARGET_SUBURBS):
            issues.append({
                "type": "empty_collection",
                "step_id": 14,
                "step_name": "Generate Suburb Statistics",
                "failure_class": "upstream_incomplete",
                "cause": f"suburb_statistics has {stats_count} docs (expected >= {len(TARGET_SUBURBS)})",
                "root_step": None,
                "metric": STEP_TO_METRIC.get(14),
                "auto_fixable": True,
                "evidence": {"suburb_statistics_count": stats_count},
            })
        # Step 13: suburb_median_prices — expect records for multiple suburbs
        median_count = db["suburb_median_prices"].count_documents({}, limit=1000)
        if median_count < 10:
            issues.append({
                "type": "empty_collection",
                "step_id": 13,
                "step_name": "Generate Suburb Median Prices",
                "failure_class": "upstream_incomplete",
                "cause": f"suburb_median_prices has only {median_count} docs",
                "root_step": None,
                "metric": STEP_TO_METRIC.get(13),
                "auto_fixable": True,
                "evidence": {"suburb_median_prices_count": median_count},
            })
    except Exception as e:
        log.warning(f"Collection count check error: {e}")
    return issues


def check_recent_process_failures(client) -> list:
    """Check system_monitor.process_runs for failed steps in the last 26 hours."""
    issues = []
    try:
        cutoff = datetime.now(timezone.utc) - timedelta(hours=26)
        failed_runs = list(
            client["system_monitor"]["process_runs"].find({
                "system": "orchestrator",
                "status": "failed",
                "started_at": {"$gt": cutoff},
            }).sort("started_at", -1).limit(20)
        )

        # Deduplicate by process_id — only report the most recent failure per step
        seen = set()
        for run in failed_runs:
            pid = run.get("process_id")
            if pid in seen:
                continue
            seen.add(pid)

            # Run step_diagnostics if we have a triage already stored; otherwise classify from errors
            triage = run.get("triage")
            if triage:
                failure_class = triage.get("failure_class", "unknown")
                cause = triage.get("cause", f"Step {pid} failed (triage stored)")
                root_step = triage.get("root_step")
            else:
                # Pull error messages and run pattern-based diagnosis
                errors = run.get("errors", [])
                error_text = " ".join(e.get("message", "") for e in errors[:5])
                try:
                    sys.path.insert(0, str(ORCHESTRATOR_DIR))
                    from src.step_diagnostics import diagnose
                    diag = diagnose(step_id=int(pid), stdout=error_text)
                    failure_class = diag.failure_class
                    cause = diag.cause
                    root_step = diag.root_step
                    triage = diag.to_dict()
                except Exception:
                    failure_class = "unknown"
                    cause = f"Step {pid} failed — no triage available"
                    root_step = None
                    triage = {}

            step_name = run.get("process_name", f"Step {pid}")
            issues.append({
                "type": "process_failure",
                "step_id": int(pid) if pid and pid.isdigit() else pid,
                "step_name": step_name,
                "failure_class": failure_class,
                "cause": cause,
                "root_step": root_step,
                "metric": STEP_TO_METRIC.get(int(pid)) if pid and pid.isdigit() else None,
                "auto_fixable": failure_class in ("transient", "upstream_incomplete"),
                "triage": triage,
                "evidence": {"last_failed_at": run.get("started_at")},
            })
    except Exception as e:
        log.warning(f"Process failure check error: {e}")
    return issues


def check_memory_pressure() -> list:
    """Check system memory and kill Chrome if usage exceeds 85% of total RAM."""
    issues = []
    try:
        with open("/proc/meminfo") as f:
            meminfo = {}
            for line in f:
                parts = line.split()
                meminfo[parts[0].rstrip(":")] = int(parts[1])

        total_kb = meminfo.get("MemTotal", 0)
        avail_kb = meminfo.get("MemAvailable", 0)
        if total_kb == 0:
            return issues

        used_pct = (1 - avail_kb / total_kb) * 100

        if used_pct > 85:
            # Find Chrome processes and their total RSS
            result = subprocess.run(
                "ps aux | grep -Ei 'chrom(e|ium|edriver)' | grep -v grep",
                shell=True, capture_output=True, text=True, timeout=10
            )
            chrome_lines = [l for l in result.stdout.strip().split('\n') if l.strip()]

            if chrome_lines:
                # Sum RSS (column 6 in ps aux, in KB)
                chrome_rss_kb = 0
                for line in chrome_lines:
                    parts = line.split()
                    if len(parts) >= 6:
                        try:
                            chrome_rss_kb += int(parts[5])
                        except ValueError:
                            pass

                chrome_rss_mb = chrome_rss_kb // 1024
                log.warning(
                    f"MEMORY PRESSURE: {used_pct:.0f}% used, "
                    f"{len(chrome_lines)} Chrome processes using {chrome_rss_mb}MB — killing them"
                )

                for pattern in ['chromedriver', 'chrome_crashpad', 'chromium', 'chrome']:
                    subprocess.run(['pkill', '-9', '-f', pattern],
                                   capture_output=True, text=True, timeout=10)

                issues.append({
                    "type": "memory_pressure",
                    "step_id": None,
                    "step_name": "System Memory",
                    "failure_class": "infrastructure",
                    "cause": (
                        f"Memory at {used_pct:.0f}% — killed {len(chrome_lines)} Chrome "
                        f"processes ({chrome_rss_mb}MB RSS) to prevent OOM"
                    ),
                    "root_step": None,
                    "metric": None,
                    "auto_fixable": False,
                    "evidence": {
                        "memory_used_pct": round(used_pct, 1),
                        "chrome_count": len(chrome_lines),
                        "chrome_rss_mb": chrome_rss_mb,
                    },
                })
            else:
                log.warning(f"MEMORY PRESSURE: {used_pct:.0f}% used but no Chrome processes found")
    except Exception as e:
        log.warning(f"Memory pressure check error: {e}")
    return issues


def check_api_health(client) -> list:
    """Check recent API health records. Flag any endpoint unhealthy in last 2 checks."""
    issues = []
    try:
        col = client["system_monitor"]["api_health_checks"]
        # Get last 2 records per endpoint
        pipeline = [
            {"$sort": {"checked_at": -1}},
            {"$group": {
                "_id": "$endpoint",
                "checks": {"$push": {"healthy": "$healthy", "checked_at": "$checked_at"}},
            }},
            {"$project": {"last_two": {"$slice": ["$checks", 2]}}},
        ]
        results = list(col.aggregate(pipeline))
        for r in results:
            endpoint = r["_id"]
            last_two = r.get("last_two", [])
            if len(last_two) >= 2 and all(not c["healthy"] for c in last_two):
                issues.append({
                    "type": "api_unhealthy",
                    "step_id": None,
                    "step_name": f"API: {endpoint}",
                    "failure_class": "infrastructure",
                    "cause": f"Endpoint {endpoint} failed last 2 consecutive health checks",
                    "root_step": None,
                    "metric": None,
                    "auto_fixable": False,
                    "evidence": {"endpoint": endpoint},
                })
    except Exception as e:
        log.warning(f"API health check error: {e}")
    return issues


# ---------------------------------------------------------------------------
# Issue router — decides what action to take per issue
# ---------------------------------------------------------------------------

def route_issue(issue: dict, repair_col, dry_run: bool) -> str:
    """
    Decide and execute the repair action for one issue.
    Returns a short result string for logging.
    """
    step_id   = issue.get("step_id")
    step_name = issue.get("step_name", f"step {step_id}")
    fc        = issue.get("failure_class", "unknown")
    metric    = issue.get("metric")

    # Infinite loop guard — count prior attempts
    if step_id:
        attempts = prior_attempt_count(repair_col, str(step_id))
        if attempts >= MAX_ATTEMPTS:
            log.warning(
                f"  ⛔ Step {step_id} has {attempts} prior attempts — marking NEEDS_HUMAN"
            )
            # Mark in repair_requests so ops dashboard shows it
            if not dry_run:
                repair_col.insert_one({
                    "status": "needs_human",
                    "type": "watchdog",
                    "created_at": datetime.now(timezone.utc),
                    "error_id": f"watchdog_blocked_{step_id}_{int(datetime.now(timezone.utc).timestamp())}",
                    "process_id": str(step_id),
                    "process_name": step_name,
                    "error_message": (
                        f"[WATCHDOG] Max attempts ({MAX_ATTEMPTS}) reached for step {step_id}. "
                        f"Last cause: {issue.get('cause','')}"
                    ),
                    "context": f"Watchdog has attempted to fix this {attempts}x — needs human review",
                    "source": "watchdog",
                })
            return f"BLOCKED — {attempts} prior attempts, NEEDS_HUMAN"

    # Infrastructure issues — log only
    if fc == "infrastructure":
        log.info(f"  🔕 INFRA issue — {issue['cause']} — no auto-repair")
        return "LOGGED_ONLY (infrastructure)"

    # API unhealthy — log only (can't auto-repair website infra)
    if issue["type"] == "api_unhealthy":
        log.info(f"  🔕 API unhealthy — {issue['cause']} — no auto-repair")
        return "LOGGED_ONLY (api)"

    # Stale scraper — not safe to auto-trigger (scrape takes 50+ min, resource intensive)
    # Create a process repair request and let repair-agent handle scheduling
    if issue["type"] == "stale_scrape":
        if dry_run:
            return "DRY_RUN — would queue scraper rerun"
        error_id = queue_repair(
            repair_col,
            request_type="process",
            step_id=101,
            step_name=step_name,
            diagnostic_dict=issue.get("triage", {}),
            metric=None,
            note=issue["cause"],
        )
        return f"QUEUED scraper rerun (id={error_id})" if error_id else "DEDUP_SKIPPED"

    # TRANSIENT / UPSTREAM_INCOMPLETE — auto-rerun the responsible step
    if fc in ("transient", "upstream_incomplete") and issue.get("auto_fixable"):
        target_step = issue.get("root_step") or step_id
        target_metric = STEP_TO_METRIC.get(target_step) if target_step else metric
        target_name = step_name if not issue.get("root_step") else f"step {target_step} (root cause)"
        if dry_run:
            return f"DRY_RUN — would queue process rerun for step {target_step} (metric={target_metric})"
        error_id = queue_repair(
            repair_col,
            request_type="process",
            step_id=target_step,
            step_name=target_name,
            diagnostic_dict=issue.get("triage", {}),
            metric=target_metric,
            note=f"[WATCHDOG] {fc}: {issue['cause']}",
        )
        return f"QUEUED process rerun (step={target_step}, metric={target_metric}, id={error_id})"

    # CODE_BUG / DATA_QUALITY / UNKNOWN — escalate to Claude
    if dry_run:
        return f"DRY_RUN — would create Claude repair request for step {step_id}"
    error_id = queue_repair(
        repair_col,
        request_type="claude",
        step_id=step_id,
        step_name=step_name,
        diagnostic_dict=issue.get("triage", {}),
        metric=None,
        note=f"[WATCHDOG] {fc}: {issue['cause']}",
        log_tail=f"Evidence: {issue.get('evidence', {})}",
    )
    return f"ESCALATED to Claude (id={error_id})"


# ---------------------------------------------------------------------------
# Main watchdog check
# ---------------------------------------------------------------------------

def run_check(client, dry_run: bool = False) -> dict:
    """
    Run a full health probe and dispatch repairs.
    Returns a summary dict written to system_monitor.watchdog_runs.
    """
    started_at = datetime.now(timezone.utc)
    repair_col = client["system_monitor"]["repair_requests"]

    log.info("=" * 60)
    log.info("WATCHDOG CHECK STARTING")
    log.info("=" * 60)

    # Guard: skip if orchestrator is running
    if is_orchestrator_running(client):
        log.info("⏳ Orchestrator pipeline is currently running — watchdog standing down")
        return {
            "started_at": started_at,
            "finished_at": datetime.now(timezone.utc),
            "skipped": True,
            "reason": "orchestrator_running",
            "issues_found": 0,
            "actions_taken": [],
        }

    # --- Run all health checks ---
    log.info("0. Memory pressure...")
    memory_issues   = check_memory_pressure()

    log.info("1. Scraper health...")
    scraper_issues  = check_scraper_health(client)

    log.info("2. DB coverage...")
    coverage_issues = check_db_coverage(client)

    log.info("3. Collection counts...")
    collection_issues = check_collection_counts(client)

    log.info("4. Recent process failures...")
    failure_issues  = check_recent_process_failures(client)

    log.info("5. API health...")
    api_issues      = check_api_health(client)

    all_issues = memory_issues + scraper_issues + coverage_issues + collection_issues + failure_issues + api_issues

    # Deduplicate: if the same step_id appears in multiple categories, keep the one
    # from process_failures (has most context) and skip the coverage issue for it.
    failed_step_ids = {i["step_id"] for i in failure_issues if i.get("step_id")}
    deduped_issues = []
    for issue in all_issues:
        if issue["type"] in ("low_coverage", "empty_collection") and issue.get("step_id") in failed_step_ids:
            continue  # already captured via process_failure with richer context
        deduped_issues.append(issue)

    log.info(f"\n{'=' * 60}")
    log.info(f"ISSUES FOUND: {len(deduped_issues)}")
    log.info(f"{'=' * 60}")

    actions = []
    for issue in deduped_issues:
        sid   = issue.get("step_id", "?")
        fc    = issue.get("failure_class", "?").upper()
        cause = issue.get("cause", "")
        log.info(f"  [{fc}] Step {sid}: {cause[:100]}")

        result = route_issue(issue, repair_col, dry_run)
        log.info(f"    → {result}")

        actions.append({
            "step_id":       sid,
            "failure_class": issue.get("failure_class"),
            "cause":         cause,
            "action":        result,
        })
        if not dry_run and ("QUEUED" in result or "ESCALATED" in result):
            write_fix_history(issue, action=result, result="queued — awaiting repair-agent or Claude")

    finished_at = datetime.now(timezone.utc)
    duration_s  = (finished_at - started_at).total_seconds()
    summary = {
        "started_at":    started_at,
        "finished_at":   finished_at,
        "duration_s":    round(duration_s, 1),
        "skipped":       False,
        "issues_found":  len(deduped_issues),
        "actions_taken": actions,
        "dry_run":       dry_run,
        "summary_text":  (
            f"{len(deduped_issues)} issues found: "
            f"{sum(1 for a in actions if 'QUEUED' in a['action'])} queued, "
            f"{sum(1 for a in actions if 'ESCALATED' in a['action'])} escalated, "
            f"{sum(1 for a in actions if 'BLOCKED' in a['action'])} blocked, "
            f"{sum(1 for a in actions if 'LOGGED' in a['action'])} logged-only"
        ),
    }

    log.info(f"\n{summary['summary_text']} (took {duration_s:.0f}s)")

    # Write to watchdog_runs collection
    if not dry_run:
        try:
            client["system_monitor"]["watchdog_runs"].insert_one(dict(summary))
        except Exception as e:
            log.warning(f"Failed to write watchdog_runs: {e}")

    return summary


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------

def main():
    parser = argparse.ArgumentParser(description="Fields Orchestrator Self-Healing Watchdog")
    parser.add_argument("--once",    action="store_true", help="Run one check then exit")
    parser.add_argument("--dry-run", action="store_true", help="Diagnose only, no repairs queued")
    args = parser.parse_args()

    if args.dry_run and not args.once:
        log.warning("--dry-run forces --once (not meaningful as a loop)")
        args.once = True

    log.info("watchdog starting up")
    log.info(f"Poll interval: {POLL_INTERVAL}s | Max attempts: {MAX_ATTEMPTS} | "
             f"Stale scrape threshold: {STALE_SCRAPE_H}h")

    shutdown = [False]
    def _sigterm(sig, frame):
        log.info("SIGTERM received — shutting down")
        shutdown[0] = True
    signal.signal(signal.SIGTERM, _sigterm)

    try:
        uri    = get_mongo_uri()
        client = get_client(uri)
        client.admin.command("ping")
        log.info("MongoDB connected")
    except Exception as e:
        log.error(f"MongoDB connection failed: {e}")
        sys.exit(1)

    while not shutdown[0]:
        try:
            run_check(client, dry_run=args.dry_run)
        except Exception as e:
            log.exception(f"Unexpected error in watchdog check: {e}")

        if args.once:
            break

        log.info(f"Next check in {POLL_INTERVAL // 60} minutes. Sleeping...")
        for _ in range(POLL_INTERVAL):
            if shutdown[0]:
                break
            time.sleep(1)

    client.close()
    log.info("watchdog stopped")


if __name__ == "__main__":
    main()
