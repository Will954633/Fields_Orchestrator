#!/usr/bin/env python3
"""Daily GCP cost monitor — snapshots spend, flags spikes, surfaces waste.

Exists because the $409.59 AUD July 2026 invoice arrived with no way to break
it down from this VM: the answer had to be modelled from the SKU price list
and live resource inventory. This closes that — once the Cloud Billing export
is on, cost becomes a query, and a bill is never a surprise again.

What it does each run:
  1. Snapshots month-to-date cost by service and by resource into
     system_monitor.gcp_costs (one doc per run).
  2. Compares yesterday's spend to the trailing median and Telegrams on a
     spike, and on a month-end forecast above the ceiling.
  3. Pulls Recommender findings (idle disks, idle IPs, oversized VMs) with
     their dollar amounts — the automated version of the manual audit that
     found an unmounted 400 GB disk billing ~$94 AUD/month.

Auth: runs on the gcloud user credentials in /home/projects/.config/gcloud.
The VM's attached service account (419034603899-compute@…) canNOT be used —
its scopes omit BigQuery and changing scopes requires stopping the VM. If
those credentials ever lapse, this job errors rather than silently reporting
$0, and lands as ERROR on the health board.

Cron (07:40 AEST daily, after the 02:00 backups and the nightly pipeline):
  40 7 * * * cd /home/fields/Fields_Orchestrator && set -a && source .env && \
    set +a && /home/fields/venv/bin/python3 scripts/gcp_cost_monitor.py \
    >> logs/gcp-cost-monitor.log 2>&1
"""
from __future__ import annotations

import datetime
import json
import os
import statistics
import subprocess
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from gcp_cost_report import (  # noqa: E402
    BILLING_ACCOUNT,
    CostDataUnavailable,
    PROJECT,
    breakdown,
    daily_totals,
    existing_tables,
    pick_table,
)
from job_status import job_run  # noqa: E402

# A day is a "spike" if it exceeds the trailing median by this factor. The
# floor stops trivial absolute swings from paging: early in a month, or on a
# quiet day, a few dollars can be several multiples of the median.
SPIKE_FACTOR = float(os.environ.get("GCP_COST_SPIKE_FACTOR", "1.6"))
SPIKE_FLOOR = float(os.environ.get("GCP_COST_SPIKE_FLOOR", "8"))
MONTHLY_CEILING = float(os.environ.get("GCP_COST_MONTHLY_CEILING", "500"))

RECOMMENDERS = {
    "google.compute.disk.IdleResourceRecommender": "idle disk",
    "google.compute.address.IdleResourceRecommender": "idle IP",
    "google.compute.instance.IdleResourceRecommender": "idle VM",
    "google.compute.instance.MachineTypeRecommender": "VM rightsizing",
}
LOCATIONS = ["australia-southeast1-b", "australia-southeast1-a", "australia-southeast1"]


def _mongo():
    from pymongo import MongoClient
    conn = os.environ.get("COSMOS_CONNECTION_STRING")
    if not conn:
        raise RuntimeError("COSMOS_CONNECTION_STRING not set")
    return MongoClient(conn)


def fetch_recommendations():
    """Cost-saving recommendations with dollar amounts. Best-effort: the
    Recommender API needs days of observation history before it returns
    anything, so an empty result is normal and not an error."""
    found = []
    for rec_id, label in RECOMMENDERS.items():
        for loc in LOCATIONS:
            r = subprocess.run(
                ["gcloud", "recommender", "recommendations", "list",
                 f"--project={PROJECT}", f"--location={loc}",
                 f"--recommender={rec_id}", "--format=json", "--quiet"],
                capture_output=True, text=True,
            )
            if r.returncode != 0 or not r.stdout.strip():
                continue
            try:
                items = json.loads(r.stdout)
            except json.JSONDecodeError:
                continue
            for it in items:
                cost = (it.get("primaryImpact", {})
                          .get("costProjection", {})
                          .get("cost", {}))
                # Savings come back as a NEGATIVE cost projection (cost avoided),
                # so flip the sign to report a positive monthly saving.
                units = float(cost.get("units", 0)) + float(cost.get("nanos", 0)) / 1e9
                found.append({
                    "type": label,
                    "description": it.get("description", ""),
                    "monthly_saving": round(-units, 2),
                    "currency": cost.get("currencyCode", ""),
                    "location": loc,
                })
    return sorted(found, key=lambda x: -x["monthly_saving"])


def analyse(beat):
    tables = existing_tables()
    table = pick_table(tables)  # raises CostDataUnavailable if not enabled yet
    has_resource_detail = table.startswith("gcp_billing_export_resource")

    today = datetime.date.today()
    month = today.strftime("%Y-%m")

    by_service = breakdown(month, "service", limit=30, table=table)
    by_resource = (breakdown(month, "resource", limit=15, table=table)
                   if has_resource_detail else [])
    dailies = daily_totals(days=30, table=table)

    mtd = sum(float(r["net_cost"]) for r in by_service)
    currency = (by_service[0]["currency"] if by_service else "") or ""

    # Forecast month-end by run-rate. Exclude today: its rows are still
    # landing, so counting it would drag the daily average down all morning.
    complete = [d for d in dailies if d["day"] < today.isoformat()]
    days_elapsed = len({d["day"] for d in complete if d["day"][:7] == month}) or 1
    days_in_month = (datetime.date(today.year + (today.month == 12),
                                   today.month % 12 + 1, 1)
                     - datetime.timedelta(days=1)).day
    mtd_complete = sum(float(d["net_cost"]) for d in complete if d["day"][:7] == month)
    forecast = (mtd_complete / days_elapsed) * days_in_month if days_elapsed else 0.0

    alerts = []

    # Spike check against the trailing median, ignoring today's partial day.
    if len(complete) >= 8:
        *history, yesterday = complete[-8:]
        y_cost = float(yesterday["net_cost"])
        median = statistics.median(float(d["net_cost"]) for d in history)
        if median > 0 and y_cost > max(median * SPIKE_FACTOR, SPIKE_FLOOR):
            alerts.append(
                f"Daily spend spike: {yesterday['day']} cost {y_cost:,.2f} {currency}, "
                f"{y_cost / median:.1f}x the trailing 7-day median of {median:,.2f}."
            )

    if forecast > MONTHLY_CEILING:
        alerts.append(
            f"Month-end forecast {forecast:,.2f} {currency} exceeds the "
            f"{MONTHLY_CEILING:,.0f} ceiling (month-to-date {mtd:,.2f} over "
            f"{days_elapsed} complete days)."
        )

    recs = fetch_recommendations()
    savings = sum(r["monthly_saving"] for r in recs if r["monthly_saving"] > 0)
    if savings > 0:
        top = "; ".join(f"{r['type']} {r['monthly_saving']:,.2f}" for r in recs[:3])
        alerts.append(f"Recommender sees {savings:,.2f}/month of removable waste — {top}.")

    doc = {
        "captured_at": datetime.datetime.now(datetime.timezone.utc),
        "billing_account": BILLING_ACCOUNT,
        "month": month,
        "currency": currency,
        "month_to_date": round(mtd, 2),
        "forecast_month_end": round(forecast, 2),
        "days_elapsed": days_elapsed,
        "by_service": [{"name": r["name"], "cost": round(float(r["net_cost"]), 2)}
                       for r in by_service],
        "by_resource": [{"name": r["name"], "cost": round(float(r["net_cost"]), 2)}
                        for r in by_resource],
        "daily": [{"day": d["day"], "cost": round(float(d["net_cost"]), 2)}
                  for d in dailies],
        "recommendations": recs,
        "alerts": alerts,
        "has_resource_detail": has_resource_detail,
    }
    with _mongo() as client:
        client["system_monitor"]["gcp_costs"].insert_one(dict(doc))

    if alerts:
        try:
            from telegram_notify import send_message
            top_services = ", ".join(
                f"{r['name']} {float(r['net_cost']):,.0f}" for r in by_service[:3])
            send_message(
                f"*GCP cost — {month}*\n"
                f"Month-to-date {mtd:,.2f} {currency}, forecast {forecast:,.2f}\n"
                f"Top: {top_services}\n\n" + "\n".join(f"• {a}" for a in alerts)
            )
        except Exception as e:  # noqa: BLE001 — a failed notify must not fail the job
            print(f"WARN: Telegram notify failed: {e}", file=sys.stderr)

    top_line = by_service[0]["name"] if by_service else "n/a"
    beat.detail = (f"{month} MTD {mtd:,.2f} {currency}, forecast {forecast:,.2f}, "
                   f"top={top_line}, {len(alerts)} alert(s)")
    beat.metrics = {
        "month_to_date": round(mtd, 2),
        "forecast_month_end": round(forecast, 2),
        "alerts": len(alerts),
        "recommended_savings": round(savings, 2),
        "resource_detail": has_resource_detail,
    }
    print(beat.detail)
    for a in alerts:
        print(f"  ALERT: {a}")


def main():
    with job_run("gcp_cost_monitor", cadence_hours=24,
                 title="GCP Cost Monitor") as beat:
        try:
            analyse(beat)
        except CostDataUnavailable as e:
            # Deliberately fatal. A monitor that shrugs when its data source is
            # missing is the silent failure Rule 7 exists to prevent — this has
            # to read as ERROR on the health board until the export is enabled.
            raise RuntimeError(f"GCP cost data unavailable — {e}") from e


if __name__ == "__main__":
    main()
