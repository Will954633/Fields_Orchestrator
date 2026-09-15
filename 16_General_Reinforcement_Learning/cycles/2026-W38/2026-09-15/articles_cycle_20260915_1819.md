# ARTICLES cycle — 2026-09-15 18:19 AEST

**Briefing tier:** `current` (updated 2026-09-13, 2 days old) → **full standing authorisations applied.**
**Market Context Engine:** latest briefs 2026-09-06, **9 days old** — inside the ~16-day tolerance. Next refresh 2026-09-20.
**Recommendations:** proposed **none**. Withdrew REC-articles-009 (resolved). Ledger now **0/2**.
**Graded:** nothing was due (`due-for-grading` empty; REC-002/003 grade 2026-09-20).

---

## 1. What changed in my area since last cycle

From `fix_digest.py --days 8 --domain articles` (42 of 117 entries matched). Two things
directly answered open questions in my own brief, so I did **not** re-raise them:

- **`[ARTICLES-FB-RANKING-AND-RETURN-ATTRIBUTION]` (03:20 today)** — both §7 open questions
  were built overnight. FB ranking moved off dead organic `post_clicks` onto
  `fb_organic.fb_referral_sessions`, and a **RETURN BY ARTICLE** block was added to the
  `Attr · Return` tab. That second one is what made this cycle's central finding visible.
- **`[ARTICLE-PERF-CRON-CD-AND-HEARTBEAT]`** — the 15-day-dead feedback loop is live again,
  so the numbers below are current rather than frozen at 2026-08-29.

Also landed: `[EDITORIAL-VALUATION-DESYNC-DURABLE-LINK]` (step 123). I found a hole in it —
see §4.

---

## 2. The numbers, with denominators

### Corpus (`articles_signal.py`)
103 articles · **47 sessions** · 2,294 impressions · 41 clicks · CTR 1.8% · **0 converters**.

⚠ **0 converters still carries no information.** At the site organic base rate (18 conv /
1,262 users = 1.4%), 47 sessions predict 0.67 conversions; observing zero has p≈0.51. This
remains a **traffic** problem, not a conversion problem. I am not re-litigating it.

### Yield per article, by format (n=101 published)
| format | n | impr/article | sessions/article |
|---|---:|---:|---:|
| major-projects | 5 | 91.2 | 2.40 |
| market-intelligence | 10 | 23.7 | 1.40 |
| watch-this-sale | 14 | 25.8 | 0.07 |
| how-it-sold | 42 | 17.5 | 0.36 |

The demand-attached ranking holds, and `major-projects` is still **n=5 with one article
carrying most of it** — directional, not statistical. This is the evidence behind the
brief's "Coomera Connector" do-now target.

### ⭐ The return engine is the `/news` hubs, not articles (Engagements tab)
New RETURN-BY-ARTICLE block, 60-day window, **n=60 returner journeys, 21 content-page returners**:

| came back to | returners |
|---|---:|
| `/news/robina` | 8 |
| `/news/varsity-lakes` | 5 |
| `/news/burleigh-waters` | 4 |
| *four individual articles* | 1 each |

**17 of 21 content returners came back to a suburb hub; 4 came back to an article.** Return
viewers are now my primary metric, and the hubs are what produce them. This is a **ranking
signal on thin volume**, not a rate — but it is the clearest steer I have, and it changed a
decision this cycle (§3).

The one article that both attracted *and* triggered a return is a how-it-sold piece
(`sold-in-10-days-how-31-roundelay-drive…`). Consistent with the brief: the subject is right,
the SEO-stub treatment is what failed.

### ⚠ Facebook brings the people; Search brings the readers
| week | FB/IG visitors | FB/IG engaged (30s+) | Search visitors | Search engaged |
|---|---:|---:|---:|---:|
| wk 24 Aug | 181 | 24 (13%) | 122 | 39 (32%) |
| wk 31 Aug | 192 | 18 (9%) | 154 | 46 (30%) |
| wk 7 Sep | 176 | **1 (0.6%)** | 132 | 49 (37%) |

FB/IG delivered **more visitors than Search every week** and almost none of the reading. The
wk-7-Sep collapse coincides with the walkthrough reel campaigns going live
(`walkthrough_reel_*_sep26`, 171 video-shown, **13 reaching 75%**, 8 completing). The reel
traffic arrives, the walkthrough autostarts, and it leaves.

This matters because the brief tells me the FB channel is where our biggest-ever piece won,
and that our per-article FB measurement is nearly blind. I am flagging the mechanism, not
claiming it: one week, and the 0.6% could be an attribution artefact of the campaign
landing path rather than real behaviour. **Not mine to fix** — sent to `onsite` (§6).

⚠ wk 14 Sep is a **partial week** (1 day) — every drop in that column is an artefact, and I
have ignored it throughout.

---

## 3. Analysis — the mechanism I think is at work

The brief's thesis is that the bond forms through **return**, not reach. This cycle's data
says the *format* that produces return is the **standing, updating hub**, not the one-off
article. That is mechanically sensible: a hub has a reason to be revisited (the numbers
moved), an article does not (you already read it).

That reframes what articles are *for*. An article's job is not to be returned to — it is to
be the thing that **introduces someone to a hub they will return to**. That is precisely the
McKinsey pattern the brief asks for, and it was completely unimplemented: the corpus had
**two internal links in total** (§4).

It also explains the Facebook picture without needing the measurement gap to be the whole
story. FB sends reach to a dead end; Search sends intent to a dead end. Both leak. The hub
link is the cheapest available fix for both, and it costs no new content.

---

## 4. What I did autonomously

**(a) Corrected 10 live pages that told readers a priced listing had no price.**
`[EDITORIAL-PRICE-ABSENCE-DESYNC]`. 58 false strings across 10 published `/property` pages —
`headline`, `meta_title`, `verdict`, `insights[]`, `faqs[]`, `cta_valuation.hook`. Oldest
had been live-false **43 days**. Verified as Googlebot before and after; post-fix sweep = 0.
Also fixed 2 not-yet-live docs that would have published the same falsehood. Applied the
absence-framing rule (delete the absence clause, lead with the evidence), kept comparable
ranges, and ran the Seller Test on every headline — no adjudication of a named vendor's ask.

The brief told me to expect **1** false title. The live-Googlebot audit that produced that
number was correct about `<title>` tags but only looked at titles; the same falsehood was
sitting in body copy on nine more pages. **Checking the layer you were told about is not the
same as checking the page.**

**(b) Closed the hole that let it happen** — extended step 123 `editorial_valuation_sync.py`
with a `price_contradiction` severity. Step 123 gates every check on
`generated_at` vs `valuation_data.computed_at`, and **publishing a price guide never advances
`computed_at`** — so this entire class was structurally invisible to the detector shipped to
prevent exactly this. New check runs *before* the desync gate. Placeholder-aware, so genuine
"Auction"/"Contact Agent" absence framing is untouched (QLD POA s216(2)(c) bars a guide on
auction listings — the absence is lawful, not concealment).
**Rule 7b discipline:** a detector that reports zero because everything is fixed is
indistinguishable from one that is broken, so I replayed the pre-fix backup through it —
**10/10 fire**, five unpriced negative controls stay silent, positive and audit-field
controls correct. Pushed `5e0353a`.

**(c) Gave all 101 published articles somewhere to go.** `[ARTICLES-NO-ONWARD-ROUTING]`.
1 of 101 linked to the funnel; the corpus held **2 internal links in total**. Added a light
"Keep reading" link to the relevant `/news` hub — 26 Robina, 19 Burleigh Waters, 13 Varsity
Lakes, 43 Gold Coast. 101/101 present, 0 duplicates, all 4 hubs 200 as Googlebot, live render
confirmed (articles are DB-served, no deploy needed).

I routed to the **hubs, not the address funnel**, on §2's evidence, and kept it a "keep
reading" link rather than a CTA because the playbook is explicit that overt CTAs trigger
persuasion-knowledge and discount goodwill from prior pieces.

**This had been raised twice as a recommendation (REC-007, REC-009b) and done neither time.**
It was always inside my standing authorisation to optimise existing published articles. That
is the §7 failure mode the contract warns about, and it is why I executed instead of asking.

**(d) Proposed 3 story drafts for Will's approval** (at the 3/day drip cap), per the conductor
ruling — which I then closed. Ranked on the **$3.465M winner's actual mechanic — a big gap
over a SHORT hold** — not on gap alone, because a large multiple over 39 years is just
inflation and is not striking:
- `#A2E4` **12 Sittella Crescent** — $1,775,000 → $2,400,000 in **fifteen months**. The
  closest structural analogue to the winner, and counter-narrative in a market the briefs
  say has fallen five months straight.
- `#372F` **14 Maitland Street** — $119,000 (1987) → $2,125,000. Biggest gap ($2,006,000)
  and multiple (17.9×); the long-arc framing is the most shareable of the batch.
- `#4202` **Varsity Lakes** — $699,000 (2011) → $1,706,000.

**(e) Rule 5 body gate on the whole batch** — 14/15 clean; fixed the 15th (unevidenced causal
claim, an advice-shaped CTA, `$1.25M` shorthand, and a line adjudicating a vendor's pricing).
Batch now 15/15.

**(f) Posted 2 published articles to Facebook** — `will-the-gold-coast-fall-too` and
`renovation-premium-gold-coast`, chosen against the 2026-09-06 sentiment brief (five straight
monthly national falls; house-price expectations at a three-year low). Deliberately **not**
bulk-posting the other 98: the playbook says the exposure curve peaks ~36 and then declines,
and the conductor said don't flood. A third was **refused by the editorial gate** — see §6.

---

## 5. What I proposed, and why nothing

**Nothing, and the ledger is now empty (0/2).** A quiet week on recommendations is a success
per §4, and this was not a quiet week on work.

- Both §7 open questions were **built overnight** — re-proposing them would have spent Will's
  attention on solved problems.
- The one genuine direction question this cycle raises — *should article effort feed the
  `/news` hubs rather than standalone pages?* — rests on **21 content-page returners**. Will
  briefed this domain **two days ago**, and his brief already states the volume is thin and the
  signal is a ranking, not a rate. Proposing a direction change on n=21, 48 hours after a
  briefing session, would be poor judgement. I acted on it where I was allowed to (the hub
  links) and will bring it back **with a measured before/after** if the return numbers move.

**Withdrew REC-articles-009.** Part (a) was answered in the 2026-09-13 briefing; part (b) I
executed myself this cycle. Nothing in it still needed a decision.

---

## 6. Coordination

- **→ `seo`** (directive `6aa9032d`): `/articles/comparing-median-house-prices` is titled
  *"Why you should be careful comparing median house prices"*. The FB composer's Rule 5 gate
  **refuses to post it** — "you should" trips the no-advice rule — so **the one article with a
  live Will walkthrough attached cannot reach the channel where our content actually wins.**
  I judged this spirit-vs-letter (advice about reading a statistic, not about transacting) and
  did **not** unilaterally retitle a ranking page with a walkthrough on it. Asked seo whether
  the URL holds rankings a title change would risk.
- **→ `onsite`** (below): the FB engagement collapse in §2 is a landing/friction question, not
  a content one.
- **Read, not duplicated:** the `from:seo` note on `seo_landing_performance` `dims` tagging —
  `articles_signal.py` and `article_performance.py` were both already updated by seo, so my
  numbers are on the corrected basis.

---

## 7. The open question I would most like answered next week

**Facebook sends us more people than Google and almost none of the readers — is that a
landing-page problem we can fix, or is FB structurally a reach-only channel for us?**

Three weeks: 549 FB/IG visitors → 43 engaged sessions (7.8%). 408 Search visitors → 134
(32.8%). If the FB half is fixable, it is the largest single lever available to this domain,
because FB is *already* delivering the volume and is the channel where the ~7,000-view piece
won. If it is not fixable, then the brief's "find the next $3.465M story" goal needs a
different distribution plan than "post it to the page", and I should know that before I spend
15 story drafts finding out.

What would settle it: for the `walkthrough_reel_*_sep26` cohort specifically, do sessions that
land on a `/news` hub engage at the Search rate or the FB rate? That separates "wrong
audience" from "wrong landing".

---

## Appendix — verification trail

| claim | reproduce |
|---|---|
| 10 live-false pages, 58 strings | multi-layer sweep over `ai_analysis`, joined to `price`; backup `absence_backup_20260915.json` |
| live-false confirmed + fixed | Googlebot fetch of `/property/<slug>`, before and after |
| detector fires | replay of pre-fix backup through `_price_contradictions` — 10/10, 5 negative controls silent |
| return engine | `python3 scripts/engagement_funnel_to_sheet.py --dry-run` → `Attr · Return` → RETURN BY ARTICLE |
| per-format yield | `python3 articles_signal.py` |
| base rate / power | `python3 reward_ledger.py` — 18 conv / 1,262 users |
| routing applied | 101/101 `news-hub-link`, 0 duplicates; 4/4 hubs HTTP 200 |
| Rule 5 batch gate | forbidden-word / advice / prediction / `$Xm` regex over all 15 drafts |
