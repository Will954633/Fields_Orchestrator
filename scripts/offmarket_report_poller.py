#!/usr/bin/env python3
"""
Off-Market Report Request Poller

Polls system_monitor.offmarket_report_requests for pending self-serve report
requests made from the V4 /off-market/:slug page, renders the Property
Positioning Report, and publishes it as a public PDF the page can link to.

Pipeline per request:
    1. slug -> Gold_Coast property doc (subject _id + suburb)
    2. generate_appraisal_v4.py --self-serve --no-flatten-cover
    3. Ghostscript downsample  (17 MB -> ~1.2 MB, no visible quality loss)
    4. write into /data/blobs/off-market-reports/<slug>/<ts>.pdf
    5. stamp pdf_url + status=completed on the request doc

⚠ Why not `trigger_requests`: that queue is global, strictly serial (one job
per 30s cycle) and shared with the nightly scrape. A visitor waiting on a live
page could sit behind a 20-minute job. This queue is dedicated, so the wait is
bounded by the render itself (~20-40s).

⚠ Publishing is a file write, nothing more. nginx serves /data/blobs directly as
https://blobs.fieldsestate.com.au with `application/pdf` already in its type
map. There is no upload step and no CDN invalidation. It also sets
`Cache-Control: immutable, max-age=31536000` on everything, which is why the
filename carries a timestamp — reusing a path would serve a stale PDF forever.

Run as a service: fields-offmarket-report-poller
"""

import logging
import os
import subprocess
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT))

from dotenv import load_dotenv

# Load our own environment rather than trusting the caller — a unit file missing
# `set -a` exports nothing, and pymongo would still connect via settings.yaml, so
# the job would look healthy while every credential-dependent call failed.
load_dotenv(REPO_ROOT / ".env")

from pymongo import MongoClient  # noqa: E402

from scripts.job_status import job_run  # noqa: E402

logging.basicConfig(
    level=logging.INFO,
    format="[%(asctime)s] [%(levelname)s] %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)
logger = logging.getLogger(__name__)

POLL_INTERVAL = 15                     # seconds — a human is waiting on this one
JOB_TIMEOUT_SECONDS = 300              # render measures 20-40s; 5 min is a wide cap
VENV_PYTHON = "/home/fields/venv/bin/python3"
GENERATOR = REPO_ROOT / "scripts" / "generate_appraisal_v4.py"
BLOB_CONTAINER = "off-market-reports"
STALE_CLAIM_SECONDS = 900              # reclaim jobs orphaned by a crash/restart
SUBURBS = ["robina", "burleigh_waters", "varsity_lakes", "merrimac"]


def get_client():
    uri = os.environ.get("COSMOS_CONNECTION_STRING")
    if not uri:
        raise RuntimeError("COSMOS_CONNECTION_STRING not set — cannot poll")
    return MongoClient(uri, retryWrites=False, serverSelectionTimeoutMS=30000)


def _resolve_subject(client, slug):
    """slug -> (subject_id, suburb_key). Returns (None, None) when unknown."""
    gc = client["Gold_Coast"]
    for suburb in SUBURBS:
        doc = gc[suburb].find_one({"url_slug": slug}, {"_id": 1})
        if doc:
            return str(doc["_id"]), suburb
    return None, None


def _shrink(pdf_path: Path) -> Path:
    """Ghostscript downsample for screen delivery.

    /printer keeps 300 DPI images — measured 17 MB -> 1.2 MB with no visible
    quality loss on the cover or the comparable photography. Falls back to the
    original file if Ghostscript is unavailable or produces something implausible,
    because a large correct PDF beats a small broken one.
    """
    out = pdf_path.with_name(pdf_path.stem + "_screen.pdf")
    try:
        subprocess.run([
            "gs", "-sDEVICE=pdfwrite", "-dCompatibilityLevel=1.4",
            "-dPDFSETTINGS=/printer", "-dNOPAUSE", "-dQUIET", "-dBATCH",
            f"-sOutputFile={out}", str(pdf_path),
        ], check=True, capture_output=True, timeout=120)
        if out.exists() and out.stat().st_size > 50_000:
            return out
        logger.warning("Ghostscript output implausible (%s bytes) — keeping original",
                       out.stat().st_size if out.exists() else 0)
    except Exception as exc:
        logger.warning("Ghostscript downsample skipped: %s", exc)
    return pdf_path


def _error_summary(output: str, returncode: int) -> str:
    """Pull the actionable line out of a Python traceback.

    Slicing the last N characters cuts mid-frame and yields fragments like
    "raisal(" — useless in the ops view and useless to anyone diagnosing a
    visitor's failed request. The generator's guards (waterfront, no hero
    image) raise with deliberately actionable messages, so surface those.
    """
    for line in reversed((output or "").strip().splitlines()):
        line = line.strip()
        if line and not line.startswith(("File \"", "Traceback", "  ")):
            return line[:600]
    return f"Generator exited {returncode} with no usable error output"


def _publish_cover(pdf_path: Path, slug: str) -> str | None:
    """Publish page 1 as a JPEG thumbnail for the page's report section.

    Taken from the RENDERED PDF rather than re-rendering the cover separately,
    so the thumbnail is by construction the cover of the document it advertises.
    A separately-built preview could drift from the real thing — the hero chain
    has six fallback tiers, and showing one photo while delivering another would
    be its own small dishonesty.

    Fixed path per slug (no timestamp) so the page can reference it without a
    lookup and simply hide the image when it 404s. ⚠ nginx serves /data/blobs
    with `immutable, max-age=31536000`, so a refreshed cover will not be picked
    up by a browser that has already cached one. Acceptable: the cover changes
    only if the hero photo changes, which is rare, and the alternative is a
    lookup on every page render.
    """
    try:
        import fitz  # PyMuPDF
        from shared.blob_storage import upload

        doc = fitz.open(pdf_path)
        # ~600px wide at A4 — retina-sharp in the ~300px slot the section gives it.
        pix = doc[0].get_pixmap(dpi=72)
        data = pix.tobytes("jpeg", jpg_quality=82) if hasattr(pix, "tobytes") else pix.tobytes()
        doc.close()
        return upload("off-market-reports", f"covers/{slug}.jpg", data,
                      content_type="image/jpeg")
    except Exception as exc:
        # A missing thumbnail degrades to no image; it must never fail the report.
        logger.warning("Cover thumbnail failed for %s: %s", slug, exc)
        return None


def _publish(pdf_path: Path, slug: str) -> str:
    """Copy the PDF into the public blob root and return its URL.

    Writes via a .tmp then atomic replace so nginx can never serve a
    half-written file to someone who polled at the wrong moment.
    """
    from shared.blob_storage import upload  # local import: needs .env loaded

    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S")
    return upload(
        BLOB_CONTAINER,
        f"{slug}/{stamp}.pdf",
        pdf_path.read_bytes(),
        content_type="application/pdf",
    )


def process_one(client, req) -> bool:
    """Render and publish one request. Returns True on success."""
    req_id = req["_id"]
    slug = req.get("slug")
    queue = client["system_monitor"]["offmarket_report_requests"]

    logger.info("Processing %s (slug=%s)", req_id, slug)

    subject_id, suburb = _resolve_subject(client, slug)
    if not subject_id:
        queue.update_one({"_id": req_id}, {"$set": {
            "status": "failed",
            "error": f"No property found for slug '{slug}' in {SUBURBS}",
            "finished_at": datetime.now(timezone.utc),
        }})
        logger.error("Unknown slug %s", slug)
        return False

    basename = f"selfserve_{slug}_{datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%S')}"
    try:
        proc = subprocess.run(
            [VENV_PYTHON, str(GENERATOR), "--subject-id", subject_id,
             "--self-serve", "--no-flatten-cover", "--output-basename", basename],
            capture_output=True, text=True, timeout=JOB_TIMEOUT_SECONDS,
            cwd=str(REPO_ROOT),
        )
    except subprocess.TimeoutExpired:
        queue.update_one({"_id": req_id}, {"$set": {
            "status": "failed",
            "error": f"Render timed out after {JOB_TIMEOUT_SECONDS}s",
            "finished_at": datetime.now(timezone.utc),
        }})
        logger.error("Request %s timed out", req_id)
        return False

    pdf_path = REPO_ROOT / "artifacts" / "appraisals_v4" / f"{basename}.pdf"
    if proc.returncode != 0 or not pdf_path.exists():
        # Keep the generator's own words. The waterfront guard and the
        # no-hero-image guard both raise here with an actionable message, and
        # discarding it would leave the failure undiagnosable.
        tail = _error_summary(proc.stderr or proc.stdout or "", proc.returncode)
        queue.update_one({"_id": req_id}, {"$set": {
            "status": "failed",
            "error": tail or f"Generator exited {proc.returncode} with no PDF",
            "finished_at": datetime.now(timezone.utc),
        }})
        logger.error("Request %s failed: %s", req_id, tail[:200])
        return False

    screen_pdf = _shrink(pdf_path)
    published = _publish(screen_pdf, slug)
    cover_url = _publish_cover(screen_pdf, slug)
    # The SHIPPED size, not the source. Recording the pre-shrink figure would
    # report 11 MB for a file the visitor downloads at 1.2 MB, and this metric
    # exists precisely to watch download weight.
    size_mb = round(screen_pdf.stat().st_size / 1_048_576, 2)

    queue.update_one({"_id": req_id}, {"$set": {
        "status": "completed",
        "pdf_url": published,
        "cover_url": cover_url,
        "size_mb": size_mb,
        "subject_id": subject_id,
        "suburb": suburb,
        "finished_at": datetime.now(timezone.utc),
        "error": None,
    }})
    logger.info("Published %s -> %s", req_id, published)
    return True


def poll_once(client) -> dict:
    """Claim and process at most one pending request. Returns counters."""
    queue = client["system_monitor"]["offmarket_report_requests"]

    # Reclaim anything a crash left mid-flight, otherwise a restart strands the
    # visitor on a spinner forever.
    cutoff = datetime.now(timezone.utc).timestamp() - STALE_CLAIM_SECONDS
    for stuck in queue.find({"status": "processing"}):
        started = stuck.get("started_at")
        if started and started.timestamp() < cutoff:
            queue.update_one({"_id": stuck["_id"]}, {"$set": {"status": "pending"}})
            logger.warning("Reclaimed stale job %s", stuck["_id"])

    req = queue.find_one_and_update(
        {"status": "pending"},
        {"$set": {"status": "processing", "started_at": datetime.now(timezone.utc)}},
        sort=[("requested_at", 1)],
    )
    if not req:
        return {"claimed": 0, "succeeded": 0, "failed": 0}

    ok = process_one(client, req)
    return {"claimed": 1, "succeeded": int(ok), "failed": int(not ok)}


def main():
    logger.info("Off-market report poller starting (every %ss)", POLL_INTERVAL)
    client = get_client()
    while True:
        try:
            # One heartbeat per claimed job rather than per idle tick: an empty
            # queue is a legitimate success, but recording it every 15s would
            # bury the runs that actually did work.
            counters = poll_once(client)
            if counters["claimed"]:
                with job_run("offmarket_report_poller", cadence_hours=24,
                             title="Off-Market Report Requests") as beat:
                    beat.metrics = counters
                    # Rule 7b — a run that claimed a job and produced nothing is
                    # a failure, not an idle cycle. Without this the poller would
                    # report success while every visitor's request errored.
                    if counters["succeeded"] == 0:
                        raise RuntimeError(
                            f"claimed {counters['claimed']} request(s) and published none — "
                            f"see offmarket_report_requests.error"
                        )
                    beat.detail = f"{counters['succeeded']} report(s) published"
        except Exception as exc:
            logger.error("Poll cycle failed: %s", exc)
        time.sleep(POLL_INTERVAL)


if __name__ == "__main__":
    main()
