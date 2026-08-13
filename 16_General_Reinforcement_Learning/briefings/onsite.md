# ONSITE (on-site conversion + experiments) — standing brief

**Last updated:** 2026-08-13 by Will + Samantha (first briefing session)
**Review cadence:** weekly

> This document is the domain's **authorisation envelope**, not background reading. Work
> inside §1 Direction and §4 Standing Authorisations is executed autonomously and reported
> afterwards. Work outside it is proposed and waits.
>

---

## 1. Direction — what we are doing here and why

The off-market surface is being rebuilt into **two versions we will A/B test**:

- **Version A — the currently deployed V4 `/off-market` page.**
- **Version B — the house mini-site (`/yourhome`)**, built and loaded on demand. The bar is
  that it builds and loads **fast enough to be used as a site link — under 20 seconds**.
  Still being worked on.

**Immediate priority: the new "download your report" section**, added to V4 on 2026-08-13.
Will is *"very keen to monitor user engagement with that feature."* Watch it closely and
report what people actually do with it. Give it roughly **another week** of observation
before drawing conclusions.

**Where this is heading.** The page likely needs more content — possibly the "process
decisions" section ported from the house mini site. And Will is thinking the **primary CTA
should become booking a call with him**, offered three ways: book an online call, one-click
request a callback, or call directly.

The hard part of that CTA is not the mechanics, it is the reason. In Will's words: *"We need
to think through user benefits of speaking with Will. How our process benefits the user using
real data and numbers. Needs to be very compelling, people don't want to speak to real estate
agents unless there is good reason."* Treat that as the design problem — a "Book a call"
button with no compelling why will fail, and failing it will look like the CTA was wrong when
the reasoning was.

## 2. Current state — what is ON, OFF, or PAUSED, and deliberately so

| Thing | State | Why |
|---|---|---|
| `/off-market` V4 | **Live default** in the three measured suburbs | Version A of the A/B. |
| "Download your report" section | **Added to V4 on 2026-08-13** | Will's immediate monitoring priority. |
| House mini site `/yourhome` | **In development** — on-demand build, target <20s load | Version B. Not ready. |
| Master kill-switch `genrl_personalization_v1` | **OFF — never flipped** | Experiments assign variants but render nothing. |
| Experiment placement | Only on `/analyse-your-home` + `/for-sale-v3` | Those fell to ~2 users/week when ads went off. |
| Primary CTA = book a call with Will | **Under consideration** | Needs the "why would I" argument built first. |

## 3. Goals — what good looks like

1. Learn what users actually do with the "download your report" section.
2. Get experiments in front of traffic that exists (545 organic users/28d on the deck and
   property pages, where the slot is not mounted).
3. Build the evidence for a compelling reason to speak with Will — real data, real numbers.
4. Surface high-intent individuals as a weekly PATTERN, not an hourly alert.

## 4. Standing authorisations — SHIP THESE WITHOUT ASKING

- Mount, unmount or move the personalization slot on any page.
- Create, serve, grade and retire experiments via `experiment_manager.py`.
- Fix telemetry, tracking and analytics bugs (e.g. the `deepest_section` fix of 2026-08-13).
- Ship reversible on-site conversion fixes and instrumentation.
- Instrument the "download your report" section and any CTA variant, and report engagement.

## 5. Off-limits — never, regardless of anything else

Global prohibitions always apply and are never granted by a brief: spending money,
editing the crontab, editing monitoring/health-check code, contacting a real person,
deleting data, Gold Coast go-live.

- **Never flip the master kill-switch `genrl_personalization_v1`** — Will's call, after
  the performance gate.
- Never contact a visitor directly.
- Do not ship a "book a call with Will" CTA until the user-benefit argument is agreed with
  him. The mechanism is easy; the reasoning is the product.

## 6. Context the agent cannot get from data

- At current traffic an experiment arm needs **~10 months** to reach N≥10 on the current
  surfaces. Any "winning arm" claim at this volume is noise — the old system graded 14 vs 11
  conversions as a 1.13x win.
- Site performance is already poor (p75 LCP measured 11-22s). Render-path changes are perf-gated.
- The `/yourhome` version is **still being worked on** — do not propose deck changes that the
  rebuild will overtake. Check its status first.
- People do not want to speak to real estate agents without a good reason. Any CTA work that
  ignores this will fail.

## 7. Open questions — Will to answer

- [ ] What has to be true before the kill-switch is flipped?
- [ ] Should the "process decisions" section be ported from the mini site to V4?
- [ ] What exactly is the user benefit of a call with Will? (Needed before the CTA ships.)

## 8. Changelog

- 2026-08-13 — seeded by Samantha from measured data.
- 2026-08-13 — **first briefing session held with Will.** §1-§7 written from his words.
