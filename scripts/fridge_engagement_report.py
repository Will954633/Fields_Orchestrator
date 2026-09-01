#!/usr/bin/env python3
"""
fridge_engagement_report.py — daily standing answer to "are the fridge magnets
attracting any engagement?"

Rolls up system_monitor.fridge_scans (the per-device ledger written by
netlify/functions/fridge-event.mjs) into a plain summary: how many devices
scanned the QR, how many opened the fridge, how many actually did something, how
many entered their address, and how many CRM households that produced. Reports
the last-24h numbers with the all-time totals for context.

Self-monitoring (CLAUDE.md Rule 7): wrapped in job_run so it shows on the Process
Registry / Systems Health sheet and can never fail silently. Rule 7b: ZERO scans
is a VALID outcome here — "nobody has scanned the magnet yet" is exactly the
signal Will is testing for, so we do NOT raise on zero. We raise only when the
DB/query itself fails (couldn't measure), which is the real failure mode.

Run:  python3 scripts/fridge_engagement_report.py            # daily (cron)
      python3 scripts/fridge_engagement_report.py --no-telegram
      python3 scripts/fridge_engagement_report.py --days 7
"""
import argparse
import os
import sys
from datetime import datetime, timedelta, timezone

_SCRIPTS = os.path.dirname(os.path.abspath(__file__))
_ROOT = os.path.dirname(_SCRIPTS)
sys.path.insert(0, _SCRIPTS)   # job_status, telegram_notify
sys.path.insert(0, _ROOT)      # shared.db, shared.env

from job_status import job_run  # noqa: E402


def _db():
    """Connect the same way the rest of the orchestrator does (settings.yaml /
    COSMOS_CONNECTION_STRING). Load our own env so a cron line missing `set -a`
    still authenticates (Rule 7 step 3)."""
    try:
        from shared.env import load_env
        load_env()
    except Exception:
        pass
    from shared.db import get_client
    return get_client()["system_monitor"]


AEST = timezone(timedelta(hours=10))


def summarise(db, days: int) -> dict:
    scans = db["fridge_scans"]
    since = datetime.now(timezone.utc) - timedelta(days=days)

    # All-time
    total_devices = scans.count_documents({})
    total_opens = scans.count_documents({"open_count": {"$gt": 0}})
    total_engaged = scans.count_documents({"engagement_count": {"$gt": 0}})
    total_address = scans.count_documents({"event_counts.fridge_address_go": {"$gt": 0}})

    # Rolling window (by last activity)
    win = {"last_activity_at": {"$gte": since}}
    win_devices = scans.count_documents(win)
    win_opens = scans.count_documents({**win, "open_count": {"$gt": 0}})
    win_engaged = scans.count_documents({**win, "engagement_count": {"$gt": 0}})
    win_address = scans.count_documents({**win, "event_counts.fridge_address_go": {"$gt": 0}})

    # New devices whose FIRST scan is in the window (true new reach)
    new_devices = scans.count_documents({"first_scan_at": {"$gte": since}})

    # CRM households the magnet has produced (contacts carrying a fridge_engagement)
    crm = db["crm_contacts"]
    crm_households = crm.count_documents({"fridge_engagement.address_slug": {"$exists": True}})

    # Which suburbs / addresses have been entered (for the human-readable line)
    recent_addresses = [
        d.get("fridge_engagement", {}).get("address")
        for d in crm.find(
            {"fridge_engagement.updated_at": {"$gte": since}},
            {"fridge_engagement.address": 1},
        ).limit(10)
    ]
    recent_addresses = [a for a in recent_addresses if a]

    return {
        "days": days,
        "all_time": {
            "devices": total_devices, "opened": total_opens,
            "engaged": total_engaged, "address_entered": total_address,
            "crm_households": crm_households,
        },
        "window": {
            "active_devices": win_devices, "new_devices": new_devices,
            "opened": win_opens, "engaged": win_engaged,
            "address_entered": win_address,
        },
        "recent_addresses": recent_addresses,
    }


def render(s: dict) -> str:
    a, w = s["all_time"], s["window"]
    lines = [
        "🧲 *Fridge magnet — engagement*",
        f"_last {s['days']}d · {datetime.now(AEST):%d %b %H:%M AEST}_",
        "",
        f"*Last {s['days']}d:*  {w['new_devices']} new scans · "
        f"{w['opened']} opened · {w['engaged']} engaged · "
        f"{w['address_entered']} entered address",
        f"*All time:*  {a['devices']} devices · {a['opened']} opened · "
        f"{a['engaged']} engaged · {a['address_entered']} gave an address "
        f"→ {a['crm_households']} CRM households",
    ]
    if s["recent_addresses"]:
        lines.append("")
        lines.append("*Addresses entered:*")
        lines += [f"  • {addr}" for addr in s["recent_addresses"]]
    if a["devices"] == 0:
        lines.append("")
        lines.append("_No scans recorded yet — magnet not (measurably) in the wild._")
    return "\n".join(lines)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--days", type=int, default=1)
    ap.add_argument("--no-telegram", action="store_true")
    args = ap.parse_args()

    with job_run("fridge_engagement_report", cadence_hours=24,
                 title="Fridge Magnet Engagement") as beat:
        db = _db()                          # any DB failure here raises → status=error
        s = summarise(db, args.days)
        msg = render(s)
        print(msg)

        if not args.no_telegram:
            try:
                from telegram_notify import send_message
                send_message(msg)
            except Exception as e:
                # Telegram down must not fail the measurement job; note it and move on.
                print(f"[warn] telegram send failed: {e}", file=sys.stderr)

        beat.detail = (f"{s['window']['new_devices']} new / "
                       f"{s['all_time']['devices']} total devices, "
                       f"{s['all_time']['address_entered']} addresses")
        beat.metrics = {
            "devices_total": s["all_time"]["devices"],
            "opened_total": s["all_time"]["opened"],
            "engaged_total": s["all_time"]["engaged"],
            "address_total": s["all_time"]["address_entered"],
            "crm_households": s["all_time"]["crm_households"],
            "new_devices_window": s["window"]["new_devices"],
        }
        # NB: no raise on zero — zero scans is the very signal being measured, a
        # legitimate success. The only failure is not being able to read the DB,
        # which throws above and is recorded as status=error by job_run.


if __name__ == "__main__":
    main()
