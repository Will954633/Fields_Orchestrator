#!/usr/bin/env python3
"""Validate that the engineering context snapshot is complete enough to review.

Can validate either:
  1. A local directory (e.g. a clone of fields-ceo-context)
  2. The latest CEO run manifest in artifacts/ceo-runs/ (--from-manifest)

Usage:
  python3 scripts/validate_snapshot.py --context-root /path/to/context
  python3 scripts/validate_snapshot.py --from-manifest
  python3 scripts/validate_snapshot.py --from-manifest --json
"""

from __future__ import annotations

import argparse
import json
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Iterable


REQUIRED_FILES = [
    "CLAUDE.md",
    "CONTEXT_MANIFEST.json",
    "OPS_STATUS.md",
    "SCHEMA_SNAPSHOT.md",
    "config/ceo_founder_truths.yaml",
    "founder-requests/index.json",
    "memory/MEMORY.md",
    "memory/structured_memory.json",
    "memory/proposal_outcomes.json",
    "metrics/orchestrator_health.json",
    "metrics/timeline_14d.json",
    "metrics/cost_summary_30d.json",
    "code/targets.json",
    "backup-scraper/status.txt",
    "backup-scraper/recent_log.txt",
    "backup-scraper/discovered_urls_summary.txt",
    "backup-scraper/CLAUDE.md",
    "backup-scraper/directory_listing.txt",
]

REQUIRED_DIRS = [
    "fix-history",
    "founder-requests/open",
    "founder-requests/responses",
    "metrics",
    "config",
    "backup-scraper/code",
]

TUESDAY_CRITICAL_FILES = [
    "metrics/orchestrator_health.json",
    "OPS_STATUS.md",
]


@dataclass
class SnapshotReport:
    context_root: str
    status: str
    required_file_count: int
    required_dir_count: int
    missing_files: list[str]
    missing_dirs: list[str]
    missing_tuesday_critical: list[str]


def missing_paths(root: Path, rel_paths: Iterable[str], expect_dir: bool) -> list[str]:
    missing: list[str] = []
    for rel_path in rel_paths:
        path = root / rel_path
        if expect_dir:
            if not path.is_dir():
                missing.append(rel_path)
        elif not path.is_file():
            missing.append(rel_path)
    return missing


def build_report(context_root: Path) -> SnapshotReport:
    missing_files = missing_paths(context_root, REQUIRED_FILES, expect_dir=False)
    missing_dirs = missing_paths(context_root, REQUIRED_DIRS, expect_dir=True)
    missing_tuesday = missing_paths(context_root, TUESDAY_CRITICAL_FILES, expect_dir=False)
    status = "ok" if not missing_files and not missing_dirs else "degraded"
    return SnapshotReport(
        context_root=str(context_root),
        status=status,
        required_file_count=len(REQUIRED_FILES),
        required_dir_count=len(REQUIRED_DIRS),
        missing_files=missing_files,
        missing_dirs=missing_dirs,
        missing_tuesday_critical=missing_tuesday,
    )


def build_report_from_manifest(manifest_path: Path) -> SnapshotReport:
    """Validate using CONTEXT_MANIFEST.json from a CEO run (no local checkout needed)."""
    with open(manifest_path) as f:
        manifest = json.load(f)

    exported_paths = {
        r["path"] for r in manifest.get("records", []) if r.get("status") == "ok"
    }

    missing_files = [f for f in REQUIRED_FILES if f not in exported_paths]
    # CONTEXT_MANIFEST.json won't be in its own records — remove from missing
    if "CONTEXT_MANIFEST.json" in missing_files:
        missing_files.remove("CONTEXT_MANIFEST.json")

    # Dirs: check if any exported path starts with the dir prefix
    missing_dirs = []
    for d in REQUIRED_DIRS:
        prefix = d if d.endswith("/") else d + "/"
        if not any(p.startswith(prefix) for p in exported_paths):
            missing_dirs.append(d)

    missing_tuesday = [f for f in TUESDAY_CRITICAL_FILES if f not in exported_paths]

    status = "ok" if not missing_files and not missing_dirs else "degraded"
    degraded_flag = manifest.get("degraded", False)
    if degraded_flag:
        status = "degraded"

    return SnapshotReport(
        context_root=str(manifest_path),
        status=status,
        required_file_count=len(REQUIRED_FILES),
        required_dir_count=len(REQUIRED_DIRS),
        missing_files=missing_files,
        missing_dirs=missing_dirs,
        missing_tuesday_critical=missing_tuesday,
    )


def find_latest_manifest() -> Path | None:
    """Find the most recent context_manifest.json from CEO run artifacts."""
    artifacts_dir = Path(__file__).resolve().parent.parent / "artifacts" / "ceo-runs"
    if not artifacts_dir.is_dir():
        return None
    manifests = sorted(artifacts_dir.rglob("context_manifest.json"), reverse=True)
    return manifests[0] if manifests else None


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__,
                                     formatter_class=argparse.RawDescriptionHelpFormatter)
    group = parser.add_mutually_exclusive_group()
    group.add_argument(
        "--context-root",
        default=None,
        help="Path to the exported context directory (local checkout)",
    )
    group.add_argument(
        "--from-manifest",
        action="store_true",
        help="Validate from the latest CEO run manifest (no local checkout needed)",
    )
    parser.add_argument(
        "--manifest-path",
        default=None,
        help="Explicit path to context_manifest.json (used with --from-manifest)",
    )
    parser.add_argument(
        "--json",
        action="store_true",
        help="Print machine-readable JSON instead of text",
    )
    return parser.parse_args()


def print_report(report: SnapshotReport, as_json: bool) -> None:
    if as_json:
        print(json.dumps(asdict(report), indent=2))
    else:
        print(f"Snapshot status: {report.status}")
        print(f"Context root: {report.context_root}")
        print(
            f"Required files present: "
            f"{report.required_file_count - len(report.missing_files)}/{report.required_file_count}"
        )
        print(
            f"Required dirs present: "
            f"{report.required_dir_count - len(report.missing_dirs)}/{report.required_dir_count}"
        )
        if report.missing_files:
            print("Missing files:")
            for path in report.missing_files:
                print(f"  - {path}")
        if report.missing_dirs:
            print("Missing dirs:")
            for path in report.missing_dirs:
                print(f"  - {path}")
        if report.missing_tuesday_critical:
            print("Missing Tuesday-critical inputs:")
            for path in report.missing_tuesday_critical:
                print(f"  - {path}")


def main() -> int:
    args = parse_args()

    if args.from_manifest:
        if args.manifest_path:
            manifest_path = Path(args.manifest_path)
        else:
            manifest_path = find_latest_manifest()
        if manifest_path is None or not manifest_path.is_file():
            print("ERROR: No context_manifest.json found in artifacts/ceo-runs/")
            return 2
        report = build_report_from_manifest(manifest_path)
    else:
        context_root = Path(args.context_root) if args.context_root else Path("context")
        if not context_root.is_dir():
            print(f"ERROR: Context root not found: {context_root}")
            return 2
        report = build_report(context_root)

    print_report(report, args.json)
    return 0 if report.status == "ok" else 1


if __name__ == "__main__":
    raise SystemExit(main())
