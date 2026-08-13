#!/usr/bin/env python3
"""
article_approval.py — Telegram approve / reject-with-feedback gate for article drafts.

WHY (Will, 2026-08-13, approved same day). Every article needs Will's explicit yes before it
goes live (his rule, 2026-07-29). That gate is correct — public content is his call — but it
had no mechanism, so drafts accumulated and the articles domain became the most constrained
one we have. 53 articles published to date have produced 0 conversions, so the bottleneck was
never a shortage of ideas.

His ask: send drafts to Telegram with approve / disapprove-with-feedback buttons.

DESIGN NOTES — two constraints shaped this, and both are worth knowing before editing it:

  1. **Reply keyboard, NOT inline buttons.** `ceo-telegram-bridge.py:1345` requests
     `allowed_updates: ["message", "edited_message"]` — it does not receive `callback_query`.
     Inline buttons would therefore fire into a void. A *reply* keyboard sends an ordinary
     text message, which the bridge already captures into `ceo_chat_messages`, so Will gets
     real buttons on a path that is known to work. (The bridge uses the same trick itself —
     see `workflow_reply_markup()`.)

  2. **Read replies from Mongo, never from getUpdates.** Telegram allows exactly one consumer
     of an update offset. The bridge owns it. Polling here would silently steal Will's
     messages from it. `fb_approval.py` established this pattern; this follows it exactly.

REJECTION FEEDBACK IS THE POINT. An approval flow that only records yes/no teaches the
articles domain nothing — it would keep proposing the same kind of draft. Everything Will
types after NO is stored on the article as `will_feedback` and replayed to the domain, the
same way recommendation verdicts are.

Flow:
  propose --id <article_id>   -> status awaiting_approval + token + Telegram with buttons
  poll                        -> read Will's reply -> publish, or record feedback and hold
  list                        -> what is pending

Usage:
  article_approval.py propose --id <mongo _id or slug>
  article_approval.py poll [--dry-run]        # cron every few minutes
  article_approval.py list
"""
from __future__ import annotations

import argparse
import os
import re
import secrets
import subprocess
import sys
from datetime import datetime, timedelta, timezone

sys.path.insert(0, "/home/fields/Fields_Orchestrator")
sys.path.insert(0, "/home/fields/Fields_Orchestrator/scripts")
from shared.db import get_client  # noqa: E402

NOW = datetime.now(timezone.utc)
ARTICLES = "content_articles"
PENDING = "article_pending_approval"
EXPIRE_H = 72          # longer than fb_approval's 24h — an article is not time-critical

YES = re.compile(r"\b(yes|approve|approved|publish|ok|👍|✅)\b", re.I)
NO = re.compile(r"\b(no|reject|rejected|hold|don'?t|nope|👎|❌)\b", re.I)


def _sm():
    return get_client()["system_monitor"]


def _token():
    return secrets.token_hex(2).upper()


def _keyboard(tok):
    """A reply keyboard — tapping a key sends its text as a normal message, which the CEO
    bridge captures. Inline buttons would not reach us (see module docstring)."""
    return {
        "keyboard": [
            [{"text": f"YES {tok}"}, {"text": f"NO {tok}"}],
        ],
        "resize_keyboard": True,
        "one_time_keyboard": True,
        "input_field_placeholder": f"Tap, or type: NO {tok} <your feedback>",
    }


def _tg(msg, keyboard=None):
    from telegram_notify import send_message
    try:
        return send_message(msg, reply_markup=keyboard) if keyboard else send_message(msg)
    except TypeError:
        # send_message may not accept reply_markup; fall back rather than lose the message.
        return send_message(msg)


def _find_article(sm, ident):
    from bson import ObjectId
    for q in ({"_id": ident}, {"slug": ident}):
        d = sm[ARTICLES].find_one(q)
        if d:
            return d
    try:
        return sm[ARTICLES].find_one({"_id": ObjectId(ident)})
    except Exception:
        return None


def cmd_propose(a):
    sm = _sm()
    art = _find_article(sm, a.id)
    if not art:
        sys.exit(f"ERROR: no article matching {a.id!r} in {ARTICLES}")
    if sm[PENDING].find_one({"article_id": art["_id"], "status": "awaiting_approval"}):
        sys.exit(f"already awaiting approval: {art.get('title')}")

    tok = _token()
    title = art.get("title") or "(untitled)"
    slug = art.get("slug") or ""
    body = art.get("html") or art.get("markdown") or art.get("body") or ""
    plain = re.sub(r"\s+", " ", re.sub(r"<[^>]+>", " ", body)).strip()
    words = len(plain.split())
    # Prefer the hand-written excerpt if the article has one — it is what a reader would
    # see, and it is a better basis for a publish decision than the first 400 characters.
    excerpt = (art.get("custom_excerpt") or "").strip() or plain[:400]

    sm[PENDING].insert_one({
        "article_id": art["_id"], "slug": slug, "title": title, "token": tok,
        "status": "awaiting_approval", "created_at": NOW.isoformat(),
    })

    # Drafts are already reachable at their live URL: db.server.ts findArticle() looks up by
    # slug or _id and does NOT filter on status, so the real page renders — hero image,
    # charts, styling and all — without publishing anything or building a preview route.
    # Nothing links to it and it is not in the sitemap, so it stays effectively unlisted.
    url = f"https://fieldsestate.com.au/articles/{slug}" if slug else None

    _tg(f"📝 *Article draft for approval*  [#{tok}]\n\n"
        f"*{title}*\n"
        f"_{words} words_\n\n"
        f"{excerpt}…\n\n"
        + (f"📄 [Read the full draft]({url})\n_(live preview — hero image and all; "
           f"still unpublished)_\n\n" if url else
           "_⚠ No slug on this article, so there is no preview link._\n\n")
        + f"Tap *YES {tok}* to publish, or *NO {tok}* — and add why, e.g.\n"
        f"`NO {tok} too generic, needs the Robina median in the opener`\n"
        f"_Your reason goes back to the articles agent; it is how it learns._\n"
        f"(expires in {EXPIRE_H}h)",
        keyboard=_keyboard(tok))
    print(f"proposed article #{tok}: {title}")
    print(f"  preview: {url}")


def _wills_verdict(sm, pend):
    """Find Will's reply for this token in ceo_chat_messages. Returns (verdict, feedback).

    Unlike fb_approval this does NOT accept a bare yes/no when only one item is pending:
    articles carry feedback, and a bare 'no' with no token is ambiguous about WHICH draft
    and carries no reason — the one thing this flow exists to capture."""
    since, tok = pend["created_at"], pend["token"]
    for m in sm["ceo_chat_messages"].find(
            {"role": "user", "created_at": {"$gt": since}}).sort("_id", 1):
        t = (m.get("text") or "").strip()
        if tok.lower() not in t.lower():
            continue
        after = re.sub(re.escape(tok), "", t, flags=re.I)
        if YES.search(after):
            return "yes", None
        if NO.search(after):
            fb = NO.sub("", after, count=1).strip(" .,:;-—\n")
            return "no", (fb or None)
    return None, None


def _publish(art_id):
    """Flip the article live. content_articles is the store the site reads."""
    sm = _sm()
    r = sm[ARTICLES].update_one(
        {"_id": art_id},
        {"$set": {"status": "published",
                  "published_at": datetime.now(timezone.utc).isoformat(),
                  "approved_by": "will_telegram"}})
    return r.modified_count == 1


def cmd_poll(a):
    sm = _sm()
    acted = 0
    for pend in sm[PENDING].find({"status": "awaiting_approval"}):
        age_h = (NOW - datetime.fromisoformat(pend["created_at"])).total_seconds() / 3600
        if age_h > EXPIRE_H:
            sm[PENDING].update_one({"_id": pend["_id"]},
                                   {"$set": {"status": "expired"}})
            print(f"expired #{pend['token']}: {pend['title']}")
            continue

        verdict, feedback = _wills_verdict(sm, pend)
        if verdict is None:
            continue
        acted += 1
        if a.dry_run:
            print(f"[dry-run] #{pend['token']} -> {verdict} (feedback: {feedback!r})")
            continue

        if verdict == "yes":
            ok = _publish(pend["article_id"])
            sm[PENDING].update_one({"_id": pend["_id"]}, {"$set": {
                "status": "published" if ok else "publish_failed",
                "decided_at": NOW.isoformat()}})
            _tg(f"✅ Published: *{pend['title']}*" if ok else
                f"⚠️ Approved but the publish write FAILED for *{pend['title']}* — "
                f"article `{pend['article_id']}` is unchanged. Needs a look.")
            print(f"published #{pend['token']}: {pend['title']}" if ok
                  else f"PUBLISH FAILED #{pend['token']}")
        else:
            # The feedback is the product of a rejection. Store it on the article so the
            # articles domain reads it next cycle, and say so plainly if it is missing.
            sm[ARTICLES].update_one({"_id": pend["article_id"]}, {"$set": {
                "will_feedback": feedback,
                "will_feedback_at": NOW.isoformat(),
                "status": "rejected"}})
            sm[PENDING].update_one({"_id": pend["_id"]}, {"$set": {
                "status": "rejected", "feedback": feedback,
                "decided_at": NOW.isoformat()}})
            if feedback:
                # Close the loop rather than parking it (Will, 2026-08-13): hand the
                # feedback straight to a revision agent, which edits the draft and
                # re-proposes it. Detached, because that agent takes minutes and this
                # poller must return promptly for the next cron tick.
                _tg(f"❌ Held: *{pend['title']}*\nNoted: _{feedback}_\n"
                    f"Revising now — I'll resend the draft for approval shortly.")
                try:
                    subprocess.Popen(
                        [sys.executable,
                         "/home/fields/Fields_Orchestrator/scripts/article_revise.py",
                         "--id", str(pend["article_id"])],
                        stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
                        start_new_session=True)
                    print(f"  -> revision agent launched for {pend['article_id']}")
                except Exception as e:
                    print(f"  -> FAILED to launch revision agent: {e}")
                    _tg(f"⚠️ Could not start the revision agent for *{pend['title']}* "
                        f"({e}). The feedback is saved; it needs a manual run of "
                        f"`article_revise.py --id {pend['article_id']}`.")
            else:
                _tg(f"❌ Held: *{pend['title']}*\n"
                    f"No reason given — so there is nothing to revise against. "
                    f"Reply `NO {pend['token']} <why>` and I'll fix it and resend.")
            print(f"rejected #{pend['token']}: {feedback!r}")
    print(f"poll complete — {acted} decision(s) actioned")


def cmd_list(a):
    sm = _sm()
    rows = list(sm[PENDING].find().sort("_id", -1).limit(15))
    if not rows:
        print("(nothing proposed yet)")
        return
    for p in rows:
        fb = f"  feedback: {p['feedback']}" if p.get("feedback") else ""
        print(f"#{p['token']:5s} {p.get('status',''):18s} {str(p.get('title'))[:55]}{fb}")


def main():
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[1])
    sub = ap.add_subparsers(dest="cmd", required=True)
    p = sub.add_parser("propose"); p.add_argument("--id", required=True); p.set_defaults(f=cmd_propose)
    p = sub.add_parser("poll"); p.add_argument("--dry-run", action="store_true"); p.set_defaults(f=cmd_poll)
    p = sub.add_parser("list"); p.set_defaults(f=cmd_list)
    a = ap.parse_args()
    a.f(a)


if __name__ == "__main__":
    main()
