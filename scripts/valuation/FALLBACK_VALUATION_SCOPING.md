# Fallback valuation for listings with no floor area — scoping

**Raised:** 2026-08-05 (Will) · **Status:** OPEN, not started · **Origin:** WTA-OPS-005

## The problem

Roughly **223 of 540 for-sale listings (41%) cannot be valued at all**, and the single
dominant cause is `missing_floor_area`. The gap is widening — 209 → 223 in 12 days
while successful valuations stayed flat at ~232.

**Will's position (2026-08-05):** most of these properties simply *don't have* floor
area published. It is not a scraping bug to be fixed; the data does not exist at
source. So waiting for floor area to arrive is not a strategy.

Valuation is the product. Today, for 4 listings in 10, we show nothing.

## The idea

Build a **fallback valuation path** that does not require floor area — select
comparables on the attributes we *do* reliably have:

- **lot size** (cadastral, near-universal coverage)
- **bedrooms / bathrooms / car spaces**
- **property type** (house / unit / townhouse / duplex)
- **location** (suburb, proximity, street, and the existing location factors)
- whatever else the canonical attribute layer already carries — check
  `[[canonical_attribute_layer]]` before designing the feature set

The output must be honest about being a lower-confidence estimate than the
floor-area path, not silently blended with it.

## Why this is plausible

The existing engine (`07_Valuation_Comps/precompute_valuations.py`) already selects
3-8 comparable sales and adjusts each for floor area, condition and location, then
takes a weighted mean. Floor area is one adjustment dimension among several — it is a
**hard gate** today largely by construction, not because the method collapses without
it. On a lot-size-and-configuration basis, a defensible comparable set should still be
reachable, especially in the master-planned estates (Robina, Varsity Lakes) where
housing stock is relatively homogeneous.

## Measured coverage (2026-08-05, 360 for-sale listings across the 6 scraped suburbs)

Fields live at the TOP LEVEL of the property doc — `total_floor_area`, `lot_size_sqm` /
`lot_size_calc_sqm`, `bedrooms`, `bathrooms`. (Not `floor_area`/`land_size`; querying
those returns ~0% and will mislead you.)

| Attribute | Coverage |
|---|---|
| `total_floor_area` | **193/360 = 53%** ← the current hard gate |
| `lot_size` (either field) | 178/360 = 49% |
| `bedrooms` | 351/360 = 97% |
| `bathrooms` | 351/360 = 97% |
| **lot + beds + baths together** | **172/360 = 47%** ← the proposed fallback feature set |

Missing floor area by type: House 89, New House & Land 29, Townhouse 17,
Apartment/Unit 14, Vacant land 8, Duplex 5.

**This is the uncomfortable finding, and it should be settled before any build:**
lot-size coverage (49%) is barely better than floor-area coverage (53%), and the two
overlap heavily — a lot+beds+baths fallback would only reach **47%** of the book, i.e.
it would rescue very few of the listings that are currently blocked. A fallback built on
lot size may therefore recover almost nothing.

### The intersection — measured, and it sizes the whole project

Of the **167** for-sale listings with no floor area:

| | |
|---|---|
| have lot size | 79 / 167 = **47%** |
| have bedrooms + bathrooms | 158 / 167 = **94%** |
| have lot + beds + baths | **73 / 167 = 43%** |

So a lot-size-based fallback rescues **73 listings** — it lifts valuation coverage from
53% to roughly **73%** of the book, not to 100%. Worth doing, but it is not the whole
answer, and the remaining ~94 listings need attribute sourcing rather than a smarter model.

The striking number is **beds+baths at 94%**. A configuration-and-location fallback
(bedrooms, bathrooms, property type, suburb/proximity — no lot size, no floor area) would
reach **158 of 167**, i.e. nearly the entire gap. It is a blunter instrument and would
need a lower confidence ceiling, but on coverage grounds it dominates the lot-size
approach. **Design for both tiers rather than assuming lot size is the answer.**

Where lot size is missing, check the cadastral join first — `lot_size_sqm_source` exists
as a field and `Gold_Coast` already holds ~40K cadastral records, so some of those 88
missing lot sizes are probably recoverable rather than absent.

## Open questions to answer before building

1. **How much accuracy do we actually lose?** Backtest the fallback against sold
   properties that DO have floor area — value them both ways and compare each against
   the real sale price. That gives an honest confidence band rather than a guess.
   `scripts/valuation_backtest.py` already exists for this.
3. **Can lot size be sourced rather than modelled around?** `lot_size_sqm_source` exists
   as a field, and cadastral data is already in `Gold_Coast`. A join may beat a fallback.
4. **Presentation.** Per CLAUDE.md Rule 5 and `[[valuation_method_comparables]]`, output
   must be a comparable **range**, never a single figure in a headline, and must state
   its own limitation. A lower-confidence estimate shown with the same visual weight as
   a high-confidence one would be worse than showing nothing.
5. **Confidence model.** The existing `confidence` field (90% CI via
   `1.645 * weighted_std_dev`, High/Medium/Low/Very Low) needs a defined behaviour for
   this path — most likely a hard ceiling, e.g. never above "Medium".

## Constraints

- **Never claim more accuracy than backtesting supports** — see
  `[[valuation_backtest_claim_constraints]]`. Never "more accurate than Domain".
- Do not let the fallback silently replace a real valuation where floor area exists.
  It is a fallback, and its provenance must be recorded on the document.
- Waterfront remains out of scope (`[[waterfront_out_of_scope]]`).

## Where the pieces live

- Engine: `/home/fields/Feilds_Website/07_Valuation_Comps/precompute_valuations.py`
- Backtest: `scripts/valuation_backtest.py`
- Pipeline step: 18 (valuation precompute) — the exclusion is logged as
  `⚠️ Excluded (missing_floor_area) — cleared existing valuation`
- Health row: "Step 18 outcome / Valuation precompute: listings excluded from valuation"
