#!/bin/bash
# ============================================================================
# Deploy Code to Google Cloud VM
# Last Edit: 08/02/2026, 7:25 AM (Sunday) - Brisbane Time
# Edit: Added aggressive excludes for large data dirs (07_Undetectable_method,
#   02_Domain_Scaping, batch_results, listing_results, etc.) to reduce upload
#   from 2.9GB to ~100MB. Previous version was hanging for 30-60+ mins on Step 2.
# Previous Edit: 07/02/2026, 6:33 PM (Wednesday) - Brisbane Time
#
# Syncs the orchestrator code, scraping scripts, website backend, and
# valuation code to the GCP VM using gcloud SCP/rsync.
#
# Usage (from local machine):
#   cd /Users/projects/Documents/Fields_Orchestrator/02_Deployment && bash gcp/03_deploy_code.sh
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

# Local source directories
LOCAL_ORCHESTRATOR="/Users/projects/Documents/Fields_Orchestrator"
LOCAL_SCRAPING="/Users/projects/Documents/Property_Data_Scraping"
LOCAL_WEBSITE="/Users/projects/Documents/Feilds_Website"
LOCAL_VALUATION="/Users/projects/Documents/Property_Valuation"

# Remote target directories
REMOTE_BASE="/home/fields"

echo "============================================================"
echo "  Deploy Code to GCP VM"
echo "  $(date '+%Y-%m-%d %H:%M:%S') (Brisbane)"
echo "============================================================"
echo ""
echo "  VM: $VM_NAME ($ZONE)"
echo ""
echo "  Deploying:"
echo "    📁 Fields_Orchestrator → $REMOTE_BASE/Fields_Orchestrator"
echo "    📁 Property_Data_Scraping → $REMOTE_BASE/Property_Data_Scraping"
echo "    📁 Feilds_Website → $REMOTE_BASE/Feilds_Website"
echo "    📁 Property_Valuation → $REMOTE_BASE/Property_Valuation"
echo ""
echo "============================================================"
echo ""

# Helper function to sync a directory
sync_dir() {
    local LOCAL_DIR="$1"
    local REMOTE_DIR="$2"
    local LABEL="$3"
    
    echo "📦 Syncing $LABEL..."
    echo "   Local:  $LOCAL_DIR"
    echo "   Remote: $REMOTE_DIR"
    
    # Use gcloud compute scp with rsync-like behavior
    # Exclude large/unnecessary files
    gcloud compute scp \
        --recurse \
        --zone="$ZONE" \
        --project="$PROJECT_ID" \
        --compress \
        "$LOCAL_DIR" \
        "$VM_NAME:$REMOTE_DIR" \
        2>&1 | tail -5
    
    echo "   ✅ $LABEL synced"
    echo ""
}

# Step 1: Deploy Orchestrator code
echo "🚀 Step 1: Deploying Fields Orchestrator..."
# Create a temp directory with only the needed files (exclude large logs, exports)
TEMP_DIR=$(mktemp -d)
rsync -a \
    --exclude='logs/*.log.*' \
    --exclude='01_Debug_Log/logs/' \
    --exclude='02_Deployment/migration/export_*' \
    --exclude='__pycache__' \
    --exclude='.git' \
    --exclude='*.pyc' \
    "$LOCAL_ORCHESTRATOR/" "$TEMP_DIR/Fields_Orchestrator/"

# Copy cloud config as the active config
cp "$SCRIPT_DIR/../config/settings_cloud.yaml" "$TEMP_DIR/Fields_Orchestrator/config/settings.yaml"

gcloud compute scp \
    --recurse \
    --zone="$ZONE" \
    --project="$PROJECT_ID" \
    --compress \
    "$TEMP_DIR/Fields_Orchestrator" \
    "$VM_NAME:$REMOTE_BASE/" \
    2>&1 | tail -3
rm -rf "$TEMP_DIR"
echo "   ✅ Orchestrator deployed"
echo ""

# Step 2: Deploy Scraping code (only scripts, not data - excludes ~2.8GB of data files)
echo "🚀 Step 2: Deploying Property Data Scraping..."
TEMP_DIR=$(mktemp -d)
rsync -a \
    --exclude='__pycache__' \
    --exclude='.git' \
    --exclude='*.pyc' \
    --exclude='*.log' \
    --exclude='07_Undetectable_method/' \
    --exclude='02_Domain_Scaping/' \
    --exclude='batch_results/' \
    --exclude='listing_results/' \
    --exclude='04_Scrape_All_Domain_Images_Only/' \
    --exclude='20_Depreciated_Files/' \
    --exclude='screenshots/' \
    --exclude='*.json.bak' \
    --exclude='*.csv' \
    --exclude='*.zip' \
    --exclude='*.tar.gz' \
    "$LOCAL_SCRAPING/" "$TEMP_DIR/Property_Data_Scraping/"

gcloud compute scp \
    --recurse \
    --zone="$ZONE" \
    --project="$PROJECT_ID" \
    --compress \
    "$TEMP_DIR/Property_Data_Scraping" \
    "$VM_NAME:$REMOTE_BASE/" \
    2>&1 | tail -3
rm -rf "$TEMP_DIR"
echo "   ✅ Scraping code deployed"
echo ""

# Step 3: Deploy Website backend (enrichment scripts only)
echo "🚀 Step 3: Deploying Website backend scripts..."
TEMP_DIR=$(mktemp -d)
mkdir -p "$TEMP_DIR/Feilds_Website"
# Only sync the backend enrichment directories needed by the orchestrator
for DIR in "03_For_Sale_Coverage" "08_Market_Narrative_Engine" "10_Floor_Plans" "07_Valuation_Comps"; do
    if [ -d "$LOCAL_WEBSITE/$DIR" ]; then
        rsync -a \
            --exclude='__pycache__' \
            --exclude='*.pyc' \
            --exclude='node_modules' \
            "$LOCAL_WEBSITE/$DIR/" "$TEMP_DIR/Feilds_Website/$DIR/"
    fi
done

gcloud compute scp \
    --recurse \
    --zone="$ZONE" \
    --project="$PROJECT_ID" \
    --compress \
    "$TEMP_DIR/Feilds_Website" \
    "$VM_NAME:$REMOTE_BASE/" \
    2>&1 | tail -3
rm -rf "$TEMP_DIR"
echo "   ✅ Website backend deployed"
echo ""

# Step 4: Deploy Valuation code (only production code, not exploration/model dev - excludes ~1.2GB)
echo "🚀 Step 4: Deploying Property Valuation..."
TEMP_DIR=$(mktemp -d)
rsync -a \
    --exclude='__pycache__' \
    --exclude='.git' \
    --exclude='*.pyc' \
    --exclude='*.log' \
    --exclude='venv/' \
    --exclude='01_Exploration/' \
    --exclude='02_House_Plan_Data/' \
    --exclude='03_Model_Development/' \
    --exclude='*.pkl' \
    --exclude='*.joblib' \
    --exclude='*.h5' \
    --exclude='*.parquet' \
    "$LOCAL_VALUATION/" "$TEMP_DIR/Property_Valuation/"

gcloud compute scp \
    --recurse \
    --zone="$ZONE" \
    --project="$PROJECT_ID" \
    --compress \
    "$TEMP_DIR/Property_Valuation" \
    "$VM_NAME:$REMOTE_BASE/" \
    2>&1 | tail -3
rm -rf "$TEMP_DIR"
echo "   ✅ Valuation code deployed"
echo ""

# Step 5: Deploy .env file with Cosmos DB connection string
echo "🔑 Step 5: Deploying environment configuration..."
gcloud compute scp \
    --zone="$ZONE" \
    --project="$PROJECT_ID" \
    "$ENV_FILE" \
    "$VM_NAME:$REMOTE_BASE/Fields_Orchestrator/.env" \
    2>&1 | tail -3
echo "   ✅ Environment config deployed"
echo ""

# Step 6: Set permissions and install Python deps on VM
echo "🔧 Step 6: Setting up on VM..."
gcloud compute ssh "$VM_NAME" \
    --zone="$ZONE" \
    --project="$PROJECT_ID" \
    --command="
        # Fix permissions
        chmod -R 755 /home/fields/Fields_Orchestrator/scripts/ 2>/dev/null || true
        chmod +x /home/fields/Fields_Orchestrator/scripts/*.sh 2>/dev/null || true
        
        # Install Python dependencies
        source /home/fields/venv/bin/activate
        pip install -r /home/fields/Fields_Orchestrator/requirements.txt 2>/dev/null || true
        
        # Set COSMOS_CONNECTION_STRING in bashrc for all sessions
        if ! grep -q 'COSMOS_CONNECTION_STRING' ~/.bashrc; then
            echo '' >> ~/.bashrc
            echo '# Fields Orchestrator - Cosmos DB' >> ~/.bashrc
            echo 'source /home/fields/Fields_Orchestrator/.env 2>/dev/null' >> ~/.bashrc
            echo 'source /home/fields/venv/bin/activate' >> ~/.bashrc
        fi
        
        echo '✅ VM configuration complete'
    "
echo ""

echo "============================================================"
echo "  ✅ DEPLOYMENT COMPLETE"
echo "============================================================"
echo ""
echo "  All code deployed to $VM_NAME"
echo ""
echo "  Next step:"
echo "    cd /Users/projects/Documents/Fields_Orchestrator/02_Deployment && bash gcp/04_start_orchestrator.sh"
echo ""
echo "  To SSH into the VM:"
echo "    gcloud compute ssh $VM_NAME --zone=$ZONE --project=$PROJECT_ID"
echo "============================================================"
