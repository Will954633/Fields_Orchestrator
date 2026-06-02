"""
Messages builder for the house mini-site "Messages" tab (consultant rebuild
Phase 3.1 / [C19]).

Turns the report's own state into a private advisory timeline that feels like
"Will is already watching this for me" — not a marketing inbox. Four system
message types are generated deterministically from report state, and any
human notes a consultant posted from the ops dashboard are preserved.

System messages (regenerated each run, stable ids so they don't duplicate):
  - welcome          — one-time, on first build.
  - valuation_review — reflects under-review vs human-reviewed/final state.
  - market_change    — one per recent comparable event (new listing / sold /
                       price move), mirroring the What-Changed banner so the
                       two never disagree.
  - preparation      — points at the Process decisions once positioning is live.

Human messages (type "human_note", from "Will") are written by the ops endpoint
(`property-report-message` in system-monitor.mjs) and are NEVER overwritten here.

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
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)

MAX_MARKET_MESSAGES = 5


def _money(n: Any) -> Optional[str]:
    try:
        v = int(n)
        return f"${v:,}" if v > 0 else None
    except (TypeError, ValueError):
        return None


def _event_dt(e: Dict[str, Any]) -> datetime:
    for key in ("ts", "date"):
        raw = e.get(key)
        if not raw:
            continue
        try:
            s = str(raw)
            if len(s) == 10:  # YYYY-MM-DD
                return datetime.fromisoformat(s).replace(tzinfo=timezone.utc)
            return datetime.fromisoformat(s.replace("Z", "+00:00"))
        except ValueError:
            continue
    return datetime.now(timezone.utc)


def build_system_messages(doc: Dict[str, Any]) -> List[Dict[str, Any]]:
    """Pure function: report doc -> list of system message dicts (stable ids)."""
    suburb = doc.get("suburb") or "your suburb"
    created = doc.get("created_at")
    created_dt = created if isinstance(created, datetime) else datetime.now(timezone.utc)
    msgs: List[Dict[str, Any]] = []

    # 1) Welcome — one-time.
    msgs.append({
        "id": "sys-welcome",
        "type": "welcome",
        "sender": "system",
        "from": "Fields",
        "headline": "Your report is live — and it keeps watching the market",
        "body": (
            "This report updates every night as listings, sales and market signals land in "
            f"{suburb}. Messages from your property consultant — and the changes that matter to "
            "your home — will appear here. You'll see a dot on this tab when there's something new."
        ),
        "created_at": created_dt,
    })

    # 2) Valuation review — reflects state.
    state = doc.get("state")
    approved = (doc.get("analyst_approved_at") or {}).get("comps")
    if state == "final" or approved:
        when = doc.get("state_transitioned_at", {}).get("final") or approved
        msgs.append({
            "id": "sys-valuation",
            "type": "valuation_review",
            "sender": "agent",
            "from": "Will",
            "headline": "I've reviewed the comparable sales behind your valuation",
            "body": (
                "The figure on your Valuation tab isn't auto-generated alone — I've gone through every "
                "comparable sale and adjustment by hand. Open the Valuation tab to see the working, and "
                "let's talk through what a physical inspection might change."
            ),
            "created_at": when if isinstance(when, datetime) else datetime.now(timezone.utc),
        })
    else:
        eta = doc.get("consultant_review_eta") or doc.get("consultantReviewEta")
        body = (
            "Your working range is ready now. I'm reviewing every comparable sale and adjustment by hand "
            "before it becomes a final recommendation"
        )
        body += f" — expected by {eta}." if eta else "."
        msgs.append({
            "id": "sys-valuation",
            "type": "valuation_review",
            "sender": "agent",
            "from": "Will",
            "headline": "I'm reviewing your valuation personally",
            "body": body,
            "created_at": created_dt,
        })

    # 3) Market changes — one per recent comparable event (mirrors What-Changed).
    events = doc.get("comparable_events") or []
    events_sorted = sorted(events, key=_event_dt, reverse=True)[:MAX_MARKET_MESSAGES]
    for e in events_sorted:
        etype = e.get("type")
        addr = e.get("address") or "A nearby home"
        price = _money(e.get("price"))
        if etype == "new_listing":
            headline = f"A comparable home just listed — {addr}"
            body = f"{addr} came onto the market" + (f" at {price}" if price else "") + \
                ". It's been added to the set of homes competing for your buyer — see The Market tab."
        elif etype == "sold":
            headline = f"A comparable home sold — {addr}"
            body = f"{addr} sold" + (f" for {price}" if price else "") + \
                ". A completed sale is the cleanest evidence of what buyers actually pay for a home like yours."
        elif etype == "price_change":
            headline = f"A competitor changed its price — {addr}"
            body = f"{addr} moved its asking price" + (f" to {price}" if price else "") + \
                ". Price moves in your competitive set can change where your home sits."
        else:
            continue
        msgs.append({
            "id": f"evt-{e.get('id') or _event_dt(e).strftime('%Y%m%d%H%M%S')}",
            "type": "market_change",
            "sender": "system",
            "from": "Fields",
            "headline": headline,
            "body": body,
            "created_at": _event_dt(e),
        })

    # 4) Preparation — once positioning is live, point at the decisions.
    if (doc.get("slot_status") or {}).get("positioning") == "approved":
        msgs.append({
            "id": "sys-preparation",
            "type": "preparation",
            "sender": "agent",
            "from": "Will",
            "headline": "Your selling-decision plan is ready to walk through",
            "body": (
                "The Process tab now lays out the decisions that shape your final price — what to fix, when "
                "to list, how to price, which method, how far to reach. Mark where you stand; there's no wrong "
                "answer, and nothing's committed by choosing."
            ),
            "created_at": created_dt,
        })

    return msgs


def merge_messages(existing: List[Dict[str, Any]], system: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """Preserve the human conversation (agent notes + seller messages); replace
    system-generated messages. Without this, a nightly re-resolve would wipe the
    seller's chat. Sort newest-first."""
    keep = [
        m for m in (existing or [])
        if m.get("type") in ("human_note", "seller_message") or m.get("sender") in ("agent", "seller")
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
