# council_data — the council/state data catalog

Enumerates the Gold Coast City + Queensland state **ArcGIS REST catalogs** into one manifest
(`catalog.json`) — the "master file" of queryable council data. All layers are **auth-free** and
queryable per parcel by `LOTPLAN` or geometry. Program context: [main README §5](../../../README.md).

## Sources
- **Gold Coast City** — ArcGIS Online org `3vStCH7NDoBOZ5zn`
  (`services.arcgis.com/3vStCH7NDoBOZ5zn/arcgis/rest/services`) — 256 FeatureServers.
- **QLD state** — `spatial-gis.information.qld.gov.au/arcgis/rest/services` — folders incl.
  `FloodCheck`, `Historic_Flood_Lines`, `Elevation`, `Environment`.

## Usage
```bash
python3 council_catalog.py                 # crawl both roots -> catalog.json
python3 council_catalog.py --grep flood    # search the saved catalog by service-name keyword
```

`catalog.json` = `{gold_coast:[{name,type,url}], qld_state:[{folder,name,type,url}], counts}`.
The GC crawl uses the single org-root call (fast); per-service layer/field detail is fetched on
demand by `../dd/dd_pull.py`.

## Gotchas
- ⚠ **QLD service URLs must carry the folder**: `{root}/{folder}/{name}/{type}`. Dropping `{folder}`
  returns a misleading `499 Token Required`. Fixed in `crawl_qld()` (see fix-history 2026-08-23).
- Don't crawl per-service metadata for all 256 GC services in one foreground run — it exceeds the
  2-minute limit. The root list is enough for the manifest.
- Querying a layer: `GET {service_url}/{layerId}/query?f=json&where=LOTPLAN='187RP128164'&outFields=*`
  for lot/plan layers, or `geometry=<lon,lat>&geometryType=esriGeometryPoint&spatialRel=…Intersects`
  for spatial. Query at the **cadastral centroid**, not a geocode (Rule 8).
