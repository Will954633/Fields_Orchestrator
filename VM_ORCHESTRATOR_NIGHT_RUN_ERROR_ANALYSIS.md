# VM Orchestrator Night Run Error Analysis
# Last Edit: 13/02/2026, 7:53 AM (Thursday) — Brisbane Time
#
# Description: Surgical analysis of orchestrator errors from the night run on 12/02/2026
# This document identifies all failures, root causes, and required fixes

---

## Executive Summary

**Run Date:** 12/02/2026  
**Run Times:** 
- First run: 07:12 - 18:45 (11.5 hours)
- Second run: 21:00 - 21:54 (54 minutes)

**Critical Finding:** 🚨 **COMPLETE FAILURE - 0 steps completed, 11-12 steps failed**

**Root Cause:** All processes are failing immediately (within seconds) because they cannot find required files/directories. The VM is trying to execute processes in **local macOS paths** (`/Users/projects/Documents/...`) which don't exist on the VM.

---

## Error Summary

### First Run (07:12 - 18:45)
- **Steps Completed:** 7
- **Steps Failed:** 5
- **Duration:** 11.5 hours
- **Backup:** Failed

### Second Run (21:00 - 21:54)
- **Steps Completed:** 0
- **Steps Failed:** 11
- **Duration:** 54 minutes
- **Backup:** Failed

---

## Critical Errors Identified

### 🔴 ERROR 1: Path Configuration Issue (CRITICAL)

**All processes are failing immediately because they're using local macOS paths instead of VM paths.**

**Evidence:**
```
Working directory: /Users/projects/Documents/Property_Data_Scraping/03_Gold_Coast/...
Working directory: /Users/projects/Documents/Property_Valuation/04_Production_Valuation
Working directory: /Users/projects/Documents/Feilds_Website
```

**Problem:** The orchestrator is configured with local development paths, not VM paths.

**Expected VM paths:**
```
/home/fields/Property_Data_Scraping/03_Gold_Coast/...
/home/fields/Property_Valuation/04_Production_Valuation
/home/fields/Feilds_Website
```

**Impact:** 🚨 **CATASTROPHIC** - Every single process fails immediately

**Affected Steps:**
- Step 101: Scrape For-Sale Properties (Target Market)
- Step 103: Monitor Sold Properties (Target Market)
- Step 105: Photo Analysis & Reorder
- Step 106: Floor Plan Analysis
- Step 6: Property Valuation Model
- Step 11: Parse Room Dimensions
- Step 12: Enrich Property Timeline
- Step 13: Generate Suburb Median Prices
- Step 14: Generate Suburb Statistics
- Step 15: Calculate Property Insights
- Step 16: Enrich Properties For Sale

---

### 🔴 ERROR 2: Missing COSMOS_CONNECTION_STRING Environment Variable

**Multiple processes fail with:**
```
Error: No connection string provided.
Either set COSMOS_CONNECTION_STRING environment variable or use --connection-string argument
```

**Affected Steps:**
- Step 15: Calculate Property Insights (all 3 attempts)

**Root Cause:** The `COSMOS_CONNECTION_STRING` environment variable is not set in the VM environment.

**Impact:** Backend enrichment processes cannot connect to Azure Cosmos DB.

---

### 🔴 ERROR 3: MongoDB Rate Limiting (429 TooManyRequests)

**Error Message:**
```
Verifier failed: Error=16500, RetryAfterMs=214, Details='Response status code does not indicate success: TooManyRequests (429); Substatus: 3200
Request rate is large. More Request Units may be needed
```

**Occurrences:**
- 2026-02-12 18:45:08 (RetryAfterMs=214)
- 2026-02-12 21:54:06 (RetryAfterMs=7)

**Root Cause:** Azure Cosmos DB is throttling requests due to exceeding provisioned Request Units (RU/s).

**Impact:** Property verification step fails, preventing data integrity checks.

---

### 🔴 ERROR 4: Backup Failure

**Error Message:**
```
Volume not mounted: /Volumes/T7
Cannot access backup directory /Users/projects/Documents/MongdbBackups: [Errno 13] Permission denied: '/Users'
Volume not mounted: /Volumes/My Passport for Mac
No backup directories available!
```

**Root Cause:** Backup coordinator is configured for local macOS volumes that don't exist on the VM.

**Impact:** No backups are being created on the VM.

---

### 🔴 ERROR 5: Process Timeout Pattern

**All failed processes show the same pattern:**
- Attempt 1: Fails immediately (< 1 second)
- Retry 1: Fails after 60 seconds
- Retry 2: Fails after 60 seconds
- Total duration: ~2 minutes per process

**This indicates:** Processes are not executing at all - they're failing to start because files/directories don't exist.

---

## Detailed Error Breakdown by Process

### Step 101: Scrape For-Sale Properties (Target Market)
- **Status:** ❌ FAILED (3 attempts)
- **Duration:** 2.0 minutes
- **Working Directory:** `/Users/projects/Documents/Property_Data_Scraping/03_Gold_Coast/Gold_Coast_Wide_Currently_For_Sale_AND_Recently_Sold`
- **Command:** `python3 run_dynamic_10_suburbs.py --test --max-concurrent 2 --parallel-properties 1`
- **Root Cause:** Path doesn't exist on VM
- **Fix Required:** Update to `/home/fields/Property_Data_Scraping/03_Gold_Coast/...`

### Step 103: Monitor Sold Properties (Target Market)
- **Status:** ❌ FAILED (3 attempts)
- **Duration:** 2.0 minutes
- **Working Directory:** `/Users/projects/Documents/Property_Data_Scraping/03_Gold_Coast/Gold_Coast_Wide_Currently_For_Sale_AND_Recently_Sold`
- **Command:** `python3 monitor_sold_properties.py --test --max-concurrent 5`
- **Root Cause:** Path doesn't exist on VM
- **Fix Required:** Update to `/home/fields/Property_Data_Scraping/03_Gold_Coast/...`

### Step 105: Photo Analysis & Reorder (Target Market - Ollama)
- **Status:** ❌ FAILED (3 attempts)
- **Duration:** 2.0 minutes
- **Working Directory:** `/Users/projects/Documents/Property_Data_Scraping/03_Gold_Coast/Gold_Coast_Wide_Currently_For_Sale_AND_Recently_Sold/Ollama_Property_Analysis`
- **Command:** `./run_target_market_photo_analysis.sh`
- **Root Cause:** Path doesn't exist on VM
- **Fix Required:** Update to `/home/fields/Property_Data_Scraping/03_Gold_Coast/.../Ollama_Property_Analysis`

### Step 106: Floor Plan Analysis (Target Market - Ollama)
- **Status:** ❌ FAILED (3 attempts)
- **Duration:** 2.0 minutes
- **Working Directory:** `/Users/projects/Documents/Property_Data_Scraping/03_Gold_Coast/Gold_Coast_Wide_Currently_For_Sale_AND_Recently_Sold/Ollama_Property_Analysis`
- **Command:** `./run_target_market_floor_plan_analysis.sh`
- **Root Cause:** Path doesn't exist on VM
- **Fix Required:** Update to `/home/fields/Property_Data_Scraping/03_Gold_Coast/.../Ollama_Property_Analysis`

### Step 6: Property Valuation Model
- **Status:** ❌ FAILED (3 attempts)
- **Duration:** 2.0 minutes
- **Working Directory:** `/Users/projects/Documents/Property_Valuation/04_Production_Valuation`
- **Command:** `python3 batch_valuate_with_tracking.py`
- **Root Cause:** Path doesn't exist on VM
- **Fix Required:** Update to `/home/fields/Property_Valuation/04_Production_Valuation`

### Step 11: Parse Room Dimensions
- **Status:** ❌ FAILED (3 attempts)
- **Duration:** 2.0 minutes
- **Working Directory:** `/Users/projects/Documents/Feilds_Website`
- **Command:** `python3 10_Floor_Plans/parse_room_dimensions.py`
- **Root Cause:** Path doesn't exist on VM
- **Fix Required:** Update to `/home/fields/Feilds_Website`

### Step 12: Enrich Property Timeline
- **Status:** ❌ FAILED (3 attempts)
- **Duration:** 2.0 minutes
- **Working Directory:** `/Users/projects/Documents/Feilds_Website`
- **Command:** `python3 03_For_Sale_Coverage/enrich_property_timeline.py`
- **Root Cause:** Path doesn't exist on VM
- **Fix Required:** Update to `/home/fields/Feilds_Website`

### Step 13: Generate Suburb Median Prices
- **Status:** ❌ FAILED (3 attempts)
- **Duration:** 2.0 minutes
- **Working Directory:** `/Users/projects/Documents/Feilds_Website`
- **Command:** `python3 08_Market_Narrative_Engine/generate_suburb_medians.py`
- **Root Cause:** Path doesn't exist on VM
- **Fix Required:** Update to `/home/fields/Feilds_Website`

### Step 14: Generate Suburb Statistics
- **Status:** ❌ FAILED (3 attempts)
- **Duration:** 2.0 minutes
- **Working Directory:** `/Users/projects/Documents/Feilds_Website`
- **Command:** `python3 03_For_Sale_Coverage/generate_suburb_statistics.py`
- **Root Cause:** Path doesn't exist on VM
- **Fix Required:** Update to `/home/fields/Feilds_Website`

### Step 15: Calculate Property Insights
- **Status:** ❌ FAILED (3 attempts)
- **Duration:** 2.0 minutes
- **Working Directory:** `/Users/projects/Documents/Feilds_Website`
- **Command:** `python3 03_For_Sale_Coverage/calculate_property_insights.py`
- **Root Cause 1:** Path doesn't exist on VM
- **Root Cause 2:** Missing `COSMOS_CONNECTION_STRING` environment variable
- **Fix Required:** 
  1. Update to `/home/fields/Feilds_Website`
  2. Set `COSMOS_CONNECTION_STRING` in VM environment

### Step 16: Enrich Properties For Sale
- **Status:** ❌ FAILED (3 attempts)
- **Duration:** 2.0 minutes
- **Working Directory:** `/Users/projects/Documents/Feilds_Website`
- **Command:** `python3 10_Floor_Plans/backend/enrich_properties_for_sale.py --new-only`
- **Root Cause:** Path doesn't exist on VM
- **Fix Required:** Update to `/home/fields/Feilds_Website`

---

## Required Fixes

### 🔧 FIX 1: Update Process Commands Configuration (CRITICAL)

**File to update:** `/home/fields/Fields_Orchestrator/config/process_commands.yaml`

**Required changes:** Replace all `/Users/projects/Documents/` paths with `/home/fields/`

**Example:**
```yaml
# BEFORE (WRONG):
working_directory: /Users/projects/Documents/Property_Data_Scraping/03_Gold_Coast/...

# AFTER (CORRECT):
working_directory: /home/fields/Property_Data_Scraping/03_Gold_Coast/...
```

**Affected processes:** ALL (101, 103, 105, 106, 6, 11, 12, 13, 14, 15, 16)

---

### 🔧 FIX 2: Set COSMOS_CONNECTION_STRING Environment Variable

**Option A: Add to systemd service**
```bash
sudo nano /etc/systemd/system/fields-orchestrator.service

# Add under [Service]:
Environment="COSMOS_CONNECTION_STRING=mongodb://fields-property-cosmos:..."
```

**Option B: Add to .env file in each project**
```bash
echo "COSMOS_CONNECTION_STRING=mongodb://..." >> /home/fields/Feilds_Website/.env
```

---

### 🔧 FIX 3: Increase Azure Cosmos DB Request Units

**Current issue:** Throttling at 429 TooManyRequests

**Options:**
1. **Increase provisioned RU/s** in Azure Portal (costs more)
2. **Add retry logic with exponential backoff** in verifier code
3. **Reduce concurrent operations** to stay within limits

**Recommended:** Implement retry logic first, then increase RU/s if needed.

---

### 🔧 FIX 4: Configure VM Backup Strategy

**Current issue:** Trying to backup to local macOS volumes

**Options:**
1. **Disable backup on VM** (rely on Azure Cosmos DB backups)
2. **Configure GCP Cloud Storage backup**
3. **Use Azure Blob Storage for backups**

**Recommended:** Disable backup on VM for now (Azure Cosmos DB has automatic backups).

---

## Verification Steps

After applying fixes, verify:

1. **Check process_commands.yaml paths:**
   ```bash
   gcloud compute ssh fields-orchestrator-vm --zone=australia-southeast1-b --project=fields-estate --command='grep "working_directory:" /home/fields/Fields_Orchestrator/config/process_commands.yaml'
   ```

2. **Verify environment variable:**
   ```bash
   gcloud compute ssh fields-orchestrator-vm --zone=australia-southeast1-b --project=fields-estate --command='systemctl show fields-orchestrator | grep COSMOS_CONNECTION_STRING'
   ```

3. **Test a single process manually:**
   ```bash
   gcloud compute ssh fields-orchestrator-vm --zone=australia-southeast1-b --project=fields-estate --command='cd /home/fields/Property_Data_Scraping/03_Gold_Coast/Gold_Coast_Wide_Currently_For_Sale_AND_Recently_Sold && python3 run_dynamic_10_suburbs.py --test --max-concurrent 1 --parallel-properties 1'
   ```

4. **Trigger test run:**
   ```bash
   gcloud compute ssh fields-orchestrator-vm --zone=australia-southeast1-b --project=fields-estate --command='cd /home/fields/Fields_Orchestrator && python3 src/orchestrator_daemon.py --run-now'
   ```

---

## Priority Action Items

### 🚨 IMMEDIATE (Blocking all processes)
1. ✅ **Update process_commands.yaml with correct VM paths**
2. ✅ **Restart orchestrator service**
3. ✅ **Test one process manually**

### 🔴 HIGH (Blocking specific processes)
4. ✅ **Set COSMOS_CONNECTION_STRING environment variable**
5. ✅ **Restart orchestrator service again**

### 🟡 MEDIUM (Non-critical but important)
6. ⏳ **Implement MongoDB retry logic for 429 errors**
7. ⏳ **Disable or reconfigure backup on VM**

### 🟢 LOW (Nice to have)
8. ⏳ **Add better error logging for path issues**
9. ⏳ **Add pre-flight checks to verify paths exist**

---

## Next Steps

1. **Create fix script** to update all paths in process_commands.yaml
2. **Deploy updated configuration** to VM
3. **Set environment variables** in systemd service
4. **Restart orchestrator** service
5. **Monitor next run** to verify fixes

---

## Related Documentation

- **VM Deployment Workflow:** `/Users/projects/Documents/Cline/Rules/vm-deployment-workflow.md`
- **Process Commands Config:** `/home/fields/Fields_Orchestrator/config/process_commands.yaml`
- **Systemd Service:** `/etc/systemd/system/fields-orchestrator.service`

---

*Analysis completed: 13/02/2026, 7:53 AM Brisbane Time*
*Based on orchestrator logs from 12/02/2026 night runs*
