# Decision — what the published range should mean

**Date:** 2026-08-07 · **Decided by:** Will · **Status:** decided, implementation in progress

---

## The question

The range we publish is a flat ±12%. Measured against 641 real sales it contains the eventual sale
**58%** of the time, while two live pages described it as a 90% confidence interval. Two honest
positions were available:

1. Keep ±12% and publish its real coverage
2. Publish the empirical band that actually achieves a stated coverage

## The decision

**Option 2, at 80% coverage.** Will, 2026-08-07:

> *"we should implement the positive findings we have found through testing and experimentation
> above that improve our valuation methodology then update our backtesting accordingly to show the
> new an improved MAE and how much the gap should be between our low and high valuation guides which
> should be 80% of valuations fall in this range."*

So the low and high valuation guides become **an empirically measured 80% band**, not a decoration.
The width becomes a finding that moves as the method improves, rather than a constant.

## What follows from it

1. **The band width is now an output of the backtest**, not a constant in the code. It has to be
   recomputed whenever the method changes, and the figure on the site has to track it.
2. **Improving the method visibly narrows the band.** That is the incentive alignment we want — the
   only way to publish a tighter range is to earn it.
3. **80% is a promise we have to keep.** If a later measurement shows the band covering 71%, the
   band widens. It does not get quietly left alone.
4. **Two bands, not one.** Sold and for-sale homes carry photo-derived attributes that off-market
   homes do not, so the off-market band will be wider than the on-market one. Publishing the
   on-market figure on an off-market report would be a false precision. See
   `methodology/05-what-we-exclude.md`.

## Immediate corrections shipped alongside

Both live pages were factually wrong and were corrected the same day (commit `dcb3e58d`):

- `MethodologyPage.tsx` — the ±12% claim, and a second claim that every comparable is time-adjusted
  (it fires on 2.0%)
- `ValuationAccuracyPage.tsx` — the "90% confidence range" phrasing

## What was explicitly NOT decided

- Whether to publish a **single figure** at all, or lead with the band. Unchanged for now.
- What to do about **golf-course backing** — the finding rests on 46 homes and is not actionable.
- Whether `water_view` homes get their own published treatment, or simply a corrected cohort.

Source: `experiments/2026-08-07-band-width-investigation.md`.
