"""
run_ingest_cron.py — weekly PropRadar sold-data refresh for the core suburbs.

Runs ingest (→ propradar_sold) + link (→ propradar_property_id + coverage gaps) for
each core suburb, then SELF-REPORTS the outcome to system_monitor.job_runs via
job_status.record_job_result('propradar_ingest', ...). That record is surfaced on the
"Fields Systems Health" sheet by main_site_health_check.py's collect_propradar_ingest —
so a failure shows up as an ERROR row instead of the feed silently going stale and
volume/months-of-supply drifting back to the Domain-scrape undercount. A Telegram alert
fires on failure as a second safety net.

Cron (weekly, Sunday 05:30 AEST — VM cron runs in Australia/Brisbane; keeps
propradar_sold fresh ahead of the 1st-of-month precompute + 3rd market-pulse jobs):
    30 5 * * 0  cd /home/fields/Fields_Orchestrator && set -a && source .env && set +a && \
      /home/fields/venv/bin/python3 scripts/propradar/run_ingest_cron.py \
      >> logs/propradar-ingest.log 2>&1
"""
from __future__ import annotations

import os
import sys
import traceback

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(os.path.dirname(HERE))
sys.path.insert(0, ROOT)
sys.path.insert(0, os.path.join(ROOT, "scripts"))
sys.path.insert(0, HERE)

import ingest_sold          # noqa: E402
import link_property_ids    # noqa: E402
from job_status import record_job_result  # noqa: E402

SUBURBS = ["robina", "burleigh_waters", "varsity_lakes"]
JOB = "propradar_ingest"


def _alert(msg: str):
    try:
        from telegram_notify import send_message
        send_message(msg)
    except Exception as e:
        print(f"(telegram alert failed: {e})")


def main():
    try:
        total_recs = total_linked = total_gaps = 0
        per = []
        for s in SUBURBS:
            recs = ingest_sold.ingest(s, months=60, apply=True)
            matched, gaps = link_property_ids.link(s, apply=True)
            total_recs += len(recs)
            total_linked += len(matched)
            total_gaps += len(gaps)
            per.append(f"{s} {len(recs)}/{len(matched)}/{len(gaps)}")
        detail = (f"ingested {total_recs}, linked {total_linked}, gaps {total_gaps} "
                  f"[{'; '.join(per)}]")
        record_job_result(JOB, "success", detail, records=total_recs,
                          linked=total_linked, gaps=total_gaps, suburbs=len(SUBURBS))
        print("OK:", detail)
    except Exception as e:
        detail = f"{type(e).__name__}: {e}"
        record_job_result(JOB, "error", detail[:300], suburbs=len(SUBURBS))
        _alert(f"⚠️ PropRadar ingest FAILED\n{detail}")
        print("FAILED:", detail)
        traceback.print_exc()
        sys.exit(1)


if __name__ == "__main__":
    main()
