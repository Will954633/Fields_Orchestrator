# Implementor Execution Brief — CEO Team Blockers

Prepared: 2026-03-18 13:30 AEST
Owner: Implementor on `Fields_Orchestrator` VM
Requested by: Will via ManagementBot / CEO team handoff
Priority: Critical

## Objective

Clear the three active execution blockers already identified by the CEO team and documented across ops, proposal, and fix-history artifacts:

1. Stabilize enrichment + coverage telemetry.
2. Repair attribution + experiment telemetry.
3. Restore sold-comps API + contract probes.

This file is the canonical implementor handoff. Work from this brief rather than reconstructing the issue from multiple context exports.

## Source Of Truth

Read these first, in order:

1. `OPS_STATUS.md`
2. `artifacts/implementation-runs/2026-03-18/2026-03-18_110440_review/review.md`
3. `artifacts/ceo-runs/2026-03-18/2026-03-18_094424/summary.md`
4. `logs/fix-history/2026-03-17.md`
5. `logs/fix-history/2026-03-18.md`
6. `ceo-founder-requests/open/Issue-1-18th-March.md`
7. `ceo-founder-requests/responses/Issue-1-18th-March.md`

## Required Delivery Sequence

Do the work in this order so downstream validation is meaningful:

1. Restore the sold-comps API contract.
2. Repair telemetry and experiment attribution.
3. Stabilize enrichment reruns and coverage reporting.
4. Re-run validation checks and document outcomes.

## Workstream 1: Restore Sold-Comps API Contract

### Problem

`/api/v1/properties/recently-sold` still returns `404` while `/api/v1/recently-sold/health` is green.

### Why it matters now

This is a user-facing break and removes sold-proof modules from the site while falsely implying the feature is healthy.

### Likely starting points

- `netlify/functions/recently-sold.mjs`
- Any route wiring or redirects that distinguish:
  - `/api/v1/recently-sold`
  - `/api/v1/properties/recently-sold`
- Any health/probe logic that currently checks only the health endpoint

### Acceptance check

- `/api/v1/properties/recently-sold` returns `200`
- payload shape matches the intended public contract
- health and data routes are both checked by the same probe path
- `OPS_STATUS.md` no longer reports the endpoint as `404`

## Workstream 2: Repair Attribution + Experiment Telemetry

### Problem

Google Ads reports clicks/conversions while website telemetry still shows zero Google sessions, malformed page paths, and empty experiment arrays.

### Why it matters now

Will cannot review experiments, growth cannot trust KPI reporting, and paid traffic decisions are currently being made on broken measurement.

### Likely starting points

- `scripts/website-metrics-collector.py`
- website tracking utilities and event emitters already touched in the 2026-03-17 fix log
- any visitor/session pipeline responsible for:
  - `page_path`
  - `source / utm attribution`
  - experiment variant capture
  - `view_content`
  - thank-you / conversion events

### Minimum contract to restore

- valid normalized page paths
- Google traffic recorded as Google traffic, not only direct
- active experiment variants recorded in telemetry
- conversion events tied to real completion paths rather than page views
- exports must fail loudly or warn clearly when channel counts are zero or malformed

### Acceptance check

- one traced manual session produces the expected source, page path, and variant data
- website metrics export shows non-zero Google sessions when Google-tagged traffic exists
- experiment arrays populate for active tests
- no impossible dwell times or full-URL page paths remain in output

## Workstream 3: Stabilize Enrichment + Coverage Telemetry

### Problem

OPS still shows repeated failures around steps `106`, `11`, and `15`, only `180 / 50,428` actives enriched, and stale/unknown suburb coverage for Merrimac, Mudgeeraba, and Reedy Creek.

### Why it matters now

Product reliability is broken, coverage reporting cannot be trusted, and downstream UX/storytelling work is blocked by stale or partial data.

### Likely starting points

- `scripts/step106_floor_plan.py`
- `scripts/backend_enrichment/parse_room_dimensions.py`
- `scripts/backend_enrichment/calculate_property_insights.py`
- `shared/ru_guard.py`
- `config/process_commands.yaml`
- any scraper-health writer or OPS refresh code that populates suburb freshness

### Required behavior

- Cosmos/RU throttling must not silently produce empty worksets
- transient per-record errors must not mark a mostly successful run as failed
- coverage telemetry must distinguish "not run", "stale", and "healthy" correctly
- reruns should leave enough evidence to verify whether target suburbs recovered

### Acceptance check

- step `106` no longer sits in a false-running or false-success state
- step `11` and step `15` stop failing on isolated transient write errors
- suburb coverage/freshness updates for Merrimac, Mudgeeraba, and Reedy Creek
- refreshed ops snapshot reflects recovered status with current timestamps

## Validation Checklist

Before closing the work, capture:

1. current `OPS_STATUS.md`
2. live probe result for `/api/v1/properties/recently-sold`
3. one traced telemetry session showing source + variant + conversion path
4. rerun evidence for the affected enrichment steps
5. updated fix-history entry for each material repair

## Definition Of Done

The handoff is complete only when all three conditions are true:

1. sold-comps route works on the documented public path
2. telemetry supports manual founder review of experiments and traffic quality
3. ops coverage/enrichment health is current enough that CEO/Product/Growth can reason from it without caveats

## Reporting Back

When finished, update the paired response thread:

- `ceo-founder-requests/responses/2026-03-18-engineering-hello.md`

and include:

- what was fixed
- what remains blocked
- exact validation evidence
- any founder approval still needed
