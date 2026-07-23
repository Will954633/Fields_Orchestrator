#!/usr/bin/env python3
"""
fetch_policy_research.py — Monthly national/state housing-policy research brief
for the Market Pulse writing session.

Why: Will asked (2026-07-22) for national/state policy context (RBA rate path,
federal tax reform, first-home-buyer schemes, state stamp duty) woven into the
Market Pulse summaries wherever materially relevant — omitting it makes a
market summary look inadequate. Doing this research ad-hoc via WebSearch inside
the collaborative writing session works, but redoes the same research from
scratch every month. This script pre-fetches it a few days ahead of the 1st-of-
month reminder, via the full `claude` CLI (billed against the Claude Max
subscription, not pay-as-you-go API credits — see scripts/backend_enrichment/
claude_max_client.py for why that distinction matters on this VM).

Note: this deliberately does NOT use claude_max_client.py's MaxClient — that
shim strips tools (including web_search) and falls back to the real API the
moment a tool is requested. This script invokes the `claude` CLI directly in
its normal agentic mode (WebSearch available, multi-turn), which is how a
regular Claude Code session gets Max-subscription web search.

Usage:
    python3 scripts/fetch_policy_research.py                # fetch + write to MongoDB
    python3 scripts/fetch_policy_research.py --dry-run       # fetch + print, don't write
    python3 scripts/fetch_policy_research.py --show-latest   # print the most recent cached brief
"""

import argparse
import json
import os
import subprocess
import sys
from datetime import datetime, timezone

from pymongo import MongoClient

CLI_TIMEOUT_S = int(os.environ.get("POLICY_RESEARCH_CLI_TIMEOUT", "300"))
CLI_BIN = os.environ.get("CLAUDE_BIN", "claude")

PROMPT = """\
Research current Australian federal and Queensland state government housing \
policy that materially affects the residential property market, for a \
Gold Coast (Robina / Burleigh Waters / Varsity Lakes) audience. Use web search \
for anything time-sensitive — do not rely on training data alone for rates, \
budget measures, or scheme thresholds.

Cover, if there's been any change or notable status update since last month:
1. RBA cash rate — current rate, recent decisions, next meeting/expectations.
2. Federal tax policy affecting property investors/owners — negative gearing, \
capital gains tax, any budget measures.
3. First-home-buyer schemes — 5% Deposit Scheme, Help to Buy, any eligibility \
or threshold changes.
4. Queensland-specific — stamp duty, land tax, foreign buyer surcharges, any \
QLD state budget housing measures.
5. Any other genuinely new, market-moving federal or QLD housing policy news \
from the last ~30 days not covered above.

For each item: state the fact plainly, the date it took effect or was \
announced, and cite the source URL. If nothing has changed on a topic since \
what would already be known (RBA held, no new budget measures), say so briefly \
rather than padding — this brief should make it fast to spot what's actually \
new, not repeat the same facts every month.

End with a short "unchanged from last month" list for anything you found no \
update on, so it's easy to skim.
"""


def get_db():
    conn_str = os.environ.get("COSMOS_CONNECTION_STRING")
    if not conn_str:
        print("ERROR: COSMOS_CONNECTION_STRING not set")
        sys.exit(1)
    return MongoClient(conn_str)


def _child_env() -> dict:
    env = dict(os.environ)
    # Force Max billing — same reasoning as claude_max_client.py's _child_env().
    env.pop("ANTHROPIC_API_KEY", None)
    env.pop("ANTHROPIC_AUTH_TOKEN", None)
    env.pop("CLAUDECODE", None)
    env.setdefault("CI", "true")
    return env


def run_research() -> dict:
    """Invoke the claude CLI in full agentic mode (WebSearch enabled) and
    return the parsed result. Raises on CLI failure — caller decides how to
    handle (this is a monthly, human-reviewed step, not a hard pipeline
    dependency, so failing loudly here is preferable to silently writing a
    stale/empty brief)."""
    cmd = [CLI_BIN, "-p", PROMPT, "--output-format", "json"]
    proc = subprocess.run(
        cmd,
        text=True,
        capture_output=True,
        timeout=CLI_TIMEOUT_S,
        env=_child_env(),
    )
    if proc.returncode != 0:
        raise RuntimeError(f"claude CLI exited {proc.returncode}: {(proc.stderr or '')[:500]}")

    try:
        data = json.loads(proc.stdout)
    except json.JSONDecodeError as e:
        raise RuntimeError(f"non-JSON CLI output: {e}: {proc.stdout[:300]}")

    if data.get("is_error") or data.get("subtype") != "success":
        raise RuntimeError(f"CLI returned error: {data.get('subtype')}: {str(data.get('result'))[:500]}")

    return data


def build_market_pulse_policy_brief(dry_run: bool = False):
    print("Researching current AU/QLD housing policy via claude CLI (web search enabled)...")
    result = run_research()
    text = result.get("result", "")
    cost = result.get("total_cost_usd")
    print(f"  Done. Notional cost: ${cost:.2f} (billed against Claude Max, not API credits)" if cost else "  Done.")
    print()
    print("=" * 80)
    print(text)
    print("=" * 80)

    if dry_run:
        print("\n=== DRY RUN — would write to system_monitor.policy_research_briefs ===")
        return

    client = get_db()
    db = client["system_monitor"]
    now = datetime.now(timezone.utc)
    doc = {
        "generated_at": now,
        "month_label": now.strftime("%B %Y"),
        "brief_text": text,
        "model": result.get("model") or "claude (CLI, Max)",
        "session_id": result.get("session_id"),
        "notional_cost_usd": cost,
    }
    db["policy_research_briefs"].insert_one(doc)
    print(f"\nWritten to system_monitor.policy_research_briefs ({now.strftime('%Y-%m-%d %H:%M')} UTC)")
    client.close()


def show_latest():
    client = get_db()
    db = client["system_monitor"]
    doc = db["policy_research_briefs"].find_one(sort=[("generated_at", -1)])
    if not doc:
        print("No policy research briefs found.")
        return
    print(f"Generated: {doc['generated_at']} ({doc.get('month_label', '?')})")
    print("=" * 80)
    print(doc.get("brief_text", ""))
    client.close()


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Fetch monthly AU/QLD housing policy research brief")
    parser.add_argument("--dry-run", action="store_true", help="Fetch and print without writing to DB")
    parser.add_argument("--show-latest", action="store_true", help="Print the most recently cached brief")
    args = parser.parse_args()

    if args.show_latest:
        show_latest()
    else:
        build_market_pulse_policy_brief(dry_run=args.dry_run)
