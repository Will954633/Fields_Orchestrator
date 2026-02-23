# Fields Orchestrator - System Design Plan

**Last Updated:** 26/01/2026, 7:47 PM (Brisbane Time)

---

## Overview

This document outlines the design plan for an automated orchestrator system that will run the property data collection pipeline every night at 8:30 PM Brisbane time, with careful coordination of MongoDB operations and backup processes.

---

## Key Requirements

### 1. User Notification System
- Display a macOS system notification at 8:30 PM regardless of what application is in focus
- Offer two options: "Start Now" or "Wait 30 Minutes"
- If "Wait 30 Minutes" is selected, re-display the notification after 30 minutes
- Continue prompting until user confirms to start

### 2. Process Sequence (7 Steps)
Based on the PROCESS_SEQUENCE_GUIDE.md:

| Step | Process | Duration | MongoDB Activity |
|------|---------|----------|------------------|
| 1 | Scrape For-Sale Properties | ~20-30 min | Heavy writes |
| 2 | GPT Photo Analysis | ~30-60 sec/property | Moderate read/write |
| 3 | GPT Photo Reorder | ~15-30 sec/property | Moderate read/write |
| 4 | Floor Plan Enrichment (For Sale) | ~30-60 sec/property | Moderate read/write |
| 5 | Scrape Sold Properties | ~20-30 min | Heavy writes |
| 6 | Floor Plan Enrichment (Sold) | ~30-60 sec/property | Moderate read/write |
| 7 | Monitor For-Sale → Sold Transitions | Variable | Moderate read/write |

### 3. Backup Coordination
The existing backup system runs every 30 minutes and performs:
- `mongodump` to create compressed backups
- Syncs to 3 locations (T7 SSD, Internal SSD, My Passport)

**Critical Constraint:** We must NOT run backups while heavy MongoDB writes are occurring.

### 4. Browser Mode Requirement
Steps 1, 5, and 7 require full-head browser mode (Selenium/Playwright), meaning the user cannot use the computer during these operations.

---

## Proposed Architecture

### Component 1: Scheduler Daemon (`orchestrator_daemon.py`)
A Python daemon that:
- Runs continuously in the background
- Checks the time every minute
- At 8:30 PM, triggers the notification system
- Manages the "wait 30 minutes" loop

### Component 2: Notification System (`notification_manager.py`)
Uses macOS native notifications via:
- `osascript` for AppleScript dialogs (allows button choices)
- Displays modal dialog that appears on top of all windows
- Returns user's choice to the daemon

### Component 3: Task Executor (`task_executor.py`)
Orchestrates the actual process execution:
- Runs each step in sequence
- Monitors process completion
- Handles errors and logging
- Coordinates with backup system

### Component 4: Backup Coordinator (`backup_coordinator.py`)
Manages backup timing:
- Pauses the continuous backup service before heavy writes
- Resumes backup service after writes complete
- Ensures a backup is taken before starting the pipeline
- Ensures a backup is taken after pipeline completion

### Component 5: MongoDB Health Monitor (`mongodb_monitor.py`)
Monitors MongoDB stability:
- Checks connection health
- Monitors operation queue depth
- Implements rate limiting between operations
- Provides cooldown periods between heavy operations

---

## Execution Flow

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                           ORCHESTRATOR FLOW                                  │
└─────────────────────────────────────────────────────────────────────────────┘

8:30 PM Trigger
      │
      ▼
┌─────────────────────┐
│ Display Notification │
│ "Start Now" or      │
│ "Wait 30 Minutes"   │
└──────────┬──────────┘
           │
     ┌─────┴─────┐
     │           │
     ▼           ▼
[Start Now]  [Wait 30 Min]
     │           │
     │           └──► Sleep 30 min ──► Loop back to notification
     │
     ▼
┌─────────────────────┐
│ PHASE 0: PREPARATION │
├─────────────────────┤
│ 1. Check MongoDB    │
│ 2. Pause Backup Svc │
│ 3. Take Pre-Backup  │
│ 4. Wait 2 min       │
└──────────┬──────────┘
           │
           ▼
┌─────────────────────┐
│ PHASE 1: FOR-SALE   │
├─────────────────────┤
│ Step 1: Scrape      │
│ [Cooldown 5 min]    │
│ Step 2: GPT Photo   │
│ [Cooldown 3 min]    │
│ Step 3: GPT Reorder │
│ [Cooldown 3 min]    │
│ Step 4: Floor Plans │
└──────────┬──────────┘
           │
           ▼
┌─────────────────────┐
│ PHASE 2: SOLD       │
├─────────────────────┤
│ [Cooldown 5 min]    │
│ Step 5: Scrape Sold │
│ [Cooldown 5 min]    │
│ Step 6: Floor Plans │
└──────────┬──────────┘
           │
           ▼
┌─────────────────────┐
│ PHASE 3: MONITORING │
├─────────────────────┤
│ [Cooldown 5 min]    │
│ Step 7: Monitor     │
└──────────┬──────────┘
           │
           ▼
┌─────────────────────┐
│ PHASE 4: CLEANUP    │
├─────────────────────┤
│ 1. Wait 5 min       │
│ 2. Take Post-Backup │
│ 3. Resume Backup Svc│
│ 4. Send Completion  │
│    Notification     │
└─────────────────────┘
```

---

## Cooldown Strategy for MongoDB Stability

To prevent MongoDB instability from too many concurrent operations:

| After Step | Cooldown | Reason |
|------------|----------|--------|
| Step 1 (Scrape For-Sale) | 5 minutes | Heavy write operation just completed |
| Step 2 (GPT Photo) | 3 minutes | Moderate read/write completed |
| Step 3 (GPT Reorder) | 3 minutes | Moderate read/write completed |
| Step 4 (Floor Plans) | 5 minutes | Before switching to sold pipeline |
| Step 5 (Scrape Sold) | 5 minutes | Heavy write operation just completed |
| Step 6 (Floor Plans Sold) | 5 minutes | Before monitoring phase |
| Step 7 (Monitor) | 5 minutes | Before backup operations |

**Total estimated cooldown time:** ~31 minutes
**Total estimated process time:** ~2-3 hours (depending on property count)

---

## Backup Coordination Strategy

### Before Pipeline Starts:
1. Send signal to pause `continuous_mongodb_backup.sh`
2. Wait for any in-progress backup to complete (check for lock file)
3. Trigger one final backup before starting
4. Wait 2 minutes for backup to complete

### During Pipeline:
- No backups run (service is paused)
- MongoDB has full resources for scraping operations

### After Pipeline Completes:
1. Wait 5 minutes for MongoDB to stabilize
2. Trigger a post-pipeline backup
3. Resume `continuous_mongodb_backup.sh` service
4. Normal 30-minute backup cycle resumes

### Implementation:
- Create a lock file `/tmp/orchestrator_running.lock` when pipeline starts
- Modify backup script to check for this lock file
- Or use a more elegant approach: send SIGSTOP/SIGCONT to backup process

---

## File Structure

```
/Users/projects/Documents/Fields_Orchestrator/
├── ORCHESTRATOR_PLAN.md          # This document
├── README.md                      # User documentation
├── config/
│   ├── settings.yaml             # Configuration file
│   └── process_commands.yaml     # Process definitions
├── src/
│   ├── __init__.py
│   ├── orchestrator_daemon.py    # Main daemon
│   ├── notification_manager.py   # macOS notifications
│   ├── task_executor.py          # Process runner
│   ├── backup_coordinator.py     # Backup management
│   ├── mongodb_monitor.py        # DB health checks
│   └── logger.py                 # Logging utilities
├── scripts/
│   ├── start_orchestrator.sh     # Start the daemon
│   ├── stop_orchestrator.sh      # Stop the daemon
│   └── manual_run.sh             # Manual trigger
├── logs/
│   └── orchestrator.log          # Log files
└── launchd/
    └── com.fields.orchestrator.plist  # macOS LaunchAgent
```

---

## Configuration File (settings.yaml)

```yaml
schedule:
  trigger_time: "20:30"  # 8:30 PM
  timezone: "Australia/Brisbane"
  snooze_duration_minutes: 30

mongodb:
  uri: "mongodb://127.0.0.1:27017/"
  database: "property_data"
  health_check_interval: 30  # seconds
  cooldown_after_heavy_write: 300  # 5 minutes
  cooldown_after_moderate_write: 180  # 3 minutes

backup:
  pause_before_pipeline: true
  backup_before_start: true
  backup_after_complete: true
  backup_script_path: "/Users/projects/Documents/SSD_DRIVE/scripts/continuous_mongodb_backup.sh"
  lock_file: "/tmp/orchestrator_running.lock"

notifications:
  use_modal_dialog: true
  completion_notification: true
  error_notification: true

logging:
  level: "INFO"
  file: "logs/orchestrator.log"
  max_size_mb: 10
  backup_count: 5
```

---

## macOS Integration

### LaunchAgent for Auto-Start
The orchestrator will be installed as a macOS LaunchAgent that:
- Starts automatically on login
- Runs in the background
- Restarts if it crashes

### Notification Implementation
Using AppleScript for modal dialogs:
```applescript
display dialog "Property Data Update Scheduled" & return & return & ¬
    "The automated data collection is ready to begin." & return & ¬
    "This process requires full browser mode and will take 2-3 hours." & return & return & ¬
    "Would you like to start now or wait 30 minutes?" ¬
    buttons {"Wait 30 Minutes", "Start Now"} ¬
    default button "Start Now" ¬
    with icon caution ¬
    giving up after 300
```

This creates a dialog that:
- Appears on top of all windows
- Has two buttons for user choice
- Times out after 5 minutes (defaults to "Start Now")

---

## Error Handling

### Process Failures
- If any step fails, log the error and continue to next step
- Send notification about the failure
- At end, provide summary of what succeeded/failed

### MongoDB Connection Issues
- If MongoDB is unreachable, wait and retry (up to 5 attempts)
- If still unreachable, abort pipeline and notify user

### Backup Failures
- If pre-backup fails, warn but continue with pipeline
- If post-backup fails, retry once, then warn user

---

## Questions for User Before Implementation

1. **Timeout Behavior:** If you don't respond to the notification within 5 minutes, should it:
   - Auto-start the pipeline?
   - Auto-snooze for 30 minutes?
   - Keep waiting indefinitely?

2. **Weekend Behavior:** Should the orchestrator run on weekends, or only weekdays?

3. **Error Recovery:** If a step fails, should the orchestrator:
   - Skip it and continue to the next step?
   - Abort the entire pipeline?
   - Retry the failed step once?

4. **Progress Notifications:** Would you like progress notifications during the pipeline (e.g., "Step 2 of 7 complete")?

5. **Manual Override:** Would you like a way to manually trigger the pipeline outside of the scheduled time?

---

## Next Steps

Once you approve this plan (with any modifications), I will:

1. Create the directory structure
2. Implement the Python modules
3. Create the configuration files
4. Set up the LaunchAgent for auto-start
5. Create start/stop scripts
6. Test the notification system
7. Document the system in README.md

---

## Estimated Implementation Time

- Core orchestrator: ~2 hours
- Notification system: ~30 minutes
- Backup coordination: ~1 hour
- Testing and refinement: ~1 hour
- Documentation: ~30 minutes

**Total: ~5 hours**
