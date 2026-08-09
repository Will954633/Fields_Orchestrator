
---

# ⚠ CORRECTION, same day — the above is measured over the WRONG SET

Everything above reconciles over `included_points`, the **8 displayed** comparables. Production
reconciles `calculate_confidence()` over the **full candidate pool** (~49). Re-measured that way
(`lambda_production.py`, same 631 homes, per-suburb calibration applied), adjusting is a clear win
and the conclusion above is void.

| adjustment strength | MAE | median | 80% band | within 10% |
|---|---|---|---|---|
| 0.0 — none | 8.87% | 7.63% | ±13.72% | 62.8% |
| 0.3 | 7.93% | 6.61% | ±12.23% | 70.5% |
| **0.5 — optimum** | **7.72%** | **6.40%** | **±11.90%** | **71.5%** |
| 0.8 — SHIPPED | 8.17% | 6.76% | ±12.44% | 69.7% |
| 1.0 — full | 8.86% | 6.91% | ±13.71% | 66.6% |

**λ=0.8 reproduces the documented figures** (MAE 8.05%, band ±12.2%, within-10% 69%) almost
exactly, which confirms the published numbers describe full-pool + λ=0.80 and that this harness
is measuring the right thing.

## Will's band-width framing was correct

He proposed measuring accuracy as *how wide the band must be to contain the sale price 80% of the
time*. On the wrong set that answered "no". On the right set it answers clearly:

**±13.72% unadjusted → ±12.44% as shipped → ±11.90% at the optimum.**
On a $1.5M home: **$411,626 → $373,314 → $356,947.**

Sayable today, quoting what we actually ship: *adjusting for the differences lets us quote a range
about **9% narrower** for the same reliability* — about **$38,000** on a $1.5M home. At λ=0.5 that
becomes 13% narrower / $55,000.

## Two defects this surfaced

**1. λ=0.8 is not optimal; 0.5 is.** MAE 8.17% → 7.72%, band ±12.44% → ±11.90%. One constant,
`_ADJUSTMENT_RELIABILITY` in `precompute_valuations.py`.

**2. The backtest no longer reproduces production.** `scripts/valuation_backtest.py` reconciles
from `included_points` (line 528) and never imports `apply_adjustment_reliability` — it is missing
BOTH changes credited with producing the current figures. Run on Robina today:

| | documented | backtest today |
|---|---|---|
| n | 251 | 253 |
| MAE | 8.2% | **9.4%** |
| median | 6.6% | **7.0%** |
| within 10% | 67% | **62%** |

The per-suburb bands on the live page were measured with a configuration the committed tool
cannot currently re-run. **Fix the backtest before re-deriving any accuracy figure from it.**

## ⚠ The win is not uniform by suburb

| suburb | n | λ=0 | λ=0.5 | λ=0.8 |
|---|---|---|---|---|
| Robina | 272 | ±14.44% | **±12.92%** | ±13.02% |
| Varsity Lakes | 205 | ±14.41% | **±11.60%** | ±10.90% |
| Burleigh Waters | 154 | **±11.23%** | ±11.64% | ±13.16% |

**Adjusting makes Burleigh Waters worse at every strength.** The aggregate win is Robina and
Varsity Lakes. A per-suburb λ is plausible but that is three constants fitted on 631 homes —
a hypothesis to test on held-out data, not a result to ship.
