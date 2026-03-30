# Sprint 2 — Decision Feed Launch + Funnel Optimisation

> **Week of:** April 7-11, 2026
> **Sprint focus:** Launch Decision Feed with live data, optimise the capture path that's working, scale winning ads
> **If we only achieve one thing:** Decision Feed live with real data and routed Facebook traffic
> **Q3 countdown:** 85 days
> **Depends on:** Sprint 1 GO gate — feed_hook fields 80+, decision-feed.mjs returning live data, at least one capture path with conversion data
>
> **Agent feedback incorporated:**
> - Product: Split Decision Feed launch into thin launch → enrichment (not Big Bang Monday)
> - Growth: Add lead follow-up workflow checkpoint
> - Chief of Staff: Do not route major paid traffic until capture path is proven somewhere
> - Data Quality: Formal readiness gate before launch

---

## Pre-Sprint Gate (Monday AM)

Before starting Sprint 2, verify:
- [ ] Sprint 1 primary capture path (price alerts) has conversion data
- [ ] Feed_hook fields generated for 80+ core suburb properties
- [ ] `decision-feed.mjs` returning live ranked data
- [ ] PostHog event tracking firing correctly

**If NO-GO:** Sprint 2 becomes "complete Sprint 1 readiness" — finish feed_hook generation, fix backend, get capture data. Don't proceed without the foundation.

---

## Daily Checkpoints

### Monday April 7 — Decision Feed Thin Launch

**CHECKPOINT:** Decision Feed live with real data (thin version)
- [ ] `DecisionFeedPage` rendering real property data from API
- [ ] Cards display: hook lines, property data, ranking visible
- [ ] Basic feed scroll working (property cards + lead capture CTA at end)
- [ ] PostHog tracking on Decision Feed: `feed_impression`, `card_view`, `card_expand`, `scroll_depth`, `cta_click`
- [ ] NOT required today: quiz cards, compare cards, surprise cards, view counts (enrichment through the week)

**AI parallel:** Generate remaining feed_hook fields (target 126/126 by Wednesday). Start ad budget reallocation memo.
**GRIND:** Email triage
**CONTENT:** Review this week's content brief. Schedule posts.

---

### Tuesday April 8 — Decision Feed Enrichment + Lead Follow-Up SOP

**CHECKPOINT:** Quiz/compare/interaction cards added + lead workflow defined
- [ ] Quiz cards and compare cards rendering with real data
- [ ] View counts on cards (PostHog aggregation or counter)
- [ ] **Lead follow-up SOP documented:** When Telegram alert fires → what does Will do? Message template, timing (24h), quality scoring criteria
- [ ] Review Sprint 1 capture data: what's the conversion rate? Which surface? What's the leak?

**AI parallel:** Ad deep dive — specific reallocation recommendations with ad IDs and projected impact. Digital market report Q1 data pull started.
**GRIND:** Bank reconciliation — start with William Simpson personal entity
**CONTENT:** Record 2 data videos for this week

---

### Wednesday April 9 — Ad Reallocation + Route Test

**CHECKPOINT:** Winning ads scaled, Facebook traffic test to Decision Feed
- [ ] Review AI's ad reallocation memo — approve changes
- [ ] Scale proof-led creative with reallocated budget (from Sprint 1 paused ads)
- [ ] Route 1-2 top campaigns to `/for-sale-v2` (Decision Feed) — NOT all traffic yet
- [ ] Set up PostHog comparison: `/for-sale` vs `/for-sale-v2` bounce rate, scroll depth
- [ ] Weekly automated ad report configured

**AI parallel:** Digital market report first draft content. Backup scraper Robina agency fix progress.
**GRIND:** PAYG — make payment if research complete
**CONTENT:** Approve and queue posts

---

### Thursday April 10 — Measure Decision Feed + Market Report Draft

**CHECKPOINT:** Decision Feed 48h data + market report review
- [ ] Decision Feed metrics: bounce rate, scroll depth, card expansion rate, CTA conversion
- [ ] Compare: Decision Feed vs old `/for-sale` on same traffic source
- [ ] If Decision Feed clearly better (>20% improvement in any key metric): plan full traffic migration
- [ ] Review digital market report first draft — add personal commentary

**AI parallel:** Market report PDF layout. Content gap analysis from search intent (Sprint 3 pre-work).
**GRIND:** API spend — set up automated billing collection if APIs available
**CONTENT:** Review market report. Does it pass Unbounce test? (Short, clear, one offer, one CTA)

---

### Friday April 11 — Sprint 2 Review

**CHECKPOINT:** Hard decisions
- [ ] Decision Feed: ship as default `/for-sale` or needs more work?
- [ ] Market report: ready to publish with email gate, or needs iteration?
- [ ] Capture path performance: which surface converts best? Double down or adjust?
- [ ] Content cadence: 2 weeks of posts going out consistently?
- [ ] **Any real leads this week? If yes, Will has already contacted them (24h rule).**

**Sprint 3 readiness:**
- [ ] Content gap list ready? (Search intent analysis done?)
- [ ] SEO audit done? (Quick check from Sprint 1 AI pre-work?)
- [ ] Market report ready to launch?

**GRIND:** Accounting review — size remaining backlog
**CONTENT:** Review engagement data. Which content types drove comments?

---

## Sprint 2 Pre-Work Started in Sprint 1

| Task | Started | Status |
|------|---------|--------|
| Feed_hook generation (126 properties) | Sprint 1 Monday | Target: 80+ by Sprint 1 Friday, 126 by Sprint 2 Wednesday |
| decision-feed.mjs backend | Sprint 1 Thursday | Must be returning live data for Sprint 2 GO gate |
| Ad audit + reallocation memo | Sprint 1 Monday/Friday | Recommendations ready for Sprint 2 Wednesday |
| Digital market report data | Sprint 1 late week | Q1 2026 data pulled and verified |
| Content gap analysis | Sprint 1 any time | Gap list ready for Sprint 3 article generation |
| SEO indexing check | Sprint 1 any time | Quick status for Sprint 3 foundation |

---

## Success Criteria

| Metric | Target |
|--------|--------|
| Decision Feed live with real data | All card types rendering |
| Decision Feed bounce rate | <60% (vs ~95% on old page) |
| Ad waste eliminated | Zero-session ads paused, budget reallocated |
| Leads captured (cumulative) | 5+ across all surfaces |
| Lead follow-up SOP | Documented and tested |
| Market report | First draft reviewed |
| Feed_hook fields | 126/126 complete |
