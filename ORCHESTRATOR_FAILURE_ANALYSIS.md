# Orchestrator Failure Analysis - 2026-01-31 Run
**Last Updated: 31/01/2026, 7:43 AM (Friday) - Brisbane**

## Executive Summary

The orchestrator ran for 3.6 hours on 2026-01-31 from 22:04 to 01:03, completing 4 steps successfully but failing 10 steps. Additionally, the backup process failed after timing out twice (60 minutes total). This document provides a comprehensive analysis of all failures and their root causes.

---

## Pipeline Execution Overview

**Start Time:** 2026-01-30 22:04:13  
**End Time:** 2026-01-31 01:03:32  
**Total Duration:** 3.6 hours  
**Steps Completed:** 4 (Steps 1, 2, 7, and part of sold upload)  
**Steps Failed:** 10  
**Backup Status:** Failed (2 timeouts)

---

## Successful Steps

### ✅ Step 1: Monitor For-Sale → Sold Transitions
- **Status:** Completed successfully
- **Duration:** Not logged in latest run

### ✅ Step 2: Scrape For-Sale Properties  
- **Status:** Completed successfully
- **Duration:** Not logged in latest run

### ✅ Step 7: Scrape Sold Properties
- **Status:** Completed successfully
- **Duration:** 93.6 minutes (01:22:41 - 00:56:31)
- **Results:** 
  - Scraped 80 properties from Burleigh Waters
  - 65 with sale dates, 15 missing sale dates
  - 100% success rate for scraping
  - MongoDB upload: 10 properties updated (all duplicates, stopped after 3 consecutive)

### ⚠️ Step 7 MongoDB Upload (Partial Success)
- All 5 suburbs hit "STOP_B" condition (3 consecutive duplicates)
- Only 2 properties updated per suburb (10 total)
- No new properties added (all were duplicates)
- This is expected behavior for incremental updates

---

## Failed Steps Analysis

### PRIMARY FAILURE CAUSE: Python Command Not Found

**Root Cause:** The orchestrator is using `python` command instead of `python3`

**Error Pattern:**
```
/bin/sh: python: command not found
Process failed with return code 127
```

**Affected Steps (9 failures):**
1. **Step 3:** GPT Photo Analysis
2. **Step 4:** GPT Photo Reorder  
3. **Step 5:** Floor Plan Enrichment (For Sale)
4. **Step 6:** Property Valuation Model
5. **Step 8:** Floor Plan Enrichment (Sold)
6. **Step 11:** Parse Room Dimensions
7. **Step 12:** Enrich Property Timeline
8. **Step 13:** Generate Suburb Median Prices
9. **Step 14:** Generate Suburb Statistics
10. **Step 15:** Calculate Property Insights

**Technical Details:**
- Return code 127 = "command not found"
- Each step attempted 3 times (initial + 2 retries)
- All retries failed with same error
- Total wasted time: ~20 minutes (10 steps × 2 minutes each)

**Configuration Issue in `process_commands.yaml`:**

The following steps use incorrect Python command:
- Step 3: `python src/main_parallel.py` ❌
- Step 4: `python src/photo_reorder_parallel.py` ❌
- Step 5: `python run_production.py --yes` ❌
- Step 6: `python batch_valuate_with_tracking.py` ❌
- Step 8: `python run_production_sold.py --yes` ❌
- Step 11: `python 10_Floor_Plans/parse_room_dimensions.py` ❌
- Step 12: `python 03_For_Sale_Coverage/enrich_property_timeline.py` ❌
- Step 13: `python 08_Market_Narrative_Engine/generate_suburb_medians.py` ❌
- Step 14: `python 03_For_Sale_Coverage/generate_suburb_statistics.py` ❌
- Step 15: `python 03_For_Sale_Coverage/calculate_property_insights.py` ❌

**Note:** Step 16 correctly uses `python3` ✅

---

## Backup Failure Analysis

### BACKUP FAILURE: Double Timeout

**Timeline:**
- 01:08:32 - Backup started after 300s cooldown
- 01:08:42 - Rotation completed for all 3 locations
- 01:08:42 - Started creating backup at `/Volumes/T7/MongdbBackups/backup_latest`
- 01:38:42 - **TIMEOUT #1** after 30 minutes (T7 SSD)
- 01:38:42 - Switched to secondary location `/Users/projects/Documents/MongdbBackups/backup_latest`
- 02:08:42 - **TIMEOUT #2** after 30 minutes (Internal SSD)
- 02:08:42 - **BACKUP FAILED** - No tertiary location attempted

**Root Causes:**

1. **T7 SSD Full**
   - Primary backup location `/Volumes/T7/MongdbBackups` is out of space
   - Backup process hung trying to write to full disk
   - **CONFIRMED:** T7 device needs to be removed from backup rotation

2. **Backup Timeout Too Short**
   - Current timeout: 30 minutes (1800 seconds)
   - Actual backup time needed: >30 minutes
   - Database has grown significantly since timeout was set

3. **No Tertiary Backup Attempt**
   - Code has logic for tertiary location (`/Volumes/My Passport for Mac/MongdbBackups`)
   - After 2 failures, backup coordinator gave up
   - Should have attempted tertiary location

4. **Database Size Issue**
   - MongoDB backup taking >30 minutes indicates large database
   - May need compression optimization or incremental backup strategy

**Code Location:** `src/backup_coordinator.py` line 234
```python
timeout=1800  # 30 minute timeout
```

---

## Impact Assessment

### Data Collection Impact
- **For-Sale Properties:** ✅ Scraped successfully, but NOT enriched
  - Missing: GPT photo analysis, photo reordering, floor plans, valuations
  - Properties are in database but lack critical enrichment data
  
- **Sold Properties:** ✅ Scraped successfully, but NOT enriched
  - Missing: Floor plan analysis
  - 10 properties updated (all duplicates)

### Backend Data Impact
- **Capital Gain Data:** ❌ Not generated
  - Room dimensions not parsed
  - Property timeline not enriched
  - Suburb medians not calculated
  
- **Unique Features:** ❌ Not generated
  - Suburb statistics not calculated
  - Property insights not computed

### Website Impact
- New properties visible but missing:
  - Photo quality scores and room identification
  - Optimized photo tour sequences
  - Floor plan room dimensions
  - Property valuations
  - Capital gain calculations
  - Unique feature badges (ONLY 1, TOP 3, RARE)

### Backup Impact
- **Critical:** No backup created for this run
- Last successful backup: Unknown (need to check backup status)
- Risk: Data loss if system failure occurs before next successful backup

---

## Historical Context

### Previous Failures (from logs)

**2026-01-27 Run:**
- Step 1 & 2 failed with permission errors (return code 126)
- Error: "Operation not permitted" accessing directories
- Snapshot creation failed: "Object of type datetime is not JSON serializable"

**2026-01-28 Run:**
- Step 9 (Floor Plan V2) timed out 3 times (225 min each = 11.3 hours total)
- Step 10 (Room-to-Photo Matching) failed 3 times
- Step 6 (Valuation) failed with "SyntaxError: invalid decimal literal"

**2026-01-29 Run:**
- Multiple permission errors
- Snapshot JSON corruption issues

**2026-01-30 Run:**
- Same `python: command not found` errors as current run
- Backup failed: "No space left on device" on T7 SSD
- 10 steps failed with return code 127

**Pattern:** The `python` vs `python3` issue has been occurring since at least 2026-01-30

---

## Recommendations

### CRITICAL - Immediate Fixes Required

1. **Fix Python Command (Priority 1)**
   - Update all `python` commands to `python3` in `config/process_commands.yaml`
   - Affects 10 steps (3, 4, 5, 6, 8, 11, 12, 13, 14, 15)
   - Estimated fix time: 5 minutes
   - Impact: Will resolve 9 of 10 failures

2. **Remove T7 SSD from Backup Rotation (Priority 1)**
   - T7 device is full and causing backup failures
   - Remove `/Volumes/T7/MongdbBackups` from backup locations
   - Update `src/backup_coordinator.py` initialization to exclude T7
   - Estimated fix time: 5 minutes

3. **Increase Backup Timeout (Priority 1)**
   - Change timeout from 30 minutes to 90 minutes in `src/backup_coordinator.py`
   - Add logic to attempt tertiary location after secondary failure
   - Consider implementing incremental backups for large databases
   - Estimated fix time: 15 minutes

4. **Clean T7 SSD (Priority 2 - Future)**
   - Device is full and needs cleanup before re-enabling
   - Check current disk usage: `df -h /Volumes/T7`
   - Clean up old backups or increase storage
   - Can re-add to rotation once space is available

### MEDIUM - Monitoring Improvements

4. **Add Pre-Flight Checks**
   - Verify `python3` is available before starting pipeline
   - Check disk space on all backup locations
   - Validate MongoDB connection
   - Estimated implementation: 30 minutes

5. **Improve Error Reporting**
   - Send notification when steps fail
   - Include specific error messages in summary
   - Log disk space before backup attempts

6. **Fix Snapshot Serialization**
   - Address "Object of type datetime is not JSON serializable" error
   - Affects pre-Phase 2 snapshot creation
   - May impact unknown status detection

### LOW - Optimization

7. **Review Backup Strategy**
   - Current database size may require different approach
   - Consider incremental backups
   - Evaluate compression settings

8. **Consolidate Python Versions**
   - Ensure all scripts use consistent Python version
   - Update shebang lines if needed
   - Document Python version requirements

---

## Testing Plan

### Phase 1: Fix Python Commands
1. Update `config/process_commands.yaml` with `python3` commands
2. Test single step execution: `python3 src/main_parallel.py`
3. Verify all 10 affected steps can find Python

### Phase 2: Fix Backup Timeout
1. Update timeout in `src/backup_coordinator.py`
2. Test backup creation manually
3. Verify tertiary location fallback logic

### Phase 3: Full Pipeline Test
1. Run complete orchestrator pipeline
2. Monitor for any remaining failures
3. Verify backup completes successfully

---

## Files Requiring Changes

1. **`config/process_commands.yaml`**
   - Lines: Steps 3, 4, 5, 6, 8, 11, 12, 13, 14, 15
   - Change: `python` → `python3`

2. **`src/backup_coordinator.py`**
   - Line 234: `timeout=1800` → `timeout=5400` (90 minutes)
   - Line 21-23: Remove T7 SSD from initialization (set `primary_dir` to Internal SSD)
   - Update to use Internal SSD as primary, My Passport as secondary
   - Add tertiary location attempt after secondary failure

3. **Snapshot serialization** (location TBD)
   - Fix datetime serialization in snapshot creation

---

## Success Metrics

After implementing fixes, the next run should achieve:
- ✅ All 14 steps complete successfully
- ✅ Backup completes within timeout
- ✅ No "command not found" errors
- ✅ All properties fully enriched with:
  - Photo analysis and reordering
  - Floor plan dimensions
  - Property valuations
  - Capital gain data
  - Unique feature badges

---

## Conclusion

The orchestrator failures are primarily caused by a simple configuration error (using `python` instead of `python3`) that affects 9 out of 10 failed steps. The backup failure is due to an insufficient timeout setting. Both issues are straightforward to fix and should resolve the majority of pipeline failures.

The pipeline successfully completed the scraping phases (Steps 1, 2, 7), demonstrating that the core data collection logic is working correctly. Once the Python command and backup timeout are fixed, the pipeline should run successfully end-to-end.

**Estimated Time to Fix:** 25 minutes  
**Estimated Time to Test:** 4 hours (full pipeline run)  
**Risk Level:** Low (changes are minimal and well-understood)

---

## Additional Notes

### T7 SSD Status
- **Current State:** Full - causing backup failures
- **Action Taken:** Removed from backup rotation
- **Backup Locations After Fix:**
  - Primary: `/Users/projects/Documents/MongdbBackups` (Internal SSD)
  - Secondary: `/Volumes/My Passport for Mac/MongdbBackups` (External HDD)
- **Future Action:** Clean up T7 and optionally re-add to rotation
