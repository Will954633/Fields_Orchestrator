# Articles Cycle #3 — The Rule 5 gate had never been shown an article

**Cycle stamp:** 20260813_1856 (Brisbane) · **Domain:** articles · **Cadence:** weekly (cron)
**Prior cycle:** `cycles/2026-W33/2026-08-13/articles_cycle_20260813_1342.md`
**Briefing tier:** `current` (updated today, 0d old) — **full standing authorisations applied.**

---

## 1. What changed in my area since last cycle

`fix_digest.py --days 8 --domain articles` — this domain had a very busy day before I woke up.
Seven entries dated today touch articles directly: `[ARTICLE-TELEGRAM-APPROVAL]`,
`[ARTICLE-REVISE-LOOP]`, `[TELEGRAM-INLINE-BUTTONS]`, `[ARTICLE-PUBLISH-NO-DEPLOY]`,
`[ARTICLES-JSON-STALE-AUTHOR]`, `[ARTICLE-LICENCE-WRONG-CORPUS]`,
`[ARTICLES-CONTINUOUS-AUTONOMY]`. I also inherited a brand-new standing brief and
`ARTICLES_PLAN.md`, both written today.

The chain state showed `forced_stop_barren` — two consecutive chained sessions produced no
artefact. So the correct posture this cycle was to **do work, not to analyse further**. The
ledger was at 1/2, and contract §7 is explicit that being at cap should make me do more
myself, not less.

Nothing due for grading (no shipped items yet). No conductor directives open. No
recommendation feedback yet — Will has not decided anything in this domain.

---

## 2. The numbers, with denominators

`articles_signal.py`, window to 2026-08-13 — unchanged from cycle #2 five hours earlier,
as expected:

| Metric | Value |
|---|---|
| Published articles | 73 |
| Sessions (all articles) | 12 |
| Converters | **0** |
| GSC impressions | 126 · clicks 1 |

**I did not re-analyse topic performance this cycle.** Cycle #2 did that properly five hours
ago and nothing has moved; repeating it would have been the manufactured-productivity failure
the contract warns about. The numbers below are the ones this cycle actually produced.

### The number that matters this cycle

| | Before | After |
|---|---|---|
| Published articles passing a **body-level** Rule 5 scan | **59 / 73** | **73 / 73** |
| Whole corpus (published + drafts) | 82 / 100 | **100 / 100** |
| Known false positives, each with a written reason | 0 (unexamined) | 8 |

---

## 3. Analysis — the mechanism

**`ARTICLES_PLAN.md` told me there were two live editorial breaches, "found by the Rule 5
gate across 73 published articles (71 pass)". There were fourteen.**

The gate is real and reasonably written. It lives inside `scripts/fb_post_article.py`. But it
is only ever *called* on the composed Facebook post — a title plus a one-line excerpt. It has
never in its life been handed an article body. So "71 of 73 pass" was a true statement about
73 **headlines**, presented as a statement about 73 **articles**. The two breaches it did
catch were in text short enough to fall inside an excerpt window; that is the entire reason
those two and not the others.

The worst thing it could not see was a live section of `leading-vs-lagging-indicators` headed
*"Practical Application: A Simple Monitoring Framework"*, containing:

> "**Step 4: Act on Leading Indicators** — See wage acceleration? **Start your property
> search now**" · "If both rising: **Strong buy signal**" · "If wages are plateauing,
> **consider listing sooner rather than later**" · "Strong wage growth equals **sell into
> strength**" · "**Make buy/hold/sell decision** based on trends"

Rule 5's no-advice rule is the one with an explicitly stated liability rationale, and this is
a licensed agent's website telling readers when to buy and sell property. It has been public
since the article went up.

**The mechanism, stated generally: a check reported PASS over a surface it was never given.**
That is the same failure shape as Rule 7b (a job reports success having done nothing) and
Rule 8 (a zero result is a fact about the question, not the world). In all three the output
of a healthy-looking check is indistinguishable from the output of a check that never ran.
Rule 7b's phrasing fits exactly: *a clean result must assert that something was examined, not
merely that nothing threw.*

**Why the plan's figure was believable.** The plan was written today by a session that had
just built a great deal of genuinely working machinery. It cited a real gate, a real count,
and a real pass rate. Nothing about it looked like a guess — which is why I checked it rather
than inherited it, and why I have written the reason into the plan for whoever reads it next.

**On the licence number, a second scoping error of the same family.** Three passes have now
corrected this number (2026-06-21, 2026-08-13 corpus, this one). The first two fixed
*instances*; the plan concluded the source was "not in the automation repo" and hypothesised
the model was reproducing the wrong number from our own older articles — a self-reinforcing
loop, which is an interesting theory and was wrong. It was hardcoded in a string literal at
`push_to_ghost.py:125`. The earlier search had looked for a *config value*.

And because the symptom showed up in articles, every prior pass searched articles. A
filesystem-wide search for the literal found two live emitters outside that surface,
including three seller-facing landing pages that say **"You can verify on the Office of Fair
Trading register"** next to a number that fails that check. That is the one I would most want
found before a seller tried it.

---

## 4. What I did autonomously

All of this sits inside §4 of the brief (rewriting/optimising existing published articles;
fixing on-page structure; investigating publishing workflow errors) or is a bug defeating the
brief's stated intent, which §7 says to fix rather than propose.

1. **Built `scripts/editorial_gate.py`** — the Rule 5 rule set run over full article bodies,
   printing the surrounding sentence for every hit. Two false-positive classes are suppressed
   *structurally* rather than by loosening the rules: a prediction inside its own disclaimer
   ("…a historical relationship, **not a forecast**"), and shorthand at project scale (`$450M`
   tower, `$5.75B` rail — Rule 5's number format is about property prices; floor set at
   $20,000,000, above any residential sale in this market).
2. **Corrected all 14 breaching published articles**, including a full rewrite of the
   `leading-vs-lagging-indicators` "Practical Application" section into observational framing
   (where the ABS series are published; what the data showed historically; an explicit note
   that a lead observed in past data may not hold), and the "Action" column of
   `what-drives-gold-coast-house-prices` into "What the data showed historically".
3. **Listed the 8 surviving false positives in `ACKNOWLEDGED` with a written reason each**, so
   the gate exits 0 on a genuinely clean corpus. A gate that always reports the same seven
   breaches is one everyone learns to ignore, and the next real breach lands in that noise.
4. **Wired the gate into `article_approval.py propose`** — it now *refuses* to put a draft in
   front of Will if the body fails, rather than warning. Verified by import and `--help`
   without sending anything to Telegram.
5. **Found the licence-number source** (P5) and fixed all three live emitters: the generator,
   the three `/launch/` pages, and `launch-form.mjs`. Build gate passed; pushed as **one**
   batched commit via `push_website_files.py` (1 Netlify build, md5-verified); **verified live**
   — all three pages now serve `4832972`.
6. **Closed P4 and P5 in `ARTICLES_PLAN.md`**, each with the scoping error that hid it written
   down rather than just a tick.
7. Logged everything to `system_monitor.rl_articles_actions`; two fix-history entries
   (`[ARTICLE-LICENCE-GENERATOR-SOURCE]`, `[EDITORIAL-GATE-NEVER-READ-BODIES]`).

**Published nothing.** Every article needs Will's explicit approval.

---

## 5. What I proposed

**REC-articles-002**, superseding REC-articles-001. Same ask — publish the 15 how-it-sold
drafts — because the ranking evidence is unchanged and good. It supersedes rather than sits
alongside because **I had to correct something I told Will**: cycle #2 described all 15 drafts
as "Rule 5 clean", which was measured with the headline-only gate. Three had never had their
bodies read and one (`13 Waitara Place`) carried `$1.5M–$1.65M` shorthand. Fixed; all 15 now
pass the body-level gate; and `article_approval.py` can no longer let that class reach him.

Ledger still **1/2**. I am deliberately holding the second slot: the obvious candidate is an
in-article bridge to `/analyse-your-home`, and it is worth more designed against real
address-query readers than against a hypothesis.

**Graded:** nothing — no shipped items exist yet.

**Nothing else was proposed**, and there is nothing I found and left untouched. The one thing
I chose not to do is retitle the two "Is Now a Good Time to Sell in X?" articles, whose titles
are advice-shaped questions. That is a title change, and §1 of the brief says titles coordinate
with seo — so it belongs in a note to that domain, not in a unilateral edit.

---

## 6. The open question I most want answered next week

**Unchanged from cycle #2, and deliberately so: does an address-query article session ever
reach `searched_address`?** This cycle did not touch it. It removed the compliance risk
sitting on the corpus that the how-it-sold format is being added to — necessary, and it was
live, but it is not progress on whether any of this converts.

The new question underneath it: **what else in this domain is measured by a check that was
never shown the thing it claims to check?** Two of today's three findings were that shape.
`article_performance.py` and its `evidence_grade` field are the obvious next place to look,
because everything I will argue from next cycle rests on them.
