# Sprint 1 — Funnel Proof + Instrumentation + Ad Waste Cut

> **Week of:** March 31 — April 4, 2026
> **Sprint focus:** Prove ONE lead capture path works. Instrument everything. Stop leaking ad spend.
> **If we only achieve one thing this week:** One capture path is live, instrumented, and converting.
> **Q3 countdown:** 92 days
> **Goal 1 progress:** 0% → starting M1.1 (Measurement Baseline)
>
> **Informed by:** CEO agent team review (2026-03-30). Key principle: "For the next 14 days, run the company like a funnel-validation business, not a platform-expansion business." — Chief of Staff
>
> **Design constraints from case studies:**
> - Unbounce: Short pages, 6th-grade copy, one CTA, one field. Target 5-8% conversion.
> - Realtor.com: "Track this property" (utility) converts better than gated content at low traffic.
> - Magri Cabinets: Very small number of high-intent pages with clear measurement beats content volume.

---

## Key Rule: Lead Response
**If ANY real (non-test) lead appears this week, Will contacts them within 24-48 hours.** Do not wait for Sprint 8. Lead quality learning is the most important signal in the business.

---

## Daily Checkpoints

### Monday March 31 — Sprint Setup + Ad Waste Cut

**CHECKPOINT:** Instrumentation foundation + ad waste eliminated
- [ ] Create PostHog dashboard: "Weekly Acquisition" — unique users by source, by page
- [ ] Create PostHog dashboard: "Engagement Depth" — pages per session, return rate, scroll depth
- [ ] Record baseline numbers (this week = week zero)
- [ ] Design and document lead capture event schema: `impression`, `expand`, `submit_start`, `submit_success`, `telegram_sent` for each surface
- [ ] Design `system_monitor.leads` schema: `{email, source, property_id, suburb, status, first_response_at, owner, next_action_at, lead_quality, notes, created_at}`
- [ ] **AD WASTE CUT (approval):** Review the 2 zero-session Meta ads ($60.56 + $60.49 = $121/week wasted). Approve pause. AI executes.

**AI does in parallel (no Will needed):**
- Build `system_monitor.leads` collection with indexes
- Run ad audit: `ad-review-dump.py --active` — produce specific pause/scale memo with ad IDs
- Start backup scraper audit (BS1) — SSH to 35.201.6.222
- Begin weekly content brief research (topic scanning, property pair selection)
- Begin generating `feed_hook`, `feed_catch` fields for core suburb listings (Sprint 2 pre-work — Data Quality recommended starting now)

**GRIND:** Email triage — inbox zero pass. Flag anything urgent.

---

### Tuesday April 1 — Primary Capture Path: Price Alerts

**CHECKPOINT:** "Track this property" price alert live + instrumented
- [ ] Email capture component on property pages: "Get notified if this property's price changes"
- [ ] Design: SHORT. One email field + one button. 6th-grade copy. Above the fold on property page.
- [ ] Writes to `system_monitor.leads` with `{source: "price_alert", property_id, suburb, email}`
- [ ] PostHog events fire: `price_alert_impression`, `price_alert_submit_start`, `price_alert_submit_success`
- [ ] Telegram notification to Will on every signup
- [ ] Test on 3 property pages across all 3 core suburbs

**Why this first (not Analyse Your Home):** Product agent research shows utility-based capture ("track this for me") converts best at low traffic. Realtor.com proved it. Price alerts are the lowest-friction capture — buyer is already looking at the property.

**AI does in parallel:**
- Execute approved ad pauses from Monday
- Continue backup scraper audit
- Continue content brief + feed_hook generation
- Draft first data video transcript

**GRIND:** Ray White emails — extract invoices for 46 Balderstone St from last 30 days

**CONTENT:** Review content brief when AI delivers it

---

### Wednesday April 2 — Secondary Capture: Analyse Your Home

**CHECKPOINT:** Analyse Your Home form wired + instrumented
- [ ] Wire form submission to `system_monitor.leads` with `{source: "analyse_home", address, email, phone}`
- [ ] Design review: Is the page SHORT? One offer above the fold? One primary CTA? (Unbounce benchmark: short pages convert 33% better)
- [ ] PostHog events: `analyse_home_impression`, `analyse_home_submit_start`, `analyse_home_submit_success`
- [ ] Telegram alert on every submission
- [ ] Auto-acknowledge: "We've received your request. Will from Fields Estate will be in touch within 24 hours."
- [ ] Test end-to-end

**AI does in parallel:**
- Wire Decision Feed LeadCapture.tsx to backend (Sprint 1 Friday or Sprint 2)
- Backup scraper: produce coverage comparison report (backup vs primary for Robina)
- Finish weekly content brief with all deliverables
- Continue feed_hook generation for core suburbs

**GRIND:** PAYG research — find out what's owed, when it's due, how to pay

**CONTENT:** Review completed content brief. Approve or adjust topics for the week.

---

### Thursday April 3 — Measure + Content Launch

**CHECKPOINT:** First 48h of capture data reviewed + first content published
- [ ] Check: any real leads captured? (Even 0 is data — what's the impression count? Are people seeing the capture forms?)
- [ ] Review PostHog funnel: ad click → property page → price alert impression → submit
- [ ] Identify the biggest leak (are people not seeing the form? Seeing but not clicking? Clicking but not submitting?)
- [ ] First Facebook content posted (from approved brief)

**AI does in parallel:**
- Decision Feed CTA wiring continues
- Draft "Track this suburb" weekly digest concept (Sprint 2 capture expansion)
- Backup scraper: begin fixing blocked Robina agency scrapers
- Continue feed_hook generation

**GRIND:** Anthropic/OpenAI/Google spend — pull current month totals

**CONTENT:** Record first data video (40-60 seconds) from approved transcript. Film first question/opinion post if property pair selected.

---

### Friday April 4 — Sprint 1 Review + Sprint 2 Readiness

**CHECKPOINT:** Sprint review with hard decisions
- [ ] **Lead capture status:** How many impressions? How many submits? Conversion rate?
- [ ] **Ad waste:** Confirmed paused? Savings redirected?
- [ ] **PostHog baseline:** Dashboards working? Week-0 numbers recorded?
- [ ] **Content:** Brief reviewed? First post published? Video recorded?
- [ ] **Backup scraper:** Audit complete? Coverage report?
- [ ] **Decision: continue / cut / double down / defer** for each workstream

**Sprint 2 readiness gate:**
- [ ] Feed_hook fields: how many of 126 core suburb properties have them? (Need 80+ for Decision Feed launch)
- [ ] Decision Feed backend: is `decision-feed.mjs` returning live data?
- [ ] If not ready: Sprint 2 shifts to "complete readiness" not "launch"

**GRIND:** Week review — 3 of 4 grind tasks done?

**CONTENT:** Approve and schedule next week's Facebook posts

---

### Saturday April 5 (Optional)

If checkpoint missed → complete it.
If all hit → film B-roll around Robina for future YouTube content.

---

## Sprint 1 Success Criteria (Revised)

| Metric | Target | How to Measure |
|--------|--------|---------------|
| **Primary capture path** | Price alerts live + instrumented on property pages | PostHog events firing, leads in DB |
| **Secondary capture** | Analyse Your Home wired + instrumented | PostHog events, Telegram alerts |
| **Conversion data** | At least impression + submit counts for both paths | PostHog dashboard |
| **Ad waste cut** | Zero-session ads paused, $121/week saved | Facebook ad manager |
| **PostHog baseline** | 2 dashboards, week-0 recorded | PostHog |
| **Content** | First brief reviewed, first post published | Content queue |
| **Backup scraper** | Coverage report produced | Report delivered |
| **Feed_hook pre-work** | 40+ properties with feed fields generated | DB count |
| **Grind** | 3 of 4 tasks done | Email, Ray White, PAYG, API spend |

**NOT required for Sprint 1 success (explicitly deferred):**
- Decision Feed launch (Sprint 2)
- Digital market report (Sprint 2-3)
- SEO work (Sprint 3)
- YouTube anything (Sprint 5+)
- Content engine automation (Sprint 3)

---

## AI Work Queue (Runs Without Will)

| Task | When | Sprint It Serves | Deliverable |
|------|------|-----------------|-------------|
| Build leads collection + schema + indexes | Mon | Sprint 1 | Working DB + Telegram |
| Ad audit + pause memo | Mon | Sprint 1 | Specific ad IDs to pause |
| Execute ad pauses (post-approval) | Tue | Sprint 1 | $121/week saved |
| Backup scraper BS1 audit | Mon-Wed | Sprint 1 | Coverage comparison report |
| Content brief generation | Mon-Wed | Sprint 1 | Full brief with transcripts |
| Feed_hook field generation (126 properties) | Mon-Fri | **Sprint 2 pre-work** | 80+ properties with feed fields |
| Data video transcript draft | Wed-Thu | Sprint 1 | Script ready for Will |
| Decision Feed backend wiring | Thu-Fri | **Sprint 2 pre-work** | decision-feed.mjs returning live data |
| SEO indexing quick-check | Any time | **Sprint 3 pre-work** | Are key pages indexed? |
| 2025 tax document checklist | Any time | **Sprint 4 pre-work** | What docs Will needs to gather |
| YouTube competitor refresh (GC-specific) | Any time | **Sprint 5 pre-work** | Local channel analysis |
| CEO agent morning analysis | Daily | Sprint 1 | Triaged proposals |

---

## CEO Agent Sprint Context

```
Sprint 1 Theme: Funnel Proof + Instrumentation + Ad Waste Cut
Sprint Focus: Prove ONE lead capture path converts. Instrument everything. Cut waste.
Q3 Countdown: 92 days
Current Goal: Goal 1 — Prove Buyer Demand (200 weekly uniques by May 31)
Current Milestone: M1.1 — Measurement Baseline

If we only achieve one thing: One capture path live, instrumented, and converting.

Checkpoints:
  Mon: Instrumentation + ad waste cut approval
  Tue: Price alerts live + instrumented (PRIMARY capture path)
  Wed: Analyse Your Home wired + instrumented
  Thu: First 48h data review + first content published
  Fri: Sprint review with continue/cut/defer decisions

Research questions:
  Product: What copy/placement converts best for property price alerts at <500 weekly traffic?
  Growth: Post-pause, which remaining ads should get the reallocated budget? Draft allocation memo.
  Engineering: Backup scraper Robina — what agencies are blocked? Feasibility assessment for each.
  Data Quality: Feed_hook generation progress — are we on track for 80+ by Friday?
  Chief of Staff: Is Sprint 2 readiness on track? Flag any dependency at risk.
```

---

## Grind Schedule

| Day | Task | Time | Notes |
|-----|------|------|-------|
| Mon | Email triage | 30 min | Inbox zero pass |
| Tue | Ray White invoices | 30 min | 46 Balderstone St — last 30 days |
| Wed | PAYG research | 30 min | What's owed, when due |
| Thu | API spend tracking | 30 min | Anthropic, OpenAI, Google |

---

## End-of-Sprint Review (Friday)

```
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
📊 SPRINT 1 REVIEW — April 4

CHECKPOINTS:     _/5 hit
  Mon: Instrumentation + ad cut    [  ]
  Tue: Price alerts live           [  ]
  Wed: Analyse Your Home wired     [  ]
  Thu: First data + content        [  ]
  Fri: Sprint review               [  ]

CAPTURE DATA:
  Price alert impressions:  ___
  Price alert submits:      ___
  Conversion rate:          ___%
  Analyse Your Home submits:___
  Real leads (non-test):    ___

AD WASTE:
  Paused: Y/N
  Weekly savings: $___

GRIND:          _/4 done
CONTENT:        Brief: Y/N | Post: Y/N | Video: Y/N
BACKUP SCRAPER: Audit: Y/N | Coverage: ___%
FEED_HOOK:      ___/126 generated (Sprint 2 needs 80+)

DECISION: continue / cut / double down / defer
  Price alerts:       ___________
  Analyse Your Home:  ___________
  Content cadence:    ___________
  Decision Feed prep: ___________

SPRINT 2 READINESS:
  Feed_hook fields:     ___/126 (need 80+)
  decision-feed.mjs:    working / not ready
  GO / NO-GO:          ___________
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
```
