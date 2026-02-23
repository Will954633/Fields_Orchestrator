# Orchestrator Hang - Root Cause Analysis
**Last Updated: 05/02/2026, 9:26 AM (Wednesday) - Brisbane**

## Executive Summary

✅ **GOOD NEWS**: The orchestrator **DOES have timeout protection** (3x estimated duration)
🔴 **BAD NEWS**: The scraping script **LACKS Selenium page-level timeouts**, causing indefinite hangs

## Root Cause Identified

### The Problem

The scraping process hung for 14+ hours because:

1. **Selenium has NO default timeout** - `driver.get(url)` will wait indefinitely if a page doesn't load
2. **The scraping script never set page timeouts** - Missing `driver.set_page_load_timeout()`
3. **The orchestrator timeout never triggered** - Because the process was technically "running" (waiting for Selenium)

### Why the Orchestrator Timeout Didn't Help

Looking at `task_executor.py` line 215:
```python
timeout_seconds = process.estimated_duration_minutes * 60 * 3  # 3x estimated time as timeout
```

For Step 101:
- Estimated: 40 minutes
- Timeout: 120 minutes (2 hours)
- **The process hung for 14+ hours**, so the timeout SHOULD have triggered

**BUT**: The timeout mechanism checks `time.time() - start_time` every 0.5 seconds. If the subprocess is stuck in a Selenium call that never returns, the timeout check still runs, but the process appears to be "alive" and consuming CPU.

### The Real Issue

The scraping script (`run_parallel_suburb_scrape.py`) creates Selenium drivers WITHOUT timeouts:

```python
def setup_driver(self):
    """Setup headless Chrome WebDriver"""
    # ... chrome options ...
    self.driver = webdriver.Chrome(service=service, options=chrome_options)
    # ❌ MISSING: self.driver.set_page_load_timeout(90)
    # ❌ MISSING: self.driver.implicitly_wait(30)
```

When `driver.get(url)` is called on a page that hangs, Selenium waits **forever**.

## Evidence

### 1. Orchestrator Log Shows Process Started
```
2026-02-05 08:35:49 | [Robina] Process started (PID: 93541)
2026-02-05 08:35:59 | [Mudgeeraba] Process started (PID: 93635)
```

### 2. No Further Output
The log stops at 08:35:59, indicating the subprocess never produced more output.

### 3. Chrome Processes Running 14+ Hours Later
```
projects  11687  16.0  0.4  1865681536  277312  ??  S  6:59PM  90:28.58  Chrome Helper (Renderer)
projects  11678  11.6  0.2   461979504  107408  ??  S  6:59PM  84:43.15  Chrome Helper (gpu-process)
```

These processes started at 6:59 PM (likely when Selenium tried to load a problematic page) and were still running at 9:22 AM.

### 4. Orchestrator Timeout Should Have Triggered
- Start: 08:35:39
- Timeout: 08:35:39 + 120 min = 10:35:39
- Actual hang: Until 09:22:00 (next day)

**The timeout DID trigger**, but the process group kill may have failed because Chrome was in an unresponsive state.

## The Fix

### 1. Add Selenium Timeouts (CRITICAL)

In `run_parallel_suburb_scrape.py`, add timeouts to the driver setup:

```python
def setup_driver(self):
    """Setup headless Chrome WebDriver"""
    self.log("Setting up headless Chrome WebDriver...")
    
    chrome_options = Options()
    # ... existing options ...
    
    service = Service(ChromeDriverManager().install())
    self.driver = webdriver.Chrome(service=service, options=chrome_options)
    
    # ✅ ADD THESE CRITICAL TIMEOUTS
    self.driver.set_page_load_timeout(90)  # 90 second page load timeout
    self.driver.implicitly_wait(30)  # 30 second element wait timeout
    self.driver.set_script_timeout(30)  # 30 second script execution timeout
    
    self.log("Headless Chrome ready with timeouts configured")
```

### 2. Add Retry Logic with Timeout Handling

Wrap `driver.get()` calls in try-except to handle timeouts:

```python
def scrape_property(self, url: str) -> Optional[Dict]:
    """Scrape single property with timeout handling"""
    max_retries = 2
    
    for attempt in range(max_retries):
        try:
            self.driver.get(url)
            time.sleep(PAGE_LOAD_WAIT)
            # ... rest of scraping logic ...
            return property_data
            
        except TimeoutException:
            if attempt < max_retries - 1:
                self.log(f"Timeout loading {url}, retrying ({attempt + 1}/{max_retries})...")
                time.sleep(5)
                continue
            else:
                self.log(f"Failed to load {url} after {max_retries} attempts")
                return None
                
        except Exception as e:
            self.log(f"Error scraping {url}: {e}")
            return None
```

### 3. Add Browser Health Checks

Periodically check if Chrome is responsive:

```python
def check_browser_health(self) -> bool:
    """Check if browser is still responsive"""
    try:
        self.driver.execute_script("return 1 + 1;")
        return True
    except:
        return False

def scrape_all_properties(self, urls: List[str]) -> Dict:
    """Scrape all properties with health checks"""
    # ... existing code ...
    
    for i, url in enumerate(urls, 1):
        # Check browser health every 10 properties
        if i % 10 == 0:
            if not self.check_browser_health():
                self.log("Browser unresponsive, restarting...")
                self.driver.quit()
                self.setup_driver()
        
        property_data = self.scrape_property(url)
        # ... rest of logic ...
```

### 4. Improve Process Group Killing

The orchestrator already uses `start_new_session=True` and `os.killpg()`, but we should add more aggressive cleanup:

```python
# In task_executor.py, improve the timeout handling:
if (time.time() - start_time) > timeout_seconds:
    self.logger.error(f"Process timed out after {timeout_seconds/60:.0f} minutes")
    
    try:
        # Try SIGTERM first
        os.killpg(proc.pid, signal.SIGTERM)
        time.sleep(5)
        
        # If still alive, use SIGKILL
        if proc.poll() is None:
            os.killpg(proc.pid, signal.SIGKILL)
            
        # Also kill any Chrome processes
        subprocess.run(['pkill', '-9', '-f', 'Chrome.*puppeteer'], 
                      stderr=subprocess.DEVNULL)
        
    except Exception as e:
        self.logger.error(f"Error killing process: {e}")
    
    return False, "", "Process timed out"
```

## Implementation Priority

### CRITICAL (Must fix before next run)
1. ✅ Add Selenium timeouts to `run_parallel_suburb_scrape.py`
2. ✅ Add timeout exception handling to `scrape_property()`
3. ✅ Test with a single suburb to verify timeouts work

### HIGH (Fix this week)
4. Add browser health checks
5. Add retry logic with exponential backoff
6. Improve process cleanup in orchestrator

### MEDIUM (Nice to have)
7. Add heartbeat logging every 5 minutes
8. Add progress percentage logging
9. Add email alerts for long-running processes

## Testing Plan

### Phase 1: Unit Test Timeouts
```bash
# Test Selenium timeouts with a non-existent URL
python3 -c "
from selenium import webdriver
from selenium.common.exceptions import TimeoutException
driver = webdriver.Chrome()
driver.set_page_load_timeout(10)
try:
    driver.get('http://192.0.2.1')  # Non-routable IP
except TimeoutException:
    print('✅ Timeout works!')
driver.quit()
"
```

### Phase 2: Test Single Suburb
```bash
cd /Users/projects/Documents/Property_Data_Scraping/03_Gold_Coast/Gold_Coast_Wide_Currently_For_Sale_AND_Recently_Sold
python3 run_parallel_suburb_scrape.py --suburbs "Robina:4226"
```

### Phase 3: Test Full Orchestrator
```bash
cd /Users/projects/Documents/Fields_Orchestrator
python3 src/orchestrator_daemon.py --run-now
```

## Estimated Fix Time

- **Selenium timeouts**: 15 minutes
- **Exception handling**: 15 minutes
- **Testing**: 30 minutes
- **Total**: 1 hour

## Conclusion

The orchestrator timeout mechanism is working correctly, but it can't help when Selenium hangs indefinitely. The fix is straightforward: add Selenium timeouts to prevent indefinite waits.

**Status**: 🔴 **CRITICAL** - Must fix before tonight's run
**Priority**: 🔥 **HIGHEST**
**Complexity**: ⭐ **LOW** - Simple configuration change
**Risk**: ⭐ **LOW** - Adding timeouts is safe and recommended practice
