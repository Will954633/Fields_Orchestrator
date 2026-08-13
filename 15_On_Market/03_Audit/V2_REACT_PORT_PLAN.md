# V2 React port — data plan

**Written:** 2026-08-13 · Based on a field-by-field gap analysis of
`prototype/build.py` + `data.json` against the live API and `Gold_Coast.*`.

## Verdict

**The port is feasible. Nothing the prototype renders is missing from the database.**
Almost every "gap" is plumbing: the data exists at high fill and simply is not exposed by the
endpoint the page calls. Two elements genuinely do not exist anywhere and must be computed or cut.

## ⚠ Correction that changes the scope

The gap analysis was run against `netlify/functions/property.mjs`. **That is not the API the property
page uses.** `PropertyPage.tsx:583-586` fetches `/api/v1/properties/for-sale/:id` →
`properties-for-sale.mjs` (and `/api/v1/recently-sold/:id` for sold). I hit the live endpoint and
enumerated its 47 response keys directly:

| Needed by V2 | in `property.mjs` | in `properties-for-sale.mjs` (**what the page actually calls**) |
|---|---|---|
| `price_history` (the 12 price events, Layer 1) | ✅ returned | ❌ **absent** |
| `valuation_data.adjusted_comparables` (Layer 2) | ❌ absent | ❌ absent |
| `valuation_data.confidence.*` | partial (range only) | ❌ absent |
| `satellite_analysis.categories.*` (Layer 4) | ❌ absent | ❌ absent |
| `zoning_data.*` (Layer 6) | ❌ absent | ❌ absent |
| `parsed_rooms`, `floor_plans`, `inspection_times` | ✅ | ✅ |

So the campaign timeline — the flagship "portal says 33 days, true figure is 137" story — is blocked
on this endpoint too, which the original analysis did not catch. **Do not scope from `property.mjs`.**

## The plumbing job (all fill rates: `Gold_Coast.robina`, 108 live listings)

| # | Add to `properties-for-sale.mjs` | DB path | Fill | Carries |
|---|---|---|---|---|
| 1 | `price_history` | `price_history[]` (`recorded_at`, `price_text`, `price_numeric`, `event`) | **100%** | Layer 1 entire + true cumulative DOM |
| 2 | `adjusted_comparables` | `valuation_data.adjusted_comparables[]` | 49% | Layer 2 entire — the flagship section |
| 3 | confidence metadata | `valuation_data.confidence.{confidence, n_verified, n_total, range_basis}` + `valuation_data.computed_at` | 100% (range_basis 42%) | Every provenance line under the range |
| 4 | `satellite_analysis.categories` | `satellite_analysis.categories.{adjacency, detractants, amenity_premiums, lot_characteristics, neighbourhood}` | **99%** | Layer 4 — "what is wrong with it" |
| 5 | `zoning_data` | `zoning_data.{lot_plan, zone, cadastral_area_sqm, flood_overlay, …}` | 40% | Layer 6 + the **land-size fallback** |
| 6 | `image_derivative_widths` / `property_images_srcset` | done 2026-08-13 | 98% | Photo weight (already shipped) |

**Traps found, worth knowing before writing code:**

- ⚠ `satellite_analysis.**categories**.adjacency.frontage` — the prototype's `satellite.adjacency.*`
  drops the `categories` level. Keep it or every lookup returns undefined.
- ⚠ `adjustments` is stored as an **object keyed by factor** (`condition`, `floor_area`, `land_size`,
  …) with `subject_value`/`comp_value`; the prototype consumes an **ordered array** with
  `subject`/`comp`, sorted by |dollars|. Reproduce `build.py`'s flatten+sort. Some factors carry
  `.skipped` and `dollars_unshrunk`, which `build.py` ignores.
- ⚠ `property_valuation_data` (already in the response) is a **decoy** — it is the photo-condition
  sub-document, not the valuation. Different thing entirely.
- ⚠ The prototype's **land size comes from `zoning_data.cadastral_area_sqm`**, not `lot_size`. A naive
  port silently loses the Land chip and the floor-to-land trade-off wherever `land_size` is empty.
- ⚠ `parsed_rooms` (79%) and `floor_plan_analysis.rooms[]` (77%) are **two competing room sources**.
  Pick one and say which on the page.
- Waterfront listings have their range deliberately nulled — Layer 2 must degrade, not break.

## Derivable client-side — not gaps despite looking like them

- **True cumulative DOM (137)**: `today − price_history[0].recorded_at`, exactly as `build.py:58`.
- **Price type** (offers_over / auction / …) driving the POA s216 explainer:
  `src/utils/listingMethod.ts:27` `classifyListingMethod()` already parses it from the price string.
  Port the mapping; do not add a field.

## Does not exist anywhere — compute or cut

1. **The three Layer 2b market stats (75% / 48% / 79%).** Hand-measured 2026-08-10. Raw material is
   in `system_monitor.price_change_events` (100% fill), so it is computable — but it needs a
   scheduled aggregation + endpoint, under Rule 7 with a heartbeat. Until then the section ships
   stale-with-a-date or not at all.
2. **Suburb median** — hardcoded at `build.py:648`. `Gold_Coast.suburb_median_prices` is complete
   (76/76) and **no endpoint serves it**; `property-insights.mjs:998` explicitly excludes it. One
   small function.
3. **Fields-vs-Domain disagreement (42%, ±13.8%, $386k)** — a one-off population measurement.
   Per-listing Domain estimates exist on only 2–6% of stock. Not portable per-property; keep as a
   cited population statistic or cut.
4. ⚠ **The published error rate at the claimed granularity.** `/api/v1/valuation-accuracy` exists and
   serves `by_price_band`/`by_suburb`/`by_confidence` — but the DB bands are `$1M-$1.5M` and
   `$1.5M-$2M`. The prototype's "$1M–$2M" headline is a **hand-blended figure held by no field**.
   Either re-band the backtest or restate the claim. Publishing a number whose provenance we cannot
   point at breaks the page's own rule.

## Sequence

1. Plumb 1–5 into `properties-for-sale.mjs` (projection + response). Verify each against the live
   endpoint before writing any component — this is one afternoon and it unblocks everything.
2. Suburb-median endpoint.
3. Port layer by layer behind the `property_page_v2` flag, starting with Layers 0/1 (100% fill, and
   Layer 1 is the strongest story on the page).
4. Section-impression instrumentation as each layer lands (`useImpression.ts`; the off-market V4
   `v4_section_read` is the working model) — without it the arms are not comparable.
5. Layers 2/4/6 as their plumbing lands. Degrade honestly where fill is low: zoning is 40%, so most
   listings show "not held" — that is the P2 rule working, not a bug.
6. Resolve the error-rate banding and the address-door guard before anything goes public.

## Stated uncertainty

Fill rates are **Robina only**, 108 sampled live listings; `varsity_lakes` and `burleigh_waters` were
not sampled. Nobody has confirmed the prototype's own subject document carries every path — the rates
are collection-level, not per-document.

## ⚠ Layer 1 coverage — measured 2026-08-13, 212 live listings across the three suburbs

The prototype's subject (38 Glen Eagles Drive) has **12 price events and a withdrawal**. That is not
typical, and the port must not assume it.

| price_history events | listings | share |
|---|---|---|
| 1 (a single dot — no story) | 81 | **38%** |
| 2 | 52 | 25% |
| 3 | 31 | 15% |
| 4 | 22 | 10% |
| 5 | 11 | 5% |
| 6+ | 15 | 7% |

**The flagship "portal says 33 days, the true figure is 137" story applies to 4 of 212 listings — 2%.**
Those are exactly the 4 carrying a `withdrawn` event. Where it does apply it is dramatic: the portal
understates by a **median of 92.5 days**.

| gap | portal | true | address |
|---|---|---|---|
| +121 | 14 | 135 | 4 Yerrecoin Place, Burleigh Waters |
| +104 | 36 | 140 | 38 Glen Eagles Drive, Robina *(the prototype subject)* |
| +81 | 65 | 146 | 50/20 Executive Drive, Burleigh Waters |
| +80 | 28 | 108 | 89 Camberwell Circuit, Robina |

**What this means for the build.** Layer 1 has something to say on **62%** of listings and is a single
dot on 38%. The differentiator is real and nobody else publishes it — but it is a *rare-case* strength,
not the page's spine. Design the empty and single-event states first, not last, and do not let the
page's credibility rest on a section that is blank for four listings in ten.

⚠ **`price_history[0].recorded_at` is when WE first saw the listing, not when it was first listed.**
For anything listed before our tracking began, "true cumulative DOM" is bounded by our own history and
understates. Do not publish it as an absolute unless the first event is `initial`.

⚠ **Methodology trap, hit while measuring this.** `recorded_at` is stored as an ISO **string**, not a
BSON datetime. A first pass using `isinstance(r, datetime)` silently matched nothing and reported
**0%** — i.e. "the flagship story never occurs", which would have killed Layer 1 on a type error.
Parse it, and sanity-check any zero against a known-positive case before believing it.
