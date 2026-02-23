# Sold Monitor Fix - Complete Resolution
# Last Updated: 12/02/2026, 9:14 AM (Wednesday) - Brisbane Time
#
# Description: Complete fix for sold property monitor Chrome crashes and MongoDB errors
#
# Edit History:
# - 12/02/2026 9:14 AM: Initial creation - fixed Chrome WebDriver and MongoDB retryable writes issues

---

## Problem Summary

The sold property monitor (`monitor_sold_properties.py`) was failing with two critical errors:

### Issue 1: Chrome WebDriver Crashes
```
[Reedy Creek] Process error: Failed to create WebDriver: Message: session not created
from disconnected: unable to connect to renderer
```

**Root Cause**: Using `webdriver-manager` which downloads ChromeDriver versions that are incompatible with the system Chrome installation on the VM.

### Issue 2: MongoDB Retryable Writes Error
```
[Robina] Error moving property: Retryable writes are not supported. Please disable retryable writes 
by specifying "retrywrites=false" in the connection string or an equivalent driver specific config.
```

**Root Cause**: Azure Cosmos DB (MongoDB API) does not support retryable writes, but PyMongo defaults to `retryWrites=True`.

### Impact
- **All suburbs failing**: Only Robina and Mudgeeraba partially completed (10 properties each)
- **7 suburbs showed "No results"**: Varsity Lakes, Reedy Creek, Burleigh Waters, Merrimac, Worongary, Carrara, Burleigh Heads, Miami
- **0 properties moved to sold collection**: Despite checking 20 properties

---

## Solution Implemented

### Fix 1: Chrome WebDriver Configuration

**Changed from:**
```python
service = Service(ChromeDriverManager().install())
self.driver = webdriver.Chrome(service=service, options=chrome_options)
```

**Changed to:**
```python
# Use system ChromeDriver (no webdriver-manager)
service = Service('/usr/bin/chromedriver')
self.driver = webdriver.Chrome(service=service, options=chrome_options)
```

**Additional improvements:**
- Added `--headless=new` flag for better stability
- Added `--remote-debugging-port=0` to prevent port conflicts
- Added `--disable-software-rasterizer` for VM compatibility
- Removed `webdriver-manager` dependency entirely

### Fix 2: MongoDB Retryable Writes

**Changed from:**
```python
_mongo_client = MongoClient(
    MONGODB_URI,
    retryWrites=True,  # ❌ Not supported by Cosmos DB
    retryReads=True
)
```

**Changed to:**
```python
_mongo_client = MongoClient(
    MONGODB_URI,
    retryWrites=False,  # ✅ CRITICAL: Cosmos DB doesn't support retryable writes
    retryReads=True
)
```

---

## Files Modified

### 1. monitor_sold_properties.py
**Location**: `/Users/projects/Documents/Property_Data_Scraping/03_Gold_Coast/Gold_Coast_Wide_Currently_For_Sale_AND_Recently_Sold/monitor_sold_properties.py`

**Changes:**
- Updated `setup_driver()` method to use system ChromeDriver
- Changed `retryWrites=True` to `retryWrites=False` in MongoDB connection
- Removed `webdriver_manager.chrome.ChromeDriverManager` import
- Updated file header with fix documentation

### 2. fix_sold_monitor_complete.py (New)
**Location**: `/Users/projects/Documents/Fields_Orchestrator/02_Deployment/scripts/fix_sold_monitor_complete.py`

**Purpose**: Automated fix script that applies all changes to monitor_sold_properties.py

---

## Deployment Steps

### Step 1: Apply Fixes Locally ✅
```bash
cd /Users/projects/Documents/Fields_Orchestrator/02_Deployment/scripts
python3 fix_sold_monitor_complete.py
```

**Result**: All 4 fixes applied successfully

### Step 2: Deploy to VM (In Progress)
```bash
cd /Users/projects/Documents/Property_Data_Scraping
gcloud compute scp --recurse 03_Gold_Coast fields-orchestrator-vm:/home/fields/Property_Data_Scraping/ \
  --zone=australia-southeast1-b --project=fields-estate
```

**Status**: Running in background (large directory)

### Step 3: Restart Orchestrator (Next)
```bash
gcloud compute ssh fields-orchestrator-vm --zone=australia-southeast1-b --project=fields-estate \
  --command='sudo systemctl restart fields-orchestrator'
```

### Step 4: Monitor Logs (Next)
```bash
gcloud compute ssh fields-orchestrator-vm --zone=australia-southeast1-b --project=fields-estate \
  --command='tail -f /home/fields/Fields_Orchestrator/logs/orchestrator.log'
```

---

## Expected Behavior After Fix

### Chrome WebDriver
- ✅ Should use system ChromeDriver at `/usr/bin/chromedriver`
- ✅ Should log: "✓ Headless Chrome ready (system ChromeDriver)"
- ✅ No more "session not created" errors
- ✅ No more "unable to connect to renderer" errors

### MongoDB Operations
- ✅ Should successfully move properties to sold collection
- ✅ No more "Retryable writes are not supported" errors
- ✅ Properties should appear in `Gold_Coast_Recently_Sold` database
- ✅ Master property records should be updated with sold transactions

### Process Completion
- ✅ All suburbs should complete successfully
- ✅ Should see "✅ COMPLETE - X properties sold" for each suburb
- ✅ Final summary should show total properties checked and sold
- ✅ No "⚠️ No results" or "⚠️ Incomplete" messages

---

## Verification Checklist

After deployment and restart, verify:

- [ ] Orchestrator service restarted successfully
- [ ] Sold monitor process starts without Chrome errors
- [ ] No "session not created" errors in logs
- [ ] No "Retryable writes are not supported" errors in logs
- [ ] Properties are successfully moved to sold collection
- [ ] All suburbs complete (no "No results" messages)
- [ ] Final summary shows properties checked and sold counts

---

## Technical Details

### Chrome WebDriver on VM

**System Chrome Version**: 
```bash
google-chrome --version
# Google Chrome 120.x.x.x
```

**System ChromeDriver Location**:
```bash
which chromedriver
# /usr/bin/chromedriver
```

**Why webdriver-manager failed**:
- Downloads ChromeDriver to user cache directory
- May download incompatible version for system Chrome
- Network issues can cause download failures
- System ChromeDriver is pre-installed and version-matched

### Azure Cosmos DB Limitations

**Retryable Writes**:
- Feature introduced in MongoDB 3.6
- Automatically retries certain write operations on network errors
- **NOT supported by Azure Cosmos DB MongoDB API**
- Must be explicitly disabled in connection string or client options

**Connection String Format**:
```
mongodb://REDACTED:REDACTED@REDACTED.mongo.cosmos.azure.com:10255/
```

Or via client options:
```python
MongoClient(uri, retryWrites=False)
```

---

## Related Issues Fixed

This fix also resolves:
- **Zombie ChromeDriver processes**: System ChromeDriver is more stable
- **Port conflicts**: Added `--remote-debugging-port=0`
- **VM compatibility**: Added `--disable-software-rasterizer`
- **Database write failures**: Disabled retryable writes for Cosmos DB

---

## Performance Impact

### Before Fix
- **Completion rate**: 2/10 suburbs (20%)
- **Properties checked**: 20 total
- **Properties moved**: 0 (all failed with MongoDB error)
- **Error rate**: 100% for property moves

### After Fix (Expected)
- **Completion rate**: 10/10 suburbs (100%)
- **Properties checked**: All properties in for-sale collections
- **Properties moved**: All sold properties detected
- **Error rate**: 0% for Chrome and MongoDB operations

---

## Monitoring Commands

### Check orchestrator status
```bash
gcloud compute ssh fields-orchestrator-vm --zone=australia-southeast1-b --project=fields-estate \
  --command='sudo systemctl status fields-orchestrator --no-pager'
```

### View recent logs
```bash
gcloud compute ssh fields-orchestrator-vm --zone=australia-southeast1-b --project=fields-estate \
  --command='tail -100 /home/fields/Fields_Orchestrator/logs/orchestrator.log'
```

### Check for Chrome errors
```bash
gcloud compute ssh fields-orchestrator-vm --zone=australia-southeast1-b --project=fields-estate \
  --command='grep -i "session not created\|unable to connect" /home/fields/Fields_Orchestrator/logs/orchestrator.log | tail -20'
```

### Check for MongoDB errors
```bash
gcloud compute ssh fields-orchestrator-vm --zone=australia-southeast1-b --project=fields-estate \
  --command='grep -i "retryable writes" /home/fields/Fields_Orchestrator/logs/orchestrator.log | tail -20'
```

### Check sold collection
```bash
gcloud compute ssh fields-orchestrator-vm --zone=australia-southeast1-b --project=fields-estate \
  --command='cd /home/fields/Fields_Orchestrator/02_Deployment/scripts && python3 test_cosmos_connection.py'
```

---

## Rollback Plan

If issues persist, rollback by reverting to previous version:

```bash
# On VM, restore backup
cd /home/fields/Property_Data_Scraping/03_Gold_Coast/Gold_Coast_Wide_Currently_For_Sale_AND_Recently_Sold
cp monitor_sold_properties.py.backup monitor_sold_properties.py

# Restart orchestrator
sudo systemctl restart fields-orchestrator
```

---

## Next Steps

1. **Wait for deployment to complete** (gcloud scp running in background)
2. **Restart orchestrator service** on VM
3. **Monitor logs** for successful execution
4. **Verify sold properties** are being moved correctly
5. **Check MongoDB collections** for sold property records
6. **Document results** in this file

---

## Success Criteria

✅ **Fix is successful when:**
- No Chrome WebDriver errors in logs
- No MongoDB retryable writes errors in logs
- All suburbs complete successfully
- Properties are moved to sold collection
- Master property records are updated
- Final summary shows accurate counts

---

## Notes

- **Chrome version compatibility**: System ChromeDriver must match system Chrome version
- **Cosmos DB limitations**: Always use `retryWrites=False` for Azure Cosmos DB
- **Parallel processing**: Monitor still uses parallel suburb processing (max 3 concurrent)
- **Shared driver**: Each suburb process uses ONE driver for all properties (performance optimization)

---

## References

- **Selenium Documentation**: https://www.selenium.dev/documentation/webdriver/
- **Azure Cosmos DB MongoDB API**: https://docs.microsoft.com/en-us/azure/cosmos-db/mongodb/
- **PyMongo Retryable Writes**: https://pymongo.readthedocs.io/en/stable/api/pymongo/mongo_client.html
- **Chrome Headless Mode**: https://developer.chrome.com/blog/headless-chrome/
