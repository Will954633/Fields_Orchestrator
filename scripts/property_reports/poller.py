"""
Property Reports Poller — picks up freshly-submitted stub docs and runs
the slot resolver. Designed to run as a systemd service on the
orchestrator VM (analogous to fields-trigger-poller).

Loops every POLL_INTERVAL_SECONDS, finds any property_reports docs in
state="stub" that are at least 5 seconds old (avoid racing the Netlify
submit), and runs build_property_report against each.

Quietly does nothing if no docs are pending.

Env:
    PROPERTY_REPORTS_POLL_INTERVAL — seconds between polls (default: 15)
    LOG_LEVEL                       — DEBUG / INFO / WARNING (default: INFO)
"""

from __future__ import annotations

import logging
import os
import signal
import sys
import time
from typing import Any, Dict

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..")))

from scripts.property_reports.build_property_report import (  # noqa: E402
    fetch_one, find_stub_slugs, resolve_one,
)
from scripts.job_status import job_run, record_job_result  # noqa: E402

POLL_INTERVAL = int(os.environ.get("PROPERTY_REPORTS_POLL_INTERVAL", "15"))
# How often the daemon proves it is still alive even when nothing is submitted.
# An idle poller is a SUCCESS (empty queue != failure, Rule 7b) — what must never
# be silent is the daemon being dead, or a build that produced nothing.
HEARTBEAT_SECONDS = int(os.environ.get("PROPERTY_REPORTS_HEARTBEAT_SECONDS", "1800"))

# Slots that make a report worth showing. A build that finishes with none of these
# is the zero-output path: it "succeeded" while producing an empty page. Until
# 2026-08-12 that was indistinguishable from a good build, which is how 22
# positioning failures accumulated unnoticed.
_CONTENT_SLOTS = (
    "comps", "statutory_cma", "your_street", "market_narrative", "comparables",
    "scarcity", "positioning", "positioning_thesis", "buyers", "case_studies",
    "walking_distance", "competitor_matches",
)


def _slots_resolved(slug):
    """Count approved slots on the freshly-built doc. Never raises."""
    try:
        doc = fetch_one(slug) or {}
        status = doc.get("slot_status") or {}
        return sorted(k for k in _CONTENT_SLOTS if status.get(k) == "approved")
    except Exception:
        return []

logging.basicConfig(
    level=os.environ.get("LOG_LEVEL", "INFO"),
    format="%(asctime)s %(levelname)s %(name)s %(message)s",
)
logger = logging.getLogger("property_reports_poller")

_RUN = True


def _stop(_signo, _frame):
    global _RUN
    logger.info("Shutdown signal received — exiting after current cycle")
    _RUN = False


def main():
    signal.signal(signal.SIGTERM, _stop)
    signal.signal(signal.SIGINT, _stop)
    logger.info(f"Property reports poller started (interval={POLL_INTERVAL}s)")

    cycles = 0
    built = 0
    failed = 0
    last_heartbeat = 0.0
    while _RUN:
        cycles += 1
        try:
            slugs = find_stub_slugs(min_age_seconds=5)
            if slugs:
                logger.info(f"Cycle {cycles}: found {len(slugs)} stub(s) to process")
                for slug in slugs:
                    doc = fetch_one(slug)
                    if not doc:
                        continue
                    # One heartbeat PER BUILD, with an outcome assertion (Rule 7b):
                    # a build that resolves no content slots must record as an error,
                    # not as a quiet success.
                    try:
                        with job_run("property_report_build", cadence_hours=168,
                                     title="House mini-site report build") as beat:
                            resolve_one(doc)
                            resolved = _slots_resolved(slug)
                            beat.metrics = {"slug": slug, "slots_resolved": len(resolved),
                                            "slots": resolved}
                            if not resolved:
                                raise RuntimeError(
                                    f"{slug}: build completed with 0 content slots — "
                                    "the report is empty, not merely sparse"
                                )
                            beat.detail = f"{slug}: {len(resolved)} slots"
                        built += 1
                        logger.info(f"  resolved {slug} ({len(resolved)} slots)")
                    except Exception as e:
                        failed += 1
                        logger.exception(f"  failed {slug}: {e}")
            else:
                logger.debug(f"Cycle {cycles}: no pending stubs")
        except Exception as e:
            logger.exception(f"Cycle {cycles} top-level error: {e}")

        # Daemon liveness heartbeat. Separate job from the per-build one so a quiet
        # week reads as "poller alive, nothing submitted" rather than "poller dead".
        now = time.time()
        if now - last_heartbeat >= HEARTBEAT_SECONDS:
            last_heartbeat = now
            try:
                record_job_result(
                    "property_report_poller", "success",
                    detail=f"alive; {cycles} cycles, {built} built, {failed} failed",
                    cadence_hours=HEARTBEAT_SECONDS / 3600.0,
                    title="House mini-site report poller (daemon)",
                    metrics={"cycles": cycles, "built": built, "failed": failed},
                )
            except Exception:
                logger.warning("heartbeat write failed", exc_info=True)

        # Sleep in 1-second steps so we respond to SIGTERM quickly
        for _ in range(POLL_INTERVAL):
            if not _RUN:
                break
            time.sleep(1)

    logger.info(f"Poller exited cleanly after {cycles} cycles")
    return 0


if __name__ == "__main__":
    sys.exit(main())
