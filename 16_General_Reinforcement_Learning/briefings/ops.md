# OPS (system health + pipeline integrity) — standing brief

**Last updated:** 2026-08-13 by Will + Samantha (first briefing session)
**Review cadence:** weekly

> This document is the domain's **authorisation envelope**, not background reading. Work
> inside §1 Direction and §4 Standing Authorisations is executed autonomously and reported
> afterwards. Work outside it is proposed and waits.
>

---

## 1. Direction — what we are doing here and why

Keep the machine honest. Every other domain asks how to win more; ops asks what is broken
and what can honestly be fixed.

Two things Will settled on 2026-08-13:

1. **Register the ~15 retired daily RL rows as PAUSED.** They still declare 1-24h cadences
   after the move to weekly, so the board is crying wolf on all of them. Will: *"register as
   paused."* Note the standing prohibition on editing monitoring code still applies — this is
   the one exception he has explicitly authorised, and it covers registering those specific
   retired rows as paused, nothing wider.
2. **Credential-liveness monitoring is agreed in principle.** Bright Data was the sixth
   credential-expiry outage and none of them had a watcher.

## 2. Current state — what is ON, OFF, or PAUSED, and deliberately so

| Thing | State | Why |
|---|---|---|
| RL fleet | **Weekly since 2026-08-13** | `rl_weekly_*` heartbeats are ordinary jobs and are ops' business. Cadence 168h — a 3-day-old row is NOT stale. |
| Home Owner funnel jobs | **Paused on purpose** since 2026-07-30 | KNOWN-GAP, not decay. |
| Retired daily RL rows | ~15 stale rows | **Will approved registering these as paused.** |
| Bright Data ingestion | **Restored 2026-08-13** | Token rotated by Will after 2.5 days dead. |
| Credential monitoring | **Approved in principle** | Build it. |

## 3. Goals — what good looks like

1. Problems genuinely resolved — never a greener-looking board.
2. Reduce time-to-notice when something silently stops working.
3. A board where every red row is honestly red.

## 4. Standing authorisations — SHIP THESE WITHOUT ASKING

- Re-run failed idempotent jobs (verify idempotency first; at most twice).
- Clear verified-dead lock files.
- Fix pipeline bugs in NON-monitoring code — including zero-output and heartbeat-ordering
  bugs such as `run_curlffi_suburb_scrape.py` returning before it writes its heartbeat.
- **Register the ~15 retired daily RL rows as paused** (Will, 2026-08-13 — this specific
  task only).
- **Build credential-liveness monitoring** (Will approved in principle 2026-08-13): one cheap
  authenticated call per credential, reported via `job_run()`, alerting before dependent jobs
  start returning zero.
- Read anything.

## 5. Off-limits — never, regardless of anything else

Global prohibitions always apply and are never granted by a brief: spending money,
editing the crontab, editing monitoring/health-check code, contacting a real person,
deleting data, Gold Coast go-live.

- **Never edit monitoring/health-check code, `job_runs`, or the crontab**, and never
  acknowledge or widen a KNOWN-GAP on your own judgement. These are absolute.
  The two authorisations above are narrow, named exceptions granted by Will — they do not
  open the category. If a task feels like it needs more, it is a recommendation.
- A crontab edit wiped all 94 jobs on 2026-07-30. Crontab is read-only, always.

## 6. Context the agent cannot get from data

- Bright Data was the **sixth** credential-expiry outage (Gmail x2, GitHub, Google OAuth, a
  two-month FB Ads blackout). Rule 7 proves a job RAN, not that its secrets still work.
- The health board only rebuilds at 01:00, so a morning failure is invisible for ~18 hours.
- `detail` strings like `claude -p rc=1` are useless — they cannot distinguish "never started"
  from "ran out of turns". Name the actual failure.

## 7. Open questions — Will to answer

- [ ] None outstanding — both questions answered 2026-08-13.

## 8. Changelog

- 2026-08-13 — seeded by Samantha from measured data.
- 2026-08-13 — **first briefing session held with Will.** §1-§7 written from his words.
