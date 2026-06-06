# Main Site Data Dictionary

**Purpose:** Single source of truth for every dynamic data point rendered on the **main
website** (`https://fieldsestate.com.au`) — News, Market Intelligence, For Sale / Sold,
Property pages, Articles, Valuation Accuracy, Discover / Decision Feed. This document is the
spec that drives `scripts/main_site_health_check.py`; when the site's data sources change,
update this file and the checker follows.

**Scope:** Main-site public pages only. The house **mini-site** (`/your-home/:slug`, served by
`property-report.mjs` from `system_monitor.property_reports`) is documented separately in
`MINISITE_DATA_DICTIONARY.md` and audited by `scripts/minisite_health_check.py`. The `/ops`
admin dashboard internals are out of scope.

**Last updated:** 2026-06-06 (initial build, from live inspection of the website Netlify
functions + the Cosmos collections they read).

---

## 1. How main-site data works (read this first)

Unlike the mini-site (one document per home), the main site reads a **fixed catalogue of
shared data sources**. Each public page calls one or more Netlify functions
(`netlify/functions/*.mjs`), which read MongoDB collections. The checker audits those
collections directly — grouped by the **page** that consumes them — rather than per-document.

### Three tiers of freshness

| Tier | What | Refresh | True freshness signal |
|------|------|---------|------------------------|
| **1 — Precomputed (nightly)** | Indexed prices, market charts (DOM / sales volume / turnover / cycle), active-listing snapshots, per-property valuations | **Nightly** via the 20:30 AEST pipeline (procs 17 / 18 / 19) | the collection's own `last_updated` / `computed_at` |
| **2 — Periodic feeds** | Asking $/sqm (weekly), market signals (weekly), market pulse (monthly), macro indicators (intended monthly), absorption rate (weekly), valuation-accuracy backtest (intended monthly) | **Weekly / monthly** (separate crons / GitHub Actions) | the doc's `last_updated` / `updated_at` / `generated_at` / `run_date` / `computed_at` |
| **3 — Build-time / request-time (blind)** | Articles (`articles.json` baked at deploy), decision-feed / discover / property-insights / active-competition (computed live per request), `/data/forecast_*.json`, hardcoded `CrashRiskSection.tsx` claims | **At build or per request** — no real data-age signal | tracked as **KNOWN-GAP** (see §6) |

> **Critical rule for the checker:** a Tier-3 endpoint can return HTTP 200 with a fresh-looking
> `last_updated` that is actually *request time*, not data-computation time. The checker does NOT
> trust those; it judges Tier-3 against the underlying suburb-collection scrape, or flags
> KNOWN-GAP, never a false OK.

### Staleness logic for nightly sources (missed-run detection)

For Tier-1 sources the checker computes the **most recent expected nightly run** — today's
20:30 AEST if the check runs after 20:30, otherwise yesterday's — and flags `STALE` the moment
a source's freshness timestamp predates it (one missed run). This is the same
`expected_last_run()` logic used by the mini-site checker (`AEST = Australia/Brisbane`, no DST).
Tier-2 periodic sources are judged on **clock age in days** against a per-source threshold.

### Suburb scope

Tier-1 per-suburb sources are checked for the **6 target-market suburbs** (`config/settings.yaml`
`target_market.suburbs`): **Robina, Varsity Lakes, Burleigh Waters, Mudgeeraba, Reedy Creek,
Worongary**. Some Tier-2 feeds only exist for the **3 core suburbs** (Robina, Burleigh Waters,
Varsity Lakes) — asking $/sqm, market pulse, absorption — and are checked for those only.
Per the documented coverage priority, non-core gaps are not treated as failures.

---

## 2. Status taxonomy (what the checker emits per data point)

| Status | Meaning |
|--------|---------|
| `OK` | Present, complete, and fresh (within its stale-after window). |
| `STALE` | Present but the freshness signal is older than the threshold (missed nightly run, or > N days). |
| `MISSING` | Required source doc absent / empty (a real defect). |
| `ERROR` | A value failed a validity rule (e.g. `failed_factcheck` count > 0, range low > high). |
| `UNKNOWN-FRESHNESS` | Data present but no timestamp anywhere to judge age. |
| `KNOWN-GAP` | Structurally un-trackable (build-time / request-time); documented, not an alarm. |

**Severity (dashboard colour):** `ERROR` / `MISSING` = red · `STALE` = amber ·
`UNKNOWN-FRESHNESS` = blue-grey · `KNOWN-GAP` = light grey · `OK` = green.
`health_pct` per page = `OK / (all rows excluding info + KNOWN-GAP)`.

---

## 3. Per-page field dictionary

Columns: **Data point** (UI) · **Page / route** · **Netlify function** · **DB.collection** ·
**Source field(s)** · **Freshness signal** · **Cadence** · **Stale-after** · **Completeness rule**.

### 3.1 Market Intelligence — `/market-metrics/:suburb` (nav "Market Intelligence")

The most data-dense page. SSR (`src/lib/db.server.ts`) and `market-insights.mjs` /
`market-narrative.mjs` read the same precomputed collections.

| Data point | Function | DB.collection (`_id`) | Source field(s) | Freshness signal | Cadence | Stale-after | Rule |
|---|---|---|---|---|---|---|---|
| Indexed prices / median / rolling-12m / YoY / growth | market-insights, market-narrative | `Gold_Coast.precomputed_indexed_prices` (`{suburb}`) | `indexed_series`, `latest_price`, `rolling_12m_yoy_pct`, `total_growth_pct`, `baseline_period` | `last_updated` | nightly | 1 missed run | doc present, `last_updated` ts |
| Days-on-market chart | market-narrative `/charts/days-on-market` | `Gold_Coast.precomputed_market_charts` (`{suburb}_days_on_market`) | chart series, `latest_quarter_median` | `last_updated` | nightly | 1 missed run | doc present |
| Sales-volume chart | market-narrative `/charts/sales-volume` | `Gold_Coast.precomputed_market_charts` (`{suburb}_sales_volume`) | chart series | `last_updated` | nightly | 1 missed run | doc present |
| Turnover-rate chart | market-narrative `/charts/turnover-rate` | `Gold_Coast.precomputed_market_charts` (`{suburb}_turnover_rate`) | chart series | `last_updated` | nightly | 1 missed run | doc present |
| Market-cycle chart | market-narrative | `Gold_Coast.precomputed_market_charts` (`{suburb}_market_cycle`) | chart series | `last_updated` | nightly | 1 missed run | doc present |
| Active listings (count + history) | market-insights / SSR | `Gold_Coast.precomputed_active_listings` (`{suburb}`) | `snapshots[]` | `last_updated` | nightly | 1 missed run | `snapshots` ≥ 1 |
| Asking $/sqm | market-insights (AskingPriceChart) | `Gold_Coast.sqm_asking_prices` (`{suburb}`, core 3 only) | `series`, `date_range_end` | `last_updated` | weekly | 10 days | doc present |
| Crash-risk macro (RBA cash/mortgage, Brent oil, national house/asking index, mortgage impact) | macro-indicators | `Gold_Coast.precomputed_macro_indicators` (`macro_indicators`) | `rba_cash_rate_quarterly`, `rba_mortgage_rate_quarterly`, `brent_crude_*`, `national_house_price_index`, `national_asking_prices`, `mortgage_impact` | `updated_at` | monthly | 35 days | doc present |
| Market signals (wage index, retail spend) | market-signals | `system_monitor.market_signals` (`market_signals_latest`) | `suburbs[].signals[]`, `raw_indicators[].timeseries`, `latest_quarter_label` | `updated_at` | weekly | 10 days | doc present |
| Market Pulse narratives (per category) | market-pulse | `system_monitor.market_pulse` (`{suburb, category}`, core 3) | `category_title`, `summary`, `verdict`, `key_signals`, `data_snapshot` | `generated_at` | monthly | 40 days | ≥ 1 doc per suburb |
| Absorption rate (months of supply) | market-insights | `system_monitor.absorption_rate_snapshots` (`{suburb}_{YYYY-MM}`, core 3) | `absorption_rate_months`, `active_count`, `sold_count_30d` | `computed_at` | weekly | 10 days | newest doc per suburb |
| Price forecast (4q + 90% CI) | static | `/data/forecast_<suburb>.json` (build artifact) | forecast series | **none in payload** | build-time | — | **KNOWN-GAP** |
| Crash-risk narrative claims | n/a | hardcoded in `CrashRiskSection.tsx` | — | **none** | manual | — | **KNOWN-GAP** |

### 3.2 For Sale / Sold — `/for-sale`, `/recently-sold`

| Data point | Function | DB.collection | Source field(s) | Freshness signal | Cadence | Stale-after | Rule |
|---|---|---|---|---|---|---|---|
| Active listing cards | properties-for-sale | `Gold_Coast.<suburb>` `{listing_status:'for_sale'}` | `address`, `price`, `bedrooms`, `bathrooms`, `car_spaces`, `land_size`, `property_images`, `days_on_market`, `agent_name`, `description` | newest doc `last_updated` | nightly | 1 missed run | count ≥ 1, fresh `last_updated` |
| Recently-sold cards | recently-sold | `Gold_Coast.<suburb>` `{listing_status:'sold'}` | `sold_price`, `sold_date`, `days_on_market`, timeline | newest `sold_date` | sold-flow | 14 days | newest `sold_date` |

### 3.3 Property Page — `/property/:id`, `/sold/:id`

| Data point | Function | DB.collection | Source field(s) | Freshness signal | Cadence | Stale-after | Rule |
|---|---|---|---|---|---|---|---|
| Reconciled valuation + range | property, valuation | `Gold_Coast.<suburb>` `{listing_status:'for_sale'}` | `valuation_data.confidence.reconciled_valuation`, `valuation_data.summary`, `valuation_data.comparables` | `valuation_data.computed_at` (newest) + coverage % | nightly | 3 days | coverage of for-sale, fresh `computed_at` |
| AI property editorial | property, properties-for-sale | `Gold_Coast.<suburb>` `{listing_status:'for_sale'}` | `ai_analysis.status` (published / draft / needs_review / failed_factcheck / rejected), `ai_analysis.generated_at` | `ai_analysis.generated_at` | ad-hoc | info | flag `failed_factcheck`/`rejected` > 0 = ERROR |
| Property insights (percentiles, scarcity, positioning) | property-insights | `Gold_Coast.<suburb>` (live aggregate) | computed per request | `computed_at` = **request time** | request | — | **KNOWN-GAP** (tied to scrape) |
| Active competition (comparable live listings) | active-competition | `Gold_Coast.<suburb>` (live query) | comparable for-sale rows | **none** | request | — | **KNOWN-GAP** (tied to scrape) |

### 3.4 Articles — `/` (News), `/articles/:slug`, `/market-intelligence/:suburb`

| Data point | Function | DB.collection | Source field(s) | Freshness signal | Cadence | Stale-after | Rule |
|---|---|---|---|---|---|---|---|
| Published-article cadence | none (`articles.json` baked at build by `fetch-articles.js`) | `system_monitor.content_articles` `{status:'published'}` | `title`, `slug`, `html`, `tags`, `published_at` | newest `published_at` | weekly | 10 days | newest `published_at` |
| Published / draft counts | — | `system_monitor.content_articles` | `status` | — | — | info | counts (draft backlog context) |
| Build artifact (`articles.json`) | fetch-articles.js | (deploy artifact) | `lastUpdated` | deploy time | per-deploy | — | **KNOWN-GAP** (decoupled from DB write) |

> Articles are auto-generated by **14 GitHub Actions workflows** in `Will954633/fields-automation`
> (~8–10 article-producing runs/week, mostly Sunday/Monday AEST). A healthy site publishes
> multiple articles per week, so a 10-day gap in `published_at` indicates the workflows have
> stopped succeeding.

### 3.5 Valuation Accuracy — `/valuation-accuracy`

| Data point | Function | DB.collection | Source field(s) | Freshness signal | Cadence | Stale-after | Rule |
|---|---|---|---|---|---|---|---|
| Backtest summary (error metrics, by-suburb / price-band / confidence, Domain benchmark) | valuation-accuracy | `system_monitor.valuation_accuracy` `{type:'summary'}` | `metrics`, `by_suburb`, `by_price_band`, `by_confidence`, `domain_benchmark`, `model_updates` | `run_date` | monthly | 40 days | doc present, fresh `run_date` |

### 3.6 Discover / Decision Feed — `/discover`, `/for-sale-v2`, V3

| Data point | Function | DB.collection | Source field(s) | Freshness signal | Cadence | Stale-after | Rule |
|---|---|---|---|---|---|---|---|
| Curated / mixed property feed | discover-feed, decision-feed, decision-feed-v3 | `Gold_Coast.<suburb>` | property card fields + derived `classification` | response `last_updated` = **request time** | request | — | **KNOWN-GAP** (real freshness = suburb scrape) |

### 3.7 Static pages (no dynamic data)

`/why-fields`, `/about`, `/compare`, `/disclaimer`, `/analyse-your-home` landing,
`/how-to-value`, `/methodology`. No freshness concern — not checked.

---

## 4. Tier-1/2 source → updating process (provenance)

| Source collection | Freshness field | Updating process | Schedule |
|---|---|---|---|
| `precomputed_indexed_prices` | `last_updated` | proc 17 `precompute_indexed_price_data.py` | nightly (in pipeline) |
| `precomputed_market_charts` | `last_updated` | proc 17 `precompute_market_charts.py` | nightly |
| `precomputed_active_listings` | `last_updated` | proc 19 `precompute_active_listings.py` | nightly |
| `<suburb>.valuation_data` | `valuation_data.computed_at` | proc 18 `precompute_valuations.py` | nightly |
| `sqm_asking_prices` | `last_updated` | asking-price collector | weekly |
| `precomputed_macro_indicators` | `updated_at` | `scripts/fetch_macro_indicators.py` | monthly (intended) |
| `market_signals` | `updated_at` | `scripts/fetch_abs_market_signals.py` | weekly |
| `market_pulse` | `generated_at` | `generate_market_pulse.py` / manual | monthly |
| `absorption_rate_snapshots` | `computed_at` | absorption collector | weekly |
| `valuation_accuracy` | `run_date` | `scripts/valuation_backtest.py` | monthly (intended) |
| `content_articles` | `published_at` | `Will954633/fields-automation` GitHub Actions | weekly+ |
| `<suburb>.ai_analysis` | `ai_analysis.generated_at` | `generate_property_ai_analysis.py` | ad-hoc |

---

## 5. Health / snapshot metadata

Each run writes a per-data-point snapshot to **`system_monitor.mainsite_health_snapshots`**
(`{run_at, overall_health_pct, counts, pages:{...}, fields:{"<page>::<name>::<scope>":
{value_hash, status, last_changed}}}`). On each run the checker compares the current value
hash to the previous snapshot; if unchanged, `last_changed` carries forward; if changed, it
stamps the new `run_at`. This populates the "date last changed" column and surfaces **silently
frozen** feeds (value never moving across many runs even though the source claims to refresh).

---

## 6. Known gaps (decided handling)

1. **Articles `articles.json`** — build-time artifact; a published/edited article only appears
   after a Netlify rebuild, and the build silently falls back to last-known-good if the DB fetch
   fails. The checker tracks the **DB** `published_at` cadence (the real signal), and marks the
   build artifact itself KNOWN-GAP.
2. **Decision-feed / discover / property-insights / active-competition** — `last_updated` /
   `computed_at` in the response is **request time**, not data age. Tracked KNOWN-GAP; their true
   freshness is the underlying `Gold_Coast.<suburb>` scrape (covered by §3.2).
3. **`/data/forecast_*.json`** — no `computed_at` inside the payload; only the file's build date.
   KNOWN-GAP.
4. **`CrashRiskSection.tsx` hardcoded claims** — no timestamp, manual update only (already in the
   CLAUDE.md monthly checks). KNOWN-GAP.
5. **`worongary_market_cycle`** was observed stale (2026-04-06) while the other Worongary charts
   refreshed nightly — the per-chart granularity of the checker catches exactly this.
