#!/bin/bash
# ============================================================================
# Start Orchestrator on Google Cloud VM
# Last Edit: 07/02/2026, 6:34 PM (Wednesday) - Brisbane Time
#
# Starts the Fields Orchestrator daemon on the GCP VM using systemd
# so it runs as a background service and survives SSH disconnects.
#
# Usage (from local machine):
#   cd /Users/projects/Documents/Fields_Orchestrator/02_Deployment && bash gcp/04_start_orchestrator.sh
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
echo "  Start Orchestrator on GCP VM"
echo "============================================================"
echo ""

# Create systemd service file and start it on the VM
gcloud compute ssh "$VM_NAME" \
    --zone="$ZONE" \
    --project="$PROJECT_ID" \
    --command='
#!/bin/bash
set -e

echo "🔧 Creating systemd service for Fields Orchestrator..."

# Create the systemd service file
sudo tee /etc/systemd/system/fields-orchestrator.service > /dev/null << EOF
[Unit]
Description=Fields Property Data Orchestrator
After=network.target ollama.service
Wants=ollama.service

[Service]
Type=simple
User=$(whoami)
WorkingDirectory=/home/fields/Fields_Orchestrator
Environment="PATH=/home/fields/venv/bin:/usr/local/bin:/usr/bin:/bin"
EnvironmentFile=/home/fields/Fields_Orchestrator/.env
ExecStart=/home/fields/venv/bin/python3 -u src/orchestrator_daemon.py
Restart=on-failure
RestartSec=60
StandardOutput=append:/home/fields/Fields_Orchestrator/logs/orchestrator.log
StandardError=append:/home/fields/Fields_Orchestrator/logs/orchestrator.log

# Resource limits
LimitNOFILE=65536
TimeoutStopSec=300

[Install]
WantedBy=multi-user.target
EOF

echo "   ✅ Service file created"

# Reload systemd
sudo systemctl daemon-reload

# Enable service (start on boot)
sudo systemctl enable fields-orchestrator
echo "   ✅ Service enabled (will start on boot)"

# Start the service
sudo systemctl start fields-orchestrator
echo "   ✅ Service started"

# Wait a moment and check status
sleep 3
echo ""
echo "📊 Service Status:"
sudo systemctl status fields-orchestrator --no-pager -l 2>&1 | head -20

echo ""
echo "📋 Recent Logs:"
tail -20 /home/fields/Fields_Orchestrator/logs/orchestrator.log 2>/dev/null || echo "   (no logs yet)"

echo ""
echo "============================================================"
echo "  ✅ ORCHESTRATOR RUNNING"
echo "============================================================"
echo ""
echo "  Useful commands (run on VM via SSH):"
echo "    sudo systemctl status fields-orchestrator   # Check status"
echo "    sudo systemctl stop fields-orchestrator      # Stop"
echo "    sudo systemctl restart fields-orchestrator   # Restart"
echo "    tail -f /home/fields/Fields_Orchestrator/logs/orchestrator.log  # Live logs"
echo ""
echo "============================================================"
'

echo ""
echo "============================================================"
echo "  ✅ ORCHESTRATOR STARTED ON VM"
echo "============================================================"
echo ""
echo "  To check status:"
echo "    gcloud compute ssh $VM_NAME --zone=$ZONE --project=$PROJECT_ID --command='sudo systemctl status fields-orchestrator'"
echo ""
echo "  To view live logs:"
echo "    gcloud compute ssh $VM_NAME --zone=$ZONE --project=$PROJECT_ID --command='tail -f /home/fields/Fields_Orchestrator/logs/orchestrator.log'"
echo ""
echo "  To SSH into VM:"
echo "    gcloud compute ssh $VM_NAME --zone=$ZONE --project=$PROJECT_ID"
echo "============================================================"
