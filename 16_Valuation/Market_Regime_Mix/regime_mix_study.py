#!/usr/bin/env python3
"""
Market-Regime Mix Study — does the MIX of homes that sell change with the cost of money?

Hypothesis (Will, 2026-09-09): expensive homes within a suburb sell freely when credit
is cheap, and stop selling (or discount heavily) when finance costs rise. We cannot
re-run the renovation-premium study per regime (vision tiers only exist for the 2024-26
scraped window), but sale-price MIX needs no photos — only price, date, suburb.

Data: raw sale events 2015-2026 from Gold_Coast.<suburb> Domain timelines, extracted
with the SAME union+dedupe logic as the published seasonality article
(scripts/seasonality_analysis.py:extract_sales — 3 timeline paths, address+date+price
dedupe). Houses only. This source covers COVID years and 2026, unlike the 18,978-row CSV.

Regimes (RBA cash rate):
  flat_easing        2015-2019   2.25% -> 0.75%, flat-to-modest market
  cheap_credit_boom  2020-2021   0.25%/0.10% emergency rates, boom
  tightening         2022-2023   0.10% -> 4.35% in 18 months
  easing_recovery    2024-2026   plateau then cuts, prices rising again

Method: within each suburb-YEAR, every sale is expressed as a ratio to that
suburb-year median (removes trend/level, keeps shape). Per suburb-regime we report
the shape of what sold: premium-tier share (>1.5x median), upper-tail share (>2.0x),
entry-tier share (<0.75x), p90/p10 spread, with Wilson 95% CIs on shares.
If Will's hypothesis holds, premium-tier share should compress in `tightening`
relative to `cheap_credit_boom`.

⚠ Capture-drift caveat (mandatory in any write-up): the timelines only exist on
properties we later scraped, and capture completeness has changed over the years
(see memory: data_source_undercapture_reset). Within-year RATIOS are robust to how
many sales we captured, but not to WHICH sales we captured — if early-year capture
skews toward a segment, shape shifts can be artefacts. Yearly n is printed so thin
years are visible; treat pre-2019 shape with caution.

Usage: python3 regime_mix_study.py
Outputs: results JSON + printed tables, next to this script.
"""

import json
import sys
from pathlib import Path

import numpy as np

sys.path.insert(0, "/home/fields/Fields_Orchestrator")
sys.path.insert(0, "/home/fields/Fields_Orchestrator/scripts")
from shared.db import get_client                     # noqa: E402
from seasonality_analysis import extract_sales       # noqa: E402

SUBURBS = ["robina", "varsity_lakes", "burleigh_waters"]
YEAR_MIN, YEAR_MAX = 2015, 2026
REGIMES = {  # year -> regime
    **{y: "flat_easing" for y in range(2015, 2020)},
    2020: "cheap_credit_boom", 2021: "cheap_credit_boom",
    2022: "tightening", 2023: "tightening",
    2024: "easing_recovery", 2025: "easing_recovery", 2026: "easing_recovery",
}
REGIME_ORDER = ["flat_easing", "cheap_credit_boom", "tightening", "easing_recovery"]
MIN_YEAR_N = 30  # suburb-years thinner than this are flagged, not silently pooled
OUT = Path(__file__).resolve().parent


def wilson(k, n, z=1.96):
    if n == 0:
        return None
    p = k / n
    d = 1 + z * z / n
    c = (p + z * z / (2 * n)) / d
    h = z * np.sqrt(p * (1 - p) / n + z * z / (4 * n * n)) / d
    return [round((c - h) * 100, 1), round((c + h) * 100, 1)]


def main():
    db = get_client()["Gold_Coast"]
    rows = []
    for suburb in SUBURBS:
        for r in extract_sales(db, suburb):
            if r["property_type"] != "House":
                continue
            if not YEAR_MIN <= r["year"] <= YEAR_MAX:
                continue
            rows.append(r)
    if not rows:
        raise RuntimeError("0 sale events extracted — upstream extraction broken, not an empty market")

    # ratio to suburb-year median
    by_sy = {}
    for r in rows:
        by_sy.setdefault((r["suburb"], r["year"]), []).append(r["price"])
    med = {k: float(np.median(v)) for k, v in by_sy.items()}
    for r in rows:
        r["ratio"] = r["price"] / med[(r["suburb"], r["year"])]
        r["regime"] = REGIMES[r["year"]]

    results = {"note": "houses only; ratio = price / suburb-year median",
               "regimes": {k: [y for y, v in REGIMES.items() if v == k] for k in REGIME_ORDER},
               "yearly": {}, "regime_mix": {}}

    for suburb in SUBURBS:
        sr = [r for r in rows if r["suburb"] == suburb]
        # yearly table (volume visibility for the capture caveat)
        results["yearly"][suburb] = {
            y: {"n": len(g), "median": int(np.median([r["price"] for r in g])),
                "thin": len(g) < MIN_YEAR_N}
            for y in range(YEAR_MIN, YEAR_MAX + 1)
            if (g := [r for r in sr if r["year"] == y])}
        # regime mix
        results["regime_mix"][suburb] = {}
        for reg in REGIME_ORDER:
            g = [r["ratio"] for r in sr if r["regime"] == reg]
            if len(g) < 20:
                results["regime_mix"][suburb][reg] = {"n": len(g), "note": "too thin"}
                continue
            a = np.array(g)
            n = len(a)
            k15, k20, k075 = int((a > 1.5).sum()), int((a > 2.0).sum()), int((a < 0.75).sum())
            results["regime_mix"][suburb][reg] = {
                "n": n,
                "premium_share_gt1.5x_pct": round(k15 / n * 100, 1),
                "premium_ci": wilson(k15, n),
                "tail_share_gt2x_pct": round(k20 / n * 100, 1),
                "tail_ci": wilson(k20, n),
                "entry_share_lt0.75x_pct": round(k075 / n * 100, 1),
                "entry_ci": wilson(k075, n),
                "p90_p10_ratio": round(float(np.percentile(a, 90) / np.percentile(a, 10)), 2),
                "p99_ratio": round(float(np.percentile(a, 99)), 2),
            }

    (OUT / "results_regime_mix.json").write_text(json.dumps(results, indent=1))
    # compact console view
    for suburb in SUBURBS:
        print(f"\n== {suburb} ==")
        for reg in REGIME_ORDER:
            m = results["regime_mix"][suburb].get(reg, {})
            if "note" in m or not m:
                print(f"  {reg:18s} n={m.get('n', 0):4d}  (too thin)")
                continue
            print(f"  {reg:18s} n={m['n']:5d}  >1.5x {m['premium_share_gt1.5x_pct']:4.1f}% {m['premium_ci']}"
                  f"  >2x {m['tail_share_gt2x_pct']:4.1f}% {m['tail_ci']}"
                  f"  <0.75x {m['entry_share_lt0.75x_pct']:4.1f}%  p90/p10 {m['p90_p10_ratio']}")
        print("  yearly n:", {y: v["n"] for y, v in results["yearly"][suburb].items()})
    print(f"\nwrote {OUT/'results_regime_mix.json'}", file=sys.stderr)


if __name__ == "__main__":
    main()
