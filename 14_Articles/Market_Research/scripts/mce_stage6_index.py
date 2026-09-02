#!/usr/bin/env python3
"""
Stage 6 — Synthesis & Index (deterministic).

Indexes this cycle's psychology brief and suburb-context files into
system_monitor.market_research_briefs (Stage 4 already indexed the dossiers), regenerates
INDEX.md, and builds audience_context_pack.json — the flattened, query-ready bundle a
downstream generator reads to get "everything current for suburb X" in one call.

Output artifacts:
  * data/<cycle>/audience_context_pack.json
  * INDEX.md
  * DB: market_research_briefs (psychology + suburb_context rows)
Zero-output assertion (Rule 7b): if there are brief files on disk for this cycle but 0 get
indexed, RAISE (indexer broken).
"""
from __future__ import annotations

import argparse
import json
import os
import re
import sys
from datetime import datetime, timezone

import mce_common as mc


def _first_para(md: str, limit: int = 600) -> str:
    body = re.sub(r"^#.*$", "", md, flags=re.M)          # drop headings
    for para in re.split(r"\n\s*\n", body):
        p = para.strip()
        if len(p) > 60 and not p.startswith(("*", ">", "-", "|")):
            return p[:limit]
    return body.strip()[:limit]


def _bottom_line(md: str, limit: int = 800) -> str:
    bl = re.findall(r"^>\s?(.*)$", md, re.M)
    return (" ".join(x.strip() for x in bl)[:limit]) or _first_para(md, limit)


def _index_extra(cycle: str) -> int:
    """Index psychology + suburb-context (dossiers are indexed in Stage 4)."""
    sm = mc.get_sm()
    n = 0
    # psychology
    pmeta = mc.load_artifact(cycle, "psychology_brief.json")
    if pmeta:
        path = os.path.join(mc.ROOT, pmeta["path"])
        if os.path.exists(path):
            md = open(path, encoding="utf-8").read()
            sm["market_research_briefs"].update_one(
                {"slug": "psychology", "cycle": cycle},
                {"$set": {"slug": "psychology", "title": "Audience psychology (buyers+sellers)",
                          "cycle": cycle, "kind": "psychology", "as_at": cycle,
                          "summary": _first_para(md), "source_file": pmeta["path"],
                          "chars": len(md),
                          "indexed_at": datetime.now(timezone.utc).isoformat(timespec="seconds")}},
                upsert=True)
            n += 1
    # suburb contexts
    s5 = mc.load_artifact(cycle, "stage5_results.json") or {}
    for r in s5.get("results", []):
        path = os.path.join(mc.ROOT, r["path"])
        if not os.path.exists(path):
            continue
        md = open(path, encoding="utf-8").read()
        sm["market_research_briefs"].update_one(
            {"slug": f"suburb-{r['suburb']}", "cycle": cycle},
            {"$set": {"slug": f"suburb-{r['suburb']}",
                      "title": f"{mc.DISPLAY_NAMES.get(r['suburb'], r['suburb'])} context",
                      "cycle": cycle, "kind": "suburb_context", "suburb": r["suburb"],
                      "as_at": cycle, "summary": _first_para(md), "source_file": r["path"],
                      "chars": len(md),
                      "indexed_at": datetime.now(timezone.utc).isoformat(timespec="seconds")}},
            upsert=True)
        n += 1
    return n


def build_pack(cycle: str) -> dict:
    slate = mc.load_artifact(cycle, "topic_slate.json") or {}
    s4 = mc.load_artifact(cycle, "stage4_results.json") or {}
    s5 = mc.load_artifact(cycle, "stage5_results.json") or {}
    pmeta = mc.load_artifact(cycle, "psychology_brief.json") or {}

    # topics — pull bottom lines from the refreshed dossiers
    topics = []
    for r in s4.get("results", []):
        p = os.path.join(mc.TOPICS_DIR, f"{r['slug']}.md")
        if os.path.exists(p):
            md = open(p, encoding="utf-8").read()
            title = (re.search(r"^#\s*(.+)$", md, re.M) or [None, r["slug"]])[1]
            topics.append({"slug": r["slug"], "title": title.strip(), "as_at": r.get("as_at"),
                           "bottom_line": _bottom_line(md), "source_file": f"topics/{r['slug']}.md"})

    # suburbs — first-para context each
    suburbs = {}
    for r in s5.get("results", []):
        path = os.path.join(mc.ROOT, r["path"])
        if os.path.exists(path):
            md = open(path, encoding="utf-8").read()
            suburbs[r["suburb"]] = {
                "name": mc.DISPLAY_NAMES.get(r["suburb"], r["suburb"]),
                "context": _first_para(md, 900), "source_file": r["path"]}

    psych = {}
    if pmeta and os.path.exists(os.path.join(mc.ROOT, pmeta.get("path", ""))):
        md = open(os.path.join(mc.ROOT, pmeta["path"]), encoding="utf-8").read()
        psych = {"summary": _first_para(md, 900), "source_file": pmeta["path"],
                 "words": pmeta.get("words")}

    pack = {
        "cycle": cycle,
        "generated_at": mc.now_tz().isoformat(timespec="seconds"),
        "slate": [{"slug": s["slug"], "kind": s["kind"], "score": s.get("score")}
                  for s in slate.get("slate", [])],
        "topics": topics,
        "psychology": psych,
        "suburbs": suburbs,
        "note": ("Source of truth for downstream generators. Every figure here traces to a "
                 "cited dossier or SUPPLIED Fields data. Bound by no-advice/no-prediction/"
                 "no-single-valuation-headline editorial rules."),
    }
    mc.save_artifact(cycle, "audience_context_pack.json", pack)
    # also index the pack itself
    try:
        mc.get_sm()["audience_context_pack"].update_one(
            {"cycle": cycle}, {"$set": pack}, upsert=True)
    except Exception as e:
        print(f"    ! Stage 6: pack DB write failed: {e}", file=sys.stderr)
    return pack


def regen_index(cycle: str, pack: dict):
    lines = ["# Market Research — current index", "",
             f"*Regenerated by the Market Context Engine, cycle {cycle}.*", "",
             "## Topic dossiers (evergreen)"]
    for f in sorted(os.listdir(mc.TOPICS_DIR)):
        if f.endswith(".md"):
            md = open(os.path.join(mc.TOPICS_DIR, f), encoding="utf-8").read()
            as_at = (re.search(r"as at (\d{4}-\d{2}-\d{2})", md) or [None, "?"])[1]
            title = (re.search(r"^#\s*(.+)$", md, re.M) or [None, f[:-3]])[1]
            lines.append(f"- [{title.strip()}](topics/{f}) — as at {as_at}")
    lines += ["", "## This cycle's suburb context"]
    for s, sd in pack.get("suburbs", {}).items():
        lines.append(f"- [{sd['name']}]({sd['source_file']})")
    if pack.get("psychology"):
        lines += ["", "## Audience psychology",
                  f"- [Buyers + sellers]({pack['psychology'].get('source_file')})"]
    lines += ["", "## Programmatic access",
              "- DB collection `system_monitor.market_research_briefs` (per-topic findings)",
              "- `data/<cycle>/audience_context_pack.json` (flattened context bundle)", ""]
    with open(mc.INDEX_MD, "w", encoding="utf-8") as fh:
        fh.write("\n".join(lines))


def run(cycle: str) -> dict:
    n_extra = _index_extra(cycle)
    pack = build_pack(cycle)
    regen_index(cycle, pack)

    # Rule 7b: brief files exist but nothing indexed => indexer broken
    on_disk = (len(pack["topics"]) + len(pack["suburbs"]) + (1 if pack["psychology"] else 0))
    n_indexed = mc.get_sm()["market_research_briefs"].count_documents({"cycle": cycle})
    if on_disk > 0 and n_indexed == 0:
        raise RuntimeError(f"Stage 6: {on_disk} briefs on disk but 0 indexed — indexer broken")

    out = {"cycle": cycle, "topics": len(pack["topics"]), "suburbs": len(pack["suburbs"]),
           "psychology": bool(pack["psychology"]), "extra_indexed": n_extra,
           "total_indexed_this_cycle": n_indexed}
    print(f"    ✓ Stage 6: pack built ({out['topics']} topics, {out['suburbs']} suburbs), "
          f"{n_indexed} briefs indexed, INDEX.md regenerated", file=sys.stderr)
    return out


def main():
    ap = argparse.ArgumentParser(description="MCE Stage 6 — synthesis & index")
    ap.add_argument("--cycle", default=mc.cycle_id())
    a = ap.parse_args()
    print(json.dumps(run(a.cycle), indent=2))
    return 0


if __name__ == "__main__":
    sys.exit(main())
