# 04 — Expanded Mandate: Funnel-Discovery Lab (Scoping)

**Status:** SCOPING — awaiting Will's answers to §11 open questions before build.
**Date:** 2026-07-30 AEST · **Author:** Claude (VM agent) · **Owner:** Will Simpson
**Supersedes (on approval):** the single-step copy-discovery mandate in `run_wakeup_prompt.md`.

---

## 1. Why we're expanding

The 2.3-day review (see `00_MASTER_LEDGER.md`, live FB pull 2026-07-30) found:

- **$868 spend → 7 leads → 4 quality "Yes"** (one of those a fake +93 phone). Blended CPL $124.
- **Isolated, the winners are fine:** AN2 $16/lead, AN15 $26, AN14 $27 — the $124 was the *cost of searching* across 40 angles, not the cost of a working funnel.
- **The killer problem is reward sparsity.** 1–2 leads per winning ad is statistically noise. You cannot optimise copy — let alone *sequences* of copy — on 7 events. Every cycle "verdict" to date is a coin-flip dressed as a finding.
- **All conversions landed Day 1**, then flatlined despite continued spend — but off 1–2 leads that decay is indistinguishable from noise.

**The fix is to move the optimisation target up-funnel to engagement**, where there are 50–100× the data points per dollar, so the learning loop becomes statistically real for the first time. That single change is the point of this expansion.

## 2. Decisions locked (Will, 2026-07-30)

1. **Behaviour-measurement, NOT harvest-and-ghost.** We measure how far down a funnel people go via owned analytics (PostHog); we do **not** collect and then fail to honour real people's PII. Honest end-states only.
2. **Will approves each new funnel template** before it goes live (landing pages are gated, unlike the current ad-batch autonomy).
3. **The cross-boundary reward ledger is in scope now** — it is the prerequisite build, not a side task.

## 3. The mandate, restated

**Primary metric:** engagement, weighted by downstream intent (§5) — not raw clicks, not single-step CPL.

**Main goal (unchanged in spirit):** find cost-effective, high-converting funnels that ultimately produce a real Gold Coast homeowner who wants to talk to us (a call, an email, a two-way mini-site conversation, or a mailable address).

**Sub-goals (new — the agent optimises toward *any* of these micro-conversions and reports each separately):**
- **G1 — Address** (highest business value: address → direct mail → inbound call; our own strategy already says the public gives address most readily)
- **G2 — Email**
- **G3 — Name**
- **G4 — Phone** (believed most-resisted; to be proven, not assumed)

**Explicit learning objectives (the questions the lab exists to answer):**
- **Q1 — Resistance ranking:** which of address/email/name/phone do people resist most, measured by field-level drop-off, not guesswork.
- **Q2 — Warm-up depth:** how many value touches, and what kind, must precede each ask before completion rate clears a bar.
- **Q3 — Funnel shape:** single-step vs progressive; on-FB vs landing-page; which sequences convert cheapest *for quality*.

## 4. Scope boundaries (what "we don't deliver" actually means)

We have **no Brisbane assets** — no valuation, no report, no mini-site for that market. So there is **no honest offer to fulfil out-of-market**. That is precisely why we measure *behaviour*, not harvest PII:

- We learn "68% clicked → 40% started the address field → 22% completed → 9% then gave email" **without storing a record or making a promise we won't keep.**
- Every funnel ends on an **honest terminal state**, e.g. *"We're not live in your area yet — want on the waitlist?"* No fake report, no ghosted inbox.
- **No PII is persisted** unless a genuinely fulfilable offer exists (a Brisbane market-newsletter/waitlist is the only candidate, and is out of scope for the learning phase — revisit later if Will wants it).

This removes the Privacy Act / Spam Act / Meta-lead-policy exposure and the brand landmine, and yields a *richer* dataset than un-actioned form-fills.

## 5. Reward function (the thing that stops us perfecting a junk funnel)

Raw engagement is a trap: AN3 had the cheapest "leads" in the whole run and every one was junk "No" intent. So the reward is a **composite**, and the terminal quality gate stays visible the whole way down:

```
reward(funnel_variant) =
    w1 · engagement_rate           (CTR → LPV → funnel-step progression)
  + w2 · micro_conversion_value    (address > email > name > phone-completion, weighted by G1..G4 business value)
  - w3 · junk_signal               (No-intent / bounce / <Ns dwell / disposable-email / invalid-phone patterns)
```

Weights start heuristic and are tuned as data accrues. The agent must **always report the quality-adjusted number alongside raw engagement** — a variant that wins on clicks but selects for tyre-kickers is a loss, not a win.

## 6. Architecture — three builds

### 6A. Cross-boundary reward ledger (PREREQUISITE — build first)
The moment traffic crosses **FB ad → landing page** we hit the classic broken seam: attribution. The agent cannot optimise across that boundary without one unified event stream.

- **Join key:** PostHog `distinct_id`, threaded from the ad click through every funnel step (aligns with existing `crm_attribution_writepath` pattern). FB click carries a param → captured on LP load → all subsequent events share the id.
- **Event spine (one ordered stream per person):**
  `ad_impression → ad_click → lp_view → step_view(n) → field_focus(field) → field_complete(field) → micro_conversion(goal) → terminal_state`
- **Storage:** `system_monitor.funnel_events` (new collection) + PostHog. The ledger is what every cycle reads instead of `checkpoint.py`'s FB-only pull.
- **This is the same "unified reward ledger" the general-RL scoping flagged as the real build** — do it once, both efforts use it.

### 6B. Behaviour-measurement layer (no PII harvest)
- Field-level instrumentation: `field_focus` / `field_complete` fire on interaction, so we learn resistance **without submission**.
- Forms are honest: either they don't persist (measurement-only) or they end on a fulfilable waitlist. No thank-you page promising a report that won't come.
- Junk-signal detection feeds §5 (dwell time, disposable-email regex, invalid-phone patterns).

### 6C. Landing-page lab infrastructure
- **Serve off-brand, noindex:** `vm.fieldsestate.com.au/lab/<variant>/` via an nginx `alias` (same pattern as the existing `/preview/` block) with an added `X-Robots-Tag: noindex, nofollow` header. **Never** under `fieldsestate.com.au` (SEO/brand contamination — Brisbane content on a GC brand).
- **Spend-capped** per the existing $15/day-per-adset, $50/day-per-campaign discipline; the wider surface means a lab-wide daily ceiling too (propose $75/day total, §11).
- **Rule 7 self-monitoring:** every new ongoing job wraps `job_run(...)`; the lab's health shows on the Process Registry sheet.
- Template library lives in the folder (`lab_templates/`), each template a self-contained instrumented page.

## 7. The experiments this unlocks

1. **PII-resistance isolation (answers Q1):** single-ask funnels — address-only, email-only, name-only, phone-only — plus progressive combinations and orderings. Measure completion **and field-level drop-off** (focus vs complete). Impossible on a FB instant form; this is the core reason we need landing pages.
2. **Warm-up sequencing (answers Q2):** retargeting touch sequences — touch 1 = pure value / no ask, touch 2 = soft ask, touch 3 = the goal — measured as PostHog cohorts. How much warming before the ask "unlocks."
3. **Copy × creative × funnel-shape (answers Q3):** the proven winning DNA (single dominant self-relevant $ number + knowledge-gap mechanic) carried onto landing pages, tested single-step vs progressive, on-FB vs off-FB.

## 8. Funnel-template approval gate (Decision 2)

Unlike ad batches (autonomous), **each new landing-page template is Will-gated**:
1. Agent designs a template → renders a static preview at `/lab/preview/<name>/` → writes a one-page spec (hypothesis, funnel steps, which goal, honest terminal state, spend).
2. Agent sends Will the preview link + spec via Telegram and **stops** — does not drive traffic.
3. On Will's approval, agent wires the ad → template → ledger and goes live.
4. *Copy/creative iterations within an already-approved template stay autonomous* (so we keep learning velocity); only a genuinely new template/flow needs sign-off.

## 9. Guardrails (extends the current hard guardrails)

- ⛔ Never promote/enable/deploy anything to the GC served funnel (`120251770885910134`) or any GC-targeted audience — Will controls all GC go-live. **Unchanged.**
- ⛔ **Persist no PII without a fulfilable offer.** Measurement-only or honest-waitlist end-states.
- ⛔ Never publish lab pages under the main brand domain; `/lab/` only, always `noindex`.
- ⛔ Never make a promise (report/email/analysis) the flow can't honour out-of-market.
- ⛔ New landing-page **template** requires Will's approval (§8); copy within an approved template does not.
- Editorial rules unchanged (no advice/predictions, comparable RANGES, forbidden words, exact $, suburbs capitalised).
- Spend caps enforced; Rule 7 heartbeat on every new job.

## 10. Validity ceiling (buy the right learning)

Brisbane/Sunshine Coast is a **proxy**. Split deliberately:
- **Transfers to GC:** funnel *shape*, PII-resistance *ranking*, warm-up *depth*, hook *mechanics* — these are structural/psychological.
- **Does NOT transfer:** absolute CPL, absolute conversion rate, whether the person is a real prospect (Brisbane people aren't your buyers).

So the claim we buy here is *"we learned the shape of the funnel and the order people thaw."* **Economics are re-validated only in a GC run** — never trust a Brisbane CPL as a GC forecast.

## 11. Decisions resolved (Will, 2026-07-30)

1. **Lab-wide daily spend ceiling: $75/day** total across all lab funnels (down from today's ~$240/day of churn).
2. **End-state: newsletter waitlist.** Funnels end on a real Brisbane market-newsletter/waitlist opt-in (captures genuine emails honestly). **⚠ Commitment created:** the opt-in is only honest if the newsletter actually exists — so a **cheap public-data Brisbane market newsletter is now a required dependency** (ABS + portal data, same machinery as GC market content). Must be committed/built before the waitlist end-state goes live; until then, funnels use the pure "not live in your area yet" dead-end.
3. **Call surface: measure intent only.** A click on a "call us" CTA is the measured conversion — no live JustCall/SMS number in the Brisbane lab.
4. **First template: progressive multi-step** (name → email → address across steps). Field *ordering* is itself a primary test variable (Q1/Q2) — iterating the order within the progressive flow stays autonomous; a genuinely different flow needs a fresh §8 approval.

---

### Build sequence
1. **Ledger first** (6A) — ✅ **DONE 2026-07-30.** `ledger/funnel_ledger.py` (schema + `lab_*` event-spine contract + idempotent writers), `ledger/ledger_sync.py` (FB + PostHog → ledger, Rule-7 heartbeat, cron `3 8-22`), `ledger/compute_reward.py` (§5 composite + Q1 resistance ranking + quality-adjusted cost/goal). Validated end-to-end (synthetic join/reward/ranking all correct); live sync = 116 ad_stats rows / 82 variants / 0 lab events (expected pre-LP). Pushed to GitHub.
2. **Lab infra + instrumentation** (6C, 6B) — ✅ **DONE 2026-07-30.** nginx `/lab/` on vm.fieldsestate.com.au (alias `/home/fields/lab-funnels/`, `X-Robots-Tag: noindex,nofollow,noarchive`, no-store); `lab_harness.js` emits the full spine with declarative data-attributes, variant+lab_cid super-props, and **no raw PII** (email domain-only). `_selftest/` + README = the LP contract. Ledger aligned to `email_domain`; `_`/`unknown` variant guard added. Headless validation: all 7 spine events fire, no PII leak, no JS errors (PASS). Served copy at `/home/fields/lab-funnels/`; mirrored to repo `…/lab-funnels/`.
3. **Brisbane market-newsletter** (dependency of the §11.2 waitlist end-state) — commit or build before waitlist goes live; else dead-end until ready.
4. **First approved template** (§8 gate) — progressive multi-step (name → email → address), preview link + spec to Will, stop for approval.
5. **Rewrite `run_wakeup_prompt.md`** to the expanded mandate (this doc's §3/§5/§9), keeping the hourly thinking-cycle cadence.
6. **First live traffic** at the $75/day lab cap; iterate on the composite reward.
