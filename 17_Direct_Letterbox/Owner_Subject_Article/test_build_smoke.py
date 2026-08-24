#!/usr/bin/env python3
"""
test_build_smoke.py -- build the owner-subject article across real addresses in every
target suburb and assert each one clears the gates (FactBook.verify + guardrails +
surface-consistency). Run this before any mail-out, and in CI after any change to the
generator, a chart, or a context file.

A build can end three ways:
  * ok             -> the article composed and passed every gate. PASS.
  * REJECTED at guard/comps/resolve -> the address legitimately does not qualify
    (listed, outside the envelope, too few comps). Expected. SKIP, not a failure.
  * REJECTED at checks/consistency  -> an unminted figure, a guardrail block, or a
    cross-surface disagreement. That is a real defect. FAIL.

Exit 0 iff no address FAILED (and at least one built OK). Non-zero otherwise.

    python3 test_build_smoke.py                 # 3 addresses per suburb, full build
    python3 test_build_smoke.py --limit 5       # more coverage
    python3 test_build_smoke.py --no-trajectory # faster; skips the as-of engine runs
"""
from __future__ import annotations

import argparse
import os
import sys
import tempfile

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)

import build_owner_article as goa            # noqa: E402

HARD_FAIL_STAGES = {"checks", "consistency"}


def main():
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--limit", type=int, default=3, help="addresses per suburb")
    ap.add_argument("--no-trajectory", action="store_true",
                    help="skip the 4x as-of valuation (faster; skips the trajectory "
                         "section + the sign-aware reading it feeds)")
    a = ap.parse_args()

    tmp = tempfile.mkdtemp(prefix="owner_smoke_")
    passed, skipped, failed = [], [], []

    for suburb in goa.SUBURBS:
        try:
            cands = goa.list_candidates(suburb, a.limit)
        except Exception as e:                               # noqa: BLE001
            print(f"  ! could not list candidates for {suburb}: {e}", file=sys.stderr)
            cands = []
        print(f"\n[{suburb}] {len(cands)} candidate(s)", file=sys.stderr)
        for c in cands:
            addr = c["address"]
            try:
                r = goa.build(addr, suburb, out_dir=tmp, want_html=False,
                              skip_market_check=True, no_hero=True, verbose=False,
                              skip_trajectory=a.no_trajectory)
            except Exception as e:                           # a crash IS a failure
                failed.append((addr, f"EXCEPTION: {type(e).__name__}: {e}"))
                print(f"  ✗ FAIL {addr}: exception {type(e).__name__}: {e}", file=sys.stderr)
                continue
            if r.get("ok"):
                passed.append(addr)
                warns = r.get("warnings") or []
                print(f"  ✓ ok   {addr}"
                      + (f"  ({len(warns)} warn)" if warns else ""), file=sys.stderr)
            elif r.get("stage") in HARD_FAIL_STAGES:
                failed.append((addr, f"{r['stage']}: {'; '.join(r.get('errors', []))[:200]}"))
                print(f"  ✗ FAIL {addr}: {r['stage']} — {r.get('errors')}", file=sys.stderr)
            else:
                skipped.append((addr, r.get("stage")))
                print(f"  – skip {addr}: {r.get('stage')} (legitimate rejection)",
                      file=sys.stderr)

    print("\n" + "=" * 60, file=sys.stderr)
    print(f"PASS {len(passed)}   SKIP {len(skipped)}   FAIL {len(failed)}", file=sys.stderr)
    for addr, why in failed:
        print(f"  FAIL {addr}: {why}", file=sys.stderr)
    if failed:
        return 1
    if not passed:
        print("  ! no address built OK — smoke test proved nothing", file=sys.stderr)
        return 2
    print("  smoke test PASSED", file=sys.stderr)
    return 0


if __name__ == "__main__":
    sys.exit(main())
