#!/usr/bin/env python3
"""
kpi_rollup.py — populate the KPI Monitor sheet from live data, and build the
"Samantha Impact" view.

Why: the KPI dashboard shipped with `MEASURE` placeholders because nothing computed
the metrics she is supposed to steer by (engaged sessions, cost-per-engaged, etc.);
`website_daily_metrics` is broken (all zeros) and PostHog was never wired to the sheet.
This pulls the reliably-computable metrics (Mongo funnel collections + 2 HogQL reads)
into the Dashboard 'Latest' column and appends a Weekly Log row. `impact` builds a
"Samantha Impact" tab (her actions, ship rate, change-ledger verdicts, cost) so we can
answer "is she a valuable asset?".

Usage:
  python3 scripts/samantha/kpi_rollup.py rollup     # update Dashboard Latest + append Weekly Log
  python3 scripts/samantha/kpi_rollup.py impact      # (re)build the Samantha Impact tab
  python3 scripts/samantha/kpi_rollup.py all         # both
"""
from __future__ import annotations
import argparse, json, os, sys, warnings
from datetime import datetime, timezone, timedelta
warnings.filterwarnings("ignore")

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))
sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "brain2"))
from google.oauth2.credentials import Credentials
from google.auth.transport.requests import Request
from googleapiclient.discovery import build
from src.mongo_client_factory import get_mongo_client

SHEET = "1BxDgfEVLOsmGujZe5R1LNsq9sY2WtVt6d_wEpxJMLYY"
OAUTH_KEYS = "/home/fields/.gdrive-oauth.keys.json"
SERVER_CREDS = "/home/fields/.gdrive-server-credentials.json"
NOW = datetime.now(timezone.utc)
WK = NOW - timedelta(days=7)
TODAY = (NOW + timedelta(hours=10)).strftime("%Y-%m-%d")  # AEST date


def _svc():
    keys = json.load(open(OAUTH_KEYS))["installed"]; tok = json.load(open(SERVER_CREDS))
    c = Credentials(token=tok.get("access_token"), refresh_token=tok.get("refresh_token"),
        token_uri=keys["token_uri"], client_id=keys["client_id"],
        client_secret=keys["client_secret"], scopes=(tok.get("scope") or "").split())
    if not c.valid:
        c.refresh(Request())
    return build("sheets", "v4", credentials=c, cache_discovery=False)


def _count7(sm, coll, field=("created_at", "submitted_at", "timestamp", "date")):
    """7-day count via a best-effort date field."""
    from datetime import datetime as _dt
    try:
        c = sm[coll]
        for f in field:
            n = c.count_documents({f: {"$gte": WK}})
            if n:
                return n
        # fallback: iterate (small collections)
        tot = 0
        for d in c.find({}, limit=3000):
            for f in field:
                v = d.get(f)
                if isinstance(v, _dt):
                    vv = v if v.tzinfo else v.replace(tzinfo=timezone.utc)
                    if vv >= WK:
                        tot += 1
                    break
        return tot
    except Exception:
        return 0


def _hog(sql):
    try:
        from brain2_util import hog_retry
        pid = os.environ.get("POSTHOG_PROJECT_ID", "348370")
        key = os.environ.get("POSTHOG_ALL_ACCESS_KEY") or os.environ.get("POSTHOG_PERSONAL_API_KEY")
        r = hog_retry(pid, key, sql)
        return r[0][0] if r and r[0] else None
    except Exception as e:
        print(f"  [hog] {str(e)[:80]}")
        return None


def compute_metrics(sm):
    m = {}
    # HogQL — engaged sessions (>=2 pageviews) + organic sessions, 7d
    m["engaged"] = _hog("SELECT count() FROM (SELECT properties.$session_id AS s, count() AS pv "
                        "FROM events WHERE event='$pageview' AND timestamp>now()-INTERVAL 7 DAY "
                        "GROUP BY s HAVING pv>=2)")
    m["organic"] = _hog("SELECT count(DISTINCT properties.$session_id) FROM events WHERE event='$pageview' "
                        "AND timestamp>now()-INTERVAL 7 DAY AND (properties.$referring_domain ILIKE '%google%' "
                        "OR properties.$referring_domain ILIKE '%bing%' OR properties.$referring_domain ILIKE '%duckduckgo%')")
    # Mongo funnel (7d)
    m["intent"] = (_count7(sm, "offmarket_qualification") + _count7(sm, "forsale_ladder_responses")
                   + _count7(sm, "price_alert_subscriptions"))
    m["enquiries"] = (_count7(sm, "report_review_bookings") + _count7(sm, "fb_leads")
                      + _count7(sm, "leads"))
    m["mini_sites"] = _count7(sm, "property_reports")
    m["appraisals"] = _count7(sm, "appraisal_pipeline")
    m["crm_growth"] = _count7(sm, "crm_contacts")
    m["rrb_total"] = sm["report_review_bookings"].estimated_document_count()
    m["timeframe_total"] = sm["offmarket_qualification"].estimated_document_count()
    # ad spend 7d
    try:
        docs = list(sm["ad_daily_metrics"].find({"date": {"$gte": (NOW - timedelta(days=7)).strftime("%Y-%m-%d")}}))
        m["ad_spend"] = round(sum(float(d.get("spend") or 0) for d in docs), 2)
    except Exception:
        m["ad_spend"] = None
    m["cost_per_engaged"] = (round(m["ad_spend"] / m["engaged"], 3)
                             if m.get("ad_spend") and m.get("engaged") else None)
    return m


def cmd_rollup(a):
    sm = get_mongo_client()["system_monitor"]
    m = compute_metrics(sm)
    print("metrics:", {k: v for k, v in m.items()})
    svc = _svc()
    # update Dashboard 'Latest value' (col L=12) + 'Latest date' (col M=13) by matching KPI name (col B)
    grid = svc.spreadsheets().values().get(spreadsheetId=SHEET, range="'KPI Dashboard'!A1:P60").execute().get("values", [])
    name_to_val = [
        ("Engaged sessions", m["engaged"]), ("Organic search sessions", m["organic"]),
        ("Intent signals / wk", m["intent"]), ("Inbound enquiries / wk", m["enquiries"]),
        ("Mini-sites generated / wk", m["mini_sites"]), ("Appraisals staged / wk", m["appraisals"]),
        ("Selling-timeframe answers", m["timeframe_total"]), ("Report-review bookings", m["rrb_total"]),
        ("Ad spend / wk", m["ad_spend"]), ("Cost per engaged session", m["cost_per_engaged"]),
    ]
    updates = []
    for i, row in enumerate(grid):
        b = row[1] if len(row) > 1 else ""
        for key, val in name_to_val:
            if val is not None and key.lower() in b.lower():
                r = i + 1
                updates.append({"range": f"'KPI Dashboard'!L{r}:M{r}", "values": [[val, TODAY]]})
    if updates:
        svc.spreadsheets().values().batchUpdate(spreadsheetId=SHEET,
            body={"valueInputOption": "USER_ENTERED", "data": updates}).execute()
    print(f"updated {len(updates)} Dashboard 'Latest' cells")
    # append Weekly Log row
    wl = [TODAY, m.get("organic") and (m["engaged"] or ""), m.get("engaged", ""), m.get("organic", ""), "",
          "", m.get("mini_sites", ""), m.get("intent", ""), m.get("enquiries", ""), m.get("rrb_total", ""),
          m.get("appraisals", ""), "", m.get("ad_spend", ""), m.get("cost_per_engaged", ""),
          "auto-rollup (kpi_rollup.py). engaged/organic via HogQL 7d; rest via Mongo 7d."]
    svc.spreadsheets().values().append(spreadsheetId=SHEET, range="'Weekly Log'!A1",
        valueInputOption="USER_ENTERED", insertDataOption="INSERT_ROWS", body={"values": [wl]}).execute()
    print("appended Weekly Log row for", TODAY)
    return 0


def cmd_impact(a):
    from collections import Counter
    sm = get_mongo_client()["system_monitor"]
    act = sm["samantha_actions"]
    d7 = list(act.find({"harvested_at": {"$gte": WK}}))
    d30 = list(act.find({"harvested_at": {"$gte": NOW - timedelta(days=30)}}))
    def ship_analysis(rows):
        c = Counter(r.get("category") for r in rows)
        ship = sum(c[x] for x in ("push", "code_edit", "ad", "git"))
        analysis = sum(c[x] for x in ("query", "read", "search", "shell", "note"))
        return ship, analysis, c
    s7, a7, c7 = ship_analysis(d7)
    s30, a30, c30 = ship_analysis(d30)
    # change ledger
    ch = list(sm["samantha_changes"].find({}))
    verdicts = Counter(x.get("latest_verdict") for x in ch)
    validated = verdicts.get("validated", 0) + verdicts.get("improved", 0)
    rolled = verdicts.get("rolled_back", 0) + verdicts.get("worse", 0)
    measured = sum(1 for x in ch if x.get("measurements"))
    # cost (her AI compute) last 30d from cost_tracking
    cost30 = 0.0
    try:
        for d in sm["cost_tracking"].find({"date": {"$gte": (NOW - timedelta(days=30)).strftime("%Y-%m-%d")}}):
            bc = d.get("by_category") or {}
            cost30 += float(bc.get("ai_compute", 0) or 0)
    except Exception:
        pass
    rows = [
        ["Samantha Impact", f"generated {TODAY} (AEST)"],
        ["", ""],
        ["ACTIONS (from samantha_actions)", ""],
        ["  actions last 7d", len(d7)],
        ["  actions last 30d", len(d30)],
        ["  ship:analysis 7d", f"{s7}:{a7} ({a7/max(s7,1):.1f}:1 analysis-heavy)"],
        ["  ship:analysis 30d", f"{s30}:{a30} ({a30/max(s30,1):.1f}:1)"],
        ["  top categories 30d", ", ".join(f"{k}:{v}" for k, v in c30.most_common(6))],
        ["", ""],
        ["CHANGES SHIPPED (change ledger)", ""],
        ["  total changes", len(ch)],
        ["  measured (loop closed)", f"{measured}/{len(ch)}"],
        ["  validated/improved", validated],
        ["  worse/rolled-back", rolled],
        ["  verdict mix", ", ".join(f"{k}:{v}" for k, v in verdicts.items() if k)],
        ["", ""],
        ["COST", ""],
        ["  AI-compute cost 30d (approx)", f"${cost30:.2f}"],
        ["", ""],
        ["READ", "Is she earning her keep? Ship rate + measured-loop % + validated changes vs cost. "
                 "A high analysis:ship ratio or low measured % = coach toward executing + closing loops."],
    ]
    svc = _svc()
    meta = svc.spreadsheets().get(spreadsheetId=SHEET).execute()
    titles = [s["properties"]["title"] for s in meta["sheets"]]
    if "Samantha Impact" not in titles:
        svc.spreadsheets().batchUpdate(spreadsheetId=SHEET, body={"requests": [
            {"addSheet": {"properties": {"title": "Samantha Impact", "tabColor": {"red": 0.5, "green": 0.3, "blue": 0.15}}}}]}).execute()
        meta = svc.spreadsheets().get(spreadsheetId=SHEET).execute()
    gid = {s["properties"]["title"]: s["properties"]["sheetId"] for s in meta["sheets"]}["Samantha Impact"]
    svc.spreadsheets().values().update(spreadsheetId=SHEET, range="'Samantha Impact'!A1",
        valueInputOption="USER_ENTERED", body={"values": rows}).execute()
    svc.spreadsheets().batchUpdate(spreadsheetId=SHEET, body={"requests": [
        {"repeatCell": {"range": {"sheetId": gid, "startRowIndex": 0, "endRowIndex": 1},
         "cell": {"userEnteredFormat": {"textFormat": {"bold": True, "fontSize": 12}}},
         "fields": "userEnteredFormat.textFormat"}},
        {"updateDimensionProperties": {"range": {"sheetId": gid, "dimension": "COLUMNS", "startIndex": 0, "endIndex": 1},
         "properties": {"pixelSize": 260}, "fields": "pixelSize"}},
        {"updateDimensionProperties": {"range": {"sheetId": gid, "dimension": "COLUMNS", "startIndex": 1, "endIndex": 2},
         "properties": {"pixelSize": 520}, "fields": "pixelSize"}},
        {"repeatCell": {"range": {"sheetId": gid}, "cell": {"userEnteredFormat": {"wrapStrategy": "WRAP", "verticalAlignment": "TOP"}},
         "fields": "userEnteredFormat(wrapStrategy,verticalAlignment)"}}]}).execute()
    print("Samantha Impact tab written")
    return 0


def main():
    ap = argparse.ArgumentParser()
    sub = ap.add_subparsers(dest="cmd", required=True)
    sub.add_parser("rollup").set_defaults(func=cmd_rollup)
    sub.add_parser("impact").set_defaults(func=cmd_impact)
    sub.add_parser("all").set_defaults(func=lambda a: (cmd_rollup(a), cmd_impact(a)) and 0)
    a = ap.parse_args()
    return a.func(a)


if __name__ == "__main__":
    raise SystemExit(main())
