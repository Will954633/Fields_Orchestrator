# Data Integrity Debug Logging System

**Last Updated:** 05/02/2026, 8:19 AM (Wednesday) - Brisbane

## Overview

This debug logging system monitors and verifies data integrity throughout the Fields Orchestrator processes. It ensures that:

1. **Sold properties** are properly migrated with all historical data preserved
2. **Static records** in the Gold_Coast database are updated with sale information
3. **New listings** are matched to their static records before they sell

## Components

### 1. Data Integrity Monitor (`data_integrity_monitor.py`)

Verifies data integrity for sold properties and new listings.

**Key Checks:**
- ✅ Last known listing price is preserved (not overwritten by sold price)
- ✅ Complete price history is maintained
- ✅ Agent description history is maintained
- ✅ Property removed from `properties_for_sale` collection
- ✅ Property exists in `properties_sold` collection
- ✅ Static record updated with sale information
- ✅ New listings have links to static records

**Usage:**
```bash
cd /Users/projects/Documents/Fields_Orchestrator && python3 01_Debug_Log/data_integrity_monitor.py --run-id <RUN_ID>
```

**Output:**
- Detailed console logging
- JSON report saved to `01_Debug_Log/logs/integrity_report_<RUN_ID>_<TIMESTAMP>.json`

### 2. Static Record Matcher (`static_record_matcher.py`)

Matches newly listed properties to their static records in the Gold_Coast database.

**Matching Strategy:**
1. **Exact match** - Direct address match (preferred)
2. **Fuzzy match** - Normalized address matching (handles variations like "Street" vs "St")
3. **No match** - Property not found in static database

**Usage:**
```bash
# Match only new listings from current run
cd /Users/projects/Documents/Fields_Orchestrator && python3 01_Debug_Log/static_record_matcher.py --run-id <RUN_ID> --mode new

# Match all unmatched properties
cd /Users/projects/Documents/Fields_Orchestrator && python3 01_Debug_Log/static_record_matcher.py --run-id <RUN_ID> --mode all
```

**What it does:**
- Finds the property's static record in Gold_Coast database
- Adds `gold_coast_doc_id` to the property's orchestrator metadata
- Stores suburb and matching confidence level
- Enables future updates to static record when property sells

### 3. Debug Checks Runner (`run_debug_checks.py`)

Wrapper script that runs all debug checks in sequence.

**Usage:**
```bash
cd /Users/projects/Documents/Fields_Orchestrator && python3 01_Debug_Log/run_debug_checks.py --run-id <RUN_ID>
```

**Process:**
1. Matches new listings to static records
2. Runs data integrity verification
3. Generates comprehensive reports
4. Returns exit code 0 (success) or 1 (failures detected)

## Integration with Orchestrator

### Automatic Integration

To integrate these checks into the orchestrator workflow, add to `src/task_executor.py` or call from the orchestrator daemon after the main pipeline completes:

```python
from pathlib import Path
import subprocess

def run_debug_checks(run_id: str) -> bool:
    """Run debug checks after orchestrator completes"""
    script_path = Path(__file__).parent.parent / "01_Debug_Log" / "run_debug_checks.py"
    
    result = subprocess.run(
        ["python3", str(script_path), "--run-id", run_id],
        capture_output=True,
        text=True
    )
    
    return result.returncode == 0
```

### Manual Testing

For manual testing or debugging specific runs:

```bash
# Get the run_id from orchestrator logs or state files
RUN_ID="20260205_081900"

# Run all checks
cd /Users/projects/Documents/Fields_Orchestrator && python3 01_Debug_Log/run_debug_checks.py --run-id $RUN_ID

# Or run individual components
cd /Users/projects/Documents/Fields_Orchestrator && python3 01_Debug_Log/static_record_matcher.py --run-id $RUN_ID --mode new
cd /Users/projects/Documents/Fields_Orchestrator && python3 01_Debug_Log/data_integrity_monitor.py --run-id $RUN_ID
```

## Log Files and Reports

### Directory Structure

```
01_Debug_Log/
├── data_integrity_monitor.py
├── static_record_matcher.py
├── run_debug_checks.py
├── README.md
└── logs/
    ├── integrity_report_<RUN_ID>_<TIMESTAMP>.json
    └── (additional reports...)
```

### Report Format

Each integrity report contains:

```json
{
  "run_id": "20260205_081900",
  "timestamp": "2026-02-05 08:19:00",
  "sold_properties_checked": 5,
  "sold_properties_passed": 4,
  "sold_properties_failed": 1,
  "new_listings_checked": 12,
  "new_listings_matched": 11,
  "new_listings_unmatched": 1,
  "static_update_failures": ["123 Main St, Robina"],
  "sold_property_details": [...],
  "new_listing_details": [...],
  "errors": []
}
```

## Data Integrity Requirements

### Requirement 1: Sold Property Data Preservation

When a property moves from `properties_for_sale` to `properties_sold`:

✅ **MUST preserve:**
- Last known listing price (in `orchestrator.history.price`)
- Complete price change history with timestamps
- Complete agent description history with timestamps
- All listing metadata

❌ **MUST NOT:**
- Overwrite listing price with sold price
- Lose any historical data
- Leave property in for_sale collection

### Requirement 2: Static Record Updates

When a property sells:

✅ **MUST update** Gold_Coast database static record with:
- Sale price
- Sale date
- Sale method (auction, private, etc.)
- Agents involved
- Agency information
- Complete timeline of the sale process

❌ **MUST log failures** when static record update fails

### Requirement 3: New Listing Matching

When a property is first added to `properties_for_sale`:

✅ **MUST:**
- Match to static record in Gold_Coast database
- Store `gold_coast_doc_id` in orchestrator metadata
- Store suburb and match confidence
- Enable future static record updates

⚠️ **SHOULD warn** when matching fails (property may be new construction)

## Troubleshooting

### No Static Record Found

**Issue:** New listing cannot be matched to static record

**Possible Causes:**
1. Property is new construction (not in static database yet)
2. Address format mismatch
3. Property in different suburb than expected

**Resolution:**
- Check if property exists in Gold_Coast database manually
- Verify address format matches static records
- Consider adding manual matching rules for edge cases

### Static Record Update Failed

**Issue:** Sold property's static record was not updated

**Possible Causes:**
1. No `gold_coast_doc_id` link (property was never matched)
2. Static record was deleted or moved
3. Database connection issue during update

**Resolution:**
- Check integrity report for specific property addresses
- Manually verify static record exists
- Re-run matching for unmatched properties
- Update static record manually if needed

### Price History Lost

**Issue:** Sold property has no price history

**Possible Causes:**
1. Property was added directly to sold collection (bypassed for_sale)
2. Field change tracker not running
3. Price field name mismatch

**Resolution:**
- Verify field change tracker runs before sold migration
- Check price field names in scraper output
- Review orchestrator execution order

## Monitoring Best Practices

1. **Review reports after each run** - Check for failures and warnings
2. **Track matching success rate** - Should be >95% for established suburbs
3. **Monitor static update failures** - Should be near zero
4. **Archive old reports** - Keep last 30 days for trend analysis
5. **Alert on repeated failures** - Same property failing multiple times needs investigation

## Future Enhancements

Potential improvements to consider:

1. **Automated alerts** - Email/Slack notifications for failures
2. **Trend analysis** - Track success rates over time
3. **Manual matching UI** - Web interface for resolving unmatched properties
4. **Batch remediation** - Scripts to fix historical data issues
5. **Performance metrics** - Track execution time and resource usage

## Support

For issues or questions:
- Review orchestrator logs: `logs/orchestrator.log`
- Check integrity reports: `01_Debug_Log/logs/`
- Examine MongoDB collections directly using `mongosh`

## Version History

- **05/02/2026** - Initial creation
  - Data integrity monitor
  - Static record matcher
  - Debug checks runner
  - Comprehensive documentation
