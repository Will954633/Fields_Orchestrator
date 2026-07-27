# Fields — Capability Stock Take, KPI Framework & Samantha Re-Direction

**Author:** Ops session with Will · **Date:** 2026-07-27 (AEST) · **Status:** REVIEWED & APPLIED (2026-07-27)
**Purpose:** Re-direct Samantha away from "book 5 appraisals" toward **generating inbound enquiry** —
warming the audience, teasing out people considering selling in the next ~12 months, and moving the
audience through the funnel. Before changing Samantha's system, we (1) take stock of every capability &
initiative and how we monitor it, (2) agree the KPIs for this stage, (3) stand up a KPI monitoring sheet,
and (4) write a concrete Samantha integration plan.

---

## 0. The re-direction in one paragraph

Samantha's current North Star is **"Get Fields 5 listing appointments"** and her whole task stack pushes
the *bottom* of the funnel (find a pre-market seller → stage a printed appraisal → Will posts it). The data
says that bottom-funnel ask isn't the constraint: the address-entry lead channel (`analyse_leads`) has been
**dead since 2026-04-10**, `valuation_requests` is stale, and `report_review_bookings` sits at **1** (June).
Meanwhile the *activity* is all top/mid-funnel — organic owner-lookups, mini-site views, content — and the
binding constraint (per our own analysis) is **engagement: roughly 1 click per 80 views**. So we re-point
Samantha at the real lever: **warm the audience and surface intent**, and let inbound enquiry be the output
we optimise, instead of trying to force a printed-appraisal booking at the end of a cold funnel.

**New primary steer:** *Inbound enquiries per week* (any raised hand), fed by *considering-to-sell intent
signals per week* (leading), fuelled by *engaged-audience growth* (top). Listing appointments become a
*lagging* outcome we watch, not the thing we push.

---

## 1. Capability & Initiative Stock Take

Status legend: **LIVE** · **STALLED** (built & live but throttled, e.g. billing) · **PARKED** (built,
intentionally dormant / gated) · **PLANNED** (spec'd, not built). Funnel stage: **TOP** (reach/awareness),
**WARM** (engagement/consideration), **INTENT** (tease-out considering-to-sell), **ENQUIRY** (raised hand),
**CONVERT** (appointment/listing).

### 1a. Audience-acquisition & distribution channels

| # | Initiative | Stage | Status | What it does / note | Primary data capture |
|---|-----------|-------|--------|---------------------|----------------------|
| 1 | **Off-market owner-lookup deck** `/off-market/:slug` | TOP→INTENT | **LIVE (default for all since 23 Jul)** | Flagship. Owner Googles own address → value-first swipe deck → interactive plan flow that **asks selling timeframe**. Now the majority of site traffic (6→25→41 owners/day). | `offmarket_qualification.timeframe`, PostHog `offmarket_*`, `leads`, `offmarket_intel/_positioning` |
| 2 | **SEO owner-lookup** (`/property/:slug`, sold pages) | TOP | **LIVE** | Organic "what's my/neighbour's home worth". ~1,594 property pages in sitemap. Behavioural seller flag `neighbour_sale_trigger`. Per-suburb SSR landing pages = next build. | `seo_landing_performance`, `seo_pilot_weekly`, GSC `search_console_queries`, `organic_journeys` |
| 3 | **AI-as-distribution** (SSR citability) | TOP | **PARTIAL** | LLMs already cite Fields (ChatGPT/Copilot). Full SSR of `/your-home` + `/property` is the single fix for both Google indexation and AI citability. | `ai_referral_signal` (utm_source=chatgpt.com etc.) |
| 4 | **`/for-sale-v3` Decision Feed** | TOP+WARM | **LIVE (crawlable since 24 Jul)** | Editorial curated listings, SEO wedge "Portals list. We judge." | PostHog `v3_*`, `feed_interactions` |
| 5 | **Facebook PAID prospecting** | TOP | **STALLED** | Curiosity/property-story creatives (curiosity 3.22% vs fear 0.31% CTR). **Delivery collapsed ~22 Jul — ad account unsettled (~$103).** Reads near-zero due to billing, not creative. | `ad_daily_metrics`, `ad_profiles`, `ad_decisions`, Brain 2 `ad_downstream`, `marketing_stage` |
| 6 | **Facebook ORGANIC (Will on camera)** | TOP+WARM | **LIVE (manual)** | 2×/day auto-scheduler is **DEAD/parked** (data-cards didn't land); replaced by Will-on-camera 40-60s videos + opinion/question posts. | `fb_ad_tests` (72h verdicts), `fb_page_posts` |
| 7 | **YouTube evergreen** | TOP | **PLANNED** | "Living in <suburb>" 1 video/wk. Never run paid to YouTube. Not yet producing. | none first-party yet |
| 8 | **Full-funnel retargeting** | WARM | **PARKED (volume-gated)** | Retargetable pool ~20 vs Meta's ~1,000 floor. Prospecting must build volume first. | FB pixels, `ad_*`, PostHog |
| 9 | **Facebook LEAD ADS (Instant Forms)** | ENQUIRY | **STALLED** | Buyer-brief + AYH seller forms (name/phone/address/timeframe). Phone capture proven. | `fb_leads`, `lead_attribution.intent_score` |
| 10 | **PDF flyer direct-mail (QR→mini-site)** | TOP→ENQUIRY | **PLANNED** | Unique per-address A4 flyer → posted → QR to their mini-site. Reaches no-contact owners. Vendor researched, lists staged. | (planned) unique QR → PostHog UTM |
| 11 | **Google Ads (search)** | TOP | **PLANNED/dev** | Infra live but conversion tag not installed; Will only a test user. | `google_ads_daily_metrics` (empty) |
| 12 | **Email / newsletter** | WARM | **PLANNED (gap)** | No marketing/nurture channel exists — email is **transactional only**. Gmail/MS-Graph agents unauthenticated. | `email_sends`, `email_events`, `email_tracking` |

### 1b. On-site funnel surfaces (where we capture intent)

| # | Surface | Stage | Status | Capture |
|---|--------|-------|--------|---------|
| 13 | Homepage / News `MarketIntelligencePage` `/` | TOP | LIVE | `$pageview`; content from `content_articles` |
| 14 | Market Metrics `/market-metrics/:suburb` | TOP+WARM | LIVE | `market_metrics_tab_switch`; `market_pulse`. ⚠ volume unreliable (sold under-capture) |
| 15 | Articles `/articles/:slug` | TOP | LIVE | `article_view`, `time_on_page` → `article_events`; gated by `ai_analysis.status==published` |
| 16 | Property detail `/property/:id` | TOP→INTENT | LIVE | `property_view`, `scroll_depth`; **PriceAlertSignup** → `price_alert_subscriptions` + `leads` |
| 17 | **ForSaleLadder** intent quiz (in `/for-sale-v3`) | INTENT | LIVE | buyer-vs-seller tease → `forsale_ladder_responses` (+timeframe) |
| 18 | Discover feed `/discover` | WARM | LIVE (exp `discover_mode_v1`) | `discover_*`; SignupGate → `lead_signups`; `feed_interactions` |
| 19 | Subscribe / newsletter opt-in (global) | WARM | LIVE | `/subscribe` → `subscribers` |
| 20 | 5 Property Friday signup | WARM | PARKED-ish (v4a only) | `five_property_friday_subscribers` |
| 21 | **Analyse Your Home** `/analyse-your-home` | ENQUIRY | LIVE (mostly test/organic) | `analyse_home_submit_success` + `property_reports`; legacy `analyse_leads`/`valuation_requests` |
| 22 | **Seller mini-site** `/your-home/:slug` | INTENT→ENQUIRY | LIVE | `minisite_*`; **"Book 30-min review"** → `report_review_bookings` + `leads` + `crm_contacts` |
| 23 | Off-market $15 unlock (Square) | ENQUIRY/CONVERT | PARKED (dormant since ladder default) | `offmarket_orders`, `property_reports.paid_unlock` |
| 24 | Contact `/contact` | ENQUIRY | LIVE | direct enquiry form |

### 1c. Content / intelligence engines (the warming substrate)

| # | Engine | Role | Status | Capture |
|---|-------|------|--------|---------|
| 25 | AI property editorial (per-listing articles) | TOP warming (SEO) | LIVE (auto-publish, step 120) | `ai_analysis` on property docs; `article_view` |
| 26 | House mini-site + case studies | INTENT/ENQUIRY core | LIVE | `property_reports`, `case_study_library` |
| 27 | Seller appraisal generator (11-pg PDF, print+post) | CONVERT | LIVE | `appraisal_pipeline` (stage/timeline) |
| 28 | Five Property Friday (buyer warming email) | WARM | LIVE (Fri cron) | tracked email opens/clicks; reads `fb_leads` |
| 29 | Market Pulse (monthly summaries) | WARM/authority | LIVE | `market_pulse` |
| 30 | Market-update videos / reels (quarterly) | TOP | LIVE workflow, founder-gated | FB/YouTube analytics only |
| 31 | The Fields Quarterly (print booklet) | WARM/trust | LIVE (Q2 issue built) | QR→PostHog only; personalised-mailer variant PLANNED |
| 32 | "Before You List" book (physical) | CONVERT reward | LIVE asset | none digital (gated on mini-site engagement) |
| 33 | Messenger AI responder | INTENT/ENQUIRY | **PLANNED (biggest warming gap)** | (intended) `crm_contacts`/`leads` |
| 34 | Brain 1 (coaching corpus) / Brain 2 (in-house data) / Brain 3 (institutional memory) | intelligence | LIVE | Brain 2 is the monitoring hub: `all_conversions`, `neighbour_sale_trigger`, person timelines |
| 35 | Lead-intelligence pipeline (02:00 cron) | plumbing | LIVE | unifies every lead → **`lead_worklist`** |
| 36 | CEO agents (Eng/Growth/Product/DQ/CoS) | strategy input | LIVE | `ceo_proposals` |

### The seven genuine "tease-out latent seller" mechanisms we already own
1. `offmarket_qualification.timeframe` — the deck asks directly (strongest, explicit).
2. `neighbour_sale_trigger` (Brain 2) — behavioural: valued a *different* house on the same street.
3. `lead_attribution.intent_score` — timeframe≤6mo=+2, owns_gc_home=+1.
4. `forsale_ladder_responses` — the on-feed buyer-vs-seller quiz (+timeframe).
5. `report_review_bookings` — explicit soft ask on the mini-site.
6. `price_alert_subscriptions` — low-friction "keep me posted on my street".
7. SOLD_OFFMARKET_THRESHOLD_MONTHS=12 — owners of homes sold 12+ mo ago = plausible future sellers.

---

## 2. How we monitor it (data-capture layers)

Three layers converge:
- **PostHog** (behaviour) — `$pageview` + per-surface events, UTM/`fbclid`/`gclid` super-props; durable join
  key `posthog_distinct_id`. Gotchas: HogQL LIMIT-100, heatmaps off, ~68% recording coverage, **Will's
  browser is opted out**, and `website_daily_metrics` (the Mongo rollup) is **broken (all zeros)** — PostHog
  is the real traffic source.
- **MongoDB `system_monitor`** (state & outcomes) — every lead-bearing collection is unified nightly by
  `lead_intelligence.py` into **`lead_worklist`** (the no-miss net). Brain 2 collections (`all_conversions`,
  `organic_journeys`, `ad_downstream`, `ai_referral_signal`) are the joined analysis layer.
- **Google Sheets** (human-facing) — Live Leads Tracker (nightly `live_leads_to_sheet.py` 23:55), Sold→Market
  Tracking, **Fields Systems Health** (nightly 01:00, `main_site_health_check.py`), Samantha Task Board.

*(Tab 5 of the KPI sheet is the full source-by-source map with cadence + gotchas.)*

### Monitoring gaps found during this stock take (these are themselves work items)
- **`website_daily_metrics` broken** (all zeros) → traffic not captured in Mongo; wire a PostHog→Mongo weekly rollup.
- **`marketing_stage` half-broken** — `weekly_reach`, `website_visitors`, `weekly_engagements` read 0.
- **`article_events`** last event 2026-06-01 — verify article-engagement capture didn't stop.
- **No email/nurture channel** and **Messenger AI not built** — the two biggest *warming* capability gaps.
- **Sold-data under-capture** (~40-50% vs PropRadar) → volume/months-of-supply unreliable site-wide.
- **FB paid billing outage** — annotate every paid KPI so a near-zero isn't misread as creative failure.

---

## 3. KPI Framework for this stage

**Principle (honest sizing):** at ~600 visitors/wk (~46 organic) the absolute conversion numbers are tiny
for months. So we steer on **leading indicators, rates, and trend**, not lagging absolutes. A small set of
**★ primary steers** drives decisions; a wider **diagnostic set** explains movement.

### Funnel-stage KPIs

**REACH (top)** — how many we get in front of
- Unique visitors / wk (PostHog) · Organic search sessions / wk (`organic_journeys`, GSC) · AI-referral
  sessions / wk (`ai_referral_signal`) · New page followers (`marketing_stage.page_followers`, now 21) ·
  Video views (826)

**WARM (engagement)** — are they consuming & returning
- ★ **Engaged sessions / wk** (PostHog engaged = >X s or scroll) · Returning-visitor % · Avg time on page ·
  Article/mini-site views / wk (`article_events`, `property_reports`) · Retargeting/page-engager pool size

**INTENT (tease-out)** — surfacing people considering selling ← the crux
- ★ **Intent signals / wk** = `offmarket_qualification` (timeframe answered) + `neighbour_sale_trigger` +
  `forsale_ladder_responses` (seller) + `price_alert_subscriptions` + report-review interest
- Owner-lookup address views / wk (single-address organic) · Repeat visits to one address

**ENQUIRY (raised hand)** — the NEW primary output
- ★★ **Inbound enquiries / wk** = report-review bookings + AYH submits + valuation requests + FB lead-form
  leads + contact-form + (later) Messenger + JustCall. Unified in `lead_worklist`.

**CONVERT (lagging — watch, don't steer)**
- Enquiry→appointment rate · Listing appointments · Listings signed (`appraisal_pipeline`, `marketing_stage`)

**ACTIVITY (leading inputs — what WE do)**
- Content cadence: FB posts/wk, videos/wk, articles/wk (vs `03-WEEKLY-CONTENT-PLAYBOOK`) · Live experiments
  (`change_ledger list --status live`) · Ad spend vs $500/wk cap · ★ **Cost per engaged session**
- SEO pages published/indexed · Mini-sites generated / wk (`property_reports`)

**DATA-HEALTH (can't manage what we don't capture)**
- % of funnel stages with a live, trusted capture point · # broken capture points open (currently ≥3)

### The five primary steers (the few that matter now)
| ★ | Metric | Why it's the steer at this stage | Source |
|---|--------|----------------------------------|--------|
| ★★ | **Inbound enquiries / wk** | Replaces "5 appointments" as the output we optimise — any raised hand | `lead_worklist` |
| ★ | **Intent signals / wk** | Leading indicator of enquiry; the "considering to sell" tease-out | offmarket_qualification + neighbour_sale_trigger + ladder + price_alerts |
| ★ | **Engaged sessions / wk** | The fuel — engagement is our binding constraint (1 click/80) | PostHog |
| ★ | **Cost per engaged session** | Is our (paid) spend actually buying warmth | ad spend / engaged sessions |
| watch | **Listing appointments** | Lagging outcome; confirms the funnel works, doesn't steer it | appraisal_pipeline |

**Targets:** set as **30/60/90-day trend goals**, not absolutes — Will to confirm the levels. Suggested
starting posture: hold reach flat (paid is down anyway), and drive *engagement rate* and *intent-signals/wk*
up week-on-week, with inbound enquiries as the north the whole thing is judged by.

---

## 4. Samantha Integration Plan (concrete — for review, not yet applied)

Samantha performs well only with **specific task objectives and documented workflows**. The re-direction is
therefore a set of precise edits to her charter + daily_tasks, plus the KPI sheet as her new scoreboard.

### 4.1 Change the North Star (charter.md)
- **From:** "Get Fields 5 listing appointments" (the filter for everything).
- **To:** "**Grow inbound enquiry** — warm the audience, surface people considering selling in the next 12
  months, and move them through the funnel." Filter for every task: *does this increase engaged audience,
  intent signals, or inbound enquiries?* Listing appointments stay as the lagging outcome she reports, not
  the thing she pushes.

### 4.2 Re-order her task stack (daily_tasks.md)
Current order over-weights bottom-funnel (Task 0 = work the leads worklist → stage appraisals). New order:
1. **Task A — Intent-signal sweep (new, highest value).** Each run, pull the week's intent signals
   (`offmarket_qualification`, `neighbour_sale_trigger`, `forsale_ladder_responses`, `price_alerts`,
   report-review interest), rank the warmest, and for each: is there a *next step for this person*, or a
   dead-end to fix? (Generalises her existing "opportunity-chasing doctrine".)
2. **Task B — Warming-engine health & cadence.** Are the warming engines actually firing? Content cadence vs
   playbook, editorial auto-publish, off-market deck, Five Property Friday, articles. Fix/prompt what's stalled.
3. **Task C — KPI scoreboard update (new).** Refresh the KPI sheet, compute trend, flag red. This is her
   weekly report backbone (replaces the appraisal-count PATH-TO-5 section).
4. **Task D — Experiments toward engagement/intent** (not toward "book appraisal"): test warming hooks,
   intent-tease CTAs, content angles — within the same $15/day, $500/wk caps and one-test-per-surface rule.
5. **Task E — Leads worklist** (kept, demoted): still surface & stage packages for genuinely hot enquiries,
   but this is now downstream of A–D, not the headline.
6. **Task F — Systems/data-health** (kept): plus the new monitoring-gap items (§2) as standing fixes.

### 4.3 Reframe the "PATH TO 5 APPRAISALS" report section
Replace with **"FUNNEL MOVEMENT THIS RUN"**: what moved reach → warm → intent → enquiry, the single
highest-leverage next warming move, and whether she executed/staged it.

### 4.4 Wire the KPI sheet in as her scoreboard
- Add the sheet ID to charter.md next to the Task Board.
- Task C writes the Weekly Log row + updates the Dashboard each run (reuse `task_board.py` auth).
- Her "Scorecard" tab and this sheet's Dashboard should agree (single source of truth for KPIs).

### 4.5 Close the biggest capability gaps (so there's something to steer)
Flag to Will as **WILL-unblock** items, because they're the ceiling on inbound enquiry:
- **Settle the FB ad account** (~$103) — paid warming is off entirely until then.
- **Build the Messenger AI responder** (permission-based warm→qualify→escalate) — biggest missing warming engine.
- **Decide the email/nurture channel** — currently no way to warm a captured contact over time.
- **Ship SSR for `/your-home` + `/property`** — unlocks both Google indexation and AI citability (top-of-funnel fuel).

### 4.6 What we do NOT change
Editorial rules, autonomy tier (DOER), budget caps, the three-brains discipline, the session-end sweep, and
memory discipline all stay. This is a **re-pointing of the goal and task priorities**, not a rebuild.

---

## 5. Order of operations — status

1. ✅ Stock take + data-capture map (this doc).
2. ✅ KPI framework (this doc §3).
3. ✅ KPI Monitor Google Sheet built — `1BxDgfEVLOsmGujZe5R1LNsq9sY2WtVt6d_wEpxJMLYY` (Samantha's folder).
4. ✅ **Reviewed with Will 2026-07-27** — confirmed: (1) inbound enquiry = North Star; (2) targets are
   **rate/trend goals** (grow intent-signals + engaged-session-rate week-on-week, not absolute counts).
5. ✅ **Samantha edits applied** (§4) — charter.md North Star + scope re-pointed; daily_tasks.md task
   priority (A–F) + PRIME DIRECTIVE + report section re-framed to inbound enquiry.

## 6. New workstream — FB ad-spend review (Will, 2026-07-27)

A **separate, scheduled working session between Samantha and Will**, distinct from the routine ad autonomy:
- **Objective:** review current FB ad spend, **cut the ads that aren't working**, and **develop + test
  Will's new ad concepts**.
- **Samantha's prep (before the session):** an evidence-backed cut-list (which ads to kill, with the
  downstream attribution that justifies it) + the current portfolio's cost-per-engaged-session read.
  Note the confound: **FB paid delivery has been stalled since ~22 Jul (billing ~$103)**, so recent
  performance data is thin — flag which reads are pre- vs post-collapse.
- **Boundary:** Samantha does NOT unilaterally overhaul the ad account ahead of the session; routine
  "pause an obvious dud within caps" autonomy still stands. New concepts come from Will.
- **Tracked:** Task Board Backlog (P1, Needs-Will = YES).
- **Still open (not chosen this round):** settle the ad account, build the Messenger AI responder, decide
  an email/nurture channel, ship SSR for `/your-home` + `/property` — the other ceilings on inbound enquiry.
