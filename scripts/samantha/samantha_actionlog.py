#!/usr/bin/env python3
"""
samantha_actionlog.py — the UNIFIED, queryable log of everything Samantha does.

Why: her actions were scattered across a raw nightly-only transcript (local, not
queryable, with gaps), plus three narrow slices that depend on her remembering to
write them (fix-history, change_ledger, ad_decisions), plus a Decision Log tab that
was chronically empty. You cannot target improvements from that. This gives ONE
structured, queryable collection — `system_monitor.samantha_actions` — fed by:

  1. `harvest` / `harvest-interactive` — parse a run TRANSCRIPT (the nightly daily_run
     JSONL, and the interactive Claude Code session JSONLs) and extract EVERY tool call
     into a structured row. INCREMENTAL: per-file line cursor in
     `samantha_actionlog_state`, so re-runs only parse new lines (the interactive dir
     has thousands of files, some 50MB+). This is the "log everything" guarantee — it
     does not depend on her remembering.
  2. `log` — a one-line helper she calls for a meaningful action + rationale.

`report [--telegram]` aggregates the log so improvements can be targeted (analysis-vs-
ship ratio, unmeasured changes, skipped Task G, repeated commands) — and can push a
weekly summary to Will on Telegram.

Usage:
  python3 scripts/samantha/samantha_actionlog.py harvest --transcript <path> [--channel nightly]
  python3 scripts/samantha/samantha_actionlog.py harvest-interactive [--since-hours 36] [--max-files 40]
  python3 scripts/samantha/samantha_actionlog.py log --category ad --summary "paused ad X" [--target .. --tags a,b]
  python3 scripts/samantha/samantha_actionlog.py report [--days 7] [--channel ..] [--telegram]
"""
from __future__ import annotations
import argparse, glob, json, os, re, subprocess, sys
from datetime import datetime, timezone, timedelta

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))
from src.mongo_client_factory import get_mongo_client

ORCH = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))  # repo root
INTERACTIVE_DIR = "/home/projects/.claude/projects/-home-fields-Fields-Orchestrator"


def _sm():
    return get_mongo_client()["system_monitor"]


def _now():
    return datetime.now(timezone.utc)


# ---- categorisation -------------------------------------------------------
def _categorise(tool, inp):
    tool = tool or ""
    inp = inp or ""
    def find(pat):
        m = re.search(pat, inp, re.I)
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
                         ("samantha_actionlog.py", "actionlog"), ("lead_intelligence.py", "leads"),
                         ("generate_appraisal", "appraisal"), ("ad-flow-report", "ad_analysis"),
                         ("site-inspector", "screenshot"), ("from_will.py", "willnotes")]:
            if scr in c:
                return cat, scr, cat.replace("_", " ")
        m = re.search(r"python3?\s+([^\s'\"]+\.py)", cmd)
        if m:
            return "script_run", os.path.basename(m.group(1)), f"run {os.path.basename(m.group(1))}"
        if any(k in c for k in ["get_mongo_client", "pymongo", ".find(", ".aggregate(", "mongo", "posthog", "hogql"]):
            return "query", "", "data query"
        return "shell", "", (cmd[:60] if cmd else "shell")
    return (tool or "unknown").lower(), "", (tool or "action")[:40]


def _blocks(rec):
    """Yield (kind, tool, payload) from a record — daily_run compact ({'t':..}) OR
    Claude Code ({'type':'assistant','message':{'content':[...]}})."""
    if "t" in rec:
        t = rec.get("t")
        if t == "tool_use":
            yield ("tool_use", rec.get("name"), rec.get("input", ""))
        elif t == "text" and (rec.get("text") or "").strip():
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
            elif bt == "text" and (b.get("text") or "").strip():
                yield ("text", None, b.get("text", ""))
            elif bt == "tool_result":
                yield ("tool_result", None, str(b.get("content", "")))


def _harvest_file(coll, state, path, channel):
    """Incremental harvest of one transcript file. Stable key = source:line:block, so
    reprocessing is idempotent; a per-file line cursor skips already-parsed lines."""
    source = os.path.basename(path)
    st = state.find_one({"_id": source}) or {}
    start = st.get("lines_done", 0)
    mdate = re.search(r"(\d{4}-\d{2}-\d{2})", source)
    default_date = mdate.group(1) if mdate else _now().strftime("%Y-%m-%d")
    n_new = 0
    li = start - 1
    pending_key = None
    with open(path, "r", errors="ignore") as fh:
        for li, line in enumerate(fh):
            if li < start:
                continue
            line = line.strip()
            if not line:
                continue
            try:
                rec = json.loads(line)
            except Exception:
                continue
            # date: prefer record timestamp, else filename/default
            rts = rec.get("timestamp") or rec.get("ts") or ""
            day = (rts[:10] if isinstance(rts, str) and len(rts) >= 10 and rts[4] == "-" else default_date)
            for bi, (kind, tool, payload) in enumerate(_blocks(rec)):
                key = f"{source}:{li}:{bi}"
                if kind == "tool_use":
                    payload = payload if isinstance(payload, str) else str(payload)
                    cat, target, summary = _categorise(tool, payload)
                    row = {"_id": key, "source": source, "channel": channel, "date": day,
                           "line": li, "kind": "tool_use", "tool": tool, "category": cat,
                           "target": target, "summary": summary, "detail": payload[:800],
                           "harvested_at": _now()}
                    r = coll.update_one({"_id": key}, {"$setOnInsert": row}, upsert=True)
                    if r.upserted_id is not None:
                        n_new += 1
                    pending_key = key
                elif kind == "tool_result" and pending_key:
                    coll.update_one({"_id": pending_key}, {"$set": {"result": str(payload)[:400]}})
                    pending_key = None
                elif kind == "text":
                    txt = payload.strip()
                    pending_key = None
                    if len(txt) >= 60:
                        row = {"_id": key, "source": source, "channel": channel, "date": day,
                               "line": li, "kind": "note", "tool": None, "category": "note",
                               "target": "", "summary": txt[:140], "detail": txt[:800],
                               "harvested_at": _now()}
                        r = coll.update_one({"_id": key}, {"$setOnInsert": row}, upsert=True)
                        if r.upserted_id is not None:
                            n_new += 1
    state.update_one({"_id": source},
                     {"$set": {"lines_done": li + 1, "channel": channel, "updated_at": _now()}},
                     upsert=True)
    return n_new


def cmd_harvest(a):
    sm = _sm()
    if not os.path.exists(a.transcript):
        print(f"ERROR: no transcript at {a.transcript}"); return 1
    n = _harvest_file(sm["samantha_actions"], sm["samantha_actionlog_state"], a.transcript, a.channel)
    print(f"harvested {os.path.basename(a.transcript)}: {n} new rows (channel={a.channel})")
    return 0


def cmd_harvest_interactive(a):
    sm = _sm()
    coll = sm["samantha_actions"]; state = sm["samantha_actionlog_state"]
    cutoff = _now().timestamp() - a.since_hours * 3600
    files = [p for p in glob.glob(os.path.join(a.dir, "*.jsonl")) if os.path.getmtime(p) >= cutoff]
    files.sort(key=os.path.getmtime, reverse=True)
    files = files[: a.max_files]
    total = 0
    for p in files:
        try:
            total += _harvest_file(coll, state, p, "interactive")
        except Exception as e:  # noqa: BLE001
            print(f"  skip {os.path.basename(p)}: {e}")
    print(f"harvest-interactive: {len(files)} recent file(s) (<{a.since_hours}h), {total} new rows")
    return 0


def cmd_log(a):
    coll = _sm()["samantha_actions"]
    key = f"manual:{int(_now().timestamp()*1000)}"
    coll.insert_one({"_id": key, "source": "manual", "channel": a.channel,
                     "date": _now().strftime("%Y-%m-%d"), "kind": "manual", "tool": None,
                     "category": a.category, "target": a.target, "summary": a.summary,
                     "detail": a.detail, "result": a.result, "reversible": a.reversible,
                     "tags": [t for t in a.tags.split(",") if t], "harvested_at": _now()})
    print(f"logged: [{a.category}] {a.summary}")
    return 0


def cmd_report(a):
    from collections import Counter
    sm = _sm(); coll = sm["samantha_actions"]
    since = _now() - timedelta(days=a.days)
    q = {"harvested_at": {"$gte": since}}
    if a.channel:
        q["channel"] = a.channel
    rows = list(coll.find(q))
    if not rows:
        msg = f"Samantha action log: no actions in the last {a.days}d (channel={a.channel or 'all'})."
        print(msg)
        if a.telegram:
            _telegram(msg)
        return 0
    cat = Counter(r.get("category") for r in rows)
    tgt = Counter(r.get("target") for r in rows if r.get("target"))
    ch = Counter(r.get("channel") for r in rows)
    analysis = sum(cat[c] for c in ("query", "read", "search", "shell", "note"))
    ship = sum(cat[c] for c in ("push", "code_edit", "ad", "git"))
    live_unmeasured = sm["samantha_changes"].count_documents({"status": "live", "latest_verdict": None})
    gi = cat.get("growth_ideation", 0); board = cat.get("board", 0); wn = cat.get("willnotes", 0)

    lines = [f"=== Samantha action log — last {a.days}d ({len(rows)} actions; {dict(ch)}) ==="]
    lines.append("by category: " + ", ".join(f"{c}:{n}" for c, n in cat.most_common(10)))
    lines.append(f"analysis:ship = {analysis}:{ship} ({analysis/max(ship,1):.1f}:1)")
    lines.append(f"Will Notes:{wn}  board:{board}  growth-ideation:{gi}")
    lines.append("top targets: " + ", ".join(f"{str(t)[:26]}×{n}" for t, n in tgt.most_common(6)))
    flags = []
    if ship == 0 and analysis > 10:
        flags.append("⚠ analysis but ZERO ships (analysing without executing)")
    if live_unmeasured:
        flags.append(f"⚠ {live_unmeasured} live change(s) never measured")
    if gi == 0:
        flags.append("⚠ growth_ideation (Task G) not run in window")
    if board == 0:
        flags.append("⚠ 0 Task-Board writes (Decision Log going stale)")
    repeated = [str(t) for t, n in tgt.items() if n >= 8]
    if repeated:
        flags.append("repeat cmds worth scripting: " + ", ".join(repeated[:4]))
    if flags:
        lines.append("IMPROVEMENT TARGETS:\n  - " + "\n  - ".join(flags))
    out = "\n".join(lines)
    print(out)
    if a.telegram:
        _telegram("📊 Weekly Samantha action review\n\n" + out)
    return 0


def _telegram(text):
    try:
        r = subprocess.run(["python3", "scripts/telegram_notify.py", text[:3900]],
                           cwd=ORCH, capture_output=True, text=True, timeout=30)
        print("[telegram]", "sent" if r.returncode == 0 else f"failed: {r.stderr[:120]}")
    except Exception as e:  # noqa: BLE001
        print(f"[telegram] error: {e}")


def main():
    ap = argparse.ArgumentParser()
    sub = ap.add_subparsers(dest="cmd", required=True)
    h = sub.add_parser("harvest"); h.add_argument("--transcript", required=True)
    h.add_argument("--channel", default="nightly"); h.set_defaults(func=cmd_harvest)
    hi = sub.add_parser("harvest-interactive")
    hi.add_argument("--dir", default=INTERACTIVE_DIR)
    hi.add_argument("--since-hours", type=int, default=36, dest="since_hours")
    hi.add_argument("--max-files", type=int, default=40, dest="max_files")
    hi.set_defaults(func=cmd_harvest_interactive)
    l = sub.add_parser("log"); l.add_argument("--category", required=True); l.add_argument("--summary", required=True)
    l.add_argument("--target", default=""); l.add_argument("--detail", default=""); l.add_argument("--result", default="")
    l.add_argument("--reversible", default=""); l.add_argument("--tags", default=""); l.add_argument("--channel", default="interactive")
    l.set_defaults(func=cmd_log)
    r = sub.add_parser("report"); r.add_argument("--days", type=int, default=7)
    r.add_argument("--channel", default=""); r.add_argument("--telegram", action="store_true")
    r.set_defaults(func=cmd_report)
    a = ap.parse_args()
    return a.func(a)


if __name__ == "__main__":
    raise SystemExit(main())
