## Step 116 Now Exits 0 For Violations Found (Fixed 2026-03-28)
Step 116 (`data_quality_validator.py`) previously exited 1 whenever it found unfixed violations, which made the entire pipeline show as "failed" even when the validator was working correctly. This also cascaded to skip step 107 (Database Audit).
**Fix applied:** Exit code is now always 0 for normal operation (both `passed` and `violations_found`). Exit 1 only on `execution_failed` (uncaught exception). The structured `OUTCOME:` line in stdout distinguishes the three states.
**Why it matters:** The pipeline should not go red because the validator found data quality issues — those are expected findings, not failures.
**When to recall:** Any step 116 triage, orchestrator-health discussion, or validator refactor.

## API Health Display Bug Was Timezone Mismatch (Fixed 2026-03-28)
The "0/4 buyer-facing API health" issue was NOT a missing write problem. All 11 endpoints were healthy and being checked every 30 minutes. The bug was in `refresh-ops-context.py`: it queried with `datetime.utcnow()` (naive) but `api-health-check.py` stores `datetime.now(timezone.utc)` (aware). The `$gte` comparison silently returned no results.
**Fix applied:** `fetch_api_health()` now queries with both aware and naive cutoffs via `$or`, and the stale gate normalizes datetimes before comparison.
**Why it matters:** Do NOT propose completeness guards or write-path changes for api-health-check.py based on the 0/4 display — the writer was always correct. The reader was broken.
**When to recall:** Any OPS health display issue, api-health-check discussion, or proposal about health check architecture.

## Non-Target Suburb Scraping Is Weekly (Sunday Only)
Non-target suburbs (Carrara, Merrimac, Mudgeeraba, Reedy Creek, Worongary, Burleigh Heads, etc.) are scraped ONLY on Sundays via steps 102 and 104. This means up to 7 days of staleness mid-week is completely normal.
**Freshness SLA:** 7 days for non-target, 12 hours for target suburbs (Robina, Burleigh Waters, Varsity Lakes).
**Why it matters:** Do NOT flag 5-6 day staleness in non-target suburbs as "critical" or recommend "immediate replay". Only flag if staleness exceeds 8 days (missed a Sunday run).
**When to recall:** Any scraper health review, coverage analysis, or proposal about replaying non-target suburbs.

## Floor-Area Field Fragmentation Already Resolved (2026-03-27)
The floor-area schema has ~7 field paths in the DB (`house_plan.floor_area_sqm`, `enriched_data.floor_area_sqm`, `floor_plan_analysis.internal_floor_area`, etc.). This was fixed on 2026-03-27 ([VALUATION-FLOOR-001]) by adding a comprehensive fallback chain in `valuation.mjs` and backfilling all 17 affected properties.
**Status:** Consumer-side resolved. The underlying DB fragmentation exists but is fully handled. No urgent action needed.
**When to recall:** Any valuation display issue or proposal about floor-area normalization.
