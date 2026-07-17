#!/usr/bin/env python3
"""
daily_run.py — Samantha's scheduled nightly run.

Runs headless on the Claude Max subscription (Opus, high effort) once per day,
hard-capped at ~30 minutes. Produces ONE combined daily report covering:
  Task 1 — marketing direction signals (PostHog + CRM + Brain 2)
  Task 2 — organic engagement + served-data quality (SEO / Bing / AI referrals)
Saves the report as a Google Doc in Samantha's Drive folder and Telegrams Will a copy.

Billing: strips ANTHROPIC_API_KEY from the child env so the Agent SDK authenticates
via the Max subscription (OAuth) instead of pay-as-you-go API credits — same pattern
the voice agent uses (voice-agent/router.py:_sdk_env).

Time budget / elegant finish:
  * Samantha is TOLD her hard deadline (AEST HH:MM) and instructed to stop analysing
    and finalise (Doc + Telegram + status file) once within the last ~5 minutes.
  * Belt-and-braces: this runner hard-cancels the SDK query at SAMANTHA_RUN_MINUTES and,
    if she hasn't confirmed delivery in her status file, delivers a fallback Telegram from
    whatever she wrote to her working report file.

Usage:
  python3 scripts/samantha/daily_run.py            # full nightly run
  python3 scripts/samantha/daily_run.py --smoke    # cheap plumbing test (~2 min, low turns)
"""
from __future__ import annotations

import argparse
import asyncio
import json
import os
import subprocess
import sys
from datetime import datetime, timezone, timedelta
from pathlib import Path

ORCH = "/home/fields/Fields_Orchestrator"
sys.path.insert(0, ORCH)

from claude_agent_sdk import query, ClaudeAgentOptions  # noqa: E402

AEST = timezone(timedelta(hours=10))  # VM is Australia/Brisbane — fixed AEST, no DST
FOLDER_ID = "19avOQvAdn5uYiPveNxuXuKaMHEfzgShb"  # Samantha's Drive folder
SAMANTHA_DIR = Path(ORCH) / "scripts" / "samantha"
LOG_DIR = Path(ORCH) / "logs" / "samantha"
LOG_DIR.mkdir(parents=True, exist_ok=True)

RUN_MINUTES = int(os.environ.get("SAMANTHA_RUN_MINUTES", "30"))
RESERVE_MINUTES = int(os.environ.get("SAMANTHA_RESERVE_MINUTES", "5"))  # finish-elegantly buffer


def _now() -> datetime:
    return datetime.now(AEST)


def _telegram(text: str) -> bool:
    """Fallback Telegram send from the runner (Samantha sends her own during the run)."""
    try:
        r = subprocess.run(
            ["python3", "scripts/telegram_notify.py", text],
            cwd=ORCH, capture_output=True, text=True, timeout=30,
        )
        if r.returncode != 0:
            print(f"[runner] telegram send failed: {r.stdout} {r.stderr}", flush=True)
        return r.returncode == 0
    except Exception as e:  # noqa: BLE001
        print(f"[runner] telegram exception: {e}", flush=True)
        return False


def _sdk_env() -> dict:
    """Force Max billing: strip the API key so the CLI/SDK uses the OAuth subscription."""
    env = {k: v for k, v in os.environ.items() if k != "ANTHROPIC_API_KEY"}
    env["ANTHROPIC_API_KEY"] = ""
    return env


def _build_prompt(date_str: str, deadline: datetime, report_path: Path,
                  status_path: Path, smoke: bool) -> str:
    charter = (SAMANTHA_DIR / "charter.md").read_text()
    tasks = (SAMANTHA_DIR / "daily_tasks.md").read_text()
    soft = deadline - timedelta(minutes=RESERVE_MINUTES)

    runtime = f"""
=== THIS RUN (runtime) ===
Date (AEST): {date_str}
Hard deadline (AEST): {deadline.strftime('%H:%M')} — you MUST have finished delivery by then.
Soft deadline (AEST): {soft.strftime('%H:%M')} — STOP new analysis at this time and finalise.
The wall clock is real and enforced: at {deadline.strftime('%H:%M')} this process is killed.

FINISH ELEGANTLY — time-budget discipline:
- Before starting any expensive step, run `date +%H:%M` and check the clock.
- Reserve the final {RESERVE_MINUTES} minutes (from the soft deadline) to finalise: write your
  report file, create the Google Doc, send the Telegram, and write your status file.
- Better a complete, honest, slightly-shorter report delivered on time than a rich one that never ships.

=== DELIVERY PROTOCOL (mandatory — do ALL of these) ===
1. Write your full report (Markdown) to: {report_path}
   Write it INCREMENTALLY as you work so a partial exists even if you run out of time.
   One combined report, two clearly-headed sections (Task 1 and Task 2) + a "Follow-up
   opportunities" section + a short "Staged for Will's approval" section if you staged anything.
2. Create a Google Doc in your Drive folder (id: {FOLDER_ID}) titled "Samantha Daily — {date_str}"
   with the report contents, using the google-drive MCP tool `create_file`
   (mimeType application/vnd.google-apps.document). Capture the returned webViewLink.
   If Drive fails (OAuth can expire ~weekly), don't block — note it and continue.
3. Telegram Will a CONCISE summary (not the whole doc — Telegram caps ~4000 chars) via:
      python3 scripts/telegram_notify.py "..."
   Lead with the 2-3 highest-value findings + any approval-gated items, then the Doc link
   (or, if Drive failed, say the full report is in {report_path} on the VM).
4. Write your status file to {status_path} as JSON, EXACTLY this shape:
   {{"delivered": true, "doc_url": "<link or null>", "telegram_sent": true,
     "finished_reason": "complete|budget", "notes": "<one line>"}}
   This is how the runner knows delivery succeeded and skips its fallback. Write it LAST.

If you are cut off before step 4, the runner will read {report_path} and Telegram a fallback —
so keeping that file current throughout the run is your safety net.
"""

    if smoke:
        runtime += """
=== SMOKE TEST MODE ===
This is a cheap plumbing test, NOT a real analysis. Do only this, fast:
- Run `date` and one tiny mongo count (e.g. valuation_requests count) to prove VM/data access.
- Do the FULL delivery protocol above with a 3-line report titled "Samantha SMOKE TEST — {date}".
- The point is to verify Max auth, the report file, the Google Doc write, the Telegram, and the
  status file all work end-to-end. Keep it under ~2 minutes.
""".replace("{date}", date_str)

    return f"{charter}\n\n{tasks}\n\n{runtime}"


async def _run(prompt: str, timeout_s: int, smoke: bool) -> str:
    options = ClaudeAgentOptions(
        model="opus",
        effort="high",
        cwd=ORCH,
        env=_sdk_env(),
        permission_mode="bypassPermissions",
        setting_sources=["user", "project", "local"],  # load CLAUDE.md + .mcp.json (gdrive, posthog)
        max_turns=8 if smoke else 240,
        # Max subscription: the 30-min WALL CLOCK is the real limiter, not $ cost.
        # Keep this generous so the time budget (not a cost estimate) ends the run.
        max_budget_usd=1.0 if smoke else 50.0,
        system_prompt={"type": "preset", "preset": "claude_code",
                       "append": prompt},
    )

    transcript_tail = ""
    tool_calls = 0

    async def _loop():
        nonlocal transcript_tail, tool_calls
        async for msg in query(prompt="Begin your scheduled run now.", options=options):
            content = getattr(msg, "content", None)
            if content:
                for block in content:
                    btype = getattr(block, "type", None) or type(block).__name__
                    text = getattr(block, "text", None)
                    if text:
                        transcript_tail = (transcript_tail + text)[-4000:]
                    if "ToolUse" in str(btype) or btype == "tool_use":
                        tool_calls += 1
            rtype = type(msg).__name__
            if rtype == "ResultMessage":
                print(f"[runner] result: {getattr(msg,'subtype','')} "
                      f"turns={getattr(msg,'num_turns','?')} "
                      f"cost=${getattr(msg,'total_cost_usd','?')}", flush=True)

    try:
        await asyncio.wait_for(_loop(), timeout=timeout_s)
        return "complete"
    except asyncio.TimeoutError:
        print(f"[runner] hard timeout at {timeout_s}s — cancelling.", flush=True)
        return "timeout"
    except Exception as e:  # noqa: BLE001
        print(f"[runner] SDK error: {e}", flush=True)
        return f"error: {e}"


def _fallback_delivery(date_str: str, report_path: Path, status_path: Path,
                       finished_reason: str) -> None:
    """If Samantha didn't confirm delivery, ship what we have + alert Will."""
    delivered = False
    if status_path.exists():
        try:
            st = json.loads(status_path.read_text())
            delivered = bool(st.get("delivered"))
        except Exception:  # noqa: BLE001
            pass

    if delivered:
        print("[runner] Samantha confirmed delivery — no fallback needed.", flush=True)
        return

    print(f"[runner] delivery NOT confirmed ({finished_reason}) — sending fallback.", flush=True)
    body = ""
    if report_path.exists():
        body = report_path.read_text().strip()

    prefix = (f"⏱ Samantha nightly ({date_str}) — {finished_reason.upper()}, "
              f"she didn't confirm delivery. ")
    if not body:
        _telegram(prefix + "No report file was written. Check logs/samantha/ on the VM.")
        return

    # Telegram cap ~4096 chars; send a header + the first chunk, point to the VM for the rest.
    head = body[:3200]
    more = "" if len(body) <= 3200 else f"\n\n…(truncated; full report: {report_path})"
    _telegram(prefix + "Fallback copy of her working report:\n\n" + head + more)


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--smoke", action="store_true", help="cheap plumbing test")
    ap.add_argument("--minutes", type=int, default=RUN_MINUTES)
    args = ap.parse_args()

    start = _now()
    date_str = start.strftime("%Y-%m-%d")
    run_minutes = 3 if args.smoke else args.minutes
    deadline = start + timedelta(minutes=run_minutes)
    report_path = LOG_DIR / f"{date_str}-report.md"
    status_path = LOG_DIR / f"{date_str}-status.json"

    # Clear any stale status from a previous same-day run so fallback logic is correct.
    if status_path.exists():
        status_path.unlink()

    print(f"[runner] Samantha {'SMOKE' if args.smoke else 'nightly'} run start "
          f"{start.isoformat()} deadline {deadline.strftime('%H:%M')} AEST "
          f"({run_minutes} min)", flush=True)

    prompt = _build_prompt(date_str, deadline, report_path, status_path, args.smoke)
    timeout_s = run_minutes * 60
    finished_reason = asyncio.run(_run(prompt, timeout_s, args.smoke))

    _fallback_delivery(date_str, report_path, status_path, finished_reason)

    print(f"[runner] done in {(_now()-start).total_seconds():.0f}s "
          f"reason={finished_reason}", flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
