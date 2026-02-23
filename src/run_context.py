#!/usr/bin/env python3
"""
Run Context Utilities for Fields Orchestrator

Last Updated: 28/01/2026, 6:27 PM (Wednesday) - Brisbane
- Initial creation: RUN_ID generation + per-run state files (candidates, summary)

Provides a small, explicit "run context" object so multiple modules can:
- share a common RUN_ID
- write/read run state artifacts under state/

This is used to support the daily incremental operating model.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional


def generate_run_id(now: Optional[datetime] = None) -> str:
    """Generate a stable run id string with timezone-less local time.

    We intentionally keep this simple and filesystem-safe.
    Example: 2026-01-28T18-27-00
    """
    now = now or datetime.now()
    return now.strftime("%Y-%m-%dT%H-%M-%S")


@dataclass(frozen=True)
class RunContext:
    """Shared context for a single orchestrator execution."""

    run_id: str
    base_dir: Path

    @property
    def state_dir(self) -> Path:
        return self.base_dir / "state"

    @property
    def candidates_file(self) -> Path:
        return self.state_dir / "current_run_candidates.json"

    @property
    def summary_file(self) -> Path:
        return self.state_dir / "last_run_summary.json"

    def write_candidates(self, candidates: List[str]) -> None:
        self.state_dir.mkdir(parents=True, exist_ok=True)
        payload = {
            "run_id": self.run_id,
            "generated_at": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            "canonical_key": "address",
            "count": len(candidates),
            "candidates": candidates,
        }
        self.candidates_file.write_text(json.dumps(payload, indent=2), encoding="utf-8")

    def write_candidate_sets(self, candidate_sets: Dict[str, Any]) -> None:
        """Write richer candidate-set details for audit/debugging."""
        self.state_dir.mkdir(parents=True, exist_ok=True)
        payload = {
            "run_id": self.run_id,
            "generated_at": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            "canonical_key": "address",
            **candidate_sets,
        }
        self.candidates_file.write_text(json.dumps(payload, indent=2), encoding="utf-8")

    def write_summary(self, summary: Dict[str, Any]) -> None:
        self.state_dir.mkdir(parents=True, exist_ok=True)
        payload = {
            "run_id": self.run_id,
            "written_at": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            **summary,
        }
        self.summary_file.write_text(json.dumps(payload, indent=2), encoding="utf-8")


def load_previous_candidates(base_dir: Path) -> List[str]:
    """Load the previous snapshot of for-sale addresses (if present)."""
    snapshot_file = base_dir / "state" / "for_sale_snapshot.json"
    if not snapshot_file.exists():
        return []

    try:
        data = json.loads(snapshot_file.read_text(encoding="utf-8"))
        props = data.get("properties", [])
        # existing snapshot format stores objects with url/address
        return [p.get("address") for p in props if p.get("address")]
    except Exception:
        return []
