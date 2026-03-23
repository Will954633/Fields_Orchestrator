#!/bin/bash
# Fallback market pulse generator — runs on the 3rd of every month
# Only generates summaries for categories NOT manually updated this month
cd /home/fields/Fields_Orchestrator
set -a && . .env && set +a
echo "$(date): Running fallback pulse generation (skipping manual updates)..." >> logs/market-pulse.log
/home/fields/venv/bin/python3 scripts/generate_market_pulse.py >> logs/market-pulse.log 2>&1
