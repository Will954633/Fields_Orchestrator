#!/usr/bin/env python3
"""
Build public/data/leading_indicators_gc.json — the Gold-Coast-wide dataset for the
IndicatorsExplorer ("Which Signals Actually Lead Prices?") on the planned GC overview
page. Requested by Will 2026-09-12 (see 10_Market_Report/gc_wide_overview_data_scoping_
2026-09-12.md, addendum).

Method — decisions locked with Will's go-ahead 2026-09-12:
  * PRICE TARGET: a Gold-Coast-wide momentum series (YoY % of a composite rolling-12m
    median) built from `Gold_Coast.precomputed_indexed_prices` — every suburb doc with
    >=90% coverage of the 2017-Q3..now window (50 suburbs at build time), weighted by
    each suburb's total transaction count (fixed weights -> no quarter-to-quarter
    composition drift; the weighting is volume-honest and dominated by the northern
    corridor: pimpama, upper_coomera, coomera, ormeau).
  * LAGS ARE NOT RE-PICKED. The lead/lag structure comes from the deep 2008-2026
    3-suburb pooled cross-correlation baked into the parent file
    (public/data/leading_indicators.json). Only r is recomputed, at that fixed lag,
    against the GC series — re-picking best lags on a ~31-point window produces
    spurious winners (observed: clearance r=-0.91 at +7q on n=18).
  * INDICATOR SERIES are reused verbatim from the parent file (they are QLD/national —
    unchanged at GC level).
  * `proj` (forward projection band) is DROPPED: the parent projections were validated
    out-of-sample against the pooled 3-suburb series only. Do not re-add without a GC
    validation run. The engine guards on its absence (IndicatorsExplorer.engine.ts:93).
  * The three per-suburb momentum series are carried through so the explorer's price
    seg control keeps working; the page build should relabel "3-suburb avg" ->
    "Gold Coast" when mounting.

Refresh cadence: like the parent file, this is a baked snapshot for now. When the GC
page ships, add this script to run_monthly_market_precompute.sh AFTER the indexed-
prices step and wrap the call in job_run (Rule 7) — flagged in the scoping report.

Usage:
  python3 scripts/build_gc_leading_indicators.py            # writes website public/data/
  python3 scripts/build_gc_leading_indicators.py --out X    # write elsewhere
  python3 scripts/build_gc_leading_indicators.py --dry-run  # print summary only
"""
import argparse
import json
import math
import sys
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from shared.db import get_client  # noqa: E402
from shared.env import load_env  # noqa: E402

PARENT_JSON = Path("/home/fields/Feilds_Website/01_Website/public/data/leading_indicators.json")
DEFAULT_OUT = Path("/home/fields/Feilds_Website/01_Website/public/data/leading_indicators_gc.json")

WINDOW_START = "2017-Q3"   # wide-suburb rolling series begin 2017-Q2/Q3
MIN_COVERAGE = 0.90        # share of window quarters a suburb must have (post-interpolation)
MAX_GAP_FILL = 2           # interpolate interior gaps up to this many quarters
MIN_QUARTER_WEIGHT = 0.95  # a composite quarter needs this share of total weight, else None
                           # (suburb series end at DIFFERENT quarters — without this the
                           # ragged tail fabricates a momentum cliff from composition
                           # change alone; observed: fake 8.7% -> 0.5% drop at 2026-Q1
                           # when contributors fell from 47 suburbs to 16)
MIN_SUBURBS = 40           # guard: composite must stay genuinely coast-wide
MIN_MOMENTUM_PTS = 28      # guard: enough quarters to correlate on
MIN_LENDING_R = 0.5        # guard: headline signal must survive; if not, data broke


def norm_period(p):  # 'Q3 2016' -> '2016-Q3'
    a, b = p.split()
    return f"{b}-{a}"


def pearson(pairs):
    n = len(pairs)
    if n < 12:
        return None, n
    xs, ys = zip(*pairs)
    mx, my = sum(xs) / n, sum(ys) / n
    sx = math.sqrt(sum((a - mx) ** 2 for a in xs))
    sy = math.sqrt(sum((b - my) ** 2 for b in ys))
    if sx == 0 or sy == 0:
        return None, n
    return sum((a - mx) * (b - my) for a, b in zip(xs, ys)) / (sx * sy), n


def r_at_lag(ind_series, mom, lag, n_q):
    pairs = [
        (ind_series[t], mom[t + lag])
        for t in range(n_q)
        if 0 <= t + lag < n_q and ind_series[t] is not None and mom[t + lag] is not None
    ]
    return pearson(pairs)


def build(dry_run=False, out_path=DEFAULT_OUT):
    parent = json.loads(PARENT_JSON.read_text())
    quarters = parent["quarters"]
    qidx = {q: i for i, q in enumerate(quarters)}
    n_q = len(quarters)

    col = get_client()["Gold_Coast"]["precomputed_indexed_prices"]
    docs = col.find(
        {"_id": {"$nin": ["gold_coast", "gold_coast_average"]}},
        {"_id": 1, "rolling_12m_median_series": 1},
    )
    sub = {}
    for d in docs:
        pts = {
            norm_period(pt["period"]): (pt["rolling_median"], pt.get("transaction_count") or 0)
            for pt in (d.get("rolling_12m_median_series") or [])
            if pt.get("rolling_median") and norm_period(pt["period"]) in qidx
        }
        if pts:
            sub[d["_id"]] = pts

    # Interpolate short INTERIOR gaps per suburb (rolling-12m medians are smooth, so a
    # 1-2 quarter linear fill is safe). Without this the three deepest suburbs (robina,
    # burleigh_waters, varsity_lakes) fail the coverage rule on scattered missing
    # quarters, and remaining contributors flap in/out quarter to quarter.
    for k, m in sub.items():
        idxs = sorted(qidx[q] for q in m)
        for a, b in zip(idxs, idxs[1:]):
            gap = b - a - 1
            if 0 < gap <= MAX_GAP_FILL:
                va, vb = m[quarters[a]][0], m[quarters[b]][0]
                for j in range(1, gap + 1):
                    m[quarters[a + j]] = (va + (vb - va) * j / (gap + 1), 0)

    idx0 = qidx[WINDOW_START]
    window = quarters[idx0:]
    eligible = sorted(
        k for k, m in sub.items() if sum(1 for q in window if q in m) >= MIN_COVERAGE * len(window)
    )
    if len(eligible) < MIN_SUBURBS:
        raise RuntimeError(
            f"only {len(eligible)} suburbs meet {MIN_COVERAGE:.0%} coverage of {WINDOW_START}.. "
            f"(need {MIN_SUBURBS}); upstream precompute has shrunk — not writing"
        )
    weights = {k: sum(tx for _, tx in sub[k].values()) for k in eligible}

    total_weight = sum(weights.values())
    composite = []
    for i, q in enumerate(quarters):
        if i < idx0:
            composite.append(None)
            continue
        num = den = 0
        for k in eligible:
            if q in sub[k]:
                med, _ = sub[k][q]
                num += weights[k] * med
                den += weights[k]
        # composition guard: a quarter missing a meaningful share of the panel would
        # move the composite by mix change, not price change — drop it instead
        composite.append(num / den if den >= MIN_QUARTER_WEIGHT * total_weight else None)

    momentum = [
        round((composite[i] / composite[i - 4] - 1) * 100, 2)
        if i >= 4 and composite[i] and composite[i - 4]
        else None
        for i in range(n_q)
    ]
    mom_pts = [i for i, m in enumerate(momentum) if m is not None]
    if len(mom_pts) < MIN_MOMENTUM_PTS:
        raise RuntimeError(
            f"GC momentum has only {len(mom_pts)} points (need {MIN_MOMENTUM_PTS}) — not writing"
        )

    indicators = []
    r_report = []
    for ind in parent["indicators"]:
        # rateofsale is EXCLUDED at GC level: its series is sold/(sold+unsold) built from
        # OUR 3-suburb listing histories — a local gauge, not a QLD/national indicator.
        # Presenting it on a Gold-Coast-wide board would claim coverage it doesn't have.
        if ind["key"] == "rateofsale":
            continue
        new = {k: v for k, v in ind.items() if k != "proj"}  # proj: pooled-validated only
        r, n = r_at_lag(ind["series"], momentum, ind["lag"], n_q)
        if r is None:
            raise RuntimeError(f"indicator {ind['key']}: too few overlapping points at lag {ind['lag']}")
        new["r"] = round(r, 3)
        indicators.append(new)
        r_report.append((ind["key"], ind["lag"], ind["r"], new["r"], n))

    lending_r = next(abs(x[3]) for x in r_report if x[0] == "lending")
    if lending_r < MIN_LENDING_R:
        raise RuntimeError(
            f"lending r at fixed lag collapsed to {lending_r:.2f} (<{MIN_LENDING_R}) — "
            "input data is broken, not a real regime change; not writing"
        )

    out = {
        "meta": {
            "scope": "gold_coast_wide",
            "generated_at": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
            "price_method": (
                f"YoY momentum of a transaction-weighted composite of rolling-12m medians "
                f"across {len(eligible)} GC suburbs (fixed weights = suburb total transactions), "
                f"window {quarters[mom_pts[0]]}..{quarters[mom_pts[-1]]}"
            ),
            "r_method": (
                "lags fixed from the 2008-2026 pooled cross-correlation (parent file); "
                "r recomputed at that lag against the GC-wide series"
            ),
            "suburbs_used": len(eligible),
            "top_weights": sorted(weights, key=weights.get, reverse=True)[:5],
            "source": "Gold_Coast.precomputed_indexed_prices + parent leading_indicators.json",
        },
        "quarters": quarters,
        "price": {
            "pooled": momentum,               # the GC-wide series (explorer default)
            "robina": parent["price"]["robina"],
            "burleigh_waters": parent["price"]["burleigh_waters"],
            "varsity_lakes": parent["price"]["varsity_lakes"],
        },
        "indicators": indicators,
    }

    print(f"GC composite: {len(eligible)} suburbs · momentum {quarters[mom_pts[0]]}"
          f" -> {quarters[mom_pts[-1]]} ({len(mom_pts)} pts) · latest {momentum[mom_pts[-1]]}%")
    print(f"{'indicator':12s} {'lag':>4s} {'r(3sub)':>8s} {'r(GC)':>7s} {'n':>4s}")
    for key, lag, r_old, r_new, n in r_report:
        print(f"{key:12s} {lag:>+4d} {r_old:>8.2f} {r_new:>7.2f} {n:>4d}")

    if dry_run:
        print("(dry run — nothing written)")
        return
    out_path.write_text(json.dumps(out, separators=(",", ":")) + "\n")
    print(f"wrote {out_path} ({out_path.stat().st_size:,} bytes)")


if __name__ == "__main__":
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[1])
    ap.add_argument("--out", type=Path, default=DEFAULT_OUT)
    ap.add_argument("--dry-run", action="store_true")
    args = ap.parse_args()
    load_env()
    build(dry_run=args.dry_run, out_path=args.out)
