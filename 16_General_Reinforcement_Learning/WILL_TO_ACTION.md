# Will — To Action (General Reinforcement Learning)

Human-only dependencies raised by the General RL initiative. The loop appends here + pings @WillFieldsBot,
and keeps working other arms rather than stalling. Item format:

```
## [WTA-NNN] Short title — raised YYYY-MM-DD — [sphere] — status: OPEN|DONE|WONTFIX
**Blocks:** what the loop can't proceed on.
**Needs a human because:** (new data asset / physical mechanism / sign-off / budget / GC go-live / legal).
**Proposed:** what Claude recommends.
```

---

## RESOLVED in scoping session 2026-07-29

## [WTA-001] Governance model — raised 2026-07-29 — [meta] — status: DONE
**Resolved:** Independent sub-autonomous workflows per domain + ONE shared reward ledger they all read/write.
Samantha = future meta-conductor over the top (manual-only today → no collision now). The two existing
autonomous loops (FB funnel, off-market RL) join the shared ledger for holistic view. (00_SCOPING v2 §4)

## [WTA-002] The single true reward — raised 2026-07-29 — [meta] — status: DONE
**Resolved:** True reward = **identified, contactable seller** (name+email+phone+intent in `lead_worklist`);
**proactive inbound enquiry = high-weight bonus multiplier**; booked-call/listing = weekly sanity-check.
Graded via a **self-discovering, self-reweighting milestone map** (weight = measured predictiveness). (§5)

## [WTA-006] Autonomy bounds — raised 2026-07-29 — [meta] — status: DONE
**Resolved:** FB-funnel model. Free on low-risk reversible (stage variants, cull weak ads, propose SEO/GEO/
articles, re-weight milestones, flag individuals). Routes here for real-world blast radius: net-new ad spend
beyond caps, **GC go-live**, physical mail / outbound calls, anything new public-facing. Never unattended on
the irreversible/costly. (§12)

---

## OPEN

## [WTA-003] Build the reward ledger + milestone map + identity-join fix (Phase 0) — raised 2026-07-29 — [foundation] — status: DONE (core)
**Resolved 2026-07-29 (Will: go ahead; forward anonymous distinct_id only, no identify()):**
- ✅ `reward_ledger.py` LIVE (milestone map + predictiveness + channel/cost attribution → `rl_reward_ledger`; cron 00:30; Rule-7 heartbeat). First insight: searched_address = 16× lift; passive property-view below base.
- ✅ Identity join widened — lead-signup + subscribe forms now forward `posthog_distinct_id` (deployed d22f3da, build clean, one commit).
- ⏭ Remaining (not blocking): strengthen true reward via cross-collection distinct_id join; optional retroactive stitch. Tracked in 01_BUILD_LOG.

## [WTA-004] Confirm onsite personalization scope — raised 2026-07-29 — [onsite] — status: OPEN
**Blocks:** Phase 2 (Sphere 1 build shape).
**Needs a human because:** real infra investment vs. a weaker flag-only alternative.
**Proposed (recommended):** THIN, STAGED server-side decision layer on the two surfaces with traffic
(`/for-sale-v3`, `/analyse-your-home`), keyed to milestone-state — NOT a site-wide engine, NOT before Phase 0/1
prove which milestones matter. Confirm. (§7)

## [WTA-005] Physical-mail + outbound-call mechanism (offsite) — raised 2026-07-29 — [offsite] — status: OPEN
**Blocks:** Sphere 3 (offsite closer) is theoretical until there's a repeatable way to post assets / place calls
at the loop's request.
**Needs a human because:** vendor/tool decision + budget (PostGrid print-post, JustCall/SMS, or Will-manual).
**Proposed:** confirm which the loop may assume. Phases 0–2 don't depend on it. (§9)

## [WTA-008] Approve GEO / AI-channel content as the flagship Phase-1 arm — raised 2026-07-29 — [upstream] — status: OPEN
**Blocks:** building the flagship feedback loop first.
**Needs a human because:** sign-off on a new upstream content type (AI-optimised / LLM-citation-friendly pages).
**Proposed (recommended):** yes — it's live (Copilot referrals this morning), instrumented (`ai_source`), already
converting (Bing 2/7 conversions ~4× Google), fast on both ends, and uncontested. Also runs diagnosis-and-recovery
on the dead ChatGPT channel (had leads months ago, none now). (§2.2)

## [WTA-007] Verify Samantha nightly DOER (02:30) status — raised 2026-07-29 — [meta] — status: OPEN
**Blocks:** clean governance — the infra map couldn't confirm the 02:30 DOER in the live crontab.
**Needs a human because:** you know whether it was intentionally moved/disabled.
**Proposed:** confirm status so the Conductor doesn't assume a loop that isn't firing.

## [WTA-009] Add Gold-Coast market-metrics pages to sitemap — raised 2026-07-29 — [GEO] — status: OPEN
**Blocks:** ChatGPT win-back + AI-engine discovery of our #1 cited page.
**Needs a human because:** sitemap generator change + deploy.
**Proposed:** Add 7 URLs (`/market-metrics/Gold-Coast/overview`, `/direction`, `/crash-risk`, `/sell-now`, `/buy`, `/suburb-compare`, and the index `/market-metrics/Gold-Coast`) to the sitemap. These pages get 100% of AI-chat traffic and 41% of Bing traffic but are currently invisible to sitemap-based discovery. ChatGPT likely went dormant because Bing deprioritised the page without freshness signals. This is the single highest-impact GEO fix.

## [WTA-010] Push robots.txt with explicit AI crawler allows — raised 2026-07-29 — [GEO] — status: OPEN
**Blocks:** AI crawler access verification.
**Needs a human because:** website file change + deploy.
**Proposed:** Add explicit `User-agent: GPTBot / Allow: /` (and OAI-SearchBot, PerplexityBot, ClaudeBot, CCBot, Google-Extended) to robots.txt. Research shows 41% of sites accidentally block AI bots via CDN/WAF overrides that ignore the generic `User-agent: *` rule. Explicit allows bypass this. Critical: `OAI-SearchBot` is what ChatGPT uses for search citations (separate from GPTBot for training).

## [WTA-011] Verify Bing Webmaster Tools + re-submit sitemap — raised 2026-07-29 — [GEO] — status: OPEN
**Blocks:** Bing→Copilot→ChatGPT indexation pipeline health.
**Needs a human because:** Bing Webmaster account access.
**Proposed:** Log into Bing Webmaster, verify sitemap submission, check crawl errors on market-metrics pages, re-submit after WTA-009 lands. Bing powers both Copilot and ChatGPT search — if Bing doesn't have our latest pages, AI engines can't cite us.

## [WTA-012] Approve quotable stat blocks + AYH bridge on market-metrics pages — raised 2026-07-29 — [GEO] — status: OPEN
**Blocks:** AI citation quality + conversion from AI traffic.
**Needs a human because:** content change on public pages.
**Proposed:** (a) Add "At a Glance" stat blocks with question-shaped H2s (e.g. "What is the median house price in Robina?") — 30-40% higher AI visibility per Princeton GEO study. (b) Add soft contextual link from market-metrics → AYH ("See how your home compares"). Both Bing conversions came through the market-data → AYH funnel; AI-chat users don't take that step because there's no visible bridge. Spec in `cycles/geo_cycle_20260729_1345.md` §3 ACTION 4-5.
