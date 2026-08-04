#!/bin/bash
# Monthly reminder — runs on the 1st of every month.
#
# Self-reports to system_monitor.job_runs (CLAUDE.md Rule 7) rather than relying on
# log freshness: this script and run_market_pulse.sh both append to the SHARED
# logs/market-pulse.log, so a log-mtime probe cannot tell which of the two ran. The
# health board read MISSING until 2026-08-05 because its registry row looked for a
# per-job pulse-reminder.log that never existed.
cd /home/fields/Fields_Orchestrator
set -a && . .env && set +a
/home/fields/venv/bin/python3 scripts/telegram_notify.py --market-pulse-reminder >> logs/market-pulse.log 2>&1
RC=$?

/home/fields/venv/bin/python3 - "$RC" <<'PY' 2>/dev/null || true
import sys
sys.path.insert(0, "/home/fields/Fields_Orchestrator/scripts")
try:
    from job_status import record_job_result
    rc = int(sys.argv[1])
    # Monthly (1st @ 08:00 AEST). stale_hours=800 (~33d) so one missed month flags
    # without crying stale during a normal 28-31 day gap.
    record_job_result("market_pulse_reminder", "success" if rc == 0 else "error",
                      cadence_hours=744, stale_hours=800,
                      title="Market Pulse reminder (1st of month)",
                      detail=f"telegram reminder rc={rc}")
except Exception as e:
    print("job_status record failed:", e)
PY
exit $RC
