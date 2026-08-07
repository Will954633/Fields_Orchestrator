# Address-level enrichment propagation across cadastral entities

**Raised:** 2026-08-07 · **Status:** OPEN, not started · **Severity:** potentially material beyond SEO
**Found during:** `[OFFMARKET-MULTILOT-OSCILLATOR]` (see `logs/fix-history/2026-08-07.md`)

## The problem in one line

Enrichment is attached to cadastral records **by address string**, without first
resolving which real-world property entity it belongs to — so every cadastral row
sharing an address receives the same transactions, photos, valuation and floorplan,
while `LOT` / `PLAN` / land area stay record-specific.

## Evidence

**10 Wayville Place, Robina** — two records, ~13 m apart, *different parcels*:

| | LOT 1 | LOT 2 |
|---|---|---|
| land area | 459 sqm | 478 sqm |
| latitude | -28.07755639 | -28.07766997 |
| transactions | 8 | 8 — **byte-identical** |

Both carry the same eight sales, same dates, same prices, **down to the agent
names** (`RW Broadbeach`, `_Place Gold Coast`, `REMAX Regency - Gold Coast`,
`Ray White Robina`). Two differently-sized parcels cannot share literally the same
sale history. One of these records is displaying another property's past.

**Not a pooling artefact.** If two homes' histories were merged you would expect
roughly double the transactions. Measured across Robina: colliding pages average
**3.57** transactions, non-colliding **3.42** — indistinguishable. So this is *one*
property's history copied onto both records, not two histories combined.

**It is not limited to transactions.** Across all 166 collision groups, photos,
`cadastral_photos_count`, valuation presence and floorplan extraction are identical
within every group. Only cadastral identity fields differ.

**Worked example of the resulting falsehood — 4 Tea Gardens Place, Robina:**
the 116 sqm easement parcel rendered the 829 sqm house's imagery and valuation
while displaying **116 sqm** as its land area. That page was live and indexable.

## Why this matters beyond SEO

The immediate SEO exposure is contained — those records are now `noindex` under
`offmarket_entity_unresolved` (132 records) or `offmarket_multilot` (157). But the
underlying join is not SEO-specific, so the same contamination may reach:

- valuation modelling inputs
- comparable-sale selection
- automated appraisal reports
- homeowner-facing reports and mini-sites
- AI editorial (sale-history claims are asserted as fact)
- historical sale presentation
- land-value reconciliation
- property feature attribution

**None of these have been checked.** The SEO fix deliberately did not touch them.

## What the fix actually is

```
current:  address → transactions/photos/floorplan/valuation → every cadastral row matching address
needed:   real property entity → correct cadastral record → correct enrichment
```

## Scope of the affected set (measured 2026-08-07)

- 166 colliding slug bases across robina / varsity_lakes / burleigh_waters
- 391 cadastral records in those groups
- 63 groups (132 records) where entity identity is genuinely unresolved
- Not yet measured: how many *non-colliding* records also received address-joined
  enrichment. **Slug collision is how this was noticed, not necessarily its boundary** —
  the join has no reason to respect collision groups, so the affected set is
  plausibly much larger.

## Suggested first steps

1. Find the join. Identify every writer that attaches `enriched_data.transactions`,
   photos, valuation or floorplans keyed on address rather than on a resolved entity.
2. Quantify blast radius beyond collision groups (see caveat above).
3. Check whether valuation/comps consumed contaminated history — this is the
   highest-consequence path, since it feeds `reconciled_valuation` and appraisals.
4. Decide the entity model: what is the stable identifier for "one real home", and
   how do cadastral rows map onto it.
5. Only then revisit `offmarket_entity_unresolved` — those 132 records become
   releasable once identity is resolvable.

## Related

- `logs/fix-history/2026-08-07.md` → `[OFFMARKET-MULTILOT-OSCILLATOR]`
- `scripts/flag_multilot_offmarket.py` (module docstring explains the two states)
- `system_monitor.offmarket_entity_diagnostics` — the 64 unresolved groups
- Planned rename `offmarket_multilot` → `offmarket_entity_duplicate`
- Slug reassignment: 6 addresses where a non-dwelling parcel holds the unsuffixed URL
