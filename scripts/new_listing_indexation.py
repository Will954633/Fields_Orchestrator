#!/usr/bin/env python3
"""
new_listing_indexation.py — GSC URL Inspection for newly-published property
editorial, with a persistent cache so we stop re-querying Google once a page
is confirmed indexed (conserves the shared ~2000/day Search Console quota;
the weekly `seo_indexation_check.py` random-samples the whole sitemap and
shares the same credential/quota pool).

Reuses `_svc()`/`inspect()`/`SITE` from `scripts/brain2/seo_indexation_check.py`
verbatim rather than re-implementing GSC auth — same service account
(`.gcp-floor-plan-vision.json`, webmasters scope), same proven-working path.

Persists to `system_monitor.new_listing_indexation` (one doc per property
slug): {slug, url, first_checked_at, last_checked_at, checks, confirmed_indexed,
coverage_state, verdict, detail}.

Usage:
  python3 scripts/new_listing_indexation.py --slug some-slug --check   # one-off manual check
"""
from __future__ import annotations
import argparse
import os
import sys
from datetime import datetime, timezone

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "brain2"))
from seo_indexation_check import _svc as gsc_svc, inspect as gsc_inspect, SITE  # noqa: E402

INDEXED_STATES = {"Submitted and indexed", "Indexed, not submitted in sitemap"}


def property_url(url_slug: str) -> str:
    return f"{SITE.rstrip('/')}/property/{url_slug}"


def get_cached(sm_db, slug):
    return sm_db["new_listing_indexation"].find_one({"slug": slug})


def check_and_cache(sm_db, svc, slug: str, force: bool = False):
    """Returns the (possibly freshly-updated) cache doc. Skips the live GSC
    call entirely if already confirmed indexed and not forced — that's the
    quota-conservation behaviour this module exists for."""
    now = datetime.now(timezone.utc)
    cached = get_cached(sm_db, slug)
    if cached and cached.get("confirmed_indexed") and not force:
        return cached

    url = property_url(slug)
    result = gsc_inspect(svc, url)
    coverage_state = result.get("coverageState")
    confirmed = coverage_state in INDEXED_STATES

    doc = {
        "slug": slug, "url": url,
        "first_checked_at": (cached or {}).get("first_checked_at", now),
        "last_checked_at": now,
        "checks": (cached or {}).get("checks", 0) + 1,
        "confirmed_indexed": confirmed,
        "coverage_state": coverage_state,
        "verdict": result.get("verdict"),
        "detail": {k: v for k, v in result.items() if k != "url"},
    }
    sm_db["new_listing_indexation"].replace_one({"slug": slug}, doc, upsert=True)
    return doc


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--slug", required=True)
    ap.add_argument("--check", action="store_true")
    args = ap.parse_args()

    sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
    from shared.db import get_client
    client = get_client()
    sm_db = client["system_monitor"]
    svc = gsc_svc()
    doc = check_and_cache(sm_db, svc, args.slug, force=True)
    print(doc)


if __name__ == "__main__":
    main()
