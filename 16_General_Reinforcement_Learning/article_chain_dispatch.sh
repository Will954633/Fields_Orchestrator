#!/usr/bin/env bash
# article_chain_dispatch.sh — cheap poller. Asks article_chain.py whether the ARTICLES domain
# asked to run again; only then launches the expensive weekly_cycle.sh articles.
#
# This is the ONE domain permitted to chain its own sessions (Will, 2026-08-13). The guards
# live in article_chain.py, not here, so they cannot be bypassed by editing this file.
set -uo pipefail
DIR=/home/fields/Fields_Orchestrator/16_General_Reinforcement_Learning
LOG=/home/fields/Fields_Orchestrator/logs/article_chain.log
STAMP=$(TZ=Australia/Brisbane date +%Y%m%d_%H%M)
cd /home/fields/Fields_Orchestrator
set -a; source ./.env; set +a
source /home/fields/venv/bin/activate 2>/dev/null || true
DECISION=$(python3 "$DIR/article_chain.py" --claim 2>&1); RC=$?
echo "[$STAMP] $DECISION" >> "$LOG"
if [ "$RC" -eq 0 ]; then
  echo "[$STAMP] launching chained articles cycle" >> "$LOG"
  "$DIR/weekly_cycle.sh" articles
fi
exit 0
