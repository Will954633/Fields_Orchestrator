# ARTICLES — the plan, and everything you can work from

**Owner:** the `articles` domain agent. **Written:** 2026-08-13. **Status:** live plan; update it as you go.

Will asked for this on 2026-08-13, after establishing that the article generator's
self-learning loop was **closed at 0%** — it had never read a single outcome for anything it
wrote. He also granted this domain the right to **chain its own sessions** rather than wait
for the weekly cycle (see §6). You are taking over work started in that session; the
groundwork below already exists and is verified.

**Read this with `briefings/articles.md`.** The brief is your authorisation envelope and
outranks this document; this is the *how* and the *what with*.

---

## 1. What was just built for you (all verified, all live)

| Asset | What it gives you |
|---|---|
| `scripts/article_performance.py` | Nightly rollup writing measured outcomes onto **every** article — `content_articles.performance` + the `article_performance` collection. Organic sessions, GSC clicks/impressions/position, **paid read-depth**, **organic read-depth**, article-titled ad CTR, FB post clicks. |
| `system_monitor.content_hook_corpus` (92) | Every annotated ad headline joined to its measured outcome. 305,208 impressions, $2,624 spend. |
| `system_monitor.content_hook_aggregates` (60) | Weighted CTR per hook type / emotional lever / theme, with `insufficient_evidence` flags. |
| `system_monitor.content_learnings` (80) | 3 archetypes, 26 laws, 15 cautions, **36 dead angles** — machine-readable at last. |
| `scripts/article_approval.py` | Draft → Telegram with preview link + ✅/✏️ buttons → publish + deploy. |
| `scripts/article_revise.py` | Will rejects with a reason → you revise → resubmit. 3 rounds, then `needs_human`. |
| `scripts/fb_post_article.py` | Post a published article to the page. Rule 5 gate built in. **Dry-run only so far.** |
| `scripts/post-performance-tracker.py` | Now collects real post insights (`post_clicks` etc). |
| `scripts/build_hook_corpus.py` · `build_content_learnings.py` | Rebuild the two corpora. Re-run when new ads or findings land. |

---

## 2. What the evidence says right now

**The distribution problem dwarfs the writing problem.**
**60 of 100 articles have never been seen by anyone** — zero impressions, zero sessions,
any channel. Graded `never_distributed`, deliberately NOT `dead`. The previous articles
cycle called 25 articles dead when they had never been live; do not repeat that.

**Headlines have a ~25× measured spread, and the pattern is legible.**

| Headline | Impressions | CTR |
|---|---|---|
| Someone Bought This Robina Home Six Months Ago. Now… | 12,195 | **16.47%** |
| The Owner Paid $475,000 in 2010. They're Now Asking… | 2,290 | **11.79%** |
| Someone Paid $1,550,000… (flagship) | 6,952 | 9.97% |
| The Southern Gold Coast Apartment Boom: A Suburb-by-Suburb Guide | 2,856 | **0.74%** |
| Is Now a Good Time to Sell in Robina? | 3,098 | **0.65%** |
| Is Now a Good Time to Buy in Robina? | 2,847 | **0.70%** |

⚠ **Correction (2026-08-13):** an earlier version of this table carried a row *"How to Choose
a Real Estate Agent — What 1,475 Sales Show, 44,198 impressions, 0.31%"*. **That was an
attribution error and it has been removed.** The figure is real but belongs to an *ad* named
`"Traffic - How to choose the best agent. Ad"` in `content_hook_corpus` — the similarly-titled
ARTICLE has zero paid impressions in `article_performance`. Every other row above comes from
`article_performance`. Ad names and article titles are different namespaces and must not be
mixed in one table: doing so is how an unverifiable number becomes self-reinforcing, which is
exactly the mechanism behind P5 (the wrong licence number reproduced across 68 articles).

Specific property + specific numbers + a temporal twist wins. Generic guide, generic
question, and "how to choose an agent" die. This is the funnel's *specific shocking numbers
≫ abstract concepts* law, now confirmed on article headlines at real volume.

**The body is the failure point, not the hook.** The flagship earned 9.97% CTR and then
**37 sessions at 10.1% average scroll**. Best hook in the business; nine readers in ten
gone before the tenth of the page. **This is the highest-value problem you own.**

**⚠ The hook corpus measures CLICKS ONLY.** Not one of the 92 annotated ads is
lead-optimised — all are ENGAGEMENT / TRAFFIC / AWARENESS. The 108 lead-optimised ads,
including all 43 homeowner-funnel angles, are unannotated. Your own funnel documented **nine
high-CTR non-converters**. So a hook that wins clicks is not evidence of a hook that wins
sellers, and you must say so whenever you cite this corpus.

---

## 3. The plan, in priority order

### P1 — ✅ CLOSED 2026-08-16 — and it was not the body, it was the exit
P1 was written as "fix where readers leave". The audit that should have come first showed
something simpler and worse: **0 of 90 published articles linked `/analyse-your-home`, and
88 of 90 carried no non-disclaimer internal link at all.** Neither template CTA pointed
there either. `/analyse-your-home` is the only page where `address_search` /
`analyse_home_address_submit` fire, and `submitted_address` is the reward (lift 50.5,
n=9 conversions). **The funnel had no entrance, so "0 converters" was never evidence about
the format.**

Shipped (commits `2e6e85b8`, `4289682e`, both verified live):
- Mid + end CTAs lead with `/analyse-your-home/<suburb>`; clicks emit `article_cta_click`.
- Internal article links canonicalised to `/articles/:slug` (they all went via a 301).
- The card-index merge bug — every SSR article page rendered the wrong category and **no
  suburb**, because the route loader's PLACEHOLDER `category`/`scope`/`suburbs` are defined
  values and the merge copied them over the index. `INDEX_OWNED_KEYS` now protects them.
- The mid-article CTA no longer splits a section off its heading (it was landing between
  "The Result" and the result).

**The lesson to carry, because it has now cost three cycles:** verify by *rendering the
page and reading it*, not by reading the source. The three defects above were all invisible
in the diff and all obvious in one screenshot.

**What P1 was originally about is still open** and is now testable for the first time:
does moving `## The Result` earlier (shipped in the generator prompt on 2026-08-13) raise
read depth? Needs an article generated through the new prompt — first `how_it_sold` run
after 2026-08-13 — plus `paid_avg_scroll_pct`. Success = scroll rises, n stated.

### P1b — Draft residue is a THIRD defect class the editorial gate cannot see
The gate checks Rule 5. It has now passed, in three separate cycles: a duplicate pair
contradicting itself (24% vs 24.5%), a self-correction left in the prose
(`"+4.9% — correction: +4.4%"`), and a **prompt instruction rendered as body copy**
(`<p><em>Editorial opinion.</em></p>`, on an article Will had personally approved and which
was live). Before sending any draft, scan for residue as well as compliance:
`Editorial opinion`, `correction:`, `[INSERT|TBC|TODO]`, `as an AI`, and a same-suburb
same-hook duplicate check against the PUBLISHED corpus. A clean gate result says nothing
about any of these.

### P1c — ⏳ OPEN — the demand-led drip queue (6 drafts waiting, and a control group)
Written 2026-08-23 12:45. **This is the next session's first job and it is time-sensitive.**

Seven how-it-sold drafts were written this cycle against addresses that already carry measured
Search Console demand. **One was proposed; six are queued.** The drip cap is 3 per 24h and it
had already been reached (`article_approval.py propose` refuses; do not `--force` without a
reason). Send the rest at 3/day, highest demand first:

| # | article id | address | impr/30d |
|---|---|---|---|
| 1 | `6a8a5264710ff61068cbc047` | 180 Christine Avenue, Burleigh Waters | 38 | ← proposed 2026-08-23
| 2 | `6a8a5264710ff61068cbc04a` | 40 Palma Crescent, Varsity Lakes | 26 |
| 3 | `6a8a5264710ff61068cbc04d` | 12 Wayville Place, Robina | 18 |
| 4 | `6a8a5264710ff61068cbc04c` | 5 Chelsea Place, Robina | 14 |
| 5 | `6a8a5264710ff61068cbc049` | 4/44 Frascott Avenue, Varsity Lakes | 11 |
| 6 | `6a8a5264710ff61068cbc04b` | 3/1 Lakefront Crescent, Varsity Lakes | 10 |
| 7 | `6a8a5264710ff61068cbc048` | 9 Skua Street, Burleigh Waters | 8 |

**⚠ Do not write the other seven backlog addresses.** They are a pre-registered control group
(`rl_articles_signal`, cycle `20260823_1140`), matched on impressions (125 v 127) and suburb.
Writing them destroys the only control this domain has ever had. They are: 55/9 Moores Crescent,
17 Pitta Place, 1/5 Peacock Place, 2710/397 Christine Avenue, 2/5 Bottlewood Court,
41 Olympus Drive, 41 Watts Drive. Read out after 2026-09-22.

**Aiming the generator:** `run_how_it_sold.py --suburb <s> --address "<street address>"`
(repeatable) targets a specific sale, ignoring the date window and the `article_generated`
flag. Added 2026-08-23 for exactly this. Requires `AZURE_COSMOS_URI` (set it from
`COSMOS_CONNECTION_STRING`); push with `scripts/push_to_ghost.py --mode how_it_sold
--all-unpushed`, which creates drafts only.

### P0 — ✅ CLOSED 2026-08-13 21:20 — the 15 how-it-sold drafts are live
Will approved **REC-articles-002** via Telegram (token `A3B8`, 10:29:32Z). All 15 were
re-scanned by the body-level gate (15/15 clean, whole corpus 100/100) and published in one
batch with a **single** Netlify build. `approved_by` reads
`will_recommendation:REC-articles-002`, not `will_telegram`, so the provenance is not
misstated, and all 15 overrides are recorded in `system_monitor.article_publish_overrides`.
**Published corpus 73 → 88**; `articles.json` verified at 88 and three URLs verified 200 live.

**The judgement, written down because the next session will face it too.** The per-article
Telegram gate drips at 3/day by design. Executing a decision Will had *already made* through
that gate would have taken five days and 15 builds. The invariant the gate protects is *Will
decides* — and he decided, through a route (a full recommendation with claim, evidence and N)
that gave him strictly more to go on than a Telegram card does. The guard's own docstring
anticipates exactly this: "a documented, loud escape hatch survives contact with reality."
**Use the override only when you can name his approval and cite its token.** A draft he has
not seen still goes to Telegram, one at a time.

**12 drafts remain** (4 Varsity Lakes market-data, 2 of which are near-duplicates; and the
rest). These have NOT been approved — they go through `article_approval.py propose`, 3/day.

### P2 — Distribute the 60 undistributed
Nothing else you do matters if articles are never seen. Order by likely value using the hook
patterns above, propose the best for organic posting, and measure.
- ⚠ **Rank on `post_clicks`, not reach.** Meta has deprecated post-level impressions and
  reach entirely — `post_impressions` now errors on every API version with `read_insights`
  granted. You cannot compute an organic CTR. Absolute clicks is the metric.
- Baseline: all 15 prior organic posts scored **exactly zero** engagement. Anything above
  zero is new information.

**Where we may publish — researched 2026-08-13, ranked.**
| Channel | Verdict | Why |
|---|---|---|
| **r/AusPropertyChat + r/AusProperty** (~286k) | **Do first** | The only channel where this exact asset demonstrably outperforms: a sales-analysis post scored 456 upvotes/159 comments; a price-guide-accuracy tool 747 upvotes. Free, referrer-measurable. ⚠ Disclosure of the licence is legally required and costs upvotes — a self-identified agent's post scored 0, while the top agent-related posts are *attacks* on agents. Our sold-vs-asking data is genuinely adversarial to agent interests, which is the only reason this can work. Numbers in the body, link in a comment. |
| **Firstlinks (Morningstar)** | **Do** | Uniquely permits content already on your own site, and grants a bio link. SMSF/retiree audience ≈ asset-rich 45-65. Free. |
| **The GC Minute** (6,000+ local subs) · **myGC** (`news@mygc.com.au`) | **Do** | Geographically matched, low effort, plausible links. |
| SourceBottle free tier | Conditional | Reactive, ~10 min/day, no PR history needed. |
| Facebook community groups | Conditional | Right audience, but **Group Insights are admin-only** — a non-admin poster gets zero analytics. Only worth it as an admin-sanctioned recurring data snapshot, with a distinct UTM per group. |
| PropertyChat | **Low priority** | $1,375/yr, and its two rule pages **contradict each other** on the one thing you would pay for (Forum Rules permit article links; the Business Members Guide forbids them). Assume the restrictive reading. Audience is national investors, not GC sellers. ⚠ It also has a "No Market Research" rule a prior session may already have breached. |
| LinkedIn · Medium · Nextdoor · Whirlpool · r/GoldCoast · Gold Coast Bulletin · trade titles | **Ignore** | Medium's Distribution Guidelines disqualify content marketing outright. r/GoldCoast is the highest ban risk and lowest reach. **Gold Coast Bulletin is News Corp, which majority-owns REA Group — PropTrack is their in-house suburb data, so ours is a substitute for something they already own.** |

**⭐ The opening nobody has taken:** Domain and Brisbane Times are Nine/CoStar-owned and
structurally locked out of REA's PropTrack. They are the one national outlet family for whom
"original non-REA Gold Coast suburb data" is a competitive offer rather than a redundancy.
Worth a dedicated approach.

**⚠ The QLD risk is not advertising — it is inbound DMs.** Publishing suburb aggregates does
not trigger POA s215; that fires when a seller *asks* what their property will sell for.
Every forum channel creates a path to exactly that question in a private message, and
answering it invokes the CMA obligation plus the s216(6) bar on passing it to anyone else.
**Route valuation questions off-forum into the appraisal flow; never answer inline.** And
posting without disclosing the licence is astroturfing under ACL s18 — PropertyChat states
it reports such businesses to the ACCC.

### P3 — ✅ SHIPPED 2026-08-13 21:10 — the generator now reads its own outcomes
**REC-articles-003** approved by Will (token `F6E6`). Merged to `fields-automation` as one
commit **`d8895c0c`**, five files, all md5-verified:
`pipeline/learning_context.py` (new) renders `pipeline/data/learning_snapshot.json` (new,
committed so the prompt input stays diff-reviewable, regenerated by
`scripts/build_learning_snapshot.py`) into every How It Sold and Watch This Sale prompt —
6,085 chars of measured headline CTR, read-depth, and abstracted dead hook mechanics, with
`caution_hook_corpus_has_no_lead_outcomes` carried verbatim. `article_prompt_template.md`
moves `## The Result` from section 6 to section 3 and drops the target length to 800–1000.

⚠ **Not yet graded, and the claim is narrow.** It expects `paid_avg_scroll_pct` on newly
generated How It Sold articles to rise from 10.1% (n=37, one article) to >20% by 2026-09-30.
Nothing has been generated through the new prompt yet — the next scheduled `how_it_sold` run
is the first test. **Do not claim this worked until an article written by it has been measured.**

⚠ **A trap this cost an hour to avoid, and it will still be there next time.**
`/home/fields/fields-automation` is a **stale clone** — `pipeline/claude_max_client.py` is on
GitHub and imported by `article_generator.py`, but is neither present nor tracked locally. So a
diff against the local tree shows phantom changes (it flagged an `anthropic.Anthropic →
make_client` swap that had already landed on remote). **Fetch from GitHub and diff against
that before pushing anything to this repo.** See fix-history `[REC-003-STALE-BASE]`.

### P4 — ✅ CLOSED 2026-08-13 — and it was far bigger than "two breaches"
The "two live editorial breaches (71 of 73 pass)" figure was wrong, and wrong for a
knowable reason: the only Rule 5 checker in the article path lived inside
`fb_post_article.py` and was only ever handed a **title plus a one-line excerpt**. It had
never read an article body. A body-level scan found **14 of 73 published articles
breaching**, including a whole live section of `leading-vs-lagging-indicators` telling
readers to "Start your property search now", "sell into strength" and "Make buy/hold/sell
decision".

All 14 corrected. Corpus is now `scanned 100 · clean 100 · with breaches 0`.

**What you now have:** `scripts/editorial_gate.py` — run it over bodies, not headlines.
```bash
python3 scripts/editorial_gate.py --published    # or --drafts / --all / --slug <s>
```
It is wired into `article_approval.py propose`, which **refuses** to put a failing draft in
front of Will. Eight known false positives sit in `ACKNOWLEDGED` with a written reason each,
so a clean run genuinely means clean — do not add to that list without reading the sentence
in full and writing down why.

⚠ **The lesson generalises.** "71 of 73 pass" was a true statement about 73 headlines
presented as a statement about 73 articles. Before trusting any gate, check what it was
actually shown. Same shape as Rule 7b and Rule 8.

### P5 — ✅ CLOSED 2026-08-13 — it *was* in the automation repo
`fields-automation/scripts/push_to_ghost.py:125` hardcoded
`'Fields Real Estate (Licence No. 4832971) makes no warranty…'` into the disclaimer appended
to every article it pushed. The earlier search looked for a config value; the number was
inline in a string literal. Fixed and pushed.

The same filesystem search found **two live emitters nobody had looked for**, because every
prior pass scoped itself to articles:
- `public/launch/{a,b,c}/index.html` — three seller-facing landing pages, one of which
  invites the reader to *"verify on the Office of Fair Trading register"* against a number
  that fails that check.
- `netlify/functions/launch-form.mjs` — the form response.
Both corrected and verified live.

⚠ **Carry this forward:** the symptom appeared in articles, so three passes searched
articles. Search the whole filesystem for the literal before concluding where a bad value
does and does not live.

### P6 — Google News eligibility
Will's stated goal. Requires quality and consistency first; sequence after P1–P3.

---

## 4. Reference list — every source, and its honest limitation

**Outcome data**
- `article_performance` / `content_articles.performance` — your primary read. Check
  `evidence_grade` before believing any row: `never_distributed` / `insufficient` / `measurable`.
- `ad_session_behaviour.articles_read[]` — `max_scroll_pct`, dwell. **Paid traffic only.**
- `organic_journeys.timeline[]` — organic `article_view` + `scroll_depth`, now rolled up.
- `organic_landing_affinity` — sessions/engaged/converters. ~6 article rows, 12 sessions. Tiny.
- `seo_landing_performance` — GSC per page×query. ⚠ **A single snapshot (2026-08-12), not a
  series.** You cannot compute a trend from it and must not imply one.
- `ad_profiles.lifetime` — ~200 article-titled ads. ⚠ `ad_daily_metrics` keeps only 90 days,
  so pre-2026-07-15 daily detail is gone; only lifetime aggregates survive.
- `fb_page_posts.insights.metrics` — `post_clicks`, `post_fan_reach`, reactions. No reach.

**Learning corpora**
- `content_hook_corpus` / `content_hook_aggregates` — `build_hook_corpus.py --show`.
  ⚠ clicks only; no lead outcomes; 55 of 92 rows clear the impression floor.
- `content_learnings` — `build_content_learnings.py --show`. Archetypes, laws, cautions,
  36 dead angles. **Read the dead angles before proposing any topic or hook.**
- `16_General_Reinforcement_Learning/CONTENT_LEARNINGS.md` — what the corpus is and its ten
  stated limitations.

**The Brains — query at will; they are free and nobody had told you they exist**
- **Brain 2 — our own behaviour** (FB Ads + PostHog). `scripts/brain2/brain2_util.py` →
  `hog_retry(pid, key, sql)` for arbitrary HogQL. See `scripts/brain2/POSTHOG_CAPABILITIES.md`.
  Use it when the rolled-up collections cannot answer the question — per-event, per-session,
  any breakdown you like. This is how you'd find *where* in an article readers drop, rather
  than only that they do.
- **Brain 1** (coaching/sales corpus) and **Brain 3** (internal operational knowledge: fix
  logs, CEO memory, prior articles): `scripts/samantha/brain_search.py "<q>" --brain all`.
  Check here before assuming something has never been tried.

**⚠ Contested claims — do NOT treat as settled**
CLAUDE.md lists these as "established, do not re-test", but our own sources contradict them:
- *"broad targeting beats custom audiences"* — filed as **Error 3** (confounded) in
  `drafts/marketing-test-summary.md`.
- *"OFFSITE_CONVERSIONS is the #1 lever"* — its isolating experiment got **one** website view.
- *"a phone field doesn't suppress lead volume"* — contradicted by
  `NEXT_CYCLE_AD_PLAN_2026-07-30.md`: phone-required cost **$30/lead, 0 hot** vs ~$15 without.
Also: Archetype B's famous **$4.27 CPL was its single best instant** — it decayed to ~$28 at
cull. And "4 quality leads" is really **3**; one had a fake +93 phone number.

**Prior art (prose, already mined into `content_learnings` — go back only for detail)**
`03_Facebook/Home_Owner_Lead_Funnel_Search/00_MASTER_LEDGER.md` + `cycles/` ·
`drafts/marketing-test-summary.md` · `NEXT_CYCLE_AD_PLAN_2026-07-30.md`

**Binding rules**
CLAUDE.md Rule 5 (editorial) · Rule 1 (fix-history) · Rule 8 (never infer absence from a
guessed field name) · `briefings/articles.md` §5 — canonical gate on syndication, community
group rules, and never add a channel you cannot measure.

---

## 5. What you may NOT do, however good the idea

- **Publish anything.** Every article needs Will's explicit approval — his rule, 2026-07-29,
  reaffirmed in your brief. Use `article_approval.py propose`.
- **Post to Facebook without approval**, or to any group in breach of its self-promotion rules.
- **Republish full text off-site without a `rel=canonical`** to fieldsestate.com.au.
- **Spend money.** The $20/week article ad budget is the ads domain's to execute and Will's
  to authorise.
- **Message Will.** Samantha is the only channel.

---

## 6. Working continuously — you may chain your own sessions

Will granted this on 2026-08-13: *"work continuously until it reaches a point where it
believes everything that should be done now has been done and that most benefit would be in
waiting till the next scheduled wake cycle."*

```bash
python3 article_chain.py --continue --reason "<the specific next task>"   # run again soon
python3 article_chain.py --stop --reason "<why waiting is now better>"    # end the run
```

**You must call one of these at the end of every session.** Neither is a default.

**Chain when** there is concrete work in hand you could start now: an article to revise, a
measurement to take, a corpus to rebuild, a body to restructure.

**Stop when** you are blocked on Will, at your recommendation cap with nothing else to do, or
genuinely finished — the honest and expected end state. **Stopping early is not failure.**
Chaining to look busy is the single worst thing you can do here: it burns Max usage, and it
recreates exactly the churn that got the previous system switched off after 27 cycles in two
days.

**Guards you cannot override** (`article_chain.py` enforces them): a hard daily and weekly
cap, a minimum gap between sessions, and an automatic stop if consecutive sessions produce
nothing. A chain that produces no artefact is treated as a failed chain, not a quiet one.
