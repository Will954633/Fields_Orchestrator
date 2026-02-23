#!/bin/bash
# Last Updated: 04/02/2026, 2:28 PM (Brisbane Time)
# Monitor script to watch orchestrator logs during test run

echo "=========================================="
echo "Monitoring Orchestrator Logs"
echo "=========================================="
echo "Current Time: $(date '+%Y-%m-%d %H:%M:%S')"
echo "Orchestrator will start at: 2026-02-04 14:30:26"
echo ""
echo "Watching logs/orchestrator.log..."
echo "Press Ctrl+C to stop monitoring"
echo "=========================================="
echo ""

cd /Users/projects/Documents/Fields_Orchestrator && tail -f logs/orchestrator.log
