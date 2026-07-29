#!/usr/bin/env bash
# run_cycle.sh — durable scheduled iteration for the Off-Market RL loop.
# Invoked by OS cron (NOT the in-session scheduler). Runs headless Claude (Claude Max)
# with tools to read state (corpus + PostHog behaviour), analyse what engaged + why,
# run the daily coverage wave, stage content/format arms, and document the cycle.
#
# Safety: flock (no overlap) + timeout + self-report to Systems Health (Rule 7).
set -uo pipefail
DIR=/home/fields/Fields_Orchestrator/15_Off-Market/Reinforcement_Learning
LOG=/home/fields/Fields_Orchestrator/logs/offmarket_rl_cycle.log
LOCK=/tmp/offmarket_rl_cycle.lock
STAMP=$(TZ=Australia/Brisbane date +%Y%m%d_%H%M)

exec 9>"$LOCK"
if ! flock -n 9; then echo "[$STAMP] previous cycle still running — skip" >> "$LOG"; exit 0; fi

cd /home/fields/Fields_Orchestrator
set -a; source ./.env; set +a
source /home/fields/venv/bin/activate 2>/dev/null || true
export GH_CONFIG_DIR=/home/projects/.config/gh
unset CLAUDECODE CLAUDE_CODE_SSE_PORT 2>/dev/null || true   # not a nested session
unset ANTHROPIC_API_KEY 2>/dev/null || true                 # force Claude Max, not API billing
mkdir -p "$DIR/cycles"

PROMPT="$(cat "$DIR/cycle_prompt.md")"
echo "[$STAMP] ===== off-market RL cycle start =====" >> "$LOG"

set +e
timeout 1800 claude -p "$PROMPT" \
  --allowedTools "Bash,Read,Write,Edit,Glob,Grep,WebSearch,WebFetch,TodoWrite" \
  --max-turns 80 >> "$LOG" 2>&1
RC=$?
set -e 2>/dev/null || true
echo "[$STAMP] ===== off-market RL cycle end (rc=$RC) =====" >> "$LOG"

python3 - "$RC" <<'PY' 2>/dev/null || true
import sys
sys.path.insert(0, "/home/fields/Fields_Orchestrator/scripts")
try:
    from job_status import record_job_result
    rc = int(sys.argv[1])
    record_job_result("offmarket_rl_cycle", "success" if rc == 0 else "error",
                      cadence_hours=24, title="Off-Market RL — cycle (daily)",
                      detail=f"claude -p rc={rc}")
except Exception as e:
    print("job_status record failed:", e)
PY
exit 0
