#!/usr/bin/env python3
"""
seo_improvement_weekly.py — Samantha's special WEEKLY SEO-improvement run.

Separate from the daily run. Once a week she reviews the SEO & Indexation
Dashboard (and live GSC) with one aim: raise organic SEO performance generally,
and for /for-sale-v3 in particular — then SHIP at least one real, verified
improvement (or escalate a genuine Will-decision), and report it.

Runs headless on the Claude Max subscription (Opus, high effort), same billing
pattern as daily_run.py (strips ANTHROPIC_API_KEY so it uses the Max OAuth).

The whole run is wrapped in job_status.job_run("samantha_seo_improvement",
cadence_hours=168, stale_hours=180) so it self-reports to system_monitor.job_runs
and AUTO-appears on the Fields Systems Health sheet → Process Registry, going
STALE if a week passes with no run (that is the monitor Will asked for).

Usage:
    python3 scripts/samantha/seo_improvement_weekly.py            # real weekly run
    python3 scripts/samantha/seo_improvement_weekly.py --smoke    # cheap plumbing test
"""
import argparse
import asyncio
import json
import os
import sys
import time
from pathlib import Path

ORCH = "/home/fields/Fields_Orchestrator"
sys.path.insert(0, ORCH)
sys.path.insert(0, str(Path(ORCH) / "scripts"))
sys.path.insert(0, str(Path(ORCH) / "scripts" / "samantha"))

from claude_agent_sdk import query, ClaudeAgentOptions  # noqa: E402
from job_status import job_run  # noqa: E402
# Reuse the battle-tested Max-billing + usage + telegram + transcript helpers.
from daily_run import (  # noqa: E402
    _usage_status, _now, _telegram, _sdk_env, _serialize_block,
    FOLDER_ID, SAMANTHA_DIR, LOG_DIR,
)

RUN_MINUTES = int(os.environ.get("SEO_RUN_MINUTES", "40"))
TASK_FILE = SAMANTHA_DIR / "seo_improvement_task.md"
DASHBOARD_URL = "https://docs.google.com/spreadsheets/d/1ePTElYggYG8ZQKag4FuLCuh8uYTYfVWhGg9X_dTzyYs/edit"


def _build_prompt(date_str: str, report_path: Path, status_path: Path) -> str:
    charter = (SAMANTHA_DIR / "charter.md").read_text()
    task = TASK_FILE.read_text()
    runtime = f"""
=== THIS RUN: WEEKLY SEO IMPROVEMENT ({date_str}) ===
You are running your **special weekly SEO-improvement workflow** (above), NOT the daily run.
One focus only: raise organic SEO performance, especially for /for-sale-v3. Keep a running
report file at {report_path} and append to it as you work.

DELIVERY PROTOCOL — checkpoint, THEN act, THEN finalise:

PHASE A (first ~10 min): read ALL tabs of the SEO & Indexation Dashboard
({DASHBOARD_URL}) via the google-drive MCP, fetch /for-sale-v3 + a /houses-for-sale/<suburb>
page as Googlebot, and decide the single highest-leverage improvement. Then:
  FOLDER=$(python3 scripts/samantha/session_folder.py ensure --quiet)
Create a Google Doc "Samantha SEO Weekly — {date_str}" (mimeType application/vnd.google-apps.document,
parents=[$FOLDER]) with your findings so far, and Telegram Will a concise checkpoint
(`python3 scripts/telegram_notify.py "..."`). If Drive OAuth is down, note it and continue.

PHASE B (ACT — the mandatory part): ship at least ONE concrete, safe, reversible SEO
improvement (bias to /for-sale-v3 and the suburb pages), verified per CLAUDE.md Rules 4+5
(real build + Googlebot fetch + a screenshot you READ; ONE atomic Git-Trees commit — never a
burst of per-file PUTs). Record it in the change ledger. If the only worthwhile move is a
genuine Will-decision, write a crisp evidence-backed proposal instead. Append everything to
{report_path} as you go.

PHASE C (finalise, last ~5 min): update the same Google Doc with the full report (incl. a
"What I shipped this week" section + the SEO hypothesis + next week's candidate), send a short
FINAL Telegram of what you DID, then write {status_path} LAST as JSON exactly:
  {{"delivered": true, "doc_url": "<link or null>", "telegram_sent": true,
    "shipped": "<one line: what changed, or 'proposal only'>", "commit": "<sha or null>"}}

If cut off before the status file, the runner reads {report_path} and Telegrams a fallback —
so keep it current. Deliver the Phase-A checkpoint EARLY so acting never risks delivery.
You have ~{RUN_MINUTES} minutes of wall-clock. Do NOT finish with lots of budget left and
nothing shipped — that defeats the point of the weekly run.
"""
    if os.environ.get("_SEO_SMOKE"):
        runtime += f"""
=== SMOKE TEST MODE ===
Plumbing test only, ~2 min: read just the Overview tab of the dashboard, then do the FULL
delivery protocol with a 3-line Doc "Samantha SEO SMOKE — {date_str}" and a Telegram. Do NOT
make any website change. The point is to verify Max auth + Drive + Telegram + the status file.
"""
    return f"{charter}\n\n{task}\n\n{runtime}"


async def _run_agent(prompt: str, timeout_s: int, smoke: bool,
                     transcript_path: Path, report_path: Path) -> str:
    options = ClaudeAgentOptions(
        model="opus",             # Fable disabled 2026-07-29 (Will) — draws down Max limit too fast
        fallback_model="opus",
        effort="high",
        cwd=ORCH,
        env=_sdk_env(),
        permission_mode="bypassPermissions",
        setting_sources=["user", "project", "local"],  # CLAUDE.md + .mcp.json (gdrive, posthog)
        max_turns=8 if smoke else 240,
        max_buffer_size=64 * 1024 * 1024,
        # smoke still needs enough headroom to read a tab + write the Doc + Telegram
        # + status file (delivery is the whole point of the plumbing test).
        max_budget_usd=5.0 if smoke else 50.0,
        system_prompt={"type": "preset", "preset": "claude_code", "append": prompt},
    )

    tool_calls = 0
    session_id = None

    def _log(rec):
        try:
            rec["ts"] = _now().strftime("%H:%M:%S")
            with transcript_path.open("a") as fh:
                fh.write(json.dumps(rec, default=str) + "\n")
        except Exception:
            pass

    async def _segment(seg_prompt: str):
        nonlocal tool_calls, session_id
        async for msg in query(prompt=seg_prompt, options=options):
            sid = getattr(msg, "session_id", None)
            if sid:
                session_id = sid
            for block in (getattr(msg, "content", None) or []):
                rec = _serialize_block(block)
                if not rec:
                    continue
                _log(rec)
                if rec["t"] == "tool_use":
                    tool_calls += 1
                    print(f"[seo] tool #{tool_calls}: {rec.get('name')} {rec.get('input','')[:100]}", flush=True)
            if type(msg).__name__ == "ResultMessage":
                print(f"[seo] segment done: {getattr(msg,'subtype','')} "
                      f"turns={getattr(msg,'num_turns',None)} tools={tool_calls}", flush=True)

    start = time.monotonic()
    nudges = 0
    max_nudges = 0 if smoke else 2
    seg = "Begin your weekly SEO-improvement run now."
    while True:
        if time.monotonic() - start > timeout_s - 20:
            return "budget"
        await _segment(seg)
        # If it stopped with meaningful time left and hasn't shipped much, nudge once.
        remaining_m = (timeout_s - (time.monotonic() - start)) / 60
        shipped = report_path.exists() and "shipped" in report_path.read_text().lower()
        if nudges >= max_nudges or remaining_m < 6 or shipped:
            return "complete"
        nudges += 1
        if session_id:
            options.resume = session_id
        seg = (f"You have ~{remaining_m:.0f} min left and have not yet shipped a verified SEO "
               "improvement (or a written proposal). Per the workflow, pick the single highest-"
               "leverage move for /for-sale-v3 or the suburb pages and EXECUTE it now — build, "
               "verify, ONE atomic commit — then finalise the Doc + Telegram + status file.")


def _fallback(date_str: str, report_path: Path, status_path: Path):
    prefix = f"📈 Samantha SEO Weekly — {date_str}\n"
    if status_path.exists():
        try:
            st = json.loads(status_path.read_text())
            if st.get("delivered"):
                return  # she delivered her own
        except Exception:
            pass
    if report_path.exists():
        body = report_path.read_text()
        _telegram(prefix + "Runner fallback (she was cut off). Working report:\n\n" + body[:1400])
    else:
        _telegram(prefix + "No report written — check logs/samantha/seo-weekly.log on the VM.")


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--smoke", action="store_true")
    args = ap.parse_args()
    if args.smoke:
        os.environ["_SEO_SMOKE"] = "1"

    date_str = _now().strftime("%Y-%m-%d")
    report_path = LOG_DIR / f"seo-weekly-report-{date_str}.md"
    status_path = LOG_DIR / f"seo-weekly-status-{date_str}.json"
    transcript_path = LOG_DIR / f"seo-weekly-transcript-{date_str}.jsonl"
    report_path.write_text(f"# Samantha SEO Weekly — {date_str}\n\n(in progress)\n")

    # Pre-flight Max usage gate (shared account pool) — skip if already over budget.
    usage = _usage_status()
    if usage.get("ok") and usage.get("over_budget") and not args.smoke:
        msg = (f"⏭️ Samantha skipped the weekly SEO run — Claude Max usage over budget "
               f"(5h={usage['five_hour_pct']}%, 7d={usage['seven_day_pct']}%). Will retry next week.")
        print(msg, flush=True)
        _telegram(msg)
        # NOT a failure — a deliberate skip. Do not poison the heartbeat; leave last week's OK.
        return 0
    if usage.get("ok"):
        print(f"[seo] usage OK: 5h={usage['five_hour_pct']}% 7d={usage['seven_day_pct']}%", flush=True)

    timeout_s = RUN_MINUTES * 60
    prompt = _build_prompt(date_str, report_path, status_path)

    # Heartbeat wrapper: success/failure recorded → monitor on Systems Health.
    # Weekly cadence; flag STALE if no run in ~7.5 days (stale_hours=180) so a
    # genuinely-missed week alerts without flapping at the weekly boundary.
    with job_run("samantha_seo_improvement", cadence_hours=168, stale_hours=180,
                 title="Weekly SEO Improvement (Samantha)") as beat:
        start = _now()
        reason = asyncio.run(_run_agent(prompt, timeout_s, args.smoke, transcript_path, report_path))
        _fallback(date_str, report_path, status_path)
        shipped = "unknown"
        if status_path.exists():
            try:
                shipped = json.loads(status_path.read_text()).get("shipped", "unknown")
            except Exception:
                pass
        beat.detail = f"{reason} · shipped: {shipped}"
        beat.metrics = {"finished": reason, "smoke": args.smoke}
        print(f"[seo] done in {(_now()-start).total_seconds():.0f}s ({reason})", flush=True)
    return 0


if __name__ == "__main__":
    sys.exit(main())
