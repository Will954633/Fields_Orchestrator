#!/usr/bin/env python3
"""
step_diagnostics.py — Fields Orchestrator

Codified root-cause analysis for pipeline step failures.

Each failing step is diagnosed by:
  1. Pattern-matching stdout/stderr for known error signatures
     (rate limits, infra failures, import errors, missing fields)
  2. Probing MongoDB for expected outputs from this step and its dependencies
     (if step 15 fails, check that step 14 wrote suburb_statistics first)
  3. Walking the depends_on chain from process_commands.yaml

Returns a DiagnosticResult classifying the failure and suggesting concrete actions.

Usage (CLI):
    python3 -m src.step_diagnostics --step 6
    python3 -m src.step_diagnostics --step 15 --stdout /path/to/stdout.log
    python3 -m src.step_diagnostics --step 6 --json
"""

import os
import re
import sys
import yaml
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Optional, Dict, Any, List


# ─── Failure class constants ─────────────────────────────────────────────────

class FC:
    """Failure class labels."""
    TRANSIENT           = "transient"           # Rate limit, timeout, connection blip — retry likely works
    UPSTREAM_INCOMPLETE = "upstream_incomplete"  # A dependency step's DB output is missing
    DATA_QUALITY        = "data_quality"         # Field exists but is malformed/unusable
    INFRASTRUCTURE      = "infrastructure"       # DB/API/disk not available — human attention needed
    CODE_BUG            = "code_bug"             # Traceback, ImportError, SyntaxError
    UNKNOWN             = "unknown"              # Could not classify


# ─── Result dataclass ────────────────────────────────────────────────────────

@dataclass
class DiagnosticResult:
    step_id: int
    failure_class: str                 # One of FC.*
    root_step: Optional[int]           # If upstream_incomplete, the step that's the real problem
    cause: str                         # Human-readable explanation
    evidence: Dict[str, Any]           # DB counts, matched patterns, upstream checks
    suggested_actions: List[str]
    auto_fixable: bool                 # True = safe to re-run without human approval
    retry_recommended: bool            # True = another retry would likely succeed
    diagnosed_at: datetime = field(default_factory=datetime.now)

    def to_dict(self) -> Dict[str, Any]:
        d = {k: v for k, v in self.__dict__.items()}
        d["diagnosed_at"] = self.diagnosed_at.isoformat()
        return d

    def summary(self) -> str:
        parts = [f"Step {self.step_id} [{self.failure_class.upper()}]: {self.cause}"]
        if self.root_step and self.root_step != self.step_id:
            parts.append(f"root_step={self.root_step}")
        if self.suggested_actions:
            parts.append("→ " + "; ".join(self.suggested_actions[:2]))
        return " | ".join(parts)


# ─── Known error patterns ────────────────────────────────────────────────────

_TRANSIENT_PATTERNS = [
    r"RateLimitError",
    r"rate.?limit",
    r"429\s+Too\s+Many\s+Requests",
    r"openai\.error\.RateLimitError",
    r"openai\.RateLimitError",
    r"Process timed out",
    r"timed out after \d+ minutes",
    r"Connection reset by peer",
    r"RemoteDisconnected",
    r"Temporary failure in name resolution",
    r"ServiceUnavailableError",
    r"503\s+Service\s+Unavailable",
    r"HTTPSConnectionPool.*Max retries exceeded",
    r"InsufficientServerResources",
    r"Retry-After",
]

_INFRASTRUCTURE_PATTERNS = [
    r"ServerSelectionTimeoutError",
    r"ConnectionFailure",
    r"Connection refused",
    r"127\.0\.0\.1:27017",            # Unresolved MongoDB localhost — wrong/missing URI
    r"Name or service not known",
    r"No space left on device",
    r"PermissionError.*\[Errno 13\]",
    r"ENOSPC",
    r"Cannot connect to MongoDB",
    r"NetworkTimeout",
    r"MongoServerError.*authentication",
    r"MONGODB_URI.*not set",
    r"COSMOS_CONNECTION_STRING.*not",
]

_CODE_BUG_PATTERNS = [
    r"ImportError",
    r"ModuleNotFoundError",
    r"SyntaxError",
    r"IndentationError",
    r"NameError:\s+name",
    r"TypeError:\s+",
    r"AttributeError:\s+",
    r"RecursionError",
    r"FileNotFoundError.*\.py",
    r"cannot import name",
]

_DATA_QUALITY_PATTERNS = [
    r"KeyError:\s+['\"]?(floor_plan_analysis|room_dimensions|property_valuation_data|"
    r"valuation_data|enriched_data|property_insights|suburb_statistics|property_timeline)",
    r"'floor_plan_analysis'",
    r"'room_dimensions'",
    r"'enriched_data'",
    r"'property_insights'",
    r"NoneType.*has no attribute",
    r"list index out of range",
    r"division by zero",
    r"expected.*got None",
]


# ─── Target market config ─────────────────────────────────────────────────────

TARGET_SUBURBS = ["robina", "varsity_lakes", "burleigh_waters"]
ACTIVE_DB = "Gold_Coast_Currently_For_Sale"

# The DB field that signals a step's output is present on a property document.
# Steps that write to their own collection (e.g. step 13 → suburb_median_prices)
# are NOT listed here — collection-level checks are done in specific check functions.
STEP_OUTPUT_FIELD: Dict[int, str] = {
    6:   "valuation_data",
    11:  "parsed_rooms",           # parse_room_dimensions.py writes parsed_rooms + total_floor_area
    12:  "transactions",           # enrich_property_timeline.py writes transactions
    15:  "property_insights",
    16:  "enriched_data",
    105: "photo_tour_order",       # photo analysis writes photo_tour_order
    106: "floor_plan_analysis",
    108: "property_valuation_data",
    18:  "valuation_data",
}


# ─── DB helpers ──────────────────────────────────────────────────────────────

def _load_settings_uri(settings_path: Optional[str] = None) -> Optional[str]:
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


def _get_client(uri: str):
    from pymongo import MongoClient
    return MongoClient(uri, serverSelectionTimeoutMS=8000, retryWrites=False)


def _count_with_field(client, db_name: str, field_name: str, limit: int = 1000) -> int:
    """Count documents in target suburb collections that have `field_name`."""
    total = 0
    try:
        db = client[db_name]
        for suburb in TARGET_SUBURBS:
            col = db[suburb]
            total += col.count_documents({field_name: {"$exists": True}}, limit=limit)
    except Exception:
        pass
    return total


def _count_without_field(client, db_name: str, field_name: str, limit: int = 1000) -> int:
    """Count documents in target suburb collections that are missing `field_name`."""
    total = 0
    try:
        db = client[db_name]
        for suburb in TARGET_SUBURBS:
            col = db[suburb]
            total += col.count_documents({field_name: {"$exists": False}}, limit=limit)
    except Exception:
        pass
    return total


def _count_collection(client, db_name: str, collection: str) -> int:
    """Count total documents in a specific collection."""
    try:
        return client[db_name][collection].count_documents({}, limit=50000)
    except Exception:
        return -1


def _match_patterns(text: str, patterns: List[str]) -> Optional[str]:
    """Return the first pattern that matches `text`, or None."""
    for p in patterns:
        if re.search(p, text, re.IGNORECASE):
            return p
    return None


def _load_depends_on(step_id: int) -> List[int]:
    """Read the depends_on list for `step_id` from process_commands.yaml."""
    try:
        cfg_path = Path(__file__).parent.parent / "config" / "process_commands.yaml"
        with open(cfg_path) as f:
            cfg = yaml.safe_load(f)
        for proc in cfg.get("processes", []):
            if proc["id"] == step_id:
                return proc.get("depends_on", [])
    except Exception:
        pass
    return []


# ─── Per-step diagnostic functions ───────────────────────────────────────────

def _diagnose_step_6(stdout: str, client) -> DiagnosticResult:
    """Step 6: Property Valuation Model (depends on 101, 106)."""
    evidence: Dict[str, Any] = {}

    # Upstream check: how many properties have floor_plan_analysis (from step 106)?
    with_fp = _count_with_field(client, ACTIVE_DB, "floor_plan_analysis")
    without_fp = _count_without_field(client, ACTIVE_DB, "floor_plan_analysis")
    evidence["floor_plan_analysis_present"] = with_fp
    evidence["floor_plan_analysis_missing"] = without_fp

    # Output check: how many properties now have valuation_data?
    with_val = _count_with_field(client, ACTIVE_DB, "valuation_data")
    evidence["valuation_data_present"] = with_val

    total_props = with_fp + without_fp
    fp_missing_pct = (without_fp / total_props * 100) if total_props > 0 else 0

    # 1. Transient (rate limit / timeout) — check first, highest frequency
    transient = _match_patterns(stdout, _TRANSIENT_PATTERNS)
    if transient:
        return DiagnosticResult(
            step_id=6,
            failure_class=FC.TRANSIENT,
            root_step=None,
            cause=f"API rate limit or timeout (matched: {transient})",
            evidence=evidence,
            suggested_actions=["Wait 10 minutes and re-run step 6"],
            auto_fixable=True,
            retry_recommended=True,
        )

    # 2. Floor plan analysis missing from most properties → step 106 is the root cause
    if fp_missing_pct > 40 and with_fp < 5:
        return DiagnosticResult(
            step_id=6,
            failure_class=FC.UPSTREAM_INCOMPLETE,
            root_step=106,
            cause=(
                f"floor_plan_analysis missing on {without_fp}/{total_props} properties "
                f"({fp_missing_pct:.0f}%) — step 106 (Floor Plan Analysis) incomplete"
            ),
            evidence=evidence,
            suggested_actions=[
                "Re-run step 106 (Floor Plan Analysis) for target suburbs",
                "Then retry step 6 (Property Valuation Model)",
            ],
            auto_fixable=True,
            retry_recommended=False,
        )

    # 3. Data quality (missing field in individual documents)
    dq = _match_patterns(stdout, _DATA_QUALITY_PATTERNS)
    if dq:
        return DiagnosticResult(
            step_id=6,
            failure_class=FC.DATA_QUALITY,
            root_step=106,
            cause=f"Missing or malformed data field in property documents (matched: {dq})",
            evidence=evidence,
            suggested_actions=[
                "Inspect floor_plan_analysis field structure on failing properties",
                "Check step 106 output format has not changed",
            ],
            auto_fixable=False,
            retry_recommended=False,
        )

    # 4. Infrastructure
    infra = _match_patterns(stdout, _INFRASTRUCTURE_PATTERNS)
    if infra:
        return DiagnosticResult(
            step_id=6,
            failure_class=FC.INFRASTRUCTURE,
            root_step=None,
            cause=f"Infrastructure issue — DB or API unreachable (matched: {infra})",
            evidence=evidence,
            suggested_actions=["Check MongoDB connection", "Check COSMOS_CONNECTION_STRING env var"],
            auto_fixable=False,
            retry_recommended=False,
        )

    # 5. Code bug
    bug = _match_patterns(stdout, _CODE_BUG_PATTERNS)
    if bug:
        return DiagnosticResult(
            step_id=6,
            failure_class=FC.CODE_BUG,
            root_step=None,
            cause=f"Code error in valuation script (matched: {bug})",
            evidence=evidence,
            suggested_actions=["Inspect batch_valuate_with_tracking.py traceback in step logs"],
            auto_fixable=False,
            retry_recommended=False,
        )

    return DiagnosticResult(
        step_id=6,
        failure_class=FC.UNKNOWN,
        root_step=None,
        cause="No recognizable error pattern — step failed with non-zero exit code",
        evidence=evidence,
        suggested_actions=["Review full stdout log for step 6"],
        auto_fixable=False,
        retry_recommended=False,
    )


def _diagnose_step_15(stdout: str, client) -> DiagnosticResult:
    """Step 15: Calculate Property Insights (depends on step 14 and step 16)."""
    evidence: Dict[str, Any] = {}

    # Check step 14 output: suburb_statistics collection should have records
    stats_count = _count_collection(client, ACTIVE_DB, "suburb_statistics")
    evidence["suburb_statistics_docs"] = stats_count

    # Check step 16 output: enriched_data field on properties
    with_enriched = _count_with_field(client, ACTIVE_DB, "enriched_data")
    without_enriched = _count_without_field(client, ACTIVE_DB, "enriched_data")
    evidence["enriched_data_present"] = with_enriched
    evidence["enriched_data_missing"] = without_enriched

    # Check own output
    with_insights = _count_with_field(client, ACTIVE_DB, "property_insights")
    evidence["property_insights_present"] = with_insights

    # Suburb stats missing → step 14 didn't write its output
    if stats_count <= 0:
        return DiagnosticResult(
            step_id=15,
            failure_class=FC.UPSTREAM_INCOMPLETE,
            root_step=14,
            cause="suburb_statistics collection is empty — step 14 (Generate Suburb Statistics) did not complete",
            evidence=evidence,
            suggested_actions=[
                "Re-run step 14 (Generate Suburb Statistics)",
                "Then retry step 15 (Calculate Property Insights)",
            ],
            auto_fixable=True,
            retry_recommended=False,
        )

    # enriched_data missing from most properties → step 16 didn't complete
    total_props = with_enriched + without_enriched
    if total_props > 0 and (without_enriched / total_props) > 0.5:
        return DiagnosticResult(
            step_id=15,
            failure_class=FC.UPSTREAM_INCOMPLETE,
            root_step=16,
            cause=(
                f"enriched_data missing on {without_enriched}/{total_props} properties — "
                "step 16 (Enrich Properties For Sale) incomplete"
            ),
            evidence=evidence,
            suggested_actions=[
                "Re-run step 16 (Enrich Properties For Sale)",
                "Then retry step 15 (Calculate Property Insights)",
            ],
            auto_fixable=True,
            retry_recommended=False,
        )

    dq = _match_patterns(stdout, _DATA_QUALITY_PATTERNS)
    if dq:
        return DiagnosticResult(
            step_id=15,
            failure_class=FC.DATA_QUALITY,
            root_step=None,
            cause=f"Missing or malformed field in property documents (matched: {dq})",
            evidence=evidence,
            suggested_actions=[
                "Inspect calculate_property_insights.py traceback",
                "Check enriched_data and suburb_statistics field structures",
            ],
            auto_fixable=False,
            retry_recommended=False,
        )

    transient = _match_patterns(stdout, _TRANSIENT_PATTERNS)
    if transient:
        return DiagnosticResult(
            step_id=15,
            failure_class=FC.TRANSIENT,
            root_step=None,
            cause=f"Transient error (matched: {transient})",
            evidence=evidence,
            suggested_actions=["Retry step 15"],
            auto_fixable=True,
            retry_recommended=True,
        )

    bug = _match_patterns(stdout, _CODE_BUG_PATTERNS)
    if bug:
        return DiagnosticResult(
            step_id=15,
            failure_class=FC.CODE_BUG,
            root_step=None,
            cause=f"Code error in property insights script (matched: {bug})",
            evidence=evidence,
            suggested_actions=["Inspect calculate_property_insights.py traceback"],
            auto_fixable=False,
            retry_recommended=False,
        )

    return DiagnosticResult(
        step_id=15,
        failure_class=FC.UNKNOWN,
        root_step=None,
        cause="No recognizable error pattern — check step 15 logs",
        evidence=evidence,
        suggested_actions=["Review step 15 stdout log for clues"],
        auto_fixable=False,
        retry_recommended=False,
    )


def _diagnose_step_generic(step_id: int, stdout: str, client) -> DiagnosticResult:
    """
    Generic diagnostic for any step not covered by a specific check function.
    Walks the depends_on chain and checks for expected upstream outputs.
    Falls back to pattern matching.
    """
    evidence: Dict[str, Any] = {}
    depends_on = _load_depends_on(step_id)
    evidence["depends_on"] = depends_on

    # Check each upstream dependency for its expected DB output
    for dep_id in depends_on:
        dep_field = STEP_OUTPUT_FIELD.get(dep_id)
        if dep_field:
            count = _count_with_field(client, ACTIVE_DB, dep_field)
            evidence[f"step_{dep_id}_{dep_field}_count"] = count
            if count == 0:
                return DiagnosticResult(
                    step_id=step_id,
                    failure_class=FC.UPSTREAM_INCOMPLETE,
                    root_step=dep_id,
                    cause=(
                        f"Step {dep_id} output field '{dep_field}' not found on any target properties — "
                        f"step {dep_id} likely did not complete"
                    ),
                    evidence=evidence,
                    suggested_actions=[
                        f"Re-run step {dep_id}",
                        f"Then retry step {step_id}",
                    ],
                    auto_fixable=True,
                    retry_recommended=False,
                )

    # Pattern matching over stdout
    for patterns, cls, retry, auto_fix in [
        (_TRANSIENT_PATTERNS,    FC.TRANSIENT,      True,  True),
        (_INFRASTRUCTURE_PATTERNS, FC.INFRASTRUCTURE, False, False),
        (_CODE_BUG_PATTERNS,     FC.CODE_BUG,       False, False),
        (_DATA_QUALITY_PATTERNS, FC.DATA_QUALITY,   False, False),
    ]:
        matched = _match_patterns(stdout, patterns)
        if matched:
            return DiagnosticResult(
                step_id=step_id,
                failure_class=cls,
                root_step=None,
                cause=f"Matched error pattern: {matched}",
                evidence={**evidence, "matched_pattern": matched},
                suggested_actions=[f"Investigate step {step_id} logs around pattern: {matched}"],
                auto_fixable=auto_fix,
                retry_recommended=retry,
            )

    return DiagnosticResult(
        step_id=step_id,
        failure_class=FC.UNKNOWN,
        root_step=None,
        cause="No recognizable error pattern — check logs manually",
        evidence=evidence,
        suggested_actions=[f"Review step {step_id} stdout log for clues"],
        auto_fixable=False,
        retry_recommended=False,
    )


def _pattern_only_diagnose(step_id: int, stdout: str) -> DiagnosticResult:
    """Fallback when DB connection is unavailable — pattern matching only."""
    for patterns, cls, retry, auto_fix in [
        (_TRANSIENT_PATTERNS,    FC.TRANSIENT,      True,  True),
        (_INFRASTRUCTURE_PATTERNS, FC.INFRASTRUCTURE, False, False),
        (_CODE_BUG_PATTERNS,     FC.CODE_BUG,       False, False),
        (_DATA_QUALITY_PATTERNS, FC.DATA_QUALITY,   False, False),
    ]:
        matched = _match_patterns(stdout, patterns)
        if matched:
            return DiagnosticResult(
                step_id=step_id,
                failure_class=cls,
                root_step=None,
                cause=f"Pattern match (DB unavailable): {matched}",
                evidence={"db_available": False, "matched_pattern": matched},
                suggested_actions=[f"Investigate step {step_id} logs around: {matched}"],
                auto_fixable=auto_fix,
                retry_recommended=retry,
            )

    return DiagnosticResult(
        step_id=step_id,
        failure_class=FC.UNKNOWN,
        root_step=None,
        cause="DB unavailable and no error pattern matched in stdout",
        evidence={"db_available": False},
        suggested_actions=["Check DB connection, then review step logs manually"],
        auto_fixable=False,
        retry_recommended=False,
    )


# ─── Step dispatch table ─────────────────────────────────────────────────────

_STEP_CHECKS = {
    6:  _diagnose_step_6,
    15: _diagnose_step_15,
}


# ─── Public API ──────────────────────────────────────────────────────────────

def diagnose(
    step_id: int,
    stdout: str = "",
    settings_path: Optional[str] = None,
) -> DiagnosticResult:
    """
    Diagnose a failed pipeline step.

    Args:
        step_id:       The step ID that failed (e.g. 6, 15, 106).
        stdout:        Captured stdout/stderr from the step (used for pattern matching).
        settings_path: Path to settings.yaml. Defaults to project root config.

    Returns:
        DiagnosticResult with failure classification, root cause, and suggested actions.
    """
    uri = _load_settings_uri(settings_path)
    client = None

    if uri:
        try:
            client = _get_client(uri)
            client.admin.command("ping")
        except Exception:
            client = None

    try:
        check_fn = _STEP_CHECKS.get(step_id)
        if check_fn and client:
            result = check_fn(stdout, client)
        elif client:
            result = _diagnose_step_generic(step_id, stdout, client)
        else:
            result = _pattern_only_diagnose(step_id, stdout)
    finally:
        if client:
            try:
                client.close()
            except Exception:
                pass

    return result


# ─── CLI ─────────────────────────────────────────────────────────────────────

if __name__ == "__main__":
    import argparse
    import json

    parser = argparse.ArgumentParser(
        description="Diagnose a failed Fields pipeline step",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=__doc__,
    )
    parser.add_argument("--step", type=int, required=True, help="Step ID to diagnose (e.g. 6, 15)")
    parser.add_argument("--stdout", type=str, default="", help="Path to captured stdout/stderr log")
    parser.add_argument("--json", action="store_true", help="Output as JSON")
    args = parser.parse_args()

    stdout_text = ""
    if args.stdout and Path(args.stdout).exists():
        stdout_text = Path(args.stdout).read_text(errors="replace")

    result = diagnose(step_id=args.step, stdout=stdout_text)

    if getattr(args, "json"):
        print(json.dumps(result.to_dict(), indent=2))
    else:
        w = 60
        print(f"\n{'=' * w}")
        print(f"  STEP {result.step_id} DIAGNOSIS")
        print(f"{'=' * w}")
        print(f"  Failure class  : {result.failure_class.upper()}")
        print(f"  Cause          : {result.cause}")
        if result.root_step:
            print(f"  Root step      : {result.root_step}")
        print(f"  Auto-fixable   : {'yes' if result.auto_fixable else 'no'}")
        print(f"  Retry advised  : {'yes' if result.retry_recommended else 'no'}")
        if result.evidence:
            print(f"  Evidence       :")
            for k, v in result.evidence.items():
                print(f"    {k}: {v}")
        if result.suggested_actions:
            print(f"  Actions        :")
            for a in result.suggested_actions:
                print(f"    → {a}")
        print(f"{'=' * w}\n")
