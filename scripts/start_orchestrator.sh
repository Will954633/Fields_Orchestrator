#!/bin/bash
# Start Orchestrator Script
# Last Updated: 26/01/2026, 7:57 PM (Brisbane Time)
#
# Starts the Fields Orchestrator daemon in the background.
# The daemon will run continuously and trigger at 8:30 PM daily.

# Colors for output
GREEN='\033[0;32m'
RED='\033[0;31m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

# Get the directory where this script is located
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
BASE_DIR="$(dirname "$SCRIPT_DIR")"

# Configuration
PID_FILE="/tmp/fields_orchestrator.pid"
LOG_FILE="${BASE_DIR}/logs/orchestrator.log"
PYTHON_SCRIPT="${BASE_DIR}/src/orchestrator_daemon.py"

echo -e "${GREEN}=========================================${NC}"
echo -e "${GREEN}  Fields Orchestrator - Start Script${NC}"
echo -e "${GREEN}=========================================${NC}"

# Check if already running
if [ -f "$PID_FILE" ]; then
    PID=$(cat "$PID_FILE")
    if ps -p "$PID" > /dev/null 2>&1; then
        echo -e "${YELLOW}Orchestrator is already running (PID: $PID)${NC}"
        echo -e "Use ${GREEN}./stop_orchestrator.sh${NC} to stop it first."
        exit 1
    else
        echo -e "${YELLOW}Removing stale PID file...${NC}"
        rm -f "$PID_FILE"
    fi
fi

# Ensure log directory exists
mkdir -p "${BASE_DIR}/logs"
mkdir -p "${BASE_DIR}/state"

# Check if Python script exists
if [ ! -f "$PYTHON_SCRIPT" ]; then
    echo -e "${RED}Error: Python script not found: $PYTHON_SCRIPT${NC}"
    exit 1
fi

# Check for required Python packages
echo -e "${GREEN}Checking dependencies...${NC}"
python3 -c "import yaml, pymongo" 2>/dev/null
if [ $? -ne 0 ]; then
    echo -e "${YELLOW}Installing required packages...${NC}"
    pip3 install pyyaml pymongo
fi

# Start the daemon in the background
echo -e "${GREEN}Starting orchestrator daemon...${NC}"
cd "$BASE_DIR"
nohup python3 "$PYTHON_SCRIPT" >> "$LOG_FILE" 2>&1 &

# Wait a moment for the process to start
sleep 2

# Check if it started successfully
if [ -f "$PID_FILE" ]; then
    PID=$(cat "$PID_FILE")
    if ps -p "$PID" > /dev/null 2>&1; then
        echo -e "${GREEN}✅ Orchestrator started successfully!${NC}"
        echo -e "   PID: $PID"
        echo -e "   Log: $LOG_FILE"
        echo -e ""
        echo -e "The orchestrator will trigger at ${GREEN}8:30 PM${NC} daily."
        echo -e "Use ${GREEN}./stop_orchestrator.sh${NC} to stop it."
        echo -e "Use ${GREEN}./manual_run.sh${NC} to run immediately."
        exit 0
    fi
fi

echo -e "${RED}❌ Failed to start orchestrator${NC}"
echo -e "Check the log file for errors: $LOG_FILE"
exit 1
