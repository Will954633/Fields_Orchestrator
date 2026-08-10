# Units on `/off-market` — Delivery Plan

**Date:** 2026-08-10 · Companion to `UNITS_COVERAGE_AUDIT.md`.
Covers the two things asked for: **getting unit owners the data they actually need**, and **a unit-specific
valuation methodology**.

---

## The governing constraint — REVISED 2026-08-10 after live testing

**Superseded finding.** I initially had floor area as the critical path (229 attached sales hold both a
price and a floor area). **Testing showed that framing was wrong.** Units in one complex sharing a bedroom
count are near-identical by construction — the heterogeneity that forces houses through a floor-area
adjustment does not exist. Measured coverage on the off-market surface:

| For off-market units missing a floor area (n=5,119) | Coverage |
|---|---|
| Same-complex donor **with a floor area** (beds+baths match) | 24.3% |
| Same-complex **priced sale** (beds match) | **85.8%** |

**The comparable is the same-complex sale, not the $/m².** Floor area is a refinement, not a requirement.
That moves it off the critical path.

**The real constraint is a unit price index** — we have none (`suburb_median_prices` is 76 docs, all
`property_type: "House"`). It is needed as the time-deflator for the method *and* it is what the live page
is currently getting wrong. One build fixes both.

---

## Can PropRadar help? — measured live, 2026-08-10

**Yes, for comparable sales. No, for the two things we actually lack.**

`GET /v1/suburbs/QLD/{suburb}/sold?property_type=Unit` returns real unit sales:

```
{'address': '21/10 Ben Lexcen Place, Robina, QLD, 4226', 'bedrooms': 2, 'bathrooms': 1,
 'parking': 1, 'property_type': 'Unit', 'sold_price': 840000, 'sold_date': '2026-07-09',
 'property_id': '8c9cc8ae', 'geo': None}
```

`GET /v1/properties/{id}` on 25 attached dwellings:

| Field | Result |
|---|---|
| `attributes.floor_area_sqm` | **5 of 25 (20%)** — same as our own coverage. **Does not solve the constraint.** |
| `attributes.land_size_sqm` | 11 of 25 — median 138 m², **max 2,535 m² for a 2-bed unit**. This is the *strata parcel*. |
| Strata / levy / floor level / lift | **No such field exists on any endpoint.** |
| `valuation.estimated_value` (AVM) | present, `confidence: "unknown"` |
| `last_sale.days_on_market` | present — we have no unit DOM of our own |
| `geo` | **locked to Pro tier** |

### ⚠ PropRadar has NO off-market unit data — measured, 0/12

`/properties/search` is a **listing + sold index, not a cadastral database**. Tested against 12 randomly
sampled *never-listed* attached dwellings drawn from our own off-market surface (9,470 available):

```
not found  2604/42 LAVER DRIVE ROBINA          not found  302/25 LAKE ORR DRIVE ROBINA
not found  203/2 RIVERWALK AVENUE ROBINA       not found  55/206 CHELTENHAM DRIVE ROBINA
...                                            => 0 of 12 found
```

**PropRadar cannot supply floor area, or anything else, for the 10,824 never-listed units that ARE the
off-market product.** It only knows stock that has been listed or sold. Plan accordingly.

**Verdict — use it for three specific things:**

1. **Unit sold comparables.** Title/settlement-based, so it catches what our Domain scrape misses.
   Our own `onthehouse_sold` is **711/711 House** by construction, so PropRadar is currently our *only*
   viable second source for unit sales.
2. **Unit days-on-market**, which we cannot compute today.
3. **A cross-check on our own range** — never as a published figure. Its AVM measured 3.4% median error
   against sold price, but ⚠ **that number is not credible**: the AVM almost certainly ingested the sale
   it was scored against. Do not quote it, internally or externally, without a leakage-free test.

**Two traps, both live:**

- ⚠ **`land_size_sqm` on an attached dwelling is the whole strata parcel.** Ingesting it into the land
  adjustment would produce exactly the "plausible-looking nonsense" failure mode — a 2-bed unit priced as
  if it sat on 2,535 m². **Quarantine this field for attached stock at ingest.**
- ⚠ Row counts are **page-limited at 20**, not totals. The 166 rows I pulled are 9 first-pages, not the
  12-month volume. Use `fetch_all_sold()` (cursor pagination), not `limit=`.

Budget is not a constraint: 18,300 of 20,000 monthly calls remaining.

---

## Phase 0 — Recover what we already pay for ($0, ~2 weeks)

**Nothing here is an acquisition. Every item is data already arriving in bytes we download and parse away.**

| # | Fix | Yield |
|---|---|---|
| 0.1 | **Source `agents_description` from `componentProps.description`**, not the collapsed DOM panel (`html_parser.py:311-334`, sold clone `html_parser_sold.py:443-466`) | 391 → 3,467 chars. **24% of listings publish "Council rates: $…", "Water rates: $…" or body-corp figures; 100% currently lost.** Verified: stored unit descriptions have a hard ceiling at 576 chars, **0 of 598 above 600**. |
| 0.2 | **Read `listingByIdV2.buildingArea` / `pageInfo.property.internalArea`** instead of JSON-LD `floorSize` | JSON-LD `floorSize` is absent for units — this is *why* our unit floor-area fill is 5–20%. Direct progress on the critical path, for listed units. |
| 0.3 | **Store `structuredFeatures[]`** (categorised, `{name, category, source}`) | Lift, gym, secure parking, intercom, on-site manager. Today `features` is a 17-keyword substring scan with no lift/gym/security token at all. |
| 0.4 | **Drop the `is_house` filter** at `onthehouse_sold_sync.py:58` / `onthehouse/client.py:132-133` | `onthehouse_sold` is **711/711 House**. Pages are already fetched and discarded. Zero marginal cost. |
| 0.5 | **Store PropRadar `attributes{}`** (`propradar/ingest_sold.py:55-68` closed dict; `market_status.py:142`) — **excluding `land_size_sqm` for attached** | Unit comps + DOM. |
| 0.6 | **Adopt `effectiveAddress` + `shared/dwelling_type` everywhere** (5 duplicate definitions today, 1 consumer) | Measured: attached **8,349 → 11,650**, unclassifiable **5,163 → 2,030 (−61%)**. Correctly classifies 3,300 more dwellings on its own. |
| 0.7 | **Use the cadastral `PLAN` prefix as the strata sub-type** | BUP (building w/ common property) + GTP (villa/townhouse) = **25.6% of attached vs 3.4% of houses — 7.5× enriched**, 93% filled. Gives apartment-vs-townhouse for free. **Stop using `is_strata_title`** — 500 False, 1 True, null on every BUP and GTP. |
| 0.8 | **Mine aspect/outlook from the recovered description text** | Even in the *truncated* 598 records: north-facing 40, outlook 34, water view 17. Expect ~9× at full length. |

---

## Phase 1 — Free public data ($0, ~2 weeks)

All CC-BY 4.0, commercially republishable with attribution.

| Source | Delivers | Verified |
|---|---|---|
| **QLD cadastre, LandParcelPropertyFramework layer 4** | Complex name, **CTS scheme number**, lots per scheme | **9,641 CMS-linked parcels** across the 3 suburbs; 414 distinct schemes in Robina alone |
| **QLD Buildings layer 11** (LiDAR) | Building height → **storeys band** | 42,940 footprints; 4.3 m/storey calibration = 59% exact, **90% within ±1 storey** |
| **AustLII `QBCCMCmr`** | Adjudicator orders → disputes flag | Free, full text, searchable by scheme |

⚠ **Publish storeys as bands ("4–6 storeys"), never point values** — the method cannot separate 1 from 2
storeys (tree canopy inflates low-rise). Lift is *inferred* from storeys above ~4 and must be labelled so.
⚠ Aggregate by **CMS number, not plan** — one scheme can span several plans.
⚠ LiDAR is Apr–Jun 2022; cadastre refreshes weekly. Version them separately.

**Verified negatives — do not spend time here:** no public QLD register of community titles schemes; no QLD
equivalent of NSW Strata Hub (and even NSW publishes no financials); Gold Coast council's `NO_OF_STOREYS`
/ `NO_OF_LIFTS` fields cover **council-owned assets only**; Geoscape has no Gold Coast free tier.

---

## Phase 2 — A unit price index (the actual critical path)

We have no unit price series anywhere. This one build unblocks three things at once:

1. **The method's time-deflator** (see Phase 3 — the test below had to borrow the *house* index).
2. **The live editorial defect** — unit pages currently show "Robina median **house** price" as the
   reader's own market.
3. **The market section** of the unit page.

**Build it the way the house series is built** — `precompute_union_prices.py` already does Domain ∪
onthehouse deduped on address+date, and already calls `classify_dwelling`. It filters
`== "house"` at one line. Emit the `attached` bucket in parallel, keyed
`precomputed_indexed_prices/_market_charts/_active_listings` by `(suburb, dwelling_class)`.

⚠ **Prerequisite:** `onthehouse_sold` is **711/711 House** by construction (Phase 0.4). Fix that first or
the unit index is built on Domain alone.

### Floor area — demoted to refinement, still worth collecting

1. **Phase 0.2** — Domain `internalArea` for every unit ever listed. Free, immediate.
2. **Same-complex imputation** — validated below; use for display and as a secondary adjustment.
3. **Floor plans** — `floor_plan_analysis` covers **75.9% of live unit listings** but 2.9% of all attached
   stock. Extend to archived listing images.

**Imputation is validated** (leave-one-out, n=424 across 73 cohorts):

| Basis | Median abs error | Within 10% |
|---|---|---|
| **Same complex + same bedrooms** | **5.2%** | **67%** |
| Suburb-wide, same bedrooms | 15.9% | 28% |

Within-cohort floor-area CoV is 10.5% vs 36.7% across all attached stock. Label imputed values as derived;
never present one as a measured figure.

---

## Phase 3 — A unit valuation methodology

**Do not extend the house method. Build a parallel one.** The house method's own measurement says it runs
**18.0% MAE on attached stock against 10.3% on houses**.

### 3.1 The method has been tested and it works

**Same-complex, same-bedroom sales, time-adjusted, leave-one-out** — n=4,093 predictions across 281
(complex, bedrooms) cohorts, median 33 comps per prediction:

| Metric | Unit method (measured) | House method (in-envelope) |
|---|---|---|
| Median abs error | **9.07%** | 8.2% |
| Mean abs error (MAE) | **12.19%** | 10.5% |
| Within 10% | **54.8%** | 59% |
| P80 error → 80% band | **±19.8%** | ±12.4% (shipped) |

**It lands close to the house method, and far better than the 18.0% MAE the house method scores on
attached stock.** The approach is sound.

⚠ **This is an upper bound on error, not a final figure.** Three reasons it should improve:
1. The time-deflator was the **house** median index — the only one that exists. A unit index (Phase 2)
   removes a known, systematic error source.
2. Only 4,549 of 12,500 usable sales had a deflator at all (36%), so the sample is index-limited.
3. Sales back to 2005 were deflated forward to 2026; long deflation amplifies index error.

⚠ **Not yet a publishable figure.** It is leave-one-out on a generous cohort, not a production-shaped
backtest. Re-run through `valuation_backtest.py` (§3.3) before any number reaches a page.

### 3.2 Design

- **Comparable pool:** same CTS scheme first, then same plan-type (BUP↔BUP, GTP↔GTP) within radius —
  never a detached house. Today's selector uses exact `property_type` string equality, which fragments
  `Apartment` from `Apartment / Unit / Flat` and leaves a Robina Apartment with **11 candidates**.
  **Canonicalise the type strings in `precompute_valuations.py` and `valuation_backtest.py` in the same
  change**, or the backtest measures a pool production will not have.
- **Basis:** the same-complex same-bed sale, time-adjusted — **not** $/m². Floor area enters as a
  secondary adjustment where known or imputed, not as a gate. This is the single biggest departure from
  the house method and it is what makes the method reachable on 85.8% of off-market stock.
- **Retire for attached:** `land_size`, `pool`, `cladding`, `golf_course_backing`, `stories`.
- **Add when available:** floor level, aspect, lift, car-space tenure, levy band.
- **Its own envelope.** Attached medians are **$980k / $950k / $989k** — *below* the house `$1M` floor.
  Reusing it suppresses ~55–62% of units as `below_design_floor`.
- **Its own accuracy key.** `ACCURACY` is keyed by suburb only. **Key it by (suburb, dwelling class)** or
  the house track record leaks onto unit ranges — which has already happened once (19 Manhattan Avenue).
- **Backtest flags are mandatory:** `--include-attached --price-filter none --blind-subject`, unit price
  band. Off-market attached stock has ~3 photos in total, so `--blind-subject` is not optional.

---

## Phase 4 — Levies: owner-funded, never bulk

### The legal position (BCCM Act 1997 s205, current 1 Aug 2025)

Body corporate records are restricted to an **"interested person"** — owner, mortgagee, buyer, disclosure
recipient, someone with a "proper interest", **or an agent of any of those (s205(13)(f))**.

**We cannot obtain these as a third-party data business.** The "proper interest" limb will not carry a
commercial harvesting operation. **But the agent limb fits our funnel exactly**: when an owner engages us,
we act for them, lawfully.

### The multiplier that makes it affordable

Levies are not independent per-lot facts — they are apportioned by lot entitlement:

```
scheme budget = lot levy × (total entitlement ÷ lot entitlement)
```

Verified against a real Form 33: admin $2,127.60 × 10,000/1,080 = **$19,700.00**; sinking
$702.00 × 10,000/1,080 = **$6,500.00**. Both land on exact round budget figures.

**One Form 33 ($86.95) + one CMS ($50.16) reconstructs the levy for every lot in that scheme — $137.**

### And the stock is extremely concentrated

| Tier | Complexes | Units | Share |
|---|---:|---:|---:|
| Top 54 | 54 (5%) | 4,951 | **50%** |
| ≥10 units | 171 (16%) | 7,529 | 77% |
| ≤3 units | 728 (69%) | 1,480 | 15% |

**~54 owner engagements would cover half the unit market's levy data** — and each one is a paying customer,
not a cost. This turns the largest data gap into a reason to talk to sellers, which is the business model.

**Optional:** CMS images for the top 54 schemes = **$2,709** ($0.55/unit) for full entitlement schedules.
Buy lazily, one scheme at a time, when a page for it is actually built.

### Never
Scrape the portals. REA's Terms of Use ban *the purpose* — *"constructing or populating a property data or
property insights product"* — which is a verbatim description of Fields, and REA sued Domain in the Federal
Court in Dec 2024 over 181 listings. Manual re-typing is caught identically. It would also fail on the
merits: instantaneous coverage is **~0.7–0.9% of unit stock**, and the fill is structurally biased downward
because low levies are advertised and high ones omitted. Worse than no data for a valuation product.

Also never: buy CoreLogic/Cotality/PropTrack/Pricefinder for strata — **they do not have it**. Pricefinder's
own public OpenAPI spec was inspected: `strata`, `bodyCorporate`, `levy`, `sinkingFund` → **zero matches**.

---

## Phase 5 — Page and gates

1. **Fix the live wrongness first** (see audit § 5) — unit pages currently present house medians, house DOM
   and house listing counts as *"homes like yours"*, and a buyer persona promising a *"backyard"*.
2. Type-scoped scarcity cohort and denominator; suppress `green_space` for attached stock; unit buyer
   archetypes; `copy_units_v4.yaml`.
3. Replace the cadastral-lot hero — for a unit the parcel is the whole scheme. Use complex context.
4. **Relax the four gates in lockstep** — `generate-sitemap.mjs`, `off-market.$slug.tsx` `meta()`,
   `offmarket_discovery_nightly.py`, `batch_value_offmarket.py`. Relaxing any subset reproduces the
   2026-08-08 sitemap/robots contradiction.

---

## Publishing guardrails

**Safe** (scheme-level facts about an entity): CTS number, complex name, lots in scheme, storeys band,
regulation module, plan type, scheme-level admin/sinking budget, insurance sum insured.

**With care:** per-lot *indicative* levy derived from entitlement share — state the method, the certificate
date, and that it is derived. Levies reset annually; anything older than ~18 months is indicative only.

**Never:** owner names or addresses from the body corporate roll; arrears or individual debt; **defect
allegations** — Form 33 explicitly excludes defects, so any claim would rest on adjudicator orders or QBCC
records and carries live **defamation** exposure. Publish the existence and citation of a formal order,
never a characterisation.

⚠ **Two open legal questions — get advice, do not resolve internally:**
1. **Titles Registry republication.** Search output carries a Crown copyright notice and the ToU page 404s.
   Publish *derived facts* (entitlement shares, lot counts), not reproduced documents.
2. **s205 agency mechanics at volume** — worth 30 minutes of a strata lawyer's time to confirm the authority
   wording before doing this repeatedly.

Privacy Act: the small-business exemption has **not** been removed yet (tranche 2, no Bill as at Feb 2026).
Design as though it applies now.

---

## Sequencing and the honest recommendation

```
Phase 0  ($0, 2wk)  recover discarded data ────┐
Phase 1  ($0, 2wk)  free public strata data ───┼──► ship a NO-FIGURE unit page
Phase 5a (1wk)      fix the live wrongness ────┘    (real evidence, no valuation)
                              │
Phase 2  (ongoing)  floor-area backfill ──► gate: Robina ≥150
                              │
Phase 3  (quarter)  unit valuation method ──► backtest ──► ACCURACY[(suburb,class)]
                              │
Phase 5b            relax the four gates, index
Phase 4  (ongoing, owner-funded)  levies
```

**Recommendation: ship the no-figure unit page after Phases 0, 1 and 5a — roughly 5 weeks — and do not
wait for the valuation.**

Rationale: units are already being served a broken page today, so the alternative to shipping is not
"nothing", it is "continue being wrong". A page carrying complex name, scheme size, storeys, sale history,
POI context, unit-scoped market data and an explicit *"we do not put a figure on attached dwellings and
here is why"* is honest, defensible, and better than what is live now. `NoFigureSection` already exists.

The valuation figure is a quarter of work gated on data we do not yet have, and **Burleigh Waters will
probably never qualify**. Treating it as the launch requirement would keep the current broken pages live
for months.

**One thing I cannot decide:** whether the ~8,095 unit discovery docs already built (audit § 1) get deleted
and rebuilt under the unit engine, or repaired in place. That is a product call about whether current
content is a liability or a base to improve. My inclination is delete — they were built by a house-shaped
engine and carry house-shaped claims — but it is your call.
