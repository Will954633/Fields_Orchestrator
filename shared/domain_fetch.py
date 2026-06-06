#!/usr/bin/env python3
"""
Domain.com.au fetch helper — routes requests through Bright Data Web Unlocker
to bypass Akamai bot management.

Background: starting around 2026-05-11 the VM's GCP IP (and the backup scraper VM's
IP) were intermittently flagged by Akamai. Direct curl_cffi requests get HTTP 403
on `/sale/*`, `/sold-listings/*`, and individual listing URLs. Image CDNs
(`*.domainstatic.com.au`, `bucket-api.domain.com.au`) are NOT behind Akamai and
remain fetchable directly.

Usage:
    from shared.domain_fetch import fetch_html, fetch_with_status

    html = fetch_html('https://www.domain.com.au/sale/robina-qld-4226/')
    if html:
        ...

    # Need the original status code (e.g. for redirect-based withdrawn detection):
    result = fetch_with_status('https://www.domain.com.au/some-listing-12345')
    if result:
        status, html, final_url = result['status'], result['body'], result['url']

Env vars required:
    BRIGHTDATA_API_KEY  — Bright Data API token
    BRIGHTDATA_ZONE     — zone name (default: 'web_unlocker2')

Falls back to direct curl_cffi when BRIGHTDATA_API_KEY is unset (useful for
local testing or when the block lifts).
"""

import os
import re
import time
from typing import Optional, Dict

from curl_cffi import requests as cffi_requests

BRIGHTDATA_ENDPOINT = 'https://api.brightdata.com/request'

# Recover the resolved URL from the page itself — Bright Data's raw mode doesn't
# expose the final (post-redirect) URL, and its json mode returns url=null. Domain's
# canonical/og:url tag carries the resolved address, including the `/property-profile/`
# slug it redirects withdrawn listings to.
_CANONICAL_RE = re.compile(r'<link[^>]+rel=["\']canonical["\'][^>]+href=["\']([^"\']+)["\']', re.I)
_OG_URL_RE = re.compile(r'<meta[^>]+property=["\']og:url["\'][^>]+content=["\']([^"\']+)["\']', re.I)

DEFAULT_TIMEOUT = 90
DEFAULT_RETRIES = 3


def _api_key() -> Optional[str]:
    """Read env at call time (not import time) so callers can load_env() after import."""
    return os.environ.get('BRIGHTDATA_API_KEY')


def _zone() -> str:
    return os.environ.get('BRIGHTDATA_ZONE', 'web_unlocker2')


# Back-compat module attributes for callers that introspect them
BRIGHTDATA_API_KEY = property(lambda self: _api_key())  # type: ignore
BRIGHTDATA_ZONE = property(lambda self: _zone())  # type: ignore


def _post_unlocker(url: str, return_json: bool = False, timeout: int = DEFAULT_TIMEOUT) -> Optional[Dict]:
    """POST to Bright Data Web Unlocker. Returns dict with 'body' (always) plus
    'status' and 'url' when return_json=True. None on failure.

    Always uses Bright Data's `raw` format — the `json` envelope is markedly
    flakier for Domain (frequent 502 `min_size` empties) and returns url=null,
    which broke `/property-profile/` redirect detection. We take the upstream HTTP
    status from the `x-brd-status-code` header and recover the resolved URL from the
    page's canonical/og:url tag.
    """
    api_key = _api_key()
    if not api_key:
        return None

    payload = {'zone': _zone(), 'url': url, 'format': 'raw'}
    headers = {
        'Content-Type': 'application/json',
        'Authorization': f'Bearer {api_key}',
    }
    try:
        resp = cffi_requests.post(BRIGHTDATA_ENDPOINT, headers=headers, json=payload, timeout=timeout)
        if resp.status_code != 200:
            return None

        brd_status_raw = resp.headers.get('x-brd-status-code', '')
        brd_status = int(brd_status_raw) if brd_status_raw.isdigit() else 0
        body = resp.text or ''

        # Unlocker failure (min_size 502, challenge, empty) — signal retry. A real
        # Domain 404 still returns a full body, so size is a safe discriminator.
        if brd_status in (502, 0) and len(body) < 200:
            return None
        if not return_json and len(body) < 200:
            return None
        if not return_json:
            return {'body': body}

        m = _CANONICAL_RE.search(body) or _OG_URL_RE.search(body)
        final_url = m.group(1) if m else url
        return {
            'status': brd_status or 200,
            'body': body,
            'url': final_url,
            'headers': dict(resp.headers),
        }
    except Exception:
        return None


def fetch_html(url: str, retries: int = DEFAULT_RETRIES, timeout: int = DEFAULT_TIMEOUT) -> Optional[str]:
    """Fetch HTML from a Domain URL. Returns the page body or None on failure.

    Routes through Bright Data Web Unlocker if BRIGHTDATA_API_KEY is set, else
    falls back to direct curl_cffi with chrome120 TLS impersonation.
    """
    use_unlocker = bool(_api_key())
    for attempt in range(retries):
        if use_unlocker:
            result = _post_unlocker(url, return_json=False, timeout=timeout)
            if result and result.get('body'):
                return result['body']
        else:
            try:
                resp = cffi_requests.get(url, impersonate='chrome120', timeout=timeout)
                if resp.status_code == 200:
                    return resp.text
                if resp.status_code == 404:
                    return None
            except Exception:
                pass
        if attempt < retries - 1:
            time.sleep(3)
    return None


def fetch_with_status(url: str, retries: int = DEFAULT_RETRIES, timeout: int = DEFAULT_TIMEOUT) -> Optional[Dict]:
    """Fetch a Domain URL preserving HTTP status code and final URL (for
    redirect-based detection, e.g. withdrawn listings).

    Returns {'status': int, 'body': str, 'url': str, 'headers': dict} or None.

    Note: Bright Data Web Unlocker follows redirects internally and returns the
    final page. The `url` field reflects the resolved URL — for `/property-profile/`
    redirects (Domain's pattern for withdrawn listings), check if `'/property-profile/'`
    appears in the returned `url` field.
    """
    use_unlocker = bool(_api_key())
    for attempt in range(retries):
        if use_unlocker:
            result = _post_unlocker(url, return_json=True, timeout=timeout)
            if result:
                return result
        else:
            try:
                resp = cffi_requests.get(url, impersonate='chrome120', timeout=timeout, allow_redirects=False)
                return {
                    'status': resp.status_code,
                    'body': resp.text,
                    'url': str(resp.url),
                    'headers': dict(resp.headers),
                }
            except Exception:
                pass
        if attempt < retries - 1:
            time.sleep(3)
    return None
