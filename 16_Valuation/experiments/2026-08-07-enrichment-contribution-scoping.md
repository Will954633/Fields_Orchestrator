# 2026-08-07 — What enrichment is worth: scoping before the forced-enrichment experiment

**Origin:** Will, 2026-08-07 — *"we might need to do an experiment where we run full attribution,
including photo analysis and any other similar process off market homes need to give rich data on a
small batch of homes, say 30 homes where we force full analysis of all comparable homes and see if
our error rate drops and see how much of a contribution each attribute makes in isolation."*

**Status:** scoping done, experiment NOT yet run. The scoping changed what the experiment should be.

---

## What an off-market home actually has

| field | off-market (25,330) | sold (1,568) | for_sale (207) |
|---|---|---|---|
| `property_valuation_data` (photo AI) | 41.9% | 76.1% | 99.5% |
| **`satellite_analysis`** | **2.5%** | 36.0% | **100%** |
| `domain_image_urls` | **57.2%** | 57.3% | 44.0% |
| `cadastral_photos_count` | 57.1% | 57.2% | 44.0% |
| `floor_plans` | 0.4% | 70.7% | 82.6% |
| `parsed_rooms` | 0.3% | 59.7% | 79.7% |
| `osm_location_features` | 98.8% | 70.5% | 67.6% |

**57% of off-market homes already have image URLs.** They are not un-analysable — they are
un-analysed. And satellite analysis needs no listing at all, yet sits at 2.5% against 100% for-sale.

## The natural experiment, run first

36% of sold homes already have satellite analysis and 64% do not, so the contribution can be measured
without enriching anything. n = 588, per-suburb de-biased:

| enrichment | n | MAE | within 10% |
|---|---|---|---|
| **satellite_analysis — yes** | 179 | **9.09%** | 63% |
| **satellite_analysis — no** | 409 | **9.20%** | 64% |
| floor_plans — yes | 491 | 8.59% | 65% |
| floor_plans — no | 97 | 12.10% | 59% |
| parsed_rooms — yes | 446 | 8.40% | 65% |
| parsed_rooms — no | 142 | 11.57% | 60% |

**⚠ Satellite analysis, as currently used, contributes nothing measurable** (9.09% against 9.20%).
It is worth having for adjacency (`backs_onto` feeds waterfront and golf detection) but it is not an
accuracy lever, and enriching 30 homes with it would not move the number.

Floor plans and parsed rooms look powerful — but they are confounded with knowing the floor area.

## Controlling for floor area

| group | n | MAE | within 10% |
|---|---|---|---|
| floor area known, **has floor plan** | 481 | **8.44%** | 65% |
| floor area known, **no floor plan** | 88 | **12.03%** | 59% |
| floor area unknown | 19 | 14.41% | 47% |

The floor-plan effect **survives** the control — 8.44% against 12.03% with the number known either
way. So it is not merely *having* a floor area. It is **which** floor area.

## ⚠ The finding — subject and comparables are measured on different rulers

`resolve_floor_area()`'s own docstring says it exists so that *"the SUBJECT and its COHORT use the
same metric (mixing internal-living with internal+garage invalidates premium math)"*, and it treats
Domain's `total_floor_area` as a **last resort** because it is internal + garage + sometimes patio.

Measured across 438 properties carrying both fields, the two disagree by a **median −17.8%**, with
**78% differing by more than 10%** and **52% by more than 25%**.

And the cohorts resolve differently:

| cohort | internal-living source | **`building_fallback`** (internal + garage) |
|---|---|---|
| **off-market — the subject** | 47.9% `legacy_floor_area` | **1.7%** |
| **sold — its comparables** | 13.5% | **41.6%** |
| for_sale | ~42% combined | 42.0% |

**So for roughly 40% of comparisons we measure an off-market home's internal living area against a
comparable's internal-plus-garage.** On the single largest adjustment in the method — removing
`floor_area` costs +0.72 to +0.86pp of MAE — and the code already warns this invalidates the premium
maths.

**Also: 48.7% of off-market homes resolve to NO floor area at all.**

## What the experiment should therefore be

The original design — force full photo + satellite enrichment on 30 homes — would have measured the
wrong thing, because satellite contributes nothing measurable and photo-derived quality attributes
already measured as **noise** (blinding the subject to them *improved* MAE, 10.22% → 9.93%).

Revised, in priority order:

1. **Fix the ruler before adding data.** Quantify the error caused purely by metric mismatch:
   re-run the backtest forcing subject and comparables onto the same floor-area source, and compare.
   This costs no enrichment at all and is likely the largest single win available.
2. **Then** the 30-home forced-enrichment run — but targeted at **floor area**, not photo quality
   scores: derive an internal-living area for off-market homes from the 57% that have image URLs,
   and from cadastral footprint minus a garage allowance for the rest.
3. **Measure each attribute in isolation** as already instrumented — `--dump-errors` carries the full
   per-comparable adjustment breakdown, so ablation needs no new runs.

⚠ Any vision work goes through **Gemini via Vertex** (`VISION_BACKEND=gemini_vertex`), per
`shared/claude_vision.py` — the Claude Max CLI is text-only.

## Open question this raises

If `total_floor_area` (internal + garage) is what 42% of listed comparables resolve to, and
off-market subjects almost never have it, then **the comparables pool itself is internally
inconsistent** — some comps measured one way, some the other, inside the same valuation. That should
be measured before deciding which ruler to standardise on.


---

# ⚠ CORRECTION (2026-08-07, same day) — the ruler mismatch does NOT cause the error

Everything above about subject and comparables being measured on different rulers is **factually
true and materially irrelevant**. It was written as "the largest known remaining defect" **before it
was tested**. It was then tested, and it failed.

## The test

Instrumented `--dump-errors` to record the floor-area source of the subject **and of every
comparable**, then measured error against the share of comparables sitting on a different ruler.
n = 581 off-market (blind) subjects.

**The mismatch is extremely prevalent — a median 62% of comparables sit on a different ruler than
their subject.** And it does not predict error:

| comparables on a different ruler | n | MAE | median error |
|---|---|---|---|
| 0–25% (mostly matched) | 34 | 7.76% | −0.8% |
| 25–50% | 143 | 7.86% | −0.6% |
| 50–75% | 174 | 9.29% | −0.8% |
| 75–100% (mostly mismatched) | 230 | 9.07% | +1.4% |

**r = +0.027** against absolute error, **r = +0.069** signed. Non-monotonic across the middle bands.

Error by the subject's own source shows the same absence of effect — `building_fallback` 8.5% MAE,
`legacy_floor_area` 9.1%, `stated_plan_label` 9.5%, **all with median error ≈ 0**. If a systematic
17–22% metric difference were flowing into the estimate, it would appear as a bias here. It does not.

## Why it does not matter

The adjustment **rates** are regressed from the same mixed pool the comparables come from. The model
learns a dollars-per-m² on a blended metric and applies it consistently, so the unit error largely
cancels rather than propagating. The docstring's warning is about mixing metrics *within a single
comparison*; in practice the regression absorbs it.

The weak 7.76% → 9.07% gradient is confounded: properties whose ruler matches their comparables are
better-documented properties generally, and better documentation is what actually predicts accuracy.

## What this means for the enrichment experiment

**Do not spend the 30-home enrichment run on floor-area harmonisation.** Two hypotheses have now
been tested and both came back negative:

| hypothesis | result |
|---|---|
| satellite analysis lifts accuracy | **no** — 9.09% with vs 9.20% without |
| ruler mismatch causes error | **no** — r = +0.027 |
| photo-derived quality attributes help | **no** — blinding the subject *improved* MAE |

Three separate enrichment hypotheses, all negative. The consistent signal across every test in this
domain remains: **more measured facts about the property help (land size, floor area, location);
more AI judgement about the property does not.**

⚠ **The open question is now whether enrichment is the right lever at all.** Before commissioning a
forced-enrichment run, the cheaper test is the one still not done: **leave-one-out inside the comp
set** — how well the weighted mean of seven adjusted comparables predicts the eighth. That measures
the method's irreducible noise floor. If it lands near the current ±13.7%, no amount of enrichment
will narrow the band, and the remaining work is presentational rather than computational.

---

# The noise floor — measured, and it says there IS headroom

The question left open all day: **how narrow could this method ever be?** Answered by leave-one-out
*inside* the comparable set. Every adjusted comparable is an independent estimate of the same
subject's value, so their disagreement with each other is the method's own precision, with no
reference to the eventual sale price at all.

**4,549 leave-one-out predictions across 581 properties:**

| | |
|---|---|
| median disagreement between our own comparables | **4.01%** |
| mean disagreement | 5.13% |
| 80% of comparables agree within | **±8.3%** |
| averaging ~8 of them should therefore give (÷√n) | **±3.0%** |
| **what the method actually delivers** | **±15.6%** |

## ⚠ The method is PRECISE but not ACCURATE

The band is roughly **five times wider than internal comparable disagreement explains**. Our
comparables agree closely with one another and are then **collectively displaced** from the eventual
sale price.

That distinction matters more than any individual finding in this file:

- If the comparables disagreed wildly and averaged out to the right answer, the fix would be **more
  comparables** or **better weighting**. Tested — more comps helps slightly, weighting is worse than
  a plain median.
- They do the opposite. They **agree with each other and are wrong together.** Random noise cancels
  under averaging; this does not, so it is not noise. It is a systematic, per-property displacement.

## What can displace an entire comparable set at once

Only something about the **subject** that the comparables do not share and we do not measure. Three
candidates, none yet tested:

1. **Property-specific attributes we capture for nobody** — aspect, outlook, slope, street frontage
   width, noise exposure, renovation recency, view quality. `beach_proximity` and
   `golf_course_backing` were of this class and one of them (proximity) earned its keep.
2. **Comparable SELECTION rather than adjustment** — if the eight chosen comps are collectively
   unrepresentative of the subject, every one of them is displaced the same way and they will still
   agree beautifully with each other. This has never been tested directly.
3. **Sale-specific circumstance** — auction vs private treaty, campaign length, motivated vendor.
   Irreducible from our data, and part of the floor.

## What this changes about the enrichment experiment

It **supports** running it — with a correction to the conclusion drawn earlier in this file.

"More AI judgement does not help" holds for the three attributes tested (kitchen, renovation
quality, satellite adjacency). It does **not** follow that no further data can help, because there is
a measured **~12 percentage points** between what averaging should deliver (±3.0%) and what we get
(±15.6%), and it has to come from somewhere property-specific.

**Revised design for the 30-home run:**

- Choose the 30 homes from the **worst-error** tail, not at random — they are where the displacement
  lives, and the worst 10% carry 31% of all absolute error.
- For each, capture what a valuer would notice and we do not: aspect, outlook, slope, frontage,
  noise, condition relative to street.
- Test whether any of it predicts the **signed** residual. A displacement that a human can see and we
  cannot is the whole hypothesis.
- ⚠ Vision through **Gemini via Vertex** (`VISION_BACKEND=gemini_vertex`).

⚠ **Test comparable selection at the same time.** It is free — the dumps already carry every
comparable's price, adjustment breakdown and weight. If the chosen set is collectively displaced,
that is a selection defect, and no amount of enrichment of the *subject* will fix it.
