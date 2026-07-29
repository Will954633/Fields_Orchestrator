# General RL — Development Plan (finish the build)

**Purpose:** the ordered milestone plan to complete the vision in `00_SCOPING.md` — the closed
SENSE→STEER→ACQUIRE→CONVERT loop across onsite/upstream/offsite, as independent self-pacing
sub-workflows on one shared reward ledger, with a meta-conductor over the top.

**Legend:** ✅ done · 🔨 buildable now · ⛔ gated on Will · 🔁 data-gated (build machinery now, value accrues).
Each milestone has an **acceptance test** — it's not done until that passes.

---

## Already built (the spine)
✅ Shared reward ledger + milestone map (history-informed, cost-aware, true-reward join) · identity join
(form-submitters) · self-pacing + tiered execution + autonomy bounds + Will-to-action/Telegram · Control Loop
dashboard + ops tab · **2 autonomous domains (GEO, SEO)** · Phase-2 design + P2.0 decision layer · WTA-012.

---

## M1 — Generalise the cycle scaffold  ✅ DONE 2026-07-29  *(makes every later domain cheap + consistent)*
Extract the per-domain runner/dispatcher into ONE generic pair driven by a domain registry, so a new domain =
just a **sensor** + a **prompt** + cron lines (not 5 hand-cloned files).
- `rl_cycle.sh <domain>` + `rl_dispatch.sh <domain>` (generic; read `<domain>_prompt.md`, lock/log/job/pacer by name).
- `domains.yaml` registry (domain → sensor script, cadence, cron slot, enabled).
- Migrate SEO to the generic runner (lowest-risk); GEO stays on its tested bespoke scripts (migrate later).
- **Acceptance:** SEO runs end-to-end via `rl_dispatch.sh seo`; heartbeat green; a new domain needs only 2 new files.

## M2 — Upstream breadth: onboard the remaining levers  🔨 (M2a Ads ✅ · M2b Articles · M2c FB-organic pending)  *(the bulk — biggest channels)*
Each is a new domain via the M1 scaffold (sensor + prompt), reading the shared ledger, tiered-execution.
- **M2a — Ads** (FB + Google): sensor over `ad_daily_metrics` + `google_ads_daily_metrics` + reward tie; cycle
  proposes budget/cull/creative moves (Tier-3 = spend/campaign → draft+telegram; Tier-1 = analysis, reporting).
  Onboard the existing **FB funnel** + **ad_lifecycle** to WRITE their actions/outcomes to the shared ledger.
- **M2b — Articles**: sensor over which topics/suburbs/pages convert (organic_landing_affinity + reward ledger);
  cycle drives topic/cadence/hook selection; new articles route through the fact-checked pipeline (Tier-3 publish).
- **M2c — Revive FB organic** as a governed arm (cron was commented out); cycle schedules data-first posts.
- **Acceptance:** each domain has a green heartbeat, a cycle file, actions in `rl_<domain>_actions`, and its
  outcomes visible in the shared ledger / Control Loop. FB funnel + ad_lifecycle write to the ledger.

## M3 — Onsite per-user loop  🔨  *(ungated; high near-term value)*
A cycle that reads `seller_intent` + `organic_journeys` + reward ledger, identifies **hot individuals**
(frustrated vendors, pre-market sellers, returning searchers), and **Telegrams Will while they're warm** +
queues them in `lead_worklist`. Not personalization-serving (that's P2.1) — this is intent-surfacing.
- **Acceptance:** a real high-intent visitor is surfaced to Will within the hour of a qualifying session, with
  their story + recommended action, logged.

## M4 — The learning/grading loop  🔨🔁  *(closes the RL heart)*
The automated arm-outcome attribution: for every active arm (content variant, title change, personalization
variant, ad angle), measure its effect on the target milestone, grade it, and update the policy — promote
winners, retire losers. This is what makes it reinforcement-*learning*, not reinforcement-*informed*.
- `arm_grader.py` — reads arm assignments + outcomes from the ledger/PostHog → per-arm lift vs control →
  writes verdicts to `rl_arm_grades`; feeds `personalization_policy` + each domain cycle.
- **Acceptance:** one real arm gets a data-backed verdict (win/kill/inconclusive-need-more-N) the cycles consume.
  (Value 🔁 accrues with volume; the machinery is the deliverable.)

## M5 — Foundation hardening  🔨
- Anonymous-journey handling: attribute where possible; retroactive `distinct_id` stitch onto historic leads.
- Switch the true reward from the `converted` proxy to the `lead_worklist` contactable-seller join once linkage
  is dense enough (the join exists; add the switchover + a coverage gate).
- **WTA-013** — Gold-Coast aggregate median into `getMarketMetricsSummary` so the AI-traffic page gets its Q&A.
- **Acceptance:** true-reward coverage metric rises; a Gold-Coast page renders the citable Q&A.

## M6 — Gated spheres (prep now, ship on Will's word)  ⛔
- **P2.1 (onsite personalization serving)** — build the deferred-slot on `/analyse-your-home` behind the
  kill-switch, with a before/after LCP measurement; **do not enable without Will's nod** (render-path on a slow page).
  Deliver as a ready diff + preview perf numbers.
- **Offsite sphere (WTA-005)** — the call/email/posted-asset closer cycle; **gated on the mechanism** (PostGrid /
  JustCall / manual). Prep the cycle so it's ready the moment the mechanism is chosen.
- **Acceptance:** each is one Will decision away from live, with the work pre-staged + measured.

## M7 — Meta-conductor (last)  🔨  *(after ≥3 domains)*
The cross-sphere coordinator (future-Samantha layer): reads the whole shared ledger + every sub-workflow's state,
allocates effort across domains, enforces one-writer-per-lever, surfaces the holistic picture. Independent
sub-workflows already give autonomous operation — this optimises allocation.
- `conductor.py` (or Samantha integration) + Control Loop dashboard shows ALL domains + arm grades.
- **Acceptance:** the conductor reallocates a cycle's cadence/priority based on cross-sphere reward, visible on the board.

## M8 — Observability + hardening pass  🔨  *(continuous)*
Every cycle self-monitors; Control Loop shows all domains, arm grades, action-audit trails; a weekly "what did the
system do + what moved" digest to Will. **Acceptance:** the board answers "is everything running + is it working?" at a glance.

---

## Critical path & sequencing
1. **M1** (unlocks cheap domains) → 2. **M2** (upstream breadth — biggest value, all buildable) →
3. **M3** (onsite per-user, ungated) in parallel → 4. **M4** (grading loop) in parallel as arms accrue →
5. **M5** (hardening, ongoing) → 6. **M6** prep (await Will) → 7. **M7** meta-conductor → 8. **M8** continuous.

**Buildable autonomously now:** M1, M2, M3, M4, M5, M7, M8. **Need Will:** M6 (P2.1 nod, offsite mechanism),
and any Tier-3 content/spend each cycle surfaces. Execution respects the tiered-autonomy model throughout.

---
*Status log kept in `01_BUILD_LOG.md`; human decisions in `WILL_TO_ACTION.md`.*
