"""
Per-Run Logging Infrastructure
Created: 2026-02-18

Manages per-run logging directory structure for the Fields Orchestrator.
Each run gets its own directory with organized, sequential logs for each step.

Directory Structure:
    logs/runs/YYYY-MM-DD_HH-MM-SS_<status>/
    ├── 00_run_metadata.json
    ├── 01_step_101_scrape_for_sale/
    │   ├── start.log
    │   ├── stdout.log
    │   ├── stderr.log
    │   └── result.json
    ├── 02_step_103_monitor_sold/
    │   └── ...
    └── run_summary.json
"""

import json
from datetime import datetime
from pathlib import Path
from typing import Dict, Any, Optional


class RunLogger:
    """Manages per-run logging directory structure."""

    def __init__(self, run_id: str, base_logs_dir: Path):
        """
        Initialize RunLogger for a specific run.

        Args:
            run_id: Unique identifier for this run (format: YYYY-MM-DDTHH-MM-SS)
            base_logs_dir: Base directory for logs (e.g., /path/to/logs)
        """
        self.run_id = run_id
        self.run_dir = base_logs_dir / "runs" / f"{run_id}_running"
        self.current_step_num = 0

    def initialize_run(self, pipeline_signature: Dict[str, Any], config_snapshot: Dict[str, Any]) -> None:
        """
        Create run directory and metadata file.

        Args:
            pipeline_signature: Pipeline signature dict with version and hash
            config_snapshot: Key configuration settings for this run
        """
        self.run_dir.mkdir(parents=True, exist_ok=True)

        metadata = {
            "run_id": self.run_id,
            "start_time": datetime.now().isoformat(),
            "pipeline_signature": pipeline_signature,
            "status": "running",
            "config_snapshot": config_snapshot
        }

        metadata_path = self.run_dir / "00_run_metadata.json"
        metadata_path.write_text(json.dumps(metadata, indent=2))

    def create_step_logger(self, step_id: int, step_name: str, command: str, working_dir: str) -> Dict[str, Path]:
        """
        Create a step directory and return file paths for stdout/stderr/result.

        Args:
            step_id: Process ID from process_commands.yaml
            step_name: Human-readable step name
            command: Command being executed
            working_dir: Working directory for the command

        Returns:
            Dict with keys: stdout_path, stderr_path, result_path, step_dir
        """
        self.current_step_num += 1

        # Sanitize step name for filesystem
        safe_name = (step_name.lower()
                     .replace(" ", "_")
                     .replace("(", "")
                     .replace(")", "")
                     .replace("-", "_")
                     .replace("/", "_"))

        step_dir = self.run_dir / f"{self.current_step_num:02d}_step_{step_id}_{safe_name}"
        step_dir.mkdir(parents=True, exist_ok=True)

        # Write start metadata
        start_info = {
            "step_id": step_id,
            "step_name": step_name,
            "start_time": datetime.now().isoformat(),
            "command": command,
            "working_dir": working_dir,
            "sequence": self.current_step_num
        }

        start_path = step_dir / "start.log"
        start_path.write_text(json.dumps(start_info, indent=2))

        return {
            "stdout_path": step_dir / "stdout.log",
            "stderr_path": step_dir / "stderr.log",
            "result_path": step_dir / "result.json",
            "step_dir": step_dir
        }

    def finalize_run(self, success: bool, summary_data: Dict[str, Any]) -> None:
        """
        Write final summary and rename directory with status.

        Args:
            success: Whether the run completed successfully
            summary_data: Summary statistics (steps_completed, steps_failed, etc.)
        """
        summary_data.update({
            "end_time": datetime.now().isoformat(),
            "status": "completed" if success else "failed"
        })

        summary_path = self.run_dir / "run_summary.json"
        summary_path.write_text(json.dumps(summary_data, indent=2))

        # Rename directory to include status
        status_suffix = "completed" if success else "failed"
        new_dir = self.run_dir.parent / f"{self.run_id}_{status_suffix}"

        # Handle case where directory already exists (shouldn't happen, but be safe)
        if new_dir.exists():
            import time
            timestamp = int(time.time())
            new_dir = self.run_dir.parent / f"{self.run_id}_{status_suffix}_{timestamp}"

        self.run_dir.rename(new_dir)
        self.run_dir = new_dir  # Update internal reference

    def write_step_result(self, step_id: int, step_name: str, success: bool,
                         exit_code: int, duration_seconds: float, attempts: int,
                         error_message: Optional[str], result_path: Path) -> None:
        """
        Write step result.json file.

        Args:
            step_id: Process ID
            step_name: Step name
            success: Whether step succeeded
            exit_code: Process exit code
            duration_seconds: Execution duration
            attempts: Number of retry attempts
            error_message: Error message if failed
            result_path: Path to result.json file
        """
        result_data = {
            "step_id": step_id,
            "step_name": step_name,
            "success": success,
            "exit_code": exit_code,
            "duration_seconds": duration_seconds,
            "attempts": attempts,
            "error_message": error_message,
            "end_time": datetime.now().isoformat()
        }

        result_path.write_text(json.dumps(result_data, indent=2))
