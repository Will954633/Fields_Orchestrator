# gpt_arm_final

Model `gpt-5.6-terra` via openai · recovered from 43 recorded tool calls · 26,021 in / 2,613 out · ~$0.06

## FINDING 1: Public Sales Volume tile uses the unreliable transaction-count series
CATEGORY: correctness
CLAIM: The public `Sales Volume` metric is calculated from `indexed_series.transaction_count` and presented with a QoQ percentage, despite the guarded market-pulse pipeline using a separate union-count series specifically because the captured sold series is not suitable for direct volume claims.
EVIDENCE: `/home/fields/Feilds_Website/01_Website/netlify/functions/market-insights.mjs:240-248` assigns `salesVolumeQuarter` and `salesVolumePreviousQuarter` from `latestQuarter.transaction_count` and calculates QoQ; `/home/fields/Feilds_Website/01_Website/netlify/functions/market-insights.mjs:620-648` returns those fields; `/home/fields/Feilds_Website/01_Website/src/components/DataInsightsStrip/DataInsightsStrip.tsx:137-145` renders them as the public “Sales Volume” value and percentage change; `scripts/generate_market_pulse.py:290-337` instead selects union-basis `median_sample_n` counts and explicitly limits their interpretation to the union window.
STATUS: VERIFIED — I inspected the response calculation and public rendering path.
IMPACT: One public Sales Volume tile per Market Intelligence page can show a count and QoQ movement from a different series than the guarded pipeline uses for volume narration; the rendered field is a numeric market claim, not merely an internal diagnostic.
CONFIDENCE: HIGH
EFFORT: 2–4 hours
PROPOSED ACTION: Remove `sales_volume_quarter` and `sales_volume_qoq_pct` from the public strip until a canonical, reliability-labelled volume field is published from the guarded union series; alternatively have `market-insights.mjs` consume that canonical field and render it as a lower-bound/sample metric without a misleading QoQ comparison.
FALSIFIED BY: A database inspection showing that `indexed_series.transaction_count` is identical to the canonical union sales-count series for every published period and suburb, with identical basis and completeness rules.

## FINDING 2: Missing sales-volume data is rendered as “Adequate volume”
CATEGORY: correctness
CLAIM: When the pipeline deliberately omits unreliable `sales_volume_yoy_change`, the Market Direction confidence logic treats the absence as strong/adequate volume and can publicly state “Adequate volume, tight supply.”
EVIDENCE: `scripts/generate_market_pulse.py:290-337` builds a qualified union volume series rather than a year-on-year comparison; `/home/fields/Feilds_Website/01_Website/src/components/DirectionSection/DirectionSection.tsx:111-132` sets `volumeKnown = volumeChange != null`, then sets `hasStrongVolume = !volumeKnown || volumeChange > -30`; with tight absorption it returns `{ value: 'Medium-High', detail: 'Adequate volume, tight supply' }`; `/home/fields/Feilds_Website/01_Website/src/pages/MarketMetricsPage/MarketMetricsPage.tsx:806` renders `DirectionSection`.
STATUS: VERIFIED — I inspected the omission-handling branch and the rendered Market Metrics page component path.
IMPACT: Every Market Direction snapshot that lacks the deliberately suppressed volume field and has absorption below three months is eligible for a Medium-High confidence verdict carrying an affirmative volume claim unsupported by the supplied data.
CONFIDENCE: HIGH
EFFORT: 1–2 hours
PROPOSED ACTION: Make unknown volume remain unknown: replace `hasStrongVolume = !volumeKnown || volumeChange > -30` with a three-state assessment, and render “Volume not assessed” rather than “Adequate volume” when the field is absent. Do not allow an omitted volume metric to raise confidence above the level supported by the remaining signals.
FALSIFIED BY: A runtime trace or saved `market_pulse.data_snapshot` sample showing that `sales_volume_yoy_change` is always present for every snapshot rendered by `DirectionSection`.

## COVERAGE
CHECKED: `CLAUDE.md` system map and database guidance; `SCHEMA_SNAPSHOT.md` entries for `system_monitor.job_runs` and `system_monitor.market_pulse`; the latest available fix-history files (`2026-08-05.md`, `2026-08-06.md`, `2026-08-07.md`); market-pulse generation; the `market-insights` and `market-pulse` Netlify functions; SSR market-metric retrieval; and public React consumers for Sales Volume, Market Metrics, and Market Direction.
NOT CHECKED: Live database contents for `job_runs` and `market_pulse`—both attempted Mongo reads failed with `Cursor.__init__() got an unexpected keyword argument 'maxTimeMS'`; live HTTP responses and deployed-site rendering; the complete cron/process registry; all article/report generators; and all historical fix-history entries.
MOST LIKELY BLIND SPOT: Stale or contradictory stored `market_pulse` content layers and stopped jobs, because the available Mongo query mechanism failed before current documents and heartbeats could be inspected.
