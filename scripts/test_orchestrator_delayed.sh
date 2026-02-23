#!/bin/bash
# Last Updated: 04/02/2026, 2:28 PM (Brisbane Time)
# Test script to trigger orchestrator after a 2-minute delay
# This allows us to verify automatic startup and execution

echo "=========================================="
echo "Fields Orchestrator - Delayed Test Run"
echo "=========================================="
echo "Current Time: $(date '+%Y-%m-%d %H:%M:%S')"
echo "Scheduled Start: $(date -v+2M '+%Y-%m-%d %H:%M:%S')"
echo ""
echo "Waiting 2 minutes before starting orchestrator..."
echo "You can monitor progress in logs/orchestrator.log"
echo ""

# Wait for 2 minutes (120 seconds)
sleep 120

echo ""
echo "=========================================="
echo "Starting Orchestrator NOW!"
echo "Time: $(date '+%Y-%m-%d %H:%M:%S')"
echo "=========================================="
echo ""

# Change to the orchestrator directory and run
cd /Users/projects/Documents/Fields_Orchestrator && python3 src/orchestrator_daemon.py --run-now
