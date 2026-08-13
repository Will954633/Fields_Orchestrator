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

Accuracy is measured and respectable within the design envelope (MAE 8.05%, 80% band
±12.2%, n = 581 — `16_Valuation/accuracy/2026-08-08-figures.md`). **59.4% of the live
for-sale book carries no valuation** (126 of 212, 2026-08-13) — but read the correction
below before drawing the obvious conclusion from that number, because the domain's first
cycle showed the obvious conclusion is wrong.

⚠ **Corrected 2026-08-13 by the domain's own first cycle.** This section originally said
76 of the 126 failures "record no reason whatsoever" and that we could not tell a deliberate
refusal from a crash. **That was false, and it was a defect in our instrument, not in the
data.** All 76 carry a machine-readable reason under keys the first sensor did not read
(`directional_reason`, and the `confidence` tier itself); all 76 have `computed_at`; none is
a crash. The sensor has been fixed. Keep the correction visible — it is the cleanest example
in this domain of Rule 8 applied to our own measurement rather than to the database.

**What is actually true:** the 59.4% is overwhelmingly the method *correctly refusing to
speak*. Against the population the house method claims to serve — classified House, inside
the design envelope, n = 69 — coverage is **78.3%**, and it is even across suburbs (Robina
77.6%, Varsity Lakes 81.8%, Burleigh Waters 77.8%). **Burleigh Waters' alarming 16.7% is a
composition effect**: 45 of its 54 listings are attached dwellings or above the ceiling.

So the honest coverage gap on the house method is **15 properties**, of which about 9 are a
sourceable missing input. There is no large coverage win hiding here — which is itself the
finding, and it redirects this domain away from coverage and toward the two surfaces that
are genuinely thin: **attached dwellings (28.3% valued, n = 113, dominated by empty
comparable pools)** and comp-pool depth.

## 2. Current state — what is ON, OFF, or PAUSED, and deliberately so

| Thing | State | Why |
|---|---|---|
| Comparable-sales method (`reconciled_valuation`) | **LIVE — this is the number** | Weighted mean of adjusted comparables. It is what property pages and appraisals show. |
| CatBoost `iteration_08_valuation` | **Not in use** | Separate, inferior model. Do not confuse the two; do not revive it. |
| Design envelope $1M–$2M, detached houses | **ON, deliberately** | Structural, not a policy choice — the estimate cannot exceed its priciest comparable. Outside it we suppress **both** figure and range. This is correct behaviour and is not to be "fixed". |
| Waterfront | **Out of scope by decision** | Varsity Lakes has only 18 waterfront comparables. Decided, not open. |
| Attached dwellings — **house** method | **Excluded by decision** | They inflate every published accuracy figure. `05-what-we-exclude.md`. |
| Attached dwellings — **own** method | **LIVE since 2026-08-10** | `[UNITS-VALUATION-LIVE]` — units/townhouses now get a measured range of their own. ⚠ This is why `05-what-we-exclude.md` is no longer the whole story, why the $1M–$2M envelope must never be applied to a unit, and why this surface (28.3% valued, n = 113) is now the domain's largest honest opportunity. |
| The ±12.2% band | **An EMPIRICAL 80% band** | NOT a confidence interval. It was called a "90% CI" on two live pages until 2026-08-07, when it actually contained the sale 58% of the time. |
| `16_Valuation/` folder governance | **Binding** | Experiment record before any method change ships; append-only. Predates this domain and outranks it. |
| This domain's write access | **OFF in week one** | See §4. Deliberate, and Will's call to widen. |

## 3. Goals — what good looks like

1. **Coverage is always reported against the addressable population, never the raw book.**
   The raw 40.6% is not a defect rate — it counts every correct refusal as a failure. The
   number that means something is 78.3% of the 69 homes the house method serves. Report
   both, and never let the raw one travel alone.
2. **Coverage rises where it honestly can** — i.e. where the blocker is a missing input we
   can source (floor area 7, land size 2 on the house method), not where the method is
   correctly refusing. The attached-dwelling surface (28.3%, n = 113) is the larger prize.
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

- [ ] **Week two: widen §4 to allow writes?** ⚠ The original version of this question asked
      for permission to stamp reasons onto the "76 silent failures" — a job that turned out
      not to exist. Cycle 1 needs no new write access to have been useful, which is evidence
      the read-only constraint is cheap. Ask again only when there is a specific write worth
      naming.
- [ ] **Is coverage or accuracy the priority?** They pull in different directions: the
      cheapest way to lift coverage is to value homes we currently refuse, which lowers
      average accuracy. Stated preference beats the domain guessing.
- [x] ~~**Burleigh Waters is at 16.7% coverage against Robina's 55.6%.**~~ **Answered by
      cycle 1:** composition effect, not a suburb problem. On the homes the method is built
      for it performs identically to Robina (77.8% vs 77.6%). A targeted data-sourcing
      effort there is **not** warranted.
- [ ] **`16_Valuation/README.md` indexes `methodology/02-design-envelope.md`, which does not
      exist on disk.** Should the domain write it from CLAUDE.md's envelope section, or is
      the index line the thing to remove?

## 8. Changelog

- 2026-08-13 — created. Domain added to the weekly RL fleet as the first non-marketing
  vertical. Week one deliberately read-only (§4). Baseline at creation: 86/212 valued
  (40.6% of the raw book; **78.3% of the 69 addressable homes**), 126 unvalued.
- 2026-08-13 — **corrected after cycle 1.** The "76 unvalued with no recorded reason"
  premise this brief was written on was an artefact of the sensor reading one of three
  reason fields. Retired; §1, §3 and §7 rewritten; Burleigh Waters question answered and
  closed. The domain's first act was to falsify its own brief, which is the system working.
