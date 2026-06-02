#!/usr/bin/env python3
"""
backfill_sample_extraction.py — run vision extraction on the positioning sample,
recoverable-now only.

For each sample member that HAS photos but no GPT enrichment yet, runs the
existing per-id pipeline (scripts/on_demand_valuation.py — photo analysis +
floor-plan analysis + georeference + valuation) so the canonical attributes
(pool, condition, finish, floor area, stories) can be resolved. Media-less
members are NOT re-scraped here (separate effort) — they stay scraped-only and
are flagged honestly in provenance.

Idempotent: a member that already has property_valuation_data is skipped. After
extraction, refreshes the golden records via canonical_resolver.

Usage:
  python3 scripts/backfill_sample_extraction.py --dry-run
  python3 scripts/backfill_sample_extraction.py --confirm
"""
from __future__ import annotations

import argparse
import subprocess
import sys
import time
from collections import Counter
from pathlib import Path

from bson import ObjectId

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from shared.db import get_client, get_gold_coast_db  # noqa: E402

REPO_ROOT = Path(__file__).resolve().parent.parent
EST_COST_PER = 0.25
PER_PROP_TIMEOUT = 300


def _targets(client, db):
    m = client["system_monitor"]["sample_manifest"].find_one(sort=[("created_at", -1)])
    if not m:
        raise SystemExit("No sample_manifest — run build_positioning_sample.py first.")
    out = []
    for suburb, ids in m["members"].items():
        for oid in ids:
            d = db[suburb].find_one({"_id": ObjectId(oid)},
                                    {"property_images": 1, "property_valuation_data": 1})
            if d and d.get("property_images") and not d.get("property_valuation_data"):
                out.append((suburb, oid))
    return m["sample_id"], out


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--confirm", action="store_true")
    args = ap.parse_args()

    client = get_client()
    db = get_gold_coast_db()
    sample_id, targets = _targets(client, db)

    print(f"Sample: {sample_id}")
    print(f"Extraction targets (have photos, no GPT enrichment): {len(targets)}")
    print(f"  by suburb: {dict(Counter(s for s, _ in targets))}")
    print(f"  est. cost: ~${len(targets) * EST_COST_PER:.0f}  "
          f"| est. serial wall-time: ~{len(targets) * 2} min")

    if not targets:
        print("Nothing to extract.")
        return 0
    if args.dry_run or not args.confirm:
        print("\n(dry-run — no paid calls. Re-run with --confirm to extract.)")
        return 0

    ok = fail = 0
    for i, (suburb, oid) in enumerate(targets, 1):
        print(f"\n[{i}/{len(targets)}] {suburb}/{oid} …", flush=True)
        t0 = time.time()
        try:
            r = subprocess.run(
                [sys.executable, str(REPO_ROOT / "scripts" / "on_demand_valuation.py"),
                 "--suburb", suburb, "--property-id", oid],
                cwd=str(REPO_ROOT), timeout=PER_PROP_TIMEOUT,
                capture_output=True, text=True)
            if r.returncode == 0:
                ok += 1
                print(f"    done in {time.time()-t0:.0f}s")
            else:
                fail += 1
                print(f"    FAILED rc={r.returncode}: {r.stderr.strip()[-200:]}")
        except subprocess.TimeoutExpired:
            fail += 1
            print(f"    TIMEOUT after {PER_PROP_TIMEOUT}s")

    print(f"\nExtraction complete: {ok} ok, {fail} failed.")
    print("Refreshing golden records …")
    subprocess.run([sys.executable,
                    str(REPO_ROOT / "scripts" / "property_reports" / "canonical_resolver.py"),
                    "--all-sample"], cwd=str(REPO_ROOT))
    return 0


if __name__ == "__main__":
    sys.exit(main())
