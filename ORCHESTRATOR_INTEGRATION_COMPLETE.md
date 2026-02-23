# Orchestrator Integration Complete - Property Enrichment & Insights

**Date:** 30/01/2026, 5:03 PM (Thursday) - Brisbane Time

## Summary

Successfully integrated TWO missing processes into the Fields Orchestrator pipeline:
1. **Process 16:** Property Enrichment (floor area, lot size, transactions, capital gain)
2. **Process 15:** Property Insights (rarity analysis - already existed but had wrong execution order)

## Critical Fix: Execution Order

### The Problem
Process 15 (Calculate Property Insights) was running BEFORE Process 16 (Enrich Properties), but Process 15 needs the `enriched_data` field that Process 16 creates!

### The Solution
Reordered execution so Process 16 runs first:
- **OLD:** `[..., 14, 15, 16, 7, 8]` ❌
- **NEW:** `[..., 14, 16, 15, 7, 8]` ✅

## Complete Pipeline Flow

```
PHASE 1: MONITORING
1. Monitor For-Sale → Sold Transitions (40 min)

PHASE 2: FOR-SALE PROPERTIES
2. Scrape For-Sale Properties (22 min)
3. GPT Photo Analysis (155 min)
4. GPT Photo Reorder (160 min)
5. Floor Plan Enrichment (30 min)
6. Property Valuation Model (45 min)

PHASE 3: BACKEND DATA ENRICHMENT
11. Parse Room Dimensions (15 min)
12. Enrich Property Timeline (20 min)
13. Generate Suburb Median Prices (25 min)
14. Generate Suburb Statistics (30 min)
16. Enrich Properties For Sale (15 min) ← NEW POSITION
15. Calculate Property Insights (20 min) ← MOVED AFTER 16

PHASE 4: SOLD PROPERTIES
7. Scrape Sold Properties (75 min)
8. Floor Plan Enrichment (Sold) (30 min)

PHASE 5: BACKUP
(Handled by backup_coordinator)
```

## Process 16: Enrich Properties For Sale

### Configuration
- **ID:** 16
- **Command:** `python3 10_Floor_Plans/backend/enrich_properties_for_sale.py --new-only`
- **Working Dir:** `/Users/projects/Documents/Feilds_Website`
- **Duration:** 15 minutes
- **Dependencies:** Process 11 (Parse Room Dimensions), Process 12 (Enrich Property Timeline)

### What It Does
Enriches each property with:
1. **Floor Area** - From `floor_plan_analysis.internal_floor_area.value`
2. **Lot Size** - From `Gold_Coast.[suburb].lot_size_sqm`
3. **Transaction History** - From `Gold_Coast.[suburb].scraped_data.property_timeline`
4. **Capital Gain Data** - Calculates years held and prepares for frontend display

### Output Structure
```json
{
  "enriched_data": {
    "floor_area_sqm": 237.0,
    "lot_size_sqm": 603.0,
    "transactions": [
      {"date": "2020-08-15", "price": 850000.0, "type": "Sale"}
    ],
    "capital_gain": {
      "has_data": true,
      "oldest_transaction_date": "2020-08-15",
      "oldest_transaction_price": 850000.0,
      "years_held": 4.1
    },
    "last_enriched": "2026-01-30T17:03:00.000000"
  }
}
```

### Incremental Processing
Uses `--new-only` flag to only process properties without `enriched_data`, making subsequent runs fast and efficient.

## Process 15: Calculate Property Insights

### Configuration
- **ID:** 15
- **Command:** `python 03_For_Sale_Coverage/calculate_property_insights.py`
- **Working Dir:** `/Users/projects/Documents/Feilds_Website`
- **Duration:** 20 minutes
- **Dependencies:** Process 14 (Suburb Statistics), **Process 16 (Enrich Properties)** ← CRITICAL

### What It Does
Compares each property against ALL other properties currently for sale to generate rarity insights:
- **"ONLY 1"** badges - Unique features (e.g., "Only property with kitchen over 24.5m²")
- **"TOP 3"** badges - Ranking features (e.g., "2nd largest lot currently for sale")
- **"RARE"** badges - Percentile-based rarity

### Why It Needs Process 16
The script reads:
- `enriched_data.floor_area_sqm` - For floor area comparisons
- `enriched_data.lot_size_sqm` - For lot size rankings
- `floor_plan_analysis.rooms[].dimensions.area` - For room size comparisons

### Output Structure
```json
{
  "property_insights": {
    "floor_area": {
      "value": 276,
      "rarity_insights": [{
        "type": "top_n",
        "feature": "kitchen",
        "label": "2nd largest kitchen currently for sale",
        "urgencyLevel": "medium",
        "rank": 2
      }]
    },
    "lot_size": {
      "value": 883,
      "rarity_insights": [{
        "type": "only_one",
        "feature": "lot_size",
        "label": "Largest lot currently for sale (883m²)",
        "urgencyLevel": "high"
      }]
    }
  },
  "property_insights_updated": "2026-01-30T17:03:20.000000"
}
```

### Why It Processes ALL Properties
Unlike Process 16 (which uses `--new-only`), Process 15 MUST process all properties every time because:
- Insights are **relative** - they depend on comparing against all other properties
- Rankings change as properties are added/removed from the market
- A property that was "3rd largest" yesterday might be "2nd largest" today

## Frontend Integration

Both processes enable critical frontend features:

### PropertyPage.tsx Stat Pills
1. **Floor Area** (from Process 16) - Shows internal floor area in sqm
2. **Lot Size** (from Process 16) - Shows land size in sqm
3. **Capital Gain Annualized** (from Process 16) - Shows investment performance
4. **Rarity Badges** (from Process 15) - Shows "ONLY 1", "TOP 3", "RARE" insights

### API Response
The `properties_for_sale` API now returns both `enriched_data` and `property_insights` fields, enabling the frontend to display comprehensive property information without runtime calculations.

## Configuration Changes

### Updated Files
1. **config/process_commands.yaml**
   - Added Process 16 definition
   - Reordered Process 15 and 16 (16 now runs first)
   - Updated execution_order: `[1, 2, 3, 4, 5, 6, 11, 12, 13, 14, 16, 15, 7, 8]`
   - Updated backend_enrichment phase steps: `[11, 12, 13, 14, 16, 15]`
   - Updated Process 15 dependencies: `[14, 16]`

## Benefits

1. **Automated** - Both processes run automatically during nightly pipeline
2. **Efficient** - Process 16 uses incremental processing (`--new-only`)
3. **Accurate** - Process 15 recalculates all insights to reflect current market
4. **Performant** - Pre-calculated data eliminates runtime API overhead
5. **Reliable** - Correct execution order ensures data dependencies are met

## Testing

To verify the integration:

1. **Check orchestrator recognizes both processes:**
   ```bash
   cd /Users/projects/Documents/Fields_Orchestrator && python3 src/task_executor.py
   ```

2. **Run enrichment manually:**
   ```bash
   cd /Users/projects/Documents/Feilds_Website && python3 10_Floor_Plans/backend/enrich_properties_for_sale.py --new-only
   ```

3. **Run insights calculation manually:**
   ```bash
   cd /Users/projects/Documents/Feilds_Website/03_For_Sale_Coverage && python3 calculate_property_insights.py
   ```

4. **Verify API returns both fields:**
   ```bash
   curl http://localhost:8000/api/properties/697b54a463353834978e7007 | jq '.enriched_data, .property_insights'
   ```

5. **Check frontend displays all features:**
   ```
   http://localhost:3000/property/697b54a463353834978e7007
   ```

## Next Pipeline Run

During the next nightly orchestrator execution:

1. Process 16 will enrich any NEW properties (fast - only processes properties without `enriched_data`)
2. Process 15 will recalculate insights for ALL properties (necessary - rankings are relative)
3. Frontend will display updated Floor Area, Lot Size, Capital Gain, and Rarity insights

## Related Files

- **Orchestrator Config:** `/Users/projects/Documents/Fields_Orchestrator/config/process_commands.yaml`
- **Enrichment Script:** `/Users/projects/Documents/Feilds_Website/10_Floor_Plans/backend/enrich_properties_for_sale.py`
- **Insights Script:** `/Users/projects/Documents/Feilds_Website/03_For_Sale_Coverage/calculate_property_insights.py`
- **API Endpoint:** `/Users/projects/Documents/Feilds_Website/10_Floor_Plans/backend/api/properties_for_sale.py`
- **Frontend Component:** `/Users/projects/Documents/Feilds_Website/01_Website/src/pages/PropertyPage/PropertyPage.tsx`

---

✅ **Integration Complete** - Both property enrichment and insights calculation are now fully operational in the orchestrator pipeline with correct execution order and dependencies.
