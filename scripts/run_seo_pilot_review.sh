#!/bin/bash
# Weekly SEO demand-engine pilot review — fires every Monday 08:00 AEST.
# Runs seo_pilot_status.py: computes real indexation + organic-conversion numbers,
# persists a weekly snapshot (system_monitor.seo_pilot_weekly), and Telegrams the
# summary + a "prompt Claude to review" checklist to Will.
# Model: run_ad_read_reminder.sh (Will's proposer-style reminder pattern), recurring.
cd /home/fields/Fields_Orchestrator
set -a && . .env && set +a
source /home/fields/venv/bin/activate 2>/dev/null
python3 scripts/brain2/seo_pilot_status.py --telegram >> logs/seo-pilot-review.log 2>&1
