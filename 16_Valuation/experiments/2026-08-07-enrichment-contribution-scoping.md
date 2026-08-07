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
