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

POLL_INTERVAL = int(os.environ.get("PROPERTY_REPORTS_POLL_INTERVAL", "15"))

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
                    try:
                        resolve_one(doc)
                        logger.info(f"  resolved {slug}")
                    except Exception as e:
                        logger.exception(f"  failed {slug}: {e}")
            else:
                logger.debug(f"Cycle {cycles}: no pending stubs")
        except Exception as e:
            logger.exception(f"Cycle {cycles} top-level error: {e}")

        # Sleep in 1-second steps so we respond to SIGTERM quickly
        for _ in range(POLL_INTERVAL):
            if not _RUN:
                break
            time.sleep(1)

    logger.info(f"Poller exited cleanly after {cycles} cycles")
    return 0


if __name__ == "__main__":
    sys.exit(main())
