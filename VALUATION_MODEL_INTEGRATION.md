# Property Valuation Model Integration

**Last Updated:** 27/01/2026, 1:55 PM (Monday) - Brisbane

## Overview

Successfully integrated the **iteration_08 property valuation model** into the Fields Orchestrator pipeline. This model predicts property values and stores them in the MongoDB field `iteration_08_valuation.predicted_value`, which is used by the front-end valuation service.

## Integration Details

### Model Information
- **Model Name:** iteration_08_phase1
- **Model File:** `catboost_iteration_08_phase1_20251119_135151.cbm`
- **Script:** `batch_valuate_with_tracking.py`
- **Location:** `/Users/projects/Documents/Property_Valuation/04_Production_Valuation`

### MongoDB Data Flow

#### Data Written
The valuation model writes to:
```
property_data.properties_for_sale.iteration_08_valuation.predicted_value
```

#### Data Used by Front End
The front-end valuation service (`valuation_service.py`) reads from:
1. **Primary Source:** `iteration_08_valuation.predicted_value` (preferred)
2. **Fallback Source:** `valuation.mid` (if primary not available)

Code reference from `valuation_service.py` (lines 484-489):
```python
valuation_price = None
iteration_val = property_doc.get("iteration_08_valuation") or {}
if isinstance(iteration_val, dict) and isinstance(iteration_val.get("predicted_value"), (int, float)):
    valuation_price = float(iteration_val["predicted_value"])
elif isinstance(property_doc.get("valuation", {}).get("mid"), (int, float)):
    valuation_price = float(property_doc["valuation"]["mid"])
```

### Pipeline Position

The valuation model has been added as **Process ID 6** in the for-sale properties pipeline:

```yaml
- id: 6
  name: "Property Valuation Model"
  description: "Runs iteration_08 valuation model to predict property values"
  phase: "for_sale"
  command: "python batch_valuate_with_tracking.py"
  working_dir: "/Users/projects/Documents/Property_Valuation/04_Production_Valuation"
  mongodb_activity: "moderate_write"
  requires_browser: false
  estimated_duration_minutes: 45
  cooldown_seconds: 300
  depends_on: [2, 5]  # Depends on scraping and floor plan enrichment
```

### Execution Order

The complete pipeline now runs in this sequence:

1. **Phase 1: Monitoring** (ID 1)
   - Monitor For-Sale → Sold Transitions

2. **Phase 2: For-Sale Properties** (IDs 2-6)
   - Scrape For-Sale Properties (ID 2)
   - GPT Photo Analysis (ID 3)
   - GPT Photo Reorder (ID 4)
   - Floor Plan Enrichment (ID 5)
   - **Property Valuation Model (ID 6)** ← NEW

3. **Phase 3: Sold Properties** (IDs 7-8)
   - Scrape Sold Properties (ID 7)
   - Floor Plan Enrichment (ID 8)

4. **Phase 4: Backup**
   - MongoDB Backup (handled separately)

### Dependencies

The valuation model depends on:
- **Process 2:** Scrape For-Sale Properties (provides base property data)
- **Process 5:** Floor Plan Enrichment (provides floor area data for features)

The model requires the following data to be present:
- Property coordinates (LATITUDE, LONGITUDE)
- Basic property features (bedrooms, bathrooms, etc.)
- Enriched data from GPT and OSM enrichment pipelines

## Model Features

The `batch_valuate_with_tracking.py` script includes:

1. **Comprehensive Feature Calculation**
   - Base features (bedrooms, bathrooms, lot size, floor area)
   - GPT enrichment features
   - OSM location features
   - Comparable sales features
   - Suburb statistics
   - Distance calculations
   - School catchment data

2. **Missing Features Tracking**
   - Tracks which features are missing per property
   - Generates JSON reports with coverage statistics
   - Links reports to valuation metadata

3. **Dual Database Insertion**
   - Writes to `property_data.properties_for_sale`
   - Also writes to `Gold_Coast.[suburb]` collections

4. **Valuation Metadata**
   - Predicted value
   - Confidence level
   - Model version
   - Valuation date
   - Feature coverage statistics
   - Link to missing features report

## Configuration Changes

### Updated Files
- `config/process_commands.yaml` - Added valuation process (ID 6)
- Process IDs renumbered: Sold pipeline now uses IDs 7-8 (was 6-7)
- Execution order updated: `[1, 2, 3, 4, 5, 6, 7, 8]`
- Phase definitions updated to include valuation in for_sale phase

### Timing
- **Estimated Duration:** 45 minutes (varies by number of properties)
- **Cooldown:** 5 minutes before switching to sold pipeline
- **Total Pipeline Impact:** +45 minutes to overall execution time

## Testing Recommendations

Before running in production, test the integration:

1. **Dry Run Test:**
   ```bash
   cd /Users/projects/Documents/Property_Valuation/04_Production_Valuation
   python batch_valuate_with_tracking.py
   ```

2. **Verify Data Written:**
   - Check MongoDB for `iteration_08_valuation.predicted_value` field
   - Verify valuation metadata is complete
   - Check missing features reports are generated

3. **Front-End Verification:**
   - Test valuation service API endpoint
   - Verify predicted values appear in UI
   - Check for "7 Turnberry Court, Robina" (previously had no valuation)

4. **Orchestrator Test:**
   ```bash
   cd /Users/projects/Documents/Fields_Orchestrator
   python src/orchestrator_daemon.py --test-mode
   ```

## Monitoring

The orchestrator will log:
- Valuation process start/completion
- Number of properties valued
- Any errors during valuation
- Feature coverage statistics
- Links to missing features reports

Check logs at:
- `/Users/projects/Documents/Fields_Orchestrator/logs/orchestrator.log`
- `/Users/projects/Documents/Property_Valuation/04_Production_Valuation/logs/valuation.log`

## Troubleshooting

### Common Issues

1. **Missing Dependencies:**
   - Ensure CatBoost model file exists
   - Verify all Python dependencies installed
   - Check MongoDB connection

2. **Low Feature Coverage:**
   - Review missing features reports
   - Ensure GPT enrichment ran successfully
   - Verify OSM enrichment completed

3. **No Properties Valued:**
   - Check query filters in config.py
   - Verify properties have required coordinates
   - Review MongoDB query results

## Next Steps

1. Monitor first production run
2. Review valuation accuracy
3. Analyze missing features reports
4. Optimize feature coverage
5. Consider adding valuation for sold properties (future enhancement)

## References

- **Valuation Script:** `/Users/projects/Documents/Property_Valuation/04_Production_Valuation/batch_valuate_with_tracking.py`
- **Front-End Service:** `/Users/projects/Documents/Feilds_Website/07_Valuation_Comps/Compared_to_currently_listed/backend/valuation_service.py`
- **Model Location:** `/Users/projects/Documents/Property_Valuation/03_Model_Development/Iteration_04/Iteration_08/models/`
- **Orchestrator Config:** `/Users/projects/Documents/Fields_Orchestrator/config/process_commands.yaml`
