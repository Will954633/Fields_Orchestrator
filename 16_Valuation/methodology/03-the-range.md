# 03 — The range: what ±12% is, and what it is not

**Last verified 2026-08-07** against 641 real sales inside the design envelope.

---

## What it is

A **flat ±12% of the point estimate**. That is the whole rule. It is computed in
`precompute_valuations.py` as a fixed fraction — it is not derived from the dispersion of the
comparables, the confidence tier, or anything else about the individual property.

## What it is not

**It is not a confidence interval, and it must never be described as one.**

Until 2026-08-07 two live pages said it was:

- `MethodologyPage.tsx` — *"The reconciled range is a 90% confidence interval; ~10% of properties
  will fall outside."*
- `ValuationAccuracyPage.tsx` — *"Our 90% confidence range captured the actual sale price X% of the
  time"* — which contradicted itself on screen, since X was nowhere near 90.

Both corrected. **Do not reintroduce this language anywhere**, including appraisal PDFs, the
off-market report, article copy, or ad copy.

## Measured coverage

| what we print | band on a $1.6M home | contains the eventual sale |
|---|---|---|
| **±12%, as shipped** | $384,000 | **58%** |
| ±16.4% (after per-suburb offsets) | $524,000 | 80% |
| ±18.9% (uncorrected) | $604,000 | 80% |

So **roughly four sales in ten fall outside the band we publish**, not one in ten. A genuine 90%
band would need about ±26.4%.

## The consequence for how we talk about it

There are only two honest positions, and they are a genuine trade-off rather than a right answer:

1. **Keep ±12% and state its real coverage.** The number stays familiar and tight; we say plainly
   that it contains the sale closer to six times in ten than nine. Risk: a band that misses 40% of
   the time invites the question of why we publish it at all.
2. **Publish the empirical 80% band.** Honest by construction, and the width is then a *finding*
   rather than a decoration. Risk: ~$500,000 on a $1.6M home reads as low confidence, and a reader
   who wanted a number gets a corridor.

See `decisions/2026-08-07-range-meaning.md`.

## What does NOT narrow it

Tested 2026-08-07, all negative — recorded so they are not retried:

- **Adaptive width** by comp dispersion: average ±17.0% against a flat ±16.4%. Pooling beats
  stratification. The signals are real but weak (best `adj_cv`, r=+0.248 against absolute error).
- **Blending toward the raw-comp median**: ±18.2%. Marginal.
- **Flat de-biasing**: fixes the centre, leaves the width alone.
- **Refitting every adjustment multiplier**: ±15.5% against ±15.6% for a simple three-attribute
  drop, and in-sample.

## What does

| | 80% band on $1.6M |
|---|---|
| as shipped | $604,000 |
| + per-suburb offsets | $528,000 |
| + drop the subjective adjustments | $501,000 |
| + exclude attached and 3+-missing records | $479,000 |

⚠ Every figure above is measured on **sold** subjects, which carry photo-derived attributes that
off-market subjects do not. See `05-what-we-exclude.md` and use `--blind-subject` for any figure
quoted about the off-market product.

## The open question

Nothing tested establishes **how narrow this method could ever be**. The outstanding test is
leave-one-out inside the comp set: how well the weighted mean of seven adjusted comparables predicts
the eighth. That is the method's internal consistency and an upper bound on achievable accuracy. If
it lands near ±15%, the width is irreducible market noise — two genuinely similar houses sell for
different prices — and the honest move is to change how the range is *presented*, not computed.

Source: `experiments/2026-08-07-band-width-investigation.md`.
