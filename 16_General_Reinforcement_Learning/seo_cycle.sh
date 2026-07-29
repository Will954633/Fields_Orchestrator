#!/usr/bin/env bash
# seo_cycle.sh — durable daily SEO (Google organic) analyst cycle (General RL flagship loop).
# Mirrors 03_Facebook/Home_Owner_Lead_Funnel_Search/run_wakeup.sh: OS cron -> headless
# Claude (Claude Max) reads the GEO signal + reward ledger, researches GEO tactics, and
# produces a prioritised content plan. ANALYSIS/DRAFTS ONLY — never publishes (publish
# routes to Will via WILL_TO_ACTION.md). Safety: flock + timeout + self-report (Rule 7).
set -uo pipefail
DIR=/home/fields/Fields_Orchestrator/16_General_Reinforcement_Learning
LOG=/home/fields/Fields_Orchestrator/logs/seo_cycle.log
LOCK=/tmp/seo_cycle.lock
STAMP=$(TZ=Australia/Brisbane date +%Y%m%d_%H%M)

exec 9>"$LOCK"
if ! flock -n 9; then echo "[$STAMP] previous SEO cycle still running — skip" >> "$LOG"; exit 0; fi

cd /home/fields/Fields_Orchestrator
set -a; source ./.env; set +a
source /home/fields/venv/bin/activate 2>/dev/null || true
export GH_CONFIG_DIR=/home/projects/.config/gh
unset CLAUDECODE CLAUDE_CODE_SSE_PORT 2>/dev/null || true
unset ANTHROPIC_API_KEY 2>/dev/null || true   # force Claude Max subscription, not API billing
mkdir -p "$DIR/cycles"

PROMPT="$(cat "$DIR/seo_prompt.md")"
echo "[$STAMP] ===== SEO cycle start =====" >> "$LOG"

set +e
timeout 1500 claude -p "$PROMPT" \
  --allowedTools "Bash,Read,Write,Edit,Glob,Grep,WebSearch,WebFetch,TodoWrite" \
  --max-turns 60 >> "$LOG" 2>&1
RC=$?
set -e 2>/dev/null || true
echo "[$STAMP] ===== SEO cycle end (rc=$RC) =====" >> "$LOG"

python3 - "$RC" <<'PY' 2>/dev/null || true
import sys
sys.path.insert(0, "/home/fields/Fields_Orchestrator/scripts")
try:
    from job_status import record_job_result
    rc = int(sys.argv[1])
    record_job_result("seo_cycle", "success" if rc == 0 else "error",
                      cadence_hours=24, title="General RL — SEO (Google organic) analyst cycle (daily)",
                      detail=f"claude -p rc={rc}")
except Exception as e:
    print("job_status record failed:", e)
PY
exit 0
