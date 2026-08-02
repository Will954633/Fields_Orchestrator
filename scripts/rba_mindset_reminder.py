#!/usr/bin/env python3
"""
rba_mindset_reminder.py — nag until the homeowner mindset brief is revisited after an RBA decision.

WHY (2026-08-02): the mindset brief that shapes all 21 Market Pulse summaries leans heavily on rate
expectations — "no major bank expects a cut before 2027", "the four majors expect a hold". An RBA
decision can invalidate that overnight, and several published summaries reference the decision date
directly. A fixed 90-day staleness threshold does not catch this: the brief can be four days old and
already wrong. So the trigger is the event, not the age.

Fires the day AFTER each RBA decision and keeps firing daily until acknowledged, because a single
message on a busy morning is a message that gets missed.

Acknowledge with EITHER:
    python3 scripts/rba_mindset_reminder.py --done
    python3 scripts/refresh_homeowner_mindset.py     # refreshing the brief acknowledges implicitly

State lives in system_monitor.reminder_state so it survives restarts.

RBA_2026_DATES must be extended before 2027. If the list runs out the job says so loudly on the
health board rather than going quiet — a reminder that silently stops reminding is worse than none.
"""
from __future__ import annotations

import argparse
import os
import subprocess
import sys
from datetime import date, datetime, timedelta

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from job_status import job_run  # noqa: E402

REMINDER_ID = "rba_mindset_revisit"
MAX_NAG_DAYS = 14  # stop nagging after this, and flag it as unresolved rather than silently giving up

# RBA Board meeting decision dates. Source: rba.gov.au/schedules-events/board-meeting-schedules.html
RBA_2026_DATES = [
    date(2026, 2, 3), date(2026, 3, 17), date(2026, 5, 5), date(2026, 6, 16),
    date(2026, 8, 11), date(2026, 9, 29), date(2026, 11, 3), date(2026, 12, 8),
]


def _db():
    from src.mongo_client_factory import get_database
    return get_database("system_monitor")


def last_decision_on_or_before(today: date):
    past = [d for d in RBA_2026_DATES if d <= today]
    return max(past) if past else None


def state(db):
    return db["reminder_state"].find_one({"_id": REMINDER_ID}) or {}


def mark_done(db, decision: date | None, note: str = "manual"):
    db["reminder_state"].update_one(
        {"_id": REMINDER_ID},
        {"$set": {"_id": REMINDER_ID, "acknowledged_for": decision.isoformat() if decision else None,
                  "acknowledged_at": datetime.now(), "how": note}},
        upsert=True,
    )


def send(text: str):
    cmd = [sys.executable, os.path.join(os.path.dirname(os.path.abspath(__file__)),
                                        "telegram_notify.py"), text]
    proc = subprocess.run(cmd, capture_output=True, text=True, timeout=60)
    if proc.returncode != 0:
        raise RuntimeError(f"telegram_notify failed: {(proc.stderr or proc.stdout)[:300]}")


def brief_age_days():
    from homeowner_mindset import latest_report
    rep = latest_report()
    return rep["age_days"] if rep else None


def run(today: date, force: bool = False):
    db = _db()
    decision = last_decision_on_or_before(today)

    if not decision:
        return "no RBA decision has occurred yet in the configured schedule"

    if today > max(RBA_2026_DATES) + timedelta(days=MAX_NAG_DAYS):
        raise RuntimeError(
            "RBA_2026_DATES is exhausted — extend it with the 2027 board meeting dates from "
            "rba.gov.au/schedules-events/board-meeting-schedules.html, or this reminder stops firing."
        )

    days_since = (today - decision).days
    if days_since < 1 and not force:
        return f"RBA decision {decision} was today; the reminder fires tomorrow"

    st = state(db)
    if st.get("acknowledged_for") == decision.isoformat() and not force:
        return f"already acknowledged for the {decision} decision"

    # Refreshing the brief after the decision counts as acknowledgement — don't nag for work done.
    age = brief_age_days()
    if age is not None and age < days_since and not force:
        mark_done(db, decision, note="brief refreshed after the decision")
        return f"brief was refreshed {age}d ago, after the {decision} decision — acknowledged automatically"

    if days_since > MAX_NAG_DAYS and not force:
        raise RuntimeError(
            f"The {decision} RBA decision has gone {days_since} days without the mindset brief being "
            f"revisited. Nagging stopped at {MAX_NAG_DAYS} days; this is now an open item."
        )

    nag = st.get("nag_count", 0) + 1 if st.get("nagging_for") == decision.isoformat() else 1
    age_txt = f"{age} days old" if age is not None else "missing"
    send(
        f"*Market Pulse — revisit the homeowner mindset brief*\n\n"
        f"The RBA decided on {decision:%d %b %Y} ({days_since} day"
        f"{'s' if days_since != 1 else ''} ago).\n\n"
        f"The brief behind all 21 market summaries leans on rate expectations, and several "
        f"published summaries reference that decision. It is currently {age_txt}.\n\n"
        f"Refresh:  `python3 scripts/refresh_homeowner_mindset.py`\n"
        f"Or dismiss:  `python3 scripts/rba_mindset_reminder.py --done`\n\n"
        f"_Reminder {nag} — repeats daily until one of the above._"
    )
    db["reminder_state"].update_one(
        {"_id": REMINDER_ID},
        {"$set": {"_id": REMINDER_ID, "nagging_for": decision.isoformat(),
                  "nag_count": nag, "last_sent": datetime.now()}},
        upsert=True,
    )
    return f"reminder {nag} sent for the {decision} decision ({days_since}d ago, brief {age_txt})"


def main():
    ap = argparse.ArgumentParser(description="Nag until the mindset brief is revisited post-RBA")
    ap.add_argument("--done", action="store_true", help="acknowledge — stops the reminders")
    ap.add_argument("--status", action="store_true", help="show state, send nothing")
    ap.add_argument("--force", action="store_true", help="send regardless of acknowledgement")
    args = ap.parse_args()

    today = date.today()
    if args.done:
        d = last_decision_on_or_before(today)
        mark_done(_db(), d)
        print(f"Acknowledged for the {d} decision — reminders stopped.")
        return 0

    if args.status:
        st = state(_db())
        d = last_decision_on_or_before(today)
        print(f"last decision   : {d}")
        print(f"acknowledged for: {st.get('acknowledged_for')}")
        print(f"nagging for     : {st.get('nagging_for')} (count {st.get('nag_count', 0)})")
        print(f"brief age       : {brief_age_days()} days")
        return 0

    with job_run(REMINDER_ID, cadence_hours=24,
                 title="RBA → mindset brief revisit reminder") as beat:
        beat.detail = run(today, force=args.force)
        print(beat.detail)
    return 0


if __name__ == "__main__":
    sys.exit(main())
