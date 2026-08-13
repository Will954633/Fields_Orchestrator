#!/usr/bin/env python3
"""
Pre-warm self-serve off-market reports.

Renders the Property Positioning Report for eligible V4 properties ahead of
demand and publishes two artefacts:

    covers/<slug>.jpg        the front cover, shown in the page's report section
    <slug>/<ts>.pdf          the report itself

Both matter. The cover is what makes the section worth clicking; the PDF means a
pre-warmed address downloads INSTANTLY instead of waiting ~35s, because the
request endpoint reuses any completed build younger than 7 days.

⚠ ELIGIBILITY MIRRORS THE PAGE, and must keep mirroring it:
    - engine valuation range present  (the report's spine is the derived range;
      without one the valuation pages are a placeholder)
    - NOT waterfront                  (out of scope since 2026-07-26 — the
      comparable-sales model values it against dry comps)
A property the page will not offer must not be pre-warmed, or we spend ~35s of
VM time producing a PDF nobody can ever be shown.

Cost: ~35s and ~1.2 MB per property. Resumable — anything with a cover already
on disk is skipped, so it can be stopped and restarted freely.

    python3 scripts/prewarm_offmarket_covers.py --limit 100
    python3 scripts/prewarm_offmarket_covers.py --suburb robina --limit 500
"""

import argparse
import logging
import subprocess
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT))

from dotenv import load_dotenv

load_dotenv(REPO_ROOT / ".env")

from shared.db import get_gold_coast_db  # noqa: E402
from shared.waterfront import detect_waterfront  # noqa: E402

from scripts.offmarket_report_poller import (  # noqa: E402
    GENERATOR, VENV_PYTHON, JOB_TIMEOUT_SECONDS,
    _publish, _publish_cover, _shrink,
)

logging.basicConfig(level=logging.INFO, format="[%(asctime)s] %(message)s",
                    datefmt="%H:%M:%S")
logger = logging.getLogger(__name__)

BLOB_ROOT = Path("/data/blobs/off-market-reports")
V4_SUBURBS = ["robina", "burleigh_waters", "varsity_lakes"]


def eligible(suburb, limit):
    """Properties the page will actually offer a report for."""
    db = get_gold_coast_db()
    q = {
        "url_slug": {"$exists": True, "$ne": None},
        "valuation_data.confidence.range.low": {"$exists": True, "$ne": None},
        "valuation_data.confidence.reconciled_valuation": {"$exists": True, "$ne": None},
    }
    out = []
    for s in ([suburb] if suburb else V4_SUBURBS):
        for d in db[s].find(q):
            if (BLOB_ROOT / "covers" / f"{d['url_slug']}.jpg").exists():
                continue  # already warm — resumable
            if detect_waterfront(d).get("is_waterfront"):
                continue  # page will refuse it; do not spend a render
            out.append((str(d["_id"]), d["url_slug"], s))
            if limit and len(out) >= limit:
                return out
    return out


def warm_one(subject_id, slug):
    basename = f"prewarm_{slug}_{datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%S')}"
    proc = subprocess.run(
        [VENV_PYTHON, str(GENERATOR), "--subject-id", subject_id, "--self-serve",
         "--no-flatten-cover", "--output-basename", basename],
        capture_output=True, text=True, timeout=JOB_TIMEOUT_SECONDS, cwd=str(REPO_ROOT),
    )
    pdf = REPO_ROOT / "artifacts" / "appraisals_v4" / f"{basename}.pdf"
    if proc.returncode != 0 or not pdf.exists():
        return None, (proc.stderr or "")[-160:]

    screen = _shrink(pdf)
    pdf_url = _publish(screen, slug)
    _publish_cover(screen, slug)

    # Keep the audit's photo_sources BEFORE deleting the intermediates. Which
    # hero tier each cover used is the only scalable way to verify 7,730 covers
    # — `local_cadastral` in particular is usually an uncentred aerial showing
    # several homes, which reads badly on a cover printed with one address.
    # Deleting the audit made that unanswerable except by eye.
    audit = (REPO_ROOT / "artifacts" / "appraisals_v4" / f"{basename}.audit.json")
    sources = {}
    try:
        import json
        sources = json.loads(audit.read_text()).get("photo_sources") or {}
    except Exception:
        pass

    from shared.db import get_client
    get_client()["system_monitor"]["offmarket_report_covers"].update_one(
        {"slug": slug},
        {"$set": {"slug": slug, "cover_hero": sources.get("cover_hero"),
                  "satellite": sources.get("satellite"),
                  "pdf_url": pdf_url, "built_at": datetime.now(timezone.utc)}},
        upsert=True,
    )

    # The 11 MB source and its HTML siblings are pure intermediates once the
    # 1.2 MB screen copy is published. Keeping ~8,000 of them would be ~95 GB
    # against 27 GB free — the constraint that ruled out pre-generating in the
    # first place.
    for junk in (REPO_ROOT / "artifacts" / "appraisals_v4").glob(f"{basename}*"):
        try:
            junk.unlink()
        except Exception:
            pass
    return pdf_url, None


# ⚠ THE ORCHESTRATOR WINDOW IS A HARD EXCLUSION, NOT A PREFERENCE.
# The nightly pipeline starts 20:30 AEST and each worker here spawns Chromium +
# node + Ghostscript. Running both would contend for all 4 vCPU and, per Will,
# would likely take the VM down. The guard is checked before EVERY property, not
# once at startup, so a long run walks into the window and parks rather than
# ploughing through it.
BLACKOUT_START = 20      # 20:00 AEST — half an hour of headroom before 20:30
BLACKOUT_END = 6         # 06:00 AEST


def _aest_hour() -> int:
    from datetime import timedelta, timezone as _tz
    return (datetime.now(_tz(timedelta(hours=10)))).hour


def _in_blackout() -> bool:
    h = _aest_hour()
    return h >= BLACKOUT_START or h < BLACKOUT_END


def _wait_out_blackout():
    while _in_blackout():
        logger.info("orchestrator window (%02d:00 AEST) — parked, re-checking in 10 min",
                    _aest_hour())
        time.sleep(600)


def _warm_task(args_tuple):
    """Worker entry point. Must be module-level and picklable.

    ⚠ Drops the inherited MongoClient first. `shared.db` caches one at module
    level, ProcessPoolExecutor forks, and a forked client carries the parent's
    sockets and background monitor threads — pymongo warns about exactly this
    and the documented failure is a deadlock, not an error. On a 30-hour run a
    hung worker would be invisible until the batch simply stopped progressing.
    Each process therefore builds its own connection on first use.
    """
    import shared.db as _db
    _db._cached_client = None

    subject_id, slug = args_tuple
    try:
        url, err = warm_one(subject_id, slug)
        return slug, url, err
    except Exception as exc:                                    # noqa: BLE001
        return slug, None, f"{type(exc).__name__}: {exc}"


def main():
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--limit", type=int, default=50)
    ap.add_argument("--suburb", choices=V4_SUBURBS)
    ap.add_argument("--workers", type=int, default=1,
                    help="Parallel renders. Each spawns Chromium + node + Ghostscript, so this "
                         "is CPU-bound: 3 is the practical ceiling on a 4-vCPU VM. Ignore the "
                         "temptation to raise it — the bottleneck is the browser, not I/O.")
    ap.add_argument("--ignore-blackout", action="store_true",
                    help="Run through the 20:00-06:00 AEST orchestrator window. Do not use on "
                         "this VM: concurrent Chromium plus the nightly pipeline is what takes "
                         "it down.")
    args = ap.parse_args()

    targets = eligible(args.suburb, args.limit)
    logger.info("%d properties to warm, %d worker(s)", len(targets), args.workers)
    ok = fail = 0
    t0 = time.time()

    if args.workers <= 1:
        for i, (subject_id, slug, _suburb) in enumerate(targets, 1):
            if not args.ignore_blackout:
                _wait_out_blackout()
            slug, url, err = _warm_task((subject_id, slug))
            ok, fail = (ok + 1, fail) if url else (ok, fail + 1)
            logger.info("[%d/%d] %s %s", i, len(targets), slug,
                        "ok" if url else f"FAILED: {err}")
    else:
        from concurrent.futures import ProcessPoolExecutor, as_completed
        # Submitted in chunks rather than all at once so the blackout guard can
        # take effect mid-run: a single submit of 7,700 futures would run
        # straight through 20:30 no matter what the guard said.
        CHUNK = args.workers * 4
        done = 0
        for start in range(0, len(targets), CHUNK):
            if not args.ignore_blackout:
                _wait_out_blackout()
            chunk = [(s, sl) for s, sl, _ in targets[start:start + CHUNK]]
            with ProcessPoolExecutor(max_workers=args.workers) as pool:
                futures = {pool.submit(_warm_task, t): t[1] for t in chunk}
                for fut in as_completed(futures):
                    slug, url, err = fut.result()
                    done += 1
                    ok, fail = (ok + 1, fail) if url else (ok, fail + 1)
                    logger.info("[%d/%d] %s %s", done, len(targets), slug,
                                "ok" if url else f"FAILED: {err}")

    mins = (time.time() - t0) / 60
    logger.info("done: %d warmed, %d failed, %.1f min (%.1fs/property)",
                ok, fail, mins, (mins * 60 / max(ok + fail, 1)))
    # Non-zero when the batch achieved nothing despite having work — a silent
    # "0 warmed" run is indistinguishable from success otherwise (Rule 7b).
    if targets and ok == 0:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
