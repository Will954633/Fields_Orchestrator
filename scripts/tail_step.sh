#!/bin/bash
# Tail a specific step's output from the latest orchestrator run
# Created: 2026-02-18
#
# Usage: ./tail_step.sh <step_id>
# Example: ./tail_step.sh 101

RUNS_DIR="/home/fields/Fields_Orchestrator/logs/runs"
LAST_RUN=$(ls -1t "$RUNS_DIR" 2>/dev/null | head -1)

if [ -z "$LAST_RUN" ]; then
    echo "No runs found in $RUNS_DIR"
    exit 1
fi

if [ -z "$1" ]; then
    echo "Usage: $0 <step_id>"
    echo ""
    echo "Available steps in most recent run ($LAST_RUN):"
    ls -1 "$RUNS_DIR/$LAST_RUN" | grep "^[0-9]" | while read step_dir; do
        if [ -f "$RUNS_DIR/$LAST_RUN/$step_dir/start.log" ]; then
            STEP_NAME=$(cat "$RUNS_DIR/$LAST_RUN/$step_dir/start.log" | jq -r '.step_name' 2>/dev/null || echo "Unknown")
            echo "  - $step_dir: $STEP_NAME"
        fi
    done
    exit 1
fi

STEP_ID="$1"
STEP_DIR=$(ls -1d "$RUNS_DIR/$LAST_RUN"/*"_step_${STEP_ID}_"* 2>/dev/null | head -1)

if [ -z "$STEP_DIR" ]; then
    echo "Step $STEP_ID not found in $LAST_RUN"
    echo ""
    echo "Available steps:"
    ls -1 "$RUNS_DIR/$LAST_RUN" | grep "^[0-9]"
    exit 1
fi

echo "Tailing: $STEP_DIR/stdout.log"
echo "=========================================="
tail -f "$STEP_DIR/stdout.log"
