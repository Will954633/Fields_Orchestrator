#!/bin/bash
# Disable Confirmation Dialogs for Cloud Deployment
# Last Updated: 15/02/2026, 8:58 PM (Sunday) - Brisbane Time
#
# The orchestrator currently shows confirmation dialogs which don't work on Linux VM
# This causes a 30-minute snooze delay. This script:
# 1. Deploys updated settings.yaml with skip_confirmation_dialogs: true
# 2. Restarts the orchestrator
#
# Future improvement: Update orchestrator_daemon.py to check this setting

set -e

echo "=========================================="
echo "DISABLE CONFIRMATION DIALOGS"
echo "=========================================="
echo ""

# Step 1: Deploy updated settings
echo "Step 1: Deploying updated settings.yaml..."
cd /Users/projects/Documents/Fields_Orchestrator
gcloud compute scp \
  02_Deployment/config/settings_cloud.yaml \
  fields-orchestrator-vm:/home/fields/Fields_Orchestrator/config/settings.yaml \
  --zone=australia-southeast1-b \
  --project=fields-estate

echo "✅ Settings deployed"

# Step 2: Verify the setting
echo ""
echo "Step 2: Verifying skip_confirmation_dialogs setting..."
gcloud compute ssh fields-orchestrator-vm \
  --zone=australia-southeast1-b \
  --project=fields-estate \
  --command='grep "skip_confirmation_dialogs" /home/fields/Fields_Orchestrator/config/settings.yaml'

# Step 3: Restart orchestrator
echo ""
echo "Step 3: Restarting orchestrator..."
gcloud compute ssh fields-orchestrator-vm \
  --zone=australia-southeast1-b \
  --project=fields-estate \
  --command='sudo systemctl restart fields-orchestrator'

sleep 3

# Step 4: Check status
echo ""
echo "Step 4: Checking orchestrator status..."
gcloud compute ssh fields-orchestrator-vm \
  --zone=australia-southeast1-b \
  --project=fields-estate \
  --command='sudo systemctl status fields-orchestrator --no-pager | head -15'

echo ""
echo "=========================================="
echo "✅ SETTINGS DEPLOYED"
echo "=========================================="
echo ""
echo "NOTE: The orchestrator code still has dialog logic."
echo "The setting is in place, but the code needs to be updated"
echo "to actually check and respect this setting."
echo ""
echo "For now, dialogs will still attempt to show (and fail),"
echo "causing the 30-minute snooze."
echo ""
echo "Next step: Update src/orchestrator_daemon.py to check"
echo "settings['schedule']['skip_confirmation_dialogs'] and"
echo "skip the dialog code entirely when true."
