# Chief of Staff — Persistent Memory

Write durable learnings here. These persist across runs so you don't re-discover the same issues.

## Format
```
## <Topic>
<What you learned>
**Why it matters:** <context>
**When to recall:** <trigger condition>
```

## Non-Target Suburb Staleness Is Expected — Weekly Cycle (Added 2026-03-28)
Non-target suburbs are scraped only on Sundays (steps 102, 104). Mid-week staleness of 5-6 days is normal. Only escalate if staleness exceeds 8 days (missed Sunday run) or coverage gap exceeds 20% of Domain count.
**Target suburb SLA:** 12 hours. **Non-target suburb SLA:** 7 days.
**Why it matters:** The 2026-03-28 run incorrectly escalated normal weekly staleness in Carrara, Merrimac, Mudgeeraba, Reedy Creek, and Worongary as "critical" and recommended "immediate replay". This wasted the top-3 priority list on a non-issue.
**When to recall:** Any synthesis involving scraper health, coverage risk, or replay recommendations for non-target suburbs.

## Three Issues Resolved Before 2026-03-28 Run — Do Not Re-Propose (Added 2026-03-28)
1. **API health 0/4 display:** Was a timezone mismatch bug in `refresh-ops-context.py`, not a missing writer. Fixed 2026-03-28. All APIs were healthy.
2. **Step 116 exit code:** Was exiting 1 on violations_found, making pipeline red. Fixed 2026-03-28 to exit 0 for findings, 1 only for execution failure.
3. **Floor-area field fragmentation:** Resolved 2026-03-27 with fallback chain in `valuation.mjs` + backfill of 17 properties.
**Why it matters:** Future runs should verify these fixes are holding rather than re-proposing them.
**When to recall:** Any synthesis that references API health trust, step 116 failures, or floor-area schema.
