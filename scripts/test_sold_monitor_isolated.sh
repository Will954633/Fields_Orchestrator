#!/bin/bash
# Test Sold Monitor in Isolation on VM
# Last Updated: 12/02/2026, 10:08 AM (Wednesday) - Brisbane Time
#
# Description: Runs the sold monitor script in isolation on the VM to test
# under exact production conditions. Captures all output for error analysis.
#
# Usage: Run this script on the VM via SSH

set -e

echo "============================================================"
echo "SOLD MONITOR ISOLATED TEST"
echo "============================================================"
echo "Started: $(date)"
echo "Environment: VM Production"
echo "Mode: Test (first 10 properties per suburb)"
echo "============================================================"
echo ""

# Change to scraping directory
cd /home/fields/Property_Data_Scraping/03_Gold_Coast/Gold_Coast_Wide_Currently_For_Sale_AND_Recently_Sold

# Create logs directory if it doesn't exist
mkdir -p logs

# Set log file with timestamp
LOG_FILE="logs/sold_monitor_isolated_test_$(date +%Y%m%d_%H%M%S).log"

echo "Log file: $LOG_FILE"
echo ""

# Run the sold monitor in test mode
# --test: Only process first 10 properties per suburb
# --max-concurrent 2: Run 2 suburbs at a time (conservative for testing)
# --parallel-properties 1: Process properties sequentially (safer for testing)
echo "Running sold monitor..."
python3 -u monitor_sold_properties.py \
    --test \
    --max-concurrent 2 \
    --parallel-properties 1 \
    2>&1 | tee "$LOG_FILE"

EXIT_CODE=${PIPESTATUS[0]}

echo ""
echo "============================================================"
echo "TEST COMPLETE"
echo "============================================================"
echo "Finished: $(date)"
echo "Exit code: $EXIT_CODE"
echo "Log file: $LOG_FILE"
echo ""

# Check for errors in log
if grep -qi "error\|exception\|failed\|traceback" "$LOG_FILE"; then
    echo "⚠️  ERRORS DETECTED - Check log file for details"
    echo ""
    echo "Last 50 lines of log:"
    tail -50 "$LOG_FILE"
    exit 1
else
    echo "✅ NO ERRORS DETECTED"
    exit 0
fi
