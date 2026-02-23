#!/bin/bash
# ============================================================================
# Azure Cosmos DB Setup Script (MongoDB API)
# Last Edit: 07/02/2026, 6:26 PM (Wednesday) - Brisbane Time
#
# This script creates an Azure Cosmos DB account with MongoDB API compatibility.
# It uses the FREE TIER (1000 RU/s + 25 GB storage).
#
# Prerequisites:
#   - Azure CLI installed: brew install azure-cli
#   - Logged in: az login
#   - Subscription set: az account set --subscription <id>
#
# Usage:
#   cd /Users/projects/Documents/Fields_Orchestrator/02_Deployment && bash azure/01_setup_cosmos_db.sh
# ============================================================================

set -e

# Load environment variables
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ENV_FILE="$SCRIPT_DIR/../.env"

if [ -f "$ENV_FILE" ]; then
    source "$ENV_FILE"
else
    echo "⚠️  .env file not found. Creating from template..."
    cp "$SCRIPT_DIR/../.env.template" "$ENV_FILE"
    echo "📝 Please edit $ENV_FILE with your values, then re-run this script."
    exit 1
fi

# Configuration
SUBSCRIPTION_ID="${AZURE_SUBSCRIPTION_ID}"
RESOURCE_GROUP="${AZURE_RESOURCE_GROUP:-fields-property-rg}"
REGION="${AZURE_REGION:-australiaeast}"
ACCOUNT_NAME="${COSMOS_ACCOUNT_NAME:-fields-property-cosmos}"

echo "============================================================"
echo "  Azure Cosmos DB Setup - Fields Property Data"
echo "============================================================"
echo ""
echo "  Subscription:    $SUBSCRIPTION_ID"
echo "  Resource Group:  $RESOURCE_GROUP"
echo "  Region:          $REGION"
echo "  Account Name:    $ACCOUNT_NAME"
echo "  API:             MongoDB (v4.2)"
echo "  Tier:            Free Tier (1000 RU/s, 25 GB)"
echo ""
echo "============================================================"
echo ""

# Step 0: Check Azure CLI is installed and logged in
echo "🔍 Step 0: Checking Azure CLI..."
if ! command -v az &> /dev/null; then
    echo "❌ Azure CLI not found. Install with: brew install azure-cli"
    exit 1
fi

# Check if logged in
if ! az account show &> /dev/null; then
    echo "❌ Not logged in to Azure. Run: az login"
    exit 1
fi

# Set subscription
echo "   Setting subscription..."
az account set --subscription "$SUBSCRIPTION_ID"
echo "   ✅ Subscription set"

# Register Microsoft.DocumentDB provider (required for Cosmos DB)
echo "   Registering Microsoft.DocumentDB provider..."
REG_STATE=$(az provider show --namespace Microsoft.DocumentDB --query "registrationState" --output tsv 2>/dev/null)
if [ "$REG_STATE" != "Registered" ]; then
    az provider register --namespace Microsoft.DocumentDB 2>/dev/null
    echo "   ⏳ Waiting for provider registration (this can take 1-3 minutes)..."
    while [ "$(az provider show --namespace Microsoft.DocumentDB --query 'registrationState' --output tsv 2>/dev/null)" != "Registered" ]; do
        sleep 10
        echo "   ... still registering"
    done
fi
echo "   ✅ Microsoft.DocumentDB provider registered"
echo ""

# Step 1: Create Resource Group
echo "🔧 Step 1: Creating Resource Group '$RESOURCE_GROUP'..."
if az group show --name "$RESOURCE_GROUP" &> /dev/null; then
    echo "   ℹ️  Resource group already exists"
else
    az group create \
        --name "$RESOURCE_GROUP" \
        --location "$REGION" \
        --tags "project=fields-estate" "environment=production"
    echo "   ✅ Resource group created"
fi
echo ""

# Step 2: Create Cosmos DB Account with MongoDB API (Free Tier)
echo "🔧 Step 2: Creating Cosmos DB Account '$ACCOUNT_NAME'..."
echo "   ⏳ This may take 5-10 minutes..."

if az cosmosdb show --name "$ACCOUNT_NAME" --resource-group "$RESOURCE_GROUP" &> /dev/null; then
    echo "   ℹ️  Cosmos DB account already exists"
else
    az cosmosdb create \
        --name "$ACCOUNT_NAME" \
        --resource-group "$RESOURCE_GROUP" \
        --kind MongoDB \
        --server-version "4.2" \
        --locations regionName="$REGION" failoverPriority=0 isZoneRedundant=false \
        --default-consistency-level "Session" \
        --enable-free-tier true \
        --enable-automatic-failover false \
        --tags "project=fields-estate" "environment=production"
    echo "   ✅ Cosmos DB account created with FREE TIER"
fi
echo ""

# Step 3: Create Databases
echo "🔧 Step 3: Creating Databases..."

DATABASES=(
    "property_data"
    "Gold_Coast_Currently_For_Sale"
    "Gold_Coast"
    "Gold_Coast_Recently_Sold"
)

for DB_NAME in "${DATABASES[@]}"; do
    echo "   Creating database: $DB_NAME"
    if az cosmosdb mongodb database show \
        --account-name "$ACCOUNT_NAME" \
        --resource-group "$RESOURCE_GROUP" \
        --name "$DB_NAME" &> /dev/null; then
        echo "   ℹ️  Database '$DB_NAME' already exists"
    else
        az cosmosdb mongodb database create \
            --account-name "$ACCOUNT_NAME" \
            --resource-group "$RESOURCE_GROUP" \
            --name "$DB_NAME"
        echo "   ✅ Database '$DB_NAME' created"
    fi
done
echo ""

# Step 4: Get and display connection string
echo "🔑 Step 4: Retrieving Connection String..."
CONNECTION_STRING=$(az cosmosdb keys list \
    --name "$ACCOUNT_NAME" \
    --resource-group "$RESOURCE_GROUP" \
    --type connection-strings \
    --query "connectionStrings[0].connectionString" \
    --output tsv)

echo ""
echo "============================================================"
echo "  ✅ SETUP COMPLETE!"
echo "============================================================"
echo ""
echo "  Connection String (save this!):"
echo "  $CONNECTION_STRING"
echo ""
echo "  Databases Created:"
for DB_NAME in "${DATABASES[@]}"; do
    echo "    - $DB_NAME"
done
echo ""
echo "  Next Steps:"
echo "    1. Run: bash azure/02_get_connection_string.sh"
echo "       (saves connection string to .env)"
echo "    2. Run: python3 scripts/test_cosmos_connection.py"
echo "       (tests connectivity)"
echo "    3. Run: python3 azure/03_create_indexes.py"
echo "       (creates indexes for performance)"
echo ""
echo "  Azure Portal:"
echo "    https://portal.azure.com/#@/resource/subscriptions/$SUBSCRIPTION_ID/resourceGroups/$RESOURCE_GROUP/providers/Microsoft.DocumentDB/databaseAccounts/$ACCOUNT_NAME"
echo ""
echo "  ⚠️  IMPORTANT: Free Tier Limits"
echo "    - 1000 RU/s throughput (shared across all databases)"
echo "    - 25 GB storage total"
echo "    - Monitor usage in Azure Portal → Metrics"
echo "============================================================"
