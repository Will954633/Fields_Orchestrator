#!/bin/bash
# ============================================================================
# Get Cosmos DB Connection String and Save to .env
# Last Edit: 07/02/2026, 6:49 PM (Wednesday) - Brisbane Time
#
# Retrieves the connection string from Azure and saves it to .env file.
# Uses Python to write the .env to avoid sed issues with special characters
# (the connection string contains &, =, @ which break sed).
#
# Usage:
#   cd /Users/projects/Documents/Fields_Orchestrator/02_Deployment && bash azure/02_get_connection_string.sh
# ============================================================================

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ENV_FILE="$SCRIPT_DIR/../.env"

if [ -f "$ENV_FILE" ]; then
    source "$ENV_FILE"
fi

ACCOUNT_NAME="${COSMOS_ACCOUNT_NAME:-fields-property-cosmos}"
RESOURCE_GROUP="${AZURE_RESOURCE_GROUP:-fields-property-rg}"

echo "🔑 Retrieving Cosmos DB connection string..."
echo "   Account: $ACCOUNT_NAME"
echo "   Resource Group: $RESOURCE_GROUP"
echo ""

# Get connection string
CONNECTION_STRING=$(az cosmosdb keys list \
    --name "$ACCOUNT_NAME" \
    --resource-group "$RESOURCE_GROUP" \
    --type connection-strings \
    --query "connectionStrings[0].connectionString" \
    --output tsv 2>/dev/null)

if [ -z "$CONNECTION_STRING" ]; then
    echo "❌ Failed to retrieve connection string."
    echo "   Make sure the Cosmos DB account exists and you're logged in."
    exit 1
fi

# Use Python to safely write the connection string to .env
# (avoids sed issues with &, =, @ characters in the URI)
python3 -c "
import re
conn_str = '''$CONNECTION_STRING'''
with open('$ENV_FILE', 'r') as f:
    content = f.read()
# Remove any existing COSMOS_CONNECTION_STRING lines
content = re.sub(r'COSMOS_CONNECTION_STRING=.*\n?', '', content)
# Clean up extra blank lines
while '\n\n\n' in content:
    content = content.replace('\n\n\n', '\n\n')
content = content.rstrip() + '\nCOSMOS_CONNECTION_STRING=\"' + conn_str + '\"\n'
with open('$ENV_FILE', 'w') as f:
    f.write(content)
"

echo "✅ Connection string saved to .env"
echo ""
echo "Connection String:"
echo "  ${CONNECTION_STRING:0:80}..."
echo ""
echo "Next Steps:"
echo "  1. Test connection: cd /Users/projects/Documents/Fields_Orchestrator/02_Deployment && python3 scripts/test_cosmos_connection.py"
echo "  2. Create indexes:  cd /Users/projects/Documents/Fields_Orchestrator/02_Deployment && python3 azure/03_create_indexes.py"
