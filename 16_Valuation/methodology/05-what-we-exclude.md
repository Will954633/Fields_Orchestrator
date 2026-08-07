# 05 — What we refuse to value, and why

**Last verified 2026-08-07.**

The comparable-sales method is built for **detached houses**. Refusing to value the things it was
not built for is not a weakness in the product — publishing a confident number for a townhouse is.

⚠ **Exclusion has to apply to the product, not only to the measurement.** An excluded home must get
`directional_only`, exactly as the design envelope already does outside $1M–$2M. Dropping homes from
the accuracy claim while still publishing figures for them is marking our own homework.

---

## 1. Outside the design envelope

Detached houses below $1,000,000 or above $2,000,000. Structural, not a policy choice — see
`02-design-envelope.md`. Already implemented: `_ENVELOPE_MIN` / `_ENVELOPE_MAX` in
`precompute_valuations.py` suppress **both** the point estimate and the range.

## 2. Attached dwellings

`is_attached_dwelling()` in `scripts/valuation_backtest.py`. **`property_type == "House"` does not
exclude attached stock** — measured 2026-08-07, homes surviving that filter ran MAE 18.0% against
10.3%. Four signals, any one sufficient:

| signal | notes |
|---|---|
| `property_type` in the attached list | unit, apartment, townhouse, villa, duplex, terrace… |
| `is_strata_title` | trustworthy when present, frequently absent |
| cadastral `UNIT_NUMBER`, or a unit-numbered address | catches `6/27 Beachcomber Court` |
| **QLD plan prefix** `GTP` / `BUP` / `CTS` / `SUP` | community or building-units title. 27 of 990 sold "Houses". `RP` (533) and `SP` (328) are freehold and prove nothing either way |
| **floor-to-land ratio > 0.70** | see below |

### The floor-to-land rule

A detached house needs setbacks, a driveway and some yard, so its ratio cannot approach 1.0. Across
833 sold houses with both figures: **p50 0.32, p75 0.44, p90 0.60**. A threshold of **0.70** leaves
clear air.

**24 Brooklyn Crescent, Robina** is the case that motivated it: 131 m² of land to 122.4 m² of floor —
**0.93** — on a cadastral parcel measuring 5 m × 26 m. Freehold tenure, no unit number,
`property_type "House"`, `is_strata_title False`. **Every other signal missed it.** We valued it 56%
high.

The rule also catches genuine data errors (7 Nypa Close: 495 m² of floor on 495 m² of land). Both
classes belong out of a detached-house valuation, so the double duty is a feature.

## 3. Records missing 3+ of 4 core facts

Land size, floor area, bedrooms, bathrooms. 23 homes in the sample, MAE 19–26%. `41 Kirralee Drive`
had no bedrooms, bathrooms or land size recorded and we produced a number anyway.

⚠ Missing **1 or 2** of the four is **not** a problem — those homes run MAE 10.2% against 10.0% for
complete records. Do not tighten this to "any missing fact"; the evidence does not support it.

## 4. ⚠ Not an exclusion, but a measurement rule — the blind subject

Three attributes come from photo analysis:

| attribute | on sold homes | on off-market homes |
|---|---|---|
| `renovation_quality_score` | 89% | **0%** |
| `kitchen_score` | 86% | **0%** |
| `number_of_stories` | 89% | **0%** |

Sold and for-sale homes have marketing photographs. **Off-market homes have none** — and off-market
*is* the product.

So a backtest run on sold subjects values a property richer than the one we actually meet, and
reports an accuracy we cannot deliver off-market. Use **`--blind-subject`** for any figure that will
be quoted about the off-market report.

This is also why `renovation_quality` fires on 79.9% of backtest comparables and **0.2%** of
production ones: `calculate_adjustments` skips an attribute when either side is None, and in
production the *subject* side is always None. Any ablation conclusion about those three attributes
drawn from a sighted backtest is invalid for the off-market product.

Source: `experiments/2026-08-07-band-width-investigation.md` Parts 3 and 6.
