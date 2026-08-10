# Units on `/off-market` — Development Plan

**Version:** 1.1 · **Date:** 2026-08-10 · **Status:** proposed, not started
This is the execution document. Evidence: `research/UNITS_COVERAGE_AUDIT.md`. Strategy and sourcing
research: `research/UNITS_DELIVERY_PLAN.md`.

## Where this work lives

**Everything for this project goes in `15_Off-Market/Units/`.**

```
15_Off-Market/Units/
├── UNITS_DEVELOPMENT_PLAN.md      ← this file, the execution doc
├── research/                      ← audit + sourcing research (evidence, not instructions)
├── scripts/                       ← all new code for this project
│   ├── render_unit_report.py      ← the acceptance artefact (see below)
│   ├── unit_valuation.py          ← the parallel method (Workstream F)
│   ├── complex_entity.py          ← CTS/scheme builder (Workstream E)
│   └── ...
└── artifacts/                     ← rendered reports, backtest output, snapshots
    ├── unit_reports/              ← per-address markdown, the review surface
    └── snapshots/                 ← pre-delete backup of the 8,095 docs (D1)
```

**Exception — edits to existing pipeline files stay where they are.** Workstreams A, C and D are mostly
changes to `scripts/`, `shared/`, `Page_Redesign_V2/` and the website repo. Only *new* code for this
project lives under `Units/scripts/`. Do not fork existing pipeline files into this folder — that would
create the sixth duplicate definition, which is the root cause of half the defects in the audit.

---

## Premise

Units are **already being served V4 pages** — `v4Eligible()` tests suburb only. So the choice is not
"launch units or not". It is "keep serving a wrong page, or fix it". Every phase below is ordered by that.

**Target state:** attached dwellings in the three measured suburbs get a page that is true about their
market, carries complex-level evidence, states a range where the method qualifies and refuses one where it
does not, and is indexed only where the data supports it.

**Population:** 11,650 attached dwellings across the three suburbs; 10,824 never-listed; ≈3,000 would
become indexable.

---

## The acceptance artefact — a markdown report per unit address

**Every milestone is accepted by reading a document, not by reading a diff.**

```bash
python3 15_Off-Market/Units/scripts/render_unit_report.py \
    --address "1/3 Laurel Oak Drive, Robina" \
    --out 15_Off-Market/Units/artifacts/unit_reports/1-3-laurel-oak-drive-robina.md
```

It emits the **full prose** of a unit page — every section the live house page carries, in order, with real
data — so the copy can be judged, argued with and rewritten in markdown long before any of it reaches the
web. Where content does not yet exist it emits an explicit marker naming the gap and the workstream that
closes it:

```markdown
> ⛔ GAP [D1] — no unit price series exists for Robina.
>    House median would be wrong here. Section suppressed.
```

So the document doubles as a live progress tracker: **the plan is done when a sampled report contains no
GAP markers and reads as well as the house page.**

**Section map — unit page vs the live house page** (captured from
`/off-market/27-huntingdale-crescent-robina`, 409 lines):

| # | House page | Unit equivalent | Supplied by |
|---|---|---|---|
| 0 | Hero: lot boundary, land m², beds/baths/floor, last sale | Complex name, scheme size, storeys band, beds/baths/floor, last sale | E1/E2/G4 |
| 1 | What's changed — comps, suburb median, DOM, macro | Same, **unit-scoped** | D1–D4 |
| 2 | Part 01 — range, the sale up the road, comparables, reliability, dispersion | Same-complex comps, unit range, unit accuracy | F1–F8 |
| 3 | Part 02 — reveal, features, rarity funnel, value drivers, buyer | Complex identity, position in scheme, unit-scoped rarity, unit buyer | G1–G6, E4 |
| 4 | Part 03 — timing, market, corrections, plan, next | Same, unit-scoped | D5, G1 |

**Build it early (M1) and re-run it at every milestone.** It is the cheapest way to discover that a section
is structurally meaningless for a unit — far cheaper than discovering it in React.

---

## Milestones and gates

| Milestone | Outcome | Acceptance | Est. |
|---|---|---|---|
| **M1** | Bleeding stopped; **report renderer exists** | 0 attached pages showing house data as their own. Report renders for 10 addresses — mostly GAP markers, but the skeleton is right | **Week 2** |
| **M2** | Classification spine + unit market series | `dwelling_class` on 100% of core docs. **Report: sections 0–1 and 4 carry real unit data, no GAPs** | **Week 5** |
| **M3** | Complex data; no-figure page ships | **Report: section 3 complete; section 2 is an honest refusal, not a hole.** Will reads 10 reports and signs off the prose. Then React, then index | **Week 8** |
| **M4** | Valuation figure where measured | Backtest passes per (suburb, class). **Report: zero GAP markers** | **Week 14** |

**M4 will not include Burleigh Waters.** n≈27–51 usable records against a house baseline of 146. Same
discipline as `V4_SUBURBS` today: a surface cannot ship without a measurement.

**Prose is signed off in markdown at M3, before it is built in React.** That ordering is deliberate — the
house page's copy is its product, and reviewing it as a document is faster than reviewing it as a deploy.

---

## Workstream A — Stop the bleeding (M1)

Independently justified. Do this even if units are never formally launched.

| ID | Change | Files | Done when |
|---|---|---|---|
| **A1** | Add `dwelling_class` to `PropertyData`; loader sets it from `classify_dwelling` on the effective address. **Suppress or relabel** `TimingSection`, `MedianTrend`, `OffMarketSuburbLinks` for `attached`. | `src/routes/off-market.$slug.tsx`, `v4/types.ts`, `v4/TimingSection.tsx`, `v4/MedianTrend.tsx`, `components/OffMarketSuburbLinks/` | A unit page shows no house median, house DOM or "N houses for sale" framed as its market |
| **A2** | Builder unit test uses `address \|\| complete_address` (mirror `effectiveAddress()`; keep excluding `ADDRESS_STANDARD` — it holds `"UK"`) | `15_Off-Market/Page_Redesign_V2/offmarket_discovery_nightly.py` | Dry-run count matches the sitemap generator's attached count |
| **A3** | Type-filter the peer cohort so it matches the house-only stats lookup | `scripts/backend_enrichment/calculate_property_insights.py` | No unit receives a house-cohort percentile; "Largest lot" cannot fire on a unit |
| **A4** | Skip step 117 for `attached` — it writes lot/yard/setback attributes from a strata parcel and downstream treats them as ground truth | `scripts/step117_satellite_analysis.py` | Step logs `skipped_attached` count; no new satellite doc on an attached dwelling |
| **A5** | **Decision + action** on the ~8,095 existing unit discovery docs | — | See *Decision D1* |

**A1 is the one that matters.** Everything else in A is hygiene; A1 is the thing a real unit owner is
reading right now.

---

## Workstream I — The report renderer (M1, then continuous)

Built **first**, alongside A. It is how every later workstream is accepted.

| ID | Change | Done when |
|---|---|---|
| **I1** | `Units/scripts/render_unit_report.py` — address → markdown, mirroring the house page's section order exactly | Renders for any attached address in the 3 suburbs without crashing |
| **I2** | Every section either emits real prose or a `⛔ GAP [workstream-id]` marker naming what is missing and why | No section silently renders empty — a hole must announce itself |
| **I3** | `--batch` mode over a sampled address list; a summary table of GAP counts by workstream | One command shows how much of the page is real |
| **I4** | Reuse the **existing** engine (`fact_bundle.py` → `emit_v4.py`) plus a markdown emitter — do not reimplement the content logic | Report content and page content cannot diverge |

**I4 is the important constraint.** If the renderer builds its own version of the facts, it will drift from
what the page shows and we will have re-created the exact defect class the audit is full of — one concept,
two implementations, one maintained. The renderer is a *new output format for the existing engine*, not a
new engine.

**Sampling for review:** at least one of each — a high-rise BUP (e.g. `42 Laver Drive, Robina`), a low-rise
GTP townhouse, a duplex, a unit with a same-complex sale history, and one with none. The failure modes
differ per subtype and a sample of five high-rises will hide three of them.

---

## Workstream B — Classification spine (M2)

Everything downstream keys off this. Do not start C–G until B1/B2 land.

| ID | Change | Notes |
|---|---|---|
| **B1** | Make `shared/dwelling_type.py` the **only** definition. Delete the duplicates in `precompute_valuations.py` (`_UNIT_TYPE_TOKENS`), `offmarket_discovery_nightly.py` + `fix_house_misclassification.py` (`UNIT_ADDR_RE`), and port it to JS for `generate-sitemap.mjs` / `off-market.$slug.tsx`. | 5 definitions, 3 behaviours, 1 consumer today |
| **B2** | Persist `dwelling_class` (`house`/`attached`/`unknown`) + `dwelling_subtype` on every core-suburb doc. One backfill + nightly maintenance. | Measured effect of using the effective address: attached **8,349 → 11,650**, unknown **5,163 → 2,030 (−61%)** |
| **B3** | Derive `dwelling_subtype` from the cadastral `PLAN` prefix: **BUP** = building w/ common property (lift likely), **GTP** = villa/townhouse complex, **SP** = ambiguous, **RP** = freehold. | 93% filled; BUP+GTP is 25.6% of attached vs 3.4% of houses (7.5× enriched) |
| **B4** | Stop reading `is_strata_title` anywhere. | 500 `False`, 1 `True`, null on every BUP and GTP |
| **B5** | Extend step 112 (`classify_property_type.py`) beyond `for_sale`, or add a cadastral classifier for the ~2,030 remaining unknowns. | Vision won't work — off-market attached stock has ~3 photos in total |

**Rule 7 applies:** the `dwelling_class` backfill becomes an ongoing nightly maintenance job → wrap in
`job_run("dwelling_class_maintenance", cadence_hours=24, ...)` and **raise on the zero-output path**
(classified 0 while unclassified > 0 is a failure, not an empty queue).

---

## Workstream C — Recover discarded data (M2) — $0

Nothing here is an acquisition. All of it already arrives in bytes we download.

| ID | Change | Files | Yield |
|---|---|---|---|
| **C1** | Source `agents_description` from `componentProps.description`, not the collapsed DOM panel | `07_Undetectable_method/.../html_parser.py`, `02_Domain_Scaping/.../html_parser_sold.py` | 391 → 3,467 chars. 24% of listings publish council rates / water rates / body-corp figures; **100% currently lost** (verified: 0 of 598 stored unit descriptions exceed 600 chars) |
| **C2** | Read `listingByIdV2.buildingArea` / `pageInfo.property.internalArea` instead of JSON-LD `floorSize` | Domain scraper | JSON-LD `floorSize` is absent for units — this is *why* unit floor-area fill is 10.4% |
| **C3** | Store `structuredFeatures[]` (`{name, category, source}`) | Domain scraper | Lift, gym, secure parking, intercom. Current `features` is a 17-keyword substring scan with no such token |
| **C4** | Drop the `is_house` filter | `scripts/onthehouse_sold_sync.py`, `scripts/onthehouse/client.py` | `onthehouse_sold` is **711/711 House**. Pages already fetched and discarded. **Blocks D1.** |
| **C5** | Store PropRadar `attributes{}` + `last_sale.days_on_market` | `scripts/propradar/ingest_sold.py`, `market_status.py` | Unit comps + unit DOM. Use `fetch_all_sold()` — rows are page-limited at 20, not totals |
| **C6** | Mine aspect/outlook from recovered description text | new enrichment | Even truncated: north-facing 40, outlook 34, water view 17 of 598 |

⚠ **C5 hard requirement:** **quarantine `land_size_sqm` for attached dwellings.** PropRadar returned
**2,535 m² for a 2-bed unit** — the strata parcel. Ingesting it into the land adjustment is the
"plausible-looking nonsense" failure mode.

⚠ **C1/C2/C3 re-scrape scope:** these only improve records we scrape *from now on*, plus any archived
payloads we can reprocess. Never-listed stock is unaffected — that is what B3/E and the imputation are for.

---

## Workstream D — Unit market series (M2) — the critical path

Fixes the live defect, supplies the method's deflator, and populates the page's market section. One build.

| ID | Change | Notes |
|---|---|---|
| **D1** | Emit the `attached` bucket from the union-median pipeline in parallel with `house` | `scripts/precompute_union_prices.py` already calls `classify_dwelling` and filters `== "house"` at one line. **Depends on C4** or it is built on Domain alone |
| **D2** | Key `precomputed_indexed_prices`, `precomputed_market_charts`, `precomputed_active_listings` by **(suburb, dwelling_class)** | Currently `_id: suburb` with no type dimension |
| **D3** | Steps 13 / 14 / 19 emit a parallel unit series | `generate_suburb_medians.py`, `generate_suburb_statistics.py`, `precompute_active_listings.py` — all hardcode `property_type: 'House'`. Also fix step 13's second source, which has **no** type filter and already contaminates the House median |
| **D4** | `whats_changed.py` reads the class-scoped series and drops "median **house** price" copy for attached | Currently hardcoded |
| **D5** | Front-end reads the class-scoped series | Completes A1 properly — relabel becomes real data |

**Rule 7b:** D1/D3 must raise when they produce a zero-length attached series while attached sales exist.
An empty series is not an empty queue.

**Verification:** run `scripts/verify_market_metrics_live.py` and **read every saved file** (Rule 6) —
a unit series introduces a fourth content layer that can go stale independently.

---

## Workstream E — Complex entity from free public data (M3) — $0

All CC-BY 4.0, commercially republishable with attribution.

| ID | Source | Delivers |
|---|---|---|
| **E1** | QLD cadastre, LandParcelPropertyFramework **layer 4** | Complex name, **CTS scheme number**, lots per scheme. Robina: 4,872 parcels carry a complex name, 894 of them BUP/GTP |

**⚠ Verified field names, 2026-08-10 — the research doc named these wrongly.** Tested live from the VM:

```
GET .../PlanningCadastre/LandParcelPropertyFramework/MapServer/4/query
    ?where=locality='Robina' AND plan LIKE 'BUP%' AND feat_name IS NOT NULL
    &outFields=lotplan,feat_name,alias_name,lot_area&f=json

  1BUP9672 | Shanandoa Court | CMS5659
```

| Want | **Real field** | Not |
|---|---|---|
| Complex name | `feat_name` | ~~COMPLEX_NAME~~ |
| CTS / CMS number | `alias_name` | ~~CMS_NUMBER~~ |
| Parcel key | `lotplan` | — |
| Lots per scheme | `COUNT(*) GROUP BY alias_name` | — |

**Two traps that cost real time:**
- `locality` is **title-case** (`'Robina'`). `'ROBINA'` returns **0**, not an error — a silent false absence,
  exactly the Rule 8 failure mode. Use `UPPER(locality)='ROBINA'`.
- **Layer 10 "Strata Parcels Only" is not community-title lots** — Robina returns **59**. It means
  volumetric/strata *land* parcels. The unit stock is in layer 4, discriminated by the `plan` prefix.
| **E2** | QLD Buildings layer 11 (LiDAR) | Height → **storeys band**. 4.3 m/storey: 59% exact, **90% within ±1** |
| **E3** | AustLII `QBCCMCmr` | Adjudicator orders → disputes flag (Form 33 explicitly excludes defects) |
| **E4** | New `Gold_Coast.complexes` collection keyed on **CTS number** | The unit of analysis, replacing the lot |

⚠ **Publish storeys as bands** ("4–6 storeys"), never point values — the method cannot separate 1 from 2
storeys. **Lift is inferred** above ~4 storeys and must be labelled inferred.
⚠ Aggregate by **CMS number, not plan** — one scheme can span several plans.
⚠ Version E1 (weekly) and E2 (Apr–Jun 2022 LiDAR) separately.

**Do not pursue:** no public QLD scheme register; no QLD Strata Hub equivalent; council `NO_OF_STOREYS` /
`NO_OF_LIFTS` covers **council-owned assets only**; Geoscape has no Gold Coast free tier.

---

## Workstream F — Unit valuation method (M4)

**A parallel method, not an extension.** The house method scores **18.0% MAE on attached stock vs 10.3% on
houses** by its own measurement.

| ID | Change | Notes |
|---|---|---|
| **F1** | Canonicalise type strings in **`precompute_valuations.py` and `valuation_backtest.py` in the same change** | Domain emits `Apartment` and `Apartment / Unit / Flat` separately; a Robina Apartment sees **11 candidates**. Changing only production means the backtest measures a pool production won't have |
| **F2** | Comparable selector: same CTS scheme → same subtype (BUP↔BUP, GTP↔GTP) within radius. **Never a detached house.** | |
| **F3** | Basis = **same-complex, same-bed sale, time-adjusted** — not $/m². Floor area is a secondary adjustment where known or imputed | Reachable on **85.8%** of off-market stock vs 24.3% for a floor-area basis |
| **F4** | Floor-area imputation from same-complex same-bed cohort, labelled derived | Validated: **5.2% median error, 67% within 10%** vs 15.9% / 28% suburb-wide |
| **F5** | Retire for attached: `land_size`, `pool`, `cladding`, `golf_course_backing`, `stories`. Add floor level, aspect, lift, car-space tenure, levy band as they arrive | |
| **F6** | Its own envelope | Attached medians **$980k / $950k / $989k** sit *below* the house $1M floor; reusing it suppresses ~55–62% as `below_design_floor` |
| **F7** | Backtest: `--include-attached --price-filter none --blind-subject`, unit price band. Derive unit `_SUBURB_CALIBRATION` and `_SUBURB_80_BAND` | `--blind-subject` is not optional — off-market attached stock has ~3 photos in total |
| **F8** | Key `ACCURACY` by **(suburb, dwelling_class)**; `v4Eligible()` reads the same key | Otherwise house track record leaks onto unit ranges — which already happened once (19 Manhattan Avenue) |

### Where the method currently stands

Leave-one-out, same-complex same-bedroom, time-adjusted, n=4,093 across 281 cohorts:

| | Unit method | House method (in-envelope) |
|---|---|---|
| Median abs error | **9.07%** | 8.2% |
| MAE | **12.19%** | 10.5% |
| Within 10% | **54.8%** | 59% |
| 80% band | **±19.8%** | ±12.4% |

⚠ **Upper bound, not a publishable figure.** The deflator was the *house* index (the only one that exists —
D1 removes this); only 36% of sales had a deflator; sales from 2005 were deflated forward to 2026. It is
also leave-one-out on a generous cohort, not a production-shaped backtest. **No number reaches a page until
F7 passes.**

**Publish bar:** ≥80% of eventual sale prices inside the published band, on a leakage-free backtest, with
n sufficient per (suburb, class). If a suburb fails, it does not ship — it does not get a wider band.

---

## Workstream G — The page (M3, refined at M4)

| ID | Change |
|---|---|
| **G1** | `copy_units_v4.yaml` — or a `by_dwelling_class:` layer in `load_copy_v4()`. There is **zero** per-type templating today |
| **G2** | Type-scoped scarcity **cohort and denominator** (`scarcity_features.py`) — the source of the live "107 of 233 nearby homes" claim, where 233 is houses |
| **G3** | **Suppress `green_space` for attached.** It classifies "backs onto" from a single geocode; for a 40-unit complex that is the building centroid and the claim can be flatly false |
| **G4** | Replace the cadastral-lot hero — the parcel is the whole scheme. Use complex context (name, scheme size, storeys band) |
| **G5** | Unit buyer archetypes and filter checklist (lift, secure parking, levy band, aspect, floor level) replacing land/yard/single-level |
| **G6** | Type-matched `obvious_comp`; unit-relevant deltas |
| **G7** | `wait_time` — remove "3-bedroom homes on 600m²+ blocks" phrasing for attached |
| **G8** | `meta()` — emit `Apartment` schema type, drop `"Land size"` and `"{n}m² block"` |

---

## Workstream H — Go live (M3 index, M4 figure)

| ID | Change |
|---|---|
| **H1** | Relax the four gates **in lockstep**: `generate-sitemap.mjs`, `off-market.$slug.tsx` `meta()`, `offmarket_discovery_nightly.py`, `batch_value_offmarket.py`. Replace the address-syntax proxy with the real rule — **supported class + sufficient data + resolved identity** |
| **H2** | Extend the `sitemap_robots_invariant` monitor to cover attached before H1 ships | Relaxing any subset reproduces the 2026-08-08 defect (4,559 URLs advertised while serving noindex) |
| **H3** | Staged index: units passing a data-sufficiency bar first, not all ~3,000 at once |
| **H4** | Rollback: `?v4=0` already serves the deck without a deploy. Add a class-level kill switch in the loader |

---

## Decisions needed

**D1 — the ~8,095 existing unit discovery docs. ✅ DECIDED 2026-08-10 (Will): DELETE and rebuild.**
They were built by a house-shaped engine and carry house-shaped claims (the live "space and backyard"
buyer persona). Repairing in place would mean auditing 8,095 documents for claims that were never true.
Rebuild is ~2.1 s/home ≈ 5 hours sharded, and `_needs_build` would re-run them anyway once
`dwelling_class` and valuations change.

**Execution — this is a destructive delete, so it is gated:**
1. Land **A2** first (the address-gap fix), or the nightly rebuilds them within 24h.
2. Snapshot the 8,095 docs to `artifacts/` before deleting — cheap insurance, and the only record of what
   was live.
3. Delete scoped by `classify_dwelling(effective_address) == "attached"`, **not** by the slug regex.
4. Confirm the pages fall back cleanly (they 200 with Part 02 absent — not a 404) before the unit engine
   backfills them.

**D2 — index the no-figure page at M3, or wait for M4?** My recommendation: **index at M3**, staged, for
units meeting a data-sufficiency bar. The sitemap's own comment says the rule is "supported property type +
sufficient data + resolved identity", not "has a valuation". A page with complex context, sale history and
honest refusal is indexable content. Holding it back keeps ~3,000 URLs out of the index for a further
6 weeks for no reader benefit.

**D3 — legal. ✅ PART (a) DECIDED 2026-08-10 (Will): proceed on "publish derived facts, never reproduce
the CMS".** Entitlement shares, lot counts, scheme size and derived levy bands are publishable as facts;
the CMS document itself is never reproduced, quoted at length, or made downloadable. Encode this as a
constraint in the renderer and the page, not as a convention someone has to remember.

**(b) still open — s205(13)(f) agency at volume.** Needed only for Phase 4 (levies). It does **not** gate
M1–M3 or the markdown report. Worth ~30 minutes of a strata lawyer's time before Phase 4 is built, because
the answer changes its economics: if the authority carries only to the instructing owner's lot, "54
engagements covers 50% of stock" becomes "one engagement covers one lot" — a per-customer service rather
than a data multiplier.

---

## Standing obligations (CLAUDE.md)

- **Rule 7 / 7b** — every new ongoing process (B2 maintenance, D1/D3 series, E1/E2 refresh, F backfills)
  wraps `job_run(name, cadence_hours=…, title=…)` **and raises on its zero-output path**. Run once at
  creation; confirm it appears on the Process Registry before calling the task done.
- **Rule 8** — no field name from memory. `db_fields.py --find/--check` first. A zero is a fact about the
  name typed.
- **Rule 6** — after any market-metrics content change, run `verify_market_metrics_live.py` and **read
  every saved file**.
- **Rule 5** — no advice, no predictions, ranges not single figures. A derived levy or an imputed floor
  area is stated as derived, with its method and date.
- **Rule 1** — fix-history entry per change. **Rule 2** — push to GitHub, md5-verify.
- **Website changes** — deploy-tracker log, screenshot, read the PNG, check console + network errors.

## Out of scope

Scraping levies from Domain/REA (their ToU bans *the purpose*; REA sued Domain over 181 listings in
Dec 2024; coverage would be ~0.7–0.9% and biased downward). Buying strata from
CoreLogic/Cotality/PropTrack/Pricefinder — **they do not have it** (Pricefinder's public OpenAPI spec:
`strata`, `bodyCorporate`, `levy`, `sinkingFund` → zero matches). Bulk Form 33 purchase. Waterfront units.
Nerang and other unmeasured suburbs.
