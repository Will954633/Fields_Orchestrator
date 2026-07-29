# General Reinforcement Learning — Scoping Document (v2)

**Author:** Ops agent · **Date:** 2026-07-29 · **Status:** Scoping, worked through with Will (nothing built yet)
**v2 supersedes v1** — rebuilt around the closed-loop thesis after discussion. v1's "Conductor over spheres" framing and its "statistical A/B is dead on arrival" claim are both **retired** (see §2–§3 for why).

**Concept:** A family of **Claude-as-analyst** workflows that, together, form **one closed feedback loop** — the website's own behaviour (sensor) steers what traffic the upstream content/ads engine goes and acquires (actuator), which grows and improves the traffic, which the onsite + offsite arms convert, whose outcomes re-steer the upstream engine. Ported from the proven [Home Owner Lead Funnel](../03_Facebook/Home_Owner_Lead_Funnel_Search/) pattern.

---

## 1. TL;DR

1. **This is one closed loop, not three separate optimisers.** SENSE (onsite behaviour + attribution) → STEER (signals) → ACQUIRE (upstream content/ads that *manufacture* traffic) → CONVERT (onsite per-user + offsite) → back to SENSE. The **onsite→upstream feedback loops are the crown jewels** — the site telling the acquisition engine what traffic to go get and what to make more of. (§2)

2. **"RL" here means Claude-as-analyst, not a statistical bandit.** Like the running FB loop, a Claude session observes, forms a mechanism-level hypothesis, reads early proxy signals *before* the true reward lands, kills/launches, writes up **why**, and compounds the theory each cycle. The FB loop makes confident decisions off **6 total leads** and kills variants on **~100 impressions** — it reasons about *mechanisms*, not *significance*. **That method runs fine on today's traffic.** (§3)

3. **The flagship first loop already exists in the data: AI-channel optimisation (GEO).** This morning we got our first **Copilot** referrals (4) and 2 **ChatGPT**; Bing (Copilot's engine) converted **2 of our 7 converting sessions off just 29 journeys** — ~4× Google's conversion rate — and nobody told the content engine to chase it. `ai_source` is already instrumented. This is the perfect proof-of-concept: live, instrumented, converting, fast on both ends, and uncontested. It also **diagnoses and recovers** dead channels (we had ChatGPT leads months ago, now near-zero → *why did they come, why did they stop, how do we win them back?*). (§2.2)

4. **Architecture (decided): independent sub-autonomous workflows + one shared reward ledger, with Samantha as the future meta-conductor.** Each domain (system-health, SEO, FB-ads, off-market, onsite-funnel) runs its own self-contained loop at its own cadence, but they all **read from and write to a shared reward ledger** so nothing optimises a private proxy while the real number stays flat. Samantha (manual-only today → no collision) sits over the top later, monitoring and conducting from that one scoreboard. The two existing autonomous loops (FB funnel, off-market RL — now live) join the ledger too. (§4)

5. **The true reward (decided): an identified, contactable seller** (name+email+phone+intent in `lead_worklist`), with **proactive inbound enquiry as a high-weight bonus multiplier**, and booked-call/listing as the weekly sanity-check. Everything grades against this one number. (§5)

6. **The reward is a self-discovering, self-reweighting milestone map (decided).** The system earns a *shaped* reward at each milestone a user reaches, weighted by that milestone's **measured predictive power** toward the true reward (potential-based shaping — provably doesn't distort the real objective). Weights are re-learned continuously (the built-in Goodhart defence), cold-started from the FB funnel's proven laws. **The system discovers and re-weights milestones as an ongoing job.** Building this ledger + fixing the identity join is **Phase 0** — nothing can learn until it exists. (§5)

7. **Two structural gaps gate the ambitious onsite arm** — identity only joins behaviour↔outcome at form-submit (anon + FB-ad leads stranded), and there is no server-side personalization (per-user content is a build). Both are Phase-0/Phase-2 items, not blockers to starting. (§10.3)

8. **Cadence (decided): OBSERVE hourly · DECIDE daily · VERDICT weekly**, per sphere's reward physics — with the FB funnel keeping its hourly fast-lane. Hourly OBSERVE has a real job: surface a high-intent individual (a returning frustrated vendor) to Will *while they're still on the site*. (§11)

---

## 2. The core thesis — one closed loop

The system is a control loop, not a set of parallel tools. Its power is that the **onsite arm senses**, the **upstream arm can manufacture traffic**, and the **shared ledger is the wire between them**.

```
   SENSE  ──────────────►  STEER  ──────────────►  ACQUIRE  ──────────────►  CONVERT ──┐
   onsite: every           signals derived from     upstream arm — CAN         milestone   │
   session's story +       what converted & from    BUY / MANUFACTURE          pages +     │
   full attribution        where: "Copilot traffic  exposure: paid ads +       per-user    │
   (channel, referrer,     appeared & converts →    AI-optimised organic       reasoning + │
   ai_source, journey,     make GEO content";        + SEO + articles →         Will's      │
   what converted)         "ChatGPT leads dried      more & better-matched      calls       │
        ▲                  up → win them back"       traffic to the site                    │
        │                                                                                    │
        └──────────────────────  more & better-matched traffic  ◄──────────────────────────┘
```

### 2.1 Why this dissolves the "onsite is slow" problem
Looked at in isolation, the onsite arm is slow: it can't buy exposure, so a single content-variant test accumulates only at the organic arrival rate (~10 visits/day on the busiest page). **But the combined system is not a passive recipient of traffic — it drives its own, and drives more of the kind its sensor says converts.** So it actively speeds up its own test clock and grows the high-intent stream. The "slow clock" was an artefact of viewing one arm alone.

### 2.2 The flagship worked example — AI-channel optimisation (GEO)
Generative engines (ChatGPT, Copilot, Perplexity, Gemini) are an emerging referral channel most competitors don't optimise for. The loop in action:

- **SENSE:** `organic_journeys` already tags `ai_source`. Current build: **Copilot 4, ChatGPT 2**; `copilot.microsoft.com` appears as a referrer for the first time (this morning). Bing (29 journeys) produced **2 of 7 conversions** — ~4× Google's per-journey conversion rate.
- **STEER:** the signal is "AI-referred traffic is arriving and converting above weight, and one AI channel that used to convert (ChatGPT, months ago) has gone dark."
- **ACQUIRE:** the upstream arm acts — generate **AI-optimised / citation-friendly content** (GEO: structured data, quotable stats, question-shaped headings, methodology pages LLMs cite), and run the diagnosis-and-recovery cycle on the dead ChatGPT channel.
- **CONVERT → SENSE:** measure whether GEO content lifts AI-referred conversions; re-steer.

This loop is **fast on both ends** (an onsite signal → an upstream content action that publishes in hours), unlike a pure onsite variant test — which is exactly why the onsite→upstream loops, not onsite→onsite tuning, are where leverage compounds.

---

## 3. What we're porting — Claude-as-analyst, not statistical RL

The Home Owner funnel is **not a bandit reaching significance.** Read its live cycles ([`cycles/cycle_20260729_1001.md`](../03_Facebook/Home_Owner_Lead_Funnel_Search/cycles/) …1101, …1201): it kills AN20 on ~106 impressions and one click; it has made *every* decision off a total of **6 leads**; it acts on **CTR and delivery priority before a single lead lands**; and it attributes at the level of **mechanism** — "the viewer needs a NUMBER, not a CONCEPT… same failure mode as AN6/AN8/AN12." That is a sharp analyst forming a hypothesis, testing it, reading an early proxy, writing down *why*, and compounding the theory. **This method ports to onsite traffic unchanged.**

**The one real difference is tempo, and it cuts both ways:**
- On FB, dollars push a variant to 50–200 impressions in two hours → a same-day read. Onsite, a variant is seen only as fast as traffic arrives → a *single-variant* verdict takes days. (Mitigated by §2.1 — the system drives its own traffic.)
- **But each onsite observation is far richer than an FB impression.** FB sees impression+click (a binary). Onsite sees the whole story — dwell, scroll, which cards, what they did next, whether they returned, and via attribution what they'd already viewed and whether their own home is listed. **One session tells Claude more than 50 blank FB impressions.**
- **And onsite Claude can reason about *named individuals with full histories*** — impossible on anonymous FB. Pure upside.

So: same observe → analyse → note → iterate discipline, same cycle files. Onsite is **narrower and slower on the variant-test side, richer on the observation side, with a per-individual layer FB can't touch.**

### The transferable laws (seed every workflow — earned by real kills)
> Converting hooks require a **PERSONAL OPEN LOOP** the next step closes ("what's MY number?"). Topic engagement without it does not convert, regardless of CTR.

1. Specific shocking numbers ≫ abstract concepts (7–10× CTR). 2. Compound = narrative + $-shock + personal question. 3. Fear > aspiration. 4. **Engagement ≠ conversion** (the Goodhart proof — high-CTR agent-trust angles converted zero). 5. Format × context (table/data → light, narrative/shock → dark).

---

## 4. Architecture — independent workflows, shared ledger, Samantha over the top

```
                 ┌──────────────────────────────────────────────────────────┐
                 │  SHARED REWARD LEDGER  (extends system_monitor.lead_worklist)  │
                 │  every ACTION → every OUTCOME, attributed by channel/       │
                 │  referrer/content/milestone → true reward (identified seller)│
                 └───────▲───────▲───────▲───────▲───────▲────────────────────┘
                         │       │       │       │       │  (all read + write)
     ┌───────────────┬───┴───┬───┴───┬───┴───┬───┴───┬───┴──────────────┐
     │ system-health │  SEO  │ FB-ads│ off-  │ onsite-funnel (NEW)      │
     │  workflow     │ workfl│ workfl│ market│  = the SENSOR of the loop│
     │ (exists)      │(exists│(exists│ RL    │  + GEO/AI-channel arm    │
     │               │ weekly│ daily)│(live) │                          │
     └───────────────┴───────┴───────┴───────┴──────────────────────────┘
                         ▲
                 ┌───────┴─────────────────────────────────────────────┐
                 │  SAMANTHA (future meta-conductor)                     │
                 │  monitors + conducts from the one scoreboard.        │
                 │  Manual-only today → NO collision risk now.          │
                 └──────────────────────────────────────────────────────┘
```

**Decided (Will, this session):**
- **Independent sub-autonomous workflows per domain**, each self-contained (own loop, own cadence, own local decisions). No monolithic controller.
- **One shared reward ledger** they all read/write — so the SEO loop sees whether its traffic converted, the ad loop sees its leads go cold, the onsite loop sees which channel its high-intent visitors came from. This is the anti-Goodhart mechanism at the *system* level: no workflow can look successful on a private proxy while the real number is flat.
- **Samantha is the future meta-conductor** — she monitors and conducts the workflows from that scoreboard. She runs manual-only today, so there is **no two-loops-fighting risk right now**; the sub-workflows are built first, Samantha inherits the conductor role when automated.
- **The two existing autonomous loops (FB funnel, off-market RL) join the ledger** so Samantha gets a holistic view (e.g. an FB lead going cold, or an off-market swiper resurfacing on `/analyse-your-home` weeks later — visible in one place). They keep running exactly as-is; they just also report in.

**The ledger's #1 job is channel/referrer/content attribution of conversion** — because that is the wire the ACQUIRE arm needs to know what to make more of (§2).

---

## 5. The reward — identified seller, via a self-reweighting milestone map

**True reward (decided):** an **identified, contactable seller** — name+email+phone+selling-intent landing in `lead_worklist` — with **proactive inbound enquiry as a high-weight bonus multiplier** (worth more, not a separate objective) and **booked-call / listing as the weekly sanity-check** that the intent-leads are real, not noise.

**The milestone map (decided) — this is what makes it learnable at low N.** A user's path to the true reward passes through many milestones. The system earns a *shaped* reward each time a user reaches one, and **each milestone's reward weight = its measured predictive power toward the true reward** — P(identified seller | reached this milestone). Illustrative chain (the system refines it):

```
anon pageview → return visit → viewed own suburb data → property_view →
address_search → started AYH / off-market qualify → address_submit →
submit_success (contact captured) → seller-intent flagged →
[TRUE REWARD: identified contactable seller] → (×bonus) proactive inbound enquiry
```

Properties of the design:
- **Dense enough to learn on now.** Instead of waiting for ~1–2 true rewards/day, the loop learns every cycle on milestone transitions — `time_on_page` (1,376/mo), `scroll_depth` (613), `property_view` (361) are all available shaped signals.
- **Provably safe.** Potential-based shaping (weight = predictiveness) does not distort the true objective.
- **Self-defending against Goodhart.** Weights are **re-learned continuously** — a milestone only earns what it *currently* predicts. If "viewed a market chart" stops predicting conversion, its reward decays automatically. This is Law 4 (engagement ≠ conversion) enforced structurally: a milestone that leads nowhere earns almost nothing.
- **Never flying blind.** Cold-started from the FB funnel's proven laws (personal-open-loop milestones weighted high, passive-browse low), updated as real data accumulates.
- **Self-discovering (decided).** Discovering new candidate milestones and re-weighting existing ones is an **ongoing job of the system itself**, not a fixed list we define once.

**Building this milestone ledger + fixing the identity join is Phase 0.** It *is* the shared reward ledger; every workflow grades against it.

---

## 6. The three spheres, re-cast as loop roles

| | **Onsite = SENSOR** | **Upstream = ACTUATOR** | **Offsite = CLOSER** |
|---|---|---|---|
| **Role in loop** | senses each visitor's story + attribution; converts the high-intent | manufactures traffic; acts on the sensor's signals | closes the identified few (call/email/mail) |
| **Can buy trials?** | no (organic arrival-bound) | **yes** ($ or content) | no (human + $ gated) |
| **Reward physics** | starved but rich per-observation | dense; fast where paid | tiny-N, high-value |
| **Learning mode** | Claude-as-analyst + per-user reasoning | Claude-as-analyst; several loops exist | contextual, human-in-loop |
| **Loop viable now?** | yes (shaped rewards + per-user) | **yes — where the leverage is** | yes as Will-to-action |

---

## 7. Onsite — the two-tier sensor

At ~46 visitors/49 sessions/day, onsite runs **two loops at once**:

**(A) Per-user reasoning — the identifiable high-intent few (single digits/day). Immediate value.**
The loop reads the day's journeys + `seller_intent`, places each person on the milestone map from their story, and picks the single best next action *for them* — surface a specific payload on their next visit, and/or **fire a Will-to-action so you can call while they're warm.** This needs reasoning over stories, not statistics; outcomes are observed per-person, so it learns fast. `seller_intent.py` already produces the input (own-home days-on-market + competing listings viewed → "frustrated vendor" / "pre-market seller").

**(B) Population content policy — anonymous milestone-cohorts (the slow game).**
Accumulate sessions *by milestone-state* over weeks; learn "for a session in state X from channel Y, content Z lifts progression." Classic optimiser, traffic-rate-limited → weekly/monthly verdicts, dense shaped rewards only. Real, but the long play — and it only pays as upstream grows the traffic.

**Onsite personalization scope (Q4 — recommended, pending final confirm):** build a **thin, staged** server-side decision layer on the two surfaces that actually have traffic (`/for-sale-v3` 299/mo, `/analyse-your-home` 288/mo), keyed to milestone-state — **not** a site-wide personalization engine up front, and **not before** Phase 0/1 prove which milestones matter. Start narrow, expand as reward justifies.

---

## 8. Upstream — the actuator that manufactures traffic

Where the loop's leverage compounds. Coordinate the **existing** loops (don't rebuild), make them accountable to the shared reward, and add the GEO arm:

- **FB ads** — Home Owner funnel wakeup (hourly, live) + `ad_lifecycle.py` (daily cull + winner→organic).
- **SEO** — `seo_dashboard.py` (nightly) + Samantha weekly SEO ship (live) + the new **GEO/AI-channel** arm (§2.2) — the flagship.
- **Articles** — orchestrator step 120 auto-publish + `fields-automation` GH Actions. Topic/cadence/hook become steered by what converts, not just "new listings."
- **Organic FB** — `fb-content-scheduler` is **currently dormant (cron commented out)** — a live gap to revive as a governed arm.
- **Landing pages** — static today; enter the loop via the onsite personalization layer (§7).

**The change is not new optimisers — it's making each one read the shared ledger** so its output is graded by real downstream conversion (and by channel), not its local proxy (CPL, CTR, indexation).

---

## 9. Offsite — the human-gated closer

Contextual, human-in-loop: the loop proposes the best call/email/posted-asset for a high-intent person from the ledger; **Will executes**; each touch is logged as an action and its downstream re-engagement (return visit, reply, booked call) is measured back into the ledger. **Gated on a repeatable mechanism** (print-post + outbound-call) — a standing Will-to-action (WTA-005). Phases 0–2 don't depend on it.

---

## 10. Current state — the evidence

### 10.1 Traffic (measured 2026-07-29)
- **Last 24h:** 46 unique visitors · 49 sessions · 64 pageviews (~1.3 pp/session). Channel: **68% organic search**, 20% direct, 7% organic social, 5% referral.
- **Last 30d:** 1,601 pageviews site-wide (~53/day); true conversions low-tens/month. Concentrated surfaces: `/for-sale-v3` 299, `/analyse-your-home` 288; the rest spread one-address-thin across thousands of unique URLs.
- **Journeys (current build, 265):** 132 viewed ≥1 property, **only 5 viewed ≥2**; 10 searched; **7 converted; 7 submitted an address.** High-intent identifiable segment = single digits.
- **AI channel:** `ai_source` Copilot 4 / ChatGPT 2; Bing 29 journeys → **2 conversions** (vs Google 140 → 4). AI/Bing converting ~4× Google per journey.

### 10.2 What already exists (do not rebuild)
- **Attribution spine:** Brain 2 nightly builds (`ad_attribution`, `ad_behaviour`, `organic_journey` 60d, `lead_attribution`, `seo_landing_performance`).
- **Unified outcome ledger (~80% of the reward ledger):** `lead_intelligence.py` (02:00) dedupes every lead-bearing collection into `system_monitor.lead_worklist` with `posthog_distinct_id` + CRM engagement. `seller_intent.py` layers per-person seller conclusions on top.
- **Rich per-session record:** `organic_journeys` (entry, channel, referrer, ai_source, pages, properties_viewed, searches, converted, pattern).
- **Live autonomous loops (7):** FB wakeup (hourly), weekly-SEO, ad-lifecycle (daily), lead-intel (02:00), hot-lead responder (10-min), Brain 2/3 nightly. **Off-market RL is now BUILT and live** (daily 19:00, as of this morning). CEO agents on the remote VM. **FB organic auto-posting dormant.**
- **Brains 1/2/3** all live, unified via `scripts/samantha/brain_search.py`.

### 10.3 The two structural gaps (Phase-0 / Phase-2 items)
- **Gap A — identity join only closes at form-submit.** Join key = email; `posthog_distinct_id` bridge forwarded only by AYH/off-market/ladder forms. **Anonymous browsers and FB-ad leads are stranded** (`identify()` fires only for internal users; `lead-signup`/`subscribe` don't forward distinct_id; calls/mail attach at person-level only). Fix in Phase 0.
- **Gap B — no server-side personalization.** Content varies only client-side post-hydration via PostHog flags; SSR is uniform. Per-user content is a build (Phase 2, thin/staged — §7).

---

## 11. Cadence (decided)

| Tier | What | Cadence | Why |
|---|---|---|---|
| **OBSERVE** | monitoring rollup; **no changes**; surface high-intent individuals + fire Will-to-action | **hourly (daytime)** | your instinct, with a real job: ping Will about a returning frustrated vendor *while they're on the site* |
| **DECIDE** | one Claude cycle/workflow: read ledger → attribute WHY → stage one change (incl. per-user actions every cycle) → document | **daily** | a day accumulates enough story to reason over |
| **VERDICT** | kill/scale content variants with the analyst's mechanism-reasoning (not significance) | **every few days–weekly** | onsite variant tests reach a read at the organic arrival rate |
| **Upstream fast-lane** | FB funnel keeps hourly; GEO content actions publish in hours | as-is | dollars/content buy fast signal |

---

## 12. Autonomy bounds (decided — the FB-funnel model)

**Free (low-risk, reversible):** stage content variants, cull weak ad variants, propose SEO/article/GEO changes, re-weight milestones, flag individuals to Will.
**Routes to Will-to-action (real-world blast radius):** net-new ad spend beyond set caps, **Gold Coast go-live**, sending physical mail / placing outbound calls, anything new that's public-facing. **Never acts unattended on the irreversible or the costly** — exactly the FB funnel's "never promote to GC without Will" rule, generalised.

---

## 13. Phased roadmap

**Phase 0 — Shared reward ledger + milestone map + identity join (the true first task; mostly wiring).**
Extend `lead_worklist` into an action→outcome ledger with channel/referrer/content attribution; stand up the milestone map + predictiveness weights (cold-started from the FB laws); fix Gap A (forward distinct_id from all forms + retroactive stitch). *Exit:* for a real conversion, trace the full channel→onsite→outcome chain in one query, and read each milestone's current predictive weight. **Nothing learns before this.**

**Phase 1 — The flagship loop (GEO/AI-channel) + make existing upstream loops ledger-accountable.**
Stand up the onsite-funnel sensor workflow; ship the AI-channel loop (§2.2) end-to-end (sense ai_source → generate GEO content → measure); point the existing FB/SEO/article loops at the shared reward; revive dormant FB organic as a governed arm; wire OBSERVE→Will-to-action. *Exit:* one full turn of the loop — an onsite signal drives an upstream action that measurably moves AI-referred conversion.

**Phase 2 — Onsite arms (gated on Gap B).**
Thin staged personalization on `/for-sale-v3` + `/analyse-your-home` keyed to milestone-state; adopt the (now-live) off-market RL as an onsite arm; stand up the per-user reasoning loop (A) on the identifiable high-intent few. *Exit:* a served variant that lifts dense reward *and* holds the sparse true reward over a week.

**Phase 3 — Offsite closer (human-in-loop).** Contextual call/email/mail actions on high-intent people; gated on the mechanism (WTA-005).

**Phase 4 — Full closure + Samantha as meta-conductor.** Downstream outcomes re-weight all upstream levers; Samantha (once automated) conducts the workflows from the shared scoreboard.

---

## 14. Will-to-action mechanism

`WILL_TO_ACTION.md` (this folder). Each workflow appends + pings @WillFieldsBot on any human-only dependency (new data asset, physical mechanism, sign-off, budget, GC go-live, legal) and **keeps working other arms rather than stalling.**

---

## 15. Remaining open questions (most now decided)

- **Resolved:** governance (§4), true reward (§5), milestone design + self-discovery (§5), method = Claude-as-analyst (§3), cadence (§11), autonomy bounds (§12), sequencing = ledger-first (§13).
- **Q4 — onsite personalization scope:** confirm the **thin, staged, two-surface** version (§7) rather than a full engine up front.
- **Q5 — offsite mechanism:** which print-post + call tooling may the loop assume (PostGrid / JustCall / Will-manual)? Standing WTA-005.
- **New Q — GEO scope:** is generating AI-optimised (LLM-citation-friendly) content an approved upstream action to build first in Phase 1? (Recommended — it's the flagship.)

---

## Appendix — key numbers (measured 2026-07-29)

- Traffic: 24h = 46 visitors / 49 sessions / 64 pv; 30d = 1,601 pv (~53/day); true reward ~1–2/day.
- Concentrated surfaces: `/for-sale-v3` 299, `/analyse-your-home` 288; rest one-address-thin.
- Journeys (build of 265): 132 viewed ≥1 property, 5 ≥2, 10 searched, **7 converted, 7 address-submits**.
- **AI channel:** ai_source Copilot 4 / ChatGPT 2; Bing 29→2 conversions vs Google 140→4 (~4× per-journey).
- Shaped-reward availability: time_on_page 1,376, autocapture 858, scroll_depth 613 /30d.
- Attribution: join = email; distinct_id bridge only at form-submit; anon + FB-ad leads stranded.
- Existing: Brain 2 spine + `lead_worklist` (~80% of ledger) + `organic_journeys` + `seller_intent`; 7 live loops; off-market RL now live; FB organic dormant.
- FB source-loop proof: 6 leads total, kills on ~100 impressions, acts on CTR pre-lead, mechanism-level attribution.

---

*Inputs: PostHog project 348370 (24h + 30d traffic, pathname + event + ai_source breakdowns); the Home Owner Lead Funnel (`01_STRATEGY.md`, `run_wakeup_prompt.md`, live cycles 1001/1101/1201); the off-market RL scoping + now-live build; `crontab -l` + `systemctl`; code map of `crm_sync.py`, `crm_lead_sync.py`, `scripts/samantha/{lead_intelligence,seller_intent,ad_lifecycle,seo_improvement_weekly}.py`, `scripts/brain2/*`, `src/utils/posthog.ts`, `organic_journeys` schema, website Netlify functions. Memory: [[home_owner_lead_funnel]], [[offmarket_rl_scoping]], [[general_rl_scoping]], [[samantha_redirect_inbound_enquiry_2026-07-27]], [[crm_attribution_writepath]], [[lead_intelligence_pipeline]], [[brain2_inhouse_data]], [[posthog_analytics]].*
