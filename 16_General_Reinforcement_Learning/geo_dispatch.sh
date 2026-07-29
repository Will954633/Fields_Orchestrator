#!/usr/bin/env bash
# geo_dispatch.sh — cheap poller that gives the GEO cycle SELF-PACING.
# Runs every 20 min (awake hours) via cron. It does NOT run the cycle itself — it
# asks cycle_state.py --claim whether a cycle is DUE (the previous cycle chose when)
# and UNDER the daily cap. Only then does it launch the heavy claude -p cycle. So the
# cycle does max work in min cycles: it chains straight on when it has work in hand,
# backs off when blocked on Will / quiet, and can never exceed MAX_CYCLES_PER_DAY.
set -uo pipefail
DIR=/home/fields/Fields_Orchestrator/16_General_Reinforcement_Learning
LOG=/home/fields/Fields_Orchestrator/logs/geo_dispatch.log
STAMP=$(TZ=Australia/Brisbane date +%Y%m%d_%H%M)

cd /home/fields/Fields_Orchestrator
set -a; source ./.env; set +a
source /home/fields/venv/bin/activate 2>/dev/null || true

DECISION=$(python3 "$DIR/cycle_state.py" --claim 2>&1); RC=$?
echo "[$STAMP] $DECISION" >> "$LOG"
if [ "$RC" -eq 0 ]; then
  echo "[$STAMP] launching geo_cycle.sh" >> "$LOG"
  "$DIR/geo_cycle.sh"
fi
exit 0
