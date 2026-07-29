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

## [WTA-003] Build the reward ledger + milestone map + identity-join fix (Phase 0) — raised 2026-07-29 — [foundation] — status: OPEN
**Blocks:** everything — nothing can learn until this exists.
**Needs a human because:** website code change (forward `posthog_distinct_id` from ALL conversion forms, incl.
`lead-signup`/`subscribe`) + a call on identifying more anonymous visitors (privacy posture).
**Proposed:** extend `lead_worklist` → action→outcome ledger w/ channel/referrer/content attribution; stand up
milestone map cold-started from the FB laws; forward distinct_id everywhere + retroactive stitch. Direction
approved in principle; this tracks the actual build sign-off. (§13 Phase 0)

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
