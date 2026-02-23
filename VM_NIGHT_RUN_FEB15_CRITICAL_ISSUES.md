# VM Night Run Feb 15 - Critical Issues Discovered
# Last Updated: 15/02/2026, 9:06 PM (Saturday) - Brisbane Time
#
# Status: ORCHESTRATOR RUNNING BUT SCRAPING SCRIPTS FAILING
# Root Cause: Subprocess environment variable inheritance issue

---

## Executive Summary

The orchestrator is running and executing processes, BUT all scraping scripts are failing to connect to MongoDB because they're trying to connect to `127.0.0.1:27017` (localhost) instead of Azure Cosmos DB.

**Impact**: 0/11 steps will complete successfully. Scripts run but produce no data.

---

## Issue #1: Config Path Problem (FIXED ✅)

**Problem**: VM was using LOCAL Mac paths instead of VM paths
- Orchestrator config pointed to `/Users/projects/Documents/...`
- Should point to `/home/fields/...`

**Fix Applied**: 
- Deployed correct `settings_cloud.yaml` and `process_commands_cloud.yaml`
- Removed local development configs from VM
- Orchestrator restarted with correct paths

**Status**: ✅ RESOLVED

---

## Issue #2: Confirmation Dialog Delay (MINOR - NOT FIXED)

**Problem**: Orchestrator shows confirmation dialogs which don't work on Linux VM
- Tries to run `osascript` (Mac-only command)
- Causes 30-minute snooze delay
- Run starts at 9:00 PM instead of 8:30 PM

**Impact**: Minor - just a 30-minute delay

**Partial Fix Applied**:
- Added `skip_confirmation_dialogs: true` to `settings_cloud.yaml`
- BUT: Code doesn't check this setting yet

**Status**: ⏳ NEEDS CODE UPDATE (for tomorrow)
- Update `src/orchestrator_daemon.py` to check `settings['schedule']['skip_confirmation_dialogs']`
- Skip dialog code entirely when true

---

## Issue #3: Scraping Scripts Can't Connect to MongoDB (CRITICAL ❌)

**Problem**: ALL scraping scripts are connecting to `127.0.0.1:27017` instead of Cosmos DB

**Evidence**:
```
[Robina] Process error: MongoDB connection failed after 3 attempts: 
127.0.0.1:27017: [Errno 111] Connection refused
```

**Root Cause**: Subprocess environment variable inheritance issue

The environment variables ARE set correctly:
- ✅ `MONGODB_URI` set in shell environment  
- ✅ `COSMOS_CONNECTION_STRING` set in systemd service

BUT when the orchestrator spawns subprocesses (scraping scripts), those subprocesses are NOT inheriting the environment variables.

**Why This Happens**:
1. Orchestrator runs as systemd service with `COSMOS_CONNECTION_STRING` env var
2. Orchestrator spawns subprocess: `python3 run_dynamic_10_suburbs.py`
3. Subprocess doesn't inherit parent's environment variables
4. Script falls back to hardcoded default: `mongodb://127.0.0.1:27017/`

**Impact**: 
- Scripts execute but can't access database
- No data is scraped
- All steps show "✅ COMPLETED" but actually failed
- This is why Feb 14 run showed 0/11 steps completed

**Status**: ❌ CRITICAL - NEEDS IMMEDIATE FIX

---

## The Fix Required

### Option A: Pass Environment Variables to Subprocesses (RECOMMENDED)

Update `src/task_executor.py` to explicitly pass environment variables to subprocesses:

```python
import os

# In execute_command() method:
env = os.environ.copy()
env['MONGODB_URI'] = os.getenv('COSMOS_CONNECTION_STRING') or os.getenv('MONGODB_URI')

subprocess.Popen(
    command,
    env=env,  # ← ADD THIS
    ...
)
```

### Option B: Create .env Files for Each Script Directory

Create `.env` files in each script directory with the connection string:

```bash
# /home/fields/Property_Data_Scraping/03_Gold_Coast/Gold_Coast_Wide_Currently_For_Sale_AND_Recently_Sold/.env
MONGODB_URI=mongodb://REDACTED:REDACTED@REDACTED.mongo.cosmos.azure.com:10255/
```

Then ensure scripts load from `.env` using `python-dotenv`.

### Option C: Update All Scraping Scripts

Update every scraping script to read from environment variable with Cosmos DB as fallback:

```python
import os

# OLD (hardcoded localhost):
mongodb_uri = os.getenv('MONGODB_URI', 'mongodb://127.0.0.1:27017/')

# NEW (Cosmos DB fallback):
mongodb_uri = os.getenv('MONGODB_URI') or os.getenv('COSMOS_CONNECTION_STRING') or 'mongodb://127.0.0.1:27017/'
```

**Recommendation**: Use Option A (subprocess environment) - it's the cleanest and fixes all scripts at once.

---

## Current Run Status (9:06 PM)

**Orchestrator**: ✅ Running  
**Process 101 (Scraping)**: ⚠️ Running but failing to connect to MongoDB  
**Progress**: 4/10 suburbs "completed" (but no data scraped)  
**Expected Outcome**: 0/11 steps will complete successfully

---

## Action Plan for Tomorrow

### Priority 1: Fix Subprocess Environment (CRITICAL)
1. Update `src/task_executor.py` to pass environment variables to subprocesses
2. Test locally
3. Deploy to VM
4. Restart orchestrator
5. Trigger test run
6. Verify MongoDB connections succeed

### Priority 2: Fix Confirmation Dialogs (MINOR)
1. Update `src/orchestrator_daemon.py` to check `skip_confirmation_dialogs` setting
2. Skip dialog code when setting is true
3. Deploy to VM
4. Verify immediate start at 8:30 PM

### Priority 3: Monitor Next Night Run
1. Check logs at 8:30 PM
2. Verify immediate start (no 30-min delay)
3. Verify MongoDB connections succeed
4. Verify data is actually scraped
5. Check final step count (should be 7-11/11 instead of 0/11)

---

## Files That Need Updates

### 1. src/task_executor.py
**Change**: Pass environment variables to subprocesses
**Lines**: ~50-100 (subprocess.Popen call)

### 2. src/orchestrator_daemon.py  
**Change**: Check `skip_confirmation_dialogs` setting
**Lines**: ~200-250 (dialog code)

### 3. 02_Deployment/scripts/fix_subprocess_environment.sh (NEW)
**Purpose**: Deploy the subprocess environment fix

---

## Related Documentation

- Config path fix: `VM_CONFIG_PATH_CRITICAL_FIX.md`
- Dialog fix script: `02_Deployment/scripts/disable_confirmation_dialogs.sh`
- Original analysis: `VM_NIGHT_RUN_FEB13_DETAILED_ANALYSIS.md`

---

## Key Learnings

1. **Config paths matter**: VM paths ≠ Local paths
2. **Environment variables don't auto-inherit**: Subprocesses need explicit env passing
3. **"Completed" ≠ "Successful"**: Scripts can complete without doing anything
4. **Test subprocess behavior**: Environment inheritance is platform/method-specific

---

*Analysis completed: 15/02/2026, 9:06 PM Brisbane Time*
*Next action: Fix subprocess environment variable inheritance*
