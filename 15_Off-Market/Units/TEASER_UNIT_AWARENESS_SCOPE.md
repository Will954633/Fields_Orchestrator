# Making the Owner teaser (and article) unit-aware — scope

**Status:** BACK BURNER (parked 2026-08-26). Pursue **Option 2 (full parity)** *after* the
first detached teaser batch is sent to Pronto and the first trial is underway (Will,
2026-08-26).

**Why this exists:** the ad runs across the whole core market, but the Owner teaser and its
full article are built on the **detached house engine only** (`valuation_data`,
`subject_trajectory`, house comps). Units get nothing today. Measured 2026-08-26:

| | Homes | Article-servable today |
|---|---|---|
| Detached | 12,305 | ~8,080 (66%) |
| Attached | 12,968 | **0** (engine can't build for units) |
| **All indexed /offmarket** | **25,273** | **8,084 = 32%** |

The **data** to serve units already exists — it's a *build* gap, not a data gap.

## What units already have (reusable)
- **`Gold_Coast.unit_valuations`** — a separate unit comparable-sales model with a
  `publishable` accuracy gate. **6,534 publishable**: Robina 3,582, Varsity 2,952,
  **Burleigh Waters 0** (fails the suburb accuracy gate). `publishable` IS the unit
  equivalent of the house $1M–$2M envelope.
- **`Gold_Coast.unit_market_series`** (per suburb) — `rolling_12m_by_bedrooms` (per-bedroom
  median index), `median_days_on_market`, `yoy_pct`. Supplies 2 of the teaser's 3 figures.
- **`unit_page_data.assemble()`** — already builds the unit `/off-market` landing page
  (valuation range + same-building and within-5km comps + complex info).
- Scheme centroids for all 1,964 schemes (`ingest_scheme_centroids`) — a real lat/lon per
  complex, usable for a unit hero map.

## The teaser is a small surface
Only **3 subject-specific figures** (`build_owner_mailer.teaser_facts`): the home's own
6-month value move, the suburb median 6-month move, and days-on-market. Everything else is
national/suburb narrative that is dwelling-agnostic. Plus the hero image and the eligibility
guard.

## Work, by workstream
**A. Three figures (small).** Suburb unit median move + unit DOM come straight from
`unit_market_series`. The **per-unit 6-month move** has no unit trajectory — either build a
tiny one (`unit_valuation.value()` already has a `cutoff` hook) *after a noise backtest*, or
**lead with the bedroom-segment figure** and don't claim a per-unit move (units are noisier
than houses; the house 6-month move is already flagged as noise). Recommended: segment figure.

**B. `teaser_facts_unit()` + guard (small–medium).** Dwelling-class branch; gate on
`unit_valuations.publishable`; a unit-appropriate "holding band" (measure it first).

**C. Unit hero image (medium, design).** The cadastral-boundary aerial is wrong for a tower;
units have no hero today. Options: Static-Map of the complex (scheme centroid), building
photo, or location map. The one genuine design decision.

**D. Unit copy variant (small–medium).** "this home" → "this apartment"; figure labels to
segment framing; back-page "questions the full analysis answers" must match what the unit
landing page actually shows.

**E. The landing-page promise — the real fork.**
- **Option 1 (teaser-only, fast):** teaser drives to the *existing* unit page; reframe the
  back copy + banner so the promise matches (range + comps + market series). No unit article.
  Unlocks all ~6,534 homes in ~1–2 sessions.
- **Option 2 (full parity — CHOSEN, deferred):** build a unit market-update *article* — a
  unit branch through the whole figures/charts/copy pipeline (unit trajectory, unit median
  chart, unit DOM chart, unit comps). Honors the identical "read the complete analysis"
  promise. Multi-session.

## Hard constraints
- **Burleigh Waters units → 0 publishable.** No unit teasers there until accuracy clears.
- `unit_valuation.ACCURACY` renders verbatim on ~5,000 live pages — re-measure if the comp
  set changes; never hand-edit.
- Never print a per-unit move without a backtest.
- The teaser/banner must not promise what the landing delivers can't — the QR-promise-unmet
  trap has bitten before.

## Related
`UNITS_DEVELOPMENT_PLAN.md` · `scripts/unit_valuation.py` · `scripts/unit_market_series` ·
`17_Direct_Letterbox/Owner_Subject_Article/build_owner_mailer.py` (teaser) ·
`build_owner_article.py` (full article).
