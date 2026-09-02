#!/usr/bin/env python3
"""
Stage 8 — QA gate + digest.

Runs the automated editorial/honesty gate over everything this cycle produced, writes a QA
report, and (unless suppressed) sends Will a Telegram digest: the ranked slate, what refreshed,
the three suburb one-pagers, and any QA failures. The self-report heartbeat itself is emitted by
the orchestrator (run_context_cycle.py) so a crash mid-Stage-8 still records an error.

QA checks per output file:
  * forbidden words (Rule 5)
  * single-valuation-in-heading heuristic
  * §9 'did NOT conclude' present on synthesized briefs (psychology, suburb context)
  * reliability tripwire: a QoQ move narrated off a quarter the pack flags reliable=false

A QA failure does NOT delete content — it blocks the optional draft-content stage and is
surfaced loudly in the digest for human review.
"""
from __future__ import annotations

import argparse
import json
import os
import re
import sys

import mce_common as mc


def _files_for_cycle(cycle: str) -> list[tuple[str, str, bool]]:
    """(label, path, needs_section9) for every file this cycle produced."""
    out = []
    # dossiers refreshed this cycle
    s4 = mc.load_artifact(cycle, "stage4_results.json") or {}
    for r in s4.get("results", []):
        out.append((f"dossier:{r['slug']}", os.path.join(mc.TOPICS_DIR, f"{r['slug']}.md"), False))
    # psychology
    pmeta = mc.load_artifact(cycle, "psychology_brief.json")
    if pmeta:
        out.append(("psychology", os.path.join(mc.ROOT, pmeta["path"]), True))
    # suburb contexts
    s5 = mc.load_artifact(cycle, "stage5_results.json") or {}
    for r in s5.get("results", []):
        out.append((f"suburb:{r['suburb']}", os.path.join(mc.ROOT, r["path"]), True))
    return out


def _unreliable_quarters(pack: dict) -> list[str]:
    md = (pack or {}).get("fields_price_pack_md", "")
    qs = re.findall(r"DO NOT narrate a QoQ move from:\s*(.+)", md)
    out = []
    for line in qs:
        out += [q.strip() for q in line.split(",")]
    return list({q for q in out if q})


def qa_report(cycle: str) -> dict:
    pack = mc.load_artifact(cycle, "internal_pack.json")
    unreliable = _unreliable_quarters(pack)
    findings = []
    for label, path, needs9 in _files_for_cycle(cycle):
        if not os.path.exists(path):
            findings.append({"file": label, "issue": "missing file", "severity": "error"})
            continue
        md = open(path, encoding="utf-8").read()
        for v in mc.qa_scan(md):
            findings.append({"file": label, "issue": v, "severity": "warn"})
        if needs9 and not mc.has_section9(md):
            findings.append({"file": label, "issue": "missing §9 did-NOT-conclude",
                             "severity": "error"})
        # reliability tripwire — a rise/fall narrated near an unreliable quarter mention.
        # Suppress when the surrounding text is a GUARD (warning against narrating the move);
        # those sentences enforce the rule, they don't break it.
        guard = re.compile(
            r"must not|do not|don't|did not|didn't|cannot|can't|never|unreliable|reliable\s*=?\s*false"
            r"|noise|noisy|not\s+(?:a\s+)?(?:real|demonstrat)|too\s+(?:noisy|wide|thin)"
            r"|not\s+report|not\s+narrat|no\b.*survives", re.I)
        # Only a PRICE move is governed by the reliability flag (volume drops are fine to
        # narrate), so require a $ figure near the direction word, and no guard phrase.
        for q in unreliable:
            for m in re.finditer(re.escape(q), md):
                window = md[max(0, m.start() - 200):m.end() + 200]
                has_dir = re.search(r"\b(rose|fell|jump\w*|surged|climbed|dropped?|declined?|"
                                    r"rise|fall|gain\w*|lost)\b", window, re.I)
                has_price = re.search(r"\$[\d,]{5,}", window)
                if has_dir and has_price and not guard.search(window):
                    findings.append({"file": label,
                                     "issue": f"possible PRICE QoQ move narrated off unreliable {q}",
                                     "severity": "warn"})
                    break
    report = {"cycle": cycle, "n_findings": len(findings),
              "n_errors": sum(1 for f in findings if f["severity"] == "error"),
              "n_warns": sum(1 for f in findings if f["severity"] == "warn"),
              "findings": findings, "clean": not findings}
    mc.save_artifact(cycle, "qa_report.json", report)
    print(f"    ✓ Stage 8 QA: {report['n_errors']} errors, {report['n_warns']} warns",
          file=sys.stderr)
    return report


def build_digest(cycle: str, qa: dict) -> str:
    slate = mc.load_artifact(cycle, "topic_slate.json") or {}
    s4 = mc.load_artifact(cycle, "stage4_results.json") or {}
    s5 = mc.load_artifact(cycle, "stage5_results.json") or {}
    pack = mc.load_artifact(cycle, "audience_context_pack.json") or {}

    lines = [f"📊 *Market Context Engine* — cycle {cycle}", ""]
    promoted = [s for s in slate.get("slate", []) if s.get("kind") == "promoted"]
    lines.append(f"*Slate:* {slate.get('n_standing', 0)} standing + {len(promoted)} promoted")
    if promoted:
        lines.append("Promoted topics: " + ", ".join(f"{s['slug']} ({s.get('score')})"
                                                      for s in promoted))
    lines.append(f"*Refreshed:* {s4.get('refreshed', 0)}/{s4.get('n_topics', 0)} dossiers")
    if s4.get("failures"):
        lines.append("⚠️ dossier failures: " + "; ".join(s4["failures"])[:300])
    lines.append(f"*Suburb context:* {s5.get('done', 0)}/{len(mc.TARGET_SUBURBS)}")
    # one-line-per-suburb
    for sub, sd in (pack.get("suburbs") or {}).items():
        ctx = re.sub(r"\s+", " ", sd.get("context", ""))[:180]
        lines.append(f"  • *{sd.get('name')}*: {ctx}…")
    lines += ["", ("✅ QA clean" if qa["clean"]
                   else f"⚠️ QA: {qa['n_errors']} errors, {qa['n_warns']} warns "
                        f"(see qa_report.json)")]
    if qa["n_errors"]:
        for f in [x for x in qa["findings"] if x["severity"] == "error"][:5]:
            lines.append(f"  ✗ {f['file']}: {f['issue']}")
    lines += ["", "Review: `14_Articles/Market_Research/` (briefs/current, suburb_context)",
              "Nothing published — research + human-reviewed publish."]
    return "\n".join(lines)


def send_digest(cycle: str, qa: dict) -> bool:
    text = build_digest(cycle, qa)
    try:
        sys.path.insert(0, os.path.join(mc.ORCH, "scripts"))
        from telegram_notify import send_message
        send_message(text)
        print("    ✓ Stage 8: digest sent to Telegram", file=sys.stderr)
        return True
    except Exception as e:
        print(f"    ! Stage 8: digest send failed ({type(e).__name__}: {e})", file=sys.stderr)
        # persist it so it is not lost
        with open(os.path.join(mc.cycle_data_dir(cycle), "digest.txt"), "w") as fh:
            fh.write(text)
        return False


def run(cycle: str, *, notify: bool = True) -> dict:
    qa = qa_report(cycle)
    sent = send_digest(cycle, qa) if notify else False
    return {"qa": qa, "digest_sent": sent}


def main():
    ap = argparse.ArgumentParser(description="MCE Stage 8 — QA + digest")
    ap.add_argument("--cycle", default=mc.cycle_id())
    ap.add_argument("--no-notify", action="store_true")
    ap.add_argument("--print-digest", action="store_true")
    a = ap.parse_args()
    if a.print_digest:
        qa = qa_report(a.cycle)
        print(build_digest(a.cycle, qa))
        return 0
    out = run(a.cycle, notify=not a.no_notify)
    print(json.dumps(out["qa"], indent=2))
    return 0


if __name__ == "__main__":
    sys.exit(main())
