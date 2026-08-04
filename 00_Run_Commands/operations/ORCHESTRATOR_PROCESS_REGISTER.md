# Orchestrator Process Register

**Purpose:** the complete inventory of every automated process on `fields-orchestrator-vm` — the nightly
pipeline steps and their sub-steps, the daemons that run continuously, and the cron jobs around them —
with what each actually does, what it covers, and its verified state.

**Audit basis:** run `2026-08-04T20-30-16_completed`, compared against the 08-01/08-02/08-03 runs, plus live
inspection of cron, systemd and `system_monitor.job_runs`.
**Compiled:** 2026-08-05 · **Previous audit:** 2026-08-02 (of the 2026-08-01 run)

> **Regenerate by** re-auditing the newest `logs/runs/<id>_completed/` against `config/process_commands.yaml`,
> `src/schedule_manager.py`, `crontab -l`, `systemctl list-units 'fields-*'` and `system_monitor.job_runs`.
> All counts are point-in-time.

> ⚠️ **Read this before auditing from logs.** Per-step `stdout.log` files are **silently truncated** — they
> lose the final buffered chunk, which is usually the whole SUMMARY block (§7 #2). There is also **no
> `stderr.log` for any step, ever** — stderr is merged into stdout by design. The authoritative tail is
> `logs/orchestrator.log` (`[STEP <id> OUTPUT]` lines). Several conclusions in the 2026-08-02 audit were
> distorted by this; it is not a per-script buffering quirk as previously assumed.

---

## 1. Executive state

| | |
|---|---|
| Nightly pipeline | **Healthy at the step level** — 26/26 completed, 0 failed, 4.06 h (20:30 → 00:33) |
| Last 4 runs | 08-01 ✅ · 08-02 ✅ 3.29 h · 08-03 ✅ 2.75 h · 08-04 ✅ 4.06 h — all 26/26, 0 failed |
| Watchdog | 0 issues, hourly, last 08:12 |
| Defined processes | 35 — 26 ran, 9 did not (8 intentional, **1 dead**) |
| Cron entries | 83 active (+ a deliberately paused RL/agent block of ~21) |
| systemd services | 17 active, 1 timer-driven |
| Heartbeat jobs | 69 registered |
| Disk / Mem | 77% used (23 G free) · 4.9/15 Gi |

**"0 steps failed" is not "0 work lost."** Every step exits 0 while absorbing failures internally. The
material problems below all live inside green steps.

**Three things changed since the 2026-08-02 audit:**
- ✅ The blob dead-host fix **worked** — step 106 went from 54 failures/152 analyses to **0 failures/206**, stable over 3 runs.
- ✅ The coverage-check fixes **worked** — step 109 now tests 6 config-driven suburbs, 0 false ERRORs, Burleigh Waters parses (was `DOMAIN_UNAVAILABLE`).
- 🔴 The **same dead-host defect surfaced in step 105** and is escalating (0 → 1 → **158** failures), because the fix was applied to only one of four vision clients.

---

## 2. How the nightly run is scheduled

Trigger **20:30 AEST daily** — `fields-orchestrator.service` → `src/orchestrator_daemon.py`.
Manual: `python3 src/orchestrator_daemon.py --run-now`.

### ⚠️ Schedule membership lives in Python, not YAML
`config/process_commands.yaml` carries **no** `schedule`/`run_days`/`enabled` key on any process. Membership is
three hardcoded sets in `src/schedule_manager.py:64-66`:

```python
target_market_processes = {101,103,105,106,108,111,112,113,115,117}          # daily
other_suburbs_processes = {102,104}                                          # "Sunday" (see §5)
always_run_processes    = {6,11,12,13,14,15,16,17,18,19,107,109,110,114,116,120}
```

**Anything absent from all three can never run, on any day** — which is exactly how step 121 died (§5).
A process's schedule is invisible from its own definition; the two must be edited in lockstep and nothing
detects drift.

### `config/settings.yaml`
- `run_target_market_daily: true` — daily, weekends included.
- `run_other_suburbs_weekly: false` — **hard off since 2026-05-13** (the Sunday all-suburbs sweep tripped Akamai rate-limiting on Domain).
- `target_market.suburbs` — the single source of truth for scraping:
  **Robina 4226 · Varsity Lakes 4227 · Burleigh Waters 4220 · Mudgeeraba 4213 · Reedy Creek 4227 · Worongary 4213**
  (Merrimac and Carrara commented out.)

### Pre-run hooks
1. Chrome + ChromeDriver zombie cleanup (killed 4 on 08-04) → 2. Chromium snap tmp clear → 3. MongoDB connect

### Post-run hooks
1. `write-scraper-health.py` → `system_monitor.scraper_health` → 2. `write-audit-snapshot.py` →
3. Netlify rebuild hook (sitemap) → 4. Backup **intentionally skipped** (Cosmos has built-in backup)

---

## 3. Step-by-step register — the 26 that ran

Durations in seconds. Every step below exited 0.

| # | ID | Step | 08-02 | 08-03 | 08-04 |
|---|----|------|------:|------:|------:|
| 1 | 101 | Scrape For-Sale (Target Market) | 3576 | 2165 | 2567 |
| 2 | 103 | Monitor Sold (Target Market) | 1783 | 917 | 780 |
| 3 | 111 | Sold Listings Backfill | 205 | 77 | 78 |
| 4 | 113 | Detect Withdrawn | 2420 | 2415 | 2409 |
| 5 | 114 | Backfill URL Slugs | 2.3 | 2.8 | 4.9 |
| 6 | 115 | Track Price Changes | 22.9 | 22.4 | 22.9 |
| 7 | 110 | Download Images to Blob | 24.9 | 43.0 | 81.6 |
| 8 | 116 | Data Quality Validator | 149 | 150 | 151 |
| 9 | 112 | Classify Property Type | 0.9 | 5.4 | 50.1 |
| 10 | 105 | Photo Analysis & Reorder | 17.0 | 235 | 466 |
| 11 | 106 | Floor Plan Analysis | 896 | 960 | 970 |
| 12 | 108 | Valuation-Grade Enrichment | 3.4 | 36.5 | 275 |
| 13 | 117 | Satellite Image Analysis | 0.9 | 15.5 | 162 |
| 14 | 6 | Property Valuation Model | 32.0 | 35.2 | 214 |
| 15 | 11 | Parse Room Dimensions | 123 | 122 | 124 |
| 16 | 12 | Enrich Property Timeline | 220 | 222 | 229 |
| 17 | 13 | Generate Suburb Medians | 4.4 | 4.4 | 4.4 |
| 18 | 14 | Generate Suburb Statistics | 3.4 | 3.0 | 3.4 |
| 19 | 16 | Enrich Properties For Sale | 23.8 | 22.9 | 29.4 |
| 20 | 15 | Calculate Property Insights | 67.4 | 65.6 | 68.8 |
| 21 | 17 | Market Narrative Pre-compute | 0.3 | 0.3 | 0.3 |
| 22 | 19 | Active Listings Snapshot | 0.8 | 0.8 | 0.9 |
| 23 | 18 | Valuation Pre-computation | 338 | 343 | 340 |
| 24 | 120 | AI Property Editorial | 3.6 | 4.4 | 3490 |
| 25 | 109 | Coverage Check | 70.5 | 173 | 200 |
| 26 | 107 | Database Audit | 50.3 | 55.8 | 74.9 |

---

### Step 101 — Scrape For-Sale Properties (Target Market)
`run_curlffi_suburb_scrape.py --suburbs 'Robina,Varsity Lakes,Burleigh Waters,Mudgeeraba,Reedy Creek,Worongary'`
· cwd `Property_Data_Scraping/03_Gold_Coast/Gold_Coast_Wide_…` · 2567 s · **6 suburbs**

**Sub-steps (11), per suburb:**
1. `get_mongodb_connection()` / `_create_indexes()`
2. **Phase 1 `discover()`** — paginated `/sale/{slug}/?ssubs=0`; each page **re-fetched up to `PAGE_REFETCH_MAX` times**, unioning URLs until they cover that page's authoritative ld+json Residence count; reads `expected_count` from page 1. Stops on empty page / count reached / two consecutive barren pages / `MAX_PAGES`.
3. **Unresolved-address reconciliation** — keyed by `_addr_key` (number + street) so unit runs don't create false gaps
4. **New-vs-existing split** — loads `{listing_status: "for_sale", listing_url exists}`
5. **Cheap refresh `_refresh_existing()`** — no detail fetch; updates `price` from search-page meta (this feeds step 115), recomputes `days_on_domain`
6. **Phase 2 detail scrape** — JSON-LD schema → meta tags → HTML elements → inspection times → agent info → property features → images → floor plans
7. **Validity gate `_is_invalid_listing()`** — rejects `ID:\d+/` off-plan, `Type X`, `Lot N/`, suburb-only addresses
8. **Inline sold detection** → `listing_status = 'sold'`
9. **`save_to_mongodb()`** — GIS cadastral address match, new-listing blob-refresh flag, `PIPELINE_FIELDS` preservation
10. **`record_coverage()`** → `system_monitor.listing_coverage` with named `missing_addresses`
11. Final per-suburb summary *(lost to the truncation bug)*

| Suburb | Expected | Pages | Discovered | Unresolved | Detail | Refresh | New | Failed | In DB | Missing |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| Robina | 100 | 8 | **86 (86%)** | **19** | 17 | 69 | 13 | 4 | 103 | 6 |
| Varsity Lakes | 62 | 6 | 55 (89%) | **15** | 10 | 45 | 3 | 7 | 56 | 9 |
| Burleigh Waters | 56 | 5 | 54 (96%) | 6 | 8 | 46 | 7 | 1 | 58 | 1 |
| Mudgeeraba | 34 | 2 | 37 (109%) | 0 | 4 | 33 | 4 | 0 | 42 | 0 |
| Reedy Creek | 36 | 4 | 33 (92%) | 5 | 4 | 29 | 4 | 0 | 49 | 0 |
| Worongary | 35 | 4 | 29 (83%) | **9** | 5 | 24 | 5 | 0 | 59 | 1 |
| **Total** | **323** | | **294 (91%)** | **54** | 48 | 246 | 36 | 12 | 367 | 17 |

Writes: 4 inserts, 15 updates, 17 marked sold, 16 GIS matches, 12 blob re-download flags.

**⚠️ Discovery regression.** 08-03 was 310/311 (99.7%) with 26 unresolved; now **294/323 (91%) with 54
unresolved**. Robina fell from 94/94 to 86/100.
**⚠️ ~44% of detail-scrape work is a nightly repeat** — 13 of 17 sold-marks and 8 of 12 rejections are
byte-identical to the night before, including listings sold in Sep/Oct/Nov 2025. Once a doc leaves `for_sale`
it drops out of the `existing` map, so the same URL is re-discovered and full-fetched every night forever.
**⚠️** `listing_status` is unconditionally reset to `for_sale` on any detail re-scrape — an `under_contract`
flag set by step 103 can be silently reverted. The 12 "failed" are all deliberate rejections; the counter
conflates rejection with failure.

### Step 103 — Monitor Sold Properties (Target Market) · 780 s · **6 suburbs**
**Sub-steps (6):** curl_cffi chrome120 session (via Bright Data) → **sold pass** (3 pages of `/sold-listings/`)
→ **sold cross-reference** (match by listing id; on match writes sold fields plus three sub-calculations —
**vendor discount %**, **`price_history` "sold" append**, **Domain valuation accuracy**, and days-on-market)
→ **under-contract pass** (5 pages of `/sale/`, text-matching "under contract | under offer | deposit taken |
offer accepted | conditional") → **UC cross-reference** → TOTALS.

| Suburb | Sold on Domain | sold_detected | already_sold | **not_in_db** | UC on Domain | uc_detected |
|---|---:|---:|---:|---:|---:|---:|
| Robina | 29 | 1 | 24 | 4 | 1 | 0 |
| Varsity Lakes | 14 | 0 | 13 | 1 | 9 | 0 |
| Burleigh Waters | 24 | 2 | 21 | 1 | 2 | 0 |
| Mudgeeraba | 34 | 1 | 12 | **21** | 0 | 0 |
| Reedy Creek | 36 | 0 | 15 | **21** | 3 | 1 |
| Worongary | 19 | 0 | 9 | **10** | 2 | 1 |
| **TOTAL** | 156 | **4** | 94 | **58** | 17 | 2 |

Sales written: 6 Nypa Close Robina $1,285,000 (vendor discount −1.1%, Domain valuation +7.1%);
2401/12-14 Executive Dr $870,000 (−2.8%); 105 Harrier Dr $1,290,000 (Domain −7.9%);
8 Holterman Ct Mudgeeraba — **sold with price `None`**.

**⚠️ 58 sold listings/night are silently discarded** — visible on Domain, held neither as `for_sale` nor `sold`.
52 of the 58 are in the three suburbs step 111 doesn't cover, so nothing else catches them. (Was 44 on 08-03.)
**⚠️ Page yields are unstable** — this fetcher has **no re-fetch-until-covered loop** (unlike step 101). Robina
returned 17 cards on page 1 here and 3 to step 111 two minutes later. Any metric derived from these counts is unreliable.

### Step 111 — Sold Listings Backfill · 78 s · **4 suburbs (Robina, Varsity Lakes, Burleigh Waters, Merrimac)**
**Sub-steps:** connect → cutoff computation (`--days 7` → 2026-07-28) → paginated per-suburb scrape (max 15
pages, 3 retries on blank) → card parse → **cutoff break on first stale card** → dedupe → `update_database()`.

9 records after dedup, 8 matched, **0 updated, 0 inserted, 9 skipped, 0 errors — the step wrote nothing.**
(08-03 wrote 3.) Robina found 3 records, matched 2, inserted 0, skipped 3 — one record vanished with no
reason logged. `matched` and `skipped` double-count the same record, so the totals are not disjoint.
**⚠️ Covers Merrimac (which no other step in this phase touches) but NOT the three suburbs where 90% of step
103's misses occur** — the exact opposite of what a backstop should do.

### Step 113 — Detect Withdrawn Properties · 2409 s · **3 suburbs only**
**Sub-steps (8):** connect + curl_cffi/Bright Data → per-suburb worklist **sorted oldest-checked-first (a
persisted rotation cursor)** → **round-robin interleave** across suburbs so a truncated budget spreads evenly →
per-listing `check_listing_status()` (title `Sold…` → sold; `/property-profile/` redirect → withdrawn; else
active) → two abort guards (40-min wall clock, 15 consecutive errors) → withdrawal write with price snapshot →
Telegram notify → RESULTS with explicit incomplete-suburb report.

Worklist 214 (robina 102, varsity_lakes 56, burleigh_waters 56) → **checked 143 (66.8%), 1 withdrawn, 0 errors**
→ `ABORTED EARLY: runtime budget exceeded (40 min)`. ~16.8 s/listing.
**Has never completed a full sweep** on any audited run (self-caps at `MAX_RUNTIME_MIN = 40`). To its credit
the shortfall is named per-suburb and the cursor guarantees next-run pickup — but the 147 listings in the three
uncovered suburbs are checked **never**, which is why they all show `withdrawn = 0`.
*(One reconciliation gap: 30 Aruma Ave was flagged withdrawn on 08-03 then marked sold on 08-04. Nothing reconciles contradictory statuses.)*

### Step 114 — Backfill URL Slugs · 4.9 s · **9 suburbs** (`shared/db.py` TARGET_SUBURBS)
**Sub-steps:** connect → per-collection sparse query (non-empty `address`, missing `url_slug`) →
`clean_address()` (strips `Sold … on DD Mon YYYY - <id>` wrapper and trailing `, QLD ####`) → `generate_slug()`
→ **duplicate-slug check** (5× Cosmos 16500 retry) → on collision **append last 4 chars of `_id`** → write.

**8 slugs backfilled, 0 errors.** No per-suburb breakdown is ever printed — the least observable step in the
pipeline. **The collision path is silent**: it suffixes and prints nothing, which is the mechanism behind the
known suffixed-slug duplicate-public-page problem.

### Step 115 — Track Price Changes · 22.9 s · **3 suburbs**
**Sub-steps:** connect + build `run_id` → per-suburb load → **seed branch** (`event: "initial"`) → **change
branch** (`$push event: "change"`, compute `change_pct`, classify reduction/increase/unknown, insert into
`system_monitor.price_change_events`) → unchanged counter → totals. Does no fetching; reads prices written by step 101.

| Suburb | Seeded | Changed | Unchanged | Errors |
|---|---:|---:|---:|---:|
| robina | 8 | 1 | 92 | 0 |
| varsity_lakes | 0 | 0 | 56 | 0 |
| burleigh_waters | 4 | 1 | 51 | 0 |
| **TOTAL** | **12** | **2** | **199** | **0** |

Changes: `1/47 Treeview Drive $1,179,000+ → $1,100,000+ −6.7% (reduction)` — cross-confirmed against step 101's
cheap refresh 2 h earlier, so the 101→115 chain works end to end. And `83 Glen Eagles Drive: Offer Above $1.8m
→ **Auction Results**` — `change_pct = None`, direction `unknown`.
**⚠️ Garbage price text is stored unvalidated.** `Auction Results` was written as a price; the night before the
same property logged `OFFERS ABOVE $1,600,000 → Offer Above $1.8m`. 4 of 6 "price changes" on 08-03 had no
numeric delta. Any "price reductions this month" metric built on `price_change_events` is contaminated.
Related upstream artefact: step 101 stored `'$1,250.000 +'` (period for comma) for 18 Wollemi Court.

### Step 110 — Download Property Images to Blob · 81.6 s
**Sub-steps: three full collection sweeps** — (1) `Gold_Coast` for_sale (108 collections), (2) `Gold_Coast` sold
(108 again), (3) `Target_Market_Sold_Last_12_Months` (8). Backend `local` → `blobs.fieldsestate.com.au`.
**Coverage: all 108 collections — no gap.** 18 uploaded, 4 skipped, **Failed=0**.

**Silent issues:** 4 image losses reported as successes (1 read timeout, 1 Domain 403 on a virtual-viewer URL,
2× 404 — one doc left with 0 photos still logged `OK`); the for_sale and sold passes double-process the same
doc. **Critically, it rewrites `property_images`/`floor_plans` but NOT `scraped_data.images`** — the direct
cause of the step 105 failure below.

### Step 116 — Data Quality Validator · 150.8 s · rules only, no model
Scans **9 suburbs** (the 6 + burleigh_heads, merrimac, carrara) — superset, no gap.
`OUTCOME: violations_found` — **251 issues, 221 auto-fixed, 30 unfixed**: `stale_days_on_domain` 221 (all fixed),
`missing_critical_fields` 21 (0 fixed), `implausible_land_size` 9 (0 fixed, e.g. land_size 1 m²).
Exits 0 for both `passed` and `violations_found` by design — the 30 unfixed persist nightly with no escalation.

### Step 112 — Classify Property Type · `claude-haiku-4-5` via OpenRouter · 50.1 s
**Sub-steps:** per-suburb candidate query → vision classify + write → divergence report.
**Coverage: 3 suburbs** (robina, varsity_lakes, burleigh_waters).
13 candidates → **12 classified, 1 skipped (no images), 0 errors**, 2 reclassifications
(`2/64 Riverwalk Ave` Unknown→Unit; `108/170 Bardon Ave` Retirement Living→Townhouse).

### Step 105 — Photo Analysis & Reorder — 🔴 **BROKEN** · `claude-sonnet-4-6` · 466 s
**Sub-steps:** wrapper loops 6 suburbs × 2 passes. Pass 1 **photo analysis** (`run_production.py`) — note the
`--collection` arg is **ignored**, so the first invocation sweeps all 7 collections and iterations 2-6 no-op.
Pass 2 **photo reorder** (`run_photo_reorder.py`), genuinely per-suburb.

**16 properties had work; 5 succeeded (105 images analysed); 11 produced ZERO analyses; 158 image
downloads failed** — all against `fieldspropertyimages.blob.core.windows.net`, now `NameResolutionError`
(the Azure account has been fully **deleted**, so the symptom changed from HTTP 403 to NXDOMAIN).

**Root cause:** `worker_multi.py:_extract_images()` resolves `scraped_data.images` → `property_images` → `images`
and takes the **first non-empty**. `scraped_data.images` is a legacy field step 110 never rewrites and still
holds dead Azure URLs — while `property_images` on the *same docs* holds valid live URLs written 4 minutes
earlier. The `to_live_url()` fix of 2026-08-02 exists **only in `openai_floorplan_client.py`**; step 105's
downloader is `ollama_client_single_image.py` and has no rewrite.

**Silent failure (severity: high):** all 11 zero-analysis docs logged `Successfully processed` and are now
flagged processed — **they will never be retried and cannot self-heal.** Trend: 0 → 0 → 1 → **158** failures;
the earlier clean runs were vacuous (no work), so the defect was simply never exercised.

### Step 106 — Floor Plan Analysis — ✅ **FIX CONFIRMED** · `claude-sonnet-4-6` · 970 s
**Sub-steps:** per-suburb backlog count (RU-guarded) → candidate load → **stub-write pass** for image-less docs
→ floor-plan identification (dedicated `floor_plans` field, else URL-pattern fallback) → download → PNG convert
→ base64 → Claude vision → JSON parse → write. **Coverage: 3 suburbs.**

168 candidates → 33 stubbed → 135 processed → **103 analysed (105 plans), 32 no-plan, 0 errors.**

| Run | 403 / "account is disabled" | Download failures | Analysed |
|---|---:|---:|---:|
| 08-01 (pre-fix) | **54** | 162 | 49 |
| 08-02 (fix day) | 0 | 0 | 103 |
| 08-03 | 0 | 0 | 102 |
| **08-04** | **0** | **0** | **103** |

### Step 108 — Valuation-Grade Enrichment · `claude-sonnet-4-6` · 275 s · **3 suburbs**
13 to process → **12 succeeded, 6 with floor plan, 1 skipped (no photos), 0 failed**, 21.1 s/doc.
Reads `property_images` (live URLs), so it is unaffected by the dead-host bug.

### Step 117 — Satellite Image Analysis · `claude-opus-4-8` · 162 s · **4 suburbs** (+merrimac)
**Sub-steps per property:** backlog count → candidate load → **Google Maps Static fetch** (zoom 19, 640×640, ×2)
→ **blob archive** of the aerial → Claude Opus vision → write `satellite_analysis`.
12 candidates → **12 successful, 0 errors.** 8 of 12 used real lat/lng; **4 fell back to address-string
geocoding** — a silent accuracy degradation counted nowhere.

### Step 6 — Property Valuation Model — 🔴 · CatBoost `iteration_08` · 214 s
*(This is the deprecated CatBoost model, NOT the public `reconciled_valuation` — that is step 18.)*
**Sub-steps:** startup (model load, **GPT client init FAILS**, feature aligner 126 features) → query for-sale →
**Gold_Coast document match** (+ Nominatim geocode fallback) → GPT enrichment **skipped** → per-property
(lat/lng guard → **OSM/Overpass enrichment** → features → predict → dual-DB insert) → missing-features report.

**Queried 25 (23 unique — 2 duplicate docs) → 1 valued, 24 failed.**
- **Overpass HTTP 406 on 20 calls — a 100% failure rate on every property needing a live call.** `406` falls
  into a bare `else: return None` with **no retry** (`osm_feature_definitions.py:170`); only 429/5xx retry.
- The single success had **cached** OSM features and made no Overpass call (`osm_enrichments: 0` all run) — not evidence of a fix.
- 4 × missing lat/lng; 4 Nominatim misses; `gpt_client` module missing (gpt features 88.2% null);
  type bug `Error calculating suburb stats for ROBINA: '<' not supported between float and dict`.
- Comparables contain a sale dated **2105-12-10**.
- The 214 s (vs 35 s) is one property triggering a 105-collection sweep — a cost regression, not throughput.

### Step 11 — Parse Room Dimensions · 124 s · 3 suburbs
415 candidates → **415 processed, 403 updated, 0 errors.** Clean. (+7 vs prior run.)

### Step 12 — Enrich Property Timeline — 🔴 Pass 3 dead · 229 s
**Sub-steps:** **Pass 1** Gold_Coast address match → **Pass 2** URL-slug fallback → **Pass 3** Domain
property-profile scrape for the unmatched.
Pass 1+2: 18,409 checked, **143 for-sale updated** (robina 59, varsity_lakes 36, burleigh_waters 48). Healthy.
**Pass 3: 73 attempted, 73 failed, 0 transactions, 0 new docs** — third-plus consecutive total failure.
**Root cause:** `domain_profile_scraper.py:203` uses `curl_cffi` **direct from the VM IP**, which Domain/Akamai
blocks, instead of `shared.domain_fetch.fetch_html` (Bright Data). It swallows the status code, so blocks are
**mislabelled "no profile page (404)"**. ~219 s of the 229 s runtime is spent on requests that cannot succeed.

### Step 13 — Generate Suburb Medians · 4.4 s · 3 suburbs
robina 174 quarters (latest $1,365,000), varsity_lakes 167 ($1,477,500), burleigh_waters 208 ($2,250,000). 0 errors.
Byte-identical across three runs. Outlier surviving: `stapylton 2024-Q3 median $4,730,000`.

### Step 14 — Generate Suburb Statistics · 3.4 s · 3 suburbs
robina 450 houses (59 priced), varsity_lakes 295 (21), burleigh_waters 352 (32). 0 errors.
Floor-area minima of **7.9 m²** and 31.3 m² are entering the distributions that drive step 15 rarity percentiles.

### Step 16 — Enrich Properties For Sale · 29.4 s · `--new-only`
48 found → **48 enriched, 0 errors**. But completeness is poor: **Floor Area present on only 7/48 (14.6%)**,
Lot Size 20/48, transactions >0 on 26/48. **This 85% missing-floor-area rate is the direct upstream cause of
step 18's 219 `missing_floor_area` exclusions.**

### Step 15 — Calculate Property Insights · 68.8 s · 3 suburbs
669 processed, **44 with unique insights** (6.6%). 0 errors. Builds ONLY 1 / TOP 3 / RARE badges from
floor-area and bedroom percentiles.

### Step 17 — Market Narrative Pre-computation · 0.3 s — ✅ **INTENTIONAL NO-OP**
**Not a failure.** `RUN_PRECOMPUTE.sh` carries a dated 2026-08-02 block (fix `[UNION-MEDIANS-REVERTED-NIGHTLY]`)
removing both precomputes, because `precompute_indexed_price_data.py` did a blind `replace_one` that **wiped the
corrected medians promoted by the 1st-of-month chain — ~29 nights in 30 the live pages served raw values.**
Both are now cron-only on the 1st, in a strict order. The script says **"DO NOT re-add either line here."**
*(The 300 s run on 08-01 was the last nightly execution before removal — this corrects the 2026-08-02 audit,
which flagged the 0.3 s as suspicious.)*
Residual: the step still occupies a slot + 60 s cooldown, `process_commands.yaml` still describes it as a 30-min
`moderate_write`, and it still prints "Pre-computation complete!".

### Step 19 — Active Listings Snapshot · 0.9 s · 8 suburbs · 234 active (+3). 0 errors.
Note `burleigh_heads` is absent here but is step 18's largest collection (113) — the two disagree on the suburb set.

### Step 18 — Valuation Pre-computation · 340 s — produces the public `reconciled_valuation`
**Sub-steps:** load sold comparables + dedup (5,065 across 54 suburbs; 330 dupes removed) → preload coordinates
(153,027) → preload timelines/build years (115,145) → suburb median cache (581) → street premium cache (531) →
fetch for-sale (540 across 9 collections) → per-property (exclusion gate → dedup → comparable selection →
regression rate validation → weighted valuation → write).

**233 succeeded · 303 excluded · 4 skipped · 0 errors — 56.9% exclusion rate**, and **every one of the 303
printed `— cleared existing valuation`**, i.e. 303 properties had a published valuation actively wiped.

| Reason | 08-04 | 08-01 |
|---|---:|---:|
| missing_floor_area | 219 | 217 |
| misclassified_dwelling | 28 | 28 |
| acreage | 23 | 21 |
| insufficient_comparables | 17 | 16 |
| missing_land_size | 16 | 16 |

**The split is the story:** target suburbs succeed 76–83% (Robina 84/101, Burleigh Waters 46/56, Varsity Lakes
43/56); expansion suburbs succeed 3–29% (**Worongary 2/58**, Mudgeeraba 4/41, Carrara 11/56, Burleigh Heads
27/113). **260 of 303 exclusions (86%) come from suburbs that never receive the enrichment chain.**
Also: several valuations written as `Success` with **0/0 comparables included**.

### Step 120 — AI Property Editorial · `claude-opus-4-8` on Claude Max · 3490 s
*(3.4 s on 08-01 because zero listings qualified — not a regression.)*
**Selection:** 4 hardcoded suburbs, `for_sale`, `days_on_domain ≤ 7`, `property_type == "House"`, no `ai_analysis`.
**Pre-flight sub-steps:** valuation check → zoning + flood + ICA → **satellite verification (vision via
Gemini/Vertex)** → document serialisation + comparables compaction → suburb medians → competing listings →
recent sales → Domain valuation extraction.
**LLM chain (11 calls/property):** Price & Value Analyst → Property & Trade-offs Analyst → Market Position
Analyst → Editor (body) → Sabri Headline Specialist (draft 1) → Reflection → Data Backfill → Fact-Check →
Editor Draft 2 → Verify → Sabri Re-run.

**5 entered, 3 fully processed, 3 published, 0 draft, 0 failed_factcheck, 2 skipped (WATERFRONT, out of scope).**
Per-property ~1,080–1,230 s.

**Quality signal worth registering:** across the 3 properties the fact-checker caught **14 failures in 128
verified claims plus 15 unverifiable**, and **all 3 draft-1 headlines were invalidated**. Failures were
fabricated comparable adjustments (e.g. a comp claimed at $1,305,000 vs actual adjusted $1,032,710). Content is
safe only because the gate works. One property (`3 Corina Close`) was **published with an unresolved
fact-check flag** (`verify_outcome=minor_flags`) — worth confirming that auto-publish policy is intended.
Also: 1 ArcGIS LOT_PLAN timeout → published with `Zoned: ?`; **zero prompt-cache utilisation** (1.21 M input
tokens, 100% uncached over 33 calls).

### Step 109 — Coverage Check — ✅ **BOTH 2026-08-02 FIXES VERIFIED** · 200 s
Runs `--from-config --no-fail`, reading `settings.yaml target_market`. **6 suburbs, all OK, 0 gaps, 0
DOMAIN_UNAVAILABLE.** Wrote 6 records to `system_monitor.data_integrity`.

| | 08-01 | 08-04 |
|---|---|---|
| Suburbs | 8 (hardcoded) | 6 (config-driven) |
| False ERRORs | 2 (Merrimac, Carrara) | **0** |
| Burleigh Waters | `DOMAIN_UNAVAILABLE` | **OK 56/56** |
| Duration | 511 s | 200 s |

Caveat: Varsity Lakes is Domain 62 vs DB 56 and passes only because 8 recent-sold are added to the visible
count. Thinnest margin of the six.

### Step 107 — Database Audit & Validation · 74.9 s · report-only (`--fix` not passed)
105 collections, 399,337 properties audited → **416 misplaced, all HIGH, all `WRONG_COLLECTION`.**
By collection: `propradar_sold` 293, `property_attributes` 92, `propradar_coverage_gaps` 30, `propradar_gap_enriched` 1.
By root cause: `COLLECTION_ASSIGNMENT_BUG` 92; **`UNKNOWN` 324 (78%)** — the classifier assumes a populated
suburb field the `propradar_*` collections don't carry, so it cannot reason about most of what it reports.
Count stepped 388 → 416 on 2026-08-02 and has held. **Writes nothing to MongoDB and has no heartbeat** — the
416 findings exist only in logs and a `/tmp` file.

---

## 4. Coverage — the structural gaps

### 4.1 🔴 `under_contract` is a terminal state — 117 listings are frozen

Verified live. `sold_backfill/search_based_sold_monitor.py:548` is the **only writer** of `under_contract`
anywhere, and **nothing reads it as an input**. Every downstream step filters `{"listing_status": "for_sale"}`
— steps 101 (cheap refresh), 103 (sold + UC cross-reference), 113, 115. So once a property is flagged it
leaves the pipeline permanently: never re-priced, never checked for withdrawal, and **if it sells it can never
be detected as sold**.

| Suburb | for_sale | **under_contract** | sold | withdrawn |
|---|---:|---:|---:|---:|
| robina | 101 | 18 | 616 | 26 |
| varsity_lakes | 56 | 19 | 515 | 18 |
| burleigh_waters | 56 | 10 | 418 | 20 |
| **mudgeeraba** | 41 | **37** | 277 | **0** |
| reedy_creek | 48 | 18 | 279 | **0** |
| worongary | 58 | 15 | 239 | **0** |
| **Total** | 360 | **117** | | |

Oldest stuck record: **37 Bridgman Drive, Reedy Creek — detected 2026-03-22, 4.5 months ago.** Mudgeeraba has
37 frozen against 41 active — roughly 47% of its market is in a dead state. The `withdrawn = 0` on the three
expansion suburbs is a coverage artefact of step 113's 3-suburb scope, not a market fact.

Side effect: `already_uc` in `process_under_contract_for_suburb` is **structurally unreachable** (it can only
fire for a doc in a `for_sale`-only query that is already `under_contract`), reads 0 every night, and makes the
UC `not_in_db` figure meaningless.

### 4.2 Phase-1 suburb coverage — 3 of 6 scraped suburbs are half-served

| Step | Suburbs covered | List source |
|---|---|---|
| 101 Scrape | all 6 | CLI arg |
| 103 Sold monitor | all 6 | CLI arg |
| 111 Sold backfill | **4** — +Merrimac, −Mudgeeraba/Reedy Creek/Worongary | hardcoded `scrape_recent_sold.py:46` |
| 113 Withdrawn | **3** | hardcoded `detect_withdrawn.py:61` |
| 114 URL slugs | 9 | `shared/db.py:36` |
| 115 Price changes | **3** | hardcoded `track_price_changes.py:49` |

Mudgeeraba, Reedy Creek and Worongary — **147 for-sale listings** — get no withdrawn detection, no
price-change tracking and no sold backfill. Because they have no `price_history`, `vendor_discount_pct` can
never be computed for them even when step 103 does detect a sale.

### 4.3 Enrichment coverage

Measured live, for-sale listings, after the 08-04 run:

| Suburb | for_sale | photo | floorplan | satellite | valuation | AI editorial | insights |
|---|---:|---:|---:|---:|---:|---:|---:|
| robina | 101 | 101 | 71 | 101 | 101 | 66 | 100 |
| varsity_lakes | 56 | 56 | 45 | 56 | 56 | 26 | 56 |
| burleigh_waters | 56 | 56 | 41 | 56 | 56 | 34 | 56 |
| **mudgeeraba** | 41 | 41 | **5** | **0** | 41 | **0** | **0** |
| **reedy_creek** | 48 | 47 | **15** | **1** | 48 | **0** | **0** |
| **worongary** | 58 | 58 | **8** | **1** | 58 | **0** | 11 |
| **Total** | 360 | 359 | 185 | 215 | 360 | 126 | 223 |

**Four different definitions of "target market" are live simultaneously:** `config.py:TARGET_SUBURBS` (7), the
step-105 bash array (6), `shared/db.py:FEATURED_SUBURBS` (3), and step 117's hardcoded list (4). Steps 112,
106, 108 cover 3; step 117 covers 4; step 120 covers 4 **including the retired Merrimac**; steps 110/116 cover
all. Mudgeeraba, Reedy Creek and Worongary are scraped nightly and receive images, validation and photo
analysis — but **no classification, no floor plans, no satellite, no editorial**.

---

## 5. The 9 processes that did not run

| ID | Name | Verdict |
|---|---|---|
| 102 | Scrape For-Sale (All Suburbs) | Intentional — off indefinitely (Akamai). Last ran 2026-05-10 |
| 104 | Monitor Sold (All Suburbs) | Intentional — same |
| **121** | **SEO Sitemap Resubmit (Nightly)** | 🔴 **SILENTLY DEAD — has never run, ever** |
| 122 | Live Leads Sheet — Selling Plan Refresh | Intentional — trigger-driven (`trigger_requests`) |
| 201 | Facebook Ads Metrics Collector | Intentional — owned by cron (12:00 + 23:00) |
| 202 | Google Ads Metrics Collector | Intentional — cron (12:15 + 23:10) |
| 203 | Marketing Stage Tracker | Intentional — cron (23:05) |
| 301 | Run Subject Valuation | Intentional — trigger-only (`PIPELINE_ID` placeholder) |
| 300 | Generate Appraisal Report (V4) | Intentional — trigger-only |

### 🔴 Step 121 has never executed
Created 2026-07-21 specifically so newly-published pages are resubmitted **same night** instead of waiting for
the Monday cron; re-added to `execution_order` 2026-07-30 with `depends_on: [120]`. But `121` appears **zero
times in `src/schedule_manager.py`** — when steps 117 and 120 were added to `always_run_processes`, 121 was
not. Verified: **0 run directories in the entire history of `logs/runs/`.** It is skipped nightly with the
generic `SKIPPED (not scheduled for today)`, which reads as normal.
**Impact:** the up-to-7-day sitemap resubmission lag it was built to eliminate is still fully present, and has
been for ~15 days. The 3 pages published on 08-04 wait until Monday 2026-08-10 07:00.
**Fix:** add `121` to `always_run_processes` (`src/schedule_manager.py:66`).

### Misleading skip message for 102/104
`should_run_other_suburbs()` returns `False` on the disable flag **before** the day check, so the log line
"today is Tuesday, runs on Sunday" is wrong — they will not run on any Sunday. Reactivation requires flipping
`run_other_suburbs_weekly`, not waiting.

---

## 6. Processes outside the nightly pipeline

### 6.1 systemd services (17 active)

| Service | Script | Role |
|---|---|---|
| `fields-orchestrator` | `src/orchestrator_daemon.py` | Nightly pipeline daemon |
| `fields-watchdog` | `watchdog.py` | Hourly self-heal: memory, scraper health, DB coverage, collection counts, process failures, API health |
| `fields-trigger-poller` | `trigger-poller.py` | Executes on-demand `trigger_requests` (30 s poll) — dispatches 122/300/301 |
| `fields-valuation-api` / `-poller` | `scripts/valuation_poller.py` | On-demand valuation service + queue |
| `fields-ai-analysis-poller` | `scripts/ai_analysis_poller.py` | Editorial requests |
| `fields-appraisal-poller` | `appraisal-poller.py` | Appraisal queue |
| `fields-property-report-poller` | — | Mini-site report builds |
| `fields-offmarket-processor` | `offmarket_order_processor.py` | Off-market orders |
| `fields-offmarket-intel-poller` | `scripts/offmarket_intel_poller.py` | Off-market intel |
| `fields-bridge-sync` | `property_reports_to_appraisal_pipeline_bridge.py` | Report → appraisal bridge |
| `fields-ceo-telegram` / `fields-builder-telegram` | `*-telegram-bridge.py` | Telegram bridges |
| `fields-samantha-chat` | `scripts/samantha_chat/service.py` | Chat agent |
| `fields-voice-agent` / `fields-tracking` | `server.py` | Voice agent, tracking |
| `fields-resource-guard` | `scripts/resource_guard.py` | Timer-driven (90 s) OOM guard |
| `actions.runner…fields-vm-runner` | — | Self-hosted GitHub Actions runner |

### 6.2 Cron — 83 active entries
Grouped by function (full list: `crontab -l`):
- **Ops/health:** `refresh-ops-context.py` (15 min), `api-health-check.py` (30 min), `write_vm_metrics.py` + `write_heartbeat.sh` (1 min), `main_site_health_to_sheet.py` (01:00), `check_systems_health_ran.py` (07:00), `api_health_monitor.py` (08:00), `check_unpushed_code.py` (09:10)
- **Data:** `generate_schema_snapshot.py` (03:00), `mongodb-backup.sh` (02:00), blob→GCS rsync (03:00), `refresh-mongo-allowlist.sh` (04:30), `monthly_sold_refresh.py` (25th)
- **onthehouse chain (nightly):** `rental_listings_sync` 23:30 → `normalize_addresses` 23:40 → `onthehouse_listings_sync` 23:35 → `onthehouse_sold_sync` 23:40 (deep on Sun) → `onthehouse_reconcile` 23:55
- **Leads:** `fb-lead-puller.py` (15 min), `hot_lead_responder.py` (10 min), `nightly_lead_chain.py` (00:15), `crm_sync.py` (hourly), `sms_claim_watchdog.py` (hourly)
- **Ads:** FB + Google metrics collectors (2×/day), `marketing-stage-tracker.py`, `fb_approval.py poll` (3 min, 08-22)
- **Off-market:** `offmarket_discovery_nightly.py` (00:20), `flag_multilot_offmarket.py` (00:10), `build_listed_property.py --drain` (3 min), `keep_warm_forsale_v3.py` (5 min)
- **Content/SEO:** `regenerate-sitemap.sh` (06:15), `seo_dashboard.py` (06:45), `seo_indexation_check.py` (Mon 07:00), brain2 nightly suite (23:30-23:52)
- **Monthly/weekly:** market pulse reminder (1st 08:00) + fallback (3rd 06:00), `run_monthly_market_precompute.sh` (1st 05:00), `valuation_backtest.py` (Sun 06:07)

**Deliberately paused block (~21 entries), all tagged `[PAUSED 2026-07-30 RL/agents off]`:** the entire
Reinforcement Learning / Conductor layer — `conductor_cycle.sh`, `conductor_dispatch.sh`, `rl_dispatch.sh`
(seo/ads/articles/onsite), `geo_dispatch.sh`, all `*_signal.py`, `reward_ledger.py`, `arm_grader.py`,
`rl_selftest.py`, `organize_cycles.py`, `offmarket_sitemap_release.py`, off-market `tick.sh`.

### 6.3 Heartbeats — `system_monitor.job_runs` (69 registered)

**Healthy (≤ cadence):** 36 jobs, including the whole onthehouse chain, `nightly_lead_chain`,
`listing_discovery_coverage`, `offmarket_discovery_nightly`, `brain_drive_refresh`, `crm`/lead jobs,
`samantha_chat`, `fb_approval_poll`.

**STALE but EXPECTED (~30 jobs)** — every one belongs to the paused RL/agent block above: `rl_*`, `*_cycle`,
`*_dispatch`, `conductor_cycle`, `offmarket_sitemap_release`, `offmarket_coverage_scraper`. Ages 136–163 h.
**These are not failures.** They are the single largest source of noise on the Systems Health board.

**Genuine problems:**
| Job | State | Note |
|---|---|---|
| `seo_dashboard` | 🔴 **188.9 h stale, cadence 24 h** | Cron entry is **active** (`45 6 * * *`) but `logs/seo-dashboard.log` has not been written since **2026-07-28** and contains only one successful run ever. The cron is not executing. |
| `search_intent_ads` | 🟠 `error` | detail: `0 rows collected` |
| `offmarket_coverage_scraper` | 🟠 `error` + stale | Within the paused block; error predates the pause |

### 6.4 A second, unfixed copy of the coverage false-alarm
`scripts/refresh-ops-context.py` (15-min cron) **independently writes `system_monitor.data_integrity`** and still
carries **Merrimac and Carrara as `critical`** — the exact false-alarm class fixed in step 109 on 2026-08-02,
still live in a parallel path feeding the ops dashboard.

---

## 6.5 Monitoring reconciliation (2026-08-05)

Every process in this register was reconciled against the **Fields Systems Health** sheet
(`1Oa7uZv0shzsxftDYJJ3WErxhr7OZMf_SOxRFawbSgTk`, rebuilt nightly at 01:00 by
`scripts/main_site_health_to_sheet.py`).

**How each class of process is watched:**

| Class | Mechanism | Where |
|---|---|---|
| Nightly pipeline — did it run | newest `logs/runs/` dir vs the expected 20:30 trigger | Pipeline Processes |
| Nightly pipeline — did a step crash | `result.json.success` per step | Pipeline Processes |
| **Nightly pipeline — did a step lose work** | **`_STEP_OUTCOME_CHECKS` (new)** | Pipeline Processes |
| **Step defined but unreachable by scheduler** | **schedule-membership drift check (new)** | Pipeline Processes |
| **Terminal-state accumulation** | **`under_contract` backlog check (new)** | Pipeline Processes |
| Suburb coverage vs Domain | `system_monitor.scraper_health` (step 109 → write-scraper-health) | Pipeline Processes |
| Vision provider credit | live Anthropic/OpenAI probe | Pipeline Processes |
| Cron jobs that self-report | `job_run()` heartbeat → `system_monitor.job_runs` | Process Registry |
| Cron jobs that don't | log-file freshness vs cadence | Process Registry |
| Deliberately paused jobs | `_PAUSED_JOBS` / `_REGISTRY_DISABLED` → renders KNOWN-GAP, not alarm | Process Registry |
| Daemons | `systemctl is-active` per unit | Process Registry |
| The checker itself | `check_systems_health_ran.py`, separate 07:00 cron, Telegrams directly | Process Registry (Meta) |

**Gaps closed on 2026-08-05:**
- **Outcome blindness.** The page judged steps purely on exit code. Since every step exits 0 while
  absorbing failures, a night that lost 11 listings' photo analyses, valued 1 property of 25, failed 73/73
  profile scrapes and cleared 303 valuations rendered as "26 ok / 0 failed". Added
  `collect_pipeline_integrity()` with per-step outcome assertions for steps 6, 12, 18, 105, 106, 111, 113.
  A step whose log no longer matches its pattern renders **UNKNOWN ("cannot verify"), never a silent OK**.
- **Schedule drift.** A step in `execution_order` but in no `schedule_manager.py` set produces no
  `result.json` and therefore produced no row at all — how step 121 went 15 days unnoticed. Now an ERROR
  naming the orphan.
- **Terminal states.** The 117 frozen `under_contract` listings had no check anywhere.
- **`fields-samantha-chat`** was active and enabled but absent from the monitored systemd list.
- **9 active cron jobs** had no heartbeat, no registry row and no other coverage: policy research fetch,
  price-tier liquidity precompute, monthly market precompute chain, Market Pulse reminder + auto-fallback,
  Brain 3 ops nightly, Samantha action-log harvest, for-sale-v3 keep-warm, VM heartbeat writer.
- **Log truncation.** `src/task_executor.py` never wrote the drained stdout tail to the per-step log, so
  the summary block the outcome checks read was being discarded. Fixed — see `[STEP-STDOUT-TRUNCATED]`.

**Effect:** Pipeline Processes moved **64% → 38% (4 → 11 errors)**. The score dropped because the board
started telling the truth, not because anything got worse.

**Still unwatched (accepted, low value):** per-suburb enrichment-coverage ratios (§4.3) and the four
competing "target market" definitions are documented here but not alarmed — they are scope decisions for
Will, not failures.

---

## 7. Open issues — priority order

| # | Sev | Where | Issue |
|---|---|---|---|
| 0 | 🔴 | Step 103 / all | **`under_contract` is a terminal state — 117 listings permanently frozen** (§4.1). Only a writer, no reader; every downstream step filters `for_sale`. A property flagged UC can never be re-priced, withdrawn-checked, or **detected as sold**. Oldest stuck 4.5 months. Mudgeeraba 37 frozen vs 41 active. |
| 1 | 🔴 | Step 105 | **Dead Azure host, unfixed.** 158 download failures; **11 listings written with zero photo analyses, marked processed, will never retry.** `to_live_url()` was applied only to `openai_floorplan_client.py`; `ollama_client_single_image.py` + `ollama_client.py` + `ollama_floorplan_client.py` still lack it. Root cause is `worker_multi.py:_extract_images()` preferring stale `scraped_data.images` over live `property_images`. Escalating: 0 → 1 → 158. |
| 2 | 🔴 | `task_executor.py` | **Per-step `stdout.log` silently truncates.** The drain block writes the final chunk to memory and `orchestrator.log` but never to `stdout_file`. Affects all 35 steps, every run. No truncation marker. Also allocates an unused `stderr_path` — no `stderr.log` is ever written. |
| 3 | 🔴 | Step 121 | **Has never executed.** Missing from `schedule_manager.py:66`. Same-night sitemap resubmission has never worked since it was built 2026-07-21. |
| 4 | 🔴 | Step 6 | **Overpass HTTP 406 on 100% of live calls**, no retry for 406. 1 of 25 properties valued. |
| 5 | 🟠 | Step 12 | **Pass 3 is 100% dead** (73/73). Scrapes Domain direct from the blocked VM IP instead of Bright Data, and **mislabels blocks as "404"**. ~219 s wasted nightly. |
| 6 | 🟠 | Step 18 | **303 of 540 (56.9%) excluded and existing valuations cleared.** 86% of exclusions are expansion suburbs that never get enrichment. Upstream cause is step 16 writing 85% `N/A` floor areas. |
| 7 | 🟠 | Step 113 | **Never completes** — hits the 40-min budget every night, checks 143 of 214, covers only 3 suburbs. |
| 8 | 🟠 | Coverage scope | **Mudgeeraba, Reedy Creek, Worongary are scraped but barely enriched** (0 satellite, 0 editorial, 0 insights). Four competing definitions of "target market" in code. |
| 9 | 🟠 | `seo_dashboard` | Cron active but **not executing since 2026-07-28**; heartbeat 188.9 h stale. |
| 10 | 🟠 | Step 107 | 416 HIGH errors, **no DB write, no heartbeat**, export to `/tmp`; 78% classified `UNKNOWN`. |
| 10b | 🟠 | Steps 111/113/115 | **3 of 6 scraped suburbs (147 listings) get no withdrawn detection, no price tracking, no sold backfill** (§4.2). Step 111 covers Merrimac — which nothing else touches — but not the three suburbs holding 90% of step 103's misses. |
| 10c | 🟠 | Step 103 | **58 sold listings/night silently discarded** (`not_in_db`, up from 44). 52 of 58 are in step-111-uncovered suburbs, so nothing catches them. |
| 11 | 🟡 | Step 101 | **Discovery regression** — 294/323 (91%) vs 310/311 (99.7%) on 08-03; unresolved 26 → 54; Robina 94/94 → 86/100. |
| 11b | 🟡 | Steps 103/111 | No re-fetch-until-covered loop (step 101 has one), so Domain page yields are unstable — Robina page 1 returned 17 cards to step 103 and 3 to step 111 two minutes later. Derived counts unreliable. |
| 11c | 🟡 | Step 101 | ~44% of detail scrapes are nightly repeats of already-sold/rejected listings; `listing_status` is unconditionally reset to `for_sale` on re-scrape, which can silently revert an `under_contract` flag. |
| 11d | 🟡 | Step 115 / 101 | **Unvalidated price text stored** — `Auction Results` written as a price; `'$1,250.000 +'` typo propagated. 4 of 6 "price changes" on 08-03 had no numeric delta, contaminating `price_change_events`. |
| 12 | 🟡 | Steps 111/114 | Silent skips: step 111 lost a Robina record with no reason and double-counts `matched`/`skipped`; step 114 suffixes colliding slugs silently (the duplicate-public-page mechanism) and prints no per-suburb breakdown. |
| 13 | 🟡 | `refresh-ops-context.py` | Second `data_integrity` writer still emits Merrimac + Carrara as `critical`. |
| 14 | 🟡 | Step 120 | Suburb list hardcoded to 4 **including retired Merrimac**; excludes 3 scraped suburbs; units/townhouses permanently out (`property_type == "House"`). |
| 15 | 🟡 | Step 120 | Fact-checker catches ~11% fabricated claims and invalidated **all 3** draft-1 headlines. One page published with an unresolved flag. Zero prompt caching (1.21 M tokens uncached). |
| 16 | 🟡 | Health board | ~30 STALE heartbeats from the deliberately paused RL block drown genuine staleness. Needs a "paused" state. |
| 17 | 🟢 | Step 17 | Intentional no-op still consuming a slot + 60 s cooldown; registry metadata (30 min, `moderate_write`) now false. |
| 18 | 🟢 | Steps 105/106/108/117 | Named "OpenAI GPT"/"GPT-5.4" but all run Claude. 105/106 lack the `ANTHROPIC_BACKEND=openrouter` the others set. |
| 19 | 🟢 | Data quality | 30 unfixed validator issues nightly; land sizes of 1 m²; floor areas of 7.9 m²; a comparable sale dated **2105-12-10**; duplicate docs processed twice in steps 6 and 18. |
| 20 | 🟢 | Housekeeping | 199 run directories / 165 MB in `logs/runs`, oldest 2026-02-18 — no retention policy. Disk 77%. |

**Verified fixed since the last audit:** blob dead-host in step 106 (54 → 0 failures, +54 plans/night, stable
3 runs) · coverage-check suburb drift (2 false ERRORs → 0) · Domain page-variant parsing (Burleigh Waters
`DOMAIN_UNAVAILABLE` → `OK 56/56`).
