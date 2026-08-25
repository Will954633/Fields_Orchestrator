#!/usr/bin/env python3
"""Pre-warm V5 off-market artifacts (valuation-report + market-update) across the
measured suburbs, so most user requests hit the fast path (blob already there).

Idempotent: skips addresses whose blob artifact already exists unless --force.
Mirrors scripts/prewarm_offmarket_covers.py. Rule-7 self-monitored.

  python3 scripts/prewarm_offmarket_artifacts.py [--limit N] [--kind ...] [--force]
"""
from __future__ import annotations

import argparse
import functools
import sys
import threading
from concurrent.futures import ThreadPoolExecutor, as_completed
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


# A blob is only "warm" if it is at least as new as the generator that produced
# it. Comparing the blob's mtime against the newest source file in each kind's
# generator directory means a copy edit, a data-context refresh, or a code change
# automatically invalidates every stale artifact on the next run — without which
# a finalised copy change stays frozen behind pre-built blobs forever (all 8,050
# market-update artifacts sat at an Aug-21 build after the 2026-08-25 rewrite).
_GEN_DIRS = {
    "market-update": REPO / "17_Direct_Letterbox" / "Owner_Subject_Article",
    "valuation-report": REPO / "16_Valuation" / "report_page",
}


@functools.lru_cache(maxsize=None)
def _source_mtime(kind: str) -> float:
    """Newest mtime among the *.py / *.json source files of this kind's
    generator. Cached: the sources don't change during a run."""
    gen_dir = _GEN_DIRS.get(kind)
    if not gen_dir or not gen_dir.exists():
        return 0.0
    mtimes = [
        p.stat().st_mtime
        for pat in ("*.py", "*.json")
        for p in gen_dir.glob(pat)
        if p.is_file()
    ]
    return max(mtimes) if mtimes else 0.0


def _blob_path(slug: str, kind: str) -> Path:
    sub = "market-update" if kind == "market-update" else "valuation-report"
    return BLOB_ROOT / sub / f"{slug}.html"


def has_artifact(slug: str, kind: str) -> bool:
    """True only if the blob exists AND is newer than the generator sources.
    A stale (pre-copy-change) blob reports False so it is rebuilt."""
    blob = _blob_path(slug, kind)
    try:
        return blob.stat().st_mtime >= _source_mtime(kind)
    except FileNotFoundError:
        return False


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
    ap.add_argument("--force", action="store_true")
    args = ap.parse_args()

    with job_run("offmarket_artifact_prewarm", cadence_hours=24, title="Off-Market V5 Artifact Pre-Warm") as beat:
        slugs = candidates(args.limit)
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
