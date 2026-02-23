#!/bin/bash
# ============================================================================
# Setup Google Cloud VM - Install Dependencies
# Last Edit: 07/02/2026, 6:33 PM (Wednesday) - Brisbane Time
#
# Runs on the GCP VM via SSH to install all required dependencies:
# - Python 3.11+, pip, venv
# - Chrome/Chromium + ChromeDriver (for Selenium scraping)
# - Ollama (for LLaVA photo/floor plan analysis)
# - MongoDB tools (mongodump/mongorestore for backups)
# - System utilities
#
# Usage (from local machine):
#   cd /Users/projects/Documents/Fields_Orchestrator/02_Deployment && bash gcp/02_setup_vm.sh
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
echo "  GCP VM Setup - Installing Dependencies"
echo "============================================================"
echo ""
echo "  VM: $VM_NAME ($ZONE)"
echo "  This will SSH into the VM and install everything needed."
echo ""
echo "============================================================"
echo ""

# Create the setup script that will run ON the VM
SETUP_SCRIPT=$(cat << 'REMOTE_SCRIPT'
#!/bin/bash
set -e

echo "============================================================"
echo "  Fields Orchestrator VM Setup"
echo "  $(date '+%Y-%m-%d %H:%M:%S')"
echo "============================================================"

# Create fields user directory
sudo mkdir -p /home/fields
sudo chown $(whoami):$(whoami) /home/fields

# ============================================================
# 1. System Updates
# ============================================================
echo ""
echo "📦 Step 1: System updates..."
sudo apt-get update -y
sudo apt-get upgrade -y
echo "   ✅ System updated"

# ============================================================
# 2. Python 3.11+
# ============================================================
echo ""
echo "🐍 Step 2: Installing Python..."
sudo apt-get install -y python3 python3-pip python3-venv python3-dev
python3 --version
echo "   ✅ Python installed"

# ============================================================
# 3. Chrome/Chromium for Selenium
# ============================================================
echo ""
echo "🌐 Step 3: Installing Chrome..."
sudo apt-get install -y chromium-browser chromium-chromedriver
# Also install dependencies for headless Chrome
sudo apt-get install -y \
    libnss3 libatk1.0-0 libatk-bridge2.0-0 libcups2 \
    libxkbcommon0 libxcomposite1 libxdamage1 libxrandr2 \
    libgbm1 libpango-1.0-0 libcairo2 libasound2 \
    fonts-liberation xdg-utils
echo "   Chrome version: $(chromium-browser --version 2>/dev/null || echo 'installed')"
echo "   ✅ Chrome installed"

# ============================================================
# 4. Ollama (for LLaVA model)
# ============================================================
echo ""
echo "🤖 Step 4: Installing Ollama..."
curl -fsSL https://ollama.com/install.sh | sh
# Start Ollama service
sudo systemctl enable ollama
sudo systemctl start ollama
# Wait for Ollama to be ready
sleep 5
# Pull LLaVA model (used for photo and floor plan analysis)
echo "   Pulling LLaVA model (this may take 10-15 minutes)..."
ollama pull llava:7b || echo "   ⚠️  LLaVA pull failed - retry manually: ollama pull llava:7b"
echo "   ✅ Ollama installed"

# ============================================================
# 5. MongoDB Database Tools (for backup/restore)
# ============================================================
echo ""
echo "🔧 Step 5: Installing MongoDB tools..."
# Import MongoDB public GPG key
curl -fsSL https://www.mongodb.org/static/pgp/server-7.0.asc | \
    sudo gpg --dearmor -o /usr/share/keyrings/mongodb-server-7.0.gpg 2>/dev/null || true
# Add MongoDB repo
echo "deb [ signed-by=/usr/share/keyrings/mongodb-server-7.0.gpg ] https://repo.mongodb.org/apt/ubuntu jammy/mongodb-org/7.0 multiverse" | \
    sudo tee /etc/apt/sources.list.d/mongodb-org-7.0.list
sudo apt-get update -y
sudo apt-get install -y mongodb-database-tools || {
    echo "   ⚠️  MongoDB tools from repo failed, trying direct download..."
    wget -q https://fastdl.mongodb.org/tools/db/mongodb-database-tools-ubuntu2204-x86_64-100.9.0.deb -O /tmp/mongo-tools.deb
    sudo dpkg -i /tmp/mongo-tools.deb || sudo apt-get install -f -y
}
echo "   mongodump version: $(mongodump --version 2>/dev/null | head -1 || echo 'installed')"
echo "   ✅ MongoDB tools installed"

# ============================================================
# 6. Additional utilities
# ============================================================
echo ""
echo "🔧 Step 6: Installing utilities..."
sudo apt-get install -y \
    git \
    jq \
    htop \
    tmux \
    unzip \
    curl \
    wget \
    rsync
echo "   ✅ Utilities installed"

# ============================================================
# 7. Set timezone to Brisbane
# ============================================================
echo ""
echo "🕐 Step 7: Setting timezone..."
sudo timedatectl set-timezone Australia/Brisbane
echo "   Timezone: $(timedatectl show --property=Timezone --value)"
echo "   ✅ Timezone set to Brisbane"

# ============================================================
# 8. Create directory structure
# ============================================================
echo ""
echo "📁 Step 8: Creating directory structure..."
mkdir -p /home/fields/Fields_Orchestrator/logs
mkdir -p /home/fields/Fields_Orchestrator/state
mkdir -p /home/fields/Property_Data_Scraping
mkdir -p /home/fields/Feilds_Website
mkdir -p /home/fields/Property_Valuation
mkdir -p /home/fields/backups
echo "   ✅ Directories created"

# ============================================================
# 9. Create Python virtual environment
# ============================================================
echo ""
echo "🐍 Step 9: Creating Python virtual environment..."
python3 -m venv /home/fields/venv
source /home/fields/venv/bin/activate
pip install --upgrade pip
pip install pymongo PyYAML selenium requests beautifulsoup4 Pillow
echo "   ✅ Virtual environment created"

# ============================================================
# Summary
# ============================================================
echo ""
echo "============================================================"
echo "  ✅ VM SETUP COMPLETE"
echo "============================================================"
echo ""
echo "  Python:     $(python3 --version)"
echo "  Chrome:     $(chromium-browser --version 2>/dev/null || echo 'installed')"
echo "  Ollama:     $(ollama --version 2>/dev/null || echo 'installed')"
echo "  mongodump:  $(mongodump --version 2>/dev/null | head -1 || echo 'installed')"
echo "  Timezone:   $(timedatectl show --property=Timezone --value)"
echo ""
echo "  Next: Deploy code with gcp/03_deploy_code.sh"
echo "============================================================"
REMOTE_SCRIPT
)

# Execute the setup script on the VM via SSH
echo "🚀 Connecting to VM and running setup..."
echo ""

gcloud compute ssh "$VM_NAME" \
    --zone="$ZONE" \
    --project="$PROJECT_ID" \
    --command="$SETUP_SCRIPT"

echo ""
echo "✅ VM setup complete!"
echo ""
echo "Next step:"
echo "  cd /Users/projects/Documents/Fields_Orchestrator/02_Deployment && bash gcp/03_deploy_code.sh"
