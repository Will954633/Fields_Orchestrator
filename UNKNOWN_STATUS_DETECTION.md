# Unknown Status Property Detection

**Last Updated:** 27/01/2026, 10:47 AM (Monday) - Brisbane

## Overview

The Unknown Status Detection feature identifies properties that remain in the `properties_for_sale` collection after Phase 2 completes but were not found as currently listed on Domain.com.au. These properties require manual investigation to determine their actual status.

## Purpose

During the automated data collection pipeline, properties can end up in an "unknown status" state for several reasons:

- **Delisted without selling** - Property removed from market without a sale
- **URL changes** - Domain.com.au changed the property's URL
- **Temporary removal** - Property temporarily taken off market
- **Data quality issues** - Scraping errors or database inconsistencies

This feature automatically detects these edge cases and alerts the user for manual review.

## How It Works

### 1. Pre-Phase 2 Snapshot (Before Step 2)

Before Phase 2 (For-Sale Properties Pipeline) begins, the system:
- Takes a snapshot of all properties currently in `properties_for_sale` collection
- Records each property's URL and address
- Saves snapshot to `state/for_sale_snapshot.json`

**Timing:** Immediately before Step 2 (Scrape For-Sale Properties) executes

### 2. Phase 2 Execution (Steps 2-5)

During Phase 2, the system:
- Scrapes current for-sale listings from Domain.com.au
- Updates `last_scraped` timestamp for properties found
- May move some properties to `properties_sold` if detected as sold

### 3. Post-Phase 2 Detection (After Step 5)

After Phase 2 completes, the system:
- Loads the pre-Phase 2 snapshot
- Compares with current state of `properties_for_sale` collection
- Identifies properties that:
  - Were in the snapshot (existed before Phase 2)
  - Still exist in `properties_for_sale` (not moved to sold)
  - Have NOT been scraped recently (not found during Phase 2)

### 4. User Notification

If unknown status properties are detected:
- **Popup Alert** - macOS dialog with caution symbol listing properties
- **Detailed Logging** - Full details logged to orchestrator.log
- **JSON Report** - Saved to `logs/unknown_status_report.json`

## Detection Logic

```python
# A property has "unknown status" if:
1. It was in properties_for_sale BEFORE Phase 2 started
   AND
2. It is STILL in properties_for_sale AFTER Phase 2 completed
   AND
3. It was NOT moved to properties_sold
   AND
4. Its last_scraped timestamp is NOT recent (>24 hours old or missing)
```

## Files Created/Modified

### New Files

1. **`src/unknown_status_detector.py`**
   - Main detection module
   - Handles snapshot, detection, and alerting
   - Can be run standalone for testing

2. **`state/for_sale_snapshot.json`**
   - Snapshot of properties before Phase 2
   - Created automatically before each Phase 2 run
   - Contains URLs and addresses

3. **`logs/unknown_status_report.json`**
   - Detailed report of unknown status properties
   - Created only when unknown properties detected
   - Includes timestamps and property details

### Modified Files

1. **`src/task_executor.py`**
   - Integrated snapshot and detection calls
   - Takes snapshot before Phase 2 starts
   - Runs detection after Phase 2 completes

## Popup Alert

When unknown status properties are detected, a macOS dialog appears:

```
⚠️ UNKNOWN STATUS PROPERTIES DETECTED

X properties remain in 'for_sale' collection but were NOT found 
as currently listed on Domain:

1. 123 Example Street, Brisbane QLD 4000
2. 456 Sample Road, Gold Coast QLD 4217
...

These properties require MANUAL INVESTIGATION.
Check the orchestrator logs for full details.

[View Logs]  [OK]
```

**Buttons:**
- **View Logs** - Opens Console.app with orchestrator.log
- **OK** - Dismisses the dialog

## Logging Output

When unknown status properties are detected, the logs show:

```
================================================================================
⚠️ UNKNOWN STATUS DETECTED: 3 properties
================================================================================
The following properties are in 'for_sale' collection but were NOT found
as currently listed on Domain during Phase 2 scraping:
================================================================================

1. 123 Example Street, Brisbane QLD 4000
   URL: https://www.domain.com.au/123-example-street-brisbane-qld-4000
   Last Scraped: 2026-01-20 14:30:00
   Last Updated: 2026-01-20 14:30:00

2. 456 Sample Road, Gold Coast QLD 4217
   URL: https://www.domain.com.au/456-sample-road-gold-coast-qld-4217
   Last Scraped: Never
   Last Updated: 2026-01-15 09:15:00

================================================================================
⚠️ MANUAL INVESTIGATION REQUIRED
These properties may have:
  - Been delisted without selling
  - Changed URLs on Domain
  - Temporarily removed from market
  - Data quality issues
================================================================================
```

## Manual Investigation Steps

When unknown status properties are detected:

1. **Review the Alert** - Note the number and addresses of properties
2. **Check the Logs** - Review full details in orchestrator.log
3. **Verify on Domain** - Manually search for each property on Domain.com.au
4. **Determine Status:**
   - **Still For Sale** - Property is listed but URL may have changed
   - **Sold** - Property sold but not detected by monitor
   - **Delisted** - Property removed from market
   - **Data Error** - Database inconsistency

5. **Take Action:**
   - Update property record manually if needed
   - Move to `properties_sold` if confirmed sold
   - Remove from database if delisted
   - Update URL if changed

## Testing

### Standalone Testing

Run the detector independently:

```bash
cd /Users/projects/Documents/Fields_Orchestrator && python3 -m src.unknown_status_detector
```

### Test Scenario

To test the detection:

1. Manually modify a property's `last_scraped` field to be old
2. Run Phase 2 pipeline
3. Detector should identify the property as unknown status

## Configuration

No configuration required. The detector uses:
- **MongoDB URI:** `mongodb://localhost:27017/`
- **Database:** `property_data`
- **Collections:** `properties_for_sale`, `properties_sold`
- **Recent Threshold:** 24 hours

## Integration Points

### In Pipeline Execution

```
Phase 1: Monitoring Pipeline
  └─ Step 1: Monitor For-Sale → Sold Transitions

📸 PRE-PHASE 2 SNAPSHOT TAKEN

Phase 2: For-Sale Properties Pipeline
  ├─ Step 2: Scrape For-Sale Properties
  ├─ Step 3: GPT Photo Analysis
  ├─ Step 4: GPT Photo Reorder
  └─ Step 5: Floor Plan Enrichment (For Sale)

🔍 UNKNOWN STATUS DETECTION RUNS

Phase 3: Sold Properties Pipeline
  ├─ Step 6: Scrape Sold Properties
  └─ Step 7: Floor Plan Enrichment (Sold)

Phase 4: Backup
  └─ Daily Backup
```

## Benefits

1. **Automatic Detection** - No manual checking required
2. **Immediate Alerts** - User notified right away
3. **Data Quality** - Identifies database inconsistencies
4. **Audit Trail** - Full logging and reporting
5. **Actionable** - Clear next steps for investigation

## Limitations

1. **Requires Snapshot** - First run won't have comparison data
2. **24-Hour Window** - Uses 24-hour threshold for "recent"
3. **Manual Resolution** - Requires human investigation
4. **No Auto-Fix** - Does not automatically correct issues

## Future Enhancements

Potential improvements:
- Auto-retry scraping for unknown status properties
- Integration with Domain API for verification
- Historical tracking of unknown status occurrences
- Automated URL change detection
- Email notifications in addition to popup

## Troubleshooting

### No Snapshot Found

**Issue:** "⚠️ No pre-Phase 2 snapshot found"

**Solution:** This is normal on first run. Snapshot will be created for next run.

### MongoDB Connection Failed

**Issue:** "❌ Failed to connect to MongoDB"

**Solution:** Ensure MongoDB is running: `brew services start mongodb-community`

### Popup Not Showing

**Issue:** Alert popup doesn't appear

**Solution:** Check logs for detection results. Popup only shows if unknown properties found.

## Related Documentation

- [ORCHESTRATOR_PLAN.md](ORCHESTRATOR_PLAN.md) - Overall orchestrator design
- [README.md](README.md) - General orchestrator documentation
- [config/process_commands.yaml](config/process_commands.yaml) - Pipeline configuration

## Support

For issues or questions:
1. Check orchestrator.log for detailed error messages
2. Review unknown_status_report.json for property details
3. Verify MongoDB connection and data integrity
4. Test detector standalone to isolate issues
