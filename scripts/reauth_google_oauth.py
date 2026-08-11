#!/usr/bin/env python3
"""
Re-authorise the shared Google OAuth token (Drive + Sheets + Ads + Indexing + Search Console).

ONE token backs FIVE integrations. When it dies, all of these break together:
  - gdrive MCP server (mcp-servers/gdrive/index.mjs)
  - from_will.py / running_doc.py / drive_comment.py
  - google-ads-metrics-collector.py
  - google_indexing.py  (Search Console + Indexing API)
  - drive_brain_ingest.py uploads

The app is in Testing mode in Google Cloud, so Google revokes the refresh token
every 7 days. The permanent fix is to publish the OAuth consent screen
(Google Cloud Console -> APIs & Services -> OAuth consent screen -> Publish app).
Until then this script is the weekly workaround.

Usage:
    python3 scripts/reauth_google_oauth.py

Prints a consent URL, waits while you approve it in a browser, then takes the
failed http://localhost/?code=... redirect, exchanges it, writes the new refresh
token to all three places, and verifies each integration independently.

All five scopes are requested together. Do not request a subset: google_indexing.py
pins the FULL `webmasters` scope (not `.readonly`), and a mismatch makes the refresh
itself fail with invalid_scope.
"""
import json
import os
import re
import subprocess
import sys
import urllib.parse
import urllib.request
from datetime import datetime, timezone

KEYS = "/home/fields/.gdrive-oauth.keys.json"
CREDS = "/home/fields/.gdrive-server-credentials.json"
ENV = "/home/fields/Fields_Orchestrator/.env"

SCOPES = [
    "https://www.googleapis.com/auth/drive",
    "https://www.googleapis.com/auth/spreadsheets",
    "https://www.googleapis.com/auth/adwords",
    "https://www.googleapis.com/auth/indexing",
    "https://www.googleapis.com/auth/webmasters",  # FULL, not .readonly
]
ENV_KEYS = ("GOOGLE_ADS_REFRESH_TOKEN", "GOOGLE_INDEXING_REFRESH_TOKEN")


def load_client():
    with open(KEYS) as fh:
        return json.load(fh)["installed"]


def consent_url(client):
    q = urllib.parse.urlencode({
        "client_id": client["client_id"],
        "redirect_uri": "http://localhost",
        "response_type": "code",
        "scope": " ".join(SCOPES),
        "access_type": "offline",
        "prompt": "consent",
    })
    return f"{client['auth_uri']}?{q}"


def extract_code(raw):
    raw = raw.strip()
    if not raw:
        return None
    if raw.startswith("http"):
        qs = urllib.parse.parse_qs(urllib.parse.urlparse(raw).query)
        if "error" in qs:
            print(f"\n  Google returned an error: {qs['error'][0]}")
            return None
        got = qs.get("code", [None])[0]
        return urllib.parse.unquote(got) if got else None
    # bare code pasted
    m = re.search(r"[?&]code=([^&\s]+)", raw)
    return urllib.parse.unquote(m.group(1)) if m else raw


def exchange(client, code):
    body = urllib.parse.urlencode({
        "code": code,
        "client_id": client["client_id"],
        "client_secret": client["client_secret"],
        "redirect_uri": "http://localhost",
        "grant_type": "authorization_code",
    }).encode()
    req = urllib.request.Request(client["token_uri"], data=body,
                                 headers={"Content-Type": "application/x-www-form-urlencoded"})
    try:
        with urllib.request.urlopen(req, timeout=30) as r:
            return json.load(r)
    except urllib.error.HTTPError as e:
        detail = e.read().decode(errors="replace")
        print(f"\n  Token exchange failed ({e.code}): {detail[:400]}")
        if "invalid_grant" in detail:
            print("  -> The code is single-use and expires in ~60s. Re-run and be quick.")
        if "invalid_scope" in detail:
            print("  -> A scope was not granted. Approve ALL FIVE on the consent screen.")
        return None


def write_creds(tok):
    prev = {}
    if os.path.exists(CREDS):
        with open(CREDS) as fh:
            prev = json.load(fh)
        os.replace(CREDS, CREDS + ".bak")
    out = {
        "access_token": tok["access_token"],
        "refresh_token": tok.get("refresh_token") or prev.get("refresh_token"),
        "scope": tok.get("scope", " ".join(SCOPES)),
        "token_type": tok.get("token_type", "Bearer"),
        "expiry_date": int(datetime.now(timezone.utc).timestamp() * 1000) + tok["expires_in"] * 1000,
        "refresh_token_expires_in": tok.get("refresh_token_expires_in"),
    }
    with open(CREDS, "w") as fh:
        json.dump(out, fh, indent=2)
    os.chmod(CREDS, 0o600)
    return out["refresh_token"]


def write_env(refresh):
    """Rewrite the two .env keys in place. Never reformats or reorders the rest."""
    with open(ENV) as fh:
        lines = fh.readlines()
    seen = set()
    for i, ln in enumerate(lines):
        for k in ENV_KEYS:
            if ln.startswith(k + "="):
                lines[i] = f"{k}={refresh}\n"
                seen.add(k)
    missing = [k for k in ENV_KEYS if k not in seen]
    if missing:
        print(f"  WARNING: these .env keys were not found and were NOT written: {missing}")
    with open(ENV + ".tmp", "w") as fh:
        fh.writelines(lines)
    os.replace(ENV + ".tmp", ENV)
    return sorted(seen)


def verify():
    """Each integration checked independently - one success does not imply the others."""
    checks = [
        ("Drive  ", ["python3", "scripts/samantha/from_will.py", "--peek"]),
        ("Indexing", ["python3", "scripts/google_indexing.py", "status"]),
        ("Ads    ", ["python3", "scripts/google-ads-metrics-collector.py", "--dry-run"]),
    ]
    print("\nVerifying each integration separately:")
    ok = True
    for name, cmd in checks:
        if not os.path.exists(cmd[1]):
            print(f"  {name} SKIP  ({cmd[1]} not found)")
            continue
        try:
            p = subprocess.run(cmd, cwd="/home/fields/Fields_Orchestrator",
                               capture_output=True, text=True, timeout=180)
            tail = (p.stderr or p.stdout or "").strip().splitlines()
            tail = tail[-1][:150] if tail else ""
            if p.returncode == 0:
                print(f"  {name} OK")
            else:
                ok = False
                print(f"  {name} FAIL (rc={p.returncode}) {tail}")
        except subprocess.TimeoutExpired:
            ok = False
            print(f"  {name} TIMEOUT")
        except Exception as e:
            ok = False
            print(f"  {name} ERROR {str(e)[:120]}")
    return ok


def main():
    client = load_client()

    print("=" * 72)
    print("GOOGLE OAUTH RE-AUTH  (Drive + Sheets + Ads + Indexing + Search Console)")
    print("=" * 72)
    print("\n1. Open this URL in your browser and approve ALL FIVE permissions:\n")
    print(consent_url(client))
    print("\n2. The browser will fail to load a page at http://localhost/?code=...")
    print("   That failure is expected. Copy the FULL URL out of the address bar.")
    print("   (The code is single-use and expires in about 60 seconds.)\n")

    try:
        raw = input("3. Paste the http://localhost/?code=... URL here: ")
    except (EOFError, KeyboardInterrupt):
        print("\nAborted - nothing was changed.")
        return 1

    code = extract_code(raw)
    if not code:
        print("\nNo authorization code found in that input. Nothing was changed.")
        return 1

    tok = exchange(client, code)
    if not tok:
        print("\nNothing was changed.")
        return 1

    refresh = write_creds(tok)
    if not refresh:
        print("\nNo refresh_token returned and none on file. Re-run - the consent URL "
              "must include prompt=consent (it does) and the app must not already be "
              "authorised without offline access.")
        return 1

    wrote = write_env(refresh)
    days = (tok.get("refresh_token_expires_in") or 0) / 86400

    print(f"\nWrote refresh token to:")
    print(f"  {CREDS}  (previous backed up to {CREDS}.bak)")
    for k in wrote:
        print(f"  {ENV} -> {k}")
    if days:
        print(f"\nThis refresh token expires in {days:.1f} days "
              f"(Testing mode). Publishing the OAuth consent screen removes the limit.")

    all_ok = verify()
    print("\n" + ("All checks passed." if all_ok else
                  "One or more checks FAILED - fix before assuming the token works."))
    return 0 if all_ok else 2


if __name__ == "__main__":
    sys.exit(main())
