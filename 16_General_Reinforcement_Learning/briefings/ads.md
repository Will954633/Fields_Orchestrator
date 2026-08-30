# ADS (Facebook + Google paid) — standing brief

**Last updated:** 2026-08-13 by Will + Samantha (first briefing session)
**Review cadence:** weekly

> This document is the domain's **authorisation envelope**, not background reading. Work
> inside §1 Direction and §4 Standing Authorisations is executed autonomously and reported
> afterwards. Work outside it is proposed and waits.
>

---

## 1. Direction — what we are doing here and why

**All ads are paused right now, deliberately.** Will is working with an advertising company;
they are producing ad copy now and will film video for Facebook and Instagram. The relaunch
happens later, on Will's signal — not on this agent's judgement.

In Will's words: *"So essentially not much or anything the ads domain agent can do until I
say otherwise."* Take that literally for anything that touches a campaign. But there is real
ANALYSIS Will has asked for in the meantime, and that work is authorised (§4):

1. **Mine the Home Owner Lead Funnel for transferable learnings.**
   `03_Facebook/Home_Owner_Lead_Funnel_Search` ran an automatic iterative FB cycle. Will
   wants to know what carries forward into the new creative.
2. **Find the lead forms that actually converted.** Will believes one, possibly two, lead
   forms converted at around **$15 per lead**. Identify them, reconstruct the exact flow,
   and describe what made them work — he may tweak and restart that flow shortly, ahead of
   the full relaunch.
3. **Prepare the landing-page tests.** When ads restart, Will wants to test traffic landing
   on (a) `/off-market` pages — the start, or specific sections — and (b) the `/yourhome`
   house mini-site. A fast-loading mini-site version is being built so users can be sent
   straight there.

## 2. Current state — what is ON, OFF, or PAUSED, and deliberately so

> ⚠ **THIS SECTION IS KNOWN TO BE WRONG AS OF 2026-08-30 AND IS AWAITING A RE-BRIEF (REC-ads-007).**
> The table below says all spend is paused. It is not: six campaigns spent **$796.08 in 14 days**
> and produced 17 lead-form submissions. Do not treat the table as an authorisation for anything.
> Freshness has deliberately **not** been reset — this brief stays `stale`/NARROWED until Will
> rewrites §1/§2/§4, because restoring full autonomy on a brief this wrong would be worse than
> the narrowing. — Samantha, 2026-W35
>
> **Will's own direction recorded since, in his words (verdict on REC-ads-005, 2026-08-24):**
> he had *"already stopped all ads himself"*; 93 Burleigh Waters (the Messenger-destination
> carousel) is *"confirmed a failure"*, matching the 0-qualified / 3-blocks finding. **Key
> learning he named: "the Facebook MARKETPLACE listing of the SAME address succeeded where the
> paid Messenger carousel failed."** A new ad was launching that day. Carry this into the
> re-brief — it is the strongest organic-vs-paid signal he has given this domain.

| Thing | State | Why |
|---|---|---|
| All ad spend | **PAUSED — Will's deliberate call** | Not a failure. New creative in production with an advertising company. |
| New creative | In production — copy now, video for FB + Instagram to follow | External agency, not this agent's work. |
| Relaunch | **Later, on Will's signal only** | Do not propose restarting spend. |
| The ~$15/lead forms | **Believed to exist — find them** | Possible early restart ahead of the main relaunch. |
| Landing-page tests | Planned: `/off-market` sections and `/yourhome` mini site | Mini site needs to load fast enough first. |

## 3. Goals — what good looks like

1. Give Will a usable account of **what actually worked** in the FB funnel, so the new
   creative starts from evidence rather than a blank page.
2. Identify and document the ~$15/lead flow precisely enough to rebuild it.
3. When spend does restart: drive down cost-per-identified-SELLER, never cost-per-lead.

## 4. Standing authorisations — SHIP THESE WITHOUT ASKING

- Analysis, attribution and cost-per-seller measurement across all historical ad data.
- Mining `03_Facebook/Home_Owner_Lead_Funnel_Search` and the FB lead-form history for
  transferable learnings, and writing them up.
- Drafting creative, angles and landing-page test plans for Will's approval.
- Writing to the RL collections and cycle docs.

## 5. Off-limits — never, regardless of anything else

Global prohibitions always apply and are never granted by a brief: spending money,
editing the crontab, editing monitoring/health-check code, contacting a real person,
deleting data, Gold Coast go-live.

- **Never create, unpause, pause, or change the budget or targeting of any campaign**, with
  the single ring-fenced exception below. All other spend is Will's, and the relaunch is on
  his signal alone.
- Do not propose restarting the main campaigns until Will says otherwise. He has already decided.

**⚠ RING-FENCED EXCEPTION — the $20/week article-test budget (Will, 2026-08-13):**
*"we could give the agent a $20 per week ad budget to test articles with."*
- **Cap: $20 per calendar week, total, across all article tests.** Not per campaign, not per
  article. Track cumulative spend and stop at the cap — do not rely on Facebook's pacing.
- Purpose is **content learning, not lead generation**: buy enough impressions to read whether
  a headline works. Expect to learn about clicks; the funnel proved clicks do NOT predict
  seller conversion (9 documented high-CTR non-converters), so never report a click winner as
  a seller winner.
- **Organic first.** Will's sequence: post to the page, see how it goes, then spend. Do not
  buy distribution for an article that has not had an organic run.
- ⛔ **This authorisation is approval-in-principle and has NOT yet been exercised.** Will said
  "we could". Before the FIRST dollar is spent, put the exact campaign — objective, audience,
  daily cap, kill rule — to him as a recommendation and get a definite yes. After that first
  approval, subsequent tests inside the $20 run without asking.
- Log every change to `system_monitor.ad_decisions` (CLAUDE.md Rule 3).

## 6. Context the agent cannot get from data

- $1,742 of FB spend has produced **0** true-reward seller conversions; every measured
  conversion was organic at $0.
- The step AFTER the ad is not instrumented: **0 of 135** appraisal records have ever passed
  `draft_ready`. Restarting spend before that works buys leads into a funnel we cannot measure.
- 2026-08-13: ads proposed posting 97 rendered reports as "leads we already paid for".
  Samantha checked — 4 of 98 have a name, two of those are `Test Pipeline` and `E2E Test`.
  Do not re-raise without re-verifying.

## 7. Open questions — Will to answer

- [ ] Budget and kill rule for the relaunch — to be set when Will signals.
- [ ] Does the posted-report step have to work before spend restarts?

## 8. Changelog

- 2026-08-13 — seeded by Samantha from measured data.
- 2026-08-13 — **first briefing session held with Will.** §1-§7 written from his words.
