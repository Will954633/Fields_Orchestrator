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
**Will: approved thin/staged/two-surface + HARD perf constraint (site can't get slower).**
- ✅ Design: `PHASE2_DESIGN.md` — zero-latency architecture (server decides / client applies late, post-LCP; kill-switch; perf-gated). Baseline measured: p75 LCP 11-22s (!).
- ✅ P2.0 decision layer LIVE: `personalization_policy.py` → `rl_personalization_policy` (variants target the 26× address-search milestone; cron 01:15).
- ⏭ P2.1 (the one render-path touch) needs Will's nod: deferred-slot on /analyse-your-home, perf-gated. See PHASE2_DESIGN open question.

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

## [WTA-009] Add Gold-Coast market-metrics pages to sitemap — raised 2026-07-29 — [GEO] — status: DONE (deployed 2026-07-29, commit fcecf1f + sitemap 4a2d847)
**Blocks:** ChatGPT win-back + AI-engine discovery of our #1 cited page.
**Needs a human because:** sitemap generator change + deploy.
**Proposed:** Add 7 URLs (`/market-metrics/Gold-Coast/overview`, `/direction`, `/crash-risk`, `/sell-now`, `/buy`, `/suburb-compare`, and the index `/market-metrics/Gold-Coast`) to the sitemap. These pages get 100% of AI-chat traffic and 41% of Bing traffic but are currently invisible to sitemap-based discovery. ChatGPT likely went dormant because Bing deprioritised the page without freshness signals. This is the single highest-impact GEO fix.

## [WTA-010] Push robots.txt with explicit AI crawler allows — raised 2026-07-29 — [GEO] — status: DONE (deployed 2026-07-29, commit fcecf1f)
**Blocks:** AI crawler access verification.
**Needs a human because:** website file change + deploy.
**Proposed:** Add explicit `User-agent: GPTBot / Allow: /` (and OAI-SearchBot, PerplexityBot, ClaudeBot, CCBot, Google-Extended) to robots.txt. Research shows 41% of sites accidentally block AI bots via CDN/WAF overrides that ignore the generic `User-agent: *` rule. Explicit allows bypass this. Critical: `OAI-SearchBot` is what ChatGPT uses for search citations (separate from GPTBot for training).

## [WTA-011] Verify Bing Webmaster Tools + re-submit sitemap — raised 2026-07-29 — [GEO] — status: DONE (2026-07-29)
**Done:** Site verified in Bing (IsVerified=true). Submitted the 7 Gold-Coast market-metrics URLs via Bing Webmaster API (SubmitUrlbatch OK). Sitemap auto-submit method 404'd but sitemap is in robots.txt → Bing crawls it. Account 188439555 / G120Q45Z on file.
**Blocks:** Bing→Copilot→ChatGPT indexation pipeline health.
**Needs a human because:** Bing Webmaster account access.
**Proposed:** Log into Bing Webmaster, verify sitemap submission, check crawl errors on market-metrics pages, re-submit after WTA-009 lands. Bing powers both Copilot and ChatGPT search — if Bing doesn't have our latest pages, AI engines can't cite us.

## [WTA-012] Approve quotable stat blocks + AYH bridge on market-metrics pages — raised 2026-07-29 — [GEO] — status: OPEN
**Blocks:** AI citation quality + conversion from AI traffic.
**Needs a human because:** content change on public pages.
**STATUS: DONE — approved + shipped 2026-07-29 (commit ef97323+d21ea92, verified live).** Per-suburb market-metrics pages now render question→stat→source Q&A + FAQPage JSON-LD + AYH bridge, bound to SSR data (zero latency). ⚠ Gold-Coast city-wide page → WTA-013 (needs aggregate median wired).
**Proposed:** (a) Add "At a Glance" stat blocks with question-shaped H2s (e.g. "What is the median house price in Robina?") — 30-40% higher AI visibility per Princeton GEO study. (b) Add soft contextual link from market-metrics → AYH ("See how your home compares"). Both Bing conversions came through the market-data → AYH funnel; AI-chat users don't take that step because there's no visible bridge. Spec in `cycles/geo_cycle_20260729_1345.md` §3 ACTION 4-5.
**Strengthened by Cycle #2 research:** tables extract at 2.1× inline stats; front-loaded answers capture 55% of citations; question-shaped H2s = 34% more likely to be cited. All support the spec.

## [WTA-013] Check Bing AI Performance report in Webmaster UI — raised 2026-07-30 — [GEO] — status: OPEN
**Blocks:** Understanding Copilot citation volume + which queries trigger citations.
**Needs a human because:** The AI Performance report is UI-only in Bing Webmaster Tools (API endpoints returned 404). Account is verified (ID 188439555).
**Proposed:** Log into Bing Webmaster Tools → look for "AI Performance" or "Copilot" tab. This report (launched Feb 2026) shows: which pages Copilot cites us in, the "Grounding Queries" (Copilot's internal search phrases), citation count over 90 days, and trends. This is the ONLY first-party Copilot citation data — PostHog only shows us clicks, not citations. A page can be cited 100× in Copilot answers and we'd only know if someone clicks through.
**What we'd learn:** Whether Copilot citations are growing, stable, or declining; which queries trigger citations; whether the sitemap/robots.txt changes had any effect on citation frequency.

## [WTA-016] Server-render article bodies as semantic HTML — raised 2026-07-30 — [GEO] — status: OPEN
**Blocks:** AI citation of our largest + freshest content surface (sold-story / median articles, ~86% of SEO surface, ~19 new/day).
**The finding (measured live this cycle):** article pages server-render only the title + meta — the body (exact prices, median comparisons, prose) is fetched client-side after hydration and is ABSENT from the initial HTML. On a fresh article the SSR had 0 `<p>`, 0 `<h2>`, 0 of 7 body-prose probe words, and no Article/NewsArticle schema — vs the market-metrics overview page which is fully SSR'd (76 KB, 67 `<p>`, 5 `<h2>`, stat schema). Non-JS AI fetchers (the real-time fetchers ChatGPT/Perplexity use, plus much GPTBot/ClaudeBot traffic) see a near-empty page. The pages that ARE fully SSR'd (market-metrics) are precisely the ones earning Bing clicks + the growing Copilot signal; the articles earn almost none despite volume + freshness.
**Needs a human because:** it's a RENDER-PATH change on a perf-sensitive site (must not regress TTFB/LCP) → Tier-3, your call. Body copy already exists + already passes editorial rules (it's the published article) — this is a rendering change, not new copy.
**Proposed:** move the article body into the server loader on `routes/articles.$slug` (mirror the market-metrics SSR path) so `<h1>/<h2>/<p>`/tables + the quotable lede are in the initial document; add `Article`/`NewsArticle` JSON-LD. Full spec: `16_General_Reinforcement_Learning/WTA-016_DRAFT_article_ssr.md`. Fully reversible, one commit.

## [WTA-017] Put the personalization slot where the traffic is (property page) + stamp real address submits — raised 2026-07-30 — [onsite] — status: OPEN
**Blocks:** Testing the browse→address-search bridge (the 29× lever) on the surface that actually gets owner-lookup traffic. Our two test surfaces (`/analyse-your-home`, `/for-sale-v3`) are low-traffic; ~94% of organic owner-lookup sessions land on `/property/:id` + market-metrics, which have NO `PersonalizationSlot` — so we can't test the bridge where the visitors are. This is the ceiling on the whole onsite experiment program, separate from the kill-switch.
**Needs a human because:** website deploy on a perf-sensitive page (Tier-3, your call). Inert until `genrl_personalization_v1` ON; renders after paint; no SSR/LCP impact; one commit, revertible.
**Proposed:** (1) mount `<PersonalizationSlot surface="/property" />` in the main render path of `PropertyPage.tsx` + add `/property` to `SURFACES`; the cycle then stages a "compare your own home" comparable-**range** bridge experiment targeting `searched_address`. (2) Stamp `capture_source`/`is_prewarm` on every REAL address submit so the WTA-015 mail loop is measurable (conductor SECONDARY directive) — measurement only, NOT dispatch and NOT email/phone gating. Full spec: `16_General_Reinforcement_Learning/WTA-017_DRAFT_property_slot_and_submit_stamp.md`.

## [WTA-014] Onsite personalization go-live — raised 2026-07-29 — [onsite] — status: IN-FLIGHT (auto)
**Resolved (Will: yes, flip on after cycle proposes 1st experiment + LCP recheck):** watcher `personalization_golive_watch.sh` running — flips `genrl_personalization_v1` ON + Telegrams you once the onsite cycle serves its first experiment. Instant off: `enable_personalization.py --disable`.

## [WTA-005] Offsite mechanism — status: RESOLVED (Telegram-only for now)
**Will:** Claude Telegrams the offsite actions needed; Will does them manually; automate later. Already the model (onsite cycle surfaces hot individuals + drafts outbound as Tier-3 → Telegram).

## [FB-organic] Public posting gate — status: DONE
**Will:** gate behind Telegram yes/no. `fb_approval.py` LIVE (propose→Telegram→YES/NO reply→publish/skip; poll */3). Reply `YES <token>` / `NO <token>` on @WillFieldsBot. FB-organic proposer can now be revived safely (nothing posts without your yes).

## [WTA-ART-001] Publish Tier-1 valuation-methodology articles — raised 2026-07-30 — [articles] — status: OPEN
**Blocks:** First article conversion test.
**Needs a human because:** publishing new public content.
**Proposed:** Write + publish 1-2 articles targeting "what is my house worth [suburb]" / "free property valuation gold coast". These queries are closest to the `searched_address` milestone (26× lift). Article presents our comparable-sales methodology (ranges, not single figures), shows example suburb data, bridges DIRECTLY to /analyse-your-home. Angle we own: we publish methodology + confidence intervals; competitors give black-box estimates. Editorial-compliant (data only, no advice). ~$0 marginal cost. Draft will be written and routed through standard editorial pipeline for review.

## [WTA-ART-002] Redirect draft pipeline toward Tier 1-2 topics — raised 2026-07-30 — [articles] — status: OPEN
**Blocks:** Automated article topic quality.
**Needs a human because:** changes what the GH Actions article generator produces.
**Proposed:** The `how-it-sold` topic (14 articles, 0 sessions, 0 readers) and `watch-this-sale` (7 articles, 0 readers) should be deprioritised or retired. The automation pipeline should focus on: (a) suburb market pillar content ("Robina Property Market 2026"), (b) valuation methodology explainers, (c) infrastructure/development updates. These topics have proven engagement (major-projects = 9/9 sessions) or high conversion proximity (valuation → AYH → address search → 26× lift).

## [WTA-ART-003] Fix non-SEO slugs on published articles — raised 2026-07-30 — [articles] — status: OPEN
**Blocks:** Article SEO discoverability.
**Needs a human because:** website code change (slug migration + 301 redirects).
**Proposed:** Many published articles have MongoDB ObjectID slugs (e.g. `/articles/699d7222a47edd0001e077e1`). These will never rank. Migrate to human-readable slugs (e.g. `/articles/gold-coast-athletes-village-new-suburb`) with 301 redirects from old paths. Scope: 53 published articles, ~25 have ObjectID slugs.

## [WTA-ADS-001] Pause AYH seller campaign — raised 2026-07-29 — [ads] — status: OPEN
**Blocks:** Wasted spend on a dead seller campaign.
**Needs a human because:** spend change.
**Current:** $203 spent, 1 lead in 90 days, CPL $203. Channel dead since April 10 (no AYH submissions). Burning ~$2.30/day.
**Proposed:** Pause "Leads: Analyse Your Home — Before an Agent v1" entirely. This is the worst-performing campaign in the account by a factor of 40× vs the $5 target.
**Kill rule:** Already met — $203 / 0 identified sellers.

## [WTA-ADS-002] Investigate Before You List delivery ($0 spent) — raised 2026-07-29 — [ads] — status: OPEN
**Blocks:** Seller-book physical-mail funnel test stalled.
**Needs a human because:** requires Ads Manager check.
**Current:** Campaign "Before You List — Seller Book (3-arm test)" shows ACTIVE with 3 ads but $0 spend, 0 impressions. This was launched 2026-07-28 at $75/day ($5/day × 3 arms × 5 interest targets).
**Proposed:** Check Ads Manager for: (a) ad-set or ad level paused/rejected, (b) audience too narrow (5km radius, 35-65, advantage_audience off), (c) billing issue, (d) creative review stuck.
**This is the highest-intent seller capture mechanism** — physical address in lead form = Will can mail the appraisal book.

## [WTA-ADS-003] Deploy AN2 + AN14 to GC served funnel — raised 2026-07-29 — [ads] — status: OPEN
**Blocks:** First real GC seller lead from paid ads.
**Needs a human because:** GC go-live (Will controls all GC ad activation).
**Current:** GC funnel (`120251770885910134`) PAUSED. 8 ads built with GC-specific forms (report delivery + Will calls). OOM test has validated AN2_missmillion_light ($7.96 CPL, 2 leads, both Yes intent) and AN14_7daywindow_dark ($6.42 CPL, 1 lead, Yes intent) as the 2 best converting seller creatives.
**Proposed:** Activate AN2_missmillion_light + AN14_7daywindow_dark in the GC served funnel at $15/day each = $30/day. These 2 ads have the strongest proven mechanics.
**Expected CPL:** $15-25 in GC (smaller, more competitive audience).
**Kill rule:** pause if $50 spent with 0 leads (per ad).
**Scale rule:** if CPL < $10 at 5+ leads, increase to $30/day.
**This is the single fastest path to a real identified seller from paid ads.**

## [WTA-SEO-001] Property page title differentiation for address queries — raised 2026-07-29 — [SEO] — status: OPEN
**Blocks:** CTR lift on the highest-conversion organic pages (address searches = 26× conversion lift).
**Needs a human because:** title tag change = public copy.
**Current:** Property page titles use "ADDRESS, Suburb, QLD PostCode | Fields Estate" — identical structure to Domain/REA. 10+ pages at positions 5-8 earn 0% CTR because searchers have no reason to click Fields over a recognized portal.
**Proposed:** For pages with published editorial, change title to: `ADDRESS, Suburb — Sale History & Value Analysis | Fields`. This differentiates from listing portals by signaling unique analysis content. Expected: +2-3% CTR on ~400 impressions = 8-12 additional clicks/month of the most convertible traffic.
**File:** Property page route loader (SSR title generation).

## [WTA-SEO-002] Robina market-metrics title sharpening — raised 2026-07-29 — [SEO] — status: OPEN
**Blocks:** Position improvement for #1 impression page.
**Needs a human because:** title/meta tag change = public copy.
**Current title:** "Robina Property Market Overview (2026): Prices, Trends & Data | Fields Estate"
**Proposed title:** "Robina Property Market (2026): Prices, Growth & Market Data | Fields Estate"
**Change:** "Trends" → "Growth" (matches "robina property growth" query, 79 impressions at pos 9.2); remove "Overview" (saves space, adds nothing).
**Current meta:** ends "...with local analysis. 2026."
**Proposed meta:** "Robina property market data — median house price, price growth, days on market, sales volume, supply, and demand drivers. Updated weekly with local Gold Coast analysis."
**File:** `src/config/marketMetricsSeo.ts`

## [WTA-SEO-003] Fix stale date in Burleigh Waters crash-risk meta — raised 2026-07-29 — [SEO] — status: OPEN
**Blocks:** Trust signal in SERPs.
**Needs a human because:** meta description change = public copy.
**Current meta:** "...Updated March 2026."
**Proposed meta:** "...Updated July 2026." (or better: auto-populate from build/data date).
**File:** `src/config/marketMetricsSeo.ts`

## [WTA-SEO-004] Normalize 114 Florabella Drive ALL-CAPS address — raised 2026-07-29 — [SEO] — status: OPEN
**Blocks:** CTR — ALL CAPS title looks spammy in SERPs.
**Needs a human because:** data change that affects title tag (public copy).
**Current:** `<title>114 FLORABELLA DRIVE, Robina, QLD 4226 | Fields Estate</title>`
**Proposed:** Update MongoDB `address` field from "114 FLORABELLA DRIVE, Robina, QLD 4226" to "114 Florabella Drive, Robina, QLD 4226".
**Risk:** Very low — pure data normalization, correct format.

## [WTA-015] The posted-report dispatch loop has never fired once — raised 2026-07-29 — [meta/onsite] — status: OPEN
**Blocks:** The ENTIRE strategy (address → posted report → rapport → inbound call). This is the conductor's named binding constraint for cycle 2.
**The finding:** Across 62 `system_monitor.property_reports`, every `print_appraisal` block shows `queued_at=null`, `dispatched_at=null`, `delivered_at=null`. Not one printed appraisal has ever been queued, dispatched, or delivered in the system's record. The `print_appraisal` fields are a data placeholder — there is no dispatcher script and no cron that populates them. Ultimate reward is stuck at 1 booked call (7 Huntingdale Crescent, booked 2026-06-10, still status `new` 7 weeks on) + 1 contactable lead. Meanwhile FB spend = $1,172 for 0 true-reward conversions.
**Needs a human because:** the dispatch stage is a PHYSICAL mechanism (print + post) that I can't execute, and only you know whether you're already posting reports manually (memory says you started printing packages for no-phone off-market leads ~2026-07-27) — if so, it's happening OFF the record so we can never learn whether the loop converts.
**Two questions for you:**
  1. Are you currently printing + posting these reports? To which addresses (the real address-submits, or the off-market flyer list)?
  2. Can we record each dispatch (even a one-tap "posted" toggle on the ops dashboard, or wiring PostGrid/Pronto Direct)? Until dispatch is recorded, the address→call loop is unmeasurable and the RL system is optimising a funnel whose final stage is invisible.
**Proposed:** (a) short-term — a lightweight "mark as posted" action that stamps `print_appraisal.dispatched_at` on the real submits you post, so we start a measurable cohort; (b) medium-term — decide manual-post vs PostGrid/Pronto API. Also: given $1,172 FB spend → 0 true reward while the real constraint is downstream, hold ad-spend increases until dispatch is measurable (ads wants to scale Carousel Lead v1 — recommend pause on scale-up).

**Cycle-3 correction (2026-07-30, conductor):** fresh data sharpens this. Dispatch is a real gap but it is a *secondary* bottleneck, not the top one — it's starved of input. Truth on captures: the "7 near-term reward addresses" the board counted were **test data** (all `offmarket_direct_test_v1`, submitted in one morning 2026-07-21, `distinct_id=null` — your own tests). **Genuinely public address captures in 60d = just 4, every one from paid FB, ZERO from organic.** Meanwhile 426 organic owner-lookup sessions produced **0** address submits (only 10 even searched). So the true *binding* constraint is one stage earlier: converting organic owner-lookup traffic into an address submit at all — which onsite is already working (browse→address-search bridge; it just fixed the experiment plumbing that stopped any capture test from firing). This WTA-015 (dispatch/measurement) still stands and still needs your answer on the two questions above — but even a perfect dispatch loop has ~4 real addresses to mail today, so onsite's organic-capture fix is the higher-leverage front. Dispatch matters most *after* capture volume rises.

## [WTA-ADS-004] BYL: kill dead-mechanic arms + fix CTA — raised 2026-07-30 — [ads] — status: OPEN
**Blocks:** The one live GC seller test is spending with 0 conversions.
**Needs a human because:** spend + creative change (all ad spend is Will's call).
**Current:** BYL Seller-Book 3-arm live, $146 lifetime / 2,570 imp / **0 leads**. Ad A (Loss→Proof) = multi-$ two-home puzzle (the AN3 junk-lead pattern); Ad C (Control) = no-$ narrative — both replicate confirmed-dead OOM mechanics. Only Ad B (Trust: single $2,120,000→$1,742,000 tool-miss) carries the proven single-$-gap Knowledge-Gap DNA (4/4 Yes intent OOM).
**Proposed:** (1) Pause Ad A + Ad C; concentrate the full $75/day on Ad B. (2) Rewrite Ad B CTA from "we'll post you a free guide" → self-number open loop ("see what a home like yours is really worth — comparable sales say $X–$Y", range only, Rule 5). The current CTA never opens the self-relevant loop the form should close, and the hardcover-mail ask adds friction.
**Kill rule:** Ad B at $60 spend / 0 leads → physical-book ask too high-friction; pivot BYL to a number-reveal form.
**Scale rule:** Ad B CPL < $15 at 3+ name+email+phone leads → raise to $50/day; becomes the GC seller creative.

## [WTA-ADS-005] Seed the GC rebuild with AN2 star DNA — raised 2026-07-30 — [ads] — status: OPEN (supersedes WTA-ADS-003)
**Blocks:** GC lab rebuild risks re-discovering DNA already proven.
**Needs a human because:** GC go-live (Will controls all GC activation + owns the rebuild).
**Current:** OOM loop paused today for a Southern-GC rebuild. WTA-ADS-003 (deploy AN2+AN14 to old GC funnel) folds into this.
**Proposed:** Make AN2 the seed creative — single $1,000,000→$2,500,000 "a home like yours" gap (comparable range), number-reveal lead form (not a book), light background. Only creative with 2× Yes intent at ~$14–16 CPL across the whole OOM run. Pair with WTA-ADS-004's CTA lesson.
**Kill rule:** any GC arm $50 / 0 leads. **Scale rule:** any arm < $10 CPL at 5+ leads.
**Carry-forward DNA (do not re-test):** one dominant clean $ number + "a home like yours" + comparable-sales reveal = Knowledge Gap. Dead: multi-$ puzzle, no-$ narrative, reno-return, time-decay, identity-threat, abstract agent-spread. Dark ~3× light except data-table format (light wins).

## [WTA-ADS-006] Ad take-stock + relaunch plan (your 07-30 request) — raised 2026-07-30 — [ads/meta] — status: OPEN
**You asked** (Telegram, ads switched off): take stock of 2wks, what works/not, ensure Brain 2 updated, plan next cycle = 1 proven funnel + a handful of targeted data ads.
**Done:** full plan → `03_Facebook/Home_Owner_Lead_Funnel_Search/NEXT_CYCLE_AD_PLAN_2026-07-30.md`. Brain 2 attribution/lead layers confirmed current (rebuilt today); only stale layer = AI session summaries (07-16, not cronned) — follow-up.
**Headline:** 2wks = ~$1,743 / 107 ads → **21 contactable FB-form leads** ($4–30 each) but **0 inbound enquiries**, and only 6/21 leads were ever contacted. The ad funnel WORKS; the leak is downstream (un-worked leads + no dispatch record). The 107-ad AN## matrix was the waste; winning DNA = single clean $-gap + "a home like yours" + comparable range (AN2/AN3/Carousel-C).
**Plan:** 1 proven funnel (FB Instant Form, number-reveal, name+email+phone+intent, AN2 DNA, no book) + 4 well-budgeted arms (AN2 seed / Ad-B CTA fix / Carousel-C buyer / "posted report→mailable address" to feed WTA-015). Replaces 107 starved arms with 4 arms @ ~$15-20/day each.
**Needs a human because:** spend + go-live are yours.
**Decisions needed:** (1) approve ~$60-80/day (~$400-550/wk) 4-arm relaunch, or set a cap; (2) WTA-015 lead-follow-up answer (are you calling/posting these leads? can we record it?); (3) any arm cuts/adds. **Do first, $0 cost:** work the ~15 uncontacted leads incl. the "yes"-intent seller.

## [WTA-SEO-005] Property `<title>` = editorial value hook (hybrid) — raised 2026-07-30 — [seo] — status: OPEN
**Implements open conductor directive `6a69ca8ea8d4716b374fbf11`.** This is the #1 organic-SEO lever for our highest-converting page type (address searches → `searched_address` = 29× conversion lift, `submitted_address` = 35×).

**The finding:** 12 property pages rank page-1 (pos 5–8) for their exact-address queries but earn ~0% CTR. The SERP is dominated by Domain/REA; our `<title>` is *structurally identical* to theirs (`{address} | Fields Estate`) with **no value signal**, so a searcher has no reason to click Fields at a lower rank. Meanwhile the editorial pipeline already writes a compelling hook (`ai_analysis.meta_title`, e.g. `23 Camberwell Cct — $191K Below Valuation. Why? | Fields`) — but today it feeds **only** the social `og:title`, NOT the SEO `<title>`. The value hook is being wasted on the one slot that drives organic clicks.

**Blast radius:** 115 of 119 published property pages get the new title (4 whose meta_title lacks the ` — ` hook shape safely fall back to generic). Unpublished + sold-without-editorial pages keep the generic title.

**Rule-5 check (passed):** the hooks are all **gaps/ranges** ("$335K Below Comps", "$3.2M Ask vs $2.4M Comps", "Comps Say $1.7M–$2M") — never a single-figure "this home is worth $X". They are already published live as `og:title`/`meta_description` (already passed the editorial compliance gate); this change only *routes the same approved copy into the `<title>` slot* — no new copy is authored. Property pages already show the valuation methodology + confidence disclaimer required for on-page $ claims.

**Needs a human because:** the `<title>` is public SEO copy shown on every property SERP result (Tier-3). One approval → I deploy through the gate (`npm run build` must pass, ONE batched Netlify commit, deploy-tracker log), then request Bing+IndexNow reindex of the changed pages and watch CTR/position over the following 1–2 weeks.

**Before / After (example — 23 Camberwell Circuit):**
```
BEFORE  <title>23 Camberwell Circuit, Robina, QLD 4226 | Fields Estate</title>
AFTER   <title>23 Camberwell Circuit — $191K Below Valuation. Why? | Fields</title>
```
Keeps the **full, un-abbreviated street** for exact-address match; grafts on the published value hook; length-aware (≤62 chars, else uses the editorial's own already-tuned meta_title, else generic).

**Exact change (3 files, identical logic client+server so the title never flips on hydration):**

1. NEW FILE `src/lib/propertyTitle.ts`:
```ts
/**
 * SEO <title> for a property page: hybrid of exact-match street address + the
 * published editorial value hook, e.g.
 *   "23 Camberwell Circuit — $191K Below Valuation. Why? | Fields"
 * Falls back to generic "{address} | Fields Estate" when unpublished, when the
 * meta_title isn't in the "{street} — {hook} | Fields" shape, or when the hybrid
 * would blow the ~60-char SERP budget (then the editorial's own abbreviated
 * meta_title if it fits, else generic). Used by BOTH the SSR route meta() and the
 * client document.title effect so server and first client render match.
 */
export function buildPropertySeoTitle(address: string, aiMetaTitle?: string): string {
  const generic = `${address} | Fields Estate`;
  const mt = (aiMetaTitle || "").trim();
  if (!mt) return generic;
  const sep = mt.indexOf(" — ");
  if (sep === -1) return generic;
  const hook = mt.slice(sep + 3).replace(/\s*\|\s*Fields.*$/i, "").trim();
  if (!hook) return generic;
  const street = address.split(",")[0].trim();
  if (!street) return generic;
  const hybrid = `${street} — ${hook} | Fields`;
  if (hybrid.length <= 62) return hybrid;
  const abbreviated = /\|\s*Fields/i.test(mt) ? mt : `${mt} | Fields`;
  return abbreviated.length <= 65 ? abbreviated : generic;
}
```

2. `src/routes/property.$id.tsx` — add import at top and replace the seoTitle line (currently line 156):
```ts
// add near the other imports:
import { buildPropertySeoTitle } from "../lib/propertyTitle";

// replace:
//   const seoTitle = `${p.address} | Fields Estate`;
// with:
const seoTitle = buildPropertySeoTitle(p.address, p.ai_meta_title);
// (socialTitle / og:title line UNCHANGED — social keeps the full editorial hook)
```

3. `src/pages/PropertyPage/PropertyPage.tsx` — add import and replace the seoTitle line (currently line 319):
```ts
// add near the other imports:
import { buildPropertySeoTitle } from "../../lib/propertyTitle";

// replace:
//   const seoTitle = `${addr} | Fields Estate`;
// with:
const seoTitle = buildPropertySeoTitle(addr, ai?.meta_title);
// document.title = seoTitle;  ← unchanged; socialTitle line unchanged
```

**Expected impact:** address-query pages sit at pos 5–8 with ~0% CTR today. A value-hook title gives the click reason the generic title lacks. Even +2–3pp CTR across ~250 striking impr = several extra clicks/month of the 29×/35× address-search traffic — the single highest-converting organic path — and it applies to 115 published pages, compounding as more editorial publishes nightly.

**Kill/rollback:** pure title-string change, instantly reversible by reverting the 3 files; fallback-to-generic keeps every edge case safe.

---

## [WTA-OPS-001] 3 suburbs health-checked but never scraped since 2026-05-10 — raised 2026-08-05 — [ops] — status: OPEN
**Blocks:** 3 of the 14 ERROR rows on Pipeline Processes ("Coverage vs Domain": Burleigh Heads + Carrara at
54.9 failing-days, Merrimac at 27.4). They are the two longest-running red rows on the whole board and they
can never go green on their own.

**Symptom (proven, not guessed):** `system_monitor.scraper_health`, latest batch `2026-08-04 14:33:51.871`,
9 docs — 6 `healthy`, 3 `critical`:
```
burleigh_heads  critical  total=113  last_scraped=2026-05-10 21:11:22  staleness_hours=2057.4
carrara         critical  total=56   last_scraped=2026-05-10 21:14:25  staleness_hours=2057.3
merrimac        critical  total=11   last_scraped=2026-05-10 22:04:51  staleness_hours=2056.5
```
Meanwhile step 109's own `logs/coverage_check.log` reports `TOTAL: 6 suburbs checked, 0 gap(s) found` on every
run including 2026-08-05 00:27 — because it checks a *different*, 6-suburb list that excludes all three.

**Root cause (proven):** two suburb lists have silently diverged.
- `config/settings.yaml:64-72` — the scrape list, **6** suburbs. `Merrimac` and `Carrara` are commented out;
  `Burleigh Heads` is absent entirely.
- `shared/db.py:36-40` — `TARGET_SUBURBS`, **9** suburbs, still includes all three.
`write-scraper-health.py:42` iterates `TARGET_SUBURBS`, so it writes a health doc nightly for 3 suburbs the
pipeline no longer scrapes. Its status is derived purely from `age_hours` of the newest `last_updated`
(`write-scraper-health.py:64-80`): >50h ⇒ `critical`. Frozen `last_scraped_at` ⇒ permanently critical, forever.
The 2026-05-10 freeze date matches `settings.yaml:17` — `run_other_suburbs_weekly: false  # DISABLED
2026-05-13 … Akamai rate-limit`. 2026-05-10 was the last Sunday all-suburbs run before that switch.

**Second, larger problem underneath the noise:** those 3 collections still hold **180 documents at
`listing_status: "for_sale"`** (113 / 56 / 11) last verified 87 days ago. Because the suburbs are out of the
scrape set they are also out of sold-detection (103/111), withdrawn-detection (113/114) and re-pricing. They
will sit as "for sale" indefinitely. Exposure is bounded but not zero: `/for-sale` only queries
`TARGET_MARKET_SUBURBS = ['robina','varsity_lakes','burleigh_waters']` (`netlify/functions/config.mjs:7`), so
they are NOT on the listings page — but `KNOWN_SUBURBS` (same file, line 10) covers all 9, so individual
`/property/:id` routes can still resolve them. **I did not verify whether they appear in the sitemap** — that
is the one open question here and it decides whether this is cosmetic or a public-facing accuracy problem.

**Needs a human because:** it is a scope decision only you can make (were these 3 suburbs retired on purpose in
May, or did they fall out as collateral of the Akamai fix?), and both candidate fixes touch monitoring code or
production data, which I am not permitted to change.

**Proposed (pick one):**
- **(a) They are retired on purpose — the likely case.** Add the 3 to a paused/known-gap registry so the board
  stops alarming, exactly as `_PAUSED_JOBS` did on 2026-08-05: in `write-scraper-health.py`, iterate the
  `settings.yaml` scrape list instead of `shared/db.py:TARGET_SUBURBS` (one-line source change, makes the two
  lists structurally impossible to diverge again). Then decide the 180 listings: mark them
  `listing_status: "unverified"` or similar so nothing downstream reads them as live. Reversible — the docs are
  untouched apart from one field, and the suburb list is one line.
- **(b) They should be scraped.** Re-add to `settings.yaml:target_market.suburbs`. Costs 3 more suburbs of
  Domain fetch per night, against the Akamai budget that caused the May 13 disable in the first place — that
  trade-off is yours, not mine.
**Blast radius:** (a) board-only + 180 internal docs; (b) nightly scrape load + Akamai risk. Both reversible.

## [WTA-OPS-002] Step 121 (SEO Sitemap Resubmit) can never run — raised 2026-08-05 — [ops] — status: OPEN
**Blocks:** Pipeline Processes row "Schedule membership" — ERROR: *"121 (SEO Sitemap Resubmit (Nightly))
defined and ordered but in NO schedule set, so it can never run on any day and is skipped as 'not scheduled
for today'"*.

**Root cause (proven):** step 121 is in `config/process_commands.yaml:528` `execution_order`, and the YAML
comment block at lines 523-525 lists it in both the Mon-Sat and Sunday sets — but the YAML comment is not the
schedule. The real schedule is the three sets in `src/schedule_manager.py`
(`target_market_processes` / `other_suburbs_processes` / `always_run_processes`), and
`grep -n "121" src/schedule_manager.py` returns **nothing**. `get_processes_to_run()` (line ~118) builds the
run list purely from those three sets, so 121 is never included and is skipped nightly as "not scheduled".
Same class as the `[[orchestrator_process_register]]` note: *the schedule lives in `schedule_manager.py` sets,
not YAML*.

**Impact:** the nightly sitemap resubmit to Google has never fired from the pipeline. There is a separate
06:15 `regenerate-sitemap.sh` cron, so sitemaps are still being generated and pushed — what is missing is the
step-121 *resubmit*. I have not measured the indexation cost of that gap.

**Needs a human because:** it is a pipeline schedule change. Adding a step to a nightly run is not on my Tier 1
list and its cost (Google Indexing API quota, 200/day, shared with submit-new) needs your call.

**Proposed:** add `121` to `always_run_processes` in `src/schedule_manager.py` (it already sits after 18/117 in
`execution_order`, so ordering needs no change), then restart `fields-orchestrator`. One-line, trivially
reversible. Alternative if the 06:15 cron already covers it: delete 121 from `execution_order` so the board
stops reporting an orphan. Either resolves the row honestly; leaving it is the only wrong answer.

## [WTA-OPS-003] Anthropic metered API out of credit — alarmed 18 days, probably obsolete — raised 2026-08-05 — [ops] — status: OPEN
**Blocks:** Pipeline Processes row "Vision provider / Anthropic (primary)" — ERROR since 2026-07-17 (18.4 days).

**Symptom + root cause (proven by live probe, run this cycle):** the board's detail text reads
`ANTHROPIC_API_KEY not set`, which is the `SKIP` branch of `api_health_monitor.probe_anthropic`
(`scripts/api_health_monitor.py:82-84`) — i.e. the process that generated that row had no `.env` loaded. That
text is **misleading**. I sourced `.env` and ran the probe directly:
```
key present in env: True  len 108
probe: ('OUT_OF_CREDIT', 'credit balance too low — top up', '')
```
So the key is present and valid; the account has no credit. Consistent with `[[opus5_access_and_api_credits]]`.

**Why it is probably a false alarm:** the code comment at `main_site_health_check.py:1910` claims *"Claude is
the primary engine for steps 105/106/108/112/117"*. That is out of date. Every one of those steps now routes
around the metered API: 108, 112 and 117 all `export ANTHROPIC_BACKEND=openrouter`, and 120 uses
`USE_CLAUDE_MAX=1`. Vision goes to Gemini-via-Vertex. So no pipeline step consumes this key.
**Explicitly not proven:** I did not exhaustively verify every non-pipeline cron script — no cron sets
`ANTHROPIC_BACKEND` at all, so any script calling `make_client` without it would fall through to the raw key.
To prove it either way I would need to grep every cron target for `make_client`/`anthropic.Anthropic` and
confirm each sets a backend; that is a bigger sweep than this cycle had room for.

**Needs a human because:** the fix is either spending money (top up) or editing monitoring code (re-point the
probe / mark it info-only), and monitoring code is read-only to me by design.

**Proposed:** confirm nothing still uses the metered key, then in `main_site_health_check.py:1910-1918` demote
the Anthropic row to `info=True` with detail "metered API retired — vision on Gemini/Vertex, text on Claude
Max/OpenRouter", and update the stale comment. If something *does* still use it, top up instead and the row
goes green on its own. Board-only change, one block, instantly reversible.

## [WTA-OPS-004] Timeline-refresh row is judged by a superseded log while its heartbeat says success — raised 2026-08-05 — [ops] — status: OPEN
**Blocks:** Process Registry row "Property timeline refresh (weekly)" — ERROR 2.4 days.

**Symptom:** the row reports *"'Traceback (most recent call last)' found in last run's log tail"*.

**Root cause (proven):** the underlying bug is **already fixed** and the row is red on stale evidence.
- The traceback in `logs/refresh-timelines.log` is `pymongo.errors.CursorNotFound (code 43)` — the cursor held
  open across per-document Bright Data fetches, which Cosmos closes.
- That was fixed on 2026-08-03: `scripts/refresh_property_timelines.py:262` now materialises the cursor first
  (`docs = list(coll.find(...))`) with a comment naming exactly this failure.
- Heartbeat confirms the fix works: `system_monitor.job_runs` → `refresh_property_timelines`,
  `status=success`, `run_at=2026-08-03 05:51`, `detail="408 timelines refreshed across 3 suburbs"`.
- The log's mtime is **2026-08-02 02:21** and has not moved since. The cron is `0 1 * * 0` — Sunday only. The
  last Sunday was 2026-08-02 (pre-fix); the next is 2026-08-09.

**So:** the row will stay red until 2026-08-09 and should then clear by itself. **No action is needed on the
job.** I deliberately did not re-run it to force the log green — it would be manufacturing a green row.

**The actual defect is in the probe, not the job:** this job is watched TWICE — by a log-tail probe
(`main_site_health_check.py:1080`, `("Property timeline refresh (weekly)", …, "refresh-timelines.log", 9)`)
and by a Rule 7 heartbeat. The two disagree right now (log ERROR 2026-08-02 vs heartbeat success 2026-08-03),
and the log-tail probe is the weaker signal: it cannot see a manual run and it re-reports a resolved failure
until enough clean output scrolls it out of the 60-line tail window.

**Needs a human because:** monitoring code is read-only to me.

**Proposed:** delete line 1080 from `_REGISTRY_LOG_JOBS` and let `collect_self_reported_jobs` render the
heartbeat, exactly as `[MONITOR-FITNESS-PROBES]` did for the two Market Pulse rows on 2026-08-05. The heartbeat
already carries the right cadence semantics for a weekly job. One-line deletion; restore the tuple to undo.
**Do not action before 2026-08-09** if you would rather first watch the Sunday cron clear it naturally — that
is also a valid confirmation that the CursorNotFound fix holds under the full weekly load.

## [WTA-OPS-005] 57% of the for-sale book cannot be valued — 223 blocked on floor area alone — raised 2026-08-05 — [ops] — status: OPEN
**Blocks:** Pipeline Processes row "Step 18 outcome / Valuation precompute: cleared valuations" — ERROR.

**Symptom:** the row reads *"303 properties had a published valuation wiped this run"*.

**Root cause (proven) — the row's wording is wrong, but what it points at is worse than it says.**
The probe counts the string `cleared existing valuation`, printed at
`/home/fields/Feilds_Website/07_Valuation_Comps/precompute_valuations.py:3736`. That line fires
**unconditionally whenever `exclusion_reason` is set** — it does not check whether a valuation existed
beforehand. So "wiped this run" is not what happened.

What is actually happening is steady state, and it has been for at least 12 nights:
```
2026-07-24 cleared=290 total=538 success=244
2026-07-29 cleared=299 total=530 success=227
2026-08-04 cleared=303 total=540 success=233   <- the run that raised the row
```
Confirmed against the DB directly (all 9 `shared/db.py` target suburbs, `listing_status:"for_sale"`):
```
for_sale total: 540
valued OK  : 233   (43%)
excluded   : 307   (57%)  missing_floor_area 223 · misclassified_dwelling 28 ·
                          acreage 23 · insufficient_comparables 17 · missing_land_size 16
no valuation_data at all: 0
```
So no data is being destroyed nightly. Instead **57% of the live for-sale book has never had a valuation**,
and `missing_floor_area` alone accounts for 223 of 540 listings (41% of everything we list). Sampled
excluded doc: `71 EASTHILL DRIVE, Robina` — `property_type: House`, `bedrooms: 3`, no floor-area field at all.
The gap is also **widening, not closing**: `missing_floor_area` went 209 → 223 in 12 days while the
successfully-valued count sat flat at ~232, i.e. essentially every listing added in that window landed
excluded.

**Why this matters more than the row suggests:** the valuation IS the product. Two in five listings we
publish cannot carry the thing we exist to provide, and nothing before today reported it — step 18 exits 0
every night.

**Needs a human because:** the fix is a code/sourcing decision on the valuation pipeline (where floor area
comes from for units and older listings), not a re-run, and its blast radius is the public property pages.

**Proposed (two separable pieces):**
1. *Product* — treat `missing_floor_area` as a data-sourcing backlog, not an exclusion to live with.
   223 listings is a finite, named list. Worth deciding whether floor area can be derived from the
   floor-plan analysis (step 106) or the Domain payload before excluding.
2. *Board wording* — `main_site_health_check.py:1208-1211` should judge this as a **level** ("57% of the
   book is unvaluable"), not an **event** ("wiped this run"), and probably on a delta vs the previous run.
   As written it will read ERROR every night forever regardless of whether anything changed, which is the
   wolf-crying pattern `[HEALTH-BOARD-PAUSED-VS-DEAD]` just finished removing. Monitoring code is read-only
   to me, so I have not touched it. One-block change, trivially reversible.
**I did NOT verify** whether the frontend hides an excluded property's valuation panel gracefully or shows
an empty state — worth one look, but it needs a rendered page, not a DB query.

## [WTA-OPS-006] Photo analysis is silently losing listings to a deleted Azure storage account — raised 2026-08-05 — [ops] — status: OPEN
**Blocks:** Pipeline Processes row "Step 105 outcome / Photo analysis: dead-host image failures" — ERROR.

**Symptom:** *"158 image downloads failed — listings are being written with ZERO photo analyses and marked
processed, so they never retry"* (run `2026-08-04T20-30-16`).

**Root cause (proven, live, this cycle):** the blob host **no longer exists in DNS**. Every one of the 158
failures is the same error:
```
Failed to resolve 'fieldspropertyimages.blob.core.windows.net' ([Errno -2] Name or service not known)
```
Verified independently of the VM's resolver — `dig +short @8.8.8.8 fieldspropertyimages.blob.core.windows.net`
returns **nothing** (NXDOMAIN at Google's public resolver, not a local DNS fault), and a live
`curl` of one of the failed URLs returns `http=000` in 26 ms. The storage account has been deleted or
renamed; this is not a transient outage and no number of re-runs will fix it. That is why I took no Tier 1
action here.

**Scope:** 158 failed downloads across **11 distinct listings**, each of which logged
`Analyzed 0 images in 0.0s` and was then marked processed — so they are permanently photo-blind unless
something re-queues them.

**The part I could not prove — and it is the important part:** why *now*. The nightly counts are
`Jul 30: 15 · Jul 31: 90 · Aug 1: 0 · Aug 2: 0 · Aug 3: 1 · Aug 4: 158`. A dead DNS name does not produce
zeros on Aug 1-2, so most listings are evidently already on a different image host and only a subset still
carry stale `fieldspropertyimages…` URLs in the DB. I do **not** know whether Aug 4's 158 is a one-off batch
of 11 stale-URL listings or the leading edge of a re-processing sweep that will keep re-hitting the dead
host. To answer it I would need to identify what wrote those 11 documents' `image_urls` and when — a bigger
sweep than this cycle had room for.

**Needs a human because:** the fix is a data migration decision (repoint the 11 listings' image URLs to the
live host, then re-queue them through step 105) plus a code change to stop marking a listing processed when
it analysed zero images. Both are outside Tier 1.

**Proposed:**
1. Find every `for_sale` doc whose image URLs still point at `fieldspropertyimages.blob.core.windows.net`
   and repoint them at the current host (`[[gcs_blob_backup]]` / `[[azure_blob_serving]]` describe the
   migration). Reversible — it is a URL rewrite, originals recoverable from the run logs.
2. Harden step 105: a listing that analysed **zero** images must not be marked processed. Right now
   "everything failed" and "nothing to do" are indistinguishable to the pipeline, which is exactly how 11
   listings became permanently photo-blind after one bad night.
