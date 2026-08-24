#!/usr/bin/env bash
# Install the fortnightly Market Research cycle cron.
# Cron fires every Sunday noon (VM is Australia/Brisbane); run_research_cycle.py
# no-ops on OFF weeks, so the effective cadence is fortnightly. Idempotent.
#
# ⚠ Run this from a STABLE checkout (/home/fields/Fields_Orchestrator on main),
#   NOT a temporary git worktree — the cron path must survive.
set -euo pipefail
ORCH=/home/fields/Fields_Orchestrator
PY=/home/fields/venv/bin/python
LOG="$ORCH/logs/market_research_cycle.log"
LINE="0 12 * * 0 cd $ORCH && set -a && . ./.env && set +a && $PY 14_Articles/Market_Research/scripts/run_research_cycle.py >> $LOG 2>&1 # market_research_cycle"
( crontab -l 2>/dev/null | grep -v 'market_research_cycle' ; echo "$LINE" ) | crontab -
echo "Installed. Current entry:"; crontab -l | grep market_research_cycle
echo "Seed a first heartbeat now with:  $PY 14_Articles/Market_Research/scripts/run_research_cycle.py --topic national-market-turn-2026 --force"
