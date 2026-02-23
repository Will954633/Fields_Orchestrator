#!/bin/bash
# Quick status check for most recent orchestrator run
# Created: 2026-02-18

RUNS_DIR="/home/fields/Fields_Orchestrator/logs/runs"

# Find most recent run directory
LAST_RUN=$(ls -1t "$RUNS_DIR" 2>/dev/null | head -1)

if [ -z "$LAST_RUN" ]; then
    echo "No runs found in $RUNS_DIR"
    exit 1
fi

echo "=========================================="
echo "MOST RECENT RUN: $LAST_RUN"
echo "=========================================="
echo ""

# Show metadata
if [ -f "$RUNS_DIR/$LAST_RUN/00_run_metadata.json" ]; then
    echo "## Metadata"
    cat "$RUNS_DIR/$LAST_RUN/00_run_metadata.json" | jq '.'
    echo ""
fi

# Show each step status
echo "## Step Results"
for step_dir in "$RUNS_DIR/$LAST_RUN"/*/; do
    if [ -f "$step_dir/result.json" ]; then
        STEP_NAME=$(basename "$step_dir")
        SUCCESS=$(cat "$step_dir/result.json" | jq -r '.success')
        DURATION=$(cat "$step_dir/result.json" | jq -r '.duration_seconds')

        if [ "$SUCCESS" == "true" ]; then
            echo "✅ $STEP_NAME (${DURATION}s)"
        else
            echo "❌ $STEP_NAME (${DURATION}s)"
            ERROR=$(cat "$step_dir/result.json" | jq -r '.error_message')
            echo "   Error: $ERROR"
        fi
    fi
done
echo ""

# Show summary if exists
if [ -f "$RUNS_DIR/$LAST_RUN/run_summary.json" ]; then
    echo "## Run Summary"
    cat "$RUNS_DIR/$LAST_RUN/run_summary.json" | jq '.'
fi
