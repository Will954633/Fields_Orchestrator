#!/usr/bin/env python3
"""GCP cost breakdown from the BigQuery Cloud Billing export.

Reads whichever export tables exist in fields-estate:billing_export and prints
a cost breakdown for a month. The detailed export carries resource-level rows
(per-disk, per-VM), which is what lets us answer "which disk costs what"
instead of modelling it from the SKU price list.

Usage:
  python3 scripts/gcp_cost_report.py                    # current month, by service
  python3 scripts/gcp_cost_report.py --month 2026-08    # a specific month
  python3 scripts/gcp_cost_report.py --by sku           # break down by SKU
  python3 scripts/gcp_cost_report.py --by resource      # per-resource (detailed export only)
  python3 scripts/gcp_cost_report.py --by project

Note: the export is not retroactive — it only holds data from the day it was
switched on in the Cloud Console. See docs/GCP_BILLING_EXPORT.md.
"""
import argparse
import datetime
import json
import subprocess
import sys

PROJECT = "fields-estate"
DATASET = "billing_export"
BILLING_ACCOUNT = "015552-D96B77-2718DA"
_SUFFIX = BILLING_ACCOUNT.replace("-", "_")

STANDARD_TABLE = f"gcp_billing_export_v1_{_SUFFIX}"
DETAILED_TABLE = f"gcp_billing_export_resource_v1_{_SUFFIX}"


def bq(args):
    return subprocess.run(
        ["bq", f"--project_id={PROJECT}", "--format=json", "--quiet"] + args,
        capture_output=True, text=True,
    )


def existing_tables():
    r = bq(["ls", "--max_results=1000", f"{PROJECT}:{DATASET}"])
    if r.returncode != 0:
        sys.exit(f"Cannot list {PROJECT}:{DATASET} — {r.stderr.strip()}")
    if not r.stdout.strip():
        return []
    return [t["tableReference"]["tableId"] for t in json.loads(r.stdout)]


def query(sql):
    r = bq(["query", "--use_legacy_sql=false", "--max_rows=500", sql])
    if r.returncode != 0:
        sys.exit(f"Query failed:\n{r.stderr.strip()}")
    return json.loads(r.stdout) if r.stdout.strip() else []


def month_bounds(month):
    start = datetime.date(int(month[:4]), int(month[5:7]), 1)
    end = datetime.date(start.year + (start.month == 12), start.month % 12 + 1, 1)
    return start.isoformat(), end.isoformat()


# Cost is net of credits: sustained-use discounts and free tier arrive as
# negative-amount rows in the credits array, so a raw SUM(cost) overstates
# every line. This is the same "cost + credits" figure the console shows.
NET_COST = "SUM(cost) + SUM(IFNULL((SELECT SUM(c.amount) FROM UNNEST(credits) c), 0))"

DIMENSIONS = {
    "service": "service.description",
    "sku": "sku.description",
    "project": "IFNULL(project.name, '(unattributed)')",
    "resource": "IFNULL(resource.name, '(no resource)')",
}


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--month", default=datetime.date.today().strftime("%Y-%m"),
                   help="YYYY-MM (default: current month)")
    p.add_argument("--by", default="service", choices=sorted(DIMENSIONS),
                   help="dimension to break down by (default: service)")
    p.add_argument("--limit", type=int, default=30)
    args = p.parse_args()

    tables = existing_tables()
    if not tables:
        sys.exit(
            f"No export tables in {PROJECT}:{DATASET} yet.\n"
            "The export still needs to be switched on in the Cloud Console — see\n"
            "docs/GCP_BILLING_EXPORT.md. Tables appear within ~24h of enabling it."
        )

    if args.by == "resource":
        if DETAILED_TABLE not in tables:
            sys.exit(
                "--by resource needs the DETAILED export, which isn't enabled.\n"
                f"Found only: {', '.join(tables)}\n"
                "Enable 'Detailed usage cost' in the Cloud Console."
            )
        table = DETAILED_TABLE
    else:
        table = DETAILED_TABLE if DETAILED_TABLE in tables else STANDARD_TABLE
        if table not in tables:
            sys.exit(f"Expected {STANDARD_TABLE} or {DETAILED_TABLE}; found: {', '.join(tables)}")

    start, end = month_bounds(args.month)
    dim = DIMENSIONS[args.by]
    rows = query(f"""
        SELECT {dim} AS name,
               {NET_COST} AS net_cost,
               ANY_VALUE(currency) AS currency
        FROM `{PROJECT}.{DATASET}.{table}`
        WHERE DATE(usage_start_time) >= '{start}'
          AND DATE(usage_start_time) < '{end}'
        GROUP BY name
        HAVING ROUND(net_cost, 2) != 0
        ORDER BY net_cost DESC
        LIMIT {args.limit}
    """)

    if not rows:
        sys.exit(f"No usage rows for {args.month} in {table}. "
                 "If the export was enabled after that month, the data won't exist.")

    total = sum(float(r["net_cost"]) for r in rows)
    currency = rows[0]["currency"] or ""
    width = max(len(r["name"]) for r in rows)

    print(f"\n{args.month} — cost by {args.by}  (net of credits, from {table})\n")
    for r in rows:
        cost = float(r["net_cost"])
        print(f"  {r['name']:<{width}}  {cost:>10,.2f} {currency}  {cost / total * 100:5.1f}%")
    print(f"  {'TOTAL':<{width}}  {total:>10,.2f} {currency}\n")


if __name__ == "__main__":
    main()
