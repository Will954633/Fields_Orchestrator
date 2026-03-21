#!/usr/bin/env python3
""" 
Task Executor Module for Fields Orchestrator

Last Updated: 15/02/2026, 9:11 PM (Saturday) - Brisbane
- CRITICAL FIX: Pass MONGODB_URI environment variable to subprocesses
  Subprocesses don't automatically inherit environment variables from systemd service,
  so we must explicitly pass them. This fixes the "127.0.0.1:27017 connection refused"
  issue where scraping scripts couldn't connect to Cosmos DB.

Previous: 10/02/2026, 7:33 AM (Tuesday) - Brisbane
- CRITICAL FIX: Added _resolve_env_vars() to expand ${VAR_NAME} patterns in
  settings.yaml values. The MongoDB URI "${COSMOS_CONNECTION_STRING}" was being
  passed as a literal string to SoldMover, Verifier, and FieldChangeTracker,
  causing all of them to fail with "Name or service not known" errors.

Previous: 06/02/2026, 3:15 PM (Friday) - Brisbane
- CRITICAL FIX: Added PYTHONUNBUFFERED=1 to subprocess environment to fix
  multiprocessing stdout buffering issue that caused "hang" appearance
- Added sys.stdout/stderr flush forcing for child processes
- Added per-process cleanup of Chrome/ChromeDriver after each browser step
- Added heartbeat logging every 60 seconds during process execution
- Root cause: Python multiprocessing child processes buffer stdout when
  launched via subprocess.Popen(stdout=PIPE), making the orchestrator
  think the process is hung when it's actually working fine

Previous Updates:
- 04/02/2026, 7:17 AM (Tuesday) - Brisbane
- Integrated schedule_manager for day-based process filtering
- Processes are now filtered based on target market schedule (daily vs weekly)
- Added schedule summary logging at pipeline start

Previous Updates:
- 30/01/2026, 9:11 AM (Thursday) - Brisbane
- Added support for `enabled` flag in process configuration
- Processes with `enabled: false` are now skipped during pipeline execution
- Used to disable Process 9 (Floor Plan V2) which breaks interactive floor plans

Previous Updates (descending):
- 28/01/2026, 6:37 PM (Wednesday) - Brisbane
  - Added RUN_ID + pipeline signature logging
  - Added daily incremental artifacts: `state/for_sale_snapshot.json`, `state/current_run_candidates.json`, `state/last_run_summary.json`
  - Added sold migration hook (copy to sold then delete from for_sale)
  - Added per-property verifier hook (writes `orchestrator.processing.steps.*` verification results)
  - Added change-history tracker for price/inspections/agent description under `orchestrator.history.*`
- 28/01/2026, 04:15 PM (Wednesday) - Brisbane
  - Stream subprocess stdout/stderr to orchestrator logger while steps run (prevents long steps looking "stuck")
  - Run each step in its own process group and terminate the whole group on timeout (prevents orphan child processes)
- 27/01/2026, 10:46 AM (Monday) - Brisbane
  - Added unknown status detection after Phase 2 completes
  - Takes snapshot before Phase 2 begins
  - Detects properties with unknown status after Phase 2

Executes the property data collection pipeline steps in sequence.
Handles process execution, retries, cooldowns, and progress tracking.
"""

import os
import re
import signal
import subprocess
import time
import selectors
import yaml
from datetime import datetime
from pathlib import Path
from typing import Optional, List, Dict, Any, Callable
from dataclasses import dataclass, field

from .logger import get_logger, log_step_start, log_step_complete, log_pipeline_start, log_pipeline_complete
from .mongodb_monitor import MongoDBMonitor
from .unknown_status_detector import UnknownStatusDetector
from .run_context import RunContext, generate_run_id
from .pipeline_signature import compute_pipeline_signature
from .sold_mover import SoldMover
from .property_processing_verifier import PropertyProcessingVerifier
from .daily_incremental import write_for_sale_snapshot, compute_candidate_sets
from .field_change_tracker import FieldChangeTracker
from .property_change_detector import PropertyChangeDetector
from .schedule_manager import ScheduleManager
try:
    from shared.monitor_client import MonitorClient as _MonitorClient
    _MONITOR_AVAILABLE = True
except ImportError:
    _MONITOR_AVAILABLE = False
    _MonitorClient = None

try:
    from .auto_triage import triage_step as _triage_step, TA as _TA
    _TRIAGE_AVAILABLE = True
except ImportError:
    _TRIAGE_AVAILABLE = False

# Import process failures logger
import sys
sys.path.append(str(Path(__file__).parent.parent / "01_Debug_Log"))
try:
    from process_failures_logger import log_process_failure
    PROCESS_LOGGING_ENABLED = True
except ImportError:
    PROCESS_LOGGING_ENABLED = False
    def log_process_failure(*args, **kwargs):
        pass  # No-op if logger not available


@dataclass
class ProcessConfig:
    """Configuration for a single process step."""
    id: int
    name: str
    description: str
    phase: str
    command: str
    working_dir: str
    mongodb_activity: str  # "heavy_write" or "moderate_write"
    requires_browser: bool
    estimated_duration_minutes: int
    cooldown_seconds: int
    depends_on: List[int] = field(default_factory=list)
    enabled: bool = True  # Allow processes to be disabled


@dataclass
class StepResult:
    """Result of executing a single step."""
    step_id: int
    step_name: str
    success: bool
    duration_seconds: float
    start_time: datetime
    end_time: datetime
    attempts: int
    error_message: Optional[str] = None
    output: Optional[str] = None


class TaskExecutor:
    """
    Executes the property data collection pipeline.
    
    This class handles:
    - Loading process configurations from YAML
    - Executing processes in sequence
    - Retrying failed processes
    - Managing cooldown periods between processes
    - Tracking progress and results
    """
    
    def __init__(
        self,
        config_path: Optional[str] = None,
        mongodb_monitor: Optional[MongoDBMonitor] = None,
        max_retries: int = 2,
        retry_delay: int = 60,
        progress_callback: Optional[Callable[[int, str, str], None]] = None
    ):
        """
        Initialize the task executor.
        
        Args:
            config_path: Path to process_commands.yaml
            mongodb_monitor: MongoDB monitor instance for cooldowns
            max_retries: Maximum retries per step (default 2)
            retry_delay: Delay between retries in seconds
            progress_callback: Callback function for progress updates
                              (step_id, step_name, status)
        """
        self.logger = get_logger()
        self.max_retries = max_retries
        self.retry_delay = retry_delay
        self.progress_callback = progress_callback
        
        # Load process configurations
        if config_path is None:
            config_path = Path(__file__).parent.parent / "config" / "process_commands.yaml"
        self.processes = self._load_processes(config_path)
        
        # MongoDB monitor for cooldowns
        self.mongodb_monitor = mongodb_monitor or MongoDBMonitor()
        
        # Schedule manager for day-based filtering
        self.schedule_manager = ScheduleManager()
        
        # Track results
        self.results: List[StepResult] = []
        self.is_running = False
        self.current_step: Optional[int] = None
        self.pipeline_start_time: Optional[datetime] = None
    
    def _load_processes(self, config_path: str) -> List[ProcessConfig]:
        """Load process configurations from YAML file."""
        config_path = Path(config_path)
        
        if not config_path.exists():
            self.logger.error(f"Process config not found: {config_path}")
            return []
        
        try:
            with open(config_path, 'r') as f:
                config = yaml.safe_load(f)
            
            processes = []
            for proc in config.get('processes', []):
                processes.append(ProcessConfig(
                    id=proc['id'],
                    name=proc['name'],
                    description=proc.get('description', ''),
                    phase=proc['phase'],
                    command=proc['command'],
                    working_dir=proc['working_dir'],
                    mongodb_activity=proc.get('mongodb_activity', 'moderate_write'),
                    requires_browser=proc.get('requires_browser', False),
                    estimated_duration_minutes=proc.get('estimated_duration_minutes', 30),
                    cooldown_seconds=proc.get('cooldown_seconds', 180),
                    depends_on=proc.get('depends_on', []),
                    enabled=proc.get('enabled', True)  # Default to enabled if not specified
                ))
            
            # Sort by execution order
            execution_order = config.get('execution_order', [p.id for p in processes])
            processes.sort(key=lambda p: execution_order.index(p.id) if p.id in execution_order else 999)
            
            self.logger.info(f"Loaded {len(processes)} process configurations")
            return processes
            
        except Exception as e:
            self.logger.error(f"Failed to load process config: {e}")
            return []
    
    def _notify_progress(self, step_id: int, step_name: str, status: str) -> None:
        """Send progress notification via callback."""
        if self.progress_callback:
            try:
                self.progress_callback(step_id, step_name, status)
            except Exception as e:
                self.logger.warning(f"Progress callback failed: {e}")
    
    def _execute_process(self, process: ProcessConfig, run_logger=None, step_paths=None) -> tuple[bool, str, str]:
        """
        Execute a single process.

        Args:
            process: Process configuration
            run_logger: Optional RunLogger for per-run logging
            step_paths: Optional dict with stdout_path, stderr_path, result_path

        Returns:
            Tuple of (success, stdout, stderr)
        """
        self.logger.info(f"Executing: {process.command}")
        self.logger.info(f"Working directory: {process.working_dir}")

        # Check if working directory exists
        if not os.path.isdir(process.working_dir):
            return False, "", f"Working directory does not exist: {process.working_dir}"

        timeout_seconds = process.estimated_duration_minutes * 60 * 2  # 2x estimated time as hard timeout

        # Open per-step log files if step_paths provided
        stdout_file = None
        if step_paths:
            stdout_file = open(step_paths["stdout_path"], "w", buffering=1)  # Line buffered

        # NOTE:
        # We intentionally stream output while the process is running so the orchestrator log keeps updating.
        # We also run the subprocess in its own process group so that on timeout we can kill the whole group.
        #
        # CRITICAL FIX (06/02/2026): Set PYTHONUNBUFFERED=1 in the subprocess environment.
        # Without this, Python's multiprocessing child processes buffer their stdout when
        # launched via subprocess.Popen(stdout=PIPE). This makes the orchestrator think the
        # process is "hung" when it's actually working fine - the output is just stuck in
        # a buffer. This was the root cause of the "scraping hang" issue.
        #
        # WHY IT WORKED WHEN RUN DIRECTLY: When you run `python3 run_dynamic_10_suburbs.py`
        # from a terminal, stdout is a TTY and Python uses line-buffering. When the orchestrator
        # runs it via Popen(stdout=PIPE), stdout is a pipe and Python switches to full buffering
        # (typically 8KB). The multiprocessing child processes inherit this buffered pipe, so
        # their print() output never reaches the orchestrator until the buffer fills or the
        # process exits.
        try:
            # Build environment with PYTHONUNBUFFERED to force line-buffered output
            # CRITICAL FIX (15/02/2026): Also pass MONGODB_URI from COSMOS_CONNECTION_STRING
            # Subprocesses don't automatically inherit environment variables from systemd service,
            # so we must explicitly pass them. This fixes the "127.0.0.1:27017 connection refused" issue.
            env = os.environ.copy()
            env['PYTHONUNBUFFERED'] = '1'  # Forces unbuffered stdout/stderr for Python subprocesses

            # Activate venv by prepending its bin dir to PATH so all `python3` calls
            # use the venv (which has openai, pandas, azure, etc. installed).
            venv_bin = '/home/fields/venv/bin'
            if os.path.isdir(venv_bin):
                env['PATH'] = venv_bin + ':' + env.get('PATH', '')
                env['VIRTUAL_ENV'] = '/home/fields/venv'

            # Pass MongoDB connection string to subprocess
            # Try COSMOS_CONNECTION_STRING first (systemd service), then MONGODB_URI (shell)
            cosmos_uri = os.getenv('COSMOS_CONNECTION_STRING')
            mongodb_uri = os.getenv('MONGODB_URI')
            if cosmos_uri:
                env['MONGODB_URI'] = cosmos_uri
                env['COSMOS_CONNECTION_STRING'] = cosmos_uri  # Some scripts read this directly
                self.logger.debug(f"Passing MONGODB_URI + COSMOS_CONNECTION_STRING to subprocess")
            elif mongodb_uri:
                env['MONGODB_URI'] = mongodb_uri
                self.logger.debug(f"Passing MONGODB_URI to subprocess (from MONGODB_URI)")
            else:
                self.logger.warning("No COSMOS_CONNECTION_STRING or MONGODB_URI found in environment!")

            # Pass Azure Blob Storage connection string to subprocess (for process 110)
            azure_conn = os.getenv('AZURE_STORAGE_CONNECTION_STRING')
            if azure_conn:
                env['AZURE_STORAGE_CONNECTION_STRING'] = azure_conn
                self.logger.debug("Passing AZURE_STORAGE_CONNECTION_STRING to subprocess")
            else:
                self.logger.debug("AZURE_STORAGE_CONNECTION_STRING not set (only needed for process 110)")

            proc = subprocess.Popen(
                process.command,
                shell=True,
                cwd=process.working_dir,
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                text=True,
                bufsize=1,
                universal_newlines=True,
                start_new_session=True,  # new process group/session (prevents orphan children)
                env=env  # CRITICAL: Pass environment with PYTHONUNBUFFERED=1 and MONGODB_URI
            )

            stdout_lines: List[str] = []
            start_time = time.time()
            last_heartbeat = time.time()
            last_output_time = time.time()

            sel = selectors.DefaultSelector()
            if proc.stdout is not None:
                sel.register(proc.stdout, selectors.EVENT_READ)

            # Stream output line-by-line and enforce our own timeout.
            while True:
                now = time.time()
                
                # Heartbeat logging every 60 seconds when no output received
                if (now - last_heartbeat) >= 60:
                    elapsed = now - start_time
                    silence = now - last_output_time
                    self.logger.info(
                        f"[STEP {process.id} HEARTBEAT] Running for {elapsed/60:.1f} min | "
                        f"No output for {silence:.0f}s | PID: {proc.pid} | "
                        f"Timeout in {(timeout_seconds - elapsed)/60:.1f} min"
                    )
                    last_heartbeat = now
                
                # Timeout check
                if (now - start_time) > timeout_seconds:
                    error_msg = f"Process timed out after {timeout_seconds/60:.0f} minutes (limit: {process.estimated_duration_minutes}m estimated × 2)"
                    self.logger.error(error_msg)
                    
                    # Log to debug system
                    if PROCESS_LOGGING_ENABLED:
                        log_process_failure(
                            step_id=process.id,
                            step_name=process.name,
                            error_type="step_timeout",
                            error_message=error_msg,
                            additional_info={
                                "timeout_seconds": timeout_seconds,
                                "estimated_minutes": process.estimated_duration_minutes
                            }
                        )

                    try:
                        # Kill entire process group
                        os.killpg(proc.pid, signal.SIGTERM)
                    except Exception:
                        pass

                    # Give it a moment to exit cleanly, then SIGKILL
                    try:
                        proc.wait(timeout=10)
                    except Exception:
                        try:
                            os.killpg(proc.pid, signal.SIGKILL)
                        except Exception:
                            pass

                    return False, "", "Process timed out"

                # Non-blocking wait for output
                events = sel.select(timeout=0.5)
                for key, _ in events:
                    stream = key.fileobj
                    try:
                        line = stream.readline()
                    except Exception:
                        line = ""

                    if line:
                        line_stripped = line.rstrip("\n")
                        stdout_lines.append(line_stripped)
                        self.logger.info(f"[STEP {process.id} OUTPUT] {line_stripped}")
                        # Also write to per-step log file
                        if stdout_file:
                            stdout_file.write(line_stripped + "\n")
                            stdout_file.flush()
                        last_output_time = time.time()

                # Process status
                if proc.poll() is not None:
                    break

            # Drain remaining output
            if proc.stdout is not None:
                for remaining in proc.stdout.read().splitlines():
                    stdout_lines.append(remaining)
                    self.logger.info(f"[STEP {process.id} OUTPUT] {remaining}")

            try:
                sel.close()
            except Exception:
                pass

            rc = proc.returncode if proc.returncode is not None else 1
            stdout_text = "\n".join(stdout_lines)

            success = rc == 0
            if not success:
                self.logger.error(f"Process failed with return code {rc}")

            # Close per-step log file
            if stdout_file:
                stdout_file.close()

            # stderr is merged into stdout in streaming mode
            return success, stdout_text, ""

        except Exception as e:
            error_msg = f"Process execution failed: {e}"
            self.logger.error(error_msg)
            
            # Log to debug system
            if PROCESS_LOGGING_ENABLED:
                log_process_failure(
                    step_id=process.id,
                    step_name=process.name,
                    error_type="execution_exception",
                    error_message=str(e)
                )
            
            return False, "", str(e)
    
    def _step_lock_path(self, step_id: int) -> Path:
        return Path(f"/tmp/fields_step_{step_id}.lock")

    def _acquire_step_lock(self, step_id: int) -> bool:
        """Acquire a file-based lock for a step. Returns False if already running."""
        lock = self._step_lock_path(step_id)
        if lock.exists():
            try:
                content = lock.read_text().strip().split("\n")
                pid = int(content[0])
                os.kill(pid, 0)  # Check if PID is alive
                self.logger.warning(f"Step {step_id} already running (PID {pid}) — skipping duplicate")
                return False
            except (ProcessLookupError, ValueError, IndexError):
                self.logger.info(f"Removing stale lock for step {step_id}")
                lock.unlink(missing_ok=True)
        lock.write_text(f"{os.getpid()}\n{datetime.now().isoformat()}\n")
        return True

    def _release_step_lock(self, step_id: int) -> None:
        self._step_lock_path(step_id).unlink(missing_ok=True)

    def execute_step(self, process: ProcessConfig, run_logger=None) -> StepResult:
        """
        Execute a single step with retries.

        Args:
            process: Process configuration
            run_logger: Optional RunLogger for per-run logging

        Returns:
            StepResult with execution details
        """
        # Prevent duplicate step execution
        if not self._acquire_step_lock(process.id):
            return StepResult(
                step_id=process.id,
                step_name=process.name,
                success=False,
                start_time=datetime.now(),
                end_time=datetime.now(),
                duration_seconds=0,
                attempts=0,
                output="",
                error_message=f"Step {process.id} already running (duplicate prevented)",
            )

        log_step_start(process.id, process.name)
        self._notify_progress(process.id, process.name, "running")

        # Create step logger if run_logger provided
        step_paths = None
        if run_logger:
            step_paths = run_logger.create_step_logger(
                step_id=process.id,
                step_name=process.name,
                command=process.command,
                working_dir=process.working_dir
            )

        start_time = datetime.now()
        attempts = 0
        success = False
        error_message = None
        output = None

        # MonitorClient — record step start
        _monitor = None
        if _MONITOR_AVAILABLE:
            try:
                _monitor = _MonitorClient(
                    system="orchestrator",
                    pipeline="orchestrator_daily",
                    process_id=str(process.id),
                    process_name=process.name,
                )
                _monitor.start()
            except Exception:
                _monitor = None

        # Try up to max_retries + 1 times
        for attempt in range(self.max_retries + 1):
            attempts = attempt + 1

            if attempt > 0:
                self.logger.warning(f"Retry attempt {attempt}/{self.max_retries}")
                self._notify_progress(process.id, process.name, f"retrying ({attempt}/{self.max_retries})")
                time.sleep(self.retry_delay)

            success, stdout, stderr = self._execute_process(process, run_logger=run_logger, step_paths=step_paths)
            output = stdout
            error_message = stderr if not success else None
            
            if success:
                break
        
        end_time = datetime.now()
        duration = (end_time - start_time).total_seconds()

        result = StepResult(
            step_id=process.id,
            step_name=process.name,
            success=success,
            duration_seconds=duration,
            start_time=start_time,
            end_time=end_time,
            attempts=attempts,
            error_message=error_message,
            output=output
        )

        # Write result.json if run_logger provided
        if run_logger and step_paths:
            run_logger.write_step_result(
                step_id=process.id,
                step_name=process.name,
                success=success,
                exit_code=0 if success else 1,
                duration_seconds=duration,
                attempts=attempts,
                error_message=error_message,
                result_path=step_paths["result_path"]
            )

        log_step_complete(process.id, process.name, duration, success)

        # MonitorClient — record step completion
        if _monitor is not None:
            try:
                if error_message:
                    _monitor.log_error(error_message, file=process.command.split()[0] if process.command else "unknown")
                _monitor.log_metric("attempts", attempts)
                _monitor.log_metric("duration_seconds", round(duration, 1))
                _monitor.finish(status="success" if success else "failed")
            except Exception:
                pass

        # Auto-triage on step failure: classify root cause, queue the right repair
        if not success and _TRIAGE_AVAILABLE:
            try:
                _decision = _triage_step(
                    step_id=process.id,
                    step_name=process.name,
                    stdout=output or "",
                    attempts=attempts,
                )
                _icons = {_TA.NONE: "🔕", _TA.PROCESS_RERUN: "🔄", _TA.ESCALATE: "🤖"}
                self.logger.info(
                    f"{_icons.get(_decision.action, '❓')} Triage [{process.id}] "
                    f"[{_decision.diagnostic.failure_class.upper()}] — {_decision.repair_note}"
                )
                if _decision.request_id:
                    self.logger.info(
                        f"   ↳ Repair queued: {_decision.request_id} "
                        f"(action={_decision.action})"
                    )
                # Write triage result onto the process_runs document so the
                # ops dashboard can surface it in the expanded step view.
                if _monitor is not None and _monitor._run_id is not None:
                    try:
                        _d = _decision.diagnostic
                        _monitor._get_collection("process_runs").update_one(
                            {"_id": _monitor._run_id},
                            {"$set": {"triage": {
                                "failure_class": _d.failure_class,
                                "cause":         _d.cause,
                                "root_step":     _d.root_step,
                                "action":        _decision.action,
                                "suggested_actions": _d.suggested_actions,
                                "auto_fixable":  _d.auto_fixable,
                                "request_id":    _decision.request_id,
                            }}}
                        )
                    except Exception:
                        pass  # Never break the pipeline over a monitoring write
            except Exception as _te:
                self.logger.warning(f"Auto-triage error for step {process.id}: {_te}")

        status = "completed" if success else "failed"
        self._notify_progress(process.id, process.name, status)

        self._release_step_lock(process.id)
        return result
    
    def execute_pipeline(self) -> Dict[str, Any]:
        """
        Execute the entire pipeline.
        
        Returns:
            Dictionary with pipeline execution results
        """
        if self.is_running:
            self.logger.warning("Pipeline is already running")
            return {"success": False, "error": "Pipeline already running"}
        
        self.is_running = True
        self.results = []
        self.pipeline_start_time = datetime.now()

        base_dir = Path(__file__).parent.parent
        run_id = generate_run_id(self.pipeline_start_time)
        run_ctx = RunContext(run_id=run_id, base_dir=base_dir)
        pipeline_sig = compute_pipeline_signature(base_dir=base_dir, version=2)

        # Initialize per-run logging
        from run_logger import RunLogger
        from dataclasses import asdict
        run_logger = RunLogger(
            run_id=run_id,
            base_logs_dir=base_dir / "logs"
        )
        run_logger.initialize_run(
            pipeline_signature=asdict(pipeline_sig),
            config_snapshot={
                "max_retries": self.max_retries,
                "total_processes": len(self.processes)
            }
        )

        log_pipeline_start()
        self.logger.info(f"RUN_ID: {run_id}")
        self.logger.info(f"PIPELINE_SIGNATURE: {pipeline_sig.signature} (version={pipeline_sig.version})")
        self.logger.info(f"RUN_LOG_DIR: {run_logger.run_dir}")
        
        # Log schedule summary
        schedule_summary = self.schedule_manager.get_schedule_summary()
        self.logger.info("\n" + "="*60)
        self.logger.info("📅 SCHEDULE SUMMARY")
        self.logger.info("="*60)
        self.logger.info(f"Date: {schedule_summary['date']} ({schedule_summary['day_of_week']})")
        self.logger.info(f"Target Market: {'✅ Running' if schedule_summary['target_market_runs'] else '⏭️  Skipped'}")
        self.logger.info(f"Other Suburbs: {'✅ Running' if schedule_summary['other_suburbs_runs'] else '⏭️  Skipped'}")
        self.logger.info(f"Processes to run: {schedule_summary['processes_to_run']}")
        self.logger.info(f"Total processes: {schedule_summary['process_counts']['total']}")
        self.logger.info("="*60 + "\n")
        
        # Check MongoDB connection first
        if not self.mongodb_monitor.wait_for_connection():
            self.is_running = False
            return {
                "success": False,
                "error": "Could not connect to MongoDB",
                "steps_completed": 0,
                "steps_failed": 0
            }
        
        # Log MongoDB status
        self.mongodb_monitor.log_status()

        # Load MongoDB URI from settings (needed for all MongoDB components)
        settings_path = base_dir / "config" / "settings.yaml"
        mongo_uri = "mongodb://127.0.0.1:27017/"
        mongo_db = "property_data"
        try:
            if settings_path.exists():
                with open(settings_path, "r") as f:
                    settings = yaml.safe_load(f) or {}
                mongo_uri_raw = settings.get("mongodb", {}).get("uri", mongo_uri)
                mongo_db = settings.get("mongodb", {}).get("database", mongo_db)

                # Resolve environment variables in URI (e.g. "${COSMOS_CONNECTION_STRING}")
                # YAML doesn't do shell variable expansion, so we need to do it in Python
                def _resolve_env_vars(value: str) -> str:
                    if not isinstance(value, str):
                        return value
                    def replace_var(match):
                        var_name = match.group(1) or match.group(2)
                        env_value = os.environ.get(var_name, '')
                        if not env_value:
                            self.logger.warning(f"Environment variable '{var_name}' is not set")
                        return env_value
                    return re.sub(r'\$\{([^}]+)\}|\$([A-Za-z_][A-Za-z0-9_]*)', replace_var, value)

                mongo_uri = _resolve_env_vars(mongo_uri_raw)
                self.logger.info(f"MongoDB URI resolved (starts with: {mongo_uri[:30]}...)")
        except Exception as e:
            self.logger.warning(f"Failed to load settings: {e}")

        # Load target suburbs for unknown status detection and daily incremental
        _target_suburbs_slugs: List[str] = []
        try:
            _settings_for_suburbs = yaml.safe_load(open(settings_path)) or {} if settings_path.exists() else {}
            _suburbs_raw = _settings_for_suburbs.get("target_market", {}).get("suburbs", [])
            _target_suburbs_slugs = [s.split(":")[0].strip().lower().replace(" ", "_") for s in _suburbs_raw]
        except Exception as e:
            self.logger.warning(f"Failed to load target suburbs for unknown status detection: {e}")

        # Initialize all MongoDB components with correct URI
        unknown_detector = UnknownStatusDetector(
            mongodb_uri=mongo_uri,
            for_sale_db="Gold_Coast",
            target_suburbs=_target_suburbs_slugs,
        )
        unknown_detector.connect_mongodb()

        sold_mover = SoldMover(mongo_uri=mongo_uri, database=mongo_db)
        verifier = PropertyProcessingVerifier(
            mongo_uri=mongo_uri,
            database=mongo_db,
            pipeline_version=pipeline_sig.version,
            pipeline_signature=pipeline_sig.signature,
            # IMPORTANT: conservative rollout: write verification results but do not mark complete yet.
            dry_run=False,
            write_verification_results=True,
            mark_complete=False,
        )
        field_tracker = FieldChangeTracker(mongo_uri=mongo_uri, database=mongo_db)
        change_detector = PropertyChangeDetector(mongo_uri=mongo_uri, database=mongo_db)
        sold_mover.connect()
        verifier.connect()
        field_tracker.connect()
        change_detector.connect()
        
        steps_completed = 0
        steps_failed = 0
        phase2_started = False
        phase2_completed = False

        run_summary: Dict[str, Any] = {
            "counts": {
                "steps_completed": 0,
                "steps_failed": 0,
                "sold_moved": 0,
                "sold_deleted_from_for_sale": 0,
                "verifier_examined": 0,
                "verifier_complete": 0,
                "verifier_incomplete": 0,
                "field_tracker_examined": 0,
                "field_tracker_updated": 0,
                "change_detector_examined": 0,
                "change_detector_with_changes": 0,
                "change_detector_total_changes": 0,
                "change_detector_new_properties": 0,
                "change_detector_removed_properties": 0,
            },
            "pipeline_signature": {"version": pipeline_sig.version, "signature": pipeline_sig.signature},
        }
        
        try:
            # Get processes that should run today
            processes_to_run = set(self.schedule_manager.get_processes_to_run())
            
            for i, process in enumerate(self.processes):
                # Skip disabled processes
                if not process.enabled:
                    self.logger.info(f"\n{'='*60}")
                    self.logger.info(f"STEP {i+1}/{len(self.processes)}: {process.name} - SKIPPED (disabled)")
                    self.logger.info(f"{'='*60}\n")
                    continue
                
                # Skip processes not scheduled for today
                if process.id not in processes_to_run:
                    self.logger.info(f"\n{'='*60}")
                    self.logger.info(f"STEP {i+1}/{len(self.processes)}: {process.name} - SKIPPED (not scheduled for today)")
                    self.logger.info(f"{'='*60}\n")
                    continue
                
                # Check depends_on: skip if any dependency failed this run
                if process.depends_on:
                    failed_dep = None
                    for dep_id in process.depends_on:
                        dep_result = next((r for r in self.results if r.step_id == dep_id), None)
                        # If dependency ran this run and failed, block this step
                        if dep_result is not None and not dep_result.success:
                            failed_dep = dep_id
                            break
                    if failed_dep is not None:
                        dep_name = next((p.name for p in self.processes if p.id == failed_dep), str(failed_dep))
                        self.logger.warning(f"\n{'='*60}")
                        self.logger.warning(f"STEP {i+1}/{len(self.processes)}: {process.name} - SKIPPED (dependency {dep_name} [step {failed_dep}] failed this run)")
                        self.logger.warning(f"{'='*60}\n")
                        steps_failed += 1
                        continue

                self.current_step = process.id

                # Take snapshot before Phase 2 begins (for_sale or for_sale_target)
                if process.phase in ("for_sale", "for_sale_target", "for_sale_other") and not phase2_started:
                    # Daily snapshot + candidate generation (used by downstream scripts once they accept filters)
                    try:
                        write_for_sale_snapshot(
                            base_dir=base_dir,
                            mongo_uri=mongo_uri,
                            database=mongo_db,
                            for_sale_database="Gold_Coast",
                            target_suburbs=_target_suburbs_slugs,
                        )
                        candidate_sets = compute_candidate_sets(
                            base_dir=base_dir,
                            mongo_uri=mongo_uri,
                            database=mongo_db,
                            pipeline_signature={"version": pipeline_sig.version, "signature": pipeline_sig.signature},
                            for_sale_database="Gold_Coast",
                            target_suburbs=_target_suburbs_slugs,
                        )
                        run_ctx.write_candidate_sets(
                            {
                                "new": candidate_sets.new_addresses,
                                "incomplete": candidate_sets.incomplete_addresses,
                                "stale": candidate_sets.stale_addresses,
                                "candidates": candidate_sets.all_candidates,
                                "counts": {
                                    "new": len(candidate_sets.new_addresses),
                                    "incomplete": len(candidate_sets.incomplete_addresses),
                                    "stale": len(candidate_sets.stale_addresses),
                                    "candidates": len(candidate_sets.all_candidates),
                                },
                            }
                        )
                        run_summary["candidate_sets"] = {
                            "counts": {
                                "new": len(candidate_sets.new_addresses),
                                "incomplete": len(candidate_sets.incomplete_addresses),
                                "stale": len(candidate_sets.stale_addresses),
                                "candidates": len(candidate_sets.all_candidates),
                            }
                        }
                    except Exception as e:
                        self.logger.warning(f"Failed to write snapshot/candidates: {e}")

                    self.logger.info("\n" + "="*60)
                    self.logger.info("📸 Taking Pre-Phase 2 Snapshot")
                    self.logger.info("="*60 + "\n")
                    unknown_detector.take_pre_phase2_snapshot()

                    # NEW: Take property change detection snapshot BEFORE scraping
                    self.logger.info("\n" + "="*60)
                    self.logger.info("📸 Taking Property Change Detection Snapshot")
                    self.logger.info("="*60 + "\n")
                    try:
                        # Load settings to get target suburbs
                        settings_path = base_dir / "config" / "settings.yaml"
                        target_suburbs = []
                        if settings_path.exists():
                            with open(settings_path, "r") as f:
                                settings = yaml.safe_load(f) or {}
                            target_suburbs_config = settings.get("target_market", {}).get("suburbs", [])
                            target_suburbs = [s.split(":")[0].lower().replace(" ", "_") for s in target_suburbs_config]

                        if target_suburbs:
                            snapshot_count = change_detector.create_snapshot(
                                suburbs=target_suburbs,
                                run_id=run_id
                            )
                            self.logger.info(f"✅ Snapshot created: {snapshot_count} properties across {len(target_suburbs)} suburbs")
                        else:
                            self.logger.warning("⚠️  No target suburbs configured for change detection")
                    except Exception as e:
                        self.logger.error(f"❌ Failed to create change detection snapshot: {e}")
                        import traceback
                        self.logger.error(traceback.format_exc())

                    phase2_started = True
                
                self.logger.info(f"\n{'='*60}")
                self.logger.info(f"STEP {i+1}/{len(self.processes)}: {process.name}")
                self.logger.info(f"Phase: {process.phase}")
                self.logger.info(f"{'='*60}\n")
                
                # Execute the step
                result = self.execute_step(process, run_logger=run_logger)
                self.results.append(result)
                
                if result.success:
                    steps_completed += 1
                else:
                    steps_failed += 1
                    self.logger.warning(f"Step {process.id} failed after {result.attempts} attempts")

                # Kill leftover Chrome processes after any browser-using step
                if process.requires_browser:
                    self.logger.info(f"Post-step cleanup: killing Chrome processes after step {process.id}")
                    import subprocess as _cleanup_sp
                    for _pat in ['chromedriver', 'chrome_crashpad', 'chromium', 'chrome']:
                        _cleanup_sp.run(['pkill', '-9', '-f', _pat],
                                        capture_output=True, text=True, timeout=10)
                    # Wait for processes to fully exit before next step tries to launch Chrome
                    time.sleep(3)
                    # Clean up Chrome temp dirs that accumulate and cause SessionNotCreatedException
                    import glob as _cleanup_glob
                    import shutil as _cleanup_shutil
                    for _pattern in ['/tmp/.com.google.Chrome*', '/tmp/chrome_crashpad_*',
                                     '/tmp/.org.chromium.*', '/tmp/chromium-*']:
                        for _tmp in _cleanup_glob.glob(_pattern):
                            _cleanup_shutil.rmtree(_tmp, ignore_errors=True)
                    # Verify no chrome processes remain
                    _check = _cleanup_sp.run(['pgrep', '-c', '-f', 'chrome'],
                                             capture_output=True, text=True, timeout=5)
                    _remaining = int(_check.stdout.strip()) if _check.stdout.strip() and _check.returncode == 0 else 0
                    if _remaining > 0:
                        self.logger.warning(f"  {_remaining} Chrome processes still alive — force kill + 5s wait")
                        time.sleep(5)
                        for _pat in ['chromedriver', 'chrome_crashpad', 'chromium', 'chrome']:
                            _cleanup_sp.run(['pkill', '-9', '-f', _pat],
                                            capture_output=True, text=True, timeout=10)
                    else:
                        self.logger.info(f"  Chrome cleanup OK — 0 processes remaining")

                run_summary["counts"]["steps_completed"] = steps_completed
                run_summary["counts"]["steps_failed"] = steps_failed

                # Check if Phase 2 just completed
                if process.phase in ("for_sale", "for_sale_target", "for_sale_other") and phase2_started:
                    # Check if next ENABLED process is not for_sale (meaning Phase 2 is done)
                    # Look ahead to find the next enabled process (skip disabled/skipped ones)
                    next_phase = None
                    for j in range(i + 1, len(self.processes)):
                        next_proc = self.processes[j]
                        if next_proc.enabled and next_proc.id in set(self.schedule_manager.get_processes_to_run()):
                            next_phase = next_proc.phase
                            break

                    if next_phase is None or next_phase not in ("for_sale", "for_sale_target", "for_sale_other"):
                        phase2_completed = True
                        
                        # Run unknown status detection
                        self.logger.info("\n" + "="*60)
                        self.logger.info("🔍 Running Unknown Status Detection")
                        self.logger.info("="*60 + "\n")
                        
                        unknown_detector.run_detection()

                        # After for_sale phase completes, detect and record ALL property changes
                        try:
                            self.logger.info("\n" + "=" * 60)
                            self.logger.info("🔍 Detecting Property Changes (Comprehensive)")
                            self.logger.info("=" * 60 + "\n")

                            # Get target suburbs from config
                            settings_path = base_dir / "config" / "settings.yaml"
                            target_suburbs = []
                            if settings_path.exists():
                                with open(settings_path, "r") as f:
                                    settings = yaml.safe_load(f) or {}
                                target_suburbs_config = settings.get("target_market", {}).get("suburbs", [])
                                target_suburbs = [s.split(":")[0].lower().replace(" ", "_") for s in target_suburbs_config]

                            if target_suburbs:
                                change_summary = change_detector.detect_and_record_changes(
                                    run_id=run_id,
                                    suburbs=target_suburbs
                                )
                                run_summary["counts"]["change_detector_examined"] = change_summary.properties_examined
                                run_summary["counts"]["change_detector_with_changes"] = change_summary.properties_with_changes
                                run_summary["counts"]["change_detector_total_changes"] = change_summary.total_field_changes
                                run_summary["counts"]["change_detector_new_properties"] = change_summary.new_properties
                                run_summary["counts"]["change_detector_removed_properties"] = change_summary.removed_properties

                                self.logger.info(f"✅ Change detection complete:")
                                self.logger.info(f"   {change_summary.properties_examined} properties examined")
                                self.logger.info(f"   {change_summary.properties_with_changes} properties with changes")
                                self.logger.info(f"   {change_summary.total_field_changes} total field changes")
                                if change_summary.changes_by_field:
                                    self.logger.info(f"   Top changes: {dict(list(sorted(change_summary.changes_by_field.items(), key=lambda x: -x[1]))[:5])}")
                            else:
                                self.logger.warning("⚠️  No target suburbs configured for change detection")

                        except Exception as e:
                            self.logger.error(f"❌ Property change detection failed: {e}")
                            import traceback
                            self.logger.error(traceback.format_exc())
                        
                        # Add cooldown after detection
                        self.mongodb_monitor.start_cooldown(60, "after unknown status detection")

                        # Write scraper health + audit snapshot to MongoDB for OpsPage
                        import subprocess as _sp
                        for _snap_script in [
                            "/home/fields/Fields_Orchestrator/write-scraper-health.py",
                            "/home/fields/Fields_Orchestrator/write-audit-snapshot.py",
                        ]:
                            try:
                                self.logger.info(f"📊 Running {_snap_script.split('/')[-1]}")
                                _sp.run(
                                    ["python3", _snap_script],
                                    timeout=60,
                                    check=False,
                                    capture_output=True,
                                )
                            except Exception as _e:
                                self.logger.warning(f"Snapshot script failed (non-fatal): {_e}")
                
                # Apply cooldown after the step
                if i < len(self.processes) - 1:  # Don't cooldown after last step
                    cooldown_reason = f"after {process.name}"
                    self.mongodb_monitor.start_cooldown(process.cooldown_seconds, cooldown_reason)

                # After the monitoring step runs, immediately migrate any sold properties.
                if process.id == 1:
                    try:
                        self.logger.info("\n" + "=" * 60)
                        self.logger.info("🚚 Running Sold Mover (copy→sold then delete from for_sale)")
                        self.logger.info("=" * 60 + "\n")
                        sm_res = sold_mover.move_sold_properties(run_id=run_id)
                        run_summary["counts"]["sold_moved"] += sm_res.moved
                        run_summary["counts"]["sold_deleted_from_for_sale"] += sm_res.deleted_from_for_sale
                    except Exception as e:
                        self.logger.error(f"Sold mover failed: {e}")

                # After backend enrichment completes (step 15), verify per-property completeness.
                if process.id == 15:
                    try:
                        self.logger.info("\n" + "=" * 60)
                        self.logger.info("✅ Running Property Verifier (write results; mark_complete=false)")
                        self.logger.info("=" * 60 + "\n")
                        v_sum = verifier.verify_and_update(run_id=run_id)
                        run_summary["counts"]["verifier_examined"] += int(v_sum.get("examined", 0))
                        run_summary["counts"]["verifier_complete"] += int(v_sum.get("verified_complete", 0))
                        run_summary["counts"]["verifier_incomplete"] += int(v_sum.get("verified_incomplete", 0))
                    except Exception as e:
                        self.logger.error(f"Verifier failed: {e}")
            
        except KeyboardInterrupt:
            self.logger.warning("Pipeline interrupted by user")
        except Exception as e:
            self.logger.error(f"Pipeline failed with exception: {e}")
        finally:
            unknown_detector.disconnect_mongodb()
            try:
                verifier.close()
            except Exception:
                pass
            try:
                sold_mover.close()
            except Exception:
                pass
            try:
                field_tracker.close()
            except Exception:
                pass
            try:
                change_detector.close()
            except Exception:
                pass
            self.is_running = False
            self.current_step = None
        
        # Calculate total duration
        pipeline_end_time = datetime.now()
        total_duration = (pipeline_end_time - self.pipeline_start_time).total_seconds()
        
        log_pipeline_complete(total_duration, steps_completed, steps_failed)

        # Finalize per-run logging
        try:
            run_logger.finalize_run(
                success=(steps_failed == 0),
                summary_data={
                    "steps_completed": steps_completed,
                    "steps_failed": steps_failed,
                    "total_duration_seconds": total_duration,
                    "run_id": run_id
                }
            )
        except Exception as e:
            self.logger.warning(f"Failed to finalize run logger: {e}")

        # Persist last run summary for audit
        try:
            run_ctx.write_summary(run_summary)
        except Exception as e:
            self.logger.warning(f"Failed to write run summary: {e}")
        
        return {
            "success": steps_failed == 0,
            "steps_completed": steps_completed,
            "steps_failed": steps_failed,
            "total_duration_seconds": total_duration,
            "start_time": self.pipeline_start_time.strftime("%Y-%m-%d %H:%M:%S"),
            "end_time": pipeline_end_time.strftime("%Y-%m-%d %H:%M:%S"),
            "run_id": run_id,
            "pipeline_signature": {"version": pipeline_sig.version, "signature": pipeline_sig.signature},
            "run_summary": run_summary,
            "results": [
                {
                    "step_id": r.step_id,
                    "step_name": r.step_name,
                    "success": r.success,
                    "duration_seconds": r.duration_seconds,
                    "attempts": r.attempts,
                    "error": r.error_message
                }
                for r in self.results
            ]
        }
    
    def get_process_list(self) -> List[Dict[str, Any]]:
        """Get list of all processes with their configurations."""
        return [
            {
                "id": p.id,
                "name": p.name,
                "description": p.description,
                "phase": p.phase,
                "requires_browser": p.requires_browser,
                "estimated_duration_minutes": p.estimated_duration_minutes
            }
            for p in self.processes
        ]
    
    def get_current_status(self) -> Dict[str, Any]:
        """Get current execution status."""
        return {
            "is_running": self.is_running,
            "current_step": self.current_step,
            "steps_completed": len([r for r in self.results if r.success]),
            "steps_failed": len([r for r in self.results if not r.success]),
            "total_steps": len(self.processes),
            "pipeline_start_time": self.pipeline_start_time.strftime("%Y-%m-%d %H:%M:%S") if self.pipeline_start_time else None
        }


if __name__ == "__main__":
    # Test the task executor
    from .logger import setup_logger
    
    setup_logger(level="DEBUG", console_output=True)
    
    def progress_callback(step_id: int, step_name: str, status: str):
        print(f"[PROGRESS] Step {step_id}: {step_name} - {status}")
    
    executor = TaskExecutor(progress_callback=progress_callback)
    
    print("\n--- Process List ---\n")
    for proc in executor.get_process_list():
        print(f"  {proc['id']}. {proc['name']} ({proc['phase']}) - ~{proc['estimated_duration_minutes']} min")
    
    print("\n--- Current Status ---\n")
    print(executor.get_current_status())
    
    # Uncomment to test actual execution
    # print("\n--- Executing Pipeline ---\n")
    # results = executor.execute_pipeline()
    # print(results)
