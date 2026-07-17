#!/usr/bin/env python3
"""hypothesis_queue.py — Closed-loop P1: the prioritised experiment backlog.

Every evidenced concept (from Brain 1, the KB, or domain knowledge) enters HERE as a
queued hypothesis instead of being invented-and-launched on the spot. Each run Samantha
pulls the top queued item into a free experiment slot; when launched, the change-ledger
entry references the hypothesis_id and tags its sources (change_ledger.py --sources).
Source hit-rates (change_ledger.py sources) feed priority — the RL policy update.

Scope doc: scripts/samantha/closed_loop_intelligence_scope.md (Will-approved 2026-07-17).
Storage: system_monitor.hypothesis_queue.

Usage:
  hypothesis_queue.py add --concept "Specific property story ads" \
      --sources brain2 --evidence "78% of conversions at $0.18/LPV but 12/93 ads use it" \
      --surface fb_ads --expected-effect "lower CPL vs generic creative" --score 8
  hypothesis_queue.py list [--status queued]
  hypothesis_queue.py top                  # next hypothesis to pull into a free slot
  hypothesis_queue.py launch --id <id> --ledger-id <change_id>
  hypothesis_queue.py conclude --id <id> --verdict improved|no_change|worse --note "..."
"""
from __future__ import annotations

import argparse
import re
import sys
from datetime import datetime, timezone, timedelta

sys.path.insert(0, "/home/fields/Fields_Orchestrator")
from src.mongo_client_factory import get_mongo_client, cosmos_retry  # noqa: E402

AEST = timezone(timedelta(hours=10))
COLL = "hypothesis_queue"


def _db():
    return get_mongo_client()["system_monitor"]


def _now():
    return datetime.now(AEST)


def cmd_add(a) -> int:
    slug = re.sub(r"[^a-z0-9]+", "-", a.concept.lower()).strip("-")[:40]
    hid = f"{_now().strftime('%Y-%m-%d')}_{slug}"
    doc = {
        "hypothesis_id": hid, "created_at": _now(), "concept": a.concept,
        "sources": [s.strip() for s in a.sources.split(",") if s.strip()],
        "evidence": a.evidence, "surface": a.surface,
        "expected_effect": a.expected_effect,
        "est_power": a.est_power,  # can our traffic actually read this? (yes/directional/no)
        "priority_score": a.score, "status": "queued",
        "ledger_id": None, "verdict": None, "note": None,
    }
    cosmos_retry(lambda: _db()[COLL].update_one({"hypothesis_id": hid}, {"$set": doc}, upsert=True))
    print(f"queued {hid} (score {a.score}, surface {a.surface})")
    return 0


def cmd_list(a) -> int:
    q = {"status": a.status} if a.status else {}
    for d in _db()[COLL].find(q).sort([("status", 1), ("priority_score", -1)]):
        print(f"[{d['status']:>9}] {d['priority_score']:>2} {d['hypothesis_id']} | "
              f"{d['surface']} | {d['concept'][:60]} | src={','.join(d.get('sources', []))}")
    return 0


def cmd_top(a) -> int:
    d = _db()[COLL].find_one({"status": "queued"}, sort=[("priority_score", -1)])
    if not d:
        print("queue empty — feed it from Brain 1 / KB before the next launch")
        return 0
    print(f"NEXT: {d['hypothesis_id']} (score {d['priority_score']})")
    print(f"  concept:  {d['concept']}")
    print(f"  surface:  {d['surface']} | expected: {d.get('expected_effect')}")
    print(f"  evidence: {d.get('evidence')} (sources: {','.join(d.get('sources', []))})")
    print(f"  → launch within caps, then: hypothesis_queue.py launch --id {d['hypothesis_id']} --ledger-id <change_id>")
    return 0


def cmd_launch(a) -> int:
    r = cosmos_retry(lambda: _db()[COLL].update_one(
        {"hypothesis_id": a.id},
        {"$set": {"status": "live", "ledger_id": a.ledger_id, "launched_at": _now()}}))
    print(f"launched {a.id} → ledger {a.ledger_id}" if r.matched_count else f"no such hypothesis: {a.id}")
    return 0 if r.matched_count else 1


def cmd_conclude(a) -> int:
    r = cosmos_retry(lambda: _db()[COLL].update_one(
        {"hypothesis_id": a.id},
        {"$set": {"status": "concluded", "verdict": a.verdict, "note": a.note,
                  "concluded_at": _now()}}))
    print(f"concluded {a.id}: {a.verdict}" if r.matched_count else f"no such hypothesis: {a.id}")
    return 0 if r.matched_count else 1


def main() -> int:
    ap = argparse.ArgumentParser()
    sub = ap.add_subparsers(dest="cmd", required=True)

    p = sub.add_parser("add")
    p.add_argument("--concept", required=True)
    p.add_argument("--sources", required=True, help="comma-separated (brain1,brain2,kb,domain)")
    p.add_argument("--evidence", required=True, help="the citation — no evidence, no queue entry")
    p.add_argument("--surface", required=True, help="fb_ads|website|seo|email|flyer|...")
    p.add_argument("--expected-effect", default="")
    p.add_argument("--est-power", choices=["yes", "directional", "no"], default="directional")
    p.add_argument("--score", type=int, default=5, help="1-10 priority")
    p.set_defaults(func=cmd_add)

    p = sub.add_parser("list"); p.add_argument("--status", default=""); p.set_defaults(func=cmd_list)
    p = sub.add_parser("top"); p.set_defaults(func=cmd_top)

    p = sub.add_parser("launch")
    p.add_argument("--id", required=True)
    p.add_argument("--ledger-id", required=True)
    p.set_defaults(func=cmd_launch)

    p = sub.add_parser("conclude")
    p.add_argument("--id", required=True)
    p.add_argument("--verdict", required=True, choices=["improved", "no_change", "worse", "abandoned"])
    p.add_argument("--note", default="")
    p.set_defaults(func=cmd_conclude)

    a = ap.parse_args()
    return a.func(a)


if __name__ == "__main__":
    raise SystemExit(main())
