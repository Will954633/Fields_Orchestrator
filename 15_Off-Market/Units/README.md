# Units on `/off-market`

Bringing attached dwellings (units, apartments, townhouses, villas, duplexes) into
`/off-market` coverage for Robina, Varsity Lakes and Burleigh Waters.

**Start here:** [`UNITS_DEVELOPMENT_PLAN.md`](UNITS_DEVELOPMENT_PLAN.md) — the execution document.

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
