#!/usr/bin/env python3
"""
fix_digest.py — a compact INDEX of logs/fix-history/ for the RL domain agents.

Why this exists: every RL domain cycle is supposed to start by reading what has
changed in the business since it last ran. But `logs/fix-history/` now runs ~45
entries and ~1,000 lines PER DAY — roughly 7,000 lines a week. A raw read of the
window burns the agent's whole context before it has looked at a single signal,
so in practice the agents skip it and re-diagnose things that were fixed days ago.

This tool inverts that: one compact line per fix entry (date, problem ID, title,
files touched, recurrence), grouped by day, with drill-down on demand:

    python3 fix_digest.py --days 7                 # the index
    python3 fix_digest.py --days 30 --recurring    # "have we fixed this before?"
    python3 fix_digest.py --days 14 --domain ops   # only entries this domain owns
    python3 fix_digest.py --full BRIGHTDATA-TOKEN-EXPIRED   # the full entry text
    python3 fix_digest.py --days 7 --json          # machine-readable, any mode

Design notes:
  - READ-ONLY. It never writes to fix-history (or anywhere else).
  - Only opens the files inside the requested window (the directory holds 136+).
  - All matching is done in Python. NEVER shell out to grep: `grep` on this VM is
    ugrep and a regex blowup has locked the box up before (see MEMORY:
    ugrep-regex-blowup-vm-lockup).
  - Defensive parsing. Real entries omit fields, use `###` for addenda, and the
    watchdog writes a different field set entirely. Nothing here raises on a
    malformed entry — unparseable headings are COUNTED and reported, never
    silently dropped.
  - stdlib + PyYAML only. No database, no network.

Domain filtering reads `fix_keywords:` from domains.yaml, matched case-insensitively
on token boundaries against the entry's ID, title and Files list. A domain with no
`fix_keywords` gets everything, and the summary says so.
"""
import argparse
import json
import os
import re
import sys
from collections import Counter, defaultdict
from datetime import date, datetime, timedelta

try:
    import yaml
except ImportError:  # keep the tool usable for the index even without PyYAML
    yaml = None

HERE = os.path.dirname(os.path.abspath(__file__))
DEFAULT_HISTORY_DIR = os.path.abspath(os.path.join(HERE, "..", "logs", "fix-history"))
DOMAINS_YAML = os.path.join(HERE, "domains.yaml")

# `## [PROBLEM-ID] Short description — HH:MM AEST`  (also ### / #### addenda)
ENTRY_RE = re.compile(r"^(#{2,6})\s*\[([^\]]{1,80})\]\s*(.*)$")
# any other heading at h2+ inside a day file — counted, not parsed
OTHER_HEADING_RE = re.compile(r"^#{2,6}\s+\S")
FIELD_RE = re.compile(r"^\*\*([A-Za-z][A-Za-z /_-]{0,40}):?\*\*:?\s*(.*)$")
TIME_TAIL_RE = re.compile(r"\s*[—–-]\s*(\d{1,2}:\d{2})\s*(AEST|AEDT|UTC)?\s*$", re.I)
FILENAME_RE = re.compile(r"^(\d{4})-(\d{2})-(\d{2})\.md$")

ORDINALS = {
    "first": "1st", "second": "2nd", "third": "3rd", "fourth": "4th",
    "fifth": "5th", "sixth": "6th", "seventh": "7th", "eighth": "8th",
    "ninth": "9th", "tenth": "10th", "1st": "1st", "2nd": "2nd", "3rd": "3rd",
}


# ---------------------------------------------------------------- file window

def files_in_window(history_dir, start_date, end_date):
    """Return [(date, path)] for YYYY-MM-DD.md files inside the window, newest first."""
    out = []
    try:
        names = os.listdir(history_dir)
    except OSError as exc:
        print(f"fix_digest: cannot read {history_dir}: {exc}", file=sys.stderr)
        return out
    for name in names:
        m = FILENAME_RE.match(name)
        if not m:
            continue
        try:
            d = date(int(m.group(1)), int(m.group(2)), int(m.group(3)))
        except ValueError:
            continue
        if start_date <= d <= end_date:
            out.append((d, os.path.join(history_dir, name)))
    out.sort(key=lambda t: t[0], reverse=True)
    return out


# ------------------------------------------------------------------- parsing

def _clean_id(raw):
    return re.sub(r"\s+", " ", (raw or "").strip()).upper()


def _short_recurrence(text):
    """'Third of this class — ...' -> '3rd'.  'First occurrence' -> '1st'."""
    if not text:
        return ""
    t = text.strip()
    m = re.match(r"^([A-Za-z]+|\d+(?:st|nd|rd|th))", t)
    if not m:
        return ""
    word = m.group(1).lower()
    if word in ORDINALS:
        return ORDINALS[word]
    if re.match(r"^\d+(st|nd|rd|th)$", word):
        return word
    if word in ("recurrence", "recurring", "repeat"):
        return "again"
    if word in ("n", "nth"):
        return "Nth"
    return word[:8]


def _count_files(text):
    """Best-effort count of paths in a **Files:** value. Returns None if unknown."""
    if text is None:
        return None
    t = text.strip()
    if not t:
        return None
    low = t.lower()
    if low.startswith("none") or low in ("n/a", "-", "—"):
        return 0
    # strip markdown emphasis/backticks, then split on commas / newlines
    t = t.replace("`", " ").replace("**", " ")
    parts = re.split(r"[,\n;]+", t)
    n = 0
    for p in parts:
        p = p.strip().strip("*").strip()
        if not p:
            continue
        # a token is a path if it has a / or a file extension
        if "/" in p or re.search(r"\.[A-Za-z0-9]{1,6}\b", p):
            n += 1
    return n if n else None


def parse_file(day, path):
    """Parse one day file -> (entries, stats). Never raises on content."""
    entries = []
    stats = {"unparsed_headings": 0, "read_error": None}
    try:
        with open(path, "r", encoding="utf-8", errors="replace") as fh:
            lines = fh.read().splitlines()
    except OSError as exc:
        stats["read_error"] = str(exc)
        return entries, stats

    current = None

    def close(cur):
        if cur is None:
            return
        body = "\n".join(cur["_body"]).strip()
        cur["raw"] = (cur["_heading"] + "\n" + body).strip()
        fields = {}
        key = None
        for ln in cur["_body"]:
            fm = FIELD_RE.match(ln.strip())
            if fm:
                key = fm.group(1).strip().lower()
                fields[key] = fm.group(2).strip()
            elif key and ln.strip():
                fields[key] = (fields[key] + " " + ln.strip()).strip()
            elif not ln.strip():
                key = None
        cur["fields"] = fields
        files_text = fields.get("files")
        cur["files_text"] = files_text or ""
        cur["file_count"] = _count_files(files_text)
        cur["recurrence"] = _short_recurrence(fields.get("recurrence"))
        cur["recurrence_text"] = fields.get("recurrence", "")
        cur["symptom"] = fields.get("symptom", "")
        for k in ("_body", "_heading"):
            cur.pop(k, None)
        entries.append(cur)

    for ln in lines:
        m = ENTRY_RE.match(ln)
        if m:
            close(current)
            title = m.group(3).strip()
            tm = TIME_TAIL_RE.search(title)
            time_str = ""
            if tm:
                time_str = tm.group(1)
                title = TIME_TAIL_RE.sub("", title).strip()
            title = title.lstrip("—–-").strip()
            current = {
                "date": day.isoformat(),
                "id": _clean_id(m.group(2)),
                "title": title,
                "time": time_str,
                "level": len(m.group(1)),
                "file": os.path.basename(path),
                "_heading": ln.rstrip(),
                "_body": [],
            }
            continue
        if OTHER_HEADING_RE.match(ln):
            # a section heading with no [ID] — ends the current entry, and is
            # reported rather than dropped
            close(current)
            current = None
            stats["unparsed_headings"] += 1
            continue
        if current is not None:
            current["_body"].append(ln)

    close(current)
    return entries, stats


def load_entries(history_dir, start_date, end_date):
    entries, stats = [], {"unparsed_headings": 0, "files_read": 0, "read_errors": []}
    for day, path in files_in_window(history_dir, start_date, end_date):
        e, s = parse_file(day, path)
        if s["read_error"]:
            stats["read_errors"].append(f"{os.path.basename(path)}: {s['read_error']}")
            continue
        stats["files_read"] += 1
        stats["unparsed_headings"] += s["unparsed_headings"]
        entries.extend(e)
    return entries, stats


# ------------------------------------------------------------ domain filtering

def load_domain_keywords(domain, path=DOMAINS_YAML):
    """-> (keywords, note). keywords==[] means 'no filter defined'."""
    if yaml is None:
        return [], "PyYAML unavailable — domain filter skipped, showing everything"
    try:
        with open(path, "r", encoding="utf-8") as fh:
            data = yaml.safe_load(fh) or {}
    except (OSError, yaml.YAMLError) as exc:
        return [], f"could not read {os.path.basename(path)} ({exc}) — showing everything"
    domains = (data or {}).get("domains") or {}
    if domain not in domains:
        known = ", ".join(sorted(domains)) or "none"
        return None, f"unknown domain '{domain}' — known domains: {known}"
    cfg = domains.get(domain) or {}
    kws = cfg.get("fix_keywords") or []
    if isinstance(kws, str):
        kws = [kws]
    kws = [str(k).strip().lower() for k in kws if str(k).strip()]
    if not kws:
        return [], f"domain '{domain}' has no fix_keywords in domains.yaml — showing everything"
    return kws, ""


def _compile_keywords(keywords):
    pats = []
    for kw in keywords:
        pats.append((kw, re.compile(r"(?<![a-z0-9])" + re.escape(kw) + r"(?![a-z0-9])")))
    return pats


def match_entry(entry, patterns):
    """-> list of keywords hit (matching ID, title and Files list)."""
    hay = " ".join([entry.get("id", ""), entry.get("title", ""), entry.get("files_text", "")]).lower()
    return [kw for kw, pat in patterns if pat.search(hay)]


# --------------------------------------------------------------- presentation

def _trunc(s, n):
    s = re.sub(r"\s+", " ", s or "").strip()
    return s if len(s) <= n else s[: n - 1].rstrip() + "…"


def recurring_ids(entries, min_days=2):
    days_by_id = defaultdict(set)
    for e in entries:
        days_by_id[e["id"]].add(e["date"])
    rows = [
        {"id": i, "days": len(d), "dates": sorted(d, reverse=True)}
        for i, d in days_by_id.items()
        if len(d) >= min_days
    ]
    rows.sort(key=lambda r: (-r["days"], r["id"]))
    return rows


def print_index(entries, stats, args, domain_note, total_before_filter):
    by_date = defaultdict(list)
    for e in entries:
        by_date[e["date"]].append(e)

    for d in sorted(by_date, reverse=True):
        print(f"\n{d}")
        for e in sorted(by_date[d], key=lambda x: x.get("time") or "99:99"):
            fc = e["file_count"]
            files_bit = "—" if fc is None else ("no files" if fc == 0 else f"{fc} file{'s' if fc != 1 else ''}")
            rec = e["recurrence"] or "—"
            print(f"  {d}  [{e['id']}]  {_trunc(e['title'], 78)}  ·  {files_bit}  ·  {rec}")

    rec = recurring_ids(entries)
    print("\n" + "-" * 78)
    dates = sorted({e["date"] for e in entries})
    span = f"{dates[0]} → {dates[-1]}" if dates else "no entries in window"
    print(f"SUMMARY  {len(entries)} entries over {stats['files_read']} day-files  ·  {span}")
    if args.domain:
        print(f"         domain filter '{args.domain}': {len(entries)} of {total_before_filter} entries matched")
    if domain_note:
        print(f"         note: {domain_note}")
    print(f"         parse failures: {stats['unparsed_headings']} heading(s) with no [PROBLEM-ID]"
          + (f", {len(stats['read_errors'])} unreadable file(s)" if stats["read_errors"] else ""))
    for err in stats["read_errors"]:
        print(f"           ! {err}")
    if rec:
        top = ", ".join(f"[{r['id']}]×{r['days']}d" for r in rec[:5])
        print(f"         top recurring: {top}")
        print(f"         ({len(rec)} ID(s) on 2+ days — run --recurring for the full list)")
    else:
        print("         top recurring: none (no ID appeared on 2+ distinct days)")


def print_recurring(rows, entries, stats, args):
    if not rows:
        print("No problem ID appeared on 2 or more distinct days in this window.")
        return
    titles = {}
    for e in entries:
        titles.setdefault(e["id"], e["title"])
    print(f"Recurring problem IDs — {len(rows)} ID(s) on 2+ distinct days\n")
    for r in rows:
        print(f"  {r['days']}d  [{r['id']}]  {_trunc(titles.get(r['id'], ''), 60)}")
        print(f"        {', '.join(r['dates'])}")
    print("\n" + "-" * 78)
    print(f"SUMMARY  {len(entries)} entries scanned over {stats['files_read']} day-files  ·  "
          f"{len(rows)} recurring  ·  {stats['unparsed_headings']} parse failure(s)")


def print_full(matches, wanted):
    if not matches:
        print(f"No entry found with problem ID [{wanted}] in this window.")
        print("Widen the window with --days N / --since YYYY-MM-DD, or check the ID in the index.")
        return
    print(f"[{wanted}] — {len(matches)} occurrence(s)\n")
    for e in matches:
        print("=" * 78)
        print(f"{e['date']}  ({e['file']})" + (f"  {e['time']} AEST" if e.get("time") else ""))
        print("=" * 78)
        print(e.get("raw", "").strip())
        print()


# ---------------------------------------------------------------------- main

def main():
    ap = argparse.ArgumentParser(
        description="Compact index of logs/fix-history/ for the RL domain agents (read-only).",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="Examples:\n"
               "  python3 fix_digest.py --days 7\n"
               "  python3 fix_digest.py --days 30 --recurring\n"
               "  python3 fix_digest.py --days 14 --domain ops\n"
               "  python3 fix_digest.py --full BRIGHTDATA-TOKEN-EXPIRED\n",
    )
    ap.add_argument("--since", metavar="YYYY-MM-DD", help="start date (AEST), inclusive")
    ap.add_argument("--days", type=int, default=7, help="window size in days (default 7)")
    ap.add_argument("--domain", help="filter to a domain's fix_keywords from domains.yaml")
    ap.add_argument("--full", metavar="ID", help="print the complete text of every entry with this problem ID")
    ap.add_argument("--recurring", action="store_true", help="problem IDs seen on 2+ distinct days, most frequent first")
    ap.add_argument("--json", action="store_true", help="machine-readable output (all modes)")
    ap.add_argument("--history-dir", default=DEFAULT_HISTORY_DIR,
                    help="fix-history directory (default: logs/fix-history)")
    args = ap.parse_args()

    end_date = date.today()
    if args.since:
        try:
            start_date = datetime.strptime(args.since.strip(), "%Y-%m-%d").date()
        except ValueError:
            ap.error("--since must be YYYY-MM-DD")
        if args.full and start_date > end_date:
            start_date, end_date = end_date, start_date
    else:
        if args.days < 1:
            ap.error("--days must be >= 1")
        start_date = end_date - timedelta(days=args.days - 1)

    # --full defaults to a wide window: an ID may last have been seen months ago
    if args.full and not args.since and args.days == 7:
        start_date = end_date - timedelta(days=365)

    entries, stats = load_entries(args.history_dir, start_date, end_date)
    total_before_filter = len(entries)

    domain_note = ""
    if args.domain:
        keywords, note = load_domain_keywords(args.domain)
        if keywords is None:  # unknown domain
            print(f"fix_digest: {note}", file=sys.stderr)
            return 2
        domain_note = note
        if keywords:
            pats = _compile_keywords(keywords)
            kept = []
            for e in entries:
                hits = match_entry(e, pats)
                if hits:
                    e["matched_keywords"] = hits
                    kept.append(e)
            entries = kept

    if args.full:
        wanted = _clean_id(args.full.strip().strip("[]"))
        matches = [e for e in entries if e["id"] == wanted]
        matches.sort(key=lambda e: (e["date"], e.get("time") or ""), reverse=True)
        if args.json:
            print(json.dumps({
                "mode": "full", "id": wanted,
                "window": {"since": start_date.isoformat(), "until": end_date.isoformat()},
                "occurrences": matches,
                "stats": stats,
            }, indent=2, default=str))
        else:
            print_full(matches, wanted)
        return 0

    if args.recurring:
        rows = recurring_ids(entries)
        if args.json:
            print(json.dumps({
                "mode": "recurring",
                "window": {"since": start_date.isoformat(), "until": end_date.isoformat()},
                "domain": args.domain, "domain_note": domain_note,
                "recurring": rows, "entries_scanned": len(entries), "stats": stats,
            }, indent=2, default=str))
        else:
            print_recurring(rows, entries, stats, args)
        return 0

    if args.json:
        print(json.dumps({
            "mode": "index",
            "window": {"since": start_date.isoformat(), "until": end_date.isoformat()},
            "domain": args.domain, "domain_note": domain_note,
            "total_entries": len(entries),
            "total_before_domain_filter": total_before_filter,
            "recurring": recurring_ids(entries),
            "stats": stats,
            # index JSON stays COMPACT — one summary object per entry. Use --full ID
            # (or --json --full ID) to get an entry's body, fields and raw text.
            "entries": [
                {k: e.get(k) for k in ("date", "time", "id", "title", "file",
                                       "file_count", "recurrence", "matched_keywords")}
                for e in sorted(entries, key=lambda x: (x["date"], x.get("time") or ""), reverse=True)
            ],
        }, indent=2, default=str))
    else:
        print_index(entries, stats, args, domain_note, total_before_filter)
    return 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    except KeyboardInterrupt:
        sys.exit(130)
    except BrokenPipeError:
        # piping into `head` is the normal way to read this — exit quietly
        try:
            os.dup2(os.open(os.devnull, os.O_WRONLY), sys.stdout.fileno())
        except OSError:
            pass
        sys.exit(0)
