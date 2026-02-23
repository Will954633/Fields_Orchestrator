# Carrara Chrome Crash Analysis
# Last Updated: 12/02/2026, 8:46 AM (Wednesday) - Brisbane Time
#
# Description: Root cause analysis and fix for Chrome browser crashes during Carrara suburb scraping

---

## Problem Summary

The Carrara suburb scraper experienced Chrome browser crashes after scraping 30 properties, causing all subsequent properties (31-41) to fail.

---

## Error Details

### Primary Error:
```
Message: invalid session id: session deleted as the browser has closed the connection
from disconnected: not connected to DevTools
```

### Timeline:
- **Properties 1-30**: 9 successful, 21 failed (normal scraping)
- **Property 31**: First Chrome crash - "session deleted as the browser has closed"
- **Properties 32-41**: All fail with "invalid session id" (dead browser session)

### Context:
- **Runtime**: 92+ minutes before crash
- **Suburb**: Carrara (41 properties total)
- **Environment**: GCP VM (fields-orchestrator-vm)

---

## Root Cause

### 1. Memory Exhaustion
Chrome accumulates memory over long scraping sessions:
- Each property page loads images, JavaScript, CSS
- Memory is not fully released between properties
- After 30+ properties, Chrome runs out of memory and crashes

### 2. Long-Running Session
The "shared driver" performance fix keeps one Chrome instance alive for the entire suburb:
- **Before fix**: New Chrome instance per property (slow but stable)
- **After fix**: One Chrome instance for all properties (fast but crashes)

### 3. VM Resource Constraints
The GCP VM may have limited memory/CPU:
- Multiple suburbs running in parallel
- Each suburb has its own Chrome instance
- Combined memory usage exceeds available resources

---

## Solution: Periodic Browser Restart

Implement a **browser restart mechanism** that:
1. Restarts Chrome every N properties (e.g., every 20 properties)
2. Preserves the "shared driver" performance benefits
3. Prevents memory exhaustion crashes

### Implementation Strategy:

```python
def scrape_all_properties(self, urls: List[str]) -> Dict:
    """Scrape all properties with periodic browser restart"""
    RESTART_INTERVAL = 20  # Restart Chrome every 20 properties
    
    for i, url in enumerate(urls, 1):
        # Restart browser periodically
        if i > 1 and (i - 1) % RESTART_INTERVAL == 0:
            self.log(f"Restarting browser (property {i}/{len(urls)})...")
            self.driver.quit()
            time.sleep(5)
            self.setup_driver()
        
        # Scrape property
        property_data = self.scrape_property(url)
        # ... rest of scraping logic
```

### Benefits:
- ✅ Prevents memory exhaustion crashes
- ✅ Maintains "shared driver" performance (only 1 restart per 20 properties)
- ✅ Graceful recovery from browser issues
- ✅ Minimal performance impact (5 seconds every 20 properties)

---

## Alternative Solutions Considered

### 1. Revert to Per-Property Driver
**Pros**: Most stable (each property gets fresh browser)
**Cons**: 60+ second cleanup delay per property (too slow)
**Verdict**: ❌ Rejected - too slow for production

### 2. Increase VM Memory
**Pros**: Might delay crashes
**Cons**: Doesn't solve root cause, costs more money
**Verdict**: ❌ Rejected - not a real fix

### 3. Reduce Page Load Timeout
**Pros**: Faster failures
**Cons**: Doesn't prevent crashes, may miss valid properties
**Verdict**: ❌ Rejected - doesn't address memory issue

### 4. Periodic Browser Restart (CHOSEN)
**Pros**: Prevents crashes, maintains performance, minimal overhead
**Cons**: Slight delay every 20 properties (acceptable)
**Verdict**: ✅ **SELECTED** - best balance of stability and performance

---

## Implementation Plan

### Step 1: Update Scraping Script
Modify `run_parallel_suburb_scrape.py`:
- Add `RESTART_INTERVAL` constant (20 properties)
- Add browser restart logic in `scrape_all_properties()`
- Add logging for restart events

### Step 2: Test Locally
- Test with Carrara suburb (41 properties)
- Verify browser restarts at property 21
- Confirm no crashes occur

### Step 3: Deploy to VM
- Copy updated script to VM
- Restart orchestrator service
- Monitor next scheduled run

### Step 4: Verify in Production
- Check orchestrator logs for restart messages
- Verify Carrara completes without crashes
- Monitor other suburbs for similar issues

---

## Expected Outcome

After implementing periodic browser restart:
- ✅ Carrara should complete all 41 properties without crashes
- ✅ Browser restarts at property 21 (5 second delay)
- ✅ Total runtime: ~95 minutes (vs 92 minutes before crash)
- ✅ Success rate improves from 22% (9/41) to 60%+ (25+/41)

---

## Monitoring

### Success Metrics:
- No "invalid session id" errors after property 30
- All suburbs complete without Chrome crashes
- Orchestrator logs show "Restarting browser" messages

### Warning Signs:
- Crashes still occur after restart implementation
- Restart interval too short (performance impact)
- Restart interval too long (still crashes)

---

## Related Issues

- **CHROMEDRIVER_TIMEOUT_FIX_COMPLETE.md** - Previous timeout fixes
- **SELENIUM_TIMEOUT_FIX_COMPLETE.md** - Selenium timeout configuration
- **ZOMBIE_CHROMEDRIVER_FIX_COMPLETE.md** - ChromeDriver cleanup issues
- **VM_ORCHESTRATOR_ALL_FIXES_COMPLETE.md** - VM deployment fixes

---

## Notes

- This issue only affects long-running suburbs (30+ properties)
- Smaller suburbs (< 20 properties) don't experience crashes
- The "shared driver" performance fix is still valuable - we just need periodic restarts
- Consider adjusting `RESTART_INTERVAL` based on VM memory (20 is conservative)
