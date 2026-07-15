#!/usr/bin/env bash
# run_todo_reminders.sh — Cron wrapper for todo reminder digest.
# Runs 2x/day: 08:00 + 17:00 AEST.
# Sends Telegram digest of overdue + due-today + due-this-week items.
#
# Crontab entries:
#   0 22 * * * /home/fields/Fields_Orchestrator/scripts/run_todo_reminders.sh  # 08:00 AEST (UTC+10)
#   0 7 * * *  /home/fields/Fields_Orchestrator/scripts/run_todo_reminders.sh  # 17:00 AEST (UTC+10)

set -euo pipefail

cd /home/fields/Fields_Orchestrator
source /home/fields/venv/bin/activate
set -a && source .env && set +a

python3 scripts/todo-manager.py remind --quiet
