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

Usage:
    from job_status import record_job_result
    record_job_result("fetch_abs_market_signals", "success", indicators_written=6)
    record_job_result("fetch_abs_market_signals", "error", detail=str(e))
"""
from __future__ import annotations
import os
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


def record_job_result(job: str, status: str, detail: str = "", **extra):
    """Write one status doc for `job` to system_monitor.job_runs. Best-effort —
    never raises, so a monitoring write can't itself break the calling job."""
    assert status in ("success", "error"), f"bad status: {status}"
    try:
        client = _get_client()
        doc = {"job": job, "status": status, "detail": detail,
               "run_at": datetime.now(timezone.utc), **extra}
        client["system_monitor"]["job_runs"].replace_one({"job": job}, doc, upsert=True)
        client.close()
    except Exception as e:
        print(f"(job_status: failed to record result for {job}: {e})")
