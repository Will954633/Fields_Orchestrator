#!/usr/bin/env python3
"""
conductor_state.py — the conductor's DURABLE cross-cycle memory (so Samantha self-persists +
self-corrects her focus without a human re-reading .md docs each cycle).

Two things live here, in `system_monitor`:
  • rl_conductor_state  (_id "current") — the STANDING binding constraint + cross-domain priority + why.
    The conductor reads it at the START of every cycle and rewrites it at the END. The constraint
    persists automatically until the DATA says it moved — she changes it herself, nobody hand-feeds it.
  • rl_domain_directives — durable, addressed instructions ("onsite: design an identity-capture
    experiment"). The conductor issues them; each domain cycle reads its own OPEN directives and acts.
    This is how a conductor decision actually reaches a domain, instead of dying as prose in a doc.

Usage:
  conductor_state.py show
  conductor_state.py set --constraint "..." --priority onsite,seo,geo,ads,articles --why "..." [--cycle N]
  conductor_state.py directive --domain onsite --text "design an identity-capture experiment on the address-submit flow"
  conductor_state.py directives [--domain onsite] [--all]        # open directives (a domain reads its own)
  conductor_state.py done --id <directive_id>
"""
import argparse
import sys
from datetime import datetime, timezone

sys.path.insert(0, "/home/fields/Fields_Orchestrator")
from shared.db import get_client  # noqa: E402

STATE_COLL = "rl_conductor_state"
DIRECTIVE_COLL = "rl_domain_directives"
DOMAINS = {"geo", "seo", "ads", "articles", "onsite", "offmarket", "all"}


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _sm():
    return get_client()["system_monitor"]


def show(sm) -> None:
    s = sm[STATE_COLL].find_one({"_id": "current"})
    if not s:
        print("(no conductor state yet — first cycle: set the constraint after you diagnose it)")
    else:
        print(f"BINDING CONSTRAINT: {s.get('constraint','—')}")
        print(f"  since:    {s.get('constraint_since','—')}  (updated {s.get('updated_at','—')}, cycle {s.get('updated_cycle','—')})")
        print(f"  priority: {' > '.join(s.get('priority') or []) or '—'}")
        print(f"  why:      {s.get('why','—')}")
    opens = list(sm[DIRECTIVE_COLL].find({"status": "open"}).sort("created_at", 1))
    print(f"\nOPEN DIRECTIVES ({len(opens)}):")
    for d in opens:
        print(f"  [{d['_id']}] → {d.get('domain'):9} {d.get('text','')}  (since {str(d.get('created_at',''))[:16]})")


def set_state(sm, constraint, priority, why, cycle) -> None:
    prev = sm[STATE_COLL].find_one({"_id": "current"}) or {}
    changed = constraint and constraint.strip() != (prev.get("constraint") or "").strip()
    doc = {
        "_id": "current",
        "constraint": constraint if constraint is not None else prev.get("constraint"),
        "constraint_since": _now() if changed else prev.get("constraint_since", _now()),
        "priority": [p.strip() for p in priority.split(",") if p.strip()] if priority else prev.get("priority", []),
        "why": why if why is not None else prev.get("why"),
        "updated_at": _now(),
        "updated_cycle": cycle if cycle is not None else prev.get("updated_cycle"),
    }
    sm[STATE_COLL].replace_one({"_id": "current"}, doc, upsert=True)
    # keep an append-only history so constraint shifts are auditable
    sm[STATE_COLL].insert_one({k: v for k, v in {**doc, "kind": "history", "snapshot_at": _now()}.items() if k != "_id"})
    print(f"state updated (constraint {'CHANGED' if changed else 'unchanged'}): {doc['constraint']}")


def add_directive(sm, domain, text, cycle, origin="conductor") -> None:
    """origin defaults to the conductor. A DOMAIN may also write to another domain —
    Will asked on 2026-08-13 for seo and articles to work together — and when it does,
    the note must say who sent it. A domain-to-domain note is a REQUEST between peers;
    a conductor directive carries Will's authority. Rendering them identically would let
    any domain issue instructions in Samantha's name."""
    if domain not in DOMAINS:
        print(f"unknown domain '{domain}' (valid: {sorted(DOMAINS)})"); return
    r = sm[DIRECTIVE_COLL].insert_one({
        "domain": domain, "text": text, "status": "open", "origin": origin,
        "created_at": _now(), "created_cycle": cycle,
    })
    label = "directive" if origin == "conductor" else f"note from {origin}"
    print(f"{label} added [{r.inserted_id}] → {domain}: {text}")


def list_directives(sm, domain, show_all) -> None:
    q = {} if show_all else {"status": "open"}
    if domain:
        q["domain"] = {"$in": [domain, "all"]}
    for d in sm[DIRECTIVE_COLL].find(q).sort("created_at", 1):
        origin = d.get("origin", "conductor")
        src = "CONDUCTOR" if origin == "conductor" else f"from:{origin}"
        print(f"[{d['_id']}] {d.get('status'):5} {d.get('domain'):9} {src:14} {d.get('text','')}")


def done(sm, did) -> None:
    from bson import ObjectId
    try:
        _id = ObjectId(did)
    except Exception:
        _id = did
    r = sm[DIRECTIVE_COLL].update_one({"_id": _id}, {"$set": {"status": "done", "closed_at": _now()}})
    print("closed" if r.modified_count else "not found")


def main() -> int:
    ap = argparse.ArgumentParser()
    sub = ap.add_subparsers(dest="cmd", required=True)
    sub.add_parser("show")
    p = sub.add_parser("set"); p.add_argument("--constraint"); p.add_argument("--priority"); p.add_argument("--why"); p.add_argument("--cycle", type=int)
    p = sub.add_parser("directive"); p.add_argument("--domain", required=True); p.add_argument("--text", required=True); p.add_argument("--cycle", type=int); p.add_argument("--from", dest="origin", default="conductor", help="sending domain; omit for a conductor directive")
    p = sub.add_parser("directives"); p.add_argument("--domain"); p.add_argument("--all", action="store_true")
    p = sub.add_parser("done"); p.add_argument("--id", required=True)
    a = ap.parse_args()
    sm = _sm()
    if a.cmd == "show": show(sm)
    elif a.cmd == "set": set_state(sm, a.constraint, a.priority, a.why, a.cycle)
    elif a.cmd == "directive": add_directive(sm, a.domain, a.text, a.cycle, a.origin)
    elif a.cmd == "directives": list_directives(sm, a.domain, a.all)
    elif a.cmd == "done": done(sm, a.id)
    return 0


if __name__ == "__main__":
    sys.exit(main())
