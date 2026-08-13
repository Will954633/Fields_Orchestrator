#!/usr/bin/env python3
"""
check_property_sitemap_urls.py — do the /property/ URLs we publish actually render?

A URL in sitemap.xml is a promise to Google that the page exists. A sitemap entry
that server-renders "Property Not Found" is worse than no entry: it spends crawl
budget, earns a soft-404, and drags ranking on the URLs that DO work.

    python3 scripts/check_property_sitemap_urls.py                 # full sweep
    python3 scripts/check_property_sitemap_urls.py --limit 50      # quick sample
    python3 scripts/check_property_sitemap_urls.py --out /tmp/x.json

⚠ This checks the SERVER-RENDERED html only. The site SSRs property pages (a live
page measured ~42 KB with content), so a missing property is visible in the raw
response — no browser needed. If that ever stops being true, this check silently
starts passing everything, so it asserts a minimum body size too.

Written 2026-08-13 because the defect "115 of 1,493 /property sitemap URLs render
Property Not Found" was reported with no reproduction command, and the brief for
it cited a script that did not exist. This is that script.
"""
from __future__ import annotations

import argparse
import concurrent.futures
import json
import re
import sys
import urllib.request
from pathlib import Path

SITEMAP = "https://fieldsestate.com.au/sitemap.xml"
UA = "FieldsEstate-SitemapCheck/1.0 (+ops)"
TIMEOUT = 30

# Strings that mean "this page has no property behind it". Kept as a list because
# the failure copy has changed before and may again.
FAILURE_MARKERS = ("property not found", "not found", "no longer available")
MIN_BODY_BYTES = 5000       # a real SSR'd property page measures ~40 KB


def _get(url: str) -> tuple[int, str]:
    req = urllib.request.Request(url, headers={"User-Agent": UA})
    try:
        with urllib.request.urlopen(req, timeout=TIMEOUT) as r:
            return r.status, r.read().decode("utf-8", errors="replace")
    except Exception as exc:  # noqa: BLE001
        return -1, f"__fetch_error__ {exc}"


def sitemap_urls(pattern: str = "/property/") -> list[str]:
    status, body = _get(SITEMAP)
    if status != 200:
        raise SystemExit(f"sitemap fetch failed: {status} {body[:200]}")
    locs = re.findall(r"<loc>([^<]+)</loc>", body)
    return [u for u in locs if pattern in u]


def check(url: str) -> dict:
    status, body = _get(url)
    low = body.lower()
    if status == -1:
        return {"url": url, "verdict": "fetch_error", "detail": body[:200]}
    if status != 200:
        return {"url": url, "verdict": "http_error", "status": status}
    hit = next((m for m in FAILURE_MARKERS if m in low), None)
    if hit:
        return {"url": url, "verdict": "not_found_page", "marker": hit, "bytes": len(body)}
    if len(body) < MIN_BODY_BYTES:
        # Guards against the check silently passing everything if SSR breaks.
        return {"url": url, "verdict": "suspiciously_small", "bytes": len(body)}
    return {"url": url, "verdict": "ok", "bytes": len(body)}


def main() -> int:
    p = argparse.ArgumentParser()
    p.add_argument("--pattern", default="/property/",
                   help="URL substring to check (e.g. /off-market/). Default /property/")
    p.add_argument("--limit", type=int, help="check only the first N (quick sample)")
    p.add_argument("--sample", type=int,
                   help="check N RANDOMLY chosen URLs — use for large classes where a "
                        "head-N slice would only ever test one suburb or one vintage")
    p.add_argument("--workers", type=int, default=8, help="concurrent requests (be kind)")
    p.add_argument("--out", type=Path, help="write full JSON results here")
    args = p.parse_args()

    urls = sitemap_urls(args.pattern)
    if args.sample and args.sample < len(urls):
        import random
        random.seed(20260813)          # reproducible sample
        urls = random.sample(urls, args.sample)
    elif args.limit:
        urls = urls[: args.limit]
    print(f"checking {len(urls)} {args.pattern} URLs from the live sitemap...", flush=True)

    results = []
    with concurrent.futures.ThreadPoolExecutor(max_workers=args.workers) as pool:
        for i, res in enumerate(pool.map(check, urls), 1):
            results.append(res)
            if i % 100 == 0:
                bad = sum(1 for r in results if r["verdict"] != "ok")
                print(f"  {i}/{len(urls)} — {bad} failing so far", flush=True)

    buckets: dict[str, list] = {}
    for r in results:
        buckets.setdefault(r["verdict"], []).append(r)

    print("\n=== RESULT")
    for verdict, rows in sorted(buckets.items(), key=lambda kv: -len(kv[1])):
        print(f"  {len(rows):>5}  {verdict}")
    broken = [r for r in results if r["verdict"] != "ok"]
    print(f"\n{len(broken)} of {len(results)} published {args.pattern} URLs do not render.")
    for r in broken[:15]:
        print(f"  - {r['verdict']:<20} {r['url']}")
    if len(broken) > 15:
        print(f"  ... and {len(broken) - 15} more")

    if args.out:
        args.out.write_text(json.dumps(results, indent=2))
        print(f"\nfull results: {args.out}")

    # Exit non-zero when the sitemap is publishing dead URLs, so this can gate a job.
    return 1 if broken else 0


if __name__ == "__main__":
    sys.exit(main())
