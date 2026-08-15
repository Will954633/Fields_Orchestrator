#!/usr/bin/env python3
"""
brain_drive_nightly.py — nightly refresh of the Google-Drive knowledge that feeds the brains.

Pipeline (all on the Max subscription — Haiku; no metered API):
  1. drive_brain_ingest.py --emit --delta   → walk Drive, classify each doc (Brain 1 / Brain 3 /
                                               exclude), emit only NEW/CHANGED units to batches_b1
                                               (external) + batches_b3 (internal).
  2. brain3_annotate.py --pool b1 / --pool b3 --base /home/fields/brain_drive
                                               → annotate the new batches (Haiku on Max).
  3. Rebuild BRAIN 1 = coaching corpus + KB public books + Drive-external, applying the
     Drive-external tombstones. (This script OWNS the Brain 1 rebuild — nothing else does.)

  Brain 3 is rebuilt by run_ops_nightly.sh, which already merges the Drive-internal annotations
  (annotations_b3.jsonl) — kept there so Brain 3 has a single rebuild owner. This nightly is
  scheduled BEFORE the ops nightly so annotations_b3 is fresh when ops rebuilds.

Self-monitors via job_run("brain_drive_refresh", cadence_hours=24) → Systems Health Process
Registry. On Max quota exhaustion the annotate step pauses cleanly (MaxQuotaExhausted) and this
run records an error heartbeat (visible), never a silent skip.

Run: python3 scripts/samantha/brain_drive_nightly.py   (add --no-telegram to suppress the ping)
"""
import os, sys, subprocess, json, argparse
from datetime import datetime, timezone

ORCH = "/home/fields/Fields_Orchestrator"
HERE = os.path.join(ORCH, "scripts", "samantha")
sys.path.insert(0, os.path.join(ORCH, "scripts"))  # job_status
from job_status import job_run

DRIVE = "/home/fields/brain_drive"
B1 = "/home/fields/brain1_build"
B3PUB = "/home/fields/brain3_build"          # KB public book annotations (external pool)
LOG = f"{DRIVE}/nightly.log"


def _env():
    e = dict(os.environ)
    for k in ("CLAUDECODE", "CLAUDE_CODE_ENTRYPOINT", "CLAUDE_CODE_SSE_PORT"):
        e.pop(k, None)
    e.setdefault("CI", "true")
    return e


def run(cmd, timeout=None):
    with open(LOG, "a") as fh:
        fh.write(f"\n{datetime.now(timezone.utc).isoformat()} $ {' '.join(cmd)}\n")
    r = subprocess.run(cmd, cwd=ORCH, env=_env(), timeout=timeout,
                       stdout=open(LOG, "a"), stderr=subprocess.STDOUT)
    if r.returncode != 0:
        raise RuntimeError(f"step failed (exit {r.returncode}): {' '.join(cmd[:3])}… — see {LOG}")


def count_lines(p):
    return sum(1 for _ in open(p)) if os.path.exists(p) else 0


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--no-telegram", action="store_true")
    ap.add_argument("--full", action="store_true", help="full re-emit (not delta) — first build / rare")
    args = ap.parse_args()
    py = sys.executable

    with job_run("brain_drive_refresh", cadence_hours=24,
                 title="Brain Drive ingest → Brain 1/3") as beat:
        before_b1 = count_lines(f"{DRIVE}/annotations_b1.jsonl")
        before_b3 = count_lines(f"{DRIVE}/annotations_b3.jsonl")

        # 1. ingest (classify + emit delta batches)
        ingest = [py, f"{HERE}/drive_brain_ingest.py", "--emit"]
        if not args.full:
            ingest.append("--delta")
        run(ingest, timeout=1800)

        # 2. annotate both pools on Max (Haiku). Empty pool = no-op (annotate sees 0 todo).
        for pool in ("b1", "b3"):
            if os.path.isdir(f"{DRIVE}/batches_{pool}"):
                run([py, f"{HERE}/brain3_annotate.py", "--pool", pool, "--base", DRIVE], timeout=7200)

        # 3. rebuild BRAIN 1 = coaching + KB public + Drive-external + YouTube
        #
        # ⚠ THIS IS THE SOLE NIGHTLY OWNER OF package.json. It rebuilds the graph
        # from exactly the list below, so ANY corpus missing from it is deleted
        # from Brain 1 at 03:10 every night — silently, with a success exit.
        # That is what happened on 2026-08-09: a 2,264-unit YouTube corpus was
        # merged by hand at 17:00 and was gone by 03:12, reverting 8,664 -> 6,400
        # units. See fix-history [BRAIN1-NIGHTLY-REBUILD-DROPS-SOURCES].
        #
        # Adding a new Brain 1 corpus means adding it HERE, not just merging it once.
        BRAIN1_SOURCES = [
            f"{B3PUB}/annotations_public.jsonl",           # k#### KB public books
            f"{DRIVE}/annotations_b1.jsonl",               # i######### Drive external
            "/home/fields/brain1_yt/annotations.jsonl",    # u9##### YouTube channels
            "/home/fields/brain1_books/annotations.jsonl",  # k9#### raw-.txt books
            "/home/fields/brain1_build/Spotify/annotations.jsonl",  # u8##### podcasts
        ]
        merges = [p for p in BRAIN1_SOURCES if os.path.exists(p)]
        missing = [p for p in BRAIN1_SOURCES if not os.path.exists(p)]
        if missing:
            # A source that vanishes is a corpus silently leaving the graph. Say so
            # in the log rather than quietly building a smaller brain.
            with open(LOG, "a") as fh:
                fh.write(f"{datetime.now(timezone.utc).isoformat()} "
                         f"⚠ Brain 1 source(s) MISSING — graph will be built "
                         f"WITHOUT them: {missing}\n")
        cmd = [py, f"{HERE}/brain1_graph.py", "--in", f"{B1}/annotations.jsonl",
               "--outdir", B1, "--dedupe"]
        if merges:
            cmd += ["--merge"] + merges
        if os.path.exists(f"{DRIVE}/tombstones_b1.json"):
            cmd += ["--tombstones", f"{DRIVE}/tombstones_b1.json"]
        run(cmd, timeout=1800)

        after_b1 = count_lines(f"{DRIVE}/annotations_b1.jsonl")
        after_b3 = count_lines(f"{DRIVE}/annotations_b3.jsonl")
        new_b1, new_b3 = after_b1 - before_b1, after_b3 - before_b3
        beat.detail = f"Drive→brains: +{new_b1} external (Brain 1), +{new_b3} internal (Brain 3) unit(s)"
        beat.metrics = {"drive_b1_units": after_b1, "drive_b3_units": after_b3,
                        "new_b1": new_b1, "new_b3": new_b3}

        if (new_b1 or new_b3) and not args.no_telegram:
            try:
                subprocess.run([py, f"{ORCH}/scripts/telegram_notify.py",
                                f"🧠 Brain Drive refresh: +{new_b1} external unit(s) → Brain 1, "
                                f"+{new_b3} internal unit(s) → Brain 3 (Google Drive). Graphs rebuilt."],
                               cwd=ORCH, env=_env(), timeout=30)
            except Exception:
                pass


if __name__ == "__main__":
    main()
