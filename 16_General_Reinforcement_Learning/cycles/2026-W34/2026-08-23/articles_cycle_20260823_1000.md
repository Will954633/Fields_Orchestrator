# ARTICLES CYCLE — 2026-08-23 10:00 AEST

**Briefing tier:** `aging` (10d, updated 2026-08-13) — full standing authorisations apply.
**Open recommendations at start:** 0. **At end:** 1 (REC-articles-004).
**Graded:** nothing due.

---

## 1. What changed in my area since last cycle

`fix_digest.py --days 8 --domain articles` returned 36 entries. The ones that bear on
this cycle:

- **[AGENT-LISTING-DISPARAGEMENT]** (2026-08-20) — gated `ai_analysis` on
  `status === 'published'` across three endpoints after 42 live listings leaked
  unpublished editorial, 16 of it naming the listing agent. **It missed two things, and
  both were still live today.** See §3.
- **[ENVELOPE-FALLTHROUGH-MINISITE]** (2026-08-19) — the mini-site published valuations
  the engine had refused. Same defect, third surface, found again today on `/property`
  and `/for-sale-v3`.
- **[ARTICLE-NO-ROUTE-TO-REWARD]** (2026-08-16) — my own last cycle. Not yet gradeable.

**One open conductor directive**, from `seo`: a Rule 5 breach live on `/for-sale-v3` —
single-property valuation figures in generated editorial, two of them in headline fields.
Explicitly handed to me as the editorial owner, explicitly not proposed to Will because
"it is a defect against a rule we already hold ourselves to." Agreed. That directive is
what this cycle became. Closed.

---

## 2. The numbers, with denominators

`articles_signal.py` — **100 articles, 17 sessions, 0 converters, 237 impressions,
3 clicks (CTR 1.3%)**. Up from 53 articles / 9 sessions in the brief; conversions still 0.

| topic | articles | sessions | sess/article | impressions |
|---|---|---|---|---|
| major-projects | 5 | 11 | **2.20** | 28 |
| how-it-sold | 42 | 4 | 0.10 | 153 |
| watch-this-sale | 14 | 1 | 0.07 | 44 |
| seller-strategy | 7 | 0 | 0.00 | 3 |

`major-projects` is 5% of the library and **65% of the sessions**. At n=11 sessions that
is directional, not significant — but it is the only topic signal that has survived three
cycles, and it points away from the property-level formats that make up 56 of 100 articles.

`reward_ledger.py` — 809 users, 931 sessions, 10 conversions, base rate 0.012.
`submitted_address` remains the reward at 54× lift (n=10). Organic Search 681 users,
9 conversions.

**The Facebook page trial from last cycle — answered, and it is not about format.**
Both articles posted 2026-08-16 returned `post_clicks: 0`. The number that matters is
`post_fan_reach: **1**`. Every record in `fb_page_posts` back to 2026-03 shows a fan reach
of 1–4 (n=18 posts). The open question was *"is the constraint distribution or format?"*
It is distribution, absolutely: **at a reach of one, no format can be tested.** I will keep
posting published articles because the brief instructs it, but I am retiring the idea that
these posts measure anything about content.

---

## 3. What I did autonomously, and the mechanism

The seo directive reported 11 Rule 5 occurrences on the feed. Re-running the repro found
**17**, including `first_offer_advice` — *"Do not accept anything below $1,880,000"* — which
is not a formatting problem, it is advice, which Rule 5 forbids outright. That discrepancy
is what made me widen the scan, and the widening is where the real finding was.

**Three gaps, all server-side, all downstream of one root defect.**

**(a) The public property API served the editorial pipeline's private workings.**
`property.mjs` gates `ai_analysis` on `status === 'published'` — the 2026-08-20 fix — and
then returns the **whole object**. So every `_`-prefixed working field went with it:
`_draft1` (pre-fact-check copy), `_reflection` (self-critique), `_backfill_data` and
`_agent_briefings` (verification notes that name Domain, onthehouse and CoreLogic — which
public copy must never do) and, on 10 listings, `_factcheck_failures`: the claims our own
fact-checker rejected. **All 71 live published listings. 1,374,315 characters. Zero
frontend consumers.** The previous fix gated on status; it did not gate on field name.

**(b) The decision feed shipped the seller-only positioning tier.**
`decision-feed-v3.mjs` passed `positioning_analysis` through raw, `gated` tier included —
`pricing_strategy`, `negotiation_positioning`, `first_offer_advice`, `agency_recommendation`
— on other agencies' listings. Nothing in V3 reads it; the fields the feed renders were
already extracted server-side. It was dead weight carrying most of the breaches.

**(c) The root defect: editorial is generated once and never revalidated.**
Every breaching editorial was written 2026-07-20/21 and never re-read, while asking prices
moved and valuations recomputed underneath it (bands measured 2026-08-08). 21 Misty Court
published comps of *"$1,023,000 to $1,173,000"* against a current band of
$1,283,080–$1,606,741. **Four listings were arguing from a valuation the engine has since
suppressed** (`directional_only`, above the $1M–$2M design envelope) **or dropped**
(`confidence: not_available`) — 185 Easthill quoting it to the dollar,
*"this site's reconciled model ($1,205,403…)"*.

The Rule 5 breaches are symptoms. (c) is the disease.

### Shipped

One batched commit, two files, one Netlify build (`npm run build` passed first).

- **`property.mjs`** — `stripInternals()` drops any `_`-prefixed key from `ai_analysis` and
  `sold_analysis`. Convention over enumeration on purpose: a *new* `_field` is withheld by
  default rather than leaking until someone notices. Verified live: 24 keys → 20, no
  internals.
- **`decision-feed-v3.mjs`** — `positioning_analysis` deleted from the response, plus
  `statesSingleValuation()`, a Rule 5 assertion on `hook`/`opinionated_headline` that
  rejects a currency figure adjacent to a valuation term and falls through to the compliant
  rule-based headline. Comparable ranges are stripped before the test, so permitted copy
  passes. Payload **533,689 → 414,679 bytes** (−22%), all of it content nobody could render.
- **Data** — 66 fields across 39 listings rewritten from each document's *current* values
  (not patched, because the originals were stale as well as non-compliant), and **4
  listings unpublished to `needs_review`**. Those four had no honest patch: the whole
  argument rests on a withdrawn valuation, so regeneration is the fix, not a rewrite.
  Unpublishing is reversible and errs toward withholding.
- **`config/property_editorial_prompt.md`** — rules 9 (never state our valuation as a
  single figure; publish nothing when `directional_only`), 10 (never name a data source),
  11 (anchor claims to dated facts so they cannot go stale silently).
- **`scripts/editorial_compliance_check.py`** — standing scan of live published copy,
  `job_run` heartbeat at 24h, **raises on `scanned == 0`** (Rule 7b: an empty scan means the
  query is wrong, not the corpus clean). Seeded with one run.

**Verification:** `named_source` 8 → 0, `advice` 1 → 0, `single_valuation` 4 → 1 — and I
checked the remaining one rather than reporting it: 5 Mornington Terrace cites a
*reconciled valuation range*, which Rule 5 permits, alongside the asking price. False
positive, left alone.

### Two things I deliberately did NOT do

**38 abbreviated-currency figures remain, all in `meta_title`/`meta_description`.** My first
pass reformatted them and I reverted it. The brief says titles and metas coordinate with
`seo`, and unilaterally lengthening 30-odd SERP titles is not a compliance fix, it is an
SEO change wearing one. I fixed only the four whose metas carried an actual valuation
breach, and sent seo the list with a repro.

**I did not touch the gated tier on `/property`.** On the feed nothing rendered it, so
removing it was obvious. On the property page `PositioningCard` renders it deliberately
behind a click-to-reveal — that is a built product feature, not a bug, so it is Will's call.
It is REC-articles-004.

### A correction to my own work

My first `stale_price` check reported 17 stale listings. I spot-checked four before
reporting and two were false positives — comparable *sale* prices ("Same Street Sold for
$1,420,000") and a correctly past-tensed ask. Tightened to require an asking-price cue:
6 flagged, **4 verified genuinely wrong**, 2 not. The 4 is the number I stand behind, and
the script now carries its own precision limit in a comment so the next reader does not
repeat my error.

---

## 4. What I proposed

**REC-articles-004** — the gated positioning tier on public `/property` pages. Our
recommended asking range, negotiation buffer, first-offer advice and a **ranked agency
recommendation**, on 25 other agencies' listings, behind a `useState` reveal (so it is in
the uncredentialed API response whether or not anyone clicks). n=3 live listings.

It is a decision, not a fix, because the feature was built on purpose. But Rule 5 forbids
advice outright, and publishing a ranked agency list on a competitor's listing is the same
exposure as [AGENT-LISTING-DISPARAGEMENT], which cost a written undertaking to Tyler Benson
three days ago. My recommendation is to withhold it entirely.

**Nothing else proposed.** Everything else this cycle was covered by §1 and §4 of my brief
or was a bug defeating its stated intent, so it shipped.

---

## 5. What I graded

Nothing due. REC-002 (article sessions → ~30 by 2026-09-10) and REC-003
(`paid_avg_scroll_pct` > 20% by 2026-09-30) are both weeks out.

Last cycle's self-set claim — article → `/analyse-your-home` CTA clicks — I said a zero
would falsify nothing at 12 sessions a fortnight. Sessions are now 17 across 100 articles.
Still too thin to read; carrying it to next cycle rather than calling it either way.

---

## 6. The open question I most want answered next week

**Why is `major-projects` the only topic anyone reads?** 5 articles, 11 of 17 total
sessions, against 42 how-it-sold articles producing 4. The how-it-sold format is the one
Will approved 15 more of, and it is 42% of the library returning 0.10 sessions per article.

The honest read is that `major-projects` (light rail, infrastructure) answers a question
people already search for, whereas how-it-sold answers a question only we thought to ask.
That is testable against real query demand rather than my intuition, and it is the first
thing I would look at — because if it holds, the library is 56% invested in a format with
no search behind it, and no amount of distribution fixes that.

I did not start it this cycle: the seo directive was a live compliance breach on public
pages and it took the session. That is the one piece of named work I am carrying rather
than dispatching, and this is me saying so.

---

## 7. Housekeeping

- Contract §8 observed: no `telegram_notify.py`, no `WILL_TO_ACTION.md`, no
  `cycle_pacer.py`, no self-scheduling.
- Netlify: **1 build**, batched across both function files.
- Rule 1: fix-history entry `[EDITORIAL-INTERNALS-AND-GATED-TIER-PUBLIC]` written.
- Rule 7: `editorial_compliance_check.py` self-registers at 24h cadence and has one real
  heartbeat. **Not on cron** — crontab edits are outside this domain's authority. Handed to
  seo/ops in the directive reply; it needs a daily line after the nightly valuation
  recompute to actually close the loop.
- 5 actions logged to `system_monitor.rl_articles_actions`.
