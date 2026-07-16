#!/usr/bin/env python3
"""
seo_indexation_check.py — Phase 1 SEO experiment readout: are the /property pages
getting discovered, crawled and indexed by Google?

Context: on 2026-07-16 the sitemap was expanded from ~163 to 1,594 /property URLs
(1,372 sold pages re-enabled with human-readable address slugs) as the Brain-2
"demand-engine" pilot. This script measures whether Google is actually indexing
them — the make-or-break signal that gates any further page generation.

What it reports:
  1. Sitemap submission status (submitted vs indexed count, last downloaded).
  2. URL Inspection on a SAMPLE of property URLs → coverageState breakdown:
       - "Submitted and indexed"                 = working
       - "Crawled - currently not indexed"        = quality/thin-content signal
       - "Discovered - currently not indexed"     = crawl-budget / authority signal
       - "URL is unknown to Google"               = not yet discovered
  3. Writes a durable snapshot to system_monitor.seo_indexation_snapshots so we can
     track the indexation curve week-over-week.

Auth: reuses the floor-plan-vision service account (webmasters.readonly scope).
Note: SA currently has only the URL-prefix property https://fieldsestate.com.au/ ;
adding it to the sc-domain property in Search Console would give fuller coverage data.

Usage:
  python3 scripts/brain2/seo_indexation_check.py                 # report + snapshot (read-only)
  python3 scripts/brain2/seo_indexation_check.py --resubmit      # also (re)submit sitemap.xml to Google
  python3 scripts/brain2/seo_indexation_check.py --sample 30     # inspect 30 URLs (default 20; GSC quota ~2000/day)
  python3 scripts/brain2/seo_indexation_check.py --no-snapshot   # don't write to DB
"""
import os, sys, json, argparse, random, urllib.request, re
from datetime import datetime, timezone

sys.path.insert(0, "/home/fields/Fields_Orchestrator")
from dotenv import load_dotenv
load_dotenv("/home/fields/Fields_Orchestrator/.env")
from shared.db import get_client  # noqa: E402

SA = "/home/fields/.gcp-floor-plan-vision.json"
SITE = "https://fieldsestate.com.au/"          # SA-accessible property (URL-prefix form)
SITEMAP_URL = "https://fieldsestate.com.au/sitemap.xml"
SCOPES = ["https://www.googleapis.com/auth/webmasters"]  # read+write (submit needs write; also covers inspect/list)


def _svc():
    from google.oauth2 import service_account
    from googleapiclient.discovery import build
    creds = service_account.Credentials.from_service_account_file(SA, scopes=SCOPES)
    return build("searchconsole", "v1", credentials=creds, cache_discovery=False)


def sitemap_status(svc):
    out = []
    for s in svc.sitemaps().list(siteUrl=SITE).execute().get("sitemap", []):
        contents = s.get("contents", [])
        out.append({
            "path": s.get("path"),
            "lastSubmitted": s.get("lastSubmitted"),
            "lastDownloaded": s.get("lastDownloaded"),
            "isPending": s.get("isPending"),
            "errors": s.get("errors"), "warnings": s.get("warnings"),
            "submitted": sum(int(c.get("submitted", 0)) for c in contents),
            "indexed": sum(int(c.get("indexed", 0)) for c in contents),
        })
    return out


def resubmit_sitemap(svc, feedpath=SITEMAP_URL):
    """WRITE: asks Google to re-fetch the (already-public) sitemap. Standard, reversible."""
    svc.sitemaps().submit(siteUrl=SITE, feedpath=feedpath).execute()
    return feedpath


def sample_property_urls(n):
    """Pull /property URLs straight from the live sitemap and sample n of them."""
    xml = urllib.request.urlopen(SITEMAP_URL, timeout=30).read().decode("utf-8", "replace")
    urls = re.findall(r"<loc>(https://fieldsestate\.com\.au/property/[^<]+)</loc>", xml)
    random.shuffle(urls)
    return urls[:n], len(urls)


def inspect(svc, url):
    body = {"inspectionUrl": url, "siteUrl": SITE, "languageCode": "en-AU"}
    r = svc.urlInspection().index().inspect(body=body).execute()
    idx = r.get("inspectionResult", {}).get("indexStatusResult", {})
    return {
        "url": url,
        "coverageState": idx.get("coverageState"),
        "verdict": idx.get("verdict"),
        "lastCrawlTime": idx.get("lastCrawlTime"),
        "robotsTxtState": idx.get("robotsTxtState"),
        "indexingState": idx.get("indexingState"),
        "pageFetchState": idx.get("pageFetchState"),
    }


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--sample", type=int, default=20)
    ap.add_argument("--resubmit", action="store_true")
    ap.add_argument("--no-snapshot", action="store_true")
    args = ap.parse_args()

    svc = _svc()

    print("=" * 68)
    print("SEO INDEXATION CHECK —", datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC"))
    print("=" * 68)

    resubmit_ok = None
    if args.resubmit:
        try:
            fp = resubmit_sitemap(svc)
            resubmit_ok = True
            print(f"\n[RESUBMIT] Asked Google to re-fetch {fp}")
        except Exception as e:
            resubmit_ok = False
            print(f"\n[RESUBMIT FAILED] {type(e).__name__}: {e}")
            print("  -> SA likely lacks 'Owner/Full' permission on the GSC property, "
                  "or the property is URL-prefix only. Fix: Will resubmits sitemap.xml "
                  "manually in Search Console, or grants the SA Full access.")

    print("\n--- Sitemap status ---")
    sm = sitemap_status(svc)
    for s in sm:
        print(f"  {s['path']}")
        print(f"    submitted={s['submitted']} indexed={s['indexed']} "
              f"lastDownloaded={s['lastDownloaded']} pending={s['isPending']} "
              f"errors={s['errors']} warnings={s['warnings']}")

    print(f"\n--- URL Inspection sample (n={args.sample}) ---")
    urls, total = sample_property_urls(args.sample)
    print(f"    (sampling {len(urls)} of {total} /property URLs in the live sitemap)")
    results, breakdown = [], {}
    for u in urls:
        try:
            res = inspect(svc, u)
        except Exception as e:  # quota / transient
            res = {"url": u, "coverageState": f"ERROR: {type(e).__name__}", "verdict": None}
        results.append(res)
        key = res.get("coverageState") or "UNKNOWN"
        breakdown[key] = breakdown.get(key, 0) + 1
        print(f"    [{res.get('coverageState')}]  {u.split('/property/')[-1]}"
              f"  (crawled: {res.get('lastCrawlTime') or 'never'})")

    print("\n--- Coverage breakdown ---")
    for k, v in sorted(breakdown.items(), key=lambda x: -x[1]):
        pct = 100.0 * v / max(1, len(results))
        print(f"    {v:>3}  ({pct:4.0f}%)  {k}")

    if not args.no_snapshot:
        snap = {
            "computed_at": datetime.now(timezone.utc),
            "site": SITE,
            "sitemaps": sm,
            "sample_size": len(results),
            "sample_total_property_urls": total,
            "coverage_breakdown": breakdown,
            "sample_results": results,
            "resubmitted": bool(args.resubmit),
        }
        get_client()["system_monitor"]["seo_indexation_snapshots"].insert_one(snap)
        print("\n[snapshot] written to system_monitor.seo_indexation_snapshots")

    # Machine-readable tail for cron/telegram
    print("\nSUMMARY:", json.dumps({"sitemap_submitted": sm[0]["submitted"] if sm else 0,
                                    "sitemap_indexed": sm[0]["indexed"] if sm else 0,
                                    "coverage": breakdown}))


if __name__ == "__main__":
    main()
