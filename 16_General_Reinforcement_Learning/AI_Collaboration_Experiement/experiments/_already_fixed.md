# ALREADY FIXED — do not report these again

A previous audit round found and fixed the items below on 2026-08-07/08. Re-reporting any
of them is a **null finding** and will be scored as noise. Finding a *sibling* of one
elsewhere is exactly what is wanted — say which pattern it matches.

## Median / price provenance (six consumers, all resolved)
- `scripts/owner_article/build_owner_article.py` — computed a Domain-only suburb median and
  called it "independently measured"; now reads the provenance-gated union scalar.
- `scripts/backend_enrichment/generate_property_ai_analysis.py` — fed the LLM the
  in-progress quarter labelled "USE THIS FIGURE" ($2,250,000 on n=11 vs canonical
  $1,925,000); now reads the union scalar with CI and sample size.
- `scripts/generate_appraisal_report.py` — inline median $110,000 below the published one,
  plus a "balanced supply and demand" verdict off under-capturing counts. Both fixed.
- `01_Website/netlify/functions/market-narrative.mjs` + the `property-type-race` chart —
  plotted quarterly medians off 2-5 sales in absolute dollars. Chart **withdrawn**
  (`marketMetrics.ts` `available: false`).
- `scripts/fb-page-post.py` — dead median block (read `quarterly_medians`; field is `data`)
  removed.
- `scripts/backend_enrichment/generate_sold_analysis.py` — accepted `listing_price` as a
  sale price in five places; removed, 800 pages republished, 4 retracted.
- `Gold_Coast.suburb_median_prices` is **deliberately retained** with a documented contract
  (long-run trajectory only, never a current median). A rename was considered and rejected:
  the off-market capital-gain chart needs its pre-2016 history and canonical cannot serve
  it. Do not propose renaming or deleting it.

## Silent-failure / monitoring
- `scripts/build_listed_property.py` — cron omitted `set -a` so `BRIGHTDATA_API_KEY` was
  never exported; 11/11 builds failed while `job_run` recorded success. Fixed with
  `load_env()`, an infra-vs-not-listed distinction, and a raise.
- `scripts/google_indexing.py` — submitted 0 URLs for 9 nights, discarded the error,
  advanced its watermark, had no heartbeat. All fixed; migrated to a service account;
  `--since`/`--no-advance` backfill added.
- `scripts/gcp_cost_monitor.py` — reported `MTD $0.00, success` on an empty billing export;
  now raises.
- **CLAUDE.md Rule 7b added** — a heartbeat must assert an outcome, not merely a clean exit.
  Judge remaining jobs against 7b, and cite it.

## Website
- `src/routes/$.tsx` — the catch-all returned HTTP 200 (site-wide soft 404); now 404 +
  noindex.
- `/review/:slug` — hardcoded prototype serving any slug; route removed.
- `netlify/functions/market-insights.mjs` — `.limit(20)` used as the 30-day count (Robina
  served 20/4 against a real 121/22); now a `$group` aggregate.
- `/methodology` + `/accuracy` "90% confidence interval" wording — already corrected and
  deployed before this round.

## Infrastructure
- 400 GB unmounted `fields-blob-storage` deleted (SSD quota 500/500 -> 100/500); backup
  bucket soft-delete extended 7d -> 30d first.
- `property-scraper` stopped (DR disk retained), `searxng-server` and
  `greyhound-betting-vm` deleted.
- ⚠ **The database is NOT Azure Cosmos.** It is self-hosted `mongod` v7.0.31 on
  `localhost:27017`. **RU is not a billed dimension anywhere.** `CLAUDE.md`,
  `SCHEMA_SNAPSHOT.md` and `scripts/cost-collector.py` still say Cosmos — that staleness is
  known. Do not frame anything as an RU cost.
- `scripts/cost-collector.py` books infrastructure as a hardcoded $4.38/day constant,
  understating real spend ~3.3x. **Known, not yet fixed** — do not re-report as new.

## Still open and already known — only report with NEW evidence or a concrete fix
- `01_Website/src/lib/db.server.ts:468` and `src/routes/off-market.$slug.tsx:267` read
  `suburb_median_prices` for the capital-gain chart. This is the sanctioned trajectory use.
- `gcp_cost_monitor.py` has a single hardcoded `BILLING_ACCOUNT`, so project
  `property-data-scraping-477306` is invisible to cost tooling.
- `appraisal_pipeline` has no `mailed`/`dispatched`/`delivered` field; 126 print-only
  appraisals, 39 addresses cleared, 0 posted, no vendor integration.
- `hot_lead_responder.py` fails on every run (`claude -p` without stripping
  `ANTHROPIC_API_KEY`), 1,933 times, no heartbeat.
- `keep_warm_forsale_v3.py` hits a CDN cache (`s-maxage=300`) so it can neither warm the
  function nor detect its failure.
- `system_monitor.leads` is append-only — nothing ever moves `status` off `"new"` or sets
  `first_response_at`.
- `offmarket_intel_poller` swallows resolver exceptions, writes `status: "done"`, never
  retries; 231 deck pages missing narrative.
