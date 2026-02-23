#!/bin/bash
# Stop Orchestrator Script
# Last Updated: 26/01/2026, 7:57 PM (Brisbane Time)
#
# Gracefully stops the Fields Orchestrator daemon.

# Colors for output
GREEN='\033[0;32m'
RED='\033[0;31m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

# Configuration
PID_FILE="/tmp/fields_orchestrator.pid"
LOCK_FILE="/tmp/fields_orchestrator.lock"

echo -e "${GREEN}=========================================${NC}"
echo -e "${GREEN}  Fields Orchestrator - Stop Script${NC}"
echo -e "${GREEN}=========================================${NC}"

# Check if PID file exists
if [ ! -f "$PID_FILE" ]; then
    echo -e "${YELLOW}Orchestrator is not running (no PID file found)${NC}"
    
    # Clean up lock file if it exists
    if [ -f "$LOCK_FILE" ]; then
        rm -f "$LOCK_FILE"
        echo -e "${GREEN}Cleaned up stale lock file${NC}"
    fi
    exit 0
fi

# Get the PID
PID=$(cat "$PID_FILE")

# Check if process is running
if ! ps -p "$PID" > /dev/null 2>&1; then
    echo -e "${YELLOW}Orchestrator process not found (PID: $PID)${NC}"
    echo -e "${GREEN}Cleaning up PID and lock files...${NC}"
    rm -f "$PID_FILE" "$LOCK_FILE"
    exit 0
fi

echo -e "${GREEN}Stopping orchestrator (PID: $PID)...${NC}"

# Send SIGTERM for graceful shutdown
kill -TERM "$PID" 2>/dev/null

# Wait for process to stop (up to 30 seconds)
TIMEOUT=30
COUNTER=0
while ps -p "$PID" > /dev/null 2>&1; do
    if [ $COUNTER -ge $TIMEOUT ]; then
        echo -e "${YELLOW}Process did not stop gracefully. Forcing...${NC}"
        kill -9 "$PID" 2>/dev/null
        break
    fi
    sleep 1
    ((COUNTER++))
    echo -ne "\rWaiting for shutdown... ${COUNTER}s"
done
echo ""

# Clean up files
rm -f "$PID_FILE" "$LOCK_FILE"

# Verify process stopped
if ps -p "$PID" > /dev/null 2>&1; then
    echo -e "${RED}❌ Failed to stop orchestrator${NC}"
    exit 1
else
    echo -e "${GREEN}✅ Orchestrator stopped successfully${NC}"
    exit 0
fi
