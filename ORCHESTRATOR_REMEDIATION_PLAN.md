# Orchestrator Remediation Plan
**Last Updated: 29/01/2026, 2:17 PM (Wednesday) - Brisbane**

## Current Status Summary

### Orchestrator Run Health
- **Process Status**: Running (Step 14/15 - Scrape Sold Properties)
- **Log Last Updated**: 11:08 AM (appears stuck/hung after launching sold scraper)
- **Total Properties**: 147 in `property_data.properties_for_sale`
- **Documents Marked Complete**: **0** (none are skippable for tomorrow's run)

### Critical Errors Identified

#### 1. Step 6 (Property Valuation Model) - ❌ FAILED
**Error**: `SyntaxError: invalid decimal literal` at line 12
**Root Cause**: Invalid Python docstring header with text "Date: 20th November 2025" outside comment block
**Status**: ✅ **FIXED** - Cleaned up header, added Gold_Coast address-based join for LATITUDE/LONGITUDE

#### 2. Step 10 (Room-to-Photo Matching) - ❌ FAILED  
**Error**: `'str' object has no attribute 'get'` for property `697a03122dd05817453a97d8`
**Root Cause**: Code assumes `photo` is dict but it may be string in some cases
**Status**: ⚠️ **NEEDS FIX** - Add type checking before `.get()` calls

#### 3. Verifier Schema Mismatches
**Issues**:
- Checks for `images` field but actual field is `property_images` (147/147 have it)
- Requires `photo_tour_order` length ≥20 but max observed is 16 (0/147 meet this)
- Checks for `floor_plan_v2` artifacts but field names don't match
- Checks for `room_photo_matches` but actual field is `room_photo_matching_completed_at`

**Status**: ⚠️ **NEEDS UPDATE**

### Verification Results (Current State)

```
Total: 147 properties
Status breakdown:
  - incomplete: 147
  - complete: 0

Step-level verification (orchestrator.processing.steps.*):
  - scrape_for_sale: 0/147 ok (missing 'images' - should check 'property_images')
  - gpt_photo_analysis: 115/147 ok
  - gpt_photo_reorder: 0/147 ok (photo_tour_order too short - threshold too strict)
  - floor_plan_enrichment: 131/147 ok
  - floor_plan_v2: 0/147 ok (field name mismatch)
  - room_photo_matching: 0/147 ok (field name mismatch)
  - valuation: 0/147 ok (Step 6 failed - now fixed)
  - backend_enrichment: 147/147 ok ✓
```

### Why Tomorrow Won't Be Faster (Yet)

The orchestrator's incremental skip logic requires:
1. `orchestrator.processing.status == "complete"`
2. `orchestrator.pipeline_signature.signature` matches current

Currently:
- **0 properties** have `status="complete"`
- Verifier runs with `mark_complete=false` (conservative rollout)
- Even if we flip to `mark_complete=true`, most checks would fail due to schema mismatches

**Result**: Tomorrow's run will process all 147 properties again (no speedup).

---

## Remediation Steps

### Phase 1: Fix Broken Scripts ✅ (Partially Complete)

#### 1.1 Valuation Script (Step 6) ✅ DONE
- [x] Remove invalid docstring text causing SyntaxError
- [x] Add Gold_Coast address-based join (coords live in Gold_Coast.<suburb> collections)
- [x] Parse `street_address` into components (STREET_NO_1, STREET_NO_1_SUFFIX, STREET_NAME, STREET_TYPE)
- [x] Match to Gold_Coast using parsed components + postcode
- [x] Merge LATITUDE/LONGITUDE from Gold_Coast into for-sale doc for feature calculation
- [x] Add CLI flags (--limit, --for-sale-id) for targeted reruns

#### 1.2 Room-Photo Matching Script (Step 10) ⚠️ TODO
- [ ] Add defensive type checking before `.get()` calls on photo objects
- [ ] Handle case where `photo` might be string instead of dict
- [ ] Add try/except around photo processing to prevent single-property failures from crashing batch

### Phase 2: Update Verifier Schema Checks

#### 2.1 Fix Field Name Mismatches
- [ ] `scrape_for_sale`: Check `property_images` instead of `images`
- [ ] `gpt_photo_reorder`: Lower threshold from ≥20 to ≥5 (or make it optional)
- [ ] `floor_plan_v2`: Accept `floor_plan_analysis.rooms` as valid (already exists)
- [ ] `room_photo_matching`: Check `room_photo_matching_completed_at` field

#### 2.2 Make Checks More Permissive
- [ ] `valuation`: Accept `property_valuation_data.structural` OR `iteration_08_valuation.predicted_value`
- [ ] `backend_enrichment`: Already works ✓

### Phase 3: Rerun Failed Steps

#### 3.1 Rerun Step 10 (Room-Photo Matching)
```bash
cd /Users/projects/Documents/Feilds_Website && \
python3 match_floor_plan_rooms_to_photos.py --property-id 697a03122dd05817453a97d8
```

#### 3.2 Rerun Step 6 (Valuation) for All 147
```bash
cd /Users/projects/Documents/Property_Valuation/04_Production_Valuation && \
python batch_valuate_with_tracking.py
```

### Phase 4: Enable Completion Marking

#### 4.1 Update task_executor.py
Change verifier instantiation from:
```python
mark_complete=False,
```
to:
```python
mark_complete=True,
```

#### 4.2 Rerun Verifier
```python
from src.property_processing_verifier import PropertyProcessingVerifier
verifier = PropertyProcessingVerifier(
    mongo_uri="mongodb://127.0.0.1:27017/",
    database="property_data",
    pipeline_version=2,
    pipeline_signature="sha256:cfca0f94ba28ca7f89d9dabc3725b97defeac74d4f61fe6e03d76fd842df1153",
    dry_run=False,
    write_verification_results=True,
    mark_complete=True,  # ← Enable completion marking
)
verifier.connect()
result = verifier.verify_and_update(run_id="manual-remediation-2026-01-29")
print(result)
verifier.close()
```

### Phase 5: Confirm Results

#### 5.1 Check MongoDB Counts
```javascript
db.properties_for_sale.aggregate([
  {$group: {_id: "$orchestrator.processing.status", n: {$sum: 1}}},
  {$sort: {n: -1}}
])
```

Expected after remediation:
- `complete`: ~140-147 (depending on how many pass all checks)
- `incomplete`: ~0-7

#### 5.2 Verify Skip Logic
```javascript
const sig = "sha256:cfca0f94ba28ca7f89d9dabc3725b97defeac74d4f61fe6e03d76fd842df1153";
db.properties_for_sale.countDocuments({
  "orchestrator.processing.status": "complete",
  "orchestrator.pipeline_signature.signature": sig
})
```

This count = number of properties that will be skipped tomorrow (except for price/agent/inspection changes).

---

## Expected Outcome

After completing all remediation steps:
1. **Step 6 & 10 errors resolved** → All 147 properties successfully processed
2. **Verifier schema aligned** → Accurate completeness detection
3. **Completion marking enabled** → Properties marked `status="complete"`
4. **Tomorrow's run**: Only process new/changed/incomplete properties (dramatic speedup)

---

## Next Actions

1. Fix room-photo matching robustness
2. Update verifier schema checks
3. Rerun Step 10 for failing property
4. Rerun Step 6 for all 147 properties
5. Run verifier with mark_complete=true
6. Confirm completion counts in MongoDB
