# 04 — Water relationship and comparable cohorts

**Last verified 2026-08-07.**

---

## The principle

**Geometry decides frontage. Photographs decide views.**

A photograph can tell you a home has a water outlook. It cannot tell you whether the parcel touches
water. Those are different homes at different prices, and conflating them is the single largest
source of over-valuation we have measured.

## The defect this replaces

`shared/waterfront.py::detect_waterfront()` is deliberately **broad** because it drives a
**suppression gate** — skip editorial, `noindex`, withhold the valuation. There a false positive is
cheap: we stay quiet about a dry home. **That design is correct and must not change.**

But `precompute_valuations.py` read the **same flag** to choose the comparable cohort, where a
waterfront subject is compared only to waterfront comps. There a false positive is expensive: a
lake-*view* home gets pooled against genuine water-frontage sales, which sell far higher.

Signal 1 of that detector is `property_valuation_data.outdoor.water_views` — a GPT-4 Vision read of
the **marketing photographs**.

### Measured, n = 625 detached houses

| group | n | median error | MAE | over-valued |
|---|---|---|---|---|
| flagged waterfront | 59 | **+8.0%** | 13.5% | 73% |
| not flagged | 566 | −0.6% | 9.4% | 48% |

Split by geometry rather than photographs:

| | n | median error | MAE | over-valued |
|---|---|---|---|---|
| genuinely waterfront | 18 | +1.6% | 10.2% | 61% |
| **misclassified — 69% of the flagged group** | **41** | **+10.4%** | **14.9%** | **78%** |

**The method handles genuine waterfront acceptably. The false positives are what break it.**

### The worked example — 24 Brooklyn Crescent, Robina

Its own OSM record already held the right answer:

```
distance_to_water_m          21.5
waterfront_type              "none"
canal_frontage               False
waterfront_premium_eligible  False
satellite backs_onto         ["residential_only"]
photo outdoor.water_views    True      <- the only positive signal
is_waterfront                True      <- set anyway
```

We had the measurement, overrode it with a photograph, and valued the home **56% high**.

## The classifier

`shared/waterfront.py::classify_water_relationship(doc)` → `waterfront | water_view | dry`, with a
reason string. Frontage is decided in this order, all from fields we already compute:

1. OSM `water_features`: `canal_frontage`, `waterfront_premium_eligible`, `waterfront_type`
2. Satellite structured adjacency: `backs_onto` naming a water body
3. `distance_to_water_m <= 5` — a parcel effectively touching water

Only then do photographs get a say, and only to mark the **view** class.

Re-classified, all three cohorts behave:

| class | n | median error | MAE |
|---|---|---|---|
| waterfront | 18 | +1.6% | 10.2% |
| water_view | 157 | +1.4% | 10.0% |
| dry | 450 | −0.4% | 9.6% |

## ✅ The blocker is closed (2026-08-07, same day)

The classifier could not originally be trusted, because **53% of homes had no OSM `water_features`
block** — a geometry-first classifier with no geometry is a photo classifier wearing a better name.

`scripts/backfill_osm_water_features.py` closed it: **coverage 53% → 100%**, 23,748 properties, 0
failures. Homes falling back to the photo signal dropped from **332 of 625 to 2 of 586**.

`classify_water_relationship()` is now wired into `in_cohort()` in `precompute_valuations.py` and is
the cohort authority. Full record: `experiments/2026-08-07-water-geometry-backfill.md`.

### The threshold is measured, not assumed

30 m was first chosen by analogy to the river rule, then tested against 807 sold houses — median
price per m² of floor area against distance to water:

| 10–20 m | 20–30 m | **30–50 m** | 50–200 m | 400 m+ |
|---|---|---|---|---|
| **+13.6%** | **+12.4%** | **−9.0%** | ~+1% | — |

**The premium is ~+13% inside 30 m and gone beyond it.**

### Only waterfront is separated

`water_view` and `dry` are **pooled**, not split. They measured statistically indistinguishable
(median error −0.0% against −0.2%), the price data above shows no premium beyond 30 m, and splitting
them would thin every pool for no accuracy gain.

### ⚠ `lakefront` did not previously exist

The original `extract_water_features()` set `waterfront_type` for canal, coastline and river only —
a home **on a lake** scored `'none'`. Two of our three suburbs are lake suburbs. **1,817 properties
(7.7%) are lakefront**, previously undetectable. `9 Laura Place, Varsity Lakes` — the worst outlier
in the investigation at +87% — is one, and now correctly returns no figure instead of a wrong one.

### ⚠ Watch the waterfront cohort size

| suburb | waterfront | water_view | dry |
|---|---|---|---|
| Robina | 34 | 127 | 232 |
| Varsity Lakes | **18** | 82 | 176 |
| Burleigh Waters | 32 | 124 | 166 |

Varsity Lakes has 18 waterfront comparables. Genuinely waterfront homes there will often fail the
minimum-comps test and return nothing. That is intended while waterfront is out of scope — but if
the refusal rate turns out to be material, the answer is a waterfront arm of the business, not a
looser cohort.

## Which function to call

| you are… | call |
|---|---|
| deciding whether to publish/index/generate editorial | `detect_waterfront()` — stays broad |
| choosing a comparable cohort | `classify_water_relationship()` |

A home can legitimately be `water_view` for cohort purposes and still be suppressed for publishing.
The two answer different questions and should be allowed to disagree.

Source: `experiments/2026-08-07-band-width-investigation.md` Part 5.
