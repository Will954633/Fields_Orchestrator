# Market Context Engine — Build + Test-Run Evaluation

**Date:** 2026-09-03 · **Author:** Ops agent (autonomous build while Will was out)
**Verdict:** ✅ **Built and working end-to-end.** All 8 stages ran, produced correct, sourced,
editorially-compliant output, and indexed to the DB. One real bug was found and fixed during
testing. The system is ready for a full (unbounded) cycle on Will's review.

> Companion doc: [`DEV_MARKET_CONTEXT_ENGINE.md`](DEV_MARKET_CONTEXT_ENGINE.md) (the design this
> implements). This file reports what was actually built and how the test run went.

---

## 1. What was built

An 8-stage pipeline that **evolves** the existing fortnightly research cycle (per Will's scope
decision) into the demand-sensing → psychology → deep-research → suburb-context system. New code,
all under `14_Articles/Market_Research/scripts/`:

| File | Stage | Role |
|---|---|---|
| `mce_common.py` | — | Shared: Max-CLI runner (`claude -p`, JSON output, clean env), honesty rules, output discipline, QA helpers, cycle bookkeeping, paths |
| `mce_stage0_data.py` | 0 | Internal ground-truth pack (prices w/ reliability flags + live listing counts + search-intent demand/fear/velocity digest) |
| `mce_stage1_headlines.py` | 1 | 3-tier headline scan (national → QLD → Gold Coast), structured JSON |
| `mce_stage2_rank.py` | 2 | Deterministic topic scorer (reach·novelty·demand·answerability·suburb) → ranked slate |
| `mce_stage3_psychology.py` | 3 | Buyer + seller psychology synthesis, folds in the mindset brief |
| `mce_stage4_research.py` | 4 | Per-topic deep-research dossier refresh (web + internal join) |
| `mce_stage5_suburb.py` | 5 | Per-suburb contextualisation (core three) |
| `mce_stage6_index.py` | 6 | DB index + `audience_context_pack.json` + `INDEX.md` |
| `mce_qa.py` | 8 | Editorial/honesty QA gate + Telegram digest |
| `run_context_cycle.py` | — | Orchestrator: fortnight gate, `--test`/`--dry-run`, stage resume, one heartbeat (Rule 7/7b) |

Every stage: runs standalone (own `--cycle` CLI), reads/writes JSON artifacts under
`data/<cycle>/` (so a failed run resumes with `--start-stage N`), and has a **Rule 7b
zero-output assertion** (raises rather than silently succeeding on an empty result).

---

## 2. Test run — what happened

Command: `run_context_cycle.py --test` (bounded: all 3 headline tiers, but 1 topic + 1 suburb to
cap cost/time). Cycle `2026-09-03`.

| Stage | Result | Evidence |
|---|---|---|
| 0 Data pull | ✅ | 219 live listings; demand layer active (25 clusters, 20 content gaps) from `search_intent_analysis` (18,264 records, as at 2026-09-01) |
| 1 Headline scan | ✅ | **32 headlines**: national 12, QLD 11, Gold Coast 9 — all with outlet + URL + date |
| 2 Topic rank | ✅ | 16 candidates → slate of 10 (8 standing + **2 promoted, demand-discovered**: `prices-cooling`, `infrastructure-uplift`) |
| 3 Psychology | ✅ | 2,936-word buyer+seller brief, per-suburb, §9 present, QA-clean |
| 4 Deep research | ✅ (after fix) | Dossier refreshed to **22,500 chars**, Fields figures used verbatim, Premise-test verdict, sourced |
| 5 Suburb context | ✅ | Robina context 11,028 chars, §9 present, QA-clean |
| 6 Index | ✅ | 3 briefs indexed to `market_research_briefs`; `audience_context_pack.json` + `INDEX.md` built |
| 8 QA + digest | ✅ | 0 errors, 0 warns (after tripwire refinement); digest suppressed in test mode |

**DB writes confirmed:** `market_research_briefs` (dossier + psychology + suburb rows),
`mce_topic_slate`, `audience_context_pack` — all for cycle `2026-09-03`.

### Cost
All research bills the **Claude Max subscription** — **$0 marginal (metered) cost**. Notional
spend this bounded test ≈ **$6.30** (Stage 1 $2.69 + psych $1.97 + 1 topic $0.89 + 1 suburb
$0.75). Projected **full** cycle (8–11 topics + 3 suburbs): ≈ **$18–22 notional / cycle, all on
Max** → effectively free; the real budget is wall-clock (~30–60 min unattended).

---

## 3. The bug found and fixed (this is why we test)

**Symptom:** Stage 4's first two attempts failed — the model returned an 86-char, then a 2,650-char
conversational summary ("Refreshed and saved in place at `topics/…`. Want me to push it?") instead
of the dossier markdown.

**Root cause:** the deep-research child is the *Claude Code CLI*. Given an existing dossier and
"revise in place" phrasing, it behaved **agentically** — it believed it had edited the file and
reported completion, rather than returning the document as its reply (it has no write tool; the
parent writes files).

**Fix:** added an explicit `OUTPUT_DISCIPLINE` block ("you have no file-write access; do not say
you saved anything; your entire reply must be the document, first character onward"), reworded the
Stage-4 prompt away from "revise in place", and raised `max_turns` 34→50. Applied defensively to
Stages 3 and 5 too. Re-ran → clean 22,500-char dossier. The Rule-7b assertion is what caught it
(a silent pipeline would have written an 86-char "dossier").

**Second refinement:** the QA reliability tripwire raised 4 warnings — all **false positives**. The
flagged sentences were the ones *enforcing* the rule ("Q1→Q2 2026 drop **must not** be reported as
a real fall — both quarters unreliable") and *volume* drops (allowed; the flag governs *price*
only). Tightened the tripwire to require a `$` figure near the direction word **and** no guard
phrase → 0/0, while still catching a genuine "median fell from $X to $Y" violation.

Both logged in `logs/fix-history/2026-09-03.md`.

---

## 4. Output-quality assessment (the part that matters)

I read the generated content critically against our editorial rules. It is **strong** — not a
plausible-looking stub.

**Dossier** (`topics/national-market-turn-2026.md`):
- **Internal data used verbatim, not recalled** — Robina $1,492,500 +6.5%, Burleigh Waters
  $1,925,000 +6.9%, Varsity Lakes $1,400,000 +10.2%, with DOM and Q2 volumes exactly as supplied.
  This is the union-medians safeguard working.
- FACT/COMMENTARY tags throughout; every figure carries a source URL + date (RBA, ABS, Cotality,
  Westpac-MI, ATO, budget.gov.au).
- **Premise test** section: tests the popular "NG/CGT caused the turn" claim and returns *amplifier,
  not trigger*, with the reasoning (turn predates budget; tax effective 1 Jul 2027).
- **Honest limitations**: flags per-city August figures as needing primary-PDF verification, notes
  PropTrack August not yet released, preliminary-vs-final clearance caveat.
- **For our audience** section frames the national-vs-local divergence as a *data contrast*, "report
  the divergence, do not advise on it", ranges not single valuations — Rule 5 respected.

**Suburb context** (`suburb_context/robina_2026-09-03.md`):
- Leads with volume (the reliable signal), explicitly refuses to narrate the noisy Q1→Q2 median
  drop, tags `[FIELDS]`/`[VERIFIED]`/`[INFERRED]`, and its §9 says "We did NOT conclude Robina
  prices are falling."

**Psychology brief** (`briefs/current/2026-09-03_psychology.md`):
- Both sides (sellers *and* buyers — the buyer side the mindset brief lacks), grounded in our
  search-intent fears (crash n=72, price-drop n=39) and Reddit sentiment, per-suburb only where
  data supports, with a binding §9 and a sources list.

**Topic discovery** (the headline requirement): the scorer independently surfaced `supply-and-
approvals` as the loudest cross-tier theme and promoted `prices-cooling` + `infrastructure-uplift`
from the Gold Coast tier — genuinely topical, demand-backed choices, not hand-fed.

---

## 5. What's production-ready vs. what needs your call

**Ready now:** all 8 stages, the artifact/resume plumbing, the DB contract, the QA gate, the Max-CLI
research recipe, the Rule-7b assertions, the heartbeat wiring.

**Deliberately NOT done (your decisions — §10 of the dev doc):**
1. **Not scheduled.** I did **not** install or swap any cron. MCE is meant to replace
   `run_research_cycle.py`'s `0 12 * * 0`; swapping the fortnightly job is your call. (Install line
   ready in §6 below.)
2. **Not pushed to prod content.** Nothing published — research + human-reviewed publish, as agreed.
3. **Stage 7 (draft content) not built** — held for after you trust the research layer (dev-doc
   Phase 4).
4. **Slate authority:** currently auto-selects promoted topics; recommend you eyeball the slate
   one-pager for the first ~3 real cycles before it drives unattended spend.
5. **Full unbounded cycle not yet run** — the test capped topics/suburbs to 1 each to bound cost. A
   full run (all standing + promoted topics, all 3 suburbs) is the natural next step once you've
   reviewed this.

---

## 6. Recommended next steps (in order)

1. **Review the three sample outputs** above — confirm the voice/quality is what you want.
2. **Run one full cycle** to see the whole slate + all three suburbs:
   `python3 scripts/run_context_cycle.py --force --notify` (≈30–60 min, ~$20 notional on Max; sends
   you the Telegram digest).
3. **If happy, schedule it** (replaces the old research cron):
   `0 12 * * 0  cd …/Fields_Orchestrator && set -a && source .env && set +a && /home/fields/venv/bin/python3 14_Articles/Market_Research/scripts/run_context_cycle.py >> logs/mce_cycle.log 2>&1`
   (fortnightly via the even-week gate; retire the `run_research_cycle.py` line).
4. **Then** decide on Stage 7 (auto-drafting suburb content for your review).

---

## 7. Files produced this test cycle (for review)

- `topics/national-market-turn-2026.md` — refreshed dossier (22.5 KB)
- `briefs/current/2026-09-03_psychology.md` — buyer+seller psychology (21 KB)
- `suburb_context/robina_2026-09-03.md` — Robina context (11 KB)
- `briefs/current/2026-09-03_national-market-turn-2026.md` — dated cover brief
- `data/2026-09-03/` — all intermediate artifacts (internal_pack, headlines_raw, topic_slate,
  audience_context_pack, qa_report)
- `INDEX.md` — regenerated
- DB: `market_research_briefs`, `mce_topic_slate`, `audience_context_pack` (cycle 2026-09-03)
</content>
</invoke>
