#!/usr/bin/env python3
"""
Pre-warm self-serve off-market reports.

Renders the Property Positioning Report for eligible V4 properties ahead of
demand and publishes four artefacts:

    covers/<slug>.jpg                     front cover, shown in the report section
    <slug>/<ts>.pdf                       the published download
    <slug>/report.pdf                     durable copy the TRACKED VIEWER reads
    offmarket_report_requests row         what the ENDPOINT actually serves from

⚠ THE LAST TWO ARE NOT OPTIONAL, and their absence is what made the first two
useless. Until 2026-08-14 this script wrote only the cover and the PDF, and
recorded them in `offmarket_report_covers` — a collection
offmarket-report-request.mjs does not read. 2,443 finished reports were
therefore invisible to the endpoint serving them, and every visitor triggered a
~29s rebuild of a file already on disk. 3 Ripponlea Street was pre-built at
06:59 and rebuilt from scratch at 07:34 for a reader who gave up after 12s.
Without report.pdf the tracked viewer 404s, so a pre-warmed report would
download but record no open, no page and no dwell.

⚠ ELIGIBILITY MIRRORS THE PAGE, and must keep mirroring it:
    - engine valuation range present  (the report's spine is the derived range;
      without one the valuation pages are a placeholder)
    - NOT waterfront                  (out of scope since 2026-07-26 — the
      comparable-sales model values it against dry comps)
A property the page will not offer must not be pre-warmed, or we spend ~35s of
VM time producing a PDF nobody can ever be shown.

Cost: ~21s and ~1.2 MB per property. Resumable — anything with a fresh cover is
skipped, and anything that recently FAILED is skipped too (see the failure
memory in eligible(); without it the job re-attempts its own dead ends forever
and never reaches new work).

    # ad-hoc: fill gaps only
    python3 scripts/prewarm_offmarket_covers.py --suburb robina --limit 500

    # scheduled: also refresh anything nearing the end of its 7-day shelf life
    python3 scripts/prewarm_offmarket_covers.py --limit 1200 --workers 3 --max-age-days 7
"""

import argparse
import logging
import shutil
import subprocess
import sys
import time
from datetime import datetime, timedelta, timezone
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT))

from dotenv import load_dotenv

load_dotenv(REPO_ROOT / ".env")

from shared.db import get_client, get_gold_coast_db  # noqa: E402
from shared.waterfront import detect_waterfront  # noqa: E402

from scripts.job_status import job_run  # noqa: E402
from scripts.offmarket_report_poller import (  # noqa: E402
    GENERATOR, VENV_PYTHON, JOB_TIMEOUT_SECONDS,
    _mint_tracking, _publish, _publish_cover, _shrink, _wf_address,
)

logging.basicConfig(level=logging.INFO, format="[%(asctime)s] %(message)s",
                    datefmt="%H:%M:%S")
logger = logging.getLogger(__name__)

# ⚠ THE OUTCOME ASSERTION KEYS ON ERROR TYPE, NOT ON A COUNT.
#
# Two failed attempts I made at this, both wrong, both caught by running it:
#   1. "0 warmed and any work due" -> tripped on a single property that legitimately
#      had no resolvable hero image.
#   2. "0 warmed and >=20 due"     -> tripped on a batch of 25 that were ALL the same
#      legitimate refusal, because the unbuildable ones cluster together.
# No threshold on the COUNT can separate "25 properties we correctly declined" from
# "the generator is broken", because both look like zero output. Only the reason can.
#
# These are the generator's own guards firing as designed — a property we cannot
# honestly produce a report for. Any failure NOT matching one of these is unexplained
# and is what the heartbeat must go red on.
_EXPECTED_REFUSALS = (
    "no cover hero image could be resolved",   # every photo tier failed; refuses rather
                                               # than print a different house on the cover
    "no satellite image could be resolved",    # no coords, no aerial, no static map
    "property is waterfront",                  # out of scope since 2026-07-26
    "not found in gold_coast",                 # slug resolves to nothing
)


def _is_expected_refusal(err: str) -> bool:
    low = (err or "").lower()
    return any(p in low for p in _EXPECTED_REFUSALS)

BLOB_ROOT = Path("/data/blobs/off-market-reports")
V4_SUBURBS = ["robina", "burleigh_waters", "varsity_lakes"]


def eligible(suburb, limit, max_age_days=0, retry_failed_after_days=14):
    """Properties the page will actually offer a report for.

    ⚠ `max_age_days` is what makes the steady state real. A build carries a
    7-day shelf life on both sides — the substantiation records self-declare
    `valid_until = now + 7d`, and the request endpoint's CACHE_MAX_AGE_MS is the
    same 7 days — so a warm cache that is never refreshed simply expires and
    every visitor is back to a ~29s rebuild, silently. With `--max-age-days 7`
    an expiring build is re-queued BEFORE the endpoint stops honouring it.

    Default 0 keeps the original fill-the-gaps behaviour for one-off runs.
    """
    db = get_gold_coast_db()
    q = {
        "url_slug": {"$exists": True, "$ne": None},
        "valuation_data.confidence.range.low": {"$exists": True, "$ne": None},
        "valuation_data.confidence.reconciled_valuation": {"$exists": True, "$ne": None},
    }

    # One read for the whole catchment rather than a lookup per property: this
    # loop already walks ~8,000 docs and a per-slug find_one would add ~8,000
    # Cosmos round-trips to a function that is meant to be cheap.
    built_at, failed_at = {}, {}
    for c in get_client()["system_monitor"]["offmarket_report_covers"].find(
            {}, {"slug": 1, "built_at": 1, "failed_at": 1}):
        if c.get("built_at"):
            built_at[c["slug"]] = c["built_at"]
        if c.get("failed_at"):
            failed_at[c["slug"]] = c["failed_at"]
    now = datetime.now(timezone.utc)
    cutoff = now - timedelta(days=max_age_days) if max_age_days else None
    retry_cutoff = now - timedelta(days=retry_failed_after_days)

    out = []
    for s in ([suburb] if suburb else V4_SUBURBS):
        for d in db[s].find(q):
            slug = d["url_slug"]
            if (BLOB_ROOT / "covers" / f"{slug}.jpg").exists():
                if not max_age_days:
                    continue  # already warm — resumable
                stamp = built_at.get(slug)
                # A cover on disk with no recorded build date predates this
                # bookkeeping; treat it as stale so it gets a tracked row.
                if stamp and stamp.replace(tzinfo=timezone.utc) > cutoff:
                    continue  # still inside its shelf life

            # ⚠ FAILURE MEMORY. Without this the job cannot make progress past
            # its own dead ends: a property that CANNOT build never gets a
            # cover, so the "already warm" test above never excludes it and it
            # is re-attempted on every run, forever. Worse, they sort to the
            # front — measured 2026-08-14, 32 of the first 60 targets were
            # permanently unbuildable against 3.3% of the remainder, because
            # every prior run had already skimmed off everything that worked.
            # A 25-property test batch spent 23 renders re-failing the same
            # addresses.
            #
            # The dead end is real and not transient: ~181 eligible properties
            # carry no coordinates and no boundary aerial, so every hero tier
            # fails and the generator refuses rather than print the wrong house
            # on the cover. Retried after `retry_failed_after_days` so a genuine
            # fix upstream (coordinates backfilled, photos repointed) is still
            # picked up without anyone re-running this by hand.
            fstamp = failed_at.get(slug)
            if fstamp and fstamp.replace(tzinfo=timezone.utc) > retry_cutoff:
                continue

            if detect_waterfront(d).get("is_waterfront"):
                continue  # page will refuse it; do not spend a render
            out.append((str(d["_id"]), slug, s))
            if limit and len(out) >= limit:
                return out
    return out


def warm_one(subject_id, slug, suburb):
    basename = f"prewarm_{slug}_{datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%S')}"
    proc = subprocess.run(
        [VENV_PYTHON, str(GENERATOR), "--subject-id", subject_id, "--self-serve",
         "--no-flatten-cover", "--output-basename", basename],
        capture_output=True, text=True, timeout=JOB_TIMEOUT_SECONDS, cwd=str(REPO_ROOT),
    )
    pdf = REPO_ROOT / "artifacts" / "appraisals_v4" / f"{basename}.pdf"
    if proc.returncode != 0 or not pdf.exists():
        full = proc.stderr or ""
        # ⚠ CLASSIFY HERE, AGAINST THE FULL STDERR. The identifying phrase is in
        # the RuntimeError line; the 160-char tail handed back to the caller is
        # the operator advice that follows it. Re-deriving the verdict downstream
        # from that tail marked every legitimate refusal "unexplained" and would
        # have turned the heartbeat red on a perfectly healthy run.
        declined = _is_expected_refusal(full)
        err = full[-400:]
        # Remembered so eligible() can stop re-attempting a dead end every run.
        # Keep the generator's own words: the hero and waterfront guards raise
        # with actionable text, and "which of the guards fired, on how many" is
        # the only way to tell an upstream data gap from a broken generator.
        try:
            get_client()["system_monitor"]["offmarket_report_covers"].update_one(
                {"slug": slug},
                {"$set": {"slug": slug,
                          "failed_at": datetime.now(timezone.utc),
                          "error": err}},
                upsert=True,
            )
        except Exception:
            pass  # a lost failure note costs one wasted retry, not correctness
        return None, err[-160:], declined

    screen = _shrink(pdf)
    pdf_url = _publish(screen, slug)
    cover_url = _publish_cover(screen, slug)

    # ⚠ THE DURABLE COPY IS NOT OPTIONAL — the tracked viewer renders its pages
    # from this path, not from the blob. Omitting it (as this script did until
    # 2026-08-14) yields a report that downloads but cannot be READ in the
    # viewer, so every open/page/dwell event is lost.
    kept = BLOB_ROOT / slug / "report.pdf"
    kept.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy(screen, kept)

    client = get_client()
    address = _wf_address(client, subject_id, suburb) or slug.replace("-", " ").title()
    tracking_id = _mint_tracking(client, kept, slug, address)

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

    now = datetime.now(timezone.utc)
    sm = client["system_monitor"]
    sm["offmarket_report_covers"].update_one(
        {"slug": slug},
        {"$set": {"slug": slug, "cover_hero": sources.get("cover_hero"),
                  "satellite": sources.get("satellite"),
                  "pdf_url": pdf_url, "built_at": now},
         # A property that has just built is not a dead end any more. Leaving a
         # stale failed_at would keep excluding it for the backoff window even
         # though a good report now exists.
         "$unset": {"failed_at": "", "error": ""}},
        upsert=True,
    )

    # ⚠ THIS WRITE IS THE WHOLE POINT OF PRE-WARMING.
    #
    # offmarket-report-request.mjs answers readers from
    # `offmarket_report_requests` and NOTHING ELSE. Until 2026-08-14 this script
    # recorded only to `offmarket_report_covers`, so 2,443 finished reports were
    # invisible to the endpoint that serves them: every visitor triggered a
    # ~29s rebuild of a PDF already sitting on disk. 3 Ripponlea Street was
    # pre-built at 06:59 and rebuilt from scratch at 07:34 for a reader who left
    # after 12s. Two collections, no join — that was the entire bug.
    #
    # Keyed on (slug, source) so re-warming refreshes ONE prewarm row instead of
    # accumulating them, and never touches a real reader's request row. The
    # endpoint sorts by requested_at desc and reuses any completed build younger
    # than its 7-day window, so a fresh row here is served instantly.
    sm["offmarket_report_requests"].update_one(
        {"slug": slug, "source": "prewarm"},
        {"$set": {
            "slug": slug,
            "source": "prewarm",
            "status": "completed",
            "requested_at": now,
            "started_at": now,
            "finished_at": now,
            "pdf_url": pdf_url,
            "cover_url": cover_url,
            "tracking_id": tracking_id,
            "viewer_url": f"https://fieldsestate.com.au/track/view/{tracking_id}"
                          if tracking_id else None,
            "size_mb": round(screen.stat().st_size / 1_048_576, 2),
            "subject_id": subject_id,
            "suburb": suburb,
            "error": None,
            # No user_agent / country: nobody asked for this one. Their absence
            # is how a pre-warm is told apart from a real request in the funnel.
        }},
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
    return pdf_url, None, False


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

    subject_id, slug, suburb = args_tuple
    try:
        url, err, declined = warm_one(subject_id, slug, suburb)
        return slug, url, err, declined
    except Exception as exc:                                    # noqa: BLE001
        # An exception escaping warm_one is never an expected refusal — those
        # come back as a return value. This is the harness itself failing.
        return slug, None, f"{type(exc).__name__}: {exc}", False


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
    ap.add_argument("--max-age-days", type=int, default=0,
                    help="Also re-warm builds older than N days. Use 7 on the scheduled run: "
                         "both the substantiation valid_until and the endpoint's cache window "
                         "are 7 days, so without this the cache expires and never refills.")
    ap.add_argument("--retry-failed-after-days", type=int, default=14,
                    help="Re-attempt a property that previously failed to build only after N "
                         "days. ~181 eligible properties have no coordinates and can never "
                         "render a cover; without this they are retried every run and, because "
                         "they never acquire a cover, crowd the front of the queue.")
    ap.add_argument("--no-heartbeat", action="store_true",
                    help="Skip the job_runs heartbeat. For ad-hoc runs only — a scheduled run "
                         "must report, or its failure is invisible (Rule 7).")
    args = ap.parse_args()

    # Rule 7b, stated once and enforced on both paths: "nothing to do" is
    # success; "had work and achieved none" is not. An empty target list means
    # every eligible report is inside its shelf life — the good outcome, and the
    # one this job exists to reach.
    #
    # ⚠ "0 warmed" IS NOT AUTOMATICALLY A FAULT — see _EXPECTED_REFUSALS. A run
    # that correctly declined every property it was handed did its job. A run
    # that failed for reasons nobody anticipated did not, however many succeeded
    # alongside. So the assertion fires on UNEXPLAINED failures only, and it does
    # not wait for the batch to be a total loss.
    def _assert_outcome(ok, refused, unexplained, considered):
        if unexplained:
            raise RuntimeError(
                f"{unexplained} of {considered} builds failed for reasons that are not "
                f"recognised per-property refusals ({ok} warmed, {refused} correctly "
                f"declined) — see offmarket_report_covers.error")

    if args.no_heartbeat:
        _assert_outcome(*_run(args))
        return

    with job_run("offmarket_report_prewarm", cadence_hours=24,
                 title="Off-Market Report Pre-Warm") as beat:
        ok, refused, unexplained, considered = _run(args)
        beat.metrics = {"warmed": ok, "declined": refused,
                        "unexplained": unexplained, "considered": considered}
        beat.detail = (f"{ok} warmed, {refused} declined, "
                       f"{unexplained} unexplained of {considered} due")
        _assert_outcome(ok, refused, unexplained, considered)


def _run(args):
    targets = eligible(args.suburb, args.limit, args.max_age_days,
                       args.retry_failed_after_days)
    logger.info("%d properties to warm, %d worker(s)", len(targets), args.workers)
    ok = refused = unexplained = 0
    t0 = time.time()

    def _tally(url, declined):
        """Success / correctly-declined / unexplained. See _EXPECTED_REFUSALS."""
        nonlocal ok, refused, unexplained
        if url:
            ok += 1
        elif declined:
            refused += 1
        else:
            unexplained += 1

    if args.workers <= 1:
        for i, (subject_id, slug, suburb) in enumerate(targets, 1):
            if not args.ignore_blackout:
                _wait_out_blackout()
            slug, url, err, declined = _warm_task((subject_id, slug, suburb))
            _tally(url, declined)
            logger.info("[%d/%d] %s %s", i, len(targets), slug,
                        "ok" if url else f"{'declined' if declined else 'FAILED'}: {err}")
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
            chunk = list(targets[start:start + CHUNK])
            with ProcessPoolExecutor(max_workers=args.workers) as pool:
                futures = {pool.submit(_warm_task, t): t[1] for t in chunk}
                for fut in as_completed(futures):
                    slug, url, err, declined = fut.result()
                    done += 1
                    _tally(url, declined)
                    logger.info("[%d/%d] %s %s", done, len(targets), slug,
                                "ok" if url else f"{'declined' if declined else 'FAILED'}: {err}")

    mins = (time.time() - t0) / 60
    logger.info("done: %d warmed, %d declined, %d unexplained, %.1f min (%.1fs/property)",
                ok, refused, unexplained, mins,
                (mins * 60 / max(len(targets), 1)))
    return ok, refused, unexplained, len(targets)


if __name__ == "__main__":
    main()
