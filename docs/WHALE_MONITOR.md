# Whale Moment — monitoring context

Linked from the **Process Registry** page of the [Fields Systems Health sheet](https://docs.google.com/spreadsheets/d/1Oa7uZv0shzsxftDYJJ3WErxhr7OZMf_SOxRFawbSgTk/edit)
(row: *Whale Moment (seasonal overlay)*). Monitor: `scripts/whale_moment_monitor.py`, daily.

---

## The one thing to know

> **One thing to expect: showings should now be rarer per navigation but possible
> across all surfaces — Bug 2 was suppressing far more than Bug 1 was causing. If
> showings go to zero rather than up, the veto is the first place to look.**

---

## What the whale is

A humpback crosses the screen once, over a lightly blurred version of the page,
when a visitor stops reading. July–September AEST only, once per person per
season. Shipped 2026-08-04. Component: `src/components/WhaleMoment/`, mounted in
`src/root.tsx` on every surface except `/off-market/*` and ops.

Four triggers, all meaning "not currently reading": footer linger ≥6s, scroll
reversal after 60% depth, idle 30s mobile / 20s desktop past 60% depth, and
desktop mouse-exit through the top.

Durable record: `system_monitor.whale_moments` (server-side, deduped per
person+season). PostHog events `whale_shown` / `whale_dismissed` / `whale_audio`
are client-side and lossy, so they enrich but never decide "did anyone see it".

## Why this monitor exists

On 2026-08-05 the only real showing to date turned out to have fired for the
wrong reason, and investigating it surfaced two defects (fix-history
`[WHALE-ROUTE-MISFIRE]`, commit `4c253949`):

**Bug 1 — fired on arrival.** The trigger's scroll state survived client-side
navigation, so React Router's scroll-to-top read as "reader walked back up" using
the *previous* page's depth. The whale landed ~10ms into a new property page —
the moment of peak intent, the exact inverse of the intended signal.

**Bug 2 — vetoed nearly everywhere.** `pageIsBusy()` matched `[role="dialog"]`
bare. MobileNav's drawer is a `role="dialog"` that is deliberately never
unmounted (so its close transition can run) and is only `inert`/`aria-hidden`
when shut — and `SiteHeader` renders it on every surface. So the veto was
permanently on and blocked every organic trigger sitewide.

The two interlocked, which is why exactly **one** showing had ever occurred: it
slipped past the permanent veto only during the drawer portal's brief remount
gap on navigation, which is the same instant Bug 1 fires in. `SiteHeader` is
rendered per-route, not in root, which is what creates that gap.

Hence the expectation quoted at the top: Bug 2 was suppressing far more than
Bug 1 was causing, so the fix should make showings **go up**, not down.

## What the monitor checks

| Signal | Meaning | Alarms when |
|---|---|---|
| `misfires_7d` | `whale_shown` within 5s of a pageview in the same session — the Bug 1 signature. Nothing legitimate can fire that fast; the fastest trigger needs 8s dwell. | any at all |
| `people_7d` = 0 | The Bug 2 signature: veto back on. | in season **and** ≥50 visitors that week |
| `continued_after_dismiss_pct` | Share of dismissals followed by more browsing in the same session. The harm check. | never — directional only |
| `median_elapsed_ms`, `audio_playing_pct` | How long it's watched; whether the iOS audio primer is working. | never — directional only |

Misfires are only counted from `FIX_DEPLOYED_AT`. The historical misfire is what
prompted this monitor and must not hold the row red for a week over a fixed bug.

Out of season (Oct–Jun AEST) zero showings is correct, so the silence alarm is
suppressed — otherwise the row sits red for nine months and stops being read.

Daily history accrues in `system_monitor.whale_monitor_daily`.

## What this deliberately does NOT measure

**"Is the whale lifting engagement or return visits?" is not answerable, and the
monitor does not pretend otherwise.** Two independent reasons:

**1. Sample size.** Site traffic is ~20–50 people/day (measured 2026-08-05 over
21 days; property pages alone are ~5/day). Baseline return rate is **4.9%** —
over 30 days, 1,232 people had one session and only 64 came back at all.
Detecting even a *doubling* of that (4.9% → 9.8%) at 80% power needs roughly
**450 people per arm**; a more realistic 50% lift needs ~1,450 per arm. The
season ends 30 September. The numbers required do not exist and will not.

**2. Selection bias.** The trigger fires *on disengagement* — footer linger,
scroll reversal, idle, exit intent. Whale-seers are, by construction, people who
had already stopped reading and were on their way out. Comparing them to
non-seers measures the trigger's selection criteria, not the whale's effect, and
would make the whale look actively harmful no matter what it does.

A holdout would fix reason 2 but not reason 1, and would halve an already
insufficient sample while denying half the audience the thing itself. **Not
recommended.**

What *is* readable at this sample size is within-person: did a given visitor keep
browsing after dismissing? That needs no control group and reads usefully at
n≈20. It answers "is this driving people away", which is the question that
actually has a decision attached to it. It does not answer "is this helping",
and no amount of dashboard will change that.

**Judge the whale as a craft and brand decision, not as a conversion lever.**
The monitor's job is to guarantee it is working as designed and not doing harm.

## If the row goes red

- **misfires** → the trigger is firing on arrival again. Check that per-page
  scroll state still re-baselines on path change in `useWhaleTrigger.ts`; keying
  the effect on `pathname` alone is **not** sufficient (the deps re-run is a
  passive effect, React Router's scroll restore a layout effect — the stale
  listener still won ~1 nav in 3).
- **silence** → check `pageIsBusy()` first. Anything that adds a persistent
  `role="dialog"`/`aria-modal` to the page, or locks `body.overflow`, re-creates
  Bug 2 and silently suppresses every trigger sitewide.
- **STALE** → the cron stopped; see `crontab -l`.

Verify trigger changes on the `/api/v1/whale-alert` payload, not the overlay DOM
— the overlay only renders once sprites load, so it lags the trigger and cannot
tell you *which* signal fired. Always run the control against pre-fix code: the
first two harnesses written for this both "passed" against the live bug.
