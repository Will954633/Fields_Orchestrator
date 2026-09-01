# Property Data & Asset Index

> **Generated 2026-09-01 12:51 AEST** by `scripts/generate_property_data_index.py` (weekly). Do NOT hand-edit — regenerate. Companion: `PROPERTY_DATA_INDEX.tsv` (every field, tagged, grep-able).

## ⛑ Retrieval procedure (read before claiming data is missing — Rule 8)

1. **Any field:** `grep <tag> PROPERTY_DATA_INDEX.tsv` or `python3 scripts/db_fields.py --find <word>` — never a guessed name.
2. **Photos:** follow *Photo resolution order* below verbatim — it is the same order the live site uses (`extractPhotos`).
3. **Verify over HTTP, not the VM disk.** This VM's `/data/blobs` is a PARTIAL mirror. A 404 on `blobs.fieldsestate.com.au` is truth; a missing local dir is not.


## 📸 Photo resolution order (canonical — from `shared-utils.mjs`)

1. v2 scrape fields              — Domain CDN, freshest (post-shutdown)
2. `scraped_data_apr01_recovered` — Apr 1 mongodump sidecar, Domain CDN (Phase 1 recovery — 204,702 properties; APR01-MERGE-01, 2026-05-15)
3. `scraped_data_recently_sold_apr01_recovered` + `_for_sale_apr01_recovered`
4. `property_images_original`    — Domain CDN (rewritten to b.domainstatic.com.au)
5. `scraped_property_images`     — Domain CDN raw scrape
6. `photo_tour_order`            — GPT-ordered photo tour. May include dead Azure URLs which are filtered out.
7. `property_images`             — Azure mirror, mostly dead since 2026-05-13. Kept in the chain so any non-Azure entries still work.
8. `image_analysis`              — visual-pipeline output, mixed sources.
9. `scraped_data.images`         — cadastral scrape, mostly Azure (dead). Always filters dead hosts. Dedupes preserving first occurrence (which gives priority-1 sources the front-of-list spot in the gallery).

**Floor plans:**
1. `floor_plans_v2_extracted`  — GPT-4o-mini vision classifier output from v2 scrape image arrays (COVERAGE-AUDIT-004, 2026-05-18). Domain CDN. Covers ~1,588 Robina records (13%) including never-listed cadastral.
2. `floor_plans_original`      — Domain CDN URLs preserved from when the property was actively listed. ~390 Robina records.
3. `scraped_floor_plans`       — older scrape field, mostly empty now.
4. `floor_plans`               — Azure mirror, mostly dead since 2026-05-13. Kept last so any non-Azure entries still work. Same dead-host filter as photos.

> ⚠ The mini-site (`/yourhome`, `property_reports.property.photos[]`) mirrors the chosen Domain photos to **our own blob** under `property-images/reports/<suburb>/<id>/` at build time. That is where we hold owned copies of off-market facades — not `gold_coast/` (that path's URLs are dead Azure).


## 🗂 Asset field catalog (sampled, live)

| Field path | Asset type | Host(s) | Status | Coverage |
|---|---|---|---|---|
| `living_map.tiles.city` | living_map | `blobs.fieldsestate.com.au` | 🟢OWNED | 1118/1200 (93%) |
| `living_map.tiles.suburb` | living_map | `blobs.fieldsestate.com.au` | 🟢OWNED | 1118/1200 (93%) |
| `aerial_boundary_url` | aerial | `blobs.fieldsestate.com.au` | 🟢OWNED | 836/1200 (70%) |
| `scraped_data.images[].url` | facade_gallery | `fieldspropertyimages.blob.core.windows.net` | 🔴DEAD | 808/1200 (67%) |
| `cadastral_photo_url` | cadastral_street | `blobs.fieldsestate.com.au` | 🟢OWNED | 652/1200 (54%) |
| `living_map.tiles.house` | living_map | `blobs.fieldsestate.com.au` | 🟢OWNED | 455/1200 (38%) |
| `living_map.tiles.street` | living_map | `blobs.fieldsestate.com.au` | 🟢OWNED | 454/1200 (38%) |
| `valuation_data.recent_sales[].images[]` | facade_gallery | `fieldspropertyimages.blob.core.windows.net`<br>`blobs.fieldsestate.com.au`<br>`bucket-api.domain.com.au` | 🔴DEAD 🟢OWNED 🟢DOMAIN | 445/1200 (37%) |
| `floor_plans_v2_classifier.candidates[].url` | floor_plan | `rimh2.domainstatic.com.au`<br>`images.corelogic.asia`<br>`bucket-api.domain.com.au` | 🔴DOMAIN 🟢OTHER 🟢DOMAIN | 328/1200 (27%) |
| `scraped_data_apr01_recovered.images[].url` | facade_gallery | `rimh2.domainstatic.com.au` | 🔴DOMAIN | 273/1200 (23%) |
| `domain_image_urls[]` | facade_gallery | `rimh2.domainstatic.com.au` | 🔴DOMAIN | 262/1200 (22%) |
| `scraped_data_v2.image_urls[]` | facade_gallery | `rimh2.domainstatic.com.au` | 🔴DOMAIN | 262/1200 (22%) |
| `domain_hero_image_url` | hero_facade | `rimh2.domainstatic.com.au` | 🔴DOMAIN | 260/1200 (22%) |
| `scraped_data_v2.hero_image_url` | hero_facade | `rimh2.domainstatic.com.au` | 🔴DOMAIN | 260/1200 (22%) |
| `floor_plans_v2_extracted[]` | floor_plan | `bucket-api.domain.com.au` | 🟢DOMAIN | 242/1200 (20%) |
| `property_images[]` | facade_gallery | `blobs.fieldsestate.com.au`<br>`bucket-api.domain.com.au`<br>`fieldspropertyimages.blob.core.windows.net` | 🔴DEAD 🟢OWNED 🟢DOMAIN | 75/1200 (6%) |
| `property_images_original[]` | facade_gallery | `bucket-api.domain.com.au` | 🟢DOMAIN | 72/1200 (6%) |
| `satellite_analysis.satellite_image_url` | satellite | `fieldspropertyimages.blob.core.windows.net`<br>`blobs.fieldsestate.com.au` | 🔴DEAD 🟢OWNED | 57/1200 (5%) |
| `floor_plans[]` | floor_plan | `fieldspropertyimages.blob.core.windows.net`<br>`blobs.fieldsestate.com.au` | 🔴DEAD 🟢OWNED | 54/1200 (4%) |
| `image_history[].urls[]` | facade_gallery | `blobs.fieldsestate.com.au`<br>`fieldspropertyimages.blob.core.windows.net` | 🟢OWNED 🔴DEAD | 33/1200 (3%) |
| `scraped_property_images[]` | facade_gallery | `bucket-api.domain.com.au` | 🟢DOMAIN | 28/1200 (2%) |
| `valuation_data.subject_property.images[]` | facade_gallery | `blobs.fieldsestate.com.au`<br>`bucket-api.domain.com.au` | 🟢OWNED 🟢DOMAIN | 28/1200 (2%) |
| `oth_image_urls[]` | facade_gallery | `images.corelogic.asia` | 🟢OTHER | 21/1200 (2%) |
| `ollama_image_analysis[].url` | facade_gallery | `bucket-api.domain.com.au`<br>`blobs.fieldsestate.com.au` | 🟢DOMAIN 🟢OWNED | 13/1200 (1%) |
| `photo_tour_order[].url` | facade_gallery | `bucket-api.domain.com.au`<br>`blobs.fieldsestate.com.au` | 🟢DOMAIN 🟢OWNED | 13/1200 (1%) |
| `street_view_analysis.street_view_image_url` | street_view | `blobs.fieldsestate.com.au` | 🟢OWNED | 8/1200 (1%) |
| `floor_plans_oth_extracted[]` | floor_plan | `images.corelogic.asia` | 🟢OTHER | 7/1200 (1%) |
| `satellite_analysis.annotated_image_url` | satellite | `blobs.fieldsestate.com.au` | 🟢OWNED | 3/1200 (0%) |
| `ollama_floor_plan_analysis.floor_plan_data.floor_plan_url` | floor_plan | `blobs.fieldsestate.com.au`<br>`fieldspropertyimages.blob.core.windows.net` | 🟢OWNED 🔴DEAD | 2/1200 (0%) |
| `oth_floorplan_urls[]` | floor_plan | `images.corelogic.asia` | 🟢OTHER | 2/1200 (0%) |
| `valuation_data.comparables[].images[]` | facade_gallery | `bucket-api.domain.com.au`<br>`blobs.fieldsestate.com.au` | 🟢DOMAIN 🟢OWNED | 2/1200 (0%) |
| `scraped_data_for_sale_apr01_recovered.ollama_image_analysis[].url` | facade_gallery | `bucket-api.domain.com.au` | 🟢DOMAIN | 1/1200 (0%) |
| `scraped_data_for_sale_apr01_recovered.ollama_photo_tour_order[].url` | facade_gallery | `bucket-api.domain.com.au` | 🟢DOMAIN | 1/1200 (0%) |
| `scraped_data_for_sale_apr01_recovered.property_images[]` | facade_gallery | `bucket-api.domain.com.au` | 🟢DOMAIN | 1/1200 (0%) |

_Status legend: 🟢 live · 🔴 dead · ⚪ unprobed · DEAD=retired Azure · OWNED=our blob · DOMAIN=external CDN (rotates)._


## 💾 Blob storage layout (`/data/blobs/property-images/` on blob host)

| Root | Files (this VM's partial mirror) | Holds |
|---|---|---|
| `aerial/` | 23,566 | Living-Map boundary aerials (generated here) |
| `all/` | 680 | Satellite/aerial per property |
| `appraisal/` | 1 |  |
| `articles/` | 16 |  |
| `cadastral/` | 461,098 | Street-level cadastral photos |
| `for_sale/` | 338,523 | On-market listing photos (kept fresh) |
| `gold_coast/` | 309,843 | Legacy listing-photo path — URLs in DB are DEAD Azure |
| `livingmap/` | 25,058 | Living-Map tiles (house/street/suburb) |
| `reports/` | 44 | **Owned facade mirror per built mini-site** — the off-market photos we hold |
| `sold/` | 40,127 | Sold listing photos |

> ⚠ Counts above are THIS VM's disk, a partial mirror. Truth = HTTP GET `https://blobs.fieldsestate.com.au/property-images/<root>/...`.


## 🏷 Field dictionary — tag summary (Gold_Coast target suburbs)

| Domain tag | # field paths |
|---|---|
| valuation | 2640 |
| physical_attributes | 1776 |
| images_assets | 819 |
| other | 796 |
| identity_location | 757 |
| listing_scrape | 246 |
| editorial_ai | 202 |
| transactions_history | 138 |
| pipeline_meta | 66 |
| market_metrics | 60 |
| offmarket_report | 21 |

Full tagged list: **`PROPERTY_DATA_INDEX.tsv`** (7521 paths). Example: `grep -P '\timages_assets\t' PROPERTY_DATA_INDEX.tsv`.

