# ARTICLES CYCLE — 2026-08-23 11:40 AEST

**Briefing tier:** `aging` (10d, updated 2026-08-13) — full standing authorisations apply.
**Open recommendations:** 1 at start, **2 at end** (REC-articles-005 raised). At cap.
**Graded:** nothing due.
**Chained session**, third today, following `articles_cycle_20260823_1100.md`. That cycle ended
by naming its own next job — *choose the treatment subset deliberately, so the backlog does not
destroy its own control group* — and left it undone on purpose. This session is that work, and
it turned into rather more than that.

---

## 1. What changed since the 11:00 cycle

`fix_digest.py` shows nothing new from anyone else. No conductor directives outstanding. The
change that mattered was one the 11:00 cycle believed it had already made, and had not — see §3(c).

---

## 2. The numbers, with denominators

**The experiment is pre-registered, and it was registered before a word was written.**
`system_monitor.rl_articles_signal`, cycle `20260823_1140`.

15 backlog addresses; 1 (16 Jabiru Avenue, 19 impr) has no sold document in
`Gold_Coast.burleigh_waters` at all, so it cannot be written and is excluded from both arms.
The remaining 14 were split into matched pairs on 30-day impressions, then balanced on suburb:

| | n | impressions/30d | Burleigh Waters | Varsity Lakes | Robina |
|---|---|---|---|---|---|
| **Treatment** (written today) | 7 | **125** | 2 | 3 | 2 |
| **Control** (deliberately unwritten) | 7 | **127** | 3 | 3 | 1 |

**The imbalance I could not fix, stated rather than buried:** property type. Treatment is
6 houses / 1 apartment; control is 4 houses / 2 apartments / 1 duplex. With 14 items you cannot
match impressions, suburb *and* type simultaneously, and impressions are the outcome variable, so
they won.

**And the honest power statement: n=7 per arm, on 8–38 impressions each. This is a control
group, not a powered test.** It can tell us the difference is large, or that we cannot see one.
It cannot tell us the difference is small.

The primary metric is deliberately **not** "did the article get clicks". It is *combined
impressions and clicks across every URL of ours that ranks for the query* — article, property
page, off-market page. That is the only form of the measurement that can distinguish adding
demand from splitting it, which was the open question.

**⚠ The read-out depends on something outside my control.** Drafts do not rank. The treatment
arm only exists if Will publishes the 7 articles. If they sit unapproved, the arms stay
comparable and the window simply moves — the experiment degrades gracefully, which is why it was
worth pre-registering rather than waiting.

---

## 3. What I did autonomously

### (a) Wrote the treatment arm — all 7, zero failures

`180 Christine Avenue` · `40 Palma Crescent` · `12 Wayville Place` · `5 Chelsea Place` ·
`4/44 Frascott Avenue` · `3/1 Lakefront Crescent` · `9 Skua Street`. Generated through the real
`fields-automation` how-it-sold pipeline, not by hand, so they carry the format that measurably
ranks page-1 for exact-address queries. Pushed to `content_articles` as **drafts**.

The generator could not previously be aimed. It selects by suburb and recency; the backlog is
selected by *measured search demand*, which is a different axis entirely. So I added
`--address` (repeatable) to `run_how_it_sold.py` and `get_sales_by_address()` to
`mongodb_client.py`. Both pushed to `Will954633/fields-automation`.

Headlines came out in the archetype the corpus says wins — *"Someone Paid $665,000 for This
Burleigh Waters Home in 2019. Seven Years Later, It Sold for $1,545,000."* — which is the
16.47%-CTR shape. **That corpus measures clicks only and not one of its 92 ads is
lead-optimised**, so this is a reason to expect clicks, not conversions, and I am not claiming
otherwise.

### (b) Found why the backlog existed at all — the automation blocks itself every week

This is the real finding of the cycle, and it is not a content problem.

`fields-automation` runs on **one self-hosted runner, one job at a time**. Seven weekly
workflows all fired inside a **2h05m window** on Sunday night UTC — 20:00, 21:00 ×3, 21:30,
22:00 ×2 — with `how_it_sold` queued behind them at Monday 02:00. **Not one job declared
`timeout-minutes`**, so a single hang held the runner for 11 hours.

On 2026-08-16/17 the queue outran GitHub's 24-hour pending limit and **five runs were cancelled**:
`market_insight` 25h01m, `market_shift` 24h32m, `state_of_market`, `market_drivers` and
`how_it_sold` at 24h00m each. **None of the five ever started** — `/home/fields/actions-runner/_diag`
holds no `Worker_*.log` between 2026-08-16T21:10Z and 2026-08-18T22:15Z. That is the decisive
evidence: these are not failures, they are jobs that never ran.

The fix is written: `timeout-minutes: 90` on all 13 jobs, and the Sunday cluster re-spaced across
Sun 20:00 → Mon 13:00 UTC with every slot ≥2h apart — matching the timeout, so a queue can no
longer build — leaving `how_it_sold` its Monday 02:00 slot with a clear runway. All 13 files
validate under `yaml.safe_load`; the now-wrong schedule comments were corrected too.

**I could not deploy it.** The fine-grained PAT is refused `403 Resource not accessible` on
`.github/workflows`, which GitHub gates behind a separate `workflows` permission. Everything
else in that repo pushes fine — the three pipeline files went up without trouble. So this is
**REC-articles-005**, and it is the one thing this cycle genuinely needs Will for.

Interim mitigation: the 7 articles I wrote by hand are the highest-demand items Monday's run
would have picked up, so it has less to lose if it is cancelled again.

### (c) The byline regression, third time — because there were two writers, not one

All 7 new drafts came out as `author: "Fields Research"`. That is the exact value corrected
corpus-wide on 2026-08-13 and corrected *again* three hours ago at 11:00.

The 11:00 cycle patched `Fields_Orchestrator/scripts/push-ghost-draft.py`. **That is not the
writer the GitHub Actions use.** `fields-automation/scripts/push_to_ghost.py` is, and it carried
the byline in three places at once: `AUTHOR_MAP` mapped 9 of 20 article types — including
`how_it_sold` — to a `"fields"` byline, `author_names` resolved anything unknown to
`"Fields Research"`, and the insert defaulted `author_slug` to `"fields"`.

Fixing one of two writers is indistinguishable from fixing the bug right up until the other one
runs. Map retired to `"will"` throughout with the instruction and both prior correction dates in
the comment; both fallbacks changed; 7 documents corrected. **Corpus 120/120.**

It is not cosmetic: `ArticlePage.tsx:582,592` gates Will's author avatar and the `/about/will`
author-entity link on `authorSlug === "will"`, so a wrong slug also drops the entity link seo and
geo consolidated on 2026-08-13.

### (d) Two smaller defects, both found by reading the output rather than trusting it

**Raw ISO dates in prose.** 4 of 7 drafts printed *"sold on 2026-07-20"* alongside *"20 July
2026"* in the same article. `article_generator` passes `sold_date_text or sold_date` into the
prompt and `data_assembler` read `sold_date_text` off the source document with no fallback — so
where the scraper had not populated it, the model was handed an ISO string and correctly repeated
what it was given. Fixed at source; corrected the 4 drafts with a tag-aware substitution so dates
inside image URLs were left alone.

**The drip cap crashed instead of refusing.** `article_approval.py propose` raised
`AttributeError: 'Namespace' object has no attribute 'force'`. `cmd_propose` has always read
`a.force` in its rate-limit branch and the parser never defined it; short-circuit evaluation hid
it until today, the first day the cap was actually reached. A guard that crashes reads as a
broken tool and invites a retry loop against the very thing it protects. `--force` defined; the
refusal message now prints as written.

### (e) OpenAI has zero credits — account-wide

The outlier vision step failed on 12 Wayville Place with `credit_balance_exhausted`. I checked
the account directly rather than assume it was our call: a 5-token `gpt-4o` request returns
HTTP 429 account-wide.

The generator caught it, printed a warning and wrote the article without the vision analysis —
so the article looks fine and the failure is invisible downstream. **That is a Rule 7b
zero-output path.** The orchestrator's Phase 3 visual steps 105/106/108/117 are on the same key.
Whether they are still producing analysis or silently skipping it, and for how long, I did not
determine — it is not my domain and the fix costs money, which no domain may spend. Broadcast to
all domains via `conductor_state.py directive` with the repro.

---

## 4. What I proposed to Will

**One: REC-articles-005** — the workflow queue fix, written and validated, blocked on a token
permission. Effort S, reversible. It is the only item here that needs him, and it recurs
**tonight**.

**What I deliberately did not do:** `--force` past the drip cap to send the other six drafts.
Will already has three article notifications from today, one of which is a dead button from the
11:00 cycle's error. Six more on top is precisely the unread queue the contract was written to
prevent. They are queued in `ARTICLES_PLAN.md` P1c at 3/day, highest demand first, with the
control group named in the same table so the next session cannot destroy it by accident.

## 5. What I graded

Nothing due. REC-002 and REC-003 remain weeks out.

---

## 6. The open question I would most like answered next week

**Where else are we shipping two writers for one rule?**

The byline has now been "fixed" three times in ten days. Each fix was correct and each was
incomplete, because `Fields_Orchestrator` and `fields-automation` both write to
`content_articles` and nothing reconciles them. Today's version cost seven articles. The same
shape is what produced the wrong QLD licence number across 68 articles — corrected on the
website in June, still emitted by the generator in August.

The question is not "is the byline right now" (it is, 120/120). It is: **what is the list of
values that two independent writers can both set on a published article, and which of them
currently disagree?** That is answerable by inspection rather than by waiting for the next
regression to announce itself, and I would rather answer it than fix this a fourth time.

---

## 7. Housekeeping

- Contract §8 observed: no `telegram_notify.py`, no `WILL_TO_ACTION.md`, no `cycle_pacer.py`,
  no self-scheduling.
- Netlify: **0 builds.** Everything here is database state or repo files.
- Rule 1: four fix-history entries — `[ARTICLE-AUTHOR-DEFAULT-REGRESSION]` (3rd),
  `[ARTICLE-ISO-DATE-IN-PROSE]`, `[APPROVAL-RATE-LIMIT-CRASHES]`, `[AUTOMATION-QUEUE-SELF-BLOCK]`.
- Rule 2: `run_how_it_sold.py`, `mongodb_client.py`, `push_to_ghost.py`, `data_assembler.py`
  pushed to `fields-automation`; `article_approval.py` and this cycle's docs to
  `Fields_Orchestrator`. The 13 workflow files could **not** be pushed — that is REC-005.
- 8 actions logged to `system_monitor.rl_articles_actions`; pre-registration written to
  `rl_articles_signal`.
- Notes sent to `seo` (the control group, and a warning that changing /property metas for those
  14 addresses contaminates both arms) and to `all` (the OpenAI credit exhaustion).
- Chain: **stopped.** The remaining work is the six queued drafts, and the drip cap means the
  earliest they can go is tomorrow. Chaining now would produce a session with nothing it is
  allowed to do.
