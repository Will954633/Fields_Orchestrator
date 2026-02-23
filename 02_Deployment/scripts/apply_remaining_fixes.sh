#!/bin/bash
# Apply Remaining VM Orchestrator Fixes
# Last Edit: 13/02/2026, 8:01 AM (Friday) — Brisbane Time
#
# Description: Applies the remaining fixes identified in night run analysis:
# 1. Add COSMOS_CONNECTION_STRING environment variable to systemd service
# 2. Deploy cloud settings.yaml with skip_backup: true
# 3. Restart orchestrator service

set -e  # Exit on error

COSMOS_CONN_STR='mongodb://fields-property-cosmos:REDACTED'

echo "============================================================"
echo "APPLYING REMAINING VM ORCHESTRATOR FIXES"
echo "============================================================"
echo ""

# Fix 1: Update systemd service with COSMOS_CONNECTION_STRING
echo "Fix 1: Adding COSMOS_CONNECTION_STRING to systemd service..."
gcloud compute ssh fields-orchestrator-vm \
  --zone=australia-southeast1-b \
  --project=fields-estate \
  --command="sudo tee /etc/systemd/system/fields-orchestrator.service > /dev/null <<'EOF'
[Unit]
Description=Fields Property Data Orchestrator
After=network.target

[Service]
Type=simple
User=fields
WorkingDirectory=/home/fields/Fields_Orchestrator
Environment=\"COSMOS_CONNECTION_STRING=${COSMOS_CONN_STR}\"
ExecStart=/usr/bin/python3 -u src/orchestrator_daemon.py
Restart=always
RestartSec=10
StandardOutput=append:/home/fields/Fields_Orchestrator/logs/orchestrator.log
StandardError=append:/home/fields/Fields_Orchestrator/logs/orchestrator.log

[Install]
WantedBy=multi-user.target
EOF
"

echo "✅ Systemd service updated with COSMOS_CONNECTION_STRING"
echo ""

# Fix 2: Deploy cloud settings.yaml
echo "Fix 2: Deploying cloud settings.yaml (with skip_backup: true)..."
cd /Users/projects/Documents/Fields_Orchestrator
gcloud compute scp 02_Deployment/config/settings_cloud.yaml \
  fields-orchestrator-vm:/home/fields/Fields_Orchestrator/config/settings.yaml \
  --zone=australia-southeast1-b \
  --project=fields-estate

echo "✅ Cloud settings.yaml deployed"
echo ""

# Fix 3: Reload systemd and restart service
echo "Fix 3: Reloading systemd and restarting orchestrator..."
gcloud compute ssh fields-orchestrator-vm \
  --zone=australia-southeast1-b \
  --project=fields-estate \
  --command='sudo systemctl daemon-reload && sudo systemctl restart fields-orchestrator'

echo "✅ Orchestrator service restarted"
echo ""

# Verification
echo "============================================================"
echo "VERIFICATION"
echo "============================================================"
echo ""

echo "Checking service status..."
gcloud compute ssh fields-orchestrator-vm \
  --zone=australia-southeast1-b \
  --project=fields-estate \
  --command='sudo systemctl status fields-orchestrator --no-pager | head -15'

echo ""
echo "Checking if COSMOS_CONNECTION_STRING is set..."
gcloud compute ssh fields-orchestrator-vm \
  --zone=australia-southeast1-b \
  --project=fields-estate \
  --command='systemctl show fields-orchestrator | grep "COSMOS_CONNECTION_STRING" | head -c 100'

echo ""
echo ""
echo "Checking if skip_backup is enabled..."
gcloud compute ssh fields-orchestrator-vm \
  --zone=australia-southeast1-b \
  --project=fields-estate \
  --command='grep "skip_backup:" /home/fields/Fields_Orchestrator/config/settings.yaml'

echo ""
echo "============================================================"
echo "ALL FIXES APPLIED SUCCESSFULLY"
echo "============================================================"
echo ""
echo "Next scheduled run: Tonight at 20:30 (8:30 PM Brisbane time)"
echo "Monitor logs: gcloud compute ssh fields-orchestrator-vm --command='tail -f /home/fields/Fields_Orchestrator/logs/orchestrator.log'"
