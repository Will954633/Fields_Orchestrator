# 03 — Port plan: what we build vs what we already own

**Decided 2026-08-07.** The V4 page is **substantially an assembly of existing production
components plus new copy — not a new build.** That was established the hard way: three sections
were rebuilt in the prototype before anyone checked whether they already existed. All three did.

---

## The rule

> **Before building any section, grep for the component. A failed API probe is not evidence that a
> component does not exist.**

Cost of ignoring it, this session alone:

| section | what I built | what already existed | what was lost |
|---|---|---|---|
| Seasonality | ad-hoc SVG bar chart | `YourHomePage/components/SeasonalityStrip.tsx` | tile treatment, tap-to-detail, the academic citations |
| Median price | 8-quarter bar chart | `components/MetricCharts/MedianPriceChart.tsx` | 84 quarters back to 1993, the rolling series, per-quarter CIs |
| Comparables | 3 cards + a `<details>` table | `YourHomePage/components/ValuationEvidence.tsx` (1,068 lines) | photo strips + lightbox, weight %, verified flags, weight factors, evidence map |

---

## PORT — already built, drop in unchanged

### `ValuationEvidence.tsx` — the whole valuation spine

**Verified 2026-08-07 that this is free.** `slot_resolver.valuation_evidence_from_engine()` reads
**straight off `valuation_data`** — "no recomputation", per its own docstring — and that is the same
field on every off-market document. Run against off-market subjects it returned, unchanged:

| | 28 Wedgebill | 5 Chantilly |
|---|---|---|
| comparables | 8 | 8 |
| photos each | 15 | 15 |
| per-feature adjustments | 10 | 10 |
| weight %, distance, verified | ✓ | ✓ |
| narrative | ✓ | ✓ |

Same data, same resolver, same component. It also brings **`EvidenceMap`** ("where these sales
sit"), which the prototype has no equivalent of at all.

⚠ **Two things must NOT come across with it:**
- *"The final figure is being reviewed by a property consultant"* — a **contact promise**, the exact
  class of copy stripped from this page (see `[TIMELINE-CONTACT-PROMISE]`). On the appraisal product
  it is true; here it contradicts the page's central claim.
- **The statutory CMA block** (*"The comparable sales required by law"*) — needs a deliberate
  decision. It belongs on an appraisal someone requested; whether it belongs on a page nobody asked
  for is a different question.

### Also port
- `SeasonalityStrip.tsx` — treatment already reproduced in the prototype; use the real component.
- `MedianPriceChart.tsx` — fed by `/api/market-insights`. **`OffMarketPage/MarketCharts.tsx` already
  imports it.**
- `CitationStrip` — the "if a claim has no source, the block should not have rendered" rule, built.

---

## BUILD — genuinely new, nothing to reuse

1. **The two-portals preamble** — "Two property sites. Two different values… which one is right?"
2. **The excluded sale** — the priciest nearby sale NOT used, with the recorded reason from
   `verification.issues`. No equivalent anywhere.
3. **The dispersion finding** — the $469,000 three-comp spread.
4. **The private working plan** — five owner-only questions; prototyped in
   `Prototypes/build_working_plan.py`.
5. **The market-timing section** — new copy, but the two visuals inside it are ported.
6. **The copy and the ordering throughout** — the largest piece of remaining work, and the one the
   prototype is genuinely good for.

---

## What the prototype is for now

**Keep using it for:** copy, sequence, and the six sections above. It is the fastest loop available
— no build step, real data, instant regeneration.

**Stop using it for:** re-implementing shipped components. Sections marked `PORTED` in
`render_prototype_a.py` are placeholders that exist so the page reads end to end. Do not polish
them, do not add thumbnails to them, do not fix their styling. They are being replaced.

See [[01_UI_BRIEF]], [[02_VISUAL_SYSTEM_PARKED]].
