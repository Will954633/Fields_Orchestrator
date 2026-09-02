#!/usr/bin/env python3
"""
Stage 4 — Deep Research per topic (web + internal join).

For each topic on the slate, one headless `claude -p` deep pass (Max, web tools, read-only)
that REFRESHES the evergreen dossier. Evolves run_research_cycle.refresh_topic by injecting the
Stage-0 internal pack (our numbers, supplied with reliability flags) so the dossier grounds its
Gold-Coast claims in our data rather than the web. The parent validates and writes every file.

Output artifacts:
  * topics/<slug>.md            (evergreen dossier, refreshed in place; prior snapshotted)
  * briefs/current/<cycle>_<slug>.md   (dated cover brief)
  * DB: system_monitor.market_research_briefs (indexed)
Zero-output assertion (Rule 7b): a topic returning empty/invalid text is a per-topic failure
recorded with its error text; if ALL topics fail, the orchestrator RAISES. A failed topic never
advances — it re-runs next cycle from the un-refreshed dossier.
"""
from __future__ import annotations

import argparse
import json
import os
import re
import sys
from datetime import datetime, timezone

import mce_common as mc

STRUCTURE = """\
OUTPUT CONTRACT: return ONLY the full refreshed dossier as GitHub-flavoured Markdown, same
structure as the current version (title; a '> Bottom line.' blockquote; numbered sections that
RANK the underlying drivers behind the headline; a 'Premise test' note stating whether the
headline's implied cause holds; an 'Unverified / limitations' section; a 'For our audience'
section connecting it to southern Gold Coast owners/buyers; and a dated 'Changelog'). Update the
'as at' date to today and add a changelog line describing what changed. No preamble.
"""


def _prompt(topic: dict, cycle: str, current: str, pack_md: str) -> str:
    head = (f"{mc.HONESTY_RULES}\n\n"
            f"{mc.OUTPUT_DISCIPLINE}\n\n"
            f"Produce the updated text of ONE evergreen market-research dossier.\n\n"
            f"TOPIC: {topic['title']}\n"
            f"FOCUS THIS CYCLE: {topic['focus']}\n"
            f"TODAY: {cycle}\n\n"
            f"## Our own Gold Coast numbers are SUPPLIED — use verbatim, never look them up\n"
            f"{pack_md}\n\n"
            f"{STRUCTURE}\n")
    if current:
        return head + ("\nHere is the CURRENT version of the dossier for reference. Produce the "
                       "FULL updated dossier text (same structure, figures revised, 'as at' "
                       "date and changelog updated). Output the whole document, not a diff:\n\n"
                       f"--- CURRENT DOSSIER ---\n{current}\n")
    return head + ("\nNo dossier exists yet — research it from scratch and output the first "
                   "one in the structure described above.\n")


def _brief_from_dossier(md: str, slug: str, title: str, cycle: str) -> str:
    bl = re.findall(r"^>\s?(.*)$", md, re.M)
    bottom = " ".join(x.strip() for x in bl).strip() or "(see dossier)"
    as_at = (re.search(r"as at (\d{4}-\d{2}-\d{2})", md) or [None, cycle])[1]
    return (f"# Brief — {title}\n\n"
            f"**Cycle:** {cycle} · **As at:** {as_at} · "
            f"**Dossier:** [{slug}](../../topics/{slug}.md)\n\n{bottom}\n\n"
            f"Full sources, FACT/COMMENTARY tags and limitations are in the dossier.\n")


def _index(topic, cycle, as_at, md, source_file, kind="dossier"):
    try:
        bl = re.findall(r"^>\s?(.*)$", md, re.M)
        summary = " ".join(x.strip() for x in bl)[:2000]
        mc.get_sm()["market_research_briefs"].update_one(
            {"slug": topic["slug"], "cycle": cycle},
            {"$set": {"slug": topic["slug"], "title": topic["title"], "cycle": cycle,
                      "as_at": as_at, "summary": summary, "source_file": source_file,
                      "kind": kind, "chars": len(md),
                      "indexed_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
                      "model": mc.MODEL_DEEP}}, upsert=True)
        return True
    except Exception as e:
        print(f"    ! index failed for {topic['slug']}: {type(e).__name__}: {e}", file=sys.stderr)
        return False


def refresh_topic(topic: dict, cycle: str, pack_md: str, *, model=None, timeout=1800) -> dict:
    slug = topic["slug"]
    dossier_path = os.path.join(mc.TOPICS_DIR, f"{slug}.md")
    current = ""
    if os.path.exists(dossier_path):
        with open(dossier_path, encoding="utf-8") as fh:
            current = fh.read()

    res = mc.run_claude(_prompt(topic, cycle, current, pack_md),
                        model=model or mc.MODEL_DEEP, timeout=timeout, max_turns=50)
    md = mc.extract_markdown(res["text"])
    if len(md) < 800 or "> " not in md or "##" not in md:
        # capture the raw response so the failure is diagnosable, not just counted (Rule 7b)
        dbg = os.path.join(mc.cycle_data_dir(cycle), f"_stage4_{slug}_raw.txt")
        with open(dbg, "w", encoding="utf-8") as fh:
            fh.write(f"turns={res.get('turns')} cost={res.get('cost')}\n\n{res['text']}")
        raise RuntimeError(f"{slug}: implausible dossier ({len(md)} chars, "
                           f"{res.get('turns')} turns) — raw saved to {dbg}")

    if current:                                             # snapshot prior
        arch = os.path.join(mc.BRIEFS_ARCH, cycle)
        os.makedirs(arch, exist_ok=True)
        with open(os.path.join(arch, f"{slug}.md"), "w", encoding="utf-8") as fh:
            fh.write(current)
    os.makedirs(mc.TOPICS_DIR, exist_ok=True)
    with open(dossier_path, "w", encoding="utf-8") as fh:
        fh.write(md if md.endswith("\n") else md + "\n")

    os.makedirs(mc.BRIEFS_CUR, exist_ok=True)
    with open(os.path.join(mc.BRIEFS_CUR, f"{cycle}_{slug}.md"), "w", encoding="utf-8") as fh:
        fh.write(_brief_from_dossier(md, slug, topic["title"], cycle))

    as_at = (re.search(r"as at (\d{4}-\d{2}-\d{2})", md) or [None, cycle])[1]
    _index(topic, cycle, as_at, md, f"topics/{slug}.md")
    qa = mc.qa_scan(md)
    print(f"    ✓ Stage 4 [{slug}]: {len(md)} chars (${res.get('cost')}), QA={len(qa)}",
          file=sys.stderr)
    return {"slug": slug, "chars": len(md), "as_at": as_at, "cost": res.get("cost"),
            "qa": qa, "was_new": not current}


def run(cycle: str, *, only: list[str] | None = None, limit: int | None = None,
        model=None, timeout=1800) -> dict:
    slate_doc = mc.load_artifact(cycle, "topic_slate.json")
    pack = mc.load_artifact(cycle, "internal_pack.json")
    if not slate_doc:
        raise RuntimeError("Stage 4: topic_slate.json missing — run Stage 2 first")
    from mce_stage0_data import render_pack_md
    pack_md = render_pack_md(pack, include_demand=False) if pack else "(no internal pack)"

    topics = slate_doc["slate"]
    if only:
        topics = [t for t in topics if t["slug"] in only]
    if limit:
        topics = topics[:limit]

    refreshed, failures = [], []
    for t in topics:
        try:
            refreshed.append(refresh_topic(t, cycle, pack_md, model=model, timeout=timeout))
        except Exception as e:
            failures.append(f"{t['slug']}: {type(e).__name__}: {e}")
            print(f"    ✗ Stage 4 [{t['slug']}]: {e}", file=sys.stderr)

    out = {"cycle": cycle, "n_topics": len(topics), "refreshed": len(refreshed),
           "failures": failures, "results": refreshed}
    mc.save_artifact(cycle, "stage4_results.json", out)
    if topics and not refreshed:
        raise RuntimeError(f"Stage 4 refreshed 0/{len(topics)} topics; failures={failures}")
    print(f"    ✓ Stage 4: refreshed {len(refreshed)}/{len(topics)} topics", file=sys.stderr)
    return out


def main():
    ap = argparse.ArgumentParser(description="MCE Stage 4 — deep research per topic")
    ap.add_argument("--cycle", default=mc.cycle_id())
    ap.add_argument("--only", action="append", help="only these slugs; repeatable")
    ap.add_argument("--limit", type=int, help="cap number of topics (test mode)")
    ap.add_argument("--model", default=None)
    a = ap.parse_args()
    out = run(a.cycle, only=a.only, limit=a.limit, model=a.model)
    print(json.dumps({"refreshed": out["refreshed"], "failures": out["failures"]}, indent=2))
    return 0


if __name__ == "__main__":
    sys.exit(main())
