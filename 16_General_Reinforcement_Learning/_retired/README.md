# Retired — the self-pacing General RL machinery (2026-08-13)

These files implemented the **daily self-pacing** design that ran 2026-07-29 → 07-30 and was
paused by Will on 07-30. They are kept for reference, not use. Nothing in the live system
imports or invokes them, and no active cron line references them.

## Why they were retired

Each domain chose its own next wake (`cycle_pacer.py --set-next`), was permitted **14 runs a
day**, and every prompt ended *"CHAIN 20–45 min if actionable work in hand."* A cheap
dispatcher polled every 20 minutes and launched the expensive `claude -p` only when the
domain had scheduled itself. Mechanically this worked — 299 dispatcher polls produced 27
cycles. The problem was never efficiency.

Six agents pacing themselves, each with its own Telegram line to Will, produced **31
human-decision items in 48 hours** and a 1,773-line action file with 48 items open. The
pacer optimised the resource that was cheap (compute) and spent the one that was scarce
(Will's attention). Replaced by fixed weekly cron — see `../weekly_cycle.sh`.

## What each file was

| File | Was | Replaced by |
|---|---|---|
| `cycle_pacer.py` | self-pacing state machine, `--claim` / `--set-next`, cap 14/day | cron |
| `cycle_state.py` | near-verbatim stale fork of `cycle_pacer.py`, hardcoded to geo | — |
| `rl_cycle.sh` / `rl_dispatch.sh` | generic daily runner + poller | `weekly_cycle.sh` |
| `geo_cycle.sh` / `geo_dispatch.sh` | pre-refactor fork of the above, geo-only | `weekly_cycle.sh geo` |
| `seo_cycle.sh` / `seo_dispatch.sh` | thin shims | `weekly_cycle.sh seo` |
| `conductor_cycle.sh` / `conductor_dispatch.sh` | meta-conductor runner, 3 wake lanes | `samantha_weekly.sh` |
| `ops_cycle.sh` | standalone daily ops runner on Opus 5 | `weekly_cycle.sh ops` |
| `rl_selftest.py` | 51-check self-test | Rule-7b assertions in `weekly_cycle.sh` |
| `organize_cycles.py` | filed stray cycle docs into weekly folders | runner sets `$CYCLE_DIR` |
| `personalization_policy.py` | already retired upstream; superseded by `rl_onsite_experiments` | — |

## Two of these were actively misleading, which is why they are gone rather than dormant

- **`rl_selftest.py`** verified cron wiring with a substring match against `crontab -l`.
  The paused lines were *comments containing those exact strings*, so every cron check
  passed green while nothing was scheduled. It also required all five sensors fresh to
  pass, so it could never be green once the fleet paused. A monitor that cannot fail
  usefully is worse than no monitor.
- **`cycle_state.py`** wrote the same `rl_geo_cycle_state` document as
  `cycle_pacer.py --job geo`, with no coordination between the two writers. `geo_cycle.sh`
  never exported `PACER_JOB`, so a geo agent calling `cycle_pacer.py --set-next` without
  `--job` would have silently written **seo's** pacer state (the default is `"seo"`).

`ops_integrity.py` was NOT retired — its tamper-baseline guard is now invoked directly by
`weekly_cycle.sh` for the ops domain.
