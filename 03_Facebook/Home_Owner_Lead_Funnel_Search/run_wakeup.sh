#!/usr/bin/env bash
# run_wakeup.sh — durable hourly WAKE-UP-CLAUDE iteration for the Home Owner Lead Funnel.
# Invoked by OS cron (NOT the in-session scheduler, which does not fire while the REPL
# waits on user input). Runs headless Claude (Claude Max) with tools to analyse the
# out-of-market copy test, research new concepts, and launch a fresh batch. Copy
# discovery ONLY — never promotes to Gold Coast (Will controls GC go-live).
#
# Safety: flock (no overlapping runs) + timeout + self-report to Systems Health (Rule 7).
set -uo pipefail
DIR=/home/fields/Fields_Orchestrator/03_Facebook/Home_Owner_Lead_Funnel_Search
LOG=/home/fields/Fields_Orchestrator/logs/home_owner_wakeup.log
LOCK=/tmp/home_owner_wakeup.lock
STAMP=$(TZ=Australia/Brisbane date +%Y%m%d_%H%M)

exec 9>"$LOCK"
if ! flock -n 9; then echo "[$STAMP] previous wake-up still running — skip" >> "$LOG"; exit 0; fi

cd /home/fields/Fields_Orchestrator
set -a; source ./.env; set +a
source /home/fields/venv/bin/activate 2>/dev/null || true
export GH_CONFIG_DIR=/home/projects/.config/gh
unset CLAUDECODE CLAUDE_CODE_SSE_PORT 2>/dev/null || true   # ensure not treated as nested
unset ANTHROPIC_API_KEY 2>/dev/null || true                 # force Claude Max subscription, not API billing (Will)
mkdir -p "$DIR/cycles"

PROMPT="$(cat "$DIR/run_wakeup_prompt.md")"
echo "[$STAMP] ===== wake-up cycle start =====" >> "$LOG"

set +e
timeout 1500 claude --model claude-opus-4-8 -p "$PROMPT" \
  --allowedTools "Bash,Read,Write,Edit,Glob,Grep,WebSearch,WebFetch,TodoWrite" \
  --max-turns 60 >> "$LOG" 2>&1
RC=$?
set -e 2>/dev/null || true
echo "[$STAMP] ===== wake-up cycle end (rc=$RC) =====" >> "$LOG"

# self-report to Systems Health (CLAUDE.md Rule 7)
python3 - "$RC" <<'PY' 2>/dev/null || true
import sys
sys.path.insert(0,"/home/fields/Fields_Orchestrator/scripts")
try:
    from job_status import record_job_result
    rc=int(sys.argv[1])
    record_job_result("home_owner_wakeup", "success" if rc==0 else "error",
                      cadence_hours=8, title="Home Owner Funnel — wake-up cycle (hourly 8am-10pm)",
                      detail=f"claude -p rc={rc}")
except Exception as e:
    print("job_status record failed:", e)
PY
exit 0
