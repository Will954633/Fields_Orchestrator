# 2026-08-08 — Where the 12pp of headroom actually is

**Origin:** the noise-floor measurement showed the band is ~5× wider than internal comparable
disagreement explains, leaving two candidate explanations — **missing subject attributes** or a
**comparable-selection defect**. Will: *"so we need to dig into this area then?"*

**Answer: comparable selection and data coverage. Not missing subject attributes.**

---

## The signature

Even after every fix shipped 2026-08-07, n = 577:

| | measured | a fair set |
|---|---|---|
| median percentile of the sale inside its own adjusted comp set | **88** | 50 |
| sold **above every** comparable | **42%** | ~12% |
| sold **below every** comparable | **13%** | ~12% |

**The floor is correctly calibrated. Only the ceiling is broken.** That asymmetry is the whole
finding — a noisy pool would fail at both ends.

## Splitting selection from adjustment

| | dearest **raw** comp vs sale | dearest **adjusted** comp vs sale |
|---|---|---|
| Burleigh Waters | +21.5% | +6.4% |
| Robina | +12.6% | +4.9% |
| Varsity Lakes | +0.7% | −5.0% |
| **all** | **+9.4%** | **+1.9%** |

| | sells above the dearest comp |
|---|---|
| **raw** pool | **24%** (fair ~12%) |
| **adjusted** pool | **42%** |

Two distinct defects, and both are real:

1. **The raw comparable pool is already collectively too low** — 24% against 12% expected, before we
   touch it. This is selection or data coverage.
2. **The adjustment roughly doubles it** — 24% → 42%.

## The adjustment's mechanism: asymmetric compression

Ranking each property's comparables by raw price within its own set:

| comp's price rank | median adjustment |
|---|---|
| cheapest fifth | **+6.1%** |
| 2nd fifth | +1.4% |
| middle | −0.9% |
| 4th fifth | −4.4% |
| **dearest fifth** | **−9.4%** |

15.5pp of net compression, and asymmetric: dear comps are pulled down **9.4%** while cheap ones are
lifted only **6.1%**. The whole pool drifts down — which is simultaneously the ceiling and the
systematic low bias tracked since the start of this investigation.

## ⚠ Two hypotheses tested and rejected

### 1. Over-scaled adjustments — NO

Shrinking the **total** adjustment toward the raw sale price (`adjusted' = price + λ(adjusted −
price)`):

| λ | MAE | within 10% | 80% band on $1.6M | sells above all comps |
|---|---|---|---|---|
| 0.00 (no adjustment) | 10.16% | 62% | $472,031 | 24% |
| 0.80 | 8.63% | 65% | $429,353 | 40% |
| **0.90** | **8.62%** | **67%** | **$425,692** | 42% |
| **1.00 (shipped)** | 8.76% | 66% | $437,755 | 42% |
| 1.25 | 9.62% | 61% | $480,187 | 43% |

**λ = 0.90 is marginally better than 1.00** — worth ~0.14pp of MAE and ~$12,000 of band — but the
adjustment is close to correctly scaled. It is not over-applied, so simple shrinkage is not the fix.
Note λ = 0 still leaves the ceiling at 24%: **shrinking cannot repair a pool that is already low.**

### 2. The subject looks average because we cannot see it — NO (⚠ but see the correction below)

The obvious explanation for pulling dear comps down was that a blind subject presents as unremarkable,
so superior comparables get adjusted down to meet it. Tested by running the same properties with the
subject **sighted** (photo-derived attributes restored):

| subject | sells above all comps | dear fifth adj | cheap fifth adj |
|---|---|---|---|
| blind (off-market) | 42% | −9.4% | +6.1% |
| **sighted (has photos)** | **43%** | −9.2% | +6.2% |

**Identical.** Seeing the subject changes nothing. This is now the **fourth** enrichment-flavoured
hypothesis to fail, and the strongest evidence yet that subject enrichment is not the lever.

## What this means

The headroom is **not** in knowing more about the subject. It is in the comparable pool being
collectively too cheap before any adjustment is applied — 24% against 12% expected — which is either:

- **which comparables we select** from an adequate pool, or
- **the pool itself** being biased low, consistent with `[[data_source_undercapture_reset]]`:
  Domain sold records miss 40–50% of transactions, and there is every reason to expect the missing
  ones skew to the top (off-market, pre-auction and premium sales are the least likely to be
  published).

**Varsity Lakes is the tell.** Its raw pool reaches only +0.7% above the eventual sale against
Burleigh Waters' +21.5%, and it carries by far the largest suburb offset (−11.8% against −1.9%).
That is what a coverage hole looks like, not a method flaw.

## The next test, and it is cheap

Distinguish selection from coverage:

1. **Selection** — for each subject, compare the 8 chosen comparables against every eligible sale in
   the suburb. If the chosen set is systematically cheaper than the available set, the selector is
   the problem and the fix is free.
2. **Coverage** — compare our sold price distribution against PropRadar's for the same period. If
   our recorded sales are collectively lower, the pool is the problem and no selector change fixes
   it. ⚠ PropRadar is volume-only per `[[propradar_api]]`, so check what price data is actually
   available before designing this.

Run (1) first. It needs no new data — the dumps already carry every comparable's price and weight,
and the eligible pool is reconstructable from the same sold collections.

⚠ **Do not run the 30-home enrichment experiment until this is settled.** Four subject-enrichment
hypotheses have now failed, and this evidence says the defect is upstream of the subject entirely.


---

# ⚠ CORRECTION (2026-08-08) — "missing subject attributes" was NOT properly rejected

This file concluded the missing-subject-attribute hypothesis was rejected. **Over-stated.**

The sighted-vs-blind test restored **three specific photo-derived attributes** —
`renovation_quality_score`, `kitchen_score`, `number_of_stories` — every one of which had *already*
measured as noise in the earlier ablation. Showing the subject three worthless attributes and finding
no improvement does not test whether attributes we hold **no data on at all** would help.

**Aspect, outlook, slope, frontage width and noise exposure remain untested**, and after
`2026-08-08-comparable-selection.md` they are the only surviving candidate: selection, adjustment
scaling and photo attributes all move the centre or the shape while leaving the **band width** at
13.7%.

The selection conclusion in this file stands and is strengthened — see the follow-up for the
mechanism (`calculate_weight` factor 2 scores comparables on their closeness to the cohort median,
i.e. selection on the dependent variable) and for what fixing it does and does not buy.
