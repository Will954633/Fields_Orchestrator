#!/usr/bin/env python3
"""
Notification Manager Module for Fields Orchestrator
Last Updated: 26/01/2026, 8:33 PM (Brisbane Time)
- Made tkinter import optional to avoid crashes when tkinter is not available

Manages macOS notifications and the persistent status window.
Uses tkinter for the GUI window (optional) and osascript for system dialogs.

Features:
- Persistent status window showing pipeline progress (when tkinter available)
- Modal dialogs for user confirmation via AppleScript
- Real-time progress updates
- Summary display for morning review
"""

import subprocess
import threading
import time
import json
from datetime import datetime
from pathlib import Path
from typing import Optional, Dict, Any, List, Callable
from dataclasses import dataclass, field

# Try to import tkinter, but make it optional
# tkinter can crash when run from background threads on macOS
try:
    import tkinter as tk
    from tkinter import ttk, messagebox
    TKINTER_AVAILABLE = True
except ImportError:
    tk = None
    ttk = None
    messagebox = None
    TKINTER_AVAILABLE = False


@dataclass
class StepStatus:
    """Status of a single pipeline step."""
    id: int
    name: str
    status: str = "pending"  # pending, running, completed, failed, retrying
    start_time: Optional[str] = None
    end_time: Optional[str] = None
    duration: Optional[str] = None
    attempts: int = 0


class NotificationManager:
    """
    Manages notifications and the status window for the orchestrator.
    
    This class provides:
    - Modal dialogs for user confirmation (Start Now / Wait 30 Min)
    - Persistent status window with real-time progress
    - System notifications for important events
    """
    
    def __init__(
        self,
        dialog_timeout_seconds: int = 300,
        snooze_duration_minutes: int = 30,
        on_start_callback: Optional[Callable] = None,
        on_manual_run_callback: Optional[Callable] = None
    ):
        """
        Initialize the notification manager.
        
        Args:
            dialog_timeout_seconds: Timeout for confirmation dialog (default 5 min)
            snooze_duration_minutes: Duration to wait when user chooses to snooze
            on_start_callback: Callback when user clicks "Start Now"
            on_manual_run_callback: Callback when user clicks "Run Now" (manual trigger)
        """
        self.dialog_timeout = dialog_timeout_seconds
        self.snooze_duration = snooze_duration_minutes
        self.on_start_callback = on_start_callback
        self.on_manual_run_callback = on_manual_run_callback
        
        # Step statuses
        self.steps: List[StepStatus] = []
        
        # Window state
        self.window: Optional[tk.Tk] = None
        self.is_window_open = False
        self.window_thread: Optional[threading.Thread] = None
        
        # Last run info
        self.last_run_date: Optional[str] = None
        self.last_run_status: Optional[str] = None
        
        # State file for persistence
        self.state_file = Path(__file__).parent.parent / "state" / "window_state.json"
        self._load_state()
    
    def _load_state(self) -> None:
        """Load persisted state from file."""
        try:
            if self.state_file.exists():
                with open(self.state_file, 'r') as f:
                    state = json.load(f)
                    self.last_run_date = state.get('last_run_date')
                    self.last_run_status = state.get('last_run_status')
        except Exception:
            pass
    
    def _save_state(self) -> None:
        """Save state to file for persistence."""
        try:
            self.state_file.parent.mkdir(parents=True, exist_ok=True)
            with open(self.state_file, 'w') as f:
                json.dump({
                    'last_run_date': self.last_run_date,
                    'last_run_status': self.last_run_status
                }, f)
        except Exception:
            pass
    
    def initialize_steps(self, steps: List[Dict[str, Any]]) -> None:
        """
        Initialize the step list from process configurations.
        
        Args:
            steps: List of step dictionaries with id, name, etc.
        """
        self.steps = [
            StepStatus(id=s['id'], name=s['name'])
            for s in steps
        ]
        # Add backup step
        self.steps.append(StepStatus(id=8, name="Daily Backup"))
    
    def update_step_status(
        self,
        step_id: int,
        status: str,
        start_time: Optional[str] = None,
        end_time: Optional[str] = None,
        attempts: int = 0
    ) -> None:
        """
        Update the status of a specific step.
        
        Args:
            step_id: ID of the step to update
            status: New status (pending, running, completed, failed, retrying)
            start_time: Start time string
            end_time: End time string
            attempts: Number of attempts made
        """
        for step in self.steps:
            if step.id == step_id:
                step.status = status
                if start_time:
                    step.start_time = start_time
                if end_time:
                    step.end_time = end_time
                step.attempts = attempts
                
                # Calculate duration if both times available
                if step.start_time and step.end_time:
                    try:
                        start = datetime.strptime(step.start_time, "%Y-%m-%d %H:%M:%S")
                        end = datetime.strptime(step.end_time, "%Y-%m-%d %H:%M:%S")
                        duration = (end - start).total_seconds()
                        if duration >= 3600:
                            step.duration = f"{duration/3600:.1f}h"
                        elif duration >= 60:
                            step.duration = f"{duration/60:.0f}m"
                        else:
                            step.duration = f"{duration:.0f}s"
                    except:
                        pass
                break
        
        # Update window if open
        if self.is_window_open and self.window:
            self._update_window_display()
    
    def show_confirmation_dialog(self) -> str:
        """
        Show a modal dialog asking user to start or wait.
        
        Returns:
            "start" if user clicks Start Now
            "snooze" if user clicks Wait 30 Minutes or timeout
        """
        # Use AppleScript for a modal dialog that appears on top
        script = f'''
        tell application "System Events"
            activate
            set dialogResult to display dialog "🏠 Property Data Update Scheduled" & return & return & ¬
                "The automated data collection is ready to begin." & return & ¬
                "This process requires full browser mode and will take 2-3 hours." & return & return & ¬
                "Would you like to start now or wait 30 minutes?" ¬
                buttons {{"Wait 30 Minutes", "Start Now"}} ¬
                default button "Start Now" ¬
                with icon caution ¬
                giving up after {self.dialog_timeout}
            
            if gave up of dialogResult then
                return "snooze"
            else if button returned of dialogResult is "Start Now" then
                return "start"
            else
                return "snooze"
            end if
        end tell
        '''
        
        try:
            result = subprocess.run(
                ['osascript', '-e', script],
                capture_output=True,
                text=True,
                timeout=self.dialog_timeout + 10
            )
            
            response = result.stdout.strip().lower()
            if response == "start":
                return "start"
            else:
                return "snooze"
                
        except subprocess.TimeoutExpired:
            return "snooze"
        except Exception as e:
            print(f"Dialog error: {e}")
            return "snooze"
    
    def show_system_notification(self, title: str, message: str, sound: bool = True) -> None:
        """
        Show a macOS system notification.
        
        Args:
            title: Notification title
            message: Notification message
            sound: Whether to play a sound
        """
        sound_str = 'with sound name "default"' if sound else ''
        script = f'''
        display notification "{message}" with title "{title}" {sound_str}
        '''
        
        try:
            subprocess.run(['osascript', '-e', script], capture_output=True)
        except Exception:
            pass
    
    def _get_status_icon(self, status: str) -> str:
        """Get emoji icon for status."""
        icons = {
            "pending": "⏳",
            "running": "🔄",
            "completed": "✅",
            "failed": "❌",
            "retrying": "🔁"
        }
        return icons.get(status, "⬜")
    
    def _create_window(self) -> None:
        """Create the status window."""
        self.window = tk.Tk()
        self.window.title("🏠 Fields Property Data Orchestrator")
        self.window.geometry("500x600")
        self.window.resizable(True, True)
        
        # Make window stay on top
        self.window.attributes('-topmost', True)
        
        # Main frame with padding
        main_frame = ttk.Frame(self.window, padding="10")
        main_frame.pack(fill=tk.BOTH, expand=True)
        
        # Title
        title_label = ttk.Label(
            main_frame,
            text="🏠 Fields Property Data Orchestrator",
            font=('Helvetica', 16, 'bold')
        )
        title_label.pack(pady=(0, 10))
        
        # Status label
        self.status_var = tk.StringVar(value="Status: Waiting for scheduled time")
        status_label = ttk.Label(main_frame, textvariable=self.status_var, font=('Helvetica', 12))
        status_label.pack(pady=(0, 10))
        
        # Button frame
        button_frame = ttk.Frame(main_frame)
        button_frame.pack(pady=(0, 15))
        
        # Start Now button
        self.start_btn = ttk.Button(
            button_frame,
            text="▶️ Start Now",
            command=self._on_start_click
        )
        self.start_btn.pack(side=tk.LEFT, padx=5)
        
        # Wait button
        self.wait_btn = ttk.Button(
            button_frame,
            text="⏰ Wait 30 Min",
            command=self._on_wait_click
        )
        self.wait_btn.pack(side=tk.LEFT, padx=5)
        
        # Manual Run button
        self.manual_btn = ttk.Button(
            button_frame,
            text="🔧 Run Now (Manual)",
            command=self._on_manual_click
        )
        self.manual_btn.pack(side=tk.LEFT, padx=5)
        
        # Separator
        ttk.Separator(main_frame, orient='horizontal').pack(fill=tk.X, pady=10)
        
        # Progress section
        progress_label = ttk.Label(main_frame, text="Progress:", font=('Helvetica', 12, 'bold'))
        progress_label.pack(anchor=tk.W)
        
        # Steps frame with scrollbar
        steps_frame = ttk.Frame(main_frame)
        steps_frame.pack(fill=tk.BOTH, expand=True, pady=(5, 10))
        
        # Canvas for scrolling
        canvas = tk.Canvas(steps_frame, highlightthickness=0)
        scrollbar = ttk.Scrollbar(steps_frame, orient="vertical", command=canvas.yview)
        self.steps_inner_frame = ttk.Frame(canvas)
        
        self.steps_inner_frame.bind(
            "<Configure>",
            lambda e: canvas.configure(scrollregion=canvas.bbox("all"))
        )
        
        canvas.create_window((0, 0), window=self.steps_inner_frame, anchor="nw")
        canvas.configure(yscrollcommand=scrollbar.set)
        
        canvas.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        scrollbar.pack(side=tk.RIGHT, fill=tk.Y)
        
        # Step labels (will be populated)
        self.step_labels: Dict[int, ttk.Label] = {}
        self._populate_steps()
        
        # Separator
        ttk.Separator(main_frame, orient='horizontal').pack(fill=tk.X, pady=10)
        
        # Last run info
        self.last_run_var = tk.StringVar(value=self._get_last_run_text())
        last_run_label = ttk.Label(main_frame, textvariable=self.last_run_var, font=('Helvetica', 10))
        last_run_label.pack(anchor=tk.W)
        
        # Handle window close
        self.window.protocol("WM_DELETE_WINDOW", self._on_window_close)
        
        self.is_window_open = True
    
    def _populate_steps(self) -> None:
        """Populate step labels in the window."""
        for widget in self.steps_inner_frame.winfo_children():
            widget.destroy()
        
        self.step_labels = {}
        
        for step in self.steps:
            icon = self._get_status_icon(step.status)
            time_str = ""
            if step.end_time and step.duration:
                time_str = f" ({step.duration})"
            elif step.status == "running":
                time_str = " (running...)"
            
            text = f"{icon} Step {step.id}: {step.name}{time_str}"
            
            label = ttk.Label(
                self.steps_inner_frame,
                text=text,
                font=('Helvetica', 11)
            )
            label.pack(anchor=tk.W, pady=2)
            self.step_labels[step.id] = label
    
    def _update_window_display(self) -> None:
        """Update the window display with current step statuses."""
        if not self.window or not self.is_window_open:
            return
        
        try:
            for step in self.steps:
                if step.id in self.step_labels:
                    icon = self._get_status_icon(step.status)
                    time_str = ""
                    if step.end_time and step.duration:
                        time_str = f" ({step.duration})"
                    elif step.status == "running":
                        time_str = " (running...)"
                    
                    text = f"{icon} Step {step.id}: {step.name}{time_str}"
                    self.step_labels[step.id].config(text=text)
            
            self.window.update_idletasks()
        except tk.TclError:
            # Window was closed
            self.is_window_open = False
    
    def _get_last_run_text(self) -> str:
        """Get text for last run info."""
        if self.last_run_date and self.last_run_status:
            return f"Last Run: {self.last_run_date} - {self.last_run_status}"
        return "Last Run: Never"
    
    def _on_start_click(self) -> None:
        """Handle Start Now button click."""
        self.status_var.set("Status: Starting pipeline...")
        self.start_btn.config(state=tk.DISABLED)
        self.wait_btn.config(state=tk.DISABLED)
        self.manual_btn.config(state=tk.DISABLED)
        
        if self.on_start_callback:
            # Run in separate thread to not block UI
            threading.Thread(target=self.on_start_callback, daemon=True).start()
    
    def _on_wait_click(self) -> None:
        """Handle Wait 30 Minutes button click."""
        self.status_var.set(f"Status: Waiting {self.snooze_duration} minutes...")
        self.start_btn.config(state=tk.DISABLED)
        self.wait_btn.config(state=tk.DISABLED)
        
        # Schedule re-enable after snooze
        def reenable():
            time.sleep(self.snooze_duration * 60)
            if self.is_window_open and self.window:
                self.window.after(0, lambda: self.status_var.set("Status: Ready to start"))
                self.window.after(0, lambda: self.start_btn.config(state=tk.NORMAL))
                self.window.after(0, lambda: self.wait_btn.config(state=tk.NORMAL))
                self.show_system_notification(
                    "Fields Orchestrator",
                    "Snooze complete. Ready to start data collection."
                )
        
        threading.Thread(target=reenable, daemon=True).start()
    
    def _on_manual_click(self) -> None:
        """Handle Manual Run button click."""
        if messagebox.askyesno(
            "Manual Run",
            "Are you sure you want to start the pipeline manually?\n\n"
            "This will run all data collection processes."
        ):
            self.status_var.set("Status: Starting manual run...")
            self.start_btn.config(state=tk.DISABLED)
            self.wait_btn.config(state=tk.DISABLED)
            self.manual_btn.config(state=tk.DISABLED)
            
            if self.on_manual_run_callback:
                threading.Thread(target=self.on_manual_run_callback, daemon=True).start()
    
    def _on_window_close(self) -> None:
        """Handle window close event."""
        # Minimize to dock instead of closing
        self.window.withdraw()
        self.show_system_notification(
            "Fields Orchestrator",
            "Window minimized. The orchestrator is still running."
        )
    
    def show_window(self) -> None:
        """Show the status window."""
        if self.window and self.is_window_open:
            self.window.deiconify()
            self.window.lift()
            return
        
        # Create window in main thread
        self._create_window()
        self.window.mainloop()
    
    def show_window_async(self) -> None:
        """Show the status window in a separate thread."""
        if self.window_thread and self.window_thread.is_alive():
            if self.window:
                self.window.after(0, self.window.deiconify)
                self.window.after(0, self.window.lift)
            return
        
        self.window_thread = threading.Thread(target=self.show_window, daemon=True)
        self.window_thread.start()
    
    def close_window(self) -> None:
        """Close the status window."""
        if self.window:
            self.window.quit()
            self.window.destroy()
            self.window = None
        self.is_window_open = False
    
    def set_status(self, status: str) -> None:
        """Set the status text in the window."""
        if self.window and self.is_window_open:
            self.window.after(0, lambda: self.status_var.set(f"Status: {status}"))
    
    def set_pipeline_complete(self, success: bool, summary: str) -> None:
        """
        Mark the pipeline as complete and update display.
        
        Args:
            success: Whether pipeline completed successfully
            summary: Summary text to display
        """
        self.last_run_date = datetime.now().strftime("%d/%m/%Y %H:%M")
        self.last_run_status = "All steps completed ✅" if success else "Completed with errors ⚠️"
        self._save_state()
        
        if self.window and self.is_window_open:
            self.window.after(0, lambda: self.status_var.set(f"Status: {summary}"))
            self.window.after(0, lambda: self.last_run_var.set(self._get_last_run_text()))
            self.window.after(0, lambda: self.start_btn.config(state=tk.NORMAL))
            self.window.after(0, lambda: self.wait_btn.config(state=tk.NORMAL))
            self.window.after(0, lambda: self.manual_btn.config(state=tk.NORMAL))
        
        # Show system notification
        if success:
            self.show_system_notification(
                "Fields Orchestrator - Complete ✅",
                "All data collection processes completed successfully!"
            )
        else:
            self.show_system_notification(
                "Fields Orchestrator - Complete ⚠️",
                "Data collection completed with some errors. Check the window for details."
            )


if __name__ == "__main__":
    # Test the notification manager
    def on_start():
        print("Start callback triggered!")
        time.sleep(2)
        manager.update_step_status(1, "running", datetime.now().strftime("%Y-%m-%d %H:%M:%S"))
        time.sleep(2)
        manager.update_step_status(1, "completed", end_time=datetime.now().strftime("%Y-%m-%d %H:%M:%S"))
        manager.update_step_status(2, "running", datetime.now().strftime("%Y-%m-%d %H:%M:%S"))
        time.sleep(2)
        manager.update_step_status(2, "completed", end_time=datetime.now().strftime("%Y-%m-%d %H:%M:%S"))
        manager.set_pipeline_complete(True, "Pipeline completed successfully!")
    
    manager = NotificationManager(
        on_start_callback=on_start,
        on_manual_run_callback=on_start
    )
    
    # Initialize with test steps
    manager.initialize_steps([
        {"id": 1, "name": "Scrape For-Sale Properties"},
        {"id": 2, "name": "GPT Photo Analysis"},
        {"id": 3, "name": "GPT Photo Reorder"},
        {"id": 4, "name": "Floor Plan Enrichment"},
        {"id": 5, "name": "Scrape Sold Properties"},
        {"id": 6, "name": "Floor Plan Enrichment (Sold)"},
        {"id": 7, "name": "Monitor Sold Transitions"},
    ])
    
    # Show window
    manager.show_window()
