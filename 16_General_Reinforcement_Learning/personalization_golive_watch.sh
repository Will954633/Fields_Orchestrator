#!/usr/bin/env bash
# Waits for the onsite cycle's FIRST serving experiment, then flips the master kill-switch
# (Will authorised: flip on after propose + load re-check). Telegrams Will either way. One-shot.
set -uo pipefail
cd /home/fields/Fields_Orchestrator
set -a; source ./.env; set +a; source /home/fields/venv/bin/activate 2>/dev/null || true
D=16_General_Reinforcement_Learning
for i in $(seq 1 90); do   # up to ~45 min
  N=$(python3 "$D/experiment_manager.py" list --serving 2>/dev/null | grep -c "onsite_exp" || true)
  if [ "${N:-0}" -ge 1 ]; then
    python3 "$D/enable_personalization.py" --rollout 100 >> logs/personalization_golive.log 2>&1
    exit 0
  fi
  sleep 30
done
python3 - <<'PY' 2>/dev/null || true
import sys; sys.path.insert(0,"scripts")
from telegram_notify import send_telegram
send_telegram("⏳ Onsite cycle hasn't served a first experiment within 45min — personalization kill-switch stays OFF. It'll go live on the next cycle that proposes one.")
PY
exit 0
