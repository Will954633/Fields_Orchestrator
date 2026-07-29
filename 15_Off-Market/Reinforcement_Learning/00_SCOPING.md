# Off-Market Reinforcement Learning — Scoping Document

**Author:** Ops agent · **Date:** 2026-07-29 · **Status:** Exploration / scoping (no build committed)
**Concept:** Port the Claude-in-the-loop reinforcement pattern proven on the [Home Owner Lead Funnel](../../03_Facebook/Home_Owner_Lead_Funnel_Search/) to the off-market owner-lookup surface (`/off-market/:slug`) — discover, through repeated measured cycles, which **on-page information** best engages and converts homeowners who Google their own address.

---

## TL;DR (read this first)

1. **The concept fits the surface unusually well.** The Facebook funnel spends ~$8/lead to *manufacture* a "what's MY number?" open loop. The off-market page has that loop **native and free**: a homeowner Googling their own address arrives on a page about their own home, pre-qualified, at ~94% organic, growing. This is the highest-intent seller audience we can reach.

2. **The content palette is a wiring problem, not a build problem.** We already generate — and battle-test on the mini-site — at least **12 high-personalisation information moves** (your-street premium, dynamic case study, full valuation range, feature-evidence ladder, AI editorial, aerial/street vision reads, buyer personas/catchment, seasonality, POI proximity). Most can become a testable deck card by rendering an existing resolver's output. The RL "action space" is largely ready.

3. **But the loop cannot learn anything today.** Two hard constraints gate it, and both must be addressed *before* a learning loop is meaningful:
   - **Reward is near-empty + instrumentation is incompatible.** Over the surface's entire 9-day history: **1** seller-intent (`offmarket_qualify`) event, **10** users doing any downstream action, and the per-card funnel is instrumented in **only one of the two live arms**. There is no per-card dwell, swipe outcome, or card position. The learnable dataset today is ≈ zero.
   - **More volume is data-gated, not quota-gated.** You can't reach "whole-GC $1M–$2M houses" by *filtering* — that bracket is only ~1,601 houses whole-GC vs ~1,573 already in core, and everything outside core is bare cadastral skeleton. The right expansion lever (Will, 2026-07-29) is **whole-population TIMELINE enrichment via Bright Data Domain scraping** — infra we already own — over the **117,038-address southern-to-middle band (incl Nerang); a ~115K gap ≈ 7× the current corpus** at a one-time ~$175–350. **A "recently-sold" feed is the wrong lever** (fresh owners = least likely to relist; misses the long-tenure majority). PropRadar Starter (now 20K/mo) is for suburb-selection + the `/recently-modified` inbound-intent feed, not bulk enrichment. Google index "quota" is a non-issue; the real ceiling is crawl-budget × domain authority × page quality — so roll out in watched waves.

4. **Recommended shape:** a **daily** (not hourly) Claude cycle with a **low arm count** (2–4, because trials — not dollars — are scarce here), using **deck-depth as a dense shaped reward** and downstream-action as the sparse true reward. Sequenced as **Phase 0 instrumentation → Phase 1 quality-first coverage lap → Phase 2 content loop.** Weekly is the honest cadence for actual kill/scale verdicts at current N.

5. **Will's index-quota worry is validated:** an "other-city lap" is the worst-ROI expansion (thin pages, no local authority, near-certain "discovered-not-indexed," diverts crawl from the corpus that's ranking). Expand within southern GC where index equity compounds.

---

## 1. What we're porting — the source system

The Home Owner Lead Funnel is not a bandit in code; it is a **Claude-in-the-loop reinforcement pattern**. Its anatomy:

| Element | Source system |
|---|---|
| **Action space** | Ad copy variant = angle × hook-mechanic × format × background (dark/light). ~21 angles day 1. |
| **Environment** | Meta ad auction, out-of-market audience (Brisbane + Sunshine Coast; GC excluded to protect the core). |
| **Reward** | Real name+email+phone+**selling-intent** form-fill (NOT clicks). CPL ≤ $8 = winner; ≤ $5 = north star. |
| **Policy update** | A **Claude wake-up cycle** — durable OS cron → headless `claude -p` (Claude Max), hourly 08:00–22:00 AEST. |
| **Isolation** | Each variant is its own $15/day ad set (shared ad sets let Meta starve variants — the AYH lesson). |
| **Compounding** | Every winner's *WHY* is attributed and logged so the next cycle builds on the mechanic, not just the creative. |
| **Self-monitoring** | The cron self-reports as `home_owner_wakeup` (CLAUDE.md Rule 7) — can't die silently. |

Each cycle Claude: reads live state (`checkpoint.py` hourly rollup) → analyses what converted and **why** → researches new concepts (Brains 1/2/3, web, Sabri/Halo) → kills losers (0 leads@$15 or CPL>$25) → scales winners → launches a fresh batch → documents to `cycles/cycle_*.md` + ledger + `ad_decisions` + Telegram.

### The transferable laws it has already discovered (day 1: 21 angles, ~$374, 6 leads / 4 quality)

> **The one law that matters most:** converting hooks require a **PERSONAL OPEN LOOP** the next step closes — "what's MY number?". Topic-level engagement (anger / interest / awareness) does **not** convert regardless of CTR.

Three converting axes all share this mechanic: **AN2 "Missed by a million"** (home-value gap, ★ $7.96–8.54 CPL), **AN14 "7-Day Window"** (listing-attention decay, $6.42 CPL), **AN15 "$150K Data Gap"** (agent-said vs comps-said, $15.74 CPL). Supporting laws, each earned by a kill:

1. **Specific shocking numbers ≫ abstract concepts** (7–10× CTR). Every abstract-label angle died.
2. **Compound formula = narrative engagement + specific $-shock + personal question.** Pure narrative gets clicks / 0 leads; pure statistic dies; the *combination* converts.
3. **Fear > aspiration.** Positive urgency ("+4% week-three premium") is definitively dead; loss-framing wins.
4. **Agent-trust axis engages but does not convert** (12% CTR, 0 leads) — anger, not personal curiosity.
5. **Format × context interaction** — narrative→dark background, table/utility→light; utility with no curiosity gap dies.

**Why these matter here:** the off-market deck's job is exactly to open and close a personal loop about *their* home. Laws 1–3 tell us which cards will earn engagement (specific personal numbers, compounded with a light narrative and a concrete ask) and which will die (abstract, aspirational, generic-market). We can seed the off-market action space with the *mechanics* that already won, rather than re-discovering them.

---

## 2. Why off-market is the right target — and where it differs

The off-market page is already the exact open loop the ad system pays to rent. A person Googling their own address is *actively thinking about their home's value in that moment* — reachable without ad spend. Current organic reality: **~94% Google organic, 62.5% mobile (50.6% iOS), ~77% SEQ, ~17 unique visitors/day** landing on a single address and leaving.

Structural differences that change the RL design:

| Dimension | Ad funnel (source) | Off-market surface (target) |
|---|---|---|
| Action space | Ad copy variant | **On-page information move** (which card, what data, order, what ask, tone) |
| Environment | Meta auction, out-of-market | Google organic, real GC owners on **their** address |
| Reward | Form-fill (name+email+phone+intent) | **Engagement depth → downstream action** (deck depth → door/deep-dive → lead/qualify) |
| Cost per trial | $15/day real spend | ~$0 marginal (organic) — but **traffic volume is the scarce resource**, not dollars |
| Signal speed | Fast ($ buys impressions on demand) | **Slow — bounded by organic arrival rate × index coverage** ← the core scoping problem |
| Isolation | 1 ad set / variant | PostHog feature-flag arm / variant (sticky per person) |
| Optimal breadth | GO WIDE (16–24 variants) | **GO NARROW (2–4 arms)** — trials, not dollars, are scarce |

**The reward is engagement, and engagement is the known binding constraint** ([samantha_redirect_inbound_enquiry](../../../home/projects/.claude/...) north star). The current baseline is exactly what needs optimising (Section 3).

---

## 3. Current state — the evidence

### 3.1 User behaviour (PostHog, project 348370, full history 2026-07-20→28; N is small but real — internal + bots filtered)

**Traffic & audience.** 176 pageviews / **151 unique visitors** / 155 sessions in 9 days. **1.17 pv/user, 1.03 sessions/user** — near-total single-page, single-visit. Launch spike 07-22 (41 users) then a steady **~17 unique/day, flat-to-slightly-declining**. Source: **94% Google organic**, 6% direct, **zero paid/social**. Device: **62.5% mobile, 50.6% Apple/iOS**. Geo: 77% SEQ (Brisbane line overstated by ISP routing). Arms live concurrently: `ladder_dark` 68 users / `rich` 83 users.

**Card-by-card funnel (⚠ `card_viewed` fires only in the `ladder_dark` arm — 68 users, not all 151):**

| Card | Unique users | % of hero | Retention |
|---|---|---|---|
| hero | 53 | 100% | — |
| **value-range** | **20** | **38%** | **−62% ← steepest cliff (first swipe)** |
| capital-gain | 12 | 23% | −40% |
| market-direction | 10 | 19% | −17% |
| market-now | 10 | 19% | 0% |
| market-segue | 8 | 15% | −20% |
| market-drivers | 7 | 13% | −13% |
| ownership | 5 | 9% | −29% |
| plan-priority | 2 | 4% | −60% |
| buyer-who / positioning / selling-thesis | 1 each | 2% | — |

**The disengagement drivers (evidence-based):**
1. **First-swipe abandonment is the headline problem** — 78% see the hero, only 38% of those swipe once. The **hero→value-range −62% wall** is where the audience is lost, *not* deep in the deck. (Note: the steepest cliff has **moved forward** since the 2026-07-27 read, when it was value-range→market-direction — the redesign helped the mid-funnel but the very first swipe is now the gate.)
2. **Shortest session of any key surface** — off-market **82s** vs for-sale-v3 220s, /property 240s, /market-metrics 155s. ~1/3 the dwell of comparable pages.
3. **No lateral exploration** — 1.17 pv/user; the highest-intent audience looks at one address and leaves.
4. **Mobile, one-handed, organic-cold** — a low-patience context that punishes a 12-card swipe gauntlet.
5. **The seller-conversion payload is effectively unseen** — cards 8–12 reach ≤5 users.

**Downstream conversion (of 151 visitors):** any action **10 (6.6%)**; any menu door 4 (2.6%); `forward_cta_clicked` 6 (4.0%); **`offmarket_qualify` — the real seller signal — 1 (0.7%)**. i.e. the surface currently converts intent into a measurable seller signal for **one person in nine days**.

**Instrumentation gaps that block an RL loop (this is the gating finding):**
- **Reward is near-empty** — terminal reward fired once; RL needs reward density.
- **The two arms use incompatible schemas** — `card_viewed` only in `ladder_dark`; the `rich` majority (83 users) produces no trajectory. No shared state/reward across arms.
- **No per-card dwell / swipe-direction / dismissal** — `card_viewed` is a binary "reached" flag; you can't tell "read it and left" from "flicked past in 0.5s" — the exact discriminator a policy needs.
- **Card position/sequence is not logged** — order is *inferred* from aggregate counts; state-transition tuples can't be reconstructed reliably, especially after a reorder (already happened).
- **`scroll_depth` is effectively dark** (15 events, wrong payload key). No session-terminal marker.
- **Sample size** — ~17 users/day is 2–3 orders of magnitude below what an online policy over a 12-card action space needs to escape noise.

### 3.2 Indexation & coverage (measured 2026-07-29; GSC 28d window)

**Off-market is already the site's #1 organic surface — bigger than `/property/`.**

| Page type | Sitemap URLs | URLs w/ impressions (28d) | Impressions | Clicks |
|---|---|---|---|---|
| **off-market** | ~16,900 | **2,889** | **5,276** | **156** |
| property | ~1,600 | 929 | 4,886 | 106 |
| market-metrics | — | 14 | 1,724 | 13 |

- **Indexed ≈ 15,000** (URL-Inspection sample **9/10 = 90% indexed**; impressions prove indexation; GSC's `indexed=0` sitemap report is the known reporting bug). ~19% surface for queries in any 28-day window. Balanced across the 3 core suburbs.
- **The historical "discovered-not-indexed / low-authority" constraint is NOT currently binding** at ~17K scale — because every page carries **real sale history**. That quality signal is what's earning the 90% indexation.

**DB coverage (Gold_Coast: 312,147 addresses, 85 suburbs). Off-market-eligible = the exact sitemap rule.**

| Group | Addresses | Off-mkt eligible | With sale history | **$1M–$2M houses** |
|---|---|---|---|---|
| **CORE (3 suburbs)** | 27,092 | 17,247 | 17,039 | **1,573** |
| **SOUTHERN GC (25 suburbs)** | 111,307 | 17,347 | 17,115 | **1,585** |
| **WHOLE GC (85 suburbs)** | 312,147 | 17,349 | 17,207 | **1,601** |

> **The decisive finding:** enrichment is ~100% concentrated in the 3 core suburbs. The *entire rest of the Gold Coast* adds only **~100 eligible records and ~28 additional $1M–$2M houses.** Non-core collections are bare cadastral skeletons (no `property_type`, no `transactions`). **"Whole-GC $1–2M houses" is not queryable from our DB** — you can't identify a non-core house's type/price without fetching it. Expanding means *acquiring* data, not filtering it. And the $1–2M bracket itself is small (~1,600) — it is a *value filter*, not a volume lever.

### 3.3 The content palette (action space) — already largely built

The deck was redesigned 2026-07-27 (fused hero+intent-menu replaced the 0-converting ownership gate). Beyond the ~10 cards live today, the mini-site (`/your-home/:slug`) is a reservoir of blocks that already render and are powered by resolvers writing to `system_monitor.property_reports`. **The generation code for the moves below already exists and is battle-tested — the loop's action space is a *rendering/wiring* problem.**

**Shortlist — 12 most promising UNTESTED information moves** (personalisation × generation-readiness × low wiring cost):

1. **Your-Street price premium** — "Homes on *your street* sold ~X% above suburb median (N sales)." Deterministic, hyper-personal. (`your_street_narrative.py`)
2. **Dynamic case study** — "A home like yours sold for $X in Y days, [nearby street]." Real number + social proof. (`case_study_dynamic.py`)
3. **Full reconciled valuation range + confidence + value-gap** — upgrade the coarse comps range to the real engine output. (`precompute_valuations.py`)
4. **Feature-evidence ladder** — "buyers actually paid $X for [your pool/land/view]," 3 confidence layers; cohort premiums already computed. (`FeatureEvidencePanel`)
5. **AI editorial cadastral card** — a magazine paragraph about *their* home; cadastral "your home" mode already exists. Highest-variety surface. (`generate_property_ai_analysis.py`)
6. **Aerial/satellite read** — "your lot backs onto [park/golf]; drainage/flood note." Curiosity + honest risk. (`inline_satellite.py`)
7. **Street-view kerb/condition read** — build era, style, condition vs street. (`inline_street_view.py`)
8. **All 3 buyer personas** (deck shows only persona[0] today) — cheap: render persona[1]/[2]. (data already generated)
9. **Buyer catchment + campaign-reach math** — "your buyer most likely comes from [origin cohorts]." (`buyers_narrative.py`)
10. **Seasonality strip** — month-by-month sale-price calendar for their suburb; timing lever. (`SeasonalityStrip`)
11. **POI proximity card** — nearest school/beach/park; intel **already computed by the poller**, under-surfaced. Near-zero cost. (`compute_intel` proximity)
12. **Suburb Market-Pulse micro-narrative + the coded-but-unused market charts** (`market-now`/`direction`/`drivers`) re-tested as opt-in single cards, not the old force-march.

**Persuasion-angle map** (mechanic → asset), aligned to the funnel's fear/curiosity hierarchy:
- **"What's MY number" / valuation uncertainty** → wealth reveal, reconciled valuation, your-street premium, feature-evidence, dynamic case study
- **Loss-aversion / endowment** → capital-gain card, agent-premium research
- **Rarity / scarcity of their home** → scarcity thesis, feature-evidence, "only N compete"
- **Curiosity (information gap)** → surprise nugget, aerial/street vision reads, floor-plan
- **Timing** → seasonality strip, market direction, Market Pulse
- **Agent-trust / honesty** → anti-frame ("what we wouldn't claim"), `/research/` papers, statutory CMA, seller-appraisal's "what we couldn't see"
- **Desirability / demand** → buyer personas, buyer catchment, campaign-reach

Off-site payloads for the conversion end: the **Seller Appraisal PDF** (already tied to the `fromReport` QR path — the artifact Will prints and posts), the **Q2 2026 Market Pulse PDF** (light suburb credibility), the **"Before You List" book** (as a digital chapter/download unlock), and individual **`/research/` papers** cited inline behind each claim.

---

## 4. The two gating constraints (must precede any loop)

### Constraint A — the loop is currently unobservable and unrewarded
An RL loop is a measurement engine; ours has almost nothing to measure. **1** true-reward event and **incompatible per-arm instrumentation** mean that even with a perfect policy there is no signal to learn from. **This is the first thing to fix, and it is cheap** (instrumentation, not new product):
- Unify the per-card event schema across **both** arms (add `card_viewed` + `card_index` + per-card dwell + swipe-outcome to `rich`).
- Add a **dense shaped reward**: deck-depth reached, per-card dwell, forward-swipe rate — so the loop has thousands of signals/week even while the sparse `offmarket_qualify` stays rare.
- Add a session-terminal marker (`deck_abandoned_at_card`, `deck_completed`).

### Constraint B — volume is data-gated; the right lever is whole-population TIMELINE enrichment, not a sold feed
More trials/week is the throttle on learning rate. It **cannot** come from filtering the DB (the $1–2M bracket is ~1,600 whole-GC and non-core is skeleton). It must come from **acquiring property data** for adjacent suburbs — but the *kind* of data matters, and an earlier draft got this wrong:

> **⚠ Corrected (Will, 2026-07-29): a "recently-sold" feed is the wrong lever.** A home that just sold has a *fresh owner* — the cohort least likely to relist. And a sold feed is structurally biased: it only ever surfaces addresses that **transacted** in the window (~5–15% of a suburb's stock), and specifically misses the **long-tenure owners** (bought 8/12/20 yrs ago) who are the prime latent-seller population. It fails on both audience quality and coverage breadth.

**The right lever: enrich the whole cadastral address population with real property TIMELINES** (full sale/rental history per address), then mint a rich off-market page per address and filter by the timeline for off-market eligibility. Two complementary sources:

- **PRIMARY — Bright Data Domain scraping (bulk corpus backfill).** We already own the infra: `shared/domain_fetch.py` (Bright Data Web Unlocker, bypasses the Akamai block on `domain.com.au`) + the step-12 property-timeline builder + `__NEXT_DATA__` parsing. Domain property-profile pages carry the **full timeline for any address** (every owner, not just recent transactors). Target band = **117,038 non-core cadastral addresses** across 26 southern-to-middle suburbs (Nerang 8,070, Palm Beach 10,816, Burleigh Heads 9,572, …), of which only ~1,580 are enriched today → a **~115K gap ≈ 7× the current ~17K indexed corpus.** Cost is a **one-time ~$175–350** at typical Web Unlocker rates (~$1.5–3/1,000 fetches), scrapeable in days, throughput under our control. *This is the volume engine.*
- **SECONDARY — PropRadar Starter (already upgraded: 20,000 calls/mo, ~19,850 remaining).** Not the corpus tool — per-address enrichment is ~3 calls each = ~6,600 addresses/mo ≈ **18 months** for the band, which would eat the whole quota. Its real jobs: (1) **suburb selection** — one snapshot call/suburb (`GET /suburbs/QLD/{suburb}`) to rank which suburbs have the $1–2M house stock worth scraping first; (2) **`/properties/recently-modified`** (Starter-unlocked) — a daily "who just listed / cut price / sold" nationwide feed = the strongest **inbound seller-intent trigger** we can buy (a distinct, high-value use beyond corpus building); (3) verification + `POST /properties/bulk` fallback for addresses Domain can't resolve.
- **Decision:** Bright Data for the bulk corpus; PropRadar Starter for suburb-selection + the ongoing intent feed. Don't spend the 20K/mo quota on blind per-address enrichment — the scraper is cheaper and faster for that.

**The crawl-budget/authority ceiling still binds** (survives either tool). Timeline-rich pages index far better than thin skeletons — that's precisely why this beats both the sold-feed and the earlier "dump bare cadastral" idea (agent B's "scaled content abuse" risk was about *thinness*, which real timelines remove). But a young domain can only get so many new pages *crawled and indexed* per week regardless of quality. So roll the 117K out in **watched waves, highest-value suburb first — not all at once** — and treat the arrival-rate uplift as **real but lagged** (indexation is days-to-weeks; more pages ≠ instantly-more arrivals).

### Constraint B, resolved — the on-demand / lazy enrichment architecture (Will, 2026-07-29)
The bulk scrape is **not the default** — it demotes to an accelerator. The insight: we don't need to pre-enrich 117K addresses; we need URLs that **resolve and self-enrich on first touch, cached forever**, so the corpus fills *along the contour of real demand*. At ~17 requests/day, enriching a subject on first arrival costs ~3 PropRadar calls → **~1,500/month ≈ 8% of the 20K Starter budget** (under half even at 5× growth). The `off-market.$slug.tsx` SSR loader (already an async server fn reading Cosmos via `getNearbySoldComps`/`getMarketMetricsSummary`) is the hook: on a cache-miss, fetch PropRadar → write back to the doc → render; mirrors the hardened `offmarket-intel`/`offmarket-positioning` cache-forever pattern (schema-versioned).

**Data-timing tiers:**
| Tier | When | What | Source |
|---|---|---|---|
| **0 · Indexing floor** | SSR, at crawl time | address, land, lat/lon, comparable **range**, market verdict | cadastral (100%, instant, 0 calls) + per-suburb cached comps; per-address gap = subject last-sale + beds/baths |
| **1 · Instant serve** | first paint | hero: address, Mapbox aerial (from lat/lon, no backend), last-sale anchor, "homes like yours $X–$Y" | Tier-0 cache → instant |
| **2 · Fast async** | on load, 1–3s | richer attributes, valuation estimate, capital-gain, scarcity/competition ratio | **on-demand PropRadar** `/properties/{id}` + existing intel poller |
| **3 · Slow async** | on load +delay, 40s–3.5min | LLM positioning (scarcity narrative, personas, "how we'd position it") | existing positioning queue, cache-forever, rotating loader |

Tiers 2–3 **already work this way** in the deck (market-pulse on mount, intel poller, positioning queue). Only new plumbing = the Tier-0/1 loader-level on-demand fetch+cache.

**The one honest catch — indexing ≠ serving.** On-demand-on-*human*-request can't bootstrap *indexing* (the human only arrives after Google has indexed the page). Two resolutions, and they change who pays the API bill:
1. **Crawler triggers the same enrich.** SSR loader fires PropRadar on *any* first hit (Googlebot included), caches forever → full page at crawl. Works, but now **crawl rate (not human rate) sets API spend.** Young-domain crawl is slow (hundreds/day), so at *wave-controlled sitemap growth* it stays inside 20K/mo. **Lever to watch = sitemap-URLs-exposed vs crawl rate.**
2. **Zero-call synthetic floor.** The comp range + verdict derive from per-suburb data on the subject's cadastral land/lot; only subject last-sale is truly per-address. **Open empirical question: does a floor with address + land + suburb-comp-range + market (no subject last-sale) index as well as today's pages?** If yes → near-zero-cost indexing for all 117K, rich data layering in on first touch. If subject last-sale is load-bearing for indexation quality → we need that one datum before crawl (a single cheap PropRadar/Bright Data pull per sitemapped address).

**So:** on-demand PropRadar (cache-forever) = the default enrichment model for *serving* (cheap, demand-shaped, perfect UX). Bright Data bulk = accelerator only for (a) pre-warming the indexing floor if the synthetic floor won't index, or (b) getting ahead of organic crawl when we want faster feedback than lazy enrichment delivers.

**Google index "quota" is a non-issue** — sitemap discovery is free; there is no per-URL submission quota (the Indexing API is JobPosting-only; URL-Inspection 2,000/day is our *monitoring* budget). **The real, finite resource is crawl-budget × domain authority × page quality.** Consequences:
- **Do not dump the ~84K bare southern addresses** — thin, mostly non-house/out-of-bracket, and risks a "scaled content abuse" domain-level signal on the seller-funnel's home domain (this reproduces the March "discovered-not-indexed" failure).
- **An other-city lap is the worst ROI** — new thin pages, no local authority/links, no impression base, diverting crawl from the corpus that's ranking. **Will's instinct is correct — skip it.**

---

## 5. Reward design (the RL heart)

Use **reward shaping** — a dense proxy the loop can learn from now, plus the sparse true reward it ultimately optimises:

| Tier | Signal | Density (today) | Role |
|---|---|---|---|
| **Dense (shaped)** | deck-depth reached, per-card dwell, forward-swipe rate, first-swipe survival | thousands/week *once instrumented* | fast policy signal; where the loop actually learns |
| **Mid (behavioural)** | menu-door click, `forward_cta_clicked`, deep-dive build start | ~10/week now | intermediate intent |
| **Sparse (true)** | `offmarket_qualify`, lead submit, book/call/print | ~1/week now | the real objective; used to validate that dense gains transfer |

The known risk with shaping: optimising the dense proxy (e.g. "make people swipe") can diverge from the true reward (a real seller signal). Mitigation: **weekly** re-check that dense-reward gains still move the sparse reward; if a variant lifts swipes but not intent, it's a false winner (the funnel already saw this — high-CTR agent-trust angles that never converted).

---

## 6. Cadence

| Rhythm | What happens | Why |
|---|---|---|
| **Daily (evening, after the day's organic traffic lands)** | One Claude cycle: read state → attribute what engaged & why → stage/adjust **one** content variable → document (`cycles/`, ledger, PostHog, `job_run` self-monitor) | Organic arrivals don't respond to a cron; hourly would analyse a handful of noisy sessions. Evening captures the full day. |
| **Light mid-day checkpoint (optional)** | Monitoring-only rollup (no changes) | Early read; no policy churn. |
| **Weekly** | Actual **kill/scale verdicts** on arms | At ~17 users/day, single-arm significance is a *weekly* question, not a daily one. Daily is for observation + hypothesis staging; weekly is for decisions. Prevents over-fitting to 5-session noise. |
| **Twice-daily** | Only after coverage expansion materially lifts arrivals | Justified by volume, not by ambition. |

**On "a lap experiment in another city":** don't. It burns crawl attention for near-zero index yield (Section 4). If a second geography is ever wanted, treat it as a *separate, authority-first* initiative, not a fast RL lap.

---

## 7. Proposed phased roadmap (for discussion — nothing committed)

**Phase 0 — Make the loop observable (instrumentation; ~days, cheap).**
Unify per-card schema across both arms; add `card_index`, per-card dwell, swipe-outcome, deck-terminal marker; add the dense shaped-reward events; collapse to **one** deck arm variant so trajectories are comparable (or instrument both identically). *Exit test:* a clean card-level funnel with dwell + a dense reward series, both arms comparable. **Until this exists, the loop has nothing to learn from — this is the true first task.**

**Phase 1 — Lift volume via lazy, demand-shaped enrichment (coverage; on-demand default, Bright Data as accelerator).**
(a) Add the **Tier-0/1 on-demand-cache-forever hook** to the SSR loader — non-core cache-miss → PropRadar subject fetch → write back → render (mirrors the intel/positioning cache pattern). (b) Rank the 26 southern-to-middle suburbs by $1–2M house stock (one PropRadar snapshot call each) and **sitemap in waves, highest-value first** (e.g. Palm Beach, Burleigh Heads, Mermaid Waters, Reedy Creek), so crawl-triggered enrichment stays inside the 20K/mo budget. (c) **Run the synthetic-floor indexing test** (Section 4): sitemap a sample of non-core URLs whose SSR floor is cadastral + per-suburb comps + market (no subject last-sale) and measure indexation vs the core rate — this decides whether we can index the 117K near-free or must pre-pull the subject datum. (d) Densify internal links among off-market/property pages; (e) stand up the PropRadar `/recently-modified` feed as an ongoing inbound-intent trigger. **Bright Data bulk** only if (c) fails or we want to pre-warm ahead of organic crawl. **Watch GSC 2–4 weeks per wave.** *Exit test:* a wave indexes + pulls impressions at the core rate → scale suburb-by-suburb; if it piles into "discovered-not-indexed," that's the authority ceiling → shift to links/PR, not more pages. Runs **in parallel with Phase 0** (backend vs frontend) but the *loop* needs both.

**Phase 2 — Run the content loop (the RL cycle).**
Daily Claude cycle over a **low arm count (2–4)** from the Section 5 palette, seeded with the funnel's proven mechanics (specific personal numbers > abstract; narrative + $-shock + personal ask; fear > aspiration; the first-swipe wall as the #1 target). Deck-depth as dense reward, downstream-action as sparse validator; weekly kill/scale; attribute every winner's *why*; document each cycle; self-monitor as a registered job. **First hypotheses practically write themselves:** (a) fix the hero→value-range −62% first-swipe cliff (put a specific personal number *above the first swipe*); (b) test your-street premium / dynamic case study / full valuation range as the hero payload; (c) shorten the pre-ask sequence and surface a low-friction ask earlier (the `/for-sale-v3` ladder is the counter-model).

### Phase 1 — execution spec (approved by Will, 2026-07-29): `offmarket_coverage_scraper`
**Goal:** mint ~**500 net new HOUSE off-market pages/day** across southern-to-central GC, GSC-governed, self-verifying. Daytime cron (can run through the day). Wrapped in `job_run("offmarket_coverage_scraper", cadence_hours=24, …)` (Rule 7).

**Per-address pipeline:**
1. **Enumerate** cadastral skeleton docs (address + lot) in the current target suburb, ordered by **house-dominant suburbs first** — Nerang, Mudgeeraba, Highland Park, Worongary, Reedy Creek, Palm Beach, Burleigh Heads, then unit-heavier central (Southport/Broadbeach/Surfers) last where houses-only trims hardest.
2. **Fetch timeline** via `shared.domain_fetch.fetch_html` (Bright Data Web Unlocker — bypasses the Akamai block); parse `__NEXT_DATA__` for full sale/rental timeline + attributes. ~$1.5–3/1,000 fetches.
3. **House filter** — keep `property_type ∈ {House, Duplex, Semi, Villa, Terrace}`; drop Unit/Apartment/Land. Expect ~**1.5× scrape-to-net** (~750 fetches/day → ~500 houses). Non-house results are cached as "skip" so we don't re-fetch.
4. **Eligibility** — apply the exact off-market rule (exclude `for_sale`/`under_contract`; `sold` only if ≥12 mo; never-sold needs `transactions`; waterfront excluded).
5. **Enrich + write** to the `Gold_Coast` doc (transactions, attributes, `url_slug` via `slugify` parity with the frontend). Rich per-address data beyond the floor fills lazily on first real visit (the on-demand tiers, §4).
6. **Sitemap append** — add to `getOffMarketUrls`; `index,follow` once sale-history present; ping Google. **Sitemap is the only sanctioned submission path** — no Indexing API (JobPosting-only; ToS risk).
7. **Screenshot self-verification gate (the "check its own work" step).** Headless Chrome (`site-inspector.js` / puppeteer-core + `google-chrome-stable`) shoots the **LIVE** `/off-market/<slug>` page and swipes the deck (ArrowRight) card-by-card; the cycle **reads the PNGs multimodally** (Read tool) and confirms: hero photo + address correct, last-sale/timeline rendered, comp range sane (not unit-inflated), no broken/empty cards, no honesty red-flags. Fails → a review queue, not a publish-confirm. Gotchas baked in: live page not Vite-dev (signal-16 death); wait past the SSR dark-deck hydration flash; cached/settled addresses only (LLM positioning cards take 40s–3.5min); headless is PostHog-bot-filtered (QA shots don't pollute analytics). Sample-verify (e.g. 1-in-N + all first-in-suburb) if per-page shots are too heavy at 500/day.
8. **Self-report** — daily metrics to Systems Health: houses minted, scrape→house hit-rate, sitemap-submitted, **verify-pass-rate**, Bright Data spend, and (weekly) the GSC indexed-vs-discovered ratio.

**Governor (the number to watch, not the scrape rate):** 500/day is supported by evidence — the initial ~16.9K sale-history corpus indexed at an effective >500/day on this domain. But hold it **GSC-governed**: weekly read of *indexed vs "discovered/crawled – not indexed"*; if a not-indexed backlog builds, that's the authority ceiling → throttle and shift effort to **internal-link suburb hubs** (crawl budget follows links), not more URLs/day. **Expectation set honestly:** indexed ≠ trafficked (~19% of indexed pages pull impressions), so owner-arrivals climb over weeks-to-months, not per-day. **Corpus ≈ 90–100K houses → ~6 months at 500/day.** Runs in parallel with Phase 0; RL payoff waits on both.

---

## 8. Open questions for Will

1. **Sequencing:** agree that **instrumentation (Phase 0) comes before any loop**, given the reward is currently ~1 event? Or run a coarse loop on deck-depth in parallel while instrumentation lands?
2. **Enrichment model:** agree the default is **on-demand PropRadar, cache-forever** (demand-shaped, ~1,500 calls/mo at current traffic) with **Bright Data bulk only as an accelerator** if the synthetic indexing floor won't index or we want to pre-warm ahead of crawl? Confirm we **skip the other-city lap**.
3. **Coverage scope & pace:** sitemap the 117K southern-to-middle band (incl Nerang) **in watched waves, highest-value-suburb-first**, gated on the per-wave GSC indexation result — with the synthetic-floor test up front to decide near-free-index vs pre-pull-the-subject-datum?
4. **PropRadar Starter roles:** it's for **on-demand serving + suburb-selection + `/recently-modified` inbound-intent feed + verification**, not bulk pre-enrichment? Worth standing the intent feed up now as its own seller-signal, independent of the RL loop?
5. **Arm strategy:** collapse to a **single canonical deck** and A/B *cards within it*, or keep `rich` vs `ladder_dark` as competing whole-deck arms (harder to instrument comparably)?
6. **True-reward definition:** for the sparse reward, is the target `offmarket_qualify` (in-deck seller signal), a lead submit, or a **booked call / posted appraisal**? This sets what the loop actually optimises.
7. **Cadence:** daily observe + weekly decide (recommended), or push for twice-daily once Phase 1 lifts volume?

---

## Appendix — key numbers (all measured 2026-07-29 unless noted)

- Off-market traffic: 176 pv / **151 unique** / 9 days · ~17/day · **94% Google organic** · 62.5% mobile · 82s avg session.
- Card funnel (dark arm, 68 users): hero 53 → value-range 20 (**−62%**) → … → qualify **1**. Any downstream action: **10 (6.6%)**.
- Indexation: ~16,900 off-market sitemap URLs · ~15,000 indexed (90% sample) · **2,889 surfacing** / 5,276 impr / 156 clicks (28d). Off-market > property on impressions.
- Coverage: core 17,247 eligible / **1,573 $1–2M houses**; whole-GC 17,349 / **1,601** (only ~28 more than core). Non-core = skeleton.
- **Corpus lever (Bright Data timeline scrape): 117,038 non-core cadastral addresses** across 26 southern-to-middle suburbs (Nerang 8,070, Palm Beach 10,816, Burleigh Heads 9,572); ~1,580 enriched today → **~115K gap ≈ 7× current corpus**, one-time ~$175–350.
- PropRadar **Starter, 20,000 calls/mo** (152 used): suburb snapshot 1 call/suburb; per-address ~3 calls (~6,600/mo = 18 mo for the band — not the bulk tool); `/recently-modified` + `bulk` unlocked.
- Source funnel: day 1 — 21 angles, ~$374, 6 leads (4 quality), $9.21 avg CPL; converting mechanic = **personal open loop + specific $-shock**.

---

*Research inputs: PostHog project 348370 (behaviour); GSC Search Analytics + URL Inspection (indexation); Gold_Coast DB counts against the live sitemap eligibility rule; `scripts/propradar/propradar_client.py`; the off-market codebase (`OffMarketDeck.tsx`, `ladderShared.ts`, `flowContent.ts`), the mini-site resolvers, and the Home Owner Lead Funnel ledger/monitoring. See memory: [[organic_offmarket_pivot_2026-07-23]], [[offmarket_deck_card_dropoff_2026-07-27]], [[offmarket_ladder_arm]], [[propradar_api]], [[home_owner_lead_funnel]].*
