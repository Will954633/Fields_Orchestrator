# report_page — the formal valuation report

A single-property report styled like a professional property valuer's document: a stated
value range and point figure, the full schedule of comparable sales, the line-by-line
adjustment grid, the weighting and reconciliation, the measured accuracy, and the
disclaimers a valuer would carry. It is the valuation **presented as evidence you can
check**, not as a number to trust.

> **⚠ STATUS: MOCKUP — not live, and not to be shown to real buyers or sellers yet.**
> One claim on the page ("four in five sales land inside this band") currently overstates —
> see [Concerns](#concerns) — and the whole method is under review
> (`../METHODOLOGY_REVIEW_TASK.md`). This folder is a working prototype for Will, published
> only as a private Claude artifact.

---

## Who it is for

People who **don't trust online instant estimates, want something more rigorous, and
specifically do not want to talk to an agent to get it.** The two things normally on offer —
a portal's one-click number with no working shown, and an agent appraisal that opens a sales
conversation — both ask for trust. This document's whole proposition is the opposite: show
every comparable, every dollar of adjustment, every weight, and every attribute we could not
observe, so the reader can disagree in specific terms.

This maps directly onto the buyer-first, seller-funded model: it is a buyer/owner-facing
artifact whose credibility is the product.

---

## What is in this folder

| file | what it is |
|---|---|
| `build_report_page.py` | Generator. Pulls one property's `valuation_data` from Cosmos and renders the HTML. **Every figure on the page comes from the database — nothing is hand-typed.** |
| `report.html` | The current rendered output (27 Huntingdale Crescent, Robina). Overwritten on each run. |
| `README.md` | This file. |

## How to (re)generate

```bash
cd /home/fields/Fields_Orchestrator
python3 16_Valuation/report_page/build_report_page.py \
    --address "27 HUNTINGDALE CRESCENT ROBINA QLD 4226" \
    --collection robina \
    --out 16_Valuation/report_page/report.html
```

`--address` must be the exact `complete_address` (uppercase, as stored). `--collection` is the
lowercase suburb collection. The script **refuses to render** a property whose valuation is
`directional_only` (outside the $1M–$2M design envelope) or has no `reconciled_valuation` —
it will not draw a range it is not entitled to draw.

To publish/update the private artifact, re-publish `report.html` (keeps the same URL):
current URL `https://claude.ai/code/artifact/0549e309-c923-4545-b8d7-d248eea8081c`.

## Where every number comes from (provenance)

The generator reads only `property_document.valuation_data`, written by
`/home/fields/Feilds_Website/07_Valuation_Comps/precompute_valuations.py` (off-market book via
`scripts/batch_value_offmarket.py`). Specifically:

| on the page | source field |
|---|---|
| Value range, point figure | `valuation_data.confidence.{range, reconciled_valuation}` |
| Band width + "four in five" note | `valuation_data.confidence.range_basis` |
| Suburb calibration factor | `valuation_data.confidence.suburb_calibration` |
| Subject attributes | `valuation_data.subject_property.features.basic` |
| Schedule + adjustment grid | `valuation_data.recent_sales[]` where `included_in_valuation` |
| Each adjustment line | `recent_sales[].adjustment_result.adjustments.*` |
| Weighting factors | `recent_sales[].weight.factors` |
| Rate schedule | `valuation_data.adjustment_rates.rates` |
| Street / micro-location evidence | `subject_property.{street_evidence, micro_location_evidence}` |
| Accuracy stats | hard-coded from `../accuracy/2026-08-08-figures.md` (the only measured source) |

⚠ **The schedule reads comparable attributes from the adjustment lines
(`adjustment_result.adjustments.<x>.comp_value`), NOT from `recent_sales[].features.basic`.**
The two disagreed — `features.basic` carried a scraped room dimension (30 m²) where the
adjustment correctly used 233 m². Sourcing from the adjustment lines is what keeps the
schedule and the grid from contradicting each other on the same page. See
`attrs_from_adjustments()` in the generator and `[VAL-FLOOR-SANITY]` in
`logs/fix-history/2026-08-20.md`.

## Design decisions

- **Valuer format, not a marketing page.** Numbered sections (purpose & limits → subject →
  method → rates → comparables → grid → weighting → locational evidence → accuracy →
  is/isn't → assumptions), a signature block, a print stylesheet. It should read as a
  document, because the audience is people who want a document.
- **One structural idea: a single accent (burnt sienna) is used *only* for limitations.**
  Every disclosure — "not a certified valuation", "not observed", "the street premium rests
  on three sales" — carries that colour and nothing else does. You can scan the page for the
  colour and find everything we don't know. The honesty is visually indexed.
- **The range carries the assessment, not the point figure.** The point figure is shown but
  framed as the arithmetic centre of the range, never as "the price" — consistent with the
  "no single valuation figure in headlines" editorial rule.
- **The eight shown are evidence, not the derivation.** The reconciled figure is computed
  over the full candidate pool (49 for this subject); the eight displayed carry ~20% of the
  weight. The page says so outright rather than letting the reader assume the eight produce
  the number.

---

## Concerns

These are the reasons this page is not live. They are tracked in
`../METHODOLOGY_REVIEW_TASK.md` (with a weekly Telegram reminder) and logged in
`logs/fix-history/2026-08-20.md`.

1. **The "four in five" band claim currently overstates.** The page repeats the stored
   `range_basis.note` — "four in five sales land inside this band" — but re-measured on
   2026-08-20 the ±12.2% / 11.2% / 14.0% bands contained only **~72% / ~75% / ~76%** of
   sales (Robina / Varsity Lakes / Burleigh Waters). Confirmed as data drift, not a bug (the
   floor-area fix was accuracy-neutral in an A/B). **This is the single blocker to shipping
   the page to real users** — it is exactly the ACCC-substantiation / brand-honesty exposure
   the domain guardrails exist to avoid. Will's call (2026-08-20) is to hold the bands and
   review the whole method rather than reflexively widen; until then the claim is on hold.

2. **A recalibration is measured but held (2026-08-13),** and the tool that produced it
   (`../experiments/calibration_refit.py`) fits on empty caches — so its Burleigh factor was
   wrong. Any number this page shows post-calibration must wait on that being resolved.

3. **The confidence tier is not calibrated** and is deliberately not rendered on the page.
   Correct for now, but it means we are holding back a signal we cannot yet stand behind.

4. **Accuracy figures are hard-coded** into the generator from the 2026-08-08 measurement.
   When the method is re-measured (item 1), these must be updated in `build_report_page.py`
   in the same change — they are the one thing on the page not pulled live from the DB.

5. **Staleness.** The report shows how many days old the assessment is and caps reliance at
   three months, but there is no recompute-on-request path — it serves whatever
   `batch_value_offmarket.py` last wrote. A real product needs on-demand revaluation.

---

## Related

- `../METHODOLOGY_REVIEW_TASK.md` — the open review this page's concerns feed into
- `../methodology/` — how the underlying valuation works
- `../accuracy/2026-08-08-figures.md` — the measured accuracy the page quotes
- `../decisions/2026-08-20-valuation-report-page.md` — the decision record for this product
- `logs/fix-history/2026-08-20.md` — `[VAL-FLOOR-SANITY]`, `[VAL-BAND-COVERAGE-DRIFT]`
- `15_Off-Market/Page_Redesign_V4/Product/` — how valuation is presented in the off-market product
