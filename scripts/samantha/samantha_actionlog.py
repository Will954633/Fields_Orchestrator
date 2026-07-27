#!/usr/bin/env python3
"""
samantha_actionlog.py — the UNIFIED, queryable log of everything Samantha does.

Why: her actions were scattered across a raw nightly-only transcript (local, not
queryable, with gaps), plus three narrow slices that depend on her remembering to
write them (fix-history, change_ledger, ad_decisions), plus a Decision Log tab that
was chronically empty. You cannot target improvements from that. This gives ONE
structured, queryable collection — `system_monitor.samantha_actions` — fed two ways:

  1. `harvest` — parses a run TRANSCRIPT (nightly daily_run JSONL, or an interactive
     Claude Code session JSONL) and extracts EVERY tool call into a structured row.
     This is the "log everything" guarantee — it does not depend on her remembering.
  2. `log` — a one-line helper she calls for a meaningful action + rationale
     ("paused ad X because Y") when the raw tool call doesn't capture the intent.

`report` aggregates the log so you can target improvements (analysis-vs-ship ratio,
unmeasured changes, repeated commands, where time actually goes).

Usage:
  python3 scripts/samantha/samantha_actionlog.py harvest --transcript <path> [--channel nightly|interactive]
  python3 scripts/samantha/samantha_actionlog.py log --category ad --summary "paused ad X" [--target ... --detail ... --tags a,b]
  python3 scripts/samantha/samantha_actionlog.py report [--days 14] [--channel nightly]
"""
from __future__ import annotations
import argparse, ast, json, os, re, sys
from datetime import datetime, timezone, timedelta

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))
from src.mongo_client_factory import get_mongo_client

COLL = "samantha_actions"


def _db():
    return get_mongo_client()["system_monitor"][COLL]


def _now():
    return datetime.now(timezone.utc)


# ---- categorisation -------------------------------------------------------
def _categorise(tool: str, inp: str):
    """Return (category, target, summary) from a tool name + stringified input."""
    tool = tool or ""
    low = (inp or "").lower()
    def find(pat):
        m = re.search(pat, inp or "", re.I)
        return m.group(1) if m else ""
    if tool in ("Edit", "Write", "NotebookEdit"):
        f = find(r"file_path['\"]?\s*[:=]\s*['\"]([^'\"]+)")
        return "code_edit", f, f"{tool} {os.path.basename(f) or ''}".strip()
    if tool == "Read":
        return "read", find(r"file_path['\"]?\s*[:=]\s*['\"]([^'\"]+)"), "read file"
    if tool in ("Grep", "Glob"):
        return "search", "", "search"
    if tool in ("Task", "Agent"):
        return "delegate", "", "spawn subagent"
    if tool.startswith("mcp__"):
        return "mcp", tool.replace("mcp__", ""), tool.replace("mcp__", "")[:40]
    if tool == "Bash":
        cmd = find(r"command['\"]?\s*[:=]\s*['\"](.+?)['\"]\s*,\s*['\"]description") or inp
        c = cmd.lower()
        if "gh api" in c and ("put" in c or "contents/" in c):
            return "push", find(r"contents/([^'\" ]+)"), "push to GitHub"
        if re.search(r"\bgit (commit|push|add|checkout|branch)", c):
            return "git", "", "git"
        if "telegram_notify" in c:
            return "telegram", "", "Telegram Will"
        for scr, cat in [("running_doc.py", "willnotes"), ("task_board.py", "board"),
                         ("change_ledger.py", "ledger"), ("hypothesis_queue.py", "hypothesis"),
                         ("growth_ideation.py", "growth_ideation"), ("session_folder.py", "session_folder"),
                         ("lead_intelligence.py", "leads"), ("generate_appraisal", "appraisal"),
                         ("ad-flow-report", "ad_analysis"), ("site-inspector", "screenshot")]:
            if scr in c:
                return cat, scr, cat.replace("_", " ")
        m = re.search(r"python3?\s+([^\s'\"]+\.py)", cmd)
        if m:
            return "script_run", os.path.basename(m.group(1)), f"run {os.path.basename(m.group(1))}"
        if any(k in c for k in ["get_mongo_client", "pymongo", ".find(", ".aggregate(", "mongo", "posthog", "hogql"]):
            return "query", "", "data query"
        return "shell", "", (cmd[:60] if cmd else "shell")
    return (tool or "unknown").lower(), "", (tool or "action")[:40]


# ---- normalise a transcript line into content blocks ----------------------
def _blocks(rec):
    """Yield (kind, tool, payload) tuples from one transcript record, handling both
    the daily_run compact format ({'t': ...}) and the Claude Code format
    ({'type':'assistant','message':{'content':[...]}})."""
    if "t" in rec:  # daily_run compact
        t = rec.get("t")
        if t == "tool_use":
            yield ("tool_use", rec.get("name"), rec.get("input", ""))
        elif t == "text" and rec.get("text", "").strip():
            yield ("text", None, rec.get("text", ""))
        elif t == "tool_result":
            yield ("tool_result", None, rec.get("content", ""))
        return
    msg = rec.get("message") or {}
    content = msg.get("content") if isinstance(msg, dict) else None
    if isinstance(content, list):
        for b in content:
            if not isinstance(b, dict):
                continue
            bt = b.get("type")
            if bt == "tool_use":
                yield ("tool_use", b.get("name"), json.dumps(b.get("input", "")))
            elif bt == "text" and b.get("text", "").strip():
                yield ("text", None, b.get("text", ""))
            elif bt == "tool_result":
                yield ("tool_result", None, str(b.get("content", "")))


def cmd_harvest(a):
    path = a.transcript
    if not os.path.exists(path):
        print(f"ERROR: no transcript at {path}"); return 1
    source = os.path.basename(path)
    mdate = re.search(r"(\d{4}-\d{2}-\d{2})", source)
    date_str = a.date or (mdate.group(1) if mdate else _now().strftime("%Y-%m-%d"))
    coll = _db()
    seq = 0
    pending = None  # a tool_use row awaiting its tool_result
    n_new = 0
    def flush(pending):
        nonlocal n_new
        if not pending:
            return
        res = coll.update_one({"source": source, "seq": pending["seq"]},
                              {"$setOnInsert": pending}, upsert=True)
        if res.upserted_id is not None:
            n_new += 1
    for line in open(path):
        line = line.strip()
        if not line:
            continue
        try:
            rec = json.loads(line)
        except Exception:
            continue
        ts = rec.get("ts")
        for kind, tool, payload in _blocks(rec):
            if kind == "tool_use":
                flush(pending)
                cat, target, summary = _categorise(tool, payload if isinstance(payload, str) else str(payload))
                pending = {
                    "source": source, "seq": seq, "channel": a.channel, "date": date_str,
                    "ts_str": ts, "kind": "tool_use", "tool": tool, "category": cat,
                    "target": target, "summary": summary,
                    "detail": (payload if isinstance(payload, str) else str(payload))[:800],
                    "harvested_at": _now(),
                }
                seq += 1
            elif kind == "tool_result" and pending is not None:
                pending["result"] = str(payload)[:400]
                flush(pending); pending = None
            elif kind == "text":
                flush(pending); pending = None
                # keep only substantive decision-like text (skip short filler)
                txt = payload.strip()
                if len(txt) >= 40:
                    coll.update_one({"source": source, "seq": seq},
                        {"$setOnInsert": {"source": source, "seq": seq, "channel": a.channel,
                         "date": date_str, "ts_str": ts, "kind": "note", "tool": None,
                         "category": "note", "target": "", "summary": txt[:140],
                         "detail": txt[:800], "harvested_at": _now()}}, upsert=True)
                seq += 1
    flush(pending)
    print(f"harvested {source}: {n_new} new action rows (channel={a.channel}, date={date_str})")
    return 0


def cmd_log(a):
    coll = _db()
    row = {"source": "manual", "seq": int(_now().timestamp()), "channel": a.channel,
           "date": _now().strftime("%Y-%m-%d"), "ts_str": _now().strftime("%H:%M:%S"),
           "kind": "manual", "tool": None, "category": a.category, "target": a.target,
           "summary": a.summary, "detail": a.detail, "result": a.result,
           "reversible": a.reversible, "tags": [t for t in a.tags.split(",") if t],
           "harvested_at": _now()}
    coll.insert_one(row)
    print(f"logged: [{a.category}] {a.summary}")
    return 0


def cmd_report(a):
    coll = _db()
    since = _now() - timedelta(days=a.days)
    q = {"harvested_at": {"$gte": since}}
    if a.channel:
        q["channel"] = a.channel
    rows = list(coll.find(q))
    if not rows:
        print(f"no actions logged in the last {a.days}d (channel={a.channel or 'all'})."); return 0
    from collections import Counter
    cat = Counter(r.get("category") for r in rows)
    tgt = Counter(r.get("target") for r in rows if r.get("target"))
    ch = Counter(r.get("channel") for r in rows)
    dates = Counter(r.get("date") for r in rows)
    print(f"=== Samantha action log — last {a.days}d ({len(rows)} actions, channels {dict(ch)}) ===")
    print("\nby category:")
    for c, n in cat.most_common():
        print(f"   {c:16} {n}")
    print("\ntop targets (scripts/files/collections):")
    for t, n in tgt.most_common(12):
        print(f"   {str(t)[:44]:44} {n}")
    print("\nby day:")
    for d, n in sorted(dates.items()):
        print(f"   {d}  {n}")
    # improvement heuristics
    analysis = sum(cat[c] for c in ("query", "read", "search", "shell", "note"))
    ship = sum(cat[c] for c in ("push", "code_edit", "ad", "git"))
    print("\n--- IMPROVEMENT TARGETS ---")
    print(f"   analysis actions: {analysis}   |   ship actions: {ship}   "
          f"(ratio {analysis/max(ship,1):.1f}:1)")
    if ship == 0 and analysis > 10:
        print("   ⚠ lots of analysis, ZERO ships — she may be analysing without executing (the documented failure mode).")
    try:
        sm = get_mongo_client()["system_monitor"]
        live_unmeasured = sm["samantha_changes"].count_documents({"status": "live", "latest_verdict": None})
        if live_unmeasured:
            print(f"   ⚠ {live_unmeasured} live change(s) never measured — close the loop (change_ledger measure).")
        # willnotes replies vs board writes as an engagement signal
        wn = cat.get("willnotes", 0); board = cat.get("board", 0); gi = cat.get("growth_ideation", 0)
        print(f"   Will Notes touches: {wn} | board writes: {board} | growth-ideation runs: {gi}")
        if gi == 0:
            print("   ⚠ growth_ideation not run in window — Task G (experiment ideation) may be getting skipped.")
    except Exception:
        pass
    repeated = [t for t, n in tgt.items() if n >= 8]
    if repeated:
        print(f"   repeated targets (≥8×) — candidates to script/cache: {', '.join(str(x) for x in repeated[:6])}")
    return 0


def main():
    ap = argparse.ArgumentParser()
    sub = ap.add_subparsers(dest="cmd", required=True)
    h = sub.add_parser("harvest")
    h.add_argument("--transcript", required=True)
    h.add_argument("--channel", default="nightly")
    h.add_argument("--date", default="")
    h.set_defaults(func=cmd_harvest)
    l = sub.add_parser("log")
    l.add_argument("--category", required=True)
    l.add_argument("--summary", required=True)
    l.add_argument("--target", default=""); l.add_argument("--detail", default="")
    l.add_argument("--result", default=""); l.add_argument("--reversible", default="")
    l.add_argument("--tags", default=""); l.add_argument("--channel", default="interactive")
    l.set_defaults(func=cmd_log)
    r = sub.add_parser("report")
    r.add_argument("--days", type=int, default=14); r.add_argument("--channel", default="")
    r.set_defaults(func=cmd_report)
    a = ap.parse_args()
    return a.func(a)


if __name__ == "__main__":
    raise SystemExit(main())
