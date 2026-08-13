#!/bin/bash
# Fields Worker Agent — Launcher  ⚠ RETIRED 2026-04-27, SAFETY-GATED 2026-08-13
#
# ⚠ DO NOT RE-ENABLE WITHOUT READING THIS.
#
# This launches `claude -p --dangerously-skip-permissions` for up to 6000s, and
# line 32 does `set -a && source .env`, which exports all 83 credentials into the
# child. An audit on 2026-08-13 confirmed by live probe that the inherited
# GITHUB_TOKEN carries admin:true AND push:true on BOTH production repos
# (Website_Version_Feb_2026 and Fields_Orchestrator). Combined with the skipped
# permission engine, a single run can deploy the live website, change Facebook and
# Google ad campaigns, publish content, drop database collections, and send from
# Will's Telegram/Gmail — with no prompt.
#
# The guardrails named at line ~72 ("system prompt enforces hard limits") are
# INSTRUCTIONS IN WORKER_AGENT.md, enforced by nothing. Worse, the prompt is built
# by concatenating 07_Focus/*.md raw, so anything written into those files becomes
# an instruction to a permissionless agent.
#
# Cron was disabled 2026-04-27 (fix-history [WORKER-AGENT-DISABLE]) and it has not
# run since 2026-04-26. It is kept only because deliverables/ has historical value.
# The successor is scripts/spawn_worker.py, which sandboxes credentials rather
# than exporting them. See CLAUDE.md Rule 9.

set -euo pipefail

if [[ "${WORKER_AGENT_I_MEAN_IT:-}" != "1" ]]; then
    cat >&2 <<'GATE'
run-worker-agent.sh is RETIRED and gated.

It runs claude with --dangerously-skip-permissions and exports every production
credential (GitHub admin+push on both repos, Netlify, Facebook Ads, Google Ads,
Cosmos, Telegram, Gmail) into that session. Nothing enforces its stated limits.

If you want a background Claude session, use the sandboxed path instead:
    python3 scripts/spawn_task.py --help

To run this anyway, you must be a human who has read the header:
    WORKER_AGENT_I_MEAN_IT=1 bash worker-agent/run-worker-agent.sh
GATE
    exit 1
fi

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ORCHESTRATOR_DIR="$(dirname "$SCRIPT_DIR")"
DATE=$(TZ=Australia/Brisbane date +%Y-%m-%d)
TIME=$(TZ=Australia/Brisbane date +%H:%M)
DELIVERABLES_DIR="$SCRIPT_DIR/deliverables/$DATE"
LOG_FILE="$SCRIPT_DIR/logs/worker-agent-$DATE.log"
MAX_TURNS=200

# Parse --max-turns flag
while [[ $# -gt 0 ]]; do
    case "$1" in
        --max-turns) MAX_TURNS="$2"; shift 2 ;;
        *) shift ;;
    esac
done

# Create directories
mkdir -p "$DELIVERABLES_DIR"/{code,content,reports,screenshots}
mkdir -p "$SCRIPT_DIR/logs"

echo "[$TIME] Worker Agent starting — date: $DATE, max turns: $MAX_TURNS" | tee -a "$LOG_FILE"

# Activate environment
source /home/fields/venv/bin/activate
set -a && source "$ORCHESTRATOR_DIR/.env" && set +a

# Allow running from within another Claude Code session (cron or manual trigger)
unset CLAUDECODE 2>/dev/null || true

# Send Telegram notification — session starting
python3 "$ORCHESTRATOR_DIR/scripts/telegram_notify.py" "🤖 Worker Agent session starting ($TIME AEST). Reading sprint and backlog..." 2>/dev/null || true

cd "$ORCHESTRATOR_DIR"

# Build context from current state
CHECKPOINT=$(cat 07_Focus/checkpoint-status.md 2>/dev/null | head -100 || echo "No checkpoint file")
BACKLOG=$(cat 07_Focus/agent-backlog.md 2>/dev/null | head -150 || echo "No backlog file")
SPRINT=$(ls -t 07_Focus/sprints/sprint-*.md 2>/dev/null | head -1)
SPRINT_CONTENT=""
if [ -n "${SPRINT:-}" ]; then
    SPRINT_CONTENT=$(head -100 "$SPRINT")
fi

# Create the prompt file (avoids shell escaping issues)
cat > /tmp/worker-agent-prompt.txt <<PROMPT
Today is $DATE, $TIME AEST.
Your deliverables directory is: $DELIVERABLES_DIR

## Current Sprint Checkpoint
$CHECKPOINT

## Agent Backlog (top priorities)
$BACKLOG

## Current Sprint
$SPRINT_CONTENT

---

Read the above context. Build your task list from overdue items and highest-priority backlog work. Start executing — produce real deliverables, not proposals. Save all output to worker-agent/deliverables/$DATE/. When done, write a session summary and notify Will via Telegram.
PROMPT

# Run Claude with worker agent instructions
# Hard time limit: 100 minutes (agent should self-stop at 90, this is the backstop)
# Guardrails: system prompt enforces hard limits on writes/deploys/ads
timeout 6000 claude -p \
    --model opus \
    --system-prompt "$(cat "$SCRIPT_DIR/WORKER_AGENT.md")" \
    --dangerously-skip-permissions \
    "$(cat /tmp/worker-agent-prompt.txt)" \
    2>&1 | tee -a "$LOG_FILE" || true

rm -f /tmp/worker-agent-prompt.txt

# Send Telegram notification — session complete
SUMMARY_FILE="$DELIVERABLES_DIR/session-summary.md"
if [ -f "$SUMMARY_FILE" ]; then
    # Send first 500 chars of summary
    MSG=$(head -c 500 "$SUMMARY_FILE")
    python3 "$ORCHESTRATOR_DIR/scripts/telegram_notify.py" "✅ Worker Agent done ($TIME AEST):
$MSG" 2>/dev/null || true
else
    python3 "$ORCHESTRATOR_DIR/scripts/telegram_notify.py" "✅ Worker Agent session complete ($TIME AEST). Check worker-agent/deliverables/$DATE/" 2>/dev/null || true
fi

echo "[$(TZ=Australia/Brisbane date +%H:%M)] Worker Agent session ended" | tee -a "$LOG_FILE"
