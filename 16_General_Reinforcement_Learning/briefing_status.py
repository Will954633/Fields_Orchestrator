#!/usr/bin/env python3
"""
briefing_status.py — tracks whether each domain's standing brief is current, and chases Will.

WHY (Will, 2026-08-13). The domain agents were producing careful analysis and then asking
permission for nearly all of it, because they had no way to know what Will already intends.
"FB ads are off on purpose" and "FB ads have broken" look identical from the data. So the
fix is not more autonomy in the abstract — it is giving each domain a written statement of
direction, agreed weekly with Will, that it can act inside.

That makes the brief an AUTHORISATION, not a memo. Which in turn makes staleness costly and
worth chasing: a domain running on a three-week-old brief is acting on three-week-old
intent, and the honest response is to narrow what it may do on its own.

Freshness tiers (see `verdict()`):
  current  — updated within 7 days. Full standing authorisations apply.
  aging    — 8-13 days. Still authorised; Will is reminded.
  stale    — 14-20 days. Authorisations NARROWED to bug-fixes-only by the contract.
  expired  — 21+ days, or no brief at all. Recommend-only.

`--remind` is idempotent per day: it sends at most one Telegram per calendar day (AEST)
regardless of how often cron fires it, so a daily chase cannot become a pager storm.

CLI:
  briefing_status.py                 # table of every domain's freshness
  briefing_status.py --json
  briefing_status.py --remind        # Telegram Will if anything needs the session
  briefing_status.py --touch seo     # record that a brief was updated today
"""
from __future__ import annotations

import argparse
import json
import re
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

sys.path.insert(0, "/home/fields/Fields_Orchestrator")

try:
    from zoneinfo import ZoneInfo
    AEST = ZoneInfo("Australia/Brisbane")
except Exception:  # pragma: no cover
    AEST = timezone(timedelta(hours=10))

DIR = Path("/home/fields/Fields_Orchestrator/16_General_Reinforcement_Learning")
BRIEF_DIR = DIR / "briefings"
DOMAINS = ["geo", "seo", "ads", "articles", "onsite", "ops"]

CURRENT_DAYS = 7
AGING_DAYS = 14
STALE_DAYS = 21

# What each tier means for the domain's autonomy. The contract quotes these verbatim, so
# the agent reads the same words the reminder does.
TIER_EFFECT = {
    "current": "full standing authorisations apply",
    "aging":   "full standing authorisations apply (brief due)",
    "stale":   "NARROWED — bug fixes restoring stated intent only; no new initiatives",
    "expired": "RECOMMEND-ONLY — no autonomous change beyond sensors and analysis",
}


def _now():
    return datetime.now(timezone.utc)


def _today_aest():
    return _now().astimezone(AEST).strftime("%Y-%m-%d")


def _parse_updated(path: Path):
    """Read '**Last updated:** YYYY-MM-DD' from the brief. Falls back to file mtime, but
    reports which was used — a brief edited without bumping the header is a real failure
    mode and the caller should be able to see it."""
    try:
        head = path.read_text(encoding="utf-8", errors="replace")[:2000]
    except Exception:
        return None, "unreadable"
    m = re.search(r"\*\*Last updated:\*\*\s*(\d{4}-\d{2}-\d{2})", head)
    if m:
        try:
            return datetime.strptime(m.group(1), "%Y-%m-%d").replace(tzinfo=AEST), "header"
        except ValueError:
            pass
    try:
        return datetime.fromtimestamp(path.stat().st_mtime, tz=AEST), "mtime"
    except Exception:
        return None, "unreadable"


def verdict(age_days):
    if age_days is None:
        return "expired"
    if age_days < CURRENT_DAYS:
        return "current"
    if age_days < AGING_DAYS:
        return "aging"
    if age_days < STALE_DAYS:
        return "stale"
    return "expired"


def _authorisations(path: Path):
    """Count real bullet entries under §4. A brief can be perfectly fresh and still
    authorise nothing — which is exactly the state of a seeded brief Will has not yet
    completed. Reporting that as 'full standing authorisations apply' would be worse than
    useless: it reads as permission where none was granted."""
    try:
        t = path.read_text(encoding="utf-8", errors="replace")
    except Exception:
        return 0
    m = re.search(r"##\s*4\.\s*Standing authorisations.*?\n(.*?)(?=\n##\s|\Z)", t, re.S | re.I)
    if not m:
        return 0
    body = m.group(1)
    n = 0
    for ln in body.split("\n"):
        s = ln.strip()
        # An italic placeholder — "*(empty — Will to complete...)*" — opens with an
        # asterisk and would otherwise be counted as a bullet, silently reporting an
        # unauthorised domain as fully authorised. Skip italic/parenthetical notes.
        if s.startswith("*(") or s.startswith("_(") or s.startswith("("):
            continue
        if not re.match(r"^([-*+]|\d+\.)\s+", s):
            continue
        content = re.sub(r"^([-*+]|\d+\.)\s+", "", s).strip()
        if content.startswith("(") or content.startswith("*("):
            continue
        if len(content) > 3:
            n += 1
    return n


def status(domain):
    path = BRIEF_DIR / f"{domain}.md"
    if not path.exists():
        return {"domain": domain, "exists": False, "age_days": None,
                "tier": "expired", "effect": TIER_EFFECT["expired"],
                "updated": None, "source": None, "authorisations": 0,
                "path": str(path)}
    updated, source = _parse_updated(path)
    if updated is None:
        age = None
    else:
        age = (_now().astimezone(AEST).date() - updated.date()).days
    t = verdict(age)
    n_auth = _authorisations(path)
    effect = TIER_EFFECT[t]
    if n_auth == 0 and t in ("current", "aging"):
        effect = ("§4 EMPTY — nothing authorised yet; domain proposes and ships nothing "
                  "until Will completes the briefing session")
    return {"domain": domain, "exists": True, "age_days": age, "tier": t,
            "effect": effect, "authorisations": n_auth,
            "updated": updated.strftime("%Y-%m-%d") if updated else None,
            "source": source, "path": str(path)}


def all_status():
    return [status(d) for d in DOMAINS]


def _reminder_state():
    from shared.db import get_client
    return get_client()["system_monitor"]["rl_briefing_reminders"]


def cmd_remind(a):
    rows = all_status()
    needs = [r for r in rows if r["tier"] != "current" or r["authorisations"] == 0]
    if not needs:
        print("all briefs current — no reminder sent")
        return

    coll = _reminder_state()
    today = _today_aest()
    prior = coll.find_one({"_id": "state"}) or {}
    if prior.get("last_sent_date") == today and not a.force:
        print(f"already reminded today ({today}) — not sending again")
        return

    streak = prior.get("streak", 0) + 1 if prior.get("last_sent_date") else 1
    worst = min(r["age_days"] if r["age_days"] is not None else 999 for r in needs)

    lines = []
    if streak == 1:
        lines.append("📋 *Weekly briefing session* — time to update the domain briefs.")
    else:
        lines.append(f"📋 *Briefing session still outstanding* (day {streak}).")
    lines.append("")
    lines.append("Each brief is what lets that domain act on its own. While it is stale the")
    lines.append("domain keeps analysing but stops being able to ship anything new.")
    lines.append("")
    for r in sorted(needs, key=lambda x: -(x["age_days"] or 999)):
        age = "never written" if not r["exists"] else f"{r['age_days']}d old"
        lines.append(f"• *{r['domain']}* — {age} → {r['effect']}")
    lines.append("")
    lines.append("Reply here with what's changed per domain and I'll write the briefs up,")
    lines.append("or say 'start briefing' and I'll walk them one at a time.")

    text = "\n".join(lines)
    try:
        from scripts.telegram_notify import send_message
        send_message(text)
        coll.replace_one({"_id": "state"},
                         {"_id": "state", "last_sent_date": today, "streak": streak,
                          "worst_age_days": worst,
                          "domains": [r["domain"] for r in needs],
                          "sent_at": _now().isoformat()}, upsert=True)
        print(f"reminder sent (day {streak}, {len(needs)} domain(s) outstanding)")
    except Exception as e:
        print(f"TELEGRAM FAILED: {e}")
        sys.exit(1)


def cmd_touch(a):
    """Record that a brief was updated. Rewrites the Last-updated header so the header and
    reality cannot drift apart."""
    path = BRIEF_DIR / f"{a.touch}.md"
    if not path.exists():
        sys.exit(f"ERROR: no brief at {path}")
    t = path.read_text(encoding="utf-8")
    today = _today_aest()
    new, n = re.subn(r"(\*\*Last updated:\*\*\s*)\d{4}-\d{2}-\d{2}",
                     rf"\g<1>{today}", t, count=1)
    if n == 0:
        sys.exit("ERROR: no '**Last updated:** YYYY-MM-DD' line found — add one first.")
    path.write_text(new, encoding="utf-8")
    # Clear the chase streak once every brief is current again.
    if all(r["tier"] == "current" for r in all_status()):
        try:
            _reminder_state().replace_one(
                {"_id": "state"},
                {"_id": "state", "last_sent_date": None, "streak": 0,
                 "cleared_at": _now().isoformat()}, upsert=True)
            print("all briefs now current — reminder streak cleared")
        except Exception as e:
            print(f"(could not clear reminder state: {e})")
    print(f"{a.touch}: Last updated -> {today}")


def main():
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[1])
    ap.add_argument("--json", action="store_true")
    ap.add_argument("--remind", action="store_true", help="Telegram Will if any brief is due")
    ap.add_argument("--force", action="store_true", help="send even if already sent today")
    ap.add_argument("--touch", metavar="DOMAIN", help="mark a brief as updated today")
    ap.add_argument("--domain", help="show one domain only")
    a = ap.parse_args()

    if a.touch:
        return cmd_touch(a)
    if a.remind:
        return cmd_remind(a)

    rows = [status(a.domain)] if a.domain else all_status()
    if a.json:
        print(json.dumps(rows, indent=2))
        return
    print(f"{'domain':10s} {'updated':12s} {'age':>5s}  {'tier':8s} effect")
    for r in rows:
        age = "—" if r["age_days"] is None else f"{r['age_days']}d"
        upd = r["updated"] or "(none)"
        flag = " ⚠" if r["source"] == "mtime" else ""
        print(f"{r['domain']:10s} {upd:12s} {age:>5s}  {r['tier']:8s} {r['effect']}{flag}")
    if any(r["source"] == "mtime" for r in rows):
        print("\n⚠ = date taken from file mtime, not the '**Last updated:**' header. "
              "Someone edited the brief without bumping the header.")


if __name__ == "__main__":
    main()
