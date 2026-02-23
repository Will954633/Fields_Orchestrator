#!/bin/bash
# Deploy only updated files to Google Cloud VM
# Created: 2026-02-17

set -e

VM_NAME="fields-orchestrator-vm"
ZONE="australia-southeast1-b"
PROJECT_ID="fields-estate"

echo "=================================================="
echo "TARGETED DEPLOYMENT - Updated Files Only"
echo "=================================================="
echo "VM: $VM_NAME"
echo "Zone: $ZONE"
echo ""

# Check if VM is running
echo "Checking VM status..."
VM_STATUS=$(gcloud compute instances describe $VM_NAME \
    --zone=$ZONE \
    --project=$PROJECT_ID \
    --format='get(status)')

if [ "$VM_STATUS" != "RUNNING" ]; then
    echo "❌ VM is not running (status: $VM_STATUS)"
    echo "Start the VM first with: gcloud compute instances start $VM_NAME --zone=$ZONE"
    exit 1
fi

echo "✅ VM is running"
echo ""

# File 1: Updated scraper with suburb extraction fix
echo "📤 [1/4] Uploading run_parallel_suburb_scrape.py..."
gcloud compute scp \
    /Users/projects/Documents/Property_Data_Scraping/03_Gold_Coast/Gold_Coast_Wide_Currently_For_Sale_AND_Recently_Sold/run_parallel_suburb_scrape.py \
    $VM_NAME:/home/fields/Property_Data_Scraping/03_Gold_Coast/Gold_Coast_Wide_Currently_For_Sale_AND_Recently_Sold/run_parallel_suburb_scrape.py \
    --zone=$ZONE \
    --project=$PROJECT_ID
echo "✅ Scraper updated"
echo ""

# File 2: Updated audit script
echo "📤 [2/4] Uploading database_audit.py..."
gcloud compute scp \
    /Users/projects/Documents/Fields_Orchestrator/scripts/database_audit.py \
    $VM_NAME:/home/fields/Fields_Orchestrator/scripts/database_audit.py \
    --zone=$ZONE \
    --project=$PROJECT_ID
echo "✅ Audit script updated"
echo ""

# File 3: New address fix script
echo "📤 [3/4] Uploading fix_malformed_addresses.py..."
gcloud compute scp \
    /Users/projects/Documents/Fields_Orchestrator/scripts/fix_malformed_addresses.py \
    $VM_NAME:/home/fields/Fields_Orchestrator/scripts/fix_malformed_addresses.py \
    --zone=$ZONE \
    --project=$PROJECT_ID
echo "✅ Address fix script uploaded"
echo ""

# File 4: Updated process config with Process 107
echo "📤 [4/4] Uploading process_commands.yaml..."
gcloud compute scp \
    /Users/projects/Documents/Fields_Orchestrator/config/process_commands.yaml \
    $VM_NAME:/home/fields/Fields_Orchestrator/config/process_commands.yaml \
    --zone=$ZONE \
    --project=$PROJECT_ID
echo "✅ Process config updated"
echo ""

# Restart orchestrator service
echo "🔄 Restarting orchestrator service..."
gcloud compute ssh $VM_NAME \
    --zone=$ZONE \
    --project=$PROJECT_ID \
    --command="sudo systemctl restart fields-orchestrator && sleep 2 && sudo systemctl status fields-orchestrator --no-pager"

echo ""
echo "=================================================="
echo "✅ DEPLOYMENT COMPLETE"
echo "=================================================="
echo ""
echo "Files updated on VM:"
echo "  1. ✅ run_parallel_suburb_scrape.py (suburb extraction fix)"
echo "  2. ✅ database_audit.py (excludes catch-all collections)"
echo "  3. ✅ fix_malformed_addresses.py (new script)"
echo "  4. ✅ process_commands.yaml (Process 107 integration)"
echo ""
echo "Service status:"
gcloud compute ssh $VM_NAME \
    --zone=$ZONE \
    --project=$PROJECT_ID \
    --command="sudo systemctl is-active fields-orchestrator"
echo ""
echo "To view logs:"
echo "  gcloud compute ssh $VM_NAME --zone=$ZONE -- sudo journalctl -u fields-orchestrator -f"
