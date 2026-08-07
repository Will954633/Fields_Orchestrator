# 11 — Why the band is $600,000 wide, and what would actually narrow it

**Investigated 2026-08-07** against the question: *"we should be able to do better than a 600k band
width between high and low valuation guide."*

**Method:** `scripts/valuation_backtest.py --price-filter none --property-type House
--min-price 1000000 --max-price 2000000`, run per suburb. **n = 641** real sales inside the design
envelope. `--price-filter none` is mandatory — the default anchor prunes comparables using the
subject's own sale price, which is target leakage.

---

## The headline, stated plainly

**$600,000 is not a defect in the band. It is the honest 80% band for this method today.**

The shipped ±12% is not a narrower band — it is the same uncertainty with a smaller number printed
on it. On a $1.6M home ±12% is a $384,000 band, and it contains the eventual sale **58%** of the
time. Nothing found in this investigation narrows the honest band below **~$580,000**.

| what we print | band on $1.6M | how often it contains the sale |
|---|---|---|
| ±12%, as shipped | $384,000 | **58%** |
| ±18.9% | $604,000 | 80% |
| ±16.4% (after per-suburb de-bias) | $524,000 | 80% |

The choice in front of us is **coverage, not width**. Any width can be printed; only one of them is
true.

---

## Where the error comes from — measured stage by stage

Median gap against the eventual sale price, tracked through the pipeline:

| suburb | n | raw comps | after adjustment | final estimate |
|---|---|---|---|---|
| Robina | 279 | −0.6% | −2.7% | −2.8% |
| Varsity Lakes | 207 | −11.2% | −11.5% | −11.9% |
| Burleigh Waters | 155 | — | — | −5.1% |
| **all** | **641** | **−5.3%** | **−6.0%** | **−6.4%** |

The comparable **pool already sits 5.3% below** the eventual sale before we touch it. Adjustment
adds −0.7pp, weighting −0.4pp. **The arithmetic is not the problem.** Roughly five-sixths of the
bias is in what goes into the pool, not what we do to it.

## ⚠ The finding that matters most — the adjustment step truncates the top

A fair comparable pool would see a home sell above its dearest comparable about 1-in-(n+1) times,
~12% with seven comps. Measured:

| suburb | sells above dearest **raw** comp | above dearest **adjusted** comp | expected |
|---|---|---|---|
| Burleigh Waters | 9% | **40%** | 11% |
| Robina | 15% | **32%** | 12% |
| Varsity Lakes | **45%** | **67%** | 12% |
| **all** | **23%** | **45%** | **12%** |

**The raw pool is roughly fair in Burleigh Waters and Robina. The adjustment step is what breaks
it** — it pulls the top of the pool down a median **6.1%** (Burleigh Waters −11.2%), from +11.1%
above the eventual sale to +1.4%. The sale then lands at the **91st percentile** of its own adjusted
pool, where a fair pool would put it at 50.

This is the same operation we have been describing as a virtue. `[[adjusted_comparables_evidence]]`
markets it as *"raw comps span $610K, adjusted $274K — 55% narrower"*. That narrowing is real, and
it is **also** what makes the estimate systematically low. **A weighted mean cannot exceed its
priciest input**, so once the top is pulled down the estimate cannot recover.

Varsity Lakes is a second, separate defect stacked on the first: even its **raw** pool is truncated
(45% of homes sell above the dearest raw comp). That one is data coverage, consistent with
`[[data_source_undercapture_reset]]` — Domain sold records miss 40–50%.

## A contributing cause, not the whole story

**Time adjustment is applied to 2.0% of 30,024 comparables.** The other 98% are skipped with
"insufficient median data". Correlation between implied time-drift and measured bias is r=+0.983,
but comps are recent (2.8–4.0 months median), so this accounts for only about a third of the offset.

---

## Three things that were tested and did NOT work

Recording these so they are not re-tried.

**1. Adaptive band width — LOSES.** Scaling the band by per-property comp dispersion (`adj_cv`,
distance, comp count) gives an average half-width of **17.0%** against a flat **16.4%**. The signals
are real but weak (best is `adj_cv`, r=+0.248 against absolute error) and pooling beats
stratification. It only separates a genuinely bad third (±21.2%) from the rest (~±15%) — which is
useful as a *warning*, not as a width.

**2. Blending toward the raw-pool median.** 50/50 blend: median error −5.3%, 80% band ±18.2%.
Marginal.

**3. Flat de-bias.** +6.2% correction: median error −0.3%, 80% band ±18.4%. **Fixes the centre and
leaves the width alone** — which is the general shape of this whole problem.

## What genuinely helps, in order

1. **Per-suburb offsets** — the offsets differ enough to matter (Robina −2.8%, Burleigh Waters
   −5.1%, Varsity Lakes −11.9%). Applying each suburb its own correction takes the 80% band from
   ±18.9% to **±16.4%** ($604k → $524k) and lifts a flat ±12%'s coverage from 58% to **68%**. This
   is mechanical, cheap, and the largest single win available.
2. **Investigate the adjustment compression** — the 6.1% top-pull is the only finding here with the
   potential to reduce *variance* rather than shift the centre. Untested.
3. **Time adjustment on 98% of comps** — worth roughly a third of the residual offset.

## The unfinished question

None of the above establishes **how narrow this method could ever be**. The next test is a
leave-one-out inside the comp set: how well does the weighted mean of seven adjusted comps predict
the eighth? That is the method's internal consistency and an upper bound on achievable accuracy. If
it comes back near ±15%, the band is irreducible noise — two genuinely similar houses sell for
different prices — and the honest move is to change how the range is *presented*, not computed.

See [[valuation_design_envelope]], [[valuation_backtest_claim_constraints]],
[[adjusted_comparables_evidence]], [[data_source_undercapture_reset]].
