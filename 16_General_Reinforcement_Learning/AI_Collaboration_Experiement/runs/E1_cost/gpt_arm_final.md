# gpt_arm_final

Model `gpt-5.6-terra` via openai · recovered from 49 recorded tool calls · 29,855 in / 4,617 out · ~$0.08

## FINDING 1: GCP cost controls are blind after a documented $94/month disk-waste incident
CATEGORY: cost
CLAIM: The GCP cost monitor cannot presently provide resource-level spend or detect idle-resource waste because the required Cloud Billing export tables do not exist.
EVIDENCE: `logs/gcp-cost-monitor.log` records `CostDataUnavailable: No export tables in fields-estate:billing_export yet`; the monitor deliberately raises an error in this condition at `scripts/gcp_cost_monitor.py:220-221`; the report’s table-discovery implementation returns no tables when BigQuery has none at `scripts/gcp_cost_report.py:54-60`; a prior manual audit found an unmounted 400-GB disk billing approximately $94 AUD/month at `logs/fix-history/2026-08-05.md:365`.
STATUS: VERIFIED — I inspected the failing monitor log and the executed failure path; I did not establish whether the previously identified disk, or another idle resource, still exists.
IMPACT: Current monthly saving cannot be established without billing-export data. The verified historical exposure is approximately $94 AUD/month for one unmounted disk (`logs/fix-history/2026-08-05.md:365`). More broadly, the system cannot currently measure actual GCP resource costs, despite the monitor being designed to identify idle disks, IPs, and oversized VMs (`scripts/gcp_cost_monitor.py:9-16`).
CONFIDENCE: HIGH
EFFORT: 1 hour to enable export; 1–2 days before useful resource-level billing data appears.
PROPOSED ACTION: Enable standard and detailed Cloud Billing export for project `fields-estate` to dataset `billing_export` in the GCP Console, wait for data ingestion, then run `scripts/gcp_cost_report.py --by resource` and remove or downsize every resource with no operational owner. Treat the approximately $94/month historical disk finding as the first item to re-check.
FALSIFIED BY: BigQuery contains the expected billing-export tables, `gcp_cost_report.py --by resource` returns current resource costs, and that report shows no idle, unattached, or oversized resource with material cost.

## FINDING 2: The daily cost collector repeats the same Netlify deployment-list request four times
CATEGORY: cost
CLAIM: Each scheduled `cost-collector.py --days 4` run recomputes four dates and, when a Netlify token is configured, requests the identical latest-100-deployments endpoint once for each date rather than fetching once and partitioning locally.
EVIDENCE: The cron schedule invokes `cost-collector.py --days 4` daily at `logs/crontab-backups/crontab-20260805-1214-pre-gcp-cost.bak:57-59`; the collector log repeatedly reports collection of four overlapping dates in `logs/cost-collector.log`; each daily snapshot calls `get_netlify_builds(date_str)` at `scripts/cost-collector.py:213-219`; that function calls a date-independent `/deploys?per_page=100` endpoint at `scripts/cost-collector.py:186-207`, then filters the returned list locally by `date_str` at `scripts/cost-collector.py:202`.
STATUS: VERIFIED — I inspected the cron entry and code path. I could not establish whether `NETLIFY_AUTH_TOKEN` is set, so I could not establish the actual number of live API requests.
IMPACT: If the Netlify token is configured, this produces 120 deployment-list API requests per 30-day month instead of 30: 90 avoidable requests/month, a 75% reduction in this request class. Dollar saving is not established; the evidence does not show Netlify charging per API request. It also repeats the other per-date collector work, whose individual implementations were not fully inspected.
CONFIDENCE: HIGH
EFFORT: 1–2 hours
PROPOSED ACTION: In the four-day collection run, fetch Netlify deployments once, group them by `created_at` date in memory, and pass each day’s count into snapshot construction. More generally, collect all four dates in one provider read where providers support a date range.
FALSIFIED BY: `NETLIFY_AUTH_TOKEN` is absent in the cron environment, or execution tracing shows `get_netlify_builds()` is not reached during the scheduled collector run.

## FINDING 3: Minute-by-minute Cosmos VM telemetry creates at least 86,400 database operations per 30-day month
CATEGORY: cost
CLAIM: The VM-metrics cron performs at least one Cosmos insert and one Cosmos read every minute, creating at least 43,200 inserts plus 43,200 reads per 30-day month before any cleanup operations.
EVIDENCE: Cron runs `write_vm_metrics.py` every minute at `logs/crontab-backups/crontab-20260805-1214-pre-gcp-cost.bak:57-59`; the script inserts one document with `col.insert_one(doc)` at `write_vm_metrics.py:55-71`; immediately afterwards it performs `col.find(...).sort(...).limit(61)` at `write_vm_metrics.py:73-75`.
STATUS: INFERRED — the operation count follows directly from the schedule and code, but I could not establish the required telemetry resolution, actual Cosmos RU charge, or whether any consumer needs one-minute data.
IMPACT: At least 86,400 Cosmos database calls per 30-day month are generated by this job alone, excluding possible deletion calls after the shown cleanup query. Reducing collection from every minute to every 15 minutes would reduce these baseline insert/read calls by 80,640 per month (93.3%); hourly collection would reduce them by 85,680 per month (99.2%). AUD saving cannot be calculated because no RU-consumption or Cosmos billing data was available.
CONFIDENCE: MEDIUM
EFFORT: 2–4 hours
PROPOSED ACTION: Identify every reader of `system_monitor.vm_metrics`; if no alert or dashboard requires one-minute granularity, change the cron to every 15 minutes, retain alert-relevant aggregates, and add a Cosmos TTL/indexed-retention policy rather than performing recurring client-side retention reads.
FALSIFIED BY: A consumer or alert rule demonstrably requires one-minute samples, or Cosmos RU metrics show this collection’s insert/read workload is immaterial relative to total consumption.

## COVERAGE
CHECKED: `CLAUDE.md`; `SCHEMA_SNAPSHOT.md`; available crontab backups; the latest available fix-history files, especially `2026-08-04.md` through `2026-08-07.md`; `scripts/cost-collector.py`; `scripts/gcp_cost_report.py`; `scripts/gcp_cost_monitor.py`; `write_vm_metrics.py`; `scripts/refresh-ops-context.py`; `generate_schema_snapshot.py`; `scripts/mongodb-backup.sh`; `logs/cost-collector.log`; `logs/gcp-cost-monitor.log`; `logs/schema_snapshot.log`; `logs/mongodb-backup.log`; and selected disk/backup evidence.
NOT CHECKED: Current GCP resource inventory, disk attachments, snapshots, static IPs, buckets, and machine utilisation; actual Azure Cosmos RU metrics and index usage; live Netlify usage/billing and function invocation metrics; live provider API-token configuration; individual pipeline query patterns; LLM provider invoices and token-level usage; website function connection-pooling and cache-header behaviour. The attempted `system_monitor.cost_tracking` query failed with a Mongo cursor error, so no cost-tracking documents were inspected.
MOST LIKELY BLIND SPOT: Actual current GCP resource charges and Cosmos RU consumption. The GCP billing export is unavailable in the inspected record, while the cost collector uses fixed estimates for infrastructure rather than demonstrated resource-level billing (`scripts/cost-collector.py:42-62`, `scripts/cost-collector.py:220-237`).
