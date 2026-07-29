#!/usr/bin/env bash
# tick.sh — cheap */15 gate for the self-paced Off-Market RL cycle.
# Each tick asks cadence.py whether a full cycle is due (work queued OR next_due passed),
# within the rails (≤6/24h, ≥15min gap). If yes → record + run one cycle. If no → exit ~free.
set -uo pipefail
DIR=/home/fields/Fields_Orchestrator/15_Off-Market/Reinforcement_Learning
LOG=/home/fields/Fields_Orchestrator/logs/offmarket_rl_tick.log
LOCK=/tmp/offmarket_rl_tick.lock
STAMP=$(TZ=Australia/Brisbane date +%Y%m%d_%H%M)

exec 9>"$LOCK"
if ! flock -n 9; then exit 0; fi   # a tick (or the cycle it launched) is still running

cd /home/fields/Fields_Orchestrator
set -a; source ./.env; set +a
source /home/fields/venv/bin/activate 2>/dev/null || true

DECISION=$(python3 "$DIR/cadence.py" --should-run 2>>"$LOG"); RC=$?
if [ "$RC" -ne 0 ]; then
  # SKIP — only log occasionally to keep the log clean (top of the hour)
  case "$STAMP" in *_?[0-9]00) echo "[$STAMP] $DECISION" >> "$LOG";; esac
  exit 0
fi

echo "[$STAMP] $DECISION -> running cycle" >> "$LOG"
python3 "$DIR/cadence.py" --record-run >> "$LOG" 2>&1
bash "$DIR/run_cycle.sh"    # has its own flock + timeout + job_run; sets next_due via cadence.py at its end
exit 0
