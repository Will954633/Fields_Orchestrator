# Orchestrator Scraping Hang Issue
**Last Updated: 05/02/2026, 9:23 AM (Thursday) - Brisbane**

## Issue Summary

The orchestrator was triggered successfully but became stuck on Step 101 (Scrape For-Sale Properties) for over 14 hours. Chrome processes from 6:59 PM yesterday were still running at 9:22 AM today, indicating the scraping process hung and never completed.

---

## Timeline

- **08:35:39** - Orchestrator started successfully
- **08:35:49** - Robina scraping process started (PID: 93541)
- **08:35:59** - Mudgeeraba scraping process started (PID: 93635)
- **08:35:59** - Last log entry in orchestrator.log
- **18:59:00** (6:59 PM) - Chrome processes still running (from previous day)
- **09:22:00** - Discovered orchestrator stuck, Chrome processes consuming CPU
- **09:22:40** - Killed stuck orchestrator and Chrome processes

---

## Root Cause Analysis

### Primary Issue: Scraping Process Hang

The scraping process (`run_dynamic_10_suburbs.py`) appears to have hung during execution. Possible causes:

1. **Website Timeout/Blocking**
   - Domain.com.au may have rate-limited or blocked the scraper
   - Page load timeouts not properly handled
   - Anti-bot detection triggered

2. **Chrome/Puppeteer Issue**
   - Chrome browser hung on a specific page
   - Puppeteer connection lost but process didn't terminate
   - Memory leak causing browser to freeze

3. **Network Issues**
   - Network connectivity problems during scraping
   - DNS resolution failures
   - Proxy/firewall blocking

4. **Code Bug**
   - Infinite loop in scraping logic
   - Missing timeout handling
   - Exception not properly caught

### Secondary Issue: No Timeout Protection

The orchestrator doesn't appear to have a timeout mechanism for individual steps. The scraping step was estimated at 6-10 minutes but ran for 14+ hours without being killed.

---

## Evidence

### Chrome Processes (14+ hours old)
```
projects  11687  16.0  0.4  1865681536  277312  ??  S  6:59PM  90:28.58  Chrome Helper (Renderer)
projects  11678  11.6  0.2   461979504  107408  ??  S  6:59PM  84:43.15  Chrome Helper (gpu-process)
```

### Orchestrator Log (Stopped at 08:35:59)
```
2026-02-05 08:35:39 | [92mINFO[0m | [STEP 101 OUTPUT] Starting initial batch of 3 suburbs...
2026-02-05 08:35:49 | [92mINFO[0m | [STEP 101 OUTPUT] [Robina] Process started (PID: 93541)
2026-02-05 08:35:59 | [92mINFO[0m | [STEP 101 OUTPUT] [Mudgeeraba] Process started (PID: 93635)
```

No further log entries after 08:35:59, indicating the orchestrator was waiting for the scraping subprocess to complete.

---

## Impact

### Immediate Impact
- ❌ Orchestrator pipeline did not complete
- ❌ No properties scraped or enriched
- ❌ No sold monitoring performed
- ❌ No photo/floor plan analysis
- ❌ No valuations calculated
- ❌ No backend data generated
- ❌ No backup created

### System Impact
- 🔴 Chrome processes consuming CPU for 14+ hours
- 🔴 Orchestrator process stuck, unable to run scheduled tasks
- 🔴 System resources wasted on hung processes

---

## Resolution Actions Taken

1. ✅ Killed stuck orchestrator process (PID: 98789)
2. ✅ Killed stuck scraping processes
3. ✅ Force-killed all Chrome/Puppeteer processes
4. ✅ Documented issue for future reference

---

## Recommendations

### CRITICAL - Add Timeout Protection

**Priority: HIGH**

Add step-level timeouts to the orchestrator to prevent indefinite hangs:

```python
# In task_executor.py or orchestrator_daemon.py
import signal

class TimeoutException(Exception):
    pass

def timeout_handler(signum, frame):
    raise TimeoutException()

# Before running each step:
signal.signal(signal.SIGALRM, timeout_handler)
signal.alarm(estimated_duration_minutes * 60 * 3)  # 3x estimated time

try:
    # Run step
    result = subprocess.run(...)
except TimeoutException:
    logger.error(f"Step {step_id} timed out after {timeout} seconds")
    # Kill subprocess
    # Mark step as failed
    # Continue to next step or abort
finally:
    signal.alarm(0)  # Cancel alarm
```

**Suggested Timeouts:**
- Step 101 (Scraping): 40 min estimated → 120 min timeout (3x)
- Step 103 (Sold Monitoring): 45 min estimated → 135 min timeout (3x)
- Step 105 (Photo Analysis): 120 min estimated → 360 min timeout (3x)
- Step 106 (Floor Plans): 60 min estimated → 180 min timeout (3x)

### HIGH - Add Scraping Resilience

**Priority: HIGH**

Improve the scraping script (`run_dynamic_10_suburbs.py`) to handle failures gracefully:

1. **Add page-level timeouts**
   ```python
   page.setDefaultTimeout(60000)  # 60 second timeout per page
   page.setDefaultNavigationTimeout(90000)  # 90 second navigation timeout
   ```

2. **Add retry logic with exponential backoff**
   ```python
   max_retries = 3
   for attempt in range(max_retries):
       try:
           # Scrape property
           break
       except TimeoutError:
           if attempt < max_retries - 1:
               wait_time = 2 ** attempt  # 1s, 2s, 4s
               time.sleep(wait_time)
           else:
               logger.error(f"Failed after {max_retries} attempts")
               # Skip property and continue
   ```

3. **Add health checks**
   ```python
   # Check if Chrome is responsive every N properties
   if property_count % 10 == 0:
       try:
           page.evaluate('1 + 1')  # Simple check
       except:
           logger.warning("Chrome unresponsive, restarting browser")
           browser.close()
           browser = launch_browser()
   ```

4. **Add progress logging**
   ```python
   # Log progress every property
   logger.info(f"Scraped {completed}/{total} properties ({completed/total*100:.1f}%)")
   ```

### MEDIUM - Add Monitoring & Alerts

**Priority: MEDIUM**

1. **Add heartbeat logging**
   - Log a heartbeat message every 5 minutes during long-running steps
   - Helps identify when a process actually hung vs. just taking a long time

2. **Add process monitoring**
   - Monitor subprocess CPU/memory usage
   - Kill and restart if usage is abnormal

3. **Add email/SMS alerts**
   - Alert if a step exceeds 2x estimated duration
   - Alert if orchestrator hasn't completed in 6 hours

### LOW - Investigate Domain.com.au Blocking

**Priority: LOW**

1. **Check for rate limiting**
   - Review Domain.com.au's robots.txt
   - Check if IP was temporarily blocked
   - Consider adding delays between requests

2. **Rotate user agents**
   - Use different user agents for each suburb
   - Mimic real browser behavior more closely

3. **Add proxy support**
   - Route requests through rotating proxies if needed
   - Avoid IP-based blocking

---

## Testing Plan

### Phase 1: Add Timeouts
1. Implement step-level timeouts in orchestrator
2. Test with artificially long-running process
3. Verify timeout triggers and cleanup works

### Phase 2: Improve Scraping
1. Add page-level timeouts to scraping script
2. Add retry logic and health checks
3. Test with problematic suburbs (Robina, Mudgeeraba)

### Phase 3: Full Pipeline Test
1. Run complete orchestrator pipeline
2. Monitor for hangs or timeouts
3. Verify all steps complete successfully

---

## Next Steps

### Immediate (Before Next Run)
1. ✅ Document this issue (this file)
2. ⏳ Implement step-level timeouts in orchestrator
3. ⏳ Add page-level timeouts to scraping script
4. ⏳ Test timeout mechanisms

### Short-term (This Week)
1. Add retry logic to scraping
2. Add health checks for Chrome
3. Improve progress logging
4. Test full pipeline with new safeguards

### Long-term (Next Sprint)
1. Add monitoring and alerts
2. Investigate Domain.com.au blocking
3. Consider alternative scraping strategies
4. Implement circuit breaker pattern

---

## Workaround for Now

Until timeouts are implemented, manually monitor orchestrator runs:

```bash
# Start orchestrator
cd /Users/projects/Documents/Fields_Orchestrator && python3 src/orchestrator_daemon.py --run-now

# In another terminal, monitor progress
watch -n 60 'tail -20 /Users/projects/Documents/Fields_Orchestrator/logs/orchestrator.log'

# If stuck for >30 minutes on a step:
# 1. Check if Chrome processes are consuming CPU
ps aux | grep -E "(Chrome|puppeteer)" | grep -v grep

# 2. If stuck, kill orchestrator and Chrome
pkill -f orchestrator_daemon
pkill -f "puppeteer_dev_chrome_profile"

# 3. Restart orchestrator
python3 src/orchestrator_daemon.py --run-now
```

---

## Related Issues

- **ORCHESTRATOR_FAILURE_ANALYSIS.md** - Previous failures (python command, backup timeout)
- **CHROMEDRIVER_TIMEOUT_FIX_COMPLETE.md** - ChromeDriver timeout fixes
- **ORCHESTRATOR_READY_FOR_PRODUCTION.md** - Production readiness checklist

---

## Conclusion

The orchestrator successfully started but hung on the scraping step due to lack of timeout protection. This is a critical issue that must be addressed before the next production run.

**Status:** 🔴 **BLOCKED** - Orchestrator cannot run reliably until timeouts are implemented

**Priority:** 🔥 **CRITICAL** - Must fix before next scheduled run (tonight at 8:30 PM)

**Estimated Fix Time:** 2-3 hours
- 1 hour: Implement step-level timeouts
- 1 hour: Add page-level timeouts to scraping
- 1 hour: Test and verify

---

## Files to Modify

1. **`src/task_executor.py`** or **`src/orchestrator_daemon.py`**
   - Add step-level timeout mechanism
   - Add subprocess cleanup on timeout

2. **`../Property_Data_Scraping/03_Gold_Coast/.../run_dynamic_10_suburbs.py`**
   - Add page-level timeouts
   - Add retry logic
   - Add health checks

3. **`config/process_commands.yaml`**
   - Update estimated_duration_minutes to be more accurate
   - Add max_duration_minutes for timeout calculation
