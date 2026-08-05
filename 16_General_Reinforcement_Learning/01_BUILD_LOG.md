# General RL — Build Log

Running log of what's actually built. Scoping: [`00_SCOPING.md`](00_SCOPING.md). Human deps: [`WILL_TO_ACTION.md`](WILL_TO_ACTION.md).

---

## SEO Domain — First Cycle (2026-07-29 19:10 AEST)

### Signal Baseline
`seo_signal.py` + `reward_ledger.py` — 370 pages, 2,190 impressions, 39 clicks (1.8% CTR).
15 striking-distance pages, 3 low-CTR. 6/7 total conversions from organic search.
`searched_address` milestone = 26× conversion lift — address-query pages are the golden path.

### Key Findings
1. **#1 by volume:** market-metrics/Robina/overview — 295 impr at pos 11.9 for "robina property market" / "robina property growth". Page 2 edge.
2. **#2 by conversion value:** 12 property pages at pos 5-10 for address queries, mostly 0% CTR. Titles identical to Domain/REA, no differentiation signal.
3. 3 noindexed pages earning impressions — correctly suppressed (waterfront/sold).
4. Crash-risk meta says "March 2026" — stale.
5. 114 Florabella Drive ALL CAPS in title (data quality).

### Tier-1 Executed
- ✅ Bing URL Submission + IndexNow for 14 striking-distance pages (both HTTP 200)
- ✅ Noindex audit — 3 pages correctly suppressed, no action needed
- ✅ Signal stored to `rl_seo_signal`, actions logged to `rl_seo_actions`

### Tier-3 Drafted → WTA
- WTA-SEO-001: Property page title differentiation ("Sale History & Value Analysis")
- WTA-SEO-002: Robina market-metrics title sharpening ("Growth" target)
- WTA-SEO-003: Crash-risk meta stale date fix
- WTA-SEO-004: 114 Florabella Drive ALL-CAPS normalization

---

## Phase 0 — Shared reward ledger + milestone map  (started 2026-07-29)

### ✅ `reward_ledger.py` — the milestone map + reward-weight table (LIVE)
The foundation everything else grades against. Read-only analytics layer over existing data
(`organic_journeys`, `lead_worklist`, `ad_daily_metrics`, `cost_tracking`) — **touches no website
code**, writes one new collection `system_monitor.rl_reward_ledger` (`_id:"latest"` for fast read +
timestamped history docs).

**Computes each run:**
- **Milestone map** — for each user, which seller-journey milestones they reached, and each
  milestone's **predictiveness** = P(true_reward | reached), Bayesian-shrunk to base rate (tiny-N safe).
  Self-reweighting → the built-in Goodhart defence (a milestone earns only what it currently predicts).
- **Channel / referrer / ai_source attribution** of conversion (the GEO signal lives in ai_source).
- **Cost attribution** — FB/Google spend + organic marginal (ai_compute+infra) → cost-per-conversion.

**True reward (v1 proxy):** `organic_journeys.converted` (address submit / contact-capture) = identified-
seller candidate. Strengthened once the identity-join fix (Gap A) lands.

**First seeded run (2026-07-29, window 2026-05-30→07-28, 240 users / 265 sessions / 7 conversions):**

| Milestone | reached | conv | predictiveness | lift |
|---|---|---|---|---|
| searched_address | 10 | 7 | 0.476 | **16.3×** ← highest-leverage pre-reward milestone |
| viewed_multiple_properties | 10 | 2 | 0.143 | 4.9× |
| return_visit | 20 | 3 | 0.126 | 4.3× |
| search_in_coverage | 120 | 7 | 0.057 | 2.0× |
| viewed_property | 126 | 3 | 0.024 | **0.82× (below base — passive browsing doesn't convert)** |
| submitted_address ★ | 7 | 7 | 0.596 | 20.4× (the reward) |

**First actionable insight:** getting a visitor to the **address-search** step is the single biggest
lever (16× lift; 7 of 10 searchers converted) — validates the FB funnel "what's MY number" law from the
onsite side. Passive property-browsing is *below* base rate → not a milestone worth chasing.

**Cadence / self-monitoring:** cron `30 0 * * *` (after the nightly `organic_journey_build` at 23:40).
`job_run("rl_reward_ledger", cadence_hours=24)` → self-registers on Systems Health Process Registry (Rule 7).
Validated: heartbeat status=success.

**Run:** `python3 reward_ledger.py [--dry-run] [--window-days N]`

### ✅ Identity join widened — lead-signup + subscribe forms (LIVE, deployed d22f3da)
Gap A: `posthog_distinct_id` was forwarded only by AYH/off-market/ladder forms. Now the for-sale-gate
(`SignupGate`→`lead-signup.mjs`) and newsletter (`SubscribeModal`/`SubscribeForm`→`subscribe.mjs`) forms
forward the **anonymous** PostHog id too (Will: no `identify()`, no new PII), and both backends persist it
on `lead_signups` / `subscribers`. → those conversions become joinable to the visitor's journey going forward.
Verified: react-router build clean; pushed as ONE Trees-API commit (Netlify discipline); deploy logged.

### ✅ Off-market deck trajectory added to the shared ledger (2026-07-29)
The Off-Market RL initiative (`15_Off-Market/Reinforcement_Learning/`) is an **application on this shared
framework**, not a fork. `organic_journey_build.py` now reconstructs `/off-market` sessions (previously dropped
as "not notable") and captures the deck events by presence — `offmarket_report_view`, `card_viewed`, `deck_exit`,
`offmarket_menu_*`, `forward_cta_clicked`, `offmarket_qualify` → new journey fields `is_offmarket`,
`offmarket_events`, `offmarket_card_views`. `reward_ledger._user_milestones()` grades four new milestones:
`offmarket_page_view`, `offmarket_deck_engaged`, `offmarket_intent_sell`, `offmarket_qualified` — same
predictiveness weighting as every channel. **First read:** offmarket_page_view reached 153 / lift **0.70 (below
base)** — the off-market engagement bottleneck, now quantified in the shared reward truth. The off-market cycle
READS this ledger for the macro/delayed reward and reads its own dense deck signals (dwell/swipe/reached-%) from
PostHog directly. One reward truth, many loops.

### ⏭ Next in Phase 0
- **Strengthen the true reward:** upgrade `reward_ledger.py` from the `converted` proxy to a real
  join across `lead_worklist` / `lead_signups` / `subscribers` / `offmarket_qualification` on
  `posthog_distinct_id` → contactable-seller (name+email+phone+intent). Now unblocked as the widened
  distinct_id data accumulates.
- **Retroactive stitch (optional):** best-effort backfill of distinct_id onto historic leads where a
  matching journey exists (email/session heuristics). Lower priority than forward-capture.
- **Then Phase 1:** the GEO/AI-channel flagship loop (pending WTA-008 approval).

### ✅ Weights now informed by full-year history (2026-07-29)
The milestone weights were learning off the thin 60-day journey build (7 conversions). Now each milestone's
current-window rate **shrinks toward its year-long PostHog rate** (measured via funnels [milestone →
address_submit], 365d), weighted by how much history backs it (`HISTORICAL_PRIORS` in `reward_ledger.py`).
Effect: `searched_address` blended from a small-sample 70% down to a defensible **49% (26× lift)** — still the
dominant lever; `viewed_property` held near base by **524 people** of history (passive browse ≠ intent).
Refreshable as history grows.

---

## Phase 1 — GEO / AI-channel flagship loop  (started 2026-07-29, WTA-008 green-lit by Will)

The onsite→upstream feedback loop, and the first turn of the closed loop. AI-referred traffic is ~$0 marginal
and converting above weight → the cheapest pathway we have.

### ✅ `geo_signal.py` — the AI-channel SENSOR (LIVE)
Read-only over `organic_journeys` → `system_monitor.rl_geo_signal`. Classifies every session's engine
(`ai_source` + referrer): generative engines (ChatGPT/Copilot/Perplexity/Gemini = GEO targets) vs AI-adjacent
search (Bing/DuckDuckGo). Per engine: users, conversions, conv-rate vs base, lift, 8-week trend, landing pages,
and **DORMANT detection** (silent for the last two complete weeks = win-back candidate). Cron 00:45; `job_run`
`rl_geo_signal` cadence 24h.
**First read:** **Bing 3.7× base** (23 users → 2 conv, zero ad spend) — AI-adjacent search is our best-converting
channel; **ChatGPT DORMANT** (2 users W24, silent since — the "had leads months ago, none now" signal, auto-caught);
Copilot active (first referrals this morning). AI engines mostly land on `/market-metrics/Gold-Coast/overview`.

### ✅ `geo_cycle.sh` + `geo_prompt.md` — the Claude-as-analyst cycle (LIVE, daily 01:00)
Durable OS cron → headless `claude -p` (Claude Max), run_wakeup pattern: reads geo_signal + reward_ledger →
attributes WHY → researches GEO/AEO tactics (web + Brains) → produces a prioritised, editorial-compliant content
plan + win-back plan for dormant channels. **ANALYSIS/DRAFTS ONLY — never publishes** (publish routes to Will
via WILL_TO_ACTION). `flock`+`timeout`+`job_run` `geo_cycle` (Rule 7). First cycle kicked at creation.

### ✅ Live dashboard — "General RL — Control Loop"
Published control panel (reward-ledger milestone weights, GEO signal, running workflows, cost) so the whole
system is visible at a glance. Regenerate from `rl_reward_ledger` + `rl_geo_signal` + `job_runs`.

### ✅ GEO Cycle #1 — inaugural signal read + action plan (2026-07-29)
First full SENSE→ANALYSE→PLAN cycle. Key findings:

**Signal:** Bing converts at **3.67× Google** (23 users → 2 conv, $0 cost). ALL AI-chat engines (Copilot, ChatGPT)
land on `/market-metrics/Gold-Coast/overview` — our most-cited page. ChatGPT **DORMANT** since week 25 (7 weeks).

**Root cause (ChatGPT dormancy):** `/market-metrics/Gold-Coast/overview` is NOT in the sitemap (19,422 URLs, zero
Gold-Coast market-metrics pages). ChatGPT's OAI-SearchBot uses Bing's index; Bing uses sitemap for discovery/freshness.
Missing sitemap entry → Bing deprioritises → ChatGPT stops citing.

**Action plan (4 items, all WTA):**
1. **WTA-009 [CRITICAL]** Add Gold-Coast market-metrics (7 URLs) to sitemap — fix the discovery gap
2. **WTA-010 [HIGH]** Explicit AI crawler allows in robots.txt — prevent CDN/WAF blocking
3. **WTA-011 [HIGH]** Verify Bing Webmaster Tools — confirm indexation pipeline healthy
4. **WTA-012 [MEDIUM]** Quotable stat blocks + AYH bridge on market-metrics — increase citation + conversion

**Existing strengths confirmed:** 5 JSON-LD blocks (RealEstateAgent, BreadcrumbList, FAQPage, AnalysisNewsArticle,
Dataset), good SSR (46KB/20K chars), proper meta. The content is citable — the problem is DISCOVERY, not quality.

**Theory state:** AI citations follow `market-metrics entry → property interest → address search (26× lift)`.
The cheapest pathway to sellers is fixing the discovery pipeline so AI engines can find and re-cite what's already good.

Full cycle doc: `cycles/geo_cycle_20260729_1345.md`

### ✅ GEO Cycle #2 — Bing intelligence + theory correction (2026-07-30)
Executed 5 Tier-1 actions:

1. **Extended Bing URL submission** from 7 → 33 URLs (all market-metrics + key conversion pages). All batches OK.
2. **Deployed llms.txt** at `/.well-known/llms.txt` (commit `b4dd0aaf`, build clean).
3. **IndexNow ping** for robots.txt, sitemap.xml, llms.txt — all 202 accepted.
4. **IndexNow key verification file** deployed (commit `51085670`) — without this, prior IndexNow pings were unverified.
5. **Fixed personalization_policy.py bug** — `_id: None` → BSON null collision on re-run (commit `2ad5700b`).

**Critical theory update from Bing Webmaster data:**
- `/market-metrics/Gold-Coast/overview` was **discovered by Bing on 2026-05-18**, continuously indexed at position 3-5, and **last crawled 2026-07-28**. It was NEVER missing.
- robots.txt was **never blocking AI crawlers** — 0 blocked-by-robots in Bing crawl stats.
- **ChatGPT dormancy ≠ indexation failure.** The 2 users in W24 may be statistical noise, not a channel that died. The "sitemap gap" hypothesis is disconfirmed.
- **Bing is the real AI opportunity**: 23 users, 2 conversions (6.9%, 3.67× base), market data queries at position 2-5. Copilot sits on Bing → improving Bing ranking automatically lifts Copilot citations.

**Research findings integrated:**
- Tables = 2.1× extraction rate; question-shaped H2s = 34% more citations; front-loaded answers = 55% of citations come from top 30% of page. All support WTA-012.
- Speakable schema and Bing AI Performance report are new intelligence levers.
- Definitive language gets cited more, but conflicts with our editorial rules (no advice/predictions). DO NOT change — liability > citations.

Full cycle doc: `cycles/geo_cycle_20260730_0039.md`

### ⏭ Next
- Cycle #3: re-run sensors after organic_journeys rebuild; verify IndexNow key live; re-ping 33 URLs with verified key; compare Bing query stats W31 vs W30.
- WTA-012 (stat blocks + AYH bridge) — strongest content-quality lever, awaiting Will.
- WTA-013 (NEW) — Will to check Bing AI Performance report in Bing Webmaster UI.
- Strengthen the true reward (cross-collection distinct_id join) as the widened data accrues.
- Phase 2: onsite personalization (thin, two-surface) — WTA-004.

---

## 2nd autonomous domain — SEO (Google organic)  (2026-07-29)

Proves the GEO pattern replicates. Same shape: sensor + Claude-as-analyst cycle + self-pacing + tiered
execution + shared reward ledger + self-monitoring.
- **`seo_signal.py`** → `rl_seo_signal` (cron 01:00). Joins GSC per-page performance
  (`seo_landing_performance`, `search_console_queries`) with the conversion tie (`organic_landing_affinity`)
  → flags striking_distance / low_ctr / converting. **First read:** `/market-metrics/Robina` = **295 impressions
  at position 11.9 (page 2), 0.3% CTR** — the single biggest organic lever (and the page WTA-012 just made citable).
- **`seo_prompt.md` + `seo_cycle.sh` + `seo_dispatch.sh`** (cron :10/:30/:50 8-22) — tiered: Tier-1 executes
  indexation (Bing/IndexNow) + sitemap priority; Tier-3 (titles/meta/on-page copy — the #1 SEO lever, but public
  content) drafts + telegrams Will. Analysis+draft-heavy by design.
- **`cycle_pacer.py --job seo`** — generalized self-pacer (GEO's `cycle_state.py` left untouched); `rl_seo_cycle_state`.
- Self-monitored: `rl_seo_signal` + `seo_dispatch` heartbeats green. Coordinates with `seo_improvement_weekly.py`
  (checks rl_seo_actions to avoid collision).

**Now 2 autonomous upstream sub-workflows (GEO + SEO), both on the shared reward ledger.** Next domains clone the
same 5 files. Whole-upstream autonomy is the sum of these; the meta-conductor (cross-sphere coordination) is later.

---

## M1 — generic scaffold ✅ + M2a — Ads domain ✅  (2026-07-29, per DEVELOPMENT_PLAN.md)
- **M1:** `rl_cycle.sh <domain>` + `rl_dispatch.sh <domain>` (generic; lock/log/job/pacer by name) + `domains.yaml`
  registry. A new domain now = a sensor + a prompt + 2 cron lines. SEO migrated to it (cron repointed;
  seo_cycle.sh now a wrapper); GEO stays on its tested scripts (migrate in M8). `cycle_pacer.py` generalised (--job).
- **M2a — Ads:** `ads_signal.py` → `rl_ads_signal` (ties ad spend → real seller leads = cost-per-identified-seller,
  the cost-as-reward gap). First read: **$1,171/14d, blended $83.69/real-lead; one scale-worthy ad @ $6.30 CPL;
  the seller ad @ $203/lead; Buyer Brief @ $17.84 (buyer, not seller).** `ads_prompt.md` — spend is ALWAYS Tier-3
  (propose+telegram; the cycle never spends); coordinates with FB funnel + ad_lifecycle. Crons: signal 01:20,
  dispatch :05/:25/:45. Heartbeats green.
- **3 autonomous upstream domains now: GEO, SEO, Ads.** Remaining M2: Articles (M2b), revive FB organic (M2c),
  onboard FB-funnel + ad_lifecycle to write the shared ledger.

---

## M2b–M8 built + full self-test  (2026-07-29, per DEVELOPMENT_PLAN.md)
- **M2b Articles** ✅ `articles_signal.py` → `rl_articles_signal` (53 articles, 25 dead cold-start — honest thin signal) + `articles_prompt.md`. Cron signal 01:25 / dispatch :15/:35/:55.
- **M3 Onsite per-user** ✅ `onsite_signal.py` → `rl_onsite_signal` (42 known-hot frustrated vendors + 88 anon high-intent returning-searchers) + `onsite_prompt.md` (low-latency pacing; Telegram Will while warm; outbound = Tier-3). Cron signal 01:30 / dispatch :08/:23/:38/:53.
- **M4 Learning/grading loop** ✅ `arm_grader.py` → `rl_arm_grades`: grades PostHog flag-variant arms by true-reward lift vs control, min-N gated. **First verdicts:** discover_mode `scroll` LEADING (1.33×, 12 conv) vs swipe; for_sale `test_c` leading, `test_a/b` lagging. Cron 01:35.
- **M7 Meta-conductor** ✅ `conductor.py` → `rl_conductor`: holistic board over all 5 domains (health, each domain's top opportunity + next run, arm promote/retire recs, cross-sphere priority); advisory (never overrides self-pacing); daily Telegram digest. Cron 01:40.
- **M8 Self-test** ✅ `rl_selftest.py`: 51/51 checks pass (compile · signal freshness · heartbeats · pacers · crons · support collections · conductor health · ops-tab source). Self-monitored; telegrams on failure. Cron 01:50.
- **cycle_pacer** generalises pacing for all non-geo domains; **domains.yaml** registry now lists geo/seo/ads/articles/onsite all `live`.

**System state: 5 autonomous domains (geo, seo, ads, articles, onsite) on one shared reward ledger, an arm-grading
learning loop, a meta-conductor board, and a passing self-test — all self-monitored.** Remaining: M2c (revive FB
organic + onboard FB-funnel/ad-lifecycle to the ledger), M5 hardening (WTA-013 Gold-Coast aggregate; wider identity
join; true-reward switchover), M6 (P2.1 + offsite — gated on Will), and extending the ops Control Loop tab to render
the conductor's all-domains board.

---

## M2c + M5 (finishing the buildable remainder)  2026-07-29
- **WTA-013 ✅** `scripts/precompute_gold_coast_aggregate.py` — mints the `gold_coast` aggregate (txn-weighted
  from the 3 tracked suburbs) into precomputed_indexed_prices/_market_charts/_active_listings. The AI-traffic page
  `/market-metrics/Gold-Coast/*` now renders its citable Q&A **with real, honestly-scoped data** — "median across
  our tracked Gold Coast suburbs is $1,616,635 (+17.1%), 32.2 days" (verified: Robina 10.9%/Varsity 17.7%/Burleigh
  22.8% → 17.1% weighted). Frontend framing scoped to "tracked suburbs" (Rule 5, not overclaiming all-GC). Zero
  loader latency (precompute, not a runtime aggregate). Cron monthly (2nd @ 05:00).
- **M2c ad-action onboarding ✅** `ads_signal.py` now surfaces recent `ad_decisions` (FB-funnel + ad_lifecycle
  actions) into `rl_ads_signal` → the ads cycle + conductor see + grade what those loops did against the one reward.
- **M5 identity-join / true-reward switchover:** the reward ledger already UNIONS the journey proxy with the
  distinct_id-linked seller outcomes — coverage widens automatically as the (post-fix) linkage data accrues; no
  discrete build, it's a data-accrual curve. Reported in each snapshot's `true_reward` block.
- Self-test: 51/51 pass.

**REMAINING (all now gated on Will, nothing left to autonomously build):** (1) flip the onsite kill-switch
`genrl_personalization_v1` ON (after the onsite cycle proposes its 1st experiment + a perf re-check); (2) enable
FB-organic public auto-posting (Will's governance OK — public-facing); (3) offsite mechanism (WTA-005: PostGrid/
JustCall/manual). The autonomous build is otherwise COMPLETE.

---

## Onsite Cycle #1 — inaugural (2026-07-30 02:57 UTC)

### Job A — Hot Lead Surfacing
Surfaced **3 urgent vendor leads** to Will via Telegram:
1. **47 Tullamarine Drive, Robina** — 89d DOM, agency expires TOMORROW
2. **7 Turnberry Court, Robina** — 342d DOM (nearly a year!), 18d to 360-day mark
3. **20/6 Lowood Court, Varsity Lakes** — 88d DOM, expires in 2 days

Plus 5 additional expiring in Robina (Pinnacle Ct, Investigator Dr, Gardenway, Glades Dr, Acorn Ln).
All logged to `rl_onsite_actions`; `lead_worklist` annotated with `rl_surfaced=true`.

### Job B — First Experiment Proposed
**`onsite_exp_forsalev3_1`** on `/for-sale-v3` — the property-browse-to-address-search bridge.

**The stall:** 128 users browse listings (1.06× lift = dead end) but only 10 ever search their own address
(26× lift). The 118-user gap is the single biggest onsite opportunity.

**Arms:** control (nothing) vs `bridge_compare` ("How does your home compare?") vs `bridge_number`
("What is your home actually worth?"). Both test data-framed, editorial-compliant copy.

**Kill/Scale:** N≥150/arm, 14 days. Scale if searched_address lifts >2× vs control. Kill if no lift in 14d.

**Blocker:** PostHog Personal API Key lacks `feature_flags:write` scope (403). Flag could not be auto-created.
Telegraphed to Will: needs API key scope fix + master kill-switch flip.

Full cycle doc: `cycles/onsite_cycle_20260730_0257.md`

---

## Articles Cycle #1 — Inaugural Signal Read + Topic Theory (2026-07-30)

First-ever articles domain cycle. **The articles channel is dead:** 53 published, 0 conversions, 9 sessions, 20
GSC impressions. 25 of 53 articles flagged dead. 181 drafts unpublished. Last published: 2026-04-07.

**Root causes:** (1) Discovery failure — Google shows almost nothing; (2) Topic mismatch — bulk `how-it-sold` (14)
and `watch-this-sale` (7) articles compete with our own `/property/` pages; (3) No conversion bridge — no path from
article to `searched_address` (26× lift); (4) Publishing stalled for 4 months; (5) Non-SEO slugs (MongoDB ObjectIDs).

**One signal of life:** `major-projects` topic = ALL 9 sessions (athletes village pos 2 for "gold coast athletes
village"). Infrastructure content works because it answers unique queries with novel content.

**Topic theory (v1):**
- **Tier 1 (seller-proximity):** "what is my house worth [suburb]" + valuation methodology → AYH bridge
- **Tier 2 (pillar content):** "[suburb] property market 2026" → feeds market-metrics → indirect conversion
- **Tier 3 (infrastructure):** proven engagement, double down on athletes village / light rail / olympics
- **RETIRE:** how-it-sold, watch-this-sale, generic seller/buyer strategy

**WTA:** ART-001 (publish tier-1 valuation article), ART-002 (redirect draft pipeline), ART-003 (fix ObjectID slugs).

Full cycle doc: `cycles/articles_cycle_20260730_0630.md`

---

## ADS domain — First cycle (2026-07-29)

### ✅ `ads_cycle_20260729_1734.md` — cost-per-seller scorecard

First RL ads cycle. Analysed all paid channels through the seller-objective lens.

**Key findings:**
- **Zero paid leads reach the true reward** — identity-join gap means FB leads don't appear in organic_journeys
- **$1,172 total FB spend (14d), 21 leads, but only 4 are proxy-seller-leads (OOM test, Yes intent)**
- **Cost-per-proxy-seller: $142 blended** ($16.70 for Archetype A quality leads)
- **Cost-per-true-seller: $0 (organic only)** — all 7 true conversions are organic search/direct
- **AYH seller campaign dead:** $203 CPL, 1 lead in 90 days
- **Before You List stuck:** $0 spend despite ACTIVE — delivery issue
- **OOM test validated 2 archetypes:** Knowledge Gap ($16.70/Yes) vs Identity Threat ($4.27/No)
- **AN31 hybrid in test:** combines both archetypes — if $4-8 CPL with Yes intent, it's the GC deployment candidate
- **Star creative: AN2_missmillion_light** — $7.96 CPL, 2 leads, 100% Yes intent
- **The wakeup cycle system (03_Facebook/) manages copy discovery; this RL layer manages cost-per-seller economics**

**TIER-3 proposals:** WTA-ADS-001 (pause AYH), WTA-ADS-002 (investigate BYL delivery), WTA-ADS-003 (GC go-live AN2+AN14).

Full cycle doc: `cycles/ads_cycle_20260729_1734.md`

---

## Onsite Cycle #2 — Race condition fix + lead batch 2 (2026-07-29 17:35 AEST)

### Job A — Hot Lead Surfacing (batch 2)
Surfaced **3 more expiring vendor leads** to Will (not sent in cycle 1):
1. **2/3 Acorn Lane, Robina** — 84d DOM, ~6 days to 90-day expiry
2. **1/35 Thornleigh Crescent, Varsity Lakes** — 83d DOM, ~7 days to expiry
3. **4904/61 Investigator Drive, Robina** — 82d DOM, ~8 days to expiry

6 target-suburb leads remain unsurfaced (9-20 days to expiry — less urgent).

### Job B — CRITICAL INFRASTRUCTURE FIX
**`PersonalizationSlot.tsx` race condition.** Despite the master switch being ON and the experiment flag existing
with a 50/50 split, **zero exposures** in PostHog. Root cause: the slot used `requestIdleCallback` + raw
`window.posthog?.getFeatureFlag` — but PostHog SDK hasn't loaded flags by the time `requestIdleCallback` fires
on most visits. `getFeatureFlag` returns `undefined` → slot exits → nothing renders, nothing logs.

Meanwhile `forsale_ladder_v1` (14 evaluations in 24h) uses `phOnFlagsReady()` from `posthog.ts` — which waits
for the SDK. Same page, same PostHog load, different timing pattern.

**Fix:** Changed PersonalizationSlot to use `phOnFlagsReady` + `phGetFlag` (commit `862dad1`). The experiment
`onsite_exp_forsalev3_1` (bridge_compare vs control on `/for-sale-v3`) is NOW truly live — first real exposures
expected within hours of Netlify deploy.

**Lesson:** "status=serving" in MongoDB ≠ "actually running." Every serving experiment must be verified by
checking PostHog `$feature_flag_called` events within 24h. Zero evaluations + traffic = infrastructure bug.

Full cycle doc: `cycles/onsite_cycle_20260729_1735.md`

---

## GEO Cycle #3 — Re-ping + intelligence (2026-07-29 18:02 AEST)

**Signal unchanged** (same W24→W31 window — organic_journeys rebuilds at 23:40 AEST tonight). Cycle focused on
**verified submissions** and **Bing intelligence pull**.

**Tier-1 actions executed:**
- **GEO-010:** IndexNow batch — 36 URLs with VERIFIED key file (HTTP 202). First submission with
  the key file confirmed live (GEO-009 deployed it; this cycle verified + re-pinged all content pages).
- **GEO-011:** Bing SubmitUrlbatch — same 36 URLs in 4 batches (all HTTP 200). Pages now contain new
  stat blocks + AYH bridge (WTA-012) since the last submission (GEO-005) → Bing should re-crawl the enriched content.

**New Bing intelligence:**
- **InIndex jumped 34%** (1,663 → 2,247) between Jul 22-25. Predates our GEO work; likely sitemap regen.
- **Suburb-specific pages convert clicks at 22× city-level** — Burleigh Waters overview 67% CTR (2/3)
  vs Gold Coast overview 3% CTR (2/61). Validates per-suburb stat block approach.
- **Address-lookup queries** are the most valuable Bing user type — naturally aligned with `searched_address` (26× lift).
- **Athletes village article** gets 2 clicks despite ObjectID slug (WTA-ART-003).

**Tier-3 noted:** Duplicate FAQPage JSON-LD on overview pages (old vague + new specific). Should clean up old one.

**Backoff:** ~20h. No new signal until tonight's journey rebuild. All discovery work exhausted. Next lever = content quality impact measurement (W32-W35).

Full cycle doc: `cycles/geo_cycle_20260729_1802.md`

---

### Conductor Cycle #1 (Inaugural) — 2026-07-29 18:30 AEST

**Binding constraint identified:** 0% identity capture on address submissions. 63 property reports (44 in 30d), ALL with `owner.email=null, owner.phone=null`. The entire funnel — traffic → property view → address submit — works but dead-ends at anonymous lookups. No downstream seller outreach possible.

**Actions:**
- **Nudged SEO** to run its first-ever cycle NOW (was scheduled for tomorrow morning). Google organic = 91% of traffic; 15 striking-distance keywords. SEO is the only never-run domain.
- **Surfaced arm verdicts** for onsite domain: RETIRE `for_sale_page_v1` test_a/b/c (all lagging control at 2.89%), PROMOTE `discover_mode_v1` scroll (1.13× lift, 14 conv). ~55% of traffic currently wasted on losing variants.
- **Reordered cross-domain priority:** onsite > seo > geo > ads > articles (board had geo first, but identity capture is an onsite problem and is the binding constraint).
- **No Telegram to Will** — no inbox, no escalation needed.

**Key data:** 7 true rewards in 60d, all organic ($0). FB ads $1,172 → 0 true rewards. Off-market milestones ANTI-predictive (0.14×–0.71× lift). PersonalizationSlot bug fixed (a8409700, 9c30f1ea) — needs 24h verification.

Full cycle doc: `cycles/conductor_cycle_20260729_1830.md`

## Conductor Cycle #2 — 2026-07-29 20:15 AEST
- Inbox clear. Board 5/5 healthy; cycle-1 SEO nudge landed (SEO ran first cycle 19:10 → WTA-SEO-001..004).
- **Re-based the binding constraint** off hard data: the posted-report DISPATCH stage has never fired (0 queued / 0 dispatched / 0 delivered across 62 `property_reports`; no dispatcher exists). Cycle #1's "0% email capture" framing was wrong per strategy (don't chase email; address=reward, mail=channel). Real gap = the unbuilt/unrecorded final step, owned by no domain.
- Actions: durable memory updated (cycle 2); directive→onsite (post-expectation UX + flag real submits for a dispatch queue, no email gating); escalation→Will (WTA-015 + Telegram) with 2 questions + hold ad-spend scale-up; ads flagged for resource restraint ($1,172→0 true reward).
- Self-paced: BACK OFF (~10h) — constraint is human/physical, domains soaking.

## Conductor Cycle #3 — 2026-07-30 13:15 AEST
- Inbox clear (0 un-actioned). 0/3 Telegram used (held; WTA-015 <24h, no new decision).
- **Constraint RE-BASED (corrected cycle #2):** organic address-capture ~0% — 426 organic owner-lookup sessions → 0 address submits (10 searched); real public captures 60d = 4, ALL paid FB, 0 organic. Cycle-2's "7/60d capture works" was TEST DATA (offmarket_direct_test_v1, one morning 2026-07-21, distinct_id=null = Will's tests). Dispatch (WTA-015) now secondary — starved with ~4 real addresses.
- **Key insight:** onsite already owns + works this lever (browse 1.06× dead, address-search 26×); it was invisible because a PersonalizationSlot unmount/flag-timing bug (fixed a8409700+9c30f1ea) stopped any capture experiment firing. Awaiting first exposure data.
- Actions: conductor_state set (cycle 3, onsite-first); closed old onsite directive 6a69d3c3, issued sharpened 6a6ac339 (verify $feature_flag_called fires; value-hook offer to organic visitor; keep real-submit dispatch flag); updated WTA-015 in place with true capture numbers; held ads spend scale-ups (allocation call).
- Self-pace: next ≈90 min to read onsite's ~14:08 exposure result.

## ADS CYCLE — 2026-07-30 13:45 AEST (20260730_1345)
Context: Will paused the OOM copy-discovery loop ~13:40 AEST today for a Southern-GC rebuild (crons off, reward-ledger sync kept). Analysis is retrospective for OOM; forward focus = live GC seller spend.
- **Cost-per-identified-SELLER (paid → true reward): still ∞** — 0 paid seller conversions ever. Organic (7 submitted_address) is the only seller-producing channel.
- **Decisive finding:** BYL Seller-Book GC campaign came alive ($146/2,570 imp) but **0 leads** — 2 of 3 arms replicate confirmed-dead mechanics (Ad A multi-$ two-home puzzle = AN3 junk pattern; Ad C no-$ narrative). Only Ad B (Trust, single tool-miss $ gap) carries proven Knowledge-Gap DNA. CTA ("free posted guide") never opens a self-number loop + adds physical-mail friction.
- **TIER-1:** analysis written to `rl_ads_actions` (20260730_1345).
- **TIER-3:** WTA-ADS-004 (BYL: kill A+C, concentrate Ad B, fix CTA to self-number open loop; kill $60/0), WTA-ADS-005 (seed GC rebuild with AN2 star DNA, supersedes WTA-ADS-003). WTA-ADS-001 (cull AYH, still active $203/0) reaffirmed.
- Nothing executed (spend gated). Doc: cycles/2026-W31/2026-07-30/ads_cycle_20260730_1345.md.

## GEO Cycle #4 — 2026-07-30 14:20 AEST
- **Signal (fresh, post overnight rebuild):** Bing 31 users (was 23); Copilot W31=5 (record week, rides Bing); ChatGPT dormant 8wk; reward ledger 418 users/7 conv, searched_address 29.51× / submitted_address 35.25×. FB spend $1,742 / 0 true-reward.
- **TIER-1 EXECUTED — GEO-012:** submitted the 19 fresh articles the editorial pipeline published today (~13:42 AEST) to IndexNow + Bing SubmitUrlbatch (both HTTP 200). Sitemap (lastmod 07-29) predates them; step 121 regenerates it tonight — IndexNow gives minutes-latency discovery meanwhile. Did NOT force a sitemap regen (Netlify credit; self-heals tonight).
- **TIER-3 DRAFTED — WTA-016:** article bodies are NOT server-rendered — measured 0 `<p>`/0 `<h2>`/0-of-7 body-prose words + no Article schema in the article SSR, vs market-metrics fully SSR'd (76KB/67 `<p>`). Non-JS AI fetchers see a near-empty page. The fully-SSR'd pages are exactly the ones winning Bing/Copilot. Proposed: SSR the article body + add Article/NewsArticle JSON-LD. Render-path change → Will's call. Spec: WTA-016_DRAFT_article_ssr.md.
- **Theory:** SSR completeness is the AI-visibility gate; Copilot is a Bing-derivative channel; discovery is done, frontier = on-page extractable structure + conversion.
- **Next:** long backoff (~1200 min). Cycle #5 verifies tonight's sitemap picked up the 19 articles + W32 Copilot trend.

## Onsite Cycle 20260730_1423 — plumbing verified + golden-path bug confirmed fixed
- **Friction FIRST:** HIGH `SEARCH_RETRY_LOOP` (did 019e95d6, "120 Gleneagles drive", 37 searches/0 submits/abandoned on /analyse-your-home) confirmed = the whitespace-match bug on a REAL in-coverage home (120 Glen Eagles Drive, Robina exists). Verified **RESOLVED**: live address-search API returns it for one-word "Gleneagles"; incident predates the deploy. Residual: user typo "gleneages" (missing l) → separate fuzzy-match nice-to-have; friction sensor's own coverage classifier still non-whitespace-tolerant (mis-tags in-coverage as out).
- **PRIMARY directive (plumbing):** VERIFIED FIXED. `$feature_flag_called` for genrl_personalization_v1 went 0 (thru 07-28) → 2 (07-29) → 1 (07-30); onsite_exp_forsalev3_1 firing; arm_grader shows 17 users assigned. Last cycle's unmount fix (a8409700+9c30f1ea) worked. No longer a plumbing bug — gated only on Will's kill-switch + perf gate.
- **Read caveat:** kill-switch OFF ⇒ no render ⇒ bridge_compare 12.5% vs control 0% (N=17) is assignment NOISE, not a result. No winner called.
- **Experiment served:** onsite_exp_analyseyourhome_1 (/analyse-your-home, 3 arms control/street_range/range_gap → searched_address). Slot confirmed in main render path (AnalyseYourHomePage.tsx:283). Staged inert. Kill/scale: batch-of-10, N≥10/arm, SCALE if ≥1.3× control & holds 2 reads, KILL if flat 10d.
- **Telegram to Will:** bug fixed + plumbing confirmed + kill-switch decision (2 experiments staged, /analyse-your-home + /for-sale-v3).
- Conductor directive 6a6ac339 advanced, left OPEN (real-data read blocked on switch; secondary flag-stamp is Tier-3).

## Conductor Cycle #4 — 2026-07-30 14:27 AEST (instant-wake on Will's Telegram)
- **Will asked** (ads all switched off): take stock of 2wks, what works/not, ensure Brain 2 updated, plan next cycle = 1 proven funnel + a handful of targeted data ads.
- **Take-stock:** ~$1,743 / 107 ads → 21 contactable FB-form leads ($4-30 ea) + ~9 on-site addresses, but **0 inbound enquiries** and only 6/21 leads contacted. Ad funnel WORKS; leak is downstream (un-worked leads). Winning DNA = single clean $-gap + "a home like yours" + comparable range (AN2/AN3/Carousel-C). Waste = 38-ad AN## matrix (~$600).
- **Brain 2:** attribution+lead layers current (rebuilt lead_attribution today); AI session-summary layer stale (07-16, not cronned) — flagged.
- **Constraint re-based** (cycle #3 capture-0% → now downstream conversion/dispatch of leads we already hold; ultimate-reward leak is follow-up/WTA-015, not top-of-funnel). Priority onsite,ads,seo,geo,articles.
- **Delivered:** NEXT_CYCLE_AD_PLAN_2026-07-30.md (1 proven funnel + 4 budgeted arms replacing 107) + WTA-ADS-006 + ads directive (stay paused; collapse to proven funnel on Will's spend approval). Telegram reply (1). Inbox actioned.
- **Self-pace:** back off ~300 min — ball in Will's court (spend + dispatch escalations); instant-wake on his reply.

## 2026-07-30 15:30 AEST — SEO cycle 2
- Signal stable vs cycle 1 (GSC lags): 376 pages / 2,278 impr / 42 clicks / CTR 1.84%; 15 striking, 3 low-CTR, 0 converting.
- Diagnosis sharpened: 12 property pages rank page-1 (pos 5–8) for exact-address queries but ~0% CTR — a title/snippet problem, not rank. Our `<title>` is identical to Domain/REA with no value signal; the editorial `ai_analysis.meta_title` hook feeds only og:title, not `<title>`.
- TIER-1: refreshed signal + reward ledger (stored). Reindex deliberately skipped (nothing changed since yesterday's submit — quota discipline; reindex fires post-deploy).
- TIER-3 (top lever): drafted WTA-SEO-005 = property `<title>` editorial-hook hybrid, implementing conductor directive 6a69ca8ea8d4716b374fbf11. New `src/lib/propertyTitle.ts` + 2 edits; 115/119 published pages affected; Rule-5 clean (gaps/ranges, already-live copy). Ready-to-approve exact before/after in WTA. Directive left OPEN pending deploy. Telegram sent.

## Onsite cycle 20260730_1608 — HOLD-AND-ADVANCE
- **Friction CLEAR:** the 1 HIGH incident (did 019e95d6, '120 Gleneagles Dr', 37 searches/0 submits) = the already-fixed whitespace bug; last_seen 01:01 UTC predates the deploy → self-clears. `/for-sale-v3 ×11` client errors = benign `window.webkit.messageHandlers` TypeErrors (in-app WebViews), not our bug. Nothing escalated as broken.
- **Experiments HELD:** slot renders only `experiments[0]`/surface; both slotted surfaces (/analyse-your-home, /for-sale-v3) occupied by fresh un-read experiments → serving more = orphan flags. No real arm data (kill-switch OFF). Nothing served/retired.
- **Constraint-advance:** drafted **WTA-017** (Tier-3) + Telegrammed Will — add `PersonalizationSlot` to `/property` (the surface owner-lookup traffic actually lands on) + add `/property` to `SURFACES`, so the 29× browse→address-search bridge becomes testable; plus stamp real address submits (conductor SECONDARY). Files: `WTA-017_DRAFT_property_slot_and_submit_stamp.md`, `WILL_TO_ACTION.md`.
- **Leads:** no NEW contactable individual (known-hot vendors → lead_worklist; anon-hot anonymous).
- **Theory earned:** the onsite program is bounded by *slot coverage*, not arm count — scale slots, not proposals; and a re-surfacing HIGH friction incident may be a stale sensor classifier, not a live bug.
- Conductor directive `6a6ac339…` advanced (SECONDARY drafted), left OPEN (PRIMARY read blocked on Will's switch).

## 2026-08-05 10:15 — ops cycle (health-board triage)
Board: 16 actionable · ERROR=14 STALE=1 UNKNOWN-FRESHNESS=1 · KNOWN-GAP=44.
- **Fixed (Tier 1):** brain2 nightly chain — two failures in the 23:40 run (organic_journey_build PostHog 504
  after 3 retries; offmarket_home_signal hitting the already-fixed `offmarket_home: null` WriteError on a
  pre-fix log). Confirmed both scripts idempotent by reading them, re-ran both, both exit 0; verified via
  `job_runs` heartbeat (success 00:20:05, 232 contacts). Row clears on tonight's cron — not forced green.
- **Verified-and-left-alone:** CRM sync (self-healed, 5 clean runs since; red only because the 60-line tail
  window still holds the traceback) and Property timeline refresh (CursorNotFound fixed 2026-08-03, heartbeat
  success 408 timelines; Sunday-only cron so the log is legitimately frozen until 2026-08-09).
- **Raised:** WTA-OPS-001 (3 suburbs health-checked but unscraped since 2026-05-10 — two suburb lists diverged;
  180 stale `for_sale` docs underneath), WTA-OPS-002 (step 121 in `execution_order` but in no
  `schedule_manager` set — can never run), WTA-OPS-003 (Anthropic metered API OUT_OF_CREDIT, proven by live
  probe; every pipeline step now routes via OpenRouter/Max so probably obsolete), WTA-OPS-004 (timeline-refresh
  watched by both a log-tail probe and a heartbeat, which now disagree).
- **Left for next cycle:** the 8 pipeline-outcome rows at 0.1d — first observation each, from probes shipped
  last night. Step 18 (303 published valuations wiped in one run) and the 117-listing `under_contract` backlog
  are the two to take to ground next.
- Nothing silenced: no monitoring code, `job_runs`, crontab, cron/unit/step, or KNOWN-GAP touched.

## 2026-08-05 11:12 AEST — ops cycle (Samantha, standalone)
Board: 16 actionable · raw ERROR=14 STALE=1 UNKNOWN-FRESHNESS=1 KNOWN-GAP=44.
**Tier 1 repairs: 0** — nothing red was transient, so nothing was re-runnable. Reported as such.
**Tier 3 raised: 2**
- `WTA-OPS-005` step 18 — the "303 valuations wiped this run" row is mis-worded (the log line fires
  unconditionally on exclusion, no data is lost; 287–303 every night for 12 nights). Underneath it sits a
  bigger real finding: 307/540 for-sale listings are unvaluable, 223 on `missing_floor_area` alone, and
  widening. Proposed a product fix + a board fix (judge level/delta, not per-run event).
- `WTA-OPS-006` step 105 — all 158 image failures are NXDOMAIN on a **deleted** Azure storage account
  (`dig @8.8.8.8` empty, `curl` http=000). 11 listings analysed 0 images and were marked processed.
  Not re-runnable by construction; flagged the "why now" as explicitly unproven rather than guessing.
10 further rows deliberately left alone with reasons recorded in the cycle doc — 8 already covered by
WTA-OPS-001..004, and Brain2 + step 111 are red on evidence that predates their fixes and clear tonight.
No monitoring code, crontab, heartbeat or log was touched.
Cycle doc: `cycles/2026-W32/2026-08-05/ops_cycle_20260805_1112.md`
