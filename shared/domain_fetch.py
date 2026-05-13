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
import time
from typing import Optional, Dict

from curl_cffi import requests as cffi_requests

BRIGHTDATA_ENDPOINT = 'https://api.brightdata.com/request'

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
    'status' and 'url' when return_json=True. None on failure."""
    api_key = _api_key()
    if not api_key:
        return None

    payload = {'zone': _zone(), 'url': url, 'format': 'json' if return_json else 'raw'}
    headers = {
        'Content-Type': 'application/json',
        'Authorization': f'Bearer {api_key}',
    }
    try:
        resp = cffi_requests.post(BRIGHTDATA_ENDPOINT, headers=headers, json=payload, timeout=timeout)
        if resp.status_code != 200:
            return None
        if return_json:
            data = resp.json()
            return {
                'status': data.get('status_code', 0),
                'body': data.get('body', ''),
                'url': data.get('url', url),
                'headers': data.get('headers', {}),
            }
        if len(resp.text) < 200:  # very small response = likely error/challenge
            return None
        return {'body': resp.text}
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
