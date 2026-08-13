#!/usr/bin/env bash
# conductor_dispatch.sh — self-pacing poller for the conductor (NEW Samantha). Cheaply asks
# cycle_pacer.py whether the conductor is DUE + under her daily cap; only then runs the heavy
# conductor_cycle.sh. The conductor sets her own next wake at the end of each cycle.
#
# This is the SELF-PACED lane. Independent of it, a GUARANTEED FLOOR of 2 runs/day (13:15, 20:15
# AEST) fires conductor_cycle.sh directly via cron, and any founder Telegram message auto-wakes her
# via the bridge — both bypass this poller. flock in conductor_cycle.sh serialises everything.
set -uo pipefail
DIR=/home/fields/Fields_Orchestrator/16_General_Reinforcement_Learning
LOG=/home/fields/Fields_Orchestrator/logs/conductor_dispatch.log
STAMP=$(TZ=Australia/Brisbane date +%Y%m%d_%H%M)
cd /home/fields/Fields_Orchestrator
set -a; source ./.env; set +a
source /home/fields/venv/bin/activate 2>/dev/null || true
DECISION=$(python3 "$DIR/cycle_pacer.py" --job conductor --claim 2>&1); RC=$?
echo "[$STAMP] conductor: $DECISION" >> "$LOG"
if [ "$RC" -eq 0 ]; then
  echo "[$STAMP] launching conductor_cycle.sh (self-paced)" >> "$LOG"
  "$DIR/conductor_cycle.sh"
fi
exit 0
