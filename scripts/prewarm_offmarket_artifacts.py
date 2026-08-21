#!/usr/bin/env python3
"""Pre-warm V5 off-market artifacts (valuation-report + market-update) across the
measured suburbs, so most user requests hit the fast path (blob already there).

Idempotent: skips addresses whose blob artifact already exists unless --force.
Mirrors scripts/prewarm_offmarket_covers.py. Rule-7 self-monitored.

  python3 scripts/prewarm_offmarket_artifacts.py [--limit N] [--kind ...] [--force]
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

REPO = Path("/home/fields/Fields_Orchestrator")
sys.path.insert(0, str(REPO))

from dotenv import load_dotenv  # noqa: E402

load_dotenv(REPO / ".env")

from scripts.job_status import job_run  # noqa: E402
from scripts.publish_offmarket_artifacts import publish  # noqa: E402

BLOB_ROOT = Path("/data/blobs")
# V5 renders only in the measured suburbs (v5Eligible == V4_SUBURBS), and the
# market-update generator supports exactly these — so we only pre-warm these.
V5_SUBURBS = ["robina", "burleigh_waters", "varsity_lakes"]


def has_artifact(slug: str, kind: str) -> bool:
    if kind == "market-update":
        return (BLOB_ROOT / "market-update" / f"{slug}.html").exists()
    return (BLOB_ROOT / "valuation-report" / f"{slug}.html").exists()


def candidates(limit: int | None) -> list[str]:
    """Off-market subjects with a real (non-directional) valuation in the
    measured suburbs — the addresses whose reports are worth pre-warming."""
    from shared.db import get_gold_coast_db

    db = get_gold_coast_db()
    out: list[str] = []
    for suburb in V5_SUBURBS:
        cur = db[suburb].find(
            {
                "listing_status": {"$nin": ["for_sale", "sold"]},
                "valuation_data.confidence.reconciled_valuation": {"$ne": None},
                "url_slug": {"$ne": None},
            },
            {"url_slug": 1},
        )
        if limit:
            cur = cur.limit(limit)
        for doc in cur:
            slug = doc.get("url_slug")
            if slug:
                out.append(slug)
    return out


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--limit", type=int, default=None, help="max candidates PER suburb")
    ap.add_argument("--kind", default="both", choices=["market-update", "valuation-report", "both"])
    ap.add_argument("--force", action="store_true")
    args = ap.parse_args()

    with job_run("offmarket_artifact_prewarm", cadence_hours=24, title="Off-Market V5 Artifact Pre-Warm") as beat:
        slugs = candidates(args.limit)
        kinds = ["market-update", "valuation-report"] if args.kind == "both" else [args.kind]
        published = failed = skipped = 0
        for slug in slugs:
            if not args.force and all(has_artifact(slug, k) for k in kinds):
                skipped += 1
                continue
            results = publish(slug, args.kind, verbose=False)
            if results and all(r.get("ok") for r in results):
                published += 1
            else:
                failed += 1
                errs = "; ".join(r.get("error", "") for r in results if not r.get("ok"))
                print(f"  FAIL {slug}: {errs[:200]}", file=sys.stderr)
        beat.metrics = {"candidates": len(slugs), "published": published, "failed": failed, "skipped": skipped}
        # Rule 7b — candidates existed but we produced and skipped nothing = broken.
        if slugs and published == 0 and skipped == 0:
            raise RuntimeError(f"pre-warm published 0 of {len(slugs)} candidates — upstream broken, not empty")
        beat.detail = f"{published} published, {skipped} already warm, {failed} failed"
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
