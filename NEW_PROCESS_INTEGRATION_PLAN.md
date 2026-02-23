# New Gold Coast Property Monitoring Process Integration Plan
**Created:** 04/02/2026, 7:04 am (Brisbane Time)

## 📋 Executive Summary

This document outlines the implementation plan to integrate the new Gold Coast-wide property monitoring processes into the Fields Orchestrator, replacing the current Domain scraping processes while preserving essential backend enrichment and valuation processes.

---

## 🔍 Analysis: Current vs New Processes

### **Current Orchestrator Processes (16 total)**

#### **PHASE 1: MONITORING (Process 1)**
- ❌ **REPLACE** - Process 1: Monitor For-Sale → Sold Transitions
  - Old: `/Users/projects/Documents/Property_Data_Scraping/02_Domain_Scaping/For_Sale_To_Sold_Transition`
  - New: `/Users/projects/Documents/Property_Data_Scraping/03_Gold_Coast/Gold_Coast_Wide_Currently_For_Sale_AND_Recently_Sold/monitor_sold_properties.py`
  - **Reason:** New version is 10x faster with ChromeDriver optimization

#### **PHASE 2: FOR-SALE PROPERTIES (Processes 2-6)**
- ❌ **REPLACE** - Process 2: Scrape For-Sale Properties
  - Old: `/Users/projects/Documents/Property_Data_Scraping/07_Undetectable_method/Simple_Method`
  - New: `/Users/projects/Documents/Property_Data_Scraping/03_Gold_Coast/Gold_Coast_Wide_Currently_For_Sale_AND_Recently_Sold/headless_forsale_mongodb_scraper.py`
  
- ❌ **REPLACE** - Process 3: GPT Photo Analysis
  - Old: `/Users/projects/Documents/Property_Data_Scraping/01_House_Plan_Data/src/main_parallel.py`
  - New: `/Users/projects/Documents/Property_Data_Scraping/03_Gold_Coast/Gold_Coast_Wide_Currently_For_Sale_AND_Recently_Sold/Ollama_Property_Analysis/ollama_photo_reorder.py`
  
- ❌ **REPLACE** - Process 4: GPT Photo Reorder
  - Old: `/Users/projects/Documents/Property_Data_Scraping/01_House_Plan_Data/src/photo_reorder_parallel.py`
  - New: Integrated into Process 3 replacement (Ollama does both analysis and reordering)
  
- ❌ **REPLACE** - Process 5: Floor Plan Enrichment (For Sale)
  - Old: `/Users/projects/Documents/Property_Data_Scraping/01.1_Floor_Plan_Data/run_production.py`
  - New: `/Users/projects/Documents/Property_Data_Scraping/03_Gold_Coast/Gold_Coast_Wide_Currently_For_Sale_AND_Recently_Sold/Ollama_Property_Analysis/ollama_floor_plan_analysis.py`
  
- ✅ **KEEP** - Process 6: Property Valuation Model
  - Location: `/Users/projects/Documents/Property_Valuation/04_Production_Valuation/batch_valuate_with_tracking.py`
  - **Status:** No changes needed

#### **PHASE 3: BACKEND ENRICHMENT (Processes 11-16)**
- ✅ **KEEP ALL** - Processes 11-16: Backend Data Enrichment
  - Process 11: Parse Room Dimensions
  - Process 12: Enrich Property Timeline
  - Process 13: Generate Suburb Median Prices
  - Process 14: Generate Suburb Statistics
  - Process 15: Calculate Property Insights
  - Process 16: Enrich Properties For Sale
  - **Status:** No changes needed - these work with any data source

#### **PHASE 4: SOLD PROPERTIES (Processes 7-8)**
- ❌ **REPLACE** - Process 7: Scrape Sold Properties
  - Old: `/Users/projects/Documents/Property_Data_Scraping/02_Domain_Scaping/Sold_In_Last_6_Months`
  - New: Handled by new monitor_sold_properties.py (moves sold properties automatically)
  
- ❌ **REPLACE** - Process 8: Floor Plan Enrichment (Sold)
  - Old: `/Users/projects/Documents/Property_Data_Scraping/01.1_Floor_Plan_Data/run_production_sold.py`
  - New: Not needed - floor plans analyzed before property sells

---

## 🎯 New Process Architecture

### **Key Differences in New System**

1. **Database Structure Change:**
   - Old: Single `property_data` database with `for_sale` and `sold` collections
   - New: `Gold_Coast_Currently_For_Sale` database with 52 suburb collections + `Gold_Coast_Recently_Sold` collection

2. **Monitoring Approach:**
   - Old: Separate scraping for for-sale and sold properties
   - New: Scrape for-sale, then monitor for transitions to sold status

3. **Target Market Focus:**
   - Old: All properties treated equally
   - New: 8 target market suburbs (nightly) + 44 other suburbs (weekly)

4. **Visual Analysis:**
   - Old: GPT-4 Vision API (expensive, token limits)
   - New: Ollama LLaVA (local, free, no limits)

5. **Performance:**
   - Old: ~1 property/minute for sold monitoring
   - New: ~10 properties/minute (10x faster with ChromeDriver optimization)

---

## 📅 Implementation Strategy

### **Phase 1: Preparation & Archival (Day 1)**

#### 1.1 Archive Old Processes
Create archive directory and move old process scripts:

```bash
# Create archive directory
mkdir -p /Users/projects/Documents/Property_Data_Scraping/00_ARCHIVED_PROCESSES_2026_02_04

# Archive old for-sale scraper
mv /Users/projects/Documents/Property_Data_Scraping/07_Undetectable_method \
   /Users/projects/Documents/Property_Data_Scraping/00_ARCHIVED_PROCESSES_2026_02_04/

# Archive old GPT photo analysis
cp -r /Users/projects/Documents/Property_Data_Scraping/01_House_Plan_Data \
   /Users/projects/Documents/Property_Data_Scraping/00_ARCHIVED_PROCESSES_2026_02_04/

# Archive old floor plan enrichment
cp -r /Users/projects/Documents/Property_Data_Scraping/01.1_Floor_Plan_Data \
   /Users/projects/Documents/Property_Data_Scraping/00_ARCHIVED_PROCESSES_2026_02_04/

# Archive old sold scraper
mv /Users/projects/Documents/Property_Data_Scraping/02_Domain_Scaping/Sold_In_Last_6_Months \
   /Users/projects/Documents/Property_Data_Scraping/00_ARCHIVED_PROCESSES_2026_02_04/

# Archive old sold monitor
mv /Users/projects/Documents/Property_Data_Scraping/02_Domain_Scaping/For_Sale_To_Sold_Transition \
   /Users/projects/Documents/Property_Data_Scraping/00_ARCHIVED_PROCESSES_2026_02_04/
```

#### 1.2 Create Archive Documentation
Document what was archived and why:

```markdown
# ARCHIVED_PROCESSES_README.md
Archived on: 04/02/2026
Reason: Replaced by Gold Coast-wide monitoring system

## Archived Processes:
1. 07_Undetectable_method - Old for-sale scraper
2. 01_House_Plan_Data - Old GPT photo analysis
3. 01.1_Floor_Plan_Data - Old floor plan enrichment
4. Sold_In_Last_6_Months - Old sold scraper
5. For_Sale_To_Sold_Transition - Old sold monitor

## Replacement System:
Location: /Users/projects/Documents/Property_Data_Scraping/03_Gold_Coast/Gold_Coast_Wide_Currently_For_Sale_AND_Recently_Sold/
Documentation: END_TO_END_PROPERTY_MONITORING_PROCESS.md
```

---

### **Phase 2: Create New Process Definitions (Day 1)**

#### 2.1 New Process IDs and Structure

**NEW PROCESS MAPPING:**

| New ID | Name | Replaces Old | Phase | Target Market | Other Suburbs |
|--------|------|--------------|-------|---------------|---------------|
| 101 | Scrape For-Sale (Target Market) | Process 2 | for_sale_target | Nightly | - |
| 102 | Scrape For-Sale (Other Suburbs) | Process 2 | for_sale_other | - | Weekly (Sunday) |
| 103 | Monitor Sold (Target Market) | Process 1, 7 | monitoring_target | Nightly | - |
| 104 | Monitor Sold (Other Suburbs) | Process 1, 7 | monitoring_other | - | Weekly (Sunday) |
| 105 | Photo Analysis (Target Market) | Process 3, 4 | enrichment_target | Nightly | - |
| 106 | Floor Plan Analysis (Target Market) | Process 5 | enrichment_target | Nightly | - |
| 6 | Property Valuation Model | Process 6 | valuation | ✅ KEEP | ✅ KEEP |
| 11-16 | Backend Enrichment (6 processes) | Processes 11-16 | backend_enrichment | ✅ KEEP | ✅ KEEP |

**REMOVED PROCESSES:**
- ❌ Process 7: Scrape Sold Properties (replaced by monitor_sold_properties.py)
- ❌ Process 8: Floor Plan Enrichment (Sold) (not needed - analyzed before sale)

---

### **Phase 3: Update Configuration Files (Day 1-2)**

#### 3.1 Create New process_commands.yaml

Key changes:
1. Add new processes 101-106 for Gold Coast monitoring
2. Keep processes 6, 11-16 unchanged
3. Remove processes 1, 2, 3, 4, 5, 7, 8
4. Add schedule differentiation (nightly vs weekly)
5. Update execution order

#### 3.2 Update settings.yaml

Add new configuration sections:
```yaml
schedule:
  # Existing settings...
  target_market_schedule: "02:00"  # 2:00 AM for target market
  other_suburbs_schedule: "01:00"  # 1:00 AM Sunday for other suburbs
  run_target_market_daily: true
  run_other_suburbs_weekly: true
  other_suburbs_day: "Sunday"  # 0 = Sunday

target_market:
  suburbs:
    - "Robina:4226"
    - "Mudgeeraba:4213"
    - "Varsity Lakes:4227"
    - "Reedy Creek:4227"
    - "Burleigh Waters:4220"
    - "Merrimac:4226"
    - "Worongary:4213"
    - "Carrara:4211"
  
mongodb:
  # Existing settings...
  # Add new database references
  gold_coast_database: "Gold_Coast_Currently_For_Sale"
  gold_coast_master_database: "Gold_Coast"
  sold_collection: "Gold_Coast_Recently_Sold"
```

---

### **Phase 4: Create Wrapper Scripts (Day 2)**

#### 4.1 Target Market Nightly Scripts

**Script: `scripts/run_target_market_nightly.sh`**
```bash
#!/bin/bash
# Target Market Nightly Pipeline
# Runs: Scrape → Monitor Sold → Photo Analysis → Floor Plan Analysis

BASE_DIR="/Users/projects/Documents/Property_Data_Scraping/03_Gold_Coast/Gold_Coast_Wide_Currently_For_Sale_AND_Recently_Sold"
OLLAMA_DIR="$BASE_DIR/Ollama_Property_Analysis"

TARGET_SUBURBS="Robina:4226 Mudgeeraba:4213 Varsity Lakes:4227 Reedy Creek:4227 Burleigh Waters:4220 Merrimac:4226 Worongary:4213 Carrara:4211"

echo "=== Target Market Nightly Pipeline Started ==="
echo "Date: $(date)"

# Step 1: Scrape for-sale properties (Target Market only)
echo "Step 1: Scraping target market suburbs..."
cd "$BASE_DIR" && python3 run_dynamic_10_suburbs.py --suburbs $TARGET_SUBURBS

# Step 2: Monitor for sold properties
echo "Step 2: Monitoring for sold properties..."
cd "$BASE_DIR" && python3 monitor_sold_properties.py \
  --suburbs $TARGET_SUBURBS \
  --max-concurrent 5

# Step 3: Photo analysis
echo "Step 3: Running photo analysis..."
cd "$OLLAMA_DIR"
for suburb in robina mudgeeraba varsity_lakes reedy_creek burleigh_waters merrimac worongary carrara; do
  echo "  Analyzing photos for $suburb..."
  python3 run_production.py --collection "$suburb" --workers 4
done

# Step 4: Floor plan analysis
echo "Step 4: Running floor plan analysis..."
for suburb in robina mudgeeraba varsity_lakes reedy_creek burleigh_waters merrimac worongary carrara; do
  echo "  Analyzing floor plans for $suburb..."
  python3 ollama_floor_plan_analysis.py --collection "$suburb" --workers 4
done

echo "=== Target Market Nightly Pipeline Completed ==="
echo "Date: $(date)"
```

#### 4.2 Other Suburbs Weekly Script

**Script: `scripts/run_other_suburbs_weekly.sh`**
```bash
#!/bin/bash
# Other Suburbs Weekly Pipeline (Sunday)
# Runs: Scrape All → Monitor Sold All

BASE_DIR="/Users/projects/Documents/Property_Data_Scraping/03_Gold_Coast/Gold_Coast_Wide_Currently_For_Sale_AND_Recently_Sold"

echo "=== Other Suburbs Weekly Pipeline Started ==="
echo "Date: $(date)"

# Step 1: Scrape all 52 suburbs
echo "Step 1: Scraping all Gold Coast suburbs..."
cd "$BASE_DIR" && python3 run_dynamic_10_suburbs.py

# Step 2: Monitor all suburbs for sold properties
echo "Step 2: Monitoring all suburbs for sold properties..."
cd "$BASE_DIR" && python3 monitor_sold_properties.py --all --max-concurrent 5

echo "=== Other Suburbs Weekly Pipeline Completed ==="
echo "Date: $(date)"
```

---

### **Phase 5: Update Orchestrator Code (Day 2-3)**

#### 5.1 Modify task_executor.py

Add support for:
1. Schedule-based process execution (nightly vs weekly)
2. Day-of-week checking for weekly processes
3. Target market vs other suburbs differentiation

#### 5.2 Create new module: schedule_manager.py

```python
"""
Schedule Manager for Gold Coast Property Monitoring
Determines which processes should run based on day/time
"""

from datetime import datetime
from typing import List, Dict

class ScheduleManager:
    def __init__(self, config: Dict):
        self.config = config
        
    def should_run_target_market(self) -> bool:
        """Target market runs daily"""
        return True
        
    def should_run_other_suburbs(self) -> bool:
        """Other suburbs run weekly on Sunday"""
        today = datetime.now().strftime('%A')
        return today == 'Sunday'
        
    def get_processes_to_run(self) -> List[int]:
        """Returns list of process IDs to run based on schedule"""
        processes = []
        
        if self.should_run_target_market():
            processes.extend([101, 103, 105, 106])  # Target market pipeline
            
        if self.should_run_other_suburbs():
            processes.extend([102, 104])  # Other suburbs pipeline
            
        # Always run valuation and backend enrichment
        processes.extend([6, 11, 12, 13, 14, 16, 15])
        
        return processes
```

---

### **Phase 6: New Sequential Ordering (Day 3)**

#### 6.1 Nightly Execution Order (Monday-Saturday)

**Target Market Only:**
```
1. Process 101: Scrape For-Sale (Target Market) - 30 min
2. Process 103: Monitor Sold (Target Market) - 45 min
3. Process 105: Photo Analysis (Target Market) - 120 min
4. Process 106: Floor Plan Analysis (Target Market) - 60 min
5. Process 6: Property Valuation Model - 45 min
6. Process 11: Parse Room Dimensions - 15 min
7. Process 12: Enrich Property Timeline - 20 min
8. Process 13: Generate Suburb Median Prices - 25 min
9. Process 14: Generate Suburb Statistics - 30 min
10. Process 16: Enrich Properties For Sale - 15 min
11. Process 15: Calculate Property Insights - 20 min
12. Backup - 30 min

Total: ~6.5 hours
```

#### 6.2 Weekly Execution Order (Sunday)

**All Suburbs:**
```
1. Process 102: Scrape For-Sale (All Suburbs) - 180 min
2. Process 104: Monitor Sold (All Suburbs) - 240 min
3. Process 101: Scrape For-Sale (Target Market) - 30 min
4. Process 103: Monitor Sold (Target Market) - 45 min
5. Process 105: Photo Analysis (Target Market) - 120 min
6. Process 106: Floor Plan Analysis (Target Market) - 60 min
7. Process 6: Property Valuation Model - 45 min
8. Process 11: Parse Room Dimensions - 15 min
9. Process 12: Enrich Property Timeline - 20 min
10. Process 13: Generate Suburb Median Prices - 25 min
11. Process 14: Generate Suburb Statistics - 30 min
12. Process 16: Enrich Properties For Sale - 15 min
13. Process 15: Calculate Property Insights - 20 min
14. Backup - 30 min

Total: ~14.5 hours
```

---

## 🗄️ Database Migration Strategy

### **Option 1: Parallel Databases (RECOMMENDED)**

**Approach:** Keep both old and new databases running in parallel for 2 weeks

**Advantages:**
- Zero downtime
- Easy rollback if issues arise
- Can compare data quality
- Frontend can gradually switch over

**Implementation:**
```bash
# Week 1: Run both systems
# - Old orchestrator continues as normal
# - New processes run separately (manual or cron)
# - Compare data quality and completeness

# Week 2: Switch frontend to new database
# - Update API endpoints to read from Gold_Coast_Currently_For_Sale
# - Monitor for issues
# - Keep old system as backup

# Week 3: Decommission old system
# - Archive old database
# - Remove old processes from orchestrator
# - Full cutover to new system
```

### **Option 2: Direct Migration (FASTER)**

**Approach:** Migrate existing data and switch immediately

**Advantages:**
- Faster implementation
- Single source of truth
- No duplicate processing

**Risks:**
- Requires downtime
- No easy rollback
- Must be confident in new system

---

## 🔧 Testing Strategy

### **Phase 1: Unit Testing (Day 3-4)**

Test each new process individually:

```bash
# Test target market scraping (10 properties)
cd /Users/projects/Documents/Property_Data_Scraping/03_Gold_Coast/Gold_Coast_Wide_Currently_For_Sale_AND_Recently_Sold && \
python3 monitor_sold_properties.py --suburbs "Robina:4226" --test

# Test photo analysis (single suburb)
cd /Users/projects/Documents/Property_Data_Scraping/03_Gold_Coast/Gold_Coast_Wide_Currently_For_Sale_AND_Recently_Sold/Ollama_Property_Analysis && \
python3 run_production.py --collection robina --workers 2 --limit 5

# Test floor plan analysis (single suburb)
python3 ollama_floor_plan_analysis.py --collection robina --workers 2 --limit 5
```

### **Phase 2: Integration Testing (Day 4-5)**

Test full pipeline with target market:

```bash
# Run complete target market pipeline
cd /Users/projects/Documents/Fields_Orchestrator && \
./scripts/run_target_market_nightly.sh
```

### **Phase 3: Production Testing (Week 1)**

Run new system in parallel with old system:
- Compare property counts
- Compare data quality
- Monitor performance
- Check for missing data

---

## 📊 Success Metrics

### **Data Quality Indicators**
- ✅ All target market properties have `image_analysis`
- ✅ All target market properties with floor plans have `floor_plan_analysis`
- ✅ Sold properties detected within 24 hours
- ✅ Zero data loss during migration
- ✅ All 52 suburbs represented in database

### **Performance Indicators**
- ✅ Target market pipeline completes in < 7 hours
- ✅ Weekly full pipeline completes in < 15 hours
- ✅ 10x faster sold monitoring (vs old system)
- ✅ Zero cost for visual analysis (Ollama vs GPT-4)

### **System Health Indicators**
- ✅ Zero failed processes
- ✅ MongoDB stability maintained
- ✅ Backup system continues working
- ✅ Frontend displays data correctly

---

## 🚨 Rollback Plan

If issues arise, rollback procedure:

1. **Stop new orchestrator:**
   ```bash
   cd /Users/projects/Documents/Fields_Orchestrator && ./scripts/stop_orchestrator.sh
   ```

2. **Restore old process_commands.yaml:**
   ```bash
   cp config/process_commands.yaml.backup config/process_commands.yaml
   ```

3. **Restart old orchestrator:**
   ```bash
   ./scripts/start_orchestrator.sh
   ```

4. **Switch frontend back to old database:**
   - Update API endpoints
   - Clear cache
   - Verify data display

---

## 📁 File Changes Summary

### **New Files to Create:**
```
/Users/projects/Documents/Fields_Orchestrator/
├── config/
│   ├── process_commands.yaml.backup (backup of old config)
│   └── process_commands_new.yaml (new config)
├── scripts/
│   ├── run_target_market_nightly.sh (new)
│   ├── run_other_suburbs_weekly.sh (new)
│   └── migrate_to_new_system.sh (new)
├── src/
│   └── schedule_manager.py (new)
└── NEW_PROCESS_INTEGRATION_PLAN.md (this document)
```

### **Files to Modify:**
```
/Users/projects/Documents/Fields_Orchestrator/
├── config/
│   ├── process_commands.yaml (major changes)
│   └── settings.yaml (add target market config)
├── src/
│   ├── task_executor.py (add schedule support)
│   └── orchestrator_daemon.py (integrate schedule_manager)
└── README.md (update documentation)
```

### **Files to Archive:**
```
/Users/projects/Documents/Property_Data_Scraping/
└── 00_ARCHIVED_PROCESSES_2026_02_04/
    ├── 07_Undetectable_method/
    ├── 01_House_Plan_Data/
    ├── 01.1_Floor_Plan_Data/
    ├── Sold_In_Last_6_Months/
    ├── For_Sale_To_Sold_Transition/
    └── ARCHIVED_PROCESSES_README.md
```

---

## 🎯 Implementation Timeline

### **Week 1: Preparation & Testing**
- **Day 1:** Archive old processes, create documentation
- **Day 2:** Create wrapper scripts, update configuration files
- **Day 3:** Modify orchestrator code, add schedule manager
- **Day 4:** Unit testing of individual processes
- **Day 5:** Integration testing of full pipeline
- **Weekend:** Run parallel systems, compare results

### **Week 2: Parallel Operation**
- **Monday-Friday:** Both systems running, monitor data quality
- **Weekend:** Analyze results, prepare for cutover

### **Week 3: Cutover**
- **Monday:** Switch frontend to new database
- **Tuesday-Thursday:** Monitor for issues, fix bugs
- **Friday:** Decommission old system if stable
- **Weekend:** Final verification

---

## ✅ Pre-Implementation Checklist

Before starting implementation:

- [ ] Backup current orchestrator configuration
- [ ] Backup current MongoDB databases
- [ ] Verify Ollama is installed and running
- [ ] Test new scripts manually (target market only)
- [ ] Verify ChromeDriver is installed
- [ ] Check disk space for new database structure
- [ ] Document current system performance baseline
- [ ] Create rollback procedure document
- [ ] Notify stakeholders of upcoming changes
- [ ] Schedule maintenance window if needed

---

## 📞 Support & Troubleshooting

### **Common Issues**

**Issue:** New processes not appearing in orchestrator  
**Solution:** Check process_commands.yaml syntax, restart orchestrator

**Issue:** Schedule not working correctly  
**Solution:** Verify schedule_manager.py logic, check system time/timezone

**Issue:** Database connection errors  
**Solution:** Verify MongoDB is running, check connection strings in settings.yaml

**Issue:** Ollama analysis fails  
**Solution:** Check Ollama is running: `ollama list`, verify model is downloaded

**Issue:** Performance degradation  
**Solution:** Check MongoDB indexes, verify cooldown periods are sufficient

---

## 🎉 Expected Benefits

### **Cost Savings**
- **GPT-4 Vision API:** $0 (was ~$500/month)
- **Faster processing:** 10x improvement in sold monitoring
- **Reduced complexity:** Fewer moving parts

### **Data Quality Improvements**
- **Comprehensive coverage:** All 52 Gold Coast suburbs
- **Target market focus:** Nightly updates for key suburbs
- **Better change tracking:** History arrays for all fields
- **Richer analysis:** Floor plan dimensions, room details

### **Operational Improvements**
- **Automated sold detection:** No separate sold scraper needed
- **Master database:** Permanent sales history tracking
- **Scalable architecture:** Easy to add more suburbs
- **Better monitoring:** Clear separation of target vs other suburbs

---

## 📚 Related Documentation

- **New System:** `/Users/projects/Documents/Property_Data_Scraping/03_Gold_Coast/Gold_Coast_Wide_Currently_For_Sale_AND_Recently_Sold/END_TO_END_PROPERTY_MONITORING_PROCESS.md`
- **Photo Analysis:** `/Users/projects/Documents/Property_Data_Scraping/03_Gold_Coast/Gold_Coast_Wide_Currently_For_Sale_AND_Recently_Sold/Ollama_Property_Analysis/PHOTO_REORDER_README.md`
- **Floor Plan Analysis:** `/Users/projects/Documents/Property_Data_Scraping/03_Gold_Coast/Gold_Coast_Wide_Currently_For_Sale_AND_Recently_Sold/Ollama_Property_Analysis/FLOOR_PLAN_ANALYSIS_README.md`
- **Performance Fix:** `/Users/projects/Documents/Property_Data_Scraping/03_Gold_Coast/Gold_Coast_Wide_Currently_For_Sale_AND_Recently_Sold/CHROMEDRIVER_PERFORMANCE_FIX.md`
- **Target Market:** `/Users/projects/Documents/Feilds_Website/02_Target_Market/BUSINESS_SUMMARY.md`

---

## 🏁 Conclusion

This implementation plan provides a comprehensive roadmap for integrating the new Gold Coast property monitoring system into the Fields Orchestrator. The phased approach with parallel operation minimizes risk while the clear rollback plan ensures business continuity.

**Key Takeaways:**
1. **Replace:** Processes 1-5, 7-8 (scraping and visual analysis)
2. **Keep:** Processes 6, 11-16 (valuation and backend enrichment)
3. **Add:** Target market differentiation (nightly vs weekly)
4. **Improve:** 10x faster, $0 cost, better data quality

**Next Steps:**
1. Review and approve this plan
2. Begin Phase 1: Preparation & Archival
3. Create wrapper scripts and test individually
4. Run parallel systems for 2 weeks
5. Complete cutover and decommission old system
