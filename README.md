# Fields Property Data Orchestrator

**Last Updated:** 27/01/2026, 2:32 PM (Monday) - Brisbane Time

---

## Overview

The Fields Orchestrator is an automated system that runs the property data collection pipeline every night at 8:30 PM Brisbane time. It coordinates 7 data collection processes plus a daily MongoDB backup, with careful management of database operations to prevent instability.

### Key Features

- 🕐 **Scheduled Execution** - Triggers at 8:30 PM daily
- 💬 **User Confirmation** - Shows dialog before starting (Start Now / Wait 30 Min)
- 📊 **Progress Window** - Real-time status updates visible in the morning
- 🔄 **Auto-Retry** - Failed steps retry twice before continuing
- 💾 **Daily Backup** - MongoDB backup after pipeline completion
- ⏱️ **Cooldown Periods** - Prevents MongoDB instability between operations

---

## Quick Start

### 1. Install Dependencies

```bash
cd /Users/projects/Documents/Fields_Orchestrator && pip3 install pyyaml pymongo
```

### 2. Start the Orchestrator

```bash
cd /Users/projects/Documents/Fields_Orchestrator/scripts && ./start_orchestrator.sh
```

### 3. (Optional) Enable Auto-Start on Login

```bash
cp /Users/projects/Documents/Fields_Orchestrator/launchd/com.fields.orchestrator.plist ~/Library/LaunchAgents/
launchctl load ~/Library/LaunchAgents/com.fields.orchestrator.plist
```

---

## Directory Structure

```
/Users/projects/Documents/Fields_Orchestrator/
├── README.md                    # This file
├── ORCHESTRATOR_PLAN.md         # Detailed design document
├── Notes.md                     # Development notes
│
├── config/
│   ├── settings.yaml            # Main configuration
│   └── process_commands.yaml    # Process definitions
│
├── src/
│   ├── __init__.py
│   ├── orchestrator_daemon.py   # Main daemon
│   ├── notification_manager.py  # GUI window & notifications
│   ├── task_executor.py         # Process execution
│   ├── backup_coordinator.py    # MongoDB backup
│   ├── mongodb_monitor.py       # DB health & cooldowns
│   └── logger.py                # Logging utilities
│
├── scripts/
│   ├── start_orchestrator.sh    # Start the daemon
│   ├── stop_orchestrator.sh     # Stop the daemon
│   └── manual_run.sh            # Run pipeline immediately
│
├── launchd/
│   └── com.fields.orchestrator.plist  # macOS auto-start config
│
├── logs/                        # Log files (auto-created)
│   └── orchestrator.log
│
└── state/                       # State files (auto-created)
    ├── orchestrator_state.json
    └── window_state.json
```

---

## Usage

### Starting the Orchestrator

```bash
cd /Users/projects/Documents/Fields_Orchestrator/scripts && ./start_orchestrator.sh
```

The daemon will:
1. Run in the background
2. Check the time every minute
3. At 8:30 PM, show a notification and status window
4. Wait for your confirmation before starting

### Stopping the Orchestrator

```bash
cd /Users/projects/Documents/Fields_Orchestrator/scripts && ./stop_orchestrator.sh
```

### Manual Pipeline Run

To run the pipeline immediately (bypassing the schedule):

```bash
cd /Users/projects/Documents/Fields_Orchestrator/scripts && ./manual_run.sh
```

Or use the "Run Now (Manual)" button in the status window.

### Checking Status

```bash
# Check if daemon is running
ps aux | grep orchestrator_daemon

# View logs
tail -f /Users/projects/Documents/Fields_Orchestrator/logs/orchestrator.log

# Check LaunchAgent status (if installed)
launchctl list | grep fields.orchestrator
```

---

## Pipeline Steps

The orchestrator runs these 10 steps in sequence:

| Step | Name | Duration | Description |
|------|------|----------|-------------|
| 1 | Monitor Sold Transitions | ~40 min | Detects properties that have sold |
| 2 | Scrape For-Sale Properties | ~22 min | Scrapes Domain.com.au for current listings |
| 3 | GPT Photo Analysis | ~155 min | Analyzes property photos with GPT Vision |
| 4 | GPT Photo Reorder | ~160 min | Creates optimal photo tour sequence |
| 5 | Floor Plan Enrichment | ~30 min | Extracts room dimensions from floor plans |
| 9 | Floor Plan V2 Processing | ~75 min | Processes floor plans with OCR and text wiping |
| 10 | Room-to-Photo Matching | ~100 min | Matches floor plan rooms to photos (86% accuracy) |
| 6 | Property Valuation Model | ~45 min | Predicts property values |
| 7 | Scrape Sold Properties | ~75 min | Scrapes recently sold properties |
| 8 | Floor Plan Enrichment (Sold) | ~30 min | Floor plan analysis for sold properties |
| Backup | Daily Backup | ~10 min | MongoDB backup to 3 locations |

**Total estimated time: 5-6 hours**

### Cooldown Periods

To prevent MongoDB instability, cooldown periods are applied between steps:
- After heavy write operations (scraping): 5 minutes
- After moderate operations (GPT/enrichment): 3 minutes
- Before backup: 5 minutes

---

## Configuration

### Main Settings (`config/settings.yaml`)

```yaml
schedule:
  trigger_time: "20:30"  # 8:30 PM
  snooze_duration_minutes: 30
  run_on_weekends: true

mongodb:
  uri: "mongodb://127.0.0.1:27017/"
  database: "property_data"
  cooldown_after_heavy_write: 300  # 5 minutes
  cooldown_after_moderate_write: 180  # 3 minutes

process_execution:
  max_retries_per_step: 2  # Retry failed steps twice

backup:
  primary_dir: "/Volumes/T7/MongdbBackups"
  secondary_dir: "/Users/projects/Documents/MongdbBackups"
  tertiary_dir: "/Volumes/My Passport for Mac/MongdbBackups"
```

### Process Commands (`config/process_commands.yaml`)

Defines each pipeline step with:
- Command to execute
- Working directory
- MongoDB activity level
- Cooldown duration
- Estimated duration

---

## Status Window

The status window shows:

```
┌─────────────────────────────────────────────────┐
│  🏠 Fields Property Data Orchestrator           │
├─────────────────────────────────────────────────┤
│  Status: Running pipeline...                    │
│                                                 │
│  [Start Now]  [Wait 30 Min]  [Run Now (Manual)] │
│                                                 │
│  Progress:                                      │
│  ✅ Step 1: Scrape For-Sale (32m)              │
│  ✅ Step 2: GPT Photo Analysis (48m)           │
│  🔄 Step 3: GPT Photo Reorder (running...)     │
│  ⏳ Step 4: Floor Plan Enrichment              │
│  ⏳ Step 5: Scrape Sold Properties             │
│  ⏳ Step 6: Floor Plan Enrichment (Sold)       │
│  ⏳ Step 7: Monitor Sold Transitions           │
│  ⏳ Step 8: Daily Backup                       │
│                                                 │
│  Last Run: 25/01/2026 22:45 - All completed ✅ │
└─────────────────────────────────────────────────┘
```

**Status Icons:**
- ⏳ Pending
- 🔄 Running
- ✅ Completed
- ❌ Failed
- 🔁 Retrying

---

## Backup System

The orchestrator performs a daily MongoDB backup after the pipeline completes.

### Backup Locations

1. **Primary:** `/Volumes/T7/MongdbBackups` (External T7 SSD)
2. **Secondary:** `/Users/projects/Documents/MongdbBackups` (Internal SSD)
3. **Tertiary:** `/Volumes/My Passport for Mac/MongdbBackups` (My Passport)

### Retention Policy

| Slot | Description |
|------|-------------|
| `backup_latest` | Most recent backup (after pipeline) |
| `backup_yesterday` | Yesterday's backup |
| `backup_3days` | 3-day-old backup |
| `backup_5days` | 5-day-old backup |

### Restoring from Backup

```bash
# Restore from latest backup
mongorestore --uri="mongodb://127.0.0.1:27017/" --gzip /Volumes/T7/MongdbBackups/backup_latest

# Restore from yesterday's backup
mongorestore --uri="mongodb://127.0.0.1:27017/" --gzip /Volumes/T7/MongdbBackups/backup_yesterday
```

---

## Auto-Start on Login

To have the orchestrator start automatically when you log in:

### Install LaunchAgent

```bash
# Copy the plist file
cp /Users/projects/Documents/Fields_Orchestrator/launchd/com.fields.orchestrator.plist ~/Library/LaunchAgents/

# Load the agent
launchctl load ~/Library/LaunchAgents/com.fields.orchestrator.plist
```

### Uninstall LaunchAgent

```bash
# Unload the agent
launchctl unload ~/Library/LaunchAgents/com.fields.orchestrator.plist

# Remove the plist file
rm ~/Library/LaunchAgents/com.fields.orchestrator.plist
```

### Check Status

```bash
launchctl list | grep fields.orchestrator
```

---

## Troubleshooting

### Orchestrator Won't Start

1. Check if already running:
   ```bash
   ps aux | grep orchestrator_daemon
   ```

2. Remove stale lock file:
   ```bash
   rm /tmp/fields_orchestrator.lock /tmp/fields_orchestrator.pid
   ```

3. Check logs:
   ```bash
   tail -100 /Users/projects/Documents/Fields_Orchestrator/logs/orchestrator.log
   ```

### MongoDB Connection Issues

1. Ensure MongoDB is running:
   ```bash
   brew services list | grep mongodb
   # or
   mongosh --eval "db.adminCommand('ping')"
   ```

2. Start MongoDB if needed:
   ```bash
   brew services start mongodb-community
   ```

### Pipeline Step Fails

- Steps automatically retry twice before continuing
- Check the log file for error details
- The status window shows which steps failed
- You can re-run the pipeline manually after fixing issues

### Notification Not Appearing

- Ensure "System Events" has permission in System Preferences > Security & Privacy > Privacy > Accessibility
- The orchestrator uses AppleScript for dialogs which requires accessibility permissions

---

## Disabling the Old Backup System

Since the orchestrator now handles daily backups, you should disable the old 30-minute continuous backup:

```bash
# Stop the old backup service
launchctl unload ~/Library/LaunchAgents/com.projects.mongodb_continuous_backup.plist

# Or if running manually, find and kill the process
ps aux | grep continuous_mongodb_backup
kill <PID>
```

---

## Development

### Running Tests

```bash
cd /Users/projects/Documents/Fields_Orchestrator

# Test logger
python3 -c "from src.logger import setup_logger; setup_logger(level='DEBUG'); print('Logger OK')"

# Test MongoDB monitor
python3 -c "from src.mongodb_monitor import MongoDBMonitor; m = MongoDBMonitor(); print('Connected:', m.check_connection())"

# Test notification (shows dialog)
python3 -c "from src.notification_manager import NotificationManager; n = NotificationManager(); n.show_system_notification('Test', 'Hello!')"
```

### Log Levels

Set in `config/settings.yaml`:
- `DEBUG` - Verbose output for development
- `INFO` - Normal operation (default)
- `WARNING` - Only warnings and errors
- `ERROR` - Only errors

---

## Support

For issues or questions:
1. Check the logs: `/Users/projects/Documents/Fields_Orchestrator/logs/orchestrator.log`
2. Review the design document: `ORCHESTRATOR_PLAN.md`
3. Check process configurations: `config/process_commands.yaml`

---

## Version History

| Version | Date | Changes |
|---------|------|---------|
| 1.1.0 | 27/01/2026 | Added Floor Plans V2 Processing and Room-to-Photo Matching |
| 1.0.0 | 26/01/2026 | Initial release |
