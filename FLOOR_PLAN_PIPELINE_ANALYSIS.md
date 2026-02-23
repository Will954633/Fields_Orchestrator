# Floor Plan Pipeline Analysis
# Last Updated: 30/01/2026, 10:31 AM (Thursday) - Brisbane

## Executive Summary

**ROOT CAUSE IDENTIFIED:** The orchestrator is using the WRONG floor plan processing pipeline.

There are **TWO DIFFERENT PIPELINES** in the codebase:

| Pipeline | Location | Output Files | Status |
|----------|----------|--------------|--------|
| **CORRECT** | `07_Valuation_Comps/Compared_to_currently_listed/backend/floorplan_processing/` | `level_1.webp`, `level_2.webp` | **NOT USED** |
| **WRONG** | `10_Floor_Plans/background_processor/` | `plan_1_no_text.png`, `plan_2_no_text.png` | **CURRENTLY USED** |

---

## The CORRECT Pipeline (07_Valuation_Comps)

### Documentation
- `/Users/projects/Documents/Feilds_Website/10_Floor_Plans/00_Process_From_Raw_To_Website.md`

### What It Does
1. Downloads raw floor plan from MongoDB `floor_plans[0]` URL
2. Runs Google Vision OCR
3. Detects levels (Ground Floor, First Floor, etc.)
4. Crops each level
5. **CLEANS the image** using `PLAN_CLEANER_SCRIPT`
6. Extracts rooms from OCR data
7. Saves to:
   - `files/floorplans_cache/{property_id}/level_1.webp` (optimized WEBP)
   - `files/floorplans_cache/{property_id}/level_2.webp`
   - `files/floorplans_cache/{property_id}/interactive.json`
   - `files/floorplans_cache/{property_id}/metadata.json`
8. Upserts to MongoDB `property_floorplan_interactive` collection

### How to Run
```bash
cd /Users/projects/Documents/Feilds_Website/07_Valuation_Comps/Compared_to_currently_listed/backend
python -m floorplan_processing.process_floor_plan --property-id {property_id} --force
```

### Key Files
- `process_floor_plan.py` - Main entrypoint
- `storage.py` - Saves files and MongoDB
- `config.py` - Configuration (OUTPUT_FORMAT = "webp")
- `image_cleaner.py` - Cleans floor plan images
- `level_detector.py` - Detects multiple levels
- `room_extractor.py` - Extracts room labels

---

## The WRONG Pipeline (10_Floor_Plans - Currently Used)

### What It Does
1. Reads from `10_Floor_Plans/processed_floor_plans/property_{id}/`
2. Copies `cleaned/*/final_padded.png` to cache
3. Creates `interactive.json` with room detection
4. **DOES NOT** run the full processing pipeline
5. **DOES NOT** create optimized WEBP images
6. **DOES NOT** upsert to MongoDB

### Output Files
- `files/floorplans_cache/{property_id}/plan_1_no_text.png` (PNG, not WEBP)
- `files/floorplans_cache/{property_id}/plan_2_no_text.png`
- `files/floorplans_cache/{property_id}/interactive.json`

### Problems
1. **Wrong file format** - PNG instead of WEBP
2. **Wrong file names** - `plan_1_no_text.png` instead of `level_1.webp`
3. **Depends on pre-processed data** - Requires `10_Floor_Plans/processed_floor_plans/` to exist
4. **No MongoDB persistence** - Doesn't upsert to `property_floorplan_interactive`
5. **No image cleaning** - Just copies existing files

---

## Current State of Test Property (693e8ea2ee434af1738b8f8e)

### Files in Cache
```
files/floorplans_cache/693e8ea2ee434af1738b8f8e/
├── interactive.json      (Jan 30 10:17) - Created by batch_interactive_floor_plan_processor.py
├── plan_1_no_text.png    (Jan 11 12:24) - Copied from 10_Floor_Plans/processed_floor_plans/
└── plan_2_no_text.png    (Jan 11 12:24) - Copied from 10_Floor_Plans/processed_floor_plans/
```

### What's Missing
- `level_1.webp` - Should be created by CORRECT pipeline
- `level_2.webp` - Should be created by CORRECT pipeline
- `metadata.json` - Should be created by CORRECT pipeline
- MongoDB document in `property_floorplan_interactive`

### interactive.json URLs
```json
"processed_image_url": "http://localhost:3050/static/floorplans/693e8ea2ee434af1738b8f8e/plan_1_no_text.png"
```

Should be:
```json
"processed_image_url": "http://localhost:3050/static/floorplans/693e8ea2ee434af1738b8f8e/level_1.webp"
```

---

## The Solution

### Option 1: Use the CORRECT Pipeline (Recommended)

Update the orchestrator to use the CORRECT pipeline from `07_Valuation_Comps`:

```yaml
- id: 9
  name: "Floor Plan Processing (Full Pipeline)"
  description: "Downloads, processes, cleans, and creates interactive floor plans"
  phase: "for_sale"
  command: "python -m floorplan_processing.process_floor_plan --batch"
  working_dir: "/Users/projects/Documents/Feilds_Website/07_Valuation_Comps/Compared_to_currently_listed/backend"
  mongodb_activity: "moderate_write"
  requires_browser: false
  estimated_duration_minutes: 120  # Full processing takes longer
  cooldown_seconds: 180
  depends_on: [2, 5]
```

**Note:** Need to create a batch processing script for this pipeline.

### Option 2: Fix the Current Pipeline

Update `batch_interactive_floor_plan_processor.py` to:
1. Use WEBP format instead of PNG
2. Use `level_1.webp` naming instead of `plan_1_no_text.png`
3. Optimize images for web
4. Upsert to MongoDB `property_floorplan_interactive`

---

## Immediate Fix for Test Property

Run the CORRECT pipeline manually:

```bash
cd /Users/projects/Documents/Feilds_Website/07_Valuation_Comps/Compared_to_currently_listed/backend
python -m floorplan_processing.process_floor_plan --property-id 693e8ea2ee434af1738b8f8e --force
```

This will:
1. Download the raw floor plan
2. Run OCR
3. Detect levels
4. Clean images
5. Create `level_1.webp`, `level_2.webp`
6. Create proper `interactive.json`
7. Upsert to MongoDB

---

## Verification Steps

After running the CORRECT pipeline:

1. Check files exist:
```bash
ls -la /Users/projects/Documents/Feilds_Website/files/floorplans_cache/693e8ea2ee434af1738b8f8e/
# Should see: level_1.webp, level_2.webp, interactive.json, metadata.json
```

2. Check interactive.json URLs:
```bash
grep processed_image_url /Users/projects/Documents/Feilds_Website/files/floorplans_cache/693e8ea2ee434af1738b8f8e/interactive.json
# Should see: level_1.webp, level_2.webp
```

3. Check MongoDB:
```bash
mongosh --eval "db.property_floorplan_interactive.findOne({property_id: ObjectId('693e8ea2ee434af1738b8f8e')})" property_data
```

4. Test frontend:
```
http://localhost:5173/property/693e8ea2ee434af1738b8f8e
```

---

## Long-Term Recommendation

1. **Deprecate** the `10_Floor_Plans/background_processor/` pipeline
2. **Create batch script** for `07_Valuation_Comps` pipeline
3. **Update orchestrator** to use the correct pipeline
4. **Reprocess all properties** with the correct pipeline
