# 01 — How the valuation works, end to end

**Last verified 2026-08-08.** This is the current method. Everything here is measured; every figure
has a reproduction command in `accuracy/`.

---

## In one paragraph

We take a subject property, find every sold house in its cohort, adjust each of those sales for its
measurable differences from the subject, shrink those adjustments for the error in our own
measurements, take the median, correct for the suburb's known bias, and publish a band that four in
five sales actually land inside. **No AI runs at valuation time.** Every number is arithmetic over
recorded sales.

## The pipeline

| # | stage | what happens |
|---|---|---|
| 1 | **Cohort filter** | Sold houses within the bedroom band, same dwelling type, same water class, comparable prestige tier, within distance. Median **47 candidates**. |
| 2 | **Adjustment** | Each candidate is adjusted toward the subject on land size, floor area, bedrooms, bathrooms, car spaces, condition, pool, property age, street premium, micro-location, beach proximity, water views, golf backing. |
| 3 | **Reliability shrinkage** | The total adjustment is multiplied by **0.80**. |
| 4 | **Estimate** | The **median of the whole adjusted pool**. |
| 5 | **Suburb calibration** | Multiplied by that suburb's measured correction factor. |
| 6 | **Band** | **±12.2%** — an empirically measured 80% band. |
| 7 | **Gates** | Outside $1M–$2M, attached dwellings, or too few comparables → direction only, no figure. |
| 8 | **Display** | The **eight** strongest comparables are shown to the reader. |

## ⚠ Stage 3 — reliability shrinkage, and why it exists

Every adjustment is `(subject_attribute − comp_attribute) × rate`. The measured difference carries
error: floor areas come from different sources, land sizes from cadastre, condition from
photographs. Adjusting by the **full** measured difference therefore over-corrects. This is
regression dilution, and the standard remedy is to shrink by a reliability factor.

**It is not a curve-fit.** λ was tuned on a random half of 581 sales and evaluated on the held-out
half: **MAE 8.31% / band ±12.7%, against 9.01% / ±14.2% at λ=1.0.**

| λ | 1.00 | 0.90 | 0.85 | **0.80** | 0.75 | 0.70 | 0.60 |
|---|---|---|---|---|---|---|---|
| MAE | 8.58% | 8.24% | 8.12% | **8.05%** | 7.98% | 7.94% | 8.20% |
| band | 13.7% | 13.2% | 12.5% | **12.2%** | 12.5% | 12.8% | 13.1% |

⚠ **λ should RISE toward 1.0 as our attribute data improves.** It measures how noisy our inputs are,
not a property of the market. Re-derive it whenever the band is re-derived.

## ⚠ Stage 4 — why the estimate uses the whole pool but we show eight

The selector is good at picking the eight most useful comparables to *show* — measured, it beats a
random eight by 0.95pp of MAE and beats a random twenty. **But it must not bound the estimate.**

`verify_comparable()` demotes any comparable whose *adjusted* price sits more than 15% from the
cohort median, plus a z-score test on the same quantity, plus a weighting factor scoring the same
distance. The intent is reasonable — after adjustment, comps should converge, so a straggler looks
anomalous. **The flaw is that it assumes our adjustment is correct.** When adjustment is imperfect, a
comparable disagrees partly *because we adjusted it badly*, and the ones we adjust worst are the ones
most different from the subject — which skew dear.

Since the estimate cannot exceed its priciest input, dropping the priciest comparables put a ceiling
on it: **42% of homes sold above every comparable in their own set**, against ~12% expected.
Computing from the whole pool takes that to **4%**.

Every candidate in that pool has already passed the cohort filter, so this is not a loosening of what
counts as comparable. It is the same similarity test without a second filter keyed to the answer.

## What the reader is told

> Your estimate is built from every comparable sale we hold. Here are the eight closest to your home.

## Current accuracy

| | |
|---|---|
| MAE | **8.05%** |
| median error | **6.44%** |
| within 10% | **69%** |
| within 5% | 40% |
| **80% band** | **±12.2%** — $391,904 on a $1.6M home |

n = 581 detached houses $1M–$2M, off-market (blind) subjects. Full reproduction:
`accuracy/2026-08-08-figures.md`.

See [[02-design-envelope]], [[03-the-range]], [[04-water-and-cohorts]], [[05-what-we-exclude]].
