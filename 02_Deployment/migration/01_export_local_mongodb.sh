#!/bin/bash
# ============================================================================
# Export Local MongoDB Data
# Last Edit: 07/02/2026, 6:30 PM (Wednesday) - Brisbane Time
#
# Exports all databases from local MongoDB using mongodump.
# Creates a compressed backup that can be imported into Cosmos DB.
#
# Prerequisites:
#   - Local MongoDB running on 127.0.0.1:27017
#   - mongodump installed (brew install mongodb-database-tools)
#
# Usage:
#   cd /Users/projects/Documents/Fields_Orchestrator/02_Deployment && bash migration/01_export_local_mongodb.sh
# ============================================================================

set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
EXPORT_DIR="$SCRIPT_DIR/export_$(date +%Y%m%d_%H%M%S)"
LOCAL_MONGO_URI="mongodb://127.0.0.1:27017/"

# Databases to export
DATABASES=(
    "property_data"
    "Gold_Coast_Currently_For_Sale"
    "Gold_Coast"
    "Gold_Coast_Recently_Sold"
)

echo "============================================================"
echo "  Local MongoDB Export"
echo "  $(date '+%Y-%m-%d %H:%M:%S') (Brisbane)"
echo "============================================================"
echo ""
echo "  Source: $LOCAL_MONGO_URI"
echo "  Export Dir: $EXPORT_DIR"
echo "  Databases: ${#DATABASES[@]}"
echo ""

# Find mongodump
MONGODUMP=""
for loc in /opt/homebrew/bin/mongodump /usr/local/bin/mongodump /usr/bin/mongodump; do
    if [ -x "$loc" ]; then
        MONGODUMP="$loc"
        break
    fi
done

if [ -z "$MONGODUMP" ]; then
    MONGODUMP=$(which mongodump 2>/dev/null || true)
fi

if [ -z "$MONGODUMP" ]; then
    echo "❌ mongodump not found!"
    echo "   Install with: brew install mongodb-database-tools"
    exit 1
fi

echo "Using mongodump: $MONGODUMP"
echo ""

# Check local MongoDB is running
echo "🔍 Checking local MongoDB..."
if ! mongosh --quiet --eval "db.runCommand({ping:1})" "$LOCAL_MONGO_URI" &>/dev/null; then
    echo "❌ Local MongoDB is not running!"
    echo "   Start it with: brew services start mongodb-community"
    exit 1
fi
echo "   ✅ Local MongoDB is running"
echo ""

# Create export directory
mkdir -p "$EXPORT_DIR"

# Export each database
for DB_NAME in "${DATABASES[@]}"; do
    echo "📦 Exporting database: $DB_NAME"
    
    # Get collection count and document count
    COLL_COUNT=$(mongosh --quiet --eval "db.getCollectionNames().length" "$LOCAL_MONGO_URI$DB_NAME" 2>/dev/null || echo "?")
    echo "   Collections: $COLL_COUNT"
    
    # Export with mongodump (JSON format for Cosmos DB compatibility)
    "$MONGODUMP" \
        --uri="$LOCAL_MONGO_URI" \
        --db="$DB_NAME" \
        --out="$EXPORT_DIR" \
        --gzip \
        2>&1 | while read -r line; do
            echo "   $line"
        done
    
    if [ ${PIPESTATUS[0]} -eq 0 ]; then
        echo "   ✅ Export complete"
    else
        echo "   ❌ Export failed for $DB_NAME"
    fi
    echo ""
done

# Calculate total export size
TOTAL_SIZE=$(du -sh "$EXPORT_DIR" | cut -f1)

echo "============================================================"
echo "  ✅ EXPORT COMPLETE"
echo "============================================================"
echo ""
echo "  Export Directory: $EXPORT_DIR"
echo "  Total Size: $TOTAL_SIZE"
echo ""
echo "  Contents:"
for DB_NAME in "${DATABASES[@]}"; do
    if [ -d "$EXPORT_DIR/$DB_NAME" ]; then
        DB_SIZE=$(du -sh "$EXPORT_DIR/$DB_NAME" | cut -f1)
        FILE_COUNT=$(find "$EXPORT_DIR/$DB_NAME" -name "*.bson.gz" | wc -l | tr -d ' ')
        echo "    📁 $DB_NAME: $DB_SIZE ($FILE_COUNT collections)"
    fi
done
echo ""
echo "  Next Step:"
echo "    cd /Users/projects/Documents/Fields_Orchestrator/02_Deployment && bash migration/02_import_to_cosmos.sh $EXPORT_DIR"
echo ""
echo "  ⚠️  IMPORTANT: Check export size vs Cosmos DB free tier (25 GB)"
echo "============================================================"
