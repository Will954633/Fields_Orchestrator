# 16_Valuation — the valuation domain

**Valuation is the most important thing Fields does.** Everything else — the off-market report, the
appraisal, the property page, the mini-site — is a wrapper around a number and a range. If that
number is wrong, or the range around it is dishonest, nothing else we build matters.

This folder is the single home for how the valuation works, what we have tested, what we found, and
what we decided. **Every change to the method gets a dated record here before it ships.**

---

## The rule

> **No change to valuation methodology ships without a dated experiment record in
> `experiments/` and, if it changes what a reader sees, a decision record in `decisions/`.**

A fix-history entry is not enough. Fix history answers *"what broke and when"*; this folder answers
*"why is the method the way it is, and what evidence supports it"*. The two serve different readers.

---

## Layout

| folder | what goes in it | naming |
|---|---|---|
| `methodology/` | How the method works **today**. Living documents — edit in place, bump `Last verified`. | `NN-topic.md` |
| `experiments/` | What we tested, when, on what sample, and what came back. **Append-only** — never edit a result. | `YYYY-MM-DD-slug.md` |
| `decisions/` | Choices made and the reasoning, especially where evidence was ambiguous or the call was Will's. | `YYYY-MM-DD-slug.md` |
| `accuracy/` | Published accuracy figures and the exact command that produced each. | `YYYY-MM-DD-figures.md` |

**Experiments are append-only.** A superseded result stays, with a pointer to what replaced it. The
history of what we believed and when is itself evidence — twice in this domain a "finding" turned
out to be an instrumentation artefact, and the only way to catch that class is to be able to read
back what the instrument was doing at the time.

## Every record carries

- **Date** (AEST) and what produced it — the **exact command**, not a description of it
- **Sample size and scope** — suburb, property type, price band, and the date range of sales
- **What would falsify it**, where that is knowable
- Links to the code that implements it

---

## ⚠ Standing traps in this domain

Read these before running any measurement. Each cost real time or produced a wrong published claim.

1. **`--price-filter none` is mandatory for off-market work.** The default `sale` anchor prunes
   comparables using the subject's own sale price — target leakage.
2. **A backtest is only valid where its firing rates match production.** An attribute can fire on
   80% of backtest comparables and 0.2% of production ones; a conclusion about it is then meaningless.
   Check firing rates first, every time.
3. **The backtest subject is richer than the production subject.** Sold homes carry photo-derived
   attributes (`renovation_quality_score`, `kitchen_score`, `number_of_stories`) ~89% of the time;
   off-market homes carry them **0%** of the time. Use `--blind-subject` for any figure that will be
   quoted about the off-market product.
4. **The range is an EMPIRICAL 80% band (±12.2%), not a confidence interval.** It was a flat ±12%
   until 2026-08-08, and two live pages described that as a "90% confidence interval" until
   2026-08-07 — it contained the sale 58% of the time. That language must never return anywhere,
   including appraisal PDFs and ad copy.
5. **The design envelope is structural, not a policy choice.** The estimate cannot exceed its
   priciest comparable, so the method cannot leave $1M–$2M.
6. **`_EMPIRICAL_80_BAND_PCT` and `_ADJUSTMENT_RELIABILITY` are OUTPUTS of the backtest**, not
   constants to tune. Re-derive both after any method change.

---

## Current position, in one line

**MAE 8.05%, 80% band ±12.2% ($391,904 on a $1.6M home), n = 581.** Down from $603,574 at the start
of this work. `accuracy/2026-08-08-figures.md` is the only quotable source.

## Index

### Methodology — how it works today
- `01-how-the-valuation-works.md` — **start here.** The pipeline end to end
- `02-design-envelope.md` — why $1M–$2M, and why it is structural
- `03-the-range.md` — what the band is, what it is not, and its measured coverage
- `04-water-and-cohorts.md` — waterfront vs water view vs dry; geometry decides frontage
- `05-what-we-exclude.md` — attached dwellings, incomplete records, and the blind-subject rule

### Experiments — append-only, newest first
- `2026-08-08-comparable-selection.md` — the post-adjustment filter keyed to the cohort median
- `2026-08-08-where-the-headroom-is.md` — the ceiling is selection, not coverage (+ a correction)
- `2026-08-07-enrichment-contribution-scoping.md` — four enrichment hypotheses, all rejected;
  the noise floor
- `2026-08-07-water-geometry-backfill.md` — 53% → 100% coverage; where the water premium stops
- `2026-08-07-band-width-investigation.md` — the original investigation (parts 1–6)
- `2026-08-07-outlier-list.md` — the 50 worst misses, with links

### Decisions
- `2026-08-07-range-meaning.md` — coverage vs width; the band became an empirical 80% band

### Accuracy
- `2026-08-08-figures.md` — **CURRENT.** Reproduction commands and the rejected-hypotheses list
- `2026-08-07-figures.md` — superseded

---

## ⚠ What has been tested and rejected

Do not re-run these. Each is recorded with its measurement:

adaptive band width · fewer-but-better comparables · nearest-by-distance selection · refitting all 19
adjustment multipliers · rescaling beach/street premiums · satellite analysis as an accuracy lever ·
photo-derived quality attributes · the floor-area "ruler mismatch"

## What is still open

1. **Attributes we hold no data on for any property** — aspect, outlook, slope, frontage width,
   noise exposure. The only surviving explanation for the residual displacement.
2. **48.7% of off-market homes have no floor area at all** — the largest adjustment, missing on half
   our subjects.
3. **Waterfront** — out of scope by decision; Varsity Lakes has only 18 waterfront comparables.

---

Related: `logs/fix-history/` for incident records, `15_Off-Market/Page_Redesign_V4/Product/` for how
valuation is *presented* to a reader.
