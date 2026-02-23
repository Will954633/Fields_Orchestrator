#!/bin/bash
# Helper script to run debug checks for Fields Orchestrator
# Last Updated: 05/02/2026, 8:20 AM (Wednesday) - Brisbane

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

# Get the directory where this script is located
SCRIPT_DIR="$( cd "$( dirname "${BASH_SOURCE[0]}" )" && pwd )"
PROJECT_DIR="$( cd "$SCRIPT_DIR/.." && pwd )"

echo "=========================================="
echo "Fields Orchestrator Debug Checks"
echo "=========================================="
echo ""

# Check if run-id is provided
if [ -z "$1" ]; then
    echo -e "${RED}Error: Run ID is required${NC}"
    echo ""
    echo "Usage: $0 <RUN_ID> [OPTIONS]"
    echo ""
    echo "Examples:"
    echo "  $0 20260205_081900                    # Run all checks"
    echo "  $0 20260205_081900 --match-only       # Only run static record matching"
    echo "  $0 20260205_081900 --verify-only      # Only run integrity verification"
    echo "  $0 20260205_081900 --match-all        # Match all unmatched properties"
    echo ""
    exit 1
fi

RUN_ID="$1"
MODE="${2:-all}"

echo "Run ID: $RUN_ID"
echo "Mode: $MODE"
echo ""

# Change to project directory
cd "$PROJECT_DIR" || exit 1

case "$MODE" in
    --match-only)
        echo "Running static record matching only..."
        python3 01_Debug_Log/static_record_matcher.py --run-id "$RUN_ID" --mode new
        ;;
    
    --match-all)
        echo "Running static record matching for ALL unmatched properties..."
        python3 01_Debug_Log/static_record_matcher.py --run-id "$RUN_ID" --mode all
        ;;
    
    --verify-only)
        echo "Running data integrity verification only..."
        python3 01_Debug_Log/data_integrity_monitor.py --run-id "$RUN_ID"
        ;;
    
    *)
        echo "Running all debug checks..."
        python3 01_Debug_Log/run_debug_checks.py --run-id "$RUN_ID"
        ;;
esac

EXIT_CODE=$?

echo ""
echo "=========================================="
if [ $EXIT_CODE -eq 0 ]; then
    echo -e "${GREEN}✅ Debug checks completed successfully${NC}"
else
    echo -e "${RED}❌ Debug checks completed with errors${NC}"
    echo -e "${YELLOW}Review logs for details:${NC}"
    echo "  - Orchestrator log: logs/orchestrator.log"
    echo "  - Integrity reports: 01_Debug_Log/logs/"
fi
echo "=========================================="

exit $EXIT_CODE
