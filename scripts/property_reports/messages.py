"""
Messages builder for the house mini-site "Messages" tab (consultant rebuild
Phase 3.1 / [C19]).

The Messages tab is a private TWO-WAY chat between the home owner and Will.
On a fresh report we seed exactly ONE message — a short personal note from Will
introducing himself, what the owner can get from the site, that he's working on
their valuation, and an invitation to reply. Everything after that is real
conversation: notes Will posts from the ops dashboard (type "human_note") and
messages the owner sends from the composer (type "seller_message").

No other messages are auto-generated. The valuation-status, market-change and
preparation updates that used to load here have been removed — this is a
person-to-person channel, not an automated feed.

The single intro is rendered as a chat bubble from Will (sender "agent"), so it
reads like the first message in a conversation rather than a system card.

Usage:
  from scripts.property_reports.messages import refresh_messages
  refresh_messages(slug, db)            # db = system_monitor Database

  # or standalone, to (re)seed one report without a full re-resolve:
  python -m scripts.property_reports.messages --slug 25-huntingdale-crescent-robina
"""

from __future__ import annotations

import argparse
import logging
import os
import sys
from datetime import datetime, timezone
from typing import Any, Dict, List

logger = logging.getLogger(__name__)


def build_system_messages(doc: Dict[str, Any]) -> List[Dict[str, Any]]:
    """Pure function: report doc -> the single auto-generated intro from Will.

    Stable id so it never duplicates across re-runs. Rendered as a chat bubble
    (sender "agent") to read like the opening message of a conversation.
    """
    suburb = doc.get("suburb") or "your area"
    created = doc.get("created_at")
    created_dt = created if isinstance(created, datetime) else datetime.now(timezone.utc)

    return [{
        "id": "sys-welcome",
        "type": "welcome",
        "sender": "agent",
        "from": "Will",
        "headline": "",
        "body": (
            "Hi, I'm Will Simpson — I built Fields, and I'll be the person you deal with directly. "
            f"I put this site together so you can see what I'm finding about your home and the {suburb} "
            "market in one place, at your own pace, with the working shown rather than just a headline "
            "figure. I'm going through the comparable sales behind your valuation by hand at the moment — "
            "it'll appear on the Valuation tab once I've reviewed it properly. In the meantime, reply here "
            "any time: introduce yourself, tell me anything about the home I should know, or ask me "
            "anything at all. This channel is private, just between the two of us."
        ),
        "created_at": created_dt,
    }]


def merge_messages(existing: List[Dict[str, Any]], system: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """Preserve the real conversation (Will's ops-dashboard notes + the owner's
    messages); replace the auto-generated intro. Keyed on message TYPE so the
    regenerated intro never duplicates the stored one. Sort newest-first."""
    keep = [
        m for m in (existing or [])
        if m.get("type") in ("human_note", "seller_message")
    ]
    merged = keep + system
    merged.sort(key=lambda m: m.get("created_at") or datetime.min.replace(tzinfo=timezone.utc), reverse=True)
    return merged


def refresh_messages(slug: str, db) -> int:
    """Rebuild messages[] for one report (preserving human notes). Returns count."""
    coll = db["property_reports"]
    doc = coll.find_one({"slug": slug})
    if not doc:
        logger.warning("refresh_messages: no report for slug=%s", slug)
        return 0
    system = build_system_messages(doc)
    merged = merge_messages(doc.get("messages") or [], system)
    coll.update_one(
        {"slug": slug},
        {"$set": {"messages": merged, "messages_refreshed_at": datetime.now(timezone.utc)}},
    )
    logger.info("refresh_messages: %s -> %d messages", slug, len(merged))
    return len(merged)


def _main() -> None:
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    ap = argparse.ArgumentParser()
    ap.add_argument("--slug", required=True)
    args = ap.parse_args()
    sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..")))
    from src.mongo_client_factory import get_database
    db = get_database("system_monitor")
    n = refresh_messages(args.slug, db)
    print(f"{args.slug}: {n} messages")


if __name__ == "__main__":
    _main()
