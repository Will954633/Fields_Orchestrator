# Data Quality Agent — Persistent Memory

Write durable learnings here. These persist across runs so you don't re-discover the same issues.

## Format
```
## <Topic>
<What you learned>
**Why it matters:** <context>
**When to recall:** <trigger condition>
```

## Non-Target Suburb Scraping Is Weekly — Do NOT Flag As Critical (Added 2026-03-28)
Non-target suburbs (Carrara, Merrimac, Mudgeeraba, Reedy Creek, Worongary, Burleigh Heads, etc.) are only scraped on Sundays via steps 102 and 104. Showing 5-6 days of staleness mid-week is NORMAL and expected.
**Freshness SLA:** 7 days for non-target suburbs, 12 hours for target suburbs (Robina, Burleigh Waters, Varsity Lakes).
**Why it matters:** Flagging expected weekly staleness as "critical" or recommending "immediate replay" wastes founder attention and generates false urgency. Only flag if staleness exceeds 8 days (missed Sunday run) or if a non-target suburb's coverage gap exceeds 20% of Domain count.
**When to recall:** Any scraper health review, coverage analysis, or staleness assessment for non-target suburbs.

## Buyer-Facing API Health Was A Display Bug, Not A Data Gap (Fixed 2026-03-28)
The "0/4 buyer-facing API health" was caused by a timezone mismatch in `refresh-ops-context.py` (naive vs aware datetime comparison). All 11 endpoints were actually healthy and checked every 30 minutes. The fix normalizes datetime comparisons.
**Why it matters:** Do NOT propose monitoring architecture changes based on the 0/4 display. The health check writer was always correct.
**When to recall:** Any API health trust assessment or proposal about health check completeness guards.

## Floor-Area Schema Fragmentation Is Resolved At Consumer Level (2026-03-27)
Multiple floor-area field paths exist in the DB (~7 variants). This was fixed in `valuation.mjs` with a comprehensive fallback chain, and all 17 affected properties were backfilled. No urgent canonicalization needed.
**When to recall:** Any proposal about floor-area normalization or valuation schema contracts.
