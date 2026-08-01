#!/usr/bin/env bash
# Lead-intelligence pipeline — unifies + enriches + flags every lead into
# system_monitor.lead_worklist.
#
# NOT the cron entrypoint any more (2026-08-01). scripts/nightly_lead_chain.py now
# runs lead_intelligence.py + seller_intent.py itself at 00:15, in order, between
# crm_sync and live_leads_to_sheet — the sheet's Situation column reads what these
# two write, so it has to run BEFORE the sheet, not at 02:00 after it. Kept as a
# convenient manual "just rebuild the worklist" shortcut.
set -euo pipefail
cd /home/fields/Fields_Orchestrator
set -a
source ./.env
set +a
export GH_CONFIG_DIR=/home/projects/.config/gh
/home/fields/venv/bin/python3 scripts/samantha/lead_intelligence.py "$@"

# Seller-intent enrichment layer — runs right after the worklist rebuild so it
# enriches fresh data. Self-monitored via job_run (Rule 7). Mirror --dry-run through.
if [[ " $* " == *" --dry-run "* ]]; then SI_ARGS="--dry-run"; else SI_ARGS=""; fi
exec /home/fields/venv/bin/python3 scripts/samantha/seller_intent.py --all $SI_ARGS
