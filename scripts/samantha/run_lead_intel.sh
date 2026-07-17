#!/usr/bin/env bash
# Lead-intelligence pipeline — cron 02:00 AEST, before Samantha's 02:30 review.
# Unifies + enriches + flags every lead into system_monitor.lead_worklist.
set -euo pipefail
cd /home/fields/Fields_Orchestrator
set -a
source ./.env
set +a
export GH_CONFIG_DIR=/home/projects/.config/gh
exec /home/fields/venv/bin/python3 scripts/samantha/lead_intelligence.py "$@"
