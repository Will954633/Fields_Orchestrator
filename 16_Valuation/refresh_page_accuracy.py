#!/usr/bin/env python3
"""
refresh_page_accuracy.py — re-derive the accuracy figures the V4 report
publishes, after the nightly recompute, and say so loudly if they have drifted.

WHY THIS EXISTS
───────────────────────────────────────────────────────────────────────────────
`v4/valuationCopy.ts` publishes a measured track record — per-suburb MAE, the
80% band, and the "$X wider" adjustment benefit. Those are constants copied from
a backtest run. The engine underneath them changes: on 2026-08-10 the suburb
calibration was re-derived, which silently made every one of those figures
describe a method the site would stop running at the next recompute.

That is the third time in one day a measured constant outlived the code it
described (the backtest itself, the calibration, and these). A note in a
fix-history did not prevent the first two.

⚠ IT NEVER WRITES TO THE WEBSITE. It re-derives, compares against what is
published, and reports. Applying the change stays a human act, because these
numbers are a public claim about our own accuracy and a bad automated push would
publish a false one silently. The job's value is that it makes drift IMPOSSIBLE
TO NOT NOTICE, not that it fixes it.

⚠ RULE 7b — the assertion is not "it ran". It is that the figures were actually
re-derived for every measured suburb; a run that measures nothing must fail.

    python3 16_Valuation/refresh_page_accuracy.py            # check + report
    python3 16_Valuation/refresh_page_accuracy.py --emit     # also print the TS
"""
import argparse
import json
import os
import re
import subprocess
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent))
sys.path.insert(0, str(HERE.parent / "scripts"))

from shared.env import load_env
from job_status import job_run

load_env()

SUBURBS = ["robina", "varsity_lakes", "burleigh_waters"]
COPY = Path("/home/fields/Feilds_Website/01_Website/src/pages/OffMarketPage/v4/valuationCopy.ts")
BT = Path("/home/fields/Fields_Orchestrator/scripts/valuation_backtest.py")

# What the page currently claims, parsed from the shipped constant rather than
# assumed — if someone hand-edits it, we compare against what is really live.
def published():
    txt = COPY.read_text()
    out = {}
    for m in re.finditer(r"(\w+):\s*\{ n: (\d+), mae: ([\d.]+), median: ([\d.]+), "
                         r"within10: (\d+), contain: (\d+), band: ([\d.]+) \}", txt):
        out[m.group(1)] = {"n": int(m.group(2)), "mae": float(m.group(3)),
                           "median": float(m.group(4)), "within10": int(m.group(5)),
                           "contain": int(m.group(6)), "band": float(m.group(7))}
    return out


def measure(suburb):
    """Run the aligned backtest for one suburb and pull the headline figures."""
    r = subprocess.run(
        [sys.executable, str(BT), "--price-filter", "none", "--property-type", "House",
         "--min-price", "1000000", "--max-price", "2000000",
         "--suburb", suburb, "--blind-subject"],
        capture_output=True, text=True, timeout=5400, cwd=str(BT.parent),
        env={**os.environ},
    )
    t = r.stdout
    def grab(pat):
        m = re.search(pat, t)
        return float(m.group(1)) if m else None
    n = re.search(r"Fields Reconciled Valuation \(n=(\d+)\)", t)
    return {
        "n": int(n.group(1)) if n else None,
        "mae": grab(r"MAE:\s+([\d.]+)%"),
        "median": grab(r"Median AE:\s+([\d.]+)%"),
        "within10": grab(r"Within 10%:\s+(\d+)%"),
    }


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--emit", action="store_true")
    args = ap.parse_args()

    with job_run("v4_page_accuracy_check", cadence_hours=168,
                 title="V4 Published Accuracy vs Measured") as beat:
        pub = published()
        measured, drifted = {}, []
        for s in SUBURBS:
            m = measure(s)
            if m["mae"] is None:
                continue
            measured[s] = m
            p = pub.get(s)
            if p and abs(p["mae"] - m["mae"]) >= 0.3:
                drifted.append(f"{s}: page says MAE {p['mae']}%, measured {m['mae']}%")

        # ── Rule 7b ──────────────────────────────────────────────────────────
        # An empty result is a broken harness, not a clean bill of health. This
        # job's whole purpose is to notice drift; measuring nothing and
        # reporting success would be the exact failure it exists to prevent.
        if len(measured) < len(SUBURBS):
            raise RuntimeError(
                f"only {len(measured)}/{len(SUBURBS)} suburbs measured — the backtest "
                f"is broken, so no statement about drift can be made")

        beat.metrics = {"suburbs": len(measured), "drifted": len(drifted)}
        if drifted:
            beat.detail = "DRIFT: " + " · ".join(drifted)
            print("\n⚠ THE PAGE'S PUBLISHED ACCURACY NO LONGER MATCHES THE METHOD:")
            for d in drifted:
                print(f"    {d}")
            print(f"\n  Re-derive and copy into {COPY.name}; do not hand-edit.")
        else:
            beat.detail = f"{len(measured)} suburbs — published figures still match"
            print("\n  Published accuracy still matches the measured method.")

        if args.emit:
            print("\n// paste into valuationCopy.ts")
            for s, m in measured.items():
                print(f"  {s}: {{ n: {m['n']}, mae: {m['mae']}, median: {m['median']}, "
                      f"within10: {int(m['within10'])}, contain: ?, band: ? }},")
            print("// ⚠ `contain` and `band` come from the 80% band derivation, "
                  "not from this summary — see 16_Valuation/accuracy/.")


if __name__ == "__main__":
    main()
