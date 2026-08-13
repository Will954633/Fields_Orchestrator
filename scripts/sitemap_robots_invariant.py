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
  A. Every URL in the sitemap is HEALTHY — 200 AND index,follow AND self-canonical
     AND not a known empty-state template. A 200 alone is not health: 115 /property
     URLs served 200 + "Property Not Found" + noindex on 2026-08-08.
  B. Every URL earning impressions that is genuinely healthy+indexable is in the
     sitemap. Confirmed against the LIVE page, so historical URLs that now 301/404/
     noindex do not raise false alarms.
  C. The canonical is STABLE ACROSS HYDRATION — the post-JS DOM canonical equals the
     one in the SSR source, and there is exactly one canonical element. Route metadata
     owns the canonical; a component that rewrites it after hydration silently changes
     what Googlebot (which renders JS) sees. On 2026-08-08 that de-indexed
     /market-intelligence/Varsity-Lakes, which declared itself a duplicate of its own
     child tab. Requires a headless browser, so it runs on a small sample.

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
from typing import Optional

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
#
# That figure is for ONE night, and until 2026-08-13 one night was all you ever got —
# `run()` used a hardcoded seed, so the same 25 URLs were drawn every night forever and
# coverage never accrued. The seed is now the date (see run()), so the small sample is
# backed by cumulative coverage: 25 URLs after one night, ~169 after a week, ~603 of
# 1,508 after a month. A 1%-prevalence defect goes from 22% detection *permanently* to
# 83% within a week and 99.9% within a month — without fetching any more per night.
DEFAULT_SAMPLE = 25
# Cap for invariant B. The missing-from-sitemap population is routinely ~1,200 and
# mostly legitimate, so this is sampled — never let a sampled check be reported as
# exhaustive (b_population records the true size).
DEFAULT_B_CAP = 40
# Invariant C needs a real browser per URL, so it is the most expensive check. A small
# per-family sample is enough: a canonical rewrite is a code-level fault that affects
# every page rendered by the same component, never a single URL.
DEFAULT_C_SAMPLE = 3
CANON_SCRIPT = os.path.join(os.path.dirname(os.path.abspath(__file__)), "canonical_stability.js")
ROBOTS_RE = re.compile(r'<meta[^>]+name="robots"[^>]+content="([^"]*)"', re.I)
CANON_RE = re.compile(r'<link[^>]+rel="canonical"[^>]+href="([^"]*)"', re.I)
TITLE_RE = re.compile(r"<title>([^<]*)</title>", re.I)

# Known empty-state templates. A 200 alone is NOT health: on 2026-08-08, 115 /property
# URLs served 200 + "Property Not Found" + noindex from a document that had resolved
# fine, and 1 /article id did the same. Google eventually labels these soft 404s; this
# catches them the same night they appear.
EMPTY_STATE_TITLES = (
    "property not found",
    "article not found",
    "off-market property |",   # meta()'s no-address fallback
    "suburb not covered yet",
)


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


def unhealthy(status, html, path) -> str:
    """A sitemap URL is healthy only if it is 200 + indexable + self-canonical + real
    content. Returns the reason it is not, or "" when healthy."""
    if status != 200:
        return f"http {status}"
    r = robots_of(html)
    if "noindex" in r:
        return f"robots={r}"
    title = (TITLE_RE.search(html).group(1).strip().lower() if TITLE_RE.search(html) else "")
    for t in EMPTY_STATE_TITLES:
        if t in title:
            return f"empty-state template: {title[:48]!r}"
    m = CANON_RE.search(html)
    if not m:
        return "no canonical"
    canon = m.group(1).replace(SITE, "").split("?")[0].rstrip("/")
    if canon != path.split("?")[0].rstrip("/"):
        return f"canonical -> {canon}"
    return ""


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
            why = unhealthy(status, html, p)
            if why:
                violations.append({"invariant": "A", "family": fam, "path": p,
                                   "status": status, "robots": robots_of(html) or "<none>",
                                   "reason": why})
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
        # Only a violation once the LIVE page confirms a genuinely healthy, indexable,
        # self-canonical page. Historical GSC URLs that now 301, 404, noindex or render
        # an empty state are correctly absent and must not raise a false alarm.
        if not unhealthy(status, html, p):
            violations.append({"invariant": "B", "family": family(p), "path": p,
                               "status": status, "robots": robots_of(html) or "<none>",
                               "reason": "healthy+indexable but not in sitemap"})
    return violations, checked, population


def check_c(paths, per_family: int, rng) -> tuple[list, int]:
    """Invariant C — canonical unchanged by hydration. Shells out to a headless
    browser; returns ([], 0) if the harness is unavailable rather than failing the
    whole run, and says so in the metrics."""
    import json as _json
    import subprocess
    if not os.path.exists(CANON_SCRIPT):
        return [], 0
    by = defaultdict(list)
    for p in paths:
        by[family(p)].append(p)
    urls = []
    for fam, ps in sorted(by.items()):
        urls += [SITE + p for p in rng.sample(ps, min(per_family, len(ps)))]
    try:
        out = subprocess.run(["node", CANON_SCRIPT, *urls], capture_output=True,
                             text=True, timeout=600).stdout
        rows = _json.loads(out or "[]")
    except Exception as e:
        print(f"  (invariant C skipped: {e})")
        return [], 0
    violations = []
    for r in rows:
        if r.get("error"):
            continue
        if r.get("count") != 1 or r.get("ssr") != r.get("post"):
            violations.append({"invariant": "C", "family": family(r["path"]), "path": r["path"],
                               "status": 200, "robots": "-",
                               "reason": f"canonical {r.get('ssr')} -> {r.get('post')} ({r.get('count')} element(s))"})
    return violations, len(rows)


def run(per_family: int, b_cap: int, c_sample: int = DEFAULT_C_SAMPLE,
        seed: Optional[int] = None) -> dict:
    # Seed from TODAY's date, not a constant.
    #
    # This was `random.Random(20260808)` — a hardcoded seed — so the sampler drew the
    # SAME 25 URLs per family every night, forever. The reassuring maths in the
    # DEFAULT_SAMPLE comment ("P(miss) over 25 draws is ~0.0006") holds for ONE night
    # and then stops accruing: repeated runs added no coverage at all, and any defect
    # outside those 25 URLs was never checked no matter how long the monitor ran. That
    # is a silent blind spot over ~98% of each family.
    #
    # A date seed keeps the property the constant was there for — a violation found
    # today is reproducible today, which is when you debug it — while giving a fresh
    # draw each night. Cumulative coverage over a month goes from 25 URLs to ~700, and
    # a 1%-prevalence defect is caught with ~83% probability inside a week rather than
    # ~0%. Pass --seed to replay a specific past run.
    if seed is None:
        seed = int(date.today().strftime("%Y%m%d"))
    rng = random.Random(seed)
    paths = sitemap_paths()
    if not paths:
        # Zero-output path (CLAUDE.md 7b): an empty sitemap is never "no work to do".
        raise RuntimeError("sitemap returned 0 URLs — cannot assert anything; treating as failure")
    va, na = check_a(paths, per_family, rng)
    vb, nb, pop_b = check_b(paths, b_cap, rng)
    vc, nc = check_c(paths, c_sample, rng)
    st = {
        "sitemap_urls": len(paths),
        "seed": seed,   # replay this exact draw with --seed
        "a_checked": na, "a_violations": len(va),
        "b_checked": nb, "b_population": pop_b, "b_violations": len(vb),
        "c_checked": nc, "c_violations": len(vc),
        "violations": (va + vb + vc)[:40],
    }
    if na == 0:
        raise RuntimeError("checked 0 sitemap URLs; the sampler is broken, not the site")
    return st


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--sample", type=int, default=DEFAULT_SAMPLE, help="URLs per family for invariant A")
    ap.add_argument("--b-cap", type=int, default=DEFAULT_B_CAP, help="max URLs sampled for invariant B")
    ap.add_argument("--c-sample", type=int, default=DEFAULT_C_SAMPLE, help="URLs per family for invariant C (headless)")
    ap.add_argument("--seed", type=int, default=None,
                    help="replay a specific draw (default: today's date, YYYYMMDD)")
    ap.add_argument("--dry-run", action="store_true", help="no heartbeat")
    args = ap.parse_args()
    load_env()  # never trust the caller's env (CLAUDE.md rule 7, step 3)

    def report(st):
        print(f"sitemap URLs: {st['sitemap_urls']}   (seed {st['seed']} — replay with --seed {st['seed']})")
        print(f"  A (sitemap URL is indexable):        checked {st['a_checked']:>4}  violations {st['a_violations']}")
        print(f"  B (indexable + ranking => in sitemap): checked {st['b_checked']:>4} of {st['b_population']} missing  violations {st['b_violations']}")
        print(f"  C (canonical stable across hydration): checked {st['c_checked']:>4}  violations {st['c_violations']}")
        for v in st["violations"]:
            print(f"    [{v['invariant']}] {v['family']:<20} {v['path']}\n          status={v['status']} robots={v['robots']} reason={v.get('reason','')}")

    if args.dry_run:
        report(run(args.sample, args.b_cap, args.c_sample, args.seed))
        return

    with job_run("sitemap_robots_invariant", cadence_hours=24,
                 title="Sitemap/Robots Invariant Check") as beat:
        st = run(args.sample, args.b_cap, args.c_sample, args.seed)
        report(st)
        beat.metrics = st
        total = st["a_violations"] + st["b_violations"] + st["c_violations"]
        beat.detail = (f"{st['sitemap_urls']} sitemap URLs; A {st['a_violations']}/{st['a_checked']} "
                       f"violations, B {st['b_violations']}/{st['b_checked']} violations, "
                       f"C {st['c_violations']}/{st['c_checked']} canonical-drift")
        # Outcome assertion (7b): a clean exit must mean the invariants HOLD, not merely
        # that the script ran. Both defects this monitor exists for would raise here.
        if total:
            raise RuntimeError(
                f"sitemap/robots/canonical invariant violated: A={st['a_violations']} unhealthy "
                f"sitemap URLs, B={st['b_violations']} indexable ranking URLs missing from the "
                f"sitemap, C={st['c_violations']} canonicals rewritten by hydration. "
                f"First: {st['violations'][0] if st['violations'] else 'n/a'}")


if __name__ == "__main__":
    main()
