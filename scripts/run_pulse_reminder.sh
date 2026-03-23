#!/bin/bash
# Monthly reminder — runs on the 1st of every month
cd /home/fields/Fields_Orchestrator
set -a && . .env && set +a
/home/fields/venv/bin/python3 scripts/telegram_notify.py --market-pulse-reminder >> logs/market-pulse.log 2>&1
