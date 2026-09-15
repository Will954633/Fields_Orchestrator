# ARTICLES (self-hosted content) — standing brief

**Last updated:** 2026-09-13 by Will + Samantha (second briefing session)
**Review cadence:** weekly

> This document is the domain's **authorisation envelope**, not background reading. Work
> inside §1 Direction and §4 Standing Authorisations is executed autonomously and reported
> afterwards. Work outside it is proposed and waits.
>

---

## 1. Direction — what we are doing here and why

Articles are a **reader-engagement, lead, and brand-credibility tool** — not a publishing
quota. Will's direction, 2026-09-13:

**This is a pivot from FORMAT to STORY, not away from house stories.** The single biggest
result this domain has ever produced was
[*"Someone Paid $1,550,000 for This Burleigh Waters Home. Eighteen Months Later, It Sold for
$3,465,000."*](https://fieldsestate.com.au/articles/someone-paid-1550000-burleigh-waters-home-sold-3465000)
— **~7,000 views, driven by Facebook.** That proves stories about individual house sales
can shoot the lights out. What does NOT work is the formulaic, exact-address `how-it-sold`
SEO page: it ranks #1 for an address almost nobody searches and returns ~0.12 sessions per
article. **The subject (a house sale) is right; the treatment (a boring SEO address stub)
is wrong.** The win was a *story* with a striking, resonant number.

Three content tracks, all live:

1. **Individual-sale STORIES that resonate with THIS market's audience.** Find recent sales
   with a striking narrative and go and write the next $3.465M-calibre piece. The market has
   changed since April 2026, so the stories that land now may be different ones — look for
   what resonates *now*, not what resonated then. This is a priority, not a legacy format.
2. **Demand-attached topics** — subjects with independent search demand that exists whether
   or not we write about them. **Do-now target: the Coomera→Nerang Stage 1 works (Coomera
   Connector) happening right now — everyone on the Gold Coast will want to know about it.**
   Major projects, infrastructure, "is the market about to fall"-type queries.
3. **Whole-of-Gold-Coast brand-credibility content, optimised for likes and comments.** The
   goal of these is to **build brand credibility**, not traffic or conversion. Judge them on
   engagement, not sessions.

Constant across all three: keep the **McKinsey pattern** — every article educates the reader
on what Fields does and gives them a reason to click deeper. Ranking #1 is still nice but is
**no longer the goal in itself**; attaching to real demand (search or social) is.

**THE OVERARCHING GOAL IS A PARASOCIAL RELATIONSHIP — AND RETURN VIEWERS ARE THE METRIC.**
(Will, 2026-09-13.) Read and internalise *"Parasocial Relationships – Science & Playbook"*
(Google Doc `1gX-7QfimUBIT69t9hmCADoQ6SVCYLYgMdJxnYD76nME`; local mirror
`14_Articles/Market_Research/parasocial_playbook.md`). The strategy: selling is a rare,
long-delayed, single-agent, trust-first decision (81% of sellers contact only ONE agent;
median ~11-year tenure), so we are running a multi-year "be the agent they already feel they
know" campaign. The science says **length of exposure does NOT predict the bond — RETURN,
DEPTH of consumption, and staged progression over time do.** So:
- **Optimise for RETURN VIEWERS especially, not just new views.** A piece that brings someone
  back is worth more than one that spikes new traffic once. New views are top-of-funnel (PSI);
  returning + deep-reading + video-watching viewers are the bond forming (PSR).
- **Write content that can later become a "Will walkthrough"** — the direct-address,
  chart-guided, talk-to-one-person format (see live examples
  [/news/robina](https://fieldsestate.com.au/news/robina) and
  [/articles/comparing-median-house-prices](https://fieldsestate.com.au/articles/comparing-median-house-prices)).
  The playbook calls this format a "direct-address credibility engine" and the bottom-of-funnel
  PSR converter. Favour topics and structures that give Will something to walk a viewer
  through on camera; flag in the draft where a walkthrough could attach.
- **Show, don't sell; warmth before competence; keep CTAs light.** Overt selling triggers
  "persuasion knowledge" and discounts the trust built by the previous pieces.

**Stay abreast of the market — READ THE MARKET CONTEXT ENGINE BRIEFS EVERY CYCLE.** The live
source is the **Market Context Engine** (`14_Articles/Market_Research/`), refreshed
**fortnightly** (Sun-noon cron, next 2026-09-20). At the start of every cycle read:
  - `14_Articles/Market_Research/INDEX.md` — the current index, and
  - `14_Articles/Market_Research/briefs/current/` — dated topic briefs: **sentiment**,
    **psychology** (buyer + seller), affordability, interest-rates, migration, supply,
    national-market-turn, negative-gearing/CGT;
  - or programmatically `system_monitor.market_research_briefs` /
    `data/<cycle>/audience_context_pack.json`.
This is the researched read on what our audience is seeing in the news, worrying about, and
being influenced by — national → Brisbane → Gold Coast, grounded per suburb. The individual-
sale stories and demand-attached topics you choose (§1) must resonate with the mindset these
briefs describe *now*, not months ago. If the latest cycle is older than ~16 days, say so in
your cycle doc. ⚠ The old `15_Off-Market/Home_Owner_Perspective/` mindset brief is SUPERSEDED
(quarterly, unscheduled, last run 2026-08-02) — do **not** use it.

**Work with the SEO domain.** SEO sends evidenced notes (query gaps, titles losing clicks,
topics worth extending). Read them at cycle start and reply the same way:

```bash
python3 conductor_state.py directives --domain articles     # includes from:seo notes
python3 conductor_state.py directive --domain seo --from articles --text "<...>"
```

## 2. Current state — what is ON, OFF, or PAUSED, and deliberately so

| Thing | State | Why |
|---|---|---|
| Publishing | **NOT paused** — publishing is expected | Direction is slow + demand-attached, not volume. |
| Cadence | **Slow, demand-attached** (Will, 2026-09-13) | Traffic, not cadence, is the constraint. Chain only with a real story/topic in hand. Don't churn. |
| Facebook posting | **AUTHORISED and expected — posting has STARTED (3 posts by 2026-09-15) but is measuring nothing** | `performance.fb_organic.posts:1` on 3 articles, all `clicks:0, fan_reach:1` (placeholders). The feedback path is broken — "learn autonomously from FB" is blocked until it's fixed. Fix measurement BEFORE scaling posting. |
| Performance feedback loop | **WAS DEAD 2026-08-29 → 2026-09-13; fixed 2026-09-13, heartbeat added 2026-09-15** | `article_performance` cron (line 343) was missing its `cd`; ran from `/home/fields` where `.env` is absent, so it died before Python for 15 days. Cron fixed + Rule 7/7b heartbeat wrapped. All 101 articles now carry fresh `performance`. |
| 15 story drafts | **Regenerated as STORY pieces 2026-09-14; CLEARED to propose (Will 2026-09-15)** | The "$X paid → sold for $Y" winning pattern, Rule 5 clean. Propose the most promising for approval (drip 3/day per §4), publish on Will's tap, monitor engagement. The old conductor HOLD directive is OVERRIDDEN. |
| Stale/false SERP titles | Audit "No Guide"-style `ai_analysis.meta_title`s vs live price each cycle | 2026-09-15 live-Googlebot audit: **1 genuinely false** (9 Auriga Ct — serves "No Guide" on a $1,949,000 listing); 2 self-resolved to generic fallback; 3 still true. Autonomous correction authorised (§4). |
| Approval | Every NEW article still needs Will's explicit YES before going live | 2026-07-29 rule, still standing. `article_approval.py propose` → Telegram YES/NO. |
| Authorship | ALL articles authored by **Will Simpson** | Corrected corpus-wide 2026-08-13. |
| QLD licence in disclaimers | **4832972** | ⚠ the GENERATOR may still emit 4832971 — watch for recurrence. |

## 3. Goals — what good looks like

**The primary metric is RETURN VIEWERS (PSR forming), measured on the "Engagements" tab —
not one-off new views.** Everything below serves that.

1. **Grow return viewers, deep-reads, and walkthrough watch-depth** week over week on the
   Engagements ladder (RETURN / DEPTH / VIDEO rows). New views are the top of the funnel;
   the bond is people coming back.
2. **Find the next individual-sale story that shoots the lights out** — the $3.465M piece,
   again, for this market. Judged on reach + onward engagement (incl. Facebook) + whether it
   brings people back, not just organic search.
3. **Build brand credibility** with whole-of-Gold-Coast content optimised for likes/comments.
4. **Attach to real demand** — infrastructure/major projects (Coomera Connector first).
5. **Learn autonomously from Facebook post performance** — post trials, keep winners.
6. **Educate each reader on what Fields does** and route them onward (McKinsey pattern).
7. Optimise/iterate existing articles; retire dead angles; rank highly where demand exists.

## 4. Standing authorisations — SHIP THESE WITHOUT ASKING

- **⭐ READ THE "ENGAGEMENTS" TAB EVERY CYCLE and reason from it (Will, 2026-09-13).** It is
  the Live Leads Tracker sheet (`1mRjT_PmjTepF1rDajJlM553Umy47dKa4fHOclrzAKFs`), tab
  **"Engagements"**, generated by `scripts/engagement_funnel_to_sheet.py` from PostHog — a
  weekly parasocial-relationship ladder (REACH→ATTENTION→VIDEO→RETURN→DEPTH→IDENTITY→INTENT→
  CONVERSION) with per-session **entry-channel/campaign attribution** ("BY FUNNEL" block).
  Use it to judge whether your content is producing RETURN viewers and depth, and **trace
  every engagement back through its link to its source** so you know what actually brought
  people back. The underlying attribution is queryable directly via Brain 2
  (`scripts/brain2/brain2_util.py` `hog_retry`) — session channel/campaign, returning-vs-new,
  `walkthrough_*` video events. Report what you learn in your cycle doc.
- **⭐ READ WILL'S WALKTHROUGH TRANSCRIPTS + THE /news CHART DATA (Will, 2026-09-13).** Ground
  your content in what Will has already said on camera and in the exact charts readers see:
  - **Walkthrough transcripts** — his actual scripts live at
    `10_Market_Report/issues/Video/<Month>_<Year>/*_Transcript.md` (August 2026: Robina /
    Burleigh Waters / Varsity Lakes suburb updates; September 2026: the *Comparing Median House
    Prices* article walkthrough). For **article** walkthroughs the caption text is authored in
    the site code (`WALK_SEGMENTS_*` in `MarketFlowProto.engine.ts`), so a transcript can always
    be regenerated from there if a markdown is missing. Use these to match Will's voice/framing and to write
    pieces that extend or set up a walkthrough rather than contradict one.
  - **/news chart data** — read `Gold_Coast.precomputed_market_charts` (e.g.
    `_id: "robina_sales_volume"`), or the `/api/market-narrative/:suburb` and `/charts`
    endpoints. Your claims must match the charts on the live page (see
    [/news/robina](https://fieldsestate.com.au/news/robina)); a stat in an article that
    disagrees with the chart on the same surface is a defect.
- Topic research, drafting, and rewriting/optimising the body of EXISTING published articles
  where it serves the goals above (titles/metas coordinate with seo).
- **⭐ NEW (Will, 2026-09-13): autonomously correct stale or factually FALSE `meta_title`s
  and on-page copy when the listing state has moved** (e.g. a "No Guide" title on a
  now-priced listing). This is a Rule 5 factual-accuracy fix restoring stated intent, not
  new public content — fix it and report it, do not file a recommendation. The 2026-09-15
  audit found **1 live-false title (9 Auriga Ct — "No Guide" on a $1,949,000 listing)**; fix
  that one first, and re-audit the "No Guide" set each cycle since listings get priced.
- **Redirect the 15 how-it-sold drafts into resonant individual-sale STORY pieces** per §1.
- Retiring dead topics; fixing slugs, metadata, internal links, on-page structure.
- Querying Brain 1/2/3 and past Facebook performance for what has worked (see below).
- **⭐ Proposing drafts for approval is AUTHORISED and needs NO recommendation.**
  `python3 scripts/article_approval.py propose --id <article_id>`. Will's tap IS the
  decision — do not file a recommendation asking permission to ask him. Drip at **3/day**
  (enforced in code). Read `will_feedback` on any rejected article before redrafting.
- **Revising a rejected draft**: `article_revise.py --id <id>` (auto-runs on rejection; never
  publishes — Will's tap is the only way live).
- **Reading measured outcomes**: `article_performance.py` (nightly) writes
  `content_articles.performance` — organic sessions, GSC, read-depth, **paid ad CTR per
  headline**, FB. Always check `evidence_grade`. ⚠ See §6 on the FB measurement gap before
  concluding anything from organic-search numbers alone.
- **The learning corpora**: `build_hook_corpus.py --show` (headlines→outcomes) and
  `build_content_learnings.py --show` (archetypes, laws, dead angles). Read the dead angles
  before proposing any hook. ⚠ the hook corpus measures CLICKS ONLY.
- **⭐ POSTING PUBLISHED ARTICLES TO FACEBOOK — authorised AND expected (Will, 2026-08-13,
  reaffirmed 2026-09-13).** Post every published article to the page as a trial, keep posting
  the winners, and **learn from the results autonomously.** `fb_post_article.py --id <slug>
  --post`. Only `status: published` articles (approval gate is upstream). Rank on
  `post_clicks` (Meta deprecated post reach). This had never once run before 2026-09-13 —
  make it real.
- **⭐ CHAINING YOUR OWN SESSIONS.** You are the only domain with this. End EVERY session with
  `article_chain.py --continue --reason "<specific next task>"` or `--stop --reason "<why
  waiting is better>"`. Given the slow/demand-attached direction, **stopping is the normal
  end state.** Chain only when a real story or demand-attached topic is in hand — never to
  look busy. Guards you cannot override: 6/day, 20/week, 20-min floor, forced stop after 2
  barren sessions.
- **THE BRAINS — query at will.** Brain 2 (our FB Ads + PostHog behaviour data) via
  `scripts/brain2/brain2_util.py` `hog_retry(pid,key,sql)`; Brain 1 (coaching/sales) and
  Brain 3 (internal ops knowledge) via `scripts/samantha/brain_search.py "<q>" --brain all`.
- **Your plan lives in `ARTICLES_PLAN.md`** — read and keep it updated. You own it.

## 5. Off-limits — never, regardless of anything else

Global prohibitions always apply and are never granted by a brief: spending money, editing
the crontab, editing monitoring/health-check code, contacting a real person, deleting data,
Gold Coast go-live.

- **Never publish a new article, or take one live, without Will's explicit approval** (Will,
  2026-07-29). Optimising an already-published article is allowed; making something newly
  public is not.

**DISTRIBUTION CONSTRAINTS (Will, 2026-08-13) — bind every channel, forever:**

- **Never republish an article's full text on a third-party platform without a
  `rel=canonical` back to `fieldsestate.com.au`.** Excerpt + link is the default; full
  republication is the exception and needs the canonical tag. "We can not hurt SEO."
- **Never post to a community group/forum/subreddit in breach of its self-promotion rules.**
  Read the rules first and record where. Will is a LICENSED agent posting under a business
  name — a breach risks a ban and QLD conduct implications. Unclear rules = "no".
- **Never add a channel we cannot MEASURE.** Establish how performance comes back before
  posting anywhere new. A channel with no feedback path is a guess, not a trial.

## 6. Context the agent cannot get from data

- **⚠ THE FACEBOOK MEASUREMENT GAP — read this before judging any article.** The domain's
  single biggest hit, the $3.465M Burleigh Waters story (~7,000 views), shows **organic
  sessions 0, search clicks 0, 10 impressions, `fb` None** in our own `performance` data. Its
  success came almost entirely through **Facebook**, which our per-article measurement barely
  captures (only 38 paid sessions + dwell were joined). **Do NOT dismiss individual-sale
  stories on organic-search numbers — the channel where they win is nearly invisible to
  you.** Closing this measurement gap is itself valuable work.
- **The winning article had `page_type: None`** — it was never in the `how-it-sold` bucket.
  The distinction Will draws is **story vs format**, not house-sales vs other topics.
- **"0 conversions" is statistically meaningless at current volume.** 46 article sessions at
  the site's 1.4% base rate predict 0.65 conversions; observing 0 has p≈0.52. You need
  ~212 sessions before a zero carries information. The old brief's "volume has not worked"
  claim was **retracted 2026-09-13** — it was never evidenced.
- **The market has changed since April 2026.** The stories that resonated then may not now.
- **The parasocial playbook is the strategic frame, and it has hard implications** (doc
  `1gX-7QfimUBIT69t9hmCADoQ6SVCYLYgMdJxnYD76nME` / `14_Articles/Market_Research/parasocial_playbook.md`):
  (a) **there is NO magic exposure count** — do not chase volume; the mere-exposure curve
  peaks ~36 exposures and then *declines*, so over-posting can hurt. (b) Consistency, RETURN,
  depth and staged progression build the bond; raw view counts do not. (c) The bond is what
  converts expertise into trust — a single brilliant analysis piece won't win a listing, many
  ordinary-but-consistent ones will. (d) A "Will walkthrough" (direct address, second-person,
  eye-to-lens, guiding through a chart) is the best-evidenced single lever — engineer content
  toward it. (e) Overt CTAs trigger persuasion-knowledge and discount prior goodwill.
- **The Engagements tab is a RELATIONSHIP ladder, not a traffic dashboard.** Session unit is
  reliable only from ~2026-08-17; engaged time caps at 300s active (a 40-min open tab is 5 min
  of reading); CONVERSION / two-way rows are MANUAL (no automated source yet) — don't read a
  blank there as zero.
- Two distinct workflows exist and must not be confused: PUBLIC sold-home articles vs
  OWNER-SUBJECT direct-mail assets (memory `two_article_workflows_public_and_posted`).
- Editorial Rule 5 binds everything: no advice, no predictions, comparable ranges not single
  valuations, cite source + period, forbidden words.

## 7. Open questions — Will to answer

- [x] Pivot away from home stories? **No** — pivot from format to story; keep individual-sale
  stories, find the next winner. (2026-09-13)
- [x] The 15 how-it-sold drafts? **Redirect into story pieces.** (2026-09-13)
- [x] Facebook posting + autonomous learning? **Yes, actively.** (2026-09-13)
- [x] Autonomous stale/false-title fixes? **Yes.** (2026-09-13)
- [x] Cadence? **Slow, demand-attached.** (2026-09-13)
- [x] Whole-of-GC brand-credibility content optimised for likes/comments? **Yes, add it.** (2026-09-13)
- [x] **The 15 story drafts** — **Will 2026-09-15: yes — start proposing the most promising
  ones for approval, publish on my tap, and monitor engagement.** Lead with the strongest
  (biggest resonant gap), drip 3/day per §4. The old conductor HOLD directive is overridden.
- [~] **Facebook 0-clicks — DIAGNOSED 2026-09-15 (fix pending Will's go).** Not a bug or
  permission problem: the `clicks:0/fan_reach:1` are REAL Meta values. Two causes: (1) the
  page has near-zero ORGANIC reach (1–3 fans/post), so organic `post_clicks` are genuinely
  ~0 — even fully refreshed, total = 1 link click across all 3 posts; (2) a staleness bug
  freezes each post's insights at 72h (`post-performance-tracker.py` finalizes and never
  re-fetches unless run with `--refresh-insights`; the 6-hourly cron omits it). The
  impressions/reach metric family IS deprecated by Meta, but `post_clicks` still works.
  **Recommended fix (2-part):** (A) add `--refresh-insights` to the 6-hourly cron (one line);
  (B) — the real answer — **rank on Facebook-referred on-site SESSIONS**, not organic
  `post_clicks`: source from `system_monitor.organic_journeys` / `organic_landing_affinity`
  (per-article FB-referral session counts; captures posts+shares+ads, real volume), add
  `fb_referral_sessions` to `article_performance.py`'s `fb_organic` block and rank on it.
- [~] **Per-article RETURN attribution — FEASIBLE, ~2h build (pending Will's go).** The slug
  is already in the PostHog `$pathname`; `engagement_funnel_to_sheet.py` already computes
  ~90% of it (`top_return_triggers`) but collapses `/news/<suburb>`→"News" and truncates
  slugs. Fix: add a "RETURN BY ARTICLE" block to the `Attr · Return` tab (un-truncated
  labels, keep the suburb) — ~2h, no new PostHog pull. ⚠ Volume is thin (60d: 102 returners,
  only 11 returned to a content page) — a *ranking* signal ("which pieces pull people back",
  `/news/robina` leads), NOT a precise rate.

## 8. Changelog

- 2026-08-13 — seeded by Samantha from measured data.
- 2026-08-13 — first briefing session with Will. §1-§7 written from his words.
- 2026-09-13 — **second briefing session.** Pivot format→story (keep individual-sale stories;
  next $3.465M-calibre piece is the target). Added demand-attached track (Coomera Connector
  Stage 1) and whole-of-GC brand-credibility/engagement track. Redirect the 15 how-it-sold
  drafts into stories. Reaffirmed FB posting + made autonomous learning from it explicit
  (it had never run). Authorised autonomous correction of stale/false SERP titles. Documented
  the FB measurement gap and retracted the "volume hasn't worked / 0 conversions" claim.
- 2026-09-15 — **factual corrections from a monitored PREVIEW run** (verified independently):
  false-title count is **1, not 6** (9 Auriga Ct); the 15 drafts were **already regenerated as
  story pieces 2026-09-14**; FB posting **has started (3 posts) but returns placeholder
  metrics**; `article_performance` heartbeat added. Three new §7 questions for Will (draft
  propose-count vs conductor HOLD; FB metric placeholders; per-article return attribution).
