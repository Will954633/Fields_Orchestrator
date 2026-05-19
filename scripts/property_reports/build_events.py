"""
BuildEventEmitter — pushes incremental progress events to
`property_reports.build_events[]` so the live build page can stream them
to the user while their house website is being assembled.

Each resolver step in SlotResolver calls emitter.start() then emitter.done()
(or .fail() on exception). Each call writes immediately to MongoDB via $push
so the frontend polling endpoint sees them in real time — we never batch
events to the end of the run.

Default emitter is a no-op (NullEmitter). Pass BuildEventEmitter when you
want live progress — typically only in the production resolver path.
"""

from __future__ import annotations

import logging
from datetime import datetime
from typing import Any, Dict

logger = logging.getLogger(__name__)


class NullEmitter:
    """No-op emitter — used by tests, dry-runs, and any caller that doesn't
    need the live build feed."""

    def start(self, step: str, label: str) -> None:
        pass

    def done(self, step: str, label: str, **extra: Any) -> None:
        pass

    def fail(self, step: str, error: str) -> None:
        pass


class BuildEventEmitter:
    """Live emitter — pushes events to property_reports.build_events[] on
    every call. Writes go through cosmos_retry so RU exhaustion doesn't
    drop events.
    """

    def __init__(self, coll, slug: str, retry):
        self.coll = coll
        self.slug = slug
        self.retry = retry

    def _push(self, event: Dict[str, Any]) -> None:
        try:
            self.retry(
                lambda: self.coll.update_one(
                    {"slug": self.slug},
                    {
                        "$push": {"build_events": event},
                        "$set": {"last_build_event_at": event.get("at")},
                    },
                ),
                label=f"build_events.push.{self.slug}",
            )
        except Exception as e:
            logger.warning(f"build_events push failed for {self.slug}: {e}")

    def start(self, step: str, label: str) -> None:
        self._push({
            "step": step,
            "label": label,
            "phase": "running",
            "at": datetime.utcnow(),
        })

    def done(self, step: str, label: str, **extra: Any) -> None:
        evt: Dict[str, Any] = {
            "step": step,
            "label": label,
            "phase": "done",
            "at": datetime.utcnow(),
        }
        if extra:
            evt["data"] = extra
        self._push(evt)

    def fail(self, step: str, error: str) -> None:
        self._push({
            "step": step,
            "phase": "failed",
            "error": (error or "")[:280],
            "at": datetime.utcnow(),
        })
