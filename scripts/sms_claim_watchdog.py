#!/usr/bin/env python3
"""
sms_claim_watchdog.py — proves the off-market SMS claim step is still alive.

The claim step is a Netlify webhook, so it cannot heartbeat itself the way a cron
job can: it only runs when someone texts us, and the failure we actually fear is
that it STOPS running. A dead webhook and a quiet Tuesday look identical from the
inside. So this checks from the outside, hourly, and asks the only question that
matters:

    did a text arrive at JustCall that never became a claim?

That single comparison catches every delivery failure at once — an unregistered
webhook, a blacklisted URL, a rotated secret, a Netlify outage, a crash in the
function — without needing to know which one happened.

Two further checks, because they fail silently and are cheap to test:

  THE WEBHOOK IS STILL REGISTERED AND ACTIVE. JustCall tracks a
  `blacklisted_url_count` and will stop delivering to a URL that has been erroring;
  nothing tells us when that happens.

  THE ENDPOINT STILL REJECTS AN UNSIGNED CALL. If a deploy ever dropped the
  secret check, this endpoint becomes a way for anyone to send SMS on our
  account. Better to find that from here than from the bill.

Run hourly:
    5 * * * * cd /home/fields/Fields_Orchestrator && /home/fields/venv/bin/python3 \
              scripts/sms_claim_watchdog.py >> logs/sms_claim_watchdog.log 2>&1
"""
from __future__ import annotations

import os
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

import requests

sys.path.insert(0, str(Path(__file__).resolve().parent))
from job_status import job_run  # noqa: E402

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from shared.db import get_client  # noqa: E402
from shared.env import load_env  # noqa: E402

# Load our own environment rather than relying on the crontab line to source it.
# Cron runs with almost no environment and from $HOME, and a watchdog that only
# works when invoked by hand is worse than none — it reports "no problems"
# precisely because it never ran.
load_env()

JC = "https://api.justcall.io/v2.1"
ENDPOINT = "https://fieldsestate.com.au/api/v1/justcall-sms"
# Wide enough to survive a slow deploy or a retry, narrow enough that a real
# outage is caught within the hour.
GRACE_MIN = 10
WINDOW_H = 24
# The webhook was registered at this moment. Texts before it were never going to
# be answered by anything, and flagging them is noise, not a finding — the very
# first check did exactly that with Will's 12:47 AEST test. Self-expiring: once
# this is more than WINDOW_H in the past it stops mattering, and it is kept only
# so the reason is on the record.
LIVE_SINCE = datetime(2026, 8, 4, 3, 4, 53, tzinfo=timezone.utc)


def auth() -> dict:
    key, secret = os.environ["JUSTCALL_API_KEY"], os.environ["JUSTCALL_API_SECRET"]
    return {"Authorization": f"{key}:{secret}", "Accept": "application/json"}


def telegram(text: str) -> None:
    tok, chat = os.getenv("TELEGRAM_BOT_TOKEN"), os.getenv("TELEGRAM_CHAT_ID")
    if not tok or not chat:
        return
    try:
        requests.post(f"https://api.telegram.org/bot{tok}/sendMessage",
                      json={"chat_id": chat, "text": text}, timeout=15)
    except requests.RequestException:
        pass          # a failed alert must not fail the check


def main() -> None:
    with job_run("sms_claim_watchdog", cadence_hours=1,
                 title="Off-Market SMS Claim Watchdog") as beat:
        problems: list[str] = []

        # 1. Is the webhook still registered, and not blacklisted?
        r = requests.get(f"{JC}/webhooks", headers=auth(), timeout=30)
        r.raise_for_status()
        hooks = r.json().get("data") or []
        registered = any(
            "justcall-sms" in str(u.get("webhook_url", ""))
            and str(u.get("status", "")).lower() == "active"
            for h in hooks for u in (h.get("webhook_urls") or [])
        )
        if not registered:
            problems.append("The sms.received webhook is NOT registered and Active. "
                            "Inbound claims are being dropped.")

        # 2. Does the endpoint still refuse an unsigned call?
        try:
            probe = requests.post(ENDPOINT, json={}, timeout=30)
            if probe.status_code != 403:
                problems.append(
                    f"The endpoint answered an UNSIGNED POST with {probe.status_code}, "
                    "not 403. Anyone could be sending SMS on our account.")
        except requests.RequestException as exc:
            problems.append(f"The endpoint is unreachable: {exc}")

        # 3. The one that matters: a text that never became a claim.
        r = requests.get(f"{JC}/texts", headers=auth(),
                         params={"per_page": 100, "sort": "id", "order": "desc"}, timeout=30)
        r.raise_for_status()
        cutoff = max(datetime.now(timezone.utc) - timedelta(hours=WINDOW_H), LIVE_SINCE)
        settled = datetime.now(timezone.utc) - timedelta(minutes=GRACE_MIN)

        inbound = []
        for t in r.json().get("data") or []:
            if str(t.get("direction", "")).lower() != "incoming":
                continue
            body = ((t.get("sms_info") or {}).get("body") or "").strip()
            if not body.lower().startswith("send"):
                continue
            # sms_date/sms_time are UTC; sms_user_* are the account's local time.
            try:
                when = datetime.strptime(f"{t['sms_date']} {t['sms_time']}",
                                         "%Y-%m-%d %H:%M:%S").replace(tzinfo=timezone.utc)
            except (KeyError, ValueError):
                continue
            if cutoff <= when <= settled:
                inbound.append((when, body, t.get("contact_number")))

        # MATCH EACH MESSAGE, DO NOT COMPARE COUNTS. Counting says "5 in, 5
        # logged, all well" even when two of the logged rows are synthetic tests
        # and two real texts were dropped. A count can only ever detect a
        # shortfall in total, and the failure we are looking for is a specific
        # message that went missing — so look for that specific message.
        db = get_client()["system_monitor"]
        logged = list(db["sms_claims"].find(
            {"received_at": {"$gte": cutoff - timedelta(minutes=GRACE_MIN)}},
            {"received_at": 1, "from": 1, "body": 1}))

        def digits(n) -> str:
            return "".join(ch for ch in str(n or "") if ch.isdigit())

        missed = []
        for when, body, number in inbound:
            hit = any(
                digits(c.get("from")) == digits(number)
                and (c.get("body") or "").strip().lower() == body.lower()
                and abs((c["received_at"].replace(tzinfo=timezone.utc) - when).total_seconds())
                    <= GRACE_MIN * 60
                for c in logged if c.get("received_at"))
            if not hit:
                missed.append((when, body, number))

        if missed:
            lines = "\n".join(f"  {w:%d %b %H:%M} {b!r} from {n}" for w, b, n in missed[:5])
            problems.append(
                f"{len(missed)} inbound claim text(s) in the last {WINDOW_H}h never reached "
                f"the webhook — received by JustCall, no claim recorded:\n{lines}")

        beat.metrics = {"inbound_24h": len(inbound), "claims_logged_24h": len(logged),
                        "unanswered": len(missed), "registered": registered,
                        "problems": len(problems)}

        if problems:
            body = "\n\n".join(problems)
            beat.detail = f"{len(problems)} problem(s)"
            telegram(f"🚨 SMS claim step\n\n{body}")
            print(f"PROBLEMS:\n{body}")
            raise RuntimeError(f"{len(problems)} problem(s) with the SMS claim step")

        beat.detail = (f"ok — {len(inbound)} inbound / {len(logged)} logged in {WINDOW_H}h, "
                       "webhook active, endpoint sealed")
        print(beat.detail)


if __name__ == "__main__":
    main()
