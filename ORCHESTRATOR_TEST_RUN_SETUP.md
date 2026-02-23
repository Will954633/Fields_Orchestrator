# Orchestrator Complete Test Run Setup
**Last Updated: 04/02/2026, 2:29 PM (Brisbane Time)**

## 🎯 Test Objective
Test the complete orchestrator with the new Gold Coast monitoring integration to verify:
1. Automatic startup via delayed trigger
2. All 13 processes load correctly
3. Schedule manager applies correct filtering
4. Pipeline executes successfully
5. Logs capture all activity

---

## ⏰ Test Schedule

### **Trigger Setup:**
- **Script Started:** 2026-02-04 14:28:26
- **Scheduled Start:** 2026-02-04 14:30:26 (2-minute delay)
- **Current Time:** 2026-02-04 14:29:14
- **Time Until Start:** ~1 minute 12 seconds

### **Test Script:**
```bash
/Users/projects/Documents/Fields_Orchestrator/scripts/test_orchestrator_delayed.sh
```

**Status:** ✅ Running in background

---

## 📋 What Will Happen

### **At 14:30:26 (Scheduled Start Time):**

1. **Orchestrator Initialization:**
   - Load configuration from `config/settings.yaml`
   - Load process commands from `config/process_commands.yaml`
   - Initialize Schedule Manager
   - Initialize Task Executor
   - Initialize MongoDB Monitor
   - Initialize Backup Coordinator

2. **Process Loading:**
   - Load all 13 process configurations
   - Validate process definitions
   - Initialize process metadata

3. **Schedule Manager Filtering:**
   - Check current day (Tuesday)
   - Apply target market rules (daily execution)
   - Apply other suburbs rules (Sunday only)
   - Filter processes based on schedule

4. **Pipeline Execution:**
   - Execute filtered processes in sequence
   - Apply cooldowns between processes
   - Log progress for each step
   - Handle any errors with retries

5. **Backup Phase:**
   - Apply 300s cooldown before backup
   - Perform MongoDB backup
   - Log backup results

---

## 📊 Expected Process Execution

### **Processes That Should Run (Tuesday):**

#### **Target Market Processes (Daily):**
- ✅ Process 101: Gold Coast Target Market - For Sale Scraping
- ✅ Process 103: Gold Coast Target Market - Photo Analysis
- ✅ Process 105: Gold Coast Target Market - Floor Plan Analysis
- ✅ Process 106: Gold Coast Target Market - Sold Monitor

#### **Always Run Processes:**
- ✅ Process 6: Property Valuation
- ✅ Process 11: Backend - Valuation Comps
- ✅ Process 12: Backend - Suburb Stats
- ✅ Process 13: Backend - Property Type Race
- ✅ Process 14: Backend - Median Price History
- ✅ Process 15: Backend - Sold Properties
- ✅ Process 16: Backend - Floor Plans

**Total Expected:** 11 processes

### **Processes That Should NOT Run (Tuesday):**
- ❌ Process 102: Gold Coast Other Suburbs - For Sale Scraping (Sunday only)
- ❌ Process 104: Gold Coast Other Suburbs - Sold Monitor (Sunday only)

---

## 🔍 Monitoring Commands

### **Watch Logs in Real-Time:**
```bash
cd /Users/projects/Documents/Fields_Orchestrator && ./scripts/monitor_test.sh
```

### **Check Last 50 Lines:**
```bash
cd /Users/projects/Documents/Fields_Orchestrator && tail -50 logs/orchestrator.log
```

### **Check Background Process Status:**
```bash
ps aux | grep test_orchestrator_delayed
```

### **Check Orchestrator Process:**
```bash
ps aux | grep orchestrator_daemon
```

---

## ✅ Success Criteria

### **1. Initialization Success:**
- [ ] All configuration files loaded
- [ ] Schedule Manager initialized
- [ ] 13 processes loaded
- [ ] MongoDB connection established

### **2. Schedule Filtering Success:**
- [ ] Target market processes identified (101, 103, 105, 106)
- [ ] Other suburbs processes excluded (102, 104)
- [ ] Always-run processes included (6, 11-16)
- [ ] Total: 11 processes scheduled

### **3. Execution Success:**
- [ ] All 11 processes start
- [ ] Progress logged for each process
- [ ] Cooldowns applied correctly
- [ ] No critical errors

### **4. Backup Success:**
- [ ] 300s cooldown before backup
- [ ] Backup initiated
- [ ] Backup completed (or gracefully handled if permissions issue)

### **5. Logging Success:**
- [ ] All events captured in logs
- [ ] Timestamps accurate
- [ ] Status updates clear
- [ ] Errors properly logged

---

## 📝 Key Log Markers to Watch For

### **Startup:**
```
FIELDS ORCHESTRATOR DAEMON STARTED
Loaded 13 process configurations
Schedule Manager initialized
Target market suburbs: 8
```

### **Schedule Filtering:**
```
Applying schedule filters...
Target market processes (daily): [101, 103, 105, 106]
Other suburbs processes (Sunday only): [102, 104]
Always run processes: [6, 11, 12, 13, 14, 15, 16]
```

### **Process Execution:**
```
Starting pipeline execution...
Step X (Process Name): running
Step X (Process Name): completed
```

### **Backup Phase:**
```
Applying 300s cooldown before backup...
Starting daily backup...
STARTING DAILY MONGODB BACKUP
```

---

## 🚨 Known Issues to Monitor

### **Backup Permissions:**
Previous runs showed permission errors with backup directories:
```
Operation not permitted: '/Users/projects/Documents/MongdbBackups/.last_daily_rotation'
```

**Expected Behavior:** This is a known issue and won't affect the main pipeline test. The orchestrator should handle this gracefully and continue.

### **MongoDB Connection:**
Ensure MongoDB is running:
```bash
mongosh --eval "db.adminCommand('ping')"
```

---

## 📂 Important Files

### **Configuration:**
- `config/settings.yaml` - Main orchestrator settings
- `config/process_commands.yaml` - Process definitions

### **Source Code:**
- `src/orchestrator_daemon.py` - Main daemon
- `src/task_executor.py` - Process execution
- `src/schedule_manager.py` - Schedule filtering
- `src/mongodb_monitor.py` - Database monitoring

### **State Files:**
- `state/orchestrator_state.json` - Persistent state
- `state/last_run_summary.json` - Last run results

### **Logs:**
- `logs/orchestrator.log` - Main log file

---

## 🎬 Next Steps After Test

1. **Review Logs:** Check for any errors or warnings
2. **Verify Process Execution:** Confirm correct processes ran
3. **Check MongoDB:** Verify data was updated
4. **Analyze Performance:** Review execution times
5. **Document Results:** Create test results summary

---

## 📞 Test Status

**Current Status:** ⏳ WAITING FOR AUTOMATIC START

**Countdown:** ~1 minute until orchestrator starts

**Monitor:** Watch `logs/orchestrator.log` for activity starting at 14:30:26

---

## 🔗 Related Documentation

- [NEW_PROCESS_INTEGRATION_COMPLETE.md](NEW_PROCESS_INTEGRATION_COMPLETE.md) - Integration completion summary
- [NEW_PROCESS_INTEGRATION_PLAN.md](NEW_PROCESS_INTEGRATION_PLAN.md) - Original integration plan
- [config/process_commands.yaml](config/process_commands.yaml) - Process definitions
- [config/settings.yaml](config/settings.yaml) - Orchestrator settings
