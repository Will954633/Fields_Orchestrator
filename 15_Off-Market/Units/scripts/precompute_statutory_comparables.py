#!/usr/bin/env python3
"""precompute_statutory_comparables.py — persist the 5km / 6-month set per unit.

Writes `Gold_Coast.unit_statutory_comps`, keyed by url_slug, for the page to read.

⚠ SEPARATE COLLECTION, LIKE unit_valuations — NOT merged into it.
These are two different answers to two different questions: `unit_valuations` holds the
figure we stand behind (same building, best evidence), this holds the set that satisfies
the Property Occupations Act's recency test. They disagree, and that disagreement is the
point of showing both. Merging them would force a caller to know which comparables came
from which method, which is how "the same field means two things" starts.

⚠ THIS SET IS MEASURABLY WORSE AND THE RECORD SAYS SO.
Scored leakage-free against the same 1,542 sales, both methods predicting the same homes:
    statutory     median error 9.1%   MAE 14.6%   within-10% 54.1%
    same-complex  median error 5.7%   MAE  9.3%   within-10% 67.4%
So the statutory set is published as EVIDENCE A READER CAN CHECK, never as the estimate.
Nothing here feeds the range. If that ever changes, the page gets less accurate while
looking more compliant, which is the worst of both.
"""
from __future__ import annotations

import argparse
import datetime as dt
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

from pymongo import UpdateOne                          # noqa: E402
from shared.db import get_client                       # noqa: E402
from shared.dwelling_type import classify_dwelling      # noqa: E402
from scripts.job_status import job_run                  # noqa: E402
from unit_valuation import UnitValuer                    # noqa: E402
from statutory_comparables import StatutoryComparables   # noqa: E402
from unit_page_data import PROJ                          # noqa: E402

SUBURBS = ["robina", "varsity_lakes", "burleigh_waters"]

# Measured 2026-08-13 by backtest_statutory_comparables.py. Published on the page so a
# reader can see WHY we prefer the other set, so it must stay in step with the backtest.
#
# ⚠ RE-MEASURED after `dedupe_sales` and the `_num` fix landed — the latter made floor
# area visible for the first time (18% of Robina attached, previously 0%), which feeds
# both the comparable ranking and the size adjustment. Re-measure whenever the comparable
# set or the definition of a sale changes; these render verbatim in the page's
# "which set predicts better?" table.
ACCURACY = {"median": 9.1, "mae": 14.6, "within10": 54.1, "n": 1542,
            "vs_same_complex": {"median": 5.7, "mae": 9.3, "within10": 67.4}}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--suburb")
    ap.add_argument("--dry-run", action="store_true")
    args = ap.parse_args()
    targets = [args.suburb] if args.suburb else SUBURBS
    today = dt.date.today().isoformat()

    with job_run("units_statutory_comps", cadence_hours=24,
                 title="Units — statutory comparable set (5km / 6 months)") as beat:
        gc = get_client()["Gold_Coast"]
        col = gc["unit_statutory_comps"]
        valuers = {s: UnitValuer(gc, s) for s in SUBURBS}
        S = StatutoryComparables(gc, today, valuers=valuers)
        print(f"  recent-sale pool: {len(S.pool):,} attached sales in the last 6 months")

        reasons, total, avail = Counter(), 0, 0
        # ⚠ TRACKED SEPARATELY BECAUSE THE ASSERTION BELOW IS ABOUT THE PUBLISHED SET.
        # 86.3% was measured over INDEXED units. Over ALL attached stock the rate is 54.5%,
        # because the wider population includes 4,143 dwellings with no bedroom count and
        # 1,086 with no scheme link — neither of which has a page. Asserting the indexed
        # figure against the full population fired a false alarm on the first run: the
        # guard itself broke the "scope the sample" rule it exists to enforce.
        idx_total, idx_avail = [0], [0]
        for suburb in targets:
            ops = []
            # ⚠ PROJ comes from unit_page_data and does NOT carry unit_indexable.
            # Without adding it here every document reads as not-indexed and the
            # assertion below sees 0 of 0 — which is exactly what happened first run.
            for d in gc[suburb].find({}, {**PROJ, "unit_indexable": 1}):
                eff = (d.get("address") or d.get("complete_address")
                       or d.get("street_address") or "")
                if classify_dwelling({**d, "street_address": eff}) != "attached":
                    continue
                slug = d.get("url_slug")
                if not slug:
                    continue
                total += 1
                indexed = d.get("unit_indexable") is True
                idx_total[0] += indexed
                r = S.for_subject(d, suburb)
                if r.get("available"):
                    avail += 1
                    idx_avail[0] += indexed
                else:
                    reasons[r.get("reason")] += 1
                ops.append(UpdateOne({"_id": slug}, {"$set": {
                    "_id": slug, "suburb_key": suburb, "address": eff,
                    "computed_at": dt.datetime.utcnow(),
                    "engine": "statutory_comparables_v1",
                    "accuracy": ACCURACY,
                    **r}}, upsert=True))
                if len(ops) >= 250 and not args.dry_run:
                    col.bulk_write(ops, ordered=False)
                    ops = []
            if ops and not args.dry_run:
                col.bulk_write(ops, ordered=False)

        pct = avail / max(1, total) * 100
        idx_pct = idx_avail[0] / max(1, idx_total[0]) * 100
        print(f"\n  attached evaluated: {total:,}")
        print(f"  statutory set available: {avail:,} ({pct:.1f}% of all attached)")
        print(f"  ON INDEXED PAGES:        {idx_avail[0]:,} of {idx_total[0]:,} "
              f"({idx_pct:.1f}%)  <- the number that matters")
        for k, v in reasons.most_common():
            print(f"    {k:28s} {v:6,}")

        beat.metrics = {"attached": total, "available": avail,
                        "available_pct": round(pct, 1),
                        "indexed": idx_total[0], "indexed_available": idx_avail[0],
                        "indexed_available_pct": round(idx_pct, 1),
                        **{f"reason_{k}": v for k, v in reasons.items()}}
        beat.detail = (f"{idx_avail[0]:,} of {idx_total[0]:,} indexed pages have a "
                       f"statutory set ({idx_pct:.1f}%)")

        # Rule 7b — the zero-output paths.
        if total == 0:
            raise RuntimeError("0 attached dwellings seen — classifier or projection broke")
        if not S.pool:
            raise RuntimeError(
                "0 attached sales in the last 6 months across three suburbs — the sold "
                "pipeline has stopped, which is a defect not a quiet market")
        if avail == 0:
            raise RuntimeError(
                f"{total:,} attached dwellings and not one statutory set — the radius, "
                "the centroids or the bedroom match broke")
        if idx_total[0] == 0:
            raise RuntimeError("0 indexed units seen — flag_unit_indexable has not run")
        # Measured at 86.3% ON INDEXED PAGES when built. A large fall means centroids or
        # bedrooms regressed; a large rise means the recency window stopped being enforced.
        # Scoped to indexed stock deliberately — see the note beside idx_total.
        if not 0.70 <= (idx_avail[0] / idx_total[0]) <= 0.98:
            raise RuntimeError(
                f"availability on indexed pages is {idx_pct:.1f}%, outside the 70-98% band "
                f"this was measured at (86.3%) — refusing to publish a comparable set that "
                f"moved this far unchecked")
    return 0


if __name__ == "__main__":
    sys.exit(main())
