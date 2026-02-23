#!/bin/bash
# Manual Run Script
# Last Updated: 26/01/2026, 7:57 PM (Brisbane Time)
# Last Updated: 28/01/2026, 6:36 PM (Wednesday) - Brisbane
# - Note: orchestrator now writes `state/current_run_candidates.json` and `state/last_run_summary.json`
# - Note: orchestrator may update MongoDB docs with `orchestrator.*` verification/history fields
#
# Manually triggers the property data collection pipeline immediately.
# This bypasses the scheduled 8:30 PM trigger time.

# Colors for output
GREEN='\033[0;32m'
RED='\033[0;31m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

# Get the directory where this script is located
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
BASE_DIR="$(dirname "$SCRIPT_DIR")"

# Configuration
PYTHON_SCRIPT="${BASE_DIR}/src/orchestrator_daemon.py"
LOG_FILE="${BASE_DIR}/logs/orchestrator.log"

echo -e "${GREEN}=========================================${NC}"
echo -e "${GREEN}  Fields Orchestrator - Manual Run${NC}"
echo -e "${GREEN}=========================================${NC}"
echo ""
echo -e "${YELLOW}⚠️  WARNING: This will start the full data collection pipeline.${NC}"
echo -e "${YELLOW}   This process requires full browser mode and will take 2-3 hours.${NC}"
echo -e "${YELLOW}   You will not be able to use the computer during scraping steps.${NC}"
echo -e "${YELLOW}   It will also write run artifacts to: state/current_run_candidates.json and state/last_run_summary.json${NC}"
echo ""

# Ask for confirmation
read -p "Are you sure you want to start the pipeline now? (y/N): " -n 1 -r
echo ""

if [[ ! $REPLY =~ ^[Yy]$ ]]; then
    echo -e "${BLUE}Cancelled.${NC}"
    exit 0
fi

# Check if Python script exists
if [ ! -f "$PYTHON_SCRIPT" ]; then
    echo -e "${RED}Error: Python script not found: $PYTHON_SCRIPT${NC}"
    exit 1
fi

# Ensure directories exist
mkdir -p "${BASE_DIR}/logs"
mkdir -p "${BASE_DIR}/state"

# Check for required Python packages
echo -e "${GREEN}Checking dependencies...${NC}"
python3 -c "import yaml, pymongo" 2>/dev/null
if [ $? -ne 0 ]; then
    echo -e "${YELLOW}Installing required packages...${NC}"
    pip3 install pyyaml pymongo
fi

echo ""
echo -e "${GREEN}Starting manual pipeline run...${NC}"
echo -e "${BLUE}Log file: $LOG_FILE${NC}"
echo ""

# Run the pipeline with --run-now flag
cd "$BASE_DIR"
python3 "$PYTHON_SCRIPT" --run-now

echo ""
echo -e "${GREEN}=========================================${NC}"
echo -e "${GREEN}  Manual run complete${NC}"
echo -e "${GREEN}=========================================${NC}"
