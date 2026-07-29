#!/usr/bin/env python3
"""
organize_cycles.py — file the RL cycle .md docs into weekly → daily folders.

Layout:  cycles/<ISO-week>/<date>/<domain>_cycle_<stamp>.md
         e.g. cycles/2026-W31/2026-07-29/geo_cycle_20260729_1345.md

We're about to generate a LOT of these, so they get organised automatically. The cycle runners now
write straight into the dated folder (via the injected $CYCLE_DIR); this sweeper is the safety net —
it files any doc left in the cycles/ root, and it uses each file's **mtime in Brisbane** to decide the
folder (robust against a mis-stamped filename). If a filename's embedded DATE disagrees with its mtime
date, the file is also renamed to the correct Brisbane stamp. Idempotent — files already in a
week/day subfolder are left alone. Self-reports job 'cycle_organizer' to Systems Health (Rule 7).

Usage: python3 organize_cycles.py [--dry-run]
"""
import argparse
import os
import re
import sys
from datetime import datetime
from zoneinfo import ZoneInfo

AEST = ZoneInfo("Australia/Brisbane")
RL_DIR = os.path.dirname(os.path.abspath(__file__))
CYCLES = os.path.join(RL_DIR, "cycles")
NAME_RE = re.compile(r"^(?P<domain>[a-z_]+)_cycle_(?P<date>\d{8})_(?P<time>\d{4})\.md$")


def week_day(dt: datetime) -> tuple[str, str]:
    return dt.strftime("%G-W%V"), dt.strftime("%Y-%m-%d")


def organize(dry_run: bool = False) -> dict:
    if not os.path.isdir(CYCLES):
        return {"moved": 0, "renamed": 0, "skipped": 0}
    moved = renamed = skipped = 0
    for entry in sorted(os.listdir(CYCLES)):
        src = os.path.join(CYCLES, entry)
        if not os.path.isfile(src) or not entry.endswith(".md"):
            continue  # only sweep root-level .md files; subfolders are already filed
        m = NAME_RE.match(entry)
        # authoritative time = mtime in Brisbane (a filename stamp can be wrong)
        dt = datetime.fromtimestamp(os.path.getmtime(src), AEST)
        # if the filename encodes a DATE that disagrees with mtime's date, rename to the true stamp
        name = entry
        if m and m.group("date") != dt.strftime("%Y%m%d"):
            name = f"{m.group('domain')}_cycle_{dt.strftime('%Y%m%d_%H%M')}.md"
            renamed += 1
        week, day = week_day(dt)
        dst_dir = os.path.join(CYCLES, week, day)
        dst = os.path.join(dst_dir, name)
        if os.path.abspath(dst) == os.path.abspath(src):
            skipped += 1
            continue
        if os.path.exists(dst):  # don't clobber
            stem, ext = os.path.splitext(name)
            dst = os.path.join(dst_dir, f"{stem}_dup{ext}")
        print(f"  {entry}  ->  {week}/{day}/{os.path.basename(dst)}", flush=True)
        if not dry_run:
            os.makedirs(dst_dir, exist_ok=True)
            os.rename(src, dst)
        moved += 1
    return {"moved": moved, "renamed": renamed, "skipped": skipped}


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--dry-run", action="store_true")
    args = ap.parse_args()
    try:
        sys.path.insert(0, "/home/fields/Fields_Orchestrator/scripts")
        from job_status import job_run
    except Exception:
        job_run = None
    if job_run and not args.dry_run:
        with job_run("cycle_organizer", cadence_hours=24, title="RL cycle-doc organiser (weekly/daily folders)") as beat:
            r = organize(dry_run=False)
            beat.detail = f"moved {r['moved']}, renamed {r['renamed']}, skipped {r['skipped']}"
            print(f"[organize_cycles] {beat.detail}", flush=True)
    else:
        r = organize(dry_run=args.dry_run)
        print(f"[organize_cycles] {r} {'(dry-run)' if args.dry_run else ''}", flush=True)
    return 0


if __name__ == "__main__":
    sys.exit(main())
