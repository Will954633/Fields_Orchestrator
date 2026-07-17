#!/usr/bin/env bash
# Samantha nightly scheduled run — invoked by cron at 02:30 AEST.
# Sources .env (Telegram/Cosmos/etc.), sets gh config dir, runs the Max (Opus) agent.
# The Python runner strips ANTHROPIC_API_KEY internally so billing is the Max subscription.
set -euo pipefail
cd /home/fields/Fields_Orchestrator
set -a
source ./.env
set +a
export GH_CONFIG_DIR=/home/projects/.config/gh
exec /home/fields/venv/bin/python3 scripts/samantha/daily_run.py "$@"
