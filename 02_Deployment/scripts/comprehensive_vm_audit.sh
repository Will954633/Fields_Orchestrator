#!/bin/bash
# Comprehensive VM Deployment Audit
# Last Edit: 13/02/2026, 8:10 AM (Friday) — Brisbane Time
#
# Description: Checks ALL files used by the orchestrator to find deployment gaps

set -e

echo "============================================================"
echo "COMPREHENSIVE VM DEPLOYMENT AUDIT"
echo "============================================================"
echo ""

# Arrays to track results
declare -a OUTDATED_FILES
declare -a UP_TO_DATE_FILES
declare -a MISSING_LOCAL
declare -a MISSING_VM

# Function to check a file
check_file() {
    local LOCAL_BASE="$1"
    local VM_BASE="$2"
    local FILE_PATH="$3"
    
    LOCAL_FULL="$LOCAL_BASE/$FILE_PATH"
    VM_FULL="$VM_BASE/$FILE_PATH"
    
    # Get local mod time
    if [ -f "$LOCAL_FULL" ]; then
        LOCAL_TIME=$(stat -f "%Sm" -t "%Y-%m-%d %H:%M:%S" "$LOCAL_FULL" 2>/dev/null)
        LOCAL_SIZE=$(stat -f "%z" "$LOCAL_FULL" 2>/dev/null)
    else
        MISSING_LOCAL+=("$FILE_PATH")
        return
    fi
    
    # Get VM mod time
    VM_RESULT=$(gcloud compute ssh fields-orchestrator-vm \
        --zone=australia-southeast1-b \
        --project=fields-estate \
        --command="stat -c '%y %s' '$VM_FULL' 2>/dev/null || echo 'MISSING'" | head -1)
    
    if [ "$VM_RESULT" = "MISSING" ]; then
        MISSING_VM+=("$FILE_PATH")
        return
    fi
    
    VM_TIME=$(echo "$VM_RESULT" | cut -d'.' -f1)
    VM_SIZE=$(echo "$VM_RESULT" | awk '{print $NF}')
    
    # Compare
    if [[ "$VM_TIME" > "$LOCAL_TIME" ]] || [[ "$VM_TIME" == "$LOCAL_TIME"* ]]; then
        UP_TO_DATE_FILES+=("$FILE_PATH")
    else
        OUTDATED_FILES+=("$FILE_PATH|$LOCAL_TIME|$VM_TIME|$LOCAL_SIZE|$VM_SIZE")
    fi
}

echo "Scanning orchestrator files..."
echo ""

# ORCHESTRATOR CORE
echo "=== ORCHESTRATOR CORE ==="
check_file "/Users/projects/Documents/Fields_Orchestrator" "/home/fields/Fields_Orchestrator" "src/orchestrator_daemon.py"
check_file "/Users/projects/Documents/Fields_Orchestrator" "/home/fields/Fields_Orchestrator" "src/task_executor.py"
check_file "/Users/projects/Documents/Fields_Orchestrator" "/home/fields/Fields_Orchestrator" "src/schedule_manager.py"
check_file "/Users/projects/Documents/Fields_Orchestrator" "/home/fields/Fields_Orchestrator" "src/backup_coordinator.py"
check_file "/Users/projects/Documents/Fields_Orchestrator" "/home/fields/Fields_Orchestrator" "src/mongodb_monitor.py"
check_file "/Users/projects/Documents/Fields_Orchestrator" "/home/fields/Fields_Orchestrator" "config/process_commands.yaml"
check_file "/Users/projects/Documents/Fields_Orchestrator" "/home/fields/Fields_Orchestrator" "config/settings.yaml"
echo ""

# PROPERTY DATA SCRAPING
echo "=== PROPERTY DATA SCRAPING ==="
check_file "/Users/projects/Documents/Property_Data_Scraping" "/home/fields/Property_Data_Scraping" "03_Gold_Coast/Gold_Coast_Wide_Currently_For_Sale_AND_Recently_Sold/run_dynamic_10_suburbs.py"
check_file "/Users/projects/Documents/Property_Data_Scraping" "/home/fields/Property_Data_Scraping" "03_Gold_Coast/Gold_Coast_Wide_Currently_For_Sale_AND_Recently_Sold/monitor_sold_properties.py"
check_file "/Users/projects/Documents/Property_Data_Scraping" "/home/fields/Property_Data_Scraping" "03_Gold_Coast/Gold_Coast_Wide_Currently_For_Sale_AND_Recently_Sold/run_parallel_suburb_scrape.py"
echo ""

# OLLAMA ANALYSIS
echo "=== OLLAMA ANALYSIS ==="
check_file "/Users/projects/Documents/Property_Data_Scraping" "/home/fields/Property_Data_Scraping" "03_Gold_Coast/Gold_Coast_Wide_Currently_For_Sale_AND_Recently_Sold/Ollama_Property_Analysis/run_target_market_photo_analysis.sh"
check_file "/Users/projects/Documents/Property_Data_Scraping" "/home/fields/Property_Data_Scraping" "03_Gold_Coast/Gold_Coast_Wide_Currently_For_Sale_AND_Recently_Sold/Ollama_Property_Analysis/run_target_market_floor_plan_analysis.sh"
check_file "/Users/projects/Documents/Property_Data_Scraping" "/home/fields/Property_Data_Scraping" "03_Gold_Coast/Gold_Coast_Wide_Currently_For_Sale_AND_Recently_Sold/Ollama_Property_Analysis/ollama_photo_client.py"
check_file "/Users/projects/Documents/Property_Data_Scraping" "/home/fields/Property_Data_Scraping" "03_Gold_Coast/Gold_Coast_Wide_Currently_For_Sale_AND_Recently_Sold/Ollama_Property_Analysis/ollama_floorplan_client.py"
echo ""

# PROPERTY VALUATION
echo "=== PROPERTY VALUATION ==="
check_file "/Users/projects/Documents/Property_Valuation" "/home/fields/Property_Valuation" "04_Production_Valuation/batch_valuate_with_tracking.py"
check_file "/Users/projects/Documents/Property_Valuation" "/home/fields/Property_Valuation" "04_Production_Valuation/feature_calculator_v2.py"
check_file "/Users/projects/Documents/Property_Valuation" "/home/fields/Property_Valuation" "04_Production_Valuation/additional_feature_engines.py"
echo ""

# WEBSITE BACKEND
echo "=== WEBSITE BACKEND ==="
check_file "/Users/projects/Documents/Feilds_Website" "/home/fields/Feilds_Website" "10_Floor_Plans/parse_room_dimensions.py"
check_file "/Users/projects/Documents/Feilds_Website" "/home/fields/Feilds_Website" "03_For_Sale_Coverage/enrich_property_timeline.py"
check_file "/Users/projects/Documents/Feilds_Website" "/home/fields/Feilds_Website" "08_Market_Narrative_Engine/generate_suburb_medians.py"
check_file "/Users/projects/Documents/Feilds_Website" "/home/fields/Feilds_Website" "03_For_Sale_Coverage/generate_suburb_statistics.py"
check_file "/Users/projects/Documents/Feilds_Website" "/home/fields/Feilds_Website" "03_For_Sale_Coverage/calculate_property_insights.py"
check_file "/Users/projects/Documents/Feilds_Website" "/home/fields/Feilds_Website" "10_Floor_Plans/backend/enrich_properties_for_sale.py"
echo ""

echo "============================================================"
echo "AUDIT RESULTS"
echo "============================================================"
echo ""

if [ ${#OUTDATED_FILES[@]} -gt 0 ]; then
    echo "🔴 OUTDATED FILES (VM is older than local):"
    echo "-----------------------------------------------------------"
    for item in "${OUTDATED_FILES[@]}"; do
        IFS='|' read -r file local_time vm_time local_size vm_size <<< "$item"
        echo "  ⚠ $file"
        echo "     Local:  $local_time ($local_size bytes)"
        echo "     VM:     $vm_time ($vm_size bytes)"
        echo ""
    done
fi

if [ ${#MISSING_VM[@]} -gt 0 ]; then
    echo "🔴 MISSING ON VM:"
    echo "-----------------------------------------------------------"
    for file in "${MISSING_VM[@]}"; do
        echo "  ✗ $file"
    done
    echo ""
fi

if [ ${#MISSING_LOCAL[@]} -gt 0 ]; then
    echo "⚠️  MISSING LOCALLY (but expected on VM):"
    echo "-----------------------------------------------------------"
    for file in "${MISSING_LOCAL[@]}"; do
        echo "  ✗ $file"
    done
    echo ""
fi

if [ ${#UP_TO_DATE_FILES[@]} -gt 0 ]; then
    echo "✅ UP TO DATE:"
    echo "-----------------------------------------------------------"
    for file in "${UP_TO_DATE_FILES[@]}"; do
        echo "  ✓ $file"
    done
    echo ""
fi

echo "============================================================"
echo "SUMMARY"
echo "============================================================"
echo "✅ Up to date: ${#UP_TO_DATE_FILES[@]}"
echo "🔴 Outdated: ${#OUTDATED_FILES[@]}"
echo "🔴 Missing on VM: ${#MISSING_VM[@]}"
echo "⚠️  Missing locally: ${#MISSING_LOCAL[@]}"
echo ""

if [ ${#OUTDATED_FILES[@]} -gt 0 ] || [ ${#MISSING_VM[@]} -gt 0 ]; then
    echo "⚠️  ACTION REQUIRED: Deploy outdated/missing files to VM"
    exit 1
else
    echo "✅ All files are synchronized!"
    exit 0
fi
