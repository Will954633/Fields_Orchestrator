
## 2026-08-16 06:00 AEST — Ops cycle (health-board triage)

Board: 19 actionable (ERROR 14 / STALE 4 / UNKNOWN-FRESHNESS 1) against OK 167, KNOWN-GAP 43.
Briefing tier **current**. **1 root cause found, proven and repaired** — it accounts for 9 of the
19 rows. 1 recommendation raised (ledger 1/2). 1 grading.

- **[ENV-ROTATION-NEVER-DELIVERED]** — Domain.com.au ingestion dead **5 consecutive nights**
  (2026-08-11 → 08-15), `FATAL: 0 URLs` across all 6 suburbs, **including 3 nights after**
  `[BRIGHTDATA-TOKEN-ROTATED]` declared it restored. Root cause: `systemd` reads
  `EnvironmentFile=` once at unit start; `fields-orchestrator` (up since 2026-08-06 07:28) still
  held the revoked key, and `task_executor.py` passes `os.environ.copy()` to every step. Proven:
  daemon-held key → HTTP 401 "Invalid token"; `.env` key → HTTP 200.
- **Tier 1 performed:** restarted 7 verified-idle services (orchestrator + 5 pollers +
  spawn-worker), all confirmed holding the live credential; re-ran step 101 — Robina discovery
  **0 → 119 of 121 expected URLs**, 23 listings needing a first-ever detail scrape.
- **Wider sweep:** 5 of 83 env vars stale across 9 long-running services
  (`BRIGHTDATA_API_KEY`, `GITHUB_TOKEN`, `GMAIL_REFRESH_TOKEN`, `GOOGLE_ADS_REFRESH_TOKEN`,
  `GOOGLE_INDEXING_REFRESH_TOKEN`), `TRACKING_ADMIN_TOKEN` absent entirely.
- **REC-ops-004** (new) — approve restarting the 6 services left alone on blast radius
  (voice-agent, samantha-chat, watchdog, trigger-poller, valuation-api, offmarket-processor), and
  choose a durable delivery mechanism. Includes the trap: a credential-liveness monitor built the
  obvious way reads a **fresh shell** and would have shown GREEN on all five dark nights — it must
  probe `/proc/PID/environ`.
- **REC-ops-001 graded `no_effect`** — claimed 15 → ~6 actionable rows; measured 19. The token was
  rotated; the delivery mechanism ate it.
- Left alone with reasons recorded: the 6 `Coverage vs Domain` rows + `Nightly run` + `Step 101`
  + `Listing Discovery Coverage` (all downstream, should clear tonight); `Terminal states`
  (53 stuck `under_contract`, oldest 146d — flagged as next week's strongest candidate);
  `Schedule membership` (retired CatBoost, cosmetic); `Step 111 outcome` (UNVERIFIABLE, needs more
  time); GSC `invalid_scope` (already REC-ops-002, approved, unshipped); the two RL-fleet rows
  (single miss on a 168h cadence — watching, not acting).

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

## 2026-08-08 07:15 AEST — ops cycle (20260808_0715)
Board: 13 actionable (ERROR 9, STALE 3, UNKNOWN-FRESHNESS 1) · OK 129 · KNOWN-GAP 44.
**0 fixed · 1 new WTA · 1 existing WTA strengthened.** 11 of 13 rows were already open as WTA-OPS-001…014,
so the cycle went depth-first on the two that were not fully understood.
- **WTA-OPS-015 (new)** — Google Indexing: 10 consecutive nights of `Submitted 0/NN`, 843 attempted / 0
  accepted / 757 permanently dropped. Root cause **proven by direct token probe**: the refresh token is alive
  and grants `indexing` only, while `google_indexing.py:41-44` requests `indexing`+`webmasters` — a superset,
  so Google returns `invalid_scope` and the token refresh fails before any URL is submitted. Distinct from
  WTA-OPS-009 (`invalid_grant`). Confirmed the 2026-08-07 watermark-refusal fix is holding — the latest 86
  URLs were preserved, not dropped.
- **WTA-OPS-013 (addendum)** — Tier 1 read-only re-run of step 107 (verified `--fix` not passed) proved a
  genuine hang rather than buffering (72 s / 67,836 B on 08-05 → 1 byte across 6 attempts since), and found it
  holding **~5.0 GB RSS on an 8 GB VM** — a new, credible link to the August VM lockups. Diagnostic process
  killed and confirmed stopped.
- No repairs performed → no fix-history entry (Rule 1 covers fixes; nothing was fixed).
- No monitoring code, `job_runs` document, or crontab line touched. Nothing acknowledged or paused.
Cycle doc: `cycles/2026-W32/2026-08-08/ops_cycle_20260808_0715.md`

---

## Ops cycle — 2026-08-09 07:15 AEST

11 actionable. **1 fixed by me, 1 fixed by Will and verified by me, 3 proven false alarms, 3 escalated,
3 deliberately left alone.** Board raw ERROR=8 STALE=2 (+1 UNKNOWN-FRESHNESS).

**Ran the experiment two prior cycles left open.** `WTA-OPS-013` named the decisive test — *"run the audit under
`/usr/bin/time -v` on a quiet box and read Maximum RSS"* — and the 2026-08-08 addendum declined it as a plausible
way to wedge the VM. It ran cleanly:

```
current code (no projection):  150 s   peak RSS 7,348,876 KB = 7.01 GB   exit 0
projection, 5 fields:            7.8 s peak RSS   104,548 KB =  102 MB   exit 0
                                       400,193 docs, same box, ~5 min apart  →  19× faster, 70× less memory
```

That converts OPS-013 from hypothesis to measured fact, and **corrects the 08-08 addendum on two points**:
step 107 is *not* a hang (it exits 0 — `audit_collection()` simply prints nothing without `--verbose`, so silence
is expected output and the prior diagnostic was killed early), and the VM is 16 GB, not the 8 GB the addendum's
arithmetic assumed.

**Corrected a second prior diagnosis.** `WTA-OPS-011` concluded the FB approval poller's heartbeat was being
swallowed because the log ran to `22:57` while `job_runs` froze at `12:57`. Those are **the same instant** —
`job_status.py:70` stores UTC, mtimes print AEST, and today's pair are **32 ms apart**. The real cause is
structural and recurs nightly: cron `*/3 8-22` leaves a 9-hour designed silence against a declared
`cadence_hours=1`, so the row is STALE with certainty every morning at the 07:15 cycle slot.

**Verified Will's Google Indexing fix end-to-end** and marked `WTA-OPS-015` RESOLVED. The SA key landed
2026-08-08 07:49; the next run went from ten straight nights of `Submitted 0/N` + `invalid_scope` to
**85/85**. The 7b watermark guard worked — it refused to advance on the failed night, so those 86 URLs were
recovered. Residual left open: the 757 dropped before the guard existed.

**Raised:** `WTA-OPS-016` (3 sitemap pages — `/privacy`, `/disclaimer`, `/accuracy` — carry no canonical; the
check's `RuntimeError` mislabels them as "serve noindex", which they do not), `WTA-OPS-017` (retired step 6 is
indistinguishable from an accidental orphan, so the schedule-membership row is red forever — the paused-vs-dead
problem reappearing on the pipeline page).

**Nothing silenced.** No monitoring code, `job_runs` doc, cron, unit or step touched. Three rows are false alarms
and I left all three red — deciding they may stop alarming is Will's call.

**Process note, against last cycle's lesson:** analysis finished at ~14 min, everything written by ~30, one
Telegram. The three-message sprawl of 2026-08-08 did not repeat.

**Late addition (after the Telegram, noted in the cycle doc so message and ledger don't disagree):**
`WTA-OPS-018` — step 111's outcome check has **never matched its own log**: it greps
`r"TOTAL:.*?(\d+)\s+updated"` against a Python dict repr (`'updated': 0`), so no possible input matches. And
repairing only the regex would make it *worse* — its assertion (`updated == 0` → STALE) fires on the step's
healthy steady state, 2 of the last 4 nights. The step itself is fine. The wider worry is that this is a
`"capture"`-mode probe that silently never fires, and any other `_STEP_OUTCOME_CHECKS` entry could be in the
same state and look identical from the board. Auditing the rest is the obvious first task next cycle.

## [ops] 2026-08-10 07:15 — health-board triage cycle
Board: 11 actionable (raw ERROR=8, STALE=2, UNKNOWN=1). **Tier 1 repairs: 0.** Raised 1 new + 1 addendum.

Key observation: **9 of 11 actionable rows were already escalated and OPEN in WILL_TO_ACTION.md** — the board
is a queue of human-blocked items, not new decay. Spent the cycle deepening the two with real open questions.

- **[WTA-OPS-019] NEW** — `Gold_Coast` is 5.60 GB / 400,193 docs but MongoDB's WiredTiger cache is **1.61 GB**
  (`/etc/mongod.conf cacheSizeGB: 1.5`, dated 17 May, sized for the 8 GB VM we left on 1 Aug; Mongo's own
  default here would be 7.0 GB). `serverStatus` shows 783.54M pages read vs 783.43M evicted — 99.99%, textbook
  thrash. This is the amplifier under step 107 ([WTA-OPS-013], now **4 consecutive nights**, byte-identical
  1921s). Explicitly NOT claimed as the trigger — the cap predates the 06 Aug cliff by 11 weeks. Re-benchmarked
  the proposed projection fix at **206–471×**. Declined the same risky RSS experiment OPS-013 declined.
- **[WTA-OPS-015 ADDENDUM]** — the "757 dropped indexing URLs" residual measured, not assumed: only **10**
  documents still carry a `last_updated` inside the outage gap, and **0 are `for_sale`**. Recommended doing
  nothing rather than burning Indexing API quota on 10 non-live pages. Side-finding: the
  `REFUSING to advance the watermark` guard worked on 06 Aug then was bypassed by the fix-verification run
  (missing `--no-advance`); damage 1 doc.
- Confirmed false alarms, not re-raised: FB approval poller (cron `*/3 8-22` vs `cadence_hours=1`, healthy),
  ops_cycle itself (yesterday `Reached max turns (80)` → rc=1 after completing its writes).
- Left alone on purpose and recorded as such: step 113 (uninvestigated, possible 4th cache victim), step 12
  (Akamai block), steps 6/111/under_contract/sitemap canonicals (all already OPEN).

Integrity: no monitoring code, `job_runs` doc, crontab, unit, step or KNOWN-GAP touched. Raw ERROR still 8.
- **[WTA-OPS-020] NEW (added after the Telegram went out)** — went back to step 113 with leftover budget rather
  than leaving it as "uninvestigated". It is a **false alarm**: `detect_withdrawn.py` sorts by
  `withdrawn_last_checked_at` ascending, so the 40-min budget abort is a *rolling* sweep. Measured all 205
  `for_sale` listings — never-checked 0, MAX age **2.42d**, none older than 3d. The whole book is covered every
  ~2.4 days. Raised as probe-fitness (assert coverage staleness, not per-run completeness), not applied.
  ⚠ Method note: `withdrawn_last_checked_at` is an ISO **string**, not a BSON date — the datetime query
  returned 0/205 and would have read as total absence (CLAUDE.md Rule 8 caught it).

## 2026-08-13 13:09 — SEO cycle (first under the weekly contract)
- Signal: 477 pages / 3,494 impr / 52 clicks (1.5% CTR). `/property/` 1,720 impr, 27 clicks, 1.57% CTR at avg pos 8.5.
- **Finding:** property pages already rank page 1; the `<title>` is generic while the editorial hook sits unused in `og:title`. 92 published pages affected, Rule 5 scan clean → **REC-seo-001** (drafted ready to approve, `cycles/2026-W33/2026-08-13/DRAFT_property_title_hybrid.md`).
- **Finding (new):** 11 of the top 20 off-market pages by impressions serve noindex; 6 302-redirect to the `/building/` "coverage in progress" stub on an unverified PropRadar on_market signal. The replacement build has succeeded 2 of 14 times and has no failure recovery. Confirmed false positive on 4 Barbie Avenue (`listing_status: sold` vs PropRadar `on_market: True`) → **REC-seo-002**.
- Tier 1: sensors refreshed; 9 verified-indexable off-market pages submitted to IndexNow + Bing (both 200); `recommendations.py propose --help` crash fixed (unescaped `%`); 5 actions logged to `rl_seo_actions`.
- Ledger 2/2, at cap. Nothing graded (empty ledger). Cycle doc: `cycles/2026-W33/2026-08-13/seo_cycle_20260813_1309.md`.

## GEO cycle — 2026-08-13 13:20 AEST (first weekly-contract cycle)
- **Finding:** Bing impressions 488 (07-16→22) → **0 on every day 07-23→08-11**; bing.com + copilot.microsoft.com referrals 0 for W31/32/33. Bingbot still crawls 100-130 pages/day at 200 (robots blocks 0), but InIndex fell 2,247→1,998 and the AllOtherCodes bucket climbed +350-400/day from 07-28. Serving problem, not discovery. Google went the other way over the same weeks (68→151 sessions/wk).
- **Tier-1 shipped:** `/llms.txt` was a 404 (only existed at `/.well-known/`); created at root, fixed every Key-Pages URL (all pointed at 301-redirecting `/market-metrics/...`), and removed a false "confidence intervals" claim about our valuations. Build passed, ONE commit `55cc0d26`, live-verified 200.
- **Tier-1 deliberately skipped:** mass Bing/IndexNow resubmission — discovery is not the constraint; would have been churn.
- **Tier-3:** REC-geo-001 (Bing collapse diagnosis; geo-block 403+noindex vs the two Netlify pauses). 1/2 open.
- **Discarded evidence:** Bing SERP scraping — the control query returned unrelated results, so the method is invalid.
- Cycle doc: `cycles/2026-W33/2026-08-13/geo_cycle_20260813_1320.md`

## 2026-08-13 13:34 — ADS cycle (weekly contract, cycle 1)
First ads cycle under the capped ledger. Spend verified genuinely $0 for 13 days (the $207.56
in the 14d window is all 2026-07-30, the pause day); pause integrity audited — 13 adsets read
ACTIVE with ~$180/day armed but every ad beneath is paused, no leak. Verified the 08-10
[ADS-NO-LEAD-CONVERSION] fix is live in production, not just locally built.
Findings: 12/12 paid-attributed leads are BUYER campaigns (0 paid seller leads ever, seller ad
$203.29 → 0); /analyse-your-home has no organic discovery (0-2 views/wk pre-ads, 233 spike only
while paid ran) though it converts 5.4% (16/299); and the binding constraint is downstream —
appraisal_pipeline n=135 has NEVER advanced past draft_ready, 97 rendered reports and 128
print_only, with no posting stage anywhere in the schema (Rule 8 checked).
Proposed REC-ads-001 (optimise seller arms to the on-site address submit, not Instant Forms)
and REC-ads-002 (post the 97 finished reports before restarting seller spend). Ledger 2/2.
Deliberately withheld the Google valuation-intent proposal — same downstream gate, already
documented; it is REC-ads-003 once posting reports. Doc: cycles/2026-W33/2026-08-13/ads_cycle_20260813_1334.md

## 2026-08-13 13:42 — Articles cycle #2 (first under the weekly contract)
- **Reversed cycle #1's core verdict.** `how-it-sold` / `watch-this-sale` were called dead topics on 0 impressions across 21 articles. Those articles were never live — `articles.json` was frozen from 2026-06-01 ([ARTICLES-JSON-FROZEN], fixed 2026-07-30). Cycle #1 measured unpublished content and blamed the topic.
- **New evidence:** of the 19 articles Will published 2026-07-30, 12 rank for their own exact-address query at position 4.3–10.3 (median ~6.8) within 14 days. 74 address-query impressions. `how-it-sold` is now the largest impression source on the article surface (53 of 126).
- **Not claimed:** 1 click on 74 impressions is not a CTR signal (expectation at pos 7 is ~2–3). 0 conversions across 72 articles / 12 sessions — the format is proven to rank, unproven to convert.
- **Open risk named:** self-competition — up to 4 of our own URLs rank for one address query (`/articles/`, `/article/`, `/property/`, `/off-market/`). Net effect unmeasured.
- **Already fixed, not re-raised:** `/article/:id` → `/articles/:slug` 301 verified live ([ARTICLE-SOFT-404], 2026-08-08).
- **Correction:** cycle #1's ObjectID-slug problem applies only to the Feb–Apr batch; all 2026-07-30 articles and all current drafts have readable slugs.
- **Tier 1:** editorial Rule 5 scan of 23 drafts (1 false-positive hit); 3 of 15 draft sale prices verified against `Gold_Coast` sold records; address-collision check; theory written to `system_monitor.rl_articles_actions`.
- **Proposed:** REC-articles-001 — publish the 15 how-it-sold drafts (2026-08-10). 1 of 2 slots used; second held deliberately.
- **Published nothing.** Cycle doc: `cycles/2026-W33/2026-08-13/articles_cycle_20260813_1342.md`

## 2026-08-13 13:48 AEST — onsite cycle (first under weekly contract)
Found the whole onsite testing apparatus welded to two pages that no longer get traffic:
`/analyse-your-home` and `/for-sale-v3` were ~100% Facebook-fed and fell to ~2 users/week when ads
paused 2026-07-30. Organic (545 users/28d, flat, healthy) lands on the off-market deck (324) and
property pages (162), where `PersonalizationSlot` is not mounted — 9 of 545 organic users ever reach
address search. Deck readers do read (25 of 28 exits read >=1 section, median 2) but 0 of the 9
forward-CTA clickers reached the address funnel.
- Extended `experiment_manager.py` SURFACES to `/off-market` + `/property`; served
  `onsite_exp_offmarket_1` (control / next_step_plain / range_specific) — STAGED pending slot mount.
- Extended `onsite_friction_signal.py`: DECK_DEAD_END incident type (the sensor could only ever see
  the address-search funnel), `is_internal` excluded, `$exception_values` instead of the always-null
  `$exception_message`, `$rageclick` added.
- Answered + closed conductor directive 6a6ac339: flags DO evaluate, plumbing is fixed, the blocker
  is exposure volume.
- ⚠ Self-correction: derived "48% of deck readers exit at the hero" from `deepest_section` and had it
  in the hypothesis before catching that `sections_read` contradicts it. Corrected pre-read; filed as
  REC-onsite-002.
- ⚠ `genrl_personalization_v1` is ACTIVE at 100% — the mandate's claim that experiments are inert is
  stale. Served copy reaches users and is Rule 5 bound.
Proposed REC-onsite-001 (mount the slot) and REC-onsite-002 (V4 telemetry contradiction). 2/2 cap.
Cycle doc: cycles/2026-W33/2026-08-13/onsite_cycle_20260813_1348.md

## 2026-08-13 14:05 AEST — Weekly brief cycle 1 (Samantha)

First run of the weekly brief. All 6 domains ran (heartbeat + cycle doc both present for
geo, seo, ads, articles, onsite, ops).

**Input:** 10 open recommendations + the frozen 1,773-line `WILL_TO_ACTION.md` (48 open).
**Output:** 5 decisions to Will in one Telegram; `weekly_brief_20260813_1405.md`.

**Triage calls worth recording:**
- `REC-onsite-002` **withdrawn** — the `deepest_section` bug was fixed at 10:35 today
  (`[V4-DEPTH-MISLABELLED]`); onsite raised it at 13:48 without running `fix_digest.py`.
  Contract step 1(a) would have caught it. Feedback recorded in the withdraw reason.
- `REC-ads-002` **corrected, not accepted as written.** ads proposed ~$250 to post 97
  "finished reports" framed as leads already paid for. Checked the records first: 4 of 98
  carry a name, two of those being `Test Pipeline` and `E2E Test`; 2 emails, 1 phone. They
  are reports we generated for addresses that never asked — cold mail at ~0.9%, where 97
  pieces yields ~1 reply and cannot support the proposal's "0 replies would be decisive"
  kill-claim. Briefed the measurement gap underneath it instead.
- `WTA-OPS-005` **re-measured rather than trusted.** Old text: 57% excluded / 223 on floor
  area / 540-listing book. Today: 369 listings, 90 valued (24%), 142 excluded (102 floor
  area), 76 directional-only, **61 with neither figure nor reason** — a bucket nothing
  watches. Briefed on today's numbers.
- Two Rule 8 saves during this cycle: `valuation_data.exclusion_reason` is really
  `valuation_data.confidence.exclusion_reason` (wrong depth returned a false "0% excluded"),
  and `job_runs` keys on `job`/`status`/`run_at`, not `_id`/`last_status` — the contract's
  own Step 2 heartbeat snippet is wrong and returns empty for every domain.

**Dispatched (Rule 9):** GSC scope fix queued as a sandboxed patch task
`6a7d44040b9606f4246666bb` rather than spending a decision slot on a one-word change.

**Legacy backlog closed out:** 48 → 9 resolved · 7 duplicates merged · 5 superseded by fresh
ledger items · 2 briefed · 25 parked with an owning domain. Record in
`WILL_TO_ACTION_TRIAGE.md`. Nothing discarded silently.

**Waiting (named in the brief so Will can pull any forward):** REC-seo-002, REC-ads-001,
REC-ops-003, WTA-OPS-019 (mongod cache still 1.5 GB on a 15 GB box — verified today).

**For next cycle:** ~15 stale health-board rows are retired daily RL jobs still declaring
1–24h cadences after the move to weekly. Paused, not dead, but not registered as paused.
Handed to ops.

---

## 2026-08-13 — VALUATION domain, cycle 1 (first run; read-only week)

📐 **78.3% of the addressable for-sale book is valued (n=69), not 40.6%.** The headline
40.6% counts every live listing including the ones the method is designed never to value.
Restricted to detached houses the design envelope did not refuse: 54/69. Robina 38/49
(77.6%), Varsity Lakes 9/11 (81.8%), Burleigh Waters 7/9 (77.8%).

**Burleigh Waters' 16.7% is a composition effect, not a Burleigh Waters problem** — 45 of
its 54 listings are attached dwellings or above the design ceiling. On the homes the method
is built for it matches Robina to within 0.2pp. Brief open-question 3 answered: correctly
silent, no data-sourcing effort warranted.

**The brief's founding premise is retired.** "76 unvalued record no reason whatsoever — we
cannot tell a deliberate refusal from a crash" is false. All 76 record a machine-readable
reason and none is a crash: 42 carry `confidence.directional_reason` (above_design_ceiling
25, below_design_floor 12, price_above_threshold 5), 34 carry `confidence == "insufficient_data"`
with `n_total ∈ {0,1}`. `computed_at` is populated on all 76. The sensor reads only
`exclusion_reason` and labelled the rest "(no reason recorded)" — Rule 8 turned on our own
instrument. Second defect in the same shape: the envelope counter runs under `if has_rv`, so
it cannot see the suppressed population it exists to measure (printed `above 0` for Robina
against 25 real flags).

**Not fixed in-cycle, deliberately:** `valuation_signal.py` carries a Rule 7 heartbeat, so
it is monitoring code and permanently outside autonomous scope whatever the brief says.
Raised as `REC-valuation-001`, with the ask that brief open-question 1 — widening week-two
write access so the domain can stamp `exclusion_reason` onto the 76 — **should not proceed**.
It would grant write access to valuation documents to fix a reporting bug in the reader.

**Remaining honest coverage lever is 15 properties**, 9 of them a sourceable missing input
(7 floor area, 2 land size). Small, and that smallness is the finding.

**Noted for other owners:** the attached-dwelling surface is 32/113 (28.3%) and a *house*
envelope reason (`below_design_floor`) is stamped on 12 attached dwellings — the brief calls
units "excluded by decision" but `[UNITS-VALUATION-LIVE]` shipped them a live range on
08-10, so brief and product disagree. Two houses are misclassified `Vacant Land` (step 112
classifier, n=2, valuations themselves correct).

Record: `16_Valuation/experiments/2026-08-13-coverage-decomposition.md` (append-only) +
`coverage_decomposition.py`. Cycle doc: `cycles/2026-W33/2026-08-13/valuation_cycle_20260813_1845.md`.
Ledger 1/2. Nothing graded (first cycle). No property writes, no method edits, no recompute.

## 2026-08-13 18:56 — articles cycle #3 (weekly cron)
**Finding:** the Rule 5 gate had never been shown an article body. It lived in
`fb_post_article.py` and was only called on a title + one-line excerpt, so "71 of 73 pass"
was a true statement about 73 headlines sold as one about 73 articles. A body-level scan
found **14 of 73 breaching**, incl. a live section of `leading-vs-lagging-indicators`
telling readers to "Start your property search now" / "sell into strength" / "Make
buy/hold/sell decision" — the no-advice rule, the one with the liability rationale.
**Shipped:** new `scripts/editorial_gate.py` (body-level, context-printing, 8 documented
false positives); all 14 articles + 1 draft corrected → corpus 100/100 clean; gate wired
into `article_approval.py propose` so a failing draft can no longer reach Will.
**Also closed P5:** the wrong QLD licence number was hardcoded at
`fields-automation/scripts/push_to_ghost.py:125` (the plan said "not in the automation
repo"). A filesystem-wide search found two more LIVE emitters outside articles — the three
`/launch/` pages, one of which invites the reader to "verify on the Office of Fair Trading
register" against a number that fails, and `launch-form.mjs`. All fixed, one batched
commit, verified live.
**Ledger:** REC-articles-002 supersedes -001 to correct the "Rule 5 clean" claim made about
the 15 drafts. 1/2 open. Nothing published.

## 2026-08-13 21:00 — articles cycle #4 (`articles_cycle_20260813_2100.md`)
Will approved both open recommendations at 20:28 AEST; this cycle executed them.
- **REC-articles-003 shipped** — `fields-automation@d8895c0c`, 5 files: `learning_context.py` +
  `learning_snapshot.json` (new) inject 6,085 chars of measured headline CTR / read-depth / dead
  hook mechanics into every How It Sold + Watch This Sale prompt; `article_prompt_template.md`
  moves `## The Result` section 6 → 3. Rebased onto the REMOTE first — the local clone of
  `fields-automation` is stale and diffing against it showed phantom changes (`[REC-003-STALE-BASE]`).
- **REC-articles-002 shipped** — 15 how-it-sold articles published (73 → 88), gate 15/15 clean
  before any write, one Netlify build, `articles.json` and three live URLs verified.
- **Fixed a live soft 404**: `/articles/<any-string>` answered HTTP 200 with a generic shell.
  The 2026-08-08 pass fixed the legacy `/article/:id` route and 301'd dead ids INTO this one —
  the canonical URL Google crawls. Now 404s; real articles and draft previews still 200.
  `Website_Version_Feb_2026@f5af4d76`.
- Investigated the brief's "publishing workflow errors": all four 2026-08-09 failures were
  `credit balance too low`, already fixed on remote. Residual: 10 workflows set `USE_CLAUDE_MAX`
  without `CLAUDE_CODE_OAUTH_TOKEN` and rely on the runner user's `~/.claude` login.
- 9 of the 12 remaining drafts flagged `review_hold` — four duplicate pairs from a double
  generation run, one headline contradicting its own body (24% vs 24.5%), one body carrying a
  visible "…correction: +4.4%" editing artefact, and an asking-vs-valuation claim resting on our
  own model's known design envelope. 2 clean drafts proposed to Will (#B1FB, #3481).
- **Proposed nothing. Ledger 0/2.** Graded nothing — both items' metrics are weeks away.

## 2026-08-16 08:00 AEST — GEO cycle (weekly)

Found and fixed the reason AI surfaces describe Fields as a data company: **every AI crawler has been
served 403 + noindex since 2026-07-21.** `public/robots.txt` explicitly allowed GPTBot, OAI-SearchBot,
ChatGPT-User, PerplexityBot, ClaudeBot, Claude-Web and CCBot (GEO cycle WTA-010), but the geo-block
edge function's `BOT_USER_AGENT_PATTERN` listed none of them, and they crawl only from US IPs.
robots.txt granted access the edge silently revoked — and robots.txt is the only half observable from
Australia, so every check we run said "AI crawlers welcome".

Measured from a US residential IP (Bright Data `gold_coast_agency_level` as a plain proxy — the Web
Unlocker 502s on blocked pages and hides the status code, which is why last cycle could not test this):
bingbot 200, Google-Extended 200, all ten OpenAI/Anthropic/Perplexity/Meta/Amazon/CommonCrawl UAs 403.
`/llms.txt` 403 too. Consequence: the correct `RealEstateAgent` entity markup the seo domain shipped on
08-13 has been invisible to every AI crawler since it shipped.

Shipped the strictly-additive fix (commit `eb443be8`, one build, `npm run build` passed). Verified live
from the same US IP: all ten AI UAs now 200, ordinary US Chrome still 403 (block intact), AU 200.
fix-history `[GEO-BLOCK-AI-CRAWLERS-403]` — 2nd in kind after `[GEO-BLOCK-INSPECTIONTOOL]`.

Also measured brief §1 requirement (2) for the first time: AI still answers "functions as a
data-driven market analytics company", and Fields is absent from "best real estate agent Robina".
Baseline recorded for re-measurement next cycle.

Bing: 24 consecutive zero-impression days; InIndex 2,247 → 1,982 (−11.8%). REC-geo-001 superseded by
**REC-geo-002** — now carrying the measured cloaking divergence (US browser 403 + noindex vs bingbot
200 on the identical URL) and asking Will the single yes/no his own brief §7 poses. Holding 1 of 2.

Cycle doc: `cycles/2026-W33/2026-08-16/geo_cycle_20260816_0800.md`

## 2026-08-16 09:00 AEST — ADS weekly cycle
Brief tier `current`; $0 spend (paused since 07-30, deliberate). Rebuilt cost-per-identified-seller
from `fb_leads` × `ad_daily_metrics` (`spend_aud`) with `ad_id→campaign` via `ad_profiles`.
- **Answered brief §1.2:** Will's ~$15 forms are Independent Listing Analysis carousel **$12.75** (n=4)
  and Buyer Brief v2 email+phone **$14.66** (n=3); both BUYER. The $15.77 seller-intent form is the
  ex-GC copy test, not GC-served.
- **Headline:** GC seller lead campaigns $355.21 → **0** real leads; buyer lead campaigns $237.54 →
  13 leads → **7 identified GC homeowners = $33.93 each** via the `owns_gc_home` qualifier. Directional (n=7).
- Form length: v2 email+phone $14.66 → v3 +name $30.89. The *name* field, not the phone, doubled CPL.
- All 19 real leads reach `lead_worklist`; **0** reach any downstream collection. 0/145 appraisals past `draft_ready`.
- **Withdrew REC-ads-002** — self-verified wrong (counted key presence not fill; 94/97 reports have an
  empty name and never form-submitted). Samantha's brief §6 challenge was correct.
- **Self-corrected within cycle:** my $371.21 seller figure grouped by ad-name prefix and folded in a
  traffic campaign; the ledger's $203.29 was right. REC-ads-003 → superseded by **REC-ads-004**.
Ledger 2/2. No spend, no campaign touched.

## 2026-08-16 12:00 AEST — VALUATION weekly cycle (cycle 2)
Brief tier `current`; week-one **read-only** envelope observed — no property writes, no method
constant, no recompute, no fix-history entry (nothing fixed, because nothing may be).
- **Headline:** `valuation_signal.py` has **never read the live unit product**. Attached-dwelling
  valuations live in a separate collection, `Gold_Coast.unit_valuations` (keyed `url_slug`, gated
  on `publishable`); the sensor reads the **house** engine's `valuation_data` for every property.
  So the brief's "28.3% valued, n=113 — the domain's largest honest opportunity" is measured off
  the wrong engine. **True live-book unit coverage 34.2% (38/111)**, median comps **12** (not 3),
  median band ±13.6%, and the dominant blocker is **`no_class_matched_comparables` (54/72 declines,
  3,148/3,725 collection-wide)** — not empty pools. Third Rule 8 failure by this sensor against itself.
- **Two hypotheses killed en route, both recorded:** (1) `insufficient_data_but_valued 7` is a false
  positive — `summary.insufficient_data` is `len(chart_points)<5`, a **scatter-plot** flag
  (`precompute_valuations.py:3824`), disclosed honestly by the frontend. (2) "band narrower than its
  evidence" was an artefact of the same blindness; `[RANGE-VS-EVIDENCE-COPY]` (08-13) shipped on the
  unit engine and **stands — I found nothing wrong with it**.
- Book 212→256, raw coverage 40.6%→46.5%, suppression 70/256 (27.3%, correct refusal, not a defect).
- **Named, not claimed:** 1,303/5,028 non-publishable `unit_valuations` records carry a full
  point/low/high, computed 2026-08-15 — the writer as designed, not `[DECLINE-LEAVES-THE-OLD-FIGURE]`
  recurring. Safe only because one consumer gates on `publishable`; `[OFFMARKET-UNIT-THIN-RANGE-HOUSE-COMPS]`
  is an open 2nd-recurrence case of a second consumer getting units from the wrong source.
- **Carried:** 9 properties with no `computed_at` at all (3 classified House) — the mandate's real
  defect class, outranked this week. `[VALUATION-ENGINE-VOLATILITY]` is next cycle's candidate.
- **REC-valuation-002** proposed, **superseding REC-valuation-001** — one item on one file: four
  sensor edits (read `unit_valuations`; drop the chart-flag contradiction; plus cycle 1's two
  unfixed edits) and a correction to `briefings/valuation.md` §1/§3. Not self-applied: the sensor
  carries a Rule 7 heartbeat, so it is monitoring code and permanently outside autonomous scope.
Ledger **1/2** — free slot held deliberately. No backtest run; `accuracy/` figures quoted unchanged.

Cycle doc: `cycles/2026-W33/2026-08-16/valuation_cycle_20260816_1200.md`
Experiment: `16_Valuation/experiments/2026-08-16-unit-engine-sensor-blindness.md`

## 2026-08-16 16:00 AEST — Samantha weekly brief, cycle 2 (2026-W33)

**Ran:** 4 of 7 domains produced a cycle doc (ops, geo, ads, valuation). 7 recommendations
open; 5 briefed across 5 slots (ads' two merged into one), 1 filtered, 1 pushed back.

**The systemic finding was the harness, not a domain.** seo, articles and onsite all died on
`Error: Reached max turns (80)` — inside a 40-minute wall-clock budget they used 13–17 minutes
of. Two ceilings on one call, and the meaningless one was binding. onsite raised both its
recommendations and then died before writing its cycle doc: findings without the reasoning
behind them. articles had already lost a run to this on 08-13, making it a 2nd occurrence that
nobody caught, because the heartbeat detail read `claude -p rc=1` — byte-identical to an auth
failure.
- `weekly_cycle.sh`: `--max-turns` 80 → 200; added `TURN_FAIL` detection so the heartbeat says
  "hit --max-turns — the agent ran out of road mid-cycle, it did not fail to start".
- Re-launched seo, articles, onsite sequentially. Their docs and any new recommendations land
  after the brief, so this week's "7 open" is a floor, and I said so in the brief.

**Two corrections I made to domains' own evidence before it reached Will:**
- **ops** asked to restart 6 services carrying stale credentials. Diffed all six against
  `.env` via `/proc/PID/environ` plus `systemctl show -p EnvironmentFiles`: only
  `fields-voice-agent` and `fields-watchdog` read that file and hold stale secrets.
  `fields-trigger-poller` / `fields-samantha-chat` have no `EnvironmentFile`;
  `fields-valuation-api` / `fields-offmarket-processor` read *different* `.env` files.
  Restarting those four delivers nothing. The blast radius ops flagged as Will's to accept
  was largely not real.
- **onsite** claimed `genrl_personalization_v1` is live at 100% against a brief that records it
  OFF. Verified independently against the PostHog API rather than relaying it. True.
  `briefings/onsite.md` §2 corrected to carry both Will's stated intent and the measured state,
  marked UNRESOLVED — I did not resolve it myself, because which one is right is his call.

**Pushed back, not briefed:** REC-onsite-004 (report-section placement) — n=3 readers, and
onsite said so itself. Its own preferred fix is a reversible copy change inside its standing
authorisations. Feedback written into `briefings/onsite.md` §8: ship it and measure it; bring
Will the result, not the placement question.

**Graded:** REC-ops-001 → `no_effect` (by ops, honestly — the token was rotated and the
delivery mechanism ate it). Nothing else due.

**The channel is itself a finding.** Will answered 0 of 5 written questions last week and 9 of
9 tappable ones. `recommendation_approval.py` sends inline buttons and was never put on cron —
only its `poll` half runs. Not wired this week: it would have re-asked the five items being
briefed. If this brief also goes unanswered, switch to buttons next week.

**Carried:** tonight's 20:30 run is the real end-to-end proof that ingestion is fixed — the
check skipped on 08-13 that cost three dark nights. First item next cycle. Also still open and
still unbriefed: the 53 `under_contract` listings polluting the public absorption rate.

---

## 2026-08-16 16:44 — articles cycle #5 (weekly cron)

**The finding:** 0 of 90 published articles linked `/analyse-your-home`, and 88 of 90 had no
non-disclaimer internal link at all. Neither template CTA pointed there either. That is the
only page where the reward event (`analyse_home_address_submit`) can fire — `submitted_address`
carries lift 50.5 on the reward ledger (n=9 conversions). So "90 articles, 12 sessions, 0
converters" was never evidence about the format: **the funnel had no entrance.** The open
question this domain has carried for three cycles was unanswerable, not unanswered.

**Shipped** (2 commits, 2 builds, `npm run build` gated, verified live by fetch + headless
render + reading the screenshot): CTAs now lead with `/analyse-your-home/<suburb>` and emit
`article_cta_click`; internal article links canonicalised off the legacy `/article/:id` 301;
and three defects the screenshot exposed — the card-index merge (every SSR article page was
rendering the wrong category and **no suburb**, because the route loader's placeholders are
defined values and the merge copied them over the index), the mid-article CTA landing between
"The Result" and the result, and the median-house-price question being emitted on ~8 URLs per
suburb rather than the 2 the `seo` directive reported.

Also removed a leaked prompt instruction (`<p><em>Editorial opinion.</em></p>`) from a LIVE
article Will approved three days ago — found by scanning all 100 for residue. Cost 0 builds:
article bodies are served from Mongo by the route loader, not from `articles.json`.

**Proposed:** nothing (ledger 0/2). **Sent to Will:** nothing — the one draft without a
`review_hold` turned out to be a near-duplicate of a published article, disagreeing with it on
four shared figures ten days apart, with a predicted outcome in its "Our Take". Held with
reasons. **0 of 10 drafts are currently sendable.**

**Graded:** nothing due. **Directive from `seo`:** actioned, answered with two findings back,
closed.

## 2026-08-16 17:16 — onsite weekly cycle
Shipped `ReportAnchor` on the V4 deck: one line under the valuation answer pointing to `#report`
(report section reached by 3 of 53 entries; the answer above it by 19). Ships the withdrawn
REC-onsite-004's option (b) myself, per the conductor's brief-§8 feedback. Verified live desktop +
mobile; one deploy-hook rebuild needed after a three-commit push published without the CSS.
Fixed three measurement defects: `arm_grader.py` graded a 2-vs-2 conversion tie as a 1.15× winner
(arm verdicts must now survive one conversion moving); `onsite_friction_signal.py` swallowed every
HogQL failure, so its deck detector had never run in 8 snapshots of "0 incidents"; and once running,
that detector tested V4 readers against `forward_cta_clicked`, a V3-only event.
Ledger 1/2 — nothing proposed. REC-onsite-003 (kill-switch state + slot mount) remains the binding
constraint on the domain. Cycle doc: `cycles/2026-W33/2026-08-16/onsite_cycle_20260816_1716.md`.

## 2026-08-23 — ops weekly cycle
🔧 Ops: 22 actionable (2 fixed, 2 need Will) · board raw ERROR=11 STALE=10

- **Fixed** [STEP117-HOUSE-GATE-FALSE-RED]: step 117 failed the whole nightly run for 3 nights
  on an empty queue. `count_needing_analysis()` ignores the `_is_house()` gate that
  `fetch_candidates()` applies — 17 matched the filter, 0 were houses (all strata units).
  Gate-drained queue now exits success; Rule 7b assertion moved post-loop; latent
  `cursor.limit()`-on-a-generator AttributeError fixed. Verified exit 0. `ed909676`.
- **Fixed** [FB-APPROVAL-DOUBLE-POLL-ON-HEARTBEAT-FAIL]: `except Exception: poll()` meant a
  heartbeat write failure silently re-ran a poller that PUBLISHES to Facebook — ~10h of
  double-polls with no heartbeat. Import-only guard now. `9efdde94`.
- **REC-ops-005**: nine jobs declare a cadence but appear in no crontab, cron.d or systemd
  timer — they have never run on schedule, only once at creation. Draft cron lines at
  `artifacts/REC-ops-005_cron_lines_DRAFT.txt`. Crontab untouched.
- **REC-ops-006**: Gmail OAuth dead again (5th time since 07-24); FPF sent 0/4 emails on
  08-21. Raised as a decision — publish the consent screen, not re-auth-again.
- Disclosed: I left TWO stray rows (`fb_approval_poll_TESTPROBE`, `rl_ops_actions`) in `job_runs` rather than delete
  it (deleting heartbeats is absolutely forbidden to ops). Needs authorised removal.

## 2026-08-23 — seo cycle (weekly, contract) — SHIPPED, not proposed

Briefing tier **aging** (10d) → full standing authorisations. Ledger 0/2 at start.
Doc: `cycles/2026-W34/2026-08-23/seo_cycle_20260823_0700.md`.

- **SEO-001:** `overview` title → `{suburb} Property Market 2026: Median Price & Growth Data`
  + matching H1 and JSON-LD headline. The cluster is 402 impressions / **0 clicks** with two of
  three queries on page one (8.5 desktop, 9.3) — the 08-13 cycle read it as a rank problem off
  mobile-blended averages and skipped it. It is a click problem. Commit `38de5d92`.
- **SEO-002:** removed **6 stale "Updated March 2026"** meta claims, one on a page at pos 8.4
  with zero clicks. Removed, not refreshed — a hardcoded date always goes stale again.
- **SEO-003:** **Rule 5 fix in public tags** — `direction` promised "[2026 Forecast]" and
  "price projections" on every suburb. Rule 5 forbids predictions. Reworded to indicators.
- **SEO-004:** entity sweep. `/houses-for-sale/:suburb` `| Fields` → `| Fields Real Estate`;
  canonical Facebook URL at 3 missed call sites; and the big one — `netlify.toml` shadows
  **four `/about*` URLs** with three static files in which **three organization names claimed
  one root URL** ("Fields Real Estate" / "Fields Estate" / "Fields Research"). `/about` had no
  structured data at all; added a RealEstateAgent node byte-identical to root.tsx.
  Commits `07822316`, `fe13a1da`, `5a300771`. **Result: `names in use : Fields Real Estate`,
  one name across all 9 sampled pages, `entity_name_drift` cleared.**
- **SEO-005:** **widened `brand_serp_signal.py` 4 → 9 pages.** The 4-page sample had reported
  the site clean on 08-22 while all of the above was live. Fix for the class, not the instance.
- **SEO-006:** discovered the **goal-1 query set** the brief said was UNKNOWN. Every term lands
  on `/houses-for-sale/:suburb` (pos 22-41); `/for-sale-v3` ranks for **none** of it — only
  brand and noise. → REC-seo-004.
- **SEO-007:** 46 URLs to IndexNow + Bing (both 200), incl. 9 legacy `/market-metrics/*` for
  301 consolidation. Verified first that the migration is clean (301 ✓, sitemap ✓, canonical ✓,
  internal links ✓) — it is crawl lag, not a defect, and reported as such.
- **SEO-008:** evidenced Rule 5 directive to `articles` — 4 headline-field + 7 body-copy
  single-valuation figures live on `/for-sale-v3`, incl. `$1,726,668`, the figure Will's brief
  records as already having reached the brand SERP. Still live 10 days on.
- Proposed **REC-seo-004** (which page owns home-search intent) and **REC-seo-006** (delete the
  `/about*` static shadow, or delete the routes). Withdrew my own **REC-seo-005** mid-cycle
  after finding its scope was wrong — 4 URLs, not 1.
- Gates: `npm run build` before every push (4 batched commits, 4 builds); JSON-LD parsed before
  every push; live Googlebot fetch after every deploy; 12 actions to `rl_seo_actions`; 3
  fix-history entries in `logs/fix-history/2026-08-23.md`.

## GEO cycle — 2026-08-23 08:00 AEST

- **Bing recovered on its own on 2026-08-14** — 0 impressions for 22 days (07-23→08-13), then
  13/18/59/62/68/57/55, back to the ~70/day baseline; `InIndex` bottomed 1,982 and has climbed
  monotonically to 2,021. That is **two days before** the AI-crawler fix (08-16) and **nine days
  before** the 403→200 change (08-23). **Neither geo action caused it**, and last cycle's
  cloaking hypothesis is ruled out as the cause of the cliff — the divergence was still live
  when impressions returned. Recorded as a grading caveat on REC-geo-002, exactly as Will
  instructed when approving it.
- **TIER-1 GEO-020 — shipped REC-geo-002** (approved 08-18, unshipped 5 days). `geo-block.js`
  serves non-AU/NZ IPs the real page at 200 and annotates it (`x-fields-region` header,
  `fields_region` cookie) instead of 403+`noindex`. Build passed, ONE commit `4e1ca6cb`,
  deploy `6a8a1d7ec4b1d20008b743cd`. Verified from a US residential IP: ordinary Chrome now
  200 / 214,959 bytes / no noindex — byte-identical to bingbot, Googlebot, GPTBot,
  OAI-SearchBot, ClaudeBot, PerplexityBot. AU unaffected. Visible region notice deliberately
  not shipped (`hydrateRoot(document)` ⇒ edge HTML injection is a hydration mismatch; needs a
  `root.tsx` component, which is a perf-gated render-path change).
  fix-history `[GEO-BLOCK-403-TO-200]`.
- **TIER-1 GEO-021 — last cycle's open question answered: NO.** Access alone did not fix the
  description. Seven days after every AI crawler was unblocked, the three GEO-018 queries
  reproduce 3/3: "primarily a data company rather than a traditional real estate agency";
  absent from "best real estate agent Robina 4226"; no fieldsestate.com.au connection for the
  brand+founder query (top hit still Will's former agency).
- **TIER-1 GEO-022 — traced the misdescription to our own copy.** The answer opened with a
  near-verbatim quote of `OverviewSection.tsx:390`. `/about` visible text: "Fields Research" ×6,
  "licensed" ×0, "real estate agency" ×1 — and that occurrence is `<h2>Independence</h2>`
  saying *"not affiliated with any real estate agency"*, sitting directly beneath JSON-LD
  (seo, 08-23) declaring the page's mainEntity a `RealEstateAgent` with a Licensed Real Estate
  Agent founder. One page, both claims, and LLMs follow prose over schema.
- **TIER-1 GEO-024 — did NOT re-submit to IndexNow/Bing:** seo's `20260823_0700` cycle already
  submitted the same 46 URLs today. Duplicate churn avoided, non-action recorded.
- **TIER-3 REC-geo-003** — five copy edits with exact before/after in
  `REC-geo-003_DRAFT_about_page_agency_identity.md`. Needs Will because the `Independence`
  reword trades editorial credibility for agency-identity clarity, and needs seo because §5
  reserves copy to one writer. Holding 1/2.

## 2026-08-23 09:00 — ads weekly cycle
- **Ads restarted since last cycle** ($294.60): Seller Intent GC v1 ran 08-18→21 ($198.91, 2 real
  GC seller leads @ $99.45 — the first paid seller leads ever), paused by Will 08-21. 93 Burleigh
  Messenger carousel is LIVE ($95.69). Brief §2 ("all paused") is out of date.
- **Read all 8 Messenger conversations verbatim: 0 qualified, 3 self-declared misclicks, 3 Page
  blocks.** The $11.96/conversation headline is a tap-counting artefact — a Messenger-destination
  carousel converts photo-zoom taps into "conversations".
- **Fixed `[MESSENGER-CONV-INVISIBLE]`**: `ad_daily_metrics` never captured `lead` or
  `onsite_conversion.messaging_*`, so the only live campaign had no outcome column and read as a
  0-conversion cull candidate. Collector + `ads_signal.py` updated (257 rows backfilled); a new
  "MESSENGER — quality UNJUDGED" section surfaces them without counting them as conversions.
- Proposed **REC-ads-005** (switch the carousel destination or stop it). Ledger 1/2 — second slot
  held deliberately, arm-level seller read banked for the relaunch instead.
- Cycle doc: `cycles/2026-W34/2026-08-23/ads_cycle_20260823_0900.md`

## 2026-08-23 10:00 — articles cycle
Acted on the open seo directive (Rule 5 breach on /for-sale-v3) and found it was wider than
reported. Three server-side gaps: `property.mjs` served all 71 live listings' internal
editorial working fields (`_draft1`, `_reflection`, `_backfill_data`, `_agent_briefings`,
`_factcheck_failures` — 1,374,315 chars, zero consumers); `decision-feed-v3.mjs` shipped the
seller-only `gated` positioning tier (pricing strategy, negotiation buffer, first-offer
advice, agency ranking) on other agencies' listings; and the root defect — editorial is
generated once and never revalidated, so 4 listings were publishing an argument built on a
valuation the engine has since suppressed or dropped.

Shipped (1 build, 2 files): `stripInternals()` in property.mjs; `positioning_analysis`
withheld from the feed (payload −22%); `statesSingleValuation()` Rule 5 headline assertion.
Data: 66 fields / 39 listings rewritten from current values, 4 listings unpublished to
`needs_review`. Prompt rules 9-11 added. New standing guard
`scripts/editorial_compliance_check.py` (job_run, 24h, raises on scanned==0) — NOT on cron,
handed to seo/ops.

Left to seo deliberately: 38 abbreviated-currency figures in meta_title/meta_description
(their scope) + 4 verified stale asking prices. Proposed REC-articles-004 — the gated tier
renders deliberately on /property, so removing it is Will's call, not a bug fix.

Measured: FB page article trial answered — `post_fan_reach: 1` on every page post since
March (n=18). The constraint is distribution, not format.

## 2026-08-23 11:00 — articles cycle (chained)

Opened the GSC query data (`system_monitor.seo_landing_performance`, 30d to 2026-08-22) for the
first time and used it to answer the question the 10:00 cycle left open.

- **Falsified last cycle's hypothesis.** `major-projects` does not win on search demand — it
  ranks **position 48.7**. Its 11 sessions are not organic-search driven, so they were never
  evidence about query demand.
- **The real finding: how-it-sold ranks well and is under-deployed.** Where an article exists it
  sits at **mean position 7.0, CTR 2.1%** — but articles cover only **30 of 417** address
  queries (189 of 3,603 impressions). The problem is coverage, not format.
- **Built the first demand-led backlog** — 15 sold homes with existing search demand and no
  article, 312 impr/30d. Honest EV is 6–7 clicks/month; the case is intent
  (`searched_address` P(reward)=0.60, n=11), stated as directional.
- **Fixed `[ARTICLE-AUTHOR-DEFAULT-REGRESSION]`** — the 2026-08-13 byline fix corrected the
  corpus but not the generator, so 9 published articles had regressed to "Fields Research" and
  were also missing the `/about/will` author-entity link. Both generator defaults fixed and
  pushed; corpus 113/113.
- Retired 1 genuinely duplicate draft; **rejected 5 of 6 flags from my own similarity gate**
  after reading them.
- Proposed 2 drafts (#FD24, #407E) after verifying all 5 subject listings are still `for_sale`
  at the quoted prices.
- **Error, recorded:** proposed a published page-1 article by mistake (#6246). A NO tap would
  have unpublished it, because `cmd_poll` does not check the article was ever a draft. Withdrawn
  before any poll ran; article verified intact. `[ARTICLE-APPROVAL-PROPOSED-WRONG-ID]`.
- Nothing proposed to Will. Ledger unchanged at 1/2.
- **Next:** choose a *subset* of the 15 to write, so the untouched remainder is a control for
  "does an article add address-query demand or split it with the property page?"

## 2026-08-23 11:00 — onsite cycle (weekly)
Shipped REC-onsite-003 (approved 08-18, unshipped): mounted `PersonalizationSlot` on `/off-market`
(OffMarketV4, end of Part 01) and `/property` (PropertyPageV2, after the comparables).
`onsite_exp_offmarket_1` had assigned 247 users an arm and rendered to none of them. Added
`personalization_exposure` (control included) + `personalization_cta_click` so arms are graded on
what rendered, not on what PostHog assigned. Served `onsite_exp_property_1` (control/own_range/
no_contact → `#bridge`). Retired `onsite_exp_analyseyourhome_1` — indistinguishable from control on
a surface now at 6 page views/week. Fixed `arm_grader.py`: a zero-conversion control no longer
yields `lift=36585365.85×  → leading`; dropped the master kill-switch from FLAGS. Instrumented
`ReportAnchor` (no effect at first read, 3.7% → 3.7% of deck entries, 0 clicks — kill deferred one
week for a real denominator). Proposed REC-onsite-005: `for_sale_page_v1` still 25/25/25/25 with
all three arms lagging control over 1,530 users. Commits `45065400` (site), `0d1127fc` (orch).
Doc: `cycles/2026-W34/2026-08-23/onsite_cycle_20260823_1100.md`

## 2026-08-23 11:40 — articles cycle (chained, 3rd today)
Wrote the **treatment arm** of a pre-registered control group: 14 sold addresses with measured
GSC address-query demand and no article, split into matched pairs (125 v 127 impr/30d,
suburb-balanced), 7 written as drafts and 7 deliberately left unwritten
(`rl_articles_signal` cycle `20260823_1140`). Answers whether a how-it-sold article ADDS
address demand or splits it with the property page; read-out after 2026-09-22. n=7/arm —
a control group, not a powered test. Added `--address` targeting to `run_how_it_sold.py` so the
generator can be aimed at demand rather than recency.
Found **why the backlog existed**: `fields-automation` self-blocks weekly — 7 jobs inside a
2h05m window on a single-concurrency runner with no `timeout-minutes` anywhere; 5 runs
cancelled *unstarted* on 08-16/17 (no `Worker_*.log` for any of them), `how_it_sold` among
them. Fix written and YAML-validated for all 13 workflows; the PAT is 403 on
`.github/workflows` → **REC-articles-005**, recurs tonight until shipped.
Fixed the byline regression at its real source — **two writers, not one**:
`fields-automation/scripts/push_to_ghost.py` (not `push-ghost-draft.py`, patched at 11:00)
mapped 9 article types to a `Fields Research` byline; corpus now 120/120. Also fixed raw ISO
dates in prose at source (4 drafts) and `article_approval.py`'s drip cap crashing instead of
refusing. Verified OpenAI is at **zero credits account-wide** — vision degrades silently
(Rule 7b); broadcast to all domains. 1 draft proposed, 6 queued at 3/day in `ARTICLES_PLAN.md`
P1c. Chain stopped: the cap means the rest cannot go until tomorrow.
Doc: `cycles/2026-W34/2026-08-23/articles_cycle_20260823_1140.md`

## 2026-08-23 — valuation cycle 2 (read-only)

📐 47.7% of the for-sale book valued (n=214) · 33.2% envelope-suppressed · MAE 8.05% (n=581, quoted, not re-measured).

- **Approved REC-valuation-002 never shipped.** Approved 2026-08-18; `valuation_signal.py`'s
  last commit is 2026-08-13, working tree clean, `briefings/valuation.md` still cites the
  disproved 28.3%/n=113, and the rec's graded metric (`insufficient_data_but_valued` 7→0 by
  today) reads 5. The domain cannot self-serve — the sensor carries a Rule 7 heartbeat, so
  it is monitoring code. Raised **REC-valuation-003**: name an executor, or grant a one-file
  read-logic exemption.
- **Re-derived live unit-engine coverage independently: 38/107 = 35.5%** (robina 27/55,
  varsity_lakes 11/27, burleigh_waters 0/25). Confirms REC-002's 34.2% (38/111) — same 38
  properties. Dominant blocker `no_class_matched_comparables`, 50 of 69 declines. Median
  `n_comps` 12 vs the house engine's 8.
- **Burleigh Waters 0/2,235 publishable is CORRECT behaviour, not an outage.** 1,294 records
  compute a full range and are then withheld by the suburb accuracy gate
  (`unit_valuation.py:482`, `within10` 46.5% below threshold). The refusal is right; it is
  just silent — 1,202 rows carry no `decline_reason`. Recorded so nobody re-diagnoses it.
- Record: `16_Valuation/experiments/2026-08-23-unit-engine-coverage-and-bw-accuracy-gate.md`.
  Nothing written to any property document, method file or website. No backtest run.
- Open question for next cycle: 29 live attached dwellings carry a house-engine figure where
  the unit engine declined — does any reader see it? Not traced; no claim made.

## 2026-08-23 16:00 AEST — Weekly brief cycle 3 (2026-W34)

**7 of 7 domains ran** — first full sweep (the `--max-turns` ceiling fixed last week held).
10 open recommendations, **5 briefed**, 1 merged, 1 executed, 3 deferred with reasons.

**Will answered all five of last week's items** (verdicts recorded 08-17/08-18 with his own
reasoning). First clean sweep since the cycle started. Only unactioned chat message was
"Start briefing" (08-21) — a request to run the cycle, not a verdict; stamped `actioned_at`.

**Briefed:** REC-articles-004 (seller-only positioning tier published on competitors' listings
via the uncredentialed API — verified live by me on all 3), REC-articles-005 (automation
self-blocks weekly; recurs tonight 20:00 UTC), REC-ads-005 (Messenger carousel buying
accidental taps, 3 Page blocks), REC-ops-006 (Gmail dead, 5th occurrence, Testing-mode consent
screen), REC-geo-003 (/about denies we are an agency; AI surfaces quote it 3/3).

**Merged/sequenced:** REC-seo-006 folded into item 5 and directed rather than briefed — seo
said "either is fine", so it is engineering hygiene. seo deletes the static `/about*` files so
the React routes serve, *before* geo's copy edits land, otherwise geo edits a file nobody is
served.

**Executed rather than briefed — the finding of the cycle:** REC-valuation-002, approved by
Will 2026-08-18, had sat **five days with no owner**. The raising domain was structurally
barred (`valuation_signal.py` carries a Rule 7 heartbeat → outside autonomous scope), and the
ledger has `verdict → ship → grade` with **nothing that names who acts**. Shipped it myself
(`f09c50b4`): sensor joins `Gold_Coast.unit_valuations` on `url_slug` gated on `publishable`;
book split by engine (houses 58/107 = 54.2%, attached 38/107 = 35.5%); blended 47.7% retained
but flagged `blended_do_not_quote`; `insufficient_data_but_valued` renamed
`chart_thin_but_valued` and moved out of `integrity` (5 false positives → 0);
`briefings/valuation.md` §1/§3 corrected and §7 given the standing-authorisation question.
Logged `[RL-APPROVED-BUT-UNOWNED]`. **REC-002 overstated its scope** — 2 of its 4 claimed edits
were already in the file; fed back to valuation.

**Verification done before briefing, not after:** fetched all 3 gated-tier payloads live;
re-ran the Gmail pre-flight (`dead — invalid_grant`); pulled account-wide 7d FB spend
($294.60 across 2 campaigns, confirming ads' "only live campaign" claim is true *now* —
Will paused Home Owner Funnel on 08-21); read live `/about` (confirmed "licensed" = 0
occurrences). One claim did not survive first contact and was re-checked rather than reported:
articles' repro command for REC-004 used a `['property'][...]` wrapper the API does not return
— the finding held, the repro did not. Fed back.

**Health flagged:** ops's own `rl_weekly_ops` heartbeat is stale (last run 2026-08-15) although
ops ran and wrote a doc at 06:12 today — the domain auditing our self-monitoring is the one not
self-reporting. All seven briefs are 10 days `aging`, and two now contain statements that are
false (ads §2 "all spend paused"; valuation §1 carried a disproved figure until today).

One Telegram sent, 5 tappable rows, tokens printed beside each question. `mark-briefed` run
before the send, per the contract.

## 2026-08-30 06:00 — ops weekly cycle
- Board: 37 actionable (ERROR=16, STALE=20). Briefing tier `stale` (17d) → bug fixes only.
- **FIXED (Tier 1)** `[LIVING-MAP-COORD-FIELD-BLIND]` — `precompute_living_map.build_one`
  read only `doc["LATITUDE"]`, so 36 of 51 eligible for-sale listings that had a point under
  `geocoded_coordinates` were counted as having no coordinates and the whole job asserted
  "0 built". Added `georeference_data.coordinates` + `geocoded_coordinates` fallbacks.
  Re-ran: 33 built, 15 failed, heartbeat `success`. Pushed `202ce215`. The 15 residual have
  no coordinates under any path (unit addresses) and were left honestly red, not silenced.
- **RAISED REC-ops-007 (Tier 3)** — `weekly_cycle.sh:125` `set -e 2>/dev/null || true`
  enables errexit (file header is `set -uo pipefail`), so `ops_integrity.py` returning 1 on a
  violation kills the runner before it writes the `rl_weekly_ops` heartbeat. The 08-23 ops
  cycle ran and wrote its doc but has shown "may not be firing, 14d" ever since. The guard
  makes the board *silent* in the exact case it was built to make loud. Not self-applied:
  it is my own tamper guard's wrapper.
- Ledger now 2/2 at cap. Nothing due for grading.
- Not diagnosed, next cycle's first job: `live_leads_to_sheet` exit 1 blocking 2 steps of the
  nightly lead chain.
- **FIXED (Tier 1, added after first write-up)** `[FB-MULTISELECT-LIST-POISONS-SHEET]` —
  `live_leads_to_sheet` exit 1 was a Facebook multi-select answer arriving as a LIST in
  `fields["area"]`; Sheets fails the whole batch on a nested list, so one lead emptied the
  Live Leads Tracker and blocked 2 chain steps. Added `_cell()` coercion across all row
  values. Re-ran: exit 0, 33 rows added. Pushed `c6975144`. The 2 blocked steps left for
  tonight's scheduled chain (one prunes, one can alert — Tier 1 forbids re-running those).
- **FIXED (Tier 1)** `[INSIGHTS-NULL-ROOM-NAME-POISONS-POOL]` — step 15 failed the nightly run
  at an 18.96% error ratio. `get_room_area` used `.get('room_name','')`, which returns None on
  an explicit null; exactly ONE doc has one, and the function runs over the whole for-sale
  comparison pool, so it failed 140 of 738 subject properties. Guarded both branches and made
  the broad `except` print the address + traceback (it had hidden the cause behind a bare
  string). **Threshold untouched.** Re-ran: exit 0, zero errors. Pushed `8fceef9f`.

## 2026-08-30 07:00 — SEO cycle (briefing tier: stale, narrowed to bug fixes)
Found and fixed the measurement defect that has mis-sized this domain since it was built:
`seo_landing_performance` stored only GSC `[page,query,device]` rows, and Google DROPS
anonymized-query rows rather than bucketing them — so every consumer was summing **9.5% of
impressions / 6.7% of clicks** and calling it the channel (5,334/78 stored vs 56,341/1,168
actual, 90d). Collector now pulls three dimension sets tagged with `dims`; all four consumers
updated to filter. Two published conclusions were wrong as a result and are corrected in the
cycle doc: `/off-market/` is the site's ENGINE (34,588 impr, 801 clicks, 2.32% CTR — the best
large template, not the worst), and `/for-sale-v3` is at position 13.0, not 41.3.
Also fixed: `seo_signal`'s CONVERTING arm, which had never fired once (path-vs-URL join key).
Shipped: Rule 5 number-format fix across 60 live SERP fields on 46 properties ($1.4M ->
$1,400,000, in the live `<title>`); a `false_confidence_range` check for the ±12% band that
live copy calls a "high-confidence range" (65 of 359 properties); 46 URLs to IndexNow + Bing.
Closed: the `/market-metrics` -> `/market-intelligence` consolidation completed (legacy path
collapsed from ~50 impr/day to ~2-6 from 08-17; rank transferred, 9.5 -> 9.1).
Ledger: withdrew REC-seo-004 (its evidence was the 9% sample, two claims false), re-filed as
REC-seo-007 with true numbers. 2/2. Two peer directives sent (`articles`, `all`).
Doc: `cycles/2026-W35/2026-08-30/seo_cycle_20260830_0700.md`

## 2026-08-30 08:00 — GEO weekly cycle (briefing tier: STALE, 17d)

- **Measured** the post-REC-geo-003 result: description unchanged, but the engine is citing a
  ~3-week-stale cache (legacy `/market-metrics/*` URL, pre-08-13 title). Live pages verified
  correct as OAI-SearchBot. **REC-geo-003 is not gradeable yet** — due 2026-09-20 stands.
- **Bing fully recovered:** InIndex 1,987 → 2,127 monotonic over 12d, impressions 40–72/day,
  Code5xx 13 → 1. Neither geo action caused it (caveat retained on REC-geo-002).
- **Submitted** 11 identity + cited-overview URLs to IndexNow + Bing SubmitUrlbatch (both 200).
  Checked against `rl_seo_actions` first — not duplicate churn.
- **Closed the 3-cycle-old `AllOtherCodes` mystery.** 304 hypothesis tested and rejected
  (Netlify serves ETags but never answers 304). Decoupled from every health metric → stop
  tracking it.
- **Proposed 2 (at cap):** REC-geo-004 — `/about/will-simpson` says "licensed" ×0, "agent" ×0,
  and its Person schema contradicts `/about`'s `founder.jobTitle: "Licensed Real Estate Agent"`.
  REC-geo-005 — `/about/<anything>` returns 200 with a self-referencing canonical; asked Will to
  fold it into the open REC-seo-006 rather than decide the same cluster twice.
- Actions GEO-027…GEO-032 in `system_monitor.rl_geo_actions` (32 docs).
- Cycle doc: `cycles/2026-W35/2026-08-30/geo_cycle_20260830_0800.md`

## 2026-08-30 — ads cycle (20260830_0900)
Brief `stale`/NARROWED (17d). Measured 14d paid: **$796.08 / 17 form leads** — against a brief
that says all spend is paused. Cost per identified SELLER: **address ask $26.20 (n=4) vs
selling-intent ask $199.00 (n=1)** — directional, but corroborated independently by
`reward_ledger` (`submitted_address` = ★reward, 53.1× lift, n=13). Fixed
`owner_market_sms.py`: the per-suburb ad was forcing its own suburb into the resolver, so
Burleigh Heads owners answering a Burleigh Waters ad could never match — 3 of 4 paid address
leads came back unresolved and were told "I'm finalising your link" with no process behind
it. 2 of the 3 were in `address_search_index` already. Also closed a Rule 7b gap (the holding
SMS made an all-unresolved batch report success) and surfaced the orphaned
`om_needs_manual_link` backlog. Did NOT contact anyone — REC-ads-006. Also REC-ads-007: the
brief needs a rewrite. Pushed `9c09977`, `24ac3cc`.

## 2026-08-30 10:00 — articles cycle (briefing tier: stale/NARROWED)
Fixed the false-confidence breach at its source: root-caused it to our OWN prompt
(rule 9's exemplar embedded "medium confidence"; PART 7B listed the valuation range
under HIGH CONFIDENCE), not to the model. Added rule 9a + deterministic
`_strip_false_confidence()` at save time. seo reported 2 live breaches; the real
count walking the whole ai_analysis document was **20 published properties / 39
strings**, including a literal "90% confidence range". Backfilled to 0 remaining.
Added `_ensure_meta_title_street_number()` — 29/237 meta_titles dropped the street
number, 6 published, one publishing 4/44 Frascott Ave as "44 Frascott Ave" (a
different property); repaired 3, warned rather than guessed on the rest.
Corrected seo on abbreviated currency: the generator was already fixed 2026-07-24;
all 149 remaining abbreviated fields predate it and none are published.
Found and handed off a Rule 7b silent zero — pipeline step 105 processes 0
properties nightly and reports success because *.blob.core.windows.net does not
resolve from this VM (6+ nights). OpenAI still 429, 7 days open.
Retired my own "articles are organically dead" premise: corrected GSC data is 1,703
impr / 27 clicks / CTR 1.6% / position 9.4, ~11x what I had. Conversions still 0.
All 13 conversions pass through the address field; no article routes to it.
Proposed nothing (0 open, deliberately). Next cycle's blocker: the onward-routing
module is a NEW initiative and needs a refreshed briefing to start.
