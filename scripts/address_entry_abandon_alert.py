#!/usr/bin/env python3
"""
address_entry_abandon_alert.py — Telegram alert for abandoned address entries.

Someone typed a real address into the site's address search box and left WITHOUT
selecting a result (the "typed but never submitted" case). The shared
<AddressSearch> component beacons each such event to
system_monitor.address_entry_attempts (via netlify/functions/address-entry-log.mjs);
this job reads the un-alerted ones and notifies Will, prioritising zero-result
searches — a real address that matched nothing is a lost seller lead.

Rule 7/7b:
  - Wrapped in job_run(cadence_hours=1) so it self-registers on the Systems Health
    sheet and any exception (e.g. DB unreachable) is recorded as ERROR.
  - "No un-alerted rows" is a legitimate SUCCESS (empty queue), NOT a failure.
  - Per-doc `alerted` flag instead of a time watermark — a failed run marks
    nothing, so the next run re-processes the exact same rows (no permanent loss).
  - Rows are only marked alerted AFTER the Telegram send succeeds; if the send
    raises, the rows stay un-alerted and the heartbeat records the error.

Run: python3 scripts/address_entry_abandon_alert.py
Cron: every hour (see install note at bottom).
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from shared.env import load_env
from shared.db import get_client
from telegram_notify import send_message
from job_status import job_run

MAX_PER_MESSAGE = 20          # cap a single digest; older ones roll to next run
FB_AD_HINT = "utm_source=facebook"


def _converted(sysmon, doc) -> bool:
    """True if this person actually submitted later (so it wasn't really an
    abandonment — e.g. they tab-switched, came back, and completed). Suppresses
    the alert. Joins on device_token (our stable key) and PostHog session id."""
    dt = doc.get("device_token")
    sid = doc.get("posthog_session_id")
    checks = []
    if dt:
        checks.append(("campaign_leads", {"device_token": dt}))
        checks.append(("property_reports", {"owner.device_token": dt}))
        checks.append(("analyse_leads", {"device_token": dt}))
    if sid:
        checks.append(("campaign_leads", {"posthog_session_id": sid}))
    for coll, q in checks:
        try:
            if sysmon[coll].find_one(q):
                return True
        except Exception:
            pass  # a missing collection/field is not a conversion
    return False


def _fmt(doc) -> str:
    q = doc.get("longest_query") or doc.get("final_query") or "(unknown)"
    rc = doc.get("last_result_count")
    page = doc.get("page") or ""
    when = (doc.get("client_ts") or doc.get("received_at") or "")[:19].replace("T", " ")
    dt = doc.get("device_token")
    # Zero results = the search FAILED to match a real address they typed.
    if rc == 0:
        head = "🔴 SEARCH FAILED (0 results)"
    elif rc is None:
        head = "⚪ typed, no search recorded"
    else:
        head = f"🟡 {rc} shown, none picked"
    line = f"{head}\n   “{q}”"
    # Trim page to the useful bits (path + campaign/content).
    short_page = page.split("?")[0]
    tags = []
    if FB_AD_HINT in page:
        import urllib.parse as up
        qs = up.parse_qs(page.split("?", 1)[1]) if "?" in page else {}
        camp = (qs.get("utm_campaign") or [""])[0]
        content = (qs.get("utm_content") or [""])[0]
        tags.append("FB ad" + (f": {camp}/{content}" if camp else ""))
    meta = f"   {short_page}"
    if tags:
        meta += "  ·  " + " ".join(tags)
    line += "\n" + meta
    if dt:
        line += f"\n   returning visitor (token …{dt[-6:]})"
    if when:
        line += f"\n   {when}"
    return line


def main():
    load_env()
    with job_run("address_entry_abandon_alert", cadence_hours=1,
                 title="Address Entry Abandonment Alerts") as beat:
        sysmon = get_client()["system_monitor"]
        attempts = sysmon["address_entry_attempts"]

        # Un-alerted, not-selected, and either a failed search or a real-looking
        # address. (If the collection doesn't exist yet, find() yields nothing —
        # a legitimate empty queue, not an error.)
        query = {
            "alerted": {"$ne": True},
            "selected": {"$ne": True},
            "$or": [{"zero_result": True}, {"looks_like_address": True}],
        }
        pending = list(attempts.find(query).sort("received_at", 1).limit(200))

        scanned = len(pending)
        to_alert, suppressed_ids = [], []
        for doc in pending:
            if _converted(sysmon, doc):
                suppressed_ids.append(doc["_id"])
            else:
                to_alert.append(doc)

        zero = sum(1 for d in to_alert if d.get("last_result_count") == 0)
        beat.metrics = {
            "scanned": scanned,
            "to_alert": len(to_alert),
            "suppressed": len(suppressed_ids),
            "zero_result": zero,
        }

        # Suppressed (converted-after-all) rows: mark alerted so we don't rescan.
        if suppressed_ids:
            attempts.update_many(
                {"_id": {"$in": suppressed_ids}},
                {"$set": {"alerted": True, "alert_suppressed": True}},
            )

        if not to_alert:
            beat.detail = f"scanned {scanned}, nothing to alert ({len(suppressed_ids)} suppressed)"
            return  # empty queue = success (Rule 7b: no work to do)

        batch = to_alert[:MAX_PER_MESSAGE]
        n = len(to_alert)
        noun = "entry" if n == 1 else "entries"
        zero_note = ""
        if zero:
            zero_note = f" — {zero} failed search" + ("" if zero == 1 else "es")
        header = (f"📍 *{n} abandoned address {noun}*{zero_note}\n"
                  "Someone typed an address and left without selecting a result.\n")
        body = "\n\n".join(_fmt(d) for d in batch)
        if len(to_alert) > MAX_PER_MESSAGE:
            body += f"\n\n…and {len(to_alert) - MAX_PER_MESSAGE} more (next run)."

        # Send FIRST; only mark alerted if it succeeds. A raised send => error
        # heartbeat and rows stay un-alerted for the next run.
        send_message(header + "\n" + body, parse_mode="Markdown")

        attempts.update_many(
            {"_id": {"$in": [d["_id"] for d in batch]}},
            {"$set": {"alerted": True}},
        )
        beat.detail = f"alerted {len(batch)} ({zero} failed searches), {len(suppressed_ids)} suppressed"


if __name__ == "__main__":
    main()
