# Experiment — the published 80% bands now contain ~72–76%, and the floor-area fix is accuracy-neutral

**Date:** 2026-08-20 (AEST) · **Scope:** detached houses $1M–$2M, per suburb, `--price-filter
none --blind-subject` · **Append-only — do not edit results.**

Two questions, one run each. (1) Did the 2026-08-20 floor-area fixes change accuracy? (2) Do
the published per-suburb 80% bands still contain 80%?

## Commands

```bash
# per suburb, on the CURRENT (fixed) engine
python3 scripts/valuation_backtest.py --suburb <s> --price-filter none --blind-subject \
    --min-price 1000000 --max-price 2000000
```

For the A/B, the pre-edit engine was reconstructed as a baseline copy (`pv_BASELINE.py`) by
reversing the three edits, **verified to define each function exactly once** (the first
reconstruction had two `def basic_features` and Python would have silently used the second —
the "control" would have measured nothing), then swapped in over the live file for the
baseline run and restored (md5-checked) afterward.

## Result 1 — the floor-area fix is accuracy-neutral

Same sales, both engine versions:

| suburb | baseline (pre-fix) | fixed | n |
|---|---|---|---|
| Robina | MAE 9.1%, w10 64% | MAE 9.0%, w10 65% | 261 |
| Varsity Lakes | MAE 7.6%, w10 72% | MAE 7.6%, w10 71% | 194 |
| Burleigh Waters | MAE 9.1%, w10 64% | MAE 9.2%, w10 63% | 150 |

All differences ≤0.1pp — sampling noise. The `basic_features`→`resolve_floor_area` change and
the 80 m² house floor **do not move accuracy**; they fix a display contradiction and drop
~29 impossible bad-scrape floor areas (e.g. 5-bed/4-bath in 45 m²) to `insufficient_data`.

⚠ **A naive "this run vs the published 2026-08-08 figures" comparison is INVALID** and read as
degradation (Robina 8.2→9.0). The n differs (261 vs 251, etc.) — 12 days of extra settled
sales changed the test population. Only the same-data A/B above is trustworthy. This is the
same class of trap as the leaked `--price-filter sale` MAE.

## Result 2 — the bands have drifted too narrow

The stored per-suburb bands (from `2026-08-08-figures.md`, `_SUBURB_80_BAND` in
`precompute_valuations.py:2340`) against this run:

| suburb | published band | contains now | width for 80% |
|---|---|---|---|
| Robina | ±12.2% | **~72%** | ~±14.7% |
| Varsity Lakes | ±11.2% | **~75%** | ~±12.5% |
| Burleigh Waters | ±14.0% | **~76%** | ~±15.5% |

(within-X coverage this run — Robina 10:65 15:81 20:89 · Varsity 10:71 15:89 20:95 · Burleigh
10:63 15:79 20:90; interpolated to the published band widths.)

Confirmed on the baseline engine too, so **not caused by the floor-area change** — it is
genuine drift, a market move, or noise on a recent-sales window of n≈150–260.

## What would falsify / resolve it

- Re-measure over a **longer sales window** so n is not driven by a handful of recent sales;
  if coverage returns to ~80%, the drift is a small-window artefact.
- If it holds, the engine's own rule (`precompute_valuations.py:2150`: coverage below 80%
  WIDENS the band) requires widening to ≈±14.7 / 12.5 / 15.5% and updating every surface that
  quotes the band + its `measured_on` date.

## Decision taken

**Hold, do not reflexively widen** (Will, 2026-08-20). Folded into the full methodology
review — `../METHODOLOGY_REVIEW_TASK.md`. Until resolved, `range_basis.note` and the
report page's "four in five" claim overstate on all three suburbs; the report page is not to
ship to real users. See `../decisions/2026-08-20-valuation-report-page.md`.
