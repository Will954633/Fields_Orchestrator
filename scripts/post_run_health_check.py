#!/usr/bin/env python3
"""
Post-Run Health Check — Compares tonight's pipeline run against the previous run.
Focuses on Cosmos DB 429 errors, step durations, and data quality.

Usage:
    python3 scripts/post_run_health_check.py           # Compare last 2 runs
    python3 scripts/post_run_health_check.py --verbose  # Include per-step detail

Designed to run automatically after pipeline completes (cron or watchdog hook).
"""

import json
import os
import re
import sys
from datetime import datetime
from pathlib import Path

RUNS_DIR = Path("/home/fields/Fields_Orchestrator/logs/runs")
LOG_FILE = Path("/home/fields/Fields_Orchestrator/logs/orchestrator.log")
REPORT_DIR = Path("/home/fields/Fields_Orchestrator/logs/health-checks")

VERBOSE = "--verbose" in sys.argv or "-v" in sys.argv


def get_last_n_runs(n=2):
    """Get the last N run directories, sorted newest first."""
    runs = sorted(RUNS_DIR.iterdir(), key=lambda p: p.name, reverse=True)
    return runs[:n]


def parse_run(run_dir):
    """Parse a run directory into a structured dict."""
    run = {
        "name": run_dir.name,
        "steps": {},
        "summary": {},
    }

    # Load summary
    summary_file = run_dir / "run_summary.json"
    if summary_file.exists():
        try:
            run["summary"] = json.loads(summary_file.read_text())
        except Exception:
            pass

    # Load each step
    for step_dir in sorted(run_dir.iterdir()):
        if not step_dir.is_dir():
            continue
        result_file = step_dir / "result.json"
        if not result_file.exists():
            continue
        try:
            result = json.loads(result_file.read_text())
            step_name = step_dir.name
            run["steps"][step_name] = {
                "success": result.get("success", False),
                "duration": round(result.get("duration_seconds", 0)),
                "error": result.get("error_message"),
            }
        except Exception:
            pass

    return run


def count_429_errors_in_log(since_timestamp=None):
    """Count 429/16500 errors in orchestrator.log, optionally since a timestamp."""
    if not LOG_FILE.exists():
        return 0, 0

    count = 0
    retry_total_ms = 0
    pattern = re.compile(r"16500|Request rate is large|TooManyRequests")
    retry_pattern = re.compile(r"RetryAfterMs=(\d+)")

    with open(LOG_FILE, "r", errors="replace") as f:
        for line in f:
            if since_timestamp and line[:19] < since_timestamp:
                continue
            if pattern.search(line):
                count += 1
                m = retry_pattern.search(line)
                if m:
                    retry_total_ms += int(m.group(1))

    return count, retry_total_ms


def count_429_in_step_logs(run_dir):
    """Count 429 errors in individual step stderr logs."""
    total = 0
    per_step = {}
    for step_dir in sorted(run_dir.iterdir()):
        if not step_dir.is_dir():
            continue
        stderr_file = step_dir / "stderr.log"
        if not stderr_file.exists():
            continue
        count = 0
        try:
            text = stderr_file.read_text(errors="replace")
            count = len(re.findall(r"16500|Request rate is large|TooManyRequests|429", text))
        except Exception:
            pass
        if count > 0:
            per_step[step_dir.name] = count
            total += count
    return total, per_step


def check_enrichment_counts():
    """Quick check of enrichment status via the DB."""
    try:
        from pymongo import MongoClient
        uri = os.environ.get("COSMOS_CONNECTION_STRING") or os.environ.get("MONGODB_URI")
        if not uri:
            # Try loading from .env
            env_file = Path("/home/fields/Fields_Orchestrator/.env")
            if env_file.exists():
                for line in env_file.read_text().splitlines():
                    if line.startswith("COSMOS_CONNECTION_STRING="):
                        uri = line.split("=", 1)[1].strip().strip('"').strip("'")
                        break
        if not uri:
            return None

        client = MongoClient(uri, serverSelectionTimeoutMS=5000)
        db = client["Gold_Coast"]

        target_suburbs = ["robina", "burleigh_waters", "varsity_lakes"]
        counts = {}
        for suburb in target_suburbs:
            coll = db[suburb]
            for_sale = coll.count_documents({"listing_status": "for_sale"})
            with_valuation = coll.count_documents({
                "listing_status": "for_sale",
                "valuation_data": {"$exists": True}
            })
            with_insights = coll.count_documents({
                "listing_status": "for_sale",
                "property_insights_updated": {"$exists": True}
            })
            counts[suburb] = {
                "for_sale": for_sale,
                "with_valuation": with_valuation,
                "with_insights": with_insights,
            }

        client.close()
        return counts

    except Exception as e:
        return {"error": str(e)}


def generate_report():
    """Generate the health check report."""
    runs = get_last_n_runs(2)
    if not runs:
        print("No runs found.")
        return

    current = parse_run(runs[0])
    previous = parse_run(runs[1]) if len(runs) > 1 else None

    lines = []
    lines.append("=" * 70)
    lines.append("POST-RUN HEALTH CHECK")
    lines.append(f"Generated: {datetime.now():%Y-%m-%d %H:%M:%S AEST}")
    lines.append("=" * 70)
    lines.append("")

    # --- Run comparison ---
    cur_summary = current["summary"]
    lines.append(f"Current run:  {current['name']}")
    lines.append(f"  Status:     {cur_summary.get('status', '?')}")
    lines.append(f"  Steps:      {cur_summary.get('steps_completed', '?')} completed, "
                 f"{cur_summary.get('steps_failed', '?')} failed")
    lines.append(f"  Duration:   {cur_summary.get('total_duration_seconds', 0) / 60:.0f} min")

    if previous:
        prev_summary = previous["summary"]
        lines.append("")
        lines.append(f"Previous run: {previous['name']}")
        lines.append(f"  Status:     {prev_summary.get('status', '?')}")
        lines.append(f"  Steps:      {prev_summary.get('steps_completed', '?')} completed, "
                     f"{prev_summary.get('steps_failed', '?')} failed")
        lines.append(f"  Duration:   {prev_summary.get('total_duration_seconds', 0) / 60:.0f} min")

    # --- 429 errors ---
    lines.append("")
    lines.append("-" * 70)
    lines.append("COSMOS DB 429 ERRORS")
    lines.append("-" * 70)

    cur_429, cur_429_steps = count_429_in_step_logs(runs[0])
    lines.append(f"Current run 429s (step logs): {cur_429}")
    if cur_429_steps:
        for step, count in sorted(cur_429_steps.items(), key=lambda x: -x[1]):
            lines.append(f"  {step}: {count}")

    if previous and len(runs) > 1:
        prev_429, prev_429_steps = count_429_in_step_logs(runs[1])
        lines.append(f"Previous run 429s (step logs): {prev_429}")
        delta = cur_429 - prev_429
        emoji = "✅" if delta < 0 else ("⚠️" if delta > 0 else "➡️")
        lines.append(f"Change: {delta:+d} {emoji}")

    # --- Step-by-step comparison ---
    lines.append("")
    lines.append("-" * 70)
    lines.append("STEP COMPARISON (duration in seconds)")
    lines.append("-" * 70)
    lines.append(f"{'Step':<55} {'Now':>6} {'Prev':>6} {'Δ':>7}")
    lines.append("-" * 70)

    # Key steps to watch (the ones we changed)
    watch_steps = {"step_6", "step_11", "step_15", "step_16", "step_17", "step_18", "step_19"}

    for step_name, step_data in current["steps"].items():
        success_icon = "✅" if step_data["success"] else "❌"
        cur_dur = step_data["duration"]

        prev_dur = ""
        delta = ""
        if previous and step_name in previous["steps"]:
            pd = previous["steps"][step_name]["duration"]
            prev_dur = str(pd)
            d = cur_dur - pd
            delta = f"{d:+d}"

        # Highlight watched steps
        marker = " ⭐" if any(ws in step_name for ws in watch_steps) else ""
        label = f"{success_icon} {step_name[:50]}{marker}"
        lines.append(f"{label:<55} {cur_dur:>6} {prev_dur:>6} {delta:>7}")

    # --- Failed steps detail ---
    failed = {k: v for k, v in current["steps"].items() if not v["success"]}
    if failed:
        lines.append("")
        lines.append("-" * 70)
        lines.append("FAILED STEPS — DETAIL")
        lines.append("-" * 70)
        for step_name, step_data in failed.items():
            lines.append(f"❌ {step_name}")
            lines.append(f"   Duration: {step_data['duration']}s")
            if step_data.get("error"):
                lines.append(f"   Error: {step_data['error'][:200]}")
            # Check for 429 in stderr
            stderr_file = runs[0] / step_name / "stderr.log"
            if stderr_file.exists():
                text = stderr_file.read_text(errors="replace")
                n429 = len(re.findall(r"16500|TooManyRequests", text))
                if n429:
                    lines.append(f"   429 errors in stderr: {n429}")
                # Last 3 lines of stderr
                last_lines = [l.strip() for l in text.strip().splitlines()[-3:] if l.strip()]
                if last_lines:
                    lines.append(f"   Last stderr:")
                    for ll in last_lines:
                        lines.append(f"     {ll[:150]}")
            lines.append("")

    # --- Enrichment status ---
    lines.append("-" * 70)
    lines.append("ENRICHMENT STATUS (live DB check)")
    lines.append("-" * 70)

    enrichment = check_enrichment_counts()
    if enrichment and "error" not in enrichment:
        for suburb, counts in enrichment.items():
            fs = counts["for_sale"]
            val = counts["with_valuation"]
            ins = counts["with_insights"]
            val_pct = f"{val/fs*100:.0f}%" if fs > 0 else "N/A"
            ins_pct = f"{ins/fs*100:.0f}%" if fs > 0 else "N/A"
            lines.append(f"  {suburb}: {fs} for_sale | valuation: {val} ({val_pct}) | insights: {ins} ({ins_pct})")
    elif enrichment:
        lines.append(f"  Error: {enrichment.get('error', 'unknown')}")
    else:
        lines.append("  Could not connect to DB")

    # --- Verdict ---
    lines.append("")
    lines.append("=" * 70)

    status = cur_summary.get("status", "unknown")
    failed_count = cur_summary.get("steps_failed", 0)

    if status == "completed" and cur_429 == 0:
        lines.append("VERDICT: ✅ CLEAN RUN — no failures, no 429 errors")
    elif status == "completed" and cur_429 > 0:
        lines.append(f"VERDICT: ⚠️ COMPLETED WITH {cur_429} COSMOS 429 ERRORS — throttling still needed")
    elif failed_count > 0 and cur_429 > 0:
        lines.append(f"VERDICT: ❌ {failed_count} STEP(S) FAILED + {cur_429} 429 ERRORS — throttle changes may be insufficient")
    elif failed_count > 0:
        lines.append(f"VERDICT: ❌ {failed_count} STEP(S) FAILED (non-429 cause)")
    else:
        lines.append(f"VERDICT: ❓ Status: {status}")

    lines.append("=" * 70)

    report = "\n".join(lines)
    print(report)

    # Save to file
    REPORT_DIR.mkdir(parents=True, exist_ok=True)
    report_file = REPORT_DIR / f"{datetime.now():%Y-%m-%d_%H%M}.txt"
    report_file.write_text(report)
    print(f"\nReport saved to: {report_file}")

    return report


if __name__ == "__main__":
    generate_report()
