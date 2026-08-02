#!/usr/bin/env python3
"""
refresh_homeowner_mindset.py — re-research the Gold Coast homeowner selling mindset.

WHY THIS EXISTS
The monthly Market Pulse prose is written for the psychological state of a homeowner in the
target market — what they're seeing, worrying about, and being influenced by. That state comes
from a researched brief under `15_Off-Market/Home_Owner_Perspective/`, which also feeds the market
update report. Conditions move (rate decisions, rental market, forecaster splits, news cycle), so
the brief has to be re-researched rather than written once and trusted forever.

THE LESSON THAT SHAPED THIS SCRIPT (2026-08-02)
The first brief (30 July 2026) was produced while `precomputed_indexed_prices` was being reverted
to raw values nightly. Its `[FIELDS]` layer therefore reported a 16% Burleigh Waters retreat off a
peak that does not exist in the corrected data — the real move is 4.9%, on a quarter flagged
`reliable: false`. The brief's headline psychological read for that suburb was an artefact of a
data bug, and it would have shaped 21 public summaries.

So this script does NOT ask the researcher to look up our own numbers. It hands over a data pack
built from the live database, with reliability flags, and forbids restating suburb figures from
any other source. External research (macro, behavioural, news, search) is genuinely researched;
our own ground truth is supplied, not recalled.

Billing: invokes the `claude` CLI directly in agentic mode so web search runs on the Claude Max
subscription rather than metered API credits — same reasoning as fetch_policy_research.py. Do not
route this through claude_max_client.py's MaxClient, which strips tools and falls back to the API.

Usage:
    python3 scripts/refresh_homeowner_mindset.py              # research + write a dated report
    python3 scripts/refresh_homeowner_mindset.py --dry-run    # print the prompt, research nothing
    python3 scripts/refresh_homeowner_mindset.py --status     # report age/staleness, exit
"""
from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
from datetime import datetime

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from homeowner_mindset import (  # noqa: E402
    REPORT_DIR, STALE_AFTER_DAYS, check_freshness, fields_data_pack, latest_report,
)
from job_status import job_run  # noqa: E402

CLI_TIMEOUT_S = int(os.environ.get("MINDSET_RESEARCH_CLI_TIMEOUT", "2400"))
CLI_BIN = os.environ.get("CLAUDE_BIN", "claude")

PROMPT_TEMPLATE = """\
Produce a comprehensive psychological and behavioural profile of the pre-listing HOMEOWNER \
considering selling on the southern Gold Coast (Robina, Varsity Lakes, Burleigh Waters, and \
nearby Burleigh Heads / Palm Beach / Mermaid Waters), as at {today}.

This is an INTERNAL strategy and messaging brief for Fields Real Estate — a data-led property \
intelligence business. It is NOT public content. Its purpose is to let us write monthly market \
commentary that speaks to what these owners are actually feeling, without ever resorting to \
advice, urgency or persuasion.

## Research it — do not rely on training data
Use web search for anything time-sensitive: the RBA cash rate and the next decision, economist \
expectations, bank and analyst forecasts (note where they DISAGREE — conflict drives seller \
paralysis), Gold Coast rental vacancy and rents, listing supply, migration, cost-of-selling \
questions, and what property media aimed at this audience is currently saying. Cite source URLs.

## Our own numbers are SUPPLIED — never look them up, never restate them from memory
{data_pack}

Any claim about our target suburbs must use those figures exactly as given. If a quarter is
marked `reliable=False`, its confidence interval is too wide to support a quarter-on-quarter
narrative — you must not describe a rise or fall from it. Sales volume is the more dependable
signal than any single quarterly median; weight it accordingly. If the external sources and our
data disagree, say so explicitly and treat OUR data as the ground truth for these suburbs.

## Tag every claim
- **[VERIFIED]** — you checked it against a primary or credible secondary source, and it survived \
an adversarial re-check. Cite the URL.
- **[FIELDS]** — taken from the supplied data pack above.
- **[INFERRED]** — a reasonable behavioural read, NOT independently confirmed. Be honest and \
generous with this tag; a brief that pretends inference is fact is worse than useless.

## Structure
1. Executive summary — the defining tension in this owner's head right now.
2. The market backdrop they are reacting to — split into the anxiety layer (macro) and the \
reassurance layer (local), with an emotional read of how each fact actually LANDS.
3. What they are worried about — ranked by emotional weight, with evidence.
4. What they are hopeful for — the motivations that actually get them to list.
5. What they need (the job-to-be-done).
6. What they are reading, listening to, and searching for.
7. Suburb-level nuance for the target markets, using the supplied data.
8. Messaging implications — what resonates, and what to avoid.
9. **What we deliberately did NOT conclude** — claims that sound right but failed verification. \
This section is mandatory and is the most valuable part of the document. Include anything you \
could not stand up, especially where it would have been convenient to believe it.

**Section 9 OUTRANKS section 8.** Before you finish, re-read your messaging section against your \
own "did not conclude" list and delete any suggested line that section 9 rules out. The 30 July \
2026 brief failed this twice: §8 offered "56 against 117" as a model sentence while §9.9 said that \
magnitude must not be published without a lag reconciliation, and §8 proposed "most homes here are \
sold by private treaty" while §9.8 recorded that no verified statistic for the auction/private-treaty \
split could be found. A messaging section that contradicts its own verification section forces the \
writer to re-litigate it every month. If a message only survives by ignoring section 9, it belongs \
in the "dropped" list, not the "resonates" list.
10. What Fields should validate next with first-party data we already own.
11. Sources.

## Editorial constraints that bind anything written FROM this brief
Public content must never give advice ("now is a good time to sell"), never predict prices, never \
put a single valuation figure in a headline (use ranges), and never use the words "stunning", \
"nestled", "boasting", "rare opportunity" or "robust market". Write the messaging section so it \
is usable within those limits — if a message only works by breaking them, say so and drop it.

Return the complete report as markdown. Aim for depth over brevity: this shapes a month of public \
commentary and is read by people who will act on it.
"""


def _child_env() -> dict:
    env = dict(os.environ)
    # Force Max billing — same reasoning as fetch_policy_research.py / claude_max_client.py.
    env.pop("ANTHROPIC_API_KEY", None)
    env.pop("ANTHROPIC_AUTH_TOKEN", None)
    env.pop("CLAUDECODE", None)
    env.setdefault("CI", "true")
    return env


def build_prompt() -> str:
    from src.mongo_client_factory import get_database
    return PROMPT_TEMPLATE.format(
        today=datetime.now().strftime("%d %B %Y"),
        data_pack=fields_data_pack(get_database("Gold_Coast")),
    )


def run_research(prompt: str) -> dict:
    cmd = [CLI_BIN, "-p", prompt, "--output-format", "json"]
    proc = subprocess.run(
        cmd, text=True, capture_output=True, timeout=CLI_TIMEOUT_S, env=_child_env(),
    )
    if proc.returncode != 0:
        raise RuntimeError(f"claude CLI exited {proc.returncode}: {(proc.stderr or '')[:500]}")
    try:
        data = json.loads(proc.stdout)
    except json.JSONDecodeError as e:
        raise RuntimeError(f"non-JSON CLI output: {e}: {proc.stdout[:300]}")
    if data.get("is_error") or data.get("subtype") != "success":
        raise RuntimeError(f"CLI error: {data.get('subtype')}: {str(data.get('result'))[:500]}")
    return data


HEADER = """\
# Inside the Mind of the Gold Coast Homeowner Considering a Sale

**A psychological & behavioural profile of pre-listing sellers**

*Prepared for Fields Real Estate · {date} · Southern Gold Coast focus \
(Robina, Varsity Lakes, Burleigh Waters, Burleigh Heads, Palm Beach, Mermaid Waters)*

*Generated by `scripts/refresh_homeowner_mindset.py`. Suburb figures were supplied from the live \
`Gold_Coast.precomputed_indexed_prices` (Domain ∪ onthehouse union basis) rather than researched, \
so they cannot drift from what the site shows. This is an INTERNAL strategy brief, not public \
content.*

---

"""


def write_report(text: str) -> str:
    os.makedirs(REPORT_DIR, exist_ok=True)
    stamp = datetime.now().strftime("%Y-%m-%d")
    path = os.path.join(REPORT_DIR, f"Gold-Coast-Homeowner-Selling-Mindset-{stamp}.md")
    body = text.lstrip()
    # The model usually opens with its own H1; drop it so the provenance header owns the top.
    if body.startswith("# "):
        body = body.split("\n", 1)[1].lstrip() if "\n" in body else ""
    with open(path, "w", encoding="utf-8") as fh:
        fh.write(HEADER.format(date=datetime.now().strftime("%-d %B %Y")) + body)
    return path


def main():
    ap = argparse.ArgumentParser(description="Re-research the Gold Coast homeowner selling mindset")
    ap.add_argument("--dry-run", action="store_true", help="print the prompt, research nothing")
    ap.add_argument("--status", action="store_true", help="report current brief age and exit")
    args = ap.parse_args()

    if args.status:
        rep, status = check_freshness()
        print(f"\nstatus: {status}")
        if rep:
            print(f"path:   {rep['path']}")
            print(f"date:   {rep['date']:%d %b %Y}  ({rep['age_days']} days old, "
                  f"stale after {STALE_AFTER_DAYS})")
        return 0

    if args.dry_run:
        print(build_prompt())
        return 0

    with job_run("homeowner_mindset_research", cadence_hours=STALE_AFTER_DAYS * 24,
                 title="Homeowner Mindset Brief — research refresh") as beat:
        prev = latest_report()
        if prev:
            print(f"Current brief: {os.path.basename(prev['path'])} ({prev['age_days']}d old)")
        print(f"Researching (claude CLI, web search, Max billing; timeout {CLI_TIMEOUT_S}s)...")

        result = run_research(build_prompt())
        text = result.get("result", "")
        if len(text) < 3000:
            raise RuntimeError(f"suspiciously short report ({len(text)} chars) — not writing it")

        path = write_report(text)
        words = len(text.split())
        cost = result.get("total_cost_usd")
        print(f"\n✅ Wrote {path}")
        print(f"   {words:,} words"
              + (f" · notional ${cost:.2f} (billed to Max, not API credits)" if cost else ""))
        print("\n   NEXT: read it before it shapes public prose — especially section 9,")
        print("   'What we deliberately did NOT conclude'.")

        beat.detail = f"{words} words -> {os.path.basename(path)}"
        beat.metrics = {"words": words, "chars": len(text)}
    return 0


if __name__ == "__main__":
    sys.exit(main())
