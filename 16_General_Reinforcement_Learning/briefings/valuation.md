# VALUATION (product quality — the number and the range) — standing brief

**Last updated:** 2026-08-13 by Will + Claude (domain created)
**Review cadence:** weekly

> This document is the domain's **authorisation envelope**, not just background reading.
> Work that falls inside the Direction and Standing Authorisations below is executed
> autonomously and reported afterwards. Work outside it is proposed and waits.
> A stale brief is therefore expensive: the domain keeps working but stops being able to
> act on anything new.

---

## 1. Direction — what we are doing here and why

The other six domains are all top-of-funnel. They compete to bring more people to a number.
**Nobody was checking the number.** That is why this domain exists, and it is the first one
pointed at the product rather than the traffic.

Valuation is the most important thing Fields does. The off-market report, the appraisal, the
property page and the mini-site are all wrappers around an estimate and a range. If the
estimate is wrong, or the range around it is dishonest, none of the marketing matters — and
the failure lands in a document with our name on it that we posted to somebody's house.

Right now the headline problem is **coverage, not accuracy**. Accuracy is measured and
respectable within the design envelope (MAE 8.05%, 80% band ±12.2%, n = 581 —
`16_Valuation/accuracy/2026-08-08-figures.md`). But **59.4% of the live for-sale book
carries no valuation at all** (126 of 212, 2026-08-13), and Burleigh Waters is at 16.7%
coverage. A method that is accurate on the 40% it will speak about, and silent on the rest,
limits every downstream product to a minority of addresses.

The first job is therefore diagnostic: **understand the shape of the 59.4% before proposing
anything to fix it.** Some of it is the method correctly refusing to speak (outside the
design envelope, attached dwelling, acreage) and that is a *success* being counted as a
failure. Some of it is missing input data we could actually go and get. And on 2026-08-13
the sensor found that **76 of the 126 — 60% of all failures — record no reason whatsoever**.
That last group is the one that matters most, because we currently cannot tell a deliberate
refusal from a crash.

## 2. Current state — what is ON, OFF, or PAUSED, and deliberately so

| Thing | State | Why |
|---|---|---|
| Comparable-sales method (`reconciled_valuation`) | **LIVE — this is the number** | Weighted mean of adjusted comparables. It is what property pages and appraisals show. |
| CatBoost `iteration_08_valuation` | **Not in use** | Separate, inferior model. Do not confuse the two; do not revive it. |
| Design envelope $1M–$2M, detached houses | **ON, deliberately** | Structural, not a policy choice — the estimate cannot exceed its priciest comparable. Outside it we suppress **both** figure and range. This is correct behaviour and is not to be "fixed". |
| Waterfront | **Out of scope by decision** | Varsity Lakes has only 18 waterfront comparables. Decided, not open. |
| Attached dwellings (units, townhouses, duplexes) | **Excluded by decision** | They inflate every published accuracy figure. `05-what-we-exclude.md`. |
| The ±12.2% band | **An EMPIRICAL 80% band** | NOT a confidence interval. It was called a "90% CI" on two live pages until 2026-08-07, when it actually contained the sale 58% of the time. |
| `16_Valuation/` folder governance | **Binding** | Experiment record before any method change ships; append-only. Predates this domain and outranks it. |
| This domain's write access | **OFF in week one** | See §4. Deliberate, and Will's call to widen. |

## 3. Goals — what good looks like

1. **Every unvalued property has a recorded, correct reason.** The 76 silent failures go to
   zero — not by valuing them, but by knowing why we didn't. This is the week-one goal and
   it is achievable without changing the method at all.
2. **Coverage rises where it honestly can** — i.e. where the blocker is a missing input we
   can source (floor area, land size), not where the method is correctly refusing.
3. **No live claim about valuation accuracy or the range is false.** Zero instances of "90%
   confidence interval" language, zero unreproducible accuracy figures in public copy.
4. **Accuracy does not drift** without somebody noticing in the same week it moves.

## 4. Standing authorisations — SHIP THESE WITHOUT ASKING

⚠ **Week one is deliberately READ-ONLY.** This is not distrust — a valuation edit propagates
into appraisal PDFs and posted mail within a day, and Will wants to read one full cycle of
this domain's reasoning before that door opens. If the constraint is costing something real,
say so in a recommendation and he will widen this section.

- **Run the sensor** (`valuation_signal.py`) and read `system_monitor.rl_valuation_signal`.
- **Run backtests** (`scripts/valuation_backtest.py`) — read-only measurement. Always
  `--price-filter none` for off-market work, `--blind-subject` for any off-market claim,
  and scope with `--limit`/`--suburb` so it cannot eat the 40-minute budget.
- **Read anything** — code, database, `16_Valuation/`, fix history, live pages.
- **Write records:** the cycle doc, an append-only `16_Valuation/experiments/` record of any
  measurement you performed, and `rl_valuation_actions`.
- **Nothing else.** No writes to property documents, no edits to `precompute_valuations.py`,
  no method constants, no bulk recompute, no website changes — however obvious the fix looks.
  Propose it instead.

## 5. Off-limits — never, regardless of anything else

Global prohibitions always apply and are never granted by a brief: spending money, editing
the crontab, editing monitoring/health-check code or `job_runs`, contacting a real person,
deleting data, Gold Coast go-live, flipping a master kill-switch.

On top of those, permanently — these do **not** become autonomous when §4 is widened:

- **No methodology change without a dated `16_Valuation/experiments/` record before it
  ships**, plus a `decisions/` record if it changes what a reader sees. A fix-history entry
  is not a substitute. Experiments are append-only — supersede, never edit.
- **Never widen the design envelope to lift coverage.** A wider envelope does not make the
  method work outside itself; it just stops us admitting that it doesn't.
- **Never change a published accuracy figure** without re-deriving it with the exact command
  recorded in `16_Valuation/accuracy/`. Those numbers appear in public copy.
- **Never run a bulk valuation recompute unattended.** It rewrites live pages.
- **Never re-run a rejected experiment** as if it were new: adaptive band width ·
  fewer-but-better comparables · nearest-by-distance selection · refitting the 19 adjustment
  multipliers · rescaling beach/street premiums · satellite analysis · photo-derived quality
  attributes · the floor-area "ruler mismatch".

## 6. Context the agent cannot get from data

- **A suppressed valuation is the system working.** The envelope exists because a weighted
  mean of adjusted comparables regresses to the middle of its pool. Of 9,232 valued houses
  our highest-ever estimate was $2,494,914, while real sales reach $5,100,000. Counting
  suppressions as a coverage failure would be reading a safety feature as a bug.
- **A ceiling-pinned home looks identical to a correct one in our own output.** You cannot
  detect one from the number; do not try.
- **Confidence tiers are not calibrated across bands** (within-10%: high 55%, medium 46%,
  low 56%, very_low 61% — non-monotonic). They behave better inside the envelope. Never
  render a bare tier to a reader as though it ranked reliability.
- **Twice in this domain a "finding" turned out to be an instrumentation artefact.** That is
  why experiments are append-only and why firing rates get checked before conclusions.
- **The three copies of `directional_only` disagree** (`confidence`, `summary`, `metadata`),
  and the `metadata` one is written `False` too, so its fill count is not its true count.
  The sensor reports all three plus the disagreement rather than picking a winner.
- **Coverage is measured against `Gold_Coast`, never `Gold_Coast_Currently_For_Sale`** —
  the latter is a deprecated mirror with 83 docs against 212 and it disagrees.

## 7. Open questions — Will to answer

- [ ] **Week two: widen §4 to allow diagnosis-driven writes?** Specifically: writing a
      correct `exclusion_reason` onto properties that currently record none. It is the
      lowest-risk write available (a reason string, never a figure) and closes goal 1.
- [ ] **Is coverage or accuracy the priority?** They pull in different directions: the
      cheapest way to lift coverage is to value homes we currently refuse, which lowers
      average accuracy. Stated preference beats the domain guessing.
- [ ] **Burleigh Waters is at 16.7% coverage against Robina's 55.6%.** Is that suburb worth
      a targeted data-sourcing effort, or is it structurally outside the envelope (premium
      family suburb, prices above $2M) and correctly silent?
- [ ] **`16_Valuation/README.md` indexes `methodology/02-design-envelope.md`, which does not
      exist on disk.** Should the domain write it from CLAUDE.md's envelope section, or is
      the index line the thing to remove?

## 8. Changelog

- 2026-08-13 — created. Domain added to the weekly RL fleet as the first non-marketing
  vertical. Week one deliberately read-only (§4). Baseline at creation: 86/212 valued
  (40.6%), 126 unvalued, of which 76 record no reason; Burleigh Waters 16.7%.
