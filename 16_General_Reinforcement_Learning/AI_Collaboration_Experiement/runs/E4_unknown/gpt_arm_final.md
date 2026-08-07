# gpt_arm_final

Model `gpt-5.6-terra` via openai · recovered from 49 recorded tool calls · 27,744 in / 4,290 out · ~$0.08

## FINDING 1: Turn the existing seasonality model into a homeowner sale-timing tool
CATEGORY: conversion
CLAIM: Fields already holds six suburb-level sale-seasonality datasets, including a Robina house-sales model built from 2,771 sales, but the website has no literal consumer of `precomputed_seasonality`, so this evidence is presently applied to appraisal/report generation rather than directly capturing homeowner intent.
EVIDENCE: `SCHEMA_SNAPSHOT.md:5000-5170` records `precomputed_seasonality` (6 documents) and the Robina sample (`totalSales: 2771`, 2015–2026, monthly premium and sale-count series); `scripts/refresh_property_reports.py:996-1022` reads that collection and inserts its output into report seasonality; `grep -R -n 'precomputed_seasonality' /home/fields/Feilds_Website/01_Website --exclude-dir=node_modules` returned no matches (tool call 42); `https://fieldsestate.com.au/analyse-your-home` returned HTTP 200 (tool call 28).
STATUS: VERIFIED — I verified the dataset count and sample size, the report-generation read path, and the absence of a literal website reference; the expected conversion benefit is inferred.
IMPACT: A timing tool could make the existing 2,771-sale Robina evidence actionable for every relevant homeowner rather than only people who complete the appraisal workflow; no visitor, lead, or sale-to-lead data was available, so leads or revenue uplift cannot be quantified.
CONFIDENCE: MEDIUM
EFFORT: 1–2 days
PROPOSED ACTION: Add a “When does this suburb usually achieve its strongest sale premium?” module after address selection on `/analyse-your-home`, using only `precomputed_seasonality` records that meet the existing sample guard; show the monthly sale count, peak/trough month, methodology, and a clear statement that seasonality is not a price forecast. Track module exposure, address completion, and appraisal-lead conversion against a no-module baseline.
FALSIFIED BY: A production website source or network trace shows that the address-analysis flow already fetches and renders `precomputed_seasonality` to homeowners, or experiment data shows no incremental address completion or lead conversion.

## FINDING 2: Complete the 31-record PropRadar recovery queue into address-search and off-market coverage
CATEGORY: growth
CLAIM: Fields has a finite queue of 31 `propradar_coverage_gaps` records and implemented a recovery process that can scrape and stage full property profiles, but its code deliberately stops before promotion into live suburb documents or public pages.
EVIDENCE: `SCHEMA_SNAPSHOT.md:5000-5170` lists `propradar_coverage_gaps` with 31 documents and fields including `address`, `suburb_key`, `status`, and `source`; `scripts/propradar/enrich_coverage_gaps.py:1-10` defines recovery into the staging collection `propradar_gap_enriched`; `scripts/propradar/enrich_coverage_gaps.py:36-60` constructs staged records from a fetched profile and, on apply, writes the staged record and marks the gap enriched; `scripts/propradar/enrich_coverage_gaps.py:1-10` explicitly states that promotion to live docs/pages is a separate gated step.
STATUS: VERIFIED — I verified the 31-record queue and the implemented staging path; the likely acquisition value of recovering those addresses is inferred.
IMPACT: The maximum immediately identifiable expansion is 31 queued addresses. Each successfully promoted address could improve the completeness of address search, property intelligence, and off-market discovery; no successful-enrichment count, staging-document count, search demand, or lead conversion data was available, so realised coverage and revenue impact could not be established.
CONFIDENCE: MEDIUM
EFFORT: 2–4 days
PROPOSED ACTION: Run a read-only validation report first: group all 31 gaps by suburb and status, test fetch success, detect canonical-address twins against live collections, and report sold-timeline completeness. Then implement an explicitly reviewed promotion job that writes only deduplicated, provenance-labelled records with stable slugs, adds them to the address index, and retains the PropRadar source link and recovery timestamp. Measure promoted records, indexable property pages, and address-search resolution before and after.
FALSIFIED BY: A current database audit shows that all 31 gap records are already represented by canonical live-property documents and address-index entries, or that the staged recoveries contain no usable property/timeline data after deduplication.

## COVERAGE
CHECKED: `CLAUDE.md`; the available sections of `SCHEMA_SNAPSHOT.md`; the fix-history files surfaced by the investigation, especially `logs/fix-history/2026-08-06.md` and `logs/fix-history/2026-08-07.md`; website source-file inventory; website literal-reference searches for `precomputed_seasonality`, appraisal substantiation, property attributes, and satellite/floor-plan fields; seasonality report-generation code; PropRadar enrichment code; appraisal archival code; the live `/for-sale-v3` and `/analyse-your-home` HTTP responses.
NOT CHECKED: Live Cosmos document samples and aggregations for the candidate collections, because both attempted `mongo_query` calls failed with `Cursor.__init__() got an unexpected keyword argument 'maxTimeMS'` (tool calls 20–21); the contents/count of `propradar_gap_enriched`; the scheduler/cron paths proving how often seasonality and PropRadar jobs run; website analytics, search-console data, PostHog funnels, CRM outcomes, and revenue data; a full source-wide reader/writer map, as recursive repository greps timed out (tool calls 44–45 and 49).
MOST LIKELY BLIND SPOT: Collections or fields that are populated but read through dynamically constructed Mongo collection names or indirect service calls; the failed database-query tool and timed-out repository-wide searches mean I could not safely classify additional assets as genuinely unused.
