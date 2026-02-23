#!/bin/bash
# Test Debug System
# Last Updated: 05/02/2026, 8:31 AM (Wednesday) - Brisbane
#
# This script tests the debug logging system by:
# 1. Finding the most recent orchestrator run
# 2. Running debug checks on that data
# 3. Displaying results

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

# Get the directory where this script is located
SCRIPT_DIR="$( cd "$( dirname "${BASH_SOURCE[0]}" )" && pwd )"
PROJECT_DIR="$( cd "$SCRIPT_DIR/.." && pwd )"

echo -e "${BLUE}=========================================="
echo "Debug Logging System Test"
echo -e "==========================================${NC}"
echo ""

cd "$PROJECT_DIR" || exit 1

# Try to get the most recent run ID from state files
echo -e "${YELLOW}Looking for recent orchestrator run data...${NC}"
echo ""

# Check if we have any sold properties with run_id
RUN_ID=$(python3 -c "
from pymongo import MongoClient
from datetime import datetime
try:
    client = MongoClient('mongodb://127.0.0.1:27017/', serverSelectionTimeoutMS=5000)
    db = client['property_data']
    
    # Try to find most recent sold property with a run_id
    sold = db['properties_sold'].find_one(
        {'orchestrator.migrated_to_sold.run_id': {'\$exists': True}},
        sort=[('orchestrator.migrated_to_sold.at', -1)]
    )
    
    if sold:
        run_id = sold['orchestrator']['migrated_to_sold']['run_id']
        print(run_id)
    else:
        # Generate a test run ID based on current time
        print(datetime.now().strftime('%Y%m%d_%H%M%S'))
except Exception as e:
    # Generate a test run ID based on current time
    print(datetime.now().strftime('%Y%m%d_%H%M%S'))
" 2>/dev/null)

if [ -z "$RUN_ID" ]; then
    echo -e "${RED}Error: Could not determine run ID${NC}"
    echo ""
    echo "Please provide a run ID manually:"
    echo "  ./01_Debug_Log/run_checks.sh <RUN_ID>"
    exit 1
fi

echo -e "${GREEN}Found run ID: $RUN_ID${NC}"
echo ""

# Check MongoDB connection
echo -e "${YELLOW}Testing MongoDB connection...${NC}"
python3 -c "
from pymongo import MongoClient
try:
    client = MongoClient('mongodb://127.0.0.1:27017/', serverSelectionTimeoutMS=5000)
    client.admin.command('ping')
    print('✅ MongoDB connection successful')
except Exception as e:
    print(f'❌ MongoDB connection failed: {e}')
    exit(1)
"

if [ $? -ne 0 ]; then
    echo -e "${RED}Cannot proceed without MongoDB connection${NC}"
    exit 1
fi

echo ""

# Get some statistics
echo -e "${YELLOW}Current database statistics:${NC}"
python3 -c "
from pymongo import MongoClient
try:
    client = MongoClient('mongodb://127.0.0.1:27017/', serverSelectionTimeoutMS=5000)
    db = client['property_data']
    
    for_sale_count = db['properties_for_sale'].count_documents({})
    sold_count = db['properties_sold'].count_documents({})
    
    # Count properties with gold_coast_doc_id
    matched_count = db['properties_for_sale'].count_documents({
        'orchestrator.gold_coast_doc_id': {'\$exists': True, '\$ne': None}
    })
    
    print(f'  Properties for sale: {for_sale_count}')
    print(f'  Properties sold: {sold_count}')
    print(f'  Matched to static records: {matched_count}/{for_sale_count}')
    
    if for_sale_count > 0:
        match_rate = (matched_count / for_sale_count) * 100
        print(f'  Match rate: {match_rate:.1f}%')
except Exception as e:
    print(f'Error getting statistics: {e}')
"

echo ""
echo -e "${BLUE}=========================================="
echo "Running Debug Checks"
echo -e "==========================================${NC}"
echo ""

# Run the debug checks
./01_Debug_Log/run_checks.sh "$RUN_ID"

EXIT_CODE=$?

echo ""
echo -e "${BLUE}=========================================="
echo "Test Complete"
echo -e "==========================================${NC}"
echo ""

if [ $EXIT_CODE -eq 0 ]; then
    echo -e "${GREEN}✅ Debug system is working correctly!${NC}"
    echo ""
    echo "Next steps:"
    echo "  1. Review the integrity report in: 01_Debug_Log/logs/"
    echo "  2. Check orchestrator logs: logs/orchestrator.log"
    echo "  3. Run a full orchestrator test when ready"
else
    echo -e "${YELLOW}⚠️  Debug checks completed with warnings/errors${NC}"
    echo ""
    echo "This is normal if:"
    echo "  - No properties were sold in this run"
    echo "  - No new listings were added in this run"
    echo "  - Some properties couldn't be matched (new construction)"
    echo ""
    echo "Review the logs for details:"
    echo "  - Integrity reports: 01_Debug_Log/logs/"
    echo "  - Orchestrator log: logs/orchestrator.log"
fi

echo ""
echo -e "${BLUE}To run debug checks manually:${NC}"
echo "  ./01_Debug_Log/run_checks.sh <RUN_ID>"
echo ""

exit $EXIT_CODE
