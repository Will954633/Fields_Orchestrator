# Sweep — every house-only filter in the estate

**Date:** 2026-08-13 · Prompted by finding the third instance in one project.

Three times during the units work a `property_type: "House"` filter turned out to be
hiding a capability we already had, rather than describing a real constraint. Rather than
keep finding them one at a time, this is the full sweep with each hit classified.

**Method:** grep for `property_type: "House"`, `classified_property_type: "House"`,
`$in: [...House...]`, `NON_HOUSE_TYPES`, `HOUSE_TYPES` across Python and the website, then
read each site to decide what the filter is actually doing.

## The classification

| | Meaning |
|---|---|
| ✅ **Correct** | The thing genuinely is a house product. The filter describes reality. |
| ⚠ **Hides capability** | Units could be served; the filter is the only reason they are not. |
| 🔴 **Actively wrong** | The code RUNS on units and produces a house-derived answer for them. |

🔴 is the dangerous class: nothing looks broken, and the output is confidently incorrect.

---

## 🔴 Actively wrong — runs on units, answers with houses

| Site | What happens |
|---|---|
| `scripts/enrich_cadastral.py:298` | ✅ **FIXED 2026-08-13** — gated on `classify_dwelling == "house"`. It looped over ALL off-market stock (1,798 attached) while looking up `suburb_stats` house-only, writing house bedroom distributions and lot percentiles onto units. Inert at the time only because those units had no bedrooms — and the bedroom backfill the same day had begun filling exactly that field. |
| `calculate_property_insights.py` | ✅ **FIXED 2026-08-13** — see below; the defect was bigger than the type filter. |
| `scripts/step117_satellite_analysis.py` | ✅ **FIXED 2026-08-13** — `_is_house()` gate. **477 attached dwellings already carried a house-shaped analysis** (a level-23 apartment recorded with `usable_yard: "minimal"`). Existing records left in place deliberately: for a duplex on its own lot the analysis is legitimate, and separating those needs a per-field pass the gate makes safe to postpone. |

### The insights defect was not really about types

Chasing the type filter in `calculate_property_insights.py` surfaced something larger. Its
comparison pool was `{"price": {"$exists": true}}` with **no `listing_status` filter at
all** — **66.4% of the "currently for sale" pool was not for sale** (50.6% sold, 8.9%
withdrawn, 5.7% under contract). Fixed to a for-sale, type-matched cohort with a
`MIN_RANK_COHORT` guard. **49 of 260 homes gained a true claim; 0 lost one.**

And chasing the last stray lot claim surfaced a bug in the shared classifier itself:
`classify_dwelling` returned `"attached"` for **Land, Industrial, Development Site,
Leisure and Farm** — directly beside a comment saying those are "neither a house nor an
attached dwelling we track". 88 non-dwellings were in the attached bucket. Now
`non_dwelling`.

**All three 🔴 items are now closed.**

---

## ⚠ Hides capability — units could be served

| Site | Status |
|---|---|
| `scripts/render_property_aerial.py` · `scripts/batch_render_aerials.py` | ✅ **FIXED 2026-08-13** — `--attached`. Townhouses resolve their own lot; apartments fall back to the scheme parcel. 86.7% of houses had an aerial against 0.4% of units, despite 94.9% of units holding the LAT/PLAN to render one. |
| `scripts/backfill_beds_baths.py` | ✅ **FIXED 2026-08-13** — `--attached`. Bedrooms are the single biggest constraint on unit valuation (WITH a count 90% of subjects get a range, WITHOUT 22%). Applied: attached off-market bedroom coverage 53.5% → **57.1%**. |
| `scripts/batch_value_offmarket.py:67` | Superseded rather than fixed — attached dwellings are valued by the parallel unit method (`precompute_unit_valuations.py`), because the house engine measures 18.0% MAE on attached stock against 10.3% on houses. Leaving the house batch house-only is correct. |
| `08_Market_Narrative_Engine/generate_suburb_medians.py` (step 13) | Superseded by `unit_market_series`. ⚠ Also carries a latent bug of its own: its second source at `:147` has **no** type filter, so unit sales already contaminate the House median. |
| `03_For_Sale_Coverage/generate_suburb_statistics.py` (step 14) | No unit statistics exist. Not yet needed by any unit surface. |
| `scripts/precompute_active_listings.py` (step 19) | Superseded for the unit page by `unit_market_series.active_listings`. |
| `generate_property_ai_analysis.py:334-335, 4155, 4194` | Editorial gated by `EDITORIAL_PROPERTY_TYPES` (default `House`). The prompt itself assumes detached — `config/property_editorial_prompt.md:81` reads *"The house is worth nothing. The land is worth everything."* Opening the gate without rewriting the prompt would be worse than leaving it shut. |
| `src/lib/db.server.ts:648` `getSuburbPriceHistory` | House-only and documented as such; superseded for units by the attached series. |
| `src/lib/db.server.ts:1111` `HOUSE_TYPES` | Active-listing fallback; superseded for units. |
| `scripts/generate-sitemap.mjs:327,414` · `off-market.$slug.tsx:752` | The indexing gates. Deliberate, and the code says so — *"CURRENT PRODUCT ELIGIBILITY, NOT a permanent unit exclusion"*. This is plan item H1. |

---

## ✅ Correct — leave alone

`backfill_design_envelope.py` (the $1M–$2M envelope is explicitly a detached-house
envelope) · `fix_house_misclassification.py` (its whole job is restoring wrongly-relabelled
houses) · `Page_Redesign_V2/batch.py` (dev sampler) · `fpf_send.py`, `fb-page-post.py`,
`select_homes.py` (editorial/marketing surfaces that are house products by choice) ·
`appraisal_template/data_pull.py` · `oil_shock_analysis.py`, `audit_canonical_paths.py`,
`main_site_health_check.py` (analysis and monitoring scoped on purpose) ·
`homeFixture.ts` (test fixture) · the marketing copy in `marketMetrics.ts` and
`MarketMetricsPage.tsx`, which correctly *labels* its figures "houses only".

---

## The pattern worth remembering

In every case the filter was written when the product genuinely was houses-only, and it
was correct then. It became wrong silently, when the data grew to support units and
nothing prompted a re-read. None of these threw an error; two of them produce confident
wrong answers today.

**A type filter is a claim about the product, not about the data.** When the product
changes, the filters do not follow on their own — and a grep for one string
(`property_type: "House"`) does not find the ones written as `$in: ['house','House']`,
`classified_property_type`, `NON_HOUSE_TYPES`, or an untyped cohort paired with a typed
lookup. The last of those is the most dangerous, because it looks like no filter at all.
