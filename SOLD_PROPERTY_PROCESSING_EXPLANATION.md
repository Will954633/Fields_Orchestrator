# Sold Property Processing Explanation

**Last Updated:** 30/01/2026, 8:27 AM (Thursday) - Brisbane

## Issue Report

User reported: "12 Carnoustie Court, Robina, QLD 4226" was being processed by the orchestrator even though it has sold. The concern was that it should have been moved from `properties_for_sale` to `properties_sold`.

## Investigation Results

### Current Status (Verified)
- ✅ Property is in `properties_sold` collection (1 document)
- ✅ Property is NOT in `properties_for_sale` collection (0 documents)
- ✅ Property has `sold_date: 2025-12-23`

### Processing Timeline (30/01/2026)

1. **06:52:37 - 08:06:01**: STEP 7 - Scrape Sold Properties
   - The sold properties scraper ran and found "12 Carnoustie Court"
   - Property was correctly identified as SOLD (og_title: "Sold 12 Carnoustie Court...")
   - Property was correctly added to `properties_sold` collection
   - Property was marked as duplicate during scraping (STOP_B condition)

2. **08:11:01 - 08:22:34**: STEP 8 - Floor Plan Enrichment (Sold)
   - This step processes floor plans for properties in `properties_sold` collection
   - "12 Carnoustie Court" was processed as part of this step
   - Log shows: "Retrieved property: 12 Carnoustie Court, Robina, QLD 4226"
   - Floor plan analysis completed successfully

## Root Cause Analysis

**This is CORRECT behavior, not a bug!**

The orchestrator has TWO separate pipelines:

### For-Sale Properties Pipeline (Steps 2-6, 9-15)
- Step 2: Scrape For-Sale Properties → `properties_for_sale`
- Step 3-6: Enrich for-sale properties
- Step 9-10: Floor Plan V2 processing
- Step 11-15: Backend enrichment

### Sold Properties Pipeline (Steps 7-8)
- **Step 7: Scrape Sold Properties → `properties_sold`**
- **Step 8: Floor Plan Enrichment (Sold) → processes `properties_sold`**

## Why This Property Was Processed

"12 Carnoustie Court" was processed because:

1. It was scraped by the **Sold Properties Scraper** (Step 7)
2. It was correctly placed in `properties_sold` collection
3. It was then enriched by the **Sold Properties Floor Plan Enrichment** (Step 8)

**This is the intended workflow for sold properties!**

## Verification

```bash
# Property is NOT in for_sale collection
mongosh property_data --eval "db.properties_for_sale.countDocuments({address: '12 Carnoustie Court, Robina, QLD 4226'})"
# Result: 0

# Property IS in sold collection
mongosh property_data --eval "db.properties_sold.countDocuments({address: '12 Carnoustie Court, Robina, QLD 4226'})"
# Result: 1
```

## Sold Monitor vs Sold Scraper

There are TWO different mechanisms for handling sold properties:

### 1. Sold Monitor (Step 1)
- **Purpose**: Detect when a property in `properties_for_sale` has sold
- **Action**: Moves property from `properties_for_sale` → `properties_sold`
- **Runs**: First in the pipeline (before scraping)

### 2. Sold Scraper (Step 7)
- **Purpose**: Scrape properties that are already sold (last 6 months)
- **Action**: Adds sold properties directly to `properties_sold`
- **Runs**: After for-sale pipeline completes

## Conclusion

**No fix is required.** The system is working correctly:

1. ✅ Sold properties are correctly identified
2. ✅ Sold properties are correctly stored in `properties_sold` collection
3. ✅ Sold properties are correctly enriched by the sold pipeline
4. ✅ Sold properties are NOT in `properties_for_sale` collection

The user's concern was based on a misunderstanding of which pipeline was processing the property. The logs showing "STEP 8" processing "12 Carnoustie Court" are from the **Sold Properties Pipeline**, not the For-Sale Pipeline.

## Recommendations

### For Better Clarity in Logs

Consider adding collection name to log messages to make it clearer which collection is being processed:

```python
logger.info(f"Retrieved property from properties_sold: {address}")
# vs
logger.info(f"Retrieved property from properties_for_sale: {address}")
```

This would prevent confusion when reviewing logs.

### Pipeline Execution Order

Current order (from `config/process_commands.yaml`):
```
execution_order: [1, 2, 3, 4, 5, 9, 10, 6, 11, 12, 13, 14, 15, 7, 8]
```

- Step 1: Monitor For-Sale → Sold Transitions
- Steps 2-6, 9-15: For-Sale Pipeline
- Steps 7-8: Sold Pipeline

This order is correct and ensures:
1. Existing for-sale properties are checked for sold status first
2. New for-sale properties are scraped and enriched
3. Sold properties are scraped and enriched separately
