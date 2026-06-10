#!/usr/bin/env python3
"""
api_health_monitor.py — daily health/credit probe of every paid API resource,
reported into the "Main Site Health" Google Sheet (tab: "API Health").

WHY: provider outages (e.g. OpenAI quota exhaustion) were only discovered by
accident during unrelated work, after they had silently broken pipeline steps
for days. This gives a once-a-day, at-a-glance status of everything we pay for.

WHAT IT CAN AND CAN'T SEE: most providers no longer expose a dollar-balance to
an API key. So for each resource we run the CHEAPEST possible authenticated
call and classify the outcome:
    OK            — call succeeded, resource healthy
    OUT_OF_CREDIT — authenticated but quota/credit exhausted (the OpenAI case)
    AUTH_ERROR    — key/token invalid or revoked
    RATE_LIMITED  — throttled (transient)
    EXPIRING      — valid but a token expires soon (see detail)
    ERROR         — anything else (detail carries the message)
Where a real number exists (token expiry days, GitHub rate remaining) it goes
in the `metric` column.

Usage:
    python3 scripts/api_health_monitor.py            # probe + write to sheet
    python3 scripts/api_health_monitor.py --dry-run  # probe + print, no write
    python3 scripts/api_health_monitor.py --only openai,anthropic
"""
from __future__ import annotations

import argparse
import os
import sys
import traceback
from datetime import datetime, timezone, timedelta

import requests

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if REPO not in sys.path:
    sys.path.insert(0, REPO)

SHEET_ID = "1Oa7uZv0shzsxftDYJJ3WErxhr7OZMf_SOxRFawbSgTk"  # "Main Site Health"
TAB = "API Health"
TIMEOUT = 15
AEST = timezone(timedelta(hours=10))

# Status constants
OK, OUT_OF_CREDIT, AUTH_ERROR, RATE_LIMITED, EXPIRING, ERROR, SKIP = (
    "OK", "OUT_OF_CREDIT", "AUTH_ERROR", "RATE_LIMITED", "EXPIRING", "ERROR", "SKIP")
CRITICAL_STATES = {OUT_OF_CREDIT, AUTH_ERROR}


def _env(name: str) -> str:
    return (os.environ.get(name) or "").strip()


# --------------------------------------------------------------------------- #
# Probes — each returns (status, detail, metric). Never raises (wrapped below).
# --------------------------------------------------------------------------- #

def probe_openai(key_env: str):
    key = _env(key_env)
    if not key:
        return SKIP, f"{key_env} not set", ""
    r = requests.post(
        "https://api.openai.com/v1/chat/completions",
        headers={"Authorization": f"Bearer {key}"},
        json={"model": "gpt-4o-mini", "messages": [{"role": "user", "content": "ping"}], "max_tokens": 1},
        timeout=TIMEOUT)
    if r.status_code == 200:
        return OK, "gpt-4o-mini reachable", ""
    body = r.text.lower()
    if r.status_code == 429 and "insufficient_quota" in body:
        return OUT_OF_CREDIT, "insufficient_quota — top up billing", ""
    if r.status_code == 429:
        return RATE_LIMITED, "429 rate limited", ""
    if r.status_code == 401:
        return AUTH_ERROR, "401 invalid key", ""
    return ERROR, f"HTTP {r.status_code}: {r.text[:120]}", ""


def probe_anthropic(key_env: str):
    key = _env(key_env)
    if not key:
        return SKIP, f"{key_env} not set", ""
    r = requests.post(
        "https://api.anthropic.com/v1/messages",
        headers={"x-api-key": key, "anthropic-version": "2023-06-01", "content-type": "application/json"},
        json={"model": "claude-haiku-4-5-20251001", "max_tokens": 1,
              "messages": [{"role": "user", "content": "hi"}]},
        timeout=TIMEOUT)
    if r.status_code == 200:
        return OK, "claude-haiku reachable", ""
    body = r.text.lower()
    if "credit balance is too low" in body or "billing" in body:
        return OUT_OF_CREDIT, "credit balance too low — top up", ""
    if r.status_code == 401:
        return AUTH_ERROR, "401 invalid key", ""
    if r.status_code == 429:
        return RATE_LIMITED, "429 rate limited", ""
    return ERROR, f"HTTP {r.status_code}: {r.text[:120]}", ""


def probe_gemini():
    key = _env("GOOGLE_GEMINI_API_KEY")
    if not key:
        return SKIP, "GOOGLE_GEMINI_API_KEY not set", ""
    r = requests.get(f"https://generativelanguage.googleapis.com/v1beta/models?key={key}", timeout=TIMEOUT)
    if r.status_code == 200:
        return OK, "models endpoint reachable", ""
    if r.status_code in (400, 403):
        return AUTH_ERROR, f"{r.status_code}: key/billing issue", ""
    if r.status_code == 429:
        return RATE_LIMITED, "429 quota", ""
    return ERROR, f"HTTP {r.status_code}: {r.text[:120]}", ""


def probe_vision():
    key = _env("GOOGLE_VISION_SA_KEY")
    if not key or not os.path.exists(key):
        return SKIP, "GOOGLE_VISION_SA_KEY not a readable path", ""
    from google.oauth2 import service_account
    from google.auth.transport.requests import Request
    creds = service_account.Credentials.from_service_account_file(
        key, scopes=["https://www.googleapis.com/auth/cloud-platform"])
    creds.refresh(Request())
    # 1x1 white pixel PNG, label detection maxResults 1 — minimal billable unit.
    px = ("iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mNk"
          "+M9QDwADhgGAWjR9awAAAABJRU5ErkJggg==")
    r = requests.post(
        f"https://vision.googleapis.com/v1/images:annotate",
        headers={"Authorization": f"Bearer {creds.token}"},
        json={"requests": [{"image": {"content": px},
                            "features": [{"type": "LABEL_DETECTION", "maxResults": 1}]}]},
        timeout=TIMEOUT)
    if r.status_code == 200 and "error" not in r.text.lower()[:200]:
        return OK, "images:annotate reachable", ""
    if r.status_code == 403:
        return AUTH_ERROR, "403 — billing disabled or SA lacks access", ""
    return ERROR, f"HTTP {r.status_code}: {r.text[:120]}", ""


def probe_streetview():
    key = _env("GOOGLE_STREETVIEW_API_KEY")
    if not key:
        return SKIP, "not set", ""
    # Metadata endpoint is FREE and returns a status string.
    r = requests.get("https://maps.googleapis.com/maps/api/streetview/metadata",
                     params={"location": "-28.07,153.39", "key": key}, timeout=TIMEOUT)
    st = (r.json() or {}).get("status", "") if r.status_code == 200 else ""
    if st in ("OK", "ZERO_RESULTS", "NOT_FOUND"):
        return OK, f"metadata status={st}", ""
    if st == "REQUEST_DENIED":
        return AUTH_ERROR, "REQUEST_DENIED — key/billing", ""
    if st == "OVER_QUERY_LIMIT":
        return OUT_OF_CREDIT, "OVER_QUERY_LIMIT", ""
    return ERROR, f"HTTP {r.status_code} status={st}", ""


def probe_maps_static():
    key = _env("GOOGLE_MAPS_STATIC_API_KEY")
    if not key:
        return SKIP, "not set", ""
    r = requests.get("https://maps.googleapis.com/maps/api/staticmap",
                     params={"center": "-28.07,153.39", "zoom": "12", "size": "1x1", "key": key},
                     timeout=TIMEOUT)
    if r.status_code == 200 and r.headers.get("content-type", "").startswith("image"):
        return OK, "static tile served", ""
    if r.status_code == 403:
        return AUTH_ERROR, "403 — key/billing", ""
    return ERROR, f"HTTP {r.status_code}: {r.text[:100]}", ""


def probe_places():
    key = _env("GOOGLE_PLACES_API_KEY")
    if not key:
        return SKIP, "not set", ""
    r = requests.get("https://maps.googleapis.com/maps/api/place/findplacefromtext/json",
                     params={"input": "Robina QLD", "inputtype": "textquery", "fields": "place_id", "key": key},
                     timeout=TIMEOUT)
    st = (r.json() or {}).get("status", "") if r.status_code == 200 else ""
    if st in ("OK", "ZERO_RESULTS"):
        return OK, f"status={st}", ""
    if st == "REQUEST_DENIED":
        return AUTH_ERROR, "REQUEST_DENIED — key/billing", ""
    if st == "OVER_QUERY_LIMIT":
        return OUT_OF_CREDIT, "OVER_QUERY_LIMIT", ""
    return ERROR, f"HTTP {r.status_code} status={st}", ""


def probe_youtube():
    key = _env("YOUTUBE_API_KEY")
    if not key:
        return SKIP, "not set", ""
    r = requests.get("https://www.googleapis.com/youtube/v3/i18nLanguages",
                     params={"part": "snippet", "key": key}, timeout=TIMEOUT)
    if r.status_code == 200:
        return OK, "data api reachable", ""
    body = r.text.lower()
    if "quotaexceeded" in body or "dailylimitexceeded" in body:
        return OUT_OF_CREDIT, "quota exceeded (resets 00:00 PT)", ""
    if r.status_code in (400, 403):
        return AUTH_ERROR, f"{r.status_code}: key issue", ""
    return ERROR, f"HTTP {r.status_code}: {r.text[:100]}", ""


def probe_facebook():
    token = _env("FACEBOOK_ADS_TOKEN")
    ver = _env("FACEBOOK_API_VERSION") or "v21.0"
    if not token:
        return SKIP, "FACEBOOK_ADS_TOKEN not set", ""
    secret = _env("FACEBOOK_APP_SECRET")
    app_id = _env("FACEBOOK_APP_ID")
    # Prefer an app access token to inspect the user token; falls back to self.
    inspector = f"{app_id}|{secret}" if (app_id and secret) else token
    r = requests.get(f"https://graph.facebook.com/{ver}/debug_token",
                     params={"input_token": token, "access_token": inspector}, timeout=TIMEOUT)
    if r.status_code != 200:
        body = r.text.lower()
        if "expired" in body:
            # The token itself expired (and was inspecting itself).
            msg = (r.json() or {}).get("error", {}).get("message", "")
            return AUTH_ERROR, f"token expired — {msg[:80]}", "EXPIRED"
        if "session" in body or "validate" in body:
            return AUTH_ERROR, "token invalid — renew", ""
        return ERROR, f"HTTP {r.status_code}: {r.text[:100]}", ""
    data = (r.json() or {}).get("data", {})
    if not data.get("is_valid"):
        return AUTH_ERROR, "token is_valid=false", ""
    exp = data.get("expires_at", 0)
    if not exp:  # 0 = never expires
        return OK, "valid, no expiry", "no expiry"
    days = (datetime.fromtimestamp(exp, tz=timezone.utc) - datetime.now(timezone.utc)).days
    metric = f"{days}d to expiry"
    if days <= 7:
        return EXPIRING, f"token expires in {days}d — renew", metric
    return OK, "token valid", metric


def probe_google_ads():
    dev = _env("GOOGLE_ADS_DEVELOPER_TOKEN")
    refresh = _env("GOOGLE_ADS_REFRESH_TOKEN")
    secret = _env("GOOGLE_ADS_CLIENT_SECRET")
    cid = _env("GOOGLE_ADS_CLIENT_ID")
    if not (dev and refresh and secret):
        return SKIP, "ads creds incomplete", ""
    # Mint an access token from the refresh token.
    tr = requests.post("https://oauth2.googleapis.com/token", data={
        "client_id": cid, "client_secret": secret,
        "refresh_token": refresh, "grant_type": "refresh_token"}, timeout=TIMEOUT)
    if tr.status_code != 200:
        return AUTH_ERROR, f"oauth refresh {tr.status_code}: {tr.text[:80]}", ""
    at = tr.json().get("access_token")
    r = requests.get("https://googleads.googleapis.com/v20/customers:listAccessibleCustomers",
                     headers={"Authorization": f"Bearer {at}", "developer-token": dev}, timeout=TIMEOUT)
    if r.status_code == 200:
        n = len(r.json().get("resourceNames", []))
        return OK, "ads api reachable", f"{n} accounts"
    return ERROR, f"HTTP {r.status_code}: {r.text[:100]}", ""


def probe_brightdata():
    key = _env("BRIGHTDATA_API_KEY")
    if not key:
        return SKIP, "not set", ""
    # Account status endpoint; returns 200 when authed.
    r = requests.get("https://api.brightdata.com/status",
                     headers={"Authorization": f"Bearer {key}"}, timeout=TIMEOUT)
    if r.status_code == 200:
        return OK, "api authed", ""
    if r.status_code in (401, 403):
        return AUTH_ERROR, f"{r.status_code} invalid key", ""
    return ERROR, f"HTTP {r.status_code}: {r.text[:100]}", ""


def probe_mapbox():
    token = _env("MAPBOX_TOKEN")
    if not token:
        return SKIP, "not set", ""
    r = requests.get(f"https://api.mapbox.com/tokens/v2?access_token={token}", timeout=TIMEOUT)
    if r.status_code == 200:
        return OK, "token valid", ""
    if r.status_code in (401, 403):
        return AUTH_ERROR, f"{r.status_code} invalid token", ""
    return ERROR, f"HTTP {r.status_code}: {r.text[:100]}", ""


def probe_netlify():
    token = _env("NETLIFY_AUTH_TOKEN")
    if not token:
        return SKIP, "not set", ""
    r = requests.get("https://api.netlify.com/api/v1/user",
                     headers={"Authorization": f"Bearer {token}"}, timeout=TIMEOUT)
    if r.status_code == 200:
        return OK, f"user {r.json().get('email','?')}", ""
    if r.status_code == 401:
        return AUTH_ERROR, "401 invalid token", ""
    return ERROR, f"HTTP {r.status_code}: {r.text[:100]}", ""


def probe_posthog():
    key = _env("POSTHOG_PERSONAL_API_KEY")
    if not key:
        return SKIP, "not set", ""
    r = requests.get("https://us.posthog.com/api/projects/",
                     headers={"Authorization": f"Bearer {key}"}, timeout=TIMEOUT)
    if r.status_code == 200:
        return OK, "projects api reachable", ""
    if r.status_code in (401, 403):
        return AUTH_ERROR, f"{r.status_code} invalid key", ""
    return ERROR, f"HTTP {r.status_code}: {r.text[:100]}", ""


def probe_github():
    token = _env("GITHUB_TOKEN") or _env("GH_TOKEN")
    if not token:
        return SKIP, "not set", ""
    r = requests.get("https://api.github.com/rate_limit",
                     headers={"Authorization": f"Bearer {token}"}, timeout=TIMEOUT)
    if r.status_code == 200:
        core = r.json().get("resources", {}).get("core", {})
        return OK, "authed", f"{core.get('remaining','?')}/{core.get('limit','?')} core left"
    if r.status_code == 401:
        return AUTH_ERROR, "401 invalid token", ""
    return ERROR, f"HTTP {r.status_code}: {r.text[:100]}", ""


def probe_telegram():
    token = _env("TELEGRAM_BOT_TOKEN")
    if not token:
        return SKIP, "not set", ""
    r = requests.get(f"https://api.telegram.org/bot{token}/getMe", timeout=TIMEOUT)
    if r.status_code == 200 and r.json().get("ok"):
        return OK, f"@{r.json()['result'].get('username','?')}", "free"
    return AUTH_ERROR, f"HTTP {r.status_code}: {r.text[:80]}", ""


def probe_cosmos():
    conn = _env("COSMOS_CONNECTION_STRING")
    if not conn:
        return SKIP, "not set", ""
    from pymongo import MongoClient
    c = MongoClient(conn, serverSelectionTimeoutMS=8000)
    c.admin.command("ping")
    c.close()
    return OK, "ping ok", ""


def probe_azure_storage():
    conn = _env("AZURE_STORAGE_CONNECTION_STRING")
    if not conn:
        return SKIP, "not set", ""
    try:
        from azure.storage.blob import BlobServiceClient
    except ImportError:
        return SKIP, "azure sdk not installed", ""
    svc = BlobServiceClient.from_connection_string(conn)
    next(svc.list_containers(results_per_page=1).by_page(), None)
    return OK, "containers listable", ""


# (key, category, fn) — order = sheet order. Category groups the dashboard.
PROBES = [
    ("OpenAI (primary)", "LLM/Vision", lambda: probe_openai("OPENAI_API_KEY")),
    ("OpenAI (codex)", "LLM/Vision", lambda: probe_openai("OPENAI_CODEX_API_KEY")),
    ("Anthropic (Opus)", "LLM/Vision", lambda: probe_anthropic("ANTHROPIC_API_KEY")),
    ("Anthropic (Sonnet)", "LLM/Vision", lambda: probe_anthropic("ANTHROPIC_SONNET_API_KEY")),
    ("Google Gemini", "LLM/Vision", probe_gemini),
    ("Google Vision", "LLM/Vision", probe_vision),
    ("Google Street View", "Maps/Geo", probe_streetview),
    ("Google Maps Static", "Maps/Geo", probe_maps_static),
    ("Google Places", "Maps/Geo", probe_places),
    ("Mapbox", "Maps/Geo", probe_mapbox),
    ("YouTube Data API", "Content", probe_youtube),
    ("Facebook Ads token", "Ads", probe_facebook),
    ("Google Ads", "Ads", probe_google_ads),
    ("Bright Data", "Scraping", probe_brightdata),
    ("Netlify", "Infra", probe_netlify),
    ("PostHog", "Infra", probe_posthog),
    ("GitHub", "Infra", probe_github),
    ("Telegram bot", "Infra", probe_telegram),
    ("Cosmos DB", "Infra", probe_cosmos),
    # Azure Blob intentionally omitted — storage decommissioned after the GCS
    # migration; the account is disabled by design (see gcs_blob_backup notes).
]


def run_probes(only=None):
    rows = []
    for name, cat, fn in PROBES:
        if only and not any(o.lower() in name.lower() for o in only):
            continue
        try:
            status, detail, metric = fn()
        except Exception as e:
            status, detail, metric = ERROR, f"{type(e).__name__}: {str(e)[:110]}", ""
        rows.append([cat, name, status, metric, detail])
        print(f"  {status:14} {name:24} {metric:16} {detail[:70]}")
    return rows


# --------------------------------------------------------------------------- #
# Sheet write
# --------------------------------------------------------------------------- #

def _sheets_service():
    from google.oauth2 import service_account
    from googleapiclient.discovery import build
    creds = service_account.Credentials.from_service_account_file(
        _env("GOOGLE_VISION_SA_KEY"), scopes=["https://www.googleapis.com/auth/spreadsheets"])
    return build("sheets", "v4", credentials=creds, cache_discovery=False)


def write_to_sheet(rows):
    svc = _sheets_service()
    # Ensure the tab exists.
    meta = svc.spreadsheets().get(spreadsheetId=SHEET_ID).execute()
    tabs = [s["properties"]["title"] for s in meta.get("sheets", [])]
    if TAB not in tabs:
        svc.spreadsheets().batchUpdate(spreadsheetId=SHEET_ID, body={
            "requests": [{"addSheet": {"properties": {"title": TAB}}}]}).execute()
    now = datetime.now(AEST).strftime("%Y-%m-%d %H:%M AEST")
    n_crit = sum(1 for r in rows if r[2] in CRITICAL_STATES)
    n_warn = sum(1 for r in rows if r[2] in (EXPIRING, ERROR, RATE_LIMITED))
    summary = "ALL OK" if (n_crit == 0 and n_warn == 0) else f"{n_crit} critical, {n_warn} warnings"
    header = [
        [f"API Resource Health — last checked {now}", "", "", "", ""],
        [f"Summary: {summary}", "", "", "", ""],
        ["Category", "Resource", "Status", "Metric", "Detail"],
    ]
    body = header + rows
    # Clear old contents then write current snapshot.
    svc.spreadsheets().values().clear(spreadsheetId=SHEET_ID, range=f"'{TAB}'!A1:E100").execute()
    svc.spreadsheets().values().update(
        spreadsheetId=SHEET_ID, range=f"'{TAB}'!A1",
        valueInputOption="RAW", body={"values": body}).execute()
    return summary, n_crit, n_warn


def telegram_alert(rows, summary):
    token = _env("TELEGRAM_BOT_TOKEN")
    chat = _env("TELEGRAM_CHAT_ID") or _env("CEO_TELEGRAM_CHAT_ID") or _env("BUILDER_TELEGRAM_CHAT_ID")
    bad = [r for r in rows if r[2] in CRITICAL_STATES or r[2] == EXPIRING]
    if not (token and chat and bad):
        return False
    lines = ["⚠️ *API resource alert*", f"_{summary}_", ""]
    lines += [f"• *{r[1]}*: {r[2]} — {r[4]}" for r in bad]
    requests.post(f"https://api.telegram.org/bot{token}/sendMessage",
                  json={"chat_id": chat, "text": "\n".join(lines), "parse_mode": "Markdown"}, timeout=TIMEOUT)
    return True


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--dry-run", action="store_true", help="probe + print, do not write to sheet")
    ap.add_argument("--only", help="comma-separated name substrings to probe (e.g. openai,anthropic)")
    ap.add_argument("--no-alert", action="store_true", help="skip Telegram alert")
    args = ap.parse_args()

    only = [s.strip() for s in args.only.split(",")] if args.only else None
    print(f"=== API health probe — {datetime.now(AEST):%Y-%m-%d %H:%M AEST} ===")
    rows = run_probes(only)

    if args.dry_run:
        print("\n(dry-run — sheet not written)")
        return 0
    try:
        summary, n_crit, n_warn = write_to_sheet(rows)
        print(f"\nwrote {len(rows)} rows to '{TAB}' — {summary}")
        if not args.no_alert and (n_crit or any(r[2] == EXPIRING for r in rows)):
            if telegram_alert(rows, summary):
                print("telegram alert sent")
    except Exception:
        traceback.print_exc()
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
