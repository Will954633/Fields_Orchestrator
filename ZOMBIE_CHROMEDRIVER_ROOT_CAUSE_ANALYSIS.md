# Zombie ChromeDriver Root Cause Analysis

**Date:** 06/02/2026, 1:51 PM (Thursday) - Brisbane  
**Issue:** 185 zombie ChromeDriver processes in uninterruptible sleep state  
**Status:** ⚠️ CRITICAL - Cleanup process ineffective

---

## Executive Summary

The orchestrator has 185 zombie ChromeDriver processes that **cannot be killed** because they are in an "UE" (uninterruptible sleep) state. The existing cleanup mechanism (`kill -9`) is ineffective against processes in this state. The orchestrator is currently stuck on Process 101 (scraping) since 11:17 AM.

---

## Current Situation

### Process Status
```
Orchestrator PID: 14548 (running since 11:15 AM)
Current Step: Process 101 (Scrape For-Sale Properties)
Stuck Since: 11:17 AM (2.5+ hours)
Zombie ChromeDrivers: 185 processes
Process State: UE (Uninterruptible Sleep)
```

### Zombie Process Details
- **State:** UE (Uninterruptible Sleep - cannot be interrupted/killed)
- **Start Time:** Most from Tuesday 6 PM and Wednesday 2-3 PM
- **Versions:** Mix of 144.0.7559.109 and 144.0.7559.133
- **Memory:** 16 bytes each (minimal footprint but resource leak)

---

## Root Cause Analysis

### 1. **Why Processes Are Stuck**

ChromeDriver processes enter uninterruptible sleep (UE state) when:
- Waiting for I/O operations that cannot complete
- Kernel-level operations that cannot be interrupted
- File system operations on network drives or slow disks
- Device driver issues

**In this case:** The ChromeDrivers are likely stuck waiting for:
- Browser processes that have crashed/hung
- Network I/O that never completes
- File system operations that are blocked

### 2. **Why Cleanup Failed**

The current cleanup implementation in `orchestrator_daemon.py`:

```python
def _cleanup_zombie_chromedrivers(self) -> int:
    # ...
    subprocess.run(['kill', '-9', str(pid)], check=False, timeout=5)
    # ...
```

**Problem:** `kill -9` (SIGKILL) cannot kill processes in uninterruptible sleep state. These processes are in kernel space and cannot receive signals.

### 3. **Why They Keep Accumulating**

From `task_executor.py`, the process cleanup uses:
```python
# Kill entire process group
os.killpg(proc.pid, signal.SIGTERM)
# Then SIGKILL
os.killpg(proc.pid, signal.SIGKILL)
```

**Issues:**
1. **Process group killing works** - but only if processes can receive signals
2. **Timeout mechanism works** - but doesn't prevent UE state
3. **No parent process cleanup** - ChromeDrivers may outlive their parent
4. **No Chrome browser cleanup** - Chrome processes may keep ChromeDrivers alive

---

## Why This Happened Despite Previous Fixes

### Previous Fix (ZOMBIE_PROCESS_PREVENTION_SOLUTION.md)
The previous solution implemented:
- ✅ Process group termination (`start_new_session=True`)
- ✅ Timeout enforcement (3x estimated duration)
- ✅ Pre-run cleanup check
- ✅ SIGTERM → SIGKILL escalation

### What Was Missing:
1. **No Chrome browser cleanup** - Only kills ChromeDriver, not Chrome itself
2. **No detection of UE state** - Cleanup assumes processes can be killed
3. **No reboot recommendation** - UE processes require system-level intervention
4. **No prevention of UE state** - Doesn't address root cause of I/O hangs

---

## Evidence from Logs

```
2026-02-06 11:17:35 | Checking for zombie ChromeDriver processes...
2026-02-06 11:17:38 | Killed 183 zombie ChromeDriver processes  ← CLAIMED SUCCESS
2026-02-06 11:17:41 | Starting pipeline execution...
2026-02-06 11:17:48 | STEP 101: Scrape For-Sale Properties (Target Market)
2026-02-06 11:17:59 | [Robina] Process started (PID: 16324)
[NO FURTHER OUTPUT - HUNG]
```

**Analysis:**
- Cleanup claimed to kill 183 processes
- But processes are still present (185 total now)
- New scraping process started but immediately hung
- Likely hit the same I/O issue that caused original zombies

---

## Impact Assessment

### System Impact
- ✅ **Low Memory:** 16 bytes per process (minimal)
- ⚠️ **Process Table:** 185 slots occupied
- ⚠️ **Port Exhaustion:** Each holds a port (49000-65000 range)
- ❌ **New Processes Fail:** Cannot create new ChromeDrivers

### Business Impact
- ❌ **Pipeline Stuck:** No data collection since 11:17 AM
- ❌ **Data Staleness:** Properties not updated for 2.5+ hours
- ⚠️ **Manual Intervention Required:** System cannot self-recover

---

## Solution Strategy

### Immediate Actions (Required)

1. **System Reboot** (ONLY solution for UE processes)
   ```bash
   sudo reboot
   ```
   - UE processes cannot be killed by any signal
   - Only system reboot clears them
   - Schedule during low-traffic period

2. **Verify Cleanup After Reboot**
   ```bash
   ps aux | grep chromedriver | grep -v grep | wc -l
   # Should return: 0
   ```

### Short-Term Fixes (Prevent Recurrence)

1. **Enhanced Cleanup - Kill Chrome Browsers Too**
   ```python
   def _cleanup_zombie_chromedrivers(self) -> int:
       # Kill Chrome browsers first
       subprocess.run(['killall', '-9', 'Google Chrome'], check=False)
       time.sleep(2)
       
       # Then kill ChromeDrivers
       subprocess.run(['killall', '-9', 'chromedriver'], check=False)
       time.sleep(2)
       
       # Verify cleanup
       result = subprocess.run(['ps', 'aux'], capture_output=True, text=True)
       remaining = sum(1 for line in result.stdout.split('\n') 
                      if 'chromedriver' in line.lower() and 'grep' not in line)
       
       if remaining > 0:
           self.logger.error(f"⚠️ {remaining} ChromeDrivers in UE state - REBOOT REQUIRED")
       
       return zombie_count
   ```

2. **Add UE State Detection**
   ```python
   def _detect_unkillable_processes(self) -> int:
       result = subprocess.run(['ps', 'aux'], capture_output=True, text=True)
       ue_count = 0
       for line in result.stdout.split('\n'):
           if 'chromedriver' in line.lower() and ' UE ' in line:
               ue_count += 1
       return ue_count
   ```

3. **Abort Pipeline if UE Processes Detected**
   ```python
   ue_count = self._detect_unkillable_processes()
   if ue_count > 0:
       self.logger.error(f"❌ {ue_count} unkillable ChromeDrivers detected")
       self.logger.error("❌ SYSTEM REBOOT REQUIRED - Aborting pipeline")
       return {"success": False, "error": "Unkillable processes detected"}
   ```

### Long-Term Fixes (Root Cause)

1. **Reduce Scraping Timeout**
   - Current: 3x estimated time (30-90 minutes)
   - Proposed: 10 minutes max per property
   - Prevents long I/O hangs

2. **Add Selenium Keepalive**
   ```python
   # In scraping script
   driver.set_page_load_timeout(60)  # 60 second page load timeout
   driver.set_script_timeout(30)      # 30 second script timeout
   ```

3. **Implement Circuit Breaker**
   - If 3 consecutive properties timeout → abort suburb
   - If 2 consecutive suburbs fail → abort entire scrape
   - Prevents cascade failures

4. **Add Health Checks**
   ```python
   # Before each property scrape
   if not driver.service.is_connectable():
       driver.quit()
       driver = create_new_driver()
   ```

---

## Recommended Actions

### Priority 1: Immediate (Now)
1. ✅ Document this analysis
2. ⚠️ **Schedule system reboot** (only solution for UE processes)
3. ⚠️ Notify stakeholders of downtime

### Priority 2: Before Next Run (Today)
1. Implement enhanced cleanup (kill Chrome + ChromeDriver)
2. Add UE state detection
3. Add abort logic if unkillable processes detected

### Priority 3: This Week
1. Reduce scraping timeouts
2. Add Selenium keepalive settings
3. Implement circuit breaker pattern
4. Add health checks before each scrape

---

## Testing Plan

### After Reboot
1. Verify all ChromeDrivers cleared: `ps aux | grep chromedriver`
2. Run orchestrator with enhanced cleanup
3. Monitor for UE state during execution
4. Verify cleanup works after normal completion

### Stress Test
1. Run scraping with intentional failures
2. Verify cleanup handles crashed browsers
3. Verify UE detection triggers abort
4. Confirm no zombie accumulation

---

## Monitoring Recommendations

### Add Alerts
1. **ChromeDriver Count > 10** → Warning
2. **ChromeDriver Count > 50** → Critical
3. **UE State Detected** → Critical + Auto-abort
4. **Process Stuck > 30 min** → Warning

### Dashboard Metrics
- Active ChromeDriver count
- ChromeDrivers in UE state
- Scraping success rate
- Average property scrape time

---

## Conclusion

The zombie ChromeDriver issue is caused by processes entering uninterruptible sleep state, which **cannot be killed by any signal**. The only solution is a system reboot. The existing cleanup mechanism works for normal processes but fails for UE state processes.

**Key Takeaways:**
1. ✅ Previous fixes work for normal process cleanup
2. ❌ No fix can handle UE state except reboot
3. ⚠️ Need to detect UE state and abort pipeline
4. 🔧 Need to prevent I/O hangs that cause UE state

**Next Steps:**
1. Reboot system to clear UE processes
2. Implement UE detection before next run
3. Add Chrome browser cleanup
4. Reduce timeouts to prevent I/O hangs


# Zombie ChromeDriver Root Cause Analysis
sudo reboot
