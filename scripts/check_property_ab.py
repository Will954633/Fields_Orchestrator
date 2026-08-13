#!/usr/bin/env python3
"""
Check the /property A/B (currently A/A) — balance, metric coverage, and effect.

Run this during the A/A period BEFORE any V2 traffic. Its job is to answer three
questions, in this order, because the later ones are meaningless if an earlier one
fails:

  1. ARE THE ARMS BALANCED?      A 50/50 flag that lands 60/40 is not randomising.
  2. IS THE METRIC COMPLETE?     `page_engagement` replaced a ladder that silently
                                 dropped 34% of sessions — the fastest ones (median
                                 3s vs 49s). If coverage is not near-total, the new
                                 metric inherits the old survivor bias and the test
                                 is not decidable. THIS IS THE GATE.
  3. IS THERE A DIFFERENCE?      During A/A the honest answer is "there must not be".
                                 A significant result here means the harness is
                                 broken, not that we found something.

⚠ `page_engagement` can fire more than once per visit (tab hidden, then restored).
Take the MAX per session — never sum, never average raw rows. This script does that.

USAGE:
  python3 scripts/check_property_ab.py                 # last 7 days
  python3 scripts/check_property_ab.py --days 14
"""
import os
import sys
import math
import argparse

import requests

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from shared.env import load_env  # type: ignore

PROJECT = '348370'
FLAG = 'property_page_v2'


def query(sql):
    key = os.getenv('POSTHOG_ALL_ACCESS_KEY') or os.getenv('POSTHOG_PERSONAL_API_KEY')
    r = requests.post(
        f'https://us.posthog.com/api/projects/{PROJECT}/query/',
        headers={'Authorization': f'Bearer {key}'},
        json={'query': {'kind': 'HogQLQuery', 'query': sql}}, timeout=120)
    j = r.json()
    if 'results' not in j:
        raise RuntimeError(f'PostHog query failed: {str(j)[:300]}')
    return j['results']


def two_prop_z(k1, n1, k2, n2):
    """Two-proportion z-test. Returns (z, p) or None when it cannot be computed."""
    if not n1 or not n2:
        return None
    p1, p2 = k1 / n1, k2 / n2
    p = (k1 + k2) / (n1 + n2)
    se = math.sqrt(p * (1 - p) * (1 / n1 + 1 / n2))
    if se == 0:
        return None
    z = (p1 - p2) / se
    return z, math.erfc(abs(z) / math.sqrt(2))


def welch(m1, s1, n1, m2, s2, n2):
    """Welch's t-test on summary stats. Returns (t, p) or None."""
    if n1 < 2 or n2 < 2:
        return None
    se = math.sqrt(s1 * s1 / n1 + s2 * s2 / n2)
    if se == 0:
        return None
    t = (m1 - m2) / se
    # Normal approximation for p; fine at the n we will ever reach here.
    return t, math.erfc(abs(t) / math.sqrt(2))


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--days', type=int, default=7)
    args = ap.parse_args()
    load_env()
    d = args.days

    print(f'=== /property A/B check — last {d} days, flag `{FLAG}` ===\n')

    # 1. BALANCE — people per arm.
    rows = query(f"""
        SELECT properties['$feature/{FLAG}'] AS arm, count(DISTINCT person_id) AS people
        FROM events
        WHERE properties.$pathname LIKE '/property/%'
          AND timestamp > now() - INTERVAL {d} DAY
          AND properties['$feature/{FLAG}'] IS NOT NULL
        GROUP BY arm ORDER BY arm LIMIT 10""")
    arms = {r[0]: r[1] for r in rows}
    total = sum(arms.values())
    print('1. ARM BALANCE')
    if not total:
        print('   no assigned traffic yet — nothing to check\n')
        return
    for a, n in sorted(arms.items()):
        print(f'   {str(a):<10} {n:>5} people  ({100*n/total:.1f}%)')
    c, v = arms.get('control', 0), arms.get('v2', 0)
    if c and v:
        res = two_prop_z(c, c + v, (c + v) / 2, c + v)
        # Simple binomial check against 50/50 instead — clearer.
        z = abs(c - (c + v) / 2) / math.sqrt((c + v) * 0.25)
        p = math.erfc(z / math.sqrt(2))
        verdict = 'OK' if p > 0.05 else '⚠ IMBALANCED — assignment may be broken'
        print(f'   split test vs 50/50: z={z:.2f} p={p:.3f}  {verdict}')
    print()

    # 2. COVERAGE — the gate. What fraction of viewing sessions produced the metric?
    rows = query(f"""
        SELECT arm, uniqExact(sid) AS sessions,
               uniqExactIf(sid, has_engagement) AS with_metric
        FROM (
          SELECT $session_id AS sid,
                 any(properties['$feature/{FLAG}']) AS arm,
                 maxIf(1, event = 'page_engagement') AS has_engagement
          FROM events
          WHERE properties.$pathname LIKE '/property/%'
            AND timestamp > now() - INTERVAL {d} DAY
          GROUP BY sid
        ) WHERE arm IS NOT NULL GROUP BY arm ORDER BY arm LIMIT 10""")
    print('2. METRIC COVERAGE  (the gate — the old ladder managed only 66%)')
    worst = 1.0
    for r in rows:
        pct = r[2] / r[1] if r[1] else 0
        worst = min(worst, pct)
        print(f'   {str(r[0]):<10} {r[2]:>4}/{r[1]:<4} sessions have page_engagement  ({100*pct:.0f}%)')
    if rows:
        if worst >= 0.95:
            print('   OK — near-total coverage, the survivor bias is gone')
        elif worst >= 0.80:
            print('   ⚠ partial — better than the ladder but still censoring; investigate before deciding')
        else:
            print('   ⚠⚠ COVERAGE TOO LOW — metric still drops sessions; test NOT decidable')
    print()

    # 3. THE METRIC ITSELF — max per session, never summed.
    rows = query(f"""
        SELECT arm, count() AS sessions,
               avg(eng) AS mean_eng, stddevSamp(eng) AS sd_eng, median(eng) AS med_eng,
               avg(depth) AS mean_depth, stddevSamp(depth) AS sd_depth
        FROM (
          SELECT $session_id AS sid,
                 any(properties['$feature/{FLAG}']) AS arm,
                 max(toFloat(properties.engaged_seconds)) AS eng,
                 max(toFloat(properties.max_depth_pct)) AS depth
          FROM events
          WHERE event = 'page_engagement'
            AND properties.$pathname LIKE '/property/%'
            AND timestamp > now() - INTERVAL {d} DAY
          GROUP BY sid
        ) WHERE arm IS NOT NULL GROUP BY arm ORDER BY arm LIMIT 10""")
    print('3. ENGAGEMENT  (max per session)')
    stats = {}
    for r in rows:
        stats[r[0]] = r
        print(f'   {str(r[0]):<10} n={r[1]:<4} engaged mean={r[2]:.1f}s sd={r[3]:.1f} '
              f'median={r[4]:.0f}s | depth mean={r[5]:.0f}%')
    if 'control' in stats and 'v2' in stats:
        a, b = stats['control'], stats['v2']
        res = welch(a[2], a[3], a[1], b[2], b[3], b[1])
        if res:
            t, p = res
            print(f'\n   engaged_seconds: t={t:.2f} p={p:.3f}')
            if p < 0.05:
                print('   ⚠ SIGNIFICANT. During A/A this means the HARNESS is broken,')
                print('     not that a difference was found. Investigate before trusting anything.')
            else:
                print('   no significant difference — expected, and required, during A/A')
    print()
    print('Reminder: conversion (cta_click etc.) runs at ~2% on ~6 people/day and needs')
    print('~11 months to resolve a doubling. Treat it as directional only.')


if __name__ == '__main__':
    main()
