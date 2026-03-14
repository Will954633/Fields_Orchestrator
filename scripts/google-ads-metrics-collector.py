#!/usr/bin/env python3
"""
Google Ads Metrics Collector — Daily performance tracking to MongoDB.

Mirrors the structure of fb-metrics-collector.py but for Google Ads.
Collects per-campaign and per-ad-group daily metrics, keyword performance,
and conversion data, storing everything in system_monitor collections.

Collections written:
  - google_ads_daily_metrics  : one doc per campaign per day (90-day retention)
  - google_ads_profiles       : one doc per campaign (config, aggregates, status)
  - google_ads_keywords       : keyword performance per 7d window
  - google_ads               : backward-compatible "latest" snapshot

Usage:
    python3 scripts/google-ads-metrics-collector.py            # Full collection
    python3 scripts/google-ads-metrics-collector.py --quick    # Skip keywords
    python3 scripts/google-ads-metrics-collector.py --print    # Print without saving
"""

import os
import sys
import argparse
import traceback
from datetime import datetime, timezone, timedelta
from dotenv import load_dotenv
from pymongo import MongoClient, UpdateOne
from google.ads.googleads.client import GoogleAdsClient

load_dotenv("/home/fields/Fields_Orchestrator/.env")

COSMOS_URI = os.environ["COSMOS_CONNECTION_STRING"]
RETENTION_DAYS = 90

def get_google_client():
    credentials = {
        "developer_token": os.environ["GOOGLE_ADS_DEVELOPER_TOKEN"],
        "client_id": os.environ["GOOGLE_ADS_CLIENT_ID"],
        "client_secret": os.environ["GOOGLE_ADS_CLIENT_SECRET"],
        "refresh_token": os.environ["GOOGLE_ADS_REFRESH_TOKEN"],
        "login_customer_id": os.environ["GOOGLE_ADS_MCC_ID"],
        "use_proto_plus": True,
    }
    return GoogleAdsClient.load_from_dict(credentials)

def micros_to_aud(micros):
    return micros / 1_000_000

# ---------------------------------------------------------------------------
# Campaign profiles + daily metrics
# ---------------------------------------------------------------------------

def collect_campaign_data(client, customer_id, days=7):
    """Collect campaign-level daily metrics for the last N days."""
    ga_service = client.get_service("GoogleAdsService")
    start = (datetime.now() - timedelta(days=days)).strftime("%Y-%m-%d")
    end = datetime.now().strftime("%Y-%m-%d")

    # Daily metrics per campaign
    query = f"""
        SELECT
            campaign.id,
            campaign.name,
            campaign.status,
            campaign.advertising_channel_type,
            campaign_budget.amount_micros,
            segments.date,
            metrics.impressions,
            metrics.clicks,
            metrics.ctr,
            metrics.average_cpc,
            metrics.cost_micros,
            metrics.conversions,
            metrics.conversions_value
        FROM campaign
        WHERE segments.date BETWEEN '{start}' AND '{end}'
          AND campaign.status != 'REMOVED'
        ORDER BY segments.date DESC
    """
    response = ga_service.search_stream(customer_id=customer_id, query=query)

    daily_metrics = []
    campaign_profiles = {}

    for batch in response:
        for row in batch.results:
            c = row.campaign
            m = row.metrics
            date_str = row.segments.date
            cost = micros_to_aud(m.cost_micros)
            avg_cpc = micros_to_aud(m.average_cpc) if m.average_cpc else 0
            budget = micros_to_aud(row.campaign_budget.amount_micros) if row.campaign_budget.amount_micros else 0

            daily_metrics.append({
                "campaign_id": str(c.id),
                "campaign_name": c.name,
                "date": date_str,
                "impressions": m.impressions,
                "clicks": m.clicks,
                "ctr": round(m.ctr * 100, 2) if m.ctr else 0,
                "avg_cpc": round(avg_cpc, 2),
                "cost": round(cost, 2),
                "conversions": round(m.conversions, 1),
                "conversion_value": round(m.conversions_value, 2),
                "collected_at": datetime.now(timezone.utc).isoformat(),
            })

            # Build/update profile
            cid = str(c.id)
            if cid not in campaign_profiles:
                campaign_profiles[cid] = {
                    "campaign_id": cid,
                    "campaign_name": c.name,
                    "status": c.status.name,
                    "channel_type": c.advertising_channel_type.name,
                    "daily_budget": round(budget, 2),
                    "total_impressions": 0,
                    "total_clicks": 0,
                    "total_cost": 0,
                    "total_conversions": 0,
                    "last_updated": datetime.now(timezone.utc).isoformat(),
                }
            p = campaign_profiles[cid]
            p["total_impressions"] += m.impressions
            p["total_clicks"] += m.clicks
            p["total_cost"] += cost
            p["total_conversions"] += m.conversions

    # Round aggregates
    for p in campaign_profiles.values():
        p["total_cost"] = round(p["total_cost"], 2)
        p["total_conversions"] = round(p["total_conversions"], 1)
        if p["total_impressions"] > 0:
            p["overall_ctr"] = round(p["total_clicks"] / p["total_impressions"] * 100, 2)
        else:
            p["overall_ctr"] = 0

    return daily_metrics, campaign_profiles


# ---------------------------------------------------------------------------
# Keyword performance
# ---------------------------------------------------------------------------

def collect_keyword_data(client, customer_id, days=7):
    """Collect keyword-level metrics for the last N days."""
    ga_service = client.get_service("GoogleAdsService")
    start = (datetime.now() - timedelta(days=days)).strftime("%Y-%m-%d")
    end = datetime.now().strftime("%Y-%m-%d")

    query = f"""
        SELECT
            campaign.name,
            ad_group.name,
            ad_group_criterion.keyword.text,
            ad_group_criterion.keyword.match_type,
            metrics.impressions,
            metrics.clicks,
            metrics.ctr,
            metrics.average_cpc,
            metrics.cost_micros,
            metrics.conversions
        FROM keyword_view
        WHERE segments.date BETWEEN '{start}' AND '{end}'
        ORDER BY metrics.impressions DESC
        LIMIT 100
    """
    response = ga_service.search_stream(customer_id=customer_id, query=query)

    keywords = []
    for batch in response:
        for row in batch.results:
            m = row.metrics
            keywords.append({
                "campaign_name": row.campaign.name,
                "ad_group_name": row.ad_group.name,
                "keyword": row.ad_group_criterion.keyword.text,
                "match_type": row.ad_group_criterion.keyword.match_type.name,
                "impressions": m.impressions,
                "clicks": m.clicks,
                "ctr": round(m.ctr * 100, 2) if m.ctr else 0,
                "avg_cpc": round(micros_to_aud(m.average_cpc), 2) if m.average_cpc else 0,
                "cost": round(micros_to_aud(m.cost_micros), 2),
                "conversions": round(m.conversions, 1),
                "period_start": start,
                "period_end": end,
                "collected_at": datetime.now(timezone.utc).isoformat(),
            })

    return keywords


# ---------------------------------------------------------------------------
# Conversion action performance
# ---------------------------------------------------------------------------

def collect_conversion_data(client, customer_id, days=7):
    """Collect conversion data from campaign metrics (segments.conversion_action_name)."""
    ga_service = client.get_service("GoogleAdsService")
    start = (datetime.now() - timedelta(days=days)).strftime("%Y-%m-%d")
    end = datetime.now().strftime("%Y-%m-%d")

    query = f"""
        SELECT
            campaign.name,
            segments.conversion_action_name,
            segments.date,
            metrics.conversions,
            metrics.conversions_value
        FROM campaign
        WHERE segments.date BETWEEN '{start}' AND '{end}'
          AND metrics.conversions > 0
    """
    try:
        response = ga_service.search_stream(customer_id=customer_id, query=query)
        conversions = []
        for batch in response:
            for row in batch.results:
                m = row.metrics
                conversions.append({
                    "campaign_name": row.campaign.name,
                    "conversion_name": row.segments.conversion_action_name,
                    "date": row.segments.date,
                    "conversions": round(m.conversions, 1),
                    "value": round(m.conversions_value, 2),
                })
        return conversions
    except Exception:
        return []


# ---------------------------------------------------------------------------
# Save to MongoDB
# ---------------------------------------------------------------------------

def save_to_mongodb(daily_metrics, profiles, keywords, conversions, dry_run=False):
    """Write all collected data to system_monitor collections."""
    if dry_run:
        print(f"  [DRY RUN] Would write {len(daily_metrics)} daily metrics")
        print(f"  [DRY RUN] Would update {len(profiles)} campaign profiles")
        print(f"  [DRY RUN] Would write {len(keywords)} keyword records")
        print(f"  [DRY RUN] Would write {len(conversions)} conversion records")
        return

    client = MongoClient(COSMOS_URI)
    db = client["system_monitor"]

    # 1. Daily metrics (upsert by campaign_id + date)
    if daily_metrics:
        ops = []
        for m in daily_metrics:
            ops.append(UpdateOne(
                {"campaign_id": m["campaign_id"], "date": m["date"]},
                {"$set": m},
                upsert=True,
            ))
        result = db["google_ads_daily_metrics"].bulk_write(ops, ordered=False)
        print(f"  Daily metrics: {result.upserted_count} new, {result.modified_count} updated")

    # 2. Campaign profiles (upsert by campaign_id)
    if profiles:
        ops = []
        for cid, p in profiles.items():
            ops.append(UpdateOne(
                {"campaign_id": cid},
                {"$set": p},
                upsert=True,
            ))
        result = db["google_ads_profiles"].bulk_write(ops, ordered=False)
        print(f"  Profiles: {result.upserted_count} new, {result.modified_count} updated")

    # 3. Keywords (upsert by keyword + campaign + period to avoid duplicates)
    if keywords:
        import time as _time
        ops = []
        for k in keywords:
            ops.append(UpdateOne(
                {"keyword": k["keyword"], "campaign_name": k["campaign_name"],
                 "match_type": k["match_type"], "period_start": k["period_start"]},
                {"$set": k},
                upsert=True,
            ))
        # Batch in chunks of 20 to avoid Cosmos 429s
        written = 0
        for i in range(0, len(ops), 20):
            batch = ops[i:i+20]
            try:
                db["google_ads_keywords"].bulk_write(batch, ordered=False)
                written += len(batch)
            except Exception as e:
                if "16500" in str(e):
                    _time.sleep(2)
                    db["google_ads_keywords"].bulk_write(batch, ordered=False)
                    written += len(batch)
                else:
                    raise
            _time.sleep(0.3)
        print(f"  Keywords: {written} records written")

    # 4. Latest snapshot (backward-compatible)
    snapshot = {
        "collected_at": datetime.now(timezone.utc).isoformat(),
        "campaigns": list(profiles.values()),
        "total_campaigns": len(profiles),
        "total_cost_7d": round(sum(p["total_cost"] for p in profiles.values()), 2),
        "total_impressions_7d": sum(p["total_impressions"] for p in profiles.values()),
        "total_clicks_7d": sum(p["total_clicks"] for p in profiles.values()),
        "total_conversions_7d": round(sum(p["total_conversions"] for p in profiles.values()), 1),
        "conversion_records": conversions,
    }
    db["google_ads"].replace_one({"_id": "latest"}, {**snapshot, "_id": "latest"}, upsert=True)
    print(f"  Latest snapshot saved")

    # 5. Retention cleanup
    cutoff = (datetime.now(timezone.utc) - timedelta(days=RETENTION_DAYS)).isoformat()
    deleted = db["google_ads_daily_metrics"].delete_many({"collected_at": {"$lt": cutoff}})
    if deleted.deleted_count:
        print(f"  Cleaned up {deleted.deleted_count} records older than {RETENTION_DAYS} days")

    client.close()


# ---------------------------------------------------------------------------
# Print summary
# ---------------------------------------------------------------------------

def print_summary(daily_metrics, profiles, keywords, conversions):
    """Print a human-readable summary."""
    print(f"\n{'='*60}")
    print(f"GOOGLE ADS METRICS COLLECTION SUMMARY")
    print(f"{'='*60}")
    print(f"Campaigns: {len(profiles)}")
    print(f"Daily metric records: {len(daily_metrics)}")

    total_cost = sum(p["total_cost"] for p in profiles.values())
    total_impr = sum(p["total_impressions"] for p in profiles.values())
    total_clicks = sum(p["total_clicks"] for p in profiles.values())
    total_conv = sum(p["total_conversions"] for p in profiles.values())

    print(f"\n7-day totals:")
    print(f"  Spend: ${total_cost:.2f}")
    print(f"  Impressions: {total_impr:,}")
    print(f"  Clicks: {total_clicks:,}")
    print(f"  Conversions: {total_conv:.1f}")
    if total_impr > 0:
        print(f"  CTR: {total_clicks/total_impr*100:.2f}%")

    print(f"\nPer campaign:")
    for p in sorted(profiles.values(), key=lambda x: x["total_cost"], reverse=True):
        print(f"  {p['campaign_name'][:40]:<40} {p['status']:<8} ${p['total_cost']:>7.2f}  {p['total_impressions']:>5} impr  {p['total_clicks']:>3} clicks  {p['total_conversions']:>4.1f} conv")

    if keywords:
        print(f"\nTop keywords ({len(keywords)} total):")
        for k in keywords[:10]:
            print(f"  {k['keyword'][:35]:<35} {k['match_type']:<8} {k['impressions']:>5} impr  {k['clicks']:>3} clicks  ${k['cost']:>5.2f}")

    if conversions:
        print(f"\nConversions:")
        for c in conversions:
            print(f"  {c['conversion_name']}: {c['conversions']} on {c['date']} (${c['value']:.2f} value)")


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main():
    parser = argparse.ArgumentParser(description="Google Ads Metrics Collector")
    parser.add_argument("--quick", action="store_true", help="Skip keyword collection")
    parser.add_argument("--print", dest="print_only", action="store_true", help="Print without saving")
    parser.add_argument("--dry-run", action="store_true", help="Show what would be collected")
    parser.add_argument("--days", type=int, default=7, help="Days of data to collect")
    args = parser.parse_args()

    print(f"Google Ads Metrics Collector — {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print(f"Collecting {args.days} days of data...")

    try:
        client = get_google_client()
        customer_id = os.environ["GOOGLE_ADS_CUSTOMER_ID"]

        # Collect campaign data
        print("\nCollecting campaign metrics...")
        daily_metrics, profiles = collect_campaign_data(client, customer_id, days=args.days)
        print(f"  Found {len(profiles)} campaigns, {len(daily_metrics)} daily records")

        # Collect keywords (unless --quick)
        keywords = []
        if not args.quick:
            print("Collecting keyword performance...")
            keywords = collect_keyword_data(client, customer_id, days=args.days)
            print(f"  Found {len(keywords)} keyword records")

        # Collect conversions
        print("Collecting conversion data...")
        conversions = collect_conversion_data(client, customer_id, days=args.days)
        print(f"  Found {len(conversions)} conversion records")

        # Print summary
        print_summary(daily_metrics, profiles, keywords, conversions)

        # Save
        if not args.print_only:
            print("\nSaving to MongoDB...")
            save_to_mongodb(daily_metrics, profiles, keywords, conversions, dry_run=args.dry_run)
            print("Done.")
        else:
            print("\n[PRINT ONLY — nothing saved]")

    except Exception as e:
        print(f"\nERROR: {e}")
        traceback.print_exc()
        sys.exit(1)


if __name__ == "__main__":
    main()
