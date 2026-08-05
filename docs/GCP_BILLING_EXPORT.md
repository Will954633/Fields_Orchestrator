# GCP Billing Export → BigQuery → this VM

Purpose: make "what is this Google bill?" an exact query instead of a
reconstruction from the SKU price list. Set up 2026-08-05 after the
$409.59 AUD July invoice could only be answered by modelling.

Billing account: **`015552-D96B77-2718DA`** ("Fields Data Management 01") —
covers `fields-estate` and `fields-estate-ads`. The scraper VMs bill to
`0154C4-059CFE-8490AD` and are a separate invoice.

---

## Why it needs a human

There is **no API and no `gcloud` command** to configure billing export. The
Cloud Billing API (v1 + v1beta) only exposes the pricing catalog, account
metadata, project links and budgets — nothing that writes export settings.
Verified against the discovery documents on 2026-08-05. The switch is
Console-only, so an agent cannot flip it.

`will.simpson@blueoceans.com.au` holds `roles/billing.admin` on the account,
which is the role required.

## Already done (no action needed)

- BigQuery dataset **`fields-estate:billing_export`** created in
  `australia-southeast1`
- `cloudbilling.googleapis.com` enabled on `fields-estate`
- `bigquerydatatransfer.googleapis.com` enabled on `fields-estate`
  (prerequisite for the export)
- `scripts/gcp_cost_report.py` written and verified to fail gracefully until
  the tables appear

## The remaining step (Console, ~1 minute)

1. Open <https://console.cloud.google.com/billing/015552-D96B77-2718DA/export/bigquery>
2. Under **Detailed usage cost**, click **Edit settings**
3. Project `fields-estate`, dataset `billing_export` → **Save**
4. Optionally repeat for **Pricing** (same dataset) — this lands the SKU rate
   card locally so unit prices can be joined without hitting the catalog API

Choose **Detailed**, not Standard. Detailed adds `resource.name`, which is what
attributes cost to an individual disk or VM. Standard stops at the SKU, so it
would say "Balanced PD Capacity: $67" without telling you which of the two
balanced disks it was.

### Two caveats worth knowing up front

- **Not retroactive.** The export only contains data from the day it is
  enabled. It will never explain the July 2026 invoice.
- **~24h lag** before the first table appears, and rows land throughout the day
  rather than in one nightly batch.

## For a past invoice (retroactive, one-off)

The export can't reach backwards, but the Cost Table can:

1. <https://console.cloud.google.com/billing/015552-D96B77-2718DA/costTable>
2. Pick the invoice month → **Download CSV**
3. Drop it anywhere on the VM and it can be parsed directly — it is SKU-level
   and reconciles exactly to the invoice total

This is the fastest route to an exact breakdown of an invoice already received.

## Using it once enabled

```bash
python3 scripts/gcp_cost_report.py                    # current month, by service
python3 scripts/gcp_cost_report.py --month 2026-08    # a specific month
python3 scripts/gcp_cost_report.py --by sku           # by SKU
python3 scripts/gcp_cost_report.py --by resource      # per-disk / per-VM
python3 scripts/gcp_cost_report.py --by project
```

Figures are **net of credits** — sustained-use discounts and free-tier arrive
as negative rows in the `credits` array, so a plain `SUM(cost)` overstates
every line. The script adds them back, matching what the Console reports.

## Cost of the export itself

Negligible. BigQuery storage is ~$0.02/GB/month and this account generates on
the order of a few hundred MB per year; the first 1 TB of query per month is
free.

## The automated job

`scripts/gcp_cost_monitor.py` runs daily at **07:40 AEST** and:

1. Snapshots month-to-date cost by service and by resource into
   `system_monitor.gcp_costs`
2. Telegrams on a daily spike (> `GCP_COST_SPIKE_FACTOR`, default 1.6× the
   trailing 7-day median, with a `GCP_COST_SPIKE_FLOOR` of $8 so a quiet day
   can't page on a few dollars) and on a month-end forecast above
   `GCP_COST_MONTHLY_CEILING` (default 500)
3. Pulls Recommender findings — idle disks, idle IPs, VM rightsizing — with
   their dollar amounts

It self-registers via `job_run(cadence_hours=24)` per CLAUDE.md Rule 7 and
appears on the Process Registry page of the Fields Systems Health sheet.

`gcp_cost_report.py` stays an on-demand CLI; the monitor imports its query
layer rather than duplicating it.

### It will show ERROR until the export is enabled

That is deliberate. A monitor that shrugs when its data source is missing is
exactly the silent failure Rule 7 exists to prevent, so the job raises rather
than recording a misleading success. It is a quiet failure — the Telegram path
lives past the point where it raises, so there is no daily message, just a red
row on the health board that clears itself the day after the export starts
producing tables.

### Auth, and why it isn't a service account

The job runs on the gcloud **user** credentials in
`/home/projects/.config/gcloud`. The VM's attached service account
(`419034603899-compute@developer.gserviceaccount.com`) cannot be used: its
scopes are `devstorage.read_only`, `logging.write`, `monitoring.write`,
`pubsub`, `service.management.readonly`, `servicecontrol`, `trace.append` —
no BigQuery, and **changing a VM's scopes requires stopping the VM**.

If those user credentials ever lapse, the job errors rather than reporting
$0, so it surfaces on the health board instead of going quiet. If it becomes a
recurring nuisance, the fix is a dedicated service account with BigQuery Job
User plus Data Viewer on the dataset, keyed via `.env` — not a VM restart.

## Dead end, recorded so it isn't retried

`POST https://cloudbilling.googleapis.com/v1beta:generateInsights` accepts a
natural-language prompt over billing data and looked like it would sidestep the
export entirely. It authenticates and gets as far as streaming "Compiling
data…" thought chunks, then returns `500 INTERNAL` every time, across several
prompt shapes, on 2026-08-05. Preview API, not usable.
