#!/bin/bash
# Weekly reminder — Will + Claude to review valuation methodology & accuracy.
# Raised 2026-08-20. Fires Monday 08:00 AEST until the brief is marked DONE.
#
# Self-terminating: reads the brief's Status line. When it is no longer OPEN the
# reminder sends nothing and records success (the task is done — that IS the
# success path, not a failure). The cron line can then be removed at leisure.
#
# Self-reporting per CLAUDE.md Rule 7 + 7b: the heartbeat asserts an OUTCOME.
# A missing brief is an ERROR (the reminder has lost its subject), not a silent
# clean exit — otherwise a deleted/renamed brief would read as "nothing to do".
set -euo pipefail
cd /home/fields/Fields_Orchestrator
set -a && . .env && set +a

BRIEF="16_Valuation/METHODOLOGY_REVIEW_TASK.md"
PY=/home/fields/venv/bin/python3

STATUS="MISSING"
if [ -f "$BRIEF" ]; then
  STATUS=$(grep -m1 '^\*\*Status:\*\*' "$BRIEF" | sed -E 's/.*Status:\*\* *//' | tr -d '[:space:]')
fi

OUTCOME="success"
DETAIL="status=$STATUS"
if [ "$STATUS" = "MISSING" ]; then
  OUTCOME="error"
  DETAIL="brief file $BRIEF not found — reminder has no subject"
elif [ "$STATUS" = "OPEN" ]; then
  $PY scripts/telegram_notify.py "$(cat <<'MSG'
🔎 Valuation methodology & accuracy — weekly review nudge

The 80% bands measured below 80% on 2026-08-20 (Robina ~72%, Varsity ~75%, Burleigh ~76%),
a recalibration is sitting held from 2026-08-13, and the confidence tier is still
uncalibrated. Worth the full pass when you have a block of time.

Brief: 16_Valuation/METHODOLOGY_REVIEW_TASK.md
Reply here to book a session, or set its Status to DONE to stop this reminder.
MSG
)" >> logs/valuation-review-reminder.log 2>&1
  DETAIL="reminder sent (status OPEN)"
fi
# STATUS=DONE (or anything not OPEN/MISSING): send nothing, record success. Task finished.

$PY - "$OUTCOME" "$DETAIL" <<'PY' 2>/dev/null || true
import sys
sys.path.insert(0, "/home/fields/Fields_Orchestrator/scripts")
try:
    from job_status import record_job_result
    outcome, detail = sys.argv[1], sys.argv[2]
    # Weekly (Mon 08:00 AEST). stale_hours=200 (~8.3d) flags one missed week.
    record_job_result("valuation_review_reminder", outcome,
                      cadence_hours=168, stale_hours=200,
                      title="Valuation methodology review reminder (weekly)",
                      detail=detail)
except Exception as e:
    print("job_status record failed:", e)
PY

[ "$OUTCOME" = "error" ] && exit 1 || exit 0
