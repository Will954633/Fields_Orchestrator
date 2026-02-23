#!/bin/bash
# VM Deployment Verification Script
# Last Edit: 13/02/2026, 8:08 AM (Friday) — Brisbane Time
#
# Description: Compares local files with VM files to ensure all updates are deployed
# Run this script after making changes to verify they're on the VM

set -e

echo "============================================================"
echo "VM DEPLOYMENT VERIFICATION"
echo "============================================================"
echo ""

# Color codes
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

# Files to check
declare -A FILES=(
    # Orchestrator config files
    ["Fields_Orchestrator/config/process_commands.yaml"]="Fields_Orchestrator/config/process_commands.yaml"
    ["Fields_Orchestrator/config/settings.yaml"]="Fields_Orchestrator/config/settings.yaml"
    
    # Scraping scripts
    ["Property_Data_Scraping/03_Gold_Coast/Gold_Coast_Wide_Currently_For_Sale_AND_Recently_Sold/monitor_sold_properties.py"]="Property_Data_Scraping/03_Gold_Coast/Gold_Coast_Wide_Currently_For_Sale_AND_Recently_Sold/monitor_sold_properties.py"
    ["Property_Data_Scraping/03_Gold_Coast/Gold_Coast_Wide_Currently_For_Sale_AND_Recently_Sold/run_dynamic_10_suburbs.py"]="Property_Data_Scraping/03_Gold_Coast/Gold_Coast_Wide_Currently_For_Sale_AND_Recently_Sold/run_dynamic_10_suburbs.py"
    
    # Ollama analysis scripts
    ["Property_Data_Scraping/03_Gold_Coast/Gold_Coast_Wide_Currently_For_Sale_AND_Recently_Sold/Ollama_Property_Analysis/run_target_market_photo_analysis.sh"]="Property_Data_Scraping/03_Gold_Coast/Gold_Coast_Wide_Currently_For_Sale_AND_Recently_Sold/Ollama_Property_Analysis/run_target_market_photo_analysis.sh"
    ["Property_Data_Scraping/03_Gold_Coast/Gold_Coast_Wide_Currently_For_Sale_AND_Recently_Sold/Ollama_Property_Analysis/run_target_market_floor_plan_analysis.sh"]="Property_Data_Scraping/03_Gold_Coast/Gold_Coast_Wide_Currently_For_Sale_AND_Recently_Sold/Ollama_Property_Analysis/run_target_market_floor_plan_analysis.sh"
)

OUTDATED_COUNT=0
UP_TO_DATE_COUNT=0
MISSING_COUNT=0

for LOCAL_PATH in "${!FILES[@]}"; do
    VM_PATH="${FILES[$LOCAL_PATH]}"
    
    LOCAL_FULL="/Users/projects/Documents/$LOCAL_PATH"
    VM_FULL="/home/fields/$VM_PATH"
    
    echo "Checking: $LOCAL_PATH"
    
    # Get local modification time
    if [ -f "$LOCAL_FULL" ]; then
        LOCAL_TIME=$(stat -f "%Sm" -t "%Y-%m-%d %H:%M:%S" "$LOCAL_FULL" 2>/dev/null || echo "ERROR")
    else
        echo -e "  ${RED}✗ Local file not found${NC}"
        MISSING_COUNT=$((MISSING_COUNT + 1))
        echo ""
        continue
    fi
    
    # Get VM modification time
    VM_TIME=$(gcloud compute ssh fields-orchestrator-vm \
        --zone=australia-southeast1-b \
        --project=fields-estate \
        --command="stat -c '%y' $VM_FULL 2>/dev/null || echo 'MISSING'" | head -1)
    
    if [ "$VM_TIME" = "MISSING" ]; then
        echo -e "  ${RED}✗ VM file not found${NC}"
        MISSING_COUNT=$((MISSING_COUNT + 1))
    elif [ "$LOCAL_TIME" = "ERROR" ]; then
        echo -e "  ${RED}✗ Cannot read local file${NC}"
        MISSING_COUNT=$((MISSING_COUNT + 1))
    else
        # Extract just the date/time for comparison
        VM_TIME_SHORT=$(echo "$VM_TIME" | cut -d'.' -f1)
        
        echo "  Local:  $LOCAL_TIME"
        echo "  VM:     $VM_TIME_SHORT"
        
        # Compare timestamps (simple string comparison)
        if [[ "$VM_TIME_SHORT" > "$LOCAL_TIME" ]] || [[ "$VM_TIME_SHORT" == "$LOCAL_TIME"* ]]; then
            echo -e "  ${GREEN}✓ VM is up to date${NC}"
            UP_TO_DATE_COUNT=$((UP_TO_DATE_COUNT + 1))
        else
            echo -e "  ${YELLOW}⚠ VM is OUTDATED - needs deployment${NC}"
            OUTDATED_COUNT=$((OUTDATED_COUNT + 1))
        fi
    fi
    
    echo ""
done

echo "============================================================"
echo "SUMMARY"
echo "============================================================"
echo -e "${GREEN}Up to date: $UP_TO_DATE_COUNT${NC}"
echo -e "${YELLOW}Outdated: $OUTDATED_COUNT${NC}"
echo -e "${RED}Missing: $MISSING_COUNT${NC}"
echo ""

if [ $OUTDATED_COUNT -gt 0 ] || [ $MISSING_COUNT -gt 0 ]; then
    echo -e "${YELLOW}⚠ WARNING: Some files need to be deployed to the VM${NC}"
    echo ""
    echo "To deploy all files, run:"
    echo "  cd /Users/projects/Documents/Fields_Orchestrator/02_Deployment/scripts"
    echo "  ./deploy_all_to_vm.sh"
    exit 1
else
    echo -e "${GREEN}✓ All files are up to date on the VM${NC}"
    exit 0
fi
