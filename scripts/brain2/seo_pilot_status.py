#!/usr/bin/env python3
"""
seo_pilot_status.py — weekly status of the SEO sold-page demand-engine pilot.

Answers: are the ~1,594 property pages (1,371 sold) we put in the sitemap on
2026-07-16 actually getting indexed + pulling organic search traffic, and is that
turning into inbound address entries (esp. neighbour_sale_trigger)?

Sources (all in-house):
  - live sitemap (curl)                     -> property-page count actually served
  - system_monitor.seo_landing_performance  -> GSC/Bing per-page,query rows (nightly)
  - system_monitor.all_conversions          -> all-channel address entries (nightly)
  - system_monitor.organic_landing_affinity -> which entry pages get organic sessions
Persists a weekly snapshot to system_monitor.seo_pilot_weekly so trends survive and
deltas can be shown. Prints a Markdown summary; --telegram sends it to Will.

Usage:
  python3 scripts/brain2/seo_pilot_status.py            # print only
  python3 scripts/brain2/seo_pilot_status.py --telegram # print + send + snapshot
  python3 scripts/brain2/seo_pilot_status.py --no-snapshot
"""
import sys, argparse, urllib.request
from collections import Counter
from datetime import datetime, timezone, timedelta

sys.path.insert(0, "/home/fields/Fields_Orchestrator")
from dotenv import load_dotenv
load_dotenv("/home/fields/Fields_Orchestrator/.env")
from shared.db import get_client  # noqa: E402

SITEMAP_URL = "https://fieldsestate.com.au/sitemap.xml"


def live_sitemap_counts():
    try:
        req = urllib.request.Request(SITEMAP_URL, headers={"User-Agent": "fields-seo-pilot"})
        xml = urllib.request.urlopen(req, timeout=30).read().decode("utf-8", "ignore")
        total = xml.count("<loc>")
        prop = xml.count("/property/")
        return total, prop
    except Exception as e:
        return None, f"error: {e}"


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--telegram", action="store_true", help="send summary to Will via Telegram")
    ap.add_argument("--no-snapshot", action="store_true", help="do not persist a weekly snapshot")
    args = ap.parse_args()

    db = get_client()["system_monitor"]
    now = datetime.now(timezone.utc)
    since7 = (now - timedelta(days=7)).isoformat()

    # 1) live sitemap
    sm_total, sm_prop = live_sitemap_counts()

    # 2) GSC/Bing search performance (from nightly seo_landing_performance)
    rows = list(db.seo_landing_performance.find({}))
    prop_rows = [r for r in rows if "/property/" in (r.get("page") or "")]
    prop_pages = {r.get("page") for r in prop_rows}
    prop_impr = sum(r.get("impressions") or 0 for r in prop_rows)
    prop_clk = sum(r.get("clicks") or 0 for r in prop_rows)
    all_impr = sum(r.get("impressions") or 0 for r in rows)
    all_clk = sum(r.get("clicks") or 0 for r in rows)
    # top property queries by impressions
    q = Counter()
    for r in prop_rows:
        if r.get("query"):
            q[r["query"]] += r.get("impressions") or 0
    top_prop_q = q.most_common(5)

    # 3) organic address entries (all-channel register), last 7d + all-time retained
    conv = list(db.all_conversions.find({}))
    conv7 = [c for c in conv if (c.get("submitted_at") or "") >= since7]
    neigh = [c for c in conv if c.get("pattern") == "neighbour_sale_trigger"]
    organic = [c for c in conv if "Organic" in (c.get("channel") or "")]

    # 4) property entry-pages getting organic sessions
    aff = list(db.organic_landing_affinity.find({"_id": {"$regex": "/property/"}}))
    prop_entry_sessions = sum(a.get("sessions") or 0 for a in aff)

    # previous snapshot for deltas
    prev = db.seo_pilot_weekly.find_one(sort=[("date", -1)])

    def delta(cur, key):
        if not prev or prev.get(key) is None:
            return ""
        d = cur - prev[key]
        return f" ({'+' if d >= 0 else ''}{d} vs last wk)"

    snap = {
        "date": now.date().isoformat(),
        "computed_at": now.isoformat(),
        "sitemap_total": sm_total,
        "sitemap_property": sm_prop if isinstance(sm_prop, int) else None,
        "gsc_property_pages_served": len(prop_pages),
        "gsc_property_impressions": prop_impr,
        "gsc_property_clicks": prop_clk,
        "gsc_all_impressions": all_impr,
        "gsc_all_clicks": all_clk,
        "organic_property_entry_sessions": prop_entry_sessions,
        "conversions_7d": len(conv7),
        "conversions_retained_total": len(conv),
        "neighbour_triggers_total": len(neigh),
    }

    # build report
    L = []
    L.append("📈 *SEO Pilot — weekly check* (sold-page demand engine)")
    L.append(f"_{snap['date']} · pilot live since 2026-07-16_")
    L.append("")
    L.append("*Sitemap (live)*")
    L.append(f"• {sm_total} URLs · {sm_prop} property pages"
             f"{delta(sm_prop, 'sitemap_property') if isinstance(sm_prop,int) else ''}")
    L.append("")
    L.append("*Search performance (GSC/Bing)*")
    L.append(f"• Property pages appearing in search: *{len(prop_pages)}*"
             f"{delta(len(prop_pages),'gsc_property_pages_served')}  ← indexation proxy (of ~1,594)")
    L.append(f"• Property impressions: {prop_impr}{delta(prop_impr,'gsc_property_impressions')} · "
             f"clicks: {prop_clk}{delta(prop_clk,'gsc_property_clicks')}")
    L.append(f"• Whole site: {all_impr} impressions · {all_clk} clicks")
    if top_prop_q:
        L.append("• Top property queries: " + "; ".join(f"“{k}” ({v})" for k, v in top_prop_q))
    L.append("")
    L.append("*Inbound address entries (all channels)*")
    L.append(f"• Last 7d: *{len(conv7)}* · retained total: {len(conv)} · "
             f"neighbour-sale-triggers: {len(neigh)}")
    L.append(f"• Organic /property entry sessions: {prop_entry_sessions}"
             f"{delta(prop_entry_sessions,'organic_property_entry_sessions')}")
    L.append("")
    L.append("*Prompt Claude on the VM to review:*")
    L.append("• Is the indexation proxy climbing? If healthy → widen `SOLD_MAX_AGE_MONTHS`; "
             "if flat/throttled → hold + strengthen internal linking")
    L.append("• Any new organic conversions / neighbour-triggers → warm that prospect (posted report / on-site)")
    L.append("• Verdict: hold · widen · move to Phase 2 (your-home pages) · or start #4 ad prospecting")
    report = "\n".join(L)
    print(report)

    if not args.no_snapshot:
        db.seo_pilot_weekly.insert_one(snap)
        print("\n[snapshot saved to system_monitor.seo_pilot_weekly]", file=sys.stderr)

    if args.telegram:
        sys.path.insert(0, "/home/fields/Fields_Orchestrator/scripts")
        import telegram_notify
        telegram_notify.send_message(report)
        print("[sent to Telegram]", file=sys.stderr)


if __name__ == "__main__":
    main()
