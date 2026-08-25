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
import threading
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path

REPO = Path("/home/fields/Fields_Orchestrator")
sys.path.insert(0, str(REPO))

from dotenv import load_dotenv  # noqa: E402

load_dotenv(REPO / ".env")

from scripts.job_status import job_run  # noqa: E402
# `artifact_fresh` is the ONE definition of staleness (blob newer than generator
# sources), shared with the on-demand poller so both agree on what to rebuild.
from scripts.publish_offmarket_artifacts import publish, artifact_fresh  # noqa: E402

# V5 renders only in the measured suburbs (v5Eligible == V4_SUBURBS), and the
# market-update generator supports exactly these — so we only pre-warm these.
V5_SUBURBS = ["robina", "burleigh_waters", "varsity_lakes"]


def has_artifact(slug: str, kind: str) -> bool:
    """A blob is only 'warm' if it is at least as new as the generator that
    produced it — so a copy/data/code change automatically invalidates every
    stale artifact on the next run. Without this a finalised copy change stays
    frozen behind pre-built blobs forever (all 8,050 market-update artifacts sat
    at an Aug-21 build after the 2026-08-25 rewrite)."""
    return artifact_fresh(slug, kind)


def candidates(limit: int | None, suburbs: list[str] | None = None) -> list[str]:
    """Off-market subjects with a real (non-directional) valuation in the
    measured suburbs — the addresses whose reports are worth pre-warming.

    `suburbs` restricts and ORDERS the sweep (default: all V5_SUBURBS). Ordering
    matters when a run may not finish in one sitting — put the suburb you need
    fresh first so it is rebuilt before the queue is exhausted."""
    from shared.db import get_gold_coast_db

    db = get_gold_coast_db()
    out: list[str] = []
    for suburb in (suburbs or V5_SUBURBS):
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


def _warm_one(slug: str, kind: str, kinds: list[str], force: bool):
    """Warm one address. Returns ('published'|'skipped'|'failed', slug[, err])."""
    if not force and all(has_artifact(slug, k) for k in kinds):
        return ("skipped", slug)
    results = publish(slug, kind, verbose=False)
    if results and all(r.get("ok") for r in results):
        return ("published", slug)
    errs = "; ".join(r.get("error", "") for r in results if not r.get("ok"))
    return ("failed", slug, errs[:200])


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--limit", type=int, default=None, help="max candidates PER suburb")
    ap.add_argument("--kind", default="both", choices=["market-update", "valuation-report", "both"])
    ap.add_argument("--workers", type=int, default=3, help="concurrent addresses (each spawns generators + headless chrome)")
    ap.add_argument("--suburbs", default=None,
                    help="comma-separated subset/ordering of measured suburbs (default: all). "
                         "Earlier suburbs are rebuilt first.")
    ap.add_argument("--force", action="store_true")
    args = ap.parse_args()

    suburbs = None
    if args.suburbs:
        suburbs = [s.strip() for s in args.suburbs.split(",") if s.strip()]
        bad = [s for s in suburbs if s not in V5_SUBURBS]
        if bad:
            ap.error(f"unknown suburb(s) {bad}; choose from {V5_SUBURBS}")

    with job_run("offmarket_artifact_prewarm", cadence_hours=24, title="Off-Market V5 Artifact Pre-Warm") as beat:
        slugs = candidates(args.limit, suburbs)
        kinds = ["market-update", "valuation-report"] if args.kind == "both" else [args.kind]
        counts = {"published": 0, "skipped": 0, "failed": 0}
        done = [0]
        lock = threading.Lock()
        total = len(slugs)

        def record(res):
            with lock:
                counts[res[0]] += 1
                done[0] += 1
                if res[0] == "failed":
                    print(f"  FAIL {res[1]}: {res[2] if len(res) > 2 else ''}", file=sys.stderr)
                if done[0] % 50 == 0 or done[0] == total:
                    print(f"  progress {done[0]}/{total}  {counts}", flush=True)

        with ThreadPoolExecutor(max_workers=max(1, args.workers)) as ex:
            futs = [ex.submit(_warm_one, s, args.kind, kinds, args.force) for s in slugs]
            for fut in as_completed(futs):
                record(fut.result())

        beat.metrics = {"candidates": total, **counts}
        # Rule 7b — candidates existed but we produced and skipped nothing = broken.
        if total and counts["published"] == 0 and counts["skipped"] == 0:
            raise RuntimeError(f"pre-warm published 0 of {total} candidates — upstream broken, not empty")
        beat.detail = f"{counts['published']} published, {counts['skipped']} already warm, {counts['failed']} failed"
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
