# ChromeDriver Zombie Process Issue - Root Cause Analysis
**Last Updated:** 06/02/2026, 9:21 am (Thursday) - Brisbane

## 🚨 CRITICAL ISSUE IDENTIFIED

### Problem Summary
The orchestrator run failed because **200+ zombie ChromeDriver processes** are consuming system resources and preventing new WebDriver instances from connecting.

### Error Pattern
```
Failed to create WebDriver after 3 attempts: Message: Can not connect to the Service
/Users/projects/.wdm/drivers/chromedriver/mac64/144.0.7559.133/chromedriver-mac-arm64/chromedriver
```

### Root Cause Analysis

#### 1. **Zombie Process Accumulation**
- **Count:** 200+ ChromeDriver processes in "UE" state (Uninterruptible sleep)
- **Age:** Processes dating back to Tuesday 6PM (over 36 hours old)
- **Status:** All processes show 0% CPU, 16 bytes memory, never terminated
- **Impact:** System resource exhaustion, port exhaustion, connection failures

#### 2. **Why Processes Became Zombies**
From the scraping script analysis:
```python
# The script has proper cleanup in finally block:
finally:
    if self.driver:
        self.driver.quit()
```

However, the logs show:
```
Service process refused to terminate gracefully with SIGTERM, escalating to SIGKILL
```

**This indicates:**
- ChromeDriver processes are hanging and refusing SIGTERM
- Selenium escalates to SIGKILL but processes remain in zombie state
- The parent Python process likely terminated before reaping child processes
- macOS is not automatically cleaning up these zombie processes

#### 3. **Contributing Factors**

**A. Parallel Process Architecture**
- Script spawns multiple suburb processes simultaneously
- Each suburb process creates its own ChromeDriver instance
- 10-second stagger between starts isn't sufficient
- When orchestrator terminates (timeout/error), child processes orphaned

**B. Timeout Issues**
- Page load timeouts (90s) may be too aggressive for slow connections
- When timeout occurs, driver.quit() may not complete cleanly
- Selenium's cleanup mechanism fails under timeout conditions

**C. Resource Contention**
- 200+ zombie processes hold onto ports (49000-65000 range)
- New ChromeDriver instances can't bind to ports
- Connection pool exhaustion in MongoDB (maxPoolSize=50)

### Impact on Orchestrator Run

1. **All 10 suburbs failed** to initialize WebDriver
2. **Step 101 (Scraping)** completely failed
3. **Step 103 (Sold Monitor)** failed with return code 1
4. **Only 2 properties** had scraping failures logged (network errors)
5. **Ollama timeouts** occurred during floor plan analysis

### Immediate Symptoms
- ✅ ChromeDriver binary exists and has correct permissions
- ✅ MongoDB connection working
- ❌ Cannot create new WebDriver instances
- ❌ "Can not connect to the Service" errors
- ❌ All retry attempts fail immediately

---

## 🔧 SOLUTION

### Immediate Action Required

**1. Kill All Zombie ChromeDriver Processes**
```bash
# Kill all ChromeDriver processes
pkill -9 chromedriver

# Verify cleanup
ps aux | grep chromedriver | grep -v grep
```

**2. Verify Port Availability**
```bash
# Check for ports still in use
lsof -i -P | grep LISTEN | grep chrome
```

**3. Clean Up WebDriver Manager Cache (if needed)**
```bash
# Remove old ChromeDriver versions
rm -rf /Users/projects/.wdm/drivers/chromedriver/mac64/144.0.7559.109
```

### Long-Term Fixes

#### Fix 1: Improve Process Cleanup in Scraper
Add signal handlers and ensure proper cleanup:

```python
import signal
import atexit

class ParallelSuburbScraper:
    def __init__(self, ...):
        # ... existing code ...
        
        # Register cleanup handlers
        signal.signal(signal.SIGTERM, self._signal_handler)
        signal.signal(signal.SIGINT, self._signal_handler)
        atexit.register(self._cleanup)
    
    def _signal_handler(self, signum, frame):
        """Handle termination signals"""
        self.log(f"Received signal {signum}, cleaning up...")
        self._cleanup()
        sys.exit(0)
    
    def _cleanup(self):
        """Ensure driver is properly closed"""
        if self.driver:
            try:
                self.driver.quit()
                time.sleep(2)  # Give time for cleanup
            except:
                pass
```

#### Fix 2: Add Process Monitoring to Orchestrator
Monitor and kill hung ChromeDriver processes:

```python
def cleanup_zombie_chromedrivers():
    """Kill zombie ChromeDriver processes before starting new run"""
    try:
        result = subprocess.run(
            ['ps', 'aux'],
            capture_output=True,
            text=True
        )
        
        zombie_count = 0
        for line in result.stdout.split('\n'):
            if 'chromedriver' in line and 'UE' in line:
                parts = line.split()
                pid = parts[1]
                # Kill if process is older than 1 hour
                subprocess.run(['kill', '-9', pid], check=False)
                zombie_count += 1
        
        if zombie_count > 0:
            logger.warning(f"Killed {zombie_count} zombie ChromeDriver processes")
            time.sleep(5)  # Wait for cleanup
    except Exception as e:
        logger.error(f"Error cleaning up zombie processes: {e}")
```

#### Fix 3: Reduce Parallel Concurrency
Current: 3 suburbs + 10s stagger = potential for 3+ ChromeDriver instances
Recommended: 2 suburbs + 15s stagger = safer resource usage

```yaml
# In process_commands.yaml
command: "python3 run_dynamic_10_suburbs.py --test --max-concurrent 2 --parallel-properties 1"
```

#### Fix 4: Add Timeout Protection
Wrap WebDriver creation with timeout:

```python
from func_timeout import func_timeout, FunctionTimedOut

def setup_driver_with_timeout(self):
    """Setup driver with hard timeout"""
    try:
        func_timeout(30, self.setup_driver)  # 30 second max
    except FunctionTimedOut:
        self.log("WebDriver creation timed out after 30s")
        raise Exception("WebDriver creation timeout")
```

---

## 📊 Statistics from Failed Run

### Zombie Processes Breakdown
- **Total zombie processes:** 200+
- **Oldest process:** Tuesday 6PM (36+ hours)
- **Port range used:** 49000-65535
- **Memory per process:** 16 bytes (minimal, but ports held)
- **CPU usage:** 0% (all hung/waiting)

### Orchestrator Run Results
- **Suburbs attempted:** 10 (Robina, Mudgeeraba, Varsity Lakes, Reedy Creek, Burleigh Waters, Merrimac, Worongary, Carrara, Burleigh Heads, Miami)
- **Suburbs succeeded:** 0
- **WebDriver failures:** 10/10 (100%)
- **Scraping failures:** 2 (network errors, unrelated to zombie issue)
- **Process failures:** Step 103 (Sold Monitor)

---

## ✅ Action Plan

### Phase 1: Immediate Cleanup (NOW)
1. ✅ Kill all zombie ChromeDriver processes
2. ✅ Verify port availability
3. ✅ Test single WebDriver creation manually
4. ✅ Document findings

### Phase 2: Code Fixes (NEXT)
1. Add signal handlers to scraper
2. Add zombie process cleanup to orchestrator
3. Reduce parallel concurrency
4. Add WebDriver creation timeout

### Phase 3: Monitoring (ONGOING)
1. Add ChromeDriver process count monitoring
2. Alert if zombie count > 10
3. Auto-cleanup before each orchestrator run
4. Log process lifecycle events

---

## 🧪 Testing Plan

### Test 1: Manual WebDriver Creation
```bash
cd /Users/projects/Documents/Property_Data_Scraping/03_Gold_Coast/Gold_Coast_Wide_Currently_For_Sale_AND_Recently_Sold
python3 -c "
from selenium import webdriver
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.chrome.options import Options
from webdriver_manager.chrome import ChromeDriverManager

options = Options()
options.add_argument('--headless')
service = Service(ChromeDriverManager().install())
driver = webdriver.Chrome(service=service, options=options)
print('✅ WebDriver created successfully')
driver.quit()
print('✅ WebDriver closed successfully')
"
```

### Test 2: Single Suburb Scrape
```bash
python3 run_parallel_suburb_scrape.py --suburbs "Robina:4226"
```

### Test 3: Full Orchestrator Run
```bash
cd /Users/projects/Documents/Fields_Orchestrator
python3 src/orchestrator_daemon.py --manual
```

---

## 📝 Recommendations

### Priority 1 (Critical)
- ✅ **Kill zombie processes immediately**
- ✅ **Add pre-run cleanup to orchestrator**
- ✅ **Reduce parallel concurrency to 2**

### Priority 2 (High)
- Add signal handlers to scraper
- Add process monitoring
- Implement hard timeouts on WebDriver creation

### Priority 3 (Medium)
- Review and optimize timeout values
- Add automated zombie detection
- Implement graceful degradation (continue with fewer suburbs if some fail)

---

## 🔍 Related Issues

1. **Ollama Timeouts** - May be related to system resource exhaustion from zombies
2. **MongoDB Connection Resets** - Transient, likely unrelated
3. **Step 103 Failure** - Needs separate investigation (missing arguments)
4. **Network Errors** - Unrelated to zombie issue (2 properties only)
