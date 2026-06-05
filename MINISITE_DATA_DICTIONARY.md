# Mini-Site Data Dictionary

**Purpose:** Single source of truth for every dynamic value rendered on a house mini-site
(`/your-home/:slug`, served by `netlify/functions/property-report.mjs` from
`system_monitor.property_reports`). This document is the spec that drives
`scripts/minisite_health_check.py` — when the mini-site changes, update this file and the
checker follows.

**Last updated:** 2026-06-06 (initial build, from live inspection of 18 `under_review` reports).

---

## 1. How mini-site data works (read this first)

Each home is **one document** in `system_monitor.property_reports`, keyed by `slug`.
The `fields-property-report-poller` daemon (15 s loop) resolves a "stub" into a full report
via `scripts/property_reports/slot_resolver.py`. `scripts/refresh_property_reports.py` then
re-runs nightly to keep the *living* parts (comparable feed, activity, messages) current.

### Two tiers of freshness

| Tier | What | Refresh cadence | True freshness signal |
|------|------|-----------------|------------------------|
| **1 — Living** | Comparable feed, activity, messages, `slots.data_pull_date` | **Nightly** (`refresh_property_reports.py`) | timestamp on the report doc itself |
| **2 — Build-time** | Valuation comps, market state, LLM narratives (scarcity/positioning/buyers/market_narrative), POIs, photos/floor-plan/satellite/street-view, case studies | **Once at build**, only re-run on rebuild | the **upstream** source's own timestamp |

> **Critical rule for the checker:** a Tier-2 field can look "fine" on the report (value
> present, slot approved) while the *underlying* data is weeks stale. For Tier-2 fields the
> checker must ALSO look at the upstream source's freshness (see §3), not just the report value.

### Slot gating

Nine slots were designed; **eight exist in live data**. Each has a `slot_status.<slot>` of
`approved` / `pending` / `error`. The frontend shows real content only when `approved`,
otherwise a `PendingPlaceholder`. While a report is `state: under_review`, `pending` is
**normal, not an alarm** — the checker classifies it `PENDING-EXPECTED`.

| Slot | Gates (tab) | Live? | Approved (of 18) |
|------|-------------|-------|------------------|
| `comps` | Valuation | ✅ | 5 |
| `scarcity` | Market | ✅ | 8 |
| `competitor_matches` | Market | ✅ | 12 |
| `market_narrative` | Market | ✅ | 12 |
| `case_studies` | Market | ✅ | 1 |
| `positioning` | Positioning | ✅ | 8 |
| `buyers` | Buyers | ✅ | 8 |
| `walking_distance` | Home (POIs) | ✅ | 15 |
| `seasonality` | Process | ❌ **fixture only** | 0 — not implemented |

---

### Staleness logic for nightly sources (missed-run detection)

For any source that refreshes on the **nightly pipeline** (20:30 AEST), the checker does NOT
use a loose rolling-hours window. It computes the **most recent expected run date** — today's
20:30 AEST if the check runs after 20:30, otherwise yesterday's — and flags `STALE` if the
source's freshness timestamp predates it. This trips the flag the moment a source misses a
single nightly run, rather than waiting a fixed number of hours. The "stale-after" columns
below state the equivalent tolerance (≈1.5 days = one missed run) for reference.

---

## 2. Status taxonomy (what the checker emits per field)

| Status | Meaning |
|--------|---------|
| `OK` | Present, complete, and fresh (within stale-after window). |
| `STALE` | Present but the freshness signal is older than the stale-after threshold. |
| `MISSING` | Required field absent / null / empty when the slot is `approved` (a real defect). |
| `PENDING-EXPECTED` | Field absent but its slot is `pending` and report is `under_review` (normal). |
| `ERROR` | Slot status is `error`, or a value failed a validity rule (e.g. range low > high). |
| `UNKNOWN-FRESHNESS` | Field present but has no timestamp anywhere to judge age (see §6 gaps). |

**Severity for the dashboard:** `ERROR` and `MISSING` (on an approved slot) = red;
`STALE` = amber; `UNKNOWN-FRESHNESS` = grey; `OK` / `PENDING-EXPECTED` = green.

---

## 3. Tier-2 upstream sources (shared data behind many fields)

These are checked **once per run** (not per home) and their status is joined onto every
field that depends on them.

| Upstream source | Collection | Freshness field | Updating process | Cadence | Stale-after |
|-----------------|------------|-----------------|------------------|---------|-------------|
| Indexed prices | `Gold_Coast.precomputed_indexed_prices` (`_id`=suburb) | `last_updated` | proc 17 (`precompute_indexed_price_data.py`) | nightly | **1.5 days** (missed run) |
| Market charts (DOM, volume) | `Gold_Coast.precomputed_market_charts` (`_id`=`{suburb}_{metric}`) | `last_updated` | proc 17 (`precompute_market_charts.py`) | nightly | **1.5 days** (missed run) |
| Active listings | `Gold_Coast.precomputed_active_listings` (`_id`=suburb) | `last_updated` ✅ | proc 19 (`precompute_active_listings.py`) | nightly | **1.5 days** (missed run) |
| Per-property valuation | `Gold_Coast.<suburb>` doc `valuation_data` | `valuation_data.metadata.computed_at` | proc 6 + 18 | nightly | 3 days |
| Sold comps | `Gold_Coast_Recently_Sold.<suburb>`, `Target_Market_Sold_Last_12_Months.<suburb>` | `sold_date` (newest) | proc 103/104/111 | nightly | 14 days* |
| Case study library | `system_monitor.case_study_library` (per `case_id`) | `built_at` ✅ | `build_case_study.py` / `draft_case_analysis.py` | ad-hoc | evergreen (track age) |
| Market pulse | `system_monitor.market_pulse` | `generated_at` | `generate_market_pulse.py` | monthly (25-day guard) | 35 days |

*Sold "stale-after" measures the newest sale ingested for the suburb, not individual comps.

---

## 4. Per-tab field dictionary

Columns: **Field** (UI) · **Doc path** (in `property_reports`) · **Slot** · **Upstream (Tier-2)** ·
**Freshness signal** · **Completeness rule** · **Stale-after**.

### 4.1 Header / Hero (always shown)

| Field | Doc path | Slot | Upstream | Freshness signal | Completeness rule | Stale-after |
|-------|----------|------|----------|------------------|-------------------|-------------|
| Address | `address` | — | — | `updated_at` | non-empty string | — |
| Suburb | `suburb` / `suburb_key` | — | — | — | non-empty | — |
| Lat / Lng | `lat`, `lng` | — | — | — | both numeric, in GC bbox | — |
| Report state | `state` | — | — | `state_transitioned_at.<state>` | in {stub,under_review,final,living} | — |
| Last data pull | `slots.data_pull_date` | — | — | **self** | present datetime | **1.5 days** (missed run) |
| Report updated | `updated_at` | — | — | self | present datetime | 1.5 days (missed run) |

### 4.2 "Your Home" tab

| Field | Doc path | Slot | Upstream | Freshness signal | Completeness rule | Stale-after |
|-------|----------|------|----------|------------------|-------------------|-------------|
| Beds/Baths/Car | `property.bed/bath/car` | — | Gold_Coast property | — | all non-null integers | — |
| Land area | `property.land_area_sqm` | — | Gold_Coast | — | non-null > 0 | — |
| Internal area | `property.internal_area_sqm` | — | Gold_Coast | — | non-null > 0 (warn if null) | — |
| Property type | `property.property_type` | — | Gold_Coast | — | non-empty | — |
| Year built | `property.year_built` | — | Gold_Coast | — | nullable (often null — info only) | — |
| Gallery photos | `property.photos[]` | — | proc 110/112 (blob) | `photos[].meta` present | ≥1 photo, hero role present | — |
| Photo analysis | `property.photo_analysis` | — | proc 105/photo vision | — | `categories` + `metadata` present | — |
| Floor plan image | `property.floor_plan.url` | — | proc 106 | `floor_plan.generated_at` | url present | — |
| Floor plan layout | `property.floor_plan.layout.rooms[]` | — | proc 106/108 | `floor_plan.generated_at` | ≥1 room | — |
| Satellite image | `property.satellite.satellite_image_url` | — | proc 117 | `property.satellite.processed_at` | url present | — |
| Satellite narrative | `property.satellite.narrative.*` | — | proc 117 | `processed_at` | `overall_setting` non-empty | — |
| Street view image | `property.street_view.street_view_image_url` | — | inline resolver | `street_view.processed_at` | url present | — |
| Street view narrative | `property.street_view.narrative.*` | — | inline resolver | `processed_at` | `kerb_summary` non-empty | — |
| POI walking distances | `pois[]` | `walking_distance` | Mapbox lookup | `data_pull_date` | ≥1 POI w/ `walkMetres` | — |

### 4.3 "Valuation" tab

| Field | Doc path | Slot | Upstream | Freshness signal | Completeness rule | Stale-after |
|-------|----------|------|----------|------------------|-------------------|-------------|
| Working range low | `valuation.model_range.low` | `comps` | `valuation_data` (proc 6/18) | `valuation_data.metadata.computed_at` | numeric > 0 | 3 days (upstream) |
| Working range high | `valuation.model_range.high` | `comps` | ↑ | ↑ | numeric > low | 3 days |
| Range method | `valuation.model_range.method` | `comps` | — | — | non-empty | — |
| Comp count (range) | `valuation.model_range.comp_count` | `comps` | sold comps | — | integer ≥ 3 | — |
| Comparable rows | `valuation.comps[]` | `comps` | sold comps | `valuation.comps_resolved_at` | ≥3 comps, each w/ soldPrice+soldDate+address | build-time† |
| Comp adjusted price | `valuation.comps[].adjustedToSubject` | `comps` | ↑ | ↑ | numeric per comp | — |
| Comp weight | `valuation.comps[].weight_pct` | `comps` | ↑ | ↑ | numeric, sum ≈ 100 | — |
| Reconciled valuation | `valuation.reconciled` | `comps` | analyst | — | nullable until analyst sign-off | — |
| Final recommendation | `valuation.recommendation.*` | `comps` | analyst | — | nullable until `final` state | — |

†Comps are resolved at build; the checker judges staleness via the **upstream**
`valuation_data.metadata.computed_at`, and flags if `comps_resolved_at` ≪ newest sold comp.

### 4.4 "The Market" tab

| Field | Doc path | Slot | Upstream | Freshness signal | Completeness rule | Stale-after |
|-------|----------|------|----------|------------------|-------------------|-------------|
| Median DOM | `market.median_dom` | — | `precomputed_market_charts` | `…charts.last_updated` | integer ≥ 0 | 1.5 days (missed run) |
| Median DOM (historical) | `market.median_dom_historical` | — | ↑ | ↑ | integer | 1.5 days |
| DOM YoY change | `market.dom_yoy_change` | — | ↑ | ↑ | integer | 1.5 days |
| Latest median price | `market.latest_median_price` | — | `precomputed_indexed_prices` | `…prices.last_updated` | numeric > 0 | 1.5 days |
| Rolling 12m median | `market.rolling_12m_median` | — | ↑ | ↑ | numeric > 0 | 1.5 days |
| Rolling 12m YoY % | `market.rolling_12m_yoy_pct` | — | ↑ | ↑ | numeric | 1.5 days |
| Growth since baseline % | `market.growth_since_baseline_pct` | — | ↑ | ↑ | numeric | 1.5 days |
| Baseline period | `market.baseline_period` | — | ↑ | ↑ | non-empty | — |
| Sold transaction count | `market.sold_transaction_count` | — | sold data | ↑ | integer > 0 | — |
| **Active listings count** | `market.active_listings_count` | — | `precomputed_active_listings` | `…active_listings.last_updated` ✅ | integer ≥ 0 | **1.5 days** (missed run) |
| Competitor count | `slots.competitor_map.competitors[]` | `competitor_matches` | live scrape (proc 101) | `competitor_map.resolved_at` | ≥1 competitor | 1.5 days |
| Competitor funnel | `slots.competitor_map.ranked_comparison.funnel` | `competitor_matches` | ↑ | `resolved_at` | `active_total`/`in_band` present | 1.5 days |
| Ranked homes | `slots.competitor_map.ranked_comparison.homes[]` | `competitor_matches` | ↑ | `resolved_at` | ≥1 ranked home | 1.5 days |
| Scarcity headline | `scarcity.headline` | `scarcity` | `scarcity_features` | `scarcity.generated_at` | non-empty | build-time |
| Combinatorial match | `scarcity.combinatorialMatch` | `scarcity` | ↑ | ↑ | non-empty | build-time |
| Walking-distance monopoly | `scarcity.walkingDistanceMonopoly` | `scarcity` | ↑ | ↑ | non-empty (nullable) | — |
| Sold-cohort premiums | `scarcity.soldCohortPremiums[]` | `scarcity` | sold data | `scarcity.generated_at` | ≥1 w/ feature+premium | build-time |
| Active listings (scarcity) | `scarcity_features.active_listings_total` | `scarcity` | `precomputed_active_listings` | `…active_listings.last_updated` ✅ | integer > 0 | 1.5 days (missed run) |
| Cohort premium stats | `scarcity_features.cohort_premiums[]` | `scarcity` | sold data | — | each w/ `premium_pct`,`n_with`,`reliable` | — |
| Market narrative | `market_narrative.text` | `market_narrative` | LLM (Opus) | `market_narrative.generated_at` | non-empty, 40–600 chars | build-time |
| Dynamic case study | `case_studies.dynamic.*` | `case_studies` | sold data | `case_studies.dynamic.resolved_at` | address+sale_price+sale_date | 30 days |
| Case study library | (joined from `case_study_library`, published) | `case_studies` | `build_case_study.py` | `case_study_library.built_at` ✅ | ≥1 published case for suburb | evergreen (track age) |

### 4.5 "The Buyers" tab

| Field | Doc path | Slot | Upstream | Freshness signal | Completeness rule | Stale-after |
|-------|----------|------|----------|------------------|-------------------|-------------|
| Thesis headline | `buyers.thesis.headline` | `buyers` | LLM | `buyers.generated_at` | non-empty | build-time |
| Thesis body | `buyers.thesis.body[]` | `buyers` | LLM | ↑ | ≥1 paragraph | build-time |
| Thesis stat blocks | `buyers.thesis.statBlocks[]` | `buyers` | LLM | ↑ | each w/ value+label | — |
| Catchment locations | `buyers.catchment.locations[]` | `buyers` | LLM | ↑ | ≥1 w/ label+share | — |
| Campaign math | `buyers.campaignMath.*` | `buyers` | LLM | ↑ | headline+body+statBlocks | — |

### 4.6 "Positioning" tab

| Field | Doc path | Slot | Upstream | Freshness signal | Completeness rule | Stale-after |
|-------|----------|------|----------|------------------|-------------------|-------------|
| Strategic frame | `positioning.frame.{angle,reasoning}` | `positioning` | LLM | `positioning.generated_at` | both non-empty | build-time |
| Vocabulary palette | `positioning.vocabulary.{use[],avoid[]}` | `positioning` | LLM | ↑ | ≥1 use + ≥1 avoid | — |
| Trade-offs | `positioning.tradeOffs[]` | `positioning` | LLM | ↑ | each w/ apparent+reframe+evidence | — |
| Photography brief | `positioning.photography[]` | `positioning` | LLM | ↑ | ≥3 shots w/ slot+brief | — |
| Sample paragraph | `positioning.sampleParagraph` | `positioning` | LLM | ↑ | non-empty | — |
| Generic paragraph | `positioning.genericParagraph` | `positioning` | LLM | ↑ | non-empty | — |
| Buyer personas | `positioning.personas[]` | `positioning` | LLM | ↑ | exactly/≈3, each w/ label+brief | — |

### 4.7 "The Process" tab

| Field | Doc path | Slot | Upstream | Freshness signal | Completeness rule | Stale-after |
|-------|----------|------|----------|------------------|-------------------|-------------|
| Seasonality calendar | `seasonality.months[]` | `seasonality` | ⚠️ **not implemented** | — | n/a — fixture placeholder | KNOWN-GAP |
| Seller saved answers | `selling_plan.answers.*` | — | seller form (`property-plan-submit.mjs`) | `answers.*.updatedAt` | per-report, optional | — |

### 4.8 "Messages" tab + activity (living)

| Field | Doc path | Slot | Upstream | Freshness signal | Completeness rule | Stale-after |
|-------|----------|------|----------|------------------|-------------------|-------------|
| Activity feed | `activity[]` | — | refresh job | `activity_refreshed_at` | ≥1 item | 1.5 days (missed run) |
| Comparable events | `comparable_events[]` | — | refresh job | event `.ts` (newest) | — | 1.5 days |
| Comparable state | `comparable_state.<url>` | — | refresh job | `.last_seen` (newest) | — | 1.5 days (missed run) |
| Closest active/sold | `comparables.closest_active/sold[]` | — | refresh job | `comparables.generated_at` / `comparables_refreshed_at` | — | 1.5 days (missed run) |
| Messages | `messages[]` | — | refresh job | `messages_refreshed_at` | — | — |

---

## 5. Build / health metadata (per report, for the dashboard)

| Field | Doc path | Use |
|-------|----------|-----|
| Build state | `build_state` | should be `complete` |
| Build events | `build_events[]` | look for any `phase: error` |
| Last build event | `last_build_event_at` | build recency |
| Slot status map | `slot_status.*` | count approved / pending / error |
| Owner visits | `owner.visit_count`, `owner.last_visit_at` | engagement context (not health) |
| Print appraisal | `print_appraisal.*` | dispatch tracking (separate workflow) |

---

## 6. Known gaps (decided handling)

1. **`seasonality` slot** — designed but not implemented in live reports; Process-tab calendar
   is illustrative placeholder. Checker reports `KNOWN-GAP`, not an error. Revisit when a real
   `seasonality_analysis` resolver ships.
2. **`property.year_built` frequently null** — informational only; warn, don't fail.
3. **Tier-2 narrative slots don't regenerate nightly** — `generated_at` will naturally age.
   The checker does NOT flag these as STALE on clock age alone; it flags only if the upstream
   market/valuation data moved materially after the narrative was generated (drift check, v2).

> **Resolved during build:** `precomputed_active_listings` (`last_updated` ✅) and
> `case_study_library` (`built_at` ✅) both carry timestamps — they are fully tracked, not
> blind spots. No `UNKNOWN-FRESHNESS` fields remain for active listings or case studies.

---

## 7. Snapshot history (for "date last changed")

Each run writes a per-field snapshot to `system_monitor.minisite_health_snapshots`
(`{slug, run_at, fields: {<doc_path>: {value_hash, status, last_changed}}}`). On each run the
checker compares the current value hash to the previous snapshot; if unchanged, `last_changed`
carries forward; if changed, it stamps the new `run_at`. This populates the "date last changed"
column and surfaces **silently frozen** Tier-2 data (value never moving across many rebuilds).
