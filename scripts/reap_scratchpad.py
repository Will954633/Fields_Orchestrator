#!/usr/bin/env python3
"""
reap_scratchpad.py — delete stale Claude Code session scratchpad dirs.

The harness creates one dir per session under
/tmp/claude-1001/<project>/ and never cleans them. They accumulate
(761 dirs / ~3G observed 2026-08-28) and are the reason `/` never trends
back below 85%: the built-in disk auto-cleanup only touches caches/logs,
not this path. This reaps session dirs older than RETAIN_DAYS.

Ongoing process -> self-reports via job_run (CLAUDE.md Rule 7 / 7b).
The zero-output path here (Rule 7b) is: if the base dir does not exist,
the harness path changed and the reaper is silently no-op'ing forever ->
raise. An empty result when the dir DOES exist is legitimately "nothing
old to reap" and is success.
"""
from __future__ import annotations
import os
import shutil
import sys
import time

sys.path.insert(0, os.path.join(os.path.dirname(__file__)))
from job_status import job_run  # noqa: E402

BASE = "/tmp/claude-1001/-home-fields-Fields-Orchestrator"
RETAIN_DAYS = 2
RETAIN_SECS = RETAIN_DAYS * 86400


def main():
    with job_run("reap_scratchpad", cadence_hours=24,
                 title="Scratchpad Reaper (/tmp)") as beat:
        if not os.path.isdir(BASE):
            # Rule 7b: a missing base dir means the harness path moved, not
            # that there's nothing to do. Fail loudly rather than pretend clean.
            raise RuntimeError(
                f"scratchpad base {BASE} does not exist — harness path changed?")

        now = time.time()
        removed = 0
        freed_bytes = 0
        errors = 0
        for name in os.listdir(BASE):
            path = os.path.join(BASE, name)
            if not os.path.isdir(path):
                continue
            try:
                if now - os.path.getmtime(path) < RETAIN_SECS:
                    continue
                # size before removal (best-effort)
                sz = 0
                for root, _dirs, files in os.walk(path):
                    for f in files:
                        try:
                            sz += os.path.getsize(os.path.join(root, f))
                        except OSError:
                            pass
                shutil.rmtree(path, ignore_errors=True)
                removed += 1
                freed_bytes += sz
            except OSError:
                errors += 1

        freed_mb = round(freed_bytes / 1_048_576, 1)
        beat.metrics = {"removed": removed, "freed_mb": freed_mb, "errors": errors}
        beat.detail = f"reaped {removed} dirs, freed {freed_mb} MB"
        print(beat.detail)


if __name__ == "__main__":
    main()
