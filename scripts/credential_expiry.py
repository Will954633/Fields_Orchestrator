#!/usr/bin/env python3
"""
credential_expiry.py — watches credentials that expire on a KNOWN DATE, and warns early.

WHY. Fields has had six credential-expiry outages — Gmail twice, GitHub, a Google OAuth
refresh token, a two-month Facebook Ads blackout, and Bright Data (2026-08-11, which killed
every Domain.com.au fetch for 2.5 days and took nine health-board rows with it). Not one of
them had a watcher. CLAUDE.md Rule 7 makes a process prove it RAN; nothing made it prove the
secrets it depends on are still VALID.

This covers the half of that problem that is easy and certain: credentials whose expiry date
we already know. It is a calendar check, not a liveness probe — no network calls, nothing to
rate-limit, nothing to get blocked. The API-liveness half (does this token still return 200?)
is a separate, harder job; keeping them apart means the easy protection ships now rather than
waiting on the hard one.

TWO OF THESE ARE COMPLIANCE, NOT PLUMBING. The QLD real estate licence and the REIQ
membership are published on the website as claims about the business. If either lapses while
the footer still asserts it, that is not an outage — it is a false public statement by a
licensed agent. They are therefore warned about far earlier than a mere API key.

Add a credential: one entry in CREDENTIALS. Dates are AEST calendar dates.

Usage:
  credential_expiry.py                 # table of everything and its runway
  credential_expiry.py --check         # cron: warn on anything inside its lead time
  credential_expiry.py --json
"""
from __future__ import annotations

import argparse
import json
import sys
from datetime import date, datetime, timedelta, timezone

sys.path.insert(0, "/home/fields/Fields_Orchestrator")
sys.path.insert(0, "/home/fields/Fields_Orchestrator/scripts")

try:
    from zoneinfo import ZoneInfo
    AEST = ZoneInfo("Australia/Brisbane")
except Exception:  # pragma: no cover
    AEST = timezone(timedelta(hours=10))

# warn_days: how far ahead to start warning. Compliance items get months, because renewing a
# licence is not a five-minute job and lapsing it is not a five-minute problem.
CREDENTIALS = [
    {
        "name": "QLD real estate licence",
        "holder": "William Alfred Harold Simpson",
        "identifier": "4832972",
        "expires": "2027-01-17",
        "warn_days": 75,          # Will asked to be reminded in November
        "kind": "compliance",
        "note": "Published in the website footer. Renew in NOVEMBER 2026 — Will's own "
                "instruction. Without it he cannot lawfully act as an agent, and the footer "
                "claim becomes false.",
    },
    {
        "name": "REIQ Individual Membership",
        "holder": "William Simpson",
        "identifier": "156204",
        "expires": "2027-01-31",
        "warn_days": 60,
        "kind": "compliance",
        "note": "Published in the website footer. NOTE: this is INDIVIDUAL membership held "
                "by Will personally — it is NOT 'REIQ Accredited Agency', which the business "
                "does not hold. Never let the site claim otherwise.",
    },
    {
        # Not a credential — a dated legal deadline, tracked here because this is the only
        # thing that watches known expiry dates, and missing it has the same shape as
        # missing a renewal: a public claim quietly stops being correct.
        "name": "Property Occupations Regulation 2014 — expiry/remake",
        "holder": "Queensland",
        "identifier": "SL 2014-251",
        "expires": "2026-08-31",
        "warn_days": 30,
        "kind": "legal-watch",
        "note": "RE-CHECK THE FOOTER WHEN THIS LAPSES OR IS REMADE. Our decision to omit a "
                "street address rests on POA s.95(1) delegating advertising particulars to a "
                "regulation that prescribes NONE (it prescribes only for s.95(2), auction "
                "signage). Statutory Instruments Regulation 2022 s.5(1) sch.3 exempts this "
                "regulation from expiry only until 2026-08-31, ground 'subject to review'. A "
                "remake could prescribe advertising particulars for the first time and make "
                "a name/licence/address mandatory. Verify before assuming the footer is "
                "still compliant.",
    },
]


def _today():
    return datetime.now(timezone.utc).astimezone(AEST).date()


def rows():
    out = []
    today = _today()
    for c in CREDENTIALS:
        exp = date.fromisoformat(c["expires"])
        days = (exp - today).days
        if days < 0:
            state = "EXPIRED"
        elif days <= c["warn_days"]:
            state = "DUE"
        else:
            state = "ok"
        out.append({**c, "days_left": days, "state": state})
    return sorted(out, key=lambda r: r["days_left"])


def main():
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[1])
    ap.add_argument("--check", action="store_true",
                    help="cron mode: Telegram + heartbeat if anything is due")
    ap.add_argument("--json", action="store_true")
    a = ap.parse_args()

    rs = rows()
    if a.json:
        print(json.dumps(rs, indent=2, default=str))
        return

    if not a.check:
        print(f"{'credential':32s} {'ref':10s} {'expires':11s} {'left':>6s}  state")
        for r in rs:
            print(f"{r['name']:32s} {r['identifier']:10s} {r['expires']:11s} "
                  f"{r['days_left']:>5d}d  {r['state']}")
        return

    # --check: the cron path. Rule 7b — assert an outcome, and make "nothing due" a
    # DIFFERENT, explicit result from "the check could not run".
    due = [r for r in rs if r["state"] in ("DUE", "EXPIRED")]
    detail = (f"{len(rs)} credential(s) tracked; "
              + (f"{len(due)} due: " + ", ".join(f"{r['name']} ({r['days_left']}d)" for r in due)
                 if due else "none due"))

    if due:
        lines = ["🔐 *Credential renewal due*", ""]
        for r in due:
            when = ("**EXPIRED**" if r["days_left"] < 0
                    else f"{r['days_left']} days left")
            lines += [f"*{r['name']}* — {when}",
                      f"  {r['holder']} · ref {r['identifier']} · expires {r['expires']}",
                      f"  {r['note']}", ""]
        lines.append("_These are published on the website. A lapsed credential that the "
                     "footer still claims is a false public statement, not just an outage._")
        try:
            from telegram_notify import send_message
            send_message("\n".join(lines))
        except Exception as e:
            print(f"telegram failed: {e}")

    try:
        from job_status import record_job_result
        record_job_result("credential_expiry",
                          "error" if any(r["state"] == "EXPIRED" for r in rs) else "success",
                          cadence_hours=24, stale_hours=40,
                          title="Credential expiry watch (licence, REIQ)",
                          detail=detail)
    except Exception as e:
        print(f"job_status failed: {e}")
    print(detail)


if __name__ == "__main__":
    main()
