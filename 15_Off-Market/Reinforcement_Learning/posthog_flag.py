#!/usr/bin/env python3
"""
posthog_flag.py — create / kill / inspect PostHog feature flags for the Off-Market RL loop.

The cycle's content/format experiments should be REAL PostHog flags (instant kill/adjust via
API — no code deploy needed), not just code-level deterministic splits. Flag WRITES need the
`feature_flag:write` scope: use `POSTHOG_ALL_ACCESS_KEY` (the PERSONAL key is read-only — that's
why cycle 3 fell back to a hash). The deck reads flags via `phGetFlag(key)` and expects a
multivariate flag returning the variant key string (e.g. "teaser"/"control").

  posthog_flag.py --create KEY --variants control:50,teaser:50 [--name "..."]
  posthog_flag.py --kill KEY        # active=false (deterministic-hash fallback takes over)
  posthog_flag.py --to-control KEY  # roll 100% to the first variant (safe default, keeps flag active)
  posthog_flag.py --get KEY | --list
"""
import argparse
import json
import os
import sys
import urllib.request
import urllib.error

PID = os.environ["POSTHOG_PROJECT_ID"]
KEY = os.environ.get("POSTHOG_ALL_ACCESS_KEY")  # WRITES need this (not POSTHOG_PERSONAL_API_KEY)
BASE = f"https://us.posthog.com/api/projects/{PID}/feature_flags/"


def _req(url, method="GET", body=None):
    if not KEY:
        sys.exit("POSTHOG_ALL_ACCESS_KEY not set — flag writes need it (personal key is read-only).")
    data = json.dumps(body).encode() if body is not None else None
    r = urllib.request.Request(url, data=data, method=method,
                               headers={"Authorization": f"Bearer {KEY}", "Content-Type": "application/json"})
    try:
        with urllib.request.urlopen(r, timeout=25) as resp:
            return json.loads(resp.read() or "{}")
    except urllib.error.HTTPError as e:
        sys.exit(f"HTTP {e.code}: {e.read().decode()[:200]}")


def _find(key):
    for f in _req(f"{BASE}?limit=300").get("results", []):
        if f.get("key") == key:
            return f
    return None


def create(key, variants, name):
    if _find(key):
        print(f"flag '{key}' already exists (id {_find(key)['id']}) — use --to-control/--kill to change it")
        return
    mv = [{"key": k, "rollout_percentage": int(p)} for k, p in variants]
    body = {"key": key, "name": name or f"Off-Market RL experiment: {key}", "active": True,
            "filters": {"groups": [{"properties": [], "rollout_percentage": 100}],
                        "multivariate": {"variants": mv}}}
    d = _req(BASE, "POST", body)
    print(f"created '{key}' (id {d['id']}), variants {[v['key']+':'+str(v['rollout_percentage']) for v in mv]}, active")


def kill(key):
    f = _find(key) or sys.exit(f"flag '{key}' not found")
    _req(f"{BASE}{f['id']}/", "PATCH", {"active": False})
    print(f"KILLED '{key}' (active=false) — deterministic-hash fallback in the deck takes over")


def to_control(key):
    f = _find(key) or sys.exit(f"flag '{key}' not found")
    mv = f["filters"]["multivariate"]["variants"]
    first = mv[0]["key"]
    for v in mv:
        v["rollout_percentage"] = 100 if v["key"] == first else 0
    _req(f"{BASE}{f['id']}/", "PATCH", {"filters": f["filters"]})
    print(f"'{key}' rolled 100% → '{first}' (flag stays active)")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--create"); ap.add_argument("--variants", default="control:50,teaser:50")
    ap.add_argument("--name", default="")
    ap.add_argument("--kill"); ap.add_argument("--to-control"); ap.add_argument("--get")
    ap.add_argument("--list", action="store_true")
    a = ap.parse_args()
    if a.create:
        create(a.create, [tuple(v.split(":")) for v in a.variants.split(",")], a.name)
    elif a.kill:
        kill(a.kill)
    elif a.to_control:
        to_control(a.to_control)
    elif a.get:
        print(json.dumps(_find(a.get), indent=2, default=str))
    elif a.list:
        for f in _req(f"{BASE}?limit=300").get("results", []):
            mv = (f.get("filters", {}).get("multivariate") or {}).get("variants", [])
            print(f"  {f['key']:32} active={f['active']} variants={[v['key']+':'+str(v['rollout_percentage']) for v in mv]}")
    else:
        ap.print_help()


if __name__ == "__main__":
    main()
