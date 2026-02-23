# Floor Plans V2 System Integration Plan
**Last Updated:** 27/01/2026, 2:25 PM (Monday) - Brisbane Time

---

## Executive Summary

This document outlines the plan to integrate the **Floor Plans V2 System** (Port 8000) into the Fields Orchestrator's automated nightly pipeline. The Floor Plans V2 System processes raw floor plan images and matches rooms to property photos, creating interactive floor plans for the website.

### Current State
- ❌ Floor Plans V2 processing is **completely manual** (property-by-property)
- ❌ No automated batch processing in the orchestrator
- ✅ Individual scripts work correctly but require manual execution
- ✅ API server (Port 8000) serves processed data to frontend

### Goal
Integrate automated batch processing of floor plans into the orchestrator's nightly pipeline, running after property scraping and photo analysis.

---

## System Overview

### Floor Plans V2 Pipeline (2 Phases)

```
┌─────────────────────────────────────────────────────────────────────────┐
│                         MONGODB DATABASE                                 │
│                   mongodb://127.0.0.1:27017/property_data               │
├─────────────────────────────────────────────────────────────────────────┤
│ Collection: properties_for_sale                                          │
│   - floor_plans[] (URLs to raw floor plan images)                       │
│   - image_analysis[] (photo descriptions from GPT)                      │
│   - floor_plan_analysis.rooms[] (room data + matched photos)            │
│   - room_photo_matching_completed_at (timestamp)                        │
└─────────────────────────────────────────────────────────────────────────┘
                                    │
                    ┌───────────────┴───────────────┐
                    ▼                               ▼
┌─────────────────────────────────┐   ┌─────────────────────────────────┐
│   PHASE 1: FLOOR PLAN           │   │   PHASE 2: ROOM-TO-PHOTO        │
│   PROCESSING                    │   │   MATCHING                      │
├─────────────────────────────────┤   ├─────────────────────────────────┤
│ Script:                         │   │ Script:                         │
│ batch_llm_matcher.py            │   │ match_floor_plan_rooms_to_      │
│                                 │   │ photos.py (needs modification)  │
│ What it does:                   │   │                                 │
│ - Finds properties with         │   │ What it does:                   │
│   floor_plans[] but no          │   │ - Uses OpenAI gpt-5-nano        │
│   processed output              │   │ - Analyzes floor plan rooms     │
│ - Runs Google Vision OCR        │   │ - Matches to property photos    │
│ - Extracts room annotations     │   │ - 86% match accuracy            │
│ - Wipes text from images        │   │ - Stores in MongoDB             │
│ - Saves to processed_floor_     │   │                                 │
│   plans/property_{id}/          │   │ Updates:                        │
│                                 │   │ floor_plan_analysis.rooms[]     │
│ Uses:                           │   │   .matched_photo_index          │
│ - Ollama (gpt-oss:20b)          │   │   .match_confidence             │
│ - Google Vision API             │   │   .match_reasoning              │
└─────────────────────────────────┘   └─────────────────────────────────┘
                    │                               │
                    └───────────────┬───────────────┘
                                    ▼
                    ┌─────────────────────────────────┐
                    │   FRONTEND WEBSITE (Port 5173)  │
                    │   Displays interactive floor    │
                    │   plans with matched photos     │
                    └─────────────────────────────────┘
```

---

## Integration Strategy

### Option A: Two Separate Processes (RECOMMENDED)

Add two new processes to the orchestrator pipeline:

**Process 9: Floor Plan V2 Processing (Batch)**
- Runs after "Floor Plan Enrichment (For Sale)" (Process ID 5)
- Processes all properties with floor plans
- Creates text-wiped floor plan images with room annotations

**Process 10: Room-to-Photo Matching (Batch)**
- Runs after "Floor Plan V2 Processing" (Process ID 9)
- Matches floor plan rooms to property photos
- Updates MongoDB with match results

**Advantages:**
- ✅ Clear separation of concerns
- ✅ Can retry each phase independently
- ✅ Better progress tracking
- ✅ Easier to debug failures
- ✅ Matches orchestrator's existing pattern

**Disadvantages:**
- ⚠️ Requires two separate cooldown periods
- ⚠️ Slightly longer total pipeline time

### Option B: Single Combined Process

Create a wrapper script that runs both phases sequentially.

**Advantages:**
- ✅ Single process to manage
- ✅ One cooldown period

**Disadvantages:**
- ❌ Harder to debug which phase failed
- ❌ Can't retry individual phases
- ❌ Less granular progress tracking
- ❌ Doesn't match orchestrator's design pattern

**RECOMMENDATION: Use Option A (Two Separate Processes)**

---

## Detailed Implementation Plan

### Phase 1: Prepare Scripts for Batch Processing

#### 1.1 Create Batch Floor Plan Processing Script

**Location:** `/Users/projects/Documents/Feilds_Website/10_Floor_Plans/background_processor/`

**Script:** `batch_floor_plan_processor.sh` (new wrapper script)

**Purpose:** Wrapper around `batch_llm_matcher.py` with orchestrator-friendly output

**Content:**
```bash
#!/bin/bash
# Batch Floor Plan V2 Processor
# Processes all properties with floor plans but no processed output

cd /Users/projects/Documents/Feilds_Website/10_Floor_Plans/background_processor

echo "Starting Floor Plan V2 batch processing..."
python batch_llm_matcher.py --model gpt-oss:20b --limit 999999

exit_code=$?
if [ $exit_code -eq 0 ]; then
    echo "Floor Plan V2 processing completed successfully"
else
    echo "Floor Plan V2 processing failed with exit code $exit_code"
fi

exit $exit_code
```

**Estimated Duration:** 60-90 minutes (depends on number of unprocessed properties)

#### 1.2 Modify Room-to-Photo Matching Script

**Location:** `/Users/projects/Documents/Feilds_Website/`

**Script:** `match_floor_plan_rooms_to_photos.py` (needs modification)

**Current Issue:** Hardcoded property ID

**Required Changes:**
1. Remove hardcoded property ID
2. Add command-line argument parsing
3. Add batch mode to process all properties
4. Add progress logging
5. Add error handling for individual properties

**New Command-Line Interface:**
```bash
# Process single property
python match_floor_plan_rooms_to_photos.py --property-id 693e8ea2ee434af1738b8f89

# Process all properties (batch mode)
python match_floor_plan_rooms_to_photos.py --batch --limit 999999

# Process only unmatched properties
python match_floor_plan_rooms_to_photos.py --batch --unmatched-only
```

**Estimated Duration:** 90-120 minutes (depends on number of properties)

#### 1.3 Create Wrapper Script for Room Matching

**Location:** `/Users/projects/Documents/Feilds_Website/`

**Script:** `batch_room_photo_matching.sh` (new wrapper script)

**Content:**
```bash
#!/bin/bash
# Batch Room-to-Photo Matching
# Matches floor plan rooms to property photos for all properties

cd /Users/projects/Documents/Feilds_Website

echo "Starting room-to-photo matching batch processing..."
python match_floor_plan_rooms_to_photos.py --batch --unmatched-only

exit_code=$?
if [ $exit_code -eq 0 ]; then
    echo "Room-to-photo matching completed successfully"
else
    echo "Room-to-photo matching failed with exit code $exit_code"
fi

exit $exit_code
```

---

### Phase 2: Update Orchestrator Configuration

#### 2.1 Add Processes to `config/process_commands.yaml`

Add two new processes after the existing "Floor Plan Enrichment (For Sale)" step:

```yaml
  - id: 9
    name: "Floor Plan V2 Processing (Batch)"
    description: "Processes raw floor plans with Google Vision OCR, extracts room annotations, and creates text-wiped images"
    phase: "for_sale"
    command: "./batch_floor_plan_processor.sh"
    working_dir: "/Users/projects/Documents/Feilds_Website/10_Floor_Plans/background_processor"
    mongodb_activity: "moderate_write"
    requires_browser: false
    estimated_duration_minutes: 75  # Depends on number of unprocessed properties
    cooldown_seconds: 180  # 3 minutes before room matching
    depends_on: [2, 5]  # Depends on scraping and floor plan enrichment
    
  - id: 10
    name: "Room-to-Photo Matching (Batch)"
    description: "Matches floor plan rooms to property photos using OpenAI vision model (86% accuracy)"
    phase: "for_sale"
    command: "./batch_room_photo_matching.sh"
    working_dir: "/Users/projects/Documents/Feilds_Website"
    mongodb_activity: "moderate_write"
    requires_browser: false
    estimated_duration_minutes: 100  # Depends on number of properties
    cooldown_seconds: 180  # 3 minutes before next step
    depends_on: [9]  # Depends on floor plan processing
```

#### 2.2 Update Execution Order

Change the execution order to include the new processes:

```yaml
# OLD execution order
execution_order: [1, 2, 3, 4, 5, 6, 7, 8]

# NEW execution order
execution_order: [1, 2, 3, 4, 5, 9, 10, 6, 7, 8]
```

**Rationale for Position:**
- Runs after "Floor Plan Enrichment (For Sale)" (ID 5) which extracts basic room data
- Runs before "Property Valuation Model" (ID 6) in case valuation needs floor plan data
- Keeps all for-sale processing together before switching to sold properties

#### 2.3 Update Phase Definitions

Update the `for_sale` phase to include the new steps:

```yaml
phases:
  monitoring:
    name: "Transition Monitoring"
    description: "Detect properties that have sold"
    steps: [1]
    
  for_sale:
    name: "For-Sale Properties"
    description: "Scrape and enrich currently listed properties"
    steps: [2, 3, 4, 5, 9, 10, 6]  # Added 9 and 10
    
  sold:
    name: "Sold Properties"
    description: "Scrape and enrich recently sold properties"
    steps: [7, 8]
    
  backup:
    name: "Daily Backup"
    description: "Create MongoDB backup after all processes complete"
    steps: []
```

---

### Phase 3: Update Documentation

#### 3.1 Update README.md

Add the new processes to the pipeline steps table:

```markdown
| Step | Name | Duration | Description |
|------|------|----------|-------------|
| 1 | Monitor Sold Transitions | ~40 min | Detects properties that have sold |
| 2 | Scrape For-Sale Properties | ~22 min | Scrapes Domain.com.au for current listings |
| 3 | GPT Photo Analysis | ~155 min | Analyzes property photos with GPT Vision |
| 4 | GPT Photo Reorder | ~160 min | Creates optimal photo tour sequence |
| 5 | Floor Plan Enrichment | ~30 min | Extracts room dimensions from floor plans |
| 9 | Floor Plan V2 Processing | ~75 min | Processes floor plans with OCR and text wiping |
| 10 | Room-to-Photo Matching | ~100 min | Matches floor plan rooms to photos (86% accuracy) |
| 6 | Property Valuation Model | ~45 min | Predicts property values |
| 7 | Scrape Sold Properties | ~75 min | Scrapes recently sold properties |
| 8 | Floor Plan Enrichment (Sold) | ~30 min | Floor plan analysis for sold properties |
| Backup | Daily Backup | ~10 min | MongoDB backup to 3 locations |

**Total estimated time: 5-6 hours** (increased from 2-3 hours)
```

#### 3.2 Update process_commands.yaml Header

Add update notes to the header:

```yaml
# Process Commands Configuration
# Last Updated: 27/01/2026, [TIME] PM (Monday) - Brisbane
# - Added Floor Plans V2 Processing (ID 9) and Room-to-Photo Matching (ID 10)
# - These processes create interactive floor plans for the website
# - Runs after Floor Plan Enrichment, before Property Valuation
# - Total pipeline time increased to 5-6 hours
```

---

### Phase 4: Prerequisites and Dependencies

#### 4.1 Required Services

Ensure these services are running:

1. **MongoDB** - `mongodb://127.0.0.1:27017/`
2. **Ollama** - For LLM categorization (gpt-oss:20b model)
3. **OpenAI API** - For vision matching (gpt-5-nano)
4. **Google Vision API** - For OCR processing

#### 4.2 Required API Keys

Ensure these environment variables are set:

```bash
# OpenAI API Key
export OPENAI_API_KEY="sk-..."

# Google Cloud credentials
export GOOGLE_APPLICATION_CREDENTIALS="/path/to/credentials.json"
```

#### 4.3 Ollama Model Installation

Ensure the required Ollama model is installed:

```bash
# Check if model exists
ollama list | grep gpt-oss:20b

# Install if needed
ollama pull gpt-oss:20b
```

#### 4.4 Python Dependencies

Ensure required packages are installed:

```bash
cd /Users/projects/Documents/Feilds_Website/10_Floor_Plans/background_processor
pip3 install -r requirements.txt

cd /Users/projects/Documents/Feilds_Website
pip3 install openai pymongo pillow
```

---

## Implementation Checklist

### Pre-Implementation Tasks

- [ ] **Verify Ollama is installed and running**
  ```bash
  ollama list
  ```

- [ ] **Verify gpt-oss:20b model is available**
  ```bash
  ollama pull gpt-oss:20b
  ```

- [ ] **Verify OpenAI API key is set**
  ```bash
  echo $OPENAI_API_KEY
  ```

- [ ] **Verify Google Vision API credentials**
  ```bash
  echo $GOOGLE_APPLICATION_CREDENTIALS
  ```

- [ ] **Test batch_llm_matcher.py manually**
  ```bash
  cd /Users/projects/Documents/Feilds_Website/10_Floor_Plans/background_processor && python batch_llm_matcher.py --model gpt-oss:20b --limit 5
  ```

### Implementation Tasks

- [ ] **1. Modify match_floor_plan_rooms_to_photos.py**
  - [ ] Add argparse for command-line arguments
  - [ ] Add batch mode functionality
  - [ ] Add --unmatched-only flag
  - [ ] Add progress logging
  - [ ] Add error handling for individual properties
  - [ ] Test with single property
  - [ ] Test with batch mode (5 properties)

- [ ] **2. Create batch_floor_plan_processor.sh**
  - [ ] Create wrapper script
  - [ ] Make executable (`chmod +x`)
  - [ ] Test manually

- [ ] **3. Create batch_room_photo_matching.sh**
  - [ ] Create wrapper script
  - [ ] Make executable (`chmod +x`)
  - [ ] Test manually

- [ ] **4. Update config/process_commands.yaml**
  - [ ] Add Process ID 9 (Floor Plan V2 Processing)
  - [ ] Add Process ID 10 (Room-to-Photo Matching)
  - [ ] Update execution_order
  - [ ] Update phase definitions
  - [ ] Update header comments

- [ ] **5. Update README.md**
  - [ ] Update pipeline steps table
  - [ ] Update total estimated time
  - [ ] Add new processes to documentation

- [ ] **6. Test Integration**
  - [ ] Run manual pipeline test
  - [ ] Verify processes execute in correct order
  - [ ] Verify MongoDB updates correctly
  - [ ] Check logs for errors

### Post-Implementation Tasks

- [ ] **Monitor first automated run**
  - [ ] Check orchestrator logs
  - [ ] Verify floor plans are processed
  - [ ] Verify room matching completes
  - [ ] Check MongoDB for updated data

- [ ] **Performance Tuning**
  - [ ] Adjust estimated_duration_minutes based on actual runs
  - [ ] Adjust cooldown_seconds if needed
  - [ ] Optimize batch sizes if needed

---

## Risk Assessment and Mitigation

### Risk 1: Long Processing Time
**Impact:** Pipeline takes 5-6 hours instead of 2-3 hours

**Mitigation:**
- Run pipeline earlier (7:00 PM instead of 8:30 PM)
- Process only unmatched properties (not all properties every night)
- Consider running Floor Plans V2 on a separate schedule (e.g., weekly)

### Risk 2: API Rate Limits
**Impact:** OpenAI or Google Vision API rate limits cause failures

**Mitigation:**
- Implement rate limiting in scripts
- Add retry logic with exponential backoff
- Monitor API usage and adjust batch sizes

### Risk 3: Ollama Service Not Running
**Impact:** Floor plan processing fails

**Mitigation:**
- Add Ollama health check before processing
- Auto-start Ollama if not running
- Add clear error messages in logs

### Risk 4: Hardcoded Property ID Not Removed
**Impact:** Only one property gets processed

**Mitigation:**
- Thoroughly test modified script before integration
- Add validation to ensure batch mode is working
- Monitor first few runs closely

### Risk 5: MongoDB Write Conflicts
**Impact:** Concurrent writes cause data corruption

**Mitigation:**
- Use proper MongoDB write concerns
- Add transaction support if needed
- Ensure cooldown periods are sufficient

---

## Alternative Approaches Considered

### Alternative 1: Weekly Processing Instead of Nightly

**Approach:** Run Floor Plans V2 processing once per week instead of every night

**Pros:**
- Reduces nightly pipeline time
- Reduces API costs
- Most properties don't change floor plans frequently

**Cons:**
- New properties wait up to 7 days for floor plans
- Less responsive to changes

**Decision:** Not recommended for initial implementation, but consider for optimization

### Alternative 2: Real-Time Processing

**Approach:** Process floor plans immediately when property is scraped

**Pros:**
- Immediate availability of floor plans
- No batch processing needed

**Cons:**
- Complicates scraping process
- Harder to manage API rate limits
- Doesn't fit orchestrator's batch design

**Decision:** Not recommended

### Alternative 3: Separate Orchestrator for Floor Plans

**Approach:** Create a separate orchestrator just for floor plan processing

**Pros:**
- Independent scheduling
- Can run at different times
- Easier to scale independently

**Cons:**
- More complex infrastructure
- Duplicate code
- Harder to coordinate with main pipeline

**Decision:** Not recommended for initial implementation

---

## Success Criteria

### Functional Requirements

✅ **Floor plans are processed automatically every night**
- All properties with floor_plans[] get processed
- Processed images saved to processed_floor_plans/
- Room annotations extracted and stored

✅ **Room-to-photo matching runs automatically**
- All processed floor plans get room matching
- Match results stored in MongoDB
- Confidence scores and reasoning included

✅ **Integration with existing pipeline**
- Processes run in correct order
- Dependencies respected
- Cooldown periods applied

✅ **Error handling**
- Individual property failures don't stop batch
- Errors logged clearly
- Failed properties can be retried

### Performance Requirements

✅ **Processing completes within 6 hours**
- Floor Plan V2 Processing: < 90 minutes
- Room-to-Photo Matching: < 120 minutes

✅ **Match accuracy maintained**
- 86% match rate (same as manual processing)
- Confidence scores accurate

✅ **Resource usage acceptable**
- MongoDB remains stable
- API rate limits not exceeded
- System resources not exhausted

### Monitoring Requirements

✅ **Progress tracking**
- Real-time progress in orchestrator window
- Detailed logs for debugging
- Success/failure counts

✅ **Data quality**
- Processed floor plans viewable on website
- Room matches display correctly
- No data corruption

---

## Timeline Estimate

### Phase 1: Script Preparation (4-6 hours)
- Modify match_floor_plan_rooms_to_photos.py: 2-3 hours
- Create wrapper scripts: 1 hour
- Testing: 1-2 hours

### Phase 2: Orchestrator Integration (2-3 hours)
- Update process_commands.yaml: 30 minutes
- Update README.md: 30 minutes
- Testing: 1-2 hours

### Phase 3: Validation (2-4 hours)
- Manual pipeline run: 2-3 hours
- Monitoring and adjustments: 1 hour

**Total Estimated Time: 8-13 hours**

---

## Next Steps

### Immediate Actions (Do First)

1. **Verify Prerequisites**
   - Check Ollama installation and gpt-oss:20b model
   - Verify API keys are set
   - Test batch_llm_matcher.py manually

2. **Modify match_floor_plan_rooms_to_photos.py**
   - This is the critical blocker
   - Add batch mode functionality
   - Test thoroughly before integration

3. **Create Wrapper Scripts**
   - batch_floor_plan_processor.sh
   - batch_room_photo_matching.sh
   - Test manually

### Secondary Actions (Do After Scripts Work)

4. **Update Orchestrator Configuration**
   - Add processes to process_commands.yaml
   - Update execution order
   - Update documentation

5. **Test Integration**
   - Run manual pipeline test
   - Monitor first automated run
   - Adjust timings based on actual performance

### Future Enhancements (Consider Later)

6. **Optimization**
   - Process only unmatched properties
   - Adjust scheduling if needed
   - Consider weekly processing for some steps

7. **Monitoring**
   - Add metrics tracking
   - Create dashboard for floor plan processing status
   - Add alerts for failures

---

## Questions to Resolve

### Before Implementation

1. **Should we process ALL properties every night, or only unmatched ones?**
   - Recommendation: Only unmatched to save time and API costs

2. **What should happen if floor plan processing fails for a property?**
   - Recommendation: Log error, continue with next property, retry on next run

3. **Should we run this every night or less frequently (e.g., weekly)?**
   - Recommendation: Start with nightly, optimize to weekly if needed

4. **Should the pipeline start earlier to accommodate longer runtime?**
   - Recommendation: Yes, change from 8:30 PM to 7:00 PM

5. **Do we need to process sold properties' floor plans too?**
   - Recommendation: Yes, add similar processes for sold properties (IDs 11-12)

---

## Conclusion

Integrating the Floor Plans V2 System into the orchestrator is **feasible and recommended**. The main work required is:

1. **Modifying match_floor_plan_rooms_to_photos.py** to support batch processing
2. **Creating wrapper scripts** for orchestrator integration
3. **Updating orchestrator configuration** to include the new processes

The integration will increase pipeline time from 2-3 hours to 5-6 hours, but will provide **fully automated floor plan processing** with **86% room-to-photo matching accuracy**.

**Recommended Approach:** Option A (Two Separate Processes) for better error handling and progress tracking.

**Estimated Implementation Time:** 8-13 hours

**Next Step:** Modify match_floor_plan_rooms_to_photos.py to add batch mode functionality.
