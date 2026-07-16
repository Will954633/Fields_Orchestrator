#!/usr/bin/env python3
"""
ad_journey.py — Brain 2: server-side funnel + path analysis via the PostHog Query API.

Instead of reconstructing funnels/paths in Python, this runs PostHog's own
FunnelsQuery and PathsQuery engines and returns the results — including per-ad
breakdown of the conversion funnel by utm_content.

Commands:
  python3 scripts/brain2/ad_journey.py funnel [--days 220]
      The analyse-your-home conversion funnel:
      landing pageview -> address submit -> submit success, broken down by ad.
  python3 scripts/brain2/ad_journey.py paths-to [--days 220]
      Common on-site journeys that END at the address-submit conversion.
  python3 scripts/brain2/ad_journey.py paths-from --start /for-sale-v3 [--days 220]
      Common journeys starting from a landing page.

Env: POSTHOG_ALL_ACCESS_KEY (or POSTHOG_PERSONAL_API_KEY), POSTHOG_PROJECT_ID
"""
import os, sys, json, argparse, urllib.request, urllib.error
from dotenv import load_dotenv

load_dotenv("/home/fields/Fields_Orchestrator/.env")
PID = os.environ["POSTHOG_PROJECT_ID"]
KEY = os.environ.get("POSTHOG_ALL_ACCESS_KEY") or os.environ["POSTHOG_PERSONAL_API_KEY"]
CONV = "analyse_home_submit_success"      # current live completion event
SUBMIT = "analyse_home_address_submit"    # address entered


def query(q):
    body = json.dumps({"query": q}).encode()
    r = urllib.request.Request(f"https://us.posthog.com/api/projects/{PID}/query/",
                               data=body, headers={"Authorization": f"Bearer {KEY}",
                                                   "Content-Type": "application/json"})
    return json.loads(urllib.request.urlopen(r, timeout=120).read())


def cmd_funnel(days):
    q = {
        "kind": "FunnelsQuery",
        "series": [
            {"kind": "EventsNode", "event": "$pageview", "name": "Landing (FB-attributed)",
             "properties": [{"key": "utm_content", "value": "^[0-9]+$",
                             "operator": "regex", "type": "event"}]},
            {"kind": "EventsNode", "event": SUBMIT, "name": "Address entered"},
            {"kind": "EventsNode", "event": CONV, "name": "Analysis completed"},
        ],
        "funnelsFilter": {"funnelVizType": "steps", "funnelOrderType": "ordered",
                          "funnelWindowInterval": 14, "funnelWindowIntervalUnit": "day"},
        "breakdownFilter": {"breakdown": "$entry_utm_content", "breakdown_type": "session"},
        "dateRange": {"date_from": f"-{days}d"},
    }
    res = query(q)["results"]
    print("=" * 60)
    print("ANALYSE-YOUR-HOME FUNNEL by ad (FB-attributed, server-side)")
    print("=" * 60)
    # results is a list-of-lists when broken down (one funnel per breakdown value)
    groups = res if res and isinstance(res[0], list) else [res]
    rows = []
    for g in groups:
        if not g:
            continue
        bd = g[0].get("breakdown_value")
        bd = bd[0] if isinstance(bd, list) else bd
        counts = [step.get("count", 0) for step in g]
        rows.append((str(bd), counts))
    rows.sort(key=lambda r: -r[1][0])
    print(f"{'ad (utm_content)':22} {'landing':>8} {'address':>8} {'complete':>8} {'L→addr':>7}")
    for bd, c in rows[:25]:
        c = c + [0] * (3 - len(c))
        rate = f"{round(100*c[1]/c[0])}%" if c[0] else "-"
        print(f"{bd[:22]:22} {c[0]:>8} {c[1]:>8} {c[2]:>8} {rate:>7}")


def cmd_paths(days, start=None, end_at_conv=False):
    pf = {"includeEventTypes": ["$pageview"], "stepLimit": 6,
          "pathReplacements": True, "edgeLimit": 40,
          "pathGroupings": ["/property/*", "/articles/*", "/article/*"]}
    if start:
        pf["startPoint"] = start
    if end_at_conv:
        pf["includeEventTypes"] = ["$pageview", "custom_event"]
        pf["endPoint"] = SUBMIT
    q = {"kind": "PathsQuery", "pathsFilter": pf, "dateRange": {"date_from": f"-{days}d"}}
    res = query(q)["results"]
    title = f"PATHS ending at address-entry" if end_at_conv else f"PATHS from {start}"
    print("=" * 60); print(title, "(server-side)"); print("=" * 60)
    edges = sorted(res, key=lambda e: -e.get("value", 0))[:30]
    for e in edges:
        s = e.get("source", "").split("_", 1)[-1]
        t = e.get("target", "").split("_", 1)[-1]
        print(f"  {e.get('value'):>3}  {s[:34]:34} -> {t[:34]}")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("cmd", choices=["funnel", "paths-to", "paths-from"])
    ap.add_argument("--days", type=int, default=220)
    ap.add_argument("--start", default="/for-sale-v3")
    args = ap.parse_args()
    try:
        if args.cmd == "funnel":
            cmd_funnel(args.days)
        elif args.cmd == "paths-to":
            cmd_paths(args.days, end_at_conv=True)
        else:
            cmd_paths(args.days, start=args.start)
    except urllib.error.HTTPError as e:
        print("Query API error:", e.read().decode()[:300])


if __name__ == "__main__":
    main()
