# VM Config Deployment Issue - RESOLVED
# Last Edit: 13/02/2026, 7:59 AM (Friday) — Brisbane Time
#
# Description: Root cause analysis and resolution of orchestrator night run failures
# The issue was NOT a code problem - it was a deployment problem

---

## 🎯 Root Cause Identified

**The orchestrator night run failed because the updated cloud configuration file was never deployed to the VM.**

### What Happened

1. **Feb 10, 2026**: We created `02_Deployment/config/process_commands_cloud.yaml` with correct VM paths (`/home/fields/...`)
2. **Feb 10-12, 2026**: We tested manually, made optimizations, everything worked
3. **Feb 12, 2026 Night**: Scheduled run failed completely (0 steps completed, 11 failed)
4. **Feb 13, 2026**: Investigation revealed the VM was still using the old Feb 4 config with macOS paths

### The Problem

The VM's `process_commands.yaml` file (last modified Feb 4) contained:
```yaml
working_dir: "/Users/projects/Documents/Property_Data_Scraping/..."
```

But it should have contained:
```yaml
working_dir: "/home/fields/Property_Data_Scraping/..."
```

**Result**: Every process failed immediately because the directories didn't exist.

---

## 🔍 Why This Happened

We had **two separate config files**:

1. **Local (Mac) version**: `config/process_commands.yaml`
   - Used for local development
   - Paths: `/Users/projects/Documents/...`

2. **Cloud (VM) version**: `02_Deployment/config/process_commands_cloud.yaml`
   - Created for VM deployment
   - Paths: `/home/fields/...`
   - **Never deployed to the VM**

The cloud config file existed locally but was never copied to the VM, so the orchestrator continued using the old Feb 4 config.

---

## ✅ Resolution

### Step 1: Deployed Correct Config
```bash
cd /Users/projects/Documents/Fields_Orchestrator
gcloud compute scp 02_Deployment/config/process_commands_cloud.yaml \
  fields-orchestrator-vm:/home/fields/Fields_Orchestrator/config/process_commands.yaml \
  --zone=australia-southeast1-b --project=fields-estate
```

### Step 2: Restarted Orchestrator Service
```bash
gcloud compute ssh fields-orchestrator-vm \
  --zone=australia-southeast1-b --project=fields-estate \
  --command='sudo systemctl restart fields-orchestrator'
```

### Step 3: Verified Paths
```bash
gcloud compute ssh fields-orchestrator-vm \
  --zone=australia-southeast1-b --project=fields-estate \
  --command='grep "working_dir:" /home/fields/Fields_Orchestrator/config/process_commands.yaml | head -5'
```

**Result**: All paths now correctly show `/home/fields/...`

---

## 📊 Error Analysis Summary

### Night Run Results (Before Fix)

**First Run (07:12-18:45):**
- Steps Completed: 7
- Steps Failed: 5
- Duration: 11.5 hours

**Second Run (21:00-21:54):**
- Steps Completed: 0
- Steps Failed: 11
- Duration: 54 minutes

### All Failed Processes

1. **Step 101**: Scrape For-Sale Properties (Target Market) - ❌ FAILED
2. **Step 103**: Monitor Sold Properties (Target Market) - ❌ FAILED
3. **Step 105**: Photo Analysis & Reorder - ❌ FAILED
4. **Step 106**: Floor Plan Analysis - ❌ FAILED
5. **Step 6**: Property Valuation Model - ❌ FAILED
6. **Step 11**: Parse Room Dimensions - ❌ FAILED
7. **Step 12**: Enrich Property Timeline - ❌ FAILED
8. **Step 13**: Generate Suburb Median Prices - ❌ FAILED
9. **Step 14**: Generate Suburb Statistics - ❌ FAILED
10. **Step 15**: Calculate Property Insights - ❌ FAILED
11. **Step 16**: Enrich Properties For Sale - ❌ FAILED

**Common Pattern**: All processes failed within 2 minutes (3 attempts each, 60 seconds per retry)

---

## 🔧 Additional Issues Found (Not Yet Fixed)

### 1. Missing COSMOS_CONNECTION_STRING Environment Variable

**Error:**
```
Error: No connection string provided.
Either set COSMOS_CONNECTION_STRING environment variable or use --connection-string argument
```

**Affected**: Step 15 (Calculate Property Insights)

**Fix Required**: Add to systemd service or .env file

### 2. MongoDB Rate Limiting (429 TooManyRequests)

**Error:**
```
Verifier failed: Error=16500, RetryAfterMs=214
Request rate is large. More Request Units may be needed
```

**Impact**: Property verification step fails

**Fix Required**: Implement retry logic or increase Azure Cosmos DB RU/s

### 3. Backup Failure

**Error:**
```
Volume not mounted: /Volumes/T7
Cannot access backup directory /Users/projects/Documents/MongdbBackups
No backup directories available!
```

**Impact**: No backups being created

**Fix Required**: Disable backup on VM (Azure Cosmos DB has built-in backups)

---

## 🎓 Lessons Learned

### 1. Deployment Checklist Gap

**Problem**: We had no checklist to ensure cloud configs are deployed

**Solution**: Created deployment checklist in `.clinerules/vm-deployment-workflow.md`

### 2. Config File Confusion

**Problem**: Two config files with similar names but different purposes

**Solution**: Clear naming convention:
- `config/process_commands.yaml` = Local (Mac)
- `02_Deployment/config/process_commands_cloud.yaml` = Cloud (VM)

### 3. Manual Testing vs Scheduled Runs

**Problem**: Manual testing worked because we ran processes directly, bypassing the orchestrator config

**Solution**: Always test via orchestrator daemon, not just individual scripts

---

## ✅ Verification Steps

### Confirm Paths Are Correct
```bash
gcloud compute ssh fields-orchestrator-vm \
  --zone=australia-southeast1-b --project=fields-estate \
  --command='grep "working_dir:" /home/fields/Fields_Orchestrator/config/process_commands.yaml'
```

**Expected**: All paths show `/home/fields/...`

### Confirm Service Is Running
```bash
gcloud compute ssh fields-orchestrator-vm \
  --zone=australia-southeast1-b --project=fields-estate \
  --command='sudo systemctl status fields-orchestrator --no-pager'
```

**Expected**: `Active: active (running)`

### Monitor Next Scheduled Run
```bash
gcloud compute ssh fields-orchestrator-vm \
  --zone=australia-southeast1-b --project=fields-estate \
  --command='tail -f /home/fields/Fields_Orchestrator/logs/orchestrator.log'
```

**Next run**: Tonight at 20:30 (8:30 PM Brisbane time)

---

## 📝 Next Steps

### Immediate (Before Tonight's Run)
1. ✅ **Deploy correct config** - DONE
2. ✅ **Restart orchestrator** - DONE
3. ⏳ **Set COSMOS_CONNECTION_STRING** environment variable
4. ⏳ **Disable backup on VM** (or configure cloud backup)

### Medium Priority
5. ⏳ **Implement MongoDB retry logic** for 429 errors
6. ⏳ **Add pre-flight path checks** to orchestrator
7. ⏳ **Create deployment automation script**

### Low Priority
8. ⏳ **Add better error logging** for path issues
9. ⏳ **Document all environment variables** needed

---

## 🔗 Related Documentation

- **VM Deployment Workflow**: `/Users/projects/Documents/Cline/Rules/vm-deployment-workflow.md`
- **Error Analysis**: `VM_ORCHESTRATOR_NIGHT_RUN_ERROR_ANALYSIS.md`
- **Process Commands (Cloud)**: `02_Deployment/config/process_commands_cloud.yaml`
- **Process Commands (Local)**: `config/process_commands.yaml`

---

## 📊 Status

- **Issue**: ✅ RESOLVED
- **Config Deployed**: ✅ YES
- **Service Running**: ✅ YES
- **Paths Verified**: ✅ CORRECT
- **Ready for Tonight**: ⚠️ MOSTLY (still need COSMOS_CONNECTION_STRING)

---

*Issue resolved: 13/02/2026, 7:59 AM Brisbane Time*
*Next scheduled run: 13/02/2026, 8:30 PM Brisbane Time*
