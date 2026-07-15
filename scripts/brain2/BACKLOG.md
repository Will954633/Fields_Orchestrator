# Brain 2 — build backlog

## TODO: patch fb-metrics-collector.py (deferred 2026-07-16)
The nightly collector still writes the WRONG `creative.format` (videos/dynamic
mislabelled) because it only requests `creative{...object_story_spec}`.
`scripts/brain2/ad_creative_enrich.py` re-corrects it 30 min later via the 23:30
cron, so this is cosmetic — but the collector should be the single source of truth.

**Fix:** in `fetch_ads_metadata()` add creative fields
`object_type,video_id,asset_feed_spec,effective_object_story_id`; in
`build_ad_profile()` replace the `object_story_spec`-only format detection +
`is_catalog_ad` heuristic with the truth table from `ad_creative_enrich.py`
(`structure_creative()`). Then the enrich script becomes annotation-only.

## Layer status
- [x] Layer 1 — ingestion fix + full creative capture (ad_creative_enrich.py)
- [ ] Layer 2 — Opus high-effort semantic annotation (in progress)
- [ ] Layer 3 — attribution refresh across ALL ads (join PostHog downstream)
- [ ] Layer 4 — PostHog granular behaviour store (recordings, AI summaries, heatmaps)
- [ ] Query layer — Opus reads whole joined package in-context
