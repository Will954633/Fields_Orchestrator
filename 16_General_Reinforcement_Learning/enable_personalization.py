#!/usr/bin/env python3
"""
enable_personalization.py — flip the master kill-switch for onsite personalization (Will's #1).

Will authorised (2026-07-29): flip `genrl_personalization_v1` ON *after* the onsite cycle proposes
its first experiment + a load re-check. This: (1) confirms a serving experiment exists, (2) enables
the PostHog master flag, (3) re-measures /analyse-your-home load, (4) Telegrams Will (with an easy
"disable" path). Instant-reversible: `--disable` turns the flag off (page reverts to default).

Usage: python3 enable_personalization.py [--rollout 100] [--force] | --disable
"""
import argparse
import json
import os
import subprocess
import sys
import urllib.request

sys.path.insert(0, "/home/fields/Fields_Orchestrator")
sys.path.insert(0, "/home/fields/Fields_Orchestrator/scripts")
from shared.db import get_client  # noqa: E402
FLAG = "genrl_personalization_v1"


def _ph(method, path, body=None):
    pid = os.environ["POSTHOG_PROJECT_ID"]; key = os.environ["POSTHOG_PERSONAL_API_KEY"]
    req = urllib.request.Request(f"https://us.posthog.com/api/projects/{pid}/{path}",
        data=json.dumps(body).encode() if body is not None else None, method=method,
        headers={"Authorization": f"Bearer {key}", "Content-Type": "application/json"})
    return json.loads(urllib.request.urlopen(req, timeout=30).read())


def _flag_id():
    for f in _ph("GET", "feature_flags/?limit=200").get("results", []):
        if f["key"] == FLAG:
            return f["id"]
    return None


def _tg(m):
    try:
        from telegram_notify import send_telegram; send_telegram(m)
    except Exception as e:
        print("telegram failed:", e)


def _ttfb():
    r = subprocess.run(["curl", "-s", "-o", "/dev/null", "-w", "%{time_starttransfer}",
                        "https://fieldsestate.com.au/analyse-your-home", "--max-time", "20"],
                       capture_output=True, text=True, timeout=25)
    return r.stdout.strip()


def enable(rollout, force):
    sm = get_client()["system_monitor"]
    serving = list(sm["rl_onsite_experiments"].find({"status": "serving"}))
    if not serving and not force:
        print("No serving experiment yet — not flipping (use --force to override).")
        return False
    fid = _flag_id()
    body = {"key": FLAG, "name": "[GenRL] master onsite personalization kill-switch",
            "active": True, "filters": {"groups": [{"rollout_percentage": rollout}]}}
    if fid:
        _ph("PATCH", f"feature_flags/{fid}/", {"active": True, "filters": body["filters"]})
    else:
        _ph("POST", "feature_flags/", body)
    ttfb = _ttfb()
    exp = serving[0] if serving else {}
    msg = (f"🟢 Onsite personalization ENABLED ({rollout}% rollout).\n"
           f"Serving experiment: {exp.get('_id','?')} — «{(exp.get('hypothesis') or '')[:60]}»\n"
           f"/analyse-your-home TTFB now {ttfb}s (baseline ~0.43s; the slot renders AFTER LCP so first "
           f"paint is unaffected). Watch PostHog web-vitals over the next day.\n"
           f"To turn OFF instantly: it's the '{FLAG}' flag — or run enable_personalization.py --disable.")
    _tg(msg); print(msg)
    return True


def disable():
    fid = _flag_id()
    if fid:
        _ph("PATCH", f"feature_flags/{fid}/", {"active": False})
    _tg(f"🔴 Onsite personalization DISABLED — /analyse-your-home reverted to default.")
    print("disabled.")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--rollout", type=int, default=100)
    ap.add_argument("--force", action="store_true")
    ap.add_argument("--disable", action="store_true")
    a = ap.parse_args()
    if a.disable:
        disable()
    else:
        enable(a.rollout, a.force)


if __name__ == "__main__":
    main()
