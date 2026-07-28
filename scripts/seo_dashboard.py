#!/usr/bin/env python3
"""
seo_dashboard.py — nightly Google Search Console + indexation dashboard → Drive.

WHAT: builds one dedicated Google Sheet ("Fields — SEO & Indexation Dashboard")
giving a comprehensive, trended view of where the site is at on SEO:
  • Overview      — 28d clicks/impressions/CTR/position (+ WoW delta), sitemap
                    composition, indexation summary, GSC sitemap status.
  • Daily Trend   — clicks/impressions/CTR/position per day (last 90d), rewritten.
  • Top Queries   — top 150 queries (28d) by impressions.
  • Top Pages     — top 150 pages (28d) by impressions.
  • By Page Type  — 28d performance aggregated by URL pattern (property, off-market,
                    market-metrics, houses-for-sale, articles, feeds, …).
  • Indexation    — per page-type index coverage from live URL Inspection sampling,
                    reconstructing the "Page indexing" buckets the API doesn't expose
                    in aggregate (Indexed / Discovered-not-indexed / Crawled-not-indexed
                    / Duplicate-canonical / Other) + extrapolated site estimate.
  • Indexation Log— one appended row per night (the indexation trend substrate).

AUTH MODEL (matches live_leads_to_sheet.py): the sheet is OWNED BY WILL (created
once with his gdrive OAuth via --bootstrap, then shared to the service account),
and every NIGHTLY run writes via the stable service account — so the cron never
depends on the 7-day-expiring OAuth refresh token.

USAGE:
  python3 scripts/seo_dashboard.py --bootstrap   # one-time: create sheet + share to SA
  python3 scripts/seo_dashboard.py               # nightly: refresh all tabs
  python3 scripts/seo_dashboard.py --sample 300  # override URL-inspection sample size

GSC data lags ~2-3 days; the trend still advances nightly.
"""
import argparse
import json
import os
import random
import re
import sys
import time
import urllib.request
from collections import defaultdict
from datetime import date, datetime, timedelta, timezone

from google.oauth2 import service_account
from googleapiclient.discovery import build

from job_status import job_run  # heartbeat → system_monitor.job_runs → Systems Health sheet

SITE = "https://fieldsestate.com.au/"
SITEMAP_URL = "https://fieldsestate.com.au/sitemap.xml"
SA_KEY = "/home/fields/.gcp-floor-plan-vision.json"
SA_EMAIL = "floor-plan-processor@fields-estate.iam.gserviceaccount.com"
CONFIG_PATH = os.path.join(os.path.dirname(__file__), "..", "config", "seo_dashboard.json")
WILL_EMAIL = "will@fieldsestate.com.au"

GSC_SCOPES = ["https://www.googleapis.com/auth/webmasters"]
SHEETS_SCOPE = ["https://www.googleapis.com/auth/spreadsheets"]

TABS = ["Overview", "Daily Trend", "Top Queries", "Top Pages",
        "By Page Type", "Indexation", "Indexation Log"]

# --- URL → page-type classification (order matters: first match wins) ---
PAGE_TYPES = [
    ("Homepage",              lambda p: p in ("", "/")),
    ("Houses-for-sale (suburb)", lambda p: p.startswith("/houses-for-sale/")),
    ("Property (for-sale+sold)", lambda p: p.startswith("/property/") or p.startswith("/sold/")),
    ("Off-market",            lambda p: p.startswith("/off-market/")),
    ("Market Metrics",        lambda p: p.startswith("/market-metrics")),
    ("Market Intelligence/News", lambda p: p.startswith("/market-intelligence")),
    ("Articles",              lambda p: p.startswith("/article")),
    ("For-Sale feeds",        lambda p: p.startswith("/for-sale") or p.startswith("/recently-sold") or p == "/discover"),
    ("Analyse Your Home",     lambda p: p.startswith("/analyse")),
    ("Compare",               lambda p: p.startswith("/compare/")),
]


def classify(url_or_path):
    p = url_or_path
    if p.startswith("http"):
        p = re.sub(r"^https?://[^/]+", "", p)
    p = p.split("?")[0].split("#")[0]
    for name, fn in PAGE_TYPES:
        if fn(p):
            return name
    return "Other"


# ---------------------------------------------------------------- auth
def sa_creds(scopes):
    return service_account.Credentials.from_service_account_file(SA_KEY, scopes=scopes)


def gsc_svc():
    return build("searchconsole", "v1", credentials=sa_creds(GSC_SCOPES), cache_discovery=False)


def sheets_svc_sa():
    return build("sheets", "v4", credentials=sa_creds(SHEETS_SCOPE), cache_discovery=False)


def load_config():
    try:
        with open(os.path.abspath(CONFIG_PATH)) as f:
            return json.load(f)
    except FileNotFoundError:
        return {}


def save_config(cfg):
    with open(os.path.abspath(CONFIG_PATH), "w") as f:
        json.dump(cfg, f, indent=2)


# ---------------------------------------------------------------- GSC pulls
def sa_query(svc, start, end, dimensions, row_limit=1000, **extra):
    body = {"startDate": str(start), "endDate": str(end),
            "dimensions": dimensions, "rowLimit": row_limit}
    body.update(extra)
    return svc.searchanalytics().query(siteUrl=SITE, body=body).execute().get("rows", [])


def totals(svc, start, end):
    r = sa_query(svc, start, end, [], 1)
    if not r:
        return {"clicks": 0, "impressions": 0, "ctr": 0, "position": 0}
    return r[0]


def sitemap_status(svc):
    out = []
    for s in svc.sitemaps().list(siteUrl=SITE).execute().get("sitemap", []):
        contents = s.get("contents", [{}])[0]
        out.append({
            "path": s.get("path"),
            "lastDownloaded": s.get("lastDownloaded", "—"),
            "isPending": s.get("isPending", False),
            "errors": s.get("errors", 0),
            "warnings": s.get("warnings", 0),
            "submitted": contents.get("submitted", "—"),
            "indexed": contents.get("indexed", "—"),
        })
    return out


# ---------------------------------------------------------------- sitemap parse
def fetch_sitemap_urls():
    xml = urllib.request.urlopen(SITEMAP_URL, timeout=60).read().decode("utf-8", "replace")
    return re.findall(r"<loc>(https://fieldsestate\.com\.au/[^<]*)</loc>", xml)


# ---------------------------------------------------------------- URL inspection
def inspect(svc, url):
    body = {"inspectionUrl": url, "siteUrl": SITE, "languageCode": "en-AU"}
    r = svc.urlInspection().index().inspect(body=body).execute()
    idx = r.get("inspectionResult", {}).get("indexStatusResult", {})
    return idx.get("coverageState") or "Unknown"


# Map raw coverageState strings to compact dashboard buckets.
def bucket(cov):
    c = (cov or "").lower()
    if "submitted and indexed" in c or c == "indexed":
        return "Indexed"
    if "discovered" in c:
        return "Discovered – not indexed"
    if "crawled" in c and "not indexed" in c:
        return "Crawled – not indexed"
    if "duplicate" in c or "alternate page" in c or "canonical" in c:
        return "Duplicate / canonical"
    if "excluded" in c or "noindex" in c or "blocked" in c or "redirect" in c or "not found" in c or "soft 404" in c:
        return "Excluded (noindex/redirect/blocked)"
    if c.startswith("error"):
        return "Inspection error"
    return "Other"


BUCKET_ORDER = ["Indexed", "Discovered – not indexed", "Crawled – not indexed",
                "Duplicate / canonical", "Excluded (noindex/redirect/blocked)",
                "Other", "Inspection error"]


# ---------------------------------------------------------------- sheet helpers
def ensure_tabs(svc, sid):
    meta = svc.spreadsheets().get(spreadsheetId=sid).execute()
    existing = {s["properties"]["title"]: s["properties"]["sheetId"] for s in meta["sheets"]}
    reqs = []
    for t in TABS:
        if t not in existing:
            reqs.append({"addSheet": {"properties": {"title": t}}})
    # drop the default "Sheet1" if present and unused
    if reqs:
        svc.spreadsheets().batchUpdate(spreadsheetId=sid, body={"requests": reqs}).execute()
    meta = svc.spreadsheets().get(spreadsheetId=sid).execute()
    gids = {s["properties"]["title"]: s["properties"]["sheetId"] for s in meta["sheets"]}
    if "Sheet1" in gids and "Overview" in gids:
        try:
            svc.spreadsheets().batchUpdate(spreadsheetId=sid, body={
                "requests": [{"deleteSheet": {"sheetId": gids["Sheet1"]}}]}).execute()
        except Exception:
            pass
    return gids


def write_tab(svc, sid, tab, rows):
    """Clear then write a 2D list of rows to a tab (overwrite semantics)."""
    svc.spreadsheets().values().clear(spreadsheetId=sid, range=f"'{tab}'!A1:Z100000").execute()
    svc.spreadsheets().values().update(
        spreadsheetId=sid, range=f"'{tab}'!A1", valueInputOption="RAW",
        body={"values": rows}).execute()


def append_or_replace_dated(svc, sid, tab, header, row, date_col=0):
    """Append a row; if the last data row has the same date (col date_col), replace it."""
    existing = svc.spreadsheets().values().get(
        spreadsheetId=sid, range=f"'{tab}'!A1:Z100000").execute().get("values", [])
    if not existing:
        write_tab(svc, sid, tab, [header, row])
        return
    if len(existing) >= 2 and existing[-1] and existing[-1][date_col] == row[date_col]:
        # overwrite last row (same-day re-run)
        r = len(existing)
        svc.spreadsheets().values().update(
            spreadsheetId=sid, range=f"'{tab}'!A{r}", valueInputOption="RAW",
            body={"values": [row]}).execute()
    else:
        svc.spreadsheets().values().append(
            spreadsheetId=sid, range=f"'{tab}'!A1", valueInputOption="RAW",
            insertDataOption="INSERT_ROWS", body={"values": [row]}).execute()


def pct(n, d):
    return round(100.0 * n / d, 1) if d else 0.0


# ---------------------------------------------------------------- bootstrap (OAuth, one-time)
def bootstrap():
    from google.oauth2.credentials import Credentials
    from google.auth.transport.requests import Request
    keys = json.load(open("/home/fields/.gdrive-oauth.keys.json"))["installed"]
    tok = json.load(open("/home/fields/.gdrive-server-credentials.json"))
    creds = Credentials(
        token=tok.get("access_token"), refresh_token=tok.get("refresh_token"),
        token_uri=keys["token_uri"], client_id=keys["client_id"],
        client_secret=keys["client_secret"],
        scopes=["https://www.googleapis.com/auth/drive",
                "https://www.googleapis.com/auth/spreadsheets"])
    if not creds.valid:
        creds.refresh(Request())
    sheets = build("sheets", "v4", credentials=creds, cache_discovery=False)
    drive = build("drive", "v3", credentials=creds, cache_discovery=False)

    created = sheets.spreadsheets().create(body={
        "properties": {"title": "Fields — SEO & Indexation Dashboard"},
        "sheets": [{"properties": {"title": t}} for t in TABS],
    }).execute()
    sid = created["spreadsheetId"]
    print("Created sheet:", sid)
    print("URL:", created.get("spreadsheetUrl"))

    # Share to the service account (writer) so nightly SA runs can update it.
    drive.permissions().create(
        fileId=sid, sendNotificationEmail=False,
        body={"type": "user", "role": "writer", "emailAddress": SA_EMAIL}).execute()
    print("Shared writer →", SA_EMAIL)

    cfg = load_config()
    cfg["spreadsheet_id"] = sid
    cfg["spreadsheet_url"] = created.get("spreadsheetUrl")
    save_config(cfg)
    print("Saved id to", os.path.abspath(CONFIG_PATH))
    return sid


# ---------------------------------------------------------------- main nightly run
def run(sample_size):
    cfg = load_config()
    sid = cfg.get("spreadsheet_id")
    if not sid:
        sys.exit("No spreadsheet_id in config — run with --bootstrap first.")

    gsc = gsc_svc()
    sh = sheets_svc_sa()
    ensure_tabs(sh, sid)

    today = datetime.now(timezone.utc).date()
    # GSC data lags ~3 days; window ends 3 days back for stable numbers.
    end = today - timedelta(days=3)
    start = end - timedelta(days=27)          # 28-day window
    prev_end = start - timedelta(days=1)
    prev_start = prev_end - timedelta(days=27)
    stamp = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")

    def delta(a, b):
        return f"{a - b:+.0f}" if isinstance(a, (int, float)) else "—"

    # ==== PERFORMANCE (fast, no sampling) — written FIRST so a slow/interrupted
    #      indexation pass never costs us the GSC numbers. =====================
    cur = totals(gsc, start, end)
    prev = totals(gsc, prev_start, prev_end)

    # ---- Daily Trend (last 90d, full rewrite)
    dstart = end - timedelta(days=89)
    drows = sorted(sa_query(gsc, dstart, end, ["date"], row_limit=1000), key=lambda r: r["keys"][0])
    dt = [["Date", "Clicks", "Impressions", "CTR %", "Avg position"]]
    for r in drows:
        dt.append([r["keys"][0], r["clicks"], r["impressions"], round(r["ctr"] * 100, 2), round(r["position"], 1)])
    write_tab(sh, sid, "Daily Trend", dt)

    # ---- Top Queries
    q = sorted(sa_query(gsc, start, end, ["query"], row_limit=150), key=lambda r: r["impressions"], reverse=True)
    tq = [["Query", "Clicks", "Impressions", "CTR %", "Avg position"]]
    for r in q:
        tq.append([r["keys"][0], r["clicks"], r["impressions"], round(r["ctr"] * 100, 2), round(r["position"], 1)])
    write_tab(sh, sid, "Top Queries", tq)

    # ---- Top Pages
    pg = sorted(sa_query(gsc, start, end, ["page"], row_limit=150), key=lambda r: r["impressions"], reverse=True)
    tp = [["Page", "Clicks", "Impressions", "CTR %", "Avg position"]]
    for r in pg:
        tp.append([r["keys"][0].replace("https://fieldsestate.com.au", ""), r["clicks"], r["impressions"],
                   round(r["ctr"] * 100, 2), round(r["position"], 1)])
    write_tab(sh, sid, "Top Pages", tp)

    # ---- sitemap composition (needed by By Page Type + Indexation)
    sm_urls = fetch_sitemap_urls()
    comp = defaultdict(int)
    by_type_urls = defaultdict(list)
    for u in sm_urls:
        t = classify(u)
        comp[t] += 1
        by_type_urls[t].append(u)
    total_urls = len(sm_urls)

    # ---- By Page Type (aggregate 28d perf across all pages)
    allpg = sa_query(gsc, start, end, ["page"], row_limit=5000)
    agg = defaultdict(lambda: {"clicks": 0, "impr": 0, "pos_w": 0.0})
    for r in allpg:
        t = classify(r["keys"][0])
        agg[t]["clicks"] += r["clicks"]
        agg[t]["impr"] += r["impressions"]
        agg[t]["pos_w"] += r["position"] * r["impressions"]
    bpt = [["Page type", "Sitemap URLs", "Clicks (28d)", "Impressions (28d)", "CTR %", "Avg position"]]
    for t in [name for name, _ in PAGE_TYPES] + ["Other"]:
        a = agg.get(t)
        if not a and not comp.get(t):
            continue
        a = a or {"clicks": 0, "impr": 0, "pos_w": 0.0}
        bpt.append([t, comp.get(t, 0), a["clicks"], a["impr"], pct(a["clicks"], a["impr"]),
                    round(a["pos_w"] / a["impr"], 1) if a["impr"] else "—"])
    write_tab(sh, sid, "By Page Type", bpt)

    # ==== INDEXATION (slow — URL Inspection sampling, stratified by page type) ==
    sm_stat = sitemap_status(gsc)
    per_type_cap = max(15, sample_size // max(1, len(by_type_urls)))
    idx_by_type = {}
    for ptype, urls in by_type_urls.items():
        random.shuffle(urls)
        counts = defaultdict(int)
        for u in urls[:per_type_cap]:
            try:
                cov = inspect(gsc, u)
            except Exception as e:
                cov = f"ERROR: {type(e).__name__}"
                time.sleep(2)
            counts[bucket(cov)] += 1
            time.sleep(0.2)   # under URL-Inspection QPS limits
        idx_by_type[ptype] = dict(counts)

    est_indexed = 0
    sample_bucket_totals = defaultdict(int)
    for ptype, counts in idx_by_type.items():
        n = sum(counts.values())
        if not n:
            continue
        for b, c in counts.items():
            sample_bucket_totals[b] += c
        est_indexed += round((counts.get("Indexed", 0) / n) * comp.get(ptype, 0))
    total_sampled = sum(sample_bucket_totals.values())
    site_indexed_pct = pct(sample_bucket_totals.get("Indexed", 0), total_sampled)

    # ---- Indexation (per page type)
    ix = [["Page type", "Sitemap URLs", "Sampled"] + BUCKET_ORDER + ["Indexed %", "Est. indexed"]]
    for t in [name for name, _ in PAGE_TYPES] + ["Other"]:
        counts = idx_by_type.get(t)
        if not counts:
            continue
        n = sum(counts.values())
        row = [t, comp.get(t, 0), n] + [counts.get(b, 0) for b in BUCKET_ORDER]
        row += [f"{pct(counts.get('Indexed', 0), n)}%",
                round((counts.get("Indexed", 0) / n) * comp.get(t, 0)) if n else 0]
        ix.append(row)
    write_tab(sh, sid, "Indexation", ix)

    # ---- Indexation Log (append one dated row)
    log_header = ["Date", "Sitemap URLs", "Sampled", "Indexed %"] + BUCKET_ORDER + ["Est. indexed"]
    log_row = [str(today), total_urls, total_sampled, site_indexed_pct] + \
              [sample_bucket_totals.get(b, 0) for b in BUCKET_ORDER] + [est_indexed]
    append_or_replace_dated(sh, sid, "Indexation Log", log_header, log_row)

    # ---- Overview (written last — needs both perf + indexation) ----
    ov = [
        ["Fields — SEO & Indexation Dashboard"],
        [f"Auto-updated nightly via scripts/seo_dashboard.py · last run {stamp}"],
        [f"GSC performance window: {start} → {end} (Search Console lags ~3 days)"],
        [],
        ["SEARCH PERFORMANCE (28 days)", "Latest", "Prev 28d", "Δ"],
        ["Clicks", cur.get("clicks", 0), prev.get("clicks", 0), delta(cur.get("clicks", 0), prev.get("clicks", 0))],
        ["Impressions", cur.get("impressions", 0), prev.get("impressions", 0), delta(cur.get("impressions", 0), prev.get("impressions", 0))],
        ["CTR %", round(cur.get("ctr", 0) * 100, 2), round(prev.get("ctr", 0) * 100, 2), delta(round(cur.get("ctr", 0) * 100, 2), round(prev.get("ctr", 0) * 100, 2))],
        ["Avg position", round(cur.get("position", 0), 1), round(prev.get("position", 0), 1), delta(round(cur.get("position", 0), 1), round(prev.get("position", 0), 1))],
        [],
        ["INDEXATION (live URL-Inspection sample)", "Value"],
        ["URLs sampled tonight", total_sampled],
        ["Sampled indexed %", f"{site_indexed_pct}%"],
        ["Est. indexed pages (extrapolated)", est_indexed],
        ["Sitemap URLs total", total_urls],
    ]
    for b in BUCKET_ORDER:
        if sample_bucket_totals.get(b):
            ov.append([f"  sample · {b}", f"{sample_bucket_totals[b]} ({pct(sample_bucket_totals[b], total_sampled)}%)"])
    ov += [[], ["SITEMAP COMPOSITION", "URLs"]]
    for ptype, _ in PAGE_TYPES + [("Other", None)]:
        if comp.get(ptype):
            ov.append([f"  {ptype}", comp[ptype]])
    ov += [[], ["GSC SITEMAP STATUS", "submitted", "indexed", "lastDownloaded", "errors", "warnings"]]
    for s in sm_stat:
        ov.append([f"  {s['path']}", s["submitted"], s["indexed"], s["lastDownloaded"], s["errors"], s["warnings"]])
    write_tab(sh, sid, "Overview", ov)

    print(f"Dashboard updated: {sid}")
    print(f"  perf 28d: clicks={cur.get('clicks',0)} impr={cur.get('impressions',0)} "
          f"ctr={round(cur.get('ctr',0)*100,2)}% pos={round(cur.get('position',0),1)}")
    print(f"  indexation sample: {total_sampled} urls, {site_indexed_pct}% indexed, "
          f"est {est_indexed}/{total_urls} indexed")
    print(f"  url: {cfg.get('spreadsheet_url')}")
    return {"clicks": cur.get("clicks", 0), "impressions": cur.get("impressions", 0),
            "ctr_pct": round(cur.get("ctr", 0) * 100, 2), "avg_position": round(cur.get("position", 0), 1),
            "sampled": total_sampled, "indexed_pct": site_indexed_pct,
            "est_indexed": est_indexed, "sitemap_urls": total_urls}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--bootstrap", action="store_true", help="one-time: create the sheet (Will-owned) + share to SA")
    ap.add_argument("--sample", type=int, default=150, help="total URL-inspection sample size (stratified by page type)")
    args = ap.parse_args()
    if args.bootstrap:
        bootstrap()
        return
    # Heartbeat wrapper: success/failure both recorded → auto-surfaces on the
    # Fields Systems Health sheet (Process Registry). Never fails silently.
    with job_run("seo_dashboard", cadence_hours=24, title="SEO & Indexation Dashboard") as beat:
        m = run(args.sample)
        beat.metrics = m
        beat.detail = (f"{m['clicks']} clicks / {m['impressions']} impr / pos {m['avg_position']} · "
                       f"{m['indexed_pct']}% indexed (sample {m['sampled']})")


if __name__ == "__main__":
    main()
