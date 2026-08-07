#!/usr/bin/env python3
"""sitemap_robots_invariant.py — assert the sitemap and the pages agree.

WHY THIS EXISTS
---------------
On 2026-08-08 we found the same defect twice in one morning, in opposite directions:

  [SITEMAP-UNDERCONTRACT-GAP]      11 pages rendered fully indexable (no robots tag
                                   at all) but were in NO sitemap — `under_contract`
                                   fell between two queries neither of which claimed it.
  [OFFMARKET-UNIT-SITEMAP-MISMATCH] 4,559 URLs were IN the sitemap while serving
                                   `noindex, nofollow` — the generator tested the unit
                                   regex on `address`, the route tested
                                   `address || complete_address || ADDRESS_STANDARD`.

Both passed every existing check. The sitemap cron was green; it generated a sitemap
"successfully" both times. Success at generating a file says nothing about whether the
file agrees with what the site actually serves — the generator and the route encode the
same policy in two places, in two languages, and nothing compared them.

THE INVARIANTS
--------------
  A. Every URL in the sitemap is indexable.        (Google: put URLs you WANT indexed
                                                    in the sitemap.)
  B. Every indexable URL that earns impressions is in the sitemap.

A is checked by sampling the sitemap and reading the live robots tag. B is checked
against Search Console — a URL Google already shows results for, which serves 200 and
is indexable, but which we never advertised. That is exactly how the under_contract gap
surfaced, and it needs no duplicate copy of the generator's eligibility rules (a second
copy being the thing that caused both bugs).

DELIBERATELY NOT DONE HERE: re-implementing "what should be eligible". This monitor
compares two things that ALREADY exist — the sitemap and the served page — so it cannot
drift from either.

Usage:
  python3 scripts/sitemap_robots_invariant.py --sample 60     # ad-hoc
  python3 scripts/sitemap_robots_invariant.py                 # nightly (heartbeat)
"""
from __future__ import annotations
import argparse
import os
import random
import re
import sys
import urllib.request
from collections import defaultdict
from datetime import date, timedelta

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from shared.env import load_env
from job_status import job_run

SITE = "https://fieldsestate.com.au"
SITEMAP = f"{SITE}/sitemap.xml"
GB_UA = "Mozilla/5.0 (compatible; Googlebot/2.1; +http://www.google.com/bot.html)"
SA_KEY = "/home/fields/.gcp-floor-plan-vision.json"
GSC_SCOPES = ["https://www.googleapis.com/auth/webmasters"]

# Per-family sample for invariant A. Small enough to stay polite, large enough that a
# systemic breakage (4,559 URLs = 26% of a family) is caught with near-certainty:
# at 26% prevalence, P(miss) over 25 draws is ~0.0006.
DEFAULT_SAMPLE = 25
# Cap for invariant B. The missing-from-sitemap population is routinely ~1,200 and
# mostly legitimate, so this is sampled — never let a sampled check be reported as
# exhaustive (b_population records the true size).
DEFAULT_B_CAP = 40
ROBOTS_RE = re.compile(r'<meta[^>]+name="robots"[^>]+content="([^"]*)"', re.I)


def family(path: str) -> str:
    for p, name in (("/off-market/", "off-market"), ("/property/", "property"),
                    ("/houses-for-sale/", "houses-for-sale"),
                    ("/market-intelligence/", "market-intelligence"),
                    ("/articles/", "articles")):
        if path.startswith(p):
            return name
    return "other"


def fetch(url: str, timeout: int = 25):
    req = urllib.request.Request(url, headers={"User-Agent": GB_UA})
    try:
        with urllib.request.urlopen(req, timeout=timeout) as r:
            return r.status, r.read().decode("utf-8", "replace")
    except urllib.error.HTTPError as e:
        return e.code, ""
    except Exception:
        return None, ""


def sitemap_paths() -> list[str]:
    _, xml = fetch(SITEMAP, timeout=90)
    return [m.replace(SITE, "") for m in re.findall(r"<loc>([^<]+)</loc>", xml)]


def robots_of(html: str) -> str:
    m = ROBOTS_RE.search(html)
    return (m.group(1).strip().lower() if m else "")


def check_a(paths, per_family: int, rng) -> tuple[list, int]:
    """Invariant A — every sitemap URL is indexable."""
    by = defaultdict(list)
    for p in paths:
        by[family(p)].append(p)
    violations, checked = [], 0
    for fam, ps in sorted(by.items()):
        for p in rng.sample(ps, min(per_family, len(ps))):
            status, html = fetch(SITE + p)
            checked += 1
            r = robots_of(html)
            if status != 200 or "noindex" in r:
                violations.append({"invariant": "A", "family": fam, "path": p,
                                   "status": status, "robots": r or "<none>"})
    return violations, checked


def check_b(paths, cap: int, rng) -> tuple[list, int, int]:
    """Invariant B — an indexable URL earning impressions must be in the sitemap.

    SAMPLED, not exhaustive. The missing set is routinely ~1,200 URLs and most are
    correctly absent (noindex, 301'd, superseded), so fetching all of them means
    ~1,200 sequential requests against production for a check that runs nightly.
    A random sample surfaces any systemic breakage; the returned `population` makes
    the sampling explicit rather than letting a partial check read as a full one.
    """
    try:
        from google.oauth2 import service_account
        from googleapiclient.discovery import build
    except ImportError:
        return [], 0, 0  # arity must match the 3-tuple below
    cred = service_account.Credentials.from_service_account_file(SA_KEY, scopes=GSC_SCOPES)
    gsc = build("searchconsole", "v1", credentials=cred, cache_discovery=False)
    end = date.today() - timedelta(days=3)
    start = end - timedelta(days=27)
    rows = gsc.searchanalytics().query(siteUrl=SITE + "/", body={
        "startDate": start.isoformat(), "endDate": end.isoformat(),
        "dimensions": ["page"], "rowLimit": 25000}).execute().get("rows", [])
    in_sitemap = set(paths)
    missing = [r["keys"][0].replace(SITE, "") for r in rows
               if r["keys"][0].replace(SITE, "") not in in_sitemap]
    population = len(missing)
    if population > cap:
        missing = rng.sample(missing, cap)
    violations, checked = [], 0
    for p in missing:
        status, html = fetch(SITE + p)
        checked += 1
        if status == 200 and "noindex" not in robots_of(html):
            # 200 + indexable + earning impressions + absent from sitemap.
            violations.append({"invariant": "B", "family": family(p), "path": p,
                               "status": status, "robots": robots_of(html) or "<none>"})
    return violations, checked, population


def run(per_family: int, b_cap: int) -> dict:
    rng = random.Random(20260808)  # fixed seed: a violation is reproducible
    paths = sitemap_paths()
    if not paths:
        # Zero-output path (CLAUDE.md 7b): an empty sitemap is never "no work to do".
        raise RuntimeError("sitemap returned 0 URLs — cannot assert anything; treating as failure")
    va, na = check_a(paths, per_family, rng)
    vb, nb, pop_b = check_b(paths, b_cap, rng)
    st = {
        "sitemap_urls": len(paths),
        "a_checked": na, "a_violations": len(va),
        "b_checked": nb, "b_population": pop_b, "b_violations": len(vb),
        "violations": (va + vb)[:40],
    }
    if na == 0:
        raise RuntimeError("checked 0 sitemap URLs; the sampler is broken, not the site")
    return st


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--sample", type=int, default=DEFAULT_SAMPLE, help="URLs per family for invariant A")
    ap.add_argument("--b-cap", type=int, default=DEFAULT_B_CAP, help="max URLs sampled for invariant B")
    ap.add_argument("--dry-run", action="store_true", help="no heartbeat")
    args = ap.parse_args()
    load_env()  # never trust the caller's env (CLAUDE.md rule 7, step 3)

    def report(st):
        print(f"sitemap URLs: {st['sitemap_urls']}")
        print(f"  A (sitemap URL is indexable):        checked {st['a_checked']:>4}  violations {st['a_violations']}")
        print(f"  B (indexable + ranking => in sitemap): checked {st['b_checked']:>4} of {st['b_population']} missing  violations {st['b_violations']}")
        for v in st["violations"]:
            print(f"    [{v['invariant']}] {v['family']:<20} {v['path']}  status={v['status']} robots={v['robots']}")

    if args.dry_run:
        report(run(args.sample, args.b_cap))
        return

    with job_run("sitemap_robots_invariant", cadence_hours=24,
                 title="Sitemap/Robots Invariant Check") as beat:
        st = run(args.sample, args.b_cap)
        report(st)
        beat.metrics = st
        total = st["a_violations"] + st["b_violations"]
        beat.detail = (f"{st['sitemap_urls']} sitemap URLs; A {st['a_violations']}/{st['a_checked']} "
                       f"violations, B {st['b_violations']}/{st['b_checked']} violations")
        # Outcome assertion (7b): a clean exit must mean the invariants HOLD, not merely
        # that the script ran. Both defects this monitor exists for would raise here.
        if total:
            raise RuntimeError(
                f"sitemap/robots invariant violated: {st['a_violations']} sitemap URLs serve "
                f"noindex, {st['b_violations']} indexable ranking URLs are missing from the "
                f"sitemap. First: {st['violations'][0] if st['violations'] else 'n/a'}")


if __name__ == "__main__":
    main()
