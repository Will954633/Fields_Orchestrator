#!/usr/bin/env python3
"""
fb_approval.py — Telegram yes/no approval gate for FB-organic posts (Will's ask, 2026-07-29).

FB-organic posting is PUBLIC-facing, so it is gated: the loop PROPOSES a post → Will gets a Telegram
→ Will replies YES/NO on @WillFieldsBot → only on YES does it publish. This reads Will's reply from
`system_monitor.ceo_chat_messages` (the CEO bridge already captures every inbound Telegram message on
that bot) — so it does NOT compete with the bridge for Telegram's update offset.

Flow:
  propose(text)  → fb_pending_posts {status: awaiting_approval, token} + Telegram Will with the token.
  poll()         → find Will's "YES/NO <token>" reply since the proposal → publish (fb-page-post) or skip
                   → Telegram confirmation. Auto-expires after 24h.

Usage:
  fb_approval.py propose --text "..." [--tags a,b]
  fb_approval.py poll [--dry-run]          # cron every ~3 min
  fb_approval.py list
"""
import argparse
import os
import re
import subprocess
import sys
from datetime import datetime, timedelta, timezone

sys.path.insert(0, "/home/fields/Fields_Orchestrator")
sys.path.insert(0, "/home/fields/Fields_Orchestrator/scripts")
from shared.db import get_client  # noqa: E402

NOW = datetime.now(timezone.utc)
COLL = "fb_pending_posts"
EXPIRE_H = 24
YES = re.compile(r"\b(yes|post|approve|ok|go)\b", re.I)
NO = re.compile(r"\b(no|skip|reject|don'?t|hold)\b", re.I)


def _tg(msg):
    try:
        from telegram_notify import send_message
        send_message(msg)
    except Exception as e:
        print("telegram send failed:", e)


def _sm():
    return get_client()["system_monitor"]


def _token():
    import hashlib
    return hashlib.sha1(NOW.isoformat().encode()).hexdigest()[:4].upper()


def propose(text, tags):
    tok = _token()
    _sm()[COLL].insert_one({
        "text": text, "token": tok, "status": "awaiting_approval",
        "source": "fb_organic_rl", "tags": tags or [], "created_at": NOW.isoformat(),
    })
    _tg(f"📣 Proposed Facebook post  [#{tok}]\n\n{text}\n\n"
        f"Reply  YES {tok}  to publish  ·  NO {tok}  to skip  (expires in {EXPIRE_H}h)")
    print(f"proposed post #{tok} (awaiting Will's Telegram approval)")


def _wills_verdict(sm, post):
    """Read ceo_chat_messages for Will's YES/NO reply for this post's token, after it was proposed."""
    since = post["created_at"]
    tok = post["token"]
    for m in sm["ceo_chat_messages"].find(
            {"role": "user", "platform": "telegram", "created_at": {"$gt": since}}).sort("_id", 1):
        t = (m.get("text") or "")
        if tok.lower() in t.lower() or _single_pending(sm):
            if YES.search(t) and tok.lower() in t.lower():
                return "yes"
            if NO.search(t) and tok.lower() in t.lower():
                return "no"
            # bare yes/no allowed only if this is the ONLY pending post
            if _single_pending(sm):
                if YES.search(t):
                    return "yes"
                if NO.search(t):
                    return "no"
    return None


def _single_pending(sm):
    return sm[COLL].count_documents({"status": "awaiting_approval"}) == 1


def poll(dry_run=False):
    sm = _sm()
    acted = 0
    for post in sm[COLL].find({"status": "awaiting_approval"}):
        # expire
        try:
            age_h = (NOW - datetime.fromisoformat(post["created_at"])).total_seconds() / 3600
        except Exception:
            age_h = 0
        if age_h > EXPIRE_H:
            if not dry_run:
                sm[COLL].update_one({"_id": post["_id"]}, {"$set": {"status": "expired"}})
            print(f"#{post['token']} expired"); continue
        verdict = _wills_verdict(sm, post)
        if not verdict:
            continue
        acted += 1
        if verdict == "yes":
            print(f"#{post['token']} APPROVED by Will" + (" (dry-run)" if dry_run else ""))
            if not dry_run:
                r = subprocess.run([sys.executable, "/home/fields/Fields_Orchestrator/scripts/fb-page-post.py",
                                    "--message", post["text"], "--post"], capture_output=True, text=True, timeout=60)
                ok = r.returncode == 0
                sm[COLL].update_one({"_id": post["_id"]},
                                    {"$set": {"status": "posted" if ok else "post_failed",
                                              "posted_at": NOW.isoformat(), "post_output": (r.stdout or r.stderr)[:200]}})
                _tg(f"✅ Posted FB post #{post['token']}" if ok else f"⚠️ FB post #{post['token']} FAILED: {(r.stderr or '')[:120]}")
        else:
            print(f"#{post['token']} SKIPPED by Will" + (" (dry-run)" if dry_run else ""))
            if not dry_run:
                sm[COLL].update_one({"_id": post["_id"]}, {"$set": {"status": "skipped", "skipped_at": NOW.isoformat()}})
                _tg(f"🚫 Skipped FB post #{post['token']} (per your reply).")
    print(f"poll done — acted on {acted} post(s)")


def _list():
    for p in _sm()[COLL].find({"status": {"$in": ["awaiting_approval", "posted", "skipped"]}}).sort("_id", -1).limit(10):
        print(f"  #{p.get('token')} {p.get('status'):<18} {p.get('created_at','')[:16]}  «{(p.get('text') or '')[:50]}»")


def main():
    ap = argparse.ArgumentParser()
    sub = ap.add_subparsers(dest="cmd", required=True)
    pr = sub.add_parser("propose"); pr.add_argument("--text", required=True); pr.add_argument("--tags", default="")
    po = sub.add_parser("poll"); po.add_argument("--dry-run", action="store_true")
    sub.add_parser("list")
    a = ap.parse_args()
    if a.cmd == "propose":
        propose(a.text, [t for t in a.tags.split(",") if t])
    elif a.cmd == "poll":
        # poll() PUBLISHES to a public Facebook page, so it must run exactly once per
        # invocation. It used to sit inside a try whose except re-ran it, which meant any
        # heartbeat failure (or a mid-flight poll error) silently double-polled AND left no
        # heartbeat — the board then read "not firing" while the poller was in fact running
        # twice. Import guard only; poll() runs once; a heartbeat failure is raised, not
        # swallowed, so it lands in logs/fb_approval.log instead of vanishing.
        try:
            from job_status import record_job_result
        except Exception:
            record_job_result = None
        poll(a.dry_run)
        if record_job_result and not a.dry_run:
            record_job_result("fb_approval_poll", "success", cadence_hours=1,
                              title="FB-organic Telegram approval poller", detail="ok")
    elif a.cmd == "list":
        _list()


if __name__ == "__main__":
    main()
