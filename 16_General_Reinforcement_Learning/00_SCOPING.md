# General Reinforcement Learning — Scoping Document

**Author:** Ops agent · **Date:** 2026-07-29 · **Status:** Exploration / scoping (nothing built, nothing committed)
**Concept (Will):** Port the Claude-in-the-loop reinforcement pattern proven on the [Home Owner Lead Funnel](../03_Facebook/Home_Owner_Lead_Funnel_Search/) to the **whole conversion funnel** — discover, through repeated measured cycles, the highest-converting flows across three spheres: **(1) onsite engagement**, **(2) upstream processes** (SEO, ads, articles, landing pages), and **(3) offsite behaviours** (calls, emails, posted materials) — driven predominantly by observed user behaviour + attribution data, with Brains 1/2/3 and web research in support.

---

## TL;DR (read this first)

1. **The pattern is real and worth generalizing.** The Home Owner funnel isn't a bandit in code; it's a *Claude-in-the-loop reinforcement pattern* — a durable cron wakes a headless Claude that reads live state, attributes **why** something worked at the mechanic level, culls losers, launches a fresh batch, documents every cycle, and self-monitors. That anatomy transfers cleanly. **But the naive framing — "one loop optimizing the whole funnel every 1–3 hours" — will fail**, for a specific, measurable reason.

2. **The binding constraint is reward physics, and it is brutal onsite.** The *entire website* produces **~1,600 pageviews/month (~53/day)**, and true conversion events sit in the **low tens per month** (`analyse_home_submit_success` = 10, `forward_cta_clicked` = 16, `address_search` = 70, `offmarket_qualify` < 10 — all last-30-days, measured). You **cannot run a fast bandit on that.** An hourly loop over the onsite action space would be analysing statistical noise. The FB funnel can iterate hourly *because dollars buy impressions on demand*; onsite traffic can't be bought that way.

3. **The three spheres have radically different reward physics — so this is a hierarchy, not a monolith.** Onsite = near-zero-cost trials but reward-starved and slow → narrow arms, weekly verdicts. Upstream = **where dollars and content buy trials fast**, and where 4–5 iteration loops *already run*. Offsite = tiny-N, high-value, human-gated → a contextual bandit with expensive arms and a person in the loop. One cadence cannot serve all three.

4. **Most of the machine already exists — and it is siloed.** ~7 autonomous loops run today (FB wakeup hourly; Samantha lead-intel / ad-lifecycle / weekly-SEO; hot-lead responder; Brain 2/3 nightly), **Brain 2 already builds a nightly attribution spine** (`ad_attribution`, `organic_journey`, `lead_attribution`), and **`system_monitor.lead_worklist` is already a unified outcome ledger.** The genuinely *new*, highest-leverage build is therefore **not another optimizer** — it is the **coordinating layer + a unified reward ledger** that grades every sphere against **one true downstream reward** (inbound enquiry / identified seller), instead of each loop optimizing its own proxy (CPL, CTR, indexation, swipe-depth) that is never validated against the real objective.

5. **Two structural gaps must be closed before a funnel-wide loop can learn anything:**
   - **Identity join is the weakest link.** Website behaviour (`posthog_distinct_id`) and outcome (email/lead) only connect *at form-submit*. **Anonymous browsers and FB-ad leads are stranded** — no behavioural trajectory tied to outcome. Any funnel-wide reward signal inherits this gap.
   - **There is no server-side personalization.** Onsite the site can only vary content *client-side after hydration, via PostHog flags* + separate routes. "Load dynamic personalised copy given prior behaviour + attribution" — the heart of Sphere 1 — **is a build, not a config.**

6. **Recommended shape:** a **tiered-cadence Conductor**, not one fast loop. A cheap **hourly OBSERVE tick** (accumulate + detect anomalies + fire *Will-to-action* alerts, no changes); a **daily DECIDE cycle** (stage one change per sphere where signal supports it); a **weekly VERDICT** (kill/scale with significance). Sequenced **upstream-first** (densest reward, fastest levers, loops already exist), with the unified reward ledger wired first, and onsite-personalization + offsite arms gated behind the two structural fixes. Start by **making existing siloed loops accountable to one reward**, then add new capability.

---

## 1. What we're porting — the source pattern

The Home Owner Lead Funnel ([`03_Facebook/Home_Owner_Lead_Funnel_Search/`](../03_Facebook/Home_Owner_Lead_Funnel_Search/)) is a **Claude-in-the-loop reinforcement pattern**. Its anatomy:

| Element | Source system |
|---|---|
| **Action space** | Ad-copy variant = angle × hook-mechanic × format × background. ~24 angles tested. |
| **Environment** | Meta ad auction, out-of-market audience (SEQ ex-GC, to protect the core). |
| **Reward** | Real name+email+phone+**selling-intent** form-fill (NOT clicks). CPL ≤ $8 winner; ≤ $5 north star. |
| **Policy update** | A **Claude wake-up cycle** — durable OS cron → headless `claude -p` (Claude Max), hourly 08:00–22:00. |
| **Isolation** | Each variant = its own $15/day ad set (shared ad sets let Meta starve variants — the AYH lesson). |
| **Compounding** | Every winner's **WHY** is attributed at the *mechanic* level so the next cycle builds on the mechanic, not the creative. |
| **Self-monitoring** | The cron self-reports as `home_owner_wakeup` (CLAUDE.md Rule 7) — can't die silently. |

Each cycle: read state (`checkpoint.py`) → attribute what converted & **why** → research new concepts (Brains, web, Sabri/Halo) → kill losers → launch a fresh batch → document (`cycles/*.md` + ledger + `ad_decisions` + Telegram).

### The transferable laws it already discovered (these seed every sphere)
> **The one law:** converting hooks require a **PERSONAL OPEN LOOP** the next step closes ("what's MY number?"). Topic-level engagement (anger/interest/awareness) does **not** convert regardless of CTR.

1. **Specific shocking numbers ≫ abstract concepts** (7–10× CTR). Every abstract-label angle died.
2. **Compound formula = narrative + specific $-shock + personal question.** Pure narrative → clicks/0 leads; pure statistic → dies; the *combination* converts.
3. **Fear > aspiration.** Positive urgency is definitively dead; loss-framing wins.
4. **Engagement ≠ conversion.** High-CTR agent-trust angles converted zero — the Goodhart warning made concrete.
5. **Format × context interaction** — narrative→dark, table/utility→light; utility with no curiosity gap dies.

These are not FB-specific. They are *persuasion mechanics* and they seed the onsite/upstream/offsite action spaces so we build on what won rather than re-discovering it.

### The nearer precedent — read it alongside this
[`15_Off-Market/Reinforcement_Learning/00_SCOPING.md`](../15_Off-Market/Reinforcement_Learning/00_SCOPING.md) (2026-07-29) already ported this pattern to *one onsite surface* (the off-market deck). Its conclusions are load-bearing here and generalize to all of Sphere 1: **reward is near-empty, instrumentation is uneven, volume is the scarce resource → narrow arms (2–4), daily-not-hourly, dense shaped rewards, weekly verdicts.** This document is the funnel-wide superset; the off-market loop becomes *one arm under the Conductor*.

---

## 2. The three spheres and their reward physics (the core of the design)

Will's three spheres are correct as a decomposition. The critical insight is that **they obey different reward physics, and physics dictates cadence, breadth, and even whether a learning loop is viable at all.**

| | **Sphere 1 — Onsite** | **Sphere 2 — Upstream** | **Sphere 3 — Offsite** |
|---|---|---|---|
| **Action space** | Which content/card/popup/copy to serve given prior behaviour + attribution | SEO topics, ad copy/targeting, article topic/cadence/hook, landing-page content, organic posts | Which call/email/posted asset to whom, when, with what message |
| **Environment** | Google-organic visitors on our pages | Meta/Google auctions, Google index, FB feed | The person's phone / inbox / letterbox |
| **Reward** | Engagement depth → downstream action | Arrival rate, CPL, indexation, article impressions | Re-engagement, reply, booked call, listing |
| **Trials/period** | **~53 pageviews/day, whole site**; true conversions low-tens/month | **Buyable** — $ or a published article = more trials; GSC impressions in the thousands | **Very few** (a handful of calls/mails), each expensive + human-gated |
| **Marginal cost/trial** | ~$0 (organic) | $ (ads) or content-effort (SEO/articles) | High ($ + Will's time + postage) |
| **Signal speed** | **Slow** — bounded by organic arrival × index coverage | **Fast where paid**, days-lagged for SEO/articles | **Slow + lumpy** |
| **Right breadth** | **Narrow (2–4 arms)** — trials are scarce | **Wide** where paid (the FB funnel already goes wide) | **Very narrow** — human-gated |
| **Right cadence** | Weekly decisions, daily observe | Hourly–daily where paid; weekly for SEO/articles | Weekly / event-triggered |
| **Loop viable today?** | Only with dense *shaped* rewards + the two structural fixes | **Yes — several already run** | Only as human-in-loop w/ Will-to-action |

**Consequence:** the ambitious "personalise every page in real time" vision (Sphere 1) is the *reward-poorest* corner of the system and the one requiring the most new build. **Sphere 2 is where fast RL actually pays and where the machinery already exists.** The honest sequencing is upstream-first, not onsite-first — and the thing that makes the whole thing more than the sum of the existing loops is the **unified reward ledger** that lets an upstream decision be graded by real downstream (onsite + offsite) conversion.

---

## 3. Current state — the evidence

### 3.1 Reward density (PostHog project 348370, last 30 days, measured 2026-07-29)

**Whole-site event volume — the numbers that gate everything:**

| Event | 30-day count | Role |
|---|---|---|
| `$pageview` (whole site) | **1,601** | total trials available, all surfaces, all month (~53/day) |
| `$autocapture` / `time_on_page` / `scroll_depth` | 858 / 1,376 / 613 | dense behavioural (shaped-reward candidates) |
| `property_view` | 361 | mid-funnel intent |
| `address_search` | 70 | mid-funnel intent |
| `forward_cta_clicked` | 16 | soft conversion |
| `analyse_home_address_submit` | 14 | conversion |
| `analyse_home_submit_success` | 10 | **true reward** |
| `offmarket_qualify` | < 10 (in "Other") | **true reward** |

**Pageviews by surface (30d):** `/for-sale-v3` 299 · `/analyse-your-home` 288 · `/market-intelligence/Robina` 82 · `/for-sale-v4b` 43 · `/` 40 · individual articles 8–25 each · **~473 in the long tail** of unique per-address `/property/*` and `/off-market/*` URLs (traffic spread one-address-thin).

**The reading:** two onsite surfaces have any concentration (`for-sale-v3`, `analyse-your-home` ≈ 10/day each); everything else is single-digits/day or spread across thousands of unique URLs. The site-wide **true-reward rate is ~1–2 per day**. That is 2–3 orders of magnitude below what an online policy over a rich action space needs to escape noise — exactly the off-market finding, now confirmed at the whole-site level.

### 3.2 What already exists (do not rebuild)

**The attribution spine (Brain 2, nightly 23:30–23:52):** `ad_attribution_build.py`, `ad_behaviour_build.py`, `organic_journey_build.py` (60d), `lead_attribution_build.py`, `seo_landing_performance.py`. Query surface: `scripts/brain2/ad_query.py`, `journey_tree.py`.

**The unified outcome ledger:** `scripts/samantha/lead_intelligence.py` (cron 02:00) dedupes **by email + address** across *every* lead-bearing collection (`property_reports`, `offmarket_qualification`, `forsale_ladder_responses`, `lead_signups`, `launch_leads`, `leads`, `price_alert_subscriptions`, `fb_leads`, `crm_contacts`) into **`system_monitor.lead_worklist`**, attaching `posthog_distinct_id` + CRM engagement. **This is already ~80% of a reward ledger.**

**Autonomous loops running now:**

| Loop | Optimizes | Cadence | Live? |
|---|---|---|---|
| Home Owner Lead Funnel wakeup | FB out-of-market seller-lead copy | hourly 08:00–22:00 | **LIVE** |
| Samantha weekly SEO (`seo_improvement_weekly.py`) | organic SEO / for-sale-v3; ships 1 fix | Sun 08:00 | **LIVE** |
| Samantha ad-lifecycle (`ad_lifecycle.py`) | FB ad cull + winner→organic | daily 12:40 | **LIVE** |
| Lead intelligence | unify/flag every lead → worklist | daily 02:00 | **LIVE** |
| Hot-lead responder | escalate hot leads (Messenger AI) | every 10 min | **LIVE** |
| Brain 2 / Brain 3 nightly builds | attribution + internal knowledge | nightly | **LIVE** |
| Samantha nightly DOER | marketing-direction signals | 02:30 (**not in current crontab**) | **UNCONFIRMED — verify** |
| CEO agents (3) | daily proposals | remote VM 00:03/00:33 | LIVE (remote) |
| Off-market RL | onsite deck | — | **NOT BUILT** (scoping only) |

**Upstream levers as code:** article gen + auto-publish (orchestrator step 120 → 121 sitemap resubmit; suburb articles via `fields-automation` GH Actions, self-hosted VM runner); SEO dashboard nightly + weekly Samantha ship; ad-lifecycle daily. **FB organic auto-posting is currently DORMANT** (`fb-content-scheduler` cron lines are commented out) — a live gap. Landing pages are **static** (deploy-time), no auto-iteration.

**Brains (all live, unified via `scripts/samantha/brain_search.py`):** B1 external (coaching corpus + KB), B2 in-house (FB Ads + PostHog), B3 internal (fix-logs, CEO memory, articles, decisions).

### 3.3 The two structural gaps (these gate the ambitious version)

**Gap A — the identity join only closes at form-submit.** The join key end-to-end is **email**; `posthog_distinct_id` is the behaviour bridge, forwarded to the backend *only by the AYH / off-market / for-sale-ladder submit forms*. Therefore:
- **Anonymous browsers** are never `identify()`-ed with an email (identify fires only for internal users — `src/utils/posthog.ts:129`), so their trajectory has no outcome attached.
- **FB lead-gen leads** never touch the site → email but **no distinct_id, no journey.**
- **`lead-signup.mjs` / `subscribe.mjs`** don't forward distinct_id → email-only join, no behavioural bridge.
- **Calls / posted mail** attach at the person level (email/address) but have **no automated link back to a distinct_id**.

A funnel-wide RL reward inherits every one of these breaks. **Closing the behaviour↔outcome join is the single highest-leverage prerequisite.**

**Gap B — no server-side personalization exists.** Content varies per-user only *client-side after hydration, via PostHog flags* (`for_sale_page_v1` 4-way, `discover_mode_v1`, `offmarket_gate_v1`); the `for-sale-v2/v3/v4` variants are *separate routes*, not per-user splits. SSR (`src/lib/db.server.ts`, `decision-feed-v3.mjs`) serves **everyone the same content.** "Dynamically load personalised copy given prior behaviour + attribution" **requires building a personalization-decision layer** — the hooks exist (flags + distinct_id) but the layer does not.

---

## 4. Proposed architecture — the Conductor + one reward ledger

Not one loop. A **Conductor** (a Claude-in-the-loop coordinator) sitting over sphere-specific arms, all accountable to **one reward ledger**.

```
                    ┌─────────────────────────────────────────────┐
                    │   UNIFIED REWARD LEDGER                      │
                    │   (extends system_monitor.lead_worklist)     │
                    │   every action → true downstream outcome     │
                    │   (inbound enquiry / identified seller)      │
                    └───────────────▲─────────────────────────────┘
                                    │ grades
        ┌───────────────────────────┼───────────────────────────┐
        │                           │                           │
 ┌──────┴───────┐          ┌────────┴────────┐         ┌────────┴────────┐
 │ SPHERE 2      │          │ SPHERE 1         │         │ SPHERE 3         │
 │ UPSTREAM      │          │ ONSITE           │         │ OFFSITE          │
 │ (fast, $-buys │          │ (slow, starved,  │         │ (tiny-N, human-  │
 │  trials;      │          │  needs build)    │         │  gated)          │
 │  loops exist) │          │                  │         │                  │
 │ • FB funnel   │          │ • personalization│         │ • call/email/    │
 │ • ad-lifecycle│          │   decision layer │         │   mail arms      │
 │ • SEO weekly  │          │ • off-market RL  │         │ • Will-to-action │
 │ • article gen │          │ • popup/copy A/B │         │   for anything   │
 │ • organic(dormant)│      │                  │         │   Claude can't do│
 └───────────────┘          └──────────────────┘         └──────────────────┘
        ▲                           ▲                           ▲
        └────────── THE CONDUCTOR (tiered-cadence Claude cycle) ─┘
        reads ledger + Brains 1/2/3 + web · attributes WHY · stages
        one change per sphere where signal supports · documents every
        cycle · self-monitors (Rule 7) · emits Will-to-action items
```

**Why a Conductor over existing loops, not a rebuild:** the loops already exist but each optimizes a **proxy** (CPL, indexation, swipe-depth) that is *never validated against the true reward*. The FB funnel already proved (Law 4) that engagement ≠ conversion. The Conductor's job is to **close that gap**: grade every upstream/onsite/offsite move by whether it produced a real inbound enquiry, and re-weight accordingly — so the *slow* onsite true-reward signal is amplified by the *fast* upstream levers that can act on it.

**Component 1 — the unified reward ledger (build first; mostly exists).** Extend `lead_worklist` into an *action→outcome* ledger: every action the system takes (ad launched, article published, page variant served, email/call/mail sent) gets a row; every true outcome (form submit, qualify, booked call, enquiry) is joined back to the action(s) that touched that person. This is the substrate the Conductor learns from. ~80% is `lead_worklist` + Brain 2 journeys; the missing ~20% is the action-side logging + the identity-join fix (Gap A).

**Component 2 — the Conductor cycle (Claude-in-loop).** Mirrors `run_wakeup.sh`: durable OS cron → headless `claude -p` (Claude Max) → read ledger + sphere state → attribute WHY → stage changes where signal supports → document (`cycles/*.md` + ledger + Telegram) → self-monitor.

**Component 3 — sphere arms.** Upstream: *coordinate* the existing loops (don't replace) + revive dormant organic. Onsite: the personalization-decision layer (Gap B) + adopt the off-market RL loop as an arm. Offsite: contextual-bandit-with-human — the Conductor proposes, Will executes via the action list.

**Component 4 — the "Will to action" mechanism** (Will's explicit ask). A persistent `WILL_TO_ACTION.md` ledger in this folder + a Telegram ping (@WillFieldsBot) whenever the loop hits something only a human can do — a new data asset, a physical-mail mechanism, sign-off on a new initiative, a budget/GC-go-live decision. Each item: ID, date raised, sphere, what's blocked, why it needs a human, status. The loop keeps working around blocked items rather than stalling.

---

## 5. Reward design

Use **reward shaping** — a dense proxy to learn from now, plus the sparse true reward it must ultimately move:

| Tier | Signal | Density (today) | Role |
|---|---|---|---|
| **Dense (shaped)** | dwell, scroll-depth, deck-depth, page-2 rate, return visit | ~thousands/mo (`time_on_page` 1,376, `scroll_depth` 613) | fast policy signal — where the loop learns day-to-day |
| **Mid (behavioural)** | `address_search`, `property_view`, `forward_cta_clicked`, menu-door | low-hundreds/mo | intermediate intent |
| **Sparse (TRUE)** | `analyse_home_submit_success`, `offmarket_qualify`, booked call, **inbound enquiry** | **~1–2/day site-wide** | the real objective — validates that dense gains transfer |

**The Goodhart guardrail is mandatory, not optional** — Law 4 already burned us (high-CTR angles, zero leads; the off-market doc's "false winner" risk). Rule: **any dense-reward win must be re-checked weekly against the sparse true reward; if a variant lifts engagement but not enquiry, it is a false winner and is discarded.** The north star (per [[samantha_redirect_inbound_enquiry_2026-07-27]]) is **inbound enquiry**, not clicks, not swipes.

---

## 6. Cadence

**1–3 hours is right for the *paid upstream* sphere and wrong for everything else.** Tiered:

| Tier | What happens | Cadence | Why |
|---|---|---|---|
| **OBSERVE** | cheap monitoring rollup; **no changes**; detect anomalies; fire Will-to-action alerts | **every 1–2h (daytime)** | matches Will's instinct where it's safe — pure observation is cheap and catches breakage/opportunity fast, no policy churn on noise |
| **DECIDE** | one Claude cycle: read ledger → attribute WHY → stage **one** change per sphere *where signal supports it* → document | **daily (evening)** | organic arrivals don't respond to a cron; a day accumulates enough behaviour to reason over |
| **VERDICT** | actual kill/scale with significance; promote/retire arms | **weekly** | at ~1–2 true rewards/day, kill/scale is a *weekly* question — daily verdicts overfit to noise |
| **Paid-arm fast lane** | the FB funnel keeps its **hourly** wakeup (dollars buy fast signal) | unchanged | already correct for that reward physics |

The Conductor *observes* hourly and *acts* on the timescale each sphere's reward can actually support.

---

## 7. Relationship to existing systems (avoid collision)

This is the most important open question, because **two autonomous Claude loops touching the same ad account / SEO / codebase can fight each other.**

- **Samantha** is the **co-CEO strategic loop** (business-level: which goals, which initiatives, 5-listings target). **This** is a **tactical funnel-optimization loop** (which copy, which page, which arm converts). They must not both, e.g., pause ads or ship SEO changes blind to each other.
- **Recommendation:** the Conductor is the **tactical execution layer that Samantha governs** — Samantha sets direction and reviews; the Conductor runs the measured cycles and reports up. Concretely: the Conductor *owns* the reward ledger + the sphere arms; Samantha *reads* its cycle output as one of her inputs. The existing loops (ad-lifecycle, weekly-SEO, FB wakeup) become **arms the Conductor coordinates**, not independent actors — one writer per lever, to prevent conflicting writes.
- **Alternative** (if Will prefers): keep them fully separate and give the Conductor a strict, non-overlapping lever set (e.g. onsite-only). Cleaner isolation, less power. **Will's call — this is Open Question 1.**

---

## 8. Proposed phased roadmap (for discussion — nothing committed)

**Phase 0 — Unified reward ledger + close the identity join (foundation; the true first task).**
Extend `lead_worklist` into an action→outcome ledger; add action-side logging (what the system did); **fix Gap A** — forward `posthog_distinct_id` from *all* conversion forms, and add a lightweight identity stitch so anonymous journeys can attach to outcomes retroactively where possible. *Exit test:* for a sample of real conversions, we can trace the full upstream→onsite→outcome chain in one query. **Until this exists, no funnel-wide loop can learn.** Cheap (mostly wiring existing pieces).

**Phase 1 — Conductor over the existing upstream loops (no new product; densest reward).**
Stand up the tiered-cadence Conductor; point it at the *existing* upstream loops (FB funnel, ad-lifecycle, weekly-SEO, article gen) and make them accountable to the true reward, not their local proxies; revive dormant FB organic as a governed arm; wire OBSERVE→Will-to-action. *Exit test:* one cycle where an upstream decision is graded by a real downstream enquiry and re-weighted. Runs in parallel with Phase 0's tail.

**Phase 2 — Onsite personalization layer (new build; gated on Gap B).**
Build the server-side (or edge) personalization-decision endpoint: given a joined person's prior behaviour + attribution, choose which content/copy/popup to serve. Adopt the **off-market RL loop** as the first onsite arm (its scoping is done). Start with the two concentrated surfaces (`for-sale-v3`, `analyse-your-home`). Narrow arms, dense shaped reward, **weekly** verdicts, Goodhart guardrail on. *Exit test:* a served variant that lifts dense reward *and* holds the sparse true reward over a week.

**Phase 3 — Offsite arms (human-in-loop).**
Contextual bandit over call/email/posted-asset actions to high-intent people from the ledger; Conductor proposes, Will executes via Will-to-action; each offsite touch is logged as an action and its downstream re-engagement measured. Gated on a repeatable physical-mail mechanism (a standing Will-to-action item).

**Phase 4 — Close the full loop.**
Downstream onsite/offsite outcomes feed back to re-weight upstream (SEO topics, ad angles, article cadence, landing content) — the full three-sphere closed loop Will described.

---

## 9. Will-to-action mechanism (spec)

Seeded now as `WILL_TO_ACTION.md` in this folder. Format per item:

```
## [WTA-NNN] Short title — raised YYYY-MM-DD — [sphere] — status: OPEN|DONE|WONTFIX
**Blocks:** what the loop can't proceed on.
**Needs a human because:** (new data asset / physical mechanism / sign-off / budget / GC go-live / legal).
**Proposed:** what Claude recommends.
```

The Conductor appends here + pings @WillFieldsBot whenever it hits a human-only dependency, and **keeps working other arms** rather than stalling.

---

## 10. Open questions for Will

1. **Governance:** Conductor as the **tactical layer Samantha governs** (recommended), or a **fully separate onsite-only** system? This decides whether the existing loops become coordinated arms or stay independent.
2. **True reward definition:** is the single optimized objective **inbound enquiry** (per the 2026-07-27 north star), or a booked call, or an identified seller? Everything grades against this one number.
3. **Sequencing:** agree that **reward ledger + identity join (Phase 0) precede any loop**, given the true-reward rate is ~1–2/day? Or run a coarse upstream loop in parallel while the ledger lands?
4. **Onsite personalization:** is building a **server-side personalization-decision layer** in scope (Gap B), or should Sphere 1 stay client-flag A/B only for now (much less powerful, but no new infra)?
5. **Cadence:** comfortable with **OBSERVE hourly / DECIDE daily / VERDICT weekly** rather than a uniform 1–3h acting loop?
6. **Offsite budget + mechanism:** what physical-mail + outbound-call mechanisms can the loop assume exist (PostGrid? JustCall? Will-manual)? This sets whether Sphere 3 is real or a standing Will-to-action.
7. **Autonomy bounds:** what can the loop change unattended vs. what always routes to Will-to-action (esp. ad spend, GC go-live, anything public-facing)? The FB funnel's rule (never promote to GC) is the model.

---

## Appendix — key numbers (measured 2026-07-29 unless noted)

- **Whole-site traffic:** 1,601 pageviews / 30d (~53/day). Concentration: `/for-sale-v3` 299, `/analyse-your-home` 288; ~473 in the unique-URL long tail.
- **True reward rate:** `analyse_home_submit_success` 10 + `offmarket_qualify` <10 + `forsale_ladder_complete` ≈ **~1–2/day site-wide.**
- **Dense shaped-reward availability:** `time_on_page` 1,376, `$autocapture` 858, `scroll_depth` 613 / 30d.
- **Attribution:** join key = **email**; behaviour bridge = `posthog_distinct_id`, populated only at form-submit; anon + FB-ad leads stranded. Existing spine = Brain 2 nightly builds + `lead_worklist` (02:00).
- **Existing autonomous loops:** 7 live (FB wakeup hourly, weekly-SEO, ad-lifecycle daily, lead-intel 02:00, hot-lead 10-min, Brain 2/3 nightly); Samantha nightly DOER unconfirmed; off-market RL not built; FB organic dormant.
- **Personalization:** client-side PostHog flags only; SSR uniform; server-side personalization = a build.
- **Source funnel laws:** personal open loop + specific $-shock converts; engagement ≠ conversion (Goodhart, proven).

---

*Research inputs: PostHog project 348370 (site-wide event + pathname volumes); the Home Owner Lead Funnel (`01_STRATEGY.md`, `run_wakeup_prompt.md`, `run_wakeup.sh`, `00_MASTER_LEDGER.md`); the off-market RL scoping; live `crontab -l` + `systemctl`; code map of `scripts/crm_sync.py`, `crm_lead_sync.py`, `scripts/samantha/{lead_intelligence,seller_intent,ad_lifecycle,seo_improvement_weekly}.py`, `scripts/brain2/*`, `src/utils/posthog.ts`, website Netlify functions. See memory: [[home_owner_lead_funnel]], [[offmarket_rl_scoping]], [[samantha_redirect_inbound_enquiry_2026-07-27]], [[crm_attribution_writepath]], [[lead_intelligence_pipeline]], [[brain2_inhouse_data]], [[posthog_analytics]], [[active_experiments]].*
