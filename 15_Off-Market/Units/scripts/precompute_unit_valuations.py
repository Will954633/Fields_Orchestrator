#!/usr/bin/env python3
"""precompute_unit_valuations.py — write the unit range where the site can read it.

The method works (see backtest_unit_valuation.py: Robina median error 6.3%, MAE 9.3%,
within-10% 68.0% — better than the house method) but nothing on the live site consumes
it, so a unit owner still reads "we are not going to put a figure on this home".

WRITES TO `Gold_Coast.unit_valuations`, KEYED BY url_slug — deliberately NOT into
`valuation_data` on the property document. That field belongs to the house
comparable-sales engine, carries its own design-envelope and directional_only
semantics, and is read by the appraisal flow, the mini-site and the ops dashboard.
Writing a differently-derived number into it would make two methods indistinguishable
downstream, which is how "the same figure means two things" bugs start.

⚠ `publishable` IS PART OF THE RECORD, NOT A CALLER'S DECISION.
Burleigh Waters measures within-10% on 49.1% of homes (n=167) against 68.0% in Robina.
A caller must not have to know that. Every document says whether its own suburb has
earned a published figure, so a page cannot accidentally show a weaker number in the
same clothes as a stronger one.
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
from unit_valuation import UnitValuer, ACCURACY         # noqa: E402
from unit_page_data import PROJ                         # noqa: E402

SUBURBS = ["robina", "varsity_lakes", "burleigh_waters"]


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--suburb")
    ap.add_argument("--limit", type=int)
    ap.add_argument("--dry-run", action="store_true")
    args = ap.parse_args()
    targets = [args.suburb] if args.suburb else SUBURBS

    with job_run("units_valuation_precompute", cadence_hours=24,
                 title="Units — precompute attached valuations") as beat:
        gc = get_client()["Gold_Coast"]
        col = gc["unit_valuations"]
        totals = Counter()

        for suburb in targets:
            V = UnitValuer(gc, suburb)
            acc = ACCURACY.get(suburb)
            ops, n, ranged = [], 0, 0
            cur = gc[suburb].find({}, PROJ)
            for d in cur:
                eff = (d.get("address") or d.get("complete_address")
                       or d.get("street_address") or "")
                if classify_dwelling({**d, "street_address": eff}) != "attached":
                    continue
                slug = d.get("url_slug")
                if not slug:
                    continue
                n += 1
                if args.limit and n > args.limit:
                    break
                r = V.value(d)
                doc = {
                    "_id": slug,
                    "suburb_key": suburb,
                    "address": eff,
                    "method": r.get("method"),
                    "tier": r.get("tier"),
                    "computed_at": dt.datetime.utcnow(),
                    "engine": "unit_comparables_v1",
                }
                if r.get("method") == "same_complex_comparables":
                    ranged += 1
                    doc.update({
                        "low": r["low"], "high": r["high"], "point": r["point"],
                        "band_pct": r["band_pct"], "n_comps": r["n_comps"],
                        "n_available": r.get("n_available"),
                        "adjusted_low": r.get("adjusted_low"),
                        "adjusted_high": r.get("adjusted_high"),
                        "comparables": r.get("comparables", [])[:8],
                        "band_basis": r.get("band_basis"),
                        "accuracy": r.get("accuracy"),
                        # See module docstring — the record decides, not the caller.
                        "publishable": bool(r.get("publishable")),
                        "dropped_too_old": r.get("dropped_too_old"),
                        "dropped_undeflatable": r.get("dropped_undeflatable"),
                    })
                else:
                    doc.update({
                        "decline_reason": r.get("decline_reason"),
                        "explain": r.get("explain"),
                        "publishable": False,
                    })
                ops.append(UpdateOne({"_id": slug}, {"$set": doc}, upsert=True))
                if len(ops) >= 250 and not args.dry_run:
                    col.bulk_write(ops, ordered=False)
                    ops = []
            if ops and not args.dry_run:
                col.bulk_write(ops, ordered=False)
            totals[suburb] = n
            totals["ranged"] += ranged
            totals["total"] += n
            pub = "yes" if (acc and acc["within10"] >= 55) else "NO — figure withheld"
            print(f"  {suburb:17s} {n:6,} attached · {ranged:6,} with a range "
                  f"({ranged/max(1,n)*100:4.1f}%) · publishable: {pub}")

        beat.metrics = {"attached": totals["total"], "ranged": totals["ranged"],
                        "coverage_pct": round(totals["ranged"] / max(1, totals["total"]) * 100, 1)}
        beat.detail = f"{totals['ranged']:,} of {totals['total']:,} attached dwellings valued"

        # Rule 7b — the zero-output path. Attached stock and the method both exist; a run
        # that values nothing means the classifier, the index or the comparable pool
        # broke, never that the market emptied.
        if totals["total"] == 0:
            raise RuntimeError("0 attached dwellings seen — the classifier or projection broke")
        if totals["ranged"] == 0:
            raise RuntimeError(f"{totals['total']:,} attached dwellings but 0 valued — "
                               "the method is refusing everything, which is a defect not a market")
        rate = totals["ranged"] / totals["total"]
        if rate < 0.35:
            raise RuntimeError(f"only {rate*100:.1f}% valued; measured reachability is ~60% — "
                               "a large drop means an input regressed")
    return 0


if __name__ == "__main__":
    sys.exit(main())
