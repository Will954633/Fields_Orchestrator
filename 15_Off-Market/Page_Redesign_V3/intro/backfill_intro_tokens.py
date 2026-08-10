#!/usr/bin/env python3
"""
backfill_intro_tokens.py — put the matrix intro's word list on every discovery doc.

The intro rains a field of words that closes in on the reader's own street, and
that field is SPECIFIC TO THE HOME: tier 3 is their street grid and their block,
which needs the property's coordinates. A browser cannot compute it, so it has to
be precomputed and stored — which is what this does, writing `intro_tokens` onto
each `system_monitor.offmarket_discovery` document for the React deck to read.

Cost measured before writing this: 0.78s and ~1.3KB per home, and tiers 1-2 are
cached per suburb, so the real per-home work is small.

  python3 backfill_intro_tokens.py --dry-run       # count what would change
  python3 backfill_intro_tokens.py                 # write missing ones
  python3 backfill_intro_tokens.py --force         # rewrite all

Self-reporting per CLAUDE.md Rule 7 when run with --cron.
"""
from __future__ import annotations

import argparse
import sys
import time
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
sys.path.insert(0, str(HERE.parent.parent.parent))            # Fields_Orchestrator
sys.path.insert(0, str(HERE.parent.parent.parent / "scripts"))

from shared.env import load_env  # noqa: E402

load_env()

import intro_tokens  # noqa: E402
from shared.db import get_client  # noqa: E402


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--force", action="store_true", help="rewrite docs that already have tokens")
    ap.add_argument("--limit", type=int, default=0)
    ap.add_argument("--cron", action="store_true", help="record a heartbeat")
    a = ap.parse_args()

    coll = get_client()["system_monitor"]["offmarket_discovery"]
    q = {} if a.force else {"intro_tokens": {"$exists": False}}
    total = coll.count_documents(q)
    print(f"{total} document(s) {'to rewrite' if a.force else 'without intro_tokens'}")
    if a.dry_run or not total:
        return

    cur = coll.find(q, {"slug": 1}).limit(a.limit or 0)
    done = failed = 0
    started = time.time()
    for d in cur:
        slug = d.get("slug")
        try:
            tok = intro_tokens.build(slug) if hasattr(intro_tokens, "build") \
                else intro_tokens.build_tokens(slug)
            coll.update_one({"_id": d["_id"]}, {"$set": {"intro_tokens": tok}})
            done += 1
        except Exception as exc:                      # noqa: BLE001 — one bad home must not stop the run
            failed += 1
            if failed <= 5:
                print(f"  ! {slug}: {type(exc).__name__}: {exc}")
        if done and done % 250 == 0:
            rate = done / max(1e-6, time.time() - started)
            print(f"  {done}/{total}  {rate:.1f}/s  ~{(total - done) / max(rate, 1e-6) / 60:.0f} min left")

    print(f"done: {done} written, {failed} failed, {time.time() - started:.0f}s")

    if a.cron:
        from job_status import record_job_result
        record_job_result("offmarket_intro_tokens", "success" if not failed else "error",
                          cadence_hours=24, title="Off-Market Intro Tokens",
                          detail=f"{done} written, {failed} failed",
                          metrics={"written": done, "failed": failed})


if __name__ == "__main__":
    main()
