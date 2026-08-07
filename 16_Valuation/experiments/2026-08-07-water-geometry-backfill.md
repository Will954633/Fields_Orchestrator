# 2026-08-07 — OSM water geometry backfill, and where the water premium actually stops

**Append-only record.** Supersedes the "53% coverage blocker" noted in
`2026-08-07-band-width-investigation.md` Part 5.

---

## What was done

Backfilled `osm_location_features.water_features` across all three target suburbs, then wired
`classify_water_relationship()` into comparable cohort selection in `precompute_valuations.py`.

**Coverage: 53% → 100%** (23,748 properties written, 0 failures). Homes falling back to the photo
signal for want of geometry dropped from **332 of 625 to 2 of 586**.

## ⚠ Why it is one API call, not 24,000

The original enricher issued one Overpass query **per property**. Water geometry does not vary by
property — only the distance to it does. So the backfill fetches every water element in the region
once (537 elements, ~78s) and computes distances locally against a 250 m grid index of 16,072
segments.

**One request replaced ~24,000.** Runtime: minutes, not days, and no load on a free public service.

⚠ **The whole `overpass-api.de` family — including `lz4.` and `z.` — returns 406 to this VM**,
regardless of User-Agent. `overpass.kumi.systems` and `overpass.private.coffee` both work. Removing
the User-Agent does not help; without one you get 406 everywhere.

## ⚠ Validated against the API before trusting it

The local computation was checked against properties whose distance the per-property API had already
stored. **First attempt: 15/18 agreement**, with three properties computing up to 200 m too far —
all in Burleigh Waters. Cause: the regional query omitted `drain` and `ditch`, which `WATER_TYPES`
handles, and Burleigh Waters is laced with drainage canals.

After widening the tag set: **29/30 agreement, median delta 0.0 m.** The one difference computes
water *closer* than the stored value — the widened tag set finding a drain the original missed.

**Keep this check.** A regional query that silently omits a water type produces confidently wrong
distances everywhere that type occurs.

## ⚠ `lakefront` did not previously exist

The original `extract_water_features()` sets `waterfront_type` for canal, coastline and river only.
**A home on a lake got `waterfront_type: 'none'` and `waterfront_premium_eligible: False`.** Two of
our three target suburbs are lake suburbs. After the backfill, **1,817 properties (7.7%) classify as
`lakefront`** — a class that was previously undetectable.

`9 Laura Place, Varsity Lakes` — the worst outlier in the whole investigation at +87% — is one of
them: 22 m from a water body, genuinely lakefront, and previously valued off a cohort that could not
represent it.

## The threshold, measured rather than assumed

30 m was chosen by analogy to the river rule. It was then tested against 807 sold houses — median
price per m² of floor area by distance to water:

| distance | n | median $/m² | vs 400m+ |
|---|---|---|---|
| 10–20 m | 19 | 9,206 | **+13.6%** |
| 20–30 m | 64 | 9,106 | **+12.4%** |
| **30–50 m** | 32 | 7,369 | **−9.0%** |
| 50–80 m | 73 | 8,017 | −1.0% |
| 80–120 m | 102 | 8,229 | +1.6% |
| 120–200 m | 203 | 8,239 | +1.7% |
| 200–400 m | 285 | 8,062 | −0.5% |
| 400 m+ | 29 | 8,102 | — |

**The premium is ~+13% inside 30 m and gone beyond it.** The analogy was right, and now it is
evidence.

This also settles the cohort design: **beyond 30 m there is no measurable water premium**, so
`water_view` and `dry` are pooled rather than split. They measured statistically indistinguishable
(median error −0.0% against −0.2%), and splitting them would thin every pool for no accuracy gain.
Only `waterfront` is kept separate.

## Classification after the backfill, n = 586

| class | n | median error | MAE | over-valued |
|---|---|---|---|---|
| waterfront | 24 | +2.4% | 10.5% | 58% |
| **water_view** | 202 | **−0.0%** | **8.6%** | 50% |
| dry | 360 | −0.2% | 9.3% | 49% |

And the defect, confirmed on full geometry:

| the old flag says waterfront | n | median error | MAE | over-valued |
|---|---|---|---|---|
| geometry agrees | 23 | +2.3% | — | — |
| **geometry disagrees** | **30 (57%)** | **+10.3%** | **14.4%** | **83%** |

## Observed effect on live properties

| property | before | after |
|---|---|---|
| 9 Laura Place (sold $1,298,000) | valued $2,141,873 (+87%) | **no figure** — lakefront, and Varsity Lakes has only 18 waterfront comps |
| 20 Washington Court (sold $1,350,000) | +46% | reclassified `dry` (205 m from a stream), now +30% |
| 4 Springvale Street | — | `water_view` at 106 m, unchanged cohort behaviour |

Refusing to value 9 Laura Place is the correct outcome, not a regression: waterfront is out of scope
(`[[waterfront_out_of_scope]]`) and a wrong number is worse than no number.

## Cohort sizes after the change

| suburb | waterfront | water_view | dry |
|---|---|---|---|
| Robina | 34 | 127 | 232 |
| Varsity Lakes | 18 | 82 | 176 |
| Burleigh Waters | 32 | 124 | 166 |

⚠ **Varsity Lakes has only 18 waterfront comparables.** Genuinely waterfront homes there will often
fail the minimum-comps test and return no figure. That is the intended behaviour while waterfront is
out of scope, but it should be watched — if the refusal rate is material, the answer is a waterfront
arm of the business, not a looser cohort.

## Not yet re-measured

The headline accuracy figures in `accuracy/2026-08-07-figures.md` predate this cohort change. **The
backtest must be re-run** before those figures are updated, since the cohort filter changes which
comparables every property sees.
