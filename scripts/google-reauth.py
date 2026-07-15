#!/usr/bin/env python3
"""
Google OAuth2 Re-Authentication — generates a new refresh token covering all Google scopes.

Usage:
  python3 scripts/google-reauth.py

This produces a single refresh token that works for:
  - Google Ads API
  - Google Search Console (webmasters.readonly)
  - Google Indexing API

After authorization, it updates .env with the new refresh token(s).
"""

import os
import sys
import urllib.parse
from datetime import datetime

from dotenv import load_dotenv

load_dotenv("/home/fields/Fields_Orchestrator/.env")

SCOPES = [
    "https://www.googleapis.com/auth/adwords",
    "https://www.googleapis.com/auth/webmasters.readonly",
    "https://www.googleapis.com/auth/indexing",
]

REDIRECT_URI = "http://localhost"


def main():
    import requests as req

    client_id = os.environ.get("GOOGLE_ADS_CLIENT_ID")
    client_secret = os.environ.get("GOOGLE_ADS_CLIENT_SECRET")

    if not client_id or not client_secret:
        print("ERROR: Set GOOGLE_ADS_CLIENT_ID and GOOGLE_ADS_CLIENT_SECRET in .env first.")
        sys.exit(1)

    # Build auth URL manually with explicit redirect_uri
    params = {
        "client_id": client_id,
        "redirect_uri": REDIRECT_URI,
        "response_type": "code",
        "scope": " ".join(SCOPES),
        "access_type": "offline",
        "prompt": "consent",
    }
    auth_url = "https://accounts.google.com/o/oauth2/auth?" + urllib.parse.urlencode(params)

    print("\n" + "=" * 60)
    print("GOOGLE RE-AUTHENTICATION — ALL SCOPES")
    print("=" * 60)
    print(f"\nScopes: {', '.join(SCOPES)}")
    print("\n1. Open this URL in your browser:\n")
    print(auth_url)
    print("\n2. Sign in with will.simpson@blueoceans.com.au")
    print("3. Grant access to 'Fields Estate Ads' app")
    print("4. You'll be redirected to http://localhost/?code=XXXXX&scope=...")
    print("   The page won't load (that's normal). Copy the FULL URL from the address bar.")
    print()

    raw = input("Paste the full redirect URL (or just the code): ").strip()

    if not raw:
        print("No code provided. Aborting.")
        sys.exit(1)

    # Extract code from URL if they pasted the full redirect URL
    if "code=" in raw:
        parsed = urllib.parse.urlparse(raw)
        params = urllib.parse.parse_qs(parsed.query)
        code = params.get("code", [raw])[0]
    else:
        code = raw

    print(f"\nExchanging authorization code for refresh token...")

    # Exchange code for tokens manually
    token_resp = req.post(
        "https://oauth2.googleapis.com/token",
        data={
            "code": code,
            "client_id": client_id,
            "client_secret": client_secret,
            "redirect_uri": REDIRECT_URI,
            "grant_type": "authorization_code",
        },
    )

    if token_resp.status_code != 200:
        print(f"ERROR: Token exchange failed: {token_resp.text}")
        sys.exit(1)

    token_data = token_resp.json()
    refresh_token = token_data.get("refresh_token")

    if not refresh_token:
        print(f"ERROR: No refresh token in response. Response: {token_data}")
        sys.exit(1)

    print(f"\n✅ New refresh token obtained!")
    print(f"   Token: {refresh_token[:20]}...{refresh_token[-10:]}")

    # Update .env — replace existing tokens
    env_path = "/home/fields/Fields_Orchestrator/.env"
    with open(env_path) as f:
        lines = f.readlines()

    updated_keys = set()
    new_lines = []
    for line in lines:
        stripped = line.strip()
        if stripped.startswith("GOOGLE_ADS_REFRESH_TOKEN="):
            new_lines.append(f"GOOGLE_ADS_REFRESH_TOKEN={refresh_token}\n")
            updated_keys.add("GOOGLE_ADS_REFRESH_TOKEN")
        elif stripped.startswith("GOOGLE_INDEXING_REFRESH_TOKEN="):
            new_lines.append(f"GOOGLE_INDEXING_REFRESH_TOKEN={refresh_token}\n")
            updated_keys.add("GOOGLE_INDEXING_REFRESH_TOKEN")
        else:
            new_lines.append(line)

    # Add any missing keys
    timestamp = datetime.now().strftime("%Y-%m-%d")
    if "GOOGLE_ADS_REFRESH_TOKEN" not in updated_keys:
        new_lines.append(f"\n# Google Ads refresh token (updated {timestamp})\n")
        new_lines.append(f"GOOGLE_ADS_REFRESH_TOKEN={refresh_token}\n")
    if "GOOGLE_INDEXING_REFRESH_TOKEN" not in updated_keys:
        new_lines.append(f"\n# Google Indexing/GSC refresh token (updated {timestamp})\n")
        new_lines.append(f"GOOGLE_INDEXING_REFRESH_TOKEN={refresh_token}\n")

    with open(env_path, "w") as f:
        f.writelines(new_lines)

    print(f"\n✅ Updated {env_path}:")
    print(f"   - GOOGLE_ADS_REFRESH_TOKEN")
    print(f"   - GOOGLE_INDEXING_REFRESH_TOKEN")
    print(f"\nBoth now use the same token with all scopes.")
    print(f"\nTest with:")
    print(f"  source /home/fields/venv/bin/activate && set -a && source .env && set +a")
    print(f"  python3 scripts/google_ads_manager.py test")
    print(f"  python3 scripts/ceo-query-broker.py search-console --days 7")


if __name__ == "__main__":
    main()
