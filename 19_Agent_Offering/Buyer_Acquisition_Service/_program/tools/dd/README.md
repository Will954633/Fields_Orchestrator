# dd — buyer due-diligence tools

Turn council + state data into buyer-facing due-diligence documents. Program context:
[main README §5](../../../README.md). Chain: `dd_pull.py → dd_data.json → dd_pack.py` (+ `flood_reality.py`).

Env: `source /home/fields/venv/bin/activate && set -a && source /home/fields/Fields_Orchestrator/.env && set +a`.
Deps: `requests`, `weasyprint`, `PIL`. Reads from Mongo (`Gold_Coast.<suburb>`) + the ArcGIS catalog
([`../council_data/`](../council_data/)).

## dd_pull.py — assemble the data
```bash
python3 dd_pull.py --address "93 Burleigh Street, Burleigh Waters"
# -> listings/<slug>/dd/dd_data.json
```
Resolves the parcel from the GC cadastre by `LOTPLAN` (never a geocode), queries ~19 curated DD layers
(a registry inside the file), merges the flood/zoning fields already stored on the Mongo doc, and
writes `{address, lotplan, parcel, mongo_flood_zoning, layers:[{key,label,answers,method,source_url,
as_at,status,hit,attributes}]}`. Per-layer errors are captured, not fatal.

## flood_reality.py — the flood one-pager (centrepiece)
```bash
python3 flood_reality.py --address "93 Burleigh Street, Burleigh Waters" \
  --agent "Tyler Benson" --agency "Coomera Realty" \
  --historical "<resolved historic-flood finding>" --out <path.pdf>
```
Reads the stored flood fields (`flood_designated_level_m`, `flood_ground_level_m`, `flood_freeboard_m`,
`flood_depth_description`, `in_any_ica_zone`, `ica_note`). Four-layer story + AHD level-diagram + the
three official searches. `--historical` fills the "has it ever actually flooded?" section (from
`dd_pull` findings); omit it and the section shows a "being added" placeholder.

## dd_pack.py — the full 5-section buyer pack
```bash
python3 dd_pack.py --data listings/<slug>/dd/dd_data.json \
  [--agent "…" --agency "…" --out <path.pdf>]
```
Cover → flood → hazards & overlays → location/services → nearby development → next-steps + sources.
Agent/agency default to Tyler Benson / Coomera Realty; output filename derives from the address.

## Rules (do not break)
- **Never assert a property "won't flood."** Data + source + as-at, conditional; keep the freeboard /
  downstairs-exposed caveat.
- Distinguish **modelled** extents (incl. extreme Hinze Dam PMF) from **recorded** inundation.
- We **cannot** get property-level insurance claim history (privacy) or do a physical building & pest —
  say so explicitly in the pack.
- Attribute the listing agent; clear the framing with them first; run `claim_gate.py` before publish.
- Brand: copy the palette/header from this folder's `flood_reality.py` and `../../../` info-pack style.
