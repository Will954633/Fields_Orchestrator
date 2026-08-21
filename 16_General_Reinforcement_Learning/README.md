# General Reinforcement Learning — how it works now

> ## 🔎 START HERE — this folder IS "Samantha and her domain agents"
>
> **If Will says "check in with Samantha", "check in with the domain agents", "how are
> the autonomous agents doing", or anything of that shape — he means THIS system.** It was
> hard to find once (2026-08-22); this banner exists so it never is again.
>
> **What it is:** a weekly team of 7 AI analyst agents — `geo`, `seo`, `ads`, `articles`,
> `onsite`, `ops`, `valuation` — each owning one slice of the business. They run Sundays
> (staggered hourly, see cron), file capped recommendations, and **Samantha** (the
> `conductor` / `samantha_weekly.sh`) dedupes + ranks them into ONE brief of ≤5 decisions
> sent to Will on Telegram. The domains NEVER message Will directly — that is the core
> design rule. The full mechanics are in the rest of this README below.
>
> **Do a check-in with these five commands** (from this folder, venv + `.env` loaded):
> ```bash
> python3 briefing_status.py                       # ← the thing most likely to be chasing Will
> python3 recommendations.py brief-candidates      # what's awaiting Will's decision now
> python3 recommendations.py stats                 # per-domain approval rate & hit rate
> tail -40 ../logs/rl_weekly_cron.log              # did last Sunday's cycles actually run?
> python3 fix_digest.py --days 7                   # what changed in the business this week
> ```
>
> **The four things that go wrong silently — check each on every check-in:**
>
> 1. **Briefing staleness (`briefing_status.py`).** Each domain's `briefings/<domain>.md`
>    is a standing *authorisation*, not a memo. It ages: **current** (<7d, full autonomy) →
>    **aging** (8–13d, full but Will is reminded) → **stale** (14–20d, NARROWED to bug-fixes
>    only) → **expired** (21+d, recommend-only). A daily cron (`briefing_status.py --remind`,
>    08:30) Telegrams Will while any brief is due; the "day N" counter is the chase streak.
>    Refreshing a brief = `briefing_status.py --touch <domain>` after editing it. **This is
>    the alert Will most often asks about.** Renewing the briefs is a Will+Samantha session:
>    Will says what's changed per domain, Samantha writes them up.
> 2. **Weekly cycles failing (`../logs/rl_weekly_cron.log`).** Each domain must write a cycle
>    doc under `cycles/<ISO-week>/<date>/`. A line `heartbeat: error — … NO CYCLE DOC written`
>    means that domain skipped the week and produced nothing. (`seo` was failing rc=1/rc=124
>    as of 2026-08-16 — check whether it recovered.)
> 3. **Recommendation queue (`recommendations.py brief-candidates`).** 0 open = domains have
>    cleared their queue (fine). Anything open is awaiting Will and should be in the brief.
> 4. **Ungraded claims (`recommendations.py stats`, "actually worked" column).** Every shipped
>    rec states a metric + date; `due-for-grading` surfaces them, `grade` records the outcome.
>    A domain that never gets graded is an idea generator that never learns if it was right.
>
> **Cadence at a glance:** domain cycles Sun 06:00–12:00 (ops→seo→geo→ads→articles→onsite→
> valuation) · Samantha's brief Sun 16:00 · reward ledger Sun 05:30 · briefing reminder daily
> 08:30 · recommendation-approval poller every 5 min (07–22). All in the VM crontab, grep
> `16_General`. Note `ops` runs standalone on Opus 5, not the shared runner.
>
> ---


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
  Sunday 06:00–12:00        Sunday 16:00              Will, whenever he likes
  ┌──────────────────┐      ┌───────────────┐         ┌──────────────────┐
  │ 7 domain agents  │─────▶│   Samantha    │────────▶│  ONE brief       │
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

**`valuation` was the first one added this way (2026-08-13)** — see it as the worked example.
Six of the seven domains are top-of-funnel marketing; that one watches the *product* (the
reconciled valuation and its range) rather than the traffic, on the reasoning that the
data-rich half of the business had nobody looking at it while five agents competed to bring
more people to a number none of them checked.

The remaining candidates, still one at a time: **data coverage** (Domain under-capture
40–50%), **editorial freshness** (51% of editorial arguing against a dead price), and
**off-market deck integrity** (231 decks the database claims completed and which are
permanently missing content).

⚠ Two things the valuation build learned that the next one should copy:

1. **Verify every field path before the sensor queries it** (Rule 8). The headline claim
   going in was "57% of the for-sale book can't be valued". The real number is **59.4%**,
   `directional_only` exists in **three copies that disagree**, and `confidence_reason` —
   which CLAUDE.md refers to — **does not exist** at that path at all. A sensor built on
   remembered field names measures nothing and reports it confidently.
2. **Start a product domain read-only.** A marketing domain that ships a bad change costs a
   week of traffic; a valuation domain that ships one puts a wrong number in a document
   posted to somebody's house. `valuation`'s §4 authorises sensors, backtests, reading and
   records — nothing else — until Will has read one cycle.
