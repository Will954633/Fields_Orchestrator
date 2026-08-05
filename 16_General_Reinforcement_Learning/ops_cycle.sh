#!/usr/bin/env bash
# ops_cycle.sh — STANDALONE daily ops-triage cycle (Samantha, ops domain).
#
# Deliberately NOT rl_cycle.sh:
#   - rl_cycle.sh is pinned to claude-opus-4-8; this runs on OPUS 5 (Will, 2026-08-05).
#   - the RL fleet is paused (2026-07-30, GC rebuild). This job must run on its own
#     schedule without dragging geo/seo/ads/articles/onsite back on with it, and
#     without depending on cycle_pacer/dispatcher state.
#
# Refreshes the ops sensor, then runs the headless agent against ops_prompt.md on the
# Claude Max subscription (credit-free — ANTHROPIC_API_KEY is unset so it can never
# fall through to metered API billing).
#
# Manual: bash ops_cycle.sh
set -uo pipefail
DIR=/home/fields/Fields_Orchestrator/16_General_Reinforcement_Learning
LOG=/home/fields/Fields_Orchestrator/logs/ops_cycle.log
LOCK=/tmp/rl_ops_cycle.lock
STAMP=$(TZ=Australia/Brisbane date +%Y%m%d_%H%M)

exec 9>"$LOCK"
if ! flock -n 9; then echo "[$STAMP] previous ops cycle still running — skip" >> "$LOG"; exit 0; fi

cd /home/fields/Fields_Orchestrator
set -a; source ./.env; set +a
source /home/fields/venv/bin/activate 2>/dev/null || true
export GH_CONFIG_DIR=/home/projects/.config/gh
export CYCLE_STAMP="$STAMP"
export CYCLE_DIR="$DIR/cycles/$(TZ=Australia/Brisbane date +%G-W%V)/$(TZ=Australia/Brisbane date +%Y-%m-%d)"
export CYCLE_START_EPOCH=$(date +%s)
mkdir -p "$CYCLE_DIR"
unset CLAUDECODE CLAUDE_CODE_SSE_PORT 2>/dev/null || true
unset ANTHROPIC_API_KEY 2>/dev/null || true   # force Claude Max, not API billing

echo "[$STAMP] ===== ops cycle start =====" >> "$LOG"

# Refresh the sensor first so the agent reads current state, not yesterday's.
python3 "$DIR/ops_signal.py" >> "$LOG" 2>&1
SIG_RC=$?
echo "[$STAMP] ops_signal rc=$SIG_RC" >> "$LOG"

set +e
timeout -k 60 2400 claude --model claude-opus-5 -p "$(cat "$DIR/ops_prompt.md")" \
  --allowedTools "Bash,Read,Write,Edit,Glob,Grep,WebSearch,WebFetch,TodoWrite" \
  --max-turns 80 >> "$LOG" 2>&1
RC=$?
set -e 2>/dev/null || true
echo "[$STAMP] ===== ops cycle end (rc=$RC) =====" >> "$LOG"

python3 - "$RC" <<'PY' 2>/dev/null || true
import sys
sys.path.insert(0, "/home/fields/Fields_Orchestrator/scripts")
try:
    from job_status import record_job_result
    rc = int(sys.argv[1])
    # Daily. stale_hours=40 so one missed day flags without alarming on a late run.
    record_job_result("ops_cycle", "success" if rc == 0 else "error",
                      cadence_hours=24, stale_hours=40,
                      title="Ops — health-board triage cycle (Samantha, Opus 5)",
                      detail=f"claude -p rc={rc}")
except Exception as e:
    print("job_status record failed:", e)
PY
exit 0
