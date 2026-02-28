#!/usr/bin/env python3
"""
auto_triage.py — Fields Orchestrator

Classifies step failures and decides the right repair action.

Called from task_executor.py immediately after all retries are exhausted.
Runs step_diagnostics to understand WHY the step failed, then routes to:

  TA.NONE          — Infrastructure failure, log only (no point retrying or
                     involving Claude until the infra issue is fixed)

  TA.PROCESS_RERUN — Re-run a specific process via repair-agent.py (handles
                     transient failures and upstream-incomplete root causes).
                     Written to system_monitor.repair_requests as type="process"
                     so repair-agent picks it up and claude-agent skips it.

  TA.ESCALATE      — Create an enriched Claude repair request (code bugs,
                     data quality issues, unclassified failures). Written as
                     type="claude" so claude-agent picks it up with diagnostic
                     context pre-filled.

Repair request deduplication: no request is queued if one already exists for
the same step in the last 2 hours with status pending/running/awaiting_approval.
"""

import os
import yaml
from dataclasses import dataclass
from datetime import datetime, timedelta
from pathlib import Path
from typing import Optional

from .step_diagnostics import diagnose, DiagnosticResult, FC


# ─── Triage action constants ──────────────────────────────────────────────────

class TA:
    NONE           = "none"          # Log only — infra issue, needs human
    PROCESS_RERUN  = "process_rerun" # Re-run a process (repair-agent.py handles)
    ESCALATE       = "escalate"      # Enriched Claude repair request


# ─── Result dataclass ────────────────────────────────────────────────────────

@dataclass
class TriageDecision:
    action: str                       # One of TA.*
    diagnostic: DiagnosticResult
    repair_step_id: Optional[int]     # For PROCESS_RERUN: which step to re-run
    repair_note: str                  # Human-readable rationale logged by task_executor
    request_id: Optional[str] = None  # Set after writing to MongoDB


# ─── Step → repair metric mapping ─────────────────────────────────────────────
# repair-agent.py uses `metric` to determine which process IDs to run.
# Maps a step ID to the metric that will trigger a rerun of that step.
# Steps with no metric entry will trigger FULL_ENRICHMENT_ORDER in repair-agent.

_STEP_TO_METRIC: dict = {
    6:   "valuation",
    18:  "valuation",
    106: "floor_plan",
    105: "photo_tour",
    12:  "transactions",
    13:  "transactions",
    14:  "insights",
    15:  "insights",
    11:  None,   # no direct metric — repair-agent runs full enrichment
    16:  None,   # no direct metric — repair-agent runs full enrichment
}


# ─── Decision logic ───────────────────────────────────────────────────────────

def _decide(diagnostic: DiagnosticResult, attempts: int) -> tuple:
    """
    Returns (action: str, note: str) based on diagnostic result and attempt count.
    """
    fc = diagnostic.failure_class

    if fc == FC.TRANSIENT:
        if attempts <= 3:
            return (
                TA.PROCESS_RERUN,
                f"Transient failure (rate limit/timeout) after {attempts} attempt(s) — "
                f"queuing delayed rerun of step {diagnostic.step_id}",
            )
        else:
            return (
                TA.ESCALATE,
                f"Transient pattern but {attempts} attempts exhausted — "
                "escalating to Claude for investigation",
            )

    if fc == FC.UPSTREAM_INCOMPLETE:
        root = diagnostic.root_step
        if root and root != diagnostic.step_id:
            return (
                TA.PROCESS_RERUN,
                f"Root cause is step {root} (upstream output missing) — "
                f"queuing rerun of step {root} first",
            )
        # Root step unknown or same as failing step — escalate
        return (
            TA.ESCALATE,
            "Upstream output incomplete but root step unclear — escalating to Claude",
        )

    if fc == FC.INFRASTRUCTURE:
        # No point retrying or calling Claude — infra needs human attention
        return (
            TA.NONE,
            "Infrastructure failure (DB/API/disk) — no auto-repair queued, manual check needed",
        )

    if fc in (FC.CODE_BUG, FC.DATA_QUALITY, FC.UNKNOWN):
        return (
            TA.ESCALATE,
            f"{fc} detected — escalating to Claude with diagnostic context pre-filled",
        )

    return (TA.ESCALATE, f"Unhandled failure class '{fc}' — escalating to Claude")


# ─── MongoDB helpers ──────────────────────────────────────────────────────────

def _load_uri(settings_path: Optional[str] = None) -> Optional[str]:
    if settings_path is None:
        settings_path = Path(__file__).parent.parent / "config" / "settings.yaml"
    try:
        with open(settings_path) as f:
            cfg = yaml.safe_load(f)
        uri = cfg.get("mongodb", {}).get("uri", "") or ""
        if "${COSMOS_CONNECTION_STRING}" in uri:
            uri = os.environ.get("COSMOS_CONNECTION_STRING", "")
        return uri or None
    except Exception:
        return None


def _dedup_check(col, step_id: int) -> bool:
    """Returns True if a recent pending/running request already exists for this step."""
    cutoff = datetime.utcnow() - timedelta(hours=2)
    existing = col.find_one({
        "process_id": str(step_id),
        "status": {"$in": ["pending", "running", "awaiting_approval"]},
        "created_at": {"$gt": cutoff},
    })
    return existing is not None


def _write_repair_request(
    col,
    request_type: str,
    step_id: int,
    step_name: str,
    diagnostic: DiagnosticResult,
    metric: Optional[str],
    note: str,
    log_tail: str,
) -> Optional[str]:
    """
    Insert a repair request document into system_monitor.repair_requests.
    Returns the error_id string on success, None if deduplicated or on error.
    """
    if _dedup_check(col, step_id):
        return None  # Already queued — skip

    error_id = f"triage_{step_id}_{int(datetime.utcnow().timestamp())}"

    # Build the error_message field that claude-agent uses in its prompt.
    # Include the diagnostic summary so Claude gets pre-filled context.
    diag_summary = (
        f"[AUTO-TRIAGE] {diagnostic.failure_class.upper()}: {diagnostic.cause}\n"
        f"Evidence: {diagnostic.evidence}\n"
        f"Suggested: {'; '.join(diagnostic.suggested_actions)}\n"
        f"---\n"
        f"Raw log tail:\n{log_tail[-1500:]}"
    )

    doc = {
        "status": "pending",
        "type": request_type,
        "created_at": datetime.utcnow(),
        "error_id": error_id,
        "process_id": str(step_id),
        "process_name": step_name,
        "error_message": diag_summary,
        "context": note,
        "triage": diagnostic.to_dict(),
        "agent": None,
        "claude_output": None,
    }

    # For process reruns, set metric so repair-agent runs the right processes
    if metric is not None:
        doc["metric"] = metric
    # If metric is None and type is "process", repair-agent runs full enrichment

    col.insert_one(doc)
    return error_id


# ─── Public API ───────────────────────────────────────────────────────────────

def triage_step(
    step_id: int,
    step_name: str,
    stdout: str,
    attempts: int,
    settings_path: Optional[str] = None,
) -> TriageDecision:
    """
    Diagnose and triage a failed pipeline step after all retries are exhausted.

    Args:
        step_id:       The step ID that failed.
        step_name:     Human-readable name (used in repair request).
        stdout:        Captured stdout/stderr from the step (pattern matching).
        attempts:      Total attempts made including all retries.
        settings_path: Path to settings.yaml. Defaults to project config.

    Returns:
        TriageDecision with action, diagnostic, and optional request_id
        (set if a repair request was written to MongoDB).
    """
    diagnostic = diagnose(step_id=step_id, stdout=stdout, settings_path=settings_path)
    action, note = _decide(diagnostic, attempts)

    # For PROCESS_RERUN, re-run the root step (upstream fix) or the failing step (transient)
    if action == TA.PROCESS_RERUN:
        target_step = diagnostic.root_step if diagnostic.root_step else step_id
    else:
        target_step = step_id

    decision = TriageDecision(
        action=action,
        diagnostic=diagnostic,
        repair_step_id=target_step if action == TA.PROCESS_RERUN else None,
        repair_note=note,
    )

    if action == TA.NONE:
        return decision  # Log only — no DB write needed

    # Write repair request to MongoDB
    uri = _load_uri(settings_path)
    if not uri:
        return decision  # No DB available — decision still valid for logging

    try:
        from pymongo import MongoClient
        mc = MongoClient(uri, serverSelectionTimeoutMS=5000, retryWrites=False)
        col = mc["system_monitor"]["repair_requests"]

        request_type = "process" if action == TA.PROCESS_RERUN else "claude"
        metric = _STEP_TO_METRIC.get(target_step) if action == TA.PROCESS_RERUN else None

        error_id = _write_repair_request(
            col=col,
            request_type=request_type,
            step_id=target_step,
            step_name=step_name,
            diagnostic=diagnostic,
            metric=metric,
            note=note,
            log_tail=stdout,
        )
        decision.request_id = error_id
        mc.close()
    except Exception:
        pass  # Triage must never crash the orchestrator

    return decision
