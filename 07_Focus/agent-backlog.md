# Agent Work Backlog — Things That Need Doing

> **Updated:** 2026-03-30
> **Rule:** Agents should work through this list in priority order. Pick the highest-value item within your expertise that you can complete autonomously. Build it, don't just propose it. Then pick the next one.
> **When the backlog is empty, THEN you can stop.**

---

## PRIORITY 1 — Sprint 1 Deliverables (needed by Friday April 4)

### Content Production
- [ ] Write all 7 Facebook post copies for Week 1 (from week-01-content-brief-v2.md) — FINAL versions ready to post
- [ ] Write all 7 Facebook post copies for Week 2 — building the 2-week buffer
- [ ] Write 2 data video transcripts for Week 1 (from content brief)
- [ ] Write 2 data video transcripts for Week 2
- [ ] Write personal insight video talking points for Week 1
- [ ] Review and improve Burleigh Beach video scripts (context/focus/burleigh-beach-video-scripts.md) — verify ALL data claims, find Sydney/Melbourne comparison data, rate hooks against keyword data
- [ ] Draft 2 new Facebook ad creative concepts using proven property-story format with REAL property data
- [ ] Write the CGT article (capital gains tax — top content gap, 30 of 30 PAA questions are CGT)
- [ ] Generate YouTube "Living in Robina" full script (12-15 min, for Sprint 5 filming)

### Lead Capture (Engineering + Product)
- [ ] Build the PostHog event tracking code for price alerts (impression, submit_start, submit_success)
- [ ] Build the PostHog event tracking code for Analyse Your Home
- [ ] Build the Telegram notification function that fires on new lead capture
- [ ] Write the price alert email notification template (what does the email say when a price changes?)

### Decision Feed (Engineering + Product)
- [ ] Audit decision-feed.mjs — does it return live data? What's broken?
- [ ] Generate feed_hook fields for ALL 126 core suburb properties
- [ ] Generate feed_catch fields for ALL 126 core suburb properties
- [ ] Generate feed_quiz fields for core suburb properties
- [ ] Test Decision Feed API endpoint — does it return ranked properties?

### Backup Scraper (Engineering)
- [ ] SSH to scraper VM, audit current Robina coverage vs Domain
- [ ] Identify ALL blocked agencies (403 errors) for Robina
- [ ] Write fix for each blocked agency — test and deploy
- [ ] Build automated coverage comparison report (backup vs primary)

### Ad Optimisation (Growth)
- [ ] Pull current ad performance data and produce specific pause/scale memo with ad IDs
- [ ] Draft the ad reallocation plan — where does the saved $121/week go?
- [ ] Research: what Facebook ad formats are working for RE pages in 2026?

## PRIORITY 2 — Grind / Admin / Accounting

### Email & Accounting
- [ ] Search Will's email for ALL invoices from 2025 — list them for tax return
- [ ] Search for Ray White emails re 46 Balderstone St — extract all rental invoices and expenses
- [ ] Research PAYG amount owed — find the calculation or relevant ATO correspondence
- [ ] Draft the Microsoft refund reply email (DONE — see meeting-prep/)
- [ ] Research WISE bank API — is there a developer API? What data can we pull? How to authenticate?
- [ ] Design the automated expense tracking flow: WISE API → MongoDB → monthly reconciliation

### Tax Preparation
- [ ] Generate a 2025 tax document checklist — what does Will need to gather?
- [ ] Categorise known 2025 expenses by tax category (business, personal, rental property)

## PRIORITY 3 — Infrastructure & System Improvements

### Agent System
- [ ] Build the Fields Chat Agent integration so agents can send messages Will actually sees
- [ ] Fix the context export to include content_research_data reliably (Cosmos sort index issue)
- [ ] Build automated weekly content brief generator script
- [ ] Build engagement tracking system for Facebook posts (daily metric collection by content type)
- [ ] Build the content feedback loop (performance data → next week's content brief)

### Pipeline & Data
- [ ] Fix step 109 coverage reporting — include domain_count, db_count, gap_count, gap_pct
- [ ] Fix weekly OPS freshness to use timestamp-based SLA (not date-based)
- [ ] Build pre-sale report template from valuation + editorial data
- [ ] Design the digital market report PDF layout

## PRIORITY 4 — Research & Case Studies

- [ ] Research Noah Escobar's YouTube method in depth — find more details on the 3-video stack
- [ ] Research Unbounce RE landing page benchmarks — get the full dataset
- [ ] Find 3 more case studies of local services businesses going from 0 to leads via digital
- [ ] Research what Ray Dalio's Dot Collector system looks like in practice — for agent meritocracy (Friday task)
- [ ] Competitive analysis: what are Gold Coast RE agents doing on YouTube right now?
- [ ] Research Facebook engagement benchmarks for pages with <1000 followers in 2026

---

## How to Use This Backlog

1. **Read the full list at the start of your session**
2. **Pick the highest-priority item you can complete autonomously** within your expertise
3. **DO IT** — produce the deliverable, not a proposal about the deliverable
4. **Check it off** (write to agent-memory that you completed it)
5. **Pick the next one**
6. **Keep going until:** you've used your time budget OR the backlog items remaining all need Will's approval
7. **If an item needs Will:** add it to will_tasks.json and move to the next autonomous item
8. **If an item needs Opus:** write request.json and wait for the response, then continue

The backlog is NOT a menu of options. It's a job list. Work through it.
