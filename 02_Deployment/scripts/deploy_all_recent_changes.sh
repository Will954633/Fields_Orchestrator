#!/bin/bash
# Deploy All Recent Changes to VM
# Last Edit: 13/02/2026, 8:13 AM (Friday) — Brisbane Time
#
# Description: Deploys all files modified on Feb 11-12 to the VM

set -e

echo "============================================================"
echo "DEPLOYING ALL RECENT CHANGES TO VM"
echo "============================================================"
echo ""

# Files modified on Feb 11-12 that need deployment
FILES_TO_DEPLOY=(
    # Property Data Scraping (Feb 12)
    "Property_Data_Scraping/03_Gold_Coast/Gold_Coast_Wide_Currently_For_Sale_AND_Recently_Sold/monitor_sold_properties.py"
    "Property_Data_Scraping/03_Gold_Coast/Gold_Coast_Wide_Currently_For_Sale_AND_Recently_Sold/run_parallel_suburb_scrape.py"
    
    # Website Backend (Feb 12)
    "Feilds_Website/08_Market_Narrative_Engine/precompute_market_charts.py"
    "Feilds_Website/08_Market_Narrative_Engine/precompute_indexed_price_data.py"
)

DEPLOYED_COUNT=0
FAILED_COUNT=0

for FILE_PATH in "${FILES_TO_DEPLOY[@]}"; do
    echo "Deploying: $FILE_PATH"
    
    LOCAL_FILE="/Users/projects/Documents/$FILE_PATH"
    VM_FILE="/home/fields/$FILE_PATH"
    
    if [ ! -f "$LOCAL_FILE" ]; then
        echo "  ✗ Local file not found - SKIPPING"
        FAILED_COUNT=$((FAILED_COUNT + 1))
        echo ""
        continue
    fi
    
    # Get directory path
    VM_DIR=$(dirname "$VM_FILE")
    
    # Deploy file
    if gcloud compute scp "$LOCAL_FILE" "fields-orchestrator-vm:$VM_FILE" \
        --zone=australia-southeast1-b \
        --project=fields-estate 2>&1; then
        echo "  ✓ Deployed successfully"
        DEPLOYED_COUNT=$((DEPLOYED_COUNT + 1))
    else
        echo "  ✗ Deployment failed"
        FAILED_COUNT=$((FAILED_COUNT + 1))
    fi
    
    echo ""
done

echo "============================================================"
echo "DEPLOYMENT SUMMARY"
echo "============================================================"
echo "✅ Successfully deployed: $DEPLOYED_COUNT"
echo "❌ Failed: $FAILED_COUNT"
echo ""

if [ $DEPLOYED_COUNT -gt 0 ]; then
    echo "Files deployed successfully. Orchestrator will use them on next run."
    echo "Next scheduled run: Tonight at 20:30 (8:30 PM Brisbane time)"
    echo ""
    echo "To restart orchestrator now (optional):"
    echo "  gcloud compute ssh fields-orchestrator-vm --command='sudo systemctl restart fields-orchestrator'"
fi

if [ $FAILED_COUNT -gt 0 ]; then
    echo "⚠️  Some files failed to deploy. Check errors above."
    exit 1
fi

exit 0
