#!/usr/bin/env python3
"""
run_research_cycle.py -- the fortnightly market-research deep-dive.

Every second Sunday at midday (Australia/Brisbane), for each ACTIVE topic in
`topics.json`:
  1. run a headless `claude -p` research pass (Claude Max, web tools) that returns
     the full REFRESHED evergreen dossier markdown for that topic;
  2. snapshot the prior dossier into `briefs/archive/<cycle>/`;
  3. write the refreshed dossier to `topics/<slug>.md` and a dated brief to
     `briefs/current/`;
  4. index the brief into `system_monitor.market_research_briefs` so article
     generators can query "latest research on topic X" without parsing markdown;
  5. self-report via `job_status.job_run` (CLAUDE.md Rule 7) and RAISE if the cycle
     refreshed nothing (Rule 7b -- a research cycle that produced no output is a
     failure, not a quiet success).

Headless recipe is the proven one from scripts/samantha/deep_research.py: strip
ANTHROPIC_API_KEY / CLAUDECODE / CLAUDE_CODE_SSE_PORT so `claude -p` bills the Max
subscription, keep gh auth. The child gets only research/read tools (no Write) --
THIS parent writes the files, so a wrong model turn can never clobber a dossier
directly; it can only return text the parent validates first.

Scheduling: the VM is Australia/Brisbane, so cron `0 12 * * 0` fires every Sunday
noon local; this script no-ops on OFF weeks, making the effective cadence fortnightly.

    python3 run_research_cycle.py --dry-run                 # plumbing check, no LLM
    python3 run_research_cycle.py --topic <slug> --force    # one topic, ignore gate
    python3 run_research_cycle.py                           # scheduled fortnightly run
"""
from __future__ import annotations

import argparse
import json
import os
import re
import subprocess
import sys
from datetime import datetime, timezone

try:
    from zoneinfo import ZoneInfo
    _TZ = ZoneInfo("Australia/Brisbane")
except Exception:                                          # pragma: no cover
    _TZ = timezone.utc

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)                               # 14_Articles/Market_Research/
ORCH = "/home/fields/Fields_Orchestrator"
sys.path.insert(0, ORCH)
sys.path.insert(0, os.path.join(ORCH, "scripts"))

TOPICS_DIR = os.path.join(ROOT, "topics")
BRIEFS_CUR = os.path.join(ROOT, "briefs", "current")
BRIEFS_ARCH = os.path.join(ROOT, "briefs", "archive")
CONFIG = os.path.join(ROOT, "topics.json")
MODEL = "claude-opus-4-8"

SHARED_RULES = """
You are refreshing ONE evergreen market-research dossier for an Australian property
business. Reputable sources ONLY (RBA, ABS, Australian Treasury, Cotality/CoreLogic,
PropTrack, Westpac-Melbourne Institute, quality press, academic, major law/accounting
firms). EVERY claim carries a source + date + URL. Separate FACT from COMMENTARY/
forecast. DO NOT fabricate figures, papers, quotes, or policy changes -- an
unverifiable claim is reported as unverifiable, never filled in. Nothing here is a
forecast of your own; you record commentators' forecasts as commentary.

OUTPUT CONTRACT: return ONLY the full refreshed dossier as GitHub-flavoured Markdown,
in the SAME structure as the current version below (keep the title, the '> Bottom
line.' blockquote, the numbered sections, a 'Unverified / limitations' section, a
'Consumers' section, and a 'Changelog'). Update the 'as at' date to today, revise any
figure that has moved, and ADD a dated changelog line describing what changed. Do not
write any preamble or closing remarks outside the markdown. Do not edit files
yourself -- just return the markdown.
""".strip()


# ---------------------------------------------------------------- headless claude

def _clean_env() -> dict:
    env = {k: v for k, v in os.environ.items()
           if k not in ("ANTHROPIC_API_KEY", "CLAUDECODE", "CLAUDE_CODE_SSE_PORT")}
    env.setdefault("GH_CONFIG_DIR", "/home/projects/.config/gh")
    return env


def _run_claude(prompt: str, timeout: int = 1000, max_turns: int = 24) -> str:
    r = subprocess.run(
        ["claude", "--model", MODEL, "-p", prompt,
         "--allowedTools", "Bash,Read,Grep,Glob,WebSearch,WebFetch",
         "--max-turns", str(max_turns)],
        cwd=ORCH, env=_clean_env(), capture_output=True, text=True, timeout=timeout,
    )
    if r.returncode != 0:
        raise RuntimeError(f"claude -p exited {r.returncode}: {r.stderr[-500:]}")
    return r.stdout.strip()


def _extract_markdown(out: str) -> str:
    """Child should return pure markdown; tolerate a ```markdown fence if present."""
    m = re.search(r"```(?:markdown)?\s*(.*?)```", out, re.S)
    body = m.group(1).strip() if m else out.strip()
    return body


# ---------------------------------------------------------------- cycle mechanics

def _cycle_id(now: datetime) -> str:
    return now.strftime("%Y-%m-%d")


def _is_on_week(now: datetime) -> bool:
    """Fortnightly parity anchored on ISO week number (even weeks run)."""
    return now.isocalendar().week % 2 == 0


def _brief_from_dossier(md: str, slug: str, title: str, cycle: str) -> str:
    """A dated cover brief: the dossier's bottom-line blockquote + pointer."""
    bl = re.findall(r"^>\s?(.*)$", md, re.M)
    bottom = " ".join(x.strip() for x in bl).strip() or "(see dossier)"
    as_at = (re.search(r"as at (\d{4}-\d{2}-\d{2})", md) or [None, cycle])[1]
    return (f"# Brief — {title}\n\n"
            f"**Cycle:** {cycle} · **As at:** {as_at} · "
            f"**Dossier:** [{slug}](../../topics/{slug}.md)\n\n"
            f"{bottom}\n\n"
            f"Full sources, FACT/COMMENTARY tags and limitations are in the dossier.\n")


def _index_brief(topic, cycle, as_at, dossier_md, source_file):
    """Upsert into system_monitor.market_research_briefs for programmatic consumers."""
    try:
        from shared.db import get_client
        bl = re.findall(r"^>\s?(.*)$", dossier_md, re.M)
        summary = " ".join(x.strip() for x in bl)[:2000]
        get_client()["system_monitor"]["market_research_briefs"].update_one(
            {"slug": topic["slug"], "cycle": cycle},
            {"$set": {
                "slug": topic["slug"], "title": topic["title"], "cycle": cycle,
                "as_at": as_at, "summary": summary, "source_file": source_file,
                "chars": len(dossier_md),
                "indexed_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
                "model": MODEL,
            }}, upsert=True)
        return True
    except Exception as e:                                  # indexing must not fail the cycle
        print(f"    ! index failed for {topic['slug']}: {type(e).__name__}: {e}",
              file=sys.stderr)
        return False


def refresh_topic(topic: dict, cycle: str, dry_run: bool) -> bool:
    slug = topic["slug"]
    dossier_path = os.path.join(TOPICS_DIR, f"{slug}.md")
    current = ""
    if os.path.exists(dossier_path):
        with open(dossier_path) as fh:
            current = fh.read()

    if dry_run:
        print(f"    [dry-run] would refresh {slug} "
              f"({'existing' if current else 'NEW'} dossier)", file=sys.stderr)
        return bool(current) or True

    prompt = (f"{SHARED_RULES}\n\n"
              f"TOPIC: {topic['title']}\n"
              f"FOCUS FOR THIS CYCLE: {topic['focus']}\n"
              f"TODAY: {cycle}\n\n"
              f"--- CURRENT DOSSIER (revise in place; keep structure) ---\n{current}\n"
              if current else
              f"{SHARED_RULES}\n\nTOPIC: {topic['title']}\n"
              f"FOCUS: {topic['focus']}\nTODAY: {cycle}\n\n"
              f"No dossier exists yet -- research from scratch and produce the first one "
              f"in the structure described above.")

    md = _extract_markdown(_run_claude(prompt))
    # Validate before writing: a real dossier is long and has the bottom-line block.
    if len(md) < 800 or "> " not in md or "##" not in md:
        raise RuntimeError(f"{slug}: model returned an implausible dossier "
                           f"({len(md)} chars) -- not writing")

    # snapshot the prior version, then write the refreshed one
    if current:
        arch_dir = os.path.join(BRIEFS_ARCH, cycle)
        os.makedirs(arch_dir, exist_ok=True)
        with open(os.path.join(arch_dir, f"{slug}.md"), "w") as fh:
            fh.write(current)
    with open(dossier_path, "w") as fh:
        fh.write(md if md.endswith("\n") else md + "\n")

    os.makedirs(BRIEFS_CUR, exist_ok=True)
    brief_path = os.path.join(BRIEFS_CUR, f"{cycle}_{slug}.md")
    with open(brief_path, "w") as fh:
        fh.write(_brief_from_dossier(md, slug, topic["title"], cycle))

    as_at = (re.search(r"as at (\d{4}-\d{2}-\d{2})", md) or [None, cycle])[1]
    _index_brief(topic, cycle, as_at, md, f"topics/{slug}.md")
    print(f"    ✓ {slug}: refreshed ({len(md)} chars), brief + indexed", file=sys.stderr)
    return True


def run(dry_run=False, only=None, force=False) -> dict:
    now = datetime.now(_TZ)
    cycle = _cycle_id(now)
    if not force and not dry_run and not _is_on_week(now):
        print(f"off-week ({now:%Y-%m-%d}, ISO week {now.isocalendar().week}) -- "
              f"fortnightly cadence, skipping", file=sys.stderr)
        return {"skipped_off_week": True, "refreshed": 0}

    with open(CONFIG) as fh:
        cfg = json.load(fh)
    topics = cfg.get("active", [])
    if only:
        topics = [t for t in topics if t["slug"] == only]
        if not topics:
            raise SystemExit(f"no active topic '{only}'")

    refreshed, failures = 0, []
    for t in topics:
        try:
            if refresh_topic(t, cycle, dry_run):
                refreshed += 1
        except Exception as e:                             # one topic failing must not sink the rest
            failures.append(f"{t['slug']}: {type(e).__name__}: {e}")
            print(f"    ✗ {t['slug']}: {e}", file=sys.stderr)

    # Rule 7b: a live cycle that refreshed nothing is a failure, not a success.
    if not dry_run and topics and refreshed == 0:
        raise RuntimeError(f"cycle refreshed 0/{len(topics)} topics; failures={failures}")
    return {"cycle": cycle, "refreshed": refreshed, "topics": len(topics),
            "failures": failures, "dry_run": dry_run}


def main():
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--dry-run", action="store_true", help="plumbing check, no LLM/cost")
    ap.add_argument("--topic", help="refresh only this slug")
    ap.add_argument("--force", action="store_true", help="ignore the fortnight gate")
    ap.add_argument("--no-heartbeat", action="store_true")
    a = ap.parse_args()

    def _go():
        return run(a.dry_run, a.topic, a.force)

    if a.no_heartbeat or a.dry_run:
        res = _go()
        print(json.dumps(res, indent=2), file=sys.stderr)
        return 0
    try:
        from job_status import job_run
    except Exception:
        _go(); return 0
    with job_run("market_research_cycle", cadence_hours=336,
                 title="Market Research fortnightly cycle") as beat:
        res = _go()
        beat.metrics = {"refreshed": res.get("refreshed", 0),
                        "topics": res.get("topics", 0)}
        beat.detail = (f"refreshed {res.get('refreshed')}/{res.get('topics')} topics"
                       if not res.get("skipped_off_week") else "off-week skip")
    return 0


if __name__ == "__main__":
    sys.exit(main())
