#!/usr/bin/env python3
"""
running_doc.py — read/append/complete on Will's RUNNING Google Doc (Docs API).

Will's running doc is a living conversation that also holds HIS COMMENTS — so it is
NEVER deleted or rebuilt, only edited in place.

Conventions:
  * NEWEST FIRST — new entries are inserted at the TOP of the doc.
  * ORANGE = DONE — completed / now-irrelevant text is highlighted orange.
    Orange text is treated as finished: `read` SKIPS it, so Samantha never re-reads
    or re-actions it.

Usage:
  running_doc.py read     --doc <id>                 # ACTIVE text only (orange skipped)
  running_doc.py read     --doc <id> --all           # everything, marking [DONE] items
  running_doc.py add      --doc <id> --text "..."    # insert at the TOP (stays un-highlighted)
  running_doc.py complete --doc <id> --match "..."   # highlight matching paragraph(s) ORANGE = done
"""
from __future__ import annotations

import argparse
import json
import sys
import warnings

warnings.filterwarnings("ignore")

from google.oauth2.credentials import Credentials  # noqa: E402
from google.auth.transport.requests import Request  # noqa: E402
from googleapiclient.discovery import build  # noqa: E402

OAUTH_KEYS = "/home/fields/.gdrive-oauth.keys.json"
SERVER_CREDS = "/home/fields/.gdrive-server-credentials.json"

# Google's standard orange highlight (#FF9900).
ORANGE = {"red": 1.0, "green": 0.6, "blue": 0.0}


def _creds():
    keys = json.load(open(OAUTH_KEYS))["installed"]
    tok = json.load(open(SERVER_CREDS))
    c = Credentials(
        token=tok.get("access_token"), refresh_token=tok.get("refresh_token"),
        token_uri=keys["token_uri"], client_id=keys["client_id"],
        client_secret=keys["client_secret"], scopes=(tok.get("scope") or "").split(),
    )
    if not c.valid:
        c.refresh(Request())
    return c


def _docs():
    return build("docs", "v1", credentials=_creds(), cache_discovery=False)


def _is_orange(rgb: dict) -> bool:
    """Tolerant orange match — red high, green mid, blue low."""
    if not rgb:
        return False
    r, g, b = rgb.get("red", 0), rgb.get("green", 0), rgb.get("blue", 0)
    return r >= 0.80 and 0.30 <= g <= 0.85 and b <= 0.35


def paragraphs(doc: dict) -> list[dict]:
    """Flatten the doc into paragraphs with text, index range, and done(orange) flag."""
    out = []
    for el in doc.get("body", {}).get("content", []):
        para = el.get("paragraph")
        if not para:
            continue
        text, start, end, orange_runs, runs = "", None, None, 0, 0
        for pe in para.get("elements", []):
            tr = pe.get("textRun")
            if not tr:
                continue
            text += tr.get("content", "")
            start = pe["startIndex"] if start is None else start
            end = pe["endIndex"]
            runs += 1
            bg = (tr.get("textStyle", {}).get("backgroundColor", {}) or {}).get("color", {}).get("rgbColor", {})
            if _is_orange(bg):
                orange_runs += 1
        if text.strip() and start is not None:
            out.append({"text": text.rstrip("\n"), "start": start, "end": end,
                        "done": runs > 0 and orange_runs == runs})
    return out


def active_text(doc_id: str) -> str:
    """ACTIVE (non-orange) text of the doc — what Samantha should still act on."""
    paras = paragraphs(_docs().documents().get(documentId=doc_id).execute())
    return "\n".join(p["text"] for p in paras if not p["done"])


def cmd_read(a) -> int:
    doc = _docs().documents().get(documentId=a.doc).execute()
    paras = paragraphs(doc)
    active = [p for p in paras if not p["done"]]
    done = [p for p in paras if p["done"]]
    print(f"=== {doc.get('title')} — {len(active)} ACTIVE / {len(done)} done(orange, skipped) ===")
    for p in paras:
        if p["done"]:
            if a.all:
                print(f"  [DONE·orange] {p['text'][:100]}")
            continue
        print(p["text"])
    if done and not a.all:
        print(f"\n({len(done)} orange/completed paragraphs skipped — already actioned, do not re-read)")
    return 0


def cmd_add(a) -> int:
    svc = _docs()
    text = a.text.rstrip("\n") + "\n"
    # Insert at the very top of the body (index 1), then explicitly CLEAR any highlight
    # so the new entry doesn't inherit orange from whatever used to be first.
    svc.documents().batchUpdate(documentId=a.doc, body={"requests": [
        {"insertText": {"location": {"index": 1}, "text": text}},
        {"updateTextStyle": {
            "range": {"startIndex": 1, "endIndex": 1 + len(text)},
            "textStyle": {"backgroundColor": {}},
            "fields": "backgroundColor",
        }},
    ]}).execute()
    print(f"added at TOP ({len(text)} chars, un-highlighted = active)")
    return 0


def cmd_complete(a) -> int:
    svc = _docs()
    doc = svc.documents().get(documentId=a.doc).execute()
    hits = [p for p in paragraphs(doc)
            if a.match.lower() in p["text"].lower() and not p["done"]]
    if not hits:
        print(f"no ACTIVE paragraph matches: {a.match!r}")
        return 1
    reqs = [{"updateTextStyle": {
        "range": {"startIndex": p["start"], "endIndex": p["end"]},
        "textStyle": {"backgroundColor": {"color": {"rgbColor": ORANGE}}},
        "fields": "backgroundColor",
    }} for p in hits]
    svc.documents().batchUpdate(documentId=a.doc, body={"requests": reqs}).execute()
    for p in hits:
        print(f"marked DONE (orange): {p['text'][:80]}")
    return 0


def cmd_reply(a) -> int:
    """Insert Samantha's answer directly into the document BODY, immediately after
    the paragraph it answers — the PRIMARY reply channel (2026-07-23), replacing
    dependence on Drive-API comment anchors, which are undocumented, unverifiable
    (no way to confirm they render as an attached inline bubble vs. floating
    invisibly), and were proven broken this session (26 comments existed via the
    API but were not visible in the actual Docs UI). Body text is not ambiguous —
    if it's in the document, Will can see it, period. Comments remain available
    as a secondary/best-effort nicety (drive_comment.py) but must never be the
    only place an answer lives.

    Marks BOTH the original paragraph and the newly-inserted reply orange
    immediately, and re-reads the doc afterward to verify the reply text is
    genuinely present before reporting success — do not trust the batchUpdate
    call alone (the same "API said OK" trap that caused the comment-anchor bug).
    """
    svc = _docs()
    doc = svc.documents().get(documentId=a.doc).execute()
    paras = paragraphs(doc)
    match = next((p for p in paras if a.match.lower() in p["text"].lower() and not p["done"]), None)
    if not match:
        print(f"no ACTIVE paragraph matches: {a.match!r}")
        return 1

    reply_text = f"→ Samantha: {a.text}".rstrip("\n") + "\n"
    insert_at = match["end"]
    svc.documents().batchUpdate(documentId=a.doc, body={"requests": [
        {"insertText": {"location": {"index": insert_at}, "text": reply_text}},
        {"updateParagraphStyle": {
            "range": {"startIndex": insert_at, "endIndex": insert_at + len(reply_text)},
            "paragraphStyle": {"indentStart": {"magnitude": 36, "unit": "PT"}},
            "fields": "indentStart",
        }},
        {"updateTextStyle": {
            "range": {"startIndex": insert_at, "endIndex": insert_at + len(reply_text)},
            "textStyle": {"italic": True},
            "fields": "italic",
        }},
    ]}).execute()

    # Mark both the reply and the original paragraph orange (done), then verify.
    doc2 = svc.documents().get(documentId=a.doc).execute()
    paras2 = paragraphs(doc2)
    reply_hit = next((p for p in paras2 if p["text"].startswith("→ Samantha:") and a.text[:60] in p["text"]), None)
    orig_hit = next((p for p in paras2 if a.match.lower() in p["text"].lower() and p["text"] != (reply_hit or {}).get("text")), None)
    reqs = []
    for p in (reply_hit, orig_hit):
        if p and not p["done"]:
            reqs.append({"updateTextStyle": {
                "range": {"startIndex": p["start"], "endIndex": p["end"]},
                "textStyle": {"backgroundColor": {"color": {"rgbColor": ORANGE}}},
                "fields": "backgroundColor",
            }})
    if reqs:
        svc.documents().batchUpdate(documentId=a.doc, body={"requests": reqs}).execute()

    # Verify: re-read once more and confirm the reply text is genuinely there.
    doc3 = svc.documents().get(documentId=a.doc).execute()
    body_text = "\n".join(p["text"] for p in paragraphs(doc3))
    if a.text[:60] in body_text:
        print(f"REPLY INSERTED + VERIFIED IN BODY (guaranteed visible): {reply_text[:100]!r}")
        return 0
    else:
        print("WARNING: reply text not found on re-read — insertion may have failed. Do not report success.")
        return 1


def main() -> int:
    ap = argparse.ArgumentParser()
    sub = ap.add_subparsers(dest="cmd", required=True)
    p = sub.add_parser("read"); p.add_argument("--doc", required=True)
    p.add_argument("--all", action="store_true"); p.set_defaults(func=cmd_read)
    p = sub.add_parser("add"); p.add_argument("--doc", required=True)
    p.add_argument("--text", required=True); p.set_defaults(func=cmd_add)
    p = sub.add_parser("complete"); p.add_argument("--doc", required=True)
    p.add_argument("--match", required=True); p.set_defaults(func=cmd_complete)
    p = sub.add_parser("reply"); p.add_argument("--doc", required=True)
    p.add_argument("--match", required=True); p.add_argument("--text", required=True)
    p.set_defaults(func=cmd_reply)
    a = ap.parse_args()
    return a.func(a)


if __name__ == "__main__":
    raise SystemExit(main())
