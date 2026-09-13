#!/usr/bin/env python3
"""
address_search_regression.py — does the address box still find addresses we hold?

WHY THIS EXISTS
---------------
Address search is the single highest-value action on the site: of the joinable
population, `searched_address` carries P(reward) ~0.69 against a 1.5% base rate.
It is also the most repeatedly broken thing we own. FIVE distinct visitor-found
failures in six weeks, every one reaching production because nothing checked the
matcher against real stored addresses:

  2026-07-30  "Glen Eagles" stored vs "Gleneagles" typed        -> 0 results, ~40 retries
  2026-08-28  "... Robina, Queensland" filler tokens            -> 0 results
  2026-08-30  street-type variants (St / Street / Str)          -> 0 results
  2026-09-06  index built once in March, never rebuilt          -> 1,843 addresses absent
  2026-09-06  a zero-result search rendered NOTHING at all      -> invisible failure

Each was found by a member of the public, not by us. This harness is the check
that should have caught them: it samples addresses we ACTUALLY HOLD in the
suburb collections, types each one the way an owner would, and asserts the live
API returns that exact address.

⚠ IT SAMPLES THE SUBURB COLLECTIONS, NEVER THE INDEX. Sampling the index can
only ever prove the index is self-consistent; the March-build failure was 1,843
addresses that were never in the index at all, and a probe drawn from the index
is structurally incapable of seeing them. The source of truth for "an address we
hold" is the suburb collection, which is what an owner's expectation is built on.

WHAT IT ASSERTS (Rule 7b — an outcome, not merely that nothing threw)
  found_pct  the address appears ANYWHERE in the results   -> hard floor
  first_pct  the address is the FIRST result               -> soft, reported
Both matter and they fail differently. "3 Cassowary Drive" returning 3/2, 35, 37
and 39 Cassowary Drive but never number 3 is a `found` failure. An owner's home
present but ranked below four neighbours is a `first` failure — measurably worse
than useless, because clicking the top result generates a report on the wrong
property.

SCHEDULING (deliberately not self-registering yet — read this before changing it)
--------------------------------------------------------------------------------
CLAUDE.md Rule 7 requires ongoing processes to self-register a heartbeat. This is
NOT yet an ongoing process: no domain may edit the crontab, so nothing schedules
it, and registering a cadence today would plant a row on the Process Registry
that goes STALE within 1.5x cadence and stays there — a false alarm about a job
nobody scheduled, which is its own kind of noise on the one board that is
supposed to mean something.

So: the job ALWAYS records its outcome to `job_runs` (`job_run` self-registers
unconditionally — `cadence_hours` defaults to 24, there is no opt-out, and that
is the right default for everything that is actually scheduled). What
`--scheduled` changes is the STALE threshold. Unscheduled, `stale_hours` is set
absurdly high so the row reports its real last outcome without ever crying STALE
about a cadence nobody signed up to. Passing `--scheduled` in the cron line drops
it to the honest 7-day threshold, and Rule 7 alerting switches on with it.

USAGE
    python3 scripts/address_search_regression.py                  # 150 probes, live API
    python3 scripts/address_search_regression.py -n 400           # the full sweep
    python3 scripts/address_search_regression.py --suburbs robina
    python3 scripts/address_search_regression.py --scheduled      # for the cron line
"""
from __future__ import annotations

import argparse
import json
import os
import random
import re
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
from collections import Counter

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))
from shared.db import get_client  # noqa: E402
from shared.env import load_env  # noqa: E402

try:
    from job_status import job_run  # scripts/job_status.py
except ImportError:  # pragma: no cover - allow running from repo root
    sys.path.insert(0, os.path.dirname(__file__))
    from job_status import job_run

API = "https://fieldsestate.com.au/api/v1/address-search"
DEFAULT_SUBURBS = ["varsity_lakes", "robina", "burleigh_waters"]

# Floors, not targets. Set from the measured post-topup state (2026-09-06: all six
# previously-failing probes returned correctly and first). A drop below these is a
# regression by definition — the addresses did not stop existing.
MIN_FOUND_PCT = 97.0
MIN_FIRST_PCT = 80.0


def norm(a: str | None) -> str:
    """Uppercase, strip punctuation, collapse whitespace — the 'same address' key.

    ⚠ PUNCTUATION MUST GO. We store `complete_address` unpunctuated
    ("31 MIKADO WAY ROBINA QLD 4226") and the API renders it for display with
    commas ("31 Mikado Way, Robina, QLD 4226"). A comparator that missed this
    scored 0/24 on its first live run against a site that was answering every
    probe correctly — a 100% false-failure rate. Worth stating plainly because
    the failure direction was the lucky one: had the harness compared loosely
    instead, it would have reported PASS forever and been worth nothing.

    The unit separator is preserved as a space, so "13/10 BEN LEXCEN" and
    "1310 BEN LEXCEN" cannot collide.
    """
    s = re.sub(r"[^A-Z0-9/]+", " ", (a or "").upper())
    return re.sub(r"\s+", " ", s.replace("/", " / ")).strip()


def display_name(key: str) -> str:
    return " ".join(w.capitalize() for w in key.split("_"))


def typed_query(src: dict, suburb_key: str) -> str | None:
    """Build the string a real owner would type, from what we hold.

    Owners type "12 Bardon Avenue Robina", not "12 BARDON AVENUE ROBINA QLD 4226".
    The stored `complete_address` carries the state and postcode; typing those was
    itself a bug once (FILLER_TOKENS, 2026-08-28), so the probe deliberately uses
    the shorter human form. Unit addresses keep their prefix — 1,002 of the 1,843
    addresses missing in September were units, and they are the shape that breaks.
    """
    street_no = str(src.get("STREET_NO_1") or "").strip()
    street_name = (src.get("STREET_NAME") or "").strip()
    street_type = (src.get("STREET_TYPE") or "").strip()
    # "XXX" is the GNAF placeholder for a street with no type ("The Links",
    # "The Esplanade"). Nobody types it, so probing it would manufacture a
    # failure the public can never hit and bury the real ones in noise.
    if street_type.upper() == "XXX":
        street_type = ""
    if not street_no or not street_name:
        return None
    # ⚠ UNIT_NUMBER, not UNIT_NO. The plausible-sounding guess is the wrong one
    # (Rule 8, verified with `db_fields.py Gold_Coast robina --grep UNIT`: 98% fill
    # on UNIT_NUMBER, no such path as UNIT_NO). Had this shipped unverified, every
    # unit probe would have silently tested the house at that street number
    # instead — the harness would have passed while blind to the 1,002 unit
    # addresses that were the actual September failure.
    unit = str(src.get("UNIT_NUMBER") or "").strip()
    lead = f"{unit}/{street_no}" if unit else street_no
    return " ".join(x for x in [lead, street_name, street_type, display_name(suburb_key)] if x)


def probe(query: str, timeout: int = 30) -> tuple[list, float, str | None]:
    """One live search. Returns (results, elapsed_seconds, error)."""
    url = f"{API}?{urllib.parse.urlencode({'q': query, 'limit': 10})}"
    t0 = time.time()
    try:
        req = urllib.request.Request(url, headers={"User-Agent": "fields-address-regression/1.0"})
        with urllib.request.urlopen(req, timeout=timeout) as r:
            body = json.load(r)
        elapsed = time.time() - t0
        results = body.get("results") if isinstance(body, dict) else body
        return (results or []), elapsed, None
    except urllib.error.HTTPError as e:
        return [], time.time() - t0, f"HTTP {e.code}"
    except Exception as e:  # timeout, JSON, connection
        return [], time.time() - t0, type(e).__name__


def sample_addresses(db, suburbs: list[str], n: int, seed: int) -> list[dict]:
    """Random $sample per suburb, proportional to n.

    ⚠ $sample, not find().limit(). CLAUDE.md Rule 8's cautionary tale is exactly
    this: SCHEMA_SNAPSHOT sampled the FIRST 5 documents of each collection, got
    the oldest and most uniform rows, and reported 75 fields where live listings
    carry 233. A prefix of a Cosmos collection is not a sample of it.
    """
    rng = random.Random(seed)
    per = max(1, n // len(suburbs))
    out = []
    for key in suburbs:
        coll = db[key]
        docs = list(coll.aggregate([
            {"$match": {"STREET_NAME": {"$exists": True, "$ne": None},
                        "STREET_NO_1": {"$exists": True, "$ne": None}}},
            {"$sample": {"size": per * 3}},  # oversample; typed_query rejects some
            {"$project": {"STREET_NO_1": 1, "STREET_NAME": 1, "STREET_TYPE": 1,
                          "UNIT_NUMBER": 1, "complete_address": 1}},
        ]))
        rng.shuffle(docs)
        picked = 0
        for d in docs:
            q = typed_query(d, key)
            if not q:
                continue
            out.append({"suburb": key, "query": q,
                        "expect": norm(d.get("complete_address")),
                        "expect_short": norm(q.rsplit(" ", len(key.split("_")))[0])})
            picked += 1
            if picked >= per:
                break
    rng.shuffle(out)
    return out


def matches(expect: str, expect_short: str, result_addr: str) -> bool:
    """Is this result the address we asked for?

    Compares on the stored `address` when we have it, else on the number+street
    prefix. Prefix comparison is anchored with a trailing space so that "3
    CASSOWARY" cannot be satisfied by "35 CASSOWARY" — the precise failure a
    Burleigh owner hit on 2026-09-06, where number 3 was absent and 35, 37 and 39
    were offered in its place.
    """
    r = norm(result_addr)
    if expect and r == expect:
        return True
    return bool(expect_short) and (r == expect_short or r.startswith(expect_short + " "))


def main() -> int:
    load_env()  # Rule 7 checklist item 3 — never trust the caller's environment
    ap = argparse.ArgumentParser()
    ap.add_argument("-n", "--probes", type=int, default=150)
    ap.add_argument("--suburbs", default=",".join(DEFAULT_SUBURBS))
    ap.add_argument("--seed", type=int, default=0, help="0 = time-varying (different rows each run)")
    ap.add_argument("--delay", type=float, default=0.35, help="seconds between probes")
    ap.add_argument("--scheduled", action="store_true",
                    help="arm the 7-day STALE threshold (set this in the cron line, not by hand)")
    ap.add_argument("--dry-run", action="store_true", help="print the probes, call nothing")
    args = ap.parse_args()

    suburbs = [s.strip() for s in args.suburbs.split(",") if s.strip()]
    seed = args.seed or int(time.time())
    # Weekly cadence either way; only the STALE alarm is gated on --scheduled.
    # 10**7 hours ~ 1,100 years: the row renders its last real outcome and never
    # ages into a false STALE while nothing is scheduled to run it.
    kw = {"cadence_hours": 168, "title": "Address Search Regression",
          "stale_hours": 168.0 if args.scheduled else 10.0**7}

    with job_run("address_search_regression", **kw) as beat:
        db = get_client()["Gold_Coast"]
        probes = sample_addresses(db, suburbs, args.probes, seed)

        if args.dry_run:
            for p in probes:
                print(f"  {p['suburb']:<16} {p['query']}")
            print(f"\n{len(probes)} probes (seed={seed}) — nothing called")
            return 0

        found = first = 0
        lat: list[float] = []
        failures: list[dict] = []
        errors: Counter = Counter()

        for i, p in enumerate(probes, 1):
            results, elapsed, err = probe(p["query"])
            lat.append(elapsed)
            if err:
                errors[err] += 1
            addrs = [(r.get("address") or r.get("full_address") or "") for r in results]
            hit = [j for j, a in enumerate(addrs) if matches(p["expect"], p["expect_short"], a)]
            if hit:
                found += 1
                if hit[0] == 0:
                    first += 1
                else:
                    failures.append({"kind": "not_first", "q": p["query"],
                                     "rank": hit[0] + 1, "top": addrs[0][:60]})
            else:
                failures.append({"kind": "absent", "q": p["query"], "err": err,
                                 "n_results": len(addrs), "top": (addrs[0][:60] if addrs else "")})
            if i % 25 == 0:
                print(f"  {i}/{len(probes)}  found={found}  first={first}", flush=True)
            time.sleep(args.delay)

        n = len(probes)
        found_pct = 100.0 * found / n if n else 0.0
        first_pct = 100.0 * first / n if n else 0.0
        lat.sort()
        p50 = lat[len(lat) // 2] if lat else 0.0
        p95 = lat[int(len(lat) * 0.95)] if lat else 0.0

        print(f"\n=== ADDRESS SEARCH REGRESSION — {n} probes over {', '.join(suburbs)} (seed={seed}) ===")
        print(f"  found  {found}/{n}  {found_pct:.1f}%   (floor {MIN_FOUND_PCT}%)")
        print(f"  first  {first}/{n}  {first_pct:.1f}%   (floor {MIN_FIRST_PCT}%)")
        print(f"  latency  p50 {p50:.2f}s   p95 {p95:.2f}s")
        if errors:
            print(f"  transport errors: {dict(errors)}")
        absent = [f for f in failures if f["kind"] == "absent"]
        notfirst = [f for f in failures if f["kind"] == "not_first"]
        for f in absent[:15]:
            print(f"  ABSENT     {f['q']}  ({f['n_results']} results"
                  + (f", err={f['err']}" if f.get("err") else "")
                  + (f", top='{f['top']}'" if f["top"] else "") + ")")
        for f in notfirst[:10]:
            print(f"  NOT-FIRST  {f['q']}  rank {f['rank']}, top='{f['top']}'")

        beat.metrics = {"probes": n, "found_pct": round(found_pct, 1),
                        "first_pct": round(first_pct, 1), "absent": len(absent),
                        "not_first": len(notfirst), "p50_s": round(p50, 2),
                        "p95_s": round(p95, 2), "transport_errors": sum(errors.values())}
        beat.detail = f"{found_pct:.1f}% found, {first_pct:.1f}% first, p95 {p95:.2f}s (n={n})"

        # ── Rule 7b: assert an OUTCOME. A run that probed nothing, or that could
        # not reach the API at all, must not read as a healthy zero — those are
        # the two shapes that let the March index sit broken for six months.
        if n == 0:
            raise RuntimeError("sampled 0 probeable addresses — the suburb collections or the "
                               "field names moved; this is a broken harness, not a clean site")
        if errors and sum(errors.values()) >= n * 0.5:
            raise RuntimeError(f"{sum(errors.values())}/{n} probes failed in transport "
                               f"({dict(errors)}) — the API is unreachable, not the index empty")
        if found_pct < MIN_FOUND_PCT:
            raise RuntimeError(
                f"found {found_pct:.1f}% < floor {MIN_FOUND_PCT}% — {len(absent)} addresses we HOLD "
                f"are not returned by the search box. First few: "
                + "; ".join(f['q'] for f in absent[:5]))
        if first_pct < MIN_FIRST_PCT:
            raise RuntimeError(
                f"first {first_pct:.1f}% < floor {MIN_FIRST_PCT}% — the right address is being "
                f"outranked by neighbours; clicking the top result reports the wrong property. "
                + "; ".join(f"{f['q']} (rank {f['rank']})" for f in notfirst[:5]))

        print("\n  PASS — both floors met")
    return 0


if __name__ == "__main__":
    sys.exit(main())
