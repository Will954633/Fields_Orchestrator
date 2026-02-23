#!/bin/bash
# ============================================================================
# Create Google Cloud VM for Fields Orchestrator
# Last Edit: 07/02/2026, 6:32 PM (Wednesday) - Brisbane Time
#
# Creates an e2-medium VM in australia-southeast1 (Sydney) to run
# the Fields Orchestrator pipeline.
#
# Prerequisites:
#   - Google Cloud SDK installed: brew install google-cloud-sdk
#   - Logged in: gcloud auth login
#   - Project set: gcloud config set project fields-estate
#
# Usage:
#   cd /Users/projects/Documents/Fields_Orchestrator/02_Deployment && bash gcp/01_create_vm.sh
# ============================================================================

set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ENV_FILE="$SCRIPT_DIR/../.env"

if [ -f "$ENV_FILE" ]; then
    source "$ENV_FILE"
fi

# Configuration
PROJECT_ID="${GCP_PROJECT_ID:-fields-estate}"
REGION="${GCP_REGION:-australia-southeast1}"
ZONE="${GCP_ZONE:-australia-southeast1-b}"
VM_NAME="${GCP_VM_NAME:-fields-orchestrator-vm}"
MACHINE_TYPE="${GCP_MACHINE_TYPE:-e2-medium}"

# VM specs
BOOT_DISK_SIZE="50"  # GB - enough for code, Ollama models, Chrome
BOOT_DISK_TYPE="pd-balanced"  # SSD-like performance at lower cost
IMAGE_FAMILY="ubuntu-2204-lts"
IMAGE_PROJECT="ubuntu-os-cloud"

echo "============================================================"
echo "  Google Cloud VM Creation - Fields Orchestrator"
echo "============================================================"
echo ""
echo "  Project:      $PROJECT_ID"
echo "  Region:       $REGION"
echo "  Zone:         $ZONE"
echo "  VM Name:      $VM_NAME"
echo "  Machine Type: $MACHINE_TYPE (2 vCPU, 4 GB RAM)"
echo "  Disk:         ${BOOT_DISK_SIZE}GB $BOOT_DISK_TYPE"
echo "  OS:           Ubuntu 22.04 LTS"
echo ""
echo "  Estimated Cost: ~\$25/month"
echo ""
echo "============================================================"
echo ""

# Step 0: Check gcloud CLI
echo "🔍 Step 0: Checking Google Cloud SDK..."
if ! command -v gcloud &> /dev/null; then
    echo "❌ gcloud CLI not found. Install with: brew install google-cloud-sdk"
    exit 1
fi

# Check if logged in
if ! gcloud auth list --filter=status:ACTIVE --format="value(account)" 2>/dev/null | head -1 | grep -q "@"; then
    echo "❌ Not logged in to Google Cloud. Run: gcloud auth login"
    exit 1
fi

# Set project
echo "   Setting project to $PROJECT_ID..."
gcloud config set project "$PROJECT_ID" 2>/dev/null
echo "   ✅ Project set"
echo ""

# Step 1: Enable required APIs
echo "🔧 Step 1: Enabling required APIs..."
gcloud services enable compute.googleapis.com --quiet 2>/dev/null || true
echo "   ✅ Compute Engine API enabled"
echo ""

# Step 2: Create firewall rule for SSH (if not exists)
echo "🔧 Step 2: Checking firewall rules..."
if ! gcloud compute firewall-rules describe allow-ssh --quiet 2>/dev/null; then
    echo "   Creating SSH firewall rule..."
    gcloud compute firewall-rules create allow-ssh \
        --allow tcp:22 \
        --source-ranges 0.0.0.0/0 \
        --description "Allow SSH access" \
        --quiet 2>/dev/null || true
fi
echo "   ✅ SSH firewall rule exists"
echo ""

# Step 3: Create the VM
echo "🔧 Step 3: Creating VM '$VM_NAME'..."
echo "   ⏳ This may take 1-2 minutes..."

if gcloud compute instances describe "$VM_NAME" --zone="$ZONE" --quiet 2>/dev/null; then
    echo "   ℹ️  VM already exists"
    VM_STATUS=$(gcloud compute instances describe "$VM_NAME" --zone="$ZONE" --format="value(status)")
    echo "   Status: $VM_STATUS"
    if [ "$VM_STATUS" = "TERMINATED" ]; then
        echo "   Starting VM..."
        gcloud compute instances start "$VM_NAME" --zone="$ZONE" --quiet
        echo "   ✅ VM started"
    fi
else
    gcloud compute instances create "$VM_NAME" \
        --zone="$ZONE" \
        --machine-type="$MACHINE_TYPE" \
        --boot-disk-size="${BOOT_DISK_SIZE}GB" \
        --boot-disk-type="$BOOT_DISK_TYPE" \
        --image-family="$IMAGE_FAMILY" \
        --image-project="$IMAGE_PROJECT" \
        --tags="fields-orchestrator" \
        --labels="project=fields-estate,environment=production" \
        --metadata="startup-script=#! /bin/bash
echo 'Fields Orchestrator VM started at \$(date)' >> /var/log/fields-startup.log" \
        --quiet
    
    echo "   ✅ VM created"
fi
echo ""

# Step 4: Get VM details
echo "🔍 Step 4: VM Details..."
EXTERNAL_IP=$(gcloud compute instances describe "$VM_NAME" \
    --zone="$ZONE" \
    --format="value(networkInterfaces[0].accessConfigs[0].natIP)")

INTERNAL_IP=$(gcloud compute instances describe "$VM_NAME" \
    --zone="$ZONE" \
    --format="value(networkInterfaces[0].networkIP)")

echo ""
echo "============================================================"
echo "  ✅ VM CREATED SUCCESSFULLY"
echo "============================================================"
echo ""
echo "  VM Name:     $VM_NAME"
echo "  External IP: $EXTERNAL_IP"
echo "  Internal IP: $INTERNAL_IP"
echo "  Zone:        $ZONE"
echo ""
echo "  SSH Access:"
echo "    gcloud compute ssh $VM_NAME --zone=$ZONE --project=$PROJECT_ID"
echo ""
echo "  Or with standard SSH:"
echo "    ssh -i ~/.ssh/google_compute_engine $EXTERNAL_IP"
echo ""
echo "  Next Steps:"
echo "    1. Set up VM: cd /Users/projects/Documents/Fields_Orchestrator/02_Deployment && bash gcp/02_setup_vm.sh"
echo "    2. Deploy code: cd /Users/projects/Documents/Fields_Orchestrator/02_Deployment && bash gcp/03_deploy_code.sh"
echo "    3. Start orchestrator: cd /Users/projects/Documents/Fields_Orchestrator/02_Deployment && bash gcp/04_start_orchestrator.sh"
echo ""
echo "  💡 To stop VM (save costs when not in use):"
echo "    gcloud compute instances stop $VM_NAME --zone=$ZONE"
echo ""
echo "  💡 To delete VM:"
echo "    gcloud compute instances delete $VM_NAME --zone=$ZONE"
echo "============================================================"
