#!/usr/bin/env bash
# rl_dispatch.sh <domain> — GENERIC self-pacing poller. Asks cycle_pacer.py --job <domain>
# whether a cycle is DUE + under cap; only then launches rl_cycle.sh <domain>. Cron fires this
# cheaply every ~20 min; the heavy claude -p runs only when the domain's own last cycle scheduled it.
set -uo pipefail
DOMAIN="${1:?usage: rl_dispatch.sh <domain>}"
DIR=/home/fields/Fields_Orchestrator/16_General_Reinforcement_Learning
LOG="/home/fields/Fields_Orchestrator/logs/${DOMAIN}_dispatch.log"
STAMP=$(TZ=Australia/Brisbane date +%Y%m%d_%H%M)
cd /home/fields/Fields_Orchestrator
set -a; source ./.env; set +a
source /home/fields/venv/bin/activate 2>/dev/null || true
DECISION=$(PACER_JOB="$DOMAIN" python3 "$DIR/cycle_pacer.py" --job "$DOMAIN" --claim 2>&1); RC=$?
echo "[$STAMP] $DOMAIN: $DECISION" >> "$LOG"
if [ "$RC" -eq 0 ]; then
  echo "[$STAMP] launching rl_cycle.sh $DOMAIN" >> "$LOG"
  "$DIR/rl_cycle.sh" "$DOMAIN"
fi
exit 0
