# 1/1 PONTOON PLACE VARSITY LAKES QLD 4227

*Private property report · rendered Monday 10 August 2026*

> **Harness note.** This is the markdown proof of the unit page, rendered from the live engine (`fact_bundle` → `emit_v4`). It is not published anywhere. GAP markers name the workstream in `UNITS_DEVELOPMENT_PLAN.md` that closes them.

| | |
|---|---|
| Slug | `1-1-pontoon-place-varsity-lakes` |
| Suburb | Varsity Lakes |
| Dwelling class | **attached** (computed live — dwelling_class is not persisted; classification is computed live here) |
| Cadastral subtype | GTP (group title — villa/townhouse) |
| Complex name | — |
| Cards emitted | 7 of 11 |

---

## 0 · The header

**1/1 PONTOON PLACE VARSITY LAKES QLD 4227**

3 bedrooms · 2 bathrooms

> **GAP [C2]** — no floor area on this dwelling (Domain internalArea not yet read).

You may be trying to answer three questions privately.

- Is the number attached to this home real?
- Is this the wrong time to move?
- And if you sold, where would you go next?

This page starts with the first: what the sales around this home actually support. There is nothing to fill in and no account to create — the whole page is here.

> **GAP [G4]** — hero is a cadastral lot; for a unit the parcel is the whole scheme.
>
> The house page shows a title boundary and land size here. For a unit the cadastral parcel is the whole scheme — it would show ~40 neighbours' roofs. Replacement is complex name + scheme size + storeys band.

> **GAP [E1]** — no complex entity - CTS number, scheme name and scheme size not yet ingested.

> **GAP [E2]** — no storeys band - QLD LiDAR buildings layer not yet ingested.

---

## 1 · The last six months — what's changed recently

> **GAP [D1]** — no unit price series exists for this suburb; the house median would be wrong here.
>
> The house page shows suburb median, days-on-market and comparable sales here. Every one of those series is houses-only by construction (`precompute_union_prices.py` filters `classify_dwelling == house`).

> **GAP [D3]** — no unit days-on-market or unit active-listing count.

---

## 2 · Part 01 — The valuation

### The range

What the sales around it say.

$1.19 million – $1.45 million

The evidence centres around

$1.3 million

rounded deliberately, because the width is the honest part

We have limited verified data on this specific home, so this is an indicative suburb-level band rather than a property-specific range.

### Reliability

What this is, and what it isn't.

This is an estimate built from comparable sales. It is not a formal valuation and it isn't an appraisal — a valuer inspects the property and carries professional liability for the figure. Nobody has been inside this home.

We take sales of homes near this one, adjust each for the ways it differs, weight them by how good a comparison they are, and publish the spread.

The range above wasn't built by the method described here — this home sits outside the band our comparable-sales model was built for, so we've used a wider approach based on what can be verified from the outside. We publish a measured error rate for the comparable-sales method; we don't have one for this fallback, so we're not quoting a number we haven't earned.

### Why three sites disagree

Why the other estimates say something different.

A valuation built from only three selected sales is highly sensitive to which three are chosen — and three comparable sales is the statutory Statement of Information standard in Victoria and the incoming NSW regime, so it is not a straw man.

We took 512 homes that have since sold, found every set of three comparable sales that could reasonably have been chosen, and worked out what each set said.

The median gap between the highest and lowest defensible result was $469,000.

That does not make any one estimate dishonest. It means three sales are often too small a sample to show which comparison deserves the most weight.

**See what the test found** — A close answer was present in the available evidence on 73.6% of those homes — identifiable only with hindsight. The worst available choice was more than 20% out on 73.4%.


> **GAP [F5]** — the engine emitted a RANGE for this unit, derived from HOUSE sales — `_thin_valuation_range` filters on bedrooms with no property_type clause.
>
> Engine emitted **$1.19 million – $1.45 million** for this dwelling via `method=thin`, n_comps=20. ⚠ **This is not a refusal — it is a number.** The V4 React page suppresses it (it requires `valuation_data.confidence.range.low`), but the DISCOVERY DECK renders this card, and the deck is the default in every non-V4 suburb. Verify before shipping the unit arm.

---

## 3 · Part 02 — The home itself

### What stood out

What makes this home less common among today's listings.

Where a buyer may focus:

- no pool

### The comparison set

What's moving around this home.

Two true things that point in different directions.

Homes here are selling more slowly than a year ago — a median of 26 days, against 21 twelve months earlier. But there is less to choose from: 23 homes are on the market, 43.8% more than a month ago.

Both readings are true and they support opposite conclusions, which is why a single market headline can't settle anything about this home.

> **GAP [D4]** — the market card quotes house days-on-market and house listing counts.
>
> The market copy rendered above draws on `precomputed_market_charts` (days-on-market) and `precomputed_active_listings` — both keyed by suburb only, both houses-only by construction. Presented here as this dwelling's market.

> **GAP [G3]** — green_space makes a boundary claim from a single geocode; invalid for a scheme.
>
> Engine returned: `{"premium": {"name": "Silvabank Lake", "kind": "water", "edge_m": 99.5, "relation": "steps from"}}`. Suppress for attached dwellings.

---

## 4 · Part 03 — Where that leaves you

### What you know that we don't

This is your home's page. You can change it.

Everything here was built from public records and sales data. Some of it will be wrong — a renovation we don't know about, a room count out of date, a sale that shouldn't have been used.

See everything we hold on this home

Tell us what's wrong, and we'll fix it and rebuild the figure in front of you.

No agent is paying to appear on this page, and your interest in your own home is not sold to anyone. Fields is the agency that built it — there is no third party being handed your address.

> **GAP [D1]** — no unit price series exists for this suburb; the house median would be wrong here.
>
> The house page closes with suburb median, median trend chart, days-on-market and "N houses for sale". All house series.


---

## Appendix — engine diagnostics

Which of the 11 emitters produced a card for this dwelling:

| # | card type | emitted |
|---|---|---|
| 00 | `recognition` | yes |
| 01 | `valuation` | yes |
| 02 | `evidence` | — |
| 03 | `comparable` | — |
| 04 | `reveal` | yes |
| 05 | `method` | yes |
| 06 | `dispersion` | yes |
| 07 | `gain` | — |
| 08 | `competition` | yes |
| 09 | `buyer` | — |
| 10 | `control` | yes |

Engine-reported gaps: `no comparable sale`, `positioning/value-drivers unavailable`

**GAP markers in this report: 9** — C2, D1, D3, D4, E1, E2, F5, G3, G4
