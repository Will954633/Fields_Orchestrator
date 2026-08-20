# Decision — a formal valuation report page

**Date:** 2026-08-20 · **Decided by:** Will (brief), Claude (build) · **Status:** prototype built, held from public release

---

## The question

Is there a place for a valuation surface aimed at the person who **distrusts online estimates,
wants something more rigorous than a portal's one-click number, but will not talk to an agent
to get it**? The two existing options both ask for trust: the instant estimate shows no
working, and the agent appraisal opens a sales conversation.

## The decision

Build a report styled like a professional property valuer's document, where the proposition
is that **all the working is shown** — comparables, per-line adjustments, weights, measured
accuracy, and an explicit list of what we could not observe. Prototype lives in
`../report_page/` and renders entirely from `valuation_data` (no hand-typed figures).

Subject for the prototype: **27 Huntingdale Crescent, Robina** — a 4-bed detached house
inside the $1M–$2M design envelope, off-market, with a full comparable set. (25 Huntingdale
was rejected as the subject because it *sold* on 2026-03-03 for $1,731,000, so it is a
comparable, not a subject — and appears in the report as one.)

## What follows from it

1. **Format is a document, not a landing page** — numbered sections, signature block, print
   stylesheet, valuer-style assumptions & limiting conditions.
2. **One structural honesty device:** a single accent colour is reserved exclusively for
   limitations, so the page can be scanned for what we don't know.
3. **The range carries the assessment**; the point figure is the arithmetic centre of it,
   never "the price" — consistent with `decisions/2026-08-07-range-meaning.md` and the
   no-single-figure-in-headlines editorial rule.
4. **The eight displayed comparables are labelled as evidence, not the derivation** — the
   figure reconciles over the full candidate pool (~49), and the page says so.

## Held from public release — the open blocker

**This page must not go to real buyers or sellers yet.** It repeats the stored
`range_basis.note` "four in five sales land inside this band", and that band was re-measured
on 2026-08-20 at ~72% / ~75% / ~76% coverage, not 80% (see
`../experiments/2026-08-20-band-coverage-drift.md`). Publishing a track record the current
method no longer earns is precisely the exposure the domain guardrails exist to prevent
(ACCC substantiation; falsifiable from our own tables). Will's call: **hold the bands and
review the whole method** (`../METHODOLOGY_REVIEW_TASK.md`) rather than reflexively widen.

Release is gated on that review resolving the band claim — either widen to the measured 80%
widths and update every surface that quotes them, or change the framing away from "four in
five". Until then the report stays a private prototype.

## Provenance / build

- Generator: `../report_page/build_report_page.py`; output `../report_page/report.html`.
- Full product notes and data-field mapping: `../report_page/README.md`.
- Incident records that shaped it: `logs/fix-history/2026-08-20.md` `[VAL-FLOOR-SANITY]`
  (the schedule now reads attributes from the adjustment lines, not `features.basic`).
