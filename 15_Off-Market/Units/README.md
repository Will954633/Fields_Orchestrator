# Units on `/off-market`

Bringing attached dwellings (units, apartments, townhouses, villas, duplexes) into
`/off-market` coverage for Robina, Varsity Lakes and Burleigh Waters.

## 👀 Look at these first

**Working prototype pages, in a browser:**
<https://vm.fieldsestate.com.au/concepts/off-market/Unit_Page_Prototype/index.html>

Six real attached addresses, rendered from live data. Deliberately spread across failure
modes: a 20-storey tower, a named apartment block, two low-rise complexes, a townhouse
group, and a 309-home tower the method **refuses** to value.

**Start here for the plan:** [`UNITS_DEVELOPMENT_PLAN.md`](UNITS_DEVELOPMENT_PLAN.md).

| Path | What |
|---|---|
| `UNITS_DEVELOPMENT_PLAN.md` | Milestones, workstreams, gates, decisions. **The plan.** |
| `research/UNITS_COVERAGE_AUDIT.md` | What breaks and why — measured, with citations |
| `research/UNITS_DELIVERY_PLAN.md` | Data-sourcing research: PropRadar, QLD strata, BCCM s205, legal position |
| `scripts/` | All new code for this project |
| `artifacts/unit_reports/` | Rendered per-address markdown — the review surface |
| `artifacts/snapshots/` | Pre-delete backup of the 8,095 house-engine unit docs |

## The one-line summary

Units are **already** served V4 pages — `v4Eligible()` tests suburb only. They render house medians,
house days-on-market and house listing counts as *"homes like yours"*, and a buyer persona promising a
*"backyard"*. So this project is not "launch units"; it is "stop being wrong, then earn the figure".

## The acceptance rule

Every milestone is accepted by **reading a markdown report for a real unit address**, not by reading a
diff. Prose is signed off as a document before it is built in React.


## Scripts

| Script | Does |
|---|---|
| `unit_page_data.py` | **The** data assembly. Both renderers consume it; neither computes a fact. |
| `render_unit_page.py` | HTML prototype → `Concepts/Unit_Page_Prototype/` (served, no build) |
| `render_unit_report.py` | Markdown review copy → `artifacts/unit_reports/` |
| `check_renderer_consistency.py` | Fails loudly if the two surfaces disagree on a figure |
| `ingest_complexes.py` | QLD cadastre → `Gold_Coast.complexes` (1,964 schemes, 90.5% linked) |
| `ingest_storeys.py` | QLD LiDAR → storeys band + inferred lift (99.0% of eligible) |
| `build_unit_market_series.py` | `Gold_Coast.unit_market_series` incl. per-bedroom indices |
| `unit_valuation.py` | Same-complex same-bedroom comparables; refuses rather than guesses |
| `ingest_scheme_centroids.py` | Cadastre → a real lat/lon per scheme (1,964/1,964). ⚠ `returnCentroid=true` is silently ignored by this service — geometry is fetched and the centroid computed locally |
| `statutory_comparables.py` | The SECOND set: 5km / 6 months / same bedrooms, adjusted (POA Sch 2) |
| `precompute_statutory_comparables.py` | → `Gold_Coast.unit_statutory_comps` (daily 05:15) |
| `backtest_statutory_comparables.py` | Head-to-head vs same-complex, leakage-free, same sales |
| `check_comparable_consistency.py` | Fails if the two comparable tables disagree about a sale they BOTH show (daily 05:40) |

## The two comparable sets

A unit page shows **both** — sales in this building, and recent sales within 5km. They
overlap by design (a same-building sale is also within 5km) and they **disagree about the
number**, which is the point: see `research/STATUTORY_COMPARABLES.md`.

Measured leakage-free on the same 1,542 sales:

| | median error | MAE | within 10% |
|---|---|---|---|
| Sales in this building | **5.7%** | **9.3%** | **67.4%** |
| Recent sales within 5km | 9.1% | 14.6% | 54.1% |

⚠ **The statutory set never feeds the range.** It is evidence a reader can check. If it
ever starts feeding the range, the page gets less accurate while looking more compliant.

⚠ **The published accuracy figures render verbatim on ~5,000 live pages** ("tested against
596 Robina attached sales"). They live in `unit_valuation.ACCURACY` and
`precompute_statutory_comparables.ACCURACY` and must be **re-measured together** with any
change to the comparable set or to what counts as a sale. Never hand-edit one.

## Known debt

`render_unit_report.py` still assembles its own data rather than using
`unit_page_data.assemble()`. Refactoring it is TODO; `check_renderer_consistency.py`
guards the gap in the meantime — it caught real drift on its first run.
