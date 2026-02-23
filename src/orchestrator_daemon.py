#!/usr/bin/env python3
"""
Orchestrator Daemon Module for Fields Orchestrator
Last Updated: 09/02/2026, 5:37 PM (Monday) - Brisbane Time
- Fixed: Environment variable resolution for MongoDB URI in settings.yaml
  The YAML config had literal "${COSMOS_CONNECTION_STRING}" which was not being
  resolved to the actual environment variable value. Added _resolve_env_vars()
  helper to expand ${VAR_NAME} patterns using os.environ.
- Previous: 06/02/2026, 2:06 PM (Thursday) - Brisbane Time
- Added: Enhanced zombie ChromeDriver cleanup (kills Chrome browsers + ChromeDrivers)
- Added: UE (Uninterruptible Sleep) state detection
- Added: Pipeline abort logic if unkillable processes detected
- Fixed: Removed show_window_async() calls that caused tkinter threading crash on macOS

Main daemon that coordinates the nightly property data collection pipeline.
Runs continuously, checking the time and triggering the pipeline at 8:30 PM.

Features:
- Scheduled execution at 8:30 PM Brisbane time
- User confirmation dialog with snooze option
- Auto-start after second timeout (first timeout → snooze 30min → second timeout 10min → auto-start)
- Progress tracking and notifications
- MongoDB backup after pipeline completion
- Graceful shutdown handling
- Enhanced zombie ChromeDriver process cleanup with UE state detection
"""

import os
import re
import sys
import signal
import time
import json
import yaml
import subprocess
from datetime import datetime, timedelta
from pathlib import Path
from typing import Optional, Dict, Any
import threading

# Add parent directory to path for imports
sys.path.insert(0, str(Path(__file__).parent.parent))

from src.logger import setup_logger, get_logger
from src.mongodb_monitor import MongoDBMonitor
from src.backup_coordinator import BackupCoordinator
from src.task_executor import TaskExecutor
from src.notification_manager import NotificationManager


class OrchestratorDaemon:
    """
    Main orchestrator daemon that coordinates the nightly pipeline.
    
    This class:
    - Runs continuously in the background
    - Triggers at 8:30 PM Brisbane time
    - Shows user confirmation dialog
    - Executes the pipeline with progress tracking
    - Performs daily backup after completion
    """
    
    def __init__(self, config_path: Optional[str] = None):
        """
        Initialize the orchestrator daemon.
        
        Args:
            config_path: Path to settings.yaml configuration file
        """
        # Load configuration
        if config_path is None:
            config_path = Path(__file__).parent.parent / "config" / "settings.yaml"
        self.config = self._load_config(config_path)
        
        # Set up logging
        log_config = self.config.get('logging', {})
        self.logger = setup_logger(
            name="orchestrator",
            log_file=log_config.get('file', 'logs/orchestrator.log'),
            level=log_config.get('level', 'INFO'),
            max_size_mb=log_config.get('max_size_mb', 10),
            backup_count=log_config.get('backup_count', 5),
            console_output=log_config.get('console_output', True)
        )
        
        # Initialize components
        mongodb_config = self.config.get('mongodb', {})
        
        # Resolve environment variables in MongoDB URI
        # settings.yaml may contain "${COSMOS_CONNECTION_STRING}" which needs
        # to be resolved from the environment (set via systemd EnvironmentFile)
        mongo_uri_raw = mongodb_config.get('uri', 'mongodb://127.0.0.1:27017/')
        mongo_uri = self._resolve_env_vars(mongo_uri_raw)
        
        # CRITICAL FIX (16/02/2026): Export resolved MongoDB URI to environment
        # so that ALL child processes (scraping scripts, etc.) inherit it.
        # Without this, subprocesses fall back to 127.0.0.1:27017 and fail.
        if mongo_uri:
            # Validate the URI before exporting
            if '127.0.0.1' in mongo_uri or 'localhost' in mongo_uri:
                self.logger.error("=" * 60)
                self.logger.error("CRITICAL: MongoDB URI resolves to LOCALHOST!")
                self.logger.error(f"URI: {mongo_uri}")
                self.logger.error("This will cause all scraping scripts to fail.")
                self.logger.error("Check COSMOS_CONNECTION_STRING environment variable.")
                self.logger.error("=" * 60)
                raise ValueError("MongoDB URI must not be localhost in cloud deployment")
            
            if '${' in mongo_uri or '$' in mongo_uri:
                self.logger.error("=" * 60)
                self.logger.error("CRITICAL: MongoDB URI contains unresolved template!")
                self.logger.error(f"URI: {mongo_uri}")
                self.logger.error("Environment variable substitution failed.")
                self.logger.error("=" * 60)
                raise ValueError("MongoDB URI contains unresolved environment variable")
            
            # Export to environment for child processes
            os.environ['MONGODB_URI'] = mongo_uri
            self.logger.info(f"✓ Exported MONGODB_URI to environment (starts with: {mongo_uri[:50]}...)")
        else:
            self.logger.error("=" * 60)
            self.logger.error("CRITICAL: MongoDB URI is empty!")
            self.logger.error("Cannot proceed without valid MongoDB connection.")
            self.logger.error("=" * 60)
            raise ValueError("MongoDB URI cannot be empty")
        
        self.mongodb_monitor = MongoDBMonitor(
            uri=mongo_uri,
            database=mongodb_config.get('database', 'property_data'),
            health_check_timeout=mongodb_config.get('health_check_timeout', 10),
            max_retries=mongodb_config.get('max_connection_retries', 5),
            retry_delay=mongodb_config.get('retry_delay_seconds', 30)
        )
        
        backup_config = self.config.get('backup', {})
        self.backup_coordinator = BackupCoordinator(
            mongo_uri=mongo_uri,
            primary_dir=backup_config.get('primary_dir', '/Volumes/T7/MongdbBackups'),
            secondary_dir=backup_config.get('secondary_dir', '/Users/projects/Documents/MongdbBackups'),
            tertiary_dir=backup_config.get('tertiary_dir', '/Volumes/My Passport for Mac/MongdbBackups'),
            rotation_marker=backup_config.get('rotation_marker', '.last_daily_rotation')
        )
        
        process_config = self.config.get('process_execution', {})
        self.task_executor = TaskExecutor(
            mongodb_monitor=self.mongodb_monitor,
            max_retries=process_config.get('max_retries_per_step', 2),
            retry_delay=process_config.get('retry_delay_seconds', 60),
            progress_callback=self._on_step_progress
        )
        
        schedule_config = self.config.get('schedule', {})
        notification_config = self.config.get('notifications', {})
        self.notification_manager = NotificationManager(
            dialog_timeout_seconds=schedule_config.get('dialog_timeout_seconds', 300),
            snooze_duration_minutes=schedule_config.get('snooze_duration_minutes', 30),
            on_start_callback=self._run_pipeline,
            on_manual_run_callback=self._run_pipeline
        )
        
        # Initialize notification manager with process list
        self.notification_manager.initialize_steps(self.task_executor.get_process_list())
        
        # Schedule configuration
        self.trigger_time = schedule_config.get('trigger_time', '20:30')
        self.run_on_weekends = schedule_config.get('run_on_weekends', True)
        
        # State
        self.is_running = False
        self.is_pipeline_running = False
        self.last_trigger_date: Optional[str] = None
        self.shutdown_event = threading.Event()
        
        # Lock and PID files
        paths_config = self.config.get('paths', {})
        self.lock_file = Path(paths_config.get('lock_file', '/tmp/fields_orchestrator.lock'))
        self.pid_file = Path(paths_config.get('pid_file', '/tmp/fields_orchestrator.pid'))
        self.state_file = Path(__file__).parent.parent / paths_config.get('state_file', 'state/orchestrator_state.json')
        
        # Load persisted state
        self._load_state()
    
    @staticmethod
    def _resolve_env_vars(value: str) -> str:
        """
        Resolve environment variable references in a string value.
        
        Supports patterns like ${VAR_NAME} and $VAR_NAME.
        If the entire value is a single env var reference (e.g. "${COSMOS_CONNECTION_STRING}"),
        returns the env var value directly. Otherwise, substitutes inline.
        
        Args:
            value: String that may contain ${VAR_NAME} patterns
            
        Returns:
            String with environment variables resolved
        """
        if not isinstance(value, str):
            return value
        
        # Pattern: ${VAR_NAME} or $VAR_NAME
        def replace_var(match):
            var_name = match.group(1) or match.group(2)
            env_value = os.environ.get(var_name, '')
            if not env_value:
                print(f"Warning: Environment variable '{var_name}' is not set")
            return env_value
        
        # Match ${VAR_NAME} or $VAR_NAME (not followed by {)
        resolved = re.sub(r'\$\{([^}]+)\}|\$([A-Za-z_][A-Za-z0-9_]*)', replace_var, value)
        return resolved
    
    def _load_config(self, config_path: str) -> Dict[str, Any]:
        """Load configuration from YAML file."""
        config_path = Path(config_path)
        
        if not config_path.exists():
            print(f"Warning: Config file not found: {config_path}")
            return {}
        
        try:
            with open(config_path, 'r') as f:
                return yaml.safe_load(f) or {}
        except Exception as e:
            print(f"Error loading config: {e}")
            return {}
    
    def _load_state(self) -> None:
        """Load persisted state from file."""
        try:
            if self.state_file.exists():
                with open(self.state_file, 'r') as f:
                    state = json.load(f)
                    self.last_trigger_date = state.get('last_trigger_date')
        except Exception:
            pass
    
    def _save_state(self) -> None:
        """Save state to file for persistence."""
        try:
            self.state_file.parent.mkdir(parents=True, exist_ok=True)
            with open(self.state_file, 'w') as f:
                json.dump({
                    'last_trigger_date': self.last_trigger_date
                }, f)
        except Exception as e:
            self.logger.warning(f"Failed to save state: {e}")
    
    def _acquire_lock(self) -> bool:
        """Acquire lock to prevent multiple instances."""
        try:
            if self.lock_file.exists():
                # Check if the process is still running
                try:
                    pid = int(self.lock_file.read_text().strip())
                    os.kill(pid, 0)  # Check if process exists
                    self.logger.error(f"Another instance is already running (PID: {pid})")
                    return False
                except (ProcessLookupError, ValueError):
                    # Process not running, remove stale lock
                    self.lock_file.unlink()
            
            # Create lock file with our PID
            self.lock_file.parent.mkdir(parents=True, exist_ok=True)
            self.lock_file.write_text(str(os.getpid()))
            
            # Also write PID file
            self.pid_file.write_text(str(os.getpid()))
            
            return True
        except Exception as e:
            self.logger.error(f"Failed to acquire lock: {e}")
            return False
    
    def _release_lock(self) -> None:
        """Release the lock file."""
        try:
            if self.lock_file.exists():
                self.lock_file.unlink()
            if self.pid_file.exists():
                self.pid_file.unlink()
        except Exception as e:
            self.logger.warning(f"Failed to release lock: {e}")
    
    def _detect_unkillable_processes(self) -> int:
        """
        Detect ChromeDriver processes in UE (Uninterruptible Sleep) state.
        These processes cannot be killed and require a system reboot.
        
        Returns:
            Number of unkillable ChromeDriver processes detected
        """
        try:
            result = subprocess.run(
                ['ps', 'aux'],
                capture_output=True,
                text=True,
                timeout=10
            )
            
            ue_count = 0
            ue_pids = []
            
            for line in result.stdout.split('\n'):
                if 'chromedriver' in line.lower() and 'grep' not in line:
                    parts = line.split()
                    if len(parts) >= 8:
                        # Check STAT column (usually column 7 or 8)
                        stat = parts[7] if len(parts) > 7 else ''
                        if 'U' in stat or 'D' in stat:  # U = uninterruptible, D = disk sleep
                            ue_count += 1
                            try:
                                ue_pids.append(int(parts[1]))
                            except ValueError:
                                pass
            
            if ue_count > 0:
                self.logger.error(f"⚠️ CRITICAL: {ue_count} ChromeDrivers in UNKILLABLE state (UE/D)")
                self.logger.error(f"⚠️ PIDs: {ue_pids}")
                self.logger.error("⚠️ These processes cannot be killed - SYSTEM REBOOT REQUIRED")
            
            return ue_count
            
        except Exception as e:
            self.logger.error(f"Error detecting unkillable processes: {e}")
            return 0
    
    def _cleanup_zombie_chromedrivers(self) -> Dict[str, Any]:
        """
        Enhanced cleanup: Kill Chrome browsers AND ChromeDriver processes.
        Also detects unkillable processes in UE state.
        
        Returns:
            Dict with cleanup results including:
            - zombie_count: Total ChromeDrivers found
            - killed_count: ChromeDrivers successfully killed
            - ue_count: Unkillable processes in UE state
            - success: Whether cleanup was successful
        """
        try:
            self.logger.info("=" * 60)
            self.logger.info("ENHANCED ZOMBIE CLEANUP: Chrome + ChromeDriver")
            self.logger.info("=" * 60)
            
            # STEP 1: Scan for ChromeDriver processes FIRST
            self.logger.info("Step 1: Scanning for ChromeDriver processes...")
            result = subprocess.run(
                ['ps', 'aux'],
                capture_output=True,
                text=True,
                timeout=10
            )
            
            zombie_count = 0
            killed_count = 0
            ue_count = 0
            ue_pids = []
            
            for line in result.stdout.split('\n'):
                if 'chromedriver' in line.lower() and 'grep' not in line:
                    zombie_count += 1
                    parts = line.split()
                    
                    if len(parts) >= 8:
                        # Check STAT column for UE state
                        stat = parts[7] if len(parts) > 7 else ''
                        pid = parts[1]
                        
                        if 'U' in stat or 'D' in stat:
                            # Unkillable process
                            ue_count += 1
                            ue_pids.append(pid)
                            self.logger.warning(f"⚠️ ChromeDriver PID {pid} in UNKILLABLE state: {stat}")
                        else:
                            # Try to kill normal process
                            try:
                                subprocess.run(['kill', '-9', pid], check=False, timeout=5)
                                killed_count += 1
                            except subprocess.TimeoutExpired:
                                pass
            
            # STEP 2: Only kill Chrome if we found zombie ChromeDrivers
            if zombie_count > 0:
                self.logger.info("Step 2: Killing Chrome browsers (zombies detected)...")
                chrome_result = subprocess.run(
                    ['killall', '-9', 'Google Chrome'],
                    capture_output=True,
                    text=True,
                    timeout=10
                )
                if chrome_result.returncode == 0:
                    self.logger.info("✓ Chrome browsers terminated")
                time.sleep(2)
            else:
                self.logger.info("Step 2: No zombies found - Chrome left running")
            
            # STEP 3: Use killall as backup for ChromeDrivers
            if zombie_count > 0:
                self.logger.info("Step 3: Running killall for remaining ChromeDrivers...")
                subprocess.run(
                    ['killall', '-9', 'chromedriver'],
                    capture_output=True,
                    text=True,
                    timeout=10
                )
                time.sleep(2)
            
            # STEP 4: Verify cleanup
            self.logger.info("Step 4: Verifying cleanup...")
            verify_result = subprocess.run(
                ['ps', 'aux'],
                capture_output=True,
                text=True,
                timeout=10
            )
            
            remaining = sum(1 for line in verify_result.stdout.split('\n') 
                          if 'chromedriver' in line.lower() and 'grep' not in line)
            
            # Log results
            self.logger.info("=" * 60)
            self.logger.info("CLEANUP RESULTS:")
            self.logger.info(f"  ChromeDrivers Found: {zombie_count}")
            self.logger.info(f"  Successfully Killed: {killed_count}")
            self.logger.info(f"  Unkillable (UE state): {ue_count}")
            self.logger.info(f"  Remaining After Cleanup: {remaining}")
            
            if ue_count > 0:
                self.logger.error("=" * 60)
                self.logger.error("⚠️ CRITICAL: UNKILLABLE PROCESSES DETECTED")
                self.logger.error(f"⚠️ {ue_count} ChromeDrivers in UE (Uninterruptible Sleep) state")
                self.logger.error(f"⚠️ PIDs: {', '.join(ue_pids)}")
                self.logger.error("⚠️ These processes CANNOT be killed by any signal")
                self.logger.error("⚠️ SYSTEM REBOOT REQUIRED to clear these processes")
                self.logger.error("⚠️ Pipeline execution will be ABORTED")
                self.logger.error("=" * 60)
            elif remaining > 0:
                self.logger.warning(f"⚠️ {remaining} ChromeDrivers still present after cleanup")
            else:
                self.logger.info("✓ All ChromeDrivers successfully cleaned up")
            
            self.logger.info("=" * 60)
            
            return {
                'zombie_count': zombie_count,
                'killed_count': killed_count,
                'ue_count': ue_count,
                'remaining': remaining,
                'success': ue_count == 0 and remaining == 0
            }
            
        except Exception as e:
            self.logger.error(f"Error during enhanced cleanup: {e}")
            return {
                'zombie_count': 0,
                'killed_count': 0,
                'ue_count': 0,
                'remaining': 0,
                'success': False,
                'error': str(e)
            }
    
    def _on_step_progress(self, step_id: int, step_name: str, status: str) -> None:
        """
        Callback for step progress updates.
        
        Args:
            step_id: ID of the step
            step_name: Name of the step
            status: Current status (running, completed, failed, retrying)
        """
        now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        
        if status == "running":
            self.notification_manager.update_step_status(step_id, status, start_time=now)
        elif status in ["completed", "failed"]:
            self.notification_manager.update_step_status(step_id, status, end_time=now)
        else:
            self.notification_manager.update_step_status(step_id, status)
        
        self.logger.info(f"Step {step_id} ({step_name}): {status}")
    
    def _run_pipeline(self) -> None:
        """Execute the full pipeline including backup."""
        if self.is_pipeline_running:
            self.logger.warning("Pipeline is already running")
            return
        
        self.is_pipeline_running = True
        self.notification_manager.set_status("Running pipeline...")
        
        try:
            # Enhanced cleanup with UE state detection
            self.logger.info("=" * 60)
            self.logger.info("PRE-RUN CLEANUP: Enhanced Chrome + ChromeDriver cleanup")
            self.logger.info("=" * 60)
            
            cleanup_results = self._cleanup_zombie_chromedrivers()
            
            # Check for unkillable processes
            if cleanup_results.get('ue_count', 0) > 0:
                error_msg = (
                    f"CRITICAL: {cleanup_results['ue_count']} unkillable ChromeDriver processes detected. "
                    "System reboot required. Pipeline execution aborted."
                )
                self.logger.error(error_msg)
                self.notification_manager.show_system_notification(
                    "Fields Orchestrator - CRITICAL ERROR",
                    "Unkillable processes detected. REBOOT REQUIRED. Pipeline aborted."
                )
                self.notification_manager.set_pipeline_complete(False, error_msg)
                return
            
            # Notify about successful cleanup
            if cleanup_results.get('killed_count', 0) > 0:
                self.notification_manager.show_system_notification(
                    "Fields Orchestrator - Cleanup",
                    f"Cleaned up {cleanup_results['killed_count']} zombie ChromeDriver processes"
                )
            
            # Execute the main pipeline
            self.logger.info("Starting pipeline execution...")
            results = self.task_executor.execute_pipeline()
            
            # Check if backup should be skipped (cloud deployment uses Cosmos DB built-in backup)
            skip_backup = self.config.get('backup', {}).get('skip_backup', False)
            
            if skip_backup:
                self.logger.info("=" * 60)
                self.logger.info("BACKUP SKIPPED - Cloud deployment uses Azure Cosmos DB built-in backup")
                self.logger.info("=" * 60)
                backup_success = True  # Not a failure, just skipped
            else:
                # Apply final cooldown before backup
                cooldown = self.config.get('mongodb', {}).get('cooldown_before_backup', 300)
                self.logger.info(f"Applying {cooldown}s cooldown before backup...")
                self.mongodb_monitor.start_cooldown(cooldown, "before backup")
                
                # Perform daily backup
                self.logger.info("Starting daily backup...")
                self.notification_manager.update_step_status(8, "running", 
                    start_time=datetime.now().strftime("%Y-%m-%d %H:%M:%S"))
                
                backup_success = self.backup_coordinator.perform_daily_backup()
                
                backup_status = "completed" if backup_success else "failed"
                self.notification_manager.update_step_status(8, backup_status,
                    end_time=datetime.now().strftime("%Y-%m-%d %H:%M:%S"))
            
            # Calculate summary
            steps_completed = results.get('steps_completed', 0)
            steps_failed = results.get('steps_failed', 0)
            
            if not skip_backup:
                if backup_success:
                    steps_completed += 1
                else:
                    steps_failed += 1
            
            total_success = steps_failed == 0
            
            # Generate summary
            duration = results.get('total_duration_seconds', 0)
            if duration >= 3600:
                duration_str = f"{duration/3600:.1f} hours"
            else:
                duration_str = f"{duration/60:.0f} minutes"
            
            summary = f"Completed in {duration_str}. {steps_completed} succeeded, {steps_failed} failed."
            
            # Update notification manager
            self.notification_manager.set_pipeline_complete(total_success, summary)
            
            # Log final status
            self.logger.info("=" * 60)
            self.logger.info("PIPELINE EXECUTION COMPLETE")
            self.logger.info(f"Duration: {duration_str}")
            self.logger.info(f"Steps Completed: {steps_completed}")
            self.logger.info(f"Steps Failed: {steps_failed}")
            self.logger.info(f"Backup: {'Success' if backup_success else 'Failed'}")
            self.logger.info("=" * 60)
            
        except Exception as e:
            self.logger.error(f"Pipeline execution failed: {e}")
            self.notification_manager.set_pipeline_complete(False, f"Pipeline failed: {e}")
        finally:
            self.is_pipeline_running = False
    
    def _should_trigger(self) -> bool:
        """Check if the pipeline should be triggered now."""
        now = datetime.now()
        
        # Check if we should run on weekends
        if not self.run_on_weekends and now.weekday() >= 5:
            return False
        
        # Check if we already triggered today
        # DISABLED FOR TESTING - allows multiple runs per day
        # today = now.strftime("%Y-%m-%d")
        # if self.last_trigger_date == today:
        #     return False
        
        # Check if it's the trigger time
        current_time = now.strftime("%H:%M")
        if current_time == self.trigger_time:
            return True
        
        return False
    
    def _handle_trigger(self) -> None:
        """
        Handle the scheduled trigger with two-stage timeout logic.
        
        Flow:
        1. First dialog (5 min timeout) → if no response, auto-snooze 30 min
        2. Second dialog (10 min timeout) → if no response, auto-start pipeline
        
        OR: If skip_confirmation_dialogs is True, start immediately (cloud/headless mode)
        """
        today = datetime.now().strftime("%Y-%m-%d")
        self.last_trigger_date = today
        self._save_state()
        
        self.logger.info("=" * 60)
        self.logger.info("SCHEDULED TRIGGER ACTIVATED")
        self.logger.info(f"Time: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
        self.logger.info("=" * 60)
        
        # Check if we should skip confirmation dialogs (cloud/headless mode)
        schedule_config = self.config.get('schedule', {})
        skip_dialogs = schedule_config.get('skip_confirmation_dialogs', False)
        
        if skip_dialogs:
            self.logger.info("Confirmation dialogs disabled - starting pipeline immediately")
            self._run_pipeline_async()
            return
        
        # NOTE: We don't show the tkinter window here because it crashes when run from
        # a background thread on macOS. The AppleScript dialog provides user interaction.
        
        # FIRST DIALOG (5 minute timeout)
        self.logger.info("Showing first confirmation dialog (5 min timeout)...")
        self.notification_manager.show_system_notification(
            "Fields Orchestrator",
            "Property data collection is scheduled. Please respond within 5 minutes."
        )
        
        response = self.notification_manager.show_confirmation_dialog()
        
        if response == "start":
            self.logger.info("User chose to start immediately")
            self._run_pipeline_async()
            return
        
        # User chose to wait OR dialog timed out - snooze for 30 minutes
        self.logger.info("First dialog: snoozing for 30 minutes...")
        self.notification_manager.set_status("Waiting 30 minutes before next prompt...")
        self.notification_manager.show_system_notification(
            "Fields Orchestrator - Snoozed",
            "Will prompt again in 30 minutes. If no response, pipeline will auto-start."
        )
        
        # Wait 30 minutes (check shutdown event periodically)
        snooze_seconds = 30 * 60  # 30 minutes
        for _ in range(snooze_seconds):
            if self.shutdown_event.is_set():
                return
            time.sleep(1)
        
        # SECOND DIALOG (10 minute timeout)
        self.logger.info("Showing second confirmation dialog (10 min timeout)...")
        self.notification_manager.set_status("Final prompt - will auto-start if no response")
        self.notification_manager.show_system_notification(
            "Fields Orchestrator - Final Notice",
            "Pipeline will AUTO-START in 10 minutes if no response!"
        )
        
        # Use a longer timeout for the second dialog (10 minutes = 600 seconds)
        original_timeout = self.notification_manager.dialog_timeout
        self.notification_manager.dialog_timeout = 600  # 10 minutes
        
        response = self.notification_manager.show_confirmation_dialog()
        
        # Restore original timeout
        self.notification_manager.dialog_timeout = original_timeout
        
        if response == "start":
            self.logger.info("User chose to start after second prompt")
            self._run_pipeline_async()
        elif response == "snooze":
            # Second timeout or user chose wait again - AUTO-START
            self.logger.info("Second dialog timed out or user snoozed - AUTO-STARTING pipeline")
            self.notification_manager.show_system_notification(
                "Fields Orchestrator - Auto-Starting",
                "No response received. Starting pipeline automatically."
            )
            self._run_pipeline_async()
    
    def _run_pipeline_async(self) -> None:
        """Run the pipeline in a separate thread."""
        threading.Thread(target=self._run_pipeline, daemon=True).start()
    
    def _signal_handler(self, signum, frame) -> None:
        """Handle shutdown signals."""
        self.logger.info(f"Received signal {signum}. Shutting down...")
        self.shutdown_event.set()
    
    def start(self) -> None:
        """Start the orchestrator daemon."""
        # Acquire lock
        if not self._acquire_lock():
            sys.exit(1)
        
        # Set up signal handlers
        signal.signal(signal.SIGINT, self._signal_handler)
        signal.signal(signal.SIGTERM, self._signal_handler)
        
        self.is_running = True
        
        self.logger.info("=" * 60)
        self.logger.info("FIELDS ORCHESTRATOR DAEMON STARTED")
        self.logger.info(f"PID: {os.getpid()}")
        self.logger.info(f"Trigger Time: {self.trigger_time}")
        self.logger.info(f"Run on Weekends: {self.run_on_weekends}")
        self.logger.info("=" * 60)
        
        # Show initial notification
        self.notification_manager.show_system_notification(
            "Fields Orchestrator Started",
            f"Will trigger at {self.trigger_time} daily."
        )
        
        try:
            # Main loop - check every minute
            while not self.shutdown_event.is_set():
                if self._should_trigger():
                    self._handle_trigger()
                
                # Sleep for 60 seconds, but check shutdown event every second
                for _ in range(60):
                    if self.shutdown_event.is_set():
                        break
                    time.sleep(1)
                    
        except Exception as e:
            self.logger.error(f"Daemon error: {e}")
        finally:
            self._shutdown()
    
    def _shutdown(self) -> None:
        """Clean shutdown of the daemon."""
        self.logger.info("Shutting down orchestrator daemon...")
        
        self.is_running = False
        
        # Close notification window
        self.notification_manager.close_window()
        
        # Close MongoDB connection
        self.mongodb_monitor.close()
        
        # Release lock
        self._release_lock()
        
        self.logger.info("Orchestrator daemon stopped.")
    
    def run_now(self) -> None:
        """Manually trigger the pipeline immediately."""
        self.logger.info("Manual trigger requested")
        
        # NOTE: Don't use show_window_async() - it crashes on macOS due to tkinter threading
        # Use system notification instead
        self.notification_manager.show_system_notification(
            "Fields Orchestrator - Manual Run",
            "Starting pipeline execution..."
        )
        
        # Run the pipeline
        self._run_pipeline()


def main():
    """Main entry point for the orchestrator daemon."""
    import argparse
    
    parser = argparse.ArgumentParser(description="Fields Property Data Orchestrator")
    parser.add_argument('--config', '-c', help='Path to configuration file')
    parser.add_argument('--run-now', action='store_true', help='Run pipeline immediately')
    parser.add_argument('--show-window', action='store_true', help='Show status window only')
    
    args = parser.parse_args()
    
    daemon = OrchestratorDaemon(config_path=args.config)
    
    if args.run_now:
        daemon.run_now()
    elif args.show_window:
        daemon.notification_manager.show_window()
    else:
        daemon.start()


if __name__ == "__main__":
    main()
