#!/bin/bash
# Wait for nightly pipeline to finish, then rerun floor plans with gpt-5.4
# Run this in background: nohup bash scripts/run_floor_plan_rerun_after_pipeline.sh &

LOG="/home/fields/Fields_Orchestrator/logs/floor_plan_rerun.log"
echo "$(date) — Waiting for pipeline to finish..." >> "$LOG"

# Wait until no step is running (check every 2 minutes)
while true; do
    LAST_LINE=$(tail -1 /home/fields/Fields_Orchestrator/logs/orchestrator.log)
    if echo "$LAST_LINE" | grep -q "Daily run complete\|Run complete\|Sleeping until"; then
        echo "$(date) — Pipeline finished. Starting floor plan rerun." >> "$LOG"
        break
    fi
    sleep 120
done

# Give Cosmos a minute to cool down after pipeline
sleep 60

source /home/fields/venv/bin/activate
set -a && source /home/fields/Fields_Orchestrator/.env && set +a
cd /home/fields/Fields_Orchestrator

python3 scripts/rerun_floor_plans.py >> "$LOG" 2>&1
echo "$(date) — Floor plan rerun complete (exit=$?)" >> "$LOG"
