# Fields Orchestrator - Development Notes

**Last Updated:** 26/01/2026, 7:59 PM (Brisbane Time)

---

## Important Considerations

### MongoDB Stability
- Too many read/write commands at once makes local MongoDB unstable
- This system implements cooldown periods between operations (3-5 minutes)
- Heavy write operations (scraping) get 5-minute cooldowns
- Moderate operations (GPT analysis) get 3-minute cooldowns

### Backup Strategy
- Replaced the 30-minute continuous backup with daily backup after pipeline
- Backup runs AFTER all 7 data collection steps complete
- Maintains 4 backup slots: latest, yesterday, 3-days, 5-days
- Backs up to 3 locations for redundancy

### Browser Mode
- Steps 1, 5, and 7 require full-head browser mode (Selenium)
- User cannot use the computer during these operations
- This is why user confirmation is required before starting

---

## System Status

✅ **Orchestrator Built:** 26/01/2026
✅ **All Python modules created**
✅ **Shell scripts created and made executable**
✅ **LaunchAgent plist created**
✅ **Documentation complete**

---

## Quick Commands

```bash
# Start the orchestrator
cd /Users/projects/Documents/Fields_Orchestrator/scripts && ./start_orchestrator.sh

# Stop the orchestrator
cd /Users/projects/Documents/Fields_Orchestrator/scripts && ./stop_orchestrator.sh

# Manual run (immediate)
cd /Users/projects/Documents/Fields_Orchestrator/scripts && ./manual_run.sh

# View logs
tail -f /Users/projects/Documents/Fields_Orchestrator/logs/orchestrator.log

# Install auto-start
cp /Users/projects/Documents/Fields_Orchestrator/launchd/com.fields.orchestrator.plist ~/Library/LaunchAgents/
launchctl load ~/Library/LaunchAgents/com.fields.orchestrator.plist
```

---

## Disable Old Backup System

Since this orchestrator handles daily backups, disable the old 30-minute backup:

```bash
# If using launchd
launchctl unload ~/Library/LaunchAgents/com.projects.mongodb_continuous_backup.plist

# If running manually
ps aux | grep continuous_mongodb_backup
kill <PID>
```
