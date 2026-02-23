#!/bin/bash
# ============================================================================
# Check Fields Orchestrator VM Status
# Last Edit: 16/02/2026, 8:10 AM (Sunday) - Brisbane Time
#
# Quick status check for the Fields Orchestrator running on Google Cloud VM
#
# Usage:
#   cd /Users/projects/Documents/Fields_Orchestrator/02_Deployment && bash scripts/check_vm_status.sh
#
# What this script checks:
#   1. VM instance status (running/stopped)
#   2. Orchestrator service status (active/inactive)
#   3. Recent orchestrator logs (last 20 lines)
#   4. Current orchestration progress
#   5. Any errors in logs
# ============================================================================

set -e

# VM Configuration (SINGLE INSTANCE)
PROJECT_ID="fields-estate"
ZONE="australia-southeast1-b"
VM_NAME="fields-orchestrator-vm"

echo "============================================================"
echo "  Fields Orchestrator VM Status Check"
echo "============================================================"
echo ""
echo "  VM Instance: $VM_NAME"
echo "  Project:     $PROJECT_ID"
echo "  Zone:        $ZONE"
echo ""
echo "============================================================"
echo ""

# Check if gcloud is installed
if ! command -v gcloud &> /dev/null; then
    echo "❌ gcloud CLI not found. Install with: brew install google-cloud-sdk"
    exit 1
fi

# Step 1: Check VM Status
echo "🔍 Step 1: Checking VM Instance Status..."
if ! gcloud compute instances describe "$VM_NAME" --zone="$ZONE" --project="$PROJECT_ID" --quiet 2>/dev/null; then
    echo "   ❌ VM does not exist or cannot be accessed"
    echo ""
    echo "   To create VM:"
    echo "     cd /Users/projects/Documents/Fields_Orchestrator/02_Deployment && bash gcp/01_create_vm.sh"
    exit 1
fi

VM_STATUS=$(gcloud compute instances describe "$VM_NAME" --zone="$ZONE" --project="$PROJECT_ID" --format="value(status)")
EXTERNAL_IP=$(gcloud compute instances describe "$VM_NAME" --zone="$ZONE" --project="$PROJECT_ID" --format="value(networkInterfaces[0].accessConfigs[0].natIP)")

if [ "$VM_STATUS" = "RUNNING" ]; then
    echo "   ✅ VM is RUNNING"
    echo "   External IP: $EXTERNAL_IP"
else
    echo "   ⚠️  VM Status: $VM_STATUS"
    echo ""
    echo "   To start VM:"
    echo "     gcloud compute instances start $VM_NAME --zone=$ZONE --project=$PROJECT_ID"
    exit 0
fi
echo ""

# Step 2: Check Orchestrator Service Status
echo "🔍 Step 2: Checking Orchestrator Service..."
SERVICE_STATUS=$(gcloud compute ssh "$VM_NAME" --zone="$ZONE" --project="$PROJECT_ID" --command='sudo systemctl is-active fields-orchestrator' 2>/dev/null || echo "inactive")

if [ "$SERVICE_STATUS" = "active" ]; then
    echo "   ✅ Orchestrator service is ACTIVE"
else
    echo "   ❌ Orchestrator service is $SERVICE_STATUS"
    echo ""
    echo "   To start service:"
    echo "     gcloud compute ssh $VM_NAME --zone=$ZONE --project=$PROJECT_ID --command='sudo systemctl start fields-orchestrator'"
    exit 0
fi
echo ""

# Step 3: Check Recent Logs
echo "🔍 Step 3: Recent Orchestrator Logs (last 20 lines)..."
echo "   ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
gcloud compute ssh "$VM_NAME" --zone="$ZONE" --project="$PROJECT_ID" --command='tail -20 /home/fields/Fields_Orchestrator/logs/orchestrator.log' 2>/dev/null | sed 's/^/   /'
echo "   ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo ""

# Step 4: Check for Today's Run
echo "🔍 Step 4: Checking Today's Orchestration Run..."
TODAY=$(date +%Y-%m-%d)
TODAY_LOGS=$(gcloud compute ssh "$VM_NAME" --zone="$ZONE" --project="$PROJECT_ID" --command="grep '$TODAY' /home/fields/Fields_Orchestrator/logs/orchestrator.log | wc -l" 2>/dev/null || echo "0")

if [ "$TODAY_LOGS" -gt 0 ]; then
    echo "   ✅ Found $TODAY_LOGS log entries for today ($TODAY)"
    
    # Check when it started
    START_TIME=$(gcloud compute ssh "$VM_NAME" --zone="$ZONE" --project="$PROJECT_ID" --command="grep '$TODAY' /home/fields/Fields_Orchestrator/logs/orchestrator.log | head -1 | cut -d'|' -f1" 2>/dev/null || echo "Unknown")
    echo "   First log entry: $START_TIME"
    
    # Check current step
    CURRENT_STEP=$(gcloud compute ssh "$VM_NAME" --zone="$ZONE" --project="$PROJECT_ID" --command="grep 'STEP' /home/fields/Fields_Orchestrator/logs/orchestrator.log | tail -1" 2>/dev/null || echo "Unknown")
    if [ -n "$CURRENT_STEP" ]; then
        echo "   Current activity: $CURRENT_STEP"
    fi
else
    echo "   ⚠️  No log entries found for today ($TODAY)"
    echo "   Last log entry:"
    gcloud compute ssh "$VM_NAME" --zone="$ZONE" --project="$PROJECT_ID" --command='tail -1 /home/fields/Fields_Orchestrator/logs/orchestrator.log' 2>/dev/null | sed 's/^/     /'
fi
echo ""

# Step 5: Check for Errors
echo "🔍 Step 5: Checking for Recent Errors..."
ERROR_COUNT=$(gcloud compute ssh "$VM_NAME" --zone="$ZONE" --project="$PROJECT_ID" --command="grep '$TODAY' /home/fields/Fields_Orchestrator/logs/orchestrator.log | grep -i 'ERROR\|FAILED' | wc -l" 2>/dev/null || echo "0")

if [ "$ERROR_COUNT" -gt 0 ]; then
    echo "   ⚠️  Found $ERROR_COUNT errors today"
    echo "   Recent errors:"
    gcloud compute ssh "$VM_NAME" --zone="$ZONE" --project="$PROJECT_ID" --command="grep '$TODAY' /home/fields/Fields_Orchestrator/logs/orchestrator.log | grep -i 'ERROR\|FAILED' | tail -5" 2>/dev/null | sed 's/^/     /'
else
    echo "   ✅ No errors found in today's logs"
fi
echo ""

# Step 6: Summary
echo "============================================================"
echo "  Summary"
echo "============================================================"
echo ""
echo "  VM Status:          $VM_STATUS"
echo "  Service Status:     $SERVICE_STATUS"
echo "  Today's Log Lines:  $TODAY_LOGS"
echo "  Errors Today:       $ERROR_COUNT"
echo ""
echo "============================================================"
echo ""
echo "  Useful Commands:"
echo ""
echo "  📊 View full logs:"
echo "     gcloud compute ssh $VM_NAME --zone=$ZONE --project=$PROJECT_ID --command='tail -f /home/fields/Fields_Orchestrator/logs/orchestrator.log'"
echo ""
echo "  🔄 Restart service:"
echo "     gcloud compute ssh $VM_NAME --zone=$ZONE --project=$PROJECT_ID --command='sudo systemctl restart fields-orchestrator'"
echo ""
echo "  📈 Check service status:"
echo "     gcloud compute ssh $VM_NAME --zone=$ZONE --project=$PROJECT_ID --command='sudo systemctl status fields-orchestrator'"
echo ""
echo "  🔍 Search logs for specific date/time:"
echo "     gcloud compute ssh $VM_NAME --zone=$ZONE --project=$PROJECT_ID --command='grep \"2026-02-16 07:\" /home/fields/Fields_Orchestrator/logs/orchestrator.log'"
echo ""
echo "============================================================"
