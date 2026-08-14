#!/usr/bin/env python3
"""
One-off migration: make already-built off-market reports visible to the endpoint.

`prewarm_offmarket_covers.py` recorded its output only to
`system_monitor.offmarket_report_covers` until 2026-08-14. The endpoint that
serves readers, `offmarket-report-request.mjs`, reads
`system_monitor.offmarket_report_requests` and nothing else — so thousands of
finished reports sat on disk while every visitor triggered a ~29s rebuild. See
`logs/fix-history/2026-08-14.md` [PREWARM-INVISIBLE-TO-ENDPOINT].

The prewarm now writes that row itself. This script repairs the ones built
BEFORE the fix. It re-renders NOTHING: the PDF is already on local disk (the
blob store IS /data/blobs, served by nginx), so this only

    1. copies <slug>/<ts>.pdf -> <slug>/report.pdf   (the tracked viewer reads
       this path, not the blob URL — without it the viewer 404s)
    2. mints an email_tracking record so viewer_url exists
    3. writes the completed offmarket_report_requests row

At ~0.1s per property instead of ~21s, so the whole catalogue repairs in minutes.

⚠ THE ROW CARRIES THE ORIGINAL built_at, NOT now(). Both the endpoint's cache
window and the substantiation records are 7 days. Stamping these with the
current time would claim a report built last week is fresh for another seven
days, serving stale comparables and medians to an owner. A build that is already
past its shelf life is deliberately left alone for the prewarm to rebuild.

    python3 scripts/backfill_prewarm_queue_rows.py --dry-run
    python3 scripts/backfill_prewarm_queue_rows.py
"""

import argparse
import shutil
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT))

from dotenv import load_dotenv

load_dotenv(REPO_ROOT / ".env")

from shared.db import get_client  # noqa: E402
from scripts.offmarket_report_poller import (  # noqa: E402
    _mint_tracking, _resolve_subject, _wf_address,
)

BLOB_ROOT = Path("/data/blobs/off-market-reports")
COVER_BASE = "https://blobs.fieldsestate.com.au/off-market-reports/covers"
SHELF_LIFE_DAYS = 7


def _newest_pdf(slug: str) -> Path | None:
    """The published PDF for this slug. Prefer the timestamped file the cover
    doc points at; fall back to the newest, since a slug can accumulate several
    builds and only the latest is the one being advertised."""
    d = BLOB_ROOT / slug
    if not d.is_dir():
        return None
    cands = sorted((p for p in d.glob("*.pdf") if p.name != "report.pdf"),
                   key=lambda p: p.stat().st_mtime, reverse=True)
    return cands[0] if cands else None


def main():
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--limit", type=int, default=0)
    args = ap.parse_args()

    client = get_client()
    sm = client["system_monitor"]
    covers, queue = sm["offmarket_report_covers"], sm["offmarket_report_requests"]

    servable = set(r["slug"] for r in queue.find({"status": "completed"}, {"slug": 1}))
    cutoff = datetime.now(timezone.utc) - timedelta(days=SHELF_LIFE_DAYS)

    stats = dict(repaired=0, already=0, no_pdf=0, expired=0, no_subject=0)
    for c in covers.find({"pdf_url": {"$ne": None}}, {"slug": 1, "pdf_url": 1, "built_at": 1}):
        slug, built_at = c["slug"], c.get("built_at")
        if slug in servable:
            stats["already"] += 1
            continue
        if not built_at:
            stats["expired"] += 1
            continue
        built_at = built_at.replace(tzinfo=timezone.utc)
        if built_at <= cutoff:
            # Past its shelf life. Leave it for the prewarm to rebuild rather
            # than publish a row the endpoint would refuse anyway.
            stats["expired"] += 1
            continue

        pdf = _newest_pdf(slug)
        if not pdf:
            stats["no_pdf"] += 1
            continue

        subject_id, suburb = _resolve_subject(client, slug)
        if not subject_id:
            stats["no_subject"] += 1
            continue

        if args.dry_run:
            stats["repaired"] += 1
            if args.limit and stats["repaired"] >= args.limit:
                break
            continue

        kept = BLOB_ROOT / slug / "report.pdf"
        if not kept.exists():
            shutil.copy(pdf, kept)

        address = _wf_address(client, subject_id, suburb) or slug.replace("-", " ").title()
        tracking_id = _mint_tracking(client, kept, slug, address)

        queue.update_one(
            {"slug": slug, "source": "prewarm"},
            {"$set": {
                "slug": slug, "source": "prewarm", "status": "completed",
                # Original build time on purpose — see the module docstring.
                "requested_at": built_at, "started_at": built_at, "finished_at": built_at,
                "pdf_url": c["pdf_url"],
                "cover_url": f"{COVER_BASE}/{slug}.jpg",
                "tracking_id": tracking_id,
                "viewer_url": f"https://fieldsestate.com.au/track/view/{tracking_id}"
                              if tracking_id else None,
                "size_mb": round(pdf.stat().st_size / 1_048_576, 2),
                "subject_id": subject_id, "suburb": suburb, "error": None,
                "backfilled_at": datetime.now(timezone.utc),
            }},
            upsert=True,
        )
        stats["repaired"] += 1
        if stats["repaired"] % 200 == 0:
            print(f"  ... {stats['repaired']} repaired", flush=True)
        if args.limit and stats["repaired"] >= args.limit:
            break

    print(("DRY RUN — " if args.dry_run else "") +
          f"repaired={stats['repaired']} already_servable={stats['already']} "
          f"past_shelf_life={stats['expired']} no_pdf={stats['no_pdf']} "
          f"unresolvable_slug={stats['no_subject']}")


if __name__ == "__main__":
    main()
