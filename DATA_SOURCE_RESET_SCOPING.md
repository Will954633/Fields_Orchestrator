# Data-Source Reset — Scoping

**Date:** 2026-07-27 · **Status:** scoping only, nothing shipped · **Owner decision required (see §7)**

## 0. The problem in one line
Our sold-sales data is scraped from Domain **listings**, which structurally miss off-market/private/agent-direct sales. We capture ~50–60% of actual house sales (PropRadar cross-check: Varsity 205 vs our ~105; Burleigh 240 vs our ~145 — ~2× undercount in both, i.e. structural, not noise).

**What's wrong:** sales **VOLUME** (undercounted ~2×) and **MONTHS OF SUPPLY / absorption** (overstated ~2×, because it's `active ÷ sold-rate` and the sold-rate is the undercounted number — this manufactures false "softening/oversupply").
**What's fine (keep):** days-on-market, price growth, median price, and **active-listing inventory** (we capture live Domain *listings* fully — only the *sold* side is undercounted).

The critical asymmetry: **the undercount is on the SOLD side only.** Active-listing counts (the numerator of months-of-supply) are reliable. So the migration only needs a better SOLD source — everything else stays ours.

---

## 1. Every surface that displays the broken metrics

All volume/supply figures on every public surface resolve to Domain-scraped **sold** events in `Gold_Coast.<suburb>` (`scraped_data.property_timeline[].is_sold` and/or `listing_status:"sold"`), plus the sold mirror `Target_Market_Sold_Last_12_Months.<suburb>`.

| # | Surface | Metric shown | Reads from |
|---|---------|--------------|-----------|
| A | `/market-metrics/:suburb` — Sales Volume chart | quarterly bars | `precomputed_market_charts._id="<s>_sales_volume".timeline[].sales_count` |
| A | `/market-metrics/:suburb` — Absorption / Months of Supply chart | months of supply | `absorption_rate_snapshots` (30-day sold window), else live `countDocuments` |
| A | `/market-metrics` — stat tiles + AI verdict (SellNow/Overview/Buy/Direction) | volume + absorption, "seller's/buyer's market" | `market_pulse.data_snapshot.{sales_volume_*, absorption_rate_months}` |
| B | `/market-intelligence/:suburb` (News) — Data Insights ticker | "Sales Volume" tile | `precomputed_indexed_prices.indexed_series[].transaction_count` |
| C | `/off-market/:addr?arm=dark` deck — Sales Volume chart | quarterly bars | same `precomputed_market_charts` `_sales_volume` doc |
| C | off-market deck — pulse prose cards | "absorption/months of supply/volume" *as text* | `market_pulse.key_signals` + `data_snapshot` |
| C | off-market deck — "homes for sale now" tile | inventory | `precomputed_active_listings` (**reliable — active listings, not sold**) |
| D | Article generator (`fields-automation`) | "X sales in 12 months", "N months of supply", softening/tight-market prose | `run_market_monitor.py::extract_suburb_metrics` → LLM writer |

Note: months-of-supply is **NOT** passed to the off-market deck as a number (the loader omits it) — on the deck it only appears inside AI pulse prose. On `/market-metrics` it appears as both chart and number.

There are **three independent, already-disagreeing volume numbers** (`precomputed_market_charts.sales_count`, `precomputed_indexed_prices.transaction_count`, and absorption's live `sold_count_30d`) — the codebase itself flags the divergence (25 vs 30, Robina Q2). All three inherit the undercount.

---

## 2. The writers to repoint (serving layer stays untouched)

The website functions and React components are **pure readers** of precompute collections. We do **not** touch the serving path. We repoint the ~5 **writers** that compute the biased numbers:

| # | Writer | Repo | Output | Absorption window |
|---|--------|------|--------|-------------------|
| W1 | `precompute_market_charts.py::calculate_sales_volume_data` (147-227, 796-872) | `Feilds_Website/08_Market_Narrative_Engine` | `precomputed_market_charts._sales_volume` | — |
| W2 | `precompute_indexed_price_data.py` | `Feilds_Website/08_Market_Narrative_Engine` | `precomputed_indexed_prices.transaction_count` | — |
| W3 | `generate_market_pulse.py` (229-240) + `manual_market_pulse.py` | `Fields_Orchestrator/scripts` | `market_pulse.data_snapshot` + AI `key_signals` | 90-day |
| W4 | `market-insights.mjs` (412-429) writer + `refresh_absorption_snapshots.py` invalidator | Website / Orchestrator | `absorption_rate_snapshots` | 30-day |
| W5 | `run_market_monitor.py::extract_suburb_metrics` (305-406) | `fields-automation` | article delta JSON | 12-month |

Four different sold-count computations across three repos with **three different time windows** (30/90/365-day) — this fragmentation is itself part of the problem and should collapse to one shared helper.

---

## 3. What PropRadar can and cannot give us (the binding constraint)

| Field we need | Source | Tier gate |
|---|---|---|
| 12-month sales volume, inventory-months (≈ months of supply), DOM, heat — **per-suburb snapshot** | `market_dynamics` on `GET /suburbs/QLD/{s}` | **Free** ✅ |
| Rich `supply_demand` object | `/suburbs/QLD/{s}` | Pro+ ($399/mo) |
| **Historical time-series** (`price_history`, `heat_history`, `market_cycle`) | per-suburb | Pro+ ($399/mo) |
| Sold comparables feed | `/comparables` | Hobby+ ($49/mo) |

API pricing (AUD/mo): Free $0 (50 calls) · Hobby $49 (5k) · Starter $99 (20k) · **Pro $399 (100k)** · Growth $799.

**Two decisive facts:**
1. **The Free-tier snapshot already contains exactly what fixes the dangerous claims** — `house_sales_12mo` and `house_inventory_months`. Confirmed live 2026-07-27. Suburb stats refresh fortnightly, so weekly pulls of 3 core suburbs = ~12 calls/mo — **fits inside the Free tier.**
2. **PropRadar has no documented quarterly sold-VOLUME history endpoint.** `price_history` = price/rent/yield; `heat_history` = heat; `market_cycle` = phase label. None is a volume series. So PropRadar is a **snapshot** source, not a historical-volume source. This splits the reset in two (below).

The "free government fallback" (QLD Valuer-General) is weaker than it sounds: land *valuations* are open data, but transaction-level *sales* (QVAS) is a paid broker product, not a free API. Not a drop-in replacement.

---

## 4. The reset splits cleanly into two problems

### Problem 1 — Current headline metrics (the dangerous ones) → **PropRadar snapshot. Cheap. Do first.**
The claims that can mislead a life-changing decision are the *current* ones: "N sales in the last 12 months", "X months of supply", "market is softening/oversupplied". All of these are single current numbers, and PropRadar's Free snapshot gives correct values for all of them.

**Approach:** nightly/weekly job pulls `GET /suburbs/QLD/{s}` per suburb → store in a new collection `Gold_Coast.propradar_suburb_snapshot` (respecting their cache/90-day terms). Then W3/W4/W5 (and the headline fields W1 writes) source the 12-month volume and months-of-supply from that snapshot instead of the scraped sold count. Active-listing inventory stays ours.

### Problem 2 — Historical quarterly volume chart → **our own timelines are the source of truth; expand coverage. Decide (§7).**

**Mechanism (corrected 2026-07-27 after Will's steer — do NOT re-derive the old way):** our historical sold data comes from `scraped_data.property_timeline` — the **authoritative** Domain property-profile transaction history (per `reconcile_sold_against_timeline.py`), NOT from detecting a live listing going sold (`listing_status:"sold"` is the *unreliable* path — see the 64 Parnell rental-as-sale bug). A property-timeline is **persistent**: one profile scrape yields *all* of that property's sales across many years, including private-treaty/off-market sales (`is_sold=true`).

So the undercount is a **property-coverage** problem (which properties' profiles we've ever scraped — `enrich_cadastral.py` only touches parcels that already have `scraped_data`), NOT a per-quarter "listings age out" effect. That makes it **~time-uniform**, except the most recent 1–2 quarters lag (fresh sales not yet in timelines + the historically-broken `refresh_property_timelines` cron). Earlier "older quarters captured worse → fabricated upward trend" reasoning was WRONG.

**Key consequence:** PropRadar has **no volume-history endpoint at any tier**, so it can never be the source of truth for the historical series. Our property timelines already can be — the gap is purely coverage. Options:
- **(A) Expand our own timeline coverage (real fix, recommended).** Scrape property-profile pages across the broader cadastral universe (we have the ~40K addresses + `domain_profile_scraper.py` + Bright Data path). Recovers missing historical sales from the authoritative source. **PropRadar = calibration benchmark** (did coverage close the gap to `house_sales_12mo`?), not the historical source. Self-owned, settlement-grade, no Pro tier. Cost: one-off Bright Data scrape + ongoing refresh.
- **(B) Interim recalibration** — flat PropRadar-anchored factor for the *level* (now defensible since undercount is ~uniform), labelled "adjusted", until (A) lands.
- **(C) Interim suppress** — pull the trend chart, lead with DOM + median, until (A) lands.

Recommendation: **(A) as the durable fix**, with **(B) or (C) as the interim trend-chart treatment**. The PropRadar *snapshot* still fixes the CURRENT headline number immediately regardless (Problem 1).

---

## 5. Target architecture

```
PropRadar /suburbs/QLD/{s}  ──weekly──▶  Gold_Coast.propradar_suburb_snapshot
  (house_sales_12mo,                       {suburb, house_sales_12mo,
   house_inventory_months,                  house_inventory_months, dom,
   dom, heat, fetched_at)                   heat, fetched_at, source:"propradar"}
                                                   │
                        ┌──────────────────────────┼───────────────────────────┐
                        ▼                           ▼                           ▼
        W3 generate_market_pulse      W4 absorption_snapshots        W5 run_market_monitor
        (volume + months-supply         (months-supply from            (sales_volume_trailing12
         from snapshot)                  snapshot, retire 30d count)     + months_of_supply
                        │                           │                    from snapshot)
                        ▼                           ▼                           ▼
        market_pulse.data_snapshot   absorption_rate_snapshots        article delta JSON
                        └───────────── serving layer UNCHANGED ────────────────┘

Active-listing inventory  ──stays ours──▶  precomputed_active_listings (reliable)
Historical volume chart   ──Problem 2──▶  recalibrate OR suppress (decision §7)
```

One shared sold-metrics helper replaces the three divergent 30/90/365-day counts.

---

## 6. Phased plan

- **Phase 0 — calibrate (½ day, ~3 API calls):** one `/suburbs` call per core suburb → capture-ratio table (ours vs PropRadar) for Robina/Burleigh/Varsity. Robina not yet snapshotted; this is the baseline for both the override and the recalibration factor. *(Cheap first move the handoff flagged.)*
- **Phase 1 — snapshot ingest (1 day):** `scripts/fetch_propradar_snapshots.py` (fortnightly/weekly cron, 3 core suburbs) → `propradar_suburb_snapshot`, append-only history. Rate-limit aware, caches, logs `x-ratelimit-remaining`. **Doubles as the forward-accumulating volume series** that later rebuilds an honest trend chart.
- **Phase 2 — repoint headline writers (2–3 days):** W3, W4, W5 + the headline volume field in W1 read the snapshot; collapse the 3 sold-count paths into one helper; retire the live absorption `countDocuments`. Re-run pulse + verify per CLAUDE.md §6 (live-render check).
- **Phase 3 — suppress historical volume trend chart:** remove the volume time-series bars from `/market-metrics` + off-market deck; publish the single PropRadar 12-month figure; lead trend narrative with DOM + median. (Trend chart returns for free once Phase-1 snapshots accumulate ~6–12mo.)
- **Phase 4 — article generator + re-run:** repoint `run_market_monitor.py::extract_suburb_metrics` to the snapshot; commit/push the staged `run_market_insight.py` `sales_count`/`is_in_progress` fix (currently local-only — **CI runs the old code**); **then trigger a fresh generation pass on corrected data** (per decision 7.4).
- **Phase 5 — cleanup:** remove/relabel any remaining raw-volume displays; add "source: PropRadar (settlement-based)" attribution; confirm ToS §8A permits public display.

---

## 7. Decisions (resolved with Will 2026-07-27)
1. **PropRadar tier** — ✅ **Free/Hobby, defer Pro.** Pro only buys history/`supply_demand`; PropRadar has no volume history, so Pro is not worth it.
2. **Historical volume chart** — 🔄 **REOPENED after Will's steer.** Historical sold data comes from our own authoritative `property_timeline`, and the undercount is a property-*coverage* problem (~time-uniform), not the age-out effect I first assumed. PropRadar has no volume-history endpoint, so it can't be the historical source of truth — our timelines can, once coverage is expanded. Direction: **(A) expand timeline coverage across the cadastral universe** as the durable fix (PropRadar = benchmark), with **(B) recalibrate or (C) suppress** as the interim trend-chart treatment until (A) lands. *Awaiting Will's pick of interim + go-ahead to measure the coverage gap (Phase 0 extended).* Current-headline fix (Problem 1 / PropRadar snapshot) proceeds regardless.
3. **Suburb scope** — ✅ **Core suburbs only** (Robina, Burleigh Waters, Varsity Lakes). ~12 calls/mo, inside Free tier.
4. **Sequencing** — ✅ **Fix the data source first (Phases 1–2), then re-run article generation** so the LLM selector/writer triggers evaluate against corrected numbers. Killed Varsity draft stays killed; nothing regenerates until the source is right.

## 9. Empirical validation (2026-07-27) — PropRadar → our DB, Robina probe
- **Auth/transport:** `X-API-Key` header works, but the API is behind Cloudflare — default `urllib` UA gets **403 error 1010**; a browser User-Agent header fixes it (same class as the ABS UA fix). Base `https://api.propradar.com.au/v1`.
- **`/suburbs/QLD/{s}/sold` shape:** envelope `{state, suburb, query, sold[], pagination}`; each record `{property_id (8-hex), address, bedrooms, bathrooms, parking, property_type, sold_price, sold_date}`. Cursor pagination, 20/page.
- **Free-tier window (empirical):** `months=60` is NOT honored on Free — returned only the recent ~4 months (Robina: 113 records, 2026-03-09→07-16). So Free = recent rolling window; **5yr backfill needs Hobby ($49)**, ongoing monthly top-ups fit Free. ~6 calls per suburb per pull.
- **Address match (Robina, first pass):** **103/113 = 91%** on normalized address alone. Normalizer: strip locality tail only (preserve suburb-name-in-street like "Robina Town Centre Drive"), expand street-type abbrevs (Crt→Court), keep unit `/` and number ranges `37-45`. The 10 misses are **real coverage gaps** (addresses PropRadar has, we never captured — mostly high-unit apartments) — i.e. the under-capture made visible, not matcher error.
- **Our address data caveats:** `robina` has 12,086 docs but only 7,883 have an address, 7,062 have a timeline; sold docs can have an empty street (`", Robina, QLD 4226"`); 7,883 addresses → 7,598 distinct normalized keys (**284 collisions** = duplicate/twin docs to resolve before id-write).
- **Field plan:** add `propradar_property_id` (join key) to matched property docs; keep sold records in a separate `propradar_sold` source-of-truth collection (don't bloat property docs). Robina sample verified by Will 2026-07-27.

### 9b. DECISIVE: PropRadar is recent-complete, NOT deep-history (2026-07-27, Hobby live)
Empirically, across ALL endpoints PropRadar only serves a recent window; it is NOT a historical archive:
- `/suburbs/{s}/sold`: recent ~4mo (~113 Robina), same on Free and Hobby, cursor AND offset exhaust ~113.
- `/comparables` (Hobby): recent ~4.5mo (~157), 40/157 null price, spills across postcodes.
- `/properties/{id}/history`: ~1 recent event on properties tested.
- `/properties/search` on a 30-yr-established house → **not found**; our own `property_timeline` for it has 6 sales back to **1991**.
**Conclusion — source of truth splits by TIME, not just metric:**
- **Recent volume + months-of-supply** (the dangerous current claims) → **PropRadar recent feed** (complete, catches off-market). Fixes Problem 1 now, ~6 calls/suburb/mo.
- **Deep history** → **our own `property_timeline`** (richer than PropRadar; PropRadar can't help). Undercount = coverage problem, fixed by expanding our Domain profile-scrape.
- **Coverage gaps** → PropRadar = discovery (which addresses we lack); OUR Domain scraper = fills their full history + enrichment for the off-market page. The "5yr PropRadar backfill" idea is DEAD (our data does it better).
**Robina run COMPLETE & verified:** propradar_sold=113; propradar_property_id written to 103 docs; propradar_coverage_gaps=10 pending. All additive, no existing data touched.

### 9a. Pipeline built (`scripts/propradar/`) — validated, gated on Hobby key
- `propradar_client.py` (browser-UA, rate-limit-aware cursor paginate), `ingest_sold.py` (→ `propradar_sold`, upsert by `property_id_sold_date`), `addr_match.py` (shared normaliser), `link_property_ids.py` (collision-resolve → write `propradar_property_id` → emit `propradar_coverage_gaps` worklist). Production matcher reproduces 91% on Robina.
- **BLOCKER:** the API key still reports `x-api-plan: free`, `x-ratelimit-limit: 50`. Will's Hobby upgrade has not propagated to this key — likely needs a **regenerated key** pasted into the `Propradar API:` line of `00_Run_Commands/gh-token-29Mar.txt`. `months=60` IS accepted but Free truncates to a recent ~4-month/113-row window. Deep backfill waits for `x-api-plan: hobby` (verify Hobby lifts `/suburbs/sold` depth on first call; fallback = per-property `/history` or Starter).
- **Coverage-gap → SEO bridge:** unmatched PropRadar addresses land in `Gold_Coast.propradar_coverage_gaps` (status: pending) — the worklist that seeds new property docs → enrichment → off-market pages → sitemap/Indexing API. Design pending (must pass the enrichment pipeline + editorial rules before any page publishes; no thin PropRadar-only stubs).

## 8. Open due-diligence
- Confirm PropRadar ToS §8A permits public display of derived suburb stats + required attribution.
- Confirm PropRadar has (or lacks) any historical sold-volume endpoint before choosing 7.2(c).
- Robina calibration snapshot still to be pulled.
