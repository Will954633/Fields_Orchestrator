#!/usr/bin/env python3
"""
Probe Bright Data auth and report, in one place, whether the unlocker route works.

Written 2026-08-15 because the failure is spread across three endpoints that
disagree with each other: `get_active_zones` lists the zone as active, while
`status` says `can_make_requests: false, auth_fail_reason: zone_not_found` and
the proxy itself returns `407 Invalid Auth`. Reading any one of them alone gives
the wrong answer.

Read-only. Makes a handful of probe calls and spends effectively nothing.

    source /home/fields/venv/bin/activate
    set -a && source /home/fields/Fields_Orchestrator/.env && set +a
    python3 scripts/probe_brightdata_auth.py
"""
import os
import sys

import requests

sys.path.insert(0, "/home/fields/Fields_Orchestrator")
from shared.env import load_env  # noqa: E402


def main():
    load_env()
    key = os.environ.get("BRIGHTDATA_API_KEY")
    if not key:
        print("BRIGHTDATA_API_KEY is not set — load .env first")
        return 2
    print(f"key present: yes (…{key[-6:]})")
    h = {"Authorization": f"Bearer {key}"}

    for label, url in [
        ("status          ", "https://api.brightdata.com/status"),
        ("active zones    ", "https://api.brightdata.com/zone/get_active_zones"),
        ("customer balance", "https://api.brightdata.com/customer/balance"),
    ]:
        try:
            r = requests.get(url, headers=h, timeout=20)
            print(f"{label}: HTTP {r.status_code} {r.text[:300]}")
        except Exception as e:
            print(f"{label}: FAILED {type(e).__name__}: {e}")

    zone = os.environ.get("BRIGHTDATA_ZONE", "web_unlocker2")
    try:
        r = requests.get(f"https://api.brightdata.com/zone/passwords?zone={zone}",
                         headers=h, timeout=20)
        pw = (r.json().get("passwords") or [None])[0] if r.status_code == 200 else None
        print(f"zone '{zone}' password fetch: HTTP {r.status_code} "
              f"({'got a password' if pw else 'no password'})")
    except Exception as e:
        print(f"zone password fetch FAILED: {type(e).__name__}: {e}")
        return 1

    if not pw:
        return 1
    # The proxy is the only probe that reflects whether traffic actually flows;
    # the management API can report a zone healthy while this still 407s.
    cust = "fieldsestate"
    try:
        c = requests.get("https://api.brightdata.com/status", headers=h, timeout=20)
        cust = c.json().get("customer", cust)
    except Exception:
        pass
    proxy = (f"http://brd-customer-{cust}-zone-{zone}-session-probe01"
             f":{pw}@brd.superproxy.io:33335")
    s = requests.Session()
    s.verify = False  # Web Unlocker presents its own CA
    try:
        r = s.get("https://geo.brdtest.com/mygeo.json",
                  proxies={"http": proxy, "https": proxy}, timeout=45)
        print(f"PROXY TEST: HTTP {r.status_code} {r.text[:200]}")
        print("VERDICT: proxy works" if r.status_code == 200 else "VERDICT: proxy REJECTED")
        return 0 if r.status_code == 200 else 1
    except Exception as e:
        print(f"PROXY TEST FAILED: {type(e).__name__}: {str(e)[:250]}")
        print("VERDICT: proxy unusable — the unlocker route is down")
        return 1


if __name__ == "__main__":
    sys.exit(main())
