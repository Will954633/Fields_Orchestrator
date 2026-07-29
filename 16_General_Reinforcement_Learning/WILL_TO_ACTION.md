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

## [WTA-001] Approve scoping direction + governance model — raised 2026-07-29 — [meta] — status: OPEN
**Blocks:** the entire build. Nothing is committed until you pick a shape.
**Needs a human because:** strategic sign-off + resolves how this coexists with Samantha (two autonomous Claude loops must not fight over the same levers).
**Proposed:** Conductor = tactical execution layer that Samantha governs; existing loops (ad-lifecycle, weekly-SEO, FB wakeup) become coordinated arms, one writer per lever. See `00_SCOPING.md` §7 + Open Question 1.

## [WTA-002] Define the single true reward — raised 2026-07-29 — [meta] — status: OPEN
**Blocks:** the reward ledger — everything grades against this one number.
**Needs a human because:** it's a business-objective decision.
**Proposed:** **inbound enquiry** (per the 2026-07-27 north star). Confirm, or name booked-call / identified-seller instead. See Open Question 2.

## [WTA-003] Approve the identity-join fix (forward distinct_id from all forms) — raised 2026-07-29 — [onsite/attribution] — status: OPEN
**Blocks:** Phase 0 — behaviour↔outcome only connects at form-submit today; `lead-signup`/`subscribe` don't forward `posthog_distinct_id`; anonymous + FB-ad leads are stranded.
**Needs a human because:** website code change + a call on whether to identify() more visitors (privacy posture).
**Proposed:** forward distinct_id from every conversion form; add a retroactive stitch where possible. Low-risk wiring. See §3.3 Gap A.

## [WTA-004] Decide whether server-side onsite personalization is in scope — raised 2026-07-29 — [onsite] — status: OPEN
**Blocks:** Phase 2 (Sphere 1). Today the site can only vary content client-side via PostHog flags; genuine per-user content is a build.
**Needs a human because:** it's a real infra investment vs. a much weaker flag-only alternative.
**Proposed:** build a server/edge personalization-decision endpoint after Phase 0/1 prove the ledger. See §3.3 Gap B + Open Question 4.

## [WTA-005] Physical-mail + outbound-call mechanism for offsite arm — raised 2026-07-29 — [offsite] — status: OPEN
**Blocks:** Sphere 3 (offsite) is theoretical until there's a repeatable way to send posted assets / place calls at the loop's request.
**Needs a human because:** requires a vendor/tool decision + budget (PostGrid for print-post, JustCall/SMS, or Will-manual).
**Proposed:** confirm which mechanisms the loop may assume exist. See Open Question 6.

## [WTA-006] Set autonomy bounds (what changes unattended vs. routes here) — raised 2026-07-29 — [meta] — status: OPEN
**Blocks:** safe operation. Especially: ad spend, GC go-live, anything public-facing.
**Needs a human because:** risk tolerance is yours to set.
**Proposed:** mirror the FB funnel rule — the loop never promotes to the Gold Coast served surface or spends beyond set caps without you; all such steps become Will-to-action items. See Open Question 7.

## [WTA-007] Verify Samantha nightly DOER (02:30) is actually cronned — raised 2026-07-29 — [meta] — status: OPEN
**Blocks:** clean governance — the infra map couldn't confirm the 02:30 DOER in the live crontab (only lead-intel/SEO-weekly/ad-lifecycle/actionlog are scheduled).
**Needs a human because:** you know whether it was intentionally moved/disabled.
**Proposed:** confirm its status so the Conductor doesn't assume a loop that isn't firing (or double-run one that is).
