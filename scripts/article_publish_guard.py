#!/usr/bin/env python3
"""
article_publish_guard.py — one door to publishing an article, and this is the lock on it.

WHY (Will, 2026-08-13): "our new method of publishing articles is to send them to me on
telegram for review. each article must now go via that path."

That path is `scripts/article_approval.py`: propose → Telegram with a live preview and
✅/✏️ buttons → Will taps → publish + deploy. But an approval gate with a side door is not a
gate, and an audit the same day found two:

  1. `push-ghost-draft.py --publish`  — sets status=published directly.
  2. `funnel-publisher.py`            — INSERTS landing pages into content_articles already
                                        marked published. Not obviously "an article", but it
                                        lands in the article store and renders at
                                        /articles/<slug>, so a reader cannot tell the
                                        difference and neither can Google.

Neither is on cron, so nothing was auto-publishing. Both are invocable by a person or an
agent, which is enough — the whole point of moving the gate into code is that instructions
get skipped under load and code does not.

USAGE — call this before any write that would make an article public:

    from article_publish_guard import require_approval
    require_approval(caller="push-ghost-draft.py", slug=slug, override=args.force_publish)

It raises SystemExit with an explanation unless `override` is explicitly set. The override
exists because a blanket ban would eventually be worked around by someone deleting the
import; a documented, loud escape hatch survives contact with reality. Every override is
recorded to `system_monitor.article_publish_overrides` so the exception is visible rather
than silent.
"""
from __future__ import annotations

import sys
from datetime import datetime, timezone

_MSG = """
REFUSED — publishing an article directly is no longer permitted.

  Caller : {caller}
  Article: {slug}

Every article must go to Will on Telegram for review (his instruction, 2026-08-13):

    python3 scripts/article_approval.py propose --id {slug}

He gets the title, the word count, a live preview link and two buttons. Tapping ✅ Publish
sets it live AND fires the Netlify deploy so it reaches the articles list — which a direct
status write does NOT do, so this path was also quietly producing published-but-unlisted
articles.

If you genuinely need to bypass the gate, pass the caller's override flag. It will be logged
to system_monitor.article_publish_overrides with a reason, and Samantha will see it.
"""


def require_approval(caller: str, slug: str = "(unknown)", override: bool = False,
                     reason: str = "") -> None:
    """Block a direct publish unless explicitly overridden. Records every override."""
    if not override:
        sys.exit(_MSG.format(caller=caller, slug=slug))

    try:
        sys.path.insert(0, "/home/fields/Fields_Orchestrator")
        from shared.db import get_client
        get_client()["system_monitor"]["article_publish_overrides"].insert_one({
            "caller": caller, "slug": slug,
            "reason": (reason or "").strip() or "no reason given",
            "at": datetime.now(timezone.utc).isoformat(),
        })
    except Exception as e:      # never let audit logging block a deliberate override
        print(f"[article_publish_guard] WARNING: could not record override: {e}",
              file=sys.stderr)
    print(f"[article_publish_guard] OVERRIDE: {caller} publishing {slug} directly, "
          f"bypassing Will's Telegram review. Recorded.", file=sys.stderr)
