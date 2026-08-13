# ARTICLES (self-hosted content) — standing brief

**Last updated:** 2026-08-13 by Will + Samantha (first briefing session)
**Review cadence:** weekly

> This document is the domain's **authorisation envelope**, not background reading. Work
> inside §1 Direction and §4 Standing Authorisations is executed autonomously and reported
> afterwards. Work outside it is proposed and waits.
>

---

## 1. Direction — what we are doing here and why

Articles are a **reader-engagement and lead tool**, not a publishing quota. Will's direction:

- **Iterate the content.** Articles are not fire-and-forget; existing ones get improved.
- **Write what we know works.** Brain data and past Facebook performance already show which
  angles landed. Query them before inventing a topic — this is evidence we already own.
- **Rank #1.** Almost nobody writes about the southern Gold Coast at suburb level. Will:
  *"We don't compete with others here."* A local-query article that is not #1 is a defect.
- **Educate the reader on what Fields does, and give them somewhere to go next.** Will's
  model is McKinsey: articles carry sections that educate and then route the reader to the
  commercial offering. Every article should leave the reader knowing what Fields is and with
  a reason to click deeper.
- **Google News eligibility** is the medium-term target.

**Work with the SEO domain.** SEO will send you evidenced notes (query gaps, titles losing
clicks, topics worth extending). Read them at cycle start and reply the same way:

```bash
python3 conductor_state.py directives --domain articles     # includes from:seo notes
python3 conductor_state.py directive --domain seo --from articles --text "<...>"
```

## 2. Current state — what is ON, OFF, or PAUSED, and deliberately so

| Thing | State | Why |
|---|---|---|
| Publishing | **NOT paused** — publishing is expected | Will: *"publishing is not paused, we should have published articles this week?"* |
| Recent output | Articles published in the last two weeks, but **there have been workflow errors** | The gap is a pipeline failure, not a decision. Investigate it. |
| Approval | Every article still needs Will's explicit yes before going live | 2026-07-29 rule, still standing. |
| Approval mechanism | **BUILT 2026-08-13** — `article_approval.py` + `article_revise.py` | Drafts go to Telegram with YES/NO buttons AND a live preview link. A NO now triggers an automatic revision against Will's feedback and RE-PROPOSES — capped at 3 rounds, then parked `needs_human`. |
| Authorship | **ALL articles authored by Will Simpson** (Will, 2026-08-13) | Was 73 'Fields Research' / 26 'Will Simpson'; corrected corpus-wide to `author='Will Simpson'`, `author_slug='will'`. |
| QLD licence number in disclaimers | **4832972** — corrected corpus-wide 2026-08-13 | 68 articles (40 published) carried **4832971**, wrong by one digit. Recurrence of a 2026-06-21 fix that only corrected 3 website pages. ⚠ The GENERATOR still produces it — 28 of the 68 were created in Aug 2026. Source not yet found. |
| 15 how-it-sold drafts | Exist; format ranks page-1 for exact-address queries | Awaiting Will. |

## 3. Goals — what good looks like

KPIs Will attached to this domain:
1. **Optimise existing articles** — iterate, don't just add.
2. **Increase engagement** and **increase return-user behaviour**.
3. **Rank #1** (or at least highly) for search terms related to each article.
4. Become a **strong source of website traffic**.
5. **Educate each reader on what Fields does**, and get them clicking onward.
6. Move the library towards **Google News eligibility**.

## 4. Standing authorisations — SHIP THESE WITHOUT ASKING

- Topic research, drafting, and rewriting/optimising the body of EXISTING published articles
  where it serves the goals above (titles/metas coordinate with seo).
- Retiring dead topics.
- Fixing slugs, metadata, internal links and on-page structure.
- Querying Brain 1/2/3 and past Facebook performance for what has worked.
- **Investigating and reporting the publishing workflow errors** that stopped this week's
  articles going out.
- Sending evidenced notes to seo via `--from articles`.
- **Proposing drafts for approval**: `python3 scripts/article_approval.py propose --id <article_id>`.
  Will taps YES/NO in Telegram; a poller publishes or records his reason. **Read
  `will_feedback` on any rejected article before redrafting it** — that field is the
  clearest statement of what he wants, exactly like a recommendation verdict.
- **Revising a rejected draft**: `article_revise.py --id <id>` runs automatically on rejection.
  You may also run it by hand. It never publishes — Will's tap is still the only way live.

## 5. Off-limits — never, regardless of anything else

Global prohibitions always apply and are never granted by a brief: spending money,
editing the crontab, editing monitoring/health-check code, contacting a real person,
deleting data, Gold Coast go-live.

- **Never publish a new article, or take one live, without Will's explicit approval.**
  This stands regardless of anything else in this brief (Will, 2026-07-29). Optimising an
  already-published article is allowed; making something newly public is not.

## 6. Context the agent cannot get from data

- 53 articles published, **0 conversions**, ~9 sessions, ~20 GSC impressions. Volume has not
  worked. Assume the format, topic selection or onward-routing is wrong rather than the cadence.
- Two distinct workflows exist and must not be confused: PUBLIC sold-home articles vs
  OWNER-SUBJECT direct-mail assets (memory `two_article_workflows_public_and_posted`).
- Editorial rules (CLAUDE.md Rule 5) bind everything: no advice, no predictions, comparable
  ranges not single valuations, cite source and period, forbidden words.
- The McKinsey pattern Will referenced is the model for onward routing — educate, then offer.

## 7. Open questions — Will to answer

- [ ] Publish the 15 how-it-sold drafts?
- [x] Telegram approve/reject-with-feedback flow — **approved and built 2026-08-13.**

## 8. Changelog

- 2026-08-13 — seeded by Samantha from measured data.
- 2026-08-13 — **first briefing session held with Will.** §1-§7 written from his words.
