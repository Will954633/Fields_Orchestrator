#!/usr/bin/env python3
"""
Detect an OSCILLATING sitemap — a count that flips back and forth between runs.

WHY THIS SHAPE, AND NOT A MOVEMENT THRESHOLD
--------------------------------------------
The obvious guard is "refuse to push if the count moves more than N%". Measured against
what actually happened, that guard is worse than nothing — the harmful event is an order
of magnitude SMALLER than the legitimate ones:

    real oscillator (Aug 1-7)          +/- 2.6%     <- the only harmful one
    unit-mismatch fix (Aug 9)            -29.7%     legitimate, one-way
    attached-dwelling launch (Aug 13)    +45.5%     legitimate, one-way
    normal nightly churn                +/- 0.04%   fine

Any threshold that catches 2.6% blocks both legitimate deploys; any threshold that
permits 45% never sees the oscillator. Magnitude cannot separate them, so this does not
try. What separates them is SHAPE: a real change moves once and stays; an oscillator
reverses direction with a similar magnitude each run, forever.

So the signal is: direction reversed AND the two deltas are comparable in size. A
one-way step of any size is ignored no matter how large.

This ALERTS, it never blocks. A blocking guard on a legitimate deploy is the failure
mode we are avoiding — a human reads this and decides.

DATA SOURCE
-----------
The counts are parsed from the sitemap commit messages, which already encode them:
    chore(seo): refresh sitemap.xml (17338 URLs, 1508 property, 15703 off-market) [VM cron]
That gives full retrospective history immediately, rather than waiting for a new log to
accumulate, and it is the same record a human would audit by hand.

USAGE:
  python3 scripts/sitemap_count_stability.py            # nightly (heartbeat)
  python3 scripts/sitemap_count_stability.py --dry-run  # no heartbeat
  python3 scripts/sitemap_count_stability.py --limit 30 # look further back
"""
import os
import re
import sys
import json
import argparse
import subprocess

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from shared.env import load_env      # type: ignore
from job_status import job_run       # type: ignore

REPO = "Will954633/Website_Version_Feb_2026"
SITEMAP_PATH = "public/sitemap.xml"

# A reversal only counts as oscillation when the two deltas are within this ratio of
# each other. 0.5 means the smaller must be at least half the larger — a +4,558 step
# followed by a -99 correction is a change plus churn, not a sawtooth.
COMPARABLE_RATIO = 0.5
# Ignore reversals below this fraction of the total, which are ordinary listing churn.
MIN_FRACTION = 0.003

MSG_RE = re.compile(
    r"\((?P<total>\d+) URLs, (?P<property>\d+) property, (?P<offmarket>\d+) off-market\)"
)


def history(limit):
    """[(iso_date, total, property, offmarket)] newest-first from commit messages."""
    env = dict(os.environ, GH_CONFIG_DIR=os.environ.get("GH_CONFIG_DIR",
                                                        "/home/projects/.config/gh"))
    out = subprocess.run(
        ["gh", "api", f"repos/{REPO}/commits?path={SITEMAP_PATH}&per_page={limit}",
         "--jq", '.[] | "\\(.commit.author.date)\\t\\(.commit.message | split("\\n")[0])"'],
        capture_output=True, text=True, env=env, timeout=90,
    )
    if out.returncode != 0:
        raise RuntimeError(f"gh api failed: {out.stderr.strip()[:200]}")
    rows = []
    for line in out.stdout.splitlines():
        if "\t" not in line:
            continue
        when, msg = line.split("\t", 1)
        m = MSG_RE.search(msg)
        if m:
            rows.append((when, int(m["total"]), int(m["property"]), int(m["offmarket"])))
    return rows


def detect(series):
    """series: newest-first list of ints. Returns a finding dict, or None.

    Compares the two most recent transitions: d1 = latest - previous,
    d2 = previous - the one before. Oscillation = opposite signs, comparable size.
    """
    if len(series) < 3:
        return None
    latest, prev, prev2 = series[0], series[1], series[2]
    d1, d2 = latest - prev, prev - prev2
    if d1 == 0 or d2 == 0:
        return None
    if (d1 > 0) == (d2 > 0):          # same direction — a trend, not a sawtooth
        return None
    lo, hi = sorted((abs(d1), abs(d2)))
    if hi == 0 or lo / hi < COMPARABLE_RATIO:
        return None                    # a big step plus small churn, not a reversal
    if abs(d1) < max(1, latest * MIN_FRACTION):
        return None                    # ordinary listing churn
    return {"latest": latest, "prev": prev, "prev2": prev2, "d1": d1, "d2": d2,
            "ratio": round(lo / hi, 3),
            "pct": round(abs(d1) / latest * 100, 2)}


def main():
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--limit", type=int, default=15, help="commits to examine")
    ap.add_argument("--dry-run", action="store_true", help="no heartbeat")
    args = ap.parse_args()
    load_env()   # never trust the caller's env (CLAUDE.md rule 7, step 3)

    def work():
        rows = history(args.limit)
        # Zero-output path (rule 7b): no parsed history means the message format changed
        # or gh is broken — never "nothing to report".
        if len(rows) < 3:
            raise RuntimeError(
                f"parsed only {len(rows)} sitemap commits with counts; expected >=3. "
                "The commit-message format or gh auth changed — this check is blind, "
                "not clean."
            )
        findings = {}
        for name, idx in (("total", 1), ("property", 2), ("offmarket", 3)):
            f = detect([r[idx] for r in rows])
            if f:
                findings[name] = f

        print(f"examined {len(rows)} sitemap commits ({rows[-1][0][:10]} -> {rows[0][0][:10]})")
        for name, idx in (("property", 2), ("offmarket", 3)):
            print(f"  {name:<10} " + " ".join(str(r[idx]) for r in rows[:8]))
        if not findings:
            print("  no oscillation detected")
        for name, f in findings.items():
            print(f"  ⚠ OSCILLATION in {name}: {f['prev2']} -> {f['prev']} -> {f['latest']} "
                  f"(delta {f['d2']:+d} then {f['d1']:+d}, {f['pct']}% of total, "
                  f"magnitude ratio {f['ratio']})")
        return rows, findings

    if args.dry_run:
        work()
        return

    with job_run("sitemap_count_stability", cadence_hours=24,
                 title="Sitemap Count Stability (oscillation)") as beat:
        rows, findings = work()
        beat.metrics = {"commits_examined": len(rows),
                        "oscillating_series": sorted(findings),
                        "latest_offmarket": rows[0][3], "latest_property": rows[0][2]}
        if findings:
            beat.detail = "OSCILLATION: " + ", ".join(
                f"{k} +/-{v['d1']}" for k, v in findings.items())
            raise RuntimeError(
                "sitemap count is oscillating: " + json.dumps(findings, sort_keys=True)
            )
        beat.detail = (f"stable: {rows[0][2]} property, {rows[0][3]} off-market "
                       f"across {len(rows)} commits")


if __name__ == "__main__":
    main()
