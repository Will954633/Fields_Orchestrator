"""
propradar_client.py — thin, rate-limit-aware client for the PropRadar Data API.

PropRadar sits behind Cloudflare: the default urllib User-Agent gets 403 error 1010,
so a browser UA header is mandatory (same class of fix as the ABS API UA requirement).

Key is read from the shared secrets file (never printed/committed). Base + endpoints
per docs: https://propradar.com.au/developers/docs
"""
from __future__ import annotations

import json
import os
import re
import time
import urllib.error
import urllib.parse
import urllib.request

KEYFILE = os.environ.get(
    "PROPRADAR_KEYFILE",
    "/home/fields/Fields_Orchestrator/00_Run_Commands/gh-token-29Mar.txt",
)
BASE = "https://api.propradar.com.au/v1"

_HEADERS = {
    "Accept": "application/json",
    "Accept-Language": "en-AU,en;q=0.9",
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
        "(KHTML, like Gecko) Chrome/125.0.0.0 Safari/537.36"
    ),
}


def _load_key() -> str:
    with open(KEYFILE) as f:
        m = re.search(r"pr_live_[A-Za-z0-9]+", f.read())
    if not m:
        raise RuntimeError(f"PropRadar key (pr_live_...) not found in {KEYFILE}")
    return m.group(0)


_KEY = _load_key()


def call(path: str, params: dict | None = None, max_retries: int = 4):
    """GET {BASE}{path}. Returns (json, headers_lower). Retries 429/5xx with backoff."""
    url = f"{BASE}{path}"
    if params:
        url += "?" + urllib.parse.urlencode(params)
    headers = {**_HEADERS, "X-API-Key": _KEY}
    for attempt in range(max_retries):
        try:
            req = urllib.request.Request(url, headers=headers)
            with urllib.request.urlopen(req, timeout=40) as r:
                hdr = {k.lower(): v for k, v in r.headers.items()}
                return json.load(r), hdr
        except urllib.error.HTTPError as e:
            body = e.read().decode(errors="replace")[:300]
            if e.code in (429,) or 500 <= e.code < 600:
                wait = 1.5 * (2 ** attempt)
                print(f"  [propradar] {e.code} retry in {wait:.1f}s :: {body}")
                time.sleep(wait)
                continue
            raise RuntimeError(f"PropRadar HTTP {e.code}: {body}")
        except (urllib.error.URLError, TimeoutError) as e:
            wait = 1.5 * (2 ** attempt)
            print(f"  [propradar] network error {e}; retry in {wait:.1f}s")
            time.sleep(wait)
    raise RuntimeError(f"PropRadar call failed after {max_retries} retries: {path}")


def fetch_all_sold(state: str, suburb: str, months: int = 60,
                   property_type: str | None = None, sleep: float = 0.55,
                   max_pages: int = 300):
    """
    Walk /suburbs/{state}/{suburb}/sold via cursor pagination.
    Returns (records, calls_made, last_headers).
    """
    base_params = {"months": months, "limit": 20}
    if property_type:
        base_params["property_type"] = property_type
    path = f"/suburbs/{state}/{urllib.parse.quote(suburb)}/sold"
    records, calls, cursor, last_hdr = [], 0, None, {}
    while calls < max_pages:
        params = dict(base_params)
        if cursor:
            params["cursor"] = cursor
        data, hdr = call(path, params)
        calls += 1
        last_hdr = hdr
        rows = data.get("sold") or []
        records.extend(rows)
        cursor = (data.get("pagination") or {}).get("next_cursor")
        if not cursor or not rows:
            break
        time.sleep(sleep)
    return records, calls, last_hdr
