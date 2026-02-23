#!/bin/bash
# ============================================================================
# Trigger VM Orchestrator with 5-Minute Delay
# Last Edit: 10/02/2026, 8:59 AM (Monday) - Brisbane Time
#
# This script triggers the orchestrator on the GCP VM to run after a 5-minute delay.
# It will start the orchestrator service if it's not already running, or restart it
# if it is running to trigger a fresh run.
#
# Usage:
#   cd /Users/projects/Documents/Fields_Orchestrator/02_Deployment && bash scripts/trigger_vm_orchestrator_delayed.sh
# ============================================================================

set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ENV_FILE="$SCRIPT_DIR/../.env"

if [ -f "$ENV_FILE" ]; then
    source "$ENV_FILE"
fi

PROJECT_ID="${GCP_PROJECT_ID:-fields-estate}"
ZONE="${GCP_ZONE:-australia-southeast1-b}"
VM_NAME="${GCP_VM_NAME:-fields-orchestrator-vm}"

echo "============================================================"
echo "  Trigger VM Orchestrator (5-Minute Delay)"
echo "============================================================"
echo ""
echo "  Current Time: $(date '+%Y-%m-%d %H:%M:%S %Z')"
echo "  Trigger Time: $(date -v+5M '+%Y-%m-%d %H:%M:%S %Z' 2>/dev/null || date -d '+5 minutes' '+%Y-%m-%d %H:%M:%S %Z' 2>/dev/null || echo 'in 5 minutes')"
echo ""
echo "  VM: $VM_NAME"
echo "  Zone: $ZONE"
echo "  Project: $PROJECT_ID"
echo ""
echo "============================================================"
echo ""

# Create a background job that will trigger after 5 minutes
(
    echo "⏰ Waiting 5 minutes before triggering orchestrator..."
    sleep 300  # 5 minutes = 300 seconds
    
    echo ""
    echo "============================================================"
    echo "  ⏰ 5 MINUTES ELAPSED - TRIGGERING ORCHESTRATOR NOW"
    echo "============================================================"
    echo ""
    echo "  Trigger Time: $(date '+%Y-%m-%d %H:%M:%S %Z')"
    echo ""
    
    # SSH into VM and restart the orchestrator service
    gcloud compute ssh "$VM_NAME" \
        --zone="$ZONE" \
        --project="$PROJECT_ID" \
        --command='
#!/bin/bash
set -e

echo "🔄 Restarting Fields Orchestrator service..."
echo ""

# Check if service exists
if sudo systemctl list-unit-files | grep -q "fields-orchestrator.service"; then
    echo "   ✅ Service found"
    
    # Restart the service (this will trigger a fresh run)
    sudo systemctl restart fields-orchestrator
    echo "   ✅ Service restarted"
    
    # Wait a moment for startup
    sleep 5
    
    # Check status
    echo ""
    echo "📊 Service Status:"
    sudo systemctl status fields-orchestrator --no-pager -l 2>&1 | head -20
    
    echo ""
    echo "📋 Recent Logs:"
    tail -30 /home/fields/Fields_Orchestrator/logs/orchestrator.log 2>/dev/null || echo "   (no logs yet)"
    
    echo ""
    echo "============================================================"
    echo "  ✅ ORCHESTRATOR TRIGGERED AND RUNNING"
    echo "============================================================"
    echo ""
    echo "  The orchestrator is now running on the VM."
    echo "  It will execute all scheduled processes."
    echo ""
    echo "  To monitor progress:"
    echo "    gcloud compute ssh '"$VM_NAME"' --zone='"$ZONE"' --project='"$PROJECT_ID"' --command=\"tail -f /home/fields/Fields_Orchestrator/logs/orchestrator.log\""
    echo ""
    echo "============================================================"
else
    echo "   ❌ Service not found!"
    echo ""
    echo "   The fields-orchestrator service is not installed on the VM."
    echo "   Please run the deployment script first:"
    echo "     cd /Users/projects/Documents/Fields_Orchestrator/02_Deployment && bash gcp/04_start_orchestrator.sh"
    exit 1
fi
'
    
    echo ""
    echo "============================================================"
    echo "  ✅ ORCHESTRATOR TRIGGER COMPLETE"
    echo "============================================================"
    echo ""
    echo "  The orchestrator has been triggered on the VM."
    echo "  Check the logs to monitor progress."
    echo ""
    
) &

BACKGROUND_PID=$!

echo "✅ Trigger scheduled successfully!"
echo ""
echo "   Background Process ID: $BACKGROUND_PID"
echo "   Trigger will execute at: $(date -v+5M '+%Y-%m-%d %H:%M:%S %Z' 2>/dev/null || date -d '+5 minutes' '+%Y-%m-%d %H:%M:%S %Z' 2>/dev/null || echo 'in 5 minutes')"
echo ""
echo "============================================================"
echo ""
echo "📝 What happens next:"
echo ""
echo "   1. This script will wait 5 minutes in the background"
echo "   2. After 5 minutes, it will SSH into the VM"
echo "   3. It will restart the orchestrator service"
echo "   4. The orchestrator will begin executing all scheduled processes"
echo ""
echo "============================================================"
echo ""
echo "💡 Useful commands:"
echo ""
echo "   # Check if trigger is still waiting:"
echo "   ps -p $BACKGROUND_PID"
echo ""
echo "   # Monitor VM logs (after trigger):"
echo "   gcloud compute ssh $VM_NAME --zone=$ZONE --project=$PROJECT_ID --command='tail -f /home/fields/Fields_Orchestrator/logs/orchestrator.log'"
echo ""
echo "   # Check VM service status:"
echo "   gcloud compute ssh $VM_NAME --zone=$ZONE --project=$PROJECT_ID --command='sudo systemctl status fields-orchestrator'"
echo ""
echo "============================================================"
echo ""
echo "✅ You can now close this terminal or continue working."
echo "   The trigger will execute automatically in 5 minutes."
echo ""
