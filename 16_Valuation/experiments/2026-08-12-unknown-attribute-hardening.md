# 2026-08-12 — Unknown-vs-known attribute hardening (water_views, cladding, stories, ac_type)

**Status: WRITTEN, NOT ENABLED.** Ships behind `VALUATION_UNKNOWN_HARDENING=1`.
Default behaviour is unchanged and verified so (below).

---

## The defect

`calculate_adjustments()` collapsed an **unknown** subject attribute to a concrete
**inferior** value:

```python
s_water = 1 if subject_features.get('water_views') else 0   # unknown -> "no water view"  ($120k)
s_clad  = subject_features.get('cladding_level', 2)         # unknown -> brick
s_stories = subject_features.get('number_of_stories') or 1  # unknown -> single storey
s_ac    = 1 if subject_features.get('ac_ducted') else 0     # unknown -> not ducted
```

An un-analysed subject was therefore marked **down** against any comparable that *had*
been analysed. This is the same defect class as the pool default fixed 2026-08-07, which
had penalised ~894 homes the full pool rate (~$75k).

**It also happens one layer earlier.** `basic_features()` collapsed the unknowns before
`calculate_adjustments()` ever saw them (`water_views ... else False`, `cladding_level`
defaulting to 2, `ac_ducted = ac_type == 'ducted'`), so a `None`-check in the adjustment
function alone would never have fired. Both layers are guarded.

**Why it matters more at corpus scale:** pre-populating ~15,000 off-market reports means
subjects with little or no photo coverage being compared against *listed* comparables with
73–97% coverage. The markdown is systematic and invisible, and it penalises precisely the
homes we know least about.

### Related: `--blind-subject` was not blinding

`valuation_backtest.py` states *"calculate_adjustments already skips an attribute when
either side is None, so nulling the subject is sufficient."* That was true for pool and
condition, **false for `number_of_stories`** — the only non-retired attribute in
`_PHOTO_DERIVED_SUBJECT_ATTRS` (the other two, `renovation_quality_score` and
`kitchen_score`, are retired and contribute $0). So the harness that produced our published
off-market figures was *penalising* storey count, not ignoring it.

The tuple is also **incomplete**: `water_views`, `cladding_level` and `ac_ducted` are
equally photo-derived and equally absent off-market. Added behind `BACKTEST_BLIND_FULL=1`
(opt-in, because changing the default changes the published figures).

---

## Measurement

`--price-filter none --property-type House --min-price 1000000 --max-price 2000000
--suburb robina --blind-subject`, n=253, identical data, A/B via the flag.

### Standard blinding (shipped `_PHOTO_DERIVED_SUBJECT_ATTRS`)

| | legacy | hardened | Δ |
|---|---|---|---|
| MAE | 9.1% | 9.2% | +0.1pp |
| median AE | 6.7% | 6.7% | — |
| bias | +2.0% | +2.3% | +0.3pp |
| within 10% | 66% | 65% | −1pp |

### Full photo-blinding (`BACKTEST_BLIND_FULL=1`) — simulates a real off-market subject

| | legacy | hardened | Δ |
|---|---|---|---|
| MAE | 9.0% | 9.2% | +0.2pp |
| **median AE** | 7.2% | **6.7%** | **−0.5pp better** |
| **bias** | **+0.7%** | **+2.1%** | **+1.4pp** |
| within 10% | 66% | 64% | −2pp |

---

## Interpretation — two wrongs were cancelling

Median error **improves**; MAE and bias worsen. The markdown was silently subtracting
~1.4% from an estimate that already runs **high** — an *uncontrolled* bias correction whose
magnitude depended on how much data happened to be missing.

Most of the exposed overvaluation is the **known-stale suburb calibration**. The refit
recorded 2026-08-10 is holdout-validated and unapplied:

| suburb | live | refit | bias at refit |
|---|---|---|---|
| robina | 1.0189 | **1.0058** | +1.52% → +0.22% |
| varsity_lakes | 1.1243 | **1.1038** | +2.66% → +0.78% |
| burleigh_waters | 0.9925 | **1.0177** | −3.81% → −1.37% |

Robina is being corrected **up 1.89%** where the refit says 0.58%. That is the +2.1%.

Fixing bias belongs in the calibration layer, not in an unrelated attribute default that
only fires when data is missing.

---

## Why it is off by default

Enabling it alone would raise every stored valuation ~1.4% at the next 20:30 recompute
while the live page still publishes accuracy measured under the old behaviour — exactly
the situation declined on 2026-08-10 (*"the page would then state a track record for a
method the site had stopped running"*).

**Ship as ONE change:**
1. `VALUATION_UNKNOWN_HARDENING=1`
2. the calibration refit (`experiments/calibration_refit.py`)
3. re-derived page tables (`refresh_page_accuracy.py`, `v4/valuationCopy.ts`)

Then re-derive the published figures and the per-suburb 80% bands together.

---

## Default-path verification

Backtest output with the flag off is unchanged from the pre-change baseline:

```
pre-change baseline   MAE 9.1%  ($136,573)
flag off              MAE 9.1%  ($136,566)
```

The $7 gap is **harness noise, not the change** — two consecutive runs of the *identical*
configuration differ by $6 ($136,566 vs $136,560). Percentage MAE, median, bias and all
within-N buckets are identical.

⚠ **Side finding: `valuation_backtest.py` is not deterministic.** Repeated identical runs
differ by ~$6 on mean absolute error. Small, but it means no A/B below ~0.05pp is readable,
and any future refit should average several runs or pin the comparable ordering (likely an
unsorted Mongo cursor).

---

## Files

- `07_Valuation_Comps/precompute_valuations.py` — `_LEGACY_UNKNOWN` flag; guards in
  `basic_features()` and the four adjustment blocks in `calculate_adjustments()`
- `scripts/valuation_backtest.py` — `BACKTEST_BLIND_FULL` extension to
  `_PHOTO_DERIVED_SUBJECT_ATTRS`
