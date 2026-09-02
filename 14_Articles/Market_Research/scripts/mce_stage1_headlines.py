#!/usr/bin/env python3
"""
Stage 1 — Headline Scan (national -> Brisbane/QLD -> Gold Coast).

Three web-research passes, one per geographic tier, each returning a STRUCTURED list of the
property-market topics being discussed right now (last ~3 weeks). The agents report WHAT is
being discussed and how loudly — they do NOT assess whether it's true (that is Stage 4).
Every item carries an outlet, a URL and a date.

Output artifact: data/<cycle>/headlines_raw.json
Zero-output assertion (Rule 7b): if any tier returns zero items, RAISE — the web tools or a
source block is broken; three empty tiers is not a quiet news week.
"""
from __future__ import annotations

import argparse
import json
import sys

import mce_common as mc

TIERS = {
    "national": (
        "AUSTRALIAN NATIONAL residential property market — the biggest stories and talking "
        "points across the country right now. Sources: AFR Property, The Australian, ABC "
        "News, news.com.au, Guardian AU, Cotality/PropTrack news, RBA/ABS releases."
    ),
    "queensland": (
        "QUEENSLAND / BRISBANE residential property — state-level stories right now. Sources: "
        "Brisbane Times, Courier-Mail, QGSO releases, REIQ, QLD Treasury/budget."
    ),
    "gold_coast": (
        "GOLD COAST (esp. southern GC — Robina, Varsity Lakes, Burleigh Waters) residential "
        "property — local stories right now. Sources: Gold Coast Bulletin, myGC, local REIQ/"
        "agent commentary, council development notices, major local listings/developments."
    ),
}

PROMPT = """\
You are a property-market news scanner for a Gold Coast data-led property business. Using web
search, find the biggest CURRENT stories and talking points (roughly the last 3 weeks, {cycle})
about: {focus}

Report WHAT is being discussed and HOW LOUDLY. Do NOT assess whether each claim is true — that
is a later stage. Just surface the live conversation, honestly weighted by how much coverage it
is getting. Prefer reputable outlets; every item needs a real URL and a date.

Return ONLY a JSON array (in a ```json fenced block) of 6-12 items, each:
{{
  "headline": "<the story in a sentence>",
  "outlet": "<publication>",
  "url": "<direct url>",
  "date": "<YYYY-MM-DD or approximate>",
  "gist": "<one line: what it says>",
  "theme": "<2-4 word underlying theme, lowercase — e.g. 'interest rates', 'negative gearing reform', 'auction clearance', 'migration', 'supply shortage', 'market crash fears'>",
  "loudness": <1-5 integer: how much coverage/attention this is getting>
}}
No prose outside the JSON block.
"""


def scan_tier(tier: str, focus: str, *, model: str, timeout: int, max_turns: int) -> list:
    prompt = PROMPT.format(cycle=mc.cycle_id(), focus=focus)
    res = mc.run_claude(prompt, model=model, timeout=timeout, max_turns=max_turns)
    try:
        items = mc.extract_json(res["text"])
    except ValueError as e:
        raise RuntimeError(f"tier '{tier}': {e}")
    # tolerate an object wrapping the array (e.g. {"headlines": [...]})
    if isinstance(items, dict):
        items = next((v for v in items.values() if isinstance(v, list)), None)
    if not isinstance(items, list):
        raise RuntimeError(f"tier '{tier}': expected a JSON array, got {type(items).__name__}")
    for it in items:
        it["tier"] = tier
    print(f"    ✓ Stage 1 [{tier}]: {len(items)} headlines "
          f"(${res.get('cost')}, {res.get('turns')} turns)", file=sys.stderr)
    return items


def run(cycle: str, *, tiers: list[str] | None = None, model: str | None = None,
        timeout: int = 900, max_turns: int = 20) -> dict:
    model = model or mc.MODEL_FAST
    tiers = tiers or list(TIERS.keys())
    all_items, per_tier, failures = [], {}, []
    for tier in tiers:
        try:
            items = scan_tier(tier, TIERS[tier], model=model, timeout=timeout,
                              max_turns=max_turns)
            per_tier[tier] = len(items)
            all_items.extend(items)
        except Exception as e:
            failures.append(f"{tier}: {type(e).__name__}: {e}")
            per_tier[tier] = 0
            print(f"    ✗ Stage 1 [{tier}]: {e}", file=sys.stderr)

    out = {"cycle": cycle, "per_tier": per_tier, "count": len(all_items),
           "failures": failures, "headlines": all_items}
    mc.save_artifact(cycle, "headlines_raw.json", out)

    # Rule 7b: empty scan means broken tools, not a quiet news week.
    if len(all_items) == 0:
        raise RuntimeError(f"Stage 1 produced 0 headlines across all tiers; failures={failures}")
    return out


def main():
    ap = argparse.ArgumentParser(description="MCE Stage 1 — headline scan")
    ap.add_argument("--cycle", default=mc.cycle_id())
    ap.add_argument("--tier", action="append", choices=list(TIERS.keys()),
                    help="limit to specific tier(s); repeatable")
    ap.add_argument("--model", default=None)
    a = ap.parse_args()
    out = run(a.cycle, tiers=a.tier, model=a.model)
    print(json.dumps(out["per_tier"], indent=2))
    return 0


if __name__ == "__main__":
    sys.exit(main())
