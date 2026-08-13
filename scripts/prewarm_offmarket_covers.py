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

    # The 11 MB source and its HTML/audit siblings are pure intermediates once
    # the 1.2 MB screen copy is published. Keeping ~8,000 of them would be ~95 GB
    # against 27 GB free — the constraint that ruled out pre-generating in the
    # first place.
    for junk in (REPO_ROOT / "artifacts" / "appraisals_v4").glob(f"{basename}*"):
        try:
            junk.unlink()
        except Exception:
            pass
    return pdf_url, None


def main():
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--limit", type=int, default=50)
    ap.add_argument("--suburb", choices=V4_SUBURBS)
    args = ap.parse_args()

    targets = eligible(args.suburb, args.limit)
    logger.info("%d properties to warm", len(targets))
    ok = fail = 0
    t0 = time.time()
    for i, (subject_id, slug, suburb) in enumerate(targets, 1):
        try:
            url, err = warm_one(subject_id, slug)
        except Exception as exc:
            url, err = None, f"{type(exc).__name__}: {exc}"
        if url:
            ok += 1
            logger.info("[%d/%d] %s ok", i, len(targets), slug)
        else:
            fail += 1
            logger.warning("[%d/%d] %s FAILED: %s", i, len(targets), slug, err)
    logger.info("done: %d warmed, %d failed, %.1f min", ok, fail, (time.time() - t0) / 60)
    # Non-zero when the batch achieved nothing despite having work — a silent
    # "0 warmed" run is indistinguishable from success otherwise (Rule 7b).
    if targets and ok == 0:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
