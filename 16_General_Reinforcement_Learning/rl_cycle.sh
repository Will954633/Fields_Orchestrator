#!/usr/bin/env bash
# rl_cycle.sh <domain> — GENERIC durable cycle runner for any General RL sub-workflow.
# A domain = a <domain>_prompt.md + a <domain>_signal.py. This runner is shared: it locks,
# runs headless Claude (Claude Max) with the domain's prompt, and self-reports. New domains
# need NO new runner. Manual trigger: `bash rl_cycle.sh <domain>`.
set -uo pipefail
DOMAIN="${1:?usage: rl_cycle.sh <domain>}"
DIR=/home/fields/Fields_Orchestrator/16_General_Reinforcement_Learning
LOG="/home/fields/Fields_Orchestrator/logs/${DOMAIN}_cycle.log"
LOCK="/tmp/rl_${DOMAIN}_cycle.lock"
PROMPT_FILE="$DIR/${DOMAIN}_prompt.md"
STAMP=$(TZ=Australia/Brisbane date +%Y%m%d_%H%M)
[ -f "$PROMPT_FILE" ] || { echo "[$STAMP] no prompt $PROMPT_FILE" >> "$LOG"; exit 1; }

exec 9>"$LOCK"
if ! flock -n 9; then echo "[$STAMP] previous $DOMAIN cycle still running — skip" >> "$LOG"; exit 0; fi

cd /home/fields/Fields_Orchestrator
set -a; source ./.env; set +a
source /home/fields/venv/bin/activate 2>/dev/null || true
export GH_CONFIG_DIR=/home/projects/.config/gh
export PACER_JOB="$DOMAIN"
export CYCLE_STAMP="$STAMP"   # Brisbane-time stamp for the cycle doc — the agent MUST use this, not guess
unset CLAUDECODE CLAUDE_CODE_SSE_PORT 2>/dev/null || true
unset ANTHROPIC_API_KEY 2>/dev/null || true   # force Claude Max, not API billing
mkdir -p "$DIR/cycles"

echo "[$STAMP] ===== $DOMAIN cycle start =====" >> "$LOG"
set +e
timeout 1500 claude -p "$(cat "$PROMPT_FILE")" \
  --allowedTools "Bash,Read,Write,Edit,Glob,Grep,WebSearch,WebFetch,TodoWrite" \
  --max-turns 60 >> "$LOG" 2>&1
RC=$?
set -e 2>/dev/null || true
echo "[$STAMP] ===== $DOMAIN cycle end (rc=$RC) =====" >> "$LOG"

python3 - "$DOMAIN" "$RC" <<'PY' 2>/dev/null || true
import sys
sys.path.insert(0, "/home/fields/Fields_Orchestrator/scripts")
try:
    from job_status import record_job_result
    dom, rc = sys.argv[1], int(sys.argv[2])
    record_job_result(f"{dom}_cycle", "success" if rc == 0 else "error",
                      cadence_hours=24, title=f"General RL — {dom.upper()} analyst cycle (self-paced)",
                      detail=f"claude -p rc={rc}")
except Exception as e:
    print("job_status record failed:", e)
PY
exit 0
