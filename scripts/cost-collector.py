#!/home/fields/venv/bin/python3
"""
Cost collector — gathers daily expense data from all platforms and stores
a unified snapshot in system_monitor.cost_tracking.

Platforms tracked:
  - Facebook Ads (from ad_daily_metrics)
  - Google Ads (from google_ads_daily_metrics)
  - Google Cloud (fixed VM cost estimate)
  - Azure Cosmos DB (serverless estimate from RU consumption)
  - Azure Blob Storage (fixed estimate from known usage)
  - Netlify (plan cost + build minutes from API)
  - Codex / CEO agents (token costs from ceo_runs)
  - Domain tools (Netlify DNS, domain registration — fixed)

Usage:
  python3 scripts/cost-collector.py                # Collect today's snapshot
  python3 scripts/cost-collector.py --days 7       # Backfill last 7 days
  python3 scripts/cost-collector.py --report        # Print current month summary
  python3 scripts/cost-collector.py --report --days 30  # Print last 30 days
"""

from __future__ import annotations

import argparse
import json
import os
import re
import subprocess
import sys
from datetime import datetime, timedelta, timezone
from typing import Any

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from ceo_agent_lib import get_client, now_aest, retry_cosmos_read, to_jsonable

AEST = timezone(timedelta(hours=10))

# ---------------------------------------------------------------------------
# Fixed monthly costs (AUD estimates — update when plans change)
# ---------------------------------------------------------------------------
FIXED_MONTHLY_COSTS = {
    "google_cloud_vm": {
        "label": "GCP e2-medium (fields-orchestrator-vm)",
        "monthly_aud": 38.00,  # ~$25 USD ≈ $38 AUD
        "category": "infrastructure",
    },
    "google_cloud_vm_scraper": {
        "label": "GCP e2-medium (property-scraper-vm / Codex)",
        "monthly_aud": 38.00,
        "category": "infrastructure",
    },
    "netlify_pro": {
        "label": "Netlify Pro plan",
        "monthly_aud": 29.00,  # $19 USD ≈ $29 AUD
        "category": "infrastructure",
    },
    "azure_cosmos_db": {
        "label": "Azure Cosmos DB Serverless",
        "monthly_aud": 15.00,  # Estimate — serverless with low RU
        "category": "infrastructure",
    },
    "azure_blob_storage": {
        "label": "Azure Blob Storage (property images)",
        "monthly_aud": 8.00,  # ~5GB stored, low egress
        "category": "infrastructure",
    },
    "domain_registration": {
        "label": "fieldsestate.com.au domain",
        "monthly_aud": 3.00,  # ~$36/year
        "category": "infrastructure",
    },
    "openai_api": {
        "label": "OpenAI API (GPT-4 Vision for enrichment)",
        "monthly_aud": 25.00,  # Estimate — depends on pipeline runs
        "category": "ai_compute",
    },
}

# Codex pricing (USD per million tokens, approximate for gpt-5.4/codex)
CODEX_INPUT_COST_PER_M = 2.00   # USD per 1M input tokens
CODEX_OUTPUT_COST_PER_M = 8.00  # USD per 1M output tokens
USD_TO_AUD = 1.53  # Approximate exchange rate


def daily_fixed_cost(key: str) -> float:
    """Return the daily portion of a fixed monthly cost."""
    return round(FIXED_MONTHLY_COSTS[key]["monthly_aud"] / 30.0, 2)


def get_fb_spend(sm, date_str: str) -> dict[str, Any]:
    """Get Facebook Ads spend for a given date."""
    rows = list(retry_cosmos_read(
        lambda: sm["ad_daily_metrics"].find(
            {"date": date_str, "spend_aud": {"$exists": True}},
            {"_id": 0, "ad_id": 1, "ad_name": 1, "spend_aud": 1, "impressions": 1, "link_clicks": 1}
        )
    ))
    total_spend = sum(float(r.get("spend_aud", 0) or 0) for r in rows)
    return {
        "platform": "facebook_ads",
        "category": "advertising",
        "spend_aud": round(total_spend, 2),
        "ad_count": len(rows),
        "top_spenders": sorted(
            [{"ad_name": r.get("ad_name", ""), "spend_aud": float(r.get("spend_aud", 0) or 0)} for r in rows],
            key=lambda x: -x["spend_aud"]
        )[:5],
    }


def get_google_ads_spend(sm, date_str: str) -> dict[str, Any]:
    """Get Google Ads spend for a given date."""
    rows = list(retry_cosmos_read(
        lambda: sm["google_ads_daily_metrics"].find(
            {"date": date_str},
            {"_id": 0, "campaign_id": 1, "campaign_name": 1, "cost": 1, "impressions": 1, "clicks": 1}
        )
    ))
    # Google Ads cost is in AUD (account currency)
    total_cost = sum(float(r.get("cost", 0) or 0) for r in rows)
    return {
        "platform": "google_ads",
        "category": "advertising",
        "spend_aud": round(total_cost, 2),
        "campaign_count": len(rows),
        "campaigns": [
            {"campaign_name": r.get("campaign_name", ""), "cost_aud": float(r.get("cost", 0) or 0)}
            for r in rows
        ],
    }


def get_codex_cost(sm, date_str: str) -> dict[str, Any]:
    """Get Codex/CEO agent token costs for a given date."""
    runs = list(retry_cosmos_read(
        lambda: sm["ceo_runs"].find(
            {"date": date_str},
            {"_id": 0, "agent_results": 1, "run_id": 1}
        )
    ))

    total_tokens = 0
    agent_breakdown = {}

    for run in runs:
        results = run.get("agent_results", {})
        for agent_id, data in results.items():
            tail = data.get("stdout_tail", "")
            # Parse "tokens used\n123,456" pattern from Codex output
            tokens = _parse_tokens(tail)
            if tokens > 0:
                total_tokens += tokens
                agent_breakdown[agent_id] = agent_breakdown.get(agent_id, 0) + tokens

    # Estimate cost — assume ~80% input, 20% output token split
    input_tokens = total_tokens * 0.8
    output_tokens = total_tokens * 0.2
    cost_usd = (input_tokens / 1_000_000 * CODEX_INPUT_COST_PER_M +
                output_tokens / 1_000_000 * CODEX_OUTPUT_COST_PER_M)
    cost_aud = round(cost_usd * USD_TO_AUD, 2)

    return {
        "platform": "codex_agents",
        "category": "ai_compute",
        "spend_aud": cost_aud,
        "total_tokens": total_tokens,
        "runs": len(runs),
        "agent_breakdown": {k: v for k, v in sorted(agent_breakdown.items(), key=lambda x: -x[1])},
    }


def _parse_tokens(text: str | list) -> int:
    """Extract token count from Codex stdout tail."""
    if not text:
        return 0
    if isinstance(text, list):
        text = "\n".join(str(line) for line in text)
    # Match patterns like "tokens used\n752,656" or "tokens used\n119,496"
    match = re.search(r"tokens\s+used\s*\n?\s*([\d,]+)", text, re.IGNORECASE)
    if match:
        return int(match.group(1).replace(",", ""))
    return 0


def get_netlify_builds(date_str: str) -> dict[str, Any]:
    """Count Netlify builds for a given date."""
    token = os.environ.get("NETLIFY_AUTH_TOKEN", "")
    if not token:
        return {"platform": "netlify", "category": "infrastructure", "builds": 0, "note": "no auth token"}

    try:
        result = subprocess.run(
            ["curl", "-s", "-H", f"Authorization: Bearer {token}",
             f"https://api.netlify.com/api/v1/sites/43e4ad42-a75a-4dc7-be22-67fcda0ec98b/deploys?per_page=100"],
            capture_output=True, text=True, timeout=30
        )
        deploys = json.loads(result.stdout)
        if not isinstance(deploys, list):
            return {"platform": "netlify", "category": "infrastructure", "builds": 0, "note": "api error"}

        day_builds = [d for d in deploys if d.get("created_at", "").startswith(date_str)]
        return {
            "platform": "netlify",
            "category": "infrastructure",
            "builds": len(day_builds),
            "build_minutes_est": len(day_builds) * 2,  # ~2 min average build
        }
    except Exception as e:
        return {"platform": "netlify", "category": "infrastructure", "builds": 0, "note": str(e)}


def collect_daily_snapshot(sm, date_str: str) -> dict[str, Any]:
    """Collect all costs for a single date and return unified snapshot."""
    fb = get_fb_spend(sm, date_str)
    google = get_google_ads_spend(sm, date_str)
    codex = get_codex_cost(sm, date_str)
    netlify = get_netlify_builds(date_str)

    # Fixed daily costs
    fixed = {}
    fixed_total = 0.0
    for key, info in FIXED_MONTHLY_COSTS.items():
        daily = daily_fixed_cost(key)
        fixed[key] = {
            "label": info["label"],
            "category": info["category"],
            "daily_aud": daily,
        }
        fixed_total += daily

    # Totals by category
    ad_spend = fb["spend_aud"] + google["spend_aud"]
    ai_compute = codex["spend_aud"] + daily_fixed_cost("openai_api")
    infrastructure = sum(
        daily_fixed_cost(k) for k in FIXED_MONTHLY_COSTS
        if FIXED_MONTHLY_COSTS[k]["category"] == "infrastructure"
    )

    total_daily = ad_spend + ai_compute + infrastructure

    snapshot = {
        "date": date_str,
        "total_daily_aud": round(total_daily, 2),
        "by_category": {
            "advertising": round(ad_spend, 2),
            "ai_compute": round(ai_compute, 2),
            "infrastructure": round(infrastructure, 2),
        },
        "platforms": {
            "facebook_ads": fb,
            "google_ads": google,
            "codex_agents": codex,
            "netlify": netlify,
        },
        "fixed_costs": fixed,
        "projected_monthly_aud": round(total_daily * 30, 2),
        "collected_at": now_aest().isoformat(),
    }
    return snapshot


def store_snapshot(sm, snapshot: dict[str, Any]) -> None:
    """Upsert daily snapshot to MongoDB."""
    retry_cosmos_read(lambda: sm["cost_tracking"].update_one(
        {"date": snapshot["date"]},
        {"$set": to_jsonable(snapshot)},
        upsert=True,
    ))
    print(f"  ✓ {snapshot['date']}: ${snapshot['total_daily_aud']:.2f}/day "
          f"(ads: ${snapshot['by_category']['advertising']:.2f}, "
          f"ai: ${snapshot['by_category']['ai_compute']:.2f}, "
          f"infra: ${snapshot['by_category']['infrastructure']:.2f})")


def print_report(sm, days: int) -> None:
    """Print a cost summary report."""
    cutoff = (now_aest() - timedelta(days=days)).strftime("%Y-%m-%d")
    rows = list(retry_cosmos_read(
        lambda: sm["cost_tracking"].find(
            {"date": {"$gte": cutoff}},
            {"_id": 0}
        )
    ))
    rows.sort(key=lambda r: r.get("date", ""))

    if not rows:
        print(f"No cost data found for last {days} days. Run without --report first.")
        return

    print(f"\n{'='*60}")
    print(f" COST REPORT — Last {days} days ({cutoff} → {now_aest().strftime('%Y-%m-%d')})")
    print(f"{'='*60}\n")

    total = 0
    cat_totals = {"advertising": 0, "ai_compute": 0, "infrastructure": 0}
    fb_total = 0
    google_total = 0
    codex_total = 0
    codex_tokens = 0

    for row in rows:
        total += row.get("total_daily_aud", 0)
        for cat, val in row.get("by_category", {}).items():
            cat_totals[cat] = cat_totals.get(cat, 0) + val
        fb_total += row.get("platforms", {}).get("facebook_ads", {}).get("spend_aud", 0)
        google_total += row.get("platforms", {}).get("google_ads", {}).get("spend_aud", 0)
        codex_total += row.get("platforms", {}).get("codex_agents", {}).get("spend_aud", 0)
        codex_tokens += row.get("platforms", {}).get("codex_agents", {}).get("total_tokens", 0)

    print(f"  Total spend:         ${total:>8.2f} AUD")
    print(f"  Daily average:       ${total / len(rows):>8.2f} AUD")
    print(f"  Projected monthly:   ${total / len(rows) * 30:>8.2f} AUD")
    print()
    print("  By category:")
    for cat, val in sorted(cat_totals.items(), key=lambda x: -x[1]):
        pct = (val / total * 100) if total else 0
        print(f"    {cat:<20s} ${val:>8.2f}  ({pct:>4.1f}%)")
    print()
    print("  Platform breakdown:")
    print(f"    Facebook Ads:      ${fb_total:>8.2f}")
    print(f"    Google Ads:        ${google_total:>8.2f}")
    print(f"    Codex agents:      ${codex_total:>8.2f}  ({codex_tokens:,} tokens)")
    infra = cat_totals.get("infrastructure", 0)
    print(f"    Infrastructure:    ${infra:>8.2f}  (fixed)")
    print()

    # Daily trend
    print("  Daily trend:")
    for row in rows[-14:]:  # Last 14 days
        d = row["date"]
        t = row.get("total_daily_aud", 0)
        ad = row.get("by_category", {}).get("advertising", 0)
        bar = "█" * int(t / 2) if t > 0 else "▏"
        print(f"    {d}  ${t:>6.2f}  (ads ${ad:>5.2f})  {bar}")

    print(f"\n{'='*60}\n")


def main() -> None:
    parser = argparse.ArgumentParser(description="Collect and report on platform costs")
    parser.add_argument("--days", type=int, default=1, help="Days to collect/report (default: 1 = today only)")
    parser.add_argument("--report", action="store_true", help="Print cost summary instead of collecting")
    args = parser.parse_args()

    client = get_client()
    sm = client["system_monitor"]

    if args.report:
        print_report(sm, args.days)
        client.close()
        return

    today = now_aest()
    print(f"📊 Cost collector — collecting {args.days} day(s)")

    for i in range(args.days - 1, -1, -1):
        date_str = (today - timedelta(days=i)).strftime("%Y-%m-%d")
        snapshot = collect_daily_snapshot(sm, date_str)
        store_snapshot(sm, snapshot)

    client.close()
    print("\n✅ Done")


if __name__ == "__main__":
    main()
