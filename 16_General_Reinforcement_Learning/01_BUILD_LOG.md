# General RL — Build Log

Running log of what's actually built. Scoping: [`00_SCOPING.md`](00_SCOPING.md). Human deps: [`WILL_TO_ACTION.md`](WILL_TO_ACTION.md).

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
