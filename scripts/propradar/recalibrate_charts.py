"""
recalibrate_charts.py — rebase the absolute-level median + volume TREND charts to
PropRadar's authoritative 12-month anchor (method A, approved 2026-07-27).

Our quarterly median/volume series come from an under-captured, premium-skewed sold
sample, so their absolute LEVEL is inflated (median) / deflated (volume) vs the true
market — and would contradict a PropRadar headline on the same card. This scales each
suburb's series by a single per-suburb factor so its trailing-12-month level matches
PropRadar's authoritative figure, preserving our (deep) SHAPE. Ratios (index_value,
yoy_change, total_growth_pct) are uniform-scale-invariant and left untouched; the
rolling-12m headline median/growth are SET to PropRadar exactly.

Idempotent: original values are preserved in *_raw on first run and every recompute
starts from _raw, so re-running never compounds the scaling.

Usage:
    python3 scripts/propradar/recalibrate_charts.py --all --dry-run
    python3 scripts/propradar/recalibrate_charts.py --all --apply
"""
from __future__ import annotations

import argparse
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(os.path.dirname(HERE))
sys.path.insert(0, ROOT)
sys.path.insert(0, HERE)

from shared.db import get_gold_coast_db, cosmos_retry  # noqa: E402
from suburb_stats import house_headline  # noqa: E402

SUBURBS = ["robina", "burleigh_waters", "varsity_lakes"]


def _raw(entry, field):
    """Return the preserved-original value, seeding it on first touch."""
    rk = field + "_raw"
    if rk not in entry or entry[rk] is None:
        entry[rk] = entry.get(field)
    return entry[rk]


def recalibrate_median(db, s, pr, apply):
    doc = db["precomputed_indexed_prices"].find_one({"_id": s})
    if not doc or not pr.get("median_price"):
        return None
    series = doc.get("indexed_series") or []
    raws = [_raw(q, "median_price") for q in series if _raw(q, "median_price")]
    if len(raws) < 4:
        return None
    anchor = sum(raws[-4:]) / 4.0                 # trailing 4 complete quarters ≈ 12mo
    factor = pr["median_price"] / anchor
    before_last = series[-1].get("median_price")
    for q in series:
        rv = _raw(q, "median_price")
        if rv:
            q["median_price"] = round(rv * factor)
    ipq = doc.get("in_progress_quarter")
    if ipq and _raw(ipq, "median_price"):
        ipq["median_price"] = round(_raw(ipq, "median_price") * factor)
    for f in ("latest_price", "baseline_price", "rolling_12m_prev_median_price"):
        rv = _raw(doc, f)
        if rv:
            doc[f] = round(rv * factor)
    doc["rolling_12m_median_price"] = pr["median_price"]
    doc["rolling_12m_yoy_pct"] = pr["growth_1y_pct"]
    doc["calibration"] = {"method": "propradar_anchor", "factor": round(factor, 4),
                          "anchor": round(anchor), "pr_median": pr["median_price"],
                          "as_of": pr.get("as_of")}
    print(f"  MEDIAN  {s}: factor {factor:.3f} | last-qtr {before_last}→{series[-1]['median_price']} "
          f"| rolling {doc.get('rolling_12m_median_price')} (=PR) | yoy→{pr['growth_1y_pct']}%")
    if apply:
        cosmos_retry(lambda: db["precomputed_indexed_prices"].replace_one({"_id": s}, doc),
                     f"recal_median:{s}")
    return factor


def recalibrate_volume(db, s, pr, apply):
    doc = db["precomputed_market_charts"].find_one({"_id": f"{s}_sales_volume"})
    if not doc or not pr.get("sales_12mo"):
        return None
    tl = doc.get("timeline") or []
    for q in tl:
        _raw(q, "sales_count")
    complete = [q for q in tl if not q.get("is_in_progress")]
    if len(complete) < 4:
        return None
    anchor = sum(q["sales_count_raw"] for q in complete[-4:] if q.get("sales_count_raw"))
    if not anchor:
        return None
    factor = pr["sales_12mo"] / anchor
    before_last = complete[-1].get("sales_count")
    for q in tl:
        rv = q.get("sales_count_raw")
        if rv is not None:
            q["sales_count"] = round(rv * factor)
    doc["calibration"] = {"method": "propradar_anchor", "factor": round(factor, 4),
                          "anchor_12mo": anchor, "pr_sales_12mo": pr["sales_12mo"],
                          "as_of": pr.get("as_of")}
    print(f"  VOLUME  {s}: factor {factor:.3f} | trailing-4q {anchor}→{pr['sales_12mo']} (=PR) "
          f"| last complete qtr {before_last}→{complete[-1]['sales_count']}")
    if apply:
        cosmos_retry(lambda: db["precomputed_market_charts"].replace_one({"_id": f"{s}_sales_volume"}, doc),
                     f"recal_volume:{s}")
    return factor


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--suburb", choices=SUBURBS)
    ap.add_argument("--all", action="store_true")
    ap.add_argument("--apply", action="store_true")
    ap.add_argument("--dry-run", action="store_true")
    args = ap.parse_args()
    targets = SUBURBS if args.all else ([args.suburb] if args.suburb else [])
    if not targets:
        ap.error("pass --suburb or --all")
    apply = args.apply and not args.dry_run
    db = get_gold_coast_db()
    for s in targets:
        pr = house_headline(db, s)
        if not pr:
            print(f"{s}: no propradar_suburb_stats — skip"); continue
        print(f"{s}:")
        recalibrate_median(db, s, pr, apply)
        recalibrate_volume(db, s, pr, apply)
    print("APPLIED" if apply else "(dry-run — nothing written)")


if __name__ == "__main__":
    main()
