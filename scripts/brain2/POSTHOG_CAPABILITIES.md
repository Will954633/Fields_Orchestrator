# PostHog Capability Reference — Fields (researched 2026-07-16)

Exhaustive map of PostHog capabilities relevant to Fields, validated against our live
US-Cloud instance with the all-access personal key (`phx_…`, in `.env` as
`POSTHOG_ALL_ACCESS_KEY`). Built during the Brain 2 v2 work.

## 0. Two definitive answers

**"Signal endpoint" — does not exist.** PostHog has no feature named Signals / signal
endpoint. What that means in practice is one of two things:
- **Alerts** — threshold/anomaly notifications on an insight (email/Slack/webhook/Telegram). Fully API-creatable. → §Alerts.
- **Realtime CDP webhook destinations** — push a single event to any URL the instant it lands (the truest "signal"). → §Webhooks. Best fit for "Telegram me when someone enters an address."

**PostHog AI session summaries — NOT accessible with any API key.** `POST
/session_recordings/{id}/summarize/` returns 403 *"does not support personal API key
access"* even with the all-access key. It's a structural DRF-permission gate (needs
browser-cookie auth), not a scope gap. `session_group_summaries` is CRUD-over-stored-
summaries only, not a generator. **We generate our own with Opus instead (Brain 2
Layer 4b) — strictly better: funnel-tuned, in-house, un-rate-limited.**

## 1. Auth model (which key for what)

| Use | Key | Notes |
|-----|-----|-------|
| Ingestion (`capture`, `batch`, `$ai_generation`, `$exception`, `/flags`) | **PROJECT token** `phc_…` | public write-only |
| Management + read APIs (query/HogQL, alerts, insights, flags, surveys, exports, recordings, snapshots) | **Personal key** `phx_…` (Bearer) | all-access key works for all |
| Heatmaps API | personal key | needs `heatmap:read` scope (all-access has it) |
| `summarize/` (AI summary) | **none** | browser-cookie only |

## 2. Capability matrix (API access + Fields relevance)

| Capability | Access (validated) | Fields relevance |
|---|---|---|
| **HogQL query** `POST /query/ {kind:HogQLQuery}` | ✅ key. **Default LIMIT 100 — always set explicit LIMIT** (this silently truncated our Layer 3 first pass). No OFFSET paging (cursor on timestamp). | Core — all Brain 2 joins |
| **`sessions` HogQL table** | ✅ per-session: `$session_duration`,`$entry_pathname`/`$exit_pathname`,`$channel_type`,`$is_bounce`,`$pageview_count`,`$entry_utm_*` | HIGH — cleaner FB attribution than manual event reconstruction |
| **Funnels** `{kind:FunnelsQuery}` | ✅ steps/drop-off/time, breakdown by `utm_content` (use `breakdown_type:session`+`$entry_utm_content`) | HIGH — ad→pageview→search→address-entry |
| **Paths** `{kind:PathsQuery}` | ✅ start/endPoint, stepLimit, `/property/*` groupings | HIGH — journey to conversion + leaks |
| **ActorsQuery** | ✅ the person_ids behind a funnel step/trend point | HIGH — pull step drop-offs, join to ad |
| **Trends/Retention/Lifecycle/Stickiness** | ✅ query kinds | MED — time-series / cohort health |
| **Session replay — metadata** `session_replay_events` view | ✅ `activity_score`,`click_count`,`keypress_count`,`active_milliseconds`,`all_urls`,console counts | HIGH — rank high-intent sessions |
| **Session replay — rrweb snapshots** `/session_recordings/{id}/snapshots?blob_v2=true` then `?source=blob_v2&start_blob_key=A&end_blob_key=B` (range **≤20 keys**, both bounds required) | ✅ key. JSONL of rrweb events → reconstruct full session → feed our Opus | HIGH — deepest "what they saw/did"; **beat TTL** (free 30d/PAYG 90d) by pulling on a rolling schedule |
| **Heatmaps** `/heatmaps/?type=click|scrolldepth&url_pattern=*/path*` | ✅ endpoint works but **returns 0 — capture is OFF**. Needs `capture_heatmaps:true` in posthog-js (forward-only). `url_pattern` matches FULL url, use wildcards | HIGH once enabled — click/scroll on feed/property/tool |
| **Autocapture `$autocapture` + `elements_chain`** | ✅ available NOW (on by default) — which CTAs/cards/links clicked | HIGH — works today, no deploy |
| **Feature flags** CRUD `/feature_flags/` + `$feature_flag_called` / `$feature/<key>` | ✅ read/write. Variant→conversion via HogQL (argMin first variant per person) | HIGH — turn informal `for_sale_page_v1`/`discover_mode_v1` into real numbers |
| **Experiments** `/experiments/` | ✅ read/write. Bayesian by default, 90/95/99% CI, ≥50 exposures + ≥5 conv/variant guardrail | HIGH — migrate conversion-critical tests; use 2-way not 4-way on quartered ad traffic |
| **Surveys** `/surveys/` (we have 0) | ✅ read/write. popover/api/widget; targeting by URL/event/flag; responses in `survey sent` event | HIGH — biggest untapped: buy-vs-sell intent + exit-intent on analyse-your-home |
| **Alerts** `/alerts/` | ✅ read/write. threshold + anomaly (beta). Free tier ≤5 alerts, hourly-or-slower (real-time=Scale+, 15min=Boost+) | HIGH — "address-entry conversions dropped" |
| **Webhook destinations (CDP)** | UI-config (no create-API). Per-event push, event-filtered, Hog-templated body, 3 retries | HIGH — Telegram on address entry, hits existing bot stack |
| **LLM analytics** `$ai_generation` (PROJECT token) | ✅ manual capture for `claude -p` (map `--output-format json` usage → tokens); OTel for SDK paths. $0.00006/evt, 100K/mo free | MED-HIGH — latency/error/quality on voice agent + editorial (NOT cost — Max is flat-rate) |
| **Error tracking** `$exception` | ✅ posthog-js autocapture (config toggle) for React; manual for Netlify fns (per-request client — no caching, per our event-loop-hang rule) | HIGH React / MED Netlify |
| **Batch export** → S3/BigQuery/Snowflake/… | UI-config, daily/hourly | MED-LOW — defer until volume |
| **Insights/Dashboards** CRUD | ✅ read/write — can stand up a "Fields Intelligence" dashboard in the PostHog UI programmatically | MED-HIGH |
| **Data warehouse (external IN)** | connect Stripe/Postgres/etc., join to events in HogQL | MED — could join FB spend natively later |

## 3. Rate limits (per-project, not per-key)
Query endpoint **240/min, 2,400/hr, 3 concurrent, 10s sync cap** (use `refresh:async`+poll beyond). CRUD 480/min. Ingestion unlimited. → batch into fewer larger HogQL queries.

## 4. PostHog MCP (for interactive Claude Code use)
Hosted HTTP server — no local process, no wizard/OAuth. Add to `.mcp.json`:
```json
"posthog": {
  "type": "http",
  "url": "https://mcp.posthog.com/mcp?readonly=true&features=flags,insights,dashboards,error_tracking",
  "headers": { "Authorization": "Bearer ${POSTHOG_ALL_ACCESS_KEY}" }
}
```
600+ tools (execute-sql, query-funnel/paths, flags, experiments, error-tracking, dashboards). Use `features=`/`tools=` to keep the tool list lean; `readonly=true` first. **Value: interactive/exploratory analytics inside Claude Code. Keep scripted/cron pipelines on the direct API** (deterministic, no token overhead).

## 5. Prioritised build/enable list for Fields
1. **Error tracking on React site** — `posthog-js` exception autocapture toggle. Cheapest high-value win; no client-side error visibility today.
2. **Realtime webhook → Telegram on address entry** — per-lead instant signal via existing bot. The real "signal endpoint."
3. **Enable heatmap capture** (`capture_heatmaps:true`) — forward-only, unlocks click/scroll maps on feed/property/tool.
4. **Alert on address-entry conversion drop** — API-creatable, daily/hourly (free tier).
5. **Surveys: buy-vs-sell intent + exit-intent on analyse-your-home** — biggest untapped signal for the seller-funded model.
6. **Migrate feed A/B to formal Experiments** (2-way) — automated significance + guardrails.
7. **Brain 2 deepening:** switch Layer 3 attribution to the native `sessions` table; add server-side Funnels/Paths; add rrweb-snapshot ingestion for richest session reconstruction (beat the replay TTL).
8. **LLM analytics** on voice agent + editorial pipeline — latency/error/quality.
9. **Add PostHog MCP** to `.mcp.json` (read-only) for interactive analysis.
10. Batch export to BigQuery — defer until volume.

All §2 rows validated against our instance 2026-07-16 unless marked. Field casing for
FunnelsQuery/PathsQuery: verify against `frontend/src/queries/schema.json` in the
PostHog repo (occasional camel/snake renames).
