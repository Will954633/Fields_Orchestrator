#!/usr/bin/env python3
"""check_comparable_consistency.py — the two comparable tables must not contradict.

WHY THIS EXISTS
---------------
A unit page now shows TWO comparable sets: sales in the same building
(`unit_valuations`) and recent sales within 5km (`unit_statutory_comps`). They are built
by different code from different pools, and they OVERLAP — a sale in the subject's own
building is also a sale within 5km, so the same address legitimately appears in both.

That overlap is the hazard. On 2026-08-13 the deployed page for 187 Easthill Drive showed
159 Easthill's $1,425,000 sale in both tables with DIFFERENT dates (2026-04 vs 2026-03)
and therefore different adjusted figures ($1,425,000 vs $1,523,676) — $98,676 apart, on
one page, for one sale. The cause was the two pipelines disagreeing on which date is
canonical when a sale is recorded twice. See fix-history
`[TWO-TABLES-ONE-SALE-TWO-DATES]`.

⚠ NOTHING ELSE CHECKS THIS. `check_renderer_consistency.py` compares the two RENDERERS
against one data source. This compares two DATA SOURCES describing the same sale. Showing
both sets on one page created the requirement, and the only reason the first instance was
caught is that someone read the rendered output.

What it asserts, per dwelling that has both sets:
  * an address in both tables carries the SAME sale date
  * and the SAME raw sold price
The ADJUSTED figures are allowed to differ — the two methods deflate to different bases by
design, and that difference is the point of showing both.
"""
from __future__ import annotations

import argparse
import re
import sys
from collections import Counter
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent.parent.parent
for p in (str(ROOT), str(HERE)):
    if p not in sys.path:
        sys.path.insert(0, p)

try:
    from shared.env import load_env
    load_env()
except Exception:
    pass

from shared.db import get_client                   # noqa: E402
from scripts.job_status import job_run             # noqa: E402

# A handful of disagreements would still be a defect, but the job must not fail the whole
# board over one stale record mid-recompute. Anything above this is systemic.
TOLERATED = 0.005          # 0.5% of pages compared


def norm(a):
    return re.sub(r"[^a-z0-9]", "", (a or "").lower())


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--show", type=int, default=10)
    args = ap.parse_args()

    with job_run("units_comparable_consistency", cadence_hours=24,
                 title="Units — the two comparable tables agree") as beat:
        gc = get_client()["Gold_Coast"]
        stat = {d["_id"]: d for d in gc["unit_statutory_comps"].find(
            {"available": True}, {"comparables": 1})}

        compared = overlapping = bad = 0
        kinds = Counter()
        examples = []
        for v in gc["unit_valuations"].find(
                {"method": "same_complex_comparables"}, {"comparables": 1}):
            s = stat.get(v["_id"])
            if not s:
                continue
            compared += 1
            byaddr = {}
            for c in (s.get("comparables") or []):
                byaddr[norm(c.get("address"))] = c
            hit = False
            for c in (v.get("comparables") or []):
                o = byaddr.get(norm(c.get("address")))
                if not o:
                    continue
                hit = True
                if str(c.get("date"))[:10] != str(o.get("date"))[:10]:
                    kinds["date"] += 1
                    bad += 1
                    if len(examples) < args.show:
                        examples.append(
                            f"{v['_id']} :: {c.get('address')} "
                            f"date {c.get('date')} vs {o.get('date')}")
                elif int(c.get("sold") or 0) != int(o.get("sold") or 0):
                    kinds["price"] += 1
                    bad += 1
                    if len(examples) < args.show:
                        examples.append(
                            f"{v['_id']} :: {c.get('address')} "
                            f"sold {c.get('sold')} vs {o.get('sold')}")
            overlapping += hit

        print(f"  pages with both sets      : {compared:,}")
        print(f"  pages where they overlap  : {overlapping:,}")
        print(f"  CONTRADICTIONS            : {bad:,}  {dict(kinds)}")
        for e in examples:
            print(f"    {e}")

        beat.metrics = {"compared": compared, "overlapping": overlapping,
                        "contradictions": bad, **{f"kind_{k}": v for k, v in kinds.items()}}
        beat.detail = (f"{bad:,} contradictions across {overlapping:,} overlapping pages "
                       f"of {compared:,} compared")

        # Rule 7b — a run that compares nothing is not a pass.
        if compared == 0:
            raise RuntimeError(
                "0 pages carry both comparable sets — one of the precomputes has not run, "
                "so this check proved nothing")
        if overlapping == 0:
            raise RuntimeError(
                f"{compared:,} pages have both sets and NONE shares a single address. A "
                "same-building sale is also a sale within 5km, so overlap is expected; "
                "zero means one set is not being populated as intended")
        if bad > max(1, TOLERATED * compared):
            raise RuntimeError(
                f"{bad:,} contradictions between the two comparable tables — the same sale "
                f"is being shown twice on one page with different facts. Examples: "
                + " | ".join(examples[:3]))
    return 0


if __name__ == "__main__":
    sys.exit(main())
