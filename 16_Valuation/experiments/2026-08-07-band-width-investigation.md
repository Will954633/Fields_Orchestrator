<!-- APPEND-ONLY EXPERIMENT RECORD. Do not edit results below; supersede them with a new
     dated file and add a pointer here. -->

> **Moved into the valuation domain 2026-08-07.** Originally written under
> `15_Off-Market/Page_Redesign_V4/Product/11_BAND_WIDTH_INVESTIGATION.md` while the work was scoped
> to the off-market page redesign. It is a valuation-methodology record, so it lives here now.
>
> **Reproduce with:**
> ```
> python3 scripts/valuation_backtest.py --price-filter none --property-type House \
>   --min-price 1000000 --max-price 2000000 --suburb <suburb> --dump-errors /tmp/out.json
> ```
> **Sample:** 641 real sales (627 after attached dwellings were excluded), Robina + Varsity Lakes +
> Burleigh Waters, detached houses $1,000,000–$2,000,000.
>
> ⚠ **Parts 1–3 were run before the instrumentation was correct.** Part 4 documents what was wrong
> and which conclusions it invalidates. Read Part 4 before quoting anything from Parts 1–3.

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

---

# Part 2 — Attribute-level ablation (2026-08-07, same n = 641)

Instrumented `--dump-errors` to carry the **full per-comparable adjustment breakdown** (4,916
comparables, 19 attributes), so every hypothesis below is an offline re-computation rather than a
fresh backtest. All figures **de-biased first**, so they measure spread, not offset.

## Does adjusting beat not adjusting? — YES

| predictor | MAE | within 10% | 80% half-width |
|---|---|---|---|
| median of the same comps, **unadjusted** | 13.1% | 53% | ±20.4% |
| median of those comps, **adjusted** | **10.8%** | **59%** | **±18.4%** |
| **weighted mean** of adjusted (shipped) | 11.2% | 58% | ±18.3% |

Adjustment earns 2.3pp of MAE. **But the six-factor weighting scheme is slightly worse than an
unweighted median of the same comps.** It is not earning its keep.

## Do more comparables add variance? — NO, the opposite

Restricting to the best-weighted comps of the same pool makes it worse: best 3 → ±18.4%, best 5 →
±18.0%, best 6 → ±17.4%, **all 8 → ±16.9%**. "Fewer but higher quality" is tested and loses.

(Across properties, 8-comp cases run MAE 9.8% against 14.1% for 3–4 comps — but that is confounded:
unusual homes are *why* a pool is thin.)

## ⚠ Which attributes hurt — the subjective ones, all of them

Leave-one-out, MAE change when the adjustment is removed:

| removing this HELPS | gain | | removing this HURTS | cost |
|---|---|---|---|---|
| kitchen | −0.39pp | | land_size | +1.55pp |
| renovation | −0.26pp | | pool | +0.74pp |
| renovation_quality | −0.22pp | | street_premium | +0.73pp |
| stories | −0.07pp | | floor_area | +0.72pp |
| car_spaces | −0.06pp | | micro_location | +0.53pp |

## ⚠ And the adjustment RATES are miscalibrated in exactly the same direction

The multiplier on our dollar adjustment that would minimise error (1.0 = our rate is right):

| calibrated / under-adjusted | | over-adjusted or pure noise | |
|---|---|---|---|
| floor_area | **1.00** | micro_location | 0.75 |
| property_age | **1.00** | condition | 0.50 |
| land_size | 1.25 | renovation | 0.25 |
| pool | 1.25 | kitchen | **0.00** |
| street_premium | 1.50 | renovation_quality | **0.00** |

**The measurable facts are calibrated. Our own quality judgements are over-trusted — three of them
carry no signal at all.** Kitchen and renovation-quality scores are AI-derived from photos;
optimal weight zero means they are adding noise, not information.

## What this buys, stacked

| | MAE | within 10% | a flat ±12% covers | honest 80% band on $1.6M |
|---|---|---|---|---|
| as shipped | 10.83% | 59% | 66% | $588,000 |
| + per-suburb offsets | 10.12% | 61% | 68% | $528,000 |
| + drop kitchen/renovation/renovation_quality | 10.30% | 59% | 66% | $540,000 |
| **+ both** | **9.52%** | **64%** | **72%** | **$501,000** |

⚠ **Prefer the binary drop to the full rate recalibration.** Refitting all 19 multipliers gives
±15.5% against ±15.6% for the simple drop — no real gain, and those multipliers were fitted on the
same 641 sales, so they are in-sample. Dropping three attributes is a far smaller overfitting
surface for the same result.

## Still not tested

- **Are we missing variables?** No residual analysis against unused attributes has been run. This
  is the open question with the most headroom.
- **Why the top of the pool is still truncated.** Dropping the subjective adjustments moves
  "sells above dearest adjusted comp" from 45% to 39% — against 12% expected. Most of the
  compression is elsewhere.
- **The irreducible-noise ceiling** — leave-one-out within the comp set.

---

# Part 3 — Outliers, coverage gaps, and what is actually excludable (2026-08-07)

## ⚠ Two adjustments are dead code

Firing rate across 4,916 comparables:

| attribute | fires on | median $ when it fires |
|---|---|---|
| **beach_proximity** | **0 (0.0%)** | never |
| **golf_course_backing** | **0 (0.0%)** | never |
| water_views | 52 (1.1%) | $228,668 |
| micro_location | 4,830 (98.3%) | $56,934 |
| land_size | 4,817 (98.0%) | $12,544 |

Their earlier "no signal" ablation reading was meaningless — they never fire. And `water_views` is
worth a median **$228,668** on the 1.1% of comps where it does fire, far too rare for ablation to
detect. **We are not capturing proximity value at all.**

## Outliers dominate the headline number

| drop the worst… | remaining | MAE | 80% band on $1.6M |
|---|---|---|---|
| nothing | 641 | 10.5% | $524,000 |
| 5% | 609 | 9.0% | $481,000 |
| 10% | 577 | 8.0% | $430,000 |
| 15% | 545 | 7.3% | $383,000 |

**The worst 10% carry 31% of all absolute error**, and **49 of those 64 are homes we valued too
HIGH** — the opposite direction to the median error. Most homes come in slightly under; the big
misses overshoot.

## What the outliers have in common — mostly, not much

Tested and largely negative, which is itself the finding:

- **Land size.** Over-valued outliers sit on a median 530 m², under-valued on 676 m², at the same
  floor area — consistent with land being under-adjusted (multiplier 1.25). But across all 641,
  r = −0.125 and **every land quintile runs MAE 9–11%**. It does not explain them.
- **Missing data.** Homes missing 1 or 2 of {land, floor, beds, baths} are **no worse** than complete
  ones (MAE 10.2% vs 10.0%). Only the 23 missing 3–4 are bad (MAE 19–26%).
- **Small floor area.** Under 150 m²: MAE 9.5% against 10.4% for larger. No effect.
- **Listing text.** Only two themes appear more in the worst 15% than the rest: **canal/waterfront
  (11% vs 5%)** and **golf (7% vs 3%)** — precisely the two attributes above that never fire.

## Two defensible exclusions

- **Unit-numbered addresses** — 13 in the sample, MAE **18.0%** against 10.3%. Being valued by the
  detached-house method at all is the bug.
- **Homes missing 3+ of 4 core facts** — 23 homes, MAE 19–26%. We are guessing.

## Everything that survived testing, stacked

| | homes valued | MAE | within 10% | flat ±12% covers | honest 80% band on $1.6M |
|---|---|---|---|---|---|
| as shipped | 641 | 10.83% | 59% | 66% | $588,000 |
| + per-suburb offsets | 641 | 10.12% | 61% | 68% | $528,000 |
| + drop 3 subjective adjustments | 641 | 9.52% | 64% | 72% | $501,000 |
| **+ refuse units & 3+-missing** | **618 (96.4%)** | **9.12%** | **65%** | **72%** | **$479,000** |

⚠ **Exclusion is only honest if it applies to the product, not just the measurement.** Those 23
homes must get `directional_only` — exactly as `precompute_valuations.py` already does outside the
$1M–$2M envelope. Dropping them from the accuracy claim alone is marking our own homework.

## The open lead

Waterfront/canal and golf frontage are the one place where the outlier evidence, the firing-rate
evidence and the listing-text evidence all point the same way. `[[waterfront_out_of_scope]]` already
rules waterfront out of scope — so the question is whether these homes should be **detected and
refused** rather than valued badly. That would be the third exclusion, and on this sample it is
worth more than any remaining calibration work.

**Property-by-property list for manual review: [[12_OUTLIER_LIST]] (50 worst, with links).**

---

# Part 4 — CORRECTION: the proximity adjustments were never broken in production

**2026-08-07.** Part 3 reported `beach_proximity` and `golf_course_backing` as "dead code" firing on
0 of 4,916 comparables. **That was wrong, and it was my instrumentation at fault, not the pipeline.**

Production, measured over **11,921** adjusted comparables in `valuation_data.adjusted_comparables`:

| attribute | backtest (before) | **production** | median $ when it fires |
|---|---|---|---|
| beach_proximity | 0.0% | **99.1%** | $13,840 |
| golf_course_backing | 0.0% | **2.9%** | **$207,000** |
| renovation_quality | 79.9% | **0.2%** | $16,200 |

`valuation_backtest.py` builds its **own** `comp_features`/`subject_features` dicts rather than
reusing the production builders, and those dicts omitted `beach_distance_km` and
`golf_course_backing` entirely — so `calculate_adjustments()` took the `skipped` branch every time.

⚠ **This also invalidates part of the Part 2 ablation.** `renovation_quality` fired on 79.9% of
backtest comparables against **0.2%** in production. The finding that it "carries no signal" was
measured on a field production barely uses. `kitchen` (63% vs 83%) and `street_premium` (30% vs 19%)
also diverged. **Any backtest conclusion about an attribute is only valid if that attribute's firing
rate matches production — check it first.**

## Fixed

`valuation_backtest.py` now mirrors production: it imports `resolve_beach_distance` and
`detect_golf_course_backing`, resolves beach distance onto each comparable's basic features, and
passes both keys through to `calculate_adjustments`. Firing rates after the fix:

| attribute | backtest now | production | agreement |
|---|---|---|---|
| beach_proximity | 99.0% | 99.1% | ✓ |
| golf_course_backing | 2.2% | 2.9% | ✓ |
| water_views | 1.1% | 0.8% | ✓ |
| micro_location | 98.2% | 97.8% | ✓ |
| land_size | 98.8% | 98.4% | ✓ |
| floor_area | 99.8% | 99.6% | ✓ |

## Their independent contribution, now measurable

A 2%-firing adjustment is invisible in a full-sample average, so each is also measured **scoped to
the homes it actually touches**:

| attribute | homes it touches | MAE with | MAE without | verdict | best multiplier |
|---|---|---|---|---|---|
| **beach_proximity** | 626 | 10.48% | 10.70% | **earns its keep** | **1.50 — we under-adjust** |
| **water_views** | 24 | **9.79%** | 10.92% | **strongest of any attribute** | 1.00 — calibrated |
| street_premium | 367 | 10.42% | 11.67% | earns its keep | 1.25 |
| **golf_course_backing** | 46 | 10.99% | **10.76%** | **hurts on the homes it touches** | **0.00** |

**Beach proximity is real and under-powered** — it fires on 99% of comparables and the optimal
multiplier is 1.5×. **Water views are the single most valuable adjustment we have** on the 24 homes
they touch (+1.13pp), perfectly calibrated, and firing on only 1.1%.

⚠ **Golf is the awkward one, and n = 46.** The adjustment is enormous ($190,800 median, $288,000
max) and on the homes it touches, removing it *improves* MAE by 0.23pp. But it does move the centre
the right way — signed error +2.0% with it against +4.0% without. So it is correcting bias while
adding variance, on a sample too small to be confident about. **Do not act on the 0.00 multiplier
yet** — 46 homes is not enough to retire a $190K adjustment. It needs a bigger sample, and the
detector (5.9% of properties with satellite analysis, `high` confidence, on real golf streets —
Merion Court, Legend Trail, Oakmont Street) is clearly working.

## Attached dwellings now excluded by default

`is_attached_dwelling()` catches units, townhouses, villas, duplexes via `property_type`,
`is_strata_title`, a cadastral `UNIT_NUMBER`, or a unit-numbered address. **`--property-type House`
alone did not exclude them** — 14 survived it across the three suburbs and ran MAE 18.0% against
10.3%. Exclusion is on by default (`--include-attached` to override) and every exclusion is printed
with its reason rather than dropped silently.

## Where this leaves the numbers

| | MAE | within 10% | flat ±12% covers | honest 80% band on $1.6M |
|---|---|---|---|---|
| attached excluded, proximity wired | 10.47% | 59% | 67% | $572,000 |
| + per-suburb offsets | 9.78% | 60% | 69% | $504,000 |
| **+ drop 3 subjective adjustments** | **9.23%** | **63%** | **72%** | **$483,000** |
| + rate recalibration on top | 9.35% | 62% | 71% | $481,000 |

Rate recalibration adds nothing beyond the simple drop — same conclusion as Part 2, now on
corrected instrumentation. **$603,574 → $483,264 on 627 detached houses.**

---

# Part 5 — Water views are being valued as waterfront (2026-08-07)

**Will's observation from reviewing the outlier list: they had water views but were not waterfront.**
That is exactly what is happening, and it is the largest single defect found in this investigation.

## The mechanism — one flag, two jobs, opposite error costs

`shared/waterfront.py::detect_waterfront()` is deliberately **broad**, because it drives a
**suppression gate**: skip editorial, `noindex`, withhold the valuation. There a false positive is
cheap — we simply stay quiet about a dry home. That design is correct and should not change.

But `precompute_valuations.py` reads the **same flag** to pick the **comparable cohort** (lines
3014–3016: a waterfront subject is compared only to waterfront comps). There a false positive is
expensive — a lake-*view* home gets pooled against genuine water-frontage sales, which sell far
higher.

**Signal 1 of that detector is `property_valuation_data.outdoor.water_views`** — a GPT-4 Vision read
of the marketing photos. It answers *"can you see water from here?"*, not *"does this parcel touch
water?"*

## Measured, n = 625 detached houses

| group | n | median error | MAE | over-valued |
|---|---|---|---|---|
| flagged waterfront | 59 | **+8.0%** | **13.5%** | **73%** |
| not flagged | 566 | −0.6% | 9.4% | 48% |

Splitting the flagged group by **geometry** instead of photographs:

| | n | median error | MAE | over-valued |
|---|---|---|---|---|
| genuinely waterfront | 18 | +1.6% | 10.2% | 61% |
| **MISCLASSIFIED — 69% of the flagged group** | **41** | **+10.4%** | **14.9%** | **78%** |

**The method handles real waterfront acceptably. It is the false positives that break it.**

## The worked example — 24 Brooklyn Crescent, Robina

Its own OSM record already said it was not waterfront:

```
distance_to_water_m          21.5
waterfront_type              "none"
canal_frontage               False
waterfront_premium_eligible  False
satellite backs_onto         ["residential_only"]
photo outdoor.water_views    True     <- the only positive signal
is_waterfront                True     <- set anyway
```

We had the correct measurement and overrode it with a photograph. Then valued the home **56% high**.

## The methodology — geometry decides frontage, photographs decide views

`shared/waterfront.py::classify_water_relationship(doc)` → `waterfront | water_view | dry`, built
2026-08-07 from fields **we already compute per property**:

1. OSM `water_features`: `canal_frontage`, `waterfront_premium_eligible`, `waterfront_type`
2. Satellite structured adjacency: `backs_onto` naming a water body
3. `distance_to_water_m <= 5` — a parcel effectively touching water

Only then do photographs get a say, and only to mark the **view** class. Re-classified, all three
cohorts behave:

| class | n | median error | MAE |
|---|---|---|---|
| waterfront | 18 | +1.6% | 10.2% |
| water_view | 157 | +1.4% | 10.0% |
| dry | 450 | −0.4% | 9.6% |

**Do not change `detect_waterfront()`** — the suppression gate should stay broad. Change only the
**cohort selector** in `precompute_valuations.py` to use the new classifier, and give `water_view`
its own cohort rather than folding it into either extreme.

## ⚠ The blocker

**332 of 625 homes (53%) have no OSM `water_features` block at all.** Where geometry is absent the
classifier falls back to the photo signal and returns `reason='photo_view_no_geometry'`. That is
provisional, not evidence of dryness. **Backfilling the OSM water pass across the sold and
off-market stock is the prerequisite** — the classifier is only as good as its coverage, and at 53%
missing it cannot yet be trusted as the sole cohort authority.

---

# Part 6 — Attached homes with a house address

`--property-type House` and unit-number checks both missed **24 Brooklyn Crescent, Robina**: freehold
tenure, no unit number, `property_type "House"`, `is_strata_title False`. It is a townhouse in a row.

Two signals now catch it:

**1. QLD plan type.** `GTP` / `BUP` / `CTS` / `SUP` prefixes are community or building-units title —
attached by definition. Across 990 sold "Houses": 19 GTP, 8 BUP. `RP` (533) and `SP` (328) are
freehold and prove nothing either way, so plan type alone is not sufficient.

**2. Floor-to-land ratio.** A detached house needs setbacks, a driveway and some yard, so it cannot
approach 1.0. 24 Brooklyn Crescent is 131 m² of land to 122.4 m² of floor — **0.93** — on a
cadastral parcel measuring 5 m × 26 m. Across 833 sold houses with both figures, p50 is 0.32 and p90
is 0.60, so **0.70** leaves clear air. Above it sit obvious townhouse rows (36 and 38 Evergreen View,
adjacent; 1 and 55 Tours Way) **and** genuine data errors (7 Nypa Close at 495 m² floor on 495 m² of
land) — both classes should be out of a detached-house valuation, so the rule earning double duty is
a feature.

Effect on the backtest: 39 homes excluded, MAE 9.78% → 9.58%, 80% band $504,247 → $485,508. Modest
on accuracy, but these homes should never have been valued as detached houses at all.

Both live in `is_attached_dwelling()` in `valuation_backtest.py`, on by default, each exclusion
printed with its reason.
