#!/usr/bin/env python3
"""
Google Drive MCP Re-Authentication.

Refreshes /home/fields/.gdrive-server-credentials.json after the refresh
token is revoked or expires (`invalid_grant`).

Usage:
  python3 scripts/gdrive-reauth.py
"""

import json
import sys
import urllib.parse
from pathlib import Path

import requests

OAUTH_KEYS = Path("/home/fields/.gdrive-oauth.keys.json")
CREDENTIALS = Path("/home/fields/.gdrive-server-credentials.json")
REDIRECT_URI = "http://localhost"
SCOPE = "https://www.googleapis.com/auth/drive"


def main():
    if not OAUTH_KEYS.exists():
        sys.exit(f"OAuth client file not found: {OAUTH_KEYS}")

    keys = json.loads(OAUTH_KEYS.read_text())
    block = keys.get("installed") or keys.get("web")
    client_id = block["client_id"]
    client_secret = block["client_secret"]

    params = {
        "client_id": client_id,
        "redirect_uri": REDIRECT_URI,
        "response_type": "code",
        "scope": SCOPE,
        "access_type": "offline",
        "prompt": "consent",
    }
    auth_url = "https://accounts.google.com/o/oauth2/auth?" + urllib.parse.urlencode(params)

    print()
    print("=" * 60)
    print("GOOGLE DRIVE RE-AUTHENTICATION")
    print("=" * 60)
    print()
    print("1. Open this URL in a browser logged in as will.simpson@blueoceans.com.au:")
    print()
    print(auth_url)
    print()
    print("2. Approve access. You'll be redirected to http://localhost/?code=...")
    print("   (page won't load — that's expected). Copy the FULL URL from the address bar.")
    print()

    raw = input("Paste the full redirect URL (or just the code): ").strip()
    if not raw:
        sys.exit("No code provided.")

    if "code=" in raw:
        parsed = urllib.parse.urlparse(raw)
        code = urllib.parse.parse_qs(parsed.query)["code"][0]
    else:
        code = raw

    resp = requests.post(
        "https://oauth2.googleapis.com/token",
        data={
            "code": code,
            "client_id": client_id,
            "client_secret": client_secret,
            "redirect_uri": REDIRECT_URI,
            "grant_type": "authorization_code",
        },
        timeout=30,
    )

    if resp.status_code != 200:
        sys.exit(f"Token exchange failed: {resp.status_code} {resp.text}")

    tokens = resp.json()
    if "refresh_token" not in tokens:
        sys.exit("No refresh_token in response. Re-run and ensure prompt=consent (this script does).")

    CREDENTIALS.write_text(json.dumps(tokens, indent=2))
    CREDENTIALS.chmod(0o600)

    print()
    print(f"Wrote new credentials to {CREDENTIALS}")
    print(f"Scopes: {tokens.get('scope')}")
    print("Now restart any running MCP client (or it'll pick up on next call).")


if __name__ == "__main__":
    main()
