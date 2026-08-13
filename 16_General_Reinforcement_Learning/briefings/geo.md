# GEO / AI-channel — standing brief

**Last updated:** 2026-08-13 by Will + Samantha (first briefing session)
**Review cadence:** weekly

> This document is the domain's **authorisation envelope**, not background reading. Work
> inside §1 Direction and §4 Standing Authorisations is executed autonomously and reported
> afterwards. Work outside it is proposed and waits.
>

---

## 1. Direction — what we are doing here and why

**AI is a real priority — not a watching brief.** Will's four requirements:

1. **We come up for the main AI searches**, including *"best real estate agent [suburb]"*.
2. **AI describes Fields accurately.** This is the critical one. Not long ago **ChatGPT did
   not know Fields sells houses** and described us as a data agency. In Will's words: *"thats
   a critical error."* Fields is a **licensed** real estate agency (Will holds a full QLD
   licence, confirmed 2026-08-13) that sells houses and happens to be exceptional at
   data — not a data company. Any AI surface saying otherwise is a defect to
   be measured and corrected.
3. **We get referrals from AI.**
4. **AI ranks us highly as a trusted source of data, and prefers us as a trusted and highly
   regarded real estate agent.**

Treat (2) as the foundation: being cited often but described wrongly is worse than obscurity,
because it actively tells sellers we are not in the business of selling their home.

## 2. Current state — what is ON, OFF, or PAUSED, and deliberately so

| Thing | State | Why |
|---|---|---|
| Bing + Copilot referrals | **ZERO for 20 consecutive days** since 2026-07-23 | 488 impressions the prior week. Bingbot still crawls normally — serving/indexing, not crawling. |
| Geo-block edge function | Shipped 2026-07-21 | 403 + noindex to non-AU/NZ IPs while exempting crawlers by user-agent — cloaking-shaped, and Bing polices that harder than Google. Prime suspect. |
| Bing index count | 2,247 → 1,998 (−11%) | Falling while crawl rate held flat. |
| How AI describes Fields | **Known to have been WRONG** (ChatGPT: "data agency") | Critical. Must be measured, not assumed fixed. |

## 3. Goals — what good looks like

1. Fields appears for "best real estate agent [suburb]" and similar AI queries.
2. **AI describes Fields accurately as a real estate agency that sells houses.**
3. Measurable AI referral traffic.
4. AI treats Fields as a trusted data source AND a trusted agent.

## 4. Standing authorisations — SHIP THESE WITHOUT ASKING

- `llms.txt`, robots directives for AI crawlers, and crawler allowlist entries.
- IndexNow and Bing submissions; recrawl requests.
- Structured data and entity markup that affects how AI systems describe us.
- **Diagnosing serving and indexing regressions**, including the Bing cliff — investigate
  fully and report; the fix itself depends on the cause (see off-limits).
- Periodically querying AI surfaces to check how Fields is being described, and recording it.

## 5. Off-limits — never, regardless of anything else

Global prohibitions always apply and are never granted by a brief: spending money,
editing the crontab, editing monitoring/health-check code, contacting a real person,
deleting data, Gold Coast go-live.

- **Never change the geo-block edge function unilaterally** — it is site-wide and affects
  every visitor. Diagnose it, evidence it, propose the change.
- Never change public page copy without coordinating with seo (one writer per lever).

## 6. Context the agent cannot get from data

- AI/Bing traffic historically converted well per journey, but on **2 conversions**. Do not
  size the loss from it.
- The geo-block exists for a real reason. Any fix must keep legitimate crawlers working —
  see memory `geoblock_crawler_allowlist`, where a mistake causes silent de-indexing of the
  whole Google family.
- Bing is **0.54% of Australian mobile search**. Its direct traffic value is small; its value
  here is as an AI-surface signal, not a traffic channel.
- The claim that Bing Places feeds Copilot/ChatGPT is vendor talking-point with no Microsoft
  source, and OpenAI now runs its own crawler. Do not build a plan on it.

## 7. Open questions — Will to answer

- [ ] May the geo-block serve a normal page + region notice to overseas IPs instead of 403+noindex, if it is the cause?

## 8. Changelog

- 2026-08-13 — seeded by Samantha from measured data.
- 2026-08-13 — **first briefing session held with Will.** §1-§7 written from his words.
