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
- [x] Layer 3 — attribution refresh (32 exact + 18 campaign = 50/92; 42 untagged/unattributable)
- [x] Layer 4a — granular session behaviour store (ad_behaviour_build.py): articles+scroll depth, sections, properties, cards, rageclicks, dwell per session
- [x] Layer 4b — Opus session summaries (ad_session_summarize.py): our own, since PostHog's summarize endpoint rejects personal-API-key access
- [ ] Layer 4c (NOT AVAILABLE via API): PostHog AI summaries (personal-key rejected) + heatmaps (empty). Would need browser-cookie auth — deferred, our Opus summaries supersede.
- [x] #6 Brain 2 deepening — native sessions table (duration/bounce/entry-exit/channel) + replay metadata (active-time/clicks) merged into ad_session_behaviour/affinity; server-side funnel+paths (ad_journey.py)
- [ ] #6 forward-only: rrweb snapshot archiver (DOM replay) — blobs expire faster than metadata; build as a rolling nightly job if full replay wanted
- [ ] Query layer — Opus reads whole joined package in-context
