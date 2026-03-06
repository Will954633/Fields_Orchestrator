# Sold Property Detection — Pipeline Analysis & Improvement Opportunities

**Date:** 2026-03-06
**Scope:** Step 103/104 (`monitor_sold_properties.py`) + new backfill scraper + downstream impacts

---

## Current Architecture

### How sold detection works today

```
Step 101 (nightly)          Step 103 (nightly)
Scrape for-sale listings    For each listing_status="for_sale" doc:
from Domain search results    -> Open its listing_url in headless Chrome
-> Insert/update in           -> Check 4 HTML signals for "sold" status
   Gold_Coast.<suburb>        -> If sold: update doc in-place
                                 (listing_status -> "sold",
                                  sold_date, sale_price, sales_history)
```

### The fundamental gap

Step 103 is **reactive** — it only monitors properties we already know about. It answers: _"Has this listing we're tracking been sold?"_ It does NOT answer: _"What has sold in this suburb recently?"_

Properties missed by this approach:
1. **Never scraped** — sold before step 101 ever picked them up (short DOM listings, off-market sales)
2. **Delisted then sold** — agent removed the listing, relisted as sold later (step 101 wouldn't re-scrape a URL it already has)
3. **Inter-cycle gap** — listed and sold between two nightly scrape runs (especially weekday sales with fast turnaround)
4. **Non-target suburbs** — steps 102/104 only run Sundays, so 6 days of sales in non-target suburbs go unmonitored

The backfill scraper (`scrape_recent_sold.py`) addresses gap #1-3 retrospectively but isn't integrated into the nightly pipeline.

---

## Improvement Opportunities

### 1. Integrate sold-listings scrape into the nightly pipeline (HIGH IMPACT)

**Problem:** The backfill scraper is a manual ad-hoc tool. The nightly pipeline only does reactive monitoring (step 103).

**Proposal:** Add a new step (e.g. **step 111**) that runs `scrape_recent_sold.py --days 7` every night, right after step 103. This catches any sales from the past week that the reactive monitor missed. The `--days 7` window is deliberately overlapping — the script's idempotent matching means duplicates are harmlessly skipped.

**Config change:**
```yaml
- id: 111
  name: "Sold Listings Backfill (Target Market)"
  phase: "monitoring_target"
  command: "python3 scripts/scrape_recent_sold.py --days 7"
  working_dir: "/home/fields/Fields_Orchestrator"
  requires_browser: true
  estimated_duration_minutes: 10
  depends_on: [103]
```

**Why it's fast:** The search results scraper extracts data from listing cards (20 per page, ~5 seconds per page). For 7 days of data, that's typically 1-2 pages per suburb = ~30 seconds per suburb. Versus step 103 which opens every individual property page (~5-7 seconds each, 40-60 properties).

---

### 2. Eliminate per-property page visits in step 103 (HIGH IMPACT)

**Problem:** Step 103 opens a Chrome page for every active listing (~120 properties across 3 suburbs). At 5-7 seconds per page load, that's 10-14 minutes minimum. If pages are slow/blocked, it balloons to 60+ minutes. It also consumes significant memory (Chrome + DOM per page).

**Proposal:** Replace the per-property check with a **search-results-based approach**:
1. Load `domain.com.au/sold-listings/<suburb>/?ssubs=0` (the same page the backfill scraper uses)
2. Get all sold listing IDs from the first 1-2 pages (most recent ~40 sales)
3. Compare those listing IDs against our `listing_status: "for_sale"` records
4. Any match = confirmed sold. Extract sold date + price from the card.
5. Only visit individual pages for edge cases (price withheld properties where we want agent details)

**Benefits:**
- **Speed:** 2-3 page loads instead of 120 (97% reduction)
- **Memory:** One Chrome tab instead of sequential 120
- **Reliability:** Search results rarely fail; individual pages sometimes 403/timeout
- **Data quality:** Search cards have standardised sold date + price format (easier to parse than 4 different detection methods on property pages)

**Risk:** Properties sold >2 pages back (~40 results) could be missed. Mitigated by running nightly — with 1-3 sales per day per suburb, the first page always covers the last week.

---

### 3. Add sold price to records with "Price Withheld" (MEDIUM IMPACT)

**Problem:** 7 of 128 scraped sold records had `None` for sale_price (price withheld on Domain). For valuations and market analysis, these missing prices create gaps.

**Proposal:** For "price withheld" properties, open the individual property page and try secondary price extraction:
- `og:price:amount` meta tag (sometimes present even when display says "withheld")
- `"price"` field in the `__NEXT_DATA__` JSON embedded in the page
- CoreLogic / RP Data cross-reference (if available via API)

Alternatively, flag these for manual review — Will may be able to find the price via agent contacts or auction results.

---

### 4. Detect "Under Contract" / "Under Offer" as a pre-sold state (MEDIUM IMPACT)

**Problem:** The current system only has two states: `for_sale` and `sold`. Properties go "Under Contract" or "Under Offer" before settlement, sometimes for 2-6 weeks. During this time, the property is effectively off the market but still shows as `for_sale` in our data.

**Proposal:** Add `listing_status: "under_contract"` as an intermediate state:
- Step 103 already loads each property page — check for "Under Contract" / "Under Offer" / "Deposit Taken" text
- Track `under_contract_date` and `under_contract_detected_at`
- This gives early warning of upcoming sold records and makes the for-sale page more accurate (removing properties that are no longer genuinely available)

**Downstream impact:** The for-sale API filter would need `{"listing_status": "for_sale"}` to remain unchanged (excluding under contract), but the website could show these properties with a "Under Contract" badge.

---

### 5. Cross-reference sold dates with listing dates for data quality (MEDIUM IMPACT)

**Problem:** Some sold records have `sold_date` but no `first_listed_date` or `first_listed_timestamp`, so we can't calculate days-on-market. The backfill scraper inserts records with sold_date but no listing history.

**Proposal:** After step 111 (sold backfill), run a lightweight enrichment pass that:
1. For each `listing_status: "sold"` record missing `first_listed_timestamp`:
   - Check if the property was ever tracked as `for_sale` (match by address in `change_detection_snapshots`)
   - If found, copy the `first_listed_timestamp` from the snapshot
   - If not found, try to extract `dateListed` from the property page's JSON-LD data
2. Calculate `days_on_market` wherever both dates exist

---

### 6. Track sale method + agent for sold analytics (LOW IMPACT, EASY)

**Problem:** The backfill scraper captures `sale_method` (private treaty / auction) from search cards, but the reactive monitor (step 103) does not. Agent names are extracted but not consistently structured.

**Proposal:**
- Add `sale_method` extraction to `monitor_sold_properties.py` (check for "private treaty" / "auction" in the sold tag text)
- Standardise agent data: `selling_agent` (name), `selling_agency` (name), both extracted from the property page at detection time
- This enables future analytics: average days on market by agent, auction clearance rates, price accuracy (listing vs sold) by agency

---

### 7. Add sold-detection to the coverage check (LOW IMPACT)

**Problem:** Step 109 (coverage check) compares our for-sale count to Domain's for-sale count. It doesn't check sold coverage at all.

**Proposal:** Extend `coverage_check.py` to also compare:
- Our sold count (last 30 days) vs Domain's sold count for the same period
- Flag any suburb where our count is significantly lower (e.g. >20% gap)
- This would have caught the 88-record gap earlier

---

### 8. Deduplicate sold records from multiple sources (LOW IMPACT, PREVENTIVE)

**Problem:** We now have sold records from three sources:
1. Step 103 reactive monitor (sets `detection_method`)
2. Backfill scraper (sets `sold_scrape_source: "domain_sold_listings_backfill"`)
3. Historical merge from `Target_Market_Sold_Last_12_Months` (sets `sold_scrape_source: "target_market_merge"`)

If a property appears in multiple sources, it could have slightly different addresses or listing URLs, leading to duplicates.

**Proposal:** Add a periodic deduplication check (run weekly or after backfill):
- Group sold records by normalized address within each suburb collection
- Where multiple docs share the same address and `listing_status: "sold"`, merge into one (keep the one with the richest data)
- Log merges to fix-history for transparency

---

## Priority Summary

| # | Opportunity | Impact | Effort | Recommendation |
|---|-----------|--------|--------|---------------|
| 1 | Integrate backfill into nightly pipeline | High | Low | Do now — add step 111 |
| 2 | Replace per-property checks with search-based detection | High | Medium | Do next — biggest speed/reliability win |
| 3 | Recover withheld prices | Medium | Low | Quick win — add fallback extraction |
| 4 | Track "Under Contract" state | Medium | Medium | Plan for next sprint |
| 5 | Cross-reference listing dates for DOM calculation | Medium | Low | Add as enrichment step |
| 6 | Standardise agent/method on sold records | Low | Low | Add alongside #2 |
| 7 | Sold coverage in coverage check | Low | Low | Quick addition to step 109 |
| 8 | Deduplication pass | Low | Low | Weekly maintenance script |

---

## Files Referenced

| File | Purpose |
|------|---------|
| `monitor_sold_properties.py` | Step 103/104 — reactive sold monitor (per-property page visits) |
| `scripts/scrape_recent_sold.py` | New backfill scraper (search results based) |
| `config/process_commands.yaml` | Pipeline step definitions |
| `src/orchestrator_daemon.py` | Pipeline scheduler |
| `src/task_executor.py` | Step execution engine |
| `scripts/coverage_check.py` | Step 109 — Domain vs DB count comparison |
| `scripts/database_audit.py` | Step 107 — data quality audit |
