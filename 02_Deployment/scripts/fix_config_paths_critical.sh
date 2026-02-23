#!/bin/bash
# Fix Critical Config Path Issue on VM
# Last Updated: 15/02/2026, 7:32 PM (Sunday) - Brisbane Time
#
# CRITICAL ISSUE: The VM has the local development process_commands.yaml with Mac paths
# This causes ALL processes to fail because they try to access /Users/projects/Documents/...
# instead of /home/fields/...
#
# This script:
# 1. Backs up the current (broken) config
# 2. Copies the correct cloud config with VM paths
# 3. DELETES the local development config from VM to prevent future mistakes
# 4. Restarts the orchestrator service

set -e

echo "=========================================="
echo "CRITICAL CONFIG PATH FIX"
echo "=========================================="
echo ""

# Step 1: Backup the broken config
echo "Step 1: Backing up broken config..."
gcloud compute ssh fields-orchestrator-vm \
  --zone=australia-southeast1-b \
  --project=fields-estate \
  --command='
    cd /home/fields/Fields_Orchestrator/config
    cp process_commands.yaml process_commands.yaml.BROKEN_LOCAL_PATHS_$(date +%Y%m%d_%H%M%S)
    echo "✅ Backup created"
  '

# Step 2: Copy the correct cloud config
echo ""
echo "Step 2: Copying correct cloud config with VM paths..."
cd /Users/projects/Documents/Fields_Orchestrator
gcloud compute scp \
  02_Deployment/config/process_commands_cloud.yaml \
  fields-orchestrator-vm:/home/fields/Fields_Orchestrator/config/process_commands.yaml \
  --zone=australia-southeast1-b \
  --project=fields-estate

echo "✅ Correct config deployed"

# Step 3: Verify the paths are correct
echo ""
echo "Step 3: Verifying paths are now correct..."
gcloud compute ssh fields-orchestrator-vm \
  --zone=australia-southeast1-b \
  --project=fields-estate \
  --command='
    echo "Checking Step 101 working_dir:"
    grep -A 5 "id: 101" /home/fields/Fields_Orchestrator/config/process_commands.yaml | grep working_dir
    
    echo ""
    echo "Checking Step 103 working_dir:"
    grep -A 5 "id: 103" /home/fields/Fields_Orchestrator/config/process_commands.yaml | grep working_dir
  '

# Step 4: Delete any remaining local development configs
echo ""
echo "Step 4: Removing local development configs from VM..."
gcloud compute ssh fields-orchestrator-vm \
  --zone=australia-southeast1-b \
  --project=fields-estate \
  --command='
    cd /home/fields/Fields_Orchestrator/config
    
    # Remove any files with "cloud" in the name (these should not exist on VM)
    rm -f process_commands_cloud.yaml settings_cloud.yaml 2>/dev/null || true
    
    echo "✅ Local development configs removed"
    echo ""
    echo "Remaining config files:"
    ls -la /home/fields/Fields_Orchestrator/config/
  '

# Step 5: Restart orchestrator service
echo ""
echo "Step 5: Restarting orchestrator service..."
gcloud compute ssh fields-orchestrator-vm \
  --zone=australia-southeast1-b \
  --project=fields-estate \
  --command='
    sudo systemctl restart fields-orchestrator
    sleep 3
    sudo systemctl status fields-orchestrator --no-pager | head -20
  '

echo ""
echo "=========================================="
echo "✅ CONFIG FIX COMPLETE"
echo "=========================================="
echo ""
echo "The orchestrator now has:"
echo "  - Correct VM paths (/home/fields/...)"
echo "  - No local development configs"
echo "  - Service restarted"
echo ""
echo "Next steps:"
echo "1. Monitor logs: gcloud compute ssh fields-orchestrator-vm --zone=australia-southeast1-b --project=fields-estate --command='tail -f /home/fields/Fields_Orchestrator/logs/orchestrator.log'"
echo "2. Wait for next scheduled run (20:30 Brisbane time)"
echo "3. Verify all steps complete successfully"
