#!/usr/bin/env python3
"""
nightly_lead_chain.py — run the whole lead pipeline in dependency order, once, nightly.

WHY THIS EXISTS
---------------
These five scripts have a real dependency chain, but until 2026-08-01 each one was
an independent cron entry at a hand-picked minute, and two of them were ordered
WRONG relative to each other:

    crm_sync            :07 hourly  (PostHog site engagement -> crm_contacts)
    live_leads_to_sheet 23:55       (writes the Live Leads Tracker sheet)
    lead_intelligence   02:00       (builds lead_worklist)   <- AFTER the sheet
    seller_intent       02:00       (writes seller_intent.story)

The sheet's "Situation" column is read from lead_worklist.seller_intent, so a lead
captured today hit the sheet at 23:55 with a BLANK Situation, only got into the
worklist at 02:00, and only had its Situation filled in by the NEXT night's 23:55
run — roughly a 30-hour lag before a lead was fully actionable.

Running them as one ordered chain after midnight (so the day's data is complete,
including the 23:30-23:55 listing/property syncs the enrichment reads) means every
lead captured today is fully collected, enriched, scored, storied and on the sheet
before the day is out — and Samantha's 02:30 review, hot_lead_responder and Will's
morning triage all see complete rows the very next day.

FAILURE POLICY
--------------
A step that fails does not silently take the rest down with it: dependent steps are
skipped (running them on half-built data would write wrong rows), independent steps
still run, and the chain then exits non-zero so job_run records status=error on the
"Fields Systems Health" Process Registry (CLAUDE.md Rule 7) and Telegram fires.

Usage:
  python3 scripts/nightly_lead_chain.py
  python3 scripts/nightly_lead_chain.py --dry-run        # pass --dry-run to steps that support it
  python3 scripts/nightly_lead_chain.py --only live_leads_to_sheet
  python3 scripts/nightly_lead_chain.py --skip crm_sync
"""
from __future__ import annotations

import argparse
import os
import subprocess
import sys
import time
from datetime import datetime, timedelta, timezone

ROOT = "/home/fields/Fields_Orchestrator"
PY = "/home/fields/venv/bin/python3"
AEST = timezone(timedelta(hours=10))

sys.path.insert(0, ROOT)
sys.path.insert(0, os.path.join(ROOT, "scripts"))


class Step:
    """One script in the chain.

    `needs` names the steps whose OUTPUT this step reads — not merely the steps that
    happen to run before it. If a named step failed, this one is skipped rather than
    run against stale/partial data.
    """

    def __init__(self, name, argv, why, needs=(), supports_dry_run=True, timeout=3600):
        self.name = name
        self.argv = argv
        self.why = why
        self.needs = tuple(needs)
        self.supports_dry_run = supports_dry_run
        self.timeout = timeout


STEPS = [
    Step("crm_sync", [PY, f"{ROOT}/scripts/crm_sync.py"],
         "PostHog site engagement -> crm_contacts. The hourly pass last ran at 23:07, "
         "so without this the final ~50 minutes of the day are missing from every "
         "downstream lead record."),
    Step("bind_report_leads_to_crm", [PY, f"{ROOT}/scripts/bind_report_leads_to_crm.py"],
         "Join leadpage property-report leads (Owner-Market carousel + other AYH-leadpage "
         "ads) to their CRM contact: stamp owner.posthog_distinct_id into lead_web + the "
         "address/source/attribution, so lead_web_activity harvests their behaviour and "
         "the crm-contact page renders it. Must run AFTER crm_sync (contact must exist / "
         "not mid-replace) and BEFORE lead_web_activity (which reads what this writes).",
         needs=["crm_sync"]),
    Step("lead_web_activity", [PY, f"{ROOT}/scripts/lead_web_activity.py"],
         "Pull each identity-bound lead's on-site pageview journey onto their "
         "crm_contact (lead_web.activity). Reads lead_web.posthog_distinct_id written "
         "by lead-link-visit.mjs (tokenised click-through) AND by bind_report_leads_to_crm "
         "(leadpage report leads), and stamps the durable journey before the sheet/worklist "
         "steps render it. Needs crm_sync (must not run mid-replace) + the bind step.",
         needs=["crm_sync", "bind_report_leads_to_crm"]),
    Step("lead_intelligence", [PY, f"{ROOT}/scripts/samantha/lead_intelligence.py"],
         "Unify + enrich + score every lead into lead_worklist. Reads crm_contacts "
         "and the Gold_Coast listing status the 23:30-23:55 syncs just refreshed.",
         needs=["crm_sync"]),
    Step("seller_intent", [PY, f"{ROOT}/scripts/samantha/seller_intent.py", "--all"],
         "Writes lead_worklist.seller_intent.story — the text the sheet's Situation "
         "column renders.",
         needs=["lead_intelligence"]),
    Step("live_leads_to_sheet", [PY, f"{ROOT}/scripts/live_leads_to_sheet.py"],
         "Insert new leads into the Live Leads Tracker. Runs LAST so a lead added "
         "tonight gets its Situation on the first insert, not a night later.",
         needs=["lead_intelligence", "seller_intent"]),
    Step("leads_came_to_market", [PY, f"{ROOT}/scripts/leads_came_to_market.py"],
         "Move leads whose home is now listed with another agent off 'All Leads' and "
         "onto the 'Came to Market' tab. Runs AFTER the sheet write so leads captured "
         "tonight are swept in the same pass rather than sitting a day in the working "
         "list. Needs the sheet step because it reads and edits the rows that step "
         "wrote.",
         needs=["live_leads_to_sheet"]),
    Step("leads_prune_nonleads", [PY, f"{ROOT}/scripts/leads_prune_nonleads.py"],
         "Take our own test builds, demos and speculative pre-builds back off the "
         "sheet. The sheet is insert-only, so a record flagged as a test AFTER it was "
         "inserted stays a 'lead' forever unless something reconciles it.",
         needs=["live_leads_to_sheet"]),
    Step("engagement_activity_to_sheet", [PY, f"{ROOT}/scripts/engagement_activity_to_sheet.py"],
         "Returning-known-contact activity ledger. Reads crm_contacts; independent of "
         "the worklist, so it still runs if enrichment failed.",
         needs=["crm_sync"], supports_dry_run=False),
    Step("priority_calls_to_sheet", [PY, f"{ROOT}/scripts/priority_calls_to_sheet.py"],
         "The Priority tab — who Will actually rings today, from crm_contacts.follow_up_at. "
         "Runs last because it harvests the Done ticks off the tab and clears them in the "
         "CRM, so it must see the day's final state. Needs crm_sync only: the follow-ups "
         "are hand-set by log_contact_touch.py, so this tab is still correct on a night "
         "when behavioural enrichment fails.",
         needs=["crm_sync"]),
    Step("mail_log_to_sheet", [PY, f"{ROOT}/scripts/mail_log_to_sheet.py"],
         "The Mail Log tab — every physical mail piece sent (system_monitor.mail_log), "
         "so posted_date updates and any new batch reach the tab nightly. Independent of "
         "the digital-lead steps; a full-rewrite mirror of an authoritative Mongo record.",
         needs=(), supports_dry_run=False),
]


def run_step(step: Step, dry_run: bool) -> tuple[str, str, float]:
    """Returns (status, detail, seconds). status in ok|failed|timeout."""
    argv = list(step.argv) + (["--dry-run"] if dry_run and step.supports_dry_run else [])
    started = time.monotonic()
    print(f"\n{'=' * 72}\n[{datetime.now(AEST):%H:%M:%S}] {step.name}\n    {step.why}\n"
          f"    $ {' '.join(argv)}\n{'=' * 72}", flush=True)

    env = dict(os.environ, GH_CONFIG_DIR="/home/projects/.config/gh")
    try:
        proc = subprocess.run(argv, cwd=ROOT, env=env, timeout=step.timeout,
                              stdout=sys.stdout, stderr=subprocess.STDOUT)
    except subprocess.TimeoutExpired:
        return "timeout", f"exceeded {step.timeout}s", time.monotonic() - started

    secs = time.monotonic() - started
    if proc.returncode != 0:
        return "failed", f"exit {proc.returncode}", secs
    return "ok", "", secs


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--only", action="append", default=[], help="run only these step(s)")
    ap.add_argument("--skip", action="append", default=[], help="skip these step(s)")
    ap.add_argument("--no-alert", action="store_true")
    args = ap.parse_args()

    from job_status import job_run

    steps = [s for s in STEPS if (not args.only or s.name in args.only)
             and s.name not in args.skip]

    results: dict[str, str] = {}
    timings: dict[str, float] = {}
    started_at = datetime.now(AEST)

    with job_run("nightly_lead_chain", cadence_hours=24,
                 title="Nightly Lead Chain (crm -> worklist -> intent -> sheet)") as beat:
        for step in steps:
            if args.dry_run and not step.supports_dry_run:
                print(f"\n[SKIP] {step.name} — has no --dry-run flag; skipping rather "
                      f"than writing for real during a dry run.", flush=True)
                results[step.name] = "dry-skip"
                continue
            blocked = [n for n in step.needs
                       if results.get(n, "ok") not in ("ok", "dry-skip")]
            if blocked:
                print(f"\n[SKIP] {step.name} — needs {', '.join(blocked)}, which did not "
                      f"succeed. Running it now would write rows built on stale data.",
                      flush=True)
                results[step.name] = "blocked"
                continue
            status, detail, secs = run_step(step, args.dry_run)
            results[step.name] = status
            timings[step.name] = round(secs, 1)
            if status != "ok":
                print(f"\n[FAIL] {step.name}: {detail} ({secs:.0f}s)", flush=True)
            else:
                print(f"\n[OK] {step.name} ({secs:.0f}s)", flush=True)

        bad = {n: s for n, s in results.items() if s not in ("ok", "dry-skip")}
        summary = ", ".join(f"{n}={s}" for n, s in results.items())
        print(f"\n{'=' * 72}\nChain finished in "
              f"{(datetime.now(AEST) - started_at).total_seconds():.0f}s — {summary}")

        beat.detail = (f"{len(results) - len(bad)}/{len(results)} steps ok" if bad
                       else f"all {len(results)} steps ok")
        beat.metrics = {"steps": results, "seconds": timings}

        if bad:
            if not args.no_alert:
                alert(bad, results)
            # Raise inside job_run so the heartbeat records status=error with the
            # traceback — a chain that half-ran must never look healthy.
            raise RuntimeError(f"nightly lead chain: {len(bad)} step(s) not ok — {summary}")

    return 0


def alert(bad: dict, results: dict) -> None:
    try:
        from telegram_notify import send_message
        lines = [f"- {n}: {s}" for n, s in bad.items()]
        send_message("Nightly lead chain PROBLEM — leads may be missing from the "
                     "worklist/sheet tonight:\n" + "\n".join(lines) +
                     f"\n\nFull: {', '.join(f'{n}={s}' for n, s in results.items())}"
                     "\nLog: logs/nightly-lead-chain.log", parse_mode="")
    except Exception as e:  # noqa: BLE001
        print(f"(telegram alert skipped: {e})")


if __name__ == "__main__":
    sys.exit(main())
