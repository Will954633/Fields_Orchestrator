#!/usr/bin/env bash
# conductor_cycle.sh — runs the NEW Samantha, the meta-conductor agent (Claude Max).
# Refreshes the holistic board (conductor.py) then runs the conductor agent against conductor_prompt.md.
# flock-guarded: message-triggered wakes (from the Telegram bridge) + cron cannot stack.
# Manual: bash conductor_cycle.sh   ·   Self-reports job "conductor_cycle" to Systems Health.
set -uo pipefail
DIR=/home/fields/Fields_Orchestrator/16_General_Reinforcement_Learning
LOG=/home/fields/Fields_Orchestrator/logs/conductor_cycle.log
LOCK=/tmp/rl_conductor_cycle.lock
PROMPT_FILE="$DIR/conductor_prompt.md"
STAMP=$(TZ=Australia/Brisbane date +%Y%m%d_%H%M)
[ -f "$PROMPT_FILE" ] || { echo "[$STAMP] no prompt $PROMPT_FILE" >> "$LOG"; exit 1; }

exec 9>"$LOCK"
if ! flock -n 9; then echo "[$STAMP] conductor already running — skip" >> "$LOG"; exit 0; fi

cd /home/fields/Fields_Orchestrator
set -a; source ./.env; set +a
source /home/fields/venv/bin/activate 2>/dev/null || true
export GH_CONFIG_DIR=/home/projects/.config/gh
export CYCLE_STAMP="$STAMP"   # Brisbane stamp for the cycle doc — the agent MUST use this, not guess
export CYCLE_DIR="$DIR/cycles/$(TZ=Australia/Brisbane date +%G-W%V)/$(TZ=Australia/Brisbane date +%Y-%m-%d)"
mkdir -p "$CYCLE_DIR"
# Time budget (Will, 2026-07-29): 60-min max; the agent self-checks elapsed against CYCLE_START_EPOCH
# and winds down gracefully (wrap at 45, outputs-done by 50) so the 60-min hard-kill never truncates her.
export CYCLE_START_EPOCH="$(date +%s)"
export CYCLE_MAX_MIN=60 CYCLE_WRAP_MIN=45 CYCLE_FINALIZE_MIN=50
unset CLAUDECODE CLAUDE_CODE_SSE_PORT 2>/dev/null || true
unset ANTHROPIC_API_KEY 2>/dev/null || true   # force Claude Max, not API billing
mkdir -p "$DIR/cycles"

echo "[$STAMP] ===== conductor cycle start =====" >> "$LOG"
# 1) refresh the holistic board so the agent reads current data (no --telegram; the agent owns messaging)
python3 "$DIR/conductor.py" >> "$LOG" 2>&1 || echo "[$STAMP] board refresh warned (continuing)" >> "$LOG"

# 2) run the conductor agent
set +e
timeout -k 120 3600 claude -p "$(cat "$PROMPT_FILE")" \
  --allowedTools "Bash,Read,Write,Edit,Glob,Grep,WebSearch,WebFetch,TodoWrite" \
  --max-turns 60 >> "$LOG" 2>&1
RC=$?
set -e 2>/dev/null || true
echo "[$STAMP] ===== conductor cycle end (rc=$RC) =====" >> "$LOG"

python3 - "$RC" <<'PY' 2>/dev/null || true
import sys
sys.path.insert(0, "/home/fields/Fields_Orchestrator/scripts")
try:
    from job_status import record_job_result
    rc = int(sys.argv[1])
    record_job_result("conductor_cycle", "success" if rc == 0 else "error",
                      cadence_hours=12, title="General RL — Samantha meta-conductor (agent)",
                      detail=f"claude -p rc={rc}")
except Exception as e:
    print("job_status record failed:", e)
PY
exit 0
