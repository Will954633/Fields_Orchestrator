#!/usr/bin/env python3
"""
ad-flow-report.py — Full user-flow attribution for a Facebook ad or campaign.

Traces every session driven by an ad and reconstructs the complete page-by-page
journey from PostHog, then reports conversions (analyse-your-home address entries).
This is the Brain 2 (in-house data) attribution tool.

Attribution key: FB dynamic url_tags stamp utm_content={{ad.id}} on every click, so
each session is tied to the EXACT ad. (Older ads only tagged utm_campaign — use
--campaign or --landing for those.)

Usage:
  python3 scripts/ad-flow-report.py --ad-id 120244615219210134 --days 30
  python3 scripts/ad-flow-report.py --campaign "Watch this sale" --days 60
  python3 scripts/ad-flow-report.py --landing /for-sale-v3 --days 30 --detail 15

Env: POSTHOG_PROJECT_ID, POSTHOG_PERSONAL_API_KEY (in .env)
"""
import os, sys, json, argparse, urllib.request
from collections import Counter, defaultdict

PID = os.environ["POSTHOG_PROJECT_ID"]
KEY = os.environ["POSTHOG_PERSONAL_API_KEY"]
HOST = "us.posthog.com"

# Events that mean "user engaged the analyse-your-home valuation flow" (a conversion)
CONV_EVENTS = [
    "analyse_home_submit_start", "analyse_home_submit_success",
    "analyse_v3_address_selected", "analyse_v2_address_selected",
    "analyse_v3_jobs_queued", "analyse_v3_analysis_complete",
]


def hog(sql):
    url = f"https://{HOST}/api/projects/{PID}/query/"
    body = json.dumps({"query": {"kind": "HogQLQuery", "query": sql}}).encode()
    req = urllib.request.Request(
        url, data=body,
        headers={"Authorization": f"Bearer {KEY}", "Content-Type": "application/json"},
    )
    return json.loads(urllib.request.urlopen(req, timeout=90).read())


def main():
    ap = argparse.ArgumentParser(description="Full user-flow attribution per FB ad/campaign.")
    g = ap.add_mutually_exclusive_group(required=True)
    g.add_argument("--ad-id", help="FB ad id (matches utm_content stamped by dynamic url_tags)")
    g.add_argument("--campaign", help="Match utm_campaign (substring, case-insensitive)")
    g.add_argument("--landing", help="Match sessions that hit this pathname, e.g. /for-sale-v3")
    ap.add_argument("--days", type=int, default=30, help="Look-back window (default 30)")
    ap.add_argument("--detail", type=int, default=10, help="How many individual session flows to print")
    args = ap.parse_args()

    since = f"now() - INTERVAL {args.days} DAY"
    if args.ad_id:
        filt = f"properties.utm_content = '{args.ad_id}'"; label = f"ad_id={args.ad_id}"
    elif args.campaign:
        c = args.campaign.replace("'", "\\'")
        filt = f"properties.utm_campaign ILIKE '%{c}%'"; label = f"campaign~'{args.campaign}'"
    else:
        p = args.landing.replace("'", "\\'")
        filt = f"properties.$pathname = '{p}'"; label = f"landing={args.landing}"

    # 1) sessions matching the attribution filter
    sess_sql = f"""SELECT DISTINCT properties.$session_id FROM events
        WHERE {filt} AND timestamp > {since} AND properties.$session_id IS NOT NULL"""
    sids = [r[0] for r in hog(sess_sql)["results"] if r[0]]
    if not sids:
        print(f"No sessions found for {label} in the last {args.days} days."); return
    id_list = ",".join("'" + s.replace("'", "") + "'" for s in sids)

    # 2) full event stream (pageviews + conversion events) for those sessions
    ev_sql = f"""SELECT properties.$session_id, timestamp, event, properties.$pathname,
        properties.utm_campaign, properties.utm_content
        FROM events
        WHERE properties.$session_id IN ({id_list})
        AND (event = '$pageview' OR event IN ({",".join("'"+e+"'" for e in CONV_EVENTS)}))
        AND timestamp > {since}
        ORDER BY properties.$session_id, timestamp"""
    rows = hog(ev_sql)["results"]

    sessions = defaultdict(lambda: {"steps": [], "camp": None, "content": None, "converted": False})
    for sid, ts, event, path, camp, content in rows:
        s = sessions[sid]
        if camp and not s["camp"]: s["camp"] = camp
        if content and not s["content"]: s["content"] = content
        if event == "$pageview":
            s["steps"].append(("page", path or "?"))
        else:
            s["steps"].append(("CONVERT", event))
            s["converted"] = True

    total = len(sessions)
    converters = sum(1 for s in sessions.values() if s["converted"])
    entry = Counter(); before_conv = Counter(); camps = Counter()
    for s in sessions.values():
        pages = [p for k, p in s["steps"] if k == "page"]
        if pages: entry[pages[0]] += 1
        camps[s["camp"] or "(untagged)"] += 1
        # page right before first conversion
        for i, (k, v) in enumerate(s["steps"]):
            if k == "CONVERT":
                prev = next((vv for kk, vv in reversed(s["steps"][:i]) if kk == "page"), "(none)")
                before_conv[prev] += 1
                break

    print("=" * 74)
    print(f"AD FLOW REPORT — {label}  (last {args.days} days)")
    print("=" * 74)
    print(f"Sessions: {total}   Converters (address entry): {converters}   "
          f"Conversion rate: {100*converters/total:.1f}%")
    print(f"\nAttribution tags seen: {dict(camps)}")
    print("\nEntry pages:")
    for p, n in entry.most_common(8): print(f"   {n:>3}  {p}")
    if before_conv:
        print("\nPage immediately before address entry:")
        for p, n in before_conv.most_common(8): print(f"   {n:>3}  {p}")

    print(f"\nSample session flows (first {args.detail}):")
    shown = 0
    # show converters first
    for sid, s in sorted(sessions.items(), key=lambda kv: not kv[1]["converted"]):
        if shown >= args.detail: break
        flow = " > ".join(f"[{v}]" if k == "CONVERT" else v for k, v in s["steps"][:10])
        tag = "✅CONV " if s["converted"] else "       "
        print(f"  {tag}{flow[:110]}")
        shown += 1


if __name__ == "__main__":
    main()
