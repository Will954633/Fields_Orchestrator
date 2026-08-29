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
    """Return GSC rows tagged with the DIMENSION SET they came from, or a setup note.

    ⚠ Why there are two pulls, not one (measured 2026-08-30, [SEO-QUERY-DIMENSION-BLINDNESS]):
    Search Console DROPS whole rows when the `query` dimension is requested, because
    anonymized (low-volume / personally-identifying) queries are withheld rather than
    bucketed. Over 90 days to 2026-08-30 the difference was not marginal:

        dimensions=[page,query,device] ->  5,330 impressions / 78 clicks
        dimensions=[page]              -> 58,422 impressions / 1,178 clicks

    i.e. the query pull sees **9% of impressions and 7% of clicks**. Every consumer that
    summed the query rows to get a per-page or site total was reading a 9% sample and
    calling it the channel. So we now pull BOTH and tag each row:

        dims="page"              -> AUTHORITATIVE per-page clicks/impressions/position.
        dims="page,query,device" -> query ATTRIBUTION only. Never sum these for a total.
        dims="__site_totals__"   -> one row, exact site totals, immune to both of the above.

    Consumers MUST filter on `dims`; summing the collection blind now double-counts.
    """
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
    from googleapiclient.errors import HttpError

    def _query(dimensions):
        """Paginate one dimension set. Returns (raw_rows, error_or_None)."""
        out, start_row = [], 0
        while True:
            try:
                resp = svc.searchanalytics().query(siteUrl=site, body={
                    "startDate": str(start), "endDate": str(end),
                    "dimensions": dimensions,
                    "rowLimit": 25000, "startRow": start_row}).execute()
            except HttpError as e:
                return out, f"GSC query error on dims={dimensions}: {e}"
            batch = resp.get("rows", [])
            out += batch
            if len(batch) < 25000:
                return out, None
            start_row += 25000

    rows = []

    # 1. AUTHORITATIVE per-page rows.
    page_raw, err = _query(["page"])
    if err:
        return None, err
    for r in page_raw:
        rows.append({"source": "google", "dims": "page", "page": r["keys"][0], "query": None,
                     "device": None, "clicks": r.get("clicks", 0),
                     "impressions": r.get("impressions", 0),
                     "ctr": round(r.get("ctr", 0), 4), "position": round(r.get("position", 0), 1)})

    # 2. Query attribution — a SAMPLE by construction (see docstring). Never sum for totals.
    q_raw, err = _query(["page", "query", "device"])
    if err:
        return None, err
    for r in q_raw:
        page, query, device = r["keys"]
        rows.append({"source": "google", "dims": "page,query,device", "page": page,
                     "query": query, "device": device,
                     "clicks": r.get("clicks", 0), "impressions": r.get("impressions", 0),
                     "ctr": round(r.get("ctr", 0), 4), "position": round(r.get("position", 0), 1)})

    # 3. Exact site totals — the ground truth neither pull above can be trusted to reproduce.
    tot_raw, err = _query(["date"])
    if err:
        return None, err
    site_impr = sum(r.get("impressions", 0) for r in tot_raw)
    site_clk = sum(r.get("clicks", 0) for r in tot_raw)
    rows.append({"source": "google", "dims": "__site_totals__", "page": None, "query": None,
                 "device": None, "clicks": site_clk, "impressions": site_impr,
                 "ctr": round(site_clk / site_impr, 4) if site_impr else 0, "position": None,
                 "window_days": days, "start_date": str(start), "end_date": str(end),
                 "days_with_data": len(tot_raw)})

    page_impr = sum(r.get("impressions", 0) for r in page_raw)
    q_impr = sum(r.get("impressions", 0) for r in q_raw)
    cov = (100.0 * q_impr / site_impr) if site_impr else 0.0
    note = (f"google: {site_impr} impr / {site_clk} clicks over {days}d from {site} | "
            f"page rows={len(page_raw)} ({page_impr} impr) | "
            f"query rows={len(q_raw)} ({q_impr} impr = {cov:.1f}% of site — the rest is "
            f"anonymized by Google and is NOT missing traffic)")
    return rows, note


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
            rows.append({"source": "bing", "dims": "query", "page": None, "query": r.get("Query"),
                         "clicks": r.get("Clicks"), "impressions": r.get("Impressions"),
                         "position": r.get("AvgImpressionPosition")})
        # per-page query stats for our converting pages -> pins query to page
        for path in sorted(converting_pages or []):
            page_url = BING_SITE.rstrip("/") + path
            try:
                for r in _bing_get("GetPageQueryStats", siteUrl=BING_SITE, page=page_url):
                    rows.append({"source": "bing", "dims": "page,query", "page": page_url,
                                 "query": r.get("Query"),
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

    # Rule 7b: a clean exit having written nothing is a failure, not an empty queue. The
    # site has continuous organic traffic, so zero rows means the pull broke — say so loudly
    # rather than leaving yesterday's snapshot in place looking current.
    if not all_rows:
        raise SystemExit("FAILED: no GSC or Bing rows returned. The site has continuous "
                         "organic traffic, so this is a broken pull, not an empty result. "
                         "Previous snapshot left untouched — do NOT read it as current.")

    coll = db.seo_landing_performance
    coll.delete_many({})
    now = datetime.now(timezone.utc).isoformat()
    for r in all_rows:
        r["computed_at"] = now
    # Batched — the page dimension alone is ~12.5k rows at 90 days and a single
    # insert_many that size exhausts Cosmos RU and 16500s the whole write.
    for i in range(0, len(all_rows), 500):
        coll.insert_many(all_rows[i:i + 500])
    coll.create_index("page")
    coll.create_index("dims")
    print(f"\nwrote {len(all_rows)} seo_landing_performance rows")
    print("   ⚠ consumers MUST filter on `dims`: 'page' = authoritative per-page totals; "
          "'page,query,device' = query attribution only (a ~9% sample — Google withholds "
          "anonymized queries); '__site_totals__' = exact site totals. Summing blind double-counts.")

    # JOIN: converting landing pages × their search queries.
    # Query rows only — the page-dimension rows carry no query and would print as None.
    q_rows = [r for r in all_rows if r.get("query")]
    conv_pages = {a["_id"] for a in db.organic_landing_affinity.find({"converters": {"$gt": 0}})}
    print("\n=== QUERIES DRIVING CONVERTING PAGES ===")
    for page in conv_pages:
        hits = [r for r in q_rows if r.get("page") and page in r["page"]]
        if not hits:
            continue
        hits.sort(key=lambda r: -(r.get("clicks") or 0))
        print(f"\n{page}")
        for h in hits[:8]:
            print(f"   [{h['source']}] '{h['query']}' — clicks {h.get('clicks')}, "
                  f"impr {h.get('impressions')}, pos {h.get('position')}")


if __name__ == "__main__":
    main()
