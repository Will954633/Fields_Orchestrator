# Units in `/off-market` V4 — Coverage Audit

**Date:** 2026-08-10 · **Scope:** everything that produces content on a live V4 off-market page
(`https://fieldsestate.com.au/off-market/27-huntingdale-crescent-robina`) and the sub-processes feeding it.
Read-only audit. Nothing was changed.

---

## 0. The finding that reframes the task

**We are already serving unit pages. They are already wrong.**

The question was framed as "what would it take to *include* units". That is not the current state.
`v4Eligible()` (`src/pages/OffMarketPage/v4/OffMarketV4.tsx:48-51`) tests **suburb only** — there is no
property-type gate on the render path. Any attached dwelling in Robina / Varsity Lakes / Burleigh Waters
gets the full V4 page today.

Verified live, 2026-08-10:

| URL | HTTP | Rendered |
|---|---|---|
| `27-huntingdale-crescent-robina` (house, control) | 200 | 409 text lines, full page |
| `1-1-silvermaple-street-robina` (unit, no discovery doc) | 200 | 178 lines — Part 02 absent entirely |
| `1-3-laurel-oak-drive-robina` (unit, has discovery doc) | 200 | 211 lines — Part 02 renders **house content** |

A 14/14 random sample of unit pages with discovery docs returned HTTP 200. They are `noindex, nofollow`,
so Google is not the exposure — but every direct link, QR code, letterbox drop, SMS "keep the link",
Messenger reply and returning visitor reaches them.

### What a unit owner is actually told today

From `1/3 Laurel Oak Drive, Robina` (live capture):

> *"It shares its core profile with 107 of 233 nearby homes"* — where the 233 is labelled two lines later as
> **"Houses for sale across the wider comparison catchment"**.
>
> *"A family who has outgrown their current home but wants the space and **backyard** to stay in Robina."*
>
> *"How quickly homes like yours are selling — a median of 34 days in Robina."*
> *"40 **houses** for sale in Robina right now."*
> *"Robina median **house** price — $1,490,000"* + the quarterly house-median chart.

Every one of those market series is houses-only **by construction** — `scripts/precompute_union_prices.py:30`
(*"House-only via the shared classifier"*), `dwelling_filter: classify_dwelling == house` (`:547`).
`suburb_median_prices` holds 76 documents, **all** `property_type: "House"`; there is no unit series anywhere.

This is a live editorial-accuracy defect under the Rule 5 factual-accuracy standard, and it exists
**independently of whether units are ever formally launched**. It should be fixed regardless of the
outcome of this audit.

---

## 1. How ~8,095 unit pages got built despite a hard exclusion

`offmarket_discovery_nightly.py:151` excludes units with:

```python
"address": {"$not": UNIT_ADDR_RE}      # UNIT_ADDR_RE = re.compile(r"\d+\s*/\s*\d+")
```

Yet `system_monitor.offmarket_discovery` contains **8,095 documents whose rendered address is unit-shaped**
(Varsity Lakes 3,104 · Robina 3,039 · Burleigh Waters 1,952).

**Cause — measured, not inferred.** Sampling 4,000 of them and joining back to the source document:

| Why it passed the filter | Count |
|---|---|
| `address` field is **absent** (address lives in `complete_address`) | **3,991 (99.8%)** |
| `address` genuinely unit-shaped (filter should have caught it) | 9 |

Examples: `{'address': None, 'complete_address': '1/3 LAUREL OAK DRIVE ROBINA QLD 4226', 'property_type': None}`.

This is **the same defect that was found and fixed in the sitemap generator two days ago** —
`[OFFMARKET-UNIT-SITEMAP-MISMATCH]`, 2026-08-08, which introduced `effectiveAddress()` in
`generate-sitemap.mjs`. The Python builder was never given the same treatment. Per that entry's own
tally this is the **6th instance** of the "one policy expressed in two places that drifted" class.

**One-line-ish fix, worth doing now:** apply the address test to `address || complete_address` per-doc in
the builder loop, mirroring `effectiveAddress()`. Note `ADDRESS_STANDARD` must stay excluded — it holds
the literal datum code `"UK"` on 2,952 Robina unit records.

---

## 2. Where the house-only policy actually lives

The unit-detection rule is **duplicated in five places with three different definitions**:

| Location | Definition |
|---|---|
| `shared/dwelling_type.py` (canonical, 3-bucket, address-first) | `_UNIT_ADDRESS` + `UNIT_TYPE_TOKENS` + trust-ordered `_TYPE_FIELDS` |
| `07_Valuation_Comps/precompute_valuations.py:259` | its own `_UNIT_TYPE_TOKENS` copy |
| `Page_Redesign_V2/offmarket_discovery_nightly.py:121` | `UNIT_ADDR_RE`, `address` field only |
| `Page_Redesign_V2/fix_house_misclassification.py:31` | `UNIT_ADDR_RE` again |
| `01_Website/scripts/generate-sitemap.mjs:334` + `off-market.$slug.tsx:676` | `UNIT_ADDR_RE` + `NON_HOUSE_TYPES` |

**`shared/dwelling_type.py` already exists and is already correct** — including the three-bucket
`house`/`attached`/`unknown` return whose docstring warns *"in Queensland a great many genuinely detached
homes sit on strata or community title with a unit-style address."* It has **exactly one consumer**:
`precompute_union_prices.py`. Adopting it everywhere else is the single highest-leverage structural change
in this audit, and it is prerequisite to all the rest.

**This is not a permanent policy.** `generate-sitemap.mjs:345-352` states it explicitly:

> *"SCOPE — this is CURRENT PRODUCT ELIGIBILITY, NOT a permanent unit exclusion. Attached homes are a
> planned surface. The rule that matters is 'supported property type + sufficient data + resolved identity
> = indexable'; the slash is only an address-format signal standing in for it today… When attached-home
> pages ship and the route starts serving `index, follow` for them, relax this filter in step."*

---

## 3. Population and demand

### Population (3 core suburbs, 27,105 documents)

| Measure | Robina | Varsity Lakes | Burleigh Waters | Total |
|---|---|---|---|---|
| Attached (`classify_dwelling`, all docs) | 3,288 | 3,485 | 1,576 | **8,349** |
| Unclassifiable (`unknown`) | 2,878 | 1,214 | 1,071 | **5,163** |
| Would become **indexable pages** after all gates | ~1,600 | ~800 | ~200 | **≈3,000** |

≈ **+20%** on the current 14,742 indexable off-market URLs.

The 5,163 `unknown` bucket matters: 4,531 of the 4,559 URLs pulled from the sitemap on 2026-08-08 had
`property_type: None`. Step 112 (`classify_property_type.py`) is scoped `{"listing_status": "for_sale"}`
(`:186`) and so **never touches off-market or cadastral stock** — the records that make up the entire
off-market product.

### Demand — real and measurable

| Source | Unit-address share |
|---|---|
| Google Search Console, address-shaped queries | **135 of 526 queries; 233 of 1,230 impressions (19%)**, avg position 9.4 |
| `address_resolution` (owner address lookups) | **81 of 291 (28%)** |

Top unit queries include `29/255 varsity parade varsity lakes` (42 impressions),
`16/84 cumberland drive varsity lakes` (40), `72/98 university drive varsity lakes` (29).

---

## 4. What breaks, by layer

### 4a. Frontend (`src/routes/off-market.$slug.tsx`, `src/pages/OffMarketPage/v4/`)

Four load-bearing sections return `null` for units because they gate on `valuation.method === "engine"`:
`AnswerBlock`, `NearbySaleSection`, `ComparablesSection`, `ReliabilitySection`. The valuation chapter
collapses to `NoFigureSection` — which is honest (there is a real `attached_dwelling` decline string) but
leads its facts table with **"Land"**.

Actively mislabelled rather than missing:

| File:line | Text |
|---|---|
| `v4/TimingSection.tsx:50` | `{n} **houses** for sale in {suburb} right now` |
| `v4/TimingSection.tsx:82` · `v4/MedianTrend.tsx:101,123` | `{suburb} median **house** price` |
| `v4/TimingSection.tsx:39` | *"How quickly homes like yours are selling"* (house DOM series) |
| `v4/ReliabilitySection.tsx:37,85` · `AnswerBlock.tsx:81` | *"{n} {suburb} **houses**"*, *"**detached houses**"* |
| `v4/HeroSection.tsx:33,91-95` | `{n} m² land`; *"Title boundary from the Queensland cadastre — lot X"* |
| `OffMarketSuburbLinks.tsx:60,74` | *"{n} **houses** are already on the market"*, *"See **houses** for sale"* |
| `off-market.$slug.tsx:654` | meta description `{n}m² block` |

Two structural notes:
- `PropertyData` (`types.ts`) has **no dwelling-kind field**. `property_type` exists at `:87` and nothing in `v4/` reads it.
- `off-market.$slug.tsx:569` defaults blank/`UNKNOWN` `property_type` to **`"House"`** — so 5,163 unclassified records are treated as houses by the only type-aware code on the route.
- The hero aerial is a **cadastral lot polygon**. `cadastral_polygon.lot_area_sqm` fill on units: **0 of 3,112** (houses: 87.8%). For a unit the parcel is the whole strata plan.

### 4b. Build engine (`15_Off-Market/Page_Redesign_V2/`)

Of 11 V4 cards, **3 survive cleanly** for a unit (`recognition`, `dispersion`, `control`);
4 degrade or blank (`valuation`, `evidence`, `method`, `gain`); 4 need type-scoped pools
(`comparable`, `reveal`, `competition`, `buyer`).

Measured card depth in existing docs — units are already visibly thinner:

| Suburb | House avg cards | Unit avg cards | Unit `comparable` cards |
|---|---|---|---|
| varsity_lakes | 8.08 | **4.94** | 1 of 2,245 |
| burleigh_waters | 9.00 | **4.63** | **0 of 1,273** |

Specific engine problems:
- **Scarcity denominator is untyped.** `scarcity_features.py:439-485` base query is
  `{"listing_status": "for_sale", bedrooms: {$exists}}` — no type filter. A unit is counted against the
  detached-house market. This produces the live "107 of 233 nearby homes" claim.
- **Cohort medians are house medians** (`scarcity_features.py:274-315`, ~612 m² land / ~214 m² floor).
- **`obvious_comp`** picks nearest priced sale by distance — for a unit, usually the house next door — and
  its deltas are land / floor / build-year.
- **`green_space`** classifies "backs onto / adjoins" from a **single geocode**. For a 40-unit complex that
  point is the building centroid; the claim is about the *scheme*, not the dwelling, and can be flatly
  false. Recommend suppressing entirely for attached stock rather than softening.
- **`wait_time`** emits the literal phrase *"3-bedroom homes on 600m²+ blocks"*.
- **`copy_v4.yaml` has zero per-type templating** — one flat document. `:55` says *"built for **detached
  houses** between $1 million and $2 million"*.
- `fact_bundle.py:127` writes `property_type` into the bundle and **no consumer ever reads it**.

**Runtime cost is not a blocker.** ~2.1 s/home measured; 2,528 indexed-eligible units ≈ 88 min sequential
or ~22 min sharded ×4 — inside the existing 3,000/night cap. Steady state ≈ 0, *unless* units start
getting valuations, which flips every one to stale via `_needs_build` and repeats the 2026-08-06
10,000-deck backlog. Stage it.

### 4c. Nightly orchestrator

**Good news: 20 of 29 nightly steps are genuinely type-agnostic and already process units.** Steps
101–111, 113–116, 109, 107, 11, 12, 16, 121 need no change; step 116 (`data_quality_validator.py`) is
already correctly unit-aware.

| Step | Problem |
|---|---|
| **117** satellite | 🔴 **Garbage for units.** Prompt asks for `lot_shape`, `usable_yard`, `neighbour_setback` at zoom 19; `:126` says downstream *"treats `categories` as ground truth for the SUBJECT lot"*. A tower's common pool becomes the unit's pool. |
| **15** insights | 🔴 **Broken today, independent of units.** Peer cohort query (`:414-416`) has **no type filter**; the stats lookup (`:443-445`) is `property_type: "House"`. Units get ranked against a mixed cohort then percentile-scored against house breakpoints. Can emit *"Largest lot currently for sale"* for a unit. |
| **13, 14, 19** aggregates | 🔴 Hardcoded `property_type: 'House'`. No unit median, no unit percentiles, no unit active-listing count. (Step 13 also has a latent bug: its second source at `:147` has *no* type filter, so unit sales already contaminate the House median.) |
| **120** editorial | 🔴 Gated by `EDITORIAL_PROPERTY_TYPES` default `"House"`; prompt says *"The house is worth nothing. The land is worth everything."* |
| **112** classifier | ⚠ Scoped to `for_sale` only — never classifies the off-market stock that is the product. |

Nightly runtime 2h57m (last run). Adding units costs ≈ **zero** on the scraping/enrichment steps —
they already ingest the 95 for-sale attached listings.

### 4d. Valuation — the actual blocker

Three independent walls, any one of which is fatal:

1. **Floor area.** Hard requirement (`exclusion_reason = 'missing_floor_area'`). Coverage:

   | | Robina | Varsity Lakes | Burleigh Waters | Houses (Robina) |
   |---|---|---|---|---|
   | Units with any floor area | 610 (19.6%) | 399 (12.2%) | **80 (5.2%)** | 4,270 (**70.8%**) |

2. **The design envelope is a house envelope.** `_ENVELOPE_MIN/MAX = $1M–$2M` applies unconditionally.
   Measured attached sold prices: **median $980,000 (Robina), $950,000 (Varsity), $989,000 (Burleigh)** —
   *below the design floor in all three*. Only 37.9–48.8% of unit sales fall inside the band, so
   **~55–62% of units would be suppressed as `below_design_floor`** even if everything else worked.

3. **Comp pool fragments on exact type strings.** Selection is
   `s.get('property_type','') == prop_type`, and Domain emits `Apartment` and `Apartment / Unit / Flat`
   as separate values. A Robina `'Apartment'` subject sees **11 candidates** in 12 months, before the
   bedroom band and ±40% price filter. The regression needs ≥15 or it silently falls back to
   `SUBURB_ADJUSTMENT_RATES` — **house rates**.

Also: the engine's attached-dwelling refusal is `subject_is_attached and prop_type == 'House'`. A
*correctly typed* unit is **not** caught and proceeds to a full valuation — the guard only catches units
masquerading as houses. Measured attached MAE where that happened: **18.0% vs 10.3%** for houses.

**Missing adjustment dimensions** — the things that actually price a unit: strata levies (commonly a
5–15% value difference), floor level, aspect/outlook, lift vs walk-up, car-space tenure, complex quality,
balcony area, sinking-fund health. **None exist as fields.** Verified under Rule 8: `--find "body
corporate"`, `--find levy`, `--grep corp` → **0 of 2,653 distinct paths in `robina`**. `is_strata_title`
is `True` on **1 of 3,112**. Meanwhile `land_size`, `pool`, `cladding`, `golf_course_backing` and
`stories` are all actively wrong for units and would need retiring.

### 4e. The go-live gate

`V4_SUBURBS = new Set(Object.keys(ACCURACY))` — deliberately derived from the backtest so a surface
cannot ship without a measured error rate. `ACCURACY` is keyed **by suburb only, not by (suburb, dwelling
class)**. Shipping units without widening that key lends the house track record to unit ranges — a
failure that has already happened once (`valuationCopy.ts:45-49`: *"19 Manhattan Avenue, Robina — an
attached dwelling the engine refuses — rendered a confident range under 'we set it by testing this method
against 251 Robina houses'"*).

Usable backtest sample after price and floor-area filters: **Robina ~96–128, Varsity Lakes ~60–98,
Burleigh Waters ~19–51**. Against house baselines of n=251/184/146. **Burleigh Waters cannot support a
published band for units.**

---

## 5. What this would take

### Fix now, regardless of the units decision (days)

1. **Stop telling unit owners about the house market.** Either suppress `TimingSection` / `MedianTrend` /
   `OffMarketSuburbLinks` for attached dwellings, or label them "Robina houses" so the reader knows it is
   context, not their market. Currently framed as *"homes like yours"*.
2. **Fix the builder's address test** (`offmarket_discovery_nightly.py:151`) to use
   `address || complete_address`, mirroring the 2026-08-08 sitemap fix. Then decide, deliberately, whether
   the 8,095 existing unit docs are deleted or kept.
3. **Fix step 15's untyped peer cohort** (`calculate_property_insights.py:414-416`) — broken today for
   every property type.
4. **Skip step 117 for attached dwellings** — it is currently writing confidently wrong lot attributes that
   downstream treats as ground truth.

### Prerequisites before any unit surface can ship (weeks)

5. **Adopt `shared/dwelling_type.py` everywhere** and persist a normalised `dwelling_class` onto every
   document. Five duplicate definitions, one consumer, today.
6. **Extend step 112 to off-market stock** — or accept that ~10,200 untyped off-market records (≈4 photos
   between them) need a cadastral/plan-prefix classifier instead of a vision one.
7. **Backfill floor area for units.** At 5–20% coverage this gates everything valuation-shaped. Highest-leverage
   data fix in the whole audit.
8. **Backtest attached stock per suburb** (`--include-attached --price-filter none --blind-subject`, unit
   price band, canonicalised type strings). Derive unit-specific `_SUBURB_CALIBRATION`, `_SUBURB_80_BAND`
   and a unit envelope. Expect Burleigh Waters to fail the sample-size bar.
9. **Key `ACCURACY` by (suburb, dwelling class)** and widen `v4Eligible()` accordingly.

### Then, and only then

10. Relax the four gates **in lockstep** — `generate-sitemap.mjs`, `off-market.$slug.tsx` `meta()`,
    `offmarket_discovery_nightly.py`, `batch_value_offmarket.py`. Relaxing any subset reproduces the
    2026-08-08 sitemap/robots contradiction.
11. Type-scoped scarcity cohort + denominator; type-matched comp pool; unit buyer archetypes; unit filter
    checklist; `copy_units_v4.yaml`; suppress `green_space` for attached stock.
12. Unit-relevant market series (steps 13/14/19) — the `/market-intelligence/:suburb/houses-vs-units`
    category already ships live unit **asking-price** data, but there is no transacted unit median.

---

## 6. The strategic question this audit cannot answer

Everything above is tractable except one thing: **the comparable-sales method is the product.**
The page's entire argument is *"here is the evidence, here is how often the method has been right."*
For units we would be shipping a page whose central claim is either absent (no figure) or unmeasured
(no backtest), on stock where our own measurement says the method is **18.0% MAE against 10.3%**.

Two honest options:

- **A "no figure, real evidence" unit page** — sale history, complex context, POI, market framing scoped
  to units, and an explicit statement that we do not value attached dwellings. Cheap, defensible, shippable
  in weeks, and consistent with `NoFigureSection` already existing. It would not carry the valuation
  argument that makes the house page work.
- **A genuine strata valuation method** — $/m² or per-bedroom-cohort within a complex, using
  `PROPERTY_NAME` (142 named complexes in Robina, 25 with ≥5 units) joined on `LATITUDE`/`LONGITUDE` as the
  unit of analysis instead of the lot. This is the right answer and it is a quarter of work, gated on the
  floor-area backfill.

One encouraging structure: **`PROPERTY_NAME` gives a real complex-level grouping with no new scrape** —
`CIENNA VARSITY RIDGE` (254 units), `EASTLAKE` (93), `ROBINA GRAND RESIDENCES` (73). A unit's true
comparable is the same complex, not the suburb. That is the natural replacement for the lot as the
page's unit of analysis, and it is available today.

---

## Appendix — verification notes

- All field names were confirmed via `scripts/db_fields.py --find/--check/--grep` before use, per Rule 8.
  Names searched and **confirmed absent under every spelling**: body corporate, strata levy, sinking fund,
  complex entity, floor level, aspect.
- Zeros corrected during the audit: `valuation_data.reconciled_valuation` → real path
  `valuation_data.confidence.reconciled_valuation`; `land_area_sqm` → `scraped_data_v2.land_area_sqm`;
  `building_area_sqm` → `floor_area_sqm` / `internal_living_area_sqm`.
- `src/routes/building.$slug.tsx` is **not** a complex/building entity — it is the gerund, a
  "we're *building* our coverage" holding page. There is no building collection in any database.
- `system_monitor.onthehouse_sold` is **100% `property_type: "House"`** — it contributes zero unit comps.
