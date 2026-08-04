#!/bin/bash
# Fallback market pulse generator — runs on the 3rd of every month
# Only generates summaries for categories NOT manually updated this month
#
# Self-reports to system_monitor.job_runs (CLAUDE.md Rule 7) rather than relying on
# log freshness: this script and run_pulse_reminder.sh both append to the SHARED
# logs/market-pulse.log, so a log-mtime probe cannot tell which of the two ran. The
# health board read MISSING until 2026-08-05 because its registry row looked for a
# per-job market-pulse-auto.log that never existed.
cd /home/fields/Fields_Orchestrator
set -a && . .env && set +a
echo "$(date): Running fallback pulse generation (skipping manual updates)..." >> logs/market-pulse.log
/home/fields/venv/bin/python3 scripts/generate_market_pulse.py >> logs/market-pulse.log 2>&1
RC=$?

/home/fields/venv/bin/python3 - "$RC" <<'PY' 2>/dev/null || true
import sys
sys.path.insert(0, "/home/fields/Fields_Orchestrator/scripts")
try:
    from job_status import record_job_result
    rc = int(sys.argv[1])
    # Monthly (3rd @ 06:00 AEST). stale_hours=800 (~33d) so one missed month flags
    # without crying stale during a normal 28-31 day gap. NB a clean run that skips
    # every category (because Will wrote them manually) is still a success — this
    # job's contract is "the fallback ran", not "it generated something".
    record_job_result("market_pulse_auto_fallback", "success" if rc == 0 else "error",
                      cadence_hours=744, stale_hours=800,
                      title="Market Pulse auto-fallback (3rd of month)",
                      detail=f"fallback generation rc={rc}")
except Exception as e:
    print("job_status record failed:", e)
PY
exit $RC
