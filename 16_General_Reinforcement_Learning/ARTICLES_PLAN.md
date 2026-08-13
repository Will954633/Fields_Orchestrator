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
| How to Choose a Real Estate Agent — What 1,475 Sales Show | 44,198 | **0.31%** |

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

### P1 — Fix the body, not the hook (highest value, evidence is strongest)
The read-depth number is the most actionable fact we have. Take the articles with a strong
headline and collapsing scroll and work out *where* readers leave. Then fix the structure and
measure whether scroll moves. Start with the flagship (37 sessions, 10.1%).
- Success = average scroll on a revised article rises, measured, with n stated.

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

### P3 — Feed the hook evidence into generation
The generator's angle selection is a hardcoded 14-rule table scoring property attributes,
and its prompt is static. It has never seen `content_hook_corpus`. Closing that is the
difference between a writer and a learner. Propose the mechanism; it changes generation, so
it needs Will.

### P4 — Fix the two live editorial breaches
Found by the Rule 5 gate across 73 published articles (71 pass):
- `is-now-a-good-time-to-sell-in-robina` contains **"you need to"** — advice, forbidden.
- A sold-townhouse article uses **"$1.1M"** shorthand instead of `$1,100,000`.
Both are already public. You may fix published copy under §4 of your brief.

### P5 — Find the licence-number source
68 articles carried QLD licence **4832971**; the correct number is **4832972**. Corpus
corrected 2026-08-13, but **the generator still emits the wrong one** — 28 of the 68 were
created in August. Not in the automation repo, not in local config. Plausible mechanism: the
model reproducing it from our own older published articles, i.e. self-reinforcing. Find it.

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
