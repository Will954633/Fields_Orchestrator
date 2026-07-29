#!/usr/bin/env bash
# geo_cycle.sh — durable daily GEO/AI-channel analyst cycle (General RL flagship loop).
# Mirrors 03_Facebook/Home_Owner_Lead_Funnel_Search/run_wakeup.sh: OS cron -> headless
# Claude (Claude Max) reads the GEO signal + reward ledger, researches GEO tactics, and
# produces a prioritised content plan. ANALYSIS/DRAFTS ONLY — never publishes (publish
# routes to Will via WILL_TO_ACTION.md). Safety: flock + timeout + self-report (Rule 7).
set -uo pipefail
DIR=/home/fields/Fields_Orchestrator/16_General_Reinforcement_Learning
LOG=/home/fields/Fields_Orchestrator/logs/geo_cycle.log
LOCK=/tmp/geo_cycle.lock
STAMP=$(TZ=Australia/Brisbane date +%Y%m%d_%H%M)

exec 9>"$LOCK"
if ! flock -n 9; then echo "[$STAMP] previous GEO cycle still running — skip" >> "$LOG"; exit 0; fi

cd /home/fields/Fields_Orchestrator
set -a; source ./.env; set +a
source /home/fields/venv/bin/activate 2>/dev/null || true
export GH_CONFIG_DIR=/home/projects/.config/gh
unset CLAUDECODE CLAUDE_CODE_SSE_PORT 2>/dev/null || true
unset ANTHROPIC_API_KEY 2>/dev/null || true   # force Claude Max subscription, not API billing
mkdir -p "$DIR/cycles"

export CYCLE_STAMP="$STAMP"   # Brisbane-time stamp for the cycle doc — the agent MUST use this, not guess
export CYCLE_DIR="$DIR/cycles/$(TZ=Australia/Brisbane date +%G-W%V)/$(TZ=Australia/Brisbane date +%Y-%m-%d)"
mkdir -p "$CYCLE_DIR"
PROMPT="$(cat "$DIR/geo_prompt.md")"
echo "[$STAMP] ===== GEO cycle start =====" >> "$LOG"

set +e
timeout -k 60 1500 claude -p "$PROMPT" \
  --allowedTools "Bash,Read,Write,Edit,Glob,Grep,WebSearch,WebFetch,TodoWrite" \
  --max-turns 60 >> "$LOG" 2>&1
RC=$?
set -e 2>/dev/null || true
echo "[$STAMP] ===== GEO cycle end (rc=$RC) =====" >> "$LOG"

python3 - "$RC" <<'PY' 2>/dev/null || true
import sys
sys.path.insert(0, "/home/fields/Fields_Orchestrator/scripts")
try:
    from job_status import record_job_result
    rc = int(sys.argv[1])
    record_job_result("geo_cycle", "success" if rc == 0 else "error",
                      cadence_hours=24, title="General RL — GEO/AI-channel analyst cycle (daily)",
                      detail=f"claude -p rc={rc}")
except Exception as e:
    print("job_status record failed:", e)
PY
exit 0
