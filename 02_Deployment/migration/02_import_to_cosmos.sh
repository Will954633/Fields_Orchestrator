#!/bin/bash
# ============================================================================
# Import Data to Azure Cosmos DB
# Last Edit: 07/02/2026, 6:31 PM (Wednesday) - Brisbane Time
#
# Imports mongodump export into Azure Cosmos DB using mongorestore.
# 
# IMPORTANT: Cosmos DB has rate limiting (1000 RU/s on free tier).
# This script uses --numInsertionWorkersPerCollection=1 to avoid
# overwhelming the free tier with too many concurrent writes.
#
# Prerequisites:
#   - mongorestore installed (brew install mongodb-database-tools)
#   - .env file with COSMOS_CONNECTION_STRING set
#   - Export directory from 01_export_local_mongodb.sh
#
# Usage:
#   cd /Users/projects/Documents/Fields_Orchestrator/02_Deployment && bash migration/02_import_to_cosmos.sh [export_dir]
# ============================================================================

set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ENV_FILE="$SCRIPT_DIR/../.env"

# Load environment
if [ ! -f "$ENV_FILE" ]; then
    echo "❌ .env file not found. Run azure setup scripts first."
    exit 1
fi
source "$ENV_FILE"

# Get export directory from argument or find latest
if [ -n "$1" ]; then
    EXPORT_DIR="$1"
else
    # Find the latest export directory
    EXPORT_DIR=$(ls -dt "$SCRIPT_DIR"/export_* 2>/dev/null | head -1)
    if [ -z "$EXPORT_DIR" ]; then
        echo "❌ No export directory found."
        echo "   Run: cd /Users/projects/Documents/Fields_Orchestrator/02_Deployment && bash migration/01_export_local_mongodb.sh"
        echo "   Or specify: bash migration/02_import_to_cosmos.sh /path/to/export_dir"
        exit 1
    fi
fi

if [ ! -d "$EXPORT_DIR" ]; then
    echo "❌ Export directory not found: $EXPORT_DIR"
    exit 1
fi

COSMOS_URI="${COSMOS_CONNECTION_STRING}"
if [ -z "$COSMOS_URI" ]; then
    echo "❌ COSMOS_CONNECTION_STRING not set in .env"
    exit 1
fi

# Databases to import
DATABASES=(
    "property_data"
    "Gold_Coast_Currently_For_Sale"
    "Gold_Coast"
    "Gold_Coast_Recently_Sold"
)

echo "============================================================"
echo "  Import to Azure Cosmos DB"
echo "  $(date '+%Y-%m-%d %H:%M:%S') (Brisbane)"
echo "============================================================"
echo ""
echo "  Source: $EXPORT_DIR"
echo "  Target: Azure Cosmos DB (fields-property-cosmos)"
echo "  Databases: ${#DATABASES[@]}"
echo ""
echo "  ⚠️  This may take a while due to Cosmos DB rate limiting."
echo "  ⚠️  Free tier: 1000 RU/s - imports are throttled to avoid 429 errors."
echo ""

# Find mongorestore
MONGORESTORE=""
for loc in /opt/homebrew/bin/mongorestore /usr/local/bin/mongorestore /usr/bin/mongorestore; do
    if [ -x "$loc" ]; then
        MONGORESTORE="$loc"
        break
    fi
done

if [ -z "$MONGORESTORE" ]; then
    MONGORESTORE=$(which mongorestore 2>/dev/null || true)
fi

if [ -z "$MONGORESTORE" ]; then
    echo "❌ mongorestore not found!"
    echo "   Install with: brew install mongodb-database-tools"
    exit 1
fi

echo "Using mongorestore: $MONGORESTORE"
echo ""

# Import each database
TOTAL_START=$(date +%s)

for DB_NAME in "${DATABASES[@]}"; do
    DB_DIR="$EXPORT_DIR/$DB_NAME"
    
    if [ ! -d "$DB_DIR" ]; then
        echo "⚠️  Skipping $DB_NAME - export directory not found"
        continue
    fi
    
    FILE_COUNT=$(find "$DB_DIR" -name "*.bson.gz" 2>/dev/null | wc -l | tr -d ' ')
    DB_SIZE=$(du -sh "$DB_DIR" | cut -f1)
    
    echo "📦 Importing database: $DB_NAME ($FILE_COUNT collections, $DB_SIZE)"
    echo "   Started: $(date '+%H:%M:%S')"
    
    DB_START=$(date +%s)
    
    # mongorestore with Cosmos DB compatible settings
    # --numInsertionWorkersPerCollection=1 prevents RU throttling
    # --bypassDocumentValidation for Cosmos DB compatibility
    # --gzip because we exported with --gzip
    "$MONGORESTORE" \
        --uri="$COSMOS_URI" \
        --db="$DB_NAME" \
        --dir="$DB_DIR" \
        --gzip \
        --numInsertionWorkersPerCollection=1 \
        --bypassDocumentValidation \
        --drop \
        2>&1 | while read -r line; do
            # Filter out progress lines to reduce noise
            if echo "$line" | grep -qE "(done|error|fail|warning|restoring)" ; then
                echo "   $line"
            fi
        done
    
    RESTORE_EXIT=${PIPESTATUS[0]}
    DB_END=$(date +%s)
    DB_ELAPSED=$((DB_END - DB_START))
    
    if [ $RESTORE_EXIT -eq 0 ]; then
        echo "   ✅ Import complete (${DB_ELAPSED}s)"
    else
        echo "   ❌ Import failed for $DB_NAME (exit code: $RESTORE_EXIT)"
        echo "   💡 If you see 429 errors, wait a few minutes and retry."
        echo "      Cosmos DB free tier may need time to recover RU budget."
    fi
    
    # Brief pause between databases to let Cosmos DB recover RU budget
    echo "   ⏳ Pausing 30s to let Cosmos DB recover RU budget..."
    sleep 30
    echo ""
done

TOTAL_END=$(date +%s)
TOTAL_ELAPSED=$((TOTAL_END - TOTAL_START))
TOTAL_MINUTES=$((TOTAL_ELAPSED / 60))

echo "============================================================"
echo "  ✅ IMPORT COMPLETE"
echo "============================================================"
echo ""
echo "  Total Time: ${TOTAL_MINUTES} minutes (${TOTAL_ELAPSED}s)"
echo ""
echo "  Next Step:"
echo "    cd /Users/projects/Documents/Fields_Orchestrator/02_Deployment && python3 migration/03_verify_migration.py"
echo ""
echo "  Then create indexes:"
echo "    cd /Users/projects/Documents/Fields_Orchestrator/02_Deployment && python3 azure/03_create_indexes.py"
echo "============================================================"
