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

## ⚠ The blocker before this can be the cohort authority

**332 of 625 homes (53%) have no OSM `water_features` block at all.** Where geometry is absent the
classifier falls back to the photo signal and returns `reason='photo_view_no_geometry'`.

**That is provisional, not evidence of dryness.** Backfilling the OSM water pass across sold and
off-market stock is a prerequisite — a geometry-first classifier with 53% missing geometry is a
photo classifier wearing a better name.

## Which function to call

| you are… | call |
|---|---|
| deciding whether to publish/index/generate editorial | `detect_waterfront()` — stays broad |
| choosing a comparable cohort | `classify_water_relationship()` |

A home can legitimately be `water_view` for cohort purposes and still be suppressed for publishing.
The two answer different questions and should be allowed to disagree.

Source: `experiments/2026-08-07-band-width-investigation.md` Part 5.
