#!/usr/bin/env bash
# samantha_weekly.sh — the weekly synthesis cycle. Runs AFTER all seven domain cycles
# (valuation, the first non-marketing domain, was added 2026-08-13 at 12:00 Sun).
#
# Samantha is now the ONLY channel between the domain agents and Will. That is the whole
# point of the redesign — but it also makes this script the single point of failure for the
# entire system. If a domain cycle dies, she reports it in the brief. If SHE dies, nobody
# finds out, and the week is silent. So unlike the domain runners, this one alerts Will
# directly when it fails. That is the one sanctioned exception to "only Samantha messages
# Will": the runner speaking about its own death, not an agent deciding it has news.
set -uo pipefail
DIR=/home/fields/Fields_Orchestrator/16_General_Reinforcement_Learning
LOG=/home/fields/Fields_Orchestrator/logs/rl_samantha_weekly.log
LOCK=/tmp/rl_samantha_weekly.lock
STAMP=$(TZ=Australia/Brisbane date +%Y%m%d_%H%M)
MODEL="${RL_MODEL:-claude-opus-5}"
BUDGET_SEC="${RL_BUDGET_SEC:-3600}"   # 60 min — she reads six cycle docs plus the ledger
PROMPT_FILE="$DIR/samantha_weekly_prompt.md"

exec 9>"$LOCK"
if ! flock -n 9; then echo "[$STAMP] previous samantha weekly still running — skip" >> "$LOG"; exit 0; fi

cd /home/fields/Fields_Orchestrator
set -a; source ./.env; set +a
source /home/fields/venv/bin/activate 2>/dev/null || true
export GH_CONFIG_DIR=/home/projects/.config/gh
export CYCLE_STAMP="$STAMP"
export CYCLE_WEEK=$(TZ=Australia/Brisbane date +%G-W%V)
export CYCLE_DIR="$DIR/cycles/$CYCLE_WEEK/$(TZ=Australia/Brisbane date +%Y-%m-%d)"
export CYCLE_START_EPOCH=$(date +%s)
export RL_DOMAIN="samantha"
mkdir -p "$CYCLE_DIR"
unset CLAUDECODE CLAUDE_CODE_SSE_PORT 2>/dev/null || true
unset ANTHROPIC_API_KEY 2>/dev/null || true   # force Claude Max, never metered API billing

echo "[$STAMP] ===== samantha weekly brief start (model=$MODEL) =====" >> "$LOG"

BRIEF="$CYCLE_DIR/weekly_brief_${STAMP}.md"
RUN_LOG="/tmp/rl_samantha_weekly_${STAMP}.out"

AUTH_FAIL=0
RC=0
for attempt in 1 2; do
  set +e
  timeout -k 120 "$BUDGET_SEC" claude --model "$MODEL" -p "$(cat "$PROMPT_FILE")" \
    --allowedTools "Bash,Read,Write,Edit,Glob,Grep,WebSearch,WebFetch,TodoWrite" \
    --max-turns 100 > "$RUN_LOG" 2>&1
  RC=$?
  set -e 2>/dev/null || true
  AUTH_FAIL=0
  grep -qF "OAuth session expired" "$RUN_LOG" && AUTH_FAIL=1
  grep -qF "Failed to authenticate" "$RUN_LOG" && AUTH_FAIL=1
  cat "$RUN_LOG" >> "$LOG"
  if [ "$AUTH_FAIL" -eq 0 ]; then break; fi
  if [ "$attempt" -eq 1 ]; then
    echo "[$STAMP] auth failure on attempt 1 — sleeping 120s, retrying once" >> "$LOG"
    sleep 120
  fi
done
echo "[$STAMP] ===== samantha weekly brief end (rc=$RC auth_fail=$AUTH_FAIL) =====" >> "$LOG"

BRIEF_OK=0
[ -s "$BRIEF" ] && BRIEF_OK=1
rm -f "$RUN_LOG"

# Rule 7b — the outcome is A BRIEF ON DISK. Nothing else counts. A silent week is exactly
# the failure this whole redesign exists to prevent, so it must be loud.
python3 - "$RC" "$BRIEF_OK" "$AUTH_FAIL" "$BRIEF" <<'PY' 2>/dev/null || true
import sys
sys.path.insert(0, "/home/fields/Fields_Orchestrator/scripts")
rc, brief_ok, auth_fail, brief = int(sys.argv[1]), int(sys.argv[2]), int(sys.argv[3]), sys.argv[4]
problems = []
if auth_fail:
    problems.append("Claude Max OAuth failed after retry — Samantha never ran")
if rc != 0:
    problems.append(f"claude -p rc={rc}")
if not brief_ok:
    problems.append(f"NO BRIEF WRITTEN ({brief}) — Will got nothing this week")
status = "error" if problems else "success"
detail = "; ".join(problems) if problems else f"brief written: {brief}"

try:
    from job_status import record_job_result
    record_job_result("rl_samantha_weekly", status,
                      cadence_hours=168, stale_hours=200,
                      title="General RL — Samantha weekly brief to Will",
                      detail=detail)
except Exception as e:
    print("job_status record failed:", e)

# The single sanctioned runner->Will alert (see header). Only on failure, and only because
# a missing brief is otherwise indistinguishable from a genuinely quiet week.
if problems:
    try:
        sys.path.insert(0, "/home/fields/Fields_Orchestrator")
        from scripts.telegram_notify import send_message
        send_message(
            "⚠️ The weekly RL brief did NOT run this week.\n"
            f"{detail}\n"
            "No domain recommendations reached you. Logs: logs/rl_samantha_weekly.log")
    except Exception as e:
        print("telegram alert failed:", e)
print(f"heartbeat: {status} — {detail}")
PY
exit 0
