# Backup Scraper Assessment

## Snapshot Verdict

The backup scraper is running, but it is not failover-ready.

## Current Robina Coverage

- The latest exported Robina pass (`Cycle 7247`) found `62` listing URLs and `54` unique Robina addresses during direct-agency scraping.
- `context/metrics/data_coverage.json` and `context/OPS_STATUS.md` show the primary DB currently has `55` active Robina listings.
- That means the direct-agency Robina pass is currently covering about `54 / 55 = 98.2%` of the primary active Robina listing count.

Important limitation:

- This is only a Robina direct-agency comparison, not a full backup-vs-Domain completeness proof.
- Step 109 still marks Robina `critical`, so the primary stack itself does not currently prove complete Robina coverage versus Domain.
- The backup runtime is also only operating on Robina, so it is not meeting the documented three-suburb contract.

## Agencies Currently Blocked

From the latest Robina direct-agency pass:

- `RE/MAX GC` is blocked with `HTTP 403` on `https://www.remaxgc.com.au/buy`
- `Coastal` is blocked with `HTTP 403` on `https://www.coastal.com.au/properties-for-sale/`

## Agencies With Low Or Zero Yield But Not Explicitly Blocked

- `Ray White Malan & Co`: `0` listing URLs, `0` addresses
- `GCSR`: `0` listing URLs, `0` addresses
- `First National Robina`: `0` listing URLs, `1` address

These are not confirmed hard blocks from the exported evidence. They may be empty inventory, page-structure drift, or parsing gaps.

## Other Operational Risks

1. Runtime scope mismatch
   `context/backup-scraper/code/url_tracking_run.py` initializes `ContinuousMonitor(suburbs=['robina'])`, while `context/config/ceo_founder_truths.yaml` says the backup scraper should cover `robina`, `burleigh_waters`, and `varsity_lakes`.

2. Zero-discovery drift
   The latest status snapshot still shows `[Pass 0 done] 0 new URLs processed`, and the recent log excerpt also shows zero new URLs discovered in the latest cycle summary.

3. Thin health surface
   The process is "running", but there is no structured per-cycle heartbeat proving expected suburbs, discovery counts, or agency-block streaks.

4. Large unrotated log
   `directory_listing.txt` shows `scraper.log` at `98,843,023` bytes.

## Prototype Fix Added

I added `engineering/sprint1_prework/backup_scraper_agency_fallback_prototype.py`.

What it does:

- Adds sitemap-based fallback parsing for agencies whose listing-index pages return `403` or `429`
- Supports sitemap index recursion and URL-set parsing
- Filters URLs by allowed domain, listing-path pattern, and suburb token
- Includes ready-to-use fallback configs for `RE/MAX GC` and `Coastal`
- Includes self-check tests so the parser logic can be validated offline

Why this is the right level of prototype:

- The exported evidence proves the current failure mode is agency-index blocking.
- We do not have live network access here to verify the exact public sitemap endpoints.
- A sitemap fallback is low-risk, easy to integrate into `direct_agency_scraper.py`, and directly targets the current 403 class without changing the rest of the extraction pipeline.

## Recommended Next Moves

1. Restore runtime suburb scope to `robina`, `burleigh_waters`, `varsity_lakes`.
2. Add a structured heartbeat after each cycle with suburb list, pass-0 discoveries, recheck count, and agency 403 counts.
3. Trial the sitemap fallback first on `RE/MAX GC` and `Coastal`.
4. Re-run Robina comparison after the fallback and report:
   `listing_urls`, `unique_addresses`, and `new addresses not previously seen`.

Status: STOP
