# Does adjusting comparables make the answer more accurate? — no

**Date:** 2026-08-10 · **n = 631** sold houses, $1M–$2M, Robina / Varsity Lakes / Burleigh Waters
**Script:** `16_Valuation/experiments/adjustment_accuracy.py` → `adjustment_accuracy.jsonl`
**Asked by:** Will, to support a line on the V4 report: *"By adjusting for specific individual home
differences, our valuations become x% more accurate."*

## The answer

**There is no such number, and the measurement points the other way.** The line must not be
published.

| | unadjusted | adjusted | change |
|---|---|---|---|
| mean error | **9.67%** | **10.29%** | +6.3% worse |
| median error | 8.18% | 8.49% | +3.8% worse |
| p75 error | 13.99% | 14.50% | +3.7% worse |
| p90 error | 19.86% | 20.78% | +4.7% worse |
| within 10% | 59.9% | 57.8% | −2.1pp |
| within 15% | 78.3% | 76.4% | −1.9pp |

**Adjusting improved the answer on 305 of 631 homes — 48.3%.** A coin flip, marginally against.

Consistent in all three suburbs, so it is not one market's quirk:

| suburb | n | mean unadj → adj | improved |
|---|---|---|---|
| Robina | 272 | 8.44% → 9.27% | 48.9% |
| Varsity Lakes | 205 | 11.44% → 11.64% | 51.2% |
| Burleigh Waters | 154 | 9.50% → 10.28% | 43.5% |

## What was compared

For each sold home, one backtest run (subject excluded by `_id`, every sale on/after its date
dropped), then two estimates from **the same comparables with the same weights**:

    unadjusted = Σ(raw sale price × weight) ÷ Σ(weight)
    adjusted   = Σ(adjusted price × weight) ÷ Σ(weight)

Only the per-feature adjustment differs. That is the cleanest possible isolation of the thing being
claimed for.

## Why this does not contradict the ~40% narrowing

It does not measure the same thing. `RESULT_dispersion_512.md` §3 measured **dispersion**: adjusted
comps agree with each other about 40% more tightly than raw ones (median 38.8%, narrows at all in
91.0%). That is **precision**. This measures **accuracy** — distance from the eventual sale price.

Adjusting pulls the comparables toward each other. It does not reliably pull them toward the truth.
A narrow range can be narrowly wrong, and on this evidence it slightly more often is.

## The other framing was already measured, and also failed

Will's wording — "than just using basic comparable metrics like approx. floor area, number of
bedrooms, and number of bathrooms" — describes a baseline that changes the comp **selection** as
well as the arithmetic. That contest was run on 2026-08-06 (`RESULT_dispersion_512.md` §1–2): every
possible 3-comp valuation drawn from a basic label-match, against the full Fields method. **A random
agent triple beats Fields exactly 50.0% of the time.** Also a dead heat.

So both readings of the question have now been measured and neither supports an accuracy claim.

## Caveats, stated so nobody re-runs this and thinks they have found something new

1. **The unadjusted arm is generous.** It inherits our comp *selection*, which already screens for
   similar land, floor area and recency. A cruder baseline would do worse — but §1–2 above tested
   exactly that cruder baseline and still found a draw.
2. **Sighted subject.** The backtest can see the subject's renovation level and condition, which we
   do not hold for an off-market home. If anything that flatters the adjusted arm, which makes the
   result stronger, not weaker.
3. **Weights are the engine's own**, so any weighting error is shared by both arms and cancels.

## What IS supported, and can be said

- **Adjusting narrows the range about 40%, and narrows it at all nine times in ten** (n=512).
  A precision claim, and a true one.
- **Determinacy.** The 3-comp method's answer depends on which three are picked: median spread
  between the best and worst defensible result is **32.9% of value ($469,000)**, over 20% on 77% of
  homes. One auditable answer versus a draw from that distribution is the real argument.
- **The measured error of the method itself** — 8.2% mean, half within 6.6% — which the page
  already states.

## What must never be said

- "Adjusting makes our valuations X% more accurate." Measured false, twice, by two designs.
- "More accurate than an agent appraisal." Dead heat (§1–2).
- "More accurate than a portal." Separately invalid — see `[DOMAIN-BENCHMARK-CONTAMINATED]`.

## The open question this raises

The per-feature adjustment layer is the centre of the page's argument and it is **not earning its
keep on accuracy**. Two possibilities worth separating: the adjustment *rates* are wrong (a
regression fit on 56 sales, with 4–7 rates falling back to defaults on most runs), or per-feature
adjustment of comparables cannot beat good selection at this sample size. The first is fixable and
testable; the second would be a finding about the method itself.
