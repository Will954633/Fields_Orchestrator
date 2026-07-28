#!/usr/bin/env python3
"""
job_status.py — shared helper for scripts to record their own run outcome.

Most cron scripts in this fleet have an external side effect (a Mongo doc, a
Sheet, a GCS object) that a health checker can verify freshness on. A few
don't — or their failure mode degrades silently in a way freshness alone
can't see (e.g. fetch_abs_market_signals.py: a DNS failure still "succeeds"
and writes a doc, just with every indicator defaulted to null/NEUTRAL).
Those scripts call record_job_result() so main_site_health_check.py's
"Market Signals Fetch" page can tell "ran and got real data" apart from
"ran, wrote nothing useful."

Usage (simple):
    from job_status import record_job_result
    record_job_result("fetch_abs_market_signals", "success", indicators_written=6)
    record_job_result("fetch_abs_market_signals", "error", detail=str(e))

Usage (preferred for any NEW ongoing process — see CLAUDE.md Mandatory Rule 7):
    from job_status import job_run
    with job_run("seo_dashboard", cadence_hours=24,
                 title="SEO & Indexation Dashboard") as beat:
        ...do the work...
        beat.detail = "296 clicks / 62% indexed"      # optional success summary
        beat.metrics = {"clicks": 296, "indexed_pct": 62}
    # -> on clean exit records status=success; on ANY exception records
    #    status=error (with traceback) and re-raises, so the run can NEVER
    #    fail silently. Passing cadence_hours self-registers the job so it
    #    auto-appears on the "Fields Systems Health" sheet's Process Registry
    #    with staleness detection — no per-script renderer wiring needed.
"""
from __future__ import annotations
import contextlib
import os
import time
import traceback
from datetime import datetime, timezone


def _get_client():
    from pymongo import MongoClient
    conn = os.environ.get("COSMOS_CONNECTION_STRING")
    if not conn:
        import yaml
        cfg_path = os.path.join(os.path.dirname(__file__), "..", "config", "settings.yaml")
        with open(cfg_path) as f:
            conn = yaml.safe_load(f)["mongodb"]["uri"]
    return MongoClient(conn)


def record_job_result(job: str, status: str, detail: str = "", *,
                      cadence_hours: float | None = None, title: str | None = None,
                      **extra):
    """Write one status doc for `job` to system_monitor.job_runs. Best-effort —
    never raises, so a monitoring write can't itself break the calling job.

    Pass `cadence_hours` (how often the job is expected to run) to SELF-REGISTER:
    the doc gets `self_registered=True` + `cadence_hours`, and the generic
    Process Registry collector in main_site_health_check.py then renders it
    automatically (OK / STALE past cadence / ERROR) — no bespoke wiring."""
    assert status in ("success", "error"), f"bad status: {status}"
    try:
        client = _get_client()
        doc = {"job": job, "status": status, "detail": detail,
               "run_at": datetime.now(timezone.utc), **extra}
        if cadence_hours is not None:
            doc["cadence_hours"] = cadence_hours
            doc["self_registered"] = True
        if title:
            doc["title"] = title
        client["system_monitor"]["job_runs"].replace_one({"job": job}, doc, upsert=True)
        client.close()
    except Exception as e:
        print(f"(job_status: failed to record result for {job}: {e})")


class _Beat:
    """Handle yielded by job_run() so the body can attach a success summary."""
    __slots__ = ("detail", "metrics")

    def __init__(self):
        self.detail = ""
        self.metrics = {}


@contextlib.contextmanager
def job_run(job: str, cadence_hours: float = 24, title: str | None = None, **extra):
    """Context manager that heartbeats the outcome of an ongoing process.

    - Clean exit  -> record_job_result(status="success", duration_s=..., <metrics>)
    - Any exception -> record_job_result(status="error", detail=exc, traceback=...)
      then RE-RAISES (so the failure is still visible in logs/exit code too).

    Always self-registers via cadence_hours so the job surfaces on the Systems
    Health sheet. This is the standard wrapper for every new cron/daemon."""
    beat = _Beat()
    start = time.time()
    try:
        yield beat
    except BaseException as e:
        record_job_result(
            job, "error",
            detail=(f"{type(e).__name__}: {e}")[:500],
            cadence_hours=cadence_hours, title=title,
            traceback=traceback.format_exc()[-1500:],
            duration_s=round(time.time() - start, 1), **extra)
        raise
    else:
        record_job_result(
            job, "success", detail=str(beat.detail)[:500],
            cadence_hours=cadence_hours, title=title,
            duration_s=round(time.time() - start, 1),
            metrics=beat.metrics or {}, **extra)
