#!/usr/bin/env python3
"""
check_union_median_integrity.py — guard the Domain ∪ onthehouse medians.

Why this exists (2026-08-02, fix-history [UNION-MEDIANS-REVERTED-NIGHTLY]):
`precompute_indexed_price_data.py` finishes with a blind full-document
`replace_one` on Gold_Coast.precomputed_indexed_prices. Anything that runs it
after `precompute_union_prices.py --promote` silently deletes every union-owned
field — the 12-month median, its 90% CI, the sample size and the method/coverage
disclosure — and the pages fall back to the raw, premium-skewed quarterly sample
with no visible sign anything changed. Burleigh Waters read $2,115,000 instead of
$1,925,000 (+9.9%) for roughly 29 days out of every 30 before anyone noticed, and
it was only caught by chasing an unrelated timestamp.

The revert itself is fixed (the nightly path no longer runs the precompute), but
the landmine remains: any manual run of that script, or any new caller, reverts
the medians again. This check is the tripwire — it asserts the live docs are in
the promoted state and fails loudly if a raw rebuild has landed on top.

Checks per core suburb:
  1. median_source == "domain_union_onthehouse"      (promotion happened)
  2. median_computed_at >= last_updated               (nothing rebuilt over it)
  3. the 90% CI and sample size are present           (disclosure intact)

Both timestamps are naive UTC (`datetime.utcnow()`) in this collection — do not
compare them against local time.

Usage:
    python3 scripts/check_union_median_integrity.py
    python3 scripts/check_union_median_integrity.py --quiet   # only print problems
"""
from __future__ import annotations

import argparse
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))

from job_status import job_run  # noqa: E402

CORE_SUBURBS = ["robina", "burleigh_waters", "varsity_lakes"]
EXPECTED_SOURCE = "domain_union_onthehouse"
REQUIRED_FIELDS = [
    "rolling_12m_median_price",
    "rolling_12m_ci_low",
    "rolling_12m_ci_high",
    "rolling_12m_median_sample_n",
]


def check(quiet: bool = False):
    from src.mongo_client_factory import get_database

    db = get_database("Gold_Coast")
    problems, checked = [], {}

    for suburb in CORE_SUBURBS:
        doc = db["precomputed_indexed_prices"].find_one({"_id": suburb})
        if not doc:
            problems.append(f"{suburb}: document missing entirely")
            continue

        source = doc.get("median_source")
        computed = doc.get("median_computed_at")
        updated = doc.get("last_updated")
        median = doc.get("rolling_12m_median_price")
        checked[suburb] = median

        if source != EXPECTED_SOURCE:
            problems.append(
                f"{suburb}: median_source is {source!r}, expected {EXPECTED_SOURCE!r} — "
                f"the union promote has been reverted. Re-run "
                f"scripts/precompute_union_prices.py --promote and find what overwrote it."
            )
        if not computed:
            problems.append(f"{suburb}: median_computed_at missing — never promoted")
        elif updated and updated > computed:
            problems.append(
                f"{suburb}: a raw rebuild landed AFTER the union promote "
                f"(last_updated {updated} > median_computed_at {computed}, both UTC). "
                f"Medians on the live pages are the raw quarterly sample."
            )

        missing = [f for f in REQUIRED_FIELDS if doc.get(f) in (None, "")]
        if missing:
            problems.append(f"{suburb}: missing {', '.join(missing)} — CI/sample disclosure lost")

        if not quiet and not problems:
            print(f"  {suburb:16} ${median:,.0f}  n={doc.get('rolling_12m_median_sample_n')}  OK")

    return problems, checked


def main():
    ap = argparse.ArgumentParser(description="Assert the union medians are live and un-reverted")
    ap.add_argument("--quiet", action="store_true", help="only print problems")
    args = ap.parse_args()

    with job_run(
        "union_median_integrity",
        cadence_hours=24,
        title="Market Metrics — union median integrity",
    ) as beat:
        problems, checked = check(quiet=args.quiet)

        if problems:
            for p in problems:
                print(f"  FAIL  {p}")
            # Raising inside job_run records status=error on the health board.
            raise RuntimeError(
                f"{len(problems)} union-median integrity failure(s): " + " | ".join(problems)
            )

        beat.detail = " ".join(
            f"{s}=${m:,.0f}" for s, m in checked.items() if m
        ) or "no suburbs checked"
        beat.metrics = {f"median_{s}": m for s, m in checked.items() if m}
        print(f"\nOK — {len(checked)} suburbs on the {EXPECTED_SOURCE} basis, none reverted.")


if __name__ == "__main__":
    main()
