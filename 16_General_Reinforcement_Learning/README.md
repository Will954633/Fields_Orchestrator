# General Reinforcement Learning — how it works now

**Rebuilt 2026-08-13.** This supersedes `00_SCOPING.md`, `DEVELOPMENT_PLAN.md` and
`PHASE2_DESIGN.md`, which describe the daily self-pacing design that ran 2026-07-29 → 07-30
and was paused. Those documents are still worth reading for the *thesis* (the closed
SENSE→STEER→ACQUIRE→CONVERT loop, the milestone map, the cost-per-outcome reward). What
changed is the **cadence, the output channel, and the feedback path** — not the ambition.

It is not machine-learning RL. It is a set of AI analysts that observe, hypothesise, act
where it is safe, record what happened, and compound across cycles.

---

## The loop, in one picture

```
  Sunday 06:00–11:00        Sunday 16:00              Will, whenever he likes
  ┌──────────────────┐      ┌───────────────┐         ┌──────────────────┐
  │ 6 domain agents  │─────▶│   Samantha    │────────▶│  ONE brief       │
  │ (staggered 1h)   │ recs │ dedupe · rank │ ≤5 asks │  numbered Qs     │
  └──────────────────┘      │ challenge N   │         └────────┬─────────┘
        ▲    ▲              └───────────────┘                  │
        │    │                      ▲                          │ "1 yes, 2 no
        │    │                      │ verdicts + REASONS       │  because X"
        │    └──────────────────────┴──────────────────────────┘
        │                    the learning signal
        │
        └─ fix_digest.py: what changed in the business since last week
```

**The domains never speak to Will.** That is the single most important property. Six agents
each deciding their own finding was urgent is what produced 31 decision items in 48 hours
and got the first version switched off.

## The pieces

| File | Role |
|---|---|
| `weekly_cycle.sh <domain>` | fixed-cadence runner: refresh sensor → prepend contract → run agent → assert outcome |
| `_CYCLE_CONTRACT.md` | the rules binding **all** domains. Prepended at run time, so it cannot drift. **Overrides the domain mandate** where they disagree |
| `<domain>_prompt.md` | that domain's mandate — what it looks at, what it may do unattended |
| `<domain>_signal.py` | that domain's sensor. Refreshed by the runner immediately before the agent, so nobody reasons over a stale snapshot |
| `recommendations.py` | the ledger. Caps, verdicts, outcome grading |
| `fix_digest.py` | index over `logs/fix-history/` so an agent can see what changed without reading 7,000 lines |
| `samantha_weekly.sh` + `samantha_weekly_prompt.md` | synthesis and the single channel to Will |
| `_retired/` | the old self-pacing machinery, with a README explaining why each piece went |

## The three rules that make it work

**1. A hard cap, enforced in code.** `MAX_OPEN_PER_DOMAIN = 2`. `propose` *refuses* a third
and tells the agent to supersede or withdraw. Will's brief is capped at **5 decisions**. The
old backlog reached 48 open items because nothing stopped it; now that state is
unrepresentable. If an idea did not make a domain's top two, it waits — that is the feature.

**2. Verdicts carry reasons, and reasons come back.** `recommendations.py verdict` requires
`--reason`. Next cycle, `feedback --domain X` replays those reasons to the domain. This is
the loop actually closing, and it did not exist before: domains never learned what Will
accepted or why he refused. After a few weeks a domain should be able to predict him.

**3. Claims get graded.** A recommendation states a metric and a date. When it ships, the
clock starts; `due-for-grading` surfaces it; `grade` records whether it worked. `stats`
shows per-domain approval rate *and* hit rate — two different failures. Without this the
system is an idea generator that never finds out if it was right, which is exactly what the
first version was.

## Running it by hand

```bash
bash weekly_cycle.sh seo          # one domain, now
bash samantha_weekly.sh           # the brief, now

python3 recommendations.py brief-candidates      # everything awaiting Will
python3 recommendations.py feedback --domain ads # what Will told ads, and why
python3 recommendations.py stats                 # who is worth listening to
python3 fix_digest.py --days 7 --domain ops      # what changed
```

## Honest limits — read before quoting any number this system produces

- **The traffic cannot support statistics.** The reward ledger rests on **7 conversions**.
  The "26× address-search lever" is 7 of 10 people. An arm was graded "1.13× leading" on 14
  conversions vs 11; one experiment had a single user per arm. Mechanism reasoning at low N
  is legitimate and is how the FB funnel works — presenting it as statistical evidence is
  not. The contract requires every claim to carry its denominator.
- **Onsite experiments are effectively parked.** They render nothing until the master
  kill-switch `genrl_personalization_v1` is flipped, which has never happened.
- **`rl_<domain>_actions` had no writer.** Five mandates told agents to read those
  collections to avoid repeating themselves; no code ever created them. Agents must write
  them properly for that instruction to mean anything.
- **A weekly cycle cannot do hot-lead work.** The onsite mandate was written to surface a
  warm vendor "within the hour". At weekly cadence its value is the *pattern* across the
  week, not the individual alert. If per-visitor latency turns out to matter, that belongs
  in a separate always-on job, not here.

## Adding a domain

Write `<name>_prompt.md` and `<name>_signal.py`, add a row plus `fix_keywords` to
`domains.yaml`, add one cron line calling `weekly_cycle.sh <name>`, and add it to the list
Samantha checks in `samantha_weekly_prompt.md` step 2. Nothing else.

The six current domains are all top-of-funnel marketing. The data-rich parts of the business
with no watcher — valuation quality, data coverage, editorial freshness, off-market deck
integrity — are the obvious candidates, one at a time, once the loop has proven itself.
