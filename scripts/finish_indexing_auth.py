#!/usr/bin/env python3
"""
finish_indexing_auth.py — exchange a Google OAuth code for an indexing refresh token.

Why this exists
---------------
`google_indexing.py auth` builds its consent URL through `InstalledAppFlow`, which
attaches a PKCE `code_challenge` tied to that one in-memory flow object. So a URL
generated in one process cannot have its code redeemed by another — which makes it
impossible to hand someone a link out-of-band and let them finish separately.

This script closes that gap: it takes the code from a plain (non-PKCE) consent URL and
does the exchange itself, writing `GOOGLE_INDEXING_REFRESH_TOKEN` straight into `.env`.
The token is printed only as a masked prefix, so it never has to be pasted anywhere.

Root cause it fixes (2026-08-07, fix-history [INDEXING-SILENT-ZERO]):
`GOOGLE_INDEXING_REFRESH_TOKEN` was byte-identical to `GOOGLE_ADS_REFRESH_TOKEN` — a
Google Ads token carrying the `adwords` scope, used to request `indexing` +
`webmasters`. Google answers that with `invalid_scope` on every refresh, which is why
submit-new posted 0 URLs for 9 consecutive nights.

Usage
-----
    1. Open the consent URL (ask the agent, or run: this script --url)
    2. Approve as will@fieldsestate.com.au
    3. The browser lands on http://localhost/?code=XXXX and fails to load — that is
       expected. Copy the `code` value out of the address bar.
    4. python3 scripts/finish_indexing_auth.py --code "XXXX"
    5. python3 scripts/google_indexing.py submit-new     # retries the backlog
"""

from __future__ import annotations

import argparse
import os
import re
import sys
import urllib.parse
import urllib.request
from pathlib import Path

ENV_PATH = Path("/home/fields/Fields_Orchestrator/.env")
SCOPES = [
    "https://www.googleapis.com/auth/indexing",
    "https://www.googleapis.com/auth/webmasters",
]


def env_value(key: str) -> str:
    for line in ENV_PATH.read_text().splitlines():
        if line.startswith(f"{key}="):
            return line.split("=", 1)[1].strip().strip('"')
    return ""


def consent_url() -> str:
    params = {
        "response_type": "code",
        "client_id": env_value("GOOGLE_ADS_CLIENT_ID"),
        "redirect_uri": "http://localhost",
        "scope": " ".join(SCOPES),
        "access_type": "offline",
        # Without prompt=consent Google may return no refresh_token at all when the
        # user has already approved this client — which is the whole point here.
        "prompt": "consent",
    }
    return "https://accounts.google.com/o/oauth2/auth?" + urllib.parse.urlencode(params)


def exchange(code: str) -> str:
    body = urllib.parse.urlencode({
        "code": code,
        "client_id": env_value("GOOGLE_ADS_CLIENT_ID"),
        "client_secret": env_value("GOOGLE_ADS_CLIENT_SECRET"),
        "redirect_uri": "http://localhost",
        "grant_type": "authorization_code",
    }).encode()
    req = urllib.request.Request("https://oauth2.googleapis.com/token", data=body)
    import json
    with urllib.request.urlopen(req, timeout=60) as r:
        payload = json.load(r)
    token = payload.get("refresh_token")
    if not token:
        raise SystemExit(
            "No refresh_token in the response. Google omits it when the client was "
            "already consented — re-open the consent URL (it includes prompt=consent) "
            "and make sure you complete the approval screen.\n"
            f"Response keys: {sorted(payload)}"
        )
    granted = payload.get("scope", "")
    for s in SCOPES:
        if s not in granted:
            raise SystemExit(
                f"The granted scopes are missing {s}.\nGranted: {granted}\n"
                "Do not save this token — it would reproduce the invalid_scope failure."
            )
    return token


def write_env(token: str) -> None:
    text = ENV_PATH.read_text()
    line = f'GOOGLE_INDEXING_REFRESH_TOKEN="{token}"'
    if re.search(r"^GOOGLE_INDEXING_REFRESH_TOKEN=.*$", text, flags=re.M):
        text = re.sub(r"^GOOGLE_INDEXING_REFRESH_TOKEN=.*$", line, text, flags=re.M)
    else:
        text = text.rstrip("\n") + f"\n{line}\n"
    ENV_PATH.write_text(text)


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--url", action="store_true", help="print the consent URL and exit")
    ap.add_argument("--code", help="authorization code from the redirect URL")
    a = ap.parse_args()

    if a.url or not a.code:
        print("\nOpen this URL, approve as will@fieldsestate.com.au, then copy the `code`")
        print("parameter out of the http://localhost/?code=... address bar:\n")
        print(consent_url())
        print('\nThen run:  python3 scripts/finish_indexing_auth.py --code "PASTE_CODE"')
        if not a.code:
            return

    token = exchange(a.code.strip())
    if token == env_value("GOOGLE_ADS_REFRESH_TOKEN"):
        raise SystemExit("Refusing to save: that is the Google Ads token again, which is "
                         "the exact cause of the invalid_scope failure.")
    write_env(token)
    print(f"Saved GOOGLE_INDEXING_REFRESH_TOKEN ({token[:12]}…, {len(token)} chars) to .env")
    print("Scopes verified to include indexing + webmasters.")
    print("\nNext: python3 scripts/google_indexing.py submit-new")
    print("The 757 URLs dropped over the last 9 nights are still in the window — the "
          "watermark was never advanced past them — so they will be retried.")


if __name__ == "__main__":
    main()
