#!/usr/bin/env python3
"""
Pipeline Signature Utilities for Fields Orchestrator

Last Updated: 28/01/2026, 6:28 PM (Wednesday) - Brisbane
- Initial creation: compute a stable pipeline signature hash for invalidating old "complete" markers

The daily incremental model requires a way to detect when the pipeline definition changes.
We compute a signature from:
- config/process_commands.yaml (primary)

This can be extended later to include downstream script versions.
"""

from __future__ import annotations

import hashlib
from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class PipelineSignature:
    version: int
    signature: str


def _sha256_bytes(data: bytes) -> str:
    h = hashlib.sha256()
    h.update(data)
    return "sha256:" + h.hexdigest()


def compute_pipeline_signature(base_dir: Path, version: int = 2) -> PipelineSignature:
    """Compute a pipeline signature.

    Version indicates the semantic definition of completeness gates.
    User decision: v2 completeness includes Floor Plan V2 artifacts.
    """
    cfg = base_dir / "config" / "process_commands.yaml"
    raw = cfg.read_bytes() if cfg.exists() else b""
    # Include version number in hash input so switching version invalidates old markers.
    material = (f"version:{version}\n".encode("utf-8") + raw)
    return PipelineSignature(version=version, signature=_sha256_bytes(material))
