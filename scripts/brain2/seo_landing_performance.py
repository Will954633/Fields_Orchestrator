#!/usr/bin/env python3
"""
seo_landing_performance.py — Brain 2 Layer 5b: SEO query/position per URL.

The search TERM + position are stripped from the PostHog referrer, so the only way
to recover "which query, what position" is the webmaster APIs — joined to our
converting pages at the URL level (per-URL, not per-person; privacy makes per-session
query attribution impossible).

Google Search Console (Search Analytics) — per (page, query, device): clicks,
impressions, ctr, avg position. Bing Webmaster Tools — same for Bing.

Writes system_monitor.seo_landing_performance (one doc per (source, page, query)),
then prints the join: converting landing pages (from organic_landing_affinity) with
the queries + positions feeding them.

SETUP (one-time, Will action):
  Google: Search Console (search.google.com/search-console) for fieldsestate.com.au
    -> Settings -> Users and permissions -> Add user ->
       floor-plan-processor@fields-estate.iam.gserviceaccount.com  (Full or Restricted)
  Bing: Bing Webmaster Tools -> Settings -> API access -> generate key ->
       put in .env as BING_WEBMASTER_API_KEY

Usage: python3 scripts/brain2/seo_landing_performance.py [--days 30]
"""
import os, sys, json, argparse, urllib.request, urllib.error, urllib.parse
from datetime import datetime, timezone, timedelta
from dotenv import load_dotenv

load_dotenv("/home/fields/Fields_Orchestrator/.env")
sys.path.insert(0, "/home/fields/Fields_Orchestrator")
from shared.db import get_client  # noqa: E402

SA = "/home/fields/.gcp-floor-plan-vision.json"
SITE_CANDIDATES = ["sc-domain:fieldsestate.com.au", "https://fieldsestate.com.au/"]
BING_KEY = os.environ.get("BING_WEBMASTER_API_KEY", "")
BING_SITE = "https://fieldsestate.com.au/"  # must match the verified form exactly (trailing slash)


def gsc_pull(days):
    """Return list of {page,query,device,clicks,impressions,ctr,position} or a setup note."""
    try:
        from google.oauth2 import service_account
        from googleapiclient.discovery import build
        from googleapiclient.errors import HttpError
    except ImportError:
        return None, "google-api-python-client not installed"
    creds = service_account.Credentials.from_service_account_file(
        SA, scopes=["https://www.googleapis.com/auth/webmasters.readonly"])
    svc = build("searchconsole", "v1", credentials=creds, cache_discovery=False)
    sites = [s["siteUrl"] for s in svc.sites().list().execute().get("siteEntry", [])]
    if not sites:
        return None, ("SA has no Search Console properties. Add "
                      "floor-plan-processor@fields-estate.iam.gserviceaccount.com as a user "
                      "on fieldsestate.com.au in Search Console → Settings → Users & permissions.")
    site = next((s for s in SITE_CANDIDATES if s in sites), sites[0])
    end = datetime.now(timezone.utc).date()
    start = end - timedelta(days=days)
    rows, start_row = [], 0
    from googleapiclient.errors import HttpError
    while True:
        try:
            resp = svc.searchanalytics().query(siteUrl=site, body={
                "startDate": str(start), "endDate": str(end),
                "dimensions": ["page", "query", "device"],
                "rowLimit": 25000, "startRow": start_row}).execute()
        except HttpError as e:
            return None, f"GSC query error: {e}"
        batch = resp.get("rows", [])
        for r in batch:
            page, query, device = r["keys"]
            rows.append({"source": "google", "page": page, "query": query, "device": device,
                         "clicks": r.get("clicks", 0), "impressions": r.get("impressions", 0),
                         "ctr": round(r.get("ctr", 0), 4), "position": round(r.get("position", 0), 1)})
        if len(batch) < 25000:
            break
        start_row += 25000
    return rows, f"google: {len(rows)} (page,query) rows from {site}"


def _bing_get(method, **params):
    params["apikey"] = BING_KEY
    url = f"https://ssl.bing.com/webmaster/api.svc/json/{method}?" + urllib.parse.urlencode(params)
    return json.loads(urllib.request.urlopen(url, timeout=60).read()).get("d", [])


def bing_pull(days, converting_pages=None):
    if not BING_KEY:
        return None, "no BING_WEBMASTER_API_KEY set — skip Bing (Bing Webmaster → Settings → API access)"
    rows = []
    try:
        # site-wide query stats (Query, Clicks, Impressions, AvgImpressionPosition)
        for r in _bing_get("GetQueryStats", siteUrl=BING_SITE):
            rows.append({"source": "bing", "page": None, "query": r.get("Query"),
                         "clicks": r.get("Clicks"), "impressions": r.get("Impressions"),
                         "position": r.get("AvgImpressionPosition")})
        # per-page query stats for our converting pages -> pins query to page
        for path in sorted(converting_pages or []):
            page_url = BING_SITE.rstrip("/") + path
            try:
                for r in _bing_get("GetPageQueryStats", siteUrl=BING_SITE, page=page_url):
                    rows.append({"source": "bing", "page": page_url, "query": r.get("Query"),
                                 "clicks": r.get("Clicks"), "impressions": r.get("Impressions"),
                                 "position": r.get("AvgImpressionPosition")})
            except Exception:
                pass
    except Exception as e:
        return None, f"Bing error: {str(e)[:150]}"
    return rows, f"bing: {len(rows)} rows (site-wide + per converting page)"


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--days", type=int, default=30)
    args = ap.parse_args()
    db = get_client()["system_monitor"]

    conv_pages = {a["_id"] for a in db.organic_landing_affinity.find({"converters": {"$gt": 0}})}

    all_rows = []
    for name, fn in [("GSC", lambda d: gsc_pull(d)),
                     ("Bing", lambda d: bing_pull(d, conv_pages))]:
        rows, note = fn(args.days)
        print(f"[{name}] {note}")
        if rows:
            all_rows += rows

    if all_rows:
        coll = db.seo_landing_performance
        coll.delete_many({})
        now = datetime.now(timezone.utc).isoformat()
        for r in all_rows:
            r["computed_at"] = now
        coll.insert_many(all_rows)
        coll.create_index("page")
        print(f"\nwrote {len(all_rows)} seo_landing_performance rows")

        # JOIN: converting landing pages × their search queries
        conv_pages = {a["_id"] for a in db.organic_landing_affinity.find({"converters": {"$gt": 0}})}
        print("\n=== QUERIES DRIVING CONVERTING PAGES ===")
        for page in conv_pages:
            hits = [r for r in all_rows if r.get("page") and page in r["page"]]
            if not hits:
                continue
            hits.sort(key=lambda r: -(r.get("clicks") or 0))
            print(f"\n{page}")
            for h in hits[:8]:
                print(f"   [{h['source']}] '{h['query']}' — clicks {h.get('clicks')}, "
                      f"impr {h.get('impressions')}, pos {h.get('position')}")
    else:
        print("\nNo SEO data yet — complete the one-time setup in the module docstring, "
              "then re-run. Script is ready.")


if __name__ == "__main__":
    main()
