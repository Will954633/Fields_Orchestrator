#!/usr/bin/env python3
"""
article_revise.py — apply Will's rejection feedback to a draft, then resubmit for approval.

WHY (Will, 2026-08-13). The approval gate originally recorded a rejection and stopped:
feedback landed on the article and waited for the weekly articles cycle. Will asked for the
loop to close — "my reply should have either samantha or the sub-domain agent make the fix
as per my feedback and resubmit draft to telegram for my approval". So a NO now triggers a
revision within minutes instead of within a week.

The result is a real iterative loop: propose -> reject with a reason -> revise -> re-propose,
until Will says yes or the round cap stops it.

THREE GUARDS, because this is an agent editing live content in a loop:

  1. **Round cap (MAX_ROUNDS).** Reject -> revise -> reject forever is the obvious failure
     mode and it would burn Max usage while pestering Will. After the cap the article is
     parked as `needs_human` and stays put.
  2. **Never publishes.** It edits the draft and re-proposes. Publishing remains Will's tap
     on the approval message — the 2026-07-29 rule is untouched.
  3. **Backs up every revision.** Each round snapshots the prior HTML into
     content_article_revisions, so any edit is reversible and the drafting history is
     inspectable rather than overwritten in place.

Run by article_approval.py on rejection; also runnable by hand:
  article_revise.py --id <article_id>
"""
from __future__ import annotations

import argparse
import os
import subprocess
import sys
from datetime import datetime, timezone

sys.path.insert(0, "/home/fields/Fields_Orchestrator")
sys.path.insert(0, "/home/fields/Fields_Orchestrator/scripts")
from shared.db import get_client  # noqa: E402

ARTICLES = "content_articles"
REVISIONS = "content_article_revisions"
MAX_ROUNDS = 3
MODEL = os.environ.get("RL_MODEL", "claude-opus-5")
BUDGET_SEC = 900


def _sm():
    return get_client()["system_monitor"]


PROMPT = """You are the ARTICLES domain agent for Fields Real Estate. Will reviewed a draft
article and REJECTED it with specific feedback. Your job is to apply that feedback, then
resubmit the draft for his approval.

ARTICLE ID: {aid}
TITLE: {title}
REVISION ROUND: {rnd} of {maxr}

WILL'S FEEDBACK (his exact words — treat as the definitive instruction):
\"\"\"{feedback}\"\"\"

DO THIS:
1. Read the article:
   python3 -c "import sys;sys.path.insert(0,'/home/fields/Fields_Orchestrator');from shared.db import get_client;from bson import ObjectId;d=get_client()['system_monitor']['content_articles'].find_one({{'_id':ObjectId('{aid}')}});print(d['html'])"
2. Work out what he is actually asking for. If the feedback is about something structural
   (a stray section, a wrong figure, a tone problem), fix the cause, not just the symptom.
3. Rewrite the `html` field to address it. Write the whole corrected HTML back with an
   update_one $set on `html`. Change nothing else — not the title, slug, status or author.
4. Re-read what you wrote and confirm the feedback is genuinely addressed. If you could not
   address it (e.g. he asked for data you do not have), say so clearly in step 5 rather than
   pretending — a resubmission that ignores his point wastes his time and he will spot it.
5. Resubmit for approval:
   python3 /home/fields/Fields_Orchestrator/scripts/article_approval.py propose --id {aid}
   The proposal message must make clear what you changed, so add a one-line note of the
   change to the article's `custom_excerpt` ONLY if that is genuinely the excerpt — otherwise
   leave it and rely on the diff being visible in the draft preview.

BINDING RULES:
- CLAUDE.md Rule 5 governs all copy: no advice, no predictions, comparable RANGES not single
  valuations, cite source and period, exact figures, suburbs capitalised, and never the words
  stunning / nestled / boasting / rare opportunity / robust market.
- The QLD licence number is 4832972. It is NOT 4832971 — 68 articles carried that wrong
  number until 2026-08-13. Never reintroduce it.
- Do NOT publish. Do NOT set status to published. Will approves by tapping in Telegram.
- Do NOT message Will directly; the approval proposal is the only message.
"""


def main():
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[1])
    ap.add_argument("--id", required=True)
    ap.add_argument("--dry-run", action="store_true")
    a = ap.parse_args()

    from bson import ObjectId
    sm = _sm()
    try:
        oid = ObjectId(a.id)
    except Exception:
        sys.exit(f"ERROR: {a.id!r} is not a valid article id")
    art = sm[ARTICLES].find_one({"_id": oid})
    if not art:
        sys.exit(f"ERROR: no article {a.id}")

    feedback = (art.get("will_feedback") or "").strip()
    if not feedback:
        sys.exit("ERROR: no will_feedback on this article — nothing to revise against. "
                 "A rejection with no reason cannot drive a revision.")

    rnd = int(art.get("revision_round") or 0) + 1
    if rnd > MAX_ROUNDS:
        sm[ARTICLES].update_one({"_id": oid}, {"$set": {"status": "needs_human"}})
        print(f"round cap reached ({MAX_ROUNDS}) — parked as needs_human, not revising again")
        return

    # Snapshot before the agent touches it.
    sm[REVISIONS].insert_one({
        "article_id": oid, "round": rnd, "html": art.get("html"),
        "feedback_addressed": feedback,
        "snapshot_at": datetime.now(timezone.utc).isoformat()})
    sm[ARTICLES].update_one({"_id": oid}, {"$set": {"revision_round": rnd}})

    prompt = PROMPT.format(aid=a.id, title=art.get("title"), feedback=feedback,
                           rnd=rnd, maxr=MAX_ROUNDS)
    if a.dry_run:
        print(prompt)
        return

    env = dict(os.environ)
    env.pop("ANTHROPIC_API_KEY", None)      # force Claude Max, never metered billing
    env.pop("CLAUDECODE", None)
    env.pop("CLAUDE_CODE_SSE_PORT", None)

    print(f"revising article {a.id} (round {rnd}/{MAX_ROUNDS})…")
    r = subprocess.run(
        ["claude", "--model", MODEL, "-p", prompt,
         "--allowedTools", "Bash,Read,Write,Edit,Glob,Grep", "--max-turns", "40"],
        env=env, capture_output=True, text=True, timeout=BUDGET_SEC)
    print(r.stdout[-2000:])
    if r.returncode != 0:
        print(f"revision agent exited {r.returncode}", file=sys.stderr)
        print(r.stderr[-800:], file=sys.stderr)


if __name__ == "__main__":
    main()
