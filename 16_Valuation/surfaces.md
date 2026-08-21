# The surfaces — where a valuation is shown, and whether they agree

Five things present a valuation to a reader. This file answers the question that matters:
**could the same property show a different number on different pages?** Mapped 2026-08-20
(agent survey, file:line verified).

> **Verdict for detached houses: no contradiction.** All four house surfaces read the *same*
> stored `valuation_data.confidence.{reconciled_valuation, range, range_basis}` and do **not**
> re-derive it. Cross-surface differences are **display rounding only** — the same value at
> different precisions. The genuine divergences below are all bounded and none is the same
> house valued twice.

---

## Same house, four surfaces, one number (rounded differently)

| surface | reads | point figure shown as | range shown as |
|---|---|---|---|
| **Report page** (this folder) | `valuation_data` directly | exact `$1,652,000` | exact dollars |
| **/property/:id** | `valuation.mjs` returns `valuation_data` verbatim (<7d) | exact, rounded to $ | `$1.65m` (2-dp millions) |
| **/off-market** (house) | `off-market.$slug.tsx` → `valuation_data.confidence` | "approximately $1.65 million" (rounded to **$50k**) | `$1.65 million` (2-dp) |
| **/your-home** appraisal | see divergence 3 below | mirrors the listed page | mirrors |

The range leads on every public surface; the bare point figure only appears where the range
also appears — consistent with the "no single valuation figure in headlines" rule.

## Genuine divergences — all bounded, none a same-house contradiction

1. **Units use a different engine and collection.** On `/off-market`, attached dwellings are
   valued by the **unit engine** (`unit_valuations` collection), because the house engine
   declines for them (`db.server.ts:871-899`). Different property type, different method — not
   the same property valued twice. See `engines/README.md`.

2. **`/property` has a fallback that recomputes.** When a property has **no stored
   `valuation_data`, or it is >7 days stale**, `valuation.mjs:632-720` **live-computes its own**
   median/regression estimate by a different method, for the scatter plot. A real second code
   path that can differ from the engine — but only for un-precomputed properties, never
   overriding a stored figure.

3. **⚠ `/your-home` is a STATIC FIXTURE, not live data.** The route renders a hardcoded
   fixture (`data/homeFixture.ts`, `TERRACE_COURT_13`); its valuation block is **hand-transcribed
   to mirror a real property's `valuation_data`** (`homeFixture.ts:97`). The risk is
   **staleness/transcription drift**, not runtime re-derivation — it cannot compute a different
   number, but it can silently fall out of date relative to the live engine. The *live*
   appraisal path (`run_subject_valuation.py`, process 301) does use the same engine and writes
   `valuation_data`, and the appraisal PDF (`generate_appraisal_v4.py:407`) reads it — so the
   real appraisal is consistent; only the demo mini-site page is a fixture.

## ⚠ The one editorial leak — the uncalibrated tier surfaces on /your-home

The confidence tier (high/med/low) is **not calibrated** (memory + `experiments/`), so it is
deliberately suppressed everywhere — **except `/your-home`**, where `evidenceTag()`
(`YourHomePage/components/ValuationEvidence.tsx:106-112`) maps `confidence.level` to
reader-facing **"Strong Evidence" / "Good Evidence" / "Limited Data"** badges (rendered
:557, :922). It is relabeled, but a reader still sees a quality grade derived from the
uncalibrated tier. The report page, property page, and off-market views do **not** do this.

**Not dispatched as a fix** — whether "Strong/Good/Limited Evidence" is acceptable framing is
Will's editorial call, not a mechanical change, and it belongs with the tier-calibration item
already in `METHODOLOGY_REVIEW_TASK.md` (item 3). Flagged there.

## The statutory-CMA layer (separate from the valuation, both product lines)

Both `/your-home` (`homeFixture.ts:2006` `statutoryCma`) and `/off-market` for units
(`unit_statutory_comps`, `db.server.ts:912`) carry a **separate 3-comp / 6-month / 5km
asking-price comparable set** built to the QLD POA CMA definition, shown *alongside* the
valuation and **never feeding** the engine range. On the unit side this is engine 3 in
`engines/README.md`; on houses it is a display layer over the same comps.

## Not fully verified

- `PropertyPage.tsx` is ~1,400 lines and carries `valuation_confidence` in its payload
  (`:625`); no High/Med/Low badge was found in the sections read, but its non-appearance
  everywhere on that page is not 100% confirmed.
- Whether `SlotResolver`'s old range path still serves any live house surface.

## Related

- `engines/README.md` — the engines behind these surfaces
- `report_page/README.md` — the new formal report (surface 4)
- `METHODOLOGY_REVIEW_TASK.md` — where the tier leak and band drift are tracked
