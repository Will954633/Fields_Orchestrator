#!/bin/bash
# CEO Agent Launcher — runs on property-scraper VM via SSH
# Called from the orchestrator VM cron job
#
# Usage:
#   bash scripts/ceo-agent-launcher-remote.sh                  # run all agents
#   bash scripts/ceo-agent-launcher-remote.sh engineering       # run one agent
#   bash scripts/ceo-agent-launcher-remote.sh --update-context  # refresh context only

set -euo pipefail

REMOTE_HOST="fields-orchestrator-vm@35.201.6.222"
REMOTE_DIR="/home/fields-orchestrator-vm/ceo-agents"
DATE=$(date +%Y-%m-%d)
AGENT="${1:-all}"

log() { echo "[$(date '+%H:%M:%S')] $1"; }

# ── Step 1: Update context on property-scraper ──
log "Updating context repo on property-scraper..."
ssh "$REMOTE_HOST" "
  cd $REMOTE_DIR/context && \
  GH_CONFIG_DIR=~/.config/gh git pull --ff-only origin main 2>&1 | tail -3
"

# Update sandbox too (to get latest proposals)
ssh "$REMOTE_HOST" "
  cd $REMOTE_DIR/sandbox && \
  GH_CONFIG_DIR=~/.config/gh git pull --ff-only origin main 2>&1 | tail -3
"

if [ "$AGENT" = "--update-context" ]; then
  log "Context updated. Exiting."
  exit 0
fi

# ── Step 2: Copy agent prompt scripts ──
log "Deploying agent prompts..."
scp /home/fields/Fields_Orchestrator/scripts/ceo-agent-prompts.sh "$REMOTE_HOST:$REMOTE_DIR/" 2>/dev/null

# ── Step 3: Run agents ──
run_agent() {
  local agent_id="$1"
  log "Running $agent_id agent..."

  ssh -o ServerAliveInterval=30 "$REMOTE_HOST" "
    cd $REMOTE_DIR/sandbox
    mkdir -p proposals $agent_id

    # Copy context into sandbox for Codex access
    rm -rf context 2>/dev/null
    cp -r $REMOTE_DIR/context context

    # Run Codex with the agent prompt
    PROMPT_FILE='/tmp/ceo_prompt_${agent_id}.txt'
    bash $REMOTE_DIR/ceo-agent-prompts.sh $agent_id $DATE > \"\$PROMPT_FILE\"

    codex exec -m gpt-5.1-codex --full-auto \
      -o /tmp/ceo_output_${agent_id}.txt \
      \"\$(cat \$PROMPT_FILE)\" 2>&1 | tail -30

    echo '---RESULT---'
    cat /tmp/ceo_output_${agent_id}.txt 2>/dev/null || echo '[no output]'

    echo '---PROPOSAL CHECK---'
    ls -la proposals/${DATE}_${agent_id}.json 2>/dev/null || echo '[no proposal file created]'
  " 2>&1
}

if [ "$AGENT" = "all" ]; then
  for a in engineering growth product; do
    run_agent "$a"
  done
else
  run_agent "$AGENT"
fi

# ── Step 4: Collect proposals and push ──
log "Collecting proposals and pushing to GitHub..."
ssh "$REMOTE_HOST" "
  cd $REMOTE_DIR/sandbox

  # Remove context copy (don't commit it to sandbox)
  rm -rf context 2>/dev/null

  # Push any new files
  if git status --porcelain | grep -q .; then
    git add -A
    git commit -m 'CEO agents run $DATE' 2>&1 | tail -2
    GH_CONFIG_DIR=~/.config/gh git push origin main 2>&1 | tail -3
  else
    echo 'No new files to push'
  fi
"

# ── Step 5: Pull proposals into MongoDB ──
log "Writing proposals to MongoDB..."
# Fetch proposals from the sandbox repo
PROPOSALS=$(ssh "$REMOTE_HOST" "cat $REMOTE_DIR/sandbox/proposals/${DATE}_*.json 2>/dev/null" || echo "")

if [ -n "$PROPOSALS" ]; then
  source /home/fields/venv/bin/activate
  set -a && source /home/fields/Fields_Orchestrator/.env && set +a

  python3 -c "
import json, os, sys, glob
from datetime import datetime
from pymongo import MongoClient

client = MongoClient(os.environ['COSMOS_CONNECTION_STRING'])
db = client['system_monitor']
coll = db['ceo_proposals']

# Read proposals from stdin (may be multiple JSON objects)
raw = sys.stdin.read()
# Try to parse as individual JSON objects
for line in raw.split('\n'):
    line = line.strip()
    if not line or not line.startswith('{'):
        continue
    try:
        p = json.loads(line)
        p['created_at'] = datetime.utcnow().isoformat()
        p['status'] = 'pending_review'
        p['reviewed_by'] = None
        coll.insert_one(p)
        print(f'  Inserted proposal from {p.get(\"agent\", \"unknown\")}')
    except json.JSONDecodeError:
        pass

client.close()
" <<< "$PROPOSALS"
else
  log "No proposals found for today"
fi

log "CEO agent run complete."
