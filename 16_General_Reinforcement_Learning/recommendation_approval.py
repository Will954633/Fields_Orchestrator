#!/usr/bin/env python3
"""
recommendation_approval.py — decide a recommendation from Telegram, without waiting for Sunday.

WHY (Will, 2026-08-13). Recommendations were only ever put to Will inside Samantha's weekly
brief, so a domain that filled its 2-item cap on Monday sat blocked until the following
Sunday. That happened the same day it was built: articles had 15 verified-clean drafts and
two open recommendations, and stopped.

This reuses the article-approval mechanics exactly — inline buttons, verdicts read out of
`ceo_chat_messages`, never a second `getUpdates` consumer — because that path is proven and
because Will already knows how it behaves.

THE REASON IS THE PRODUCT, and the button design reflects that:

  ✅ Approve   — records immediately. A bare yes is a complete answer; nothing is learned by
                 forcing him to justify agreeing.
  ✏️ No        — records nothing yet. It replies asking WHY, because `recommendations.py
  ⏳ Later        verdict` requires a reason and, more importantly, the reason is what gets
                 replayed to the domain next cycle. A rejection with no reason teaches it
                 nothing and it re-proposes the same thing. So a tap alone is not enough for
                 these two; he must send `RV NO <token> because ...`.

Usage:
  recommendation_approval.py send --id REC-articles-002   # one item to Telegram
  recommendation_approval.py send --all                   # every open item (drip-capped)
  recommendation_approval.py poll                         # cron: read verdicts, record them
  recommendation_approval.py list
"""
from __future__ import annotations

import argparse
import re
import secrets
import subprocess
import sys
from datetime import datetime, timedelta, timezone

DIR = "/home/fields/Fields_Orchestrator/16_General_Reinforcement_Learning"
sys.path.insert(0, "/home/fields/Fields_Orchestrator")
sys.path.insert(0, "/home/fields/Fields_Orchestrator/scripts")
sys.path.insert(0, DIR)
from shared.db import get_client  # noqa: E402

NOW = datetime.now(timezone.utc)
PENDING = "rl_recommendation_approvals"
RECS = "rl_recommendations"
EXPIRE_H = 168          # a week — it would otherwise reach him in the Sunday brief anyway
MAX_SENDS_PER_DAY = 4   # the brief's cap is 5; never out-shout it

# "RV YES 3F2A" / "RV NO 3F2A because the sample is too small"
VERDICT_RE = re.compile(r"\bRV\s+(YES|NO|LATER)\s+([0-9A-F]{4})\b(.*)", re.I | re.S)


def _sm():
    return get_client()["system_monitor"]


def _tg(msg, keyboard=None):
    from telegram_notify import send_message
    return send_message(msg, reply_markup=keyboard) if keyboard else send_message(msg)


def _keyboard(tok):
    return {"inline_keyboard": [[
        {"text": "✅ Approve", "callback_data": f"RV YES {tok}"},
        {"text": "✏️ No", "callback_data": f"RV NO {tok}"},
        {"text": "⏳ Later", "callback_data": f"RV LATER {tok}"},
    ]]}


def cmd_send(a):
    sm = _sm()
    q = {"status": "open"}
    if a.id:
        q["_id"] = a.id
    recs = list(sm[RECS].find(q).sort("created_at", 1))
    if not recs:
        sys.exit("nothing open to send" if not a.id else f"{a.id} is not open")

    since = (NOW - timedelta(hours=24)).isoformat()
    sent_today = sm[PENDING].count_documents({"sent_at": {"$gt": since}})
    sent = 0
    for r in recs:
        if sm[PENDING].find_one({"rec_id": r["_id"], "status": "awaiting"}):
            print(f"  {r['_id']}: already awaiting a verdict — skipped")
            continue
        if sent_today + sent >= MAX_SENDS_PER_DAY and not a.force:
            print(f"  drip cap reached ({MAX_SENDS_PER_DAY}/day) — {r['_id']} waits")
            break

        tok = secrets.token_hex(2).upper()
        ee = r.get("expected_effect") or {}
        sm[PENDING].insert_one({"rec_id": r["_id"], "token": tok, "status": "awaiting",
                                "sent_at": NOW.isoformat()})
        _tg(f"📌 *Decision needed* [#{tok}]  ·  `{r['_id']}`\n\n"
            f"*{r.get('title')}*\n"
            f"_{r.get('domain')} · {r.get('effort')} · {r.get('reversibility')}_\n\n"
            f"{str(r.get('claim'))[:420]}\n\n"
            f"*Proposed:* {str(r.get('proposed'))[:320]}\n\n"
            f"*Evidence (n={r.get('basis_n') or 'not stated'}):*\n{str(r.get('evidence'))[:380]}\n\n"
            + (f"*Expects:* {ee.get('metric')} {ee.get('direction') or ''}"
               + (f" by {ee.get('by')}" if ee.get('by') else "") + "\n\n" if ee.get("metric") else "")
            + f"➡️ *{r.get('ask')}*\n\n"
            f"_Tap ✅ to approve. For *No* or *Later*, send the reason — "
            f"`RV NO {tok} <why>` — it goes back to the {r.get('domain')} agent and is how it learns._",
            keyboard=_keyboard(tok))
        print(f"  sent {r['_id']} as #{tok}")
        sent += 1
    print(f"{sent} sent")


def cmd_poll(a):
    sm = _sm()
    acted = 0
    for pend in sm[PENDING].find({"status": "awaiting"}):
        age_h = (NOW - datetime.fromisoformat(pend["sent_at"])).total_seconds() / 3600
        if age_h > EXPIRE_H:
            sm[PENDING].update_one({"_id": pend["_id"]}, {"$set": {"status": "expired"}})
            continue

        verdict, reason = None, None
        for m in sm["ceo_chat_messages"].find(
                {"role": "user", "created_at": {"$gt": pend["sent_at"]}}).sort("_id", 1):
            hit = VERDICT_RE.search((m.get("text") or "").strip())
            if hit and hit.group(2).upper() == pend["token"]:
                verdict = hit.group(1).lower()
                reason = (hit.group(3) or "").strip(" .,:;-—\n")
        if not verdict:
            continue

        # A bare yes is a complete answer. A bare no is not — the reason is what the domain
        # reads next cycle, and without it the same proposal comes back unchanged.
        if verdict in ("no", "later") and not reason:
            if not pend.get("reason_prompted"):
                sm[PENDING].update_one({"_id": pend["_id"]},
                                       {"$set": {"reason_prompted": True}})
                _tg(f"✏️ Noted on `{pend['rec_id']}` — what's the reason?\n"
                    f"Send `RV {verdict.upper()} {pend['token']} <why>`.\n"
                    f"_Recorded verbatim and replayed to the domain; without it the same "
                    f"proposal comes back next week unchanged._")
            continue

        if a.dry_run:
            print(f"[dry-run] {pend['rec_id']} -> {verdict} ({reason!r})")
            acted += 1
            continue

        r = subprocess.run(
            [sys.executable, f"{DIR}/recommendations.py", "verdict",
             "--id", pend["rec_id"], "--verdict", verdict,
             "--reason", reason or "approved via Telegram, no comment"],
            capture_output=True, text=True)
        ok = r.returncode == 0
        sm[PENDING].update_one({"_id": pend["_id"]}, {"$set": {
            "status": "recorded" if ok else "record_failed",
            "verdict": verdict, "reason": reason, "decided_at": NOW.isoformat()}})
        _tg(f"{'✅' if ok else '⚠️'} `{pend['rec_id']}` → *{verdict}*"
            + (f"\n_{reason}_" if reason else "")
            + ("" if ok else f"\n⚠️ recording FAILED: {r.stderr.strip()[:160]}"))
        print(f"{pend['rec_id']} -> {verdict} ({'ok' if ok else 'FAILED'})")
        acted += 1
    print(f"poll complete — {acted} decision(s)")


def cmd_list(a):
    for p in _sm()[PENDING].find().sort("_id", -1).limit(15):
        print(f"#{p['token']:5s} {p.get('status',''):14s} {p['rec_id']:22s} "
              f"{str(p.get('verdict') or '')}")


def main():
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[1])
    sub = ap.add_subparsers(dest="cmd", required=True)
    s = sub.add_parser("send"); s.add_argument("--id"); s.add_argument("--all", action="store_true")
    s.add_argument("--force", action="store_true"); s.set_defaults(f=cmd_send)
    s = sub.add_parser("poll"); s.add_argument("--dry-run", action="store_true"); s.set_defaults(f=cmd_poll)
    s = sub.add_parser("list"); s.set_defaults(f=cmd_list)
    a = ap.parse_args()
    a.f(a)


if __name__ == "__main__":
    main()
