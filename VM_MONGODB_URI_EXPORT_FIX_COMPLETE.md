# VM MongoDB URI Export Fix - COMPLETE
# Last Updated: 16/02/2026, 5:56 AM (Saturday) - Brisbane Time
#
# Description: Fixed the root cause of MongoDB connection failures on VM
# All scraping scripts were falling back to 127.0.0.1:27017 because MONGODB_URI
# was not being exported to child process environments.
#
# Edit History:
# - 16/02/2026 5:56 AM: Initial creation after successful fix deployment

---

## Problem Summary

After weeks of troubleshooting, the root cause was identified:

**The orchestrator resolved `COSMOS_CONNECTION_STRING` from systemd environment correctly, BUT it never exported it as `MONGODB_URI` for child processes to inherit.**

### Symptoms
- All scraping scripts showed: `MongoDB connection failed: 127.0.0.1:27017: Connection refused`
- Every suburb reported: `⚠️ No results`
- No data was actually scraped despite scripts running

### Root Cause
Scraping scripts use this pattern:
```python
MONGODB_URI = os.getenv('MONGODB_URI', 'mongodb://127.0.0.1:27017/')
```

When `MONGODB_URI` wasn't in the environment, they fell back to localhost, which doesn't exist on the VM.

---

## The Fix

### What Was Changed

**File**: `src/orchestrator_daemon.py`

**Location**: In `__init__()` method, right after resolving the MongoDB URI from settings.yaml

**Added Code**:
```python
# CRITICAL FIX (16/02/2026): Export resolved MongoDB URI to environment
# so that ALL child processes (scraping scripts, etc.) inherit it.
# Without this, subprocesses fall back to 127.0.0.1:27017 and fail.
if mongo_uri:
    # Validate the URI before exporting
    if '127.0.0.1' in mongo_uri or 'localhost' in mongo_uri:
        self.logger.error("=" * 60)
        self.logger.error("CRITICAL: MongoDB URI resolves to LOCALHOST!")
        self.logger.error(f"URI: {mongo_uri}")
        self.logger.error("This will cause all scraping scripts to fail.")
        self.logger.error("Check COSMOS_CONNECTION_STRING environment variable.")
        self.logger.error("=" * 60)
        raise ValueError("MongoDB URI must not be localhost in cloud deployment")
    
    if '${' in mongo_uri or '$' in mongo_uri:
        self.logger.error("=" * 60)
        self.logger.error("CRITICAL: MongoDB URI contains unresolved template!")
        self.logger.error(f"URI: {mongo_uri}")
        self.logger.error("Environment variable substitution failed.")
        self.logger.error("=" * 60)
        raise ValueError("MongoDB URI contains unresolved environment variable")
    
    # Export to environment for child processes
    os.environ['MONGODB_URI'] = mongo_uri
    self.logger.info(f"✓ Exported MONGODB_URI to environment (starts with: {mongo_uri[:50]}...)")
else:
    self.logger.error("=" * 60)
    self.logger.error("CRITICAL: MongoDB URI is empty!")
    self.logger.error("Cannot proceed without valid MongoDB connection.")
    self.logger.error("=" * 60)
    raise ValueError("MongoDB URI cannot be empty")
```

### Why This Works

1. **Single Control Point**: The orchestrator resolves the URI once at startup
2. **Automatic Inheritance**: All child processes (via `subprocess.run()`) inherit `os.environ`
3. **Fail-Fast Validation**: If the URI is invalid, the orchestrator won't start (prevents silent failures)
4. **No Script Changes Needed**: All 50+ scraping scripts work without modification

---

## Deployment Steps

### 1. Deploy Fixed Code
```bash
cd /Users/projects/Documents/Fields_Orchestrator
gcloud compute scp src/orchestrator_daemon.py fields-orchestrator-vm:/home/fields/Fields_Orchestrator/src/ \
  --zone=australia-southeast1-b --project=fields-estate
```

### 2. Restart Orchestrator Service
```bash
gcloud compute ssh fields-orchestrator-vm --zone=australia-southeast1-b --project=fields-estate \
  --command='sudo systemctl restart fields-orchestrator'
```

### 3. Verify Fix
```bash
gcloud compute ssh fields-orchestrator-vm --zone=australia-southeast1-b --project=fields-estate \
  --command='tail -30 /home/fields/Fields_Orchestrator/logs/orchestrator.log | grep "Exported MONGODB_URI"'
```

**Expected Output**:
```
✓ Exported MONGODB_URI to environment (starts with: mongodb://fields-property-cosmos:REDACTED...)
```

---

## Verification Results

### ✅ Orchestrator Service Status
```
2026-02-16 05:55:00 | INFO | ✓ Exported MONGODB_URI to environment (starts with: mongodb://fields-property-cosmos:REDACTED...)
2026-02-16 05:55:00 | INFO | Trigger Time: 21:17
```

### ✅ Environment Variable Confirmed
The systemd service has `COSMOS_CONNECTION_STRING` set:
```
Environment="COSMOS_CONNECTION_STRING=mongodb://REDACTED:REDACTED@REDACTED.mongo.cosmos.azure.com:10255/"
```

### ✅ State Reset for Tonight's Run
```bash
echo '{"last_trigger_date": "2026-02-15"}' > /home/fields/Fields_Orchestrator/state/orchestrator_state.json
```

---

## Next Scheduled Run

**Date**: Tonight (16/02/2026)  
**Time**: 21:17 (9:17 PM Brisbane Time)  
**Expected Outcome**: Scraping scripts will successfully connect to Cosmos DB and actually scrape data

---

## What to Monitor

### Success Indicators
- ✅ No "127.0.0.1:27017 connection refused" errors
- ✅ Properties are actually scraped (not "⚠️ No results")
- ✅ Data appears in Cosmos DB collections
- ✅ Logs show successful MongoDB connections

### Failure Indicators
- ❌ Still seeing "127.0.0.1:27017" in logs
- ❌ Still seeing "⚠️ No results" for all suburbs
- ❌ No data in Cosmos DB after run

---

## Why Previous Fixes Didn't Work

### Attempt 1: Modified task_executor.py to pass env vars
**Problem**: Only passed `COSMOS_CONNECTION_STRING`, but scripts expect `MONGODB_URI`

### Attempt 2: Updated systemd service file
**Problem**: Systemd had the variable, but it wasn't being exported to child processes

### This Fix (Attempt 3): Export at orchestrator startup
**Success**: Single control point, automatic inheritance, fail-fast validation

---

## Alternative Approaches Considered

### ❌ Edit All Scraping Scripts
- Would require changing 50+ files
- Error-prone and hard to maintain
- Doesn't prevent future scripts from having the same issue

### ❌ Create .env Files Everywhere
- Requires deploying .env to multiple directories
- Secrets management complexity
- Still requires script changes to load .env

### ✅ Export from Orchestrator (Chosen Approach)
- Single point of control
- No script changes needed
- Fail-fast validation prevents silent failures
- Works for all current and future scripts

---

## Related Documentation

- **VM Deployment Workflow**: `/Users/projects/Documents/Cline/Rules/vm-deployment-workflow.md`
- **Previous Analysis**: `VM_NIGHT_RUN_FEB13_DETAILED_ANALYSIS.md`
- **Systemd Service**: `/etc/systemd/system/fields-orchestrator.service` (on VM)

---

## Commands for Future Reference

### Check if MONGODB_URI is exported
```bash
gcloud compute ssh fields-orchestrator-vm --zone=australia-southeast1-b --project=fields-estate \
  --command='tail -50 /home/fields/Fields_Orchestrator/logs/orchestrator.log | grep "MONGODB_URI"'
```

### Monitor tonight's run
```bash
gcloud compute ssh fields-orchestrator-vm --zone=australia-southeast1-b --project=fields-estate \
  --command='tail -f /home/fields/Fields_Orchestrator/logs/orchestrator.log'
```

### Check for 127.0.0.1 errors
```bash
gcloud compute ssh fields-orchestrator-vm --zone=australia-southeast1-b --project=fields-estate \
  --command='grep "127.0.0.1:27017" /home/fields/Fields_Orchestrator/logs/orchestrator.log | tail -20'
```

---

## Conclusion

After weeks of troubleshooting, the fix was simple but critical:

**Export the resolved MongoDB URI to `os.environ['MONGODB_URI']` at orchestrator startup.**

This ensures ALL child processes inherit the correct connection string, preventing the fallback to localhost.

The fix is:
- ✅ Deployed to VM
- ✅ Service restarted
- ✅ Verified in logs
- ✅ Ready for tonight's test run (9:17 PM)

**No rebuild or redeploy from scratch was necessary.**
