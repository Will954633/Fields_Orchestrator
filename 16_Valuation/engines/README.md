# The valuation engines — what exists, and how they differ

Fields runs **more than one valuation method**, and they are not variants of one code
path — they share essentially no code and write to different places. This file is the map.
It is the answer to "do we have different versions of the valuation?": **yes, and here they
are.** Mapped 2026-08-20 (agent survey with file:line verification).

> **The single most important fact:** the **house** engine writes `valuation_data` on the
> property document; the **unit** engine writes a *separate* `unit_valuations` collection and
> **never** touches `valuation_data`, by design, so the two can always be told apart
> downstream. They are different methods for different property types, not two settings of
> one engine.

---

## At a glance

| engine | values | method | point | range | writes | status |
|---|---|---|---|---|---|---|
| **1. House comparable-sales** | detached houses, **$1M–$2M** | ~19 per-feature $ adjustments on a sold cohort | **weighted mean** | per-suburb 80% band **±11.2–14.0%** | `valuation_data` on the property doc | **LIVE** — nightly (pipeline step 18) + on-demand per subject |
| **2. Unit comparable-sales** (`UnitValuer`) | attached: units, apartments, townhouses, villas, duplexes | same-building sale, tiered out, **time-deflated** by an attached price index | **median** | per-suburb P80 band **±13.6–21.9%** | `Gold_Coast.unit_valuations`, keyed by slug, `engine:"unit_comparables_v1"` | **LIVE** — daily 04:30 |
| **3. Unit statutory comparables** | same attached dwellings | ≥3 same-bedroom sales, ≤6 months, ≤5km (QLD POA CMA definition) | median | low/high (light adj.) | own collection, `engine:"statutory_comparables_v1"` | **LIVE** — daily 05:15 |
| **4. CatBoost `iteration_08`** | houses (ML) | gradient-boosted regression | single figure | — | (was a parallel field) | **DEAD** — retired 2026-08-05, pipeline step 6 disabled |
| **5. `SlotResolver` Tier-3 unit range** | units (old) | bedroom-median ±10%, **no type filter** | median | ±10% | (off-market slot) | **DEAD** — replaced by engine 2 (gave 3-bed *house* medians to 3-bed units, +23–33%) |

## Where the code lives

| engine | code |
|---|---|
| 1. House | `/home/fields/Feilds_Website/07_Valuation_Comps/precompute_valuations.py` — `precompute_property_valuation()` :3390; write :4520. Documented in **this folder** (`../methodology/`, `../experiments/`, `../accuracy/`). |
| 2. Unit | `/home/fields/Fields_Orchestrator/15_Off-Market/Units/scripts/unit_valuation.py` — `UnitValuer.value()` :446; batch `precompute_unit_valuations.py`. Documented in **`15_Off-Market/Units/`** (its own README + `research/`). |
| 3. Statutory | `15_Off-Market/Units/scripts/statutory_comparables.py` :47; `precompute_statutory_comparables.py`. Imports from `unit_valuation.py`. |
| 4. CatBoost | retired; dead-code comments at `precompute_valuations.py:3708-3711`, `valuation.mjs:706`. |

## How house and unit engines differ (the detail)

| dimension | House (engine 1) | Unit (engine 2) |
|---|---|---|
| Property type | detached only; attached explicitly excluded (`:3649`) | attached only; `classify_dwelling=="attached"` (`precompute_unit_valuations.py:76`) |
| Price envelope | **hard $1M–$2M**, suppress figure+range outside (`:2087`, `:4169`); >$2.5M `directional_only` | **none** — gated on comparable availability + per-suburb accuracy instead |
| Comparable selection | sold cohort, adjusted for feature differences, NPUI similarity | **same-building sale first**, tiered outward, stop at first tier with ≥3 comps (`:388-443`) |
| Primary adjustment | ~19 dollar lines: land/floor $/m², beds, baths, car, pool, storey, reno, water view, cladding, kitchen, AC, age, condition + beach/street/micro/golf premiums | **time-deflation** to today via a bedroom-matched attached price index (`deflate()` :302); floor area only a refinement, not a gate |
| Reconciliation | **weighted mean** (5-factor weights) (`w_mean` :2118) | **plain median** of adjusted comps (`st.median` :473) |
| Band | empirical 80% band, per suburb ±11.2 / 12.2 / 14.0% | empirical P80 band, per suburb ±13.6 / 14.6 / **21.9%** (units are less predictable) |
| Confidence signal | tier high/med/low/very_low from CV+n+verification (**uncalibrated, not shown**) | no tier; a boolean **`publishable`** gate (within-10% ≥55%) |
| Refusal | returns `exclusion_reason` (acreage, missing floor area, misclassified) | **declining is a valid output** — never widens the net to force a number (`:449`, `:463`) |
| Output | `valuation_data` object on `Gold_Coast.<suburb>` doc | separate `Gold_Coast.unit_valuations`, keyed by slug — **never `valuation_data`** (`precompute_unit_valuations.py:6-19`) |
| Schedule | nightly pipeline step 18 + `run_subject_valuation.py` on demand | daily 04:30 cron |
| Shared code | **none** — house imports only `shared.waterfront`/`shared.price`; unit family imports only `unit_valuation.py`. No `resolve_floor_area`, `calculate_confidence`, or band constants in common. Each reimplements. |

## Two clarifications that correct common confusion

- **`reconciled_valuation` is NOT deprecated as a computation.** It is the live output of the
  house engine, computed on every in-envelope house. What is deprecated is *displaying it as a
  headline single figure* (editorial rule) — not calculating it. The range carries the public
  assessment; the point figure is the centre of it.
- **CatBoost `iteration_08` is fully dead**, retired 2026-08-05, pipeline step 6 `enabled:
  false`. Remaining `iteration_08` string hits are field-reads/comments/backfill, not the model
  running. CLAUDE.md's note that `reconciled_valuation` "is NOT the CatBoost model" is accurate:
  the two ran in parallel and only the comparable-sales one survived.

## Open / unverified

- Whether `SlotResolver` still serves any live **house** path (only its unit role is confirmed
  replaced).
- The unit engine has **no strata / body-corporate / floor-level / aspect** adjustment line —
  plausibly a gap for high-rise, tracked in `15_Off-Market/Units/research/`.

## Related

- `../README.md` — the domain overview and current status
- `../surfaces.md` — which user-facing page reads which engine, and whether they agree
- `15_Off-Market/Units/README.md` — the unit engine's own home and development plan
- `../METHODOLOGY_REVIEW_TASK.md` — the open review (house bands are the live concern)
