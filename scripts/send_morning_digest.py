#!/usr/bin/env python3
"""send_morning_digest.py — drain the queued routine notifications into ONE message.

Why this exists
---------------
Before 2026-08-10 every reporting job Telegrammed Will independently: the Systems
Health board at 01:00, the Brain 3 refresh line at 03:35, the Samantha ops triage
cycle at 07:15, the unpushed-code check at 09:10. Four buzzes, all of them routine
status rather than anything needing a response in the moment, all of them read in
one sitting hours later anyway. Worse, three of the four re-sent a near-identical
body every night — the health board alone repeated ~46 red rows nightly of which
only 2-4 were new.

Batching is deliberately the ONLY thing this changes. Nothing is suppressed: every
queued message appears in full, in source order, under its own heading. Anything
genuinely time-sensitive — a new Analyse Your Home lead, a hot lead, the whale, a
failed code backup, an integrity violation — still calls send_message() directly
and is untouched by this file.

Scheduled 09:30 AEST, i.e. after all four producers have run.

Rule 7 / 7b contract
--------------------
Wrapped in job_run() so it self-reports to the Systems Health Process Registry, and
it asserts an OUTCOME rather than merely not throwing: an empty queue on a morning
when the producers should have run is reported as an error, because "nothing to say"
and "the producers all died" are otherwise indistinguishable. Entries are only
marked sent AFTER Telegram confirms delivery, so a failed send re-digests tomorrow
rather than being silently consumed (the watermark lesson from [INDEXING-SILENT-ZERO]).
"""
import os
import sys
from datetime import datetime, timedelta, timezone

sys.path.insert(0, "/home/fields/Fields_Orchestrator")
sys.path.insert(0, "/home/fields/Fields_Orchestrator/scripts")

from shared.env import load_env  # type: ignore
from shared.db import get_client  # type: ignore
from job_status import job_run  # type: ignore

AEST = timezone(timedelta(hours=10))
# Below this many hours with an empty queue we assume a genuine quiet morning is
# impossible: the health board and the ops cycle both run unconditionally daily.
MAX_TELEGRAM_CHARS = 3800  # Telegram hard-caps at 4096; leave room for the header


def main():
    load_env()
    with job_run("morning_digest", cadence_hours=24, stale_hours=30,
                 title="Morning Telegram digest") as beat:
        sm = get_client()["system_monitor"]
        col = sm["telegram_digest"]
        pending = list(col.find({"sent": False}).sort("queued_at", 1))

        beat.metrics = {"queued": len(pending)}

        if not pending:
            # Rule 7b: an empty queue is NOT success here. The health board (01:00) and
            # the ops cycle (07:15) both queue unconditionally every single day, so zero
            # entries means those jobs did not run, not that all is well.
            raise RuntimeError(
                "digest queue empty — the health board and ops cycle queue daily, so "
                "an empty queue means those producers did not run, not that there was "
                "nothing to report")

        now = datetime.now(AEST)
        parts = [f"🗞 Morning digest — {now:%a %d %b, %H:%M AEST} ({len(pending)} report(s))"]
        for doc in pending:
            body = (doc.get("text") or "").strip()
            if not body:
                continue
            parts.append(f"\n━━━ {doc.get('heading') or doc.get('source')} ━━━\n{body}")

        text = "\n".join(parts)
        truncated = False
        if len(text) > MAX_TELEGRAM_CHARS:
            # Never silently drop: say exactly what was cut and where to read it.
            text = text[:MAX_TELEGRAM_CHARS].rstrip()
            text += (f"\n\n… digest truncated at {MAX_TELEGRAM_CHARS} chars. "
                     f"Full entries: system_monitor.telegram_digest")
            truncated = True

        from telegram_notify import send_message, TelegramSendError
        try:
            send_message(text, parse_mode="")
        except TelegramSendError as e:
            # Do NOT mark sent — tomorrow's digest carries these forward.
            raise RuntimeError(f"digest send failed, {len(pending)} entries retained: {e}")

        col.update_many({"_id": {"$in": [d["_id"] for d in pending]}},
                        {"$set": {"sent": True, "sent_at": datetime.now(timezone.utc)}})

        # Housekeeping: keep 30 days of sent entries for auditing, drop older.
        col.delete_many({"sent": True,
                         "sent_at": {"$lt": datetime.now(timezone.utc) - timedelta(days=30)}})

        beat.metrics = {"queued": len(pending), "chars": len(text), "truncated": truncated}
        beat.detail = (f"{len(pending)} report(s) delivered as one message"
                       + (" (truncated)" if truncated else ""))
        print(beat.detail)


if __name__ == "__main__":
    main()
