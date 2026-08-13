#!/usr/bin/env python3
"""
recommendations.py — the General RL recommendation ledger.

REPLACES `WILL_TO_ACTION.md`, and exists because that file failed in a specific,
measurable way: it grew to 1,773 lines / 48 OPEN items in under two weeks, 84% of
everything ever raised, with no cap, no ranking, no expiry and no dedup. Two pairs of
items were literally the same finding raised days apart. Will read essentially none of
it. The individual write-ups were excellent; the aggregate was unusable.

So the ledger enforces, in code, the three things prose could not:

  1. A HARD CAP on open recommendations per domain (MAX_OPEN_PER_DOMAIN). A domain at
     cap cannot propose a 7th thing — it must withdraw or supersede one of its own
     first. This forces ranking at the point of writing instead of dumping onto Will.
     A 48-item backlog is not "discouraged" here; it is unrepresentable.

  2. CLOSURE. Every recommendation carries Will's verdict and, crucially, his REASON.
     `feedback --domain X` replays those verdicts to the domain agent at the start of
     its next cycle. This is the single highest-value signal in the system and it did
     not exist before: domains never learned what Will accepted or why he refused.

  3. OUTCOME GRADING. A shipped recommendation claimed a metric would move by a date.
     `due-for-grading` surfaces it when that date passes; `grade` records whether it
     actually worked. `stats` turns that into a per-domain hit rate. Without this the
     system is an idea generator that never finds out if it was right.

Together those three make the loop closed. The old system wrote; nothing ever read back.

Collection: system_monitor.rl_recommendations (one doc per recommendation).

Typical domain-agent usage in a weekly cycle:
    python3 recommendations.py feedback --domain seo      # what Will said last time
    python3 recommendations.py list --domain seo          # my own open items
    python3 recommendations.py propose --domain seo ...   # at most MAX_OPEN_PER_DOMAIN

Typical Samantha usage:
    python3 recommendations.py brief-candidates           # everything open, all domains
    python3 recommendations.py verdict --id REC-seo-004 --verdict no --reason "..."
    python3 recommendations.py due-for-grading
    python3 recommendations.py stats
"""
from __future__ import annotations

import argparse
import json
import re
import sys
from datetime import datetime, timedelta, timezone

sys.path.insert(0, "/home/fields/Fields_Orchestrator")
from shared.db import get_client  # noqa: E402

try:
    from zoneinfo import ZoneInfo
    AEST = ZoneInfo("Australia/Brisbane")
except Exception:  # pragma: no cover
    AEST = timezone(timedelta(hours=10))

COLL = "rl_recommendations"

# --- the caps. These are the whole point of the file. ------------------------------
MAX_OPEN_PER_DOMAIN = 2      # a domain may hold this many undecided items. Hard.
MAX_BRIEF_ITEMS = 5          # Samantha may put this many decisions in a weekly brief.

DOMAINS = ["geo", "seo", "ads", "articles", "onsite", "ops", "valuation"]
TYPES = ["fix", "experiment", "question", "decision", "fyi"]
EFFORTS = ["S", "M", "L"]
REVERSIBILITY = ["reversible", "hard", "irreversible"]

# status lifecycle:
#   open ──verdict yes──> approved ──ship──> shipped ──grade──> graded
#        ──verdict no───> rejected
#        ──verdict later> deferred  (does NOT count against the cap; parked, not lost)
#        ──withdraw─────> withdrawn
#        ──supersede────> superseded
OPEN_STATUSES = ["open"]              # counts against MAX_OPEN_PER_DOMAIN
LIVE_STATUSES = ["open", "approved", "shipped"]


def _now():
    return datetime.now(timezone.utc)


def _iso():
    return _now().isoformat()


def _week(dt=None):
    return (dt or _now()).astimezone(AEST).strftime("%G-W%V")


def _coll():
    return get_client()["system_monitor"][COLL]


def _next_id(domain):
    """REC-<domain>-NNN, monotonic per domain. Never reuses a number even after
    withdrawal — an id in a cycle doc must always resolve to the same thing."""
    c = _coll()
    seq = 0
    for d in c.find({"domain": domain}, {"_id": 1}):
        m = re.match(rf"^REC-{re.escape(domain)}-(\d+)$", d["_id"])
        if m:
            seq = max(seq, int(m.group(1)))
    return f"REC-{domain}-{seq + 1:03d}"


def _open_count(domain):
    return _coll().count_documents({"domain": domain, "status": {"$in": OPEN_STATUSES}})


def _get(rec_id):
    d = _coll().find_one({"_id": rec_id})
    if not d:
        sys.exit(f"ERROR: no such recommendation: {rec_id}")
    return d


# ---------------------------------------------------------------------------------
# propose
# ---------------------------------------------------------------------------------
def cmd_propose(a):
    if a.domain not in DOMAINS:
        sys.exit(f"ERROR: unknown domain {a.domain!r}. Known: {', '.join(DOMAINS)}")

    c = _coll()

    # Supersede first, so a domain at cap can always replace its own weakest item.
    superseded = None
    if a.supersedes:
        old = _get(a.supersedes)
        if old["domain"] != a.domain:
            sys.exit(f"ERROR: {a.supersedes} belongs to domain {old['domain']!r}, "
                     f"not {a.domain!r}. A domain may only supersede its own items.")
        if old["status"] not in OPEN_STATUSES:
            sys.exit(f"ERROR: {a.supersedes} is {old['status']!r}, not open — "
                     "nothing to supersede.")
        superseded = a.supersedes

    n_open = _open_count(a.domain) - (1 if superseded else 0)
    if n_open >= MAX_OPEN_PER_DOMAIN:
        current = list(c.find({"domain": a.domain, "status": {"$in": OPEN_STATUSES}},
                              {"title": 1}))
        lines = "\n".join(f"    {d['_id']}  {d.get('title','')}" for d in current)
        sys.exit(
            f"REFUSED: {a.domain} already holds {n_open} open recommendation(s); the cap "
            f"is {MAX_OPEN_PER_DOMAIN}.\n"
            f"  Currently open:\n{lines}\n"
            f"  This cap is deliberate — it forces you to RANK rather than accumulate.\n"
            f"  If this new item genuinely matters more, replace one:\n"
            f"    --supersedes <ID>            (this item takes its place)\n"
            f"  or drop one you no longer back:\n"
            f"    withdraw --id <ID> --reason '...'\n"
            f"  Do NOT work around this by writing prose into a cycle doc and hoping "
            f"Will reads it. If it did not make your top {MAX_OPEN_PER_DOMAIN}, it waits."
        )

    # Guard the fields that make a recommendation actionable rather than a musing.
    for field in ("title", "claim", "evidence", "proposed"):
        v = (getattr(a, field) or "").strip()
        if len(v) < 12:
            sys.exit(f"ERROR: --{field} is too short to be useful ({len(v)} chars). "
                     "This ledger replaced a file nobody could act on; vague entries "
                     "recreate that problem.")
    if len(a.title) > 100:
        sys.exit(f"ERROR: --title is {len(a.title)} chars; keep it under 100. The brief "
                 "shows titles only — if it needs more, it belongs in --claim.")

    rec = {
        "_id": _next_id(a.domain),
        "domain": a.domain,
        "created_at": _iso(),
        "week": _week(),
        "type": a.type,
        "title": a.title.strip(),
        "claim": a.claim.strip(),
        "evidence": a.evidence.strip(),
        "basis_n": (a.n or "").strip() or None,
        "proposed": a.proposed.strip(),
        "ask": (a.ask or "").strip() or "none — this domain will act if approved",
        "effort": a.effort,
        "reversibility": a.reversibility,
        "expected_effect": {
            "metric": (a.metric or "").strip() or None,
            "direction": (a.direction or "").strip() or None,
            "by": a.by,
        },
        "status": "open",
        "will_verdict": None,
        "will_reason": None,
        "decided_at": None,
        "shipped_at": None,
        "outcome_check_due": None,
        "outcome": None,
        "supersedes": superseded,
        "briefed_in": [],
    }
    c.insert_one(rec)

    if superseded:
        c.update_one({"_id": superseded},
                     {"$set": {"status": "superseded",
                               "superseded_by": rec["_id"],
                               "decided_at": _iso()}})

    print(f"{rec['_id']}  [{a.domain}/{a.type}]  {rec['title']}")
    if superseded:
        print(f"  supersedes {superseded}")
    print(f"  open for {a.domain}: {_open_count(a.domain)}/{MAX_OPEN_PER_DOMAIN}")
    if not rec["expected_effect"]["metric"]:
        print("  ⚠ no --metric given. An item with no measurable claim can never be "
              "graded, so it can never teach this system anything.")
    if not rec["expected_effect"]["by"]:
        print("  ⚠ no --by date given, so nothing will ever surface this for grading. "
              "Re-run with --by YYYY-MM-DD (when the effect should be visible).")
    return rec["_id"]


# ---------------------------------------------------------------------------------
# feedback — the learning signal
# ---------------------------------------------------------------------------------
def cmd_feedback(a):
    """What Will actually did with this domain's past recommendations, and whether the
    ones that shipped worked. A domain agent MUST read this before proposing."""
    c = _coll()
    q = {"domain": a.domain, "status": {"$nin": ["open"]}}
    docs = list(c.find(q).sort("created_at", -1).limit(a.limit))

    if a.json:
        print(json.dumps(docs, indent=2, default=str))
        return

    if not docs:
        print(f"No decided recommendations yet for {a.domain}. This is your first "
              f"cycle under the new ledger — nothing to learn from yet.")
        return

    print(f"═══ WHAT WILL DID WITH {a.domain.upper()}'S PAST RECOMMENDATIONS ═══")
    print("Read the REASONS. They are the clearest statement of his priorities you")
    print("will ever get. Do not re-propose something he declined without addressing")
    print("why he declined it.\n")

    by_verdict = {}
    for d in docs:
        by_verdict.setdefault(d.get("status", "?"), []).append(d)

    for status in ("rejected", "deferred", "approved", "shipped", "graded",
                   "superseded", "withdrawn"):
        group = by_verdict.get(status)
        if not group:
            continue
        print(f"── {status.upper()} ({len(group)}) ──")
        for d in group:
            print(f"  {d['_id']}  {d.get('title','')}")
            if d.get("will_reason"):
                print(f"      Will: \"{d['will_reason']}\"")
            oc = d.get("outcome")
            if oc:
                print(f"      OUTCOME: {oc.get('verdict')} — {oc.get('note','')}")
            elif status == "shipped" and d.get("outcome_check_due"):
                print(f"      shipped, grading due {d['outcome_check_due'][:10]}")
        print()

    graded = [d for d in docs if d.get("outcome")]
    if graded:
        worked = sum(1 for d in graded if d["outcome"].get("verdict") == "worked")
        print(f"Your track record: {worked}/{len(graded)} shipped recommendations "
              f"actually moved their claimed metric.")
        if worked < len(graded) / 2:
            print("  That is below half. Be more conservative about what you claim a "
                  "change will do, and state your N.")


# ---------------------------------------------------------------------------------
# list / brief-candidates
# ---------------------------------------------------------------------------------
def _print_rec(d, verbose=False):
    ee = d.get("expected_effect") or {}
    head = f"{d['_id']}  [{d['domain']}/{d.get('type','?')}]  {d.get('title','')}"
    print(head)
    print(f"    status={d.get('status')}  effort={d.get('effort')}  "
          f"{d.get('reversibility')}  raised={d.get('created_at','')[:10]}")
    if ee.get("metric"):
        print(f"    expects: {ee.get('metric')} {ee.get('direction') or ''} "
              f"by {ee.get('by') or '?'}")
    if verbose:
        print(f"    CLAIM:    {d.get('claim')}")
        print(f"    EVIDENCE: {d.get('evidence')}")
        if d.get("basis_n"):
            print(f"    N:        {d['basis_n']}")
        print(f"    PROPOSED: {d.get('proposed')}")
        print(f"    ASK:      {d.get('ask')}")
    if d.get("will_reason"):
        print(f"    WILL:     \"{d['will_reason']}\"")
    print()


def cmd_list(a):
    q = {}
    if a.domain:
        q["domain"] = a.domain
    if a.status:
        q["status"] = a.status
    elif not a.all:
        q["status"] = {"$in": OPEN_STATUSES}
    docs = list(_coll().find(q).sort([("domain", 1), ("created_at", 1)]))
    if a.json:
        print(json.dumps(docs, indent=2, default=str))
        return
    if not docs:
        print("(none)")
        return
    for d in docs:
        _print_rec(d, verbose=a.verbose)
    print(f"{len(docs)} recommendation(s)")


def cmd_brief_candidates(a):
    """Everything awaiting Will, all domains — Samantha's input for the weekly brief.
    Deliberately does NOT rank: ranking across domains is Samantha's judgement, and
    a scoring formula here would just be a number she'd feel obliged to defer to."""
    docs = list(_coll().find({"status": {"$in": OPEN_STATUSES}})
                .sort([("domain", 1), ("created_at", 1)]))
    if a.json:
        print(json.dumps(docs, indent=2, default=str))
        return
    print(f"═══ {len(docs)} OPEN ACROSS ALL DOMAINS ═══")
    print(f"The weekly brief carries at most {MAX_BRIEF_ITEMS} decisions. If there are")
    print("more than that here, the rest wait for next week — do not overflow the brief.")
    print("Rank by: what it unblocks × how confident the evidence is ÷ effort.\n")
    for d in docs:
        _print_rec(d, verbose=True)
    per_domain = {}
    for d in docs:
        per_domain[d["domain"]] = per_domain.get(d["domain"], 0) + 1
    print("open per domain: " + ", ".join(f"{k}={v}" for k, v in sorted(per_domain.items())))
    if len(docs) > MAX_BRIEF_ITEMS:
        print(f"⚠ {len(docs)} open but only {MAX_BRIEF_ITEMS} may be briefed. "
              f"{len(docs) - MAX_BRIEF_ITEMS} will wait.")


# ---------------------------------------------------------------------------------
# verdict / withdraw / ship / grade
# ---------------------------------------------------------------------------------
_VERDICT_STATUS = {"yes": "approved", "no": "rejected", "later": "deferred"}


def cmd_verdict(a):
    d = _get(a.id)
    if d["status"] not in OPEN_STATUSES:
        sys.exit(f"ERROR: {a.id} is {d['status']!r}; only open items take a verdict.")
    if not (a.reason or "").strip():
        sys.exit("ERROR: --reason is required. The reason IS the training signal — a "
                 "verdict without one teaches the domain nothing and it will re-propose "
                 "the same thing next week.")
    status = _VERDICT_STATUS[a.verdict]
    upd = {"status": status, "will_verdict": a.verdict,
           "will_reason": a.reason.strip(), "decided_at": _iso()}
    _coll().update_one({"_id": a.id}, {"$set": upd})
    print(f"{a.id} → {status}  (\"{a.reason.strip()}\")")
    if status == "approved":
        print("  next: `ship --id %s` once the change is actually live, which sets the "
              "grading due date." % a.id)


def cmd_withdraw(a):
    d = _get(a.id)
    if d["status"] not in OPEN_STATUSES:
        sys.exit(f"ERROR: {a.id} is {d['status']!r}; only open items can be withdrawn.")
    _coll().update_one({"_id": a.id}, {"$set": {
        "status": "withdrawn", "will_reason": None,
        "withdrawn_reason": (a.reason or "").strip() or "no reason given",
        "decided_at": _iso()}})
    print(f"{a.id} → withdrawn. open for {d['domain']}: "
          f"{_open_count(d['domain'])}/{MAX_OPEN_PER_DOMAIN}")


def cmd_ship(a):
    d = _get(a.id)
    if d["status"] != "approved":
        sys.exit(f"ERROR: {a.id} is {d['status']!r}; only approved items can ship.")
    due = (_now() + timedelta(days=a.grade_in_days)).isoformat()
    _coll().update_one({"_id": a.id}, {"$set": {
        "status": "shipped", "shipped_at": _iso(),
        "ship_note": (a.note or "").strip() or None,
        "outcome_check_due": due}})
    print(f"{a.id} → shipped. Grading due {due[:10]} "
          f"({a.grade_in_days}d) against: "
          f"{(d.get('expected_effect') or {}).get('metric') or 'NO METRIC SET'}")


def cmd_grade(a):
    d = _get(a.id)
    if d["status"] not in ("shipped", "graded"):
        sys.exit(f"ERROR: {a.id} is {d['status']!r}; only shipped items can be graded.")
    if not (a.note or "").strip():
        sys.exit("ERROR: --note is required — record the actual measurement, not just "
                 "the verdict.")
    _coll().update_one({"_id": a.id}, {"$set": {
        "status": "graded",
        "outcome": {"graded_at": _iso(), "verdict": a.verdict,
                    "note": a.note.strip()}}})
    print(f"{a.id} → graded: {a.verdict} — {a.note.strip()}")


def cmd_due_for_grading(a):
    now = _iso()
    docs = list(_coll().find({"status": "shipped",
                              "outcome_check_due": {"$lte": now}})
                .sort("outcome_check_due", 1))
    if a.json:
        print(json.dumps(docs, indent=2, default=str))
        return
    if not docs:
        print("(nothing due for grading)")
        return
    print(f"═══ {len(docs)} SHIPPED ITEM(S) DUE FOR OUTCOME GRADING ═══")
    print("Each of these claimed a metric would move. Go and measure it. A claim that")
    print("is never checked is how the old system convinced itself it was working.\n")
    for d in docs:
        ee = d.get("expected_effect") or {}
        print(f"{d['_id']}  [{d['domain']}]  {d.get('title')}")
        print(f"    shipped {d.get('shipped_at','')[:10]}, due {d.get('outcome_check_due','')[:10]}")
        print(f"    claimed: {ee.get('metric')} {ee.get('direction') or ''}")
        print(f"    grade with: recommendations.py grade --id {d['_id']} "
              f"--verdict worked|no_effect|backfired|unmeasurable --note '...'\n")


# ---------------------------------------------------------------------------------
# stats
# ---------------------------------------------------------------------------------
def cmd_stats(a):
    c = _coll()
    rows = []
    for dom in DOMAINS:
        docs = list(c.find({"domain": dom}))
        if not docs:
            continue
        by = {}
        for d in docs:
            by[d.get("status", "?")] = by.get(d.get("status", "?"), 0) + 1
        decided = [d for d in docs if d.get("will_verdict")]
        approved = sum(1 for d in decided if d["will_verdict"] == "yes")
        graded = [d for d in docs if d.get("outcome")]
        worked = sum(1 for d in graded if d["outcome"].get("verdict") == "worked")
        rows.append({
            "domain": dom, "total": len(docs), "open": by.get("open", 0),
            "approved_rate": f"{approved}/{len(decided)}" if decided else "—",
            "worked_rate": f"{worked}/{len(graded)}" if graded else "—",
            "by_status": by,
        })
    if a.json:
        print(json.dumps(rows, indent=2, default=str))
        return
    print(f"{'domain':10s} {'total':>5s} {'open':>5s} {'Will said yes':>14s} {'actually worked':>16s}")
    for r in rows:
        print(f"{r['domain']:10s} {r['total']:5d} {r['open']:5d} "
              f"{r['approved_rate']:>14s} {r['worked_rate']:>16s}")
    if not rows:
        print("(no recommendations yet)")
        return
    print("\n'Will said yes' is how well a domain reads his priorities.")
    print("'actually worked' is whether its claims were true. They are different "
          "failures and both matter.")


def cmd_show(a):
    d = _get(a.id)
    if a.json:
        print(json.dumps(d, indent=2, default=str))
        return
    _print_rec(d, verbose=True)
    for k in ("supersedes", "superseded_by", "shipped_at", "outcome_check_due"):
        if d.get(k):
            print(f"    {k}: {d[k]}")
    if d.get("outcome"):
        print(f"    outcome: {json.dumps(d['outcome'], default=str)}")


def cmd_mark_briefed(a):
    wk = a.week or _week()
    n = _coll().update_many({"_id": {"$in": a.ids}},
                            {"$addToSet": {"briefed_in": wk}}).modified_count
    print(f"marked {n} recommendation(s) as briefed in {wk}")


# ---------------------------------------------------------------------------------
def main():
    p = argparse.ArgumentParser(description=__doc__.split("\n")[1],
                                formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = p.add_subparsers(dest="cmd", required=True)

    sp = sub.add_parser("propose", help="raise a recommendation (cap-enforced)")
    sp.add_argument("--domain", required=True, choices=DOMAINS)
    sp.add_argument("--type", required=True, choices=TYPES)
    sp.add_argument("--title", required=True, help="<100 chars; shown in the brief")
    sp.add_argument("--claim", required=True, help="one sentence: what is true")
    sp.add_argument("--evidence", required=True,
                    help="the numbers AND the command/query that produced them")
    sp.add_argument("--proposed", required=True, help="what to actually do")
    sp.add_argument("--ask", default="", help="exactly what Will must decide")
    sp.add_argument("--n", default="", help="sample size / basis for the claim")
    sp.add_argument("--metric", default="", help="the metric this should move")
    sp.add_argument("--direction", default="", help="e.g. 'up from 2.1%% to ~3%%'")
    sp.add_argument("--by", default=None, help="YYYY-MM-DD the effect should be visible")
    sp.add_argument("--effort", default="M", choices=EFFORTS)
    sp.add_argument("--reversibility", default="reversible", choices=REVERSIBILITY)
    sp.add_argument("--supersedes", default=None, help="REC id this replaces")
    sp.set_defaults(func=cmd_propose)

    sp = sub.add_parser("feedback", help="what Will did with this domain's past items")
    sp.add_argument("--domain", required=True, choices=DOMAINS)
    sp.add_argument("--limit", type=int, default=30)
    sp.add_argument("--json", action="store_true")
    sp.set_defaults(func=cmd_feedback)

    sp = sub.add_parser("list")
    sp.add_argument("--domain", choices=DOMAINS)
    sp.add_argument("--status")
    sp.add_argument("--all", action="store_true", help="every status, not just open")
    sp.add_argument("--verbose", action="store_true")
    sp.add_argument("--json", action="store_true")
    sp.set_defaults(func=cmd_list)

    sp = sub.add_parser("brief-candidates", help="all open items — Samantha's input")
    sp.add_argument("--json", action="store_true")
    sp.set_defaults(func=cmd_brief_candidates)

    sp = sub.add_parser("show")
    sp.add_argument("--id", required=True)
    sp.add_argument("--json", action="store_true")
    sp.set_defaults(func=cmd_show)

    sp = sub.add_parser("verdict", help="record Will's decision + REASON")
    sp.add_argument("--id", required=True)
    sp.add_argument("--verdict", required=True, choices=list(_VERDICT_STATUS))
    sp.add_argument("--reason", required=True)
    sp.set_defaults(func=cmd_verdict)

    sp = sub.add_parser("withdraw", help="a domain drops its own item")
    sp.add_argument("--id", required=True)
    sp.add_argument("--reason", default="")
    sp.set_defaults(func=cmd_withdraw)

    sp = sub.add_parser("ship", help="an approved item is now live; starts the clock")
    sp.add_argument("--id", required=True)
    sp.add_argument("--note", default="")
    sp.add_argument("--grade-in-days", type=int, default=28)
    sp.set_defaults(func=cmd_ship)

    sp = sub.add_parser("grade", help="did it actually work?")
    sp.add_argument("--id", required=True)
    sp.add_argument("--verdict", required=True,
                    choices=["worked", "no_effect", "backfired", "unmeasurable"])
    sp.add_argument("--note", required=True, help="the actual measurement")
    sp.set_defaults(func=cmd_grade)

    sp = sub.add_parser("due-for-grading")
    sp.add_argument("--json", action="store_true")
    sp.set_defaults(func=cmd_due_for_grading)

    sp = sub.add_parser("stats", help="per-domain approval + hit rate")
    sp.add_argument("--json", action="store_true")
    sp.set_defaults(func=cmd_stats)

    sp = sub.add_parser("mark-briefed")
    sp.add_argument("--ids", nargs="+", required=True)
    sp.add_argument("--week", default=None)
    sp.set_defaults(func=cmd_mark_briefed)

    a = p.parse_args()
    a.func(a)


if __name__ == "__main__":
    main()
