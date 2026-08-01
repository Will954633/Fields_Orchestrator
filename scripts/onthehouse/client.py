"""Fetching and parsing onthehouse.com.au. No database, no business logic.

Access notes (measured, see ONTHEHOUSE_SCRAPING.md):
  - plain curl_cffi with Chrome impersonation; NO proxy, NO auth, NO Bright Data
  - pages are 0.5-3.3 MB, so bytes dominate runtime, not the politeness pause
  - a full 40-suburb sale+sold sweep ran 683 requests / 1.08 GB / 16.9 min with zero
    failures and zero blocks, but sustained DAILY volume remains untested — so every
    fetch watches for 403/429 and the caller is expected to abort the whole run.
"""
from __future__ import annotations

import json
import re
import time

from curl_cffi import requests as cffi

BASE = "https://www.onthehouse.com.au"
PAGE_PAUSE_S = 1.5
TIMEOUT_S = 60

# Index page -> the embedded record category that carries the data we want.
# There is no __NEXT_DATA__ block; records sit loose in the HTML (see records()).
KINDS = {
    "sale": ("property-for-sale", "SaleListing"),
    "sold": ("sold", "Property"),
    "rent": ("property-for-rent", "RentalListing"),
}


class Blocked(Exception):
    """403/429 seen. Abort the whole run — do not retry, do not degrade to 'no results'."""


def url_for(kind: str, suburb_slug: str, page: int = 1) -> str:
    path, _ = KINDS[kind]
    return f"{BASE}/{path}/qld/{suburb_slug}" + (f"?page={page}" if page > 1 else "")


def fetch(url: str) -> str | None:
    """HTML, or None if the fetch failed. Raises Blocked on 403/429.

    None means UNKNOWN, never "empty". Callers must not turn it into an empty result
    set — doing so would deactivate every listing in a suburb and, downstream,
    green-light marketing to an owner who is actively selling.
    """
    try:
        r = cffi.get(url, impersonate="chrome120", timeout=TIMEOUT_S)
    except Exception as e:
        print(f"    fetch error {type(e).__name__}: {str(e)[:120]} — {url}")
        return None
    if r.status_code in (403, 429):
        raise Blocked(f"HTTP {r.status_code} on {url}")
    if r.status_code != 200:
        print(f"    HTTP {r.status_code} — {url}")
        return None
    return r.text


def records(html: str, category: str):
    """Yield the embedded JSON records of one category, brace-matched.

    The page has no __NEXT_DATA__ envelope — records appear inline as
    {"category":"SaleListing",...}. Matching is string-aware so a brace inside a
    listing `description` cannot end the object early.
    """
    start = re.compile(r'\{"category":"%s"' % re.escape(category))
    for m in start.finditer(html):
        depth, i, n = 0, m.start(), len(html)
        in_str = esc = False
        while i < n:
            ch = html[i]
            if in_str:
                if esc:
                    esc = False
                elif ch == "\\":
                    esc = True
                elif ch == '"':
                    in_str = False
            elif ch == '"':
                in_str = True
            elif ch == "{":
                depth += 1
            elif ch == "}":
                depth -= 1
                if depth == 0:
                    try:
                        yield json.loads(html[m.start():i + 1])
                    except Exception:
                        pass
                    break
            i += 1


def crawl_suburb(kind: str, suburb_slug: str, max_pages: int, budget_s: int,
                 want=None) -> tuple[list[dict] | None, dict]:
    """Page a suburb index until it stops yielding new IN-TARGET records.

    Returns (records, meta). records is None ONLY when page 1 could not be fetched —
    i.e. we learned nothing about this suburb and must not expire anything in it.

    Every index also returns SURROUNDING suburbs (the site sets includeSurroundSuburbs),
    so a naive "stop when nothing new" rule keeps paging long after the requested suburb
    is exhausted. We stop on the target suburb's own growth and keep the neighbours we
    were given for free — they are filed under their OWN suburb by the caller.

    `want` optionally filters records (e.g. houses only) BEFORE the stop rule is
    evaluated, so we don't keep paging for stock we're going to discard.
    """
    _, category = KINDS[kind]
    out: dict[str, dict] = {}
    seen: set[str] = set()
    t0, pages, dry = time.time(), 0, 0

    for page in range(1, max_pages + 1):
        if time.time() - t0 > budget_s:
            print(f"    {suburb_slug}: page budget reached at page {page}")
            break
        html = fetch(url_for(kind, suburb_slug, page))
        if html is None:
            if page == 1:
                return None, {"suburb": suburb_slug, "kind": kind, "status": "FETCH_FAILED"}
            break
        pages = page
        new_here = 0
        for rec in records(html, category):
            addr = rec.get("address") or {}
            key = join_key(addr)
            if not key or key in seen:
                continue
            seen.add(key)
            if want is not None and not want(rec):
                continue
            rec["_key"] = key
            rec["_suburb"] = suburb_of(addr)
            rec["_via"] = suburb_slug
            out[key] = rec
            if rec["_suburb"] == suburb_slug:
                new_here += 1
        # Two consecutive barren pages, not one: a single page can legitimately be all
        # neighbours while the target still has stock further in.
        dry = dry + 1 if new_here == 0 else 0
        if dry >= 2:
            break
        time.sleep(PAGE_PAUSE_S)

    return list(out.values()), {
        "suburb": suburb_slug, "kind": kind, "status": "ok", "pages": pages,
        "records": len(out),
        "in_target": sum(1 for r in out.values() if r["_suburb"] == suburb_slug),
        "secs": round(time.time() - t0, 1),
    }


def suburb_of(addr: dict) -> str:
    s = re.sub(r"[^a-z0-9 ]", " ", (addr.get("suburb") or "").lower()).strip()
    return f"{'-'.join(s.split())}-{addr.get('postCode') or ''}"


def join_key(addr: dict) -> str | None:
    """THE join key for an onthehouse record.

    Deliberately runs the same `matching.address_key()` used on our Domain addresses,
    over onthehouse's `formattedAddress`. Both sides of every join must be computed by
    one function or the join silently loses rows — and that single-function setup is
    the one the 72%-overlap / 97%-price-agreement measurements were taken under.

    The structured components are only a fallback for records with no usable
    formattedAddress. They are NOT preferred despite carrying more explicit
    information: onthehouse sometimes packs "2/158" into `streetNumber` and keeps a
    "17A" suffix that our side normalises away, so component-derived keys agree with
    address-derived ones only ~87% of the time. Better information is worthless here if
    the other side of the join can't reproduce it.
    """
    from .matching import address_key
    key = address_key(addr.get("formattedAddress") or "")
    return key or address_key_from_components(addr)


def address_key_from_components(addr: dict) -> str | None:
    """Fallback key from structured components. See join_key() for why it's a fallback."""
    unit = (addr.get("unitNumber") or "").split("-")[0].strip()
    num = (addr.get("streetNumber") or "").split("-")[0].strip()
    name = re.sub(r"[^a-z0-9 ]", " ", (addr.get("streetName") or "").lower()).strip()
    sub = re.sub(r"[^a-z0-9 ]", " ", (addr.get("suburb") or "").lower()).strip()
    if not (num and name and sub):
        return None
    return f"{unit}|{num}|{' '.join(name.split())}|{' '.join(sub.split())}"
