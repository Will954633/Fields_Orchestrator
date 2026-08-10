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

## Known debt

`render_unit_report.py` still assembles its own data rather than using
`unit_page_data.assemble()`. Refactoring it is TODO; `check_renderer_consistency.py`
guards the gap in the meantime — it caught real drift on its first run.
